"""Voice Agent (M6) — convert the guide vocal into the artist's cloned voice.

FR-10..FR-13 + FR-23 training entrypoint. Cloud RVC via rvc-mcp; optional
stem cleanup via stem-mcp. No local GPU. Applies the Learning File's best
settings, and any quality-loop fixes routed to the "voice" stage (R5.1/R5.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..logging_utils import get_logger
from ..mcp_servers.rvc_mcp import (
    rvc_convert,
    rvc_detect_range,
    rvc_get_train_task,
    rvc_train,
)
from ..mcp_servers.stem_mcp import stem_batch_isolate, stem_isolate
from ..models import VoiceResult, VoiceSettings

logger = get_logger("agent.voice")


def _best_settings(learning: dict) -> VoiceSettings:
    vp = (learning or {}).get("voice_profile", {}) or {}
    best = vp.get("best_settings", {}) or {}
    model = vp.get("active_rvc_model") or "shyam_voice_v1"
    return VoiceSettings(
        model_name=str(model),
        pitch_shift_semitones=int(best.get("pitch_shift_semitones", 0)),
        index_ratio=float(best.get("index_ratio", 0.75)),
        f0_method=str(best.get("f0_method", "rmvpe")),  # type: ignore[arg-type]
        protect_voiceless=float(best.get("protect_voiceless", 0.33)),
        resample_sr=int(best.get("resample_sr", 48000)),
    )


def _apply_fixes(settings: VoiceSettings, state: dict) -> VoiceSettings:
    """Apply quality-loop fixes routed to the voice stage (R5.3)."""
    quality = state.get("quality")
    fixes = getattr(quality, "fixes", []) if quality is not None else []
    for fix in fixes:
        if getattr(fix, "stage", None) != "voice":
            continue
        params = getattr(fix, "params", {}) or {}
        if "index_ratio" in params:
            settings.index_ratio = float(params["index_ratio"])
        if "f0_method" in params:
            settings.f0_method = params["f0_method"]
        if "pitch_shift_semitones" in params:
            settings.pitch_shift_semitones = int(params["pitch_shift_semitones"])
        logger.info("Applied voice fix: %s", getattr(fix, "action", ""))
    return settings


def convert_voice(state: dict) -> VoiceResult:
    from .. import runs

    run_id = state["run_id"]
    learning = state.get("learning", {})
    artifacts = state.get("artifacts", {})

    guide_vocal = artifacts.get("guide_vocal")
    if not guide_vocal or not Path(guide_vocal).exists():
        raise RuntimeError("no guide vocal available from composer")

    stems_dir = str(runs.run_dir(run_id) / "stems")
    # FR-11: clean residual instrumentation from the guide vocal.
    cleaned = stem_isolate(input_path=guide_vocal, dest_dir=stems_dir, target="vocals")
    clean_vocal = cleaned.get("vocals_path") if cleaned.get("ok") else guide_vocal

    settings = _apply_fixes(_best_settings(learning), state)
    dest = str(runs.run_dir(run_id) / "voice" / "my_voice.wav")
    conv = rvc_convert(
        input_path=clean_vocal,
        model_name=settings.model_name,
        pitch_shift_semitones=settings.pitch_shift_semitones,
        index_ratio=settings.index_ratio,
        f0_method=settings.f0_method,
        protect_voiceless=settings.protect_voiceless,
        resample_sr=settings.resample_sr,
        dest_path=dest,
    )
    if not conv.get("ok"):
        raise RuntimeError(f"rvc.convert failed: {conv.get('error')}")

    similarity = _quick_similarity(learning, conv["output_path"])
    return VoiceResult(output_path=conv["output_path"], settings_used=settings, voice_similarity=similarity)


def _quick_similarity(learning: dict, vocal_path: str) -> Optional[float]:
    """Cheap self-check similarity against the reference embedding, if any."""
    ref = ((learning or {}).get("voice_profile", {}) or {}).get("reference_embedding")
    try:
        from ..mcp_servers.audio_mcp import audio_analyze

        res = audio_analyze(input_path=vocal_path, reference_voice_embedding=ref, vocal_only_path=vocal_path)
        return res.get("voice_similarity") if res.get("ok") else None
    except Exception:
        return None


def voice_node(state: dict) -> dict:
    result = convert_voice(state)
    artifacts = dict(state.get("artifacts", {}))
    artifacts["my_voice"] = result.output_path
    logger.info("Voice conversion done (similarity=%s)", result.voice_similarity)
    return {"voice": result, "artifacts": artifacts}


# --------------------------------------------------------------------------
# Setup-time training entrypoint (FR-23 / AC-6)
# --------------------------------------------------------------------------


def _download_youtube(urls_file: str, dest_dir: str) -> list[str]:
    """Download the artist's bhajans via yt-dlp (guarded; best-effort)."""
    try:
        import yt_dlp  # noqa: F401
    except Exception:
        logger.warning("yt-dlp unavailable; skipping download")
        return []
    out: list[str] = []
    try:  # pragma: no cover - network/tooling path
        from yt_dlp import YoutubeDL

        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        urls = [u.strip() for u in Path(urls_file).read_text(encoding="utf-8").splitlines() if u.strip()]
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(Path(dest_dir) / "%(id)s.%(ext)s"),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
            "quiet": True,
        }
        with YoutubeDL(opts) as ydl:
            for url in urls:
                ydl.download([url])
        out = [str(p) for p in Path(dest_dir).glob("*.wav")]
    except Exception as exc:  # noqa: BLE001
        logger.warning("yt-dlp download failed: %s", exc)
    return out


def train_voice_model(
    youtube_urls: Optional[str] = None,
    dataset: Optional[str] = None,
    model_name: str = "shyam_voice_v1",
) -> str:
    """Train/retrain the cloud RVC voice model and register it in learning.yaml.

    Flow (FR-23): yt-dlp download -> stem.batch_isolate -> rvc.train ->
    rvc.detect_range -> register model ref + range + provider in the Learning File.
    """
    from ..config import get_settings
    from ..memory import learning as mem

    settings = get_settings()
    models_dir = settings.rvc_models_dir
    models_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir = models_dir.parent / "datasets" / model_name
    dataset_dir.mkdir(parents=True, exist_ok=True)

    # 1. Acquire raw audio.
    if youtube_urls:
        downloads = str(models_dir.parent / "downloads")
        raw = _download_youtube(youtube_urls, downloads)
        if raw:
            iso = stem_batch_isolate(input_dir=downloads, dest_dir=str(dataset_dir), target="vocals")
            logger.info("Isolated %s training clips", iso.get("count"))
    elif dataset:
        src = Path(dataset)
        if src.is_dir():
            stem_batch_isolate(input_dir=str(src), dest_dir=str(dataset_dir), target="vocals")

    # 2. Train.
    dataset_ref = str(dataset or dataset_dir)
    train = rvc_train(dataset_url_or_zip=dataset_ref, model_name=model_name)
    if not train.get("ok"):
        return f"training failed: {train.get('error')}"
    task = rvc_get_train_task(task_id=train["task_id"])
    model_ref = task.get("model_ref", "")

    # 3. Auto-detect range (FR-12b).
    rng = rvc_detect_range(vocals_dir=str(dataset_dir))
    voice_range = {k: rng[k] for k in ("low_note", "high_note", "median_note") if k in rng}

    # 4. Register in the Learning File.
    mem.register_voice_model(model_ref or f"local://{model_name}", settings.voice_provider, voice_range)
    return (
        f"Trained '{model_name}': model_ref={model_ref or 'mock'}, "
        f"range={voice_range or 'default'}, provider={settings.voice_provider}. Registered in learning.yaml."
    )
