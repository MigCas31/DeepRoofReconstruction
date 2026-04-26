from __future__ import annotations

from reconcile_tiers._core.newell import polygon_area_3d
from reconcile_tiers.payload.schema import RoofType
from reconcile_tiers.roof.roof import ObliqueSurface

AZIMUTH_TOL_DEG = 30.0
INCL_TOL_DEG = 10.0
GABLE_AREA_FRACTION = 0.70
PITCH_BAND_GAP_DEG = 20.0
APEX_TOL_M = 0.25
LOW_PITCH_MANSARD_MIN_DEG = 10.0
LOW_PITCH_MANSARD_MAX_DEG = 30.0
HIP_GROUP_MIN_INCL_DEG = 35.0
SAME_AXIS_TOL_DEG = 12.0


def _angle_diff_deg(a: float, b: float) -> float:
    diff = (a - b) % 360.0
    return min(diff, 360.0 - diff)


def _axis_diff_deg(a: float, b: float) -> float:
    return _angle_diff_deg(a % 180.0, b % 180.0)


def _surface_area(surface: ObliqueSurface) -> float:
    return polygon_area_3d(surface.corners)


def _surface_meta(surface: ObliqueSurface) -> tuple[float, float, float]:
    return (
        float(surface.cluster.avg_azimuth) % 360.0,
        float(surface.cluster.avg_incl),
        _surface_area(surface),
    )


def _opposing_pairs(oblique: list[ObliqueSurface]) -> list[tuple[int, int, float]]:
    metas = [_surface_meta(surface) for surface in oblique]
    candidates: list[tuple[int, int, float]] = []
    for idx, (az_i, incl_i, area_i) in enumerate(metas):
        for jdx, (az_j, incl_j, area_j) in enumerate(metas[idx + 1 :], start=idx + 1):
            if abs(_angle_diff_deg(az_i, az_j) - 180.0) > AZIMUTH_TOL_DEG:
                continue
            if abs(incl_i - incl_j) > INCL_TOL_DEG:
                continue
            candidates.append((idx, jdx, area_i + area_j))
    candidates.sort(key=lambda item: -item[2])
    used: set[int] = set()
    pairs: list[tuple[int, int, float]] = []
    for idx, jdx, area in candidates:
        if idx in used or jdx in used:
            continue
        pairs.append((idx, jdx, area))
        used.update((idx, jdx))
    return pairs


def _pair_axis(surface: ObliqueSurface) -> float:
    return float(surface.cluster.avg_azimuth) % 180.0


def _pairs_perpendicular(oblique: list[ObliqueSurface], pair_a, pair_b) -> bool:
    axis_a = _pair_axis(oblique[pair_a[0]])
    axis_b = _pair_axis(oblique[pair_b[0]])
    return abs(_angle_diff_deg(axis_a, axis_b) - 90.0) <= AZIMUTH_TOL_DEG


def _stratifies_by_pitch(oblique: list[ObliqueSurface]) -> bool:
    inclinations = sorted(float(surface.cluster.avg_incl) for surface in oblique)
    if len(inclinations) < 4:
        return False
    gaps = [b - a for a, b in zip(inclinations, inclinations[1:])]
    return bool(gaps and max(gaps) >= PITCH_BAND_GAP_DEG)


def _same_axis_low_pitch_mansard(oblique: list[ObliqueSurface]) -> bool:
    if len(oblique) < 4:
        return False
    axes = [_pair_axis(surface) for surface in oblique]
    ref = axes[0]
    if any(_axis_diff_deg(axis, ref) > SAME_AXIS_TOL_DEG for axis in axes[1:]):
        return False
    inclinations = [float(surface.cluster.avg_incl) for surface in oblique]
    return all(LOW_PITCH_MANSARD_MIN_DEG <= incl <= LOW_PITCH_MANSARD_MAX_DEG for incl in inclinations)


def _has_perpendicular_hip_groups(oblique: list[ObliqueSurface]) -> bool:
    groups: list[list[ObliqueSurface]] = []
    for surface in oblique:
        if float(surface.cluster.avg_incl) < HIP_GROUP_MIN_INCL_DEG:
            continue
        axis = _pair_axis(surface)
        for group in groups:
            if _axis_diff_deg(axis, _pair_axis(group[0])) <= AZIMUTH_TOL_DEG:
                group.append(surface)
                break
        else:
            groups.append([surface])
    strong_axes = [_pair_axis(group[0]) for group in groups if len(group) >= 2]
    for idx, axis in enumerate(strong_axes):
        for other in strong_axes[idx + 1 :]:
            if abs(_axis_diff_deg(axis, other) - 90.0) <= AZIMUTH_TOL_DEG:
                return True
    return False


def _converges_to_apex(oblique: list[ObliqueSurface]) -> bool:
    high_points = []
    for surface in oblique:
        if not surface.corners:
            return False
        max_y = max(corner[1] for corner in surface.corners)
        candidates = [corner for corner in surface.corners if abs(corner[1] - max_y) <= APEX_TOL_M]
        if len(candidates) != 1:
            return False
        high_points.append(candidates[0])
    ref = high_points[0]
    for point in high_points[1:]:
        dx = float(point[0]) - float(ref[0])
        dy = float(point[1]) - float(ref[1])
        dz = float(point[2]) - float(ref[2])
        if (dx * dx + dy * dy + dz * dz) ** 0.5 > APEX_TOL_M:
            return False
    return True


def classify_oblique_roof(oblique: list[ObliqueSurface]) -> RoofType:
    if not oblique:
        return RoofType.NONE
    if len(oblique) == 1:
        return RoofType.SHED

    pairs = _opposing_pairs(oblique)
    total_area = sum(_surface_area(surface) for surface in oblique) or 0.0
    if len(oblique) == 2 and pairs and pairs[0][2] >= GABLE_AREA_FRACTION * total_area:
        return RoofType.GABLE

    if len(oblique) == 4 and _converges_to_apex(oblique):
        return RoofType.PYRAMID

    if len(oblique) == 4 and len(pairs) == 2:
        return RoofType.CROSS_GABLE if _pairs_perpendicular(oblique, pairs[0], pairs[1]) else RoofType.HIP

    if _same_axis_low_pitch_mansard(oblique):
        return RoofType.MANSARD

    if _has_perpendicular_hip_groups(oblique):
        return RoofType.HIP

    if len(oblique) >= 4 and _stratifies_by_pitch(oblique):
        return RoofType.MANSARD

    return RoofType.COMPLEX
