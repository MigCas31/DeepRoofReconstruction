"""Phase B.1 tests for reconcile_v3/reconstruction/solver.py.

We synthesize the same gable fixtures used in ``test_candidate_faces`` then
push the emitted candidates through :func:`solve_building` and assert on
the BIP behaviour: unique optimal selection on a gable, infeasibility when
coverage is starved, azimuth-bin capping, and topology rejection of
isolated faces.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict

from reconcile_v3.reconstruction.candidate_faces import (
    CandidateFace,
    build_candidate_faces,
)
from reconcile_v3.reconstruction.solver import (
    SolverConfig,
    solve_building,
)

_BLDG = "test-building"


def _plane_from_normal_and_point(
    nx: float, ny: float, nz: float, px: float, py: float, pz: float
) -> tuple[float, float, float, float]:
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


def _gable_candidates() -> tuple[list[dict], list[tuple[float, float]]]:
    plane_s = _plane_from_normal_and_point(0.0, 1.0, -1.0, 0.0, 2.0, 2.0)
    plane_n = _plane_from_normal_and_point(0.0, 1.0, 1.0, 0.0, 2.0, 2.0)
    south_fp = [(0.0, 0.0), (6.0, 0.0), (6.0, 1.5), (0.0, 1.5)]
    north_fp = [(0.0, 2.5), (6.0, 2.5), (6.0, 4.0), (0.0, 4.0)]
    segments = [
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::south", plane_s, south_fp,
            opposing_planes=[plane_n], opposing_canonicals=["cluster-north"],
            cluster_canonical_id="cluster-south", area_m2=12.0,
        ),
        _segment(
            f"{_BLDG}::v3-merged-roof-segment::north", plane_n, north_fp,
            opposing_planes=[plane_s], opposing_canonicals=["cluster-south"],
            cluster_canonical_id="cluster-north", area_m2=12.0,
        ),
    ]
    footprint = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]
    faces = build_candidate_faces(_BLDG, segments, footprint)
    return [asdict(f) for f in faces], footprint


def test_gable_two_planes_unique_optimal() -> None:
    # On a clean gable both faces must be selected (each covers half the
    # footprint so only the union satisfies coverage), the solver should
    # report "solved", and the selection should auto-accept.
    cands, fp = _gable_candidates()
    assert len(cands) == 2, "fixture regression: gable should produce 2 candidates"

    t0 = time.perf_counter()
    res = solve_building(_BLDG, cands, fp)
    elapsed = time.perf_counter() - t0

    assert res.status == "solved", f"got {res.status}: {res.reason}"
    assert len(res.selected_face_ids) == 2
    assert set(res.selected_face_ids) == {c["id"] for c in cands}
    assert res.coverage_ratio >= 0.99
    assert res.decision == "auto_accept", f"expected auto_accept, got {res.decision}"
    assert elapsed < 2.0, f"gable solve took {elapsed:.2f}s"


def test_forced_infeasible_high_coverage_threshold() -> None:
    # Only one small sliver candidate; theta_cov=0.99 of a 24 m² footprint
    # demands far more coverage than the candidate can provide.
    plane = _plane_from_normal_and_point(0.0, 1.0, -1.0, 0.0, 2.0, 2.0)
    seg_fp = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]  # 1 m² sliver
    segments = [
        _segment(f"{_BLDG}::v3-merged-roof-segment::sliver", plane, seg_fp, area_m2=1.0),
    ]
    footprint = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]  # 24 m²
    cands = [asdict(f) for f in build_candidate_faces(_BLDG, segments, footprint)]
    assert cands, "fixture regression: sliver should produce at least one candidate"

    res = solve_building(
        _BLDG, cands, footprint,
        config=SolverConfig(theta_cov=0.99),
    )
    assert res.status == "infeasible", f"expected infeasible, got {res.status}"
    assert res.selected_face_ids == []


def test_no_candidates_returns_no_candidates_status() -> None:
    fp = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]
    res = solve_building(_BLDG, [], fp)
    assert res.status == "no_candidates"
    assert res.decision == "review"
    assert res.selected_face_ids == []


def test_azimuth_bin_constraint_limits_selection() -> None:
    # The gable has two candidates with opposed azimuths (~180° apart).
    # With azimuth_bin_width_deg=45 they fall in different bins; capping
    # k_azimuth_bins=1 forces the solver to pick AT MOST one — and, with
    # theta_cov high enough that one face can't satisfy coverage, the
    # whole problem turns infeasible.
    cands, fp = _gable_candidates()

    res = solve_building(
        _BLDG, cands, fp,
        config=SolverConfig(k_azimuth_bins=1, theta_cov=0.85),
    )
    # Coverage constraint (0.85 × 24 = 20.4 m²) cannot be met with only
    # one 12 m² half, so the model is infeasible under the single-bin cap.
    assert res.status == "infeasible", f"expected infeasible, got {res.status}: {res.reason}"


def test_azimuth_bin_cap_two_allows_gable() -> None:
    # Same fixture but with k_azimuth_bins=2 — must solve cleanly.
    cands, fp = _gable_candidates()
    res = solve_building(
        _BLDG, cands, fp,
        config=SolverConfig(k_azimuth_bins=2),
    )
    assert res.status == "solved"
    assert len(res.selected_face_ids) == 2


def test_topology_constraint_requires_neighbour_when_available() -> None:
    # A face with in-set neighbours can only be picked if at least one of
    # its neighbours is also picked. Build a 3-face linear chain A–B–C
    # where B is the only one satisfying coverage; if the solver picks B
    # it MUST also pick a neighbour (A or C) to honour topology.
    plane_s = _plane_from_normal_and_point(0.0, 1.0, -1.0, 0.0, 2.0, 2.0)
    plane_n = _plane_from_normal_and_point(0.0, 1.0, 1.0, 0.0, 2.0, 2.0)
    a_id = f"{_BLDG}::candidate::a"
    b_id = f"{_BLDG}::candidate::b"
    c_id = f"{_BLDG}::candidate::c"
    cands = [
        {
            "id": a_id, "building_uuid": _BLDG,
            "parent_segment_id": f"{_BLDG}::v3-merged-roof-segment::a",
            "plane": list(plane_s),
            "footprint_xz": [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)],
            "area_m2": 4.0, "azimuth_deg": 180.0, "inclination_deg": 45.0,
            "neighbors": [b_id], "support_m2": 4.0,
            "extended": False, "gbm_prior": None,
        },
        {
            "id": b_id, "building_uuid": _BLDG,
            "parent_segment_id": f"{_BLDG}::v3-merged-roof-segment::b",
            "plane": list(plane_n),
            "footprint_xz": [(0.0, 2.0), (2.0, 2.0), (2.0, 4.0), (0.0, 4.0)],
            "area_m2": 4.0, "azimuth_deg": 0.0, "inclination_deg": 45.0,
            "neighbors": [a_id, c_id], "support_m2": 4.0,
            "extended": False, "gbm_prior": None,
        },
        {
            "id": c_id, "building_uuid": _BLDG,
            "parent_segment_id": f"{_BLDG}::v3-merged-roof-segment::c",
            "plane": list(plane_s),
            "footprint_xz": [(0.0, 4.0), (2.0, 4.0), (2.0, 6.0), (0.0, 6.0)],
            "area_m2": 4.0, "azimuth_deg": 180.0, "inclination_deg": 45.0,
            "neighbors": [b_id], "support_m2": 4.0,
            "extended": False, "gbm_prior": None,
        },
    ]
    fp = [(0.0, 0.0), (2.0, 0.0), (2.0, 6.0), (0.0, 6.0)]
    res = solve_building(_BLDG, cands, fp, config=SolverConfig(k_azimuth_bins=2))
    assert res.status == "solved"
    picked = set(res.selected_face_ids)
    if b_id in picked:
        assert picked & {a_id, c_id}, (
            "B has in-set neighbours, so at least one neighbour must also be picked"
        )


def test_isolated_face_is_selectable() -> None:
    # A face with no in-set neighbours must remain selectable — forcing
    # it to 0 made buildings whose Phase A slices lack cross-references
    # spuriously infeasible (32/34 of the 20260419 corpus 'infeasible'
    # bucket). A single positive-utility isolated face should be picked.
    lone = {
        "id": f"{_BLDG}::candidate::lone",
        "building_uuid": _BLDG,
        "parent_segment_id": f"{_BLDG}::v3-merged-roof-segment::lone",
        "plane": list(_plane_from_normal_and_point(0.0, 1.0, 0.0, 0.0, 0.0, 0.0)),
        "footprint_xz": [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        "area_m2": 16.0, "azimuth_deg": 0.0, "inclination_deg": 10.0,
        "neighbors": [], "support_m2": 16.0,
        "extended": False, "gbm_prior": None,
    }
    fp = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    other = {
        **lone,
        "id": f"{_BLDG}::candidate::other",
        "footprint_xz": [(10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0)],
        "area_m2": 1.0, "support_m2": 0.0,
        "neighbors": [],
    }
    res = solve_building(_BLDG, [lone, other], fp, config=SolverConfig())
    assert res.status == "solved"
    assert lone["id"] in res.selected_face_ids


def test_runner_up_captured_when_alternatives_exist() -> None:
    # Three candidates where two equivalent subsets satisfy coverage.
    # The runner-up objective should be positive and close to the primary
    # — triggering the ambiguity flag.
    plane_s = _plane_from_normal_and_point(0.0, 1.0, -1.0, 0.0, 2.0, 2.0)
    plane_n = _plane_from_normal_and_point(0.0, 1.0, 1.0, 0.0, 2.0, 2.0)

    # Two near-identical south faces (call them "south_a" and "south_b")
    # both cover the same south half — the BIP can pick either. Both have
    # identical fit. Plus a required north face.
    south_fp = [(0.0, 0.0), (6.0, 0.0), (6.0, 2.0), (0.0, 2.0)]
    north_fp = [(0.0, 2.0), (6.0, 2.0), (6.0, 4.0), (0.0, 4.0)]
    north_id = f"{_BLDG}::candidate::north"
    cands = [
        {
            "id": f"{_BLDG}::candidate::south_a",
            "building_uuid": _BLDG,
            "parent_segment_id": f"{_BLDG}::v3-merged-roof-segment::south_a",
            "plane": list(plane_s),
            "footprint_xz": south_fp,
            "area_m2": 12.0,
            "azimuth_deg": 180.0,
            "inclination_deg": 45.0,
            "neighbors": [north_id],
            "support_m2": 12.0,
            "extended": False,
            "gbm_prior": None,
        },
        {
            "id": f"{_BLDG}::candidate::south_b",
            "building_uuid": _BLDG,
            "parent_segment_id": f"{_BLDG}::v3-merged-roof-segment::south_b",
            "plane": list(plane_s),
            "footprint_xz": south_fp,
            "area_m2": 12.0,
            "azimuth_deg": 180.0,
            "inclination_deg": 45.0,
            "neighbors": [north_id],
            "support_m2": 12.0,
            "extended": False,
            "gbm_prior": None,
        },
        {
            "id": north_id,
            "building_uuid": _BLDG,
            "parent_segment_id": f"{_BLDG}::v3-merged-roof-segment::north",
            "plane": list(plane_n),
            "footprint_xz": north_fp,
            "area_m2": 12.0,
            "azimuth_deg": 0.0,
            "inclination_deg": 45.0,
            "neighbors": [
                f"{_BLDG}::candidate::south_a",
                f"{_BLDG}::candidate::south_b",
            ],
            "support_m2": 12.0,
            "extended": False,
            "gbm_prior": None,
        },
    ]
    fp = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]
    # Low theta_overlap so the duplicated souths conflict (same plane,
    # same footprint → trivially > 10% overlap, azimuth diff 0°).
    res = solve_building(
        _BLDG, cands, fp,
        config=SolverConfig(theta_overlap=0.10, theta_az_deg=45.0),
    )
    assert res.status in ("solved", "ambiguous")
    assert res.runner_up_objective > 0.0
    # Runner-up should be close enough to primary to trigger ambiguity
    # — both alternative selections (south_a+north vs south_b+north) have
    # identical objective, so runner_up == primary.
    assert math.isclose(
        res.objective_value, res.runner_up_objective, rel_tol=1e-3
    ), f"expected tied runner-up, got obj={res.objective_value} runner={res.runner_up_objective}"


def test_candidate_face_dataclass_round_trip_through_asdict() -> None:
    # Regression guard: `solve_building` takes dicts, but Phase A emits
    # `CandidateFace` dataclasses. `asdict` must produce the exact keys
    # the solver reads. If this test fails with a KeyError the dataclass
    # has drifted from the solver contract.
    face = CandidateFace(
        id="x::candidate::a",
        building_uuid="x",
        parent_segment_id="x::v3-merged-roof-segment::a",
        plane=(0.0, 1.0, 0.0, 0.0),
        footprint_xz=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        area_m2=1.0,
        azimuth_deg=0.0,
        inclination_deg=0.0,
        neighbors=[],
        support_m2=1.0,
        extended=False,
        gbm_prior=None,
    )
    d = asdict(face)
    for key in (
        "id", "footprint_xz", "area_m2", "azimuth_deg",
        "support_m2", "gbm_prior", "neighbors",
    ):
        assert key in d, f"CandidateFace drift: missing {key}"
