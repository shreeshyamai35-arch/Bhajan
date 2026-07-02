"""audio-mcp package (M1).

Analysis, mixing, and mastering on CPU. Re-exports the pure-Python core tool
functions so agents and tests can call them in-process without the mcp package.
"""

from __future__ import annotations

from .core import (
    audio_align,
    audio_analyze,
    audio_master,
    audio_mix,
    audio_transcribe,
    audio_vocal_chain,
)

__all__ = [
    "audio_align",
    "audio_vocal_chain",
    "audio_mix",
    "audio_master",
    "audio_analyze",
    "audio_transcribe",
]
