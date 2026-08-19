# app/connectors/file_connector.py
import uuid
from typing import Generator
from app.connectors.base import BaseConnector, RawDocument

class FileConnector(BaseConnector):
    """
    Connector for uploaded file streams or single file payloads.
    """
    def __init__(self, filename: str, content_bytes: bytes, mime_type: str = None):
        self.filename = filename
        self.content_bytes = content_bytes
        self.mime_type = mime_type

    def fetch_documents(self) -> Generator[RawDocument, None, None]:
        doc_id = str(uuid.uuid4())
        yield RawDocument(
            doc_id=doc_id,
            source_type="file",
            filename=self.filename,
            content_bytes=self.content_bytes,
            mime_type=self.mime_type,
            metadata={"filename": self.filename}
        )
