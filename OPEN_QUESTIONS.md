# BhajanForge — Open Questions (answer before / during Codex build)

The build can proceed with the **assumed defaults** below if you don't answer.
Please reply with any changes; Codex will use your answers over the defaults.

---

## ✅ RESOLVED DECISIONS (locked by product owner)
- **Suno access:** API-first via a **third-party Suno-compatible gateway**
  (`SUNO_API_BASE`). Browser fallback OFF unless `SUNO_USE_BROWSER=true`.
- **No local GPU:** voice (Replicate RVC) + stems (LALAL.AI) via **cloud APIs**;
  **FREE** alternative = Google Colab (T4) / Kaggle (~30h/wk) GPU notebooks
  behind a tunnel (`notebooks/README.md`). Same MCP interface either way.
- **Voice range:** **auto-detected** from training audio (`rvc.detect_range`);
  default starting point A2–E4 (male bhajan singer).
- **Mastering:** **LANDR API** primary, **matchering** free fallback.
- **Output:** **saved to the local PC** (`OUTPUT_DIR`). **NO YouTube upload.**

Remaining questions below help tune the build but are not blockers.

---

## A. Artist & Content
1. **Artist/channel name** for metadata & `voice_profile.artist_name`?
   *(default: "Shyam Bhajan Artist")*
2. **Vocal range** (lowest & highest comfortable notes)? Helps keep pitch natural.
   *(default: C3–G4)*
3. Primary **deity/focus** — only Khatu Shyam, or also Krishna/Radha/others?
   *(default: Khatu Shyam, devotional only)*
4. **Language(s)** — Hindi only, or also Rajasthani/Braj/Sanskrit slokas?
   *(default: Hindi)*

## B. Music (Suno)
5. ✅ Resolved: API-first via third-party gateway. → Do you already have a
   **gateway URL + key** to put in `SUNO_API_BASE` / `SUNO_API_KEY`? *(if not,
   you can start with the browser option by setting `SUNO_USE_BROWSER=true`)*
6. Your Suno **plan** (for commercial-use rights & monthly song limits)?
7. How many **candidates per song** should Suno generate? *(default: 2)*

## C. Voice Cloning
8. Confirm: we clone **only your own voice** (yes/no). *(default: yes — required)*
9. ✅ Resolved: RVC primary (cloud), ACE optional. Which voice backend —
   **Replicate** (paid, reliable) or **free Colab/Kaggle**? *(default: Replicate;
   free notebook option documented in `notebooks/README.md`)*
10. Can you provide **clean source vocals**, or extract them from your YouTube
    songs (via cloud stem separation)? *(default: extract via stem-mcp)*

## D. Quality Bar
11. Quality gate score — keep **95/100**? *(default: 95; min allowed 90)*
12. Loudness target — keep **-14 LUFS / -1 dBTP** (YouTube standard)? *(default: yes)*
13. Voice-similarity minimum — keep **0.95**? *(default: 0.95)*

## E. Mastering
14. ✅ Resolved: **LANDR API** primary (matchering fallback). → Provide
    `LANDR_API_KEY`? *(without it, matchering free fallback is used)*
15. Do you have a **reference master** track whose tone/loudness we should match?

## F. Publishing / Output
16. ✅ Resolved: **Save to PC only, no upload.** Output goes to `OUTPUT_DIR`.
17. Where should final files be saved? *(default: `./output/{date}_{slug}/`)*
18. Should the Packager also build a **local lyric/art video**, or just save the
    audio + metadata? *(default: audio + metadata; set `MAKE_VIDEO=true` for video)*
19. ✅ Resolved: No auto-upload. (If you ever enable YouTube later, AI-disclosure
    is mandatory and auto-set.)

## G. Infrastructure
20. ✅ Resolved: **No local GPU** — cloud APIs, or free Colab/Kaggle notebooks.
    → Will you use **Replicate** (provide `REPLICATE_API_TOKEN`) or the **free
    Colab/Kaggle** tunnel for RVC/stems?
21. Which **LLM provider/model** for the agents, and which **embedding model**
    (must handle Hindi/Devanagari well)? *(default: configurable via .env; pick a
    multilingual embedding such as bge-m3)*

## H. Scope
22. Anything to add to v1, or is the v1 scope in `PRD.md §2` correct?
23. Any **traditional/scripture texts** you want ingested into the KB that you
    know are public-domain or that you own?

---

### Notes on a known constraint (not a question, just FYI)
- **Suno has no official public API.** The system isolates Suno behind a
  `MusicProvider` interface and supports either a third-party API endpoint or the
  browser-agent on the Suno web UI. This keeps you on Suno (your choice) while
  staying swappable if Suno's terms/endpoints change. See `config/rules.md` §2.5.
