# BhajanForge — MCP Servers & Tool Contracts

All external capabilities are exposed as **MCP tools** so any agent (or another
MCP client like Codex) can call them uniformly. Build each server with the
**MCP Python SDK**. Tools are described below with input/output schemas (JSON).

> **No local GPU.** Every heavy audio-AI task runs via a **cloud API**. The MCP
> servers are thin wrappers around those APIs, so BhajanForge runs on any CPU
> machine/laptop.
>
> Convention: every tool returns `{ "ok": bool, "error": str|null, ...payload }`.
> Long operations return a `task_id`; clients poll a `get_*` tool.

---

## 1. suno-mcp  (Music generation — PRIMARY, API-FIRST)

**Reality:** Suno has **no official public API**. This server wraps a configured
Suno-compatible third-party gateway (`SUNO_API_BASE`/`SUNO_API_KEY`) — the
**recommended** path. A browser-agent fallback exists but is OFF unless
`SUNO_USE_BROWSER=true`.

### Tools

#### `suno.generate`
```json
// input
{ "lyrics": "string", "style_prompt": "string", "model": "suno-v5.5",
  "make_instrumental": false, "candidates": 2, "duration_hint_sec": 240 }
// output
{ "ok": true, "task_id": "string", "candidates": 2 }
```

#### `suno.get_task`
```json
// input  { "task_id": "string" }
// output { "ok": true, "status": "queued|running|complete|failed",
//          "clips": [ { "clip_id": "string", "audio_url": "string",
//                       "duration_sec": 0, "title": "string" } ] }
```

#### `suno.download`
```json
// input  { "clip_id": "string", "dest_dir": "runs/{id}/suno" }
// output { "ok": true, "audio_path": "runs/{id}/suno/clip.mp3" }
```

#### `suno.extract_stems`
```json
// input  { "clip_id": "string", "dest_dir": "runs/{id}/stems" }
// output { "ok": true,
//          "vocal_path": "runs/{id}/stems/guide_vocal.wav",
//          "instrumental_path": "runs/{id}/stems/instrumental.wav",
//          "extra_stems": { "drums": "...", "bass": "..." } }
```
> Prefer Suno's own stems. If the gateway lacks stem support, fall back to
> `stem-mcp.isolate` on the downloaded clip.

---

## 2. rvc-mcp  (Voice conversion + training — CLOUD, no local GPU)

Wraps a cloud voice provider (`VOICE_PROVIDER`):
- **replicate** (default): `replicate/train-rvc-model` (train) +
  `zsxkib/realistic-voice-cloning` (infer). Serverless GPU, pay-per-run. Most reliable.
- **colab_tunnel** / **kaggle_tunnel** (FREE GPU): an RVC server runs inside a
  Google Colab (T4) or Kaggle (~30 GPU hrs/week) notebook and is exposed as an
  HTTP API via a tunnel (`RVC_TUNNEL_URL`). See `notebooks/README.md`. Free but
  session-bound (URL rotates, may idle out) — best for hands-on/low-cost runs.
- **kits**: Kits.AI API.

The `rvc-mcp` tool contract is identical across backends; only the transport
differs. Trained-model **references/metadata** are stored in `RVC_MODELS_DIR`
(small JSON, not GPU weights).

### Tools

#### `rvc.list_models`
```json
// output { "ok": true, "models": [ { "name": "shyam_voice_v1",
//          "provider": "replicate", "model_ref": "...", "sr": 48000 } ] }
```

#### `rvc.convert`
```json
// input
{ "input_path": "runs/{id}/stems/guide_vocal.wav",
  "model_name": "shyam_voice_v1",
  "pitch_shift_semitones": 0, "index_ratio": 0.75, "f0_method": "rmvpe",
  "protect_voiceless": 0.33, "resample_sr": 48000,
  "dest_path": "runs/{id}/voice/my_voice.wav" }
// output { "ok": true, "output_path": "runs/{id}/voice/my_voice.wav" }
```
> Implementation: upload `input_path` to the provider, run inference with the
> trained model ref, download result to `dest_path`.

#### `rvc.train`
```json
// input
{ "dataset_url_or_zip": "models/datasets/shyam.zip",  // clean isolated vocals
  "model_name": "shyam_voice_v1", "sample_rate": 48000, "version": "v2",
  "epochs": 200, "f0_method": "rmvpe_gpu", "batch_size": 7 }
// output (long) { "ok": true, "task_id": "string" }
```

#### `rvc.get_train_task`
```json
// input  { "task_id": "string" }
// output { "ok": true, "status": "running|complete|failed",
//          "model_ref": "...", "metrics": {...} }
```

#### `rvc.detect_range`  (helper for voice-range auto-detect)
```json
// input  { "vocals_dir": "models/datasets/shyam/" }
// output { "ok": true, "low_note": "A2", "high_note": "E4",
//          "median_note": "C3" }
```

---

## 3. stem-mcp  (Stem separation — only for voice-training prep)

> **In the production pipeline, stems come from Suno itself** (`suno.extract_stems`)
> — no separate tool or cost. This `stem-mcp` server is needed ONLY for the
> **one-time** job of extracting the artist's vocals from their EXISTING
> (non-Suno) YouTube songs to build the RVC training dataset, and as a rare
> fallback to clean a Suno guide vocal if Suno stems are unavailable.

Wraps a stem provider (`STEM_PROVIDER`): a FREE **colab_tunnel** / **kaggle_tunnel**
notebook backend (recommended, see `notebooks/README.md`), or paid **lalal**
(LALAL.AI) / **replicate** (Demucs).

### Tools

#### `stem.isolate`
```json
// input  { "input_path": "path/to/song.wav", "dest_dir": "runs/{id}/stems",
//          "target": "both" }   // vocals | instrumental | both
// output { "ok": true,
//          "vocals_path": "runs/{id}/stems/cleaned_vocal.wav",
//          "instrumental_path": "runs/{id}/stems/instrumental.wav" }
```

#### `stem.batch_isolate`
```json
// input  { "input_dir": "downloads/", "dest_dir": "models/datasets/shyam/",
//          "target": "vocals" }
// output { "ok": true, "count": 12, "outputs": ["...", "..."] }
```

---

## 4. audio-mcp  (Analysis, mixing, mastering — CPU; mastering via LANDR API)

Wraps librosa, pydub, ffmpeg, pyloudnorm (CPU). Mastering uses the
`MASTERING_PROVIDER`: **landr** (LANDR API, default/primary) or **matchering**
(free OSS fallback). ASR uses a cloud provider (`ASR_PROVIDER`).

### Tools

#### `audio.align`
```json
// input  { "vocal_path":"...", "instrumental_path":"...", "dest_path":"..." }
// output { "ok": true, "offset_ms": 0, "aligned_vocal_path": "..." }
```

#### `audio.vocal_chain`
```json
// input  { "vocal_path":"...", "dest_path":"...", "low_cut_hz":100,
//          "presence_db":3.0, "comp_ratio":3.0, "deess":true,
//          "reverb_preset":"temple_hall", "reverb_predelay_ms":30 }
// output { "ok": true, "output_path":"..." }
```

#### `audio.mix`
```json
// input  { "vocal_path":"...", "instrumental_path":"...", "vocal_gain_db":0.0,
//          "dest_path":"runs/{id}/mix/premaster.wav" }
// output { "ok": true, "output_path":"..." }
```

#### `audio.master`
```json
// input  { "input_path":"runs/{id}/mix/premaster.wav",
//          "dest_path":"runs/{id}/master.wav",
//          "target_lufs": -14.0, "true_peak_dbtp": -1.0,
//          "provider": "landr", "intensity": "medium",
//          "reference_track": null }
// output { "ok": true, "output_path":"...", "lufs": -14.1, "true_peak": -1.2,
//          "provider_used": "landr" }
```
> If `provider=landr` and `LANDR_API_KEY` set → upload premaster, request master
> at intensity, download. Else use matchering (reference if provided) +
> pyloudnorm normalize + true-peak limit.

#### `audio.analyze`
```json
// input  { "input_path":"runs/{id}/master.wav",
//          "reference_voice_embedding":"path|null",
//          "vocal_only_path":"runs/{id}/voice/my_voice.wav|null" }
// output { "ok": true, "lufs": -14.1, "true_peak_dbtp": -1.2,
//          "voice_similarity": 0.97, "artifact_score": 0.08,
//          "pitch_stability": 0.94, "vocal_instr_balance_db": 2.1,
//          "max_silence_gap_sec": 0.4 }
```

#### `audio.transcribe`  (cloud ASR)
```json
// input  { "input_path":"...", "language":"hi" }
// output { "ok": true, "text":"...",
//          "words":[{"w":"...","start":0,"end":0}] }
```

---

## 5. External APIs (called via the MCP servers above)
- **Replicate** — cloud RVC train/infer (no local GPU). Used by `rvc-mcp`.
- **LALAL.AI** — cloud stem separation. Used by `stem-mcp`.
- **LANDR Mastering API** — cloud label-grade mastering. Used by `audio-mcp`.
- **Cloud ASR** — pronunciation check. Used by `audio-mcp.transcribe`.
- **Suno-compatible gateway** — music. Used by `suno-mcp`.
- **YouTube Data API** — OPTIONAL and OFF by default (`PUBLISH_TARGET=local`).

---

## 6. Browser-Agent (Browser Use) — optional UI-only fallback
- `browser.suno_generate(prompt, lyrics)` — only if `SUNO_USE_BROWSER=true`.
- `browser.ace_synthesize(midi, lyrics, voice)` — only if `ACE_ENABLED=true`.
- Runs in an **isolated profile** holding only music-tool logins (R7.2).

---

## 7. MCP Registration (see `mcp.json`)
```json
{
  "mcpServers": {
    "suno":  { "command": "python", "args": ["-m","bhajanforge.mcp_servers.suno_mcp"] },
    "rvc":   { "command": "python", "args": ["-m","bhajanforge.mcp_servers.rvc_mcp"] },
    "stem":  { "command": "python", "args": ["-m","bhajanforge.mcp_servers.stem_mcp"] },
    "audio": { "command": "python", "args": ["-m","bhajanforge.mcp_servers.audio_mcp"] }
  }
}
```
