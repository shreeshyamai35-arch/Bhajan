"""Provider selection for rvc-mcp (cloud voice conversion + training).

Backend is chosen via ``VOICE_PROVIDER``:
    replicate      (default)  -> REPLICATE_API_TOKEN + the `replicate` lib
    colab_tunnel / kaggle_tunnel -> RVC_TUNNEL_URL (httpx POST to a free GPU)
    kits           -> KITS_API_KEY

A deterministic :class:`MockProvider` activates when ``mock_enabled()`` is true
or the credentials/url for the selected backend are missing. Selection never
crashes on missing keys — it always falls back to mock.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ..common import ProviderError, assert_safe_url, mock_enabled, require_env


def _copy_or_synth(input_path: Path, dest: Path,
                   pitch_shift_semitones: float = 0.0) -> Path:
    """Produce a real output wav from an input (mock convert).

    Copies the input audio; if ``pitch_shift_semitones`` is set, applies a
    cheap resample-based pitch shift so the output differs from the input.
    Falls back to a plain copy / tiny sine if the input is unreadable.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        data, sr = sf.read(str(input_path), dtype="float32")
        if pitch_shift_semitones:
            factor = 2.0 ** (pitch_shift_semitones / 12.0)
            n = max(1, int(round(len(data) / factor)))
            idx = np.clip((np.arange(n) * factor).astype(int), 0, len(data) - 1)
            data = data[idx]
        sf.write(str(dest), data, sr)
        return dest
    except Exception:  # noqa: BLE001 - mock fallback, never fatal
        try:
            shutil.copyfile(input_path, dest)
            return dest
        except Exception:  # noqa: BLE001
            t = np.linspace(0.0, 1.0, 44100, endpoint=False)
            sf.write(str(dest), (0.2 * np.sin(2 * np.pi * 220 * t)).astype("float32"),
                     44100)
            return dest


class MockProvider:
    """Deterministic offline RVC backend for tests / no-key runs."""

    name = "mock"

    def convert(self, *, input_path: Path, dest_path: Path,
                pitch_shift_semitones: float = 0.0, **_: Any) -> Path:
        return _copy_or_synth(input_path, dest_path, pitch_shift_semitones)

    def train(self, *, model_name: str, sample_rate: int,
              models_dir: Path, **_: Any) -> dict[str, Any]:
        task_id = f"mock-rvc-{uuid.uuid4().hex[:12]}"
        model_ref = f"mock://{model_name}"
        return {
            "task_id": task_id,
            "status": "complete",
            "model_ref": model_ref,
            "metrics": {"epochs": 0, "loss": 0.0, "mock": True},
            "sr": sample_rate,
        }


class ReplicateProvider:
    """Replicate-backed RVC (uses the `replicate` lib).

    Inference uses ``zsxkib/realistic-voice-cloning`` (AICoverGen). We feed it a
    guide vocal and suppress its cover pipeline (no reverb, instrumental/backup
    muted) so the output is a near-clean converted vocal that BhajanForge then
    mixes itself. The custom voice is supplied via ``REPLICATE_RVC_MODEL_URL``
    (the trained-model zip URL produced by ``replicate/train-rvc-model``).
    """

    name = "replicate"

    @staticmethod
    def _output_to_bytes(output: Any) -> bytes | None:
        """Best-effort extraction of audio bytes from a replicate output."""
        item = output
        if isinstance(item, (list, tuple)):
            item = item[0] if item else None
        if item is None:
            return None
        # Newer replicate lib returns FileOutput (supports .read()).
        if hasattr(item, "read"):
            try:
                return item.read()
            except Exception:  # noqa: BLE001
                pass
        url = getattr(item, "url", None) or (item if isinstance(item, str) else None)
        if not url:
            return None
        import httpx

        assert_safe_url(url)
        with httpx.Client(timeout=600.0, follow_redirects=True) as c:
            resp = c.get(url)
            if resp.status_code >= 400:
                raise ProviderError(f"download {resp.status_code}")
            return resp.content

    def convert(self, *, input_path: Path, dest_path: Path,
                model_name: str = "", pitch_shift_semitones: float = 0.0,
                index_ratio: float = 0.75, f0_method: str = "rmvpe",
                protect_voiceless: float = 0.33, resample_sr: int = 48000,
                **_: Any) -> Path:
        import replicate  # local import; not needed offline

        model = os.getenv("REPLICATE_RVC_INFER_MODEL")
        if not model:
            raise ProviderError("REPLICATE_RVC_INFER_MODEL not set")
        # Community models require an explicit version. Resolve latest if the id
        # has no ':<version>' pinned.
        if ":" not in model:
            try:
                model = f"{model}:{replicate.models.get(model).latest_version.id}"
            except Exception:  # noqa: BLE001
                pass
        model_url = os.getenv("REPLICATE_RVC_MODEL_URL", "").strip()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        algo = "rmvpe" if str(f0_method).lower().startswith("rmvpe") else "mangio-crepe"
        with open(input_path, "rb") as fh:
            payload: dict[str, Any] = {
                "song_input": fh,
                "rvc_model": "CUSTOM" if model_url else (model_name or "CUSTOM"),
                "index_rate": index_ratio,
                "protect": protect_voiceless,
                "pitch_change": "no-change",
                "pitch_change_all": pitch_shift_semitones,
                "pitch_detection_algorithm": algo,
                "rms_mix_rate": 0.25,
                "output_format": "wav",
                # Suppress the cover pipeline -> near-clean converted vocal.
                "reverb_wetness": 0.0,
                "reverb_dryness": 1.0,
                "instrumental_volume_change": -50,
                "backup_vocals_volume_change": -50,
            }
            if model_url:
                payload["custom_rvc_model_download_url"] = model_url
            output = replicate.run(model, input=payload)
        data = self._output_to_bytes(output)
        if not data:
            raise ProviderError("replicate returned no usable output")
        dest_path.write_bytes(data)
        return dest_path

    def train(self, *, model_name: str, sample_rate: int, models_dir: Path,
              dataset_url_or_zip: str = "", version: str = "v2",
              epochs: int = 200, **_: Any) -> dict[str, Any]:
        import replicate

        model = os.getenv("REPLICATE_RVC_TRAIN_MODEL")
        if not model:
            raise ProviderError("REPLICATE_RVC_TRAIN_MODEL not set")
        sr = "48k" if int(sample_rate) >= 48000 else "40k"
        payload: dict[str, Any] = {
            "sample_rate": sr,
            "version": version,
            "f0method": "rmvpe_gpu",
            "epoch": int(epochs),
            "batch_size": "7",
        }
        if dataset_url_or_zip.lower().startswith("http"):
            payload["dataset_zip"] = dataset_url_or_zip
            output = replicate.run(model, input=payload)
        else:
            with open(dataset_url_or_zip, "rb") as fh:
                payload["dataset_zip"] = fh
                output = replicate.run(model, input=payload)
        item = output[0] if isinstance(output, (list, tuple)) and output else output
        model_ref = getattr(item, "url", None) or (item if isinstance(item, str) else str(item))
        return {
            "task_id": "",
            "status": "complete",
            "model_ref": model_ref,
            "metrics": {},
            "sr": sample_rate,
        }


class TunnelProvider:
    """Free-GPU tunnel (colab/kaggle) via httpx POST to ``RVC_TUNNEL_URL``."""

    name = "tunnel"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _post_convert(self, client, wav_path: str, kw: dict[str, Any]) -> bytes:
        with open(wav_path, "rb") as fh:
            resp = client.post(f"{self.base_url}/convert", files={"audio": fh},
                               data={k: str(v) for k, v in kw.items()})
        if resp.status_code >= 400:
            raise ProviderError(f"tunnel /convert {resp.status_code}")
        return resp.content

    def convert(self, *, input_path: Path, dest_path: Path, **kw: Any) -> Path:
        import httpx
        import tempfile
        import numpy as np
        import soundfile as sf

        assert_safe_url(f"{self.base_url}/convert")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        timeout = float(os.getenv("RVC_TUNNEL_TIMEOUT", "1800"))
        # Free HF Spaces drop a single request after ~5 min, so convert long
        # audio in short chunks (each well under that) and stitch the results.
        chunk_sec = float(os.getenv("RVC_TUNNEL_CHUNK_SEC", "40"))

        data, sr = sf.read(str(input_path))
        total_sec = len(data) / float(sr) if sr else 0.0

        with httpx.Client(timeout=timeout) as c:
            if total_sec <= chunk_sec * 1.25:
                tmp = tempfile.mktemp(suffix=".wav")
                sf.write(tmp, data, sr)
                dest_path.write_bytes(self._post_convert(c, tmp, kw))
                return dest_path

            step = int(chunk_sec * sr)
            parts: list[Any] = []
            out_sr = sr
            for start in range(0, len(data), step):
                seg = data[start:start + step]
                tmp_in = tempfile.mktemp(suffix=".wav")
                sf.write(tmp_in, seg, sr)
                tmp_out = tempfile.mktemp(suffix=".wav")
                Path(tmp_out).write_bytes(self._post_convert(c, tmp_in, kw))
                odata, out_sr = sf.read(tmp_out)
                parts.append(odata)
            full = np.concatenate(parts, axis=0) if parts else data
            sf.write(str(dest_path), full, out_sr)
        return dest_path

    def train(self, *, model_name: str, sample_rate: int, models_dir: Path,
              **kw: Any) -> dict[str, Any]:
        import httpx

        with httpx.Client(timeout=120.0) as c:
            resp = c.post(f"{self.base_url}/train", json={
                "model_name": model_name, "sample_rate": sample_rate, **kw})
            if resp.status_code >= 400:
                raise ProviderError(f"tunnel /train {resp.status_code}")
            data = resp.json()
        return {
            "task_id": data.get("task_id", ""),
            "status": data.get("status", "running"),
            "model_ref": data.get("model_ref", ""),
            "metrics": data.get("metrics", {}),
            "sr": sample_rate,
        }


def get_provider() -> Any:
    """Return the active RVC provider, falling back to mock when offline."""
    if mock_enabled():
        return MockProvider()

    provider = os.getenv("VOICE_PROVIDER", "replicate").strip().lower()

    if provider in {"colab_tunnel", "kaggle_tunnel"}:
        if require_env("RVC_TUNNEL_URL"):
            return MockProvider()
        return TunnelProvider(os.environ["RVC_TUNNEL_URL"])

    if provider == "kits":
        if require_env("KITS_API_KEY"):
            return MockProvider()
        # Kits shares the tunnel-style HTTP contract via its own base url.
        base = os.getenv("KITS_API_BASE", "https://arpeggi.io/api/kits")
        return TunnelProvider(base)

    # default: replicate
    if require_env("REPLICATE_API_TOKEN"):
        return MockProvider()
    return ReplicateProvider()
