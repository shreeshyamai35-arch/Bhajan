# BhajanForge — Rules File (Runtime Guardrails)

> Every agent loads this file at startup. These rules are **non-negotiable**.
> Precedence: `PRD.md` > `rules.md` > `skills/*.md` > Learning File > agent judgment.
> Codex MUST implement these as enforced checks (not just documentation) and
> cover them with unit tests (see PRD AC-8).

---

## 1. IDENTITY & SCOPE
- R1.1 The system produces **devotional music only** (bhajan, aarti, kirtan,
  stuti, chalisa). Reject any request for other genres.
- R1.2 Default deity context is **Khatu Shyam / Shyam Baba** unless the request
  specifies another devotional subject.
- R1.3 All lead vocals MUST be the **artist's cloned voice**. No other voice may
  appear as the lead. Backing choruses, if any, must be clearly non-lead.

## 2. ETHICS & LEGAL  (HARD STOPS)
- R2.1 Only the **artist's own voice** may be cloned. If any request attempts to
  clone a third party, **refuse and halt the run**.
- R2.2 Voice training data must come only from the artist's own recordings.
- R2.3 **Output is saved locally only** (`PUBLISH_TARGET=local`). The system does
  **NOT** upload to YouTube. IF the artist later opts in (`PUBLISH_TARGET=youtube`
  with valid creds), the upload MUST set the **synthetic/AI-altered content
  disclosure flag**; uploading without it is forbidden. The Packager always adds
  a reminder in `description.txt` to tick that box on manual upload.
- R2.4 Do not reproduce copyrighted melodies/lyrics. Lyrics must be original or
  traditional/public-domain devotional text verified via the knowledge base.
- R2.5 **LEGAL NOTE (Suno):** Suno has no official public API. The system uses a
  configured Suno-compatible **API gateway** (preferred) or, only if
  `SUNO_USE_BROWSER=true`, the Suno web UI via browser-agent. Keep music
  generation behind the `MusicProvider` interface so the source can be swapped.
  Respect Suno's commercial-use terms for the active plan.
- R2.6 **Cloud services:** voice (Replicate), stems (LALAL.AI), mastering (LANDR)
  and ASR run in the cloud. Send only the audio needed for the task; never send
  secrets in payloads; store provider keys in env only.

## 3. QUALITY GATE  (the "100%" bar)
- R3.1 Default publish threshold: **Quality Judge score >= 95 / 100**
  (configurable via `QUALITY_GATE` env, never below 90).
- R3.2 Loudness target: **-14 LUFS integrated (±1.0)**.
- R3.3 True peak: **<= -1.0 dBTP**.
- R3.4 Voice similarity to artist reference embedding: **>= 0.95 cosine**.
- R3.5 Artifact score (robotic/glitch detector) must be **below** the configured
  artifact ceiling.
- R3.6 Pronunciation of all devotional terms MUST be verified against the
  knowledge base. **Zero** known mispronunciations allowed in the final.
- R3.7 No clipping, no audible dropouts, no abrupt vocal-only or silent gaps
  longer than the configured max.

## 4. CORRECTION LOOP CONTROL
- R4.1 On gate failure, the Quality Judge returns the **failing stage** + fixes.
- R4.2 Max regeneration attempts per stage: **4** (`MAX_LOOP_ATTEMPTS`).
- R4.3 Max total loops per run: **8** (`MAX_TOTAL_LOOPS`).
- R4.4 On exhausting attempts, **escalate to the human** (do not publish);
  write a clear failure summary to the run manifest.
- R4.5 Each loop MUST apply a *different* fix than the previous identical failure
  (read Learning File; avoid repeating a known-bad setting).

## 5. VOICE FIDELITY
- R5.1 Always use the RVC settings recorded in `learning.yaml` as the starting
  point; only deviate when fixing a specific judge finding.
- R5.2 Pitch shift must keep the melody within the artist's natural range
  (configured in `learning.yaml: voice_profile.range`).
- R5.3 If similarity < R3.4, retry conversion with adjusted index ratio / f0
  method before regenerating the whole track.

## 6. CONTENT & RESPECT
- R6.1 Maintain devotional dignity: no irreverent, comedic, or commercialized
  treatment of sacred figures.
- R6.2 Keep lyrics theologically consistent with the retrieved scripture/context.
- R6.3 Prefer the artist's signature vocabulary/phrasing from their past bhajans.

## 7. DATA & PRIVACY
- R7.1 Secrets only via environment variables; never hard-code or log them.
- R7.2 The browser-agent profile may hold ONLY music-tool logins (Suno, ACE).
  Never store email/banking/social-master credentials there.
- R7.3 Persist run artifacts under `runs/{run_id}/`; never delete inputs
  automatically.

## 8. OPERATIONAL
- R8.1 Every stage is idempotent and resumable by `run_id`.
- R8.2 Default mode is **draft** (`PUBLISH_MODE=draft`). Auto-publish only when
  explicitly enabled.
- R8.3 Write a `manifest.json` per run capturing inputs, settings, scores,
  artifact paths, and final decision.

---

### Machine-readable thresholds (Codex: load these as defaults)
```yaml
quality_gate: 95
min_quality_gate: 90
loudness_lufs: -14.0
loudness_tolerance: 1.0
true_peak_dbtp: -1.0
voice_similarity_min: 0.95
artifact_score_max: 0.20        # 0=clean .. 1=heavy artifacts
max_loop_attempts: 4
max_total_loops: 8
max_silence_gap_sec: 2.5
publish_mode: draft             # draft | auto  (review gating)
publish_target: local           # local | youtube  (default local = save to PC, no upload)
devotional_only: true
allow_third_party_voice: false  # MUST stay false
require_ai_disclosure: true     # MUST stay true (applies only if publish_target=youtube)
```
