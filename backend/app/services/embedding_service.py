"""Lazy FastEmbed provider and embedding validation helpers."""
from __future__ import annotations

import hashlib
import os
import threading
from typing import Any, Iterable


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_EMBEDDING_DIM = 512


def embedding_model_name() -> str:
    return (os.getenv("RAG_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL).strip()


def embedding_dimension() -> int:
    try:
        return int(os.getenv("RAG_EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM)))
    except ValueError:
        return DEFAULT_EMBEDDING_DIM


def embedding_cache_dir() -> str:
    return (os.getenv("RAG_EMBEDDING_CACHE_DIR") or "/app/.fastembed_cache").strip()


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def validate_embedding_dimension(vector: Iterable[float], expected: int | None = None) -> int:
    values = list(vector)
    dimension = expected or embedding_dimension()
    if len(values) != dimension:
        raise ValueError(f"embedding dimension mismatch: expected {dimension}, got {len(values)}")
    return dimension


class FastEmbedProvider:
    """Thread-safe lazy wrapper around FastEmbed's ONNX model."""

    def __init__(self, model_name: str | None = None, cache_dir: str | None = None):
        self.model_name = model_name or embedding_model_name()
        self.cache_dir = cache_dir or embedding_cache_dir()
        self._model: Any = None
        self._lock = threading.Lock()

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(
                        model_name=self.model_name,
                        cache_dir=self.cache_dir,
                    )
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = [list(map(float, vector)) for vector in self._get_model().embed(texts)]
        for vector in vectors:
            validate_embedding_dimension(vector)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
