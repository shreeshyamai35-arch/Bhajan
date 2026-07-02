# Skill: Quality Review (Quality Judge → audio-mcp)

Compute metrics, score 0–100, decide pass/fail, and on failure return the failing
stage + concrete fixes for the correction loop.

## Metrics (`audio.analyze`)
- Integrated **LUFS** (target -14 ±1) and **true peak** (≤ -1 dBTP).
- **Voice similarity** vs the artist reference embedding (≥ 0.95, R3.4).
- **Artifact score** (≤ artifact ceiling), **pitch stability**, vocal/instrument balance.
- **Pronunciation** of devotional terms vs KB (`audio.transcribe`, R3.6) — verified
  only with a real cloud ASR; skipped offline.

## Scoring weights (default, configurable)
`voice_similarity 30 | pronunciation 20 | loudness/peak 15 | artifacts 15 |
mix balance 10 | musical fit 10`

## Decision
- `passed = score ≥ QUALITY_GATE AND all hard criteria pass`
  (hard = voice_similarity, pronunciation, loudness/peak, artifacts).
- On fail: pick the cheapest effective stage (mixing < voice < composer), attach
  fixes (e.g. new `index_ratio`, re-master gain), set `next_stage_on_fail`.
- Respect `MAX_LOOP_ATTEMPTS` (4) and `MAX_TOTAL_LOOPS` (8); each retry must apply
  a *different* fix than the last identical failure (R4.5). On exhaustion → human.
