# app/routes/governance.py
from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, require_role
from modules.auth.domain.tokens import TokenData
from modules.governance.repositories.governance_repository import GovernanceRepository
from modules.governance.services.audit_logger import AuditLogger
from app.schemas.governance import (
    PersonaCreatePayload, PersonaResponse,
    PromptTemplateCreatePayload, PromptTemplateResponse,
    AuditLogResponse
)

router = APIRouter(prefix="/enterprise/governance", tags=["Enterprise Governance & Guardrails"])

@router.get("/personas", response_model=List[PersonaResponse])
def list_personas(current_user: TokenData = Depends(get_current_user), db: Session = Depends(get_db)):
    personas = GovernanceRepository.list_personas(db, current_user.org_id)
    return [
        PersonaResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            system_template=p.system_instruction_template,
            department_id=None,
            is_default=False
        )
        for p in personas
    ]

@router.post("/personas", response_model=PersonaResponse)
def create_persona(
    payload: PersonaCreatePayload,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    persona = GovernanceRepository.create_persona(
        db=db,
        org_id=current_user.org_id,
        name=payload.name,
        system_instruction_template=payload.system_instruction_template,
        description=payload.description,
        temperature=payload.temperature
    )

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="PERSONA_CREATED",
        resource_type="PERSONA",
        resource_id=persona.id,
        details={"name": persona.name}
    )

    return PersonaResponse(
        id=persona.id,
        name=persona.name,
        description=persona.description,
        system_template=persona.system_instruction_template,
        department_id=None,
        is_default=False
    )

@router.get("/prompts", response_model=List[PromptTemplateResponse])
def list_prompt_templates(current_user: TokenData = Depends(get_current_user), db: Session = Depends(get_db)):
    templates = GovernanceRepository.list_prompt_templates(db, current_user.org_id)
    return [
        PromptTemplateResponse(
            id=t.id,
            title=t.name,
            category="QNA",
            persona_id=None,
            department_id=None,
            user_prompt_template=t.user_prompt_template
        )
        for t in templates
    ]

@router.post("/prompts", response_model=PromptTemplateResponse)
def create_prompt_template(
    payload: PromptTemplateCreatePayload,
    current_user: TokenData = Depends(require_role(["SUPER_ADMIN", "DEPT_ADMIN"])),
    db: Session = Depends(get_db)
):
    template = GovernanceRepository.create_prompt_template(
        db=db,
        org_id=current_user.org_id,
        name=payload.title,
        user_prompt_template=payload.user_prompt_template,
        description=f"Prompt template for category {payload.category}"
    )

    AuditLogger.log(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        action="PROMPT_TEMPLATE_CREATED",
        resource_type="PROMPT_TEMPLATE",
        resource_id=template.id,
        details={"name": template.name}
    )

    return PromptTemplateResponse(
        id=template.id,
        title=template.name,
        category=payload.category,
        persona_id=payload.persona_id,
        department_id=payload.target_department_id,
        user_prompt_template=template.user_prompt_template
    )

@router.get("/audit-logs", response_model=List[AuditLogResponse])
def list_audit_logs(
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
