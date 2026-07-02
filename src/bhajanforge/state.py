"""LangGraph shared state for BhajanForge (see docs/ORCHESTRATION.md §1)."""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from .models import (
    LyricsDoc,
    MixResult,
    MusicResult,
    ProductionRequest,
    PublishResult,
    QualityReport,
    RulesConfig,
    VoiceResult,
)


class BhajanState(TypedDict, total=False):
    run_id: str
    request: ProductionRequest
    rules: RulesConfig
    learning: dict
    lyrics: LyricsDoc
    music: MusicResult
    voice: VoiceResult
    mix: MixResult
    quality: QualityReport
    publish: PublishResult
    # control
    gate_passed: bool
    next_stage_on_fail: Optional[str]  # "composer" | "voice" | "mixing"
    loop_counts: dict
    total_loops: int
    halted: bool
    halt_reason: Optional[str]
    artifacts: dict  # name -> path
    errors: list


def initial_state(
    run_id: str,
    request: ProductionRequest,
    rules: RulesConfig,
    learning: dict,
) -> BhajanState:
    return BhajanState(
        run_id=run_id,
        request=request,
        rules=rules,
        learning=learning,
        gate_passed=False,
        next_stage_on_fail=None,
        loop_counts={},
        total_loops=0,
        halted=False,
        halt_reason=None,
        artifacts={},
        errors=[],
    )
