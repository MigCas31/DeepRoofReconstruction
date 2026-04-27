from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare tier-payload/raw-roof model samples")
    parser.add_argument(
        "--input-root",
        type=Path,
        required=True,
        help="Root folder containing per-building pipeline outputs (with tier_payload.json)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Where prepared per-building samples are written",
    )
    parser.add_argument(
        "--viewer-buildings",
        type=Path,
        default=Path("visualization/buildings_3d.json"),
        help="Path to visualization buildings_3d.json payload",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of buildings to process (0 = all)",
    )
    return parser.parse_args(argv)


def _as_xyz_list(point: Any) -> list[float] | None:
    if isinstance(point, (list, tuple)) and len(point) >= 3:
        return [float(point[0]), float(point[1]), float(point[2])]
    if isinstance(point, dict) and {"x", "y", "z"} <= set(point.keys()):
        return [float(point["x"]), float(point["y"]), float(point["z"])]
    return None


def _extract_planes_from_room_raw(room: dict[str, Any], room_index: int) -> list[dict[str, Any]]:
    planes: list[dict[str, Any]] = []
    story = int(room.get("story", 0))
    source = str(room.get("raw_ceiling_source", "raw_ceiling_planes"))
    for plane_index, plane in enumerate(room.get("raw_ceiling_planes", [])):
        corners_raw = plane.get("corners", [])
        corners = [_as_xyz_list(p) for p in corners_raw]
        corners = [p for p in corners if p is not None]
        if len(corners) < 3:
            continue
        planes.append(
            {
                "id": f"room-{room_index}-plane-{plane_index}",
                "room_index": room_index,
                "story": story,
                "source": source,
                "corners": corners,
            }
        )
    return planes


def _extract_planes_from_viewer_building(viewer_building: dict[str, Any]) -> list[dict[str, Any]]:
    planes: list[dict[str, Any]] = []
    for room_index, room in enumerate(viewer_building.get("rooms", [])):
        if isinstance(room, dict):
            planes.extend(_extract_planes_from_room_raw(room, room_index))
    return planes


def build_raw_roof(
    viewer_building: dict[str, Any] | None,
    building_uuid: str,
) -> tuple[dict[str, Any], bool]:
    planes: list[dict[str, Any]] = []
    extraction_mode = "visualization.buildings_3d.rooms.raw_ceiling_planes"
    missing_viewer_building = viewer_building is None
    if viewer_building is not None:
        planes = _extract_planes_from_viewer_building(viewer_building)
    payload = {
        "building_uuid": building_uuid,
        "extraction_mode": extraction_mode,
        "plane_count": len(planes),
        "planes": planes,
    }
    return payload, missing_viewer_building


def prepare_building(
    building_dir: Path,
    output_root: Path,
    viewer_by_uuid: dict[str, dict[str, Any]],
) -> tuple[bool, bool, bool]:
    tier_payload_path = building_dir / "tier_payload.json"
    if not tier_payload_path.exists():
        return (False, False, False)

    tier_payload_data = json.loads(tier_payload_path.read_text())

    building_uuid = str(building_dir.name)
    raw_roof, missing_viewer_building = build_raw_roof(
        viewer_by_uuid.get(building_uuid),
        building_uuid,
    )
    missing_raw_roof = raw_roof["plane_count"] == 0

    destination = output_root / building_uuid
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "tier_payload_input.json").write_text(
        json.dumps(tier_payload_data, indent=2, sort_keys=False)
    )
    (destination / "raw_roof.json").write_text(json.dumps(raw_roof, indent=2, sort_keys=False))
    return (True, missing_raw_roof, missing_viewer_building)


def load_viewer_buildings(path: Path) -> dict[str, dict[str, Any]]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"Expected list payload in {path}")
    result: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        uuid = item.get("uuid")
        if isinstance(uuid, str) and uuid:
            result[uuid] = item
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_root = args.input_root
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    viewer_by_uuid = load_viewer_buildings(args.viewer_buildings)

    processed = 0
    skipped = 0
    missing_raw = 0
    missing_viewer = 0

    for child in sorted(input_root.iterdir()):
        if not child.is_dir():
            continue
        ok, missing, missing_viewer_building = prepare_building(child, output_root, viewer_by_uuid)
        if not ok:
            skipped += 1
            continue
        processed += 1
        if missing:
            missing_raw += 1
        if missing_viewer_building:
            missing_viewer += 1
        if args.limit and processed >= args.limit:
            break

    print(
        f"prepared={processed} skipped={skipped} "
        f"missing_raw_roof={missing_raw} missing_viewer_building={missing_viewer} "
        f"output_root={output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
