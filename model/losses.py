from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn.functional as F

from model.types import LossBreakdown, RoofRefineBatch, RoofRefineOutput


@dataclass(slots=True)
class LossWeights:
    corners: float = 1.0
    plane: float = 1.0
    existence: float = 0.5


def _masked_mean(value: torch.Tensor, mask: torch.Tensor, eps: float = 1e-8) -> torch.Tensor:
    w = mask.to(value.dtype)
    return (value * w).sum() / (w.sum() + eps)


def chamfer_like_corner_loss(
    pred_corners: torch.Tensor,
    target_corners: torch.Tensor,
    valid_corner_mask: torch.Tensor,
    query_mask: torch.Tensor,
) -> torch.Tensor:
    """
    Approximate corner loss scaffold.
    NOTE: This is index-aligned, not full permutation-invariant chamfer matching.
    """
    l1 = torch.abs(pred_corners - target_corners).sum(dim=-1)  # [B, N_q, C]
    corner_valid = valid_corner_mask & (~query_mask.unsqueeze(-1))
    return _masked_mean(l1, corner_valid)


def plane_alignment_loss(
    pred_planes: torch.Tensor,
    target_planes: torch.Tensor,
    target_validity: torch.Tensor,
    query_mask: torch.Tensor,
) -> torch.Tensor:
    abc_pred = pred_planes[..., :3]
    abc_tgt = target_planes[..., :3]
    cos = F.cosine_similarity(abc_pred, abc_tgt, dim=-1).clamp(-1.0, 1.0)
    normal_loss = 1.0 - cos
    d_loss = torch.abs(pred_planes[..., 3] - target_planes[..., 3])
    loss = normal_loss + d_loss
    valid = (target_validity > 0.5) & (~query_mask)
    return _masked_mean(loss, valid)


def existence_bce_loss(
    validity_logits: torch.Tensor,
    target_validity: torch.Tensor,
    query_mask: torch.Tensor,
) -> torch.Tensor:
    bce = F.binary_cross_entropy_with_logits(validity_logits, target_validity, reduction="none")
    valid = ~query_mask
    return _masked_mean(bce, valid)


def composite_loss(
    output: RoofRefineOutput,
    batch: RoofRefineBatch,
    weights: LossWeights | None = None,
) -> LossBreakdown:
    weights = weights or LossWeights()

    pred_planes = batch.target_planes + output.plane_residuals
    pred_corners = batch.query_corners + output.corner_offsets

    corners = chamfer_like_corner_loss(
        pred_corners=pred_corners,
        target_corners=batch.target_corners,
        valid_corner_mask=batch.target_corner_mask,
        query_mask=batch.query.key_padding_mask,
    )
    plane = plane_alignment_loss(
        pred_planes=pred_planes,
        target_planes=batch.target_planes,
        target_validity=batch.target_validity,
        query_mask=batch.query.key_padding_mask,
    )
    existence = existence_bce_loss(
        validity_logits=output.validity_logits,
        target_validity=batch.target_validity,
        query_mask=batch.query.key_padding_mask,
    )

    total = (weights.corners * corners) + (weights.plane * plane) + (weights.existence * existence)
    return LossBreakdown(total=total, corners=corners, plane=plane, existence=existence)

