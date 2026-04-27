from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass(slots=True)
class ContextBatch:
    """Structural context tokens and masks."""

    tokens: torch.Tensor  # [B, N_ctx, D_ctx]
    key_padding_mask: torch.Tensor  # [B, N_ctx] True means padded


@dataclass(slots=True)
class QueryBatch:
    """Noisy roof proposition tokens and masks."""

    tokens: torch.Tensor  # [B, N_q, D_q]
    key_padding_mask: torch.Tensor  # [B, N_q] True means padded
    source_ids: torch.Tensor  # [B, N_q]


@dataclass(slots=True)
class RoofRefineBatch:
    """Model input batch for roof refinement."""

    context: ContextBatch
    query: QueryBatch
    query_corners: torch.Tensor  # [B, N_q, C_max, 3]
    query_corner_mask: torch.Tensor  # [B, N_q, C_max] True means valid
    target_planes: torch.Tensor  # [B, N_q, 4]
    target_corners: torch.Tensor  # [B, N_q, C_max, 3]
    target_corner_mask: torch.Tensor  # [B, N_q, C_max] True means valid
    target_validity: torch.Tensor  # [B, N_q]


@dataclass(slots=True)
class RoofRefineOutput:
    """Model outputs aligned to query tokens."""

    plane_residuals: torch.Tensor  # [B, N_q, 4]
    corner_offsets: torch.Tensor  # [B, N_q, C_max, 3]
    validity_logits: torch.Tensor  # [B, N_q]


@dataclass(slots=True)
class LossBreakdown:
    total: torch.Tensor
    corners: torch.Tensor
    plane: torch.Tensor
    existence: torch.Tensor

