"""stem-mcp core (M2) — stem separation.

This server is normally cloud-backed, but in mock/offline mode it synthesizes
plausible stems (low-passed "instrumental" + high-passed "vocals") so downstream
stages always have real wav files. Importing this module must NOT require mcp.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..common import err, ok, safe_call
from . import providers


def stem_isolate(
    input_path: str,
    dest_dir: str,
    target: str = "both",
    **_: Any,
) -> dict[str, Any]:
    """Separate ``input_path`` into vocals + instrumental into ``dest_dir``."""

    def _run() -> dict[str, Any]:
        src = Path(input_path)
        if not src.exists():
            return err(f"input not found: {input_path}")
        out_dir = Path(dest_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        prov = providers.select_stem_provider()
        try:
            result = prov.isolate(str(src), str(out_dir), target)
            if result is not None:
                return result
        except Exception:  # noqa: BLE001 - degrade to local synthesis
            pass

        # Local fallback synthesis (always available).
        return providers.MockStemProvider().isolate(str(src), str(out_dir), target)

    return safe_call(_run, "stem.isolate")


def stem_batch_isolate(
    input_dir: str,
    dest_dir: str,
    target: str = "vocals",
    **_: Any,
) -> dict[str, Any]:
    """Isolate every wav in ``input_dir``; return count + output paths."""

    def _run() -> dict[str, Any]:
        in_dir = Path(input_dir)
        if not in_dir.exists():
            return err(f"input_dir not found: {input_dir}")
        out_dir = Path(dest_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        wavs = sorted(
            p for p in in_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".wav", ".flac", ".mp3", ".ogg"}
        )
        outputs: list[str] = []
        for wav in wavs:
            sub = out_dir / wav.stem
            res = stem_isolate(str(wav), str(sub), target=target)
            if not res.get("ok"):
                continue
            if target == "instrumental":
                path = res.get("instrumental_path")
            else:
                path = res.get("vocals_path")
            if path:
                outputs.append(path)

        return ok(count=len(outputs), outputs=outputs)

    return safe_call(_run, "stem.batch_isolate")
