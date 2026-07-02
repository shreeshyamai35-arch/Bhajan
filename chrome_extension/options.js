const DEFAULTS = {
  apiBase: "http://localhost:8000",
  colabUrl: "https://colab.research.google.com/",
};

function el(id) {
  return document.getElementById(id);
}

document.addEventListener("DOMContentLoaded", () => {
  chrome.storage.sync.get(DEFAULTS, (cfg) => {
    el("apiBase").value = cfg.apiBase;
    el("colabUrl").value = cfg.colabUrl;
  });

  el("save").addEventListener("click", () => {
    const apiBase = (el("apiBase").value || DEFAULTS.apiBase).trim();
    const colabUrl = (el("colabUrl").value || DEFAULTS.colabUrl).trim();
    chrome.storage.sync.set({ apiBase, colabUrl }, () => {
      el("status").textContent = "Saved ✓";
      setTimeout(() => (el("status").textContent = ""), 1500);
    });
  });
});
