"""
Phase 1 — Data Layer: Hierarchical RAG Ingestion Pipeline
==========================================================
ingest_policy.py

This script transforms raw policy PDFs into a searchable, hierarchically-
structured FAISS vector index. It is the foundation of the Automated
Regulatory Robustness Testing system.

Pipeline:
    1. LlamaParse (Cloud API)  →  Structured Markdown extraction
    2. HierarchicalNodeParser  →  Multi-resolution node tree
    3. Vertex AI Embeddings    →  768-dim vector representations
    4. FAISS IndexFlatL2       →  In-memory similarity search
    5. Persist to disk         →  Reusable without re-ingestion

Academic Context:
    Standard flat text splitters (e.g., RecursiveCharacterTextSplitter)
    break documents into equal-sized chunks with no awareness of logical
    structure. In legal text, this is catastrophic — a sub-clause about
    an "exception to Section 4(a)(ii)" becomes meaningless without its
    parent clause. Hierarchical Node Parsing solves this by creating a
    tree of nodes at multiple granularities (2048 → 512 → 128 tokens),
    preserving the parent-child relationships that encode legal context.

    During retrieval (Phase 2), the AutoMergingRetriever leverages this
    tree: if multiple child nodes from the same parent are retrieved, it
    "merges" them back into the parent, returning the complete legal
    section rather than scattered fragments. This is the key innovation
    that makes the adversarial loophole-finding system reliable.

Usage:
    python -m src.ingest_policy

    Expects one or more PDFs in ./data/ (e.g., policy1.pdf, policy2.pdf).
    Outputs a persistent FAISS index to ./storage/faiss/.

Author: Automated Regulatory Robustness Testing Project
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Logging — structured output for pipeline observability
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project imports (config must be imported first to load .env)
# ---------------------------------------------------------------------------
# Add project root to sys.path so `config` is importable when running
# as `python -m src.ingest_policy` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings  # noqa: E402

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
import faiss  # noqa: E402
from llama_cloud import LlamaCloud  # noqa: E402
from llama_index.core import Settings as LlamaSettings  # noqa: E402
from llama_index.core import StorageContext, VectorStoreIndex  # noqa: E402
from llama_index.core.node_parser import (  # noqa: E402
    HierarchicalNodeParser,
    get_leaf_nodes,
)
from llama_index.core.schema import Document  # noqa: E402
from llama_index.embeddings.vertex import VertexTextEmbedding  # noqa: E402
from llama_index.vector_stores.faiss import FaissVectorStore  # noqa: E402


# ===================================================================
# STEP 1: Document Extraction via LlamaCloud Parsing API
# ===================================================================
def extract_documents(data_dir: Path) -> list:
    """
    Extract structured markdown from all PDF files in the data directory
    using the LlamaCloud parsing API (v2 SDK).

    WHY LlamaCloud Parsing?
    ------------------------
    Legal PDFs often contain complex tables (fee schedules, compliance
    matrices), multi-column layouts, and nested numbered lists. Standard
    text extraction (e.g., PyPDF2) destroys this structure. LlamaCloud's
    parsing engine uses cloud-hosted ML models to preserve tables as
    markdown and maintain the logical reading order — critical for
    downstream hierarchical parsing.

    NOTE: The older `llama-parse` package and its `LlamaParse` class
    were deprecated (EOL May 2026). The `llama-cloud>=2.8` SDK uses a
    client-based API: upload via `client.files.create()`, then parse
    via `client.parsing.parse()`. We manually wrap the returned
    markdown pages into LlamaIndex `Document` objects for compatibility
    with the downstream HierarchicalNodeParser.

    Args:
        data_dir: Path to directory containing policy PDFs.

    Returns:
        List of LlamaIndex Document objects with markdown text.
    """
    pdf_files = sorted(data_dir.glob("*.pdf"))

    if not pdf_files:
        logger.error(
            "No PDF files found in %s. "
            "Place your policy PDFs (policy1.pdf, policy2.pdf, ...) there.",
            data_dir,
        )
        raise FileNotFoundError(f"No PDFs found in {data_dir}")

    logger.info(
        "Found %d PDF(s) to process: %s",
        len(pdf_files),
        [f.name for f in pdf_files],
    )

    # Initialize the LlamaCloud client.
    # The client authenticates via the LLAMA_CLOUD_API_KEY.
    client = LlamaCloud(api_key=settings.LLAMA_CLOUD_API_KEY)

    all_documents = []
    for pdf_path in pdf_files:
        logger.info("Parsing: %s ...", pdf_path.name)
        start = time.perf_counter()

        # Step 1: Upload the PDF to LlamaCloud's file store.
        # `purpose="parse"` signals that this file is intended for parsing.
        file_obj = client.files.create(
            file=str(pdf_path),
            purpose="parse",
        )

        # Step 2: Trigger the parse job.
        # - tier="agentic": Uses the highest-quality parsing model,
        #   which is best for complex legal documents with tables.
        # - expand=["markdown"]: Requests markdown-formatted output
        #   (preserves tables, headings, lists as markdown syntax).
        # - version="latest": Always use the most recent parser version.
        # The SDK handles polling internally and returns when parsing
        # is complete.
        result = client.parsing.parse(
            file_id=file_obj.id,
            tier="agentic",
            version="latest",
            expand=["markdown"],
        )

        # Step 3: Convert parsed pages into LlamaIndex Document objects.
        # Each page becomes a separate Document so the downstream
        # HierarchicalNodeParser can chunk them independently.
        # We attach the source filename as metadata for traceability.
        docs = []
        for page_idx, page in enumerate(result.markdown.pages):
            doc = Document(
                text=page.markdown,
                metadata={
                    "file_name": pdf_path.name,
                    "page_number": page_idx + 1,
                    "source": str(pdf_path),
                },
            )
            docs.append(doc)

        elapsed = time.perf_counter() - start
        logger.info(
            "  → Extracted %d page(s) from %s in %.1fs",
            len(docs),
            pdf_path.name,
            elapsed,
        )
        all_documents.extend(docs)

    logger.info("Total documents extracted: %d", len(all_documents))
    return all_documents


# ===================================================================
# STEP 2: Hierarchical Node Parsing
# ===================================================================
def build_hierarchical_nodes(documents: list) -> tuple[list, list]:
    """
    Parse documents into a hierarchical tree of nodes at three
    granularity levels: 2048 → 512 → 128 tokens.

    WHY HIERARCHICAL PARSING? (Academic Justification)
    ---------------------------------------------------
    Legal documents have an inherent tree structure:

        Article 5 (≈2048 tokens)
        ├── Section 5.1 (≈512 tokens)
        │   ├── Clause 5.1(a) (≈128 tokens)
        │   └── Clause 5.1(b) (≈128 tokens)
        └── Section 5.2 (≈512 tokens)
            └── Clause 5.2(a) (≈128 tokens)

    The HierarchicalNodeParser preserves this structure by creating
    explicit parent → child relationships between nodes. Each child
    node stores a reference to its parent's node ID.

    During retrieval, we search ONLY against the leaf nodes (128-token
    chunks) for maximum precision in similarity matching. But when
    multiple leaves from the same parent are retrieved, the
    AutoMergingRetriever (Phase 2) replaces them with the parent node,
    ensuring the LLM sees the complete legal section — not fragments.

    This is the "precision of small chunks + context of large chunks"
    tradeoff that makes hierarchical RAG superior to flat RAG for
    legal analysis.

    Args:
        documents: List of LlamaIndex Document objects.

    Returns:
        Tuple of (all_nodes, leaf_nodes).
        - all_nodes: Every node at every level (for the Docstore).
        - leaf_nodes: Only the smallest chunks (for FAISS indexing).
    """
    logger.info(
        "Building hierarchical node tree with chunk sizes: %s",
        list(settings.CHUNK_SIZES),
    )

    node_parser = HierarchicalNodeParser.from_defaults(
        chunk_sizes=list(settings.CHUNK_SIZES),
    )

    # Generate the full node hierarchy from the documents.
    all_nodes = node_parser.get_nodes_from_documents(documents)

    # Extract only the leaf nodes (smallest granularity = 128 tokens).
    # These are the nodes that will be embedded and indexed in FAISS.
    leaf_nodes = get_leaf_nodes(all_nodes)

    logger.info(
        "Node hierarchy built: %d total nodes, %d leaf nodes",
        len(all_nodes),
        len(leaf_nodes),
    )

    return all_nodes, leaf_nodes


# ===================================================================
# STEP 3: Initialize Embedding Model (Vertex AI or Local Mock)
# ===================================================================
def initialize_embedding_model() -> Any:
    """
    Initialize the embedding model.

    Supports Vertex AI (production) and MockEmbedding (zero-GCP local testing).
    """
    from src.embeddings import get_embedding_model
    return get_embedding_model()


# ===================================================================
# STEP 4 & 5: Build FAISS Index, Store, and Persist
# ===================================================================
def build_and_persist_index(
    all_nodes: list,
    leaf_nodes: list,
    persist_dir: str,
) -> VectorStoreIndex:
    """
    Create a FAISS vector store, embed leaf nodes, store all nodes
    in the Docstore, and persist everything to disk.

    WHY FAISS?
    -----------
    FAISS (Facebook AI Similarity Search) provides exact L2 nearest-
    neighbor search with minimal memory overhead. For a thesis project
    on a low-spec laptop, IndexFlatL2 is ideal:
    - No training required (unlike IVF or HNSW variants)
    - Exact results (no approximation errors)
    - CPU-only (faiss-cpu) — no GPU needed
    - Sub-millisecond search for datasets under 100K vectors

    WHY ONLY LEAF NODES IN FAISS?
    ------------------------------
    We embed only the 128-token leaf nodes because:
    1. Smaller chunks produce more precise similarity scores —
       a query about "penalty for late filing" will match a specific
       sub-clause rather than a broad section.
    2. The parent nodes are stored in the Docstore (not FAISS) and
       are retrieved by the AutoMergingRetriever when needed.
    3. This keeps the FAISS index small and fast.

    Args:
        all_nodes: Complete node hierarchy (for Docstore).
        leaf_nodes: Leaf-level nodes only (for FAISS embedding).
        persist_dir: Directory path to save the index.

    Returns:
        The constructed VectorStoreIndex.
    """
    logger.info("Creating FAISS index (dimension=%d)...", settings.EMBEDDING_DIMENSION)

    # Initialize a flat L2 (Euclidean distance) FAISS index.
    # Dimension must match the embedding model output (768 for text-embedding-004).
    faiss_index = faiss.IndexFlatL2(settings.EMBEDDING_DIMENSION)
    vector_store = FaissVectorStore(faiss_index=faiss_index)

    # Create a StorageContext that wires together:
    # - The FAISS vector store (for leaf node embeddings)
    # - The default Docstore (for ALL nodes, including parents)
    # - The default IndexStore (for index metadata)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # CRITICAL: Add ALL nodes (parents + children) to the Docstore.
    # The AutoMergingRetriever in Phase 2 needs to look up parent nodes
    # by ID when it decides to merge child results. If parents aren't
    # in the Docstore, the merge fails silently and returns fragments.
    storage_context.docstore.add_documents(all_nodes)

    logger.info(
        "Embedding %d leaf nodes via Vertex AI (this may take a moment)...",
        len(leaf_nodes),
    )
    start = time.perf_counter()

    # Build the VectorStoreIndex from ONLY the leaf nodes.
    # This triggers the embedding API calls for each leaf node's text.
    index = VectorStoreIndex(
        nodes=leaf_nodes,
        storage_context=storage_context,
        show_progress=True,
    )

    elapsed = time.perf_counter() - start
    logger.info("Embedding complete in %.1fs", elapsed)

    # Persist everything to disk:
    # - ./storage/faiss/default__vector_store.faiss  (FAISS binary index)
    # - ./storage/faiss/docstore.json                (all nodes with metadata)
    # - ./storage/faiss/index_store.json             (index configuration)
    logger.info("Persisting index to: %s", persist_dir)
    storage_context.persist(persist_dir=persist_dir)

    logger.info("✓ Index persisted successfully.")
    return index


# ===================================================================
# MAIN PIPELINE
# ===================================================================
def main() -> None:
    """
    Execute the full ingestion pipeline:
        PDF → Markdown → Hierarchy → Embeddings → FAISS → Disk
    """
    logger.info("=" * 60)
    logger.info("PHASE 1: Data Layer — Hierarchical RAG Ingestion")
    logger.info("=" * 60)

    # Validate that all required environment variables are set.
    settings.validate()

    pipeline_start = time.perf_counter()

    # Step 1: Extract documents from PDFs
    documents = extract_documents(settings.DATA_DIR)

    # Step 2: Build hierarchical node tree
    all_nodes, leaf_nodes = build_hierarchical_nodes(documents)

    # Step 3: Initialize embedding model
    initialize_embedding_model()

    # Step 4 & 5: Build FAISS index and persist
    build_and_persist_index(all_nodes, leaf_nodes, settings.FAISS_PERSIST_DIR)

    total_elapsed = time.perf_counter() - pipeline_start
    logger.info("=" * 60)
    logger.info("✓ Pipeline complete in %.1fs", total_elapsed)
    logger.info(
        "  Index saved to: %s",
        settings.FAISS_PERSIST_DIR,
    )
    logger.info(
        "  Next step: Start the MCP server with `python -m src.mcp_server`"
    )
    logger.info("=" * 60)



# ===================================================================
# CALLABLE API (for Streamlit / FastAPI / tests)
# ===================================================================
def ingest_document(
    pdf_paths: list[Path | str],
    llama_api_key: str | None = None,
    output_dir: str | Path | None = None,
) -> str:
    """
    Ingest one or more PDFs and build a FAISS index. Returns the persist directory.

    This is the importable entrypoint for Streamlit, FastAPI, and tests.
    The existing ``main()`` CLI function is unchanged.

    Args:
        pdf_paths:     List of PDF file paths to ingest.
        llama_api_key: Override LLAMA_CLOUD_API_KEY for this call.
                       If None, falls back to the global settings value.
        output_dir:    Where to write the FAISS index. Defaults to
                       settings.FAISS_PERSIST_DIR.

    Returns:
        String path to the persisted FAISS index directory.

    Raises:
        FileNotFoundError: If any pdf_path does not exist.
        ValueError:        If no PDF paths are provided.
        EnvironmentError:  If the API key is missing.
    """
    if not pdf_paths:
        raise ValueError("At least one PDF path must be provided.")

    pdf_paths = [Path(p) for p in pdf_paths]
    for p in pdf_paths:
        if not p.exists():
            raise FileNotFoundError(f"PDF not found: {p}")

    # Allow per-call API key override (Mode A: use developer key from env;
    # Mode B: use the key the user pasted into the Streamlit UI).
    effective_api_key = llama_api_key or settings.LLAMA_CLOUD_API_KEY
    if not effective_api_key:
        raise EnvironmentError(
            "LLAMA_CLOUD_API_KEY is not set. "
            "Provide it via the llama_api_key argument or the environment variable."
        )

    persist_dir = str(output_dir) if output_dir else settings.FAISS_PERSIST_DIR

    logger.info("ingest_document() called for: %s", [p.name for p in pdf_paths])

    # ---- Step 1: Parse PDFs via LlamaCloud API ----
    client = LlamaCloud(api_key=effective_api_key)
    all_documents = []
    for pdf_path in pdf_paths:
        logger.info("Parsing: %s ...", pdf_path.name)
        start = time.perf_counter()
        file_obj = client.files.create(file=str(pdf_path), purpose="parse")
        result = client.parsing.parse(
            file_id=file_obj.id,
            tier="agentic",
            version="latest",
            expand=["markdown"],
        )
        docs = [
            Document(
                text=page.markdown,
                metadata={
                    "file_name": pdf_path.name,
                    "page_number": idx + 1,
                    "source": str(pdf_path),
                },
            )
            for idx, page in enumerate(result.markdown.pages)
        ]
        logger.info(
            "  → %d page(s) from %s in %.1fs",
            len(docs), pdf_path.name, time.perf_counter() - start,
        )
        all_documents.extend(docs)

    # ---- Step 2: Hierarchical node parsing ----
    all_nodes, leaf_nodes = build_hierarchical_nodes(all_documents)

    # ---- Step 3: Embedding model ----
    initialize_embedding_model()

    # ---- Step 4 & 5: Build and persist FAISS index ----
    build_and_persist_index(all_nodes, leaf_nodes, persist_dir)

    logger.info("✓ ingest_document() complete. Index at: %s", persist_dir)
    return persist_dir


if __name__ == "__main__":
    main()
