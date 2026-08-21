# modules/tasks/workers/ingestion_tasks.py
import logging
import base64
from datetime import datetime
from modules.tasks.celery_app import celery_app
from core.database import SessionLocal
from modules.governance.domain.models import (
    EnterpriseDocument, DocumentStatus, IngestionJob, IngestionJobStatus
)
from modules.governance.repositories.document_repository import DocumentRepository
from modules.rag_core.providers.llm import LLMFactory
from modules.rag_core.orchestrator.unified_orchestrator import UnifiedRAGOrchestrator

logger = logging.getLogger("ingestion_worker")

def get_services():
    db = SessionLocal()
    llm_service = LLMFactory.get_provider()
    orchestrator = UnifiedRAGOrchestrator(llm_service=llm_service)
    return db, orchestrator

@celery_app.task(name="async_ingest_document_task")
def async_ingest_document_task(
    document_id: str,
    filename: str,
    file_bytes_b64: str,
    org_id: str,
    department_id: str,
    uploader_id: str,
    access_level: str,
    session_id: str = None,
    mime_type: str = None
):
    """Asynchronously processes, chunks, embeds, and indexes a single uploaded document."""
    db, orchestrator = get_services()
    try:
        DocumentRepository.update_document_status(db, document_id, DocumentStatus.PROCESSING)

        file_bytes = base64.b64decode(file_bytes_b64.encode("utf-8"))
        chunk_count = orchestrator.ingest_document(
            filename=filename,
            file_bytes=file_bytes,
            document_id=document_id,
            org_id=org_id,
            department_id=department_id,
            uploader_id=uploader_id,
            access_level=access_level,
            session_id=session_id,
            mime_type=mime_type
        )

        DocumentRepository.update_document_status(
            db, document_id, DocumentStatus.INDEXED, chunk_count=chunk_count
        )
        logger.info(f"[ASYNC WORKER] Successfully indexed doc {document_id} ({chunk_count} chunks)")
        return {"status": "success", "document_id": document_id, "chunks": chunk_count}
    except Exception as e:
        logger.error(f"[ASYNC WORKER FAILURE] Document {document_id} failed: {e}")
        DocumentRepository.update_document_status(
            db, document_id, DocumentStatus.FAILED, error_message=str(e)
        )
        return {"status": "failed", "document_id": document_id, "error": str(e)}
    finally:
        db.close()

@celery_app.task(name="async_execute_ingestion_job_task")
def async_execute_ingestion_job_task(job_id: str):
    """Asynchronously executes an admin-configured data source ingestion job (S3, SQL DB, etc.)."""
    db, orchestrator = get_services()
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        db.close()
        return {"status": "error", "message": f"Job {job_id} not found"}

    try:
        job.status = IngestionJobStatus.RUNNING
        db.commit()

        connector = None
        if job.source_type == "s3":
            from modules.connectors.sources.s3_connector import S3Connector
            connector = S3Connector(job.connection_config)
        elif job.source_type == "relational_db":
            from modules.connectors.sources.db_connector import RelationalDBConnector
            connector = RelationalDBConnector(job.connection_config)
        else:
            raise ValueError(f"Unsupported connector source_type: {job.source_type}")

        processed_count = 0
        for raw_doc in connector.fetch_documents():
            orchestrator.ingest_document(
                filename=raw_doc.filename,
                file_bytes=raw_doc.content_bytes,
                document_id=raw_doc.doc_id,
                org_id=job.org_id,
                department_id=job.department_id,
                uploader_id=job.created_by_id or "system_admin",
                access_level=job.access_level.value if hasattr(job.access_level, "value") else str(job.access_level),
                mime_type=raw_doc.mime_type
            )
            processed_count += 1

        job.status = IngestionJobStatus.COMPLETED
        job.documents_processed_count += processed_count
        job.last_run_at = datetime.utcnow()
        db.commit()

        logger.info(f"[ASYNC WORKER JOB] Completed job {job_id} - {processed_count} docs processed")
        return {"status": "success", "job_id": job_id, "processed_count": processed_count}
    except Exception as e:
        logger.error(f"[ASYNC WORKER JOB FAILURE] Job {job_id} failed: {e}")
        job.status = IngestionJobStatus.FAILED
        job.error_message = str(e)
        db.commit()
        return {"status": "failed", "job_id": job_id, "error": str(e)}
    finally:
        db.close()
