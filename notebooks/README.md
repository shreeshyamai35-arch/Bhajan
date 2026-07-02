# Free Voice Cloning (Google Colab) — BhajanForge

Train an **RVC** model of **your own voice** on a free Colab T4 GPU, then serve it
over a public tunnel that BhajanForge calls. **No payment, no local GPU.**

## Files
- `voice_clone_colab.ipynb` — the notebook (train + serve).

## Quick start
1. Open Google Colab → **File → Upload notebook** → pick `voice_clone_colab.ipynb`
   (or push this repo to GitHub and open it from there).
2. **Runtime → Change runtime type → T4 GPU → Save.**
3. Run cells top to bottom:
   - **Step 1–1b**: installs tools + downloads RVC pretrained assets.
   - **Step 2**: paste links to *your own* bhajan songs (or upload audio to `/content/raw`).
   - **Step 3**: isolates clean vocals (Demucs).
   - **Step 4**: trains your voice model (`MODEL_NAME`, ~20–40 min for 200 epochs).
   - **Step 5**: starts the API + tunnel and prints `RVC_TUNNEL_URL`.
4. On your PC, edit BhajanForge `.env`:
   ```
   VOICE_PROVIDER=colab_tunnel
   RVC_TUNNEL_URL=https://<printed-url>
   ```
   Set the model name in `config/learning.yaml`:
   ```yaml
   voice_profile:
     active_rvc_model: shyam_voice_v1
   ```
5. Run a `produce` (CLI or the web UI). Each guide vocal is POSTed to the tunnel's
   `/convert` and returned in **your** cloned voice.
6. **Keep the Colab tab open** while producing. Close it when done.

## The API contract (already matched by BhajanForge's `colab_tunnel` provider)
- `GET /health` → `{"ok": true, "model": "<name>"}`
- `POST /convert` (multipart):
  - file field **`audio`** (the guide vocal .wav)
  - form fields: `model_name`, `pitch_shift_semitones`, `index_ratio`,
    `f0_method`, `protect_voiceless`, `resample_sr`
  - returns `audio/wav` bytes (the converted vocal)

## Tunnel options
- **ngrok** (used in the notebook): free, needs a one-time free authtoken from
  https://dashboard.ngrok.com/get-started/your-authtoken — paste it in Step 5.
- **cloudflared** (no signup) alternative — replace the ngrok block in Step 5 with:
  ```python
  !wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/bin/cloudflared && chmod +x /usr/bin/cloudflared
  import subprocess, re, time
  p = subprocess.Popen(['cloudflared','tunnel','--url','http://localhost:7865'],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
  for line in p.stdout:
      print(line, end='')
      m = re.search(r'https://[-a-z0-9]+\.trycloudflare\.com', line)
      if m:
          print('\nRVC_TUNNEL_URL =', m.group(0)); break
  ```

## Notes / troubleshooting
- Free Colab/Kaggle sessions are **session-bound**: the tunnel URL changes each run
  and the GPU idles out — fine for hands-on production, not for always-on use.
- 5–15 songs of **clear solo singing** give the best clone. More clean data = better.
- RVC Colab tooling drifts over time; if a training cell errors on a renamed script,
  it's usually a one-line path fix in the RVC repo. Tell BhajanForge which cell/error
  and it can patch the command.
- For a paid, always-on alternative, set `VOICE_PROVIDER=replicate` + `REPLICATE_API_TOKEN`
  instead — same BhajanForge interface.
