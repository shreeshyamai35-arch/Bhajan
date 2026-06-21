# SKILL: quality_review  (Quality Judge Agent)

Score the master against the gate and, on failure, return the failing stage +
concrete fixes for the correction loop.

## Inputs
`runs/{id}/master.wav`, `runs/{id}/voice/my_voice.wav`,
`voice_profile.reference_embedding`, `LyricsDoc`, rules thresholds.

## Procedure

1. **Objective metrics** via `audio.analyze`:
   - integrated LUFS, true-peak dBTP, vocal/instrumental balance,
     pitch_stability, artifact_score, max_silence_gap.

2. **Voice similarity** vs `reference_embedding` (cosine). Threshold R3.4 (0.95).

3. **Pronunciation check** (R3.6):
   - `audio.transcribe(master, language="hi")` → compare against `LyricsDoc`
     devotional_terms + `learning.yaml.pronunciation_fixes`. Any mismatch on a
     sacred term = hard fail on this criterion.

4. **Perceptual listen** (LLM, optional): naturalness / devotional feel sanity check.

5. **Score (weighted 0–100):**
   ```
   voice_similarity 30 | pronunciation 20 | loudness_peak 15 |
   artifacts 15 | mix_balance 10 | musical_fit 10
   ```
   - "Hard" criteria that must individually pass regardless of total:
     pronunciation (R3.6), loudness/peak (R3.2/R3.3), voice_similarity (R3.4),
     artifacts below ceiling (R3.5).

6. **Decision & routing:**
   - PASS if `score >= QUALITY_GATE` AND all hard criteria pass.
   - Else build `fixes[]` mapped to the responsible stage and set
     `next_stage_on_fail`:
     | Failing criterion | Stage | Example fix |
     |---|---|---|
     | voice_similarity / artifacts | `voice` | adjust index_ratio, f0_method, lower pitch shift |
     | pronunciation | `composer` (regen) or `voice` | regenerate clip / pick other candidate / fix lyrics hint |
     | loudness / peak | `mixing` | re-master with adjusted gain |
     | mix_balance | `mixing` | change vocal_gain_db |
     | musical_fit (mood/taal) | `composer` | new style prompt / candidate |
   - Respect `max_loop_attempts` & `max_total_loops`; never repeat a known-bad
     fix (consult learning history) — R4.5.

## Output `QualityReport`
`score`, `passed`, `criteria[]`, `fixes[]`, `next_stage_on_fail`, raw `metrics`.
Write to `runs/{id}/quality_report.json`.

## Guardrails
- Do not pass anything failing a hard criterion, even with a high total score.
