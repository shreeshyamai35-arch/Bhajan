"""suno-mcp core tool functions (pure Python, no mcp dependency).

Tool names map to functions with dots replaced by underscores:
    suno.generate       -> suno_generate
    suno.get_task       -> suno_get_task
    suno.download       -> suno_download
    suno.extract_stems  -> suno_extract_stems

Long operations (generate) return a ``task_id``; clients poll ``suno_get_task``.
Task state is kept in a module-level dict (and mirrored to a small JSON file)
so a subsequent ``get_task`` returns the stored clips. In mock mode tasks
complete immediately and audio is synthesised on download / stem extraction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..common import ProviderError, err, ok, safe_call
from ...logging_utils import get_logger
from .providers import get_provider

logger = get_logger("mcp.suno")

# task_id -> {"status": str, "clips": [...], "provider": str}
_TASKS: dict[str, dict[str, Any]] = {}
# clip_id -> {"audio_url": str, "title": str, "duration_sec": int}
_CLIPS: dict[str, dict[str, Any]] = {}


def _tasks_file() -> Path:
    from ...config import get_settings

    p = get_settings().runs_dir / "_suno_tasks.json"
    return p


def _persist() -> None:
    """Best-effort mirror of task state to disk (never fatal)."""
    try:
        path = _tasks_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tasks": _TASKS, "clips": _CLIPS}),
                        encoding="utf-8")
    except Exception:  # noqa: BLE001 - persistence is advisory only
        pass


def _register_clips(clips: list[dict[str, Any]], task_id: str | None = None) -> None:
    for clip in clips:
        cid = clip.get("clip_id")
        if cid:
            record = {
                "audio_url": clip.get("audio_url", ""),
                "title": clip.get("title", ""),
                "duration_sec": clip.get("duration_sec", 0),
            }
            # Preserve a previously stored parent task id when re-registering.
            if task_id:
                record["task_id"] = task_id
            elif cid in _CLIPS and _CLIPS[cid].get("task_id"):
                record["task_id"] = _CLIPS[cid]["task_id"]
            _CLIPS[cid] = record


def suno_health() -> dict[str, Any]:
    """Check the active provider's auth/credentials without generating audio.

    For the self-hosted provider this refreshes the Clerk JWT from your cookie,
    answering "is my Suno session still valid?". Returns an ``authenticated``
    flag plus best-effort credit info; never raises.
    """

    def _run() -> dict[str, Any]:
        provider = get_provider()
        info = provider.health()
        return ok(provider=provider.name, **info)

    return safe_call(_run, "suno.health")


def suno_generate(lyrics: str, style_prompt: str = "", model: str = "suno-v5.5",
                  make_instrumental: bool = False, candidates: int = 2,
                  duration_hint_sec: int = 240) -> dict[str, Any]:
    """Start a music generation task. Returns a ``task_id`` to poll."""

    def _run() -> dict[str, Any]:
        provider = get_provider()
        result = provider.generate(
            lyrics=lyrics,
            style_prompt=style_prompt,
            model=model,
            make_instrumental=make_instrumental,
            candidates=candidates,
            duration_hint_sec=duration_hint_sec,
        )
        task_id = result["task_id"]
        clips = result.get("clips", [])
        _TASKS[task_id] = {
            "status": result.get("status", "queued"),
            "clips": clips,
            "provider": provider.name,
        }
        _register_clips(clips, task_id=task_id)
        _persist()
        return ok(task_id=task_id, candidates=max(1, int(candidates)))

    return safe_call(_run, "suno.generate")


def suno_get_task(task_id: str) -> dict[str, Any]:
    """Poll a generation task. Returns status and (when complete) clips."""

    def _run() -> dict[str, Any]:
        state = _TASKS.get(task_id)
        if state is None:
            return err("unknown task_id", status="failed", clips=[])
        provider = get_provider()
        result = provider.get_task(task_id=task_id, state=state)
        status = result.get("status", state.get("status", "running"))
        clips = result.get("clips", state.get("clips", []))
        state["status"] = status
        state["clips"] = clips
        _register_clips(clips, task_id=task_id)
        _persist()
        return ok(status=status, clips=clips)

    return safe_call(_run, "suno.get_task")


def suno_download(clip_id: str, dest_dir: str) -> dict[str, Any]:
    """Download a generated clip into ``dest_dir`` as ``clip.mp3``."""

    def _run() -> dict[str, Any]:
        provider = get_provider()
        clip = _CLIPS.get(clip_id, {})
        audio_url = clip.get("audio_url", "")
        dest = Path(dest_dir) / "clip.mp3"
        out = provider.download(clip_id=clip_id, audio_url=audio_url, dest=dest)
        return ok(audio_path=str(out))

    return safe_call(_run, "suno.download")


def suno_extract_stems(clip_id: str, dest_dir: str) -> dict[str, Any]:
    """Extract guide vocal + instrumental stems for a clip.

    Prefers the gateway's own stems. If the gateway lacks stem support
    (``has_stems`` false in real mode), returns the flag so the caller can fall
    back to ``stem-mcp.isolate`` on the downloaded clip (not imported here).
    """

    def _run() -> dict[str, Any]:
        provider = get_provider()
        dest = Path(dest_dir)
        vocal_dest = dest / "guide_vocal.wav"
        instrumental_dest = dest / "instrumental.wav"

        # Real provider path: use sunoapi.org vocal-removal when we know the
        # parent music task id. On any failure, fall back gracefully (the caller
        # then runs stem-mcp.isolate on the downloaded clip) — never crash.
        separate = getattr(provider, "separate_stems", None)
        music_task_id = (_CLIPS.get(clip_id) or {}).get("task_id")
        if separate is not None and music_task_id:
            try:
                info = separate(
                    music_task_id=music_task_id,
                    audio_id=clip_id,
                    vocal_dest=vocal_dest,
                    instrumental_dest=instrumental_dest,
                )
            except ProviderError as exc:
                logger.warning("suno vocal-removal failed (%s); falling back to stem-mcp", exc)
                info = {"has_stems": False}
            if info.get("has_stems"):
                return ok(
                    vocal_path=str(vocal_dest),
                    instrumental_path=str(instrumental_dest),
                    has_stems=True,
                    extra_stems={},
                )
            return ok(
                vocal_path=None,
                instrumental_path=None,
                has_stems=False,
                extra_stems={},
                fallback="stem-mcp.isolate",
            )

        info = provider.extract_stems(
            clip_id=clip_id,
            vocal_dest=vocal_dest,
            instrumental_dest=instrumental_dest,
        )
        if not info.get("has_stems", True):
            # Gateway has no stems — signal caller to use stem-mcp fallback.
            return ok(
                vocal_path=None,
                instrumental_path=None,
                has_stems=False,
                extra_stems={},
                fallback="stem-mcp.isolate",
            )
        return ok(
            vocal_path=str(vocal_dest),
            instrumental_path=str(instrumental_dest),
            has_stems=True,
            extra_stems={},
        )

    return safe_call(_run, "suno.extract_stems")
