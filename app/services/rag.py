# app/services/rag.py
import os
import uuid
import logging
from io import BytesIO
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, 
    FieldCondition, MatchValue, PayloadSchemaType
)

from app.services.llm import BaseLLMService
from app.services.reranker import CrossEncoderReranker
from app.services.security_filter import RAGSecurityFilterBuilder
from app.services.prompt_engine import PromptEngine
from app.parsers.factory import ParserFactory
from app.connectors.file_connector import FileConnector
from app.core.audit import AuditLogger
from app.core.security import TokenData
from app.models.enterprise_models import UserRole, AssistantPersona, PromptTemplate, Organization, Department

logger = logging.getLogger("rag_service")

class RAGService:
    # Class-level client singleton cache to prevent locking conflicts
    _qdrant_client = None
    _collection_checked = False

    def __init__(self, llm_service: BaseLLMService):
        self.llm = llm_service
        self.collection_name = os.getenv("QDRANT_COLLECTION", "assistant_knowledge")
        self.reranker = CrossEncoderReranker()
        
        # 1. Initialize client using the cached singleton
        if RAGService._qdrant_client is None:
            storage_mode = os.getenv("QDRANT_STORAGE", "server").lower()
            if storage_mode == "server":
                host = os.getenv("QDRANT_HOST", "qdrant")
                port = int(os.getenv("QDRANT_PORT", 6333))
                api_key = os.getenv("QDRANT_API_KEY", None)
                RAGService._qdrant_client = QdrantClient(host=host, port=port, api_key=api_key)
            else:
                path = os.getenv("QDRANT_PATH", "./qdrant_db")
                RAGService._qdrant_client = QdrantClient(path=path)

        self.qdrant = RAGService._qdrant_client

        # 2. Initialize database collection & payload indexes
        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        if RAGService._collection_checked:
            return
        """
        Ensures that the target collection exists in Qdrant with matching vector dimensions
        and payload indexes for fast O(1) multi-tenant & RBAC pre-filtering.
        """
        vector_dimension = int(os.getenv("EMBEDDING_DIMENSION", 768))

        if not self.qdrant.collection_exists(collection_name=self.collection_name):
            try:
                self.qdrant.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=vector_dimension, 
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection '{self.collection_name}' with dim {vector_dimension}")
            except Exception as e:
                logger.warning(f"Collection creation notice: {e}")

        # Ensure Payload Indexes for fast multi-tenant security filtering
        indexed_fields = [
            ("org_id", PayloadSchemaType.KEYWORD),
            ("department_id", PayloadSchemaType.KEYWORD),
            ("access_level", PayloadSchemaType.KEYWORD),
            ("uploader_id", PayloadSchemaType.KEYWORD),
            ("session_id", PayloadSchemaType.KEYWORD),
            ("document_id", PayloadSchemaType.KEYWORD),
        ]
        for field_name, schema_type in indexed_fields:
            try:
                self.qdrant.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema_type
                )
            except Exception:
                pass
        RAGService._collection_checked = True

    def extract_text_from_file(self, filename: str, file_bytes: bytes, mime_type: str = None) -> str:
        """Parses PDF, DOCX, TXT, MD, CSV, JSON using ParserFactory."""
        parser = ParserFactory.get_parser(filename, mime_type)
        return parser.parse(file_bytes)

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
        """Splits text blocks into smaller, overlapping chunks."""
        chunks = []
        words = text.split()
        
        step = chunk_size - overlap
        for i in range(0, len(words), step):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk)
        return chunks

    # --- Enterprise Multi-Tenant Document Ingestion ---

    def ingest_enterprise_document(
        self,
        filename: str,
        file_bytes: bytes,
        document_id: str,
        org_id: str,
        department_id: str,
        uploader_id: str,
        access_level: str,
        mime_type: str = None
    ) -> int:
        """
        Ingests enterprise documents into Qdrant with tenant, department, uploader,
        and ACL payload metadata tags for zero-leakage security filtering.
        """
        connector = FileConnector(filename=filename, content_bytes=file_bytes, mime_type=mime_type)
        raw_doc = next(connector.fetch_documents())

        raw_text = self.extract_text_from_file(raw_doc.filename, raw_doc.content_bytes, raw_doc.mime_type)
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
                        "document_id": document_id,
                        "org_id": org_id,
                        "department_id": department_id,
                        "uploader_id": uploader_id,
                        "access_level": access_level,
                        "filename": filename,
                        "chunk_index": idx,
                        "content": chunk,
                        "source_type": raw_doc.source_type
                    }
                )
            )

        self.qdrant.upsert(
            collection_name=self.collection_name,
            points=points
        )
        return len(chunks)

    # --- Legacy Session Ingestion (Backward Compatible) ---

    def ingest_document(self, filename: str, file_bytes: bytes, session_id: str, mime_type: str = None) -> str:
        """Backward-compatible ingestion for legacy flat sessions."""
        connector = FileConnector(filename=filename, content_bytes=file_bytes, mime_type=mime_type)
        raw_doc = next(connector.fetch_documents())

        raw_text = self.extract_text_from_file(raw_doc.filename, raw_doc.content_bytes, raw_doc.mime_type)
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
                        "content": chunk,
                        "source_type": raw_doc.source_type
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
            logger.error(f"Error purging Qdrant vectors for session {session_id}: {e}")
            return False

    def delete_document_vectors(self, document_id: str, org_id: str) -> bool:
        """Purges vector chunks for a specific document with org_id validation."""
        try:
            doc_filter = Filter(
                must=[
                    FieldCondition(key="org_id", match=MatchValue(value=org_id)),
                    FieldCondition(key="document_id", match=MatchValue(value=document_id))
                ]
            )
            self.qdrant.delete(
                collection_name=self.collection_name,
                points_selector=doc_filter
            )
            return True
        except Exception as e:
            logger.error(f"Error purging Qdrant vectors for document {document_id}: {e}")
            return False

    # --- Enterprise Scoped Query Execution with Persona & Template Engine ---

    def query_enterprise(
        self,
        query: str,
        user_context: TokenData,
        session_id: Optional[str],
        db: Session,
        top_k: int = 3,
        score_threshold: float = 0.30,
        persona_id: Optional[str] = None,
        template_id: Optional[str] = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Executes an enterprise RAG query:
        1. Builds unbypassable multi-tenant security filter based on user's verified token.
        2. Resolves Persona system instruction template & interpolates user/department variables.
        3. Retrieves candidate vectors strictly within org/dept/role boundary.
        4. Re-ranks candidates with FlashRank Cross-Encoder.
        5. Injects verified citations into grounded prompt (interpolated via PromptTemplate if provided).
        6. Emits compliance audit log.
        """
        org_name = ""
        dept_name = ""
        if db:
            org = db.query(Organization).filter(Organization.id == user_context.org_id).first()
            if org:
                org_name = org.name
            if user_context.department_id:
                dept = db.query(Department).filter(Department.id == user_context.department_id).first()
                if dept:
                    dept_name = dept.name

        system_template = (
            "You are a helpful enterprise knowledge assistant for {org_name}. Answer the user's question "
            "truthfully using ONLY the provided verified Context block. Cite source documents. "
            "If the answer cannot be found in the Context, state clearly that the knowledge base "
            "does not contain this information."
        )

        if persona_id and db:
            persona = db.query(AssistantPersona).filter(
                AssistantPersona.id == persona_id,
                AssistantPersona.org_id == user_context.org_id,
                AssistantPersona.is_active == True
            ).first()
            if persona:
                system_template = persona.system_instruction_template

        template_vars = {
            "user_name": user_context.email.split("@")[0],
            "user_role": user_context.role,
            "department_name": dept_name or "General",
            "org_name": org_name,
            "query": query
        }
        system_instruction = PromptEngine.render_template(system_template, template_vars)

        query_embedding = self.llm.get_embeddings(query)
        
        # Unbypassable Multi-Tenant Security Filter
        security_filter = RAGSecurityFilterBuilder.build_search_filter(
            org_id=user_context.org_id,
            department_id=user_context.department_id or "",
            user_id=user_context.user_id,
            user_role=UserRole(user_context.role),
            session_id=session_id
        )

        response = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=security_filter,
            limit=15
        )
        results = response.points

        relevant_results = [p for p in results if p.score >= score_threshold]
        if not relevant_results:
            answer = self.llm.generate_text(query, system_instruction=system_instruction)
            return answer, []

        candidate_chunks = [
            {
                "id": str(p.id),
                "text": p.payload["content"],
                "payload": p.payload,
                "vector_score": p.score
            }
            for p in relevant_results
        ]

        reranked_chunks = self.reranker.rerank(query=query, candidate_chunks=candidate_chunks, top_n=top_k)

        context_block = ""
        sources = []
        retrieved_doc_ids = []
        for chunk in reranked_chunks:
            payload = chunk["meta"]
            doc_id = payload.get("document_id", "unknown")
            retrieved_doc_ids.append(doc_id)
            context_block += f"Document: {payload['filename']} [Dept: {payload.get('department_id', 'General')}]\nContent: {chunk['text']}\n\n---\n\n"
            sources.append({
                "filename": payload["filename"],
                "document_id": doc_id,
                "department_id": payload.get("department_id"),
                "access_level": payload.get("access_level"),
                "preview": chunk["text"][:150] + "...",
                "relevance_score": float(chunk.get("score", 0.0))
            })

        user_prompt_str = f"Context:\n{context_block}\n\nUser Question: {query}"
        if template_id and db:
            p_template = db.query(PromptTemplate).filter(
                PromptTemplate.id == template_id,
                PromptTemplate.org_id == user_context.org_id,
                PromptTemplate.is_active == True
            ).first()
            if p_template:
                template_vars["context"] = context_block
                user_prompt_str = PromptEngine.render_template(p_template.user_prompt_template, template_vars)

        answer = self.llm.generate_text(user_prompt_str, system_instruction=system_instruction)

        AuditLogger.log(
            db=db,
            org_id=user_context.org_id,
            user_id=user_context.user_id,
            action="ENTERPRISE_RAG_QUERY",
            resource_type="CHAT_QUERY",
            resource_id=session_id,
            details={
                "query": query[:200],
                "persona_id": persona_id,
                "template_id": template_id,
                "retrieved_documents": retrieved_doc_ids,
                "sources_count": len(sources)
            }
        )

        return answer, sources

    # --- Legacy Session Query (Backward Compatible) ---

    def query_assistant(self, query: str, session_id: str, db: Session, top_k: int = 3, score_threshold: float = 0.35) -> Tuple[str, List[Dict[str, Any]]]:
        """Backward-compatible query for legacy flat sessions."""
        from app.crud import rag_chat_crud
        uploaded_docs = rag_chat_crud.get_chat_documents(db, session_id)
        if not uploaded_docs:
            system_instruction = "You are a helpful personal assistant."
            answer = self.llm.generate_text(query, system_instruction=system_instruction)
            return answer, []

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
            limit=15
        )
        results = response.points

        relevant_results = [p for p in results if p.score >= score_threshold]
        if not relevant_results:
            system_instruction = "You are a helpful personal assistant."
            answer = self.llm.generate_text(query, system_instruction=system_instruction)
            return answer, []

        candidate_chunks = [
            {
                "id": str(p.id),
                "text": p.payload["content"],
                "payload": p.payload,
                "vector_score": p.score
            }
            for p in relevant_results
        ]

        reranked_chunks = self.reranker.rerank(query=query, candidate_chunks=candidate_chunks, top_n=top_k)

        context_block = ""
        sources = []
        for chunk in reranked_chunks:
            payload = chunk["meta"]
            context_block += f"Source File: {payload['filename']}\nContent: {chunk['text']}\n\n---\n\n"
            sources.append({
                "filename": payload["filename"],
                "preview": chunk["text"][:150] + "...",
                "relevance_score": float(chunk.get("score", 0.0))
            })

        system_instruction = (
            "You are a helpful personal knowledge assistant. Answer the user's question "
            "using ONLY the provided Context block. Be truthful and ground your answer."
        )
        
        prompt = f"Context:\n{context_block}\n\nUser Question: {query}"
        answer = self.llm.generate_text(prompt, system_instruction=system_instruction)
        return answer, sources
