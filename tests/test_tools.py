"""
Tests for src/orchestration/tools.py — MCP Response Parser
===========================================================
Validates that parse_mcp_response() correctly extracts statutory
citations, FAISS scores, page numbers, and section identifiers
from the MCP server's Markdown output format.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestration.state import RetrievalTrace, StatutoryCitation
from src.orchestration.tools import parse_mcp_response


class TestParseMcpResponse:
    """Tests for the regex-based AST metadata parser."""

    def test_extracts_citations_from_standard_response(self, sample_mcp_response: str):
        """Verify extraction of multiple sections with scores and page numbers."""
        trace = parse_mcp_response(
            raw_response=sample_mcp_response,
            agent_role="AttackerAgent",
            turn_number=1,
            query="building permit exemptions",
        )

        assert isinstance(trace, RetrievalTrace)
        assert trace.agent_role == "AttackerAgent"
        assert trace.turn_number == 1
        assert trace.query == "building permit exemptions"
        assert trace.raw_response_length == len(sample_mcp_response)

        # Should extract citations from all 3 sections
        assert len(trace.citations_extracted) >= 2  # Sections 1 & 2 have section IDs

    def test_extracts_source_document(self, sample_mcp_response: str):
        """Verify source document filename is correctly extracted from headers."""
        trace = parse_mcp_response(
            raw_response=sample_mcp_response,
            agent_role="DefenderAgent",
            turn_number=2,
            query="test query",
        )

        for citation in trace.citations_extracted:
            assert citation.source_document == "policy1.pdf"

    def test_extracts_faiss_scores(self, sample_mcp_response: str):
        """Verify FAISS similarity scores are parsed as floats."""
        trace = parse_mcp_response(
            raw_response=sample_mcp_response,
            agent_role="AttackerAgent",
            turn_number=1,
            query="test query",
        )

        scores = [c.retrieval_score for c in trace.citations_extracted]
        # All scores should be positive floats
        assert all(isinstance(s, float) for s in scores)
        assert all(s > 0.0 for s in scores)

    def test_extracts_page_numbers(self, sample_mcp_response: str):
        """Verify page numbers are extracted from 'Page N' patterns."""
        trace = parse_mcp_response(
            raw_response=sample_mcp_response,
            agent_role="AttackerAgent",
            turn_number=1,
            query="test query",
        )

        # Find citations that should have page numbers
        citations_with_pages = [
            c for c in trace.citations_extracted if c.page_number is not None
        ]
        assert len(citations_with_pages) >= 1

        page_numbers = [c.page_number for c in citations_with_pages]
        assert 12 in page_numbers or 5 in page_numbers

    def test_extracts_statutory_section_ids(self, sample_mcp_response: str):
        """Verify Pakistani legal section identifiers (§, Rule, Article, etc.) are parsed."""
        trace = parse_mcp_response(
            raw_response=sample_mcp_response,
            agent_role="AttackerAgent",
            turn_number=1,
            query="test query",
        )

        section_ids = [c.section_id for c in trace.citations_extracted]
        # Should find "Rule 7(3)(b)" and "§ 4(a)(ii)" patterns
        has_rule = any("Rule" in sid for sid in section_ids)
        has_section = any("§" in sid or "Section" in sid for sid in section_ids)
        assert has_rule or has_section, f"Expected Rule or § references, got: {section_ids}"

    def test_handles_response_without_section_ids(self, sample_mcp_response_no_sections: str):
        """Verify fallback to [Unidentified Section] when no statutory IDs found."""
        trace = parse_mcp_response(
            raw_response=sample_mcp_response_no_sections,
            agent_role="AttackerAgent",
            turn_number=1,
            query="committee meetings",
        )

        assert len(trace.citations_extracted) >= 1
        # Should use fallback section ID
        assert any(
            c.section_id == "[Unidentified Section]"
            for c in trace.citations_extracted
        )

    def test_handles_empty_response(self, empty_mcp_response: str):
        """Verify graceful handling of empty MCP responses."""
        trace = parse_mcp_response(
            raw_response=empty_mcp_response,
            agent_role="AttackerAgent",
            turn_number=1,
            query="empty query",
        )

        assert isinstance(trace, RetrievalTrace)
        assert len(trace.citations_extracted) == 0
        assert trace.raw_response_length == 0

    def test_quoted_text_max_length(self, sample_mcp_response: str):
        """Verify quoted_text is capped at 200 characters."""
        trace = parse_mcp_response(
            raw_response=sample_mcp_response,
            agent_role="AttackerAgent",
            turn_number=1,
            query="test query",
        )

        for citation in trace.citations_extracted:
            assert len(citation.quoted_text) <= 200

    def test_citation_immutability(self, sample_mcp_response: str):
        """Verify StatutoryCitation objects are frozen (immutable)."""
        trace = parse_mcp_response(
            raw_response=sample_mcp_response,
            agent_role="AttackerAgent",
            turn_number=1,
            query="test query",
        )

        if trace.citations_extracted:
            citation = trace.citations_extracted[0]
            import pytest
            with pytest.raises(Exception):  # Pydantic frozen model raises on mutation
                citation.section_id = "modified"
