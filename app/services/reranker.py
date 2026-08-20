# app/services/reranker.py
import logging
from typing import List, Dict, Any

logger = logging.getLogger("reranker")

try:
    from flashrank import Ranker, RerankRequest
    HAS_FLASHRANK = True
except ImportError:
    HAS_FLASHRANK = False
    logger.info("FlashRank not installed. Falling back to vector cosine score ranking.")

class CrossEncoderReranker:
    """
    Lightweight CPU-optimized Cross-Encoder Re-ranker powered by FlashRank.
    Re-scores candidate chunks retrieved from vector search to maximize precision.
    """
    _ranker_instance = None

    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2"):
        if HAS_FLASHRANK and CrossEncoderReranker._ranker_instance is None:
            try:
                CrossEncoderReranker._ranker_instance = Ranker(model_name=model_name)
            except Exception as e:
                logger.warning(f"Could not load FlashRank model '{model_name}': {e}")
        self.ranker = CrossEncoderReranker._ranker_instance

    def rerank(self, query: str, candidate_chunks: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
        """
        Re-ranks candidate chunk dicts:
        candidate_chunks: [{'id': ..., 'text': ..., 'payload': ...}, ...]
        Returns top_n re-scored and sorted candidate chunks.
        """
        if not candidate_chunks:
            return []

        if self.ranker and HAS_FLASHRANK:
            try:
                passages = [
                    {
                        "id": chunk.get("id", str(idx)),
                        "text": chunk.get("text", ""),
                        "meta": chunk.get("payload", {})
                    }
                    for idx, chunk in enumerate(candidate_chunks)
                ]
                request = RerankRequest(query=query, passages=passages)
                ranked_results = self.ranker.rerank(request)
                return ranked_results[:top_n]
            except Exception as e:
                logger.warning(f"FlashRank reranking error: {e}. Using vector scores.")

        # Fallback: Sort by vector similarity score
        sorted_chunks = sorted(
            candidate_chunks,
            key=lambda x: x.get("vector_score", x.get("score", 0.0)),
            reverse=True
        )
        return [
            {
                "id": chunk.get("id"),
                "text": chunk.get("text"),
                "meta": chunk.get("payload", {}),
                "score": chunk.get("vector_score", chunk.get("score", 0.0))
            }
            for chunk in sorted_chunks[:top_n]
        ]

