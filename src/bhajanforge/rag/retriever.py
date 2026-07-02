"""Top-k retrieval from the RAG knowledge base.

The module-level :func:`retrieve` is the primary entry point; :class:`Retriever`
is a thin convenience wrapper that holds a collection name.
"""

from __future__ import annotations

from typing import List, Optional

from qdrant_client import models as qmodels

from ..logging_utils import get_logger
from .embeddings import Embedder, get_embedder
from .ingest import _collection_name, _normalize_doc_type, get_client

logger = get_logger("rag.retriever")


def _build_filter(doc_types: Optional[List[str]]) -> Optional[qmodels.Filter]:
    """Build a Qdrant filter matching any of the requested doc_types."""
    if not doc_types:
        return None
    normalized = sorted({_normalize_doc_type(d) for d in doc_types})
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="doc_type",
                match=qmodels.MatchAny(any=normalized),
            )
        ]
    )


def retrieve(
    query: str,
    k: int = 5,
    doc_types: Optional[List[str]] = None,
    collection: Optional[str] = None,
    embedder: Optional[Embedder] = None,
) -> List[dict]:
    """Return up to ``k`` most similar chunks for ``query``.

    Each result is ``{"text", "doc_type", "source", "score"}``. When
    ``doc_types`` is given, only chunks of those types are returned.
    """
    embedder = embedder or get_embedder()
    client = get_client()
    name = _collection_name(collection)

    if not client.collection_exists(name):
        logger.warning("Collection '%s' does not exist; returning no results", name)
        return []

    vector = embedder.embed([query])[0]
    response = client.query_points(
        collection_name=name,
        query=vector,
        limit=k,
        query_filter=_build_filter(doc_types),
        with_payload=True,
    )

    results: List[dict] = []
    for point in response.points:
        payload = point.payload or {}
        results.append(
            {
                "text": payload.get("text", ""),
                "doc_type": payload.get("doc_type", ""),
                "source": payload.get("source", ""),
                "score": float(point.score),
            }
        )
    return results


class Retriever:
    """Convenience wrapper binding a collection (and optional embedder)."""

    def __init__(
        self,
        collection: Optional[str] = None,
        embedder: Optional[Embedder] = None,
    ) -> None:
        self.collection = collection
        self.embedder = embedder or get_embedder()

    def retrieve(
        self,
        query: str,
        k: int = 5,
        doc_types: Optional[List[str]] = None,
    ) -> List[dict]:
        return retrieve(
            query,
            k=k,
            doc_types=doc_types,
            collection=self.collection,
            embedder=self.embedder,
        )
