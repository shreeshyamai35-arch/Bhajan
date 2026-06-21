# 🕉️ BhajanForge

> Autonomous AI system that produces **studio-grade devotional bhajans sung in the
> artist's own cloned voice** — from a one-line request to a YouTube-ready master.

BhajanForge is a multi-agent crew (LangGraph) that writes authentic lyrics,
generates music with **Suno**, sings them in **your cloned voice** (RVC), mixes &
masters to professional loudness, enforces a quality gate, and publishes to YouTube
with the required AI-content disclosure.

📄 **Start here:** [`PRD.md`](./PRD.md) is the authoritative build spec.
📋 **Build order:** [`docs/ROADMAP.md`](./docs/ROADMAP.md)
❓ **Answer first:** [`OPEN_QUESTIONS.md`](./OPEN_QUESTIONS.md)

---

## What it does (in one picture)

```
request ──► Lyricist(RAG) ──► Composer(Suno API) ──► Voice(cloud RVC)
        ──► Mixing(DSP+LANDR) ──► Quality Judge(≥95?) ──► Packager(SAVE TO PC)
                                          │ if <95
                                          └── auto-fix & loop
```
**No GPU. No auto-upload.** Cloud APIs (or free Colab/Kaggle) do the heavy AI;
the finished bhajan is saved to your computer.

---

## Prerequisites

**No GPU required** — all heavy AI runs via cloud APIs (or a free Colab/Kaggle
notebook). BhajanForge runs on any normal CPU machine/laptop.

| Requirement | Why |
|-------------|-----|
| Python 3.11+ | runtime |
| FFmpeg | audio I/O |
| Docker + docker-compose | run lightweight MCP servers + Qdrant (CPU only) |
| Qdrant | RAG vector store (via docker-compose) |
| A Suno-compatible API endpoint (recommended) | music generation (API-first) |
| Replicate token **or** a free Colab/Kaggle GPU notebook | voice cloning (RVC) |
| LALAL.AI key (or Replicate/free notebook) | stem separation |
| LANDR API key | label-grade mastering (matchering used as free fallback) |
| Cloud ASR key | pronunciation checking |
| LLM + embedding provider keys | agents + RAG |

> Final audio is **saved to your PC** (`OUTPUT_DIR`). The system does **not**
> upload to YouTube — it prepares a ready-to-upload bundle for manual upload.
> Free GPU option: see [`notebooks/README.md`](./notebooks/README.md).

---

## Quick Start

```bash
# 1. Clone / open this repo
cd BhajanForge

# 2. Configure secrets
cp config/.env.example .env
# edit .env and fill in keys (see config/.env.example for every variable)

# 3. Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # or: pip install -e .

# 4. Start infra (Qdrant + MCP servers)
docker-compose up -d

# 5. One-time: build the RAG knowledge base from your existing bhajans
bhajanforge kb ingest --source knowledge_base/sources/

# 6. One-time: train your voice model from your YouTube bhajans
bhajanforge voice train \
  --youtube-urls knowledge_base/sources/youtube_urls.txt \
  --model-name shyam_voice_v1

# 7. Produce a bhajan (saves the finished bundle to ./output — NO upload)
bhajanforge produce \
  --theme "morning darshan of Khatu Shyam" \
  --mood slow-emotional \
  --taal keherwa \
  --tempo 72

# 8. Find your finished bhajan in:  ./output/<date>_<slug>/master.wav
#    (+ title.txt, description.txt, tags.txt, cover.png, quality_report.json)
#    Upload to YouTube yourself whenever you like — remember to tick the
#    "Altered/Synthetic content" box.
```

---

## Configuration Files (read before building)

| File | Purpose |
|------|---------|
| `config/rules.md` | Hard guardrails: quality bar, ethics, loop limits. Agents MUST obey. |
| `config/learning.yaml` | Persistent memory: best settings, winning prompts, fixes. |
| `config/.env.example` | Every environment variable the system reads. |
| `skills/*.md` | Step-by-step runbooks each agent follows. |
| `knowledge_base/README.md` | How to ingest lyrics & scripture for RAG. |

---

## Key Commands (CLI surface — Codex implements `src/bhajanforge/cli.py`)

| Command | Description |
|---------|-------------|
| `bhajanforge produce ...` | Run the full pipeline; saves bundle to `OUTPUT_DIR` (no upload) |
| `bhajanforge publish --run-id ID` | Re-package a run (build video; upload only if `PUBLISH_TARGET=youtube`) |
| `bhajanforge voice train ...` | Train/retrain the artist cloud RVC voice model |
| `bhajanforge kb ingest ...` | Ingest documents into the RAG store |
| `bhajanforge status --run-id ID` | Show pipeline status / resume |
| `bhajanforge serve` | Start the FastAPI trigger server |

---

## Safety, Ethics & Legal

- **Only the artist's own voice** may be cloned (consent = self). Enforced in
  `config/rules.md` and unit-tested.
- **No auto-upload.** Output is saved locally (`PUBLISH_TARGET=local`). If you
  ever enable YouTube upload, the **synthetic/altered-content disclosure** is
  mandatory; the Packager also reminds you in `description.txt`.
- Music source (Suno) is isolated behind a `MusicProvider` interface; see the
  LEGAL note in `config/rules.md` regarding Suno's terms.
- The optional browser-agent (off by default) runs in an **isolated profile**
  with only music-tool logins.

---

## License
Private project for the artist. Generated music + cloned-voice output is the
artist's own work (see rules.md §LEGAL).
