"""
Data Inspection & Verification Script — inspect_storage.py
===========================================================
Use this script to verify that your policy documents were ingested correctly,
check node counts, inspect hierarchical parent-child relationships, and view
sample text chunks stored in `./storage/faiss/`.

Usage:
    # 1. Run overall inspection & summary:
    python -m src.inspect_storage

    # 2. Run a specific test query:
    python -m src.inspect_storage --query "What are the rules for noise levels?"

Author: Automated Regulatory Robustness Testing Project
"""

from __future__ import annotations

import argparse
import json
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
from src.mcp_server import load_index_and_retriever  # noqa: E402


def inspect_docstore(storage_dir: Path) -> None:
    """
    Inspect the raw persisted docstore.json file and display detailed
    structural statistics about parents, children, and metadata.
    """
    docstore_path = storage_dir / "docstore.json"

    if not docstore_path.exists():
        print(f"[X] Error: Docstore file not found at {docstore_path}")
        print("    Run `python -m src.ingest_policy` first to ingest data.")
        return

    print("=" * 70)
    print(f"  INGESTED DATA VERIFICATION SUMMARY ({docstore_path.name})")
    print("=" * 70)

    with open(docstore_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    doc_data = data.get("docstore/data", {})
    if not doc_data:
        print("[!] Warning: Docstore is empty.")
        return

    total_nodes = len(doc_data)
    source_files = set()
    page_numbers = set()
    parent_nodes = []
    child_nodes = []

    for node_id, node_wrapper in doc_data.items():
        node_obj = node_wrapper.get("__data__", {})
        metadata = node_obj.get("metadata", {})
        relationships = node_obj.get("relationships", {})

        if "file_name" in metadata:
            source_files.add(metadata["file_name"])
        if "page_number" in metadata:
            page_numbers.add(metadata["page_number"])

        # Check if node has parent relationship (key '1' = PARENT)
        if "1" in relationships:
            child_nodes.append((node_id, node_obj))
        else:
            parent_nodes.append((node_id, node_obj))

    print(f"STATISTICS:")
    print(f"  * Source Documents : {sorted(list(source_files))}")
    print(f"  * Pages Processed  : {len(page_numbers)}")
    print(f"  * Total Storage    : {total_nodes} nodes in docstore")
    print(f"  * Top Parent Chunks: {len(parent_nodes)} root/parent sections")
    print(f"  * Child Sub-chunks : {len(child_nodes)} fine-grained clauses")
    print("-" * 70)

    if parent_nodes:
        print("\nSAMPLE PARENT NODE (Root Section):")
        sample_id, sample_obj = parent_nodes[0]
        text_snippet = sample_obj.get("text", "")[:350].strip()
        print(f"  Node ID  : {sample_id}")
        print(f"  Metadata : {sample_obj.get('metadata')}")
        print(f"  Preview  :\n    \"{text_snippet}...\"")

    if child_nodes:
        print("\nSAMPLE CHILD NODE (Sub-clause linked to parent):")
        sample_id, sample_obj = child_nodes[0]
        parent_info = sample_obj.get("relationships", {}).get("1", {})
        text_snippet = sample_obj.get("text", "")[:250].strip()
        print(f"  Node ID   : {sample_id}")
        print(f"  Parent ID : {parent_info.get('node_id')}")
        print(f"  Preview   :\n    \"{text_snippet}...\"")

    print("=" * 70)


def test_retrieval(query: str) -> None:
    """Run a test query against the AutoMergingRetriever to verify retrieval."""
    print(f"\nRUNNING TEST RETRIEVAL QUERY:")
    print(f"   Query: \"{query}\"")
    print("-" * 70)

    retriever = load_index_and_retriever(settings.FAISS_PERSIST_DIR)
    results = retriever.retrieve(query)

    print(f"\n[+] Retrieved {len(results)} merged result section(s):")
    for i, res in enumerate(results, start=1):
        content = res.node.get_content()[:400].strip()
        meta = res.node.metadata
        print(f"\n--- Result #{i} (Score: {res.score:.4f}) ---")
        print(f"Metadata: {meta}")
        print(f"Text Preview:\n{content}...\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect ingested FAISS & Docstore data.")
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        help="Optional test search query to run against the retriever.",
        default="",
    )
    args = parser.parse_args()

    storage_path = Path(settings.FAISS_PERSIST_DIR)
    inspect_docstore(storage_path)

    if args.query:
        test_retrieval(args.query)
    else:
        print("\nTIP: Run with `--query \"your test question\"` to test auto-merging search.")


if __name__ == "__main__":
    main()
