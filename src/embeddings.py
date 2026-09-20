"""
Embedding Model Factory — embeddings.py
======================================
Provides a production factory function for initializing Google Cloud Vertex AI embeddings.

Uses Google Cloud text-embedding-004 (768-dim) for semantic legal retrieval.
"""

from __future__ import annotations

import logging
from typing import Any

from llama_index.core import Settings as LlamaSettings
from llama_index.embeddings.vertex import VertexTextEmbedding

from config.settings import settings

logger = logging.getLogger(__name__)


def get_embedding_model() -> Any:
    """
    Initialize and return the configured Vertex AI embedding model,
    setting it as LlamaIndex's global embed_model.

    Returns:
        VertexTextEmbedding instance.

    Raises:
        ValueError: If GOOGLE_CLOUD_PROJECT is not configured.
    """
    if not settings.GCP_PROJECT:
        raise ValueError(
            "GOOGLE_CLOUD_PROJECT is required for Vertex AI embeddings. "
            "Please set GOOGLE_CLOUD_PROJECT in your .env file."
        )

    logger.info(
        "Initializing Vertex AI embeddings: model=%s, project=%s, location=%s",
        settings.EMBEDDING_MODEL_NAME,
        settings.GCP_PROJECT,
        settings.GCP_LOCATION,
    )

    import google.auth

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    embed_model = VertexTextEmbedding(
        model_name=settings.EMBEDDING_MODEL_NAME,
        project=settings.GCP_PROJECT,
        location=settings.GCP_LOCATION,
        credentials=credentials,
    )
    LlamaSettings.embed_model = embed_model
    return embed_model

