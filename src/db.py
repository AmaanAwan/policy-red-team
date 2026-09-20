"""
Database & Persistence Layer for Policy Red Team
==================================================
Manages test user passcodes, report quotas, and report storage.
Uses local SQLite with Write-Ahead Logging (WAL) for transactional safety,
with automatic bidirectional Google Cloud Storage (GCS) sync if GCS_BUCKET is configured.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "storage" / "policy_red_team.db"
REPORTS_DIR = PROJECT_ROOT / "storage" / "reports"
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
MASTER_ADMIN_PASSWORD = os.environ.get("APP_PASSWORD", "admin-policy-2026")


def get_db_connection() -> sqlite3.Connection:
    """Returns an SQLite connection configured with WAL mode for high concurrency."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _get_gcs_bucket():
    """Returns GCS bucket object if configured, else None."""
    if not GCS_BUCKET:
        return None
    try:
        from google.cloud import storage
        client = storage.Client()
        return client.bucket(GCS_BUCKET)
    except Exception as exc:
        logger.warning(f"GCS client initialization failed: {exc}")
        return None


def init_db() -> None:
    """
    Initializes database tables, creates storage directories,
    syncs from GCS if available, and seeds Master Admin and demo passcodes.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS passcodes (
                passcode TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                report_limit INTEGER NOT NULL DEFAULT 5,
                reports_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                passcode TEXT NOT NULL,
                user_label TEXT NOT NULL,
                policy_document TEXT NOT NULL,
                jurisdiction TEXT NOT NULL,
                severity TEXT NOT NULL,
                exploit_vector TEXT NOT NULL,
                created_at TEXT NOT NULL,
                report_json TEXT NOT NULL,
                FOREIGN KEY (passcode) REFERENCES passcodes(passcode)
            );
            """
        )
        conn.commit()

        # Seed Master Admin from environment
        now = datetime.now(timezone.utc).isoformat()
        admin_row = conn.execute(
            "SELECT passcode FROM passcodes WHERE passcode = ?", (MASTER_ADMIN_PASSWORD,)
        ).fetchone()

        if not admin_row:
            conn.execute(
                """
                INSERT OR REPLACE INTO passcodes (passcode, label, is_admin, report_limit, reports_used, created_at)
                VALUES (?, ?, 1, -1, 0, ?)
                """,
                (MASTER_ADMIN_PASSWORD, "Master Administrator", now),
            )
            conn.commit()
            logger.info("Master Admin passcode registered in database.")

        # Seed Default Beta Tester Passcodes
        for code, label, limit in [
            ("TEST-LAW-2026", "Beta Policy Tester", 5),
            ("DEMO-SAMPLE-2026", "Sample Demonstration User", 10),
        ]:
            conn.execute(
                """
                INSERT OR IGNORE INTO passcodes (passcode, label, is_admin, report_limit, reports_used, created_at)
                VALUES (?, ?, 0, ?, 0, ?)
                """,
                (code, label, limit, now),
            )
        conn.commit()

        # Load any local sample reports into database
        if REPORTS_DIR.exists():
            for r_file in REPORTS_DIR.glob("*.json"):
                try:
                    data = json.loads(r_file.read_text(encoding="utf-8"))
                    r_id = data.get("session_id", r_file.stem)
                    existing = conn.execute("SELECT report_id FROM reports WHERE report_id = ?", (r_id,)).fetchone()
                    if not existing:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO reports
                            (report_id, passcode, user_label, policy_document, jurisdiction, severity, exploit_vector, created_at, report_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                r_id,
                                "DEMO-SAMPLE-2026",
                                "Sample Demonstration User",
                                data.get("policy_document", "policy1.pdf"),
                                data.get("jurisdiction", "Islamabad, Pakistan"),
                                data.get("severity_classification", "High"),
                                data.get("exploit_vector", data.get("canonical_exploit", {}).get("exploit_vector", "Jurisdictional Arbitrage")),
                                now,
                                json.dumps(data, indent=2),
                            ),
                        )
                except Exception as exc:
                    logger.warning(f"Could not load pre-seeded report {r_file}: {exc}")
            conn.commit()

    # Attempt restore/sync from GCS if available
    _sync_from_gcs()


def _sync_from_gcs() -> None:
    """Restores passcodes and all historical reports from GCS if running on Cloud Run."""
    bucket = _get_gcs_bucket()
    if not bucket:
        return

    # 1. Restore passcodes
    try:
        blob = bucket.blob("auth/passcodes.json")
        if blob.exists():
            data = json.loads(blob.download_as_text())
            with get_db_connection() as conn:
                for item in data:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO passcodes (passcode, label, is_admin, report_limit, reports_used, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item["passcode"],
                            item["label"],
                            item.get("is_admin", 0),
                            item.get("report_limit", 5),
                            item.get("reports_used", 0),
                            item.get("created_at", datetime.now(timezone.utc).isoformat()),
                        ),
                    )
                conn.commit()
            logger.info("Synced passcodes from GCS successfully.")
    except Exception as exc:
        logger.warning(f"Failed to sync passcodes from GCS: {exc}")

    # 2. Restore reports index
    try:
        blob = bucket.blob("reports/reports_index.json")
        if blob.exists():
            rep_data = json.loads(blob.download_as_text())
            with get_db_connection() as conn:
                for r in rep_data:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO reports
                        (report_id, passcode, user_label, policy_document, jurisdiction, severity, exploit_vector, created_at, report_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            r["report_id"],
                            r["passcode"],
                            r["user_label"],
                            r["policy_document"],
                            r["jurisdiction"],
                            r["severity"],
                            r["exploit_vector"],
                            r.get("created_at", datetime.now(timezone.utc).isoformat()),
                            r.get("report_json", "{}"),
                        ),
                    )
                    local_f = REPORTS_DIR / f"{r['report_id']}.json"
                    if not local_f.exists() and "report_json" in r:
                        local_f.write_text(r["report_json"], encoding="utf-8")
                conn.commit()
            logger.info("Synced reports from GCS successfully.")
    except Exception as exc:
        logger.warning(f"Failed to sync reports from GCS: {exc}")


def _sync_passcodes_to_gcs() -> None:
    """Exports all passcodes to GCS for persistence across Cloud Run container lifecycles."""
    bucket = _get_gcs_bucket()
    if not bucket:
        return

    try:
        passcodes = list_all_passcodes()
        blob = bucket.blob("auth/passcodes.json")
        blob.upload_from_string(json.dumps(passcodes, indent=2), content_type="application/json")
        logger.info("Uploaded passcodes backup to GCS.")
    except Exception as exc:
        logger.warning(f"Failed to backup passcodes to GCS: {exc}")


def _sync_reports_to_gcs() -> None:
    """Exports all reports index to GCS for persistence across Cloud Run container lifecycles."""
    bucket = _get_gcs_bucket()
    if not bucket:
        return

    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT report_id, passcode, user_label, policy_document, jurisdiction, severity, exploit_vector, created_at, report_json FROM reports"
            ).fetchall()
            items = [dict(r) for r in rows]
        blob = bucket.blob("reports/reports_index.json")
        blob.upload_from_string(json.dumps(items, indent=2), content_type="application/json")
        logger.info("Uploaded reports index backup to GCS.")
    except Exception as exc:
        logger.warning(f"Failed to backup reports index to GCS: {exc}")


def verify_passcode(passcode: str) -> dict[str, Any] | None:
    """
    Validates a passcode. If valid, returns dict with user metadata:
    { "passcode": ..., "label": ..., "is_admin": bool, "reports_used": int, "report_limit": int }
    """
    cleaned = passcode.strip()
    # Check Master Admin override
    if cleaned == MASTER_ADMIN_PASSWORD:
        return {
            "passcode": MASTER_ADMIN_PASSWORD,
            "label": "Master Administrator",
            "is_admin": True,
            "report_limit": -1,  # Unlimited
            "reports_used": 0,
        }

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT passcode, label, is_admin, report_limit, reports_used FROM passcodes WHERE passcode = ?",
            (cleaned,),
        ).fetchone()

        if row:
            return {
                "passcode": row["passcode"],
                "label": row["label"],
                "is_admin": bool(row["is_admin"]),
                "report_limit": row["report_limit"],
                "reports_used": row["reports_used"],
            }
    return None


def can_generate_report(passcode: str) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Checks if the user is authorized and has remaining report generation quota.
    Returns (allowed: bool, reason: str, user_info: dict).
    """
    info = verify_passcode(passcode)
    if not info:
        return False, "Invalid passcode. Please verify your credentials.", None

    if info["is_admin"] or info["report_limit"] == -1:
        return True, "Authorized (Unlimited Admin Quota)", info

    if info["reports_used"] >= info["report_limit"]:
        return (
            False,
            f"Report generation quota reached ({info['reports_used']}/{info['report_limit']}). "
            f"Please contact the administrator for an additional quota allocation.",
            info,
        )

    return True, "Authorized", info


def record_report(report_id: str, passcode: str, user_label: str, report_data: dict[str, Any]) -> bool:
    """
    Saves a completed audit report to SQLite, saves JSON to disk,
    increments the user's reports_used count, and backups to GCS.
    """
    now = datetime.now(timezone.utc).isoformat()
    jurisdiction = report_data.get("jurisdiction", "Unknown")
    policy_doc = report_data.get("policy_document", "Unknown")
    severity = report_data.get("severity_classification", "Unknown")
    exploit_vector = report_data.get("exploit_vector", "Unknown")
    report_json_str = json.dumps(report_data, indent=2)

    # 1. Local disk JSON write
    try:
        local_file = REPORTS_DIR / f"{report_id}.json"
        local_file.write_text(report_json_str, encoding="utf-8")
    except Exception as exc:
        logger.error(f"Failed to write report to local disk: {exc}")

    # 2. SQLite insert & counter increment
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO reports
                (report_id, passcode, user_label, policy_document, jurisdiction, severity, exploit_vector, created_at, report_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    passcode,
                    user_label,
                    policy_doc,
                    jurisdiction,
                    severity,
                    exploit_vector,
                    now,
                    report_json_str,
                ),
            )
            # Increment quota if not master admin
            conn.execute(
                "UPDATE passcodes SET reports_used = reports_used + 1 WHERE passcode = ?",
                (passcode,),
            )
            conn.commit()
    except Exception as exc:
        logger.error(f"Failed to record report in database: {exc}")
        return False

    # 3. GCS Cloud Backup if configured
    bucket = _get_gcs_bucket()
    if bucket:
        try:
            blob = bucket.blob(f"reports/{report_id}.json")
            blob.upload_from_string(report_json_str, content_type="application/json")
            logger.info(f"Backed up report {report_id} to GCS.")
            _sync_passcodes_to_gcs()
            _sync_reports_to_gcs()
        except Exception as exc:
            logger.warning(f"Failed to backup report to GCS: {exc}")

    return True


def get_user_reports(passcode: str) -> list[dict[str, Any]]:
    """Returns list of summaries of all reports generated by a specific passcode."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT report_id, policy_document, jurisdiction, severity, exploit_vector, created_at
            FROM reports
            WHERE passcode = ?
            ORDER BY created_at DESC
            """,
            (passcode,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_reports() -> list[dict[str, Any]]:
    """Admin query: returns summary list of all reports across all users."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT report_id, passcode, user_label, policy_document, jurisdiction, severity, exploit_vector, created_at
            FROM reports
            ORDER BY created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_report_by_id(report_id: str) -> dict[str, Any] | None:
    """Retrieves the full report dictionary by report_id."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT report_json FROM reports WHERE report_id = ?", (report_id,)).fetchone()
        if row:
            try:
                return json.loads(row["report_json"])
            except Exception:
                pass

    # Fallback to disk file
    local_file = REPORTS_DIR / f"{report_id}.json"
    if local_file.exists():
        try:
            return json.loads(local_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Fallback to GCS
    bucket = _get_gcs_bucket()
    if bucket:
        try:
            blob = bucket.blob(f"reports/{report_id}.json")
            if blob.exists():
                return json.loads(blob.download_as_text())
        except Exception:
            pass

    return None


def delete_report(report_id: str, passcode: str, is_admin: bool = False) -> bool:
    """
    Deletes a report by report_id.

    Users can only delete their own reports (passcode must match).
    Admins can delete any report.
    Quota (reports_used) is intentionally NOT decremented — deletion
    does not restore generation capacity.

    Returns True if the report was found and deleted, False otherwise.
    """
    with get_db_connection() as conn:
        if is_admin:
            row = conn.execute(
                "SELECT report_id FROM reports WHERE report_id = ?", (report_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT report_id FROM reports WHERE report_id = ? AND passcode = ?",
                (report_id, passcode),
            ).fetchone()

        if not row:
            return False

        conn.execute("DELETE FROM reports WHERE report_id = ?", (report_id,))
        conn.commit()

    # Remove local disk file if present
    local_file = REPORTS_DIR / f"{report_id}.json"
    if local_file.exists():
        try:
            local_file.unlink()
        except Exception as exc:
            logger.warning(f"Could not delete local report file {local_file}: {exc}")

    # Remove from GCS if configured
    bucket = _get_gcs_bucket()
    if bucket:
        try:
            blob = bucket.blob(f"reports/{report_id}.json")
            if blob.exists():
                blob.delete()
            _sync_reports_to_gcs()
        except Exception as exc:
            logger.warning(f"Failed to delete report {report_id} from GCS: {exc}")

    logger.info(f"Report {report_id} deleted by {'admin' if is_admin else passcode}.")
    return True



def create_passcode(label: str, report_limit: int = 5, custom_passcode: str = "") -> dict[str, Any]:
    """Admin: Creates a new user passcode with specified report limit."""
    code = custom_passcode.strip() if custom_passcode else f"TEST-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO passcodes
            (passcode, label, is_admin, report_limit, reports_used, created_at)
            VALUES (?, ?, 0, ?, 0, ?)
            """,
            (code, label.strip(), report_limit, now),
        )
        conn.commit()

    _sync_passcodes_to_gcs()
    return {
        "passcode": code,
        "label": label.strip(),
        "is_admin": False,
        "report_limit": report_limit,
        "reports_used": 0,
        "created_at": now,
    }


def list_all_passcodes() -> list[dict[str, Any]]:
    """Admin: Returns list of all active passcodes and usage statistics."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT passcode, label, is_admin, report_limit, reports_used, created_at
            FROM passcodes
            ORDER BY is_admin DESC, created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def delete_passcode(passcode: str) -> bool:
    """Admin: Deletes a passcode (cannot delete master admin)."""
    if passcode == MASTER_ADMIN_PASSWORD:
        return False

    with get_db_connection() as conn:
        conn.execute("DELETE FROM passcodes WHERE passcode = ? AND is_admin = 0", (passcode,))
        conn.commit()

    _sync_passcodes_to_gcs()
    return True


def update_passcode_limit(passcode: str, new_limit: int, reset_used: bool = False) -> bool:
    """Admin: Adjusts report quota limit or resets used counter."""
    with get_db_connection() as conn:
        if reset_used:
            conn.execute(
                "UPDATE passcodes SET report_limit = ?, reports_used = 0 WHERE passcode = ?",
                (new_limit, passcode),
            )
        else:
            conn.execute(
                "UPDATE passcodes SET report_limit = ? WHERE passcode = ?",
                (new_limit, passcode),
            )
        conn.commit()

    _sync_passcodes_to_gcs()
    return True
