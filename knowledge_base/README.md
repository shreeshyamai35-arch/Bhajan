# BhajanForge — Knowledge Base (RAG) Guide

The RAG store grounds the **Lyricist** so lyrics are devotionally accurate and
written in the **artist's own style**. Without it, lyrics are generic.

## What to ingest (by document type)

| Type tag | Content | Purpose |
|----------|---------|---------|
| `artist_lyrics` | Transcribed lyrics of the artist's existing 10+ bhajans | Capture vocabulary, phrasing, signature style |
| `scripture` | Khatu Shyam / Shyam Baba katha, mahima, traditional texts (public domain) | Factual/theological grounding |
| `traditional_bhajan` | Well-known public-domain bhajan/aarti texts | Structure & devotional language reference |
| `taal_raag` | Notes on Keherwa, Dadra, common bhajan raags | Musical guidance for Composer prompts |
| `pronunciation` | Tricky Sanskrit/Hindi term pronunciations | Mirrors `learning.yaml.pronunciation_fixes` |
| `style_notes` | The artist's preferences, do/don'ts | Personalization |

## Folder layout
```
knowledge_base/
├── README.md
├── kb_config.yaml              # chunking + collection settings
└── sources/
    ├── youtube_urls.txt        # artist's bhajan URLs (for voice training too)
    ├── artist_lyrics/*.md      # one file per existing bhajan (with type tag)
    ├── scripture/*.md
    ├── traditional_bhajan/*.md
    ├── taal_raag/*.md
    └── style_notes/*.md
```

## Document front-matter (each source file)
```markdown
---
doc_type: artist_lyrics        # one of the type tags above
title: "Mere Shyam"
language: hi
source: "youtube:VIDEO_ID"      # or book/citation
public_domain: true             # scripture/traditional must be PD or owned
---
(body text / lyrics here)
```

## Ingestion
```bash
bhajanforge kb ingest --source knowledge_base/sources/
```
Codex implements `rag/ingest.py`:
1. Walk `sources/`, parse front-matter, chunk body (see `kb_config.yaml`).
2. Embed with `EMBEDDING_MODEL` (multilingual; must handle Hindi/Devanagari).
3. Upsert to Qdrant collection `QDRANT_COLLECTION` with payload
   `{doc_type, title, language, source, chunk_id}`.

## Retrieval (Lyricist)
`rag/retriever.py` supports filtered top-k:
- Style: `doc_type in (artist_lyrics, style_notes)`
- Facts: `doc_type in (scripture, traditional_bhajan)`
- Music: `doc_type == taal_raag`
- Pronunciation: `doc_type == pronunciation`
The Lyricist requests each bucket separately and composes them into the prompt.

## How to get the artist's lyrics quickly
- Use `audio.transcribe` (ASR, `language="hi"`) on the artist's existing songs to
  bootstrap `artist_lyrics/` drafts, then lightly correct by hand. This both
  seeds the KB and helps build `pronunciation` entries.

## Quality / licensing notes
- Only ingest scripture/traditional text that is **public domain or owned**.
- Keep the artist's own lyrics private to this project.
