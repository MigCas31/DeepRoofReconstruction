from __future__ import annotations

from reconcile.roof_algorithms_py.roof_hypothesis_graph import (
    build_roof_hypothesis_graph,
    select_roof_surfaces_from_hypotheses,
)
from reconcile.roof_algorithms_py.roof_partitioning import (
    derive_room_ceiling_partitions,
)
from reconcile_v2.models import GraphEdge, GraphNode, TopologyGraph


def _rect(x0: float, z0: float, x1: float, z1: float, y: float = 0.0) -> list[list[float]]:
    return [
        [x0, y, z0],
        [x1, y, z0],
        [x1, y, z1],
        [x0, y, z1],
    ]


def _graph_for_rooms() -> TopologyGraph:
    return TopologyGraph(
        version="test",
        metadata={},
        nodes=[
            GraphNode(
                id="room:r0",
                type="Room",
                story=0,
                bbox_xz=[0.0, 0.0, 4.0, 4.0],
                properties={"is_top_story": True},
            ),
            GraphNode(
                id="room:r1",
                type="Room",
                story=0,
                bbox_xz=[4.0, 0.0, 8.0, 4.0],
                properties={"is_top_story": True},
            ),
            GraphNode(id="cell:outside", type="Cell", properties={"cell_kind": "outside"}),
        ],
        edges=[
            GraphEdge(id="exposes:r0", type="EXPOSES_TO", from_id="room:r0", to_id="cell:outside"),
            GraphEdge(id="exposes:r1", type="EXPOSES_TO", from_id="room:r1", to_id="cell:outside"),
        ],
    )


def test_hypothesis_graph_selects_meaningful_partial_flat_and_oblique_candidates() -> None:
    bldg = {
        "rooms": [
            {
                "story": 0,
                "floor_polygon": _rect(0.0, 0.0, 4.0, 4.0),
            }
        ]
    }
    exposed_rooms = [
        {
            "room_index": 0,
            "story": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.0,
            "wallTopMin": 2.75,
        }
    ]
    oblique_surfaces = [
        {
            "dominant_story": 0,
            "corners": [
                [0.0, 2.5, 0.0],
                [4.0, 3.5, 0.0],
                [4.0, 3.5, 4.0],
                [0.0, 2.5, 4.0],
            ],
            "center": {"x": 2.0, "y": 3.0, "z": 2.0},
            "cluster": {
                "avgAzimuth": 90.0,
                "avgIncl": 15.0,
                "room_indices": [0],
                "segs": [{}, {}, {}, {}],
            },
            "space_boundary_ids": ["boundary:roof:o0"],
        }
    ]
    flat_surfaces = [
        {
            "kind": "intermediate",
            "story": 0,
            "room_index": 0,
            "y": 3.0,
            "corners": _rect(2.0, 0.0, 4.0, 4.0, y=3.0),
            "space_boundary_ids": ["boundary:roof:f0"],
        }
    ]

    hypothesis_graph = build_roof_hypothesis_graph(
        bldg=bldg,
        exposed_rooms=exposed_rooms,
        oblique_surfaces=oblique_surfaces,
        flat_surfaces=flat_surfaces,
        roof_graph={"nodes": [], "edges": [], "metadata": {}},
        graph=_graph_for_rooms(),
    )

    assert hypothesis_graph["selected_room_assignments"]["room:0"] == [
        "roof-hypothesis:oblique:0",
        "roof-hypothesis:flat:0",
    ]


def test_room_ceiling_partitions_split_by_selected_hypotheses() -> None:
    bldg = {
        "rooms": [
            {
                "story": 0,
                "floor_polygon": _rect(0.0, 0.0, 4.0, 4.0),
            }
        ]
    }
    exposed_rooms = [
        {
            "room_index": 0,
            "story": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.0,
            "wallTopMin": 2.75,
        }
    ]
    oblique_surfaces = [
        {
            "dominant_story": 0,
            "corners": [
                [0.0, 2.5, 0.0],
                [4.0, 3.5, 0.0],
                [4.0, 3.5, 4.0],
                [0.0, 2.5, 4.0],
            ],
            "center": {"x": 2.0, "y": 3.0, "z": 2.0},
            "cluster": {
                "avgAzimuth": 90.0,
                "avgIncl": 15.0,
                "room_indices": [0],
                "segs": [{}, {}, {}, {}],
            },
            "space_boundary_ids": ["boundary:roof:o0"],
        }
    ]
    flat_surfaces = [
        {
            "kind": "intermediate",
            "story": 0,
            "room_index": 0,
            "y": 3.0,
            "corners": _rect(2.0, 0.0, 4.0, 4.0, y=3.0),
            "space_boundary_ids": ["boundary:roof:f0"],
        }
    ]

    hypothesis_graph = build_roof_hypothesis_graph(
        bldg=bldg,
        exposed_rooms=exposed_rooms,
        oblique_surfaces=oblique_surfaces,
        flat_surfaces=flat_surfaces,
        roof_graph={"nodes": [], "edges": [], "metadata": {}},
        graph=_graph_for_rooms(),
    )
    selected_oblique, selected_flat = select_roof_surfaces_from_hypotheses(
        oblique_surfaces=oblique_surfaces,
        flat_surfaces=flat_surfaces,
        hypothesis_graph=hypothesis_graph,
    )
    partitions = derive_room_ceiling_partitions(
        exposed_rooms=exposed_rooms,
        oblique_roof_surfaces=selected_oblique,
        flat_roof_surfaces=selected_flat,
        hypothesis_graph=hypothesis_graph,
    )

    assert partitions["metadata"]["mixed_room_count"] == 0
    assert partitions["metadata"]["flat_partition_count"] == 0
    assert partitions["metadata"]["oblique_partition_count"] == 2
    assert partitions["metadata"]["split_line_count"] == 1
    total_area = sum(part["area_m2"] for part in partitions["room_partitions"][0]["partitions"])
    assert round(total_area, 3) == 16.0


def test_room_ceiling_partitions_split_by_globally_selected_competing_surface() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "story": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.5,
            "wallTopMin": 2.5,
        }
    ]
    oblique_surfaces = [
        {
            "roof_hypothesis_id": "roof-hypothesis:oblique:0",
            "dominant_story": 0,
            "corners": [
                [0.0, 2.5, 0.0],
                [4.0, 3.5, 0.0],
                [4.0, 3.5, 4.0],
                [0.0, 2.5, 4.0],
            ],
            "center": {"x": 2.0, "y": 3.0, "z": 2.0},
            "cluster": {
                "avgAzimuth": 90.0,
                "avgIncl": 14.0,
                "room_indices": [0],
                "segs": [{}, {}, {}, {}],
            },
        }
    ]
    flat_surfaces = [
        {
            "roof_hypothesis_id": "roof-hypothesis:flat:0",
            "kind": "intermediate",
            "story": 0,
            "room_index": 0,
            "y": 3.0,
            "corners": _rect(0.0, 0.0, 4.0, 4.0, y=3.0),
        }
    ]
    hypothesis_graph = {
        "nodes": [
            {"id": "roof-hypothesis:oblique:0", "type": "RoofHypothesis", "surface_kind": "oblique", "story": 1, "selected": True},
            {"id": "roof-hypothesis:flat:0", "type": "RoofHypothesis", "surface_kind": "flat", "story": 0, "selected": True},
        ],
        "edges": [
            {
                "id": "edge:covers:flat",
                "type": "COVERS_ROOM",
                "from": "roof-hypothesis:flat:0",
                "to": "room:0",
                "selected": True,
                "evidence": {"edge_score": 0.8},
            }
        ],
        "selected_hypothesis_ids": ["roof-hypothesis:oblique:0", "roof-hypothesis:flat:0"],
        "selected_room_assignments": {"room:0": ["roof-hypothesis:flat:0"]},
    }

    partitions = derive_room_ceiling_partitions(
        exposed_rooms=exposed_rooms,
        oblique_roof_surfaces=oblique_surfaces,
        flat_roof_surfaces=flat_surfaces,
        hypothesis_graph=hypothesis_graph,
    )

    room = partitions["room_partitions"][0]
    total_area = sum(part["area_m2"] for part in room["partitions"])

    assert room["mixed"] is True
    assert any(part["kind"] == "oblique" for part in room["partitions"])
    assert any(part["kind"] == "flat" for part in room["partitions"])
    assert partitions["metadata"]["split_line_count"] >= 1
    assert round(total_area, 3) == 16.0


def test_room_ceiling_partitions_fallback_to_graph_footprint_when_raw_polygon_is_invalid() -> None:
    exposed_rooms = [
        {
            "room_index": 0,
            "story": 0,
            "graph_room_id": "room:r0",
            # Degenerate raw polygon in XZ, should fail raw polygon path.
            "fp": [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [3.0, 0.0, 0.0],
            ],
            "graph_fp_xz": [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]],
            "floorY": 0.0,
            "wallTopY": 3.0,
            "wallTopMin": 2.5,
        }
    ]
    hypothesis_graph = {
        "nodes": [],
        "edges": [],
        "selected_hypothesis_ids": [],
        "selected_room_assignments": {},
    }

    partitions = derive_room_ceiling_partitions(
        exposed_rooms=exposed_rooms,
        oblique_roof_surfaces=[],
        flat_roof_surfaces=[],
        hypothesis_graph=hypothesis_graph,
    )

    assert [room["room_index"] for room in partitions["room_partitions"]] == [0]
    room = partitions["room_partitions"][0]
    assert room["partition_count"] == 1
    assert room["partitions"][0]["kind"] == "flat"
    assert round(room["partitions"][0]["area_m2"], 3) == 16.0


def test_hypothesis_graph_uses_continuation_edges_to_link_candidates() -> None:
    bldg = {
        "rooms": [
            {"story": 0, "floor_polygon": _rect(0.0, 0.0, 4.0, 4.0)},
            {"story": 0, "floor_polygon": _rect(4.0, 0.0, 8.0, 4.0)},
        ]
    }
    exposed_rooms = [
        {
            "room_index": 0,
            "story": 0,
            "graph_room_id": "room:r0",
            "fp": _rect(0.0, 0.0, 4.0, 4.0),
            "wallTopY": 3.0,
            "wallTopMin": 2.8,
        },
        {
            "room_index": 1,
            "story": 0,
            "graph_room_id": "room:r1",
            "fp": _rect(4.0, 0.0, 8.0, 4.0),
            "wallTopY": 3.0,
            "wallTopMin": 2.8,
        },
    ]
    oblique_surfaces = [
        {
            "dominant_story": 0,
            "corners": [
                [0.0, 2.8, 0.0],
                [4.0, 3.0, 0.0],
                [4.0, 3.0, 4.0],
                [0.0, 2.8, 4.0],
            ],
            "center": {"x": 2.0, "y": 2.9, "z": 2.0},
            "cluster": {
                "avgAzimuth": 90.0,
                "avgIncl": 10.0,
                "room_indices": [0],
                "segs": [{}, {}, {}, {}],
            },
            "space_boundary_ids": ["boundary:roof:o0"],
        },
        {
            "dominant_story": 0,
            "corners": [
                [4.0, 3.0, 0.0],
                [8.0, 3.2, 0.0],
                [8.0, 3.2, 4.0],
                [4.0, 3.0, 4.0],
            ],
            "center": {"x": 6.0, "y": 3.1, "z": 2.0},
            "cluster": {
                "avgAzimuth": 90.0,
                "avgIncl": 10.0,
                "room_indices": [1],
                "segs": [{}, {}, {}, {}],
            },
            "space_boundary_ids": ["boundary:roof:o1"],
        },
    ]

    hypothesis_graph = build_roof_hypothesis_graph(
        bldg=bldg,
        exposed_rooms=exposed_rooms,
        oblique_surfaces=oblique_surfaces,
        flat_surfaces=[],
        roof_graph={
            "nodes": [],
            "edges": [
                {
                    "type": "CONTINUES_AS",
                    "from": "boundary:roof:o0",
                    "to": "boundary:roof:o1",
                    "evidence": {
                        "shared_edge_length_m": 4.0,
                        "relation_state": "confirmed",
                        "exact_face_incidence": True,
                        "partition_atom_pairs": [["a0", "a1"]],
                    },
                },
                {
                    "type": "CONTINUES_AS",
                    "from": "boundary:roof:o1",
                    "to": "boundary:roof:o0",
                    "evidence": {
                        "shared_edge_length_m": 4.0,
                        "relation_state": "confirmed",
                        "exact_face_incidence": True,
                        "partition_atom_pairs": [["a1", "a0"]],
                    },
                },
            ],
            "metadata": {},
        },
        graph=_graph_for_rooms(),
    )

    hypothesis_nodes = {
        node["id"]: node
        for node in hypothesis_graph["nodes"]
        if node.get("type") == "RoofHypothesis"
    }

    assert hypothesis_graph["metadata"]["continuation_edge_count"] == 2
    assert hypothesis_nodes["roof-hypothesis:oblique:0"]["continuation_component_size"] == 2
    assert hypothesis_nodes["roof-hypothesis:oblique:1"]["continuation_component_size"] == 2
