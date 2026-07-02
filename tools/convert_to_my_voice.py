"""Convert ANY input vocal audio into the cloned voice (RVC step 3, isolated).

Usage:
  python tools/convert_to_my_voice.py "<path-to-audio>" [pitch_semitones]

- Sends the file straight to the HF Space /convert (it has ffmpeg, so mp3/wav/
  m4a all work).
- pitch_semitones: 0 = same pitch (use if source singer is also male);
  -12 if a female source should map down to a male voice, +12 the other way.
"""
from __future__ import annotations

import os
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

if len(sys.argv) < 2:
    sys.exit("usage: convert_to_my_voice.py <audio-file> [pitch_semitones]")

inp = Path(sys.argv[1].strip('"'))
if not inp.exists():
    sys.exit(f"file not found: {inp}")
pitch = sys.argv[2] if len(sys.argv) > 2 else "0"
# tunable for clarity vs timbre: higher protect = clearer consonants;
# lower index_ratio = clearer original pronunciation (slightly less timbre).
index_ratio = os.getenv("RVC_INDEX_RATIO", "0.40")
protect = os.getenv("RVC_PROTECT", "0.50")

tunnel = os.environ["RVC_TUNNEL_URL"].rstrip("/")
out_dir = ROOT / "output" / "voice_convert_test"
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / (inp.stem + f"_my_voice_idx{index_ratio}_prot{protect}.wav")

import httpx

print(f"input: {inp.name} | pitch: {pitch} | index_ratio: {index_ratio} | protect: {protect}")
print("converting via HF Space (free CPU)…")
with httpx.Client(timeout=900.0) as c:
    with open(inp, "rb") as fh:
        r = c.post(f"{tunnel}/convert",
                   files={"audio": (inp.name, fh, "application/octet-stream")},
                   data={"model_name": "shyam_voice_v1",
                         "pitch_shift_semitones": str(pitch),
                         "index_ratio": str(index_ratio),
                         "f0_method": "rmvpe",
                         "protect_voiceless": str(protect),
                         "resample_sr": "0"})
if r.status_code >= 400:
    sys.exit(f"convert failed {r.status_code}: {r.text[:300]}")
out.write_bytes(r.content)
ok = out.exists() and out.stat().st_size > 2000
print(f"DONE: {out}")
print(f"ok: {ok} | size_kb: {round(out.stat().st_size/1024,1)}")
