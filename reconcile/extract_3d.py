"""Extract 3D geometry for the viewer from merged.json + scan-cache rooms."""

import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid


def parse_transform(flat):
    return np.array(flat).reshape(4, 4, order="F")


def corners_to_world(polygon_corners, transform_flat):
    T = parse_transform(transform_flat)
    return [(T @ np.array([*c, 1.0]))[:3].tolist() for c in polygon_corners]


def wall_world_corners(wall):
    """Get wall corners in world coordinates.
    Uses polygonCorners if available, otherwise builds a rectangle from dimensions + transform.
    """
    T = parse_transform(wall["transform"])
    if wall.get("polygonCorners") and len(wall["polygonCorners"]) >= 3:
        return [(T @ np.array([*c, 1.0]))[:3].tolist() for c in wall["polygonCorners"]]
    # Rectangle from dimensions
    w = wall["dimensions"][0] / 2
    h = wall["dimensions"][1] / 2
    local = [[-w, -h, 0], [w, -h, 0], [w, h, 0], [-w, h, 0]]
    return [(T @ np.array([*c, 1.0]))[:3].tolist() for c in local]


def hybrid_wall_corners(merged_wall, raw_wall, floor_y=None):
    """Hybrid: merged wall's transform + shape (polygonCorners if available, else raw dims).
    If floor_y is given, align wall bottom to floor."""
    T = parse_transform(merged_wall["transform"])
    # Use polygonCorners if available (preserves slanted/roof shapes)
    # Prefer merged (already in building space orientation), fallback to raw
    merged_pc = merged_wall.get("polygonCorners", [])
    raw_pc = raw_wall.get("polygonCorners", [])
    if len(merged_pc) >= 3:
        local = merged_pc
    elif len(raw_pc) >= 3:
        local = raw_pc
    else:
        w = raw_wall["dimensions"][0] / 2
        h = raw_wall["dimensions"][1] / 2
        local = [[-w, -h, 0], [w, -h, 0], [w, h, 0], [-w, h, 0]]
    corners = [(T @ np.array([*c, 1.0]))[:3].tolist() for c in local]
    if floor_y is not None:
        current_bottom = min(c[1] for c in corners)
        dy = floor_y - current_bottom
        corners = [[c[0], c[1] + dy, c[2]] for c in corners]
    return corners


def compute_svd(src, dst):
    """Compute rigid transform (R, t) from src to dst. Returns R, t, max_residual_cm."""
    src_c, dst_c = src.mean(0), dst.mean(0)
    H = (src - src_c).T @ (dst - dst_c)
    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = Vt.T @ U.T
    t = dst_c - R @ src_c
    res = np.max(np.linalg.norm(dst - (R @ src.T).T - t, axis=1)) * 100
    return R, t, res


def find_scan_cache_dir(uuid, scan_cache_root):
    """Find scan-cache directory for a building UUID."""
    for entry in os.listdir(scan_cache_root):
        if uuid in entry and os.path.isdir(scan_cache_root / entry):
            return scan_cache_root / entry
    return None


def parse_address_from_scan_dir(scan_dir):
    """Extract street address from scan-cache directory name."""
    import re
    name = scan_dir.name if hasattr(scan_dir, "name") else os.path.basename(str(scan_dir))
    m = re.search(
        r"scans_[^_]+_(.+?)_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_",
        name,
    )
    if not m:
        return None
    raw = m.group(1)
    # Double underscore = separator (comma), single underscore = space
    addr = raw.replace("__", ", ").replace("_", " ")
    return addr


def load_raw_rooms(scan_dir):
    """Load individual room JSONs from scan-cache directory."""
    rooms = []
    for f in sorted(os.listdir(scan_dir)):
        if not f.endswith(".json"):
            continue
        if f in ("data.json", "arworldmap.json"):
            continue
        if f.startswith("ceiling_") or f.startswith("merged_"):
            continue
        with open(scan_dir / f) as fh:
            rooms.append((f, json.load(fh)))
    return rooms


def compute_room_transforms(raw_rooms, merged_data):
    """Compute SVD transforms from raw rooms to building space.

    Strategy (hybrid):
    1. SVD on floor polygon corners when corner counts match (0.00cm residual)
    2. SVD on shared wall center positions as fallback for multi-room scans
    """
    transforms = {}  # raw_filename -> (R, t, residual, method)

    # Build merged wall UUID -> wall data for wall-center fallback
    merged_wall_map = {}
    for mr in merged_data.get("rooms", []):
        for w in mr.get("walls", []):
            merged_wall_map[w["identifier"]] = w

    for rname, rdata in raw_rooms:
        raw_uuids = {w["identifier"] for w in rdata.get("walls", [])}
        if not raw_uuids:
            continue

        # Find best matching merged room by UUID overlap
        best_idx, best_overlap = -1, 0
        for i, mr in enumerate(merged_data["rooms"]):
            mr_uuids = {w["identifier"] for w in mr.get("walls", [])}
            overlap = len(raw_uuids & mr_uuids)
            if overlap > best_overlap:
                best_idx, best_overlap = i, overlap

        if best_idx < 0:
            continue

        mr = merged_data["rooms"][best_idx]

        # Strategy 1: SVD on floor polygon corners (preferred, 0.00cm residual)
        if (rdata.get("floors") and rdata["floors"][0].get("polygonCorners")
                and mr.get("floors") and mr["floors"][0].get("polygonCorners")):
            raw_fc = np.array(corners_to_world(
                rdata["floors"][0]["polygonCorners"],
                rdata["floors"][0]["transform"],
            ))
            m_fc = np.array(corners_to_world(
                mr["floors"][0]["polygonCorners"],
                mr["floors"][0]["transform"],
            ))
            if len(raw_fc) == len(m_fc):
                R, t, res = compute_svd(raw_fc, m_fc)
                if res < 50.0:
                    transforms[rname] = (R, t, res, "floor-svd")
                    continue

        # Strategy 2: SVD on shared wall center positions (fallback for multi-room scans)
        src_pts, dst_pts = [], []
        for rw in rdata.get("walls", []):
            if rw["identifier"] in merged_wall_map:
                mw = merged_wall_map[rw["identifier"]]
                src_pts.append(parse_transform(rw["transform"])[:3, 3])
                dst_pts.append(parse_transform(mw["transform"])[:3, 3])

        if len(src_pts) >= 3:
            src_arr = np.array(src_pts)
            dst_arr = np.array(dst_pts)
            R, t, res = compute_svd(src_arr, dst_arr)
            if res < 200.0:  # higher threshold — wall centers shift during merge
                transforms[rname] = (R, t, res, "wall-center-svd")

    return transforms


def _floor_polygon_to_shapely(floor_polygon_3d):
    """Convert 3D floor polygon [[x,y,z],...] to 2D Shapely Polygon on XZ plane."""
    if not floor_polygon_3d or len(floor_polygon_3d) < 3:
        return None
    coords = [(c[0], c[2]) for c in floor_polygon_3d]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    try:
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = make_valid(poly)
        if poly.area < 0.01:
            return None
        return poly
    except Exception:
        return None


def _decompose_polys(geom):
    """Extract all Polygon objects from a geometry."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def _compute_cross_floor_gaps(rooms_out):
    """Detect cross-floor gaps using convex-hull concavity approach.

    For each story:
    1. Compute convex hull minus footprint → concavity regions
    2. Check which concavities are filled by other floors
    3. Concavities filled by other floors are likely scanning gaps
    """
    story_rooms = defaultdict(list)
    story_floor_ys = defaultdict(list)

    for ri, room in enumerate(rooms_out):
        story = room["story"]
        poly = _floor_polygon_to_shapely(room["floor_polygon"])
        if poly is not None:
            story_rooms[story].append((ri, poly))
            ys = [c[1] for c in room["floor_polygon"]]
            story_floor_ys[story].append(np.mean(ys))

    if len(story_rooms) < 2:
        return []

    # Build per-story footprints
    story_footprints = {}
    story_y_map = {}
    for story, room_polys in sorted(story_rooms.items()):
        polys = [p for _, p in room_polys]
        union = unary_union(polys)
        footprint = union.buffer(0.02).buffer(-0.02)
        footprint = make_valid(footprint)
        polys_out = _decompose_polys(footprint)
        fp = max(polys_out, key=lambda g: g.area) if polys_out else None
        if fp and fp.area > 0.01:
            story_footprints[story] = fp
            story_y_map[story] = float(np.mean(story_floor_ys[story]))

    if len(story_footprints) < 2:
        return []

    gaps = []

    for story, footprint in story_footprints.items():
        # Find concavities: convex hull minus footprint
        hull = footprint.convex_hull
        diff = make_valid(hull.difference(footprint))
        concavities = [r for r in _decompose_polys(diff) if r.area >= 0.1]

        for region in concavities:
            # Check which other floor best fills this concavity
            best_story, best_fill = -1, 0.0
            for s, fp in story_footprints.items():
                if s == story:
                    continue
                try:
                    inter = region.intersection(fp)
                    fill = inter.area / region.area if region.area > 0 else 0
                except Exception:
                    fill = 0
                if fill > best_fill:
                    best_story, best_fill = s, fill

            # Only report if another floor fills >30%
            if best_fill < 0.3:
                continue

            area = region.area
            compactness = 4 * math.pi * area / (region.length ** 2) if region.length > 0 else 0

            # Scoring
            fill_score = min(best_fill / 0.8, 1.0)
            area_score = max(0.1, 1.0 - area / 6.0) if area < 8 else 0.1
            compact_score = 1.0 - min(compactness / 0.4, 1.0)

            other = [s for s in story_footprints if s != story]
            if other:
                filling = sum(
                    1 for s in other
                    if story_footprints[s].intersection(region).area > area * 0.5
                )
                agreement = filling / len(other)
            else:
                agreement = fill_score

            score = 0.35 * fill_score + 0.20 * area_score + 0.15 * compact_score + 0.30 * agreement

            if score >= 0.6:
                confidence = "high"
            elif score >= 0.35:
                confidence = "medium"
            else:
                confidence = "low"

            centroid = region.centroid
            floor_y = story_y_map.get(story, 0)
            coords_2d = list(region.exterior.coords)
            corners_3d = [[c[0], floor_y, c[1]] for c in coords_2d]

            try:
                shared_fp = region.boundary.intersection(footprint.exterior)
                contact = shared_fp.length / region.boundary.length if not shared_fp.is_empty else 0
            except Exception:
                contact = 0

            gaps.append({
                "story": story,
                "reference_story": best_story,
                "corners": corners_3d,
                "area_m2": round(area, 3),
                "compactness": round(compactness, 3),
                "perimeter_contact_pct": round(contact, 3),
                "confidence": confidence,
                "confidence_score": round(score, 2),
                "centroid": [round(centroid.x, 3), floor_y, round(centroid.y, 3)],
            })

    return gaps


def extract_building(uuid, pipeline_dir, scan_cache_root):
    """Extract 3D data for one building."""
    # Find merged.json
    merged_path = None
    for entry in os.listdir(pipeline_dir):
        if entry.startswith(uuid) and os.path.isdir(pipeline_dir / entry):
            mp = pipeline_dir / entry / "merged.json"
            if mp.exists():
                merged_path = mp
                break

    if not merged_path:
        return None

    with open(merged_path) as f:
        merged = json.load(f)

    # Load reconciled.json for classification if available
    recon_path = merged_path.parent / "reconciled.json"
    classification = "UNKNOWN"
    stories_changed = 0
    if recon_path.exists():
        with open(recon_path) as f:
            recon = json.load(f)
        meta = recon.get("reconciliation", {})
        classification = meta.get("classification", "UNKNOWN")

    # Story fix: cluster floor Y positions
    floor_ys = []
    for mr in merged["rooms"]:
        if mr.get("floors") and mr["floors"][0].get("polygonCorners"):
            fc = corners_to_world(
                mr["floors"][0]["polygonCorners"],
                mr["floors"][0]["transform"],
            )
            mean_y = np.mean([c[1] for c in fc])
            floor_ys.append(mean_y)
        else:
            floor_ys.append(0.0)

    # Cluster stories by Y gap > 1.0m
    sorted_ys = sorted(set(floor_ys))
    story_map = {}
    current_story = 0
    for i, y in enumerate(sorted_ys):
        if i > 0 and abs(y - sorted_ys[i - 1]) > 1.0:
            current_story += 1
        story_map[y] = current_story

    stories_found = current_story + 1

    # Assign stories to rooms
    room_stories = []
    for fy in floor_ys:
        closest_y = min(sorted_ys, key=lambda sy: abs(sy - fy))
        room_stories.append(story_map[closest_y])

    # Try loading raw scan-cache rooms
    scan_dir = find_scan_cache_dir(uuid, scan_cache_root) if scan_cache_root else None
    raw_rooms = load_raw_rooms(scan_dir) if scan_dir else []
    raw_transforms = compute_room_transforms(raw_rooms, merged) if raw_rooms else {}

    # Build wall UUID -> raw room + transform mapping
    raw_wall_data = {}  # wall_uuid -> (wall_data, R, t, method)
    for rname, rdata in raw_rooms:
        if rname not in raw_transforms:
            continue
        R, t, _res, method = raw_transforms[rname]
        for w in rdata.get("walls", []):
            raw_wall_data[w["identifier"]] = (w, R, t, method)

    # Track globally which deduped walls have been added (avoid duplicates across rooms)
    global_dedup_added = set()

    # Extract rooms
    rooms_out = []
    for ri, mr in enumerate(merged["rooms"]):
        story = room_stories[ri] if ri < len(room_stories) else 0

        # Floor polygon (from merged room, already in building space)
        floor_polygon = []
        if mr.get("floors") and mr["floors"][0].get("polygonCorners"):
            floor_polygon = corners_to_world(
                mr["floors"][0]["polygonCorners"],
                mr["floors"][0]["transform"],
            )

        # Merged walls (top-level deduplicated) — find walls belonging to this room
        # Actually, room-level walls are already per-room. Use top-level for merged view.
        walls_merged = []
        for w in mr.get("walls", []):
            corners = wall_world_corners(w)
            walls_merged.append({"corners": corners, "id": w["identifier"]})

        # Build merged wall UUID map for hybrid lookups
        merged_wall_by_id = {}
        for omr in merged["rooms"]:
            for mw in omr.get("walls", []):
                merged_wall_by_id[mw["identifier"]] = mw

        # Raw walls: use scan-cache geometry where possible
        walls_raw = []
        for w in mr.get("walls", []):
            wid = w["identifier"]
            if wid in raw_wall_data:
                raw_w, R, t_vec, method = raw_wall_data[wid]
                if method == "floor-svd":
                    # High-quality transform — use full SVD on raw wall
                    raw_corners = wall_world_corners(raw_w)
                    transformed = [(R @ np.array(c) + t_vec).tolist() for c in raw_corners]
                    walls_raw.append({"corners": transformed, "id": wid, "source": "scan-cache"})
                else:
                    # Wall-center SVD (noisy) — hybrid: merged position + raw dimensions
                    fy = np.mean([c[1] for c in floor_polygon]) if floor_polygon else None
                    corners = hybrid_wall_corners(w, raw_w, floor_y=fy)
                    walls_raw.append({"corners": corners, "id": wid, "source": "hybrid"})
            else:
                # No raw data — use merged room wall as-is
                corners = wall_world_corners(w)
                walls_raw.append({"corners": corners, "id": wid, "source": "merged-room"})

        # Also add walls that are in raw rooms but NOT in any merged room (dropped by dedup)
        # These are the "other side" of shared walls — add each deduped wall only once
        added_uuids = {w["id"] for w in walls_raw}
        for rname, rdata in raw_rooms:
            if rname not in raw_transforms:
                continue
            R, t_vec, _res, method = raw_transforms[rname]
            # Only add deduped walls from high-quality (floor-svd) transforms
            if method != "floor-svd":
                continue
            # Check if this raw room maps to this merged room
            raw_uuids = {w["identifier"] for w in rdata.get("walls", [])}
            mr_uuids = {w["identifier"] for w in mr.get("walls", [])}
            if not (raw_uuids & mr_uuids):
                continue
            for w in rdata.get("walls", []):
                wid = w["identifier"]
                if wid in added_uuids or wid in global_dedup_added:
                    continue
                # Check if this wall is NOT in any merged room (it was deduped)
                in_any_merged = any(
                    any(mw["identifier"] == wid for mw in omr.get("walls", []))
                    for omr in merged["rooms"]
                )
                if in_any_merged:
                    continue  # This wall belongs to another merged room

                raw_corners = wall_world_corners(w)
                transformed = [(R @ np.array(c) + t_vec).tolist() for c in raw_corners]
                walls_raw.append({"corners": transformed, "id": wid, "source": "scan-cache-dedup"})
                added_uuids.add(wid)
                global_dedup_added.add(wid)

        rooms_out.append({
            "story": story,
            "floor_polygon": floor_polygon,
            "walls_merged": walls_merged,
            "walls_raw": walls_raw,
        })

    # Cross-floor gap detection from floor polygons
    cross_floor_gaps_out = _compute_cross_floor_gaps(rooms_out)

    raw_total = sum(len(r["walls_raw"]) for r in rooms_out)
    merged_total = sum(len(r["walls_merged"]) for r in rooms_out)
    scan_cache_count = sum(
        1 for r in rooms_out for w in r["walls_raw"] if w.get("source") == "scan-cache"
    )

    address = parse_address_from_scan_dir(scan_dir) if scan_dir else None

    return {
        "uuid": uuid,
        "address": address,
        "classification": classification,
        "rooms": rooms_out,
        "stories_found": stories_found,
        "stories_changed": stories_changed,
        "raw_walls_total": raw_total,
        "merged_walls_total": merged_total,
        "scan_cache_walls": scan_cache_count,
        "raw_rooms_found": len(raw_rooms),
        "raw_rooms_transformed": len(raw_transforms),
        "cross_floor_gaps": cross_floor_gaps_out,
    }


def main():
    pipeline_dir = Path("pipeline-outputs")
    scan_cache_root = Path(".scan-cache")

    # Select buildings to extract
    uuids = sys.argv[1:] if len(sys.argv) > 1 else [
        "938d6ed6",  # 3-story, 22 rooms
        "3c74f488",  # 3-story
        "612d1bc8",
        "73c1d779",
        "b8782b87",
        "9bb4ada4",
    ]

    results = []
    for uuid in uuids:
        print(f"Extracting {uuid}...")
        result = extract_building(uuid, pipeline_dir, scan_cache_root)
        if result:
            results.append(result)
            raw_total = result["raw_walls_total"]
            merged_total = result["merged_walls_total"]
            scan_cache = result["scan_cache_walls"]
            print(f"  {len(result['rooms'])} rooms, {result['stories_found']} stories, "
                  f"{raw_total} raw walls ({scan_cache} from scan-cache), "
                  f"{merged_total} merged walls, "
                  f"{result['raw_rooms_found']} raw rooms ({result['raw_rooms_transformed']} transformed)")
        else:
            print(f"  SKIPPED (no merged.json)")

    out_path = Path("reconcile/buildings_3d.json")
    with open(out_path, "w") as f:
        json.dump(results, f)
    print(f"\nWrote {len(results)} buildings to {out_path}")


if __name__ == "__main__":
    main()
