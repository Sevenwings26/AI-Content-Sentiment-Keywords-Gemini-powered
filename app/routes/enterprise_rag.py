# app/routes/enterprise_rag.py
import hashlib
import base64
from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.enterprise_models import (
    Organization, Department, User, EnterpriseDocument,
    EnterpriseChatSession, EnterpriseChatMessage, AuditLog, IngestionJob,
    AssistantPersona, PromptTemplate,
    UserRole, AccessLevel, DocumentStatus, IngestionJobStatus
)
from app.core.security import (
    TokenData, get_current_user, require_role,
    create_access_token, hash_password, verify_password
)
# pyrefly: ignore [missing-import]
from app.core.audit import AuditLogger
from app.services.llm import LLMFactory
from app.services.rag import RAGService

router = APIRouter(prefix="/enterprise", tags=["Enterprise Multi-Tenant RAG"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# DB Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# RAG Service Loader
def get_rag_service():
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

class UserCreatePayload(BaseModel):
    email: str
    full_name: str
    password: str
    role: UserRole = UserRole.MEMBER
    department_id: Optional[str] = None

class EnterpriseQueryPayload(BaseModel):
    query: str
    session_id: Optional[str] = None
    persona_id: Optional[str] = None
    template_id: Optional[str] = None
    top_k: int = 3
    score_threshold: float = 0.30

class IngestionJobCreatePayload(BaseModel):
    name: str
    source_type: str
    access_level: AccessLevel = AccessLevel.DEPARTMENT
    target_department_id: Optional[str] = None
    connection_config: Dict[str, Any]
    cron_schedule: Optional[str] = None

class PersonaCreatePayload(BaseModel):
    name: str
    description: Optional[str] = None
    system_instruction_template: str
    temperature: int = 2
    target_department_id: Optional[str] = None
    is_default: bool = False

class PromptTemplateCreatePayload(BaseModel):
    title: str
    user_prompt_template: str
    category: str = "QNA"
    persona_id: Optional[str] = None
    target_department_id: Optional[str] = None


# --- UI View Templates ---

@router.get("/login", response_class=HTMLResponse)
def render_login_page(request: Request):
    """Renders the Enterprise Sign In & Authentication portal."""
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/register", response_class=HTMLResponse)
def render_register_page(request: Request):
    """Renders the Tenant Onboarding portal with register tab active."""
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/dashboard", response_class=HTMLResponse)
def render_admin_dashboard(request: Request):
    """Renders the Enterprise Admin Dashboard & SIEM Visualizer HTML view."""
    return templates.TemplateResponse("enterprise_dashboard.html", {"request": request})

@router.get("/metrics")
def get_tenant_metrics(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns real-time tenant metric summary for dashboard overview."""
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    total_users = db.query(User).filter(User.org_id == current_user.org_id).count()
    total_depts = db.query(Department).filter(Department.org_id == current_user.org_id).count()
    total_docs = db.query(EnterpriseDocument).filter(EnterpriseDocument.org_id == current_user.org_id).count()
    total_jobs = db.query(IngestionJob).filter(IngestionJob.org_id == current_user.org_id).count()
    total_audits = db.query(AuditLog).filter(AuditLog.org_id == current_user.org_id).count()

    return {
        "org_name": org.name if org else "Enterprise Tenant",
        "org_slug": org.slug if org else "",
        "total_users": total_users,
        "total_departments": total_depts,
        "total_documents": total_docs,
        "total_jobs": total_jobs,
        "total_audits": total_audits
    }


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


# --- User & Department Governance ---

@router.get("/users")
def list_tenant_users(
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN", "AUDITOR"])),
    db: Session = Depends(get_db)
):
    """Lists all user accounts in the tenant."""
    users = db.query(User).filter(User.org_id == current_user.org_id).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role.value if hasattr(u.role, "value") else str(u.role),
            "department_id": u.department_id,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat()
        }
        for u in users
    ]

@router.post("/users")
def create_tenant_user(
    payload: UserCreatePayload,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    """Provisions a new user account within the tenant."""
    existing = db.query(User).filter(User.org_id == current_user.org_id, User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="User email already exists in tenant")

    dept_id = payload.department_id or current_user.department_id
    user = User(
        org_id=current_user.org_id,
        department_id=dept_id,
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="USER_PROVISIONED",
        resource_type="USER",
        resource_id=user.id,
        details={"email": user.email, "role": user.role.value if hasattr(user.role, "value") else str(user.role)}
    )

    return {"status": "success", "user": {"id": user.id, "email": user.email, "role": user.role.value if hasattr(user.role, "value") else str(user.role)}}

@router.get("/departments")
def list_departments(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists all functional departments within the tenant."""
    depts = db.query(Department).filter(Department.org_id == current_user.org_id).order_by(Department.code.asc()).all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "code": d.code,
            "created_at": d.created_at.isoformat()
        }
        for d in depts
    ]

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


# --- Persona & Prompt Governance ---

@router.post("/personas")
def create_persona(
    payload: PersonaCreatePayload,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    """Creates an Admin-managed Assistant Persona with dynamic template variables."""
    dept_id = payload.target_department_id if (
        payload.target_department_id and current_user.role == "SUPER_ADMIN"
    ) else current_user.department_id

    persona = AssistantPersona(
        org_id=current_user.org_id,
        department_id=dept_id,
        created_by_id=current_user.user_id,
        name=payload.name,
        description=payload.description,
        system_instruction_template=payload.system_instruction_template,
        temperature=payload.temperature,
        is_default=payload.is_default
    )
    db.add(persona)
    db.commit()
    db.refresh(persona)

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="PERSONA_CREATED",
        resource_type="PERSONA",
        resource_id=persona.id,
        details={"name": persona.name, "department_id": dept_id}
    )

    return {"status": "success", "persona": {"id": persona.id, "name": persona.name, "is_default": persona.is_default}}

@router.get("/personas")
def list_personas(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists all Assistant Personas available to the current user's organization/department."""
    query = db.query(AssistantPersona).filter(
        AssistantPersona.org_id == current_user.org_id,
        AssistantPersona.is_active == True
    )
    if current_user.role != "SUPER_ADMIN":
        query = query.filter(
            (AssistantPersona.department_id == None) |
            (AssistantPersona.department_id == current_user.department_id)
        )
    personas = query.order_by(AssistantPersona.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "department_id": p.department_id,
            "is_default": p.is_default,
            "system_template": p.system_instruction_template
        }
        for p in personas
    ]

@router.post("/prompt-templates")
def create_prompt_template(
    payload: PromptTemplateCreatePayload,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    """Creates an Admin-managed structured Prompt Template."""
    dept_id = payload.target_department_id if (
        payload.target_department_id and current_user.role == "SUPER_ADMIN"
    ) else current_user.department_id

    p_template = PromptTemplate(
        org_id=current_user.org_id,
        department_id=dept_id,
        persona_id=payload.persona_id,
        title=payload.title,
        user_prompt_template=payload.user_prompt_template,
        category=payload.category
    )
    db.add(p_template)
    db.commit()
    db.refresh(p_template)

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="PROMPT_TEMPLATE_CREATED",
        resource_type="PROMPT_TEMPLATE",
        resource_id=p_template.id,
        details={"title": p_template.title, "category": p_template.category}
    )

    return {"status": "success", "template": {"id": p_template.id, "title": p_template.title, "category": p_template.category}}

@router.get("/prompt-templates")
def list_prompt_templates(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists all Prompt Templates available to the current user's organization/department."""
    query = db.query(PromptTemplate).filter(
        PromptTemplate.org_id == current_user.org_id,
        PromptTemplate.is_active == True
    )
    if current_user.role != "SUPER_ADMIN":
        query = query.filter(
            (PromptTemplate.department_id == None) |
            (PromptTemplate.department_id == current_user.department_id)
        )
    templates = query.order_by(PromptTemplate.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "category": t.category,
            "persona_id": t.persona_id,
            "department_id": t.department_id,
            "user_prompt_template": t.user_prompt_template
        }
        for t in templates
    ]


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
        # pyrefly: ignore [missing-import]
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
            "access_level": d.access_level.value if hasattr(d.access_level, "value") else str(d.access_level),
            "status": d.status.value if hasattr(d.status, "value") else str(d.status),
            "size_bytes": d.file_size_bytes,
            "created_at": d.created_at.isoformat()
        }
        for d in docs
    ]


# --- Admin-Governed Data Source Ingestion Jobs ---

@router.get("/jobs")
def list_ingestion_jobs(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists all Admin-governed data source sync jobs in the tenant."""
    jobs = db.query(IngestionJob).filter(IngestionJob.org_id == current_user.org_id).order_by(IngestionJob.created_at.desc()).all()
    return [
        {
            "id": j.id,
            "name": j.name,
            "source_type": j.source_type,
            "access_level": j.access_level.value if hasattr(j.access_level, "value") else str(j.access_level),
            "status": j.status.value if hasattr(j.status, "value") else str(j.status),
            "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
            "documents_processed_count": j.documents_processed_count,
            "created_at": j.created_at.isoformat()
        }
        for j in jobs
    ]

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
        # pyrefly: ignore [missing-import]
        from app.tasks.ingestion_tasks import async_execute_ingestion_job_task
        task = async_execute_ingestion_job_task.delay(job_id)
        task_id = task.id
    except Exception as e:
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
    """Executes an enterprise grounded query with Persona & Prompt Template interpolation."""
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
        score_threshold=payload.score_threshold,
        persona_id=payload.persona_id,
        template_id=payload.template_id
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


