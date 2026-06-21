# BhajanForge — Free GPU Backends (Google Colab / Kaggle)

Optional **$0 GPU** backend for the heavy voice/stem tasks, as an alternative to
paid Replicate. Verified feasible: Colab's free tier gives **NVIDIA T4** GPUs in a
zero-config notebook; Kaggle gives **~30 GPU hours/week** (P100/T4). RVC and
UVR/Demucs both run well on these.

> **Honest trade-off:** Colab/Kaggle are *interactive* notebooks, not always-on
> servers. The tunnel URL changes each session, sessions idle-out (Colab ~90 min
> idle / ~12 h max; Kaggle ~9 h/session, weekly quota), and free GPUs aren't
> guaranteed. Great for low cost and hands-on batches; use **Replicate** for
> unattended/automated reliability. Both plug into the SAME `rvc-mcp` / `stem-mcp`
> interface, so you can switch by changing `VOICE_PROVIDER` / `STEM_PROVIDER`.

## How it works
```
Colab/Kaggle notebook (free GPU)
   ├─ runs an RVC + UVR/Demucs HTTP server (FastAPI or Gradio)
   └─ exposes it via a tunnel (cloudflared / ngrok) -> public https URL
            │
            ▼
   set RVC_TUNNEL_URL / STEM_TUNNEL_URL in .env
            │
            ▼
   rvc-mcp / stem-mcp call that URL instead of Replicate
```

## Setup (what Codex should ship)
1. `notebooks/bhajanforge_gpu_server.ipynb` — a notebook that:
   - installs RVC + `audio-separator`/Demucs + the server deps,
   - exposes endpoints matching the MCP tool contracts in
     `docs/MCP_SERVERS.md`:
     - `POST /rvc/train`, `GET /rvc/train/{task_id}`, `POST /rvc/convert`,
       `POST /rvc/detect_range`
     - `POST /stem/isolate`, `POST /stem/batch_isolate`
   - protects them with a shared secret header (`RVC_TUNNEL_TOKEN` /
     `STEM_TUNNEL_TOKEN`),
   - starts a tunnel and prints the public URL to paste into `.env`.
2. Works on **both** Colab and Kaggle (same notebook; detect environment).
3. Persist trained RVC models to Google Drive (Colab) or Kaggle datasets so they
   survive session restarts; `rvc-mcp` stores only the model reference.

## When to use which backend
| Need | Use |
|------|-----|
| Hands-free / scheduled production | `replicate` (paid, reliable) |
| Lowest cost, you're around to babysit | `colab_tunnel` (free T4) |
| Bulk training jobs within weekly quota | `kaggle_tunnel` (free, ~30h/wk) |

## Security
- Keep the tunnel token secret; never expose the notebook server without it.
- Only the artist's own audio is sent (rules R2.1/R2.2).
