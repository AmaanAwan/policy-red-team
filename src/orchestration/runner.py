"""
Phase 3 — Orchestration Layer: Runner
======================================
runner.py

The top-level entrypoint for a policy audit session. Orchestrates:

1. MCP SERVER LAUNCH — Starts src/mcp_server.py as a background subprocess
   in SSE mode (localhost:8090). The subprocess is kept separate from the
   ADK runtime so it can be independently observed and restarted.

2. HEALTH CHECK — Polls the SSE endpoint until the MCP server is ready,
   with a configurable timeout.

3. SESSION INITIALIZATION — Creates an ADK InMemorySessionService, builds
   the workflow DAG from PolicyAuditState, and registers the session.

4. WORKFLOW EXECUTION — Runs the full PolicyAuditWorkflow via ADK Runner.
   Emits live events to the console for observability.

5. REPORT EXTRACTION — Parses final_report_json from session state and
   validates it against the LoopholeReport Pydantic schema.

6. CLEANUP — Terminates the MCP server subprocess on exit.

Usage:
    python -m src.orchestration.runner

    Or programmatically:
        from src.orchestration.runner import run_audit
        from src.orchestration.state import PolicyAuditState, JurisdictionLevel

        state = PolicyAuditState(
            jurisdiction="Rawalpindi, Punjab, Pakistan",
            jurisdiction_level=JurisdictionLevel.MUNICIPAL,
            target_entity="Real Estate Developers",
            policy_document="rda_bylaws_2023.pdf",
        )
        report = asyncio.run(run_audit(state))
        print(report.model_dump_json(indent=2))

PHASE 4 NOTE:
To swap to a Canadian context, change the PolicyAuditState fields:
    jurisdiction="Ontario, Canada"
    jurisdiction_level=JurisdictionLevel.PROVINCIAL
    target_entity="Property Development Corporations"
No other code changes required (all agents inject from state fields).
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import httpx
from google.adk.agents import BaseAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from src.orchestration.state import (
    JurisdictionLevel,
    LoopholeReport,
    PolicyAuditState,
)
from src.orchestration.workflow import build_workflow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project root for subprocess launch
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# MCP server configuration
# ---------------------------------------------------------------------------
MCP_SERVER_MODULE = "src.mcp_server"
MCP_HOST = "127.0.0.1"
MCP_PORT = 8090
MCP_HEALTH_URL = f"http://{MCP_HOST}:{MCP_PORT}/sse"  # SSE endpoint (returns headers on GET)
MCP_STARTUP_TIMEOUT_SECONDS = 30
MCP_HEALTH_POLL_INTERVAL = 0.5

# ---------------------------------------------------------------------------
# ADK session configuration
# ---------------------------------------------------------------------------
ADK_APP_NAME = "PolicyRedTeam"
ADK_USER_ID = "audit_user"


# ===================================================================
# MCP SERVER LIFECYCLE
# ===================================================================

def _start_mcp_server() -> subprocess.Popen:
    """
    Launch the MCP server as a background subprocess in SSE mode.

    Uses sys.executable to ensure the same Python interpreter (and venv)
    is used for the subprocess.

    Returns:
        subprocess.Popen handle for the running server.

    Raises:
        RuntimeError: If the server fails to start within MCP_STARTUP_TIMEOUT_SECONDS.
    """
    cmd = [
        sys.executable, "-m", MCP_SERVER_MODULE,
        "--transport", "sse",
        "--host", MCP_HOST,
        "--port", str(MCP_PORT),
    ]

    logger.info("Starting MCP server: %s", " ".join(cmd))

    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # Do NOT use shell=True — it creates a shell wrapper that makes
        # cleanup (proc.terminate()) unreliable on Windows.
    )

    logger.info("MCP server subprocess PID: %d. Waiting for readiness...", proc.pid)
    return proc


async def _wait_for_mcp_server(
    proc: subprocess.Popen,
    timeout: float = MCP_STARTUP_TIMEOUT_SECONDS,
) -> None:
    """
    Poll the MCP SSE endpoint until it responds, indicating the server is ready.

    The SSE endpoint returns HTTP 200 with Content-Type: text/event-stream
    when the server is up. We use stream() to check headers without blocking
    on the endless event body.

    Args:
        proc:    Subprocess handle (checked for premature exit).
        timeout: Maximum seconds to wait before raising RuntimeError.

    Raises:
        RuntimeError: If server doesn't start within timeout or exits prematurely.
    """
    deadline = time.monotonic() + timeout

    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            # Check if subprocess exited prematurely
            if proc.poll() is not None:
                raise RuntimeError(
                    f"MCP server subprocess exited prematurely (code={proc.returncode})."
                )

            try:
                # SSE endpoints hold the connection open, so we use stream()
                # to read headers (200 OK) without hanging on the infinite body.
                async with client.stream(
                    "GET",
                    MCP_HEALTH_URL,
                    timeout=httpx.Timeout(2.0, connect=2.0),
                    headers={"Accept": "text/event-stream"},
                ) as response:
                    if response.status_code in (200, 405):
                        logger.info(
                            "✓ MCP server ready at %s (HTTP %d)",
                            MCP_HEALTH_URL, response.status_code,
                        )
                        return
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
                # Server not yet accepting connections — normal during startup
                pass

            await asyncio.sleep(MCP_HEALTH_POLL_INTERVAL)

    raise RuntimeError(
        f"MCP server did not become ready within {timeout}s. "
        f"Check that port {MCP_PORT} is not already in use."
    )


def _stop_mcp_server(proc: subprocess.Popen) -> None:
    """
    Gracefully stop the MCP server subprocess.

    Attempts SIGTERM first, then SIGKILL after 5 seconds.

    Args:
        proc: Subprocess handle from _start_mcp_server().
    """
    if proc.poll() is not None:
        logger.info("MCP server already exited (code=%d).", proc.returncode)
        return

    logger.info("Stopping MCP server (PID=%d)...", proc.pid)
    proc.terminate()

    try:
        proc.wait(timeout=5)
        logger.info("✓ MCP server stopped cleanly.")
    except subprocess.TimeoutExpired:
        logger.warning("MCP server did not stop within 5s — sending SIGKILL.")
        proc.kill()
        proc.wait()
        logger.info("MCP server killed.")


# ===================================================================
# REPORT EXTRACTION
# ===================================================================

def _extract_report(session_state: dict, state: PolicyAuditState) -> LoopholeReport:
    """
    Extract and validate the LoopholeReport from ADK session state.

    Attempts to parse final_report_json via Pydantic. If parsing fails
    (e.g., Judge produced malformed JSON), logs the error and raises
    with the raw JSON for debugging.

    Args:
        session_state: The final session state dict from InMemorySessionService.
        state:         Original PolicyAuditState (for error context).

    Returns:
        Validated LoopholeReport.

    Raises:
        ValueError: If final_report_json is missing or fails Pydantic validation.
    """
    raw_json = session_state.get("final_report_json", "").strip()

    if not raw_json or raw_json == "{}":
        raise ValueError(
            "final_report_json is empty after workflow completion. "
            f"Session ID: {state.session_id}. "
            "This usually means the JudgeAgent did not run or produced no output. "
            "Check ADK event logs for errors in the JudgeAgent step."
        )

    # Strip Markdown code block fences (e.g., ```json ... ```) if present
    if raw_json.startswith("```"):
        lines = raw_json.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_json = "\n".join(lines).strip()

    try:
        report = LoopholeReport.model_validate_json(raw_json)
        logger.info("✓ LoopholeReport validated successfully.")
        return report
    except Exception as exc:
        logger.error(
            "LoopholeReport Pydantic validation failed: %s\n"
            "Raw JSON (first 500 chars): %s",
            exc, raw_json[:500],
        )
        raise ValueError(
            f"JudgeAgent output failed Pydantic validation: {exc}\n"
            f"Raw output: {raw_json[:500]}"
        ) from exc


# ===================================================================
# MAIN AUDIT FUNCTION
# ===================================================================

async def run_audit(
    state: PolicyAuditState,
    *,
    output_path: Path | None = None,
    verbose: bool = True,
) -> LoopholeReport:
    """
    Execute a complete policy audit session end-to-end.

    Steps:
        1. Start MCP server subprocess (SSE mode)
        2. Wait for MCP server readiness
        3. Initialize ADK session with PolicyAuditState
        4. Build and run the PolicyAuditWorkflow
        5. Extract and validate LoopholeReport
        6. Optionally save report to JSON file
        7. Stop MCP server

    Args:
        state:       Fully initialized PolicyAuditState.
        output_path: If provided, saves the LoopholeReport JSON here.
        verbose:     If True, prints live ADK events to console.

    Returns:
        Validated LoopholeReport.

    Raises:
        RuntimeError: If MCP server fails to start.
        ValueError:   If the final report cannot be parsed.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("=" * 70)
    logger.info("PHASE 3: ADK Multi-Agent Policy Audit")
    logger.info("=" * 70)
    logger.info("Session ID:   %s", state.session_id)
    logger.info("Jurisdiction: %s (%s)", state.jurisdiction, state.jurisdiction_level.value)
    logger.info("Target Entity: %s", state.target_entity)
    logger.info("Policy Doc:   %s", state.policy_document)
    logger.info("Max Turns:    %d", state.max_turns)
    logger.info("=" * 70)

    mcp_proc: subprocess.Popen | None = None

    try:
        # --- Step 1: Start MCP server ---
        mcp_proc = _start_mcp_server()
        await _wait_for_mcp_server(mcp_proc)

        # --- Step 2: Set up ADK session service ---
        session_service = InMemorySessionService()

        # Serialize PolicyAuditState to flat dict for ADK session
        initial_session_state = state.to_session_dict()

        session = await session_service.create_session(
            app_name=ADK_APP_NAME,
            user_id=ADK_USER_ID,
            state=initial_session_state,
        )
        logger.info("ADK session created: %s", session.id)

        # --- Step 3: Build workflow ---
        workflow = build_workflow(state)

        # --- Step 4: Run the workflow ---
        runner = Runner(
            agent=workflow,
            app_name=ADK_APP_NAME,
            session_service=session_service,
        )

        logger.info("Starting PolicyAuditWorkflow...")
        logger.info("-" * 70)

        # The runner expects an initial user message to kick off the workflow.
        # We use a structured trigger message that summarizes the audit task.
        trigger_message = Content(
            role="user",
            parts=[
                Part(
                    text=(
                        f"Begin a comprehensive adversarial red-team audit of the policy document "
                        f"'{state.policy_document}' in the jurisdiction of {state.jurisdiction} "
                        f"({state.jurisdiction_level.value} level). "
                        f"The target entity is: {state.target_entity}. "
                        f"Run the full debate loop (up to {state.max_turns} turns), "
                        f"canonicalize the exploit, assess stakeholder impact, and produce "
                        f"a complete LoopholeReport."
                    )
                )
            ],
        )

        # Stream and log ADK events for observability
        async for event in runner.run_async(
            session_id=session.id,
            user_id=ADK_USER_ID,
            new_message=trigger_message,
        ):
            if verbose and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        agent_name = getattr(event, "author", "Unknown")
                        # Truncate long outputs for console readability
                        display_text = part.text[:300] + "..." if len(part.text) > 300 else part.text
                        logger.info("[%s] %s", agent_name, display_text)

        logger.info("-" * 70)
        logger.info("Workflow complete. Extracting LoopholeReport...")

        # --- Step 5: Extract and validate report ---
        final_session = await session_service.get_session(
            app_name=ADK_APP_NAME,
            user_id=ADK_USER_ID,
            session_id=session.id,
        )
        report = _extract_report(dict(final_session.state), state)

        # --- Step 6: Save to file (optional) ---
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                report.model_dump_json(indent=2),
                encoding="utf-8",
            )
            logger.info("✓ Report saved to: %s", output_path)

        logger.info("=" * 70)
        logger.info("AUDIT COMPLETE")
        logger.info("  Exploit Vector:   %s", report.exploit_vector.value)
        logger.info("  Severity:         %s", report.severity_classification.value)
        logger.info("  Confidence:       %.2f", report.legal_confidence_score)
        logger.info("  Turns Completed:  %d", len(report.debate_transcript))
        logger.info("=" * 70)

        return report

    finally:
        # --- Step 7: Always stop MCP server ---
        if mcp_proc is not None:
            _stop_mcp_server(mcp_proc)


# ===================================================================
# CLI ENTRYPOINT
# ===================================================================

async def _main() -> None:
    """
    Default CLI demo — runs an audit on Rawalpindi municipal bylaws
    with Real Estate Developers as the target entity.

    For production use, import run_audit() and pass your own PolicyAuditState.
    """
    import os

    # Add project root to path (needed when running as __main__)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from config.settings import settings
    settings.validate()

    demo_state = PolicyAuditState(
        jurisdiction="Rawalpindi, Punjab, Pakistan",
        jurisdiction_level=JurisdictionLevel.MUNICIPAL,
        target_entity="Real Estate Developers",
        policy_document=os.environ.get("POLICY_PDF", "policy1.pdf"),
        max_turns=3,
    )

    output_file = PROJECT_ROOT / "storage" / "reports" / f"{demo_state.session_id}.json"

    report = await run_audit(
        demo_state,
        output_path=output_file,
        verbose=True,
    )

    # Print summary to stdout
    print("\n" + "=" * 70)
    print("LOOPHOLE REPORT SUMMARY")
    print("=" * 70)
    print(f"Exploit:   {report.canonical_exploit.summary[:200]}")
    print(f"Vector:    {report.exploit_vector.value}")
    print(f"Severity:  {report.severity_classification.value}")
    print(f"Confidence:{report.legal_confidence_score:.2f}")
    print(f"Fix:       {report.remediation_recommendation[:200]}")
    print("=" * 70)
    print(f"\nFull report saved to: {output_file}")




# ===================================================================
# SIMPLE WRAPPER (for Streamlit / FastAPI)
# ===================================================================

async def run_audit_simple(
    *,
    pdf_names: list[str],
    jurisdiction: str,
    jurisdiction_level_str: str,
    target_entity: str,
    custom_instructions: str = "",
    output_path: Path | None = None,
    verbose: bool = False,
) -> "LoopholeReport":
    """
    Streamlit / FastAPI friendly wrapper around run_audit().

    Accepts plain Python types (strings, lists) so callers don't need
    to construct Pydantic models manually.

    Args:
        pdf_names:              List of PDF filenames that were ingested
                                (used for labelling in the report).
        jurisdiction:           e.g. "Rawalpindi, Punjab, Pakistan"
        jurisdiction_level_str: "Federal", "Provincial", or "Municipal"
        target_entity:          e.g. "Real Estate Developers"
        custom_instructions:    Optional focus hint injected into AttackerAgent.
        output_path:            Optional file path to save the JSON report.
        verbose:                Stream ADK events to console if True.

    Returns:
        Validated LoopholeReport.
    """
    # Map the string jurisdiction level to the enum
    level_map = {
        "Federal": JurisdictionLevel.FEDERAL,
        "Provincial": JurisdictionLevel.PROVINCIAL,
        "Municipal": JurisdictionLevel.MUNICIPAL,
    }
    jd_level = level_map.get(jurisdiction_level_str, JurisdictionLevel.MUNICIPAL)

    # Use comma-joined filenames as the policy_document label
    policy_label = ", ".join(pdf_names) if pdf_names else "uploaded_document.pdf"

    state = PolicyAuditState(
        jurisdiction=jurisdiction,
        jurisdiction_level=jd_level,
        target_entity=target_entity,
        policy_document=policy_label,
        custom_instructions=custom_instructions,
        max_turns=3,
    )

    return await run_audit(state, output_path=output_path, verbose=verbose)


if __name__ == "__main__":
    asyncio.run(_main())

