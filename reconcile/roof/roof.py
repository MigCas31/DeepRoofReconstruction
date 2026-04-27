from __future__ import annotations

from dataclasses import dataclass, field

from reconcile._core.plane import Plane
from reconcile.extract.building import BuildingModel
from reconcile.payload.schema import KneeWallKind


@dataclass(frozen=True, slots=True)
class RoofSegment:
    a: list[float]
    b: list[float]
    incl: float
    azimuth: float
    length: float
    story: int
    room_index: int
    wall_id: str | None = None

    @property
    def midpoint(self) -> list[float]:
        return [
            (self.a[0] + self.b[0]) / 2.0,
            (self.a[1] + self.b[1]) / 2.0,
            (self.a[2] + self.b[2]) / 2.0,
        ]


@dataclass(frozen=True, slots=True)
class RoofCluster:
    segments: list[RoofSegment]
    avg_incl: float
    avg_azimuth: float
    ref_pt: list[float]

    @property
    def dominant_story(self) -> int:
        counts: dict[int, int] = {}
        for segment in self.segments:
            counts[segment.story] = counts.get(segment.story, 0) + 1
        return max(counts, key=lambda story: (counts[story], story))


@dataclass(frozen=True, slots=True)
class Footprint:
    polygon_xz: list[tuple[float, float]]
    top_story: int
    area: float


@dataclass(frozen=True, slots=True)
class RoofPlaneCandidate:
    cluster: RoofCluster
    plane: Plane
    polygon_xz: list[tuple[float, float]]
    ridge_span: float
    dominant_story: int


@dataclass(frozen=True, slots=True)
class ClippedRoofPlane:
    candidate: RoofPlaneCandidate
    polygon_xz: list[tuple[float, float]]
    max_y: float | None = None


@dataclass(slots=True)
class ObliqueSurface:
    corners: list[list[float]]
    plane: Plane
    cluster: RoofCluster
    dominant_story: int
    ridge: dict[str, float]
    cutout_holes: list[list[list[float]]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FlatSurface:
    corners: list[list[float]]
    story: int
    dominant_story: int
    source: str


@dataclass(frozen=True, slots=True)
class SplitObliqueSurface:
    corners: list[list[float]]
    plane: Plane
    arrangement_cell_id: str
    source_oblique_index: int


@dataclass(frozen=True, slots=True)
class Dormer:
    roof_surface_index: int
    room_index: int
    front_wall_id: str | None
    cutout_quad: list[list[float]]
    cheek_quads: list[list[list[float]]]
    header_quad: list[list[float]]


@dataclass(frozen=True, slots=True)
class ThermalSurface:
    corners: list[list[float]]
    kind: KneeWallKind
    room_index: int | None
    source: str


@dataclass(frozen=True, slots=True)
class RoofModel:
    simple_slant_room_indices: set[int]
    segments: list[RoofSegment]
    clusters: list[RoofCluster]
    footprint: Footprint | None
    planes: list[RoofPlaneCandidate]
    clipped_planes: list[ClippedRoofPlane]
    oblique: list[ObliqueSurface]
    flat: list[FlatSurface]
    oblique_split: list[SplitObliqueSurface]
    dormers: list[Dormer]
    thermal: list[ThermalSurface]


def build_roof_model(model: BuildingModel) -> RoofModel:
    from reconcile.roof.arrangement import split_oblique_surfaces
    from reconcile.roof.clipping import clip_planes_to_footprint
    from reconcile.roof.clustering import cluster_oblique_segments
    from reconcile.roof.dormers import append_dormer_cutouts, detect_dormers
    from reconcile.roof.flats import build_flat_surfaces
    from reconcile.roof.footprint import build_building_footprint
    from reconcile.roof.obliques import (
        build_oblique_surfaces,
        build_raw_oblique_surfaces,
        story_floor_y,
    )
    from reconcile.roof.planes import build_roof_planes
    from reconcile.roof.segments import collect_oblique_segments
    from reconcile.roof.simple_slant import (
        build_simple_slant_surfaces,
        detect_simple_slant_rooms,
    )
    from reconcile.roof.thermal import build_thermal_surfaces

    simple_slants = detect_simple_slant_rooms(model)
    segments = collect_oblique_segments(model, exclude_room_indices=simple_slants)
    clusters = cluster_oblique_segments(segments)
    footprint = build_building_footprint(model)
    planes = build_roof_planes(clusters, footprint) if footprint is not None else []
    clipped = clip_planes_to_footprint(planes, footprint, model) if footprint is not None else []
    floors = story_floor_y(model)
    oblique = build_oblique_surfaces(clipped, floors)
    oblique.extend(build_simple_slant_surfaces(model, simple_slants))
    oblique.extend(build_raw_oblique_surfaces(model, oblique))
    flat = build_flat_surfaces(model)
    split = split_oblique_surfaces(oblique, model)
    dormers = detect_dormers(model, oblique)
    append_dormer_cutouts(oblique, dormers)
    thermal = build_thermal_surfaces(model, oblique, dormers)
    return RoofModel(
        simple_slant_room_indices=simple_slants,
        segments=segments,
        clusters=clusters,
        footprint=footprint,
        planes=planes,
        clipped_planes=clipped,
        oblique=oblique,
        flat=flat,
        oblique_split=split,
        dormers=dormers,
        thermal=thermal,
    )
