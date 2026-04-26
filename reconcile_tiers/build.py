from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from reconcile_tiers._core.plane import FitFailure, Plane
from reconcile_tiers.assemble.building_center import compute_building_center
from reconcile_tiers.assemble.ceiling_painter import CeilingCandidate, assemble_ceiling
from reconcile_tiers.assemble.gaps_to_pieces import assemble_gap_pieces
from reconcile_tiers.assemble.walls_to_rooms import assemble_rooms
from reconcile_tiers.classify.roof_type import classify_oblique_roof
from reconcile_tiers.classify.tiers import classify_building
from reconcile_tiers.extract.building import BuildingModel, extract_building_model
from reconcile_tiers.ingest.merged import find_merged_path
from reconcile_tiers.ingest.scan_cache import find_scan_cache_dir
from reconcile_tiers.payload.schema import (
    CeilingSource,
    KneeWall,
    TierClassification,
    TierPayload,
    Vec3,
    payload_to_dict,
)
from reconcile_tiers.payload.validate import validate_payload
from reconcile_tiers.roof.roof import RoofModel, build_roof_model


def _fit_candidate(
    corners: list[list[float]],
    source: CeilingSource,
    locator_id: str,
    arrangement_cell_id: str | None = None,
) -> CeilingCandidate | None:
    plane = Plane.fit(corners)
    if isinstance(plane, FitFailure):
        return None
    return CeilingCandidate(
        corners=[[float(p[0]), float(p[1]), float(p[2])] for p in corners],
        plane=plane,
        source=source,
        locator_id=locator_id,
        arrangement_cell_id=arrangement_cell_id,
    )


def _ceiling_candidates(model: BuildingModel, roof: RoofModel) -> tuple[list[CeilingCandidate], list[CeilingCandidate]]:
    candidates: list[CeilingCandidate] = []
    holes: list[CeilingCandidate] = []
    for room in model.rooms:
        if room.ceiling_type == "flat" and len(room.ceiling_polygon) >= 3:
            candidate = _fit_candidate(
                room.ceiling_polygon,
                CeilingSource.FLAT_EMIT,
                f"{model.uuid}::tier-ceiling-flat::{room.index}",
            )
            if candidate is not None:
                candidates.append(candidate)
        for plane_idx, raw in enumerate(room.raw_ceiling_planes):
            candidate = _fit_candidate(
                raw.corners,
                CeilingSource.RAW_FALLBACK,
                f"{model.uuid}::tier-ceiling-raw::{room.index}:{plane_idx}",
            )
            if candidate is not None:
                candidates.append(candidate)

    for idx, surface in enumerate(roof.oblique_split):
        candidate = _fit_candidate(
            surface.corners,
            CeilingSource.ROOF_ARRANGEMENT,
            f"{model.uuid}::tier-ceiling-roof-arrangement::{idx}",
            arrangement_cell_id=surface.arrangement_cell_id,
        )
        if candidate is not None:
            candidates.append(candidate)
    if not roof.oblique_split:
        for idx, surface in enumerate(roof.oblique):
            candidate = _fit_candidate(
                surface.corners,
                CeilingSource.ROOF_ARRANGEMENT,
                f"{model.uuid}::tier-ceiling-roof-arrangement::{idx}",
            )
            if candidate is not None:
                candidates.append(candidate)

    for idx, dormer in enumerate(roof.dormers):
        candidate = _fit_candidate(
            dormer.cutout_quad,
            CeilingSource.DORMER_CUTOUT,
            f"{model.uuid}::tier-ceiling-dormer-cutout::{idx}",
        )
        if candidate is not None:
            holes.append(candidate)
    return candidates, holes


def _knee_walls(model: BuildingModel, roof: RoofModel) -> list[KneeWall]:
    return [
        KneeWall(
            corners=[Vec3(x=float(p[0]), y=float(p[1]), z=float(p[2])) for p in surface.corners],
            kind=surface.kind,
            locator_id=f"{model.uuid}::tier-knee-wall::{idx}",
        )
        for idx, surface in enumerate(roof.thermal)
        if len(surface.corners) >= 3
    ]


def _building_dict(model: BuildingModel) -> dict[str, Any]:
    return {
        "uuid": model.uuid,
        "stories_found": model.stories_found,
        "split_level": model.split_level,
        "rooms": [{"story": room.story} for room in model.rooms],
    }


def _roof_dict(roof: RoofModel) -> dict[str, Any]:
    return {
        "roof_surfaces": {
            "oblique": [
                {
                    "corners": surface.corners,
                    "story": surface.dominant_story,
                    "dominant_story": surface.dominant_story,
                    "cluster": {
                        "avgAzimuth": surface.cluster.avg_azimuth,
                        "avgIncl": surface.cluster.avg_incl,
                    },
                }
                for surface in roof.oblique
            ],
            "flat": [
                {
                    "corners": surface.corners,
                    "story": surface.story,
                    "dominant_story": surface.dominant_story,
                }
                for surface in roof.flat
            ],
        }
    }


def _classification(model: BuildingModel, roof: RoofModel) -> TierClassification:
    result = classify_building(_building_dict(model), _roof_dict(roof))
    signals = result["signals"]
    return TierClassification(
        tier=int(result["tier"]),
        tier_label=str(result["tier_label"]),
        roof_type=classify_oblique_roof(roof.oblique),
        n_stories=int(signals["n_stories"]),
        n_rooms=int(signals["n_rooms"]),
        n_oblique=int(signals["n_oblique"]),
        n_flat=int(signals["n_flat"]),
        has_half_height=bool(signals["has_half_height"]),
        has_gable=bool(signals["has_gable"]),
    )


def build_tier_payload(
    uuid: str,
    pipeline_dir: Path | str = Path("pipeline-outputs"),
    scan_root: Path | str | None = Path(".scan-cache"),
) -> TierPayload:
    model = extract_building_model(uuid, pipeline_dir, scan_root)
    roof = build_roof_model(model)
    candidates, holes = _ceiling_candidates(model, roof)
    payload = TierPayload(
        schema_version="1",
        uuid=model.uuid,
        address=model.address,
        building_center=compute_building_center(model),
        classification=_classification(model, roof),
        rooms=assemble_rooms(model),
        gaps=assemble_gap_pieces(model),
        ceiling=assemble_ceiling(candidates, holes),
        knee_walls=_knee_walls(model, roof),
    )
    validate_payload(payload)
    return payload


def payload_json(payload: TierPayload) -> str:
    return json.dumps(payload_to_dict(payload), indent=2, sort_keys=True) + "\n"


def _latest_mtime(path: Path | None) -> float:
    if path is None or not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_mtime
    latest = path.stat().st_mtime
    for child in path.rglob("*"):
        try:
            latest = max(latest, child.stat().st_mtime)
        except OSError:
            continue
    return latest


def output_path_for_uuid(uuid: str, pipeline_dir: Path | str) -> Path:
    return Path(pipeline_dir) / uuid / "tier_payload.json"


def needs_rebuild(
    uuid: str,
    pipeline_dir: Path | str,
    scan_root: Path | str | None,
    output_path: Path | str | None = None,
    *,
    force: bool = False,
) -> bool:
    if force:
        return True
    out_path = Path(output_path) if output_path is not None else output_path_for_uuid(uuid, pipeline_dir)
    if not out_path.exists():
        return True
    merged_path = find_merged_path(uuid, pipeline_dir)
    scan_dir = find_scan_cache_dir(uuid, scan_root) if scan_root is not None else None
    newest_input = max(_latest_mtime(merged_path), _latest_mtime(scan_dir))
    return newest_input > out_path.stat().st_mtime


def list_uuids(pipeline_dir: Path | str) -> list[str]:
    root = Path(pipeline_dir)
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and (entry / "merged.json").exists()
    )


def _build_one(args: tuple[str, str, str | None, bool, bool]) -> tuple[str, str, str | None]:
    uuid, pipeline_dir, scan_root, force, validate_only = args
    out_path = output_path_for_uuid(uuid, pipeline_dir)
    if not validate_only and not needs_rebuild(uuid, pipeline_dir, scan_root, out_path, force=force):
        return uuid, "skipped", None
    payload = build_tier_payload(uuid, pipeline_dir, scan_root)
    if validate_only:
        return uuid, "validated", None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload_json(payload))
    return uuid, "written", None


def build_many(
    uuids: list[str],
    *,
    pipeline_dir: Path | str = Path("pipeline-outputs"),
    scan_root: Path | str | None = Path(".scan-cache"),
    force: bool = False,
    validate_only: bool = False,
    workers: int = 1,
) -> list[tuple[str, str, str | None]]:
    worker_args = [
        (uuid, str(pipeline_dir), str(scan_root) if scan_root is not None else None, force, validate_only)
        for uuid in sorted(uuids)
    ]
    if workers <= 1:
        results = []
        for args in worker_args:
            try:
                results.append(_build_one(args))
            except Exception as exc:
                results.append((args[0], "failed", str(exc)))
        return results
    results: list[tuple[str, str, str | None]] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_build_one, args): args[0] for args in worker_args}
        for future in as_completed(futures):
            uuid = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append((uuid, "failed", str(exc)))
    return sorted(results, key=lambda item: item[0])


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--uuid", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("-j", "--workers", type=int, default=1)
    parser.add_argument("--pipeline-dir", default="pipeline-outputs")
    parser.add_argument("--scan-root", default=".scan-cache")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    uuids = list_uuids(args.pipeline_dir) if args.all else sorted(args.uuid)
    if not uuids:
        parser.error("pass --all or at least one --uuid")
    results = build_many(
        uuids,
        pipeline_dir=args.pipeline_dir,
        scan_root=args.scan_root,
        force=args.force,
        validate_only=args.validate_only,
        workers=max(1, args.workers),
    )
    failures = [result for result in results if result[1] == "failed"]
    if failures:
        failure_path = Path(args.pipeline_dir) / "tier_build_failures.log"
        failure_path.write_text(
            "\n".join(f"{uuid}: {message}" for uuid, _status, message in failures) + "\n"
        )
        return 1
    if not args.validate_only:
        index_path = Path(args.pipeline_dir) / "tier_index.json"
        index_path.write_text(json.dumps({"buildings": [uuid for uuid, _status, _message in results]}, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
