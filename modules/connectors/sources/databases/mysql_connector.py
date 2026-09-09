# modules/connectors/sources/databases/mysql_connector.py
from typing import Dict, Any
from modules.connectors.sources.databases.base_db_connector import BaseDatabaseConnector

class MySQLConnector(BaseDatabaseConnector):
    """
    Hardened Production Mysql Connector.
    Enforces AST SQL query validation, SSRF target validation, and read-only transactions.
    """
    def __init__(self, connection_config: Dict[str, Any]):
        super().__init__(
            connection_config=connection_config,
            dialect="mysql",
            source_type="MYSQL_DB"
        )

    def get_version_query(self) -> str:
        return "SELECT VERSION()"
