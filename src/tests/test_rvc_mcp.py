"""Offline tests for rvc-mcp (M3). Run with BHAJANFORGE_MOCK=1, no network."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from bhajanforge.mcp_servers.rvc_mcp import (
    rvc_convert,
    rvc_detect_range,
    rvc_get_train_task,
    rvc_list_models,
    rvc_train,
)
from bhajanforge.mcp_servers.rvc_mcp.core import freq_to_note


def _write_sine(path: Path, freq: float = 220.0, seconds: float = 1.0,
                sr: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0.0, seconds, int(sr * seconds), endpoint=False)
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * freq * t)).astype("float32"), sr)
    return path


def test_freq_to_note_helper():
    assert freq_to_note(440.0) == "A4"
    assert freq_to_note(261.63) == "C4"


def test_train_returns_task_id(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RVC_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("BHAJANFORGE_LEARNING_PATH", str(tmp_path / "learning.yaml"))
    res = rvc_train(dataset_url_or_zip="models/datasets/shyam.zip",
                    model_name="shyam_voice_v1", sample_rate=48000)
    assert res["ok"] is True
    assert isinstance(res["task_id"], str) and res["task_id"]


def test_get_train_task_completes_with_model_ref(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RVC_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("BHAJANFORGE_LEARNING_PATH", str(tmp_path / "learning.yaml"))
    train = rvc_train(dataset_url_or_zip="x.zip", model_name="shyam_voice_v1")
    task = rvc_get_train_task(task_id=train["task_id"])
    assert task["ok"] is True
    assert task["status"] == "complete"
    assert task["model_ref"]


def test_get_train_task_unknown_id():
    res = rvc_get_train_task(task_id="nope")
    assert res["ok"] is False
    assert res["status"] == "failed"


def test_convert_writes_dest_path(tmp_path: Path):
    src = _write_sine(tmp_path / "guide_vocal.wav", freq=261.63)
    dest = tmp_path / "voice" / "my_voice.wav"
    res = rvc_convert(input_path=str(src), model_name="shyam_voice_v1",
                      dest_path=str(dest))
    assert res["ok"] is True
    out = Path(res["output_path"])
    assert out.exists() and out.stat().st_size > 0


def test_convert_missing_input_errors(tmp_path: Path):
    res = rvc_convert(input_path=str(tmp_path / "missing.wav"),
                      model_name="m", dest_path=str(tmp_path / "out.wav"))
    assert res["ok"] is False


def test_list_models_returns_list_after_training(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RVC_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("BHAJANFORGE_LEARNING_PATH", str(tmp_path / "learning.yaml"))
    empty = rvc_list_models()
    assert empty["ok"] is True
    assert isinstance(empty["models"], list)
    rvc_train(dataset_url_or_zip="x.zip", model_name="shyam_voice_v1")
    after = rvc_list_models()
    assert after["ok"] is True
    assert any(m["name"] == "shyam_voice_v1" for m in after["models"])


def test_detect_range_returns_note_keys(tmp_path: Path):
    vocals = tmp_path / "vocals"
    _write_sine(vocals / "a.wav", freq=110.0, seconds=1.0)
    _write_sine(vocals / "b.wav", freq=330.0, seconds=1.0)
    res = rvc_detect_range(vocals_dir=str(vocals))
    assert res["ok"] is True
    assert "low_note" in res and "high_note" in res and "median_note" in res


def test_detect_range_defaults_when_empty(tmp_path: Path):
    res = rvc_detect_range(vocals_dir=str(tmp_path / "empty"))
    assert res["ok"] is True
    assert res["low_note"] == "A2"
    assert res["high_note"] == "E4"
    assert res["median_note"] == "C3"
