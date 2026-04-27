from __future__ import annotations

from math import cos, radians, sin

from shapely.geometry import Polygon
from shapely.ops import unary_union

from reconcile._core.shapely2 import make_valid_polygon
from reconcile.extract.building import BuildingModel
from reconcile.roof.geometry import angle_diff_deg
from reconcile.roof.roof import ClippedRoofPlane, Footprint, RoofPlaneCandidate

SNAP_ROBUST_SIMPLIFY_TOL_M = 0.005
PLANE_ROOM_BUFFER_M = 1.0
SLOPE_MARGIN_M = 0.5
EAVE_OVERHANG_M = 0.5


def _ring(geometry) -> list[tuple[float, float]]:
    if geometry.geom_type == "MultiPolygon":
        geometry = max(geometry.geoms, key=lambda g: g.area)
    if geometry.geom_type != "Polygon":
        return []
    coords = list(geometry.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    return [(float(x), float(z)) for x, z in coords]


def _room_polygon(room) -> Polygon | None:
    if len(room.floor_polygon) < 3:
        return None
    poly = Polygon([(float(p[0]), float(p[2])) for p in room.floor_polygon])
    if not poly.is_valid:
        poly = make_valid_polygon(poly)
    if poly is None:
        return None
    if poly.is_empty or poly.area <= 0.0:
        return None
    return poly


def _source_room_indices(candidate: RoofPlaneCandidate) -> set[int]:
    return {
        segment.room_index
        for segment in candidate.cluster.segments
        if segment.room_index is not None and segment.room_index >= 0
    }


def _height_cap(candidate: RoofPlaneCandidate, model: BuildingModel | None) -> float | None:
    if model is None:
        return None
    ys: list[float] = []
    for room_idx in _source_room_indices(candidate):
        if room_idx >= len(model.rooms):
            continue
        room = model.rooms[room_idx]
        for wall in room.walls_computed:
            ys.extend(float(point[1]) for point in wall.corners)
        for raw in room.raw_ceiling_planes:
            ys.extend(float(point[1]) for point in raw.corners)
        ys.extend(float(point[1]) for point in room.ceiling_polygon)
    if not ys:
        ys = [float(point[1]) for segment in candidate.cluster.segments for point in (segment.a, segment.b)]
    if not ys:
        return None
    return max(ys) + EAVE_OVERHANG_M


def _supported_domain(candidate: RoofPlaneCandidate, footprint_poly: Polygon, model: BuildingModel | None) -> Polygon:
    if model is None:
        return Polygon(candidate.polygon_xz)
    room_polys = []
    buffered = []
    for room_idx in _source_room_indices(candidate):
        if room_idx >= len(model.rooms):
            continue
        poly = _room_polygon(model.rooms[room_idx])
        if poly is None:
            continue
        room_polys.append(poly)
        buffered.append(poly.buffer(PLANE_ROOM_BUFFER_M, join_style="mitre"))
    if not room_polys or not buffered:
        return Polygon(candidate.polygon_xz)

    envelope = unary_union([footprint_poly, *room_polys])
    support = unary_union(buffered).convex_hull
    domain = envelope.intersection(support)
    if domain.is_empty:
        return Polygon(candidate.polygon_xz)
    return domain


def _axes(candidate: RoofPlaneCandidate) -> tuple[float, float, float, float]:
    az = radians(candidate.cluster.avg_azimuth)
    ridge_x, ridge_z = -cos(az), sin(az)
    slope_x, slope_z = sin(az), cos(az)
    return ridge_x, ridge_z, slope_x, slope_z


def _project(point: tuple[float, float], ref_x: float, ref_z: float, axis_x: float, axis_z: float) -> float:
    return (point[0] - ref_x) * axis_x + (point[1] - ref_z) * axis_z


def _clip_by_axis(
    polygon: list[tuple[float, float]],
    ref_x: float,
    ref_z: float,
    axis_x: float,
    axis_z: float,
    bound: float,
    keep_greater: bool,
) -> list[tuple[float, float]]:
    if len(polygon) < 3:
        return []
    out: list[tuple[float, float]] = []
    for idx, current in enumerate(polygon):
        nxt = polygon[(idx + 1) % len(polygon)]
        current_v = _project(current, ref_x, ref_z, axis_x, axis_z)
        next_v = _project(nxt, ref_x, ref_z, axis_x, axis_z)
        current_inside = current_v >= bound if keep_greater else current_v <= bound
        next_inside = next_v >= bound if keep_greater else next_v <= bound
        if current_inside:
            out.append(current)
        if current_inside != next_inside:
            denom = next_v - current_v
            if abs(denom) > 1e-9:
                t = (bound - current_v) / denom
                out.append((current[0] + t * (nxt[0] - current[0]), current[1] + t * (nxt[1] - current[1])))
    return out


def _extent_for_points(
    points: list[tuple[float, float]],
    ref_x: float,
    ref_z: float,
    axis_x: float,
    axis_z: float,
) -> tuple[float, float] | None:
    if not points:
        return None
    vals = [_project(point, ref_x, ref_z, axis_x, axis_z) for point in points]
    return min(vals), max(vals)


def _candidate_bounds(
    candidate: RoofPlaneCandidate,
    model: BuildingModel | None,
) -> tuple[float, float, float, float] | None:
    ridge_x, ridge_z, slope_x, slope_z = _axes(candidate)
    ref_x, ref_z = float(candidate.cluster.ref_pt[0]), float(candidate.cluster.ref_pt[2])
    segment_points = [(float(p[0]), float(p[2])) for segment in candidate.cluster.segments for p in (segment.a, segment.b)]
    if not segment_points:
        return None
    seg_r = _extent_for_points(segment_points, ref_x, ref_z, ridge_x, ridge_z)
    seg_s = _extent_for_points(segment_points, ref_x, ref_z, slope_x, slope_z)
    if seg_r is None or seg_s is None:
        return None
    min_r, max_r = seg_r
    min_s, max_s = seg_s
    if model is not None:
        for room_idx in _source_room_indices(candidate):
            if room_idx >= len(model.rooms):
                continue
            fp = model.rooms[room_idx].floor_polygon
            room_points = [(float(p[0]), float(p[2])) for p in fp]
            room_r = _extent_for_points(room_points, ref_x, ref_z, ridge_x, ridge_z)
            room_s = _extent_for_points(room_points, ref_x, ref_z, slope_x, slope_z)
            if room_r is not None:
                min_r = min(min_r, room_r[0])
                max_r = max(max_r, room_r[1])
            if room_s is not None:
                min_s = min(min_s, room_s[0])
                max_s = max(max_s, room_s[1])
    return min_r, max_r, min_s, max_s


def _has_opposing(candidate: RoofPlaneCandidate, candidates: list[RoofPlaneCandidate]) -> bool:
    for other in candidates:
        if other is candidate:
            continue
        if other.dominant_story != candidate.dominant_story:
            continue
        diff = angle_diff_deg(candidate.cluster.avg_azimuth, other.cluster.avg_azimuth)
        if 140.0 <= diff <= 220.0:
            return True
    return False


def _clip_to_candidate_bounds(
    ring: list[tuple[float, float]],
    candidate: RoofPlaneCandidate,
    candidates: list[RoofPlaneCandidate],
    model: BuildingModel | None,
) -> list[tuple[float, float]]:
    bounds = _candidate_bounds(candidate, model)
    if bounds is None:
        return ring
    min_r, max_r, min_s, max_s = bounds
    ridge_x, ridge_z, slope_x, slope_z = _axes(candidate)
    ref_x, ref_z = float(candidate.cluster.ref_pt[0]), float(candidate.cluster.ref_pt[2])

    clipped = _clip_by_axis(ring, ref_x, ref_z, ridge_x, ridge_z, min_r, True)
    clipped = _clip_by_axis(clipped, ref_x, ref_z, ridge_x, ridge_z, max_r, False)
    if not _has_opposing(candidate, candidates):
        clipped = _clip_by_axis(clipped, ref_x, ref_z, slope_x, slope_z, min_s - SLOPE_MARGIN_M, True)
        clipped = _clip_by_axis(clipped, ref_x, ref_z, slope_x, slope_z, max_s + SLOPE_MARGIN_M, False)
    return clipped


def clip_planes_to_footprint(
    candidates: list[RoofPlaneCandidate],
    footprint: Footprint,
    model: BuildingModel | None = None,
) -> list[ClippedRoofPlane]:
    fp = Polygon(footprint.polygon_xz)
    if not fp.is_valid:
        fp = make_valid_polygon(fp)
    if fp is None:
        return []
    out: list[ClippedRoofPlane] = []
    for candidate in candidates:
        poly = _supported_domain(candidate, fp, model)
        if not poly.is_valid:
            poly = make_valid_polygon(poly)
        if poly is None:
            continue
        clipped = poly.intersection(fp)
        if clipped.is_empty:
            continue
        clipped = clipped.simplify(SNAP_ROBUST_SIMPLIFY_TOL_M, preserve_topology=True)
        ring = _ring(clipped)
        ring = _clip_to_candidate_bounds(ring, candidate, candidates, model)
        if len(ring) >= 3:
            out.append(ClippedRoofPlane(candidate=candidate, polygon_xz=ring, max_y=_height_cap(candidate, model)))
    return out
