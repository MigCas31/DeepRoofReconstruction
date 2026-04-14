from __future__ import annotations

from collections import defaultdict
from typing import Any

from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Polygon,
)
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

from .graph_utils import stable_hash as _stable_hash
from .math_utils import plane_normal, plane_y_at

EPS = 1e-6
AREA_EPS = 0.01
LATTICE_SCALE_MM = 1000


def _snap(value: float) -> float:
    return round(float(value) * LATTICE_SCALE_MM) / LATTICE_SCALE_MM


def _poly_xz(corners: list) -> Polygon | None:
    points: list[tuple[float, float]] = []
    for corner in corners or []:
        if not isinstance(corner, (list, tuple)) or len(corner) < 3:
            continue
        points.append((_snap(float(corner[0])), _snap(float(corner[2]))))
    if len(points) < 3:
        return None
    poly = Polygon(points)
    if not poly.is_valid:
        try:
            poly = make_valid(poly)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda geom: geom.area)
        except Exception:
            return None
    if not isinstance(poly, Polygon) or poly.is_empty or poly.area <= AREA_EPS:
        return None
    return poly


def _room_polygon_with_fallback(room_data: dict[str, Any]) -> tuple[Polygon | None, list[list[float]]]:
    raw_corners = room_data.get("fp") or []
    poly = _poly_xz(raw_corners)
    if poly is not None:
        return poly, raw_corners
    graph_fp_xz = room_data.get("graph_fp_xz") or []
    if not isinstance(graph_fp_xz, list) or len(graph_fp_xz) < 3:
        return None, []
    floor_y = float(room_data.get("floorY", 0.0))
    fallback_corners = [
        [_snap(float(point[0])), _snap(floor_y), _snap(float(point[1]))]
        for point in graph_fp_xz
        if isinstance(point, (list, tuple)) and len(point) >= 2
    ]
    poly = _poly_xz(fallback_corners)
    if poly is None:
        return None, []
    return poly, fallback_corners


def _linework_for_polygon(poly) -> list[LineString]:
    if isinstance(poly, Polygon):
        polys = [poly]
    elif isinstance(poly, MultiPolygon):
        polys = list(poly.geoms)
    else:
        return []
    lines: list[LineString] = []
    for geom in polys:
        lines.append(LineString(list(geom.exterior.coords)))
        for ring in geom.interiors:
            lines.append(LineString(list(ring.coords)))
    return lines


def _decompose_polys(geom: Any) -> list[Polygon]:
    if geom is None or getattr(geom, "is_empty", True):
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        return [item for item in geom.geoms if isinstance(item, Polygon) and not item.is_empty]
    return [item for item in getattr(geom, "geoms", []) if isinstance(item, Polygon) and not item.is_empty]


def _decompose_lines(geom: Any) -> list[LineString]:
    if geom is None or getattr(geom, "is_empty", True):
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        return [item for item in geom.geoms if isinstance(item, LineString) and not item.is_empty]
    return [item for item in getattr(geom, "geoms", []) if isinstance(item, LineString) and not item.is_empty]


def _flat_y(surface: dict[str, Any], room_data: dict[str, Any]) -> float:
    y = surface.get("y")
    if isinstance(y, (float, int)):
        return float(y)
    corners = surface.get("corners") or []
    ys = [float(c[1]) for c in corners if isinstance(c, (list, tuple)) and len(c) >= 3]
    if ys:
        return sum(ys) / len(ys)
    return (float(room_data["wallTopY"]) + float(room_data["wallTopMin"])) * 0.5


def _surface_plane_from_corners(surface: dict[str, Any]) -> dict[str, Any] | None:
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
    if abs(ny) <= EPS:
        return None
    return {
        "n": {"x": float(nx), "y": float(ny), "z": float(nz)},
        "ref": {
            "x": float(a[0]),
            "y": float(a[1]),
            "z": float(a[2]),
        },
    }


def _surface_plane_from_cluster(surface: dict[str, Any]) -> dict[str, Any] | None:
    cluster = surface.get("cluster") or {}
    avg_azimuth = cluster.get("avgAzimuth")
    avg_incl = cluster.get("avgIncl")
    ref = cluster.get("refPt") or surface.get("center") or {}
    if avg_azimuth is None or avg_incl is None or not ref:
        return None
    return {
        "n": plane_normal(float(avg_azimuth), float(avg_incl)),
        "ref": {
            "x": float(ref["x"]),
            "y": float(ref["y"]),
            "z": float(ref["z"]),
        },
    }


def _surface_plane(surface: dict[str, Any]) -> dict[str, Any] | None:
    plane = _surface_plane_from_cluster(surface)
    if plane is not None:
        return plane
    return _surface_plane_from_corners(surface)


def _height_model(kind: str, surface: dict[str, Any], room_data: dict[str, Any]) -> tuple[float, float, float]:
    if kind == "flat":
        return (0.0, 0.0, _snap(_flat_y(surface, room_data)))
    plane = _surface_plane(surface)
    if plane is None:
        return (0.0, 0.0, _snap(_flat_y(surface, room_data)))
    n = plane["n"]
    ref = plane["ref"]
    ny = float(n["y"])
    if abs(ny) <= EPS:
        return (0.0, 0.0, _snap(_flat_y(surface, room_data)))
    a = -float(n["x"]) / ny
    b = -float(n["z"]) / ny
    c = float(ref["y"]) + (
        (float(n["x"]) * float(ref["x"]) + float(n["z"]) * float(ref["z"])) / ny
    )
    return (_snap(a), _snap(b), _snap(c))


def _height_at(model: tuple[float, float, float], x: float, z: float) -> float:
    a, b, c = model
    return _snap(a * float(x) + b * float(z) + c)


def _equal_height_split_lines(
    left_model: tuple[float, float, float],
    right_model: tuple[float, float, float],
    clip_poly: Polygon,
) -> list[LineString]:
    if clip_poly.is_empty or clip_poly.area <= AREA_EPS:
        return []
    da = float(left_model[0] - right_model[0])
    db = float(left_model[1] - right_model[1])
    dc = float(left_model[2] - right_model[2])
    norm_sq = da * da + db * db
    if norm_sq <= EPS:
        return []
    centroid = clip_poly.representative_point()
    cx = float(centroid.x)
    cz = float(centroid.y)
    signed = da * cx + db * cz + dc
    px = cx - (signed * da / norm_sq)
    pz = cz - (signed * db / norm_sq)
    dx = -db
    dz = da
    dir_norm = (dx * dx + dz * dz) ** 0.5
    if dir_norm <= EPS:
        return []
    dx /= dir_norm
    dz /= dir_norm
    minx, minz, maxx, maxz = clip_poly.bounds
    span = ((maxx - minx) ** 2 + (maxz - minz) ** 2) ** 0.5
    reach = max(4.0, span * 2.0)
    splitter = LineString(
        [
            (_snap(px - dx * reach), _snap(pz - dz * reach)),
            (_snap(px + dx * reach), _snap(pz + dz * reach)),
        ]
    )
    try:
        clipped = clip_poly.intersection(splitter)
    except Exception:
        return []
    return [line for line in _decompose_lines(clipped) if line.length > 0.05]


def _atom_corners(atom: Polygon, kind: str, surface: dict[str, Any] | None, room_data: dict[str, Any]) -> list[tuple[float, float, float]]:
    coords = list(atom.exterior.coords)
    if coords and coords[-1] == coords[0]:
        coords = coords[:-1]
    corners: list[tuple[float, float, float]] = []
    if kind == "oblique" and surface is not None:
        plane = _surface_plane(surface)
        if plane is not None:
            for x, z, *_ in coords:
                sx = _snap(float(x))
                sz = _snap(float(z))
                corners.append((sx, _snap(plane_y_at(plane, sx, sz)), sz))
            return corners
    y = _snap(_flat_y(surface or {}, room_data))
    return [(_snap(float(x)), y, _snap(float(z))) for x, z, *_ in coords]


def derive_room_ceiling_partitions(
    *,
    exposed_rooms: list[dict[str, Any]],
    oblique_roof_surfaces: list[dict[str, Any]],
    flat_roof_surfaces: list[dict[str, Any]],
    hypothesis_graph: dict[str, Any],
) -> dict[str, Any]:
    nodes_by_id = {
        node["id"]: node
        for node in hypothesis_graph.get("nodes") or []
        if node.get("type") == "RoofHypothesis"
    }
    selected_room_assignments = hypothesis_graph.get("selected_room_assignments") or {}
    cover_edges = {
        (edge["from"], edge["to"]): edge
        for edge in hypothesis_graph.get("edges") or []
        if edge.get("type") == "COVERS_ROOM"
    }

    surfaces_by_hypothesis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for surface in oblique_roof_surfaces:
        hypothesis_id = surface.get("roof_hypothesis_id")
        if hypothesis_id:
            surfaces_by_hypothesis[str(hypothesis_id)].append(surface)
    for surface in flat_roof_surfaces:
        hypothesis_id = surface.get("roof_hypothesis_id")
        if hypothesis_id:
            surfaces_by_hypothesis[str(hypothesis_id)].append(surface)

    room_partitions: list[dict[str, Any]] = []
    flat_surfaces: list[dict[str, Any]] = []
    oblique_surfaces: list[dict[str, Any]] = []
    selected_hypothesis_ids = {
        str(hypothesis_id)
        for hypothesis_id in (
            hypothesis_graph.get("selected_hypothesis_ids")
            or [node_id for node_id, node in nodes_by_id.items() if node.get("selected")]
        )
    }
    split_line_count = 0

    for room_data in exposed_rooms:
        room_index = int(room_data["room_index"])
        room_key = f"room:{room_index}"
        room_polygon, room_corners = _room_polygon_with_fallback(room_data)
        if room_polygon is None:
            continue

        selected_ids = list(selected_room_assignments.get(room_key) or [])
        candidate_records: list[dict[str, Any]] = []
        linework = _linework_for_polygon(room_polygon)

        candidate_ids = list(dict.fromkeys(selected_ids + sorted(selected_hypothesis_ids - set(selected_ids))))
        for hypothesis_id in candidate_ids:
            surfaces = surfaces_by_hypothesis.get(hypothesis_id) or []
            if not surfaces:
                continue
            node = nodes_by_id.get(hypothesis_id) or {}
            edge = cover_edges.get((hypothesis_id, room_key)) or {}
            for surface_index, surface in enumerate(surfaces):
                surface_poly = _poly_xz(surface.get("corners") or [])
                if surface_poly is None:
                    continue
                try:
                    overlap = room_polygon.intersection(surface_poly)
                except Exception:
                    continue
                if overlap.is_empty or overlap.area <= AREA_EPS:
                    continue
                room_overlaps = _decompose_polys(overlap)
                if not room_overlaps:
                    continue
                for room_overlap in room_overlaps:
                    linework.extend(_linework_for_polygon(room_overlap))
                candidate_records.append(
                    {
                        "surface_key": f"{hypothesis_id}:{surface_index}",
                        "hypothesis_id": hypothesis_id,
                        "surface": surface,
                        "kind": str(node.get("surface_kind", "flat")),
                        "room_overlap": unary_union(room_overlaps),
                        "selected_for_room": hypothesis_id in selected_ids,
                        "edge_score": float(((edge.get("evidence") or {}).get("edge_score")) or 0.0),
                        "height_model": _height_model(str(node.get("surface_kind", "flat")), surface, room_data),
                    }
                )

        for left_index, left in enumerate(candidate_records):
            for right in candidate_records[left_index + 1 :]:
                try:
                    common = left["room_overlap"].intersection(right["room_overlap"])
                except Exception:
                    continue
                for common_poly in _decompose_polys(common):
                    split_lines = _equal_height_split_lines(
                        left["height_model"],
                        right["height_model"],
                        common_poly,
                    )
                    split_line_count += len(split_lines)
                    linework.extend(split_lines)

        arrangement = unary_union(linework)
        atom_candidates = list(polygonize(arrangement))
        if not atom_candidates:
            atom_candidates = [room_polygon]

        atoms: list[dict[str, Any]] = []
        for atom in atom_candidates:
            if atom.is_empty or atom.area <= AREA_EPS:
                continue
            rep = atom.representative_point()
            if not room_polygon.buffer(EPS).contains(rep):
                continue

            owner_id = None
            owner_top_y = None
            owner_selected = False
            owner_edge_score = -1.0
            owner_kind = "flat"
            owner_surface = None
            supporting_hypothesis_ids: list[str] = []
            for candidate in candidate_records:
                try:
                    overlap_area = atom.intersection(candidate["room_overlap"]).area
                except Exception:
                    overlap_area = 0.0
                if overlap_area <= AREA_EPS:
                    continue
                supporting_hypothesis_ids.append(str(candidate["hypothesis_id"]))
                top_y = _height_at(candidate["height_model"], float(rep.x), float(rep.y))
                selected_for_room = bool(candidate["selected_for_room"])
                edge_score = float(candidate["edge_score"])
                if (
                    owner_top_y is None
                    or top_y < owner_top_y - EPS
                    or (
                        abs(top_y - owner_top_y) <= EPS
                        and selected_for_room
                        and not owner_selected
                    )
                    or (
                        abs(top_y - owner_top_y) <= EPS
                        and selected_for_room == owner_selected
                        and edge_score > owner_edge_score + EPS
                    )
                ):
                    owner_id = str(candidate["hypothesis_id"])
                    owner_top_y = top_y
                    owner_selected = selected_for_room
                    owner_edge_score = edge_score
                    owner_surface = candidate["surface"]
                    owner_kind = str(candidate["kind"])

            if owner_id is None:
                owner_kind = "flat"
                owner_surface = None

            corners = _atom_corners(atom, owner_kind, owner_surface, room_data)
            if len(corners) < 3:
                continue
            partition_id = f"ceiling-partition:{_stable_hash([room_key, owner_id or 'fallback', str(corners)], 20)}"
            atom_record = {
                "id": partition_id,
                "room_index": room_index,
                "story": int(room_data["story"]),
                "kind": owner_kind,
                "roof_hypothesis_id": owner_id,
                "poly": corners,
                "area_m2": round(float(atom.area), 6),
                "supporting_roof_hypothesis_ids": sorted(set(supporting_hypothesis_ids)),
            }
            if isinstance(owner_surface, dict):
                if "flat_role" in owner_surface:
                    atom_record["flat_role"] = owner_surface.get("flat_role")
                    atom_record["flat_role_reason"] = owner_surface.get("flat_role_reason")
            if owner_top_y is not None:
                atom_record["top_y_m"] = owner_top_y
            atoms.append(atom_record)
            if owner_kind == "oblique":
                oblique_surfaces.append(atom_record)
            else:
                flat_surfaces.append(atom_record)

        if not atoms:
            fallback_poly = [
                (_snap(float(p[0])), _snap((float(room_data["wallTopY"]) + float(room_data["wallTopMin"])) * 0.5), _snap(float(p[2])))
                for p in room_corners
            ]
            if len(fallback_poly) >= 3:
                atom_record = {
                    "id": f"ceiling-partition:{_stable_hash([room_key, 'fallback-flat', str(fallback_poly)], 20)}",
                    "room_index": room_index,
                    "story": int(room_data["story"]),
                    "kind": "flat",
                    "roof_hypothesis_id": None,
                    "poly": fallback_poly,
                    "area_m2": round(float(room_polygon.area), 6),
                }
                atoms.append(atom_record)
                flat_surfaces.append(atom_record)

        room_partitions.append(
            {
                "room_index": room_index,
                "story": int(room_data["story"]),
                "graph_room_id": room_data.get("graph_room_id"),
                "partition_count": len(atoms),
                "mixed": len({atom["kind"] for atom in atoms}) > 1 or len({atom["roof_hypothesis_id"] for atom in atoms if atom["roof_hypothesis_id"]}) > 1,
                "partitions": atoms,
            }
        )

    return {
        "room_partitions": room_partitions,
        "flat": flat_surfaces,
        "oblique": oblique_surfaces,
        "metadata": {
            "room_partition_count": len(room_partitions),
            "flat_partition_count": len(flat_surfaces),
            "oblique_partition_count": len(oblique_surfaces),
            "mixed_room_count": sum(1 for room in room_partitions if room["mixed"]),
            "split_line_count": split_line_count,
        },
    }
