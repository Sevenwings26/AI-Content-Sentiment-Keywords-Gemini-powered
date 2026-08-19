# app/core/audit.py
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.enterprise_models import AuditLog

logger = logging.getLogger("enterprise_audit")

class AuditLogger:
    @staticmethod
    def log(
        db: Session,
        org_id: str,
        user_id: Optional[str],
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> Optional[AuditLog]:
        """
        Records an immutable audit log entry in the PostgreSQL relational database
        and emits a structured log for SIEM / external audit pipelines.
        """
        try:
            audit_entry = AuditLog(
                org_id=org_id,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
                ip_address=ip_address
            )
            db.add(audit_entry)
            db.commit()
            db.refresh(audit_entry)
            
            logger.info(f"[AUDIT] Org: {org_id} | User: {user_id} | Action: {action} | Resource: {resource_type}:{resource_id}")
            return audit_entry
        except Exception as e:
            db.rollback()
            logger.error(f"[AUDIT FAILURE] Failed to write audit log: {e}")
            return None

