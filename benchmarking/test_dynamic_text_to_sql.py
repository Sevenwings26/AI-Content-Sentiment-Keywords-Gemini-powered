# benchmarking/test_dynamic_text_to_sql.py
import sys
import os
import unittest
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, text

from modules.connectors.schemas import PostgreSQLConfig, MySQLConfig, ConnectorSourceType
from modules.connectors.registry import ConnectorRegistry
from modules.connectors.security.sql_guard import SQLSecurityGuard, InsecureQueryError
from modules.connectors.sources.databases.schema_reflector import DatabaseSchemaReflector
from modules.connectors.sources.databases.postgres_connector import PostgreSQLConnector
from modules.rag_core.tools.sql_agent import DynamicSQLAgent
from modules.rag_core.providers.llm import BaseLLMService
from modules.rag_core.orchestrator.query_planner import QueryPlanner

class MockTextToSQLLLM(BaseLLMService):
    def __init__(self, response_text: str):
        self.response_text = response_text

    def generate_text(self, prompt: str, system_instruction: Optional[str] = None, **kwargs) -> str:
        return self.response_text

    def get_embeddings(self, text: str) -> List[float]:
        return [0.1] * 1024

class TestDynamicTextToSQL(unittest.TestCase):
    """
    Comprehensive verification suite for Dual-Engine Database Ingestion & Text-to-SQL.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_db_path = "/tmp/test_enterprise_sales.db"
        cls.engine = create_engine(f"sqlite:///{cls.test_db_path}")
        with cls.engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS orders;"))
            conn.execute(text("DROP TABLE IF EXISTS customers;"))
            conn.execute(text("""
                CREATE TABLE customers (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    region VARCHAR(50) NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL,
                    order_date VARCHAR(20) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    FOREIGN KEY (customer_id) REFERENCES customers(id)
                );
            """))
            conn.execute(text("INSERT INTO customers (id, name, region) VALUES (1, 'Acme Corp', 'North America'), (2, 'Globex', 'Europe');"))
            conn.execute(text("INSERT INTO orders (id, customer_id, amount, order_date, status) VALUES (101, 1, 1500.00, '2026-08-01', 'COMPLETED'), (102, 1, 3500.00, '2026-08-15', 'COMPLETED'), (103, 2, 800.00, '2026-08-20', 'PENDING');"))
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)

    def test_01_schema_reflector_extracts_ddl(self):
        """Verify DatabaseSchemaReflector reflects tables, columns, primary keys, and foreign keys."""
        reflected = DatabaseSchemaReflector.reflect_schema(
            dialect="sqlite",
            db_url=f"sqlite:///{self.test_db_path}"
        )
        table_names = [t["table_name"] for t in reflected]
        self.assertIn("customers", table_names)
        self.assertIn("orders", table_names)

        orders_meta = next(t for t in reflected if t["table_name"] == "orders")
        self.assertIn("id", orders_meta["column_names"])
        self.assertIn("amount", orders_meta["column_names"])
        self.assertIn("CREATE TABLE", orders_meta["ddl"])

        schema_docs = DatabaseSchemaReflector.generate_schema_documents(
            reflected_tables=reflected,
            dialect="sqlite",
            source_type="SQLITE_DB",
            db_name="test_enterprise_sales"
        )
        self.assertEqual(len(schema_docs), 2)
        self.assertEqual(schema_docs[0].metadata["chunk_type"], "sql_schema")
        self.assertTrue(schema_docs[0].filename.startswith("schema_"))

    def test_02_dual_mode_connector_defaults_to_schema_reflection(self):
        """Verify connector operates in SCHEMA_REFLECTION mode when no extraction query is provided."""
        cfg = {
            "host": "localhost",
            "port": 5432,
            "database": "knowledge_db",
            "username": "postgres",
            "password": "secret_password"
        }
        connector = PostgreSQLConnector(cfg)
        self.assertEqual(connector.mode, "SCHEMA_REFLECTION")
        self.assertIsNone(connector.sql_query)

    def test_03_dual_mode_connector_switches_to_row_extraction_on_custom_query(self):
        """Verify connector switches to ROW_EXTRACTION mode when custom query is supplied."""
        cfg = {
            "host": "localhost",
            "port": 5432,
            "database": "knowledge_db",
            "username": "postgres",
            "password": "secret_password",
            "sql_query": "SELECT id, title, content FROM enterprise_policies",
            "text_column": "content"
        }
        connector = PostgreSQLConnector(cfg)
        self.assertEqual(connector.mode, "ROW_EXTRACTION")
        self.assertEqual(connector.sql_query, "SELECT id, title, content FROM enterprise_policies")

    def test_04_dynamic_sql_agent_generates_and_executes_safe_query(self):
        """Verify DynamicSQLAgent translates natural language into safe SQL and retrieves live rows."""
        mock_llm = MockTextToSQLLLM("```sql\nSELECT SUM(amount) AS total_revenue FROM orders WHERE customer_id = 1;\n```")
        schema_context = "CREATE TABLE orders (id INTEGER, customer_id INTEGER, amount NUMERIC, status VARCHAR);"

        result = DynamicSQLAgent.generate_and_execute_sql(
            user_query="What is the total revenue for customer 1?",
            schema_context=schema_context,
            dialect="sqlite",
            db_url=f"sqlite:///{self.test_db_path}",
            llm_service=mock_llm
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(float(result["rows"][0]["total_revenue"]), 5000.00)

    def test_05_dynamic_sql_agent_rejects_write_and_destructive_mutations(self):
        """Verify DynamicSQLAgent strictly rejects any generated mutation statements via AST guard."""
        # 1. Single-statement mutation rejection
        mock_llm_mutation = MockTextToSQLLLM("DELETE FROM orders WHERE id = 101;")
        result_mut = DynamicSQLAgent.generate_and_execute_sql(
            user_query="Delete order 101",
            schema_context="CREATE TABLE orders (id INTEGER);",
            dialect="sqlite",
            db_url=f"sqlite:///{self.test_db_path}",
            llm_service=mock_llm_mutation
        )
        self.assertEqual(result_mut["status"], "security_violation")
        self.assertIn("Security Violation", result_mut["error"])
        self.assertIn("DELETE", result_mut["error"])

        # 2. Multi-statement injection rejection
        mock_llm_stacked = MockTextToSQLLLM("DROP TABLE orders; SELECT * FROM orders;")
        result_stacked = DynamicSQLAgent.generate_and_execute_sql(
            user_query="Drop and select",
            schema_context="CREATE TABLE orders (id INTEGER);",
            dialect="sqlite",
            db_url=f"sqlite:///{self.test_db_path}",
            llm_service=mock_llm_stacked
        )
        self.assertEqual(result_stacked["status"], "security_violation")
        self.assertIn("Security Violation", result_stacked["error"])

    def test_06_query_planner_identifies_structured_sql_intent(self):
        """Verify QueryPlanner routes analytical aggregation queries to STRUCTURED_SQL."""
        plan1 = QueryPlanner.analyze_and_plan("What is the total revenue in Q3?")
        self.assertTrue(plan1.is_structured_sql)
        self.assertEqual(plan1.intent_category, "STRUCTURED_SQL")

        plan2 = QueryPlanner.analyze_and_plan("How many employees are in Engineering?")
        self.assertTrue(plan2.is_structured_sql)

        plan3 = QueryPlanner.analyze_and_plan("What is our remote work travel policy?")
        self.assertFalse(plan3.is_structured_sql)
        self.assertEqual(plan3.intent_category, "DOCUMENT_RAG")

if __name__ == "__main__":
    unittest.main()
