# SKILL: generate_music  (Composer Agent — Suno)

Generate music + a guide vocal for the lyrics using **Suno** (via `suno-mcp`).

## Inputs
`ProductionRequest`, `LyricsDoc`, `learning.yaml.music_preferences`.

## Procedure

1. **Build the style prompt.**
   - Start from `music_preferences.winning_prompts[mood]`.
   - Merge request specifics: deity, taal, tempo (BPM), instruments, language,
     duration hint. Avoid anything in `music_preferences.rejected_styles`.
   - Keep it devotional and instrument-specific (harmonium, tabla, dholak,
     bansuri, tanpura, manjira) per the artist's style.

2. **Generate candidates.**
   - `suno.generate({ lyrics: LyricsDoc.as_suno_text(), style_prompt,
     model: SUNO_MODEL, candidates: MUSIC_CANDIDATES, duration_hint_sec })`.
   - Poll `suno.get_task(task_id)` every `SUNO_POLL_INTERVAL_SEC` until complete
     or `SUNO_MAX_WAIT_SEC`.

3. **Download + extract stems for each candidate.**
   - `suno.download(clip_id, dest_dir="runs/{id}/suno")`.
   - `suno.extract_stems(clip_id, dest_dir="runs/{id}/stems")`.
   - If endpoint lacks stem support → `stem.isolate(target="both")` on the clip.

4. **Pick the best candidate.**
   - Heuristic score: duration match to target, prompt adherence, vocal clarity,
     absence of obvious mispronunciation (optional quick LLM listen on a snippet).
   - Record `winning_prompt_key` and `chosen_index`.

   > Stems source: prefer Suno's own `extract_stems`. If unavailable, the Voice
   > stage cleans the guide vocal via `stem-mcp` (cloud). The chosen guide vocal
   > becomes the input the Voice Agent converts into the artist's voice.

5. **Output `MusicResult`** with chosen instrumental + guide vocal paths.

## Fallback (no API)
Only if `SUNO_USE_BROWSER=true` (off by default): use the browser-agent
(`browser.suno_generate`) to drive the Suno web UI — log in (`SUNO_WEB_*`,
isolated profile), submit prompt + lyrics, wait, "Extract Stems", download WAVs.
Then continue at step 4. Otherwise, on API error, retry then surface the error.

## Guardrails
- Devotional style only (R1.1). Lead must be the artist later (Voice stage).
- Respect Suno plan commercial terms (R2.5). Draft mode default downstream.

## Failure handling
- Timeout → retry once with fewer candidates; then surface error to orchestrator.
- Suspected mispronunciation → tag in state so Quality Judge checks it (R3.6).

## Output artifacts
`runs/{id}/suno/*`, `runs/{id}/stems/instrumental.wav`,
`runs/{id}/stems/guide_vocal.wav`.
