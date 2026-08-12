"""
Tests for src/orchestration/state.py — State Primitives & ADK Session Dict
========================================================================
Validates immutability, Pydantic model validation, ADK session dictionary
conversion (to_session_dict / from_session_dict), and TurnSummary history logic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestration.state import (
    ExploitVector,
    JurisdictionLevel,
    PolicyAuditState,
    SeverityClassification,
    StatutoryCitation,
    TurnSummary,
    TurnVerdict,
)


class TestStatutoryCitation:
    """Tests for atomic StatutoryCitation primitive."""

    def test_creation_and_immutability(self):
        citation = StatutoryCitation(
            section_id="Rule 7(3)(b)",
            source_document="policy1.pdf",
            page_number=12,
            quoted_text="No building permit shall be issued...",
            retrieval_score=0.9231,
        )
        assert citation.section_id == "Rule 7(3)(b)"
        assert citation.source_document == "policy1.pdf"
        assert citation.page_number == 12
        assert citation.retrieval_score == 0.9231

        with pytest.raises(Exception):
            citation.section_id = "Rule 8"


class TestTurnSummary:
    """Tests for TurnSummary compression struct."""

    def test_turn_summary_creation(self):
        summary = TurnSummary(
            turn_number=1,
            exploit_claim="Definitional gap allows height limit bypass.",
            defender_rebuttal="Section 4 restricts height to 30 feet.",
            attacker_citations=("Rule 7(3)(b)",),
            defender_citations=("Section 4",),
            turn_verdict=TurnVerdict.EXPLOIT_SURVIVED,
        )
        assert summary.turn_number == 1
        assert summary.turn_verdict == TurnVerdict.EXPLOIT_SURVIVED
        assert summary.attacker_citations == ("Rule 7(3)(b)",)


class TestPolicyAuditState:
    """Tests for PolicyAuditState and ADK session conversion."""

    def test_state_defaults_and_immutability(self):
        state = PolicyAuditState(
            jurisdiction="Rawalpindi, Punjab, Pakistan",
            jurisdiction_level=JurisdictionLevel.MUNICIPAL,
            target_entity="Real Estate Developers",
            policy_document="policy1.pdf",
        )

        assert state.jurisdiction == "Rawalpindi, Punjab, Pakistan"
        assert state.jurisdiction_level == JurisdictionLevel.MUNICIPAL
        assert state.current_turn == 0
        assert state.max_turns == 3
        assert state.loop_should_continue is True
        assert isinstance(state.session_id, str)

        with pytest.raises(Exception):
            state.current_turn = 1

    def test_to_session_dict(self):
        state = PolicyAuditState(
            jurisdiction="Rawalpindi, Punjab, Pakistan",
            jurisdiction_level=JurisdictionLevel.MUNICIPAL,
            target_entity="Real Estate Developers",
            policy_document="policy1.pdf",
            custom_instructions="Focus on fee schedules",
        )

        s_dict = state.to_session_dict()

        assert s_dict["jurisdiction"] == "Rawalpindi, Punjab, Pakistan"
        assert s_dict["jurisdiction_level"] == "Municipal"
        assert s_dict["target_entity"] == "Real Estate Developers"
        assert s_dict["policy_document"] == "policy1.pdf"
        assert s_dict["custom_instructions"] == "Focus on fee schedules"

        # Check pre-populated agent working keys
        assert "current_exploit_text" in s_dict
        assert "current_rebuttal_text" in s_dict
        assert "deduplication_result" in s_dict
        assert s_dict["deduplication_result"] == "CONTINUE"

    def test_from_session_dict_reconstruction(self):
        original = PolicyAuditState(
            jurisdiction="Rawalpindi, Punjab, Pakistan",
            jurisdiction_level=JurisdictionLevel.MUNICIPAL,
            target_entity="Real Estate Developers",
            policy_document="policy1.pdf",
        )

        session_dict = original.to_session_dict()
        session_dict["current_turn"] = 2
        session_dict["loop_should_continue"] = False

        summary = TurnSummary(
            turn_number=1,
            exploit_claim="Exploit claim text",
            defender_rebuttal="Rebuttal text",
            attacker_citations=("§ 1",),
            defender_citations=("§ 2",),
            turn_verdict=TurnVerdict.EXPLOIT_WEAKENED,
        )
        session_dict["debate_history_json"] = json.dumps([summary.model_dump()], default=str)

        reconstructed = PolicyAuditState.from_session_dict(session_dict, original)

        assert reconstructed.current_turn == 2
        assert reconstructed.loop_should_continue is False
        assert len(reconstructed.debate_history) == 1
        assert reconstructed.debate_history[0].exploit_claim == "Exploit claim text"
