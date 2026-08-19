# app/routes/rag.py
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path
from typing import Optional

from app.database import SessionLocal
from app.models import rag_chat_models
from app.crud import rag_chat_crud

router = APIRouter(tags=["RAG Assistant"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_rag_service():
    from app.services.llm import LLMFactory
    from app.services.rag import RAGService
    llm_service = LLMFactory.get_provider()
    return RAGService(llm_service=llm_service)

class ChatPayload(BaseModel):
    query: str
    session_id: Optional[str] = None

# 1. Draft Session Visit: Renders workspace cleanly without hitting DB session creation
@router.get("/", response_class=HTMLResponse)
async def draft_workspace(request: Request, db: Session = Depends(get_db)):
    all_sessions = db.query(rag_chat_models.ChatSession).order_by(rag_chat_models.ChatSession.created_at.desc()).all()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "session_id": "",
            "sessions": all_sessions,
            "messages": [],
            "documents": []
        }
    )

# 2. Render Workspace for Existing Session: "http://localhost:4500/chat/{session_id}"
@router.get("/chat/{session_id}", response_class=HTMLResponse)
async def chat_view(request: Request, session_id: str, db: Session = Depends(get_db)):
    session = rag_chat_crud.get_chat_session(db, session_id)
    if not session:
        return RedirectResponse(url="/", status_code=303)

    all_sessions = db.query(rag_chat_models.ChatSession).order_by(rag_chat_models.ChatSession.created_at.desc()).all()
    previous_messages = rag_chat_crud.get_chat_messages(db, session_id)
    uploaded_documents = rag_chat_crud.get_chat_documents(db, session_id)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "session_id": session_id,
            "sessions": all_sessions,
            "messages": previous_messages,
            "documents": uploaded_documents
        }
    )

# 3. Handle File Upload: "POST http://localhost:4500/chat/upload"
@router.post("/chat/upload")
async def upload_document(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    rag_service = Depends(get_rag_service)
):
    try:
        session_title = None
        if not session_id or session_id.strip() == "" or session_id == "None":
            title = f"Doc: {file.filename}"
            new_session = rag_chat_crud.create_chat_session(db, title=title)
            session_id = new_session.id
            session_title = new_session.title

        content = await file.read()
        message = rag_service.ingest_document(
            filename=file.filename,
            file_bytes=content,
            session_id=session_id
        )
        rag_chat_crud.register_chat_document(db, session_id, file.filename)
        return {
            "status": "success",
            "session_id": session_id,
            "session_title": session_title,
            "message": message
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 4. Handle Chat Query: "POST http://localhost:4500/chat/query"
@router.post("/chat/query")
async def chat_query(
    payload: ChatPayload,
    db: Session = Depends(get_db),
    rag_service = Depends(get_rag_service)
):
    try:
        session_id = payload.session_id
        session_title = None
        if not session_id or session_id.strip() == "" or session_id == "None":
            clean_query = payload.query.strip()
            title = clean_query[:30] + ("..." if len(clean_query) > 30 else "")
            new_session = rag_chat_crud.create_chat_session(db, title=title)
            session_id = new_session.id
            session_title = new_session.title

        rag_chat_crud.create_chat_message(db, session_id, "user", payload.query)
        answer, sources = rag_service.query_assistant(payload.query, session_id, db)
        rag_chat_crud.create_chat_message(db, session_id, "assistant", answer)
        return {
            "status": "success",
            "session_id": session_id,
            "session_title": session_title,
            "answer": answer,
            "sources": sources
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 5. Handle Chat Session Deletion: "DELETE http://localhost:4500/chat/{session_id}"
@router.delete("/chat/{session_id}")
async def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    rag_service = Depends(get_rag_service)
):
    try:
        # 1. Purge vectors from Qdrant
        rag_service.delete_session_vectors(session_id)

        # 2. Delete session (and cascaded records) from PostgreSQL
        deleted = rag_chat_crud.delete_chat_session(db, session_id)
        if not deleted:
            return {"status": "error", "message": "Chat session not found."}

        return {"status": "success", "message": "Chat session and vector index deleted successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
