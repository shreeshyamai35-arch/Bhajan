"""M0 foundation tests: models, config, runs, learning, governance invariants."""

from __future__ import annotations

import pytest

from bhajanforge.config import load_rules
from bhajanforge.memory import learning
from bhajanforge.models import (
    LyricLine,
    LyricSection,
    LyricsDoc,
    Mood,
    ProductionRequest,
)
from bhajanforge.runs import init_run, load_manifest, new_run_id, slugify


# --- models ---------------------------------------------------------------


def test_production_request_defaults():
    req = ProductionRequest(theme="morning darshan")
    assert req.deity == "Khatu Shyam"
    assert req.mood == Mood.slow_emotional
    assert req.publish_target == "local"


def test_lyrics_as_suno_text():
    doc = LyricsDoc(
        title_working="Test",
        sections=[
            LyricSection(name="mukhda", lines=[LyricLine(text="Shyam Shyam")]),
            LyricSection(name="antara", lines=[LyricLine(text="Khatu wale Shyam")]),
        ],
    )
    text = doc.as_suno_text()
    assert "[Chorus]" in text and "[Verse]" in text
    assert "Shyam Shyam" in text


# --- config / governance --------------------------------------------------


def test_rules_load_defaults():
    rules = load_rules()
    assert rules.quality_gate >= rules.min_quality_gate
    assert rules.loudness_lufs == -14.0
    assert rules.voice_similarity_min == 0.95


def test_rules_third_party_voice_forbidden(tmp_path):
    # The hard ethics rail (R2.1) is enforced by load_rules, not the bare model.
    bad = tmp_path / "rules.md"
    bad.write_text("```yaml\nallow_third_party_voice: true\n```", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(bad)


def test_quality_gate_floor_enforced(tmp_path, monkeypatch):
    # Isolate from .env: don't let an env QUALITY_GATE override the file's value.
    monkeypatch.setattr("bhajanforge.config._load_env", lambda: None)
    monkeypatch.delenv("QUALITY_GATE", raising=False)
    bad = tmp_path / "rules.md"
    bad.write_text("```yaml\nquality_gate: 80\nmin_quality_gate: 90\n```", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(bad)


# --- runs -----------------------------------------------------------------


def test_slugify():
    assert slugify("Morning Darshan!! 2026") == "morning-darshan-2026"


def test_run_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    monkeypatch.setattr("bhajanforge.runs.get_settings", lambda: _S(tmp_path))
    req = ProductionRequest(theme="evening aarti")
    manifest = init_run(req)
    assert manifest.run_id.endswith("evening-aarti")
    again = init_run(req, run_id=manifest.run_id)  # idempotent
    assert again.run_id == manifest.run_id
    loaded = load_manifest(manifest.run_id)
    assert loaded.request.theme == "evening aarti"


class _S:
    def __init__(self, p):
        self._p = p

    @property
    def runs_dir(self):
        return self._p


# --- learning -------------------------------------------------------------


def test_learning_record_run_updates_stats(tmp_learning):
    learning.record_run({"run_id": "r1", "judge_score": 96, "published": False}, tmp_learning)
    data = learning.record_run({"run_id": "r2", "judge_score": 94}, tmp_learning)
    assert data["stats"]["total_runs"] == 2
    assert data["stats"]["avg_judge_score"] == 95.0


def test_register_voice_model(tmp_learning):
    data = learning.register_voice_model(
        "replicate/model:abc", "replicate", {"low_note": "A2", "high_note": "E4"}, tmp_learning
    )
    assert data["voice_profile"]["active_rvc_model"] == "replicate/model:abc"
    assert data["voice_profile"]["range"]["high_note"] == "E4"


def test_new_run_id_has_date_prefix():
    rid = new_run_id("test theme")
    assert rid.count("-") >= 2 and rid.endswith("test-theme")
