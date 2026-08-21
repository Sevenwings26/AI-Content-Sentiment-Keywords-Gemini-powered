# modules/governance/services/audit_logger.py
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from modules.governance.domain.models import AuditLog

logger = logging.getLogger("governance_audit")

class AuditLogger:
    @staticmethod
    def log(
        db: Session,
        org_id: str,
        action: str,
        resource_type: str,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> Optional[AuditLog]:
        try:
            entry = AuditLog(
                org_id=org_id,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry
        except Exception as e:
            logger.error(f"[AUDIT LOGGING FAILURE] Action={action}: {e}")
            if db:
                db.rollback()
            return None
