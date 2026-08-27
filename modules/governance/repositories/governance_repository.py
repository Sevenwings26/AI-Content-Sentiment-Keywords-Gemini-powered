# modules/governance/repositories/governance_repository.py
from typing import List, Optional
from sqlalchemy.orm import Session
from modules.governance.domain.models import AssistantPersona, PromptTemplate, AuditLog

class GovernanceRepository:
    @staticmethod
    def list_personas(db: Session, org_id: str) -> List[AssistantPersona]:
        return db.query(AssistantPersona).filter(AssistantPersona.org_id == org_id, AssistantPersona.is_active == True).all()

    @staticmethod
    def create_persona(
        db: Session,
        org_id: str,
        name: str,
        system_instruction_template: str,
        description: Optional[str] = None,
        temperature: int = 2
    ) -> AssistantPersona:
        persona = AssistantPersona(
            org_id=org_id,
            name=name,
            description=description,
            system_instruction_template=system_instruction_template,
            temperature=temperature
        )
        db.add(persona)
        db.commit()
        db.refresh(persona)
        return persona

    @staticmethod
    def list_prompt_templates(db: Session, org_id: str) -> List[PromptTemplate]:
        return db.query(PromptTemplate).filter(PromptTemplate.org_id == org_id, PromptTemplate.is_active == True).all()

    @staticmethod
    def create_prompt_template(
        db: Session,
        org_id: str,
        name: str,
        user_prompt_template: str,
        description: Optional[str] = None
    ) -> PromptTemplate:
        template = PromptTemplate(
            org_id=org_id,
            name=name,
            description=description,
            user_prompt_template=user_prompt_template
        )
        db.add(template)
        db.commit()
        db.refresh(template)
        return template

    @staticmethod
    def list_audit_logs(db: Session, org_id: str, limit: int = 50) -> List[AuditLog]:
        return db.query(AuditLog).filter(AuditLog.org_id == org_id).order_by(AuditLog.created_at.desc()).limit(limit).all()
