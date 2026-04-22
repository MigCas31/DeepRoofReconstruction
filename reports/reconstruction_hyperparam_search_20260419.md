# Phase B.5 — hyperparameter search report

Date: 2026-04-19
Pilot: 20 buildings (deterministic shuffle of candidates.json filtered to
buildings with both a scan footprint and a V3 reference envelope), seed 42.
Trials: 50 random-search samples over `SolverConfig`. Total wall time 530s
(~10.6s/trial).

Artifacts:
- `reports/reconstruction_trials_20260419/trials.json` — full per-trial records
- `reports/reconstruction_trials_20260419/top_trials.md` — top-3 configs
- `reports/reconstruction_trials_20260419/search.log` — progress log

## Acceptance criteria (plan §B.5)

| Metric | Target | Best trial | Gap |
|-------:|:------:|:----------:|:---:|
| Pilot mean IoU | ≥ 0.9 | 0.352 | **miss by 0.55** |
| Review rate    | ≤ 0.10 | 0.85 | **miss by 0.75** |

**Result: not met.** The winning config is NOT promoted to
`reconcile_v3/reconstruction/hyperparams.json`.

## Search coverage

| Stat | score | mean_iou | review_rate |
|:---:|:---:|:---:|:---:|
| min | -0.171 | 0.289 | 0.85 |
| median | -0.042 | 0.373 | 0.95 |
| max | -0.013 | 0.373 | 0.95 |

Only 14 distinct `(mean_iou, review_rate)` outcomes across 50 trials; 20
trials landed exactly on `(0.373, 0.95)`. The hyperparameters we tuned
(`w_fit`, `w_prior`, `w_complexity`, `θ_cov`, `θ_overlap`, `θ_az`,
`K`) have almost no leverage on the outcome — the score function is
flat across most of the search space. **This is not a tuning problem.**

## Failure-mode breakdown (best trial, n=20)

| Outcome | Count | Note |
|:---:|:---:|:---|
| `no_candidates` | 7 | Upstream Phase A emitted zero candidates for these buildings. Solver can't pick from nothing. |
| `infeasible` | 4 | All four have `coverage_ref = 0` — candidate footprints don't overlap the V3 reference at all. |
| `ambiguous` | 6 | Selections rejected by runner-up gate. **4 of the 6 have IoU 0.60–0.93** — the gate is throwing away good solutions. |
| `solved` + auto_accept | 3 | IoU 0.39, 0.93, 0.99. The 0.39 is an over-commitment auto-accepted despite low realism. |

Three buildings reach IoU ≥ 0.9 that are currently gated to `review`:
`d8308bfc`, `f332f739`, `bfd05652` (all `ambiguous`). Moving them to
auto-accept requires an ambiguity gate that understands IoU (not just the
LP runner-up margin), which is a Phase C concern.

## Why the knobs don't move the score

- `no_candidates` is decided before the solver runs. No hyperparameter helps.
- `infeasible` at `coverage_ref = 0` means the candidate set does not
  intersect the V3 reference — tuning `θ_cov` changes feasibility, not the
  intersection.
- The `ambiguous`/`solved` split is driven by the LP gap + runner-up margin
  (B.1 defaults: `ε₁=0.02`, `δ=0.05`). Both are hardcoded in the solver, not
  in the B.5 search space, so random search can't move them. The
  `runner_up_margin` is the biggest lever, and it is set in B.1 defaults.

## What this means for the track

1. **Phase A candidate coverage is the dominant bottleneck** — 35% of the
   pilot has no candidates at all, and another 20% has candidates that
   don't overlap the V3 reference. These are upstream problems
   (`build_candidate_faces.py`), not solver-tuning problems.
2. **The runner-up margin (B.1) is the tightest auto-accept gate.** Four of
   the six `ambiguous` buildings have high IoU (0.6–0.93). Phase C's
   triage should use realism IoU as a second gate, not the LP runner-up
   in isolation.
3. **The B.5 search space is incomplete.** `runner_up_margin` and
   `lp_gap_epsilon` belong in the search space if we rerun after fixing
   the upstream candidate coverage; without that, rerunning is wasted
   time.
4. **The score function under-weights realism.** With a 0.5 coefficient
   on `review_rate`, a trial that fails upstream on 14/20 buildings
   cannot be beaten by any downstream tuning — the penalty is 0.5·0.70 =
   0.35, swamping all IoU improvements. Future iterations should score
   only on buildings where a decision was reachable.

## Recommended next step (before rerunning B.5)

Do **not** rerun the hyperparameter search as-is. Instead:

1. **Audit `no_candidates` buildings (n=7 in pilot, ~79 in full corpus).**
   Are these buildings actually candidate-less (zero merged segments), or
   is the Phase A filter rejecting them? Inspect a handful in the viewer
   with the V3 reference layer on.
2. **Audit `infeasible@cov_ref=0` buildings (n=4 in pilot).** Candidate
   footprints are not intersecting the V3 reference — either the
   candidate geometry is wrong or the reference is wrong for those
   buildings. Use B.4 screenshots to adjudicate which.
3. **Expand the B.1 hyperparameters into the B.5 search space:**
   `runner_up_margin` ∈ [0.02, 0.20] and `lp_gap_epsilon` ∈ [0.001, 0.05].
   Those are the gates that actually move the auto-accept count.
4. **Rework the trial score function** to condition on "solver had
   candidates": `score = mean_iou_on_decided + w·frac_auto_accept_of_decided`.

Only then is rerunning B.5 likely to move the needle.

## Top-3 configs (for reference)

See `top_trials.md`. All three cluster around `mean_iou ≈ 0.35`,
`review ≈ 0.85–0.90`; they differ mostly in hyperparameter values that
don't matter on this pilot. Not a signal.
