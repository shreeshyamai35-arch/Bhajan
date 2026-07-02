# BhajanForge — Build Roadmap (BUILD IN THIS ORDER)

Codex: implement milestones sequentially. Each milestone has a **Definition of
Done (DoD)** and maps to PRD Functional Requirements (FR) and Acceptance
Criteria (AC). Write tests as you go.

---

## M0 — Project Skeleton  (foundation)
**Build:** repo layout per PRD §9, `pyproject.toml`, `requirements.txt`,
`config.py` (loads `.env` + `rules.md` thresholds + `learning.yaml`),
Pydantic models (`DATA_MODELS.md`), logging, `runs/` handling, `cli.py` stub,
`api.py` stub, `docker-compose.yml`, `Dockerfile`.
**DoD:** `bhajanforge --help` works; `pytest` runs; config loads & validates
rules thresholds; `docker-compose config` is valid.

## M1 — audio-mcp  (DSP core; mastering via LANDR API)
**Build:** `audio.analyze`, `audio.align`, `audio.vocal_chain`, `audio.mix`,
`audio.master` (LANDR API primary + matchering fallback + pyloudnorm),
`audio.transcribe` (cloud ASR).
**DoD (AC-3):** given a sample vocal+instrumental, produces a master at
-14 LUFS / <= -1 dBTP and returns correct metrics. Unit-tested with fixtures.

## M2 — stem-mcp  (cloud stem separation)
**Build:** `stem.isolate`, `stem.batch_isolate` wrapping `STEM_PROVIDER`
(LALAL.AI default; Replicate Demucs / Colab-Kaggle tunnel alts). No local GPU.
**DoD:** separates a test song into clean vocals + instrumental; batch mode
populates a dataset folder.

## M3 — rvc-mcp  (cloud voice conversion + training)
**Build:** `rvc.list_models`, `rvc.convert`, `rvc.train`, `rvc.get_train_task`,
`rvc.detect_range` wrapping `VOICE_PROVIDER` (Replicate default; Colab/Kaggle
tunnel + Kits alts). No local GPU.
**DoD (AC-6):** `voice train` builds a cloud model from a vocals folder,
auto-detects range, and registers both in `learning.yaml`; `rvc.convert`
transforms a guide vocal using best_settings.

## M4 — suno-mcp  (music generation, API-first)
**Build:** `suno.generate`, `suno.get_task`, `suno.download`,
`suno.extract_stems`; API path (`SUNO_API_BASE`) primary + optional browser-agent
fallback (only if `SUNO_USE_BROWSER=true`). If endpoint lacks stems, route to
`stem-mcp`.
**DoD:** from lyrics + style prompt, returns downloadable clip(s) + vocal &
instrumental stems. Behind a `MusicProvider` interface (PRD §13).

## M5 — RAG Knowledge Base
**Build:** `rag/ingest.py` (chunk + embed + upsert to Qdrant),
`rag/retriever.py` (top-k retrieval, filters by doc type), `kb ingest` CLI.
Ingestion guide already in `knowledge_base/README.md`.
**DoD:** ingest the artist's lyrics + scripture; retrieval returns relevant,
correctly-typed context.

## M6 — Agents (logic) + Memory
**Build:** all six agents (`AGENTS.md`) calling the MCP tools; `memory/learning.py`
read/write; per-agent skill-runbook loading.
**DoD:** each agent unit-tested with mocked MCP tools; learning.yaml updates.

## M7 — Orchestration (LangGraph) + Quality Loop
**Build:** `state.py`, `graph.py` per `ORCHESTRATION.md`, checkpointer,
conditional edges, loop control, hard stops.
**DoD (AC-1, AC-5):** end-to-end `produce` runs in draft mode and yields a master
with quality_report >= 95 (using real or recorded-mock tools); resumable by run_id.

## M8 — Packager (LOCAL SAVE)
**Build:** metadata/artwork generation, optional ffmpeg lyric/art video, save
bundle to `OUTPUT_DIR/{date}_{slug}/`. YouTube upload is OPTIONAL and OFF by
default (`PUBLISH_TARGET=local`); if ever enabled it MUST set the AI-disclosure
flag. `publish` CLI re-enters the packager.
**DoD (AC-7):** produces a complete local bundle (master + metadata + artwork) and
performs NO upload by default.

## M9 — Hardening & Governance Tests
**Build:** enforce every `config/rules.md` guardrail in code; tests for ethics
hard stops (third-party voice, non-devotional), loudness/peak, similarity gate,
loop limits, disclosure flag.
**DoD (AC-8, AC-9):** governance unit tests pass; full `pytest` green;
`docker-compose up` starts all servers + API.

## M10 — UX polish (optional v1.1)
**Build:** richer CLI output, `status` dashboard text, optional n8n workflow
JSON export, optional minimal web approval page.

---

## Dependency Graph
```
M0 ─┬─► M1 ─► M2 ─► M3 ─┐
    ├─► M4 ───────────────┤
    └─► M5 ───────────────┤
                          ▼
                         M6 ─► M7 ─► M8 ─► M9 ─► M10
```

## Testing strategy
- **Unit:** each MCP tool + agent (mock tools) + governance rules.
- **Fixtures:** small sample audio in `tests/fixtures/`.
- **Smoke (pipeline):** `tests/test_pipeline.py` runs the graph with recorded mock
  MCP responses to validate flow + loop + draft gate without burning API quota.
- **Live (manual, opt-in):** `tests/live/` guarded by env flags for real Suno/RVC.
