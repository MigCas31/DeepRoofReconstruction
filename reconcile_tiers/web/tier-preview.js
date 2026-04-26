import * as THREE from "three";
import { mergeGeometries, mergeVertices, toCreasedNormals } from "three/addons/utils/BufferGeometryUtils.js";

import { newellNormal, signedArea2 } from "./geometry.js";
import { attachLocator } from "./locator.js";
import { gapMaterial, MATERIAL_PALETTE } from "./material-palette.js";
import { RENDER_TUNING } from "./render-tuning.js";

const OUTLINE_NAMES = new Set(["roof", "doorLeaf", "dormer"]);
const CREASE_ANGLE_RAD = THREE.MathUtils.degToRad(RENDER_TUNING.creaseAngleDeg);
const EDGE_THRESHOLD_DEG = RENDER_TUNING.edgeThresholdDeg;

const OUTLINE_MATERIAL = new THREE.LineBasicMaterial({
  color: 0x2a2a2a,
  transparent: true,
  opacity: 0.35,
  depthTest: true,
  depthWrite: false,
});
const PICK_MATERIAL = new THREE.MeshBasicMaterial({
  colorWrite: false,
  depthWrite: false,
  depthTest: false,
  side: THREE.DoubleSide,
});
const GROUND_MATERIAL = new THREE.MeshStandardMaterial({
  color: 0xfafafa,
  roughness: 1.0,
  metalness: 0,
  side: THREE.FrontSide,
  depthWrite: true,
  polygonOffset: true,
  polygonOffsetFactor: 1,
  polygonOffsetUnits: 1,
});

function makeMaterial(def) {
  const options = {
    color: def.fill,
    roughness: def.roughness,
    metalness: def.metalness,
    side: def.name === "window" ? THREE.DoubleSide : THREE.FrontSide,
    depthWrite: true,
  };
  if (def.name === "window") {
    options.transparent = true;
    options.opacity = 0.35;
    options.depthWrite = false;
  }
  return new THREE.MeshStandardMaterial(options);
}

const MATERIALS = Object.fromEntries(
  Object.entries(MATERIAL_PALETTE).map(([key, value]) => [key, makeMaterial(value)]),
);

function vec(c) {
  return new THREE.Vector3(c.x ?? c[0], c.y ?? c[1], c.z ?? c[2]);
}

function cornerArray(c) {
  return [c.x ?? c[0], c.y ?? c[1], c.z ?? c[2]];
}

function basis(corners) {
  const n0 = newellNormal(corners.map(cornerArray));
  const n = new THREE.Vector3(n0?.x ?? 0, n0?.y ?? 1, n0?.z ?? 0).normalize();
  let u = new THREE.Vector3(1, 0, 0);
  let best = 0;
  for (let i = 0; i < corners.length; i += 1) {
    const a = vec(corners[i]);
    const b = vec(corners[(i + 1) % corners.length]);
    const edge = b.sub(a);
    edge.addScaledVector(n, -edge.dot(n));
    const len = edge.lengthSq();
    if (len > best) {
      best = len;
      u = edge.clone().normalize();
    }
  }
  const v = new THREE.Vector3().crossVectors(n, u).normalize();
  const origin = vec(corners[0]);
  return { origin, u, v, n };
}

function to2(loop, frame) {
  return loop.map((corner) => {
    const p = vec(corner).sub(frame.origin);
    return new THREE.Vector2(p.dot(frame.u), p.dot(frame.v));
  });
}

function normalizeLoop(loop, points2, wantPositive) {
  const positive = signedArea2(points2) > 0;
  if (positive === wantPositive) return { loop, points2 };
  return { loop: [...loop].reverse(), points2: [...points2].reverse() };
}

function polygonArea3(corners) {
  let nx = 0;
  let ny = 0;
  let nz = 0;
  const arr = corners.map(cornerArray);
  for (let i = 0; i < arr.length; i += 1) {
    const a = arr[i];
    const b = arr[(i + 1) % arr.length];
    nx += (a[1] - b[1]) * (a[2] + b[2]);
    ny += (a[2] - b[2]) * (a[0] + b[0]);
    nz += (a[0] - b[0]) * (a[1] + b[1]);
  }
  return 0.5 * Math.hypot(nx, ny, nz);
}

function polygonGeometry(corners, holes = []) {
  if (!corners || corners.length < 3) return null;
  if (polygonArea3(corners) < RENDER_TUNING.minPolygonAreaM2) return null;
  const frame = basis(corners);
  let outer = normalizeLoop(corners, to2(corners, frame), true);
  const holeLoops = [];
  const holePoints = [];
  for (const hole of holes || []) {
    if (!hole || hole.length < 3) continue;
    const normalized = normalizeLoop(hole, to2(hole, frame), false);
    holeLoops.push(normalized.loop);
    holePoints.push(normalized.points2);
  }
  const triangles = THREE.ShapeUtils.triangulateShape(outer.points2, holePoints);
  if (!triangles.length) return null;
  const loops = [outer.loop, ...holeLoops];
  const vertices = loops.flat();
  const positions = new Float32Array(vertices.length * 3);
  vertices.forEach((corner, idx) => {
    const p = vec(corner);
    positions[idx * 3] = p.x;
    positions[idx * 3 + 1] = p.y;
    positions[idx * 3 + 2] = p.z;
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(triangles.flat());
  return geometry;
}

function addToAabb(aabb, corners) {
  for (const corner of corners || []) aabb.expandByPoint(vec(corner));
}

function addLocatorMesh(scene, geometry, uid, locatorMap) {
  if (!uid || !geometry) return;
  const pickGeometry = geometry.clone();
  const mesh = new THREE.Mesh(pickGeometry, PICK_MATERIAL);
  mesh.userData.tierPreview = true;
  mesh.userData.pickOnly = true;
  attachLocator(mesh, uid);
  locatorMap.set(uid, mesh);
  scene.add(mesh);
}

function addOutline(scene, geometry) {
  if (!geometry) return;
  const edges = new THREE.EdgesGeometry(geometry, EDGE_THRESHOLD_DEG);
  const line = new THREE.LineSegments(edges, OUTLINE_MATERIAL);
  line.userData.tierPreview = true;
  scene.add(line);
}

function batchGeometry(batches, material, geometry) {
  if (!geometry) return;
  const bucket = batches.get(material);
  if (bucket) bucket.push(geometry);
  else batches.set(material, [geometry]);
}

function addPolygon(scene, state, corners, material, uid, holes = [], materialName = "") {
  const geometry = polygonGeometry(corners, holes);
  if (!geometry) return;
  addToAabb(state.aabb, corners);
  batchGeometry(state.batches, material, geometry);
  addLocatorMesh(scene, geometry, uid, state.locatorMap);
  if (OUTLINE_NAMES.has(materialName)) {
    const outlineGeometry = geometry.clone();
    addOutline(scene, outlineGeometry);
  }
}

function weldTolerance(material) {
  if (material === MATERIALS.roof) return RENDER_TUNING.weldTol.roof;
  if (material === MATERIALS.structureFill) return RENDER_TUNING.weldTol.structureFill;
  return RENDER_TUNING.weldTol.default;
}

function flushBatches(scene, batches) {
  for (const [material, geometries] of batches) {
    if (!geometries.length) continue;
    let merged = null;
    try {
      merged = mergeGeometries(geometries, false);
    } catch (_err) {
      merged = null;
    }
    if (!merged) continue;
    let welded = merged;
    try {
      welded = mergeVertices(merged, weldTolerance(material));
    } catch (_err) {
      welded = merged;
    }
    const creased = toCreasedNormals(welded, CREASE_ANGLE_RAD);
    if (welded !== merged) welded.dispose();
    const mesh = new THREE.Mesh(creased, material);
    mesh.userData.tierPreview = true;
    mesh.castShadow = material !== MATERIALS.structureFill && material !== MATERIALS.window;
    mesh.receiveShadow = material !== MATERIALS.window;
    scene.add(mesh);
    if (material === MATERIALS.roof || material === MATERIALS.dormer) addOutline(scene, creased);
    for (const geometry of geometries) {
      if (geometry !== merged && geometry !== welded && geometry !== creased) geometry.dispose();
    }
    if (merged !== creased) merged.dispose();
  }
}

function openingBounds(corners, frame) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const corner of corners || []) {
    const p = vec(corner).sub(frame.origin);
    const x = p.dot(frame.u);
    const y = p.dot(frame.v);
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY };
}

function addOpeningBox(scene, state, quad, material, uid, materialName, depth) {
  if (!quad?.corners || quad.corners.length < 3) return;
  const frame = basis(quad.corners);
  const bounds = openingBounds(quad.corners, frame);
  if (bounds.width < RENDER_TUNING.opening.minDim || bounds.height < RENDER_TUNING.opening.minDim) return;
  addToAabb(state.aabb, quad.corners);
  const geometry = new THREE.BoxGeometry(bounds.width, bounds.height, depth);
  const matrix = new THREE.Matrix4().makeBasis(frame.u, frame.v, frame.n);
  const center = frame.origin.clone()
    .addScaledVector(frame.u, (bounds.minX + bounds.maxX) * 0.5)
    .addScaledVector(frame.v, (bounds.minY + bounds.maxY) * 0.5);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.quaternion.setFromRotationMatrix(matrix);
  mesh.position.copy(center);
  mesh.userData.tierPreview = true;
  mesh.castShadow = material !== MATERIALS.window;
  mesh.receiveShadow = material !== MATERIALS.window;
  scene.add(mesh);
  mesh.updateMatrixWorld(true);
  addLocatorMesh(scene, geometry.clone().applyMatrix4(mesh.matrixWorld), uid, state.locatorMap);
  if (materialName !== "window") addOutline(scene, geometry.clone().applyMatrix4(mesh.matrixWorld));
}

export function clearBuildingMeshes(scene) {
  const doomed = [];
  scene.traverse((obj) => {
    if (obj.userData?.tierPreview) doomed.push(obj);
  });
  for (const obj of doomed) {
    obj.removeFromParent();
    obj.geometry?.dispose?.();
    if (obj.userData?.disposeMaterialOnClear) obj.material?.dispose?.();
  }
  scene.userData.tierLocatorMap = new Map();
}

export function addPascalLighting(scene) {
  if (scene.userData.tierLighting) return;
  scene.add(new THREE.AmbientLight(0xffffff, RENDER_TUNING.light.ambient));
  const key = new THREE.DirectionalLight(0xffffff, RENDER_TUNING.light.key);
  key.position.set(10, 10, 10);
  key.castShadow = true;
  key.shadow.bias = RENDER_TUNING.shadow.bias;
  key.shadow.normalBias = RENDER_TUNING.shadow.normalBias;
  key.shadow.radius = RENDER_TUNING.shadow.radius;
  key.shadow.mapSize.set(RENDER_TUNING.shadow.mapSize, RENDER_TUNING.shadow.mapSize);
  if ("intensity" in key.shadow) key.shadow.intensity = 0.6;
  key.shadow.camera.near = 1;
  key.shadow.camera.far = 100;
  key.shadow.camera.left = -RENDER_TUNING.shadow.halfExtent;
  key.shadow.camera.right = RENDER_TUNING.shadow.halfExtent;
  key.shadow.camera.top = RENDER_TUNING.shadow.halfExtent;
  key.shadow.camera.bottom = -RENDER_TUNING.shadow.halfExtent;
  scene.add(key);
  const fill1 = new THREE.DirectionalLight(0xffffff, RENDER_TUNING.light.fill1);
  fill1.position.set(-10, 10, -10);
  scene.add(fill1);
  const fill2 = new THREE.DirectionalLight(0xffffff, RENDER_TUNING.light.fill2);
  fill2.position.set(-10, 10, 10);
  scene.add(fill2);
  scene.userData.tierLighting = true;
}

export function populateBuildingScene(scene, payload) {
  clearBuildingMeshes(scene);
  const state = {
    locatorMap: new Map(),
    batches: new Map(),
    aabb: new THREE.Box3(),
  };
  scene.userData.tierLocatorMap = state.locatorMap;
  state.aabb.makeEmpty();

  for (const room of payload.rooms || []) {
    addPolygon(scene, state, room.floor.corners, MATERIALS.floor, room.locator_id, [], "floor");
    for (const wall of room.walls || []) {
      addPolygon(
        scene,
        state,
        wall.corners,
        MATERIALS.structure,
        wall.locator_id,
        wall.cutouts?.map((quad) => quad.corners) ?? [],
        "structure",
      );
      if (wall.extension_strip) {
        addPolygon(scene, state, wall.extension_strip, MATERIALS.structure, `${wall.locator_id}:extension`, [], "structure");
      }
    }
    room.doors?.forEach((door, index) => {
      addOpeningBox(scene, state, door, MATERIALS.doorLeaf, `${room.locator_id}:door:${index}`, "doorLeaf", RENDER_TUNING.opening.doorDepth);
    });
    room.windows?.forEach((window, index) => {
      addOpeningBox(scene, state, window, MATERIALS.window, `${room.locator_id}:window:${index}`, "window", RENDER_TUNING.opening.glassDepth);
    });
  }

  for (const gap of payload.gaps || []) {
    const materialDef = gapMaterial(gap.kind);
    addPolygon(scene, state, gap.corners, MATERIALS[materialDef.name], gap.locator_id, [], materialDef.name);
  }
  for (const piece of payload.ceiling || []) {
    addPolygon(scene, state, piece.corners, MATERIALS.roof, piece.locator_id, piece.holes ?? [], "roof");
  }
  for (const wall of payload.knee_walls || []) {
    addPolygon(scene, state, wall.corners, MATERIALS.dormer, wall.locator_id, [], "dormer");
  }

  flushBatches(scene, state.batches);

  const center = state.aabb.isEmpty()
    ? new THREE.Vector3(payload.building_center?.x ?? 0, payload.building_center?.y ?? 0, payload.building_center?.z ?? 0)
    : state.aabb.getCenter(new THREE.Vector3());
  if (!state.aabb.isEmpty()) {
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(RENDER_TUNING.ground.size, RENDER_TUNING.ground.size),
      GROUND_MATERIAL,
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(center.x, state.aabb.min.y - RENDER_TUNING.ground.dropM, center.z);
    ground.receiveShadow = true;
    ground.castShadow = false;
    ground.userData.tierPreview = true;
    ground.userData.framingIgnore = true;
    scene.add(ground);
  }
  return { center, locatorMap: state.locatorMap };
}
