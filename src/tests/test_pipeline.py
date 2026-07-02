"""M7 orchestration smoke tests — end-to-end produce in mock mode (AC-1, AC-5),
ethics hard-stops (AC-8), and the quality-gate correction loop (R4.*).

All offline with BHAJANFORGE_MOCK=1; cloud tools return deterministic mocks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bhajanforge.models import Mood, ProductionRequest


@pytest.fixture()
def pipeline_env(tmp_path, monkeypatch):
    """Redirect all writable paths into tmp so the repo is never touched."""
    monkeypatch.setenv("BHAJANFORGE_MOCK", "1")
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("RVC_MODELS_DIR", str(tmp_path / "models" / "rvc"))
    monkeypatch.setenv("BHAJANFORGE_LEARNING_PATH", str(tmp_path / "learning.yaml"))
    monkeypatch.setenv("PUBLISH_TARGET", "local")
    return tmp_path


def test_produce_happy_path(pipeline_env):
    from bhajanforge.graph import run_pipeline

    req = ProductionRequest(theme="morning darshan of Khatu Shyam", mood=Mood.slow_emotional)
    result = run_pipeline(req)

    assert result["halted"] is False
    assert result["passed"] is True, result
    assert result["score"] >= 95, result
    assert result["decision"] == "saved_local"

    # master.wav exists for the run (AC-1).
    master = pipeline_env / "runs" / result["run_id"] / "master.wav"
    assert master.exists() and master.stat().st_size > 0

    # local bundle saved, no upload (AC-7).
    assert result["output_dir"]
    bundle = Path(result["output_dir"])
    assert (bundle / "master.wav").exists()
    assert (bundle / "description.txt").exists()


def test_resume_skips_completed_run(pipeline_env):
    from bhajanforge.graph import run_pipeline

    req = ProductionRequest(theme="evening aarti")
    first = run_pipeline(req)
    again = run_pipeline(req, run_id=first["run_id"])
    assert again.get("resumed") is True
    assert again["decision"] in {"saved_local", "published", "draft"}


def test_ethics_halt_non_devotional(pipeline_env):
    from bhajanforge.graph import run_pipeline

    req = ProductionRequest(theme="a party anthem edm club banger")
    result = run_pipeline(req)
    assert result["halted"] is True
    assert result["decision"] == "failed"
    assert "non-devotional" in (result["halt_reason"] or "")


def test_ethics_halt_third_party_voice(pipeline_env):
    from bhajanforge.graph import run_pipeline

    req = ProductionRequest(theme="bhajan in the voice of some famous singer")
    result = run_pipeline(req)
    assert result["halted"] is True
    assert "third-party voice" in (result["halt_reason"] or "")


def test_quality_loop_escalates_to_human(pipeline_env, monkeypatch):
    """Force low voice similarity so the voice loop runs out -> needs_human."""
    from bhajanforge.agents import voice as voice_agent
    from bhajanforge.graph import run_pipeline

    # The judge trusts the voice agent's own similarity self-check; drive it low.
    monkeypatch.setattr(voice_agent, "_quick_similarity", lambda *a, **k: 0.50)

    req = ProductionRequest(theme="slow bhajan")
    result = run_pipeline(req)

    assert result["passed"] is False
    assert result["decision"] == "needs_human"
    # voice stage capped at MAX_LOOP_ATTEMPTS (4).
    assert result["total_loops"] == 4
