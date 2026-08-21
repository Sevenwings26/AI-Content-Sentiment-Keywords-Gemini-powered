# modules/connectors/sources/db_connector.py
import uuid
from typing import Generator, Dict, Any
from sqlalchemy import create_engine, text
from modules.connectors.base import BaseConnector, RawDocument

class RelationalDBConnector(BaseConnector):
    def __init__(self, connection_config: Dict[str, Any]):
        self.db_url = connection_config.get("db_url")
        self.sql_query = connection_config.get("sql_query")
        self.text_column = connection_config.get("text_column", "content")
        self.filename_column = connection_config.get("filename_column", "id")
        self.engine = create_engine(self.db_url)

    def fetch_documents(self) -> Generator[RawDocument, None, None]:
        with self.engine.connect() as conn:
            result = conn.execute(text(self.sql_query))
            for row in result.mappings():
                row_dict = dict(row)
                text_content = str(row_dict.get(self.text_column, ""))
                filename = str(row_dict.get(self.filename_column, "record")) + ".txt"
                if not text_content.strip():
                    continue
                doc_id = str(uuid.uuid4())
                yield RawDocument(
                    doc_id=doc_id,
                    source_type="relational_db",
                    filename=filename,
                    content_bytes=text_content.encode("utf-8"),
                    mime_type="text/plain",
                    metadata={"sql_row_id": str(row_dict.get("id", ""))}
                )
