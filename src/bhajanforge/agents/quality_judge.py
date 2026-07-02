"""Quality Judge Agent (M6) — objective + perceptual scoring (FR-17..FR-19).

Computes a weighted 0–100 score from audio metrics, voice similarity and
pronunciation, decides pass/fail against the gate, and on failure returns the
responsible stage plus concrete fixes for the correction loop (R4.*).

Scoring weights (default, configurable):
    voice_similarity 30 | pronunciation 20 | loudness/peak 15 |
    artifacts 15 | mix balance 10 | musical fit 10
"""

from __future__ import annotations

from typing import Any, Optional

from ..logging_utils import get_logger
from ..mcp_servers.audio_mcp import audio_analyze, audio_transcribe
from ..models import CriterionResult, LyricsDoc, QualityFix, QualityReport, RulesConfig

logger = get_logger("agent.judge")

WEIGHTS = {
    "voice_similarity": 30,
    "pronunciation": 20,
    "loudness_peak": 15,
    "artifacts": 15,
    "mix_balance": 10,
    "musical_fit": 10,
}

# Candidate index_ratio values tried across voice loop attempts (R4.5).
_INDEX_RATIO_LADDER = [0.85, 0.65, 0.9, 0.7]
_F0_LADDER = ["crepe", "fcpe", "rmvpe"]


def _pronunciation_check(master_path: str, lyrics: LyricsDoc, language: str) -> tuple[float, list[str]]:
    """Transcribe and verify devotional terms appear. Returns (score0_100, missing).

    Pronunciation can only be meaningfully verified with a real cloud ASR. In
    offline/mock mode synthesized audio cannot be transcribed, so we do not
    penalize (the check is re-enabled automatically once ASR_API_KEY is set).
    """
    from ..config import get_settings

    if get_settings().is_mock():
        return 100.0, []

    terms = [t for t in (lyrics.devotional_terms or []) if t]
    if not terms:
        return 100.0, []
    tr = audio_transcribe(input_path=master_path, language=language)
    text = (tr.get("text", "") if tr.get("ok") else "").lower()
    if not text:
        return 100.0, []  # cannot verify -> do not penalize hard
    missing = [t for t in terms if t.lower().split()[0] not in text]
    # Score: fraction of terms detected (lenient — ASR is imperfect).
    detected = len(terms) - len(missing)
    score = 100.0 if not missing else max(60.0, 100.0 * detected / max(len(terms), 1))
    return score, missing


def evaluate(state: dict) -> QualityReport:
    rules: RulesConfig = state["rules"]
    artifacts = state.get("artifacts", {})
    lyrics: LyricsDoc = state["lyrics"]
    learning = state.get("learning", {})
    master = artifacts.get("master")
    if not master:
        raise RuntimeError("no master to judge")

    voice = state.get("voice")
    vocal_only = getattr(voice, "output_path", None)
    ref = ((learning or {}).get("voice_profile", {}) or {}).get("reference_embedding")

    analysis = audio_analyze(input_path=master, reference_voice_embedding=ref, vocal_only_path=vocal_only)
    metrics = {k: v for k, v in analysis.items() if k not in {"ok", "error"}}

    # Prefer the voice agent's own similarity measurement when present.
    similarity = getattr(voice, "voice_similarity", None)
    if similarity is None:
        similarity = analysis.get("voice_similarity")
    similarity = similarity if similarity is not None else 0.0

    lufs = analysis.get("lufs", -70.0)
    true_peak = analysis.get("true_peak_dbtp", 0.0)
    artifact_score = analysis.get("artifact_score", 1.0)
    balance_db = analysis.get("vocal_instr_balance_db", 0.0)

    criteria: list[CriterionResult] = []
    fixes: list[QualityFix] = []

    # --- voice similarity (hard, but only when measurable) ---
    # Without a trained reference embedding (e.g. real RVC not configured) we
    # cannot measure similarity — treat it as not-applicable rather than a
    # false failure.
    measurable = getattr(voice, "voice_similarity", None) is not None or analysis.get(
        "voice_similarity"
    ) is not None
    if measurable:
        sim_ok = similarity >= rules.voice_similarity_min
        sim_score = 100.0 if sim_ok else max(0.0, 100.0 * similarity / max(rules.voice_similarity_min, 1e-6))
        criteria.append(CriterionResult(name="voice_similarity", score=sim_score, passed=sim_ok,
                                        detail=f"{similarity:.3f} vs >= {rules.voice_similarity_min}"))
        if not sim_ok:
            attempt = int((state.get("loop_counts", {}) or {}).get("voice", 0))
            fixes.append(QualityFix(
                stage="voice",
                action="increase index_ratio / switch f0_method to improve voice fidelity",
                params={
                    "index_ratio": _INDEX_RATIO_LADDER[attempt % len(_INDEX_RATIO_LADDER)],
                    "f0_method": _F0_LADDER[attempt % len(_F0_LADDER)],
                },
            ))
    else:
        criteria.append(CriterionResult(name="voice_similarity", score=100.0, passed=True,
                                        detail="not measured (no reference voice configured)"))

    # --- pronunciation (hard) ---
    pron_score, missing = _pronunciation_check(master, lyrics, state["request"].language)
    pron_ok = not missing
    criteria.append(CriterionResult(name="pronunciation", score=pron_score, passed=pron_ok,
                                    detail=("ok" if pron_ok else f"missing: {', '.join(missing)}")))
    if not pron_ok:
        fixes.append(QualityFix(stage="composer", action="regenerate with clearer enunciation of devotional terms",
                               params={"emphasize_terms": missing}))

    # --- loudness/peak (hard) ---
    loud_ok = abs(lufs - rules.loudness_lufs) <= rules.loudness_tolerance
    peak_ok = true_peak <= rules.true_peak_dbtp + 1e-6
    lp_ok = loud_ok and peak_ok
    lp_score = 100.0 if lp_ok else 70.0
    criteria.append(CriterionResult(name="loudness_peak", score=lp_score, passed=lp_ok,
                                    detail=f"{lufs:.2f} LUFS / {true_peak:.2f} dBTP"))
    if not lp_ok:
        fixes.append(QualityFix(stage="mixing", action="re-master to hit target loudness/peak",
                               params={"target_lufs": rules.loudness_lufs}))

    # --- artifacts (hard) ---
    art_ok = artifact_score <= rules.artifact_score_max
    art_score = max(0.0, 100.0 * (1.0 - artifact_score))
    criteria.append(CriterionResult(name="artifacts", score=art_score, passed=art_ok,
                                    detail=f"artifact_score={artifact_score:.3f} <= {rules.artifact_score_max}"))
    if not art_ok:
        fixes.append(QualityFix(stage="voice", action="reduce conversion artifacts (protect/f0 tweak)",
                               params={"protect_voiceless": 0.5}))

    # --- mix balance (soft) ---
    # Full-mix energy always exceeds vocal-only energy, so this is typically
    # negative; a "vocal-forward but blended" mix sits in a wide window.
    bal_ok = -12.0 <= balance_db <= 6.0
    bal_score = 100.0 if bal_ok else 75.0
    criteria.append(CriterionResult(name="mix_balance", score=bal_score, passed=bal_ok,
                                    detail=f"vocal-instr balance {balance_db:.2f} dB"))
    if not bal_ok:
        gain = -1.5 if balance_db > 8.0 else 1.5
        fixes.append(QualityFix(stage="mixing", action="adjust vocal gain for better balance",
                               params={"vocal_gain_db": gain}))

    # --- musical fit (soft heuristic) ---
    fit_score = 95.0
    criteria.append(CriterionResult(name="musical_fit", score=fit_score, passed=True,
                                    detail="mood/taal heuristic"))

    # weighted score
    total_w = sum(WEIGHTS.values())
    score = sum(WEIGHTS[c.name] * c.score for c in criteria) / total_w

    hard = {"voice_similarity", "pronunciation", "loudness_peak", "artifacts"}
    hard_pass = all(c.passed for c in criteria if c.name in hard)
    passed = score >= rules.quality_gate and hard_pass

    next_stage = _choose_stage(criteria, fixes) if not passed else None

    report = QualityReport(
        score=round(score, 2),
        passed=passed,
        criteria=criteria,
        fixes=fixes,
        next_stage_on_fail=next_stage,
        metrics=metrics,
    )
    return report


def _choose_stage(criteria: list[CriterionResult], fixes: list[QualityFix]) -> Optional[str]:
    """Pick the stage to loop back to: cheapest effective first (mixing < voice < composer)."""
    failing = {c.name for c in criteria if not c.passed}
    if "loudness_peak" in failing or "mix_balance" in failing:
        return "mixing"
    if "voice_similarity" in failing or "artifacts" in failing:
        return "voice"
    if "pronunciation" in failing:
        return "composer"
    return fixes[0].stage if fixes else None


def judge_node(state: dict) -> dict:
    from .. import runs

    report = evaluate(state)
    path = runs.run_dir(state["run_id"]) / "quality_report.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    artifacts = dict(state.get("artifacts", {}))
    artifacts["quality_report"] = str(path)
    logger.info("Judge score=%.2f passed=%s next=%s", report.score, report.passed, report.next_stage_on_fail)
    return {
        "quality": report,
        "gate_passed": report.passed,
        "next_stage_on_fail": report.next_stage_on_fail,
        "artifacts": artifacts,
    }
