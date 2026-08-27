# modules/rag_core/retrieval/reranker.py
import logging
from typing import List, Dict, Any
from core.config import settings

logger = logging.getLogger("cross_encoder_reranker")

class CrossEncoderReranker:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.RERANKER_MODEL
        self.model = None
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(self.model_name)
            logger.info(f"Loaded CrossEncoder re-ranking model: {self.model_name}")
        except Exception as e:
            logger.warning(f"CrossEncoder fallback to vector ranking: {e}")
            self.model = None

    def rerank(
        self,
        query: str,
        candidate_chunks: List[Dict[str, Any]],
        top_n: int = 3
    ) -> List[Dict[str, Any]]:
        if not candidate_chunks:
            return []

        if not self.model:
            sorted_chunks = sorted(candidate_chunks, key=lambda x: x.get("vector_score", 0.0), reverse=True)
            for c in sorted_chunks:
                c["rerank_score"] = c.get("vector_score", 0.0)
            return sorted_chunks[:top_n]

        pairs = [[query, chunk["content"]] for chunk in candidate_chunks]
        scores = self.model.predict(pairs)

        for chunk, score in zip(candidate_chunks, scores):
            chunk["rerank_score"] = float(score)

        reranked = sorted(candidate_chunks, key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_n]
