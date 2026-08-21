# app/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from modules.auth.domain.models import UserRole
from modules.auth.domain.tokens import TokenData
from modules.auth.services.token_service import verify_password, create_access_token
from modules.auth.repositories.user_repository import UserRepository
from modules.governance.services.audit_logger import AuditLogger
from app.schemas.auth import (
    UserRegisterPayload, UserLoginPayload, TokenResponse,
    OrganizationCreatePayload, DepartmentCreatePayload, UserProfileResponse
)

router = APIRouter(prefix="/enterprise/auth", tags=["Enterprise Identity & Access"])

@router.post("/register", response_model=TokenResponse)
def register_user(payload: UserRegisterPayload, db: Session = Depends(get_db)):
    org = UserRepository.get_org_by_id(db, payload.org_id)
    if not org:
        raise HTTPException(status_code=400, detail="Organization not found")

    existing_user = UserRepository.get_by_email(db, payload.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    role = UserRole(payload.role) if hasattr(UserRole, payload.role) else UserRole.MEMBER
    user = UserRepository.create_user(
        db=db,
        org_id=payload.org_id,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=role,
        department_id=payload.department_id
    )

    token_data = {
        "sub": user.id,
        "email": user.email,
        "org_id": user.org_id,
        "dept_id": user.department_id,
        "role": user.role.value
    }
    access_token = create_access_token(data=token_data)

    AuditLogger.log(
        db=db,
        org_id=user.org_id,
        user_id=user.id,
        action="USER_REGISTERED",
        resource_type="USER",
        resource_id=user.id,
        details={"email": user.email, "role": user.role.value}
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        org_id=user.org_id,
        department_id=user.department_id,
        role=user.role.value
    )

@router.post("/login", response_model=TokenResponse)
def login_user(payload: UserLoginPayload, db: Session = Depends(get_db)):
    user = UserRepository.get_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token_data = {
        "sub": user.id,
        "email": user.email,
        "org_id": user.org_id,
        "dept_id": user.department_id,
        "role": user.role.value
    }
    access_token = create_access_token(data=token_data)

    AuditLogger.log(
        db=db,
        org_id=user.org_id,
        user_id=user.id,
        action="USER_LOGIN",
        resource_type="AUTH",
        resource_id=user.id
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        org_id=user.org_id,
        department_id=user.department_id,
        role=user.role.value
    )

@router.get("/me", response_model=UserProfileResponse)
def get_current_user_profile(current_user: TokenData = Depends(get_current_user)):
    return UserProfileResponse(
        user_id=current_user.user_id,
        email=current_user.email or "",
        org_id=current_user.org_id,
        department_id=current_user.department_id,
        role=current_user.role
    )
