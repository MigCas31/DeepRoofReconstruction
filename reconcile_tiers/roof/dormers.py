from __future__ import annotations

from math import hypot

from reconcile_tiers.extract.building import BuildingModel
from reconcile_tiers.roof.geometry import wall_normal_xz
from reconcile_tiers.roof.roof import Dormer, ObliqueSurface

PERPENDICULAR_DOT = 0.35
PROTRUSION_THRESH_M = 0.10
MAX_BOTTOM_ABOVE_ROOF_M = 1.5
MAX_WIDTH_RATIO = 0.70
MAX_HEIGHT_RATIO = 0.75
CORNER_MATCH_TOL_M = 0.15
DEPTH_FRACTION = 0.70


def _wall_height(corners: list[list[float]]) -> float:
    ys = [p[1] for p in corners]
    return max(ys) - min(ys)


def _wall_width_along_ridge(corners: list[list[float]], ridge_x: float, ridge_z: float) -> float:
    projections = [p[0] * ridge_x + p[2] * ridge_z for p in corners]
    return max(projections) - min(projections)


def _bottom_edge(corners: list[list[float]]) -> tuple[list[float], list[float]]:
    bottom = sorted(corners, key=lambda p: p[1])[:2]
    return bottom[0], bottom[1]


def _top_edge(corners: list[list[float]]) -> tuple[list[float], list[float]]:
    top = sorted(corners, key=lambda p: p[1], reverse=True)[:2]
    return top[0], top[1]


def _cutout_and_trim(surface: ObliqueSurface, wall_corners: list[list[float]]) -> tuple[list[list[float]], list[list[list[float]]], list[list[float]]] | None:
    b0, b1 = _bottom_edge(wall_corners)
    top_y = max(p[1] for p in wall_corners)
    mid_x = (b0[0] + b1[0]) / 2.0
    mid_z = (b0[2] + b1[2]) / 2.0
    base_y = surface.plane.y_at(mid_x, mid_z)
    if base_y is None:
        return None
    grad_x = -surface.plane.a / surface.plane.b
    grad_z = -surface.plane.c / surface.plane.b
    grad_len = hypot(grad_x, grad_z)
    if grad_len < 1e-9:
        return None
    up_x = grad_x / grad_len
    up_z = grad_z / grad_len
    depth = max(0.20, (top_y - base_y) / grad_len * DEPTH_FRACTION)

    front = [(b0[0], b0[2]), (b1[0], b1[2])]
    back = [(x + up_x * depth, z + up_z * depth) for x, z in front]
    xz = [front[0], front[1], back[1], back[0]]
    cutout = [[x, float(surface.plane.y_at(x, z)), z] for x, z in xz if surface.plane.y_at(x, z) is not None]
    if len(cutout) != 4:
        return None
    front_top = [[front[0][0], top_y, front[0][1]], [front[1][0], top_y, front[1][1]]]
    back_top = [[back[0][0], top_y, back[0][1]], [back[1][0], top_y, back[1][1]]]
    header = [front_top[0], front_top[1], back_top[1], back_top[0]]
    cheeks = [
        [cutout[0], front_top[0], back_top[0], cutout[3]],
        [cutout[1], cutout[2], back_top[1], front_top[1]],
    ]
    return cutout, cheeks, header


def detect_dormers(model: BuildingModel, obliques: list[ObliqueSurface]) -> list[Dormer]:
    dormers: list[Dormer] = []
    for surface_idx, surface in enumerate(obliques):
        ridge_x = surface.ridge["x"]
        ridge_z = surface.ridge["z"]
        ridge_span = surface.ridge["max"] - surface.ridge["min"]
        for room in model.rooms:
            if room.story != surface.dominant_story:
                continue
            max_room_wall_height = max((_wall_height(w.corners) for w in room.walls_merged + room.walls_computed if len(w.corners) >= 3), default=0.0)
            seen: set[str] = set()
            for wall in [*room.walls_computed, *room.walls_merged]:
                if wall.id in seen or len(wall.corners) < 3:
                    continue
                seen.add(wall.id)
                normal_x, normal_z = wall_normal_xz(wall.corners)
                if abs(normal_x * ridge_x + normal_z * ridge_z) > PERPENDICULAR_DOT:
                    continue
                roof_ys = [surface.plane.y_at(c[0], c[2]) for c in wall.corners]
                if any(y is None for y in roof_ys):
                    continue
                above = [corner[1] > roof_y + PROTRUSION_THRESH_M for corner, roof_y in zip(wall.corners, roof_ys)]
                if not any(above):
                    continue
                if all(above) and min(c[1] - y for c, y in zip(wall.corners, roof_ys)) > MAX_BOTTOM_ABOVE_ROOF_M:
                    continue
                width = _wall_width_along_ridge(wall.corners, ridge_x, ridge_z)
                if ridge_span > 0 and width >= MAX_WIDTH_RATIO * ridge_span:
                    continue
                if max_room_wall_height > 0 and _wall_height(wall.corners) >= MAX_HEIGHT_RATIO * max_room_wall_height:
                    continue
                trim = _cutout_and_trim(surface, wall.corners)
                if trim is None:
                    continue
                cutout, cheeks, header = trim
                dormers.append(
                    Dormer(
                        roof_surface_index=surface_idx,
                        room_index=room.index,
                        front_wall_id=wall.id,
                        cutout_quad=cutout,
                        cheek_quads=cheeks,
                        header_quad=header,
                    )
                )
    return dormers


def append_dormer_cutouts(obliques: list[ObliqueSurface], dormers: list[Dormer]) -> None:
    for dormer in dormers:
        if 0 <= dormer.roof_surface_index < len(obliques):
            obliques[dormer.roof_surface_index].cutout_holes.append(dormer.cutout_quad)
