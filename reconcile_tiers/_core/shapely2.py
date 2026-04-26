from __future__ import annotations

from collections.abc import Sequence
from numbers import Integral

from shapely import coverage_union_all
from shapely import make_valid as _make_valid
from shapely.strtree import STRtree


def make_valid(geometry):
    return _make_valid(geometry)


def make_valid_polygon(geometry):
    repaired = make_valid(geometry)
    if repaired.is_empty:
        return None
    if repaired.geom_type == "Polygon":
        return repaired
    polygon_parts = [
        part
        for part in getattr(repaired, "geoms", [])
        if part.geom_type == "Polygon" and part.area > 0.0
    ]
    if not polygon_parts:
        return None
    return max(polygon_parts, key=lambda part: part.area)


def coverage_union(geometries):
    return coverage_union_all(list(geometries))


def query_intersecting(geometries: Sequence, query_geometry) -> list:
    tree = STRtree(geometries)
    hits = tree.query(query_geometry)
    if len(hits) == 0:
        return []
    first = hits[0]
    if isinstance(first, Integral):
        return [geometries[int(idx)] for idx in hits if geometries[int(idx)].intersects(query_geometry)]
    return [geom for geom in hits if geom.intersects(query_geometry)]
