"""
Phase 3 — Orchestration Layer: State Management
=================================================
state.py

Defines every Pydantic model used by the ADK multi-agent workflow,
from atomic citation objects up to the final LoopholeReport.

IMMUTABILITY CONTRACT
---------------------
All models use ConfigDict(frozen=True). This means:
  - Fields cannot be mutated after creation.
  - Collections are tuple, NOT list, to prevent accidental .append().
  - State transitions: new_state = state.model_copy(update={...})

ADK SESSION STATE INTEGRATION
------------------------------
ADK's InMemorySessionService stores state as a flat Python dict.
PolicyAuditState.to_session_dict()  → produces that flat dict.
PolicyAuditState.from_session_dict() → reconstructs from it post-run.

ADK template substitution reads from session state keys at runtime.
Agent instructions use {{variable}} double-braces (Python f-string escaping)
so they become single-brace {variable} in the final string for ADK to fill.

JURISDICTION DESIGN
-------------------
jurisdiction + jurisdiction_level are the single source of truth for legal context.
To swap Pakistan → Canada: only change these values at session initialization.
No agent code requires modification — all prompts inject from these fields.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ===================================================================
# ENUMERATIONS
# ===================================================================

class ExploitVector(str, Enum):
    """
    Taxonomy of HOW a regulatory loophole operates.
    Enables cross-policy pattern analysis in the thesis.
    """
    DEFINITIONAL_GAP = "Definitional Gap"
    EXEMPTION_ABUSE = "Exemption Abuse"
    PENALTY_ASYMMETRY = "Penalty Asymmetry"
    JURISDICTIONAL_ARBITRAGE = "Jurisdictional Arbitrage"
    PROCEDURAL_LOOPHOLE = "Procedural Loophole"


class SeverityClassification(str, Enum):
    """
    Loophole severity. Analogous to CVSS severity taxonomy in cybersecurity.
    Enables ranking and prioritization of findings across multiple audits.
    """
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class JurisdictionLevel(str, Enum):
    """
    Level of governance the policy operates under — determines which
    legal frameworks agents are bound to (see agents.py for injection logic).

    FEDERAL   → Constitution of Pakistan 1973, FBR, SECP, NEPRA, OGRA
    PROVINCIAL → Punjab / Sindh / KPK / Balochistan provincial acts
    MUNICIPAL  → RDA, CDA, LDA, Cantonment Boards, Punjab LGA 2022
    """
    FEDERAL = "Federal"
    PROVINCIAL = "Provincial"
    MUNICIPAL = "Municipal"


class TurnVerdict(str, Enum):
    """Outcome of a single adversarial debate turn."""
    EXPLOIT_SURVIVED = "exploit_survived"    # Defender could not find a counter-clause
    EXPLOIT_WEAKENED = "exploit_weakened"    # Defender found a partial counter
    EXPLOIT_REFUTED = "exploit_refuted"      # Defender found a direct blocking statute


# ===================================================================
# ATOMIC DATA MODELS
# ===================================================================

class StatutoryCitation(BaseModel):
    """
    A single statutory reference extracted from MCP search results.

    Preserves the full provenance chain:
        query → FAISS similarity search → AutoMerge → node metadata → citation

    The retrieval_score field comes directly from the MCP server's Markdown output:
        mcp_server.py line 246: "Score: {score:.4f}"

    WHY THIS MATTERS:
    - Prevents the Judge from hallucinating statutory references.
    - Allows a human reviewer to trace any claim back to the original document.
    - The retrieval_score quantifies how semantically relevant the retrieved text was.
    """
    model_config = ConfigDict(frozen=True)

    section_id: str           # e.g., "§ 4(a)(ii)", "Rule 7(3)(b)", "Article 25"
    source_document: str      # PDF filename from LlamaIndex node metadata
    page_number: int | None   # Page number, if available in node metadata
    quoted_text: str          # Exact verbatim quote — max 200 characters
    retrieval_score: float    # FAISS similarity score (0.0–1.0)


class RetrievalTrace(BaseModel):
    """
    Full audit trail for one search_policy_documents MCP tool call.

    Required for academic reproducibility: every factual claim in the
    LoopholeReport must be traceable to a specific retrieval event.
    """
    model_config = ConfigDict(frozen=True)

    agent_role: str                               # "AttackerAgent", "DefenderAgent", etc.
    turn_number: int
    query: str                                    # Exact query string sent to MCP
    raw_response_length: int                      # Character count of MCP response
    citations_extracted: tuple[StatutoryCitation, ...]


class TurnSummary(BaseModel):
    """
    Compressed summary of one complete debate turn (Attacker + Defender outputs).

    CONTEXT WINDOW ROT PREVENTION:
    One MCP tool call returns up to 6 auto-merged nodes × 2048 tokens = ~12,288 tokens.
    Across 6 tool calls in a 3-turn debate = ~73,728 tokens of raw policy text in state.
    TurnSummary compresses each turn to ~50 tokens, preventing context window rot.

    The TurnSummarizerAgent produces this JSON. An after_agent_callback parses it
    and appends it to the debate_history in session state.
    """
    model_config = ConfigDict(frozen=True)

    turn_number: int
    exploit_claim: str              # ≤ 150 tokens — Attacker's core argument
    defender_rebuttal: str          # ≤ 150 tokens — Defender's counter-argument
    attacker_citations: tuple[str, ...]  # Section IDs cited by Attacker
    defender_citations: tuple[str, ...]  # Section IDs cited by Defender (must differ)
    turn_verdict: TurnVerdict


class CanonicalExploit(BaseModel):
    """
    The clean, validated exploit claim produced by ExploitCanonicalizerAgent.

    WHY THIS IS NECESSARY:
    When the adversarial loop exits at turn >= max_turns, the working exploit
    in session state is mid-debate — partially rebutted, unstable. The
    ExploitCanonicalizerAgent reads the full debate transcript and produces
    this single, clean, finalized claim. Stakeholder Proxies score THIS
    object, not the raw debate state.
    """
    model_config = ConfigDict(frozen=True)

    summary: str                                        # ≤ 250 tokens, one clean paragraph
    exploit_vector: ExploitVector
    primary_citations: tuple[StatutoryCitation, ...]    # Supporting evidence from debate
    is_novel: bool                                      # False if dedup check forced early exit


class StakeholderScore(BaseModel):
    """
    Structured impact scoring from one stakeholder perspective.

    PARALLEL EXECUTION DESIGN:
    CitizenProxyAgent writes to session key "citizen_score_json".
    BusinessProxyAgent writes to session key "business_score_json".
    These are DISTINCT keys to prevent write collisions in ParallelAgent.
    """
    model_config = ConfigDict(frozen=True)

    stakeholder_type: Literal["citizen", "business"]
    harm_score: float                      # 0.0–1.0 (1.0 = catastrophic harm to this group)
    benefit_score: float                   # 0.0–1.0 (1.0 = massive benefit to exploiter)
    affected_population: str               # Narrative description of who is affected
    priority_concerns: tuple[str, ...]     # 3–5 key concerns from this perspective
    confidence: float                      # 0.0–1.0


# ===================================================================
# FINAL OUTPUT: LoopholeReport
# ===================================================================

class LoopholeReport(BaseModel):
    """
    The canonical output of one complete red-team audit session.

    Designed to meet academic publication standards for public policy research.
    Every field either contributes to the finding or to its reproducibility.

    KEY ACADEMIC FIELDS (often absent in prototype systems):
    - statutory_citations: Full provenance chain with FAISS scores
    - legal_confidence_score: Quantitative Judge confidence for statistical analysis
    - exploit_vector: 5-type taxonomy enabling cross-policy pattern analysis
    - retrieval_provenance: Every MCP call traceable to a specific query
    - debate_transcript: Compressed but complete record of adversarial exchange
    - model_versions_used: Critical for reproducibility in thesis appendix
    """
    model_config = ConfigDict(frozen=True)

    # --- Session identity ---
    session_id: str
    jurisdiction: str
    jurisdiction_level: JurisdictionLevel
    target_entity: str
    policy_document: str

    # --- Core finding ---
    exploit_vector: ExploitVector
    severity_classification: SeverityClassification
    legal_confidence_score: float               # 0.0–1.0, assigned by JudgeAgent
    canonical_exploit: CanonicalExploit

    # --- Evidence chain (required for academic validity) ---
    statutory_citations: tuple[StatutoryCitation, ...]   # All cited sections
    debate_transcript: tuple[TurnSummary, ...]            # Full compressed debate
    retrieval_provenance: tuple[RetrievalTrace, ...]      # All MCP calls made

    # --- Stakeholder impact ---
    citizen_score: StakeholderScore
    business_score: StakeholderScore
    affected_population_estimate: str            # Combined cross-stakeholder narrative

    # --- Remediation ---
    remediation_recommendation: str             # Specific statutory amendment to close gap

    # --- Reproducibility metadata ---
    model_versions_used: dict[str, str]         # {"attacker": "gemini-3.1-pro-preview", ...}
    raw_judge_reasoning: str                    # Full Judge chain-of-thought


# ===================================================================
# SESSION STATE (ADK-COMPATIBLE)
# ===================================================================

class PolicyAuditState(BaseModel):
    """
    Immutable session state that flows through the ADK multi-agent workflow.

    HOW ADK SESSION STATE WORKS:
    ADK's InMemorySessionService stores state as a flat Python dict.
    Agents read from it via template substitution in their instructions:
        instruction="... {current_exploit_text} ..."
    ADK fills this at runtime from session_state["current_exploit_text"].

    This class provides:
    - to_session_dict(): Convert to the flat dict ADK needs at session start.
    - from_session_dict(): Reconstruct a typed state object after the run.

    JURISDICTION DESIGN (MODULAR):
    jurisdiction + jurisdiction_level are the only fields that change between
    Pakistan and Canada contexts. All agent prompts inject from these fields
    via _build_jurisdiction_context() in agents.py.
    Phase 4 swap: change these two fields at runner.py initialization. Done.
    """
    model_config = ConfigDict(frozen=True)

    # --- Session identity ---
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    jurisdiction: str                         # e.g., "Rawalpindi, Punjab, Pakistan"
    jurisdiction_level: JurisdictionLevel     # Federal / Provincial / Municipal
    target_entity: str                        # e.g., "Real Estate Developers"
    policy_document: str                      # Filename of the ingested PDF
    # Optional free-text instructions from the user (e.g., "Focus on fee schedule gaps").
    # Injected into AttackerAgent prompt when non-empty.
    custom_instructions: str = ""

    # --- Adversarial loop control ---
    current_turn: int = 0
    max_turns: int = 3
    loop_should_continue: bool = True

    # --- Accumulated history ---
    debate_history: tuple[TurnSummary, ...] = ()
    retrieval_provenance: tuple[RetrievalTrace, ...] = ()

    # --- Post-loop state ---
    canonical_exploit: CanonicalExploit | None = None
    citizen_score: StakeholderScore | None = None
    business_score: StakeholderScore | None = None

    # --- Final output ---
    final_report: LoopholeReport | None = None

    def to_session_dict(self) -> dict:
        """
        Convert to a flat dict for ADK's InMemorySessionService.

        All keys referenced by agent instruction templates are pre-populated
        (even if empty) so ADK doesn't encounter missing key errors.
        """
        return {
            # Identity (static, read by agents via template substitution)
            "session_id": self.session_id,
            "jurisdiction": self.jurisdiction,
            "jurisdiction_level": self.jurisdiction_level.value,
            "target_entity": self.target_entity,
            "policy_document": self.policy_document,
            "custom_instructions": self.custom_instructions,

            # Loop control (updated by after_agent_callbacks)
            "current_turn": self.current_turn,
            "max_turns": self.max_turns,
            "loop_should_continue": self.loop_should_continue,

            # Working state — filled in by agents during the run
            "current_exploit_text": "",
            "current_rebuttal_text": "",
            "latest_turn_summary_json": "{}",
            "deduplication_result": "CONTINUE",

            # Debate history — updated by TurnSummarizer callback
            "debate_history_text": _format_history_as_text(self.debate_history),
            "debate_history_json": json.dumps(
                [t.model_dump() for t in self.debate_history], default=str
            ),

            # Agent output slots — filled in during the run
            "canonical_exploit_json": "{}",
            "citizen_score_json": "{}",
            "business_score_json": "{}",
            "final_report_json": "{}",
        }

    @classmethod
    def from_session_dict(
        cls,
        session_dict: dict,
        original: "PolicyAuditState",
    ) -> "PolicyAuditState":
        """
        Reconstruct a typed PolicyAuditState from a completed ADK session dict.
        Uses the original for immutable identity fields (jurisdiction, etc.).
        """
        # Rebuild debate history from JSON
        history_json = session_dict.get("debate_history_json", "[]")
        try:
            history_data = json.loads(history_json) if history_json else []
            debate_history = tuple(TurnSummary(**t) for t in history_data)
        except (json.JSONDecodeError, TypeError):
            debate_history = original.debate_history

        # Attempt to parse final report
        final_report = None
        report_json = session_dict.get("final_report_json", "{}")
        if report_json and report_json != "{}":
            try:
                final_report = LoopholeReport.model_validate_json(report_json)
            except Exception:
                pass

        return original.model_copy(update={
            "current_turn": session_dict.get("current_turn", original.current_turn),
            "loop_should_continue": session_dict.get("loop_should_continue", True),
            "debate_history": debate_history,
            "final_report": final_report,
        })


# ===================================================================
# HELPERS
# ===================================================================

def _format_history_as_text(history: tuple[TurnSummary, ...]) -> str:
    """
    Format debate history as a human-readable string for agent template injection.
    Called by to_session_dict() and by the TurnSummarizer after_agent_callback.
    """
    if not history:
        return "No previous debate turns."

    parts: list[str] = []
    for turn in history:
        a_cites = ", ".join(turn.attacker_citations) or "None cited"
        d_cites = ", ".join(turn.defender_citations) or "None cited"
        parts.append(
            f"--- Turn {turn.turn_number} (Verdict: {turn.turn_verdict.value}) ---\n"
            f"Attacker: {turn.exploit_claim}\n"
            f"  Attacker cited: {a_cites}\n"
            f"Defender: {turn.defender_rebuttal}\n"
            f"  Defender cited: {d_cites}"
        )
    return "\n\n".join(parts)
