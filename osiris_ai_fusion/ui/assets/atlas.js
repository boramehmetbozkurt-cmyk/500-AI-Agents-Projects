(() => {
  "use strict";

  const MAPS = [
    ["ai-universe", "AI Universe", "/assets/atlas-ai-universe.json"],
    ["ai-gene", "AI Gene Map", "/assets/atlas-ai-gene.json"],
    ["agi", "AGI Capability", "/assets/atlas-agi.json"],
    ["meta-universe", "Meta Universe", "/assets/atlas-meta-universe.json"],
    ["btc-universe", "BTC Universe", "/assets/atlas-btc-universe.json"],
    ["money-universe", "Money Universe", "/assets/atlas-money-universe.json"]
  ];
  const SVG_NS = "http://www.w3.org/2000/svg";
  const $ = (id) => document.getElementById(id);
  const state = { meta: null, map: null, mapId: "ai-universe", selected: null };
  const els = {
    tabs: $("mapTabs"), search: $("search"), cluster: $("cluster"), confidence: $("confidence"),
    reset: $("reset"), graph: $("graph"), title: $("mapTitle"), subtitle: $("mapSubtitle"),
    disclaimer: $("disclaimer"), snapshot: $("snapshot"), stats: $("stats"), legend: $("legend"),
    nodeTitle: $("nodeTitle"), nodeMeta: $("nodeMeta"), nodeDesc: $("nodeDesc"), nodeTags: $("nodeTags"),
    nodeSources: $("nodeSources"), researchBtn: $("researchBtn"), researchStatus: $("researchStatus"),
    researchOutput: $("researchOutput"), sourcePolicy: $("sourcePolicy")
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  }

  async function getJson(url) {
    const response = await fetch(url, {cache: "no-store"});
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function nodeColor(kind) {
    const k = String(kind || "").toLowerCase();
    if (k.includes("organization") || k.includes("public-money")) return "#6ce5ff";
    if (k.includes("model") || k.includes("protocol")) return "#9a8cff";
    if (k.includes("capability") || k.includes("function")) return "#7cf5b2";
    if (k.includes("risk") || k.includes("governance") || k.includes("policy")) return "#ffb86c";
    if (k.includes("network") || k.includes("infrastructure") || k.includes("technology")) return "#ff7bd5";
    if (k.includes("money") || k.includes("asset") || k.includes("market")) return "#f4df70";
    return "#b4c4d8";
  }

  function visibleNodes() {
    if (!state.map) return [];
    const q = els.search.value.trim().toLowerCase();
    const cluster = els.cluster.value;
    const min = Number(els.confidence.value || 0);
    return (state.map.nodes || []).filter((node) => {
      const hay = [node.label, node.kind, node.cluster, node.description, ...(node.tags || [])].join(" ").toLowerCase();
      return (!q || hay.includes(q)) && (!cluster || node.cluster === cluster) && Number(node.confidence || 0) >= min;
    });
  }

  function positions(nodes) {
    const groups = new Map();
    nodes.forEach((n) => {
      const key = n.cluster || "other";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(n);
    });
    const out = new Map();
    const clusters = [...groups.entries()];
    const centerX = 600, centerY = 360, orbit = Math.min(275, 90 + clusters.length * 32);
    clusters.forEach(([cluster, members], ci) => {
      const ca = (Math.PI * 2 * ci / Math.max(1, clusters.length)) - Math.PI / 2;
      const cx = centerX + Math.cos(ca) * orbit;
      const cy = centerY + Math.sin(ca) * orbit;
      const radius = Math.min(110, 35 + members.length * 9);
      members.forEach((node, ni) => {
        const a = (Math.PI * 2 * ni / Math.max(1, members.length)) + ca;
        out.set(node.id, {
          x: members.length === 1 ? cx : cx + Math.cos(a) * radius,
          y: members.length === 1 ? cy : cy + Math.sin(a) * radius,
          cluster
        });
      });
    });
    return out;
  }

  function svgEl(name, attrs = {}) {
    const el = document.createElementNS(SVG_NS, name);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, String(v)));
    return el;
  }

  function renderGraph() {
    const nodes = visibleNodes();
    const ids = new Set(nodes.map((n) => n.id));
    const pos = positions(nodes);
    els.graph.innerHTML = "";

    const edgesLayer = svgEl("g", {class: "edges"});
    (state.map.edges || []).filter((e) => ids.has(e.source) && ids.has(e.target)).forEach((edge) => {
      const a = pos.get(edge.source), b = pos.get(edge.target);
      const line = svgEl("line", {x1:a.x, y1:a.y, x2:b.x, y2:b.y, class:"edge"});
      const title = svgEl("title");
      title.textContent = `${edge.relation || "related"} · ${Math.round(Number(edge.confidence || 0) * 100)}%`;
      line.appendChild(title);
      edgesLayer.appendChild(line);
    });
    els.graph.appendChild(edgesLayer);

    const nodesLayer = svgEl("g", {class:"nodes"});
    nodes.forEach((node) => {
      const p = pos.get(node.id);
      const g = svgEl("g", {class:`graph-node${state.selected?.id === node.id ? " selected" : ""}`, tabindex:"0", role:"button"});
      g.style.cursor = "pointer";
      const circle = svgEl("circle", {cx:p.x, cy:p.y, r: node.id === "bitcoin" ? 23 : 18, fill:nodeColor(node.kind), class:"node-circle"});
      const text = svgEl("text", {x:p.x, y:p.y + 34, "text-anchor":"middle", class:"node-label"});
      text.textContent = String(node.label || node.id).slice(0, 28);
      const title = svgEl("title"); title.textContent = node.description || node.label;
      g.append(circle, text, title);
      g.addEventListener("click", () => selectNode(node));
      g.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") selectNode(node); });
      nodesLayer.appendChild(g);
    });
    els.graph.appendChild(nodesLayer);
    renderStats(nodes);
  }

  function renderStats(nodes = visibleNodes()) {
    const ids = new Set(nodes.map((n) => n.id));
    const edgeCount = (state.map?.edges || []).filter((e) => ids.has(e.source) && ids.has(e.target)).length;
    const sourced = nodes.filter(n => (n.source_ids || []).length).length;
    els.stats.innerHTML = `<div><strong>${nodes.length}</strong><span>DÜĞÜM</span></div><div><strong>${edgeCount}</strong><span>İLİŞKİ</span></div><div><strong>${sourced}</strong><span>KAYNAKLI</span></div>`;
  }

  function renderLegend() {
    const kinds = [...new Set((state.map?.nodes || []).map(n => n.kind).filter(Boolean))].slice(0, 8);
    els.legend.innerHTML = kinds.map(k => `<span><i style="background:${nodeColor(k)}"></i>${esc(k)}</span>`).join("");
  }

  function selectNode(node) {
    state.selected = node;
    els.nodeTitle.textContent = node.label || node.id;
    els.nodeDesc.textContent = node.description || "Açıklama yok.";
    els.nodeMeta.innerHTML = `<span>${esc(node.kind || "node")}</span><span>${esc(node.cluster || "—")}</span><span>Güven ${Math.round(Number(node.confidence || 0) * 100)}%</span>${node.year ? `<span>${esc(node.year)}</span>` : ""}`;
    els.nodeTags.innerHTML = (node.tags || []).map(tag => `<span>${esc(tag)}</span>`).join("");
    const refs = node.source_ids || [];
    els.nodeSources.innerHTML = refs.length ? refs.map((id) => {
      const s = state.meta?.sources?.[id];
      return s ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(s.title)}</b><small>${esc(s.publisher)} · ${esc(s.kind)}</small></a>` : `<span class="missing-source">${esc(id)}</span>`;
    }).join("") : `<small>Seed source yok; canlı araştırma ile kanıt toplanabilir.</small>`;
    els.researchBtn.disabled = false;
    renderGraph();
  }

  function populateClusters() {
    const current = els.cluster.value;
    const clusters = [...new Set((state.map?.nodes || []).map(n => n.cluster).filter(Boolean))].sort();
    els.cluster.innerHTML = '<option value="">Tümü</option>' + clusters.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
    if (clusters.includes(current)) els.cluster.value = current;
  }

  function renderTabs() {
    els.tabs.innerHTML = MAPS.map(([id, label]) => `<button type="button" data-map="${id}" class="${id === state.mapId ? "active" : ""}">${esc(label)}</button>`).join("");
    els.tabs.querySelectorAll("button[data-map]").forEach((btn) => btn.addEventListener("click", () => loadMap(btn.dataset.map)));
  }

  async function loadMap(id) {
    const entry = MAPS.find(([mapId]) => mapId === id) || MAPS[0];
    state.mapId = entry[0]; state.selected = null;
    state.map = await getJson(entry[2]);
    els.title.textContent = state.map.title;
    els.subtitle.textContent = state.map.subtitle || "";
    els.disclaimer.textContent = state.map.disclaimer || "";
    els.nodeTitle.textContent = "Bir düğüm seç";
    els.nodeDesc.textContent = "Graf üzerinde bir düğüme dokunarak açıklama, güven skoru ve kaynakları gör.";
    els.nodeMeta.innerHTML = ""; els.nodeTags.innerHTML = ""; els.nodeSources.innerHTML = "";
    els.researchBtn.disabled = true;
    populateClusters(); renderTabs(); renderLegend(); renderGraph();
    history.replaceState(null, "", `#${state.mapId}`);
  }

  async function researchSelected() {
    const node = state.selected;
    if (!node) return;
    const key = sessionStorage.getItem("fusion_api_key") || "";
    if (!key) {
      els.researchStatus.textContent = "auth required";
      els.researchStatus.className = "pill warn";
      els.researchOutput.textContent = "Canlı araştırma için SaaS hesabından Command Center API anahtarı oluştur ve bu oturumda kullan. Atlas kaynaklı seed bilgiyi göstermeye devam eder, fakat anahtar olmadan backend araştırması başlatmaz.";
      return;
    }
    els.researchBtn.disabled = true;
    els.researchStatus.textContent = "running"; els.researchStatus.className = "pill";
    els.researchOutput.textContent = "OSIRIS Fusion evidence pipeline çalışıyor…";
    const query = `Fusion Atlas ${state.map.title}: ${node.label}. Bu düğümün güncel durumunu, temel ilişkilerini ve önemli değişiklikleri yalnız güvenilir açık kaynaklardan araştır. Seed açıklaması: ${node.description || ""}`;
    try {
      const response = await fetch("/investigate", {
        method: "POST",
        headers: {"Content-Type":"application/json", "X-API-Key":key},
        body: JSON.stringify({query, save:false, scope:{time_range:"P30D"}}),
        cache: "no-store"
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      const report = payload.report || {};
      const claims = Array.isArray(report.claims) ? report.claims : [];
      const evidence = Array.isArray(payload.evidence_index) ? payload.evidence_index : [];
      els.researchOutput.innerHTML = `<p><b>${esc(report.bluf || "Araştırma tamamlandı.")}</b></p>${claims.slice(0,5).map(c => `<p>${esc(c.text || c.claim || "")}</p>`).join("")}<small>${evidence.length} evidence record · ${esc(payload.receipt?.intent_id || payload.investigation_id || "SEAL-bound run")}</small>`;
      els.researchStatus.textContent = "complete"; els.researchStatus.className = "pill ok";
    } catch (error) {
      els.researchStatus.textContent = "failed"; els.researchStatus.className = "pill danger";
      els.researchOutput.textContent = `Canlı araştırma tamamlanamadı: ${error.message || error}`;
    } finally { els.researchBtn.disabled = false; }
  }

  function resetFilters() {
    els.search.value = ""; els.cluster.value = ""; els.confidence.value = "0"; renderGraph();
  }

  async function boot() {
    try {
      state.meta = await getJson("/assets/atlas-meta.json");
      els.snapshot.textContent = `snapshot ${state.meta.snapshot_date || "—"}`;
      els.sourcePolicy.textContent = state.meta.source_policy || "Seed claims require provenance.";
      const requested = location.hash.replace(/^#/, "");
      await loadMap(MAPS.some(([id]) => id === requested) ? requested : MAPS[0][0]);
      els.search.addEventListener("input", renderGraph);
      els.cluster.addEventListener("change", renderGraph);
      els.confidence.addEventListener("change", renderGraph);
      els.reset.addEventListener("click", resetFilters);
      els.researchBtn.addEventListener("click", researchSelected);
    } catch (error) {
      els.graph.innerHTML = `<text x="50" y="80" fill="white">Atlas yüklenemedi: ${esc(error.message || error)}</text>`;
      els.researchStatus.textContent = "error";
    }
  }

  boot();
})();
