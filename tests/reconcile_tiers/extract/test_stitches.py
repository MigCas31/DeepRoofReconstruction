from collections import Counter
from math import isfinite
from pathlib import Path

import pytest

from reconcile_tiers.extract.building import extract_building_model


@pytest.mark.parametrize(
    ("uuid", "expected_stitch_types"),
    [
        (
            "c72ad855-9e52-46f1-886d-a9f37911521f",
            {"stitch": 5, "stitch_floor": 1, "stitch_ceiling": 1},
        ),
        (
            "f40dcc9f-b97b-4bef-8b40-ba011aabf0bd",
            {"stitch": 8},
        ),
        (
            "2ea3b759-e047-424c-8034-f8ee5b811fb4",
            {"stitch": 9, "stitch_floor": 6, "stitch_ceiling": 6},
        ),
    ],
)
def test_stitch_wall_gaps_match_legacy_cohort_output(uuid, expected_stitch_types):
    model = extract_building_model(uuid, Path("pipeline-outputs"), Path(".scan-cache"))

    assert Counter(stitch.type for stitch in model.stitch_walls) == expected_stitch_types
    for stitch in model.stitch_walls:
        assert stitch.id
        assert stitch.room_index is not None
        assert len(stitch.room_indices) >= 2
        assert len(stitch.corners) >= 3
        assert all(isfinite(coord) for corner in stitch.corners for coord in corner)
        if stitch.type == "stitch":
            assert len(stitch.corners) == 4
            ys = [corner[1] for corner in stitch.corners]
            assert max(ys) - min(ys) > 0.5
