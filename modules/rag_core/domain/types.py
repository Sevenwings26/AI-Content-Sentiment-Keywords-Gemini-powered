# modules/rag_core/domain/types.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class RetrievedChunk:
    document_id: str
    filename: str
    content: str
    score: float
    chunk_index: int
    access_level: str
    department_id: Optional[str] = None
    source_type: str = "file"
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class QueryPlan:
    is_conversational_only: bool
    target_scopes: List[str]
    sub_queries: List[str]
    intent_category: str

