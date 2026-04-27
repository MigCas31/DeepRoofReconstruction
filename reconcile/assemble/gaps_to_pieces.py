from __future__ import annotations

from reconcile._core.newell import newell_normal
from reconcile.extract.building import BuildingModel
from reconcile.payload.schema import GapKind, GapPiece, GapScope, Vec3

_GAP_KIND_BY_TYPE = {
    "within_story": GapKind.SIDE,
    "gap_floor": GapKind.GAP_FLOOR,
    "gap_ceiling": GapKind.GAP_CEILING,
}
_STITCH_KIND_BY_TYPE = {
    "stitch": GapKind.STITCH,
    "stitch_floor": GapKind.STITCH_FLOOR,
    "stitch_ceiling": GapKind.STITCH_CEIL,
}
_EXTERIOR_KIND_BY_TYPE = {
    "side": GapKind.EXTERIOR_SIDE,
    "floor": GapKind.EXTERIOR_FLOOR,
    "ceiling": GapKind.EXTERIOR_CEIL,
}
_HORIZONTAL_KINDS = {
    GapKind.GAP_FLOOR,
    GapKind.GAP_CEILING,
    GapKind.STITCH_FLOOR,
    GapKind.STITCH_CEIL,
    GapKind.EXTERIOR_FLOOR,
    GapKind.EXTERIOR_CEIL,
}
_UPWARD_KINDS = {GapKind.GAP_CEILING, GapKind.STITCH_CEIL, GapKind.EXTERIOR_CEIL}
_UPWARD_KINDS.update({GapKind.GAP_FLOOR, GapKind.STITCH_FLOOR, GapKind.EXTERIOR_FLOOR})


def _normal_y(corners: list[list[float]]) -> float:
    return newell_normal(corners)[1]


def _planarize_horizontal(corners: list[list[float]], kind: GapKind) -> list[list[float]]:
    mean_y = sum(float(corner[1]) for corner in corners) / len(corners)
    out = [[float(corner[0]), mean_y, float(corner[2])] for corner in corners]
    normal_y = _normal_y(out)
    if kind in _UPWARD_KINDS and normal_y < 0.0:
        out.reverse()
    return out


def _to_vec3(corners: list[list[float]]) -> list[Vec3]:
    return [Vec3(x=float(corner[0]), y=float(corner[1]), z=float(corner[2])) for corner in corners]


def assemble_gap_pieces(model: BuildingModel) -> list[GapPiece]:
    pieces: list[GapPiece] = []

    def append_piece(
        corners: list[list[float]],
        kind: GapKind,
        scope: GapScope,
        locator_id: str,
    ) -> None:
        pieces.append(
            GapPiece(
                corners=_to_vec3(corners),
                kind=kind,
                scope=scope,
                locator_id=locator_id,
            )
        )

    for wall in model.gap_walls:
        kind = _GAP_KIND_BY_TYPE.get(wall.type)
        if kind is None:
            continue
        corners = wall.corners
        if kind in _HORIZONTAL_KINDS:
            corners = _planarize_horizontal(corners, kind)
        append_piece(
            corners,
            kind,
            GapScope.INTRA_STORY,
            f"{model.uuid}::tier-gap::{wall.id}",
        )

    for stitch in model.stitch_walls:
        kind = _STITCH_KIND_BY_TYPE.get(stitch.type)
        if kind is None:
            continue
        corners = stitch.corners
        if kind in _HORIZONTAL_KINDS:
            corners = _planarize_horizontal(corners, kind)
        append_piece(
            corners,
            kind,
            GapScope.JUNCTION,
            f"{model.uuid}::tier-gap::{stitch.id}",
        )

    for idx, closure in enumerate(model.gap_closures):
        kind = _EXTERIOR_KIND_BY_TYPE.get(closure.type)
        if kind is None:
            continue
        corners = closure.corners
        if kind in _HORIZONTAL_KINDS:
            corners = _planarize_horizontal(corners, kind)
        append_piece(
            corners,
            kind,
            GapScope.EXTERIOR,
            (
                f"{model.uuid}::tier-gap::"
                f"{closure.indicator_element_id}:{closure.indicator_wall_id}:{closure.type}:{idx}"
            ),
        )
    return pieces
