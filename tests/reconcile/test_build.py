import json
from pathlib import Path

import pytest

from reconcile_tiers.build import build_tier_payload, needs_rebuild, payload_json
from reconcile_tiers.extract.building import extract_building_model
from reconcile_tiers.payload.schema import CeilingSource
from reconcile_tiers.payload.validate import validate_payload


@pytest.mark.parametrize(
    "uuid",
    [
        "c72ad855-9e52-46f1-886d-a9f37911521f",
        "f40dcc9f-b97b-4bef-8b40-ba011aabf0bd",
        "2ea3b759-e047-424c-8034-f8ee5b811fb4",
    ],
)
def test_validate_only_passes_on_cohort_uuid(uuid):
    payload = build_tier_payload(
        uuid,
        pipeline_dir=Path("pipeline-outputs"),
        scan_root=Path(".scan-cache"),
    )

    validate_payload(payload)


def test_payload_json_is_deterministic_for_cohort_uuid():
    uuid = "c72ad855-9e52-46f1-886d-a9f37911521f"

    first = payload_json(
        build_tier_payload(uuid, pipeline_dir=Path("pipeline-outputs"), scan_root=Path(".scan-cache"))
    )
    second = payload_json(
        build_tier_payload(uuid, pipeline_dir=Path("pipeline-outputs"), scan_root=Path(".scan-cache"))
    )

    assert first == second
    validate_payload(build_tier_payload(uuid, pipeline_dir=Path("pipeline-outputs"), scan_root=Path(".scan-cache")))


def test_roof_arrangement_ceilings_do_not_project_above_observed_roof_evidence():
    uuid = "0d3f2993-8386-4130-8f1c-b2938c410828"
    pipeline_dir = Path("pipeline-outputs")
    scan_root = Path(".scan-cache")

    model = extract_building_model(uuid, pipeline_dir, scan_root)
    observed_y = [
        float(point[1])
        for room in model.rooms
        for seq in [room.floor_polygon, room.ceiling_polygon]
        for point in seq
    ]
    observed_y.extend(
        float(point[1])
        for room in model.rooms
        for wall in room.walls_computed
        for point in wall.corners
    )
    observed_y.extend(
        float(point[1])
        for room in model.rooms
        for raw in room.raw_ceiling_planes
        for point in raw.corners
    )
    payload = build_tier_payload(uuid, pipeline_dir=pipeline_dir, scan_root=scan_root)
    roof_arrangement_y = [
        corner.y
        for piece in payload.ceiling
        if piece.source == CeilingSource.ROOF_ARRANGEMENT
        for corner in piece.corners
    ]

    assert roof_arrangement_y
    assert max(roof_arrangement_y) <= max(observed_y) + 0.6


def test_mtime_gating_skips_current_payload_and_rebuilds_stale_payload(tmp_path):
    uuid = "uuid-1"
    pipeline_dir = tmp_path / "pipeline"
    building_dir = pipeline_dir / uuid
    building_dir.mkdir(parents=True)
    merged_path = building_dir / "merged.json"
    merged_path.write_text(json.dumps({"rooms": []}))
    scan_dir = tmp_path / "scan-root" / f"scans_address_{uuid}_suffix"
    scan_dir.mkdir(parents=True)
    (scan_dir / "room.json").write_text("{}")
    payload_path = building_dir / "tier_payload.json"
    payload_path.write_text("{}")

    old = 100.0
    current = 200.0
    newer = 300.0
    for path in (merged_path, scan_dir, scan_dir / "room.json"):
        path.touch()
    payload_path.touch()
    import os

    os.utime(merged_path, (current, current))
    os.utime(scan_dir / "room.json", (current, current))
    os.utime(scan_dir, (current, current))
    os.utime(payload_path, (newer, newer))

    assert not needs_rebuild(uuid, pipeline_dir, scan_dir.parent, payload_path)
    assert needs_rebuild(uuid, pipeline_dir, scan_dir.parent, payload_path, force=True)

    os.utime(payload_path, (old, old))
    assert needs_rebuild(uuid, pipeline_dir, scan_dir.parent, payload_path)
