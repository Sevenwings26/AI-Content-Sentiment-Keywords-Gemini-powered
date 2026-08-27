# modules/connectors/parsers/tabular_parser.py
import io
import csv
import logging
from typing import List, Optional
from modules.connectors.parsers.base import BaseParser

logger = logging.getLogger("tabular_parser")

class TabularParser(BaseParser):
    """
    High-performance tabular parser for .xlsx, .xls, .csv, and .tsv files.
    Serializes tabular rows into self-contained semantic Key-Value records
    and structured Markdown tables preserving header context across all chunks.
    """

    def parse(self, content_bytes: bytes) -> str:
        # 1. Try Excel (.xlsx) parsing first via openpyxl
        try:
            return self._parse_excel(content_bytes)
        except Exception as e_excel:
            logger.debug(f"Not a valid Excel workbook ({e_excel}), falling back to delimited text (CSV/TSV)...")

        # 2. Fallback to Delimited Text (CSV / TSV)
        try:
            return self._parse_delimited(content_bytes)
        except Exception as e_csv:
            logger.error(f"Tabular parsing failed for both Excel and CSV: {e_csv}")
            try:
                return content_bytes.decode("utf-8", errors="ignore")
            except Exception:
                return content_bytes.decode("latin-1", errors="ignore")

    def _parse_excel(self, content_bytes: bytes) -> str:
        import openpyxl

        wb = openpyxl.load_workbook(
            io.BytesIO(content_bytes),
            data_only=True,
            read_only=True
        )

        output_sections: List[str] = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            raw_rows = list(ws.iter_rows(values_only=True))

            # Filter out completely empty rows
            valid_rows = [
                [str(cell).strip() if cell is not None else "" for cell in row]
                for row in raw_rows
                if row and any(c is not None and str(c).strip() != "" for c in row)
            ]

            if not valid_rows:
                continue

            # First non-empty row is treated as the Header
            raw_headers = valid_rows[0]
            headers = [
                h if h else f"Column_{idx + 1}"
                for idx, h in enumerate(raw_headers)
            ]

            sheet_lines: List[str] = []
            sheet_lines.append(f"### [Spreadsheet Table - Sheet: {sheet_name}]")
            sheet_lines.append(f"Columns: {' | '.join(headers)}\n")

            # Serialize data rows into semantic Key-Value units
            data_rows = valid_rows[1:]
            if not data_rows:
                # Single header row only
                sheet_lines.append(f"Headers only: {' | '.join(headers)}")
            else:
                for r_idx, row in enumerate(data_rows, 1):
                    row_pairs = []
                    for c_idx, val in enumerate(row):
                        header_name = headers[c_idx] if c_idx < len(headers) else f"Column_{c_idx + 1}"
                        if val:
                            row_pairs.append(f"{header_name}: {val}")
                        else:
                            row_pairs.append(f"{header_name}: N/A")

                    serialized_row = f"[Sheet: {sheet_name} | Row {r_idx}] " + " | ".join(row_pairs)
                    sheet_lines.append(serialized_row)

            output_sections.append("\n".join(sheet_lines))

        wb.close()
        return "\n\n".join(output_sections) if output_sections else "Empty spreadsheet."

    def _parse_delimited(self, content_bytes: bytes) -> str:
        # Attempt text decoding
        text_content = ""
        for encoding in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                text_content = content_bytes.decode(encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if not text_content:
            text_content = content_bytes.decode("latin-1", errors="ignore")

        # Detect delimiter (comma, tab, semicolon, pipe)
        sample = text_content[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"])
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ","

        reader = csv.reader(io.StringIO(text_content), delimiter=delimiter)
        raw_rows = [
            [cell.strip() for cell in row]
            for row in reader
            if row and any(cell.strip() != "" for cell in row)
        ]

        if not raw_rows:
            return text_content

        raw_headers = raw_rows[0]
        headers = [
            h if h else f"Column_{idx + 1}"
            for idx, h in enumerate(raw_headers)
        ]

        output_lines: List[str] = []
        output_lines.append(f"### [Tabular Document - Delimited Data]")
        output_lines.append(f"Columns: {' | '.join(headers)}\n")

        for r_idx, row in enumerate(raw_rows[1:], 1):
            row_pairs = []
            for c_idx, val in enumerate(row):
                header_name = headers[c_idx] if c_idx < len(headers) else f"Column_{c_idx + 1}"
                row_pairs.append(f"{header_name}: {val}" if val else f"{header_name}: N/A")

            serialized_row = f"[Row {r_idx}] " + " | ".join(row_pairs)
            output_lines.append(serialized_row)

        return "\n".join(output_lines)
