from __future__ import annotations

from dataclasses import dataclass

import torch

SOURCE_TO_ID = {
    "scan": 0,
    "raw_fallback": 1,
    "roof_arrangement": 2,
    "flat_emit": 3,
    "dormer_cutout": 4,
    "thermal_cap": 5,
    "unknown": 6,
}


@dataclass(slots=True)
class PaddingSpec:
    max_context_tokens: int = 128
    max_query_tokens: int = 64
    max_corners: int = 8


def pad_token_tensor(tokens: list[list[float]], max_tokens: int, feat_dim: int) -> tuple[torch.Tensor, torch.Tensor]:
    out = torch.zeros((max_tokens, feat_dim), dtype=torch.float32)
    mask = torch.ones((max_tokens,), dtype=torch.bool)
    n = min(len(tokens), max_tokens)
    if n:
        out[:n] = torch.tensor(tokens[:n], dtype=torch.float32)
        mask[:n] = False
    return out, mask


def pad_corners(corners: list[list[list[float]]], max_tokens: int, max_corners: int) -> tuple[torch.Tensor, torch.Tensor]:
    out = torch.zeros((max_tokens, max_corners, 3), dtype=torch.float32)
    mask = torch.zeros((max_tokens, max_corners), dtype=torch.bool)
    token_n = min(len(corners), max_tokens)
    for t_idx in range(token_n):
        c = corners[t_idx]
        corner_n = min(len(c), max_corners)
        if corner_n:
            out[t_idx, :corner_n] = torch.tensor(c[:corner_n], dtype=torch.float32)
            mask[t_idx, :corner_n] = True
    return out, mask


def source_ids(sources: list[str], max_tokens: int) -> torch.Tensor:
    out = torch.zeros((max_tokens,), dtype=torch.long)
    n = min(len(sources), max_tokens)
    for idx in range(n):
        out[idx] = SOURCE_TO_ID.get(sources[idx], SOURCE_TO_ID["unknown"])
    return out

