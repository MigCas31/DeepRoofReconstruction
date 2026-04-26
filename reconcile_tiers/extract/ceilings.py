from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
from shapely.geometry import Point, Polygon

from reconcile_tiers._core.shapely2 import make_valid
from reconcile_tiers.extract.building import ExtractedRoom, RawCeilingPlane

WALL_TOP_SPREAD_MAX_M = 0.20
CEILING_OVERSHOOT_MAX_M = 0.30
RIDGE_EAVE_MAX_DELTA_M = 0.10
NEIGHBOUR_TOLERANCE_M = 0.30
NOISY_PLANE_DROP_TAU_M = 0.30
SLANT_THRESH_M = 0.15
SLOPE_THRESH_M = 0.15
XZ_MATCH_TOL_M = 0.20


def reassign_raw_ceiling_planes_spatially(rooms: list[ExtractedRoom]) -> list[ExtractedRoom]:
    room_polys: list[Polygon | None] = []
    for room in rooms:
        floor = room.floor_polygon
        if len(floor) < 3:
            room_polys.append(None)
            continue
        poly = make_valid(Polygon([(corner[0], corner[2]) for corner in floor]))
        room_polys.append(poly if poly.is_valid and not poly.is_empty else None)

    reassignments: list[list[RawCeilingPlane]] = [[] for _ in rooms]
    for src_idx, room in enumerate(rooms):
        for plane in room.raw_ceiling_planes:
            corners = plane.corners
            if len(corners) < 3:
                reassignments[src_idx].append(plane)
                continue
            cx = sum(corner[0] for corner in corners) / len(corners)
            cz = sum(corner[2] for corner in corners) / len(corners)
            centroid = Point(cx, cz)
            target_idx = None
            for room_idx, poly in enumerate(room_polys):
                if poly is None or rooms[room_idx].story != room.story:
                    continue
                if poly.contains(centroid):
                    target_idx = room_idx
                    break
            if target_idx is None:
                plane_poly = make_valid(Polygon([(corner[0], corner[2]) for corner in corners]))
                if plane_poly.is_valid and not plane_poly.is_empty:
                    best_area = 0.0
                    for room_idx, poly in enumerate(room_polys):
                        if poly is None or rooms[room_idx].story != room.story:
                            continue
                        area = float(poly.intersection(plane_poly).area)
                        if area > best_area:
                            best_area = area
                            target_idx = room_idx
            reassignments[src_idx if target_idx is None else target_idx].append(plane)

    return [
        replace(room, raw_ceiling_planes=reassignments[idx])
        for idx, room in enumerate(rooms)
    ]


def _wall_top_percentiles(room: ExtractedRoom) -> dict[str, float] | None:
    tops = []
    walls = room.walls_computed or room.walls_merged
    for wall in walls:
        ys = [corner[1] for corner in wall.corners]
        if ys:
            tops.append(max(ys))
    if len(tops) < 2:
        return None
    return {
        "p10": float(np.percentile(tops, 10)),
        "p50": float(np.percentile(tops, 50)),
        "p90": float(np.percentile(tops, 90)),
    }


def _max_raw_ceiling_corner_y(room: ExtractedRoom) -> float | None:
    best = None
    for plane in room.raw_ceiling_planes:
        for corner in plane.corners:
            if len(corner) >= 2 and (best is None or corner[1] > best):
                best = float(corner[1])
    return best


def _classify_should_be_flat(rooms: list[ExtractedRoom]) -> dict[int, tuple[bool, float | None]]:
    per_room = [
        {"room": room, "ws": _wall_top_percentiles(room), "max_raw_y": _max_raw_ceiling_corner_y(room)}
        for room in rooms
    ]
    by_story_p50: dict[int, list[float]] = {}
    for entry in per_room:
        ws = entry["ws"]
        if ws is None:
            continue
        if (ws["p90"] - ws["p10"]) >= WALL_TOP_SPREAD_MAX_M:
            continue
        max_raw = entry["max_raw_y"]
        if max_raw is not None and (max_raw - ws["p50"]) >= CEILING_OVERSHOOT_MAX_M:
            continue
        by_story_p50.setdefault(entry["room"].story, []).append(ws["p50"])
    neighbour_median = {
        story: float(np.median(values))
        for story, values in by_story_p50.items()
        if values
    }

    out: dict[int, tuple[bool, float | None]] = {}
    for idx, entry in enumerate(per_room):
        room = entry["room"]
        ws = entry["ws"]
        if ws is None:
            out[idx] = (False, None)
            continue
        max_raw = entry["max_raw_y"]
        if max_raw is not None and (max_raw - ws["p50"]) >= CEILING_OVERSHOOT_MAX_M:
            out[idx] = (False, None)
            continue
        internal_flat = (ws["p90"] - ws["p10"]) < WALL_TOP_SPREAD_MAX_M
        nbm = neighbour_median.get(room.story)
        nb_consensus = nbm is not None and abs(ws["p50"] - nbm) < NEIGHBOUR_TOLERANCE_M
        if internal_flat:
            out[idx] = (True, ws["p50"])
        elif nb_consensus:
            out[idx] = (True, nbm)
        else:
            out[idx] = (False, None)
    return out


def _drop_noisy_raw_ceiling_planes(
    room: ExtractedRoom,
    should_flat: bool,
    expected_y: float | None,
) -> list[RawCeilingPlane]:
    if not should_flat or expected_y is None:
        return room.raw_ceiling_planes
    kept = []
    seen = set()
    for plane in room.raw_ceiling_planes:
        if not plane.corners:
            continue
        min_y = min(corner[1] for corner in plane.corners)
        if expected_y - min_y > NOISY_PLANE_DROP_TAU_M:
            continue
        if min_y - expected_y > RIDGE_EAVE_MAX_DELTA_M:
            continue
        key = tuple(
            tuple(round(float(value), 4) for value in corner[:3])
            for corner in plane.corners
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(plane)
    return kept


def _flat_ceiling_polygon(room: ExtractedRoom, ceiling_y: float) -> list[list[float]]:
    return [[round(corner[0], 4), ceiling_y, round(corner[2], 4)] for corner in room.floor_polygon]


def _xz_dist(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2])


def build_ceiling_from_wall_tops(room: ExtractedRoom) -> list[list[float]] | None:
    floor_polygon = room.floor_polygon
    walls = room.walls_computed or room.walls_merged
    if len(floor_polygon) < 3 or not walls:
        return None

    wall_info = []
    for wall in walls:
        corners = wall.corners
        if len(corners) < 3:
            continue
        ys = [corner[1] for corner in corners]
        mid_y = (max(ys) + min(ys)) / 2.0
        bot = [corner for corner in corners if corner[1] <= mid_y + 0.01]
        top = [corner for corner in corners if corner[1] > mid_y - 0.01]
        if len(bot) >= 2 and len(top) >= 2:
            wall_info.append({"bot": bot, "top": top})
    if not wall_info:
        return None

    def nearest_corner(corner, corners):
        return min((_xz_dist(corner, candidate), candidate) for candidate in corners)

    edge_walls = [None] * len(floor_polygon)
    used = set()
    for edge_idx in range(len(floor_polygon)):
        v0 = floor_polygon[edge_idx]
        v1 = floor_polygon[(edge_idx + 1) % len(floor_polygon)]
        best_score = float("inf")
        best_idx = None
        for wall_idx, info in enumerate(wall_info):
            if wall_idx in used:
                continue
            d0, _ = nearest_corner(v0, info["bot"])
            d1, _ = nearest_corner(v1, info["bot"])
            score = d0 + d1
            if score < best_score:
                best_score = score
                best_idx = wall_idx
        if best_idx is not None and best_score < XZ_MATCH_TOL_M * 2.0:
            edge_walls[edge_idx] = best_idx
            used.add(best_idx)

    ceiling_pts = []
    for edge_idx, wall_idx in enumerate(edge_walls):
        if wall_idx is None:
            continue
        v0 = floor_polygon[edge_idx]
        v1 = floor_polygon[(edge_idx + 1) % len(floor_polygon)]
        top_corners = wall_info[wall_idx]["top"]
        bot_corners = wall_info[wall_idx]["bot"]
        start_bot = nearest_corner(v0, bot_corners)[1]
        end_bot = nearest_corner(v1, bot_corners)[1]
        start_top = nearest_corner(start_bot, top_corners)[1]
        end_top = nearest_corner(end_bot, top_corners)[1]
        ordered_top = [start_top, end_top]
        for corner in ordered_top:
            point = [round(corner[0], 4), round(corner[1], 4), round(corner[2], 4)]
            if ceiling_pts:
                last = ceiling_pts[-1]
                if abs(point[0] - last[0]) < 0.01 and abs(point[2] - last[2]) < 0.01:
                    if point[1] > last[1]:
                        ceiling_pts[-1] = point
                    continue
            ceiling_pts.append(point)

    if len(ceiling_pts) >= 2:
        first = ceiling_pts[0]
        last = ceiling_pts[-1]
        if abs(first[0] - last[0]) < 0.01 and abs(first[2] - last[2]) < 0.01:
            if last[1] > first[1]:
                ceiling_pts[0] = last
            ceiling_pts.pop()
    return ceiling_pts if len(ceiling_pts) >= 3 else None


def _has_slanted_wall_top(room: ExtractedRoom) -> bool:
    walls = room.walls_computed or room.walls_merged
    for wall in walls:
        corners = wall.corners
        if len(corners) < 3:
            continue
        ys = [corner[1] for corner in corners]
        mid_y = (max(ys) + min(ys)) / 2.0
        top_corners = [corner for corner in corners if corner[1] > mid_y - 0.01]
        if len(top_corners) < 2:
            continue
        top_range = max(corner[1] for corner in top_corners) - min(corner[1] for corner in top_corners)
        if top_range > SLANT_THRESH_M:
            return True
    return False


def infer_ceilings(rooms: list[ExtractedRoom]) -> list[ExtractedRoom]:
    reassigned = reassign_raw_ceiling_planes_spatially(rooms)
    classifications = _classify_should_be_flat(reassigned)
    out: list[ExtractedRoom] = []
    for idx, room in enumerate(reassigned):
        should_flat, expected_y = classifications.get(idx, (False, None))
        raw_planes = room.raw_ceiling_planes
        flat_raw_planes = _drop_noisy_raw_ceiling_planes(room, should_flat, expected_y)
        if should_flat and expected_y is not None and raw_planes:
            kept_max_y = _max_raw_ceiling_corner_y(replace(room, raw_ceiling_planes=flat_raw_planes))
            ceiling_y = round(float(max(expected_y, kept_max_y) if kept_max_y is not None else expected_y), 4)
            out.append(
                replace(
                    room,
                    raw_ceiling_planes=flat_raw_planes,
                    ceiling_polygon=_flat_ceiling_polygon(room, ceiling_y) if len(room.floor_polygon) >= 3 else [],
                    ceiling_type="flat",
                    ceiling_eave_height=ceiling_y,
                    ceiling_ridge_height=ceiling_y,
                )
            )
            continue

        if not _has_slanted_wall_top(room):
            out.append(replace(room, raw_ceiling_planes=raw_planes))
            continue

        ceiling_polygon = build_ceiling_from_wall_tops(room)
        if ceiling_polygon is None:
            out.append(replace(room, raw_ceiling_planes=raw_planes))
            continue
        ys = [point[1] for point in ceiling_polygon]
        ceiling_type = "flat" if max(ys) - min(ys) < SLOPE_THRESH_M else "sloped"
        out.append(
            replace(
                room,
                raw_ceiling_planes=raw_planes,
                ceiling_polygon=ceiling_polygon,
                ceiling_type=ceiling_type,
                ceiling_eave_height=round(min(ys), 4),
                ceiling_ridge_height=round(max(ys), 4),
            )
        )
    return out
