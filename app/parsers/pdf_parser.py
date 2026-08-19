# app/parsers/pdf_parser.py
from io import BytesIO
from pypdf import PdfReader
from app.parsers.base import BaseParser

class PDFParser(BaseParser):
    """
    Parser for PDF documents using pypdf.
    """
    def parse(self, content_bytes: bytes) -> str:
        pdf = PdfReader(BytesIO(content_bytes))
        text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
