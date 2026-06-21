# SKILL: produce_bhajan  (master runbook)

Produce ONE finished bhajan end-to-end. The Orchestrator follows this; each
stage links to its detailed skill file.

## Preconditions
- A trained voice model is registered in `learning.yaml`
  (`voice_profile.active_rvc_model`). If not, run `voice train` first
  (see `clone_voice.md` §Training).
- RAG KB ingested (`kb ingest`).
- `.env` configured; MCP servers + Qdrant running.

## Inputs
`ProductionRequest` (theme, mood, deity, taal, tempo, language,
duration_target_sec, optional lyrics_override, publish_mode).

## Procedure

### STEP 0 — Intake (orchestrator)
1. Validate request against `rules.md` (R1 devotional only; R2 ethics).
2. HARD STOP if non-devotional or third-party voice → abort with reason.
3. Create `run_id` + `runs/{run_id}/`; snapshot rules + learning into state.

### STEP 1 — Lyricist  → `lyrics.json`
- Follow Lyricist spec in `docs/AGENTS.md` §1.
- RAG-retrieve style + scripture; write sectioned lyrics with pronunciation hints.

### STEP 2 — Composer (Suno)  → `stems/instrumental.wav`, `stems/guide_vocal.wav`
- Follow `generate_music.md`.

### STEP 3 — Voice  → `voice/my_voice.wav`
- Follow `clone_voice.md` §Conversion.

### STEP 4 — Mixing & Mastering  → `master.wav`
- Follow `mix_and_master.md`.

### STEP 5 — Quality Judge  → `quality_report.json`
- Follow `quality_review.md`.
- If `score >= QUALITY_GATE` and all hard criteria pass → go to STEP 6.
- Else apply fixes and LOOP to the failing stage (composer/voice/mixing),
  respecting `max_loop_attempts` (4) and `max_total_loops` (8). On exhaustion →
  mark `needs_human`, write failure summary, STOP (do not publish).

### STEP 6 — Packager  → saved locally
- Follow `publish.md`. Saves the finished bundle to `OUTPUT_DIR/{date}_{slug}/`
  (master + metadata + artwork). **No upload** (`PUBLISH_TARGET=local`).

### STEP 7 — Memory
- Append a `quality_history` entry; update `best_settings`, `winning_prompts`,
  and any new `pronunciation_fixes`; bump `stats`. Write `manifest.json`.

## Outputs
`runs/{run_id}/master.wav`, `quality_report.json`, `manifest.json`,
the local bundle in `OUTPUT_DIR/{date}_{slug}/`, and updated `config/learning.yaml`.

## Done when
AC-1..AC-5 satisfied: a >=95 master produced hands-free, saved locally, resumable,
with learning updated.
