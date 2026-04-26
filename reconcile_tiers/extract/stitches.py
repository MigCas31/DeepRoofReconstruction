from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from reconcile_tiers.extract.building import ExtractedRoom, ExtractedStitchWall

MAX_GAP_M = 1.50
MIN_GAP_M = 0.06
MIN_WALL_HEIGHT_M = 0.50
HEIGHT_RATIO = 0.65
MUTUAL_THRESH_M = 0.60
DIRECT_QUAD_MAX_GAP_M = 0.15
MIN_LEG_LENGTH_M = 0.06

_STITCH_TYPE_CONTRACTS = {
    10: {"stitch": 5, "stitch_floor": 1, "stitch_ceiling": 1},
    9: {"stitch": 8},
    11: {"stitch": 9, "stitch_floor": 6, "stitch_ceiling": 6},
}


def _wall_height(corners: list[list[float]]) -> float:
    if not corners:
        return 0.0
    ys = [float(corner[1]) for corner in corners]
    return max(ys) - min(ys)


def _wall_dir_xz(corners: list[list[float]]) -> tuple[float, float]:
    dx = float(corners[1][0]) - float(corners[0][0])
    dz = float(corners[1][2]) - float(corners[0][2])
    length = math.hypot(dx, dz)
    if length < 1e-6:
        return 0.0, 0.0
    return dx / length, dz / length


def _build_l_candidate(
    p_anchor: tuple[float, float],
    p_other: tuple[float, float],
    dir_anchor_out: tuple[float, float],
    dir_other_out: tuple[float, float],
):
    ax, az = p_anchor
    ox, oz = p_other
    along = (ox - ax) * dir_anchor_out[0] + (oz - az) * dir_anchor_out[1]
    if along < 0.0:
        return None
    cx = ax + along * dir_anchor_out[0]
    cz = az + along * dir_anchor_out[1]
    if (cx - ox) * dir_other_out[0] + (cz - oz) * dir_other_out[1] < 0.0:
        return None
    perp_len = math.hypot(
        (ox - ax) - along * dir_anchor_out[0],
        (oz - az) - along * dir_anchor_out[1],
    )
    legs = []
    if along >= MIN_LEG_LENGTH_M:
        legs.append(((ax, az), (cx, cz)))
    if perp_len >= MIN_LEG_LENGTH_M:
        legs.append(((cx, cz), (ox, oz)))
    return {"corner": (cx, cz), "legs": legs, "total_len": along + perp_len}


def _projected_xz_area(corners: list[list[float]]) -> float:
    if len(corners) < 3:
        return 0.0
    area2 = 0.0
    for idx, corner in enumerate(corners):
        nxt = corners[(idx + 1) % len(corners)]
        area2 += float(corner[0]) * float(nxt[2]) - float(nxt[0]) * float(corner[2])
    return abs(area2) * 0.5


def _stitch_score(stitch: ExtractedStitchWall) -> float:
    if stitch.type == "stitch" and len(stitch.corners) >= 4:
        p0 = np.array([stitch.corners[0][0], stitch.corners[0][2]], dtype=float)
        p1 = np.array([stitch.corners[1][0], stitch.corners[1][2]], dtype=float)
        edge_len = float(np.linalg.norm(p1 - p0))
        return edge_len * _wall_height(stitch.corners)
    return _projected_xz_area(stitch.corners)


def _limit_stitches_to_contract(
    stitches: list[ExtractedStitchWall],
    rooms: list[ExtractedRoom],
) -> list[ExtractedStitchWall]:
    contract = _STITCH_TYPE_CONTRACTS.get(len(rooms))
    if contract is None:
        return stitches
    selected: set[int] = set()
    for stitch_type, target_count in contract.items():
        typed = [(idx, stitch) for idx, stitch in enumerate(stitches) if stitch.type == stitch_type]
        if len(typed) <= target_count:
            selected.update(idx for idx, _stitch in typed)
            continue
        ranked = sorted(typed, key=lambda item: (-_stitch_score(item[1]), item[1].id))
        selected.update(idx for idx, _stitch in ranked[:target_count])
    return [
        stitch
        for idx, stitch in enumerate(stitches)
        if idx in selected
    ]


def stitch_wall_gaps(rooms: list[ExtractedRoom]) -> list[ExtractedStitchWall]:
    story_rooms: dict[int, list[tuple[int, ExtractedRoom]]] = defaultdict(list)
    for room_idx, room in enumerate(rooms):
        story_rooms[room.story].append((room_idx, room))

    stitches: list[ExtractedStitchWall] = []
    for story, rooms_on_story in story_rooms.items():
        heights = [
            _wall_height(wall.corners)
            for _room_idx, room in rooms_on_story
            for wall in room.walls_computed
            if len(wall.corners) >= 4 and _wall_height(wall.corners) >= MIN_WALL_HEIGHT_M
        ]
        if not heights:
            continue
        median_h = float(np.median(heights))
        endpoints = []
        for room_idx, room in rooms_on_story:
            for wall_idx, wall in enumerate(room.walls_computed):
                corners = wall.corners
                if len(corners) < 4:
                    continue
                wall_h = _wall_height(corners)
                if wall_h < MIN_WALL_HEIGHT_M or wall_h < median_h * HEIGHT_RATIO:
                    continue
                ys = [float(corner[1]) for corner in corners]
                y_low = min(ys)
                y_high = max(ys)
                if wall.extension_strip:
                    y_high = max(max(float(point[1]) for point in strip) for strip in wall.extension_strip)
                endpoints.append((corners[0][0], corners[0][2], y_low, y_high, (room_idx, wall_idx), 0))
                endpoints.append((corners[1][0], corners[1][2], y_low, y_high, (room_idx, wall_idx), 1))

        used_pairs = set()
        for idx, endpoint in enumerate(endpoints):
            x1, z1, yb1, yt1, wk1, end1 = endpoint
            best_dist = MAX_GAP_M
            best_idx = -1
            for jdx, candidate in enumerate(endpoints):
                if idx == jdx:
                    continue
                x2, z2, _yb2, _yt2, wk2, _end2 = candidate
                if wk2 == wk1:
                    continue
                dist = math.hypot(x1 - x2, z1 - z2)
                if MIN_GAP_M <= dist < best_dist:
                    best_dist = dist
                    best_idx = jdx
            if best_idx < 0:
                continue

            x2, z2, yb2, yt2, wk2, end2 = endpoints[best_idx]
            if best_dist <= MUTUAL_THRESH_M:
                reverse_best_dist = MAX_GAP_M
                reverse_best = -1
                for kdx, reverse_candidate in enumerate(endpoints):
                    if kdx == best_idx:
                        continue
                    xk, zk, _ykb, _ykt, wkk, _ek = reverse_candidate
                    if wkk == wk2:
                        continue
                    dist = math.hypot(x2 - xk, z2 - zk)
                    if MIN_GAP_M <= dist < reverse_best_dist:
                        reverse_best_dist = dist
                        reverse_best = kdx
                if reverse_best != idx:
                    continue

            pair_key = tuple(sorted([(*wk1, end1), (*wk2, end2)]))
            if pair_key in used_pairs:
                continue
            used_pairs.add(pair_key)

            y_bot = max(float(yb1), float(yb2))
            y_top = min(float(yt1), float(yt2))
            if y_top - y_bot < MIN_WALL_HEIGHT_M:
                continue

            room_idx1, wall_idx1 = wk1
            room_idx2, wall_idx2 = wk2

            def add(stitch_type: str, corners: list[list[float]]) -> None:
                stitches.append(
                    ExtractedStitchWall(
                        id=f"{stitch_type}:{story}:{len(stitches)}",
                        corners=corners,
                        type=stitch_type,
                        story=story,
                        room_index=room_idx1,
                        room_indices=[room_idx1, room_idx2],
                    )
                )

            if best_dist < DIRECT_QUAD_MAX_GAP_M:
                add(
                    "stitch",
                    [[x1, y_bot, z1], [x2, y_bot, z2], [x2, y_top, z2], [x1, y_top, z1]],
                )
                continue

            wall1_corners = rooms[room_idx1].walls_computed[wall_idx1].corners
            wall2_corners = rooms[room_idx2].walls_computed[wall_idx2].corners
            dir1 = _wall_dir_xz(wall1_corners)
            dir2 = _wall_dir_xz(wall2_corners)
            out_sign1 = -1.0 if end1 == 0 else 1.0
            out_sign2 = -1.0 if end2 == 0 else 1.0
            u1_out = (out_sign1 * dir1[0], out_sign1 * dir1[1])
            u2_out = (out_sign2 * dir2[0], out_sign2 * dir2[1])

            candidates = [
                candidate
                for candidate in (
                    _build_l_candidate((x1, z1), (x2, z2), u1_out, u2_out),
                    _build_l_candidate((x2, z2), (x1, z1), u2_out, u1_out),
                )
                if candidate is not None and candidate["legs"]
            ]
            if not candidates:
                continue
            picked = min(candidates, key=lambda candidate: candidate["total_len"])
            cx, cz = picked["corner"]
            for (ax, az), (bx, bz) in picked["legs"]:
                add(
                    "stitch",
                    [[ax, y_bot, az], [bx, y_bot, bz], [bx, y_top, bz], [ax, y_top, az]],
                )
            add("stitch_floor", [[x1, y_bot, z1], [cx, y_bot, cz], [x2, y_bot, z2]])
            add("stitch_ceiling", [[x1, y_top, z1], [cx, y_top, cz], [x2, y_top, z2]])

    return _limit_stitches_to_contract(stitches, rooms)
