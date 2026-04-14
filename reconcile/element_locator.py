"""Backend resolver for shareable viewer element IDs.

Element IDs use the format:
<building_uuid>::<kind>::<id>
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedElementId:
    """Parsed viewer element locator token."""

    building_uuid: str
    kind: str
    element_id: str


def parse_element_id(token: str) -> ParsedElementId:
    """Parse a shareable element token.

    Expected format: ``building_uuid::kind::id``.
    """
    parts = token.strip().split("::", 2)
    if len(parts) != 3 or not all(parts):
        raise ValueError(
            "Invalid element ID. Expected format: <building_uuid>::<kind>::<id>"
        )
    return ParsedElementId(
        building_uuid=parts[0],
        kind=parts[1],
        element_id=parts[2],
    )


def _iter_room_elements(building: dict, room_key: str):
    for room_index, room in enumerate(building.get("rooms", [])):
        story = room.get("story")
        for element_index, element in enumerate(room.get(room_key, [])):
            yield room_index, story, element_index, element


def _find_in_room_collection(
    building: dict, room_key: str, element_id: str
) -> dict | None:
    for room_index, story, element_index, element in _iter_room_elements(
        building, room_key
    ):
        if str(element.get("id", "")) == element_id:
            return {
                "json_path": f"rooms[{room_index}].{room_key}[{element_index}]",
                "room_index": room_index,
                "story": story,
                "source": element.get("source"),
                "corners_count": len(element.get("corners", [])),
                "element": element,
            }
    return None


def _find_in_building_collection(
    building: dict, collection_key: str, element_id: str
) -> dict | None:
    for index, element in enumerate(building.get(collection_key, [])):
        candidate_id = element.get("id")
        if candidate_id is None:
            candidate_id = f"{element.get('type', '')}:{index}"
        if str(candidate_id) == element_id:
            return {
                "json_path": f"{collection_key}[{index}]",
                "story": element.get("story"),
                "source": element.get("source") or element.get("confidence"),
                "corners_count": len(
                    element.get("corners", [])
                    or element.get("element_corners", [])
                    or element.get("wall_corners", [])
                ),
                "element": element,
            }
    return None


def find_element(buildings: list[dict], token: str) -> dict:
    """Resolve a viewer token to an element in buildings_3d-like data."""
    parsed = parse_element_id(token)
    building = next(
        (b for b in buildings if b.get("uuid") == parsed.building_uuid),
        None,
    )
    if building is None:
        raise LookupError(f"Building not found: {parsed.building_uuid}")

    room_kind_to_key = {
        "wall-merged": "walls_merged",
        "wall-computed": "walls_computed",
        "wall-extension": "walls_computed",
        "door": "doors",
        "window": "windows",
        "wall-clipped-original": "walls_computed",
    }
    building_kind_to_key = {
        "gap-cross-story": "cross_floor_gaps",
        "gap-within-story": "cross_floor_gaps",
        "wall-stitch": "stitch_walls",
        "gap-wall": "gap_walls",
        "exterior-gap-element": "exterior_gap_indicators",
        "exterior-gap-wall": "exterior_gap_indicators",
        "gap-closure": "gap_closures",
    }
    roof_kind_to_path: dict[str, tuple[str, str]] = {
        "roof-oblique": ("roof_surfaces", "oblique"),
        "roof-flat": ("roof_surfaces", "flat"),
        "ceiling-flat": ("ceiling", "flat"),
        "ceiling-simple-slant": ("ceiling", "simple_slant"),
    }

    details: dict | None = None
    if parsed.kind == "floor" or parsed.kind == "floor-overlap":
        try:
            story_str, room_index_str = parsed.element_id.split(":", 1)
            room_index = int(room_index_str)
            room = building.get("rooms", [])[room_index]
            key = (
                "floor_overlap_region"
                if parsed.kind == "floor-overlap"
                else "floor_polygon"
            )
            corners = room.get(key, [])
            details = {
                "json_path": f"rooms[{room_index}].{key}",
                "room_index": room_index,
                "story": int(story_str),
                "source": key,
                "corners_count": len(corners),
                "element": {"id": parsed.element_id, "corners": corners},
            }
        except (ValueError, IndexError, KeyError):
            details = None
    elif parsed.kind in room_kind_to_key:
        details = _find_in_room_collection(
            building, room_kind_to_key[parsed.kind], parsed.element_id
        )
    elif parsed.kind in building_kind_to_key:
        details = _find_in_building_collection(
            building, building_kind_to_key[parsed.kind], parsed.element_id
        )
    elif parsed.kind in roof_kind_to_path:
        section, subsection = roof_kind_to_path[parsed.kind]
        try:
            # ID format: "<sub_kind>:<index>" e.g. "oblique:0"
            _, idx_str = parsed.element_id.rsplit(":", 1)
            idx = int(idx_str)
            items = building.get(section, {}).get(subsection, [])
            element = items[idx]
            corners = element.get("corners") or element.get("poly", [])
            details = {
                "json_path": f"{section}.{subsection}[{idx}]",
                "room_index": None,
                "story": element.get("story") or element.get("dominant_story"),
                "source": parsed.kind,
                "corners_count": len(corners),
                "element": element,
            }
        except (ValueError, IndexError, KeyError):
            details = None

    elif parsed.kind in ("dormer-cheek", "dormer-header"):
        try:
            parts = parsed.element_id.split(":")
            dormer_idx = int(parts[1])
            dormers = building.get("dormers", [])
            dormer = dormers[dormer_idx]
            if parsed.kind == "dormer-cheek":
                cheek_idx = int(parts[2])
                element = dormer["cheeks"][cheek_idx]
            else:
                element = dormer["header"]
            corners = element.get("corners", [])
            details = {
                "json_path": f"dormers[{dormer_idx}].{parsed.kind.split('-')[1]}",
                "room_index": dormer.get("room_index"),
                "story": None,
                "source": parsed.kind,
                "corners_count": len(corners),
                "element": element,
            }
        except (ValueError, IndexError, KeyError):
            details = None

    if details is None:
        raise LookupError(
            f"Element not found for kind='{parsed.kind}' and id='{parsed.element_id}'"
        )

    return {
        "building_uuid": building.get("uuid"),
        "building_address": building.get("address"),
        "kind": parsed.kind,
        "id": parsed.element_id,
        **details,
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve shareable viewer element IDs from buildings_3d.json"
    )
    parser.add_argument(
        "--buildings-json",
        type=Path,
        default=Path("reconcile/buildings_3d.json"),
        help="Path to buildings_3d.json (default: reconcile/buildings_3d.json)",
    )
    parser.add_argument(
        "--element-id",
        required=True,
        help="Element token in format <building_uuid>::<kind>::<id>",
    )
    args = parser.parse_args()

    buildings = json.loads(args.buildings_json.read_text())
    result = find_element(buildings, args.element_id)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
