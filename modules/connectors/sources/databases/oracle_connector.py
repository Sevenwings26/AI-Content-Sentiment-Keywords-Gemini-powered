# modules/connectors/sources/databases/oracle_connector.py
from typing import Dict, Any
from modules.connectors.sources.databases.base_db_connector import BaseDatabaseConnector

class OracleDBConnector(BaseDatabaseConnector):
    """
    Hardened Production Oracle Database 19c / 21c Connector.
    Enforces AST SQL query validation, SSRF target validation, and read-only transactions.
    """
    def __init__(self, connection_config: Dict[str, Any]):
        super().__init__(
            connection_config=connection_config,
            dialect="oracle",
            source_type="ORACLE_DB",
            default_query="SELECT id, title, content FROM enterprise_docs"
        )

    def get_version_query(self) -> str:
        return "SELECT banner FROM v$version WHERE ROWNUM = 1"
