# BhajanForge — Agent Specifications

Each agent is a LangGraph node. This doc defines, for every agent: purpose,
inputs, outputs (written to `BhajanState` + `runs/{run_id}/`), tools, the system
prompt skeleton, and failure handling. Data shapes are in `DATA_MODELS.md`.

> Common rules for ALL agents:
> - Load `config/rules.md` thresholds and obey them.
> - Load the relevant `skills/*.md` runbook as procedure.
> - Read `config/learning.yaml` before acting; propose updates after.
> - Write artifacts under `runs/{run_id}/` and update `manifest.json`.
> - Never log secrets. Be idempotent (skip work already done for this run).

---

## 1. Lyricist Agent  (`agents/lyricist.py`)
**Purpose:** Produce authentic, devotionally-correct Hindi lyrics in the artist's
style.

**Inputs:** `ProductionRequest` (theme, mood, deity, language, duration_target,
optional `lyrics_override`).

**Tools:** RAG retriever (`rag/retriever.py` → Qdrant), LLM.

**Procedure (`skills/produce_bhajan.md` §Lyricist):**
1. If `lyrics_override` provided → validate & normalize, skip generation.
2. Retrieve top-k context: artist's past lyrics (style), scripture/katha (facts),
   taal/raag notes, pronunciation fixes.
3. Draft structured lyrics: `mukhda` (refrain) + `antara` x N + optional aarti
   outro, matching `duration_target` and `mood`.
4. Add per-line **pronunciation hints** for devotional terms (from KB + learning).
5. Self-check: every devotional term appears in KB with correct spelling; fix
   otherwise. Ensure theological consistency (rules R6.2).

**Output:** `LyricsDoc` → `runs/{id}/lyrics.json`.

**Failure:** If KB lacks the deity/theme context → flag low-confidence in manifest
and proceed with clearly-traditional phrasing; never invent scripture.

**System prompt skeleton:**
```
You are a devotional lyricist for {artist_name}. Write {language} bhajan lyrics
for {deity} on the theme "{theme}", mood "{mood}". Use ONLY the retrieved
context for any scriptural/biographical claims. Mirror the artist's vocabulary
and phrasing shown in the retrieved past lyrics. Output sections: mukhda, antara
(x{n}), [optional] aarti outro. For each line, include a pronunciation hint for
sacred terms. Keep dignity and tradition (see rules).
```

---

## 2. Composer Agent  (`agents/composer.py`)
**Purpose:** Generate the music + a guide vocal/melody using **Suno**.

**Inputs:** `ProductionRequest`, `LyricsDoc`, Learning File winning prompts.

**Tools:** `suno-mcp` (generate, poll, extract_stems); Learning File.

**Procedure (`skills/generate_music.md`):**
1. Select winning prompt template for `mood`; merge with request specifics
   (taal, tempo, instruments) → final Suno style prompt.
2. Submit lyrics + style to `suno-mcp.generate` (request `MUSIC_CANDIDATES`).
3. Poll `suno-mcp.get_task` until complete or `SUNO_MAX_WAIT_SEC`.
4. For each candidate, `suno-mcp.extract_stems` → instrumental + vocal stems.
5. Score candidates (length match, clarity, prompt adherence heuristic; optional
   quick LLM listen) → pick best.

**Output:** `MusicResult` → `runs/{id}/suno/*`, `stems/instrumental.wav`,
`stems/guide_vocal.wav`.

**Failure:** API error/timeout → retry; only if `SUNO_USE_BROWSER=true`, fall back
to browser-agent Suno flow (`SUNO_WEB_*`). Mispronunciation suspected → pass note
to Quality Judge for later.

---

## 3. Voice Agent  (`agents/voice.py`)
**Purpose:** Convert the guide vocal into the **artist's cloned voice**.

**Inputs:** `stems/guide_vocal.wav`, `voice_profile` (learning), rules R5.*.

**Tools:** `stem-mcp` (cloud isolate/clean), `rvc-mcp` (cloud convert; train at
setup time), optional ACE Studio via browser-agent. (No local GPU — backends:
Replicate, or free Colab/Kaggle tunnel.)

**Procedure (`skills/clone_voice.md`):**
1. `stem-mcp.isolate` on guide vocal to remove residual instrumentation (skip if
   Suno stems are already clean).
2. Determine pitch shift to keep within artist range (R5.2).
3. `rvc-mcp.convert` with `voice_profile.best_settings` (index_ratio, f0_method,
   protect, resample_sr).
4. Quick self-check similarity (call embedding sim helper); if < R3.4, retry with
   adjusted index_ratio/f0 before giving up (R5.3).
5. (Optional) If `ACE_ENABLED` and a guide vocal is undesirable, use ACE Studio
   SVS path from MIDI + lyrics instead.

**Output:** `VoiceResult` → `runs/{id}/voice/my_voice.wav` (+ similarity score).

**Setup-time training (FR-23, see `skills/clone_voice.md` §Training):**
`voice train` → yt-dlp download → `stem-mcp.batch_isolate` → `rvc-mcp.train` →
`rvc-mcp.detect_range` → register model ref + range + best_settings in
`learning.yaml`.

---

## 4. Mixing Agent  (`agents/mixing.py`)
**Purpose:** Combine vocal + instrumental and produce a professional master.

**Inputs:** `voice/my_voice.wav`, `stems/instrumental.wav`, `mix_preferences`.

**Tools:** `audio-mcp` (align, eq, compress, deess, reverb, master). Mastering
backend = **LANDR API** (primary) with **matchering** fallback.

**Procedure (`skills/mix_and_master.md`):**
1. Time-align vocal to instrumental (offset detection).
2. Vocal chain: de-noise/de-reverb cleanup → low cut → presence EQ → compression
   → de-ess → send to reverb (`mix_preferences.reverb_preset`).
3. Balance levels (vocal-forward but blended).
4. Bounce premaster → master to **-14 LUFS / <= -1 dBTP** via LANDR API
   (`MASTERING_PROVIDER=landr`); fall back to matchering if LANDR unavailable.

**Output:** `MixResult` → `runs/{id}/mix/premaster.wav`, `runs/{id}/master.wav`.

**Failure:** Loudness/peak off target → re-run mastering with adjusted gain.

---

## 5. Quality Judge Agent  (`agents/quality_judge.py`)
**Purpose:** Decide pass/fail against the gate and drive the correction loop.

**Inputs:** `master.wav`, artist reference embedding, `LyricsDoc`, rules thresholds.

**Tools:** `audio-mcp` (loudness, true-peak, artifact detection, pitch stability),
embedding similarity helper, LLM (perceptual listen + pronunciation check vs KB).

**Procedure (`skills/quality_review.md`):**
1. Objective metrics: integrated LUFS, true peak, vocal/instr balance,
   pitch-stability, artifact score.
2. Voice similarity vs reference embedding (R3.4).
3. Pronunciation check of devotional terms vs KB (R3.6) — transcribe & compare.
4. Compute weighted 0–100 score; build `QualityReport` with per-criterion results
   and **fixes mapped to the responsible stage**.
5. Decision: `>= QUALITY_GATE` → pass; else return failing stage + fixes for loop
   (respect `MAX_LOOP_ATTEMPTS`, `MAX_TOTAL_LOOPS`; avoid repeating known-bad fix).

**Output:** `QualityReport` → `runs/{id}/quality_report.json`; sets
`state.gate_passed` and `state.next_stage_on_fail`.

**Scoring weights (default — Codex make configurable):**
```
voice_similarity 30 | pronunciation 20 | loudness/peak 15 | artifacts 15 |
mix balance 10 | musical fit to mood/taal 10
```

---

## 6. Publisher Agent  (`agents/publisher.py`)
## 6. Packager Agent  (`agents/packager.py`)
**Purpose:** Package the finished bhajan and **save it to the local machine**
(no upload).

**Inputs:** `master.wav`, `LyricsDoc`, `ProductionRequest`, run scores.

**Tools:** LLM (title/desc/tags), artwork generation (image model or
prompt-only), ffmpeg (optional local video). NO upload tools by default.

**Procedure (`skills/publish.md`):**
1. Generate SEO-friendly devotional title, description (lyrics + respectful
   hashtags + a reminder to tick YouTube's "Altered/Synthetic content" box on
   manual upload), and tags — written as `.txt` files.
2. Create artwork (`cover.png` via image model if configured, else
   `thumbnail_prompt.txt`).
3. If `MAKE_VIDEO=true` → render a simple static-art / lyric video (ffmpeg)
   locally.
4. Save the full bundle to `OUTPUT_DIR/{date}_{slug}/` (master + metadata +
   artwork + quality_report). **Do NOT upload** (`PUBLISH_TARGET=local`).
5. Only if `PUBLISH_TARGET=youtube` AND valid creds: upload via YouTube API with
   the **synthetic-content disclosure flag set** (R2.3).

**Output:** `PublishResult` → manifest (`output_dir`, status `saved_local`).

**Failure:** If `PUBLISH_TARGET=youtube` but creds missing → save locally and
mark `needs_human`; never upload without the disclosure flag.

---

## Orchestrator (not a node — the graph itself, `graph.py`)
- Initializes state, loads rules/skills/learning.
- Runs nodes in order: Lyricist → Composer → Voice → Mixing → Quality Judge →
  (loop or) Packager → Memory update.
- Enforces hard stops (ethics) before/within nodes.
- See `ORCHESTRATION.md` for the exact graph, edges, and loop logic.
