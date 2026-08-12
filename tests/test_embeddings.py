"""
Tests for src/embeddings.py — Embedding Model Factory & Fallback Logic
========================================================================
Validates that get_embedding_model() gracefully falls back to MockEmbedding
when GOOGLE_CLOUD_PROJECT is unconfigured or mode is set to "mock".
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llama_index.core.embeddings import MockEmbedding

from config.settings import settings
from src.embeddings import get_embedding_model


class TestEmbeddingFactory:
    """Tests for the embedding factory fallback mechanism."""

    def test_mock_fallback_when_no_gcp_project(self, monkeypatch):
        """When GOOGLE_CLOUD_PROJECT is empty, factory must return MockEmbedding without crashing."""
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        object.__setattr__(settings, "GCP_PROJECT", "")
        object.__setattr__(settings, "EMBEDDING_PROVIDER", "vertex")

        embed_model = get_embedding_model()

        assert isinstance(embed_model, MockEmbedding)
        assert embed_model.embed_dim == settings.EMBEDDING_DIMENSION

    def test_explicit_mock_provider(self, monkeypatch):
        """When EMBEDDING_PROVIDER is 'mock', factory returns MockEmbedding."""
        object.__setattr__(settings, "EMBEDDING_PROVIDER", "mock")

        embed_model = get_embedding_model()

        assert isinstance(embed_model, MockEmbedding)
        assert embed_model.embed_dim == settings.EMBEDDING_DIMENSION
