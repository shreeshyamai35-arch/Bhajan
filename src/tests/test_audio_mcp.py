"""M1 audio-mcp tests — offline, CPU-only, BHAJANFORGE_MOCK=1.

Generates tiny synthetic wav fixtures and exercises the audio core tools.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from bhajanforge.mcp_servers.audio_mcp import (
    audio_align,
    audio_analyze,
    audio_master,
    audio_mix,
    audio_transcribe,
    audio_vocal_chain,
)

SR = 48000


def _tone(freq: float, dur: float = 1.0, amp: float = 0.3, sr: int = SR) -> np.ndarray:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _make_wav(path: Path, signal: np.ndarray, sr: int = SR) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), signal, sr, subtype="PCM_16")
    return str(path)


def _vocal_wav(tmp_path: Path) -> str:
    # A "vocal": mid tone with a little vibrato-ish second harmonic.
    sig = _tone(220.0, 1.0) + 0.1 * _tone(440.0, 1.0)
    return _make_wav(tmp_path / "vocal.wav", sig)


def _instr_wav(tmp_path: Path) -> str:
    sig = _tone(110.0, 1.0, amp=0.25) + 0.2 * _tone(330.0, 1.0, amp=0.25)
    return _make_wav(tmp_path / "instrumental.wav", sig)


def _nonempty_wav(path: str) -> bool:
    p = Path(path)
    if not (p.exists() and p.stat().st_size > 0):
        return False
    data, _ = sf.read(path)
    return data.size > 0


def test_align_returns_offset(tmp_path: Path):
    vocal = _vocal_wav(tmp_path)
    instr = _instr_wav(tmp_path)
    dest = str(tmp_path / "aligned_vocal.wav")
    res = audio_align(vocal, instr, dest)
    assert res["ok"] is True
    assert "offset_ms" in res and isinstance(res["offset_ms"], int)
    assert _nonempty_wav(res["aligned_vocal_path"])


def test_vocal_chain_produces_wav(tmp_path: Path):
    vocal = _vocal_wav(tmp_path)
    dest = str(tmp_path / "vocal_fx.wav")
    res = audio_vocal_chain(vocal, dest, low_cut_hz=100, presence_db=3.0)
    assert res["ok"] is True
    assert _nonempty_wav(res["output_path"])


def test_mix_produces_premaster(tmp_path: Path):
    vocal = _vocal_wav(tmp_path)
    instr = _instr_wav(tmp_path)
    dest = str(tmp_path / "mix" / "premaster.wav")
    res = audio_mix(vocal, instr, dest_path=dest, vocal_gain_db=-2.0)
    assert res["ok"] is True
    assert _nonempty_wav(res["output_path"])


def test_master_hits_targets(tmp_path: Path):
    vocal = _vocal_wav(tmp_path)
    instr = _instr_wav(tmp_path)
    pre = str(tmp_path / "premaster.wav")
    audio_mix(vocal, instr, dest_path=pre)
    dest = str(tmp_path / "master.wav")
    res = audio_master(pre, dest, target_lufs=-14.0, true_peak_dbtp=-1.0)
    assert res["ok"] is True
    assert _nonempty_wav(res["output_path"])
    assert abs(res["lufs"] - (-14.0)) <= 1.5
    assert res["true_peak"] <= -1.0 + 1e-6
    assert res["provider_used"]


def test_analyze_returns_metric_keys(tmp_path: Path):
    vocal = _vocal_wav(tmp_path)
    instr = _instr_wav(tmp_path)
    pre = str(tmp_path / "premaster.wav")
    audio_mix(vocal, instr, dest_path=pre)
    master = str(tmp_path / "master.wav")
    audio_master(pre, master)
    res = audio_analyze(master, vocal_only_path=vocal)
    assert res["ok"] is True
    for key in (
        "lufs",
        "true_peak_dbtp",
        "voice_similarity",
        "artifact_score",
        "pitch_stability",
        "vocal_instr_balance_db",
        "max_silence_gap_sec",
    ):
        assert key in res


def test_transcribe_mock_stub(tmp_path: Path):
    vocal = _vocal_wav(tmp_path)
    res = audio_transcribe(vocal, language="hi")
    assert res["ok"] is True
    assert isinstance(res["text"], str) and res["text"]
    assert isinstance(res["words"], list) and len(res["words"]) > 0
    assert {"w", "start", "end"} <= set(res["words"][0].keys())
