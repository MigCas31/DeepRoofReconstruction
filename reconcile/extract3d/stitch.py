"""Wall-endpoint stitching helpers."""

import math
from collections import defaultdict

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.validation import make_valid

from reconcile_v2.decision_logic import classify_stitch_decision

from .lineage import STEP_STITCH_WALLS, record

_ = Point  # keep formatter from stripping the used-at-runtime import

# --- notch-aware snap (shared by extract_3d.py and extract3d/stitch.py) ------
_SNAP_PARALLEL_DOT_MIN = 0.98
_SNAP_PERP_MIN_M = 0.4
_SNAP_PERP_MAX_M = 2.0
_SNAP_ALONG_OVERLAP_MIN_M = 0.2
_SNAP_PERP_UNIFORM_TOL_M = 0.08      # all corners of an entry must share perp within this
_SNAP_CORNER_XZ_MATCH_M = 0.005      # caps follow via (x,z)-match to a snapped wall
_SNAP_NOTCH_SAMPLES = 21
_SNAP_NOTCH_COVERED_FRAC = 0.60      # covered-outside fraction required
_SNAP_NOTCH_INSIDE_MAX = 0.20        # inside-stitch fraction must stay below this
_SNAP_NOTCH_EXT_MARGIN_M = 0.2       # along offset past stitch ends before sampling "outside"
_SNAP_NOTCH_EXT_SPAN_M = 1.0         # sampling window size on each side past stitch ends


def _snap_safe_polygon(xz_points):
    if len(xz_points) < 3:
        return None
    poly = Polygon(xz_points)
    if not poly.is_valid:
        fixed = make_valid(poly)
        if hasattr(fixed, "geoms"):
            polys = [g for g in fixed.geoms if isinstance(g, Polygon)]
            poly = max(polys, key=lambda p: p.area) if polys else poly
        elif isinstance(fixed, Polygon):
            poly = fixed
    return poly if poly.is_valid and not poly.is_empty else None


def _snap_wall_frame(corners):
    """Return (origin_xz, dir_xz, length) from a wall's first edge, or None."""
    if not corners or len(corners) < 2:
        return None
    a = (float(corners[0][0]), float(corners[0][2]))
    b = (float(corners[1][0]), float(corners[1][2]))
    dx, dz = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dz)
    if length < 0.1:
        return None
    return a, (dx / length, dz / length), length


def _snap_project(origin, direction, point):
    """Return (along, perp) of ``point`` in the wall's local frame."""
    dx, dz = point[0] - origin[0], point[1] - origin[1]
    along = dx * direction[0] + dz * direction[1]
    perp = dx * (-direction[1]) + dz * direction[0]
    return along, perp


def _snap_world(origin, direction, along, perp):
    normal = (-direction[1], direction[0])
    return (
        origin[0] + along * direction[0] + perp * normal[0],
        origin[1] + along * direction[1] + perp * normal[1],
    )


def _snap_notch_ok(wall_origin, wall_dir, wall_len, stitch_along, perp_offset, room_poly):
    """Reproduce the Phase-A notch predicate against a shapely polygon."""
    if room_poly is None:
        return False
    a_lo, a_hi = stitch_along
    strip_mid_perp = perp_offset / 2.0

    inside_hits = 0
    for i in range(_SNAP_NOTCH_SAMPLES):
        t = i / (_SNAP_NOTCH_SAMPLES - 1)
        a = a_lo + t * (a_hi - a_lo)
        p = _snap_world(wall_origin, wall_dir, a, strip_mid_perp)
        if room_poly.covers(Point(p[0], p[1])):
            inside_hits += 1
    inside_frac = inside_hits / _SNAP_NOTCH_SAMPLES

    windows = [
        (max(0.0, a_lo - _SNAP_NOTCH_EXT_MARGIN_M - _SNAP_NOTCH_EXT_SPAN_M),
         max(0.0, a_lo - _SNAP_NOTCH_EXT_MARGIN_M)),
        (min(wall_len, a_hi + _SNAP_NOTCH_EXT_MARGIN_M),
         min(wall_len, a_hi + _SNAP_NOTCH_EXT_MARGIN_M + _SNAP_NOTCH_EXT_SPAN_M)),
    ]
    outside_hits = 0
    outside_total = 0
    for w_lo, w_hi in windows:
        if w_hi - w_lo < 0.1:
            continue
        for i in range(_SNAP_NOTCH_SAMPLES):
            t = i / (_SNAP_NOTCH_SAMPLES - 1)
            a = w_lo + t * (w_hi - w_lo)
            p = _snap_world(wall_origin, wall_dir, a, strip_mid_perp)
            outside_total += 1
            if room_poly.covers(Point(p[0], p[1])):
                outside_hits += 1
    outside_frac = outside_hits / outside_total if outside_total else 0.0

    return outside_frac >= _SNAP_NOTCH_COVERED_FRAC and inside_frac <= _SNAP_NOTCH_INSIDE_MAX


_DEDUP_XZ_TOL_M = 0.15   # xz-bbox bucket size for matching vertical stitch quads
_DEDUP_Y_TOL_M  = 0.15   # y-extent bucket size for matching vertical stitch quads
_DEDUP_MIN_SHARED_CORNERS = 2


def dedup_duplicate_vertical_stitches(stitch_walls):
    """Drop vertical ``type='stitch'`` quads that duplicate an earlier one.

    Two different wall-endpoint pairs can independently emit a stitch on the
    same physical wall plane — e.g. when a single wall separates room 1 from
    both room 0 and room 5, the pair (wall_a_end0 ↔ wall_AEAB_end0) and the
    pair (wall_b_end0 ↔ wall_AEAB_end1) each extrude an outward L-leg along
    AEAB. ``used_pairs`` does not catch this because the input endpoint
    tuples differ. Without dedup, the viewer overlays two near-identical
    translucent quads and their outline edges cross visually as a bow-tie.

    Only ``type='stitch'`` entries are compared. Cap triangles
    (``stitch_floor`` / ``stitch_ceiling``) fan into genuinely different
    wedges per pair and are left untouched.
    """
    kept = []
    buckets = defaultdict(list)
    for entry in stitch_walls:
        if entry.get("type") != "stitch":
            kept.append(entry)
            continue
        corners = entry.get("corners") or []
        if len(corners) < 3:
            kept.append(entry)
            continue
        xs = [c[0] for c in corners]
        zs = [c[2] for c in corners]
        ys = [c[1] for c in corners]
        sig = (
            round(min(xs) / _DEDUP_XZ_TOL_M) * _DEDUP_XZ_TOL_M,
            round(min(zs) / _DEDUP_XZ_TOL_M) * _DEDUP_XZ_TOL_M,
            round(max(xs) / _DEDUP_XZ_TOL_M) * _DEDUP_XZ_TOL_M,
            round(max(zs) / _DEDUP_XZ_TOL_M) * _DEDUP_XZ_TOL_M,
            round(min(ys) / _DEDUP_Y_TOL_M)  * _DEDUP_Y_TOL_M,
            round(max(ys) / _DEDUP_Y_TOL_M)  * _DEDUP_Y_TOL_M,
        )
        members = buckets[sig]
        is_dup = False
        for prev_corners in members:
            shared = 0
            for ca in corners:
                for cb in prev_corners:
                    if (
                        math.hypot(ca[0] - cb[0], ca[2] - cb[2]) < _DEDUP_XZ_TOL_M
                        and abs(ca[1] - cb[1]) < _DEDUP_Y_TOL_M
                    ):
                        shared += 1
                        break
            if shared >= _DEDUP_MIN_SHARED_CORNERS:
                is_dup = True
                break
        if is_dup:
            continue
        buckets[sig].append(corners)
        kept.append(entry)
    return kept


def snap_stitches_to_non_owner_walls(rooms_out, stitch_walls):
    """Post-process ``stitch_walls`` to move scan-boundary gaps onto the adjacent wall.

    When a synthetic stitch runs parallel to a non-owner room's wall with a ~1 m
    perpendicular offset, AND that non-owner room's floor polygon reaches the
    wall just past the stitch's ends while notching inward inside the stitch
    zone, the gap is almost always a scan-registration artifact rather than a
    real void. The snap translates the stitch's (x, z) onto the wall's plane,
    preserving its y range. See ``scripts/simulate_stitch_snap.py`` for the
    cohort simulation that validated the predicate (248 repaired / 0 regressed
    across 62 buildings).

    Mutates ``stitch_walls`` in place. Entries that are snapped gain:
      - ``snapped_to_wall``: the non-owner wall id.
      - ``id`` (if absent): ``"snap:<wall_id>"`` so viewer locators stop falling
        back to the synthetic ``sw:<index>``.

    Caps (``stitch_floor`` / ``stitch_ceiling``) follow their wall by matching
    corner (x, z) positions to the snapped wall's original endpoints.
    """
    if not stitch_walls:
        return stitch_walls

    room_polys = {}
    for ri, room in enumerate(rooms_out):
        fp = room.get("floor_polygon") or []
        room_polys[ri] = _snap_safe_polygon(
            [(float(p[0]), float(p[2])) for p in fp]
        )

    walls_by_story = defaultdict(list)
    for ri, room in enumerate(rooms_out):
        story = int(room.get("story", 0))
        for wall in room.get("walls_computed", []):
            frame = _snap_wall_frame(wall.get("corners", []))
            if frame is None:
                continue
            walls_by_story[story].append((ri, wall, frame))

    # Pass 1: identify stitch walls to snap, collect (x,z) displacements.
    displacements = []  # list of (orig_xz, new_xz)
    for entry in stitch_walls:
        if entry.get("type") != "stitch":
            continue
        corners = entry.get("corners") or []
        if len(corners) < 4:
            continue
        frame = _snap_wall_frame(corners)
        if frame is None:
            continue
        s_origin, s_dir, _s_len = frame
        story = int(entry.get("story", 0))
        owner_rooms = set()
        owners = entry.get("room_indices")
        if owners:
            owner_rooms.update(r for r in owners if r is not None)
        if entry.get("room_index") is not None:
            owner_rooms.add(entry["room_index"])

        best = None  # (wall_id, new_xz_by_corner_idx)
        for ri, wall, (w_origin, w_dir, w_len) in walls_by_story.get(story, ()):
            if ri in owner_rooms:
                continue
            dot = s_dir[0] * w_dir[0] + s_dir[1] * w_dir[1]
            if abs(dot) < _SNAP_PARALLEL_DOT_MIN:
                continue

            perps = []
            alongs = []
            for c in corners:
                along, perp = _snap_project(
                    w_origin, w_dir, (float(c[0]), float(c[2]))
                )
                alongs.append(along)
                perps.append(perp)
            perp_mean = sum(perps) / len(perps)
            if max(abs(p - perp_mean) for p in perps) > _SNAP_PERP_UNIFORM_TOL_M:
                continue
            if not (_SNAP_PERP_MIN_M <= abs(perp_mean) <= _SNAP_PERP_MAX_M):
                continue

            a_lo, a_hi = min(alongs[:2]), max(alongs[:2])
            overlap = max(0.0, min(a_hi, w_len) - max(a_lo, 0.0))
            if overlap < _SNAP_ALONG_OVERLAP_MIN_M:
                continue

            notch = False
            for owner_ri in owner_rooms:
                if _snap_notch_ok(
                    w_origin, w_dir, w_len, (a_lo, a_hi), perp_mean,
                    room_polys.get(owner_ri),
                ):
                    notch = True
                    break
            if not notch:
                continue

            new_corners_xz = []
            for along, _perp in zip(alongs, perps):
                new_xz = _snap_world(w_origin, w_dir, along, 0.0)
                new_corners_xz.append(new_xz)
            best = (wall.get("id"), new_corners_xz)
            break

        if best is None:
            continue

        wall_id, new_corners_xz = best
        for idx, c in enumerate(corners):
            orig_xz = (float(c[0]), float(c[2]))
            new_xz = new_corners_xz[idx]
            displacements.append((orig_xz, new_xz))
            c[0] = new_xz[0]
            c[2] = new_xz[1]
        if wall_id:
            entry["snapped_to_wall"] = wall_id
            entry.setdefault("id", f"snap:{wall_id}")
        record(entry, STEP_STITCH_WALLS, "snapped_to_non_owner_wall")

    # Pass 2: drag any stitch entry corners (caps AND L-shape partner walls) that
    # share (x,z) with a snapped wall's original endpoints. Unsnapped partner walls
    # get their shared corner C dragged so the L-shape stays connected; caps
    # triangulating (P1, C, P2) likewise track the projected positions.
    if displacements:
        for entry in stitch_walls:
            if entry.get("snapped_to_wall"):
                continue
            if entry.get("type") not in ("stitch", "stitch_floor", "stitch_ceiling"):
                continue
            for c in entry.get("corners") or []:
                cx, cz = float(c[0]), float(c[2])
                for orig_xz, new_xz in displacements:
                    if (
                        abs(cx - orig_xz[0]) <= _SNAP_CORNER_XZ_MATCH_M
                        and abs(cz - orig_xz[1]) <= _SNAP_CORNER_XZ_MATCH_M
                    ):
                        c[0] = new_xz[0]
                        c[2] = new_xz[1]
                        break

    return stitch_walls



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

            # Inward direction along each parent wall (toward the
            # opposite wall endpoint): end==0 → +dir, end==1 → -dir.
            inward1 = (1.0 if end1 == 0 else -1.0)
            inward2 = (1.0 if end2 == 0 else -1.0)
            u1_in = (inward1 * dir1[0], inward1 * dir1[1])
            u2_in = (inward2 * dir2[0], inward2 * dir2[1])
            # Outward direction: extends the wall PAST its endpoint toward
            # where the missing corner would be. Opposite sign of inward.
            u1_out = (-u1_in[0], -u1_in[1])
            u2_out = (-u2_in[0], -u2_in[1])

            # Intersect outward rays  P1 + t*u1_out  and  P2 + s*u2_out in
            # XZ. Solve: u1_out*t - u2_out*s = P2 - P1.
            det = u2_out[0] * u1_out[1] - u1_out[0] * u2_out[1]
            corner = None
            if abs(det) > 1e-6:
                dx = x2 - x1
                dz = z2 - z1
                t = (u2_out[0] * dz - u2_out[1] * dx) / det
                s = (u1_out[0] * dz - u1_out[1] * dx) / det
                max_reach = max(best_dist * 1.5, mutual_thresh)
                if 0.0 <= t <= max_reach and 0.0 <= s <= max_reach:
                    corner = (x1 + t * u1_out[0], z1 + t * u1_out[1])

            if corner is not None:
                cx, cz = corner
                # Two perpendicular stitch walls meeting at the corner C,
                # each parallel to its parent wall.
                entry1 = {
                    "corners": [
                        [x1, y_bot, z1],
                        [cx, y_bot, cz],
                        [cx, y_top, cz],
                        [x1, y_top, z1],
                    ],
                    "story": story,
                    "type": "stitch",
                }
                record(entry1, STEP_STITCH_WALLS, "created")
                stitch_walls.append(entry1)

                entry2 = {
                    "corners": [
                        [x2, y_bot, z2],
                        [cx, y_bot, cz],
                        [cx, y_top, cz],
                        [x2, y_top, z2],
                    ],
                    "story": story,
                    "type": "stitch",
                }
                record(entry2, STEP_STITCH_WALLS, "created")
                stitch_walls.append(entry2)

                # Triangular floor/ceiling caps fill the area enclosed by
                # the two L-shape walls and the P1-P2 line.
                floor_cap = {
                    "corners": [
                        [x1, y_bot, z1],
                        [cx, y_bot, cz],
                        [x2, y_bot, z2],
                    ],
                    "story": story,
                    "type": "stitch_floor",
                }
                record(floor_cap, STEP_STITCH_WALLS, "created")
                stitch_walls.append(floor_cap)

                ceiling_cap = {
                    "corners": [
                        [x1, y_top, z1],
                        [cx, y_top, cz],
                        [x2, y_top, z2],
                    ],
                    "story": story,
                    "type": "stitch_ceiling",
                }
                record(ceiling_cap, STEP_STITCH_WALLS, "created")
                stitch_walls.append(ceiling_cap)
                continue

            # Secondary fallback: walls near-parallel or the two-wall
            # intersection was out of bounds. Build the L-shape on wall 1's
            # axis alone — one leg parallel to d1, one leg perpendicular.
            along = (x2 - x1) * dir1[0] + (z2 - z1) * dir1[1]
            cx = x1 + along * dir1[0]
            cz = z1 + along * dir1[1]
            parallel_len = abs(along)
            perp_len = math.hypot((x2 - x1) - along * dir1[0], (z2 - z1) - along * dir1[1])
            legs = []
            if parallel_len > 1e-3:
                legs.append(((x1, z1), (cx, cz)))
            if perp_len > 1e-3:
                legs.append(((cx, cz), (x2, z2)))

            if legs:
                for (ax, az), (bx, bz) in legs:
                    leg_entry = {
                        "corners": [
                            [ax, y_bot, az],
                            [bx, y_bot, bz],
                            [bx, y_top, bz],
                            [ax, y_top, az],
                        ],
                        "story": story,
                        "type": "stitch",
                    }
                    record(leg_entry, STEP_STITCH_WALLS, "created")
                    stitch_walls.append(leg_entry)
                floor_cap = {
                    "corners": [
                        [x1, y_bot, z1], [cx, y_bot, cz], [x2, y_bot, z2],
                    ],
                    "story": story,
                    "type": "stitch_floor",
                }
                record(floor_cap, STEP_STITCH_WALLS, "created")
                stitch_walls.append(floor_cap)
                ceiling_cap = {
                    "corners": [
                        [x1, y_top, z1], [cx, y_top, cz], [x2, y_top, z2],
                    ],
                    "story": story,
                    "type": "stitch_ceiling",
                }
                record(ceiling_cap, STEP_STITCH_WALLS, "created")
                stitch_walls.append(ceiling_cap)
                continue

            # Degenerate fallback: both legs ~zero — emit the direct
            # single-quad plus inline caps (shouldn't happen in practice).
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

            reach = min(cap_reach, best_dist)
            p1_inner_x = x1 + u1_in[0] * reach
            p1_inner_z = z1 + u1_in[1] * reach
            p2_inner_x = x2 + u2_in[0] * reach
            p2_inner_z = z2 + u2_in[1] * reach

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

    stitch_walls = snap_stitches_to_non_owner_walls(rooms_out, stitch_walls)
    return dedup_duplicate_vertical_stitches(stitch_walls)
