"""M9 governance tests — enforce config/rules.md guardrails in code (AC-8)."""

from __future__ import annotations

import pytest

from bhajanforge.agents.packager import AI_DISCLOSURE_REMINDER
from bhajanforge.config import load_rules
from bhajanforge.graph import validate_request
from bhajanforge.models import ProductionRequest


# --- R2.1 / R1.1 ethics hard-stops ---------------------------------------


def test_third_party_voice_is_halted():
    rules = load_rules()
    halted, reason = validate_request(
        ProductionRequest(theme="bhajan in the voice of a famous playback singer"), rules
    )
    assert halted is True
    assert "third-party voice" in reason


def test_clone_someone_else_is_halted():
    rules = load_rules()
    halted, reason = validate_request(
        ProductionRequest(theme="please clone my friend's voice for this bhajan"), rules
    )
    assert halted is True


def test_non_devotional_is_halted():
    rules = load_rules()
    for theme in ("an edm club banger", "a romantic love song", "party anthem rap"):
        halted, reason = validate_request(ProductionRequest(theme=theme), rules)
        assert halted is True, theme
        assert "non-devotional" in reason


def test_devotional_request_passes():
    rules = load_rules()
    halted, reason = validate_request(
        ProductionRequest(theme="morning darshan of Khatu Shyam"), rules
    )
    assert halted is False
    assert reason is None


# --- R2.1 / R2.3 immutable safety rails -----------------------------------


def test_loader_rejects_third_party_flag(tmp_path):
    bad = tmp_path / "rules.md"
    bad.write_text("```yaml\nallow_third_party_voice: true\n```", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(bad)


def test_loader_rejects_disabled_disclosure(tmp_path):
    bad = tmp_path / "rules.md"
    bad.write_text("```yaml\nrequire_ai_disclosure: false\n```", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(bad)


# --- R3.1 quality gate floor ---------------------------------------------


def test_quality_gate_never_below_min(tmp_path, monkeypatch):
    monkeypatch.setattr("bhajanforge.config._load_env", lambda: None)
    monkeypatch.delenv("QUALITY_GATE", raising=False)
    bad = tmp_path / "rules.md"
    bad.write_text("```yaml\nquality_gate: 80\nmin_quality_gate: 90\n```", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(bad)


# --- R3.* default thresholds match the spec ------------------------------


def test_default_thresholds_match_spec():
    r = load_rules()
    assert r.quality_gate == 95
    assert r.loudness_lufs == -14.0
    assert r.true_peak_dbtp == -1.0
    assert r.voice_similarity_min == 0.95
    assert r.max_loop_attempts == 4
    assert r.max_total_loops == 8
    assert r.publish_target == "local"


# --- R2.3 AI-disclosure reminder is present -------------------------------


def test_disclosure_reminder_text_is_explicit():
    lowered = AI_DISCLOSURE_REMINDER.lower()
    assert "synthetic" in lowered or "altered" in lowered
    assert "youtube" in lowered
