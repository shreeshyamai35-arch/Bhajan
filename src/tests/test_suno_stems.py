"""Offline tests for suno-mcp REAL stem separation (vocal-removal API).

No live sunoapi.org calls are made — the HTTP client is fully mocked and the
download step is stubbed to write tiny files, so these tests consume zero
credits. Run with BHAJANFORGE_MOCK=1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bhajanforge.mcp_servers.suno_mcp import suno_extract_stems, suno_generate, suno_get_task
from bhajanforge.mcp_servers.suno_mcp import core as suno_core
from bhajanforge.mcp_servers.suno_mcp.providers import (
    HttpSunoProvider,
    _find_stem_urls,
)
from bhajanforge.mcp_servers.common import ProviderError


# ---------------------------------------------------------------------------
# Fake httpx client plumbing (no network)
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Context-manager stand-in for httpx.Client returning canned responses."""

    def __init__(self, post_payload: dict, get_payload: dict):
        self._post_payload = post_payload
        self._get_payload = get_payload
        self.post_calls: list = []
        self.get_calls: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None):  # noqa: A002 - mirror httpx signature
        self.post_calls.append((url, json))
        return _FakeResp(self._post_payload)

    def get(self, url, params=None):
        self.get_calls.append((url, params))
        return _FakeResp(self._get_payload)


# ---------------------------------------------------------------------------
# Mock-mode behavior must be unchanged
# ---------------------------------------------------------------------------
def test_extract_stems_mock_mode_writes_guide_and_instrumental(tmp_path: Path):
    gen = suno_generate(lyrics="Jai Shree Shyam", candidates=1)
    task = suno_get_task(task_id=gen["task_id"])
    clip_id = task["clips"][0]["clip_id"]
    res = suno_extract_stems(clip_id=clip_id, dest_dir=str(tmp_path / "stems"))

    assert res["ok"] is True
    vocal = Path(res["vocal_path"])
    instrumental = Path(res["instrumental_path"])
    assert vocal.name == "guide_vocal.wav" and vocal.exists()
    assert instrumental.name == "instrumental.wav" and instrumental.exists()
    assert vocal.stat().st_size > 0 and instrumental.stat().st_size > 0


# ---------------------------------------------------------------------------
# Defensive URL parsing
# ---------------------------------------------------------------------------
def test_find_stem_urls_parses_nested_payload():
    data = {
        "status": "SUCCESS",
        "response": {
            "vocalRemovalInfo": {
                "originUrl": "https://cdn.example.com/origin.mp3",
                "instrumentalUrl": "https://cdn.example.com/instrumental.mp3",
                "vocalUrl": "https://cdn.example.com/vocal.mp3",
            }
        },
    }
    instrumental, vocal = _find_stem_urls(data)
    assert instrumental == "https://cdn.example.com/instrumental.mp3"
    assert vocal == "https://cdn.example.com/vocal.mp3"


def test_find_stem_urls_missing_returns_none():
    instrumental, vocal = _find_stem_urls({"status": "PENDING", "response": {}})
    assert instrumental is None and vocal is None


# ---------------------------------------------------------------------------
# separate_stems happy path (mocked client + stubbed download)
# ---------------------------------------------------------------------------
def test_separate_stems_extracts_and_downloads(tmp_path: Path, monkeypatch):
    provider = HttpSunoProvider("https://api.sunoapi.org", "test-key")

    post_payload = {"code": 200, "data": {"taskId": "vr-task-123"}}
    get_payload = {
        "code": 200,
        "data": {
            "status": "SUCCESS",
            "response": {
                "vocalRemovalInfo": {
                    "instrumentalUrl": "https://cdn.example.com/instrumental.mp3",
                    "vocalUrl": "https://cdn.example.com/vocal.mp3",
                    "originUrl": "https://cdn.example.com/origin.mp3",
                }
            },
        },
    }
    fake = _FakeClient(post_payload, get_payload)
    monkeypatch.setattr(provider, "_client", lambda: fake)

    downloaded: list[tuple[str, Path]] = []

    def _fake_download(*, clip_id, audio_url, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"RIFFtiny")
        downloaded.append((audio_url, Path(dest)))
        return Path(dest)

    monkeypatch.setattr(provider, "download", _fake_download)

    vocal_dest = tmp_path / "stems" / "guide_vocal.wav"
    instrumental_dest = tmp_path / "stems" / "instrumental.wav"
    info = provider.separate_stems(
        music_task_id="music-task-abc",
        audio_id="clip-xyz",
        vocal_dest=vocal_dest,
        instrumental_dest=instrumental_dest,
    )

    assert info["has_stems"] is True
    assert info["vocal_path"] == str(vocal_dest)
    assert info["instrumental_path"] == str(instrumental_dest)
    assert vocal_dest.exists() and instrumental_dest.exists()

    # The POST body carried the parent music task id + clip id.
    assert fake.post_calls[0][1]["taskId"] == "music-task-abc"
    assert fake.post_calls[0][1]["audioId"] == "clip-xyz"
    assert fake.post_calls[0][0].endswith("/api/v1/vocal-removal/generate")

    # Both correct URLs were downloaded.
    dl_urls = {url for url, _ in downloaded}
    assert dl_urls == {
        "https://cdn.example.com/vocal.mp3",
        "https://cdn.example.com/instrumental.mp3",
    }


def test_separate_stems_raises_on_failed_status(tmp_path: Path, monkeypatch):
    provider = HttpSunoProvider("https://api.sunoapi.org", "test-key")
    post_payload = {"code": 200, "data": {"taskId": "vr-task-fail"}}
    get_payload = {"code": 200, "data": {"status": "CREATE_TASK_FAILED", "errorCode": 500}}
    monkeypatch.setattr(provider, "_client", lambda: _FakeClient(post_payload, get_payload))

    with pytest.raises(ProviderError):
        provider.separate_stems(
            music_task_id="music-task-abc",
            audio_id="clip-xyz",
            vocal_dest=tmp_path / "v.wav",
            instrumental_dest=tmp_path / "i.wav",
        )


def test_separate_stems_raises_without_task_id(tmp_path: Path):
    provider = HttpSunoProvider("https://api.sunoapi.org", "test-key")
    with pytest.raises(ProviderError):
        provider.separate_stems(
            music_task_id="",
            audio_id="clip-xyz",
            vocal_dest=tmp_path / "v.wav",
            instrumental_dest=tmp_path / "i.wav",
        )


# ---------------------------------------------------------------------------
# core.suno_extract_stems routes to separate_stems for a real provider and
# falls back gracefully (never crashes) when separation fails.
# ---------------------------------------------------------------------------
class _StubProvider:
    name = "stub"

    def __init__(self, *, fail: bool):
        self._fail = fail

    def separate_stems(self, *, music_task_id, audio_id, vocal_dest, instrumental_dest):
        if self._fail:
            raise ProviderError("boom")
        Path(vocal_dest).parent.mkdir(parents=True, exist_ok=True)
        Path(vocal_dest).write_bytes(b"v")
        Path(instrumental_dest).write_bytes(b"i")
        return {
            "has_stems": True,
            "vocal_path": str(vocal_dest),
            "instrumental_path": str(instrumental_dest),
        }


def test_core_extract_stems_uses_real_separation(tmp_path: Path, monkeypatch):
    suno_core._CLIPS["clip-real"] = {"audio_url": "", "task_id": "music-task-real"}
    monkeypatch.setattr(suno_core, "get_provider", lambda: _StubProvider(fail=False))

    res = suno_extract_stems(clip_id="clip-real", dest_dir=str(tmp_path / "stems"))
    assert res["ok"] is True
    assert res["has_stems"] is True
    assert Path(res["vocal_path"]).exists()
    assert Path(res["instrumental_path"]).exists()


def test_core_extract_stems_falls_back_on_failure(tmp_path: Path, monkeypatch):
    suno_core._CLIPS["clip-fail"] = {"audio_url": "", "task_id": "music-task-fail"}
    monkeypatch.setattr(suno_core, "get_provider", lambda: _StubProvider(fail=True))

    res = suno_extract_stems(clip_id="clip-fail", dest_dir=str(tmp_path / "stems"))
    assert res["ok"] is True
    assert res["has_stems"] is False
    assert res["vocal_path"] is None
    assert res["instrumental_path"] is None
    assert res["fallback"] == "stem-mcp.isolate"
