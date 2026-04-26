# Slanted Roof V3 Review Handoff

Date: 2026-04-19

This document is meant to brief a reviewer on the full slanted-roof classification effort at a high level. It explains:

- what the building pipeline is trying to do
- what the slanted-roof problem actually is
- how the current V3 classification workflow works end to end
- what we implemented in this round
- what results we got
- what remains unresolved

It is intentionally broader and more generic than a code changelog.

## 1. What this repo is trying to do

This repository processes RoomPlan-style building scan data into coherent 3D building models.

At a high level, the system tries to reconstruct a real building from imperfect scan sessions. That means taking many pieces of geometric evidence and turning them into a useful, physically plausible representation of:

- rooms
- slabs / floors
- walls and wall extensions
- gaps and cross-story transitions
- ceilings
- slanted roof surfaces
- topology and ontology structures used downstream

The practical goal is not just to draw geometry. It is to turn noisy scan-derived structures into building elements that are useful for later tasks such as review, visualization, modelling, and thermal reasoning.

## 2. What the slanted-roof problem is

The specific problem here is identifying which candidate slanted surfaces are real roof surfaces and which are not.

The important point is that this is no longer mainly a geometry-generation problem. We already have:

- segmentations
- merged roof-segment candidates
- planes
- room/slab/wall context
- ontology/V2/cross-modal context

So the core problem is:

> Given a merged slanted segment and all of its surrounding context, decide whether it is truly a roof surface or an artefact / non-roof segment.

In practice, many false positives come from things like:

- internal staircases
- internal slanted surfaces
- mixed or ambiguous upper-room geometry
- partial-room slants that do not behave like a building roof
- complex shapes such as dormers

That is why the current work has focused on classification rather than reconstruction.

## 3. What success looks like

The desired end state is not just "a model with a good F1 score".

The actual operational goal is autonomy:

- confidently auto-accept obvious true roof segments
- confidently auto-reject obvious false roof segments
- send only the ambiguous remainder to manual review

That means the system needs to do three things well:

1. represent each segment with enough useful context
2. learn a good decision boundary from labels
3. turn model outputs into a practical operating policy with acceptable review volume

This third point matters because a model can improve on offline metrics while still becoming worse operationally if it pushes too many cases into review.

## 4. The current V3 process end to end

The current V3 flow is best understood as a staged pipeline.

### Stage A. Build candidate slanted segments

The geometry pipeline produces candidate slanted roof-like surfaces from scan data and merges related proposals into `merged_roof_segments`.

Each merged segment has:

- geometry
- a representative plane
- member proposals / snapshots
- room and wall references
- building footprint / part context
- ontology and topology traces

This is the raw object we classify.

### Stage B. Join labels

Human review labels are attached to these merged segments. This gives a supervised training set where each row represents one merged segment and the target is essentially:

- roof / accept
- not roof / reject

This turns the task into supervised binary classification over building geometry candidates.

### Stage C. Build a feature matrix

For each labeled merged segment, the analysis pipeline computes a large feature vector. These features are intended to capture:

- the segment’s own geometry
- how it sits relative to the building footprint
- how it relates to walls, slabs, rooms, stories, and parts
- how it relates to other roof candidates
- how ontology and V2 structures interpret it
- cross-modal agreement or disagreement with older pipelines / other signals

This feature matrix is the main information surface the model sees.

### Stage D. Train a model

A gradient-boosted model is then trained on the labeled feature matrix.

The point of this model is not to replace geometry logic. It is to combine many weak and medium-strength geometric/contextual signals into a better overall classifier than any small hand-built rule set can provide.

### Stage E. Extract conservative rules

In addition to the GBM, we extract conservative auto-reject rules from a shallow tree. These rules are not the main classifier. They are a practical autonomy layer that can cheaply reject some obviously bad cases with high purity.

So the deployed scoring logic is hybrid:

- rules for some obvious rejects
- model scores for the rest
- thresholds to map scores into accept / reject / review

### Stage F. Score the full corpus

The full building corpus is run through the scoring pipeline. Each merged roof segment receives:

- a score
- possibly a rule hit
- a final autonomy label

The final autonomy label is one of:

- `auto_accept`
- `auto_reject`
- `review`

That corpus-level output is the real operational result.

## 5. What we believed going into this round

Based on manual review and earlier runs, the current working hypotheses were:

- This is primarily a classification problem, not a missing-geometry problem.
- Staircases are a major source of false positives.
- Staircase artefacts often look more internal than roof surfaces.
- True roof segments often behave more like exterior-facing sloped building shells.
- Dormers matter, but we may get better first-pass autonomy by treating them as a harder second-pass case instead of trying to solve them perfectly up front.
- Small partial-room slants are a recurring difficult case and needed explicit representation.

These hypotheses drove the most recent feature work.

## 6. What we implemented in this round

The work in this round had four main parts.

### A. Expand the feature surface substantially

We added feature families meant to make the classifier more aware of:

- interior vs exterior support
- staircase-like traversal patterns
- room-local slant coverage
- building-level slanted-area context
- dormer-related ambiguity
- ontology mixed-room situations
- how a segment’s plane exits or traverses the building footprint

Examples of added or updated features include:

- `swall_is_interior_count`
- `swall_is_interior_fraction`
- `swall_supports_only_interior`
- `swall_supports_mostly_interior`
- `room_floor_area_total_m2`
- `room_floor_area_mean_m2`
- `seg_room_coverage_fraction_min`
- `seg_room_coverage_fraction_mean`
- `seg_room_coverage_fraction_max`
- `seg_local_slant_fraction_of_touched_rooms`
- `bld_slanted_area_total_m2`
- `bld_slanted_area_fraction`
- `seg_is_small_partial_room_slant`
- `seg_small_partial_room_slant_score`
- `bld_dormer_per_slanted_roof_ratio`
- `seg_requires_dormer_second_pass`
- `plane_interior_crossing_depth_m`
- `plane_downslope_exit_distance_to_footprint_m`
- `plane_upslope_exit_distance_to_footprint_m`
- `plane_downslope_points_outside`
- `plane_downslope_exit_vs_reverse_ratio`
- `plane_exterior_edge_contact_fraction`
- `plane_eave_edge_to_exterior_shell_m`
- `plane_eave_exterior_contact_fraction`
- `artefact_internal_staircase_score`
- `artefact_internal_staircase_candidate`
- `ont_room_is_mixed`
- `seg_any_room_mixed`
- `ont_part_mixed_room_fraction`

One important detail is that local-slant coverage is now based on actual overlap between the segment and the room slab, rather than a cruder raw-area approximation.

### B. Make the full rebuild robust enough to run end to end

When we tried rebuilding the full feature corpus from scratch, several geometry robustness issues surfaced.

These were fixed so the corpus can actually be processed reliably:

- safer union handling for invalid polygons
- helpers for iterating geometry points and tracing plane flow
- support for multipart line geometries in overlap projection

These fixes mattered because a model pipeline is only as good as its ability to produce features consistently across the whole corpus.

### C. Remove training-time / offline-only leakage from the deployable model

The expanded parquet contains some columns that are useful for analysis but are not valid at inference time.

We explicitly excluded those from the deployable training matrix, including columns under prefixes such as:

- `pred_`
- `meta_`
- `lbl_`
- `sib_`

and selected explicit columns such as:

- `label_is_near_decision_boundary`
- `label_flip_stability_score`
- `scan_age_days`
- `scan_roomplan_version`
- `bld_accept_rate_history`
- `xm_heuristic_agrees_with_label`
- `xm_heuristic_disagreement_rate_in_part`
- `lbl_pitch_bucket_accept_rate`
- `lbl_azimuth_bucket_accept_rate`
- `lbl_family_accept_rate`
- `trace_rule_accept_rate_prior`

This matters because otherwise the model might look strong offline while depending on signals that do not exist in real scoring.

### D. Rebuild, retrain, re-extract rules, and rescore the full corpus

After the feature and robustness work, we reran the full pipeline:

- rebuild the feature matrix
- train the model
- extract rules
- score the full V3 results corpus

This gives us a coherent post-change operating point rather than a partial or mixed snapshot.

## 7. What was tested

Tests were added or updated around three key risk areas:

- exhaustive feature extraction
- multipart line handling in overlaps
- deployable-model filtering of offline-only columns

Relevant test files:

- `reconcile_v3/tests/test_exhaustive_features.py`
- `tests/test_extract3d_overlaps.py`
- `tests/test_modelling_prepare_data.py`

Targeted test command run:

```bash
python -m pytest tests/test_extract3d_overlaps.py tests/test_modelling_prepare_data.py reconcile_v3/tests/test_exhaustive_features.py tests/test_score_results.py -q
```

Result:

- `12 passed`

## 8. What artifacts now exist

The current canonical outputs are in `artifacts/`.

Most relevant review artifacts:

- `artifacts/features_expanded.parquet`
- `artifacts/labels_joined.parquet`
- `artifacts/model_gbm.pkl`
- `artifacts/model_metrics.json`
- `artifacts/model_report.md`
- `artifacts/gbm_feature_importance.csv`
- `artifacts/auto_reject_rules.md`
- `artifacts/auto_reject_rules.json`
- `artifacts/reconcile_v3_results_scored.json`
- `artifacts/oof_predictions.parquet`

The scratch full rebuild outputs also exist in:

- `.context/full_rebuild_parallel/`

## 9. What the rebuilt dataset now looks like

The rebuilt expanded feature parquet now has:

- `11925` labeled rows
- `1115` total columns

After removing non-deployable columns, the trainable deployable model sees:

- `994` features

This is important because earlier in the process there was confusion around the smaller `444`-column artifact. That earlier artifact was only a partial surface. The current canonical one is the larger rebuilt matrix.

## 10. What model quality looks like right now

From the current canonical metrics:

- labeled rows: `11925`
- labeled buildings: `141`
- base positive rate: `0.2251`
- heuristic `F1_accept`: `0.4838`
- calibrated GBM `F1_accept`: `0.8384`
- calibrated GBM ROC AUC: `0.9689`
- calibrated GBM PR AUC: `0.9081`

This means the trained model is clearly much better than the original heuristic baseline on the supervised labeled set.

So from a pure classification standpoint, the work is directionally successful.

## 11. What the auto-reject rules look like right now

The current conservative rule extraction pass produced:

- a depth-4 tree
- `16` leaves total
- `4` shippable reject leaves after support/purity filtering

Rule extraction gates used:

- support `>= 50`
- purity `>= 0.95`

Current reject-rule coverage:

- `5443 / 9241` reject labels
- `58.9%` reject coverage

This is conservative by design. The tradeoff is that the rules remain high-purity but cover less of the reject space.

## 12. What the full autonomy result looks like right now

The scored full-corpus result contains:

- `223` buildings
- `13410` merged roof segments

Final autonomy labels:

- `1315` `auto_accept` (`9.8%`)
- `9103` `auto_reject` (`67.9%`)
- `2992` `review` (`22.3%`)

Also:

- `6175` segments had at least one rule fire
- all `13410` segments received a score

This is the main operational result of the current round.

## 13. How this compares to the earlier partial run

Before the full rebuild, there was an earlier pragmatic run on a smaller feature surface.

That earlier run had:

- `444` expanded columns
- `426` deployable model features
- `2` reject rules
- reject-rule coverage of `69.8%`

Its final autonomy split was:

- `8.5%` auto-accept
- `73.6%` auto-reject
- `17.9%` review

The current rebuilt run has:

- `1115` expanded columns
- `994` deployable model features
- `4` reject rules
- reject-rule coverage of `58.9%`
- `9.8%` auto-accept
- `67.9%` auto-reject
- `22.3%` review

So the current state is:

- the model fit improved slightly
- the feature surface is much richer and more complete
- the final autonomy policy became more cautious
- review volume increased

That is the central tension in the current state of the work.

## 14. What this means in plain language

We are probably better at understanding the difference between roof and non-roof segments than before.

But we are not yet better at turning that understanding into fewer items for a human reviewer.

In other words:

- the classification layer improved
- the autonomy operating point did not improve

This is why it can feel like "there is more and more to review" even though the model work itself was not wasted.

The likely explanation is that the richer model is expressing uncertainty in a way that the current rules and thresholds are not exploiting well enough.

## 15. What the current leading signals appear to be

The GBM importance output suggests the model is relying heavily on:

- height above ground
- distance from supporting walls to the segment
- covered-side interaction terms
- azimuth match against ceiling-plane context
- how the plane exits the building footprint
- hypothesis match quality

That is broadly consistent with the intended design:

- staircase-like or internal artefacts should behave differently from roof shell surfaces
- true roof planes should have more coherent exterior / footprint / support behavior

So the new features appear to be being used, not ignored.

## 16. What remains unresolved

Several things are still unresolved or only partially addressed.

### Dormers

Dormers remain a hard class. The current logic treats them more as a difficult second-pass concern than a fully solved first-pass classification case.

### Small partial-room slants

These are now represented more explicitly, but they remain a naturally ambiguous class and may still contribute to review volume.

### Operating-point tuning

This is now the biggest unresolved item.

At the moment, the work suggests that the main bottleneck is no longer "we do not have enough features". The main bottleneck is more likely:

- decision thresholds
- reject-rule extraction gates
- the balance between false confidence and review burden

## 17. What should happen next

The next step should be operating-point optimization rather than another large generic feature expansion.

Concretely, the next evaluation phase should do the following:

1. Sweep score thresholds on out-of-fold predictions.
2. Sweep rule-extraction support and purity thresholds.
3. Compare candidate operating points under explicit constraints such as:
   - max acceptable false-accept rate
   - max acceptable false-reject rate
   - target review budget
4. Compare the earlier and rebuilt models at those operating points rather than by raw F1 alone.

That will tell us whether the rebuilt richer model actually dominates in the way we operationally care about.

## 18. Files most relevant for expert review

Code:

- `reconcile_v3/analysis/exhaustive_features.py`
- `reconcile_v3/analysis/modelling.py`
- `reconcile/extract3d/overlaps.py`

Tests:

- `reconcile_v3/tests/test_exhaustive_features.py`
- `tests/test_extract3d_overlaps.py`
- `tests/test_modelling_prepare_data.py`

Artifacts:

- `artifacts/model_metrics.json`
- `artifacts/auto_reject_rules.md`
- `artifacts/gbm_feature_importance.csv`
- `artifacts/reconcile_v3_results_scored.json`
- `artifacts/oof_predictions.parquet`

## 19. Reviewer questions to focus on

The most useful review questions are:

- Are the new staircase / interiority / exteriority signals conceptually correct?
- Are we now representing the problem well enough, or are any major building-physics signals still missing?
- Is the deployable feature filtering correct and complete?
- Are the conservative auto-reject rules too narrow because the gates are too strict?
- Is dormer handling appropriately deferred, or should it be explicitly split into a separate first-pass branch?
- Is the real problem now thresholding and autonomy policy rather than feature coverage?

## 20. Bottom line

The project is trying to classify which slanted merged segments are real roof surfaces in a noisy reconstructed building model, then use that classification to reduce manual review.

This round successfully:

- expanded the feature surface substantially
- incorporated staircase / exteriority / local-slant / ontology-mixed-room signals
- fixed geometry issues needed for full-corpus rebuilds
- removed training-time leakage from the deployable model
- retrained and rescored the full corpus end to end

The current system is stronger as a supervised classifier than before.

However, it is not yet stronger at the autonomy goal that matters most operationally: reducing the number of segments that must be manually reviewed.

That is why the next phase should focus on operating-point tuning rather than another broad search for additional features.

