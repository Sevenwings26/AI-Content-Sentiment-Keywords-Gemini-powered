# app/models/enterprise_models.py
import enum
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column, String, Text, ForeignKey, DateTime, Boolean, 
    Enum, Index, Integer, JSON
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB

Base = declarative_base()

# --- Enums ---

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"   # Tenant-wide configuration, access control, audit review
    DEPT_ADMIN = "DEPT_ADMIN"     # Department-level knowledge base curation & member review
    MEMBER = "MEMBER"             # Standard query and personal session access
    AUDITOR = "AUDITOR"           # Read-only access to audit logs and security telemetry

class AccessLevel(str, enum.Enum):
    PUBLIC = "PUBLIC"             # Tenant-wide (accessible by any authenticated user in the Org)
    DEPARTMENT = "DEPARTMENT"     # Restricted to users of the specific Department
    CONFIDENTIAL = "CONFIDENTIAL" # Restricted to DeptAdmins and SuperAdmins of the Department
    RESTRICTED = "RESTRICTED"     # Strictly private to the document owner / specific session

class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"

class IngestionJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# --- Tenant & Organization Models ---

class Organization(Base):
    """Represents the root Tenant boundary."""
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    sso_domain = Column(String(255), nullable=True) # e.g. 'acme.com' for SSO routing
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    departments = relationship("Department", back_populates="organization", cascade="all, delete-orphan")
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    documents = relationship("EnterpriseDocument", back_populates="organization", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="organization", cascade="all, delete-orphan")


class Department(Base):
    """Represents a functional unit (e.g. Engineering, HR, Legal)."""
    __tablename__ = "departments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    code = Column(String(50), nullable=False) # e.g. 'ENG', 'HR', 'FIN'
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="departments")
    users = relationship("User", back_populates="department")
    documents = relationship("EnterpriseDocument", back_populates="department")

    __table_args__ = (
        Index("ix_org_dept_code", "org_id", "code", unique=True),
    )


class User(Base):
    """Enterprise identity entity linked to SSO/Local Auth."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True) # Nullable if SSO is enforced
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.MEMBER, nullable=False)
    
    # SSO / OIDC linkage
    sso_provider = Column(String(50), nullable=True) # 'google', 'okta', 'azure_ad', 'saml'
    sso_subject_id = Column(String(255), nullable=True, index=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="users")
    department = relationship("Department", back_populates="users")
    sessions = relationship("EnterpriseChatSession", back_populates="user", cascade="all, delete-orphan")
    uploaded_documents = relationship("EnterpriseDocument", back_populates="uploader")

    __table_args__ = (
        Index("ix_org_user_email", "org_id", "email", unique=True),
    )


# --- Document Governance & RAG Metadata ---

class EnterpriseDocument(Base):
    """Tracks document-level permissions and ingestion metadata."""
    __tablename__ = "enterprise_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    uploader_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True) # SHA-256
    file_size_bytes = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    
    access_level = Column(Enum(AccessLevel), default=AccessLevel.DEPARTMENT, nullable=False, index=True)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="documents")
    department = relationship("Department", back_populates="documents")
    uploader = relationship("User", back_populates="uploaded_documents")


class EnterpriseChatSession(Base):
    """Scoped multi-tenant conversation container."""
    __tablename__ = "enterprise_chat_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    title = Column(String(255), default="New Enterprise Session")
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="sessions")
    messages = relationship("EnterpriseChatMessage", back_populates="session", cascade="all, delete-orphan")


class EnterpriseChatMessage(Base):
    """Stores interaction history with full citation provenance."""
    __tablename__ = "enterprise_chat_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("enterprise_chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False) # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    
    # Traceability: Stored JSON of retrieved chunk IDs, source document IDs, and confidence scores
    citation_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("EnterpriseChatSession", back_populates="messages")


class IngestionJob(Base):
    """Admin-governed scheduled or on-demand data source sync rules."""
    __tablename__ = "ingestion_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False) # 's3', 'relational_db', 'file'
    access_level = Column(Enum(AccessLevel), default=AccessLevel.DEPARTMENT, nullable=False)
    
    # Store connection parameters (e.g. bucket_name, db_connection_url, sql_query, prefix)
    connection_config = Column(JSON, nullable=False)
    cron_schedule = Column(String(100), nullable=True) # e.g. '0 0 * * *' for daily sync
    
    status = Column(Enum(IngestionJobStatus), default=IngestionJobStatus.PENDING, nullable=False)
    last_run_at = Column(DateTime, nullable=True)
    documents_processed_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- Immutable Audit Trail ---

class AuditLog(Base):
    """Tamper-evident audit logging for security compliance."""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    action = Column(String(100), nullable=False, index=True) # e.g. 'DOCUMENT_INGEST', 'RAG_QUERY', 'SESSION_DELETE'
    resource_type = Column(String(50), nullable=False)      # 'DOCUMENT', 'VECTOR_POINT', 'CHAT_SESSION'
    resource_id = Column(String(255), nullable=True)
    
    details = Column(JSON, nullable=True)                   # Query text, retrieved chunk IDs, IP address, user-agent
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    organization = relationship("Organization", back_populates="audit_logs")
