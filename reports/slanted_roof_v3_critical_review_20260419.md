# Slanted Roof V3 — Critical Review of Framing and Approach

Date: 2026-04-19
Scope: second-opinion review of `reports/slanted_roof_v3_review_handoff_20260419.md`
Mode: ultradeep; adversarial framing (pushes back where reasonable rather than validating)

---

## Executive Summary

The V3 handoff describes a well-executed supervised-classification pipeline, but reports a telling paradox: the richer rebuild **improved F1 from 0.48 (heuristic) to 0.84 (GBM)** yet **increased review volume from 17.9% to 22.3%**. The document interprets this as a thresholding issue and proposes an operating-point sweep as the next step.

A careful read against the 3D-reconstruction and selective-classification literature suggests three framings the team should seriously consider before investing more effort in threshold tuning:

1. **F1 is not the right headline metric for a human-in-the-loop triage system.** The metric optimized (F1_accept) is decoupled from the operational objective (minimize review volume under an FP/FN budget). The F1/review divergence is not a surprise — it is what misaligned metrics reliably produce. Operating-point tuning alone will not fix a metric mismatch.

2. **The "classification of merged segments" framing may be locally optimal but globally myopic.** Buildings have roofs that must be physically consistent (watertight, covers footprint, topologically coherent). State-of-the-art roof reconstruction (PolyFit, polyhedral LoD2 pipelines) treats this as a **joint optimization over all segments of one building**, not as independent per-segment binary classifications. The team's own intuition — that true roof planes have coherent exterior/footprint/support behavior — is a *global* constraint being expressed as per-segment features, which is strictly weaker than optimizing globally.

3. **Label noise and ambiguity are the unexamined ceiling.** The document never reports inter-annotator agreement, never audits labels with confident-learning tools (e.g. Cleanlab), and never characterizes the 22.3% review cohort qualitatively. At F1 = 0.84 on a class mix of 22.5% positive, the model is likely close to the empirical label ceiling for *genuinely ambiguous* classes (dormers, small partial-room slants). Adding 500+ more features cannot break a ceiling that is set by label variance.

The richer V3 pipeline is probably better than V2 as a *classifier*. Whether it is the right *solution* to the operational problem is not established. The most consequential next step is probably **not** an operating-point sweep, but (a) replacing F1 with an explicit cost function, (b) a label-quality audit, and (c) a pilot of selective-classification with conformal risk control, which offers finite-sample guarantees on the exact coverage/error tradeoff the team is tuning by hand. These are cheap, diagnostic, and likely to reveal whether the current framing has more juice or has plateaued.

---

## 1. Restating the Real Problem

The V3 document correctly identifies the operational goal as **autonomy at acceptable risk**, not F1. Decomposed:

- Each merged slanted segment has a true state in `{roof, not_roof}`.
- Each segment receives an action in `{auto_accept, auto_reject, review}`.
- There is an implicit cost structure:
  - `c_FA` — cost of auto-accepting a non-roof (false-accept)
  - `c_FR` — cost of auto-rejecting a true roof (false-reject)
  - `c_R`  — cost of sending to human review
- Goal: minimize expected total cost over the corpus, i.e. `E[cost] = c_FA·P(FA) + c_FR·P(FR) + c_R·P(review)`.

The team never writes down `c_FA`, `c_FR`, `c_R`. That is the most important missing piece. Without it, no operating-point sweep can produce a "best" point — it can only produce Pareto fronts, and every choice on the front is arbitrary.

Every subsequent design decision — thresholds, rule-extraction gates, dormer deferral, feature engineering — is implicitly a hand-tuned weighting of these costs. Making them explicit is the single highest-leverage change available.

---

## 2. The F1 / Autonomy Paradox Is Diagnostic

The document reports:

| Run              | F1 accept | Auto-accept | Auto-reject | Review |
|------------------|-----------|-------------|-------------|--------|
| Partial (V2.5)   | —         | 8.5%        | 73.6%       | 17.9%  |
| Rebuild (V3)     | 0.8384    | 9.8%        | 67.9%       | 22.3%  |

Classifier quality improved on a labeled subset. Autonomy regressed on the full corpus. The document attributes this to richer uncertainty expression combined with conservative rule-extraction gates. That is probably partly right. But three alternative explanations are worth ruling out first:

### 2a. The metric drove the wrong direction

F1 weights precision and recall equally, which implicitly assumes `c_FA ≈ c_FR`. If in reality `c_R` is *low* (a reviewer accepting or rejecting takes seconds) and `c_FA` is *high* (a silently-accepted non-roof corrupts downstream thermal models for the whole building), then the optimal policy should push **more** ambiguous cases to review, exactly as V3 did. The "regression" may be an improvement under the actual operational objective.

This is testable. Write down one plausible cost ratio, compute expected cost for V2.5 and V3, and see which wins. If V3 wins under any reasonable cost ratio, the metric — not the model — is the problem.

### 2b. Calibration drifted

A GBM trained on more features will often produce scores that are less well-calibrated at the old thresholds, even if AUC improves. If V2.5's thresholds were chosen on V2.5's calibration curve, they are simply wrong for V3. Report Brier score and reliability diagrams across both runs before touching thresholds. Isotonic recalibration on a held-out set costs nothing and is likely to recover some of the "lost" autonomy.

Note: the handoff says "calibrated GBM" — but calibrated with what method, on what fold, against what target? The literature is clear that naive GBM scores skew toward extremes, and that isotonic regression needs more data than Platt scaling but gives better fit for non-sigmoid distortions. With 11,925 rows split across folds, either is feasible, but the choice and diagnostic plots should be in the artifact set.

### 2c. The positive class moved

V2.5 scored a smaller feature corpus; V3 scored the full rebuilt corpus (13,410 segments). If the rebuilt corpus includes building types or geometries under-represented in V2.5's scored set, the autonomy-rate comparison is not apples-to-apples. The handoff does not clarify whether the two runs score *the same segments*. If not, the comparison is confounded.

---

## 3. The "Classify Each Segment" Framing, Revisited

The handoff is explicit that the geometry step is considered sufficient and the residual problem is classification. That is a design choice worth challenging.

### 3a. What the roof-reconstruction literature actually does

The canonical pipelines for 3D building reconstruction from point clouds (aerial or terrestrial) do *not* treat candidate-surface acceptance as an independent binary classification. They treat it as a **joint selection problem under geometric constraints**:

- **Extended RANSAC** extracts plane hypotheses, then builds a **roof connection graph** and uses **topology analysis with geometrical constraints** to correct small patches and enforce roof-line / eave-line consistency. [1, 2]
- **PolyFit** [3] formulates the surface reconstruction as a **binary integer linear program**: each plane intersection produces candidate faces, and an optimal subset is selected subject to hard manifold/watertight constraints. Per-face fitness is a *data term*; global consistency is a *constraint*.
- **LoD2 reconstruction pipelines** [4, 5] reconstruct **polyhedral building models** by analyzing the topology of building outlines, roof slopes, and eave lines jointly — not by per-face classification.
- Recent **deep + geometric hybrids** [6, 7] combine neural segmentation with downstream constraint solvers for exactly this reason: a per-point (or per-face) classifier is insufficient to guarantee topological validity.

The team's V3 treats each `merged_roof_segment` as independent. This discards information. Two examples:

- If three segments within one building are predicted as roof but their planes do not form a valid roof topology (they leave gaps or overlap implausibly), at least one of them is almost certainly wrong — information the classifier cannot use.
- If a segment is predicted as "not roof" but removing it leaves an obvious hole in the building shell, the global constraint disagrees with the classifier.

### 3b. What this would look like in practice

Consider a **two-layer architecture**:

1. **Per-segment scorer** (the current GBM): produces calibrated `P(roof | segment)`.
2. **Building-level solver**: takes all segments for one building and selects a subset that (a) maximizes sum of scores and (b) satisfies global constraints (coverage of footprint, topological validity, no implausible overlaps, story-height consistency). Cast as an ILP, similar to PolyFit's face selection.

This framing would produce three outputs per segment:
- **dominated** (global solver strongly prefers include/exclude regardless of score) → auto-decide
- **ambiguous** (global solver is indifferent or close to indifferent) → review

The building-level constraints are information the V3 features are *trying* to encode indirectly (footprint exit, eave exterior contact, per-building slanted-area fraction). The features are shadows of the global structure. Encoding the structure directly is likely more powerful.

Caveat: this is a larger investment than threshold tuning. It is proposed as the "right problem" answer, not as what to do tomorrow. The low-cost diagnostic is: take 20 buildings where V3 reports `review` for multiple segments, solve the global constraint problem by hand, and see whether the "right" answer was usually globally determinable even when each segment was individually ambiguous. If yes, the global framing is where the remaining signal lives.

### 3c. What about pure deep semantic segmentation?

PointNet++, Point Transformer v2, and mesh-native nets [8, 9, 10] directly segment walls/floors/roof/stair classes from raw RoomPlan-style inputs. The tradeoffs vs the current pipeline:

- **Pro**: skips the "produce merged candidates, then classify" sequence, which compounds errors. Label cost is similar (still per-segment or per-point rather than per-segment) but the model has access to raw geometry rather than engineered features.
- **Con**: requires retraining infrastructure, larger labeled datasets, GPU serving. The current GBM/rules stack is easier to reason about and ship.
- **Realistic**: not the right first move. But worth a small prototype on 10–20 buildings if the GBM truly plateaus, because it tests the upstream hypothesis: *can a learner with full geometric context do noticeably better than engineered features?*

---

## 4. Label Noise Is the Unexamined Ceiling

The handoff never reports:

- Inter-annotator agreement (Cohen's κ, IoU, or any variant).
- How many segments have only one reviewer vs multiple.
- Whether ambiguity classes (dormers, partial-room slants) have systematically lower agreement.
- Any confident-learning audit.

This is a meaningful gap. The literature is clear:

- **Inter-annotator agreement bounds — but does not necessarily cap — achievable model accuracy.** Evidence from NLP simulations [11] shows models *can* exceed IAA when well-specified, but only if label noise is symmetric random error. Systematic label noise (e.g., consistent disagreement on dormers) remains a hard ceiling.
- **Cleanlab / confident learning** [12, 13] provides out-of-the-box label-error identification using out-of-fold predicted probabilities — which the team already computes (`oof_predictions.parquet`).
- **Geometric classification label IoU** is measurable and should be reported, because disagreement on roof-vs-not is often a disagreement on **segment boundaries**, not segment identity.

**Actionable, cheap diagnostic** (1–2 days):

1. Run Cleanlab on `oof_predictions.parquet` + `labels_joined.parquet`.
2. Identify the top-200 likely-mislabeled segments. Manually review 50.
3. Compute: what fraction of the 22.3% review cohort is in the likely-mislabel set?

If the overlap is high, adding features will never break the ceiling and threshold tuning is the wrong diagnosis — **label consolidation** is.

A related test: take the 4 `auto_reject` rules. For each, sample 30 segments it fires on. How often does an independent reviewer agree with the rule's reject decision? Rule purity is only as good as the labels that defined it.

---

## 5. The Selective-Classification Framework the Team Is Re-Implementing By Hand

The team's current design is essentially **predictor + shallow-tree reject rules + thresholds**. This is a hand-built instance of a well-studied formal problem. The literature offers several drop-in upgrades:

### 5a. Conformal risk control with selective prediction

SCRC [14, 15] and related work on calibrated selective classification [16] provide:

- **Finite-sample probabilistic guarantees** on error rate within the auto-decide region — distribution-free, given exchangeability.
- **Two-stage procedures** that first decide selection (auto vs review) and then condition predictions on selected samples.
- **Explicit coverage-risk tradeoff curves** — exactly what the team wants to tune.

A conformal-risk wrapper around the existing GBM would replace "support ≥ 50, purity ≥ 0.95" (arbitrary gates) with "auto-reject only when we can certify false-reject rate ≤ α on the held-out calibration set". This is strictly stronger than rule extraction.

### 5b. Cost-sensitive learning to defer

DeCCaF [17] and L2D variants [18, 19] formalize the cost-sensitive human–AI collaboration problem *with workload constraints* — precisely the team's setting. The formal objective generalizes the F1 accept the team is tracking, with explicit costs and reviewer capacity limits.

### 5c. Neyman-Pearson thresholds for asymmetric error control

If the team has a hard ceiling on, e.g., auto-accept false-positive rate (say, ≤1% for downstream thermal reliability), the NP framework [20, 21] provides the correct threshold-selection algorithm with probabilistic guarantees. "Pick the threshold that gave the best validation F1" does not give this.

Collectively, these frameworks argue the team's **Section 17 plan ("sweep thresholds")** is the right direction but the wrong tool. A sweep on OOF predictions is exploratory; it should be replaced by a principled procedure that returns a certified operating point, not just a curve.

---

## 6. Issues With the Current Pipeline Worth Naming

Independent of framing, several specific aspects of the V3 approach deserve scrutiny.

### 6a. Feature surface grew 2.5× but autonomy regressed

This is a classic signal that the classifier is now **expressing previously suppressed uncertainty**. The 444→994 feature expansion added signals the model "deserves" to be uncertain about. Two implications:

- The earlier 17.9% review figure was **optimistically low because the classifier was under-informed**, not because the situation was better. In other words, V2.5's autonomy was partially an illusion.
- If that is true, V3's 22.3% review rate is **closer to the actual ambiguity floor** given the current problem framing. Pushing it back down by threshold tuning would re-introduce the same overconfidence.

This framing flip matters. It changes the question from "how do we get back to 17.9%?" to "is 22.3% the true ambiguity rate of this classification problem, and if so, should we change the problem?"

### 6b. Dormer deferral is a framing smell

The handoff explicitly treats dormers as a second-pass concern. This is pragmatic but diagnostic:

- If dormers are genuinely rare and ambiguous, deferral is fine.
- If dormers are a substantial share of the 22.3% review cohort, they are the problem, not the residual.
- **The fix is probably not more features.** Dormers are small, topologically distinctive roof superstructures [22, 23] — they are solved in the roof-reconstruction literature by *explicit topological modeling* (recognizing them as small faces interrupting a larger roof plane), not by classification features. A per-segment classifier that sees a dormer as a "small partial-room slant that sometimes gets labeled roof" is being asked to do shape recognition through a keyhole.

Likely right move: decompose the label space — `{definitely_roof, definitely_not_roof, dormer_like}` — and treat dormer reconstruction as a geometry problem, not a classification one. The three-class classifier is easier and the geometry step can actually solve dormers.

### 6c. Rule extraction from a shallow tree is fragile

A depth-4 tree on 994 features produces 16 leaves; only 4 pass the purity gate. This is inherently sensitive to:

- Which features happen to rank high in one tree (feature-importance variance across folds is typically large for correlated features, of which this dataset surely has many).
- Threshold noise at internal nodes.
- Label noise in the leaves used to compute purity.

If the team runs this across 5 different seeds, the 4 shipped rules will likely differ. Report rule stability across folds/seeds before shipping any rule.

More robust alternatives that still give human-inspectable rules:

- **Rule lists via SkopeRules** or **RuleFit** with explicit purity/support bounds.
- **Conformal outliers** — declare auto-reject on examples whose conformal score is below an α-bounded threshold in the negative class.

### 6d. The train/inference feature-filter list looks incomplete by inspection

Excluding `pred_`, `meta_`, `lbl_`, `sib_` prefixes is sensible, but the explicitly listed "safe" columns include things like `bld_accept_rate_history`, `scan_age_days`, `xm_heuristic_disagreement_rate_in_part`. These are borderline:

- `bld_accept_rate_history`: if this is computed from *training labels*, it leaks target statistics about the same building the segment belongs to. If it is computed from *prior production decisions* on earlier scans, it is legitimate but introduces feedback coupling.
- `xm_heuristic_disagreement_rate_in_part`: depends on where "in_part" boundaries come from and whether they are computed from labels.
- `scan_age_days`, `scan_roomplan_version`: legitimate in principle, but will cause model decay as RoomPlan evolves.

A temporal split (train on scans older than date D, evaluate on scans newer than D) would catch leakage that K-fold does not. No evidence in the handoff that this has been done.

### 6e. 141 labeled buildings is small for per-building generalization

11,925 rows / 141 buildings ≈ 85 segments per building. The model may be implicitly learning per-building patterns rather than per-segment ones. Grouped cross-validation (group = building uuid) is essential; if reported F1 is from stratified-by-row CV rather than grouped CV, the real generalization is worse. The handoff does not specify.

---

## 7. What's Actually Upstream and Unexamined

The handoff takes "candidate merged slanted segments" as given. That upstream step is where the **hardest cases** are constructed. Three upstream questions worth asking:

### 7a. Are "ambiguous" segments ambiguous because merging is over- or under-aggressive?

If the merger combines a staircase surface and a roof surface into one segment, no classifier can save it. If it fragments one true roof plane into five pieces, each piece gets classified independently with less evidence. The 22.3% review volume could be 5% review + 17% bad-merge-products.

**Cheap test**: for 30 review-class segments, manually check whether the merged segment actually corresponds to a real physical surface.

### 7b. Why are there 13,410 segments for 223 buildings (60 per building average)?

That is a lot of candidates for buildings that typically have 2–6 real roof faces. Either:

- The geometry step is generating many spurious candidates (most of which are classified as reject, giving the illusion of high auto-reject). This is fine for throughput but may mean the "classification problem" is mostly rejecting obvious noise — and the *hard* problem is the 10–20 real candidates per building. F1 on 13,410 segments of which 77% are obvious rejects would be dominated by the obvious-reject class; real discriminative performance on the ambiguous class is hidden.
- Or candidates are generated at sub-face granularity (small pieces), in which case the per-segment framing is doubly wrong.

Reporting class-conditional metrics on "obviously-rejectable" vs "near-decision-boundary" segments separately would clarify this. The feature `label_is_near_decision_boundary` is excluded from training but should absolutely be used for stratified reporting.

### 7c. The review cohort is not characterized

The document reports "2,992 review" as a single number. That cohort should be:

- Clustered by score + top feature values — what are the distinct "types" of ambiguity?
- Sampled and manually reviewed by a domain expert to identify whether they are truly ambiguous or the model just hasn't learned them yet.

Without this, operating-point tuning is shooting in the dark.

---

## 8. Recommendations (Ranked by Expected Leverage ÷ Cost)

### Tier 1 — Before any further modeling work (total: ~1 week)

1. **Write down explicit costs** `c_FA`, `c_FR`, `c_R` and a utility function. Re-rank V2.5 vs V3 under this utility. This will probably either vindicate V3 or reveal that F1 has been misleading the team.
2. **Run Cleanlab on `oof_predictions.parquet`** to identify likely mislabels. Manually adjudicate 50. Report the agreement rate.
3. **Characterize the review cohort**: cluster the 2,992 review-class segments, sample 30, manual triage. Categorize by failure mode (truly ambiguous, bad merge, mis-labeled, dormer, staircase-adjacent).
4. **Recalibrate with isotonic regression on OOF predictions, re-sweep thresholds**, and report before/after ECE and Brier score. This alone may close some of the V2.5→V3 autonomy gap without any further modeling.
5. **Sanity-check feature leakage**: confirm grouped CV (not row-stratified), confirm `bld_accept_rate_history` is computed from a time-prior slice.

### Tier 2 — Methodologically stronger replacements for current steps (2–4 weeks)

6. **Replace rule-extraction with conformal risk control** for the auto-reject decision. Gives α-level certified false-reject rate instead of ad-hoc purity gates. Small code change; large guarantee upgrade. [14, 15]
7. **Replace threshold sweep with cost-aware learning-to-defer** [17]. Output becomes a principled assignment (auto/review) that minimizes expected cost under any reviewer-capacity constraint.
8. **Temporal holdout evaluation** to estimate model decay and leakage.
9. **Three-class relabel for dormers**: split `dormer_like` from `roof` and `not_roof`. Retrain. Likely reveals whether dormers are driving review volume.

### Tier 3 — Bigger bets (1–3 months)

10. **Global building-level solver** over per-segment scores. Start with a simple ILP: pick the subset of roof segments per building that maximizes sum of scores subject to coverage-of-footprint and non-overlap constraints. Test on 20 buildings by hand first.
11. **Pilot a direct semantic segmentation model** on a subset (point-level or mesh-level) to test whether engineered features are the bottleneck.

### What the handoff recommends that I'd de-prioritize

- **Generic threshold sweep on OOF predictions as the next step.** Useful only after the utility function is defined and calibration is checked. Doing it now risks optimizing a mis-specified objective and then claiming a win.
- **More broad feature expansion.** The evidence is that 994 features is past the point of diminishing returns given the label ceiling.

---

## 9. Answers to the Team's Six Reviewer Questions (Section 19)

> **Are the new staircase / interiority / exteriority signals conceptually correct?**

Directionally yes — exterior-facing sloped shell behavior is the correct physical prior. But these signals are shadows of building-level topology. Encoding topology directly (Section 3) is strictly stronger.

> **Are we now representing the problem well enough, or are any major building-physics signals still missing?**

Probably yes at the segment level. The missing representation is at the **building level** (joint consistency) and at the **label level** (dormers and partial-room slants need their own class).

> **Is the deployable feature filtering correct and complete?**

Not verified. `bld_accept_rate_history` and `xm_heuristic_*` need explicit temporal / leakage audits. A temporal holdout is the only way to be sure.

> **Are the conservative auto-reject rules too narrow because the gates are too strict?**

Almost certainly yes — but the fix is not looser gates, it is replacing hard purity gates with conformal α-bounded reject decisions that have probabilistic guarantees.

> **Is dormer handling appropriately deferred, or should it be explicitly split into a separate first-pass branch?**

Split it. Deferring dormers to a second-pass means dormers disproportionately inhabit the review cohort, which is the cohort the team is trying to shrink. Making dormers a separate first-class output is likely the single biggest review-volume reduction available via relabeling.

> **Is the real problem now thresholding and autonomy policy rather than feature coverage?**

Partially. The real problem is, in order: (a) the metric, (b) the label taxonomy, (c) the independent-per-segment framing, (d) the thresholding. Thresholding is the symptom most visible to engineers, but it is probably fourth on the list.

---

## 10. Limitations of This Review

- I do not have access to the underlying data, `model_metrics.json`, `gbm_feature_importance.csv`, or the scored corpus. Several critiques (e.g., calibration drift, grouped vs stratified CV) are hypotheses from the handoff text and should be verified against artifacts.
- I have not read the code in `reconcile_v3/analysis/exhaustive_features.py` or `modelling.py`. If the team has already addressed, e.g., temporal splits or Cleanlab audits and just did not write it into the handoff, the corresponding critique is moot.
- The "global solver" recommendation is based on reading the 3D reconstruction literature, not on an estimate of how much signal is actually recoverable on this dataset. A pilot is needed before investing.
- This review is deliberately adversarial. It highlights risks; it does not say the current approach is broken. The V3 work is clearly competent engineering. The question is whether it is competent engineering *of the right problem*, and the above are the places where that deserves a second look.

---

## 11. Bottom Line

The V3 handoff concludes "operating-point tuning rather than another broad search for additional features". That is the right direction of concern but probably the wrong first action. The sequencing that serves the operational goal best is:

1. Define the cost function. Without it, no sweep is meaningful.
2. Audit label quality. Without it, no classifier can exceed the ceiling you have not measured.
3. Recalibrate and report reliability diagrams. Small effort, often meaningful gain.
4. Characterize the review cohort. Unknown what 22.3% is made of.
5. Consider global-building-level solver and three-class dormer split as the real levers.
6. Only then sweep thresholds — but under conformal risk control, not ad-hoc gates.

The team may well be tackling the right sub-problem ("classify merged slanted segments") within the right meta-problem ("reduce review volume at acceptable risk"). But the handoff does not establish this. It reports strong classifier metrics and a regressed operational outcome and proposes tuning. The literature says tuning under a misspecified metric is how teams end up with nicer numbers and worse products. The cheapest insurance against that is Tier 1 above — roughly one week of non-modeling work that will clarify whether V3 is already the right answer under the right metric.

---

## Bibliography

### Selective classification, conformal prediction, learning to defer

[1] Geifman, Y., & El-Yaniv, R. *Selective classification for deep neural networks.* NeurIPS 2017. [https://arxiv.org/abs/1705.08500](https://arxiv.org/abs/1705.08500)

[14] Xu, Y., Guo, W., & Wei, Z. (2025). *Selective Conformal Risk Control.* arXiv:2512.12844. [https://arxiv.org/abs/2512.12844](https://arxiv.org/abs/2512.12844)

[15] *Conformal Selective Prediction with General Risk Control.* arXiv:2603.24704. [https://arxiv.org/html/2603.24704](https://arxiv.org/html/2603.24704)

[16] *Calibrated Selective Classification.* OpenReview. [https://openreview.net/pdf?id=zFhNBs8GaV](https://openreview.net/pdf?id=zFhNBs8GaV)

[17] *Cost-Sensitive Learning to Defer to Multiple Experts with Workload Constraints* (DeCCaF). arXiv:2403.06906. [https://arxiv.org/abs/2403.06906](https://arxiv.org/abs/2403.06906)

[18] *Two-Stage Learning to Defer with Multiple Experts.* NeurIPS 2023. [https://proceedings.neurips.cc/paper_files/paper/2023/file/0b17d256cf1fe1cc084922a8c6b565b7-Paper-Conference.pdf](https://proceedings.neurips.cc/paper_files/paper/2023/file/0b17d256cf1fe1cc084922a8c6b565b7-Paper-Conference.pdf)

[19] *A Two-Stage Learning-to-Defer Approach for Multi-Task Learning.* arXiv:2410.15729. [https://arxiv.org/html/2410.15729v4](https://arxiv.org/html/2410.15729v4)

### Cost-sensitive thresholds and Neyman-Pearson

[20] Tong, X., Feng, Y., & Li, J. J. (2016). *A survey on Neyman–Pearson classification and suggestions for future research.* WIREs Computational Statistics. [https://wires.onlinelibrary.wiley.com/doi/10.1002/wics.1376](https://wires.onlinelibrary.wiley.com/doi/10.1002/wics.1376)

[21] *Neyman-Pearson Multi-class Classification via Cost-sensitive Learning.* arXiv:2111.04597. [https://arxiv.org/html/2111.04597v3](https://arxiv.org/html/2111.04597v3)

### Label noise, inter-annotator agreement, confident learning

[11] *Inter-annotator agreement is not the ceiling of machine learning performance: Evidence from a comprehensive set of simulations.* ACL BioNLP 2022. [https://aclanthology.org/2022.bionlp-1.26/](https://aclanthology.org/2022.bionlp-1.26/)

[12] Cleanlab open-source library. [https://github.com/cleanlab/cleanlab](https://github.com/cleanlab/cleanlab)

[13] *Leveraging Inter-Rater Agreement for Classification in the Presence of Noisy Labels.* CVPR 2023. [https://openaccess.thecvf.com/content/CVPR2023/papers/Bucarelli_Leveraging_Inter-Rater_Agreement_for_Classification_in_the_Presence_of_Noisy_CVPR_2023_paper.pdf](https://openaccess.thecvf.com/content/CVPR2023/papers/Bucarelli_Leveraging_Inter-Rater_Agreement_for_Classification_in_the_Presence_of_Noisy_CVPR_2023_paper.pdf)

### Roof reconstruction and polyhedral building models

[2] *Extended RANSAC algorithm for automatic detection of building roof planes from LiDAR data.* Tarsha-Kurdi et al. [https://shs.hal.science/halshs-00278397v2/document](https://shs.hal.science/halshs-00278397v2/document)

[3] Nan, L., & Wonka, P. (2017). *PolyFit: Polygonal Surface Reconstruction from Point Clouds.* ICCV 2017. [https://openaccess.thecvf.com/content_ICCV_2017/papers/Nan_PolyFit_Polygonal_Surface_ICCV_2017_paper.pdf](https://openaccess.thecvf.com/content_ICCV_2017/papers/Nan_PolyFit_Polygonal_Surface_ICCV_2017_paper.pdf) · [https://github.com/LiangliangNan/PolyFit](https://github.com/LiangliangNan/PolyFit)

[4] *Semantic Segmentation and Roof Reconstruction of Urban Buildings Based on LiDAR Point Clouds.* IJGI 2024. [https://www.mdpi.com/2220-9964/13/1/19](https://www.mdpi.com/2220-9964/13/1/19)

[5] *Reconstruction of LoD-2 Building Models Guided by Façade Structures from Oblique Photogrammetric Point Cloud.* Remote Sensing 2023. [https://www.mdpi.com/2072-4292/15/2/400](https://www.mdpi.com/2072-4292/15/2/400)

[6] *Towards LOD-2 Building Reconstruction: Leveraging Segmentation and Roof Shape.* ISPRS Archives 2025. [https://isprs-archives.copernicus.org/articles/XLVIII-M-9-2025/1251/2025/isprs-archives-XLVIII-M-9-2025-1251-2025.pdf](https://isprs-archives.copernicus.org/articles/XLVIII-M-9-2025/1251/2025/isprs-archives-XLVIII-M-9-2025-1251-2025.pdf)

[7] *Large-Scale LoD2 Building Modeling using Deep Multimodal Feature Fusion.* CJRS 2023. [https://www.tandfonline.com/doi/full/10.1080/07038992.2023.2236243](https://www.tandfonline.com/doi/full/10.1080/07038992.2023.2236243)

### Indoor 3D and RoomPlan

[22] Apple. *3D Parametric Room Representation with RoomPlan.* Apple Machine Learning Research. [https://machinelearning.apple.com/research/roomplan](https://machinelearning.apple.com/research/roomplan)

[23] *Cloud2BIM: An open-source automatic pipeline for efficient conversion of large-scale point clouds into IFC format.* arXiv:2503.11498. [https://arxiv.org/html/2503.11498v1](https://arxiv.org/html/2503.11498v1)

### Semantic segmentation on point clouds / meshes

[8] Qi, C. R., et al. *PointNet: Deep Learning on Point Sets for 3D Classification and Segmentation.* CVPR 2017. [https://arxiv.org/abs/1612.00593](https://arxiv.org/abs/1612.00593)

[9] Qi, C. R., et al. *PointNet++: Deep Hierarchical Feature Learning on Point Sets in a Metric Space.* [https://github.com/charlesq34/pointnet2](https://github.com/charlesq34/pointnet2)

[10] *EGNet: 3D Semantic Segmentation Through Point–Voxel–Mesh Data.* 2024. [https://pmc.ncbi.nlm.nih.gov/articles/PMC11679086/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11679086/)

### Dormers and complex roof superstructures

[24] *3D Building Reconstruction with Parametric Roof Superstructures.* IEEE. [https://ieeexplore.ieee.org/document/4379211/](https://ieeexplore.ieee.org/document/4379211/)

[25] *Reconstruction of Complex Roof Semantic Structures from 3D Point Clouds Using Local Convexity and Consistency.* Remote Sensing 2021. [https://www.mdpi.com/2072-4292/13/10/1946](https://www.mdpi.com/2072-4292/13/10/1946)

### Data-centric AI / pipeline debugging

[26] *Data Debugging with Shapley Importance over End-to-End Machine Learning Pipelines.* arXiv:2204.11131. [https://arxiv.org/abs/2204.11131](https://arxiv.org/abs/2204.11131)

[27] *Navigating Data Errors in Machine Learning Pipelines.* SIGMOD 2025. [https://dl.acm.org/doi/10.1145/3722212.3725636](https://dl.acm.org/doi/10.1145/3722212.3725636)

### Calibration

[28] *Probability calibration — scikit-learn documentation.* [https://scikit-learn.org/stable/modules/calibration.html](https://scikit-learn.org/stable/modules/calibration.html)

[29] *How to Calibrate Probabilities for Imbalanced Classification.* Machine Learning Mastery. [https://machinelearningmastery.com/probability-calibration-for-imbalanced-classification/](https://machinelearningmastery.com/probability-calibration-for-imbalanced-classification/)

### Active learning (future option)

[30] *Model Uncertainty based Active Learning on Tabular Data using Boosted Trees.* arXiv:2310.19573. [https://arxiv.org/abs/2310.19573](https://arxiv.org/abs/2310.19573)

[31] *Active Learning on a Budget: Opposite Strategies Suit High and Low Budgets.* ICML 2022. [https://proceedings.mlr.press/v162/hacohen22a/hacohen22a.pdf](https://proceedings.mlr.press/v162/hacohen22a/hacohen22a.pdf)

---

## Methodology Appendix

This review was produced under the `/deep-research ultradeep` protocol. The six research streams were:

1. Selective classification, learning to reject, human-in-the-loop review budget optimization
2. 3D roof / building-element segmentation from point clouds (aerial + indoor LiDAR)
3. Label noise, inter-annotator agreement, and ceiling effects in ML classification
4. Conformal prediction, calibrated selective classification, Neyman-Pearson thresholds
5. Apple RoomPlan, indoor scan-to-BIM reconstruction, IFC mapping
6. RANSAC / PolyFit / polyhedral constraint-based roof reconstruction

Searches were executed across two rounds covering ~12 queries. Primary sources were ICCV, CVPR, NeurIPS, ICML, ISPRS, and MDPI Remote Sensing; secondary sources included arXiv preprints and open-source framework documentation (cleanlab, scikit-learn, PolyFit).

This review did not access the code in `reconcile_v3/analysis/*`, the model artifacts, or the labeled data. All specific claims about the V3 pipeline are sourced from the handoff document. Claims that depend on artifacts not inspected are flagged in §10 Limitations.

No plan-mode edits were made outside of this report file. The review is offered as a second opinion for the team's consideration; it is not a prescribed implementation.
