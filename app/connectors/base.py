# app/connectors/base.py
from dataclasses import dataclass, field
from typing import Dict, Any, Generator, Optional
from abc import ABC, abstractmethod

@dataclass
class RawDocument:
    """
    Standardized, JSON-serializable domain object representing a raw document
    ingested from any data connector (Local Files, S3, SQL DBs).
    Designed to plug seamlessly into async task queues (Celery/ARQ).
    """
    doc_id: str
    source_type: str  # e.g., "file", "relational_db", "s3"
    filename: str
    content_bytes: bytes
    mime_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_type": self.source_type,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "metadata": self.metadata
        }

class BaseConnector(ABC):
    """
    Abstract Base Class for all data ingestion connectors.
    """
    @abstractmethod
    def fetch_documents(self) -> Generator[RawDocument, None, None]:
        """Yields standardized RawDocument instances."""
        pass
