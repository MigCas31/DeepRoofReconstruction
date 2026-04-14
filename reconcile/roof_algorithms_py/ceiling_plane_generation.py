from __future__ import annotations

from math import cos, sin

from reconcile_v2.decision_logic import classify_roof_room

from .graph_support import (
    classify_graph_roof_room,
    graph_allows_roof_candidate,
    graph_requires_geometry_fallback,
    graph_room_index_map,
)
from .math_utils import plane_normal, seg_midpoint


def _cap_wall_top_for_half_level(
    wall_top_y: float,
    floor_y: float,
    story: int,
    fp: list,
    bldg: dict,
) -> float:
    """Cap wall-top Y for rooms whose walls reach into a higher story.

    In half-level buildings, a room on story N may have walls that extend
    to the same height as story N+1 wall tops (e.g. stairwells, double-height
    rooms).  If a nearby higher-story room has wall tops within 0.5m of this
    room's wall tops, the ceiling should be at the higher story's floor level
    — not at the wall tops (which are at the roof).
    """
    from shapely.geometry import Polygon
    from shapely.validation import make_valid

    WALL_TOP_MATCH_TOL = 0.50  # wall tops within 0.5m = same roof
    XZ_PROXIMITY = 1.0  # floor polygon edge distance (metres)

    room_xz = Polygon([(p[0], p[2]) for p in fp])
    if not room_xz.is_valid:
        room_xz = make_valid(room_xz)

    best_cap = None
    for other in bldg.get("rooms", []):
        other_story = int(other.get("story", 0))
        if other_story <= story:
            continue
        other_fp = other.get("floor_polygon")
        if not other_fp or len(other_fp) < 3:
            continue
        other_walls = other.get("walls_computed") or []
        if not other_walls:
            continue

        # Check XZ proximity using floor polygon distance
        other_xz = Polygon([(p[0], p[2]) for p in other_fp])
        if not other_xz.is_valid:
            other_xz = make_valid(other_xz)
        dist = room_xz.distance(other_xz)
        if dist > XZ_PROXIMITY:
            continue

        # Check if wall tops match (same roof level)
        other_top = max(
            max(c[1] for c in w.get("corners", []))
            for w in other_walls
            if w.get("corners")
        )
        if abs(wall_top_y - other_top) > WALL_TOP_MATCH_TOL:
            continue

        # Cap to the higher story's floor level
        cap_y = float(other_fp[0][1])
        if best_cap is None or cap_y < best_cap:
            best_cap = cap_y

    if best_cap is not None and best_cap < wall_top_y and best_cap > floor_y:
        return best_cap
    return wall_top_y


def collect_exposed_rooms(
    bldg: dict,
    has_floor_above,
    exclude_room_indices: set[int] | None = None,
    graph=None,
) -> list:
    graph_room_footprints: dict[str, list[list[float]]] = {}
    cell_complex = ((getattr(graph, "geometry_index", None) or {}).get("cell_complex") or {}) if graph is not None else {}
    for cell in (cell_complex.get("cells") or []):
        if not isinstance(cell, dict) or str(cell.get("kind") or "") != "room":
            continue
        source_id = str(cell.get("source_id") or "")
        footprint = (cell.get("properties") or {}).get("xz_footprint") or []
        if not source_id or not isinstance(footprint, list) or len(footprint) < 3:
            continue
        graph_room_footprints[source_id] = [
            [float(point[0]), float(point[1])]
            for point in footprint
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
    out = []
    for room_idx, room in enumerate(bldg.get("rooms", [])):
        if exclude_room_indices and room_idx in exclude_room_indices:
            continue
        fp = room.get("floor_polygon")
        if not fp or len(fp) < 3:
            continue
        walls = room.get("walls_computed") or []
        if not walls:
            continue

        fcx = sum(p[0] for p in fp) / len(fp)
        fcz = sum(p[2] for p in fp) / len(fp)
        story = int(room.get("story", 0))
        graph_room, roof_decision = classify_graph_roof_room(graph, story, fp)
        if roof_decision is not None and not graph_allows_roof_candidate(roof_decision):
            continue
        if graph_requires_geometry_fallback(roof_decision) and has_floor_above(fcx, fcz, story):
            continue

        wall_top_ys = [
            max(c[1] for c in w.get("corners", [])) for w in walls if w.get("corners")
        ]
        if not wall_top_ys:
            continue

        wall_top_y = max(wall_top_ys)
        floor_y = fp[0][1]

        # For half-level buildings: if wall tops reach the same height as a
        # nearby higher-story room's wall tops, cap ceiling at that story's
        # floor level instead of at the wall tops (which are at the roof).
        capped_top = _cap_wall_top_for_half_level(
            wall_top_y, floor_y, story, fp, bldg
        )

        capped_min = min(min(wall_top_ys), capped_top)
        capped_ys = [min(y, capped_top) for y in wall_top_ys]

        out.append(
            {
                "room": room,
                "room_index": room_idx,
                "graph_room_id": graph_room.id if graph_room is not None else None,
                "graph_fp_xz": graph_room_footprints.get(graph_room.id) if graph_room is not None else None,
                "fp": fp,
                "fcx": fcx,
                "fcz": fcz,
                "floorY": floor_y,
                "wallTopY": capped_top,
                "wallTopMin": capped_min,
                "wallTopYs": sorted(capped_ys),
                "story": story,
            }
        )
    return out


def _expand_plane_room_indices(
    *,
    bldg: dict | None,
    graph,
    story: int,
    room_indices: set[int],
    ref_x: float,
    ref_z: float,
    ridge_x: float,
    ridge_z: float,
    slope_x: float,
    slope_z: float,
    min_r: float,
    max_r: float,
    min_s: float,
    max_s: float,
) -> list[int]:
    if graph is None or bldg is None or not room_indices:
        return sorted(room_indices)

    index_by_graph_room = graph_room_index_map(bldg, graph)
    seed_graph_room_ids = {
        seg_room_id
        for room_idx in room_indices
        for seg_room_id in [
            next(
                (
                    room_id
                    for room_id, idx in index_by_graph_room.items()
                    if idx == room_idx
                ),
                None,
            )
        ]
        if seg_room_id
    }
    expanded = set(room_indices)
    slope_margin = 1.5
    ridge_margin = 2.0

    for seed_room_id in seed_graph_room_ids:
        for neighbor in graph.neighbors(seed_room_id, "ADJACENT_TO"):
            if neighbor.type != "Room" or neighbor.story != story:
                continue
            decision = classify_roof_room(graph, neighbor)
            if decision["mode"] == "ceiling_below_occupied_volume":
                continue
            room_idx = index_by_graph_room.get(neighbor.id)
            if room_idx is None:
                continue
            fp = (bldg.get("rooms", [])[room_idx] or {}).get("floor_polygon") or []
            if len(fp) < 3:
                continue
            ridge_projs = [
                (p[0] - ref_x) * ridge_x + (p[2] - ref_z) * ridge_z for p in fp
            ]
            slope_projs = [
                (p[0] - ref_x) * slope_x + (p[2] - ref_z) * slope_z for p in fp
            ]
            if max(slope_projs) < min_s - slope_margin or min(slope_projs) > max_s + slope_margin:
                continue
            if max(ridge_projs) < min_r - ridge_margin or min(ridge_projs) > max_r + ridge_margin:
                continue
            expanded.add(room_idx)

    return sorted(expanded)


def build_ceiling_planes(valid_clusters: list, bldg: dict | None = None, graph=None) -> list:
    planes = []
    for cl in valid_clusters:
        n = plane_normal(cl["avgAzimuth"], cl["avgIncl"])
        if abs(n["y"]) < 0.01:
            continue

        azi_rad = cl["avgAzimuth"] * 3.141592653589793 / 180.0
        ridge_x, ridge_z = -cos(azi_rad), sin(azi_rad)
        slope_x, slope_z = sin(azi_rad), cos(azi_rad)

        mids = [seg_midpoint(seg) for seg in cl["segs"]]
        ref_x = sum(m["x"] for m in mids) / len(mids)
        ref_y = sum(m["y"] for m in mids) / len(mids)
        ref_z = sum(m["z"] for m in mids) / len(mids)

        min_r = float("inf")
        max_r = float("-inf")
        min_s = float("inf")
        max_s = float("-inf")
        for seg in cl["segs"]:
            for p in (seg["a"], seg["b"]):
                proj_r = (p[0] - ref_x) * ridge_x + (p[2] - ref_z) * ridge_z
                proj_s = (p[0] - ref_x) * slope_x + (p[2] - ref_z) * slope_z
                min_r = min(min_r, proj_r)
                max_r = max(max_r, proj_r)
                min_s = min(min_s, proj_s)
                max_s = max(max_s, proj_s)

        if (max_r - min_r) < 2.0:
            continue

        story_counts = {}
        room_indices: set[int] = set()
        for seg in cl["segs"]:
            s = int(seg["story"])
            story_counts[s] = story_counts.get(s, 0) + 1
            if "room_idx" in seg:
                room_indices.add(seg["room_idx"])
        dominant_story = sorted(
            story_counts.items(), key=lambda kv: kv[1], reverse=True
        )[0][0]
        room_indices = set(
            _expand_plane_room_indices(
                bldg=bldg,
                graph=graph,
                story=dominant_story,
                room_indices=room_indices,
                ref_x=ref_x,
                ref_z=ref_z,
                ridge_x=ridge_x,
                ridge_z=ridge_z,
                slope_x=slope_x,
                slope_z=slope_z,
                min_r=min_r,
                max_r=max_r,
                min_s=min_s,
                max_s=max_s,
            )
        )

        planes.append(
            {
                "cl": cl,
                "n": n,
                "ref": {"x": ref_x, "y": ref_y, "z": ref_z},
                "ridgeX": ridge_x,
                "ridgeZ": ridge_z,
                "minRidge": min_r,
                "maxRidge": max_r,
                "slopeX": slope_x,
                "slopeZ": slope_z,
                "minSlope": min_s,
                "maxSlope": max_s,
                "dominantStory": dominant_story,
                "room_indices": sorted(room_indices),
            }
        )

    return planes
