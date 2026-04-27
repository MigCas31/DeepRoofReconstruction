import json
from collections import Counter
from pathlib import Path

import pytest

from reconcile.complexity_tiers import classify_building as legacy_classify_building
from reconcile_tiers.classify.tiers import TIER_LABELS, classify_building, detect_gable


def _building(stories: int, *, split_level: bool = False, rooms: list | None = None) -> dict:
    return {
        "uuid": "test-uuid",
        "stories_found": stories,
        "split_level": split_level,
        "rooms": rooms or [{"story": s, "floor_polygon": []} for s in range(stories)],
    }


def _roof(oblique: list | None = None, flat: list | None = None) -> dict:
    return {"roof_surfaces": {"oblique": oblique or [], "flat": flat or []}}


def _oblique(az: float | None, incl: float | None, area: float = 25.0) -> dict:
    size = area**0.5
    return {
        "cluster": {"avgAzimuth": az, "avgIncl": incl},
        "corners": [[0, 0, 0], [size, 0, 0], [size, 0, size], [0, 0, size]],
    }


def test_flat_storey_tiers_match_existing_labels():
    assert classify_building(_building(1), _roof())["tier_label"] == TIER_LABELS[1]
    assert classify_building(_building(2), _roof())["tier"] == 2
    assert classify_building(_building(3), _roof())["tier"] == 3


def test_half_height_and_slanted_room_tiers():
    assert classify_building(_building(2, split_level=True), _roof())["tier"] == 4
    assert classify_building(_building(1), _roof(oblique=[_oblique(0, 30)]))["tier"] == 5


def test_gable_and_mixed_gable_tiers():
    gable = [_oblique(0, 30), _oblique(180, 30)]

    assert classify_building(_building(2), _roof(oblique=gable))["tier"] == 6
    assert classify_building(_building(2), _roof(oblique=gable, flat=[{"story": 2}]))["tier"] == 7


def test_invalid_oblique_meta_does_not_dilute_gable_area_fraction():
    valid_a = _oblique(0, 30, area=10.0)
    valid_b = _oblique(180, 30, area=10.0)
    invalid_large = _oblique(None, 30, area=1000.0)

    assert detect_gable([valid_a, valid_b, invalid_large]) is True


def test_story_count_falls_back_to_room_indices():
    building = {"uuid": "x", "split_level": False, "rooms": [{"story": 0}, {"story": 1}]}

    result = classify_building(building, _roof())

    assert result["signals"]["n_stories"] == 2
    assert result["tier"] == 2


@pytest.mark.parametrize(
    "building,roof,expected_tier",
    [
        (_building(1), _roof(), 1),
        (_building(2), _roof(), 2),
        (_building(3), _roof(), 3),
        (_building(4), _roof(), 8),
        (_building(2, split_level=True), _roof(), 4),
        (_building(1), _roof(oblique=[_oblique(45, 20)]), 5),
        (_building(2), _roof(oblique=[_oblique(0, 30), _oblique(180, 30)]), 6),
        (_building(2), _roof(oblique=[_oblique(0, 30), _oblique(180, 30)], flat=[{"story": 1}]), 7),
        (_building(2), _roof(oblique=[_oblique(0, 30), _oblique(90, 30)]), 8),
        (_building(1), _roof(oblique=[_oblique(0, 5), _oblique(180, 5)]), 5),
        (_building(2), _roof(oblique=[_oblique(0, 30), _oblique(150, 30)]), 6),
        (_building(2), _roof(oblique=[_oblique(0, 30), _oblique(140, 30)]), 8),
        (_building(2), _roof(oblique=[_oblique(0, 30), _oblique(180, 45)]), 8),
        (_building(2), _roof(oblique=[_oblique(0, 30, area=10), _oblique(180, 30, area=10), _oblique(90, 30, area=20)]), 8),
        (_building(2), _roof(oblique=[_oblique(0, 30, area=10), _oblique(180, 30, area=10), _oblique(90, 30, area=5)]), 6),
        (_building(2), _roof(flat=[{"story": 0}, {"story": 1}]), 2),
        (_building(2), _roof(oblique=[_oblique(0, 30), _oblique(180, 30)], flat=[{"story": 0}]), 7),
        (_building(2), _roof(oblique=[_oblique(0, 30), _oblique(180, 30)], flat=[{"story": 2}]), 7),
        ({"uuid": "x", "split_level": False, "rooms": []}, _roof(), 8),
        ({"uuid": "x", "split_level": True, "rooms": [{"story": 0}, {"story": 1}]}, _roof(), 4),
        (_building(1), _roof(oblique=[_oblique(None, 30)]), 5),
        (_building(2), _roof(oblique=[_oblique(None, 30), _oblique(180, 30)]), 8),
        (_building(2), _roof(oblique=[_oblique(0, None), _oblique(180, 30)]), 8),
        (_building(2), _roof(oblique=[_oblique(350, 30), _oblique(170, 30)]), 6),
        (_building(2), _roof(oblique=[_oblique(10, 30), _oblique(190, 30), _oblique(90, 20)]), 8),
    ],
)
def test_ported_tier_classifier_cases(building, roof, expected_tier):
    assert classify_building(building, roof)["tier"] == expected_tier


def test_total_area_fix_does_not_change_committed_corpus_tier_counts():
    buildings = json.loads(Path("reconcile/buildings_3d.json").read_text())
    roofs = json.loads(Path("reconcile/roof_algorithms_py_results.json").read_text())

    legacy_counts = Counter()
    current_counts = Counter()
    drift = []
    for building in buildings:
        uuid = building["uuid"]
        legacy = legacy_classify_building(building, roofs.get(uuid))
        current = classify_building(building, roofs.get(uuid))
        legacy_counts[legacy["tier"]] += 1
        current_counts[current["tier"]] += 1
        if legacy["tier"] != current["tier"]:
            drift.append((uuid, legacy["tier"], current["tier"]))

    assert drift == []
    assert current_counts == legacy_counts == {1: 85, 2: 10, 4: 5, 5: 20, 6: 25, 7: 57, 8: 21}


@pytest.mark.parametrize(
    "uuid",
    [
        "c72ad855-9e52-46f1-886d-a9f37911521f",
        "f40dcc9f-b97b-4bef-8b40-ba011aabf0bd",
        "2ea3b759-e047-424c-8034-f8ee5b811fb4",
    ],
)
def test_cohort_tiers_match_current_legacy_classifier(uuid):
    buildings = {building["uuid"]: building for building in json.loads(Path("reconcile/buildings_3d.json").read_text())}
    roofs = json.loads(Path("reconcile/roof_algorithms_py_results.json").read_text())

    legacy = legacy_classify_building(buildings[uuid], roofs.get(uuid))
    current = classify_building(buildings[uuid], roofs.get(uuid))

    assert current == legacy
