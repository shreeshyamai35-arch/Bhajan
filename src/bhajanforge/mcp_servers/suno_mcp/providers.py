"""Provider selection for suno-mcp.

PRIMARY: a self-hosted wrapper around your own suno.com subscription
(:class:`SelfHostedSunoProvider`), selected when ``SUNO_MODE=self_hosted`` and
``SUNO_COOKIE`` is set. FALLBACK: a Suno-compatible third-party gateway
(:class:`HttpSunoProvider`, e.g. ``https://api.sunoapi.org``) via
``SUNO_API_BASE`` / ``SUNO_API_KEY``. When ``mock_enabled()`` is true, or no
provider is configured, a deterministic :class:`MockProvider` runs offline.

Providers never crash on missing keys — selection always falls back to mock.
"""

from __future__ import annotations

import math
import os
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ..common import ProviderError, assert_safe_url, mock_enabled, require_env

_SR = 44100


def _flag(name: str, default: bool = False) -> bool:
    """Read a boolean env flag (1/true/yes/on)."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _write_sine_wav(dest: Path, freq: float = 220.0, seconds: float = 1.0,
                    sr: int = _SR) -> Path:
    """Write a tiny mono sine wav (used by mock download/stems)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0.0, seconds, int(sr * seconds), endpoint=False)
    data = 0.2 * np.sin(2.0 * math.pi * freq * t).astype(np.float32)
    sf.write(str(dest), data, sr)
    return dest


class MockProvider:
    """Deterministic, offline Suno gateway used for tests / no-key runs."""

    name = "mock"

    def generate(self, *, lyrics: str, style_prompt: str, model: str,
                 make_instrumental: bool, candidates: int,
                 duration_hint_sec: int) -> dict[str, Any]:
        task_id = f"mock-suno-{uuid.uuid4().hex[:12]}"
        clips = []
        for i in range(max(1, int(candidates))):
            clips.append(
                {
                    "clip_id": f"{task_id}-clip{i}",
                    "audio_url": f"mock://suno/{task_id}/clip{i}.wav",
                    "duration_sec": int(duration_hint_sec or 240),
                    "title": (style_prompt or "bhajan")[:40] or "bhajan",
                }
            )
        return {"task_id": task_id, "status": "complete", "clips": clips}

    def get_task(self, *, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        # Mock tasks complete immediately.
        return {"status": "complete", "clips": state.get("clips", [])}

    def download(self, *, clip_id: str, audio_url: str, dest: Path) -> Path:
        # Synthesize a small wav at the requested destination.
        return _write_sine_wav(dest, freq=261.63, seconds=1.0)

    def extract_stems(self, *, clip_id: str, vocal_dest: Path,
                      instrumental_dest: Path) -> dict[str, Any]:
        _write_sine_wav(vocal_dest, freq=330.0, seconds=1.0)
        _write_sine_wav(instrumental_dest, freq=110.0, seconds=1.0)
        return {"has_stems": True}

    def health(self) -> dict[str, Any]:
        return {"authenticated": True, "detail": "mock mode (no real Suno calls)"}


def _find_stem_urls(data: Any) -> tuple[str | None, str | None]:
    """Defensively walk a record-info payload for instrumental + vocal URLs.

    Field names vary across sunoapi.org responses, so we recurse through any
    nested dicts / lists and pick string values that look like URLs whose key
    name contains ``instrumental`` or ``vocal``. Instrumental is matched first
    so a generic ``vocal removal`` container never shadows it.
    """
    instrumental_url: str | None = None
    vocal_url: str | None = None

    def _is_url(value: Any) -> bool:
        return isinstance(value, str) and value.lower().startswith(("http://", "https://"))

    def _walk(node: Any) -> None:
        nonlocal instrumental_url, vocal_url
        if isinstance(node, dict):
            for key, value in node.items():
                klower = str(key).lower()
                if _is_url(value):
                    if "instrumental" in klower and not instrumental_url:
                        instrumental_url = value
                    elif "vocal" in klower and "removal" not in klower and not vocal_url:
                        vocal_url = value
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    return instrumental_url, vocal_url


def _map_model(model: str) -> str:
    """Map a configured model tag to a sunoapi.org model id (V3_5/V4/V4_5/V5)."""
    m = (os.getenv("SUNO_MODEL") or model or "V4").strip()
    if m.upper().startswith("V") and "_" in m or m.upper() in {"V3_5", "V4", "V4_5", "V4_5PLUS", "V5"}:
        return m.upper()
    # tolerate values like "suno-v5.5" / "v4.5" -> best-effort
    digits = m.lower().replace("suno-", "").replace("v", "").replace(".", "_").strip("_")
    table = {"3_5": "V3_5", "4": "V4", "4_5": "V4_5", "5": "V5", "5_5": "V5"}
    return table.get(digits, "V4")


class HttpSunoProvider:
    """sunoapi.org gateway connector — the primary music creation path.

    Generate: POST /api/v1/generate (customMode). Poll:
    GET /api/v1/generate/record-info?taskId=... Stems are done locally by the
    caller (stem-mcp) to conserve credits, unless native vocal-removal is used.
    """

    name = "sunoapi.org"

    def __init__(self, api_base: str, api_key: str) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key

    def _client(self):
        import httpx

        return httpx.Client(
            base_url=self.api_base,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=60.0,
        )

    def generate(self, *, lyrics: str, style_prompt: str, model: str,
                 make_instrumental: bool, candidates: int,
                 duration_hint_sec: int) -> dict[str, Any]:
        title = (style_prompt.split(",")[0] if style_prompt else "Devotional Bhajan")[:78]
        payload = {
            "prompt": (style_prompt if make_instrumental else lyrics)[:2900],
            "style": (style_prompt or "devotional bhajan")[:190],
            "title": title or "Bhajan",
            "customMode": True,
            "instrumental": bool(make_instrumental),
            "model": _map_model(model),
            "callBackUrl": os.getenv("SUNO_CALLBACK_URL", "https://example.com/callback"),
        }
        with self._client() as c:
            resp = c.post("/api/v1/generate", json=payload)
        if resp.status_code >= 400:
            raise ProviderError(f"sunoapi /generate {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if data.get("code") != 200:
            raise ProviderError(f"sunoapi /generate code={data.get('code')}: {data.get('msg')}")
        task_id = (data.get("data") or {}).get("taskId")
        if not task_id:
            raise ProviderError("sunoapi returned no taskId")
        return {"task_id": task_id, "status": "queued", "clips": []}

    def get_task(self, *, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._client() as c:
            resp = c.get("/api/v1/generate/record-info", params={"taskId": task_id})
        if resp.status_code >= 400:
            raise ProviderError(f"sunoapi record-info {resp.status_code}")
        d = (resp.json() or {}).get("data") or {}
        raw_status = (d.get("status") or "").upper()
        suno_data = ((d.get("response") or {}).get("sunoData")) or []
        clips = []
        for item in suno_data:
            url = item.get("audioUrl") or item.get("sourceAudioUrl") or item.get("streamAudioUrl")
            if url:
                clips.append({
                    "clip_id": item.get("id", ""),
                    "audio_url": url,
                    "duration_sec": float(item.get("duration") or 0),
                    "title": item.get("title", ""),
                })
        if "FAILED" in raw_status or d.get("errorCode"):
            status = "failed"
        elif raw_status in {"SUCCESS", "FIRST_SUCCESS"} and clips:
            status = "complete"
        else:
            status = "running"
        return {"status": status, "clips": clips}

    def download(self, *, clip_id: str, audio_url: str, dest: Path) -> Path:
        import httpx

        dest.parent.mkdir(parents=True, exist_ok=True)
        assert_safe_url(audio_url)
        with httpx.Client(timeout=180.0, follow_redirects=True) as c:
            resp = c.get(audio_url)
            if resp.status_code >= 400:
                raise ProviderError(f"download {resp.status_code}")
            dest.write_bytes(resp.content)
        return dest

    def extract_stems(self, *, clip_id: str, vocal_dest: Path,
                      instrumental_dest: Path) -> dict[str, Any]:
        # Conserve credits: let the caller split the downloaded clip via stem-mcp.
        return {"has_stems": False}

    def health(self) -> dict[str, Any]:
        """Best-effort reachability/credit check for the gateway key."""
        endpoint = os.getenv("SUNO_CREDIT_ENDPOINT", "/api/v1/generate/credit")
        try:
            with self._client() as c:
                r = c.get(endpoint)
        except Exception as exc:  # noqa: BLE001 - report, don't raise
            return {"authenticated": False, "detail": f"gateway unreachable: {exc}"}
        if r.status_code in (401, 403):
            return {"authenticated": False, "status_code": r.status_code,
                    "detail": "gateway rejected SUNO_API_KEY"}
        info: dict[str, Any] = {"authenticated": r.status_code < 400,
                                "status_code": r.status_code}
        try:
            body = r.json() or {}
            data = body.get("data") if isinstance(body, dict) else None
            if isinstance(data, dict):
                info["credits"] = data.get("credits", data.get("credit"))
            elif isinstance(data, (int, float)):
                info["credits"] = data
        except Exception:  # noqa: BLE001 - body may not be json
            pass
        return info

    def separate_stems(self, *, music_task_id: str, audio_id: str,
                       vocal_dest: Path, instrumental_dest: Path,
                       max_wait_sec: int | None = None,
                       interval_sec: float | None = None) -> dict[str, Any]:
        """Run sunoapi.org vocal-removal: POST generate, poll, download stems.

        Returns ``{"has_stems": True, "vocal_path": ..., "instrumental_path": ...}``
        on success. Raises :class:`ProviderError` on any failure (the caller maps
        that to a stem-mcp fallback rather than crashing the pipeline).
        """
        if not music_task_id:
            raise ProviderError("vocal-removal requires a music task id")

        callback = os.getenv("SUNO_CALLBACK_URL", "https://example.com/callback")
        body = {"taskId": music_task_id, "audioId": audio_id, "callBackUrl": callback}
        with self._client() as c:
            resp = c.post("/api/v1/vocal-removal/generate", json=body)
        if resp.status_code >= 400:
            raise ProviderError(f"vocal-removal/generate {resp.status_code}: {resp.text[:200]}")
        data = resp.json() or {}
        if data.get("code") != 200:
            raise ProviderError(f"vocal-removal/generate code={data.get('code')}: {data.get('msg')}")
        vr_task_id = (data.get("data") or {}).get("taskId")
        if not vr_task_id:
            raise ProviderError("vocal-removal returned no taskId")

        deadline = time.time() + int(
            max_wait_sec if max_wait_sec is not None
            else os.getenv("SUNO_VR_MAX_WAIT_SEC", 300)
        )
        poll = float(
            interval_sec if interval_sec is not None
            else os.getenv("SUNO_VR_INTERVAL_SEC", 5)
        )
        instrumental_url: str | None = None
        vocal_url: str | None = None
        while True:
            with self._client() as c:
                r = c.get("/api/v1/vocal-removal/record-info", params={"taskId": vr_task_id})
            if r.status_code >= 400:
                raise ProviderError(f"vocal-removal/record-info {r.status_code}")
            rd = (r.json() or {}).get("data") or {}
            instrumental_url, vocal_url = _find_stem_urls(rd)
            if instrumental_url and vocal_url:
                break
            status = str(rd.get("status") or "").upper()
            if "FAIL" in status or rd.get("errorCode"):
                raise ProviderError(f"vocal-removal failed: status={status or rd.get('errorCode')}")
            if time.time() > deadline:
                raise ProviderError("vocal-removal timed out waiting for stems")
            time.sleep(poll)

        # Download both stems to the requested destinations.
        self.download(clip_id=audio_id, audio_url=vocal_url, dest=vocal_dest)
        self.download(clip_id=audio_id, audio_url=instrumental_url, dest=instrumental_dest)
        return {
            "has_stems": True,
            "vocal_path": str(vocal_dest),
            "instrumental_path": str(instrumental_dest),
        }


def _map_mv(model: str) -> str:
    """Map a configured model tag to a Suno internal ``mv`` id (chirp-*)."""
    m = (os.getenv("SUNO_MODEL") or model or "v4").strip().lower()
    m = m.replace("suno-", "").replace("chirp-", "").replace("v", "").replace(".", "_").strip("_")
    table = {
        "3": "chirp-v3-0",
        "3_5": "chirp-v3-5",
        "4": "chirp-v4",
        "4_5": "chirp-v4-5",
        "4_5plus": "chirp-v4-5-plus",
        "5": "chirp-v5",
        "5_5": "chirp-v5",
    }
    return table.get(m, "chirp-v4")


class SelfHostedSunoProvider:
    """Token-replay connector that turns your own suno.com subscription into an
    API — the PRIMARY music creation path for the pipeline.

    Auth: Suno uses Clerk. You paste your browser session cookie into
    ``SUNO_COOKIE``; this provider exchanges it for a short-lived JWT against
    ``clerk.suno.com`` and calls Suno's internal ``studio-api`` endpoints
    (generate + feed) exactly as the web app does. No browser is launched.

    NOTE: this drives your own account through unofficial endpoints, which may
    violate Suno's Terms of Service. It is isolated behind ``MusicProvider`` so
    it can be swapped if Suno changes its API or terms (rules.md R2.5).
    """

    name = "suno-self-hosted"

    def __init__(self, cookie: str) -> None:
        self.cookie = cookie.strip()
        self.base_url = os.getenv("SUNO_BASE_URL", "https://studio-api.prod.suno.com").rstrip("/")
        self.clerk_url = os.getenv("SUNO_CLERK_URL", "https://clerk.suno.com").rstrip("/")
        self.clerk_js = os.getenv("SUNO_CLERK_JS_VERSION", "5.66.0")
        self.api_version = os.getenv("SUNO_CLERK_API_VERSION", "").strip()
        # cached JWT: (token, expiry_epoch)
        self._jwt: str | None = None
        self._jwt_exp: float = 0.0
        # access JWT carried directly in the cookie (fallback if Clerk refresh fails)
        self._cookie_jwt = self._parse_cookie_jwt("__session")

    def _parse_cookie_jwt(self, name: str) -> str | None:
        import re as _re

        m = _re.search(rf"{name}=([^;]+)", self.cookie)
        return m.group(1) if m else None

    @staticmethod
    def _jwt_expiry(jwt: str) -> float | None:
        import base64
        import json as _json

        try:
            payload = jwt.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            return float(_json.loads(base64.urlsafe_b64decode(payload)).get("exp"))
        except Exception:  # noqa: BLE001
            return None

    def _clerk_params(self) -> dict[str, str]:
        params = {"_clerk_js_version": self.clerk_js}
        if self.api_version:
            params["__clerk_api_version"] = self.api_version
        return params

    # --- auth -----------------------------------------------------------------
    def _clerk_client(self):
        import httpx

        return httpx.Client(
            base_url=self.clerk_url,
            headers={"Cookie": self.cookie, "Origin": "https://suno.com",
                     "Referer": "https://suno.com/"},
            timeout=30.0,
        )

    def _session_id(self, client) -> str:
        """Resolve the active Clerk session id from the cookie."""
        sid = os.getenv("SUNO_SESSION_ID", "").strip()
        if sid:
            return sid
        resp = client.get("/v1/client", params=self._clerk_params())
        if resp.status_code >= 400:
            raise ProviderError(f"clerk /client {resp.status_code}: check SUNO_COOKIE")
        data = (resp.json() or {}).get("response") or {}
        sid = data.get("last_active_session_id")
        if not sid:
            sessions = data.get("sessions") or []
            sid = sessions[0].get("id") if sessions else None
        if not sid:
            raise ProviderError("could not resolve Clerk session id (expired cookie?)")
        return sid

    def _token(self) -> str:
        """Return a valid short-lived JWT, refreshing ~10s before expiry.

        Tries the Clerk token-refresh flow; if that fails (e.g. Clerk API
        changes), falls back to the access JWT carried directly in the
        ``__session`` cookie while it is still valid.
        """
        now = time.time()
        if self._jwt and now < self._jwt_exp - 10:
            return self._jwt
        try:
            with self._clerk_client() as client:
                sid = self._session_id(client)
                resp = client.post(
                    f"/v1/client/sessions/{sid}/tokens",
                    params=self._clerk_params(),
                )
            if resp.status_code >= 400:
                raise ProviderError(f"clerk token refresh {resp.status_code}: re-export SUNO_COOKIE")
            jwt = (resp.json() or {}).get("jwt")
            if not jwt:
                raise ProviderError("clerk returned no jwt")
            self._jwt = jwt
            self._jwt_exp = now + 55.0  # Clerk session JWTs live ~60s
            return jwt
        except ProviderError:
            # Fallback: use the __session access JWT straight from the cookie.
            if self._cookie_jwt:
                exp = self._jwt_expiry(self._cookie_jwt)
                if exp and now < exp - 10:
                    self._jwt = self._cookie_jwt
                    self._jwt_exp = exp
                    return self._cookie_jwt
            raise

    def _api(self):
        import httpx

        return httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self._token()}",
                     "Content-Type": "application/json",
                     "Origin": "https://suno.com", "Referer": "https://suno.com/"},
            timeout=60.0,
        )

    # --- MusicProvider interface ---------------------------------------------
    def generate(self, *, lyrics: str, style_prompt: str, model: str,
                 make_instrumental: bool, candidates: int,
                 duration_hint_sec: int) -> dict[str, Any]:
        title = (style_prompt.split(",")[0] if style_prompt else "Devotional Bhajan")[:78]
        payload = {
            "prompt": "" if make_instrumental else (lyrics or "")[:3000],
            "tags": (style_prompt or "devotional bhajan")[:200],
            "title": title or "Bhajan",
            "mv": _map_mv(model),
            "make_instrumental": bool(make_instrumental),
            "generation_type": "TEXT",
            "continue_clip_id": None,
            "continue_at": None,
            "prompt_type": "gen",
        }
        with self._api() as c:
            resp = c.post("/api/generate/v2/", json=payload)
        if resp.status_code == 402:
            raise ProviderError("suno generate 402: out of credits on this account")
        if resp.status_code >= 400:
            raise ProviderError(f"suno generate {resp.status_code}: {resp.text[:200]}")
        data = resp.json() or {}
        raw_clips = data.get("clips") or []
        if not raw_clips:
            raise ProviderError("suno generate returned no clips")
        clips = [
            {
                "clip_id": rc.get("id", ""),
                "audio_url": rc.get("audio_url") or "",
                "duration_sec": float((rc.get("metadata") or {}).get("duration") or 0),
                "title": rc.get("title", ""),
            }
            for rc in raw_clips
            if rc.get("id")
        ]
        return {"task_id": data.get("id") or clips[0]["clip_id"], "status": "queued",
                "clips": clips}

    def get_task(self, *, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        ids = [c.get("clip_id") for c in state.get("clips", []) if c.get("clip_id")]
        if not ids:
            return {"status": "failed", "clips": []}
        with self._api() as c:
            resp = c.get("/api/feed/v2", params={"ids": ",".join(ids)})
        if resp.status_code >= 400:
            raise ProviderError(f"suno feed {resp.status_code}")
        items = (resp.json() or {}).get("clips")
        if items is None:
            items = resp.json() if isinstance(resp.json(), list) else []
        clips = []
        statuses = []
        for it in items:
            st = (it.get("status") or "").lower()
            statuses.append(st)
            url = it.get("audio_url") or ""
            if url:
                clips.append({
                    "clip_id": it.get("id", ""),
                    "audio_url": url,
                    "duration_sec": float((it.get("metadata") or {}).get("duration") or 0),
                    "title": it.get("title", ""),
                })
        if any(s == "error" for s in statuses):
            status = "failed"
        elif statuses and all(s in {"complete", "streaming"} for s in statuses) and clips:
            status = "complete"
        else:
            status = "running"
        return {"status": status, "clips": clips or state.get("clips", [])}

    def download(self, *, clip_id: str, audio_url: str, dest: Path) -> Path:
        import httpx

        dest.parent.mkdir(parents=True, exist_ok=True)
        assert_safe_url(audio_url)
        with httpx.Client(timeout=180.0, follow_redirects=True) as c:
            resp = c.get(audio_url)
            if resp.status_code >= 400:
                raise ProviderError(f"download {resp.status_code}")
            dest.write_bytes(resp.content)
        return dest

    def extract_stems(self, *, clip_id: str, vocal_dest: Path,
                      instrumental_dest: Path) -> dict[str, Any]:
        # Let the caller split the downloaded clip via stem-mcp (keeps this
        # provider simple and avoids extra credit-consuming stem jobs).
        return {"has_stems": False}

    def separate_stems(self, *, music_task_id: str, audio_id: str,
                       vocal_dest: Path, instrumental_dest: Path,
                       max_wait_sec: int | None = None,
                       interval_sec: float | None = None) -> dict[str, Any]:
        """Run Suno's native stem split for a clip (opt-in).

        Enabled only when ``SUNO_NATIVE_STEMS=true``; otherwise raises so the
        caller falls back to ``stem-mcp.isolate``. Posts to the stem endpoint
        (configurable via ``SUNO_STEM_ENDPOINT``), polls the feed for the
        resulting vocal + instrumental stem clips, and downloads them.

        The exact internal endpoint/response shape is unofficial and may change;
        any failure raises :class:`ProviderError` for graceful fallback.
        """
        if not _flag("SUNO_NATIVE_STEMS"):
            raise ProviderError("native stems disabled (set SUNO_NATIVE_STEMS=true)")
        if not audio_id:
            raise ProviderError("native stems require a clip id")

        template = os.getenv("SUNO_STEM_ENDPOINT", "/api/gen/{clip_id}/stems/")
        path = template.format(clip_id=audio_id)
        with self._api() as c:
            resp = c.post(path, json={"clip_id": audio_id})
        if resp.status_code == 402:
            raise ProviderError("suno stems 402: out of credits on this account")
        if resp.status_code >= 400:
            raise ProviderError(f"suno stems {resp.status_code}: {resp.text[:200]}")
        data = resp.json() or {}
        stem_clips = data.get("clips") or ([data] if data.get("id") else [])
        stem_ids = [sc.get("id") for sc in stem_clips if sc.get("id")]
        if not stem_ids:
            raise ProviderError("suno stems returned no clip ids")

        deadline = time.time() + int(
            max_wait_sec if max_wait_sec is not None
            else os.getenv("SUNO_VR_MAX_WAIT_SEC", 300)
        )
        poll = float(
            interval_sec if interval_sec is not None
            else os.getenv("SUNO_VR_INTERVAL_SEC", 5)
        )

        vocal_url: str | None = None
        instrumental_url: str | None = None
        while True:
            with self._api() as c:
                r = c.get("/api/feed/v2", params={"ids": ",".join(stem_ids)})
            if r.status_code >= 400:
                raise ProviderError(f"suno stems feed {r.status_code}")
            body = r.json() or {}
            items = body.get("clips") if isinstance(body, dict) else body
            items = items or []
            ready: list[str] = []  # completed urls in clip order (for positional fallback)
            statuses: list[str] = []
            for it in items:
                statuses.append((it.get("status") or "").lower())
                url = it.get("audio_url") or ""
                if not url:
                    continue
                ready.append(url)
                meta = it.get("metadata") or {}
                label = " ".join(
                    str(x) for x in (it.get("title", ""), meta.get("type", ""),
                                     meta.get("tags", ""), meta.get("stem_type", ""))
                ).lower()
                if "instrument" in label and not instrumental_url:
                    instrumental_url = url
                elif "vocal" in label and not vocal_url:
                    vocal_url = url
            # Positional fallback when labels are absent but both stems are ready.
            if (not (vocal_url and instrumental_url)
                    and len(ready) >= 2
                    and statuses and all(s in {"complete", "streaming"} for s in statuses)):
                vocal_url, instrumental_url = ready[0], ready[1]
            if vocal_url and instrumental_url:
                break
            if any(s == "error" for s in statuses):
                raise ProviderError("suno stems failed (clip status=error)")
            if time.time() > deadline:
                raise ProviderError("suno stems timed out waiting for stems")
            time.sleep(poll)

        self.download(clip_id=audio_id, audio_url=vocal_url, dest=vocal_dest)
        self.download(clip_id=audio_id, audio_url=instrumental_url, dest=instrumental_dest)
        return {
            "has_stems": True,
            "vocal_path": str(vocal_dest),
            "instrumental_path": str(instrumental_dest),
        }

    def health(self) -> dict[str, Any]:
        """Verify the session cookie by refreshing a Clerk JWT.

        A successful refresh means the cookie is still valid. Credits are read
        best-effort from a billing endpoint (configurable, non-fatal).
        """
        try:
            self._token()
        except ProviderError as exc:
            return {"authenticated": False,
                    "detail": f"{exc} — re-export SUNO_COOKIE from suno.com"}
        result: dict[str, Any] = {"authenticated": True,
                                  "detail": "cookie valid; JWT refreshed"}
        endpoint = os.getenv("SUNO_BILLING_ENDPOINT", "/api/billing/info/")
        try:
            with self._api() as c:
                r = c.get(endpoint)
            result["billing_status"] = r.status_code
            if r.status_code == 200:
                body = r.json() or {}
                credits = body.get("total_credits_left")
                if credits is None:
                    credits = body.get("credits")
                if credits is not None:
                    result["credits"] = credits
        except Exception:  # noqa: BLE001 - credits are advisory only
            pass
        return result


def get_provider() -> Any:
    """Return the active suno provider, falling back to mock when offline.

    Selection order:
      1. mock mode (tests / no keys) -> MockProvider
      2. SUNO_MODE=self_hosted + SUNO_COOKIE -> SelfHostedSunoProvider (PRIMARY:
         your own suno.com subscription via the token-replay wrapper)
      3. SUNO_API_BASE + SUNO_API_KEY -> HttpSunoProvider (sunoapi.org fallback)
      4. otherwise -> MockProvider
    """
    if mock_enabled():
        return MockProvider()

    # Primary: your self-hosted suno.com wrapper (token replay).
    mode = os.getenv("SUNO_MODE", "").strip().lower()
    if mode == "self_hosted" or os.getenv("SUNO_COOKIE"):
        if not require_env("SUNO_COOKIE"):
            return SelfHostedSunoProvider(os.environ["SUNO_COOKIE"])

    # Fallback: third-party sunoapi.org gateway.
    missing = require_env("SUNO_API_BASE", "SUNO_API_KEY")
    if missing:
        return MockProvider()
    return HttpSunoProvider(os.environ["SUNO_API_BASE"], os.environ["SUNO_API_KEY"])
