"""
Phase 3 — Orchestration Layer: Workflow Graph
==============================================
workflow.py

Assembles all agents into a SequentialAgent DAG that ADK can execute.

WORKFLOW GRAPH:
---------------
START
  │
  ├─► DebateRound1 (SequentialAgent — always runs)
  │     ├─► AttackerAgent_R1  → writes current_exploit_text
  │     ├─► DefenderAgent_R1  → writes current_rebuttal_text
  │     ├─► TurnSummarizerAgent_R1 → writes latest_turn_summary_json
  │     │   [after_agent_callback: parse JSON, append TurnSummary, increment turn]
  │     └─► DeduplicationAgent_R1 → writes deduplication_result (CONTINUE/STOP)
  │         [after_agent_callback: if STOP → set loop_should_continue=False]
  │
  ├─► DebateRound2 (SequentialAgent — skipped if loop_should_continue=False)
  │   [before_agent_callback: check loop_should_continue flag]
  │     ├─► AttackerAgent_R2
  │     ├─► DefenderAgent_R2
  │     ├─► TurnSummarizerAgent_R2
  │     └─► DeduplicationAgent_R2
  │
  ├─► DebateRound3 (SequentialAgent — skipped if loop_should_continue=False)
  │   [before_agent_callback: check loop_should_continue flag]
  │     ├─► AttackerAgent_R3
  │     ├─► DefenderAgent_R3
  │     ├─► TurnSummarizerAgent_R3
  │     └─► DeduplicationAgent_R3
  │
  ├─► ExploitCanonicalizerAgent
  │     [Reads full debate_history_text, writes canonical_exploit_json]
  │
  ├─► StakeholderSwarm (ParallelAgent — runs concurrently on SSE MCP server)
  │     ├─► CitizenProxyAgent  → writes citizen_score_json
  │     └─► BusinessProxyAgent → writes business_score_json
  │
  └─► JudgeAgent (gemini-2.5-pro)
        [Reads all outputs, writes final_report_json]
  │
DONE

KEY DESIGN DECISIONS:
- Manual 3-round structure (vs LoopAgent) for reliable conditional exit.
  Rounds 2 & 3 have before_agent_callback that checks loop_should_continue.
  When False, the callback returns Content to skip the round immediately.
- after_agent_callback on TurnSummarizer parses JSON and updates debate history.
- after_agent_callback on DeduplicationAgent sets loop_should_continue=False on STOP.
- ParallelAgent for stakeholders only — adversarial agents are sequential
  (each needs the other's output to respond coherently).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from google.adk.agents import (
    LlmAgent,
    ParallelAgent,
    SequentialAgent,
)
from google.adk.agents.callback_context import CallbackContext
from google.genai import types as genai_types

from src.orchestration.agents import (
    create_attacker_agent,
    create_business_proxy_agent,
    create_citizen_proxy_agent,
    create_deduplication_agent,
    create_exploit_canonicalizer_agent,
    create_defender_agent,
    create_judge_agent,
    create_turn_summarizer_agent,
)
from src.orchestration.state import (
    PolicyAuditState,
    TurnSummary,
    TurnVerdict,
    _format_history_as_text,
)

logger = logging.getLogger(__name__)


# ===================================================================
# CALLBACK FACTORIES
# ===================================================================

def _make_loop_guard_callback(round_num: int):
    """
    Returns a before_agent_callback that short-circuits a SequentialAgent
    round if loop_should_continue is False in session state.

    Usage: Attach to DebateRound2 and DebateRound3 SequentialAgents.

    When the callback returns genai_types.Content, ADK skips that agent's
    execution and uses the returned Content as its output.
    When it returns None, execution proceeds normally.

    Args:
        round_num: For logging clarity only.
    """
    def guard(
        callback_context: CallbackContext,
    ) -> Optional[genai_types.Content]:
        should_continue = callback_context.state.get("loop_should_continue", True)
        if not should_continue:
            logger.info(
                "Loop guard: skipping DebateRound%d — "
                "loop_should_continue=False (deduplication terminated loop early).",
                round_num,
            )
            return genai_types.Content(
                role="model",
                parts=[
                    genai_types.Part(
                        text=(
                            f"[DEBATE ROUND {round_num} SKIPPED] "
                            "The deduplication check determined the latest exploit was not novel. "
                            "The debate loop has been terminated early. "
                            "Proceeding to ExploitCanonicalizerAgent with current transcript."
                        )
                    )
                ],
            )
        return None  # Proceed with agent execution

    return guard


def _make_after_summarizer_callback(round_num: int):
    """
    Returns an after_agent_callback that runs after TurnSummarizerAgent.

    Responsibilities:
    1. Parse the latest_turn_summary_json from session state.
    2. Construct a TurnSummary object and validate it.
    3. Append it to debate_history_json (the persistent list).
    4. Update debate_history_text (the human-readable string for template injection).
    5. Increment current_turn counter.

    This callback is what makes context compression work — it replaces
    ~12,000 tokens of raw MCP output with a ~50-token TurnSummary per turn.

    Args:
        round_num: For logging clarity.
    """
    def callback(
        callback_context: CallbackContext,
    ) -> Optional[genai_types.Content]:
        summary_json_str = callback_context.state.get("latest_turn_summary_json", "{}")

        try:
            summary_data = json.loads(summary_json_str)
            if not summary_data or not isinstance(summary_data, dict):
                logger.warning(
                    "TurnSummarizer_R%d: Empty or invalid JSON in latest_turn_summary_json.",
                    round_num,
                )
                return None

            # Validate turn verdict value
            raw_verdict = summary_data.get("turn_verdict", "exploit_survived")
            try:
                verdict = TurnVerdict(raw_verdict)
            except ValueError:
                verdict = TurnVerdict.EXPLOIT_SURVIVED
                logger.warning(
                    "TurnSummarizer_R%d: Unknown verdict '%s', defaulting to exploit_survived.",
                    round_num, raw_verdict,
                )

            # Build TurnSummary (validates types)
            turn_summary = TurnSummary(
                turn_number=summary_data.get(
                    "turn_number",
                    callback_context.state.get("current_turn", round_num)
                ),
                exploit_claim=summary_data.get("exploit_claim", ""),
                defender_rebuttal=summary_data.get("defender_rebuttal", ""),
                attacker_citations=tuple(summary_data.get("attacker_citations", [])),
                defender_citations=tuple(summary_data.get("defender_citations", [])),
                turn_verdict=verdict,
            )

            # Append to running history JSON list
            existing_json = callback_context.state.get("debate_history_json", "[]")
            try:
                existing_list = json.loads(existing_json) if existing_json else []
            except json.JSONDecodeError:
                existing_list = []

            existing_list.append(turn_summary.model_dump(mode="json"))
            callback_context.state["debate_history_json"] = json.dumps(
                existing_list, default=str
            )

            # Rebuild text representation for template injection in future agents
            all_summaries = tuple(TurnSummary(**t) for t in existing_list)
            callback_context.state["debate_history_text"] = _format_history_as_text(
                all_summaries
            )

            # Increment turn counter
            current = callback_context.state.get("current_turn", 0)
            callback_context.state["current_turn"] = current + 1

            logger.info(
                "TurnSummarizer_R%d callback: Turn %d archived. Verdict: %s. "
                "History now has %d turn(s).",
                round_num, turn_summary.turn_number, verdict.value, len(existing_list),
            )

        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.error(
                "TurnSummarizer_R%d callback: Failed to parse summary JSON: %s",
                round_num, exc,
            )

        return None  # Do not override the agent's output

    return callback


def _make_after_dedup_callback(round_num: int):
    """
    Returns an after_agent_callback that runs after DeduplicationAgent.

    Reads deduplication_result from session state and sets
    loop_should_continue=False if the result is "STOP".

    This is the mechanism that enables early exit from the debate loop
    without relying on LoopAgent internals or escalation actions.

    Args:
        round_num: For logging clarity.
    """
    def callback(
        callback_context: CallbackContext,
    ) -> Optional[genai_types.Content]:
        raw_result = callback_context.state.get("deduplication_result", "CONTINUE")
        result = raw_result.strip().upper()

        if result == "STOP":
            callback_context.state["loop_should_continue"] = False
            current_turn = callback_context.state.get("current_turn", round_num)
            logger.info(
                "DeduplicationAgent_R%d: STOP — duplicate exploit detected at turn %d. "
                "loop_should_continue set to False. Rounds %d+ will be skipped.",
                round_num, current_turn, round_num + 1,
            )
        else:
            logger.info(
                "DeduplicationAgent_R%d: CONTINUE — novel argument detected.",
                round_num,
            )

        return None  # Do not override the agent's output

    return callback


# ===================================================================
# DEBATE ROUND BUILDER
# ===================================================================

def _build_debate_round(
    state: PolicyAuditState,
    round_num: int,
    use_guard: bool,
) -> SequentialAgent:
    """
    Build one complete debate round as a SequentialAgent:
      AttackerAgent → DefenderAgent → TurnSummarizerAgent → DeduplicationAgent

    Args:
        state:     Current PolicyAuditState (provides jurisdiction + round context).
        round_num: Round number (1, 2, or 3). Controls agent names + callbacks.
        use_guard: If True, attaches a before_agent_callback that skips this
                   entire round when loop_should_continue=False.

    Returns:
        A fully configured SequentialAgent for this debate round.
    """
    attacker = create_attacker_agent(state, round_num=round_num)
    defender = create_defender_agent(state, round_num=round_num)
    summarizer = create_turn_summarizer_agent(state, round_num=round_num)
    dedup = create_deduplication_agent(state, round_num=round_num)

    # Attach state-management callbacks to summarizer and dedup
    summarizer.after_agent_callback = _make_after_summarizer_callback(round_num)
    dedup.after_agent_callback = _make_after_dedup_callback(round_num)

    # Build the round as a SequentialAgent
    round_agent = SequentialAgent(
        name=f"DebateRound{round_num}",
        sub_agents=[attacker, defender, summarizer, dedup],
    )

    # Attach loop guard to Rounds 2 and 3
    if use_guard:
        round_agent.before_agent_callback = _make_loop_guard_callback(round_num)

    return round_agent


# ===================================================================
# MAIN WORKFLOW BUILDER
# ===================================================================

def build_workflow(state: PolicyAuditState) -> SequentialAgent:
    """
    Assemble the complete multi-agent policy audit workflow as a
    SequentialAgent DAG.

    This is the root agent passed to the ADK Runner in runner.py.

    The workflow is statically configured at initialization time — agent
    instructions are compiled with jurisdiction context from `state`. Dynamic
    content (exploit text, debate history, etc.) flows through ADK session
    state at runtime via template substitution.

    Args:
        state: The initial PolicyAuditState. Used to inject jurisdiction
               context into agent instructions at build time. Must be fully
               initialized (jurisdiction, target_entity, policy_document set).

    Returns:
        Root SequentialAgent representing the complete workflow.
    """
    logger.info(
        "Building workflow for session %s | jurisdiction=%s (%s) | entity=%s",
        state.session_id,
        state.jurisdiction,
        state.jurisdiction_level.value,
        state.target_entity,
    )

    # --- Adversarial Debate Rounds ---
    # Round 1 always runs. Rounds 2 & 3 have loop guards.
    round1 = _build_debate_round(state, round_num=1, use_guard=False)
    round2 = _build_debate_round(state, round_num=2, use_guard=True)
    round3 = _build_debate_round(state, round_num=3, use_guard=True)

    # --- Exploit Canonicalization ---
    # Transforms mid-debate messy state → clean, stable exploit claim
    canonicalizer = create_exploit_canonicalizer_agent(state)

    # --- Stakeholder Impact Scoring (Parallel) ---
    # CitizenProxy and BusinessProxy run concurrently via SSE MCP server.
    # Each writes to a DISTINCT session key to prevent write collisions.
    stakeholder_swarm = ParallelAgent(
        name="StakeholderSwarm",
        sub_agents=[
            create_citizen_proxy_agent(state),
            create_business_proxy_agent(state),
        ],
    )

    # --- Final Verdict (gemini-2.5-pro) ---
    judge = create_judge_agent(state)

    # --- Root Workflow ---
    workflow = SequentialAgent(
        name="PolicyAuditWorkflow",
        sub_agents=[
            round1,
            round2,
            round3,
            canonicalizer,
            stakeholder_swarm,
            judge,
        ],
    )

    logger.info(
        "Workflow assembled: %d top-level nodes. "
        "Agent lineup: 3 debate rounds × 4 agents + Canonicalizer + 2 Proxies + Judge = 16 agents total.",
        len(workflow.sub_agents),
    )

    return workflow
