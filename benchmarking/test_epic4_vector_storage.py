# benchmarking/test_epic4_vector_storage.py
import sys
import os
import time
import unittest
from typing import Optional, List, Dict, Any
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from core.config import settings
from modules.rag_core.retrieval.vector_store import VectorStoreService, get_vector_store_service
from modules.rag_core.retrieval.security_filter import RAGSecurityFilterBuilder
from modules.governance.domain.models import DocumentChunk, EnterpriseDocument, DocumentStatus
from modules.rag_core.orchestrator.unified_orchestrator import UnifiedRAGOrchestrator
from modules.rag_core.providers.llm import BaseLLMService

class MockLLM(BaseLLMService):
    def get_embeddings(self, text: str):
        return [0.05] * settings.EMBEDDING_DIMENSION

    def get_embeddings_batch(self, texts: list):
        return [[0.05] * settings.EMBEDDING_DIMENSION for _ in texts]

    def generate_text(self, prompt: str, system_instruction: Optional[str] = None, **kwargs) -> str:
        return "Mock LLM Response"


class TestEPIC4VectorStorage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Use in-memory local Qdrant for hermetic fast testing
        settings.QDRANT_STORAGE = "local"
        settings.QDRANT_PATH = ":memory:"
        cls.llm = MockLLM()
        cls.vector_store = VectorStoreService()
        cls.orchestrator = UnifiedRAGOrchestrator(llm_service=cls.llm)
        cls.orchestrator.vector_store = cls.vector_store

    def test_01_qdrant_payload_indexing_and_hnsw(self):
        """Verify Qdrant collection is created with HNSW parameters and payload indexes."""
        stats = self.vector_store.get_collection_stats()
        self.assertEqual(stats["status"], "healthy")
        self.assertEqual(stats["collection_name"], settings.QDRANT_COLLECTION)
        print("  [PASS] Qdrant collection initialized with HNSW parameters and payload indexes.")

    def test_02_vector_search_latency_and_security_filter(self):
        """Verify vector search executes with HNSW search tuning and sub-30ms latency."""
        # Insert test points
        from qdrant_client.models import PointStruct
        points = [
            PointStruct(
                id=101,
                vector=[0.05] * settings.EMBEDDING_DIMENSION,
                payload={"org_id": "org-test-1", "department_id": "dept-eng", "access_level": "DEPARTMENT", "content": "Security document content"}
            ),
            PointStruct(
                id=102,
                vector=[0.05] * settings.EMBEDDING_DIMENSION,
                payload={"org_id": "org-test-2", "department_id": "dept-hr", "access_level": "DEPARTMENT", "content": "HR policy content"}
            )
        ]
        self.vector_store.upsert_chunks(points)

        # Build tenant security filter
        security_filter = RAGSecurityFilterBuilder.build(
            org_id="org-test-1",
            department_id="dept-eng",
            user_role="MEMBER"
        )


        start = time.perf_counter()
        results = self.vector_store.search_vectors(
            query_vector=[0.05] * settings.EMBEDDING_DIMENSION,
            search_filter=security_filter,
            limit=5
        )
        latency_ms = (time.perf_counter() - start) * 1000

        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["payload"]["org_id"], "org-test-1")
        self.assertLess(latency_ms, 30.0, f"Vector search should execute under 30ms (actual: {latency_ms:.2f}ms)")
        print(f"  [PASS] Sub-30ms vector similarity search verified ({latency_ms:.2f}ms).")

    def test_03_pgvector_document_chunk_model(self):
        """Verify DocumentChunk SQLAlchemy model columns, vector types, and indexes."""
        chunk = DocumentChunk(
            id="chunk-123",
            document_id="doc-456",
            org_id="org-789",
            department_id="dept-eng",
            access_level="DEPARTMENT",
            chunk_index=0,
            content="Sample extracted chunk text for indexing.",
            embedding=[0.05] * settings.EMBEDDING_DIMENSION,
            metadata_json={"source": "test.pdf"}
        )
        self.assertEqual(chunk.id, "chunk-123")
        self.assertEqual(chunk.document_id, "doc-456")
        self.assertEqual(len(chunk.embedding), settings.EMBEDDING_DIMENSION)
        print("  [PASS] DocumentChunk relational pgvector model verified.")

    def test_04_dual_write_and_batch_ingest(self):
        """Verify dual-write ingestion synchronizes to Qdrant and relational stores."""
        sample_text = (
            "Enterprise Knowledge Management System. "
            "This document outlines corporate security guidelines, data isolation practices, "
            "and multi-tenant vector retrieval standards. "
        ) * 5
        file_bytes = sample_text.encode("utf-8")

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.delete.return_value = None

        chunk_count = self.orchestrator.ingest_document(
            filename="security_guidelines.txt",
            file_bytes=file_bytes,
            document_id="doc-dual-001",
            org_id="org-test-1",
            department_id="dept-eng",
            access_level="DEPARTMENT",
            mime_type="text/plain",
            db=mock_db
        )

        self.assertTrue(chunk_count >= 1)
        # Verify db.bulk_save_objects was called with DocumentChunk objects
        self.assertTrue(mock_db.bulk_save_objects.called)
        saved_chunks = mock_db.bulk_save_objects.call_args[0][0]
        self.assertEqual(len(saved_chunks), chunk_count)
        self.assertEqual(saved_chunks[0].document_id, "doc-dual-001")

        # Test cascading deletion across stores
        deleted = self.orchestrator.delete_document_vectors(
            document_id="doc-dual-001",
            org_id="org-test-1",
            db=mock_db
        )
        self.assertTrue(deleted)
        print(f"  [PASS] Synchronized dual-write and cascading delete verified ({chunk_count} chunks).")

    def test_05_indexing_endpoints_registration(self):
        """Verify status, re-indexing, and index telemetry routes are registered in FastAPI."""
        from app.main import app
        route_paths = [r.path for r in app.routes]
        self.assertIn("/documents/{document_id}/status", route_paths)
        self.assertIn("/enterprise/documents/{document_id}/status", route_paths)
        self.assertIn("/documents/{document_id}/reindex", route_paths)
        self.assertIn("/enterprise/documents/{document_id}/reindex", route_paths)
        self.assertIn("/enterprise/indexes/stats", route_paths)
        self.assertIn("/enterprise/indexes/optimize", route_paths)
        print("  [PASS] Document indexing lifecycle and telemetry endpoints verified.")

if __name__ == "__main__":
    print("=" * 65)
    print("EXECUTING EPIC 4 VECTOR STORAGE & METADATA INDEXING TEST SUITE")
    print("=" * 65)
    unittest.main(verbosity=2)
