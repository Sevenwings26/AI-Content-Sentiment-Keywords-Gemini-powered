# modules/connectors/sources/databases/mssql_connector.py
from typing import Dict, Any
from modules.connectors.sources.databases.base_db_connector import BaseDatabaseConnector

class MSSQLConnector(BaseDatabaseConnector):
    """
    Hardened Production Microsoft SQL Server & Azure SQL Connector.
    Enforces AST SQL query validation, SSRF target validation, and read-only transactions.
    """
    def __init__(self, connection_config: Dict[str, Any]):
        super().__init__(
            connection_config=connection_config,
            dialect="mssql",
            source_type="MSSQL_DB",
            default_query="SELECT id, title, body FROM KnowledgeArticles"
        )

    def get_version_query(self) -> str:
        return "SELECT @@VERSION"
