# modules/rag_core/orchestrator/query_planner.py
import re
from dataclasses import dataclass
from typing import List
from modules.auth.domain.tokens import TokenData
from modules.rag_core.domain.types import QueryPlan

@dataclass
class QueryExecutionPlan:
    is_conversational_only: bool
    target_scopes: List[str]
    sub_queries: List[str]
    intent_category: str  # "GREETING", "GENERAL", "KNOWLEDGE_SEARCH", "MULTI_SOURCE_QUERY"

class QueryPlanner:
    CONVERSATIONAL_PATTERNS = [
        r"^\s*(hi|hello|hey|good morning|good afternoon|good evening|howdy)\b",
        r"^\s*(who are you|what can you do|help me|how does this work)\b",
        r"^\s*(thank you|thanks|bye|goodbye|see you)\b"
    ]

    @classmethod
    def analyze_and_plan(cls, query: str, user_context: TokenData) -> QueryExecutionPlan:
        clean_query = query.strip()

        for pattern in cls.CONVERSATIONAL_PATTERNS:
            if re.search(pattern, clean_query, re.IGNORECASE):
                return QueryExecutionPlan(
                    is_conversational_only=True,
                    target_scopes=[],
                    sub_queries=[clean_query],
                    intent_category="GENERAL"
                )

        target_scopes = ["personal", "department", "enterprise"]
        return QueryExecutionPlan(
            is_conversational_only=False,
            target_scopes=target_scopes,
            sub_queries=[clean_query],
            intent_category="KNOWLEDGE_SEARCH"
        )
