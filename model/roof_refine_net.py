from __future__ import annotations

import torch
from torch import nn
from torch_geometric.nn import TransformerConv

from model.types import RoofRefineBatch, RoofRefineOutput


class RoofRefineNet(nn.Module):
    """Hybrid Graph-Transformer scaffold for roof refinement."""

    def __init__(
        self,
        context_in_dim: int,
        query_in_dim: int,
        source_vocab_size: int,
        model_dim: int = 256,
        n_heads: int = 8,
        n_decoder_layers: int = 2,
        max_corners: int = 8,
    ) -> None:
        super().__init__()
        self.model_dim = model_dim
        self.max_corners = max_corners

        # Structural context encoder (graph message passing + projection)
        self.context_proj = nn.Sequential(
            nn.Linear(context_in_dim, model_dim),
            nn.ReLU(),
            nn.Linear(model_dim, model_dim),
        )
        self.context_graph = TransformerConv(
            in_channels=model_dim,
            out_channels=model_dim // n_heads,
            heads=n_heads,
            concat=True,
            dropout=0.0,
        )
        self.context_norm = nn.LayerNorm(model_dim)

        # Noisy proposition encoder
        self.source_embedding = nn.Embedding(source_vocab_size, model_dim)
        self.query_proj = nn.Sequential(
            nn.Linear(query_in_dim, model_dim),
            nn.ReLU(),
            nn.Linear(model_dim, model_dim),
        )
        self.query_norm = nn.LayerNorm(model_dim)

        # Cross-attention decoder
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=model_dim,
            nhead=n_heads,
            dim_feedforward=model_dim * 4,
            batch_first=True,
        )
        self.decoder = nn.TransformerDecoder(decoder_layer, num_layers=n_decoder_layers)

        # Output heads
        self.plane_head = nn.Linear(model_dim, 4)
        self.corner_head = nn.Linear(model_dim, max_corners * 3)
        self.existence_head = nn.Linear(model_dim, 1)

    def _encode_context(self, context_tokens: torch.Tensor) -> torch.Tensor:
        bsz, n_ctx, _ = context_tokens.shape
        x = self.context_proj(context_tokens)  # [B, N_ctx, D]

        # Minimal graph topology scaffold: chain edges within each sample.
        flat = x.reshape(bsz * n_ctx, self.model_dim)
        edge_list: list[torch.Tensor] = []
        offset = 0
        for _ in range(bsz):
            if n_ctx > 1:
                start = torch.arange(offset, offset + n_ctx - 1, device=x.device)
                end = torch.arange(offset + 1, offset + n_ctx, device=x.device)
                edge_list.append(torch.stack([start, end], dim=0))
                edge_list.append(torch.stack([end, start], dim=0))
            offset += n_ctx
        if edge_list:
            edge_index = torch.cat(edge_list, dim=1)
            flat = self.context_graph(flat, edge_index)
        encoded = self.context_norm(flat.reshape(bsz, n_ctx, self.model_dim))
        return encoded

    def _encode_query(self, query_tokens: torch.Tensor, source_ids: torch.Tensor) -> torch.Tensor:
        base = self.query_proj(query_tokens)
        src = self.source_embedding(source_ids)
        return self.query_norm(base + src)

    def forward(self, batch: RoofRefineBatch) -> RoofRefineOutput:
        context_latent = self._encode_context(batch.context.tokens)
        query_latent = self._encode_query(batch.query.tokens, batch.query.source_ids)

        refined = self.decoder(
            tgt=query_latent,
            memory=context_latent,
            tgt_key_padding_mask=batch.query.key_padding_mask,
            memory_key_padding_mask=batch.context.key_padding_mask,
        )

        plane_residuals = self.plane_head(refined)
        corner_offsets = self.corner_head(refined).reshape(
            refined.shape[0], refined.shape[1], self.max_corners, 3
        )
        validity_logits = self.existence_head(refined).squeeze(-1)

        return RoofRefineOutput(
            plane_residuals=plane_residuals,
            corner_offsets=corner_offsets,
            validity_logits=validity_logits,
        )

