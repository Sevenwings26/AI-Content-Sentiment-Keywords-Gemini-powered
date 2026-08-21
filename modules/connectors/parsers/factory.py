# modules/connectors/parsers/factory.py
import os
from modules.connectors.parsers.base import BaseParser
from modules.connectors.parsers.pdf_parser import PDFParser
from modules.connectors.parsers.docx_parser import DocxParser
from modules.connectors.parsers.text_parser import TextParser

class ParserFactory:
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
