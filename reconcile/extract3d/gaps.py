"""Cross-floor gap detection and gap wall synthesis."""

import math
from collections import defaultdict

import numpy as np
from shapely import STRtree
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid

from reconcile_v2.decision_logic import classify_gap_decision

from .lineage import STEP_GAP_WALLS, record
from .overlaps import decompose_polys, floor_polygon_to_shapely


def recommend_gap_actions(graph):
    """Return graph-driven closure recommendations keyed by gap node id.

    This does not replace legacy geometry generation yet. It provides a stable
    decision layer that callers can use in hybrid mode while the exact 3D
    backend matures.
    """
    recommendations = {}
    for gap in graph.nodes_by_type("Gap"):
        decision = classify_gap_decision(graph, gap)
        recommendations[gap.id] = {**decision, "story": gap.story}
    return recommendations


def _normalize_gap_kind(kind):
    if kind == "within_story":
        return "intra_story"
    return kind


def _map_gaps_to_ontology_ids(gaps, graph):
    by_story = defaultdict(list)
    for node in graph.nodes_by_type("Gap"):
        region_wkt = (node.properties or {}).get("region_wkt")
        if not isinstance(region_wkt, str) or not region_wkt:
            continue
        try:
            poly = shapely_wkt.loads(region_wkt)
            if not poly.is_valid:
                poly = make_valid(poly)
        except Exception:
            continue
        if poly.is_empty or poly.area <= 0.0:
            continue
        by_story[node.story].append((node, poly))

    for gap in gaps:
        corners = gap.get("corners") or []
        if len(corners) < 3:
            continue
        try:
            gap_poly = Polygon([(float(c[0]), float(c[2])) for c in corners])
            if not gap_poly.is_valid:
                gap_poly = make_valid(gap_poly)
        except Exception:
            continue
        if gap_poly.is_empty:
            continue
        target_kind = _normalize_gap_kind(gap.get("type"))
        best_node = None
        best_area = 0.0
        for node, node_poly in by_story.get(gap.get("story"), []):
            node_kind = (node.properties or {}).get("gap_kind")
            if node_kind != target_kind:
                continue
            try:
                overlap = float(gap_poly.intersection(node_poly).area)
            except Exception:
                continue
            if overlap > best_area:
                best_area = overlap
                best_node = node
        if best_node is not None and best_area > 1e-5:
            gap["_ontology_gap_id"] = best_node.id


def compute_cross_floor_gaps(rooms_out):
    """Detect gaps between floor polygons: within-story and cross-story."""
    wall_half = 0.25
    pair_half = 0.50
    max_gap = 1.00
    min_area = 0.005
    max_half_floor = 1.50

    story_rooms_raw = defaultdict(list)
    for room in rooms_out:
        story = room["story"]
        poly = floor_polygon_to_shapely(room["floor_polygon"])
        if poly is not None and poly.is_valid and poly.area > 0.01:
            ys = [c[1] for c in room["floor_polygon"]]
            story_rooms_raw[story].append((poly, float(np.mean(ys))))

    story_rooms = defaultdict(list)
    story_floor_ys = defaultdict(list)
    for story, entries in story_rooms_raw.items():
        floor_ys_all = [fy for _, fy in entries]
        median_y = float(np.median(floor_ys_all))
        for poly, fy in entries:
            if abs(fy - median_y) <= max_half_floor:
                story_rooms[story].append(poly)
                story_floor_ys[story].append(fy)

    story_footprints = {}
    story_y_map = {}
    for story, polys in sorted(story_rooms.items()):
        fp = make_valid(unary_union(polys))
        if fp.area > 0.01:
            story_footprints[story] = fp
            story_y_map[story] = float(np.mean(story_floor_ys[story]))

    gaps = []

    def emit_gaps(regions, story, floor_y, gap_type, clip_to=None):
        for region in regions:
            if clip_to is not None:
                try:
                    region = make_valid(region.intersection(clip_to))
                except Exception:
                    continue
            for part in decompose_polys(region):
                if part.area < min_area:
                    continue
                area = part.area
                compactness = (
                    4 * math.pi * area / (part.length**2) if part.length > 0 else 0
                )
                if compactness < 0.15:
                    confidence = "high"
                elif compactness < 0.3:
                    confidence = "medium"
                else:
                    confidence = "low"
                coords_2d = list(part.exterior.coords)
                corners_3d = [[c[0], floor_y, c[1]] for c in coords_2d]
                centroid = part.centroid
                gaps.append(
                    {
                        "story": story,
                        "type": gap_type,
                        "corners": corners_3d,
                        "area_m2": round(area, 3),
                        "compactness": round(compactness, 3),
                        "confidence": confidence,
                        "centroid": [
                            round(centroid.x, 3),
                            floor_y,
                            round(centroid.y, 3),
                        ],
                    }
                )

    for story, polys in sorted(story_rooms.items()):
        if len(polys) < 2:
            continue

        footprint = story_footprints[story]
        floor_y = story_y_map[story]
        all_gap_parts = []

        closed = make_valid(
            footprint.buffer(wall_half, join_style=2).buffer(-wall_half, join_style=2)
        )
        morph_gaps = make_valid(closed.difference(footprint))
        all_gap_parts.extend(decompose_polys(morph_gaps))

        for poly_part in decompose_polys(closed):
            for interior in poly_part.interiors:
                hole = Polygon(interior)
                if hole.is_valid and hole.area > min_area:
                    all_gap_parts.append(hole)

        tree = STRtree(polys)
        buffered = [p.buffer(pair_half, join_style=2) for p in polys]
        pair_gap_parts = []
        seen_pairs = set()

        for i, _poly_i in enumerate(polys):
            candidates = tree.query(buffered[i])
            for j in candidates:
                if j <= i:
                    continue
                pair_key = (i, j)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                if polys[i].distance(polys[j]) > max_gap:
                    continue

                try:
                    intersection = buffered[i].intersection(buffered[j])
                    gap = make_valid(intersection.difference(footprint))
                    pair_gap_parts.extend(decompose_polys(gap))
                except Exception:
                    continue

        wide_closed = make_valid(
            footprint.buffer(pair_half, join_style=2).buffer(-pair_half, join_style=2)
        )

        if all_gap_parts:
            merged = make_valid(unary_union(all_gap_parts))
            emit_gaps(
                decompose_polys(merged), story, floor_y, "within_story", clip_to=closed
            )

        if pair_gap_parts:
            pair_merged = make_valid(unary_union(pair_gap_parts))
            if all_gap_parts:
                try:
                    pair_merged = make_valid(
                        pair_merged.difference(unary_union(all_gap_parts))
                    )
                except Exception:
                    pass
            emit_gaps(
                decompose_polys(pair_merged),
                story,
                floor_y,
                "within_story",
                clip_to=wide_closed,
            )

    sorted_stories = sorted(story_footprints.keys())
    if len(sorted_stories) >= 2:
        all_footprints = [story_footprints[s] for s in sorted_stories]
        full_envelope = make_valid(unary_union(all_footprints))

        for story in sorted_stories:
            fp = story_footprints[story]
            floor_y = story_y_map[story]
            try:
                missing = make_valid(full_envelope.difference(fp))
            except Exception:
                continue
            emit_gaps(decompose_polys(missing), story, floor_y, "cross_story")

    return gaps


def assign_gaps_to_rooms(gaps, rooms_out, graph=None):
    """Assign closeable within-story gaps to nearest room and expand floor polygons.

    When a topology graph is provided, only gaps with graph decision `close`
    are merged into room floors. This prevents intentional openings from being
    indiscriminately sealed while ensuring enclosed inferred voids are filled.
    """
    room_shapely = []
    for ri, room in enumerate(rooms_out):
        poly = floor_polygon_to_shapely(room.get("floor_polygon", []))
        room_shapely.append((ri, poly))

    if graph is not None:
        _map_gaps_to_ontology_ids(gaps, graph)
        gap_decisions = {
            node.id: classify_gap_decision(graph, node)
            for node in graph.nodes_by_type("Gap")
        }
    else:
        gap_decisions = {}

    for gap in gaps:
        if gap.get("type") != "within_story":
            continue
        ontology_gap_id = gap.get("_ontology_gap_id")
        if ontology_gap_id and graph is not None:
            decision = gap_decisions.get(ontology_gap_id, {})
            if decision.get("action") != "close":
                continue

        corners_3d = gap.get("corners") or []
        if len(corners_3d) < 3:
            continue

        gap_poly = floor_polygon_to_shapely(corners_3d)
        if gap_poly is None:
            continue

        story = gap.get("story")
        gap_centroid = gap_poly.centroid

        best_ri = None
        best_dist = float("inf")
        for ri, rpoly in room_shapely:
            if rpoly is None or rooms_out[ri].get("story") != story:
                continue
            d = rpoly.distance(gap_centroid)
            if d < best_dist:
                best_dist = d
                best_ri = ri

        if best_ri is None:
            continue

        gap["room_index"] = best_ri

        assigned_room = rooms_out[best_ri]
        wall_top_ys = []
        for w in (assigned_room.get("walls_computed") or assigned_room.get("walls_merged", [])):
            cs = w.get("corners", [])
            if cs:
                wall_top_ys.append(max(c[1] for c in cs))
        if wall_top_ys:
            ceiling_y = round(float(np.median(wall_top_ys)), 4)
        else:
            ceiling_y = corners_3d[0][1]
        gap["ceiling_corners"] = [
            [round(c[0], 4), ceiling_y, round(c[2], 4)] for c in corners_3d
        ]

        room = assigned_room
        room_poly = room_shapely[best_ri][1]
        if room_poly is None:
            continue

        floor_y = room["floor_polygon"][0][1] if room.get("floor_polygon") else corners_3d[0][1]
        merged = make_valid(unary_union([room_poly, gap_poly]))
        if getattr(merged, "geom_type", "") == "MultiPolygon":
            merged = max(merged.geoms, key=lambda g: g.area)
        if merged.is_empty:
            continue

        coords_2d = list(merged.exterior.coords)
        if coords_2d and coords_2d[0] == coords_2d[-1]:
            coords_2d = coords_2d[:-1]
        room["floor_polygon"] = [[round(c[0], 4), floor_y, round(c[1], 4)] for c in coords_2d]
        room_shapely[best_ri] = (best_ri, merged)


def compute_gap_walls(gaps, rooms_out, story_y_map, gap_closures=None, graph=None):
    """Create wall quads along each edge of cross-floor gap polygons."""
    default_wall_height = 2.50
    min_wall_height = 0.5
    max_snap_dist = 1.0
    max_y_dist = 0.75
    gap_policies = {}
    if graph is not None:
        _map_gaps_to_ontology_ids(gaps, graph)
        recommendations = recommend_gap_actions(graph)
        for gap in graph.nodes_by_type("Gap"):
            decision = recommendations.get(gap.id)
            if decision is None:
                continue
            gap_policies.setdefault(
                (gap.story, _normalize_gap_kind((gap.properties or {}).get("gap_kind"))),
                [],
            ).append((gap.id, decision))

    def add_wall_edge(story, wc):
        if len(wc) < 4:
            return
        ys = [c[1] for c in wc]
        h = max(ys) - min(ys)
        if h < min_wall_height:
            return
        p0_xz = np.array([wc[0][0], wc[0][2]])
        p1_xz = np.array([wc[1][0], wc[1][2]])
        edge = p1_xz - p0_xz
        elen = np.linalg.norm(edge)
        if elen < 1e-6:
            return
        ybot_avg = (wc[0][1] + wc[1][1]) / 2
        mid_y = (max(ys) + min(ys)) / 2.0
        top_cs = [c for c in wc if c[1] > mid_y - 0.01]
        if len(top_cs) < 2:
            top_cs = [wc[3], wc[2]]
        top_profile = []
        for c in top_cs:
            cxz = np.array([c[0], c[2]])
            t = float(np.clip(np.dot(cxz - p0_xz, edge) / (elen**2), 0, 1))
            top_profile.append((t, c[1]))
        top_profile.sort(key=lambda p: p[0])
        story_walls[story].append((wc, p0_xz, edge, elen, ybot_avg, top_profile))

    story_walls = defaultdict(list)
    for room in rooms_out:
        story = room["story"]
        for wall in room["walls_computed"]:
            wc = wall["corners"]
            if len(wc) < 4:
                continue
            ext = wall.get("extension_strip")
            if ext and len(ext) >= 1:
                ext_top_y = max(c[1] for quad in ext for c in quad)
                ec = [list(c) for c in wc]
                ys = [c[1] for c in wc]
                mid_y = (max(ys) + min(ys)) / 2.0
                for i, c in enumerate(ec):
                    if c[1] > mid_y - 0.01:
                        ec[i] = [c[0], ext_top_y, c[2]]
            else:
                ec = wc
            add_wall_edge(story, ec)

    for gc in gap_closures or []:
        if gc.get("type") == "side" and len(gc.get("corners", [])) >= 4:
            add_wall_edge(gc["story"], gc["corners"])

    sorted_stories = sorted(story_y_map.keys())
    ceiling_y_map = {}
    for i, story in enumerate(sorted_stories):
        if i + 1 < len(sorted_stories):
            ceiling_y_map[story] = story_y_map[sorted_stories[i + 1]]
        else:
            heights = []
            for wc, _p0, _edge, _elen, _ybot_avg, _top_profile in story_walls.get(
                story, []
            ):
                ys = [c[1] for c in wc]
                heights.append(max(ys) - min(ys))
            median_h = float(np.median(heights)) if heights else default_wall_height
            ceiling_y_map[story] = story_y_map[story] + median_h

    def interp_top_profile(top_profile, t):
        if len(top_profile) == 1:
            return top_profile[0][1]
        if t <= top_profile[0][0]:
            return top_profile[0][1]
        if t >= top_profile[-1][0]:
            return top_profile[-1][1]
        for k in range(len(top_profile) - 1):
            t0, y0 = top_profile[k]
            t1, y1 = top_profile[k + 1]
            if t0 <= t <= t1:
                frac = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                return y0 + frac * (y1 - y0)
        return top_profile[-1][1]

    def snap_vertex_y(xz_pt, story, floor_y):
        """Snap to the closest wall — used for wall quad heights."""
        fallback_top = ceiling_y_map.get(story, floor_y + default_wall_height)
        best_dist = max_snap_dist
        best_ybot = floor_y
        best_ytop = fallback_top

        for _wc, p0_xz, edge, elen, ybot_avg, top_profile in story_walls.get(story, []):
            if abs(ybot_avg - floor_y) > max_y_dist:
                continue
            t = float(np.clip(np.dot(xz_pt - p0_xz, edge) / (elen**2), 0, 1))
            proj = p0_xz + t * edge
            dist = float(np.linalg.norm(xz_pt - proj))
            if dist < best_dist:
                best_dist = dist
                best_ybot = float(ybot_avg)
                best_ytop = interp_top_profile(top_profile, t)

        return best_ybot, best_ytop

    def snap_ceiling_y(xz_pt, story, floor_y):
        """Snap to the lowest wall top among all nearby walls — used for ceiling quads.

        This prevents the ceiling from sticking out above oblique/sloped walls.
        """
        fallback_top = ceiling_y_map.get(story, floor_y + default_wall_height)
        found_any = False
        min_ytop = fallback_top

        for _wc, p0_xz, edge, elen, ybot_avg, top_profile in story_walls.get(story, []):
            if abs(ybot_avg - floor_y) > max_y_dist:
                continue
            t = float(np.clip(np.dot(xz_pt - p0_xz, edge) / (elen**2), 0, 1))
            proj = p0_xz + t * edge
            dist = float(np.linalg.norm(xz_pt - proj))
            if dist < max_snap_dist:
                ytop = interp_top_profile(top_profile, t)
                if not found_any or ytop < min_ytop:
                    min_ytop = ytop
                    found_any = True

        return min_ytop

    walls = []
    for gap in gaps:
        if gap["type"] != "within_story":
            continue
        if graph is not None:
            gap_kind = _normalize_gap_kind(gap["type"])
            decisions = gap_policies.get((gap.get("story"), gap_kind), [])
            if decisions and not any(decision.get("action") == "close" for _, decision in decisions):
                continue
        corners_3d = gap["corners"]
        if len(corners_3d) < 3:
            continue
        story = gap["story"]
        floor_y = corners_3d[0][1]

        vertex_ys = []
        for c in corners_3d:
            xz = np.array([c[0], c[2]])
            ybot, ytop = snap_vertex_y(xz, story, floor_y)
            vertex_ys.append((ybot, ytop))

        gap_floor_y = max(yb for yb, _ in vertex_ys)
        for c in corners_3d:
            c[1] = gap_floor_y
        gap["centroid"][1] = gap_floor_y

        n = len(corners_3d)
        # Strip duplicate closing vertex for edge iteration
        if n >= 4 and corners_3d[0] == corners_3d[-1]:
            edge_verts = corners_3d[:-1]
        else:
            edge_verts = corners_3d
        n_edges = len(edge_verts)

        for ei in range(n_edges):
            j = (ei + 1) % n_edges
            c0 = edge_verts[ei]
            c1 = edge_verts[j]
            _, ytop0 = vertex_ys[ei]
            _, ytop1 = vertex_ys[j]
            entry = {
                "corners": [
                    [c0[0], gap_floor_y, c0[2]],
                    [c1[0], gap_floor_y, c1[2]],
                    [c1[0], ytop1, c1[2]],
                    [c0[0], ytop0, c0[2]],
                ],
                "type": gap["type"],
                "story": story,
                "confidence": gap["confidence"],
                "ontology_gap_id": gap.get("_ontology_gap_id"),
            }
            if gap.get("_ontology_gap_id"):
                entry["id"] = f"gw:{gap['_ontology_gap_id']}:{entry['type']}:{len(walls)}"
            record(
                entry,
                STEP_GAP_WALLS,
                "created",
                f"type={gap['type']}, confidence={gap['confidence']}",
            )
            walls.append(entry)

        # Polygon-wide floor + ceiling caps for the entire gap polygon.
        # Without these, long within-story ribbons (e.g. post-clip slivers
        # between adjacent rooms) get vertical walls only and render as
        # visible holes in the floor. Parallels reconcile_v3 close_obvious_gaps.
        cap_ceiling_ys = [
            snap_ceiling_y(np.array([v[0], v[2]]), story, gap_floor_y)
            for v in edge_verts
        ]
        cap_ceiling_y = float(np.median(cap_ceiling_ys))
        polygon_floor = {
            "corners": [[v[0], gap_floor_y, v[2]] for v in edge_verts],
            "type": "gap_floor",
            "story": story,
            "confidence": gap["confidence"],
            "ontology_gap_id": gap.get("_ontology_gap_id"),
        }
        if gap.get("_ontology_gap_id"):
            polygon_floor["id"] = (
                f"gw:{gap['_ontology_gap_id']}:gap_floor_polygon:{len(walls)}"
            )
        record(
            polygon_floor,
            STEP_GAP_WALLS,
            "created",
            f"type=gap_floor_polygon, confidence={gap['confidence']}",
        )
        walls.append(polygon_floor)

        polygon_ceiling = {
            "corners": [[v[0], cap_ceiling_y, v[2]] for v in edge_verts],
            "type": "gap_ceiling",
            "story": story,
            "confidence": gap["confidence"],
            "ontology_gap_id": gap.get("_ontology_gap_id"),
        }
        if gap.get("_ontology_gap_id"):
            polygon_ceiling["id"] = (
                f"gw:{gap['_ontology_gap_id']}:gap_ceiling_polygon:{len(walls)}"
            )
        record(
            polygon_ceiling,
            STEP_GAP_WALLS,
            "created",
            f"type=gap_ceiling_polygon, confidence={gap['confidence']}",
        )
        walls.append(polygon_ceiling)

        # Short-edge caps: the gap polygon is often a thin ribbon whose short
        # edges (~wall thickness) connect inner/outer outlines.  Emit one
        # narrow quad per short cross-edge, clamped so it doesn't extend
        # further than the wall thickness into the adjacent run edges.
        short_edge_threshold = 0.25  # metres — wall-thickness edges
        max_cap_reach = 0.30  # don't extend further than this along run edges

        for ei in range(n_edges):
            j = (ei + 1) % n_edges
            c0 = edge_verts[ei]
            c1 = edge_verts[j]
            dx = c1[0] - c0[0]
            dz = c1[2] - c0[2]
            edge_len = math.sqrt(dx * dx + dz * dz)
            if edge_len > short_edge_threshold:
                continue  # long run edge — already has a vertical wall quad

            # Find the previous and next vertices; clamp distance along the
            # run edges so the cap quad stays narrow.
            ip = (ei - 1) % n_edges
            jn = (j + 1) % n_edges
            cp = edge_verts[ip]
            cn = edge_verts[jn]

            def _clamp_towards(origin, target, max_dist):
                """Move from origin towards target, clamped to max_dist."""
                ddx = target[0] - origin[0]
                ddz = target[2] - origin[2]
                d = math.sqrt(ddx * ddx + ddz * ddz)
                if d <= max_dist or d < 1e-6:
                    return target
                ratio = max_dist / d
                return [
                    origin[0] + ddx * ratio,
                    origin[1],
                    origin[2] + ddz * ratio,
                ]

            cp_clamped = _clamp_towards(c0, cp, max_cap_reach)
            cn_clamped = _clamp_towards(c1, cn, max_cap_reach)

            # Floor quad
            floor_quad = {
                "corners": [
                    [cp_clamped[0], gap_floor_y, cp_clamped[2]],
                    [c0[0], gap_floor_y, c0[2]],
                    [c1[0], gap_floor_y, c1[2]],
                    [cn_clamped[0], gap_floor_y, cn_clamped[2]],
                ],
                "type": "gap_floor",
                "story": story,
                "confidence": gap["confidence"],
                "ontology_gap_id": gap.get("_ontology_gap_id"),
            }
            if gap.get("_ontology_gap_id"):
                floor_quad["id"] = f"gw:{gap['_ontology_gap_id']}:gap_floor:{len(walls)}"
            record(
                floor_quad,
                STEP_GAP_WALLS,
                "created",
                f"type=gap_floor, confidence={gap['confidence']}",
            )
            walls.append(floor_quad)

            # Ceiling quad — per-vertex snap to nearest wall top
            quad_verts = [cp_clamped, c0, c1, cn_clamped]
            ceil_ys = [
                snap_ceiling_y(np.array([v[0], v[2]]), story, gap_floor_y)
                for v in quad_verts
            ]
            ceiling_quad = {
                "corners": [
                    [quad_verts[k][0], ceil_ys[k], quad_verts[k][2]]
                    for k in range(4)
                ],
                "type": "gap_ceiling",
                "story": story,
                "confidence": gap["confidence"],
                "ontology_gap_id": gap.get("_ontology_gap_id"),
            }
            if gap.get("_ontology_gap_id"):
                ceiling_quad["id"] = f"gw:{gap['_ontology_gap_id']}:gap_ceiling:{len(walls)}"
            record(
                ceiling_quad,
                STEP_GAP_WALLS,
                "created",
                f"type=gap_ceiling, confidence={gap['confidence']}",
            )
            walls.append(ceiling_quad)

    return walls
