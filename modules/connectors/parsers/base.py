# modules/connectors/parsers/base.py
from abc import ABC, abstractmethod

class BaseParser(ABC):
    """Abstract Base Class for format-specific document parsers."""
    @abstractmethod
    def parse(self, content_bytes: bytes) -> str:
        pass
