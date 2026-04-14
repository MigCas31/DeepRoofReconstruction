"""Wall-endpoint stitching helpers."""

import math
from collections import defaultdict

import numpy as np

from reconcile_v2.decision_logic import classify_stitch_decision

from .lineage import STEP_STITCH_WALLS, record


def recommend_stitch_actions(graph):
    """Return graph-driven wall stitching candidates.

    Legacy stitching still performs the geometry synthesis. This helper exposes
    a deterministic migration target based on `CONNECTS_TO` and wall role.
    """
    actions = []
    for edge in graph.edges:
        if edge.type != "CONNECTS_TO":
            continue
        left = graph.get_node(edge.from_id)
        right = graph.get_node(edge.to_id)
        if left is None or right is None:
            continue
        if left.type != "Surface" or right.type != "Surface":
            continue
        actions.append(classify_stitch_decision(graph, left, right, edge.evidence or {}))
    return actions


def stitch_wall_gaps(rooms_out):
    max_gap = 1.50
    min_gap = 0.06
    min_wall_height = 0.5
    height_ratio = 0.65
    mutual_thresh = 0.60
    cap_reach = 0.20  # how far floor/ceiling caps extend along parent walls

    story_rooms = defaultdict(list)
    for room_idx, room in enumerate(rooms_out):
        story_rooms[room["story"]].append((room_idx, room))

    stitch_walls = []
    for story, rooms in story_rooms.items():
        heights = []
        for _room_idx, room in rooms:
            for wall in room["walls_computed"]:
                corners = wall["corners"]
                if len(corners) < 4:
                    continue
                wall_h = abs(corners[2][1] - corners[0][1])
                if wall_h >= min_wall_height:
                    heights.append(wall_h)
        if not heights:
            continue

        median_h = float(np.median(heights))
        endpoints = []
        for room_idx, room in rooms:
            for wall_idx, wall in enumerate(room["walls_computed"]):
                corners = wall["corners"]
                if len(corners) < 4:
                    continue
                wall_h = abs(corners[2][1] - corners[0][1])
                if wall_h < min_wall_height or wall_h < median_h * height_ratio:
                    continue
                extension = wall.get("extension_strip")
                ext_top = (
                    max(max(point[1] for point in strip) for strip in extension)
                    if extension
                    else None
                )
                top0 = ext_top if ext_top is not None else corners[3][1]
                top1 = ext_top if ext_top is not None else corners[2][1]
                key = (room_idx, wall_idx)
                endpoints.append(
                    (corners[0][0], corners[0][2], corners[0][1], top0, key, 0)
                )
                endpoints.append(
                    (corners[1][0], corners[1][2], corners[1][1], top1, key, 1)
                )

        used_pairs = set()
        for idx in range(len(endpoints)):
            x1, z1, yb1, yt1, wk1, end1 = endpoints[idx]
            best_dist = max_gap
            best_idx = -1
            for jdx in range(len(endpoints)):
                if idx == jdx:
                    continue
                x2, z2, _yb2, _yt2, wk2, _end2 = endpoints[jdx]
                if wk2 == wk1:
                    continue
                dist = math.hypot(x1 - x2, z1 - z2)
                if min_gap <= dist < best_dist:
                    best_dist = dist
                    best_idx = jdx

            if best_idx < 0:
                continue
            x2, z2, yb2, yt2, wk2, end2 = endpoints[best_idx]

            if best_dist <= mutual_thresh:
                reverse_best_dist = max_gap
                reverse_best = -1
                for kdx in range(len(endpoints)):
                    if kdx == best_idx:
                        continue
                    xk, zk, _ykb, _ykt, wkk, _ek = endpoints[kdx]
                    if wkk == wk2:
                        continue
                    d_val = math.hypot(x2 - xk, z2 - zk)
                    if min_gap <= d_val < reverse_best_dist:
                        reverse_best_dist = d_val
                        reverse_best = kdx
                if reverse_best != idx:
                    continue

            pair_key = tuple(sorted([(*wk1, end1), (*wk2, end2)]))
            if pair_key in used_pairs:
                continue
            used_pairs.add(pair_key)

            y_bot = max(yb1, yb2)
            y_top = min(yt1, yt2)
            if y_top - y_bot < min_wall_height:
                continue

            entry = {
                "corners": [
                    [x1, y_bot, z1],
                    [x2, y_bot, z2],
                    [x2, y_top, z2],
                    [x1, y_top, z1],
                ],
                "story": story,
                "type": "stitch",
            }
            record(entry, STEP_STITCH_WALLS, "created")
            stitch_walls.append(entry)

            # Floor and ceiling caps: extend a small quad along each parent
            # wall's direction to seal the top and bottom of the stitch gap.
            room_idx1, wall_idx1 = wk1
            room_idx2, wall_idx2 = wk2
            wall1_corners = rooms_out[room_idx1]["walls_computed"][wall_idx1]["corners"]
            wall2_corners = rooms_out[room_idx2]["walls_computed"][wall_idx2]["corners"]

            # Direction along each parent wall (from endpoint 0 to endpoint 1)
            def _wall_dir_xz(corners):
                dx = corners[1][0] - corners[0][0]
                dz = corners[1][2] - corners[0][2]
                length = math.hypot(dx, dz)
                if length < 1e-6:
                    return (0.0, 0.0)
                return (dx / length, dz / length)

            dir1 = _wall_dir_xz(wall1_corners)
            dir2 = _wall_dir_xz(wall2_corners)

            # The cap extends inward from each stitch endpoint along the
            # parent wall.  end==0 means the endpoint is at corner[0], so
            # inward is the +direction; end==1 means corner[1], so inward
            # is the -direction.
            sign1 = 1.0 if end1 == 0 else -1.0
            sign2 = 1.0 if end2 == 0 else -1.0

            reach = min(cap_reach, best_dist)

            p1_inner_x = x1 + sign1 * dir1[0] * reach
            p1_inner_z = z1 + sign1 * dir1[1] * reach
            p2_inner_x = x2 + sign2 * dir2[0] * reach
            p2_inner_z = z2 + sign2 * dir2[1] * reach

            floor_cap = {
                "corners": [
                    [x1, y_bot, z1],
                    [x2, y_bot, z2],
                    [p2_inner_x, y_bot, p2_inner_z],
                    [p1_inner_x, y_bot, p1_inner_z],
                ],
                "story": story,
                "type": "stitch_floor",
            }
            record(floor_cap, STEP_STITCH_WALLS, "created")
            stitch_walls.append(floor_cap)

            ceiling_cap = {
                "corners": [
                    [x1, y_top, z1],
                    [x2, y_top, z2],
                    [p2_inner_x, y_top, p2_inner_z],
                    [p1_inner_x, y_top, p1_inner_z],
                ],
                "story": story,
                "type": "stitch_ceiling",
            }
            record(ceiling_cap, STEP_STITCH_WALLS, "created")
            stitch_walls.append(ceiling_cap)

    return stitch_walls
