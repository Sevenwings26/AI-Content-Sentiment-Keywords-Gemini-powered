# modules/connectors/sources/databases/base_db_connector.py
import time
import uuid
import logging
from abc import abstractmethod
from typing import Generator, Dict, Any, Optional, List
from sqlalchemy import create_engine, text, inspect

from modules.connectors.base import BaseConnector, RawDocument
from modules.connectors.security.sql_guard import (
    SQLSecurityGuard, InsecureQueryError, DatabaseSecurityTargetError
)
from modules.connectors.sources.databases.schema_reflector import DatabaseSchemaReflector

logger = logging.getLogger("base_database_connector")

class BaseDatabaseConnector(BaseConnector):
    """
    Dual-Mode Relational Database Connector.
    - Default Mode (SCHEMA_REFLECTION): Auto-reflects live tables, column types, and foreign keys
      for zero-config Dynamic Text-to-SQL without requiring custom SQL queries.
    - Optional Mode (ROW_EXTRACTION): Extracts and streams row text for semantic vector indexing
      when an explicit extraction query is supplied.
    """

    def __init__(
        self,
        connection_config: Dict[str, Any],
        dialect: str,
        source_type: str,
        default_query: Optional[str] = None
    ):
        self.config_data = connection_config
        self.dialect = SQLSecurityGuard.canonical_dialect(dialect)
        self.source_type = source_type

        # 1. Build and normalize connection string with URL-encoded credentials
        self.db_url = SQLSecurityGuard.safe_build_db_url(self.dialect, connection_config)

        # 2. Extract configuration parameters
        raw_query = connection_config.get("sql_query") or default_query
        self.table_name = connection_config.get("table_name")
        self.target_schema = connection_config.get("target_schema")
        self.allowed_tables = connection_config.get("allowed_tables")
        self.text_column = connection_config.get("text_column")
        self.filename_column = connection_config.get("filename_column")

        # 3. Determine Execution Mode
        if raw_query and str(raw_query).strip():
            self.mode = "ROW_EXTRACTION"
            self.sql_query = SQLSecurityGuard.validate_query(str(raw_query).strip(), dialect=self.dialect)
        elif self.table_name and str(self.table_name).strip() and self.text_column:
            self.mode = "ROW_EXTRACTION"
            self.sql_query = SQLSecurityGuard.validate_query(f"SELECT * FROM {self.table_name}", dialect=self.dialect)
        else:
            self.mode = "SCHEMA_REFLECTION"
            self.sql_query = None

    @abstractmethod
    def get_version_query(self) -> str:
        """Returns the engine-specific SQL query to test connectivity and get server version."""
        pass

    def test_connection(self) -> Dict[str, Any]:
        """
        Executes a safe pre-flight connection test with SSRF validation,
        5-second timeout, read-only transaction parameters, and credential masking.
        """
        start = time.perf_counter()
        try:
            # Step 1: Pre-flight SSRF & Network Validation
            SQLSecurityGuard.validate_db_target(self.dialect, self.db_url)

            # Step 2: Connect with 5-second timeout
            connect_args = {"connect_timeout": 5} if self.dialect in ("postgresql", "mysql") else {}
            engine = create_engine(self.db_url, connect_args=connect_args)

            version_str = "Unknown"
            detected_tables: List[str] = []
            columns: List[str] = []

            with engine.connect() as conn:
                try:
                    version_str = str(conn.execute(text(self.get_version_query())).scalar() or "Connected")[:80]
                except Exception:
                    version_str = f"{self.dialect.title()} Database"

                if self.mode == "ROW_EXTRACTION" and self.sql_query:
                    # Validate query AST
                    SQLSecurityGuard.validate_query(self.sql_query, dialect=self.dialect)
                    
                    if self.dialect == "oracle":
                        test_sql = f"SELECT * FROM ({self.sql_query}) WHERE ROWNUM <= 1"
                    elif self.dialect == "mssql":
                        test_sql = f"SELECT TOP 1 * FROM ({self.sql_query}) AS tmp_sec_test"
                    else:
                        test_sql = f"SELECT * FROM ({self.sql_query}) AS tmp_sec_test LIMIT 1"

                    row_check = conn.execute(text(test_sql)).mappings().first()
                    if row_check:
                        columns = list(row_check.keys())
                else:
                    # Reflect available tables
                    try:
                        inspector = inspect(engine)
                        detected_tables = [
                            t for t in inspector.get_table_names(schema=self.target_schema)
                            if not t.startswith(("pg_", "alembic_", "information_schema"))
                        ]
                    except Exception as e:
                        logger.warning(f"Inspector table discovery notice: {e}")
                        detected_tables = []

            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "success": True,
                "latency_ms": latency,
                "message": f"{self.dialect.title()} Handshake Verified ({latency}ms)",
                "details": {
                    "server_version": version_str,
                    "target_url_masked": SQLSecurityGuard.mask_db_url(self.db_url),
                    "mode": self.mode,
                    "detected_tables": detected_tables,
                    "detected_columns": columns if self.mode == "ROW_EXTRACTION" else None
                }
            }
        except InsecureQueryError as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "success": False,
                "latency_ms": latency,
                "message": f"Security Violation in SQL Query: {str(e)}",
                "details": None
            }
        except DatabaseSecurityTargetError as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "success": False,
                "latency_ms": latency,
                "message": f"Network Security Block: {str(e)}",
                "details": None
            }
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            masked_error = str(e).replace(self.db_url, SQLSecurityGuard.mask_db_url(self.db_url))
            return {
                "success": False,
                "latency_ms": latency,
                "message": f"{self.dialect.title()} Handshake Failed: {masked_error}",
                "details": None
            }

    def fetch_documents(self) -> Generator[RawDocument, None, None]:
        """
        Streams database content based on execution mode:
        - SCHEMA_REFLECTION: Introspects tables and yields clean DDL schema documents.
        - ROW_EXTRACTION: Streams data rows inside a read-only transaction sandbox.
        """
        SQLSecurityGuard.validate_db_target(self.dialect, self.db_url)

        if self.mode == "SCHEMA_REFLECTION":
            # 1. Reflect schema tables and generate DDL documents
            db_name = str(self.config_data.get("database") or self.config_data.get("service_name") or "db")
            reflected_tables = DatabaseSchemaReflector.reflect_schema(
                dialect=self.dialect,
                db_url=self.db_url,
                target_schema=self.target_schema,
                allowed_tables=self.allowed_tables
            )
            schema_docs = DatabaseSchemaReflector.generate_schema_documents(
                reflected_tables=reflected_tables,
                dialect=self.dialect,
                source_type=self.source_type,
                db_name=db_name
            )
            for doc in schema_docs:
                yield doc

        else:
            # 2. Row-Level Vectorization Stream
            SQLSecurityGuard.validate_query(self.sql_query, dialect=self.dialect)
            engine = create_engine(self.db_url)
            row_stream = SQLSecurityGuard.execute_read_only_query(
                engine=engine,
                dialect=self.dialect,
                sql_query=self.sql_query,
                timeout_ms=15000,
                batch_size=500
            )

            row_index = 0
            for row_dict in row_stream:
                row_index += 1
                text_content = ""
                if self.text_column and self.text_column in row_dict and row_dict[self.text_column]:
                    text_content = str(row_dict[self.text_column]).strip()
                else:
                    candidate_text_cols = ["content", "text", "body", "description", "details", "article", "message"]
                    found_col = next((c for c in candidate_text_cols if c in row_dict and row_dict[c]), None)
                    if found_col:
                        title_part = f"{row_dict.get('title', '')}\n" if 'title' in row_dict and row_dict.get('title') else ""
                        text_content = f"{title_part}{str(row_dict[found_col]).strip()}"
                    else:
                        kv_pairs = [f"{k}: {v}" for k, v in row_dict.items() if v is not None and str(v).strip() != ""]
                        text_content = f"[{self.source_type} Record]\n" + " | ".join(kv_pairs)

                if not text_content.strip():
                    continue

                if self.filename_column and self.filename_column in row_dict and row_dict[self.filename_column]:
                    raw_filename = str(row_dict[self.filename_column])
                elif "id" in row_dict and row_dict["id"]:
                    raw_filename = f"record_{row_dict['id']}"
                elif "title" in row_dict and row_dict["title"]:
                    raw_filename = str(row_dict["title"])[:50].replace(" ", "_")
                else:
                    raw_filename = f"record_{row_index}"

                filename = f"{raw_filename}.txt" if not raw_filename.endswith(".txt") else raw_filename
                doc_id = str(uuid.uuid4())

                metadata = {
                    "sql_row_id": str(row_dict.get("id", row_index)),
                    "source_dialect": self.dialect,
                    "source_type": self.source_type
                }

                yield RawDocument(
                    doc_id=doc_id,
                    source_type=self.source_type,
                    filename=filename,
                    content_bytes=text_content.encode("utf-8"),
                    mime_type="text/plain",
                    metadata=metadata
                )
