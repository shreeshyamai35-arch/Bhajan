"""LLM abstraction for BhajanForge agents.

Agents use ``get_llm()`` for text generation (lyrics drafting, metadata,
perceptual judging). In mock / offline mode a deterministic ``MockLLM`` is used
so the whole pipeline runs without any provider key. When ``LLM_API_KEY`` is set
a real provider (OpenAI/Anthropic-compatible) is called over httpx.

The optional ``generate_image`` helper raises in mock mode; the Packager falls
back to a thumbnail prompt file when it is unavailable.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .config import get_settings
from .logging_utils import get_logger

logger = get_logger("llm")


class MockLLM:
    """Deterministic, offline LLM stand-in (no network)."""

    name = "mock"

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        # Deterministic, generic devotional completion. Agents that need
        # structure use template paths in mock mode rather than parsing this.
        return "Jai Shree Shyam. " + (prompt[:64].replace("\n", " "))

    def complete_json(self, prompt: str, system: Optional[str] = None) -> dict[str, Any]:
        return {}


class HttpLLM:
    """OpenAI-compatible chat completions over httpx (lazy import)."""

    name = "api"

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = model or "gpt-4o"
        self.base_url = (base_url or os.getenv("LLM_API_BASE") or "https://api.openai.com/v1").rstrip("/")

    # HTTP status codes that are worth retrying (transient / throttling).
    RETRY_STATUS = (429, 500, 502, 503)
    MAX_ATTEMPTS = 4

    def complete(self, prompt: str, system: Optional[str] = None) -> str:  # pragma: no cover - network
        import time

        import httpx

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        last_exc: Exception | None = None
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "messages": messages, "temperature": 0.7},
                    timeout=120.0,
                )
            except httpx.TransportError as exc:  # network blip — retry
                last_exc = exc
                wait = 2 ** attempt
                logger.warning("LLM transport error (%s); retry in %ss", exc, wait)
                time.sleep(wait)
                continue
            if resp.status_code in self.RETRY_STATUS:
                last_exc = httpx.HTTPStatusError(
                    f"transient {resp.status_code}", request=resp.request, response=resp
                )
                # Don't sleep after the final attempt.
                if attempt < self.MAX_ATTEMPTS - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        "LLM transient error (%s); retry %d/%d in %ss",
                        resp.status_code, attempt + 1, self.MAX_ATTEMPTS, wait,
                    )
                    time.sleep(wait)
                continue
            resp.raise_for_status()  # non-retryable HTTP errors raise immediately
            return resp.json()["choices"][0]["message"]["content"]
        if last_exc:
            raise last_exc
        raise RuntimeError("LLM call failed after retries")

    def complete_json(self, prompt: str, system: Optional[str] = None) -> dict[str, Any]:  # pragma: no cover
        raw = self.complete(prompt + "\n\nRespond with ONLY valid JSON.", system)
        try:
            return json.loads(raw)
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if 0 <= start < end:
                try:
                    return json.loads(raw[start : end + 1])
                except Exception:
                    return {}
            return {}


class BedrockLLM:
    """Amazon Bedrock via the Converse API using a long-term bearer token
    (``AWS_BEARER_TOKEN_BEDROCK`` / ``LLM_API_KEY``). No AWS SDK required — a
    plain HTTPS call with ``Authorization: Bearer <token>``.
    """

    name = "bedrock"

    def __init__(self, token: str, model: str, region: str | None = None) -> None:
        self.token = token
        # A sensible default; override with LLM_MODEL to match your enabled access.
        self.model = model or "anthropic.claude-3-5-sonnet-20241022-v2:0"
        self.region = region or os.getenv("AWS_REGION") or "us-east-1"
        self.base_url = f"https://bedrock-runtime.{self.region}.amazonaws.com"

    def complete(self, prompt: str, system: Optional[str] = None) -> str:  # pragma: no cover - network
        import time

        import httpx

        body: dict[str, Any] = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 2000, "temperature": 0.7},
        }
        if system:
            body["system"] = [{"text": system}]
        url = f"{self.base_url}/model/{self.model}/converse"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        last_exc: Exception | None = None
        for attempt in range(5):
            resp = httpx.post(url, headers=headers, json=body, timeout=120.0)
            if resp.status_code in (429, 503):
                wait = 2 ** attempt
                logger.warning("Bedrock throttled (%s); retry in %ss", resp.status_code, wait)
                time.sleep(wait)
                last_exc = httpx.HTTPStatusError("throttled", request=resp.request, response=resp)
                continue
            resp.raise_for_status()
            data = resp.json()
            parts = data.get("output", {}).get("message", {}).get("content", [])
            return "".join(p.get("text", "") for p in parts)
        if last_exc:
            raise last_exc
        raise RuntimeError("Bedrock call failed")

    def complete_json(self, prompt: str, system: Optional[str] = None) -> dict[str, Any]:  # pragma: no cover
        raw = self.complete(prompt + "\n\nRespond with ONLY valid JSON.", system)
        try:
            return json.loads(raw)
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if 0 <= start < end:
                try:
                    return json.loads(raw[start : end + 1])
                except Exception:
                    return {}
            return {}


def get_llm() -> Any:
    """Return the active LLM, falling back to the mock when offline."""
    settings = get_settings()
    api_key = os.getenv("LLM_API_KEY")
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if api_key and not settings.is_mock():
        if provider == "bedrock":
            logger.info("Using Amazon Bedrock LLM (model=%s)", settings.llm_model or "default")
            return BedrockLLM(api_key, settings.llm_model, os.getenv("AWS_REGION"))
        logger.info("Using cloud LLM (model=%s)", settings.llm_model or "default")
        return HttpLLM(api_key, settings.llm_model, os.getenv("LLM_API_BASE"))
    return MockLLM()


def generate_image(prompt: str, out_path: str) -> str:  # pragma: no cover - optional
    """Generate cover art via a configured image model. Raises if unavailable."""
    if get_settings().is_mock() or not (os.getenv("IMAGE_MODEL") or os.getenv("IMAGE_PROVIDER")):
        raise RuntimeError("no image model configured")
    raise NotImplementedError("image generation backend not wired")
