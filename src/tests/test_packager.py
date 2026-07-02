"""M8 packager tests — offline, BHAJANFORGE_MOCK=1, no network.

Verifies FR-20/21/21b/22 and AC-7: a finished bhajan is packaged and SAVED
LOCALLY (never uploaded by default), the bundle contains the expected files,
the description carries the mandatory AI-disclosure reminder + lyric content,
and the AI-disclosure flag is set.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from bhajanforge.agents import packager
from bhajanforge.models import (
    LyricLine,
    LyricSection,
    LyricsDoc,
    ProductionRequest,
)

SR = 48000
RUN_ID = "2026-06-21_morning-darshan"


class _StubSettings:
    """Minimal settings stub pointing all paths at a tmp dir (offline/mock)."""

    def __init__(self, root: Path):
        self._root = root

    @property
    def output_dir(self) -> Path:
        return self._root / "output"

    @property
    def runs_dir(self) -> Path:
        return self._root / "runs"

    @property
    def make_video(self) -> bool:
        return False

    @property
    def publish_target(self) -> str:
        return "local"

    def is_mock(self) -> bool:
        return True


def _make_master(tmp_path: Path) -> str:
    t = np.linspace(0, 1.0, SR, endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    p = tmp_path / "master.wav"
    sf.write(str(p), sig, SR, subtype="PCM_16")
    return str(p)


def _lyrics() -> LyricsDoc:
    return LyricsDoc(
        title_working="Morning Darshan",
        sections=[
            LyricSection(
                name="mukhda",
                lines=[LyricLine(text="Shyam Shyam bolo sara din")],
            ),
            LyricSection(
                name="antara",
                lines=[LyricLine(text="Khatu wale Shyam tere darshan ko aaye")],
            ),
        ],
    )


def _patch_settings(monkeypatch, tmp_path: Path) -> _StubSettings:
    stub = _StubSettings(tmp_path)
    # Patch both the packager-local import and the runs module import.
    monkeypatch.setattr("bhajanforge.agents.packager.get_settings", lambda: stub)
    monkeypatch.setattr("bhajanforge.runs.get_settings", lambda: stub)
    # Ensure no opt-in upload can ever be triggered.
    monkeypatch.setenv("PUBLISH_TARGET", "local")
    monkeypatch.setenv("BHAJANFORGE_MOCK", "1")
    return stub


def _build_state(tmp_path: Path) -> dict:
    return {
        "run_id": RUN_ID,
        "request": ProductionRequest(theme="morning darshan"),
        "lyrics": _lyrics(),
        "artifacts": {"master": _make_master(tmp_path)},
        "quality": {"score": 96.0, "passed": True},
    }


def test_package_saves_local_bundle(tmp_path, monkeypatch):
    stub = _patch_settings(monkeypatch, tmp_path)
    state = _build_state(tmp_path)

    result = packager.package(state)

    # Status + disclosure flag.
    assert result.status in {"saved_local", "draft"}
    assert result.ai_disclosure_set is True

    # Bundle dir exists at OUTPUT_DIR/{run_id}.
    bundle = stub.output_dir / RUN_ID
    assert Path(result.output_dir) == bundle
    assert bundle.is_dir()

    # Required files present.
    for name in (
        "master.wav",
        "title.txt",
        "description.txt",
        "tags.txt",
        "quality_report.json",
    ):
        assert (bundle / name).exists(), f"missing {name}"

    # Artwork: thumbnail prompt (offline) OR a rendered cover.
    assert (bundle / "thumbnail_prompt.txt").exists() or (
        bundle / "cover.png"
    ).exists()

    # description carries the AI-disclosure reminder AND lyric content.
    desc = (bundle / "description.txt").read_text(encoding="utf-8")
    assert "synthetic" in desc.lower() or "altered" in desc.lower()
    assert "Shyam Shyam bolo sara din" in desc

    # No upload happened.
    assert result.youtube_video_id is None
    assert result.youtube_url is None


def test_default_target_local_does_not_upload(tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path)
    state = _build_state(tmp_path)
    # request.publish_target defaults to "local".
    assert state["request"].publish_target == "local"

    result = packager.package(state)

    assert result.status == "saved_local"
    assert result.youtube_video_id is None
    assert result.video_path is None
    assert result.ai_disclosure_set is True


def test_manifest_updated_with_output_dir(tmp_path, monkeypatch):
    stub = _patch_settings(monkeypatch, tmp_path)
    state = _build_state(tmp_path)

    result = packager.package(state)

    from bhajanforge import runs

    manifest = runs.load_manifest(RUN_ID)
    assert manifest.artifacts.get("output_dir") == result.output_dir
    assert manifest.decision in {"saved_local", "needs_human"}


def test_repackage_reruns_from_manifest(tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path)
    state = _build_state(tmp_path)

    # First package run to create the manifest + persist the master path.
    packager.package(state)

    from bhajanforge import runs

    manifest = runs.load_manifest(RUN_ID)
    manifest.artifacts["master"] = state["artifacts"]["master"]
    runs.save_manifest(manifest)

    summary = packager.repackage(RUN_ID)
    assert RUN_ID in summary
    assert "saved" in summary.lower()
