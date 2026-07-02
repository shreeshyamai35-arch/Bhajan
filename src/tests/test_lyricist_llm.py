"""Tests for the Lyricist LLM generation path and its template fallback.

These tests never make live network calls: the live LLM is replaced with a
fake object via monkeypatching, and mock mode uses the deterministic template.
"""

from __future__ import annotations

import bhajanforge.llm as llm_mod
from bhajanforge.agents.lyricist import write_lyrics
from bhajanforge.config import Settings
from bhajanforge.models import LyricsDoc, ProductionRequest


class _FakeLLM:
    """Fake LLM returning a canned JSON dict (or raising) — no network."""

    def __init__(self, payload=None, raises: bool = False):
        self._payload = payload
        self._raises = raises

    def complete_json(self, prompt, system=None):
        if self._raises:
            raise RuntimeError("simulated provider failure")
        return self._payload

    def complete(self, prompt, system=None):  # pragma: no cover - unused here
        return ""


_VALID_PAYLOAD = {
    "title_working": "Bhor Bhayi — Shyam Bhajan",
    "sections": [
        {
            "name": "mukhda",
            "lines": [
                {"text": "Shyam tere dware aaye", "pronunciation_hint": "shyaam"},
                {"text": "Bhor bhayi sab gaaye", "pronunciation_hint": None},
            ],
        },
        {
            "name": "antara",
            "lines": [{"text": "Khatu naresh ki jai", "pronunciation_hint": "khaatu"}],
        },
        {
            "name": "aarti_outro",
            "lines": [{"text": "Om jai shyam hare", "pronunciation_hint": None}],
        },
    ],
    "devotional_terms": ["Shyam", "Khatu", "Aarti"],
}


def test_mock_mode_uses_template(monkeypatch):
    """In mock mode write_lyrics returns the structured template doc (no net)."""
    monkeypatch.setattr(Settings, "is_mock", lambda self: True)

    # If get_llm were called we'd want to notice; make it explode.
    def _boom():
        raise AssertionError("LLM must not be used in mock mode")

    monkeypatch.setattr(llm_mod, "get_llm", _boom)

    req = ProductionRequest(theme="morning darshan")
    doc = write_lyrics(req, {"pronunciation_fixes": {"श्याम / Shyam": "shyaam"}})

    assert isinstance(doc, LyricsDoc)
    names = [s.name for s in doc.sections]
    assert names[0] == "mukhda"
    assert "antara" in names
    assert names[-1] == "aarti_outro"
    assert doc.devotional_terms


def test_live_mode_builds_doc_from_llm_json(monkeypatch):
    """When live and the LLM returns valid JSON, build a LyricsDoc from it."""
    monkeypatch.setattr(Settings, "is_mock", lambda self: False)
    monkeypatch.setattr(llm_mod, "get_llm", lambda: _FakeLLM(payload=_VALID_PAYLOAD))

    req = ProductionRequest(theme="bhor bhayi", deity="Shyam")
    doc = write_lyrics(req, {})

    assert isinstance(doc, LyricsDoc)
    assert doc.title_working == "Bhor Bhayi — Shyam Bhajan"
    names = [s.name for s in doc.sections]
    assert names == ["mukhda", "antara", "aarti_outro"]
    assert doc.sections[0].lines[0].text == "Shyam tere dware aaye"
    assert doc.sections[0].lines[0].pronunciation_hint == "shyaam"
    assert doc.devotional_terms == ["Shyam", "Khatu", "Aarti"]


def test_live_mode_llm_failure_falls_back_to_template(monkeypatch):
    """If the LLM raises, write_lyrics falls back to the template (no crash)."""
    monkeypatch.setattr(Settings, "is_mock", lambda self: False)
    monkeypatch.setattr(llm_mod, "get_llm", lambda: _FakeLLM(raises=True))

    req = ProductionRequest(theme="morning darshan")
    doc = write_lyrics(req, {})

    assert isinstance(doc, LyricsDoc)
    names = [s.name for s in doc.sections]
    assert names[0] == "mukhda"
    assert "antara" in names
    assert names[-1] == "aarti_outro"
    # Template seeds devotional terms.
    assert doc.devotional_terms


def test_live_mode_empty_json_falls_back_to_template(monkeypatch):
    """Empty/invalid JSON from the LLM also falls back to the template."""
    monkeypatch.setattr(Settings, "is_mock", lambda self: False)
    monkeypatch.setattr(llm_mod, "get_llm", lambda: _FakeLLM(payload={}))

    req = ProductionRequest(theme="evening aarti")
    doc = write_lyrics(req, {})

    assert isinstance(doc, LyricsDoc)
    names = [s.name for s in doc.sections]
    assert names[0] == "mukhda"
    assert names[-1] == "aarti_outro"
