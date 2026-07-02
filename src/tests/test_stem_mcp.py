"""M2 stem-mcp tests — offline, BHAJANFORGE_MOCK=1 synthesis fallback."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from bhajanforge.mcp_servers.stem_mcp import stem_batch_isolate, stem_isolate

SR = 48000


def _song(path: Path, dur: float = 1.0, sr: int = SR) -> str:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    # low "instrumental" + high "vocal" content mixed together
    sig = 0.3 * np.sin(2 * np.pi * 120 * t) + 0.2 * np.sin(2 * np.pi * 3000 * t)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), sig.astype(np.float32), sr, subtype="PCM_16")
    return str(path)


def _nonempty_wav(path: str) -> bool:
    p = Path(path)
    if not (p.exists() and p.stat().st_size > 0):
        return False
    data, _ = sf.read(path)
    return data.size > 0


def test_isolate_produces_both_stems(tmp_path: Path):
    song = _song(tmp_path / "song.wav")
    dest = str(tmp_path / "stems")
    res = stem_isolate(song, dest, target="both")
    assert res["ok"] is True
    assert _nonempty_wav(res["vocals_path"])
    assert _nonempty_wav(res["instrumental_path"])


def test_isolate_missing_input_errors(tmp_path: Path):
    res = stem_isolate(str(tmp_path / "nope.wav"), str(tmp_path / "out"))
    assert res["ok"] is False
    assert res["error"]


def test_batch_isolate_counts(tmp_path: Path):
    in_dir = tmp_path / "downloads"
    for i in range(3):
        _song(in_dir / f"track_{i}.wav")
    dest = str(tmp_path / "datasets")
    res = stem_batch_isolate(str(in_dir), dest, target="vocals")
    assert res["ok"] is True
    assert res["count"] > 0
    assert len(res["outputs"]) == res["count"]
    for out in res["outputs"]:
        assert _nonempty_wav(out)
