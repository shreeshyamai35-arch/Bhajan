"""Configuration loading for BhajanForge.

Loads, in order of precedence for thresholds:
  1. environment variables (.env)
  2. machine-readable YAML block inside config/rules.md
  3. RulesConfig defaults

Also exposes typed access to provider settings and paths.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

from .models import RulesConfig

# Repo root = two levels up from this file (src/bhajanforge/config.py -> repo).
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
RULES_PATH = CONFIG_DIR / "rules.md"
LEARNING_PATH = CONFIG_DIR / "learning.yaml"


def _load_env() -> None:
    """Load .env from repo root if present (idempotent)."""
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
    else:
        load_dotenv(override=False)


def _extract_rules_yaml(rules_md: str) -> dict[str, Any]:
    """Pull the machine-readable ```yaml ...``` block out of rules.md."""
    match = re.search(r"```yaml\s*(.*?)```", rules_md, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


def load_rules(path: Optional[Path] = None) -> RulesConfig:
    """Load and validate the governance thresholds from rules.md.

    Environment variables override file values where applicable.
    """
    path = path or RULES_PATH
    data: dict[str, Any] = {}
    if path.exists():
        data = _extract_rules_yaml(path.read_text(encoding="utf-8"))

    # Environment overrides (mirror config/.env.example).
    _load_env()
    if os.getenv("QUALITY_GATE"):
        data["quality_gate"] = int(os.environ["QUALITY_GATE"])
    if os.getenv("MAX_LOOP_ATTEMPTS"):
        data["max_loop_attempts"] = int(os.environ["MAX_LOOP_ATTEMPTS"])
    if os.getenv("MAX_TOTAL_LOOPS"):
        data["max_total_loops"] = int(os.environ["MAX_TOTAL_LOOPS"])
    if os.getenv("PUBLISH_MODE"):
        data["publish_mode"] = os.environ["PUBLISH_MODE"]
    if os.getenv("PUBLISH_TARGET"):
        data["publish_target"] = os.environ["PUBLISH_TARGET"]

    rules = RulesConfig(**data)

    # Hard invariants — never weaken safety rails (R3.1 / R2.1 / R2.3).
    if rules.quality_gate < rules.min_quality_gate:
        raise ValueError(
            f"quality_gate ({rules.quality_gate}) must be >= "
            f"min_quality_gate ({rules.min_quality_gate})"
        )
    if rules.allow_third_party_voice:
        raise ValueError("allow_third_party_voice MUST stay false (R2.1).")
    if not rules.require_ai_disclosure:
        raise ValueError("require_ai_disclosure MUST stay true (R2.3).")
    return rules


def load_learning(path: Optional[Path] = None) -> dict[str, Any]:
    """Load the learning.yaml snapshot as a plain dict."""
    path = path or LEARNING_PATH
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _b(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Typed accessor over environment variables (cloud providers + paths)."""

    def __init__(self) -> None:
        _load_env()

    # --- paths ---
    @property
    def runs_dir(self) -> Path:
        return REPO_ROOT / os.getenv("RUNS_DIR", "./runs").lstrip("./")

    @property
    def output_dir(self) -> Path:
        return REPO_ROOT / os.getenv("OUTPUT_DIR", "./output").lstrip("./")

    @property
    def rvc_models_dir(self) -> Path:
        return REPO_ROOT / os.getenv("RVC_MODELS_DIR", "./models/rvc").lstrip("./")

    # --- LLM / embeddings ---
    @property
    def llm_provider(self) -> str:
        return os.getenv("LLM_PROVIDER", "")

    @property
    def llm_model(self) -> str:
        return os.getenv("LLM_MODEL", "")

    @property
    def embedding_model(self) -> str:
        return os.getenv("EMBEDDING_MODEL", "")

    # --- providers ---
    @property
    def voice_provider(self) -> str:
        return os.getenv("VOICE_PROVIDER", "replicate")

    @property
    def stem_provider(self) -> str:
        return os.getenv("STEM_PROVIDER", "lalal")

    @property
    def mastering_provider(self) -> str:
        return os.getenv("MASTERING_PROVIDER", "landr")

    @property
    def suno_api_base(self) -> str:
        return os.getenv("SUNO_API_BASE", "")

    @property
    def suno_use_browser(self) -> bool:
        return _b("SUNO_USE_BROWSER", False)

    @property
    def make_video(self) -> bool:
        return _b("MAKE_VIDEO", False)

    @property
    def publish_target(self) -> str:
        return os.getenv("PUBLISH_TARGET", "local")

    @property
    def qdrant_url(self) -> str:
        return os.getenv("QDRANT_URL", "http://localhost:6333")

    @property
    def qdrant_collection(self) -> str:
        return os.getenv("QDRANT_COLLECTION", "bhajan_kb")

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO")

    def get(self, key: str, default: str = "") -> str:
        return os.getenv(key, default)

    def is_mock(self) -> bool:
        """True when no live provider keys are configured (offline/test mode)."""
        return _b("BHAJANFORGE_MOCK", False) or not (
            os.getenv("LLM_API_KEY") or os.getenv("REPLICATE_API_TOKEN")
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
