# Roof Training Summary

This note summarizes the current training flow in three parts:

1. `prepare_dataset` pipeline
2. model architecture (`RoofRefineNet`)
3. loss functions and their current limits

## 1) `prepare_dataset` Pipeline

Script: `model/prepare_dataset.py`

Purpose:
- Build per-building training samples in a compact 2-file format.
- Keep reconciled/context input separate from raw roof evidence.

### Inputs

- `--input-root`
  - Per-building pipeline output folders, expected to contain `tier_payload.json`.
- `--viewer-buildings`
  - Viewer payload (default: `visualization/buildings_3d.json`) used as the source of raw roof planes.

### Output format (per building)

For each `<uuid>` that has a `tier_payload.json`:

- `output_root/<uuid>/tier_payload_input.json`
  - Copied from `input_root/<uuid>/tier_payload.json`.
- `output_root/<uuid>/raw_roof.json`
  - Extracted from `visualization/buildings_3d.json`:
    - building match by `uuid`
    - then from `rooms[].raw_ceiling_planes[]`
    - with room metadata (`room_index`, `story`, `source`) and `corners`.

### Runtime counters

The script prints:
- `prepared`: samples written
- `skipped`: folders without required input (`tier_payload.json`)
- `missing_raw_roof`: prepared samples where zero raw planes were found
- `missing_viewer_building`: UUID not found in `buildings_3d.json`

## 2) Model Architecture

Model: `model/roof_refine_net.py` (`RoofRefineNet`)

High-level idea:
- Encode building context (rooms/features).
- Encode noisy roof propositions (raw planes).
- Refine each noisy plane through cross-attention against context.
- Predict per-plane geometry corrections and validity.

### Blocks

1. Context encoder
- Input: context tokens (`[B, N_ctx, context_dim]`).
- MLP projection (`context_proj`).
- Graph message passing (`TransformerConv`) over a simple chain topology scaffold.
- LayerNorm (`context_norm`).

2. Query encoder
- Input: noisy plane tokens (`[B, N_q, query_dim]`) + source ids.
- MLP projection (`query_proj`) + source embedding (`source_embedding`).
- LayerNorm (`query_norm`).

3. Cross-attention decoder
- `nn.TransformerDecoder` with query as `tgt` and context as `memory`.
- Uses padding masks for query/context.

4. Output heads
- `plane_head`: predicts plane residuals (`[a,b,c,d]` deltas).
- `corner_head`: predicts corner offsets (`max_corners * 3`).
- `existence_head`: predicts per-plane validity logit.

## 3) Losses

Code: `model/losses.py`

`composite_loss = corners + plane + 0.5 * existence` (default weights)

### A) Corner loss (`chamfer_like_corner_loss`)

- Uses index-aligned L1 distance between predicted and target corners.
- Masked by:
  - target valid corner mask
  - non-padding query mask

Important:
- Supports variable corner counts through padding+masking.
- Not a full permutation-invariant Chamfer/EMD implementation yet.

### B) Plane alignment loss (`plane_alignment_loss`)

Per plane:
- normal loss: `1 - cosine_similarity(pred_abc, tgt_abc)`
- offset loss: `abs(pred_d - tgt_d)`
- summed and masked by `target_validity > 0.5` and non-padding queries.

Important:
- If `target_validity` is all zeros, this term is exactly zero.

### C) Existence loss (`existence_bce_loss`)

- Binary cross entropy on predicted validity logits vs `target_validity`.
- Computed on non-padding queries.

### Current alignment limitation

In `tensorize_example` (`model/data.py`):
- queries come from noisy planes
- targets are padded/truncated to query count
- matching is by index
- TODO exists for Hungarian/permutation matching

So:
- variable plane counts are ingestible (via padding/truncation),
- but supervision is only reliable when noisy and target planes are already roughly aligned.

## Practical Training Modes

### Prepared sample mode

`python -m model.train --sample-dir <sample_dir> --epochs 1`

- Reads:
  - `tier_payload_input.json`
  - `raw_roof.json`
- For backward compatibility, loader also accepts legacy `reconciled_input.json`.

### Explicit 3-file mode

`python -m model.train --payload ... --noisy ... --target ... --epochs 1`

- Use this when you want direct control over a custom `target_roof.json`.
