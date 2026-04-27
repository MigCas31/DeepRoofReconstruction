from reconcile_tiers.payload.schema import KneeWallKind
from reconcile_tiers.roof.roof import build_roof_model
from tests.reconcile_tiers.roof.helpers import make_gable_model


def test_build_roof_model_returns_stage_outputs_not_just_final_surfaces():
    roof = build_roof_model(make_gable_model(include_dormer=True))

    assert roof.simple_slant_room_indices == set()
    assert len(roof.segments) >= 2
    assert len(roof.clusters) == 1
    assert roof.footprint is not None
    assert len(roof.planes) == 1
    assert len(roof.clipped_planes) == 1
    assert len(roof.oblique) == 1
    assert len(roof.oblique_split) == 1
    assert len(roof.dormers) == 1
    assert roof.oblique[0].cutout_holes == [roof.dormers[0].cutout_quad]
    assert {surface.kind for surface in roof.thermal} >= {KneeWallKind.DORMER_CHEEK, KneeWallKind.DORMER_HEADER}
