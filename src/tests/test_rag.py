"""M5 RAG tests: chunking, ingestion and filtered retrieval.

Runs fully offline using the in-memory Qdrant client (mock mode, forced by
conftest's ``BHAJANFORGE_MOCK=1``) and the deterministic hashing embedder.
"""

from __future__ import annotations

import uuid

import pytest

from bhajanforge.rag.embeddings import HASHING_DIM, HashingEmbedder, get_embedder
from bhajanforge.rag.ingest import (
    DOC_TYPES,
    chunk_text,
    ingest_documents,
)
from bhajanforge.rag.retriever import Retriever, retrieve


@pytest.fixture()
def collection() -> str:
    """A unique collection per test so they don't interfere."""
    return f"test_kb_{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def seeded(collection: str) -> str:
    docs = [
        {
            "text": "Shyam Shyam bolo, Khatu wale Shyam ki jai. Morning darshan aarti.",
            "doc_type": "lyrics",
            "source": "shyam-aarti",
        },
        {
            "text": "Karmanye vadhikaraste ma phaleshu kadachana, duty without attachment.",
            "doc_type": "scripture",
            "source": "gita-2.47",
        },
        {
            "text": "Keherwa is an eight beat taal commonly used for devotional bhajans.",
            "doc_type": "taal_raag",
            "source": "keherwa",
        },
        {
            "text": "Khatu is pronounced khaa-too; Shyam is pronounced shyaam.",
            "doc_type": "pronunciation",
            "source": "common-terms",
        },
    ]
    result = ingest_documents(docs, collection=collection)
    assert result["ok"] is True
    assert result["ingested"] >= len(docs)
    return collection


# --- embeddings -----------------------------------------------------------


def test_hashing_embedder_is_deterministic_and_normalized():
    emb = HashingEmbedder()
    assert emb.dim == HASHING_DIM
    a = emb.embed(["Khatu Shyam"])[0]
    b = emb.embed(["Khatu Shyam"])[0]
    assert a == b  # deterministic
    assert len(a) == HASHING_DIM
    norm = sum(x * x for x in a) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_get_embedder_offline_returns_hashing():
    # Mock mode is forced by conftest, so no cloud SDK is needed.
    emb = get_embedder()
    assert isinstance(emb, HashingEmbedder)
    assert emb.dim == HASHING_DIM


# --- chunking -------------------------------------------------------------


def test_chunk_text_splits_long_string_with_overlap():
    text = "abcdefghij" * 50  # 500 chars
    chunks = chunk_text(text, max_chars=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    # Overlap: the tail of one chunk reappears at the head of the next.
    assert text[80:100] in chunks[1]


def test_chunk_text_short_text_single_chunk():
    assert chunk_text("short text") == ["short text"]
    assert chunk_text("   ") == []


# --- retrieval ------------------------------------------------------------


def test_retrieve_returns_non_empty_with_metadata(seeded: str):
    results = retrieve("morning darshan of Shyam", k=5, collection=seeded)
    assert results, "expected non-empty results"
    top = results[0]
    assert set(top) >= {"text", "doc_type", "source", "score"}
    assert top["doc_type"] in DOC_TYPES
    assert isinstance(top["source"], str) and top["source"]
    assert isinstance(top["score"], float)


def test_retrieve_filters_by_doc_type(seeded: str):
    results = retrieve(
        "anything", k=10, doc_types=["scripture"], collection=seeded
    )
    assert results, "expected at least one scripture chunk"
    assert all(r["doc_type"] == "scripture" for r in results)


def test_retrieve_filters_by_multiple_doc_types(seeded: str):
    results = retrieve(
        "bhajan", k=10, doc_types=["lyrics", "taal_raag"], collection=seeded
    )
    assert results
    assert all(r["doc_type"] in {"lyrics", "taal_raag"} for r in results)


def test_retriever_class_wrapper(seeded: str):
    r = Retriever(collection=seeded)
    results = r.retrieve("pronunciation of Khatu", k=3, doc_types=["pronunciation"])
    assert results
    assert all(x["doc_type"] == "pronunciation" for x in results)


def test_retrieve_missing_collection_returns_empty():
    assert retrieve("anything", collection="does_not_exist_kb") == []
