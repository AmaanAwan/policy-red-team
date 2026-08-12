"""
Phase 2 — Bridge Layer: MCP Server with AutoMerging Retrieval
==============================================================
mcp_server.py

This module exposes the hierarchical FAISS index (built in Phase 1)
as a standardized tool via the Model Context Protocol (MCP). External
AI agent frameworks (e.g., Google Cloud ADK) can connect to this
server and query policy documents through a clean, typed interface.

Architecture:
    ┌─────────────────┐       stdio / SSE        ┌──────────────────┐
    │  ADK Agent      │ ←───────────────────────→ │  MCP Server      │
    │  (Attacker /    │   JSON-RPC over MCP       │  (this file)     │
    │   Defender /    │                           │                  │
    │   Judge)        │                           │  FastMCP         │
    └─────────────────┘                           │  ├─ Tool:        │
                                                  │  │  search_      │
                                                  │  │  policy_docs  │
                                                  │  └─ Retriever:   │
                                                  │     AutoMerging  │
                                                  │     + FAISS      │
                                                  └──────────────────┘

Academic Context — AutoMergingRetriever:
    The AutoMergingRetriever is the critical link between precise vector
    search and coherent legal reasoning. Here is how it works:

    1. A query is embedded and searched against the FAISS index of
       128-token leaf nodes. The top-k most similar leaves are returned.

    2. The retriever inspects the parent IDs of these leaf nodes. If a
       sufficient proportion of a parent's children were retrieved
       (default threshold: majority), it "merges" them — replacing the
       individual children with the single parent node.

    3. This merge is essential for legal analysis because:
       - A sub-clause like "notwithstanding Section 4(a)" is meaningless
         without the full text of Section 4(a).
       - Fee schedules split across child chunks become complete tables
         when merged back to the parent.
       - The adversarial agents (Attacker/Defender) need complete legal
         sections to construct valid arguments about loopholes.

    The result: the precision of small-chunk retrieval with the
    contextual completeness of large-chunk retrieval.

Usage:
    python -m src.mcp_server

    The server starts in stdio mode by default (for ADK integration).
    Ensure ./storage/faiss/ exists (run ingest_policy.py first).

Author: Automated Regulatory Robustness Testing Project
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings  # noqa: E402

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
from fastmcp import FastMCP  # noqa: E402
from llama_index.core import Settings as LlamaSettings  # noqa: E402
from llama_index.core import StorageContext, load_index_from_storage  # noqa: E402
from llama_index.core.retrievers import AutoMergingRetriever  # noqa: E402
from llama_index.embeddings.vertex import VertexTextEmbedding  # noqa: E402
from llama_index.vector_stores.faiss import FaissVectorStore  # noqa: E402


# ===================================================================
# INDEX LOADING
# ===================================================================
def load_index_and_retriever(
    persist_dir: str,
) -> AutoMergingRetriever:
    """
    Load the persisted FAISS index and Docstore from disk, then
    configure the AutoMergingRetriever.

    This function:
    1. Reconstructs the FaissVectorStore from the binary index file.
    2. Rebuilds the StorageContext (vector store + docstore + index store).
    3. Loads the VectorStoreIndex from storage.
    4. Wraps the base retriever with AutoMergingRetriever.

    WHY AutoMergingRetriever?
    --------------------------
    See module docstring for full academic justification. In brief:
    - Vector search hits small leaf nodes (128 tokens) for precision.
    - AutoMergingRetriever checks if multiple leaves share a parent.
    - If so, it replaces the leaves with the parent node (512 or 2048
      tokens), providing the LLM with coherent, complete legal sections.

    This prevents the "fragmented context" failure mode where an LLM
    receives disconnected sub-clauses and hallucinates connections.

    Args:
        persist_dir: Path to the directory where the index was saved.

    Returns:
        Configured AutoMergingRetriever ready for queries.
    """
    logger.info("Loading persisted index from: %s", persist_dir)

    # --- Embedding model must be re-initialized for the retriever ---
    # Even though we're loading a pre-built index, the retriever needs
    # the embedding model to encode incoming queries at retrieval time.
    from src.embeddings import get_embedding_model
    get_embedding_model()

    # --- Reconstruct the vector store from persisted FAISS binary ---
    vector_store = FaissVectorStore.from_persist_dir(persist_dir=persist_dir)

    # --- Rebuild the full StorageContext ---
    # persist_dir tells LlamaIndex where to find:
    #   - docstore.json (all nodes including parents)
    #   - index_store.json (index metadata)
    # vector_store provides the FAISS binary index.
    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
        persist_dir=persist_dir,
    )

    # --- Load the VectorStoreIndex ---
    index = load_index_from_storage(storage_context=storage_context)

    # --- Create the base retriever (standard FAISS similarity search) ---
    base_retriever = index.as_retriever(
        similarity_top_k=settings.SIMILARITY_TOP_K,
    )

    # --- Wrap with AutoMergingRetriever ---
    # The AutoMergingRetriever intercepts the base retriever's results
    # and applies the parent-merging logic described above.
    # `verbose=True` logs merge decisions for debugging/thesis documentation.
    retriever = AutoMergingRetriever(
        vector_retriever=base_retriever,
        storage_context=storage_context,
        verbose=True,
    )

    logger.info("✓ AutoMergingRetriever initialized (top_k=%d)", settings.SIMILARITY_TOP_K)
    return retriever


# ===================================================================
# MCP SERVER SETUP
# ===================================================================

# Initialize the FastMCP server.
# The name "PolicyRedTeam" is exposed to connecting clients (ADK agents)
# so they can identify which MCP server they are talking to.
mcp = FastMCP("PolicyRedTeam")

# Global retriever — initialized lazily on first tool call.
# We use a global so the FAISS index is loaded once and reused
# across all incoming tool calls (no re-loading per request).
_retriever: AutoMergingRetriever | None = None


def _get_retriever() -> AutoMergingRetriever:
    """Lazy-initialize the retriever on first use."""
    global _retriever
    if _retriever is None:
        settings.validate()
        _retriever = load_index_and_retriever(settings.FAISS_PERSIST_DIR)
    return _retriever


# ===================================================================
# MCP TOOL: search_policy_documents
# ===================================================================
@mcp.tool()
def search_policy_documents(query: str) -> str:
    """
    Search the ingested policy documents for sections relevant to the query.

    This tool performs a hierarchical retrieval:
    1. Encodes the query using Vertex AI text-embedding-004.
    2. Searches the FAISS index for the most similar leaf-level chunks.
    3. Applies auto-merging: if multiple child chunks from the same parent
       section were retrieved, they are replaced with the complete parent
       section to preserve legal context.

    Use this tool to find specific policy clauses, definitions, penalties,
    exemptions, or any regulatory text relevant to a legal argument.

    Args:
        query: A natural-language question about the policy
               (e.g., "What are the penalties for non-compliance
               with Section 4?").

    Returns:
        A Markdown-formatted string containing the retrieved policy
        sections, separated by horizontal rules. Each section includes
        source metadata when available.
    """
    logger.info("Tool called: search_policy_documents(query='%s')", query[:100])

    retriever = _get_retriever()

    # Execute the retrieval pipeline:
    # query → embed → FAISS search → auto-merge → results
    retrieved_nodes = retriever.retrieve(query)

    if not retrieved_nodes:
        logger.warning("No results found for query: '%s'", query[:100])
        return "No relevant policy sections found for the given query."

    logger.info("Retrieved %d node(s) after auto-merging.", len(retrieved_nodes))

    # Format the results as a concatenated Markdown string.
    # Each retrieved section is separated by a horizontal rule for clarity.
    # The adversarial agents (Attacker/Defender/Judge) will parse this
    # Markdown to construct their legal arguments.
    sections: list[str] = []
    for i, node_with_score in enumerate(retrieved_nodes, start=1):
        node = node_with_score.node
        score = node_with_score.score

        # Build a header with source info and relevance score
        source_info = node.metadata.get("file_name", "Unknown Source")
        header = f"### Retrieved Section {i} (Source: {source_info}, Score: {score:.4f})"

        # The node's text content — this is the actual policy text,
        # potentially auto-merged from multiple child chunks into
        # a complete parent section.
        content = node.get_content()

        sections.append(f"{header}\n\n{content}")

    result = "\n\n---\n\n".join(sections)
    logger.info(
        "Returning %d sections (%d chars total).",
        len(sections),
        len(result),
    )
    return result


# ===================================================================
# ENTRY POINT
# ===================================================================
if __name__ == "__main__":
    import argparse

    # ---------------------------------------------------------------------------
    # CLI arguments — transport mode selection
    # ---------------------------------------------------------------------------
    # Phase 2 (stdio): python -m src.mcp_server
    # Phase 3 (SSE):   python -m src.mcp_server --transport sse --port 8090
    #
    # WHY TWO MODES?
    # stdio transport is serial (one request at a time) — correct for Phase 2
    # where a single agent calls the tool sequentially.
    # SSE transport supports concurrent HTTP requests — required for Phase 3
    # where ParallelAgent runs CitizenProxy + BusinessProxy simultaneously.
    # Running both against the same stdio pipe would cause a deadlock.
    # ---------------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description="PolicyRedTeam MCP Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help=(
            "MCP transport mode. "
            "Use 'stdio' for Phase 2 single-agent testing (serial). "
            "Use 'sse' for Phase 3 multi-agent orchestration (concurrent)."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address for SSE transport (ignored in stdio mode).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8090,
        help="Port for SSE transport (ignored in stdio mode).",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("PHASE 2/3: Bridge Layer — MCP Server")
    logger.info("=" * 60)
    logger.info("Transport mode: %s", args.transport.upper())
    logger.info(
        "FAISS index location: %s",
        settings.FAISS_PERSIST_DIR,
    )

    if args.transport == "sse":
        logger.info(
            "SSE endpoint: http://%s:%d/sse",
            args.host, args.port,
        )
        logger.info(
            "Phase 3 ADK agents connect to this endpoint via MCPToolset."
        )
        logger.info("=" * 60)
        # SSE mode: HTTP server accepting concurrent requests.
        # All Phase 3 agents (Attacker, Defender, Citizen, Business)
        # call search_policy_documents concurrently via this endpoint.
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        logger.info(
            "Stdio mode: reading JSON-RPC from stdin, writing to stdout."
        )
        logger.info("Connect your ADK agents to this server via stdio.")
        logger.info("=" * 60)
        # stdio mode: serial pipe — Phase 2 single-agent usage.
        mcp.run()
