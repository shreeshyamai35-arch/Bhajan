"""suno-mcp (M4) — music generation, API-first.

Re-exports the pure-Python tool functions implemented in ``core`` so they can
be called in-process by tests and agents without importing the mcp package.
"""

from __future__ import annotations

from .core import (
    suno_download,
    suno_extract_stems,
    suno_generate,
    suno_get_task,
    suno_health,
)

__all__ = [
    "suno_generate",
    "suno_get_task",
    "suno_download",
    "suno_extract_stems",
    "suno_health",
]
