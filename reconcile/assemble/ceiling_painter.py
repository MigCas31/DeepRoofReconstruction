from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon
from shapely.ops import unary_union

from reconcile._core.newell import newell_normal
from reconcile._core.plane import Plane
from reconcile._core.shapely2 import make_valid
from reconcile.payload.schema import CeilingPiece, CeilingSource, Vec3
from reconcile.payload.schema import Plane as PayloadPlane

PRIORITY = {
    CeilingSource.FLAT_EMIT: 100,
    CeilingSource.DORMER_CUTOUT: 90,
    CeilingSource.ROOF_ARRANGEMENT: 80,
    CeilingSource.THERMAL_CAP: 70,
    CeilingSource.RAW_FALLBACK: 40,
}
MIN_PIECE_AREA_M2 = 0.05


@dataclass(frozen=True, slots=True)
class CeilingCandidate:
    corners: list[list[float]]
    plane: Plane
    source: CeilingSource
    locator_id: str
    arrangement_cell_id: str | None = None


def _polygon_xz(corners: list[list[float]]) -> Polygon | None:
    if len(corners) < 3:
        return None
    try:
        poly = make_valid(Polygon([(float(corner[0]), float(corner[2])) for corner in corners]))
    except Exception:
        return None
    if poly.is_empty:
        return None
    if isinstance(poly, Polygon):
        return poly if poly.area >= MIN_PIECE_AREA_M2 else None
    parts = [part for part in getattr(poly, "geoms", []) if isinstance(part, Polygon) and part.area >= MIN_PIECE_AREA_M2]
    if not parts:
        return None
    return make_valid(unary_union(parts))


def _polygon_parts(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom] if geom.area >= MIN_PIECE_AREA_M2 else []
    return [
        part
        for part in getattr(geom, "geoms", [])
        if isinstance(part, Polygon) and part.area >= MIN_PIECE_AREA_M2
    ]


def _ring_to_vec3(coords, plane: Plane) -> list[Vec3] | None:
    ring = list(coords)
    if len(ring) >= 2 and ring[0] == ring[-1]:
        ring = ring[:-1]
    out: list[Vec3] = []
    for x, z in ring:
        y = plane.y_at(float(x), float(z))
        if y is None:
            return None
        out.append(Vec3(x=float(x), y=float(y), z=float(z)))
    return out if len(out) >= 3 else None


def _to_payload_plane(plane: Plane) -> PayloadPlane:
    return PayloadPlane(a=plane.a, b=plane.b, c=plane.c, d=plane.d)


def _candidate_piece(candidate: CeilingCandidate, poly: Polygon, suffix: int) -> CeilingPiece | None:
    corners = _ring_to_vec3(poly.exterior.coords, candidate.plane)
    if corners is None:
        return None
    if newell_normal([[corner.x, corner.y, corner.z] for corner in corners])[1] <= 0.0:
        corners = list(reversed(corners))
    holes: list[list[Vec3]] = []
    for interior in poly.interiors:
        hole = _ring_to_vec3(interior.coords, candidate.plane)
        if hole is not None:
            holes.append(hole)
    locator_id = candidate.locator_id if suffix == 0 else f"{candidate.locator_id}:{suffix}"
    return CeilingPiece(
        corners=corners,
        holes=holes,
        plane=_to_payload_plane(candidate.plane),
        source=candidate.source,
        arrangement_cell_id=candidate.arrangement_cell_id,
        locator_id=locator_id,
    )


def assemble_ceiling(
    candidates: list[CeilingCandidate],
    holes: list[CeilingCandidate] | None = None,
) -> list[CeilingPiece]:
    hole_candidates = [
        candidate
        for candidate in (holes or [])
        if candidate.source == CeilingSource.DORMER_CUTOUT
    ]
    hole_polys = [
        (PRIORITY[hole.source], poly)
        for hole in hole_candidates
        if (poly := _polygon_xz(hole.corners)) is not None
    ]
    sorted_candidates = sorted(
        [candidate for candidate in candidates if candidate.source != CeilingSource.DORMER_CUTOUT],
        key=lambda candidate: -PRIORITY[candidate.source],
    )

    visible: list[CeilingPiece] = []
    occupied = None
    for candidate in sorted_candidates:
        poly = _polygon_xz(candidate.corners)
        if poly is None:
            continue
        if occupied is not None and not occupied.is_empty:
            poly = make_valid(poly.difference(occupied))
        active_holes = [
            hole_poly
            for hole_priority, hole_poly in hole_polys
            if hole_priority > PRIORITY[candidate.source]
        ]
        if active_holes:
            poly = make_valid(poly.difference(unary_union(active_holes)))

        emitted_parts = _polygon_parts(poly)
        for suffix, part in enumerate(emitted_parts):
            piece = _candidate_piece(candidate, part, suffix)
            if piece is not None:
                visible.append(piece)

        if emitted_parts:
            emitted_union = make_valid(unary_union(emitted_parts))
            occupied = emitted_union if occupied is None else make_valid(unary_union([occupied, emitted_union]))

    return visible
