"""Ceiling inference and vertical wall extension helpers."""

import math

import numpy as np


def reassign_raw_ceiling_planes_spatially(rooms_out):
    """Move each raw ceiling plane to the room whose floor it actually sits over.

    The per-room SVD matches a raw ceiling *file* to the best merged room via
    shared wall IDs, but Apple RoomPlan's captured ceiling mesh can span
    multiple rooms — a vaulted hallway, a shared pitched attic, etc. Without a
    spatial reassignment, every plane in the file lands on the single keyed
    room, which visually bleeds neighbouring rooms' ceilings onto the wrong
    footprint.

    For each plane, take its XZ centroid and pick the room (same story,
    building-local) whose floor polygon contains it. If no floor contains the
    centroid, fall back to the room with the largest 2D overlap with the plane.
    If nothing matches at all (should be rare — scan mesh drifting beyond every
    modelled room), keep the plane where it was so we don't silently drop data.
    """
    try:
        from shapely.geometry import Point, Polygon
    except ImportError:
        return

    room_polys = []
    for room in rooms_out:
        fp = room.get("floor_polygon") or []
        if len(fp) < 3:
            room_polys.append(None)
            continue
        try:
            poly = Polygon([(c[0], c[2]) for c in fp])
            if not poly.is_valid:
                poly = poly.buffer(0)
            room_polys.append(poly if poly.is_valid and not poly.is_empty else None)
        except Exception:
            room_polys.append(None)

    reassignments = [[] for _ in rooms_out]
    for src_idx, room in enumerate(rooms_out):
        src_story = room.get("story", 0)
        for plane in room.get("raw_ceiling_planes") or []:
            corners = plane.get("corners") or []
            if len(corners) < 3:
                reassignments[src_idx].append(plane)
                continue
            xs = [c[0] for c in corners]
            zs = [c[2] for c in corners]
            cx = sum(xs) / len(xs)
            cz = sum(zs) / len(zs)
            target_idx = None
            centroid = Point(cx, cz)
            for ridx, poly in enumerate(room_polys):
                if poly is None or rooms_out[ridx].get("story", 0) != src_story:
                    continue
                if poly.contains(centroid):
                    target_idx = ridx
                    break
            if target_idx is None:
                try:
                    plane_poly = Polygon([(c[0], c[2]) for c in corners])
                    if not plane_poly.is_valid:
                        plane_poly = plane_poly.buffer(0)
                except Exception:
                    plane_poly = None
                if plane_poly is not None and plane_poly.is_valid and not plane_poly.is_empty:
                    best_area = 0.0
                    for ridx, poly in enumerate(room_polys):
                        if poly is None or rooms_out[ridx].get("story", 0) != src_story:
                            continue
                        try:
                            inter = poly.intersection(plane_poly).area
                        except Exception:
                            inter = 0.0
                        if inter > best_area:
                            best_area = inter
                            target_idx = ridx
            if target_idx is None:
                target_idx = src_idx
            reassignments[target_idx].append(plane)

    for ridx, room in enumerate(rooms_out):
        room["raw_ceiling_planes"] = reassignments[ridx]


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


COHORT_TOLERANCE_M = 0.15
MIN_COHORT_COVERAGE = 0.70
MAX_OUTLIER_SPAN_FRAC = 0.25
MAX_DOMINANT_DELTA_M = 0.40
MIN_DOMINANT_DELTA_M = 0.10
FLOOR_MATCH_TOLERANCE_M = 0.10
COLINEAR_ANGLE_DEG = 8.0
COLINEAR_OFFSET_M = 0.15
COLINEAR_GAP_M = 0.80


def _wall_bottom_chord_xz(corners):
    """Return the longest chord among bottom corners as (p0, p1, length).

    Robust to non-canonical walls (5+ corners, arbitrary ordering) — selects
    corners within 1 cm of min(y) and picks the widest pair in XZ.
    """
    if len(corners) < 2:
        return None
    ys = [c[1] for c in corners]
    min_y = min(ys)
    bot = [c for c in corners if c[1] < min_y + 0.01]
    if len(bot) < 2:
        return None
    best_len = 0.0
    best_pair = None
    for i in range(len(bot)):
        for j in range(i + 1, len(bot)):
            dx = bot[i][0] - bot[j][0]
            dz = bot[i][2] - bot[j][2]
            d = math.hypot(dx, dz)
            if d > best_len:
                best_len = d
                best_pair = (bot[i], bot[j])
    if best_pair is None or best_len < 1e-4:
        return None
    return best_pair[0], best_pair[1], best_len


def _wall_record(corners):
    """Pre-compute top_y, bot_y, span, axis, mid for a wall — used by the cohort."""
    chord = _wall_bottom_chord_xz(corners)
    if chord is None:
        return None
    p0, p1, span = chord
    ys = [c[1] for c in corners]
    axis = ((p1[0] - p0[0]) / span, (p1[2] - p0[2]) / span)
    mid = ((p0[0] + p1[0]) * 0.5, (p0[2] + p1[2]) * 0.5)
    return {
        "top_y": float(max(ys)),
        "bot_y": float(min(ys)),
        "span": float(span),
        "axis": axis,
        "mid": mid,
    }


def _weighted_median(items):
    items = sorted(items, key=lambda t: t[0])
    total = sum(w for _, w in items)
    if total <= 0:
        return items[len(items) // 2][0]
    half = total / 2.0
    acc = 0.0
    for val, w in items:
        acc += w
        if acc >= half:
            return val
    return items[-1][0]


def compute_story_wall_top_cohort(rooms_out, story):
    """Find the dominant top-Y cohort for walls_computed on the given story.

    Returns None if no single cluster (tolerance ``COHORT_TOLERANCE_M``) covers
    at least ``MIN_COHORT_COVERAGE`` of the total span-weighted perimeter. The
    returned dict is the only input the per-wall gates need — it includes
    pre-computed records for every eligible wall on the story so that the
    colinearity check does not rebuild them.
    """
    records = []
    for room in rooms_out:
        if room.get("story", 0) != story:
            continue
        for wall in room.get("walls_computed") or []:
            rec = _wall_record(wall.get("corners") or [])
            if rec is None or rec["span"] < 0.05 or rec["top_y"] - rec["bot_y"] < 0.10:
                continue
            records.append(rec)
    if not records:
        return None

    total_perim = sum(r["span"] for r in records)
    if total_perim <= 0:
        return None

    sorted_by_top = sorted(records, key=lambda r: r["top_y"])
    clusters = [[sorted_by_top[0]]]
    for rec in sorted_by_top[1:]:
        if rec["top_y"] - clusters[-1][-1]["top_y"] <= COHORT_TOLERANCE_M:
            clusters[-1].append(rec)
        else:
            clusters.append([rec])

    best_cluster = max(
        clusters,
        key=lambda cl: sum(r["span"] for r in cl),
    )
    best_w = sum(r["span"] for r in best_cluster)
    coverage = best_w / total_perim
    if coverage < MIN_COHORT_COVERAGE:
        return None

    dominant_y = sum(r["top_y"] * r["span"] for r in best_cluster) / best_w
    cohort_floor_y = _weighted_median(
        [(r["bot_y"], r["span"]) for r in best_cluster]
    )

    return {
        "dominant_y": dominant_y,
        "coverage_frac": coverage,
        "total_perimeter": total_perim,
        "cohort_floor_y": cohort_floor_y,
        "records": records,
    }


def _is_colinear_neighbour(target_rec, other_rec):
    ax, az = target_rec["axis"]
    bx, bz = other_rec["axis"]
    cos_a = min(1.0, max(-1.0, abs(ax * bx + az * bz)))
    if math.degrees(math.acos(cos_a)) > COLINEAR_ANGLE_DEG:
        return False
    nx, nz = -az, ax
    tx, tz = target_rec["mid"]
    ox, oz = other_rec["mid"]
    perp = abs((ox - tx) * nx + (oz - tz) * nz)
    if perp > COLINEAR_OFFSET_M:
        return False
    along = (ox - tx) * ax + (oz - tz) * az
    gap = abs(along) - (target_rec["span"] + other_rec["span"]) * 0.5
    return gap <= COLINEAR_GAP_M


def should_extend_wall_to_dominant(corners, cohort):
    """Return the target top-Y if this wall passes every dominant-height gate.

    Gates applied in order (fast-fail):
      * wall top-Y is below dominant by at least ``MIN_DOMINANT_DELTA_M``
        and by no more than ``MAX_DOMINANT_DELTA_M``
      * wall span is at most ``MAX_OUTLIER_SPAN_FRAC`` of cohort perimeter
      * wall bottom-Y matches the cohort floor-Y within ``FLOOR_MATCH_TOLERANCE_M``
      * wall is colinear with at least one dominant-cohort neighbour
    """
    if cohort is None:
        return None
    rec = _wall_record(corners)
    if rec is None:
        return None
    dominant_y = cohort["dominant_y"]
    delta = dominant_y - rec["top_y"]
    if delta < MIN_DOMINANT_DELTA_M or delta > MAX_DOMINANT_DELTA_M:
        return None
    if rec["span"] > MAX_OUTLIER_SPAN_FRAC * cohort["total_perimeter"]:
        return None
    cohort_floor_y = cohort.get("cohort_floor_y")
    if cohort_floor_y is None:
        return None
    if abs(rec["bot_y"] - cohort_floor_y) > FLOOR_MATCH_TOLERANCE_M:
        return None
    for other in cohort["records"]:
        if other is rec:
            continue
        if abs(other["top_y"] - dominant_y) > COHORT_TOLERANCE_M:
            continue
        if _is_colinear_neighbour(rec, other):
            return dominant_y
    return None


def extend_wall_to_dominant(corners, dominant_y, epsilon=0.05):
    """Lift the wall's top corners to ``dominant_y``.

    Mirrors :func:`extend_wall_to_slab` so the resulting record has the same
    ``extended_corners``/``extension_strip`` shape the viewer already renders.
    ``should_extend_wall_to_dominant`` must have already approved the wall —
    this function performs only the geometric lift.
    """
    if len(corners) < 3:
        return None
    ys = [c[1] for c in corners]
    max_y = max(ys)
    min_y = min(ys)
    if max_y - min_y < 0.1:
        return None
    y_thresh = min_y + (max_y - min_y) * 0.4
    top_indices = [idx for idx, y in enumerate(ys) if y > y_thresh]
    if not top_indices:
        return None
    need_ext = [idx for idx in top_indices if ys[idx] < dominant_y - epsilon]
    if not need_ext:
        return None

    extended = [list(c) for c in corners]
    need_ext_set = set(need_ext)
    for idx in need_ext:
        extended[idx][1] = dominant_y

    extension_strips = []
    top_sorted = sorted(top_indices)
    for a in range(len(top_sorted) - 1):
        i0, i1 = top_sorted[a], top_sorted[a + 1]
        orig_y0, orig_y1 = corners[i0][1], corners[i1][1]
        ext_y0 = dominant_y if i0 in need_ext_set else orig_y0
        ext_y1 = dominant_y if i1 in need_ext_set else orig_y1
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
    wall_corners,
    wall_top_y,
    slabs_above,
    min_margin=0.05,
    max_gap=None,
    stack_tol=0.10,
):
    """Pick the slab above whose XZ footprint is spatially closest to the wall midpoint.

    slabs_above: list of (shapely_polygon_xz, floor_y). Polygon coords are (x, z).
    Returns the chosen slab's floor_y, or None if no slab is strictly above
    `wall_top_y + min_margin` (and within `max_gap` if provided).

    `max_gap` mirrors `extend_wall_to_slab`'s gate: candidates with
    `slab_y - wall_top_y > max_gap` are skipped, so the picker can't prefer an
    unreachable high slab over a closer-but-less-central viable slab.

    `stack_tol` enforces the stacking constraint: only extend a wall when its
    midpoint sits inside (or within `stack_tol` metres of) an upper-story room
    floor polygon. Walls whose midpoint is farther than `stack_tol` from every
    candidate slab are air-facing — the user supplies those thicknesses from
    the envelope, so no auto-extension is needed. Prevents extensions in
    detached wings / outbuildings that have no room overhead.
    """
    if not slabs_above:
        return None
    from shapely.geometry import Point  # local import to keep module load light

    wx = float(np.mean([c[0] for c in wall_corners]))
    wz = float(np.mean([c[2] for c in wall_corners]))
    pt = Point(wx, wz)
    best_dist = float("inf")
    best_y = None
    for poly, slab_y in slabs_above:
        if slab_y <= wall_top_y + min_margin:
            continue
        if max_gap is not None and slab_y - wall_top_y > max_gap:
            continue
        dist = float(poly.distance(pt))
        if stack_tol is not None and dist > stack_tol:
            continue
        if dist < best_dist:
            best_dist = dist
            best_y = slab_y
    return best_y
