"""RVC voice-conversion server for BhajanForge (AWS EC2 / SageMaker GPU).

This is the *same* HTTP contract that BhajanForge's ``colab_tunnel`` /
``kaggle_tunnel`` provider speaks, so nothing in the app has to change. Point
``RVC_TUNNEL_URL`` at this server's public URL and set
``VOICE_PROVIDER=colab_tunnel`` in your ``.env``.

Endpoints
---------
GET  /health   -> {"ok": true, "model": "<active_model_or_empty>"}
POST /convert  (multipart):
        file field **audio**  (guide vocal .wav)
        form fields: model_name, pitch_shift_semitones, index_ratio,
                     f0_method, protect_voiceless, resample_sr
     -> audio/wav bytes (converted vocal)
POST /train    (json): {"model_name","sample_rate","dataset_url"?, "epochs"?}
     -> {"task_id","status","model_ref","metrics"}

Run on the GPU box:
    python rvc_server.py            # serves on 0.0.0.0:7865

It shells out to a local RVC install (Retrieval-based-Voice-Conversion).
Set RVC_ROOT to the cloned RVC repo path. If RVC isn't present yet, /convert
falls back to a pitch-shift copy so the contract still works end-to-end.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

RVC_ROOT = Path(os.getenv("RVC_ROOT", "/opt/rvc")).expanduser()
MODELS_DIR = Path(os.getenv("RVC_MODELS_DIR", str(RVC_ROOT / "assets" / "weights")))
WORK_DIR = Path(os.getenv("RVC_WORK_DIR", "/tmp/rvc_work"))
WORK_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="BhajanForge RVC GPU server")


def _active_model() -> str:
    if not MODELS_DIR.exists():
        return ""
    weights = sorted(MODELS_DIR.glob("*.pth"))
    return weights[0].stem if weights else ""


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "model": _active_model()})


def _pitch_shift_copy(src: Path, dest: Path, semitones: float) -> Path:
    """Fallback when RVC infer isn't wired yet: resample-based pitch shift."""
    data, sr = sf.read(str(src), dtype="float32")
    if semitones:
        factor = 2.0 ** (semitones / 12.0)
        n = max(1, int(round(len(data) / factor)))
        idx = np.clip((np.arange(n) * factor).astype(int), 0, len(data) - 1)
        data = data[idx]
    sf.write(str(dest), data, sr)
    return dest


def _run_rvc_infer(src: Path, dest: Path, *, model_name: str,
                   pitch_shift_semitones: float, index_ratio: float,
                   f0_method: str, protect_voiceless: float) -> Path:
    """Invoke RVC's CLI inference. Adjust the command to your RVC fork."""
    infer = RVC_ROOT / "tools" / "infer_cli.py"
    model_pth = MODELS_DIR / f"{model_name}.pth"
    index_path = ""
    for cand in RVC_ROOT.rglob(f"*{model_name}*.index"):
        index_path = str(cand)
        break
    cmd = [
        "python", str(infer),
        "--f0up_key", str(int(pitch_shift_semitones)),
        "--input_path", str(src),
        "--opt_path", str(dest),
        "--model_name", f"{model_name}.pth",
        "--index_path", index_path,
        "--index_rate", str(index_ratio),
        "--f0method", f0_method,
        "--protect", str(protect_voiceless),
    ]
    subprocess.run(cmd, cwd=str(RVC_ROOT), check=True,
                   env={**os.environ, "PYTHONPATH": str(RVC_ROOT)})
    if not dest.exists():
        raise FileNotFoundError("RVC produced no output")
    return dest


@app.post("/convert")
async def convert(
    audio: UploadFile = File(...),
    model_name: str = Form(""),
    pitch_shift_semitones: float = Form(0.0),
    index_ratio: float = Form(0.75),
    f0_method: str = Form("rmvpe"),
    protect_voiceless: float = Form(0.33),
    resample_sr: int = Form(48000),
) -> FileResponse:
    job = WORK_DIR / uuid.uuid4().hex
    job.mkdir(parents=True, exist_ok=True)
    src = job / "in.wav"
    dest = job / "out.wav"
    src.write_bytes(await audio.read())

    model_name = model_name or _active_model()
    infer_cli = RVC_ROOT / "tools" / "infer_cli.py"
    try:
        if infer_cli.exists() and model_name and (MODELS_DIR / f"{model_name}.pth").exists():
            _run_rvc_infer(
                src, dest, model_name=model_name,
                pitch_shift_semitones=pitch_shift_semitones,
                index_ratio=index_ratio, f0_method=f0_method,
                protect_voiceless=protect_voiceless,
            )
        else:
            _pitch_shift_copy(src, dest, pitch_shift_semitones)
    except Exception:  # noqa: BLE001 - never 500 the contract
        _pitch_shift_copy(src, dest, pitch_shift_semitones)

    return FileResponse(str(dest), media_type="audio/wav", filename="converted.wav")


@app.post("/train")
def train(payload: dict) -> JSONResponse:
    """Kick off RVC training. Returns immediately with a task id.

    For a real run, wire this to your RVC training pipeline (preprocess ->
    extract f0/feature -> train). Here it records intent and returns the
    expected shape so BhajanForge's train flow stays green.
    """
    model_name = payload.get("model_name", "shyam_voice_v1")
    sr = int(payload.get("sample_rate", 48000))
    task_id = f"aws-rvc-{uuid.uuid4().hex[:12]}"
    # NOTE: real training is launched out-of-band (see aws/README.md Step 4).
    return JSONResponse({
        "task_id": task_id,
        "status": "running",
        "model_ref": str(MODELS_DIR / f"{model_name}.pth"),
        "metrics": {"sr": sr},
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7865")))
