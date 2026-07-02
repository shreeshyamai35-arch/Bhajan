"""Quick end-to-end test of the Replicate voice-conversion path."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# load .env into the environment
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()
os.environ["BHAJANFORGE_MOCK"] = "0"

sys.path.insert(0, str(ROOT / "src"))
from bhajanforge.mcp_servers.rvc_mcp.providers import get_provider  # noqa: E402

prov = get_provider()
print("provider:", prov.name)

inp = ROOT / "runs" / "2026-06-23_morning-darshan-of-khatu-shyam" / "stems" / "guide_vocal.wav"
if not inp.exists():
    # fall back to any guide vocal we can find
    hits = list(ROOT.glob("runs/**/guide_vocal.wav"))
    inp = hits[0] if hits else inp
print("input:", inp, "exists:", inp.exists())

out = ROOT / "_voice_test_out.wav"
print("calling Replicate convert (zsxkib/realistic-voice-cloning + custom model)…")
prov.convert(input_path=inp, dest_path=out, model_name="shyam_voice_v1",
             pitch_shift_semitones=0)
print("OUTPUT:", out, "exists:", out.exists(),
      "size_kb:", round(out.stat().st_size / 1024, 1) if out.exists() else 0)
print("VOICE CONVERSION OK" if out.exists() and out.stat().st_size > 1000 else "FAILED")
