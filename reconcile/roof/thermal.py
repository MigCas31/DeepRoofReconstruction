from __future__ import annotations

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid

from reconcile.extract.building import BuildingModel
from reconcile.payload.schema import KneeWallKind
from reconcile.roof.roof import Dormer, ObliqueSurface, ThermalSurface

BARRIER_REACH_M = 0.30
SURFACE_SUPPORT_TOLERANCE_M = 0.30
THERMAL_KINDS = frozenset(
    {KneeWallKind.KNEE, KneeWallKind.DORMER_CHEEK, KneeWallKind.DORMER_HEADER}
)


def _surface_support_geometry(surface: ObliqueSurface):
    if len(surface.corners) < 3:
        return None
    geom = Polygon([(float(p[0]), float(p[2])) for p in surface.corners])
    if not geom.is_valid:
        geom = make_valid(geom)
    if hasattr(geom, "geoms"):
        polygons = [
            part
            for part in geom.geoms
            if isinstance(part, Polygon) and part.area > 1e-9
        ]
        geom = unary_union(polygons) if polygons else None
    if geom is None or geom.is_empty or geom.area <= 1e-9:
        return None
    return geom


def _wall_top_supported_by_surface(
    top: list[list[float]], surface: ObliqueSurface
) -> bool:
    support = _surface_support_geometry(surface)
    if support is None:
        return False
    line = LineString([(float(p[0]), float(p[2])) for p in top])
    if line.length <= 1e-9:
        return False
    return bool(support.buffer(SURFACE_SUPPORT_TOLERANCE_M).covers(line))


def _knee_walls(
    model: BuildingModel, obliques: list[ObliqueSurface]
) -> list[ThermalSurface]:
    out: list[ThermalSurface] = []
    for room in model.rooms:
        for wall in room.walls_computed:
            if len(wall.corners) < 3:
                continue
            top = sorted(wall.corners, key=lambda p: p[1], reverse=True)[:2]
            if len(top) != 2:
                continue
            for surface in obliques:
                if surface.dominant_story != room.story:
                    continue
                if not _wall_top_supported_by_surface(top, surface):
                    continue
                lifted = []
                for p in top:
                    y = surface.plane.y_at(p[0], p[2])
                    if y is None:
                        lifted = []
                        break
                    lifted.append([p[0], y, p[2]])
                if len(lifted) != 2:
                    continue
                gaps = [lifted[idx][1] - top[idx][1] for idx in range(2)]
                if min(gaps) <= BARRIER_REACH_M:
                    continue
                out.append(
                    ThermalSurface(
                        corners=[top[0], top[1], lifted[1], lifted[0]],
                        kind=KneeWallKind.KNEE,
                        room_index=room.index,
                        source="wall_top_to_oblique",
                    )
                )
                break
    return out


def build_thermal_surfaces(
    model: BuildingModel, obliques: list[ObliqueSurface], dormers: list[Dormer]
) -> list[ThermalSurface]:
    surfaces = _knee_walls(model, obliques)
    for dormer in dormers:
        for cheek in dormer.cheek_quads:
            surfaces.append(
                ThermalSurface(
                    corners=cheek,
                    kind=KneeWallKind.DORMER_CHEEK,
                    room_index=dormer.room_index,
                    source="dormer",
                )
            )
        surfaces.append(
            ThermalSurface(
                corners=dormer.header_quad,
                kind=KneeWallKind.DORMER_HEADER,
                room_index=dormer.room_index,
                source="dormer",
            )
        )
    return surfaces
