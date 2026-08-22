# modules/rag_core/orchestrator/query_planner.py
import re
from typing import List, Optional
from modules.auth.domain.tokens import TokenData
from modules.rag_core.domain.types import QueryPlan

QueryExecutionPlan = QueryPlan

class QueryPlanner:
    CONVERSATIONAL_PATTERNS = [
        r"^\s*(hi|hello|hey|good morning|good afternoon|good evening|howdy|greetings)\b",
        r"^\s*(who are you|what can you do|help me|how does this work|what is your name)\b",
        r"^\s*(thank you|thanks|bye|goodbye|see you|good night)\b",
        r"^\s*(how are you|how's it going|what's up)\b"
    ]

    GENERAL_KNOWLEDGE_PATTERNS = [
        r"^(how many|what is the capital of|who wrote|when was|translate|calculate|write a|code a|explain the concept of)\b",
        r"\b(continents?|planets?|oceans?|countries|pythagorean|fibonacci|javascript|python|css|html)\b"
    ]

    DOCUMENT_RAG_KEYWORDS = [
        r"\b(policy|policies|document|documents|file|files|uploaded|pdf|handbook|manual|contract|procedure|agreement|revenue|q[1-4]|report|internal|nda|org|department|guideline|compliance|sop)\b"
    ]

    @classmethod
    def analyze_and_plan(
        cls,
        query: str,
        user_context: Optional[TokenData] = None,
        has_session_documents: bool = False,
        mode: str = "auto"
    ) -> QueryPlan:
        clean_query = query.strip()
        lower_query = clean_query.lower()

        # 1. Explicit Mode Override
        if mode == "general":
            return QueryPlan(
                is_conversational_only=True,
                target_scopes=[],
                sub_queries=[clean_query],
                intent_category="CONVERSATIONAL"
            )
        elif mode == "rag":
            return QueryPlan(
                is_conversational_only=False,
                target_scopes=["personal", "department", "enterprise"],
                sub_queries=[clean_query],
                intent_category="DOCUMENT_RAG"
            )

        # 2. Dynamic Auto-Routing:
        # A. Conversational / Greetings
        for pattern in cls.CONVERSATIONAL_PATTERNS:
            if re.search(pattern, lower_query):
                return QueryPlan(
                    is_conversational_only=True,
                    target_scopes=[],
                    sub_queries=[clean_query],
                    intent_category="CONVERSATIONAL"
                )

        # B. Document-referencing keywords -> Prioritize RAG
        for pattern in cls.DOCUMENT_RAG_KEYWORDS:
            if re.search(pattern, lower_query):
                return QueryPlan(
                    is_conversational_only=False,
                    target_scopes=["personal", "department", "enterprise"],
                    sub_queries=[clean_query],
                    intent_category="DOCUMENT_RAG"
                )

        # C. If session has uploaded files attached -> Route to RAG
        if has_session_documents:
            return QueryPlan(
                is_conversational_only=False,
                target_scopes=["personal", "department", "enterprise"],
                sub_queries=[clean_query],
                intent_category="DOCUMENT_RAG"
            )

        # D. General world knowledge pattern check
        for pattern in cls.GENERAL_KNOWLEDGE_PATTERNS:
            if re.search(pattern, lower_query):
                return QueryPlan(
                    is_conversational_only=True,
                    target_scopes=[],
                    sub_queries=[clean_query],
                    intent_category="GENERAL_KNOWLEDGE"
                )

        # Default fallback: Route to RAG with graceful general fallback if no documents match
        return QueryPlan(
            is_conversational_only=False,
            target_scopes=["personal", "department", "enterprise"],
            sub_queries=[clean_query],
            intent_category="DOCUMENT_RAG"
        )
