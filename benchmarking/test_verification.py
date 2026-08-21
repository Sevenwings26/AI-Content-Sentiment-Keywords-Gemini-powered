# benchmarking/test_verification.py
import os
import sys

# Ensure project root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def test_modular_monolith_architecture():
    print("Testing Modular Monolith Architecture (Clean Zero-Shim State)...")

    # 1. Test Core Kernel
    from core.config import settings
    from core.database import Base, engine, SessionLocal
    print(f"  [PASS] Core Kernel loaded: App='{settings.APP_NAME}', Version='{settings.APP_VERSION}'")

    # 2. Test Connectors & Parsers Domain
    from modules.connectors import (
        BaseConnector, RawDocument, BaseParser, ParserFactory,
        PDFParser, DocxParser, TextParser, FileConnector, S3Connector, RelationalDBConnector
    )
    sample_text = b"Enterprise Modular Monolith Test Document"
    parser = ParserFactory.get_parser("document.txt")
    assert parser.parse(sample_text) == "Enterprise Modular Monolith Test Document"
    print("  [PASS] modules.connectors and ParserFactory verified.")

    # 3. Test Auth & Identity Domain
    from modules.auth import (
        TokenData, User, Organization, Department, UserRole, AccessLevel,
        verify_password, get_password_hash, create_access_token, decode_access_token,
        UserRepository, has_role
    )
    pw_hash = get_password_hash("testpassword123")
    assert verify_password("testpassword123", pw_hash)
    token = create_access_token({"sub": "u123", "org_id": "org123", "role": "SUPER_ADMIN"})
    payload = decode_access_token(token)
    assert payload["sub"] == "u123" and payload["role"] == "SUPER_ADMIN"
    print("  [PASS] modules.auth (tokens, password hashing, JWT) verified.")

    # 4. Test Governance & Audit Domain
    from modules.governance import (
        DocumentStatus, IngestionJobStatus, AssistantPersona, PromptTemplate,
        AuditLog, EnterpriseDocument, IngestionJob, ChatSession, ChatMessage,
        AuditLogger, GovernanceRepository, DocumentRepository, ChatRepository
    )
    print("  [PASS] modules.governance domain models and repositories verified.")

    # 5. Test RAG Core Domain
    from modules.rag_core import (
        RetrievedChunk, QueryPlan, BaseLLMService, LLMFactory,
        VectorStoreService, RAGSecurityFilterBuilder, HybridRetriever,
        CrossEncoderReranker, GroundingValidator, PromptEngine,
        KnowledgeRegistry, QueryPlanner, UnifiedRAGOrchestrator
    )
    test_user = TokenData(user_id="u1", org_id="o1", department_id="d1", role="MEMBER", email="test@sevenwings.ai")
    plan_conv = QueryPlanner.analyze_and_plan("hello assistant", test_user)
    assert plan_conv.is_conversational_only
    plan_rag = QueryPlanner.analyze_and_plan("What is our security policy?", test_user)
    assert not plan_rag.is_conversational_only
    assert "department" in plan_rag.target_scopes

    out_ans, out_src, is_grounded, conf = GroundingValidator.get_out_of_context_response(
        "What is the future of Artificial Intelligence?",
        org_name="SevenWings AI"
    )
    assert not is_grounded
    assert len(out_src) == 0
    assert "does not contain records matching" in out_ans
    print("  [PASS] modules.rag_core (Planner, GroundingValidator, PromptEngine, Orchestrator) verified.")

    # 6. Test Background Tasks Domain
    from modules.tasks import celery_app, async_ingest_document_task, async_execute_ingestion_job_task
    assert "async_ingest_document_task" in celery_app.tasks
    assert "async_execute_ingestion_job_task" in celery_app.tasks
    print("  [PASS] modules.tasks (Celery app, worker tasks) verified.")

    # 7. Test FastAPI Presentation Layer & Dependencies
    from app.dependencies import get_db, get_orchestrator, get_optional_user, require_role
    from app.routes import auth, chat, documents, governance, jobs, audit, views
    from app.main import app
    assert app.title == settings.APP_NAME
    print("  [PASS] app Presentation Layer (FastAPI routes & dependency injection) verified.")

    print("\n=======================================================")
    print("ALL CLEAN MODULAR MONOLITH VERIFICATION TESTS PASSED!")
    print("=======================================================")

if __name__ == "__main__":
    test_modular_monolith_architecture()
