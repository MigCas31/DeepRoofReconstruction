from __future__ import annotations

from .graph_support import (
    classify_graph_roof_room,
    graph_allows_roof_candidate,
    graph_requires_geometry_fallback,
)
from .roof_flat_geometry import bbox, bbox_surface


def collect_intermediate_flat_surfaces(
    *, bldg: dict, has_floor_above, bldg_min_y: float, graph=None
) -> tuple[list, list]:
    flat_surfaces = []
    roof_legend_flat = []

    for room_idx, room in enumerate(bldg.get("rooms", [])):
        fp = room.get("floor_polygon")
        if not fp or len(fp) < 3:
            continue

        fcx = sum(p[0] for p in fp) / len(fp)
        fcz = sum(p[2] for p in fp) / len(fp)
        story = int(room.get("story", 0))
        _graph_room, roof_decision = classify_graph_roof_room(graph, story, fp)
        if roof_decision is not None and not graph_allows_roof_candidate(roof_decision):
            continue
        if graph_requires_geometry_fallback(roof_decision) and has_floor_above(fcx, fcz, story):
            continue

        min_x, max_x, min_z, max_z = bbox(fp)
        if max(max_x - min_x, max_z - min_z) < 2.0:
            continue

        y = fp[0][1]
        corners = bbox_surface(fp, y)
        flat_surfaces.append(
            {
                "kind": "intermediate",
                "story": story,
                "y": y,
                "corners": corners,
                "room_index": room_idx,
                "graph_room_id": _graph_room.id if _graph_room is not None else None,
            }
        )
        roof_legend_flat.append(
            {
                "count": 1,
                "avgIncl": 0.0,
                "avgAzimuth": None,
                "flat": True,
                "height": (y - bldg_min_y) if bldg_min_y != float("inf") else y,
            }
        )

    return flat_surfaces, roof_legend_flat
