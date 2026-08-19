# app/services/reranker.py
from typing import List, Dict, Any
from flashrank import Ranker, RerankRequest

class CrossEncoderReranker:
    """
    Lightweight CPU-optimized Cross-Encoder Re-ranker powered by FlashRank.
    Re-scores candidate chunks retrieved from vector search to maximize precision.
    """
    _ranker_instance = None

    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2"):
        if CrossEncoderReranker._ranker_instance is None:
            CrossEncoderReranker._ranker_instance = Ranker(model_name=model_name)
        self.ranker = CrossEncoderReranker._ranker_instance

    def rerank(self, query: str, candidate_chunks: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
        """
        Re-ranks candidate chunk dicts:
        candidate_chunks: [{'id': ..., 'text': ..., 'payload': ...}, ...]
        Returns top_n re-scored and sorted candidate chunks.
        """
        if not candidate_chunks:
            return []

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
