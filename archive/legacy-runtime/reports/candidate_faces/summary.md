# Phase A — candidate face generation summary

Corpus: `reconcile/reconcile_v3_results.json` — 223 buildings (elapsed 43.8s).

## Aggregates

- Buildings with scan footprint: **223** (100.0%)
- Total merged segments in: 13410
- Total candidate faces out: **2242** (16.7% vs. segments)
- Extended (ridge-extrapolated) candidates: **1768** (78.9%)
- Total authoritative zones: **787**
- Buildings with zero candidates: 79

## Candidate count distribution (non-empty buildings)

- min: 1
- median: 10
- mean: 15.6
- p90: 29
- max: 189

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