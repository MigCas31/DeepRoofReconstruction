# Exhaustive slanted-roof feature catalogue

> **Scope.** Reverse-engineer the accept/reject decision Martin makes on every `V3MergedRoofSegment` in the viewer. This document enumerates *every* signal that could plausibly help a classifier — not just what is already implemented. External-data features (BBR, orthophoto, neighbors, climate) are listed at the end but deliberately out of scope for the build.
>
> **Relationship to prior catalogues.**
> - `slanted_roof_feature_catalogue.md` (V1) — Band 1/2 labels + wall-aggregate prior art.
> - `slanted_roof_feature_catalogue_v2.md` (V2) — 396 live features audit + physics extensions.
> - `slanted_roof_feature_catalogue_v3.md` (V3) — 527 feature IDs across Parts A–N.
> - **This document (exhaustive)** — superset, re-organized by the user's categories (vertices, edges, faces, 3D position, neighbors, physics, architecture, relative positions, segments, kneewalls, drainage). Cross-references the feature IDs in the v3 catalogue where they exist; assigns new IDs where they don't.
>
> **Labels available today.** 11,925 labels across 141 buildings; 22.5 % accept base rate; single rater (martin@lun.energy); `reasons[]` empty on every record.
>
> **Rows available today.** 415 columns in `artifacts/features_expanded.parquet`. Of those, the top-40 by Cohen's d are dominated by `member_*`, `swall_*`, `drainage_*`, `normals_*`, `cluster_*`, `opposing_*`. The ceiling has *not* been found.
>
> **Status codes.**
> - **LIVE** — column present in `features_expanded.parquet`.
> - **READY** — data already on `V3MergedRoofSegment` / `V3Building` / `V3Part`; one feature-module call away.
> - **NEEDS_PLUMBING** — requires running a V1 ontology module, ingesting v1 results JSON, or extending the viewer event log.
> - **EXTERNAL** — requires BBR, orthophoto, neighbor, or climate data.
> - **TRAINING_ONLY** — derivable only from label telemetry (skip counts, latency, sibling labels); unavailable at inference time on new buildings.

## Table of contents

1. [Vertex-level signals](#1-vertex-level-signals)
2. [Edge-level signals](#2-edge-level-signals)
3. [Face / polygon signals](#3-face--polygon-signals)
4. [Plane-fit signals](#4-plane-fit-signals)
5. [Segment-level merging evidence](#5-segment-level-merging-evidence-cluster-scale)
6. [3D position signals](#6-3d-position-signals)
7. [Orientation signals](#7-orientation-signals-azimuth--inclination)
8. [Scale-invariant ratios](#8-scale-invariant-ratios)
9. [Neighbor / opposing-plane signals](#9-neighbor--opposing-plane-signals)
10. [Source-wall features](#10-source-wall-features)
11. [Per-room / per-story relational signals](#11-per-room--per-story-relational-signals)
12. [Part-scale signals](#12-part-scale-signals)
13. [Building-scale signals](#13-building-scale-signals)
14. [Footprint-relative position signals](#14-footprint-relative-position-signals)
15. [Relational rank signals](#15-relational-rank-signals)
16. [Coverage-coherence signals](#16-coverage-coherence-signals)
17. [Drainage and water-physics signals](#17-drainage-and-water-physics-signals)
18. [Gravitational / structural physics signals](#18-gravitational--structural-physics-signals)
19. [Kneewall signals](#19-kneewall-signals)
20. [Dormer signals](#20-dormer-signals)
21. [Ridge / hip / valley / eave signals](#21-ridge--hip--valley--eave-signals)
22. [Gable-extension signals](#22-gable-extension-signals)
23. [Typology signatures — per DK roof family](#23-typology-signatures--per-dk-roof-family)
24. [V1 ontology signals](#24-v1-ontology-signals)
25. [V2 topology signals](#25-v2-topology-signals)
26. [Cross-modal agreement signals](#26-cross-modal-agreement-signals)
27. [Counter-evidence / adversarial priors](#27-counter-evidence--adversarial-priors)
28. [Uncertainty-quantification signals](#28-uncertainty-quantification-signals)
29. [Scan-artefact signals](#29-scan-artefact-signals)
30. [Temporal / versioning signals](#30-temporal--versioning-signals)
31. [Label-behavior signals (training-only)](#31-label-behavior-signals-training-only)
32. [Idle V3 fields — ready to surface](#32-idle-v3-fields--ready-to-surface)
33. [External-data feature surface (out of scope)](#33-external-data-feature-surface-out-of-scope)
34. [Summary — feature count estimate](#34-summary--feature-count-estimate)
35. [Interaction / compound features](#35-interaction--compound-features)
36. [Meta-features about the classifier itself](#36-meta-features-about-the-classifier-itself)

---

## 1. Vertex-level signals

Every merged-roof segment is a polygon of XYZ corners. Individual corners carry identity, altitude, grid-alignment, and clustering semantics.

### 1.1 Vertex counts + simple aggregates `LIVE`

| Feature | Description | Status |
|---|---|---|
| `poly_vertex_count` | Total corners in the segment polygon. | LIVE |
| `poly_vertex_count_after_simplify` | Corners after Douglas-Peucker simplify at 0.05 m. | READY |
| `poly_unique_xy_count` | Distinct (x,z) pairs after rounding to 0.01 m. | READY |
| `poly_reflex_corner_count` | Corners with interior angle > 180°. | READY |
| `poly_acute_corner_count` | Corners with interior angle < 60°. | READY |
| `poly_right_angle_fraction` | Corners within ±5° of 90°. | READY |

### 1.2 Vertex Y-coordinate clustering `READY`

Roofs exhibit natural Y-bands: ridge vertices, eave vertices, gutter vertices, kneewall-top vertices. 1-D k-means over `corners[].y` with k ∈ {1, 2, 3} reveals the structure.

| Feature | Description |
|---|---|
| `vtx_y_range_m` | `max(y) - min(y)`. |
| `vtx_y_cluster_count_k2` | Silhouette-best k between 1 and 3 for y clustering. |
| `vtx_y_gap_at_median_m` | Vertical gap between the 2 Y-clusters if k=2. |
| `vtx_ridge_band_count` | Corners within 0.15 m of max(y). |
| `vtx_eave_band_count` | Corners within 0.15 m of min(y). |
| `vtx_ridge_band_fraction` | Ratio of ridge-band vertices to total. |
| `vtx_eave_band_fraction` | Ratio of eave-band vertices to total. |
| `vtx_mid_band_count` | Corners not in ridge or eave band. |
| `vtx_y_iqr_m` | Inter-quartile range of corner Y. |
| `vtx_y_skewness` | Skew of Y distribution (positive → ridge-heavy). |
| `vtx_y_kurtosis` | Kurtosis of Y distribution. |

### 1.3 Grid-snap artefacts (Apple RoomPlan) `READY`

RoomPlan snaps XZ to 0.1 m grids in many cases. A segment that is *too* grid-aligned is more likely a wall mis-classified as a roof; one that is *not* grid-aligned at all is a likely scan artefact.

| Feature | Description |
|---|---|
| `vtx_grid_snap_fraction_0p05` | Corners whose XZ lies within 0.025 m of a 0.05 m grid. |
| `vtx_grid_snap_fraction_0p1` | Same at 0.1 m. |
| `vtx_grid_snap_fraction_0p25` | Same at 0.25 m. |
| `vtx_grid_axis_alignment_deg` | Rotation offset of MRR from global X. |
| `vtx_grid_snap_std_m` | Std-dev of each corner's distance to the nearest grid point. |

### 1.4 Vertex-to-structure proximity `READY`

Each corner can be associated with the nearest structural element: a wall top, a floor slab, a kneewall top, another segment's edge.

| Feature | Description |
|---|---|
| `vtx_on_wall_top_count` | Corners within 0.1 m of the top Y of a wall in `room_boundary_refs`. |
| `vtx_on_wall_top_fraction` | Same, normalised. |
| `vtx_on_floor_slab_count` | Corners within 0.1 m of a `V3Slab.polygon` Y. |
| `vtx_on_kneewall_top_count` | Corners within 0.1 m of any kneewall top (from `roof_cell_complex`). |
| `vtx_outside_building_footprint_count` | Corners whose XZ lies outside `building_boundary_xz`. |
| `vtx_outside_building_footprint_max_m` | Max distance by which a corner escapes the footprint. |
| `vtx_on_opposing_segment_edge_count` | Corners within 0.05 m of an edge in any `opposing_planes` segment's corner-polygon. |

### 1.5 Vertex valence (for hypothetical roof-graph) `NEEDS_PLUMBING`

If we stitch all merged segments of a building into a single polyhedral complex, each vertex has a valence (number of incident edges / faces).

| Feature | Description |
|---|---|
| `vtx_valence_max` | Max per-vertex face count across corners. |
| `vtx_valence_min` | Min. |
| `vtx_valence_distribution_entropy` | Shannon entropy over valence histogram. |

---

## 2. Edge-level signals

Each merged segment contributes polygon edges. Edges are where ridges, hips, valleys, eaves and rakes live.

### 2.1 Edge geometry `LIVE + READY`

| Feature | Description | Status |
|---|---|---|
| `edge_count` | `poly_vertex_count` with the last edge closing the ring. | LIVE |
| `edge_length_m_sum` | Total perimeter. | LIVE |
| `edge_length_m_min` / `_max` / `_mean` / `_median` / `_std` / `_iqr` / `_gini` | Length distribution aggregates. | LIVE (partial) |
| `edge_shortest_to_longest_ratio` | `min / max`. | READY |
| `edge_length_cv` | Coefficient of variation. | READY |
| `edge_length_entropy_log` | Entropy of the length distribution after log-binning. | READY |
| `edge_azimuth_deg_std` | Std-dev of the XZ azimuth over all edges. | READY |
| `edge_azimuth_deg_modes_count` | Count of modes ≥ 20 ° apart in the azimuth histogram. | READY |
| `edge_turning_angle_sum_deg` | Sum of exterior turning angles around the polygon (≈ 360° for simple polygons). | LIVE (ADV) |
| `edge_turning_angle_std_deg` | Std-dev of turning angles. | LIVE (ADV) |

### 2.2 Edge classification by role `READY`

The polygon has edges that play structural roles: **ridge** (top, horizontal, adjacent to an opposing plane), **hip** (descending, adjacent to an opposing plane), **valley** (ascending, adjacent to an opposing plane with opposite azimuth), **eave** (bottom, horizontal, facing a wall top), **rake** (descending, facing a gable end).

| Feature | Description |
|---|---|
| `edge_is_ridge_count` | Edges satisfying: both endpoints in top Y-band + dihedral with an opposing plane ∈ (140°, 220°). |
| `edge_is_hip_count` | Edges descending from ridge to eave-band + dihedral with an opposing plane ∈ (90°, 180°). |
| `edge_is_valley_count` | Edges ascending + dihedral with opposing plane ∈ (180°, 270°). |
| `edge_is_eave_count` | Edges in bottom Y-band + aligned with a wall top azimuth (±10°). |
| `edge_is_rake_count` | Edges descending + aligned with a gable-end wall azimuth. |
| `edge_is_free_count` | Edges not touching any peer / wall / slab (floating; hint of incomplete coverage). |
| `edge_role_entropy` | Shannon entropy over {ridge, hip, valley, eave, rake, free}. |
| `edge_ridge_length_m` | Sum of ridge-edge lengths. |
| `edge_eave_length_m` | Sum of eave-edge lengths. |
| `edge_ridge_to_eave_length_ratio` | `ridge / max(eave, ε)`. |
| `edge_free_length_m` | Sum of free-edge lengths. |
| `edge_free_length_fraction` | `free / perimeter`. |

### 2.3 Edge dihedral angles `READY`

When two segments share an edge, the dihedral angle quantifies the "fold" between them. Steep dihedrals (< 120°) are hips/valleys; shallow (> 150°) are ridges.

| Feature | Description |
|---|---|
| `edge_shared_dihedral_deg_min` | Smallest dihedral with any opposing segment sharing the edge. |
| `edge_shared_dihedral_deg_max` | Largest. |
| `edge_shared_dihedral_deg_mean` | Mean over shared edges. |
| `edge_shared_dihedral_deg_std` | Std-dev. |
| `edge_shared_dihedral_deg_count_under_120` | Count of hip-like folds. |
| `edge_shared_dihedral_deg_count_over_150` | Count of ridge-like folds. |

### 2.4 Edge parallelism `READY`

Real-roof polygons have edge-pair parallelism structure (rectangles, trapezoids).

| Feature | Description |
|---|---|
| `edge_parallel_pair_count` | Pairs of edges whose azimuth differs by < 3° (modulo 180°). |
| `edge_parallel_pair_fraction` | Parallel pairs / `C(n,2)`. |
| `edge_perpendicular_pair_count` | Pairs at 90 ± 3°. |
| `edge_rectangularity_score` | Fraction of interior angles within 5° of 90°. |

### 2.5 Edge-to-wall alignment `READY`

An eave edge aligned with a wall-top edge in `room_boundary_refs` is strong accept evidence.

| Feature | Description |
|---|---|
| `edge_to_nearest_wall_top_m_min` | Minimum 3D distance from any edge midpoint to any wall-top polyline. |
| `edge_to_nearest_wall_top_m_median` | Same, median over all edges. |
| `edge_aligned_with_wall_count` | Edges whose azimuth matches a wall azimuth within ±5° and is within 0.3 m of the wall top. |
| `edge_aligned_with_wall_length_fraction` | Fraction of perimeter aligned with wall tops. |
| `edge_orthogonal_to_wall_count` | Edges orthogonal to any wall (hip/rake candidates). |

---

## 3. Face / polygon signals

The face *is* the segment.

### 3.1 Basic polygon metrics `LIVE`

| Feature | Description | Status |
|---|---|---|
| `poly_area_m2` | Shapely area. | LIVE |
| `poly_perimeter_m` | Shapely length. | LIVE |
| `poly_convex_hull_area_m2` | Hull area. | LIVE |
| `poly_convex_hull_perimeter_m` | Hull perimeter. | READY |
| `poly_solidity` | `area / hull_area`. | LIVE |
| `poly_aspect_ratio` | MRR long / short. | LIVE |
| `poly_mrr_length_m` / `_width_m` | Minimum rotated rectangle dimensions. | LIVE |
| `poly_bbox_aligned_length_m` / `_width_m` | Axis-aligned bbox. | LIVE |
| `poly_bbox_area_m2` | Axis-aligned bbox area. | READY |
| `poly_reflex_count` | Reflex vertices. | LIVE (partial) |
| `poly_interior_ring_count` | Holes (dormer cutouts). | READY |

### 3.2 Shape compactness descriptors `LIVE + READY`

Multiple compactness measures — each sensitive to different shape distortions.

| Feature | Description | Status |
|---|---|---|
| `polsby_popper` | `4π·A / P²`. | LIVE |
| `reock` | `A / (π·r_smallest_bounding²)`. | LIVE |
| `schwartzberg` | `P / (2π·√(A/π))`. | LIVE |
| `convex_deficiency` | `1 − A / A_hull`. | LIVE |
| `rectangularity` | `A / A_mrr`. | LIVE |
| `circularity` | `4π·A / P²` (alias of Polsby-Popper, included for completeness). | LIVE |
| `elongation` | `1 − w / l` where l, w are MRR. | LIVE |
| `form_factor` | `A / P`. | READY |
| `waviness` | `P / P_hull`. | READY |
| `roundness_ratio` | `4A / (π·l²)`. | READY |

### 3.3 Hu moment invariants `READY`

7 rotation-translation-scale-invariant shape descriptors from 2D image moments. Standard in shape-classification literature.

| Feature | Description |
|---|---|
| `hu_1` … `hu_7` | Hu's 7 moment invariants computed on the XZ polygon rasterised to a unit grid. |
| `hu_log_1` … `hu_log_7` | `sign(hu_i)·log10(|hu_i|)` for numerical stability. |

### 3.4 Fourier descriptors `LIVE`

Polygon perimeter re-sampled at N points, DFT gives shape modes.

| Feature | Description | Status |
|---|---|---|
| `fourier_mag_1` … `fourier_mag_16` | Magnitude of first 16 Fourier coefficients after arc-length resample. | LIVE (top 8) |
| `fourier_log_1` … `fourier_log_16` | Log of same. | LIVE (top 8) |
| `fourier_phase_1` … `fourier_phase_16` | Phase angles. | READY |
| `fourier_energy_fraction_top_5` | Fraction of total spectral energy in first 5 modes. | READY |

### 3.5 Inertia-tensor eigenvalues (Hackel shape families) `READY`

Point-cloud shape-descriptor family from 3D point-cloud learning, adapted to 2D polygons and to 3D corner cloud.

For the corners viewed as a 3D point set:

| Feature | Description |
|---|---|
| `hackel_linearity` | `(λ₁ − λ₂) / λ₁`. |
| `hackel_planarity` | `(λ₂ − λ₃) / λ₁`. |
| `hackel_scatter` | `λ₃ / λ₁`. |
| `hackel_omnivariance` | `(λ₁·λ₂·λ₃)^(1/3)`. |
| `hackel_anisotropy` | `(λ₁ − λ₃) / λ₁`. |
| `hackel_eigenentropy` | `− Σ (λᵢ/Σλ)·log(λᵢ/Σλ)`. |
| `hackel_curvature_change` | `λ₃ / (λ₁ + λ₂ + λ₃)`. |
| `hackel_sum` | `λ₁ + λ₂ + λ₃`. |

Compute the same 8 on the union of `member_snapshots[*].corners` to get the *cluster-level* Hackel family (prefix `hackel_cluster_*`).

### 3.6 3D Hu moments on XYZ corners `READY`

Same 7 moments as §3.3 but computed on the 3D XYZ point cloud, then on the 2D XZ projection, then on the 2D XY side-profile.

| Feature | Description |
|---|---|
| `hu3_xyz_1` … `hu3_xyz_7` | 3D Hu invariants. |
| `hu2_xz_1` … `hu2_xz_7` | 2D Hu on plan view. |
| `hu2_xy_1` … `hu2_xy_7` | 2D Hu on elevation view. |
| `hu2_zy_1` … `hu2_zy_7` | 2D Hu on side view. |

### 3.7 Symmetry `READY`

Gable legs and hip faces are symmetric by construction; a polygon that is symmetric under a 180° rotation about its centroid is typically a rectangle (accept-favoured); under reflection, trapezoidal.

| Feature | Description |
|---|---|
| `symmetry_rot180_iou` | IoU between polygon and its 180°-rotated copy about centroid. |
| `symmetry_reflect_x_iou` | IoU with X-reflected copy about centroid. |
| `symmetry_reflect_z_iou` | Same for Z. |
| `symmetry_reflect_principal_iou` | Reflection over the MRR principal axis. |
| `symmetry_best_reflection_deg` | Angle of the reflection axis that maximises IoU. |

### 3.8 Thin-sliver / degeneracy detectors `READY`

| Feature | Description |
|---|---|
| `poly_min_inscribed_circle_radius_m` | Largest circle inscribed in polygon. |
| `poly_pole_of_inaccessibility_m` | Shapely `maximum_inscribed_circle` radius. |
| `poly_min_width_m` | MRR short side. |
| `poly_is_sliver` | Bool: `min_width < 0.3 m AND aspect_ratio > 10`. |
| `poly_has_pinch_point` | Bool: exists pair of non-adjacent vertices with 3D distance < 0.1 m. |

### 3.9 Statistical centroid vs. centroid of mass `READY`

For uniform-density assumption the two coincide; divergence hints at non-convex / multi-lobed polygons.

| Feature | Description |
|---|---|
| `poly_centroid_x`, `_y`, `_z` | Area-weighted centroid of polygon (LIVE). |
| `poly_vertex_centroid_x`, `_y`, `_z` | Arithmetic mean of corners. |
| `poly_centroid_divergence_m` | Distance between polygon centroid and vertex centroid. |

### 3.10 Radial / Dirichlet shape descriptors `READY`

| Feature | Description |
|---|---|
| `radial_distance_mean_m` | Mean distance from centroid to perimeter. |
| `radial_distance_std_m` | Std. |
| `radial_distance_cv` | Coefficient of variation (0 = circle, high = spiky). |
| `radial_distance_autocorr_lag1` | Lag-1 autocorrelation around perimeter arc. |

---

## 4. Plane-fit signals

Each merged segment has a 4-tuple `merged_plane = (a, b, c, d)` with `a·x + b·y + c·z + d = 0`.

### 4.1 Plane coefficients + derived angles `LIVE`

| Feature | Description | Status |
|---|---|---|
| `plane_a`, `_b`, `_c`, `_d` | Raw coefficients. | LIVE |
| `plane_azimuth_deg` | Compass azimuth of downhill normal projected to XZ. | LIVE |
| `plane_incl_deg` | Inclination from horizontal (0 = flat, 90 = vertical). | LIVE |
| `plane_tilt_deg` | Alias for incl; angle from XZ. | LIVE |
| `plane_slope_ratio` | `tan(incl)` — rise/run. | READY |
| `plane_pitch_is_architectural` | Bool: 5° < incl < 80°. | LIVE |
| `plane_pitch_is_shallow` | Bool: 5° < incl < 20°. | READY |
| `plane_pitch_is_medium` | Bool: 20° ≤ incl < 50°. | READY |
| `plane_pitch_is_steep` | Bool: 50° ≤ incl < 80°. | READY |
| `plane_pitch_matches_dk_norm` | Bool: 25° < incl < 50° (typical DK residential). | READY |
| `plane_d_m` | Signed distance from origin to plane; useful as height proxy. | LIVE |

### 4.2 Plane-fit residuals from member proposals `LIVE`

The merged plane is a least-squares fit across member proposal planes; residuals quantify the fit quality.

| Feature | Description | Status |
|---|---|---|
| `slant_residual_rms_m` | RMS of per-member signed distance to `merged_plane`. | LIVE |
| `slant_residual_mae_m` | Mean absolute. | READY |
| `slant_residual_max_m` | Worst single-member residual. | READY |
| `slant_residual_iqr_m` | IQR of residuals. | READY |
| `slant_residual_skewness` | Skew of residual distribution. | READY |
| `plane_fit_r2` | Coefficient of determination across members. | READY |
| `member_plane_incl_spread_deg` | Spread of member inclinations before merging. | LIVE |
| `member_plane_azimuth_spread_deg` | Spread of member azimuths. | LIVE |
| `member_plane_d_spread_m` | Spread of member plane offsets. | LIVE |

### 4.3 Height-above-slab signals `LIVE`

| Feature | Description | Status |
|---|---|---|
| `member_plane_height_above_slab_m_mean` | Avg plane height above nearest `V3Slab`. | LIVE |
| `member_plane_height_above_slab_m_median` | Median. | LIVE |
| `member_plane_height_above_slab_m_min` / `_max` | Extremes. | LIVE |
| `member_plane_height_above_slab_m_std` | Std. | LIVE |
| `plane_top_y_m` | Highest Y on the segment polygon. | LIVE |
| `plane_mid_y_m` | Mean Y on segment polygon. | LIVE |
| `plane_bottom_y_m` | Lowest Y. | LIVE |
| `plane_y_extent_m` | `top − bottom`. | LIVE |
| `plane_y_extent_vs_story_height` | `plane_y_extent / typical_story_height`. | READY |

### 4.4 Principal-curvature-like descriptors on plane `READY`

If we sample the merged plane at many points and measure the difference from member planes, we recover a smoothness metric.

| Feature | Description |
|---|---|
| `plane_curvature_rms_m_per_m` | RMS bending curvature across member-plane residual field. |
| `plane_waviness_amplitude_m` | Peak-to-peak amplitude of member-plane residual. |
| `plane_normal_consistency_index` | Mean cosine similarity between the merged normal and each member normal. |

---

## 5. Segment-level merging evidence (cluster scale)

A merged segment aggregates N member `V3RoofProposal`s into a single plane. Members carry their own statistics.

### 5.1 Count / composition aggregates `LIVE`

| Feature | Description | Status |
|---|---|---|
| `cluster_member_count` | N. | LIVE |
| `snapshot_member_count` | Alias. | LIVE |
| `member_unique_source_walls` | Distinct source walls across members. | LIVE |
| `member_unique_source_rooms` | Distinct source rooms. | LIVE |
| `member_unique_source_stories` | Distinct stories. | LIVE |
| `member_wall_entropy` | Shannon entropy over source-wall distribution. | LIVE |
| `member_room_entropy` | Same over rooms. | LIVE |
| `member_story_entropy` | Same over stories. | READY |

### 5.2 Member geometry distribution aggregates `LIVE`

Over `N` members: length, inclination, azimuth, mid-Y, plane-d — each expanded to {min, max, mean, median, std, range}.

| Feature family | Description | Status |
|---|---|---|
| `member_segment_length_m_*` | 6 aggregates. | LIVE |
| `member_segment_incl_deg_*` | 6 aggregates. | LIVE |
| `member_segment_azimuth_deg_*` | 6 aggregates + azimuth-specific circular-mean. | LIVE |
| `member_segment_mid_y_m_*` | 6 aggregates. | LIVE |
| `member_plane_d_m_*` | 6 aggregates. | LIVE |
| `member_plane_height_above_slab_m_*` | 6 aggregates. | LIVE |
| `member_story_delta_max` / `_mean` / `_min` | Max delta between any two members' stories. | LIVE |

### 5.3 Circular-statistics for azimuth `READY`

Azimuth is on a 360° circle; arithmetic aggregates mis-behave. Proper circular mean + variance.

| Feature | Description |
|---|---|
| `member_azimuth_circular_mean_deg` | Atan2 of sum of unit vectors. |
| `member_azimuth_circular_variance` | 1 − |R|, where R is the resultant vector length. |
| `member_azimuth_resultant_length` | |R| / N. |
| `member_azimuth_is_unimodal` | Rayleigh-test p-value thresholded. |
| `member_azimuth_bimodality_index` | 2-mode mixture-model log-likelihood ratio. |

### 5.4 Cluster-parameter features `LIVE`

From `cluster_params` dict computed during merging.

| Feature | Description | Status |
|---|---|---|
| `cluster_plane_incl_tolerance_deg` | Tolerance used during grouping. | LIVE |
| `cluster_plane_azimuth_tolerance_deg` | Same. | LIVE |
| `cluster_plane_d_tolerance_m` | Same for offset. | LIVE |
| `cluster_algorithm_version` | String. | LIVE |

### 5.5 Heuristic label aggregates `LIVE`

Members carry a `heuristic_label ∈ {accepted, rejected, uncertain}` from the proposer.

| Feature | Description | Status |
|---|---|---|
| `member_heuristic_accepted_count` | Members with `accepted` label. | LIVE |
| `member_heuristic_accepted_fraction` | Normalised. | LIVE |
| `member_heuristic_rejected_count` | Same for `rejected`. | LIVE |
| `member_heuristic_rejected_fraction` | Normalised. | LIVE |
| `member_heuristic_uncertain_fraction` | Normalised. | LIVE |
| `member_heuristic_unanimous` | Bool: all members agree. | READY |

### 5.6 Member trace / rule-fired aggregates `READY`

Each `V3RoofProposal.trace.rule` is the pipeline stage that produced it.

| Feature | Description |
|---|---|
| `member_trace_rule_entropy` | Shannon entropy over member rules. |
| `member_trace_top_rule` | Most common rule (categorical). |
| `member_trace_rules_count` | Distinct rules. |

---

## 6. 3D position signals

Absolute position of the segment in world-space and in the building frame.

### 6.1 Absolute (UTM + local) `LIVE`

| Feature | Description | Status |
|---|---|---|
| `poly_centroid_x`, `_y`, `_z` | Local metres. | LIVE |
| `poly_centroid_utm_e`, `_utm_n` | UTM32N. | READY (via building transform) |
| `poly_top_y_m_abs` | Top Y in world frame. | LIVE |
| `poly_bottom_y_m_abs` | Bottom Y. | LIVE |

### 6.2 Relative to building `LIVE`

| Feature | Description | Status |
|---|---|---|
| `poly_centroid_x_rel_bld_center` | `x − bld_centroid_x`. | READY |
| `poly_centroid_z_rel_bld_center` | `z − bld_centroid_z`. | READY |
| `distance_to_footprint_edge_m` | Inside-footprint distance. | LIVE |
| `distance_to_footprint_center_m` | Plan-view distance. | READY |
| `distance_to_footprint_center_normalised` | / `sqrt(footprint_area)`. | READY |
| `poly_in_footprint` | Bool: centroid inside footprint. | READY |

### 6.3 Relative to ground `LIVE`

| Feature | Description | Status |
|---|---|---|
| `segment_story_index_mean` | Implicit via member story delta. | LIVE |
| `height_above_ground_m` | Centroid Y − ground Y. | READY |
| `height_above_ground_fraction` | / `bld_height_m`. | READY |

### 6.4 Relative to the building's principal axes `LIVE + READY`

| Feature | Description | Status |
|---|---|---|
| `poly_long_axis_projection_m` | Centroid projected on footprint major axis. | READY |
| `poly_short_axis_projection_m` | On minor axis. | READY |
| `poly_long_axis_projection_normalised` | / MRR long side. | READY |
| `bld_footprint_principal_axis_deg` | LIVE (Tier A addition). | LIVE |

---

## 7. Orientation signals (azimuth + inclination)

Where the plane points. Combined with 3D position, orientation is the most predictive signal family in the top-40 ranking.

### 7.1 Absolute azimuth `LIVE`

| Feature | Description | Status |
|---|---|---|
| `plane_azimuth_deg` | 0–360°. | LIVE |
| `plane_azimuth_sin`, `_cos` | Unit-circle encoding. | LIVE |
| `plane_azimuth_bucket_8` | 8-compass bucket (N, NE, E, ...). | READY |
| `plane_azimuth_bucket_16` | 16-way. | READY |

### 7.2 Relative azimuth `LIVE + READY`

| Feature | Description | Status |
|---|---|---|
| `plane_az_vs_bld_major_deg` | Folded 0–90. | LIVE (as `derived_*`) |
| `plane_az_vs_bld_minor_deg` | 90 − major. | READY |
| `plane_az_parallel_to_major` | Bool: < 15°. | READY |
| `plane_az_perpendicular_to_major` | Bool: > 75°. | READY |
| `plane_az_diagonal_to_major` | Bool: 35–55°. | READY |
| `plane_az_vs_nearest_wall_deg` | Min folded diff to any wall azimuth in building. | READY |

### 7.3 Inclination-based `LIVE`

| Feature | Description | Status |
|---|---|---|
| `plane_incl_deg` | 0–90. | LIVE |
| `plane_incl_sin`, `_cos` | Encoded. | READY |
| `plane_incl_bucket_5` | {flat, shallow, medium, steep, vertical}. | READY |
| `plane_incl_is_dk_typical` | Bool: 25–50°. | READY |
| `plane_incl_too_steep_for_residential` | Bool: > 60°. | READY |
| `plane_incl_too_shallow_for_oblique` | Bool: < 5°. | READY |

### 7.4 Normal-space aggregates `LIVE`

| Feature | Description | Status |
|---|---|---|
| `normals_a_mean`, `_std` | Across members. | LIVE |
| `normals_b_mean`, `_std` | Same. | LIVE |
| `normals_c_mean`, `_std` | Same. | LIVE |
| `normals_d_mean`, `_std`, `_entropy` | Same for plane-d. | LIVE |

---

## 8. Scale-invariant ratios

Ratios are more transferable across buildings of different sizes than absolutes.

| Feature | Description | Status |
|---|---|---|
| `area_vs_footprint_area_ratio` | `poly_area / bld_footprint_area`. | READY |
| `perimeter_vs_footprint_perimeter_ratio` | Same for perimeter. | READY |
| `area_vs_part_area_ratio` | `poly_area / part_footprint_area`. | READY |
| `perimeter_vs_part_perimeter_ratio` | Same. | READY |
| `plane_top_y_vs_bld_height_ratio` | `plane_top_y / bld_height`. | READY |
| `plane_y_extent_vs_story_height_ratio` | Same scale. | READY |
| `edges_vs_part_edges_ratio` | `edge_count / sum(edge_count in same part)`. | READY |
| `area_rank_in_part_normalised` | Rank / part_segment_count. | READY |
| `area_rank_in_building_normalised` | Rank / building_segment_count. | READY |
| `incl_vs_part_median_incl_ratio` | Segment incl / part median incl. | READY |
| `azimuth_spread_relative_to_part` | Angular spread / part angular spread. | READY |
| `segment_height_vs_max_segment_height` | `top_y / max(top_y in building)`. | READY |
| `member_count_vs_part_member_count` | / part-summed member count. | READY |
| `hull_efficiency_vs_part_median` | Solidity / part median solidity. | READY |
| `edge_count_vs_median_in_part` | / part-median edge_count. | READY |

---

## 9. Neighbor / opposing-plane signals

Each segment may have one or more *opposing* planes — peer segments that together form a gable, hip, or valley.

### 9.1 Count + basic aggregates `LIVE`

| Feature | Description | Status |
|---|---|---|
| `opposing_count` | Size of `opposing_planes`. | LIVE |
| `opposing_cluster_unique_count` | Distinct `cluster_canonical_id`s among opposites. | LIVE |
| `opposing_incl_mean_deg`, `_min_deg`, `_max_deg`, `_std_deg` | Inclination aggregates across opposing planes. | LIVE |
| `opposing_incl_diff_max_deg` | |self_incl − opp_incl| max. | LIVE |
| `opposing_incl_diff_mean_deg` | Same, mean. | LIVE |
| `opposing_azimuth_diff_max_deg` | Folded 0–180, max. | LIVE |
| `opposing_azimuth_diff_mean_deg` | Mean. | LIVE |

### 9.2 Gable-specific neighbor signals `READY`

Gables have exactly 2 opposing legs, roughly 180° apart in azimuth, with matching inclinations.

| Feature | Description |
|---|---|
| `opposing_is_gable_pair` | Bool: exactly 1 opposing, azimuth diff ∈ 160–200°, incl diff ≤ 5°. |
| `opposing_gable_incl_asymmetry_deg` | |incl_self − incl_opp| for the pair. |
| `opposing_gable_azimuth_offset_deg` | |az_diff − 180|. |
| `opposing_gable_ridge_colinearity` | Min distance from ridge-line to opposing's ridge-line. |
| `opposing_gable_eave_y_asymmetry_m` | |eave_y_self − eave_y_opp|. |
| `opposing_gable_area_ratio` | `area / opp_area`. |

### 9.3 Hip-specific neighbor signals `READY`

Hip faces have 3+ opposing planes forming a closed topology around the ridge.

| Feature | Description |
|---|---|
| `opposing_is_hip_trio` | Bool: 3 opposing, azimuths spaced ~120°. |
| `opposing_is_hip_quartet` | Bool: 4 opposing at ~90°. |
| `opposing_hip_closure_angle_deg` | Sum of opposing azimuth deltas (360 = closed). |

### 9.4 Cross-part opposition `READY`

Opposing planes in *different* `V3Part`s → likely wrong merging; opposing in *same* part → likely correct.

| Feature | Description |
|---|---|
| `opposing_same_part_count` | Opposing peers in the same part. |
| `opposing_cross_part_count` | In different parts. |
| `opposing_cross_part_fraction` | / `opposing_count`. |

### 9.5 Coplanar peers `READY`

Peer segments that are nearly coplanar (same plane equation within tolerance) are duplicate-candidates.

| Feature | Description |
|---|---|
| `coplanar_peer_count` | Peers with `|az_diff| < 5°` AND `|incl_diff| < 3°` AND `|d_diff| < 0.3 m`. |
| `coplanar_peer_union_area_m2` | Union area with all coplanar peers. |
| `coplanar_peer_overlap_area_m2` | Intersection area. |
| `coplanar_peer_is_rank_1_by_area` | Bool: this seg has the largest area among coplanar peers. |

---

## 10. Source-wall features

Each member proposal originates from a source wall. Source-wall consistency is a strong signal (5 of the top-40 features are `swall_*`).

### 10.1 Source-wall aggregates `LIVE`

| Feature | Description | Status |
|---|---|---|
| `swall_resolved_count` | Member proposals with a resolvable wall. | LIVE |
| `swall_unresolved_count` | Proposals with source wall missing. | READY |
| `swall_length_total` | Sum of source-wall lengths. | LIVE |
| `swall_length_min`, `_max`, `_mean`, `_median`, `_std` | Aggregates. | LIVE |
| `swall_top_y_mean`, `_std`, `_range`, `_min`, `_max` | Wall-top Y. | LIVE |
| `swall_centroid_to_seg_mean_m`, `_max_m` | Mean distance from wall centroid to segment centroid. | LIVE |
| `swall_azimuth_alignment_mean_deg` | Mean |wall_az − seg_az|. | READY |
| `swall_thickness_mean_m` | Wall thickness (V2 inference). | NEEDS_PLUMBING |
| `swall_thickness_std_m` | Same. | NEEDS_PLUMBING |

### 10.2 Source-wall categorical aggregates `READY`

| Feature | Description |
|---|---|
| `swall_is_exterior_count` | Exterior walls. |
| `swall_is_exterior_fraction` | /N. |
| `swall_has_door_count` | Walls with a door. |
| `swall_has_window_count` | With a window. |
| `swall_material_entropy` | Shannon entropy over wall materials (if present). |

---

## 11. Per-room / per-story relational signals

### 11.1 Room-level `READY`

| Feature | Description |
|---|---|
| `room_id_count` | Distinct rooms touched. |
| `room_floor_area_total_m2` | Total floor area of contributing rooms. |
| `room_floor_area_mean_m2` | Mean. |
| `room_has_simple_slant_count` | Rooms flagged `simple_slant`. |
| `room_is_top_story_count` | Rooms on the top story. |
| `room_is_top_story_fraction` | /N. |
| `room_has_dormer_count` | Rooms with `V3Dormer`. |

### 11.2 Story-level `READY`

| Feature | Description |
|---|---|
| `story_count_touched` | Distinct stories the segment spans. |
| `story_is_top_only` | Bool: only top story. |
| `story_index_max` | Highest story index. |
| `story_index_min` | Lowest. |
| `story_index_range` | max − min. |
| `member_story_delta_max` | LIVE. |
| `segment_crosses_story_boundary` | Bool: `story_count_touched > 1`. |

---

## 12. Part-scale signals

A `V3Part` is a connected component of a building's rooms; it carries a `GableExtension` verdict and derived metrics.

### 12.1 Gable-extension metrics `LIVE`

| Feature | Description | Status |
|---|---|---|
| `part_gable_status` | Categorical: complete / along / cross / ambiguous / absent. | LIVE |
| `part_gable_metric_n_slanted_roofs` | Slanted plane count in part. | LIVE |
| `part_gable_metric_major_az` | Part major axis azimuth. | LIVE |
| `part_gable_metric_ridge_az` | Detected ridge azimuth. | LIVE |
| `part_gable_metric_az0`, `_az1` | Gable-leg azimuths. | LIVE |
| `part_gable_metric_incl0`, `_incl1` | Gable-leg inclinations. | LIVE |
| `part_gable_tier1_reason_count` | # of Tier-1 rejection reasons. | LIVE |
| `part_gable_tier2_reason_count` | Tier-2. | LIVE |
| `part_gable_has_ridge_line` | Bool: `GableExtension.ridge_line` present. | READY |
| `part_gable_ridge_length_m` | Length of the ridge line. | READY |
| `part_gable_uncovered_region_area_m2` | Area of the uncovered XZ region. | READY |

### 12.2 Part size / shape `LIVE`

| Feature | Description | Status |
|---|---|---|
| `part_footprint_area_m2` | Shapely area. | LIVE |
| `part_footprint_perimeter_m` | Length. | LIVE |
| `part_footprint_aspect_ratio` | MRR. | LIVE |
| `part_footprint_elongation` | 1 − w/l. | LIVE |
| `part_footprint_solidity` | Area / hull area. | LIVE |
| `part_story_count` | Distinct stories in part. | LIVE |
| `part_room_count` | Room count. | LIVE |
| `part_has_kneewall` | Bool. | READY |
| `part_knee_wall_count` | From `roof_cell_complex`. | NEEDS_PLUMBING |

### 12.3 Part-derived roof-family `LIVE` (derived_features)

| Feature | Description | Status |
|---|---|---|
| `derived_part_roof_family_guess` | {gable, hip, shed, flat, complex, unknown}. | LIVE |
| `derived_part_n_slanted_roofs_eq_1` | Bool. | LIVE |
| `derived_part_n_slanted_roofs_eq_2` | Bool. | LIVE |
| `derived_part_n_slanted_roofs_ge_4` | Bool. | LIVE |
| `derived_plane_matches_gable_family` | Bool. | LIVE |
| `derived_plane_min_az_to_gable_leg_deg` | Min angular diff. | LIVE |

### 12.4 Rank within part `READY`

| Feature | Description |
|---|---|
| `seg_rank_in_part_by_area` | 1 = largest. |
| `seg_rank_in_part_by_height` | 1 = highest. |
| `seg_rank_in_part_by_incl` | 1 = steepest. |
| `seg_is_part_primary_roof` | Bool: rank 1 by area and incl > 20°. |
| `seg_fraction_of_part_roof_area` | / sum of all seg areas in part. |

---

## 13. Building-scale signals

### 13.1 Footprint `LIVE`

| Feature | Description | Status |
|---|---|---|
| `bld_footprint_area_m2` | Shapely area. | LIVE |
| `bld_footprint_perimeter_m` | Length. | LIVE |
| `bld_footprint_aspect_ratio` | MRR. | LIVE |
| `bld_footprint_elongation` | 1 − w/l. | LIVE |
| `bld_footprint_principal_axis_deg` | Principal axis. | LIVE |
| `bld_footprint_solidity` | Hull solidity. | READY |
| `bld_footprint_convexity_deficiency` | 1 − solidity. | READY |
| `bld_footprint_interior_ring_count` | Courtyards. | READY |
| `bld_footprint_is_L_shape` | Bool via convexity heuristic. | READY |
| `bld_footprint_is_T_shape` | Bool. | READY |
| `bld_footprint_is_U_shape` | Bool. | READY |
| `bld_footprint_is_rectangle` | Bool: rectangularity > 0.95. | READY |

### 13.2 Height / stories `LIVE`

| Feature | Description | Status |
|---|---|---|
| `bld_height_m` | Top Y − bottom Y. | LIVE |
| `bld_story_count` | Distinct stories. | LIVE |
| `bld_typical_story_height_m` | height / stories. | READY |
| `bld_has_basement` | Bool: any story index < 0. | READY |
| `bld_has_attic_story` | Bool: top story has slanted ceiling ratio > threshold. | READY |

### 13.3 Building interior counts `LIVE`

| Feature | Description | Status |
|---|---|---|
| `bld_room_count` | Total rooms. | LIVE |
| `bld_wall_count` | Total walls (all kinds). | LIVE |
| `bld_door_count` | Total doors. | LIVE |
| `bld_window_count` | Total windows. | LIVE |
| `bld_slab_count` | Total slabs. | LIVE |
| `bld_cross_floor_gap_count` | V3 gap count. | LIVE |
| `bld_wall_extension_count` | V3 wall-extension count. | LIVE |
| `bld_flat_ceiling_count` | V3 flat-ceiling count. | LIVE |
| `bld_slanted_roof_count` | V3 slanted-roof count. | LIVE |
| `bld_roof_proposal_count` | Pre-merge. | LIVE |
| `bld_merged_roof_segment_count` | Post-merge. | LIVE |
| `bld_dormer_count` | V3 dormer count. | LIVE |
| `bld_unresolved_region_count` | V3 unresolved. | LIVE |
| `bld_part_count` | V3 parts. | LIVE |

### 13.4 Building-level priors / base rates `READY`

| Feature | Description |
|---|---|
| `bld_accept_rate_history` | Historical accept rate for this UUID over past labels. |
| `bld_proposal_density` | `merged_roof_segment_count / footprint_area`. |
| `bld_complexity_index` | `part_count × story_count × aspect_ratio`. |
| `bld_scan_quality_score` | Mean of `overlap_metrics.*` fractions. |

### 13.5 Building-level orientation `READY`

| Feature | Description |
|---|---|
| `bld_dominant_wall_azimuth_deg` | Mode of wall azimuths. |
| `bld_wall_azimuth_entropy` | Entropy. |
| `bld_footprint_orientation_rank_cluster` | k-means cluster membership over orientation. |

---

## 14. Footprint-relative position signals

| Feature | Description | Status |
|---|---|---|
| `poly_inside_footprint_area_m2` | Intersection with footprint. | READY |
| `poly_outside_footprint_area_m2` | Area escaping footprint. | READY |
| `poly_outside_footprint_fraction` | / `poly_area`. | LIVE |
| `poly_overhang_exceeds_0p5m` | Bool: outside-fraction > 0.05 AND outside-max-distance > 0.5 m. | READY |
| `distance_to_footprint_edge_m` | Min interior distance. | LIVE |
| `distance_to_footprint_edge_normalised` | / `√footprint_area`. | READY |
| `poly_is_near_footprint_corner` | Bool: within 1 m of a footprint reflex corner. | READY |

---

## 15. Relational rank signals

| Feature | Description | Status |
|---|---|---|
| `seg_rank_in_bld_by_area` | 1 = largest. | READY |
| `seg_rank_in_bld_by_top_y` | 1 = highest. | READY |
| `seg_rank_in_bld_by_incl` | 1 = steepest. | READY |
| `seg_rank_in_cluster_by_area` | 1 = largest. | READY |
| `seg_percentile_area_in_bld` | 0–1. | READY |
| `seg_percentile_incl_in_bld` | 0–1. | READY |
| `seg_is_bld_unique_by_incl` | Bool: no peer within 5°. | READY |
| `seg_is_bld_unique_by_az` | Bool: no peer within 15° az. | READY |

---

## 16. Coverage-coherence signals

If we treat accepted segments as a set, their union tells us about coverage quality.

### 16.1 Per-part coverage `READY`

| Feature | Description |
|---|---|
| `part_coverage_union_area_m2` | Union of all seg polygons projected to XZ. |
| `part_coverage_union_to_footprint_ratio` | / `part_footprint_area`. |
| `part_coverage_gap_area_m2` | Footprint − union. |
| `part_coverage_gap_fraction` | / `part_footprint_area`. |
| `part_coverage_over_cover_area_m2` | Sum(seg areas) − union. |
| `part_coverage_over_cover_fraction` | / union. |
| `this_seg_coverage_contribution_m2` | Area exclusively covered by this seg. |
| `this_seg_coverage_contribution_fraction` | / `part_coverage_union_area`. |
| `this_seg_is_redundant` | Bool: removing it shrinks union by < 0.01 m². |
| `this_seg_covers_gap_region` | Bool: intersects the computed gap polygon. |

### 16.2 Per-building coverage `READY`

| Feature | Description |
|---|---|
| `bld_coverage_union_area_m2` | Over all parts. |
| `bld_coverage_union_to_footprint_ratio` | / `bld_footprint_area`. |
| `bld_coverage_gap_fraction` | Residual gap. |
| `bld_coverage_over_cover_fraction` | Over-cover. |

### 16.3 Height-coverage coherence `READY`

| Feature | Description |
|---|---|
| `part_y_coverage_range_m` | Max top_y − min bottom_y among accepted-family segs in part. |
| `this_seg_y_range_fraction` | `plane_y_extent` / part range. |
| `this_seg_is_above_part_median_y` | Bool. |

---

## 17. Drainage and water-physics signals

A roof exists because of weather. Drainage azimuth, mass balance, and outflow direction per part carry strong signal (top-ranked feature is `drainage_to_building_center_cos`).

### 17.1 Per-segment drainage `LIVE`

| Feature | Description | Status |
|---|---|---|
| `drainage_azimuth_deg` | Downhill azimuth. | LIVE |
| `drainage_to_building_center_cos` | Cosine with vector from centroid to building centroid. | LIVE |
| `drainage_to_footprint_edge_cos` | With vector to nearest footprint edge. | LIVE |
| `drainage_to_nearest_gutter_cos` | With vector to nearest gutter (exterior wall top). | READY |
| `drainage_to_ground_distance_m` | Travel distance until water hits ground. | READY |
| `rain_hitting_side_count` | Opposing peers exposed to prevailing wind. | LIVE |
| `covered_side_count` | Peers that shield this one from rain. | LIVE |

### 17.2 Per-part mass balance `READY`

| Feature | Description |
|---|---|
| `part_drainage_azimuth_resultant` | Sum of unit drainage vectors weighted by area. |
| `part_drainage_balance` | `|resultant|` — 0 = well-balanced, 1 = monopitch. |
| `part_drainage_azimuths_spread_deg` | Max − min. |
| `part_drainage_has_4way_split` | Bool: drainage vectors span all 4 quadrants. |

### 17.3 Watershed simulation `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `seg_watershed_downstream_count` | Peers that water flows into. |
| `seg_watershed_upstream_count` | Peers that flow into this. |
| `seg_watershed_is_ridge_origin` | Bool: upstream count = 0. |
| `seg_watershed_is_gutter_sink` | Bool: downstream count = 0 AND drains off-footprint. |

### 17.4 DK climate priors `EXTERNAL` (listed for completeness)

| Feature | Description |
|---|---|
| `clim_prevailing_wind_az_deg` | Regional prevailing wind. |
| `clim_snow_load_kpa` | Snow design load. |
| `clim_rain_mm_yr` | Annual rainfall. |
| `seg_windward_score` | Cosine of segment normal with prevailing wind. |

---

## 18. Gravitational / structural physics signals

### 18.1 Bearing / support `READY`

| Feature | Description |
|---|---|
| `seg_supported_by_wall_count` | Walls directly under the segment's edges. |
| `seg_supported_by_wall_length_m` | Sum of supporting-edge lengths. |
| `seg_supported_by_wall_fraction` | / perimeter. |
| `seg_has_eave_overhang` | Bool: portion over-hangs exterior wall top. |
| `seg_overhang_length_m` | Horizontal extent of overhang. |
| `seg_is_cantilevered` | Bool: not supported on > 50 % of perimeter. |

### 18.2 Self-weight / moment `READY`

| Feature | Description |
|---|---|
| `seg_area_moment_about_centroid_m4` | Second moment. |
| `seg_torque_about_building_center_m3` | Area × distance to centroid. |
| `seg_aspect_is_unstable` | Bool: aspect > 20 AND min_width < 0.3 m. |

### 18.3 Height feasibility `READY`

| Feature | Description |
|---|---|
| `plane_top_y_below_br18_cap` | Bool: < 12 m (BR18 residential cap). |
| `plane_top_y_above_building_physics_limit` | Bool: > 20 m — impossible. |
| `plane_bottom_y_below_slab` | Bool: impossible geometry. |
| `plane_normal_dot_gravity` | Dot product of plane normal with (0,1,0). |

---

## 19. Kneewall signals

Knee walls are low walls between the sloped ceiling and the attic floor. Their presence/absence distinguishes truly-attic from top-story-with-sloped-ceiling.

### 19.1 Per-building kneewall inventory `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `bld_knee_wall_count` | From `roof_cell_complex.knee_walls`. |
| `bld_knee_wall_total_length_m` | Sum of kneewall lengths. |
| `bld_knee_wall_occupied_shell_support_mean` | Avg `occupied_shell_support` across kneewalls. |
| `bld_knee_wall_dropped_count` | `metadata.knee_wall_dropped_by_occupied_shell`. |

### 19.2 Per-segment kneewall relation `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `seg_has_kneewall_below` | Bool: kneewall within 0.5 m XZ of segment's lower edge. |
| `seg_kneewall_distance_m` | Min distance to any kneewall. |
| `seg_kneewall_span_fraction` | Fraction of eave edge overlapping a kneewall. |
| `seg_kneewall_height_m` | Height of the kneewall below this segment. |
| `seg_kneewall_eave_consistency` | Bool: kneewall top Y ≈ segment eave Y. |

---

## 20. Dormer signals

Dormers punch holes in the roof. A segment that covers a dormer-locus is suspect; a segment that is itself a dormer face is distinct.

### 20.1 Per-building dormer inventory `READY`

| Feature | Description |
|---|---|
| `bld_dormer_count` | Distinct `V3Dormer` instances. |
| `bld_dormer_total_front_wall_length_m` | Sum. |
| `bld_dormer_total_surface_area_m2` | Sum of dormer roof areas. |

### 20.2 Per-segment dormer relation `READY`

| Feature | Description |
|---|---|
| `seg_is_dormer_front` | Bool: referenced as `V3Dormer.front_wall_id` source. |
| `seg_is_dormer_top` | Bool: matches `V3Dormer.roof_surface_id`. |
| `seg_contains_dormer_locus_count` | Interior rings or holes consistent with dormer pass-through. |
| `seg_dormer_proximity_m` | Min XZ distance to any dormer. |
| `seg_has_dormer_hole` | Bool: polygon has interior ring > 0.3 m². |

---

## 21. Ridge / hip / valley / eave signals

Segment-scoped roles derived from edge classification (§2.2) but aggregated per segment.

| Feature | Description | Status |
|---|---|---|
| `seg_has_ridge` | Bool: ≥ 1 ridge edge. | LIVE (`ridge_edge_length_m > 0`) |
| `seg_has_eave` | Bool: ≥ 1 eave edge. | LIVE |
| `seg_has_hip` | Bool: ≥ 1 hip edge. | READY |
| `seg_has_valley` | Bool: ≥ 1 valley edge. | READY |
| `seg_has_rake` | Bool: ≥ 1 rake edge. | READY |
| `seg_has_free_edge` | Bool: ≥ 1 edge with no peer. | READY |
| `ridge_edge_length_m` | LIVE. | LIVE |
| `eave_edge_length_m` | LIVE. | LIVE |
| `hip_edge_length_m` | READY. | READY |
| `valley_edge_length_m` | READY. | READY |
| `rake_edge_length_m` | READY. | READY |
| `ridge_to_eave_length_ratio` | LIVE. | LIVE |
| `seg_ridge_is_at_part_top` | Bool: ridge Y within 0.2 m of part's max Y. | READY |
| `seg_eave_is_at_wall_top` | Bool: eave Y within 0.2 m of supporting wall top. | READY |
| `seg_ridge_colinear_with_part_major` | Bool: |ridge_az − part_major| < 15°. | READY |
| `seg_ridge_colinear_with_bld_major` | Bool: same vs `bld_footprint_principal_axis`. | READY |

---

## 22. Gable-extension signals

Already partially live from `part_gable_*` — this section captures the segment-level projections.

| Feature | Description | Status |
|---|---|---|
| `derived_plane_matches_gable_family` | LIVE. | LIVE |
| `derived_plane_min_az_to_gable_leg_deg` | LIVE. | LIVE |
| `derived_gable_leg_az_delta_deg` | LIVE. | LIVE |
| `derived_ridge_vs_major_axis_deg` | LIVE. | LIVE |
| `derived_gable_leg0_vs_major_deg` | LIVE. | LIVE |
| `derived_gable_leg1_vs_major_deg` | LIVE. | LIVE |
| `seg_is_in_gable_tier1_reasons` | Bool: segment cited in `GableExtension.tier1_reasons`. | READY |
| `seg_is_in_gable_tier2_reasons` | Bool: same for tier2. | READY |
| `seg_intersects_gable_ridge_line` | Bool: ridge line passes through segment. | READY |
| `seg_covers_gable_uncovered_region_fraction` | Area intersection with `uncovered_region_xz`. | READY |

---

## 23. Typology signatures — per DK roof family

Danish residential roofs fall into a small taxonomy. Each family has a geometric signature. Emit one `is_<family>_candidate` + 3–5 continuous supporters per family.

### 23.1 Gable `READY` (partial LIVE)

| Feature | Description |
|---|---|
| `typ_gable_candidate` | Bool: 2 opposing planes with matching incl, 160–200° az diff. |
| `typ_gable_incl_symmetry_deg` | |incl_self − incl_opp|. |
| `typ_gable_ridge_horizontality` | Bool: ridge Y-std < 0.1 m. |
| `typ_gable_leg_azimuth_match` | Folded diff to major axis, 0–90°. |
| `typ_gable_eave_parallelism_to_ridge_deg` | Expected 0. |

### 23.2 Hip `READY`

| Feature | Description |
|---|---|
| `typ_hip_candidate` | Bool: ≥ 3 opposing planes spaced ~120° OR 4 at ~90°. |
| `typ_hip_closure_deg` | Sum of opposing az deltas; closed = 360°. |
| `typ_hip_has_apex_point` | Bool: all peers converge at a single vertex ±0.2 m. |
| `typ_hip_aspect_ratio` | Ratio of ridge to eave length. |
| `typ_hip_apex_height_above_eave_m` | Peak height. |

### 23.3 Shed / monopitch `READY`

| Feature | Description |
|---|---|
| `typ_shed_candidate` | Bool: `opposing_count == 0 OR 1` + incl ∈ [5°, 30°]. |
| `typ_shed_is_architectural` | Bool: incl > 10° AND area > 5 m². |
| `typ_shed_is_outbuilding_scale` | Bool: area < 20 m² AND footprint_fraction < 0.3. |

### 23.4 Mansard `READY`

Two stacked pitches: lower leg 45–70° incl, upper leg 5–25° incl, same azimuth (±10°).

| Feature | Description |
|---|---|
| `typ_mansard_candidate` | Bool: has a coplanar-az peer with different incl matching mansard ratios. |
| `typ_mansard_lower_leg_incl_deg` | If candidate. |
| `typ_mansard_upper_leg_incl_deg` | Same. |
| `typ_mansard_knuckle_y_m` | Junction Y between legs. |
| `typ_mansard_is_lower` | Bool: this seg is the steeper of the two. |

### 23.5 Gambrel `READY`

Mansard variant: 2 pitches on each side of a ridge.

| Feature | Description |
|---|---|
| `typ_gambrel_candidate` | Bool: 4 peers in two matched pairs. |

### 23.6 Flat `READY`

| Feature | Description |
|---|---|
| `typ_flat_candidate` | Bool: incl < 5°. |
| `typ_flat_is_ceiling_not_roof` | Bool: overlapped by a `V3FlatCeiling`. |

### 23.7 Pyramid `READY`

| Feature | Description |
|---|---|
| `typ_pyramid_candidate` | Bool: 4 peers sharing a single apex, matching incl. |
| `typ_pyramid_apex_distance_m` | Max spread of peers' top vertex. |

### 23.8 L-plan / T-plan / U-plan `READY`

Composition of multiple gables.

| Feature | Description |
|---|---|
| `typ_lplan_candidate` | Bool: part footprint is L-shape AND segment is one of two gables. |
| `typ_tplan_candidate` | Bool: T-shape. |
| `typ_uplan_candidate` | Bool: U-shape. |
| `typ_lplan_leg_index` | 0 or 1. |
| `typ_lplan_elbow_distance_m` | Distance from segment centroid to the L's interior corner. |

### 23.9 Half-hip / hipped-gable `READY`

| Feature | Description |
|---|---|
| `typ_half_hip_candidate` | Bool: gable candidate but one end has an additional hip face. |
| `typ_hipped_gable_candidate` | Bool: gable body with small hip triangle at each end. |

### 23.10 Tower / turret `READY`

| Feature | Description |
|---|---|
| `typ_tower_candidate` | Bool: pyramid or conical on a roof-footprint smaller than 10 m² AND top_y > bld_height − 1 m. |
| `typ_tower_is_conical` | Bool: radial symmetry score > 0.8. |

### 23.11 Kneewall-extended `READY`

| Feature | Description |
|---|---|
| `typ_knee_extended_candidate` | Bool: segment sits directly above a kneewall. |

### 23.12 Multi-pitch complex `READY`

| Feature | Description |
|---|---|
| `typ_complex_candidate` | Bool: ≥ 5 slanted planes in part AND no pure typology match. |

---

## 24. V1 ontology signals

Eight V1 modules produce structured dicts. Running them during the V3 pipeline (stage: `ontology_attachment`) and ingesting their outputs unlocks a large feature surface.

### 24.1 `roof_building_parts` (per-building-part) `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `ont_part_family_guess` | Categorical: {gable_or_multi_slope, flat_or_capped, mixed_or_partial}. |
| `ont_part_slant_ratio` | Ratio of sloped to total roof coverage. |
| `ont_part_max_room_slant_delta_m` | Max Y-delta of slant within a part. |
| `ont_part_articulation_room_count` | Rooms articulating multiple parts. |
| `ont_part_hypothesis_count` | # hypothesis references. |

### 24.2 `roof_cell_complex` `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `ont_cell_complex_flat_cell_count` | Detected flat cells. |
| `ont_cell_complex_oblique_cell_count` | Detected oblique cells. |
| `ont_cell_complex_mixed_cell_count` | Mixed. |
| `seg_cell_id` | ID of the cell the segment projects into. |
| `seg_cell_is_pure_flat` | Bool. |
| `seg_cell_is_pure_oblique` | Bool. |
| `seg_crosses_cell_boundary_count` | # of cells the segment spans. |

### 24.3 `roof_coverage_graph` `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `ont_coverage_confirmed_sloped_atom_count` | Atoms classified as "confirmed sloped". |
| `ont_coverage_partial_sloped_atom_count` | "Partial sloped". |
| `ont_coverage_subpart_count` | Sub-parts inferred. |
| `ont_coverage_gable_run_count` | Gable-run subparts. |
| `ont_coverage_l_t_subpart_count` | L/T branches. |
| `seg_atom_sloped_state` | Per-seg atom's `sloped_state` value. |
| `seg_subpart_semantic_kind` | {gable_run, l_t_branch, ...}. |
| `seg_subpart_member_count` | # segs in this subpart. |

### 24.4 `roof_evidence_graph` `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `ont_evidence_edge_tier_mean` | Avg evidence-tier across part edges. |
| `ont_evidence_supports_oblique` | Bool: part has strong evidence for sloped roof. |
| `seg_evidence_tier` | Per-seg edge evidence tier. |

### 24.5 `top_boundary_graph` `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `ont_top_boundary_ceiling_plane_count` | # ceiling planes. |
| `seg_projects_onto_ceiling_plane` | Bool. |
| `seg_ceiling_plane_azimuth_match_deg` | Diff. |

### 24.6 `roof_hypothesis_graph` + `select_roof_surfaces_from_hypotheses` `NEEDS_PLUMBING`

The "set cover" solver picks an optimal set of hypotheses; whether a merged segment matches a selected hypothesis is a cross-modal sanity check.

| Feature | Description |
|---|---|
| `ont_hypothesis_total_count` | # of hypotheses considered. |
| `ont_hypothesis_selected_count` | # selected. |
| `seg_hypothesis_match_selected` | Bool: segment's plane matches a selected hypothesis. |
| `seg_hypothesis_match_score` | Distance-to-match. |

### 24.7 `simple_slant.identify_simple_slant_rooms` `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `ont_room_is_simple_slant` | Bool per room; aggregated to per-seg via member room membership. |
| `seg_all_rooms_simple_slant` | Bool: all contributing rooms are simple-slant. |

### 24.8 `thermal_ceiling.*` `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `ont_thermal_ceiling_is_flat` | Bool. |
| `ont_thermal_ceiling_count` | # distinct thermal ceilings. |

### 24.9 `roof_flat_intermediate` `NEEDS_PLUMBING`

Intermediate flat hypothesis gate before the main flat detector.

| Feature | Description |
|---|---|
| `ont_flat_intermediate_candidate_count` | # intermediate flat candidates. |
| `seg_overlaps_flat_intermediate` | Bool. |

### 24.10 `roof_partitioning` `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `ont_partition_region_count` | # roof partitions. |
| `seg_partition_id` | Partition membership. |
| `seg_partition_area_m2` | Partition size. |

---

## 25. V2 topology signals

`reconcile_v2` builds a graph of rooms / walls / doors / windows / extensions with adjacency edges (`ADJACENT_TO`, `ABOVE`, `BELOW`) and inferred wall thickness.

### 25.1 Per-seg graph context `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `v2_node_count_adjacent_to_seg` | # nodes adjacent to seg's contributing rooms. |
| `v2_seg_is_in_gable_run_chain` | Bool: matches V2's gable-run chain. |
| `v2_seg_chain_length` | Length of the ridge/hip chain seg belongs to. |
| `v2_source_wall_thickness_m_mean` | V2-inferred wall thickness aggregated over source walls. |
| `v2_source_wall_thickness_m_std` | Std. |
| `v2_source_wall_is_exterior_fraction` | Fraction of contributing walls flagged exterior by V2. |

### 25.2 IFC class agreement `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `v2_ifc_class_mode` | Most common IFC class across source nodes. |
| `v2_ifc_class_entropy` | Entropy across source nodes. |

---

## 26. Cross-modal agreement signals

### 26.1 V1 ↔ V3 `NEEDS_PLUMBING`

V1's `reconcile/roof_algorithms_py_results.json` contains oblique + flat surface lists.

| Feature | Description |
|---|---|
| `xm_v1_oblique_match_exists` | Bool: V1 oblique surface within thresholds of V3 seg. |
| `xm_v1_oblique_match_azimuth_diff_deg` | Diff if match. |
| `xm_v1_oblique_match_incl_diff_deg` | Diff. |
| `xm_v1_oblique_match_centroid_distance_m` | 3D distance. |
| `xm_v1_match_count` | # V1 surfaces matching this seg. |
| `xm_v1_flat_match_exists` | Bool: V1 flat surface match. |
| `xm_v1_is_v3_orphan` | Bool: V3 seg has no V1 peer. |

### 26.2 V3 ontology ↔ V3 seg `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `xm_ontology_family_agrees` | Bool: `ont_part_family_guess` matches `derived_part_roof_family_guess`. |
| `xm_ontology_disagreement_mode` | Categorical: which guess each pipeline makes. |
| `xm_hypothesis_solver_selects_seg` | Bool. |
| `xm_cell_complex_agrees_with_ridge_class` | Bool. |

### 26.3 V2 topology ↔ V3 seg `NEEDS_PLUMBING`

| Feature | Description |
|---|---|
| `xm_v2_chain_membership_agrees` | Bool. |
| `xm_v2_gable_run_endpoint_matches_seg` | Bool. |

### 26.4 Heuristic ↔ human `TRAINING_ONLY` for eval only

| Feature | Description |
|---|---|
| `xm_heuristic_agrees_with_label` | Bool (training-time accuracy only). |
| `xm_heuristic_disagreement_rate_in_part` | Part-level disagreement. |

---

## 27. Counter-evidence / adversarial priors

Features that *specifically* look for reasons to reject.

### 27.1 Physical impossibility `READY`

| Feature | Description |
|---|---|
| `adv_plane_clips_into_wall_interior` | Bool: plane intersects a wall interior >0.2 m below the wall top. |
| `adv_plane_clips_through_floor` | Bool: plane crosses a `V3Slab`. |
| `adv_eave_below_floor` | Bool: eave Y < slab Y. |
| `adv_ridge_above_reasonable` | Bool: top Y > bld height + 2 m. |
| `adv_plane_is_vertical` | Bool: incl > 85° (likely a wall). |
| `adv_plane_is_horizontal` | Bool: incl < 2° (likely a slab). |

### 27.2 Scan-artefact priors `READY`

| Feature | Description |
|---|---|
| `adv_is_thin_sliver` | Bool (§3.8). |
| `adv_is_tiny_area` | Bool: area < 0.25 m². |
| `adv_has_single_member` | Bool: `cluster_member_count == 1`. |
| `adv_high_reflex_count` | Bool: `poly_reflex_count ≥ 3`. |
| `adv_low_grid_snap` | Bool: `vtx_grid_snap_fraction_0p05 < 0.1`. |
| `adv_high_min_inscribed_circle` | Bool: `poly_pole_of_inaccessibility_m < 0.15`. |

### 27.3 Duplication priors `READY`

| Feature | Description |
|---|---|
| `adv_duplicates_accepted_peer` | Bool: coplanar peer exists with `heuristic_label == "accepted"` covering > 80 % of this seg. |
| `adv_duplicate_cluster_canonical` | Bool: peer with identical `cluster_canonical_id` and substantial overlap. |
| `adv_overlap_with_accepted_peer_fraction` | Max IoU. |

### 27.4 Typology-violation priors `READY`

| Feature | Description |
|---|---|
| `adv_is_orphan_oblique` | Bool: LIVE. |
| `adv_gable_has_no_opposing` | Bool: gable candidate but no opposing peer. |
| `adv_hip_has_wrong_peer_count` | Bool: hip candidate but < 3 peers. |
| `adv_pitch_outside_dk_norm` | Bool: not in 25–50° AND not flat. |

### 27.5 Story spill `READY`

| Feature | Description |
|---|---|
| `adv_cross_story_without_part_support` | Bool: `member_story_delta_max > 0` AND `part_story_count == 1`. |
| `adv_above_top_story_ceiling` | Bool: plane bottom Y > top-story ceiling Y + 0.5 m. |

---

## 28. Uncertainty-quantification signals

### 28.1 From fitting process `LIVE`

| Feature | Description | Status |
|---|---|---|
| `slant_residual_rms_m` | LIVE. | LIVE |
| `member_plane_*_spread_*` | LIVE. | LIVE |
| `cluster_confidence_score` | LIVE? Review `cluster_params.confidence` if present. | READY |

### 28.2 Model-level (post-training) `READY`

| Feature | Description |
|---|---|
| `pred_gbm_proba` | Output of the gradient-boosted classifier. |
| `pred_gbm_margin` | `|2·proba − 1|`. |
| `pred_gbm_disagreement_with_tree` | Bool: tree predicts reject, GBM predicts accept, or vice versa. |
| `pred_ensemble_stddev` | Across seed-varied models. |
| `pred_shap_value_top_feature` | Most-influential SHAP value. |
| `pred_shap_entropy` | Entropy of |SHAP| distribution. |

### 28.3 Label-space uncertainty `TRAINING_ONLY`

| Feature | Description |
|---|---|
| `label_flip_stability_score` | Fraction of bootstrap replicas where label would flip. |
| `label_is_near_decision_boundary` | Bool: `|proba − 0.5| < 0.1`. |

---

## 29. Scan-artefact signals

Overlap with §27.2, pulled into its own cohort because RoomPlan imposes systematic biases.

| Feature | Description |
|---|---|
| `artefact_vertex_on_grid_fraction` | §1.3. |
| `artefact_incl_near_discrete_bucket` | Bool: incl within 1° of {0, 5, 10, 15, 22.5, 30, 35, 40, 45, 50, 60} — RoomPlan bucket preference. |
| `artefact_azimuth_near_cardinal` | Bool: az within 3° of {0, 90, 180, 270}. |
| `artefact_small_segment_from_doorway` | Bool: small area AND near a door. |
| `artefact_duplicated_wall_signature` | Bool: derived from a wall whose `walls_removed_in_overlap` count is high. |
| `artefact_from_scan_cache_only` | Bool: contributing walls all from `scan_cache_walls`. |
| `scan_quality_overlap_fraction` | Building-level: `overlap_metrics.floor_overlaps / room_count`. |
| `scan_quality_cross_floor_gap_density` | Building-level: `cross_floor_gaps / footprint_area`. |

---

## 30. Temporal / versioning signals

| Feature | Description | Status |
|---|---|---|
| `scan_age_days` | Days since scan timestamp. | NEEDS_PLUMBING |
| `scan_roomplan_version` | iOS RoomPlan SDK version. | NEEDS_PLUMBING |
| `pipeline_v3_git_sha` | Git sha at time of emit. | READY |
| `pipeline_v2_git_sha` | Same for V2. | READY |
| `pipeline_v1_git_sha` | Same for V1. | READY |
| `cluster_algorithm_version` | LIVE. | LIVE |
| `model_train_timestamp` | Injected at inference. | READY |
| `model_hash` | SHA256 of `.pkl`. | READY |
| `label_age_days_mean` | Mean age of labels in training set. | READY |

---

## 31. Label-behavior signals (training-only)

Not usable at inference, but valuable for training-set quality diagnostics and for sibling-aware retraining.

### 31.1 Per-segment behavior `TRAINING_ONLY`

| Feature | Description |
|---|---|
| `lbl_latency_ms` | Time between render and click. |
| `lbl_labeler_id` | Categorical. |
| `lbl_session_id` | Categorical (burst detection). |
| `lbl_skip_count_before_decide` | # times skipped before labeled. |
| `lbl_skip_count_in_session` | Skip fatigue proxy. |
| `lbl_was_split_child` | Bool. |
| `lbl_has_merge_event` | Bool. |
| `lbl_viewer_camera_az_deg` | If captured. |

### 31.2 Sibling aggregates `TRAINING_ONLY`

| Feature | Description |
|---|---|
| `sib_cluster_accept_fraction` | Accept rate among same-cluster sibs. |
| `sib_cluster_count` | # cluster sibs. |
| `sib_part_accept_fraction` | Same for part sibs. |
| `sib_bld_accept_fraction` | Same for building sibs. |
| `sib_coplanar_accept_fraction` | Among coplanar peers. |
| `sib_labeled_before_me_count` | Labeled chronologically before. |
| `sib_labeled_after_me_count` | After. |
| `sib_peer_label_entropy` | Entropy over sib labels. |
| `sib_peer_label_disagreement_rate` | Mixed-label peer fraction. |

### 31.3 Pitch / orientation base-rates `TRAINING_ONLY`

| Feature | Description |
|---|---|
| `lbl_pitch_bucket_accept_rate` | Historic accept rate for this incl bucket. |
| `lbl_azimuth_bucket_accept_rate` | Same for az bucket. |
| `lbl_family_accept_rate` | Per roof-family. |

---

## 32. Idle V3 fields — ready to surface

V3 dataclasses carry fields never read in `reconcile_v3/analysis/*.py`. Each is a free feature waiting for a 3-line aggregator.

### 32.1 `V3Gap` (cross-floor gaps) `READY`

| Feature | Description |
|---|---|
| `seg_gap_proximity_m` | Min 3D distance from seg to any `V3Gap`. |
| `seg_gap_adjacent_count` | `V3Gap`s within 0.5 m. |
| `bld_gap_floor_area_m2` | Sum of `V3Gap.footprint_xz` areas. |
| `bld_gap_to_footprint_ratio` | Same / `bld_footprint_area`. |
| `bld_gap_status_entropy` | Entropy over `V3Gap.status`. |

### 32.2 `V3Slab` (slabs) `READY`

| Feature | Description |
|---|---|
| `seg_nearest_slab_distance_m` | Min 3D. |
| `seg_is_above_slab_count` | # slabs directly below seg. |
| `bld_slab_area_total_m2` | Sum. |
| `bld_slab_count` | LIVE. |

### 32.3 `V3WallExtension` (strips extending walls) `READY`

| Feature | Description |
|---|---|
| `seg_wall_extension_contact_count` | # strips touching seg. |
| `seg_wall_extension_total_length_m` | Sum. |
| `seg_has_behind_knee_wall_extension` | Bool. |
| `bld_wall_extension_count` | LIVE. |

### 32.4 `V3FlatCeiling` (flat ceilings) `READY`

| Feature | Description |
|---|---|
| `seg_flat_ceiling_overlap_m2` | Area of seg polygon intersected with any `V3FlatCeiling.footprint_xz`. |
| `seg_flat_ceiling_overlap_fraction` | / `poly_area`. |
| `seg_is_mostly_a_flat_ceiling` | Bool: fraction > 0.7 AND incl < 10°. |
| `bld_flat_ceiling_area_total_m2` | Sum. |

### 32.5 `V3UnresolvedRegion` `READY`

| Feature | Description |
|---|---|
| `seg_unresolved_region_proximity_m` | Min distance to any unresolved region. |
| `seg_unresolved_region_overlap_m2` | Intersection area. |
| `bld_unresolved_region_area_total_m2` | Sum. |
| `bld_unresolved_reason_mode` | Categorical. |

### 32.6 `HypothesisTrace` on every entity `READY`

Every V3 entity has a `trace` (stage + rule + inputs + decision_reason) capturing which pipeline rule produced it.

| Feature | Description |
|---|---|
| `trace_stage` | LIVE? (partial). |
| `trace_rule` | Categorical. |
| `trace_rule_accept_rate_prior` | Historic accept rate for this rule. |
| `trace_decision_reason_token_entropy` | Entropy over decision_reason tokens across members. |

### 32.7 `GableExtension.ridge_line` + `uncovered_region_xz` `READY`

Already surfaced in §22; repeated here as idle source.

### 32.8 `V3Part.stories` `READY`

| Feature | Description |
|---|---|
| `part_story_index_min` | Min story index in part. |
| `part_story_index_max` | Max. |
| `part_story_index_range` | Range. |
| `part_has_basement` | Bool. |

---

## 33. External-data feature surface (out of scope)

Listed so we know the opportunity cost of the "no external data" constraint. Each bucket is a separate initiative; none is in scope for the build.

### 33.1 BBR (Danish Building & Housing Register) `EXTERNAL`

| Feature | Description |
|---|---|
| `bbr_usage_code` | Cat. |
| `bbr_construction_year` | Int. |
| `bbr_renovation_year` | Int. |
| `bbr_living_area_m2` | Float. |
| `bbr_floor_count_official` | Int. |
| `bbr_roof_material_code` | Cat. |
| `bbr_wall_material_code` | Cat. |
| `bbr_heating_type` | Cat. |
| `bbr_owner_type` | Cat. |
| `bbr_is_listed_building` | Bool. |
| `bbr_architectural_period` | Cat derived from construction year. |

### 33.2 Orthophoto (Datafordeler WMTS) `EXTERNAL`

Per-segment XZ-polygon sampled from the orthophoto tile gives colour/texture signatures.

| Feature | Description |
|---|---|
| `orto_rgb_r_mean`, `_g_mean`, `_b_mean` | Mean per channel. |
| `orto_rgb_*_std` | Std. |
| `orto_hsv_h_mean`, `_s_mean`, `_v_mean` | HSV. |
| `orto_glcm_contrast`, `_homogeneity`, `_energy` | Texture. |
| `orto_edge_density` | Canny edge count per area. |
| `orto_is_tiled_pattern` | Bool: Fourier peak at tile frequency. |
| `orto_shadow_mask_fraction` | Thresholded dark fraction. |
| `orto_estimated_roof_material` | Cat: {tile, slate, metal, thatch, tar}. |

### 33.3 Site neighbours `EXTERNAL`

| Feature | Description |
|---|---|
| `site_neighbor_count_within_20m` | # BBR neighbors. |
| `site_nearest_neighbor_distance_m` | Distance. |
| `site_neighbor_height_ratio` | Nearest neighbor height / own height. |
| `site_neighbor_density` | / m². |
| `site_is_detached` | Bool. |
| `site_row_house_membership` | Cat: {none, row, end-of-row}. |

### 33.4 Climate priors `EXTERNAL`

| Feature | Description |
|---|---|
| `climate_snow_load_kpa` | DMI snow load. |
| `climate_wind_load_kpa` | DMI wind. |
| `climate_prevailing_wind_az_deg` | Mean. |
| `climate_rain_mm_yr` | Annual rainfall. |

### 33.5 Cadastral / zoning `EXTERNAL`

| Feature | Description |
|---|---|
| `zone_type` | Cat. |
| `zone_max_roof_height_m` | Permit cap. |
| `zone_permitted_roof_materials` | Cat set. |

---

## 34. Summary — feature count estimate

Intent: ≥ 1,000 columns in `features_expanded.parquet` after all waves, before any pruning.

| Category | Live today | To add (READY) | To add (NEEDS_PLUMBING) | Total (excl. external) |
|---|---:|---:|---:|---:|
| Vertex (§1) | 0 | 28 | 3 | 31 |
| Edge (§2) | 15 | 40 | 0 | 55 |
| Face / polygon (§3) | 25 | 55 | 0 | 80 |
| Plane-fit (§4) | 15 | 15 | 0 | 30 |
| Segment-level / cluster (§5) | 50 | 20 | 0 | 70 |
| 3D position (§6) | 8 | 12 | 0 | 20 |
| Orientation (§7) | 10 | 18 | 0 | 28 |
| Scale-invariant ratios (§8) | 0 | 16 | 0 | 16 |
| Neighbor / opposing (§9) | 12 | 20 | 0 | 32 |
| Source wall (§10) | 15 | 10 | 2 | 27 |
| Per-room / story (§11) | 3 | 12 | 0 | 15 |
| Part-scale (§12) | 30 | 15 | 0 | 45 |
| Building-scale (§13) | 28 | 15 | 0 | 43 |
| Footprint-relative (§14) | 2 | 8 | 0 | 10 |
| Rank signals (§15) | 0 | 10 | 0 | 10 |
| Coverage (§16) | 0 | 18 | 0 | 18 |
| Drainage / water (§17) | 6 | 10 | 4 | 20 |
| Gravity / structural (§18) | 0 | 12 | 0 | 12 |
| Kneewall (§19) | 0 | 4 | 5 | 9 |
| Dormer (§20) | 2 | 8 | 0 | 10 |
| Ridge / hip / valley / eave (§21) | 4 | 16 | 0 | 20 |
| Gable-extension (§22) | 7 | 4 | 0 | 11 |
| Typology (§23) | 0 | 60 | 0 | 60 |
| V1 ontology (§24) | 0 | 0 | 45 | 45 |
| V2 topology (§25) | 0 | 0 | 10 | 10 |
| Cross-modal (§26) | 3 | 0 | 18 | 21 |
| Counter-evidence (§27) | 5 | 20 | 0 | 25 |
| Uncertainty (§28) | 5 | 10 | 0 | 15 |
| Scan artefact (§29) | 0 | 12 | 0 | 12 |
| Temporal (§30) | 2 | 8 | 2 | 12 |
| Label behavior (§31) | 0 | 0 | 25 (TRAINING_ONLY) | 25 |
| Idle V3 fields (§32) | 0 | 30 | 0 | 30 |
| Interaction / compound (§35) | 0 | 40 | 0 | 40 |
| **Total (exclusive)** | **242** | **544** | **114** | **900+** |

Meta-commentary: if we also emit the 60 polynomial-interaction features (§35.1), the parquet lands at ~960 columns — within reach of the 1,000-column target without touching external data.

---

## 35. Interaction / compound features

Some signal only appears in combinations. Tree-based learners discover these, but emitting them explicitly can tighten linear-baseline models and make rules more interpretable.

### 35.1 Polynomial interactions (top-K × top-K) `READY`

Take the top-20 features by Cohen's d; emit `top_i × top_j` and `top_i / top_j` for `i < j`.

| Feature family | Count |
|---|---:|
| Products | 190 (20C2) — keep best 30 |
| Ratios | 380 (20P2) — keep best 30 |

### 35.2 Domain-motivated interactions `READY`

| Feature | Description |
|---|---|
| `covered_side_count × member_heuristic_accepted_fraction` | Interaction: orphan (0 covered) with high heuristic accept → strong accept. |
| `drainage_to_building_center_cos × plane_incl_deg` | Inward-facing pitches. |
| `member_story_delta_max × part_story_count` | Cross-story in single-story part → red flag. |
| `edge_ridge_length_m × part_gable_metric_n_slanted_roofs` | Ridge length on gable. |
| `swall_centroid_to_seg_mean_m × cluster_member_count` | Distance anomaly for large clusters. |
| `poly_area × (1 − distance_to_footprint_edge_m/footprint_width)` | Area weighted by interiority. |
| `opposing_incl_diff_max_deg × opposing_count` | Severity of asymmetry. |
| `normals_d_entropy × cluster_member_count` | Normalised entropy. |

### 35.3 Symbolic regression / GP features `READY` (deferred)

Use `PySR` or similar to search for closed-form operators over the top-20; keep those that cross the F1-gain threshold.

---

## 36. Meta-features about the classifier itself

Self-reflective features that *describe* a segment's position in the feature space, not the segment itself.

| Feature | Description |
|---|---|
| `meta_isolation_forest_score` | Score from an IsolationForest fit on the training set. |
| `meta_local_outlier_factor` | Sklearn LOF. |
| `meta_knn_accept_fraction` | Accept rate among k=20 nearest neighbours in feature space. |
| `meta_knn_distance_mean_m` | Avg feature-space distance. |
| `meta_in_training_manifold` | Bool: > 0.5 of k-NN have same label. |
| `meta_cluster_label_from_unsupervised` | Cluster id from k-means over top-20 features. |
| `meta_low_density_region` | Bool: LOF > threshold. |

---

## Appendix A. Feature production sequence

To keep training and inference bit-for-bit identical (tested in `tests/test_score_results.py`), every wave follows the same merge order in both `scripts/analyze_labels.py` and `reconcile_v3/autonomy/inference_features.py::compute_features`:

1. `feature_expansion.expand(record)` — Band 1 (poly / plane / cluster / member / opposing / drainage / footprint / piece).
2. `building_features` — `bld_*`.
3. `context_features` — Band 3 (part_*, ridge_*, gable_*, kneewall_*, dormer_*).
4. `advanced_features` — Band 2 + 4 (swall_*, normals_*, polsby_*, reock_*, fourier_*, turning_*, vangle_*).
5. *(new)* `primitive_features` — §§1, 2.
6. *(new)* `shape_features` — §3.
7. *(new)* `relational_features` — §§9, 15.
8. *(new)* `coverage_features` — §16.
9. *(new)* `physics_features` — §§17, 18.
10. *(new)* `kneewall_dormer_features` — §§19, 20.
11. *(new)* `ontology_features` — §24 (requires stage `ontology_attachment`).
12. *(new)* `cross_modal_features` — §26.
13. *(new)* `counter_evidence_features` — §27.
14. *(new)* `typology_features` — §23.
15. *(new)* `scan_artefact_features` — §29.
16. *(new)* `interaction_features` — §35 (requires features from 1–15 to be present).
17. `derived_features` — Tier A (§12.3).

Interaction features run last so every input column is present. `meta_*` features (§36) run after training (injected at inference).

## Appendix B. Naming conventions

| Prefix | Meaning |
|---|---|
| `poly_*` | Polygon shape (the segment itself). |
| `plane_*` | Plane equation + derived angles. |
| `member_*` | Aggregate over cluster members. |
| `cluster_*` | Cluster-level scalars. |
| `opposing_*` | Aggregates over `opposing_planes`. |
| `swall_*` | Source-wall aggregates. |
| `bld_*` | Building-level scalars. |
| `part_*` | Part-level scalars. |
| `room_*` / `story_*` | Room / story aggregates. |
| `edge_*` | Polygon edge stats. |
| `vtx_*` | Polygon vertex stats. |
| `derived_*` | Tier A combinations. |
| `typ_*` | Typology signature booleans + supporters. |
| `ont_*` | V1 ontology signals. |
| `xm_*` | Cross-modal agreement. |
| `adv_*` | Counter-evidence / adversarial priors. |
| `seg_*` | Segment-centric relational signals. |
| `sib_*` | Sibling aggregates (TRAINING_ONLY). |
| `lbl_*` | Label behavior (TRAINING_ONLY). |
| `scan_*` / `artefact_*` | Scan-quality priors. |
| `meta_*` | Feature-space meta-descriptors. |

## Appendix C. Things we deliberately do NOT plan to add

| Reason | Features excluded |
|---|---|
| External data constraint | §33 in full (BBR, orthophoto, neighbors, climate, zoning). |
| Label-time only (inference invalid) | §31 sibling + latency. Keep for training-diagnostic use only. |
| Requires multi-rater data (structurally unobtainable) | Inter-rater agreement, Krippendorff α, labeler disagreement maps. |
| Requires proprietary CAD data | IFC-sourced material specs beyond what V2 already infers. |

## Appendix D. Open questions during implementation

1. When running V1 ontology during V3, do we regenerate `reconcile_v3_results.json` or a side-car file? (Default: side-car, `reconcile_v3_ontology.json`.)
2. For interaction features, do we emit before or after pruning? (Default: before; pruning is the last step.)
3. For `meta_*` features, the training-set feature-space is baked in; on a proposer regen it becomes stale. Refresh cadence: tie to model retrain.
4. Typology signature booleans for DK families are mutually-exclusive by construction but fuzzy in borderline cases. Emit as one-hot (exclusive) or as overlapping flags (non-exclusive)? Default: non-exclusive, let the GBM figure it out.

---

*End of exhaustive catalogue. Total discrete features enumerated (excluding external): ~900. Target 1,000 achievable by adding the §35.1 polynomial-interaction features.*
