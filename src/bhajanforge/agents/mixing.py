"""Mixing Agent (M6) — align, vocal chain, mix, master (FR-14..FR-16).

Combines the converted vocal with the instrumental and produces a professional
master at -14 LUFS / <= -1 dBTP via audio-mcp (LANDR primary, matchering/local
fallback). Applies quality-loop fixes routed to the "mixing" stage.
"""

from __future__ import annotations

from typing import Any

from ..logging_utils import get_logger
from ..mcp_servers.audio_mcp import (
    audio_align,
    audio_master,
    audio_mix,
    audio_vocal_chain,
)
from ..models import MixResult

logger = get_logger("agent.mixing")


def _mix_prefs(learning: dict) -> dict:
    return (learning or {}).get("mix_preferences", {}) or {}


def _apply_fixes(params: dict, state: dict) -> dict:
    quality = state.get("quality")
    fixes = getattr(quality, "fixes", []) if quality is not None else []
    for fix in fixes:
        if getattr(fix, "stage", None) != "mixing":
            continue
        params.update(getattr(fix, "params", {}) or {})
        logger.info("Applied mixing fix: %s", getattr(fix, "action", ""))
    return params


def mix_and_master(state: dict) -> MixResult:
    from .. import runs

    run_id = state["run_id"]
    rules = state["rules"]
    learning = state.get("learning", {})
    artifacts = state.get("artifacts", {})

    vocal = artifacts.get("my_voice")
    instrumental = artifacts.get("instrumental")
    if not vocal or not instrumental:
        raise RuntimeError("missing vocal or instrumental for mixing")

    mix_dir = runs.run_dir(run_id) / "mix"
    mix_dir.mkdir(parents=True, exist_ok=True)

    # 1. Align vocal to instrumental.
    aligned_path = str(mix_dir / "aligned_vocal.wav")
    align = audio_align(vocal_path=vocal, instrumental_path=instrumental, dest_path=aligned_path)
    aligned_vocal = align.get("aligned_vocal_path", vocal) if align.get("ok") else vocal
    offset_ms = align.get("offset_ms", 0) if align.get("ok") else 0

    prefs = _mix_prefs(learning)
    chain_params: dict[str, Any] = {
        "reverb_preset": prefs.get("reverb_preset", "temple_hall"),
        "reverb_predelay_ms": prefs.get("reverb_predelay_ms", 30),
    }
    chain_params = _apply_fixes(chain_params, state)

    # 2. Vocal chain.
    fx_path = str(mix_dir / "vocal_fx.wav")
    chain = audio_vocal_chain(vocal_path=aligned_vocal, dest_path=fx_path, **chain_params)
    fx_vocal = chain.get("output_path", aligned_vocal) if chain.get("ok") else aligned_vocal

    # 3. Mix to premaster.
    premaster = str(mix_dir / "premaster.wav")
    vocal_gain = float(chain_params.get("vocal_gain_db", 0.0))
    mix = audio_mix(vocal_path=fx_vocal, instrumental_path=instrumental, vocal_gain_db=vocal_gain, dest_path=premaster)
    if not mix.get("ok"):
        raise RuntimeError(f"audio.mix failed: {mix.get('error')}")

    # 4. Master to target loudness / peak.
    master_path = str(runs.run_dir(run_id) / "master.wav")
    reference = prefs.get("master_reference_track")
    master = audio_master(
        input_path=premaster,
        dest_path=master_path,
        target_lufs=rules.loudness_lufs,
        true_peak_dbtp=rules.true_peak_dbtp,
        reference_track=reference,
    )
    if not master.get("ok"):
        raise RuntimeError(f"audio.master failed: {master.get('error')}")

    return MixResult(
        premaster_path=premaster,
        master_path=master["output_path"],
        offset_ms=int(offset_ms),
        lufs=master.get("lufs"),
        true_peak_dbtp=master.get("true_peak"),
        used_landr=(master.get("provider_used") == "landr"),
    )


def mixing_node(state: dict) -> dict:
    result = mix_and_master(state)
    artifacts = dict(state.get("artifacts", {}))
    artifacts["master"] = result.master_path
    artifacts["premaster"] = result.premaster_path
    logger.info("Mastered: %.2f LUFS, %.2f dBTP", result.lufs or 0.0, result.true_peak_dbtp or 0.0)
    return {"mix": result, "artifacts": artifacts}
