"""
Tests for src/embeddings.py — Production Embedding Model Factory
================================================================
Validates that get_embedding_model() initializes VertexTextEmbedding when
configured and raises ValueError when GOOGLE_CLOUD_PROJECT is missing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.embeddings import get_embedding_model


class TestEmbeddingFactory:
    """Tests for the production Vertex AI embedding factory."""

    def test_raises_error_when_no_gcp_project(self, monkeypatch):
        """When GOOGLE_CLOUD_PROJECT is empty, factory must raise ValueError."""
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        object.__setattr__(settings, "GCP_PROJECT", "")

        with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT is required"):
            get_embedding_model()

    @patch("src.embeddings.VertexTextEmbedding")
    def test_initializes_vertex_embedding_when_configured(self, mock_vertex_cls):
        """When GOOGLE_CLOUD_PROJECT is set, factory initializes VertexTextEmbedding."""
        from llama_index.core.base.embeddings.base import BaseEmbedding
        mock_instance = MagicMock(spec=BaseEmbedding)
        mock_vertex_cls.return_value = mock_instance

        object.__setattr__(settings, "GCP_PROJECT", "policy-red-team")
        object.__setattr__(settings, "GCP_LOCATION", "us-central1")
        object.__setattr__(settings, "EMBEDDING_MODEL_NAME", "text-embedding-004")

        embed_model = get_embedding_model()

        assert embed_model == mock_instance
        mock_vertex_cls.assert_called_once_with(
            model_name="text-embedding-004",
            project="policy-red-team",
            location="us-central1",
        )


