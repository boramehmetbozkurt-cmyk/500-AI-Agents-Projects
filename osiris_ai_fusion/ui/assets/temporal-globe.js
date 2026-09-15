import * as THREE from "https://unpkg.com/three@0.186.0/build/three.module.js";

const $ = (id) => document.getElementById(id);
const REALITY_BRANCH = "reality";
const EARTH_RADIUS = 1.8;
const MODE_REALMS = {
  physical: ["physical"],
  history: ["historical_reconstruction"],
  digital: ["digital_twin", "mixed_reality"],
  metaverse: ["metaverse"],
  future: ["physical", "digital_twin", "mixed_reality", "metaverse", "simulation"],
};
const FUTURE_TRUTH = new Set(["planned", "belief", "scenario"]);
const state = {
  mode: "physical",
  year: new Date().getUTCFullYear(),
  branch: REALITY_BRANCH,
  features: [],
  unanchored: [],
  portals: [],
  selected: null,
  requestSerial: 0,
  scene: null,
  camera: null,
  renderer: null,
  earthGroup: null,
  featureGroup: null,
  portalGroup: null,
  clickTargets: [],
  markerById: new Map(),
  anchorById: new Map(),
  dragging: false,
  pointerStart: null,
  lastPointer: null,
};
const els = {
  globe: $("globe"),
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

function truthHex(truth) {
  if (truth === "fact") return 0x7cf5b2;
  if (truth === "claim") return 0x6ce5ff;
  if (truth === "reconstruction") return 0x9a8cff;
  if (truth === "planned") return 0xffbf69;
  if (truth === "scenario") return 0xff7bd5;
  if (truth === "belief") return 0xff8e8e;
  return 0xc2d0df;
}

function latLonToVector3(lon, lat, radius = EARTH_RADIUS) {
  const phi = (90 - Number(lat)) * Math.PI / 180;
  const theta = (Number(lon) + 180) * Math.PI / 180;
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function deterministicRandom(seed) {
  let value = seed >>> 0;
  return () => {
    value = (1664525 * value + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

function buildStars() {
  const rand = deterministicRandom(0x0f51f15);
  const positions = [];
  for (let i = 0; i < 1400; i += 1) {
    const radius = 10 + rand() * 18;
    const theta = rand() * Math.PI * 2;
    const z = rand() * 2 - 1;
    const planar = Math.sqrt(1 - z * z);
    positions.push(
      radius * planar * Math.cos(theta),
      radius * z,
      radius * planar * Math.sin(theta),
    );
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  const material = new THREE.PointsMaterial({color: 0x7c96ad, size: 0.015, transparent: true, opacity: 0.55});
  state.scene.add(new THREE.Points(geometry, material));
}

function graticuleLine(points, opacity = 0.16) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({color: 0x88b7d8, transparent: true, opacity});
  return new THREE.Line(geometry, material);
}

function buildGraticule() {
  const group = new THREE.Group();
  for (let lat = -75; lat <= 75; lat += 15) {
    const points = [];
    for (let lon = -180; lon <= 180; lon += 3) points.push(latLonToVector3(lon, lat, EARTH_RADIUS + 0.006));
    group.add(graticuleLine(points, lat === 0 ? 0.28 : 0.13));
  }
  for (let lon = -180; lon < 180; lon += 15) {
    const points = [];
    for (let lat = -90; lat <= 90; lat += 3) points.push(latLonToVector3(lon, lat, EARTH_RADIUS + 0.006));
    group.add(graticuleLine(points, lon === 0 ? 0.25 : 0.12));
  }
  state.earthGroup.add(group);
}

function initGlobe() {
  const width = els.globe.clientWidth || window.innerWidth;
  const height = els.globe.clientHeight || window.innerHeight;
  state.scene = new THREE.Scene();
  state.scene.background = new THREE.Color(0x03060b);
  state.camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100);
  state.camera.position.set(0, 0.15, 5.4);

  state.renderer = new THREE.WebGLRenderer({antialias: true, powerPreference: "high-performance"});
  state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  state.renderer.setSize(width, height);
  state.renderer.outputColorSpace = THREE.SRGBColorSpace;
  els.globe.appendChild(state.renderer.domElement);

  state.earthGroup = new THREE.Group();
  state.earthGroup.rotation.x = -0.08;
  state.earthGroup.rotation.y = -0.48;
  state.scene.add(state.earthGroup);

  const earth = new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS, 96, 64),
    new THREE.MeshPhongMaterial({color: 0x0a1a29, emissive: 0x02080e, shininess: 12, specular: 0x31536b}),
  );
  state.earthGroup.add(earth);

  const atmosphere = new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS * 1.035, 64, 48),
    new THREE.MeshBasicMaterial({color: 0x4ab9ff, transparent: true, opacity: 0.055, side: THREE.BackSide, blending: THREE.AdditiveBlending}),
  );
  state.earthGroup.add(atmosphere);

  buildGraticule();
  buildStars();

  state.featureGroup = new THREE.Group();
  state.portalGroup = new THREE.Group();
  state.earthGroup.add(state.portalGroup);
  state.earthGroup.add(state.featureGroup);

  state.scene.add(new THREE.AmbientLight(0x9dc8e8, 0.72));
  const keyLight = new THREE.DirectionalLight(0xbce8ff, 2.1);
  keyLight.position.set(4, 3, 5);
  state.scene.add(keyLight);
  const rim = new THREE.DirectionalLight(0x8d70ff, 1.1);
  rim.position.set(-5, -2, -3);
  state.scene.add(rim);

  bindGlobeInteraction();
  window.addEventListener("resize", resizeGlobe);
  animate();
}

function resizeGlobe() {
  if (!state.renderer || !state.camera) return;
  const width = els.globe.clientWidth || window.innerWidth;
  const height = els.globe.clientHeight || window.innerHeight;
  state.camera.aspect = width / height;
  state.camera.updateProjectionMatrix();
  state.renderer.setSize(width, height);
}

function animate() {
  requestAnimationFrame(animate);
  if (!state.dragging && state.earthGroup) state.earthGroup.rotation.y += 0.00045;
  if (state.renderer && state.scene && state.camera) state.renderer.render(state.scene, state.camera);
}

function pointerNdc(event) {
  const rect = state.renderer.domElement.getBoundingClientRect();
  return new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  );
}

function pickFeature(event) {
  if (!state.clickTargets.length) return;
  const raycaster = new THREE.Raycaster();
  raycaster.params.Points.threshold = 0.05;
  raycaster.setFromCamera(pointerNdc(event), state.camera);
  const hits = raycaster.intersectObjects(state.clickTargets, false);
  if (!hits.length) return;
  const id = hits[0].object.userData.featureId;
  if (id) selectFeature(String(id));
}

function bindGlobeInteraction() {
  const canvas = state.renderer.domElement;
  canvas.addEventListener("pointerdown", (event) => {
    state.dragging = true;
    state.pointerStart = {x: event.clientX, y: event.clientY};
    state.lastPointer = {x: event.clientX, y: event.clientY};
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!state.dragging || !state.lastPointer) return;
    const dx = event.clientX - state.lastPointer.x;
    const dy = event.clientY - state.lastPointer.y;
    state.earthGroup.rotation.y += dx * 0.005;
    state.earthGroup.rotation.x += dy * 0.004;
    state.earthGroup.rotation.x = Math.max(-1.25, Math.min(1.25, state.earthGroup.rotation.x));
    state.lastPointer = {x: event.clientX, y: event.clientY};
  });
  canvas.addEventListener("pointerup", (event) => {
    const start = state.pointerStart;
    state.dragging = false;
    state.lastPointer = null;
    if (start) {
      const moved = Math.hypot(event.clientX - start.x, event.clientY - start.y);
      if (moved < 6) pickFeature(event);
    }
    state.pointerStart = null;
  });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    state.camera.position.z = Math.max(3.25, Math.min(8.5, state.camera.position.z + event.deltaY * 0.003));
  }, {passive: false});
}

function disposeGroup(group) {
  const children = [...group.children];
  children.forEach((child) => {
    group.remove(child);
    child.traverse((object) => {
      object.geometry?.dispose?.();
      if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose?.());
      else object.material?.dispose?.();
    });
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

function geometryPairs(value, output = []) {
  if (!Array.isArray(value)) return output;
  if (value.length >= 2 && Number.isFinite(Number(value[0])) && Number.isFinite(Number(value[1]))) {
    output.push([Number(value[0]), Number(value[1])]);
    return output;
  }
  value.forEach((item) => geometryPairs(item, output));
  return output;
}

function featureAnchor(feature) {
  if (feature.geometry) {
    const pairs = geometryPairs(feature.geometry.coordinates || []);
    if (pairs.length) {
      const sum = pairs.reduce((acc, pair) => [acc[0] + pair[0], acc[1] + pair[1]], [0, 0]);
      return [sum[0] / pairs.length, sum[1] / pairs.length];
    }
  }
  const anchor = feature.space?.earth_anchor;
  if (anchor) return [Number(anchor.longitude), Number(anchor.latitude)];
  return null;
}

function markerMesh(feature, lon, lat, color) {
  const radius = 0.022 + Math.max(0, Math.min(1, Number(feature.confidence || 0))) * 0.018;
  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 16, 12),
    new THREE.MeshBasicMaterial({color}),
  );
  marker.position.copy(latLonToVector3(lon, lat, EARTH_RADIUS + 0.035));
  marker.userData.featureId = feature.id;
  state.featureGroup.add(marker);
  state.clickTargets.push(marker);
  state.markerById.set(feature.id, marker);
  return marker;
}

function lineForCoordinates(coords, color, opacity = 0.8) {
  const points = coords
    .filter((pair) => Array.isArray(pair) && pair.length >= 2)
    .map((pair) => latLonToVector3(Number(pair[0]), Number(pair[1]), EARTH_RADIUS + 0.018));
  if (points.length < 2) return;
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({color, transparent: true, opacity});
  state.featureGroup.add(new THREE.Line(geometry, material));
}

function renderGeometry(feature, color) {
  const geometry = feature.geometry;
  if (!geometry) return;
  const type = geometry.type;
  const coords = geometry.coordinates;
  if (type === "Point" && Array.isArray(coords)) {
    markerMesh(feature, Number(coords[0]), Number(coords[1]), color);
  } else if (type === "MultiPoint" && Array.isArray(coords)) {
    coords.slice(0, 250).forEach((pair) => markerMesh(feature, Number(pair[0]), Number(pair[1]), color));
  } else if (type === "LineString" && Array.isArray(coords)) {
    lineForCoordinates(coords, color);
  } else if (type === "MultiLineString" && Array.isArray(coords)) {
    coords.slice(0, 100).forEach((line) => lineForCoordinates(line, color));
  } else if (type === "Polygon" && Array.isArray(coords)) {
    coords.slice(0, 40).forEach((ring, index) => lineForCoordinates(ring, color, index === 0 ? 0.85 : 0.42));
  } else if (type === "MultiPolygon" && Array.isArray(coords)) {
    coords.slice(0, 50).forEach((polygon) => polygon.slice(0, 20).forEach((ring, index) => lineForCoordinates(ring, color, index === 0 ? 0.82 : 0.36)));
  }
}

function portalArc(start, end) {
  const a = latLonToVector3(start[0], start[1], EARTH_RADIUS + 0.055).normalize();
  const b = latLonToVector3(end[0], end[1], EARTH_RADIUS + 0.055).normalize();
  const points = [];
  for (let i = 0; i <= 40; i += 1) {
    const t = i / 40;
    const point = a.clone().lerp(b, t).normalize();
    const lift = EARTH_RADIUS + 0.055 + Math.sin(Math.PI * t) * 0.22;
    points.push(point.multiplyScalar(lift));
  }
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({color: 0xff7bd5, transparent: true, opacity: 0.4});
  state.portalGroup.add(new THREE.Line(geometry, material));
}

function renderPortals() {
  disposeGroup(state.portalGroup);
  state.portals.forEach((portal) => {
    const start = state.anchorById.get(String(portal.source_feature_id || ""));
    const end = state.anchorById.get(String(portal.target_feature_id || ""));
    if (start && end) portalArc(start, end);
  });
}

function renderFeatures() {
  if (!state.featureGroup || !state.portalGroup) return;
  disposeGroup(state.featureGroup);
  state.clickTargets = [];
  state.markerById.clear();
  state.anchorById.clear();
  const anchored = [];
  const unanchored = [];

  state.features.forEach((feature) => {
    const anchor = featureAnchor(feature);
    if (!anchor || !Number.isFinite(anchor[0]) || !Number.isFinite(anchor[1])) {
      unanchored.push(feature);
      return;
    }
    anchored.push(feature);
    state.anchorById.set(feature.id, anchor);
    const color = truthHex(feature.truth_mode);
    renderGeometry(feature, color);
    if (!state.markerById.has(feature.id)) markerMesh(feature, anchor[0], anchor[1], color);
  });

  state.unanchored = unanchored;
  renderPortals();
  els.featureCount.textContent = String(anchored.length);
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
  if (state.selected?.id && state.markerById.has(state.selected.id)) state.markerById.get(state.selected.id).scale.setScalar(1);
  state.selected = feature;
  const marker = state.markerById.get(feature.id);
  if (marker) marker.scale.setScalar(1.8);
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
    const extra = state.unanchored.length ? ` · ${state.unanchored.length} sanal öğe Earth anchor olmadan ayrı coordinate-space'te.` : "";
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
  initGlobe();
  if (apiKey()) await loadBranches();
  await loadFeatures();
}

boot();
