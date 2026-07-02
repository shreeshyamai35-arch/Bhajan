"""Shared utilities for all MCP servers.

Convention (docs/MCP_SERVERS.md): every tool returns
    { "ok": bool, "error": str | null, ...payload }
Long operations return a ``task_id``; clients poll a ``get_*`` tool.

Providers are swappable behind small interfaces so the pipeline runs CPU-only
and offline (mock mode) when no cloud keys are present.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse
from typing import Any, Callable

from ..logging_utils import get_logger

logger = get_logger("mcp")


def ok(**payload: Any) -> dict[str, Any]:
    """Build a successful tool envelope."""
    return {"ok": True, "error": None, **payload}


def err(message: str, **payload: Any) -> dict[str, Any]:
    """Build a failed tool envelope (never include secrets)."""
    return {"ok": False, "error": message, **payload}


def mock_enabled() -> bool:
    """Mock mode: deterministic offline behaviour for tests / no-key runs."""
    if os.getenv("BHAJANFORGE_MOCK", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return False


def require_env(*names: str) -> str | None:
    """Return the first missing env var name, or None if all present."""
    for name in names:
        if not os.getenv(name):
            return name
    return None


class ProviderError(RuntimeError):
    """Raised when a cloud provider call fails irrecoverably."""


def assert_safe_url(url: str) -> str:
    """Block SSRF: only http(s), and never resolve to a private/loopback/
    link-local/metadata address (e.g. 169.254.169.254). Returns the url or
    raises ProviderError. Opt out for trusted local tunnels by setting
    BHAJANFORGE_ALLOW_LOCAL_URLS=1.
    """
    if os.getenv("BHAJANFORGE_ALLOW_LOCAL_URLS", "").strip().lower() in {"1", "true", "yes"}:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ProviderError(f"refusing non-http(s) url: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ProviderError("url has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ProviderError(f"cannot resolve host {host!r}: {exc}") from exc
    nat64 = ipaddress.ip_network("64:ff9b::/96")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # NAT64 / IPv4-mapped IPv6 embed a real IPv4 in the low 32 bits; many
        # resolvers (incl. Windows) return these for normal public hosts.
        if isinstance(ip, ipaddress.IPv6Address):
            if ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            elif ip in nat64:
                ip = ipaddress.ip_address(int(ip) & 0xFFFFFFFF)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_unspecified):
            raise ProviderError(f"refusing url resolving to non-public ip {ip}")
    return url


def safe_call(fn: Callable[[], dict[str, Any]], context: str) -> dict[str, Any]:
    """Run a provider call, converting exceptions into an error envelope."""
    try:
        return fn()
    except ProviderError as exc:
        logger.error("%s failed: %s", context, exc)
        return err(f"{context}: {exc}")
    except Exception as exc:  # noqa: BLE001 - boundary; convert to envelope
        logger.exception("%s unexpected error", context)
        return err(f"{context}: unexpected error: {exc}")
