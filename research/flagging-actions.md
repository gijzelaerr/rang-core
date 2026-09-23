# Measured gain-TV patch-action pilot

Implemented and measured 2026-09-23. Baseline code revision `35e763b`;
this follow-up is diagnostic, not an established calibration improvement.

Use the same real MeerKAT L-band SKA scan 9, original flags, seed-7 visibility
splits, approximate unpolarized phase-centre model, native weights and QuartiCal
complex 2x2 grid (two integrations x 32 channels, 50 iterations).
Original input and `original.ms` remain read-only. Actual removals happen only
on `work.ms` and receive the existing before/after flag snapshots. Final output
restores original holdout/autocorrelation/outside-window flags; DATA is unchanged.

Define disjoint baseline x gain-time x gain-frequency training patches. Require
at least eight eligible samples; select 16 patches across the residual/TV score
range with seed 29. Features describe training-only whitened residual z-scores,
log residual amplitude, incident gain TV and patch size. Temporarily remove
each patch and re-solve from identity. The target is measured change in
fixed-support, fixed-scale gain TV divided by baseline TV; missing support is
an unavailable label, never a zero-change label.

Split the 16 actions into 10 train, 3 validation and 3 test with seed 29.
Fit a standardized ridge predictor; centering/scaling and coefficients use train
actions only, select penalty from `[0.1, 1, 10]` using validation-action error.
Test labels do not choose any model or mask. A proposed union considers only
training actions, penalizes additional flag volume and is capped at 2%; if
nonempty it requires a fresh solve, fixed TV support and the existing held-out
validation guard. A no-change option remains available. This action split is
not independent observation-level evaluation, and the approximate sky remains
a confounder. There is no gradient through QuartiCal.

## Measured result

Complete Stimela2 run: `outputs/tv-flagging-actions-01/`.
Baseline fixed-support TV 0.1474368701; validation/test weighted MSE
25.20612260 / 24.91960760. All 16 action re-solves completed with support and
prediction validity. Fifteen removals increased TV. Validation action 14
removed 29 training row-channel samples (0.0393%), lowering TV to 0.1471834032
(0.172%), but increased validation/test MSE to 25.23554006 / 24.96376248
(0.117% / 0.177%). Lower TV and better held-out prediction are not equivalent.
This does not establish whether those removed samples contained pre-existing RFI.

Selected ridge penalty 1.0. Test-action MSE of normalized TV change:
2.971197e-6, versus 1.670672e-6 for the constant training-mean predictor.
The learned predictor did not beat that small control and selected no added
flags. Tiny action counts cannot establish transfer or scientific quality.
All originals/flags and final DATA passed preservation audits; holdout additions
are zero. Solve timings were collected under amd64 emulation with compilation
and concurrent-work effects and are not a native performance benchmark.

Compact numerical labels, coefficients, splits, configuration and provenance:
[gain-tv-actions.json](results/gain-tv-actions.json).
Every definition, actual solve, rejected/null outcome and per-action checkpoint
remains in the run directory. Pre-run code backup:
`outputs/flagging-backups/20260923-actions/code.tar.gz`.

## Reproduce

With the base flagging image built, mount the checkout read-only and outputs
writable using the same runtime policy as the base pilot, then invoke:

```sh
stimela run recipes/tv-flagging-actions.yaml tv-flagging-actions \
  archive=outputs/ska-pointing/outer_scans.zip \
  run-dir=outputs/tv-flagging-actions-new
```

The parallel suite also exposes this branch. Use fresh output directories,
the pinned container environment and the Rust TV library; host Python 3.14
cannot run the pinned QuartiCal solver.

Next scientific question: do measured action benefits become more predictable
under known RFI injections and a verified calibrator sky, and do they improve
quality relative to established flaggers at matched cost? The parallel controls
inform that question; this single-scan ridge pilot is not evidence of novelty.

## Contaminated-copy action pilot

The same 16-action experiment completed in
`outputs/tv-flagging-actions-injected-01/`, reading only a copy of the completed
`outputs/tv-injections-pilot-01/cases/time-burst-s10` prepared input. Its exact
injection mask and oracle are never read by the learner. The consumed
contaminated DATA are intentionally different from the clean observation;
original observatory flags and native weights remain unchanged. Hash audits
confirm the entire prepared source and immutable originals were not modified.

Contaminated baseline TV0.1490094949, clean held-out validation/test MSE
25.37595806 / 25.06903159. Thirteen patch removals raised TV; three lowered it
slightly. The ridge model selected penalty10 and no additional flags. Its
test-action MSE9.546514e-7 is slightly worse than constant-control9.397650e-7.
There is no demonstrated action-learning or injection-recovery advantage.
Independent masks/actions on a single contaminated observation are not
independent-scanning generalization.

The injection-only oracle nevertheless benefits the full current objective in
this scenario, as documented in the injection report. Our small local action
pool and ridge predictor have not found that structured beneficial action;
this motivates testing broader time/frequency/antenna-coherent proposal shapes,
not assuming a more complex model will solve it. Retain the observed negatives.

Configuration, labels, coefficients and audits:
[gain-tv-actions-injected.json](results/gain-tv-actions-injected.json).
Use the action recipe's `prepared-dir=...` instead of `archive=...` to reproduce;
the input must be stable/read-only and the output path fresh and separate.

## Prepared-input boundary verification

The action recipe validates authoritative original FLAG/FLAG_ROW and weights,
working DATA/model, actual MeerKAT L-band coordinates, split eligibility and
manifest coherence before any solve or flag write. Either input/output nesting
relationship is rejected before directory creation. These guards are tested
independently of casacore; final native-weight preservation is also checked on
the exported MS.

Fresh gated Stimela smoke `outputs/tv-flagging-actions-boundary-01/` completed
six counterfactual actions on the strong time-burst prepared copy, selecting
no-change and passing all preservation checks. It records the initial helper
SHA256 `25f4067f2cd31710e642d2577a4ea546c75cc3b87e9086fdff1011e04b100dc9`.
The final stronger helper's independent read-only audit also passed all clean,
contaminated, concurrent and smoke action inputs. Its added manifest checks
did not rerun or replace the original 16-action numerical experiments.
See the [parallel verification report](flagging-parallel.md).
