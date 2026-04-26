import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { GTAOPass } from "three/addons/postprocessing/GTAOPass.js";
import { SMAAPass } from "three/addons/postprocessing/SMAAPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { addPascalLighting, clearBuildingMeshes, populateBuildingScene } from "./tier-preview.js";
import { parseElementUid } from "./locator.js";

const DATA_ROOT = "../../pipeline-outputs";
const canvas = document.querySelector("#view");
const list = document.querySelector("#list");
const search = document.querySelector("#search");
const sidebarStats = document.querySelector("#sidebar-stats");
const status = document.querySelector("#status");
const pill = document.querySelector("#pill");
const loading = document.querySelector("#loading");
const signals = document.querySelector("#signals");
const currentAddress = document.querySelector("#current-address");
const currentMeta = document.querySelector("#current-meta");
const navPrev = document.querySelector("#nav-prev");
const navNext = document.querySelector("#nav-next");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xffffff);
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.9;
renderer.outputColorSpace = THREE.SRGBColorSpace;
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
window.__tierViewer = { scene, camera, controls, renderer, requestRender: null };
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let rows = [];
let activeUuid = null;
let activePayload = null;
let selectedHelper = null;
let renderQueued = false;
let lastRenderWidth = 0;
let lastRenderHeight = 0;

addPascalLighting(scene);
const pmremGenerator = new THREE.PMREMGenerator(renderer);
scene.environment = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.35;
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const gtao = new GTAOPass(scene, camera, 1, 1);
gtao.output = GTAOPass.OUTPUT.Default;
gtao.updateGtaoMaterial({
  radius: 0.4,
  distanceExponent: 1.2,
  thickness: 0.5,
  scale: 1.0,
  samples: 16,
  distanceFallOff: 1.0,
  screenSpaceRadius: false,
});
composer.addPass(gtao);
const smaa = new SMAAPass(1, 1);
composer.addPass(smaa);
composer.addPass(new OutputPass());

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[char]));
}

function classification(row) {
  return row.classification || row.payload?.classification || {};
}

function rowLabel(row) {
  return row.address || row.payload?.address || row.uuid;
}

function rowSearchText(row) {
  const cls = classification(row);
  return [
    row.uuid,
    row.address,
    row.payload?.address,
    cls.tier_label,
    cls.roof_type,
    cls.tier,
  ].filter(Boolean).join(" ").toLowerCase();
}

function shortUuid(uuid) {
  return uuid ? uuid.slice(0, 8) : "";
}

function renderBadges(row) {
  const cls = classification(row);
  const badges = [];
  if (cls.tier != null) badges.push(`<span class="badge badge-tier">T${escapeHtml(cls.tier)}</span>`);
  if (cls.n_stories != null) badges.push(`<span class="badge">${escapeHtml(cls.n_stories)}st</span>`);
  if (cls.has_half_height) badges.push('<span class="badge badge-half">1/2</span>');
  if (cls.has_gable) badges.push('<span class="badge badge-gable">gable</span>');
  if (cls.n_oblique > 0) badges.push(`<span class="badge badge-oblique">${escapeHtml(cls.n_oblique)}ob</span>`);
  if (cls.n_flat > 0) badges.push(`<span class="badge">${escapeHtml(cls.n_flat)}fl</span>`);
  return badges.join("");
}

function updateSidebarStats() {
  const loaded = rows.filter((row) => row.address || row.classification || row.payload).length;
  const visible = list.querySelectorAll(".row").length;
  sidebarStats.textContent = `${visible} shown · ${rows.length} buildings · ${loaded} with loaded metadata`;
}

function updateNavButtons() {
  const canNavigate = rows.length > 1;
  navPrev.disabled = !canNavigate;
  navNext.disabled = !canNavigate;
}

function resize() {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(1, Math.floor(rect.height));
  if (width === lastRenderWidth && height === lastRenderHeight) return;
  lastRenderWidth = width;
  lastRenderHeight = height;
  renderer.setSize(width, height, false);
  composer.setSize(width, height);
  gtao.setSize(width, height);
  smaa.setSize(width, height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function renderFrame() {
  renderQueued = false;
  resize();
  controls.update();
  composer.render();
}

function requestRender() {
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(renderFrame);
}
if (window.__tierViewer) window.__tierViewer.requestRender = requestRender;

function framePayload(payload) {
  const box = new THREE.Box3();
  scene.traverse((obj) => {
    if (obj.userData?.tierPreview && obj.isMesh && !obj.userData.pickOnly && !obj.userData.framingIgnore) box.expandByObject(obj);
  });
  const center = box.isEmpty() ? new THREE.Vector3(payload.building_center.x, payload.building_center.y, payload.building_center.z) : box.getCenter(new THREE.Vector3());
  const size = box.isEmpty() ? new THREE.Vector3(8, 4, 8) : box.getSize(new THREE.Vector3());
  const radius = Math.max(size.x, size.y, size.z, 4);
  controls.target.copy(center);
  camera.position.set(center.x + radius * 1.2, center.y + radius * 0.9, center.z + radius * 1.2);
  camera.near = Math.max(0.05, radius / 200);
  camera.far = radius * 20;
  camera.updateProjectionMatrix();
  controls.update();
}

async function loadPayload(uuid) {
  activeUuid = uuid;
  loading.classList.remove("hidden");
  currentAddress.textContent = "Loading...";
  currentMeta.textContent = uuid;
  const response = await fetch(`${DATA_ROOT}/${uuid}/tier_payload.json`, { cache: "no-store" });
  if (!response.ok) throw new Error(`tier_payload.json missing for ${uuid}`);
  activePayload = await response.json();
  const row = rows.find((entry) => entry.uuid === uuid);
  if (row) {
    row.address = row.address || activePayload.address;
    row.classification = activePayload.classification;
    row.payload = activePayload;
  }
  clearSelection();
  populateBuildingScene(scene, activePayload);
  window.__tierState = {
    activeUuid: uuid,
    locatorCount: scene.userData.tierLocatorMap?.size || 0,
    firstLocator: scene.userData.tierLocatorMap ? [...scene.userData.tierLocatorMap.keys()][0] : null,
    selectedLocator: null,
  };
  framePayload(activePayload);
  status.classList.remove("locator");
  status.textContent = "Click a mesh to inspect it. Right-click to copy its locator ID.";
  const cls = activePayload.classification || {};
  const title = activePayload.address || activePayload.uuid;
  currentAddress.textContent = title;
  currentMeta.textContent = `${activePayload.uuid} · Tier ${cls.tier ?? "-"} · ${cls.tier_label || "Unclassified"}`;
  pill.textContent = `${cls.tier_label || "Unclassified"} · ${cls.roof_type || "unknown roof"}`;
  signals.innerHTML = `
    <div class="signal-row"><span class="key">Storeys</span><span class="value">${escapeHtml(cls.n_stories ?? "-")}</span></div>
    <div class="signal-row"><span class="key">Rooms</span><span class="value">${escapeHtml(cls.n_rooms ?? "-")}</span></div>
    <div class="signal-row"><span class="key">Oblique</span><span class="value">${escapeHtml(cls.n_oblique ?? "-")}</span></div>
    <div class="signal-row"><span class="key">Flat</span><span class="value">${escapeHtml(cls.n_flat ?? "-")}</span></div>
    <div class="signal-row"><span class="key">Half-height</span><span class="value">${cls.has_half_height ? "yes" : "no"}</span></div>
    <div class="signal-row"><span class="key">Gable</span><span class="value">${cls.has_gable ? "yes" : "no"}</span></div>
  `;
  history.replaceState(null, "", `#b=${encodeURIComponent(uuid)}`);
  renderList(search.value.includes("::") ? "" : search.value);
  const activeRow = list.querySelector(`.row[data-uuid="${CSS.escape(uuid)}"]`);
  if (activeRow) {
    activeRow.classList.add("active");
    activeRow.scrollIntoView({ block: "nearest" });
  }
  loading.classList.add("hidden");
  requestRender();
}

async function hydrateSidebarMetadata(limit = 32) {
  const candidates = rows.filter((row) => !row.address && !row.classification).slice(0, limit);
  let updated = false;
  for (const row of candidates) {
    if (row.uuid === activeUuid && activePayload) continue;
    try {
      const response = await fetch(`${DATA_ROOT}/${row.uuid}/tier_payload.json`, { cache: "force-cache" });
      if (!response.ok) continue;
      const payload = await response.json();
      row.address = payload.address;
      row.classification = payload.classification;
      updated = true;
      if (!search.value.includes("::")) renderList(search.value);
    } catch (error) {
      console.debug("sidebar metadata fetch failed", row.uuid, error);
    }
  }
  if (updated && !search.value.includes("::")) renderList(search.value);
}

function renderList(filter = "") {
  const needle = filter.trim().toLowerCase();
  list.textContent = "";
  for (const row of rows) {
    if (needle && !rowSearchText(row).includes(needle)) continue;
    const button = document.createElement("button");
    button.className = `row${row.uuid === activeUuid ? " active" : ""}`;
    button.dataset.uuid = row.uuid;
    const meta = renderBadges(row);
    button.innerHTML = `
      <span class="label">${escapeHtml(rowLabel(row))}</span>
      <span class="uuid">${escapeHtml(shortUuid(row.uuid))} · ${escapeHtml(row.uuid)}</span>
      <span class="row-meta">${meta}</span>
    `;
    button.addEventListener("click", () => loadPayload(row.uuid).catch(showError));
    list.appendChild(button);
  }
  updateSidebarStats();
  updateNavButtons();
}

function showError(error) {
  console.error(error);
  loading.classList.add("hidden");
  status.textContent = error.message || String(error);
  currentAddress.textContent = "Unable to load building";
  currentMeta.textContent = error.message || String(error);
}

function meshesUnderPointer(event) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
  raycaster.setFromCamera(pointer, camera);
  return raycaster.intersectObjects(scene.children, true);
}

function locatorHit(event) {
  return meshesUnderPointer(event).find((item) => item.object.userData?.elementLocator);
}

function clearSelection() {
  if (!selectedHelper) return;
  selectedHelper.removeFromParent();
  selectedHelper.geometry?.dispose?.();
  selectedHelper.material?.dispose?.();
  selectedHelper = null;
}

function showLocator(uid, copied = false) {
  status.classList.add("locator");
  status.textContent = copied ? `Copied ${uid}` : uid;
  search.value = uid;
  if (window.__tierState) window.__tierState.selectedLocator = uid;
}

function selectLocator(uid, options = {}) {
  const mesh = scene.userData.tierLocatorMap?.get(uid);
  if (!mesh) return false;
  clearSelection();
  selectedHelper = new THREE.BoxHelper(mesh, 0xffcc00);
  selectedHelper.userData.tierPreview = true;
  selectedHelper.userData.selectionHelper = true;
  scene.add(selectedHelper);
  const box = new THREE.Box3().setFromObject(mesh);
  const center = box.getCenter(new THREE.Vector3());
  if (options.focus) {
    controls.target.copy(center);
    camera.position.lerp(new THREE.Vector3(center.x + 6, center.y + 4, center.z + 6), 0.8);
    controls.update();
  }
  showLocator(uid, Boolean(options.copied));
  requestRender();
  return true;
}

canvas.addEventListener("click", (event) => {
  const hit = locatorHit(event);
  if (!hit) return;
  selectLocator(hit.object.userData.elementLocator);
});

canvas.addEventListener("contextmenu", async (event) => {
  event.preventDefault();
  const hit = locatorHit(event);
  if (!hit) return;
  const uid = hit.object.userData.elementLocator;
  let copied = false;
  try {
    await navigator.clipboard?.writeText(uid);
    copied = true;
  } catch (_err) {
    copied = false;
  }
  selectLocator(uid, { copied });
});

search.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  const value = search.value.trim();
  const parsed = parseElementUid(value);
  if (parsed) {
    if (parsed.uuid !== activeUuid) await loadPayload(parsed.uuid);
    if (!selectLocator(value, { focus: true })) {
      status.classList.remove("locator");
      status.textContent = `No mesh for ${value}`;
    }
    return;
  }
  const found = rows.find((row) => rowSearchText(row).includes(value.toLowerCase()));
  if (found) await loadPayload(found.uuid);
});
search.addEventListener("input", () => renderList(search.value));

function visibleRows() {
  const needle = search.value.trim().toLowerCase();
  return rows.filter((row) => !needle || rowSearchText(row).includes(needle));
}

function step(delta) {
  const visible = visibleRows();
  if (!visible.length) return;
  const currentIndex = Math.max(0, visible.findIndex((row) => row.uuid === activeUuid));
  const nextIndex = (currentIndex + delta + visible.length) % visible.length;
  loadPayload(visible[nextIndex].uuid).catch(showError);
}

navPrev.addEventListener("click", () => step(-1));
navNext.addEventListener("click", () => step(1));
window.addEventListener("keydown", (event) => {
  if (event.target === search) return;
  if (event.key === "ArrowUp" || event.key === "k") {
    event.preventDefault();
    step(-1);
  } else if (event.key === "ArrowDown" || event.key === "j") {
    event.preventDefault();
    step(1);
  }
});

async function init() {
  const response = await fetch(`${DATA_ROOT}/tier_index.json`, { cache: "no-store" });
  const index = response.ok ? await response.json() : { buildings: [] };
  rows = (index.buildings || []).map((entry) => typeof entry === "string" ? { uuid: entry } : entry);
  renderList();
  const hash = new URLSearchParams(location.hash.slice(1));
  const uuid = hash.get("b") || rows[0]?.uuid;
  if (uuid) {
    await loadPayload(uuid);
    hydrateSidebarMetadata().catch((error) => console.debug("metadata hydration failed", error));
  }
  else {
    status.textContent = "No tier payloads found";
    currentAddress.textContent = "No tier payloads found";
    currentMeta.textContent = "";
    pill.textContent = "-";
  }
  requestRender();
}

init().catch(showError);
controls.addEventListener("change", requestRender);
window.addEventListener("resize", requestRender);
