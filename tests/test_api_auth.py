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
