# modules/rag_core/guardrails/grounding_validator.py
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger("grounding_validator")

class GroundingValidator:
    STRICT_SYSTEM_INSTRUCTION = (
        "You are an enterprise AI knowledge assistant for {{ org_name }}. "
        "Your task is to provide accurate, grounded answers strictly based on the supplied context documents. "
        "Rules:\n"
        "1. Every factual assertion must be directly supported by the context snippets.\n"
        "2. If the context does not contain sufficient information to answer the question, explicitly state "
        "'Based on the available organizational documents, I could not find information regarding [topic].'\n"
        "3. Do not extrapolate, speculate, or utilize external world knowledge beyond what is grounded.\n"
        "4. Always cite specific document names and sections where appropriate."
    )

    ADAPTIVE_SYSTEM_INSTRUCTION = (
        "You are an intelligent Enterprise AI Knowledge & Cognitive Assistant for {{ org_name }}.\n"
        "Your objective is to provide comprehensive, accurate, and properly grounded responses following these dual-mode synthesis rules:\n\n"
        "1. STRICT INTERNAL GROUNDING:\n"
        "   - All statements, procedures, metrics, personnel details, and policies specific to {{ org_name }} or its departments MUST be derived strictly from the provided [Context Sources] and accurately cited (e.g. [Source 1: filename]).\n"
        "   - If internal organizational details or company-specific policies are requested but absent from the context, explicitly state that internal organizational records do not specify that detail.\n\n"
        "2. DIFFERENTIATED EXTERNAL / GENERAL KNOWLEDGE SYNTHESIS:\n"
        "   - When the user asks for broader definitions, statutory laws (e.g., national labor acts), global/industry standards, general comparisons, or open-domain concepts alongside or beyond organizational documents, you SHOULD draw upon your general parametric knowledge to provide a helpful, accurate answer.\n"
        "   - You MUST clearly differentiate between internal organizational facts and external general knowledge (e.g., 'According to {{ org_name }}\'s internal policy [Source 1]... whereas under general statutory labor standards...').\n\n"
        "3. INTEGRITY & CITATIONS:\n"
        "   - Never misattribute external world knowledge to the internal context documents, and never invent internal company facts not present in the context."
    )

    @classmethod
    def format_grounded_context(cls, retrieved_chunks: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
        if not retrieved_chunks:
            return "", []

        context_blocks = []
        sources = []

        for idx, chunk in enumerate(retrieved_chunks, 1):
            filename = chunk.get("filename", "Unknown Document")
            content = chunk.get("content", "").strip()
            score = chunk.get("rerank_score", chunk.get("vector_score", 0.0))

            context_blocks.append(f"[Source {idx}: {filename}]\n{content}\n")
            sources.append({
                "source_id": str(idx),
                "filename": filename,
                "document_id": chunk.get("document_id"),
                "department_id": chunk.get("department_id"),
                "access_level": chunk.get("access_level"),
                "preview": content[:160] + ("..." if len(content) > 160 else ""),
                "relevance_score": round(float(score), 4),
                "source_type": chunk.get("source_type", "file")
            })

        return "\n".join(context_blocks), sources

    @classmethod
    def validate_grounding(cls, answer: str, sources: List[Dict[str, Any]]) -> Tuple[bool, float]:
        if not sources:
            return False, 0.0

        refusal_phrases = [
            "the system does not contain records matching",
            "could not find any records in the knowledge base"
        ]

        lower_answer = answer.lower()
        for phrase in refusal_phrases:
            if phrase in lower_answer:
                return False, 0.0

        top_score = sources[0].get("relevance_score", 0.5) if sources else 0.5
        confidence = min(max(top_score, 0.5), 1.0)
        return True, confidence

    @classmethod
    def get_out_of_context_response(cls, query: str, org_name: str = "your organization") -> Tuple[str, List[Dict[str, Any]], bool, float]:
        response = (
            f"Based on the authorized knowledge repositories of {org_name}, "
            f"the system does not contain records matching your query: '{query}'.\n\n"
            f"Please verify your query keywords or consult your department administrator for access clearance."
        )
        return response, [], False, 0.0
