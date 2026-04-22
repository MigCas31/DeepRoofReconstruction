# Phase A — candidate face generation summary

Corpus: `reconcile/reconcile_v3_results.json` — 2 buildings (elapsed 0.8s).

## Aggregates

- Buildings with scan footprint: **2** (100.0%)
- Total merged segments in: 66
- Total candidate faces out: **62** (93.9% vs. segments)
- Extended (ridge-extrapolated) candidates: **58** (93.5%)
- Buildings with zero candidates: 0

## Candidate count distribution (non-empty buildings)

- min: 28
- median: 31
- mean: 31.0
- p90: 38
- max: 34

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