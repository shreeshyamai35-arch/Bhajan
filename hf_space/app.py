"""BhajanForge voice inference Space (RVC over HTTP).

Serves the exact contract BhajanForge's `colab_tunnel` provider expects:
    GET  /health   -> {"ok": true, "model": <name>, "model_loaded": bool}
    POST /convert  -> multipart {audio, model_name, pitch_shift_semitones,
                                 index_ratio, f0_method, protect_voiceless,
                                 resample_sr} -> audio/wav

If no model is uploaded yet (models/ empty), it runs in PASSTHROUGH mode so the
pipeline never hard-fails: /convert returns the input audio unchanged.
"""

from __future__ import annotations

import glob
import os
import shutil
import sys
import tempfile
import traceback

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RVC_DIR = os.path.join(APP_DIR, "rvc")
MODELS_DIR = os.path.join(APP_DIR, "models")
WEIGHTS_DIR = os.path.join(RVC_DIR, "assets", "weights")
RMVPE_DIR = os.path.join(RVC_DIR, "assets", "rmvpe")
HUBERT_DIR = os.path.join(RVC_DIR, "assets", "hubert")

app = FastAPI(title="BhajanForge Voice (RVC)")

_vc = None          # RVC VC instance (None => passthrough)
_model_name = ""    # basename of the loaded .pth
_index_path = ""    # path to the faiss .index
_load_error = ""    # last load error, surfaced via /health


def _find(pattern: str) -> str:
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else ""


def _load_model() -> None:
    """Load the uploaded RVC model into an RVC VC instance (best-effort)."""
    global _vc, _model_name, _index_path, _load_error
    try:
        pth = _find(os.path.join(MODELS_DIR, "*.pth"))
        if not pth:
            _load_error = "no .pth in models/ (passthrough mode)"
            return

        os.makedirs(WEIGHTS_DIR, exist_ok=True)
        target = os.path.join(WEIGHTS_DIR, os.path.basename(pth))
        if not os.path.exists(target):
            shutil.copyfile(pth, target)
        _model_name = os.path.basename(pth)
        _index_path = _find(os.path.join(MODELS_DIR, "*.index"))

        # RVC code uses relative asset paths, so import from inside its dir.
        os.chdir(RVC_DIR)
        if RVC_DIR not in sys.path:
            sys.path.insert(0, RVC_DIR)

        # RVC resolves model/index/pitch assets through these env vars
        # (configs.config + infer.modules.vc.*). Without them get_vc loads
        # "None/<model>.pth", get_index_path_from_model does os.walk(None),
        # and the rmvpe pipeline raises KeyError on os.environ["rmvpe_root"].
        os.environ["weight_root"] = WEIGHTS_DIR
        os.environ["index_root"] = MODELS_DIR
        os.environ["rmvpe_root"] = RMVPE_DIR
        os.environ.setdefault("hubert_path", os.path.join(HUBERT_DIR, "hubert_base.pt"))

        # configs.config.Config() runs argparse on sys.argv. Under uvicorn
        # sys.argv is ["...", "app:app", "--host", "0.0.0.0", "--port", "7860"],
        # which argparse rejects with SystemExit (NOT caught by Exception) and
        # kills startup. Neutralise argv so Config() falls back to its defaults.
        _saved_argv = sys.argv
        sys.argv = [sys.argv[0]]
        try:
            from configs.config import Config  # type: ignore
            from infer.modules.vc.modules import VC  # type: ignore

            config = Config()
        finally:
            sys.argv = _saved_argv

        vc = VC(config)
        vc.get_vc(_model_name)
        _vc = vc
        _load_error = ""
        print(f"[voice] loaded model={_model_name} index={_index_path or '(none)'}")
    except Exception as exc:  # noqa: BLE001
        _vc = None
        _load_error = f"{type(exc).__name__}: {exc}"
        print("[voice] model load failed -> passthrough:\n" + traceback.format_exc())


@app.on_event("startup")
def _startup() -> None:
    _load_model()


@app.get("/")
def root() -> JSONResponse:
    return JSONResponse({
        "service": "BhajanForge Voice (RVC)",
        "model_loaded": _vc is not None,
        "model": _model_name,
        "hint": "POST /convert with an 'audio' file. See /health.",
    })


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "model": _model_name or "passthrough",
        "model_loaded": _vc is not None,
        "load_error": _load_error,
    })


@app.post("/convert")
async def convert(
    audio: UploadFile = File(...),
    model_name: str = Form(""),
    pitch_shift_semitones: int = Form(0),
    index_ratio: float = Form(0.75),
    f0_method: str = Form("rmvpe"),
    protect_voiceless: float = Form(0.33),
    resample_sr: int = Form(0),
):
    raw = await audio.read()
    src = tempfile.mktemp(suffix=".wav")
    with open(src, "wb") as fh:
        fh.write(raw)

    # Passthrough when no model is loaded.
    if _vc is None:
        return FileResponse(src, media_type="audio/wav", filename="passthrough.wav")

    import soundfile as sf  # noqa: WPS433

    info, (sr, wav) = _vc.vc_single(
        0, src, int(pitch_shift_semitones), None, f0_method,
        _index_path, _index_path, float(index_ratio), 3,
        int(resample_sr), 0.25, float(protect_voiceless),
    )
    # vc_single returns (info, (None, None)) on internal failure. Surface that
    # as a 500 instead of crashing on sf.write(out, None, None).
    if wav is None:
        return JSONResponse(status_code=500, content={"error": "conversion failed", "detail": info})
    out = tempfile.mktemp(suffix=".wav")
    sf.write(out, wav, sr)
    return FileResponse(out, media_type="audio/wav", filename="my_voice.wav")
