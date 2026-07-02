# Skill: Publish / Package (Packager Agent — LOCAL SAVE)

Default behaviour is **save to PC, never upload** (`PUBLISH_TARGET=local`, R2.3).

1. Generate metadata:
   - **title** — SEO-friendly devotional title.
   - **description** — includes the full lyrics, respectful hashtags, and a
     **mandatory reminder** to tick YouTube's *"Altered/Synthetic content"* box on
     manual upload (FR-21b / R2.3).
   - **tags** — devotional + theme keywords.
2. Artwork — `cover.png` via an image model if configured, else `thumbnail_prompt.txt`.
3. If `MAKE_VIDEO=true` **and** ffmpeg is available → render a static-art/lyric
   `video.mp4` locally. Otherwise skip.
4. Save the bundle to `OUTPUT_DIR/{date}_{slug}/`:
   `master.wav`, `title.txt`, `description.txt`, `tags.txt`,
   `cover.png`|`thumbnail_prompt.txt`, `quality_report.json`, (+ `video.mp4`).
   **Do NOT upload.**
5. Upload path (opt-in only): if `PUBLISH_TARGET=youtube` **and** valid creds →
   upload with the **AI-disclosure flag set** (never omit). Missing creds → keep
   local and mark `needs_human`.

`bhajanforge publish --run-id ID` re-enters here (e.g. to rebuild the video).
