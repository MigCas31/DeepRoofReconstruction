from collections import Counter
from pathlib import Path

from reconcile_tiers._core.newell import newell_normal
from reconcile_tiers.assemble.gaps_to_pieces import assemble_gap_pieces
from reconcile_tiers.extract.building import (
    BuildingModel,
    ExtractedGapWall,
    ExtractedStitchWall,
    GapClosure,
    extract_building_model,
)
from reconcile_tiers.payload.schema import GapKind, GapScope


def _model(gap_walls=None, stitch_walls=None):
    return BuildingModel(
        uuid="test",
        address=None,
        stories_found=1,
        split_level=False,
        rooms=[],
        scan_rooms_found=0,
        scan_rooms_transformed=0,
        gap_walls=gap_walls or [],
        stitch_walls=stitch_walls or [],
    )


def test_gap_floor_is_planarized_and_wound_upward():
    model = _model(
        gap_walls=[
            ExtractedGapWall(
                id="floor",
                type="gap_floor",
                story=0,
                confidence="high",
                corners=[[0, 0.0, 0], [0, 0.02, 1], [1, -0.01, 1], [1, 0.01, 0]],
            )
        ]
    )

    pieces = assemble_gap_pieces(model)

    assert pieces[0].kind == GapKind.GAP_FLOOR
    assert pieces[0].scope == GapScope.INTRA_STORY
    assert max(corner.y for corner in pieces[0].corners) - min(corner.y for corner in pieces[0].corners) < 1e-9
    assert newell_normal([[corner.x, corner.y, corner.z] for corner in pieces[0].corners])[1] > 0.0


def test_gap_ceiling_is_planarized_and_wound_upward():
    model = _model(
        gap_walls=[
            ExtractedGapWall(
                id="ceiling",
                type="gap_ceiling",
                story=0,
                confidence="high",
                corners=[[0, 3.0, 0], [1, 3.01, 0], [1, 2.99, 1], [0, 3.0, 1]],
            )
        ]
    )

    pieces = assemble_gap_pieces(model)

    assert pieces[0].kind == GapKind.GAP_CEILING
    assert newell_normal([[corner.x, corner.y, corner.z] for corner in pieces[0].corners])[1] > 0.0


def test_stitch_types_are_typed_junction_pieces_without_substring_dispatch():
    model = _model(
        stitch_walls=[
            ExtractedStitchWall(
                id="stitch",
                type="stitch",
                story=0,
                room_index=0,
                room_indices=[0, 1],
                corners=[[0, 0, 0], [1, 0, 0], [1, 2, 0], [0, 2, 0]],
            ),
            ExtractedStitchWall(
                id="stitch-ceiling",
                type="stitch_ceiling",
                story=0,
                room_index=0,
                room_indices=[0, 1],
                corners=[[0, 2, 0], [1, 2, 0], [0, 2, 1]],
            ),
        ]
    )

    pieces = assemble_gap_pieces(model)

    assert [piece.kind for piece in pieces] == [GapKind.STITCH, GapKind.STITCH_CEIL]
    assert all(piece.scope == GapScope.JUNCTION for piece in pieces)


def test_unknown_gap_stitch_and_exterior_types_are_not_substring_dispatched():
    model = BuildingModel(
        uuid="test",
        address=None,
        stories_found=1,
        split_level=False,
        rooms=[],
        scan_rooms_found=0,
        scan_rooms_transformed=0,
        gap_walls=[
            ExtractedGapWall(
                id="mystery-floor-name",
                type="mystery_floor",
                story=0,
                confidence="low",
                corners=[[0, 0, 0], [1, 0, 0], [1, 0, 1]],
            )
        ],
        stitch_walls=[
            ExtractedStitchWall(
                id="mystery-stitch",
                type="stitch_unknown",
                story=0,
                room_index=0,
                room_indices=[0, 1],
                corners=[[0, 0, 0], [1, 0, 0], [1, 1, 0]],
            )
        ],
        gap_closures=[
            GapClosure(
                type="floorish",
                story=0,
                indicator_element_id="door-a",
                indicator_wall_id="wall-b",
                corners=[[0, 0, 0], [1, 0, 0], [1, 0, 1]],
            )
        ],
    )

    assert assemble_gap_pieces(model) == []


def test_exterior_closures_are_typed_exterior_pieces():
    model = _model()
    model = BuildingModel(
        uuid=model.uuid,
        address=model.address,
        stories_found=model.stories_found,
        split_level=model.split_level,
        rooms=model.rooms,
        scan_rooms_found=model.scan_rooms_found,
        scan_rooms_transformed=model.scan_rooms_transformed,
        gap_closures=[
            GapClosure(
                type="side",
                story=0,
                indicator_element_id="door-a",
                indicator_wall_id="wall-b",
                corners=[[0, 0, 0], [1, 0, 0], [1, 2, 0], [0, 2, 0]],
            ),
            GapClosure(
                type="ceiling",
                story=0,
                indicator_element_id="door-a",
                indicator_wall_id="wall-b",
                corners=[[0, 2, 0], [1, 2.02, 0], [1, 1.99, 1], [0, 2, 1]],
            ),
        ],
    )

    pieces = assemble_gap_pieces(model)

    assert [piece.kind for piece in pieces] == [GapKind.EXTERIOR_SIDE, GapKind.EXTERIOR_CEIL]
    assert all(piece.scope == GapScope.EXTERIOR for piece in pieces)
    assert pieces[0].locator_id == "test::tier-gap::door-a:wall-b:side:0"
    assert newell_normal([[corner.x, corner.y, corner.z] for corner in pieces[1].corners])[1] > 0.0


def test_cohort_gap_piece_counts_include_gap_stitch_and_exterior_surfaces():
    expected = {
        "c72ad855-9e52-46f1-886d-a9f37911521f": {
            "exterior_ceiling": 3,
            "exterior_floor": 3,
            "exterior_side": 6,
            "gap_ceiling": 100,
            "gap_floor": 14,
            "side": 32,
            "stitch": 5,
            "stitch_ceiling": 1,
            "stitch_floor": 1,
        },
        "f40dcc9f-b97b-4bef-8b40-ba011aabf0bd": {
            "exterior_ceiling": 2,
            "exterior_floor": 2,
            "exterior_side": 4,
            "gap_ceiling": 115,
            "gap_floor": 15,
            "side": 42,
            "stitch": 8,
        },
        "2ea3b759-e047-424c-8034-f8ee5b811fb4": {
            "exterior_ceiling": 1,
            "exterior_floor": 1,
            "exterior_side": 2,
            "gap_ceiling": 99,
            "gap_floor": 19,
            "side": 41,
            "stitch": 9,
            "stitch_ceiling": 6,
            "stitch_floor": 6,
        },
    }

    for uuid, expected_counts in expected.items():
        model = extract_building_model(uuid, Path("pipeline-outputs"), Path(".scan-cache"))
        pieces = assemble_gap_pieces(model)

        assert Counter(piece.kind.value for piece in pieces) == expected_counts
