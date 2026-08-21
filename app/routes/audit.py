# app/routes/audit.py
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, require_role
from modules.auth.domain.tokens import TokenData
from modules.governance.repositories.governance_repository import GovernanceRepository
from app.schemas.governance import AuditLogResponse

router = APIRouter(prefix="/enterprise/audit", tags=["Compliance & Audit"])

@router.get("/logs", response_model=List[AuditLogResponse])
def get_org_audit_logs(
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "AUDITOR"])),
    db: Session = Depends(get_db)
):
    logs = GovernanceRepository.list_audit_logs(db, current_user.org_id)
    return [
        AuditLogResponse(
            id=l.id,
            user_id=l.user_id,
            action=l.action,
            resource_type=l.resource_type,
            resource_id=l.resource_id,
            details=l.details,
            created_at=l.created_at.isoformat()
        )
        for l in logs
    ]
