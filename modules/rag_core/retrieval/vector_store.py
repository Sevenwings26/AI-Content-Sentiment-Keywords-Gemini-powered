# modules/rag_core/retrieval/vector_store.py
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct, Filter
)
from core.config import settings

logger = logging.getLogger("vector_store_service")

class VectorStoreService:
    def __init__(self):
        if settings.QDRANT_STORAGE == "server":
            self.client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                api_key=settings.QDRANT_API_KEY
            )
        else:
            self.client = QdrantClient(path=settings.QDRANT_PATH)

        self.collection_name = settings.QDRANT_COLLECTION
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                logger.info(f"Creating Qdrant collection '{self.collection_name}'...")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=settings.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE
                    )
                )
        except Exception as e:
            logger.error(f"Error ensuring Qdrant collection '{self.collection_name}': {e}")

    def upsert_chunks(self, points: List[PointStruct]):
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    def search_vectors(
        self,
        query_vector: List[float],
        search_filter: Optional[Filter] = None,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes vector similarity search with backward and forward compatibility
        supporting modern qdrant-client (>=1.10.0 query_points) and legacy (search).
        """
        hits = []
        try:
            if hasattr(self.client, "query_points"):
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=search_filter,
                    limit=limit,
                    score_threshold=score_threshold
                )
                hits = response.points if hasattr(response, "points") else response
            elif hasattr(self.client, "search"):
                hits = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=search_filter,
                    limit=limit,
                    score_threshold=score_threshold
                )
        except Exception as e:
            logger.error(f"Error searching vectors in Qdrant collection '{self.collection_name}': {e}")
            return []

        return [
            {
                "id": hit.id,
                "score": getattr(hit, "score", 0.0),
                "payload": getattr(hit, "payload", {}) or {}
            }
            for hit in hits
        ]

    def delete_by_filter(self, points_filter: Filter) -> bool:
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=points_filter
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors with filter: {e}")
            return False
