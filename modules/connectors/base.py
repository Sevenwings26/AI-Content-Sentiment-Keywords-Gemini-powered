# modules/connectors/base.py
from dataclasses import dataclass, field
from typing import Dict, Any, Generator, Optional
from abc import ABC, abstractmethod

@dataclass
class RawDocument:
    """
    Standardized, JSON-serializable domain object representing a raw document
    ingested from any data connector (Local Files, S3, SQL DBs, Wikis, Cloud Storage).
    """
    doc_id: str
    source_type: str
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
    Every connector must implement:
      1. fetch_documents() -> Streams raw documents for ingestion
      2. test_connection() -> Fast pre-flight healthcheck, credential handshake, and latency metric
    """
    @abstractmethod
    def fetch_documents(self) -> Generator[RawDocument, None, None]:
        """Streams documents and passages from the external source."""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Executes a fast pre-flight connectivity, authentication, and permission check.
        Returns: {"success": bool, "latency_ms": float, "message": str, "details": Optional[Dict]}
        """
        pass
