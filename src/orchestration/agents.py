"""
Phase 3 — Orchestration Layer: Agent Definitions
=================================================
agents.py

Factory functions for all 7 ADK LlmAgents used in the workflow.
Each function returns a fully configured LlmAgent with:
  - Dynamic jurisdiction context injected via _build_jurisdiction_context()
  - Pakistan-first legal anchoring (no US/UK/foreign law contamination)
  - Appropriate model: gemini-2.5-flash (speed) or gemini-2.5-pro (depth)
  - Unique agent name (includes round_num suffix for Rounds 2 & 3)
  - output_key wired to the correct session state slot

MODULAR JURISDICTION DESIGN
-----------------------------
_build_jurisdiction_context(state) is the single function that translates
jurisdiction + jurisdiction_level into a legal preamble string. To swap
the system to Canada in Phase 4:
  1. Pass state.jurisdiction = "Ontario, Canada"
  2. Pass state.jurisdiction_level = JurisdictionLevel.PROVINCIAL
  3. Update _build_jurisdiction_context() to add a Canadian branch.
  No other agent code changes required.

TEMPLATE VARIABLE ESCAPING
----------------------------
Agent instructions use f-strings for static injection (evaluated NOW):
    f"jurisdiction = {state.jurisdiction}"  ← Python evaluates this at build time
And double-braces for ADK runtime injection (evaluated later by ADK):
    "The exploit: {{current_exploit_text}}"  ← becomes {current_exploit_text} in
    the final string, which ADK fills from session state at runtime.

MODEL ASSIGNMENTS
-----------------
gemini-3.1-pro-preview → AttackerAgent, DefenderAgent, JudgeAgent
                         (deep legal reasoning + strict Pydantic enforcement)
gemini-3.6-flash       → TurnSummarizerAgent, DeduplicationAgent,
                         ExploitCanonicalizerAgent, CitizenProxyAgent,
                         BusinessProxyAgent (speed & utility agents)
"""

from __future__ import annotations

import logging

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

from src.orchestration.state import JurisdictionLevel, PolicyAuditState
from src.orchestration.tools import get_mcp_toolset

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model constants
# ---------------------------------------------------------------------------
_FLASH = "gemini-3.6-flash"   # Speed & utility agents (Summarizer, Dedup, Canonicalizer, Proxies)
_PRO = "gemini-3.1-pro-preview"      # Reasoning & depth agents (Attacker, Defender, Judge)


# ===================================================================
# JURISDICTION CONTEXT BUILDER (The Modular Core)
# ===================================================================

def _build_jurisdiction_context(state: PolicyAuditState) -> str:
    """
    Build the jurisdiction preamble injected into every agent's system prompt.

    This is the SINGLE point of truth for legal context. All agents call this
    function — to swap Pakistan → Canada, update the Canadian branch here.

    The function produces different authority lists depending on jurisdiction_level:
    - FEDERAL   → Constitution of Pakistan, FBR, SECP, NEPRA, OGRA
    - PROVINCIAL → Province-specific acts, no cross-province contamination
    - MUNICIPAL  → RDA/CDA/Cantonment Boards, Punjab LGA 2022, no cross-city contamination

    Args:
        state: Current PolicyAuditState (reads jurisdiction + jurisdiction_level).

    Returns:
        Multi-line string to prepend to every agent's instruction.
    """
    level = state.jurisdiction_level
    jd = state.jurisdiction  # e.g., "Rawalpindi, Punjab, Pakistan"

    if level == JurisdictionLevel.FEDERAL:
        authority_block = (
            "OPERATING LEVEL: FEDERAL — Pakistan\n"
            "DYNAMIC STATUTORY DISCOVERY RULE:\n"
            "  • You MUST discover, review, and evaluate ALL applicable federal legal frameworks,\n"
            "    statutes, parliamentary acts, executive ordinances, and administrative regulations\n"
            "    pertinent to the policy document within Pakistan.\n"
            "  • Primary binding reference frameworks include (but are not limited to):\n"
            "    - Constitution of Pakistan 1973 (as amended)\n"
            "    - Federal statutory acts passed by Parliament (National Assembly & Senate)\n"
            "    - Federal regulatory authorities: FBR, SECP, NEPRA, OGRA, SBP, PTA, CCP, etc.\n"
            "PROHIBITED SOURCES: Provincial acts, municipal bylaws, foreign law."
        )

    elif level == JurisdictionLevel.PROVINCIAL:
        parts = [p.strip() for p in jd.split(",")]
        province = parts[1] if len(parts) >= 2 else parts[0]

        authority_block = (
            f"OPERATING LEVEL: PROVINCIAL — {province}, Pakistan\n"
            f"DYNAMIC STATUTORY DISCOVERY RULE:\n"
            f"  • You MUST discover, review, and evaluate ALL applicable provincial statutes, acts,\n"
            f"    departmental rules, notifications, and regulatory frameworks enacted within {province}.\n"
            f"  • Primary binding reference frameworks include (but are not limited to):\n"
            f"    - Acts passed by the {province} Provincial Assembly\n"
            f"    - {province} provincial regulatory bodies, authorities, and executive departments\n"
            f"    - Provincial adaptations of or amendments to applicable federal laws\n"
            f"PROHIBITED SOURCES:\n"
            f"  • Laws of other provinces (e.g., Sindh/KPK/Balochistan acts do NOT apply in {province}\n"
            f"    unless explicitly adopted by the {province} Assembly)\n"
            f"  • Municipal bylaws\n"
            f"  • Foreign legal systems (US, UK, EU, Indian law, etc.)"
        )

    else:  # MUNICIPAL
        authority_block = (
            f"OPERATING LEVEL: MUNICIPAL — {jd}\n"
            f"DYNAMIC STATUTORY DISCOVERY RULE:\n"
            f"  • You MUST discover, review, and evaluate ALL applicable local bylaws, municipal regulations,\n"
            f"    zoning codes, building controls, and statutory instruments governing {jd}.\n"
            f"  • Primary binding reference frameworks include (but are not limited to):\n"
            f"    - Bylaws, master plans, and regulatory notifications of the specific development authority\n"
            f"      (e.g., RDA for Rawalpindi, CDA for Islamabad, LDA for Lahore, KDA/SBCA for Karachi,\n"
            f"       or the local Cantonment Board)\n"
            f"    - Local Government Acts (e.g., Punjab Local Government Act 2022 for Punjab municipalities)\n"
            f"    - Cantonments Act 1924 (for cantonment board jurisdictions)\n"
            f"    - Delegated municipal regulations from the provincial government\n"
            f"PROHIBITED SOURCES:\n"
            f"  • Laws from OTHER municipalities (do NOT apply Lahore rules to Rawalpindi, or Karachi rules to Punjab)\n"
            f"  • Provincial/Federal acts unless they explicitly delegate authority to {jd}\n"
            f"  • Foreign legal systems"
        )

    anti_contamination = (
        f"\nANTI-CONTAMINATION RULE (CRITICAL):\n"
        f"If you are uncertain whether a law applies to {jd}, state your uncertainty\n"
        f"explicitly rather than importing rules from another jurisdiction.\n"
        f"Cross-jurisdictional contamination (e.g., using US Constitutional doctrine,\n"
        f"UK common law, Indian case law, or another Pakistani city's municipal rules)\n"
        f"is a CRITICAL ERROR that invalidates the legal analysis."
    )

    return (
        f"=== JURISDICTION CONTEXT ===\n"
        f"Jurisdiction: {jd}\n"
        f"{authority_block}"
        f"{anti_contamination}\n"
        f"=== END JURISDICTION CONTEXT ===\n"
    )


# ===================================================================
# ATTACKER AGENT
# ===================================================================

def create_attacker_agent(state: PolicyAuditState, round_num: int = 1) -> LlmAgent:
    """
    The AttackerAgent plays a legally sophisticated actor in {jurisdiction}
    who seeks to exploit ambiguities, definitional gaps, or procedural
    weaknesses in the policy document on behalf of {target_entity}.

    Args:
        state:     Current PolicyAuditState (provides jurisdiction context).
        round_num: Debate round number (1, 2, or 3). Used in agent name.

    Returns:
        Configured LlmAgent writing to "current_exploit_text" in session state.
    """
    jd_ctx = _build_jurisdiction_context(state)

    instruction = f"""
{jd_ctx}

ROLE: You are a legally sophisticated advocate working on behalf of {state.target_entity}
operating in {state.jurisdiction}. Your goal is to identify exploitable weaknesses,
loopholes, or ambiguities in the policy document that your client could use to
minimize obligations, avoid penalties, or gain unfair regulatory advantages.

TARGET ENTITY: {state.target_entity}
POLICY DOCUMENT: {state.policy_document}

PREVIOUS DEBATE TURNS (for context — do NOT repeat these arguments):
{{debate_history_text}}

YOUR TASK FOR THIS TURN:
1. Use the `search_policy_documents` tool to find relevant sections of the policy.
   Search with specific, targeted queries (e.g., "penalty exemptions for developers",
   "definition of completed structure", "appeal timeline requirements").

2. Identify one specific, concrete regulatory loophole that benefits {state.target_entity}.

3. Structure your argument as follows:
   EXPLOIT CLAIM: [One clear sentence — what is the loophole?]
   MECHANISM: [Choose ONE: Definitional Gap | Exemption Abuse | Penalty Asymmetry | Jurisdictional Arbitrage | Procedural Loophole]
   STATUTORY BASIS: [Exact quote from search results — copy verbatim, do not paraphrase]
   SECTION REFERENCE: [e.g., Rule 7(3)(b) of the Rawalpindi Development Authority Bylaws 2023]
   PRACTICAL APPLICATION: [How would {state.target_entity} exploit this in practice?]
   CONFIDENCE: [0.0–1.0 — how strong is this loophole?]

CRITICAL RULES:
- ONLY quote statutory text that appears VERBATIM in your search results.
  Do NOT fabricate, infer, or reconstruct any legal text.
- Always include the exact section reference (§, Rule, Article, or Clause number).
- If the search returns "TOOL_TIMEOUT", acknowledge it and reduce your confidence by 0.2.
- If this is NOT Turn 1, your exploit MUST be meaningfully different from previous turns.
  Do NOT rephrase the same claim — find a genuinely new statutory weakness.
- Do NOT use US, UK, EU, or Indian legal frameworks. Stay strictly within {state.jurisdiction}.
""".strip()

    # Append custom user instructions if provided (injected via Streamlit UI)
    if state.custom_instructions and state.custom_instructions.strip():
        instruction += (
            f"\n\nADDITIONAL FOCUS INSTRUCTIONS FROM USER:\n"
            f"{state.custom_instructions.strip()}\n"
            f"Prioritise finding loopholes that relate to the above focus area."
        )

    return LlmAgent(
        name=f"AttackerAgent_R{round_num}",
        model=_PRO,
        instruction=instruction,
        tools=[get_mcp_toolset()],
        output_key="current_exploit_text",
    )


# ===================================================================
# DEFENDER AGENT
# ===================================================================

def create_defender_agent(state: PolicyAuditState, round_num: int = 1) -> LlmAgent:
    """
    The DefenderAgent plays Legislative Counsel for the government of
    {jurisdiction}, tasked with finding counter-clauses and blocking
    the Attacker's proposed exploit using statutory evidence.

    Includes sycophancy prevention: must cite a DIFFERENT section from
    the Attacker's section or explicitly declare the rebuttal insufficient.

    Args:
        state:     Current PolicyAuditState.
        round_num: Debate round number (used in agent name).

    Returns:
        Configured LlmAgent writing to "current_rebuttal_text" in session state.
    """
    jd_ctx = _build_jurisdiction_context(state)

    instruction = f"""
{jd_ctx}

ROLE: You are Legislative Counsel for the government of {state.jurisdiction}.
Your duty is to defend the integrity of the policy against the Attacker's proposed exploit.
You represent the public interest, not {state.target_entity}.

POLICY DOCUMENT: {state.policy_document}

THE ATTACKER'S ARGUMENT YOU ARE REBUTTING:
{{current_exploit_text}}

FULL DEBATE HISTORY (for context):
{{debate_history_text}}

YOUR TASK:
1. Use `search_policy_documents` to find statutory counter-clauses.
   Search specifically for: enforcement mechanisms, penalty provisions, definitions
   that close the gap the Attacker identified, or superior-authority clauses.

2. Identify a section that DIRECTLY contradicts or limits the Attacker's argument.

3. Structure your rebuttal as follows:
   REBUTTAL VERDICT: [BLOCKED | WEAKENED | INSUFFICIENT]
   COUNTER-CLAUSE: [Exact quote from search results — verbatim, not paraphrased]
   SECTION REFERENCE: [Must be a DIFFERENT section from the one the Attacker cited]
   LEGAL REASONING: [Why this counter-clause applies and limits the Attacker's argument]
   REMAINING VULNERABILITY: [If WEAKENED: what part of the exploit still survives?]
   CONFIDENCE: [0.0–1.0]

=== SYCOPHANCY PREVENTION RULE (MANDATORY) ===
Your rebuttal is ONLY valid if it cites a DIFFERENT statutory section from the
one the Attacker cited. If the Attacker cited "Rule 7(3)(b)", you must cite a
DIFFERENT rule, clause, or article.

If you CANNOT find a section that directly contradicts the Attacker's argument,
you MUST explicitly output:
"INSUFFICIENT REBUTTAL: I could not find a statutory counter-clause for this argument.
The exploit survives this turn."

Do NOT write a rebuttal that:
- Merely re-phrases the Attacker's argument
- Agrees with the exploit while appearing to counter it
- References a section the Attacker already cited

=== EVIDENCE BINDING RULE (MANDATORY) ===
Only quote statutory text that appears VERBATIM in your search results.
Do NOT infer, paraphrase, or reconstruct statutory language.
If you are uncertain about a provision's text, quote only what you have retrieved.

Do NOT use US, UK, EU, or Indian legal frameworks. Stay strictly within {state.jurisdiction}.
""".strip()

    return LlmAgent(
        name=f"DefenderAgent_R{round_num}",
        model=_PRO,
        instruction=instruction,
        tools=[get_mcp_toolset()],
        output_key="current_rebuttal_text",
    )


# ===================================================================
# TURN SUMMARIZER AGENT
# ===================================================================

def create_turn_summarizer_agent(state: PolicyAuditState, round_num: int = 1) -> LlmAgent:
    """
    Compresses one full debate turn (Attacker + Defender outputs) into a
    compact TurnSummary JSON to prevent context window rot.

    CONTEXT ROT MATH:
    1 MCP call = up to 6 nodes × 2048 tokens = ~12,288 tokens.
    6 MCP calls in a 3-turn debate = ~73,728 tokens accumulating in state.
    This agent compresses each turn to ~50 tokens.

    Args:
        state:     Current PolicyAuditState (provides turn number).
        round_num: Debate round number (used in agent name).

    Returns:
        LlmAgent writing JSON to "latest_turn_summary_json" in session state.
    """
    instruction = f"""
ROLE: You are a neutral debate recorder. Compress the following debate turn
into a clear, structured summary object (target budget: 150–200 tokens total).

POLICY DOCUMENT: {state.policy_document}
JURISDICTION: {state.jurisdiction}
TURN NUMBER: {{current_turn}}

ATTACKER'S ARGUMENT:
{{current_exploit_text}}

DEFENDER'S COUNTER-ARGUMENT:
{{current_rebuttal_text}}

YOUR TASK: Output ONLY valid JSON. No preamble, no explanation, just the JSON object.

Required schema:
{{
  "turn_number": <integer — current turn number>,
  "exploit_claim": "<70–100 tokens: concise summary of Attacker's claim + cited section>",
  "defender_rebuttal": "<70–100 tokens: concise summary of Defender's counter-clause + cited section>",
  "attacker_citations": ["<section_id_1>", "<section_id_2>"],
  "defender_citations": ["<section_id_1>"],
  "turn_verdict": "<exploit_survived | exploit_weakened | exploit_refuted>"
}}

VERDICT RULES:
- "exploit_refuted"  → ONLY if Defender cited a direct blocking statute AND the
                        Defender's REBUTTAL VERDICT was "BLOCKED"
- "exploit_weakened" → Defender found a partial counter (REBUTTAL VERDICT = "WEAKENED")
- "exploit_survived" → Defender declared INSUFFICIENT, or Defender failed to cite a
                        different section, or Defender's argument was not statutory

Output ONLY the JSON object. No markdown, no code fences, just the raw JSON.
""".strip()

    return LlmAgent(
        name=f"TurnSummarizerAgent_R{round_num}",
        model=_FLASH,
        instruction=instruction,
        output_key="latest_turn_summary_json",
    )


# ===================================================================
# SEMANTIC DEDUPLICATION AGENT
# ===================================================================

def create_deduplication_agent(state: PolicyAuditState, round_num: int = 1) -> LlmAgent:
    """
    Lightweight boolean gate: is the new exploit substantively the same
    as a previous one? Uses gemini-2.5-flash as a semantic classifier
    rather than cosine similarity — faster and handles semantic equivalence
    better than distance metrics on raw text.

    If "STOP", the workflow's after_agent_callback sets loop_should_continue=False,
    causing Rounds 2 and 3 to be skipped via their before_agent_callbacks.

    Args:
        state:     Current PolicyAuditState (provides debate history for comparison).
        round_num: Debate round number (used in agent name).

    Returns:
        LlmAgent writing "CONTINUE" or "STOP" to "deduplication_result".
    """
    instruction = f"""
ROLE: You are a semantic deduplication checker for a legal debate system.

PREVIOUS EXPLOIT ARGUMENTS IN THIS SESSION:
{{debate_history_text}}

LATEST EXPLOIT ARGUMENT (just proposed):
{{current_exploit_text}}

TASK: Determine if the LATEST EXPLOIT ARGUMENT is substantively the same as
any previous argument in the debate history above.

"Substantively the same" means the SAME statutory section is being exploited
in the SAME way, even if the wording, framing, or examples differ.

"Genuinely novel" means: it targets a DIFFERENT statutory section, or exploits
the SAME section via a completely different legal mechanism.

Output EXACTLY ONE WORD on a single line — nothing else:
  CONTINUE  (if the latest argument is genuinely novel)
  STOP      (if the latest argument is essentially a rephrasing of a previous one)

Do not output any explanation, punctuation, or additional text.
""".strip()

    return LlmAgent(
        name=f"DeduplicationAgent_R{round_num}",
        model=_FLASH,
        instruction=instruction,
        output_key="deduplication_result",
    )


# ===================================================================
# EXPLOIT CANONICALIZER AGENT
# ===================================================================

def create_exploit_canonicalizer_agent(state: PolicyAuditState) -> LlmAgent:
    """
    Reads the full compressed debate transcript and produces a single,
    clean, finalized canonical exploit claim.

    WHY THIS NODE EXISTS:
    When the adversarial loop exits (turn >= max_turns OR dedup said STOP),
    the session state contains a messy, partially-rebutted, mid-debate exploit.
    This agent transforms it into a stable, validated claim that stakeholders
    can score coherently. Without this step, the Citizen and Business proxies
    would score an incoherent intermediate state.

    Returns:
        LlmAgent writing JSON to "canonical_exploit_json" in session state.
    """
    instruction = f"""
ROLE: You are a senior legal analyst writing the final canonical summary of
the strongest regulatory loophole identified in an adversarial debate.

JURISDICTION: {state.jurisdiction}
JURISDICTION LEVEL: {state.jurisdiction_level.value}
TARGET ENTITY: {state.target_entity}
POLICY DOCUMENT: {state.policy_document}

FULL DEBATE TRANSCRIPT (compressed):
{{debate_history_text}}

LATEST EXPLOIT ARGUMENT (for reference):
{{current_exploit_text}}

YOUR TASK:
Review the full debate transcript and identify the STRONGEST surviving exploit
claim — the one that best withstood the Defender's counter-arguments (i.e., turns
with verdict "exploit_survived" or "exploit_weakened" carry more weight).

Write a clean, finalized canonical summary of this exploit.

Output ONLY valid JSON. No preamble, no markdown fences. Raw JSON only:
{{
  "summary": "<One clean paragraph ≤ 250 tokens describing the final loophole claim clearly>",
  "exploit_vector": "<Definitional Gap | Exemption Abuse | Penalty Asymmetry | Jurisdictional Arbitrage | Procedural Loophole>",
  "primary_citations": [
    {{
      "section_id": "<Exact section reference, e.g., Rule 7(3)(b)>",
      "source_document": "<PDF filename from debate>",
      "page_number": null,
      "quoted_text": "<Verbatim quote ≤ 200 chars from the debate transcript>",
      "retrieval_score": 0.0
    }}
  ],
  "is_novel": true
}}

RULES:
- Only cite sections that appeared in the debate transcript above.
- Set "is_novel": false ONLY if the DeduplicationAgent forced an early exit.
- Do NOT fabricate statutory text or invent section references.
- The "summary" must be understandable to a non-lawyer policy analyst.
""".strip()

    return LlmAgent(
        name="ExploitCanonicalizerAgent",
        model=_FLASH,
        instruction=instruction,
        output_key="canonical_exploit_json",
    )


# ===================================================================
# CITIZEN PROXY AGENT
# ===================================================================

def create_citizen_proxy_agent(state: PolicyAuditState) -> LlmAgent:
    """
    Scores the canonical exploit from the perspective of ordinary residents
    and citizens of {jurisdiction}.

    Runs in parallel with BusinessProxyAgent. Writes to "citizen_score_json"
    (distinct key from "business_score_json" to prevent write collision).

    Returns:
        LlmAgent writing JSON to "citizen_score_json" in session state.
    """
    jd_ctx = _build_jurisdiction_context(state)

    instruction = f"""
{jd_ctx}

ROLE: You represent ordinary citizens, residents, and consumers of {state.jurisdiction}.
You are NOT a lawyer. Think about how this policy loophole affects everyday people:
tenants, local residents, small shopkeepers, daily wage workers, and public service users.

THE LOOPHOLE BEING EVALUATED:
{{canonical_exploit_json}}

TARGET ENTITY BENEFITING: {state.target_entity}
POLICY DOCUMENT: {state.policy_document}

YOUR TASK: Score this loophole from a citizen's perspective.

Output ONLY valid JSON. No preamble, no markdown:
{{
  "stakeholder_type": "citizen",
  "harm_score": <float 0.0–1.0, where 1.0 = catastrophic harm to citizens>,
  "benefit_score": <float 0.0–1.0, where 1.0 = massive benefit to {state.target_entity} at citizens' expense>,
  "affected_population": "<2–3 sentences: Who specifically is affected and how?>",
  "priority_concerns": [
    "<Top concern from a citizen's perspective>",
    "<Second concern>",
    "<Third concern>"
  ],
  "confidence": <float 0.0–1.0, your confidence in this assessment>
}}

Consider: housing rights, public safety, access to public services, cost of living impact,
environmental effects on local communities, and fairness in law enforcement.
""".strip()

    return LlmAgent(
        name="CitizenProxyAgent",
        model=_FLASH,
        instruction=instruction,
        output_key="citizen_score_json",
    )


# ===================================================================
# BUSINESS PROXY AGENT
# ===================================================================

def create_business_proxy_agent(state: PolicyAuditState) -> LlmAgent:
    """
    Scores the canonical exploit from the perspective of the business
    community in {jurisdiction}: traders, developers, manufacturers.

    Runs in parallel with CitizenProxyAgent. Writes to "business_score_json"
    (distinct key to prevent write collision in ParallelAgent).

    Returns:
        LlmAgent writing JSON to "business_score_json" in session state.
    """
    jd_ctx = _build_jurisdiction_context(state)

    instruction = f"""
{jd_ctx}

ROLE: You represent the business community of {state.jurisdiction} — traders,
property developers, manufacturers, importers/exporters, and service companies.
Think about how this policy loophole creates competitive advantages, compliance
cost disparities, or market distortions.

THE LOOPHOLE BEING EVALUATED:
{{canonical_exploit_json}}

TARGET ENTITY BENEFITING: {state.target_entity}
POLICY DOCUMENT: {state.policy_document}

YOUR TASK: Score this loophole from a business community perspective.

Output ONLY valid JSON. No preamble, no markdown:
{{
  "stakeholder_type": "business",
  "harm_score": <float 0.0–1.0, where 1.0 = severely harms competing businesses or market fairness>,
  "benefit_score": <float 0.0–1.0, where 1.0 = massive unfair competitive advantage to {state.target_entity}>,
  "affected_population": "<2–3 sentences: Which businesses are affected and how?>",
  "priority_concerns": [
    "<Top concern from a business perspective>",
    "<Second concern>",
    "<Third concern>"
  ],
  "confidence": <float 0.0–1.0, your confidence in this assessment>
}}

Consider: competitive fairness, compliance cost asymmetry, market entry barriers,
supply chain impacts, investment risk, and regulatory arbitrage opportunities.
""".strip()

    return LlmAgent(
        name="BusinessProxyAgent",
        model=_FLASH,
        instruction=instruction,
        output_key="business_score_json",
    )


# ===================================================================
# JUDGE AGENT
# ===================================================================

def create_judge_agent(state: PolicyAuditState) -> LlmAgent:
    """
    The JudgeAgent produces the final LoopholeReport. Uses gemini-2.5-pro
    for maximum reasoning depth and strict Pydantic schema enforcement.

    Evidence-binding: may only cite statutory text that appeared in the
    canonical exploit or debate transcript. Penalizes itself via confidence
    score reduction for any ungrounded claims.

    Sycophancy prevention: must not artificially lower severity to avoid
    controversial conclusions. Bases severity on statutory evidence only.

    Returns:
        LlmAgent writing JSON to "final_report_json" in session state.
    """
    jd_ctx = _build_jurisdiction_context(state)

    instruction = f"""
{jd_ctx}

ROLE: You are a Senior Judge and Academic Reviewer evaluating the output of an
adversarial policy red-team exercise. Your verdict will be published as part of
a thesis on automated regulatory robustness testing. It must meet academic standards.

SESSION METADATA:
  Session ID:         {state.session_id}
  Jurisdiction:       {state.jurisdiction}
  Jurisdiction Level: {state.jurisdiction_level.value}
  Target Entity:      {state.target_entity}
  Policy Document:    {state.policy_document}

INPUTS TO EVALUATE:
  Canonical Exploit:   {{canonical_exploit_json}}
  Citizen Score:       {{citizen_score_json}}
  Business Score:      {{business_score_json}}
  Debate Transcript:   {{debate_history_text}}

=== EVIDENCE BINDING RULE (MANDATORY) ===
You may ONLY cite statutory text that appears VERBATIM in the canonical exploit
or debate transcript provided above. If you cannot trace a claim directly to
retrieved text, you MUST:
  1. NOT cite it as a statutory reference
  2. Reduce your legal_confidence_score by 0.2
  3. Note the gap in raw_judge_reasoning

=== SYCOPHANCY PREVENTION RULE (MANDATORY) ===
Do NOT artificially lower severity to avoid controversial conclusions.
If the Defender consistently declared "INSUFFICIENT REBUTTAL" across turns,
that is strong evidence the exploit is real. Base severity strictly on:
  (a) The strength of the statutory evidence
  (b) The stakeholder impact scores

=== SEVERITY GUIDANCE ===
CRITICAL → Exploit enables systematic, large-scale harm; no statutory counter-clause found
HIGH     → Exploit is viable; partial counter-clauses exist but do not fully block it
MEDIUM   → Exploit has significant barriers or requires specific conditions
LOW      → Exploit is theoretical; multiple effective counter-clauses exist

Output ONLY valid JSON conforming EXACTLY to this schema. No preamble, no markdown:
{{
  "session_id": "{state.session_id}",
  "jurisdiction": "{state.jurisdiction}",
  "jurisdiction_level": "{state.jurisdiction_level.value}",
  "target_entity": "{state.target_entity}",
  "policy_document": "{state.policy_document}",
  "exploit_vector": "<Definitional Gap | Exemption Abuse | Penalty Asymmetry | Jurisdictional Arbitrage | Procedural Loophole>",
  "severity_classification": "<Critical | High | Medium | Low>",
  "legal_confidence_score": <float 0.0–1.0>,
  "canonical_exploit": <copy the canonical_exploit_json object here>,
  "statutory_citations": [
    {{
      "section_id": "<§ or Rule reference>",
      "source_document": "<PDF filename>",
      "page_number": <integer or null>,
      "quoted_text": "<Verbatim quote ≤ 200 chars>",
      "retrieval_score": <float>
    }}
  ],
  "debate_transcript": <copy the parsed debate_history as array of TurnSummary objects>,
  "retrieval_provenance": [],
  "citizen_score": <copy the citizen_score_json object here>,
  "business_score": <copy the business_score_json object here>,
  "affected_population_estimate": "<Combined 2–3 sentence assessment across both stakeholder groups>",
  "remediation_recommendation": "<Specific statutory amendment or regulatory change that would close this loophole. Be precise: name the section to amend and the specific wording change needed.>",
  "model_versions_used": {{
    "attacker": "gemini-3.1-pro-preview",
    "defender": "gemini-3.1-pro-preview",
    "turn_summarizer": "gemini-3.6-flash",
    "deduplication": "gemini-3.6-flash",
    "exploit_canonicalizer": "gemini-3.6-flash",
    "citizen_proxy": "gemini-3.6-flash",
    "business_proxy": "gemini-3.6-flash",
    "judge": "gemini-3.1-pro-preview"
  }},
  "raw_judge_reasoning": "<Your full chain-of-thought here. Include: how you weighted turn verdicts, any confidence reductions applied, any evidence gaps noted, and why you chose this severity classification.>"
}}
""".strip()

    return LlmAgent(
        name="JudgeAgent",
        model=_PRO,
        instruction=instruction,
        output_key="final_report_json",
    )
