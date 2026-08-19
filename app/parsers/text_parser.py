# app/parsers/text_parser.py
from app.parsers.base import BaseParser

class TextParser(BaseParser):
    """
    Parser for plaintext, Markdown (.md), CSV, and JSON text files.
    """
    def parse(self, content_bytes: bytes) -> str:
        return content_bytes.decode("utf-8", errors="ignore")
