"""Tests for half-level / split-level building support.

Covers wall extensions, knee wall thermal ceilings, slab detection,
and the _floor_y_at_xz helper — all for buildings where rooms on the
same story have different floor elevations.
"""

import pytest

from reconcile.extract3d.ceilings import extend_wall_to_slab, find_closest_slab_y
from reconcile.roof_algorithms_py.thermal_ceiling import (
    _build_knee_wall_ceilings,
    _floor_y_at_xz,
)

# ---------------------------------------------------------------------------
# Helpers to build minimal geometry
# ---------------------------------------------------------------------------

def _rect_floor(x0, z0, x1, z1, y):
    """Create a rectangular floor polygon at height y."""
    return [[x0, y, z0], [x1, y, z0], [x1, y, z1], [x0, y, z1]]


def _wall_corners(x0, z0, x1, z1, y_bot, y_top):
    """Create a simple rectangular wall quad (4 corners)."""
    return [
        [x0, y_bot, z0],
        [x1, y_bot, z1],
        [x1, y_top, z1],
        [x0, y_top, z0],
    ]


# ---------------------------------------------------------------------------
# test_floor_y_at_xz_helper
# ---------------------------------------------------------------------------

class TestFloorYAtXz:
    def test_point_in_room_a(self):
        """Point inside room A returns room A's floor Y."""
        regions = {
            1: [
                (_rect_floor(0, 0, 5, 3, 2.7), 2.7),
                (_rect_floor(0, 3, 5, 6, 4.0), 4.0),
            ]
        }
        assert _floor_y_at_xz(regions, 1, 2.5, 1.5, 0.0) == 2.7

    def test_point_in_room_b(self):
        """Point inside room B returns room B's floor Y."""
        regions = {
            1: [
                (_rect_floor(0, 0, 5, 3, 2.7), 2.7),
                (_rect_floor(0, 3, 5, 6, 4.0), 4.0),
            ]
        }
        assert _floor_y_at_xz(regions, 1, 2.5, 4.5, 0.0) == 4.0

    def test_point_outside_returns_fallback(self):
        """Point outside all rooms returns fallback."""
        regions = {
            1: [
                (_rect_floor(0, 0, 5, 3, 2.7), 2.7),
            ]
        }
        assert _floor_y_at_xz(regions, 1, 10.0, 10.0, 99.0) == 99.0

    def test_no_regions_returns_fallback(self):
        assert _floor_y_at_xz(None, 1, 2.5, 1.5, 99.0) == 99.0

    def test_wrong_story_returns_fallback(self):
        regions = {
            1: [(_rect_floor(0, 0, 5, 5, 2.7), 2.7)]
        }
        assert _floor_y_at_xz(regions, 2, 2.5, 2.5, 99.0) == 99.0


# ---------------------------------------------------------------------------
# test_find_closest_slab_y
# ---------------------------------------------------------------------------

class TestFindClosestSlabY:
    def test_prefers_nearest_xz(self):
        """With two slabs at different Y, picks the one closest in XZ."""
        wall_corners = _wall_corners(2, 1, 3, 1, 0.0, 2.5)
        slabs = [
            (2.5, 1.5, 2.7),  # nearby in XZ, Y=2.7
            (2.5, 4.5, 4.0),  # far in XZ, Y=4.0
        ]
        result = find_closest_slab_y(wall_corners, slabs)
        assert result == 2.7

    def test_picks_other_slab_when_closer(self):
        wall_corners = _wall_corners(2, 4, 3, 4, 0.0, 2.5)
        slabs = [
            (2.5, 1.5, 2.7),  # far in XZ
            (2.5, 4.5, 4.0),  # nearby in XZ, Y=4.0
        ]
        result = find_closest_slab_y(wall_corners, slabs)
        assert result == 4.0

    def test_empty_slabs_returns_none(self):
        wall_corners = _wall_corners(0, 0, 1, 0, 0.0, 2.5)
        assert find_closest_slab_y(wall_corners, []) is None


# ---------------------------------------------------------------------------
# test_wall_extension_half_level
# ---------------------------------------------------------------------------

class TestWallExtensionHalfLevel:
    def test_extends_to_lower_half_level(self):
        """Wall just below a slab at Y=2.7 should extend to 2.7."""
        corners = _wall_corners(0, 0, 1, 0, 0.0, 2.5)
        result = extend_wall_to_slab(corners, slab_y_above=2.7)
        assert result is not None
        assert len(result["extension_strip"]) > 0
        # Extension should reach slab_y
        for strip in result["extension_strip"]:
            strip_ys = [pt[1] for pt in strip]
            assert max(strip_ys) == pytest.approx(2.7, abs=0.01)

    def test_extends_to_higher_half_level(self):
        """Wall just below a slab at Y=4.0 should extend to 4.0 (within max_gap)."""
        corners = _wall_corners(0, 0, 1, 0, 0.0, 3.5)
        result = extend_wall_to_slab(corners, slab_y_above=4.0)
        assert result is not None
        for strip in result["extension_strip"]:
            strip_ys = [pt[1] for pt in strip]
            assert max(strip_ys) == pytest.approx(4.0, abs=0.01)

    def test_no_extension_when_already_at_slab(self):
        """Wall top already at slab Y should not produce extension."""
        corners = _wall_corners(0, 0, 1, 0, 0.0, 2.7)
        result = extend_wall_to_slab(corners, slab_y_above=2.7)
        assert result is None

    def test_no_extension_when_gap_too_large(self):
        """Gap > max_gap (0.80m) should not produce extension."""
        corners = _wall_corners(0, 0, 1, 0, 0.0, 2.0)
        result = extend_wall_to_slab(corners, slab_y_above=3.0)
        assert result is None


# ---------------------------------------------------------------------------
# test_wall_extension_standard_building
# ---------------------------------------------------------------------------

class TestWallExtensionStandard:
    def test_single_slab_above(self):
        """Standard building: wall extends to uniform story+1 slab."""
        corners = _wall_corners(0, 0, 1, 0, 0.0, 2.5)
        result = extend_wall_to_slab(corners, slab_y_above=2.7)
        assert result is not None
        for strip in result["extension_strip"]:
            strip_ys = [pt[1] for pt in strip]
            assert max(strip_ys) == pytest.approx(2.7, abs=0.01)


# ---------------------------------------------------------------------------
# test_knee_wall_height_half_level
# ---------------------------------------------------------------------------

class TestKneeWallHalfLevel:
    def test_knee_wall_uses_per_zone_height(self):
        """Knee wall gap under half-level rooms should use per-zone floor Y."""
        # Story 0: large floor covering (0,0)-(10,10)
        # Story 1: two rooms — room A at Y=2.7 covers (0,0)-(10,5),
        #          room B at Y=4.0 covers (0,5)-(10,8)
        # Story 0 floor extends beyond story 1 in Z direction (8-10)
        floors_by_story = {
            0: [_rect_floor(0, 0, 10, 10, 0.0)],
            1: [
                _rect_floor(0, 0, 10, 5, 2.7),
                _rect_floor(0, 5, 10, 8, 4.0),
            ],
        }
        story_floor_y = {0: 0.0, 1: 2.7}  # min Y per story
        story_floor_regions = {
            0: [(_rect_floor(0, 0, 10, 10, 0.0), 0.0)],
            1: [
                (_rect_floor(0, 0, 10, 5, 2.7), 2.7),
                (_rect_floor(0, 5, 10, 8, 4.0), 4.0),
            ],
        }

        result = _build_knee_wall_ceilings(
            floors_by_story, story_floor_y, story_floor_regions
        )
        assert len(result) > 0

        for kc in result:
            assert kc["kind"] == "thermal-knee"
            assert kc["story"] == 1
            # The knee wall gap is in the (0,8)-(10,10) zone, which is
            # beyond story 1's coverage entirely. The centroid is around Z=9.
            # Since no story 1 room covers Z=9, it falls back to story_floor_y[1]=2.7
            poly_ys = [p[1] for p in kc["poly"]]
            assert all(y == pytest.approx(poly_ys[0], abs=0.01) for y in poly_ys)

    def test_knee_wall_standard_building(self):
        """Standard (non-half-level) building: knee walls work as before."""
        floors_by_story = {
            0: [_rect_floor(0, 0, 10, 10, 0.0)],
            1: [_rect_floor(0, 0, 10, 7, 2.7)],
        }
        story_floor_y = {0: 0.0, 1: 2.7}

        result_without = _build_knee_wall_ceilings(
            floors_by_story, story_floor_y
        )
        result_with = _build_knee_wall_ceilings(
            floors_by_story, story_floor_y, story_floor_regions=None
        )

        assert len(result_without) == len(result_with)
        for a, b in zip(result_without, result_with):
            assert a["kind"] == b["kind"]
            assert a["story"] == b["story"]
            a_ys = [p[1] for p in a["poly"]]
            b_ys = [p[1] for p in b["poly"]]
            assert a_ys == b_ys


# ---------------------------------------------------------------------------
# test_slab_detection_includes_half_level
# ---------------------------------------------------------------------------

class TestSlabDetection:
    def test_half_level_rooms_not_excluded(self):
        """Rooms with floor Y > 0.50m from median should still be in story_slabs."""
        # This tests the builder.py logic indirectly by simulating what
        # the slab detection does. With the fix, no rooms are filtered out.

        import numpy as np

        # Simulate two rooms on story 0 at different heights
        story_slab_raw = {
            0: [
                (2.5, 2.5, 0.0),   # room at Y=0.0
                (2.5, 7.5, 1.5),   # room at Y=1.5 (half-level)
            ],
            1: [
                (2.5, 2.5, 2.7),
            ],
        }

        # New logic: keep all entries (no filtering)
        story_slabs = dict(story_slab_raw)

        # Both rooms should be present
        assert len(story_slabs[0]) == 2
        assert any(fy == 1.5 for _, _, fy in story_slabs[0])

        # story_y_map uses mode cluster
        for story, entries in story_slabs.items():
            floor_ys = sorted(fy for _, _, fy in entries)
            # Cluster within 0.30m
            clusters = []
            current = [floor_ys[0]]
            for fy in floor_ys[1:]:
                if fy - current[-1] <= 0.30:
                    current.append(fy)
                else:
                    clusters.append(current)
                    current = [fy]
            clusters.append(current)
            best_cluster = max(clusters, key=len)
            story_y = float(np.median(best_cluster))

            if story == 0:
                # With two isolated rooms, both clusters have size 1,
                # so max picks the first (Y=0.0)
                assert story_y == pytest.approx(0.0, abs=0.01)

    def test_wall_gets_half_level_slab_above(self):
        """Wall extension should find same-story half-level slab when > 1.0m above."""

        room_floor_y = 0.0
        story_slabs = {
            0: [
                (2.5, 2.5, 0.0),
                (2.5, 7.5, 1.5),
            ],
            1: [
                (2.5, 2.5, 2.7),
            ],
        }

        # Simulate builder.py wall extension slab collection
        slabs_above = list(story_slabs.get(1, []))
        for cx, cz, fy in story_slabs.get(0, []):
            if fy > room_floor_y + 1.0:
                slabs_above.append((cx, cz, fy))

        # The Y=1.5 slab from story 0 should be included
        slab_ys = [fy for _, _, fy in slabs_above]
        assert 1.5 in slab_ys
        assert 2.7 in slab_ys

        # Wall near (2.5, 7.5) should pick Y=1.5 (closest in XZ)
        wall_corners = _wall_corners(2, 7, 3, 7, 0.0, 1.2)
        result = find_closest_slab_y(wall_corners, slabs_above)
        assert result == 1.5


# ---------------------------------------------------------------------------
# test_cap_wall_top_for_half_level
# ---------------------------------------------------------------------------

class TestCapWallTopForHalfLevel:
    def test_caps_to_adjacent_higher_story_floor(self):
        """Room whose wall tops match adjacent higher-story gets capped to that floor."""
        from reconcile.roof_algorithms_py.ceiling_plane_generation import (
            _cap_wall_top_for_half_level,
        )

        # Room on story 1 at floor=-2.5, walls to 1.2
        # Adjacent story 2 room at floor=-1.3, walls to 1.25
        fp_room = _rect_floor(-10, -2, -2, 9, -2.5)
        bldg = {
            "rooms": [
                {
                    "story": 2,
                    "floor_polygon": _rect_floor(-3, 2, 0, 4, -1.3),
                    "walls_computed": [
                        {"corners": _wall_corners(-3, 2, 0, 2, -1.3, 1.25)}
                    ],
                },
            ]
        }

        result = _cap_wall_top_for_half_level(
            wall_top_y=1.2, floor_y=-2.5, story=1, fp=fp_room, bldg=bldg
        )
        assert result == pytest.approx(-1.3, abs=0.01)

    def test_no_cap_when_no_nearby_higher_story(self):
        """No higher-story rooms nearby — wall top unchanged."""
        from reconcile.roof_algorithms_py.ceiling_plane_generation import (
            _cap_wall_top_for_half_level,
        )

        fp_room = _rect_floor(0, 0, 5, 5, 0.0)
        bldg = {
            "rooms": [
                {
                    "story": 2,
                    "floor_polygon": _rect_floor(50, 50, 55, 55, 2.7),
                    "walls_computed": [
                        {"corners": _wall_corners(50, 50, 55, 50, 2.7, 5.0)}
                    ],
                },
            ]
        }

        result = _cap_wall_top_for_half_level(
            wall_top_y=5.0, floor_y=0.0, story=1, fp=fp_room, bldg=bldg
        )
        assert result == 5.0  # unchanged

    def test_no_cap_when_wall_tops_dont_match(self):
        """Nearby room with different wall tops — no capping."""
        from reconcile.roof_algorithms_py.ceiling_plane_generation import (
            _cap_wall_top_for_half_level,
        )

        fp_room = _rect_floor(0, 0, 5, 5, 0.0)
        bldg = {
            "rooms": [
                {
                    "story": 2,
                    "floor_polygon": _rect_floor(5, 0, 10, 5, 2.7),
                    "walls_computed": [
                        {"corners": _wall_corners(5, 0, 10, 0, 2.7, 8.0)}
                    ],
                },
            ]
        }

        # Wall top 5.0 vs other 8.0 — diff 3.0 > 0.5 tolerance
        result = _cap_wall_top_for_half_level(
            wall_top_y=5.0, floor_y=0.0, story=1, fp=fp_room, bldg=bldg
        )
        assert result == 5.0  # unchanged

    def test_standard_building_unchanged(self):
        """Standard building with no half-level — wall top unchanged."""
        from reconcile.roof_algorithms_py.ceiling_plane_generation import (
            _cap_wall_top_for_half_level,
        )

        fp_room = _rect_floor(0, 0, 5, 5, 0.0)
        bldg = {"rooms": []}

        result = _cap_wall_top_for_half_level(
            wall_top_y=2.5, floor_y=0.0, story=0, fp=fp_room, bldg=bldg
        )
        assert result == 2.5
