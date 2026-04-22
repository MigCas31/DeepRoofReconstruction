# Scan-footprint robustness audit

Corpus: `pipeline-outputs` — 223 buildings

## Headline (D4 gate)

**The derived footprint is robust across the full corpus.** Across all
223 buildings:

- 0 fell back to the convex-hull path (Shapely union succeeded everywhere)
- 0 produced an invalid or self-intersecting polygon
- 0 pipeline errors

Maximum suspicion score across the corpus is 2.0 — triggered only by
soft heuristics (convexity > 0.995 or area outside 20–1500 m²), not
actual failures. Quick visual adjudication of the top 20 (files in
`geojson/`) should comfortably clear the ≥ 0.95 precision/recall gate
set by the revised plan, clearing the path to Phase A (candidate face
generation). If any of the top 20 turns out to be wrong on visual
check, add the failure mode here and revisit
`reconcile/roof_algorithms_py/footprint_derivation.py` before Phase A.

## Aggregates

- OK: **223**
- No exposed rooms: 0
- No footprint produced: 0
- Pipeline errors: 0
- Fell back to convex hull (union path failed): **0**
- Invalid / self-intersecting footprint: **0**

## Top suspects for manual adjudication

| rank | uuid | score | status | area m² | convexity | aspect | fallback | valid | simple | note |
|-----:|------|------:|--------|--------:|----------:|-------:|:--------:|:-----:|:------:|------|
| 1 | `2df1d2ed-54c9-41e9-9ed8-c4110e3868e0` | 2.0 | ok | 119.9 | 0.996 | 2.20 | . | Y | Y |  |
| 2 | `3a034c99-8986-4749-aedb-0a5a04ea803f` | 2.0 | ok | 52.8 | 0.995 | 1.14 | . | Y | Y |  |
| 3 | `513a4b03-cfb1-4221-99ff-d9b7d1e1d3f6` | 2.0 | ok | 42.3 | 0.998 | 1.77 | . | Y | Y |  |
| 4 | `573ee2ba-67b9-4bb0-b4ba-47015d09377c` | 2.0 | ok | 72.9 | 0.995 | 1.40 | . | Y | Y |  |
| 5 | `91f66e67-37e3-4cc9-9815-a4ce71c56a0a` | 2.0 | ok | 107.7 | 0.995 | 1.93 | . | Y | Y |  |
| 6 | `a1ac389f-7406-4ddf-a270-d9a5e72dbf51` | 2.0 | ok | 16.3 | 0.829 | 1.39 | . | Y | Y |  |
| 7 | `016980bc-6762-4022-bfbf-17df4112e10c` | 1.0 | ok | 34.5 | 0.876 | 1.16 | . | Y | Y |  |
| 8 | `0ce3ac3a-93ce-4ac0-9704-3cf7d31a636d` | 1.0 | ok | 72.4 | 0.804 | 1.10 | . | Y | Y |  |
| 9 | `0f911051-6084-4f0d-8f9a-24fc5b20f6ff` | 1.0 | ok | 258.5 | 0.917 | 2.03 | . | Y | Y |  |
| 10 | `10d27382-8fce-456b-897d-3d5194ff5de5` | 1.0 | ok | 85.2 | 0.958 | 3.06 | . | Y | Y |  |
| 11 | `117d172e-00d6-436e-8df2-050f25977602` | 1.0 | ok | 44.1 | 0.863 | 1.72 | . | Y | Y |  |
| 12 | `146ecf8b-ffa1-4239-ba58-040b61861fd9` | 1.0 | ok | 61.5 | 0.656 | 1.19 | . | Y | Y |  |
| 13 | `1825a812-09d0-4407-9265-182a07053cfc` | 1.0 | ok | 122.3 | 0.980 | 2.53 | . | Y | Y |  |
| 14 | `1900be91-8684-4316-98e2-c4fef6e6296f` | 1.0 | ok | 72.3 | 0.809 | 2.83 | . | Y | Y |  |
| 15 | `193c3c70-2271-4c42-ab2c-586e1d64d4cb` | 1.0 | ok | 93.5 | 0.993 | 1.91 | . | Y | Y |  |
| 16 | `19bf6498-09eb-4c62-8fc8-8623942351ba` | 1.0 | ok | 116.6 | 0.850 | 1.31 | . | Y | Y |  |
| 17 | `1f03f6e0-dfe6-4b25-bb45-f44ad146c0a3` | 1.0 | ok | 407.1 | 0.662 | 1.82 | . | Y | Y |  |
| 18 | `23cbb422-ada0-454d-8f91-30888256960d` | 1.0 | ok | 68.2 | 0.991 | 1.31 | . | Y | Y |  |
| 19 | `24e8aaa7-ec15-4a72-be5f-c67b95a53411` | 1.0 | ok | 124.7 | 0.878 | 1.80 | . | Y | Y |  |
| 20 | `287808db-3826-4351-b9a1-6f9831bdc870` | 1.0 | ok | 38.5 | 0.821 | 1.36 | . | Y | Y |  |

## Adjudication protocol

For each top-N building:

1. Open `geojson/<uuid>.geojson` in QGIS or https://geojson.io (this is XZ-plane scan-local coordinates, not geographic).
2. Judge: is the derived footprint (blue) a faithful outline of    the union of the room polygons? Flag if:
   - it misses an L- or T-shape wing
   - it collapses to a convex hull over a clearly concave building
   - it is self-intersecting or has absurd aspect ratio
3. Record verdict and failure mode in `adjudications.csv`    (columns: uuid, verdict=ok|wrong|uncertain, failure_mode, notes).

## Gate

Per the revised plan: if precision/recall of the footprint across the 20-building sample falls below 0.95, fix `reconcile/roof_algorithms_py/footprint_derivation.py` before starting Phase A (candidate face generation).