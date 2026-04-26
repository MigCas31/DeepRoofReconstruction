import logging

from reconcile_tiers._core.newell import newell_normal
from reconcile_tiers.assemble.walls_to_rooms import assemble_rooms
from reconcile_tiers.extract.building import (
    BuildingModel,
    ExtractedElement,
    ExtractedRoom,
    ExtractedWall,
)


def _room(*, walls, doors=None, windows=None, floor=None):
    return ExtractedRoom(
        index=0,
        story=2,
        floor_polygon=floor or [[0, 0, 0], [2, 0, 0], [2, 0, 2], [0, 0, 2]],
        walls_merged=[],
        walls_computed=walls,
        doors=doors or [],
        windows=windows or [],
        openings=[],
        storages=[],
        raw_ceiling_planes=[],
        raw_ceiling_source=None,
        ceiling_polygon=[],
        ceiling_type=None,
        ceiling_eave_height=None,
        ceiling_ridge_height=None,
    )


def _model(room):
    return BuildingModel(
        uuid="uuid-1",
        address=None,
        stories_found=1,
        split_level=False,
        rooms=[room],
        scan_rooms_found=0,
        scan_rooms_transformed=0,
    )


def test_assemble_rooms_orients_floor_up_and_walls_away_from_room_centroid():
    wall = ExtractedWall(
        id="left",
        source="test",
        # This winds toward the room interior (+X) and must be reversed.
        corners=[[0, 0, 0], [0, 0, 2], [0, 2, 2], [0, 2, 0]],
    )

    rooms = assemble_rooms(_model(_room(walls=[wall])))

    room = rooms[0]
    assert room.story == 2
    assert room.locator_id == "uuid-1::tier-room::0"
    assert newell_normal([[c.x, c.y, c.z] for c in room.floor.corners])[1] > 0
    normal = newell_normal([[c.x, c.y, c.z] for c in room.walls[0].corners])
    wall_center = [
        sum(getattr(c, axis) for c in room.walls[0].corners) / len(room.walls[0].corners)
        for axis in ("x", "y", "z")
    ]
    room_center = [1.0, 0.0, 1.0]
    outward = [wall_center[idx] - room_center[idx] for idx in range(3)]
    assert sum(normal[idx] * outward[idx] for idx in range(3)) > 0


def test_assemble_rooms_precollects_only_valid_quad_cutouts(caplog):
    wall = ExtractedWall(
        id="left",
        source="test",
        corners=[[0, 0, 2], [0, 0, 0], [0, 2, 0], [0, 2, 2]],
    )
    door = ExtractedElement(
        id="door",
        source="test",
        corners=[[0, 0.2, 0.6], [0, 0.2, 1.0], [0, 1.4, 1.0], [0, 1.4, 0.6]],
    )
    window = ExtractedElement(
        id="window",
        source="test",
        corners=[[0, 0.8, 1.2], [0, 0.8, 1.6], [0, 1.4, 1.6], [0, 1.4, 1.2]],
    )
    edge_touching = ExtractedElement(
        id="edge",
        source="test",
        corners=[[0, 0.2, 0.0], [0, 0.2, 0.4], [0, 1.0, 0.4], [0, 1.0, 0.0]],
    )
    non_quad = ExtractedElement(
        id="triangle",
        source="test",
        corners=[[0, 0.2, 0.6], [0, 0.2, 1.0], [0, 1.4, 1.0]],
    )

    with caplog.at_level(logging.WARNING, logger="reconcile_tiers.assemble.walls_to_rooms"):
        rooms = assemble_rooms(
            _model(_room(walls=[wall], doors=[door, edge_touching, non_quad], windows=[window]))
        )

    room = rooms[0]
    assert len(room.doors) == 2
    assert len(room.windows) == 1
    assert "Skipping non-quad door opening" in caplog.text
    assert "id=triangle" in caplog.text
    assert "corner_count=3" in caplog.text
    cutouts = [
        [[corner.x, corner.y, corner.z] for corner in cutout.corners]
        for cutout in room.walls[0].cutouts
    ]
    assert cutouts == [window.corners, door.corners]
