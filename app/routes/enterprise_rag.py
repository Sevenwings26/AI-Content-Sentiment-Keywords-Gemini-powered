# app/routes/enterprise_rag.py
import hashlib
import base64
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import SessionLocal
from app.models.enterprise_models import (
    Organization, Department, User, EnterpriseDocument,
    EnterpriseChatSession, EnterpriseChatMessage, AuditLog, IngestionJob,
    UserRole, AccessLevel, DocumentStatus, IngestionJobStatus
)
from app.core.security import (
    TokenData, get_current_user, require_role,
    create_access_token, hash_password, verify_password
)
from app.core.audit import AuditLogger

router = APIRouter(prefix="/enterprise", tags=["Enterprise Multi-Tenant RAG"])

# DB Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# RAG Service Loader
def get_rag_service():
    from app.services.llm import LLMFactory
    from app.services.rag import RAGService
    llm_service = LLMFactory.get_provider()
    return RAGService(llm_service=llm_service)


# --- Pydantic Request / Response Schemas ---

class TenantRegistrationPayload(BaseModel):
    org_name: str
    org_slug: str
    admin_name: str
    admin_email: str
    admin_password: str
    department_name: str = "Engineering"
    department_code: str = "ENG"

class DepartmentCreatePayload(BaseModel):
    name: str
    code: str

class EnterpriseQueryPayload(BaseModel):
    query: str
    session_id: Optional[str] = None
    top_k: int = 3
    score_threshold: float = 0.30

class IngestionJobCreatePayload(BaseModel):
    name: str
    source_type: str  # 's3', 'relational_db'
    access_level: AccessLevel = AccessLevel.DEPARTMENT
    target_department_id: Optional[str] = None
    connection_config: Dict[str, Any]
    cron_schedule: Optional[str] = None


# --- Authentication & Tenant Provisioning ---

@router.post("/auth/register-tenant")
def register_tenant(payload: TenantRegistrationPayload, db: Session = Depends(get_db)):
    """Provisions a new Organization, default Department, and initial SuperAdmin."""
    if db.query(Organization).filter(Organization.slug == payload.org_slug.lower()).first():
        raise HTTPException(status_code=400, detail="Organization slug already registered")

    org = Organization(name=payload.org_name, slug=payload.org_slug.lower())
    db.add(org)
    db.commit()
    db.refresh(org)

    dept = Department(org_id=org.id, name=payload.department_name, code=payload.department_code.upper())
    db.add(dept)
    db.commit()
    db.refresh(dept)

    admin_user = User(
        org_id=org.id,
        department_id=dept.id,
        email=payload.admin_email.lower(),
        hashed_password=hash_password(payload.admin_password),
        full_name=payload.admin_name,
        role=UserRole.SUPER_ADMIN
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    AuditLogger.log(
        db=db,
        org_id=org.id,
        user_id=admin_user.id,
        action="TENANT_PROVISIONED",
        resource_type="ORGANIZATION",
        resource_id=org.id,
        details={"org_name": org.name, "admin_email": admin_user.email}
    )

    token = create_access_token({
        "sub": admin_user.id,
        "org_id": org.id,
        "dept_id": dept.id,
        "role": admin_user.role.value,
        "email": admin_user.email
    })

    return {
        "status": "success",
        "message": f"Tenant '{org.name}' provisioned successfully",
        "access_token": token,
        "token_type": "bearer",
        "org_id": org.id,
        "user_id": admin_user.id
    }

@router.post("/auth/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 Password flow issuing scoped JWT with Org, Dept, and Role claims."""
    user = db.query(User).filter(User.email == form_data.username.lower()).first()
    if not user or not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated")

    token = create_access_token({
        "sub": user.id,
        "org_id": user.org_id,
        "dept_id": user.department_id,
        "role": user.role.value,
        "email": user.email
    })

    AuditLogger.log(
        db=db,
        org_id=user.org_id,
        user_id=user.id,
        action="USER_LOGIN",
        resource_type="USER",
        resource_id=user.id
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.value,
            "org_id": user.org_id,
            "department_id": user.department_id
        }
    }


# --- Department Governance ---

@router.post("/departments")
def create_department(
    payload: DepartmentCreatePayload,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    """Creates a new department within the current tenant."""
    existing = db.query(Department).filter(
        Department.org_id == current_user.org_id,
        Department.code == payload.code.upper()
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Department code '{payload.code}' already exists")

    dept = Department(org_id=current_user.org_id, name=payload.name, code=payload.code.upper())
    db.add(dept)
    db.commit()
    db.refresh(dept)

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="DEPARTMENT_CREATED",
        resource_type="DEPARTMENT",
        resource_id=dept.id,
        details={"name": dept.name, "code": dept.code}
    )

    return {"status": "success", "department": {"id": dept.id, "name": dept.name, "code": dept.code}}


# --- Secure Ingestion Pipeline ---

@router.post("/documents/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_enterprise_document(
    file: UploadFile = File(...),
    access_level: AccessLevel = Form(AccessLevel.DEPARTMENT),
    target_department_id: Optional[str] = Form(None),
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN", "MEMBER"])),
    db: Session = Depends(get_db),
    rag_service = Depends(get_rag_service)
):
    """
    Asynchronously ingests documents into PostgreSQL and Qdrant via Celery task.
    Returns 202 Accepted immediately in < 50ms.
    """
    dept_id = target_department_id if (
        target_department_id and current_user.role == "SUPER_ADMIN"
    ) else current_user.department_id

    if not dept_id:
        raise HTTPException(status_code=400, detail="User is not assigned to a department")

    if access_level == AccessLevel.CONFIDENTIAL and current_user.role == "MEMBER":
        raise HTTPException(status_code=403, detail="Members cannot upload Confidential documents")

    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    doc_record = EnterpriseDocument(
        org_id=current_user.org_id,
        department_id=dept_id,
        uploader_id=current_user.user_id,
        filename=file.filename,
        file_hash=file_hash,
        file_size_bytes=len(content),
        mime_type=file.content_type or "application/octet-stream",
        access_level=access_level,
        status=DocumentStatus.PENDING
    )
    db.add(doc_record)
    db.commit()
    db.refresh(doc_record)

    file_b64 = base64.b64encode(content).decode("utf-8")

    try:
        from app.tasks.ingestion_tasks import async_ingest_document_task
        task = async_ingest_document_task.delay(
            document_id=doc_record.id,
            filename=file.filename,
            file_bytes_b64=file_b64,
            org_id=current_user.org_id,
            department_id=dept_id,
            uploader_id=current_user.user_id,
            access_level=access_level.value,
            mime_type=file.content_type
        )
        task_id = task.id
    except Exception as e:
        # Fallback if Redis broker is offline
        from app.tasks.ingestion_tasks import async_ingest_document_task
        async_ingest_document_task(
            document_id=doc_record.id,
            filename=file.filename,
            file_bytes_b64=file_b64,
            org_id=current_user.org_id,
            department_id=dept_id,
            uploader_id=current_user.user_id,
            access_level=access_level.value,
            mime_type=file.content_type
        )
        task_id = "sync-executed"

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="DOCUMENT_UPLOAD_QUEUED",
        resource_type="DOCUMENT",
        resource_id=doc_record.id,
        details={"filename": file.filename, "task_id": task_id}
    )

    return {
        "status": "accepted",
        "message": f"Document '{file.filename}' queued for background ingestion",
        "document_id": doc_record.id,
        "task_id": task_id
    }

@router.get("/documents")
def list_accessible_documents(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists all documents within the tenant that the current user has clearance to view."""
    query = db.query(EnterpriseDocument).filter(
        EnterpriseDocument.org_id == current_user.org_id
    )
    if current_user.role != "SUPER_ADMIN":
        query = query.filter(
            (EnterpriseDocument.access_level == AccessLevel.PUBLIC) |
            ((EnterpriseDocument.department_id == current_user.department_id) & (EnterpriseDocument.access_level == AccessLevel.DEPARTMENT)) |
            (EnterpriseDocument.uploader_id == current_user.user_id)
        )
    docs = query.order_by(EnterpriseDocument.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "department_id": d.department_id,
            "access_level": d.access_level.value,
            "status": d.status.value if hasattr(d.status, "value") else str(d.status),
            "size_bytes": d.file_size_bytes,
            "created_at": d.created_at.isoformat()
        }
        for d in docs
    ]


# --- Admin-Governed Data Source Ingestion Jobs ---

@router.post("/jobs/create")
def create_ingestion_job(
    payload: IngestionJobCreatePayload,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    """Configures an Admin-governed data source ingestion job (S3 bucket or SQL DB)."""
    dept_id = payload.target_department_id if (
        payload.target_department_id and current_user.role == "SUPER_ADMIN"
    ) else current_user.department_id

    if not dept_id:
        raise HTTPException(status_code=400, detail="Department ID is required")

    job = IngestionJob(
        org_id=current_user.org_id,
        department_id=dept_id,
        created_by_id=current_user.user_id,
        name=payload.name,
        source_type=payload.source_type,
        access_level=payload.access_level,
        connection_config=payload.connection_config,
        cron_schedule=payload.cron_schedule
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="INGESTION_JOB_CREATED",
        resource_type="INGESTION_JOB",
        resource_id=job.id,
        details={"name": job.name, "source_type": job.source_type}
    )

    return {"status": "success", "job_id": job.id, "name": job.name, "source_type": job.source_type}

@router.post("/jobs/{job_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_ingestion_job(
    job_id: str,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    """Triggers an async background execution of a data source ingestion job via Celery."""
    job = db.query(IngestionJob).filter(
        IngestionJob.id == job_id,
        IngestionJob.org_id == current_user.org_id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    try:
        from app.tasks.ingestion_tasks import async_execute_ingestion_job_task
        task = async_execute_ingestion_job_task.delay(job_id)
        task_id = task.id
    except Exception as e:
        from app.tasks.ingestion_tasks import async_execute_ingestion_job_task
        async_execute_ingestion_job_task(job_id)
        task_id = "sync-executed"

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="INGESTION_JOB_TRIGGERED",
        resource_type="INGESTION_JOB",
        resource_id=job.id,
        details={"task_id": task_id}
    )

    return {"status": "accepted", "message": f"Job '{job.name}' queued for processing", "task_id": task_id}


# --- Scoped Query & Interaction Execution ---

@router.post("/chat/query")
def execute_enterprise_query(
    payload: EnterpriseQueryPayload,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    rag_service = Depends(get_rag_service)
):
    """Executes an enterprise grounded query with strict multi-tenant RBAC filtering."""
    session = None
    if payload.session_id:
        session = db.query(EnterpriseChatSession).filter(
            EnterpriseChatSession.id == payload.session_id,
            EnterpriseChatSession.org_id == current_user.org_id
        ).first()
        if not session:
            session = EnterpriseChatSession(
                id=payload.session_id,
                org_id=current_user.org_id,
                department_id=current_user.department_id or "",
                user_id=current_user.user_id,
                title=f"Chat: {payload.query[:30]}"
            )
            db.add(session)
            db.commit()

        user_msg = EnterpriseChatMessage(
            session_id=session.id,
            role="user",
            content=payload.query
        )
        db.add(user_msg)
        db.commit()

    answer, sources = rag_service.query_enterprise(
        query=payload.query,
        user_context=current_user,
        session_id=payload.session_id,
        db=db,
        top_k=payload.top_k,
        score_threshold=payload.score_threshold
    )

    if session:
        assistant_msg = EnterpriseChatMessage(
            session_id=session.id,
            role="assistant",
            content=answer,
            citation_metadata={"sources": sources}
        )
        db.add(assistant_msg)
        db.commit()

    return {
        "status": "success",
        "session_id": payload.session_id,
        "answer": answer,
        "sources": sources
    }


# --- Immutable Audit Review ---

@router.get("/audit/logs")
def view_audit_logs(
    limit: int = 50,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "AUDITOR"])),
    db: Session = Depends(get_db)
):
    """Audit review endpoint strictly restricted to SuperAdmins and Auditors."""
    logs = db.query(AuditLog).filter(
        AuditLog.org_id == current_user.org_id
    ).order_by(AuditLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": log.details,
            "created_at": log.created_at.isoformat()
        }
        for log in logs
    ]
