"""Composer Agent (M6) — music + guide vocal via suno-mcp (FR-6..FR-9).

Builds a Suno style prompt from the request + Learning File winning prompts,
generates candidates, polls to completion, downloads + extracts stems, scores
candidates and picks the best. Calls the suno-mcp core functions in-process.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from ..logging_utils import get_logger
from ..mcp_servers.suno_mcp import (
    suno_download,
    suno_extract_stems,
    suno_generate,
    suno_get_task,
)
from ..models import LyricsDoc, MusicCandidate, MusicResult, ProductionRequest

logger = get_logger("agent.composer")

_MOOD_KEY = {
    "slow-emotional": "slow_emotional",
    "celebratory": "celebratory",
    "meditative": "meditative",
}


def build_style_prompt(request: ProductionRequest, learning: dict) -> tuple[str, str | None]:
    """Merge the Learning File's winning prompt for the mood with the request."""
    mood_key = _MOOD_KEY.get(request.mood.value, "slow_emotional")
    prompts = (learning.get("music_preferences", {}) or {}).get("winning_prompts", {}) or {}
    base = (prompts.get(mood_key) or "").strip()
    detail = (
        f"Devotional {request.deity} bhajan, {request.mood.value}, "
        f"{request.taal} taal, {request.tempo} BPM, {request.language} lyrics, "
        "solo male voice, harmonium + tabla + bansuri, temple ambience."
    )
    style = f"{base} {detail}".strip() if base else detail
    return style, (mood_key if base else None)


def _poll(task_id: str, max_wait_sec: int = 600, interval_sec: int = 5) -> dict:
    """Poll suno.get_task until complete/failed or timeout."""
    deadline = time.time() + max_wait_sec
    last: dict[str, Any] = {}
    while time.time() <= deadline:
        last = suno_get_task(task_id=task_id)
        if not last.get("ok"):
            return last
        status = last.get("status")
        if status in {"complete", "failed"}:
            return last
        time.sleep(min(interval_sec, 1))  # mock completes immediately
    return last


def _score_candidate(clip: dict, target_sec: int) -> float:
    """Heuristic: closeness of duration to target (0..1)."""
    dur = float(clip.get("duration_sec") or 0)
    if dur <= 0:
        return 0.0
    diff = abs(dur - target_sec)
    return max(0.0, 1.0 - diff / max(target_sec, 1))


def _compose_from_clip(clip_path: str, request: ProductionRequest, run_id: str) -> MusicResult:
    """Use a user-provided song clip (e.g. generated on suno.com in the browser)
    instead of calling the Suno API. Splits stems locally so the rest of the
    pipeline (voice clone, mix, package) runs unchanged."""
    from .. import runs
    from ..mcp_servers.stem_mcp import stem_isolate

    src = Path(clip_path)
    if not src.exists():
        raise RuntimeError(f"SUNO_CLIP_PATH not found: {clip_path}")

    suno_dir = runs.run_dir(run_id) / "suno"
    stems_dir = runs.run_dir(run_id) / "stems"
    suno_dir.mkdir(parents=True, exist_ok=True)
    audio_path = str(suno_dir / ("byo" + (src.suffix.lower() or ".mp3")))
    shutil.copyfile(src, audio_path)

    iso = stem_isolate(input_path=audio_path, dest_dir=str(stems_dir), target="both")
    vocal_path = iso.get("vocals_path") if iso.get("ok") else None
    instrumental_path = iso.get("instrumental_path") if iso.get("ok") else None

    try:
        import soundfile as sf
        info = sf.info(audio_path)
        dur = float(info.frames) / float(info.samplerate)
    except Exception:  # noqa: BLE001
        dur = float(request.duration_target_sec)

    logger.info("Composer using provided clip %s (stems split: %s)",
                clip_path, bool(vocal_path and instrumental_path))
    cand = MusicCandidate(
        clip_id="byo", audio_path=audio_path,
        instrumental_path=instrumental_path, guide_vocal_path=vocal_path,
        duration_sec=dur, score=1.0,
    )
    return MusicResult(style_prompt_used="(user-provided clip)",
                       winning_prompt_key=None, candidates=[cand], chosen_index=0)


def compose(request: ProductionRequest, lyrics: LyricsDoc, learning: dict, run_id: str) -> MusicResult:
    from .. import runs

    # Bring-your-own-clip: skip Suno generation entirely if a clip is provided.
    byo = os.getenv("SUNO_CLIP_PATH", "").strip()
    if byo:
        return _compose_from_clip(byo, request, run_id)

    style_prompt, winning_key = build_style_prompt(request, learning)
    gen = suno_generate(
        lyrics=lyrics.as_suno_text(),
        style_prompt=style_prompt,
        model=(learning.get("music_preferences", {}) or {}).get("default_model_tag", "suno-v5.5"),
        candidates=request.candidates,
        duration_hint_sec=request.duration_target_sec,
    )
    if not gen.get("ok"):
        msg = str(gen.get("error") or "")
        if "429" in msg or "credit" in msg.lower() or "insufficient" in msg.lower():
            raise RuntimeError(
                "Music step needs Suno credits — top up at sunoapi.org, then "
                f"re-run. (Suno said: {msg})")
        raise RuntimeError(f"suno.generate failed: {msg}")

    task = _poll(gen["task_id"])
    if not task.get("ok") or task.get("status") != "complete":
        raise RuntimeError(f"suno generation did not complete: {task.get('error') or task.get('status')}")

    clips = task.get("clips", [])
    if not clips:
        raise RuntimeError("suno returned no clips")

    suno_dir = str(runs.run_dir(run_id) / "suno")
    stems_dir = str(runs.run_dir(run_id) / "stems")

    candidates: list[MusicCandidate] = []
    for clip in clips:
        clip_id = clip["clip_id"]
        dl = suno_download(clip_id=clip_id, dest_dir=suno_dir)
        audio_path = dl.get("audio_path", "") if dl.get("ok") else ""

        stems = suno_extract_stems(clip_id=clip_id, dest_dir=stems_dir)
        vocal_path = stems.get("vocal_path") if stems.get("ok") else None
        instrumental_path = stems.get("instrumental_path") if stems.get("ok") else None

        # Gateway didn't return stems (e.g. sunoapi.org) -> split the real clip locally.
        if (not vocal_path or not instrumental_path) and audio_path:
            from ..mcp_servers.stem_mcp import stem_isolate

            iso = stem_isolate(input_path=audio_path, dest_dir=stems_dir, target="both")
            if iso.get("ok"):
                vocal_path = iso.get("vocals_path")
                instrumental_path = iso.get("instrumental_path")

        candidates.append(
            MusicCandidate(
                clip_id=clip_id,
                audio_path=audio_path,
                instrumental_path=instrumental_path,
                guide_vocal_path=vocal_path,
                duration_sec=float(clip.get("duration_sec") or 0),
                score=_score_candidate(clip, request.duration_target_sec),
            )
        )

    chosen_index = max(range(len(candidates)), key=lambda i: candidates[i].score or 0.0)
    return MusicResult(
        style_prompt_used=style_prompt,
        winning_prompt_key=winning_key,
        candidates=candidates,
        chosen_index=chosen_index,
    )


def composer_node(state: dict) -> dict:
    request: ProductionRequest = state["request"]
    lyrics: LyricsDoc = state["lyrics"]
    learning: dict = state.get("learning", {})
    result = compose(request, lyrics, learning, state["run_id"])

    artifacts = dict(state.get("artifacts", {}))
    chosen = result.chosen
    if chosen.instrumental_path:
        artifacts["instrumental"] = chosen.instrumental_path
    if chosen.guide_vocal_path:
        artifacts["guide_vocal"] = chosen.guide_vocal_path
    logger.info("Composed %d candidate(s); chose #%d", len(result.candidates), result.chosen_index)
    return {"music": result, "artifacts": artifacts}
