from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

from model.encoding import PaddingSpec, pad_corners, pad_token_tensor, source_ids
from model.types import ContextBatch, QueryBatch, RoofRefineBatch
from reconcile.payload.schema import TierPayload, payload_from_dict
from reconcile.payload.validate import validate_payload


@dataclass(slots=True)
class ExampleRecord:
    payload: TierPayload | dict[str, Any]
    noisy_proposition: dict[str, Any]
    target_ceilings: dict[str, Any]


def load_tier_payload(path: str | Path) -> TierPayload:
    data = json.loads(Path(path).read_text())
    payload = payload_from_dict(data)
    validate_payload(payload)
    return payload


def load_example(
    payload_path: str | Path,
    noisy_path: str | Path,
    target_path: str | Path,
) -> ExampleRecord:
    return ExampleRecord(
        payload=load_tier_payload(payload_path),
        noisy_proposition=json.loads(Path(noisy_path).read_text()),
        target_ceilings=json.loads(Path(target_path).read_text()),
    )


def load_prepared_sample(sample_dir: str | Path) -> ExampleRecord:
    sample_path = Path(sample_dir)
    tier_payload_input_path = sample_path / "tier_payload_input.json"
    if tier_payload_input_path.exists():
        prepared_payload = json.loads(tier_payload_input_path.read_text())
    else:
        # Backward compatibility with older prepared samples.
        prepared_payload = json.loads((sample_path / "reconciled_input.json").read_text())
    raw_roof = json.loads((sample_path / "raw_roof.json").read_text())

    noisy_planes: list[dict[str, Any]] = []
    for plane in raw_roof.get("planes", []):
        corners = [
            [float(point[0]), float(point[1]), float(point[2])]
            for point in plane.get("corners", [])
            if isinstance(point, (list, tuple)) and len(point) >= 3
        ]
        if len(corners) < 3:
            continue
        noisy_planes.append(
            {
                "corners": corners,
                "source": plane.get("source", "raw_roof"),
                "plane_abcd": plane.get("plane_abcd", [0.0, 0.0, 1.0, 0.0]),
                "area_hint": len(corners),
            }
        )

    target_planes: list[dict[str, Any]] = []
    for item in prepared_payload.get("ceiling", []):
        corners = []
        for point in item.get("corners", []):
            if isinstance(point, dict):
                corners.append(
                    [
                        float(point.get("x", 0.0)),
                        float(point.get("y", 0.0)),
                        float(point.get("z", 0.0)),
                    ]
                )
            elif isinstance(point, (list, tuple)) and len(point) >= 3:
                corners.append([float(point[0]), float(point[1]), float(point[2])])
        if len(corners) < 3:
            continue
        plane = item.get("plane", {}) or {}
        target_planes.append(
            {
                "corners": corners,
                "plane_abcd": [
                    float(plane.get("a", 0.0)),
                    float(plane.get("b", 0.0)),
                    float(plane.get("c", 1.0)),
                    float(plane.get("d", 0.0)),
                ],
                "validity": 1.0,
            }
        )

    return ExampleRecord(
        payload=prepared_payload,
        noisy_proposition={"planes": noisy_planes},
        target_ceilings={"planes": target_planes},
    )


def _vec3_list_to_xyz_stats(points: list[Any]) -> list[float]:
    if not points:
        return [0.0] * 6
    xs = [float(p.x) for p in points]
    ys = [float(p.y) for p in points]
    zs = [float(p.z) for p in points]
    return [
        sum(xs) / len(xs),
        sum(ys) / len(ys),
        sum(zs) / len(zs),
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs),
    ]


def _point_xyz(point: Any) -> list[float] | None:
    if isinstance(point, dict):
        if {"x", "y", "z"} <= set(point.keys()):
            return [float(point["x"]), float(point["y"]), float(point["z"])]
        return None
    if isinstance(point, (list, tuple)) and len(point) >= 3:
        return [float(point[0]), float(point[1]), float(point[2])]
    if all(hasattr(point, k) for k in ("x", "y", "z")):
        return [float(point.x), float(point.y), float(point.z)]
    return None


def _corners_to_xyz_stats(points: list[Any]) -> list[float]:
    xyz = [_point_xyz(p) for p in points]
    xyz = [p for p in xyz if p is not None]
    if not xyz:
        return [0.0] * 6
    xs = [p[0] for p in xyz]
    ys = [p[1] for p in xyz]
    zs = [p[2] for p in xyz]
    return [
        sum(xs) / len(xs),
        sum(ys) / len(ys),
        sum(zs) / len(zs),
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs),
    ]


def build_context_tokens_from_reconciled(payload: dict[str, Any]) -> list[list[float]]:
    tokens: list[list[float]] = []
    rooms = payload.get("rooms", [])
    for room in rooms:
        if not isinstance(room, dict):
            continue
        floor_stats = _corners_to_xyz_stats(room.get("floorPolygon", []))
        tokens.append(
            [
                float(room.get("story", 0)),
                float(len(room.get("walls", []))),
                float(len(room.get("doors", []))),
                float(len(room.get("windows", []))),
                *floor_stats,
                0.0,
                float(len(rooms)),
            ]
        )
    return tokens


def build_context_tokens(payload: TierPayload) -> list[list[float]]:
    tokens: list[list[float]] = []
    for room in payload.rooms:
        floor_stats = _vec3_list_to_xyz_stats(room.floor.corners)
        tokens.append(
            [
                float(room.story),
                float(len(room.walls)),
                float(len(room.doors)),
                float(len(room.windows)),
                *floor_stats,
                float(payload.classification.n_stories),
                float(payload.classification.n_rooms),
            ]
        )
    return tokens


def build_query_tokens(noisy_proposition: dict[str, Any]) -> tuple[list[list[float]], list[str], list[list[list[float]]]]:
    planes = noisy_proposition.get("planes", [])
    tokens: list[list[float]] = []
    src_tags: list[str] = []
    corners: list[list[list[float]]] = []
    for plane in planes:
        abcd = plane.get("plane_abcd") or plane.get("plane") or [0.0, 0.0, 1.0, 0.0]
        poly = plane.get("corners") or []
        area_hint = float(plane.get("area_hint", len(poly)))
        slope_hint = float(plane.get("slope_hint", 0.0))
        tokens.append([float(abcd[0]), float(abcd[1]), float(abcd[2]), float(abcd[3]), area_hint, slope_hint])
        src_tags.append(str(plane.get("source", "unknown")))
        corners.append([[float(p[0]), float(p[1]), float(p[2])] for p in poly])
    return tokens, src_tags, corners


def build_targets(target_ceilings: dict[str, Any]) -> tuple[list[list[float]], list[list[list[float]]], list[float]]:
    items = target_ceilings.get("planes", [])
    planes: list[list[float]] = []
    corners: list[list[list[float]]] = []
    validity: list[float] = []
    for item in items:
        abcd = item.get("plane_abcd") or item.get("plane") or [0.0, 0.0, 1.0, 0.0]
        planes.append([float(abcd[0]), float(abcd[1]), float(abcd[2]), float(abcd[3])])
        corners.append([[float(p[0]), float(p[1]), float(p[2])] for p in item.get("corners", [])])
        validity.append(float(item.get("validity", 1.0)))
    return planes, corners, validity


def tensorize_example(example: ExampleRecord, spec: PaddingSpec) -> RoofRefineBatch:
    if isinstance(example.payload, dict):
        context_tokens = build_context_tokens_from_reconciled(example.payload)
    else:
        context_tokens = build_context_tokens(example.payload)
    query_tokens, query_sources, query_corners_list = build_query_tokens(example.noisy_proposition)
    target_planes_list, target_corners_list, target_validity_list = build_targets(example.target_ceilings)

    # TODO: Hungarian/permutation matching between noisy and target planes.
    n_q = min(len(query_tokens), spec.max_query_tokens)
    if len(target_planes_list) < n_q:
        pad = n_q - len(target_planes_list)
        target_planes_list.extend([[0.0, 0.0, 1.0, 0.0] for _ in range(pad)])
        target_corners_list.extend([[] for _ in range(pad)])
        target_validity_list.extend([0.0 for _ in range(pad)])
    else:
        target_planes_list = target_planes_list[:n_q]
        target_corners_list = target_corners_list[:n_q]
        target_validity_list = target_validity_list[:n_q]

    ctx, ctx_mask = pad_token_tensor(context_tokens, spec.max_context_tokens, feat_dim=12)
    qry, qry_mask = pad_token_tensor(query_tokens, spec.max_query_tokens, feat_dim=6)
    qry_src = source_ids(query_sources, spec.max_query_tokens)

    qry_corners, qry_corner_mask = pad_corners(query_corners_list, spec.max_query_tokens, spec.max_corners)
    tgt_corners, tgt_corner_mask = pad_corners(target_corners_list, spec.max_query_tokens, spec.max_corners)

    target_planes = torch.zeros((spec.max_query_tokens, 4), dtype=torch.float32)
    if n_q:
        target_planes[:n_q] = torch.tensor(target_planes_list[:n_q], dtype=torch.float32)
    target_validity = torch.zeros((spec.max_query_tokens,), dtype=torch.float32)
    if n_q:
        target_validity[:n_q] = torch.tensor(target_validity_list[:n_q], dtype=torch.float32)

    return RoofRefineBatch(
        context=ContextBatch(tokens=ctx.unsqueeze(0), key_padding_mask=ctx_mask.unsqueeze(0)),
        query=QueryBatch(
            tokens=qry.unsqueeze(0),
            key_padding_mask=qry_mask.unsqueeze(0),
            source_ids=qry_src.unsqueeze(0),
        ),
        query_corners=qry_corners.unsqueeze(0),
        query_corner_mask=qry_corner_mask.unsqueeze(0),
        target_planes=target_planes.unsqueeze(0),
        target_corners=tgt_corners.unsqueeze(0),
        target_corner_mask=tgt_corner_mask.unsqueeze(0),
        target_validity=target_validity.unsqueeze(0),
    )

