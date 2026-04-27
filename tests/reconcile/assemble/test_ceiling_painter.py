import json

from shapely.geometry import Polygon
from shapely.ops import unary_union

import reconcile.viewer_server as legacy_viewer_server
from reconcile_tiers._core.plane import FitFailure, Plane
from reconcile_tiers.assemble.ceiling_painter import CeilingCandidate, assemble_ceiling
from reconcile_tiers.payload.schema import CeilingSource


def _flat_candidate(source: CeilingSource, locator_id: str, x0=0.0, z0=0.0, x1=2.0, z1=2.0):
    corners = [[x0, 3.0, z0], [x1, 3.0, z0], [x1, 3.0, z1], [x0, 3.0, z1]]
    return CeilingCandidate(
        corners=corners,
        plane=Plane(a=0.0, b=1.0, c=0.0, d=3.0),
        source=source,
        locator_id=locator_id,
    )


def _xz_poly(piece):
    return Polygon([(corner.x, corner.z) for corner in piece.corners])


def _visible_xz_poly(piece):
    return Polygon(
        [(corner.x, corner.z) for corner in piece.corners],
        holes=[[(corner.x, corner.z) for corner in hole] for hole in piece.holes],
    )


def _load_legacy_server_caches():
    legacy_viewer_server.ROOF_RESULTS_CACHE = json.loads(
        legacy_viewer_server.ROOF_RESULTS_PATH.read_text()
    )
    legacy_viewer_server.BUILDINGS_3D_CACHE = {
        building["uuid"]: building
        for building in json.loads(legacy_viewer_server.BUILDINGS_3D_PATH.read_text())
        if building.get("uuid")
    }


def _candidate_from_corners(source: CeilingSource, locator_id: str, corners):
    plane = Plane.fit(corners)
    if isinstance(plane, FitFailure):
        return None
    return CeilingCandidate(
        corners=[[float(p[0]), float(p[1]), float(p[2])] for p in corners],
        plane=plane,
        source=source,
        locator_id=locator_id,
    )


def _dormer_cutout_candidate(uuid: str, idx: int, xz_poly, coeffs):
    a, b, c, d = coeffs
    ring = list(xz_poly.exterior.coords)
    if len(ring) >= 2 and ring[0] == ring[-1]:
        ring = ring[:-1]
    corners = [[float(x), float((d - a * x - c * z) / b), float(z)] for x, z in ring]
    return CeilingCandidate(
        corners=corners,
        plane=Plane(a=float(a), b=float(b), c=float(c), d=float(d)),
        source=CeilingSource.DORMER_CUTOUT,
        locator_id=f"{uuid}::tier-ceiling-dormer-cutout::{idx}",
    )


def test_higher_priority_dominates_lower_overlap():
    pieces = assemble_ceiling(
        [
            _flat_candidate(CeilingSource.RAW_FALLBACK, "raw"),
            _flat_candidate(CeilingSource.FLAT_EMIT, "flat"),
        ]
    )

    assert len(pieces) == 1
    assert pieces[0].source == CeilingSource.FLAT_EMIT
    assert round(_xz_poly(pieces[0]).area, 6) == 4.0


def test_dormer_cutout_punches_lower_priority_but_not_flat():
    cutout = _flat_candidate(CeilingSource.DORMER_CUTOUT, "cutout", 0.5, 0.5, 1.5, 1.5)

    arrangement = assemble_ceiling(
        [_flat_candidate(CeilingSource.ROOF_ARRANGEMENT, "arrangement")],
        holes=[cutout],
    )
    flat = assemble_ceiling(
        [_flat_candidate(CeilingSource.FLAT_EMIT, "flat")],
        holes=[cutout],
    )

    assert len(arrangement) == 1
    assert len(arrangement[0].holes) == 1
    assert round(_xz_poly(arrangement[0]).area, 6) == 4.0
    assert round(Polygon([(corner.x, corner.z) for corner in arrangement[0].holes[0]]).area, 6) == 1.0
    assert len(flat[0].holes) == 0


def test_visible_area_no_overlap_and_corners_stay_on_plane():
    pieces = assemble_ceiling(
        [
            _flat_candidate(CeilingSource.RAW_FALLBACK, "raw", 0.0, 0.0, 3.0, 3.0),
            _flat_candidate(CeilingSource.THERMAL_CAP, "thermal", 1.0, 0.0, 4.0, 3.0),
            _flat_candidate(CeilingSource.ROOF_ARRANGEMENT, "arrangement", 2.0, 0.0, 5.0, 3.0),
        ]
    )

    total_visible = sum(_visible_xz_poly(piece).area for piece in pieces)
    total_candidate = 9.0 + 9.0 + 9.0
    assert total_visible <= total_candidate
    for idx, piece in enumerate(pieces):
        poly = _visible_xz_poly(piece)
        for other in pieces[idx + 1 :]:
            assert poly.intersection(_visible_xz_poly(other)).area < 1e-9
        for corner in piece.corners:
            assert abs(piece.plane.b - 1.0) < 1e-9
            assert abs(corner.y - 3.0) < 1e-9


def test_painter_skips_invalid_tiny_and_near_vertical_candidates():
    tiny = _flat_candidate(CeilingSource.RAW_FALLBACK, "tiny", 0.0, 0.0, 0.1, 0.1)
    invalid = CeilingCandidate(
        corners=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        plane=Plane(a=0.0, b=1.0, c=0.0, d=0.0),
        source=CeilingSource.RAW_FALLBACK,
        locator_id="invalid",
    )
    near_vertical = CeilingCandidate(
        corners=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        plane=Plane(a=1.0, b=0.0, c=0.0, d=0.0),
        source=CeilingSource.RAW_FALLBACK,
        locator_id="near-vertical",
    )

    assert assemble_ceiling([tiny, invalid, near_vertical]) == []


def test_visible_area_property_for_rectangular_candidates():
    cases = [
        [
            (CeilingSource.RAW_FALLBACK, -1.0, -1.0, 2.0, 2.0),
            (CeilingSource.THERMAL_CAP, 0.5, -1.0, 2.0, 2.0),
            (CeilingSource.ROOF_ARRANGEMENT, 1.0, 0.0, 3.0, 2.5),
        ],
        [
            (CeilingSource.FLAT_EMIT, 0.0, 0.0, 4.0, 1.0),
            (CeilingSource.RAW_FALLBACK, 1.0, -1.0, 1.0, 4.0),
            (CeilingSource.THERMAL_CAP, -1.0, 0.25, 6.0, 0.5),
        ],
        [
            (CeilingSource.ROOF_ARRANGEMENT, -3.0, 1.0, 2.25, 1.5),
            (CeilingSource.ROOF_ARRANGEMENT, -0.5, 1.0, 2.25, 1.5),
            (CeilingSource.RAW_FALLBACK, -2.0, 0.0, 4.0, 3.0),
        ],
    ]

    for rects in cases:
        candidates = [
            _flat_candidate(source, f"{source.value}:{idx}", x0, z0, x0 + width, z0 + depth)
            for idx, (source, x0, z0, width, depth) in enumerate(rects)
        ]
        total_candidate_area = sum(width * depth for _source, _x0, _z0, width, depth in rects)
        pieces = assemble_ceiling(candidates)

        total_visible = sum(_visible_xz_poly(piece).area for piece in pieces)
        assert total_visible <= total_candidate_area + 1e-6
        for idx, piece in enumerate(pieces):
            poly = _visible_xz_poly(piece)
            for other in pieces[idx + 1 :]:
                assert poly.intersection(_visible_xz_poly(other)).area < 1e-8
            for corner in piece.corners:
                assert abs(piece.plane.a * corner.x + piece.plane.b * corner.y + piece.plane.c * corner.z - piece.plane.d) < 1e-8


def test_painter_occupied_xz_area_matches_legacy_combined_subtraction_for_cohort():
    _load_legacy_server_caches()
    uuids = [
        "c72ad855-9e52-46f1-886d-a9f37911521f",
        "f40dcc9f-b97b-4bef-8b40-ba011aabf0bd",
        "2ea3b759-e047-424c-8034-f8ee5b811fb4",
        # Dormer-cutout regression: cutouts are visual holes but still occupy
        # XZ space so lower-priority raw fallback cannot refill them.
        "7153d532-16c1-45e8-b7c9-f5cd1ba5cc85",
    ]

    for uuid in uuids:
        candidates = [
            candidate
            for idx, piece in enumerate(
                legacy_viewer_server._active_slanted_source_pieces_for_uuid(uuid)
            )
            if (
                candidate := _candidate_from_corners(
                    CeilingSource.ROOF_ARRANGEMENT,
                    f"{uuid}::tier-ceiling-roof-arrangement::{idx}",
                    piece.get("corners") or piece.get("poly") or [],
                )
            )
            is not None
        ]
        holes = [
            _dormer_cutout_candidate(uuid, idx, xz_poly, coeffs)
            for idx, (xz_poly, coeffs) in enumerate(
                legacy_viewer_server._dormer_cutouts_for_uuid(uuid)
            )
        ]
        pieces = assemble_ceiling(candidates, holes)
        occupied_polys = [_xz_poly(piece) for piece in pieces] + [
            Polygon([(corner[0], corner[2]) for corner in hole.corners])
            for hole in holes
        ]
        painter_area = unary_union(occupied_polys).area if occupied_polys else 0.0
        legacy_union = legacy_viewer_server._combined_ceiling_subtraction(uuid)
        legacy_area = legacy_union.area if legacy_union is not None else 0.0

        assert abs(painter_area - legacy_area) <= 0.5, uuid
