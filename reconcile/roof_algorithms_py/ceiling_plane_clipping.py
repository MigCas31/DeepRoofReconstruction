from __future__ import annotations

from .ceiling_clipping_caps import compute_plane_height_caps
from .ceiling_clipping_initial import build_initial_plane_clips
from .ceiling_clipping_opposing import apply_lower_envelope_cuts


def clip_ceiling_planes(
    *,
    bldg: dict,
    ceiling_planes: list,
    building_footprint: list,
    exposed_rooms: list,
    all_rooms: list[dict] | None = None,
    top_story: int,
    all_stories: list,
    floors_by_story: dict,
    point_in_poly_xz,
    point_in_poly_2d,
    graph=None,
):
    plane_clipped = build_initial_plane_clips(
        ceiling_planes=ceiling_planes,
        building_footprint=building_footprint,
        exposed_rooms=exposed_rooms,
        all_rooms=all_rooms,
    )

    plane_max_y = compute_plane_height_caps(
        bldg=bldg,
        ceiling_planes=ceiling_planes,
        plane_clipped=plane_clipped,
        top_story=top_story,
        all_stories=all_stories,
        floors_by_story=floors_by_story,
        point_in_poly_xz=point_in_poly_xz,
        point_in_poly_2d=point_in_poly_2d,
        graph=graph,
    )

    apply_lower_envelope_cuts(
        ceiling_planes=ceiling_planes,
        plane_clipped=plane_clipped,
    )

    return {
        "plane_clipped": plane_clipped,
        "plane_max_y": plane_max_y,
        "junction_patches": [],
        "l_junctions": [],
    }
