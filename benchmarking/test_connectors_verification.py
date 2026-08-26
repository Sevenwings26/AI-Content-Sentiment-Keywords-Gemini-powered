# benchmarking/test_connectors_verification.py
import sys
import os
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from modules.connectors.base import BaseConnector, RawDocument
from modules.connectors.schemas import (
    ConnectorCategory, ConnectorSourceType, ConnectorFieldMeta,
    ConnectorDescriptor, FieldType,
    PostgreSQLConfig, MySQLConfig, OracleConfig, MSSQLConfig,
    S3Config, GoogleDriveConfig, SharePointConfig,
    ConfluenceConfig, NotionConfig,
    ConnectorTestRequest, ConnectorTestResponse
)
from modules.connectors.registry import ConnectorRegistry

class TestEnterpriseConnectors(unittest.TestCase):

    def test_01_schema_descriptors(self):
        """Verify all 9 enterprise connector descriptors load with full metadata."""
        descriptors = ConnectorRegistry.get_descriptor_list()
        self.assertEqual(len(descriptors), 9, f"Expected 9 descriptors, got {len(descriptors)}")

        expected_sources = {
            "POSTGRES_DB": ConnectorCategory.DATABASES,
            "MYSQL_DB": ConnectorCategory.DATABASES,
            "ORACLE_DB": ConnectorCategory.DATABASES,
            "MSSQL_DB": ConnectorCategory.DATABASES,
            "S3_BUCKET": ConnectorCategory.CLOUD_STORAGE,
            "GOOGLE_DRIVE": ConnectorCategory.CLOUD_STORAGE,
            "SHAREPOINT": ConnectorCategory.CLOUD_STORAGE,
            "CONFLUENCE": ConnectorCategory.PRODUCTIVITY,
            "NOTION": ConnectorCategory.PRODUCTIVITY
        }

        for d in descriptors:
            self.assertIn(d.source_type, expected_sources)
            self.assertEqual(d.category, expected_sources[d.source_type])
            self.assertTrue(len(d.fields) >= 2, f"Connector {d.source_type} should have fields")
            self.assertTrue(bool(d.icon), f"Connector {d.source_type} should have an icon")
            # Verify secret flags
            secret_fields = [f.name for f in d.fields if f.is_secret]
            self.assertTrue(len(secret_fields) >= 1, f"Connector {d.source_type} should have at least one secret field")

        print("  [PASS] All 9 connector schema descriptors and metadata verified.")

    def test_02_connector_factory_instantiation(self):
        """Verify ConnectorRegistry instantiates all 9 connector classes."""
        dummy_configs = {
            "POSTGRES_DB": {"host": "localhost", "port": 5432, "database": "test", "username": "postgres", "password": "pwd"},
            "MYSQL_DB": {"host": "localhost", "port": 3306, "database": "test", "username": "root", "password": "pwd"},
            "ORACLE_DB": {"host": "localhost", "port": 1521, "service_name": "ORCL", "username": "sys", "password": "pwd"},
            "MSSQL_DB": {"host": "localhost", "port": 1433, "database": "test", "username": "sa", "password": "pwd"},
            "S3_BUCKET": {"bucket_name": "my-bucket", "region_name": "us-east-1"},
            "GOOGLE_DRIVE": {"service_account_json": "{}", "folder_id": "test_folder"},
            "SHAREPOINT": {"tenant_id": "tenant-1", "client_id": "client-1", "client_secret": "secret", "site_url": "https://company.sharepoint.com"},
            "CONFLUENCE": {"base_url": "https://company.atlassian.net", "space_key": "ENG", "user_email": "a@c.com", "api_token": "tok"},
            "NOTION": {"api_token": "secret_test", "database_id": "db_1"}
        }

        for stype, cfg in dummy_configs.items():
            connector = ConnectorRegistry.get_connector(stype, cfg)
            self.assertIsInstance(connector, BaseConnector, f"Connector {stype} must inherit from BaseConnector")
            self.assertTrue(hasattr(connector, "test_connection"))
            self.assertTrue(hasattr(connector, "fetch_documents"))

        print("  [PASS] ConnectorRegistry dynamically instantiates all 9 BaseConnector classes.")

    def test_03_preflight_test_connection_contract(self):
        """Verify test_connection returns standardized latency and error response on mock credentials."""
        # Test Confluence test_connection
        confluence = ConnectorRegistry.get_connector("CONFLUENCE", {
            "base_url": "https://invalid-subdomain-mock-test.atlassian.net",
            "space_key": "DOCS",
            "user_email": "test@domain.invalid",
            "api_token": "fake_token"
        })
        res = confluence.test_connection()
        self.assertIn("success", res)
        self.assertIn("latency_ms", res)
        self.assertIn("message", res)
        self.assertIsInstance(res["latency_ms"], float)
        self.assertFalse(res["success"])  # Should fail cleanly without unhandled exception

        # Test Notion test_connection
        notion = ConnectorRegistry.get_connector("NOTION", {"api_token": "secret_invalid_mock_token"})
        res_notion = notion.test_connection()
        self.assertIn("success", res_notion)
        self.assertIsInstance(res_notion["latency_ms"], float)
        self.assertFalse(res_notion["success"])

        # Test PostgreSQL test_connection on unreachable mock port
        pg = ConnectorRegistry.get_connector("POSTGRES_DB", {
            "host": "127.0.0.1",
            "port": 59999,
            "database": "mockdb",
            "username": "mockuser",
            "password": "mockpassword"
        })
        res_pg = pg.test_connection()
        self.assertFalse(res_pg["success"])
        self.assertIn("latency_ms", res_pg)
        self.assertIn("Failed", res_pg["message"])

        print("  [PASS] Pre-flight test_connection() contract validated across connectors.")

    def test_04_api_routes_and_schemas(self):
        """Verify FastAPI routes for connector schemas and test-connection."""
        from app.routes.jobs import router
        route_paths = [r.path for r in router.routes]
        self.assertIn("/enterprise/connectors/schemas", route_paths)
        self.assertIn("/enterprise/connectors/test-connection", route_paths)
        self.assertIn("/enterprise/jobs", route_paths)
        self.assertIn("/enterprise/jobs/create", route_paths)
        self.assertIn("/enterprise/jobs/{job_id}/trigger", route_paths)

        print("  [PASS] FastAPI router registered all enterprise connector endpoints.")

if __name__ == "__main__":
    print("=" * 65)
    print("EXECUTING ENTERPRISE KNOWLEDGE CONNECTORS VERIFICATION SUITE")
    print("=" * 65)
    unittest.main(verbosity=2)
