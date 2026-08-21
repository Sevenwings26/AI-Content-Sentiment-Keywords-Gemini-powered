# modules/connectors/parsers/pdf_parser.py
import io
from modules.connectors.parsers.base import BaseParser

class PDFParser(BaseParser):
    def parse(self, content_bytes: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content_bytes))
            text = ""
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            return text.strip()
        except Exception:
            return content_bytes.decode("utf-8", errors="ignore")
