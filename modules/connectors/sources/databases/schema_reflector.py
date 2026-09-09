# modules/connectors/sources/databases/schema_reflector.py
import uuid
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, MetaData, inspect
from sqlalchemy.schema import CreateTable

from modules.connectors.base import RawDocument
from modules.connectors.security.sql_guard import (
    SQLSecurityGuard, DatabaseSecurityTargetError
)

logger = logging.getLogger("schema_reflector")

class DatabaseSchemaReflector:
    """
    Introspects and reflects live database schemas using safe metadata inspection.
    Extracts table names, column data types, primary keys, and foreign keys,
    compiling them into clean DDL documents for Dynamic Text-to-SQL.
    """

    @classmethod
    def reflect_schema(
        cls,
        dialect: str,
        db_url: str,
        target_schema: Optional[str] = None,
        allowed_tables: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Reflects accessible tables and builds structured DDL metadata representations.
        """
        canonical = SQLSecurityGuard.canonical_dialect(dialect)
        SQLSecurityGuard.validate_db_target(canonical, db_url)

        connect_args = {"connect_timeout": 5} if canonical in ("postgresql", "mysql") else {}
        engine = create_engine(db_url, connect_args=connect_args)

        reflected_tables: List[Dict[str, Any]] = []

        try:
            metadata = MetaData(schema=target_schema)
            metadata.reflect(bind=engine, only=allowed_tables)

            for table_name, table in metadata.tables.items():
                short_name = table.name
                
                # Filter out system and migration tables
                if short_name.startswith(("pg_", "alembic_", "information_schema")):
                    continue

                # Compile clean CREATE TABLE DDL
                try:
                    ddl_str = str(CreateTable(table).compile(engine)).strip()
                except Exception:
                    # Fallback manual column extraction if dialect compilation issues arise
                    cols_desc = [f"  {c.name} {c.type}" for c in table.columns]
                    ddl_str = f"CREATE TABLE {short_name} (\n" + ",\n".join(cols_desc) + "\n);"

                pks = [c.name for c in table.primary_key.columns]
                fks = [
                    f"{fk.parent.name} -> {fk.column.table.name}.{fk.column.name}"
                    for fk in table.foreign_keys
                ]
                columns = [
                    {"name": c.name, "type": str(c.type), "nullable": c.nullable}
                    for c in table.columns
                ]

                reflected_tables.append({
                    "table_name": short_name,
                    "full_table_name": table_name,
                    "schema": target_schema or table.schema,
                    "ddl": ddl_str,
                    "primary_keys": pks,
                    "foreign_keys": fks,
                    "columns": columns,
                    "column_names": [c["name"] for c in columns]
                })

            logger.info(f"[SCHEMA REFLECTOR] Successfully reflected {len(reflected_tables)} tables for {canonical}")
            return reflected_tables
        except Exception as e:
            logger.error(f"[SCHEMA REFLECTOR] Failed to reflect schema: {e}")
            raise

    @classmethod
    def generate_schema_documents(
        cls,
        reflected_tables: List[Dict[str, Any]],
        dialect: str,
        source_type: str,
        db_name: str
    ) -> List[RawDocument]:
        """
        Converts reflected table metadata into lightweight RawDocument instances
        formatted for schema cataloging and LLM SQL Agent context.
        """
        schema_docs: List[RawDocument] = []

        for tbl in reflected_tables:
            table_name = tbl["table_name"]
            ddl_text = tbl["ddl"]
            pks = ", ".join(tbl["primary_keys"]) if tbl["primary_keys"] else "None"
            fks = ", ".join(tbl["foreign_keys"]) if tbl["foreign_keys"] else "None"

            structured_content = (
                f"-- Database Schema DDL for Table: {table_name}\n"
                f"-- Dialect: {dialect} | Database: {db_name}\n"
                f"-- Primary Keys: {pks}\n"
                f"-- Foreign Keys: {fks}\n\n"
                f"{ddl_text}\n"
            )

            doc_id = str(uuid.uuid4())
            metadata = {
                "chunk_type": "sql_schema",
                "table_name": table_name,
                "database_name": db_name,
                "dialect": dialect,
                "source_type": source_type,
                "column_names": tbl["column_names"],
                "primary_keys": tbl["primary_keys"],
                "foreign_keys": tbl["foreign_keys"]
            }

            schema_docs.append(RawDocument(
                doc_id=doc_id,
                source_type=source_type,
                filename=f"schema_{table_name}.sql",
                content_bytes=structured_content.encode("utf-8"),
                mime_type="application/sql",
                metadata=metadata
            ))

        return schema_docs
