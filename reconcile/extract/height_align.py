from __future__ import annotations

from dataclasses import replace
from statistics import median

from reconcile.extract.building import ExtractedRoom, ExtractedWall

FLOOR_ALIGN_TOL_M = 0.06
WALL_HEIGHT_ALIGN_TOL_M = 0.05
CORNER_SNAP_TOL_M = 0.05

MIN_WALL_SPAN_M = 0.05
MIN_WALL_HEIGHT_M = 0.10


def _room_floor_y(room: ExtractedRoom) -> float | None:
    if len(room.floor_polygon) < 3:
        return None
    return float(median(corner[1] for corner in room.floor_polygon))


def _wall_span_xz(corners: list[list[float]]) -> float:
    xs = [corner[0] for corner in corners]
    zs = [corner[2] for corner in corners]
    return max((max(xs) - min(xs)) ** 2 + (max(zs) - min(zs)) ** 2, 0.0) ** 0.5


def _room_wall_height(room: ExtractedRoom) -> float | None:
    heights = []
    for wall in room.walls_computed:
        corners = wall.corners
        if len(corners) < 3 or _wall_span_xz(corners) < MIN_WALL_SPAN_M:
            continue
        ys = [corner[1] for corner in corners]
        height = max(ys) - min(ys)
        if height >= MIN_WALL_HEIGHT_M:
            heights.append(height)
    return float(median(heights)) if heights else None


def _room_wall_ceiling_ref(room: ExtractedRoom) -> float | None:
    tops = []
    for wall in room.walls_computed:
        corners = wall.corners
        if len(corners) < 3 or _wall_span_xz(corners) < MIN_WALL_SPAN_M:
            continue
        ys = [corner[1] for corner in corners]
        if max(ys) - min(ys) >= MIN_WALL_HEIGHT_M:
            tops.append(max(ys))
    return float(median(tops)) if tops else None


def _group_rooms(entries: list[tuple[float, float, int]]) -> list[list[tuple[float, float, int]]]:
    groups: list[list[tuple[float, float, int]]] = []
    current: list[tuple[float, float, int]] = []
    for entry in sorted(entries, key=lambda item: item[0]):
        floor_y, wall_height, _idx = entry
        if not current:
            current.append(entry)
            continue
        group_floor_ys = [item[0] for item in current]
        spread_ok = (
            floor_y - min(group_floor_ys) <= FLOOR_ALIGN_TOL_M
            and max(floor_y - min(group_floor_ys), max(group_floor_ys) - floor_y) <= FLOOR_ALIGN_TOL_M
        )
        wall_height_ok = abs(wall_height - median(item[1] for item in current)) <= WALL_HEIGHT_ALIGN_TOL_M
        if spread_ok and wall_height_ok:
            current.append(entry)
        else:
            groups.append(current)
            current = [entry]
    if current:
        groups.append(current)
    return groups


def _align_wall(
    wall: ExtractedWall,
    floor_y: float,
    room_ceiling_ref: float | None,
    target_floor_y: float,
    target_ceiling_y: float,
) -> tuple[ExtractedWall, bool, float, float]:
    corners = [list(corner) for corner in wall.corners]
    if len(corners) < 3:
        return wall, False, 0.0, 0.0
    ys = [corner[1] for corner in corners]
    wall_min_y = min(ys)
    wall_max_y = max(ys)
    if wall_max_y - wall_min_y < MIN_WALL_HEIGHT_M:
        return wall, False, 0.0, 0.0

    top_snap_ok = room_ceiling_ref is not None and abs(wall_max_y - room_ceiling_ref) <= CORNER_SNAP_TOL_M
    bottom_snap_ok = abs(wall_min_y - floor_y) <= CORNER_SNAP_TOL_M
    bottom_shift = 0.0
    top_shift = 0.0
    changed = False
    for corner in corners:
        y = corner[1]
        if bottom_snap_ok and abs(y - wall_min_y) <= CORNER_SNAP_TOL_M:
            if abs(target_floor_y - y) > 1e-6:
                corner[1] = target_floor_y
                bottom_shift = max(bottom_shift, abs(target_floor_y - y))
                changed = True
        elif top_snap_ok and abs(y - wall_max_y) <= CORNER_SNAP_TOL_M:
            if abs(target_ceiling_y - y) > 1e-6:
                corner[1] = target_ceiling_y
                top_shift = max(top_shift, abs(target_ceiling_y - y))
                changed = True
    if not changed:
        return wall, False, 0.0, 0.0
    return replace(wall, corners=corners), True, bottom_shift, top_shift


def align_room_heights(rooms: list[ExtractedRoom]) -> tuple[list[ExtractedRoom], dict[str, float | int]]:
    metrics: dict[str, float | int] = {
        "aligned_groups": 0,
        "aligned_rooms": 0,
        "aligned_walls": 0,
        "max_floor_shift": 0.0,
        "max_top_shift": 0.0,
    }

    by_story: dict[int, list[tuple[float, float, int]]] = {}
    for idx, room in enumerate(rooms):
        floor_y = _room_floor_y(room)
        wall_height = _room_wall_height(room)
        if floor_y is None or wall_height is None:
            continue
        by_story.setdefault(room.story, []).append((floor_y, wall_height, idx))

    out = list(rooms)
    for entries in by_story.values():
        if len(entries) < 2:
            continue
        for group in _group_rooms(entries):
            if len(group) < 2:
                continue
            floor_ys = [item[0] for item in group]
            ceiling_ys = [floor_y + wall_height for floor_y, wall_height, _idx in group]
            target_floor_y = float(median(floor_ys))
            target_ceiling_y = float(median(ceiling_ys))
            metrics["aligned_groups"] += 1

            for floor_y, _wall_height, room_idx in group:
                room = out[room_idx]
                room_ceiling_ref = _room_wall_ceiling_ref(room)
                floor_polygon = [list(corner) for corner in room.floor_polygon]
                if len(floor_polygon) >= 3:
                    for corner in floor_polygon:
                        corner[1] = target_floor_y
                    metrics["max_floor_shift"] = max(
                        float(metrics["max_floor_shift"]),
                        abs(target_floor_y - floor_y),
                    )

                aligned_walls = []
                for wall in room.walls_computed:
                    aligned_wall, changed, bottom_shift, top_shift = _align_wall(
                        wall,
                        floor_y,
                        room_ceiling_ref,
                        target_floor_y,
                        target_ceiling_y,
                    )
                    aligned_walls.append(aligned_wall)
                    if changed:
                        metrics["aligned_walls"] += 1
                        metrics["max_floor_shift"] = max(float(metrics["max_floor_shift"]), bottom_shift)
                        metrics["max_top_shift"] = max(float(metrics["max_top_shift"]), top_shift)

                out[room_idx] = replace(
                    room,
                    floor_polygon=floor_polygon,
                    walls_computed=aligned_walls,
                )
                metrics["aligned_rooms"] += 1

    return out, metrics
