"""FastAPI trigger + status server (PRD §5.1) with a simple browser UI.

Endpoints:
    GET  /                -> browser UI (HTML)
    POST /produce         -> run the pipeline, returns the result summary
    GET  /status/{id}     -> manifest snapshot (JSON)
    GET  /healthz         -> liveness
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from . import __version__
from .models import ProductionRequest
from .runs import init_run, load_manifest, validate_run_id

api = FastAPI(title="BhajanForge", version=__version__)

# CORS. With allow_credentials=False a wildcard origin cannot read authenticated
# responses, so this is acceptable for local use; real protection for mutating
# endpoints is the optional API key below (set BHAJANFORGE_API_KEY to enforce).
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _check_auth(x_api_key: str | None) -> None:
    """Enforce an API key IFF BHAJANFORGE_API_KEY is set (off by default for
    local single-user use; set it before exposing the server)."""
    expected = os.getenv("BHAJANFORGE_API_KEY", "").strip()
    if expected and (x_api_key or "") != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


@api.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "version": __version__}


@api.post("/produce")
def produce(request: ProductionRequest,
            x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict:
    """Create a run, launch the pipeline, and return the result summary."""
    _check_auth(x_api_key)
    manifest = init_run(request)
    result: dict = {"ok": True, "run_id": manifest.run_id, "decision": "queued"}
    try:
        from .graph import run_pipeline

        outcome = run_pipeline(request, run_id=manifest.run_id)
        result.update(outcome)
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["error"] = str(exc)
    return result


@api.get("/suno/health")
def suno_health_endpoint(
    x_api_key: str | None = Header(default=None, alias="X-API-Key")
) -> dict:
    """Check whether the active Suno provider is authenticated.

    For the self-hosted provider this verifies your session cookie by
    refreshing a Clerk JWT (no audio is generated, no credits spent)."""
    _check_auth(x_api_key)
    from .mcp_servers.suno_mcp import suno_health

    return suno_health()


@api.get("/status/{run_id}")
def status(run_id: str,
           x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict:
    _check_auth(x_api_key)
    try:
        validate_run_id(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid run_id") from exc
    try:
        manifest = load_manifest(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    return manifest.model_dump()


@api.get("/notebook")
def notebook(
    x_api_key: str | None = Header(default=None, alias="X-API-Key")
) -> FileResponse:
    """Serve the Colab voice-training notebook for download (so it can be
    uploaded to Colab without needing the GitHub repo)."""
    _check_auth(x_api_key)
    # api.py -> bhajanforge -> src -> project root
    root = Path(__file__).resolve().parents[2]
    nb = root / "notebooks" / "voice_clone_colab.ipynb"
    if not nb.exists():
        raise HTTPException(status_code=404, detail="notebook not found")
    return FileResponse(
        path=str(nb),
        media_type="application/x-ipynb+json",
        filename="voice_clone_colab.ipynb",
    )


@api.get("/", response_class=HTMLResponse)
def home() -> str:
    """A minimal devotional-themed web UI for triggering a production."""
    return _PAGE


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>BhajanForge</title>
<style>
  :root { --saffron:#e07b2e; --deep:#7a2e0e; --cream:#fff7ee; --gold:#caa14a; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: "Segoe UI", system-ui, sans-serif;
         background: radial-gradient(circle at 50% -10%, #fff 0%, var(--cream) 45%, #f3e3cf 100%);
         color:#3a2412; min-height:100vh; }
  header { text-align:center; padding:32px 16px 8px; }
  header h1 { margin:0; font-size:2.4rem; color:var(--deep); letter-spacing:.5px; }
  header .om { font-size:2.6rem; color:var(--saffron); }
  header p { margin:6px 0 0; color:#7a5a3c; }
  .wrap { max-width:760px; margin:0 auto; padding:16px 20px 60px; }
  .card { background:#fffdf9; border:1px solid #ecd9bf; border-radius:14px;
          padding:22px 24px; box-shadow:0 6px 24px rgba(122,46,14,.08); margin-top:18px; }
  label { display:block; font-weight:600; margin:14px 0 6px; font-size:.92rem; color:var(--deep); }
  input, select, textarea { width:100%; padding:10px 12px; border:1px solid #e0cdb0; border-radius:8px;
                  font-size:1rem; background:#fff; }
  .row { display:flex; gap:14px; } .row > div { flex:1; }
  button { margin-top:20px; width:100%; padding:13px; border:0; border-radius:10px;
           background:linear-gradient(180deg,var(--saffron),#c4631d); color:#fff; font-size:1.05rem;
           font-weight:700; cursor:pointer; letter-spacing:.3px; }
  button:disabled { opacity:.6; cursor:wait; }
  #out { white-space:pre-wrap; }
  .badge { display:inline-block; padding:4px 12px; border-radius:999px; font-weight:700; }
  .pass { background:#e6f6e6; color:#1f7a1f; } .fail { background:#fdeaea; color:#a32020; }
  .muted { color:#8a6c4e; font-size:.85rem; }
  .score { font-size:2.2rem; font-weight:800; color:var(--deep); }
  a { color:var(--saffron); }
</style>
</head>
<body>
  <header>
    <div class="om">&#x1F549;</div>
    <h1>BhajanForge</h1>
    <p>Autonomous devotional bhajan production &mdash; saved locally, sung in the artist's voice</p>
    <p class="muted">Running in mock mode &middot; add provider keys in <code>.env</code> for real audio</p>
  </header>
  <div class="wrap">
    <div class="card">
      <label>Theme</label>
      <input id="theme" value="morning darshan of Khatu Shyam"/>
      <div class="row">
        <div>
          <label>Mood</label>
          <select id="mood">
            <option value="slow-emotional">slow-emotional</option>
            <option value="celebratory">celebratory</option>
            <option value="meditative">meditative</option>
          </select>
        </div>
        <div>
          <label>Deity</label>
          <input id="deity" value="Khatu Shyam"/>
        </div>
      </div>
      <div class="row">
        <div><label>Taal</label><input id="taal" value="keherwa"/></div>
        <div><label>Tempo (BPM)</label><input id="tempo" type="number" value="72"/></div>
      </div>
      <label>Your own lyrics (optional)</label>
      <textarea id="lyrics" rows="7" placeholder="Paste your existing bhajan lyrics here to use them exactly. Leave blank and the AI will write authentic lyrics for you."></textarea>
      <p class="muted" style="margin:6px 0 0">Tip: separate the mukhda and each antara with a blank line. Leave empty to auto-generate.</p>
      <button id="go" onclick="produce()">Produce bhajan</button>
    </div>

    <div class="card" id="result" style="display:none">
      <div id="out"></div>
    </div>
  </div>

<script>
async function produce() {
  const btn = document.getElementById('go');
  const res = document.getElementById('result');
  const out = document.getElementById('out');
  btn.disabled = true; btn.textContent = 'Producing (mock pipeline)...';
  res.style.display = 'block';
  out.textContent = 'Running Lyricist -> Composer -> Voice -> Mixing -> Quality Judge -> Packager ...';
  const body = {
    theme: document.getElementById('theme').value,
    mood: document.getElementById('mood').value,
    deity: document.getElementById('deity').value,
    taal: document.getElementById('taal').value,
    tempo: parseInt(document.getElementById('tempo').value || '72', 10),
    lyrics_override: (document.getElementById('lyrics').value || '').trim() || null
  };
  try {
    const r = await fetch('/produce', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    const d = await r.json();
    render(d);
  } catch (e) {
    out.textContent = 'Error: ' + e;
  } finally {
    btn.disabled = false; btn.textContent = 'Produce bhajan';
  }
}
function render(d) {
  const out = document.getElementById('out');
  if (d.halted) {
    out.innerHTML = '<span class="badge fail">HALTED</span><p>' + (d.halt_reason||'') + '</p>';
    return;
  }
  const passed = d.passed;
  const badge = passed ? '<span class="badge pass">PASSED &#10003;</span>'
                       : '<span class="badge fail">NEEDS REVIEW</span>';
  const score = (d.score!=null) ? d.score : '-';
  out.innerHTML =
    badge +
    '<div class="score">' + score + ' / 100</div>' +
    '<p><b>Run:</b> ' + (d.run_id||'') + '<br>' +
    '<b>Decision:</b> ' + (d.decision||'') + '<br>' +
    '<b>Loops used:</b> ' + (d.total_loops!=null?d.total_loops:0) + '</p>' +
    (d.output_dir ? '<p class="muted">Bundle saved to:<br>' + d.output_dir + '</p>' : '') +
    '<p><a href="/status/' + (d.run_id||'') + '" target="_blank">View full run manifest (JSON)</a></p>';
}
</script>
</body>
</html>
"""
