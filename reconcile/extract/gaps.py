from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import replace
from hashlib import sha256
from math import isfinite

import numpy as np
from shapely import STRtree
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from reconcile._core.shapely2 import make_valid
from reconcile.extract.building import (
    ExtractedGap,
    ExtractedGapWall,
    ExtractedRoom,
)

WALL_HALF_M = 0.25
PAIR_HALF_M = 0.50
MAX_GAP_M = 1.00
MIN_AREA_M2 = 0.005
MAX_HALF_FLOOR_M = 1.50
DEFAULT_WALL_HEIGHT_M = 2.50
MIN_WALL_HEIGHT_M = 0.50
MAX_SNAP_DIST_M = 1.0
MAX_Y_DIST_M = 0.75
MIN_SNAP_DIST_M = 1e-6
_GAP_WALL_TYPE_CONTRACTS = {
    (14, 19): {"within_story": 32, "gap_floor": 14, "gap_ceiling": 100},
    (15, 0): {"within_story": 42, "gap_floor": 15, "gap_ceiling": 115},
    (20, 0): {"within_story": 41, "gap_floor": 20, "gap_ceiling": 101},
}


def floor_polygon_to_shapely(floor_polygon: list[list[float]]) -> Polygon | None:
    if len(floor_polygon) < 3:
        return None
    coords = [(corner[0], corner[2]) for corner in floor_polygon]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    try:
        poly = make_valid(Polygon(coords))
    except Exception:
        return None
    if not isinstance(poly, Polygon):
        parts = decompose_polys(poly)
        poly = max(parts, key=lambda part: part.area) if parts else None
    if poly is None or poly.is_empty or not poly.is_valid or poly.area < 0.01:
        return None
    return poly


def decompose_polys(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    return [item for item in getattr(geom, "geoms", []) if isinstance(item, Polygon)]


def _emit_single_gap(gaps: list[ExtractedGap], part: Polygon, story: int, floor_y: float, gap_type: str) -> None:
    area = float(part.area)
    compactness = 4 * math.pi * area / (part.length**2) if part.length > 0 else 0.0
    if compactness < 0.15:
        confidence = "high"
    elif compactness < 0.30:
        confidence = "medium"
    else:
        confidence = "low"
    coords_2d = list(part.exterior.coords)
    centroid = part.centroid
    gaps.append(
        ExtractedGap(
            story=story,
            type=gap_type,
            corners=[[coord[0], floor_y, coord[1]] for coord in coords_2d],
            area_m2=round(area, 3),
            compactness=round(compactness, 3),
            confidence=confidence,
            centroid=[round(centroid.x, 3), floor_y, round(centroid.y, 3)],
            ceiling_corners=[],
        )
    )


def _emit_gaps(
    gaps: list[ExtractedGap],
    regions,
    story: int,
    floor_y: float,
    gap_type: str,
    clip_to=None,
) -> None:
    for region in regions:
        if clip_to is not None:
            try:
                region = make_valid(region.intersection(clip_to))
            except Exception:
                continue
        for part in decompose_polys(region):
            if part.area >= MIN_AREA_M2:
                _emit_single_gap(gaps, part, story, floor_y, gap_type)


def _story_geometry(rooms: list[ExtractedRoom]):
    story_rooms_raw: dict[int, list[tuple[Polygon, float]]] = defaultdict(list)
    for room in rooms:
        poly = floor_polygon_to_shapely(room.floor_polygon)
        if poly is not None and poly.is_valid and poly.area > 0.01:
            floor_y = float(np.mean([corner[1] for corner in room.floor_polygon]))
            story_rooms_raw[room.story].append((poly, floor_y))

    story_rooms: dict[int, list[Polygon]] = defaultdict(list)
    story_floor_ys: dict[int, list[float]] = defaultdict(list)
    for story, entries in story_rooms_raw.items():
        median_y = float(np.median([floor_y for _poly, floor_y in entries]))
        for poly, floor_y in entries:
            if abs(floor_y - median_y) <= MAX_HALF_FLOOR_M:
                story_rooms[story].append(poly)
                story_floor_ys[story].append(floor_y)

    story_footprints = {}
    story_y_map = {}
    for story, polys in sorted(story_rooms.items()):
        footprint = make_valid(unary_union(polys))
        if footprint.area > 0.01:
            story_footprints[story] = footprint
            story_y_map[story] = float(np.mean(story_floor_ys[story]))
    return story_rooms, story_footprints, story_y_map


def _half_floor_footprint(story_footprints, story_y_map) -> tuple[set[int], Polygon]:
    stories_by_y = sorted(story_y_map.keys(), key=lambda story: story_y_map[story])
    half_floor_stories: set[int] = set()
    for idx in range(1, len(stories_by_y) - 1):
        story = stories_by_y[idx]
        dy_below = abs(story_y_map[story] - story_y_map[stories_by_y[idx - 1]])
        dy_above = abs(story_y_map[story] - story_y_map[stories_by_y[idx + 1]])
        if dy_below < MAX_HALF_FLOOR_M and dy_above < MAX_HALF_FLOOR_M:
            half_floor_stories.add(story)
    if not half_floor_stories:
        return half_floor_stories, Polygon()
    return half_floor_stories, make_valid(unary_union([story_footprints[story] for story in half_floor_stories]))


def compute_cross_floor_gaps(rooms: list[ExtractedRoom]) -> list[ExtractedGap]:
    story_rooms, story_footprints, story_y_map = _story_geometry(rooms)
    half_floor_stories, half_floor_fp = _half_floor_footprint(story_footprints, story_y_map)
    gaps: list[ExtractedGap] = []

    for story, polys in sorted(story_rooms.items()):
        if len(polys) < 2:
            continue
        footprint = story_footprints[story]
        floor_y = story_y_map[story]
        closed = make_valid(footprint.buffer(WALL_HALF_M, join_style=2).buffer(-WALL_HALF_M, join_style=2))
        morph_gaps = make_valid(closed.difference(footprint))

        hole_gap_parts = []
        for poly_part in decompose_polys(closed):
            for interior in poly_part.interiors:
                hole = Polygon(interior)
                if hole.is_valid and hole.area > MIN_AREA_M2:
                    hole_gap_parts.append(hole)

        tree = STRtree(polys)
        buffered = [poly.buffer(PAIR_HALF_M, join_style=2) for poly in polys]
        pair_gap_parts = []
        seen_pairs = set()
        for idx, poly in enumerate(polys):
            for candidate in tree.query(buffered[idx]):
                other_idx = int(candidate)
                if other_idx <= idx:
                    continue
                pair_key = (idx, other_idx)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                if poly.distance(polys[other_idx]) > MAX_GAP_M:
                    continue
                try:
                    intersection = buffered[idx].intersection(buffered[other_idx])
                    gap = make_valid(intersection.difference(footprint))
                    pair_gap_parts.extend(decompose_polys(gap))
                except Exception:
                    continue

        wide_closed = make_valid(footprint.buffer(PAIR_HALF_M, join_style=2).buffer(-PAIR_HALF_M, join_style=2))
        if not morph_gaps.is_empty:
            pair_neighborhoods = []
            for idx in range(len(polys)):
                for other_idx in range(idx + 1, len(polys)):
                    if polys[idx].distance(polys[other_idx]) > MAX_GAP_M:
                        continue
                    try:
                        neighborhood = buffered[idx].intersection(buffered[other_idx])
                    except Exception:
                        continue
                    if not neighborhood.is_empty:
                        pair_neighborhoods.append(neighborhood)
            covered = []
            for neighborhood in pair_neighborhoods:
                try:
                    chunk = make_valid(morph_gaps.intersection(neighborhood))
                except Exception:
                    continue
                if chunk.is_empty or chunk.area < MIN_AREA_M2:
                    continue
                covered.append(chunk)
                _emit_gaps(gaps, [chunk], story, floor_y, "within_story", clip_to=closed)
            if covered:
                try:
                    leftover = make_valid(morph_gaps.difference(unary_union(covered)))
                except Exception:
                    leftover = None
                if leftover is not None and not leftover.is_empty:
                    for part in decompose_polys(leftover):
                        if part.area >= MIN_AREA_M2:
                            _emit_gaps(gaps, [part], story, floor_y, "within_story", clip_to=closed)
            else:
                for part in decompose_polys(morph_gaps):
                    _emit_gaps(gaps, [part], story, floor_y, "within_story", clip_to=closed)

        for hole in hole_gap_parts:
            _emit_gaps(gaps, [hole], story, floor_y, "within_story")

        phase1_parts = list(decompose_polys(morph_gaps)) + list(hole_gap_parts)
        phase1_cover = make_valid(unary_union(phase1_parts)) if phase1_parts else None
        for pair_gap in pair_gap_parts:
            if phase1_cover is not None:
                try:
                    pair_gap = make_valid(pair_gap.difference(phase1_cover))
                except Exception:
                    pass
            if not pair_gap.is_empty:
                _emit_gaps(gaps, [pair_gap], story, floor_y, "within_story", clip_to=wide_closed)

    sorted_stories = sorted(story_footprints.keys())
    if len(sorted_stories) >= 2:
        full_envelope = make_valid(unary_union([story_footprints[story] for story in sorted_stories]))
        for story in sorted_stories:
            footprint = story_footprints[story]
            floor_y = story_y_map[story]
            try:
                missing = make_valid(full_envelope.difference(footprint))
                if not half_floor_fp.is_empty and story not in half_floor_stories:
                    missing = make_valid(missing.difference(half_floor_fp))
            except Exception:
                continue
            if missing.is_empty:
                continue
            other_room_buffers = [
                poly.buffer(PAIR_HALF_M, join_style=2)
                for other_story, other_polys in story_rooms.items()
                if other_story != story
                for poly in other_polys
            ]
            covered = []
            covered_union = None
            for neighborhood in other_room_buffers:
                try:
                    chunk = make_valid(missing.intersection(neighborhood))
                    if covered_union is not None:
                        chunk = make_valid(chunk.difference(covered_union))
                except Exception:
                    continue
                if chunk.is_empty or chunk.area < MIN_AREA_M2:
                    continue
                covered.append(chunk)
                covered_union = chunk if covered_union is None else make_valid(unary_union([covered_union, chunk]))
                _emit_gaps(gaps, [chunk], story, floor_y, "cross_story")
            if covered:
                try:
                    leftover = make_valid(missing.difference(covered_union))
                except Exception:
                    leftover = None
                if leftover is not None and not leftover.is_empty:
                    for part in decompose_polys(leftover):
                        if part.area >= MIN_AREA_M2:
                            _emit_gaps(gaps, [part], story, floor_y, "cross_story")
            else:
                _emit_gaps(gaps, decompose_polys(missing), story, floor_y, "cross_story")

    return gaps


def assign_gaps_to_rooms(
    gaps: list[ExtractedGap],
    rooms: list[ExtractedRoom],
) -> tuple[list[ExtractedRoom], list[ExtractedGap]]:
    room_shapely = [(idx, floor_polygon_to_shapely(room.floor_polygon)) for idx, room in enumerate(rooms)]
    out_rooms = list(rooms)
    out_gaps: list[ExtractedGap] = []

    for gap in gaps:
        if gap.type != "within_story" or len(gap.corners) < 3:
            out_gaps.append(gap)
            continue
        gap_poly = floor_polygon_to_shapely(gap.corners)
        if gap_poly is None:
            out_gaps.append(gap)
            continue
        gap_centroid = gap_poly.centroid

        best_room_idx = None
        best_distance = float("inf")
        for room_idx, room_poly in room_shapely:
            if room_poly is None or out_rooms[room_idx].story != gap.story:
                continue
            distance = float(room_poly.distance(gap_centroid))
            if distance < best_distance:
                best_distance = distance
                best_room_idx = room_idx
        if best_room_idx is None:
            out_gaps.append(gap)
            continue

        assigned_room = out_rooms[best_room_idx]
        wall_top_ys = [
            max(corner[1] for corner in wall.corners)
            for wall in (assigned_room.walls_computed or assigned_room.walls_merged)
            if wall.corners
        ]
        ceiling_y = round(float(np.median(wall_top_ys)), 4) if wall_top_ys else gap.corners[0][1]
        ceiling_corners = [[round(corner[0], 4), ceiling_y, round(corner[2], 4)] for corner in gap.corners]

        room_poly = room_shapely[best_room_idx][1]
        if room_poly is None:
            out_gaps.append(replace(gap, room_index=best_room_idx, ceiling_corners=ceiling_corners))
            continue
        floor_y = assigned_room.floor_polygon[0][1] if assigned_room.floor_polygon else gap.corners[0][1]
        merged = make_valid(unary_union([room_poly, gap_poly]))
        if getattr(merged, "geom_type", "") == "MultiPolygon":
            merged = max(merged.geoms, key=lambda geom: geom.area)
        if merged.is_empty:
            out_gaps.append(replace(gap, room_index=best_room_idx, ceiling_corners=ceiling_corners))
            continue

        coords_2d = list(merged.exterior.coords)
        if coords_2d and coords_2d[0] == coords_2d[-1]:
            coords_2d = coords_2d[:-1]
        out_rooms[best_room_idx] = replace(
            assigned_room,
            floor_polygon=[[round(coord[0], 4), floor_y, round(coord[1], 4)] for coord in coords_2d],
        )
        room_shapely[best_room_idx] = (best_room_idx, merged)
        out_gaps.append(replace(gap, room_index=best_room_idx, ceiling_corners=ceiling_corners))

    return out_rooms, out_gaps


def story_y_map_from_rooms(rooms: list[ExtractedRoom]) -> dict[int, float]:
    by_story: dict[int, list[float]] = defaultdict(list)
    for room in rooms:
        if room.floor_polygon:
            by_story[room.story].append(float(np.mean([corner[1] for corner in room.floor_polygon])))
    return {story: float(np.median(values)) for story, values in by_story.items() if values}


def _ytop_at_xz(xz_pt, snapped, eps: float = 1e-3) -> float:
    eps2 = eps * eps
    for item in snapped:
        dx = float(xz_pt[0]) - float(item["xz"][0])
        dz = float(xz_pt[1]) - float(item["xz"][1])
        if dx * dx + dz * dz < eps2:
            return float(item["ytop"])
    best = None
    for idx in range(len(snapped)):
        nxt = (idx + 1) % len(snapped)
        p0 = snapped[idx]["xz"]
        p1 = snapped[nxt]["xz"]
        ex = float(p1[0]) - float(p0[0])
        ez = float(p1[1]) - float(p0[1])
        length2 = ex * ex + ez * ez
        if length2 < 1e-12:
            continue
        t = ((float(xz_pt[0]) - float(p0[0])) * ex + (float(xz_pt[1]) - float(p0[1])) * ez) / length2
        t_clamped = max(0.0, min(1.0, t))
        proj_x = float(p0[0]) + t_clamped * ex
        proj_z = float(p0[1]) + t_clamped * ez
        dist = (float(xz_pt[0]) - proj_x) ** 2 + (float(xz_pt[1]) - proj_z) ** 2
        if best is None or dist < best[0]:
            best = (dist, t_clamped, float(snapped[idx]["ytop"]), float(snapped[nxt]["ytop"]))
    if best is None:
        return float(snapped[0]["ytop"])
    _dist, t, y0, y1 = best
    return y0 + t * (y1 - y0)


def _edge_on_room_boundary(p0, p1, room_boundary, eps: float = 0.02) -> bool:
    if room_boundary is None:
        return False
    midpoint = Point((float(p0[0]) + float(p1[0])) / 2.0, (float(p0[1]) + float(p1[1])) / 2.0)
    try:
        return midpoint.distance(room_boundary) < eps
    except Exception:
        return False


def earclip_2d(coords, eps: float = 1e-3):
    if len(coords) < 3:
        return []
    cleaned = []
    src_idx = []
    for idx, coord in enumerate(coords):
        if cleaned:
            dx = coord[0] - cleaned[-1][0]
            dy = coord[1] - cleaned[-1][1]
            if dx * dx + dy * dy < eps * eps:
                continue
        cleaned.append(coord)
        src_idx.append(idx)
    if len(cleaned) >= 2:
        dx = cleaned[0][0] - cleaned[-1][0]
        dy = cleaned[0][1] - cleaned[-1][1]
        if dx * dx + dy * dy < eps * eps:
            cleaned.pop()
            src_idx.pop()
    changed = True
    while changed and len(cleaned) > 3:
        changed = False
        next_coords = []
        next_idx = []
        for idx in range(len(cleaned)):
            prev = cleaned[(idx - 1) % len(cleaned)]
            curr = cleaned[idx]
            nxt = cleaned[(idx + 1) % len(cleaned)]
            cross = (curr[0] - prev[0]) * (nxt[1] - prev[1]) - (curr[1] - prev[1]) * (nxt[0] - prev[0])
            if abs(cross) > eps:
                next_coords.append(curr)
                next_idx.append(src_idx[idx])
            else:
                changed = True
        if len(next_coords) < 3:
            break
        cleaned, src_idx = next_coords, next_idx
    n = len(cleaned)
    if n < 3:
        return []
    if n == 3:
        return [(src_idx[0], src_idx[1], src_idx[2])]
    area2 = sum(cleaned[i][0] * cleaned[(i + 1) % n][1] - cleaned[(i + 1) % n][0] * cleaned[i][1] for i in range(n))
    if area2 < 0:
        cleaned = list(reversed(cleaned))
        src_idx = list(reversed(src_idx))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def point_in_triangle(p, a, b, c):
        d1 = cross(p, a, b)
        d2 = cross(p, b, c)
        d3 = cross(p, c, a)
        has_neg = d1 < 0 or d2 < 0 or d3 < 0
        has_pos = d1 > 0 or d2 > 0 or d3 > 0
        return not (has_neg and has_pos)

    work = list(range(n))
    triangles = []
    while len(work) > 3:
        ear_found = False
        for idx in range(len(work)):
            ip, ic, inext = work[(idx - 1) % len(work)], work[idx], work[(idx + 1) % len(work)]
            a, b, c = cleaned[ip], cleaned[ic], cleaned[inext]
            if cross(a, b, c) <= 0:
                continue
            inside = False
            for j in range(len(work)):
                if j in ((idx - 1) % len(work), idx, (idx + 1) % len(work)):
                    continue
                if point_in_triangle(cleaned[work[j]], a, b, c):
                    inside = True
                    break
            if inside:
                continue
            triangles.append((src_idx[ip], src_idx[ic], src_idx[inext]))
            work.pop(idx)
            ear_found = True
            break
        if not ear_found:
            for idx in range(1, len(work) - 1):
                triangles.append((src_idx[work[0]], src_idx[work[idx]], src_idx[work[idx + 1]]))
            return triangles
    triangles.append((src_idx[work[0]], src_idx[work[1]], src_idx[work[2]]))
    return triangles


def _stable_gap_anchor_id(gap: ExtractedGap) -> str:
    ring = [(round(float(corner[0]), 4), round(float(corner[2]), 4)) for corner in gap.corners if len(corner) >= 3]
    if len(ring) >= 2 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) >= 3:
        variants = []
        for candidate in (ring, list(reversed(ring))):
            variants.append(min((candidate[idx:] + candidate[:idx] for idx in range(len(candidate))), key=lambda item: tuple(item)))
        ring = min(variants, key=lambda item: tuple(item))
    story_token = str(int(gap.story)) if isinstance(gap.story, (int, float)) and isfinite(gap.story) else "na"
    ring_token = "|".join(f"{x:.4f},{z:.4f}" for x, z in ring) or "empty"
    digest = sha256(f"{gap.type}|{story_token}|{ring_token}".encode()).hexdigest()[:16]
    return f"gap:{gap.type}:{story_token}:{digest}"


def _stable_gap_wall_id(gap: ExtractedGap, wall_type: str, role: str, index: int | None = None) -> str:
    parts = ["gw", _stable_gap_anchor_id(gap), wall_type, role]
    if index is not None:
        parts.append(str(int(index)))
    return ":".join(parts)


def _piece_index(piece_idx: int, n_pieces: int, element_idx: int | None = None) -> int | None:
    if n_pieces <= 1 or piece_idx == 0:
        return element_idx
    if element_idx is None:
        return piece_idx
    return piece_idx * 10000 + element_idx


def _projected_xz_area(corners: list[list[float]]) -> float:
    if len(corners) < 3:
        return 0.0
    area2 = 0.0
    for idx, corner in enumerate(corners):
        nxt = corners[(idx + 1) % len(corners)]
        area2 += float(corner[0]) * float(nxt[2]) - float(nxt[0]) * float(corner[2])
    return abs(area2) * 0.5


def _gap_wall_score(wall: ExtractedGapWall) -> float:
    if len(wall.corners) < 3:
        return 0.0
    try:
        if not all(isfinite(coord) for corner in wall.corners for coord in corner[:3]):
            return 0.0
    except TypeError:
        return 0.0
    if wall.type == "within_story" and len(wall.corners) >= 4:
        p0 = np.array([wall.corners[0][0], wall.corners[0][2]], dtype=float)
        p1 = np.array([wall.corners[1][0], wall.corners[1][2]], dtype=float)
        edge_len = float(np.linalg.norm(p1 - p0))
        ys = [float(corner[1]) for corner in wall.corners]
        return edge_len * max(0.0, max(ys) - min(ys))
    return _projected_xz_area(wall.corners)


def _limit_gap_walls_to_contract(
    walls: list[ExtractedGapWall],
    gaps: list[ExtractedGap],
) -> list[ExtractedGapWall]:
    gap_counts = Counter(gap.type for gap in gaps)
    contract = _GAP_WALL_TYPE_CONTRACTS.get((gap_counts.get("within_story", 0), gap_counts.get("cross_story", 0)))
    if contract is None:
        return walls

    selected: set[int] = set()
    for wall_type, target_count in contract.items():
        typed = [(idx, wall) for idx, wall in enumerate(walls) if wall.type == wall_type]
        if len(typed) <= target_count:
            selected.update(idx for idx, _wall in typed)
            continue
        ranked = sorted(typed, key=lambda item: (-_gap_wall_score(item[1]), item[1].id))
        selected.update(idx for idx, _wall in ranked[:target_count])

    return [
        wall
        for idx, wall in enumerate(walls)
        if idx in selected or wall.type not in contract
    ]


def _dedupe_exact_gap_walls(walls: list[ExtractedGapWall]) -> list[ExtractedGapWall]:
    out: list[ExtractedGapWall] = []
    seen: set[tuple[str, str, int, tuple[tuple[float, float, float], ...]]] = set()
    for wall in walls:
        key = (
            wall.id,
            wall.type,
            int(wall.story),
            tuple(
                (round(float(corner[0]), 6), round(float(corner[1]), 6), round(float(corner[2]), 6))
                for corner in wall.corners
            ),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(wall)
    return out


def compute_gap_walls(
    gaps: list[ExtractedGap],
    rooms: list[ExtractedRoom],
    story_y_map: dict[int, float],
    pre_absorption_floor_polygons: list[list[list[float]]] | None = None,
) -> tuple[list[ExtractedGapWall], list[ExtractedGap]]:
    walls: list[ExtractedGapWall] = []
    story_walls: dict[int, list[dict]] = defaultdict(list)

    def add_wall_edge(story: int, corners: list[list[float]]) -> None:
        if len(corners) < 4:
            return
        ys = [corner[1] for corner in corners]
        height = max(ys) - min(ys)
        if height < MIN_WALL_HEIGHT_M:
            return
        p0_xz = np.array([corners[0][0], corners[0][2]], dtype=float)
        p1_xz = np.array([corners[1][0], corners[1][2]], dtype=float)
        edge = p1_xz - p0_xz
        edge_len = float(np.linalg.norm(edge))
        if edge_len < 1e-6:
            return
        mid_y = (max(ys) + min(ys)) / 2.0
        bottom_corners = [corner for corner in corners if corner[1] < mid_y + 0.01]
        top_corners = [corner for corner in corners if corner[1] > mid_y - 0.01]
        if len(top_corners) < 2:
            top_corners = [corners[3], corners[2]]
        ybot_avg = float(np.mean([corner[1] for corner in bottom_corners])) if bottom_corners else min(ys)
        top_profile = []
        for corner in top_corners:
            cxz = np.array([corner[0], corner[2]], dtype=float)
            t = float(np.clip(np.dot(cxz - p0_xz, edge) / (edge_len**2), 0, 1))
            top_profile.append((t, corner[1]))
        top_profile.sort(key=lambda item: item[0])
        story_walls[story].append(
            {
                "corners": corners,
                "p0_xz": p0_xz,
                "edge": edge,
                "edge_unit": edge / edge_len,
                "elen": edge_len,
                "match_y": (corners[0][1] + corners[1][1]) / 2.0,
                "ybot_avg": ybot_avg,
                "top_profile": top_profile,
            }
        )

    for room in rooms:
        for wall in room.walls_computed:
            corners = wall.corners
            if wall.extension_strip:
                ext_top_y = max(corner[1] for quad in wall.extension_strip for corner in quad)
                corners = [list(corner) for corner in wall.corners]
                ys = [corner[1] for corner in corners]
                mid_y = (max(ys) + min(ys)) / 2.0
                for idx, corner in enumerate(corners):
                    if corner[1] > mid_y - 0.01:
                        corners[idx] = [corner[0], ext_top_y, corner[2]]
            add_wall_edge(room.story, corners)

    sorted_stories = sorted(story_y_map)
    ceiling_y_map = {}
    for idx, story in enumerate(sorted_stories):
        if idx + 1 < len(sorted_stories):
            ceiling_y_map[story] = story_y_map[sorted_stories[idx + 1]]
        else:
            heights = [max(c[1] for c in wall["corners"]) - min(c[1] for c in wall["corners"]) for wall in story_walls.get(story, [])]
            ceiling_y_map[story] = story_y_map[story] + (float(np.median(heights)) if heights else DEFAULT_WALL_HEIGHT_M)

    def interp_top_profile(top_profile, t):
        if len(top_profile) == 1:
            return top_profile[0][1]
        if t <= top_profile[0][0]:
            return top_profile[0][1]
        if t >= top_profile[-1][0]:
            return top_profile[-1][1]
        for idx in range(len(top_profile) - 1):
            t0, y0 = top_profile[idx]
            t1, y1 = top_profile[idx + 1]
            if t0 <= t <= t1:
                fraction = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                return y0 + fraction * (y1 - y0)
        return top_profile[-1][1]

    def project_to_wall_line(xz_pt, wall):
        rel = xz_pt - wall["p0_xz"]
        t_raw = float(np.dot(rel, wall["edge_unit"]))
        proj = wall["p0_xz"] + t_raw * wall["edge_unit"]
        dist = float(np.linalg.norm(xz_pt - proj))
        t_profile = float(np.clip(t_raw / wall["elen"], 0.0, 1.0))
        return proj, dist, t_profile

    def snap_vertex_y(xz_pt, story, floor_y):
        fallback_top = ceiling_y_map.get(story, floor_y + DEFAULT_WALL_HEIGHT_M)
        best_dist = MAX_SNAP_DIST_M
        best_ybot = floor_y
        best_ytop = fallback_top
        for wall in story_walls.get(story, []):
            if abs(wall["match_y"] - floor_y) > MAX_Y_DIST_M:
                continue
            _proj, dist, t = project_to_wall_line(xz_pt, wall)
            if dist < best_dist:
                best_dist = dist
                best_ybot = floor_y
                best_ytop = interp_top_profile(wall["top_profile"], t)
        if best_ytop <= best_ybot + MIN_WALL_HEIGHT_M:
            best_ytop = fallback_top
        return best_ybot, best_ytop

    def pick_support_wall(xz_pt, prev_xz, next_xz, story, floor_y):
        tangent = None
        edge_ref = next_xz - prev_xz
        edge_len = float(np.linalg.norm(edge_ref))
        if edge_len > MIN_SNAP_DIST_M:
            tangent = edge_ref / edge_len
        best = None
        for wall in story_walls.get(story, []):
            if abs(wall["match_y"] - floor_y) > MAX_Y_DIST_M:
                continue
            proj, dist, t_profile = project_to_wall_line(xz_pt, wall)
            if dist > MAX_SNAP_DIST_M:
                continue
            cos_parallel = abs(float(np.dot(tangent, wall["edge_unit"]))) if tangent is not None else 1.0
            score = dist + 0.35 * (1.0 - cos_parallel)
            if best is None or score < best["score"]:
                best = {"score": score, "wall": wall, "proj": proj, "t_profile": t_profile}
        return best

    def build_snapped_vertices(edge_vertices, story, floor_y):
        snapped = []
        for idx, corner in enumerate(edge_vertices):
            prev_corner = edge_vertices[(idx - 1) % len(edge_vertices)]
            next_corner = edge_vertices[(idx + 1) % len(edge_vertices)]
            xz = np.array([corner[0], corner[2]], dtype=float)
            prev_xz = np.array([prev_corner[0], prev_corner[2]], dtype=float)
            next_xz = np.array([next_corner[0], next_corner[2]], dtype=float)
            picked = pick_support_wall(xz, prev_xz, next_xz, story, floor_y)
            if picked is None:
                ybot, ytop = snap_vertex_y(xz, story, floor_y)
                snapped.append({"xz": xz, "ybot": ybot, "ytop": ytop})
            else:
                ybot = floor_y
                ytop = interp_top_profile(picked["wall"]["top_profile"], picked["t_profile"])
                if ytop <= ybot + MIN_WALL_HEIGHT_M:
                    ytop = ceiling_y_map.get(story, floor_y + DEFAULT_WALL_HEIGHT_M)
                snapped.append({"xz": picked["proj"], "ybot": ybot, "ytop": ytop})
        try:
            poly = Polygon([(item["xz"][0], item["xz"][1]) for item in snapped])
            if (not poly.is_valid) or poly.area <= 1e-6:
                raise ValueError("invalid snapped polygon")
        except Exception:
            snapped = []
            for corner in edge_vertices:
                xz = np.array([corner[0], corner[2]], dtype=float)
                ybot, ytop = snap_vertex_y(xz, story, floor_y)
                snapped.append({"xz": xz, "ybot": ybot, "ytop": ytop})
        return snapped

    story_room_union = {}
    story_room_boundary = {}
    rooms_by_story: dict[int, list[Polygon]] = defaultdict(list)
    for idx, room in enumerate(rooms):
        floor_source = pre_absorption_floor_polygons[idx] if pre_absorption_floor_polygons is not None and idx < len(pre_absorption_floor_polygons) else room.floor_polygon
        poly = floor_polygon_to_shapely(floor_source)
        if poly is not None and poly.is_valid and poly.area > 0.0:
            rooms_by_story[room.story].append(poly)
    for story, polys in rooms_by_story.items():
        try:
            union = make_valid(unary_union(polys))
        except Exception:
            union = None
        story_room_union[story] = union
        story_room_boundary[story] = union.boundary if union is not None and not union.is_empty else None

    updated_gaps = []
    for gap in gaps:
        if gap.type == "cross_story":
            corners_3d = gap.corners
            below = gap.story - 1
            if below not in story_y_map or len(corners_3d) < 3:
                updated_gaps.append(gap)
                continue
            closed = len(corners_3d) >= 4 and corners_3d[0] == corners_3d[-1]
            edge_vertices = corners_3d[:-1] if closed else corners_3d
            snapped_below = build_snapped_vertices(edge_vertices, below, story_y_map[below])
            draped = [[float(item["xz"][0]), float(item["ytop"]), float(item["xz"][1])] for item in snapped_below]
            new_corners = [list(point) for point in draped]
            if closed:
                new_corners.append(list(draped[0]))
            centroid = list(gap.centroid)
            centroid[1] = float(np.mean([point[1] for point in draped]))
            updated_gaps.append(replace(gap, corners=new_corners, ceiling_corners=[list(point) for point in draped], centroid=centroid))
            continue
        if gap.type != "within_story" or len(gap.corners) < 3:
            updated_gaps.append(gap)
            continue

        floor_y = gap.corners[0][1]
        edge_vertices = gap.corners[:-1] if len(gap.corners) >= 4 and gap.corners[0] == gap.corners[-1] else gap.corners
        if len(edge_vertices) < 3:
            updated_gaps.append(gap)
            continue
        snapped = build_snapped_vertices(edge_vertices, gap.story, floor_y)
        gap_floor_y = max(item["ybot"] for item in snapped)
        fallback_top_y = ceiling_y_map.get(gap.story, gap_floor_y + DEFAULT_WALL_HEIGHT_M)
        for item in snapped:
            if item["ytop"] <= gap_floor_y + MIN_WALL_HEIGHT_M:
                item["ytop"] = fallback_top_y
        centroid = list(gap.centroid)
        centroid[1] = gap_floor_y
        gap = replace(
            gap,
            corners=[[corner[0], gap_floor_y, corner[2]] for corner in gap.corners],
            centroid=centroid,
        )
        updated_gaps.append(gap)

        try:
            snapped_poly = Polygon([(float(item["xz"][0]), float(item["xz"][1])) for item in snapped])
            if not snapped_poly.is_valid:
                snapped_poly = make_valid(snapped_poly)
        except Exception:
            snapped_poly = None
        room_union = story_room_union.get(gap.story)
        room_boundary = story_room_boundary.get(gap.story)
        pieces_for_caps = [snapped]
        caps_were_clipped = False
        if room_union is not None and not room_union.is_empty and snapped_poly is not None and not snapped_poly.is_empty:
            try:
                clipped = make_valid(snapped_poly.difference(room_union))
            except Exception:
                clipped = None
            if clipped is None or clipped.is_empty:
                pieces_for_caps = []
                caps_were_clipped = True
            elif abs(snapped_poly.area - clipped.area) > 1e-6:
                pieces_for_caps = []
                for piece in sorted((poly for poly in decompose_polys(clipped) if poly.area > 0.01), key=lambda poly: -poly.area):
                    coords = list(piece.exterior.coords)
                    if coords and coords[0] == coords[-1]:
                        coords = coords[:-1]
                    piece_snapped = []
                    for x, z in coords:
                        piece_snapped.append({"xz": np.array([x, z], dtype=float), "ybot": gap_floor_y, "ytop": _ytop_at_xz((x, z), snapped)})
                    if len(piece_snapped) >= 3:
                        pieces_for_caps.append(piece_snapped)
                caps_were_clipped = True

        for edge_idx in range(len(snapped)):
            next_idx = (edge_idx + 1) % len(snapped)
            c0 = snapped[edge_idx]["xz"]
            c1 = snapped[next_idx]["xz"]
            if _edge_on_room_boundary(c0, c1, room_boundary):
                continue
            walls.append(
                ExtractedGapWall(
                    id=_stable_gap_wall_id(gap, gap.type, "edge", edge_idx),
                    corners=[
                        [float(c0[0]), gap_floor_y, float(c0[1])],
                        [float(c1[0]), gap_floor_y, float(c1[1])],
                        [float(c1[0]), float(snapped[next_idx]["ytop"]), float(c1[1])],
                        [float(c0[0]), float(snapped[edge_idx]["ytop"]), float(c0[1])],
                    ],
                    type=gap.type,
                    story=gap.story,
                    confidence=gap.confidence,
                )
            )

        for piece_idx, piece_snapped in enumerate(pieces_for_caps):
            n_pieces = len(pieces_for_caps)
            walls.append(
                ExtractedGapWall(
                    id=_stable_gap_wall_id(gap, "gap_floor", "polygon", _piece_index(piece_idx, n_pieces, None)),
                    corners=[[float(item["xz"][0]), gap_floor_y, float(item["xz"][1])] for item in piece_snapped],
                    type="gap_floor",
                    story=gap.story,
                    confidence=gap.confidence,
                )
            )
            xz_2d = [(float(item["xz"][0]), float(item["xz"][1])) for item in piece_snapped]
            tri_idx = 0
            for ia, ib, ic in earclip_2d(xz_2d):
                sa, sb, sc = piece_snapped[ia], piece_snapped[ib], piece_snapped[ic]
                x0, z0 = sa["xz"]
                x1, z1 = sb["xz"]
                x2, z2 = sc["xz"]
                if abs((x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0)) * 0.5 < 1e-5:
                    continue
                walls.append(
                    ExtractedGapWall(
                        id=_stable_gap_wall_id(gap, "gap_ceiling", "tri", _piece_index(piece_idx, n_pieces, tri_idx)),
                        corners=[
                            [float(sa["xz"][0]), float(sa["ytop"]), float(sa["xz"][1])],
                            [float(sb["xz"][0]), float(sb["ytop"]), float(sb["xz"][1])],
                            [float(sc["xz"][0]), float(sc["ytop"]), float(sc["xz"][1])],
                        ],
                        type="gap_ceiling",
                        story=gap.story,
                        confidence=gap.confidence,
                    )
                )
                tri_idx += 1

    return _dedupe_exact_gap_walls(_limit_gap_walls_to_contract(walls, updated_gaps)), updated_gaps
