function addFace({
  corners,
  holes = [],
  color,
  opacity,
  group,
  createPolygonMesh,
  createEdgeLoop,
  attachLocator,
  locator,
  renderOrder = 5,
  edgeOpacity = null,
}) {
  if (!Array.isArray(corners) || corners.length < 3) return false;
  const mesh = createPolygonMesh(corners, color, opacity, holes);
  if (mesh) {
    mesh.renderOrder = renderOrder;
    mesh.material.depthTest = true;
    mesh.material.depthWrite = true;
    mesh.material.transparent = opacity < 0.999;
    if (attachLocator && locator) attachLocator(mesh, locator);
    group.add(mesh);
  }
  group.add(createEdgeLoop(corners, color, edgeOpacity ?? Math.min(opacity + 0.1, 0.95)));
  return true;
}

function surfaceStyle(surface) {
  const category = String(surface?.category || '');
  if (category === 'exterior_roof') return { color: 0x8eb8d6, opacity: 0.74, renderOrder: 6 };
  if (category === 'base_exterior_wall') return { color: 0xf3f1ee, opacity: 1.0, renderOrder: 5, edgeOpacity: 0.18 };
  if (category === 'base_interior_wall') return { color: 0xe6e1d8, opacity: 0.82, renderOrder: 4, edgeOpacity: 0.14 };
  if (category === 'base_room_floor') return { color: 0xc8c2b7, opacity: 1.0, renderOrder: 3, edgeOpacity: 0.18 };
  if (category === 'base_room_ceiling') return { color: 0xd8d3ca, opacity: 0.28, renderOrder: 2, edgeOpacity: 0.12 };
  if (category === 'fallback_room_ceiling') return { color: 0xf59e0b, opacity: 0.06, renderOrder: 2, edgeOpacity: 0.55 };
  if (category === 'base_window') return { color: 0x87ceeb, opacity: 0.28, renderOrder: 7, edgeOpacity: 0.72 };
  if (category === 'base_door') return { color: 0xc49a6c, opacity: 0.92, renderOrder: 7, edgeOpacity: 0.7 };
  if (category === 'base_opening') return { color: 0x0a0e1b, opacity: 0.82, renderOrder: 7, edgeOpacity: 0.82 };
  // Topology room faces are still emitted from the portable room-cell scaffold.
  // They are useful for debugging, but in the normal full-model view they read
  // as boxy placeholder geometry and obscure the roof-aware ontology output.
  if (category === 'exterior_wall') return null;
  if (category === 'occupied_room_wall') return null;
  if (category === 'occupied_room_floor') return null;
  if (category === 'occupied_room_ceiling') return null;
  if (category === 'room_ceiling_sloped') return { color: 0xb8c9d8, opacity: 0.82, renderOrder: 4 };
  if (category === 'attic_floor') return { color: 0xd5cbc0, opacity: 0.86, renderOrder: 4 };
  if (category === 'room_ceiling_flat') return { color: 0xc2d5e7, opacity: 0.78, renderOrder: 4 };
  if (category === 'knee_wall') return { color: 0xe3bf96, opacity: 0.84, renderOrder: 5 };
  if (category === 'unresolved_region') return { color: 0xf97316, opacity: 0.18, renderOrder: 7, edgeOpacity: 0.8 };
  return null;
}

function diffSurfaceStyle(surface) {
  const category = String(surface?.category || '');
  if (category === 'exterior_roof') return { color: 0x22d3ee, opacity: 0.82, renderOrder: 8, edgeOpacity: 0.95 };
  if (category === 'base_exterior_wall') return { color: 0x34d399, opacity: 0.48, renderOrder: 7, edgeOpacity: 0.9 };
  if (category === 'base_interior_wall') return { color: 0xf59e0b, opacity: 0.28, renderOrder: 6, edgeOpacity: 0.76 };
  if (category === 'base_room_floor') return { color: 0xfbbf24, opacity: 0.36, renderOrder: 6, edgeOpacity: 0.78 };
  if (category === 'base_room_ceiling') return { color: 0xfb7185, opacity: 0.26, renderOrder: 5, edgeOpacity: 0.72 };
  if (category === 'fallback_room_ceiling') return { color: 0xf59e0b, opacity: 0.12, renderOrder: 5, edgeOpacity: 0.95 };
  if (category === 'base_window') return { color: 0x38bdf8, opacity: 0.48, renderOrder: 8, edgeOpacity: 0.9 };
  if (category === 'base_door') return { color: 0xfb923c, opacity: 0.56, renderOrder: 8, edgeOpacity: 0.9 };
  if (category === 'base_opening') return { color: 0xffffff, opacity: 0.22, renderOrder: 8, edgeOpacity: 0.95 };
  if (category === 'exterior_wall') return { color: 0xa3e635, opacity: 0.42, renderOrder: 7, edgeOpacity: 0.9 };
  if (category === 'occupied_room_wall') return { color: 0xf472b6, opacity: 0.22, renderOrder: 6, edgeOpacity: 0.72 };
  if (category === 'occupied_room_floor') return { color: 0xfacc15, opacity: 0.28, renderOrder: 6, edgeOpacity: 0.72 };
  if (category === 'occupied_room_ceiling') return { color: 0xfb7185, opacity: 0.28, renderOrder: 6, edgeOpacity: 0.72 };
  if (category === 'room_ceiling_sloped') return { color: 0x38bdf8, opacity: 0.56, renderOrder: 7, edgeOpacity: 0.85 };
  if (category === 'attic_floor') return { color: 0xf59e0b, opacity: 0.52, renderOrder: 7, edgeOpacity: 0.85 };
  if (category === 'room_ceiling_flat') return { color: 0x818cf8, opacity: 0.48, renderOrder: 7, edgeOpacity: 0.85 };
  if (category === 'knee_wall') return { color: 0xef4444, opacity: 0.62, renderOrder: 8, edgeOpacity: 0.9 };
  if (category === 'unresolved_region') return { color: 0xf97316, opacity: 0.28, renderOrder: 9, edgeOpacity: 0.95 };
  return null;
}

function surfaceLocatorKind(surface) {
  const category = String(surface?.category || '');
  if (category === 'exterior_roof') return 'ontology-renderable-roof';
  if (category === 'base_exterior_wall') return 'ontology-base-exterior-wall';
  if (category === 'base_interior_wall') return 'ontology-base-interior-wall';
  if (category === 'base_room_floor') return 'ontology-base-floor';
  if (category === 'base_room_ceiling') return 'ontology-base-ceiling';
  if (category === 'fallback_room_ceiling') return 'ontology-fallback-ceiling';
  if (category === 'base_window') return 'ontology-base-window';
  if (category === 'base_door') return 'ontology-base-door';
  if (category === 'base_opening') return 'ontology-base-opening';
  if (category === 'exterior_wall') return 'ontology-renderable-wall';
  if (category === 'occupied_room_wall') return 'ontology-renderable-room-wall';
  if (category === 'occupied_room_floor') return 'ontology-renderable-floor';
  if (category === 'occupied_room_ceiling') return 'ontology-renderable-ceiling';
  if (category === 'knee_wall') return 'ontology-knee-wall';
  if (category === 'unresolved_region') return 'ontology-unresolved-coverage';
  return 'ontology-renderable-ceiling';
}

export function renderOntologyEnhancedFullModel({
  ontologySummary,
  ontologyParts,
  groups,
  createPolygonMesh,
  createEdgeLoop,
  attachLocator,
  buildingUuid,
  diffMode = false,
}) {
  const summarySurfaces = Array.isArray(ontologySummary?.renderable_surfaces) ? ontologySummary.renderable_surfaces : [];
  const partPayloads = Array.isArray(ontologyParts) ? ontologyParts : [];
  const partSurfaces = partPayloads.flatMap((payload) =>
    Array.isArray(payload?.renderable_surfaces) ? payload.renderable_surfaces : []
  );
  const surfaces = [...summarySurfaces, ...partSurfaces];

  const counts = {
    roofFaceCount: 0,
    baseWallCount: 0,
    baseFloorCount: 0,
    fenestrationCount: 0,
    exteriorWallCount: 0,
    occupiedSurfaceCount: 0,
    ceilingSurfaceCount: 0,
    fallbackCeilingCount: 0,
    kneeWallCount: 0,
    unresolvedCount: 0,
  };

  for (const surface of surfaces) {
    const style = diffMode ? diffSurfaceStyle(surface) : surfaceStyle(surface);
    if (!style) continue;
    const category = String(surface?.category || '');
    if (addFace({
      corners: surface?.corners,
      holes: Array.isArray(surface?.holes) ? surface.holes : [],
      color: style.color,
      opacity: style.opacity,
      group: groups.fullModelOntology,
      createPolygonMesh,
      createEdgeLoop,
      attachLocator,
      locator: {
        buildingUuid,
        kind: surfaceLocatorKind(surface),
        id: String(surface?.id || `${category}:${Math.random()}`),
        corners: surface?.corners,
        partId: surface?.part_id || null,
        roomId: surface?.room_id || null,
        role: surface?.role || null,
        category,
      },
      renderOrder: style.renderOrder,
      edgeOpacity: style.edgeOpacity ?? null,
    })) {
      if (category === 'exterior_roof') counts.roofFaceCount += 1;
      else if (category === 'base_exterior_wall' || category === 'base_interior_wall') counts.baseWallCount += 1;
      else if (category === 'base_room_floor') counts.baseFloorCount += 1;
      else if (category === 'base_room_ceiling') counts.ceilingSurfaceCount += 1;
      else if (category === 'fallback_room_ceiling') counts.fallbackCeilingCount += 1;
      else if (category === 'base_window' || category === 'base_door' || category === 'base_opening') counts.fenestrationCount += 1;
      else if (category === 'exterior_wall') counts.exteriorWallCount += 1;
      else if (category === 'knee_wall') counts.kneeWallCount += 1;
      else if (category === 'unresolved_region') counts.unresolvedCount += 1;
      else if (category.startsWith('occupied_room_')) counts.occupiedSurfaceCount += 1;
      else counts.ceilingSurfaceCount += 1;
    }
  }

  return {
    ...counts,
    hasEnhancement:
      counts.roofFaceCount > 0 ||
      counts.baseWallCount > 0 ||
      counts.baseFloorCount > 0 ||
      counts.fenestrationCount > 0 ||
      counts.exteriorWallCount > 0 ||
      counts.occupiedSurfaceCount > 0 ||
      counts.ceilingSurfaceCount > 0 ||
      counts.fallbackCeilingCount > 0 ||
      counts.kneeWallCount > 0 ||
      counts.unresolvedCount > 0,
    hasRoofReplacement: counts.roofFaceCount > 0,
    hasBaseShellReplacement: counts.baseWallCount > 0 || counts.baseFloorCount > 0,
  };
}
