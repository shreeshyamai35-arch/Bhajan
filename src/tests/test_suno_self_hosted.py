"""Offline tests for the self-hosted (token-replay) Suno provider.

No network: Clerk auth + studio-api calls are served by an httpx.MockTransport
that imitates the real generate -> feed flow.
"""

from __future__ import annotations

import httpx
import pytest

from bhajanforge.mcp_servers.suno_mcp import providers as P


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/v1/client":
        return httpx.Response(200, json={
            "response": {"last_active_session_id": "sess_1",
                         "sessions": [{"id": "sess_1"}]}
        })
    if path.startswith("/v1/client/sessions/") and path.endswith("/tokens"):
        return httpx.Response(200, json={"jwt": "fake.jwt.token"})
    if path == "/api/generate/v2/":
        return httpx.Response(200, json={
            "id": "batch1",
            "clips": [
                {"id": "c1", "audio_url": "", "title": "Bhajan",
                 "metadata": {"duration": 0}},
                {"id": "c2", "audio_url": "", "title": "Bhajan 2",
                 "metadata": {"duration": 0}},
            ],
        })
    if path == "/api/feed/v2":
        return httpx.Response(200, json={"clips": [
            {"id": "c1", "status": "complete",
             "audio_url": "https://cdn.suno.ai/c1.mp3",
             "metadata": {"duration": 181}, "title": "Bhajan"},
            {"id": "c2", "status": "complete",
             "audio_url": "https://cdn.suno.ai/c2.mp3",
             "metadata": {"duration": 176}, "title": "Bhajan 2"},
        ]})
    if path == "/api/billing/info/":
        return httpx.Response(200, json={"total_credits_left": 1234})
    return httpx.Response(404, json={"error": f"unmocked {path}"})


def _stem_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.startswith("/v1/client/sessions/") and path.endswith("/tokens"):
        return httpx.Response(200, json={"jwt": "fake.jwt.token"})
    if path == "/api/gen/c1/stems/":
        return httpx.Response(200, json={"clips": [
            {"id": "stem_voc"}, {"id": "stem_inst"},
        ]})
    if path == "/api/feed/v2":
        return httpx.Response(200, json={"clips": [
            {"id": "stem_voc", "status": "complete",
             "audio_url": "https://cdn.suno.ai/voc.mp3",
             "metadata": {"type": "vocals"}, "title": "Vocals"},
            {"id": "stem_inst", "status": "complete",
             "audio_url": "https://cdn.suno.ai/inst.mp3",
             "metadata": {"type": "instrumental"}, "title": "Instrumental"},
        ]})
    if path in ("/voc.mp3", "/inst.mp3"):
        return httpx.Response(200, content=b"RIFF....fake-wav-bytes....")
    return httpx.Response(404, json={"error": f"unmocked {path}"})


@pytest.fixture()
def patched_httpx(monkeypatch: pytest.MonkeyPatch):
    real_client = httpx.Client

    def make_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", make_client)
    yield


def test_map_mv_variants(monkeypatch):
    # _map_mv prioritises the SUNO_MODEL env var; clear it so we test the
    # argument-mapping logic deterministically (the real .env sets SUNO_MODEL).
    monkeypatch.delenv("SUNO_MODEL", raising=False)
    assert P._map_mv("suno-v5.5") == "chirp-v5"
    assert P._map_mv("v4.5") == "chirp-v4-5"
    assert P._map_mv("v3.5") == "chirp-v3-5"
    assert P._map_mv("garbage") == "chirp-v4"  # safe default


def test_get_provider_selects_self_hosted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BHAJANFORGE_MOCK", "0")
    monkeypatch.setenv("SUNO_MODE", "self_hosted")
    monkeypatch.setenv("SUNO_COOKIE", "session=abc; __client=def")
    provider = P.get_provider()
    assert isinstance(provider, P.SelfHostedSunoProvider)
    assert provider.name == "suno-self-hosted"


def test_generate_then_poll(patched_httpx):
    provider = P.SelfHostedSunoProvider(cookie="session=abc; __client=def")
    gen = provider.generate(
        lyrics="Shyam Shyam bolo", style_prompt="slow devotional bhajan",
        model="suno-v5.5", make_instrumental=False, candidates=2,
        duration_hint_sec=240,
    )
    assert gen["task_id"] == "batch1"
    assert gen["status"] == "queued"
    assert {c["clip_id"] for c in gen["clips"]} == {"c1", "c2"}

    state = {"clips": gen["clips"]}
    task = provider.get_task(task_id=gen["task_id"], state=state)
    assert task["status"] == "complete"
    assert len(task["clips"]) == 2
    assert all(c["audio_url"].startswith("https://cdn.suno.ai/") for c in task["clips"])


def test_token_is_cached(patched_httpx):
    provider = P.SelfHostedSunoProvider(cookie="session=abc")
    first = provider._token()
    assert first == "fake.jwt.token"
    # second call returns the cached jwt without re-fetching
    assert provider._token() == first
    assert provider._jwt_exp > 0


def test_native_stems_disabled_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUNO_NATIVE_STEMS", raising=False)
    provider = P.SelfHostedSunoProvider(cookie="session=abc")
    with pytest.raises(P.ProviderError):
        provider.separate_stems(
            music_task_id="batch1", audio_id="c1",
            vocal_dest=__import__("pathlib").Path("v.wav"),
            instrumental_dest=__import__("pathlib").Path("i.wav"),
        )


def test_native_stems_split(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("SUNO_NATIVE_STEMS", "true")
    monkeypatch.setenv("SUNO_SESSION_ID", "sess_1")  # skip /v1/client lookup
    monkeypatch.setenv("BHAJANFORGE_ALLOW_LOCAL_URLS", "1")  # skip DNS/SSRF check
    real_client = httpx.Client

    def make_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_stem_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", make_client)

    provider = P.SelfHostedSunoProvider(cookie="session=abc")
    vocal = tmp_path / "guide_vocal.wav"
    instrumental = tmp_path / "instrumental.wav"
    info = provider.separate_stems(
        music_task_id="batch1", audio_id="c1",
        vocal_dest=vocal, instrumental_dest=instrumental,
        max_wait_sec=5, interval_sec=0.1,
    )
    assert info["has_stems"] is True
    assert vocal.exists() and vocal.stat().st_size > 0
    assert instrumental.exists() and instrumental.stat().st_size > 0


def test_health_valid_cookie(patched_httpx):
    provider = P.SelfHostedSunoProvider(cookie="session=abc")
    h = provider.health()
    assert h["authenticated"] is True
    assert h.get("credits") == 1234


def test_health_invalid_cookie(monkeypatch: pytest.MonkeyPatch):
    def bad_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "expired"})

    real_client = httpx.Client

    def make_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(bad_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", make_client)
    provider = P.SelfHostedSunoProvider(cookie="stale")
    h = provider.health()
    assert h["authenticated"] is False
    assert "SUNO_COOKIE" in h["detail"]


def test_suno_health_tool_mock_mode():
    # conftest forces BHAJANFORGE_MOCK=1 -> MockProvider is selected.
    from bhajanforge.mcp_servers.suno_mcp import suno_health

    res = suno_health()
    assert res["ok"] is True
    assert res["provider"] == "mock"
    assert res["authenticated"] is True
