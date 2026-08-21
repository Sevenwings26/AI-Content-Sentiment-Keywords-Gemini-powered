# modules/rag_core/guardrails/grounding_validator.py
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger("grounding_validator")

class GroundingValidator:
    STRICT_SYSTEM_INSTRUCTION = (
        "You are an enterprise AI knowledge assistant. "
        "Your task is to provide accurate, grounded answers strictly based on the supplied context documents. "
        "Rules:\n"
        "1. Every factual assertion must be directly supported by the context snippets.\n"
        "2. If the context does not contain sufficient information to answer the question, explicitly state "
        "'Based on the available organizational documents, I could not find information regarding [topic].'\n"
        "3. Do not extrapolate, speculate, or utilize external world knowledge beyond what is grounded.\n"
        "4. Always cite specific document names and sections where appropriate."
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

        uncertain_phrases = [
            "could not find",
            "not mentioned in the documents",
            "no information available",
            "based on the available organizational documents, i could not",
            "the provided context does not"
        ]

        lower_answer = answer.lower()
        for phrase in uncertain_phrases:
            if phrase in lower_answer:
                return False, 0.1

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
