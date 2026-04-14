from __future__ import annotations

import pytest

from reconcile.element_locator import find_element, parse_element_id


def _sample_buildings() -> list[dict]:
    return [
        {
            "uuid": "11111111-2222-3333-4444-555555555555",
            "address": "Testvej 1",
            "rooms": [
                {
                    "story": 0,
                    "floor_polygon": [[0, 0, 0], [1, 0, 0], [1, 0, 1]],
                    "floor_overlap_region": [[0, 0, 0], [0.5, 0, 0], [0.5, 0, 0.5]],
                    "walls_merged": [
                        {
                            "id": "wm-1",
                            "source": "merged",
                            "corners": [[0, 0, 0], [1, 0, 0], [1, 1, 0]],
                        }
                    ],
                    "walls_computed": [
                        {
                            "id": "wc-1",
                            "source": "scan-room",
                            "corners": [[0, 0, 0], [1, 0, 0], [1, 1, 0]],
                        }
                    ],
                    "doors": [
                        {
                            "id": "door-1",
                            "source": "scan-room",
                            "corners": [[0, 0, 0], [0.5, 0, 0], [0.5, 1, 0]],
                        }
                    ],
                    "windows": [],
                }
            ],
            "cross_floor_gaps": [
                {
                    "id": "cg-1",
                    "type": "cross_story",
                    "confidence": "high",
                    "corners": [[0, 0, 0], [1, 0, 0], [1, 0.1, 0]],
                }
            ],
            "stitch_walls": [
                {
                    "id": "sw-1",
                    "story": 0,
                    "corners": [[0, 0, 0], [1, 0, 0], [1, 1, 0]],
                }
            ],
            "gap_walls": [
                {
                    "id": "gw-1",
                    "type": "gap_wall",
                    "corners": [[0, 0, 0], [1, 0, 0], [1, 1, 0]],
                }
            ],
            "exterior_gap_indicators": [
                {
                    "id": "eg-1",
                    "element_corners": [[0, 0, 0], [0.5, 0, 0], [0.5, 1, 0]],
                    "wall_corners": [[0, 0, 0], [1, 0, 0], [1, 1, 0]],
                }
            ],
            "gap_closures": [
                {
                    "id": "gc-1",
                    "type": "side",
                    "corners": [[0, 0, 0], [1, 0, 0], [1, 1, 0]],
                }
            ],
            "roof_surfaces": {
                "oblique": [
                    {
                        "corners": [[0, 2, 0], [2, 3, 0], [2, 3, 2], [0, 2, 2]],
                        "dominant_story": 1,
                        "cluster": {"avgAzimuth": 180, "avgIncl": 30},
                    }
                ],
                "flat": [
                    {
                        "corners": [[0, 3, 0], [2, 3, 0], [2, 3, 2], [0, 3, 2]],
                        "kind": "flat",
                        "story": 1,
                        "y": 3.0,
                    }
                ],
            },
            "ceiling": {
                "flat": [{"poly": [[0, 2.5, 0], [2, 2.5, 0], [2, 2.5, 2]], "story": 0}],
                "oblique": [
                    {
                        "poly": [[0, 2, 0], [1, 3, 0], [1, 3, 1]],
                        "kind": "clipped",
                        "story": 1,
                        "plane_index": 0,
                    }
                ],
                "simple_slant": [
                    {"poly": [[0, 2, 0], [1, 2.5, 0], [1, 2.5, 1]], "story": 0}
                ],
            },
        }
    ]


def test_parse_element_id_valid_expected():
    parsed = parse_element_id("11111111-2222-3333-4444-555555555555::door::door-1")
    assert parsed.building_uuid == "11111111-2222-3333-4444-555555555555"
    assert parsed.kind == "door"
    assert parsed.element_id == "door-1"


def test_parse_element_id_invalid_format_raises():
    with pytest.raises(ValueError):
        parse_element_id("bad-format")


def test_find_element_room_surface_expected_details():
    result = find_element(
        _sample_buildings(),
        "11111111-2222-3333-4444-555555555555::wall-computed::wc-1",
    )
    assert result["json_path"] == "rooms[0].walls_computed[0]"
    assert result["story"] == 0
    assert result["source"] == "scan-room"


def test_find_element_gap_collection_expected_details():
    result = find_element(
        _sample_buildings(),
        "11111111-2222-3333-4444-555555555555::gap-cross-story::cg-1",
    )
    assert result["json_path"] == "cross_floor_gaps[0]"
    assert result["kind"] == "gap-cross-story"


def test_find_element_floor_locator_expected_details():
    result = find_element(
        _sample_buildings(),
        "11111111-2222-3333-4444-555555555555::floor::0:0",
    )
    assert result["json_path"] == "rooms[0].floor_polygon"
    assert result["corners_count"] == 3


def test_find_element_roof_oblique():
    result = find_element(
        _sample_buildings(),
        "11111111-2222-3333-4444-555555555555::roof-oblique::oblique:0",
    )
    assert result["json_path"] == "roof_surfaces.oblique[0]"
    assert result["corners_count"] == 4
    assert result["story"] == 1


def test_find_element_roof_flat():
    result = find_element(
        _sample_buildings(),
        "11111111-2222-3333-4444-555555555555::roof-flat::flat:0",
    )
    assert result["json_path"] == "roof_surfaces.flat[0]"
    assert result["corners_count"] == 4


def test_find_element_ceiling_flat():
    result = find_element(
        _sample_buildings(),
        "11111111-2222-3333-4444-555555555555::ceiling-flat::ceiling-flat:0",
    )
    assert result["json_path"] == "ceiling.flat[0]"
    assert result["corners_count"] == 3



def test_find_element_ceiling_simple_slant():
    result = find_element(
        _sample_buildings(),
        "11111111-2222-3333-4444-555555555555::ceiling-simple-slant::ceiling-slant:0",
    )
    assert result["json_path"] == "ceiling.simple_slant[0]"
    assert result["corners_count"] == 3


def test_find_element_roof_invalid_index_raises():
    with pytest.raises(LookupError):
        find_element(
            _sample_buildings(),
            "11111111-2222-3333-4444-555555555555::roof-oblique::oblique:99",
        )


def test_find_element_missing_id_raises():
    with pytest.raises(LookupError):
        find_element(
            _sample_buildings(),
            "11111111-2222-3333-4444-555555555555::door::nope",
        )
