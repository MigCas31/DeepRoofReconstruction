import pytest

from reconcile_tiers.roof.segments import collect_oblique_segments
from tests.reconcile_tiers.roof.helpers import make_gable_model, make_simple_slant_model


def test_collect_oblique_segments_filters_by_inclination_length_and_floor_above():
    model = make_gable_model()

    segments = collect_oblique_segments(model)

    assert len(segments) == 2
    assert {segment.room_index for segment in segments} == {0}
    assert all(segment.length >= 0.3 for segment in segments)
    assert all(segment.incl == pytest.approx(30.0, abs=1e-6) for segment in segments)

    blocked = collect_oblique_segments(model, has_floor_above=lambda _x, _z, _story: True)
    assert blocked == []


def test_collect_oblique_segments_respects_simple_slant_exclusion():
    model = make_simple_slant_model()

    assert collect_oblique_segments(model, exclude_room_indices={0}) == []
