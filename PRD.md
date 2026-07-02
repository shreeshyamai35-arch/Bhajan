# Product Requirements Document (PRD)
# BhajanForge — Autonomous AI Bhajan Production System

| Field | Value |
|-------|-------|
| **Product Name** | BhajanForge |
| **Version** | 1.0 (Build Spec for Codex) |
| **Owner** | (Artist / Devotional Singer) |
| **Document Status** | Ready for implementation |
| **Primary Builder** | Codex (autonomous coding agent) |
| **Last Updated** | 2026-06-21 |

---

## 0. How To Use This Document (For Codex)

This PRD is the **single source of truth**. Build the system exactly as specified here.
Companion files in this repository expand each area:

- `README.md` — setup & run instructions
- `docs/ARCHITECTURE.md` — system architecture & component diagram
- `docs/AGENTS.md` — exact spec for every agent (inputs/outputs/prompts)
- `docs/MCP_SERVERS.md` — MCP tool schemas & contracts
- `docs/ORCHESTRATION.md` — LangGraph state machine (nodes, edges, state)
- `docs/DATA_MODELS.md` — Pydantic data models / JSON schemas
- `docs/ROADMAP.md` — milestones & build order (BUILD IN THIS ORDER)
- `config/rules.md` — runtime guardrails the agents MUST obey
- `config/learning.yaml` — persistent memory template
- `config/.env.example` — required environment variables
- `skills/*.md` — step-by-step procedures (runbooks) for each stage
- `knowledge_base/README.md` — RAG ingestion guide

> **Golden rule:** When code and this PRD disagree, follow the PRD. When the PRD
> is silent, follow `config/rules.md`. When still ambiguous, choose the simplest,
> most testable implementation and leave a `# TODO(clarify):` comment.

---

## 1. Problem Statement

The user is a devotional singer (bhajans of Shyam Baba / Khatu Shyam) with 10+
songs already published on YouTube. They:

1. **Lack time** to record new bhajans regularly.
2. **Lack music-composition / arrangement ideas.**
3. Want new releases to sound **100% like their own voice** and be
   **professional / studio-grade**.

**Goal:** An autonomous pipeline that takes a simple request
("make a slow emotional Khatu Shyam bhajan about morning darshan") and produces a
**finished, mastered, YouTube-ready bhajan sung in the artist's cloned voice**,
with minimal human effort and a quality gate that prevents bad output.

---

## 2. Goals & Non-Goals

### 2.1 Goals
- G1. Generate authentic devotional lyrics in the artist's style (RAG-grounded).
- G2. Generate music + a guide melody/vocal using **Suno (via Suno MCP)**.
- G3. Convert the guide vocal into the **artist's cloned voice** (RVC primary).
- G4. Mix & master to professional, streaming-loudness standards.
- G5. Enforce a **>= 95/100 quality gate** with an automatic correction loop.
- G6. Auto-publish to YouTube with the required AI-content disclosure.
- G7. Persist learnings so each release improves (`learning.yaml`).
- G8. Be operable by a non-developer via a single command / simple trigger.

### 2.2 Non-Goals (v1)
- NG1. Real-time / live performance voice conversion.
- NG2. Non-devotional genres.
- NG3. Mobile app (CLI + optional simple web trigger only).
- NG4. Cloning anyone other than the artist (explicitly disallowed).
- NG5. Multi-tenant SaaS (single-artist system in v1).

---

## 3. Target User & Personas

| Persona | Description | Needs |
|---------|-------------|-------|
| **The Artist (primary)** | Devotional singer, non-technical | One-command production, review/approve, publish |
| **Codex (builder)** | Autonomous coding agent | Precise, testable, dependency-clear spec |
| **Operator (optional)** | Tech-savvy helper | Configure keys, run servers, tune settings |

---

## 4. Core Concept — Multi-Agent Crew

BhajanForge is an **orchestrated multi-agent system**. One Orchestrator directs
six specialist agents through a deterministic pipeline with quality loops.

```
                    ORCHESTRATOR (LangGraph state machine)
                    loads: rules.md + skills/* + learning.yaml
                                   |
   ┌────────┬───────────┬──────────┴────────┬───────────┬───────────┐
   ▼        ▼           ▼                    ▼           ▼           ▼
 Lyricist  Composer   Voice Agent         Mixing     Quality      Packager
 (RAG)     (Suno API) (cloud RVC/ACE)     (DSP/LANDR)  Judge       (LOCAL SAVE)
```

> **Deployment decisions (locked by product owner):**
> - **Music:** Suno via a **third-party API gateway** (API-first; browser fallback OFF by default).
> - **No local GPU:** voice conversion (cloud RVC on Replicate) and stem separation
>   (LALAL.AI) run via cloud APIs; the pipeline runs on any CPU machine/laptop.
> - **Mastering:** **LANDR API** primary, **matchering** free fallback.
> - **Output:** final audio is **saved to the local machine only** — NO YouTube
>   upload. A ready-to-upload bundle is produced for manual upload.

Full agent specs in `docs/AGENTS.md`. Orchestration graph in `docs/ORCHESTRATION.md`.

---

## 5. System Components

### 5.1 Orchestration Layer
- **LangGraph** — stateful graph; deterministic pipeline + quality-gate loops.
- **FastAPI** — HTTP trigger + status endpoints (`/produce`, `/status/{run_id}`).
- **n8n (optional)** — no-code trigger/notify layer wrapping the FastAPI endpoint.

### 5.2 Agents (see `docs/AGENTS.md`)
1. **Lyricist Agent** — RAG-grounded Hindi/Sanskrit lyric writing.
2. **Composer Agent** — music + guide vocal via **Suno MCP**.
3. **Voice Agent** — voice conversion to artist's voice (**cloud RVC**; ACE optional).
4. **Mixing Agent** — stem alignment, EQ/compression/reverb, mastering (LANDR).
5. **Quality Judge Agent** — objective + perceptual scoring; pass/fail/loop.
6. **Packager Agent** — metadata, artwork, optional video; **saves locally** (no upload).

### 5.3 Tool Layer (MCP servers & APIs — see `docs/MCP_SERVERS.md`)
- **suno-mcp** (music generation + stem extraction) — PRIMARY music source, API-first.
- **rvc-mcp** (**cloud** RVC voice conversion + training via Replicate; no local GPU).
- **stem-mcp** (stem separation — used ONLY for one-time voice-training prep from
  the artist's existing songs; FREE Colab/Kaggle recommended, LALAL/Replicate
  optional). Production stems come from **Suno** itself.
- **audio-mcp** (librosa/ffmpeg analysis + mixing; mastering via **LANDR API**,
  matchering fallback; cloud ASR).
- **browser-agent** (Browser Use) — OPTIONAL fallback for UI-only tools (ACE Studio;
  Suno UI only if `SUNO_USE_BROWSER=true`).
- **youtube-api** — OPTIONAL, OFF by default (`PUBLISH_TARGET=local`).

### 5.4 Knowledge & Memory
- **RAG**: Qdrant vector DB + embeddings (artist's lyrics, Shyam katha, taal/raag,
  pronunciation). See `knowledge_base/README.md`.
- **Learning File**: `config/learning.yaml` — best settings, winning prompts,
  pronunciation fixes, quality history.

### 5.5 Governance
- **Rules File**: `config/rules.md` — hard guardrails (quality bar, ethics, loops).
- **Skill Files**: `skills/*.md` — reusable runbooks per stage.

---

## 6. Functional Requirements

> IDs are referenced by acceptance tests. `MUST` = required for v1.

### 6.1 Intake
- **FR-1 (MUST):** Accept a production request via CLI and FastAPI with fields:
  `theme`, `mood`, `deity` (default "Khatu Shyam"), `taal`, `tempo`, `language`
  (default "hi"), `duration_target`, `lyrics_override` (optional).
- **FR-2 (MUST):** Validate request against `config/rules.md` (devotional only).

### 6.2 Lyricist
- **FR-3 (MUST):** Retrieve relevant context from RAG before writing.
- **FR-4 (MUST):** Output structured lyrics (`LyricsDoc`) with sections
  (mukhda, antara x N, optional aarti outro) and per-line pronunciation hints.
- **FR-5 (MUST):** Self-validate spelling of devotional terms against KB.

### 6.3 Composer (Suno MCP)
- **FR-6 (MUST):** Build a Suno prompt from request + lyrics + Learning File's
  winning prompt templates.
- **FR-7 (MUST):** Call **suno-mcp** to generate the song; poll until complete.
- **FR-8 (MUST):** Call **suno-mcp** stem extraction → download `instrumental.wav`
  and `guide_vocal.wav` (and other stems if available).
- **FR-9 (SHOULD):** Generate 2–3 candidates and pick best by Composer heuristic.

### 6.4 Voice Agent
- **FR-10 (MUST):** Maintain a trained **cloud RVC** model of the artist's voice
  (provider model reference stored in `learning.yaml`; no local GPU weights).
  Provide a training entrypoint (FR-23) and an inference path via **rvc-mcp**.
- **FR-11 (MUST):** Clean the guide vocal via **stem-mcp** (cloud) when Suno stems
  are unavailable or contain residual music.
- **FR-12 (MUST):** Convert guide vocal → artist's voice via **rvc-mcp** (cloud)
  using Learning File's best settings (pitch shift, index ratio, f0 method).
- **FR-12b (MUST):** Auto-detect the artist's vocal range during training
  (`rvc.detect_range`) and store it in `learning.yaml`.
- **FR-13 (SHOULD):** Optional ACE Studio path (browser-agent) for SVS from MIDI
  + lyrics when a guide vocal is undesirable.

### 6.5 Mixing & Mastering
- **FR-14 (MUST):** Time-align converted vocal with instrumental.
- **FR-15 (MUST):** Apply vocal chain: noise/de-reverb cleanup, EQ, compression,
  de-ess, reverb (via **audio-mcp**).
- **FR-16 (MUST):** Master to **-14 LUFS integrated, <= -1 dBTP** via the
  **LANDR API** (primary); fall back to **matchering** if LANDR is unavailable.

### 6.6 Quality Judge
- **FR-17 (MUST):** Compute objective metrics: integrated LUFS, true peak,
  pitch-stability, vocal/instrumental balance, artifact detection, voice-similarity
  to artist reference embedding.
- **FR-18 (MUST):** Produce a `QualityReport` with a 0–100 score + per-criterion
  breakdown + actionable fixes mapped to the failing stage.
- **FR-19 (MUST):** If score < threshold (default 95), trigger the correction loop
  (max attempts from rules.md), applying fixes from the report + Learning File.

### 6.7 Packager (LOCAL SAVE — no upload)
- **FR-20 (MUST):** Generate title, description (with lyrics), and tags as files.
- **FR-21 (MUST):** Save a complete bundle to `OUTPUT_DIR/{date}_{slug}/`:
  `master.wav`, `title.txt`, `description.txt`, `tags.txt`, artwork
  (`cover.png` or `thumbnail_prompt.txt`), `quality_report.json`, and `video.mp4`
  only if `MAKE_VIDEO=true`. **Do NOT upload anywhere.**
- **FR-21b (MUST):** Include a reminder in `description.txt` to tick YouTube's
  "Altered/Synthetic content" box during manual upload.
- **FR-22 (SHOULD):** Support "draft mode" review gating before packaging
  (default ON). YouTube upload is OPTIONAL and OFF unless `PUBLISH_TARGET=youtube`.

### 6.8 Training & Memory
- **FR-23 (MUST):** Voice-model training pipeline: download the artist's existing
  YouTube bhajans (yt-dlp) → isolate vocals (**stem-mcp**, cloud) → train **cloud
  RVC** model (**rvc-mcp** via Replicate) → register model reference + auto-detected
  vocal range in Learning File.
- **FR-24 (MUST):** After each run, update `config/learning.yaml` with the
  winning settings, score, and any pronunciation fixes discovered.

---

## 7. Non-Functional Requirements

- **NFR-1 Quality:** Default publish gate >= 95/100 (configurable in rules.md).
- **NFR-2 Voice fidelity:** vocal similarity to reference >= 0.95 (cosine on
  speaker embedding); else loop.
- **NFR-3 Reliability:** Each stage idempotent & resumable by `run_id`; artifacts
  persisted to `runs/{run_id}/`.
- **NFR-4 Observability:** Structured logs + per-stage timing + a run manifest
  JSON. Optional LangSmith tracing if key present.
- **NFR-5 Cost control:** Configurable max candidates and max loop attempts.
- **NFR-6 Security:** Secrets only via env; browser-agent runs in an isolated
  profile holding ONLY music-tool logins (never email/bank).
- **NFR-7 Portability:** **No local GPU required** — all heavy AI runs via cloud
  APIs. Runs on any CPU machine/laptop. Dockerized (lightweight CPU containers).
- **NFR-8 Usability:** One command (`bhajanforge produce ...`) end-to-end.

---

## 8. Tech Stack (authoritative)

| Concern | Choice | Notes |
|---------|--------|-------|
| Language | **Python 3.11+** | |
| Orchestration | **LangGraph + LangChain** | stateful crew |
| API | **FastAPI + Uvicorn** | triggers/status |
| Data models | **Pydantic v2** | typed contracts |
| MCP | **Model Context Protocol Python SDK** | build & consume MCP servers |
| Music | **Suno via suno-mcp** | 3rd-party Suno API gateway (API-first) behind MCP |
| Voice clone | **Cloud RVC via Replicate** wrapped as rvc-mcp | no local GPU; FREE Colab/Kaggle or Kits.AI alts |
| Stems (production) | **Suno built-in** `extract_stems` | FREE (part of Suno); no separate tool |
| Stems (training prep only) | stem-mcp: FREE Colab/Kaggle | one-time, for vocals from old songs; LALAL/Replicate optional |
| Audio DSP | **librosa, pydub, ffmpeg, pyloudnorm** | CPU analysis + processing |
| Mastering | **LANDR API** (primary) + **matchering** (fallback) | cloud label-grade |
| ASR | **cloud ASR** (multilingual, Hindi) | pronunciation check |
| Vector DB | **Qdrant** | RAG (local CPU) |
| Embeddings | configurable (e.g., `bge-m3` / provider) | multilingual incl. Hindi |
| LLM | configurable provider (frontier model) | Orchestrator + agents |
| Browser agent | **Browser Use** | OPTIONAL UI-only fallback (off by default) |
| Download | **yt-dlp** | fetch existing bhajans for training |
| Output | **local save to `OUTPUT_DIR`** | NO auto-upload; YouTube optional/off |
| Packaging | **Docker + docker-compose** | reproducible, CPU-only |
| Tests | **pytest** | unit + pipeline smoke tests |

> **Locked decisions (product owner):**
> - **Music = Suno only** (ElevenLabs explicitly NOT used). Suno has no official
>   public API, so `suno-mcp` wraps a configured Suno-compatible **API gateway**
>   (`SUNO_API_BASE`/`SUNO_API_KEY`) — API-first. Browser fallback is OFF unless
>   `SUNO_USE_BROWSER=true`.
> - **No local GPU** — voice (Replicate RVC) and stems (LALAL.AI) are cloud APIs.
>   FREE alternative: run RVC/UVR on **Google Colab (T4)** or **Kaggle (~30h/wk)**
>   GPUs exposed via a tunnel — same MCP interface (see `notebooks/README.md`).
> - **Mastering = LANDR API** primary, matchering fallback.
> - **Output saved locally only** — NO YouTube upload (`PUBLISH_TARGET=local`).
> See the LEGAL note in `config/rules.md` §2.5.

---

## 9. Repository Structure (target — Codex creates code under `src/`)

```
BhajanForge/
├── PRD.md                      # this file
├── README.md
├── pyproject.toml
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── config/
│   ├── rules.md
│   ├── learning.yaml
│   └── .env.example
├── skills/
│   ├── produce_bhajan.md
│   ├── generate_music.md
│   ├── clone_voice.md
│   ├── mix_and_master.md
│   ├── quality_review.md
│   └── publish.md
├── knowledge_base/
│   └── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AGENTS.md
│   ├── MCP_SERVERS.md
│   ├── ORCHESTRATION.md
│   ├── DATA_MODELS.md
│   └── ROADMAP.md
└── src/                        # <-- Codex implements here
    ├── bhajanforge/
    │   ├── __init__.py
    │   ├── cli.py
    │   ├── api.py
    │   ├── config.py            # loads rules.md + learning.yaml + env
    │   ├── state.py             # LangGraph state (DATA_MODELS.md)
    │   ├── graph.py             # LangGraph wiring (ORCHESTRATION.md)
    │   ├── agents/
    │   │   ├── lyricist.py
    │   │   ├── composer.py
    │   │   ├── voice.py
    │   │   ├── mixing.py
    │   │   ├── quality_judge.py
    │   │   └── packager.py
    │   ├── mcp_servers/
    │   │   ├── suno_mcp/         # Suno API gateway (API-first)
    │   │   ├── rvc_mcp/          # cloud RVC (Replicate) — no local GPU
    │   │   ├── stem_mcp/         # cloud stem separation (LALAL.AI)
    │   │   └── audio_mcp/        # DSP + LANDR mastering + cloud ASR
    │   ├── rag/
    │   │   ├── ingest.py
    │   │   └── retriever.py
    │   ├── memory/
    │   │   └── learning.py       # read/write learning.yaml
    │   └── utils/
    └── tests/
```

---

## 10. End-to-End Flow (happy path)

1. **Intake** → validate request (rules) → create `run_id`, `runs/{run_id}/`.
2. **Lyricist** → RAG retrieve → write `lyrics.json`.
3. **Composer** → build Suno prompt → `suno-mcp.generate` → poll →
   `suno-mcp.extract_stems` → `instrumental.wav`, `guide_vocal.wav`.
4. **Voice** → `stem-mcp.isolate` (clean guide if needed) → `rvc-mcp.convert`
   (cloud) → `my_voice.wav`.
5. **Mixing** → align + vocal chain (`audio-mcp`) → master via LANDR → `master.wav`.
6. **Quality Judge** → metrics → `quality_report.json` →
   if score >= gate: continue; else loop to failing stage (max attempts).
7. **Packager** → metadata + artwork (+ optional video) → **save bundle to
   `OUTPUT_DIR/` locally**. NO upload.
8. **Memory** → update `learning.yaml`; write `runs/{run_id}/manifest.json`.

---

## 11. Success Metrics

| Metric | Target |
|--------|--------|
| Quality gate pass rate (first 3 attempts) | >= 90% |
| Voice similarity to artist reference | >= 0.95 |
| Integrated loudness | -14 LUFS (±1) |
| True peak | <= -1 dBTP |
| Human edits required before publish | <= 1 per bhajan |
| End-to-end runtime (cloud, 1 candidate) | <= 20 min |
| Pronunciation errors in final | 0 (verified vs KB) |

---

## 12. Acceptance Criteria (Definition of Done)

- AC-1. `bhajanforge produce --theme "morning darshan" --mood slow-emotional`
  produces `runs/{id}/master.wav` + `quality_report.json` with score >= 95
  in draft mode, with NO manual intervention.
- AC-2. The voice in `master.wav` matches the artist reference (>= 0.95 similarity)
  and contains no audible robotic artifacts (judge artifact metric below threshold).
- AC-3. Loudness/peak meet NFR targets (verified by audio-mcp report).
- AC-4. `learning.yaml` is updated after the run.
- AC-5. Re-running the same `run_id` resumes without redoing completed stages.
- AC-6. Voice training entrypoint builds a **cloud RVC** model from a folder of
  the artist's isolated vocals, auto-detects vocal range, and registers both in
  `learning.yaml`.
- AC-7. Packager saves a complete bundle to `OUTPUT_DIR/{date}_{slug}/`
  (`master.wav` + metadata + artwork) and performs **NO upload**
  (`PUBLISH_TARGET=local`).
- AC-8. All `config/rules.md` guardrails are enforced (unit-tested).
- AC-9. `pytest` passes; `docker-compose up` starts all MCP servers + API
  (CPU-only, no GPU).

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Suno has no official API; endpoints may break | MCP isolates Suno behind one `MusicProvider`; config-driven gateway; optional browser fallback |
| Suno copyright/ToS uncertainty | Swappable `MusicProvider`; documented in rules.md; draft-mode + local-save default |
| Cloud RVC quality varies with data | Training pipeline + Learning File best-settings; quality loop; range auto-detect |
| Hindi mispronunciation by Suno | Lyricist pronunciation hints + KB verification + judge check + regenerate |
| Cloud API cost / rate limits | Configurable candidates + loop caps; retries with backoff (tenacity); cost logged in manifest |
| Cloud API outage | LANDR→matchering fallback; Replicate→Kits alt; LALAL→Replicate Demucs alt |
| Browser-agent security (if enabled) | Off by default; isolated profile, music-tool logins only (NFR-6) |
| Accidental upload | Default `PUBLISH_TARGET=local`; upload requires explicit opt-in + AI-disclosure |

---

## 14. Open Questions (please answer before Codex build)

See the consolidated list in `OPEN_QUESTIONS.md`. Defaults are assumed where not
answered, so the build can proceed either way.

---

## 15. Out-of-Scope / Future (v2+)
- Multi-deity / multi-language expansion beyond Hindi.
- Web dashboard with audio preview + approve button.
- A/B testing thumbnails & titles for YouTube CTR.
- Automatic short-form (Reels/Shorts) clip generation.
- Distribution to Spotify/Apple Music via an aggregator API.
