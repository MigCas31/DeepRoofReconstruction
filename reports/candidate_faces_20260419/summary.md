# Phase A — candidate face generation summary

Corpus: `reconcile/reconcile_v3_results.json` — 223 buildings (elapsed 212.3s).

## Aggregates

- Buildings with scan footprint: **223** (100.0%)
- Total merged segments in: 13410
- Total candidate faces out: **13105** (97.7% vs. segments)
- Extended (ridge-extrapolated) candidates: **9544** (72.8%)
- Buildings with zero candidates: 79

## Candidate count distribution (non-empty buildings)

- min: 6
- median: 44
- mean: 91.0
- p90: 153
- max: 2488

## Errors

- none

## Phase B handoff

Each building's ``candidates`` list feeds directly into the BIP
solver (`reconcile_v3/reconstruction/solver.py`, not yet written).
Per the revised plan, each candidate face carries: plane, clipped
footprint (XZ), area, azimuth/inclination, neighbour IDs
(topology constraint), support (data-term weight), and — once
D1 calibration runs — a GBM prior to be multiplied into the
objective.