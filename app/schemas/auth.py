# app/schemas/auth.py
from typing import Optional
from pydantic import BaseModel
from modules.auth.domain.models import UserRole

class TenantRegistrationPayload(BaseModel):
    org_name: str
    org_slug: str
    admin_name: str
    admin_email: str
    admin_password: str
    department_name: str = "Engineering"
    department_code: str = "ENG"

class UserRegisterPayload(BaseModel):
    org_id: str
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "MEMBER"
    department_id: Optional[str] = None

class UserCreatePayload(BaseModel):
    email: str
    full_name: str
    password: str
    role: UserRole = UserRole.MEMBER
    department_id: Optional[str] = None

class UserLoginPayload(BaseModel):
    email: str
    password: str

class LoginPayload(BaseModel):
    email: str
    password: str

class OrganizationCreatePayload(BaseModel):
    name: str
    slug: str

class DepartmentCreatePayload(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    org_id: Optional[str] = None
    user_id: Optional[str] = None
    department_id: Optional[str] = None
    role: Optional[str] = None

class UserProfileResponse(BaseModel):
    id: Optional[str] = None
    user_id: Optional[str] = None
    full_name: Optional[str] = None
    email: str
    role: str
    org_id: str
    department_id: Optional[str] = None
    is_active: bool = True
