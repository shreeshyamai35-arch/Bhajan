"""Time a full-length voice conversion of the current run's guide vocal."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

sys.path.insert(0, str(ROOT / "src"))
from bhajanforge.mcp_servers.rvc_mcp.providers import get_provider  # noqa: E402

inp = ROOT / "runs" / "2026-06-24_tere-charno-mein-khatu-shyam-cloned-voice" / "stems" / "guide_vocal.wav"
out = ROOT / "_voice_full_test.wav"

try:
    import soundfile as sf
    info = sf.info(str(inp))
    print(f"input duration: {info.frames/info.samplerate:.1f}s")
except Exception as e:  # noqa: BLE001
    print("duration check failed:", e)

prov = get_provider()
print("provider:", prov.name, "| timeout:", os.getenv("RVC_TUNNEL_TIMEOUT", "1800"))
t0 = time.time()
try:
    prov.convert(input_path=inp, dest_path=out, model_name="shyam_voice_v1",
                 pitch_shift_semitones=0)
    dt = time.time() - t0
    ok = out.exists() and out.stat().st_size > 1000
    print(f"DONE in {dt:.0f}s | output ok: {ok} | "
          f"size_kb: {round(out.stat().st_size/1024,1) if out.exists() else 0}")
except Exception as e:  # noqa: BLE001
    print(f"FAILED after {time.time()-t0:.0f}s: {repr(e)}")
