# app/routes/chat.py
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_orchestrator, get_optional_user, resolve_effective_user
from modules.auth.domain.tokens import TokenData
from modules.rag_core.orchestrator.unified_orchestrator import UnifiedRAGOrchestrator
from modules.governance.repositories.chat_repository import ChatRepository
from app.schemas.chat import (
    ChatQueryPayload, ChatQueryResponse, SourceCitation, ChatSessionItem, ChatMessageItem
)

router = APIRouter(tags=["Unified Conversational RAG"])

@router.post("/chat/query", response_model=ChatQueryResponse)
@router.post("/enterprise/chat/query", response_model=ChatQueryResponse)
def execute_chat_query(
    payload: ChatQueryPayload,
    db: Session = Depends(get_db),
    orchestrator: UnifiedRAGOrchestrator = Depends(get_orchestrator),
    auth_user: Optional[TokenData] = Depends(get_optional_user)
):
    user_context = resolve_effective_user(auth_user, db)

    clean_query = payload.query.strip()
    session_title = clean_query[:30] + ("..." if len(clean_query) > 30 else "")
    session = ChatRepository.get_or_create_session(
        db=db,
        session_id=payload.session_id,
        org_id=user_context.org_id,
        department_id=user_context.department_id,
        user_id=user_context.user_id,
        title=session_title
    )

    ChatRepository.add_message(db, session_id=session.id, role="user", content=payload.query)

    answer, sources, is_grounded, confidence = orchestrator.execute_unified_query(
        query=payload.query,
        user_context=user_context,
        db=db,
        session_id=session.id,
        scope=payload.scope,
        persona_id=payload.persona_id,
        template_id=payload.template_id,
        top_k=payload.top_k,
        score_threshold=payload.score_threshold,
        mode=payload.mode or "auto"
    )

    ChatRepository.add_message(
        db=db,
        session_id=session.id,
        role="assistant",
        content=answer,
        citation_metadata={"sources": sources, "is_grounded": is_grounded, "confidence": confidence}
    )

    formatted_sources = [
        SourceCitation(
            filename=s["filename"],
            document_id=s.get("document_id"),
            department_id=s.get("department_id"),
            access_level=s.get("access_level"),
            preview=s["preview"],
            relevance_score=s["relevance_score"],
            source_type=s.get("source_type", "file")
        )
        for s in sources
    ]

    return ChatQueryResponse(
        status="success",
        session_id=session.id,
        session_title=session.title,
        answer=answer,
        sources=formatted_sources,
        is_grounded=is_grounded,
        grounding_confidence=confidence
    )

@router.get("/chat/sessions", response_model=List[ChatSessionItem])
def list_chat_sessions(
    db: Session = Depends(get_db),
    auth_user: Optional[TokenData] = Depends(get_optional_user)
):
    if not auth_user or not auth_user.user_id:
        return []  # Unauthenticated guests receive zero historical sessions

    sessions = ChatRepository.list_user_sessions(
        db,
        org_id=auth_user.org_id,
        user_id=auth_user.user_id
    )
    return [
        ChatSessionItem(
            id=s.id,
            title=s.title,
            created_at=s.created_at.isoformat() if s.created_at else ""
        )
        for s in sessions
    ]

@router.get("/chat/{session_id}/messages", response_model=List[ChatMessageItem])
def get_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    auth_user: Optional[TokenData] = Depends(get_optional_user)
):
    user_context = resolve_effective_user(auth_user, db)
    session = ChatRepository.get_session_by_id(db, session_id, user_context.org_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Access control: session owner, super admin, or guest session created in same context
    if session.user_id and session.user_id != user_context.user_id and user_context.role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Access denied to this conversation thread")

    messages = ChatRepository.get_session_messages(db, session_id)
    return [
        ChatMessageItem(
            id=str(m.id),
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat() if m.created_at else "",
            citation_metadata=m.citation_metadata
        )
        for m in messages
    ]

@router.delete("/chat/{session_id}")
def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    orchestrator: UnifiedRAGOrchestrator = Depends(get_orchestrator),
    auth_user: Optional[TokenData] = Depends(get_optional_user)
):
    user_context = resolve_effective_user(auth_user, db)
    session = ChatRepository.get_session_by_id(db, session_id, user_context.org_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    if session.user_id != user_context.user_id and user_context.role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Access denied")

    orchestrator.delete_session_vectors(session_id)
    ChatRepository.delete_session(db, session_id, user_context.org_id)

    return {"status": "success", "message": "Chat session and associated vectors deleted successfully"}
