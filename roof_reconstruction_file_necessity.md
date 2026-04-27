# Repository Necessity Map For Roof Reconstruction

## Target behavior (what this map optimizes for)

You want to build a new `roof_reconstruction` pipeline using:
- raw input geometry,
- raw roof/ceiling evidence,
- reconciled inputs from the latest `reconcile_tiers` flow,

while keeping viewer behavior as:
- default: show reconciled input,
- toggle 1: `show raw input` (before reconciliation and without roof),
- toggle 2: `show raw roof` (raw ceiling/roof evidence).

This document classifies repository directories by how necessary they are for that exact task.

## Data flow you are targeting

1. Load reconciled baseline (`pipeline-outputs/<uuid>/merged.json`) through `reconcile_tiers` ingest.
2. Attach raw scan/ceiling evidence (from `.scan-cache`) to room/building model.
3. Build/read reconciled model without invoking roof reconstruction when needed.
4. Build a new roof reconstruction stage using raw roof/ceiling + reconciled geometry.
5. Visualize reconciled by default; expose raw-input and raw-roof toggle presets in viewer.

## Required now (core implementation directories)

- `reconcile_tiers/`  
  Why: This is the latest pipeline stack and where ingest, extract, and roof orchestration live.
- `reconcile_tiers/ingest/`  
  Why: Loads reconciled `merged.json` and scan-cache inputs needed to preserve raw evidence.
- `reconcile_tiers/extract/`  
  Why: Builds reconciled building/room models and carries raw ceiling planes into later stages.
- `reconcile_tiers/roof/`  
  Why: Current roof logic and extension point for a new `roof_reconstruction` pipeline.
- `reconcile_tiers/build.py` and `reconcile_tiers/cli.py`  
  Why: Defines execution path, including where roof reconstruction is called or can be bypassed.
- `pipeline-outputs/`  
  Why: Canonical runtime reconciled artifacts (`merged.json`, `tier_payload.json`, `tier_index.json`).
- `.scan-cache` (external runtime input source)  
  Why: Raw room and ceiling files used to preserve/show raw roof/ceiling evidence.

## Required for viewer toggles and default display

- `reconcile/`  
  Why: Contains active viewer pages/scripts used for layer visibility and interaction controls.
- `reconcile/viewer.html`  
  Why: UI location to add the two buttons (`show raw input`, `show raw roof`).
- `reconcile/viewer-main.js`  
  Why: Startup/default loading behavior and main place to wire layer-preset toggles.
- `reconcile/viewer-modules/`  
  Why: Layer constants, rendering paths, and UI bindings used by toggle behavior.
- `reconcile/viewer-modules/constants.js`  
  Why: Defines pipeline/layer presets; best place to encode raw-input and raw-roof presets.
- `reconcile/viewer-modules/roof-python.js`  
  Why: Handles rendering of roof-sidecar style outputs relevant to raw roof visualization.
- `reconcile/viewer_server.py`  
  Why: Serves viewer + payload artifacts; needed to verify default and toggle views end-to-end.

## Optional / reference (useful but not mandatory)

- `archive/legacy-runtime/reconcile/`  
  Why: Historical extraction/roof implementations useful for parity checks and ideas.
- `reconcile_tiers/TRACKING.md`  
  Why: Architecture decisions and migration notes that explain intended behavior.
- `tests/reconcile_tiers/`  
  Why: Validation baseline for ingest/extract/roof behavior when changing pipeline logic.
- `tests/golden/tier_payload/`  
  Why: Golden-output references for payload shape regressions.
- `reports/`  
  Why: Can help inspect intermediate roof/ceiling diagnostics during algorithm iteration.
- `docs/`  
  Why: Background and process context; useful for onboarding but not runtime-critical.

## Not needed for this task (initial implementation scope)

- `reconcile_v2/`  
  Why: Separate topology pipeline; not required for this roof reconstruction + viewer-toggle path.
- `reconcile_v3/`  
  Why: Separate evolution track; not required for current reconciled/raw roof integration goal.
- `reconcile_ext/`  
  Why: Ancillary extension flow not needed for core `reconcile_tiers` + viewer-toggle implementation.
- Root one-off analysis scripts (for example `analyze_*.py`, `investigate_*.py`, `compare_*.py`)  
  Why: Investigation helpers, not part of the runtime pipeline path you are targeting.
- `schemas/` (initially)  
  Why: Needed only if payload contract changes; not required for first pass integration.
- `scripts/` (initially)  
  Why: Operational helpers; useful later for automation, not required to design core flow.
- `artifacts/`  
  Why: Storage/output support, not central to implementing ingest/reconcile/roof/viewer behavior.

## Display modes to keep explicit in implementation

- Reconciled default view  
  Source: reconciled pipeline artifacts; should be initial viewer state.
- Raw input no-roof view (`show raw input`)  
  Source: pre-reconciliation geometry signals; hide roof/final overlays.
- Raw roof view (`show raw roof`)  
  Source: raw ceiling/roof evidence; show raw roof-related layers clearly.

## Read-first shortlist (high-impact files)

1. `reconcile_tiers/build.py`
2. `reconcile_tiers/cli.py`
3. `reconcile_tiers/ingest/merged.py`
4. `reconcile_tiers/ingest/scan_cache.py`
5. `reconcile_tiers/ingest/room_transforms.py`
6. `reconcile_tiers/extract/building.py`
7. `reconcile_tiers/extract/ceilings.py`
8. `reconcile_tiers/roof/roof.py`
9. `reconcile_tiers/roof/obliques.py`
10. `reconcile_tiers/roof/simple_slant.py`
11. `reconcile/viewer-main.js`
12. `reconcile/viewer-modules/constants.js`
13. `reconcile/viewer-modules/roof-python.js`
14. `reconcile/viewer.html`
15. `reconcile/viewer_server.py`

## Practical next-step sequence (implementation handoff)

1. Add a roof-reconstruction split point in `reconcile_tiers/build.py` so reconciled ingest/extract can run without roof generation.
2. Define a dedicated `roof_reconstruction` module boundary inside `reconcile_tiers/roof/` that consumes reconciled model + raw ceiling evidence.
3. Ensure payload/build path can emit:
   - reconciled-only view model,
   - raw-input-no-roof layer data,
   - raw roof/ceiling layer data.
4. Add two viewer buttons in `reconcile/viewer.html` and wire preset toggles in `reconcile/viewer-main.js` (or `viewer-modules/constants.js`).
5. Verify on real UUIDs in `pipeline-outputs/` that:
   - default opens in reconciled mode,
   - `show raw input` hides roof and shows pre-reconciliation/raw signals,
   - `show raw roof` exposes raw roof/ceiling overlays correctly.
