# BhajanForge — Architecture

## 1. Overview
BhajanForge is a **single-artist, multi-agent audio production pipeline**. A
LangGraph state machine (the Orchestrator) drives six specialist agents. Agents
reach external capabilities through **MCP servers** (local & remote) and APIs.
Knowledge comes from a **RAG** store; behavior is governed by a **Rules File**;
procedures live in **Skill Files**; and the system improves via a **Learning File**.

```
                         ┌──────────────────────────────────────┐
   CLI / FastAPI ───────►│        ORCHESTRATOR (LangGraph)        │
   (trigger)             │  loads rules.md + skills/* + learning  │
                         └──────────────────────────────────────┘
                                          │ state: BhajanState
   ┌──────────┬───────────┬───────────────┼───────────────┬───────────┬───────────┐
   ▼          ▼           ▼               ▼               ▼           ▼           ▼
 Lyricist   Composer    Voice           Mixing          Quality     Packager    (loop)
   │          │           │               │             Judge          │
   ▼          ▼           ▼               ▼               ▼            ▼
 RAG        suno-mcp   rvc-mcp (cloud)  audio-mcp       audio-mcp    LOCAL SAVE
 (Qdrant)   (API)      stem-mcp(cloud)  (DSP+LANDR)     + embed sim  (OUTPUT_DIR)
                       ACE(browser opt)
```

## 2. Layers

### 2.1 Interface Layer
- **CLI** (`cli.py`) — primary surface for the artist/operator.
- **FastAPI** (`api.py`) — `POST /produce`, `GET /status/{run_id}`,
  `POST /publish/{run_id}`. Enables n8n / web triggers.

### 2.2 Orchestration Layer
- **LangGraph** graph (`graph.py`) with a typed shared state (`state.py`).
- Deterministic node order with a **conditional quality-gate loop** edge.
- Each node = one agent. Nodes are pure-ish: read state, do work, write state +
  artifacts to `runs/{run_id}/`.

### 2.3 Agent Layer (`agents/`)
Six agents (full spec in `AGENTS.md`). Agents are thin: they assemble prompts +
call tools (MCP/APIs) + validate against rules. Heavy lifting is in MCP servers.

### 2.4 Tool Layer (`mcp_servers/` + external APIs)
MCP servers expose typed tools (schemas in `MCP_SERVERS.md`):
- `suno-mcp` — music generation + stem extraction (Suno API gateway, API-first).
- `rvc-mcp` — voice conversion + training via **cloud RVC** (Replicate, or free
  Colab/Kaggle tunnel). No local GPU.
- `stem-mcp` — stem separation via **cloud** LALAL.AI / Replicate Demucs.
- `audio-mcp` — analysis, mixing (librosa/pydub/ffmpeg/pyloudnorm); mastering via
  **LANDR API** (matchering fallback); cloud ASR.
External APIs: optional YouTube Data API (off by default).
Browser-agent (Browser Use) optionally drives UI-only tools (Suno UI only if
`SUNO_USE_BROWSER=true`; ACE Studio if `ACE_ENABLED`).

### 2.5 Knowledge & Memory Layer
- **RAG** (`rag/`) — Qdrant + embeddings; retrieval for the Lyricist.
- **Learning File** (`memory/learning.py`) — read/write `config/learning.yaml`.

### 2.6 Governance Layer
- **Rules** (`config/rules.md`) loaded as enforced thresholds (`config.py`).
- **Skills** (`skills/*.md`) loaded as runbooks/system-prompt context per agent.

## 3. Data Flow & Persistence
- A run creates `runs/{run_id}/` containing:
  ```
  manifest.json        # inputs, settings, scores, decisions, artifact index
  lyrics.json
  suno/                # raw suno outputs + candidates
  stems/               # instrumental.wav, guide_vocal.wav, cleaned_vocal.wav
  voice/               # my_voice.wav (converted)
  mix/                 # premaster.wav
  master.wav
  quality_report.json
  cover.png            # or thumbnail_prompt.txt
  logs/
  ```
- State is checkpointed (LangGraph checkpointer) so runs are **resumable**.
- The final bundle is also copied to `OUTPUT_DIR/{date}_{slug}/` for the artist.

## 4. Deployment
- `docker-compose.yml` brings up: Qdrant, suno-mcp, rvc-mcp, stem-mcp, audio-mcp,
  and the FastAPI app — all **lightweight CPU containers** (no GPU).
- Heavy AI is offloaded to cloud APIs (Replicate/LALAL/LANDR/Suno gateway) or a
  free Colab/Kaggle GPU notebook via tunnel. Single host; runs on a laptop.

## 5. Failure & Recovery
- Each MCP call has timeout + retry (tenacity).
- Stage failures mark the node failed in `manifest.json`; `status` shows where to
  resume. Quality-gate failures trigger the bounded correction loop (rules §4).
- Hard stops (ethics violations, third-party voice) abort the run with a logged
  reason.

## 6. Extensibility Seams
- `MusicProvider` interface (Suno today; swappable later).
- `VoiceProvider` interface (Replicate RVC today; Colab/Kaggle tunnel, Kits,
  ACE later).
- `StemProvider` interface (LALAL.AI today; Replicate Demucs / free notebook later).
- `MasteringProvider` interface (LANDR today; matchering fallback).
- `OutputTarget` interface (local save today; YouTube optional later).
- New agents = new LangGraph node + entry in `AGENTS.md`.
