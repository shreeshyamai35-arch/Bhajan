"""Embedding abstraction for the RAG knowledge base.

Two backends share one tiny interface (``Embedder``):

* ``HashingEmbedder`` — deterministic, dependency-free, CPU-only. It turns text
  into an L2-normalised vector by hashing tokens into a fixed-size space. No
  cloud SDK, no network, no model download — perfect for offline use and tests.
* ``CloudEmbedder`` — used only when ``EMBEDDING_API_KEY`` is set. The cloud
  call is structured with ``httpx`` but never exercised in tests (mock mode
  always selects the hashing embedder).

``get_embedder()`` picks the right backend automatically.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import List, Protocol, runtime_checkable

from ..config import get_settings
from ..logging_utils import get_logger

logger = get_logger("rag.embeddings")

# Fixed dimensionality for the offline hashing embedder.
HASHING_DIM = 384

_TOKEN_RE = re.compile(r"[A-Za-z0-9\u0900-\u097F]+")


@runtime_checkable
class Embedder(Protocol):
    """Minimal embedding interface used throughout the RAG package."""

    dim: int

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Return one vector (list of floats) per input string."""
        ...


def _tokenize(text: str) -> List[str]:
    """Lowercased word/devanagari tokens; deterministic and language-agnostic."""
    return _TOKEN_RE.findall(text.lower())


class HashingEmbedder:
    """Deterministic local embedder using the hashing trick.

    Each token is hashed to an index in ``[0, dim)`` and a sign, then summed.
    The resulting vector is L2-normalised so cosine similarity is meaningful.
    Identical input always yields an identical vector (no randomness).
    """

    def __init__(self, dim: int = HASHING_DIM) -> None:
        self.dim = dim

    def _hash(self, token: str) -> tuple[int, float]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        index = h % self.dim
        sign = 1.0 if (h >> 63) & 1 else -1.0
        return index, sign

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in _tokenize(text):
                index, sign = self._hash(token)
                vec[index] += sign
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0.0:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors


class CloudEmbedder:
    """Cloud-backed embedder (OpenAI-compatible) selected when a key is set.

    The request is structured but intentionally lazy: ``httpx`` is imported and
    called only inside :meth:`embed`, so importing this module never requires a
    network or any cloud SDK. Tests never reach this path.
    """

    def __init__(self, api_key: str, model: str, dim: int = HASHING_DIM) -> None:
        self.api_key = api_key
        self.model = model or "text-embedding-3-small"
        self.dim = dim
        self.base_url = os.getenv(
            "EMBEDDING_API_BASE", "https://api.openai.com/v1"
        ).rstrip("/")

    def embed(self, texts: List[str]) -> List[List[float]]:  # pragma: no cover
        import httpx  # local import keeps module import side-effect free

        resp = httpx.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        vectors = [item["embedding"] for item in data]
        if vectors:
            self.dim = len(vectors[0])
        return vectors


def get_embedder() -> Embedder:
    """Return the cloud embedder when ``EMBEDDING_API_KEY`` is present, else the
    deterministic offline :class:`HashingEmbedder`."""
    settings = get_settings()
    api_key = os.getenv("EMBEDDING_API_KEY")
    if api_key and not settings.is_mock():
        logger.info("Using cloud embedder (model=%s)", settings.embedding_model or "default")
        return CloudEmbedder(api_key=api_key, model=settings.embedding_model)
    logger.debug("Using offline HashingEmbedder (dim=%d)", HASHING_DIM)
    return HashingEmbedder(dim=HASHING_DIM)
