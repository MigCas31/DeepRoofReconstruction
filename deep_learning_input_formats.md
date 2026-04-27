# Deep Learning Input Format Specification

## Purpose
This document defines the two input channels to use for deep learning in this repository:

1. **Reconciled structured building payload** (`TierPayload`-style output).
2. **Raw roof evidence** from scan cache, represented in rooms as `raw_ceiling_planes`.

The goal is to help an AI system select model families and build data loaders without reverse-engineering Python code.

---

## Canonical Data Sources

### Reconciled Input (Primary Structured Input)
- Canonical contract: `reconcile/payload/schema.py`
- JSON schema: `reconcile/payload/tier_payload_schema.json`
- Builder/orchestration: `reconcile/build.py`

### Raw Roof Input (Primary Raw Geometric Input)
- Ingestion: `reconcile/ingest/scan_cache.py` (`load_raw_ceilings`)
- Attachment/remap to rooms: `reconcile/extract/building.py` (`_remap_raw_ceilings`)
- Roof usage examples:
  - `reconcile/roof/simple_slant.py`
  - `reconcile/roof/obliques.py`
  - `reconcile/roof/clipping.py`

---

## Coordinate and Geometry Conventions
- Coordinates are 3D metric values in world space after transforms (`x`, `y`, `z`).
- `y` is vertical (height axis).
- Polygonal geometry is variable-length:
  - room floors/walls/ceilings can have variable corner count,
  - openings are typically quads (`corners` arrays) but should be treated as generic polygons.
- All loaders should tolerate variable object counts:
  - variable number of rooms per building,
  - variable walls/openings/planes per room.

---

## Input A: Reconciled Payload (`TierPayload`)

Top-level required fields (schema version `1`):
- `schema_version`: literal `"1"`
- `uuid`: building UUID string
- `address`: string or null
- `building_center`: `{x, y, z}`
- `classification`: roof/tier summary block
- `rooms`: list of room objects
- `gaps`: list of gap polygons
- `ceiling`: list of ceiling polygons with fitted planes
- `knee_walls`: list of thermal/knee wall polygons

### A.1 `classification` block
Fields:
- `tier` (int), `tier_label` (string)
- `roof_type` (enum): `none | flat | shed | gable | hip | mansard | pyramid | cross_gable | complex`
- `n_stories`, `n_rooms`, `n_oblique`, `n_flat` (int)
- `has_half_height`, `has_gable` (bool)

ML role:
- strong global supervisory targets and priors for architecture conditioning.

### A.2 `rooms[]` block
Each room includes:
- `story` (int)
- `floor.corners[]`: polygon of `Vec3`
- `walls[]` where each wall has:
  - `corners[]`
  - `extension_strip[] | null`
  - `cutouts[]` (list of quads)
  - `locator_id`
- `doors[]` and `windows[]` (lists of `Quad`-like `corners[]`)
- `locator_id`

ML role:
- room graph nodes, wall graph edges, opening tokens, story-level grouping.

### A.3 `gaps[]` block
Each gap has:
- `corners[]` (`Vec3` polygon)
- `kind` enum:
  - `gap_floor`, `gap_ceiling`, `side`,
  - `stitch`, `stitch_floor`, `stitch_ceiling`,
  - `exterior_side`, `exterior_floor`, `exterior_ceiling`
- `scope` enum: `intra_story | inter_story | exterior | junction`
- `locator_id`

ML role:
- geometric inconsistency signals; useful as auxiliary targets or quality scores.

### A.4 `ceiling[]` block
Each ceiling piece has:
- `corners[]`
- `holes[][]`
- `plane`: `{a,b,c,d}`
- `source` enum:
  - `flat_emit`, `dormer_cutout`, `roof_arrangement`, `thermal_cap`, `raw_fallback`
- `arrangement_cell_id` (string|null)
- `locator_id`

ML role:
- the highest-value normalized roof/ceiling representation for prediction targets.

### A.5 `knee_walls[]` block
Each knee wall has:
- `corners[]`
- `kind` enum: `knee | dormer_cheek | dormer_header`
- `locator_id`

ML role:
- secondary roof-structure labels and dormer boundary context.

---

## Input B: Raw Roof (`room.raw_ceiling_planes`)

### B.1 Pre-remap raw source in scan cache
From each `ceiling_<room-id>.json` file:
- payload iterates over `walls[]`
- for each wall entry:
  - `polygonCorners` -> `corners_local`
  - `transform` (local plane transform)
- room-level metadata:
  - `source` from `ceiling_metadata_<room-id>.json` when present, else `"scan"`

Parsed shape per scan-room:
```json
{
  "planes": [
    {
      "corners_local": [[x,y,z], ...],
      "transform": [16-float transform or equivalent]
    }
  ],
  "source": "scan|<metadata-key>"
}
```

### B.2 Canonical form after remap/attachment to extracted rooms
In `ExtractedRoom`:
- `raw_ceiling_planes`: list of `RawCeilingPlane`
  - each plane: `corners: [[x,y,z], ...]` (world-space, transformed)
- `raw_ceiling_source`: `str | None`

Remap process:
1. `corners_local` transformed to world via scan transform.
2. room transform applied (`compute_room_transforms` pipeline).
3. coordinates rounded to 4 decimals.
4. only polygons with at least 3 corners retained.

---

## Joining Input A and Input B

Recommended joins:
1. **Primary:** by building UUID + room index in extracted pipeline.
2. **Secondary:** by story and geometric proximity if indices drift.
3. **Locator-based:** keep `locator_id` strings for traceability to rendered elements.

Important:
- raw ceilings are attached at room level before final payload assembly.
- in final ceiling candidates, raw ceilings may appear as `source = raw_fallback`.

---

## ML-Ready Feature Inventory

### Global features (building-level)
- `classification.*`
- counts derived from payload lists (`len(rooms)`, `len(ceiling)`, `len(gaps)`)
- `building_center`

### Room-level features
- `story`
- floor polygon geometry stats (area, perimeter, normal consistency)
- wall count, opening count
- wall orientations and extents from `walls[].corners`

### Ceiling/roof features
- reconciled ceiling polygons (`ceiling[].corners`, `holes`, `plane`, `source`)
- raw ceiling polygons (`raw_ceiling_planes[].corners`)
- per-plane slope/inclination and azimuth (derived from fitted plane)

### Categorical features
- `roof_type`, `tier_label`, `ceiling.source`, `gap.kind`, `gap.scope`, `knee_walls.kind`
- encode via embeddings or one-hot (embedding preferred for large multi-task models)

---

## Tensorization Patterns and Suitable Model Families

### Option 1: Hierarchical Set/Transformer (recommended default)
Representation:
- building -> set of rooms -> set of polygons/planes per room.
Why:
- native handling of variable cardinality.
- strong fit for mixed global + local tasks (classification + regression).

### Option 2: Graph Neural Network
Representation:
- room nodes, wall/opening nodes, optional gap nodes, spatial edges.
Why:
- explicit topology, adjacency, story relationships.
- good for consistency/construction tasks.

### Option 3: Point/Polygon Encoder + Fusion
Representation:
- sample polygon points from reconciled and raw plane boundaries.
Why:
- useful when geometry detail dominates and strict topology is noisy.

### Option 4: Voxel/BEV projection
Representation:
- rasterize to 2D/3D grids.
Why:
- easier convolutional baselines, but may lose fine polygon fidelity.

---

## Normalization and Invariants
- center coordinates by `building_center` (or per-building centroid).
- normalize scale by robust building extent (for cross-building training).
- enforce/validate minimum polygon size (`>= 3` corners).
- compute plane coefficients from normalized coordinates when possible.
- keep story index as integer token, not continuous scalar.
- preserve source tags (`raw_fallback`, `roof_arrangement`, etc.) as confidence/provenance signals.

---

## Data Quality and Edge Cases
- Some rooms have no raw ceiling planes.
- Raw ceiling planes are often sparse and can be non-rectangular after remap.
- The roof pipeline uses strict guards for promoting raw planes (inclination, area, residual, duplicate checks).
- Reconciled payload can include ceilings from multiple sources in the same building.
- `address` can be null.

---

## Minimal Unified Training Sample (AI-Oriented)

```json
{
  "building_uuid": "string",
  "global": {
    "building_center": [x, y, z],
    "roof_type": "gable",
    "tier": 2
  },
  "rooms": [
    {
      "room_index": 0,
      "story": 0,
      "floor_polygon": [[x, y, z], ...],
      "walls": [
        {
          "corners": [[x, y, z], ...],
          "extension_strip": [[x, y, z], ...] ,
          "cutouts": [[[x, y, z], ...], ...]
        }
      ],
      "doors": [[[x, y, z], ...], ...],
      "windows": [[[x, y, z], ...], ...],
      "raw_ceiling_source": "scan",
      "raw_ceiling_planes": [
        {
          "corners": [[x, y, z], ...]
        }
      ]
    }
  ],
  "reconciled_ceilings": [
    {
      "corners": [[x, y, z], ...],
      "holes": [[[x, y, z], ...], ...],
      "plane_abcd": [a, b, c, d],
      "source": "roof_arrangement"
    }
  ],
  "gaps": [
    {
      "corners": [[x, y, z], ...],
      "kind": "gap_ceiling",
      "scope": "inter_story"
    }
  ],
  "knee_walls": [
    {
      "corners": [[x, y, z], ...],
      "kind": "knee"
    }
  ]
}
```

---

## Model Selection Guidance from This Input Design
- If the main target is **roof type / tier classification**: hierarchical set transformer with global pooling.
- If the main target is **ceiling/roof geometry generation**: graph + polygon decoder, conditioned on raw ceilings.
- If data is limited and targets are coarse: start with feature-engineered gradient boosting baseline from aggregated geometric stats.
- For multi-task training, combine:
  - classification heads (`roof_type`, `tier_label`)
  - regression heads (plane parameters, heights, areas)
  - optional auxiliary reconstruction loss on ceiling polygons.

This input design is most naturally suited for **set/graph hybrid models** rather than fixed-size CNN-only architectures.
