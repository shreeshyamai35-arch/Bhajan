"""Shared pytest fixtures for BhajanForge."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Force deterministic offline behaviour for the whole suite.
os.environ.setdefault("BHAJANFORGE_MOCK", "1")


@pytest.fixture()
def tmp_learning(tmp_path: Path) -> Path:
    """A throwaway learning.yaml seeded with the default schema."""
    content = (
        "schema_version: 1\n"
        "voice_profile:\n"
        "  artist_name: Test Artist\n"
        "  best_settings:\n"
        "    index_ratio: 0.75\n"
        "    f0_method: rmvpe\n"
        "music_preferences:\n"
        "  winning_prompts:\n"
        "    slow_emotional: 'slow emotional bhajan'\n"
        "quality_history: []\n"
        "stats:\n"
        "  total_runs: 0\n"
        "  total_published: 0\n"
        "  avg_judge_score: null\n"
    )
    p = tmp_path / "learning.yaml"
    p.write_text(content, encoding="utf-8")
    return p
