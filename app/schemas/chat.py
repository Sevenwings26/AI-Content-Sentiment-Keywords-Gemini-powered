# app/schemas/chat.py
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ChatQueryPayload(BaseModel):
    """
    Unified query payload supporting personal, departmental, and enterprise scopes.
    """
    query: str = Field(..., description="The user's query text")
    session_id: Optional[str] = Field(None, description="Active conversational thread ID")
    scope: Optional[List[str]] = Field(
        default=["personal", "department", "enterprise"],
        description="Allowed search scopes: 'personal', 'department', 'enterprise'"
    )
    persona_id: Optional[str] = Field(None, description="Optional Assistant Persona ID")
    template_id: Optional[str] = Field(None, description="Optional Prompt Template ID")
    top_k: int = Field(3, description="Number of final context chunks after reranking")
    score_threshold: float = Field(0.35, description="Minimum similarity score threshold")

class SourceCitation(BaseModel):
    filename: str
    document_id: Optional[str] = None
    department_id: Optional[str] = None
    access_level: Optional[str] = None
    preview: str
    relevance_score: float
    source_type: Optional[str] = "file"

class ChatQueryResponse(BaseModel):
    status: str = "success"
    session_id: Optional[str] = None
    session_title: Optional[str] = None
    answer: str
    sources: List[SourceCitation] = []
    is_grounded: bool = True
    grounding_confidence: float = 1.0

class ChatSessionItem(BaseModel):
    id: str
    title: str
    created_at: str

class ChatMessageItem(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    citation_metadata: Optional[Dict[str, Any]] = None
