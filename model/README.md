# RoofRefineNet Scaffold

This folder contains a minimal scaffold for a geometry-to-geometry roof refinement model based on a hybrid Graph-Transformer architecture.

## Files

- `types.py`: batch/output dataclasses and tensor contracts.
- `encoding.py`: source vocabulary and padding/mask helpers.
- `roof_refine_net.py`: context encoder + proposition encoder + cross-attention decoder + output heads.
- `losses.py`: weighted composite loss (`corners`, `plane`, `existence`).
- `data.py`: repo-aware JSON loading hooks using `payload_from_dict` and `validate_payload`.
- `prepare_dataset.py`: builds per-building training folders with tier payload input + raw roof.
- `train.py`: minimal single-sample training loop.

## Expected Inputs

`train.py` expects three JSON files:

1. `--payload`: TierPayload-format JSON (`tier_payload.json` style).
1. `--noisy`: noisy proposition JSON:

```json
{
  "planes": [
    {
      "corners": [[x, y, z], [x, y, z], [x, y, z]],
      "plane_abcd": [a, b, c, d],
      "source": "raw_fallback"
    }
  ]
}
```

1. `--target`: corrected roof JSON:

```json
{
  "planes": [
    {
      "corners": [[x, y, z], [x, y, z], [x, y, z]],
      "plane_abcd": [a, b, c, d],
      "validity": 1.0
    }
  ]
}
```

## Example

```bash
python -m model.train \
  --payload /path/to/tier_payload.json \
  --noisy /path/to/noisy_roof.json \
  --target /path/to/target_roof.json \
  --epochs 2
```

## Prepared Folder Workflow

Build training samples from `input_files/pipeline-outputs`:

```bash
python -m model.prepare_dataset \
  --input-root input_files/pipeline-outputs \
  --output-root model/prepared-samples \
  --viewer-buildings visualization/buildings_3d.json
```

Each output sample folder has:

- `tier_payload_input.json` (copied from per-building `tier_payload.json`)
- `raw_roof.json` (raw roof planes extracted from `visualization/buildings_3d.json` using `building.uuid -> rooms[].raw_ceiling_planes[]`, matching the viewer's "Show raw roof" source)

Train directly from one prepared sample:

```bash
python -m model.train \
  --sample-dir model/prepared-samples/<building_uuid> \
  --epochs 2
```

## Scaffold Limits (Intentional)

- No full dataset abstraction yet.
- No Hungarian/permutation matching yet; target/noisy planes are currently index-aligned.
- Corner loss is a chamfer-like placeholder, not full permutation-invariant chamfer.
- Graph topology is a minimal chain-edge scaffold for context tokens.
