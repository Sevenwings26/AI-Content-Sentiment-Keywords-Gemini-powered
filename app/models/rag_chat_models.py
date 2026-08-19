# app/models.py (add these to the end of the file)
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
# import hashlib

from app.database import Base


class ChatSession(Base):
    """
    Represents an isolated chat room/conversation thread.
    Uniquely identified by a UUID.
    """
    __tablename__ = "chat_sessions"

    # String(36) is cross-compatible between SQLite and PostgreSQL for UUID strings
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), default="New Chat Session")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships: Deleting a session cleans up its messages and documents
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    documents = relationship("ChatDocument", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """
    Stores conversational chat history for a session to provide short-term memory.
    """
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class ChatDocument(Base):
    """
    Tracks which files have been uploaded to a specific chat session.
    (Kept in SQL so we can display uploaded file names in the UI quickly).
    """
    __tablename__ = "chat_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="documents")
    