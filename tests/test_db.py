"""
Tests for src/db.py — Database, Passcodes, and Quotas
=====================================================
Validates SQLite table initialization, passcode verification,
quota tracking (can_generate_report), report persistence, and admin queries.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db import (
    init_db,
    verify_passcode,
    can_generate_report,
    record_report,
    get_user_reports,
    get_all_reports,
    get_report_by_id,
    create_passcode,
    list_all_passcodes,
    delete_passcode,
    update_passcode_limit,
    get_db_connection,
    MASTER_ADMIN_PASSWORD,
)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Overrides DB_PATH to use a temporary SQLite database for each test run."""
    test_db = tmp_path / "test_policy.db"
    test_reports = tmp_path / "reports"
    test_reports.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("src.db.DB_PATH", test_db)
    monkeypatch.setattr("src.db.REPORTS_DIR", test_reports)
    monkeypatch.setattr("src.db.GCS_BUCKET", "")  # Disable remote GCS calls in test

    init_db()
    yield test_db


class TestDatabasePasscodes:
    """Tests for authentication, passcode creation, and quota enforcement."""

    def test_master_admin_verification(self):
        info = verify_passcode(MASTER_ADMIN_PASSWORD)
        assert info is not None
        assert info["is_admin"] is True
        assert info["report_limit"] == -1

    def test_default_seeded_tester(self):
        info = verify_passcode("TEST-LAW-2026")
        assert info is not None
        assert info["is_admin"] is False
        assert info["report_limit"] == 5
        assert info["reports_used"] == 0

    def test_invalid_passcode(self):
        assert verify_passcode("NON-EXISTENT-CODE") is None

    def test_create_and_delete_passcode(self):
        created = create_passcode(label="Junior Researcher", report_limit=3, custom_passcode="CUSTOM-123")
        assert created["passcode"] == "CUSTOM-123"
        assert created["report_limit"] == 3

        info = verify_passcode("CUSTOM-123")
        assert info is not None
        assert info["label"] == "Junior Researcher"

        # Delete it
        success = delete_passcode("CUSTOM-123")
        assert success is True
        assert verify_passcode("CUSTOM-123") is None

    def test_cannot_delete_master_admin(self):
        assert delete_passcode(MASTER_ADMIN_PASSWORD) is False

    def test_quota_exhaustion_enforcement(self):
        code = "QUOTA-TEST"
        create_passcode(label="Quota Tester", report_limit=1, custom_passcode=code)

        # First report: allowed
        allowed, msg, info = can_generate_report(code)
        assert allowed is True

        # Simulate generating a report
        sample_report = {
            "session_id": "test-session-1",
            "jurisdiction": "Islamabad",
            "policy_document": "test.pdf",
            "severity_classification": "High",
            "exploit_vector": "Definitional Gap",
        }
        record_report("test-session-1", code, "Quota Tester", sample_report)

        # Quota used should now be 1
        info = verify_passcode(code)
        assert info["reports_used"] == 1

        # Second report: blocked!
        allowed, msg, info = can_generate_report(code)
        assert allowed is False
        assert "quota reached" in msg.lower()

        # Admin resets/increases quota
        update_passcode_limit(code, new_limit=5, reset_used=True)
        allowed, msg, info = can_generate_report(code)
        assert allowed is True
        assert info["reports_used"] == 0

    def test_admin_has_unlimited_quota(self):
        allowed, msg, info = can_generate_report(MASTER_ADMIN_PASSWORD)
        assert allowed is True
        assert "unlimited" in msg.lower()


class TestDatabaseReports:
    """Tests for report persistence and scoping."""

    def test_record_and_fetch_report(self):
        code = "TESTER-ALICE"
        create_passcode(label="Alice", report_limit=10, custom_passcode=code)

        report_data = {
            "session_id": "rep-999",
            "jurisdiction": "Punjab, Pakistan",
            "policy_document": "bylaw_2023.pdf",
            "severity_classification": "Critical",
            "exploit_vector": "Penalty Asymmetry",
            "details": "Sample loophole explanation",
        }

        success = record_report("rep-999", code, "Alice", report_data)
        assert success is True

        # Fetch by user
        user_reports = get_user_reports(code)
        assert len(user_reports) == 1
        assert user_reports[0]["report_id"] == "rep-999"
        assert user_reports[0]["severity"] == "Critical"

        # Fetch full report JSON
        full = get_report_by_id("rep-999")
        assert full is not None
        assert full["details"] == "Sample loophole explanation"

        # Admin fetches all
        all_reps = get_all_reports()
        assert len(all_reps) >= 1
        assert any(r["report_id"] == "rep-999" for r in all_reps)
