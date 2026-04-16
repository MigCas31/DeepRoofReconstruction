from __future__ import annotations

from reconcile.roof_algorithms_py.ceiling_plane_generation import collect_room_top_boundary_records
from reconcile.roof_algorithms_py.roof_cell_complex import build_roof_cell_complex
from reconcile.roof_algorithms_py.roof_coverage_graph import build_roof_coverage_graph
from reconcile.roof_algorithms_py.roof_evidence_graph import build_roof_evidence_graph
from reconcile.roof_algorithms_py.top_boundary_graph import build_top_boundary_graph


def _rect(x0: float, z0: float, x1: float, z1: float, y: float = 0.0) -> list[list[float]]:
    return [
        [x0, y, z0],
        [x1, y, z0],
        [x1, y, z1],
        [x0, y, z1],
    ]


def test_top_boundary_graph_uses_exact_attic_cell_for_flat_cap_in_sloped_part() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.1,
            "wallTopMin": 2.0,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "roof_hypothesis_id": "roof-hypothesis:flat:0",
                    "flat_role": "ambiguous_flat_over_sloped_part",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.0),
                    "area_m2": 12.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [
            {
                "id": "part:0",
                "type": "BuildingPart",
                "roof_family_guess": "gable_or_multi_slope",
                "max_room_slant_delta_m": 1.1,
            }
        ],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:oblique:0": ["part:0"]},
    }
    roof_coverage_graph = build_roof_coverage_graph(
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 3.2, 0.0],
                    [4.0, 3.2, 0.0],
                    [4.0, 4.0, 4.0],
                    [0.0, 4.0, 4.0],
                ],
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
    )
    roof_cell_complex = build_roof_cell_complex(
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "kind": "oblique",
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 3.2, 0.0],
                    [4.0, 3.2, 0.0],
                    [4.0, 4.0, 4.0],
                    [0.0, 4.0, 4.0],
                ],
                "cluster": {"avgAzimuth": 0.0, "avgIncl": 20.0},
                "center": {"x": 2.0, "y": 3.6, "z": 2.0},
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
    )

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
        roof_cell_complex=roof_cell_complex,
    )

    room_summary = top_boundary["room_summaries"]["room:0"]
    atom_node = next(node for node in top_boundary["nodes"] if node.get("type") == "TopBoundaryAtom")
    cell_node = next(node for node in top_boundary["nodes"] if node.get("type") == "Cell")

    assert atom_node["role"] == "attic_floor"
    assert room_summary["has_attic_relation"] is True
    assert cell_node["cell_kind"] == "attic"
    assert top_boundary["metadata"]["exact_attic_cell_count"] == 1


def test_top_boundary_graph_marks_flat_transition_cap_inside_mixed_room() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.0,
            "wallTopMin": 2.5,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": True,
            "partitions": [
                {
                    "id": "atom:oblique:0",
                    "room_index": 0,
                    "story": 0,
                    "kind": "oblique",
                    "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                    "poly": [
                        [0.0, 2.7, 0.0],
                        [2.0, 2.7, 0.0],
                        [2.0, 3.2, 4.0],
                        [0.0, 3.2, 4.0],
                    ],
                    "area_m2": 8.0,
                },
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "roof_hypothesis_id": "roof-hypothesis:flat:0",
                    "poly": _rect(2.0, 0.0, 4.0, 4.0, y=2.5),
                    "area_m2": 4.0,
                },
            ],
        }
    ]
    building_part_graph = {
        "nodes": [
            {
                "id": "part:0",
                "type": "BuildingPart",
                "roof_family_guess": "gable_or_multi_slope",
                "max_room_slant_delta_m": 0.5,
            }
        ],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:oblique:0": ["part:0"]},
    }
    roof_coverage_graph = build_roof_coverage_graph(
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 2.8, 0.0],
                    [4.0, 2.8, 0.0],
                    [4.0, 3.8, 4.0],
                    [0.0, 3.8, 4.0],
                ],
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
    )
    roof_cell_complex = build_roof_cell_complex(
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "kind": "oblique",
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 2.8, 0.0],
                    [4.0, 2.8, 0.0],
                    [4.0, 3.8, 4.0],
                    [0.0, 3.8, 4.0],
                ],
                "cluster": {"avgAzimuth": 0.0, "avgIncl": 20.0},
                "center": {"x": 2.0, "y": 3.3, "z": 2.0},
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
    )

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
        roof_cell_complex=roof_cell_complex,
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:0")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "flat_transition_cap"
    assert room_summary["has_attic_relation"] is False
    assert "sloped_ceiling" in room_summary["roles"]
    assert top_boundary["metadata"]["exact_upper_void_cell_count"] == 1


def test_top_boundary_graph_uses_partial_sloped_coverage_before_attic_inference() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.3,
            "wallTopMin": 2.0,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.4),
                    "area_m2": 16.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [{"id": "part:0", "type": "BuildingPart", "roof_family_guess": "gable_or_multi_slope"}],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:oblique:0": ["part:0"]},
    }
    roof_coverage_graph = build_roof_coverage_graph(
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 2.0, 0.0],
                    [4.0, 2.0, 0.0],
                    [4.0, 2.1, 4.0],
                    [0.0, 2.1, 4.0],
                ],
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
    )

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
        roof_cell_complex={"cells": [], "edges": []},
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:0")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "attic_floor_candidate"
    assert flat_atom["sloped_coverage_state"] == "partial"
    assert room_summary["partially_covered_by_sloped_roof"] is True
    assert room_summary["has_candidate_attic_relation"] is True


def test_top_boundary_graph_keeps_unsupported_ceiling_cap_as_flat_ceiling_without_sloped_context() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 2.8,
            "wallTopMin": 2.8,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": True,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "roof_hypothesis_id": "roof-hypothesis:flat:0",
                    "flat_role": "ceiling_cap",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.8),
                    "area_m2": 16.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [{"id": "part:0", "type": "BuildingPart", "roof_family_guess": "gable_or_multi_slope"}],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {},
    }

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph={"atom_coverage": {}, "room_subpart_membership": {}, "atom_subpart_membership": {}},
        roof_cell_complex={"cells": [], "edges": []},
        roof_evidence_graph={"atom_evidence": {}, "room_evidence": {}},
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:0")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "flat_ceiling"
    assert room_summary["has_candidate_attic_relation"] is False
    assert room_summary["has_resolved_roof_relation"] is False


def test_top_boundary_graph_promotes_selected_flat_hypothesis_without_sloped_context_to_flat_ceiling() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 2.8,
            "wallTopMin": 2.1,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:selected",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "roof_hypothesis_id": "roof-hypothesis:flat:0",
                    "flat_role": "roof_flat",
                    "flat_role_reason": "selected_flat_hypothesis",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.3),
                    "area_m2": 16.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [{"id": "part:0", "type": "BuildingPart", "roof_family_guess": "gable_or_multi_slope"}],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:flat:0": ["part:0"]},
    }

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph={"atom_coverage": {}, "room_subpart_membership": {}, "atom_subpart_membership": {}},
        roof_cell_complex={"cells": [], "edges": []},
        roof_evidence_graph={"atom_evidence": {}, "room_evidence": {}},
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:selected")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "flat_ceiling"
    assert flat_atom["reason"] == "selected_flat_hypothesis_without_sloped_context"
    assert room_summary["has_candidate_attic_relation"] is False


def test_top_boundary_graph_keeps_ambiguous_flat_as_ceiling_when_room_part_is_not_sloped() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.4,
            "wallTopMin": 2.1,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:ambiguous",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "roof_hypothesis_id": "roof-hypothesis:flat:0",
                    "flat_role": "ambiguous_flat_over_sloped_part",
                    "flat_role_reason": "flat_hypothesis_spans_sloped_building_part",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.3),
                    "area_m2": 16.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [{"id": "part:0", "type": "BuildingPart", "roof_family_guess": "flat_or_capped"}],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:flat:0": ["part:0"]},
    }

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph={"atom_coverage": {}, "room_subpart_membership": {}, "atom_subpart_membership": {}},
        roof_cell_complex={"cells": [], "edges": []},
        roof_evidence_graph={"atom_evidence": {}, "room_evidence": {}},
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:ambiguous")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "flat_ceiling"
    assert flat_atom["reason"] == "ambiguous_flat_without_local_sloped_support"
    assert room_summary["has_candidate_attic_relation"] is False


def test_top_boundary_graph_keeps_ambiguous_flat_as_ceiling_without_local_support_even_if_room_has_gabled_membership() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.4,
            "wallTopMin": 1.0,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:ambiguous",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "roof_hypothesis_id": "roof-hypothesis:flat:0",
                    "flat_role": "ambiguous_flat_over_sloped_part",
                    "flat_role_reason": "flat_hypothesis_spans_sloped_building_part",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.3),
                    "area_m2": 16.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [
            {"id": "part:gable", "type": "BuildingPart", "roof_family_guess": "gable_or_multi_slope"},
            {"id": "part:flat", "type": "BuildingPart", "roof_family_guess": "flat_or_capped"},
        ],
        "room_membership": {"room:0": ["part:gable", "part:flat"]},
        "hypothesis_membership": {"roof-hypothesis:flat:0": ["part:flat"]},
    }

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph={"atom_coverage": {}, "room_subpart_membership": {}, "atom_subpart_membership": {}},
        roof_cell_complex={"cells": [], "edges": []},
        roof_evidence_graph={"atom_evidence": {}, "room_evidence": {}},
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:ambiguous")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "flat_ceiling"
    assert flat_atom["reason"] == "ambiguous_flat_without_local_sloped_support"
    assert room_summary["has_candidate_attic_relation"] is False


def test_top_boundary_graph_infers_flat_transition_cap_for_strong_upper_void_room_in_sloped_part() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.4,
            "wallTopMin": 2.5,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": True,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "roof_hypothesis_id": "roof-hypothesis:flat:0",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.6),
                    "area_m2": 16.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [{"id": "part:0", "type": "BuildingPart", "roof_family_guess": "gable_or_multi_slope"}],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {},
    }
    roof_evidence_graph = {
        "atom_evidence": {
            "atom:flat:0": {
                "atom_id": "atom:flat:0",
                "room_id": "room:0",
                "room_index": 0,
                "kind": "flat",
                "sloped_context": False,
                "flat_cap_under_slope": False,
                "upper_void_cell_count": 0,
                "attic_cell_count": 0,
            }
        },
        "room_evidence": {
            "room:0": {
                "room_id": "room:0",
                "room_index": 0,
                "strong_upper_void_context": True,
                "strong_attic_context": False,
                "strong_perimeter_sloped": True,
                "strong_knee_wall_signal": True,
                "evidence_score": 8,
            }
        },
    }

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph={"atom_coverage": {}, "room_subpart_membership": {}, "atom_subpart_membership": {}},
        roof_cell_complex={"cells": [], "edges": []},
        roof_evidence_graph=roof_evidence_graph,
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:0")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "flat_transition_cap_inferred"
    assert flat_atom["reason"] == "strong_upper_void_room_in_sloped_part"
    assert room_summary["has_candidate_attic_relation"] is False
    assert room_summary["has_inferred_upper_void_relation"] is True


def test_collect_room_top_boundary_records_uses_original_floor_polygon_when_floor_polygon_is_empty() -> None:
    building = {
        "rooms": [
            {
                "story": 1,
                "floor_polygon": [],
                "floor_polygon_original": _rect(0.0, 0.0, 2.0, 2.0, y=1.0),
                "walls_computed": [
                    {"corners": [[0.0, 1.0, 0.0], [2.0, 1.0, 0.0], [2.0, 2.8, 0.0], [0.0, 2.8, 0.0]]},
                    {"corners": [[2.0, 1.0, 0.0], [2.0, 1.0, 2.0], [2.0, 2.8, 2.0], [2.0, 2.8, 0.0]]},
                ],
            }
        ]
    }

    records = collect_room_top_boundary_records(
        building,
        has_floor_above=lambda _x, _z, _story: False,
        graph=None,
    )

    assert len(records) == 1
    assert records[0]["room_index"] == 0
    assert records[0]["fp"] == _rect(0.0, 0.0, 2.0, 2.0, y=1.0)
    assert records[0]["floorY"] == 1.0


def test_top_boundary_graph_infers_attic_for_flat_cap_under_slope_without_upper_void_context() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.0,
            "wallTopMin": 2.4,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "roof_hypothesis_id": "roof-hypothesis:flat:0",
                    "flat_role": "ceiling_cap",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.4),
                    "area_m2": 16.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [{"id": "part:0", "type": "BuildingPart", "roof_family_guess": "gable_or_multi_slope"}],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:oblique:0": ["part:0"]},
    }
    roof_coverage_graph = build_roof_coverage_graph(
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 3.0, 0.0],
                    [4.0, 3.0, 0.0],
                    [4.0, 3.8, 4.0],
                    [0.0, 3.8, 4.0],
                ],
                "cluster": {"avgAzimuth": 0.0},
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
    )
    roof_evidence_graph = build_roof_evidence_graph(
        exposed_rooms=exposed_rooms,
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 3.0, 0.0],
                    [4.0, 3.0, 0.0],
                    [4.0, 3.8, 4.0],
                    [0.0, 3.8, 4.0],
                ],
                "cluster": {"avgAzimuth": 0.0},
            }
        ],
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
        roof_cell_complex={"cells": [], "knee_walls": []},
    )

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
        roof_cell_complex={"cells": [], "edges": []},
        roof_evidence_graph=roof_evidence_graph,
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:0")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "attic_floor_inferred"
    assert room_summary["has_inferred_attic_relation"] is True
    assert room_summary["has_resolved_roof_relation"] is True


def test_top_boundary_graph_infers_upper_void_from_evidence_without_exact_cell() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.3,
            "wallTopMin": 2.0,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.4),
                    "area_m2": 16.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [{"id": "part:0", "type": "BuildingPart", "roof_family_guess": "mixed_or_partial"}],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:oblique:0": ["part:0"]},
    }
    roof_coverage_graph = build_roof_coverage_graph(
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 2.0, 0.0],
                    [4.0, 2.0, 0.0],
                    [4.0, 2.1, 4.0],
                    [0.0, 2.1, 4.0],
                ],
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
    )
    roof_cell_complex = {
        "cells": [],
        "edges": [],
        "knee_walls": [
            {
                "room_index": 0,
                "corners": [
                    [0.0, 2.4, 0.0],
                    [2.0, 2.4, 0.0],
                    [2.0, 2.8, 0.0],
                    [0.0, 2.8, 0.0],
                ],
            }
        ],
    }
    roof_evidence_graph = build_roof_evidence_graph(
        exposed_rooms=exposed_rooms,
        room_partitions=room_partitions,
        selected_oblique_surfaces=[{"roof_hypothesis_id": "roof-hypothesis:oblique:0", "cluster": {"avgAzimuth": 0.0}}],
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
        roof_cell_complex=roof_cell_complex,
    )

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
        roof_cell_complex=roof_cell_complex,
        roof_evidence_graph=roof_evidence_graph,
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:0")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "flat_transition_cap_inferred"
    assert room_summary["has_upper_void_relation"] is True
    assert room_summary["has_resolved_roof_relation"] is True


def test_top_boundary_graph_infers_attic_from_gable_evidence_without_exact_cell() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.4,
            "wallTopMin": 2.0,
        }
    ]
    room_partitions = [
        {
            "room_index": 0,
            "story": 0,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 0,
                    "kind": "flat",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, y=2.4),
                    "area_m2": 16.0,
                }
            ],
        }
    ]
    building_part_graph = {
        "nodes": [{"id": "part:0", "type": "BuildingPart", "roof_family_guess": "gable_or_multi_slope"}],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:oblique:0": ["part:0"]},
    }
    roof_coverage_graph = {
        "atom_coverage": {
            "atom:flat:0": {
                "sloped_state": "partial",
                "sloped_overlap_ratio": 1.0,
                "sloped_vertical_clearance_m": -0.1,
                "sloped_hypothesis_id": "roof-hypothesis:oblique:0",
            }
        },
        "atom_subpart_membership": {"atom:flat:0": ["subpart:gable:0"]},
        "room_subpart_membership": {"room:0": ["subpart:gable:0"]},
        "subparts": [
            {
                "id": "subpart:gable:0",
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "room_indices": [0],
                "part_ids": ["part:0"],
                "semantic_kind": "gable_run",
            }
        ],
    }
    roof_evidence_graph = build_roof_evidence_graph(
        exposed_rooms=exposed_rooms,
        room_partitions=room_partitions,
        selected_oblique_surfaces=[{"roof_hypothesis_id": "roof-hypothesis:oblique:0", "cluster": {"avgAzimuth": 0.0}}],
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
        roof_cell_complex={"cells": [], "knee_walls": []},
    )

    top_boundary = build_top_boundary_graph(
        room_records=exposed_rooms,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
        roof_cell_complex={"cells": [], "edges": []},
        roof_evidence_graph=roof_evidence_graph,
    )

    flat_atom = next(node for node in top_boundary["nodes"] if node.get("id") == "atom:flat:0")
    room_summary = top_boundary["room_summaries"]["room:0"]

    assert flat_atom["role"] == "attic_floor_inferred"
    assert room_summary["has_attic_relation"] is True
    assert room_summary["has_resolved_roof_relation"] is True
