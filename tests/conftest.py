"""
Shared test fixtures for the Policy Red Team test suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def sample_mcp_response() -> str:
    """
    Simulated Markdown response from the MCP server's
    search_policy_documents tool, matching the format
    emitted by mcp_server.py.
    """
    return (
        "### Retrieved Section 1 (Source: policy1.pdf, Score: 0.9231)\n\n"
        "Rule 7(3)(b) of the Rawalpindi Development Authority Building and "
        "Zoning Regulations 2023 states: \"No building permit shall be issued "
        "for a structure exceeding 40 feet in height unless the applicant has "
        "obtained prior approval from the Director General, RDA.\"\n\n"
        "Page 12\n\n"
        "---\n\n"
        "### Retrieved Section 2 (Source: policy1.pdf, Score: 0.8714)\n\n"
        "§ 4(a)(ii) — Exemptions: The following categories of construction "
        "shall be exempt from the requirements of Section 3: (a) temporary "
        "structures erected for a period not exceeding 90 days; (b) boundary "
        "walls not exceeding 8 feet in height.\n\n"
        "Page 5\n\n"
        "---\n\n"
        "### Retrieved Section 3 (Source: policy1.pdf, Score: 0.7102)\n\n"
        "The fee schedule for building permits is as follows: residential "
        "structures shall pay PKR 50 per square foot, commercial structures "
        "shall pay PKR 100 per square foot.\n\n"
        "---\n"
    )


@pytest.fixture
def sample_mcp_response_no_sections() -> str:
    """MCP response with no statutory section identifiers."""
    return (
        "### Retrieved Section 1 (Source: bylaw.pdf, Score: 0.6500)\n\n"
        "The committee shall meet quarterly to review applications.\n\n"
        "---\n"
    )


@pytest.fixture
def empty_mcp_response() -> str:
    """Empty MCP response (no sections retrieved)."""
    return ""
