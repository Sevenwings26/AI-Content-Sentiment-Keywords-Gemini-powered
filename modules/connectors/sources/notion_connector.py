# modules/connectors/sources/notion_connector.py
import time
import uuid
import logging
from typing import Generator, Dict, Any, Optional
import requests
from modules.connectors.base import BaseConnector, RawDocument

logger = logging.getLogger("notion_connector")

class NotionConnector(BaseConnector):
    """
    Notion REST API Connector for Pages and Databases.
    """
    def __init__(self, connection_config: Dict[str, Any]):
        self.config = connection_config
        self.api_token = connection_config.get("api_token", "")
        self.database_id = connection_config.get("database_id")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    def test_connection(self) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            if not self.api_token:
                return {
                    "success": False,
                    "latency_ms": 0.0,
                    "message": "Notion Integration Token is required.",
                    "details": None
                }
            url = "https://api.notion.com/v1/users/me"
            res = requests.get(url, headers=self._get_headers(), timeout=8)
            latency = round((time.perf_counter() - start) * 1000, 2)
            if res.status_code == 200:
                data = res.json()
                bot_name = data.get("name", "Notion Bot")
                return {
                    "success": True,
                    "latency_ms": latency,
                    "message": f"Notion Handshake Verified ({latency}ms)",
                    "details": {"bot_name": bot_name}
                }
            return {
                "success": False,
                "latency_ms": latency,
                "message": f"Notion API Error ({res.status_code}): {res.text[:120]}",
                "details": None
            }
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "success": False,
                "latency_ms": latency,
                "message": f"Notion Connection Failed: {str(e)}",
                "details": None
            }

    def fetch_documents(self) -> Generator[RawDocument, None, None]:
        url = "https://api.notion.com/v1/search"
        res = requests.post(url, headers=self._get_headers(), json={"filter": {"value": "page", "property": "object"}}, timeout=20)
        if res.status_code != 200:
            logger.error(f"Notion fetch error: {res.text}")
            return

        for page in res.json().get("results", []):
            page_id = page["id"]
            # Fetch page title
            title = "Notion Document"
            props = page.get("properties", {})
            for p_val in props.values():
                if p_val.get("type") == "title" and p_val.get("title"):
                    title = "".join([t.get("plain_text", "") for t in p_val["title"]])
                    break

            # Fetch blocks
            b_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
            b_res = requests.get(b_url, headers=self._get_headers(), timeout=15)
            lines = []
            if b_res.status_code == 200:
                for block in b_res.json().get("results", []):
                    b_type = block.get("type")
                    if b_type and b_type in block:
                        rich_texts = block[b_type].get("rich_text", [])
                        lines.append("".join([t.get("plain_text", "") for t in rich_texts]))

            content = chr(10).join([l for l in lines if l.strip()])
            if not content:
                continue

            doc_id = str(uuid.uuid4())
            yield RawDocument(
                doc_id=doc_id,
                source_type="NOTION",
                filename=f"{title}.txt",
                content_bytes=content.encode("utf-8"),
                mime_type="text/plain",
                metadata={"notion_page_id": page_id, "url": page.get("url", "")}
            )
