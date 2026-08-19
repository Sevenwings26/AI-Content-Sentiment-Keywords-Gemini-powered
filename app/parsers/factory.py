# app/parsers/factory.py
import os
from app.parsers.base import BaseParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.docx_parser import DocxParser
from app.parsers.text_parser import TextParser

class ParserFactory:
    """
    Factory pattern selecting the appropriate BaseParser implementation
    based on filename extension or MIME type.
    """
    _parsers = {
        ".pdf": PDFParser(),
        ".docx": DocxParser(),
        ".doc": DocxParser(),
        ".txt": TextParser(),
        ".md": TextParser(),
        ".csv": TextParser(),
        ".json": TextParser(),
    }

    @classmethod
    def get_parser(cls, filename: str, mime_type: str = None) -> BaseParser:
        ext = os.path.splitext(filename)[1].lower()
        parser = cls._parsers.get(ext)
        if not parser:
            return TextParser()
        return parser
