# BhajanForge — Data Models (Pydantic v2)

Authoritative data contracts. Codex: implement in `src/bhajanforge/` (e.g.
`models.py`) and reuse across agents, MCP clients, and the API.

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum

# --------------------------------------------------------------------------
# INTAKE
# --------------------------------------------------------------------------
class Mood(str, Enum):
    slow_emotional = "slow-emotional"
    celebratory = "celebratory"
    meditative = "meditative"

class ProductionRequest(BaseModel):
    theme: str
    mood: Mood = Mood.slow_emotional
    deity: str = "Khatu Shyam"
    taal: str = "keherwa"
    tempo: int = 72                       # BPM
    language: str = "hi"
    duration_target_sec: int = 240
    lyrics_override: Optional[str] = None
    candidates: int = 2                   # Suno candidates
    publish_mode: Literal["draft", "auto"] = "draft"
    publish_target: Literal["local", "youtube"] = "local"   # default: save to PC, no upload

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
    devotional_terms: list[str] = []      # verified against KB
    rag_confidence: float = 1.0           # 0..1
    def as_suno_text(self) -> str: ...     # flatten to Suno-friendly lyrics

# --------------------------------------------------------------------------
# MUSIC (SUNO)
# --------------------------------------------------------------------------
class MusicCandidate(BaseModel):
    clip_id: str
    audio_path: str
    instrumental_path: Optional[str] = None
    guide_vocal_path: Optional[str] = None
    duration_sec: float
    score: Optional[float] = None         # composer heuristic

class MusicResult(BaseModel):
    style_prompt_used: str
    winning_prompt_key: Optional[str] = None
    candidates: list[MusicCandidate]
    chosen_index: int
    @property
    def chosen(self) -> MusicCandidate: return self.candidates[self.chosen_index]

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
    output_path: str                      # my_voice.wav
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
    score: float                          # 0..100 contribution-normalized
    passed: bool
    detail: str = ""

class QualityFix(BaseModel):
    stage: Literal["composer", "voice", "mixing"]
    action: str                           # human-readable fix
    params: dict = {}                     # concrete params to apply on re-run

class QualityReport(BaseModel):
    score: float                          # 0..100 weighted
    passed: bool
    criteria: list[CriterionResult]
    fixes: list[QualityFix] = []
    next_stage_on_fail: Optional[Literal["composer","voice","mixing"]] = None
    metrics: dict = {}                    # raw audio.analyze output

# --------------------------------------------------------------------------
# PUBLISH
# --------------------------------------------------------------------------
class PublishResult(BaseModel):
    title: str
    description: str
    tags: list[str]
    thumbnail_path: Optional[str] = None
    video_path: Optional[str] = None
    output_dir: Optional[str] = None      # OUTPUT_DIR/{date}_{slug}/ (local bundle)
    youtube_video_id: Optional[str] = None
    youtube_url: Optional[str] = None
    ai_disclosure_set: bool = True        # MUST be true IF uploaded (R2.3)
    status: Literal["saved_local","draft","published","needs_human","failed"] = "saved_local"

# --------------------------------------------------------------------------
# RUN MANIFEST (persisted to runs/{id}/manifest.json)
# --------------------------------------------------------------------------
class RunManifest(BaseModel):
    run_id: str
    created_at: str
    request: ProductionRequest
    artifacts: dict[str, str] = {}        # name -> path
    scores: dict = {}                     # judge_score, voice_similarity, lufs...
    loops_used: dict[str, int] = {}
    total_loops: int = 0
    decision: Literal["saved_local","published","draft","needs_human","failed"] = "saved_local"
    failure_summary: Optional[str] = None
```

## Validation rules (enforced)
- `ProductionRequest`: reject if genre/deity is non-devotional (rules R1.1).
- `PublishResult`: if `status=="published"` then `ai_disclosure_set` MUST be true.
- `VoiceResult`: `voice_similarity` (when present) must meet R3.4 to pass the gate.
- `QualityReport`: `passed == (score >= QUALITY_GATE and all hard criteria passed)`.
