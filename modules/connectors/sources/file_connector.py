# modules/connectors/sources/file_connector.py
import uuid
from typing import Generator
from modules.connectors.base import BaseConnector, RawDocument

class FileConnector(BaseConnector):
    def __init__(self, filename: str, content_bytes: bytes, mime_type: str = None):
        self.filename = filename
        self.content_bytes = content_bytes
        self.mime_type = mime_type

    def test_connection(self) -> dict:
        return {
            "success": True,
            "latency_ms": 0.1,
            "message": f"File stream verified: {self.filename} ({len(self.content_bytes or b'')} bytes)",
            "details": {"filename": self.filename}
        }

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


