# app/routes/indexes.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.dependencies import get_db, get_current_user, get_orchestrator, require_role
from modules.auth.domain.tokens import TokenData
from modules.governance.domain.models import DocumentChunk, EnterpriseDocument
from modules.governance.services.audit_logger import AuditLogger
from modules.rag_core.orchestrator.unified_orchestrator import UnifiedRAGOrchestrator

router = APIRouter(prefix="/enterprise/indexes", tags=["Vector Storage & Indexing Management"])

@router.get("/stats")
def get_vector_index_stats(
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db),
    orchestrator: UnifiedRAGOrchestrator = Depends(get_orchestrator)
):
    """
    Returns real-time telemetry on vector storage health, points count,
    indexed vectors, segment stats, and relational PostgreSQL chunks.
    """
    # 1. Fetch Qdrant stats
    qdrant_stats = orchestrator.vector_store.get_collection_stats()

    # 2. Fetch PostgreSQL relational chunk stats
    try:
        total_chunks = db.query(DocumentChunk).filter(DocumentChunk.org_id == current_user.org_id).count()
        total_docs = db.query(EnterpriseDocument).filter(EnterpriseDocument.org_id == current_user.org_id).count()
    except Exception:
        total_chunks = 0
        total_docs = 0

    return {
        "status": "healthy",
        "tenant_id": current_user.org_id,
        "qdrant": qdrant_stats,
        "relational_store": {
            "total_documents_count": total_docs,
            "total_relational_chunks_count": total_chunks,
            "dual_storage_enabled": True
        }
    }

@router.post("/optimize")
def optimize_vector_indexes(
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN"])),
    db: Session = Depends(get_db),
    orchestrator: UnifiedRAGOrchestrator = Depends(get_orchestrator)
):
    """
    Re-verifies collection configuration, triggers payload index verification,
    and returns optimization status.
    """
    try:
        orchestrator.vector_store._ensure_collection_and_indexes()
        qdrant_stats = orchestrator.vector_store.get_collection_stats()

        AuditLogger.log(
            db=db,
            org_id=current_user.org_id,
            user_id=current_user.user_id,
            action="VECTOR_INDEX_OPTIMIZED",
            resource_type="VECTOR_STORE",
            resource_id=orchestrator.vector_store.collection_name,
            details={"qdrant": qdrant_stats}
        )

        return {
            "status": "success",
            "message": f"Collection '{orchestrator.vector_store.collection_name}' indexes verified and optimized.",
            "details": qdrant_stats
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Index optimization failed: {str(e)}"
        )
