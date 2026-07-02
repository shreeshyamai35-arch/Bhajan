"""RAG knowledge base (M5) for BhajanForge.

Document ingestion and retrieval against Qdrant. Runs fully offline in mock
mode (``QdrantClient(location=":memory:")`` + a deterministic local hashing
embedder), so no Qdrant server or embedding API keys are required for tests.
"""

from __future__ import annotations

from .embeddings import Embedder, HashingEmbedder, get_embedder
from .ingest import DOC_TYPES, DocType, chunk_text, get_client, ingest_documents, ingest_path
from .retriever import Retriever, retrieve

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "get_embedder",
    "DOC_TYPES",
    "DocType",
    "chunk_text",
    "get_client",
    "ingest_documents",
    "ingest_path",
    "Retriever",
    "retrieve",
]
