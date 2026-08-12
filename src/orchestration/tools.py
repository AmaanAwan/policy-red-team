"""
Phase 3 — Orchestration Layer: ADK Tool Definitions
=====================================================
tools.py

Three responsibilities:
1. MCPToolset factory  — creates an ADK MCPToolset pointed at the local
   SSE MCP server so agents can call search_policy_documents.
2. Response parser     — extracts StatutoryCitation objects from the MCP
   server's Markdown output, preserving the provenance data (source
   filename, FAISS score, page number) that mcp_server.py already emits
   but that agents would otherwise silently discard.
3. Retry wrapper       — async function for programmatic MCP calls with
   exponential backoff, used in post-processing callbacks.

WHY SSE TRANSPORT?
------------------
The original mcp_server.py uses stdio (serial pipe, one caller at a time).
Phase 3's ParallelAgent runs CitizenProxyAgent and BusinessProxyAgent
concurrently — both would call search_policy_documents simultaneously,
deadlocking on a stdio pipe. SSE (Server-Sent Events) on localhost:8090
allows unlimited concurrent HTTP requests without blocking.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re

from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseConnectionParams

from src.orchestration.state import RetrievalTrace, StatutoryCitation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection settings
# ---------------------------------------------------------------------------
MCP_SERVER_HOST = "127.0.0.1"
MCP_SERVER_PORT = 8090
MCP_SERVER_URL = f"http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}/sse"
MCP_TOOL_TIMEOUT_SECONDS = 60


# ---------------------------------------------------------------------------
# MCP Markdown response parsing patterns
# ---------------------------------------------------------------------------
# Matches the header line emitted by mcp_server.py:
#   ### Retrieved Section N (Source: filename.pdf, Score: 0.8523)
_SECTION_HEADER_RE = re.compile(
    r"###\s+Retrieved Section \d+\s*\("
    r"Source:\s*(?P<source>[^,]+),\s*"
    r"Score:\s*(?P<score>[\d.]+)\)"
)

# Matches page references in retrieved text, e.g., "Page 12" or "page: 12"
_PAGE_RE = re.compile(r"[Pp]age[:\s]+(\d+)")

# Matches Pakistani legal citation patterns:
# § 4(a)(ii), Rule 7(3)(b), Section 12, Article 25, Clause 4, Schedule III
_SECTION_ID_RE = re.compile(
    r"(?:"
    r"§\s*[\w.()\-]+|"
    r"Section\s+[\w.()\-]+|"
    r"Rule\s+[\w.()\-]+|"
    r"Article\s+[\w.()\-]+|"
    r"Clause\s+[\w.()\-]+|"
    r"Schedule\s+[\w.()\-]+|"
    r"Regulation\s+[\w.()\-]+"
    r")"
)


# ===================================================================
# MCPToolset Factory
# ===================================================================

def get_mcp_toolset() -> MCPToolset:
    """
    Create an ADK MCPToolset connected to the PolicyRedTeam MCP server
    running in SSE mode on localhost:8090.

    This toolset is passed to LlmAgent(tools=[...]) in agents.py.
    ADK automatically exposes all tools registered on the MCP server
    (i.e., search_policy_documents) to the agent.

    Returns:
        MCPToolset instance ready for use in LlmAgent constructor.
    """
    return MCPToolset(
        connection_params=SseConnectionParams(url=MCP_SERVER_URL),
    )


# ===================================================================
# MCP Response Parser
# ===================================================================

def parse_mcp_response(
    raw_response: str,
    agent_role: str,
    turn_number: int,
    query: str,
) -> RetrievalTrace:
    """
    Parse the Markdown-formatted response from search_policy_documents
    into structured StatutoryCitation objects.

    This function extracts the provenance data that mcp_server.py embeds
    in every response but that agents would otherwise discard after
    consuming the text.

    The MCP server emits this format (mcp_server.py lines 246–253):
        ### Retrieved Section N (Source: policy.pdf, Score: 0.8523)

        [Full legal text of the auto-merged node...]

        ---

    Args:
        raw_response:  Full Markdown string from the MCP tool call.
        agent_role:    Which agent made this call (for the trace record).
        turn_number:   Current debate turn number.
        query:         Exact query string sent to the tool.

    Returns:
        RetrievalTrace with all StatutoryCitation objects extracted.
    """
    citations: list[StatutoryCitation] = []

    # Split on section headers, preserving the named groups (source, score)
    blocks = _SECTION_HEADER_RE.split(raw_response)
    # split() with groups yields: [pre, source1, score1, text1, source2, score2, text2, ...]
    i = 1
    while i + 2 <= len(blocks):
        source = blocks[i].strip()
        try:
            score = float(blocks[i + 1].strip())
        except (ValueError, IndexError):
            score = 0.0

        content = blocks[i + 2].strip() if i + 2 < len(blocks) else ""

        # Extract page number from content
        page_match = _PAGE_RE.search(content)
        page_number = int(page_match.group(1)) if page_match else None

        # Extract Pakistani legal section identifiers
        section_ids = _SECTION_ID_RE.findall(content)

        if section_ids:
            # Create one citation per identified section, capped at 3 per block
            for sid in section_ids[:3]:
                quote = content[:200].replace("\n", " ").strip()
                citations.append(
                    StatutoryCitation(
                        section_id=sid.strip(),
                        source_document=source,
                        page_number=page_number,
                        quoted_text=quote,
                        retrieval_score=score,
                    )
                )
        elif content:
            # No explicit section ID found — generic provenance record
            quote = content[:200].replace("\n", " ").strip()
            citations.append(
                StatutoryCitation(
                    section_id="[Unidentified Section]",
                    source_document=source,
                    page_number=page_number,
                    quoted_text=quote,
                    retrieval_score=score,
                )
            )

        i += 3  # advance past (source, score, content) triple

    logger.debug(
        "parse_mcp_response: extracted %d citations from %d chars (agent=%s, turn=%d)",
        len(citations), len(raw_response), agent_role, turn_number,
    )

    return RetrievalTrace(
        agent_role=agent_role,
        turn_number=turn_number,
        query=query,
        raw_response_length=len(raw_response),
        citations_extracted=tuple(citations),
    )


# ===================================================================
# Async Retry Wrapper
# ===================================================================

async def search_with_retry(
    mcp_client,
    query: str,
    max_retries: int = 3,
) -> str:
    """
    Call the search_policy_documents MCP tool with exponential backoff retry.

    Used in post-processing callbacks and runner utilities where programmatic
    tool calls are needed outside of agent execution context.

    Agents themselves retry via their LLM reasoning loop — this wrapper is
    for infrastructure-level resilience.

    Args:
        mcp_client:   ADK MCPToolset client (or compatible async callable).
        query:        Natural-language query for the policy search.
        max_retries:  Maximum retry attempts before returning sentinel value.

    Returns:
        Raw Markdown response string, or "TOOL_TIMEOUT: ..." sentinel.
        Agents are instructed to treat TOOL_TIMEOUT as a soft failure:
        proceed with reduced confidence, do not halt, do not fabricate text.
    """
    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(
                mcp_client.call_tool(
                    "search_policy_documents",
                    {"query": query},
                ),
                timeout=float(MCP_TOOL_TIMEOUT_SECONDS),
            )
            return result
        except (TimeoutError, asyncio.TimeoutError):
            jitter = random.uniform(0.0, 0.3)
            wait = 0.5 * (2 ** attempt) + jitter
            logger.warning(
                "MCP tool timeout (attempt %d/%d, query='%.60s...'). Retrying in %.2fs.",
                attempt + 1, max_retries, query, wait,
            )
            await asyncio.sleep(wait)
        except Exception as exc:
            wait = 0.5 * (2 ** attempt)
            logger.error(
                "MCP tool error (attempt %d/%d): %s. Retrying in %.2fs.",
                attempt + 1, max_retries, exc, wait,
            )
            await asyncio.sleep(wait)

    logger.error(
        "All %d MCP retry attempts exhausted for query: '%.80s'",
        max_retries, query,
    )
    return (
        "TOOL_TIMEOUT: Could not retrieve policy sections after multiple attempts. "
        "Proceed with reduced confidence. "
        "Do NOT fabricate statutory text or section references. "
        "Reduce legal_confidence_score by 0.2 for any claim you cannot ground in prior retrieved text."
    )
