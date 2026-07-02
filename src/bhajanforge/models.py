"""BhajanForge data models (Pydantic v2).

Authoritative data contracts (see docs/DATA_MODELS.md). Reused across agents,
MCP clients, the orchestration state, and the API.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# INTAKE
# --------------------------------------------------------------------------


class Mood(str, Enum):
    slow_emotional = "slow-emotional"
    celebratory = "celebratory"
    meditative = "meditative"


class ProductionRequest(BaseModel):
    theme: str = Field(min_length=1, max_length=200)
    mood: Mood = Mood.slow_emotional
    deity: str = Field(default="Khatu Shyam", max_length=100)
    taal: str = Field(default="keherwa", max_length=50)
    tempo: int = Field(default=72, ge=30, le=300)  # BPM
    language: str = Field(default="hi", max_length=20)
    duration_target_sec: int = Field(default=240, ge=30, le=900)
    lyrics_override: Optional[str] = Field(default=None, max_length=8000)
    candidates: int = Field(default=2, ge=1, le=4)  # Suno candidates
    publish_mode: Literal["draft", "auto"] = "draft"
    publish_target: Literal["local", "youtube"] = "local"  # default: save to PC


# --------------------------------------------------------------------------
# LYRICS
# --------------------------------------------------------------------------


class LyricLine(BaseModel):
    text: str
    pronunciation_hint: Optional[str] = None


class LyricSection(BaseModel):
    name: Literal["mukhda", "antara", "aarti_outro"]
    lines: list[LyricLine]


class LyricsDoc(BaseModel):
    title_working: str
    language: str = "hi"
    sections: list[LyricSection]
    devotional_terms: list[str] = Field(default_factory=list)  # verified vs KB
    rag_confidence: float = 1.0  # 0..1

    def as_suno_text(self) -> str:
        """Flatten structured lyrics to Suno-friendly text with section tags."""
        blocks: list[str] = []
        for section in self.sections:
            tag = {
                "mukhda": "[Chorus]",
                "antara": "[Verse]",
                "aarti_outro": "[Outro]",
            }.get(section.name, f"[{section.name}]")
            lines = "\n".join(line.text for line in section.lines)
            blocks.append(f"{tag}\n{lines}")
        return "\n\n".join(blocks)


# --------------------------------------------------------------------------
# MUSIC (SUNO)
# --------------------------------------------------------------------------


class MusicCandidate(BaseModel):
    clip_id: str
    audio_path: str
    instrumental_path: Optional[str] = None
    guide_vocal_path: Optional[str] = None
    duration_sec: float
    score: Optional[float] = None  # composer heuristic


class MusicResult(BaseModel):
    style_prompt_used: str
    winning_prompt_key: Optional[str] = None
    candidates: list[MusicCandidate]
    chosen_index: int

    @property
    def chosen(self) -> MusicCandidate:
        return self.candidates[self.chosen_index]


# --------------------------------------------------------------------------
# VOICE
# --------------------------------------------------------------------------


class VoiceSettings(BaseModel):
    model_name: str
    pitch_shift_semitones: int = 0
    index_ratio: float = 0.75
    f0_method: Literal["rmvpe", "crepe", "fcpe"] = "rmvpe"
    protect_voiceless: float = 0.33
    resample_sr: int = 48000


class VoiceResult(BaseModel):
    output_path: str  # my_voice.wav
    settings_used: VoiceSettings
    voice_similarity: Optional[float] = None
    used_ace_studio: bool = False


# --------------------------------------------------------------------------
# MIX / MASTER
# --------------------------------------------------------------------------


class MixResult(BaseModel):
    premaster_path: str
    master_path: str
    offset_ms: int = 0
    lufs: Optional[float] = None
    true_peak_dbtp: Optional[float] = None
    used_landr: bool = False


# --------------------------------------------------------------------------
# QUALITY
# --------------------------------------------------------------------------


class CriterionResult(BaseModel):
    name: str
    score: float  # 0..100 contribution-normalized
    passed: bool
    detail: str = ""


class QualityFix(BaseModel):
    stage: Literal["composer", "voice", "mixing"]
    action: str  # human-readable fix
    params: dict = Field(default_factory=dict)  # concrete params for re-run


class QualityReport(BaseModel):
    score: float  # 0..100 weighted
    passed: bool
    criteria: list[CriterionResult]
    fixes: list[QualityFix] = Field(default_factory=list)
    next_stage_on_fail: Optional[Literal["composer", "voice", "mixing"]] = None
    metrics: dict = Field(default_factory=dict)  # raw audio.analyze output


# --------------------------------------------------------------------------
# PUBLISH
# --------------------------------------------------------------------------


class PublishResult(BaseModel):
    title: str
    description: str
    tags: list[str]
    thumbnail_path: Optional[str] = None
    video_path: Optional[str] = None
    output_dir: Optional[str] = None  # OUTPUT_DIR/{date}_{slug}/ (local bundle)
    youtube_video_id: Optional[str] = None
    youtube_url: Optional[str] = None
    ai_disclosure_set: bool = True  # MUST be true IF uploaded (R2.3)
    status: Literal["saved_local", "draft", "published", "needs_human", "failed"] = (
        "saved_local"
    )


# --------------------------------------------------------------------------
# RUN MANIFEST (persisted to runs/{id}/manifest.json)
# --------------------------------------------------------------------------


class RunManifest(BaseModel):
    run_id: str
    created_at: str
    request: ProductionRequest
    artifacts: dict[str, str] = Field(default_factory=dict)  # name -> path
    scores: dict = Field(default_factory=dict)  # judge_score, similarity, lufs...
    loops_used: dict[str, int] = Field(default_factory=dict)
    total_loops: int = 0
    decision: Literal["saved_local", "published", "draft", "needs_human", "failed"] = (
        "saved_local"
    )
    failure_summary: Optional[str] = None


# --------------------------------------------------------------------------
# RULES CONFIG (machine-readable thresholds loaded from config/rules.md)
# --------------------------------------------------------------------------


class RulesConfig(BaseModel):
    quality_gate: int = 95
    min_quality_gate: int = 90
    loudness_lufs: float = -14.0
    loudness_tolerance: float = 1.0
    true_peak_dbtp: float = -1.0
    voice_similarity_min: float = 0.95
    artifact_score_max: float = 0.20
    max_loop_attempts: int = 4
    max_total_loops: int = 8
    max_silence_gap_sec: float = 2.5
    publish_mode: Literal["draft", "auto"] = "draft"
    publish_target: Literal["local", "youtube"] = "local"
    devotional_only: bool = True
    allow_third_party_voice: bool = False
    require_ai_disclosure: bool = True
