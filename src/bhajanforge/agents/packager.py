"""Packager Agent (M8) — package a finished bhajan and save it locally.

Implements FR-20 / FR-21 / FR-21b / FR-22 and Acceptance Criterion AC-7.

Behaviour (skills/publish.md):
  * Generate SEO metadata (title / description / tags) via the LLM helper if it
    exists, else deterministic templates. The description ALWAYS embeds the full
    lyrics plus the mandatory "tick the synthetic/AI-altered content box" reminder
    required by R2.3 / FR-21b.
  * Produce artwork: a real cover.png when an image model is configured, otherwise
    a thumbnail_prompt.txt describing the cover to generate manually.
  * Optionally render a static-image lyric video to video.mp4 — only when
    MAKE_VIDEO is enabled AND ffmpeg is on PATH. Skipped gracefully otherwise.
  * Save the full bundle to OUTPUT_DIR/{date}_{slug}/ (run_id is already
    "{date}_{slug}"). Nothing is uploaded by default (PUBLISH_TARGET=local).
  * Upload to YouTube ONLY when the request opts in, the PUBLISH_TARGET env is
    "youtube", and valid creds exist — and even then the AI-disclosure flag MUST
    be set. Missing creds => save locally + status "needs_human". The disclosure
    flag is never omitted on upload.

This module guards every optional dependency (llm helper, ffmpeg, the YouTube
client) so it works on a CPU-only, offline machine where those may be absent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..config import get_settings
from ..models import (
    LyricLine,
    LyricsDoc,
    LyricSection,
    ProductionRequest,
    PublishResult,
)
from .. import runs

# --------------------------------------------------------------------------
# Mandatory R2.3 / FR-21b reminder. Kept as a module constant so tests and the
# CLI can assert/locate it. NEVER drop this from description.txt.
# --------------------------------------------------------------------------
AI_DISCLOSURE_REMINDER = (
    "IMPORTANT — MANUAL UPLOAD REMINDER (R2.3): This track contains "
    "AI-generated / AI-altered audio. When uploading to YouTube you MUST tick "
    "the \"Altered or synthetic content\" disclosure box in the upload flow. "
    "Do not publish without enabling that setting."
)


# --------------------------------------------------------------------------
# Metadata generation
# --------------------------------------------------------------------------


def _lyrics_text(lyrics: LyricsDoc) -> str:
    """Flatten lyrics to plain text (prefer as_suno_text, fall back to join)."""
    try:
        text = lyrics.as_suno_text()
        if text and text.strip():
            return text
    except Exception:
        pass
    blocks: list[str] = []
    for section in getattr(lyrics, "sections", []) or []:
        lines = "\n".join(line.text for line in section.lines)
        blocks.append(lines)
    return "\n\n".join(blocks)


def _template_metadata(
    request: ProductionRequest, lyrics: LyricsDoc
) -> tuple[str, str, list[str]]:
    """Deterministic, offline-safe metadata. Used when no LLM is available."""
    deity = (request.deity or "Khatu Shyam").strip()
    theme = (request.theme or "Bhajan").strip()
    theme_title = theme.title()

    title = f"{deity} Bhajan | {theme_title} | Devotional Darshan"

    lyric_body = _lyrics_text(lyrics)
    hashtags = " ".join(
        [
            "#bhajan",
            "#devotional",
            f"#{_hashtag(deity)}",
            f"#{_hashtag(theme)}",
            "#bhakti",
            "#shyambaba",
        ]
    )
    description = (
        f"{title}\n\n"
        f"A devotional {theme} bhajan dedicated to {deity}.\n\n"
        f"--- Lyrics ---\n{lyric_body}\n\n"
        f"{hashtags}\n\n"
        f"{AI_DISCLOSURE_REMINDER}\n"
    )

    tags = _dedupe(
        [
            "bhajan",
            "devotional",
            "bhakti",
            deity.lower(),
            "khatu shyam",
            "shyam baba",
            *[w for w in theme.lower().split() if w],
            "aarti",
            "kirtan",
        ]
    )
    return title, description, tags


def _hashtag(text: str) -> str:
    return "".join(ch for ch in text.title() if ch.isalnum()) or "Bhajan"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def _generate_metadata(
    request: ProductionRequest, lyrics: LyricsDoc, settings
) -> tuple[str, str, list[str]]:
    """Use the LLM helper when present + online; otherwise template fallback.

    The llm module is owned by another worker and may not exist yet, so the
    import is fully defensive. Offline / mock mode always uses templates.
    """
    title, description, tags = _template_metadata(request, lyrics)

    if settings.is_mock():
        return title, description, tags

    try:  # the helper may not exist yet — never hard-depend on it
        from ..llm import get_llm  # type: ignore
    except Exception:
        return title, description, tags

    try:
        llm = get_llm()
        lyric_body = _lyrics_text(lyrics)
        prompt = (
            "Write an SEO-friendly YouTube title, description and comma-separated "
            "tags for a Hindu devotional bhajan.\n"
            f"Deity: {request.deity}\nTheme: {request.theme}\n"
            f"Lyrics:\n{lyric_body}\n"
            "Return JSON with keys: title, description, tags (list)."
        )
        raw = llm.complete(prompt) if hasattr(llm, "complete") else llm(prompt)
        data = json.loads(raw) if isinstance(raw, str) else raw
        title = str(data.get("title") or title)
        gen_desc = str(data.get("description") or "")
        gen_tags = data.get("tags") or tags
        if isinstance(gen_tags, str):
            gen_tags = [t.strip() for t in gen_tags.split(",")]

        # Always (re)embed lyrics + the mandatory disclosure reminder.
        description = (
            f"{gen_desc}\n\n--- Lyrics ---\n{lyric_body}\n\n{AI_DISCLOSURE_REMINDER}\n"
        )
        tags = _dedupe([str(t) for t in gen_tags])
    except Exception:
        # Any LLM failure falls back to the safe deterministic template.
        return _template_metadata(request, lyrics)

    return title, description, tags


# --------------------------------------------------------------------------
# Artwork + video
# --------------------------------------------------------------------------


def _image_model_available(settings) -> bool:
    """True only when a real image model is configured and we're online."""
    if settings.is_mock():
        return False
    return bool(os.getenv("IMAGE_MODEL") or os.getenv("IMAGE_PROVIDER"))


def _write_thumbnail_prompt(
    bundle: Path, request: ProductionRequest, title: str
) -> Path:
    prompt = (
        f"Devotional cover art for a {request.deity} bhajan titled '{title}'.\n"
        f"Theme: {request.theme}. Serene, reverent, warm golden temple lighting, "
        f"traditional Indian devotional aesthetic, soft glow, no text overlays, "
        f"16:9 thumbnail composition.\n"
    )
    path = bundle / "thumbnail_prompt.txt"
    path.write_text(prompt, encoding="utf-8")
    return path


def _make_cover(bundle: Path, title: str) -> Optional[Path]:
    """Attempt to create cover.png via a configured image model.

    Guarded: any failure returns None so callers can fall back to a prompt file.
    """
    try:  # image helper is optional and owned elsewhere
        from ..llm import generate_image  # type: ignore
    except Exception:
        return None
    try:
        out = bundle / "cover.png"
        generate_image(title, str(out))
        if out.exists() and out.stat().st_size > 0:
            return out
    except Exception:
        return None
    return None


def _maybe_render_video(
    bundle: Path, master: Path, cover: Optional[Path], settings
) -> Optional[str]:
    """Render a simple static-image video — only if enabled AND ffmpeg exists."""
    if not settings.make_video:
        return None
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    image = cover if (cover and cover.exists()) else None
    out = bundle / "video.mp4"
    try:
        if image is not None:
            cmd = [
                ffmpeg, "-y", "-loop", "1", "-i", str(image),
                "-i", str(master), "-c:v", "libx264", "-tune", "stillimage",
                "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
                "-shortest", str(out),
            ]
        else:
            # No image: synthesize a plain colour background sized to the audio.
            cmd = [
                ffmpeg, "-y", "-f", "lavfi", "-i",
                "color=c=black:s=1280x720:r=2", "-i", str(master),
                "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-shortest", str(out),
            ]
        subprocess.run(cmd, check=True, capture_output=True)
        if out.exists() and out.stat().st_size > 0:
            return str(out)
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------
# YouTube upload (opt-in only, never default)
# --------------------------------------------------------------------------


def _youtube_creds_present() -> bool:
    token = os.getenv("YOUTUBE_TOKEN_FILE") or os.getenv("YOUTUBE_CREDENTIALS_FILE")
    if token and Path(token).exists():
        return True
    return bool(
        os.getenv("YOUTUBE_CLIENT_ID")
        and os.getenv("YOUTUBE_CLIENT_SECRET")
        and os.getenv("YOUTUBE_REFRESH_TOKEN")
    )


def _try_youtube_upload(
    video_path: str, title: str, description: str, tags: list[str]
) -> Optional[str]:
    """Attempt an upload with the AI-disclosure flag set. Returns video id or None.

    The google client is optional and may be absent; guard the import.
    """
    try:
        from googleapiclient.discovery import build  # type: ignore  # noqa: F401
    except Exception:
        return None
    try:
        # Real upload wiring lives behind the (optional) youtube client. We never
        # reach a successful upload without ai_disclosure_set=True (see caller).
        # Placeholder: the concrete client is provided by another module.
        from ..youtube import upload_video  # type: ignore

        return upload_video(
            video_path,
            title=title,
            description=description,
            tags=tags,
            ai_disclosure_set=True,  # R2.3 — mandatory, never omit
        )
    except Exception:
        return None


# --------------------------------------------------------------------------
# Bundle writer
# --------------------------------------------------------------------------


def _write_bundle(
    bundle: Path,
    master: Path,
    title: str,
    description: str,
    tags: list[str],
    quality: Optional[dict],
    settings,
    request: ProductionRequest,
) -> dict:
    """Write the full local bundle. Returns paths for thumbnail/cover/video."""
    bundle.mkdir(parents=True, exist_ok=True)

    # master.wav (copy from artifacts)
    if master.exists():
        shutil.copy2(str(master), str(bundle / "master.wav"))

    (bundle / "title.txt").write_text(title, encoding="utf-8")
    (bundle / "description.txt").write_text(description, encoding="utf-8")
    (bundle / "tags.txt").write_text("\n".join(tags), encoding="utf-8")

    # quality_report.json
    (bundle / "quality_report.json").write_text(
        json.dumps(quality or {}, indent=2, default=str), encoding="utf-8"
    )

    # Artwork: real cover.png when possible, else a prompt file.
    cover: Optional[Path] = None
    thumbnail_path: Optional[str] = None
    if _image_model_available(settings):
        cover = _make_cover(bundle, title)
    if cover is not None:
        thumbnail_path = str(cover)
    else:
        thumbnail_path = str(_write_thumbnail_prompt(bundle, request, title))

    # Optional video.
    video_path = _maybe_render_video(bundle, bundle / "master.wav", cover, settings)

    return {
        "thumbnail_path": thumbnail_path,
        "cover": cover,
        "video_path": video_path,
    }


def _coerce_quality(quality) -> Optional[dict]:
    if quality is None:
        return None
    if isinstance(quality, dict):
        return quality
    if hasattr(quality, "model_dump"):
        return quality.model_dump()
    try:
        return dict(quality)
    except Exception:
        return {}


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def package(state: dict) -> "PublishResult":
    """Package a finished bhajan and save it locally (FR-20/21/21b/22, AC-7).

    `state` keys: run_id (str), request (ProductionRequest), lyrics (LyricsDoc),
    artifacts (dict with at least artifacts["master"]). Optional: quality, scores.
    """
    settings = get_settings()

    run_id: str = state["run_id"]
    request: ProductionRequest = state["request"]
    lyrics: LyricsDoc = state["lyrics"]
    artifacts: dict = state.get("artifacts", {}) or {}
    master = Path(str(artifacts.get("master", "")))
    quality = _coerce_quality(state.get("quality"))

    # 1. Metadata
    title, description, tags = _generate_metadata(request, lyrics, settings)

    # 2/3/4. Bundle dir = OUTPUT_DIR/{date}_{slug}/  (run_id is already date_slug)
    bundle = settings.output_dir / run_id
    written = _write_bundle(
        bundle, master, title, description, tags, quality, settings, request
    )

    # 5. Upload decision — local by default, opt-in YouTube only.
    status = "saved_local"
    youtube_video_id: Optional[str] = None
    youtube_url: Optional[str] = None
    env_target = os.getenv("PUBLISH_TARGET", settings.publish_target).strip().lower()
    wants_youtube = request.publish_target == "youtube" and env_target == "youtube"

    if wants_youtube:
        if _youtube_creds_present() and written["video_path"]:
            youtube_video_id = _try_youtube_upload(
                written["video_path"], title, description, tags
            )
            if youtube_video_id:
                status = "published"
                youtube_url = f"https://youtu.be/{youtube_video_id}"
            else:
                # Upload could not complete safely -> keep local, ask a human.
                status = "needs_human"
        else:
            # Opted in but no creds / no video -> save locally, escalate.
            status = "needs_human"

    result = PublishResult(
        title=title,
        description=description,
        tags=tags,
        thumbnail_path=written["thumbnail_path"],
        video_path=written["video_path"],
        output_dir=str(bundle),
        youtube_video_id=youtube_video_id,
        youtube_url=youtube_url,
        ai_disclosure_set=True,  # always true; mandatory IF uploaded (R2.3)
        status=status,
    )

    # 6. Update the run manifest (idempotent — create if it doesn't exist yet).
    _update_manifest(run_id, request, str(bundle), status)

    return result


def _update_manifest(
    run_id: str, request: ProductionRequest, bundle: str, status: str
) -> None:
    try:
        manifest = runs.load_manifest(run_id)
    except Exception:
        manifest = runs.init_run(request, run_id=run_id)
    manifest.artifacts["output_dir"] = bundle
    decision = status if status in {"needs_human", "published"} else "saved_local"
    manifest.decision = decision  # type: ignore[assignment]
    try:
        runs.save_manifest(manifest)
    except Exception:
        pass


def repackage(run_id: str) -> str:
    """Load a run's manifest and re-run packaging for it. Returns a summary."""
    manifest = runs.load_manifest(run_id)
    request = manifest.request

    master = (
        manifest.artifacts.get("master")
        or manifest.artifacts.get("master_path")
        or ""
    )

    # Manifests don't persist lyrics — reconstruct a minimal devotional doc.
    lyrics = _fallback_lyrics(request)

    state = {
        "run_id": run_id,
        "request": request,
        "lyrics": lyrics,
        "artifacts": {"master": master},
        "quality": manifest.scores or {},
    }
    result = package(state)

    return (
        f"Repackaged run '{run_id}': status={result.status}, "
        f"saved to {result.output_dir}. "
        f"Title: {result.title}. "
        f"Thumbnail: {result.thumbnail_path or 'none'}. "
        f"Video: {result.video_path or 'none'}. "
        f"Uploaded: {'yes (' + result.youtube_video_id + ')' if result.youtube_video_id else 'no'}."
    )


def _fallback_lyrics(request: ProductionRequest) -> LyricsDoc:
    deity = request.deity or "Khatu Shyam"
    return LyricsDoc(
        title_working=f"{deity} Bhajan",
        language=request.language,
        sections=[
            LyricSection(
                name="mukhda",
                lines=[LyricLine(text=f"Bolo {deity} ki jai")],
            )
        ],
    )
