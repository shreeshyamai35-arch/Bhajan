# BhajanForge Chrome Extension

A browser popup that drives the BhajanForge HTTP API: fill in a theme/mood (or
paste your own lyrics), hit **Produce bhajan**, and watch the pipeline run. It
also has a one-click **Open Voice Trainer (Colab)** button.

## Install (unpacked — no store needed)
1. Start the API on your PC:
   ```powershell
   $env:PYTHONPATH="src"; $env:BHAJANFORGE_MOCK="0"; $env:QDRANT_PATH="./qdrant_data"
   uvicorn bhajanforge.api:api --host 127.0.0.1 --port 8000
   ```
2. Open Chrome → `chrome://extensions`.
3. Toggle **Developer mode** (top-right) ON.
4. Click **Load unpacked** → select this `chrome_extension` folder.
5. Pin the extension and click its icon. The status dot turns **green** when it
   reaches the API.

## Use
- **Produce bhajan** → `POST /produce`, shows score + a link to the run manifest.
- **Settings** (gear) → change the API base URL or the Colab notebook URL.
- **Open Voice Trainer (Colab)** → opens the training notebook in Colab.

## How the Colab button works
Clicking **Get Voice Trainer + open Colab** does two things:
1. Downloads `voice_clone_colab.ipynb` from your API (`GET /notebook`) into your
   Downloads folder.
2. Opens `colab.research.google.com`.

In the Colab dialog that appears, choose the **Upload** tab and pick the
`voice_clone_colab.ipynb` you just downloaded. Then **Runtime → Change runtime
type → T4 GPU → Save** and run the cells. No GitHub or Google Drive needed.

## Notes
- The API enables permissive CORS (local single-user service), so the popup can
  call `http://localhost:8000` directly.
- Producing in real (non-mock) mode can take a while — the popup stays open and
  shows the result when the pipeline finishes.
