# 🕉️ BhajanForge

> Autonomous AI system that produces **studio-grade devotional bhajans sung in the
> artist's own cloned voice** — from a one-line request to a YouTube-ready master,
> saved to your PC.

BhajanForge is a multi-agent crew (LangGraph) that writes authentic lyrics,
generates music via **Suno**, sings them in **your cloned voice** (cloud RVC),
mixes & masters to streaming loudness, enforces a **≥ 95/100 quality gate** with
an automatic correction loop, and saves a ready-to-upload bundle locally.

**No GPU. No auto-upload.** Cloud APIs (or free Colab/Kaggle) do the heavy AI; the
pipeline runs on any CPU machine. Output is saved to `OUTPUT_DIR`.

📄 Authoritative spec: [`PRD.md`](./PRD.md) · build order: [`docs/ROADMAP.md`](./docs/ROADMAP.md)

---

## Architecture

```
request ─► Lyricist(RAG) ─► Composer(suno-mcp) ─► Voice(rvc-mcp, cloud)
        ─► Mixing(audio-mcp + LANDR) ─► Quality Judge(≥95?) ─► Packager(LOCAL SAVE)
                                              │ if <95
                                              └── auto-fix & loop (max 4/stage, 8 total)
```

| Layer | Modules |
|-------|---------|
| Orchestration | `graph.py` (LangGraph state machine + quality loop), `state.py` |
| Agents (M6) | `agents/{lyricist,composer,voice,mixing,quality_judge,packager}.py` |
| MCP servers | `mcp_servers/{suno,rvc,stem,audio}_mcp/` — each `core.py` (in-process) + `__main__.py` (MCP) |
| Knowledge / Memory | `rag/` (Qdrant + embeddings), `memory/learning.py` (`config/learning.yaml`) |
| Governance | `config/rules.md` (loaded + enforced + unit-tested) |
| Surfaces | `cli.py` (Typer), `api.py` (FastAPI) |

Every heavy capability sits behind a **provider interface** with a deterministic
**mock mode**, so the whole pipeline runs and the full test suite passes offline
with no API keys. Plug real keys into `.env` for live runs.

---

## Quick start

```powershell
# 1. Create a virtualenv and install
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .

# 2. Configure secrets (optional for offline/mock runs)
copy config\.env.example .env   # then edit .env

# 3. (offline) run the test suite
$env:PYTHONPATH="src"; $env:BHAJANFORGE_MOCK="1"
.\.venv\Scripts\python.exe -m pytest src/tests -q

# 4. Produce a bhajan (mock mode saves a bundle to ./output)
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m bhajanforge.cli produce --theme "morning darshan of Khatu Shyam" --mood slow-emotional
```

On Linux/macOS use `source .venv/bin/activate` and `export PYTHONPATH=src`.

### Infra (live mode)
`docker-compose up -d` starts Qdrant + the four MCP servers + the API (CPU-only).

---

## CLI

| Command | Description |
|---------|-------------|
| `bhajanforge produce --theme ... [--mood --deity --taal --tempo --candidates]` | Full pipeline → local bundle (no upload) |
| `bhajanforge publish --run-id ID` | Re-package a run |
| `bhajanforge voice train --youtube-urls FILE --model-name NAME` | Train/retrain the cloud RVC voice model |
| `bhajanforge kb ingest --source DIR` | Ingest documents into the RAG store |
| `bhajanforge status --run-id ID` | Show run manifest / resume info |
| `bhajanforge serve` | Start the FastAPI trigger server |

---

## Output bundle

`OUTPUT_DIR/{date}_{slug}/` contains `master.wav`, `title.txt`, `description.txt`
(lyrics + the mandatory *Altered/Synthetic content* disclosure reminder),
`tags.txt`, `cover.png` or `thumbnail_prompt.txt`, `quality_report.json`, and
`video.mp4` (only if `MAKE_VIDEO=true`). Nothing is uploaded.

---

## Configuration

| File | Purpose |
|------|---------|
| `config/rules.md` | Hard guardrails (quality bar, ethics, loop limits) — loaded and enforced in code |
| `config/learning.yaml` | Persistent memory: best RVC settings, winning prompts, pronunciation fixes, quality history |
| `config/.env.example` | Every environment variable the system reads |
| `skills/*.md` | Step-by-step runbooks each agent follows |
| `mcp.json` | MCP server registration |

---

## Safety, ethics & legal

- **Only the artist's own voice** may be cloned (R2.1) — enforced in `intake` and
  unit-tested; non-devotional requests are refused (R1.1).
- **No auto-upload.** `PUBLISH_TARGET=local` by default. If YouTube upload is ever
  enabled, the **synthetic/AI-altered content disclosure** is mandatory.
- Music (Suno) sits behind a swappable `MusicProvider`; see `config/rules.md §2.5`.

## Status

All 10 milestones (M0–M9) are implemented and the offline test suite is green
(see `docs/ROADMAP.md`). Live runs require provider keys in `.env`
(LLM, Suno gateway, Replicate, LALAL.AI, LANDR, cloud ASR, embeddings).
