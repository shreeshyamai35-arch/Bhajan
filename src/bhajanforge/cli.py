"""BhajanForge command-line interface (Typer).

Surface (PRD §"Key Commands"):
    bhajanforge produce ...        run the full pipeline; save bundle locally
    bhajanforge publish --run-id   re-package a run
    bhajanforge voice train ...    train/retrain the cloud RVC voice model
    bhajanforge kb ingest ...       ingest documents into the RAG store
    bhajanforge status --run-id    show pipeline status / resume
    bhajanforge serve              start the FastAPI trigger server
"""

from __future__ import annotations

import json
from typing import Optional

import typer

from . import __version__
from .config import load_rules
from .logging_utils import get_logger
from .models import Mood, ProductionRequest

app = typer.Typer(
    add_completion=False,
    help="BhajanForge — autonomous devotional bhajan production (CPU-only, local save).",
)
voice_app = typer.Typer(help="Voice model training / management.")
kb_app = typer.Typer(help="RAG knowledge-base management.")
suno_app = typer.Typer(help="Suno music provider utilities.")
app.add_typer(voice_app, name="voice")
app.add_typer(kb_app, name="kb")
app.add_typer(suno_app, name="suno")

logger = get_logger("cli")


@app.callback(invoke_without_command=True)
def _root(version: bool = typer.Option(False, "--version", help="Show version.")) -> None:
    if version:
        typer.echo(f"BhajanForge {__version__}")
        raise typer.Exit()


@app.command()
def produce(
    theme: str = typer.Option(..., help="What the bhajan is about."),
    mood: Mood = typer.Option(Mood.slow_emotional, help="Emotional mood."),
    deity: str = typer.Option("Khatu Shyam", help="Devotional subject."),
    taal: str = typer.Option("keherwa", help="Rhythmic cycle."),
    tempo: int = typer.Option(72, help="Tempo in BPM."),
    language: str = typer.Option("hi", help="Lyric language."),
    duration: int = typer.Option(240, help="Target duration (seconds)."),
    candidates: int = typer.Option(2, help="Suno candidates to generate."),
    run_id: Optional[str] = typer.Option(None, help="Resume an existing run."),
) -> None:
    """Run the full pipeline and save a local bundle (NO upload)."""
    rules = load_rules()
    request = ProductionRequest(
        theme=theme,
        mood=mood,
        deity=deity,
        taal=taal,
        tempo=tempo,
        language=language,
        duration_target_sec=duration,
        candidates=candidates,
        publish_mode=rules.publish_mode,
        publish_target=rules.publish_target,
    )
    try:
        from .graph import run_pipeline  # imported lazily (heavy deps)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[produce] pipeline not available yet: {exc}")
        typer.echo(f"[produce] validated request: {request.model_dump()}")
        raise typer.Exit(code=0)
    result = run_pipeline(request, run_id=run_id)
    typer.echo(f"[produce] done: {result}")


@app.command()
def publish(run_id: str = typer.Option(..., help="Run to (re)package.")) -> None:
    """Re-package a run (rebuild bundle/video; upload only if PUBLISH_TARGET=youtube)."""
    try:
        from .graph import repackage
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[publish] packager not available yet: {exc}")
        raise typer.Exit(code=0)
    typer.echo(repackage(run_id))


@app.command()
def status(run_id: str = typer.Option(..., help="Run to inspect.")) -> None:
    """Show pipeline status from the manifest + checkpoint."""
    from .runs import load_manifest

    try:
        manifest = load_manifest(run_id)
    except FileNotFoundError:
        typer.echo(f"[status] no run found: {run_id}")
        raise typer.Exit(code=1)
    typer.echo(manifest.model_dump_json(indent=2))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the FastAPI trigger server."""
    import uvicorn

    uvicorn.run("bhajanforge.api:api", host=host, port=port, reload=False)


@voice_app.command("train")
def voice_train(
    youtube_urls: Optional[str] = typer.Option(None, help="File of YouTube URLs."),
    dataset: Optional[str] = typer.Option(None, help="Folder/zip of clean vocals."),
    model_name: str = typer.Option("shyam_voice_v1", help="Voice model name."),
) -> None:
    """Train/retrain the cloud RVC voice model (FR-23)."""
    try:
        from .agents.voice import train_voice_model
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[voice train] not available yet: {exc}")
        raise typer.Exit(code=0)
    typer.echo(train_voice_model(youtube_urls=youtube_urls, dataset=dataset, model_name=model_name))


@kb_app.command("ingest")
def kb_ingest(source: str = typer.Option(..., help="Folder of documents to ingest.")) -> None:
    """Ingest documents into the RAG store (Qdrant)."""
    try:
        from .rag.ingest import ingest_path
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[kb ingest] RAG not available yet: {exc}")
        raise typer.Exit(code=0)
    typer.echo(ingest_path(source))


@suno_app.command("health")
def suno_health_cmd() -> None:
    """Check the active Suno provider's auth (verifies your cookie/JWT or key).

    Exits non-zero if the provider is not authenticated, so it is usable as a
    pre-flight gate in scripts before launching a full production run."""
    from .mcp_servers.suno_mcp import suno_health

    result = suno_health()
    typer.echo(json.dumps(result, indent=2))
    if not (result.get("ok") and result.get("authenticated")):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
