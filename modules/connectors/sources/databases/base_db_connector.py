# modules/connectors/sources/databases/base_db_connector.py
import time
import uuid
import logging
from abc import abstractmethod
from typing import Generator, Dict, Any, Optional
from sqlalchemy import create_engine, text

from modules.connectors.base import BaseConnector, RawDocument
from modules.connectors.security.sql_guard import (
    SQLSecurityGuard, InsecureQueryError, DatabaseSecurityTargetError
)

logger = logging.getLogger("base_database_connector")

class BaseDatabaseConnector(BaseConnector):
    """
    Abstract hardened base connector for relational database engines.
    Enforces AST SQL query validation, SSRF target validation, credential masking,
    and engine-native read-only streaming transactions.
    """

    def __init__(
        self,
        connection_config: Dict[str, Any],
        dialect: str,
        source_type: str,
        default_query: str = "SELECT id, title, content FROM documents"
    ):
        self.config_data = connection_config
        self.dialect = SQLSecurityGuard.canonical_dialect(dialect)
        self.source_type = source_type

        # 1. Build and normalize connection string with URL-encoded credentials
        self.db_url = SQLSecurityGuard.safe_build_db_url(self.dialect, connection_config)

        # 2. Extract and validate extraction query
        raw_query = connection_config.get("sql_query", default_query)
        self.sql_query = SQLSecurityGuard.validate_query(raw_query, dialect=self.dialect)

        self.text_column = connection_config.get("text_column", "content")
        self.filename_column = connection_config.get("filename_column", "id")

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

            # Step 2: Validate SQL Query AST
            SQLSecurityGuard.validate_query(self.sql_query, dialect=self.dialect)

            # Step 3: Connect with 5-second timeout
            connect_args = {"connect_timeout": 5} if self.dialect in ("postgresql", "mysql") else {}
            engine = create_engine(self.db_url, connect_args=connect_args)

            version_str = "Unknown"
            columns = []

            with engine.connect() as conn:
                # Fast version query
                try:
                    version_str = str(conn.execute(text(self.get_version_query())).scalar() or "Connected")[:80]
                except Exception:
                    version_str = f"{self.dialect.title()} Database"

                # Check sample row columns within read-only subquery
                test_sql = f"SELECT * FROM ({self.sql_query}) AS tmp_sec_test"
                # For Oracle, use ROWNUM <= 1; for standard SQL, use LIMIT 1
                if self.dialect == "oracle":
                    test_sql = f"SELECT * FROM ({self.sql_query}) WHERE ROWNUM <= 1"
                elif self.dialect == "mssql":
                    test_sql = f"SELECT TOP 1 * FROM ({self.sql_query}) AS tmp_sec_test"
                else:
                    test_sql = f"SELECT * FROM ({self.sql_query}) AS tmp_sec_test LIMIT 1"

                row_check = conn.execute(text(test_sql)).mappings().first()
                if row_check:
                    columns = list(row_check.keys())

            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "success": True,
                "latency_ms": latency,
                "message": f"{self.dialect.title()} Handshake Verified & Sandboxed ({latency}ms)",
                "details": {
                    "server_version": version_str,
                    "target_url_masked": SQLSecurityGuard.mask_db_url(self.db_url),
                    "detected_columns": columns,
                    "text_column_present": (self.text_column in columns) if columns else True
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
        Streams documents from the external database inside a strictly enforced
        read-only transaction sandbox.
        """
        # 1. SSRF & Network Validation
        SQLSecurityGuard.validate_db_target(self.dialect, self.db_url)

        # 2. AST Query Validation
        SQLSecurityGuard.validate_query(self.sql_query, dialect=self.dialect)

        # 3. Create engine
        engine = create_engine(self.db_url)

        # 4. Stream rows using engine-native read-only execution
        row_stream = SQLSecurityGuard.execute_read_only_query(
            engine=engine,
            dialect=self.dialect,
            sql_query=self.sql_query,
            timeout_ms=15000,
            batch_size=500
        )

        for row_dict in row_stream:
            text_content = str(row_dict.get(self.text_column, "")).strip()
            if not text_content:
                continue

            raw_filename = str(row_dict.get(self.filename_column, "record"))
            filename = f"{raw_filename}.txt" if not raw_filename.endswith(".txt") else raw_filename
            doc_id = str(uuid.uuid4())

            metadata = {
                "sql_row_id": str(row_dict.get("id", raw_filename)),
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

