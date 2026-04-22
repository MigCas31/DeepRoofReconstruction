"""Phase A — candidate face generation for the reconstruction BIP.

Given one building's merged roof-segment hypotheses plus the scan-derived
footprint, produce a set of **candidate clipped faces** that the
downstream binary integer program (``solver.py``) selects among.

Each candidate face carries:

* the parent plane equation (a, b, c, d),
* a 2-D XZ polygon — the footprint the face occupies if selected,
* azimuth / inclination / area for objective terms,
* a neighbour list (candidate face IDs that share a ridge) for the
  topology constraint,
* a support weight (scan evidence — currently parent-segment area),
* an ``extended`` flag (``True`` when the candidate was extended beyond
  the raw merged segment up to the ridge against an opposing plane).

This v1 emits **one candidate per merged segment**, extended when the
upstream V3 pipeline identified opposing planes, otherwise returned
unextended. That keeps Phase A linear in the number of merged segments
— critical for buildings with 2000+ segments. Phase B can relax this
later (e.g. emit both an "extended" and an "unextended" variant and let
the BIP pick).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, degrees, sqrt

from shapely.geometry import Polygon as ShapelyPolygon

Plane = tuple[float, float, float, float]  # ax + by + cz + d = 0, (a,b,c) unit
Point2D = tuple[float, float]

_RIDGE_HALFPLANE_NORMAL_MIN = 1e-6
_MIN_FACE_AREA_M2 = 0.1


@dataclass
class CandidateFace:
    id: str
    building_uuid: str
    parent_segment_id: str
    plane: Plane
    footprint_xz: list[Point2D]
    area_m2: float
    azimuth_deg: float
    inclination_deg: float
    neighbors: list[str] = field(default_factory=list)
    support_m2: float = 0.0
    extended: bool = False
    gbm_prior: float | None = None


def _plane_azimuth_inclination(plane: Plane) -> tuple[float, float]:
    """Downslope azimuth (0=+Z, clockwise) and inclination (degrees)."""
    a, b, c, _ = plane
    norm = sqrt(a * a + b * b + c * c)
    if norm < 1e-9:
        return 0.0, 0.0
    a, b, c = a / norm, b / norm, c / norm
    if b < 0:
        a, b, c = -a, -b, -c
    horiz = sqrt(a * a + c * c)
    incl = degrees(atan2(horiz, b))
    azimuth = degrees(atan2(-a, -c)) % 360.0
    return azimuth, incl


def _to_xz_ring(footprint_xz: list) -> list[Point2D]:
    """Accept either [x, y, z] triples or [x, z] pairs; return [x, z] pairs."""
    out: list[Point2D] = []
    for pt in footprint_xz:
        if len(pt) >= 3:
            out.append((float(pt[0]), float(pt[2])))
        elif len(pt) == 2:
            out.append((float(pt[0]), float(pt[1])))
    return out


def _poly_from_ring(ring: list[Point2D]) -> ShapelyPolygon | None:
    if len(ring) < 3:
        return None
    try:
        poly = ShapelyPolygon(ring)
    except Exception:
        return None
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or not poly.is_valid:
        return None
    return poly


def _exterior_ring(poly: ShapelyPolygon) -> list[Point2D]:
    coords = list(poly.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    return [(float(x), float(z)) for (x, z) in coords]


def _ridge_halfplane_coeffs(
    plane_self: Plane, plane_other: Plane
) -> tuple[float, float, float] | None:
    """Coefficients (A, C, D) of the seam line ``A·x + C·z + D = 0``
    between ``plane_self`` and ``plane_other``.

    Derivation: ``y_i = -(a_i·x + c_i·z + d_i) / b_i`` (roof-up convention
    ``b_i > 0``). The seam is where ``y_self = y_other``; the half-plane
    ``A·x + C·z + D >= 0`` corresponds to ``y_self <= y_other`` with

        (a_s·b_o − a_o·b_s)·x + (c_s·b_o − c_o·b_s)·z + (d_s·b_o − d_o·b_s).

    The caller picks which *side* of this seam the candidate belongs on
    (see ``_extend_against_opposing`` — we orient via the segment's own
    centroid so extension always grows into the segment's own half).

    Returns ``None`` if either plane is near-vertical (``|b| < eps``) or
    the coefficients degenerate to zero (parallel planes).
    """
    a_s, b_s, c_s, d_s = plane_self
    a_o, b_o, c_o, d_o = plane_other
    if abs(b_s) < 1e-6 or abs(b_o) < 1e-6:
        return None
    # Orient so both planes face up (b > 0) before forming the half-plane.
    if b_s < 0:
        a_s, b_s, c_s, d_s = -a_s, -b_s, -c_s, -d_s
    if b_o < 0:
        a_o, b_o, c_o, d_o = -a_o, -b_o, -c_o, -d_o
    A = a_s * b_o - a_o * b_s
    C = c_s * b_o - c_o * b_s
    D = d_s * b_o - d_o * b_s
    if sqrt(A * A + C * C) < _RIDGE_HALFPLANE_NORMAL_MIN:
        return None
    return A, C, D


def _clip_by_halfplane(
    poly: ShapelyPolygon, coeffs: tuple[float, float, float]
) -> ShapelyPolygon | None:
    """Intersect ``poly`` with the half-plane ``A·x + C·z + D >= 0``.

    Builds a large rectangle on the half-plane's positive side and takes
    the intersection — robust for any convex/concave input.
    """
    A, C, D = coeffs
    minx, minz, maxx, maxz = poly.bounds
    pad = max(maxx - minx, maxz - minz, 10.0) * 10.0 + 10.0
    cx = (minx + maxx) / 2.0
    cz = (minz + maxz) / 2.0
    # Unit vector pointing into the positive side of the half-plane.
    norm = sqrt(A * A + C * C)
    ux, uz = A / norm, C / norm
    # Offset the rectangle centre along +u by ``pad`` so the whole
    # rectangle lies on the positive side of A·x + C·z + D = 0.
    # The boundary line passes through the point closest to the origin:
    # (-A·D / (A²+C²), -C·D / (A²+C²)).
    t0 = -D / (norm * norm)  # signed distance from origin to the line
    # Anchor the rectangle half-plane side starting at the boundary line
    # through poly's centroid projected onto the line, extended ``pad``
    # units into +u.
    base_x = cx - (A * cx + C * cz + D) * A / (norm * norm)
    base_z = cz - (A * cx + C * cz + D) * C / (norm * norm)
    _ = t0  # silence lint
    # Perpendicular direction (tangent to the boundary).
    tx, tz = -uz, ux
    # Build a rectangle: from (base − pad·t) to (base + pad·t) on the
    # boundary line, extruded ``2·pad`` into +u.
    corners = [
        (base_x - pad * tx, base_z - pad * tz),
        (base_x + pad * tx, base_z + pad * tz),
        (base_x + pad * tx + 2 * pad * ux, base_z + pad * tz + 2 * pad * uz),
        (base_x - pad * tx + 2 * pad * ux, base_z - pad * tz + 2 * pad * uz),
    ]
    try:
        rect = ShapelyPolygon(corners)
        clipped = poly.intersection(rect)
    except Exception:
        return None
    if clipped.is_empty or not clipped.is_valid:
        return None
    if clipped.geom_type == "MultiPolygon":
        clipped = max(clipped.geoms, key=lambda g: g.area)
    if clipped.geom_type != "Polygon" or clipped.area <= 0:
        return None
    return clipped


def _extend_against_opposing(
    plane_self: Plane,
    seg_poly: ShapelyPolygon,
    scan_footprint_poly: ShapelyPolygon | None,
    opposing_planes: list[Plane],
) -> tuple[ShapelyPolygon | None, bool]:
    """Return ``(clipped_poly, extended)``.

    If the segment has no opposing planes we cannot responsibly extend it
    — there is no ridge geometry to bound the extension — so we keep the
    segment's own footprint (clipped to the scan footprint if provided)
    and return ``extended=False``. With opposing planes, start from the
    scan footprint (or segment footprint as fallback), and for each
    opposing plane clip to the half of the seam that the segment's own
    centroid already lives on — so extension always grows the segment
    *within* its own side of the ridge rather than flipping it across.

    This sidedness-by-centroid avoids depending on upstream conventions:
    ``merged_slanted_roof_proposals.py`` emits segments on BOTH sides of
    each opposing seam ("rain" and "covered"), and we have no direct way
    to know which from ``opposing_planes`` alone. The centroid lookup
    answers it from the data itself.
    """
    if not opposing_planes:
        if scan_footprint_poly is None or scan_footprint_poly.is_empty:
            return seg_poly, False
        try:
            clipped = seg_poly.intersection(scan_footprint_poly)
        except Exception:
            return seg_poly, False
        if clipped.is_empty or not clipped.is_valid:
            return None, False
        if clipped.geom_type == "MultiPolygon":
            clipped = max(clipped.geoms, key=lambda g: g.area)
        if clipped.geom_type != "Polygon" or clipped.area < _MIN_FACE_AREA_M2:
            return None, False
        return clipped, False

    if scan_footprint_poly is not None and not scan_footprint_poly.is_empty:
        work = scan_footprint_poly
    else:
        work = seg_poly

    # Use the segment's own centroid (not the scan footprint's) to decide
    # sidedness: scan_footprint spans the whole building, but each segment
    # lives on a specific side of each ridge.
    seg_centroid = seg_poly.centroid
    cx, cz = float(seg_centroid.x), float(seg_centroid.y)

    for plane_other in opposing_planes:
        coeffs = _ridge_halfplane_coeffs(plane_self, plane_other)
        if coeffs is None:
            continue
        A, C, D = coeffs
        # Pick the half-plane that the segment already sits on. Value > 0
        # means ``y_self < y_other`` at the centroid (segment is on the
        # "covered" side); value < 0 means the opposite (rain side).
        if A * cx + C * cz + D < 0.0:
            coeffs = (-A, -C, -D)
        clipped = _clip_by_halfplane(work, coeffs)
        if clipped is None:
            # Half-plane clipped to empty — face would vanish.
            return None, False
        work = clipped

    if work.area < _MIN_FACE_AREA_M2:
        return None, False

    # Did we actually extend beyond the original segment footprint?
    extended = work.area > seg_poly.area * 1.01
    return work, extended


def _segment_plane(segment: dict) -> Plane | None:
    plane = segment.get("merged_plane")
    if not plane or len(plane) < 4:
        return None
    a, b, c, d = (float(plane[0]), float(plane[1]), float(plane[2]), float(plane[3]))
    if abs(a) + abs(b) + abs(c) < 1e-9:
        return None
    return a, b, c, d


def build_candidate_faces(
    building_uuid: str,
    merged_segments: list[dict],
    building_footprint_xz: list[Point2D] | None = None,
) -> list[CandidateFace]:
    """Produce one candidate face per merged segment, ridge-extended where
    opposing planes are available.

    Args:
        building_uuid: used as the prefix for candidate IDs.
        merged_segments: list of dicts with keys ``id``, ``merged_plane``,
            ``footprint_xz``, ``opposing_planes`` (optional, list of
            plane tuples), ``features`` (optional).
        building_footprint_xz: XZ-plane ring of the scan-derived
            footprint. If provided, candidates are clipped to it.

    Returns:
        List of ``CandidateFace``.
    """
    scan_poly: ShapelyPolygon | None = None
    if building_footprint_xz:
        scan_poly = _poly_from_ring(list(building_footprint_xz))

    # Pre-compute each segment's shapely poly + plane + opposing planes.
    prepared: list[dict] = []
    for seg in merged_segments:
        plane = _segment_plane(seg)
        if plane is None:
            continue
        ring = _to_xz_ring(seg.get("footprint_xz") or [])
        seg_poly = _poly_from_ring(ring)
        if seg_poly is None or seg_poly.area < _MIN_FACE_AREA_M2:
            continue
        opp_raw = seg.get("opposing_planes") or []
        opposing: list[Plane] = []
        for p in opp_raw:
            if p and len(p) >= 4:
                opposing.append((float(p[0]), float(p[1]), float(p[2]), float(p[3])))
        prepared.append({
            "segment": seg,
            "plane": plane,
            "seg_poly": seg_poly,
            "opposing": opposing,
        })

    # Build a quick id lookup for neighbour resolution via opposing_cluster_canonicals.
    id_by_opposing_id: dict[str, str] = {}
    for entry in prepared:
        seg = entry["segment"]
        cand_id = f"{building_uuid}::candidate::{seg['id'].split('::')[-1]}"
        id_by_opposing_id[seg["id"]] = cand_id

    candidates: list[CandidateFace] = []
    for entry in prepared:
        seg = entry["segment"]
        plane = entry["plane"]
        seg_poly = entry["seg_poly"]
        opposing = entry["opposing"]

        clipped_poly, extended = _extend_against_opposing(
            plane, seg_poly, scan_poly, opposing
        )
        if clipped_poly is None:
            # Fall back to the raw segment poly clipped to the scan footprint.
            if scan_poly is not None:
                try:
                    fb = seg_poly.intersection(scan_poly)
                except Exception:
                    fb = None
                if fb is not None and not fb.is_empty and fb.area >= _MIN_FACE_AREA_M2:
                    if fb.geom_type == "MultiPolygon":
                        fb = max(fb.geoms, key=lambda g: g.area)
                    if fb.geom_type == "Polygon":
                        clipped_poly = fb
                        extended = False
            if clipped_poly is None:
                clipped_poly = seg_poly
                extended = False

        ring = _exterior_ring(clipped_poly)
        if len(ring) < 3:
            continue

        azimuth, inclination = _plane_azimuth_inclination(plane)
        feat = seg.get("features") or {}
        support = float(feat.get("area_m2") or seg_poly.area)

        cand_id = f"{building_uuid}::candidate::{seg['id'].split('::')[-1]}"
        neighbours_ids: list[str] = []
        for opp_canonical in seg.get("opposing_cluster_canonicals") or []:
            # Canonicals are cluster-level; candidates live at segment-level.
            # Resolve via suffix match on prepared segment ids.
            for other in prepared:
                if other["segment"].get("cluster_canonical_id") == opp_canonical:
                    other_id = f"{building_uuid}::candidate::{other['segment']['id'].split('::')[-1]}"
                    if other_id != cand_id and other_id not in neighbours_ids:
                        neighbours_ids.append(other_id)

        candidates.append(CandidateFace(
            id=cand_id,
            building_uuid=building_uuid,
            parent_segment_id=seg["id"],
            plane=plane,
            footprint_xz=ring,
            area_m2=float(clipped_poly.area),
            azimuth_deg=azimuth,
            inclination_deg=inclination,
            neighbors=neighbours_ids,
            support_m2=support,
            extended=extended,
        ))

    return candidates
