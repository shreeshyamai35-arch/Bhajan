// BhajanForge popup logic — talks to the local FastAPI server over HTTP.

const DEFAULTS = {
  apiBase: "http://localhost:8000",
  colabUrl: "https://colab.research.google.com/",
};

function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(DEFAULTS, (cfg) => resolve(cfg));
  });
}

function el(id) {
  return document.getElementById(id);
}

async function checkHealth(base) {
  const dot = el("dot");
  try {
    const r = await fetch(base.replace(/\/$/, "") + "/healthz", {
      method: "GET",
    });
    const d = await r.json();
    if (d && d.ok) {
      dot.className = "dot up";
      dot.title = "API online · v" + (d.version || "?");
      return true;
    }
  } catch (e) {
    /* fall through */
  }
  dot.className = "dot down";
  dot.title = "API offline — start uvicorn on " + base;
  return false;
}

async function produce(base) {
  const btn = el("go");
  const res = el("result");
  const out = el("out");
  btn.disabled = true;
  btn.textContent = "Producing…";
  res.style.display = "block";
  out.textContent =
    "Lyricist → Composer → Voice → Mixing → Quality Judge → Packager …";

  const body = {
    theme: el("theme").value,
    mood: el("mood").value,
    deity: el("deity").value,
    taal: el("taal").value,
    tempo: parseInt(el("tempo").value || "72", 10),
    lyrics_override: (el("lyrics").value || "").trim() || null,
  };

  try {
    const r = await fetch(base.replace(/\/$/, "") + "/produce", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    render(d, base);
  } catch (e) {
    out.innerHTML =
      '<span class="badge fail">ERROR</span><p class="muted">' +
      String(e) +
      "<br>Is the API running? Check Settings for the URL.</p>";
  } finally {
    btn.disabled = false;
    btn.textContent = "Produce bhajan";
  }
}

function render(d, base) {
  const out = el("out");
  if (!d.ok && d.error) {
    out.innerHTML =
      '<span class="badge fail">FAILED</span><p class="muted">' +
      d.error +
      "</p>";
    return;
  }
  if (d.halted) {
    out.innerHTML =
      '<span class="badge fail">HALTED</span><p>' + (d.halt_reason || "") + "</p>";
    return;
  }
  const badge = d.passed
    ? '<span class="badge pass">PASSED ✓</span>'
    : '<span class="badge fail">NEEDS REVIEW</span>';
  const score = d.score != null ? d.score : "–";
  const statusUrl = base.replace(/\/$/, "") + "/status/" + (d.run_id || "");
  out.innerHTML =
    badge +
    '<div class="score">' +
    score +
    " / 100</div>" +
    "<p><b>Run:</b> " +
    (d.run_id || "") +
    "<br><b>Decision:</b> " +
    (d.decision || "") +
    "<br><b>Loops:</b> " +
    (d.total_loops != null ? d.total_loops : 0) +
    "</p>" +
    (d.output_dir
      ? '<p class="muted">Saved to:<br>' + d.output_dir + "</p>"
      : "") +
    '<p><a href="' +
    statusUrl +
    '" target="_blank">View run manifest (JSON)</a></p>';
}

document.addEventListener("DOMContentLoaded", async () => {
  const cfg = await getConfig();
  checkHealth(cfg.apiBase);

  el("colab").addEventListener("click", (e) => {
    e.preventDefault();
    // 1) download the notebook from the local API (lands in Downloads),
    // 2) open Colab — use its Upload tab to pick the just-downloaded file.
    const base = cfg.apiBase.replace(/\/$/, "");
    chrome.downloads
      ? chrome.downloads.download({ url: base + "/notebook" })
      : window.open(base + "/notebook", "_blank");
    window.open(cfg.colabUrl, "_blank");
  });
  el("go").addEventListener("click", () => produce(cfg.apiBase));
  el("opts").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });
});
