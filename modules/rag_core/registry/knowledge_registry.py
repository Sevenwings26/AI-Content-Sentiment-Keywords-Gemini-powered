# modules/rag_core/registry/knowledge_registry.py
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from modules.auth.domain.tokens import TokenData

logger = logging.getLogger("knowledge_registry")

@dataclass
class KnowledgeSourceDescriptor:
    source_id: str
    name: str
    description: str
    scope_type: str  # "personal", "department", "enterprise", "connector"
    required_roles: List[str] = field(default_factory=lambda: ["MEMBER", "DEPT_ADMIN", "SUPER_ADMIN", "AUDITOR"])
    connector_type: str = "vector_qdrant"
    is_active: bool = True

class KnowledgeRegistry:
    def __init__(self):
        self._sources: Dict[str, KnowledgeSourceDescriptor] = {}
        self._register_default_sources()

    def _register_default_sources(self):
        self.register_source(
            KnowledgeSourceDescriptor(
                source_id="personal_docs",
                name="Personal Workspace Documents",
                description="Documents uploaded directly by the user or attached to the current session",
                scope_type="personal",
                required_roles=["MEMBER", "DEPT_ADMIN", "SUPER_ADMIN"]
            )
        )
        self.register_source(
            KnowledgeSourceDescriptor(
                source_id="department_kb",
                name="Department Knowledge Base",
                description="Functional department documentation, wikis, and technical runbooks",
                scope_type="department",
                required_roles=["MEMBER", "DEPT_ADMIN", "SUPER_ADMIN"]
            )
        )
        self.register_source(
            KnowledgeSourceDescriptor(
                source_id="enterprise_policies",
                name="Enterprise Organization Knowledge",
                description="Company-wide policies, employee guidelines, standard operating procedures",
                scope_type="enterprise",
                required_roles=["MEMBER", "DEPT_ADMIN", "SUPER_ADMIN", "AUDITOR"]
            )
        )

    def register_source(self, descriptor: KnowledgeSourceDescriptor):
        self._sources[descriptor.source_id] = descriptor
        logger.info(f"Registered knowledge source: {descriptor.source_id} ({descriptor.name})")

    def list_accessible_sources(self, user_context: TokenData, requested_scopes: Optional[List[str]] = None) -> List[KnowledgeSourceDescriptor]:
        scopes = requested_scopes or ["personal", "department", "enterprise"]
        accessible = []

        for source in self._sources.values():
            if not source.is_active:
                continue
            if source.scope_type not in scopes:
                continue
            if user_context.role not in source.required_roles:
                continue
            accessible.append(source)

        return accessible
