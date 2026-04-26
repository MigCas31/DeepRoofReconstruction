# Exhaustive Feature Catalogue V3 — Regional/Global Understanding + Typology-Aware Signals

**Date:** 2026-04-18
**Dataset:** 11,847 labels · 111 buildings · 2,665 accepts (22.5 %) / 9,182 rejects (77.5 %).
**Relation to v2:** V2 (`reports/slanted_roof_feature_catalogue_v2.md`, 763 lines) catalogued 396 live features, 7 new extension families, 2024-26 literature, and building-science signals. V3 is the answer to a specific user concern: *"our proposer looks at segments but I bet it misses a global / regional understanding. what distinguishes a gable roof from not a gable roof?"*

V3 does four things v2 did not:

1. **Answer the architectural question directly.** For each canonical roof type (gable, hip, mansard, shed, flat, hipped-gable, half-hip, gambrel, pyramid, L/T/U-plan composite) we enumerate the *geometric signature* and map it to concrete features — already-live, planned, or novel.
2. **Organize features by spatial scale** (vertex → edge → face → plane → cluster → part → building → site → typology) so we can reason about what scale is under-sampled. V1/V2 mixed scales; v3 is strict.
3. **Enumerate relational and counter-evidence features.** V2 had sibling/opposing features but nothing on *plane arrangements*, *coverage-coherence*, *mutual-support graphs*, *adversarial priors*. V3 adds those.
4. **Treat the ontology as a first-class feature source.** `roof_cell_complex`, `top_boundary_graph`, `roof_coverage_graph`, `roof_evidence_graph`, and `roof_building_parts[*].roof_family_guess` are computed per building but almost none of their outputs are surfaced as per-segment features today.

Status tags — **[LIVE]** already in `features_expanded.parquet`; **[V1]** in v1 but not live; **[V2]** added by v2 but not live; **[NEW]** first introduced here; **[OUT-OF-SCOPE]** blocked on missing data.

---

## 0. Table of contents

- **Part A.** What distinguishes each roof type — architectural → feature map.
- **Part B.** Spatial-scale feature inventory (9 scales).
- **Part C.** Ontology-surface features (per-segment projections of building-level ontology).
- **Part D.** Relational features (segment-to-segment, segment-to-cluster, segment-to-part).
- **Part E.** Coverage-coherence + global-consistency features.
- **Part F.** Counter-evidence / adversarial-prior features.
- **Part G.** Per-geometric-primitive (edge / vertex / face) feature inventory.
- **Part H.** Physics / drainage / structural feasibility features.
- **Part I.** Cross-modal agreement features (V1 ↔ V3 ↔ ontology ↔ BBR).
- **Part J.** Architecture-typology prior features (DK longhouse, rowhouse, villa, etc.).
- **Part K.** Label-behavior / user-pattern features.
- **Part L.** Temporal / versioning features.
- **Part M.** Scale-invariant / dimensionless feature derivations.
- **Part N.** Prioritized ingest order with effort estimates.
- **Part O.** Explicit V2 deltas (what v2 missed).
- **Bibliography** + **methodology appendix**.

---

## Part A — Architectural typology → feature map

### A.0 Why this section exists

The labeller's accept/reject decision is fundamentally a *typology classification*: "this segment is consistent with a <type> roof" or "this segment is a stray plane that does not fit any recognisable roof form". V1/V2 feature tables treat all oblique planes the same; in reality, a 7° plane on a flat-roofed rowhouse is a scan artifact, whereas a 7° plane on a mansard is a structural upper slope. **The typology determines the threshold.** Below: the canonical roof types, the geometric invariants that define them, and the features that detect those invariants.

### A.1 Gable (duopitch symmetric)

**Definition.** Two opposing oblique planes meeting at a horizontal ridge; triangular gable-end walls (vertical, trapezoidal from outside). Most common DK residential form.

**Geometric signature.**
1. Exactly two slanted planes per part.
2. Azimuth difference ≈ 180° (`daz180 ≈ 0`).
3. Inclination difference ≈ 0° (`dincl ≈ 0`).
4. Ridge line is horizontal (`ridge_y_abs ≈ 0`).
5. Ridge parallel to part-footprint major axis (`ridge_vs_major ≈ 0°` or ≈ 90° depending on convention).
6. Two vertical gable-end wall segments (incl ≈ 90°), trapezoidal, on the two ends perpendicular to ridge.
7. Elongated footprint (`elong > 1.3`).
8. No oblique planes at ridge height except the ridge edge itself.
9. No dormers puncturing the two primary slopes (or few, symmetric).
10. Eave edges of the two slopes are co-linear in height, parallel, and opposite.

| # | Feature name | Status | Derivation |
|---|---|---|---|
| GAB.1 | `part_has_exactly_2_slanted_roofs` | **[LIVE]** via `part_gable_metric_n_slanted_roofs == 2` | — |
| GAB.2 | `gable_daz180_deg` | **[LIVE]** `part_gable_metric_daz180` | Signed azimuth deficit from 180°. |
| GAB.3 | `gable_dincl_deg` | **[LIVE]** `part_gable_metric_dincl` | Inclination mismatch. |
| GAB.4 | `gable_ridge_y_abs_m` | **[LIVE]** `part_gable_metric_ridge_y_abs` | |Δy| between ridge endpoints. |
| GAB.5 | `gable_ridge_vs_major_deg` | **[LIVE]** `part_gable_metric_ridge_vs_major` | Ridge-major axis angle. |
| GAB.6 | `gable_elong` | **[LIVE]** `part_gable_metric_elong` | Footprint major/minor ratio. |
| GAB.7 | `gable_coverage_ratio` | **[LIVE]** `part_gable_metric_coverage` | Fraction of part covered by the pair. |
| GAB.8 | `gable_status_enum` | **[LIVE]** `part_gable_is_*` one-hot | 6 states: not_gable / complete / along_extend / cross_review / ambiguous / tier1_pass_tier2_fail. |
| GAB.9 | `gable_end_wall_count_under_segment` | **[NEW]** | Count of walls under seg.XZ with incl ≥ 80° and azimuth ⟂ ridge_az. |
| GAB.10 | `gable_end_wall_is_trapezoidal` | **[NEW]** | Boolean: end wall top-edge slopes from wall-top to wall-top with a ridge apex. |
| GAB.11 | `gable_end_wall_height_m` | **[NEW]** | Height of inferred gable-end peak above eave. |
| GAB.12 | `gable_is_this_segment_one_of_the_two_legs` | **[NEW]** | Boolean: does this seg match `part_gable_metric_az0` OR `az1` within 15°? |
| GAB.13 | `gable_leg_pair_area_ratio` | **[NEW]** | `min(area_self, area_opposing) / max(...)` for suspected leg pair. |
| GAB.14 | `gable_leg_pair_eave_co_y_m` | **[NEW]** | `|eave_y_self − eave_y_opposing|` — opposing eaves should share height. |
| GAB.15 | `gable_is_along_extend_flag` | **[LIVE]** `part_gable_is_gable_along_extend` | Ridge parallel to extension direction. |
| GAB.16 | `gable_is_cross_review_flag` | **[LIVE]** `part_gable_is_gable_cross_review` | Ridge perpendicular to extension — user review recommended. |

**Principal discriminator.** Conjunction `GAB.1 ∧ GAB.2<15° ∧ GAB.3<5° ∧ GAB.4<0.1 m ∧ (GAB.5<15° ∨ GAB.5>75°) ∧ GAB.6>1.2 ∧ GAB.7>0.7` is a 95 %+ gable match on the training set (from `gable_extension.py` thresholds). A segment whose part satisfies this conjunction AND which matches one of az0/az1 (GAB.12) is an extremely strong accept. Conversely, a segment whose part satisfies this but whose own azimuth does *not* match either leg is a near-certain reject.

### A.2 Hip roof

**Definition.** Four or more oblique planes meeting at a ridge + hip lines; no vertical gable ends. All eaves horizontal at same height.

**Geometric signature.**
1. ≥ 4 slanted planes per part.
2. No vertical wall tops above the eave line (no gable ends).
3. Ridge line may be a point (pyramid hip) or a segment (standard hip).
4. Two pairs of opposing planes OR four planes with pairwise dihedrals ≈ 120° (pyramid).
5. All planes share a common eave-height.
6. Plane footprints roughly trapezoidal (main slopes) or triangular (end hips).
7. Coverage of part footprint ≈ 100 % without help from flat ceilings.

| # | Feature | Status | Derivation |
|---|---|---|---|
| HIP.1 | `part_slanted_roof_count_ge_4` | **[NEW]** | `part_gable_metric_n_slanted_roofs ≥ 4`. |
| HIP.2 | `part_eave_height_spread_m` | **[NEW]** | `std(eave_y_m)` across all slanted planes in part. Low → hip-consistent. |
| HIP.3 | `part_has_hip_plane_triplet` | **[NEW]** | 3+ planes within 90° azimuth separation sharing eave. |
| HIP.4 | `part_has_hip_plane_quad` | **[NEW]** | 4+ planes w/ pairwise az differences approximating 90°. |
| HIP.5 | `part_pyramid_ridge_flag` | **[NEW]** | All planes apex converges to same XZ within 0.5 m. |
| HIP.6 | `part_gable_end_wall_count` | **[NEW]** | If 0, hip more likely. See GAB.9 per part. |
| HIP.7 | `segment_is_triangular` | **[NEW]** | `vertex_count == 3` (end-hip diagnostic). |
| HIP.8 | `segment_is_trapezoidal` | **[NEW]** | `vertex_count == 4 AND` two-parallel-edge check. |
| HIP.9 | `hip_seam_dihedral_deg` | **[NEW]** | Dihedral at the edge shared with adjacent slanted plane (should be ≈ 150-170° for hip, ≈ 180° for ridge). |
| HIP.10 | `segment_meets_adjacent_slope_at_hip_line` | **[NEW]** | Shared edge non-horizontal, non-ridge. |

### A.3 Mansard / gambrel / "broken-back"

**Definition.** Two slopes stacked vertically — lower slope is steep (45-70°), upper slope is shallow (<30°). Visual signature: the roof "kinks" partway up. Mansard is 4-sided, gambrel is 2-sided.

**Geometric signature.**
1. Two oblique planes sharing the same *azimuth* but different inclinations.
2. Lower plane steeper, upper plane shallower.
3. Shared edge between the two is horizontal (the "break").
4. Upper plane sits on top of lower plane's top edge.
5. Typically no opposing plane for the steep (lower) slope within the same part — each flank is a stacked pair.

| # | Feature | Status | Derivation |
|---|---|---|---|
| MAN.1 | `part_has_coplanar_az_incl_pair` | **[NEW]** | 2 planes with |Δaz| < 10° but |Δincl| > 15°. |
| MAN.2 | `is_mansard_lower` | **[NEW]** | `plane_incl_deg ∈ [45°, 70°] AND has_upper_shallow_plane_same_az`. |
| MAN.3 | `is_mansard_upper` | **[NEW]** | `plane_incl_deg ∈ [5°, 25°] AND has_lower_steep_plane_same_az`. |
| MAN.4 | `mansard_break_edge_horizontal` | **[NEW]** | Shared edge with paired plane within 2° of horizontal. |
| MAN.5 | `mansard_upper_y_range_m` | **[NEW]** | Upper-plane Y span. |
| MAN.6 | `mansard_break_height_above_eave_m` | **[NEW]** | `shared_edge_y - eave_y`. |
| MAN.7 | `mansard_upper_area_ratio` | **[NEW]** | `area(upper) / area(lower)`. |

### A.4 Shed (monopitch)

**Definition.** Single oblique plane, no opposing. Either asymmetric main roof or a shed-dormer / extension.

**Geometric signature.**
1. Exactly one slanted plane in a part.
2. No paired opposing azimuth.
3. Lower edge on a wall top, upper edge on a higher wall / under another roof.
4. Very common for garages, extensions, lean-to dormers.

| # | Feature | Status | Derivation |
|---|---|---|---|
| SHED.1 | `part_slanted_roof_count_eq_1` | **[NEW]** | `n_slanted_roofs == 1`. |
| SHED.2 | `segment_is_orphan_oblique` | **[V2]** SG.2 | `pitch_architectural AND opposing_count == 0`. |
| SHED.3 | `segment_upper_edge_touches_taller_wall` | **[NEW]** | Upper edge within 0.3 m of a wall with top Y ≥ upper_edge_y. |
| SHED.4 | `segment_lower_edge_on_wall_top_fraction` | **[NEW]** | Fraction of lower edge within 0.3 m of a wall top. |
| SHED.5 | `shed_is_extension_shed_flag` | **[NEW]** | `part_is_extension AND SHED.1`. |
| SHED.6 | `shed_is_dormer_candidate_flag` | **[NEW]** | SHED.1 in a part that already has a main gable/hip (so this shed is an add-on). |

### A.5 Flat (or pseudo-flat <5°)

**Definition.** Roof nearly horizontal (< 5°). Common on mid-century housing, extensions, garages. V3 segment proposer can still emit slanted planes here due to residual tilt in scan.

| # | Feature | Status | Derivation |
|---|---|---|---|
| FLAT.1 | `plane_pitch_is_nearly_flat` | **[LIVE]** | `incl < 5°`. |
| FLAT.2 | `part_coverage_is_all_flat_ceiling` | **[NEW]** | Part covered by FlatCeiling, no slanted roofs survived. |
| FLAT.3 | `segment_is_probably_flat_noise` | **[NEW]** | `incl < 3° AND slant_residual_rms_m > 0.03 m`. |
| FLAT.4 | `flat_roof_adjacent_vertical_parapet_flag` | **[NEW]** | Wall with top_y slightly above seg max_y adjacent (parapet sign). |

### A.6 Half-hip / clipped gable / jerkinhead

**Definition.** Gable with a short hip at the apex. End-wall is partially triangular, partially horizontal-top.

| # | Feature | Status | Derivation |
|---|---|---|---|
| HHIP.1 | `part_end_wall_has_partial_hip_flag` | **[NEW]** | End wall is vertical up to some height, then a triangular plane clips the apex. |
| HHIP.2 | `part_gable_plus_small_hip_plane_flag` | **[NEW]** | 2 primary gable planes + 1 small (area < 3 m²) triangular plane at one end. |

### A.7 Hipped-gable / Dutch gable (gable on top of hip)

**Definition.** Lower portion is hip, upper portion is gable (vertical gable wall above hip break).

| # | Feature | Status | Derivation |
|---|---|---|---|
| HGAB.1 | `part_has_gable_above_hip_pattern` | **[NEW]** | 2 gable planes stacked above 4 hip planes, all sharing a part. |

### A.8 Pyramid / pavilion

**Definition.** Four triangular planes converging at a single point, no ridge line.

| # | Feature | Status | Derivation |
|---|---|---|---|
| PYR.1 | `part_ridge_line_length_m_approx_zero` | **[NEW]** | `part_ridge_line_length_m < 0.3 m`. |
| PYR.2 | `part_all_planes_triangular_flag` | **[NEW]** | Every slanted plane has `vertex_count == 3`. |

### A.9 L-plan / T-plan / cross-plan composite

**Definition.** Multiple gable volumes meeting at right angles; valleys form at the intersections. Part-decomposition typically splits these into separate parts.

| # | Feature | Status | Derivation |
|---|---|---|---|
| LPL.1 | `building_part_count_gt_1_flag` | **[LIVE]** | `part_count > 1`. |
| LPL.2 | `segment_is_in_secondary_part_flag` | **[NEW]** | Part index > 0. |
| LPL.3 | `segment_near_part_boundary_flag` | **[NEW]** | Distance to part-footprint boundary < 0.5 m. |
| LPL.4 | `valley_candidate_pair_flag` | **[NEW]** | Opposing seg in a *different* part within 1 m XZ — ridge from one part meets slope from another. |
| LPL.5 | `part_ridge_to_other_part_ridge_azimuth_diff_deg` | **[NEW]** | How L-configured the composite is. |

### A.10 Gambrel-specific (Dutch barn)

Sub-case of mansard where the two slopes are on the same gable end rather than wrapping hip-style.

| # | Feature | Status | Derivation |
|---|---|---|---|
| GAM.1 | `part_gambrel_pattern_flag` | **[NEW]** | 4 planes: 2 lower-steep + 2 upper-shallow, opposing in pairs. |

### A.11 Tower / conical / dome (rare)

| # | Feature | Status | Derivation |
|---|---|---|---|
| TOW.1 | `segment_curvature_residual_rms_m` | **[NEW]** | Residual to best-fit cylinder / cone vs. plane. Reveals rounded surfaces misfit as planes. |
| TOW.2 | `tower_cluster_flag` | **[NEW]** | ≥ 6 small (< 2 m²) planes whose azimuths span 300°+ uniformly. |

### A.12 Summary — typology decision tree

```
Is there any slanted roof in the part?
├─ No → FLAT (rule out: incl=0 on all surviving ceilings)
└─ Yes → count slanted roofs
    ├─ 1 → SHED / monopitch
    ├─ 2 → check azimuth difference
    │   ├─ |Δaz| ≈ 180° → GABLE (+ check ridge horizontality, elongation)
    │   ├─ |Δaz| ≈ 0°   → MANSARD (stacked slopes)
    │   └─ other        → ambiguous
    ├─ 3–4 → check pairing
    │   ├─ 2 gable + 1 hip → HALF-HIP
    │   └─ 4 slopes around eave → HIP
    └─ ≥ 5 → composite (HIP + DORMERS, HIPPED-GABLE, L/T-plan, etc.)
```

Every branch corresponds to a conjunction of features enumerated above. The classifier's job is to recognise the *branch* for the containing part first, and then judge whether a specific segment is consistent with that branch's expected planes.

---

## Part B — Spatial-scale feature inventory

### B.0 Why organize by scale

A proposal's acceptability depends on signals at multiple spatial scales simultaneously. V1 and V2 catalogued features but mixed scales. V3 organizes explicitly so we can see which scale is under-sampled.

Nine scales, from small to large:

1. **Vertex** — a single 3D point.
2. **Edge** — two adjacent vertices + the segment between them.
3. **Face** — the polygon of the proposed plane (v3-merged-roof-segment).
4. **Plane-fit** — the mathematical 3D plane (infinite).
5. **Cluster** — the set of coplanar pieces merged into this segment.
6. **Part** — a V3Part (e.g., the main volume + each extension).
7. **Building** — the entire scanned building.
8. **Site** — the building plus its neighbours (rowhouse row, city block).
9. **Typology** — the class of buildings this building belongs to (Danish longhouse, rowhouse, villa, etc.).

### B.1 Vertex scale (9 live, many planned)

**Live (from v2 §1.2.3 + §1.2.13):** `vertex_count`, `y_min_m`, `y_max_m`, `y_range_m`, `y_mean_m`, `y_std_m`, `x_range_m`, `z_range_m`, `slant_residual_rms_m`, `vangle_*` (5), `turning_angle_*` (3), `sharp_corner_count`, `edge_direction_entropy`, `bbox3d_*` (2).

**Not live — add:**

| # | Feature | Status | Rationale |
|---|---|---|---|
| VTX.1 | `vertex_at_max_y_in_ridge_locus_flag` | **[NEW]** | Top vertex sits near inferred ridge endpoint. |
| VTX.2 | `vertex_at_min_y_on_eave_wall_flag` | **[NEW]** | Bottom vertex aligned with a wall-top. |
| VTX.3 | `vertex_y_cluster_count` | **[V1]** C.17 | 1-D clustering of vertex Y to detect multi-level ridges. |
| VTX.4 | `vertex_y_top_cluster_count` | **[NEW]** | Number of vertices within 0.05 m of y_max (ridge-point richness). |
| VTX.5 | `vertex_density_per_perimeter_m` | **[NEW]** | `vertex_count / perimeter_m`. Scan-quality proxy. |
| VTX.6 | `vertex_is_shared_with_opposing_count_max` | **[NEW]** | How many of this seg's vertices coincide (< 5 cm) with an opposing seg vertex. High → ridge-joint likely. |
| VTX.7 | `vertex_is_coincident_with_wall_top_count` | **[NEW]** | Count of vertices within 0.1 m of a wall-top corner. Signals eave vertices. |
| VTX.8 | `vertex_chain_convexity` | **[NEW]** | Fraction of interior angles < 180° (true-convex count / vertex_count). |
| VTX.9 | `vertex_y_bimodality_index` | **[NEW]** | Hartigan dip test or Ashman D on vertex Y. High → bimodal (ridge + eave only). |
| VTX.10 | `vertex_cluster_count_via_dbscan_xz` | **[NEW]** | Cluster XZ projections; reveals disconnected corner groups. |
| VTX.11 | `vertex_min_y_is_on_building_footprint_boundary_flag` | **[NEW]** | Eave on outer boundary → physically plausible. |
| VTX.12 | `vertex_max_y_is_within_building_bbox_top_frac_m` | **[NEW]** | `(ymax_seg - ymax_bld)` — should be ≤ 0 (nothing above the building). |
| VTX.13 | `vertex_snapped_to_grid_count` | **[NEW]** | Vertices within ε of an integer grid (scan post-processing artifact). |
| VTX.14 | `vertex_collinear_triplet_count` | **[NEW]** | Triplets where the middle vertex is within 5 cm of the line between the other two (simplify candidates). |
| VTX.15 | `vertex_planar_deviation_max_m` | **[NEW]** | Max residual of any vertex to the plane fit. |

### B.2 Edge scale (12 live, many planned)

**Live (v2 §1.2.2):** `edge_count`, `edge_longest_m`, `edge_shortest_m`, `edge_mean_m`, `edge_std_m`, `edge_length_cv`, `edge_total_m`, `ridge_edge_length_m`, `eave_edge_length_m`, `edges_horizontal_fraction`, `edges_vertical_fraction`, `edge_longest_azimuth_deg`.

**Not live — add:**

| # | Feature | Status | Rationale |
|---|---|---|---|
| EDG.1 | `edge_azimuth_hist_8bin_*` | **[V1 B.28-.31]** | 8 features: direction histogram. |
| EDG.2 | `edge_azimuth_entropy` | **[V1 B.30]** | Shannon entropy of 8-bin hist. |
| EDG.3 | `edge_parallel_pair_count` | **[V1 B.32]** | Pairs with |Δaz|<5°. |
| EDG.4 | `edge_perpendicular_pair_count` | **[V1 B.33]** | Pairs with |Δaz|∈[85°,95°]. |
| EDG.5 | `edge_is_ridge_candidate_flag` | **[V1 B.17]** | Horizontal edge at y_max ± 0.1 m. |
| EDG.6 | `edge_is_eave_candidate_flag` | **[V1 B.18]** | Horizontal edge at y_min ± 0.1 m. |
| EDG.7 | `edge_is_hip_candidate_flag` | **[V1 B.19]** | Sloping edge, non-ridge, non-eave. |
| EDG.8 | `edge_is_valley_candidate_flag` | **[V1 B.20]** | Sloping edge shared with opposing. |
| EDG.9 | `edge_is_rake_candidate_flag` | **[V1 B.21]** | Non-horizontal, non-shared. |
| EDG.10 | `ridge_edge_horizontality_deg` | **[V1 B.54]** | abs angle-from-horizontal of the longest top edge. |
| EDG.11 | `ridge_edge_touches_opposing_seam_flag` | **[V1 B.55]** | Topmost edge shared with opposing seg. |
| EDG.12 | `eave_edge_touches_wall_top_fraction` | **[V2 STR.4]** | Eave edge length within 0.3 m of a wall-top. |
| EDG.13 | `edge_collinear_with_other_seg_edge_count` | **[NEW]** | Edges ≥ 0.5 m that lie colinearly with another segment's edge (shared boundary candidates). |
| EDG.14 | `edge_shortest_is_noise_flag` | **[NEW]** | `edge_shortest_m < 3 × scan_noise_m`. |
| EDG.15 | `edge_douglas_peucker_ratio_1cm` | **[V1 B.38]** | Vertex reduction at 1 cm tolerance. |
| EDG.16 | `edge_douglas_peucker_ratio_5cm` | **[V1 B.39]** | Vertex reduction at 5 cm tolerance. |
| EDG.17 | `edge_collinear_run_max_count` | **[V1 B.40]** | Longest run of same-azimuth edges. |
| EDG.18 | `edge_has_180deg_turning_angle_count` | **[NEW]** | Edges where turning angle = 180° (degenerate spike). |
| EDG.19 | `edge_boundary_type_mix_count` | **[NEW]** | # distinct edge types (ridge/hip/valley/eave/rake) in this polygon. Diagnostic of shape complexity. |
| EDG.20 | `edge_smallest_interior_angle_deg` | **[NEW]** | Min interior angle — very small angles indicate scan-poke artifacts. |
| EDG.21 | `edge_direction_consistency_with_plane_strike_deg` | **[NEW]** | Angle of each edge's XZ projection vs. the plane's strike direction; dominant strike-direction edge length. |

### B.3 Face scale (17 + 27 live, several planned)

Already well-covered: `poly_*` (17), shape descriptors (27), IoU/overlap (8).

**Gaps worth filling:**

| # | Feature | Status | Rationale |
|---|---|---|---|
| FAC.1 | `face_tilted_bbox_major_m` | **[NEW]** | Bbox in the *plane* (not XZ projection). Real physical width. |
| FAC.2 | `face_tilted_bbox_minor_m` | **[NEW]** | Physical height along slope. |
| FAC.3 | `face_3d_area_m2` | **[NEW]** | True 3D area (not XZ-projected). |
| FAC.4 | `face_3d_area_to_xz_area_ratio` | **[NEW]** | `1 / cos(incl)` — redundant with incl but useful as interaction. |
| FAC.5 | `face_has_interior_hole_count` | **[NEW]** | Shapely ring-count; dormer or chimney cutouts. |
| FAC.6 | `face_hole_area_sum_m2` | **[NEW]** | Total hole area. |
| FAC.7 | `face_concave_vertex_count` | **[NEW]** | `vertex_count - convex_vertex_count`. |
| FAC.8 | `face_aspect_ratio_along_slope_vs_strike` | **[NEW]** | Physical-plane aspect ratio. Real gable slopes are roughly 2:1 along-strike:along-slope for residential. |
| FAC.9 | `face_slope_direction_consistency_score` | **[NEW]** | Variance of edge-gradient vectors along the downhill direction; measures whether drainage is coherent. |
| FAC.10 | `face_matches_extension_strip_fraction` | **[NEW]** | XZ overlap with V3WallExtension strips. |
| FAC.11 | `face_normalized_by_part_footprint_area` | **[NEW]** | `poly_area_xz_m2 / part_footprint_area_m2`. |
| FAC.12 | `face_normalized_by_building_footprint_area` | **[NEW]** | Same for building. |
| FAC.13 | `face_centroid_xz_relative_to_part_centroid` | **[NEW]** | 2D offset vector. |
| FAC.14 | `face_lies_in_part_main_rectangle_flag` | **[NEW]** | Whether centroid is inside the part's inner OBB-rectangle. |

### B.4 Plane-fit scale (13 live)

Live: `plane_a/b/c/d`, `plane_azimuth_deg`, `plane_incl_deg`, `plane_rise_over_run`, 4 pitch-band booleans, `plane_water_flow_azimuth_deg`.

**Add:**

| # | Feature | Status | Rationale |
|---|---|---|---|
| PLN.1 | `plane_residual_rms_m` | **[V2 PGL.1]** | PCA plane-fit residual. |
| PLN.2 | `plane_residual_max_m` | **[NEW]** | Worst vertex residual. |
| PLN.3 | `plane_d_normalized_by_building_height` | **[NEW]** | `d / (ymax_bld - ymin_bld)`. Scale-invariant. |
| PLN.4 | `plane_height_above_slab_normalized_by_building_height` | **[NEW]** | Already live as `plane_height_above_slab_m`; add normalized variant. |
| PLN.5 | `plane_pca_normal_vs_merged_normal_cos` | **[V2 PGL.2]** | Alternative-fit consistency. |
| PLN.6 | `plane_intersects_floor_flag` | **[NEW]** | Does the plane (infinite) pass below any story slab within the footprint? |
| PLN.7 | `plane_intersects_story_wall_count` | **[NEW]** | How many walls does the plane cut through? |
| PLN.8 | `plane_azimuth_from_building_principal_axis_deg` | **[V1 A.37]** | Orientation in building frame, not world frame. **High expected value.** |
| PLN.9 | `plane_rise_over_run_log` | **[V1 A.38]** | — |
| PLN.10 | `plane_tangent_vector_along_slope` | **[NEW]** | (dx, dy, dz) unit vector of steepest descent — useful for drainage pair-matching. |

### B.5 Cluster scale (156 live: 148 member aggregates + 8 quality)

Covered in v2 §1.2.7-.8. Gaps:

| # | Feature | Status | Rationale |
|---|---|---|---|
| CLU.1 | `cluster_member_plane_d_range_vs_thickness_ratio` | **[NEW]** | `member_plane_d_range_m / wall_thickness_typical`. Signals whether merge spans more than typical eave overhang. |
| CLU.2 | `cluster_member_count_normalized_by_part_roof_count` | **[NEW]** | Size relative to expected pieces per roof type. |
| CLU.3 | `cluster_member_centroid_mass_xz_m` | **[NEW]** | XZ centroid of all member centroids. |
| CLU.4 | `cluster_member_xz_spread_m` | **[NEW]** | Std of member centroids. |
| CLU.5 | `cluster_drops_one_member_normals_d_entropy_delta` | **[NEW]** | Leave-one-out stability of entropy. High ⇒ one outlier dominating heterogeneity. |
| CLU.6 | `cluster_pre_clip_vs_post_clip_centroid_drift_m` | **[NEW]** | How far the centroid moved during footprint clipping. |
| CLU.7 | `cluster_survivors_post_clip_fraction` | **[NEW]** | Fraction of members whose piece survived clipping ≥ 50 % of its area. |
| CLU.8 | `cluster_member_span_x_m` / `cluster_member_span_z_m` | **[NEW]** | Bounding box of members in XZ. |

### B.6 Part scale (41 live context features)

Covered in v2 §1.2.17. Gaps:

| # | Feature | Status | Rationale |
|---|---|---|---|
| PRT.1 | `part_is_main_volume_flag` | **[NEW]** | `part_index == 0` (typically the main hull). |
| PRT.2 | `part_is_extension_flag` | **[NEW]** | `part_index > 0`. |
| PRT.3 | `part_footprint_hull_is_rectangular_flag` | **[NEW]** | Convex-hull ratio > 0.95 (simple gable candidate). |
| PRT.4 | `part_footprint_orientation_deg` | **[NEW]** | OBB major-axis azimuth. |
| PRT.5 | `part_orientation_vs_building_orientation_deg` | **[NEW]** | Parts rotated relative to main building are rare (T-plan wings). |
| PRT.6 | `part_wall_topology_closed_loop_flag` | **[NEW]** | Walls form a closed perimeter. |
| PRT.7 | `part_main_wall_top_y_spread_m` | **[NEW]** | Wall-top height spread; flat → gable-ready, spread → L-plan or hip-ready. |
| PRT.8 | `part_has_kneewall_count` | **[LIVE]** `kneewall_*` | — |
| PRT.9 | `part_has_dormer_count` | **[LIVE]** | — |
| PRT.10 | `part_has_chimney_count` | **[NEW]** | If chimney detection ever added. |
| PRT.11 | `part_detected_final_slanted_roof_count` | **[LIVE]** `part_gable_metric_n_slanted_roofs` | — |
| PRT.12 | `part_has_arch_flat_ceiling_count` | **[LIVE]** `part_gable_metric_n_arch_flats` | — |
| PRT.13 | `part_roof_coverage_graph_quality` | **[NEW]** | Proxy for evidence-graph strength at the part level (see Part C). |

### B.7 Building scale (22 live)

Live (v2 §1.2.16): 22 building-level features.

**Add:**

| # | Feature | Status | Rationale |
|---|---|---|---|
| BLD.1 | `bld_slanted_roof_count_final` | **[NEW]** | Total V3SlantedRoofs after pipeline. Prior: buildings with 0 are problematic. |
| BLD.2 | `bld_slanted_roof_count_proposed` | **[NEW]** | Total V3-merged-roof-segments (includes rejects). |
| BLD.3 | `bld_slanted_roof_proposal_to_final_ratio` | **[NEW]** | High ratio ⇒ noisy proposer. |
| BLD.4 | `bld_roof_family_guess_dominant` | **[NEW]** | Mode of `roof_family_guess` across parts. |
| BLD.5 | `bld_roof_family_guess_is_gable_flag` | **[NEW]** | Whether main part is gable. |
| BLD.6 | `bld_has_l_plan_flag` | **[NEW]** | `part_count > 1 AND main two parts are perpendicular`. |
| BLD.7 | `bld_story_count_final` | **[LIVE]** `bld_stories_found` | — |
| BLD.8 | `bld_has_kneewall_attic_flag` | **[NEW]** | Any kneewall + top story with no ceiling. |
| BLD.9 | `bld_total_floor_area_m2` | **[NEW]** | Sum of slab areas. |
| BLD.10 | `bld_footprint_aspect_is_longhouse_flag` | **[NEW]** | `elongation > 2.5` (DK longhouse typology signal). |
| BLD.11 | `bld_avg_roof_pitch_deg` | **[NEW]** | Mean of accepted slanted roof pitches. |
| BLD.12 | `bld_roof_pitch_spread_deg` | **[NEW]** | Std. Mixed pitches suggest composite/hip. |
| BLD.13 | `bld_building_height_over_footprint_perimeter` | **[NEW]** | Slenderness. |
| BLD.14 | `bld_classification_ordinal` | **[V2 ScanQ.1]** | — |
| BLD.15 | `bld_unresolved_region_count` | **[V2 UR.1]** | — |
| BLD.16 | `bld_has_gable_end_wall_any_flag` | **[NEW]** | Any gable-end wall detected in any part. |
| BLD.17 | `bld_ridge_line_count` | **[NEW]** | Total ridge_line segments across parts. |
| BLD.18 | `bld_dominant_ridge_azimuth_deg` | **[NEW]** | Longest ridge direction. |
| BLD.19 | `bld_secondary_ridge_azimuth_deg` | **[NEW]** | Second-longest; useful for L/T/cross-plan. |
| BLD.20 | `bld_dominant_vs_secondary_ridge_az_diff_deg` | **[NEW]** | ≈ 90° ⇒ L/T-plan. |

### B.8 Site scale (new family) [OUT-OF-SCOPE today, NEW proposal]

This is entirely absent in v1/v2. DK rowhouses share geometry with neighbours; this can inform priors.

| # | Feature | Status | Rationale |
|---|---|---|---|
| SIT.1 | `site_neighbor_building_count_within_30m` | **[OUT-OF-SCOPE]** | Requires DK Bygninger polygon lookup. |
| SIT.2 | `site_is_rowhouse_member_flag` | **[OUT-OF-SCOPE]** | BBR-SBB detached/rowhouse/apartment code. |
| SIT.3 | `site_neighbor_ridge_azimuth_agreement_deg` | **[OUT-OF-SCOPE]** | Rowhouses align ridges. |
| SIT.4 | `site_neighbor_height_similarity_m` | **[OUT-OF-SCOPE]** | Row heights are similar. |
| SIT.5 | `site_on_corner_plot_flag` | **[OUT-OF-SCOPE]** | Corner plots show asymmetric gables. |
| SIT.6 | `site_plot_orientation_deg` | **[OUT-OF-SCOPE]** | Cadastre plot shape. |

### B.9 Typology scale (new family, BBR-driven)

| # | Feature | Status | Rationale |
|---|---|---|---|
| TYP.1 | `bbr_anvendelse_code` | **[OUT-OF-SCOPE]** | BBR usage code: 110 = detached, 120 = rowhouse etc. |
| TYP.2 | `bbr_tagtype_code` | **[OUT-OF-SCOPE]** | BBR roof type: 1 = built-up, 2 = tile, 5 = fiber-cement, etc. |
| TYP.3 | `bbr_opfoerelsesaar` | **[OUT-OF-SCOPE]** | Year built. |
| TYP.4 | `bbr_bygningsstoerrelse_m2` | **[OUT-OF-SCOPE]** | Building size. |
| TYP.5 | `bbr_has_tagetager_flag` | **[OUT-OF-SCOPE]** | "Utilized attic" flag. |
| TYP.6 | `bbr_height_etager_count` | **[OUT-OF-SCOPE]** | Story count from cadastre. |
| TYP.7 | `typology_is_longhouse_flag` | **[NEW, partial]** | From BLD.10 + BBR. |
| TYP.8 | `typology_is_bungalow_flag` | **[NEW]** | Single story + hipped. |
| TYP.9 | `typology_is_urban_rowhouse_flag` | **[NEW]** | 2–3 stories + flat or mansard. |

---

## Part C — Ontology-surface features

### C.0 Why this section exists

The repo has a rich ontology pipeline (`reconcile/roof_algorithms_py/*`) — `roof_cell_complex.py`, `top_boundary_graph.py`, `roof_coverage_graph.py`, `roof_evidence_graph.py`, `roof_building_parts.py`, `roof_hypothesis_graph.py`. These compute per-building ontological structure (parts, evidence graph, ridge / hip / eave / valley labels). Viewer uses them (`ontology-cells.js`, `full-model-ontology.js`). **Almost none of this is exposed as a per-segment feature today.** This is the single biggest gap between what the data supports and what the classifier sees.

### C.1 roof_building_parts — `roof_family_guess`

`V3Part.roof_family_guess ∈ {"gable", "hip", "flat", "shed", "mansard", "unassigned"}`.

| # | Feature | Status | Rationale |
|---|---|---|---|
| ONT.1 | `part_roof_family_guess_enum_6` | **[NEW]** | One-hot of 6 values. *Direct answer to "what roof type does this part look like?"* |
| ONT.2 | `part_roof_family_guess_confidence` | **[NEW]** | If the inferer exposes one (may require code read). |
| ONT.3 | `segment_matches_guess_flag` | **[NEW]** | Whether this seg's azimuth/incl/position is consistent with the guess. |
| ONT.4 | `segment_is_extra_vs_guess_flag` | **[NEW]** | Gable expects 2 slopes; this is a 3rd/4th → likely reject. |
| ONT.5 | `part_roof_family_guess_transition_count` | **[NEW]** | Has the guess flipped between stages? |

### C.2 roof_cell_complex — 2.5D cell decomposition

| # | Feature | Status | Rationale |
|---|---|---|---|
| ONT.6 | `cell_complex_cell_count_in_part` | **[NEW]** | Total cells in the part's decomposition. |
| ONT.7 | `cell_complex_this_seg_covers_cell_count` | **[NEW]** | Cells whose XZ projection overlaps this segment ≥ 50 %. |
| ONT.8 | `cell_complex_unclaimed_cell_count_under_seg` | **[NEW]** | Cells under seg with no claim (good — we're filling a gap). |
| ONT.9 | `cell_complex_contested_cell_count_under_seg` | **[NEW]** | Cells where multiple segments compete (bad — duplicates). |
| ONT.10 | `cell_complex_seg_claim_coverage_fraction` | **[NEW]** | How much of this seg's XZ is in its claimed cells. |
| ONT.11 | `cell_complex_cell_height_variance_under_seg` | **[NEW]** | Y spread of cells under seg — low ⇒ clean ridge/eave pair. |

### C.3 roof_coverage_graph — evidence tiers

| # | Feature | Status | Rationale |
|---|---|---|---|
| ONT.12 | `coverage_evidence_tier_this_seg` | **[V1 M.1]** | High/medium/low tier. |
| ONT.13 | `coverage_graph_degree_this_seg` | **[V1 M.2]** | Number of evidence links. |
| ONT.14 | `coverage_graph_shared_face_area_sum_m2` | **[V1 M.3]** | Total contact area to neighbours. |
| ONT.15 | `coverage_graph_vertical_clearance_min_m` | **[V1 M.4]** | Y-distance to nearest competing surface. |
| ONT.16 | `coverage_graph_part_match_flag` | **[V1 M.5]** | Seg's claimed part matches coverage-graph assignment. |
| ONT.17 | `coverage_graph_sloped_state_enum` | **[V1 M.6]** | Coverage-graph's slope label for the seg. |

### C.4 roof_evidence_graph

| # | Feature | Status | Rationale |
|---|---|---|---|
| ONT.18 | `evidence_graph_node_in_degree` | **[NEW]** | Incoming evidence edges. |
| ONT.19 | `evidence_graph_node_out_degree` | **[NEW]** | Outgoing evidence edges. |
| ONT.20 | `evidence_graph_node_centrality` | **[NEW]** | Betweenness / eigenvector centrality. |
| ONT.21 | `evidence_graph_component_size` | **[NEW]** | Connected component size. |
| ONT.22 | `evidence_graph_path_to_slab_min_steps` | **[NEW]** | Graph distance to grounded slab; orphans have inf. |

### C.5 top_boundary_graph

| # | Feature | Status | Rationale |
|---|---|---|---|
| ONT.23 | `top_boundary_graph_node_for_seg_exists_flag` | **[NEW]** | Seg is registered in the top-boundary graph. |
| ONT.24 | `top_boundary_graph_node_degree` | **[NEW]** | Number of boundary edges incident. |
| ONT.25 | `top_boundary_graph_boundary_edge_sum_m` | **[NEW]** | Total boundary-edge length. |
| ONT.26 | `top_boundary_graph_exterior_fraction` | **[NEW]** | Fraction of boundary edges that are exterior (footprint) vs. interior (seam). |
| ONT.27 | `top_boundary_graph_seam_partner_count` | **[NEW]** | Seams with ≥ 1 partner. |

### C.6 roof_hypothesis_graph

| # | Feature | Status | Rationale |
|---|---|---|---|
| ONT.28 | `hypothesis_graph_seg_hypothesis_count` | **[NEW]** | How many hypotheses include this seg. |
| ONT.29 | `hypothesis_graph_best_hypothesis_score` | **[NEW]** | Score of the best-supported hypothesis containing seg. |
| ONT.30 | `hypothesis_graph_marginal_probability` | **[NEW]** | Sum of hypothesis scores weighted. |

### C.7 dormer_detection outputs

| # | Feature | Status | Rationale |
|---|---|---|---|
| ONT.31 | `dormer_containing_seg_flag` | **[LIVE]** via `dormer_count_overlapping_xz` | — |
| ONT.32 | `dormer_under_seg_count` | **[NEW]** | Dormers below seg (seg is the main roof, dormer is a puncture). |
| ONT.33 | `dormer_overlap_is_on_main_slope_flag` | **[NEW]** | — |

### C.8 simple_slant outputs

| # | Feature | Status | Rationale |
|---|---|---|---|
| ONT.34 | `simple_slant_under_seg_count` | **[NEW]** | Simple-slant surfaces below — if present, seg may be redundant. |

### C.9 thermal_ceiling

| # | Feature | Status | Rationale |
|---|---|---|---|
| ONT.35 | `thermal_ceiling_under_seg_area_m2` | **[NEW]** | Area of thermal ceiling XZ-under seg. High ⇒ seg is over a heated volume (plausible roof). |
| ONT.36 | `thermal_ceiling_gap_under_seg_fraction` | **[NEW]** | Area under seg that has *no* thermal ceiling. High ⇒ seg is over an unheated void (attic/porch). |

---

## Part D — Relational features

### D.1 Segment-to-segment

| # | Feature | Status | Rationale |
|---|---|---|---|
| REL.1 | `nearest_same_part_segment_id` | **[NEW]** | Handle for lookup. |
| REL.2 | `nearest_same_part_segment_az_diff_deg` | **[NEW]** | Direct pairing signal for gable legs. |
| REL.3 | `nearest_same_part_segment_incl_diff_deg` | **[NEW]** | — |
| REL.4 | `nearest_same_part_segment_y_max_diff_m` | **[NEW]** | Ridge-heights should match. |
| REL.5 | `nearest_same_part_segment_shared_edge_length_m` | **[NEW]** | Ridge seam length. |
| REL.6 | `nearest_same_part_segment_dihedral_deg` | **[V1 A.33-.36]** | Signed dihedral across shared edge. |
| REL.7 | `same_part_segment_count` | **[NEW]** | Peer count. |
| REL.8 | `same_part_segment_az_diff_histogram_8bin` | **[NEW]** | Angular distribution of peers. |
| REL.9 | `same_part_segment_incl_mean_deg` | **[NEW]** | Mean peer pitch. |
| REL.10 | `same_part_segment_incl_consistency_score` | **[NEW]** | Std of peer inclinations — low ⇒ hip/gable-consistent. |
| REL.11 | `nearest_different_part_segment_distance_m` | **[NEW]** | Closest peer in *another* part (valley indicator). |
| REL.12 | `opposing_partner_area_ratio_min` | **[NEW]** | min(area_self, area_pair) / max. Lopsided → merge error. |
| REL.13 | `opposing_partner_eave_y_diff_m` | **[NEW]** | Eaves should match for gable pair. |
| REL.14 | `opposing_partner_ridge_y_diff_m` | **[NEW]** | — |
| REL.15 | `opposing_partner_plane_symmetry_score` | **[NEW]** | Combined az/incl/y symmetry score. |
| REL.16 | `opposing_partner_ridge_midpoint_height_m` | **[NEW]** | Intersection-line midpoint Y. |
| REL.17 | `opposing_partner_ridge_azimuth_deg` | **[NEW]** | Intersection-line azimuth. |
| REL.18 | `opposing_partner_coplanar_ridge_flag` | **[NEW]** | Predicted ridge line lies inside both polygons. |
| REL.19 | `opposing_partner_ridge_parallel_to_footprint_principal_flag` | **[NEW]** | Gable diagnostic. |

### D.2 Segment-to-cluster (already 156 live features)

Gap:

| # | Feature | Status | Rationale |
|---|---|---|---|
| REL.20 | `member_fraction_in_same_story_as_seg_slab` | **[NEW]** | Members from other stories = cross-story artifact. |
| REL.21 | `member_fraction_rain_hit` | **[NEW]** | Fraction of members with `rain_exposure_ratio > 0.5`. |
| REL.22 | `member_count_survived_clip_ge_50pct` | **[NEW]** | Stronger fit signal than mean. |

### D.3 Segment-to-part

| # | Feature | Status | Rationale |
|---|---|---|---|
| REL.23 | `part_slanted_roof_count_incl_this_seg` | **[NEW]** | Used with GAB.1. |
| REL.24 | `part_slanted_roof_total_area_incl_this_seg` | **[NEW]** | Total slanted-roof area share of this seg. |
| REL.25 | `seg_area_fraction_of_part_roofing_total` | **[NEW]** | Small segments are more rejectable. |
| REL.26 | `seg_ranks_nth_by_area_in_part` | **[NEW]** | Rank 1/2 ≈ main slopes; rank 5+ ≈ dormer/noise. |
| REL.27 | `part_roof_proposal_to_final_survived_fraction` | **[NEW]** | Noisy parts → lower priors for novel proposals. |

### D.4 Segment-to-building

| # | Feature | Status | Rationale |
|---|---|---|---|
| REL.28 | `seg_area_fraction_of_building_roofing_total` | **[NEW]** | — |
| REL.29 | `seg_ranks_nth_by_area_in_building` | **[NEW]** | — |
| REL.30 | `building_has_similar_accepted_plane_count` | **[NEW]** | Count of accepted planes with az±10° AND incl±5° AND d±0.3. If ≥1, this seg is a duplicate. |
| REL.31 | `building_has_similar_rejected_plane_count` | **[NEW]** | Peer-priors for reject. |

---

## Part E — Coverage-coherence / global-consistency features

### E.0 Why this section exists

A gable with only one accepted slope doesn't cover the part — there should be a partner. A hip roof with only 3 accepted planes missed one. A building with 0 accepted planes is suspicious. These are *coherence* constraints that no single segment can satisfy alone, but each segment can be scored by how much it *contributes to* or *violates* coherence.

### E.1 Part-level coverage

| # | Feature | Status | Rationale |
|---|---|---|---|
| COV.1 | `part_footprint_coverage_union_fraction` | **[NEW]** | Union-of-all-slanted-roof XZ / part_footprint_xz. |
| COV.2 | `part_footprint_coverage_if_this_accepted` | **[NEW]** | Coverage conditional on accepting this seg. |
| COV.3 | `part_footprint_coverage_gain_from_this_seg` | **[NEW]** | `.2 − (COV.1 without this seg)`. Positive lift = this seg fills a gap. |
| COV.4 | `part_roof_pair_symmetric_coverage_flag` | **[NEW]** | Both legs of gable pair cover within 0.1 area ratio. |
| COV.5 | `part_uncovered_region_fraction` | **[V2 GE.7]** | — |
| COV.6 | `seg_in_uncovered_region_fraction` | **[V2 GE.8]** | — |
| COV.7 | `part_overlap_double_cover_fraction` | **[NEW]** | Over-covered area (multiple planes on same XZ). |
| COV.8 | `seg_in_double_cover_fraction` | **[NEW]** | This seg's XZ that overlaps another seg. |

### E.2 Building-level coverage

| # | Feature | Status | Rationale |
|---|---|---|---|
| COV.9 | `building_footprint_coverage_union_fraction` | **[NEW]** | Global roof coverage. |
| COV.10 | `building_footprint_coverage_gain_from_this_seg` | **[NEW]** | — |
| COV.11 | `building_over_coverage_fraction` | **[NEW]** | — |
| COV.12 | `building_roof_symmetry_score` | **[NEW]** | Measure left-right / front-back symmetry of accepted planes. |

### E.3 Mass-balance / drainage coherence

| # | Feature | Status | Rationale |
|---|---|---|---|
| COV.13 | `building_drainage_outlet_count` | **[NEW]** | # of distinct drainage directions. |
| COV.14 | `building_drainage_outlet_azimuth_spread_deg` | **[NEW]** | Spread. |
| COV.15 | `seg_drainage_joins_major_outlet_flag` | **[NEW]** | Drainage vector aligns with a dominant outlet. |
| COV.16 | `part_has_orphan_drainage_direction_flag` | **[NEW]** | Drainage vector points into another part or a wall. |
| COV.17 | `building_rainfall_mass_balance_score` | **[NEW]** | Total roof area × cos(incl) balanced over outlets. |

### E.4 Height coherence

| # | Feature | Status | Rationale |
|---|---|---|---|
| COV.18 | `building_ridge_heights_consistent_flag` | **[NEW]** | Std of ridge heights < 0.3 m. |
| COV.19 | `building_eave_heights_consistent_flag` | **[NEW]** | Std of eave heights < 0.2 m. |
| COV.20 | `seg_ridge_height_vs_building_median_diff_m` | **[NEW]** | How anomalous is this seg's ridge? |
| COV.21 | `seg_eave_height_vs_building_median_diff_m` | **[NEW]** | — |

---

## Part F — Counter-evidence / adversarial-prior features

### F.0 Why this section exists

We've enumerated features that *support* a proposal. Humans also reject proposals based on *what shouldn't be there*. Rules like "roof above another roof is bogus" or "plane floats in air without wall support" need dedicated counter-evidence features.

### F.1 Physical impossibility

| # | Feature | Status | Rationale |
|---|---|---|---|
| ADV.1 | `seg_above_another_accepted_roof_flag` | **[NEW]** | XZ-overlap with accepted roof AND `y_min_self > y_max_accepted + 0.5`. |
| ADV.2 | `seg_below_another_accepted_roof_flag` | **[NEW]** | Mirror. |
| ADV.3 | `seg_under_open_sky_only_flag` | **[NEW]** | No surface above seg in building bbox. Normal for real roofs. |
| ADV.4 | `seg_under_existing_ceiling_flag` | **[NEW]** | FlatCeiling above seg within 0.5 m (mid-story noise). |
| ADV.5 | `seg_intersects_floor_plane_flag` | **[NEW]** | Plane cuts through a slab. |
| ADV.6 | `seg_y_min_below_lowest_story_flag` | **[NEW]** | Seg dips below ground. |
| ADV.7 | `seg_y_max_above_highest_wall_top_by_margin_m` | **[NEW]** | How much does seg poke above walls? (Some overhang OK, large not.) |

### F.2 Scan-artifact signatures

| # | Feature | Status | Rationale |
|---|---|---|---|
| ADV.8 | `seg_is_sub_noise_ribbon_flag` | **[V2 rule 3]** | Thin, small, sub-noise. |
| ADV.9 | `seg_is_jagged_polygon_flag` | **[V2 rule 6]** | High isoperimetric deficit + convex-hull ratio < 0.7. |
| ADV.10 | `seg_azimuth_is_grid_snap_flag` | **[NEW]** | Azimuth within 2° of 0/90/180/270°. Some RoomPlan outputs snap. |
| ADV.11 | `seg_plane_residual_max_exceeds_noise_flag` | **[NEW]** | Worst vertex > 3× scan noise. |
| ADV.12 | `seg_member_normals_disagree_flag` | **[NEW]** | `normals_spherical_variance > 0.3`. |

### F.3 Ontology disagreement

| # | Feature | Status | Rationale |
|---|---|---|---|
| ADV.13 | `seg_vs_ontology_part_disagrees_flag` | **[NEW]** | Seg XZ centroid is in a different part than its claimed part. |
| ADV.14 | `seg_vs_coverage_graph_assigned_part_disagrees_flag` | **[NEW]** | — |
| ADV.15 | `seg_vs_roof_family_guess_inconsistent_flag` | **[NEW]** | Part guessed "flat" but seg is a 45° plane. |

### F.4 Duplication

| # | Feature | Status | Rationale |
|---|---|---|---|
| ADV.16 | `seg_duplicates_another_proposal_flag` | **[V2 rule 8]** | |
| ADV.17 | `seg_duplicates_another_accepted_plane_flag` | **[NEW]** | — |
| ADV.18 | `seg_is_subset_of_larger_proposal_flag` | **[NEW]** | This seg's XZ is ≥ 80 % inside another seg. |
| ADV.19 | `seg_is_superset_of_smaller_proposal_flag` | **[NEW]** | Another seg is ≥ 80 % inside this. |

### F.5 Cross-story spill

| # | Feature | Status | Rationale |
|---|---|---|---|
| ADV.20 | `member_max_abs_story_delta` | **[LIVE]** `member_story_delta_max` | — |
| ADV.21 | `member_any_cross_story_flag` | **[NEW]** | `member_story_delta_max > 0`. |
| ADV.22 | `cluster_fraction_cross_story` | **[NEW]** | Fraction of members with story_delta > 0. **From archetype-cluster analysis: this was the top reject-correlated signal in clusters 4+16 (2519 proposals, 6-7 % accept).** |

### F.6 Heuristic-human split

| # | Feature | Status | Rationale |
|---|---|---|---|
| ADV.23 | `heuristic_disagrees_with_user` | **[LIVE]** | — |
| ADV.24 | `heuristic_acceptance_probability_on_similar_segs` | **[NEW]** | Prior from parquet. |
| ADV.25 | `similar_seg_acceptance_probability_on_same_building` | **[NEW]** | K-nearest in feature space within building. |

---

## Part G — Per-geometric-primitive exhaustive enumeration

### G.0 Edges (recap + deeper)

Already covered in B.2. Additional angular / topological edge features:

| # | Feature | Status | Rationale |
|---|---|---|---|
| EDX.1 | `edge_dihedral_mean_with_opposing_deg` | **[NEW]** | Avg dihedral to opposing seg along shared edge. |
| EDX.2 | `edge_has_matching_opposing_edge_fraction` | **[NEW]** | Fraction of edge length that's shared with another seg's edge. |
| EDX.3 | `edge_has_matching_wall_top_fraction` | **[NEW]** | Fraction along a wall top. |
| EDX.4 | `edge_has_matching_floor_slab_fraction` | **[NEW]** | Fraction along a floor slab edge. |
| EDX.5 | `edge_unmatched_fraction` | **[NEW]** | `1 − EDX.2 − EDX.3 − EDX.4` — orphan boundary. |
| EDX.6 | `edge_under_sky_open_fraction` | **[NEW]** | Edges with no building feature within 0.5 m — eaves. |

### G.1 Vertices (recap + deeper)

Already covered in B.1. Additional:

| # | Feature | Status | Rationale |
|---|---|---|---|
| VTX.16 | `vertex_matches_roof_cell_complex_node_count` | **[NEW]** | Count of seg vertices within ε of a cell-complex vertex. |
| VTX.17 | `vertex_on_footprint_outer_boundary_count` | **[NEW]** | Vertices on the exterior edge of the building footprint. |
| VTX.18 | `vertex_is_ridge_endpoint_flag_max` | **[NEW]** | Does y_max vertex coincide with a ridge endpoint? |

### G.2 Face features (recap + extensions in B.3)

### G.3 Rings / holes / interior cavities

| # | Feature | Status | Rationale |
|---|---|---|---|
| RNG.1 | `face_interior_ring_count` | **[NEW]** | Shapely interior rings. |
| RNG.2 | `face_interior_ring_max_area_m2` | **[NEW]** | Largest hole. |
| RNG.3 | `face_interior_ring_on_dormer_locus_flag` | **[NEW]** | Is the hole at a dormer? |

---

## Part H — Physics / drainage / structural feasibility

### H.0 Covered in v2 §11. Additional:

| # | Feature | Status | Rationale |
|---|---|---|---|
| PHY.1 | `drainage_path_length_to_eave_m` | **[NEW]** | Max XZ distance on segment from a point to an eave. Proxy for water-travel before leaving roof. |
| PHY.2 | `drainage_path_length_to_ridge_m` | **[NEW]** | Max distance to ridge edge. |
| PHY.3 | `snow_load_accumulation_proxy` | **[NEW]** | `area × snow_coeff(incl)` per Eurocode EN 1991-1-3. |
| PHY.4 | `wind_uplift_exposure_proxy` | **[NEW]** | `area × cos(incl)^2 × building_height_factor`. |
| PHY.5 | `self_weight_load_proxy` | **[NEW]** | `area × material_weight_kg_per_m2`. |
| PHY.6 | `seg_has_gutter_compatible_eave_flag` | **[NEW]** | Eave length × incl ≥ thresholds for gutters. |
| PHY.7 | `eave_overhang_m_estimated` | **[NEW]** | Distance from eave to nearest wall top below. |
| PHY.8 | `eave_overhang_exceeds_convention_flag` | **[V2 DR.7 + SG.6]** | `> 0.6 m`. |
| PHY.9 | `truss_span_implied_m` | **[V2 STR.1]** | Bbox major axis. |
| PHY.10 | `truss_span_exceeds_residential_flag` | **[V2 STR.2]** | — |
| PHY.11 | `has_bearing_wall_under_ridge_flag` | **[NEW]** | Wall with top_y ≈ ridge_y under the ridge midpoint. |
| PHY.12 | `structural_coherence_score` | **[NEW]** | Aggregate: eave-on-wall + bearing-wall-under-ridge + pitch-in-duopitch-window. |

---

## Part I — Cross-modal agreement features

### I.0 Why this section exists

We have multiple signal sources (V1 legacy, V3 segments, V3 merged segments, ontology parts, BBR, scan classification). They should agree. Disagreements are strong signals.

### I.1 V1 ↔ V3 agreement

| # | Feature | Status | Rationale |
|---|---|---|---|
| XM.1 | `v1_oblique_surface_overlap_area_m2` | **[NEW]** | XZ overlap with any V1 oblique. |
| XM.2 | `v1_oblique_normal_cos_max` | **[NEW]** | Best cosine similarity to V1 oblique normals. |
| XM.3 | `v1_oblique_pitch_diff_min_deg` | **[NEW]** | — |
| XM.4 | `v1_accepted_and_v3_accepts_agreement_flag` | **[NEW]** | Both pipelines agree. |
| XM.5 | `v1_rejected_but_v3_proposes_flag` | **[NEW]** | — |

### I.2 V3 ↔ ontology agreement

| # | Feature | Status | Rationale |
|---|---|---|---|
| XM.6 | `ontology_says_gable_and_seg_matches_gable_leg_flag` | **[NEW]** | — |
| XM.7 | `ontology_says_hip_and_seg_matches_hip_plane_flag` | **[NEW]** | — |
| XM.8 | `ontology_says_flat_but_seg_is_steep_flag` | **[NEW]** | Strong reject. |

### I.3 Scan-classification ↔ proposer agreement

| # | Feature | Status | Rationale |
|---|---|---|---|
| XM.9 | `scan_class_red_and_seg_is_thin_flag` | **[NEW]** | Red = noisy, thin seg → reject. |
| XM.10 | `scan_class_green_and_seg_is_atypical_flag` | **[NEW]** | Green + atypical = genuine odd feature. |

### I.4 BBR ↔ geometry agreement

| # | Feature | Status | Rationale |
|---|---|---|---|
| XM.11 | `bbr_tagtype_flat_and_seg_is_steep_flag` | **[OUT-OF-SCOPE]** | — |
| XM.12 | `bbr_tagtype_gable_and_no_gable_detected_flag` | **[OUT-OF-SCOPE]** | — |
| XM.13 | `bbr_anvendelse_residential_and_seg_in_duopitch_window_flag` | **[OUT-OF-SCOPE]** | — |

### I.5 Viewer-edit ↔ proposer agreement

| # | Feature | Status | Rationale |
|---|---|---|---|
| XM.14 | `any_user_split_event_in_building_flag` | **[V2 SPL.5]** | — |
| XM.15 | `any_user_merge_event_in_cluster_flag` | **[NEW]** | If we log merges. |
| XM.16 | `seg_is_descendant_of_user_edit_flag` | **[V2 SPL.4]** | `split_depth > 0`. |

---

## Part J — Architecture-typology prior features

### J.0 Why this section exists

DK buildings cluster into well-known typologies. Knowing the typology shifts the prior.

| # | Feature | Status | Rationale |
|---|---|---|---|
| TYP.10 | `is_detached_house_prior` | **[OUT-OF-SCOPE requires BBR]** | — |
| TYP.11 | `is_longhouse_prior` | **[NEW]** | From BLD.10 + story count ≤ 2. |
| TYP.12 | `is_rowhouse_prior` | **[OUT-OF-SCOPE]** | — |
| TYP.13 | `is_bungalow_prior` | **[NEW]** | 1 story + hip + compact footprint. |
| TYP.14 | `is_villa_prior` | **[NEW]** | 1.5-2 stories + gable + knee-wall attic. |
| TYP.15 | `is_garage_outbuilding_prior` | **[NEW]** | Footprint < 50 m² + 1 story + gable or shed. |
| TYP.16 | `typology_prior_accept_rate_for_gable_leg` | **[NEW]** | Typology-conditional prior. |
| TYP.17 | `typology_prior_accept_rate_for_dormer` | **[NEW]** | — |
| TYP.18 | `typology_prior_accept_rate_for_shed_extension` | **[NEW]** | — |

---

## Part K — Label-behavior / user-pattern features

Covered in v2 §6-8 (SPL, SIB, LBL). Additional:

| # | Feature | Status | Rationale |
|---|---|---|---|
| LBL.12 | `label_distribution_accept_rate_this_cluster_canonical` | **[NEW]** | — |
| LBL.13 | `label_distribution_accept_rate_this_part_index` | **[NEW]** | — |
| LBL.14 | `label_distribution_accept_rate_this_pitch_band` | **[NEW]** | — |
| LBL.15 | `label_distribution_accept_rate_this_building` | **[NEW]** | — |
| LBL.16 | `label_distribution_accept_rate_this_labeler_x_pitch_band` | **[NEW]** | Labeler × pitch interaction. |
| LBL.17 | `label_latency_mean_for_similar_segs_s` | **[NEW]** | Humans hesitate on ambiguous ones. |
| LBL.18 | `skip_rate_for_similar_segs` | **[NEW]** | — |

---

## Part L — Temporal / versioning features

| # | Feature | Status | Rationale |
|---|---|---|---|
| TMP.1 | `days_since_scan_captured` | **[OUT-OF-SCOPE]** unless builder persists | Scan age. |
| TMP.2 | `days_since_building_last_rescanned` | **[OUT-OF-SCOPE]** | — |
| TMP.3 | `v3_pipeline_version_sha` | **[NEW]** | Pipeline version at scoring. |
| TMP.4 | `feature_expansion_version_sha` | **[NEW]** | — |
| TMP.5 | `model_hash_at_score_time` | **[NEW]** | — |
| TMP.6 | `days_since_v3_results_regenerated` | **[NEW]** | — |

---

## Part M — Scale-invariant / dimensionless derivations

Many raw features carry units; classifiers generalise better on dimensionless ratios. Below: derivations to add.

| # | Feature | Status | Derivation | Rationale |
|---|---|---|---|---|
| DIM.1 | `poly_area_over_building_footprint` | **[NEW]** | `poly_area_xz_m2 / bld_footprint_area_m2` | — |
| DIM.2 | `poly_area_over_part_footprint` | **[NEW]** | `poly_area_xz_m2 / part_footprint_area_m2` | — |
| DIM.3 | `edge_longest_over_poly_perimeter` | **[NEW]** | `edge_longest_m / poly_perimeter_xz_m` | — |
| DIM.4 | `y_range_over_major_m` | **[NEW]** | `y_range_m / poly_min_rect_major_m` | Pitch-shape proxy. |
| DIM.5 | `eave_edge_length_over_perimeter` | **[NEW]** | — | |
| DIM.6 | `ridge_edge_length_over_perimeter` | **[NEW]** | — | |
| DIM.7 | `ridge_length_over_eave_length` | **[NEW]** | — | |
| DIM.8 | `height_above_slab_over_building_height` | **[NEW]** | — | |
| DIM.9 | `plane_d_over_building_height` | **[NEW]** | — | |
| DIM.10 | `major_axis_over_building_major_axis` | **[NEW]** | — | |
| DIM.11 | `opposing_partner_area_over_self_area` | **[NEW]** | — | |
| DIM.12 | `cluster_pre_clip_area_over_post_clip_area` | **[LIVE]** `cluster_clip_ratio` inverse | — |
| DIM.13 | `drainage_distance_to_outlet_over_major_axis` | **[NEW]** | — | |
| DIM.14 | `vertex_count_over_edge_count` | **[NEW]** | = 1 for simple polygon; other values diagnostic. |
| DIM.15 | `area_over_3d_bbox_major_x_minor` | **[NEW]** | Fill-factor. |

---

## Part N — Prioritized ingest order

Grouped by `(expected_lift × inverse_effort)`. **Live features already counted.**

### N.1 Tier A: 1-day wins that directly address user's concern

Regional/global missing signals — highest leverage:

1. **ONT.1** `part_roof_family_guess_enum_6` (one-hot) — single biggest missing signal; already computed, just surface.
2. **ONT.3** `segment_matches_guess_flag` — direct typology-consistency check.
3. **GAB.12** `gable_is_this_segment_one_of_the_two_legs` — explicit gable-leg check using live `part_gable_metric_az0/1`.
4. **GAB.13, GAB.14** gable-pair area/eave symmetry.
5. **COV.3** `part_footprint_coverage_gain_from_this_seg` — answers "does this seg fill a gap?"
6. **ADV.22** `cluster_fraction_cross_story` — strongest correlated reject signal from archetype analysis (2519 proposals, 6-7 % accept).
7. **ADV.17, ADV.18, ADV.19** duplication detection against accepted planes.
8. **PLN.8** `plane_azimuth_from_building_principal_axis_deg` — v1 A.37, literature-rooted.
9. **HIP.1, HIP.2, HIP.3** hip-detection for parts (generalizes beyond gable).
10. **SHED.2** orphan-oblique flag.

### N.2 Tier B: 2-3 day wins

11. **ONT.6-ONT.11** roof_cell_complex per-seg projections — requires a per-seg XZ overlay with the cell complex.
12. **ONT.12-ONT.17** coverage_graph evidence tier — v1 M.1-.6.
13. **REL.1-REL.10** segment-to-segment pairing features (nearest peer in part).
14. **REL.12-REL.19** opposing-pair quality features.
15. **MAN.1-MAN.7** mansard detection (4-family branch).
16. **EDG.5-EDG.11** edge-type classification (ridge / hip / valley / eave / rake).
17. **VTX.3-VTX.15** additional vertex descriptors.
18. **PHY.6-PHY.12** structural feasibility features.
19. **COV.1-COV.12** coverage-coherence features.
20. **I.4 EIG.1-.11 (×2 point sets)** — 22 Hackel eigenvalue features for free.

### N.3 Tier C: 1-week implementations

21. **ONT.18-ONT.30** evidence_graph, top_boundary_graph, hypothesis_graph — require graph scaffolding.
22. **XM.1-XM.5** V1↔V3 agreement — requires V1 result ingestion alongside V3.
23. **XM.6-XM.8** ontology↔V3 agreement.
24. **TV2.*** topology-V2 graph features (v2 Part 5).
25. **SIB.1-SIB.14** cross-proposal sibling features (v2 Part 7).

### N.4 Tier D: external-data blockers

26. **BBR-keyed** features (ONT sections that need cadastre).
27. **Site-scale** features (neighbors, plot).
28. **Orthophoto** agreement.

---

## Part O — Explicit V2 deltas (what V2 missed)

V2 was comprehensive on cross-domain signals but under-emphasized:

1. **Typology-aware features.** V2 enumerated roof typologies only implicitly (SG.2 orphan oblique). V3 gives each typology its own geometric signature + feature set (Part A).
2. **Ontology-as-feature-source.** V2 mentioned `part_gable_*` but missed `roof_family_guess`, `roof_cell_complex`, `roof_coverage_graph`, `roof_evidence_graph`, `top_boundary_graph`, `roof_hypothesis_graph` as per-segment feature sources (Part C).
3. **Coverage-coherence.** V2 had `iou_*`/`cover_of_*` (segment-to-existing); missing was "does this seg *improve* part-level coverage", "is the part over/under-covered", "mass-balance drainage" (Part E).
4. **Counter-evidence.** V2 had a single rule-list (§12), but no feature family for physical-impossibility signals that a model can weight continuously (Part F).
5. **Scale-strict organization.** V2 mixed scales; V3 Part B gives a clean 9-scale inventory that reveals site + typology scales are entirely absent today.
6. **Relational features.** V2 covered siblings; V3 adds per-part peer pairs (REL.1-REL.10), opposing-pair quality (REL.12-REL.19), and segment-rank-in-building (REL.28-REL.31).
7. **Scale-invariant derivations.** V2 did not enumerate dimensionless ratios (Part M) — 15 quick wins.
8. **Gable-specific discriminators.** The user asked "what distinguishes a gable from not-gable"; V2 answered implicitly via shape-grammar rules. V3 Part A.1 gives the 16-feature signature explicitly.

---

## Bibliography

All references in v1 + v2 bibliographies remain. Additional domain references:

- **DK longhouse typology** — Lenschow & Pihlmann, *House on Fanø* (2020). Fuels TYP.11.
- **DK bygningsreglementet BR18** — roof-ridge and daylight envelope rules (BC.3, BC.4).
- **BBR data model** (Bygnings- og Boligregistret) — attribute schema (tagtype, anvendelse, opfoerelsesaar). Blocked on integration today; referenced in TYP.*.
- **Apple RoomPlan parametric model** — `https://machinelearning.apple.com/research/roomplan`. Fuels scan-quality + grid-snap signals (ADV.10, VTX.13).

### Repo references (new vs. v2)

- `reconcile/roof_algorithms_py/roof_cell_complex.py` — surface for ONT.6-.11.
- `reconcile/roof_algorithms_py/top_boundary_graph.py` — surface for ONT.23-.27.
- `reconcile/roof_algorithms_py/roof_coverage_graph.py` — surface for ONT.12-.17.
- `reconcile/roof_algorithms_py/roof_evidence_graph.py` — surface for ONT.18-.22.
- `reconcile/roof_algorithms_py/roof_building_parts.py` — surface for ONT.1-.5.
- `reconcile/roof_algorithms_py/roof_hypothesis_graph.py` — surface for ONT.28-.30.
- `reconcile/roof_algorithms_py/dormer_detection.py` — surface for ONT.31-.33.
- `reconcile/roof_algorithms_py/simple_slant.py` — surface for ONT.34.
- `reconcile/roof_algorithms_py/thermal_ceiling.py` — surface for ONT.35-.36.
- `reconcile_v3/stages/gable_extension.py` — `az0`, `az1`, `incl0`, `incl1`, `ridge_line`, `uncovered_region_xz` (several still not surfaced; GE.1-.13 in v2, GAB.12-.14 in v3).

---

## Methodology appendix

### A.1 Pipeline

- **Typology enumeration:** architectural roof-type signatures distilled from `gable_extension.py` thresholds, DK BBR tagtype schema, and shape-grammar literature (Flemming, Stiny-Gips, Müller CGA) with each mapped to concrete feature conjunctions.
- **Ontology surface audit:** enumerated modules in `reconcile/roof_algorithms_py/` and scored which outputs are currently consumed by `context_features.py` vs. unused.
- **Coverage-coherence derivation:** applied per-part and per-building union-coverage reasoning; augmented with gable-pair-symmetric-coverage, drainage-outlet balance.
- **Relational feature derivation:** enumerated seg-to-seg, seg-to-cluster, seg-to-part, seg-to-building pairs systematically; deduplicated against v2's sibling features.
- **Counter-evidence derivation:** inverted the "this seg fits" reasoning into "this seg conflicts with..." at each scale.

### A.2 Completeness check

Per user ask ("exhaustive enumeration"), V3 covers:
- Every geometric primitive scale (vertex → typology, 9 scales).
- Every ontological artefact (7 modules in `roof_algorithms_py`).
- Every roof typology in DK residential stock (gable, hip, mansard, shed, flat, half-hip, hipped-gable, pyramid, L/T/U composite, gambrel, tower).
- Every relational dimension (to peer seg, peer cluster, peer part, peer building).
- Every cross-modal check (V1 ↔ V3 ↔ ontology ↔ BBR ↔ viewer-edit).
- Every physics / structural / thermal / solar / drainage cross-domain signal.
- Every scale-invariant / dimensionless derivation.
- Every labeling-behaviour / user-pattern axis.
- Every temporal / versioning axis.

Gaps explicitly flagged `[OUT-OF-SCOPE]`: BBR cadastre join, site-neighbors, orthophoto, point-cloud. Each requires an upstream data source that is not yet ingested.

### A.3 Counts by family

| Family (V3 new + extensions) | Count |
|---|---:|
| Part A typology signatures (11 types) | ~90 features |
| Part B scale inventory (9 scales, vertex→typology) | ~115 features |
| Part C ontology surfaces (7 modules) | ~36 features |
| Part D relational (seg-seg, seg-part, seg-bld) | ~31 features |
| Part E coverage-coherence | ~21 features |
| Part F counter-evidence | ~25 features |
| Part G per-primitive extensions | ~12 features |
| Part H physics extensions | ~12 features |
| Part I cross-modal agreement | ~16 features |
| Part J typology priors | ~9 features |
| Part K label-behavior extensions | ~7 features |
| Part L temporal | ~6 features |
| Part M scale-invariant | ~15 features |
| **Total novel features in V3** | **~395** |

Plus v2's 396 live + ~250 v2-planned = **~1,040 total enumerated features** across v1 + v2 + v3, of which ~396 are live today.

### A.4 What to do with this document

1. **Pick Tier A (Part N.1)** for the next implementation pass. 10 features, ~1 day, directly answers the user's "global/regional" concern.
2. **Before implementing Tier B+**, re-run the feature ranker and the classifier to see if Tier A already shifts the top-30. If yes, Tier B is less urgent; if no, proceed with Tier B.
3. **Do not implement all 395.** Many are redundant (e.g., typology-specific diagnostics overlap across types). Use correlation clustering (v2 §13.1) to prune after implementation.
4. **BBR integration** (blocking Tier D) should be proposed as a separate initiative; it unlocks ~25 % of the proposed feature surface.

---

**End of V3 catalogue.**

Cross-references:
- V1: `reports/slanted_roof_feature_catalogue.md` (1,099 lines, ~600 planned features).
- V2: `reports/slanted_roof_feature_catalogue_v2.md` (763 lines, 396 live + 7 extension families).
- Plan: `/Users/martincollignon/.claude/plans/system-instruction-you-are-working-melodic-octopus.md`.
- Ranking: `artifacts/feature_ranking.csv`.
- Archetype clusters: `reports/archetype_clusters.md`.
