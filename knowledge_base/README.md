# BhajanForge Knowledge Base (RAG)

This folder holds the source documents that power BhajanForge's retrieval-augmented
generation (RAG). Documents are chunked, embedded, and stored in
[Qdrant](https://qdrant.tech/) so the lyric and music agents can ground their output
in real scripture, devotional lyrics, rhythmic/melodic theory, and correct pronunciation.

Everything runs **CPU-only and offline** by default: in mock mode the store is an
in-memory Qdrant instance and embeddings come from a deterministic local hashing
embedder — no Qdrant server and no embedding API key required.

## Document types

Every chunk is tagged with a `doc_type` so retrieval can be filtered to the right
kind of knowledge:

| `doc_type`      | What goes here                                                        |
| --------------- | --------------------------------------------------------------------- |
| `lyrics`        | Existing bhajan lyrics, devotional poetry, refrains, mukhda/antara.   |
| `scripture`     | Verses and passages from scripture (Gita, Ramayana, stotras, etc.).   |
| `taal_raag`     | Rhythmic cycles (taal) and melodic frameworks (raag) and their usage. |
| `pronunciation` | Transliteration and pronunciation notes for Sanskrit/Hindi terms.     |

## Folder layout

Place documents under `knowledge_base/sources/`, one subfolder per doc type. The
ingester infers the `doc_type` from the **subfolder name** (and falls back to a
filename prefix, then to `lyrics`):

```
knowledge_base/
  README.md
  sources/
    lyrics/
      shyam-aarti.txt
      khatu-naresh.md
    scripture/
      gita-ch12.txt
    taal_raag/
      keherwa.md
      raag-bhairavi.txt
    pronunciation/
      common-terms.md
  youtube_urls.txt        # NOT ingested into RAG — see below
```

Only `.txt` and `.md` files are ingested. Empty files are skipped.

### `youtube_urls.txt`

`youtube_urls.txt` is **not** part of the RAG corpus. It is consumed by the voice
training pipeline (`bhajanforge voice train --youtube-urls ...`) to collect clean
vocal references. The ingester deliberately skips it.

## Ingesting

Use the CLI to walk a folder and ingest everything under it:

```bash
bhajanforge kb ingest --source knowledge_base/sources/
```

This chunks each document (overlapping windows), embeds the chunks, and upserts them
into the configured Qdrant collection (`QDRANT_COLLECTION`, default `bhajan_kb`),
creating the collection with cosine distance if it does not yet exist.

### Programmatic ingestion

```python
from bhajanforge.rag.ingest import ingest_documents, ingest_path

# From a folder:
ingest_path("knowledge_base/sources/")

# From in-memory docs:
ingest_documents([
    {"text": "Shyam Shyam bolo...", "doc_type": "lyrics", "source": "shyam-aarti"},
    {"text": "Karmanye vadhikaraste...", "doc_type": "scripture", "source": "gita-2.47"},
])
```

## Retrieving

```python
from bhajanforge.rag.retriever import retrieve

# Top-k across all doc types:
hits = retrieve("morning darshan of Khatu Shyam", k=5)

# Filter to specific doc types:
verses = retrieve("duty without attachment", k=3, doc_types=["scripture"])

for h in hits:
    print(h["score"], h["doc_type"], h["source"], h["text"][:60])
```

Each hit is `{"text", "doc_type", "source", "score"}`.

## Configuration

| Setting             | Env var               | Default                 |
| ------------------- | --------------------- | ----------------------- |
| Qdrant URL          | `QDRANT_URL`          | `http://localhost:6333` |
| Collection name     | `QDRANT_COLLECTION`   | `bhajan_kb`             |
| Embedding model     | `EMBEDDING_MODEL`     | _(provider default)_    |
| Embedding API key   | `EMBEDDING_API_KEY`   | _(unset → local hashing embedder)_ |
| Offline / mock mode | `BHAJANFORGE_MOCK=1`  | auto when no keys set   |

When `EMBEDDING_API_KEY` is set (and not in mock mode), a cloud embedder is used.
Otherwise BhajanForge falls back to the offline 384-dimensional hashing embedder so
ingestion and retrieval always work without external services.
