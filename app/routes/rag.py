 #app/routes/rag.py
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, Header, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path
from typing import Optional, List

from app.database import SessionLocal
from app.models import rag_chat_models
from app.crud import rag_chat_crud
from app.services.llm import LLMFactory
from app.services.rag import RAGService
from app.core.security import TokenData, decode_access_token

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
    llm_service = LLMFactory.get_provider()
    return RAGService(llm_service=llm_service)

def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[TokenData]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ")[1]
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        org_id = payload.get("org_id")
        role = payload.get("role")
        if user_id and org_id:
            return TokenData(
                user_id=user_id,
                org_id=org_id,
                department_id=payload.get("dept_id"),
                role=role or "MEMBER",
                email=payload.get("email", "")
            )
    except Exception:
        pass
    return None

class ChatPayload(BaseModel):
    query: str
    session_id: Optional[str] = None

@router.get("/login", response_class=HTMLResponse)
async def login_view(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# API endpoint to fetch user-scoped sessions
@router.get("/chat/sessions")
async def list_user_sessions(
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(get_optional_user)
):
    user_id = current_user.user_id if current_user else None
    org_id = current_user.org_id if current_user else None
    sessions = rag_chat_crud.get_user_chat_sessions(db, user_id=user_id, org_id=org_id)
    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at.isoformat()
        }
        for s in sessions
    ]

# 1. Draft Session Visit: Renders workspace cleanly
@router.get("/", response_class=HTMLResponse)
async def draft_workspace(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(get_optional_user)
):
    user_id = current_user.user_id if current_user else None
    org_id = current_user.org_id if current_user else None
    user_sessions = rag_chat_crud.get_user_chat_sessions(db, user_id=user_id, org_id=org_id)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "session_id": "",
            "sessions": user_sessions,
            "messages": [],
            "documents": []
        }
    )

# 2. Render Workspace for Existing Session
@router.get("/chat/{session_id}", response_class=HTMLResponse)
async def chat_view(
    request: Request,
    session_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(get_optional_user)
):
    session = rag_chat_crud.get_chat_session(db, session_id)
    if not session:
        return RedirectResponse(url="/", status_code=303)

    user_id = current_user.user_id if current_user else None
    org_id = current_user.org_id if current_user else None

    if session.user_id and user_id and session.user_id != user_id:
        return RedirectResponse(url="/", status_code=303)

    user_sessions = rag_chat_crud.get_user_chat_sessions(db, user_id=user_id, org_id=org_id)
    previous_messages = rag_chat_crud.get_chat_messages(db, session_id)
    uploaded_documents = rag_chat_crud.get_chat_documents(db, session_id)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "session_id": session_id,
            "sessions": user_sessions,
            "messages": previous_messages,
            "documents": uploaded_documents
        }
    )

# 3. Handle File Upload
@router.post("/chat/upload")
async def upload_document(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    rag_service = Depends(get_rag_service),
    current_user: Optional[TokenData] = Depends(get_optional_user)
):
    try:
        user_id = current_user.user_id if current_user else None
        org_id = current_user.org_id if current_user else None

        session_title = None
        if not session_id or session_id.strip() == "" or session_id == "None":
            title = f"Doc: {file.filename}"
            new_session = rag_chat_crud.create_chat_session(db, title=title, user_id=user_id, org_id=org_id)
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

# 4. Handle Chat Query
@router.post("/chat/query")
async def chat_query(
    payload: ChatPayload,
    db: Session = Depends(get_db),
    rag_service = Depends(get_rag_service),
    current_user: Optional[TokenData] = Depends(get_optional_user)
):
    try:
        user_id = current_user.user_id if current_user else None
        org_id = current_user.org_id if current_user else None

        session_id = payload.session_id
        session_title = None
        if not session_id or session_id.strip() == "" or session_id == "None":
            clean_query = payload.query.strip()
            title = clean_query[:30] + ("..." if len(clean_query) > 30 else "")
            new_session = rag_chat_crud.create_chat_session(db, title=title, user_id=user_id, org_id=org_id)
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

# 5. Handle Chat Session Deletion
@router.delete("/chat/{session_id}")
async def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    rag_service = Depends(get_rag_service),
    current_user: Optional[TokenData] = Depends(get_optional_user)
):
    try:
        session = rag_chat_crud.get_chat_session(db, session_id)
        if not session:
            return {"status": "error", "message": "Chat session not found."}

        user_id = current_user.user_id if current_user else None
        if session.user_id and user_id and session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        rag_service.delete_session_vectors(session_id)
        rag_chat_crud.delete_chat_session(db, session_id)

        return {"status": "success", "message": "Chat session and vector index deleted successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 6. Handle Document Deletion
@router.delete("/chat/{session_id}/document/{filename}")
async def delete_document(
    session_id: str,
    filename: str,
    db: Session = Depends(get_db),
    rag_service = Depends(get_rag_service),
    current_user: Optional[TokenData] = Depends(get_optional_user)
):
    try:
        session = rag_chat_crud.get_chat_session(db, session_id)
        user_id = current_user.user_id if current_user else None
        if session and session.user_id and user_id and session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        rag_service.delete_document_vectors(session_id, filename)
        deleted = rag_chat_crud.delete_chat_document(db, session_id, filename)
        if not deleted:
            return {"status": "error", "message": "Document record not found."}

        return {"status": "success", "message": f"Document '{filename}' and vector chunks removed successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}