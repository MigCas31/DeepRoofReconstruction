from __future__ import annotations

from collections.abc import Callable
from math import sqrt

from reconcile_tiers.extract.building import BuildingModel
from reconcile_tiers.roof.geometry import (
    edge_azimuth_deg,
    edge_inclination_deg,
    wall_quads,
)
from reconcile_tiers.roof.roof import RoofSegment

MIN_SEG_LEN_M = 0.3
MIN_INCL_DEG = 5.0
MAX_INCL_DEG = 80.0


def collect_oblique_segments(
    model: BuildingModel,
    has_floor_above: Callable[[float, float, int], bool] | None = None,
    exclude_room_indices: set[int] | None = None,
) -> list[RoofSegment]:
    segments: list[RoofSegment] = []
    for room in model.rooms:
        if exclude_room_indices and room.index in exclude_room_indices:
            continue
        for wall in room.walls_computed:
            for corners in wall_quads(wall):
                for idx, first in enumerate(corners):
                    second = corners[(idx + 1) % len(corners)]
                    a = first
                    b = second
                    if a[1] < b[1]:
                        a, b = b, a
                    dx = b[0] - a[0]
                    dy = b[1] - a[1]
                    dz = b[2] - a[2]
                    length = sqrt(dx * dx + dy * dy + dz * dz)
                    if length < MIN_SEG_LEN_M:
                        continue
                    incl = edge_inclination_deg(a, b)
                    if incl <= MIN_INCL_DEG or incl >= MAX_INCL_DEG:
                        continue
                    midpoint_x = (a[0] + b[0]) / 2.0
                    midpoint_z = (a[2] + b[2]) / 2.0
                    if has_floor_above is not None and has_floor_above(midpoint_x, midpoint_z, room.story):
                        continue
                    segments.append(
                        RoofSegment(
                            a=[float(a[0]), float(a[1]), float(a[2])],
                            b=[float(b[0]), float(b[1]), float(b[2])],
                            incl=incl,
                            azimuth=edge_azimuth_deg(a, b),
                            length=length,
                            story=room.story,
                            room_index=room.index,
                            wall_id=wall.id,
                        )
                    )
    return segments
