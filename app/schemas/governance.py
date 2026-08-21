# app/schemas/governance.py
from typing import Optional
from pydantic import BaseModel

class DepartmentCreatePayload(BaseModel):
    name: str
    code: str

class DepartmentResponse(BaseModel):
    id: str
    name: str
    code: str
    created_at: str

class PersonaCreatePayload(BaseModel):
    name: str
    description: Optional[str] = None
    system_instruction_template: str
    temperature: int = 2
    target_department_id: Optional[str] = None
    is_default: bool = False

class PersonaResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    department_id: Optional[str] = None
    is_default: bool = False
    system_template: str

class PromptTemplateCreatePayload(BaseModel):
    title: str
    user_prompt_template: str
    category: str = "QNA"
    persona_id: Optional[str] = None
    target_department_id: Optional[str] = None

class PromptTemplateResponse(BaseModel):
    id: str
    title: str
    category: str
    persona_id: Optional[str] = None
    department_id: Optional[str] = None
    user_prompt_template: str

class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[dict] = None
    created_at: str
