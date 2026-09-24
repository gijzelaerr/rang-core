# Fitted guarded-action benefit model

Frozen protocol, 2026-09-24, before new balanced outcome measurements.
This is a modest actual fitted ridge estimator, not just a TV ranking rule.
It predicts the **guarded objective benefit** of a whole TRAIN-only action:
baseline objective minus its measured counterfactual objective. Labels must
come from actual frozen QuartiCal complex 2×2 re-solves at the existing TV
scale/support. Missing solutions, support loss, budget/validation guard
failures and nonfinite outcomes are missing labels, never zero benefits.

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
