"""M6 agent unit tests (mocked tools, offline)."""

from __future__ import annotations

import pytest

from bhajanforge.agents.composer import build_style_prompt
from bhajanforge.agents.lyricist import write_lyrics
from bhajanforge.agents.quality_judge import evaluate
from bhajanforge.config import load_rules
from bhajanforge.models import (
    LyricLine,
    LyricsDoc,
    LyricSection,
    Mood,
    ProductionRequest,
    VoiceResult,
    VoiceSettings,
)


def test_lyricist_builds_structured_doc():
    req = ProductionRequest(theme="morning darshan")
    learning = {"pronunciation_fixes": {"श्याम / Shyam": "shyaam"}}
    doc = write_lyrics(req, learning)
    names = [s.name for s in doc.sections]
    assert names[0] == "mukhda"
    assert "antara" in names
    assert names[-1] == "aarti_outro"
    assert doc.devotional_terms


def test_lyricist_honours_override():
    req = ProductionRequest(theme="x", lyrics_override="Line A\nLine B\n\nVerse one")
    doc = write_lyrics(req, {})
    assert doc.title_working == "Custom Lyrics"
    assert doc.rag_confidence == 1.0


def test_composer_style_prompt_uses_winning_template():
    req = ProductionRequest(theme="darshan", mood=Mood.slow_emotional)
    learning = {"music_preferences": {"winning_prompts": {"slow_emotional": "TEMPLE PROMPT"}}}
    style, key = build_style_prompt(req, learning)
    assert "TEMPLE PROMPT" in style
    assert key == "slow_emotional"
    assert "keherwa" in style.lower()


def _lyrics() -> LyricsDoc:
    return LyricsDoc(
        title_working="t",
        sections=[LyricSection(name="mukhda", lines=[LyricLine(text="Shyam")])],
        devotional_terms=[],
    )


def test_judge_passes_clean_master(tmp_path, monkeypatch):
    import bhajanforge.agents.quality_judge as qj

    monkeypatch.setattr(qj, "audio_analyze", lambda **k: {
        "ok": True, "error": None, "lufs": -14.0, "true_peak_dbtp": -1.1,
        "voice_similarity": 0.97, "artifact_score": 0.05, "pitch_stability": 0.95,
        "vocal_instr_balance_db": 2.0, "max_silence_gap_sec": 0.2,
    })
    rules = load_rules()
    state = {
        "run_id": "t", "rules": rules, "request": ProductionRequest(theme="x"),
        "lyrics": _lyrics(), "learning": {}, "loop_counts": {},
        "artifacts": {"master": str(tmp_path / "m.wav")},
        "voice": VoiceResult(output_path="v.wav", settings_used=VoiceSettings(model_name="m"),
                             voice_similarity=0.97),
    }
    report = evaluate(state)
    assert report.passed is True
    assert report.score >= 95
    assert report.next_stage_on_fail is None


def test_judge_fails_low_similarity_routes_voice(tmp_path, monkeypatch):
    import bhajanforge.agents.quality_judge as qj

    monkeypatch.setattr(qj, "audio_analyze", lambda **k: {
        "ok": True, "error": None, "lufs": -14.0, "true_peak_dbtp": -1.1,
        "voice_similarity": 0.40, "artifact_score": 0.05, "pitch_stability": 0.95,
        "vocal_instr_balance_db": 2.0, "max_silence_gap_sec": 0.2,
    })
    rules = load_rules()
    state = {
        "run_id": "t", "rules": rules, "request": ProductionRequest(theme="x"),
        "lyrics": _lyrics(), "learning": {}, "loop_counts": {},
        "artifacts": {"master": str(tmp_path / "m.wav")},
        "voice": VoiceResult(output_path="v.wav", settings_used=VoiceSettings(model_name="m"),
                             voice_similarity=0.40),
    }
    report = evaluate(state)
    assert report.passed is False
    assert report.next_stage_on_fail == "voice"
    assert any(f.stage == "voice" and "index_ratio" in f.params for f in report.fixes)
