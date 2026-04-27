from collections import Counter
from pathlib import Path

import pytest

from reconcile_tiers.extract.building import extract_building_model


@pytest.mark.parametrize(
    ("uuid", "expected_types", "expected_polygons", "expected_raw_planes"),
    [
        ("c72ad855-9e52-46f1-886d-a9f37911521f", {"flat": 6, None: 4}, 6, 20),
        ("f40dcc9f-b97b-4bef-8b40-ba011aabf0bd", {"flat": 9}, 9, 9),
        ("2ea3b759-e047-424c-8034-f8ee5b811fb4", {"flat": 9, None: 2}, 9, 12),
        ("107e8496-9bff-42bb-b776-720f44b70e55", {"flat": 7, "sloped": 2}, 9, 9),
    ],
)
def test_infer_ceilings_matches_legacy_cohort_types_and_raw_plane_counts(
    uuid,
    expected_types,
    expected_polygons,
    expected_raw_planes,
):
    model = extract_building_model(uuid, Path("pipeline-outputs"), Path(".scan-cache"))

    assert Counter(room.ceiling_type for room in model.rooms) == expected_types
    assert sum(1 for room in model.rooms if room.ceiling_polygon) == expected_polygons
    assert sum(len(room.raw_ceiling_planes) for room in model.rooms) == expected_raw_planes


def test_flat_ceiling_polygons_are_horizontal_and_above_floors():
    model = extract_building_model(
        "f40dcc9f-b97b-4bef-8b40-ba011aabf0bd",
        Path("pipeline-outputs"),
        Path(".scan-cache"),
    )

    for room in model.rooms:
        assert room.ceiling_type == "flat"
        assert room.ceiling_polygon
        ceiling_ys = {round(corner[1], 4) for corner in room.ceiling_polygon}
        floor_y = sum(corner[1] for corner in room.floor_polygon) / len(room.floor_polygon)
        assert len(ceiling_ys) == 1
        assert next(iter(ceiling_ys)) > floor_y
        assert room.ceiling_eave_height == room.ceiling_ridge_height == next(iter(ceiling_ys))
