# modules/connectors/sources/databases/postgres_connector.py
from typing import Dict, Any
from modules.connectors.sources.databases.base_db_connector import BaseDatabaseConnector

class PostgreSQLConnector(BaseDatabaseConnector):
    """
    Hardened Production Postgresql Connector.
    Enforces AST SQL query validation, SSRF target validation, and read-only transactions.
    """
    def __init__(self, connection_config: Dict[str, Any]):
        super().__init__(
            connection_config=connection_config,
            dialect="postgresql",
            source_type="POSTGRES_DB"
        )

    def get_version_query(self) -> str:
        return "SELECT version()"

# Backwards-compatibility alias
RelationalDBConnector = PostgreSQLConnector
