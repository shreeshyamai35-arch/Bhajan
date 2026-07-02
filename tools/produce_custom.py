"""Run a full BhajanForge produce with user-supplied lyrics, in the cloned
voice (via whatever VOICE_PROVIDER is configured in .env)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# load .env
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

sys.path.insert(0, str(ROOT / "src"))

# Reuse the Suno clip already generated for this run (avoids re-billing Suno);
# composer's bring-your-own-clip path picks it up.
_existing = (ROOT / "runs" / "2026-06-24_tere-charno-mein-khatu-shyam-cloned-voice"
             / "suno" / "clip.mp3")
if _existing.exists():
    os.environ.setdefault("SUNO_CLIP_PATH", str(_existing))
    print("reusing existing Suno clip:", _existing)

from bhajanforge.models import Mood, ProductionRequest  # noqa: E402
from bhajanforge.graph import run_pipeline  # noqa: E402

lyrics = (ROOT / "_custom_lyrics.txt").read_text(encoding="utf-8").strip()

req = ProductionRequest(
    theme="tere charno mein - Khatu Shyam (cloned voice)",
    mood=Mood.slow_emotional,
    deity="Khatu Shyam",
    taal="keherwa",
    tempo=72,
    language="hi",
    duration_target_sec=240,
    candidates=1,            # keep Suno usage minimal
    lyrics_override=lyrics,
)

print("provider (voice):", os.getenv("VOICE_PROVIDER"))
print("starting full produce with custom lyrics…", flush=True)
result = run_pipeline(req)
print("\n=== RESULT ===")
for k, v in result.items():
    print(f"{k}: {v}")
