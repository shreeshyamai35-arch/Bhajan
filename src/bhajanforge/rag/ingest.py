"""Document ingestion for the RAG knowledge base.

Pipeline: ``chunk_text`` -> embed (see :mod:`embeddings`) -> upsert into Qdrant.

Offline-first: ``get_client()`` is the single connection helper and supports
three modes, chosen in this order of precedence:

1. **Local on-disk** — when ``QDRANT_PATH`` is set, use a file-based store
   (``QdrantClient(path=...)``). No server, no Docker, survives process
   restarts. qdrant-client allows only ONE client per path per process, so the
   client is cached and reused.
2. **In-memory** — in mock mode (``BHAJANFORGE_MOCK=1`` / no provider keys) use
   ``QdrantClient(location=":memory:")``. Fast, ephemeral, perfect for tests.
3. **Server** — otherwise connect to ``QDRANT_URL``.
"""

from __future__ import annotations

import atexit
import os
import uuid
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from qdrant_client import QdrantClient
from qdrant_client import models as qmodels

from ..config import REPO_ROOT, get_settings
from ..logging_utils import get_logger
from .embeddings import Embedder, get_embedder

logger = get_logger("rag.ingest")


class DocType(str, Enum):
    """The four kinds of knowledge stored in the base."""

    lyrics = "lyrics"
    scripture = "scripture"
    taal_raag = "taal_raag"
    pronunciation = "pronunciation"


DOC_TYPES: tuple[str, ...] = tuple(d.value for d in DocType)

# Cache a single in-memory client so ingest + retrieve share the same store
# within a process when running in mock mode.
_MOCK_CLIENT: Optional[QdrantClient] = None

# Cache local on-disk clients keyed by their resolved path. qdrant-client's
# local ``path=`` mode permits only ONE live client instance per path per
# process, so we must reuse the same object for the lifetime of the process.
_LOCAL_CLIENTS: Dict[str, QdrantClient] = {}


def _normalize_doc_type(value: Optional[str]) -> str:
    """Map an arbitrary string to a known doc_type, defaulting to 'lyrics'."""
    if not value:
        return DocType.lyrics.value
    v = value.strip().lower()
    if v in DOC_TYPES:
        return v
    # tolerate common aliases / pluralisation
    aliases = {
        "lyric": "lyrics",
        "scriptures": "scripture",
        "taal": "taal_raag",
        "raag": "taal_raag",
        "raga": "taal_raag",
        "taal-raag": "taal_raag",
        "pronunciations": "pronunciation",
        "phonetics": "pronunciation",
    }
    return aliases.get(v, DocType.lyrics.value)


def _resolve_local_path(raw: str) -> str:
    """Resolve ``QDRANT_PATH`` to an absolute string (relative to repo root).

    Relative paths like ``./qdrant_data`` are anchored at :data:`REPO_ROOT` so
    behaviour is independent of the current working directory.
    """
    p = Path(raw)
    if not p.is_absolute():
        p = REPO_ROOT / raw
    return str(p.resolve())


def get_client() -> QdrantClient:
    """Return a Qdrant client using the highest-precedence configured mode.

    1. ``QDRANT_PATH`` set -> local on-disk store (no server, persistent). The
       client is cached per resolved path because qdrant-client allows only one
       local client per path per process.
    2. mock mode (``is_mock()``) -> process-wide in-memory client (ephemeral).
    3. otherwise -> connect to ``get_settings().qdrant_url``.
    """
    global _MOCK_CLIENT
    settings = get_settings()

    qdrant_path = os.getenv("QDRANT_PATH")
    if qdrant_path and qdrant_path.strip():
        resolved = _resolve_local_path(qdrant_path.strip())
        client = _LOCAL_CLIENTS.get(resolved)
        if client is None:
            logger.debug("Opening local on-disk Qdrant client at %s", resolved)
            Path(resolved).mkdir(parents=True, exist_ok=True)
            client = QdrantClient(path=resolved)
            _LOCAL_CLIENTS[resolved] = client
        return client

    if settings.is_mock():
        if _MOCK_CLIENT is None:
            logger.debug("Creating in-memory Qdrant client (mock mode)")
            _MOCK_CLIENT = QdrantClient(location=":memory:")
        return _MOCK_CLIENT
    logger.debug("Connecting to Qdrant at %s", settings.qdrant_url)
    return QdrantClient(url=settings.qdrant_url)


def reset_client_cache() -> None:
    """Close and drop all cached clients (test/maintenance helper).

    Releases any local on-disk lock so a fresh :func:`get_client` re-opens the
    store. Safe to call repeatedly.
    """
    global _MOCK_CLIENT
    for client in list(_LOCAL_CLIENTS.values()):
        try:
            client.close()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass
    _LOCAL_CLIENTS.clear()
    if _MOCK_CLIENT is not None:
        try:
            _MOCK_CLIENT.close()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass
        _MOCK_CLIENT = None


# Close local on-disk clients cleanly before interpreter shutdown, otherwise
# qdrant-client's __del__ can raise a noisy ImportError when sys.meta_path is
# already gone. Best-effort only.
atexit.register(reset_client_cache)


def _collection_name(collection: Optional[str]) -> str:
    return collection or get_settings().qdrant_collection


def _ensure_collection(client: QdrantClient, name: str, dim: int) -> None:
    """Create the collection with COSINE distance if it does not exist."""
    if client.collection_exists(name):
        return
    logger.info("Creating Qdrant collection '%s' (dim=%d, COSINE)", name, dim)
    client.create_collection(
        collection_name=name,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )


def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> List[str]:
    """Split ``text`` into overlapping character windows.

    Returns chunks of at most ``max_chars`` characters; consecutive chunks share
    ``overlap`` characters so context is not lost at boundaries. Short text
    yields a single chunk; empty/whitespace text yields an empty list.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be >= 0 and < max_chars")

    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    step = max_chars - overlap
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start += step
    return chunks


def ingest_documents(
    docs: List[dict],
    collection: Optional[str] = None,
    embedder: Optional[Embedder] = None,
) -> dict:
    """Chunk, embed and upsert documents into Qdrant.

    Each doc is ``{"text": str, "doc_type": str, "source": str}``. Every chunk
    is tagged with ``doc_type`` + ``source`` metadata. Creates the collection
    (vector size = embedder dim, COSINE) if missing.

    Returns ``{"ok": True, "ingested": N}`` where N is the number of chunks
    upserted.
    """
    embedder = embedder or get_embedder()
    client = get_client()
    name = _collection_name(collection)
    _ensure_collection(client, name, embedder.dim)

    texts: List[str] = []
    payloads: List[dict] = []
    for doc in docs:
        raw = doc.get("text", "")
        doc_type = _normalize_doc_type(doc.get("doc_type"))
        source = doc.get("source", "unknown")
        for chunk in chunk_text(raw):
            texts.append(chunk)
            payloads.append({"text": chunk, "doc_type": doc_type, "source": source})

    if not texts:
        return {"ok": True, "ingested": 0}

    vectors = embedder.embed(texts)
    points = [
        qmodels.PointStruct(id=str(uuid.uuid4()), vector=vec, payload=payload)
        for vec, payload in zip(vectors, payloads)
    ]
    client.upsert(collection_name=name, points=points)
    logger.info("Ingested %d chunks into '%s'", len(points), name)
    return {"ok": True, "ingested": len(points)}


def _infer_doc_type(path: Path, root: Path) -> str:
    """Infer doc_type from a subfolder name, else a filename prefix.

    e.g. ``sources/scripture/gita.txt`` -> ``scripture``;
    ``sources/pronunciation_guide.md`` -> ``pronunciation``.
    """
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        rel_parts = path.parts
    for part in rel_parts[:-1]:
        norm = _normalize_doc_type(part)
        if part.strip().lower() in DOC_TYPES or norm != DocType.lyrics.value:
            return norm
    # filename prefix before the first separator
    stem = path.stem.lower()
    prefix = stem.replace("-", "_").split("_", 1)[0]
    return _normalize_doc_type(prefix)


def ingest_path(source: str, collection: Optional[str] = None) -> dict:
    """Walk a folder (or single file) and ingest all .txt/.md documents.

    doc_type is inferred from the containing subfolder name or filename prefix,
    defaulting to ``lyrics``. Returns a summary dict.
    """
    src = Path(source)
    if not src.is_absolute():
        candidate = (REPO_ROOT / source)
        if candidate.exists() or not src.exists():
            src = candidate

    if not src.exists():
        return {"ok": False, "error": f"source not found: {source}", "ingested": 0, "files": 0}

    if src.is_file():
        files: Iterable[Path] = [src]
        root = src.parent
    else:
        files = sorted(
            p for p in src.rglob("*") if p.suffix.lower() in {".txt", ".md"} and p.is_file()
        )
        root = src

    docs: List[dict] = []
    used: List[str] = []
    for f in files:
        if f.suffix.lower() not in {".txt", ".md"}:
            continue
        # Skip the URL list consumed by voice training, not RAG content.
        if f.name.lower() == "youtube_urls.txt":
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Skipping %s: %s", f, exc)
            continue
        if not text.strip():
            continue
        docs.append(
            {
                "text": text,
                "doc_type": _infer_doc_type(f, root),
                "source": str(f.relative_to(root)) if root in f.parents or root == f.parent else f.name,
            }
        )
        used.append(str(f))

    result = ingest_documents(docs, collection=collection)
    result.update({"files": len(used), "source": str(src)})
    return result


def _main(argv: Optional[List[str]] = None) -> int:
    """CLI: ``python -m bhajanforge.rag.ingest [SOURCE] [--collection NAME]``.

    (Re)builds the knowledge base from a folder of .txt/.md files. Set
    ``QDRANT_PATH`` first for a persistent on-disk store, e.g.::

        $env:QDRANT_PATH="./qdrant_data"
        python -m bhajanforge.rag.ingest knowledge_base/sources/
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="bhajanforge.rag.ingest",
        description="Ingest devotional texts into the RAG knowledge base.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        default="knowledge_base/sources/",
        help="folder or file to ingest (default: knowledge_base/sources/)",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="target collection name (default: QDRANT_COLLECTION env or bhajan_kb)",
    )
    args = parser.parse_args(argv)

    result = ingest_path(args.source, collection=args.collection)
    store = os.getenv("QDRANT_PATH") or (
        ":memory:" if get_settings().is_mock() else get_settings().qdrant_url
    )
    logger.info("KB ingest into store=%s -> %s", store, result)
    print(f"store={store}")
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    raise SystemExit(_main())
