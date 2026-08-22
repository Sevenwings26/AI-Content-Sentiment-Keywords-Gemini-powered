# benchmarking/test_guest_chat_flow.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.rag_core.retrieval.security_filter import RAGSecurityFilterBuilder
from modules.auth.domain.models import UserRole
from modules.auth.domain.tokens import TokenData
from modules.rag_core.guardrails.grounding_validator import GroundingValidator

def test_guest_security_filter():
    print('Testing guest search filter creation...')
    # Test unauthenticated user (user_id=None, department_id=None, session_id=None)
    qdrant_filter = RAGSecurityFilterBuilder.build_search_filter(
        org_id='default-org-uuid',
        department_id=None,
        user_id=None,
        user_role=UserRole.MEMBER,
        session_id=None,
        scope=None
    )
    print(f'  [PASS] Successfully created guest Qdrant Filter: {qdrant_filter}')

    # Test personal scope with guest session_id
    personal_filter = RAGSecurityFilterBuilder.build_search_filter(
        org_id='default-org-uuid',
        department_id=None,
        user_id=None,
        user_role=UserRole.MEMBER,
        session_id='session-uuid-123',
        scope='personal'
    )
    print(f'  [PASS] Successfully created personal guest session Filter: {personal_filter}')

    # Test general query grounding response
    ans, sources, is_grounded, conf = GroundingValidator.get_out_of_context_response(
        'How many continents exist?', org_name='Default Workspace'
    )
    assert not is_grounded
    print(f'  [PASS] GroundingValidator returned clean fallback: {ans[:80]}...')
    print('\nALL GUEST FLOW TESTS PASSED!')

if __name__ == '__main__':
    test_guest_security_filter()
