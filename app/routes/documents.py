# app/routes/documents.py
import hashlib
import base64
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, get_orchestrator, require_role
from modules.auth.domain.tokens import TokenData
from modules.auth.domain.models import AccessLevel
from modules.auth.repositories.user_repository import UserRepository
from modules.governance.domain.models import DocumentStatus
from modules.governance.repositories.document_repository import DocumentRepository
from modules.governance.services.audit_logger import AuditLogger
from modules.rag_core.orchestrator.unified_orchestrator import UnifiedRAGOrchestrator
from app.schemas.document import DocumentUploadResponse, DocumentItemResponse

router = APIRouter(tags=["Document Ingestion & Management"])

@router.post("/documents/upload", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentUploadResponse)
@router.post("/enterprise/documents/upload", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentUploadResponse)
@router.post("/chat/upload", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    access_level: AccessLevel = Form(AccessLevel.DEPARTMENT),
    target_department_id: Optional[str] = Form(None),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    orchestrator: UnifiedRAGOrchestrator = Depends(get_orchestrator)
):
    dept_id = target_department_id if (
        target_department_id and current_user.role == "SUPER_ADMIN"
    ) else current_user.department_id

    if not dept_id and access_level == AccessLevel.DEPARTMENT:
        dept = UserRepository.list_org_departments(db, current_user.org_id)
        dept_id = dept[0].id if dept else ""

    if access_level == AccessLevel.CONFIDENTIAL and current_user.role == "MEMBER":
        raise HTTPException(status_code=403, detail="Members cannot upload Confidential documents")

    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    doc_record = DocumentRepository.create_document(
        db=db,
        org_id=current_user.org_id,
        department_id=dept_id or "",
        uploader_id=current_user.user_id,
        filename=file.filename,
        file_hash=file_hash,
        file_size_bytes=len(content),
        mime_type=file.content_type or "application/octet-stream",
        access_level=access_level
    )

    file_b64 = base64.b64encode(content).decode("utf-8")
    task_id = "sync-executed"

    try:
        from modules.tasks.workers.ingestion_tasks import async_ingest_document_task
        task = async_ingest_document_task.delay(
            document_id=doc_record.id,
            filename=file.filename,
            file_bytes_b64=file_b64,
            org_id=current_user.org_id,
            department_id=dept_id,
            uploader_id=current_user.user_id,
            access_level=access_level.value,
            session_id=session_id,
            mime_type=file.content_type
        )
        task_id = task.id
    except Exception:
        chunk_count = orchestrator.ingest_document(
            filename=file.filename,
            file_bytes=content,
            document_id=doc_record.id,
            org_id=current_user.org_id,
            department_id=dept_id,
            uploader_id=current_user.user_id,
            access_level=access_level.value,
            session_id=session_id,
            mime_type=file.content_type
        )
        DocumentRepository.update_document_status(db, doc_record.id, DocumentStatus.INDEXED, chunk_count=chunk_count)

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="DOCUMENT_UPLOAD_QUEUED",
        resource_type="DOCUMENT",
        resource_id=doc_record.id,
        details={"filename": file.filename, "task_id": task_id}
    )

    return DocumentUploadResponse(
        status="accepted",
        message=f"Document '{file.filename}' queued for background ingestion",
        document_id=doc_record.id,
        session_id=session_id,
        task_id=task_id
    )

@router.get("/documents", response_model=List[DocumentItemResponse])
@router.get("/enterprise/documents", response_model=List[DocumentItemResponse])
def list_documents(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    docs = DocumentRepository.list_accessible_documents(
        db=db,
        org_id=current_user.org_id,
        department_id=current_user.department_id,
        user_id=current_user.user_id,
        user_role=current_user.role
    )
    return [
        DocumentItemResponse(
            id=d.id,
            filename=d.filename,
            department_id=d.department_id,
            access_level=d.access_level.value if hasattr(d.access_level, "value") else str(d.access_level),
            status=d.status.value if hasattr(d.status, "value") else str(d.status),
            size_bytes=d.file_size_bytes,
            created_at=d.created_at.isoformat()
        )
        for d in docs
    ]

@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db),
    orchestrator: UnifiedRAGOrchestrator = Depends(get_orchestrator)
):
    doc = DocumentRepository.get_document_by_id(db, document_id, current_user.org_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    orchestrator.delete_document_vectors(document_id, current_user.org_id)
    DocumentRepository.delete_document(db, document_id, current_user.org_id)

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="DOCUMENT_DELETED",
        resource_type="DOCUMENT",
        resource_id=document_id,
        details={"filename": doc.filename}
    )

    return {"status": "success", "message": f"Document '{doc.filename}' purged successfully"}
