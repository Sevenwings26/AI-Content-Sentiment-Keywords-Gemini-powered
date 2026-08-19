# app/services/security_filter.py
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
from typing import Optional

from app.models.enterprise_models import UserRole, AccessLevel

class RAGSecurityFilterBuilder:
    @staticmethod
    def build_search_filter(
        org_id: str,
        department_id: str,
        user_id: str,
        user_role: UserRole,
        session_id: Optional[str] = None
    ) -> Filter:
        """
        Constructs a mathematically strict zero-leakage security filter:
        Rule 1: org_id MUST match exactly (Cross-tenant boundary).
        Rule 2: User can access:
           - PUBLIC documents within their Org.
           - DEPARTMENT documents matching their Department.
           - CONFIDENTIAL documents IF user is DeptAdmin or SuperAdmin.
           - RESTRICTED documents matching their specific user_id or active session_id.
        """
        # Base Tenant Isolation Constraint (Non-negotiable)
        must_conditions = [
            FieldCondition(key="org_id", match=MatchValue(value=org_id))
        ]

        # Role-Based Permission Clauses
        should_access_clauses = [
            # 1. Any Public document in the Organization
            FieldCondition(key="access_level", match=MatchValue(value=AccessLevel.PUBLIC.value)),
            
            # 2. Any Standard Department Document matching user's department
            Filter(
                must=[
                    FieldCondition(key="department_id", match=MatchValue(value=department_id)),
                    FieldCondition(key="access_level", match=MatchValue(value=AccessLevel.DEPARTMENT.value))
                ]
            ),
            
            # 3. User's Own Uploaded / Private Documents
            FieldCondition(key="uploader_id", match=MatchValue(value=user_id))
        ]

        # 4. Confidential Access (Admins only)
        if user_role in [UserRole.SUPER_ADMIN, UserRole.DEPT_ADMIN]:
            should_access_clauses.append(
                Filter(
                    must=[
                        FieldCondition(key="department_id", match=MatchValue(value=department_id)),
                        FieldCondition(key="access_level", match=MatchValue(value=AccessLevel.CONFIDENTIAL.value))
                    ]
                )
            )

        # 5. Session Scope (if querying within an isolated session)
        if session_id:
            should_access_clauses.append(
                FieldCondition(key="session_id", match=MatchValue(value=session_id))
            )

        return Filter(
            must=must_conditions,
            should=should_access_clauses
        )
