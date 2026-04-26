# Archetype clusters — V3 merged roof segments

KMEANS on a StandardScaled + PCA-reduced feature matrix. Clusters are sorted by human accept rate — the lowest-accept clusters at the top are the strongest candidates for a classifier auto-reject rule or a systematic proposer bug; the highest-accept clusters at the bottom are candidate auto-accepts.

**Population.** 11847 proposals · 20 clusters · 0 noise points · grand accept rate 22.5%.

## At a glance

| cluster | size | labeled | accept | heuristic | top feature |
|---|---|---|---|---|---|
| 14 | 81 | 81 | 0.0% | 100.0% | `member_plane_azimuth_spread_deg` (+11.2σ) |
| 16 | 1014 | 1014 | 2.4% | 75.3% | `member_story_delta_max` (+0.9σ) |
| 4 | 1505 | 1505 | 6.4% | 74.7% | `member_story_delta_max` (+0.8σ) |
| 9 | 1141 | 1141 | 7.4% | 55.5% | `opposing_count` (+2.1σ) |
| 7 | 375 | 375 | 9.6% | 100.0% | `bld_footprint_bbox_aspect` (+3.6σ) |
| 15 | 346 | 346 | 12.4% | 100.0% | `part_gable_metric_n_arch_flats` (+2.0σ) |
| 19 | 245 | 245 | 12.7% | 92.9% | `poly_convex_hull_area_m2` (+4.0σ) |
| 3 | 155 | 155 | 16.8% | 42.1% | `member_piece_area_m2_mean` (+5.8σ) |
| 13 | 162 | 162 | 17.9% | 76.8% | `member_slab_vertex_count_mean` (+4.0σ) |
| 17 | 204 | 204 | 18.1% | 100.0% | `bld_footprint_bbox_aspect` (+3.6σ) |
| 6 | 1034 | 1034 | 18.4% | 98.5% | `bld_height_m` (-1.6σ) |
| 1 | 608 | 608 | 23.5% | 100.0% | `dormer_count_in_building` (+1.7σ) |
| 5 | 337 | 337 | 26.7% | 100.0% | `part_gable_metric_major_m` (+4.3σ) |
| 2 | 464 | 464 | 29.1% | 88.0% | `member_piece_compactness_min` (+2.6σ) |
| 10 | 829 | 829 | 30.2% | 100.0% | `member_segment_mid_y_m_min` (+1.9σ) |
| 12 | 477 | 477 | 30.6% | 74.4% | `member_unique_source_walls` (+1.9σ) |
| 18 | 222 | 222 | 31.1% | 87.8% | `swall_stories_touched` (+5.5σ) |
| 11 | 1502 | 1502 | 46.0% | 98.3% | `normals_d_entropy` (+0.9σ) |
| 0 | 251 | 251 | 46.2% | 100.0% | `swall_length_total` (+3.6σ) |
| 8 | 895 | 895 | 47.7% | 100.0% | `member_slab_floor_y_m_count` (+1.6σ) |

## Clusters (sorted by accept rate, ascending)

### Cluster 14 — 81 members · accept 0.0% (0/81 labeled) · heuristic 100.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `member_plane_azimuth_spread_deg` | +11.21 | 50 |
| `member_segment_azimuth_deg_std` | +11.05 | 48.6 |
| `member_segment_azimuth_deg_range` | +10.86 | 99.9 |
| `swall_azimuth_std` | +10.58 | 97.9 |
| `swall_azimuth_max_diff_deg` | +10.33 | 79.9 |
| `normals_mean_resultant_length` | -5.52 | 0.99 |
| `normals_spherical_variance` | +5.52 | 0.00966 |
| `normals_pairwise_cos_mean` | -5.45 | 0.98 |

**Exemplars** (paste into the viewer search bar):
- `37e9355f-29a7-4303-abae-240c55df13e4::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-4`
- `37e9355f-29a7-4303-abae-240c55df13e4::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-36`
- `a317a543-06cf-4f1b-97d2-139c26c1cb13::v3-merged-roof-segment::segment-0:gap-cross_story-0-8:piece-0:seg-210`
- `a317a543-06cf-4f1b-97d2-139c26c1cb13::v3-merged-roof-segment::segment-0:gap-cross_story-0-8:piece-0:seg-48`
- `a317a543-06cf-4f1b-97d2-139c26c1cb13::v3-merged-roof-segment::segment-0:gap-cross_story-0-8:piece-0:seg-116`

### Cluster 16 — 1014 members · accept 2.4% (24/1014 labeled) · heuristic 75.3%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `member_story_delta_max` | +0.95 | 0.873 |
| `normals_d_entropy` | -0.84 | 0.077 |
| `hu_log_1` | +0.83 | -1.43 |
| `hu_log_4` | -0.83 | 3.91 |
| `hu_log_3` | -0.82 | 3.84 |
| `hu_log_2` | -0.82 | 2.81 |
| `hu_log_6` | +0.82 | -5.3 |
| `hu_log_5` | -0.82 | 7.77 |

**Exemplars** (paste into the viewer search bar):
- `016980bc-6762-4022-bfbf-17df4112e10c::v3-merged-roof-segment::segment-0:room-10:piece-0:seg-0`
- `5ecc6e8c-228b-4167-9331-de247c802320::v3-merged-roof-segment::segment-12:room-0:piece-0:seg-1`
- `3a576e1b-4b3e-4f5d-8c20-b39b157fcf03::v3-merged-roof-segment::segment-11:gap-cross_story-0-2:piece-0:seg-57`
- `873952bc-1159-43dd-b4bd-6535a55c57cf::v3-merged-roof-segment::segment-10:gap-cross_story-0-1:piece-0:seg-19`
- `b8cefbc4-bb4e-4d53-be56-990780166cae::v3-merged-roof-segment::segment-3:gap-cross_story-0-11:piece-0:seg-7`

### Cluster 4 — 1505 members · accept 6.4% (97/1505 labeled) · heuristic 74.7%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `member_story_delta_max` | +0.79 | 0.785 |
| `normals_d_entropy` | -0.79 | 0.0912 |
| `swall_length_max` | -0.77 | 2.36 |
| `member_segment_mid_y_m_max` | -0.77 | -0.525 |
| `swall_top_y_mean` | -0.76 | -0.21 |
| `member_wall_entropy` | -0.75 | 0.26 |
| `member_segment_length_m_max` | -0.74 | 1.2 |
| `bld_footprint_compactness` | +0.74 | 0.502 |

**Exemplars** (paste into the viewer search bar):
- `016980bc-6762-4022-bfbf-17df4112e10c::v3-merged-roof-segment::segment-0:room-10:piece-0:seg-10`
- `0fe789ce-e653-4828-863c-0f6ce7fee21d::v3-merged-roof-segment::segment-10:gap-cross_story-0-3:piece-0:seg-13`
- `720c2f50-9586-47b5-b27c-130214cd8b5d::v3-merged-roof-segment::segment-9:gap-cross_story-0-6:piece-0:seg-82`
- `b65126ae-ccca-4032-876f-e9c1c059862c::v3-merged-roof-segment::segment-14:room-10:piece-0:seg-19`
- `d32d5562-5763-4c71-a816-6732c638fa6a::v3-merged-roof-segment::segment-7:gap-cross_story-0-4:piece-0:seg-33`

### Cluster 9 — 1141 members · accept 7.4% (85/1141 labeled) · heuristic 55.5%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `opposing_count` | +2.08 | 9.62 |
| `opposing_cluster_count` | +2.08 | 9.62 |
| `snapshot_opposing_cluster_count` | +2.08 | 9.62 |
| `bld_window_count` | +1.95 | 31.6 |
| `covered_side_count` | +1.62 | 5.13 |
| `cluster_pre_clip_area_sum_m2` | +1.58 | 219 |
| `bld_footprint_area_m2` | +1.57 | 219 |
| `member_unique_slab_rooms` | +1.54 | 14.8 |

**Exemplars** (paste into the viewer search bar):
- `1900be91-8684-4316-98e2-c4fef6e6296f::v3-merged-roof-segment::segment-14:gap-cross_story-0-8:piece-0:seg-2`
- `d28b528a-475b-4ac0-a38d-ee992cd877db::v3-merged-roof-segment::segment-2:gap-cross_story-0-0:piece-0:seg-448`
- `d28b528a-475b-4ac0-a38d-ee992cd877db::v3-merged-roof-segment::segment-6:gap-cross_story-0-0:piece-0:seg-188`
- `d28b528a-475b-4ac0-a38d-ee992cd877db::v3-merged-roof-segment::segment-24:gap-cross_story-0-0:piece-0:seg-186`
- `e9f0631f-ae34-4d30-af21-d3369327755f::v3-merged-roof-segment::segment-1:gap-cross_story-0-22:piece-0:seg-427`

### Cluster 7 — 375 members · accept 9.6% (36/375 labeled) · heuristic 100.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `bld_footprint_bbox_aspect` | +3.63 | 2.88 |
| `part_footprint_perimeter_m` | +3.33 | 119 |
| `ctx_roof_proposals_count` | +2.99 | 504 |
| `dormer_nearest_distance_m` | +2.93 | 9.34 |
| `bld_footprint_elongation_ratio` | +2.63 | 3 |
| `part_footprint_area_m2` | +2.55 | 228 |
| `bld_footprint_part_count` | +2.35 | 3 |
| `part_gable_metric_n_slanted_roofs` | +2.30 | 5.92 |

**Exemplars** (paste into the viewer search bar):
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-8`
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-3:room-0:piece-0:seg-129`
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-14:room-0:piece-0:seg-45`
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-1:gap-within_story-0-2:piece-0:seg-43`
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-11:gap-within_story-0-2:piece-0:seg-127`

### Cluster 15 — 346 members · accept 12.4% (43/346 labeled) · heuristic 100.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `part_gable_metric_n_arch_flats` | +2.00 | 3.19 |
| `member_plane_y_at_piece_centroid_m_std` | +1.87 | 5.58 |
| `swall_length_min` | +1.85 | 4.85 |
| `member_plane_y_at_piece_centroid_m_range` | +1.83 | 17.4 |
| `y_std_m` | +1.81 | 1.83 |
| `member_plane_height_above_slab_m_std` | +1.81 | 5.77 |
| `y_range_m` | +1.75 | 4.5 |
| `member_slant_delta_over_piece_m_median` | +1.73 | 5.61 |

**Exemplars** (paste into the viewer search bar):
- `0d3f2993-8386-4130-8f1c-b2938c410828::v3-merged-roof-segment::segment-15:room-0:piece-0:seg-0`
- `6203a969-742b-4935-bc4d-8eae644b8f73::v3-merged-roof-segment::segment-1:room-0:piece-0:seg-21`
- `517846b1-d1f1-4faa-8407-e80dcdbcc003::v3-merged-roof-segment::segment-2:gap-cross_story-1-7:piece-0:seg-25`
- `0d3f2993-8386-4130-8f1c-b2938c410828::v3-merged-roof-segment::segment-0:gap-cross_story-0-2:piece-0:seg-6`
- `d8308bfc-c2c1-42bd-8503-282571708b8c::v3-merged-roof-segment::segment-5:room-0:piece-0:seg-6`

### Cluster 19 — 245 members · accept 12.7% (31/245 labeled) · heuristic 92.9%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `poly_convex_hull_area_m2` | +3.99 | 49.4 |
| `snapshot_perimeter_m` | +3.64 | 41.1 |
| `poly_perimeter_xz_m` | +3.61 | 40.3 |
| `turning_angle_abs_sum_deg` | +3.58 | 1.82e+03 |
| `vangle_sum_defect_deg` | -3.58 | -1.1e+03 |
| `sharp_corner_count` | +3.52 | 18.4 |
| `vertex_count` | +3.52 | 19.5 |
| `edge_count` | +3.52 | 19.5 |

**Exemplars** (paste into the viewer search bar):
- `019e1376-9762-42d6-8520-b664b8c752df::v3-merged-roof-segment::segment-10:room-0:piece-0:seg-15`
- `720c2f50-9586-47b5-b27c-130214cd8b5d::v3-merged-roof-segment::segment-0:room-10:piece-0:seg-153`
- `517846b1-d1f1-4faa-8407-e80dcdbcc003::v3-merged-roof-segment::segment-3:gap-cross_story-1-7:piece-0:seg-79`
- `a317a543-06cf-4f1b-97d2-139c26c1cb13::v3-merged-roof-segment::segment-5:gap-cross_story-0-8:piece-0:seg-130`
- `cb711a0b-6e8d-4ae6-b008-af3297446dcc::v3-merged-roof-segment::segment-0:gap-cross_story-1-4:piece-0:seg-48`

### Cluster 3 — 155 members · accept 16.8% (26/155 labeled) · heuristic 42.1%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `member_piece_area_m2_mean` | +5.82 | 67.3 |
| `member_slab_area_m2_mean` | +5.51 | 67.3 |
| `member_piece_area_m2_min` | +5.21 | 18.9 |
| `member_piece_min_width_m_mean` | +5.02 | 3.07 |
| `ctx_part_count` | +4.90 | 2 |
| `member_piece_compactness_range` | -4.78 | 0.0768 |
| `member_slab_area_m2_min` | +4.68 | 18.9 |
| `member_piece_min_width_m_min` | +4.61 | 1.75 |

**Exemplars** (paste into the viewer search bar):
- `7dbc53a6-17e8-4806-83de-42286b95726c::v3-merged-roof-segment::segment-0:room-11:piece-0:seg-0`
- `7dbc53a6-17e8-4806-83de-42286b95726c::v3-merged-roof-segment::segment-1:gap-cross_story-0-3:piece-0:seg-3`
- `7dbc53a6-17e8-4806-83de-42286b95726c::v3-merged-roof-segment::segment-2:gap-cross_story-0-3:piece-0:seg-38`
- `7dbc53a6-17e8-4806-83de-42286b95726c::v3-merged-roof-segment::segment-10:gap-cross_story-0-3:piece-0:seg-11`
- `7dbc53a6-17e8-4806-83de-42286b95726c::v3-merged-roof-segment::segment-6:gap-cross_story-0-3:piece-0:seg-2`

### Cluster 13 — 162 members · accept 17.9% (29/162 labeled) · heuristic 76.8%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `member_slab_vertex_count_mean` | +3.99 | 18.5 |
| `member_piece_bbox_aspect_mean` | +3.89 | 3.86 |
| `member_piece_vertex_count_mean` | +3.73 | 17.7 |
| `member_piece_bbox_aspect_median` | +3.48 | 2.88 |
| `member_piece_bbox_aspect_std` | +3.35 | 2.76 |
| `member_slab_vertex_count_std` | +3.07 | 15.6 |
| `member_piece_vertex_count_std` | +2.93 | 15.4 |
| `member_story_delta_median` | -2.78 | -2.92 |

**Exemplars** (paste into the viewer search bar):
- `52f91e67-3891-4729-8bf3-be2c0a6a0d04::v3-merged-roof-segment::segment-0:gap-cross_story-0-3:piece-0:seg-7`
- `52f91e67-3891-4729-8bf3-be2c0a6a0d04::v3-merged-roof-segment::segment-10:gap-cross_story-0-3:piece-0:seg-0`
- `bad532ea-75de-411a-a390-77f4d6a93ff8::v3-merged-roof-segment::segment-0:gap-cross_story-0-1:piece-0:seg-20`
- `bc2779a4-d0a2-4ba8-abbf-10129d3f82de::v3-merged-roof-segment::segment-1:gap-cross_story-0-5:piece-0:seg-0`
- `bc2779a4-d0a2-4ba8-abbf-10129d3f82de::v3-merged-roof-segment::segment-0:gap-cross_story-0-5:piece-0:seg-32`

### Cluster 17 — 204 members · accept 18.1% (37/204 labeled) · heuristic 100.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `bld_footprint_bbox_aspect` | +3.63 | 2.88 |
| `part_footprint_perimeter_m` | +3.35 | 120 |
| `ctx_roof_proposals_count` | +2.99 | 504 |
| `bld_footprint_elongation_ratio` | +2.63 | 3 |
| `part_footprint_area_m2` | +2.57 | 229 |
| `bld_footprint_part_count` | +2.35 | 3 |
| `part_gable_metric_n_slanted_roofs` | +2.32 | 5.94 |
| `final_roof_union_area_m2` | +2.23 | 32.1 |

**Exemplars** (paste into the viewer search bar):
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-10:room-0:piece-0:seg-5`
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-10:room-0:piece-0:seg-330`
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-20:room-0:piece-0:seg-29`
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-10:gap-within_story-0-2:piece-0:seg-146`
- `8c0ef0cf-51a7-4ac0-8bbf-735f88a799cc::v3-merged-roof-segment::segment-19:gap-within_story-0-2:piece-0:seg-82`

### Cluster 6 — 1034 members · accept 18.4% (190/1034 labeled) · heuristic 98.5%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `bld_height_m` | -1.65 | 3.51 |
| `member_is_top_story_slab_fraction` | +1.61 | 0.928 |
| `member_slab_floor_y_m_std` | -1.54 | 0.144 |
| `member_rain_exposure_ratio_min` | +1.50 | 0.969 |
| `member_rain_exposure_ratio_range` | -1.50 | 0.0311 |
| `member_rain_exposure_ratio_std` | -1.46 | 0.0102 |
| `bld_cross_floor_gap_count` | -1.43 | 6.5 |
| `member_slab_floor_y_m_range` | -1.42 | 0.436 |

**Exemplars** (paste into the viewer search bar):
- `019e1376-9762-42d6-8520-b664b8c752df::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-15`
- `5c557e06-393e-466e-a957-f7391b76b8ff::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-5`
- `893d4535-3169-4907-a93a-b3ab8f66ec1c::v3-merged-roof-segment::segment-6:room-10:piece-0:seg-90`
- `992198d7-4dfe-4ecd-9fa0-b66fa6cac3fd::v3-merged-roof-segment::segment-0:gap-within_story-0-1:piece-0:seg-5`
- `d8308bfc-c2c1-42bd-8503-282571708b8c::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-54`

### Cluster 1 — 608 members · accept 23.5% (143/608 labeled) · heuristic 100.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `dormer_count_in_building` | +1.68 | 1.03 |
| `member_piece_bbox_aspect_max` | +1.34 | 5.81 |
| `member_piece_bbox_aspect_range` | +1.33 | 4.74 |
| `final_slanted_roof_count` | +1.25 | 4.54 |
| `member_piece_compactness_median` | -1.21 | 0.322 |
| `part_gable_metric_n_slanted_roofs` | +1.20 | 4.52 |
| `member_piece_bbox_aspect_std` | +1.19 | 1.3 |
| `member_piece_bbox_aspect_mean` | +1.18 | 2.22 |

**Exemplars** (paste into the viewer search bar):
- `0d3f2993-8386-4130-8f1c-b2938c410828::v3-merged-roof-segment::segment-15:room-0:piece-0:seg-101`
- `16784bad-2cd9-4f4c-bb26-60355981cfe2::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-35`
- `74e87bcd-3989-4d5c-8f16-f7782dc3afbd::v3-merged-roof-segment::segment-2:room-0:piece-0:seg-79`
- `16784bad-2cd9-4f4c-bb26-60355981cfe2::v3-merged-roof-segment::segment-15:gap-cross_story-0-4:piece-0:seg-10`
- `74e87bcd-3989-4d5c-8f16-f7782dc3afbd::v3-merged-roof-segment::segment-2:gap-cross_story-1-13:piece-0:seg-63`

### Cluster 5 — 337 members · accept 26.7% (90/337 labeled) · heuristic 100.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `part_gable_metric_major_m` | +4.29 | 26 |
| `member_slab_area_m2_range` | +4.21 | 205 |
| `member_piece_area_m2_range` | +4.18 | 205 |
| `member_slab_area_m2_max` | +4.16 | 206 |
| `member_piece_area_m2_max` | +4.11 | 206 |
| `part_gable_metric_elong` | +3.98 | 2.48 |
| `member_slab_area_m2_std` | +3.34 | 52.1 |
| `member_piece_area_m2_std` | +3.34 | 51.5 |

**Exemplars** (paste into the viewer search bar):
- `2388d90c-8cc9-4cca-b232-d658e184074d::v3-merged-roof-segment::segment-0:gap-cross_story-1-4:piece-0:seg-0`
- `a317a543-06cf-4f1b-97d2-139c26c1cb13::v3-merged-roof-segment::segment-14:gap-cross_story-0-8:piece-0:seg-225`
- `a317a543-06cf-4f1b-97d2-139c26c1cb13::v3-merged-roof-segment::segment-5:gap-cross_story-0-8:piece-0:seg-89`
- `a317a543-06cf-4f1b-97d2-139c26c1cb13::v3-merged-roof-segment::segment-15:gap-cross_story-0-8:piece-0:seg-198`
- `a317a543-06cf-4f1b-97d2-139c26c1cb13::v3-merged-roof-segment::segment-10:gap-cross_story-0-8:piece-0:seg-3`

### Cluster 2 — 464 members · accept 29.1% (135/464 labeled) · heuristic 88.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `member_piece_compactness_min` | +2.59 | 0.364 |
| `member_is_same_room_fraction` | +2.52 | 0.243 |
| `member_piece_compactness_range` | -2.36 | 0.363 |
| `member_piece_min_width_m_min` | +2.15 | 0.981 |
| `member_piece_perimeter_m_min` | +1.90 | 12.6 |
| `member_piece_area_m2_min` | +1.83 | 7.72 |
| `member_piece_compactness_std` | -1.70 | 0.145 |
| `member_unique_slab_rooms` | -1.68 | 3.18 |

**Exemplars** (paste into the viewer search bar):
- `0b75d30e-c50c-4fc6-88ff-fce983078aa4::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-0`
- `3e378d10-6d7f-451c-b5e8-705731e6f37e::v3-merged-roof-segment::segment-0:room-5:piece-0:seg-56`
- `513a4b03-cfb1-4221-99ff-d9b7d1e1d3f6::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-1`
- `7153d532-16c1-45e8-b7c9-f5cd1ba5cc85::v3-merged-roof-segment::segment-3:room-10:piece-0:seg-104`
- `3e378d10-6d7f-451c-b5e8-705731e6f37e::v3-merged-roof-segment::segment-13:gap-cross_story-1-2:piece-0:seg-122`

### Cluster 10 — 829 members · accept 30.2% (250/829 labeled) · heuristic 100.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `member_segment_mid_y_m_min` | +1.94 | 5.23 |
| `swall_bottom_y_mean` | +1.90 | 3.43 |
| `member_segment_mid_y_m_mean` | +1.89 | 5.31 |
| `member_segment_mid_y_m_median` | +1.89 | 5.31 |
| `swall_top_y_mean` | +1.86 | 5.89 |
| `member_segment_mid_y_m_max` | +1.82 | 5.38 |
| `member_slab_floor_y_m_max` | +1.78 | 3.59 |
| `bld_y_max_m` | +1.72 | 6.13 |

**Exemplars** (paste into the viewer search bar):
- `3a576e1b-4b3e-4f5d-8c20-b39b157fcf03::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-0`
- `59b505e7-b384-451b-90b1-80f2654dd10d::v3-merged-roof-segment::segment-6:room-0:piece-0:seg-146`
- `6c29deb7-51e6-437d-bfe4-0eb83e559881::v3-merged-roof-segment::segment-3:room-0:piece-0:seg-19`
- `59b505e7-b384-451b-90b1-80f2654dd10d::v3-merged-roof-segment::segment-13:gap-cross_story-1-4:piece-0:seg-193`
- `72122129-7ee2-4a14-a645-23d44df3d2b5::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-30`

### Cluster 12 — 477 members · accept 30.6% (146/477 labeled) · heuristic 74.4%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `member_unique_source_walls` | +1.89 | 7.25 |
| `opposing_cos_min` | +1.69 | 0.731 |
| `member_unique_source_rooms` | +1.58 | 3.26 |
| `member_story_delta_count` | +1.42 | 80.3 |
| `member_piece_bbox_aspect_count` | +1.42 | 80.3 |
| `member_segment_azimuth_deg_count` | +1.42 | 80.3 |
| `member_piece_compactness_count` | +1.42 | 80.3 |
| `member_slab_vertex_count_count` | +1.42 | 80.3 |

**Exemplars** (paste into the viewer search bar):
- `019e1376-9762-42d6-8520-b664b8c752df::v3-merged-roof-segment::segment-10:room-0:piece-0:seg-0`
- `7153d532-16c1-45e8-b7c9-f5cd1ba5cc85::v3-merged-roof-segment::segment-10:room-10:piece-0:seg-60`
- `7cabc39b-6328-4a6e-9491-822fa6b3c3fb::v3-merged-roof-segment::segment-12:room-0:piece-0:seg-81`
- `720c2f50-9586-47b5-b27c-130214cd8b5d::v3-merged-roof-segment::segment-0:gap-cross_story-0-6:piece-0:seg-17`
- `73465f84-d5f5-4b84-8509-0e818beb5ecd::v3-merged-roof-segment::segment-0:gap-cross_story-0-7:piece-0:seg-4`

### Cluster 18 — 222 members · accept 31.1% (69/222 labeled) · heuristic 87.8%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `swall_stories_touched` | +5.51 | 2 |
| `member_unique_stories` | +5.51 | 2 |
| `swall_unique_stories` | +5.51 | 2 |
| `swall_bottom_y_std` | +5.34 | 1.15 |
| `swall_top_y_std` | +4.25 | 1.11 |
| `member_segment_mid_y_m_std` | +4.22 | 0.977 |
| `swall_top_y_range` | +3.87 | 2.4 |
| `member_segment_mid_y_m_range` | +3.57 | 2.12 |

**Exemplars** (paste into the viewer search bar):
- `59b505e7-b384-451b-90b1-80f2654dd10d::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-7`
- `287808db-3826-4351-b9a1-6f9831bdc870::v3-merged-roof-segment::segment-0:gap-cross_story-1-3:piece-0:seg-23`
- `59b505e7-b384-451b-90b1-80f2654dd10d::v3-merged-roof-segment::segment-0:gap-cross_story-1-4:piece-0:seg-93`
- `9c42b8bc-b55c-427b-b695-9d073c5f8a75::v3-merged-roof-segment::segment-0:room-0:piece-0:seg-189`
- `bc2779a4-d0a2-4ba8-abbf-10129d3f82de::v3-merged-roof-segment::segment-2:gap-cross_story-0-5:piece-0:seg-13`

### Cluster 11 — 1502 members · accept 46.0% (691/1502 labeled) · heuristic 98.3%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `normals_d_entropy` | +0.90 | 0.539 |
| `bld_footprint_area_m2` | -0.84 | 73.4 |
| `cluster_pre_clip_area_sum_m2` | -0.82 | 71.3 |
| `member_room_entropy` | +0.81 | 0.815 |
| `member_wall_entropy` | +0.76 | 0.988 |
| `member_segment_incl_deg_max` | +0.75 | 47 |
| `bld_footprint_perimeter_m` | -0.73 | 47.3 |
| `bld_wall_count` | -0.71 | 132 |

**Exemplars** (paste into the viewer search bar):
- `016980bc-6762-4022-bfbf-17df4112e10c::v3-merged-roof-segment::segment-3:room-10:piece-0:seg-15`
- `38158927-652c-4d01-9aa3-770956648d85::v3-merged-roof-segment::segment-1:room-0:piece-0:seg-8`
- `21af2a12-2a29-44b5-b703-fbaa208996e9::v3-merged-roof-segment::segment-6:gap-cross_story-0-2:piece-0:seg-0`
- `a443b86f-c86a-47a7-abef-0a56893c99b0::v3-merged-roof-segment::segment-0:gap-cross_story-1-6:piece-0:seg-54`
- `cb711a0b-6e8d-4ae6-b008-af3297446dcc::v3-merged-roof-segment::segment-0:gap-cross_story-1-4:piece-0:seg-58`

### Cluster 0 — 251 members · accept 46.2% (116/251 labeled) · heuristic 100.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `swall_length_total` | +3.65 | 478 |
| `member_segment_azimuth_deg_count` | +3.24 | 138 |
| `swall_resolved_count` | +3.24 | 138 |
| `member_piece_perimeter_m_count` | +3.24 | 138 |
| `member_plane_y_at_piece_centroid_m_count` | +3.24 | 138 |
| `member_piece_compactness_count` | +3.24 | 138 |
| `member_piece_bbox_aspect_count` | +3.24 | 138 |
| `member_plane_height_above_slab_m_count` | +3.24 | 138 |

**Exemplars** (paste into the viewer search bar):
- `1900be91-8684-4316-98e2-c4fef6e6296f::v3-merged-roof-segment::segment-0:gap-cross_story-0-8:piece-0:seg-1`
- `9c42b8bc-b55c-427b-b695-9d073c5f8a75::v3-merged-roof-segment::segment-11:room-0:piece-0:seg-104`
- `d28b528a-475b-4ac0-a38d-ee992cd877db::v3-merged-roof-segment::segment-12:gap-cross_story-0-0:piece-0:seg-251`
- `d28b528a-475b-4ac0-a38d-ee992cd877db::v3-merged-roof-segment::segment-13:gap-cross_story-0-0:piece-0:seg-100`
- `d28b528a-475b-4ac0-a38d-ee992cd877db::v3-merged-roof-segment::segment-13:gap-cross_story-0-0:piece-0:seg-518`

### Cluster 8 — 895 members · accept 47.7% (427/895 labeled) · heuristic 100.0%

**Most distinguishing features** (z vs grand mean, cluster raw mean):

| feature | z | raw mean |
|---|---|---|
| `member_slab_floor_y_m_count` | +1.59 | 85.7 |
| `swall_resolved_count` | +1.59 | 85.7 |
| `member_slant_delta_over_piece_m_count` | +1.59 | 85.7 |
| `member_segment_incl_deg_count` | +1.59 | 85.7 |
| `member_plane_y_at_piece_centroid_m_count` | +1.59 | 85.7 |
| `member_seg_mid_to_piece_centroid_xz_m_count` | +1.59 | 85.7 |
| `member_segment_mid_y_m_count` | +1.59 | 85.7 |
| `member_piece_bbox_aspect_count` | +1.59 | 85.7 |

**Exemplars** (paste into the viewer search bar):
- `0d3f2993-8386-4130-8f1c-b2938c410828::v3-merged-roof-segment::segment-10:room-0:piece-0:seg-101`
- `66a72e63-8b3c-4e57-977b-32f5119a9d09::v3-merged-roof-segment::segment-10:room-0:piece-0:seg-20`
- `466d0aa8-7021-4825-8f7b-b954c824c13a::v3-merged-roof-segment::segment-0:gap-cross_story-0-6:piece-0:seg-39`
- `720c2f50-9586-47b5-b27c-130214cd8b5d::v3-merged-roof-segment::segment-10:gap-cross_story-0-6:piece-0:seg-34`
- `d32d5562-5763-4c71-a816-6732c638fa6a::v3-merged-roof-segment::segment-10:gap-cross_story-0-4:piece-0:seg-9`

## How to use this

1. Scan the top 3–5 clusters (lowest accept rate). If >95 % rejection and size > 100, that's a candidate auto-reject rule — check the distinguishing features first, then verify 3 exemplars in the viewer to name the archetype.
2. Scan the bottom 3–5 clusters (highest accept rate). Same logic in reverse: easy auto-accepts if they hold up under inspection.
3. Any cluster where the heuristic accept rate diverges wildly from the human accept rate is a labeling-quality hotspot — the heuristic is either systematically wrong or systematically right where the human wavered.
