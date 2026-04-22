"""Phase A tests for reconcile_v3/reconstruction/candidate_faces.py.

Synthetic buildings with known geometry so we can assert what the
candidate-face generator should emit. Numbers to keep in your head:

* Gable over a 6 m x 4 m footprint, ridge along x at z=2 m:
  each slope's clipped face should be the 6 m x 2 m half-footprint —
  area 12 m², split by the ridge line.
* Hip over a 6 m x 4 m footprint: four planes meeting at a single
  ridge point; each face is a triangle of area 6 m².
"""

from __future__ import annotations

import math

from reconcile_v3.reconstruction.candidate_faces import (
    build_candidate_faces,
)

_BLDG = "test-building"


def _plane_from_normal_and_point(
    nx: float, ny: float, nz: float, px: float, py: float, pz: float
) -> tuple[float, float, float, float]:
    """Unit-normalised (a, b, c, d) for the plane with normal (nx, ny, nz)
    passing through (px, py, pz). Convention: ``a·x + b·y + c·z + d = 0``."""
    norm = math.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / norm, ny / norm, nz / norm
    d = -(nx * px + ny * py + nz * pz)
    return nx, ny, nz, d


def _segment(
    seg_id: str,
    plane,
    footprint_xz_pairs,
    *,
    opposing_planes=None,
    opposing_canonicals=None,
    cluster_canonical_id: str = "cluster-A",
    area_m2: float | None = None,
) -> dict:
    fp = [[float(x), 0.0, float(z)] for (x, z) in footprint_xz_pairs]
    return {
        "id": seg_id,
        "cluster_canonical_id": cluster_canonical_id,
        "merged_plane": list(plane),
        "footprint_xz": fp,
        "opposing_planes": [list(p) for p in (opposing_planes or [])],
        "opposing_cluster_canonicals": list(opposing_canonicals or []),
        "features": {"area_m2": area_m2 if area_m2 is not None else 1.0},
    }


def _ring_area(ring):
    n = len(ring)
    a = 0.0
    for i in range(n):
        xi, zi = ring[i]
        xj, zj = ring[(i + 1) % n]
        a += xi * zj - xj * zi
    return abs(a) / 2.0


def test_gable_two_planes_split_footprint_at_ridge() -> None:
    # 6 m (x) × 4 m (z) gable. Ridge along x at z = 2. Slope = 1 (45°).
    # South slope normal (+z component) passes through ridge (0, 2, 2),
    # rises toward -z. Actually, construct both planes from geometry:
    # * plane_south: passes through z=0 at y=0 and z=2 at y=2 (rising N→S
    #   at 45°). Normal = (0, 1, -1)/sqrt2. Point: (0, 2, 2).
    # * plane_north: passes through z=4 at y=0 and z=2 at y=2 (rising N→S
    #   in the opposite sense). Normal = (0, 1, 1)/sqrt2. Point: (0, 2, 2).
    plane_south = _plane_from_normal_and_point(0.0, 1.0, -1.0, 0.0, 2.0, 2.0)
    plane_north = _plane_from_normal_and_point(0.0, 1.0, 1.0, 0.0, 2.0, 2.0)

    # Segments cover their respective halves but leave a 0.5 m gap either
    # side of the ridge — so extension must fill to the ridge.
    south_fp = [(0.0, 0.0), (6.0, 0.0), (6.0, 1.5), (0.0, 1.5)]
    north_fp = [(0.0, 2.5), (6.0, 2.5), (6.0, 4.0), (0.0, 4.0)]

    segments = [
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::south",
            plane_south, south_fp,
            opposing_planes=[plane_north],
            opposing_canonicals=["cluster-north"],
            cluster_canonical_id="cluster-south",
            area_m2=9.0,
        ),
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::north",
            plane_north, north_fp,
            opposing_planes=[plane_south],
            opposing_canonicals=["cluster-south"],
            cluster_canonical_id="cluster-north",
            area_m2=9.0,
        ),
    ]
    footprint = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]

    faces = build_candidate_faces(_BLDG, segments, footprint)

    assert len(faces) == 2
    by_parent = {f.parent_segment_id.split("::")[-1]: f for f in faces}
    south = by_parent["south"]
    north = by_parent["north"]

    # Both should extend to the ridge line z = 2 (half of the 24 m² footprint).
    assert south.extended and north.extended
    assert south.area_m2 == 12.0 or math.isclose(south.area_m2, 12.0, abs_tol=0.01)
    assert math.isclose(north.area_m2, 12.0, abs_tol=0.01)
    # Combined coverage is the full footprint (no overlap expected at the ridge).
    assert math.isclose(south.area_m2 + north.area_m2, 24.0, abs_tol=0.01)

    # Each face must cover its OWN half of the footprint, not the opposing
    # half. Without this assertion both choices of ridge half-plane sum to
    # 24 m² — but only "own half" renders a valid roof (ridge at the top);
    # the opposing choice renders an inverted V (apex at the bottom).
    south_z = [z for (_, z) in south.footprint_xz]
    north_z = [z for (_, z) in north.footprint_xz]
    assert max(south_z) <= 2.0 + 1e-6, f"south leaked past ridge: max z={max(south_z)}"
    assert min(north_z) >= 2.0 - 1e-6, f"north leaked past ridge: min z={min(north_z)}"

    # Azimuths should be opposed (~180° apart).
    az_diff = abs(((south.azimuth_deg - north.azimuth_deg) + 180.0) % 360.0 - 180.0)
    assert az_diff > 170.0, f"expected opposed azimuths, got {az_diff}"

    # Neighbours wired up via opposing_cluster_canonicals.
    assert north.id in south.neighbors
    assert south.id in north.neighbors


def test_segment_without_opposing_planes_is_not_extended() -> None:
    # A single shed plane with no opposing partners — should pass through
    # unchanged (apart from clipping to the scan footprint).
    plane = _plane_from_normal_and_point(0.0, 1.0, -0.25, 0.0, 2.0, 0.0)
    seg_fp = [(1.0, 1.0), (5.0, 1.0), (5.0, 3.0), (1.0, 3.0)]
    footprint = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]

    faces = build_candidate_faces(
        _BLDG,
        [_segment(f"{_BLDG}::v3-merged-roof-segment::lone", plane, seg_fp, area_m2=8.0)],
        footprint,
    )

    assert len(faces) == 1
    face = faces[0]
    assert not face.extended
    assert math.isclose(face.area_m2, 8.0, abs_tol=0.05)
    assert face.neighbors == []


def test_candidates_clipped_to_scan_footprint() -> None:
    # Gable where segments' raw footprints poke outside the scan footprint
    # (e.g. scanner overshoot). Candidate polygons must not leak past the
    # scan outline.
    plane_s = _plane_from_normal_and_point(0.0, 1.0, -1.0, 0.0, 2.0, 2.0)
    plane_n = _plane_from_normal_and_point(0.0, 1.0, 1.0, 0.0, 2.0, 2.0)
    south_fp = [(-1.0, 0.0), (7.0, 0.0), (7.0, 1.5), (-1.0, 1.5)]  # overshoots x
    north_fp = [(-1.0, 2.5), (7.0, 2.5), (7.0, 4.0), (-1.0, 4.0)]
    footprint = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]

    segments = [
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::south", plane_s, south_fp,
            opposing_planes=[plane_n], opposing_canonicals=["c-n"],
            cluster_canonical_id="c-s", area_m2=12.0,
        ),
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::north", plane_n, north_fp,
            opposing_planes=[plane_s], opposing_canonicals=["c-s"],
            cluster_canonical_id="c-n", area_m2=12.0,
        ),
    ]
    faces = build_candidate_faces(_BLDG, segments, footprint)

    for face in faces:
        xs = [x for (x, _) in face.footprint_xz]
        zs = [z for (_, z) in face.footprint_xz]
        assert min(xs) >= -1e-6, f"leaked negative x: {min(xs)}"
        assert max(xs) <= 6.0 + 1e-6, f"leaked past x=6: {max(xs)}"
        assert min(zs) >= -1e-6
        assert max(zs) <= 4.0 + 1e-6


def test_degenerate_segments_are_skipped() -> None:
    good_plane = _plane_from_normal_and_point(0.0, 1.0, -0.25, 0.0, 2.0, 0.0)
    good_fp = [(1.0, 1.0), (5.0, 1.0), (5.0, 3.0), (1.0, 3.0)]

    segs = [
        # Missing plane
        {"id": "bad1", "merged_plane": None, "footprint_xz": good_fp},
        # Zero-norm plane
        _segment("bad2", [0.0, 0.0, 0.0, 0.0], good_fp),
        # Degenerate ring
        _segment("bad3", [0.0, 1.0, 0.0, 0.0], [(0.0, 0.0), (1.0, 0.0)]),
        # OK segment
        _segment("ok", good_plane, good_fp),
    ]
    faces = build_candidate_faces(_BLDG, segs, None)
    assert len(faces) == 1
    assert faces[0].parent_segment_id == "ok"


def test_segment_on_rain_side_extends_within_rain_half() -> None:
    # Upstream emits segments on BOTH sides of each opposing seam ("rain"
    # and "covered"). A rain-side segment sits where ``own.y > other.y``
    # — if we naively clipped to ``own.y <= other.y`` we'd translate the
    # face across the ridge. Here we construct two segments that share a
    # plane but live on opposite halves and confirm each grows within its
    # own side.
    plane_south = _plane_from_normal_and_point(0.0, 1.0, -1.0, 0.0, 2.0, 2.0)
    plane_north = _plane_from_normal_and_point(0.0, 1.0, 1.0, 0.0, 2.0, 2.0)

    # Segment centroid at z ≈ 0.75 — on the "covered" half (y_south < y_north).
    seg_covered_fp = [(0.0, 0.0), (6.0, 0.0), (6.0, 1.5), (0.0, 1.5)]
    # Segment centroid at z ≈ 3.25 — on the "rain" half for plane_south
    # (y_south > y_north, since y_south = z and y_north = 4 - z).
    seg_rain_fp = [(0.0, 2.5), (6.0, 2.5), (6.0, 4.0), (0.0, 4.0)]

    footprint = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]

    segments = [
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::south-covered",
            plane_south, seg_covered_fp,
            opposing_planes=[plane_north],
            cluster_canonical_id="cluster-south",
            area_m2=9.0,
        ),
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::south-rain",
            plane_south, seg_rain_fp,
            opposing_planes=[plane_north],
            cluster_canonical_id="cluster-south",
            area_m2=9.0,
        ),
    ]
    faces = build_candidate_faces(_BLDG, segments, footprint)
    assert len(faces) == 2
    by_parent = {f.parent_segment_id.split("::")[-1]: f for f in faces}
    covered = by_parent["south-covered"]
    rain = by_parent["south-rain"]

    # Covered-side segment must stay on z <= 2; rain-side must stay on z >= 2.
    covered_z = [z for (_, z) in covered.footprint_xz]
    rain_z = [z for (_, z) in rain.footprint_xz]
    assert max(covered_z) <= 2.0 + 1e-6, f"covered leaked past ridge: max z={max(covered_z)}"
    assert min(rain_z) >= 2.0 - 1e-6, f"rain leaked past ridge: min z={min(rain_z)}"
    # Both should extend to the full 12 m² half.
    assert math.isclose(covered.area_m2, 12.0, abs_tol=0.01)
    assert math.isclose(rain.area_m2, 12.0, abs_tol=0.01)


def test_no_footprint_returns_unextended_candidates() -> None:
    # Without a scan footprint, extension works against opposing planes but
    # the base region is the segment's own footprint.
    plane_s = _plane_from_normal_and_point(0.0, 1.0, -1.0, 0.0, 2.0, 2.0)
    plane_n = _plane_from_normal_and_point(0.0, 1.0, 1.0, 0.0, 2.0, 2.0)
    south_fp = [(0.0, 0.0), (6.0, 0.0), (6.0, 1.5), (0.0, 1.5)]
    north_fp = [(0.0, 2.5), (6.0, 2.5), (6.0, 4.0), (0.0, 4.0)]

    segments = [
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::south", plane_s, south_fp,
            opposing_planes=[plane_n], area_m2=9.0,
        ),
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::north", plane_n, north_fp,
            opposing_planes=[plane_s], area_m2=9.0,
        ),
    ]
    faces = build_candidate_faces(_BLDG, segments, None)
    assert len(faces) == 2
    # Each face can only be as big as its own segment footprint (9 m²) since
    # there is no scan footprint to extend into.
    for f in faces:
        assert f.area_m2 <= 9.0 + 0.01
