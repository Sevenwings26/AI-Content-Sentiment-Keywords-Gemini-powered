# app/services/rag.py
import os
import uuid
from io import BytesIO
from typing import List, Dict, Any, Tuple
from pypdf import PdfReader
from sqlalchemy.orm import Session
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from app.services.llm import BaseLLMService

class RAGService:
    # Class-level client singleton cache to prevent locking conflicts
    _qdrant_client = None

    def __init__(self, llm_service: BaseLLMService):
        self.llm = llm_service
        self.collection_name = "assistant_knowledge"
        
        # 1. Initialize client using the cached singleton
        if RAGService._qdrant_client is None:
            storage_mode = os.getenv("QDRANT_STORAGE", "local").lower()
            if storage_mode == "server":
                host = os.getenv("QDRANT_HOST", "localhost")
                port = int(os.getenv("QDRANT_PORT", 6333))
                api_key = os.getenv("QDRANT_API_KEY", None)
                RAGService._qdrant_client = QdrantClient(host=host, port=port, api_key=api_key)
            else:
                path = os.getenv("QDRANT_PATH", "./qdrant_db")
                RAGService._qdrant_client = QdrantClient(path=path)

        self.qdrant = RAGService._qdrant_client

        # 2. Initialize database collection parameters
        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        """
        Ensures that the target collection exists in Qdrant with matching vector dimensions.
        Dynamically detects active embedding provider dimension and recreates collection if mismatched.
        """
        try:
            sample_vector = self.llm.get_embeddings("test")
            vector_dimension = len(sample_vector)
        except Exception:
            vector_dimension = int(os.getenv("EMBEDDING_DIMENSION", 1024))

        if self.qdrant.collection_exists(collection_name=self.collection_name):
            collection_info = self.qdrant.get_collection(collection_name=self.collection_name)
            existing_size = collection_info.config.params.vectors.size
            if existing_size != vector_dimension:
                self.qdrant.delete_collection(collection_name=self.collection_name)
                self.qdrant.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=vector_dimension, 
                        distance=Distance.COSINE
                    )
                )
        else:
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=vector_dimension, 
                    distance=Distance.COSINE
                )
            )

    def extract_text_from_file(self, filename: str, file_bytes: bytes) -> str:
        """Parses PDF or TXT files and extracts raw text."""
        if filename.endswith(".pdf"):
            pdf = PdfReader(BytesIO(file_bytes))
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
        else:
            return file_bytes.decode("utf-8", errors="ignore")

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
        """Splits large text blocks into smaller, overlapping chunks."""
        chunks = []
        words = text.split()
        
        step = chunk_size - overlap
        for i in range(0, len(words), step):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk)
        return chunks

    def ingest_document(self, filename: str, file_bytes: bytes, session_id: str) -> str:
        """
        Extracts, chunks, embeds, and indexes a file into Qdrant.
        Stores session_id in payload metadata for scoping.
        """
        raw_text = self.extract_text_from_file(filename, file_bytes)
        chunks = self.chunk_text(raw_text)
        
        if not chunks:
            raise ValueError("No extractable text found in document.")

        points = []
        for idx, chunk in enumerate(chunks):
            point_id = str(uuid.uuid4())
            embedding = self.llm.get_embeddings(chunk)
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "filename": filename,
                        "session_id": session_id,
                        "chunk_index": idx,
                        "content": chunk
                    }
                )
            )

        self.qdrant.upsert(
            collection_name=self.collection_name,
            points=points
        )
        return f"Successfully ingested {len(chunks)} chunks from {filename} into Qdrant."

    def delete_session_vectors(self, session_id: str) -> bool:
        """Purges all indexed vector points associated with a specific session_id from Qdrant."""
        try:
            session_filter = Filter(
                must=[
                    FieldCondition(
                        key="session_id",
                        match=MatchValue(value=session_id)
                    )
                ]
            )
            self.qdrant.delete(
                collection_name=self.collection_name,
                points_selector=session_filter
            )
            return True
        except Exception as e:
            print(f"Error purging Qdrant vectors for session {session_id}: {e}")
            return False

    def delete_document_vectors(self, session_id: str, filename: str) -> bool:
        """Purges vector chunks associated with a specific file within a session from Qdrant."""
        try:
            doc_filter = Filter(
                must=[
                    FieldCondition(
                        key="session_id",
                        match=MatchValue(value=session_id)
                    ),
                    FieldCondition(
                        key="filename",
                        match=MatchValue(value=filename)
                    )
                ]
            )
            self.qdrant.delete(
                collection_name=self.collection_name,
                points_selector=doc_filter
            )
            return True
        except Exception as e:
            print(f"Error purging Qdrant vectors for file {filename} in session {session_id}: {e}")
            return False

    def query_assistant(self, query: str, session_id: str, db: Session, top_k: int = 3, score_threshold: float = 0.35) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Smart Query Routing Workflow:
        1. Fast SQL Pre-Check: Checks if any documents are attached to session_id in PostgreSQL.
           If empty, bypasses embedding calculation & Qdrant vector search entirely (0ms overhead).
        2. Relevance Thresholding: Evaluates Qdrant point similarity scores.
           If top score < score_threshold (0.35), ignores context and generates a general response.
        """
        # --- Step 1: Fast SQL Pre-Check ---
        from app.crud import rag_chat_crud
        uploaded_docs = rag_chat_crud.get_chat_documents(db, session_id)
        if not uploaded_docs:
            # Fast path: No documents attached -> Skip Qdrant search & embedding calls completely
            system_instruction = "You are a helpful personal assistant."
            answer = self.llm.generate_text(query, system_instruction=system_instruction)
            return answer, []

        # --- Step 2: Vector Search & Relevance Thresholding ---
        query_embedding = self.llm.get_embeddings(query)

        session_filter = Filter(
            must=[
                FieldCondition(
                    key="session_id",
                    match=MatchValue(value=session_id)
                )
            ]
        )

        response = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=session_filter,
            limit=top_k
        )
        results = response.points

        # Filter out points below similarity score threshold (e.g. 0.35)
        relevant_results = [p for p in results if p.score >= score_threshold]

        if not relevant_results:
            # Relevance score below threshold -> Fall back to general unconstrained LLM response
            system_instruction = "You are a helpful personal assistant."
            answer = self.llm.generate_text(query, system_instruction=system_instruction)
            return answer, []

        # --- Step 3: Grounded RAG Generation ---
        context_block = ""
        sources = []
        for point in relevant_results:
            payload = point.payload
            context_block += f"Source File: {payload['filename']}\nContent: {payload['content']}\n\n---\n\n"
            sources.append({
                "filename": payload["filename"],
                "preview": payload["content"][:150] + "..."
            })

        system_instruction = (
            "You are a helpful personal knowledge assistant. Answer the user's question "
            "using ONLY the provided Context block. Be truthful and ground your answer. "
            "If the answer cannot be found in the Context, explain that you don't know "
            "based on the uploaded documents."
        )
        
        prompt = (
            f"Context:\n{context_block}\n"
            f"User Question: {query}"
        )

        answer = self.llm.generate_text(prompt, system_instruction=system_instruction)
        return answer, sources
