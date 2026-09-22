"""
Integration tests for FastAPI Authentication, User Quotas, and Admin API
========================================================================
Validates /api/auth, /api/user/*, and /api/admin/* endpoints using TestClient.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import app
from src.db import MASTER_ADMIN_PASSWORD, init_db


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_auth_master_admin(client):
    res = client.post("/api/auth", data={"password": MASTER_ADMIN_PASSWORD})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["is_admin"] is True
    assert data["report_limit"] == -1


def test_auth_demo_tester(client):
    res = client.post("/api/auth", data={"password": "TEST-LAW-2026"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["is_admin"] is False
    assert data["report_limit"] == 5


def test_auth_invalid_passcode(client):
    res = client.post("/api/auth", data={"password": "WRONG_PASSCODE_XYZ"})
    assert res.status_code == 401


def test_user_info_and_reports(client):
    res = client.get("/api/user/info?passcode=TEST-LAW-2026")
    assert res.status_code == 200
    assert res.json()["label"] == "Beta Policy Tester"

    res = client.get("/api/user/reports?passcode=TEST-LAW-2026")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_admin_endpoints_authorization(client):
    # Non-admin rejected
    res = client.get("/api/admin/passcodes?admin_passcode=TEST-LAW-2026")
    assert res.status_code == 403

    # Admin accepted
    res = client.get(f"/api/admin/passcodes?admin_passcode={MASTER_ADMIN_PASSWORD}")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # Admin creates new passcode
    res = client.post(
        "/api/admin/passcodes",
        data={
            "admin_passcode": MASTER_ADMIN_PASSWORD,
            "label": "API Test User",
            "report_limit": 7,
            "custom_passcode": "API-TEST-CODE",
        },
    )
    assert res.status_code == 200
    assert res.json()["passcode"] == "API-TEST-CODE"

    # Newly created passcode authenticates
    auth_res = client.post("/api/auth", data={"password": "API-TEST-CODE"})
    assert auth_res.status_code == 200
    assert auth_res.json()["report_limit"] == 7

    # Admin adjusts quota limit
    adj_res = client.post(
        "/api/admin/passcodes/API-TEST-CODE/adjust",
        data={
            "admin_passcode": MASTER_ADMIN_PASSWORD,
            "report_limit": 15,
            "reset_used": False,
        },
    )
    assert adj_res.status_code == 200

    # Admin deletes passcode
    del_res = client.delete(f"/api/admin/passcodes/API-TEST-CODE?admin_passcode={MASTER_ADMIN_PASSWORD}")
    assert del_res.status_code == 200

    # Deleted passcode no longer works
    assert client.post("/api/auth", data={"password": "API-TEST-CODE"}).status_code == 401


def test_auth_demo_passcode(client):
    res = client.post("/api/auth", data={"password": "DEMO!"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["is_admin"] is False
    assert data["passcode"] == "DEMO!"


def test_demo_cannot_delete_report_via_api(client):
    from src.db import record_report, get_report_by_id
    rep = {"session_id": "api-demo-rep-1", "jurisdiction": "Islamabad", "policy_document": "policy1.pdf"}
    record_report("api-demo-rep-1", "DEMO!", "Pre-Compiled Demonstration Account", rep)

    # Demo user attempting delete returns 403 Forbidden
    res = client.delete("/api/reports/api-demo-rep-1?passcode=DEMO!")
    assert res.status_code == 403
    assert "Demo users cannot delete" in res.json()["detail"]

    # Report still exists
    assert get_report_by_id("api-demo-rep-1") is not None


def test_report_pdf_endpoint(client):
    # data/policy1.pdf exists in the repo
    res = client.get("/api/reports/api-demo-rep-1/pdf/policy1.pdf?passcode=DEMO!")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"


def test_user_without_llama_key_blocked_from_analyze(client):
    # Create a fresh user without llama_key
    from src.db import create_passcode
    create_passcode("No Key Tester", report_limit=5, custom_passcode="NO-KEY-TESTER")

    pdf_content = b"%PDF-1.4 sample pdf content for testing"
    files = [("files", ("test_doc.pdf", pdf_content, "application/pdf"))]
    res = client.post("/api/analyze", data={"password": "NO-KEY-TESTER"}, files=files)
    assert res.status_code == 403
    assert "LlamaCloud API Key required" in res.json()["detail"]


def test_set_user_llama_key_validation(client):
    # Empty key returns 400
    res = client.post("/api/user/llama_key", data={"passcode": "TEST-LAW-2026", "llama_key": "   "})
    assert res.status_code == 400

    # Key without llx- or too short returns 400
    res = client.post("/api/user/llama_key", data={"passcode": "TEST-LAW-2026", "llama_key": "short"})
    assert res.status_code == 400

    # Valid key saves and returns masked key
    valid_key = "llx-testusersecretkey9876543210"
    res = client.post("/api/user/llama_key", data={"passcode": "TEST-LAW-2026", "llama_key": valid_key})
    assert res.status_code == 200
    data = res.json()
    assert data["saved"] is True
    assert data["has_llama_key"] is True
    assert data["llama_key_masked"] == "llx-tes...3210"

    # Verify /api/user/info now returns has_llama_key: True and masked key
    info_res = client.get("/api/user/info?passcode=TEST-LAW-2026")
    assert info_res.status_code == 200
    info_data = info_res.json()
    assert info_data["has_llama_key"] is True
    assert info_data["llama_key_masked"] == "llx-tes...3210"


def test_user_entered_llama_key_used_in_ingestion(client, monkeypatch):
    from src.orchestration.state import (
        LoopholeReport,
        SeverityClassification,
        ExploitVector,
        JurisdictionLevel,
        CanonicalExploit,
        StakeholderScore,
    )
    from src.db import create_passcode

    # Create a dedicated passcode to guarantee available quota
    create_passcode("Ingest Key Tester", report_limit=10, custom_passcode="INGEST-KEY-TESTER")
    user_key = "llx-user-custom-key-11223344"
    client.post("/api/user/llama_key", data={"passcode": "INGEST-KEY-TESTER", "llama_key": user_key})

    captured_key = None

    def mock_ingest(pdf_paths, llama_api_key=None, output_dir=None):
        nonlocal captured_key
        captured_key = llama_api_key
        return str(output_dir)

    async def mock_run_audit(*args, **kwargs):
        return LoopholeReport(
            session_id="test-session-key",
            jurisdiction="Islamabad",
            jurisdiction_level=JurisdictionLevel.FEDERAL,
            target_entity="Developers",
            policy_document="test_doc.pdf",
            exploit_vector=ExploitVector.DEFINITIONAL_GAP,
            severity_classification=SeverityClassification.LOW,
            legal_confidence_score=0.9,
            canonical_exploit=CanonicalExploit(
                summary="Exploit summary",
                exploit_vector=ExploitVector.DEFINITIONAL_GAP,
                primary_citation_ids=("Section 1",),
                is_novel=True,
            ),
            statutory_citations=(),
            debate_transcript=(),
            retrieval_provenance=(),
            citizen_score=StakeholderScore(
                stakeholder_type="citizen",
                harm_score=0.1,
                benefit_score=1,
                affected_population="Citizens",
                priority_concerns=("Concern 1",),
                confidence=0.9,
            ),
            business_score=StakeholderScore(
                stakeholder_type="business",
                harm_score=0.1,
                benefit_score=0.1,
                affected_population="Businesses",
                priority_concerns=("Concern 2",),
                confidence=0.9,
            ),
            affected_population_estimate="None",
            remediation_recommendation="None",
            raw_judge_reasoning="Reasoning",
            model_versions_used={"attacker": "test", "defender": "test"},
        )

    monkeypatch.setattr("src.ingest_policy.ingest_document", mock_ingest)
    monkeypatch.setattr("src.orchestration.runner.run_audit_simple", mock_run_audit)

    pdf_content = b"%PDF-1.4 sample pdf"
    files = [("files", ("test_doc.pdf", pdf_content, "application/pdf"))]
    res = client.post("/api/analyze", data={"password": "INGEST-KEY-TESTER"}, files=files)
    assert res.status_code == 200
    assert captured_key == user_key

