"""LangGraph orchestration (M7) — see docs/ORCHESTRATION.md.

Wires the agents into a stateful pipeline with a quality-gate correction loop
and ethics hard-stops. Exposes ``run_pipeline`` (used by CLI/API) and re-exports
``repackage`` from the packager.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from langgraph.graph import END, StateGraph

from .agents import packager as packager_agent
from .agents.composer import composer_node
from .agents.lyricist import lyricist_node
from .agents.mixing import mixing_node
from .agents.quality_judge import judge_node
from .agents.voice import voice_node
from .config import load_learning, load_rules
from .logging_utils import get_logger
from .memory import learning as mem
from .models import ProductionRequest, RulesConfig
from .runs import init_run, load_manifest, run_dir, save_manifest
from .state import BhajanState, initial_state

logger = get_logger("graph")

# Re-export so cli.py / api.py can `from .graph import repackage`.
repackage = packager_agent.repackage

_NON_DEVOTIONAL = re.compile(
    r"\b(rap|edm|techno|pop song|item song|party anthem|club|rock band|metal|hip[- ]?hop|"
    r"romantic|love song|drinking|alcohol)\b",
    re.IGNORECASE,
)
_THIRD_PARTY_VOICE = re.compile(
    r"\b(?:clone|mimic|imitate|in the voice of|sound like|copy)\b.{0,40}\bvoice\b|"
    r"\bvoice of\s+(?!the\s+artist\b)\w+",
    re.IGNORECASE,
)


def validate_request(request: ProductionRequest, rules: RulesConfig) -> tuple[bool, Optional[str]]:
    """Enforce ethics hard-stops (R1.1, R2.1). Returns (halted, reason)."""
    blob = " ".join(filter(None, [request.theme, request.deity, request.lyrics_override or ""]))

    if rules.devotional_only and _NON_DEVOTIONAL.search(blob):
        return True, "non-devotional content requested (R1.1)"

    if not rules.allow_third_party_voice and _THIRD_PARTY_VOICE.search(blob):
        return True, "third-party voice cloning requested — refused and halted (R2.1)"

    return False, None


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------


def intake_node(state: dict) -> dict:
    request: ProductionRequest = state["request"]
    rules: RulesConfig = state["rules"]
    halted, reason = validate_request(request, rules)
    if halted:
        logger.error("Intake HALT: %s", reason)
        return {"halted": True, "halt_reason": reason}
    logger.info("Intake OK for run %s", state["run_id"])
    return {"halted": False}


def packager_node(state: dict) -> dict:
    result = packager_agent.package(state)
    artifacts = dict(state.get("artifacts", {}))
    if result.output_dir:
        artifacts["output_dir"] = result.output_dir
    return {"publish": result, "artifacts": artifacts}


def memory_node(state: dict) -> dict:
    """Persist learnings (FR-24) + write the final run manifest (R8.3)."""
    run_id = state["run_id"]
    request: ProductionRequest = state["request"]
    quality = state.get("quality")
    publish = state.get("publish")

    if state.get("halted"):
        decision = "failed"
        failure = state.get("halt_reason")
    elif state.get("gate_passed") and publish is not None:
        decision = publish.status
        failure = None
    elif not state.get("gate_passed"):
        decision = "needs_human"
        failure = "quality gate not met after max loops"
    else:
        decision = "saved_local"
        failure = None

    # Update the Learning File (only on a real completed run).
    if quality is not None and not state.get("halted"):
        voice = state.get("voice")
        mix = state.get("mix")
        music = state.get("music")
        entry = {
            "run_id": run_id,
            "theme": request.theme,
            "mood": request.mood.value,
            "judge_score": getattr(quality, "score", None),
            "voice_similarity": getattr(voice, "voice_similarity", None),
            "lufs": getattr(mix, "lufs", None),
            "true_peak_dbtp": getattr(mix, "true_peak_dbtp", None),
            "loops_used": state.get("total_loops", 0),
            "winning_prompt_key": getattr(music, "winning_prompt_key", None),
            "published": decision == "published",
        }
        try:
            mem.record_run(entry)
            if getattr(quality, "passed", False) and voice is not None:
                mem.update_best_settings(voice.settings_used.model_dump())
        except Exception as exc:  # noqa: BLE001 - memory is non-fatal
            logger.warning("learning update failed: %s", exc)

    # Write the manifest.
    try:
        manifest = load_manifest(run_id)
    except Exception:
        manifest = init_run(request, run_id=run_id)
    manifest.artifacts.update({k: str(v) for k, v in (state.get("artifacts", {}) or {}).items()})
    manifest.scores = {
        "judge_score": getattr(quality, "score", None),
        "voice_similarity": getattr(state.get("voice"), "voice_similarity", None),
        "lufs": getattr(state.get("mix"), "lufs", None),
        "true_peak_dbtp": getattr(state.get("mix"), "true_peak_dbtp", None),
    }
    manifest.loops_used = state.get("loop_counts", {}) or {}
    manifest.total_loops = state.get("total_loops", 0)
    manifest.decision = decision  # type: ignore[assignment]
    manifest.failure_summary = failure
    save_manifest(manifest)

    return {}


# --------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------


def intake_router(state: dict) -> str:
    return "halted" if state.get("halted") else "ok"


def judge_node_with_loop(state: dict) -> dict:
    """Run the judge, then decide routing + increment loop counters (R4.*)."""
    update = judge_node(state)
    rules: RulesConfig = state["rules"]

    if update.get("gate_passed"):
        update["_route"] = "packager"
        return update

    stage = update.get("next_stage_on_fail")
    counts = dict(state.get("loop_counts", {}) or {})
    total = int(state.get("total_loops", 0))
    can_loop = (
        stage is not None
        and counts.get(stage, 0) < rules.max_loop_attempts
        and total < rules.max_total_loops
    )
    if can_loop:
        counts[stage] = counts.get(stage, 0) + 1
        update["loop_counts"] = counts
        update["total_loops"] = total + 1
        update["_route"] = stage
        logger.info("Looping back to '%s' (attempt %d, total %d)", stage, counts[stage], total + 1)
    else:
        update["_route"] = "needs_human"
        logger.warning("Quality gate exhausted; escalating to human")
    return update


def judge_router(state: dict) -> str:
    return state.get("_route", "needs_human")


# --------------------------------------------------------------------------
# Graph assembly
# --------------------------------------------------------------------------


def build_graph():
    g = StateGraph(BhajanState)
    g.add_node("intake", intake_node)
    g.add_node("lyricist", lyricist_node)
    g.add_node("composer", composer_node)
    g.add_node("voice", voice_node)
    g.add_node("mixing", mixing_node)
    g.add_node("judge", judge_node_with_loop)
    g.add_node("packager", packager_node)
    g.add_node("memory", memory_node)

    g.set_entry_point("intake")
    g.add_conditional_edges("intake", intake_router, {"halted": "memory", "ok": "lyricist"})
    g.add_edge("lyricist", "composer")
    g.add_edge("composer", "voice")
    g.add_edge("voice", "mixing")
    g.add_edge("mixing", "judge")
    g.add_conditional_edges(
        "judge",
        judge_router,
        {
            "packager": "packager",
            "composer": "composer",
            "voice": "voice",
            "mixing": "mixing",
            "needs_human": "memory",
        },
    )
    g.add_edge("packager", "memory")
    g.add_edge("memory", END)
    return g.compile()


def run_pipeline(request: ProductionRequest, run_id: Optional[str] = None) -> dict:
    """Run the full pipeline end-to-end and return a result summary."""
    rules = load_rules()
    learning = load_learning()

    manifest = init_run(request, run_id=run_id)
    rid = manifest.run_id

    # Resumability (AC-5): if this run already produced a saved bundle, skip.
    master = run_dir(rid) / "master.wav"
    if manifest.decision in {"saved_local", "published", "draft"} and master.exists():
        logger.info("Run %s already complete (%s); skipping.", rid, manifest.decision)
        return {"run_id": rid, "decision": manifest.decision, "resumed": True,
                "output_dir": manifest.artifacts.get("output_dir")}

    state = initial_state(rid, request, rules, learning)
    app = build_graph()
    final = app.invoke(state, config={"recursion_limit": 50})

    quality = final.get("quality")
    publish = final.get("publish")
    return {
        "run_id": rid,
        "decision": (publish.status if publish else ("failed" if final.get("halted") else "needs_human")),
        "score": getattr(quality, "score", None),
        "passed": getattr(quality, "passed", False),
        "output_dir": getattr(publish, "output_dir", None),
        "halted": final.get("halted", False),
        "halt_reason": final.get("halt_reason"),
        "total_loops": final.get("total_loops", 0),
    }
