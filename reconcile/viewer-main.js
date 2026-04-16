import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import {
  STORY_COLORS, STORY_WALL_COLORS, ROOM_COLORS,
  DOOR_COLOR, DOOR_EDGE, WINDOW_COLOR, WINDOW_EDGE, MERGED_COLOR, MERGED_EDGE,
  ROOF_CLUSTER_COLORS,
  SOURCE_COLORS, SOURCE_LABELS,
  LAYER_CONTROL_IDS, LAYER_KEYS, PIPELINE_STEPS,
  EMPTY_MAP_STYLE,
} from './viewer-modules/constants.js';
import {
  createPolygonMesh, createEdgeLoop, createLine, createPolyline3,
  createTriangleMesh, createTriangleBoundaryEdges,
  disposeGroup, polygonPlaneBasis, projectToPlane2,
  collectWallCutoutHoles, orientedStructureCorners,
} from './viewer-modules/geometry.js';
import { renderRoofFromPythonResult } from './viewer-modules/roof-python.js';
import {
  renderOntologySemantics,
  renderOntologyContinuationDiagnostics,
  renderOntologyExact,
} from './viewer-modules/ontology-cells.js';
import { renderOntologyEnhancedFullModel } from './viewer-modules/full-model-ontology.js';
import { createOrthoMapController } from './viewer-modules/map-ortho.js';
import { bindUIEventHandlers } from './viewer-modules/ui-bindings.js';

const viewport = document.getElementById('viewport');
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setClearColor(0x171717);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.9;

function resizeRenderer() {
  const w = viewport.clientWidth, h = viewport.clientHeight;
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 500);
camera.position.set(10, 15, 10);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;

scene.add(new THREE.AmbientLight(0xffffff, 0.45));
const dl1 = new THREE.DirectionalLight(0xffffff, 1.0);
dl1.position.set(10, 20, 10);
dl1.castShadow = true;
dl1.shadow.mapSize.set(2048, 2048);
dl1.shadow.bias = 0.0002;
dl1.shadow.normalBias = 0.25;
dl1.shadow.camera.near = 1;
dl1.shadow.camera.far = 120;
dl1.shadow.camera.left = -40;
dl1.shadow.camera.right = 40;
dl1.shadow.camera.top = 40;
dl1.shadow.camera.bottom = -40;
scene.add(dl1);
const dl2 = new THREE.DirectionalLight(0xffffff, 0.3);
dl2.position.set(-10, 10, -10);
scene.add(dl2);

const grid = new THREE.GridHelper(60, 60, 0x2d2d2d, 0x232323);
grid.visible = false;
scene.add(grid);

let roofClusterData = [];
let colorByStory = true;
let colorBySource = false;
let DATA = [];
let currentBuilding = 0;
let orthoEnabled = false;
let modelMapEnabled = true;
let modelMapRotationDeg = 0;
let modelMapOffsetEastM = 0;
let modelMapOffsetNorthM = 0;
let alignmentByUuid = {};
let alignmentSaveTimer = null;
let anchorModeEnabled = false;
let pyRoofByUuid = {};
let ontologySummaryByUuid = {};
let ontologySummaryPromiseByUuid = {};
let ontologyPartDetailsByUuid = {};
let ontologyPartPromiseByUuid = {};
let ontologyLoadStateByUuid = {};
let selectedOntologyPartByUuid = {};
let fullModelEnhancementByUuid = {};
let fullModelDiffModeEnabled = false;
let buildingIndexByUuid = new Map();
const elementMeshByUid = new Map();
let pendingElementUid = getElementUidFromHash();
let pendingBuildingUuid = getBuildingUuidFromHash();
let buildingInfoBaseHtml = '';

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

function getVisiblePickRoots() {
  return [
    groups.merged,
    groups.computed,
    groups.doors,
    groups.windows,
    groups.floors,
    groups.gaps,
    groups.crossStory,
    groups.extensions,
    groups.overlaps,
    groups.wallClips,
    groups.extGaps,
    groups.fullModel,
    groups.ceilings,
    groups.thermalCeilings,
    groups.roofClusters,
    groups.fullModelHeuristicRoof,
    groups.fullModelOntology,
    groups.ontologySemantics,
    groups.ontologyContinuation,
    groups.ontologyCells,
  ].filter(g => g.visible);
}

function ontologyPartIdFromLocator(locator) {
  if (!locator) return null;
  if (locator.partId) return String(locator.partId);
  if (Array.isArray(locator.partIds) && locator.partIds.length > 0) return String(locator.partIds[0]);
  return null;
}

function getBuildingUuid() {
  return DATA[currentBuilding]?.uuid || "";
}

function makeElementUid(locator) {
  const buildingUuid = locator?.buildingUuid || getBuildingUuid();
  if (!buildingUuid || !locator?.kind || !locator?.id) return null;
  return `${buildingUuid}::${locator.kind}::${locator.id}`;
}

function attachLocator(mesh, locator) {
  if (!mesh || !locator) return;
  const uid = makeElementUid(locator);
  if (!uid) return;
  mesh.userData.elementLocator = locator;
  mesh.userData.elementUid = uid;
  if (!elementMeshByUid.has(uid)) elementMeshByUid.set(uid, mesh);
}

function cornersCenter(corners) {
  if (!Array.isArray(corners) || corners.length === 0) return null;
  let sx = 0;
  let sy = 0;
  let sz = 0;
  for (const c of corners) {
    sx += Number(c?.[0] || 0);
    sy += Number(c?.[1] || 0);
    sz += Number(c?.[2] || 0);
  }
  return [sx / corners.length, sy / corners.length, sz / corners.length];
}

function parseElementUid(text) {
  const match = String(text || "").trim().match(
    /^([0-9a-fA-F-]{36})::([a-zA-Z0-9_-]+)::(.+)$/
  );
  if (!match) return null;
  return {
    buildingUuid: match[1],
    kind: match[2],
    id: match[3],
    uid: `${match[1]}::${match[2]}::${match[3]}`,
  };
}

function updateElementHash(uid) {
  if (!uid) return;
  const parsed = parseElementUid(uid);
  if (!parsed) return;
  const encoded = encodeURIComponent(uid);
  history.replaceState(null, "", `#eid=${encoded}`);
}

function getElementUidFromHash() {
  const hash = window.location.hash || "";
  const match = hash.match(/eid=([^&]+)/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch (_err) {
    return null;
  }
}

function getBuildingUuidFromHash() {
  const hash = window.location.hash || "";
  const match = hash.match(/(?:^#|&)b=([0-9a-fA-F-]{36})/);
  if (!match) return null;
  return match[1];
}

function selectElementByUid(uid, { focus = true, updateHash = true } = {}) {
  const parsed = parseElementUid(uid);
  if (!parsed) return false;
  const mesh = elementMeshByUid.get(parsed.uid);
  if (!mesh) return false;
  disposeGroup(groups.selection);

  if (mesh.geometry) {
    const highlightMesh = new THREE.Mesh(
      mesh.geometry.clone(),
      new THREE.MeshBasicMaterial({
        color: 0xffd166,
        transparent: true,
        opacity: 0.32,
        depthWrite: false,
        side: THREE.DoubleSide,
      }),
    );
    highlightMesh.position.copy(mesh.position);
    highlightMesh.quaternion.copy(mesh.quaternion);
    highlightMesh.scale.copy(mesh.scale);
    highlightMesh.renderOrder = 1000;
    groups.selection.add(highlightMesh);

    const edgeLines = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry),
      new THREE.LineBasicMaterial({ color: 0xffef99, transparent: true, opacity: 0.95 }),
    );
    edgeLines.position.copy(mesh.position);
    edgeLines.quaternion.copy(mesh.quaternion);
    edgeLines.scale.copy(mesh.scale);
    edgeLines.renderOrder = 1001;
    groups.selection.add(edgeLines);
  }

  const bldg = DATA[currentBuilding];
  const addr = bldg?.address || bldg?.uuid || "Building";
  const locator = mesh.userData?.elementLocator;
  const roomPart = locator?.roomId ? ` room ${locator.roomId}` : "";
  const storyPart = Number.isFinite(locator?.story) ? ` story ${locator.story}` : "";
  const sourcePart = locator?.source ? ` (${locator.source})` : "";
  setMapStatus(`Selected ${parsed.kind} ${parsed.id}${roomPart}${storyPart}${sourcePart}`);

  if (focus) {
    const center = cornersCenter(locator?.corners);
    if (center) {
      controls.target.set(center[0], center[1], center[2]);
      controls.update();
    }
  }

  showLineagePanel(parsed, locator);

  if (updateHash) updateElementHash(parsed.uid);
  document.title = `${addr} - ${parsed.kind} ${parsed.id} - 3D Viewer`;
  return true;
}

function showLineagePanel(parsed, locator) {
  const panel = document.getElementById("lineage-panel");
  const content = document.getElementById("lineage-content");
  const lineage = locator?.lineage;
  if (!lineage || lineage.length === 0) {
    panel.classList.remove("visible");
    return;
  }
  let html = `<div class="lineage-element-info"><strong>${parsed.kind}</strong> ${parsed.id}`;
  if (locator.source) html += ` <span style="color:#666">(${locator.source})</span>`;
  html += `</div>`;
  for (const entry of lineage) {
    html += `<div class="lineage-entry ${entry.action}">`;
    html += `<span class="lineage-step">${entry.step}</span>`;
    html += `<span class="lineage-action">${entry.action}</span>`;
    if (entry.detail) html += `<div class="lineage-detail">${entry.detail}</div>`;
    html += `</div>`;
  }
  content.innerHTML = html;
  panel.classList.add("visible");
}

function hideLineagePanel() {
  document.getElementById("lineage-panel").classList.remove("visible");
}

function jumpToElementUid(uid, { focus = true, updateHash = true } = {}) {
  const parsed = parseElementUid(uid);
  if (!parsed) return false;
  const targetIndex = buildingIndexByUuid.get(parsed.buildingUuid);
  if (!Number.isInteger(targetIndex)) return false;

  if (currentBuilding !== targetIndex) {
    loadBuilding(targetIndex, { resetPipeline: false });
  }
  return selectElementByUid(parsed.uid, { focus, updateHash });
}

async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_err) {
    // Fall through to textarea fallback.
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (_err) {
    return false;
  }
}

let groups = {
  merged: new THREE.Group(),
  computed: new THREE.Group(),
  doors: new THREE.Group(),
  windows: new THREE.Group(),
  floors: new THREE.Group(),
  gaps: new THREE.Group(),
  extensions: new THREE.Group(),
  overlaps: new THREE.Group(),
  wallClips: new THREE.Group(),
  extGaps: new THREE.Group(),
  ceilings: new THREE.Group(),
  thermalCeilings: new THREE.Group(),
  crossStory: new THREE.Group(),
  roofClusters: new THREE.Group(),
  fullModelHeuristicRoof: new THREE.Group(),
  fullModelOntology: new THREE.Group(),
  ontologySemantics: new THREE.Group(),
  ontologyContinuation: new THREE.Group(),
  ontologyCells: new THREE.Group(),
  fullModel: new THREE.Group(),
  selection: new THREE.Group(),
};
scene.add(groups.merged);
scene.add(groups.computed);
scene.add(groups.doors);
scene.add(groups.windows);
scene.add(groups.floors);
scene.add(groups.gaps);
scene.add(groups.extensions);
scene.add(groups.overlaps);
scene.add(groups.wallClips);
scene.add(groups.extGaps);
scene.add(groups.ceilings);
scene.add(groups.thermalCeilings);
scene.add(groups.crossStory);
scene.add(groups.roofClusters);
scene.add(groups.fullModelHeuristicRoof);
scene.add(groups.fullModelOntology);
scene.add(groups.ontologySemantics);
scene.add(groups.ontologyContinuation);
scene.add(groups.ontologyCells);
scene.add(groups.fullModel);
scene.add(groups.selection);
groups.overlaps.visible = false;
groups.fullModel.visible = false;
groups.wallClips.visible = false;
groups.merged.visible = false;
groups.gaps.visible = false;
groups.crossStory.visible = false;
groups.extGaps.visible = false;
groups.ceilings.visible = false;
groups.thermalCeilings.visible = false;
groups.fullModelHeuristicRoof.visible = false;
groups.fullModelOntology.visible = false;
groups.ontologySemantics.visible = false;
groups.ontologyContinuation.visible = false;
groups.ontologyCells.visible = false;
groups.selection.visible = true;

let pipelineStepIndex = 0;
let currentStorySet = new Set();

function buildPipelineVisibility(stepIndex) {
  const vis = {};
  for (const key of LAYER_KEYS) vis[key] = false;

  for (let i = 0; i <= stepIndex; i++) {
    const step = PIPELINE_STEPS[i];
    if (!step) continue;
    if (step.exclusive) {
      for (const key of LAYER_KEYS) vis[key] = false;
      for (const key of step.exclusive) vis[key] = true;
      continue;
    }
    for (const key of (step.adds || [])) vis[key] = true;
  }
  return vis;
}

function setLayerVisibility(layer, visible, syncControls = true) {
  if (groups[layer]) groups[layer].visible = visible;
  if (layer === 'fullModel') {
    groups.fullModelHeuristicRoof.visible = visible;
    groups.fullModelOntology.visible = visible;
  }
  if (syncControls) {
    const id = LAYER_CONTROL_IDS[layer];
    const ctl = id ? document.getElementById(id) : null;
    if (ctl) ctl.checked = visible;
  }
  if (layer === 'ontologySemantics' || layer === 'ontologyContinuation' || layer === 'ontologyCells') {
    updateOntologyStatusInfo();
  }
}

function renderLegend() {
  const legendBox = document.getElementById('legend-box');
  let html = '';
  if (colorBySource) {
    for (const [src, label] of Object.entries(SOURCE_LABELS)) {
      const c = SOURCE_COLORS[src].fill.toString(16).padStart(6, '0');
      html += `<span style="background:#${c}"></span>${label} `;
    }
  } else if (colorByStory) {
    for (const s of [...currentStorySet].sort()) {
      const c = STORY_COLORS[s % STORY_COLORS.length].toString(16).padStart(6, '0');
      html += `<span style="background:#${c}"></span>S${s} `;
    }
  }
  html += `<span style="background:#c73"></span>Door `;
  html += `<span style="background:#3ad"></span>Window `;
  if (document.getElementById('show-full-model').checked) {
    html += `<span style="background:#be8ad8"></span>Opening `;
  }
  if (document.getElementById('show-overlaps').checked) {
    html += `<span style="background:#f22"></span>Overlap `;
  }
  if (document.getElementById('show-wall-clips').checked) {
    html += `<span style="background:#f66;opacity:0.3"></span>Clipped wall `;
  }
  if (document.getElementById('show-full-model').checked) {
    html += `<span style="background:#d2d8e0;opacity:0.45"></span>Heuristic shell reference `;
    html += `<span style="background:#8eb8d6"></span>Ontology roof replacement `;
    html += `<span style="background:#e5ded4"></span>Ontology wall replacement `;
    html += `<span style="background:#c8c2b7"></span>Ontology floor replacement `;
    html += `<span style="background:#d5cbc0"></span>Exact semantic ceiling `;
    html += `<span style="background:#f59e0b"></span>Fallback ceiling diagnostic `;
    html += `<span style="background:#e3bf96"></span>Knee wall `;
    html += `<span style="background:#f97316"></span>Unresolved coverage `;
    if (document.getElementById('show-full-model-diff')?.checked) {
      html += `<span style="background:#22d3ee"></span>Ontology diff roof `;
      html += `<span style="background:#a3e635"></span>Ontology diff exterior wall `;
      html += `<span style="background:#fb7185"></span>Ontology diff ceiling `;
      html += `<span style="background:#ef4444"></span>Ontology diff knee wall `;
    }
  }
  if (document.getElementById('show-thermal-ceilings')?.checked) {
    html += `<span style="background:#e85d04"></span>Thermal flat `;
    html += `<span style="background:#dc2f02"></span>Thermal slant `;
    html += `<span style="background:#f48c06"></span>Thermal cap `;
    html += `<span style="background:#ff006e"></span>Knee wall `;
    html += `<span style="background:#cc8844"></span>Dormer cheek `;
    html += `<span style="background:#ccaa44"></span>Dormer header `;
    html += `<span style="background:#e85d04"></span>Gap ceiling `;
  }
  if (document.getElementById('show-roof-clusters').checked && roofClusterData.length > 0) {
    html += '<br>';
    const compassDir = (deg) => {
      const dirs = ['N','NE','E','SE','S','SW','W','NW'];
      return dirs[Math.round(deg / 45) % 8];
    };
    for (const cl of roofClusterData) {
      const c = cl.color.toString(16).padStart(6, '0');
      if (cl.flat) {
        html += `<span style="background:#${c}"></span>Flat +${cl.height}m (${cl.count}) `;
      } else {
        html += `<span style="background:#${c}"></span>${cl.avgIncl.toFixed(0)}&deg; ${compassDir(cl.avgAzimuth)} (${cl.count}) `;
      }
    }
  }
  if (document.getElementById('show-ontology-semantics')?.checked) {
    html += '<br>';
    html += `<span style="background:#e5e7eb"></span>Building part `;
    html += `<span style="background:#0f766e"></span>Sloped roof coverage `;
    html += `<span style="background:#f59e0b"></span>Slope subpart `;
    html += `<span style="background:#dc2626"></span>Gable subpart `;
    html += `<span style="background:#7c3aed"></span>L/T branch `;
    html += `<span style="background:#0f766e"></span>Sloped atom `;
    html += `<span style="background:#c2410c"></span>Attic atom `;
    html += `<span style="background:#2563eb"></span>Flat cap `;
    html += `<span style="background:#dc2626"></span>Unresolved `;
    html += `<span style="background:#eab308"></span>Dormer `;
  }
  if (document.getElementById('show-ontology-continuation')?.checked) {
    html += '<br>';
    html += `<span style="background:#22d3ee"></span>Arrangement-face continuation `;
    html += `<span style="background:#38bdf8"></span>Continuation candidate `;
  }
  if (document.getElementById('show-ontology-cells')?.checked) {
    html += '<br>';
    html += `<span style="background:#c2410c"></span>Attic roof `;
    html += `<span style="background:#0f766e"></span>Upper-void roof `;
    html += `<span style="background:#60a5fa"></span>Slab faces `;
    html += `<span style="background:#e11d48"></span>Perimeter walls `;
    html += `<span style="background:#ff006e"></span>Knee walls `;
  }
  legendBox.innerHTML = html;
}

function setGhostStateOnMaterial(material, ghosted, opacityScale, minOpacity = 0.04) {
  if (!material || material.isLineBasicMaterial || material.isLineDashedMaterial) return;
  material.userData = material.userData || {};
  if (material.userData._ghostBaseOpacity === undefined) {
    material.userData._ghostBaseOpacity = Number.isFinite(material.opacity) ? material.opacity : 1.0;
    material.userData._ghostBaseTransparent = !!material.transparent;
    material.userData._ghostBaseDepthWrite = material.depthWrite !== false;
  }
  if (ghosted) {
    const baseOpacity = Number(material.userData._ghostBaseOpacity ?? 1.0);
    material.opacity = Math.max(minOpacity, baseOpacity * opacityScale);
    material.transparent = true;
    material.depthWrite = false;
  } else {
    material.opacity = Number(material.userData._ghostBaseOpacity ?? 1.0);
    material.transparent = !!material.userData._ghostBaseTransparent;
    material.depthWrite = material.userData._ghostBaseDepthWrite !== false;
  }
  material.needsUpdate = true;
}

function setGroupGhostState(group, ghosted, opacityScale, minOpacity = 0.04) {
  if (!group) return;
  group.traverse((obj) => {
    if (!obj?.isMesh || !obj.material) return;
    const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
    materials.forEach((material) => setGhostStateOnMaterial(material, ghosted, opacityScale, minOpacity));
  });
}

function updateFullModelReferencePresentation(bldg) {
  if (!bldg?.uuid) return;
  const showFullModel = !!document.getElementById('show-full-model')?.checked;
  const enhancement = fullModelEnhancementByUuid[bldg.uuid] || null;
  const ghostBaseline = showFullModel && !!enhancement?.hasEnhancement;
  setGroupGhostState(groups.fullModel, ghostBaseline, fullModelDiffModeEnabled ? 0.14 : 0.22, 0.035);
  setGroupGhostState(groups.fullModelHeuristicRoof, ghostBaseline, fullModelDiffModeEnabled ? 0.18 : 0.24, 0.05);
}

function getOntologyLoadState(uuid) {
  if (!ontologyLoadStateByUuid[uuid]) {
    ontologyLoadStateByUuid[uuid] = {
      streamToken: 0,
      streaming: false,
      requestedPartIds: new Set(),
      loadedPartIds: new Set(),
    };
  }
  return ontologyLoadStateByUuid[uuid];
}

function getLoadedOntologyParts(uuid) {
  return Object.values(ontologyPartDetailsByUuid[uuid] || {});
}

function getAllOntologyPartIds(summary) {
  const parts = Array.isArray(summary?.building_parts) ? summary.building_parts : [];
  return parts
    .map((part) => String(part?.id || ''))
    .filter(Boolean);
}

function getDefaultOntologyPartId(summary) {
  const parts = Array.isArray(summary?.building_parts) ? summary.building_parts : [];
  const fullBuilding = parts.find((part) => part?.synthetic_role === 'full_building');
  if (fullBuilding?.id) return String(fullBuilding.id);
  const real = parts.find((part) => !part?.synthetic);
  return String((real || parts[0] || {}).id || '') || null;
}

function getSelectedOntologyPartId(uuid) {
  return selectedOntologyPartByUuid[uuid] || null;
}

function setSelectedOntologyPart(uuid, partId, { announce = false } = {}) {
  if (!uuid || !partId) return;
  selectedOntologyPartByUuid[uuid] = partId;
  const bldg = DATA[currentBuilding];
  if (bldg?.uuid === uuid) {
    renderOntologySemanticsForBuilding(bldg);
    renderOntologyContinuationForBuilding(bldg);
    renderOntologyExactForBuilding(bldg);
    updateOntologyStatusInfo();
    if (announce) setMapStatus(`Selected ontology part ${partId}`);
    if (document.getElementById('show-ontology-cells')?.checked) {
      ensureOntologyPart(uuid, partId).then(() => {
        if (DATA[currentBuilding]?.uuid !== uuid) return;
        renderOntologyExactForBuilding(bldg);
        renderLegend();
      });
    }
  }
}

function updateOntologyStatusInfo() {
  const bldg = DATA[currentBuilding];
  if (!bldg) return;
  const showSemantics = !!document.getElementById('show-ontology-semantics')?.checked;
  const showContinuation = !!document.getElementById('show-ontology-continuation')?.checked;
  const showCells = !!document.getElementById('show-ontology-cells')?.checked;
  const showFullModel = !!document.getElementById('show-full-model')?.checked;
  if (!showSemantics && !showContinuation && !showCells && !showFullModel) {
    document.getElementById('building-info').innerHTML = buildingInfoBaseHtml;
    return;
  }
  const summary = ontologySummaryByUuid[bldg.uuid];
  const loadState = getOntologyLoadState(bldg.uuid);
  const partCount = Array.isArray(summary?.building_parts) ? summary.building_parts.length : 0;
  const selectedPartId = getSelectedOntologyPartId(bldg.uuid) || getDefaultOntologyPartId(summary);
  const enhancement = fullModelEnhancementByUuid[bldg.uuid] || null;
  const summaryLine = summary
    ? `Ontology summary: ${summary.metadata?.oblique_coverage_patch_count || 0} slope patches, ${summary.metadata?.roof_continuation_region_count || 0} continuation regions, ${summary.metadata?.coverage_subpart_count || 0} subparts, ${summary.metadata?.unresolved_region_count || 0} unresolved`
    : 'Ontology summary: not loaded';
  const continuationLine = showContinuation
    ? `Continuation diagnostics: ${summary?.metadata?.roof_continuation_region_count || 0} arrangement-face regions`
    : 'Continuation diagnostics: layer hidden';
  const exactLine = showCells
    ? `Exact part: ${selectedPartId || 'none'}${selectedPartId && loadState.loadedPartIds.has(selectedPartId) ? ' loaded' : ''}`
    : 'Exact part payloads: layer hidden';
  const fullModelLine = showFullModel
    ? (enhancement
      ? `Full model ontology: ${enhancement.hasEnhancement ? 'active' : 'no exact replacement'}${enhancement.hasEnhancement ? ` (${enhancement.roofFaceCount} roof faces, ${enhancement.baseWallCount} base walls, ${enhancement.baseFloorCount} base floors, ${enhancement.fenestrationCount} fenestration surfaces, ${enhancement.exteriorWallCount} scaffold exterior walls, ${enhancement.occupiedSurfaceCount} scaffold occupied-room surfaces, ${enhancement.ceilingSurfaceCount} exact semantic ceilings${enhancement.fallbackCeilingCount ? `, ${enhancement.fallbackCeilingCount} fallback ceilings` : ''}, ${enhancement.kneeWallCount} knee walls${enhancement.unresolvedCount ? `, ${enhancement.unresolvedCount} unresolved` : ''}${fullModelDiffModeEnabled ? ', diff mode' : ', heuristic shell ghosted'})` : ''}`
      : `Full model ontology: loading ${partCount > 0 ? `${loadState.loadedPartIds.size}/${partCount} parts` : 'summary'}`)
    : 'Full model ontology: layer hidden';
  document.getElementById('building-info').innerHTML =
    `${buildingInfoBaseHtml}<br><span style="color:#67e8f9">${summaryLine}</span><br><span style="color:#22d3ee">${continuationLine}</span><br><span style="color:#93c5fd">${exactLine}</span><br><span style="color:#c4b5fd">${fullModelLine}</span>`;
}

function renderOntologySemanticsForBuilding(bldg) {
  disposeGroup(groups.ontologySemantics);
  const summary = ontologySummaryByUuid[bldg.uuid] || null;
  if (!summary) {
    updateOntologyStatusInfo();
    return;
  }
  renderOntologySemantics({
    ontologySummary: summary,
    selectedPartId: getSelectedOntologyPartId(bldg.uuid) || getDefaultOntologyPartId(summary),
    groups,
    createPolygonMesh,
    createEdgeLoop,
    attachLocator,
    buildingUuid: bldg.uuid,
  });
  updateOntologyStatusInfo();
}

function renderOntologyContinuationForBuilding(bldg) {
  disposeGroup(groups.ontologyContinuation);
  const summary = ontologySummaryByUuid[bldg.uuid] || null;
  if (!summary) {
    updateOntologyStatusInfo();
    return;
  }
  renderOntologyContinuationDiagnostics({
    ontologySummary: summary,
    selectedPartId: getSelectedOntologyPartId(bldg.uuid) || getDefaultOntologyPartId(summary),
    groups,
    createPolygonMesh,
    createEdgeLoop,
    attachLocator,
    buildingUuid: bldg.uuid,
  });
  updateOntologyStatusInfo();
}

function renderOntologyExactForBuilding(bldg) {
  disposeGroup(groups.ontologyCells);
  const selectedPartId = getSelectedOntologyPartId(bldg.uuid) || getDefaultOntologyPartId(ontologySummaryByUuid[bldg.uuid]);
  const parts = getLoadedOntologyParts(bldg.uuid).filter((payload) => payload?.part_id === selectedPartId);
  renderOntologyExact({
    ontologyParts: parts,
    groups,
    createPolygonMesh,
    createEdgeLoop,
    attachLocator,
    buildingUuid: bldg.uuid,
  });
  updateOntologyStatusInfo();
}

function renderFullModelOntologyForBuilding(bldg) {
  disposeGroup(groups.fullModelOntology);
  fullModelEnhancementByUuid[bldg.uuid] = null;
  const summary = ontologySummaryByUuid[bldg.uuid] || null;
  const parts = getLoadedOntologyParts(bldg.uuid);
  if (!summary || parts.length === 0) {
    groups.fullModel.visible = !!document.getElementById('show-full-model')?.checked;
    groups.fullModelHeuristicRoof.visible = groups.fullModel.visible;
    updateFullModelReferencePresentation(bldg);
    updateOntologyStatusInfo();
    return null;
  }
  const enhancement = renderOntologyEnhancedFullModel({
    ontologySummary: summary,
    ontologyParts: parts,
    groups,
    createPolygonMesh,
    createEdgeLoop,
    attachLocator,
    buildingUuid: bldg.uuid,
    diffMode: fullModelDiffModeEnabled,
  });
  fullModelEnhancementByUuid[bldg.uuid] = enhancement;
  const showFullModel = !!document.getElementById('show-full-model')?.checked;
  groups.fullModel.visible = showFullModel;
  groups.fullModelHeuristicRoof.visible = showFullModel;
  groups.fullModelOntology.visible = showFullModel;
  updateFullModelReferencePresentation(bldg);
  updateOntologyStatusInfo();
  return enhancement;
}

function renderAncillaryBuildingLayers(bldg, pyResult) {
  try {
    roofClusterData = renderRoofFromPythonResult({
      pyResult,
      THREE,
      groups,
      createLine,
      createPolygonMesh,
      createEdgeLoop,
      roofClusterColors: ROOF_CLUSTER_COLORS,
      attachLocator,
      buildingUuid: bldg.uuid,
    });
  } catch (err) {
    roofClusterData = [];
    console.error('Roof render failed', bldg?.uuid, err);
  }
  try {
    renderOntologySemanticsForBuilding(bldg);
  } catch (err) {
    console.error('Ontology semantics render failed', bldg?.uuid, err);
  }
  try {
    renderOntologyContinuationForBuilding(bldg);
  } catch (err) {
    console.error('Ontology continuation render failed', bldg?.uuid, err);
  }
  try {
    renderOntologyExactForBuilding(bldg);
  } catch (err) {
    console.error('Ontology exact render failed', bldg?.uuid, err);
  }
  try {
    maybeLoadOntologyForCurrentBuilding();
  } catch (err) {
    console.error('Ontology load trigger failed', bldg?.uuid, err);
  }
}

function ensureOntologySummary(uuid) {
  if (ontologySummaryByUuid[uuid]) return Promise.resolve(ontologySummaryByUuid[uuid]);
  if (ontologySummaryPromiseByUuid[uuid]) return ontologySummaryPromiseByUuid[uuid];
  ontologySummaryPromiseByUuid[uuid] = fetch(
    `ontology-artifacts?uuid=${encodeURIComponent(uuid)}&view=summary`,
    { cache: 'no-store' },
  )
    .then((resp) => {
      if (!resp.ok) throw new Error(`Ontology summary fetch failed: ${resp.status}`);
      return resp.json();
    })
    .then((data) => {
      ontologySummaryByUuid[uuid] = data;
      return data;
    })
    .catch((err) => {
      console.warn('Failed to load ontology summary', uuid, err);
      return null;
    })
    .finally(() => {
      delete ontologySummaryPromiseByUuid[uuid];
    });
  return ontologySummaryPromiseByUuid[uuid];
}

function ensureOntologyPart(uuid, partId) {
  ontologyPartDetailsByUuid[uuid] = ontologyPartDetailsByUuid[uuid] || {};
  ontologyPartPromiseByUuid[uuid] = ontologyPartPromiseByUuid[uuid] || {};
  if (ontologyPartDetailsByUuid[uuid][partId]) return Promise.resolve(ontologyPartDetailsByUuid[uuid][partId]);
  if (ontologyPartPromiseByUuid[uuid][partId]) return ontologyPartPromiseByUuid[uuid][partId];
  const loadState = getOntologyLoadState(uuid);
  loadState.requestedPartIds.add(partId);
  ontologyPartPromiseByUuid[uuid][partId] = fetch(
    `ontology-artifacts?uuid=${encodeURIComponent(uuid)}&view=part&part_id=${encodeURIComponent(partId)}`,
    { cache: 'no-store' },
  )
    .then((resp) => {
      if (!resp.ok) throw new Error(`Ontology part fetch failed: ${resp.status}`);
      return resp.json();
    })
    .then((data) => {
      ontologyPartDetailsByUuid[uuid][partId] = data;
      loadState.loadedPartIds.add(partId);
      return data;
    })
    .catch((err) => {
      console.warn('Failed to load ontology part', uuid, partId, err);
      return null;
    })
    .finally(() => {
      delete ontologyPartPromiseByUuid[uuid][partId];
      updateOntologyStatusInfo();
    });
  return ontologyPartPromiseByUuid[uuid][partId];
}

function ensureOntologyAllParts(uuid, summary = null) {
  return Promise.resolve(summary || ensureOntologySummary(uuid)).then((resolvedSummary) => {
    if (!resolvedSummary) return [];
    const partIds = getAllOntologyPartIds(resolvedSummary);
    if (partIds.length === 0) return [];
    return Promise.all(partIds.map((partId) => ensureOntologyPart(uuid, partId)));
  });
}

function maybeLoadOntologyForCurrentBuilding() {
  const bldg = DATA[currentBuilding];
  if (!bldg?.uuid) return;
  const showSemantics = !!document.getElementById('show-ontology-semantics')?.checked;
  const showContinuation = !!document.getElementById('show-ontology-continuation')?.checked;
  const showCells = !!document.getElementById('show-ontology-cells')?.checked;
  const showFullModel = !!document.getElementById('show-full-model')?.checked;
  if (!showSemantics && !showContinuation && !showCells && !showFullModel) {
    updateOntologyStatusInfo();
    return;
  }
  ensureOntologySummary(bldg.uuid).then((summary) => {
    if (!summary) return;
    if (!DATA[currentBuilding] || DATA[currentBuilding].uuid !== bldg.uuid) return;
    if (!getSelectedOntologyPartId(bldg.uuid)) {
      const defaultPartId = getDefaultOntologyPartId(summary);
      if (defaultPartId) selectedOntologyPartByUuid[bldg.uuid] = defaultPartId;
    }
    renderOntologySemanticsForBuilding(bldg);
    renderOntologyContinuationForBuilding(bldg);
    renderLegend();
    if (showFullModel) {
      ensureOntologyAllParts(bldg.uuid, summary).then(() => {
        if (!DATA[currentBuilding] || DATA[currentBuilding].uuid !== bldg.uuid) return;
        renderFullModelOntologyForBuilding(bldg);
        renderLegend();
        updateOntologyStatusInfo();
      });
    }
    if (!showCells) {
      renderOntologyExactForBuilding(bldg);
      return;
    }
    const partId = getSelectedOntologyPartId(bldg.uuid);
    if (!partId) {
      updateOntologyStatusInfo();
      return;
    }
    ensureOntologyPart(bldg.uuid, partId).then(() => {
      if (!DATA[currentBuilding] || DATA[currentBuilding].uuid !== bldg.uuid) return;
      renderOntologyExactForBuilding(bldg);
      renderLegend();
      updateOntologyStatusInfo();
    });
  });
}

function renderPipelineStatus() {
  const current = PIPELINE_STEPS[pipelineStepIndex];
  const currentLabel = current ? current.label : 'Unknown';
  document.getElementById('pipeline-current').textContent =
    `Step ${pipelineStepIndex + 1}/${PIPELINE_STEPS.length}: ${currentLabel}`;

  const prevBtn = document.getElementById('pipeline-prev');
  const nextBtn = document.getElementById('pipeline-next');
  prevBtn.disabled = pipelineStepIndex <= 0;
  nextBtn.disabled = pipelineStepIndex >= PIPELINE_STEPS.length - 1;

  const holder = document.getElementById('pipeline-steps');
  holder.innerHTML = PIPELINE_STEPS.map((step, i) => {
    const cls = i < pipelineStepIndex ? 'pipeline-step-pill done' : (i === pipelineStepIndex ? 'pipeline-step-pill active' : 'pipeline-step-pill');
    return `<span class="${cls}" data-step="${i}">${i + 1}. ${step.label}</span>`;
  }).join('');
}

function applyPipelineStep(stepIndex) {
  pipelineStepIndex = Math.max(0, Math.min(stepIndex, PIPELINE_STEPS.length - 1));
  const vis = buildPipelineVisibility(pipelineStepIndex);
  for (const key of LAYER_KEYS) setLayerVisibility(key, !!vis[key], true);
  renderPipelineStatus();
  renderLegend();
}

function normalizeDeg(d) {
  let x = d % 360;
  if (x > 180) x -= 360;
  if (x < -180) x += 360;
  return x;
}

function setMapAlignLabel(id, value) {
  document.getElementById(id).textContent = String(Number(value));
}

function applyAlignmentStateToControls(state) {
  const rot = Number(state?.rotation_deg ?? 0);
  const east = Number(state?.offset_east_m ?? 0);
  const north = Number(state?.offset_north_m ?? 0);
  document.getElementById('map-rot').value = String(rot);
  document.getElementById('map-east').value = String(east);
  document.getElementById('map-north').value = String(north);
  setMapAlignLabel('map-rot-val', rot);
  setMapAlignLabel('map-east-val', east);
  setMapAlignLabel('map-north-val', north);
  modelMapRotationDeg = rot;
  modelMapOffsetEastM = east;
  modelMapOffsetNorthM = north;
}

function queueSaveAlignmentForCurrentBuilding() {
  const bldg = DATA[currentBuilding];
  if (!bldg?.uuid) return;
  if (alignmentSaveTimer) clearTimeout(alignmentSaveTimer);
  alignmentSaveTimer = setTimeout(async () => {
    const payload = {
      uuid: bldg.uuid,
      rotation_deg: modelMapRotationDeg,
      offset_east_m: modelMapOffsetEastM,
      offset_north_m: modelMapOffsetNorthM,
    };
    alignmentByUuid[bldg.uuid] = {
      rotation_deg: payload.rotation_deg,
      offset_east_m: payload.offset_east_m,
      offset_north_m: payload.offset_north_m,
    };
    try {
      await fetch('/alignment-calibration', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch (_err) {
      // Keep local state; save can be retried on next adjustment.
    }
  }, 220);
}

function computeModelFootprintGeoJSON(bldg) {
  const gps = bldg.gps;
  if (!gps || typeof gps.lng !== 'number' || typeof gps.lat !== 'number') return null;

  const roomPolys = [];
  const allPts = [];
  for (const room of (bldg.rooms || [])) {
    const fp = room.floor_polygon;
    if (!Array.isArray(fp) || fp.length < 3) continue;
    const pts = fp.map(c => [c[0], c[2]]);
    roomPolys.push(pts);
    allPts.push(...pts);
  }
  if (allPts.length < 3 || roomPolys.length === 0) return null;

  let cx = 0, cz = 0;
  for (const p of allPts) { cx += p[0]; cz += p[1]; }
  cx /= allPts.length;
  cz /= allPts.length;

  const theta = modelMapRotationDeg * Math.PI / 180;
  const ct = Math.cos(theta), st = Math.sin(theta);
  const lat0 = gps.lat;
  const lng0 = gps.lng;
  const metersPerDegLat = 111320;
  const metersPerDegLng = 111320 * Math.cos(lat0 * Math.PI / 180);

  function toLngLat(x, z) {
    const dx = x - cx;
    const dz = z - cz;
    const dn = -dz;
    const e = (ct * dx - st * dn) + modelMapOffsetEastM;
    const n = (st * dx + ct * dn) + modelMapOffsetNorthM;
    return [lng0 + (e / metersPerDegLng), lat0 + (n / metersPerDegLat)];
  }

  const features = roomPolys.map(poly => {
    const ring = poly.map(([x, z]) => toLngLat(x, z));
    ring.push(ring[0]);
    return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } };
  });
  return { type: 'FeatureCollection', features };
}

const orthoController = createOrthoMapController({
  maplibregl: window.maplibregl,
  emptyMapStyle: EMPTY_MAP_STYLE,
  getCurrentBuilding: () => DATA[currentBuilding],
  getAllData: () => DATA,
  getCurrentBuildingIndex: () => currentBuilding,
  getAnchorModeEnabled: () => anchorModeEnabled,
  setAnchorModeEnabled: (v) => { anchorModeEnabled = v; },
  getModelAlignment: () => ({
    rotationDeg: modelMapRotationDeg,
    eastM: modelMapOffsetEastM,
    northM: modelMapOffsetNorthM,
    enabled: modelMapEnabled,
  }),
  setModelOffsets: (eastM, northM) => { modelMapOffsetEastM = eastM; modelMapOffsetNorthM = northM; },
  applyAlignmentStateToControls,
  queueSaveAlignmentForCurrentBuilding,
  computeModelFootprintGeoJSON,
  onSetStatus: (txt) => {
    const statusEl = document.getElementById('map-panel-status');
    statusEl.textContent = txt || '';
  },
});

function setMapStatus(text) {
  orthoController.setMapStatus(text);
}

function updateModelMapOverlay(bldg) {
  orthoController.updateModelMapOverlay(bldg);
}

function updateOrthoPanelForBuilding(bldg) {
  orthoController.updateOrthoPanelForBuilding(bldg, orthoEnabled);
}

function getOrthoMap() {
  return orthoController.getMap();
}

function loadBuilding(index, { resetPipeline = true } = {}) {
  currentBuilding = index;
  elementMeshByUid.clear();
  [groups.merged, groups.computed, groups.doors, groups.windows, groups.floors, groups.gaps, groups.crossStory, groups.extensions, groups.overlaps, groups.wallClips, groups.extGaps, groups.ceilings, groups.thermalCeilings, groups.roofClusters, groups.fullModelHeuristicRoof, groups.fullModelOntology, groups.ontologySemantics, groups.ontologyContinuation, groups.ontologyCells, groups.fullModel, groups.selection].forEach(disposeGroup);
  roofClusterData = [];

  const bldg = DATA[index];
  fullModelEnhancementByUuid[bldg.uuid] = null;
  groups.fullModelHeuristicRoof.visible = groups.fullModel.visible;
  groups.fullModelOntology.visible = groups.fullModel.visible;
  applyAlignmentStateToControls(alignmentByUuid[bldg.uuid] || {});

  const allCorners = bldg.rooms.flatMap(r =>
    (r.walls_computed.length > 0 ? r.walls_computed : r.walls_merged).flatMap(w => w.corners)
  );
  let cx = 0, cy = 0, cz = 0;
  for (const c of allCorners) { cx += c[0]; cy += c[1]; cz += c[2]; }
  if (allCorners.length > 0) { cx /= allCorners.length; cy /= allCorners.length; cz /= allCorners.length; }

  const storySet = new Set(bldg.rooms.map(r => r.story));
  currentStorySet = storySet;
  let hasRoomCeilingFill = false;

  bldg.rooms.forEach((room, ri) => {
    const story = room.story || 0;
    const floorColor = colorByStory ? STORY_COLORS[story % STORY_COLORS.length] : ROOM_COLORS[ri % ROOM_COLORS.length];
    const wallColor = colorByStory ? STORY_WALL_COLORS[story % STORY_WALL_COLORS.length] : 0x44aa88;
    const wallEdge = colorByStory ? STORY_COLORS[story % STORY_COLORS.length] : 0x66ccaa;

    for (const w of room.walls_merged) {
      if (w.corners.length < 3) continue;
      const mesh = createPolygonMesh(w.corners, MERGED_COLOR, 0.4);
      if (mesh) {
        attachLocator(mesh, {
          buildingUuid: bldg.uuid,
          kind: "wall-merged",
          id: String(w.id || ""),
          roomId: `${story}:${ri}`,
          story,
          source: w.source || "merged",
          corners: w.corners,
          lineage: w.lineage || [],
        });
        groups.merged.add(mesh);
      }
      groups.merged.add(createEdgeLoop(w.corners, MERGED_EDGE));
    }

    // Computed walls: color by source provenance or by story/room
    if (colorBySource) {
      for (const w of room.walls_computed) {
        if (w.corners.length < 3) continue;
        const src = SOURCE_COLORS[w.source] || SOURCE_COLORS['merged-room'];
        const mesh = createPolygonMesh(w.corners, src.fill, 0.5);
        if (mesh) {
          attachLocator(mesh, {
            buildingUuid: bldg.uuid,
            kind: "wall-computed",
            id: String(w.id || ""),
            roomId: `${story}:${ri}`,
            story,
            source: w.source || "",
            corners: w.corners,
            lineage: w.lineage || [],
          });
          groups.computed.add(mesh);
        }
        groups.computed.add(createEdgeLoop(w.corners, src.edge));
      }
    } else {
      for (const w of room.walls_computed) {
        if (w.corners.length < 3) continue;
        const mesh = createPolygonMesh(w.corners, wallColor, 0.5);
        if (mesh) {
          attachLocator(mesh, {
            buildingUuid: bldg.uuid,
            kind: "wall-computed",
            id: String(w.id || ""),
            roomId: `${story}:${ri}`,
            story,
            source: w.source || "",
            corners: w.corners,
            lineage: w.lineage || [],
          });
          groups.computed.add(mesh);
        }
        groups.computed.add(createEdgeLoop(w.corners, wallEdge));
      }
    }

    // Render wall extension strips (computed portions closing floor gaps)
    // extension_strip is a list of quads (each quad is 4 corners)
    for (const w of room.walls_computed) {
      if (w.extension_strip && w.extension_strip.length > 0) {
        const strips = Array.isArray(w.extension_strip[0]?.[0]) ? w.extension_strip : [w.extension_strip];
        for (const quad of strips) {
          if (quad.length >= 3) {
            const mesh = createPolygonMesh(quad, 0xffaa44, 0.35);
            if (mesh) {
              attachLocator(mesh, {
                buildingUuid: bldg.uuid,
                kind: "wall-extension",
                id: `${w.id || "wall"}:${story}:${ri}`,
                roomId: `${story}:${ri}`,
                story,
                source: w.source || "",
                corners: quad,
                lineage: w.lineage || [],
              });
              groups.extensions.add(mesh);
            }
            groups.extensions.add(createEdgeLoop(quad, 0xff8800));
          }
        }
      }
    }

    // Doors
    for (const d of (room.doors || [])) {
      if (d.corners.length >= 3) {
        const mesh = createPolygonMesh(d.corners, DOOR_COLOR, 0.7);
        if (mesh) {
          attachLocator(mesh, {
            buildingUuid: bldg.uuid,
            kind: "door",
            id: String(d.id || ""),
            roomId: `${story}:${ri}`,
            story,
            source: d.source || "",
            corners: d.corners,
            lineage: d.lineage || [],
          });
          groups.doors.add(mesh);
        }
        groups.doors.add(createEdgeLoop(d.corners, DOOR_EDGE));
      }
    }

    // Windows
    for (const w of (room.windows || [])) {
      if (w.corners.length >= 3) {
        const mesh = createPolygonMesh(w.corners, WINDOW_COLOR, 0.6);
        if (mesh) {
          attachLocator(mesh, {
            buildingUuid: bldg.uuid,
            kind: "window",
            id: String(w.id || ""),
            roomId: `${story}:${ri}`,
            story,
            source: w.source || "",
            corners: w.corners,
            lineage: w.lineage || [],
          });
          groups.windows.add(mesh);
        }
        groups.windows.add(createEdgeLoop(w.corners, WINDOW_EDGE));
      }
    }

    if (room.floor_polygon && room.floor_polygon.length >= 3) {
      const floorMesh = createPolygonMesh(room.floor_polygon, floorColor, 0.4);
      if (floorMesh) {
        attachLocator(floorMesh, {
          buildingUuid: bldg.uuid,
          kind: "floor",
          id: `${story}:${ri}`,
          roomId: `${story}:${ri}`,
          story,
          source: "room-floor",
          corners: room.floor_polygon,
          lineage: [],
        });
        groups.floors.add(floorMesh);
      }
      groups.floors.add(createEdgeLoop(room.floor_polygon, floorColor));
    }

    // Floor overlap regions (clipped area visualization)
    if (room.floor_overlap_region && room.floor_overlap_region.length >= 3) {
      const overlapMesh = createPolygonMesh(room.floor_overlap_region, 0xff2222, 0.5);
      if (overlapMesh) {
        attachLocator(overlapMesh, {
          buildingUuid: bldg.uuid,
          kind: "floor-overlap",
          id: `${story}:${ri}`,
          roomId: `${story}:${ri}`,
          story,
          source: "overlap",
          corners: room.floor_overlap_region,
          lineage: [],
        });
        groups.overlaps.add(overlapMesh);
      }
      groups.overlaps.add(createEdgeLoop(room.floor_overlap_region, 0xff4444));
    }

    // Wall clip ghosts (original extent of clipped staircase walls)
    for (const w of room.walls_computed) {
      if (w.wall_clipped && w.corners_original && w.corners_original.length >= 3) {
        const ghost = createPolygonMesh(w.corners_original, 0xff6666, 0.15);
        if (ghost) {
          attachLocator(ghost, {
            buildingUuid: bldg.uuid,
            kind: "wall-clipped-original",
            id: String(w.id || ""),
            roomId: `${story}:${ri}`,
            story,
            source: w.source || "",
            corners: w.corners_original,
            lineage: w.lineage || [],
          });
          groups.wallClips.add(ghost);
        }
        groups.wallClips.add(createEdgeLoop(w.corners_original, 0xff4444));
      }
    }

    // OLD ceiling rendering commented out — replaced by cluster-based construction below
    // if (room.ceiling_mesh_triangles && room.ceiling_mesh_triangles.length > 0) { ... }
    // else if (room.ceiling_polygon && room.ceiling_polygon.length >= 3) { ... }

  });

  // OLD building-level roof envelope — commented out
  // if (bldg.roof_mesh_triangles && bldg.roof_mesh_triangles.length > 0) { ... }

  const pyResult = bldg.roof_surfaces ? bldg : pyRoofByUuid[bldg.uuid];
  renderAncillaryBuildingLayers(bldg, pyResult);

  // Thermal ceiling surfaces over detected gaps.
  // Skip cross_story gap ceilings when the roof pipeline produced thermal
  // ceilings — the thermal system (thermal-knee, thermal-cap, etc.) already
  // handles cross-story coverage and avoids extending into building extensions.
  const THERMAL_GAP_COLOR = 0xe85d04;
  const THERMAL_GAP_OPACITY = 0.5;
  const thermalCeilings = Array.isArray(pyResult?.ceiling?.thermal) ? pyResult.ceiling.thermal : [];
  const hasThermalCeilings = thermalCeilings.length > 0;
  // a) cross_floor_gaps (within_story + cross_story horizontal gap polygons)
  for (let gi = 0; gi < (bldg.cross_floor_gaps || []).length; gi++) {
    const gap = bldg.cross_floor_gaps[gi];
    // When thermal ceilings exist, cross_story gaps are redundant — those
    // areas are already covered by thermal-knee surfaces.
    if (hasThermalCeilings && gap.type === 'cross_story') continue;
    // Use ceiling_corners (raised to wall-top Y) when available; fall back to floor-level corners
    const ceilCorners = gap.ceiling_corners || gap.corners;
    if (!ceilCorners || ceilCorners.length < 3) continue;
    const mesh = createPolygonMesh(ceilCorners, THERMAL_GAP_COLOR, THERMAL_GAP_OPACITY);
    if (mesh) {
      mesh.renderOrder = 55;
      mesh.material.depthTest = true;
      mesh.material.depthWrite = false;
      if (attachLocator) attachLocator(mesh, {
        buildingUuid: bldg.uuid,
        kind: 'thermal-ceiling',
        id: `thermal:gap:${gi}`,
        corners: ceilCorners,
      });
      groups.thermalCeilings.add(mesh);
    }
    groups.thermalCeilings.add(createEdgeLoop(ceilCorners, THERMAL_GAP_COLOR, 0.6));
  }
  // b) gap_closures with type=ceiling
  for (let ci = 0; ci < (bldg.gap_closures || []).length; ci++) {
    const gc = bldg.gap_closures[ci];
    if (gc.type !== 'ceiling' || !gc.corners || gc.corners.length < 3) continue;
    const mesh = createPolygonMesh(gc.corners, THERMAL_GAP_COLOR, THERMAL_GAP_OPACITY);
    if (mesh) {
      mesh.renderOrder = 55;
      mesh.material.depthTest = true;
      mesh.material.depthWrite = false;
      if (attachLocator) attachLocator(mesh, {
        buildingUuid: bldg.uuid,
        kind: 'thermal-ceiling',
        id: `thermal:closure-ceil:${ci}`,
        corners: gc.corners,
      });
      groups.thermalCeilings.add(mesh);
    }
    groups.thermalCeilings.add(createEdgeLoop(gc.corners, THERMAL_GAP_COLOR, 0.6));
  }

  // Cross-floor gap regions
  // within_story = strips between rooms (magenta), cross_story = coverage differences (orange)
  const WITHIN_COLORS = { high: 0xff00ff, medium: 0xcc44ff, low: 0x8866ff };
  const CROSS_COLORS = { high: 0xff8800, medium: 0xffaa44, low: 0xffcc88 };
  const GAP_OPACITIES = { high: 0.55, medium: 0.4, low: 0.25 };
  const gapList = bldg.cross_floor_gaps || [];
  for (const gap of gapList) {
    if (gap.corners && gap.corners.length >= 3) {
      const isCross = gap.type === 'cross_story';
      const palette = isCross ? CROSS_COLORS : WITHIN_COLORS;
      const col = palette[gap.confidence] || 0xff2222;
      const opa = GAP_OPACITIES[gap.confidence] || 0.3;
      const targetGroup = isCross ? groups.crossStory : groups.gaps;
      const gapMesh = createPolygonMesh(gap.corners, col, opa);
      if (gapMesh) {
        attachLocator(gapMesh, {
          buildingUuid: bldg.uuid,
          kind: isCross ? "gap-cross-story" : "gap-within-story",
          id: String(gap.id || `${gap.type || "gap"}:${gap.confidence || "unknown"}:${targetGroup.children.length}`),
          roomId: "",
          story: Number.isFinite(gap.story) ? gap.story : null,
          source: gap.confidence || "",
          corners: gap.corners,
          lineage: gap.lineage || [],
        });
        targetGroup.add(gapMesh);
      }
      targetGroup.add(createEdgeLoop(gap.corners, col));
    }
  }

  // Stitch walls (fill gaps between disconnected wall endpoints)
  const STITCH_COLOR = 0x44aa88;
  const STITCH_EDGE = 0x66ccaa;
  for (const sw of (bldg.stitch_walls || [])) {
    if (sw.corners && sw.corners.length >= 3) {
      const sCol = colorByStory ? STORY_WALL_COLORS[(sw.story || 0) % STORY_WALL_COLORS.length] : STITCH_COLOR;
      const sEdge = colorByStory ? STORY_COLORS[(sw.story || 0) % STORY_COLORS.length] : STITCH_EDGE;
      const mesh = createPolygonMesh(sw.corners, sCol, 0.5);
      if (mesh) {
        attachLocator(mesh, {
          buildingUuid: bldg.uuid,
          kind: "wall-stitch",
          id: String(sw.id || `stitch:${sw.story || 0}:${groups.computed.children.length}`),
          roomId: "",
          story: Number(sw.story || 0),
          source: "stitch",
          corners: sw.corners,
          lineage: sw.lineage || [],
        });
        groups.computed.add(mesh);
      }
      groups.computed.add(createEdgeLoop(sw.corners, sEdge));
    }
  }

  // Gap walls (vertical walls + floor/ceiling quads along cross-floor gap edges)
  const GAP_WALL_COLORS = {
    wall:    { fill: 0xcc44ff, edge: 0xaa22dd },
    floor:   { fill: 0x88bb44, edge: 0x669933 },
    ceiling: { fill: 0x4488dd, edge: 0x3366bb },
  };
  for (const gw of (bldg.gap_walls || [])) {
    if (gw.corners && gw.corners.length >= 3) {
      const palette = gw.type === 'gap_floor' ? GAP_WALL_COLORS.floor
                    : gw.type === 'gap_ceiling' ? GAP_WALL_COLORS.ceiling
                    : GAP_WALL_COLORS.wall;
      const mesh = createPolygonMesh(gw.corners, palette.fill, 0.35);
      if (mesh) {
        attachLocator(mesh, {
          buildingUuid: bldg.uuid,
          kind: "gap-wall",
          id: String(gw.id || `${gw.type || "wall"}:${groups.gaps.children.length}`),
          roomId: "",
          story: Number.isFinite(gw.story) ? gw.story : null,
          source: gw.type || "",
          corners: gw.corners,
          lineage: gw.lineage || [],
        });
        groups.gaps.add(mesh);
      }
      groups.gaps.add(createEdgeLoop(gw.corners, palette.edge));
    }
  }

  // Exterior gap indicators (door/opening + parallel wall pairs)
  const extGapList = bldg.exterior_gap_indicators || [];
  const EXT_GAP_COLOR = 0xff44ff;
  const EXT_GAP_EDGE = 0xff66ff;
  for (const ind of extGapList) {
    if (ind.element_corners && ind.element_corners.length >= 3) {
      const mesh = createPolygonMesh(ind.element_corners, EXT_GAP_COLOR, 0.7);
      if (mesh) {
        attachLocator(mesh, {
          buildingUuid: bldg.uuid,
          kind: "exterior-gap-element",
          id: String(ind.id || `element:${groups.extGaps.children.length}`),
          roomId: "",
          story: Number.isFinite(ind.story) ? ind.story : null,
          source: "exterior-gap",
          corners: ind.element_corners,
          lineage: ind.lineage || [],
        });
        groups.extGaps.add(mesh);
      }
      groups.extGaps.add(createEdgeLoop(ind.element_corners, EXT_GAP_EDGE));
    }
    if (ind.wall_corners && ind.wall_corners.length >= 3) {
      const mesh = createPolygonMesh(ind.wall_corners, EXT_GAP_COLOR, 0.4);
      if (mesh) {
        attachLocator(mesh, {
          buildingUuid: bldg.uuid,
          kind: "exterior-gap-wall",
          id: String(ind.id || `wall:${groups.extGaps.children.length}`),
          roomId: "",
          story: Number.isFinite(ind.story) ? ind.story : null,
          source: "exterior-gap",
          corners: ind.wall_corners,
          lineage: ind.lineage || [],
        });
        groups.extGaps.add(mesh);
      }
      groups.extGaps.add(createEdgeLoop(ind.wall_corners, EXT_GAP_EDGE));
    }
  }

  // Gap closures (side/floor/ceiling quads filling detected gaps)
  const GAP_CLOSURE_COLORS = {
    side:    { fill: 0x44ddaa, edge: 0x33bb88 },
    floor:   { fill: 0x88bb44, edge: 0x669933 },
    ceiling: { fill: 0x4488dd, edge: 0x3366bb },
  };
  const GAP_CLOSURE_DEFAULT = { fill: 0x44ddaa, edge: 0x33bb88 };
  for (const gc of (bldg.gap_closures || [])) {
    if (gc.corners && gc.corners.length >= 3) {
      const palette = GAP_CLOSURE_COLORS[gc.type] || GAP_CLOSURE_DEFAULT;
      const mesh = createPolygonMesh(gc.corners, palette.fill, 0.5);
      if (mesh) {
        attachLocator(mesh, {
          buildingUuid: bldg.uuid,
          kind: "gap-closure",
          id: String(gc.id || `${gc.type || "closure"}:${groups.extGaps.children.length}`),
          roomId: "",
          story: Number.isFinite(gc.story) ? gc.story : null,
          source: gc.type || "",
          corners: gc.corners,
          lineage: gc.lineage || [],
        });
        groups.extGaps.add(mesh);
      }
      groups.extGaps.add(createEdgeLoop(gc.corners, palette.edge));
    }
  }

  // Full model: neutral structure + accented openings for readability
  const SHOW_FULL_MODEL_EDGES = false;
  const FULL_EDGE_OPACITY = 0.18;
  const fullPalette = {
    structure: { fill: 0xf3f1ee, edge: 0xa1a1aa, opacity: 1.0, roughness: 0.9, metalness: 0.0 },
    floor:     { fill: 0xc8c2b7, edge: 0x9f978a, opacity: 1.0, roughness: 0.55, metalness: 0.0 },
    ceiling:   { fill: 0xd8d2c7, edge: 0xafa89b, opacity: 1.0, roughness: 0.6, metalness: 0.0 },
    // Inspired by pascalorg/editor material presets: wood + glass
    door:      { fill: 0xc49a6c, edge: 0x8a5f3a, opacity: 0.96, roughness: 0.72, metalness: 0.0 },
    window:    { fill: 0x87ceeb, edge: 0xe6f6ff, opacity: 0.28, roughness: 0.08, metalness: 0.12 },
    // Opening shown as "void-like" cut marker (dark fill, bright edge)
    opening:   { fill: 0x0a0e1b, edge: 0xfafafa, opacity: 0.92, roughness: 0.6, metalness: 0.0 },
    // Roof surfaces — light blue, semi-transparent
    roof:      { fill: 0x88aacc, edge: 0x6688aa, opacity: 0.3, roughness: 0.5, metalness: 0.0 },
    // Dormer cheeks/headers — tinted to stand out from plain walls
    dormer:    { fill: 0xcc8844, edge: 0x996633, opacity: 0.85, roughness: 0.7, metalness: 0.0 },
  };
  const fullMaterials = {
    structure: new THREE.MeshStandardMaterial({
      color: fullPalette.structure.fill, opacity: fullPalette.structure.opacity, transparent: false,
      side: THREE.DoubleSide, depthWrite: true, roughness: fullPalette.structure.roughness, metalness: fullPalette.structure.metalness,
      flatShading: false,
    }),
    floor: new THREE.MeshStandardMaterial({
      color: fullPalette.floor.fill, opacity: fullPalette.floor.opacity, transparent: false,
      side: THREE.DoubleSide, depthWrite: true, roughness: fullPalette.floor.roughness, metalness: fullPalette.floor.metalness,
      emissive: 0x16120c, emissiveIntensity: 0.03,
    }),
    ceiling: new THREE.MeshStandardMaterial({
      color: fullPalette.ceiling.fill, opacity: fullPalette.ceiling.opacity, transparent: false,
      side: THREE.DoubleSide, depthWrite: true, roughness: fullPalette.ceiling.roughness, metalness: fullPalette.ceiling.metalness,
    }),
    door: new THREE.MeshStandardMaterial({
      color: fullPalette.door.fill, opacity: fullPalette.door.opacity, transparent: true,
      side: THREE.DoubleSide, depthWrite: false, roughness: fullPalette.door.roughness, metalness: fullPalette.door.metalness,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    }),
    window: new THREE.MeshStandardMaterial({
      color: fullPalette.window.fill, opacity: fullPalette.window.opacity, transparent: true,
      side: THREE.DoubleSide, depthWrite: false, roughness: fullPalette.window.roughness, metalness: fullPalette.window.metalness,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    }),
    opening: new THREE.MeshStandardMaterial({
      color: fullPalette.opening.fill, opacity: fullPalette.opening.opacity, transparent: true,
      side: THREE.DoubleSide, depthWrite: false, roughness: fullPalette.opening.roughness, metalness: fullPalette.opening.metalness,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    }),
    roof: new THREE.MeshStandardMaterial({
      color: fullPalette.roof.fill, opacity: fullPalette.roof.opacity, transparent: true,
      side: THREE.DoubleSide, depthWrite: false, roughness: fullPalette.roof.roughness, metalness: fullPalette.roof.metalness,
    }),
    dormer: new THREE.MeshStandardMaterial({
      color: fullPalette.dormer.fill, opacity: fullPalette.dormer.opacity, transparent: true,
      side: THREE.DoubleSide, depthWrite: false, roughness: fullPalette.dormer.roughness, metalness: fullPalette.dormer.metalness,
    }),
    frame: new THREE.MeshStandardMaterial({
      color: '#f2f0ed', opacity: 1, transparent: false,
      side: THREE.DoubleSide, depthWrite: true, roughness: 0.5, metalness: 0,
    }),
    frameDark: new THREE.MeshStandardMaterial({
      color: '#8a5f3a', opacity: 1, transparent: false,
      side: THREE.DoubleSide, depthWrite: true, roughness: 0.65, metalness: 0,
    }),
    doorLeaf: new THREE.MeshStandardMaterial({
      color: '#c8a27a', opacity: 1, transparent: false,
      side: THREE.DoubleSide, depthWrite: true, roughness: 0.7, metalness: 0,
    }),
    doorPanel: new THREE.MeshStandardMaterial({
      color: '#b88e65', opacity: 1, transparent: false,
      side: THREE.DoubleSide, depthWrite: true, roughness: 0.72, metalness: 0,
    }),
    handleMetal: new THREE.MeshStandardMaterial({
      color: '#c0c0c0', opacity: 1, transparent: false,
      side: THREE.DoubleSide, depthWrite: true, roughness: 0.3, metalness: 0.9,
    }),
  };
  function addOrientedBox(group, basis, cx, cy, cz, sx, sy, sz, material, renderOrder = 3, castShadow = true, receiveShadow = true, locator = null) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), material);
    const rot = new THREE.Matrix4().makeBasis(basis.u, basis.v, basis.n);
    mesh.quaternion.setFromRotationMatrix(rot);
    mesh.position.copy(basis.origin)
      .addScaledVector(basis.u, cx)
      .addScaledVector(basis.v, cy)
      .addScaledVector(basis.n, cz);
    mesh.renderOrder = renderOrder;
    mesh.castShadow = castShadow && material !== fullMaterials.window;
    mesh.receiveShadow = receiveShadow;
    if (locator) attachLocator(mesh, locator);
    group.add(mesh);
  }

  function openingBounds(corners, basis) {
    const pts = corners.map(p => projectToPlane2(new THREE.Vector3(...p), basis));
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of pts) {
      minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
    }
    return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY };
  }

  function addWindowModel(corners, locator) {
    const basis = polygonPlaneBasis(corners);
    if (!basis) return;
    const b = openingBounds(corners, basis);
    if (b.width < 0.05 || b.height < 0.05) return;
    const frameT = Math.max(0.03, Math.min(0.08, Math.min(b.width, b.height) * 0.1));
    const depth = 0.07;
    const glassDepth = 0.012;
    const cx = (b.minX + b.maxX) * 0.5;
    const cy = (b.minY + b.maxY) * 0.5;

    // Outer frame — first piece gets the locator so right-click picks up the window
    addOrientedBox(groups.fullModel, basis, cx, b.maxY - frameT * 0.5, 0, b.width, frameT, depth, fullMaterials.frame, 4, true, false, locator);
    addOrientedBox(groups.fullModel, basis, cx, b.minY + frameT * 0.5, 0, b.width, frameT, depth, fullMaterials.frame, 4, true, false);
    addOrientedBox(groups.fullModel, basis, b.minX + frameT * 0.5, cy, 0, frameT, b.height - 2 * frameT, depth, fullMaterials.frame, 4, true, false);
    addOrientedBox(groups.fullModel, basis, b.maxX - frameT * 0.5, cy, 0, frameT, b.height - 2 * frameT, depth, fullMaterials.frame, 4, true, false);

    // Vertical mullion
    const innerW = Math.max(0.02, b.width - 2 * frameT);
    const innerH = Math.max(0.02, b.height - 2 * frameT);
    const mullionW = Math.max(0.015, frameT * 0.7);
    addOrientedBox(groups.fullModel, basis, cx, cy, 0, mullionW, innerH, depth * 0.96, fullMaterials.frame, 5, true, false);

    // Glass panes — also attach locator so clicking glass works
    const paneW = Math.max(0.01, (innerW - mullionW) * 0.5);
    addOrientedBox(groups.fullModel, basis, cx - (mullionW + paneW) * 0.5, cy, 0, paneW, innerH, glassDepth, fullMaterials.window, 6, false, false, locator);
    addOrientedBox(groups.fullModel, basis, cx + (mullionW + paneW) * 0.5, cy, 0, paneW, innerH, glassDepth, fullMaterials.window, 6, false, false, locator);
  }

  function addDoorModel(corners, locator) {
    const basis = polygonPlaneBasis(corners);
    if (!basis) return;
    const b = openingBounds(corners, basis);
    if (b.width < 0.05 || b.height < 0.05) return;
    const frameT = Math.max(0.035, Math.min(0.09, Math.min(b.width, b.height) * 0.11));
    const depth = 0.08;
    const leafDepth = 0.04;
    const cx = (b.minX + b.maxX) * 0.5;

    // Frame: sides + head (Pascal-like door frame)
    addOrientedBox(groups.fullModel, basis, b.minX + frameT * 0.5, (b.minY + b.maxY) * 0.5, 0, frameT, b.height, depth, fullMaterials.frame, 4, true, false, locator);
    addOrientedBox(groups.fullModel, basis, b.maxX - frameT * 0.5, (b.minY + b.maxY) * 0.5, 0, frameT, b.height, depth, fullMaterials.frame, 4, true, false);
    addOrientedBox(groups.fullModel, basis, cx, b.maxY - frameT * 0.5, 0, b.width, frameT, depth, fullMaterials.frame, 4, true, false);

    // Leaf fills opening below top frame — attach locator since it's the biggest clickable surface
    const leafW = Math.max(0.02, b.width - 2 * frameT);
    const leafH = Math.max(0.02, b.height - frameT);
    const leafCy = b.minY + leafH * 0.5;
    addOrientedBox(groups.fullModel, basis, cx, leafCy, 0, leafW, leafH, leafDepth, fullMaterials.doorLeaf, 5, true, false, locator);

    // Inset panel
    const insetX = Math.max(0.02, leafW * 0.12);
    const insetY = Math.max(0.02, leafH * 0.12);
    addOrientedBox(groups.fullModel, basis, cx, leafCy, leafDepth * 0.38, leafW - 2 * insetX, leafH - 2 * insetY, 0.01, fullMaterials.doorPanel, 6, false, false);

    // Handle (right side)
    const hx = b.maxX - frameT - leafW * 0.08;
    const hy = b.minY + leafH * 0.55;
    addOrientedBox(groups.fullModel, basis, hx, hy, leafDepth * 0.62, 0.02, 0.10, 0.03, fullMaterials.handleMetal, 7, false, false);
  }

  function addOpeningModel(corners) {
    const basis = polygonPlaneBasis(corners);
    if (!basis) return;
    const b = openingBounds(corners, basis);
    if (b.width < 0.03 || b.height < 0.03) return;
    // Thin slab slightly in front of the wall plane to avoid coplanar jitter.
    addOrientedBox(
      groups.fullModel,
      basis,
      (b.minX + b.maxX) * 0.5,
      (b.minY + b.maxY) * 0.5,
      0.03,
      b.width,
      b.height,
      0.02,
      fullMaterials.opening,
      6
    );
  }

  const fullMeshRenderProps = {
    structure: { renderOrder: 1, castShadow: true, receiveShadow: true },
    floor:     { renderOrder: 0, castShadow: true, receiveShadow: true },
    ceiling:   { renderOrder: 0, castShadow: false, receiveShadow: true },
  };

  function addFullMesh(corners, kind = 'structure', holes = [], locator = null, targetGroup = groups.fullModel) {
    if (!corners || corners.length < 3) return;
    if (kind === 'door') { addDoorModel(corners, locator); return; }
    if (kind === 'window') { addWindowModel(corners, locator); return; }
    if (kind === 'opening') { return; }
    if (kind === 'structure') {
      corners = orientedStructureCorners(corners, [cx, cy, cz]);
    }
    const palette = fullPalette[kind] || fullPalette.structure;
    const mat = fullMaterials[kind] || fullMaterials.structure;
    const mesh = createPolygonMesh(corners, palette.fill, palette.opacity, holes);
    if (mesh) {
      mesh.material = mat;
      const props = fullMeshRenderProps[kind] || { renderOrder: 3, castShadow: false, receiveShadow: false };
      mesh.renderOrder = props.renderOrder;
      mesh.castShadow = props.castShadow;
      mesh.receiveShadow = props.receiveShadow;
      if (locator) attachLocator(mesh, locator);
      targetGroup.add(mesh);
    }
    // Keep structural/floor edges off for a clean mass.
    const showKindEdge = SHOW_FULL_MODEL_EDGES || (kind !== 'structure' && kind !== 'floor' && kind !== 'ceiling');
    if (showKindEdge) {
      const edgeOpacity = kind === 'structure' ? FULL_EDGE_OPACITY : 0.55;
      targetGroup.add(createEdgeLoop(corners, palette.edge, edgeOpacity));
    }

  }
  // a) Computed walls + extension strips
  bldg.rooms.forEach((room, ri) => {
    const story = room.story || 0;
    const roomId = `${story}:${ri}`;
    // Physical rule for final model:
    // only windows create light-through wall holes.
    const openingsForCutout = [
      ...(room.windows || []).map(w => ({ corners: w.corners })),
    ];
    for (const w of room.walls_computed) {
      const loc = {
        buildingUuid: bldg.uuid, kind: 'wall-computed',
        id: `${w.id || 'wall'}:${story}:${ri}`, roomId, story, corners: w.corners,
      };
      const holes = collectWallCutoutHoles(w.corners, openingsForCutout);
      addFullMesh(w.corners, 'structure', holes, loc);
      // Extension strips as continuation (same color = no seam)
      if (w.extension_strip && w.extension_strip.length > 0) {
        const strips = Array.isArray(w.extension_strip[0]?.[0]) ? w.extension_strip : [w.extension_strip];
        for (const quad of strips) {
          addFullMesh(quad, 'structure', [], {
            buildingUuid: bldg.uuid, kind: 'wall-extension',
            id: `${w.id || 'wall'}:${story}:${ri}`, roomId, story, corners: quad,
          });
        }
      }
    }
  });
  // b) Gap walls (including gap floor/ceiling quads)
  for (let gi = 0; gi < (bldg.gap_walls || []).length; gi++) {
    const gw = bldg.gap_walls[gi];
    const kind = gw.type === 'gap_floor' ? 'floor' : gw.type === 'gap_ceiling' ? 'ceiling' : 'structure';
    addFullMesh(gw.corners, kind, [], {
      buildingUuid: bldg.uuid, kind: 'gap-wall', id: String(gw.id || `gw:${gi}`), corners: gw.corners,
    });
  }
  // b2) Floors (included in final full model)
  bldg.rooms.forEach((room, ri) => {
    const story = room.story || 0;
    if (room.floor_polygon && room.floor_polygon.length >= 3) {
      addFullMesh(room.floor_polygon, 'floor', [], {
        buildingUuid: bldg.uuid, kind: 'floor', id: `${story}:${ri}`, corners: room.floor_polygon,
      });
    }
  });
  // c) Gap closures (side/floor/ceiling quads filling exterior gaps)
  for (let ci = 0; ci < (bldg.gap_closures || []).length; ci++) {
    const gc = bldg.gap_closures[ci];
    const kind = gc.type === 'floor' ? 'floor' : gc.type === 'ceiling' ? 'ceiling' : 'structure';
    addFullMesh(gc.corners, kind, [], {
      buildingUuid: bldg.uuid, kind: 'gap-closure', id: String(gc.id || `gc:${ci}`), corners: gc.corners,
    });
  }
  // d) Stitch walls
  for (let si = 0; si < (bldg.stitch_walls || []).length; si++) {
    const sw = bldg.stitch_walls[si];
    addFullMesh(sw.corners, 'structure', [], {
      buildingUuid: bldg.uuid, kind: 'wall-stitch', id: String(sw.id || `sw:${si}`), corners: sw.corners,
    });
  }
  // d2) Dormer cheeks and headers — added individually (not merged) so locators work
  for (let di = 0; di < (bldg.dormers || []).length; di++) {
    const d = bldg.dormers[di];
    for (let ci = 0; ci < (d.cheeks || []).length; ci++) {
      const cheek = d.cheeks[ci];
      if (!cheek?.corners || cheek.corners.length < 3 || cheek.source === 'existing') continue;
      const mesh = createPolygonMesh(cheek.corners, fullPalette.dormer.fill, fullPalette.dormer.opacity);
      if (mesh) {
        mesh.material = fullMaterials.dormer.clone();
        mesh.renderOrder = 3;
        mesh.castShadow = false;
        attachLocator(mesh, {
          buildingUuid: bldg.uuid,
          kind: 'dormer-cheek',
          id: `dormer-cheek:${di}:${ci}`,
          corners: cheek.corners,
        });
        groups.fullModel.add(mesh);
      }
    }
    if (d.header && d.header.corners && d.header.corners.length >= 3 && d.header.source !== 'existing') {
      const mesh = createPolygonMesh(d.header.corners, fullPalette.dormer.fill, fullPalette.dormer.opacity);
      if (mesh) {
        mesh.material = fullMaterials.dormer.clone();
        mesh.renderOrder = 3;
        attachLocator(mesh, {
          buildingUuid: bldg.uuid,
          kind: 'dormer-header',
          id: `dormer-header:${di}`,
          corners: d.header.corners,
        });
        groups.fullModel.add(mesh);
      }
    }
  }
  // d3) Oblique roof surfaces (with dormer cutout holes)
  const obliqueRoofSurfaces = bldg?.roof_surfaces?.oblique || [];
  for (let ri = 0; ri < obliqueRoofSurfaces.length; ri++) {
    const s = obliqueRoofSurfaces[ri];
    if (!s.corners || s.corners.length < 3) continue;
    const holes = Array.isArray(s.cutout_holes) ? s.cutout_holes : [];
    addFullMesh(s.corners, 'roof', holes, {
      buildingUuid: bldg.uuid, kind: 'roof-oblique', id: `oblique:${ri}`, corners: s.corners,
    }, groups.fullModelHeuristicRoof);
  }
  // (Structure/floor/ceiling meshes are added individually in addFullMesh for right-click locators.)
  // e) Openings + windows/doors so final stage includes all cutout geometry context
  bldg.rooms.forEach((room, ri) => {
    const story = room.story || 0;
    const roomId = `${story}:${ri}`;
    for (const d of (room.doors || [])) {
      addFullMesh(d.corners, 'door', [], {
        buildingUuid: bldg.uuid, kind: 'door', id: String(d.id || ''),
        roomId, story, corners: d.corners,
      });
    }
    for (const w of (room.windows || [])) {
      addFullMesh(w.corners, 'window', [], {
        buildingUuid: bldg.uuid, kind: 'window', id: String(w.id || ''),
        roomId, story, corners: w.corners,
      });
    }
  });
  // Exterior indicators are diagnostic; skip in final model to avoid overlap/jitter with doors.

  // Legend
  renderLegend();

  // Info
  const computedCount = bldg.rooms.reduce((s, r) => s + r.walls_computed.length, 0);
  const mergedCount = bldg.rooms.reduce((s, r) => s + r.walls_merged.length, 0);
  const doorCount = bldg.rooms.reduce((s, r) => s + (r.doors || []).length, 0);
  const windowCount = bldg.rooms.reduce((s, r) => s + (r.windows || []).length, 0);
  const addr = bldg.address || bldg.uuid;
  const gapHigh = gapList.filter(g => g.confidence === 'high').length;
  const gapMed = gapList.filter(g => g.confidence === 'medium').length;
  const gapInfo = gapList.length > 0 ? ` &middot; gaps: ${gapHigh}h/${gapMed}m/${gapList.length - gapHigh - gapMed}l` : '';
  const extCount = bldg.rooms.reduce((s, r) => s + r.walls_computed.filter(w => w.extension_strip).length, 0);
  const extInfo = extCount > 0 ? ` &middot; ${extCount} extended` : '';
  const om = bldg.overlap_metrics || {};
  const overlapInfo = om.floor_overlap_count > 0 ? ` &middot; <span style="color:#f44">${om.floor_overlap_count} overlaps (${om.total_floor_overlap_area_m2}m&sup2;)</span>` : '';
  const wallClipInfo = om.walls_clipped > 0 ? ` &middot; <span style="color:#f66">${om.walls_clipped} wall clips</span>` : '';
  const extGapInfo = extGapList.length > 0 ? ` &middot; <span style="color:#f4f">${extGapList.length} ext.gaps</span>` : '';
  const openingsInfo = (doorCount + windowCount) > 0 ? ` &middot; <span style="color:#c73">${doorCount}d</span> <span style="color:#3ad">${windowCount}w</span>` : '';
  // Source breakdown for computed walls
  const srcCounts = {};
  bldg.rooms.forEach(r => r.walls_computed.forEach(w => { srcCounts[w.source] = (srcCounts[w.source] || 0) + 1; }));
  const srcInfo = Object.entries(srcCounts).map(([k, v]) => `${v} ${k}`).join(', ');
  buildingInfoBaseHtml =
    `${addr} &middot; ${bldg.rooms.length} rooms &middot; ` +
    `${bldg.stories_found} stories &middot; ${computedCount} computed / ${mergedCount} merged walls${openingsInfo}${gapInfo}${extInfo}${overlapInfo}${wallClipInfo}${extGapInfo}` +
    `<br><span style="color:#555">Sources: ${srcInfo}</span>` +
    `<br><span style="color:#888">Right-click any element to copy its shareable ID</span>`;
  document.getElementById('building-info').innerHTML = buildingInfoBaseHtml;
  updateOntologyStatusInfo();

  // Camera
  let maxDist = 5;
  for (const p of allCorners) {
    const d = Math.hypot(p[0]-cx, p[1]-cy, p[2]-cz);
    if (d > maxDist) maxDist = d;
  }
  const cd = maxDist * 1.8;
  camera.position.set(cx + cd*0.7, cy + cd*0.9, cz + cd*0.7);
  controls.target.set(cx, cy, cz);
  controls.update();

  // Highlight sidebar (only scroll for keyboard nav, not clicks)
  document.querySelectorAll('.bldg-item').forEach(el => {
    el.classList.toggle('active', Number(el.dataset.index) === index);
  });
  document.title = `${addr} - 3D Viewer`;
  updateOrthoPanelForBuilding(bldg);

  if (resetPipeline) {
    applyPipelineStep(0);
  } else {
    applyPipelineStep(pipelineStepIndex);
  }
}

bindUIEventHandlers({
  documentRef: document,
  LAYER_CONTROL_IDS,
  LAYER_KEYS,
  groups,
  getData: () => DATA,
  getCurrentBuilding: () => currentBuilding,
  getPipelineStepIndex: () => pipelineStepIndex,
  applyPipelineStep,
  setLayerVisibility,
  onLayerVisibilityChanged: (layer, visible) => {
    if (layer === 'ontologySemantics' || layer === 'ontologyContinuation' || layer === 'ontologyCells' || layer === 'fullModel') {
      const bldg = DATA[currentBuilding];
      if (bldg && layer === 'ontologyCells' && !visible) {
        const loadState = getOntologyLoadState(bldg.uuid);
        loadState.streamToken += 1;
        loadState.streaming = false;
      }
      if (bldg) {
        if (layer === 'ontologySemantics') renderOntologySemanticsForBuilding(bldg);
        if (layer === 'ontologyContinuation') renderOntologyContinuationForBuilding(bldg);
        if (layer === 'ontologyCells') renderOntologyExactForBuilding(bldg);
        if (layer === 'fullModel') renderFullModelOntologyForBuilding(bldg);
      }
      if (visible) maybeLoadOntologyForCurrentBuilding();
      else updateOntologyStatusInfo();
    }
  },
  renderLegend,
  loadBuilding,
  setColorByStory: (v) => { colorByStory = v; },
  setColorBySource: (v) => { colorBySource = v; },
  setOrthoEnabled: (v) => { orthoEnabled = v; },
  updateOrthoPanelForBuilding,
  getOrthoMap,
  setModelMapEnabled: (v) => { modelMapEnabled = v; },
  setModelMapRotationDeg: (v) => { modelMapRotationDeg = v; },
  setModelMapOffsetEastM: (v) => { modelMapOffsetEastM = v; },
  setModelMapOffsetNorthM: (v) => { modelMapOffsetNorthM = v; },
  getModelMapRotationDeg: () => modelMapRotationDeg,
  getModelMapOffsetEastM: () => modelMapOffsetEastM,
  getModelMapOffsetNorthM: () => modelMapOffsetNorthM,
  applyAlignmentStateToControls,
  updateModelMapOverlay,
  queueSaveAlignmentForCurrentBuilding,
  normalizeDeg,
  setMapStatus,
  setAnchorModeEnabled: (v) => { anchorModeEnabled = v; },
  getAnchorModeEnabled: () => anchorModeEnabled,
});

document.getElementById('show-full-model-diff')?.addEventListener('change', (event) => {
  fullModelDiffModeEnabled = !!event.target?.checked;
  const bldg = DATA[currentBuilding];
  if (bldg && document.getElementById('show-full-model')?.checked) {
    renderFullModelOntologyForBuilding(bldg);
  }
  renderLegend();
  updateOntologyStatusInfo();
});

canvas.addEventListener("contextmenu", async (event) => {
  event.preventDefault();
  if (!DATA[currentBuilding]) return;

  const rect = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);

  const intersections = raycaster.intersectObjects(getVisiblePickRoots(), true);
  const hit = intersections.find((it) => it.object?.userData?.elementUid);
  if (!hit) {
    setMapStatus("Right-click a rendered element to copy a shareable ID");
    hideLineagePanel();
    return;
  }

  const uid = hit.object.userData.elementUid;
  const ok = await copyText(uid);
  if (!ok) {
    setMapStatus(`Element ID: ${uid}`);
    return;
  }

  const selected = jumpToElementUid(uid, { focus: false, updateHash: true });
  if (selected) {
    setMapStatus(`Copied element ID: ${uid}`);
  } else {
    setMapStatus(`Copied: ${uid}`);
  }
});

canvas.addEventListener("click", (event) => {
  if (!DATA[currentBuilding]) return;
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const intersections = raycaster.intersectObjects(getVisiblePickRoots(), true);
  const hit = intersections.find((it) => it.object?.userData?.elementUid);
  if (!hit) return;
  const uid = hit.object.userData.elementUid;
  const locator = hit.object.userData?.elementLocator || null;
  jumpToElementUid(uid, { focus: false, updateHash: true });
  const partId = ontologyPartIdFromLocator(locator);
  if (partId) {
    const uuid = locator?.buildingUuid || DATA[currentBuilding]?.uuid;
    if (uuid) setSelectedOntologyPart(uuid, partId, { announce: true });
  }
});

document.getElementById("search").addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  const uid = String(event.target?.value || "").trim();
  if (!uid.includes("::")) return;
  if (jumpToElementUid(uid)) {
    event.preventDefault();
    setMapStatus("Jumped to shared element ID");
  } else {
    setMapStatus("Could not resolve that element ID");
  }
});

window.addEventListener('resize', resizeRenderer);

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

renderPipelineStatus();
renderLegend();

fetch(`roof_algorithms_py_results.json?v=${Date.now()}`, { cache: 'no-store' })
  .then(r => (r.ok ? r.json() : {}))
  .then(data => {
    pyRoofByUuid = (data && typeof data === 'object') ? data : {};
    if (DATA.length > 0) {
      loadBuilding(currentBuilding, { resetPipeline: false });
    }
  })
  .catch(() => {
    pyRoofByUuid = {};
  });

fetch(`buildings_3d.json?v=${Date.now()}`, { cache: 'no-store' })
  .then(r => r.json())
  .then(data => {
    return fetch('/alignment-calibration')
      .then(r => (r.ok ? r.json() : {}))
      .catch(() => ({}))
      .then(calib => {
        alignmentByUuid = (calib && typeof calib === 'object') ? calib : {};
        return data;
      });
  })
  .then(data => {
    DATA = data;
    buildingIndexByUuid = new Map();
    data.forEach((b, i) => {
      if (b?.uuid) buildingIndexByUuid.set(b.uuid, i);
    });

    // Sort by address
    const indices = data.map((b, i) => i);
    indices.sort((a, b) => (data[a].address || '').localeCompare(data[b].address || ''));

    const list = document.getElementById('building-list');
    for (const i of indices) {
      const b = data[i];
      const el = document.createElement('div');
      el.className = 'bldg-item';
      const addr = b.address || b.uuid.slice(0, 12);
      const computedCount = b.rooms.reduce((s, r) => s + r.walls_computed.length, 0);
      const doorCount = b.rooms.reduce((s, r) => s + (r.doors || []).length, 0);
      const windowCount = b.rooms.reduce((s, r) => s + (r.windows || []).length, 0);
      const cls = b.classification || 'UNKNOWN';
      const storiesClass = b.stories_found > 1 ? 'multi' : '';
      const gapCount = (b.cross_floor_gaps || []).length;
      const gapBadge = gapCount > 0 ? `<span style="color:#f84">${gapCount}gaps</span>` : '';
      const extGapCount = (b.exterior_gap_indicators || []).length;
      const extGapBadge = extGapCount > 0 ? `<span style="color:#f4f">${extGapCount}eg</span>` : '';
      el.innerHTML =
        `<div class="bldg-addr">${addr}</div>` +
        `<div class="bldg-meta">` +
          `<span class="tag tag-${cls}">${cls}</span>` +
          `<span class="stories-badge ${storiesClass}">${b.stories_found}F</span>` +
          `<span>${b.rooms.length}r</span>` +
          `<span>${computedCount}w</span>` +
          `<span style="color:#c73">${doorCount}d</span>` +
          `<span style="color:#3ad">${windowCount}w</span>` +
          gapBadge +
          extGapBadge +
        `</div>`;
      el.dataset.search = `${addr} ${b.uuid} ${cls}`.toLowerCase();
      el.dataset.index = i;
      el.addEventListener('click', () => {
        document.querySelectorAll('.bldg-item').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        requestAnimationFrame(() => loadBuilding(i));
      });
      list.appendChild(el);
    }

    document.getElementById('sidebar-stats').textContent = `${data.length} buildings`;
    resizeRenderer();
    if (pendingElementUid) {
      const parsed = parseElementUid(pendingElementUid);
      if (parsed && buildingIndexByUuid.has(parsed.buildingUuid)) {
        const idx = buildingIndexByUuid.get(parsed.buildingUuid);
        const b = data[idx];
        applyAlignmentStateToControls(alignmentByUuid[b.uuid] || {});
        try {
          loadBuilding(idx);
        } catch (err) {
          console.error('Initial building load failed', b?.uuid, err);
          document.getElementById('building-info').textContent = `Initial building load failed for ${b?.uuid || 'unknown building'}`;
        }
        jumpToElementUid(pendingElementUid, { focus: true, updateHash: false });
      } else if (indices.length > 0) {
        const b = data[indices[0]];
        applyAlignmentStateToControls(alignmentByUuid[b.uuid] || {});
        try {
          loadBuilding(indices[0]);
        } catch (err) {
          console.error('Initial building load failed', b?.uuid, err);
          document.getElementById('building-info').textContent = `Initial building load failed for ${b?.uuid || 'unknown building'}`;
        }
      }
      pendingElementUid = null;
      pendingBuildingUuid = null;
    } else if (pendingBuildingUuid && buildingIndexByUuid.has(pendingBuildingUuid)) {
      const idx = buildingIndexByUuid.get(pendingBuildingUuid);
      const b = data[idx];
      applyAlignmentStateToControls(alignmentByUuid[b.uuid] || {});
      try {
        loadBuilding(idx);
      } catch (err) {
        console.error('Initial building load failed', b?.uuid, err);
        document.getElementById('building-info').textContent = `Initial building load failed for ${b?.uuid || 'unknown building'}`;
      }
      pendingBuildingUuid = null;
    } else if (indices.length > 0) {
      const b = data[indices[0]];
      applyAlignmentStateToControls(alignmentByUuid[b.uuid] || {});
      try {
        loadBuilding(indices[0]);
      } catch (err) {
        console.error('Initial building load failed', b?.uuid, err);
        document.getElementById('building-info').textContent = `Initial building load failed for ${b?.uuid || 'unknown building'}`;
      }
    }
    animate();
  })
  .catch(err => {
    console.error('Failed to load buildings_3d.json', err);
    document.getElementById('sidebar-stats').textContent = 'Failed to load buildings';
    document.getElementById('building-info').textContent = 'Could not load buildings_3d.json';
  });
