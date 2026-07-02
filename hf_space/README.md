---
title: BhajanForge Voice (RVC)
emoji: 🎤
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# BhajanForge Voice — RVC inference Space

Serves your trained **RVC** voice model over an HTTP API that BhajanForge calls.
This runs on a **free Hugging Face CPU Space** — which, unlike Colab's free tier,
is *allowed* to host a long-running web service. No tab to keep open.

## Why this exists
Colab's free tier disallows running a public server/tunnel, so it kept killing
the runtime. The split that works:
- **Train** your voice model on Colab (GPU, allowed) → download the model.
- **Serve** it here on Hugging Face Spaces (CPU, allowed, persistent).

## API contract (matches BhajanForge `colab_tunnel`)
- `GET /health` → `{"ok": true, "model": "<name>"}`
- `POST /convert` (multipart): file field **`audio`** + form fields
  `model_name, pitch_shift_semitones, index_ratio, f0_method,
  protect_voiceless, resample_sr` → returns `audio/wav`.

## Deploy (free, ~10 min)
1. Create a free account at https://huggingface.co.
2. **New → Space** → SDK = **Docker** → name it e.g. `bhajan-voice`.
3. Upload these files to the Space repo (drag-drop in the Space's *Files* tab):
   `Dockerfile`, `app.py`, `requirements.txt`, `README.md`.
4. Create a folder **`models/`** in the Space and upload your trained files from
   Colab: `your_voice.pth` (the weight) and `added_*.index` (the retrieval index).
5. The Space builds automatically. When it shows **Running**, your URL is:
   `https://<your-username>-bhajan-voice.hf.space`
6. On your PC, set in BhajanForge `.env`:
   ```
   VOICE_PROVIDER=colab_tunnel
   RVC_TUNNEL_URL=https://<your-username>-bhajan-voice.hf.space
   ```
   and `config/learning.yaml` → `voice_profile.active_rvc_model: <your_voice>`.
7. Run a produce. Each guide vocal is sent to `/convert` and returned in your voice.

## Notes
- Free CPU Spaces are slower than a GPU; converting a 3–4 min vocal may take a
  couple of minutes. That's fine for batch production.
- The RVC upstream repo occasionally renames modules. If the build or model load
  errors, tell BhajanForge the exact error and it will patch `app.py`/`Dockerfile`.
- Until a model is uploaded, `/health` reports `model_loaded: false` and `/convert`
  returns the input unchanged (passthrough) so the pipeline never hard-fails.
