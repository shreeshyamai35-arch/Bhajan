"""Offline tests for suno-mcp (M4). Run with BHAJANFORGE_MOCK=1, no network."""

from __future__ import annotations

from pathlib import Path

from bhajanforge.mcp_servers.suno_mcp import (
    suno_download,
    suno_extract_stems,
    suno_generate,
    suno_get_task,
)


def test_generate_returns_task_id():
    res = suno_generate(lyrics="Shyam Shyam", style_prompt="slow bhajan",
                        candidates=2)
    assert res["ok"] is True
    assert res["error"] is None
    assert isinstance(res["task_id"], str) and res["task_id"]
    assert res["candidates"] == 2


def test_get_task_completes_with_clips():
    gen = suno_generate(lyrics="Khatu wale Shyam", style_prompt="devotional",
                        candidates=1)
    task = suno_get_task(task_id=gen["task_id"])
    assert task["ok"] is True
    assert task["status"] == "complete"
    assert len(task["clips"]) >= 1
    clip = task["clips"][0]
    assert "clip_id" in clip and "audio_url" in clip


def test_get_task_unknown_id():
    res = suno_get_task(task_id="does-not-exist")
    assert res["ok"] is False
    assert res["status"] == "failed"


def test_download_writes_file(tmp_path: Path):
    gen = suno_generate(lyrics="Bolo Shyam", candidates=1)
    task = suno_get_task(task_id=gen["task_id"])
    clip_id = task["clips"][0]["clip_id"]
    dest_dir = tmp_path / "suno"
    res = suno_download(clip_id=clip_id, dest_dir=str(dest_dir))
    assert res["ok"] is True
    out = Path(res["audio_path"])
    assert out.exists() and out.stat().st_size > 0


def test_extract_stems_writes_vocal_and_instrumental(tmp_path: Path):
    gen = suno_generate(lyrics="Jai Shree Shyam", candidates=1)
    task = suno_get_task(task_id=gen["task_id"])
    clip_id = task["clips"][0]["clip_id"]
    dest_dir = tmp_path / "stems"
    res = suno_extract_stems(clip_id=clip_id, dest_dir=str(dest_dir))
    assert res["ok"] is True
    vocal = Path(res["vocal_path"])
    instrumental = Path(res["instrumental_path"])
    assert vocal.name == "guide_vocal.wav" and vocal.exists()
    assert instrumental.name == "instrumental.wav" and instrumental.exists()
    assert vocal.stat().st_size > 0 and instrumental.stat().st_size > 0
