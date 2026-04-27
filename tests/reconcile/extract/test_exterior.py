from collections import Counter
from math import isfinite
from pathlib import Path

import pytest

from reconcile_tiers.extract.building import extract_building_model


@pytest.mark.parametrize(
    ("uuid", "expected_indicators", "expected_closures"),
    [
        (
            "c72ad855-9e52-46f1-886d-a9f37911521f",
            {"door": 1, "storage": 2},
            {"side": 6, "floor": 3, "ceiling": 3},
        ),
        (
            "f40dcc9f-b97b-4bef-8b40-ba011aabf0bd",
            {"door": 1, "storage": 1},
            {"side": 4, "floor": 2, "ceiling": 2},
        ),
        (
            "2ea3b759-e047-424c-8034-f8ee5b811fb4",
            {"door": 1},
            {"side": 2, "floor": 1, "ceiling": 1},
        ),
    ],
)
def test_exterior_gap_indicators_and_closures_match_legacy_cohort(
    uuid,
    expected_indicators,
    expected_closures,
):
    model = extract_building_model(uuid, Path("pipeline-outputs"), Path(".scan-cache"))

    assert Counter(indicator.element_type for indicator in model.exterior_gap_indicators) == expected_indicators
    assert Counter(closure.type for closure in model.gap_closures) == expected_closures
    for indicator in model.exterior_gap_indicators:
        assert indicator.element_id
        assert indicator.wall_id
        assert indicator.wall_distance_m > 0.0
        assert indicator.element_width_m >= 0.5
    for closure in model.gap_closures:
        assert len(closure.corners) == 4
        assert all(isfinite(coord) for corner in closure.corners for coord in corner)
