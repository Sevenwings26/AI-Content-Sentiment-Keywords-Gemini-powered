# modules/connectors/sources/sharepoint_connector.py
import time
import uuid
import logging
from typing import Generator, Dict, Any, Optional
import requests
from modules.connectors.base import BaseConnector, RawDocument

logger = logging.getLogger("sharepoint_connector")

class SharePointConnector(BaseConnector):
    """
    Microsoft SharePoint & OneDrive Connector via Microsoft Graph REST API.
    """
    def __init__(self, connection_config: Dict[str, Any]):
        self.config = connection_config
        self.tenant_id = connection_config.get("tenant_id", "")
        self.client_id = connection_config.get("client_id", "")
        self.client_secret = connection_config.get("client_secret", "")
        self.site_url = connection_config.get("site_url", "")
        self.folder_path = connection_config.get("folder_path", "/Shared Documents")

    def _get_access_token(self) -> str:
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        res = requests.post(token_url, data=payload, timeout=10)
        if res.status_code == 200:
            return res.json()["access_token"]
        raise ValueError(f"Microsoft Entra OAuth2 Failed ({res.status_code}): {res.text[:120]}")

    def test_connection(self) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            if not self.tenant_id or not self.client_id:
                return {
                    "success": False,
                    "latency_ms": 0.0,
                    "message": "Tenant ID and Client ID are required.",
                    "details": None
                }
            token = self._get_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            # Verify Graph API Ping
            res = requests.get("https://graph.microsoft.com/v1.0/organization", headers=headers, timeout=8)
            latency = round((time.perf_counter() - start) * 1000, 2)
            if res.status_code == 200:
                data = res.json()
                org_name = data.get("value", [{}])[0].get("displayName", "Microsoft 365 Tenant")
                return {
                    "success": True,
                    "latency_ms": latency,
                    "message": f"SharePoint Handshake Verified ({latency}ms)",
                    "details": {
                        "organization": org_name,
                        "site_url": self.site_url
                    }
                }
            return {
                "success": False,
                "latency_ms": latency,
                "message": f"Microsoft Graph API Error: {res.text[:120]}",
                "details": None
            }
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "success": False,
                "latency_ms": latency,
                "message": f"SharePoint Authentication Failed: {str(e)}",
                "details": None
            }

    def fetch_documents(self) -> Generator[RawDocument, None, None]:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        # In a full deployment, traverse drives and folders
        # Standard graph endpoint for files in root drive
        url = "https://graph.microsoft.com/v1.0/me/drive/root/children"
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            for item in res.json().get("value", []):
                if "@microsoft.graph.downloadUrl" in item:
                    f_res = requests.get(item["@microsoft.graph.downloadUrl"], timeout=30)
                    if f_res.status_code == 200:
                        yield RawDocument(
                            doc_id=str(uuid.uuid4()),
                            source_type="SHAREPOINT",
                            filename=item.get("name", "document"),
                            content_bytes=f_res.content,
                            mime_type=item.get("file", {}).get("mimeType", "application/octet-stream"),
                            metadata={"sharepoint_id": item.get("id")}
                        )
