from __future__ import annotations

from dataclasses import replace

import numpy as np
from shapely.geometry import Point, Polygon

from reconcile._core.shapely2 import make_valid
from reconcile.extract.building import ExtractedRoom, ExtractedWall

TOP_EPSILON_M = 0.05
MAX_GAP_TO_SLAB_M = 0.80
STACK_TOLERANCE_M = 0.10


def extend_wall_to_slab(
    corners: list[list[float]],
    slab_y_above: float,
    epsilon: float = TOP_EPSILON_M,
    max_gap: float = MAX_GAP_TO_SLAB_M,
) -> dict[str, list] | None:
    if len(corners) < 3:
        return None

    ys = [corner[1] for corner in corners]
    max_y = max(ys)
    min_y = min(ys)
    wall_height = max_y - min_y
    if wall_height < 0.1:
        return None

    y_threshold = min_y + wall_height * 0.4
    top_indices = [idx for idx, y_value in enumerate(ys) if y_value > y_threshold]
    if not top_indices:
        return None

    need_extension = [idx for idx in top_indices if ys[idx] < slab_y_above - epsilon]
    if not need_extension:
        return None

    max_top_y = max(ys[idx] for idx in top_indices)
    if slab_y_above - max_top_y > max_gap:
        return None

    extended = [list(corner) for corner in corners]
    need_extension_set = set(need_extension)
    for idx in need_extension:
        extended[idx][1] = slab_y_above

    extension_strips = []
    top_indices_sorted = sorted(top_indices)
    for idx in range(len(top_indices_sorted) - 1):
        i0 = top_indices_sorted[idx]
        i1 = top_indices_sorted[idx + 1]
        orig_y0 = corners[i0][1]
        orig_y1 = corners[i1][1]
        ext_y0 = slab_y_above if i0 in need_extension_set else orig_y0
        ext_y1 = slab_y_above if i1 in need_extension_set else orig_y1
        if abs(ext_y0 - orig_y0) < 1e-4 and abs(ext_y1 - orig_y1) < 1e-4:
            continue
        extension_strips.append(
            [
                [corners[i0][0], orig_y0, corners[i0][2]],
                [corners[i1][0], orig_y1, corners[i1][2]],
                [corners[i1][0], ext_y1, corners[i1][2]],
                [corners[i0][0], ext_y0, corners[i0][2]],
            ]
        )

    if not extension_strips:
        return None
    return {"extended_corners": extended, "extension_strip": extension_strips}


def find_best_slab_above(
    wall_corners: list[list[float]],
    wall_top_y: float,
    slabs_above: list[tuple[Polygon, float]],
    min_margin: float = TOP_EPSILON_M,
    max_gap: float | None = MAX_GAP_TO_SLAB_M,
    stack_tolerance: float | None = STACK_TOLERANCE_M,
) -> float | None:
    if not slabs_above or not wall_corners:
        return None
    wall_x = float(np.mean([corner[0] for corner in wall_corners]))
    wall_z = float(np.mean([corner[2] for corner in wall_corners]))
    point = Point(wall_x, wall_z)
    best_distance = float("inf")
    best_y = None
    for poly, slab_y in slabs_above:
        if slab_y <= wall_top_y + min_margin:
            continue
        if max_gap is not None and slab_y - wall_top_y > max_gap:
            continue
        distance = float(poly.distance(point))
        if stack_tolerance is not None and distance > stack_tolerance:
            continue
        if distance < best_distance:
            best_distance = distance
            best_y = slab_y
    return best_y


def _room_slab(room: ExtractedRoom) -> tuple[Polygon, float] | None:
    if len(room.floor_polygon) < 3:
        return None
    floor_y = float(np.mean([corner[1] for corner in room.floor_polygon]))
    poly = make_valid(Polygon([(corner[0], corner[2]) for corner in room.floor_polygon]))
    if not isinstance(poly, Polygon) or poly.is_empty or not poly.is_valid:
        return None
    return poly, floor_y


def extend_walls_to_slabs(rooms: list[ExtractedRoom]) -> list[ExtractedRoom]:
    story_slabs: dict[int, list[tuple[Polygon, float]]] = {}
    for room in rooms:
        slab = _room_slab(room)
        if slab is not None:
            story_slabs.setdefault(room.story, []).append(slab)

    out: list[ExtractedRoom] = []
    for room in rooms:
        slabs_above = [
            slab
            for story in sorted(story_slabs)
            if story > room.story
            for slab in story_slabs[story]
        ]
        extended_walls: list[ExtractedWall] = []
        for wall in room.walls_computed:
            if not wall.corners:
                extended_walls.append(replace(wall, extension_strip=None))
                continue
            wall_top_y = max(corner[1] for corner in wall.corners)
            slab_y = find_best_slab_above(wall.corners, wall_top_y, slabs_above)
            if slab_y is None:
                extended_walls.append(replace(wall, extension_strip=None))
                continue
            result = extend_wall_to_slab(wall.corners, slab_y)
            extended_walls.append(
                replace(
                    wall,
                    extension_strip=None if result is None else result["extension_strip"],
                )
            )
        out.append(replace(room, walls_computed=extended_walls))
    return out
