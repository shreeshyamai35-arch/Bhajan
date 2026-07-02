"""audio-mcp providers.

Mastering uses ``MASTERING_PROVIDER`` (landr | matchering | mock). ASR uses
``ASR_PROVIDER``. Cloud providers are httpx-based but must degrade to a local
fallback (handled by ``core``) when keys are absent or a call fails — never crash.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..common import ProviderError, mock_enabled


class MockMasterProvider:
    """No cloud; signals core to run the local pyloudnorm/limiter master."""

    name = "local"
    cloud_available = False


class LandrProvider:
    """LANDR mastering via HTTP. Degrades by raising ``ProviderError`` so that
    ``core`` falls back to local mastering."""

    name = "landr"

    def __init__(self, api_key: str, base_url: Optional[str] = None) -> None:
        self._api_key = api_key
        self._base_url = (base_url or os.getenv("LANDR_API_BASE", "https://api.landr.com")).rstrip("/")
        self.cloud_available = True

    def master(
        self,
        input_path: str,
        dest_path: str,
        target_lufs: float,
        true_peak_dbtp: float,
        intensity: str = "medium",
        reference_track: Optional[str] = None,
    ) -> dict[str, Any]:
        try:
            import httpx
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"httpx unavailable: {exc}") from exc

        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:  # pragma: no cover - network path, exercised only with a real key
            with httpx.Client(timeout=60.0) as client:
                with open(input_path, "rb") as fh:
                    up = client.post(
                        f"{self._base_url}/v1/masters",
                        headers=headers,
                        files={"file": fh},
                        data={"intensity": intensity, "target_lufs": str(target_lufs)},
                    )
                up.raise_for_status()
                payload = up.json()
                audio_url = payload.get("audio_url")
                if not audio_url:
                    raise ProviderError("LANDR response missing audio_url")
                dl = client.get(audio_url, headers=headers)
                dl.raise_for_status()
                from pathlib import Path

                Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
                Path(dest_path).write_bytes(dl.content)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"LANDR mastering failed: {exc}") from exc

        # Measure the delivered master locally for the envelope.
        from . import core

        data, sr = core._read(dest_path)
        from ..common import ok

        return ok(
            output_path=str(dest_path),
            lufs=round(core._integrated_lufs(data, sr), 2),
            true_peak=round(core._true_peak_dbtp(data), 2),
            provider_used="landr",
        )


def select_mastering_provider(provider: Optional[str] = None) -> Any:
    """Pick a mastering provider from env / argument; mock-safe."""
    name = (provider or os.getenv("MASTERING_PROVIDER", "landr")).strip().lower()
    if mock_enabled():
        return MockMasterProvider()
    if name == "landr":
        key = os.getenv("LANDR_API_KEY")
        if key:
            return LandrProvider(key)
        return MockMasterProvider()
    # matchering / unknown -> local path (core handles matchering if importable)
    return MockMasterProvider()


class MockASRProvider:
    name = "stub"
    cloud_available = False


class GroqASRProvider:
    """Groq Whisper ASR over the OpenAI-compatible HTTP API.

    POSTs a multipart request to ``{ASR_API_BASE}/audio/transcriptions`` with the
    audio file + model, Bearer auth. The response JSON exposes a ``text`` field
    (no word timings), so ``words`` is returned empty. Degrades to
    ``ProviderError`` on any failure so ``core`` can fall back to the stub.
    """

    name = "groq"

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None) -> None:
        self._api_key = api_key
        self._base_url = (base_url or os.getenv("ASR_API_BASE", "")).rstrip("/")
        self._model = model or os.getenv("ASR_MODEL", "whisper-large-v3")
        self.cloud_available = bool(self._base_url and self._api_key)

    def transcribe(self, input_path: str, language: str = "hi") -> dict[str, Any]:
        try:
            import httpx
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"httpx unavailable: {exc}") from exc

        from pathlib import Path

        data: dict[str, str] = {"model": self._model}
        if language:
            data["language"] = language
        try:
            with httpx.Client(timeout=120.0) as client:
                with open(input_path, "rb") as fh:
                    resp = client.post(
                        f"{self._base_url}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        files={"file": (Path(input_path).name, fh, "application/octet-stream")},
                        data=data,
                    )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:
            raise ProviderError(f"Groq ASR failed: {exc}") from exc

        from ..common import ok

        text = payload.get("text", "") if isinstance(payload, dict) else ""
        return ok(text=text, words=[])


class CloudASRProvider:
    """Generic cloud ASR over HTTP; degrades to ``ProviderError`` on failure."""

    name = "cloud"

    def __init__(self, api_key: str, base_url: Optional[str] = None) -> None:
        self._api_key = api_key
        self._base_url = (base_url or os.getenv("ASR_API_BASE", "")).rstrip("/")
        self.cloud_available = bool(self._base_url)

    def transcribe(self, input_path: str, language: str = "hi") -> dict[str, Any]:
        try:
            import httpx
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"httpx unavailable: {exc}") from exc
        try:  # pragma: no cover - network path
            with httpx.Client(timeout=120.0) as client:
                with open(input_path, "rb") as fh:
                    resp = client.post(
                        f"{self._base_url}/v1/transcribe",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        files={"file": fh},
                        data={"language": language},
                    )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:
            raise ProviderError(f"ASR failed: {exc}") from exc

        from ..common import ok

        return ok(text=payload.get("text", ""), words=payload.get("words", []))


def select_asr_provider() -> Any:
    """Pick an ASR provider from env; mock-safe and never crashes on missing keys."""
    if mock_enabled():
        return MockASRProvider()
    provider = os.getenv("ASR_PROVIDER", "").strip().lower()
    key = os.getenv("ASR_API_KEY")
    base = os.getenv("ASR_API_BASE")
    if provider == "groq":
        if key:
            return GroqASRProvider(key, base)
        return MockASRProvider()
    if key and base:
        return CloudASRProvider(key, base)
    return MockASRProvider()
