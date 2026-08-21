# app/routes/jobs.py
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, require_role
from modules.auth.domain.tokens import TokenData
from modules.governance.repositories.document_repository import DocumentRepository
from modules.governance.services.audit_logger import AuditLogger
from app.schemas.document import IngestionJobCreatePayload, IngestionJobResponse

router = APIRouter(prefix="/enterprise/jobs", tags=["Ingestion Jobs & Sync Rules"])

@router.get("", response_model=List[IngestionJobResponse])
def list_jobs(current_user: TokenData = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = DocumentRepository.list_ingestion_jobs(db, current_user.org_id)
    return [
        IngestionJobResponse(
            id=j.id,
            name=j.name,
            source_type=j.source_type,
            access_level=j.access_level.value if hasattr(j.access_level, "value") else str(j.access_level),
            status=j.status.value if hasattr(j.status, "value") else str(j.status),
            last_run_at=j.last_run_at.isoformat() if j.last_run_at else None,
            documents_processed_count=j.documents_processed_count,
            created_at=j.created_at.isoformat()
        )
        for j in jobs
    ]

@router.post("/create")
def create_job(
    payload: IngestionJobCreatePayload,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    dept_id = payload.target_department_id if (
        payload.target_department_id and current_user.role == "SUPER_ADMIN"
    ) else current_user.department_id

    if not dept_id:
        raise HTTPException(status_code=400, detail="Department ID is required")

    job = DocumentRepository.create_ingestion_job(
        db=db,
        org_id=current_user.org_id,
        department_id=dept_id,
        created_by_id=current_user.user_id,
        name=payload.name,
        source_type=payload.source_type,
        access_level=payload.access_level,
        connection_config=payload.connection_config,
        cron_schedule=payload.cron_schedule
    )

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="INGESTION_JOB_CREATED",
        resource_type="INGESTION_JOB",
        resource_id=job.id,
        details={"name": job.name, "source_type": job.source_type}
    )

    return {"status": "success", "job_id": job.id, "name": job.name}

@router.post("/{job_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_job(
    job_id: str,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    job = DocumentRepository.get_ingestion_job(db, job_id, current_user.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    task_id = "sync-executed"
    try:
        from modules.tasks.workers.ingestion_tasks import async_execute_ingestion_job_task
        task = async_execute_ingestion_job_task.delay(job_id)
        task_id = task.id
    except Exception:
        from modules.tasks.workers.ingestion_tasks import async_execute_ingestion_job_task
        async_execute_ingestion_job_task(job_id)

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
