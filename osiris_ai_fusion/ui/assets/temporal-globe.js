import * as maplibregl from "https://unpkg.com/maplibre-gl@6.9.0/dist/maplibre-gl.mjs";

const $ = (id) => document.getElementById(id);
const REALITY_BRANCH = "reality";
const MODE_REALMS = {
  physical: ["physical"],
  history: ["historical_reconstruction"],
  digital: ["digital_twin", "mixed_reality"],
  metaverse: ["metaverse"],
  future: ["physical", "digital_twin", "mixed_reality", "metaverse", "simulation"],
};
const FUTURE_TRUTH = new Set(["planned", "belief", "scenario"]);
const state = {
  map: null,
  mapReady: false,
  mode: "physical",
  year: new Date().getUTCFullYear(),
  branch: REALITY_BRANCH,
  features: [],
  unanchored: [],
  portals: [],
  selected: null,
  requestSerial: 0,
};
const els = {
  connection: $("connection"),
  layerModes: $("layerModes"),
  yearLabel: $("yearLabel"),
  yearSlider: $("yearSlider"),
  yearInput: $("yearInput"),
  applyYear: $("applyYear"),
  milestones: $("milestones"),
  branchSelect: $("branchSelect"),
  featureCount: $("featureCount"),
  virtualCount: $("virtualCount"),
  portalCount: $("portalCount"),
  notice: $("notice"),
  featureTitle: $("featureTitle"),
  featureDescription: $("featureDescription"),
  featureMeta: $("featureMeta"),
  featureSources: $("featureSources"),
  accessBtn: $("accessBtn"),
  accessDialog: $("accessDialog"),
  apiKeyInput: $("apiKeyInput"),
  saveAccess: $("saveAccess"),
};

function apiKey() {
  return sessionStorage.getItem("fusion_api_key") || "";
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function formatYear(year) {
  if (year < 0) return `MÖ ${Math.abs(year).toLocaleString("tr-TR")}`;
  return `MS ${year.toLocaleString("tr-TR")}`;
}

function normalizeYear(raw) {
  let year = Math.trunc(Number(raw));
  if (!Number.isFinite(year)) year = new Date().getUTCFullYear();
  year = Math.max(-2000000, Math.min(2000000, year));
  if (year === 0) year = 1;
  return year;
}

function syncTimeControls() {
  els.yearLabel.textContent = formatYear(state.year);
  els.yearInput.value = String(state.year);
  els.yearSlider.value = String(Math.max(-3000, Math.min(2100, state.year)));
}

function headers() {
  const key = apiKey();
  return key ? {"X-API-Key": key} : {};
}

async function getJson(url) {
  const response = await fetch(url, {headers: headers(), cache: "no-store"});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

function truthColor(truth) {
  if (truth === "fact") return "#7cf5b2";
  if (truth === "claim") return "#6ce5ff";
  if (truth === "reconstruction") return "#9a8cff";
  if (truth === "planned") return "#ffbf69";
  if (truth === "scenario") return "#ff7bd5";
  if (truth === "belief") return "#ff8e8e";
  return "#c2d0df";
}

function mapPaintExpression() {
  return [
    "match", ["get", "truth_mode"],
    "fact", "#7cf5b2",
    "claim", "#6ce5ff",
    "reconstruction", "#9a8cff",
    "planned", "#ffbf69",
    "scenario", "#ff7bd5",
    "belief", "#ff8e8e",
    "#c2d0df",
  ];
}

function emptyCollection() {
  return {type: "FeatureCollection", features: []};
}

function initGlobeLayers() {
  if (!state.map || state.map.getSource("osiris-atlas")) return;
  state.map.addSource("osiris-atlas", {type: "geojson", data: emptyCollection()});
  state.map.addLayer({
    id: "osiris-atlas-polygons",
    type: "fill",
    source: "osiris-atlas",
    filter: ["==", ["geometry-type"], "Polygon"],
    paint: {"fill-color": mapPaintExpression(), "fill-opacity": 0.34, "fill-outline-color": mapPaintExpression()},
  });
  state.map.addLayer({
    id: "osiris-atlas-lines",
    type: "line",
    source: "osiris-atlas",
    filter: ["==", ["geometry-type"], "LineString"],
    paint: {"line-color": mapPaintExpression(), "line-width": 3, "line-opacity": 0.85},
  });
  state.map.addLayer({
    id: "osiris-atlas-points",
    type: "circle",
    source: "osiris-atlas",
    filter: ["==", ["geometry-type"], "Point"],
    paint: {
      "circle-color": mapPaintExpression(),
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 4, 5, 7, 10, 11],
      "circle-stroke-color": "rgba(255,255,255,.85)",
      "circle-stroke-width": 1.2,
      "circle-opacity": 0.92,
    },
  });

  ["osiris-atlas-points", "osiris-atlas-lines", "osiris-atlas-polygons"].forEach((layer) => {
    state.map.on("mouseenter", layer, () => { state.map.getCanvas().style.cursor = "pointer"; });
    state.map.on("mouseleave", layer, () => { state.map.getCanvas().style.cursor = ""; });
    state.map.on("click", layer, (event) => {
      const rendered = event.features && event.features[0];
      if (!rendered) return;
      selectFeature(String(rendered.properties?.atlas_id || ""));
    });
  });
}

function initMap() {
  state.map = new maplibregl.Map({
    container: "globe",
    style: "https://demotiles.maplibre.org/globe.json",
    center: [27.1, 38.4],
    zoom: 1.35,
    attributionControl: true,
    maxPitch: 80,
    canvasContextAttributes: {antialias: true},
  });
  state.map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), "top-right");
  state.map.addControl(new maplibregl.GlobeControl(), "top-right");
  state.map.on("style.load", () => state.map.setProjection({type: "globe"}));
  state.map.on("load", () => {
    state.mapReady = true;
    initGlobeLayers();
    renderFeatures();
  });
  state.map.on("error", (event) => {
    const message = event?.error?.message || "Globe basemap error";
    if (!message.includes("AbortError")) els.notice.textContent = `Globe: ${message}`;
  });
}

function temporalLabel(feature) {
  const temporal = feature.temporal || {};
  const start = temporal.start;
  const end = temporal.end;
  if (!start && !end) return "zaman belirtilmedi";
  const label = (item) => item ? formatYear(Number(item.year)) : "—";
  if (temporal.open_ended) return `${label(start)} → açık uçlu`;
  if (start && end && start.year !== end.year) return `${label(start)} → ${label(end)}`;
  return label(start || end);
}

function atlasToGeoJson(feature) {
  let geometry = feature.geometry || null;
  if (!geometry && feature.space?.earth_anchor) {
    geometry = {
      type: "Point",
      coordinates: [Number(feature.space.earth_anchor.longitude), Number(feature.space.earth_anchor.latitude)],
    };
  }
  if (!geometry) return null;
  return {
    type: "Feature",
    id: feature.id,
    geometry,
    properties: {
      atlas_id: feature.id,
      name: feature.name,
      realm: feature.realm,
      truth_mode: feature.truth_mode,
      feature_type: feature.feature_type,
      confidence: Number(feature.confidence || 0),
      space_id: feature.space?.space_id || "",
      temporal: temporalLabel(feature),
    },
  };
}

function renderFeatures() {
  const geo = [];
  const unanchored = [];
  state.features.forEach((feature) => {
    const item = atlasToGeoJson(feature);
    if (item) geo.push(item);
    else unanchored.push(feature);
  });
  state.unanchored = unanchored;
  if (state.mapReady) {
    const source = state.map.getSource("osiris-atlas");
    if (source) source.setData({type: "FeatureCollection", features: geo});
  }
  els.featureCount.textContent = String(geo.length);
  els.virtualCount.textContent = String(unanchored.length);
  els.portalCount.textContent = String(state.portals.length);
}

function sourceMarkup(sourceId) {
  const value = String(sourceId || "");
  if (/^https:\/\//i.test(value)) {
    return `<a href="${esc(value)}" target="_blank" rel="noopener noreferrer">${esc(value)}</a>`;
  }
  return `<span>${esc(value)}</span>`;
}

function selectFeature(id) {
  const feature = state.features.find((item) => item.id === id);
  if (!feature) return;
  state.selected = feature;
  els.featureTitle.textContent = feature.name || feature.id;
  const meta = feature.metadata || {};
  els.featureDescription.textContent = String(meta.description || meta.summary || `${feature.feature_type} · ${feature.realm}`);
  const space = feature.space || {};
  const rows = [
    ["Reality", feature.realm],
    ["Truth", feature.truth_mode],
    ["Time", temporalLabel(feature)],
    ["Confidence", `${Math.round(Number(feature.confidence || 0) * 100)}%`],
    ["Feature type", feature.feature_type],
    ["Space", space.space_id || "—"],
    ["Space kind", space.kind || "—"],
    ["CRS", space.crs || "local / virtual"],
    ["Branch", feature.branch_id || REALITY_BRANCH],
  ];
  els.featureMeta.innerHTML = rows.map(([key, value]) => `<div class="row"><span>${esc(key)}</span><span>${esc(value)}</span></div>`).join("");
  const sources = [...(feature.source_ids || []), ...(feature.evidence_ids || []).map((item) => `evidence:${item}`)];
  els.featureSources.innerHTML = sources.length ? sources.map(sourceMarkup).join("") : "<span>No source IDs exposed.</span>";

  const point = atlasToGeoJson(feature);
  if (point?.geometry?.type === "Point") {
    state.map.easeTo({center: point.geometry.coordinates.slice(0, 2), zoom: Math.max(state.map.getZoom(), 5), duration: 900});
  }
}

function realmUrls() {
  const realms = MODE_REALMS[state.mode] || MODE_REALMS.physical;
  return realms.map((realm) => {
    const params = new URLSearchParams({
      branch_id: state.branch,
      year: String(state.year),
      realm,
      limit: "5000",
    });
    return `/world/atlas/features?${params.toString()}`;
  });
}

function filterModeFeatures(features) {
  if (state.mode !== "future") return features;
  return features.filter((feature) => FUTURE_TRUTH.has(String(feature.truth_mode)));
}

async function loadFeatures() {
  if (!apiKey()) {
    state.features = [];
    state.portals = [];
    renderFeatures();
    els.connection.textContent = "ATLAS AUTH REQUIRED";
    els.connection.className = "status-pill warn";
    els.notice.textContent = "Atlas verisi tenant-scoped. ACCESS ile API anahtarını bu sekmeye ekle.";
    return;
  }
  const serial = ++state.requestSerial;
  els.connection.textContent = "ATLAS LOADING";
  els.connection.className = "status-pill muted";
  els.notice.textContent = `${formatYear(state.year)} · ${state.mode.toUpperCase()} katmanı yükleniyor…`;
  try {
    const [featureResults, portalPayload] = await Promise.all([
      Promise.all(realmUrls().map(getJson)),
      getJson(`/world/atlas/portals?branch_id=${encodeURIComponent(state.branch)}&limit=5000`),
    ]);
    if (serial !== state.requestSerial) return;
    const merged = featureResults.flatMap((result) => Array.isArray(result.features) ? result.features : []);
    const unique = new Map(merged.map((feature) => [feature.id, feature]));
    state.features = filterModeFeatures([...unique.values()]);
    state.portals = Array.isArray(portalPayload.portals) ? portalPayload.portals : [];
    renderFeatures();
    els.connection.textContent = "ATLAS LIVE";
    els.connection.className = "status-pill";
    const extra = state.unanchored.length ? ` · ${state.unanchored.length} sanal öğe Earth anchor olmadan ayrı space'te.` : "";
    const futureRule = state.mode === "future" && state.branch === REALITY_BRANCH
      ? " Reality branch'te yalnız planned/belief görünür; scenario için fork seç."
      : "";
    els.notice.textContent = `${state.features.length} Atlas feature · ${formatYear(state.year)}.${extra}${futureRule}`;
    updateUrl();
  } catch (error) {
    if (serial !== state.requestSerial) return;
    state.features = [];
    state.portals = [];
    renderFeatures();
    els.connection.textContent = "ATLAS ERROR";
    els.connection.className = "status-pill warn";
    els.notice.textContent = `Atlas yüklenemedi: ${error.message || error}`;
  }
}

async function loadBranches() {
  if (!apiKey()) return;
  try {
    const payload = await getJson("/world/forks");
    const rows = Array.isArray(payload) ? payload : [];
    const current = state.branch;
    els.branchSelect.innerHTML = rows.map((branch) => `<option value="${esc(branch.id)}">${esc(branch.name || branch.id)}</option>`).join("");
    if (![...els.branchSelect.options].some((option) => option.value === REALITY_BRANCH)) {
      els.branchSelect.insertAdjacentHTML("afterbegin", '<option value="reality">Reality</option>');
    }
    state.branch = [...els.branchSelect.options].some((option) => option.value === current) ? current : REALITY_BRANCH;
    els.branchSelect.value = state.branch;
  } catch (error) {
    els.notice.textContent = `World Fork listesi alınamadı: ${error.message || error}`;
  }
}

function updateLayerButtons() {
  els.layerModes.querySelectorAll("button[data-mode]").forEach((button) => {
    const active = button.dataset.mode === state.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
}

function setMode(mode) {
  if (!Object.hasOwn(MODE_REALMS, mode)) return;
  state.mode = mode;
  if (mode === "future" && state.year <= new Date().getUTCFullYear()) {
    state.year = 2040;
    syncTimeControls();
  }
  updateLayerButtons();
  loadFeatures();
}

function setYear(raw) {
  state.year = normalizeYear(raw);
  syncTimeControls();
  loadFeatures();
}

function updateUrl() {
  const params = new URLSearchParams({year: String(state.year), mode: state.mode});
  if (state.branch !== REALITY_BRANCH) params.set("branch", state.branch);
  history.replaceState(null, "", `${location.pathname}?${params.toString()}`);
}

function restoreUrlState() {
  const params = new URLSearchParams(location.search);
  const requestedMode = params.get("mode");
  if (requestedMode && Object.hasOwn(MODE_REALMS, requestedMode)) state.mode = requestedMode;
  if (params.has("year")) state.year = normalizeYear(params.get("year"));
  if (params.get("branch")) state.branch = params.get("branch");
}

function bindControls() {
  els.layerModes.querySelectorAll("button[data-mode]").forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  });
  els.yearSlider.addEventListener("input", () => {
    const year = normalizeYear(els.yearSlider.value);
    els.yearLabel.textContent = formatYear(year);
    els.yearInput.value = String(year);
  });
  els.yearSlider.addEventListener("change", () => setYear(els.yearSlider.value));
  els.applyYear.addEventListener("click", () => setYear(els.yearInput.value));
  els.yearInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") setYear(els.yearInput.value);
  });
  els.milestones.querySelectorAll("button[data-year]").forEach((button) => {
    button.addEventListener("click", () => setYear(button.dataset.year));
  });
  els.branchSelect.addEventListener("change", () => {
    state.branch = els.branchSelect.value || REALITY_BRANCH;
    loadFeatures();
  });
  els.accessBtn.addEventListener("click", () => {
    els.apiKeyInput.value = apiKey();
    els.accessDialog.showModal();
  });
  els.saveAccess.addEventListener("click", (event) => {
    event.preventDefault();
    const key = els.apiKeyInput.value.trim();
    if (key) sessionStorage.setItem("fusion_api_key", key);
    else sessionStorage.removeItem("fusion_api_key");
    els.accessDialog.close();
    loadBranches().then(loadFeatures);
  });
}

async function boot() {
  restoreUrlState();
  syncTimeControls();
  updateLayerButtons();
  bindControls();
  initMap();
  if (apiKey()) {
    await loadBranches();
    await loadFeatures();
  } else {
    await loadFeatures();
  }
}

boot();
