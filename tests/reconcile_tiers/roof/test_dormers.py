from reconcile_tiers.roof.clipping import clip_planes_to_footprint
from reconcile_tiers.roof.clustering import cluster_oblique_segments
from reconcile_tiers.roof.dormers import append_dormer_cutouts, detect_dormers
from reconcile_tiers.roof.footprint import build_building_footprint
from reconcile_tiers.roof.obliques import build_oblique_surfaces, story_floor_y
from reconcile_tiers.roof.planes import build_roof_planes
from reconcile_tiers.roof.segments import collect_oblique_segments
from tests.reconcile_tiers.roof.helpers import make_gable_model


def _obliques(model):
    footprint = build_building_footprint(model)
    planes = build_roof_planes(cluster_oblique_segments(collect_oblique_segments(model)), footprint)
    clipped = clip_planes_to_footprint(planes, footprint)
    return build_oblique_surfaces(clipped, story_floor_y(model))


def test_dormer_detection_builds_cutout_quad_and_attaches_to_parent_oblique():
    model = make_gable_model(include_dormer=True)
    obliques = _obliques(model)

    dormers = detect_dormers(model, obliques)
    append_dormer_cutouts(obliques, dormers)

    assert len(dormers) == 1
    assert dormers[0].front_wall_id == "dormer-front"
    assert len(dormers[0].cutout_quad) == 4
    assert len(dormers[0].cheek_quads) == 2
    assert len(dormers[0].header_quad) == 4
    assert obliques[0].cutout_holes == [dormers[0].cutout_quad]
