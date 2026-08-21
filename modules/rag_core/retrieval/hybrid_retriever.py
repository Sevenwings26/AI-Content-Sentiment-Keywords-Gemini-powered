# modules/rag_core/retrieval/hybrid_retriever.py
import logging
from typing import List, Dict, Any, Optional
from qdrant_client.models import Filter
from core.config import settings
from modules.rag_core.retrieval.vector_store import VectorStoreService
from modules.rag_core.providers.llm import BaseLLMService

logger = logging.getLogger("hybrid_retriever")

class HybridRetriever:
    def __init__(self, vector_store: VectorStoreService, llm_service: BaseLLMService):
        self.vector_store = vector_store
        self.llm = llm_service

    def retrieve(
        self,
        query: str,
        security_filter: Filter,
        candidate_limit: int = 15,
        score_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        threshold = score_threshold if score_threshold is not None else settings.DEFAULT_SCORE_THRESHOLD
        query_vector = self.llm.get_embeddings(query)

        hits = self.vector_store.search_vectors(
            query_vector=query_vector,
            search_filter=security_filter,
            limit=candidate_limit,
            score_threshold=threshold
        )

        candidates = []
        for hit in hits:
            payload = hit["payload"]
            candidates.append({
                "chunk_id": hit["id"],
                "content": payload.get("content", ""),
                "filename": payload.get("filename", "unknown"),
                "document_id": payload.get("document_id"),
                "department_id": payload.get("department_id"),
                "access_level": payload.get("access_level"),
                "source_type": payload.get("source_type", "file"),
                "vector_score": hit["score"]
            })

        logger.info(f"HybridRetriever retrieved {len(candidates)} candidate chunks above score {threshold}")
        return candidates
