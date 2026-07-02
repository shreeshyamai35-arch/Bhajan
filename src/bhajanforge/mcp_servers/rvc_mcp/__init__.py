"""rvc-mcp (M3) — cloud voice conversion + training.

Re-exports the pure-Python tool functions implemented in ``core`` so they can
be called in-process by tests and agents without importing the mcp package.
"""

from __future__ import annotations

from .core import (
    rvc_convert,
    rvc_detect_range,
    rvc_get_train_task,
    rvc_list_models,
    rvc_train,
)

__all__ = [
    "rvc_list_models",
    "rvc_convert",
    "rvc_train",
    "rvc_get_train_task",
    "rvc_detect_range",
]
