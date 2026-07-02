"""stem-mcp providers.

Selected via ``STEM_PROVIDER``: lalal (default) | replicate (Demucs) |
colab_tunnel/kaggle_tunnel (``STEM_TUNNEL_URL``). Cloud paths are gated behind
key/url presence and degrade to the local ``MockStemProvider`` synthesis, which
splits a track into a low-passed instrumental and a high-passed vocal so the
pipeline always gets real files offline.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import numpy as np
import scipy.signal as sps

from ..common import ProviderError, mock_enabled, ok


def _read(path: str) -> tuple[np.ndarray, int]:
    import soundfile as sf

    data, sr = sf.read(str(path), dtype="float64", always_2d=False)
    return np.asarray(data, dtype=np.float64), int(sr)


def _to_mono(data: np.ndarray) -> np.ndarray:
    return data if data.ndim == 1 else data.mean(axis=1)


def _write(path: str, data: np.ndarray, sr: int) -> None:
    import soundfile as sf

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    arr = np.nan_to_num(np.asarray(data, dtype=np.float32))
    arr = np.clip(arr, -1.0, 1.0)
    sf.write(str(p), arr, sr, subtype="PCM_16")


class MockStemProvider:
    """Offline synthesis: low-pass -> instrumental, high-pass -> vocals."""

    name = "mock"
    cloud_available = False

    def isolate(self, input_path: str, dest_dir: str, target: str = "both") -> dict[str, Any]:
        data, sr = _read(input_path)
        mono = _to_mono(data)
        nyq = sr / 2.0
        split = min(2000.0, nyq - 1.0)

        b_lp, a_lp = sps.butter(4, split / nyq, btype="lowpass")
        b_hp, a_hp = sps.butter(4, split / nyq, btype="highpass")
        instrumental = sps.lfilter(b_lp, a_lp, mono)
        vocals = sps.lfilter(b_hp, a_hp, mono)

        out = Path(dest_dir)
        vocals_path = out / "cleaned_vocal.wav"
        instr_path = out / "instrumental.wav"
        _write(str(vocals_path), vocals, sr)
        _write(str(instr_path), instrumental, sr)

        return ok(
            vocals_path=str(vocals_path),
            instrumental_path=str(instr_path),
            provider_used="mock",
        )


class LalalProvider:
    """LALAL.AI HTTP flow; degrades to ProviderError on any failure."""

    name = "lalal"

    def __init__(self, api_key: str, base_url: Optional[str] = None) -> None:
        self._api_key = api_key
        self._base_url = (base_url or os.getenv("LALAL_API_BASE", "https://www.lalal.ai/api")).rstrip("/")
        self.cloud_available = True

    def isolate(self, input_path: str, dest_dir: str, target: str = "both") -> dict[str, Any]:
        try:
            import httpx
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"httpx unavailable: {exc}") from exc
        try:  # pragma: no cover - network path
            headers = {"Authorization": f"license {self._api_key}"}
            with httpx.Client(timeout=120.0) as client:
                with open(input_path, "rb") as fh:
                    up = client.post(f"{self._base_url}/upload/", headers=headers, files={"file": fh})
                up.raise_for_status()
                file_id = up.json().get("id")
                if not file_id:
                    raise ProviderError("LALAL upload missing id")
                # In a real flow we'd poll /check/ and download stems; gated here.
                raise ProviderError("LALAL polling not configured offline")
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"LALAL isolate failed: {exc}") from exc


class ReplicateDemucsProvider:
    """Replicate Demucs HTTP flow; degrades to ProviderError on failure."""

    name = "replicate"

    def __init__(self, api_token: str) -> None:
        self._token = api_token
        self.cloud_available = True

    def isolate(self, input_path: str, dest_dir: str, target: str = "both") -> dict[str, Any]:
        try:
            import httpx  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"httpx unavailable: {exc}") from exc
        # Gated: real prediction requires upload + polling.
        raise ProviderError("Replicate Demucs not configured offline")


class TunnelStemProvider:
    """colab_tunnel / kaggle_tunnel: POST to STEM_TUNNEL_URL."""

    name = "tunnel"

    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/")
        self.cloud_available = True

    def isolate(self, input_path: str, dest_dir: str, target: str = "both") -> dict[str, Any]:
        try:
            import httpx
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"httpx unavailable: {exc}") from exc
        try:  # pragma: no cover - network path
            with httpx.Client(timeout=300.0) as client:
                with open(input_path, "rb") as fh:
                    resp = client.post(
                        f"{self._url}/isolate",
                        files={"file": fh},
                        data={"target": target},
                    )
                resp.raise_for_status()
                payload = resp.json()
            out = Path(dest_dir)
            out.mkdir(parents=True, exist_ok=True)
            vocals_path = out / "cleaned_vocal.wav"
            instr_path = out / "instrumental.wav"
            if payload.get("vocals_b64"):
                import base64

                vocals_path.write_bytes(base64.b64decode(payload["vocals_b64"]))
            if payload.get("instrumental_b64"):
                import base64

                instr_path.write_bytes(base64.b64decode(payload["instrumental_b64"]))
            return ok(
                vocals_path=str(vocals_path),
                instrumental_path=str(instr_path),
                provider_used="tunnel",
            )
        except Exception as exc:
            raise ProviderError(f"tunnel isolate failed: {exc}") from exc


def select_stem_provider() -> Any:
    """Choose a stem provider from env; mock-safe and key/url gated."""
    if mock_enabled():
        return MockStemProvider()
    name = os.getenv("STEM_PROVIDER", "lalal").strip().lower()
    if name == "lalal":
        key = os.getenv("LALAL_API_KEY")
        if key:
            return LalalProvider(key)
    elif name == "replicate":
        token = os.getenv("REPLICATE_API_TOKEN")
        if token:
            return ReplicateDemucsProvider(token)
    elif name in {"colab_tunnel", "kaggle_tunnel"}:
        url = os.getenv("STEM_TUNNEL_URL")
        if url:
            return TunnelStemProvider(url)
    return MockStemProvider()
