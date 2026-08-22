# modules/rag_core/orchestrator/unified_orchestrator.py
import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from core.config import settings
from modules.auth.domain.tokens import TokenData
from modules.auth.domain.models import UserRole, Organization, Department
from modules.governance.domain.models import AssistantPersona, PromptTemplate, EnterpriseDocument
from modules.governance.services.audit_logger import AuditLogger
from modules.connectors.parsers.factory import ParserFactory
from modules.connectors.sources.file_connector import FileConnector
from modules.rag_core.providers.llm import BaseLLMService, LLMFactory
from modules.rag_core.retrieval.vector_store import VectorStoreService
from modules.rag_core.retrieval.security_filter import RAGSecurityFilterBuilder
from modules.rag_core.retrieval.hybrid_retriever import HybridRetriever
from modules.rag_core.retrieval.reranker import CrossEncoderReranker
from modules.rag_core.guardrails.grounding_validator import GroundingValidator
from modules.rag_core.guardrails.prompt_engine import PromptEngine
from modules.rag_core.registry.knowledge_registry import KnowledgeRegistry
from modules.rag_core.orchestrator.query_planner import QueryPlanner
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

logger = logging.getLogger("unified_rag_orchestrator")

class UnifiedRAGOrchestrator:
    def __init__(
        self,
        llm_service: Optional[BaseLLMService] = None,
        vector_store: Optional[VectorStoreService] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        knowledge_registry: Optional[KnowledgeRegistry] = None
    ):
        self.llm = llm_service or LLMFactory.get_provider()
        self.vector_store = vector_store or VectorStoreService()
        self.reranker = reranker or CrossEncoderReranker()
        self.registry = knowledge_registry or KnowledgeRegistry()
        self.hybrid_retriever = HybridRetriever(vector_store=self.vector_store, llm_service=self.llm)
        self.grounding_validator = GroundingValidator()
        self.prompt_engine = PromptEngine()

    def execute_unified_query(
        self,
        query: str,
        user_context: TokenData,
        db: Optional[Session] = None,
        session_id: Optional[str] = None,
        scope: Optional[str] = None,
        persona_id: Optional[str] = None,
        template_id: Optional[str] = None,
        top_k: int = 3,
        score_threshold: float = 0.35,
        mode: str = "auto"
    ) -> Tuple[str, List[Dict[str, Any]], bool, float]:
        # 1. Resolve Organization & Department Names
        org_name = "Enterprise"
        dept_name = "General"
        has_session_documents = False

        if db:
            org = db.query(Organization).filter(Organization.id == user_context.org_id).first()
            if org:
                org_name = org.name
            if user_context.department_id:
                dept = db.query(Department).filter(Department.id == user_context.department_id).first()
                if dept:
                    dept_name = dept.name
            if session_id:
                # Check if documents were uploaded to this session or org
                doc_count = db.query(EnterpriseDocument).filter(
                    EnterpriseDocument.org_id == user_context.org_id
                ).count()
                has_session_documents = (doc_count > 0)

        # 2. Analyze Query Intent & Plan Execution
        plan = QueryPlanner.analyze_and_plan(
            query=query,
            user_context=user_context,
            has_session_documents=has_session_documents,
            mode=mode
        )

        # 3. Resolve System Instruction & Temperature
        system_template = self.grounding_validator.STRICT_SYSTEM_INSTRUCTION
        temperature = 0.2

        if persona_id and db:
            persona = db.query(AssistantPersona).filter(
                AssistantPersona.id == persona_id,
                AssistantPersona.org_id == user_context.org_id,
                AssistantPersona.is_active == True
            ).first()
            if persona:
                system_template = persona.system_instruction_template
                temperature = persona.temperature / 10.0 if persona.temperature > 1 else persona.temperature

        template_vars = {
            "user_name": user_context.email.split("@")[0] if user_context.email else "User",
            "user_role": user_context.role,
            "department_name": dept_name,
            "org_name": org_name,
            "query": query
        }

        # --- ROUTE A: Conversational / General Knowledge ---
        if plan.is_conversational_only:
            logger.info(f"Query routed to General/Conversational handler (intent: {plan.intent_category}).")
            general_instruction = (
                f"You are a helpful and knowledgeable AI assistant for {org_name}. "
                "Answer the user's question clearly, politely, and accurately using your general knowledge."
            )
            if persona_id:
                general_instruction = self.prompt_engine.render_template(system_template, template_vars)

            answer = self.llm.generate_text(
                query,
                system_instruction=general_instruction,
                temperature=max(temperature, 0.5)
            )

            if db:
                AuditLogger.log(
                    db=db,
                    org_id=user_context.org_id,
                    user_id=user_context.user_id,
                    action="GENERAL_CHAT_QUERY",
                    resource_type="CHAT_QUERY",
                    resource_id=session_id,
                    details={"query": query[:200], "intent": plan.intent_category}
                )

            return answer, [], True, 1.0

        # --- ROUTE B: Document-Grounded RAG Pipeline ---
        system_instruction = self.prompt_engine.render_template(system_template, template_vars)

        user_role_enum = UserRole(user_context.role) if hasattr(UserRole, user_context.role) else UserRole.MEMBER
        security_filter = RAGSecurityFilterBuilder.build_search_filter(
            org_id=user_context.org_id,
            department_id=user_context.department_id,
            user_id=user_context.user_id,
            user_role=user_role_enum,
            session_id=session_id,
            scope=scope
        )

        candidate_chunks = self.hybrid_retriever.retrieve(
            query=query,
            security_filter=security_filter,
            candidate_limit=settings.DEFAULT_CANDIDATE_LIMIT,
            score_threshold=score_threshold
        )

        # Fallback if no relevant documents found
        if not candidate_chunks:
            logger.info(f"Query '{query[:50]}' had no chunks above threshold {score_threshold}.")
            if mode == "rag":
                # Strict out-of-context response in explicit RAG mode
                return self.grounding_validator.get_out_of_context_response(query, org_name)
            else:
                # In Auto mode, fallback to general LLM response with polite notice
                general_fallback_instruction = (
                    f"You are an AI assistant for {org_name}. Answer the user query accurately using general knowledge."
                )
                answer = self.llm.generate_text(
                    query,
                    system_instruction=general_fallback_instruction,
                    temperature=0.6
                )
                return answer, [], False, 0.0

        reranked_chunks = self.reranker.rerank(
            query=query,
            candidate_chunks=candidate_chunks,
            top_n=top_k
        )

        context_block, sources = self.grounding_validator.format_grounded_context(reranked_chunks)

        user_prompt_str = f"Context:\n{context_block}\n\nUser Question: {query}"
        if template_id and db:
            p_template = db.query(PromptTemplate).filter(
                PromptTemplate.id == template_id,
                PromptTemplate.org_id == user_context.org_id,
                PromptTemplate.is_active == True
            ).first()
            if p_template:
                template_vars["context"] = context_block
                user_prompt_str = self.prompt_engine.render_template(p_template.user_prompt_template, template_vars)

        answer = self.llm.generate_text(
            user_prompt_str,
            system_instruction=system_instruction,
            temperature=temperature
        )

        is_grounded, confidence = self.grounding_validator.validate_grounding(answer, sources)

        if db:
            AuditLogger.log(
                db=db,
                org_id=user_context.org_id,
                user_id=user_context.user_id,
                action="UNIFIED_RAG_QUERY",
                resource_type="CHAT_QUERY",
                resource_id=session_id,
                details={
                    "query": query[:200],
                    "persona_id": persona_id,
                    "template_id": template_id,
                    "sources_count": len(sources),
                    "is_grounded": is_grounded,
                    "confidence": confidence
                }
            )

        return answer, sources, is_grounded, confidence

    def extract_text_from_file(self, filename: str, file_bytes: bytes, mime_type: Optional[str] = None) -> str:
        parser = ParserFactory.get_parser(filename, mime_type)
        return parser.parse(file_bytes)

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
        chunks = []
        words = text.split()
        step = max(chunk_size - overlap, 1)
        for i in range(0, len(words), step):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk)
        return chunks

    def ingest_document(
        self,
        filename: str,
        file_bytes: bytes,
        document_id: str,
        org_id: str,
        department_id: Optional[str] = None,
        uploader_id: Optional[str] = None,
        access_level: str = "DEPARTMENT",
        session_id: Optional[str] = None,
        mime_type: Optional[str] = None
    ) -> int:
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

            payload = {
                "document_id": document_id,
                "org_id": org_id,
                "department_id": department_id or "",
                "uploader_id": uploader_id or "",
                "access_level": access_level,
                "session_id": session_id or "",
                "filename": filename,
                "chunk_index": idx,
                "content": chunk,
                "source_type": raw_doc.source_type
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
            )

        self.vector_store.upsert_chunks(points)
        return len(chunks)

    def delete_session_vectors(self, session_id: str) -> bool:
        doc_filter = Filter(
            must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
        )
        return self.vector_store.delete_by_filter(doc_filter)

    def delete_document_vectors(self, document_id: str, org_id: str) -> bool:
        doc_filter = Filter(
            must=[
                FieldCondition(key="org_id", match=MatchValue(value=org_id)),
                FieldCondition(key="document_id", match=MatchValue(value=document_id))
            ]
        )
        return self.vector_store.delete_by_filter(doc_filter)
