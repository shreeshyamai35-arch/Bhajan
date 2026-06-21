# SKILL: package_and_save  (Packager Agent — LOCAL SAVE, no upload)

Package the finished master and **save everything to the local machine**.
Per the product owner's decision, BhajanForge does **NOT** upload to YouTube.
It prepares a ready-to-upload bundle the artist uploads manually whenever they want.

## Inputs
`runs/{id}/master.wav`, `LyricsDoc`, `ProductionRequest`, run scores, env.

## Procedure

1. **Generate metadata (LLM)** — saved as files, NOT posted anywhere.
   - `title.txt` — devotional, SEO-aware (deity + theme).
   - `description.txt` — short intro + full lyrics + respectful hashtags
     (#KhatuShyam #ShyamBaba #Bhajan) + a short honest note that the track uses
     AI-assisted production with the artist's own voice.
   - `tags.txt` — comma-separated tags.

2. **Artwork.**
   - If an image model is configured → generate respectful devotional art
     (no real people's faces) → `cover.png`.
   - Else write `thumbnail_prompt.txt` for manual creation.

3. **Optional local video** (only if `MAKE_VIDEO=true`).
   - ffmpeg: static art OR lyric video (lyrics timed via `audio.transcribe`)
     over `master.wav` → `video.mp4`. Saved locally only.

4. **Save the bundle to `OUTPUT_DIR`.**
   ```
   {OUTPUT_DIR}/{YYYY-MM-DD}_{slug}/
     ├── master.wav            # the finished, mastered bhajan
     ├── title.txt
     ├── description.txt
     ├── tags.txt
     ├── cover.png             # or thumbnail_prompt.txt
     ├── video.mp4             # only if MAKE_VIDEO=true
     └── quality_report.json   # copy of the run's score breakdown
   ```

5. **Do NOT upload.** `PUBLISH_TARGET=local` (default) → finish here and tell the
   artist the exact output folder path.

## Output `PublishResult`
title, description, tags, artwork_path, video_path (opt), `output_dir`,
`status = "saved_local"`. (`youtube_*` stay null; `ai_disclosure_set` carried for
the artist's reference when they upload manually.)

## Guardrails
- Never upload anywhere unless `PUBLISH_TARGET=youtube` is explicitly set AND
  valid creds exist — and even then the AI-disclosure flag is mandatory (R2.3).
- Maintain devotional dignity in all metadata/art (R6.1).
- Include a note in `description.txt` reminding the artist to tick YouTube's
  "Altered/Synthetic content" box when they upload manually.
