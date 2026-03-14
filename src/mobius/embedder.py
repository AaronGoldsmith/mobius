"""Embedding abstraction using sentence-transformers."""

from __future__ import annotations

import logging

import numpy as np

from mobius.config import MobiusConfig

logger = logging.getLogger(__name__)

# Cached model instance
_model = None


def _get_model(config: MobiusConfig):
    """Lazy-load the embedding model (downloads on first use)."""
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", config.embedding_model)
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(config.embedding_model)
        logger.info("Embedding model loaded")
    return _model


def embed(text: str, config: MobiusConfig) -> np.ndarray:
    """Embed a text string into a vector."""
    if not text.strip():
        return np.zeros(config.embedding_dim, dtype=np.float32)

    model = _get_model(config)
    vec = model.encode(text, normalize_embeddings=True)
    return vec.astype(np.float32)


def embed_batch(texts: list[str], config: MobiusConfig) -> list[np.ndarray]:
    """Embed multiple texts efficiently."""
    if not texts:
        return []

    model = _get_model(config)
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.astype(np.float32) for v in vecs]
