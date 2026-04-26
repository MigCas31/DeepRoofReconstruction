# Phase A — candidate face generation summary

Corpus: `reconcile/reconcile_v3_results.json` — 223 buildings (elapsed 208.1s).

## Aggregates

- Buildings with scan footprint: **223** (100.0%)
- Total merged segments in: 13480
- Total candidate faces out: **2327** (17.3% vs. segments)
- Extended (ridge-extrapolated) candidates: **1872** (80.4%)
- Total authoritative zones: **837**
- Buildings with zero candidates: 80

## Candidate count distribution (non-empty buildings)

- min: 2
- median: 8
- mean: 16.3
- p90: 33
- max: 244

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