"""audio-mcp core DSP — CPU-only, runs real signal processing even in mock mode.

Pure-Python functions named after the MCP tools (dots -> underscores). These are
what tests and agents call in-process. Importing this module must NOT require the
``mcp`` package. Every function returns the common ``ok()`` / ``err()`` envelope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

try:  # heavy deps are installed, but stay defensive
    import soundfile as sf
except Exception as exc:  # pragma: no cover - import guard
    sf = None  # type: ignore
    _SF_ERR = exc

import scipy.signal as sps

from ..common import err, mock_enabled, ok, safe_call
from . import providers

# --------------------------------------------------------------------------
# Audio IO helpers
# --------------------------------------------------------------------------


def _read(path: str) -> tuple[np.ndarray, int]:
    """Read a wav as float64 array shaped (n,) mono or (n, ch)."""
    data, sr = sf.read(str(path), dtype="float64", always_2d=False)
    return np.asarray(data, dtype=np.float64), int(sr)


def _to_mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 1:
        return data
    return data.mean(axis=1)


def _write(path: str, data: np.ndarray, sr: int) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(data, dtype=np.float32)
    # Guard against NaN / inf and hard clip to valid range.
    arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)
    arr = np.clip(arr, -1.0, 1.0)
    sf.write(str(out), arr, sr, subtype="PCM_16")


def _true_peak_dbtp(data: np.ndarray, oversample: int = 4) -> float:
    """Estimate inter-sample true peak in dBTP via polyphase oversampling."""
    x = data if data.ndim == 2 else data[:, None]
    try:
        up = sps.resample_poly(x, oversample, 1, axis=0)
    except Exception:
        up = x
    peak = float(np.max(np.abs(up))) if up.size else 0.0
    if peak <= 1e-12:
        return -120.0
    return 20.0 * float(np.log10(peak))


def _integrated_lufs(data: np.ndarray, sr: int) -> float:
    """Integrated loudness (LUFS) via pyloudnorm; finite-safe."""
    import pyloudnorm as pyln

    meter = pyln.Meter(sr)
    d = data
    # pyloudnorm accepts (n,) or (n, ch).
    try:
        loud = float(meter.integrated_loudness(d))
    except Exception:
        return -70.0
    if not np.isfinite(loud):
        return -70.0
    return loud


# --------------------------------------------------------------------------
# audio.align
# --------------------------------------------------------------------------


def audio_align(
    vocal_path: str,
    instrumental_path: str,
    dest_path: str,
    **_: Any,
) -> dict[str, Any]:
    """Detect the vocal->instrumental offset via cross-correlation and write the
    time-aligned vocal to ``dest_path``."""

    def _run() -> dict[str, Any]:
        vocal, sr_v = _read(vocal_path)
        instr, sr_i = _read(instrumental_path)
        sr = sr_v
        if sr_i != sr_v:
            # resample instrumental reference to the vocal rate for correlation
            n = int(round(instr.shape[0] * sr_v / sr_i))
            instr = sps.resample(_to_mono(instr), n)
        vm = _to_mono(vocal)
        im = _to_mono(instr)

        # Normalize to unit energy for a stable correlation peak.
        def _norm(a: np.ndarray) -> np.ndarray:
            s = float(np.sqrt(np.sum(a * a))) or 1.0
            return a / s

        corr = sps.fftconvolve(_norm(vm), _norm(im)[::-1], mode="full")
        lag = int(np.argmax(corr)) - (len(im) - 1)
        # lag > 0 means vocal starts after instrumental -> shift vocal earlier.
        offset_ms = int(round(lag / sr * 1000.0))

        # Apply the shift to the (original, possibly multichannel) vocal.
        aligned = _shift(vocal, -lag)
        _write(dest_path, aligned, sr)
        return ok(offset_ms=offset_ms, aligned_vocal_path=str(dest_path))

    return safe_call(_run, "audio.align")


def _shift(data: np.ndarray, n: int) -> np.ndarray:
    """Shift samples by ``n`` (positive = delay) with zero padding, same length."""
    if n == 0:
        return data
    out = np.zeros_like(data)
    if data.ndim == 1:
        length = data.shape[0]
        if n > 0:
            if n < length:
                out[n:] = data[: length - n]
        else:
            k = -n
            if k < length:
                out[: length - k] = data[k:]
        return out
    length = data.shape[0]
    if n > 0:
        if n < length:
            out[n:, :] = data[: length - n, :]
    else:
        k = -n
        if k < length:
            out[: length - k, :] = data[k:, :]
    return out


# --------------------------------------------------------------------------
# audio.vocal_chain
# --------------------------------------------------------------------------


def audio_vocal_chain(
    vocal_path: str,
    dest_path: str,
    low_cut_hz: float = 100.0,
    presence_db: float = 3.0,
    comp_ratio: float = 3.0,
    deess: bool = True,
    reverb_preset: str = "temple_hall",
    reverb_predelay_ms: float = 30.0,
    **_: Any,
) -> dict[str, Any]:
    """Apply a simple CPU vocal chain: low-cut, presence EQ, compression, optional
    de-ess, and a synthetic reverb. Writes the processed vocal to ``dest_path``."""

    def _run() -> dict[str, Any]:
        data, sr = _read(vocal_path)
        mono = _to_mono(data)

        x = _highpass(mono, sr, low_cut_hz)
        x = _presence_eq(x, sr, gain_db=presence_db)
        if deess:
            x = _deess(x, sr)
        x = _compress(x, ratio=comp_ratio)
        x = _reverb(x, sr, preset=reverb_preset, predelay_ms=reverb_predelay_ms)

        # Tame any post-FX overs.
        peak = float(np.max(np.abs(x))) or 1.0
        if peak > 0.99:
            x = x * (0.99 / peak)
        _write(dest_path, x, sr)
        return ok(output_path=str(dest_path))

    return safe_call(_run, "audio.vocal_chain")


def _highpass(x: np.ndarray, sr: int, cutoff: float) -> np.ndarray:
    cutoff = max(20.0, min(float(cutoff), sr / 2.0 - 1.0))
    b, a = sps.butter(2, cutoff / (sr / 2.0), btype="highpass")
    return sps.lfilter(b, a, x)


def _presence_eq(x: np.ndarray, sr: int, gain_db: float, center: float = 4000.0) -> np.ndarray:
    """Gentle peaking boost around the presence band via a biquad."""
    if abs(gain_db) < 1e-3:
        return x
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * min(center, sr / 2.0 - 1.0) / sr
    alpha = np.sin(w0) / (2 * 1.0)  # Q = 1
    cosw = np.cos(w0)
    b0 = 1 + alpha * A
    b1 = -2 * cosw
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * cosw
    a2 = 1 - alpha / A
    b = np.array([b0, b1, b2]) / a0
    a = np.array([a0, a1, a2]) / a0
    return sps.lfilter(b, a, x)


def _deess(x: np.ndarray, sr: int) -> np.ndarray:
    """Crude de-esser: attenuate high-band energy a few dB."""
    cutoff = min(6000.0, sr / 2.0 - 1.0)
    b, a = sps.butter(2, cutoff / (sr / 2.0), btype="highpass")
    high = sps.lfilter(b, a, x)
    return x - 0.35 * high


def _compress(x: np.ndarray, ratio: float = 3.0, threshold: float = 0.2) -> np.ndarray:
    """Simple static waveshaping compressor above ``threshold``."""
    ratio = max(1.0, float(ratio))
    out = x.copy()
    mag = np.abs(x)
    over = mag > threshold
    out[over] = np.sign(x[over]) * (
        threshold + (mag[over] - threshold) / ratio
    )
    # makeup gain
    return out * (1.0 + 0.5 * (1.0 - 1.0 / ratio))


def _reverb(
    x: np.ndarray,
    sr: int,
    preset: str = "temple_hall",
    predelay_ms: float = 30.0,
    wet: float = 0.25,
) -> np.ndarray:
    """Convolve with a short synthetic decaying-noise impulse response."""
    decay = {"temple_hall": 1.2, "room": 0.4, "plate": 0.8}.get(preset, 0.8)
    ir_len = max(1, int(sr * decay))
    rng = np.random.default_rng(42)
    t = np.linspace(0, decay, ir_len, endpoint=False)
    ir = rng.standard_normal(ir_len) * np.exp(-3.0 * t / max(decay, 1e-6))
    ir[0] = 1.0  # direct spike
    pre = max(0, int(sr * predelay_ms / 1000.0))
    if pre:
        ir = np.concatenate([np.zeros(pre), ir])
    wetsig = sps.fftconvolve(x, ir, mode="full")[: len(x)]
    wp = float(np.max(np.abs(wetsig))) or 1.0
    wetsig = wetsig / wp
    return (1.0 - wet) * x + wet * wetsig


# --------------------------------------------------------------------------
# audio.mix
# --------------------------------------------------------------------------


def audio_mix(
    vocal_path: str,
    instrumental_path: str,
    vocal_gain_db: float = 0.0,
    dest_path: str = "premaster.wav",
    **_: Any,
) -> dict[str, Any]:
    """Sum vocal + instrumental (with vocal gain), prevent clipping, write premaster."""

    def _run() -> dict[str, Any]:
        vocal, sr_v = _read(vocal_path)
        instr, sr_i = _read(instrumental_path)
        sr = sr_v
        vm = _to_mono(vocal)
        im = _to_mono(instr)
        if sr_i != sr_v:
            im = sps.resample(im, int(round(len(im) * sr_v / sr_i)))
        n = max(len(vm), len(im))
        vm = np.pad(vm, (0, n - len(vm)))
        im = np.pad(im, (0, n - len(im)))

        gain = 10 ** (float(vocal_gain_db) / 20.0)
        mix = vm * gain + im
        peak = float(np.max(np.abs(mix)))
        if peak > 0.99:
            mix = mix * (0.99 / peak)
        _write(dest_path, mix, sr)
        return ok(output_path=str(dest_path))

    return safe_call(_run, "audio.mix")


# --------------------------------------------------------------------------
# audio.master
# --------------------------------------------------------------------------


def audio_master(
    input_path: str,
    dest_path: str,
    target_lufs: float = -14.0,
    true_peak_dbtp: float = -1.0,
    provider: Optional[str] = None,
    intensity: str = "medium",
    reference_track: Optional[str] = None,
    **_: Any,
) -> dict[str, Any]:
    """Master to ``target_lufs`` with a true-peak ceiling. Uses LANDR when a key is
    present; otherwise a local pyloudnorm + true-peak limiter (optionally matchering)."""

    def _run() -> dict[str, Any]:
        prov = providers.select_mastering_provider(provider)

        # Try the cloud provider first (it degrades to ProviderError on issues).
        if getattr(prov, "cloud_available", False):
            try:
                result = prov.master(
                    input_path=input_path,
                    dest_path=dest_path,
                    target_lufs=target_lufs,
                    true_peak_dbtp=true_peak_dbtp,
                    intensity=intensity,
                    reference_track=reference_track,
                )
                if result is not None:
                    return result
            except Exception:  # noqa: BLE001 - degrade to local mastering
                pass

        return _local_master(
            input_path, dest_path, target_lufs, true_peak_dbtp, reference_track,
            provider_used=getattr(prov, "name", "local"),
        )

    return safe_call(_run, "audio.master")


def _local_master(
    input_path: str,
    dest_path: str,
    target_lufs: float,
    true_peak_dbtp: float,
    reference_track: Optional[str],
    provider_used: str = "local",
) -> dict[str, Any]:
    import pyloudnorm as pyln

    data, sr = _read(input_path)

    # Optional matchering pass against a reference, if importable + provided.
    if reference_track:
        try:  # pragma: no cover - optional dependency
            import matchering as mg  # type: ignore

            tmp = str(Path(dest_path).with_suffix(".match.wav"))
            mg.process(
                target=str(input_path),
                reference=str(reference_track),
                results=[mg.pcm16(tmp)],
            )
            data, sr = _read(tmp)
            provider_used = "matchering"
        except Exception:
            pass

    # Loudness normalize toward target.
    loud = _integrated_lufs(data, sr)
    gain_db = float(np.clip(float(target_lufs) - loud, -40.0, 40.0))
    out = data * (10 ** (gain_db / 20.0))

    # Soft-knee true-peak limiter: tanh keeps peaks under the ceiling while
    # preserving loudness (instead of scaling the whole track down, which made
    # the master far too quiet). Iterate gain->limit a couple of times so the
    # integrated loudness lands near target.
    ceiling = float(true_peak_dbtp)
    ceiling_lin = 10 ** (ceiling / 20.0)
    for _ in range(3):
        out = ceiling_lin * np.tanh(out / max(ceiling_lin, 1e-6))
        cur = _integrated_lufs(out, sr)
        delta = float(target_lufs) - cur
        if abs(delta) <= 0.5:
            break
        out = out * (10 ** (float(np.clip(delta, -12.0, 12.0)) / 20.0))

    # Safety: ensure inter-sample true peak is at/under the ceiling.
    tp = _true_peak_dbtp(out)
    if tp > ceiling:
        out = out * (10 ** ((ceiling - tp) / 20.0))
    out = np.clip(out, -0.999, 0.999)

    _write(dest_path, out, sr)

    final, fsr = _read(dest_path)
    measured_lufs = round(_integrated_lufs(final, fsr), 2)
    measured_tp = round(_true_peak_dbtp(final), 2)
    return ok(
        output_path=str(dest_path),
        lufs=measured_lufs,
        true_peak=measured_tp,
        provider_used=provider_used,
    )


# --------------------------------------------------------------------------
# audio.analyze
# --------------------------------------------------------------------------


def audio_analyze(
    input_path: str,
    reference_voice_embedding: Optional[str] = None,
    vocal_only_path: Optional[str] = None,
    **_: Any,
) -> dict[str, Any]:
    """Compute loudness/quality metrics for the (mastered) track."""

    def _run() -> dict[str, Any]:
        data, sr = _read(input_path)
        mono = _to_mono(data)

        lufs = round(_integrated_lufs(data, sr), 2)
        true_peak = round(_true_peak_dbtp(data), 2)
        artifact_score = round(_artifact_score(mono, sr), 4)
        pitch_stability = round(_pitch_stability(mono, sr), 4)
        balance_db = round(_balance_db(input_path, vocal_only_path), 2)
        max_gap = round(_max_silence_gap(mono, sr), 3)
        similarity = _voice_similarity(reference_voice_embedding, vocal_only_path)

        return ok(
            lufs=lufs,
            true_peak_dbtp=true_peak,
            voice_similarity=similarity,
            artifact_score=artifact_score,
            pitch_stability=pitch_stability,
            vocal_instr_balance_db=balance_db,
            max_silence_gap_sec=max_gap,
        )

    return safe_call(_run, "audio.analyze")


def _artifact_score(x: np.ndarray, sr: int) -> float:
    """0..1 (low = clean). Blend of clipping fraction and spectral flatness."""
    if x.size == 0:
        return 1.0
    clip_frac = float(np.mean(np.abs(x) >= 0.999))
    try:
        import librosa

        flat = float(np.mean(librosa.feature.spectral_flatness(y=x.astype(np.float32))))
    except Exception:
        flat = 0.0
    score = 0.7 * min(1.0, clip_frac * 50.0) + 0.3 * min(1.0, flat)
    return float(np.clip(score, 0.0, 1.0))


def _pitch_stability(x: np.ndarray, sr: int) -> float:
    """0..1 (high = stable). Based on std of detected f0 (librosa.pyin)."""
    if x.size < sr // 4:
        return 1.0
    try:
        import librosa

        target_sr = 16000
        y = librosa.resample(x.astype(np.float32), orig_sr=sr, target_sr=target_sr)
        # Analyze at most the first 30s — pyin is expensive on long tracks.
        y = y[: target_sr * 30]
        f0, _, _ = librosa.pyin(
            y,
            sr=target_sr,
            fmin=80.0,
            fmax=400.0,
            frame_length=2048,
            hop_length=512,
        )
        f0 = f0[np.isfinite(f0)]
        if f0.size < 2:
            return 1.0
        # Convert to semitone deviation; map std -> 0..1.
        semis = 12.0 * np.log2(f0 / np.median(f0))
        std = float(np.std(semis))
        return float(np.clip(1.0 / (1.0 + std), 0.0, 1.0))
    except Exception:
        return 1.0


def _balance_db(input_path: str, vocal_only_path: Optional[str]) -> float:
    """RMS difference (dB) between vocal-only and the full mix; 0 if unavailable."""
    if not vocal_only_path or not Path(vocal_only_path).exists():
        return 0.0
    try:
        full, _ = _read(input_path)
        voc, _ = _read(vocal_only_path)
        rms_full = float(np.sqrt(np.mean(_to_mono(full) ** 2))) or 1e-9
        rms_voc = float(np.sqrt(np.mean(_to_mono(voc) ** 2))) or 1e-9
        return 20.0 * float(np.log10(rms_voc / rms_full))
    except Exception:
        return 0.0


def _max_silence_gap(x: np.ndarray, sr: int, win_ms: float = 50.0, thresh: float = 1e-3) -> float:
    """Longest contiguous near-silence span in seconds."""
    if x.size == 0:
        return 0.0
    win = max(1, int(sr * win_ms / 1000.0))
    n_win = x.size // win
    if n_win == 0:
        return 0.0
    frames = x[: n_win * win].reshape(n_win, win)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    silent = rms < thresh
    longest = 0
    cur = 0
    for s in silent:
        if s:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    return longest * win / sr


def _mfcc_embedding(path: str) -> Optional[np.ndarray]:
    try:
        import librosa

        x, sr = _read(path)
        mono = _to_mono(x).astype(np.float32)
        mfcc = librosa.feature.mfcc(y=mono, sr=sr, n_mfcc=20)
        return np.mean(mfcc, axis=1)
    except Exception:
        return None


def _voice_similarity(
    reference_voice_embedding: Optional[str],
    vocal_only_path: Optional[str],
) -> Optional[float]:
    """Cosine similarity of MFCC-mean embeddings, or mock/None when unavailable."""
    if reference_voice_embedding and vocal_only_path and Path(vocal_only_path).exists():
        try:
            ref_path = Path(reference_voice_embedding)
            if ref_path.exists() and ref_path.suffix == ".npy":
                ref = np.load(str(ref_path))
            else:
                ref = _mfcc_embedding(reference_voice_embedding)
            cur = _mfcc_embedding(vocal_only_path)
            if ref is not None and cur is not None and ref.shape == cur.shape:
                denom = (np.linalg.norm(ref) * np.linalg.norm(cur)) or 1.0
                return round(float(np.dot(ref, cur) / denom), 4)
        except Exception:
            pass
    if mock_enabled():
        return 0.97
    return None


# --------------------------------------------------------------------------
# audio.transcribe
# --------------------------------------------------------------------------


def audio_transcribe(
    input_path: str,
    language: str = "hi",
    **_: Any,
) -> dict[str, Any]:
    """Cloud ASR when a key is present; otherwise a deterministic offline stub."""

    def _run() -> dict[str, Any]:
        prov = providers.select_asr_provider()
        if getattr(prov, "cloud_available", False):
            try:
                result = prov.transcribe(input_path=input_path, language=language)
                if result is not None:
                    return result
            except Exception:  # noqa: BLE001 - degrade to stub
                pass

        # Deterministic offline stub keyed off duration so downstream is stable.
        try:
            data, sr = _read(input_path)
            dur = round(len(_to_mono(data)) / sr, 3)
        except Exception:
            dur = 0.0
        text = "shyam shyam khatu wale"
        toks = text.split()
        step = (dur / len(toks)) if toks and dur else 0.0
        words = [
            {"w": w, "start": round(i * step, 3), "end": round((i + 1) * step, 3)}
            for i, w in enumerate(toks)
        ]
        return ok(text=text, words=words)

    return safe_call(_run, "audio.transcribe")
