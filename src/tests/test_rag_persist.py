"""RAG on-disk persistence tests (no server, no Docker).

These verify the local file-based Qdrant mode selected by the ``QDRANT_PATH``
env var: documents ingested into an on-disk store survive a fresh
``get_client()`` call (re-open) within the same process. They run fully offline
with the deterministic hashing embedder; ``BHAJANFORGE_MOCK=1`` is forced by
conftest but ``QDRANT_PATH`` takes precedence over the in-memory mock client.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from bhajanforge.rag import ingest as ingest_mod
from bhajanforge.rag.ingest import (
    DOC_TYPES,
    get_client,
    ingest_documents,
    ingest_path,
    reset_client_cache,
)
from bhajanforge.rag.retriever import retrieve


@pytest.fixture()
def local_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point QDRANT_PATH at a throwaway dir and isolate the client cache."""
    store_dir = tmp_path / "qdrant_data"
    monkeypatch.setenv("QDRANT_PATH", str(store_dir))
    # Start from a clean cache and guarantee cleanup releases the on-disk lock.
    reset_client_cache()
    yield store_dir
    reset_client_cache()


@pytest.fixture()
def collection() -> str:
    return f"persist_kb_{uuid.uuid4().hex[:8]}"


def test_qdrant_path_selects_local_on_disk_client(local_store: Path):
    """With QDRANT_PATH set, get_client() opens a persistent local store."""
    client = get_client()
    # The on-disk directory is created and the client is reused (cached).
    assert local_store.exists()
    assert client is get_client()
    # The same path resolves to the same cached instance.
    resolved = ingest_mod._resolve_local_path(str(local_store))
    assert resolved in ingest_mod._LOCAL_CLIENTS


def test_ingest_then_retrieve_from_local_store(local_store: Path, collection: str):
    docs = [
        {
            "text": "Morning mangla aarti: darshan of Khatu Shyam at Khatu dham.",
            "doc_type": "lyrics",
            "source": "shyam-aarti",
        },
        {
            "text": "Barbarika offered his head to Krishna as the supreme daan.",
            "doc_type": "scripture",
            "source": "khatu-shyam-katha",
        },
    ]
    result = ingest_documents(docs, collection=collection)
    assert result["ok"] is True
    assert result["ingested"] >= len(docs)

    hits = retrieve("morning darshan of Khatu Shyam", k=5, collection=collection)
    assert hits, "expected non-empty results from on-disk store"
    top = hits[0]
    assert set(top) >= {"text", "doc_type", "source", "score"}
    assert top["doc_type"] in DOC_TYPES


def test_data_persists_across_fresh_client(local_store: Path, collection: str):
    """Re-opening the store (fresh get_client) returns previously ingested data."""
    docs = [
        {
            "text": "Shyam Baba is praised as Haare ka sahara, support of the helpless.",
            "doc_type": "lyrics",
            "source": "shyam-bhajan",
        },
        {
            "text": "Keherwa is an eight beat taal suited to devotional bhajans.",
            "doc_type": "taal_raag",
            "source": "keherwa",
        },
    ]
    assert ingest_documents(docs, collection=collection)["ingested"] >= 2

    # Drop the cached client (releasing the lock) and re-open the SAME path.
    reset_client_cache()
    assert not ingest_mod._LOCAL_CLIENTS  # cache truly cleared

    reopened = get_client()
    assert reopened.collection_exists(collection), "collection should persist on disk"

    hits = retrieve("support of the helpless", k=5, collection=collection)
    assert hits, "data should survive a fresh client (persistence)"
    assert any("sahara" in h["text"].lower() for h in hits)


def test_ingest_path_builds_kb_into_local_store(local_store: Path, collection: str):
    """End-to-end: build the real KB from knowledge_base/sources/ on disk."""
    result = ingest_path("knowledge_base/sources/", collection=collection)
    assert result["ok"] is True, result
    assert result["files"] >= 5, result
    assert result["ingested"] >= 5, result

    hits = retrieve(
        "morning darshan of Khatu Shyam", k=5, collection=collection
    )
    assert hits, "expected grounded results from the real KB"
    # doc_type metadata is populated from the source subfolders.
    assert all(h["doc_type"] in DOC_TYPES for h in hits)

    scripture = retrieve(
        "story of Barbarika sacrifice",
        k=5,
        doc_types=["scripture"],
        collection=collection,
    )
    assert scripture, "expected scripture chunks from khatu-shyam-katha.md"
    assert all(h["doc_type"] == "scripture" for h in scripture)
