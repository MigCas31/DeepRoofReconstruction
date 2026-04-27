from dataclasses import replace

import pytest

from reconcile_tiers.extract.building import ExtractedRoom, ExtractedWall
from reconcile_tiers.extract.height_align import align_room_heights
from reconcile_tiers.extract.overlaps import clip_walls_to_story_bounds


def _wall(wall_id, floor_y, top_y):
    return ExtractedWall(
        id=wall_id,
        source="synthetic",
        corners=[
            [0.0, top_y, 0.0],
            [1.0, top_y, 0.0],
            [1.0, floor_y, 0.0],
            [0.0, floor_y, 0.0],
        ],
    )


def _room(index, floor_y, top_y):
    return ExtractedRoom(
        index=index,
        story=0,
        floor_polygon=[
            [0.0, floor_y, 0.0],
            [1.0, floor_y, 0.0],
            [1.0, floor_y, 1.0],
            [0.0, floor_y, 1.0],
        ],
        walls_merged=[],
        walls_computed=[_wall(f"w{index}", floor_y, top_y)],
        doors=[],
        windows=[],
        openings=[],
        storages=[],
        raw_ceiling_planes=[],
        raw_ceiling_source=None,
        ceiling_polygon=[],
        ceiling_type=None,
        ceiling_eave_height=None,
        ceiling_ridge_height=None,
    )


def test_align_room_heights_snaps_near_coplanar_floor_and_wall_tops():
    rooms = [_room(0, 0.0, 2.50), _room(1, 0.04, 2.56)]

    aligned, metrics = align_room_heights(rooms)

    assert metrics["aligned_groups"] == 1
    assert metrics["aligned_rooms"] == 2
    assert metrics["aligned_walls"] == 2
    floor_ys = {round(corner[1], 6) for room in aligned for corner in room.floor_polygon}
    assert floor_ys == {0.02}
    top_ys = {
        corner[1]
        for room in aligned
        for wall in room.walls_computed
        for corner in wall.corners[:2]
    }
    assert len(top_ys) == 1
    assert next(iter(top_ys)) == pytest.approx(2.53)


def test_align_room_heights_keeps_rooms_with_different_wall_heights_separate():
    rooms = [_room(0, 0.0, 2.50), _room(1, 0.04, 2.80)]

    aligned, metrics = align_room_heights(rooms)

    assert metrics["aligned_groups"] == 0
    assert [room.floor_polygon[0][1] for room in aligned] == [0.0, 0.04]
    assert [room.walls_computed[0].corners[0][1] for room in aligned] == [2.50, 2.80]


def test_clip_walls_to_story_bounds_caps_wall_at_next_story_floor():
    lower = _room(0, 0.0, 3.20)
    upper = replace(_room(1, 2.80, 5.20), story=1)

    clipped, metrics = clip_walls_to_story_bounds([lower, upper], {0: 0.0, 1: 2.80})

    assert metrics["walls_clipped"] == 1
    assert max(corner[1] for corner in clipped[0].walls_computed[0].corners) == 2.80
