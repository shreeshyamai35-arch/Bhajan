"""Read/write the Learning File (config/learning.yaml).

Agents READ this before acting and WRITE after each run. Unknown keys are
treated as forward-compatible (never crash). See config/learning.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

from ..config import LEARNING_PATH


def _default_path() -> Path:
    """Honour a test/runtime override so we never write the repo file by mistake."""
    override = os.getenv("BHAJANFORGE_LEARNING_PATH")
    return Path(override) if override else LEARNING_PATH


def load(path: Optional[Path] = None) -> dict[str, Any]:
    path = path or _default_path()
    if not path.exists():
        return {"schema_version": 1}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"schema_version": 1}


def save(data: dict[str, Any], path: Optional[Path] = None) -> Path:
    path = path or _default_path()
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def best_voice_settings(data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = data if data is not None else load()
    return (data.get("voice_profile") or {}).get("best_settings", {}) or {}


def winning_prompt(mood_key: str, data: Optional[dict[str, Any]] = None) -> Optional[str]:
    data = data if data is not None else load()
    prompts = (data.get("music_preferences") or {}).get("winning_prompts", {}) or {}
    val = prompts.get(mood_key)
    return val.strip() if isinstance(val, str) else None


def register_voice_model(
    model_ref: str,
    provider: str,
    voice_range: dict[str, Any],
    path: Optional[Path] = None,
) -> dict[str, Any]:
    """Register a trained cloud RVC model + auto-detected range (FR-23/AC-6)."""
    data = load(path)
    vp = data.setdefault("voice_profile", {})
    vp["active_rvc_model"] = model_ref
    vp["active_rvc_provider"] = provider
    rng = vp.setdefault("range", {})
    rng.update(voice_range)
    save(data, path)
    return data


def record_run(entry: dict[str, Any], path: Optional[Path] = None) -> dict[str, Any]:
    """Append a quality_history entry and update rolling stats (FR-24)."""
    data = load(path)
    history = data.setdefault("quality_history", [])
    history.append(entry)

    stats = data.setdefault("stats", {})
    stats["total_runs"] = int(stats.get("total_runs", 0)) + 1
    if entry.get("published"):
        stats["total_published"] = int(stats.get("total_published", 0)) + 1

    scores = [h.get("judge_score") for h in history if isinstance(h.get("judge_score"), (int, float))]
    stats["avg_judge_score"] = round(sum(scores) / len(scores), 2) if scores else None

    save(data, path)
    return data


def update_best_settings(settings: dict[str, Any], path: Optional[Path] = None) -> dict[str, Any]:
    """Persist winning RVC settings discovered during a run (R5.1)."""
    data = load(path)
    vp = data.setdefault("voice_profile", {})
    best = vp.setdefault("best_settings", {})
    best.update({k: v for k, v in settings.items() if v is not None})
    save(data, path)
    return data
