"""Ceiling inference and vertical wall extension helpers."""

import math

import numpy as np


def extend_wall_to_slab(corners, slab_y_above, epsilon=0.05, max_gap=0.80):
    if len(corners) < 3:
        return None

    ys = [corner[1] for corner in corners]
    max_y = max(ys)
    min_y = min(ys)
    wall_height = max_y - min_y
    if wall_height < 0.1:
        return None

    y_thresh = min_y + wall_height * 0.4
    top_indices = [idx for idx, y_val in enumerate(ys) if y_val > y_thresh]
    if not top_indices:
        return None

    need_ext = [idx for idx in top_indices if ys[idx] < slab_y_above - epsilon]
    if not need_ext:
        return None

    max_top_y = max(ys[idx] for idx in top_indices)
    if slab_y_above - max_top_y > max_gap:
        return None

    extended = [list(corner) for corner in corners]
    need_ext_set = set(need_ext)
    for idx in need_ext:
        extended[idx][1] = slab_y_above

    extension_strips = []
    top_indices_sorted = sorted(top_indices)
    for idx in range(len(top_indices_sorted) - 1):
        i0 = top_indices_sorted[idx]
        i1 = top_indices_sorted[idx + 1]
        orig_y0 = corners[i0][1]
        orig_y1 = corners[i1][1]
        ext_y0 = slab_y_above if i0 in need_ext_set else orig_y0
        ext_y1 = slab_y_above if i1 in need_ext_set else orig_y1
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


def infer_ceilings(rooms_out):
    slant_thresh = 0.15
    slope_thresh = 0.15
    xz_match_tol = 0.20

    for room in rooms_out:
        floor_polygon = room.get("floor_polygon", [])
        walls = room.get("walls_computed") or room.get("walls_merged", [])
        if len(floor_polygon) < 3 or not walls:
            continue

        has_slant = False
        for wall in walls:
            corners = wall["corners"]
            if len(corners) < 3:
                continue
            ys = [corner[1] for corner in corners]
            mid_y = (max(ys) + min(ys)) / 2.0
            top_corners = [corner for corner in corners if corner[1] > mid_y - 0.01]
            if len(top_corners) >= 2:
                top_range = max(corner[1] for corner in top_corners) - min(
                    corner[1] for corner in top_corners
                )
                if top_range > slant_thresh:
                    has_slant = True
                    break

        if not has_slant:
            continue

        ceiling_polygon = build_ceiling_from_wall_tops(
            floor_polygon, walls, xz_match_tol
        )
        if ceiling_polygon is None or len(ceiling_polygon) < 3:
            continue

        ceiling_ys = [point[1] for point in ceiling_polygon]
        y_range = max(ceiling_ys) - min(ceiling_ys)
        ceiling_type = "flat" if y_range < slope_thresh else "sloped"
        room["ceiling_polygon"] = ceiling_polygon
        room["ceiling_type"] = ceiling_type
        room["ceiling_ridge_height"] = round(max(ceiling_ys), 4)
        room["ceiling_eave_height"] = round(min(ceiling_ys), 4)


def build_ceiling_from_wall_tops(floor_polygon, walls, xz_tol):
    def xz_dist(a, b):
        return math.hypot(a[0] - b[0], a[2] - b[2])

    wall_info = []
    for wall in walls:
        corners = wall["corners"]
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
        best_d = float("inf")
        best_corner = None
        for candidate in corners:
            dist = xz_dist(corner, candidate)
            if dist < best_d:
                best_d = dist
                best_corner = candidate
        return best_d, best_corner

    n = len(floor_polygon)
    edge_walls = [None] * n
    used = set()
    for edge_idx in range(n):
        v0 = floor_polygon[edge_idx]
        v1 = floor_polygon[(edge_idx + 1) % n]
        best_score = float("inf")
        best_idx = None
        for wi, wi_info in enumerate(wall_info):
            if wi in used:
                continue
            d0, _ = nearest_corner(v0, wi_info["bot"])
            d1, _ = nearest_corner(v1, wi_info["bot"])
            score = d0 + d1
            if score < best_score:
                best_score = score
                best_idx = wi
        if best_idx is not None and best_score < xz_tol * 2:
            edge_walls[edge_idx] = best_idx
            used.add(best_idx)

    ceiling_pts = []
    for edge_idx in range(n):
        wi = edge_walls[edge_idx]
        if wi is None:
            continue

        v0 = floor_polygon[edge_idx]
        v1 = floor_polygon[(edge_idx + 1) % n]
        top_corners = wall_info[wi]["top"]
        bot_corners = wall_info[wi]["bot"]

        start_bot = sorted((xz_dist(v0, bc), bc) for bc in bot_corners)[0][1]
        end_bot = sorted((xz_dist(v1, bc), bc) for bc in bot_corners)[0][1]

        def find_top_at_xz(bot_corner, _top_corners=top_corners):
            return sorted((xz_dist(bot_corner, tc), tc) for tc in _top_corners)[0][1]

        start_top = find_top_at_xz(start_bot)
        end_top = find_top_at_xz(end_bot)

        if len(top_corners) <= 2:
            ordered_top = [start_top, end_top]
        else:
            interior = []
            for corner in top_corners:
                if (
                    xz_dist(corner, start_bot) > xz_tol
                    and xz_dist(corner, end_bot) > xz_tol
                ):
                    interior.append(corner)

            edge_dir = np.array([v1[0] - v0[0], v1[2] - v0[2]])
            edge_len = np.linalg.norm(edge_dir)
            if edge_len > 1e-6:
                unit = edge_dir / edge_len
                interior.sort(
                    key=lambda c: np.dot(np.array([c[0] - v0[0], c[2] - v0[2]]), unit)
                )

            ordered_top = [start_top, *interior, end_top]

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


def flat_ceiling_fallback(rooms, slab_y):
    _ = slab_y
    wall_tops = []
    for room in rooms:
        for wall in room.get("walls_computed") or room.get("walls_merged", []):
            ys = [corner[1] for corner in wall["corners"]]
            if ys:
                wall_tops.append(max(ys))

    if not wall_tops:
        return

    ceil_y = round(float(np.median(wall_tops)), 4)
    for room in rooms:
        floor_polygon = room.get("floor_polygon", [])
        if len(floor_polygon) < 3:
            continue
        room["ceiling_polygon"] = [
            [round(v[0], 4), ceil_y, round(v[2], 4)] for v in floor_polygon
        ]
        room["ceiling_type"] = "flat"
        room["ceiling_ridge_height"] = ceil_y
        room["ceiling_eave_height"] = ceil_y


def find_closest_slab_y(wall_corners, slabs_above):
    if not slabs_above:
        return None
    wall_x = np.mean([corner[0] for corner in wall_corners])
    wall_z = np.mean([corner[2] for corner in wall_corners])
    best_dist = float("inf")
    best_y = None
    for slab_x, slab_z, slab_y in slabs_above:
        dist = math.hypot(wall_x - slab_x, wall_z - slab_z)
        if dist < best_dist:
            best_dist = dist
            best_y = slab_y
    return best_y
