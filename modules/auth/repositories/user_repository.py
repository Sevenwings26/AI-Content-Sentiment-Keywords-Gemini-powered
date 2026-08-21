# modules/auth/repositories/user_repository.py
import uuid
from typing import Optional, List
from sqlalchemy.orm import Session
from modules.auth.domain.models import User, Organization, Department, UserRole
from modules.auth.services.token_service import get_password_hash

class UserRepository:
    @staticmethod
    def get_by_id(db: Session, user_id: str) -> Optional[User]:
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email, User.is_active == True).first()

    @staticmethod
    def get_org_by_id(db: Session, org_id: str) -> Optional[Organization]:
        return db.query(Organization).filter(Organization.id == org_id).first()

    @staticmethod
    def get_org_by_slug(db: Session, slug: str) -> Optional[Organization]:
        return db.query(Organization).filter(Organization.slug == slug).first()

    @staticmethod
    def create_org(db: Session, name: str, slug: str) -> Organization:
        org = Organization(name=name, slug=slug)
        db.add(org)
        db.commit()
        db.refresh(org)
        return org

    @staticmethod
    def create_department(db: Session, org_id: str, name: str, slug: str, description: Optional[str] = None) -> Department:
        dept = Department(org_id=org_id, name=name, slug=slug, description=description)
        db.add(dept)
        db.commit()
        db.refresh(dept)
        return dept

    @staticmethod
    def list_org_departments(db: Session, org_id: str) -> List[Department]:
        return db.query(Department).filter(Department.org_id == org_id).all()

    @staticmethod
    def create_user(
        db: Session,
        org_id: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: UserRole = UserRole.MEMBER,
        department_id: Optional[str] = None
    ) -> User:
        hashed_password = get_password_hash(password)
        user = User(
            org_id=org_id,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            department_id=department_id
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
