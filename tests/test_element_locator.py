from __future__ import annotations

import pytest

from reconcile.element_locator import (
    build_trace,
    find_element,
    is_ontology_kind,
    parse_element_id,
)


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


def test_find_element_wall_computed_full_model_suffix():
    # Full-model viewer appends :<story>:<room_index> to wall IDs (viewer-main.js:1924).
    result = find_element(
        _sample_buildings(),
        "11111111-2222-3333-4444-555555555555::wall-computed::wc-1:0:0",
    )
    assert result["json_path"] == "rooms[0].walls_computed[0]"
    assert result["story"] == 0


def test_find_element_wall_computed_suffix_story_mismatch_raises():
    # story hint 1 doesn't match the room's story 0 — should not resolve.
    with pytest.raises(LookupError):
        find_element(
            _sample_buildings(),
            "11111111-2222-3333-4444-555555555555::wall-computed::wc-1:1:0",
        )


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


def _sample_roof_results() -> dict:
    uuid = "11111111-2222-3333-4444-555555555555"
    return {
        uuid: {
            "ceiling_partitions": {
                "oblique": [
                    {
                        "id": "ceiling-partition:abc123abc123abc123ab",
                        "room_index": 2,
                        "story": 1,
                        "kind": "oblique",
                        "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                        "poly": [[0, 0, 0], [1, 0, 0], [1, 0, 1]],
                        "area_m2": 0.5,
                    }
                ],
                "flat": [
                    {
                        "id": "ceiling-partition:ff1122ff1122ff1122ff",
                        "room_index": 3,
                        "story": 1,
                        "kind": "flat",
                        "flat_role": "roof_flat",
                        "roof_hypothesis_id": "roof-hypothesis:flat:0",
                        "poly": [[0, 3.3, 0], [2, 3.3, 0], [2, 3.3, 2], [0, 3.3, 2]],
                        "area_m2": 4.0,
                        "top_y_m": 3.3,
                    }
                ],
                "room_partitions": [
                    {
                        "room_index": 2,
                        "story": 1,
                        "partitions": [
                            {
                                "id": "ceiling-partition:abc123abc123abc123ab",
                                "kind": "oblique",
                            }
                        ],
                    }
                ],
            },
            "knee_walls": [
                {
                    "id": "knee-wall:deadbeefcafebabe1234",
                    "room_index": 2,
                    "height_m": 0.6,
                    "corners": [[0, 0, 0], [1, 0, 0], [1, 0.6, 0], [0, 0.6, 0]],
                }
            ],
            "roof_evidence_graph": {
                "atom_evidence": {
                    "ceiling-partition:abc123abc123abc123ab": {
                        "atom_id": "ceiling-partition:abc123abc123abc123ab",
                        "semantic_kinds": ["gable_run"],
                        "subpart_ids": ["coverage-subpart:xyz"],
                    }
                }
            },
            "top_boundary_graph": {
                "nodes": [
                    {"id": "ceiling-partition:abc123abc123abc123ab"},
                ]
            },
            "roof_cell_complex": {
                "cells": [
                    {
                        "id": "roof-cell:attic:c0b7aeb9a909c05ebd10",
                        "type": "Cell",
                        "cell_kind": "attic",
                        "story": 0,
                        "room_id": "room:10",
                        "room_index": 10,
                        "part_id": "building-part:abc",
                        "base_atom_id": "ceiling-partition:ff1122ff1122ff1122ff",
                        "roof_hypothesis_id": "roof-hypothesis:oblique:1",
                        "roof_surface_kind": "oblique",
                        "volume_m3": 11.1,
                        "bbox_xyz": [0.5, 3.5, -3.8, 5.2, 6.7, 0.7],
                        "faces": [
                            {
                                "id": "arr-face:bottomslab0000000000",
                                "kind": "bottom",
                                "role": "slab",
                                "source_kind": "bottom_cap",
                                "corners": [
                                    [0, 3.5, 0], [5, 3.5, 0], [5, 3.5, 4], [0, 3.5, 4]
                                ],
                            },
                            {
                                "id": "arr-face:5b790a478078551d5568",
                                "kind": "top",
                                "role": "roof",
                                "source_kind": "oblique",
                                "corners": [
                                    [1.9, 6.7, 0.7],
                                    [0.5, 6.7, -2.2],
                                    [3.9, 4.0, -3.8],
                                    [5.2, 4.1, -0.9],
                                ],
                                "area_m2": 14.4,
                                "metadata": {
                                    "face_kind": "top",
                                    "roof_hypothesis_id": "roof-hypothesis:oblique:1",
                                },
                            },
                        ],
                    }
                ],
                "edges": [],
                "knee_walls": [],
                "metadata": {},
            },
        }
    }


def test_is_ontology_kind():
    assert is_ontology_kind("ontology-renderable-ceiling")
    assert is_ontology_kind("ontology-base-exterior-wall")
    assert is_ontology_kind("ontology-knee-wall")
    assert not is_ontology_kind("ceiling-flat")
    assert not is_ontology_kind("wall-merged")


def test_find_ontology_renderable_ceiling_atom():
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-ceiling"
        "::renderable:room_ceiling_sloped:ceiling-partition:abc123abc123abc123ab"
    )
    result = find_element([], token, roof_results=_sample_roof_results())
    assert result["kind"] == "ontology-renderable-ceiling"
    assert result["category"] == "room_ceiling_sloped"
    assert result["source_id"] == "ceiling-partition:abc123abc123abc123ab"
    assert result["atom"]["room_index"] == 2
    assert result["atom"]["kind"] == "oblique"
    assert "ceiling_partitions.oblique[0]" in result["provenance_paths"]
    assert (
        "ceiling_partitions.room_partitions[0].partitions[0]"
        in result["provenance_paths"]
    )
    assert result["evidence"]["semantic_kinds"] == ["gable_run"]


def test_find_ontology_knee_wall_atom():
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-knee-wall"
        "::renderable:knee_wall:knee-wall:deadbeefcafebabe1234"
    )
    result = find_element([], token, roof_results=_sample_roof_results())
    assert result["source_id"] == "knee-wall:deadbeefcafebabe1234"
    assert result["atom"]["height_m"] == 0.6
    assert "knee_walls[0]" in result["provenance_paths"]


def test_find_ontology_missing_source_raises():
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-ceiling"
        "::renderable:room_ceiling_sloped:ceiling-partition:does_not_exist"
    )
    with pytest.raises(LookupError):
        find_element([], token, roof_results=_sample_roof_results())


def test_find_ontology_missing_roof_results_raises():
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-ceiling"
        "::renderable:room_ceiling_sloped:ceiling-partition:abc"
    )
    with pytest.raises(LookupError):
        find_element([], token)


def test_find_ontology_bad_renderable_format_raises():
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-ceiling"
        "::not_a_renderable_id"
    )
    with pytest.raises(LookupError):
        find_element([], token, roof_results=_sample_roof_results())


def test_find_ontology_roof_atom_patch_flat():
    """roof-atom-patch:flat: prefix is stripped; underlying atom resolves."""
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-roof"
        "::renderable:exterior_roof:roof-atom-patch:flat:ceiling-partition:ff1122ff1122ff1122ff"
    )
    result = find_element([], token, roof_results=_sample_roof_results())
    assert result["kind"] == "ontology-renderable-roof"
    assert result["category"] == "exterior_roof"
    assert result["source_id"] == "roof-atom-patch:flat:ceiling-partition:ff1122ff1122ff1122ff"
    assert result["atom"]["id"] == "ceiling-partition:ff1122ff1122ff1122ff"
    assert result["atom"]["flat_role"] == "roof_flat"
    assert "ceiling_partitions.flat[0]" in result["provenance_paths"]


def test_find_ontology_roof_atom_patch_trace_points_at_roof_partitioning():
    """build_trace resolves pipeline_step to roof_partitioning.py, not viewer_server."""
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-roof"
        "::renderable:exterior_roof:roof-atom-patch:flat:ceiling-partition:ff1122ff1122ff1122ff"
    )
    result = find_element([], token, roof_results=_sample_roof_results())
    traced = build_trace(result)
    assert traced["pipeline_step"]["file"].endswith("roof_partitioning.py")


def test_find_ontology_roof_cell_face_composite():
    """Resolves <cell_id>:arr-face:<face_hash> to the face dict and parent cell."""
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-roof"
        "::renderable:exterior_roof:roof-cell:attic:c0b7aeb9a909c05ebd10:arr-face:5b790a478078551d5568"
    )
    result = find_element([], token, roof_results=_sample_roof_results())
    assert result["source_id"] == (
        "roof-cell:attic:c0b7aeb9a909c05ebd10:arr-face:5b790a478078551d5568"
    )
    assert result["atom"]["id"] == "arr-face:5b790a478078551d5568"
    assert result["atom"]["role"] == "roof"
    assert result["atom"]["source_kind"] == "oblique"
    assert "roof_cell_complex.cells[0].faces[1]" in result["provenance_paths"]
    parent = result["parent_cell"]
    assert parent["id"] == "roof-cell:attic:c0b7aeb9a909c05ebd10"
    assert parent["room_index"] == 10
    assert parent["cell_kind"] == "attic"
    assert parent["roof_hypothesis_id"] == "roof-hypothesis:oblique:1"


def test_find_ontology_roof_cell_bare_resolves_to_cell():
    """Bare <cell_id> (no face suffix) resolves to the cell itself."""
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-roof"
        "::renderable:exterior_roof:roof-cell:attic:c0b7aeb9a909c05ebd10"
    )
    result = find_element([], token, roof_results=_sample_roof_results())
    assert result["atom"]["id"] == "roof-cell:attic:c0b7aeb9a909c05ebd10"
    assert result["atom"]["cell_kind"] == "attic"
    assert result["provenance_paths"] == ["roof_cell_complex.cells[0]"]
    assert result["parent_cell"]["room_index"] == 10


def test_find_ontology_roof_cell_face_missing_face_raises():
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-roof"
        "::renderable:exterior_roof:roof-cell:attic:c0b7aeb9a909c05ebd10:arr-face:deadbeefdeadbeefdead"
    )
    with pytest.raises(LookupError):
        find_element([], token, roof_results=_sample_roof_results())


def test_find_ontology_roof_cell_trace_points_at_roof_cell_complex():
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-roof"
        "::renderable:exterior_roof:roof-cell:attic:c0b7aeb9a909c05ebd10:arr-face:5b790a478078551d5568"
    )
    result = find_element([], token, roof_results=_sample_roof_results())
    traced = build_trace(result)
    assert traced["pipeline_step"]["file"].endswith("roof_cell_complex.py")


def test_build_trace_attaches_thresholds_and_step():
    token = (
        "11111111-2222-3333-4444-555555555555"
        "::ontology-renderable-ceiling"
        "::renderable:room_ceiling_sloped:ceiling-partition:abc123abc123abc123ab"
    )
    result = find_element([], token, roof_results=_sample_roof_results())
    traced = build_trace(result)
    assert traced["pipeline_step"]["file"].endswith("roof_partitioning.py")
    assert any(
        "ROOM_TOP_MIN_CLEARANCE_M" in t["note"] for t in traced["thresholds"]
    )
