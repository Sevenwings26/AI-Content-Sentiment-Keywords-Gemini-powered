# benchmarking/test_session_isolation.py
import sys
import os
import uuid

BASE_DIR = "/home/techyz-admin/sevenwings/03_learning/26-08-10-ai-system/multi-tenant-rag-system"
sys.path.insert(0, BASE_DIR)

from core.database import SessionLocal
from modules.auth.domain.models import User, Organization, Department, UserRole
from modules.auth.services.token_service import get_password_hash
from modules.governance.repositories.chat_repository import ChatRepository
from modules.governance.domain.models import ChatSession

db = SessionLocal()

try:
    print("Testing Strict Session Isolation & Multi-Tenant Boundaries...")

    # 1. Setup Test Organizations and Users
    org1 = db.query(Organization).filter(Organization.slug == "test-isolation-org").first()
    if not org1:
        org1 = Organization(id=str(uuid.uuid4()), name="Test Isolation Org", slug="test-isolation-org")
        db.add(org1)
        db.commit()

    admin_user = User(
        id=str(uuid.uuid4()),
        org_id=org1.id,
        email=f"admin_{uuid.uuid4().hex[:6]}@test.local",
        hashed_password=get_password_hash("password123"),
        role=UserRole.SUPER_ADMIN,
        full_name="Test Admin"
    )
    member_user = User(
        id=str(uuid.uuid4()),
        org_id=org1.id,
        email=f"member_{uuid.uuid4().hex[:6]}@test.local",
        hashed_password=get_password_hash("password123"),
        role=UserRole.MEMBER,
        full_name="Test Member"
    )
    db.add(admin_user)
    db.add(member_user)
    db.commit()

    # 2. Simulate Guest creating a chat session
    guest_session = ChatRepository.get_or_create_session(
        db=db,
        session_id=None,
        org_id=org1.id,
        user_id=None,
        title="Guest Secret Chat"
    )
    ChatRepository.add_message(db, session_id=guest_session.id, role="user", content="Guest confidential prompt")
    print(f"  [OK] Guest Session Created: {guest_session.id}")

    # 3. Simulate Guest listing sessions -> MUST BE EMPTY
    guest_sessions_list = ChatRepository.list_user_sessions(db, org_id=org1.id, user_id=None)
    assert len(guest_sessions_list) == 0, f"Expected 0 guest sessions listed, got {len(guest_sessions_list)}"
    print("  [PASS] Guest session listing is isolated (returns 0 historical sessions).")

    # 4. Simulate Enterprise Admin listing sessions -> MUST NOT CONTAIN GUEST SESSION
    admin_sessions_before = ChatRepository.list_user_sessions(db, org_id=org1.id, user_id=admin_user.id)
    assert len(admin_sessions_before) == 0, "Admin should have 0 sessions before creating any"
    print("  [PASS] Admin does NOT see guest session in sidebar.")

    # 5. Simulate Enterprise Member listing sessions -> MUST NOT CONTAIN GUEST SESSION
    member_sessions_before = ChatRepository.list_user_sessions(db, org_id=org1.id, user_id=member_user.id)
    assert len(member_sessions_before) == 0, "Member should have 0 sessions before creating any"
    print("  [PASS] Regular Member does NOT see guest session in sidebar.")

    # 6. Admin creates their own chat session
    admin_session = ChatRepository.get_or_create_session(
        db=db,
        session_id=None,
        org_id=org1.id,
        user_id=admin_user.id,
        title="Admin Executive Strategy"
    )
    print(f"  [OK] Admin Session Created: {admin_session.id}")

    # 7. Member creates their own chat session
    member_session = ChatRepository.get_or_create_session(
        db=db,
        session_id=None,
        org_id=org1.id,
        user_id=member_user.id,
        title="Member Project Discussion"
    )
    print(f"  [OK] Member Session Created: {member_session.id}")

    # 8. Verify Admin sees ONLY Admin session
    admin_sessions_after = ChatRepository.list_user_sessions(db, org_id=org1.id, user_id=admin_user.id)
    assert len(admin_sessions_after) == 1
    assert admin_sessions_after[0].id == admin_session.id
    print("  [PASS] Admin sees strictly their own session.")

    # 9. Verify Member sees ONLY Member session
    member_sessions_after = ChatRepository.list_user_sessions(db, org_id=org1.id, user_id=member_user.id)
    assert len(member_sessions_after) == 1
    assert member_sessions_after[0].id == member_session.id
    print("  [PASS] Member sees strictly their own session.")

    # 10. Clean up test records
    ChatRepository.delete_session(db, guest_session.id, org1.id)
    ChatRepository.delete_session(db, admin_session.id, org1.id)
    ChatRepository.delete_session(db, member_session.id, org1.id)
    db.delete(admin_user)
    db.delete(member_user)
    db.commit()
    print("  [OK] Cleaned up test records.")

    print("\n=======================================================")
    print("ALL SESSION ISOLATION & AUTHORIZATION TESTS PASSED!")
    print("=======================================================")

finally:
    db.close()
