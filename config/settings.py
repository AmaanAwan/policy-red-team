"""
Centralized Configuration — settings.py
========================================
Single source of truth for all environment variables and constants.
Loads credentials from `.env` at import time so no module needs to
call `load_dotenv()` independently.

Usage:
    from config.settings import settings
    print(settings.GCP_PROJECT)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Resolve project root (two levels up from config/settings.py)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root — silently skip if not present
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Disable NLTK's CWD import security hook.
# Academic/Technical note: NLTK's inisec module inspects whether imported
# packages resolve to paths relative to CWD. When running inside a virtual
# environment (venv) created inside the project root, site-packages
# (e.g., venv/Lib/site-packages/regex) resides inside CWD, causing NLTK
# to falsely flag valid dependencies as CWD hijacking.
os.environ["NLTK_DISABLE_IMPORT_SECURITY"] = "1"

# Enable Vertex AI mode only if project ID is present AND it is not explicitly disabled
if os.environ.get("GOOGLE_CLOUD_PROJECT") and os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() != "false":
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"


# ---------------------------------------------------------------------------
# Settings Dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment variables."""

    # --- LlamaCloud / LlamaParse ---
    LLAMA_CLOUD_API_KEY: str = field(
        default_factory=lambda: os.environ.get("LLAMA_CLOUD_API_KEY", "")
    )

    # --- Google Cloud Platform ---
    GCP_PROJECT: str = field(
        default_factory=lambda: os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    )
    GCP_LOCATION: str = field(
        default_factory=lambda: os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    )

    # --- Embedding Model ---
    EMBEDDING_PROVIDER: str = field(
        default_factory=lambda: os.environ.get("EMBEDDING_PROVIDER", "vertex")
    )
    EMBEDDING_MODEL_NAME: str = "text-embedding-004"
    EMBEDDING_DIMENSION: int = 768  # text-embedding-004 default output dim

    # --- Hierarchical Chunking ---
    # Academic rationale: These three tiers map to the typical structure of
    # legal documents — (1) full sections/articles, (2) individual clauses,
    # and (3) sub-clauses or definitions. This preserves the logical nesting
    # that flat chunking destroys.
    CHUNK_SIZES: tuple[int, ...] = (2048, 512, 128)

    # --- Retrieval ---
    SIMILARITY_TOP_K: int = 6  # Number of leaf nodes to retrieve before merging

    # --- Paths ---
    DATA_DIR: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    FAISS_PERSIST_DIR: str = field(
        default_factory=lambda: str(PROJECT_ROOT / "storage" / "faiss")
    )

    def validate(self) -> None:
        """Raise early if critical credentials are missing."""
        errors: list[str] = []
        if not self.LLAMA_CLOUD_API_KEY:
            errors.append(
                "LLAMA_CLOUD_API_KEY is not set. "
                "Get one at https://cloud.llamaindex.ai/api-key"
            )
        if not self.GCP_PROJECT and self.EMBEDDING_PROVIDER.lower() == "vertex":
            print(
                "[CONFIG NOTICE] GOOGLE_CLOUD_PROJECT is not set. "
                "Running in Local Test Mode (using MockEmbedding). "
                "Set GOOGLE_CLOUD_PROJECT in .env when ready to use Vertex AI text-embedding-004.",
                file=sys.stderr,
            )
        if errors:
            for e in errors:
                print(f"[CONFIG ERROR] {e}", file=sys.stderr)
            raise EnvironmentError(
                "Missing required environment variables. See messages above."
            )


# ---------------------------------------------------------------------------
# Module-level singleton — import this everywhere
# ---------------------------------------------------------------------------
settings = Settings()
