"""Serve reconcile viewer assets and proxy Datafordeleren orthophoto WMTS tiles.

Usage:
  DATAFORDELEREN_API_KEY=... python reconcile/viewer_server.py

Then open:
  http://localhost:8765/viewer.html
"""

from __future__ import annotations

import json
import os
import posixpath
import subprocess
import urllib.parse
import urllib.request
from collections import defaultdict
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid

from reconcile.extract3d.builder import extract_building
from reconcile.roof_algorithms_py import run_roof_algorithms
from reconcile.roof_algorithms_py.math_utils import plane_normal, plane_y_at
from reconcile_v2.graph_builder import build_topology_graph

HOST = "127.0.0.1"
PORT = int(os.environ.get("VIEWER_PORT", "8080"))
WMTS_BASE = "https://wmts.datafordeler.dk/GeoDanmarkOrto/orto_foraar_webm/1.0.0/WMTS"
SECRET_NAME = "datafordeler-graphql-api-key"
ROOT_DIR = Path(__file__).resolve().parent
CALIBRATION_PATH = ROOT_DIR.parent / ".context" / "alignment_calibration.json"
PIPELINE_ROOT = ROOT_DIR.parent / "pipeline-outputs"
SCAN_CACHE_ROOT = ROOT_DIR.parent / ".scan-cache"
ONTOLOGY_CACHE: dict[str, dict] = {}
UNASSIGNED_PART_ID = "building-part:unassigned"
FULL_BUILDING_PART_ID = "building-part:full-building"


def _room_key(room_index: int) -> str:
    return f"room:{int(room_index)}"


def _round6(value: float) -> float:
    return round(float(value), 6)


def _parse_room_index(room_id: str) -> int | None:
    if not isinstance(room_id, str) or not room_id.startswith("room:"):
        return None
    try:
        return int(room_id.split(":", 1)[1])
    except Exception:
        return None


def _parse_topology_room_index(source_id: str) -> int | None:
    if not isinstance(source_id, str) or not source_id:
        return None
    direct = _parse_room_index(source_id)
    if direct is not None:
        return direct
    marker = "merged_room_"
    if marker not in source_id:
        return None
    try:
        return int(source_id.rsplit(marker, 1)[1])
    except Exception:
        return None


def _room_indices_for_ids(room_ids: set[str] | list[str], room_indices_by_room_id: dict[str, int]) -> list[int]:
    indices: set[int] = set()
    for room_id in room_ids or []:
        if room_id in room_indices_by_room_id:
            indices.add(int(room_indices_by_room_id[room_id]))
            continue
        parsed = _parse_room_index(str(room_id))
        if parsed is not None:
            indices.add(parsed)
    return sorted(indices)


def _poly_xz_from_3d(corners: list[Any]) -> Polygon | None:
    coords: list[tuple[float, float]] = []
    for corner in corners or []:
        if not isinstance(corner, (list, tuple)) or len(corner) < 3:
            continue
        coords.append((_round6(corner[0]), _round6(corner[2])))
    if len(coords) < 3:
        return None
    poly = Polygon(coords)
    if not poly.is_valid:
        try:
            poly = make_valid(poly)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda geom: geom.area, default=None)
        except Exception:
            return None
    if poly is None or poly.is_empty or not isinstance(poly, Polygon):
        return None
    if poly.area <= 1e-6:
        return None
    return poly


def _polygon_xz_to_3d(polygon_xz: list[list[float]], y: float) -> list[list[float]]:
    return [[_round6(x), _round6(y), _round6(z)] for x, z in polygon_xz]


def _serialize_poly_xz(poly: Polygon | None) -> list[list[float]]:
    if poly is None or poly.is_empty:
        return []
    coords = list(poly.exterior.coords)
    if coords and coords[-1] == coords[0]:
        coords = coords[:-1]
    return [[_round6(x), _round6(z)] for x, z, *_ in coords]


def _bbox_xz(poly: Polygon | None) -> list[float] | None:
    if poly is None or poly.is_empty:
        return None
    min_x, min_z, max_x, max_z = poly.bounds
    return [_round6(min_x), _round6(min_z), _round6(max_x), _round6(max_z)]


def _centroid_xz(poly: Polygon | None) -> list[float] | None:
    if poly is None or poly.is_empty:
        return None
    c = poly.centroid
    return [_round6(c.x), _round6(c.y)]


def _largest_polygon(geom: Any) -> Polygon | None:
    if geom is None or getattr(geom, "is_empty", True):
        return None
    if isinstance(geom, Polygon):
        return geom
    geoms = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]
    if not geoms:
        return None
    return max(geoms, key=lambda poly: poly.area)


def _decompose_polygons(geom: Any) -> list[Polygon]:
    if geom is None or getattr(geom, "is_empty", True):
        return []
    if isinstance(geom, Polygon):
        return [geom]
    return [poly for poly in getattr(geom, "geoms", []) if isinstance(poly, Polygon) and not poly.is_empty]


def _surface_plane(surface: dict[str, Any]) -> dict[str, Any] | None:
    cluster = surface.get("cluster") or {}
    avg_azimuth = cluster.get("avgAzimuth")
    avg_incl = cluster.get("avgIncl")
    ref = cluster.get("refPt") or surface.get("center") or {}
    if avg_azimuth is not None and avg_incl is not None and ref:
        return {
            "n": plane_normal(float(avg_azimuth), float(avg_incl)),
            "ref": {
                "x": float(ref["x"]),
                "y": float(ref["y"]),
                "z": float(ref["z"]),
            },
        }
    corners = [
        corner
        for corner in (surface.get("corners") or [])
        if isinstance(corner, (list, tuple)) and len(corner) >= 3
    ]
    if len(corners) < 3:
        return None
    a, b, c = corners[0], corners[1], corners[2]
    ab = (
        float(b[0]) - float(a[0]),
        float(b[1]) - float(a[1]),
        float(b[2]) - float(a[2]),
    )
    ac = (
        float(c[0]) - float(a[0]),
        float(c[1]) - float(a[1]),
        float(c[2]) - float(a[2]),
    )
    nx = ab[1] * ac[2] - ab[2] * ac[1]
    ny = ab[2] * ac[0] - ab[0] * ac[2]
    nz = ab[0] * ac[1] - ab[1] * ac[0]
    norm = (nx * nx + ny * ny + nz * nz) ** 0.5
    if norm <= 1e-9 or abs(ny) <= 1e-9:
        return None
    nx /= norm
    ny /= norm
    nz /= norm
    if ny < 0.0:
        nx *= -1.0
        ny *= -1.0
        nz *= -1.0
    return {
        "n": {"x": nx, "y": ny, "z": nz},
        "ref": {"x": float(a[0]), "y": float(a[1]), "z": float(a[2])},
    }


def _surface_is_oblique(surface: dict[str, Any]) -> bool:
    kind = str(surface.get("kind") or surface.get("surface_kind") or "")
    if kind == "oblique":
        return True
    if kind == "flat":
        return False
    hypothesis_id = str(surface.get("roof_hypothesis_id") or "")
    if hypothesis_id.startswith("roof-hypothesis:oblique:"):
        return True
    if hypothesis_id.startswith("roof-hypothesis:flat:"):
        return False
    cluster = surface.get("cluster") or {}
    try:
        return abs(float(cluster.get("avgIncl"))) > 5.0
    except Exception:
        return False


def _surface_y_at(surface: dict[str, Any], x: float, z: float) -> float:
    if _surface_is_oblique(surface):
        plane = _surface_plane(surface)
        if plane is not None:
            return _round6(plane_y_at(plane, float(x), float(z)))
    ys = [
        float(corner[1])
        for corner in (surface.get("corners") or [])
        if isinstance(corner, (list, tuple)) and len(corner) >= 3
    ]
    return _round6(sum(ys) / len(ys)) if ys else 0.0


def _lift_poly_on_surface(poly: Polygon, surface: dict[str, Any]) -> list[list[float]]:
    coords = list(poly.exterior.coords)
    if coords and coords[-1] == coords[0]:
        coords = coords[:-1]
    lifted: list[list[float]] = []
    for x, z, *_ in coords:
        lifted.append([_round6(x), _surface_y_at(surface, float(x), float(z)), _round6(z)])
    return lifted


def _slice_topology_cells_for_graph_rooms(
    topology_cell_complex: dict[str, Any],
    graph_room_ids: set[str],
) -> list[dict[str, Any]]:
    cells = []
    for cell in (topology_cell_complex.get("cells") or []):
        if not isinstance(cell, dict):
            continue
        if str(cell.get("kind")) != "room":
            continue
        if str(cell.get("source_id") or "") not in graph_room_ids:
            continue
        cells.append(cell)
    return cells


def _filter_part_dormers(dormers: list[dict[str, Any]], room_indices: set[int]) -> list[dict[str, Any]]:
    if not room_indices:
        return []
    kept: list[dict[str, Any]] = []
    for dormer in dormers or []:
        room_index = dormer.get("room_index")
        if isinstance(room_index, int) and room_index in room_indices:
            kept.append(dormer)
    return kept


def _room_partition_surfaces_by_room(roof: dict[str, Any] | None) -> dict[int, list[dict[str, Any]]]:
    surfaces_by_room: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for room_partition in (((roof or {}).get("ceiling_partitions") or {}).get("room_partitions") or []):
        room_index = room_partition.get("room_index")
        if not isinstance(room_index, int):
            continue
        for partition in (room_partition.get("partitions") or []):
            corners = partition.get("poly") or []
            if not isinstance(corners, list) or len(corners) < 3:
                continue
            surfaces_by_room[room_index].append(
                {
                    "id": partition.get("id"),
                    "kind": str(partition.get("kind") or "flat"),
                    "roof_hypothesis_id": partition.get("roof_hypothesis_id"),
                    "corners": corners,
                }
            )
    return surfaces_by_room


def _wall_vertical_pairs(corners: list[list[float]]) -> tuple[list[int], dict[int, int]] | None:
    points = [
        [_round6(corner[0]), _round6(corner[1]), _round6(corner[2])]
        for corner in corners or []
        if isinstance(corner, (list, tuple)) and len(corner) >= 3
    ]
    if len(points) < 4:
        return None
    indexed = list(enumerate(points))
    indexed.sort(key=lambda item: (item[1][1], item[1][0], item[1][2]))
    bottom = [index for index, _ in indexed[:2]]
    top = [index for index, _ in indexed[-2:]]
    if len(set(bottom)) != 2 or len(set(top)) != 2:
        return None
    mapping: dict[int, int] = {}
    unused_top = set(top)
    for bottom_index in bottom:
        bx, _, bz = points[bottom_index]
        best_top = min(
            unused_top,
            key=lambda top_index: (
                (points[top_index][0] - bx) ** 2 + (points[top_index][2] - bz) ** 2,
                abs(points[top_index][1] - points[bottom_index][1]),
            ),
        )
        mapping[bottom_index] = best_top
        unused_top.remove(best_top)
    return bottom, mapping


def _decompose_lines(geom: Any) -> list[LineString]:
    if geom is None or getattr(geom, "is_empty", True):
        return []
    if isinstance(geom, LineString):
        return [geom]
    return [line for line in getattr(geom, "geoms", []) if isinstance(line, LineString) and not line.is_empty]


def _serialize_corners(corners: list[list[float]]) -> list[list[float]]:
    return [[_round6(c[0]), _round6(c[1]), _round6(c[2])] for c in corners or [] if len(c) >= 3]


def _building_story_unions(building: dict[str, Any] | None) -> dict[int, Polygon]:
    if building is None:
        return {}
    polys_by_story: dict[int, list[Polygon]] = defaultdict(list)
    for room in (building.get("rooms") or []):
        story = int(room.get("story", 0) or 0)
        poly = _poly_xz_from_3d(room.get("floor_polygon") or [])
        if poly is not None:
            polys_by_story[story].append(poly)
    unions: dict[int, Polygon] = {}
    for story, polys in polys_by_story.items():
        if not polys:
            continue
        try:
            union_poly = _largest_polygon(unary_union(polys))
        except Exception:
            union_poly = None
        if union_poly is not None:
            unions[story] = union_poly
    return unions


def _wall_ordered_profile(
    corners: list[list[float]],
) -> tuple[list[list[float]], list[list[float]], LineString] | None:
    points = _serialize_corners(corners)
    pairing = _wall_vertical_pairs(points)
    if pairing is None:
        return None
    bottom_indices, top_by_bottom = pairing
    provisional = LineString([(float(points[index][0]), float(points[index][2])) for index in bottom_indices])
    if provisional.length <= 1e-6:
        return None
    ordered_bottom = sorted(
        bottom_indices,
        key=lambda index: float(provisional.project(Point(float(points[index][0]), float(points[index][2])))),
    )
    b0, b1 = ordered_bottom
    t0 = top_by_bottom[b0]
    t1 = top_by_bottom[b1]
    bottom = [points[b0], points[b1]]
    top = [points[t0], points[t1]]
    wall_line = LineString([(bottom[0][0], bottom[0][2]), (bottom[1][0], bottom[1][2])])
    if wall_line.length <= 1e-6:
        return None
    return bottom, top, wall_line


def _interp_corner(left: list[float], right: list[float], t: float) -> list[float]:
    return [
        _round6(float(left[0]) + (float(right[0]) - float(left[0])) * t),
        _round6(float(left[1]) + (float(right[1]) - float(left[1])) * t),
        _round6(float(left[2]) + (float(right[2]) - float(left[2])) * t),
    ]


def _wall_surface_intervals(
    wall_line: LineString,
    room_surfaces: list[dict[str, Any]],
) -> list[tuple[float, float, dict[str, Any]]]:
    intervals: list[tuple[float, float, dict[str, Any]]] = []
    for surface in room_surfaces:
        poly = _poly_xz_from_3d(surface.get("corners") or [])
        if poly is None:
            continue
        try:
            intersection = poly.buffer(1e-6, cap_style=2, join_style=2).intersection(wall_line)
        except Exception:
            continue
        for line in _decompose_lines(intersection):
            coords = list(line.coords)
            if len(coords) < 2:
                continue
            start = wall_line.project(Point(coords[0]))
            end = wall_line.project(Point(coords[-1]))
            if end < start:
                start, end = end, start
            if end - start <= 1e-6:
                continue
            intervals.append((start / wall_line.length, end / wall_line.length, surface))
    return intervals


def _is_exterior_wall_line(wall_line: LineString, story_union: Polygon | None) -> bool:
    if story_union is None:
        return False
    try:
        overlap = wall_line.intersection(story_union.boundary)
    except Exception:
        return False
    return not overlap.is_empty and float(getattr(overlap, "length", 0.0)) > 1e-6


def _polygon_centroid3(corners: list[list[float]]) -> list[float]:
    if not corners:
        return [0.0, 0.0, 0.0]
    sx = sum(float(corner[0]) for corner in corners)
    sy = sum(float(corner[1]) for corner in corners)
    sz = sum(float(corner[2]) for corner in corners)
    inv = 1.0 / max(1, len(corners))
    return [_round6(sx * inv), _round6(sy * inv), _round6(sz * inv)]


def _projection_axes_for_corners(corners: list[list[float]]) -> tuple[int, int]:
    nx = ny = nz = 0.0
    count = len(corners)
    for index, corner in enumerate(corners):
        next_corner = corners[(index + 1) % count]
        nx += (float(corner[1]) - float(next_corner[1])) * (float(corner[2]) + float(next_corner[2]))
        ny += (float(corner[2]) - float(next_corner[2])) * (float(corner[0]) + float(next_corner[0]))
        nz += (float(corner[0]) - float(next_corner[0])) * (float(corner[1]) + float(next_corner[1]))
    anx, any_, anz = abs(nx), abs(ny), abs(nz)
    if any_ >= anx and any_ >= anz:
        return (0, 2)
    if anx >= any_ and anx >= anz:
        return (1, 2)
    return (0, 1)


def _point_in_polygon_2(point: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    inside = False
    for index in range(len(poly)):
        xi, yi = poly[index]
        xj, yj = poly[index - 1]
        crosses = ((yi > point[1]) != (yj > point[1])) and (
            point[0] < (xj - xi) * (point[1] - yi) / ((yj - yi) or 1e-9) + xi
        )
        if crosses:
            inside = not inside
    return inside


def _distance_point_to_segment_2(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    vx = float(b[0] - a[0])
    vy = float(b[1] - a[1])
    wx = float(point[0] - a[0])
    wy = float(point[1] - a[1])
    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        return ((wx * wx) + (wy * wy)) ** 0.5
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / vv))
    px = float(a[0] + t * vx)
    py = float(a[1] + t * vy)
    dx = float(point[0] - px)
    dy = float(point[1] - py)
    return (dx * dx + dy * dy) ** 0.5


def _wall_plane(corners: list[list[float]]) -> tuple[tuple[float, float, float], float] | None:
    if len(corners) < 3:
        return None
    a, b, c = corners[0], corners[1], corners[2]
    ab = (float(b[0] - a[0]), float(b[1] - a[1]), float(b[2] - a[2]))
    ac = (float(c[0] - a[0]), float(c[1] - a[1]), float(c[2] - a[2]))
    nx = ab[1] * ac[2] - ab[2] * ac[1]
    ny = ab[2] * ac[0] - ab[0] * ac[2]
    nz = ab[0] * ac[1] - ab[1] * ac[0]
    norm = (nx * nx + ny * ny + nz * nz) ** 0.5
    if norm <= 1e-12:
        return None
    nx /= norm
    ny /= norm
    nz /= norm
    d = -((nx * float(a[0])) + (ny * float(a[1])) + (nz * float(a[2])))
    return (nx, ny, nz), d


def _distance_to_plane(plane: tuple[tuple[float, float, float], float], point: list[float]) -> float:
    (nx, ny, nz), d = plane
    return abs(nx * float(point[0]) + ny * float(point[1]) + nz * float(point[2]) + d)


def _collect_wall_cutout_holes(
    wall_corners: list[list[float]],
    openings: list[dict[str, Any]],
) -> list[list[list[float]]]:
    plane = _wall_plane(wall_corners)
    if plane is None:
        return []
    axis0, axis1 = _projection_axes_for_corners(wall_corners)
    outer2 = [(float(corner[axis0]), float(corner[axis1])) for corner in wall_corners]
    holes: list[list[list[float]]] = []
    plane_eps = 0.05
    edge_margin = 0.01
    for opening in openings or []:
        corners = opening.get("corners") or []
        if not isinstance(corners, list) or len(corners) != 4:
            continue
        normalized = _serialize_corners(corners)
        if any(_distance_to_plane(plane, corner) > plane_eps for corner in normalized):
            continue
        centroid = _polygon_centroid3(normalized)
        centroid2 = (float(centroid[axis0]), float(centroid[axis1]))
        if not _point_in_polygon_2(centroid2, outer2):
            continue
        hole2 = [(float(corner[axis0]), float(corner[axis1])) for corner in normalized]
        valid = True
        for point in hole2:
            if not _point_in_polygon_2(point, outer2):
                valid = False
                break
            min_dist = min(
                _distance_point_to_segment_2(point, outer2[index - 1], outer2[index])
                for index in range(len(outer2))
            )
            if min_dist < edge_margin:
                valid = False
                break
        if valid:
            holes.append(normalized)
    return holes


def _segment_wall_corners_by_room_surfaces(
    corners: list[list[float]],
    room_surfaces: list[dict[str, Any]],
) -> list[tuple[list[list[float]], dict[str, Any] | None]]:
    profile = _wall_ordered_profile(corners)
    if profile is None:
        return [(_serialize_corners(corners), None)]
    bottom, top, wall_line = profile
    intervals = _wall_surface_intervals(wall_line, room_surfaces)
    if not intervals:
        return [(_serialize_corners(corners), None)]
    split_ts = {0.0, 1.0}
    for start_t, end_t, _surface in intervals:
        split_ts.add(max(0.0, min(1.0, start_t)))
        split_ts.add(max(0.0, min(1.0, end_t)))
    ordered_ts = sorted(split_ts)
    segments: list[tuple[list[list[float]], dict[str, Any] | None]] = []
    for left_t, right_t in zip(ordered_ts[:-1], ordered_ts[1:]):
        if right_t - left_t <= 1e-6:
            continue
        mid_t = (left_t + right_t) * 0.5
        surface = None
        for start_t, end_t, candidate in intervals:
            if start_t - 1e-6 <= mid_t <= end_t + 1e-6:
                surface = candidate
                break
        bottom_left = _interp_corner(bottom[0], bottom[1], left_t)
        bottom_right = _interp_corner(bottom[0], bottom[1], right_t)
        top_left = _interp_corner(top[0], top[1], left_t)
        top_right = _interp_corner(top[0], top[1], right_t)
        if surface is not None:
            top_left[1] = _round6(max(bottom_left[1], min(top_left[1], _surface_y_at(surface, top_left[0], top_left[2]))))
            top_right[1] = _round6(max(bottom_right[1], min(top_right[1], _surface_y_at(surface, top_right[0], top_right[2]))))
        segment = [bottom_left, bottom_right, top_right, top_left]
        if LineString([(bottom_left[0], bottom_left[2]), (bottom_right[0], bottom_right[2])]).length <= 1e-6:
            continue
        segments.append((segment, surface))
    return segments or [(_serialize_corners(corners), None)]


def _renderable_surfaces_from_room_wall(
    wall: dict[str, Any],
    *,
    part_id: str,
    room_index: int,
    story: int,
    room_surfaces: list[dict[str, Any]],
    openings: list[dict[str, Any]],
    wall_index: int,
    story_union: Polygon | None,
    extension_index: int | None = None,
) -> list[dict[str, Any]]:
    raw_corners = wall.get("corners") or []
    if not isinstance(raw_corners, list) or len(raw_corners) < 3:
        return []
    profile = _wall_ordered_profile(raw_corners)
    if profile is None:
        return []
    _bottom, _top, wall_line = profile
    category = "base_exterior_wall" if _is_exterior_wall_line(wall_line, story_union) else "base_interior_wall"
    identifier = str(wall.get("id") or f"room-wall:{room_index}:{wall_index}")
    suffix = f":ext:{extension_index}" if extension_index is not None else ""
    renderable: list[dict[str, Any]] = []
    for segment_index, (segment_corners, surface) in enumerate(_segment_wall_corners_by_room_surfaces(raw_corners, room_surfaces)):
        renderable.append(
            {
                "id": f"renderable:{category}:{identifier}{suffix}:seg:{segment_index}",
                "category": category,
                "source_kind": "raw_room_wall",
                "source_id": identifier,
                "corners": segment_corners,
                "holes": _collect_wall_cutout_holes(segment_corners, openings),
                "part_id": part_id,
                "room_id": _room_key(room_index),
                "room_index": room_index,
                "story": story,
                "roof_hypothesis_id": (surface or {}).get("roof_hypothesis_id"),
            }
        )
    return renderable


def _renderable_surface_from_room_floor(room: dict[str, Any], *, part_id: str, room_index: int, story: int) -> dict[str, Any] | None:
    corners = room.get("floor_polygon") or []
    if not isinstance(corners, list) or len(corners) < 3:
        return None
    return {
        "id": f"renderable:base_room_floor:{room_index}",
        "category": "base_room_floor",
        "source_kind": "raw_room_floor",
        "source_id": f"room-floor:{room_index}",
        "corners": [[_round6(c[0]), _round6(c[1]), _round6(c[2])] for c in corners if len(c) >= 3],
        "part_id": part_id,
        "room_id": _room_key(room_index),
        "room_index": room_index,
        "story": story,
    }


def _renderable_fenestration_surfaces(
    room: dict[str, Any],
    *,
    part_id: str,
    room_index: int,
    story: int,
) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    fenestration_specs = [
        ("window", "base_window", room.get("windows") or []),
        ("door", "base_door", room.get("doors") or []),
        ("opening", "base_opening", room.get("openings") or []),
    ]
    for kind, category, items in fenestration_specs:
        for index, item in enumerate(items):
            corners = _serialize_corners(item.get("corners") or [])
            if len(corners) < 3:
                continue
            surfaces.append(
                {
                    "id": f"renderable:{category}:{room_index}:{index}",
                    "category": category,
                    "source_kind": kind,
                    "source_id": item.get("id") or f"{kind}:{room_index}:{index}",
                    "corners": corners,
                    "part_id": part_id,
                    "room_id": _room_key(room_index),
                    "room_index": room_index,
                    "story": story,
                }
            )
    return surfaces


def _fenestration_by_room(building: dict[str, Any] | None) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    if building is None:
        return out
    for room_index, room in enumerate(building.get("rooms") or []):
        out[room_index] = [
            *({"corners": item.get("corners") or []} for item in (room.get("windows") or [])),
            *({"corners": item.get("corners") or []} for item in (room.get("doors") or [])),
            *({"corners": item.get("corners") or []} for item in (room.get("openings") or [])),
        ]
    return out


def _renderable_surface_from_occupied_face(
    face: dict[str, Any],
    cell: dict[str, Any],
    *,
    part_id: str,
    openings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    corners = _face_corners(face)
    if len(corners) < 3:
        return None
    metadata = face.get("metadata") or {}
    boundary_class = str(metadata.get("boundary_class") or "")
    category: str | None = None
    holes: list[list[list[float]]] = []
    if boundary_class == "floor":
        category = "base_room_floor"
    elif boundary_class == "ceiling":
        category = "base_room_ceiling"
    elif boundary_class == "exterior_wall":
        category = "base_exterior_wall"
        holes = _collect_wall_cutout_holes(corners, openings)
    elif boundary_class == "interior_wall":
        category = "base_interior_wall"
        holes = _collect_wall_cutout_holes(corners, openings)
    if category is None:
        return None
    return {
        "id": f"renderable:{category}:{cell.get('id')}:{face.get('id') or boundary_class}",
        "category": category,
        "source_kind": "occupied_room_cell_face",
        "source_id": face.get("id") or boundary_class,
        "cell_id": cell.get("id"),
        "corners": corners,
        "holes": holes,
        "part_id": part_id,
        "room_id": cell.get("room_id"),
        "room_index": cell.get("room_index"),
        "story": cell.get("story"),
        "roof_hypothesis_id": cell.get("roof_hypothesis_id"),
        "top_boundary_atom_id": cell.get("top_boundary_atom_id"),
        "boundary_class": boundary_class,
    }


def _renderable_surfaces_from_occupied_room_cells(
    *,
    occupied_room_cell_complex: dict[str, Any] | None,
    building: dict[str, Any] | None,
    room_indices: set[int],
    part_id: str,
) -> list[dict[str, Any]]:
    if occupied_room_cell_complex is None:
        return []
    fenestration_by_room = _fenestration_by_room(building)
    rooms = building.get("rooms") or [] if building is not None else []
    renderable: list[dict[str, Any]] = []
    include_all = part_id == FULL_BUILDING_PART_ID
    emitted_fenestration_rooms: set[int] = set()
    for cell in (occupied_room_cell_complex.get("cells") or []):
        if not isinstance(cell, dict):
            continue
        room_index = cell.get("room_index")
        if not include_all and (not isinstance(room_index, int) or room_index not in room_indices):
            continue
        for face in (cell.get("faces") or []):
            if not isinstance(face, dict):
                continue
            surface = _renderable_surface_from_occupied_face(
                face,
                cell,
                part_id=part_id,
                openings=fenestration_by_room.get(room_index, []),
            )
            if surface is not None:
                renderable.append(surface)
        if not isinstance(room_index, int):
            continue
        if room_index in emitted_fenestration_rooms:
            continue
        if room_index < 0 or room_index >= len(rooms):
            continue
        room = rooms[room_index] or {}
        story = int(room.get("story", 0) or 0)
        renderable.extend(
            _renderable_fenestration_surfaces(
                room,
                part_id=part_id,
                room_index=room_index,
                story=story,
            )
        )
        emitted_fenestration_rooms.add(room_index)
    return renderable


def _renderable_base_room_surfaces(
    *,
    building: dict[str, Any] | None,
    roof: dict[str, Any] | None,
    room_indices: set[int],
    primary_part_id_by_room_index: dict[int, str],
    part_id: str,
) -> list[dict[str, Any]]:
    if building is None or not room_indices:
        return []
    room_surfaces_by_room = _room_partition_surfaces_by_room(roof)
    story_unions = _building_story_unions(building)
    renderable: list[dict[str, Any]] = []
    rooms = building.get("rooms") or []
    for room_index in sorted(room_indices):
        if primary_part_id_by_room_index.get(room_index) != part_id:
            continue
        if room_index < 0 or room_index >= len(rooms):
            continue
        room = rooms[room_index] or {}
        story = int(room.get("story", 0) or 0)
        fenestration = [
            *({"corners": item.get("corners") or []} for item in (room.get("windows") or [])),
            *({"corners": item.get("corners") or []} for item in (room.get("doors") or [])),
            *({"corners": item.get("corners") or []} for item in (room.get("openings") or [])),
        ]
        floor_surface = _renderable_surface_from_room_floor(room, part_id=part_id, room_index=room_index, story=story)
        if floor_surface is not None:
            renderable.append(floor_surface)
        renderable.extend(
            _renderable_fenestration_surfaces(
                room,
                part_id=part_id,
                room_index=room_index,
                story=story,
            )
        )
        room_surfaces = room_surfaces_by_room.get(room_index) or []
        story_union = story_unions.get(story)
        for wall_index, wall in enumerate(room.get("walls_computed") or []):
            renderable.extend(
                _renderable_surfaces_from_room_wall(
                wall,
                part_id=part_id,
                room_index=room_index,
                story=story,
                room_surfaces=room_surfaces,
                openings=fenestration,
                wall_index=wall_index,
                story_union=story_union,
                )
            )
            extension_strip = wall.get("extension_strip")
            if not extension_strip:
                continue
            strips = extension_strip if isinstance(extension_strip[0], list) and extension_strip and isinstance(extension_strip[0][0], list) else [extension_strip]
            for extension_index, strip in enumerate(strips):
                renderable.extend(
                    _renderable_surfaces_from_room_wall(
                        {"id": wall.get("id"), "corners": strip},
                        part_id=part_id,
                        room_index=room_index,
                        story=story,
                        room_surfaces=room_surfaces,
                        openings=fenestration,
                        wall_index=wall_index,
                        story_union=story_union,
                        extension_index=extension_index,
                    )
                )
    return renderable


def _renderable_category_for_atom(atom: dict[str, Any]) -> str | None:
    role = str(atom.get("role") or "")
    if role == "sloped_ceiling":
        return "room_ceiling_sloped"
    if role in {"attic_floor", "attic_floor_inferred"}:
        return "attic_floor"
    if role in {"flat_transition_cap", "flat_transition_cap_inferred"}:
        return "room_ceiling_flat"
    return None


def _renderable_surface_from_atom(atom: dict[str, Any]) -> dict[str, Any] | None:
    category = _renderable_category_for_atom(atom)
    corners = atom.get("poly") or []
    if category is None or not isinstance(corners, list) or len(corners) < 3:
        return None
    return {
        "id": f"renderable:{category}:{atom.get('id')}",
        "category": category,
        "source_kind": "semantic_atom",
        "source_id": atom.get("id"),
        "corners": corners,
        "part_id": atom.get("effective_part_id") or UNASSIGNED_PART_ID,
        "room_id": atom.get("room_id"),
        "room_index": atom.get("room_index"),
        "story": atom.get("story"),
        "role": atom.get("role"),
        "roof_hypothesis_id": atom.get("roof_hypothesis_id"),
        "top_y_m": atom.get("top_y_m"),
    }


def _renderable_surface_from_unresolved_region(region: dict[str, Any]) -> dict[str, Any] | None:
    corners = region.get("polygon") or []
    if not isinstance(corners, list) or len(corners) < 3:
        return None
    part_ids = [str(value) for value in (region.get("effective_part_ids") or []) if value]
    return {
        "id": f"renderable:unresolved_region:{region.get('id')}",
        "category": "unresolved_region",
        "source_kind": "unresolved_region",
        "source_id": region.get("id"),
        "corners": corners,
        "part_id": part_ids[0] if part_ids else UNASSIGNED_PART_ID,
        "part_ids": part_ids or [UNASSIGNED_PART_ID],
        "room_id": region.get("room_id"),
        "room_index": region.get("room_index"),
        "story": region.get("story"),
        "roof_evidence_score": region.get("roof_evidence_score"),
    }


def _renderable_surface_from_roof_surface(
    surface: dict[str, Any],
    *,
    part_id: str,
    surface_id: str,
    source_kind: str,
) -> dict[str, Any] | None:
    corners = _serialize_corners(surface.get("corners") or [])
    if len(corners) < 3:
        return None
    room_index = surface.get("room_index")
    room_id = _room_key(room_index) if isinstance(room_index, int) else None
    return {
        "id": f"renderable:exterior_roof:{surface_id}",
        "category": "exterior_roof",
        "source_kind": source_kind,
        "source_id": surface.get("boundary_face_id") or surface_id,
        "corners": corners,
        "part_id": part_id,
        "room_id": room_id,
        "room_index": room_index,
        "story": surface.get("story", surface.get("dominant_story")),
        "roof_hypothesis_id": surface.get("roof_hypothesis_id"),
        "surface_kind": surface.get("surface_kind"),
        "flat_role": surface.get("flat_role"),
    }


def _renderable_surface_from_coverage_patch(
    patch: dict[str, Any],
    *,
    part_id: str,
) -> dict[str, Any] | None:
    corners = _serialize_corners(patch.get("polygon") or [])
    if len(corners) < 3:
        return None
    room_indices = [
        int(value)
        for value in (patch.get("room_indices") or [])
        if isinstance(value, int)
    ]
    room_ids = [_room_key(room_index) for room_index in room_indices]
    room_index = room_indices[0] if len(room_indices) == 1 else None
    room_id = room_ids[0] if len(room_ids) == 1 else None
    part_ids = [str(value) for value in (patch.get("effective_part_ids") or []) if value]
    return {
        "id": f"renderable:exterior_roof:{patch.get('id')}",
        "category": "exterior_roof",
        "source_kind": "roof_coverage_patch",
        "source_id": patch.get("id"),
        "corners": corners,
        "part_id": part_id,
        "part_ids": part_ids or [part_id],
        "room_id": room_id,
        "room_index": room_index,
        "room_ids": room_ids,
        "room_indices": room_indices,
        "story": patch.get("story"),
        "roof_hypothesis_id": patch.get("roof_hypothesis_id"),
        "surface_kind": patch.get("surface_kind"),
        "coverage_subpart_id": patch.get("coverage_subpart_id"),
        "coverage_semantic_kind": patch.get("coverage_semantic_kind"),
        "continuation_source": patch.get("continuation_source"),
    }


def _fallback_unresolved_region_from_roof_surface(
    surface: dict[str, Any],
    *,
    part_id: str,
    surface_id: str,
) -> dict[str, Any] | None:
    polygon = _serialize_corners(surface.get("corners") or [])
    if len(polygon) < 3:
        return None
    room_index = surface.get("room_index")
    room_id = _room_key(room_index) if isinstance(room_index, int) else None
    polygon_xz = [[_round6(corner[0]), _round6(corner[2])] for corner in polygon if len(corner) >= 3]
    return {
        "id": f"unresolved-fallback-roof:{surface_id}",
        "room_id": room_id,
        "room_index": room_index,
        "story": surface.get("story", surface.get("dominant_story")),
        "effective_part_ids": [part_id],
        "polygon": polygon,
        "polygon_xz": polygon_xz,
        "roof_evidence_score": 0,
        "fallback_source_kind": "roof_surface_fallback",
        "roof_hypothesis_id": surface.get("roof_hypothesis_id"),
    }


def _room_summary_for_room_index(summary: dict[str, Any], room_index: int | None) -> dict[str, Any]:
    if not isinstance(room_index, int):
        return {}
    return ((summary.get("room_summaries") or {}).get(_room_key(room_index)) or {})


def _is_exact_flat_roof_surface(
    *,
    surface: dict[str, Any],
    summary: dict[str, Any],
) -> bool:
    if str(surface.get("surface_kind") or surface.get("kind") or "") != "flat":
        return False
    room_summary = _room_summary_for_room_index(summary, surface.get("room_index"))
    if not room_summary:
        return True
    if bool(room_summary.get("has_resolved_roof_relation")):
        return True
    return not any(
        [
            bool(room_summary.get("partially_covered_by_sloped_roof")),
            bool(room_summary.get("strong_perimeter_sloped")),
            bool(room_summary.get("strong_knee_wall_signal")),
            bool(room_summary.get("has_candidate_attic_relation")),
            bool(room_summary.get("has_candidate_upper_void_relation")),
            bool(room_summary.get("has_oblique_atom")),
            int(room_summary.get("roof_evidence_score", 0) or 0) >= 4,
        ]
    )


def _roof_surface_fallback_payload(
    *,
    roof: dict[str, Any] | None,
    summary: dict[str, Any],
    part_id: str,
    room_indices: set[int],
    exact_roof_room_indices: set[int],
    include_all_rooms: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    if roof is None:
        return [], [], 0, 0
    roof_surfaces = roof.get("roof_surfaces") or {}
    renderable: list[dict[str, Any]] = []
    unresolved_regions: list[dict[str, Any]] = []
    exact_flat_surface_count = 0
    coverage_patch_surface_count = 0
    patch_ids_by_hypothesis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for patch in (summary.get("oblique_coverage_patches") or []):
        if not isinstance(patch, dict):
            continue
        hypothesis_id = str(patch.get("roof_hypothesis_id") or "")
        if not hypothesis_id:
            continue
        patch_ids_by_hypothesis[hypothesis_id].append(patch)
    emitted_patch_ids: set[str] = set()
    for surface_kind in ("oblique", "flat"):
        for index, surface in enumerate(roof_surfaces.get(surface_kind) or []):
            if not isinstance(surface, dict):
                continue
            room_index = surface.get("room_index")
            matching_patches = []
            if surface_kind == "oblique":
                hypothesis_id = str(surface.get("roof_hypothesis_id") or "")
                for patch in patch_ids_by_hypothesis.get(hypothesis_id, []):
                    effective_part_ids = {
                        str(value)
                        for value in (patch.get("effective_part_ids") or [])
                        if value
                    }
                    patch_room_indices = {
                        int(value)
                        for value in (patch.get("room_indices") or [])
                        if isinstance(value, int)
                    }
                    if include_all_rooms:
                        matching_patches.append(patch)
                        continue
                    if part_id in effective_part_ids:
                        matching_patches.append(patch)
                        continue
                    if patch_room_indices and patch_room_indices.intersection(room_indices):
                        matching_patches.append(patch)
            if isinstance(room_index, int):
                if not include_all_rooms and room_index not in room_indices:
                    continue
                if room_index in exact_roof_room_indices:
                    continue
            elif not include_all_rooms:
                if matching_patches:
                    for patch in matching_patches:
                        patch_id = str(patch.get("id") or "")
                        if not patch_id or patch_id in emitted_patch_ids:
                            continue
                        renderable_patch = _renderable_surface_from_coverage_patch(
                            patch,
                            part_id=part_id,
                        )
                        if renderable_patch is None:
                            continue
                        renderable.append(renderable_patch)
                        emitted_patch_ids.add(patch_id)
                        coverage_patch_surface_count += 1
                continue
            if matching_patches and not isinstance(room_index, int):
                for patch in matching_patches:
                    patch_id = str(patch.get("id") or "")
                    if not patch_id or patch_id in emitted_patch_ids:
                        continue
                    renderable_patch = _renderable_surface_from_coverage_patch(
                        patch,
                        part_id=part_id,
                    )
                    if renderable_patch is None:
                        continue
                    renderable.append(renderable_patch)
                    emitted_patch_ids.add(patch_id)
                    coverage_patch_surface_count += 1
                continue
            surface_id = str(
                surface.get("boundary_face_id")
                or surface.get("roof_hypothesis_id")
                or f"{surface_kind}:{index}"
            )
            source_kind = "roof_surface_fallback"
            emit_unresolved = True
            if _is_exact_flat_roof_surface(surface=surface, summary=summary):
                source_kind = "roof_surface_exact_flat"
                emit_unresolved = False
                exact_flat_surface_count += 1
            fallback_surface = _renderable_surface_from_roof_surface(
                surface,
                part_id=part_id,
                surface_id=surface_id,
                source_kind=source_kind,
            )
            if fallback_surface is None:
                continue
            renderable.append(fallback_surface)
            if emit_unresolved:
                unresolved = _fallback_unresolved_region_from_roof_surface(
                    surface,
                    part_id=part_id,
                    surface_id=surface_id,
                )
                if unresolved is not None:
                    unresolved_regions.append(unresolved)
    return renderable, unresolved_regions, exact_flat_surface_count, coverage_patch_surface_count


def _part_unresolved_regions(
    *,
    summary: dict[str, Any],
    part_id: str,
    room_indices: set[int],
    include_all_rooms: bool,
) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for region in (summary.get("unresolved_regions") or []):
        if not isinstance(region, dict):
            continue
        effective_part_ids = {str(value) for value in (region.get("effective_part_ids") or []) if value}
        room_index = region.get("room_index")
        if include_all_rooms:
            regions.append(dict(region))
            continue
        if part_id in effective_part_ids:
            regions.append(dict(region))
            continue
        if isinstance(room_index, int) and room_index in room_indices:
            regions.append(dict(region))
    return regions


def _renderable_surface_from_roof_face(face: dict[str, Any], cell: dict[str, Any], part_id: str) -> dict[str, Any] | None:
    corners = face.get("corners") or []
    if not isinstance(corners, list) or len(corners) < 3:
        return None
    if str(face.get("role") or "") != "roof":
        return None
    return {
        "id": f"renderable:exterior_roof:{cell.get('id')}:{face.get('id') or face.get('kind') or 'face'}",
        "category": "exterior_roof",
        "source_kind": "roof_cell_face",
        "source_id": face.get("id") or face.get("kind") or "face",
        "cell_id": cell.get("id"),
        "cell_kind": cell.get("cell_kind"),
        "corners": corners,
        "part_id": part_id,
        "room_id": cell.get("room_id"),
        "room_index": cell.get("room_index"),
        "story": cell.get("story"),
        "roof_hypothesis_id": cell.get("roof_hypothesis_id") or (face.get("metadata") or {}).get("roof_hypothesis_id"),
    }


def _renderable_surface_from_knee_wall(wall: dict[str, Any], part_id: str) -> dict[str, Any] | None:
    corners = wall.get("corners") or []
    if not isinstance(corners, list) or len(corners) < 3:
        return None
    return {
        "id": f"renderable:knee_wall:{wall.get('id')}",
        "category": "knee_wall",
        "source_kind": "knee_wall",
        "source_id": wall.get("id"),
        "corners": corners,
        "part_id": part_id,
        "room_id": wall.get("room_id"),
        "room_index": wall.get("room_index"),
        "story": wall.get("story"),
    }


def _surface_category_counts(surfaces: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for surface in surfaces:
        category = str(surface.get("category") or "")
        if category:
            counts[category] += 1
    return dict(sorted(counts.items()))


def _topology_cell_polygon(cell: dict[str, Any]) -> Polygon | None:
    footprint = ((cell.get("properties") or {}).get("xz_footprint") or [])
    if not isinstance(footprint, list) or len(footprint) < 3:
        return None
    coords: list[tuple[float, float]] = []
    for point in footprint:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        coords.append((_round6(point[0]), _round6(point[1])))
    if len(coords) < 3:
        return None
    poly = Polygon(coords)
    if not poly.is_valid:
        try:
            poly = make_valid(poly)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda geom: geom.area, default=None)
        except Exception:
            return None
    if poly is None or poly.is_empty or not isinstance(poly, Polygon) or poly.area <= 1e-6:
        return None
    return poly


def _topology_story_unions(cells: list[dict[str, Any]]) -> dict[int, Polygon]:
    polys_by_story: dict[int, list[Polygon]] = defaultdict(list)
    for cell in cells:
        if str(cell.get("kind") or "") != "room":
            continue
        story = cell.get("story")
        if not isinstance(story, int):
            continue
        poly = _topology_cell_polygon(cell)
        if poly is not None:
            polys_by_story[story].append(poly)
    unions: dict[int, Polygon] = {}
    for story, polys in polys_by_story.items():
        if not polys:
            continue
        try:
            merged = unary_union(polys)
            merged = _largest_polygon(merged)
        except Exception:
            merged = None
        if merged is not None:
            unions[story] = merged
    return unions


def _face_corners(face: dict[str, Any]) -> list[list[float]]:
    vertices = face.get("corners") or face.get("vertices") or []
    corners: list[list[float]] = []
    for vertex in vertices:
        if isinstance(vertex, (list, tuple)) and len(vertex) >= 3:
            corners.append([_round6(vertex[0]), _round6(vertex[1]), _round6(vertex[2])])
    return corners


def _wall_face_xz_edge(face: dict[str, Any]) -> LineString | None:
    corners = _face_corners(face)
    unique: list[tuple[float, float]] = []
    for corner in corners:
        xz = (_round6(corner[0]), _round6(corner[2]))
        if xz not in unique:
            unique.append(xz)
    if len(unique) < 2:
        return None
    line = LineString([unique[0], unique[1]])
    return line if line.length > 1e-6 else None


def _is_exterior_wall_face(face: dict[str, Any], story_union: Polygon | None) -> bool:
    metadata = face.get("metadata") or {}
    if bool(metadata.get("perimeter_facing")):
        return True
    if story_union is None:
        return False
    wall_edge = _wall_face_xz_edge(face)
    if wall_edge is None:
        return False
    try:
        overlap = wall_edge.intersection(story_union.boundary)
    except Exception:
        return False
    return not overlap.is_empty and float(getattr(overlap, "length", 0.0)) > 1e-6


def _renderable_surface_from_topology_face(
    face: dict[str, Any],
    cell: dict[str, Any],
    *,
    part_id: str,
    is_exterior_wall: bool,
    include_ceiling: bool,
) -> dict[str, Any] | None:
    if str(cell.get("kind") or "") != "room":
        return None
    corners = _face_corners(face)
    if len(corners) < 3:
        return None
    metadata = face.get("metadata") or {}
    role = str(face.get("role") or "")
    face_kind = str(metadata.get("face_kind") or face.get("boundary_kind") or "")
    category: str | None = None
    if face_kind == "bottom":
        category = "occupied_room_floor"
    elif face_kind == "top":
        if include_ceiling:
            category = "occupied_room_ceiling"
    elif role == "wall":
        category = "exterior_wall" if is_exterior_wall else "occupied_room_wall"
    if category is None:
        return None
    return {
        "id": f"renderable:{category}:{cell.get('id')}:{face.get('id') or face_kind or role}",
        "category": category,
        "source_kind": "topology_room_face",
        "source_id": face.get("id") or face_kind or role,
        "cell_id": cell.get("id"),
        "corners": corners,
        "part_id": part_id,
        "room_id": cell.get("source_id"),
        "story": cell.get("story"),
        "face_kind": face_kind,
        "role": role,
    }


def _build_ontology_summary(
    *,
    uuid: str,
    roof: dict[str, Any],
    topology_cell_complex: dict[str, Any],
    building: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, set[str]]]:
    building_part_graph = roof.get("building_part_graph") or {}
    roof_coverage_graph = roof.get("roof_coverage_graph") or {}
    top_boundary_graph = roof.get("top_boundary_graph") or {}
    roof_evidence_graph = roof.get("roof_evidence_graph") or {}
    roof_cell_complex = roof.get("roof_cell_complex") or {}
    roof_surfaces = roof.get("roof_surfaces") or {}
    room_partitions = ((roof.get("ceiling_partitions") or {}).get("room_partitions") or [])
    dormers = roof.get("dormers") or []

    partition_by_id: dict[str, dict[str, Any]] = {}
    graph_room_by_room_id: dict[str, str] = {}
    room_partition_polys: dict[str, list[Polygon]] = defaultdict(list)
    room_partition_tops: dict[str, list[float]] = defaultdict(list)
    room_partition_count: dict[str, int] = defaultdict(int)
    room_indices_by_room_id: dict[str, int] = {}

    for room_partition in room_partitions:
        room_index = int(room_partition.get("room_index", 0))
        room_id = _room_key(room_index)
        room_indices_by_room_id[room_id] = room_index
        graph_room_id = room_partition.get("graph_room_id")
        if isinstance(graph_room_id, str) and graph_room_id:
            graph_room_by_room_id[room_id] = graph_room_id
        for partition in (room_partition.get("partitions") or []):
            if not isinstance(partition, dict):
                continue
            atom_id = str(partition.get("id") or "")
            if atom_id:
                partition_by_id[atom_id] = partition
            poly = _poly_xz_from_3d(partition.get("poly") or [])
            if poly is not None:
                room_partition_polys[room_id].append(poly)
            top_y = partition.get("top_y_m")
            if isinstance(top_y, (int, float)):
                room_partition_tops[room_id].append(float(top_y))
            room_partition_count[room_id] += 1

    semantic_atoms: list[dict[str, Any]] = []
    atoms_by_id: dict[str, dict[str, Any]] = {}
    unassigned_room_ids: set[str] = set()
    for node in (top_boundary_graph.get("nodes") or []):
        if not isinstance(node, dict) or node.get("type") != "TopBoundaryAtom":
            continue
        atom_id = str(node.get("id") or "")
        partition = partition_by_id.get(atom_id) or {}
        part_id = node.get("part_id")
        effective_part_id = str(part_id) if part_id else UNASSIGNED_PART_ID
        if not part_id and node.get("room_id"):
            unassigned_room_ids.add(str(node["room_id"]))
        record = dict(node)
        record["effective_part_id"] = effective_part_id
        record["poly"] = partition.get("poly") or []
        record["top_y_m"] = partition.get("top_y_m")
        record["supporting_roof_hypothesis_ids"] = list(partition.get("supporting_roof_hypothesis_ids") or [])
        record["flat_role_reason"] = partition.get("flat_role_reason")
        semantic_atoms.append(record)
        atoms_by_id[atom_id] = record

    part_nodes = [dict(node) for node in (building_part_graph.get("nodes") or []) if isinstance(node, dict)]
    part_room_ids: dict[str, set[str]] = {
        str(node["id"]): set(str(room_id) for room_id in (node.get("room_ids") or []))
        for node in part_nodes
        if node.get("id")
    }

    for cell in (roof_cell_complex.get("cells") or []):
        if not isinstance(cell, dict):
            continue
        part_id = cell.get("part_id")
        room_id = cell.get("room_id")
        if not part_id and room_id:
            unassigned_room_ids.add(str(room_id))

    for knee_wall in (roof_cell_complex.get("knee_walls") or []):
        if not isinstance(knee_wall, dict):
            continue
        part_id = knee_wall.get("part_id")
        room_index = knee_wall.get("room_index")
        if not part_id and isinstance(room_index, int):
            unassigned_room_ids.add(_room_key(room_index))

    coverage_part_ids: dict[str, set[str]] = {}
    atom_subpart_membership = roof_coverage_graph.get("atom_subpart_membership") or {}
    room_membership = building_part_graph.get("room_membership") or {}
    for subpart in (roof_coverage_graph.get("subparts") or []):
        if not isinstance(subpart, dict):
            continue
        subpart_id = str(subpart.get("id") or "")
        part_ids = {str(value) for value in (subpart.get("part_ids") or []) if value}
        if not part_ids:
            room_indices = [int(v) for v in (subpart.get("room_indices") or []) if isinstance(v, int)]
            for room_index in room_indices:
                part_ids.update(str(part_id) for part_id in (room_membership.get(_room_key(room_index)) or []))
            if not part_ids:
                for atom_id, subpart_ids in atom_subpart_membership.items():
                    if subpart_id not in [str(value) for value in (subpart_ids or [])]:
                        continue
                    atom = atoms_by_id.get(str(atom_id))
                    if atom is None:
                        continue
                    part_ids.add(str(atom.get("effective_part_id") or UNASSIGNED_PART_ID))
        if not part_ids:
            part_ids = {UNASSIGNED_PART_ID}
        coverage_part_ids[subpart_id] = part_ids

    building_parts: list[dict[str, Any]] = []
    part_graph_room_ids: dict[str, set[str]] = {}
    for node in part_nodes:
        part_id = str(node["id"])
        room_ids = part_room_ids.get(part_id, set())
        part_graph_room_ids[part_id] = {
            graph_room_by_room_id[room_id]
            for room_id in room_ids
            if graph_room_by_room_id.get(room_id)
        }
        room_polys = room_partition_polys.get(next(iter(room_ids), ""), [])
        polys: list[Polygon] = []
        top_values: list[float] = []
        for room_id in sorted(room_ids):
            polys.extend(room_partition_polys.get(room_id, []))
            top_values.extend(room_partition_tops.get(room_id, []))
        union_poly = _largest_polygon(unary_union(polys)) if polys else None
        avg_top_y = sum(top_values) / len(top_values) if top_values else 0.0
        polygon_xz = _serialize_poly_xz(union_poly)
        building_parts.append(
            {
                **node,
                "effective_part_id": part_id,
                "room_indices": _room_indices_for_ids(room_ids, room_indices_by_room_id),
                "polygon_xz": polygon_xz,
                "polygon": _polygon_xz_to_3d(polygon_xz, avg_top_y) if polygon_xz else [],
                "bbox_xz": _bbox_xz(union_poly),
                "centroid_xz": _centroid_xz(union_poly),
                "area_m2": _round6(union_poly.area if isinstance(union_poly, Polygon) else 0.0),
                "top_y_m": _round6(avg_top_y) if top_values else None,
            }
        )

    if unassigned_room_ids:
        polys: list[Polygon] = []
        top_values: list[float] = []
        for room_id in sorted(unassigned_room_ids):
            polys.extend(room_partition_polys.get(room_id, []))
            top_values.extend(room_partition_tops.get(room_id, []))
        union_poly = _largest_polygon(unary_union(polys)) if polys else None
        avg_top_y = sum(top_values) / len(top_values) if top_values else 0.0
        polygon_xz = _serialize_poly_xz(union_poly)
        part_graph_room_ids[UNASSIGNED_PART_ID] = {
            graph_room_by_room_id[room_id]
            for room_id in unassigned_room_ids
            if graph_room_by_room_id.get(room_id)
        }
        building_parts.append(
            {
                "id": UNASSIGNED_PART_ID,
                "type": "BuildingPart",
                "effective_part_id": UNASSIGNED_PART_ID,
                "room_ids": sorted(unassigned_room_ids),
                "room_indices": _room_indices_for_ids(unassigned_room_ids, room_indices_by_room_id),
                "hypothesis_ids": [],
                "oblique_hypothesis_ids": [],
                "flat_hypothesis_ids": [],
                "articulation_room_ids": [],
                "roof_family_guess": "unassigned",
                "polygon_xz": polygon_xz,
                "polygon": _polygon_xz_to_3d(polygon_xz, avg_top_y) if polygon_xz else [],
                "bbox_xz": _bbox_xz(union_poly),
                "centroid_xz": _centroid_xz(union_poly),
                "area_m2": _round6(union_poly.area if isinstance(union_poly, Polygon) else 0.0),
                "top_y_m": _round6(avg_top_y) if top_values else None,
                "synthetic": True,
            }
        )

    if building is not None:
        all_room_indices = list(range(len(building.get("rooms") or [])))
        all_room_ids = {_room_key(room_index) for room_index in all_room_indices}
        all_room_polys = [
            poly
            for room_index in all_room_indices
            for poly in [_poly_xz_from_3d((building.get("rooms") or [])[room_index].get("floor_polygon") or [])]
            if poly is not None
        ]
        full_union = _largest_polygon(unary_union(all_room_polys)) if all_room_polys else None
        polygon_xz = _serialize_poly_xz(full_union)
        all_top_values = [
            float(value)
            for values in room_partition_tops.values()
            for value in values
            if isinstance(value, (int, float))
        ]
        avg_top_y = sum(all_top_values) / len(all_top_values) if all_top_values else 0.0
        part_graph_room_ids[FULL_BUILDING_PART_ID] = set(part_graph_room_ids.get(FULL_BUILDING_PART_ID) or set())
        part_graph_room_ids[FULL_BUILDING_PART_ID].update(
            {
                source_id
                for cell in (topology_cell_complex.get("cells") or [])
                if isinstance(cell, dict)
                and str(cell.get("kind") or "") == "room"
                and isinstance((source_id := cell.get("source_id")), str)
                and source_id
            }
        )
        building_parts.append(
            {
                "id": FULL_BUILDING_PART_ID,
                "type": "BuildingPart",
                "effective_part_id": FULL_BUILDING_PART_ID,
                "room_ids": sorted(all_room_ids),
                "room_indices": all_room_indices,
                "hypothesis_ids": [],
                "oblique_hypothesis_ids": [],
                "flat_hypothesis_ids": [],
                "articulation_room_ids": [],
                "roof_family_guess": "full_building",
                "polygon_xz": polygon_xz,
                "polygon": _polygon_xz_to_3d(polygon_xz, avg_top_y) if polygon_xz else [],
                "bbox_xz": _bbox_xz(full_union),
                "centroid_xz": _centroid_xz(full_union),
                "area_m2": _round6(full_union.area if isinstance(full_union, Polygon) else 0.0),
                "top_y_m": _round6(avg_top_y) if all_top_values else None,
                "synthetic": True,
                "synthetic_role": "full_building",
            }
        )

    building_parts.sort(
        key=lambda part: (
            0 if part.get("synthetic_role") == "full_building" else 1,
            1 if part.get("synthetic") else 0,
            -float(part.get("area_m2", 0.0) or 0.0),
            str(part.get("id") or ""),
        )
    )

    coverage_subparts: list[dict[str, Any]] = []
    room_subpart_membership = roof_coverage_graph.get("room_subpart_membership") or {}
    atom_tops_by_subpart: dict[str, list[float]] = defaultdict(list)
    for atom_id, subpart_ids in atom_subpart_membership.items():
        atom = atoms_by_id.get(str(atom_id))
        if atom is None:
            continue
        top_y = atom.get("top_y_m")
        if not isinstance(top_y, (int, float)):
            continue
        for subpart_id in (subpart_ids or []):
            atom_tops_by_subpart[str(subpart_id)].append(float(top_y))
    for subpart in (roof_coverage_graph.get("subparts") or []):
        if not isinstance(subpart, dict):
            continue
        subpart_id = str(subpart.get("id") or "")
        polygon_xz = [
            [_round6(point[0]), _round6(point[1])]
            for point in (subpart.get("polygon_xz") or [])
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
        top_values = list(atom_tops_by_subpart.get(subpart_id, []))
        if not top_values:
            for room_index in [int(v) for v in (subpart.get("room_indices") or []) if isinstance(v, int)]:
                top_values.extend(room_partition_tops.get(_room_key(room_index), []))
        top_y = sum(top_values) / len(top_values) if top_values else 0.0
        coverage_subparts.append(
            {
                **subpart,
                "effective_part_ids": sorted(coverage_part_ids.get(subpart_id, {UNASSIGNED_PART_ID})),
                "polygon": _polygon_xz_to_3d(polygon_xz, top_y) if polygon_xz else [],
                "top_y_m": _round6(top_y) if top_values else None,
            }
        )

    subparts_by_hypothesis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for subpart in coverage_subparts:
        hypothesis_id = str(subpart.get("roof_hypothesis_id") or "")
        if hypothesis_id:
            subparts_by_hypothesis[hypothesis_id].append(subpart)

    oblique_coverage_patches: list[dict[str, Any]] = []
    hypothesis_membership = building_part_graph.get("hypothesis_membership") or {}
    for index, surface in enumerate(roof_surfaces.get("oblique") or []):
        if not isinstance(surface, dict):
            continue
        hypothesis_id = str(surface.get("roof_hypothesis_id") or f"roof-hypothesis:oblique:{index}")
        surface_poly = _poly_xz_from_3d(surface.get("corners") or [])
        if surface_poly is None:
            continue
        matching_subparts = subparts_by_hypothesis.get(hypothesis_id) or []
        if not matching_subparts:
            continue
        for subpart in matching_subparts:
            subpart_poly = Polygon(subpart.get("polygon_xz") or [])
            if subpart_poly.is_empty:
                continue
            try:
                clipped = surface_poly.intersection(subpart_poly)
            except Exception:
                continue
            for piece_index, piece in enumerate(_decompose_polygons(clipped)):
                if piece.is_empty or piece.area <= 1e-6:
                    continue
                effective_part_ids = list(subpart.get("effective_part_ids") or [])
                if not effective_part_ids:
                    effective_part_ids = [
                        str(part_id)
                        for part_id in (hypothesis_membership.get(hypothesis_id) or [])
                    ] or [UNASSIGNED_PART_ID]
                room_indices = [
                    int(value)
                    for value in (subpart.get("room_indices") or [])
                    if isinstance(value, int)
                ]
                oblique_coverage_patches.append(
                    {
                        "id": f"roof-coverage-patch:{hypothesis_id}:{subpart.get('id')}:{piece_index}",
                        "roof_hypothesis_id": hypothesis_id,
                        "coverage_subpart_id": subpart.get("id"),
                        "effective_part_ids": effective_part_ids,
                        "room_indices": room_indices,
                        "room_ids": [_room_key(room_index) for room_index in room_indices],
                        "polygon": _lift_poly_on_surface(piece, surface),
                        "polygon_xz": _serialize_poly_xz(piece),
                        "surface_kind": "oblique",
                        "story": surface.get("story", surface.get("dominant_story")),
                        "coverage_semantic_kind": subpart.get("semantic_kind"),
                        "continuation_source": surface.get("continuation_source"),
                    }
                )

    unresolved_regions: list[dict[str, Any]] = []
    room_summaries = top_boundary_graph.get("room_summaries") or {}
    for room_id, room_summary in room_summaries.items():
        if not isinstance(room_summary, dict):
            continue
        has_resolved = bool(room_summary.get("has_resolved_roof_relation"))
        if not has_resolved:
            has_resolved = bool(room_summary.get("has_attic_relation") or room_summary.get("has_upper_void_relation") or room_summary.get("has_oblique_atom"))
        should_be_covered = bool(
            room_summary.get("partially_covered_by_sloped_roof")
            or room_summary.get("strong_perimeter_sloped")
            or room_summary.get("strong_knee_wall_signal")
            or room_summary.get("has_candidate_attic_relation")
            or room_summary.get("has_candidate_upper_void_relation")
            or int(room_summary.get("roof_evidence_score", 0) or 0) >= 4
        )
        if has_resolved or not should_be_covered:
            continue
        polys = room_partition_polys.get(str(room_id), [])
        union_poly = _largest_polygon(unary_union(polys)) if polys else None
        if union_poly is None:
            continue
        polygon_xz = _serialize_poly_xz(union_poly)
        top_values = room_partition_tops.get(str(room_id), [])
        top_y = sum(top_values) / len(top_values) if top_values else 0.0
        unresolved_regions.append(
            {
                "id": f"unresolved-coverage:{room_id}",
                "room_id": room_id,
                "room_index": room_summary.get("room_index"),
                "story": room_summary.get("story"),
                "effective_part_ids": list(room_summary.get("part_ids") or [UNASSIGNED_PART_ID]),
                "polygon": _polygon_xz_to_3d(polygon_xz, top_y) if polygon_xz else [],
                "polygon_xz": polygon_xz,
                "slant_delta_m": room_summary.get("slant_delta_m"),
                "roof_evidence_score": room_summary.get("roof_evidence_score"),
                "has_candidate_attic_relation": bool(room_summary.get("has_candidate_attic_relation")),
                "has_candidate_upper_void_relation": bool(room_summary.get("has_candidate_upper_void_relation")),
            }
        )

    for dormer in dormers:
        if not isinstance(dormer, dict):
            continue
        room_index = dormer.get("room_index")
        room_id = _room_key(room_index) if isinstance(room_index, int) else None
        effective_part_ids = []
        if room_id is not None:
            effective_part_ids = [
                str(part_id)
                for part_id in (room_membership.get(room_id) or [])
            ] or ([UNASSIGNED_PART_ID] if room_id in unassigned_room_ids else [])
        dormer["effective_part_ids"] = effective_part_ids

    renderable_surfaces = [
        surface
        for surface in (
            _renderable_surface_from_atom(atom)
            for atom in semantic_atoms
        )
        if surface is not None
    ]
    renderable_surfaces.extend(
        surface
        for surface in (
            _renderable_surface_from_unresolved_region(region)
            for region in unresolved_regions
        )
        if surface is not None
    )
    renderable_surface_counts = _surface_category_counts(renderable_surfaces)

    summary = {
        "uuid": uuid,
        "view": "summary",
        "building_parts": building_parts,
        "coverage_subparts": coverage_subparts,
        "oblique_coverage_patches": oblique_coverage_patches,
        "semantic_atoms": semantic_atoms,
        "unresolved_regions": unresolved_regions,
        "renderable_surfaces": renderable_surfaces,
        "room_summaries": top_boundary_graph.get("room_summaries") or {},
        "building_part_graph": building_part_graph,
        "roof_coverage_metadata": roof_coverage_graph.get("metadata") or {},
        "top_boundary_metadata": top_boundary_graph.get("metadata") or {},
        "roof_evidence_metadata": roof_evidence_graph.get("metadata") or {},
        "dormers": dormers,
        "metadata": {
            "building_part_count": len(building_parts),
            "semantic_atom_count": len(semantic_atoms),
            "coverage_subpart_count": len(coverage_subparts),
            "oblique_coverage_patch_count": len(oblique_coverage_patches),
            "unresolved_region_count": len(unresolved_regions),
            "renderable_surface_count": len(renderable_surfaces),
            "renderable_surface_counts": renderable_surface_counts,
            "dormer_count": len(dormers),
            "topology_room_cell_count": len(
                [cell for cell in (topology_cell_complex.get("cells") or []) if cell.get("kind") == "room"]
            ),
            "roof_exact_cell_count": len(roof_cell_complex.get("cells") or []),
            "occupied_room_cell_count": len(((roof.get("occupied_room_cell_complex") or {}).get("cells") or [])),
            "knee_wall_count": len(roof_cell_complex.get("knee_walls") or []),
        },
    }
    return summary, part_graph_room_ids


def _build_ontology_part_payloads(
    *,
    uuid: str,
    summary: dict[str, Any],
    part_graph_room_ids: dict[str, set[str]],
    topology_cell_complex: dict[str, Any],
    roof_cell_complex: dict[str, Any],
    occupied_room_cell_complex: dict[str, Any] | None = None,
    building: dict[str, Any] | None = None,
    roof: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    part_details: dict[str, dict[str, Any]] = {}
    part_summaries = {
        str(part["id"]): part
        for part in (summary.get("building_parts") or [])
        if isinstance(part, dict) and part.get("id")
    }
    dormers = summary.get("dormers") or []
    topology_room_cells = [
        cell
        for cell in (topology_cell_complex.get("cells") or [])
        if isinstance(cell, dict) and str(cell.get("kind") or "") == "room"
    ]
    topology_room_unions = _topology_story_unions(topology_room_cells)
    room_to_part_id: dict[str, str] = {}
    part_ids_by_room_index: dict[int, str] = {}
    for mapped_part_id, room_ids in part_graph_room_ids.items():
        for room_id in room_ids:
            room_to_part_id.setdefault(str(room_id), str(mapped_part_id))
    top_graph_room_ids = set(room_to_part_id.keys())
    for part in (summary.get("building_parts") or []):
        if not isinstance(part, dict):
            continue
        if str(part.get("synthetic_role") or "") == "full_building":
            continue
        part_id = str(part.get("id") or "")
        if not part_id:
            continue
        for room_index in (part.get("room_indices") or []):
            if isinstance(room_index, int):
                part_ids_by_room_index.setdefault(room_index, part_id)
    for cell in topology_room_cells:
        source_id = str(cell.get("source_id") or "")
        if source_id in room_to_part_id:
            continue
        room_index = _parse_topology_room_index(source_id)
        if room_index is None:
            continue
        fallback_part_id = part_ids_by_room_index.get(room_index)
        if fallback_part_id:
            room_to_part_id[source_id] = fallback_part_id

    for part_id, part in part_summaries.items():
        room_indices = {
            int(value)
            for value in (part.get("room_indices") or [])
            if isinstance(value, int)
        }
        include_all_rooms = str(part.get("synthetic_role") or "") == "full_building"
        unresolved_regions = _part_unresolved_regions(
            summary=summary,
            part_id=part_id,
            room_indices=room_indices,
            include_all_rooms=include_all_rooms,
        )
        roof_cells = [
            cell
            for cell in (roof_cell_complex.get("cells") or [])
            if isinstance(cell, dict)
            and (
                include_all_rooms
                or (
                str(cell.get("part_id") or "") == part_id
                or cell.get("room_id") in set(part.get("room_ids") or [])
                or (
                    part_id == UNASSIGNED_PART_ID
                    and not cell.get("part_id")
                )
                )
            )
        ]
        filtered_roof_cells: list[dict[str, Any]] = []
        renderable_surfaces: list[dict[str, Any]] = []
        exact_roof_room_indices: set[int] = set()
        topology_cells = [
            cell
            for cell in topology_room_cells
            if (
                str(room_to_part_id.get(str(cell.get("source_id") or ""), UNASSIGNED_PART_ID)) == part_id
                or (
                    part_id == UNASSIGNED_PART_ID
                    and str(cell.get("source_id") or "") not in room_to_part_id
                )
            )
        ]
        for cell in roof_cells:
            viewer_faces = []
            for face in (cell.get("faces") or []):
                if not isinstance(face, dict):
                    continue
                role = str(face.get("role") or "")
                perimeter_facing = bool((face.get("metadata") or {}).get("perimeter_facing"))
                if role in {"roof", "slab"}:
                    viewer_faces.append(face)
                elif role == "wall" and perimeter_facing:
                    viewer_faces.append(face)
                renderable = _renderable_surface_from_roof_face(face, cell, part_id)
                if renderable is not None:
                    renderable_surfaces.append(renderable)
                    room_index = cell.get("room_index")
                    if isinstance(room_index, int):
                        exact_roof_room_indices.add(room_index)
            if not viewer_faces:
                continue
            filtered = dict(cell)
            filtered["faces"] = viewer_faces
            filtered_roof_cells.append(filtered)
        knee_walls = [
            wall
            for wall in (roof_cell_complex.get("knee_walls") or [])
            if isinstance(wall, dict)
            and (
                include_all_rooms
                or (
                str(wall.get("part_id") or "") == part_id
                or (
                    isinstance(wall.get("room_index"), int)
                    and wall.get("room_index") in room_indices
                )
                or (
                    part_id == UNASSIGNED_PART_ID
                    and not wall.get("part_id")
                )
                )
            )
        ]
        renderable_surfaces.extend(
            surface
            for surface in (
                _renderable_surface_from_knee_wall(wall, part_id)
                for wall in knee_walls
            )
            if surface is not None
        )
        occupied_renderable_surfaces = _renderable_surfaces_from_occupied_room_cells(
            occupied_room_cell_complex=occupied_room_cell_complex,
            building=building,
            room_indices=room_indices,
            part_id=part_id,
        )
        if occupied_renderable_surfaces:
            renderable_surfaces.extend(occupied_renderable_surfaces)
        else:
            renderable_surfaces.extend(
                _renderable_base_room_surfaces(
                    building=building,
                    roof=roof,
                    room_indices=room_indices,
                    primary_part_id_by_room_index=part_ids_by_room_index,
                    part_id=part_id,
                )
            )
        (
            fallback_roof_surfaces,
            fallback_unresolved_regions,
            exact_flat_surface_count,
            coverage_patch_surface_count,
        ) = _roof_surface_fallback_payload(
            roof=roof,
            summary=summary,
            part_id=part_id,
            room_indices=room_indices,
            exact_roof_room_indices=exact_roof_room_indices,
            include_all_rooms=include_all_rooms,
        )
        renderable_surfaces.extend(fallback_roof_surfaces)
        unresolved_regions.extend(fallback_unresolved_regions)
        roof_fallback_surface_count = sum(
            1
            for surface in fallback_roof_surfaces
            if str(surface.get("source_kind") or "") == "roof_surface_fallback"
        )
        if building is None or roof is None:
            for cell in topology_cells:
                story_union = topology_room_unions.get(cell.get("story")) if isinstance(cell.get("story"), int) else None
                include_ceiling = str(cell.get("source_id") or "") not in top_graph_room_ids
                for face in (cell.get("faces") or []):
                    if not isinstance(face, dict):
                        continue
                    renderable = _renderable_surface_from_topology_face(
                        face,
                        cell,
                        part_id=part_id,
                        is_exterior_wall=_is_exterior_wall_face(face, story_union),
                        include_ceiling=include_ceiling,
                    )
                    if renderable is not None:
                        renderable_surfaces.append(renderable)
        unresolved_renderable_surfaces = [
            surface
            for surface in (
                _renderable_surface_from_unresolved_region(region)
                for region in unresolved_regions
            )
            if surface is not None
        ]
        renderable_surfaces.extend(unresolved_renderable_surfaces)
        renderable_surface_counts = _surface_category_counts(renderable_surfaces)
        dormer_subset = _filter_part_dormers(dormers, room_indices)
        part_details[part_id] = {
            "uuid": uuid,
            "view": "part",
            "part_id": part_id,
            "part_summary": part,
            "roof_cells": filtered_roof_cells,
            "knee_walls": knee_walls,
            "unresolved_regions": unresolved_regions,
            "renderable_surfaces": renderable_surfaces,
            "dormers": dormer_subset,
            "metadata": {
                "roof_cell_count": len(filtered_roof_cells),
                "attic_cell_count": sum(1 for cell in filtered_roof_cells if cell.get("cell_kind") == "attic"),
                "upper_void_cell_count": sum(1 for cell in filtered_roof_cells if cell.get("cell_kind") == "upper_void"),
                "knee_wall_count": len(knee_walls),
                "occupied_room_cell_count": sum(
                    1
                    for cell in ((occupied_room_cell_complex or {}).get("cells") or [])
                    if isinstance(cell, dict)
                    and (
                        include_all_rooms
                        or (
                            isinstance(cell.get("room_index"), int)
                            and cell.get("room_index") in room_indices
                        )
                    )
                ),
                "roof_exact_flat_surface_count": exact_flat_surface_count,
                "roof_coverage_patch_surface_count": coverage_patch_surface_count,
                "roof_fallback_surface_count": roof_fallback_surface_count,
                "unresolved_region_count": len(unresolved_regions),
                "renderable_surface_count": len(renderable_surfaces),
                "renderable_surface_counts": renderable_surface_counts,
                "dormer_count": len(dormer_subset),
            },
        }
    return part_details


def _build_ontology_cache_entry(uuid: str) -> dict[str, Any]:
    merged_path = PIPELINE_ROOT / uuid / "merged.json"
    if not merged_path.exists():
        raise FileNotFoundError(f"No merged.json for {uuid}")
    graph = build_topology_graph(
        merged_path=merged_path,
        scan_dir=SCAN_CACHE_ROOT,
        uuid=uuid,
    )
    building = extract_building(
        uuid=uuid,
        pipeline_dir=PIPELINE_ROOT,
        scan_cache_root=SCAN_CACHE_ROOT,
        load_topology_graph=False,
    )
    if not building:
        raise RuntimeError(f"extract_building returned no building for {uuid}")
    roof = run_roof_algorithms(building, graph=graph)
    topology_cell_complex = (graph.geometry_index or {}).get("cell_complex") or {}
    summary, part_graph_room_ids = _build_ontology_summary(
        uuid=uuid,
        roof=roof,
        topology_cell_complex=topology_cell_complex,
        building=building,
    )
    parts = _build_ontology_part_payloads(
        uuid=uuid,
        summary=summary,
        part_graph_room_ids=part_graph_room_ids,
        topology_cell_complex=topology_cell_complex,
        roof_cell_complex=roof.get("roof_cell_complex") or {},
        occupied_room_cell_complex=roof.get("occupied_room_cell_complex") or {},
        building=building,
        roof=roof,
    )
    return {
        "summary": summary,
        "parts": parts,
    }


def resolve_datafordeleren_api_key():
    env_key = os.environ.get("DATAFORDELEREN_API_KEY")
    if env_key:
        return env_key

    # Fallback: fetch from Secret Manager using local gcloud auth.
    try:
        out = subprocess.check_output(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                "latest",
                f"--secret={SECRET_NAME}",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
        ).strip()
        return out or None
    except Exception:
        return None


class ViewerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        if directory is None:
            directory = str(ROOT_DIR)
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/ortofoto":
            self._handle_ortofoto(parsed.query)
            return
        if parsed.path == "/ontology-artifacts":
            self._handle_ontology_artifacts(parsed.query)
            return
        if parsed.path == "/alignment-calibration":
            self._handle_calibration_get()
            return

        if parsed.path == "/":
            self.path = "/viewer.html"
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/alignment-calibration":
            self._handle_calibration_post()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _handle_ortofoto(self, query: str):
        params = urllib.parse.parse_qs(query)
        z = (params.get("z") or [None])[0]
        x = (params.get("x") or [None])[0]
        y = (params.get("y") or [None])[0]
        if not z or not x or not y:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing z/x/y query params")
            return

        # Prefer server-side key from env; allow query fallback for local testing.
        api_key = (
            resolve_datafordeleren_api_key() or (params.get("apiKey") or [None])[0]
        )
        if not api_key:
            self.send_error(
                HTTPStatus.BAD_REQUEST,
                "Missing Datafordeleren key "
                "(set DATAFORDELEREN_API_KEY or "
                "provide apiKey query param)",
            )
            return

        wmts_url = urllib.parse.urlencode(
            {
                "apikey": api_key,
                "SERVICE": "WMTS",
                "REQUEST": "GetTile",
                "VERSION": "1.0.0",
                "STYLE": "default",
                "FORMAT": "image/jpeg",
                "TILEMATRIXSET": "DFD_GoogleMapsCompatible",
                "TILEMATRIX": z,
                "TILEROW": y,
                "TILECOL": x,
                "Layer": "orto_foraar_webm",
            }
        )
        url = f"{WMTS_BASE}?{wmts_url}"

        request = urllib.request.Request(
            url, headers={"User-Agent": "tirana-viewer/1.0"}
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "image/jpeg")
        except Exception as exc:
            self.send_error(HTTPStatus.BAD_GATEWAY, f"Ortofoto upstream error: {exc}")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_calibration(self):
        if not CALIBRATION_PATH.exists():
            return {}
        try:
            with open(CALIBRATION_PATH) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_calibration(self, data):
        CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CALIBRATION_PATH.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        tmp.replace(CALIBRATION_PATH)

    def _handle_calibration_get(self):
        payload = self._read_calibration()
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_calibration_post(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON body")
            return

        if not isinstance(payload, dict):
            self.send_error(HTTPStatus.BAD_REQUEST, "Body must be an object")
            return
        uuid = payload.get("uuid")
        if not isinstance(uuid, str) or not uuid:
            self.send_error(HTTPStatus.BAD_REQUEST, "uuid is required")
            return

        try:
            record = {
                "rotation_deg": float(payload.get("rotation_deg", 0.0)),
                "offset_east_m": float(payload.get("offset_east_m", 0.0)),
                "offset_north_m": float(payload.get("offset_north_m", 0.0)),
            }
        except Exception:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid numeric values")
            return

        all_data = self._read_calibration()
        all_data[uuid] = record
        self._write_calibration(all_data)

        out = json.dumps({"ok": True, "uuid": uuid, "record": record}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def _handle_ontology_artifacts(self, query: str):
        params = urllib.parse.parse_qs(query)
        uuid = (params.get("uuid") or [None])[0]
        view = (params.get("view") or ["summary"])[0]
        part_id = (params.get("part_id") or [None])[0]
        if not uuid:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing uuid query param")
            return
        try:
            entry = ONTOLOGY_CACHE.get(uuid)
            if entry is None:
                entry = _build_ontology_cache_entry(uuid)
                ONTOLOGY_CACHE[uuid] = entry
            if view == "summary":
                payload = entry["summary"]
            elif view == "part":
                if not part_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "Missing part_id for view=part")
                    return
                payload = entry["parts"].get(part_id)
                if payload is None:
                    self.send_error(HTTPStatus.NOT_FOUND, f"No ontology part {part_id} for {uuid}")
                    return
            else:
                self.send_error(HTTPStatus.BAD_REQUEST, f"Unsupported ontology view: {view}")
                return
        except FileNotFoundError as exc:
            self.send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        except Exception as exc:
            self.send_error(HTTPStatus.BAD_GATEWAY, f"Ontology build failed: {exc}")
            return

        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Keep default static path normalization behavior explicit.
    def translate_path(self, path: str) -> str:
        path = urllib.parse.urlparse(path).path
        path = posixpath.normpath(urllib.parse.unquote(path))
        words = [w for w in path.split("/") if w]
        resolved = Path(self.directory)
        for word in words:
            resolved = resolved / word
        return str(resolved)


class ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main():
    server = ReusableHTTPServer((HOST, PORT), ViewerHandler)
    print(f"Serving viewer on http://{HOST}:{PORT}/viewer.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
