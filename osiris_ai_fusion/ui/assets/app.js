(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    form: $("queryForm"), query: $("queryInput"), region: $("regionInput"), time: $("timeRangeInput"),
    save: $("saveInput"), run: $("runBtn"), connection: $("connectionBadge"),
    settingsBtn: $("settingsBtn"), dialog: $("settingsDialog"), apiKey: $("apiKeyInput"),
    saveSettings: $("saveSettingsBtn"), plan: $("planView"), plannerModel: $("plannerModel"),
    evidence: $("evidenceView"), evidenceCount: $("evidenceCount"), correlations: $("correlationView"),
    correlationCount: $("correlationCount"), markerCount: $("markerCount"), bluf: $("bluf"),
    claims: $("claims"), confidence: $("confidenceBadge"), receipt: $("receiptView"), seal: $("sealBadge"),
    system: $("systemView"), refreshSystem: $("refreshSystemBtn"), log: $("eventLog"), clearLog: $("clearLogBtn")
  };

  let map;
  let markerLayer;
  let busy = false;

  function apiHeaders(json = false) {
    const headers = {};
    const key = sessionStorage.getItem("fusion_api_key") || "";
    if (key) headers["X-API-Key"] = key;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'\"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'\"':"&quot;"})[char]);
  }

  function log(message, obj) {
    const stamp = new Date().toISOString();
    const payload = obj === undefined ? message : `${message}\n${JSON.stringify(obj, null, 2)}`;
    els.log.textContent = `[${stamp}] ${payload}\n\n${els.log.textContent}`.slice(0, 40000);
  }

  function setConnection(ok, detail = "") {
    els.connection.className = `badge ${ok ? "ok" : "danger"}`;
    els.connection.textContent = ok ? "BACKEND: ONLINE" : "BACKEND: OFFLINE";
    els.connection.title = detail;
  }

  function setStage(stage) {
    const order = ["plan", "evidence", "correlation", "analysis", "receipt", "complete"];
    const current = order.indexOf(stage);
    document.querySelectorAll(".stage").forEach((node) => {
      const idx = order.indexOf(node.dataset.stage);
      node.classList.toggle("active", idx === current);
      node.classList.toggle("done", idx >= 0 && idx < current);
    });
  }

  function initMap() {
    if (!window.L) {
      $("map").textContent = "Map library unavailable.";
      return;
    }
    map = L.map("map", { zoomControl: true, worldCopyJump: true }).setView([38.42, 27.14], 5);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
  }

  function renderMarkers(markers = []) {
    els.markerCount.textContent = `${markers.length} MARKERS`;
    if (!map || !markerLayer) return;
    markerLayer.clearLayers();
    const bounds = [];
    for (const item of markers) {
      const lat = Number(item.lat ?? item.latitude);
      const lon = Number(item.lon ?? item.lng ?? item.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const title = escapeHtml(item.title || item.label || item.tool || "OSINT evidence");
      const evidenceId = escapeHtml(item.evidence_id || "");
      L.circleMarker([lat, lon], { radius: 7, weight: 2, fillOpacity: .7 })
        .bindPopup(`<strong>${title}</strong>${evidenceId ? `<br><code>${evidenceId}</code>` : ""}`)
        .addTo(markerLayer);
      bounds.push([lat, lon]);
    }
    if (bounds.length === 1) map.setView(bounds[0], 8);
    else if (bounds.length > 1) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 9 });
  }

  function renderPlan(plan, model) {
    els.plan.textContent = JSON.stringify(plan || {}, null, 2);
    els.plannerModel.textContent = model ? `${model.provider || "—"} / ${model.model || "—"}` : "—";
  }

  function renderEvidence(items = []) {
    els.evidenceCount.textContent = `${items.length} SOURCES`;
    if (!items.length) {
      els.evidence.className = "stack empty";
      els.evidence.textContent = "Kanıt kaydı bulunamadı.";
      return;
    }
    els.evidence.className = "stack";
    els.evidence.innerHTML = items.map((item) => {
      const status = item.ok === false ? "FAILED" : "OK";
      return `<div class="card"><strong>${escapeHtml(item.tool || "source")} · ${status}</strong><small>${escapeHtml(item.evidence_id || "")}</small><small>${escapeHtml(item.source_url || "")}</small><small>SHA ${escapeHtml((item.digest || "").slice(0, 20))}${item.digest ? "…" : ""}</small></div>`;
    }).join("");
  }

  function renderCorrelations(items = []) {
    els.correlationCount.textContent = `${items.length} CANDIDATES`;
    if (!items.length) {
      els.correlations.className = "stack empty";
      els.correlations.textContent = "Korelasyon adayı bulunamadı.";
      return;
    }
    els.correlations.className = "stack";
    els.correlations.innerHTML = items.map((item) => `<div class="card"><strong>${escapeHtml(item.summary || item.reason || "Correlation candidate")}</strong><small>distance=${escapeHtml(item.distance_km ?? "—")} km · time=${escapeHtml(item.time_delta_seconds ?? "—")} s</small><small>Correlation is not causation.</small></div>`).join("");
  }

  function renderReport(report, confidence) {
    const score = Number(report?.overall_confidence ?? confidence?.score ?? 0);
    els.confidence.className = `badge ${score >= .8 ? "ok" : score >= .5 ? "warn" : "muted"}`;
    els.confidence.textContent = `CONFIDENCE ${Number.isFinite(score) ? Math.round(score * 100) : 0}%`;
    els.bluf.classList.remove("empty");
    els.bluf.textContent = report?.bluf || "No synthesized conclusion.";
    const claims = Array.isArray(report?.claims) ? report.claims : [];
    els.claims.innerHTML = claims.length ? claims.map((claim) => {
      const refs = (claim.evidence_ids || []).map((ref) => `<span class="ref">${escapeHtml(ref)}</span>`).join("");
      return `<div class="claim"><div class="claim-top"><span class="claim-kind">${escapeHtml(claim.kind || "claim")}</span><span class="micro">${escapeHtml(claim.confidence ?? "")}</span></div><p>${escapeHtml(claim.text || claim.claim || "")}</p><div class="refs">${refs}</div></div>`;
    }).join("") : `<div class="empty">Kanıta bağlı claim üretilmedi.</div>`;
    renderMarkers(report?.map_markers || []);
  }

  function renderReceipt(receipt) {
    els.receipt.textContent = JSON.stringify(receipt || {}, null, 2);
    const pass = receipt && String(receipt.policy_check || "").includes("PASS") && String(receipt.effect_match || "").includes("PASS");
    els.seal.className = `badge ${pass ? "ok" : "warn"}`;
    els.seal.textContent = pass ? "VERIFIED" : "CHECK";
  }

  async function fetchJson(url) {
    const response = await fetch(url, { headers: apiHeaders(false), cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  async function refreshSystem() {
    els.system.innerHTML = "Kontrol ediliyor…";
    try {
      const [health, providers, tools] = await Promise.all([fetchJson("/health"), fetchJson("/providers"), fetchJson("/tools")]);
      setConnection(true);
      const blocked = (providers.policies || []).filter((p) => p.commercial_allowed === false).length;
      const toolCount = Array.isArray(tools.tools) ? tools.tools.length : 0;
      els.system.innerHTML = [
        `<div class="card"><strong>${escapeHtml(health.service)} v${escapeHtml(health.version)}</strong><small>Status: ${escapeHtml(health.status)}</small></div>`,
        `<div class="card"><strong>${toolCount} read-only tools</strong><small>Active routes hard-denied: ${escapeHtml((tools.forbidden_active_paths || []).join(", "))}</small></div>`,
        `<div class="card"><strong>Commercial mode: ${providers.commercial_mode ? "ON" : "OFF"}</strong><small>${blocked} provider policy entries currently restricted.</small></div>`
      ].join("");
    } catch (error) {
      setConnection(false, String(error));
      els.system.innerHTML = `<div class="card"><strong>Backend erişilemiyor</strong><small>${escapeHtml(error.message || error)}</small></div>`;
    }
  }

  function resetInvestigationUi() {
    setStage("plan");
    els.plan.textContent = "Planlanıyor…";
    els.plannerModel.textContent = "—";
    els.evidenceCount.textContent = "0 SOURCES";
    els.evidence.className = "stack empty";
    els.evidence.textContent = "Kanıt toplanıyor…";
    els.correlationCount.textContent = "0 CANDIDATES";
    els.correlations.className = "stack empty";
    els.correlations.textContent = "Korelasyon bekleniyor…";
    els.bluf.className = "bluf empty";
    els.bluf.textContent = "Analiz bekleniyor…";
    els.claims.innerHTML = "";
    els.receipt.textContent = "SEAL doğrulaması bekleniyor…";
    els.seal.className = "badge muted";
    els.seal.textContent = "PENDING";
    renderMarkers([]);
  }

  function handleEvent(event) {
    if (!event || !event.stage) return;
    setStage(event.stage);
    log(`stage=${event.stage}`, event);
    if (event.stage === "plan") renderPlan(event.plan, event.model);
    if (event.stage === "evidence") {
      renderEvidence(event.evidence_index || []);
      if (event.confidence) {
        const score = Number(event.confidence.score || 0);
        els.confidence.textContent = `SOURCE AVAILABILITY ${Math.round(score * 100)}%`;
      }
    }
    if (event.stage === "correlation") {
      renderCorrelations(event.correlation_candidates || []);
      renderMarkers(event.map_markers || []);
    }
    if (event.stage === "analysis") renderReport(event.report || {}, null);
    if (event.stage === "receipt") renderReceipt(event.receipt || {});
    if (event.stage === "complete") {
      const result = event.result || {};
      renderPlan(result.plan, result.planner_model);
      renderEvidence(result.evidence_index || []);
      renderCorrelations(result.correlation_candidates || []);
      renderReport(result.report || {}, result.confidence || {});
      renderReceipt(result.receipt || {});
    }
    if (event.stage === "error") throw new Error(event.detail || event.error || "Investigation failed");
  }

  async function streamInvestigation(payload) {
    const response = await fetch("/investigate/stream", {
      method: "POST",
      headers: apiHeaders(true),
      body: JSON.stringify(payload),
      cache: "no-store"
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${response.status} ${text.slice(0, 500)}`);
    }
    if (!response.body) throw new Error("Streaming body unavailable");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
        if (!dataLine) continue;
        handleEvent(JSON.parse(dataLine.slice(6)));
      }
    }
    if (buffer.trim()) {
      const dataLine = buffer.split("\n").find((line) => line.startsWith("data: "));
      if (dataLine) handleEvent(JSON.parse(dataLine.slice(6)));
    }
  }

  els.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    const query = els.query.value.trim();
    if (query.length < 3) return;
    busy = true;
    els.run.disabled = true;
    els.run.textContent = "RUNNING…";
    resetInvestigationUi();
    const payload = {
      query,
      save: els.save.checked,
      scope: {
        region: els.region.value.trim() || null,
        time_range: els.time.value || null,
        workspace_id: "default"
      }
    };
    try {
      await streamInvestigation(payload);
      setConnection(true);
    } catch (error) {
      setConnection(false, String(error));
      log("investigation_error", { message: error.message || String(error) });
      els.bluf.className = "bluf empty";
      els.bluf.textContent = `Araştırma tamamlanamadı: ${error.message || error}`;
      els.seal.className = "badge danger";
      els.seal.textContent = "FAILED";
    } finally {
      busy = false;
      els.run.disabled = false;
      els.run.textContent = "INVESTIGATE";
    }
  });

  els.settingsBtn.addEventListener("click", () => {
    els.apiKey.value = sessionStorage.getItem("fusion_api_key") || "";
    els.dialog.showModal();
  });
  els.saveSettings.addEventListener("click", () => {
    const key = els.apiKey.value.trim();
    if (key) sessionStorage.setItem("fusion_api_key", key);
    else sessionStorage.removeItem("fusion_api_key");
    setTimeout(refreshSystem, 0);
  });
  els.refreshSystem.addEventListener("click", refreshSystem);
  els.clearLog.addEventListener("click", () => { els.log.textContent = "Cleared."; });

  initMap();
  refreshSystem();
})();
