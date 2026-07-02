"""Groq Whisper ASR tests — fully offline, httpx is monkeypatched (NO live calls).

Covers:
  * select_asr_provider() returns the mock stub in mock mode.
  * GroqASRProvider POSTs to the OpenAI-compatible endpoint and parses ``text``.
  * audio_transcribe() in mock mode returns the deterministic offline stub.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from bhajanforge.mcp_servers.audio_mcp import audio_transcribe
from bhajanforge.mcp_servers.audio_mcp import providers

SR = 48000


def _make_wav(path: Path) -> str:
    t = np.linspace(0, 1.0, SR, endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), sig, SR, subtype="PCM_16")
    return str(path)


# --------------------------------------------------------------------------
# Fake httpx plumbing
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict, captured: dict) -> None:
        self._payload = payload
        self._captured = captured

    def raise_for_status(self) -> None:  # noqa: D401 - mimic httpx
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Drop-in for ``httpx.Client`` capturing the request and returning a payload."""

    payload: dict = {"text": ""}
    captured: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def post(self, url, headers=None, files=None, data=None, **kwargs) -> _FakeResponse:
        _FakeClient.captured = {
            "url": url,
            "headers": headers or {},
            "files": files or {},
            "data": data or {},
        }
        return _FakeResponse(_FakeClient.payload, _FakeClient.captured)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_select_asr_provider_mock_mode():
    # BHAJANFORGE_MOCK=1 is set by the test harness.
    prov = providers.select_asr_provider()
    assert prov.name == "stub"
    assert getattr(prov, "cloud_available", False) is False


def test_groq_provider_transcribes(tmp_path, monkeypatch):
    import httpx

    _FakeClient.payload = {"text": "shyam shyam khatu wale"}
    monkeypatch.setattr(httpx, "Client", _FakeClient)

    audio = _make_wav(tmp_path / "master.wav")
    prov = providers.GroqASRProvider(
        api_key="test-key",
        base_url="https://api.groq.com/openai/v1",
        model="whisper-large-v3",
    )
    assert prov.cloud_available is True

    res = prov.transcribe(input_path=audio, language="hi")
    assert res["ok"] is True
    assert res["text"] == "shyam shyam khatu wale"
    assert res["words"] == []

    # Verify the request shape (OpenAI-compatible transcription endpoint).
    cap = _FakeClient.captured
    assert cap["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert cap["headers"]["Authorization"] == "Bearer test-key"
    assert cap["data"]["model"] == "whisper-large-v3"
    assert cap["data"]["language"] == "hi"
    assert "file" in cap["files"]


def test_select_asr_provider_groq(monkeypatch):
    monkeypatch.delenv("BHAJANFORGE_MOCK", raising=False)
    monkeypatch.setenv("ASR_PROVIDER", "groq")
    monkeypatch.setenv("ASR_API_KEY", "test-key")
    monkeypatch.setenv("ASR_API_BASE", "https://api.groq.com/openai/v1")

    prov = providers.select_asr_provider()
    assert isinstance(prov, providers.GroqASRProvider)
    assert prov.cloud_available is True


def test_select_asr_provider_groq_missing_key(monkeypatch):
    monkeypatch.delenv("BHAJANFORGE_MOCK", raising=False)
    monkeypatch.setenv("ASR_PROVIDER", "groq")
    monkeypatch.delenv("ASR_API_KEY", raising=False)

    # Never crashes on a missing key -> falls back to the mock stub.
    prov = providers.select_asr_provider()
    assert prov.name == "stub"


def test_audio_transcribe_mock_stub(tmp_path):
    audio = _make_wav(tmp_path / "master.wav")
    res = audio_transcribe(input_path=audio, language="hi")
    assert res["ok"] is True
    assert isinstance(res["text"], str) and res["text"]
    assert isinstance(res["words"], list) and len(res["words"]) > 0
    assert {"w", "start", "end"} <= set(res["words"][0].keys())
