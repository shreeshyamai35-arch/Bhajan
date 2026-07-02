"""stem-mcp package (M2).

Cloud-backed stem separation with an offline synthesis fallback. Re-exports the
pure-Python core tool functions for in-process use by agents and tests.
"""

from __future__ import annotations

from .core import stem_batch_isolate, stem_isolate

__all__ = ["stem_isolate", "stem_batch_isolate"]
