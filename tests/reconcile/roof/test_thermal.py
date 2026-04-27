from reconcile_tiers._core.plane import Plane
from reconcile_tiers.extract.building import BuildingModel, ExtractedRoom
from reconcile_tiers.payload.schema import KneeWallKind
from reconcile_tiers.roof.clipping import clip_planes_to_footprint
from reconcile_tiers.roof.clustering import cluster_oblique_segments
from reconcile_tiers.roof.dormers import append_dormer_cutouts, detect_dormers
from reconcile_tiers.roof.footprint import build_building_footprint
from reconcile_tiers.roof.obliques import build_oblique_surfaces, story_floor_y
from reconcile_tiers.roof.planes import build_roof_planes
from reconcile_tiers.roof.roof import ObliqueSurface, RoofCluster
from reconcile_tiers.roof.segments import collect_oblique_segments
from reconcile_tiers.roof.thermal import THERMAL_KINDS, build_thermal_surfaces
from tests.reconcile_tiers.roof.helpers import _wall, make_gable_model


def test_thermal_surfaces_emit_only_knee_cheek_and_header_not_caps():
    model = make_gable_model(include_dormer=True)
    footprint = build_building_footprint(model)
    planes = build_roof_planes(
        cluster_oblique_segments(collect_oblique_segments(model)), footprint
    )
    clipped = clip_planes_to_footprint(planes, footprint)
    obliques = build_oblique_surfaces(clipped, story_floor_y(model))
    dormers = detect_dormers(model, obliques)
    append_dormer_cutouts(obliques, dormers)

    thermal = build_thermal_surfaces(model, obliques, dormers)
    kinds = {surface.kind for surface in thermal}

    assert kinds <= THERMAL_KINDS
    assert KneeWallKind.DORMER_CHEEK in kinds
    assert KneeWallKind.DORMER_HEADER in kinds
    assert all("cap" not in surface.kind.value for surface in thermal)


def test_thermal_knee_wall_requires_wall_top_under_oblique_surface_support():
    wall = _wall(
        "wall-outside-roof-face",
        [
            [10.0, 0.0, 0.0],
            [10.0, 0.0, 2.0],
            [10.0, 1.0, 2.0],
            [10.0, 1.0, 0.0],
        ],
    )
    room = ExtractedRoom(
        index=0,
        story=0,
        floor_polygon=[
            [9.0, 0.0, -1.0],
            [11.0, 0.0, -1.0],
            [11.0, 0.0, 3.0],
            [9.0, 0.0, 3.0],
        ],
        walls_merged=[wall],
        walls_computed=[wall],
        doors=[],
        windows=[],
        openings=[],
        storages=[],
        raw_ceiling_planes=[],
        raw_ceiling_source=None,
        ceiling_polygon=[],
        ceiling_type=None,
        ceiling_eave_height=None,
        ceiling_ridge_height=None,
    )
    model = BuildingModel("synthetic-offset", None, 1, False, [room], 1, 1)
    cluster = RoofCluster(
        segments=[], avg_incl=15.0, avg_azimuth=270.0, ref_pt=[0.0, 2.0, 0.0]
    )
    nearby_oblique = ObliqueSurface(
        corners=[
            [0.0, 2.0, 0.0],
            [2.0, 2.4, 0.0],
            [2.0, 2.4, 2.0],
            [0.0, 2.0, 2.0],
        ],
        plane=Plane(a=-0.2, b=1.0, c=0.0, d=2.0),
        cluster=cluster,
        dominant_story=0,
        ridge={},
    )

    assert build_thermal_surfaces(model, [nearby_oblique], dormers=[]) == []
