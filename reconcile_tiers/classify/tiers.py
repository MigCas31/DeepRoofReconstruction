from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from reconcile_tiers._core.newell import polygon_area_3d

TIER_LABELS: dict[int, str] = {
    1: "1 storey · flat",
    2: "2 storeys · flat",
    3: "3 storeys · flat",
    4: "Multi-storey · half-height",
    5: "1 storey · slanted room",
    6: "Gable (ridge + eave)",
    7: "Mixed: gable + flat roof",
    8: "Other",
}

_GABLE_AZIMUTH_TOL_DEG = 30.0
_GABLE_INCL_TOL_DEG = 10.0
_GABLE_AREA_FRACTION = 0.70
_MIN_GABLE_INCL_DEG = 10.0


def _angle_diff_deg(a: float, b: float) -> float:
    diff = (a - b) % 360.0
    return min(diff, 360.0 - diff)


def _polygon_area_3d(corners: Iterable[Iterable[float]]) -> float:
    return polygon_area_3d([list(point) for point in corners])


def _oblique_meta(surface: dict[str, Any]) -> tuple[float | None, float | None, float]:
    cluster = surface.get("cluster") or {}
    az = cluster.get("avgAzimuth")
    incl = cluster.get("avgIncl")
    try:
        az = float(az) if az is not None else None
    except (TypeError, ValueError):
        az = None
    try:
        incl = float(incl) if incl is not None else None
    except (TypeError, ValueError):
        incl = None
    return az, incl, _polygon_area_3d(surface.get("corners") or [])


def detect_gable(oblique_surfaces: list[dict[str, Any]]) -> bool:
    metas = [_oblique_meta(surface) for surface in oblique_surfaces]
    valid = [
        (az, incl, area)
        for az, incl, area in metas
        if az is not None and incl is not None and incl >= _MIN_GABLE_INCL_DEG
    ]
    if len(valid) < 2:
        return False
    total_area = sum(area for _az, _incl, area in valid)
    if total_area <= 0.0:
        return False

    best_pair_area = 0.0
    for idx, (az_i, incl_i, area_i) in enumerate(valid):
        for az_j, incl_j, area_j in valid[idx + 1 :]:
            if abs(_angle_diff_deg(az_i, az_j) - 180.0) > _GABLE_AZIMUTH_TOL_DEG:
                continue
            if abs(incl_i - incl_j) > _GABLE_INCL_TOL_DEG:
                continue
            best_pair_area = max(best_pair_area, area_i + area_j)
    return best_pair_area >= _GABLE_AREA_FRACTION * total_area


def _n_stories(building: dict[str, Any]) -> int:
    raw = building.get("stories_found")
    if isinstance(raw, int) and raw > 0:
        return raw
    stories = set()
    for room in building.get("rooms") or []:
        try:
            stories.add(int(room.get("story")))
        except (TypeError, ValueError):
            continue
    return len(stories)


def _top_story(surfaces: list[dict[str, Any]]) -> int | None:
    stories = []
    for surface in surfaces:
        for key in ("story", "dominant_story"):
            raw = surface.get(key)
            if raw is None:
                continue
            try:
                stories.append(int(raw))
                break
            except (TypeError, ValueError):
                continue
    return max(stories) if stories else None


def _count_top_flat(flat: list[dict[str, Any]], oblique: list[dict[str, Any]]) -> int:
    if not flat:
        return 0
    top = _top_story(oblique)
    if top is None:
        top = _top_story(flat)
    if top is None:
        return len(flat)
    count = 0
    for surface in flat:
        try:
            if surface.get("story") is not None and int(surface["story"]) >= top:
                count += 1
        except (TypeError, ValueError):
            continue
    return count


def classify_building(building: dict[str, Any], roof: dict[str, Any] | None) -> dict[str, Any]:
    rooms = building.get("rooms") or []
    roof_surfaces = ((roof or {}).get("roof_surfaces") or {}) if roof else {}
    oblique = roof_surfaces.get("oblique") or []
    flat = roof_surfaces.get("flat") or []

    n_stories = _n_stories(building)
    n_oblique = len(oblique)
    n_flat = _count_top_flat(flat, oblique)
    has_half_height = bool(building.get("split_level"))
    has_gable = detect_gable(oblique) if n_oblique >= 2 else False

    if n_oblique == 0 and not has_half_height:
        if n_stories == 1:
            tier = 1
        elif n_stories == 2:
            tier = 2
        elif n_stories == 3:
            tier = 3
        else:
            tier = 8
    elif has_half_height and n_oblique == 0:
        tier = 4
    elif has_gable and n_flat == 0:
        tier = 6
    elif has_gable and n_flat >= 1:
        tier = 7
    elif n_stories == 1 and n_oblique >= 1 and not has_gable:
        tier = 5
    else:
        tier = 8

    return {
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "signals": {
            "n_stories": n_stories,
            "n_rooms": len(rooms),
            "n_oblique": n_oblique,
            "n_flat": n_flat,
            "has_half_height": has_half_height,
            "has_gable": has_gable,
        },
    }
