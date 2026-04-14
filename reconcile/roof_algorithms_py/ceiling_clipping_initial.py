from __future__ import annotations

from .math_utils import angle_diff, clip_poly_by_ridge


def _per_plane_footprint(
    plane: dict,
    all_rooms: list[dict],
    buffer: float = 3.0,
) -> list[tuple[float, float]] | None:
    """Compute a tight footprint from the rooms that contributed segments.

    Returns a 2-D polygon (list of (x, z) tuples) covering the source rooms
    buffered by *buffer* metres.  Unlike expanding to include entire adjacent
    rooms (which can pull in long bridging rooms), this approach grows the
    source room geometry uniformly, naturally covering nearby areas without
    inheriting distant room extents.

    Returns ``None`` if Shapely is unavailable or the result is degenerate.
    """
    room_indices: set[int] = set(plane.get("room_indices", []))
    if not room_indices or not all_rooms:
        return None

    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
    except ImportError:
        return None

    polys = []
    for ri in room_indices:
        if ri >= len(all_rooms):
            continue
        fp = all_rooms[ri].get("floor_polygon", [])
        if not fp or len(fp) < 3:
            continue
        ring = [(p[0], p[2]) for p in fp]
        try:
            p = Polygon(ring).buffer(buffer, join_style="mitre")
            if p.is_valid and not p.is_empty:
                polys.append(p)
        except Exception:
            continue

    if not polys:
        return None

    merged = unary_union(polys)
    if merged.is_empty:
        return None
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda g: g.area)

    # Roofs span the full convex extent of contributing rooms — don't
    # let L-shaped or concave room footprints hollow out the ceiling.
    merged = merged.convex_hull

    coords = list(merged.exterior.coords)
    if coords and coords[-1] == coords[0]:
        coords = coords[:-1]
    return [(x, z) for x, z in coords] if len(coords) >= 3 else None


def _intersect_footprints(
    fp_a: list[tuple[float, float]], fp_b: list[tuple[float, float]]
) -> list[tuple[float, float]] | None:
    """Return the intersection of two 2-D footprint polygons via Shapely."""
    try:
        from shapely.geometry import Polygon
    except ImportError:
        return None

    try:
        pa = Polygon(fp_a)
        pb = Polygon(fp_b)
        inter = pa.intersection(pb)
        if inter.is_empty or inter.geom_type not in ("Polygon", "MultiPolygon"):
            return None
        if inter.geom_type == "MultiPolygon":
            inter = max(inter.geoms, key=lambda g: g.area)
        coords = list(inter.exterior.coords)
        if coords and coords[-1] == coords[0]:
            coords = coords[:-1]
        return [(x, z) for x, z in coords] if len(coords) >= 3 else None
    except Exception:
        return None


def build_initial_plane_clips(
    *,
    ceiling_planes: list,
    building_footprint: list,
    exposed_rooms: list,
    all_rooms: list[dict] | None = None,
) -> list:
    plane_clipped = []

    # Slope-direction margin for flat-ceiling cross-checks.
    _SLOPE_MARGIN = 1.5

    flat_ceil_polys = [
        [(p[0], p[2]) for p in er["fp"]]
        for er in exposed_rooms
        if (er["wallTopY"] - er["wallTopMin"]) < 0.3
    ]

    for pi, plane in enumerate(ceiling_planes):
        ridge_min = plane["minRidge"]
        ridge_max = plane["maxRidge"]

        expanded = True
        while expanded:
            expanded = False
            for flat_poly in flat_ceil_polys:
                projs = [
                    (pt[0] - plane["ref"]["x"]) * plane["ridgeX"]
                    + (pt[1] - plane["ref"]["z"]) * plane["ridgeZ"]
                    for pt in flat_poly
                ]
                min_p, max_p = min(projs), max(projs)
                if max_p >= ridge_min - 1.0 and min_p <= ridge_max + 1.0:
                    # Check slope-direction overlap to prevent chaining
                    # across building sections that are offset perpendicular
                    # to the ridge (e.g. L-shaped extensions).
                    slope_projs = [
                        (pt[0] - plane["ref"]["x"]) * plane["slopeX"]
                        + (pt[1] - plane["ref"]["z"]) * plane["slopeZ"]
                        for pt in flat_poly
                    ]
                    s_min, s_max = min(slope_projs), max(slope_projs)
                    if (
                        s_max < plane["minSlope"] - _SLOPE_MARGIN
                        or s_min > plane["maxSlope"] + _SLOPE_MARGIN
                    ):
                        continue

                    if min_p < ridge_min:
                        ridge_min = min_p
                        expanded = True
                    if max_p > ridge_max:
                        ridge_max = max_p
                        expanded = True

        # Room-based expansion fallback: when no flat ceilings are available,
        # extend ridge bounds to cover exposed rooms whose centroids fall
        # within the plane's slope-direction extent.
        if not flat_ceil_polys:
            room_expanded = True
            while room_expanded:
                room_expanded = False
                for er in exposed_rooms:
                    slope_proj = (
                        (er["fcx"] - plane["ref"]["x"]) * plane["slopeX"]
                        + (er["fcz"] - plane["ref"]["z"]) * plane["slopeZ"]
                    )
                    if (
                        slope_proj < plane["minSlope"] - _SLOPE_MARGIN
                        or slope_proj > plane["maxSlope"] + _SLOPE_MARGIN
                    ):
                        continue
                    ridge_proj = (
                        (er["fcx"] - plane["ref"]["x"]) * plane["ridgeX"]
                        + (er["fcz"] - plane["ref"]["z"]) * plane["ridgeZ"]
                    )
                    if ridge_min - 2.0 <= ridge_proj <= ridge_max + 2.0:
                        if ridge_proj - 1.0 < ridge_min:
                            ridge_min = ridge_proj - 1.0
                            room_expanded = True
                        if ridge_proj + 1.0 > ridge_max:
                            ridge_max = ridge_proj + 1.0
                            room_expanded = True

        # Per-plane footprint: narrow the clipping polygon to the rooms
        # that contributed segments (plus nearby rooms).  Prevents ceiling
        # planes from extending into distant building sections via the
        # building-wide footprint.
        effective_fp = building_footprint
        if all_rooms:
            plane_fp = _per_plane_footprint(plane, all_rooms)
            if plane_fp:
                narrowed = _intersect_footprints(building_footprint, plane_fp)
                if narrowed and len(narrowed) >= 3:
                    effective_fp = narrowed

        clipped = list(effective_fp)
        clipped = clip_poly_by_ridge(
            clipped,
            plane["ridgeX"],
            plane["ridgeZ"],
            plane["ref"]["x"],
            plane["ref"]["z"],
            ridge_min,
            True,
        )
        clipped = clip_poly_by_ridge(
            clipped,
            plane["ridgeX"],
            plane["ridgeZ"],
            plane["ref"]["x"],
            plane["ref"]["z"],
            ridge_max,
            False,
        )

        # For isolated planes (no opposing plane), also clip along slope direction
        # to prevent the ceiling from extending beyond the room's XZ bounds.
        has_opposing = False
        for pj, other in enumerate(ceiling_planes):
            if pj == pi:
                continue
            if plane["dominantStory"] != other["dominantStory"]:
                continue
            azi_diff = angle_diff(plane["cl"]["avgAzimuth"], other["cl"]["avgAzimuth"])
            if 140.0 <= azi_diff <= 220.0:
                has_opposing = True
                break

        if not has_opposing:
            # Compute contributing rooms' ridge/slope bounds so margins
            # never push the ceiling beyond the actual room footprint.
            room_ridge_min = float("-inf")
            room_ridge_max = float("inf")
            room_slope_min = float("-inf")
            room_slope_max = float("inf")
            room_indices = plane.get("room_indices", [])
            if all_rooms and room_indices:
                r_mins, r_maxs, s_mins, s_maxs = [], [], [], []
                for ri in room_indices:
                    if ri >= len(all_rooms):
                        continue
                    fp = all_rooms[ri].get("floor_polygon", [])
                    if not fp:
                        continue
                    for p in fp:
                        r_proj = (
                            (p[0] - plane["ref"]["x"]) * plane["ridgeX"]
                            + (p[2] - plane["ref"]["z"]) * plane["ridgeZ"]
                        )
                        s_proj = (
                            (p[0] - plane["ref"]["x"]) * plane["slopeX"]
                            + (p[2] - plane["ref"]["z"]) * plane["slopeZ"]
                        )
                        r_mins.append(r_proj)
                        r_maxs.append(r_proj)
                        s_mins.append(s_proj)
                        s_maxs.append(s_proj)
                if r_mins:
                    room_ridge_min = min(r_mins)
                    room_ridge_max = max(r_maxs)
                    room_slope_min = min(s_mins)
                    room_slope_max = max(s_maxs)

            slope_min = max(plane["minSlope"] - 0.5, room_slope_min)
            slope_max = min(plane["maxSlope"] + 0.5, room_slope_max)
            clipped = clip_poly_by_ridge(
                clipped,
                plane["slopeX"],
                plane["slopeZ"],
                plane["ref"]["x"],
                plane["ref"]["z"],
                slope_min,
                True,
            )
            clipped = clip_poly_by_ridge(
                clipped,
                plane["slopeX"],
                plane["slopeZ"],
                plane["ref"]["x"],
                plane["ref"]["z"],
                slope_max,
                False,
            )
            seg_ridge_min = max(plane["minRidge"] - 0.5, room_ridge_min)
            seg_ridge_max = min(plane["maxRidge"] + 0.5, room_ridge_max)
            if seg_ridge_min > ridge_min:
                clipped = clip_poly_by_ridge(
                    clipped,
                    plane["ridgeX"],
                    plane["ridgeZ"],
                    plane["ref"]["x"],
                    plane["ref"]["z"],
                    seg_ridge_min,
                    True,
                )
            if seg_ridge_max < ridge_max:
                clipped = clip_poly_by_ridge(
                    clipped,
                    plane["ridgeX"],
                    plane["ridgeZ"],
                    plane["ref"]["x"],
                    plane["ref"]["z"],
                    seg_ridge_max,
                    False,
                )

        plane_clipped.append(
            {"clipped": clipped, "ridgeMin": ridge_min, "ridgeMax": ridge_max}
        )

    return plane_clipped
