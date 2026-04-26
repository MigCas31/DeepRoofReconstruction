## Exhaustive Feature Catalogue V2 — Implementation Audit + Ultradeep Extension

**Date:** 2026-04-18
**Dataset now:** 8,865 labels across 111 buildings (up from 5,760/70 in v1); 2,130 accepts (24 %) / 6,735 rejects (76 %).
**Relation to v1:** V1 is `reports/slanted_roof_feature_catalogue.md` (1,099 lines, ~600 planned features, bands A–O + P.1–P.12). V2 supersedes the "what exists / what to add" portion and *extends* v1 along seven orthogonal axes v1 did not cover.

### Why a V2

1. **Implementation has moved.** 396 features are live in `reconcile_v3/analysis/` today; v1 enumerated planned features only, using placeholder IDs (`A.1`…`P.12`) that don't match the actual column names.
2. **Data has grown.** Labels: 5,760 → 8,865. Buildings: 70 → 111. The class ratio held (~76 % reject), so any distributional claims in v1 still hold qualitatively.
3. **Seven feature families were out of scope in v1.** Scan-quality metadata, audit-log decision traces, topology-V2 graph structure, split-history user-behavior, cross-proposal siblings, labeler-session context, and 2024-2026 deep-learning features.
4. **Building-science cross-domain surfaces red-flag rules** that map directly onto surveyor intuition but weren't enumerated in v1 (truss span, Eurocode duopitch window, BR18 daylight envelope, shape-grammar orphan-oblique, material-minimum pitch).

---

### 0. How to read this catalogue

- **Part 1** — ground-truth audit of the 396 features currently emitted by `analyze_labels.py`; each is a real column in `artifacts/features_expanded.parquet`.
- **Part 2** — catalogue-gap closure (v1 features still not implemented).
- **Part 3–9** — seven new feature families not in v1.
- **Part 10** — 2024-2026 literature features applicable to polygon-based data.
- **Part 11** — building-science cross-domain signals.
- **Part 12** — surveyor-style red-flag rules.
- **Part 13** — prioritization matrix for next implementation pass.
- **Bibliography** and **methodology appendix** at end.

Any feature tagged **[LIVE]** is already in `features_expanded.parquet`. **[PLANNED]** means listed in v1 but not yet implemented. **[NEW]** means not in v1 and not implemented — candidate for a future pass. **[OUT-OF-SCOPE]** flags features that require data we don't have (raw LiDAR, RGB ortho, etc.) and would require an upstream signal change to implement.

---

## Part 1 — Ground-truth implementation audit (396 features)

Every feature below is verified against the current `reconcile_v3/analysis/` package. Source citations use `file.py:line` conventions.

### 1.1 Live feature buckets — summary

| Bucket | Count | Source module | v1 category |
|---|---:|---|---|
| Plane descriptors | 13 | `feature_expansion.py` | A (subset) |
| Edge geometry | 12 | `feature_expansion.py` | B (subset) |
| Vertex basic | 9 | `feature_expansion.py` | C (subset) |
| Polygon XZ geometry | 17 | `feature_expansion.py` | D |
| Position vs building | 6 | `feature_expansion.py` | E (subset) |
| Neighbor / opposing planes | 14 | `feature_expansion.py` | F (subset) |
| Cluster-member aggregates | 148 | `feature_expansion.py` | G |
| Cluster quality | 8 | `feature_expansion.py` | H |
| Physics / drainage | 5 | `feature_expansion.py` | I (subset) |
| Record metadata | 25 | `feature_expansion.py` | J |
| Source-wall aggregates (Band 2) | 26 | `advanced_features.py` | not in v1 as Band 2 — mapped to lit P.2/P.3 |
| Shape descriptors (Hu / Fourier / inertia / radial / Reock / Schwartzberg / Polsby-Popper) | 27 | `advanced_features.py` | D.26–D.48 + new |
| 3D vertex angles / turning / bbox | 11 | `advanced_features.py` | C (extension) |
| Normal-stats (spherical var, Fisher κ, entropy) | 8 | `advanced_features.py` | F/H extension |
| IoU / overlap | 8 | `advanced_features.py` | E extension |
| Building-level (footprint shape, counts, height) | 22 | `building_features.py` | N (subset) |
| Context (part gable + kneewall + dormer + survival) | 41 | `context_features.py` | K + L (subset) + M (subset) |
| **Total** | **396** | | |

### 1.2 Feature listing

All names below are the **literal column names** in the parquet file, not v1's placeholder IDs.

#### 1.2.1 Plane descriptors — 13 features [`feature_expansion.py`]

`plane_a`, `plane_b`, `plane_c`, `plane_d`, `plane_azimuth_deg`, `plane_incl_deg`, `plane_rise_over_run`, `plane_pitch_is_nearly_flat` (<5°), `plane_pitch_is_shallow` (5-15°), `plane_pitch_is_architectural` (15-60°), `plane_pitch_is_steep` (≥60°), `plane_pitch_is_nearly_vertical` (≥80°), `plane_water_flow_azimuth_deg`.

#### 1.2.2 Edge geometry — 12 features

`edge_count`, `edge_longest_m`, `edge_shortest_m`, `edge_mean_m`, `edge_std_m`, `edge_length_cv`, `edge_total_m`, `ridge_edge_length_m`, `eave_edge_length_m`, `edges_horizontal_fraction`, `edges_vertical_fraction`, `edge_longest_azimuth_deg`.

#### 1.2.3 Vertex basic — 9 features

`vertex_count`, `y_min_m`, `y_max_m`, `y_range_m`, `y_mean_m`, `y_std_m`, `x_range_m`, `z_range_m`, `slant_residual_rms_m`.

#### 1.2.4 Polygon XZ geometry — 17 features

`poly_area_xz_m2`, `poly_perimeter_xz_m`, `poly_compactness`, `poly_convex_hull_area_m2`, `poly_convex_hull_ratio`, `poly_bbox_aspect`, `poly_bbox_area_m2`, `poly_min_rect_major_m`, `poly_min_rect_minor_m`, `poly_min_rect_aspect`, `poly_min_rect_azimuth_deg`, `poly_min_rect_fill_ratio`, `poly_min_width_m`, `poly_simplify_vertex_ratio`, `poly_is_convex`, `poly_centroid_x`, `poly_centroid_z`.

#### 1.2.5 Position vs building — 6 features

`inside_building_footprint`, `distance_to_footprint_edge_m`, `fraction_inside_footprint`, `touches_footprint_boundary_length_m`, `centroid_distance_to_boundary_m`, `overshoot_area_m2`.

#### 1.2.6 Neighbor / opposing planes — 14 features

`opposing_count`, `opposing_cluster_count`, `opposing_azimuth_mean_deg`, `opposing_azimuth_std_deg`, `opposing_incl_mean_deg`, `opposing_incl_std_deg`, `opposing_azimuth_diff_min_deg`, `opposing_azimuth_diff_mean_deg`, `opposing_azimuth_diff_max_deg`, `opposing_incl_diff_max_deg`, `opposing_cos_min`, `side_piece_count`, `side_piece_area_sum_m2`, `side_piece_has_parent`.

#### 1.2.7 Cluster-member aggregates — 148 features

19 per-member numeric fields × 6 aggregation operators (`count`, `mean`, `std`, `min`, `max`, `range`) + median = up to 7 stats per field. Live base fields:

`segment_azimuth_deg`, `segment_incl_deg`, `segment_length_m`, `segment_mid_y_m`, `plane_height_above_slab_m`, `plane_y_at_piece_centroid_m`, `piece_area_m2`, `piece_perimeter_m`, `piece_compactness`, `piece_bbox_aspect`, `piece_min_width_m`, `piece_vertex_count`, `rain_exposure_ratio`, `slant_delta_over_piece_m`, `seg_mid_to_piece_centroid_xz_m`, `slab_area_m2`, `slab_floor_y_m`, `slab_vertex_count`, `story_delta`.

Column pattern: `member_<field>_<stat>` (e.g., `member_rain_exposure_ratio_mean`).

Plus 14 cluster-level scalars: `cluster_member_count`, `member_heuristic_accepted_fraction`, `member_unique_source_rooms`, `member_unique_source_walls`, `member_unique_slab_rooms`, `member_unique_stories`, `member_plane_d_spread_m`, `member_plane_azimuth_spread_deg`, `member_plane_incl_spread_deg`, `member_plane_dot_min`, `member_piece_kind_room_fraction`, `member_piece_kind_gap_fraction`, `member_is_same_room_fraction`, `member_is_top_story_slab_fraction`.

#### 1.2.8 Cluster quality — 8 features

`cluster_pre_clip_area_sum_m2`, `cluster_post_clip_area_m2`, `cluster_clip_ratio`, `cluster_param_d_abs_max`, `cluster_param_normal_dot_min`, `cluster_param_opposing_cos_az_max`, `snapshot_area_m2`, `snapshot_perimeter_m`.

#### 1.2.9 Physics / drainage — 5 features

`drainage_flow_azimuth_deg`, `drainage_to_building_center_cos`, `drainage_sheds_away_from_center`, `eave_y_m`, `ridge_y_m`.

#### 1.2.10 Record metadata — 25 features

`building_uuid`, `proposal_id`, `cluster_canonical_id`, `label`, `heuristic_label`, `labeler`, `ts`, `merge_mode`, `part_index`, `part_count`, `is_split_child`, `parent_proposal_id`, `piece_kind`, `piece_kind_is_room`, `piece_kind_is_gap`, `rain_hitting_side_count`, `covered_side_count`, `clipped_by_building_boundary`, `snapshot_member_count`, `snapshot_opposing_cluster_count`, `n_room_boundary_refs`, `heuristic_disagrees_with_user`, `label_is_accept`.

(Some of the remaining slots are record-level flags populated at join time.)

#### 1.2.11 Source-wall aggregates (Band 2) — 26 features [`advanced_features.py`]

`swall_resolved_count`, `swall_resolution_ratio`, `swall_length_mean`, `swall_length_std`, `swall_length_min`, `swall_length_max`, `swall_length_total`, `swall_top_y_mean`, `swall_top_y_std`, `swall_top_y_range`, `swall_bottom_y_mean`, `swall_bottom_y_std`, `swall_azimuth_mean`, `swall_azimuth_std`, `swall_azimuth_max_diff_deg`, `swall_incl_mean_deg`, `swall_incl_std_deg`, `swall_incl_max_deg`, `swall_incl_is_nonvertical_fraction`, `swall_centroid_to_seg_mean_m`, `swall_centroid_to_seg_max_m`, `swall_fraction_walls_merged`, `swall_fraction_same_room_as_slab`, `swall_fraction_on_footprint_boundary`, `swall_stories_touched`, `swall_unique_stories`.

> **Phase-3 ranking finding:** `swall_fraction_on_footprint_boundary`, `swall_top_y_std`, `swall_azimuth_max_diff_deg` are among the top-15 features by effect size; source-wall aggregates vaulted into the top-ranked bucket.

#### 1.2.12 Shape descriptors — 27 features

- **Hu moments (7):** `hu_log_1` … `hu_log_7` (signed log-magnitude; sign preserved).
- **Fourier descriptors (8):** `fourier_log_1` … `fourier_log_8` (log of normalized FFT coefficient magnitudes; resampled to 64 boundary samples).
- **Inertia ellipse (4):** `inertia_major_axis_m`, `inertia_minor_axis_m`, `inertia_eccentricity`, `inertia_orientation_deg`.
- **Compactness (3):** `reock_compactness` (area/π·r_enc²), `schwartzberg_compactness`, `polsby_popper`.
- **Radial signature (5):** `radial_mean_m`, `radial_std_m`, `radial_min_m`, `radial_max_m`, `radial_cv`.

#### 1.2.13 3D vertex angles / turning / bbox — 11 features

`vangle_mean_deg`, `vangle_std_deg`, `vangle_min_deg`, `vangle_max_deg`, `vangle_sum_defect_deg`, `turning_angle_mean_deg`, `turning_angle_std_deg`, `turning_angle_abs_sum_deg`, `sharp_corner_count`, `edge_direction_entropy`, `bbox3d_volume_m3`, `bbox3d_diagonal_m`.

#### 1.2.14 Normal-vector statistics — 8 features

`normals_spherical_variance`, `normals_mean_resultant_length`, `normals_fisher_kappa`, `normals_d_entropy`, `normals_pairwise_cos_min`, `normals_pairwise_cos_mean`, `member_room_entropy`, `member_wall_entropy`.

> **Phase-3 finding:** `normals_d_entropy`, `member_wall_entropy`, `member_room_entropy` are in the top-10 by effect size; they encode cluster heterogeneity directly.

#### 1.2.15 IoU / overlap — 8 features

`iou_building_footprint`, `cover_of_building_footprint`, `iou_part_footprint`, `cover_of_part_footprint`, `iou_nearest_final_roof`, `cover_of_nearest_final_roof`, `final_roof_count_overlapping`, `final_roof_union_area_m2`.

#### 1.2.16 Building-level — 22 features [`building_features.py`]

`bld_classification`, `bld_stories_found`, `bld_story_count_rooms`, `bld_room_count`, `bld_wall_count`, `bld_door_count`, `bld_window_count`, `bld_cross_floor_gap_count`, `bld_gap_wall_count`, `bld_stitch_wall_count`, `bld_footprint_area_m2`, `bld_footprint_perimeter_m`, `bld_footprint_compactness`, `bld_footprint_bbox_aspect`, `bld_footprint_convex_hull_ratio`, `bld_footprint_elongation_ratio`, `bld_footprint_centroid_x`, `bld_footprint_centroid_z`, `bld_footprint_part_count`, `bld_height_m`, `bld_y_min_m`, `bld_y_max_m`.

#### 1.2.17 Context (part-gable + kneewall + dormer + survival) — 41 features [`context_features.py`]

Part-gable (22): `ctx_roof_proposals_count`, `ctx_merged_roof_segments_count`, `ctx_part_count`, `part_gable_status`, `part_gable_tier1_reason_count`, `part_gable_tier2_reason_count`, `part_gable_is_not_gable`, `part_gable_is_gable_complete`, `part_gable_is_gable_along_extend`, `part_gable_is_gable_cross_review`, `part_gable_is_gable_ambiguous`, `part_gable_metric_n_slanted_roofs`, `part_gable_metric_elong`, `part_gable_metric_coverage`, `part_gable_metric_n_dormers`, `part_gable_metric_n_arch_flats`, `part_gable_metric_ridge_y_abs`, `part_gable_metric_ridge_vs_expected`, `part_gable_metric_ridge_vs_major`, `part_gable_metric_dincl`, `part_gable_metric_daz180`, `part_gable_metric_major_m`, `part_gable_metric_minor_m`, `part_footprint_area_m2`, `part_footprint_perimeter_m`, `part_room_count`.

Kneewall (5): `kneewall_count_overlapping_xz`, `kneewall_count_in_same_room`, `kneewall_overlap_area_m2`, `kneewall_nearest_distance_m`, `any_kneewall_in_building`.

Dormer (4): `dormer_count_in_building`, `dormer_count_overlapping_xz`, `dormer_overlap_area_m2`, `dormer_nearest_distance_m`.

Roof-survival (5): `final_slanted_roof_count`, `survived_to_final_plane`, `best_final_plane_cos`, `best_final_overlap_area_m2`, `best_final_overlap_fraction`.

---

## Part 2 — V1 features not yet implemented (gap closure)

The table below is the delta between v1's enumerated features and today's live 396. Omits features that are out-of-scope (per point-cloud / raster literature).

| v1 ID | Feature | Bucket | Status | Priority |
|---|---|---|---|---|
| A.14 | `steepness_bin` (<5°/5-25°/25-50°/50°+) | plane | [PLANNED] | low (redundant with pitch_is_*) |
| A.15 | `pitch_category` (2:12, 4:12, …) | plane | [PLANNED] | low |
| A.20–A.23 | drainage-vector trio + `sheds_water_away_from_centroid` | physics | [LIVE] partial | — |
| A.33–A.36 | dihedral-to-opposing {min, max, mean, std} | neighbor | [PLANNED] | **high** |
| A.37 | `azimuth_from_building_principal_axis_deg` | plane | [PLANNED] | **high** — Goebbels 2020 key signal |
| A.38 | `log_plane_rise_over_run` | plane | [PLANNED] | medium |
| B.17–B.22 | ridge / eave / hip / rake edge classification | edge | [PLANNED] | **high** |
| B.28–B.31 | edge-azimuth 8-bin histogram + entropy + dominant direction + freq | edge | [PLANNED] | medium |
| B.32–B.33 | parallel / perpendicular edge-pair count | edge | [PLANNED] | medium |
| B.38–B.40 | collinear runs + Douglas-Peucker reduction ratios at 1 cm / 5 cm | edge | [PLANNED] | medium |
| B.54–B.55 | ridge-edge horizontality + ridge-touches-opposing-seam | edge | [PLANNED] | **high** |
| C.2–C.8 | interior-angle mean/std/min/max, convex/reflex counts, convexity ratio | vertex | [LIVE] (as `vangle_*`) | — |
| C.9–C.12 | max-y / min-y vertex index + multi-vertex ridge/eave counts | vertex | [PLANNED] | medium |
| C.17 | vertex-Y cluster count (multi-level ridges) | vertex | [PLANNED] | low |
| C.21–C.23 | symmetry scores (x-axis, z-axis, point-symmetry) | vertex | [PLANNED] | low |
| D.22–D.24 | `is_trapezoid_xz`, `is_rectangle_xz`, `is_right_trapezoid_xz` | polygon | [PLANNED] | low |
| D.39 | fractal_dimension (box count) | polygon | [PLANNED] | low |
| D.45–D.48 | Delaunay triangulation stats | polygon | [PLANNED] | low |
| E.6 | `fraction_inside_building_footprint` | position | [LIVE] (as `fraction_inside_footprint`) | — |
| E.16–E.20 | relative story + multi-story-cluster flags | position | [LIVE] via `ctx_*` / `member_*_story` | — |
| E.24–E.28 | fraction of polygon with floor-above/below; `segment_max_y_equals_building_max_y` | position | [PLANNED] | **high** |
| F.13–F.14 | opposing-seam length 3D / 2D | neighbor | [PLANNED] | medium |
| F.16–F.19 | same-cluster sibling count + shared boundary; other-cluster neighbor counts | neighbor | [PLANNED] | medium |
| F.20–F.22 | touching room/gap/part-boundary counts | neighbor | [PLANNED] | medium |
| F.25–F.27 | rain-to-covered ratio, has-ridge / has-valley seam | neighbor | [PLANNED] | **high** |
| F.31–F.32 | convex-ridge / concave-valley pairs (signed dihedral) | neighbor | [PLANNED] | **high** — HRTT, Yan 2021 |
| I.7–I.10 | wall-top coverage ratio (on eave band + overall) | physics | [PLANNED] | **high** |
| I.13–I.16 | eave-to-ridge height; ridge-is-below-building-max; drainage-to-opposing-seam | physics | [PLANNED] | medium |
| K.16–K.22 | SlopeHypothesis fields | context | [PLANNED] | **high** |
| L.10–L.14 | V3FlatCeiling beneath; V3SlantedRoof beneath; V3UnresolvedRegion beneath | context | [PLANNED] | **high** |
| M.1–M.6 | roof-coverage-graph evidence tier (sloped_state, overlap_ratio, vertical_clearance, part_match) | context | [PLANNED] | **high** |
| N.6–N.10 | building-footprint shape detection (L/T/U/E) | building | [PLANNED] | low |
| N.19–N.20 | building principal-axis azimuth + elongation | building | [LIVE] (as `bld_footprint_bbox_aspect` + elongation_ratio) | — |

---

## Part 3 — Extension A: Scan / capture quality signals [NEW]

Source: `buildings_3d.json[*]`, `reconcile_v3_results.json::constants`, `V3Input.classification`.

| # | Feature | Source | Rationale |
|---|---|---|---|
| ScanQ.1 | `bld_classification_ordinal` (RED=0, YELLOW=0.5, GREEN=1.0) | `V3Input.classification` | Pipeline's per-building quality tier. Strong prior on accept rate. |
| ScanQ.2 | `bld_classification_is_red` / `_is_yellow` / `_is_green` | same | One-hot alt to ordinal. |
| ScanQ.3 | `scan_noise_m` | `reconcile_v3_results.json::constants.scan_noise_m` | Per-building geometry-noise floor (typical 0.05 m). |
| ScanQ.4 | `is_segment_finer_than_scan_noise` | `poly_min_width_m / scan_noise_m < threshold` | Segments below noise floor are artifact candidates. |
| ScanQ.5 | `stories_changed_to_stories_ratio` | `buildings_3d.json[*]` | Story-extraction instability proxy. |
| ScanQ.6 | `merged_wall_divergence` | `(computed_walls_total − merged_walls_total) / computed_walls_total` | Wall-topology noise. |
| ScanQ.7 | `cache_wall_fraction` | `scan_cache_walls / merged_walls_total` | Cache hit rate → staleness proxy. |
| ScanQ.8 | `gap_remediation_density` | `(cross_floor_gaps + gap_walls + stitch_walls) / (room_count × story_count)` | Topology-noise density. |
| ScanQ.9 | `overlap_metric_max` | `buildings_3d.json[*].overlap_metrics.max_excess` | Max room-room geometry collision. |
| ScanQ.10 | `overlap_metric_mean` | `buildings_3d.json[*].overlap_metrics.mean_excess` | Mean overlap magnitude. |
| ScanQ.11 | `scan_session_count` | from builder-emitted provenance (if persisted) | # of 3D scan sessions merged. |
| ScanQ.12 | `scan_device_model` | builder metadata (if persisted) | iPad vs iPhone Pro, LiDAR quality differs. |
| ScanQ.13 | `scan_capture_duration_s` | builder metadata (if persisted) | Rushed scans = noisier. |

> Of these, #1–#10 are readable today; #11–#13 require builder-layer persistence.

---

## Part 4 — Extension B: V3 intermediate fields (audit-log & metrics) [NEW]

Source: `reconcile_v3/models.py`, `reconcile_v3_results.json`.

### 4.1 GableExtension.metrics dict (per-part, 20+ keys)

Not fully exposed as features; the current `part_gable_metric_*` covers only a subset. Add:

| # | Feature | Source | Rationale |
|---|---|---|---|
| GE.1 | `part_gable_metric_major_az` | `GableExtension.metrics.major_az` | Part footprint OBB major-axis azimuth. |
| GE.2 | `part_gable_metric_ridge_az` | `GableExtension.metrics.ridge_az` | Detected ridge azimuth. |
| GE.3 | `part_gable_metric_az0` / `az1` | same | Two gable-slope azimuths. |
| GE.4 | `part_gable_metric_incl0` / `incl1` | same | Two gable-slope inclinations. |
| GE.5 | `segment_vs_part_ridge_az_deg` | angle_diff(`plane_azimuth_deg`, `part_gable_metric_ridge_az`) | Segment aligned with detected ridge? |
| GE.6 | `segment_vs_part_az0_deg` / `_az1_deg` | angle_diff | Segment matches one of the two gable slopes? |

### 4.2 GableExtension.uncovered_region_xz

| # | Feature | Source | Rationale |
|---|---|---|---|
| GE.7 | `part_uncovered_fraction` | `area(uncovered_region_xz) / area(part_footprint)` | Part's roof-coverage deficit. |
| GE.8 | `segment_in_uncovered_region_fraction` | `(segment_xz ∩ uncovered_region_xz).area / segment.area` | Segment lives in un-roofed region → more plausible. |
| GE.9 | `uncovered_region_has_segment` | boolean | — |

### 4.3 GableExtension.ridge_line

| # | Feature | Source | Rationale |
|---|---|---|---|
| GE.10 | `part_ridge_line_length_m` | `‖ridge_line[1] − ridge_line[0]‖` | Detected ridge length. |
| GE.11 | `part_ridge_line_y_m` | mean Y of ridge_line endpoints | Ridge elevation. |
| GE.12 | `segment_max_y_vs_part_ridge_y_m` | `y_max_m − part_ridge_line_y_m` | Should be ≈0 for a real top-of-roof segment. |
| GE.13 | `segment_ridge_edge_parallel_to_part_ridge` | dihedral of ridge_edge with ridge_line | — |

### 4.4 V3WallExtension.behind_knee_wall flag aggregation

| # | Feature | Source | Rationale |
|---|---|---|---|
| WE.1 | `swall_behind_kneewall_fraction` | per-member wall_extension flag | Fraction of members sitting on an artificial shelf. |
| WE.2 | `swall_any_behind_kneewall` | boolean | — |

### 4.5 V3UnresolvedRegion

| # | Feature | Source | Rationale |
|---|---|---|---|
| UR.1 | `unresolved_region_count` | `V3Building.unresolved_regions` len | — |
| UR.2 | `unresolved_region_total_area_m2` | sum | Total unresolved ceiling area in building. |
| UR.3 | `nearest_unresolved_distance_m` | min over regions | Segment's proximity to unresolved ceiling. |
| UR.4 | `segment_room_is_in_any_unresolved_neighbor_list` | boolean | Room flagged as ambiguous. |
| UR.5 | `unresolved_reason_gap_between_rooms_count` | filter by `reason` | Category-specific count. |
| UR.6 | `unresolved_reason_within_story_gap_count` | — | — |

### 4.6 V3FlatCeiling.over (literal)

| # | Feature | Source | Rationale |
|---|---|---|---|
| FC.1 | `flat_ceiling_over_room_count` | per segment XZ overlap | FlatCeiling over an actual room under this segment. |
| FC.2 | `flat_ceiling_over_extension_count` | — | FlatCeiling over an extension (artificial shelf). |
| FC.3 | `flat_ceiling_over_fill_count` | — | FlatCeiling marking a fill region. |
| FC.4 | `flat_ceiling_over_gap_count` | — | FlatCeiling marking a gap. |

> Segments stacked above `over=extension` or `over=fill` are likelier artifacts than those above `over=room`.

### 4.7 V3Gap.status / V3Gap.between_rooms

| # | Feature | Source | Rationale |
|---|---|---|---|
| GAP.1 | `segment_nearest_gap_status_ambiguous` | min distance to ambiguous gap | Ambiguity adjacency. |
| GAP.2 | `segment_nearest_gap_distance_m` | min distance to any gap | — |
| GAP.3 | `segment_near_cross_part_gap` | is nearest gap bridging two parts? | Cross-part gaps are topology-fragile. |

### 4.8 V3SlantedRoof.source_segment_ids (reverse lookup)

| # | Feature | Source | Rationale |
|---|---|---|---|
| SR.1 | `member_roof_fan_out_max` | max over members of # SlantedRoofs citing member | Member used by many final roofs → over-coverage. |
| SR.2 | `member_roof_fan_out_mean` | mean | — |
| SR.3 | `member_never_used_fraction` | fraction of members not in any final roof's source_segment_ids | Unused members → segment rests on weak evidence. |

### 4.9 audit_log decision-trace features

| # | Feature | Source | Rationale |
|---|---|---|---|
| AL.1 | `audit_log_rule_firing_hist_<rule>` | count of each rule name firing in building | Per-rule prior on this building. |
| AL.2 | `dominant_rule_for_segment` | rule that created majority of members (categorical) | Which pipeline rule is responsible. |
| AL.3 | `dominant_rule_confidence_tier` | mapping rule → confidence tier (empirical) | Is the rule known-noisy? |
| AL.4 | `rule_input_complexity` | # input keys passed to dominant rule | Complex rules more brittle. |
| AL.5 | `threshold_adherence_min` | for dominant-rule decisions, min of (input − threshold) / threshold | Near-boundary decisions are fragile. |

---

## Part 5 — Extension C: Topology-V2 graph features [NEW]

Source: `.context/<uuid>.topology-v2.json` + `.topology-v2.qa.json`. Requires BFS/NetworkX.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| TV2.1 | `swall_node_degree_mean` | mean(degree(wall_node)) over members | Well-connected walls are structurally real. |
| TV2.2 | `swall_node_degree_min` | min | Least-connected wall → outlier. |
| TV2.3 | `swall_exterior_link_count_sum` | sum of count(neighbor.type="exterior") | Exterior-facing walls carry roofs. |
| TV2.4 | `swall_exterior_link_fraction` | count(ext) / degree | Normalized. |
| TV2.5 | `swall_shared_face_area_sum` | Σ over adjacent edges of `evidence.shared_face_area` | Total real contact area. |
| TV2.6 | `swall_node_confidence_mean` | mean topology node confidence | From QA file. |
| TV2.7 | `swall_boundary_level_min` | min of {L0,L1,L2} | L0=raw is suspicious. |
| TV2.8 | `swall_steps_to_exterior_mean` | BFS distance to any exterior node, averaged | Deeper walls are interior. |
| TV2.9 | `swall_steps_to_exterior_min` | min | Segment's "most exterior" member. |
| TV2.10 | `swall_betweenness_centrality_mean` | mean node betweenness | Load-bearing walls. |
| TV2.11 | `swall_clustering_coefficient_mean` | mean local clustering | Topology tightness. |
| TV2.12 | `swall_connected_component_size` | size of component containing the walls | Isolated small components are fragile. |
| TV2.13 | `segment_straddles_multiple_components` | # distinct components | Implausible — walls should cluster. |
| TV2.14 | `qa_flags_on_swall_nodes_count` | count of QA annotations | Known-problem walls. |
| TV2.15 | `qa_flag_categories_present` | set-of-flags one-hot | Category-specific priors. |

---

## Part 6 — Extension D: Split-history / user-interaction features [NEW]

Source: `.context/v3_roof_proposal_splits.jsonl`.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| SPL.1 | `split_line_azimuth_deg` | atan2(Δz, Δx) of user-drawn line | Direction of split. |
| SPL.2 | `split_vs_segment_az_diff_deg` | angle_diff with `plane_azimuth_deg` | Perpendicular = ridge re-cut; parallel = eave adjust. |
| SPL.3 | `split_vs_segment_rect_major_az_diff_deg` | with `poly_min_rect_azimuth_deg` | Split aligned with polygon OBB? |
| SPL.4 | `split_depth` | count of "#" in proposal_id | User split-recursion depth. |
| SPL.5 | `building_split_count` | count splits in building | User's per-building effort. |
| SPL.6 | `building_split_density` | splits / merged_roof_segment_count | Interaction-intensity ratio. |
| SPL.7 | `split_line_length_m` | segment_length of split_line | — |
| SPL.8 | `split_line_midpoint_inside_segment` | boolean | Was the split within the segment? |
| SPL.9 | `split_branching_factor` | #children of this split | Binary (2) vs multi-way. |
| SPL.10 | `days_since_split_ts` | now − split.ts | Staleness. |
| SPL.11 | `split_ts_vs_label_ts_delta_s` | seconds between | Same-session split (fresh) vs label after refresh (stale). |
| SPL.12 | `cluster_has_any_split_child` | boolean | Cluster required human subdivision → ambiguity signal. |
| SPL.13 | `cluster_split_child_count` | int | — |

---

## Part 7 — Extension E: Cross-proposal sibling / cluster features [NEW]

Source: label-store aggregates + `cluster_canonical_id`.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| SIB.1 | `sibling_count` | #labeled segments with same `cluster_canonical_id` − 1 | — |
| SIB.2 | `sibling_accept_rate` | count(accepted siblings) / sibling_count | Peer prior. |
| SIB.3 | `sibling_reject_rate` | count(rejected) / sibling_count | — |
| SIB.4 | `sibling_skip_rate` | count(skip) / sibling_count | Ambiguity-adjacent. |
| SIB.5 | `sibling_unanimous_reject` | all siblings rejected | Strong reject signal. |
| SIB.6 | `sibling_unanimous_accept` | all siblings accepted | Strong accept signal. |
| SIB.7 | `opposing_cluster_accept_rate_mean` | mean over opposing-clusters of member acceptance | If opposing is rejected, ridge may be bogus. |
| SIB.8 | `opposing_cluster_was_accepted` | boolean: any opposing cluster fully accepted | — |
| SIB.9 | `opposing_vs_own_size_ratio_mean` | mean(opposing.member_count) / own.member_count | Lopsided = merge error. |
| SIB.10 | `opposing_vs_own_size_ratio_max` | max | — |
| SIB.11 | `is_largest_cluster_in_part` | boolean | Main roof plane gets lower prior for "reject". |
| SIB.12 | `is_smallest_cluster_in_part` | boolean | Small clusters on a part are often artifacts. |
| SIB.13 | `cluster_rank_by_area_in_part` | percentile rank | Continuous version of .11/.12. |
| SIB.14 | `same_building_similar_accepted_count` | # accepted segments in building with similar (az, incl) within 10° | Historical acceptance pattern. |

---

## Part 8 — Extension F: Labeler / session metadata [NEW]

Source: `v3_roof_proposal_labels.jsonl::ts, labeler, context`.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| LBL.1 | `labeler_prior_accept_rate` | historical accept% for labeler | Labeler bias correction. |
| LBL.2 | `labeler_prior_accept_rate_on_this_building` | historical rate for (labeler, uuid) | Per-building bias. |
| LBL.3 | `labeling_session_duration_s` | ts(last label in session) − ts(first) | Session length. |
| LBL.4 | `label_index_in_session` | rank | Fatigue (later labels noisier). |
| LBL.5 | `time_of_day_hour` | `ts.hour` | Morning vs. evening effect. |
| LBL.6 | `is_weekend_label` | boolean | — |
| LBL.7 | `label_is_quick_decision_flag` | < 5 s between consecutive labels | Fast labels = higher heuristic trust. |
| LBL.8 | `label_has_context_dict_populated` | bool | Rare — viewer rarely persists context. |
| LBL.9 | `skip_rate_in_building` | count(skip) / total | Building's ambiguity rate. |
| LBL.10 | `neighbor_skip_count` | count of skipped segments with `cluster_canonical_id` adjacent | Ambiguity cluster. |
| LBL.11 | `heuristic_accuracy_in_building` | count(match) / total for building | Heuristic is trustworthy here or not. |

---

## Part 9 — Extension G: Audit-log decision-trace features [NEW]

Source: `reconcile_v3_results.json::audit_log`.

See Part 4.9. Treat this as a first-class feature family once the audit_log schema is stable.

---

## Part 10 — Extension H: 2024-2026 literature features applicable to polygon data

### 10.1 Eigenvalue / PCA-on-vertex-set (Hackel 2017, reused 2024) [NEW]

V1 flagged these as **OUT-OF-SCOPE (no point cloud)**. That's overly conservative: the Hackel eigenvalue descriptors apply to **any** vertex/point set. We have `segment_corners_xyz` (and `member_snapshots[*].corners` for an expanded set). Compute PCA on:

  A) segment-corners-only (N×3, N=vertex_count)
  B) union of member-corners (large N).

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| EIG.1 | `eig_linearity_seg` | (λ₁ − λ₂) / λ₁ on segment corners | Line-like vertex set. |
| EIG.2 | `eig_planarity_seg` | (λ₂ − λ₃) / λ₁ | Plane-like vertex set. |
| EIG.3 | `eig_sphericity_seg` | λ₃ / λ₁ | Isotropy. |
| EIG.4 | `eig_anisotropy_seg` | (λ₁ − λ₃) / λ₁ | Directional spread. |
| EIG.5 | `eig_omnivariance_seg` | ∛(λ₁·λ₂·λ₃) | Volume. |
| EIG.6 | `eig_eigenentropy_seg` | −Σ λᵢ·log(λᵢ) | Eigenvalue spread. |
| EIG.7 | `eig_sum_seg` | λ₁ + λ₂ + λ₃ | Absolute spread. |
| EIG.8 | `eig_change_of_curvature_seg` | λ₃ / (λ₁+λ₂+λ₃) | Curvature proxy. |
| EIG.9 | `eig_verticality_seg` | 1 − |e₃ · ẑ| (e₃ = smallest eigenvector) | Normal vs. world-Y alignment. |
| EIG.10 | `eig_normal_change_rate_seg` | (requires local neighborhoods — may skip) | — |
| EIG.11 | `eig_roughness_seg` | λ₃ (smallest eigenvalue) | Residual thickness. |
| EIG.12 | `eig_*_member_union` | same metrics on union of member corners | Cluster-level eigen descriptors. |
| EIG.13 | `eig_planarity_seg_vs_member_union` | ratio | Has the merge preserved planarity? |

11 Hackel features × 2 point sets = 22 additional columns. Cheap to compute, fills a literature-rooted gap.

### 10.2 Learned polygon embeddings (PolyMP, Geo2Vec, Poly2Vec) [OUT-OF-SCOPE but cheap alt]

Pretrained polygon encoders produce fixed-length vectors:
- **PolyMP** (2025): graph message-passing over vertex-coordinate-invariant encodings → 128-d embedding.
- **Geo2Vec** (2025): signed-distance samples around boundary → 256-d.
- **Poly2Vec** (2024): Fourier spectral → 64-d.

These require an extra PyTorch dependency and pretrained weights. Cheap alternative: compute hand-crafted invariants that *mimic* what these encoders produce — we already have Hu moments (7), Fourier descriptors (8), radial signature (5), inertia ellipse (4) = 24 invariant shape descriptors. **Evaluate whether the learned embedding adds marginal lift over these** before paying the dependency cost.

### 10.3 Plane-fit PCA residual (RoofSeg "plane geometric loss") [NEW, cheap]

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| PGL.1 | `segment_pca_plane_rms_m` | PCA on `segment_corners_xyz`, residual to best-fit plane | True fit quality (vs. `slant_residual_rms_m` which uses merged_plane). |
| PGL.2 | `segment_pca_vs_merged_normal_cos` | dot product of PCA normal with merged-plane normal | Plane consistency. |
| PGL.3 | `member_union_pca_plane_rms_m` | PCA on union of member corners | Pre-clip fit quality. |
| PGL.4 | `member_union_pca_vs_merged_cos` | dot | Cluster-level coplanarity. |

### 10.4 Graph-based roof reconstruction features (Springer 2025) [partially NEW]

Many are live (dihedral to opposing, shared boundary). Add:
| # | Feature | Status | Note |
|---|---|---|---|
| GRF.1 | `edge_type_is_ridge` (per shared edge) | [NEW] | dihedral sign × orientation → ridge/hip/valley taxonomy |
| GRF.2 | `edge_type_is_hip` | [NEW] | — |
| GRF.3 | `edge_type_is_valley` | [NEW] | — |
| GRF.4 | `edge_type_is_eave` | [NEW] | — |
| GRF.5 | `edge_type_is_step` | [NEW] | — |
| GRF.6 | `shared_edge_length_ratio_to_perimeter` | [NEW] | per-edge fraction |
| GRF.7 | `k_nearest_plane_coplanarity_residual` | [NEW] | requires neighbor-plane lookup |
| GRF.8 | `k_nearest_plane_distance_mean_m` | [NEW] | — |

### 10.5 Photometric agreement (GS4Buildings, PLANES4LOD2) [OUT-OF-SCOPE]

Requires orthophoto alignment to RoomPlan data. Flagged for a hypothetical future where we pull Datafordeleren WMTS tiles over each building and compare.

### 10.6 Diffusion-model expected-height (RoofDiffusion) [OUT-OF-SCOPE]

Requires trained diffusion model on DK roof-height maps. Would produce an `expected_plane_y(x, z)` that we could compare to our proposed plane. Research-only.

### 10.7 OSM / cadastre priors [NEW, partial]

Today we use `V3Input.classification` (3-way) and no cadastre attributes. Potential additions (require external lookup):
| # | Feature | Source | Rationale |
|---|---|---|---|
| OSM.1 | `osm_roof_shape` | OSM `roof:shape` tag for building centroid | Prior on expected shape class. |
| OSM.2 | `osm_roof_orientation` | OSM `roof:orientation` (along / across) | — |
| OSM.3 | `osm_building_use` | residential / commercial / etc. | Class-specific roof priors. |
| OSM.4 | `bbr_year_built_decade` | BBR (Danish building register) | Age-bin priors (e.g., 1950s-era roofs differ from 1990s). |
| OSM.5 | `bbr_primary_material` | BBR | Constrains minimum pitch. |
| OSM.6 | `bbr_floor_count_registered` | BBR | Ground-truth story count (vs. scan-inferred). |
| OSM.7 | `bbr_floor_count_mismatch` | BBR count vs. scan | Discrepancy = scan quality issue. |

---

## Part 11 — Extension I: Building-science / surveyor signals

### 11.1 Structural feasibility [NEW]

Residential trusses in Northern Europe: 8–20 m span, >12 m needs engineering, heavy tile requires tighter spacing.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| STR.1 | `implied_free_span_m` | `max(bbox_xz_width_m, bbox_xz_height_m)` | Rough horizontal span. |
| STR.2 | `free_span_exceeds_residential_threshold` | `span > 12 m` | Over-spanned → either commercial/engineered or bogus. |
| STR.3 | `eave_edge_has_supporting_wall` | eave edge within 0.3 m of a wall-top | Bearing-wall check. |
| STR.4 | `eave_support_fraction` | length of eave within 0.3 m of wall / eave length | How much of eave is structurally supported. |
| STR.5 | `has_knee_wall_stub_under_segment` | V3WallExtension with `behind_knee_wall=True` under segment XZ | Attic stub presence. |
| STR.6 | `segment_floats_without_kneewall` | no knee wall and plane Y significantly above floor | Floating plane = scan artifact. |

### 11.2 Building code — Eurocode / BR18 [NEW]

- EN 1991-1-4 duopitch defined only for 5° < α < 75°.
- EN 1991-1-3 snow: μ₁ = 0.8 for 0-30°, linear decrease to 0 at 60°.
- BR18: typical max ridge height 8.5 m residential; 1.4 m setback sloping envelope.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| BC.1 | `pitch_in_duopitch_window` | `5 ≤ plane_incl_deg ≤ 75` | Eurocode-valid roof. |
| BC.2 | `pitch_outside_snow_curve` | `plane_incl_deg > 60` | Above which snow-load = 0 → implausible load path. |
| BC.3 | `ridge_height_exceeds_br18_max` | `ridge_y_m − y_min_building > 8.5` | Residential ridge-height rule. |
| BC.4 | `daylight_envelope_setback_violation` | dist to neighbor building < 1.4 m and pitch above daylight-angle | Urban-code violation proxy. |
| BC.5 | `meets_br18_residential_ridge_check` | conjunction | — |

### 11.3 Thermal envelope [NEW]

EnergyPlus / BE18 need per-surface tilt + azimuth + area + U-value + outward normal + boundary condition.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| TH.1 | `surface_tilt_deg` | = `plane_incl_deg` | Already live. |
| TH.2 | `surface_azimuth_deg_energyplus_convention` | = `plane_azimuth_deg` rotated to EP convention | If we ever export. |
| TH.3 | `linear_thermal_bridge_length_m` | ridge + eave + valley edge lengths | Loss-detail proxy. |
| TH.4 | `surface_implies_attic_vs_cathedral` | has FlatCeiling under? → attic | Boundary-condition hint. |
| TH.5 | `north_facing_penalty_score` | |angle_diff(az, 0°)| / 180 | Heat-loss surface. |

### 11.4 Solar potential [NEW]

NREL rooftop PV thresholds: tilt ≤ 60°, not north-facing, ≥ 10 m² contiguous, ≥ 70 % unshaded.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| SOL.1 | `solar_tilt_in_pv_band` | `tilt ∈ [5°, 60°]` | PV-suitable. |
| SOL.2 | `solar_area_exceeds_10m2` | `poly_area_xz_m2 ≥ 10` | NREL lower bound. |
| SOL.3 | `solar_azimuth_in_southern_half` | `azimuth ∈ [90°, 270°]` northern hemisphere | Orientation. |
| SOL.4 | `solar_is_pv_candidate` | conjunction of SOL.1-.3 | — |
| SOL.5 | `self_shading_proxy` | # other segments within 5 m XZ with y_max > this.y_min | Shading-likelihood. |

### 11.5 Drainage / material-minimum pitch [NEW]

Minimum pitch by material: membrane/bitumen ≥ 2°, metal standing-seam ≥ 3°, tile ≥ 22°, slate ≥ 25°.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| DR.1 | `pitch_implies_membrane_only` | `incl < 5°` | Material-code constraint. |
| DR.2 | `pitch_implies_metal_or_tile` | `5 ≤ incl < 22°` | — |
| DR.3 | `pitch_allows_slate` | `incl ≥ 25°` | — |
| DR.4 | `pitch_consistent_with_bbr_material` | match BBR.primary_material | Requires BBR. |
| DR.5 | `drainage_terminates_at_eave` | drainage vector points toward a valid eave edge | Flow reaches drain. |
| DR.6 | `drainage_terminates_at_ridge` | points toward ridge (invalid) | — |
| DR.7 | `eave_overhang_exceeds_0_6m` | overhang > 0.6 m (typical residential max without engineering) | Anomaly. |

### 11.6 Shape-grammar red flags [NEW]

Flemming / Stiny-Gips / Müller CGA: every oblique face should have a partner sharing a ridge/hip/valley edge.

| # | Feature | Derivation | Rationale |
|---|---|---|---|
| SG.1 | `has_counter_face` | any opposing plane present | Grammar: oblique faces come in pairs. |
| SG.2 | `is_orphan_oblique` | `plane_pitch_is_architectural AND opposing_count == 0` | Strong reject prior. |
| SG.3 | `boundary_is_concave` | `poly_convex_hull_ratio < 0.85` | Jagged boundary = RANSAC "spurious plane". |
| SG.4 | `boundary_isoperimetric_deficit` | `perimeter² / (4π·area) > 3.0` | Ribbon / thin-shape proxy. |
| SG.5 | `island_plane_flag` | boolean: connected only to 0 neighbors | Island planes penalised in RANSAC lit. |
| SG.6 | `overhang_exceeds_eave_convention` | `overshoot_area_m2 > eave_typical_overhang × eave_length` | Too-much overhang. |

### 11.7 IFC / CityGML enum priors [OUT-OF-SCOPE without a target labeling]

IfcRoofTypeEnum has 15 values; CityGML LOD2 uses outward-normal classification. These define a **target space**, not input features; use only if we ever move to multi-class roof-shape prediction.

---

## Part 12 — Surveyor red-flag rules

Distilled from Parts 10-11. These are **high-precision reject gates** worth testing as rules (Phase 5 of the plan):

1. **Orphan oblique** — `plane_pitch_is_architectural AND opposing_count == 0` → reject.
2. **Pitch outside duopitch window** — `plane_incl_deg > 75 OR (plane_incl_deg < 5 AND NOT is_flat_roof_cluster)` → reject.
3. **Sub-noise thin ribbon** — `poly_min_width_m < 2 × scan_noise_m AND poly_area_xz_m2 < 2 m²` → reject.
4. **Over-spanned residential roof** — `bld_classification == "residential" AND implied_free_span_m > 12 m AND NOT has_counter_face` → reject.
5. **Floating plane** — `NOT has_knee_wall_stub_under_segment AND plane_y_at_centroid − floor_y > 3 m` → reject.
6. **Jagged boundary / isoperimetric deficit** — `poly_convex_hull_ratio < 0.7 AND perimeter² / (4π·area) > 5` → reject.
7. **Excessive overhang** — `fraction_inside_footprint < 0.5 AND overhang_exceeds_eave_convention` → reject.
8. **Duplicate-azimuth plane already accepted** — within-building nearest accepted plane with |Δaz| < 5° and |Δincl| < 3° and |Δd| < 0.3 m → reject (duplicate).
9. **Mid-story "roof"** — `NOT is_top_story AND cross_floor_gap_adjacent` → reject with cross-floor-gap priors.
10. **Heavy clipping + low member count** — `cluster_clip_ratio < 0.3 AND cluster_member_count ≤ 2` → reject (over-clipped noise).
11. **Roof-over-existing-roof** — `iou_nearest_final_roof > 0.7 AND y_max_m < existing_final_roof.y_min_m` → reject (below an existing accepted roof).
12. **Material-pitch mismatch** — `pitch_implies_membrane_only AND bbr_primary_material == "tile"` → reject (requires BBR).
13. **Island plane** — `SG.5` → reject.
14. **Sibling unanimous reject** — `sibling_unanimous_reject` → reject.
15. **Unresolved-region-adjacent with wide normal spread** — `nearest_unresolved_distance_m < 0.3 AND normals_spherical_variance > 0.3` → reject.

Each rule should be verified on ≥ 5 reject + ≥ 3 accept examples in the viewer (per v1 methodology §VI) before shipping. Rule #12 depends on BBR data not in scope today.

---

## Part 13 — Cross-cutting feature clusters & prioritization

### 13.1 Feature-family correlation clusters (expected)

Based on v1's §V and the 2026-04-18 ranking (`feature_ranking.csv`):

| Cluster | Representative features | Redundancy expectation |
|---|---|---|
| **Pitch & orientation** | `plane_incl_deg`, `plane_rise_over_run`, `plane_pitch_is_*`, `steepness_bin` | Very high (choose one + one boolean). |
| **Shape invariants** | `hu_log_*`, `fourier_log_*`, `inertia_*`, `radial_*`, `poly_compactness`, `reock_compactness` | High (24 invariants; top-2 or top-3 carry most signal). |
| **Source-wall aggregates** | `swall_*` (26 features) | Medium; keep top-5 by ranking. |
| **Cluster-member stats** | `member_*` (148 features) | High (6 stats of 19 fields); many nearly redundant. |
| **Drainage physics** | `drainage_*`, `sheds_*`, `eave_*`, `ridge_*` | Medium; keep drainage_cos + sheds_away flag. |
| **Context / gable** | `part_gable_*` (21 features) | Medium; status enum + coverage + major/minor dominate. |
| **IoU / overlap** | `iou_*` + `cover_of_*` (8 features) | High; keep iou_building_footprint + iou_nearest_final_roof. |
| **Normal stats** | `normals_*` (8) | Medium; Fisher-κ + spherical-variance + d-entropy cover most. |
| **Metadata / provenance** | `heuristic_*`, `part_*`, `is_*` | Low overlap; keep all. |

### 13.2 Prioritized next-implementation pass

Grouped by effort × expected lift:

**Quick wins (< 1 day):**
1. `bld_classification_ordinal` (ScanQ.1)
2. `dihedral_to_opposing_{min,max,mean,std}` (v1 A.33-.36)
3. `azimuth_from_building_principal_axis_deg` (v1 A.37)
4. `ridge_edge_is_horizontal`, `ridge_touches_opposing_seam` (v1 B.54/.55)
5. `wall_top_coverage_ratio` (v1 I.9)
6. `sibling_accept_rate`, `sibling_unanimous_*` (SIB.2, .5, .6)
7. `has_counter_face`, `is_orphan_oblique`, `island_plane_flag` (SG.1-.3, .5)
8. `pitch_in_duopitch_window` (BC.1)
9. `rain_to_covered_ratio` (v1 F.25)

**Medium (~ 2-3 days):**
10. Eigenvalue features on corners (EIG.1-.11) — literature-grounded; 11 features for free.
11. Edge-azimuth 8-bin histogram + entropy (v1 B.28-.31).
12. V3UnresolvedRegion & V3Gap adjacency features (UR.1-.6, GAP.1-.3).
13. Split-history features (SPL.1-.13).
14. Labeler-session features (LBL.1-.11).

**Harder (~ 1 week):**
15. Topology-V2 graph features (TV2.1-.15) — need to load topology JSON + run BFS.
16. Audit-log decision-trace features (AL.1-.5) — need a rule → confidence empirical table.
17. Roof-coverage-graph evidence tiers (v1 M.1-.6) — re-read `roof_coverage_graph.py`.

**Future / out-of-scope without new data:**
18. OSM / BBR attributes (OSM.1-.7) — external data pull.
19. Learned polygon embeddings (PolyMP / Geo2Vec) — extra dependency + pretrained weights.
20. Photometric agreement / diffusion-expected-height — new upstream signal (orthophotos).

### 13.3 Expected cumulative lift (rough)

- **Current 396 features + live model:** beats heuristic by unknown margin (Phase 4 in progress).
- **+ quick wins 1-9:** 3-6 % absolute F1 lift expected (direct literature alignment + sibling peer prior).
- **+ medium 10-14:** 2-4 % additional (eigenvalues + split-history add new axes).
- **+ hard 15-17:** 1-3 % (diminishing returns; model already capacity-saturated).

Total upside from known signals: ~ 6-13 % F1 lift over a well-trained baseline. Past that, lift requires new **labels** (reasons[] taxonomy) or new **upstream signals** (orthophoto, point cloud).

---

## Bibliography

### Repo references

Preserved from v1 §XI — see `reports/slanted_roof_feature_catalogue.md`. Delta for V2:

- `reconcile_v3/analysis/feature_expansion.py` — flat-dict feature emitter.
- `reconcile_v3/analysis/advanced_features.py` — Band 2 + Band 4 live (396 − 245 live in expand + building + context = 151 features).
- `reconcile_v3/analysis/source_wall_index.py` — per-UUID wall lookup.
- `reconcile_v3/analysis/v3_context.py` — V3 results streaming cache.
- `reconcile_v3/analysis/context_features.py` — Band 3 part/knee/dormer/survival.
- `reconcile_v3/analysis/building_features.py` — per-building footprint + counts.
- `reconcile_v3/analysis/ranking.py` — Phase 3 effect-size/MI/Cramér's-V ranking.
- `reconcile_v3/analysis/modelling.py` — Phase 4 GBM + tree trainer (isotonic-calibrated).
- `reconcile_v3/models.py::V3WallExtension.behind_knee_wall`, `V3UnresolvedRegion`, `V3Gap.status`, `V3FlatCeiling.over`, `V3Part.gable_extension.{metrics, ridge_line, uncovered_region_xz}`, `V3Building.audit_log`.
- `.context/<uuid>.topology-v2.json` / `.topology-v2.qa.json` — graph adjacency for source walls.
- `.context/v3_roof_proposal_splits.jsonl` — user split events.

### V1 literature references (preserved)

All P1–P30 from v1 still apply. See `reports/slanted_roof_feature_catalogue.md` §XI.

### 2024-2026 additions

- [RoofSeg](https://arxiv.org/abs/2508.19003) — edge-aware transformer, plane-geometric loss, PCA plane-fit features (arXiv 2508.19003, 2025).
- [PLANES4LOD2](https://www.sciencedirect.com/science/article/pii/S0924271624001758) — depth-attention FCN, joint section/plane prediction (ISPRS J. P&RS 2024).
- [PolyMP / PolyMP-DSC](https://link.springer.com/article/10.1007/s10707-025-00554-y) — graph message-passing over polygons ([arXiv 2407.04334](https://arxiv.org/abs/2407.04334); [GitHub](https://github.com/zexhuang/PolyMP)).
- [RoofDiffusion](https://arxiv.org/abs/2404.09290) — diffusion over roof height maps (ECCV 2024).
- [Domain-Specific Self-Supervised Roof Classifier](https://arxiv.org/abs/2503.22251) — SimCLR + EfficientNet + CBAM (ISPRS Annals 2025).
- [RoofNet](https://arxiv.org/html/2505.19358v1) — global multimodal roof-material dataset (2025).
- [GS4Buildings](https://arxiv.org/html/2508.07355v1) — LoD2-prior-guided Gaussian splatting (TUM2TWIN 2025).
- [Graph-Based Roof Reconstruction w/ Synthetic Supervision](https://link.springer.com/chapter/10.1007/978-3-032-12840-9_34) — plane/edge graph node features (Springer 2025).
- [Two-Stage Polygon Decomposition & Adaptive Roof Fitting](https://www.mdpi.com/2072-4292/17/23/3832) — rectangle-fit residual + per-part roof type (MDPI RS 2025).
- [BuildingWorld](https://arxiv.org/html/2511.06337v1) — structured foundation-model benchmark with parametric roof vectors (2025).
- [Geo2Vec](https://arxiv.org/html/2508.19305) / [Poly2Vec](https://arxiv.org/html/2408.14806v1) — polygon SDF + Fourier embeddings (2024-2025).
- [Automated Roof Type Classification for Wind Risk](https://arxiv.org/abs/2305.17315) — CNN + ASCE-7 wind-zone raster (2024).
- [Bimodal Segmentation for LoD2](https://ieeexplore.ieee.org/document/11139121/) — joint plane + inline + outline instance segmentation (IEEE TGRS 2025).
- [RoofMapNet](https://www.sciencedirect.com/science/article/pii/S1569843225002778) — HEAT-style corner + edge transformer (2025).
- [Hackel et al., Geometric Features for 3D Point Cloud Classification](https://publikationen.bibliothek.kit.edu/1000081641/7655183) — 11 eigenvalue-based descriptors.
- [Deep Learning w/ Simulated Laser Scanning](https://www.sciencedirect.com/science/article/pii/S0924271624002569) — synthetic LiDAR for roof labels (2024).
- [Rooftop PV Multi-Orientation Integration](https://www.mdpi.com/2071-1050/18/1/158) — solar-potential feature set (Sustainability 2026).
- [EUBUCCO v0.1](https://docs.eubucco.com/) / [DBSM R2025](https://data.jrc.ec.europa.eu/dataset/a601a4a8-9289-4fc4-983a-25d54f957f3a) / [GHS-OBAT 2025](https://www.researchgate.net/publication/392487937_GHS-OBAT_Global_Open_Building_Attribute_data_reporting_age_function_height_and_compactness_at_footprint_level) — EU / global building-stock attribute schemas.
- [OSM Key:roof:shape](https://wiki.openstreetmap.org/wiki/Key:roof:shape), [Key:roof:orientation](https://wiki.openstreetmap.org/wiki/Key:roof:orientation), [Key:roof:direction](https://wiki.openstreetmap.org/wiki/Key:roof:direction), [Key:roof:material](https://wiki.openstreetmap.org/wiki/Key:roof:material), [OSM-4D Roof table](https://wiki.openstreetmap.org/wiki/OSM-4D/Roof_table).
- [IfcRoofTypeEnum IFC 4.2](https://standards.buildingsmart.org/IFC/DEV/IFC4_2/FINAL/HTML/schema/ifcsharedbldgelements/lexical/ifcrooftypeenum.htm).
- [3DCityDB / CityGML LOD2 building module](https://3dcitydb-docs.readthedocs.io/en/release-v4.2.3/3dcitydb/schema/module/building.html).
- [Eurocode EN 1991-1-3 snow loads — DK NA](https://www.ds.dk/media/szmi4dvn/ds-en-1991-1-3-dk-na-2015-version-2-english.pdf).
- [Eurocode EN 1991-1-4 wind duopitch](https://eurocodeapplied.com/design/en1991/wind-pressure-duopitch-roof).
- [BR18 executive order](https://www.byggerietsregler.dk/wp-content/uploads/2018/09/BR18_Executive_order_on_building_regulations_2018.pdf).
- [EnergyPlus surface geometry](https://bigladdersoftware.com/epx/docs/23-2/input-output-reference/group-thermal-zone-description-geometry.html).
- [BE18 (Danish LCA / BR18)](https://help.oneclicklca.com/en/articles/275707-denmark-bygningsreglementet-br18-and-lca).
- [PVsyst orientations](https://www.pvsyst.com/help/project-design/orientations-in-v8/orientations-procedure.html).
- [NREL rooftop PV potential](https://docs.nrel.gov/docs/fy16osti/65298.pdf).
- [Müller et al., Procedural Modeling of Buildings](http://peterwonka.net/Publications/pdfs/2006.SG.Mueller.ProceduralModelingOfBuildings.final.pdf).
- [NRCA roof-slope guidelines](https://www.professionalroofing.net/Articles/Roof-slope-guidelines--08-01-2018/4284).
- [Danish longhouse typology](https://www.designboom.com/architecture/house-on-fano-lenschow-pihlmann-reinterprets-traditional-danish-longhouse-05-20-2020/).
- [Apple RoomPlan — Parametric Room Representation](https://machinelearning.apple.com/research/roomplan).

---

## Methodology appendix

### A.1 Pipeline

- **Implementation audit:** Explore agent scanned 9 analysis modules and extracted 396 column names.
- **Untapped-signal discovery:** Explore agent mined `reconcile_v3/models.py`, `buildings_3d.json`, `.context/*.topology-v2.{json,qa.json}`, `.context/v3_roof_proposal_splits.jsonl`, `reconcile_v3_results.json::audit_log` for fields not yet featured.
- **2024-2026 literature:** general-purpose agent ran 12 WebSearches across arXiv, ISPRS, IEEE, MDPI, Springer; extracted feature-level detail from 20+ papers.
- **Building-science cross-domain:** general-purpose agent surveyed Eurocode, BR18, EnergyPlus, BE18, PVsyst, NREL, CGA/shape grammar, IFC / CityGML, LiDAR-RANSAC literature.

### A.2 What this report is

- A **superset feature enumeration**, not a ranking or a model.
- A **gap closure** on v1 that records implementation state as of today.
- A **cross-domain checklist** spanning pipeline internals, graph topology, user behavior, academic literature, and building science.

### A.3 What this report is not

- Not a product spec.
- Not a training run.
- Not a commitment to implement all listed features.

### A.4 Verification priorities

Before any rule in Part 12 ships to the proposer or post-processor, verify in the viewer on 5 reject + 3 accept examples (per v1 methodology §VI.2).

### A.5 Known blind spots

- No BBR cadastre data joined to buildings yet; OSM.* and DR.4 require it.
- No orthophoto alignment; photometric features out of scope.
- No raw point clouds; the 22 `eig_*` features operate on polygon-vertex sets, which Hackel-style eigenvalue descriptors do handle but at lower resolution than true point-cloud eigen-descriptors.
- Reasons-taxonomy on label records still empty; binary accept/reject only.
- Topology-V2 files exist for 3 buildings in `.context/`, not all 111 — the TV2.* family requires that `reconcile_v2/cli.py` be run on every labeled building.

### A.6 Authoritativeness notes

- Feature-column names verified against `feature_expansion.py`, `advanced_features.py`, `building_features.py`, `context_features.py` as of commit on branch `mc/merge-room-building-json`, 2026-04-18.
- Label statistics (8,865 / 111) are as of the same date.
- Literature references: 2024-2026 papers taken from arXiv / publisher pages with direct URL citations; feature descriptions drawn from abstracts + introductions + feature sections, not full paper retrieval.

---

**End of V2 catalogue.**

Cross-references: v1 catalogue at `reports/slanted_roof_feature_catalogue.md`; implementation plan at `/Users/martincollignon/.claude/plans/system-instruction-you-are-working-melodic-octopus.md`.
