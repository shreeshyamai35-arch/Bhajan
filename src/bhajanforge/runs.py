"""Run directory + manifest handling (NFR-3, R8.3).

Every stage is idempotent and resumable by run_id. Artifacts persist under
runs/{run_id}/ and a manifest.json captures inputs, settings, scores, paths.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import get_settings
from .models import ProductionRequest, RunManifest


_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def validate_run_id(run_id: str) -> str:
    """Reject run_ids that could escape the runs/ directory (path traversal).

    Run ids are date + slug (e.g. ``2026-06-23_morning-darshan``); anything
    containing ``/``, ``\\``, ``..`` or other unexpected characters is refused.
    """
    if not run_id or not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    return run_id


def slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:max_len] or "bhajan"


def new_run_id(theme: str) -> str:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{date}_{slugify(theme)}"


def run_dir(run_id: str) -> Path:
    validate_run_id(run_id)
    d = get_settings().runs_dir / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifest_path(run_id: str) -> Path:
    return run_dir(run_id) / "manifest.json"


def init_run(request: ProductionRequest, run_id: Optional[str] = None) -> RunManifest:
    """Create (or load) a run and its manifest. Idempotent by run_id."""
    rid = run_id or new_run_id(request.theme)
    path = manifest_path(rid)
    if path.exists():
        return load_manifest(rid)
    manifest = RunManifest(
        run_id=rid,
        created_at=datetime.now(timezone.utc).isoformat(),
        request=request,
    )
    save_manifest(manifest)
    # standard sub-directories
    for sub in ("suno", "stems", "voice", "mix"):
        (run_dir(rid) / sub).mkdir(parents=True, exist_ok=True)
    return manifest


def save_manifest(manifest: RunManifest) -> Path:
    path = manifest_path(manifest.run_id)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_manifest(run_id: str) -> RunManifest:
    data = json.loads(manifest_path(run_id).read_text(encoding="utf-8"))
    return RunManifest(**data)


def artifact_exists(run_id: str, rel_path: str) -> bool:
    """Idempotency helper: True if an artifact already exists and is non-empty."""
    p = run_dir(run_id) / rel_path
    return p.exists() and p.stat().st_size > 0
