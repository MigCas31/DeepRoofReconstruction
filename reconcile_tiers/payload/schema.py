from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import StrEnum
from types import UnionType
from typing import Any, Literal, get_args, get_origin, get_type_hints


class GapKind(StrEnum):
    GAP_FLOOR = "gap_floor"
    GAP_CEILING = "gap_ceiling"
    SIDE = "side"
    STITCH = "stitch"
    STITCH_FLOOR = "stitch_floor"
    STITCH_CEIL = "stitch_ceiling"
    EXTERIOR_SIDE = "exterior_side"
    EXTERIOR_FLOOR = "exterior_floor"
    EXTERIOR_CEIL = "exterior_ceiling"


class GapScope(StrEnum):
    INTRA_STORY = "intra_story"
    INTER_STORY = "inter_story"
    EXTERIOR = "exterior"
    JUNCTION = "junction"


class CeilingSource(StrEnum):
    FLAT_EMIT = "flat_emit"
    DORMER_CUTOUT = "dormer_cutout"
    ROOF_ARRANGEMENT = "roof_arrangement"
    THERMAL_CAP = "thermal_cap"
    RAW_FALLBACK = "raw_fallback"


class RoofType(StrEnum):
    NONE = "none"
    FLAT = "flat"
    SHED = "shed"
    GABLE = "gable"
    HIP = "hip"
    MANSARD = "mansard"
    PYRAMID = "pyramid"
    CROSS_GABLE = "cross_gable"
    COMPLEX = "complex"


class KneeWallKind(StrEnum):
    KNEE = "knee"
    DORMER_CHEEK = "dormer_cheek"
    DORMER_HEADER = "dormer_header"


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class Plane:
    a: float
    b: float
    c: float
    d: float


@dataclass(frozen=True, slots=True)
class Quad:
    corners: list[Vec3]


@dataclass(frozen=True, slots=True)
class HorizontalLid:
    corners: list[Vec3]


@dataclass(frozen=True, slots=True)
class Wall:
    corners: list[Vec3]
    extension_strip: list[Vec3] | None
    cutouts: list[Quad]
    locator_id: str


@dataclass(frozen=True, slots=True)
class Room:
    story: int
    floor: HorizontalLid
    walls: list[Wall]
    doors: list[Quad]
    windows: list[Quad]
    locator_id: str


@dataclass(frozen=True, slots=True)
class GapPiece:
    corners: list[Vec3]
    kind: GapKind
    scope: GapScope
    locator_id: str


@dataclass(frozen=True, slots=True)
class CeilingPiece:
    corners: list[Vec3]
    holes: list[list[Vec3]]
    plane: Plane
    source: CeilingSource
    arrangement_cell_id: str | None
    locator_id: str


@dataclass(frozen=True, slots=True)
class KneeWall:
    corners: list[Vec3]
    kind: KneeWallKind
    locator_id: str


@dataclass(frozen=True, slots=True)
class TierClassification:
    tier: int
    tier_label: str
    roof_type: RoofType
    n_stories: int
    n_rooms: int
    n_oblique: int
    n_flat: int
    has_half_height: bool
    has_gable: bool


@dataclass(frozen=True, slots=True)
class TierPayload:
    schema_version: Literal["1"]
    uuid: str
    address: str | None
    building_center: Vec3
    classification: TierClassification
    rooms: list[Room]
    gaps: list[GapPiece]
    ceiling: list[CeilingPiece]
    knee_walls: list[KneeWall]


def _to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: _to_jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    return value


def payload_to_dict(payload: TierPayload) -> dict[str, Any]:
    return _to_jsonable(payload)


def _is_optional(field_type: Any) -> bool:
    return get_origin(field_type) in (UnionType, __import__("typing").Union) and type(None) in get_args(field_type)


def _from_jsonable(field_type: Any, value: Any) -> Any:
    origin = get_origin(field_type)
    args = get_args(field_type)
    if origin is Literal:
        if value not in args:
            raise ValueError(f"expected one of {args}, got {value!r}")
        return value
    if _is_optional(field_type):
        if value is None:
            return None
        non_none = next(arg for arg in args if arg is not type(None))
        return _from_jsonable(non_none, value)
    if origin is list:
        (item_type,) = args
        return [_from_jsonable(item_type, item) for item in value]
    if isinstance(field_type, type) and issubclass(field_type, StrEnum):
        return field_type(value)
    if dataclasses.is_dataclass(field_type):
        hints = get_type_hints(field_type)
        return field_type(**{field.name: _from_jsonable(hints[field.name], value[field.name]) for field in dataclasses.fields(field_type)})
    return value


def payload_from_dict(data: dict[str, Any]) -> TierPayload:
    return _from_jsonable(TierPayload, data)
