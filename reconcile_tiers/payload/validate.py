from __future__ import annotations

import math

from shapely.geometry import Polygon

from reconcile_tiers._core.newell import is_planar, newell_normal
from reconcile_tiers._core.plane import Plane as CorePlane
from reconcile_tiers.payload.schema import (
    CeilingPiece,
    GapKind,
    GapPiece,
    HorizontalLid,
    Plane,
    Quad,
    Room,
    TierPayload,
    Vec3,
    Wall,
)

_HORIZONTAL_GAP_KINDS = {
    GapKind.GAP_FLOOR,
    GapKind.GAP_CEILING,
    GapKind.STITCH_FLOOR,
    GapKind.STITCH_CEIL,
    GapKind.EXTERIOR_FLOOR,
    GapKind.EXTERIOR_CEIL,
}


class PayloadInvariantError(ValueError):
    def __init__(self, path: str, expected: str, actual: object) -> None:
        super().__init__(f"{path}: expected {expected}, got {actual!r}")
        self.path = path
        self.expected = expected
        self.actual = actual


def _coords(corners: list[Vec3]) -> list[list[float]]:
    return [[corner.x, corner.y, corner.z] for corner in corners]


def _validate_horizontal_lid(lid: HorizontalLid, path: str) -> None:
    if len(lid.corners) < 3:
        raise PayloadInvariantError(path, "at least 3 corners", len(lid.corners))
    ys = [corner.y for corner in lid.corners]
    spread = max(ys) - min(ys)
    if spread > 1e-3:
        raise PayloadInvariantError(path, "planar Y spread <= 0.001", spread)
    normal_y = newell_normal(_coords(lid.corners))[1]
    if normal_y <= 0.0:
        raise PayloadInvariantError(path, "Newell normal +Y", normal_y)


def _validate_quad(quad: Quad, path: str) -> None:
    if len(quad.corners) != 4:
        raise PayloadInvariantError(path, "exactly 4 corners", len(quad.corners))
    if not is_planar(_coords(quad.corners), tol=0.05):
        raise PayloadInvariantError(path, "coplanar within 0.05 m", _coords(quad.corners))


def _validate_plane(plane: Plane, path: str) -> None:
    coeffs = (plane.a, plane.b, plane.c, plane.d)
    if not all(math.isfinite(value) for value in coeffs):
        raise PayloadInvariantError(path, "finite plane coefficients", coeffs)
    if abs(plane.b) < CorePlane.MIN_NY:
        raise PayloadInvariantError(path, f"|b| >= {CorePlane.MIN_NY}", plane.b)


def _plane_y_at(plane: Plane, x: float, z: float) -> float:
    return (plane.d - plane.a * x - plane.c * z) / plane.b


def _polygon_xz(corners: list[Vec3]) -> Polygon:
    return Polygon([(corner.x, corner.z) for corner in corners])


def _validate_ceiling_piece(piece: CeilingPiece, path: str) -> None:
    _validate_plane(piece.plane, f"{path}.plane")
    if len(piece.corners) < 3:
        raise PayloadInvariantError(f"{path}.corners", "at least 3 corners", len(piece.corners))
    if newell_normal(_coords(piece.corners))[1] <= 0.0:
        raise PayloadInvariantError(f"{path}.corners", "Newell normal +Y", newell_normal(_coords(piece.corners))[1])
    for idx, corner in enumerate(piece.corners):
        expected_y = _plane_y_at(piece.plane, corner.x, corner.z)
        if abs(expected_y - corner.y) > 0.01:
            raise PayloadInvariantError(f"{path}.corners[{idx}]", "corner.y within 0.01 m of plane.y_at", corner.y - expected_y)
    main_poly = _polygon_xz(piece.corners)
    if not main_poly.is_valid or main_poly.is_empty:
        raise PayloadInvariantError(f"{path}.corners", "valid non-empty XZ polygon", main_poly.wkt)
    for hole_idx, hole in enumerate(piece.holes):
        if len(hole) < 3:
            raise PayloadInvariantError(f"{path}.holes[{hole_idx}]", "at least 3 corners", len(hole))
        hole_poly = _polygon_xz(hole)
        if not main_poly.contains(hole_poly):
            raise PayloadInvariantError(f"{path}.holes[{hole_idx}]", "hole contained by main polygon", hole_poly.wkt)


def _validate_wall(wall: Wall, room: Room, wall_idx: int, room_path: str) -> None:
    if len(wall.corners) < 3:
        raise PayloadInvariantError(f"{room_path}.walls[{wall_idx}].corners", "at least 3 corners", len(wall.corners))
    for cutout_idx, cutout in enumerate(wall.cutouts):
        _validate_quad(cutout, f"{room_path}.walls[{wall_idx}].cutouts[{cutout_idx}]")


def _validate_gap_piece(piece: GapPiece, path: str) -> None:
    if len(piece.corners) < 3:
        raise PayloadInvariantError(f"{path}.corners", "at least 3 corners", len(piece.corners))
    if piece.kind in _HORIZONTAL_GAP_KINDS:
        normal_y = newell_normal(_coords(piece.corners))[1]
        if normal_y <= 0.0:
            raise PayloadInvariantError(f"{path}.corners", "Newell normal +Y", normal_y)


def validate_payload(payload: TierPayload) -> None:
    if payload.schema_version != "1":
        raise PayloadInvariantError("schema_version", "'1'", payload.schema_version)
    if not 1 <= payload.classification.tier <= 8:
        raise PayloadInvariantError("classification.tier", "1..8", payload.classification.tier)
    for room_idx, room in enumerate(payload.rooms):
        room_path = f"rooms[{room_idx}]"
        _validate_horizontal_lid(room.floor, f"{room_path}.floor")
        for wall_idx, wall in enumerate(room.walls):
            _validate_wall(wall, room, wall_idx, room_path)
        for door_idx, door in enumerate(room.doors):
            _validate_quad(door, f"{room_path}.doors[{door_idx}]")
        for window_idx, window in enumerate(room.windows):
            _validate_quad(window, f"{room_path}.windows[{window_idx}]")
    for ceiling_idx, piece in enumerate(payload.ceiling):
        _validate_ceiling_piece(piece, f"ceiling[{ceiling_idx}]")
    for gap_idx, piece in enumerate(payload.gaps):
        _validate_gap_piece(piece, f"gaps[{gap_idx}]")
