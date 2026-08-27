# benchmarking/test_tabular_ingestion.py
import io
import os
import sys
import uuid
import openpyxl

BASE_DIR = "/home/techyz-admin/sevenwings/03_learning/26-08-10-ai-system/multi-tenant-rag-system"
sys.path.insert(0, BASE_DIR)

from core.database import SessionLocal
from modules.auth.domain.tokens import TokenData
from modules.auth.domain.models import User, Organization, Department, UserRole, AccessLevel
from modules.governance.domain.models import EnterpriseDocument
from modules.connectors.parsers.factory import ParserFactory
from modules.connectors.parsers.tabular_parser import TabularParser
from modules.rag_core.orchestrator.unified_orchestrator import UnifiedRAGOrchestrator

def create_mock_rate_card_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Commercial Rates"

    # Header Row
    headers = ["Role / Designation", "Experience Level", "Standard Rate (Hourly)", "Day Rate (8 Hours)", "Overtime Rate"]
    ws.append(headers)

    # Data Rows
    rows = [
        ["Intern / Trainee", "Level 0", "8,000 NGN/hour", "64,000 NGN", "12,000 NGN/hour"],
        ["Junior Engineer / Analyst", "Level 1-2", "18,000 NGN/hour", "144,000 NGN", "27,000 NGN/hour"],
        ["Senior Engineer / Consultant", "Level 3-4", "35,000 NGN/hour", "280,000 NGN", "52,500 NGN/hour"],
        ["Principal Architect / Lead", "Level 5", "60,000 NGN/hour", "480,000 NGN", "90,000 NGN/hour"]
    ]
    for r in rows:
        ws.append(r)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def create_mock_csv() -> bytes:
    csv_text = (
        "Department,Travel Allowance,Hazard Allowance,Remote Stipend\n"
        "Finance,50000 NGN/mo,10000 NGN/mo,30000 NGN/mo\n"
        "Engineering,75000 NGN/mo,25000 NGN/mo,45000 NGN/mo\n"
    )
    return csv_text.encode("utf-8")

def run_tabular_tests():
    print("Testing Tabular Ingestion (.xlsx / .csv) & Semantic Row Retrieval...")
    db = SessionLocal()
    orchestrator = UnifiedRAGOrchestrator()

    try:
        # 1. Test Parser Factory Registration
        xlsx_parser = ParserFactory.get_parser("Rate Card 2025.xlsx")
        assert isinstance(xlsx_parser, TabularParser), f"Expected TabularParser, got {type(xlsx_parser)}"
        csv_parser = ParserFactory.get_parser("allowances.csv")
        assert isinstance(csv_parser, TabularParser), f"Expected TabularParser, got {type(csv_parser)}"
        print("  [PASS] ParserFactory correctly resolves TabularParser for .xlsx and .csv.")

        # 2. Test Tabular Parsing & Semantic Row Serialization
        xlsx_bytes = create_mock_rate_card_xlsx()
        parsed_text = xlsx_parser.parse(xlsx_bytes)
        assert "### [Spreadsheet Table - Sheet: Commercial Rates]" in parsed_text
        assert "Junior Engineer / Analyst" in parsed_text
        assert "18,000 NGN/hour" in parsed_text
        assert "[Sheet: Commercial Rates | Row 2]" in parsed_text
        print("  [PASS] TabularParser successfully serializes Excel rows into structured Key-Value records.")

        # 3. Test Tabular-Aware Chunking
        chunks = orchestrator.chunk_text(parsed_text)
        assert len(chunks) >= 1
        assert "Columns: Role / Designation" in chunks[0]
        assert "Junior Engineer / Analyst" in chunks[0]
        print(f"  [PASS] Tabular chunking preserved header context across {len(chunks)} chunks.")

        # 4. Setup Test Organization & Departments
        org = db.query(Organization).filter(Organization.slug == "test-tabular-org").first()
        if not org:
            org = Organization(id=str(uuid.uuid4()), name="Bluesources Test Tenant", slug="test-tabular-org")
            db.add(org)
            db.commit()

        dept_finance = db.query(Department).filter(Department.org_id == org.id, Department.slug == "finance").first()
        if not dept_finance:
            dept_finance = Department(id=str(uuid.uuid4()), org_id=org.id, name="Finance Department", slug="finance")
            db.add(dept_finance)
            db.commit()

        dept_eng = db.query(Department).filter(Department.org_id == org.id, Department.slug == "eng").first()
        if not dept_eng:
            dept_eng = Department(id=str(uuid.uuid4()), org_id=org.id, name="Engineering Department", slug="eng")
            db.add(dept_eng)
            db.commit()

        # 5. Ingest Rate Card .xlsx scoped to Finance Department
        doc_id = str(uuid.uuid4())
        chunk_count = orchestrator.ingest_document(
            filename="Rate_Card_2025.xlsx",
            file_bytes=xlsx_bytes,
            document_id=doc_id,
            org_id=org.id,
            department_id=dept_finance.id,
            uploader_id=None,
            access_level="DEPARTMENT",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        print(f"  [PASS] Successfully ingested Rate_Card_2025.xlsx ({chunk_count} chunks indexed in Qdrant).")

        # 6. Test User A: Finance Member querying Rate Card
        finance_user = TokenData(
            user_id=str(uuid.uuid4()),
            email="finance_analyst@bluesources.local",
            org_id=org.id,
            department_id=dept_finance.id,
            role="MEMBER"
        )

        query = "What is the payment rate for a Junior Engineer / Analyst, at level 1?"
        answer, sources, is_grounded, confidence = orchestrator.execute_unified_query(
            query=query,
            user_context=finance_user,
            db=db,
            mode="auto"
        )

        print(f"\n  --- Finance User Query Execution ---")
        print(f"  Query: {query}")
        print(f"  Grounded: {is_grounded} | Confidence: {confidence}")
        print(f"  Sources Count: {len(sources)}")
        for s in sources:
            print(f"    Source: {s['filename']} (score={s['relevance_score']}) -> {s['preview']}")
        print(f"  Answer Preview:\n{answer}\n")

        assert len(sources) > 0, "Finance user should retrieve Rate Card sources!"
        assert "18,000" in answer or "18000" in answer, f"Answer should contain the 18,000 NGN rate, got: {answer}"
        print("  [PASS] User A (Finance) retrieved exact 18,000 NGN/hour rate from indexed spreadsheet.")

        # 7. Test User B: Engineering Member querying Rate Card (RBAC Test)
        eng_user = TokenData(
            user_id=str(uuid.uuid4()),
            email="engineer_dev@bluesources.local",
            org_id=org.id,
            department_id=dept_eng.id,
            role="MEMBER"
        )

        answer_eng, sources_eng, is_grounded_eng, _ = orchestrator.execute_unified_query(
            query=query,
            user_context=eng_user,
            db=db,
            mode="rag"  # Strict RAG mode
        )

        print(f"  --- Engineering User RBAC Test ---")
        print(f"  Sources retrieved by Engineering user: {len(sources_eng)}")
        assert len(sources_eng) == 0, "Engineering user must NOT access Finance-confidential Rate Card!"
        print("  [PASS] User B (Engineering) correctly isolated by RBAC departmental boundaries.")

        # 8. Clean up test vectors & DB records
        orchestrator.delete_document_vectors(doc_id, org.id)
        db.delete(dept_finance)
        db.delete(dept_eng)
        db.delete(org)
        db.commit()
        print("  [OK] Cleaned up test records.")

        print("\n=======================================================")
        print("ALL TABULAR INGESTION & SEMANTIC RETRIEVAL TESTS PASSED!")
        print("=======================================================")

    finally:
        db.close()

if __name__ == "__main__":
    run_tabular_tests()
