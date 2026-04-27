from __future__ import annotations

from dataclasses import replace

from reconcile.roof.geometry import (
    angle_diff_deg,
    circular_mean_deg,
    plane_normal_from_azimuth_inclination,
)
from reconcile.roof.roof import RoofCluster, RoofSegment

AZIMUTH_TOL_DEG = 30.0
INCL_TOL_DEG = 15.0
COPLANAR_TOL_M = 0.5
MIN_CLUSTER_SIZE = 2


def _midpoint_plane_residual(cluster: RoofCluster, segment: RoofSegment) -> float:
    nx, ny, nz = plane_normal_from_azimuth_inclination(cluster.avg_azimuth, cluster.avg_incl)
    denom = (nx * nx + ny * ny + nz * nz) ** 0.5
    if denom <= 1e-12:
        return float("inf")
    mid = segment.midpoint
    ref = cluster.ref_pt
    return abs((mid[0] - ref[0]) * nx + (mid[1] - ref[1]) * ny + (mid[2] - ref[2]) * nz) / denom


def _cluster_with(cl: RoofCluster, segment: RoofSegment) -> RoofCluster | None:
    if angle_diff_deg(segment.azimuth, cl.avg_azimuth) >= AZIMUTH_TOL_DEG:
        return None
    if abs(segment.incl - cl.avg_incl) >= INCL_TOL_DEG:
        return None
    new_segments = [*cl.segments, segment]
    if _midpoint_plane_residual(cl, segment) > COPLANAR_TOL_M:
        return None
    count = len(new_segments)
    return RoofCluster(
        segments=new_segments,
        avg_incl=sum(s.incl for s in new_segments) / count,
        avg_azimuth=circular_mean_deg(s.azimuth for s in new_segments),
        ref_pt=cl.ref_pt,
    )


def cluster_oblique_segments(segments: list[RoofSegment]) -> list[RoofCluster]:
    clusters: list[RoofCluster] = []
    for segment in segments:
        assigned = False
        for idx, cluster in enumerate(clusters):
            updated = _cluster_with(cluster, segment)
            if updated is None:
                continue
            clusters[idx] = updated
            assigned = True
            break
        if not assigned:
            clusters.append(
                RoofCluster(
                    segments=[segment],
                    avg_incl=segment.incl,
                    avg_azimuth=segment.azimuth % 360.0,
                    ref_pt=segment.midpoint,
                )
            )
    return [replace(cluster, avg_azimuth=cluster.avg_azimuth % 360.0) for cluster in clusters if len(cluster.segments) >= MIN_CLUSTER_SIZE]
