from __future__ import annotations

from shapely.geometry import Polygon

from reconcile.roof_algorithms_py.occupied_room_cell_complex import (
    _annotate_boundary_classes,
    build_occupied_room_cell_complex,
)
from reconcile.roof_algorithms_py.roof_cell_complex import _poly_xz_from_3d, build_roof_cell_complex
from reconcile.roof_algorithms_py.roof_coverage_graph import build_roof_coverage_graph


def _rect(x0: float, z0: float, x1: float, z1: float, y: float) -> list[list[float]]:
    return [
        [x0, y, z0],
        [x1, y, z0],
        [x1, y, z1],
        [x0, y, z1],
    ]


def test_poly_xz_from_3d_recovers_largest_polygon_from_make_valid_geometry_collection() -> None:
    corners = [
        [-3.1533, 0.0, 0.7598],
        [-3.1043, 0.0, 0.8281],
        [-3.0851, 0.0, 0.8547],
        [-3.0974, 0.0, 0.8636],
        [-0.7176, 0.0, 4.1630],
        [2.6241, 0.0, 1.7527],
        [0.2443, 0.0, -1.5467],
        [2.6069, 0.0, 1.7288],
        [2.6715, 0.0, 1.6823],
        [0.7014, 0.0, -1.0492],
        [3.1794, 0.0, -2.8365],
        [5.0732, 0.0, -0.2110],
        [3.1176, 0.0, -2.9223],
        [3.1211, 0.0, -2.9248],
        [3.1211, 0.0, -2.9248],
        [0.9251, 0.0, -1.3409],
        [0.7144, 0.0, -1.6331],
        [0.4328, 0.0, -1.4300],
        [-1.4658, 0.0, -4.0621],
        [-2.6269, 0.0, -3.2246],
        [-1.5467, 0.0, -4.0037],
        [0.1619, 0.0, -1.6349],
        [-1.5707, 0.0, -0.3851],
        [-3.2793, 0.0, -2.7540],
        [-3.3625, 0.0, -2.6940],
        [-3.3648, 0.0, -2.6973],
        [-4.8641, 0.0, -1.6191],
        [-3.3648, 0.0, -2.6973],
        [-2.6974, 0.0, -1.7691],
        [-1.6541, 0.0, -0.3183],
    ]

    poly = _poly_xz_from_3d(corners)

    assert poly is not None
    assert poly.is_valid
    assert poly.area > 18.0


def test_occupied_room_cell_complex_recovers_room_from_wall_bottom_footprint_when_floor_polygon_is_empty() -> None:
    bldg = {
        "rooms": [
            {
                "story": 0,
                "floor_polygon": [],
                "walls_computed": [
                    {"corners": [[0.0, -1.0, 0.0], [4.0, -1.0, 0.0], [4.0, 1.4, 0.0], [0.0, 1.4, 0.0]]},
                    {"corners": [[4.0, -1.0, 0.0], [4.0, -1.0, 3.0], [4.0, 1.4, 3.0], [4.0, 1.4, 0.0]]},
                    {"corners": [[4.0, -1.0, 3.0], [0.0, -1.0, 3.0], [0.0, 1.4, 3.0], [4.0, 1.4, 3.0]]},
                    {"corners": [[0.0, -1.0, 3.0], [0.0, -1.0, 0.0], [0.0, 1.4, 0.0], [0.0, 1.4, 3.0]]},
                ],
                "walls_merged": [],
            }
        ]
    }

    result = build_occupied_room_cell_complex(
        bldg=bldg,
        room_partitions=[],
        building_part_graph={},
    )

    assert result["metadata"]["room_count"] == 1
    assert result["metadata"]["cell_count"] >= 1
    cell = result["cells"][0]
    assert cell["room_index"] == 0
    assert cell["exact_source_kind"] == "synthetic_top_boundary_atom"
    assert result["metadata"]["synthetic_atom_cell_count"] >= 1
    assert cell["volume_m3"] > 0.0


def test_occupied_room_cell_complex_prefers_richer_merged_walls_over_sparse_computed_walls() -> None:
    bldg = {
        "rooms": [
            {
                "story": 0,
                "floor_polygon": [],
                "walls_computed": [
                    {"corners": [[0.0, -1.0, 0.0], [4.0, -1.0, 0.0], [4.0, 1.4, 0.0], [0.0, 1.4, 0.0]]},
                ],
                "walls_merged": [
                    {"corners": [[0.0, -1.0, 0.0], [4.0, -1.0, 0.0], [4.0, 1.4, 0.0], [0.0, 1.4, 0.0]]},
                    {"corners": [[4.0, -1.0, 0.0], [4.0, -1.0, 3.0], [4.0, 1.4, 3.0], [4.0, 1.4, 0.0]]},
                    {"corners": [[4.0, -1.0, 3.0], [0.0, -1.0, 3.0], [0.0, 1.4, 3.0], [4.0, 1.4, 3.0]]},
                    {"corners": [[0.0, -1.0, 3.0], [0.0, -1.0, 0.0], [0.0, 1.4, 0.0], [0.0, 1.4, 3.0]]},
                ],
            }
        ]
    }

    result = build_occupied_room_cell_complex(
        bldg=bldg,
        room_partitions=[],
        building_part_graph={},
    )

    assert result["metadata"]["room_count"] == 1
    assert result["metadata"]["cell_count"] >= 1
    assert result["metadata"]["synthetic_atom_cell_count"] >= 1


def test_occupied_room_cell_complex_falls_back_when_partition_surface_is_coplanar_with_floor() -> None:
    bldg = {
        "rooms": [
            {
                "story": 0,
                "floor_polygon": _rect(0.0, 0.0, 4.0, 3.0, -1.0),
                "walls_computed": [
                    {"corners": [[0.0, -1.0, 0.0], [4.0, -1.0, 0.0], [4.0, 1.4, 0.0], [0.0, 1.4, 0.0]]},
                    {"corners": [[4.0, -1.0, 0.0], [4.0, -1.0, 3.0], [4.0, 1.4, 3.0], [4.0, 1.4, 0.0]]},
                    {"corners": [[4.0, -1.0, 3.0], [0.0, -1.0, 3.0], [0.0, 1.4, 3.0], [4.0, 1.4, 3.0]]},
                    {"corners": [[0.0, -1.0, 3.0], [0.0, -1.0, 0.0], [0.0, 1.4, 0.0], [0.0, 1.4, 3.0]]},
                ],
                "walls_merged": [],
            }
        ]
    }
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
                    "poly": _rect(0.0, 0.0, 4.0, 3.0, -1.0),
                }
            ],
        }
    ]

    result = build_occupied_room_cell_complex(
        bldg=bldg,
        room_partitions=room_partitions,
        building_part_graph={},
    )

    assert result["metadata"]["room_count"] == 1
    assert result["metadata"]["cell_count"] >= 1
    assert result["metadata"]["fallback_cell_count"] == 0
    assert all(cell["volume_m3"] > 0.0 for cell in result["cells"])


def test_annotate_boundary_classes_marks_story_boundary_side_as_exterior_even_if_face_role_is_splitter() -> None:
    cell = {
        "faces": [
            {
                "kind": "side",
                "role": "splitter",
                "corners": [
                    [0.0, 0.0, 0.0],
                    [4.0, 0.0, 0.0],
                    [4.0, 2.4, 0.0],
                    [0.0, 2.4, 0.0],
                ],
            }
        ]
    }
    room_poly = Polygon([(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)])
    story_union = room_poly

    _annotate_boundary_classes(cell, room_poly, story_union)

    assert cell["faces"][0]["metadata"]["boundary_class"] == "exterior_wall"


def test_roof_cell_complex_builds_exact_attic_cell_from_flat_atom_and_oblique_roof() -> None:
    room_partitions = [
        {
            "room_index": 0,
            "story": 1,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 1,
                    "kind": "flat",
                    "flat_role": "ambiguous_flat_over_sloped_part",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, 2.4),
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
                    [0.0, 3.0, 0.0],
                    [4.0, 3.0, 0.0],
                    [4.0, 4.0, 4.0],
                    [0.0, 4.0, 4.0],
                ],
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
    )

    result = build_roof_cell_complex(
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "kind": "oblique",
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 3.0, 0.0],
                    [4.0, 3.0, 0.0],
                    [4.0, 4.0, 4.0],
                    [0.0, 4.0, 4.0],
                ],
                "cluster": {"avgAzimuth": 0.0, "avgIncl": 20.0},
                "center": {"x": 2.0, "y": 3.5, "z": 2.0},
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
    )

    assert result["metadata"]["exact_on_lattice"] is True
    assert result["metadata"]["attic_cell_count"] == 1
    assert result["metadata"]["knee_wall_count"] >= 1
    assert result["metadata"]["backend"] == "exact_lattice_roof_wall_slab_arrangement_v2"
    cell = result["cells"][0]
    assert cell["cell_kind"] == "attic"
    assert cell["volume_m3"] > 0.0
    assert cell["arrangement"]["plane_count"] >= 4
    face_roles = {face["role"] for face in cell["faces"]}
    assert "roof" in face_roles
    assert "slab" in face_roles
    assert "wall" in face_roles
    assert all("corners_lattice" in face for face in cell["faces"])


def test_roof_cell_complex_builds_upper_void_for_flat_transition_in_mixed_room() -> None:
    room_partitions = [
        {
            "room_index": 0,
            "story": 1,
            "mixed": True,
            "partitions": [
                {
                    "id": "atom:oblique:0",
                    "room_index": 0,
                    "story": 1,
                    "kind": "oblique",
                    "poly": [
                        [0.0, 2.8, 0.0],
                        [2.0, 2.8, 0.0],
                        [2.0, 3.4, 4.0],
                        [0.0, 3.4, 4.0],
                    ],
                },
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 1,
                    "kind": "flat",
                    "flat_role": "ceiling_cap",
                    "poly": _rect(2.0, 0.0, 4.0, 4.0, 2.6),
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
                    [0.0, 3.0, 0.0],
                    [4.0, 3.0, 0.0],
                    [4.0, 4.2, 4.0],
                    [0.0, 4.2, 4.0],
                ],
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
    )

    result = build_roof_cell_complex(
        room_partitions=room_partitions,
        selected_oblique_surfaces=[
            {
                "kind": "oblique",
                "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                "corners": [
                    [0.0, 3.0, 0.0],
                    [4.0, 3.0, 0.0],
                    [4.0, 4.2, 4.0],
                    [0.0, 4.2, 4.0],
                ],
                "cluster": {"avgAzimuth": 0.0, "avgIncl": 20.0},
                "center": {"x": 2.0, "y": 3.6, "z": 2.0},
            }
        ],
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
    )

    assert result["metadata"]["upper_void_cell_count"] == 1
    assert result["cells"][0]["cell_kind"] == "upper_void"
    assert any(face["role"] == "roof" for face in result["cells"][0]["faces"])


def test_roof_cell_complex_keeps_only_perimeter_facing_knee_walls() -> None:
    room_partitions = [
        {
            "room_index": 0,
            "story": 1,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 1,
                    "kind": "flat",
                    "flat_role": "ambiguous_flat_over_sloped_part",
                    "poly": _rect(0.0, 0.0, 4.0, 4.0, 2.4),
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
            }
        ],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:oblique:0": ["part:0"]},
    }
    selected_oblique_surfaces = [
        {
            "kind": "oblique",
            "roof_hypothesis_id": "roof-hypothesis:oblique:0",
            "corners": [
                [0.0, 4.0, 0.0],
                [4.0, 4.0, 0.0],
                [0.0, 5.2, 4.0],
            ],
            "cluster": {"avgAzimuth": 0.0, "avgIncl": 20.0},
            "center": {"x": 1.333333, "y": 4.4, "z": 1.333333},
        }
    ]
    roof_coverage_graph = build_roof_coverage_graph(
        room_partitions=room_partitions,
        selected_oblique_surfaces=selected_oblique_surfaces,
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
    )

    result = build_roof_cell_complex(
        room_partitions=room_partitions,
        selected_oblique_surfaces=selected_oblique_surfaces,
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
    )

    assert result["metadata"]["cell_count"] == 1
    assert result["metadata"]["knee_wall_count"] == 2


def test_roof_cell_complex_splits_non_convex_region_into_multiple_polyhedral_cells() -> None:
    room_partitions = [
        {
            "room_index": 0,
            "story": 1,
            "mixed": False,
            "partitions": [
                {
                    "id": "atom:flat:0",
                    "room_index": 0,
                    "story": 1,
                    "kind": "flat",
                    "flat_role": "ambiguous_flat_over_sloped_part",
                    "poly": [
                        [0.0, 2.4, 0.0],
                        [4.0, 2.4, 0.0],
                        [4.0, 2.4, 1.0],
                        [1.0, 2.4, 1.0],
                        [1.0, 2.4, 4.0],
                        [0.0, 2.4, 4.0],
                    ],
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
            }
        ],
        "room_membership": {"room:0": ["part:0"]},
        "hypothesis_membership": {"roof-hypothesis:oblique:0": ["part:0"]},
    }
    selected_oblique_surfaces = [
        {
            "kind": "oblique",
            "roof_hypothesis_id": "roof-hypothesis:oblique:0",
            "corners": [
                [0.0, 3.0, 0.0],
                [4.0, 3.0, 0.0],
                [4.0, 4.0, 4.0],
                [0.0, 4.0, 4.0],
            ],
            "cluster": {"avgAzimuth": 0.0, "avgIncl": 20.0},
            "center": {"x": 2.0, "y": 3.5, "z": 2.0},
        }
    ]
    roof_coverage_graph = build_roof_coverage_graph(
        room_partitions=room_partitions,
        selected_oblique_surfaces=selected_oblique_surfaces,
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
    )

    result = build_roof_cell_complex(
        room_partitions=room_partitions,
        selected_oblique_surfaces=selected_oblique_surfaces,
        selected_flat_surfaces=[],
        building_part_graph=building_part_graph,
        roof_coverage_graph=roof_coverage_graph,
    )

    assert result["metadata"]["cell_count"] >= 2
    assert all(cell["volume_m3"] > 0.0 for cell in result["cells"])
    assert all(cell["arrangement"]["vertex_count"] >= 4 for cell in result["cells"])


def test_occupied_room_cell_complex_splits_room_shell_by_exact_top_boundary_atoms() -> None:
    building = {
        "rooms": [
            {
                "story": 1,
                "floor_polygon": _rect(0.0, 0.0, 4.0, 4.0, 0.0),
                "walls_computed": [
                    {"corners": [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [4.0, 3.0, 0.0], [0.0, 3.0, 0.0]]},
                    {"corners": [[4.0, 0.0, 0.0], [4.0, 0.0, 4.0], [4.0, 3.0, 4.0], [4.0, 3.0, 0.0]]},
                    {"corners": [[4.0, 0.0, 4.0], [0.0, 0.0, 4.0], [0.0, 3.0, 4.0], [4.0, 3.0, 4.0]]},
                    {"corners": [[0.0, 0.0, 4.0], [0.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 3.0, 4.0]]},
                ],
            }
        ]
    }
    room_partitions = [
        {
            "room_index": 0,
            "story": 1,
            "mixed": True,
            "partitions": [
                {
                    "id": "atom:left",
                    "room_index": 0,
                    "story": 1,
                    "kind": "flat",
                    "poly": _rect(0.0, 0.0, 2.0, 4.0, 2.2),
                },
                {
                    "id": "atom:right",
                    "room_index": 0,
                    "story": 1,
                    "kind": "oblique",
                    "roof_hypothesis_id": "roof-hypothesis:oblique:0",
                    "poly": [
                        [2.0, 2.2, 0.0],
                        [4.0, 3.0, 0.0],
                        [4.0, 3.0, 4.0],
                        [2.0, 2.2, 4.0],
                    ],
                },
            ],
        }
    ]
    building_part_graph = {
        "room_membership": {"room:0": ["part:0"]},
    }

    result = build_occupied_room_cell_complex(
        bldg=building,
        room_partitions=room_partitions,
        building_part_graph=building_part_graph,
    )

    assert result["metadata"]["cell_count"] == 2
    assert result["metadata"]["fallback_cell_count"] == 0
    assert result["metadata"]["atom_bound_cell_count"] == 2
    assert result["metadata"]["face_class_counts"]["exterior_wall"] >= 4
    assert all(cell["exact_source_kind"] == "top_boundary_atom" for cell in result["cells"])
    assert {cell["top_boundary_atom_id"] for cell in result["cells"]} == {"atom:left", "atom:right"}
    assert any(cell["roof_hypothesis_id"] == "roof-hypothesis:oblique:0" for cell in result["cells"])
    assert all(
        any((face.get("metadata") or {}).get("boundary_class") == "ceiling" for face in (cell.get("faces") or []))
        for cell in result["cells"]
    )
