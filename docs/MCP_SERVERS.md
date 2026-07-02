# BhajanForge — MCP Servers & Tool Contracts

All external capabilities are exposed as **MCP tools** so any agent can call them
uniformly. Build each server with the **MCP Python SDK**.

> **No local GPU.** Every heavy audio-AI task runs via a **cloud API**. The MCP
> servers are thin wrappers around those APIs.
>
> Convention: every tool returns `{ "ok": bool, "error": str|null, ...payload }`.
> Long operations return a `task_id`; clients poll a `get_*` tool.

---

## 1. suno-mcp  (Music generation — PRIMARY, API-FIRST)

Wraps a configured Suno-compatible third-party gateway (`SUNO_API_BASE`/
`SUNO_API_KEY`). Browser-agent fallback OFF unless `SUNO_USE_BROWSER=true`.

### `suno.generate`
```json
// input
{ "lyrics": "string", "style_prompt": "string", "model": "suno-v5.5",
  "make_instrumental": false, "candidates": 2, "duration_hint_sec": 240 }
// output
{ "ok": true, "task_id": "string", "candidates": 2 }
```

### `suno.get_task`
```json
// input  { "task_id": "string" }
// output { "ok": true, "status": "queued|running|complete|failed",
//          "clips": [ { "clip_id": "string", "audio_url": "string",
//                       "duration_sec": 0, "title": "string" } ] }
```

### `suno.download`
```json
// input  { "clip_id": "string", "dest_dir": "runs/{id}/suno" }
// output { "ok": true, "audio_path": "runs/{id}/suno/clip.mp3" }
```

### `suno.extract_stems`
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

Wraps `VOICE_PROVIDER`: **replicate** (default), **colab_tunnel**/**kaggle_tunnel**
(free GPU via `RVC_TUNNEL_URL`), **kits**. Identical tool contract across
backends. Trained-model references/metadata stored in `RVC_MODELS_DIR` (small
JSON, not GPU weights).

### `rvc.list_models`
```json
// output { "ok": true, "models": [ { "name": "shyam_voice_v1",
//          "provider": "replicate", "model_ref": "...", "sr": 48000 } ] }
```

### `rvc.convert`
```json
// input
{ "input_path": "runs/{id}/stems/guide_vocal.wav",
  "model_name": "shyam_voice_v1",
  "pitch_shift_semitones": 0, "index_ratio": 0.75, "f0_method": "rmvpe",
  "protect_voiceless": 0.33, "resample_sr": 48000,
  "dest_path": "runs/{id}/voice/my_voice.wav" }
// output { "ok": true, "output_path": "runs/{id}/voice/my_voice.wav" }
```

### `rvc.train`
```json
// input
{ "dataset_url_or_zip": "models/datasets/shyam.zip",
  "model_name": "shyam_voice_v1", "sample_rate": 48000, "version": "v2",
  "epochs": 200, "f0_method": "rmvpe_gpu", "batch_size": 7 }
// output (long) { "ok": true, "task_id": "string" }
```

### `rvc.get_train_task`
```json
// input  { "task_id": "string" }
// output { "ok": true, "status": "running|complete|failed",
//          "model_ref": "...", "metrics": {...} }
```

### `rvc.detect_range`
```json
// input  { "vocals_dir": "models/datasets/shyam/" }
// output { "ok": true, "low_note": "A2", "high_note": "E4", "median_note": "C3" }
```

---

## 3. stem-mcp  (Stem separation — CLOUD, no local GPU)

Wraps `STEM_PROVIDER`: **lalal** (default), **replicate** (Demucs), or
**colab_tunnel**/**kaggle_tunnel** (`STEM_TUNNEL_URL`).

### `stem.isolate`
```json
// input  { "input_path": "path/to/song.wav", "dest_dir": "runs/{id}/stems",
//          "target": "both" }   // vocals | instrumental | both
// output { "ok": true,
//          "vocals_path": "runs/{id}/stems/cleaned_vocal.wav",
//          "instrumental_path": "runs/{id}/stems/instrumental.wav" }
```

### `stem.batch_isolate`
```json
// input  { "input_dir": "downloads/", "dest_dir": "models/datasets/shyam/",
//          "target": "vocals" }
// output { "ok": true, "count": 12, "outputs": ["...", "..."] }
```

---

## 4. audio-mcp  (Analysis, mixing, mastering — CPU; mastering via LANDR API)

Wraps librosa, pydub, ffmpeg, pyloudnorm (CPU). Mastering uses
`MASTERING_PROVIDER`: **landr** (default) or **matchering** (free fallback).
ASR uses `ASR_PROVIDER`.

### `audio.align`
```json
// input  { "vocal_path":"...", "instrumental_path":"...", "dest_path":"..." }
// output { "ok": true, "offset_ms": 0, "aligned_vocal_path": "..." }
```

### `audio.vocal_chain`
```json
// input  { "vocal_path":"...", "dest_path":"...", "low_cut_hz":100,
//          "presence_db":3.0, "comp_ratio":3.0, "deess":true,
//          "reverb_preset":"temple_hall", "reverb_predelay_ms":30 }
// output { "ok": true, "output_path":"..." }
```

### `audio.mix`
```json
// input  { "vocal_path":"...", "instrumental_path":"...", "vocal_gain_db":0.0,
//          "dest_path":"runs/{id}/mix/premaster.wav" }
// output { "ok": true, "output_path":"..." }
```

### `audio.master`
```json
// input  { "input_path":"runs/{id}/mix/premaster.wav",
//          "dest_path":"runs/{id}/master.wav",
//          "target_lufs": -14.0, "true_peak_dbtp": -1.0,
//          "provider": "landr", "intensity": "medium", "reference_track": null }
// output { "ok": true, "output_path":"...", "lufs": -14.1, "true_peak": -1.2,
//          "provider_used": "landr" }
```
> If `provider=landr` and `LANDR_API_KEY` set → upload premaster, request master,
> download. Else matchering (reference if provided) + pyloudnorm + true-peak limit.

### `audio.analyze`
```json
// input  { "input_path":"runs/{id}/master.wav",
//          "reference_voice_embedding":"path|null",
//          "vocal_only_path":"runs/{id}/voice/my_voice.wav|null" }
// output { "ok": true, "lufs": -14.1, "true_peak_dbtp": -1.2,
//          "voice_similarity": 0.97, "artifact_score": 0.08,
//          "pitch_stability": 0.94, "vocal_instr_balance_db": 2.1,
//          "max_silence_gap_sec": 0.4 }
```

### `audio.transcribe`  (cloud ASR)
```json
// input  { "input_path":"...", "language":"hi" }
// output { "ok": true, "text":"...", "words":[{"w":"...","start":0,"end":0}] }
```

---

## 5. MCP Registration (mcp.json)
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
