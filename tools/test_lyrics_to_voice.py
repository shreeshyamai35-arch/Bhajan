"""FEATURE TEST: lyrics + cloned voice -> recited vocals (NO Suno).

1. Synthesize the lyrics as Hindi speech with free edge-tts.
2. Send that speech to the RVC HF Space -> converted to YOUR cloned voice.
Result = your voice reciting the bhajan lyrics (spoken, not sung).
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

VOICE = "hi-IN-MadhurNeural"          # free Hindi male neural voice
TUNNEL = os.environ["RVC_TUNNEL_URL"].rstrip("/")
OUT = ROOT / "output" / "voice_test_recite"
OUT.mkdir(parents=True, exist_ok=True)

# --- 1. take the opening lines, strip repeat markers (-2, ..1 etc.) ---
raw = (ROOT / "_custom_lyrics.txt").read_text(encoding="utf-8").strip().splitlines()
lines = [l for l in raw if l.strip()][:4]
text = " ".join(lines)
text = re.sub(r"-?\d+", "", text)
text = text.replace("..", " ").replace("।", "। ").strip()
print("TTS text:", text)

mp3 = OUT / "tts_source.mp3"


async def _tts() -> None:
    import edge_tts
    await edge_tts.Communicate(text, VOICE).save(str(mp3))


asyncio.run(_tts())
print("TTS speech saved:", mp3, mp3.stat().st_size, "bytes")

# --- 2. convert that speech to the cloned voice via the HF Space ---
import httpx

out = OUT / "lyrics_in_my_voice.wav"
print("converting to cloned voice via HF Space (CPU, ~1-2 min)…")
with httpx.Client(timeout=600.0) as c:
    with open(mp3, "rb") as fh:
        r = c.post(f"{TUNNEL}/convert",
                   files={"audio": ("source.mp3", fh, "audio/mpeg")},
                   data={"model_name": "shyam_voice_v1",
                         "pitch_shift_semitones": "0",
                         "index_ratio": "0.75",
                         "f0_method": "rmvpe",
                         "protect_voiceless": "0.33",
                         "resample_sr": "0"})
    if r.status_code >= 400:
        print("CONVERT FAILED", r.status_code, r.text[:300])
        sys.exit(1)
    out.write_bytes(r.content)

ok = out.exists() and out.stat().st_size > 2000
print("DONE:", out, "| ok:", ok, "| size_kb:",
      round(out.stat().st_size / 1024, 1) if out.exists() else 0)
print("\nListen to:", out)
print("(spoken recitation in your cloned voice — singing needs a melody source)")
