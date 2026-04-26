from collections import Counter
from math import isfinite
from pathlib import Path

import pytest

from reconcile_tiers.extract.building import extract_building_model


def _projected_xz_area(corners):
    area2 = 0.0
    for idx, corner in enumerate(corners):
        nxt = corners[(idx + 1) % len(corners)]
        area2 += corner[0] * nxt[2] - nxt[0] * corner[2]
    return abs(area2) * 0.5


@pytest.mark.parametrize(
    ("uuid", "expected_gap_types", "expected_floor_vertices", "expected_gap_wall_types"),
    [
        (
            "c72ad855-9e52-46f1-886d-a9f37911521f",
            {"within_story": 14, "cross_story": 19},
            [15, 13, 12, 13, 14, 4, 4, 15, 8, 12],
            {"within_story": 32, "gap_floor": 14, "gap_ceiling": 100},
        ),
        (
            "f40dcc9f-b97b-4bef-8b40-ba011aabf0bd",
            {"within_story": 15},
            [4, 16, 27, 18, 10, 15, 13, 11, 4],
            {"within_story": 42, "gap_floor": 15, "gap_ceiling": 115},
        ),
        (
            "2ea3b759-e047-424c-8034-f8ee5b811fb4",
            {"within_story": 20},
            [6, 15, 27, 26, 0, 10, 19, 4, 10, 20, 4],
            {"within_story": 41, "gap_floor": 19, "gap_ceiling": 99},
        ),
    ],
)
def test_cross_floor_gap_detection_and_absorption_matches_legacy_cohort(
    uuid,
    expected_gap_types,
    expected_floor_vertices,
    expected_gap_wall_types,
):
    model = extract_building_model(uuid, Path("pipeline-outputs"), Path(".scan-cache"))

    assert Counter(gap.type for gap in model.cross_floor_gaps) == expected_gap_types
    assert [len(room.floor_polygon) for room in model.rooms] == expected_floor_vertices

    within_story = [gap for gap in model.cross_floor_gaps if gap.type == "within_story"]
    assert within_story
    assert all(gap.room_index is not None for gap in within_story)
    assert all(gap.ceiling_corners for gap in within_story)
    assert Counter(wall.type for wall in model.gap_walls) == expected_gap_wall_types

    for wall in model.gap_walls:
        assert len(wall.corners) >= 3
        assert all(isfinite(coord) for corner in wall.corners for coord in corner)
        if wall.type == "within_story":
            assert len(wall.corners) == 4
            ys = [corner[1] for corner in wall.corners]
            assert max(ys) - min(ys) > 0.5
        elif wall.type == "gap_floor":
            ys = [corner[1] for corner in wall.corners]
            assert max(ys) - min(ys) < 1e-6
            assert _projected_xz_area(wall.corners) > 1e-6
        elif wall.type == "gap_ceiling":
            assert _projected_xz_area(wall.corners) > 1e-6


def test_within_story_gap_neighborhoods_do_not_emit_duplicate_gap_wall_surfaces():
    model = extract_building_model("0a5032e9-85a0-4970-9143-c430bbdaa0f5", Path("pipeline-outputs"), Path(".scan-cache"))

    gap_wall_ids = [wall.id for wall in model.gap_walls]

    assert len(gap_wall_ids) == len(set(gap_wall_ids))
