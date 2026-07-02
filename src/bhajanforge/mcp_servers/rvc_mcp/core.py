"""rvc-mcp core tool functions (pure Python, no mcp dependency).

Tool names map to functions with dots replaced by underscores:
    rvc.list_models     -> rvc_list_models
    rvc.convert         -> rvc_convert
    rvc.train           -> rvc_train          (long: returns task_id)
    rvc.get_train_task  -> rvc_get_train_task
    rvc.detect_range    -> rvc_detect_range

Trained-model references/metadata are stored as small JSON files in
``RVC_MODELS_DIR`` (Settings().rvc_models_dir) — never GPU weights. On training
completion the model + auto-detected range are registered into the Learning
File via ``memory.learning.register_voice_model``.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np
import soundfile as sf

from ..common import err, ok, safe_call
from .providers import get_provider

# task_id -> {"status", "model_ref", "metrics", "model_name", "provider", "sr"}
_TRAIN_TASKS: dict[str, dict[str, Any]] = {}

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_DEFAULT_RANGE = {"low_note": "A2", "high_note": "E4", "median_note": "C3"}


# --- helpers --------------------------------------------------------------


def _models_dir() -> Path:
    from ...config import get_settings

    d = get_settings().rvc_models_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _learning_path() -> Optional[Path]:
    """Resolve the learning.yaml path, honouring a test override env var."""
    override = os.getenv("BHAJANFORGE_LEARNING_PATH")
    return Path(override) if override else None


def freq_to_note(freq: float) -> str:
    """Convert a frequency in Hz to the nearest note name (e.g. ``A2``)."""
    if freq <= 0:
        return "C3"
    midi = int(round(69 + 12 * math.log2(freq / 440.0)))
    name = _NOTE_NAMES[midi % 12]
    octave = midi // 12 - 1
    return f"{name}{octave}"


def _estimate_pitch_hz(samples: np.ndarray, sr: int) -> float:
    """Estimate a dominant pitch (Hz) via autocorrelation. 0.0 if none found."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    samples = samples.astype(np.float64)
    if samples.size < sr // 20:  # too short to be meaningful
        # Fall back to FFT peak for very short signals.
        return _fft_peak_hz(samples, sr)
    samples = samples - np.mean(samples)
    if not np.any(samples):
        return 0.0
    corr = np.correlate(samples, samples, mode="full")
    corr = corr[corr.size // 2:]
    # Search a plausible vocal range: ~65 Hz (C2) to ~1000 Hz.
    min_lag = max(1, int(sr / 1000.0))
    max_lag = min(len(corr) - 1, int(sr / 65.0))
    if max_lag <= min_lag:
        return _fft_peak_hz(samples, sr)
    segment = corr[min_lag:max_lag]
    if segment.size == 0 or not np.any(segment):
        return 0.0
    lag = int(np.argmax(segment)) + min_lag
    return sr / lag if lag > 0 else 0.0


def _fft_peak_hz(samples: np.ndarray, sr: int) -> float:
    if samples.size == 0:
        return 0.0
    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sr)
    if spectrum.size <= 1:
        return 0.0
    peak = int(np.argmax(spectrum[1:])) + 1
    return float(freqs[peak])


# --- tools ----------------------------------------------------------------


def rvc_list_models() -> dict[str, Any]:
    """List trained voice models from RVC_MODELS_DIR metadata JSON files."""

    def _run() -> dict[str, Any]:
        models: list[dict[str, Any]] = []
        models_dir = _models_dir()
        for meta_file in sorted(models_dir.glob("*.json")):
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - skip unreadable metadata
                continue
            models.append({
                "name": data.get("name", meta_file.stem),
                "provider": data.get("provider", ""),
                "model_ref": data.get("model_ref", ""),
                "sr": data.get("sr", 0),
            })
        return ok(models=models)

    return safe_call(_run, "rvc.list_models")


def rvc_convert(input_path: str, model_name: str, pitch_shift_semitones: float = 0,
                index_ratio: float = 0.75, f0_method: str = "rmvpe",
                protect_voiceless: float = 0.33, resample_sr: int = 48000,
                dest_path: str = "") -> dict[str, Any]:
    """Convert a guide vocal to the target voice, writing ``dest_path``."""

    def _run() -> dict[str, Any]:
        src = Path(input_path)
        if not src.exists():
            return err(f"input_path not found: {input_path}")
        dest = Path(dest_path)
        provider = get_provider()
        out = provider.convert(
            input_path=src,
            dest_path=dest,
            model_name=model_name,
            pitch_shift_semitones=pitch_shift_semitones,
            index_ratio=index_ratio,
            f0_method=f0_method,
            protect_voiceless=protect_voiceless,
            resample_sr=resample_sr,
        )
        return ok(output_path=str(out))

    return safe_call(_run, "rvc.convert")


def _write_model_metadata(model_name: str, provider: str, model_ref: str,
                          sr: int) -> Path:
    models_dir = _models_dir()
    meta_path = models_dir / f"{model_name}.json"
    meta_path.write_text(json.dumps({
        "name": model_name,
        "provider": provider,
        "model_ref": model_ref,
        "sr": sr,
    }, indent=2), encoding="utf-8")
    return meta_path


def _finalize_training(state: dict[str, Any]) -> None:
    """Persist metadata + register model/range once a task is complete."""
    model_ref = state.get("model_ref")
    if not model_ref:
        return
    _write_model_metadata(
        state["model_name"], state.get("provider", ""), model_ref,
        state.get("sr", 48000),
    )
    try:
        from ...memory.learning import register_voice_model

        register_voice_model(
            model_ref,
            state.get("provider", ""),
            dict(_DEFAULT_RANGE),
            _learning_path(),
        )
    except Exception:  # noqa: BLE001 - learning registration is non-fatal
        pass


def rvc_train(dataset_url_or_zip: str, model_name: str, sample_rate: int = 48000,
              version: str = "v2", epochs: int = 200,
              f0_method: str = "rmvpe_gpu", batch_size: int = 7) -> dict[str, Any]:
    """Start cloud RVC training. Returns a ``task_id`` to poll."""

    def _run() -> dict[str, Any]:
        provider = get_provider()
        result = provider.train(
            dataset_url_or_zip=dataset_url_or_zip,
            model_name=model_name,
            sample_rate=sample_rate,
            version=version,
            epochs=epochs,
            f0_method=f0_method,
            batch_size=batch_size,
            models_dir=_models_dir(),
        )
        task_id = result["task_id"]
        state = {
            "status": result.get("status", "running"),
            "model_ref": result.get("model_ref", ""),
            "metrics": result.get("metrics", {}),
            "model_name": model_name,
            "provider": provider.name,
            "sr": result.get("sr", sample_rate),
        }
        _TRAIN_TASKS[task_id] = state
        if state["status"] == "complete":
            _finalize_training(state)
        return ok(task_id=task_id)

    return safe_call(_run, "rvc.train")


def rvc_get_train_task(task_id: str) -> dict[str, Any]:
    """Poll a training task. Returns status, model_ref and metrics."""

    def _run() -> dict[str, Any]:
        state = _TRAIN_TASKS.get(task_id)
        if state is None:
            return err("unknown task_id", status="failed")
        if state["status"] != "complete":
            # Real backends would be polled here; mock is already complete.
            provider = get_provider()
            poll = getattr(provider, "get_train_task", None)
            if callable(poll):
                try:
                    result = poll(task_id=task_id, state=state)
                    state["status"] = result.get("status", state["status"])
                    state["model_ref"] = result.get("model_ref", state["model_ref"])
                    state["metrics"] = result.get("metrics", state["metrics"])
                except Exception:  # noqa: BLE001
                    pass
            if state["status"] == "complete":
                _finalize_training(state)
        return ok(
            status=state["status"],
            model_ref=state.get("model_ref", ""),
            metrics=state.get("metrics", {}),
        )

    return safe_call(_run, "rvc.get_train_task")


def rvc_detect_range(vocals_dir: str) -> dict[str, Any]:
    """Analyze vocal wavs to estimate the singer's low/high/median note.

    Returns documented defaults (A2/E4/C3) when no analysable audio is found.
    """

    def _run() -> dict[str, Any]:
        directory = Path(vocals_dir)
        pitches: list[float] = []
        if directory.exists():
            for wav in sorted(directory.glob("**/*.wav")):
                try:
                    data, sr = sf.read(str(wav), dtype="float32")
                except Exception:  # noqa: BLE001 - skip unreadable file
                    continue
                freq = _estimate_pitch_hz(np.asarray(data), sr)
                if freq and 50.0 <= freq <= 1200.0:
                    pitches.append(freq)
        if not pitches:
            return ok(**_DEFAULT_RANGE)
        pitches.sort()
        low = pitches[0]
        high = pitches[-1]
        median = float(np.median(pitches))
        return ok(
            low_note=freq_to_note(low),
            high_note=freq_to_note(high),
            median_note=freq_to_note(median),
        )

    return safe_call(_run, "rvc.detect_range")
