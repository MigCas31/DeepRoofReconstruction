from reconcile_tiers._core.plane import Plane
from reconcile_tiers.classify.roof_type import classify_oblique_roof
from reconcile_tiers.extract.building import extract_building_model
from reconcile_tiers.payload.schema import RoofType
from reconcile_tiers.roof.roof import ObliqueSurface, RoofCluster, build_roof_model


def _surface(azimuth, incl=35.0, area_scale=1.0, corners=None):
    if corners is None:
        corners = [[0, 0, 0], [area_scale, 0, 0], [area_scale, 1, 1], [0, 1, 1]]
    return ObliqueSurface(
        corners=corners,
        plane=Plane(a=0.0, b=1.0, c=0.0, d=0.0),
        cluster=RoofCluster(segments=[], avg_incl=incl, avg_azimuth=azimuth, ref_pt=[0, 0, 0]),
        dominant_story=0,
        ridge={},
    )


def test_roof_type_none_and_shed():
    assert classify_oblique_roof([]) == RoofType.NONE
    assert classify_oblique_roof([_surface(90)]) == RoofType.SHED


def test_roof_type_gable_from_dominant_opposing_pair():
    assert classify_oblique_roof([_surface(90), _surface(270)]) == RoofType.GABLE


def test_roof_type_cross_gable_from_perpendicular_opposing_pairs():
    roof = [_surface(0), _surface(180), _surface(90), _surface(270)]

    assert classify_oblique_roof(roof) == RoofType.CROSS_GABLE


def test_roof_type_hip_from_two_non_perpendicular_opposing_pairs():
    roof = [_surface(20), _surface(200), _surface(65), _surface(245)]

    assert classify_oblique_roof(roof) == RoofType.HIP


def test_roof_type_mansard_from_two_pitch_bands():
    roof = [_surface(0, 30), _surface(180, 31), _surface(90, 30), _surface(270, 31), _surface(45, 70), _surface(225, 70)]

    assert classify_oblique_roof(roof) == RoofType.MANSARD


def test_roof_type_pyramid_from_common_apex():
    apex = [0.0, 3.0, 0.0]
    roof = [
        _surface(20, corners=[[-1, 0, -1], [1, 0, -1], apex]),
        _surface(120, corners=[[1, 0, -1], [1, 0, 1], apex]),
        _surface(220, corners=[[1, 0, 1], [-1, 0, 1], apex]),
        _surface(320, corners=[[-1, 0, 1], [-1, 0, -1], apex]),
    ]

    assert classify_oblique_roof(roof) == RoofType.PYRAMID


def test_roof_type_complex_fallback():
    assert classify_oblique_roof([_surface(0), _surface(70), _surface(150)]) == RoofType.COMPLEX


def test_roof_type_matches_documented_hip_and_mansard_cohort_picks():
    hip_model = extract_building_model(
        "16784bad-2cd9-4f4c-bb26-60355981cfe2",
        "pipeline-outputs",
        ".scan-cache",
    )
    mansard_model = extract_building_model(
        "3297bc28-5d39-4358-bd2e-0f1183cae489",
        "pipeline-outputs",
        ".scan-cache",
    )

    assert classify_oblique_roof(build_roof_model(hip_model).oblique) == RoofType.HIP
    assert classify_oblique_roof(build_roof_model(mansard_model).oblique) == RoofType.MANSARD
