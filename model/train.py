from __future__ import annotations

import argparse
from pathlib import Path

import torch

from model.data import load_example, load_prepared_sample, tensorize_example
from model.encoding import PaddingSpec
from model.losses import LossWeights, composite_loss
from model.roof_refine_net import RoofRefineNet


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RoofRefineNet scaffold trainer")
    parser.add_argument(
        "--sample-dir",
        type=Path,
        help="Prepared sample directory containing tier_payload_input.json and raw_roof.json",
    )
    parser.add_argument("--payload", type=Path, help="Path to tier_payload JSON")
    parser.add_argument("--noisy", type=Path, help="Path to noisy roof proposition JSON")
    parser.add_argument("--target", type=Path, help="Path to target roof JSON")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--model-dim", type=int, default=256)
    parser.add_argument("--max-context", type=int, default=128)
    parser.add_argument("--max-query", type=int, default=64)
    parser.add_argument("--max-corners", type=int, default=8)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    spec = PaddingSpec(
        max_context_tokens=args.max_context,
        max_query_tokens=args.max_query,
        max_corners=args.max_corners,
    )
    if args.sample_dir is not None:
        example = load_prepared_sample(args.sample_dir)
    else:
        if args.payload is None or args.noisy is None or args.target is None:
            raise SystemExit(
                "Either pass --sample-dir, or provide --payload --noisy --target together."
            )
        example = load_example(args.payload, args.noisy, args.target)
    batch = tensorize_example(example, spec)

    model = RoofRefineNet(
        context_in_dim=batch.context.tokens.shape[-1],
        query_in_dim=batch.query.tokens.shape[-1],
        source_vocab_size=7,
        model_dim=args.model_dim,
        max_corners=args.max_corners,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    weights = LossWeights()

    batch.context.tokens = batch.context.tokens.to(device)
    batch.context.key_padding_mask = batch.context.key_padding_mask.to(device)
    batch.query.tokens = batch.query.tokens.to(device)
    batch.query.key_padding_mask = batch.query.key_padding_mask.to(device)
    batch.query.source_ids = batch.query.source_ids.to(device)
    batch.query_corners = batch.query_corners.to(device)
    batch.query_corner_mask = batch.query_corner_mask.to(device)
    batch.target_planes = batch.target_planes.to(device)
    batch.target_corners = batch.target_corners.to(device)
    batch.target_corner_mask = batch.target_corner_mask.to(device)
    batch.target_validity = batch.target_validity.to(device)

    for epoch in range(args.epochs):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        output = model(batch)
        loss = composite_loss(output, batch, weights)
        loss.total.backward()
        optimizer.step()
        print(
            f"epoch={epoch + 1} total={loss.total.item():.6f} "
            f"corners={loss.corners.item():.6f} plane={loss.plane.item():.6f} "
            f"existence={loss.existence.item():.6f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

