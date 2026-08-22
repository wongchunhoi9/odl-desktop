"use strict";

/* ------------------------------------------------------------------ */
/* State                                                                */
/* ------------------------------------------------------------------ */

let inputPaths = [];     // absolute paths chosen by the user (files or folders)
let hybridPollTimer = null;
let converting = false;
let javaOk = false;      // gates Convert — no point starting a batch that can only fail on the JVM step

/* ------------------------------------------------------------------ */
/* Boot                                                                 */
/* ------------------------------------------------------------------ */

window.addEventListener("pywebviewready", init);

async function init() {
  await checkEnvironment();

  const settings = await api("get_settings");
  applySettingsToForm(settings);

  wireStaticControls();
  refreshHybridStatus();
  hybridPollTimer = setInterval(refreshHybridStatus, 1500);

  window.addEventListener("odl:progress", (e) => appendLog(e.detail.message));
  window.addEventListener("odl:complete", (e) => onConversionComplete(e.detail));

  updateConvertEnabled();
}

/* small wrapper so call sites read `await api("method", arg1, arg2)` */
function api(method, ...args) {
  return window.pywebview.api[method](...args);
}

/* Re-runs the Java check (used at boot and from the banner's "Re-check"
 * button, since a user who just installed Java can't otherwise get the
 * app to notice without quitting and relaunching it). */
async function checkEnvironment() {
  const env = await api("check_environment");
  javaOk = !!env.java_ok;
  if (javaOk) {
    hideEnvBanner();
  } else {
    showEnvBanner(env.java_message || "Java 11+ is required but was not detected.");
  }
  updateConvertEnabled();
  return env;
}

function showEnvBanner(text) {
  const banner = document.getElementById("env-banner");
  document.getElementById("env-banner-text").textContent = "⚠ " + text;
  banner.classList.remove("hidden");
}

function hideEnvBanner() {
  document.getElementById("env-banner").classList.add("hidden");
}

/* ------------------------------------------------------------------ */
/* Settings <-> form                                                    */
/* ------------------------------------------------------------------ */

function applySettingsToForm(s) {
  document.getElementById("output-dir").value = s.output_dir || "";
  document.getElementById("chk-subfolders").checked = !!s.include_subfolders;

  document.querySelectorAll(".fmt-check").forEach((cb) => {
    cb.checked = (s.formats || []).includes(cb.value);
  });

  document.getElementById("chk-header-footer").checked = !!s.include_header_footer;
  document.getElementById("sel-table-method").value = s.table_method || "default";
  document.getElementById("sel-reading-order").value = s.reading_order || "xycut";
  document.getElementById("sel-image-output").value = s.image_output || "off";
  document.getElementById("sel-image-format").value = s.image_format || "png";
  document.getElementById("chk-sanitize").checked = !!s.sanitize;
  document.getElementById("input-page-range").value = s.page_range || "";

  document.getElementById("sel-hybrid-mode").value = s.hybrid_mode || "auto";
  document.getElementById("chk-force-ocr").checked = !!s.force_ocr;
  document.getElementById("input-ocr-lang").value = s.ocr_lang || "en";
  document.getElementById("chk-enrich-formula").checked = !!s.enrich_formula;
  document.getElementById("chk-enrich-picture").checked = !!s.enrich_picture_description;
  document.getElementById("input-hybrid-port").value = s.hybrid_port || 5002;
  document.getElementById("chk-hybrid-enabled").checked = !!s.hybrid_enabled;

  toggleImageFormatRow();
}

function gatherSettings() {
  return {
    output_dir: document.getElementById("output-dir").value,
    include_subfolders: document.getElementById("chk-subfolders").checked,
    formats: Array.from(document.querySelectorAll(".fmt-check:checked")).map((cb) => cb.value),
    include_header_footer: document.getElementById("chk-header-footer").checked,
    table_method: document.getElementById("sel-table-method").value,
    reading_order: document.getElementById("sel-reading-order").value,
    image_output: document.getElementById("sel-image-output").value,
    image_format: document.getElementById("sel-image-format").value,
    sanitize: document.getElementById("chk-sanitize").checked,
    page_range: document.getElementById("input-page-range").value,

    // Per-run (client) flags — safe to change any time hybrid is enabled.
    hybrid_enabled: document.getElementById("chk-hybrid-enabled").checked,
    hybrid_mode: document.getElementById("sel-hybrid-mode").value,
    hybrid_port: parseInt(document.getElementById("input-hybrid-port").value, 10) || 5002,

    // Backend startup flags — only take effect the next time the backend
    // is (re)started; see gatherHybridStartupOptions().
    force_ocr: document.getElementById("chk-force-ocr").checked,
    ocr_lang: document.getElementById("input-ocr-lang").value,
    enrich_formula: document.getElementById("chk-enrich-formula").checked,
    enrich_picture_description: document.getElementById("chk-enrich-picture").checked,
  };
}

/** Options sent specifically to hybrid_start — kept separate from
 * gatherSettings() so it's clear these are startup-time-only. */
function gatherHybridStartupOptions() {
  return {
    port: parseInt(document.getElementById("input-hybrid-port").value, 10) || 5002,
    force_ocr: document.getElementById("chk-force-ocr").checked,
    ocr_lang: document.getElementById("input-ocr-lang").value || "en",
    enrich_formula: document.getElementById("chk-enrich-formula").checked,
    enrich_picture_description: document.getElementById("chk-enrich-picture").checked,
  };
}

function persistSettings() {
  api("save_settings", gatherSettings());
}

/* ------------------------------------------------------------------ */
/* Static control wiring                                                */
/* ------------------------------------------------------------------ */

function wireStaticControls() {
  document.getElementById("btn-choose-files").addEventListener("click", async () => {
    const paths = await api("choose_input_files");
    addInputPaths(paths);
  });

  document.getElementById("btn-choose-folder").addEventListener("click", async () => {
    const paths = await api("choose_input_folder");
    addInputPaths(paths);
  });

  document.getElementById("btn-choose-output").addEventListener("click", async () => {
    const dir = await api("choose_output_folder");
    if (dir) {
      document.getElementById("output-dir").value = dir;
      persistSettings();
      updateConvertEnabled();
    }
  });

  // Dropzone. Note: extracting a real filesystem path from an HTML5 drop
  // event depends on the underlying webview engine exposing `file.path`.
  // On pywebview's macOS (WKWebView) backend this isn't guaranteed across
  // versions, so we try it and fall back to prompting the user to use the
  // "Choose Files…" button if no usable path comes through.
  const dropzone = document.getElementById("dropzone");
  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const files = Array.from(e.dataTransfer.files || []);
    const paths = files.map((f) => f.path).filter(Boolean);
    if (paths.length) {
      addInputPaths(paths);
    } else if (files.length) {
      appendLog("Couldn't read a filesystem path from the dropped item(s) — use \"Choose Files…\" instead.");
    }
  });

  // Any settings field: persist on change.
  document
    .querySelectorAll("#section-options input, #section-options select, #chk-subfolders")
    .forEach((el) => el.addEventListener("change", persistSettings));

  document.getElementById("sel-image-output").addEventListener("change", () => {
    toggleImageFormatRow();
    persistSettings();
  });

  document.getElementById("link-docs").addEventListener("click", (e) => {
    e.preventDefault();
    api("open_docs");
  });

  document.getElementById("btn-download-java").addEventListener("click", () => {
    api("open_java_download");
  });
  document.getElementById("btn-recheck-java").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Checking…";
    const env = await checkEnvironment();
    btn.disabled = false;
    btn.textContent = "Re-check";
    if (env.java_ok) appendLog("Java detected — Convert is now available.");
  });

  document.getElementById("btn-hybrid-toggle").addEventListener("click", onHybridToggleClick);
  document.getElementById("chk-hybrid-enabled").addEventListener("change", () => {
    persistSettings();
    updateConvertEnabled();
  });
  document.getElementById("sel-hybrid-mode").addEventListener("change", persistSettings);
  document.getElementById("chk-force-ocr").addEventListener("change", persistSettings);
  document.getElementById("input-ocr-lang").addEventListener("change", persistSettings);
  document.getElementById("chk-enrich-formula").addEventListener("change", persistSettings);
  document.getElementById("chk-enrich-picture").addEventListener("change", persistSettings);
  document.getElementById("input-hybrid-port").addEventListener("change", persistSettings);

  document.getElementById("btn-convert").addEventListener("click", onConvertClick);
  document.getElementById("btn-cancel").addEventListener("click", () => {
    appendLog("Cancellation isn't supported once a batch has started — waiting for it to finish.");
  });
  document.getElementById("btn-open-output").addEventListener("click", async () => {
    const dir = document.getElementById("output-dir").value;
    if (dir) await api("open_folder", dir);
  });
}

function toggleImageFormatRow() {
  const show = document.getElementById("sel-image-output").value !== "off";
  document.getElementById("row-image-format").classList.toggle("hidden", !show);
}

/* ------------------------------------------------------------------ */
/* Input chips                                                          */
/* ------------------------------------------------------------------ */

function addInputPaths(paths) {
  if (!paths || !paths.length) return;
  for (const p of paths) {
    if (!inputPaths.includes(p)) inputPaths.push(p);
  }
  renderChips();
  updateConvertEnabled();
}

function removeInputPath(p) {
  inputPaths = inputPaths.filter((x) => x !== p);
  renderChips();
  updateConvertEnabled();
}

function renderChips() {
  const list = document.getElementById("input-chip-list");
  list.innerHTML = "";
  for (const p of inputPaths) {
    const li = document.createElement("li");
    li.className = "chip";
    const name = p.split("/").pop();
    li.innerHTML = `<span title="${escapeHtml(p)}">${escapeHtml(name)}</span>`;
    const removeBtn = document.createElement("button");
    removeBtn.textContent = "×";
    removeBtn.setAttribute("aria-label", `Remove ${name}`);
    removeBtn.addEventListener("click", () => removeInputPath(p));
    li.appendChild(removeBtn);
    list.appendChild(li);
  }
  const summary = document.getElementById("input-summary");
  summary.textContent = inputPaths.length
    ? `${inputPaths.length} item(s) selected.`
    : "No files selected yet.";
}

/* ------------------------------------------------------------------ */
/* Hybrid backend                                                       */
/* ------------------------------------------------------------------ */

async function refreshHybridStatus() {
  const status = await api("hybrid_status");
  applyHybridStatus(status);
}

// Per-run (client) flags: only meaningful — so only enabled — once the
// backend is actually running.
const PER_RUN_CONTROLS = ["chk-hybrid-enabled", "sel-hybrid-mode"];
// Backend startup flags: baked into the process at launch, so they're only
// editable while stopped. Changing them requires a restart.
const STARTUP_CONTROLS = [
  "input-hybrid-port",
  "chk-force-ocr",
  "input-ocr-lang",
  "chk-enrich-formula",
  "chk-enrich-picture",
];

function applyHybridStatus(status) {
  const card = document.getElementById("section-hybrid");
  const btn = document.getElementById("btn-hybrid-toggle");
  const text = document.getElementById("hybrid-status-text");

  card.dataset.state = status.state;

  switch (status.state) {
    case "running":
      text.textContent = `Running on port ${status.port}`;
      btn.textContent = "Stop Backend";
      btn.disabled = false;
      PER_RUN_CONTROLS.forEach((id) => (document.getElementById(id).disabled = false));
      STARTUP_CONTROLS.forEach((id) => (document.getElementById(id).disabled = true));
      break;
    case "starting":
      text.textContent = "Starting… (first run downloads OCR models — can take a minute)";
      btn.textContent = "Starting…";
      btn.disabled = true;
      PER_RUN_CONTROLS.forEach((id) => (document.getElementById(id).disabled = true));
      STARTUP_CONTROLS.forEach((id) => (document.getElementById(id).disabled = true));
      break;
    case "error":
      text.textContent = status.message || "Backend error";
      btn.textContent = "Start Backend";
      btn.disabled = false;
      PER_RUN_CONTROLS.forEach((id) => (document.getElementById(id).disabled = true));
      STARTUP_CONTROLS.forEach((id) => (document.getElementById(id).disabled = false));
      document.getElementById("chk-hybrid-enabled").checked = false;
      break;
    default: // stopped
      text.textContent = "Not running";
      btn.textContent = "Start Backend";
      btn.disabled = false;
      PER_RUN_CONTROLS.forEach((id) => (document.getElementById(id).disabled = true));
      STARTUP_CONTROLS.forEach((id) => (document.getElementById(id).disabled = false));
      document.getElementById("chk-hybrid-enabled").checked = false;
  }
  updateConvertEnabled();
}

async function onHybridToggleClick() {
  const state = document.getElementById("section-hybrid").dataset.state;
  const btn = document.getElementById("btn-hybrid-toggle");
  btn.disabled = true;
  if (state === "running" || state === "starting") {
    await api("hybrid_stop");
    appendLog("Hybrid backend stopped.");
  } else {
    appendLog("Starting hybrid backend…");
    persistSettings();
    const result = await api("hybrid_start", gatherHybridStartupOptions());
    if (result.state === "error") {
      appendLog(`Hybrid backend error: ${result.message}`);
    }
  }
  refreshHybridStatus();
}

/* ------------------------------------------------------------------ */
/* Convert                                                              */
/* ------------------------------------------------------------------ */

function updateConvertEnabled() {
  const btn = document.getElementById("btn-convert");
  const hasInputs = inputPaths.length > 0;
  const hasOutput = !!document.getElementById("output-dir").value;
  const hybridWantedButNotRunning =
    document.getElementById("chk-hybrid-enabled").checked &&
    document.getElementById("section-hybrid").dataset.state !== "running";

  btn.disabled = converting || !javaOk || !hasInputs || !hasOutput;
  btn.textContent = hybridWantedButNotRunning ? "Start Backend & Convert" : "Convert";
  btn.title = !javaOk ? "Java 11+ is required — see the banner above." : "";
}

async function onConvertClick() {
  const settings = gatherSettings();

  // If hybrid was requested but isn't running yet, start it first.
  if (settings.hybrid_enabled) {
    const status = await api("hybrid_status");
    if (status.state !== "running") {
      appendLog("Starting hybrid backend before conversion…");
      await api("hybrid_start", gatherHybridStartupOptions());
      const ok = await waitForHybridRunning();
      if (!ok) {
        appendLog("Hybrid backend didn't come up in time — check the panel and try again.");
        return;
      }
    }
  }

  converting = true;
  setRunningUI(true);
  clearLog();
  clearResults();
  appendLog(`Converting ${inputPaths.length} item(s)…`);

  await api("start_conversion", inputPaths, settings);
  // Completion arrives asynchronously via the 'odl:complete' event.
}

function waitForHybridRunning(timeoutMs = 30000) {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = async () => {
      const status = await api("hybrid_status");
      applyHybridStatus(status);
      if (status.state === "running") return resolve(true);
      if (status.state === "error" || Date.now() - start > timeoutMs) return resolve(false);
      setTimeout(check, 500);
    };
    check();
  });
}

function onConversionComplete(result) {
  converting = false;
  setRunningUI(false);

  if (result.error) {
    appendLog(`Error: ${result.error}`);
  }

  const list = document.getElementById("results-list");
  for (const f of result.files || []) {
    const li = document.createElement("li");
    li.className = "result-row";
    const name = f.input_path.split("/").pop();
    li.innerHTML = `
      <span class="result-icon ${f.ok ? "ok" : "fail"}">${f.ok ? "✓" : "✕"}</span>
      <span class="result-name" title="${escapeHtml(f.input_path)}">${escapeHtml(name)}</span>
    `;
    if (f.ok && f.outputs && f.outputs[0]) {
      const revealBtn = document.createElement("button");
      revealBtn.className = "result-reveal";
      revealBtn.textContent = "Reveal in Finder";
      revealBtn.addEventListener("click", () => api("reveal_in_finder", f.outputs[0]));
      li.appendChild(revealBtn);
    } else if (f.error) {
      appendLog(`${name}: ${f.error}`);
    }
    list.appendChild(li);
  }

  if (result.files && result.files.some((f) => f.ok)) {
    document.getElementById("btn-open-output").classList.remove("hidden");
  }

  appendLog(result.ok ? "Done." : "Finished with errors — see details above.");
  updateConvertEnabled();
}

function setRunningUI(running) {
  document.getElementById("btn-convert").disabled = running;
  document.getElementById("btn-cancel").classList.toggle("hidden", !running);
  const progressWrap = document.getElementById("progress-wrap");
  progressWrap.classList.toggle("hidden", !running);
  document.getElementById("progress-bar").classList.toggle("indeterminate", running);
  document.getElementById("progress-label").textContent = running ? "Working…" : "";
}

/* ------------------------------------------------------------------ */
/* Log helpers                                                          */
/* ------------------------------------------------------------------ */

function appendLog(message) {
  const out = document.getElementById("log-output");
  const time = new Date().toLocaleTimeString();
  out.textContent += `[${time}] ${message}\n`;
  out.scrollTop = out.scrollHeight;
  document.getElementById("progress-label").textContent = message;
}

function clearLog() {
  document.getElementById("log-output").textContent = "";
}

function clearResults() {
  document.getElementById("results-list").innerHTML = "";
  document.getElementById("btn-open-output").classList.add("hidden");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
