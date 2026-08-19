from sqlalchemy.orm import Session
from app import models

# --- RAG Session CRUD ---

def create_chat_session(db: Session, title: str = "New Chat Session"):
    db_session = models.ChatSession(title=title)
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

def get_chat_session(db: Session, session_id: str):
    return db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()

def delete_chat_session(db: Session, session_id: str) -> bool:
    """Deletes a chat session from PostgreSQL (cascading to messages and document metadata)."""
    db_session = get_chat_session(db, session_id)
    if db_session:
        db.delete(db_session)
        db.commit()
        return True
    return False

# --- Chat Messages CRUD ---

def create_chat_message(db: Session, session_id: str, role: str, content: str):
    db_message = models.ChatMessage(session_id=session_id, role=role, content=content)
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

def get_chat_messages(db: Session, session_id: str):
    """Retrieves all messages for a specific session ordered by creation time."""
    return (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )

# --- Chat Documents CRUD ---

def register_chat_document(db: Session, session_id: str, filename: str):
    db_document = models.ChatDocument(session_id=session_id, filename=filename)
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    return db_document

def get_chat_documents(db: Session, session_id: str):
    return db.query(models.ChatDocument).filter(models.ChatDocument.session_id == session_id).all()

def delete_chat_document(db: Session, session_id: str, filename: str) -> bool:
    """Deletes a specific document metadata record for a session from PostgreSQL."""
    doc = (
        db.query(models.ChatDocument)
        .filter(
            models.ChatDocument.session_id == session_id,
            models.ChatDocument.filename == filename
        )
        .first()
    )
    if doc:
        db.delete(doc)
        db.commit()
        return True
    return False
