from __future__ import annotations

from math import radians, tan

from reconcile_tiers.extract.building import (
    BuildingModel,
    ExtractedRoom,
    ExtractedWall,
    RawCeilingPlane,
)


def _wall(wall_id: str, corners: list[list[float]]) -> ExtractedWall:
    return ExtractedWall(id=wall_id, corners=corners, source="test")


def make_gable_model(include_dormer: bool = False) -> BuildingModel:
    slope = tan(radians(30.0))
    floor = [[0.0, 0.0, 0.0], [6.0, 0.0, 0.0], [6.0, 0.0, 4.0], [0.0, 0.0, 4.0]]
    roof_wall = _wall(
        "roof-plane",
        [
            [0.0, 2.0, 0.0],
            [6.0, 2.0 + slope * 6.0, 0.0],
            [6.0, 2.0 + slope * 6.0, 4.0],
            [0.0, 2.0, 4.0],
        ],
    )
    tall_reference = _wall(
        "tall-reference",
        [
            [6.0, 0.0, 0.0],
            [6.0, 0.0, 4.0],
            [6.0, 4.0, 4.0],
            [6.0, 4.0, 0.0],
        ],
    )
    walls = [roof_wall, tall_reference]
    if include_dormer:
        base_y = 2.0 + slope * 3.0
        walls.append(
            _wall(
                "dormer-front",
                [
                    [3.0, base_y + 0.05, 1.5],
                    [3.0, base_y + 0.05, 2.5],
                    [3.0, base_y + 0.85, 2.5],
                    [3.0, base_y + 0.85, 1.5],
                ],
            )
        )
    room = ExtractedRoom(
        index=0,
        story=0,
        floor_polygon=floor,
        walls_merged=list(walls),
        walls_computed=list(walls),
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
    return BuildingModel(
        uuid="synthetic-gable",
        address=None,
        stories_found=1,
        split_level=False,
        rooms=[room],
        scan_rooms_found=1,
        scan_rooms_transformed=1,
    )


def make_two_story_flat_model() -> BuildingModel:
    floor0 = [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [4.0, 0.0, 4.0], [0.0, 0.0, 4.0]]
    floor1 = [[0.0, 3.1, 0.0], [4.0, 3.1, 0.0], [4.0, 3.1, 4.0], [0.0, 3.1, 4.0]]
    lower_wall = _wall("lower-wall", [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [4.0, 3.0, 0.0], [0.0, 3.0, 0.0]])
    top_wall = _wall("top-wall", [[0.0, 3.1, 0.0], [4.0, 3.1, 0.0], [4.0, 3.4, 0.0], [0.0, 3.4, 0.0]])
    rooms = [
        ExtractedRoom(
            index=0,
            story=0,
            floor_polygon=floor0,
            walls_merged=[lower_wall],
            walls_computed=[lower_wall],
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
        ),
        ExtractedRoom(
            index=1,
            story=1,
            floor_polygon=floor1,
            walls_merged=[top_wall],
            walls_computed=[top_wall],
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
        ),
    ]
    return BuildingModel("synthetic-flat", None, 2, False, rooms, 2, 2)


def make_simple_slant_model() -> BuildingModel:
    floor = [[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [3.0, 0.0, 3.0], [0.0, 0.0, 3.0]]
    wall = _wall("plain-wall", [[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [3.0, 2.4, 0.0], [0.0, 2.4, 0.0]])
    raw = RawCeilingPlane(
        corners=[
            [0.0, 2.0, 0.0],
            [3.0, 2.8, 0.0],
            [3.0, 2.8, 3.0],
            [0.0, 2.0, 3.0],
        ]
    )
    room = ExtractedRoom(
        index=0,
        story=0,
        floor_polygon=floor,
        walls_merged=[wall],
        walls_computed=[wall],
        doors=[],
        windows=[],
        openings=[],
        storages=[],
        raw_ceiling_planes=[raw],
        raw_ceiling_source="test",
        ceiling_polygon=[],
        ceiling_type=None,
        ceiling_eave_height=None,
        ceiling_ridge_height=None,
    )
    return BuildingModel("synthetic-simple-slant", None, 1, False, [room], 1, 1)
