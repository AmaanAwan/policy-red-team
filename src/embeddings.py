"""
Embedding Model Factory — embeddings.py
======================================
Provides a unified factory function for initializing the embedding model.

Supports two modes:
    1. Vertex AI ("vertex"): Uses Google Cloud text-embedding-004 (768-dim).
    2. Mock ("mock"): Uses LlamaIndex MockEmbedding for zero-GCP local testing.

If GOOGLE_CLOUD_PROJECT is not set, it automatically falls back to MockEmbedding
so the full ingestion and MCP pipeline can be tested locally using ONLY a
LlamaCloud API key.
"""

from __future__ import annotations

import logging
from typing import Any

from llama_index.core import Settings as LlamaSettings
from llama_index.core.embeddings import MockEmbedding
from llama_index.embeddings.vertex import VertexTextEmbedding

from config.settings import settings

logger = logging.getLogger(__name__)


def get_embedding_model() -> Any:
    """
    Initialize and return the configured embedding model, setting it as
    LlamaIndex's global embed_model.

    Returns:
        VertexTextEmbedding or MockEmbedding instance.
    """
    provider = settings.EMBEDDING_PROVIDER.lower().strip()

    # Automatic fallback to mock mode if GCP project is missing
    if provider == "mock" or (provider == "vertex" and not settings.GCP_PROJECT):
        if not settings.GCP_PROJECT and provider == "vertex":
            logger.warning(
                "[LOCAL TEST MODE] GOOGLE_CLOUD_PROJECT is not set in .env. "
                "Falling back to MockEmbedding (dim=%d) for local testing without GCP credentials.",
                settings.EMBEDDING_DIMENSION,
            )
        else:
            logger.info(
                "[LOCAL TEST MODE] Initializing MockEmbedding (dim=%d)",
                settings.EMBEDDING_DIMENSION,
            )

        embed_model = MockEmbedding(embed_dim=settings.EMBEDDING_DIMENSION)
        LlamaSettings.embed_model = embed_model
        return embed_model

    logger.info(
        "Initializing Vertex AI embeddings: model=%s, project=%s, location=%s",
        settings.EMBEDDING_MODEL_NAME,
        settings.GCP_PROJECT,
        settings.GCP_LOCATION,
    )
    try:
        embed_model = VertexTextEmbedding(
            model_name=settings.EMBEDDING_MODEL_NAME,
            project=settings.GCP_PROJECT,
            location=settings.GCP_LOCATION,
        )
        LlamaSettings.embed_model = embed_model
        return embed_model
    except Exception as exc:
        logger.warning(
            "[EMBEDDING FALLBACK] Could not initialize Vertex AI embeddings (%s). "
            "Falling back to MockEmbedding (dim=%d) for seamless local execution.",
            exc,
            settings.EMBEDDING_DIMENSION,
        )
        embed_model = MockEmbedding(embed_dim=settings.EMBEDDING_DIMENSION)
        LlamaSettings.embed_model = embed_model
        return embed_model
