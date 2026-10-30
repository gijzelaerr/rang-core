# Fitted guarded-action benefit model

Frozen protocol, 2026-09-24, before new balanced outcome measurements.
This is a modest actual fitted ridge estimator, not just a TV ranking rule.
It predicts the **guarded objective benefit** of a whole TRAIN-only action:
baseline objective minus its measured counterfactual objective. Labels must
come from actual frozen QuartiCal complex 2×2 re-solves at the existing TV
scale/support. Missing solutions, support loss, budget/validation guard
failures and nonfinite outcomes are missing labels, never zero benefits.

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../history/README.md); this text keeps the paths it was written
with.

New balanced cases: seed101 train, seed103 validation, seed105 test; all
morphologies with one seed share a group. Group identifiers must not cross
splits. These still reuse one reference scan and do not establish independent
observation transfer. Observation IDs/digests and source result hashes are
recorded. The older seven structured cases are development data only; they
must not be relabeled independent-observation evaluation.

Fixed TRAIN-only candidate features are log sample count, added fraction,
log frequency width, single/all time scope, group indicators (global,
antenna-star, baseline), log1p residual score, log1p TV-conditioned score,
log1p TV/residual score ratio, and baseline supported-gain fraction. Optional
uncertainty information is deferred, rather than inventing missing values.
Candidate scores are the existing TRAIN-only measured generator outputs;
no validation/test visibility features or decoded injection truth are read.
Actual validation MSE is part of the training label's fixed guarded objective,
not a model input. The final visibility test loss is never a label or input.

Ridge penalties are frozen at [0.1,1,10]. Feature normalization and domain
envelopes use supported TRAIN actions only. Each case group receives equal
total fitting weight. Validation-group mean squared error chooses one penalty,
without refitting on validation. Validation's fixed 90th percentile of
prediction-minus-benefit sets a nonnegative optimism margin. Predictions
outside TRAIN feature ranges expanded by three TRAIN standard deviations
are refused; constant TRAIN features have tolerance 1e-8. Domain remains
MeerKAT L band and the original candidate semantics/guard protocol.

Ranking uses predicted benefit with stable mask-hash ties. A recommendation
requires predicted benefit minus that margin greater than 1e-6; otherwise
no-change. Test predictions/rankings are frozen before reading test labels
for evaluation. Test cases get prediction-only recommendations, not selected
or exported flags; deployment requires a fresh fully guarded confirmation.
No combination of individually trained rectangles is assumed additive.

Report missing supported labels by split, fitted coefficients/penalty,
validation/test prediction MSE against a TRAIN-mean constant, calibration
bias/slope, within-case rank inversion error and retrospective regret where
supported. Also report source counterfactual solve counts/emulated recorded
cost and zero new solver runs by this fitting workflow; no native performance
or robust scientific improvement claim. Every null/refusal is retained.

API: `fit_grouped_ridge(features, targets, groups, split)`,
`predict_actions(model, features)`, `rank_predictions(mask_ids, predictions)`;
`run(run_dir, cases_path)` consumes a JSON object with `cases`, each containing
`case_id`, `run_dir`, `split`, `group_id`, and optionally `observation_id`.
The compact list `{case_id, seed, result_path}` is also accepted: the result
filename must be `result.json`, its parent supplies run_dir, and the frozen
seed mapping supplies split/group identifiers.
The source manifest must explicitly match MeerKAT/L-band metadata and the
2/32 gain grid. Recorded original-source digests, not optional observation
nicknames, determine distinct-observation counts and the same-scan audit.
Each run directory has completed `result.json`, `manifest.json`, and actual
candidate records. Source/output ancestry and reused outputs are refused.
No Measurement Sets are copied or written and input artifacts remain unchanged.

Stimela2 entry: [tv-flagging-transfer.yaml](../recipes/tv-flagging-transfer.yaml).
This protocol is implementation/development, not a measured transfer result.

Implementation checkpoint: 26 targeted tests across transfer and uncertainty
pass, with Ruff lint/format. Includes test-label mutation invariance, grouped
partition rejection, missing guards/nonfinite support, feature-domain refusal,
source telescope/band/grid rejection, compact-manifest integration, exclusive
outputs and no MS exports. Stable transfer source SHA256
`0b1230d3a6e6189590ac38a81814429aaadb7adf149bb235f5532c226ad808a2`.
Only unit fixtures have been fitted at this checkpoint. Root schedules the
six real counterfactual case outcomes before the actual grouped model fit.

## Actual fitted checkpoint, 2026-09-24

[Complete model, forecasts and diagnostics](results/gain-tv-transfer.json):
35TRAIN(seed101),34validation(seed103),36TEST(seed105) guarded labels; no
missing/domain-refused labels in this run. Penalty0.1 wins validation without
refitting, optimism margin0.0010800573398795986. All six feature-only
recommendations remain no-change; test forecasts freeze before evaluation.
The estimator misses the supported time-burst105 benefit0.0007685912874668688,
and no flags are exported or deployed.

TEST group MSE is7.292590951716504e-7 versus TRAIN-mean constant
8.175777973013089e-6. However, a **post-hoc descriptive** known flag-cost-only
predictor `benefit=-2*added_fraction`, with no fitting/clipping/tuning, gives
9.289019773620847e-7 on the same finite supported TEST actions. This comparison
was not a frozen/tuned benchmark; retain it to expose how much of the apparent
constant-baseline win is predictable volume penalty, not useful flagging.
All split metrics, inversion errors and missed-action regret are archived.

Source labels require111 actual emulated counterfactual solves; the fitting
workflow runs zero new QuartiCal solves. Their recorded805.523s sum is neither
suite wall time nor native runtime. [680 separate read-only predicates](results/gain-tv-concurrent-audit.json)
reconstruct all105 actual features/guarded labels, independent ridge solutions,
TRAIN normalization/domain, validation tuning/margin, forecast ordering and
metrics. In-memory TEST-label mutations leave model/penalty/margin/ranks fixed.
One original observation spans every split: independent-observation transfer,
prospective winner confirmation, signal/image quality and SOTA cost/quality
superiority remain unestablished.
