# modules/connectors/sources/confluence_connector.py
import re
import time
import uuid
import logging
from typing import Generator, Dict, Any, Optional
import requests
from requests.auth import HTTPBasicAuth
from modules.connectors.base import BaseConnector, RawDocument

logger = logging.getLogger("confluence_connector")

class ConfluenceConnector(BaseConnector):
    """
    Atlassian Confluence Cloud & Server Connector.
    """
    def __init__(self, connection_config: Dict[str, Any]):
        self.config = connection_config
        self.base_url = connection_config.get("base_url", "").rstrip("/")
        self.space_key = connection_config.get("space_key", "")
        self.user_email = connection_config.get("user_email", "")
        self.api_token = connection_config.get("api_token", "")

    def _get_auth(self):
        return HTTPBasicAuth(self.user_email, self.api_token)

    def test_connection(self) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            if not self.base_url or not self.api_token:
                return {
                    "success": False,
                    "latency_ms": 0.0,
                    "message": "Base URL and API Token are required.",
                    "details": None
                }
            url = f"{self.base_url}/rest/api/space/{self.space_key}" if self.space_key else f"{self.base_url}/rest/api/space"
            res = requests.get(url, auth=self._get_auth(), timeout=8)
            latency = round((time.perf_counter() - start) * 1000, 2)
            if res.status_code == 200:
                data = res.json()
                space_name = data.get("name", self.space_key)
                return {
                    "success": True,
                    "latency_ms": latency,
                    "message": f"Confluence Handshake Verified ({latency}ms)",
                    "details": {"space": space_name, "url": self.base_url}
                }
            return {
                "success": False,
                "latency_ms": latency,
                "message": f"Confluence API returned HTTP {res.status_code}: {res.text[:120]}",
                "details": None
            }
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "success": False,
                "latency_ms": latency,
                "message": f"Confluence Connection Failed: {str(e)}",
                "details": None
            }

    def fetch_documents(self) -> Generator[RawDocument, None, None]:
        url = f"{self.base_url}/rest/api/content?spaceKey={self.space_key}&expand=body.storage"
        res = requests.get(url, auth=self._get_auth(), timeout=20)
        if res.status_code != 200:
            logger.error(f"Confluence content fetch error: {res.text}")
            return

        for page in res.json().get("results", []):
            title = page.get("title", "Confluence Page")
            html_content = page.get("body", {}).get("storage", {}).get("value", "")
            # Clean basic HTML tags
            clean_text = re.sub(r"<[^>]+>", " ", html_content).strip()
            if not clean_text:
                continue
            doc_id = str(uuid.uuid4())
            filename = f"{title}.txt"
            yield RawDocument(
                doc_id=doc_id,
                source_type="CONFLUENCE",
                filename=filename,
                content_bytes=clean_text.encode("utf-8"),
                mime_type="text/plain",
                metadata={"confluence_page_id": page.get("id"), "confluence_url": f"{self.base_url}{page.get('_links', {}).get('webui', '')}"}
            )
