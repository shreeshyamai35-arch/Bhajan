# Skill: Generate Music (Composer → suno-mcp)

1. Select the winning prompt template for the request `mood` from
   `learning.yaml: music_preferences.winning_prompts`.
2. Merge with request specifics (deity, taal, tempo, instruments, language) into
   a single Suno style prompt.
3. `suno.generate` with `candidates = MUSIC_CANDIDATES` (lyrics = `LyricsDoc.as_suno_text()`).
4. Poll `suno.get_task` until `complete` or `SUNO_MAX_WAIT_SEC`.
5. For each clip: `suno.download` then `suno.extract_stems`
   (→ `stems/instrumental.wav`, `stems/guide_vocal.wav`). If the gateway lacks
   stems, fall back to `stem.isolate` on the downloaded clip.
6. Score candidates (duration match to target; clarity) and pick the best.

**Failure:** API error/timeout → retry with backoff. Only if
`SUNO_USE_BROWSER=true`, fall back to the browser-agent Suno flow.

**Avoid** the styles listed in `learning.yaml: music_preferences.rejected_styles`.
