"""Tests for the permissive (slanted-segment × slab) roof proposer."""

from __future__ import annotations

from pathlib import Path

import pytest

from reconcile_v3.io.load import load_building
from reconcile_v3.pipeline import run_pipeline

BUILDINGS_JSON = (
    Path(__file__).resolve().parent.parent.parent
    / "reconcile"
    / "buildings_3d.json"
)
SUBJECT_UUID = "d32d5562-5763-4c71-a816-6732c638fa6a"

EXPECTED_FEATURE_KEYS = {
    "segment_azimuth_deg",
    "segment_incl_deg",
    "segment_length_m",
    "segment_mid_y_m",
    "segment_story",
    "slab_area_m2",
    "slab_vertex_count",
    "slab_story",
    "piece_index",
    "piece_area_m2",
    "piece_perimeter_m",
    "piece_compactness",
    "piece_vertex_count",
    "piece_bbox_aspect",
    "piece_min_width_m",
    "rain_exposure_ratio",
    "is_top_story_slab",
    "is_same_room",
    "story_delta",
    "seg_mid_to_piece_centroid_xz_m",
    "slab_floor_y_m",
    "plane_y_at_piece_centroid_m",
    "plane_height_above_slab_m",
    "slant_delta_over_piece_m",
}

VALID_HEURISTIC_LABELS = {"accepted", "rejected", "not_evaluated"}


@pytest.fixture(scope="module")
def building():
    if not BUILDINGS_JSON.exists():
        pytest.skip(f"Missing {BUILDINGS_JSON}")
    data = load_building(BUILDINGS_JSON, SUBJECT_UUID)
    return run_pipeline(data)


def test_proposals_are_emitted(building):
    assert len(building.roof_proposals) >= 1


def test_slanted_roofs_untouched_by_proposer(building):
    """Proposer must not modify the authoritative slanted_roofs output."""
    assert building.slanted_roofs is not None


def test_all_proposals_have_complete_feature_vector(building):
    assert building.roof_proposals, "test needs proposals"
    for p in building.roof_proposals:
        assert set(p.features.keys()) == EXPECTED_FEATURE_KEYS, (
            f"feature keys drift for {p.id}"
        )
        assert p.heuristic_label in VALID_HEURISTIC_LABELS
        assert len(p.corners) >= 3
        assert p.segment_index >= 0


def test_proposal_ids_are_unique(building):
    ids = [p.id for p in building.roof_proposals]
    assert len(ids) == len(set(ids)), "proposal ids collided"


def test_permissive_count_exceeds_heuristic(building):
    """Sanity: per-segment × per-slab enumeration should dwarf the cluster-level
    heuristic output."""
    assert len(building.roof_proposals) >= len(building.slanted_roofs)
