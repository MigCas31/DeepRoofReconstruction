# Exhaustive Feature Catalogue for Slanted-Roof Classification (V3)

**Date:** 2026-04-18
**Author:** Deep research synthesis (codebase mining + academic literature)
**Dataset:** 5,760 human labels / 5,628 unique proposals across 70 buildings (`.context/v3_roof_proposal_labels.jsonl`)
**Purpose:** Drive feature-engineering for a classifier that reverse-engineers what distinguishes an accepted from a rejected merged slanted-roof segment.

---

## Executive Summary

We enumerate **~600 distinct candidate features** for classifying a `V3MergedRoofSegment` as accept/reject, organized across 18 categories. Features fall into four bands by source:

| Band | Count | Source |
|---|---|---|
| **Band 1 — Already in label record** | 33 | Enrichment at save time; zero recomputation. |
| **Band 2 — Derivable from stored provenance** | ~300 | Computable from `merged_plane`, `segment_corners_xyz`, `opposing_planes`, `building_boundary_xz`, `member_snapshots`, `room_boundary_refs`. No pipeline re-run. |
| **Band 3 — Requires pipeline re-read** | ~100 | Need `reconcile_v3_results.json` + `buildings_3d.json` per `building_uuid` (kneewall beneath segment, dormer adjacency, part gable status, slope hypothesis, roof-coverage-graph evidence tier, etc.). |
| **Band 4 — From academic literature** | ~163 | Features used in published roof-plane classifiers (PolyFit, HRTT, RoofSeg, Weinmann 2017, PDAL, OSM roof:shape, etc.). Most are already in Bands 2–3 under different names; the remainder (e.g., eigenvalue features on *point clouds*, which we don't have) are out of scope. |

**Three structural caveats the data imposes:**

1. **`reasons[]` is empty on every label record** — we have binary accept/reject only, no "why" taxonomy. Limits error-analysis granularity.
2. **No formal roof-type taxonomy exists anywhere in the repo** (no gable/hip/mansard/shed enum). The only architectural classifier is `V3Part.gable_extension.status` (5-way gable-vs-not enum).
3. **No ML or pandas/sklearn/lightgbm code currently in the repo.** All existing "heuristics" are hand-crafted thresholds; the classifier effort is greenfield.

**Recommended prioritization (Part V + VIII):** start with the ~20 features in Band 1 plus the top 40 Band-2 signals the literature converges on — plane angular descriptors, dihedral to opposing planes, inlier residual RMS, α-shape/convex-hull ratios, footprint-alignment azimuth residual, wall-top coverage, rain-exposure ratio, relative-story index, part-gable status. Most literature signals map directly onto signals we can compute without touching the pipeline.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Part I — Band 1: Features already in the label record](#part-i--band-1-features-already-in-the-label-record)
3. [Part II — Band 2: Features derivable from stored provenance](#part-ii--band-2-features-derivable-from-stored-provenance)
4. [Part III — Band 3: Features requiring pipeline/results re-read](#part-iii--band-3-features-requiring-pipelineresults-re-read)
5. [Part IV — Band 4: Features from academic literature](#part-iv--band-4-features-from-academic-literature)
6. [Part V — Cross-synthesis: top expected signals](#part-v--cross-synthesis-top-expected-signals)
7. [Part VI — Implementation notes and utilities to reuse](#part-vi--implementation-notes-and-utilities-to-reuse)
8. [Part VII — Gaps and limitations](#part-vii--gaps-and-limitations)
9. [Part VIII — Prioritized experimental roadmap](#part-viii--prioritized-experimental-roadmap)
10. [Bibliography](#bibliography)
11. [Methodology appendix](#methodology-appendix)

---

## 1. Introduction

### 1.1 Problem framing

V3's `slanted_roof_proposals` stage emits a permissive Cartesian product of `(slanted-segment × rain-exposed piece)`. A downstream stage (`merged_slanted_roof_proposals`) clusters coplanar proposals and splits them against opposing planes, producing **one labelable piece per cluster × opposing-sides × room/gap piece** — these are the `V3MergedRoofSegment` records humans label in the viewer.

Today, whether a merged segment is a "real" roof is decided by a heuristic: inherit the `heuristic_label` of the first member whose source wall appears in any accepted `V3SlantedRoof` and whose `slab_room_id` matches. This is brittle and over-rejects (74.31% of labels rejected by humans, but human accept rate per the heuristic is much lower).

We want a **data-driven classifier** — not to change the proposer, but to surface a ranked list of rules humans can inspect. Per `generalize-before-specialize`, no production rule change lands until the analysis is reviewed.

### 1.2 Data inventory

- **Labels:** `.context/v3_roof_proposal_labels.jsonl`, 5,760 records / 5,628 unique (last-write-wins on `proposal_id`). 1,427 accepts (25.35%) / 4,183 rejects (74.31%) / 18 skips / 132 duplicates. Median 60 labels/building, max 521.
- **Splits:** `.context/v3_roof_proposal_splits.jsonl` — user-drawn XZ lines that split a proposal into children; children inherit parent's plane + everything else.
- **Results:** `reconcile/reconcile_v3_results.json` — full V3Building per UUID, all 11 element types.
- **Source geometry:** `reconcile/buildings_3d.json` — rooms, walls, floors, windows, doors, per UUID.

### 1.3 What makes a feature "in-scope"

A feature is in-scope if one of:
1. It is directly stored in the label record (Band 1).
2. It is computable from `(label_record + numpy + Shapely v2)` alone (Band 2).
3. It is computable from `(label_record + reconcile_v3_results.json + buildings_3d.json)` (Band 3).

Out of scope: per-point LiDAR features (we don't have raw point clouds; the upstream iOS RoomPlan scan is already abstracted into walls/floors), CNN embeddings of orthophotos, and anything requiring a new upstream signal.

---

## Part I — Band 1: Features already in the label record

All 33 fields captured today. Per-record, one row per labeled `V3MergedRoofSegment` (or `V3RoofProposal` if `merge_mode=false`).

### 1.1 Top-level label fields

| # | Field | Type | Notes |
|---|---|---|---|
| B1.1 | `building_uuid` | str | Building identifier. |
| B1.2 | `proposal_id` | str | ID of the labeled object. For merged: `<uuid>::slanted-roof-segment::<cluster_canonical_id>` plus optional `#<n>` or `#side-<bits>` split suffix. |
| B1.3 | `kind` | str ("proposal"\|"merged") | Object type. |
| B1.4 | `label` | str ("accept"\|"reject"\|"skip") | Human choice (**target**). |
| B1.5 | `labeler` | str | Email/identity of labeler. |
| B1.6 | `ts` | str (ISO) / float | Save timestamp. |
| B1.7 | `merge_mode` | bool | Was merge mode on when labeled? |
| B1.8 | `heuristic_label` | str | Pipeline's prediction (accepted/rejected/not_evaluated). |
| B1.9 | `reasons` | list[str] | **Empty on every record today** — no reject-taxonomy available. |
| B1.10 | `context` | dict | Optional UI-context dict (rarely populated). |

### 1.2 Merged-segment-specific fields

| # | Field | Type | Notes |
|---|---|---|---|
| B1.11 | `cluster_canonical_id` | str | ID of the merged plane cluster. |
| B1.12 | `merged_plane` | list[float×4] | Canonical cluster plane `(a, b, c, d)`. |
| B1.13 | `member_proposal_ids` | list[str] | IDs of all raw proposals in this cluster. |
| B1.14 | `cluster_members` / `member_snapshots` | list[dict] | Archived copies of all member proposals (see §1.3 for per-member schema). |
| B1.15 | `cluster_params` | dict | `{normal_dot_min: 0.94, d_abs_max: 0.50, opposing_cos_azimuth_max: 0.866}` — merge thresholds used. |
| B1.16 | `building_boundary_xz` | list[list[float, float]] | 2D polygon ring — union of all slab XZ footprints (outer clip boundary). |
| B1.17 | `opposing_cluster_canonicals` | list[str] | IDs of clusters this segment was split against. |
| B1.18 | `opposing_planes` | list[list[float×4]] | Plane equations of the opposing clusters. |
| B1.19 | `room_boundary_refs` | list[dict] | Reference(s) to the rain-exposed piece(s). See §1.4. |
| B1.20 | `segment_corners_xyz` | list[list[float×3]] | Final 3D polygon vertices (lifted onto merged_plane). |
| B1.21 | `side_pieces` | list[dict] | Opposing-side metadata — per (opposing_cluster_id, side="rain"\|"covered"). |
| B1.22 | `part_count` | int | Total parts in the building. |
| B1.23 | `part_index` | int | Which part this segment belongs to. |
| B1.24 | `features_snapshot` | dict | Segment-level aggregates (see §1.5). |

### 1.3 Per-member-snapshot schema

`member_snapshots[i]` is a dict with the following keys (from `reconcile_v3/stages/merged_slanted_roof_proposals.py:308–325`):

| # | Field | Type |
|---|---|---|
| B1.25 | `id` | str (proposal ID) |
| B1.26 | `plane` | list[float×4] |
| B1.27 | `corners` | list[list[float×3]] — original pre-clip corners |
| B1.28 | `features` | dict — 25-key flat feature vector (see §1.6) |
| B1.29 | `heuristic_label` | str |
| B1.30 | `segment_index` | int |
| B1.31 | `source_room_id` | str \| None |
| B1.32 | `source_wall_id` | str \| None |
| B1.33 | `slab_room_id` | str \| None |
| B1.34 | `slab_id` | str \| None |

### 1.4 Per-room-boundary-ref schema

Either a room-piece ref or a gap-piece ref:

**Room kind:** `{kind: "room", room_id, room_index, story, piece_index}`
**Gap kind:** `{kind: "gap", gap_id, floor_y, ceiling_y}`

### 1.5 `features_snapshot` keys (merged segment aggregates)

From `merged_slanted_roof_proposals.py:505–518`:

| # | Feature | Type | Meaning |
|---|---|---|---|
| B1.35 | `area_m2` | float | XZ area of final segment polygon. |
| B1.36 | `perimeter_m` | float | Perimeter of final polygon. |
| B1.37 | `member_count` | int | Number of raw proposals merged. |
| B1.38 | `opposing_cluster_count` | int | Number of opposing merged planes that split this segment. |
| B1.39 | `piece_kind` | str ("room"\|"gap") | Rain-exposed piece type. |
| B1.40 | `clipped_by_building_boundary` | bool | Was the segment clipped by the building-boundary polygon? |
| B1.41 | `rain_hitting_side_count` | int | Number of opposing seams where this plane is the *higher* side. |
| B1.42 | `covered_side_count` | int | Number of opposing seams where this plane is the *covered/lower* side. |

### 1.6 Per-proposal `features` dict (from `slanted_roof_proposals.py:290–356`)

25 keys, computed by `_compute_features()`. Each `member_snapshots[i].features` carries the full dict. Aggregates across members are Band-2 derivables.

| # | Feature | Type | Formula |
|---|---|---|---|
| B1.43 | `segment_azimuth_deg` | float | atan2(dx, dz) mod 360. |
| B1.44 | `segment_incl_deg` | float | acos(dy / length). |
| B1.45 | `segment_length_m` | float | 3D length of source wall edge. |
| B1.46 | `segment_mid_y_m` | float | Y of midpoint. |
| B1.47 | `segment_story` | int | Story of source wall. |
| B1.48 | `slab_area_m2` | float | Area of target slab/room floor. |
| B1.49 | `slab_vertex_count` | int | Number of vertices in slab polygon. |
| B1.50 | `slab_story` | int | Story of target slab. |
| B1.51 | `slab_kind` | str ("room"\|"gap") | Is target a room or sealed gap? |
| B1.52 | `piece_index` | int | Index within slab's rain-exposed pieces. |
| B1.53 | `piece_area_m2` | float | XZ area of this rain-exposed piece. |
| B1.54 | `piece_perimeter_m` | float | Perimeter of piece polygon. |
| B1.55 | `piece_compactness` | float | 4π·area / perimeter² ∈ [0, 1]. |
| B1.56 | `piece_vertex_count` | int | Vertices in piece. |
| B1.57 | `piece_bbox_aspect` | float | max-side / min-side of bbox. |
| B1.58 | `piece_min_width_m` | float | 2·area / perimeter (ribbon thickness proxy). |
| B1.59 | `rain_exposure_ratio` | float | piece_area / slab_area ∈ [0, 1]. |
| B1.60 | `is_top_story_slab` | bool | Slab on top story of building? |
| B1.61 | `is_same_room` | bool | Segment's source room == slab's room? |
| B1.62 | `story_delta` | int | slab_story − segment_story. |
| B1.63 | `seg_mid_to_piece_centroid_xz_m` | float | 2D XZ distance, segment midpoint → piece centroid. |
| B1.64 | `slab_floor_y_m` | float | Floor Y of target slab. |
| B1.65 | `plane_y_at_piece_centroid_m` | float | Plane Y evaluated at piece centroid XZ. |
| B1.66 | `plane_height_above_slab_m` | float | plane_y_at_centroid − slab_floor_y. |
| B1.67 | `slant_delta_over_piece_m` | float | max_y − min_y of plane evaluated over piece. |

---

## Part II — Band 2: Features derivable from stored provenance

Features computable from `(merged_plane, segment_corners_xyz, opposing_planes, building_boundary_xz, member_snapshots, room_boundary_refs)` alone. Implementable with numpy + Shapely v2. Organized by 10 sub-categories.

### A. Plane / normal descriptors (39 features)

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| A1 | `plane_azimuth_deg` | atan2(a, c) · 180/π mod 360 | Cardinal orientation. Primary water-flow. |
| A2 | `plane_incl_deg` | acos(\|b\| / ‖n‖) · 180/π | Steepness / pitch. |
| A3 | `plane_rise_over_run` | √(a² + c²) / \|b\| | Dimensionless pitch. |
| A4 | `plane_pitch_x12` | rise / run · 12 | Builder convention. |
| A5 | `plane_slope_pct` | rise / run · 100 | GIS convention. |
| A6 | `normal_a` | merged_plane[0] | Raw coefficient. |
| A7 | `normal_b` | merged_plane[1] | Raw coefficient. |
| A8 | `normal_c` | merged_plane[2] | Raw coefficient. |
| A9 | `plane_d` | merged_plane[3] | Plane offset. |
| A10 | `normal_magnitude` | √(a² + b² + c²) | Validation (~1 after normalization). |
| A11 | `angle_to_world_y_deg` | acos(\|b\|) · 180/π | Planarity vs vertical. |
| A12 | `angle_to_world_x_deg` | acos(\|a\|) · 180/π | — |
| A13 | `angle_to_world_z_deg` | acos(\|c\|) · 180/π | — |
| A14 | `steepness_bin` | {<5°:0, 5–25°:1, 25–50°:2, 50°+:3} | Categorical pitch. |
| A15 | `pitch_category` | nearest standard (2:12, 4:12, 6:12, 8:12, 12:12) | Building-code bucket. |
| A16 | `is_flat` | incl < 5° | Filters mis-classed flats. |
| A17 | `is_steep` | incl > 50° | Near-wall detector. |
| A18 | `is_architectural_pitch` | 15° ≤ incl ≤ 60° | Typical roof range. |
| A19 | `is_near_vertical` | incl > 80° | Should never be a roof. |
| A20 | `water_flow_azimuth_deg` | = plane_azimuth | Runoff compass bearing. |
| A21 | `water_flow_dir_xz` | (−a, −c) / √(a²+c²) | 2D drainage unit vector. |
| A22 | `sheds_water_away_from_centroid` | (centroid − building_centroid) · water_flow_dir > 0 | Physically plausible? |
| A23 | `drainage_efficiency` | \|dot product\| / (‖flow‖·‖offset‖) | Cosine of flow/offset angle. |
| A24 | `normal_dot_world_up` | \|b\| | Upward-facing magnitude. |
| A25 | `horizontal_component_magnitude` | √(a² + c²) | Lateral slope magnitude. |
| A26 | `azimuth_quadrant` | floor(az / 90) mod 4 | Cardinal bucket. |
| A27 | `azimuth_from_north` | angle_diff(az, 0) | Compass deviation. |
| A28 | `azimuth_from_south` | angle_diff(az, 180) | — |
| A29 | `azimuth_from_east` | angle_diff(az, 90) | — |
| A30 | `azimuth_from_west` | angle_diff(az, 270) | — |
| A31 | `is_axis_aligned_xy` | \|c\| < 1e-6 | Gable-end wall check. |
| A32 | `is_axis_aligned_yz` | \|a\| < 1e-6 | Gable-end wall check. |
| A33 | `dihedral_to_opposing_min_deg` | min over opposing planes | Sharpest ridge. |
| A34 | `dihedral_to_opposing_max_deg` | max over opposing planes | Shallowest ridge. |
| A35 | `dihedral_to_opposing_mean_deg` | mean over opposing planes | Typical ridge angle. |
| A36 | `dihedral_to_opposing_std_deg` | std over opposing planes | Ridge consistency. |
| A37 | `azimuth_from_building_principal_axis_deg` | angle_diff(az, building_axis) | Aligned with building orientation? |
| A38 | `log_plane_rise_over_run` | log(rise/run + ε) | Scale-invariant pitch. |
| A39 | `is_monotone_downslope` | dot(plane_xz_gradient, eave_direction) ≈ 1 | Slope direction consistency. |

### B. Edge geometry — 2D and 3D (56 features)

For every edge of `segment_corners_xyz`: length, azimuth, inclination, height delta. Then statistics over the set.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| B.1 | `edge_count` | len(corners) | Polygon complexity. |
| B.2 | `edge_len_3d_min_m` | min ‖eᵢ‖ | Smallest boundary. |
| B.3 | `edge_len_3d_max_m` | max ‖eᵢ‖ | Longest boundary. |
| B.4 | `edge_len_3d_mean_m` | mean ‖eᵢ‖ | Typical edge size. |
| B.5 | `edge_len_3d_median_m` | median ‖eᵢ‖ | — |
| B.6 | `edge_len_3d_std_m` | std ‖eᵢ‖ | Regularity. |
| B.7 | `edge_len_3d_cv` | std / mean | Scan-noise proxy. |
| B.8 | `edge_len_3d_p10` | pct(10, ‖eᵢ‖) | — |
| B.9 | `edge_len_3d_p25` | pct(25, ‖eᵢ‖) | — |
| B.10 | `edge_len_3d_p75` | pct(75, ‖eᵢ‖) | — |
| B.11 | `edge_len_3d_p90` | pct(90, ‖eᵢ‖) | — |
| B.12 | `edge_len_3d_iqr` | p75 − p25 | Spread. |
| B.13 | `edge_len_2d_min_m` | min ‖eᵢ_xz‖ | XZ smallest. |
| B.14 | `edge_len_2d_max_m` | max ‖eᵢ_xz‖ | XZ longest. |
| B.15 | `edge_len_2d_mean_m` | mean ‖eᵢ_xz‖ | — |
| B.16 | `edge_len_2d_std_m` | std ‖eᵢ_xz‖ | — |
| B.17 | `ridge_edge_len_3d_m` | length of longest near-horizontal edge at max-Y band | Ridge dimension. |
| B.18 | `ridge_edge_len_2d_m` | same, projected to XZ | Ridge footprint. |
| B.19 | `ridge_edge_azimuth_deg` | atan2 of ridge-edge direction | Ridge orientation. |
| B.20 | `eave_edge_len_3d_m` | longest near-horizontal edge at min-Y band | Eave dimension. |
| B.21 | `eave_edge_len_2d_m` | same in XZ | Eave footprint. |
| B.22 | `eave_edge_azimuth_deg` | atan2 of eave-edge direction | Eave orientation. |
| B.23 | `ridge_vs_eave_azimuth_diff_deg` | angle_diff(ridge_az, eave_az) | Should ≈ 0° for simple slopes. |
| B.24 | `hip_edge_count` | edges with 5° < incl < eave-band | Hipped/valley count. |
| B.25 | `rake_edge_count` | vertical-ish edges (incl > 60°) | Gable rake count. |
| B.26 | `horizontal_edge_count` | edges with incl < 5° | Level edges. |
| B.27 | `sloped_edge_count` | edges with incl ≥ 5° | Inclined edges. |
| B.28 | `edge_azimuth_histogram_[8bin]` | 8-bin histogram | Directional distribution. |
| B.29 | `edge_azimuth_entropy` | Shannon entropy of 8-bin histogram | Directionality randomness. |
| B.30 | `dominant_edge_direction_deg` | mode of azimuth histogram | Primary edge direction. |
| B.31 | `dominant_edge_freq` | count in dominant bin | Dominance strength. |
| B.32 | `parallel_edge_pair_count` | pairs within 10° of parallel | Ridge/eave parallelism. |
| B.33 | `perpendicular_edge_pair_count` | pairs within 10° of 90° | Right-angle count. |
| B.34 | `turning_angle_mean_deg` | mean interior turn | Regularity. |
| B.35 | `turning_angle_std_deg` | std interior turn | Irregularity. |
| B.36 | `turning_angle_min_deg` | sharpest corner | — |
| B.37 | `turning_angle_max_deg` | most obtuse corner | — |
| B.38 | `collinear_run_max` | longest sequence of <1°-deviation edges | Line-like runs. |
| B.39 | `douglas_peucker_reduction_ratio` | N / N_simplified @ 5cm | Vertex redundancy. |
| B.40 | `douglas_peucker_reduction_ratio_1cm` | @ 1cm | Finer scale. |
| B.41 | `total_perimeter_3d_m` | Σ ‖eᵢ‖ | — |
| B.42 | `total_perimeter_2d_m` | Σ ‖eᵢ_xz‖ | — |
| B.43 | `perimeter_rise_m` | max(yᵢ) − min(yᵢ) | Vertical span. |
| B.44 | `perimeter_rise_ratio` | rise / total_perimeter_3d | Normalized slope. |
| B.45 | `longest_edge_as_pct_perimeter` | max(‖eᵢ‖) / Σ | Single-edge dominance. |
| B.46 | `shortest_edge_as_pct_perimeter` | min(‖eᵢ‖) / Σ | — |
| B.47 | `longest_to_shortest_edge_ratio` | max / min | Edge-length spread. |
| B.48 | `edge_incl_mean_deg` | mean of per-edge inclinations | — |
| B.49 | `edge_incl_std_deg` | std of inclinations | — |
| B.50 | `edge_incl_max_deg` | max inclination edge | — |
| B.51 | `x_span_m` | max(x) − min(x) | XZ footprint X extent. |
| B.52 | `z_span_m` | max(z) − min(z) | XZ footprint Z extent. |
| B.53 | `xz_bbox_aspect` | max-side / min-side | Footprint elongation. |
| B.54 | `ridge_touches_opposing_seam` | max-Y edge shared with opposing plane | Ridge-seam validity. |
| B.55 | `ridge_edge_is_horizontal` | abs(ridge_edge_incl) < 2° | Proper ridge check. |
| B.56 | `total_edge_length_per_area` | perimeter_3d / area_3d | Boundary density. |

### C. Vertex / corner geometry (30 features)

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| C.1 | `vertex_count` | len(corners) | Polygon complexity. |
| C.2 | `interior_angle_mean_deg` | mean over corners | Regularity. |
| C.3 | `interior_angle_std_deg` | std over corners | Irregularity. |
| C.4 | `interior_angle_min_deg` | sharpest corner | Potential degeneracy. |
| C.5 | `interior_angle_max_deg` | most obtuse corner | — |
| C.6 | `convex_vertex_count` | angles < 180° | Convexity count. |
| C.7 | `reflex_vertex_count` | angles > 180° | Concavity count. |
| C.8 | `convexity_ratio` | convex / total | Rectangularity. |
| C.9 | `max_y_vertex_index` | argmax y | Ridge apex position. |
| C.10 | `min_y_vertex_index` | argmin y | Eave foot position. |
| C.11 | `max_y_vertex_count` | count of vertices at max_y (within ε) | Multi-vertex ridge. |
| C.12 | `min_y_vertex_count` | count at min_y (within ε) | Multi-vertex eave. |
| C.13 | `vertex_y_range_m` | max(y) − min(y) | Height span. |
| C.14 | `vertex_y_mean_m` | mean y | Central elevation. |
| C.15 | `vertex_y_median_m` | median y | — |
| C.16 | `vertex_y_std_m` | std y | Height variation. |
| C.17 | `vertex_y_cluster_count` | # modes in Y-histogram @ 0.1m bins | Multi-level ridges. |
| C.18 | `vertex_to_plane_rms_m` | √mean((a·x + b·y + c·z + d)²) | Coplanarity (lower = cleaner). |
| C.19 | `vertex_to_plane_max_m` | max abs residual | Worst outlier. |
| C.20 | `is_perfectly_planar` | max residual < 1cm | Boolean. |
| C.21 | `symmetry_x_axis_score` | reflection matching score around centroid X | Rectangular symmetry. |
| C.22 | `symmetry_z_axis_score` | — around centroid Z | — |
| C.23 | `point_symmetry_score` | 180° rotation matching | Central symmetry. |
| C.24 | `vertex_centroid_x_m` | mean(x) | — |
| C.25 | `vertex_centroid_z_m` | mean(z) | — |
| C.26 | `vertex_centroid_y_m` | mean(y) | — |
| C.27 | `min_dist_centroid_to_vertex_m` | min ‖vᵢ − centroid‖ | — |
| C.28 | `max_dist_centroid_to_vertex_m` | max ‖vᵢ − centroid‖ | — |
| C.29 | `eccentricity` | max / min distance | Elliptical elongation. |
| C.30 | `vertex_count_at_min_y` | count of vertices at eave band | Eave complexity. |

### D. Face / polygon geometry (48 features)

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| D.1 | `area_3d_m2` | Shoelace on 3D corners lifted to plane | True surface area. |
| D.2 | `area_2d_xz_m2` | Shoelace on XZ projection (= `features_snapshot['area_m2']`) | Footprint area. |
| D.3 | `projection_ratio` | area_3d / area_2d | Slope multiplier (1/cos incl). |
| D.4 | `perimeter_3d_m` | Σ ‖eᵢ‖ | — |
| D.5 | `perimeter_2d_m` | Σ ‖eᵢ_xz‖ | — |
| D.6 | `compactness_2d` | 4π·area / perimeter² | Shape regularity (0=thin ribbon, 1=circle). |
| D.7 | `compactness_3d` | 4π·area_3d / perimeter_3d² | 3D analog. |
| D.8 | `convex_hull_area_2d` | Shapely convex_hull.area | — |
| D.9 | `convex_hull_area_3d` | 3D convex hull projection | — |
| D.10 | `convex_hull_ratio` | area_2d / convex_hull_area | 1 = convex, <1 = concave. |
| D.11 | `min_rotated_rect_major_m` | Shapely minimum_rotated_rectangle | Tightest bbox major axis. |
| D.12 | `min_rotated_rect_minor_m` | — | Minor axis. |
| D.13 | `min_rotated_rect_aspect` | major / minor | Elongation. |
| D.14 | `min_rotated_rect_azimuth_deg` | atan2 of major edge | Primary axis direction. |
| D.15 | `bbox_xz_width_m` | max(x) − min(x) | — |
| D.16 | `bbox_xz_height_m` | max(z) − min(z) | — |
| D.17 | `bbox_xz_aspect` | max / min side | — |
| D.18 | `bbox_3d_volume_m3` | x_extent · y_extent · z_extent | Envelope volume. |
| D.19 | `polygon_type_triangle` | vertex_count == 3 | Degenerate check. |
| D.20 | `polygon_type_quad` | vertex_count == 4 | Simple gable. |
| D.21 | `polygon_type_pentagon_plus` | vertex_count ≥ 5 | Complex facet. |
| D.22 | `is_trapezoid_xz` | exactly one pair of parallel edges in XZ | Mono-pitch indicator. |
| D.23 | `is_rectangle_xz` | 4 vertices with ~90° angles and parallel pairs | Simple slope. |
| D.24 | `is_right_trapezoid_xz` | 2 right angles + 1 parallel pair | — |
| D.25 | `hole_count` | Shapely interiors count | Usually 0 for roofs. |
| D.26 | `hu_moment_1..7` | 7 scale/rotation-invariant image moments | Shape descriptor. (counts as 7 features D.26–D.32) |
| D.33 | `elongation_pca_ratio` | λ_max / λ_min from PCA on vertices | Inertial elongation. |
| D.34 | `circularity` | perimeter² / (4π·area) | 1 = circle; higher = more complex. |
| D.35 | `solidity` | area / convex_hull_area | = D.10. |
| D.36 | `extent` | area / bbox_area | Fill factor. |
| D.37 | `perimeter_to_area_ratio` | perimeter / area | Boundary density. |
| D.38 | `isoperimetric_ratio` | perimeter / (2√(π·area)) | Deviation from optimal circle. |
| D.39 | `fractal_dimension` | log–log box-count slope | Edge roughness. |
| D.40 | `area_weighted_centroid_xz` | from triangulation | True center of mass. |
| D.41 | `centroid_to_bbox_center_offset_m` | ‖centroid − bbox_center‖ | Asymmetry. |
| D.42 | `polygon_is_ccw` | shoelace sign > 0 | Winding order. |
| D.43 | `polygon_is_valid_xz` | Shapely `is_valid` | Validity check. |
| D.44 | `polygon_is_simple_xz` | no self-intersection | — |
| D.45 | `triangulated_max_triangle_area_m2` | max triangle in Delaunay | Largest face. |
| D.46 | `triangulated_min_triangle_area_m2` | min triangle | Smallest face. |
| D.47 | `triangulated_mean_triangle_area_m2` | mean | — |
| D.48 | `triangulated_triangle_count` | number of triangles | Mesh complexity. |

### E. 3D position relative to building (28 features)

Computed from `segment_corners_xyz` + `building_boundary_xz` + the list of all rooms/stories for this building (available from the label record's `part_count`, `part_index`, and room_boundary_refs[0].story).

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| E.1 | `min_y_m` | min over corners | Eave elevation. |
| E.2 | `max_y_m` | max over corners | Ridge elevation. |
| E.3 | `mean_y_m` | mean over corners | — |
| E.4 | `median_y_m` | median | — |
| E.5 | `centroid_xz_inside_building_footprint` | point-in-polygon test vs `building_boundary_xz` | Interior check. |
| E.6 | `fraction_inside_building_footprint` | (segment_xz ∩ boundary).area / segment.area | Overhang fraction. |
| E.7 | `fraction_outside_building_footprint` | 1 − fraction_inside | Overhang fraction. |
| E.8 | `is_overhang` | fraction_outside > 0.05 | Boolean. |
| E.9 | `max_overhang_distance_m` | max dist of outside corner to boundary | Maximum overhang. |
| E.10 | `overhang_area_m2` | area of segment XZ outside boundary | — |
| E.11 | `signed_distance_centroid_to_boundary_m` | negative inside, positive outside | Geometric position. |
| E.12 | `distance_centroid_to_nearest_boundary_corner_m` | min over boundary corners | Proximity. |
| E.13 | `building_centroid_xz` | mean of boundary polygon points | — |
| E.14 | `centroid_to_building_centroid_distance_m` | ‖segment_centroid − building_centroid‖ | — |
| E.15 | `azimuth_from_building_centroid_deg` | atan2(Δx, Δz) | Which side of building. |
| E.16 | `relative_story_index` | room_boundary_refs[0].story (can also compute from context) | 0 = topmost. |
| E.17 | `is_top_story` | relative_story_index == 0 | Boolean. |
| E.18 | `is_bottom_story` | story == 0 | Rare for roofs; red flag. |
| E.19 | `story_span` | max − min of member_snapshots stories | Cluster vertical extent. |
| E.20 | `is_multi_story_cluster` | story_span > 0 | Suspicious for a single roof face. |
| E.21 | `part_count` | field | — |
| E.22 | `part_index` | field | — |
| E.23 | `is_multi_part_building` | part_count > 1 | Context. |
| E.24 | `fraction_polygon_with_floor_above` | count of corners where slab above exists / total | Coverage check. |
| E.25 | `fraction_polygon_with_floor_below` | corners with slab below / total | — |
| E.26 | `floor_y_below_segment_min_m` | nearest slab floor_y under segment | Floor clearance. |
| E.27 | `ceiling_y_above_segment_max_m` | nearest slab ceiling_y above segment | Headroom. |
| E.28 | `segment_max_y_equals_building_max_y` | within 0.1m of building max | True roof peak? |

### F. Neighbor / adjacency signals (33 features)

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| F.1 | `opposing_count` | = `features_snapshot['opposing_cluster_count']` | Ridge complexity. |
| F.2 | `opposing_azimuth_mean_deg` | mean azimuth of opposing plane normals | — |
| F.3 | `opposing_azimuth_std_deg` | std | — |
| F.4 | `opposing_azimuth_spread_deg` | max − min | Diversity of opposite faces. |
| F.5 | `opposing_incl_mean_deg` | mean of opposing inclinations | — |
| F.6 | `opposing_incl_std_deg` | std | — |
| F.7 | `opposing_incl_spread_deg` | max − min | — |
| F.8 | `opposing_d_spread_m` | max − min of opposing `d` | Vertical offset spread. |
| F.9 | `dihedral_mean_deg` | mean dihedral (see A.35) | — |
| F.10 | `dihedral_std_deg` | std | — |
| F.11 | `dihedral_min_deg` | sharpest | — |
| F.12 | `dihedral_max_deg` | shallowest | — |
| F.13 | `opposing_seam_length_3d_m` | Σ length of plane-plane intersection lines clipped to segment | Total ridge length. |
| F.14 | `opposing_seam_length_2d_m` | in XZ | — |
| F.15 | `ridge_is_horizontal` | abs(seam direction Y) < 0.05 | Proper ridge orientation. |
| F.16 | `same_cluster_sibling_count` | members of same cluster_canonical_id that produced other segments | — |
| F.17 | `same_cluster_sibling_shared_boundary_m` | total shared edge length | — |
| F.18 | `other_cluster_neighbor_count_xz` | different clusters sharing an XZ edge (within ε) | — |
| F.19 | `other_cluster_neighbor_touching_length_m` | sum of shared lengths | — |
| F.20 | `touching_room_count` | distinct `room_boundary_refs` | Piece fragmentation. |
| F.21 | `touching_gap_count` | gap-kind refs | Void coverage. |
| F.22 | `touching_part_boundary` | segment XZ crosses a part boundary | — |
| F.23 | `rain_hitting_side_count` | = B1.41 | — |
| F.24 | `covered_side_count` | = B1.42 | — |
| F.25 | `rain_to_covered_ratio` | rain / (rain + covered + ε) | Side-type balance. |
| F.26 | `has_ridge_seam` | rain_hitting_side_count > 0 | Boolean. |
| F.27 | `has_valley_seam` | covered_side_count > 0 AND dihedral < 180° | Valley detection. |
| F.28 | `side_pieces_count` | len(side_pieces) | — |
| F.29 | `opposing_avg_azimuth_diff_from_segment_deg` | mean dihedral to opposing by azimuth | — |
| F.30 | `max_opposing_d_abs_m` | max \|d\| of opposing planes | — |
| F.31 | `has_convex_ridge_pair` | any dihedral with convex sign | Convex ridge. |
| F.32 | `has_concave_valley_pair` | any with concave sign | Valley indicator. |
| F.33 | `member_proposal_xz_adjacency_count` | for each member, count adjacent-member XZ neighbors | Cluster density proxy. |

### G. Source-wall / member aggregates (42 features)

All computed by iterating `member_snapshots` and aggregating.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| G.1 | `member_count` | len | — |
| G.2 | `unique_source_room_count` | distinct source_room_id | — |
| G.3 | `unique_source_wall_count` | distinct source_wall_id | — |
| G.4 | `unique_source_story_count` | distinct features.segment_story | — |
| G.5 | `unique_target_slab_count` | distinct slab_id | — |
| G.6 | `source_wall_azimuth_mean_deg` | mean of segment_azimuth_deg | Primary wall orientation. |
| G.7 | `source_wall_azimuth_std_deg` | std | — |
| G.8 | `source_wall_azimuth_spread_deg` | max − min | — |
| G.9 | `source_wall_length_sum_m` | Σ segment_length_m | Coverage. |
| G.10 | `source_wall_length_mean_m` | mean | — |
| G.11 | `source_wall_length_std_m` | std | — |
| G.12 | `source_wall_top_y_mean_m` | mean segment_mid_y_m | — |
| G.13 | `source_wall_top_y_std_m` | std | — |
| G.14 | `source_wall_top_y_range_m` | max − min | — |
| G.15 | `member_plane_azimuth_std_deg` | std azimuth of member planes (pre-merge) | Coplanarity proxy. |
| G.16 | `member_plane_incl_std_deg` | std inclination | — |
| G.17 | `member_plane_d_std_m` | std d | — |
| G.18 | `member_area_sum_m2` | Σ member piece_area_m2 | Total proposed coverage. |
| G.19 | `member_area_mean_m2` | mean | — |
| G.20 | `member_area_max_m2` | max | — |
| G.21 | `member_area_min_m2` | min | Noise floor. |
| G.22 | `member_area_std_m2` | std | — |
| G.23 | `member_area_to_merged_area_ratio` | sum / area_m2 | Redundancy. |
| G.24 | `heuristic_accepted_member_fraction` | count(accepted) / total | — |
| G.25 | `heuristic_rejected_member_fraction` | count(rejected) / total | — |
| G.26 | `heuristic_not_evaluated_member_fraction` | count(not_evaluated) / total | Cluster uncertainty. |
| G.27 | `heuristic_label_entropy` | Shannon entropy of member label distribution | — |
| G.28 | `source_rooms_area_sum_m2` | Σ slab_area of unique source rooms | — |
| G.29 | `source_rooms_floor_y_mean_m` | mean slab_floor_y_m | — |
| G.30 | `source_rooms_floor_y_std_m` | std | — |
| G.31 | `story_delta_mean` | mean of features.story_delta | — |
| G.32 | `story_delta_max` | max | — |
| G.33 | `story_delta_nonzero_fraction` | count(story_delta != 0) / total | Cross-story member fraction. |
| G.34 | `plane_height_above_slab_mean_m` | mean of member plane_height_above_slab | — |
| G.35 | `plane_height_above_slab_std_m` | std | — |
| G.36 | `slant_delta_mean_m` | mean slant_delta_over_piece_m | — |
| G.37 | `slant_delta_std_m` | std | — |
| G.38 | `rain_exposure_ratio_mean` | mean rain_exposure_ratio | — |
| G.39 | `rain_exposure_ratio_min` | min | Weakest coverage. |
| G.40 | `piece_compactness_mean` | mean piece_compactness | — |
| G.41 | `piece_min_width_min_m` | min piece_min_width_m | Thinnest ribbon. |
| G.42 | `is_same_room_fraction` | count(is_same_room) / total | Self-ceiling ratio. |

### H. Cluster quality (18 features)

Restating member aggregates with cluster framing, plus cluster-specific XZ union metrics.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| H.1 | `cluster_member_count` | = G.1 | — |
| H.2 | `cluster_azimuth_spread_deg` | = G.8 | — |
| H.3 | `cluster_incl_spread_deg` | std of member inclinations | — |
| H.4 | `cluster_d_spread_m` | std of normalized d | Coplanarity tightness. |
| H.5 | `cluster_source_room_count` | = G.2 | — |
| H.6 | `cluster_source_wall_count` | = G.3 | — |
| H.7 | `cluster_source_story_count` | = G.4 | — |
| H.8 | `cluster_pre_clip_xz_area_m2` | Σ union of member corners (XZ) | Original cluster size. |
| H.9 | `cluster_post_clip_xz_area_m2` | area_m2 (segment-level) | — |
| H.10 | `cluster_clip_ratio` | post / pre | Boundary-clip impact. |
| H.11 | `cluster_compactness_xz` | 4π·pre_area / pre_perimeter² | Cluster shape regularity. |
| H.12 | `cluster_convex_hull_ratio` | pre_area / pre_hull_area | — |
| H.13 | `cluster_member_heuristic_accept_fraction` | = G.24 | — |
| H.14 | `cluster_member_heuristic_entropy` | = G.27 | — |
| H.15 | `cluster_is_multi_part` | members span multiple part_index | — |
| H.16 | `cluster_is_multi_story` | members span multiple stories | — |
| H.17 | `cluster_normal_dot_min_actual` | min over member plane dots with merged_plane | Tightest actual dot. |
| H.18 | `cluster_d_abs_max_actual` | max abs member.d − merged.d | Widest actual d offset. |

### I. Physics / drainage (18 features)

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| I.1 | `water_flow_dir_xz` | (A.21) | — |
| I.2 | `water_flow_azimuth_deg` | (A.20) | — |
| I.3 | `drainage_vector_to_building_centroid` | `building_centroid − segment_centroid` | — |
| I.4 | `drainage_flow_dot_centroid_offset` | water_flow · drainage_vector | Pos = drains toward center, neg = away. |
| I.5 | `sheds_water_away_from_building` | drainage_flow_dot > 0 | Boolean. |
| I.6 | `drainage_efficiency` | \|dot\| / (‖flow‖·‖drag‖) | Cosine alignment. |
| I.7 | `eave_xz_distance_to_nearest_source_wall_m` | min over source-wall XZ lines | Overhang. |
| I.8 | `eave_edge_outside_footprint_length_m` | eave segment length outside building_boundary_xz | — |
| I.9 | `wall_top_coverage_ratio` | (segment_xz ∩ union(source-wall tops)).area / segment_xz.area | Roof-over-wall fraction. |
| I.10 | `wall_top_coverage_of_eave_edge` | same, restricted to 0.5m band around eave_edge | — |
| I.11 | `eave_height_m` | min(y) over corners | — |
| I.12 | `ridge_height_m` | max(y) over corners | — |
| I.13 | `eave_to_ridge_height_m` | ridge − eave | — |
| I.14 | `ridge_is_below_building_max` | ridge_height < building_max_y − 0.1m | Is this under a higher roof? |
| I.15 | `drainage_to_nearest_opposing_seam` | is drainage vector pointing toward a ridge or away? | — |
| I.16 | `plane_slope_direction_consistent_with_ridge_and_eave` | cross(ridge_edge, eave_edge) aligned with plane normal | — |
| I.17 | `sun_exposure_azimuth_alignment_deg` | angle_diff(az, 180°) for Northern Hemisphere south-facing ideal | Solar prior. |
| I.18 | `prevailing_wind_alignment_deg` | angle_diff(az, wind_azimuth) | If we have site-specific wind data. |

### J. Record meta / record-level (11 features)

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| J.1 | `piece_kind` | = B1.39 | room vs gap. |
| J.2 | `is_split_child` | proposal_id contains "#" | User manually split parent. |
| J.3 | `split_depth` | count of "#" occurrences | Depth of recursive splits. |
| J.4 | `merge_mode` | bool field | Was merge mode on? |
| J.5 | `labeler` | str | One-hot or grouped. |
| J.6 | `label_ts_epoch` | converted | Temporal feature. |
| J.7 | `has_reasons` | len(reasons) > 0 | **Always false today.** |
| J.8 | `part_index` | int | — |
| J.9 | `part_count` | int | Building part complexity. |
| J.10 | `part_index_is_zero` | bool | Main part? |
| J.11 | `is_merge_vs_proposal` | kind == "merged" | Record type. |

---

## Part III — Band 3: Features requiring pipeline/results re-read

Features that need additional signals from `reconcile_v3_results.json` and `buildings_3d.json` beyond what the label record embeds.

### K. Architectural priors (22 features)

| # | Feature | Source | Rationale |
|---|---|---|---|
| K.1 | `part_gable_status` | `V3Part.gable_extension.status` ∈ {not_gable, gable_complete, gable_along_extend, gable_cross_review, gable_ambiguous} | 5-way. |
| K.2 | `part_gable_n_slanted_roofs` | `V3Part.gable_extension.metrics['n_slanted_roofs']` | Number of slanted roofs on this part. |
| K.3 | `part_gable_az0` / `az1` | metrics | Azimuth of the two gable slopes. |
| K.4 | `part_gable_incl0` / `incl1` | metrics | Inclinations. |
| K.5 | `part_gable_daz180` | metrics | Opposing-slope angular gap. |
| K.6 | `part_gable_dincl` | metrics | Inclination mismatch. |
| K.7 | `part_gable_ridge_y_abs` | metrics['ridge_y_abs'] | Horizontality of ridge. |
| K.8 | `part_gable_ridge_az` | metrics | Ridge azimuth. |
| K.9 | `part_gable_ridge_vs_expected_deg` | metrics | Ridge alignment with expected. |
| K.10 | `part_gable_major_m` / `minor_m` | metrics | Footprint OBB dims. |
| K.11 | `part_gable_elong` | metrics | major / minor. |
| K.12 | `part_gable_ridge_vs_major_deg` | metrics | Ridge aligned with footprint major axis? |
| K.13 | `part_gable_coverage` | metrics | Fraction of part footprint covered by the two roofs. |
| K.14 | `part_gable_n_dormers` | metrics | Dormers on this part. |
| K.15 | `part_gable_n_arch_flats` | metrics | Architectural flat ceilings on top story of this part. |
| K.16 | `slope_hypothesis_confidence` | `SlopeHypothesis.confidence` for source room | 0–1 confidence. |
| K.17 | `slope_hypothesis_has_cluster_source` | "cluster" in sources | Scan-derived slope evidence. |
| K.18 | `slope_hypothesis_has_asymmetry_source` | "wall_height_asymmetry" | — |
| K.19 | `slope_hypothesis_has_missing_wall_source` | "missing_wall" | — |
| K.20 | `slope_hypothesis_plane_exists` | plane is not None | — |
| K.21 | `slope_hypothesis_cluster_index` | cluster_index | Which cluster. |
| K.22 | `slope_hypothesis_direction_alignment_with_segment_deg` | angle between SlopeHypothesis.direction_xz and plane-downslope direction | — |

### L. Kneewall / dormer / extension adjacency (14 features)

| # | Feature | Source | Rationale |
|---|---|---|---|
| L.1 | `kneewall_below_count` | count of `V3WallExtension` with `behind_knee_wall == True` under segment XZ | Attic below. |
| L.2 | `kneewall_beside_count` | kneewalls within 0.5m of segment eave | — |
| L.3 | `is_above_kneewall` | kneewall_below_count > 0 | Boolean. |
| L.4 | `wall_extension_overlap_count` | `V3WallExtension` XZ ∩ segment non-empty | — |
| L.5 | `wall_extension_overlap_area_m2` | sum of overlap areas | — |
| L.6 | `dormer_count_on_plane` | `V3Dormer` with `roof_surface_id` == this cluster's primary slanted_roof | — |
| L.7 | `dormer_count_under_segment` | `V3Dormer` corners XZ ∩ segment non-empty | — |
| L.8 | `min_distance_to_dormer_xz_m` | min over dormers | — |
| L.9 | `is_dormer_adjacent` | distance < 0.5m | Boolean. |
| L.10 | `flat_ceiling_beneath_overlap_m2` | `V3FlatCeiling` with overlap in XZ and y below segment | Under-ceiling check. |
| L.11 | `slanted_roof_beneath_overlap_m2` | existing `V3SlantedRoof` XZ ∩ segment, y below | Roof-over-roof conflict. |
| L.12 | `is_under_existing_slanted_roof` | slanted_roof_overlap > 0 | Suspicious. |
| L.13 | `overlap_with_unresolved_region_m2` | `V3UnresolvedRegion` XZ ∩ segment | Unresolved below. |
| L.14 | `v3_slanted_roof_id_this_covers` | element_id of best-matching V3SlantedRoof | Ground-truth link. |

### M. Roof-coverage-graph evidence tier (6 features)

From `reconcile/roof_algorithms_py/roof_coverage_graph.py::build_roof_coverage_graph`:

| # | Feature | Source | Rationale |
|---|---|---|---|
| M.1 | `roof_evidence_sloped_state` | atom.sloped_state ∈ {none, weak, partial, confirmed} | Evidence tier. |
| M.2 | `roof_evidence_sloped_overlap_ratio` | atom.sloped_overlap_ratio | — |
| M.3 | `roof_evidence_sloped_vertical_clearance_m` | atom.sloped_vertical_clearance_m | Height above atom. |
| M.4 | `roof_evidence_sloped_part_match` | atom.sloped_part_match | Same building part. |
| M.5 | `roof_evidence_flat_shell_overlap_ratio` | atom.flat_shell_overlap_ratio | — |
| M.6 | `roof_evidence_tier_bucket` | 0=none, 1=weak, 2=partial, 3=confirmed | Ordinal. |

### N. Building-level shape priors (22 features)

Per `building_uuid` from `reconcile/buildings_3d.json` + union of all V3 slabs.

| # | Feature | Source | Rationale |
|---|---|---|---|
| N.1 | `building_footprint_area_m2` | union of slab XZ areas | — |
| N.2 | `building_footprint_perimeter_m` | perimeter of union | — |
| N.3 | `building_footprint_compactness` | 4π·area / perimeter² | — |
| N.4 | `building_footprint_bbox_aspect` | — | Elongation direction. |
| N.5 | `building_footprint_convexity` | area / hull_area | — |
| N.6 | `building_footprint_concavity_corner_count` | reflex vertices in hull−footprint | Shape complexity. |
| N.7 | `building_footprint_has_L_shape` | heuristic (2 concavities, 90° each) | — |
| N.8 | `building_footprint_has_T_shape` | (3 concavities) | — |
| N.9 | `building_footprint_has_U_shape` | — | — |
| N.10 | `building_footprint_has_E_shape` | — | — |
| N.11 | `building_part_count` | len(V3Building.parts) | — |
| N.12 | `building_story_count` | distinct stories | — |
| N.13 | `building_room_count` | len(V3Building rooms) | — |
| N.14 | `building_gap_count` | len(V3Building.gaps) | — |
| N.15 | `building_min_y_m` | min over all rooms/slabs | — |
| N.16 | `building_max_y_m` | max over all corners | — |
| N.17 | `building_height_m` | max − min | — |
| N.18 | `building_mean_story_height_m` | height / story_count | — |
| N.19 | `building_principal_axis_azimuth_deg` | from covariance of footprint vertices | Orientation. |
| N.20 | `building_elongation_ratio` | λ_max / λ_min | — |
| N.21 | `building_address_has_value` | bool | — |
| N.22 | `building_classification` | str from V3Input.classification | BBR code if present (one-hot). |

### O. Upstream-scan quality (7 features)

From `reconcile/buildings_3d.json` top-level per-UUID stats:

| # | Feature | Source | Rationale |
|---|---|---|---|
| O.1 | `scan_stories_found` | int | — |
| O.2 | `scan_rooms_found` | int | — |
| O.3 | `scan_cross_floor_gaps` | int | Stitch quality. |
| O.4 | `scan_stitch_walls` | int | — |
| O.5 | `scan_gap_walls` | int | — |
| O.6 | `scan_exterior_gap_indicators` | int | — |
| O.7 | `scan_overlap_metrics` | dict (coverage, excess, etc.) | — |

---

## Part IV — Band 4: Features from academic literature

Features used in published roof-plane classifiers, mapped to our codebase. Many duplicate Bands 2–3 under different names; the mapping column makes the overlap explicit. Uniquely literature-only features (like per-point eigenvalue features) are flagged **NO POINT CLOUD** — they are out of scope because RoomPlan gives us vector geometry, not raw points.

### P.1 Per-point geometric features (eigenvalue/covariance)

Out of scope (no point-cloud data). Flagged for completeness. [Weinmann 2017, PDAL]

- λ1, λ2, λ3, Σλ, omnivariance, eigenentropy, anisotropy, planarity, linearity, sphericity, surface variation, curvature, verticality, normal.

### P.2 Per-plane primitive features (mapping)

| Literature name | Band 2/3 equivalent | Citation |
|---|---|---|
| Plane normal n | A.6–A.10 | All |
| Plane offset d | A.9 | All |
| Inlier count / inlier ratio | G.1 (member_count) | Xu, PolyFit, Goebbels |
| RMS residual | C.18 (vertex_to_plane_rms) | Dehbi, City3D |
| α-shape boundary | D.8 (convex hull — approx), D.40 | Dehbi |
| Plane perimeter | D.4/D.5 | Standard |
| Aspect ratio of plane footprint | D.13 (min_rotated_rect_aspect) | Li (PhD), SIGGRAPH A21 |
| Elongation | D.33 | Standard |
| Compactness | D.6 | SIGGRAPH A21 |
| Convexity | D.10 | Standard |
| **Hu moments** | D.26–D.32 | Standard |
| Min / max / mean elevation | E.1/E.2/E.3 | Ridge-based decomposition |
| Plane inclination | A.2 | HRTT, OSM |
| Plane azimuth / aspect | A.1 | HRTT, OSM |
| **Pitch ratio rise/run** | A.3 | OSM roof:angle |
| Vertical alignment score | A.24 | City3D |
| Plane confidence / support | (new — need member-level residuals) | PolyFit |
| **Footprint-alignment azimuth residual (threshold 5°)** | **new: A.37** | Goebbels 2020 |
| Parallelism to footprint edge | new: B.32 applied to source walls | Goebbels |
| Orthogonality to footprint edge | new | Goebbels |
| Vertical / horizontal / tilted label | A.14 | HRTT |

### P.3 Per-plane-pair / pairwise features

| Literature name | Band 2/3 equivalent | Citation |
|---|---|---|
| **Dihedral angle** | A.33–A.36 (to opposing) | Dehbi, HRTT |
| **Sign of dihedral (convex/concave)** | F.31/F.32 | Yan 2021, HRTT |
| **Intersection line (ridge hypothesis)** | F.13 (opposing_seam_length) | Dehbi, HRTT |
| Intersection-line orientation (horizontal/oblique) | B.54 (ridge_touches_opposing), F.15 | HRTT |
| **Intersection-line length** | F.13 | Graph-edit 2014 |
| Ridge coverage ratio | (new — requires per-plane inlier span along seam) | Dehbi |
| Step-edge height difference | (new) | Graph-edit |
| Coplanarity | H.4/H.17/H.18 | Sampath, FastReg |
| Parallelism | F.2 (opposing azimuth diff) | FastReg |
| Orthogonality | F.33 (perpendicular edges to neighbors) | FastReg |
| Shared boundary length | F.17/F.19 | Yan 2021 |

### P.4 Topological/graph features

Partially applicable; we have adjacency via opposing_planes and same_cluster siblings.

| Literature name | Band 2/3 equivalent | Citation |
|---|---|---|
| Node degree | F.1 + F.16 | Graph-edit |
| **Edge type taxonomy (ridge/hip/valley/eave/step/gap)** | (new — derive from dihedral sign × opposing azimuth × orientation) | HRTT, P26 |
| Sub-graph isomorphism to primitive template | (new, if we build a template library) | HRTT, SIGGRAPH A21 |
| Connected-component membership | H.15/H.16 | Sampath |

### P.5 Boundary / polygon descriptors

| Literature name | Band 2/3 equivalent | Citation |
|---|---|---|
| α-shape polygon | D.9 (approx via convex hull) | Dehbi |
| Concave hull | new Shapely op | — |
| Convex hull | D.8 | — |
| Boundary point count | D.1 | RoofSeg |
| Boundary curvature / smoothness | B.34/B.35 | RoofSeg |
| Number of edges after polygonization | D.40 (douglas_peucker_reduction) | PolyFit |
| **Vertex regularity (right-angle count)** | B.33, D.23 | FastReg |

### P.6 Building-level / contextual

| Literature name | Band 2/3 equivalent | Citation |
|---|---|---|
| Building footprint polygon | N.1 | — |
| Footprint area | N.1 | Roof model rec. |
| Footprint aspect ratio | N.4 | — |
| Footprint convexity | N.5 | — |
| Footprint symmetry axis count | C.21/C.22 applied to building | SIGGRAPH A21 |
| Rectangle decomposition | (new) | P17 |
| **Ridge-direction prior (along/across footprint)** | K.12 (gable_ridge_vs_major_deg) | OSM roof:orientation |
| Cadastral alignment | N.21/N.22 | — |

### P.7 Architectural / semantic labels (target space, not feature)

Out of scope for features, but useful for **error analysis**:

- **OSM roof:shape 22 values**: flat, gabled, skillion, saltbox, hipped, half-hipped, hipped-and-gabled, mansard, gambrel, pyramidal, crosspitched, sawtooth, butterfly, cone, dome, onion, round, many, etc. [OSM wiki]
- **Wikipedia architectural taxonomy 30+ shapes**: adds bonnet, Dutch gable, monitor, barrel, arched/gothic, catenary, bell, helm, pyatthat, karahafu, etc. [Wikipedia]
- **Castagno & Atkins 2018, Sensors**: 8-class classifier (unknown, complex-flat, flat, gabled, half-hipped, hipped, pyramidal, skillion).
- **Li PhD 2025, Purdue**: primitive parameter vector (length, width, ridge height, eave height, overhang, ridge-offset) + hybrid primitive flag.

If we ever build a roof-type classifier, these are the label spaces to consider. Today we have *binary* accept/reject only — no architectural target.

### P.8 Physical / building-sense (all already in Band 2)

| Literature name | Our feature |
|---|---|
| Gravity alignment | A.11/A.24 |
| Oblique surface filter 5° < incl < 80° | A.16/A.17 |
| Eave height | I.11 |
| Ridge height | I.12 |
| Drainage direction consistency | I.5/I.6 |
| Thermal-ceiling / attic presence | L.3 |
| Roof overhang | E.9/I.7 |

### P.9 Solar / downstream (nice-to-have)

| Literature feature | Band 2 |
|---|---|
| Tilt | A.2 |
| Orientation | A.1 |
| Shading fraction | (requires raytracing — out of scope) |
| TOF / TSRF | (out of scope — requires solar model) |

### P.10 Learned / embedding features

Out of scope. We would need:
- PointNet++ 256-d embedding [RoofSeg, Li PhD] — requires raw points.
- Inception-ResNet 1536-d [Castagno] — requires RGB ortho.
- ResNet50 2048-d [Castagno] — requires LiDAR DSM raster.

Not available without upstream changes.

### P.11 Quality-metric / validation features (for evaluating *our classifier*, not the data)

| Literature name | Use |
|---|---|
| Completeness, Correctness, Quality C·K/(C+K−C·K) | For per-building accuracy heatmap in Phase 6. |
| IoU 2D / 3D, Hausdorff, Fréchet, RMSE corners, F1 | Reporting metrics. |

### P.12 Regularity constraints / thresholds from literature

Values we can check for our thresholds against published benchmarks:

- Normal-angle merge threshold: literature typically 5–10° [P1, P2]. Ours: `normal_dot_min=0.94` → ~20°. **Potentially too permissive.**
- Distance merge threshold: 0.1 m [P18]. Ours: `d_abs_max=0.50` m. **Potentially too permissive.**
- Azimuth alignment to footprint: 5° [P18]. We haven't tested this explicitly; **candidate new rule**.
- Opposing cos-azimuth: 0.866 (≈30°). We reject pairs within 30° of parallel. Reasonable.

---

## Part V — Cross-synthesis: top expected signals

Ranked by prior probability of strong signal (combining literature evidence, structural position in the pipeline, and known failure modes from recent bug fixes).

### V.1 Tier 1: almost certainly strong signals (20 features)

| Rank | Feature | Reasoning |
|---|---|---|
| 1 | `plane_incl_deg` (A.2) | Steepness directly filters near-walls (>80°) and near-flats (<5°). Published filters are 5°–80°. |
| 2 | `heuristic_accepted_member_fraction` (G.24) | Cluster-level heuristic consensus — proxy for the current pipeline's belief. |
| 3 | `vertex_to_plane_rms_m` (C.18) | Coplanarity of the polygon vertices with the merged plane. Loose fits are suspect. |
| 4 | `opposing_count` (F.1) | Having ≥1 opposing plane is a strong positive — real roofs form ridges. |
| 5 | `rain_hitting_side_count` (F.23) | Being the rain-catching side of a ridge is a direct "is a real roof" signal. |
| 6 | `wall_top_coverage_ratio` (I.9) | A real roof sits on walls; a rejected piece often doesn't. |
| 7 | `rain_exposure_ratio_mean` (G.38) | Members covering high-rain-exposure pieces are more likely real. |
| 8 | `is_top_story` (E.17) | Roofs live on the top story. Mid-story "roofs" are usually cross-floor gap artifacts. |
| 9 | `piece_min_width_min_m` (G.41) | Ribbon-thin pieces are usually clip noise. |
| 10 | `area_2d_xz_m2` (D.2) | Tiny segments are usually artifacts. |
| 11 | `dihedral_mean_deg` (F.9) | Valid roof dihedral is in a narrow band (~120° for 30° pitches). |
| 12 | `source_wall_azimuth_spread_deg` (G.8) | Tight azimuth spread = real cluster. Wide spread = noise cluster. |
| 13 | `cluster_d_spread_m` (H.4) | Tight d-spread = real coplanar cluster. |
| 14 | `part_gable_status` (K.1) | Part-level gable classification directly colors roof-proposal probability. |
| 15 | `slope_hypothesis_confidence` (K.16) | Room-level slope evidence. |
| 16 | `roof_evidence_sloped_state` (M.1) | Roof-coverage-graph evidence tier (confirmed > partial > weak). |
| 17 | `fraction_inside_building_footprint` (E.6) | Overhangs > ~0.5m are usually bogus. |
| 18 | `is_under_existing_slanted_roof` (L.12) | A proposed roof below an existing accepted roof is contradictory. |
| 19 | `cluster_clip_ratio` (H.10) | Heavy clipping by boundary = proposal was over-extended. |
| 20 | `sheds_water_away_from_centroid` (A.22) | Physics prior — drainage must point outward. |

### V.2 Tier 2: likely useful (next 20)

21. `heuristic_label_entropy` (G.27) — cluster-member disagreement.
22. `is_same_room_fraction` (G.42) — self-ceiling sign.
23. `story_delta_nonzero_fraction` (G.33) — cross-story members are suspicious.
24. `plane_height_above_slab_mean_m` (G.34) — typical roof clearance.
25. `piece_compactness_mean` (G.40).
26. `ridge_edge_is_horizontal` (B.55).
27. `cluster_is_multi_part` (H.15) — multi-part clusters often span incorrect boundaries.
28. `cluster_is_multi_story` (H.16).
29. `is_axis_aligned_xy`/`is_axis_aligned_yz` (A.31/A.32) — degenerate planes.
30. `convex_hull_ratio` (D.10).
31. `min_rotated_rect_aspect` (D.13) — very elongated = ribbon noise.
32. `dormer_count_under_segment` (L.7).
33. `kneewall_below_count` (L.1).
34. `azimuth_from_building_principal_axis_deg` (A.37) — most roofs align with building axes.
35. `fraction_polygon_with_floor_above` (E.24).
36. `segment_max_y_equals_building_max_y` (E.28) — is this actually the highest surface?
37. `building_footprint_compactness` (N.3) — building shape influences roof type.
38. `building_part_count` (N.11).
39. `part_gable_coverage` (K.13).
40. `slope_hypothesis_has_cluster_source` (K.17).

### V.3 Tier 3: speculative / likely noise but cheap to compute (40+)

All remaining Band-2/3 features. Include in the initial feature dump; prune via SHAP + mutual information.

---

## Part VI — Implementation notes and utilities to reuse

### VI.1 Utilities already in the repo (do not reimplement)

| Utility | File | Use for |
|---|---|---|
| `parse_element_id(token)` | `reconcile/element_locator.py` | Round-trip `<uuid>::<kind>::<inner>` with `#` suffixes. |
| `plane_normal(azimuth, incl)` | `reconcile/roof_algorithms_py/math_utils.py` | Azimuth/incl ↔ normal conversion. |
| `angle_diff(a, b)` | `reconcile_v3/stages/gable_extension.py:75` | Mod-180 and mod-360 angular difference. |
| `_polygon_compactness(poly)` | `reconcile_v3/stages/slanted_roof_proposals.py:108` | 4π·area/perimeter². |
| `_polygon_bbox_aspect(poly)` | `slanted_roof_proposals.py:115` | max/min side. |
| `_polygon_min_width(poly)` | `slanted_roof_proposals.py:123` | 2·area/perimeter. |
| `_plane_y_at(point_xz, plane)` | `slanted_roof_proposals.py:237` | Plane height at XZ point. |
| `_slant_delta_over_polygon(poly, plane)` | `slanted_roof_proposals.py:244` | Height range. |
| `_normalized_plane(plane)` | `merged_slanted_roof_proposals.py:63` | Plane normalization with upward normal. |
| `_cos_azimuth(p1, p2)` | `merged_slanted_roof_proposals.py:115` | Azimuth cosine. |
| `_half_plane_for_opposing(own, other)` | `merged_slanted_roof_proposals.py:126` | Opposing-seam separation. |
| `_building_boundary(slabs)` | `merged_slanted_roof_proposals.py:196` | Union of slab XZ. |
| `_collect_rain_exposed_pieces(rooms, gaps)` | `merged_slanted_roof_proposals.py:210` | Piece enumeration. |
| `build_roof_coverage_graph(...)` | `reconcile/roof_algorithms_py/roof_coverage_graph.py` | Evidence tiers. |
| `SlopeHypothesis` | `reconcile_v3/stages/slanted_roofs.py:47` | Per-room slope confidence + sources. |
| `compute_building_y_bounds`, `has_floor_above` | `reconcile_v3/stages/story_index.py` | Building Y bounds & floor-above check. |
| `classify_gable_extension` | `reconcile_v3/stages/gable_extension.py:243` | Part-level gable classification + metrics. |
| Shapely v2 `convex_hull`, `minimum_rotated_rectangle`, `simplify`, `boundary.distance`, `unary_union` | Shapely | Geometric primitives. |

### VI.2 Implementation sketch for Phase 2 (from the plan)

1. **`reconcile_v3/analysis/join.py`** — reads `.context/v3_roof_proposal_labels.jsonl`, last-write-wins, drops skips, resolves split children via splits.jsonl, falls back to `reconcile_v3_results.json` if label record is missing a field. Outputs `artifacts/labels_joined.parquet`.

2. **`reconcile_v3/analysis/feature_expansion.py`** — one function per category (A–O from Part II/III), each taking `(label_record, building_ctx)` and returning a flat dict. Concatenate into one row per label. Outputs `artifacts/features_expanded.parquet`.

3. **Per-building context** — lazy-load `reconcile_v3_results.json` and `buildings_3d.json` once per `building_uuid` and cache. ~70 buildings × modest JSON size = no memory issue.

4. **Validation** — for 5 random labels, recompute all Band-2 features and check ±1e-3 parity with values derived by an independent path (e.g., Shapely vs manual numpy). Write as a unit test.

### VI.3 Dependencies to add

Under a new `analysis` extra in `pyproject.toml`:
- `pandas` — data frame work.
- `pyarrow` — parquet I/O.
- `scikit-learn` — GroupKFold, tree models, mutual information.
- `lightgbm` — gradient boosting (feature importance + SHAP).
- `shap` — SHAP values.
- `matplotlib` — histograms + confusion matrices.

### VI.4 `artifacts/` gitignore

Add `artifacts/` to `.gitignore`. The actual data files are regeneratable from the label store + results.

---

## Part VII — Gaps and limitations

### VII.1 Data gaps

1. **`reasons[]` empty on every label.** No reject-reason taxonomy. We can do binary classification but no error stratification by reason. **Mitigation:** Optional ~1-day viewer pass to retro-tag a stratified subsample with reasons (wrong-azimuth / wrong-footprint / should-be-flat / not-a-roof / covers-wrong-room).
2. **No formal roof-type taxonomy.** We cannot test "gable vs hip vs shed" hypotheses directly; only "accept this segment" or "reject this segment". Part-level `V3Part.gable_extension.status` is the closest thing.
3. **No learned embeddings.** We lack raw point clouds, ortho RGB, and LiDAR DSM. All literature features that require those (P.1, P.10) are out of scope.
4. **No BBR / cadastral metadata per building.** Only `address` and `classification` strings. No year-built, storey count from public registry, or footprint-source confidence.
5. **`heuristic_label` is coarse.** Today it's a three-way flag that compares the segment's source wall against existing V3SlantedRoof objects. It has no confidence score or disagreement-with-cluster information beyond what we can aggregate.
6. **Class imbalance.** 25.35% accepts vs 74.31% rejects. Needs `class_weight='balanced'` or SMOTE in Phase 4.
7. **Building imbalance.** Max 521 labels from one building vs median 60. Needs inverse-weighting by `building_label_count` and GroupKFold by `building_uuid`.
8. **Label drift.** Labels span multiple pipeline revisions. IDs may be stale after regeneration. Mitigated by using embedded provenance in each record.

### VII.2 Structural caveats

9. **Merge thresholds may be too permissive.** Literature uses 5–10° normal-angle and 0.1 m distance; we use ~20° and 0.50 m. Validate by checking if `cluster_d_spread_m` (H.4) or `cluster_incl_spread_deg` (H.3) correlate strongly with rejects.
10. **Split children inherit parent features.** A user-split child has the parent's `merged_plane`, `opposing_planes`, etc. — only `segment_corners_xyz` changes. Features derived purely from corners (Bands B, C, D, E) are child-specific; features from provenance (G, H, K) are inherited. Be explicit about which is which.
11. **`is_multi_story_cluster` is a red flag, not a hard rule.** Some valid clusters span two stories when a roof covers a stairwell.

---

## Part VIII — Prioritized experimental roadmap

### Step 1 — Phase 1–2 of the plan (~2 days)

Build `labels_joined.parquet` and `features_expanded.parquet` with **all Band-1 + Band-2** features (~300). Defer Band-3 architectural priors to Step 2. Reason: Band 2 is a pure function of the label record + numpy/Shapely, trivially parallelizable, and avoids JSON-parse cost per label.

**Verification:** ≥99% of unique labels resolve to a feature row. Spot-check 5 labels end-to-end.

### Step 2 — Add Band 3 (~1 day)

Extend with K/L/M/N/O categories by lazy-loading `reconcile_v3_results.json` and `buildings_3d.json` per `building_uuid`. 70 buildings — trivial.

**Verification:** Per-building context cache hit rate = 100%. Feature parity for 5 more random labels.

### Step 3 — Descriptive stats (Phase 3 of plan)

Per feature: mean/std/median/p5/p95 split by label, Cohen's d for continuous, Cramér's V for categorical, mutual information via sklearn. Output `artifacts/feature_ranking.csv` + top-20 histograms.

**Expected outcome:** Tier-1 predictions from Part V validated (or falsified). If `plane_incl_deg` or `heuristic_accepted_member_fraction` are NOT top-5, something is wrong with feature expansion — investigate before modelling.

### Step 4 — Modelling (Phase 4)

- **GroupKFold by `building_uuid`.**
- **Inverse-weight by `1 / building_label_count`.**
- Model 1: shallow decision tree (max_depth 4–6) — extract rule paths.
- Model 2: LightGBM with `class_weight='balanced'` — feature importance + SHAP.

**Baseline:** heuristic F1. **Target:** beat heuristic by ≥10% absolute F1.

**If target missed:** stop and re-examine features; don't ship a model that barely beats the heuristic.

### Step 5 — Rule extraction (Phase 5)

Extract depth-4 leaves with ≥50 samples and ≥85% purity. Rank by `precision × coverage`. For each, emit:
- rule text ("if `slope_hypothesis_confidence < 2.0` AND `opposing_count == 0` AND `not is_top_story` → reject"),
- support, precision, recall,
- 3 accepting + 3 rejecting example IDs for viewer inspection.

Output: `artifacts/candidate_rules.md`.

### Step 6 — Visual verification

For the top 3 candidate rules, load the 6 example IDs in the viewer. **Required gate before any production change** — spatial errors don't show up in metrics.

### Step 7 — Disagreement audits (Phase 6)

- Heuristic-accept vs user-reject: feature pattern.
- Heuristic-reject vs user-accept: feature pattern.
- Model-accept vs user-reject, model-reject vs user-accept.
- Per-building accuracy heatmap.

Output: `artifacts/disagreements.md`.

### Step 8 — Go/no-go decision

Review `candidate_rules.md` + `disagreements.md` + per-building heatmap. Decide:
- Which rules graduate to proposer/merger logic (via `generalize-before-specialize`: never ship a rule that fires on <10 buildings).
- Whether to spend the budget on a retro-label reasons pass.
- Whether to invest in new Band-3 signals (e.g., computing ridge/hip/valley edge taxonomy explicitly).

---

## Bibliography

### Primary repo references

- `reconcile_v3/models.py` — all V3 dataclasses.
- `reconcile_v3/stages/slanted_roof_proposals.py` — proposer + 25 features.
- `reconcile_v3/stages/merged_slanted_roof_proposals.py` — cluster/split + 9 merged features.
- `reconcile_v3/stages/slanted_roofs.py` — SlopeHypothesis.
- `reconcile_v3/stages/gable_extension.py` — part gable classifier (5-way enum + metrics).
- `reconcile_v3/stages/dormers.py` — V3Dormer.
- `reconcile_v3/stages/wall_extensions.py` — V3WallExtension.behind_knee_wall.
- `reconcile_v3/stages/flat_ceilings.py` — V3FlatCeiling.
- `reconcile_v3/stages/story_index.py` — building Y bounds, floor-above check.
- `reconcile/roof_algorithms_py/roof_coverage_graph.py` — evidence tiers.
- `reconcile/roof_algorithms_py/math_utils.py` — plane_normal.
- `reconcile/element_locator.py` — parse_element_id.
- `.context/v3_roof_proposal_labels.jsonl` — label store.
- `.context/v3_roof_proposal_splits.jsonl` — split log.
- `reconcile/buildings_3d.json` — per-UUID source geometry.
- `reconcile/reconcile_v3_results.json` — per-UUID V3Building outputs.
- `reconcile/viewer_server.py:3339` — label POST endpoint.

### Literature references

- [P1] Xu, Vosselman, Oude Elberink, "Investigation on the Weighted RANSAC Approaches for Building Roof Plane Segmentation from LiDAR Point Clouds," *Remote Sensing* 8(1), 2016. https://www.mdpi.com/2072-4292/8/1/5
- [P2] Dorninger & Pfeifer — seeded region growing on normals.
- [P3] Castagno & Atkins, "Roof Shape Classification from LiDAR and Satellite Image Data Fusion Using Supervised Learning," *Sensors* 18(11), 2018. https://pmc.ncbi.nlm.nih.gov/articles/PMC6264004/
- [P4] Dehbi et al., "Robust and fast reconstruction of complex roofs with active sampling from 3D point clouds," *Transactions in GIS*, 2021. https://onlinelibrary.wiley.com/doi/10.1111/tgis.12659
- [P5] Sampath & Shan, "Segmentation and Reconstruction of Polyhedral Building Roofs from Aerial LiDAR Point Clouds," IEEE TGRS 48(3), 2010. https://ieeexplore.ieee.org/document/5308335
- [P6] Nan & Wonka, "PolyFit: Polygonal Surface Reconstruction from Point Clouds," ICCV 2017.
- [P7] Poullis, "A framework for automatic modeling from point cloud data," 2013.
- [P8] Xiong et al., "Hierarchical Roof Topology Tree (HRTT)," *Remote Sensing* 9(4), 2017. https://www.mdpi.com/2072-4292/9/4/354
- [P9] Poullis et al., "Roof feature lines from airborne LiDAR with geometric constraints," *Remote Sensing* 15(23), 2023. https://www.mdpi.com/2072-4292/15/23/5493
- [P10] "Ridge-based Hierarchical Decomposition," *Remote Sensing* 6(4), 2014. https://www.mdpi.com/2072-4292/6/4/3284
- [P11] Weinmann et al., "Geometric Features and their Relevance for 3D Point Cloud Classification," *ISPRS Annals* IV-1/W1, 2017. https://isprs-annals.copernicus.org/articles/IV-1-W1/157/2017/
- [P12] PDAL `filters.covariancefeatures`. https://pdal.io/stages/filters.covariancefeatures.html
- [P13] Yan et al., "Reconstruction of Complex Roof Semantic Structures using Local Convexity & Consistency," *Remote Sensing* 13(10), 2021. https://www.mdpi.com/2072-4292/13/10/1946
- [P14] RoofSeg — edge-aware transformer, arXiv 2508.19003, 2025. https://arxiv.org/html/2508.19003
- [P15] KIBS — 3D roof sections from satellite, arXiv 2307.05409.
- [P16] Liu et al., "Intuitive and Efficient Roof Modeling," SIGGRAPH Asia 2021. https://arxiv.org/abs/2109.07683
- [P17] "Roof model recommendation based on footprint combination + symmetry," *International Journal of Digital Earth*, 2017.
- [P18] Goebbels et al., "RANSAC for Aligned Planes with Application to Roof Plane Detection," GRAPP 2020. https://www.scitepress.org/Papers/2020/88363/88363.pdf
- [P19] Habib et al. — linear-feature photogrammetry regularity constraints.
- [P20] "Graph edit dictionary for correcting roof-topology errors," *ISPRS JPRS*, 2014.
- [P22] Li, "Primitive-Based Building Reconstruction," PhD Thesis, Purdue, 2025.
- [P23] OpenStreetMap `roof:shape` key taxonomy. https://wiki.openstreetmap.org/wiki/Key:roof:shape
- [P24] Wikipedia, "List of roof shapes." https://en.wikipedia.org/wiki/List_of_roof_shapes
- [P25] "Fast regularity-constrained plane fitting," *ISPRS JPRS*, 2020. https://arxiv.org/abs/1905.07922
- [P26] Verma, Oude Elberink — roof-topology graph matching, 2008–2011.
- [P27] City3D, *Remote Sensing* 14(9), 2022.
- [P29] Roof-as-fuzzy-set / thermal & solar downstream features.
- [P30] Apple RoomPlan. https://developer.apple.com/documentation/roomplan

---

## Methodology appendix

### A.1 Research pipeline

- **Phase 1 (Codebase mining):** 3 parallel Explore agents: (a) exhaustive dataclass field enumeration, (b) derivable geometric/topological/physics signals, (c) label record schema + heuristic/enrichment/roof-typology/ML-code inventory.
- **Phase 2 (Literature scan):** 1 general-purpose agent running 12 targeted WebSearches on roof-plane classification / LoD2 reconstruction / topology graphs / eigenvalue features / OSM taxonomy / Apple RoomPlan.
- **Phase 3 (Synthesis):** Deduplication, mapping literature feature names to Band-2/3 equivalents, ranking by prior signal strength.

### A.2 Key inclusion criterion

Every feature that *any* mining source surfaced is included, even when obvious or likely redundant. This is an enumeration report, not a curation report. Filtering is a Phase-3+ activity.

### A.3 Known sources not reached

WebFetch was blocked for MDPI, ScienceDirect, Taylor & Francis, and ISPRS binary PDFs; named literature features were recovered from search-result abstracts plus cross-referenced papers. Full-text for P10, P17, P19, P20, P25, P27 was not obtained — treat those citations as abstract-only.

### A.4 Authoritativeness notes

- Repo file references (file:line) are authoritative as of commit on branch `mc/merge-room-building-json` on 2026-04-18.
- Label-store statistics (5,760 / 5,628 / 70) reflect the store as of the same date.
- Literature feature names are taken verbatim from papers; equivalence to our Band-2/3 features is our mapping and should be verified during implementation.

### A.5 What this report is **not**

- Not a model. No training, no cross-validation, no predictions.
- Not a rule recommendation. Candidate rules will come from Phase 5 of the implementation plan.
- Not a product spec. Nothing here changes the proposer or merger.

---

**End of catalogue.** For the implementation plan that consumes this catalogue, see `/Users/martincollignon/.claude/plans/system-instruction-you-are-working-melodic-octopus.md`.
