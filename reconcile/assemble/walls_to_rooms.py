from __future__ import annotations

import logging
from collections.abc import Sequence
from math import hypot, sqrt

from reconcile._core.newell import newell_normal
from reconcile.extract.building import (
    BuildingModel,
    ExtractedElement,
    ExtractedRoom,
)
from reconcile.payload.schema import HorizontalLid, Quad, Room, Vec3, Wall

PLANE_EPS_M = 0.05
EDGE_MARGIN_M = 0.01
LOGGER = logging.getLogger(__name__)


def _vec3(corner: Sequence[float]) -> Vec3:
    return Vec3(x=float(corner[0]), y=float(corner[1]), z=float(corner[2]))


def _coords(corners: Sequence[Vec3]) -> list[list[float]]:
    return [[corner.x, corner.y, corner.z] for corner in corners]


def _centroid(corners: Sequence[Sequence[float]]) -> list[float]:
    n = max(1, len(corners))
    return [
        sum(float(corner[axis]) for corner in corners) / n
        for axis in range(3)
    ]


def _room_center(room: ExtractedRoom) -> list[float]:
    return _centroid(room.floor_polygon) if room.floor_polygon else [0.0, 0.0, 0.0]


def _orient_floor_up(corners: list[list[float]]) -> list[list[float]]:
    if len(corners) < 3:
        return corners
    return list(reversed(corners)) if newell_normal(corners)[1] <= 0.0 else corners


def _orient_wall_outward(corners: list[list[float]], room_center: list[float]) -> list[list[float]]:
    if len(corners) < 3:
        return corners
    normal = newell_normal(corners)
    wall_center = _centroid(corners)
    outward = [wall_center[idx] - room_center[idx] for idx in range(3)]
    if sum(normal[idx] * outward[idx] for idx in range(3)) < 0.0:
        return list(reversed(corners))
    return corners


def _projection_axes(corners: list[list[float]]) -> tuple[int, int]:
    nx, ny, nz = newell_normal(corners)
    anx, any_, anz = abs(nx), abs(ny), abs(nz)
    if any_ >= anx and any_ >= anz:
        return 0, 2
    if anx >= any_ and anx >= anz:
        return 1, 2
    return 0, 1


def _point_in_polygon_2d(point: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    j = len(poly) - 1
    for i, (xi, yi) in enumerate(poly):
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


def _distance_point_to_segment_2d(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = point[0] - a[0], point[1] - a[1]
    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        return hypot(wx, wy)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / vv))
    px, py = a[0] + t * vx, a[1] + t * vy
    return hypot(point[0] - px, point[1] - py)


def _distance_to_wall_plane(normal: tuple[float, float, float], p0: list[float], point: list[float]) -> float:
    norm = sqrt(sum(value * value for value in normal))
    if norm <= 1e-12:
        return float("inf")
    return abs(sum(normal[idx] * (float(point[idx]) - p0[idx]) for idx in range(3))) / norm


def _opening_inside_wall(wall_corners: list[list[float]], opening: ExtractedElement) -> bool:
    if len(opening.corners) != 4 or len(wall_corners) < 3:
        return False
    normal = newell_normal(wall_corners)
    if sqrt(sum(value * value for value in normal)) <= 1e-12:
        return False
    p0 = [float(value) for value in wall_corners[0]]
    if any(_distance_to_wall_plane(normal, p0, point) > PLANE_EPS_M for point in opening.corners):
        return False

    axis0, axis1 = _projection_axes(wall_corners)
    outer = [(float(corner[axis0]), float(corner[axis1])) for corner in wall_corners]
    centroid = _centroid(opening.corners)
    if not _point_in_polygon_2d((centroid[axis0], centroid[axis1]), outer):
        return False

    for corner in opening.corners:
        point = (float(corner[axis0]), float(corner[axis1]))
        if not _point_in_polygon_2d(point, outer):
            return False
        min_distance = min(
            _distance_point_to_segment_2d(point, outer[idx - 1], outer[idx])
            for idx in range(len(outer))
        )
        if min_distance < EDGE_MARGIN_M:
            return False
    return True


def _quad(element: ExtractedElement) -> Quad:
    return Quad(corners=[_vec3(corner) for corner in element.corners])


def _quad_openings(
    openings: list[ExtractedElement],
    *,
    model_uuid: str,
    room_index: int,
    kind: str,
) -> list[ExtractedElement]:
    quads: list[ExtractedElement] = []
    for opening in openings:
        if len(opening.corners) == 4:
            quads.append(opening)
            continue
        LOGGER.warning(
            "Skipping non-quad %s opening in tier payload assembly: "
            "uuid=%s room=%s id=%s corner_count=%s",
            kind,
            model_uuid,
            room_index,
            opening.id,
            len(opening.corners),
        )
    return quads


def assemble_rooms(model: BuildingModel) -> list[Room]:
    rooms: list[Room] = []
    for room in model.rooms:
        if len(room.floor_polygon) < 3:
            continue
        room_center = _room_center(room)
        windows = _quad_openings(
            room.windows,
            model_uuid=model.uuid,
            room_index=room.index,
            kind="window",
        )
        doors = _quad_openings(
            room.doors,
            model_uuid=model.uuid,
            room_index=room.index,
            kind="door",
        )
        openings = [*windows, *doors]
        walls: list[Wall] = []
        for wall in room.walls_computed:
            wall_corners = _orient_wall_outward(
                [[float(corner[0]), float(corner[1]), float(corner[2])] for corner in wall.corners],
                room_center,
            )
            cutouts = [
                _quad(opening)
                for opening in openings
                if _opening_inside_wall(wall_corners, opening)
            ]
            extension_strip = None
            if wall.extension_strip:
                strip = wall.extension_strip[0]
                extension_strip = [
                    _vec3(corner)
                    for corner in _orient_wall_outward(strip, room_center)
                ]
            walls.append(
                Wall(
                    corners=[_vec3(corner) for corner in wall_corners],
                    extension_strip=extension_strip,
                    cutouts=cutouts,
                    locator_id=f"{model.uuid}::tier-wall::{room.index}:{wall.id}",
                )
            )
        rooms.append(
            Room(
                story=room.story,
                floor=HorizontalLid(corners=[_vec3(corner) for corner in _orient_floor_up(room.floor_polygon)]),
                walls=walls,
                doors=[_quad(door) for door in doors],
                windows=[_quad(window) for window in windows],
                locator_id=f"{model.uuid}::tier-room::{room.index}",
            )
        )
    return rooms
