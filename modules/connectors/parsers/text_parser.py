# modules/connectors/parsers/text_parser.py
from modules.connectors.parsers.base import BaseParser

class TextParser(BaseParser):
    def parse(self, content_bytes: bytes) -> str:
        try:
            return content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return content_bytes.decode("latin-1", errors="ignore")
