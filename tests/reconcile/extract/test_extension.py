from reconcile_tiers.extract.building import ExtractedRoom, ExtractedWall
from reconcile_tiers.extract.extension import extend_walls_to_slabs


def _wall(wall_id, top_y=2.40):
    return ExtractedWall(
        id=wall_id,
        source="synthetic",
        corners=[
            [0.0, top_y, 0.0],
            [1.0, top_y, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ],
    )


def _room(index, story, floor_y, floor_x0=0.0, floor_x1=1.0, wall=None):
    return ExtractedRoom(
        index=index,
        story=story,
        floor_polygon=[
            [floor_x0, floor_y, -0.5],
            [floor_x1, floor_y, -0.5],
            [floor_x1, floor_y, 0.5],
            [floor_x0, floor_y, 0.5],
        ],
        walls_merged=[],
        walls_computed=[] if wall is None else [wall],
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


def test_extend_walls_to_slabs_adds_strip_for_stacked_upper_floor():
    lower = _room(0, 0, 0.0, wall=_wall("w0", top_y=2.40))
    upper = _room(1, 1, 2.70)

    extended = extend_walls_to_slabs([lower, upper])

    strip = extended[0].walls_computed[0].extension_strip
    assert strip == [
        [
            [0.0, 2.40, 0.0],
            [1.0, 2.40, 0.0],
            [1.0, 2.70, 0.0],
            [0.0, 2.70, 0.0],
        ]
    ]


def test_extend_walls_to_slabs_skips_unstacked_or_too_distant_slabs():
    unstacked = [_room(0, 0, 0.0, wall=_wall("w0", top_y=2.40)), _room(1, 1, 2.70, 3.0, 4.0)]
    too_high = [_room(0, 0, 0.0, wall=_wall("w1", top_y=2.40)), _room(1, 1, 3.30)]

    assert extend_walls_to_slabs(unstacked)[0].walls_computed[0].extension_strip is None
    assert extend_walls_to_slabs(too_high)[0].walls_computed[0].extension_strip is None
