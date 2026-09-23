# Established flagger comparisons

## Purpose and scope

Compare the current TV-guided policy with actual QuartiCal MAD and actual
Tricolour SumThreshold on the same small real MeerKAT L-band pointing scan.
This is not a representative science benchmark, clean-data ground truth, image
improvement or novelty claim. QuartiCal's complex full 2x2 Jones gains retain
two-integration / 32-channel intervals, 50-iteration identity initialization,
original weights, approximate unpolarized phase-centre sky, gauge convention
and fixed seed-7 splits.

## Scientific comparison design

- Original `FLAG` and `FLAG_ROW` are immutable lower bounds. Source and private
  `original.ms` are checksum audited. `DATA` and weights must be bit-preserved.
- Each native MAD proposal uses its own retained MS copy, training exclusions
  and snapshots before and after native flag writing. Import only eligible
  training samples; rerun identity-initialized calibration with its mask frozen,
  MAD disabled and flag writes disabled.
- Retain MAD's default diagonal-residual behavior. Compare unwhitened 5/10
  baseline/global thresholds and a predefined native-weight whitening sweep at
  5/10, 8/16 and 12/24. Disable solver-raised flag propagation only in proposal
  generation to isolate MAD; retain the baseline solver settings for evaluation.
- Tricolour 0.2.1 executes its genuine published NumPy/Numba SumThreshold kernel,
  using background and narrow passes at predefined sigma thresholds 10, 15 and
  20 on absolute `(XX+YY)/2`, a Stokes-I proxy. Mask holdouts, missing samples,
  autocorrelations and excluded channels; zero holdout values to prevent leakage.
- This is a **SumThreshold subset**, not Tricolour's full default strategy. It
  excludes static masks and UV continuum-polynomial subtraction. This already
  heavily flagged, 14-dump pointing scan does not qualify the full default
  MeerKAT strategy as a general science benchmark.
- The packaged 3x3 flag dilation expands masked random holdouts and existing
  gaps as though they were interference. Preserve this negative control, but
  also use an explicit holdout-safe configuration: dilation widths 1 and
  whole-time/frequency propagation fractions 1. Background estimation and
  SumThreshold remain unchanged. This adaptation must not be presented as the
  packaged default strategy.
- Never arbitrarily clip comparison masks to match the TV policy's budget.
  Report raw additional volume, TV on exact fixed baseline edge support with
  fixed normalization, held-out weighted errors and unsupported predictions.
- Select only candidates within the predefined 2% extra-volume budget and 1%
  validation-degradation limit, with unchanged objective:
  `TV/TV0 + 2*added_fraction + 0.25*MSEval/MSEval0`. Test never tunes thresholds
  or selects a method; no-change remains available.
- Final selected MS restores original holdout, outside-window and auto flags;
  audit against exact original-plus-selected flags. This is a frozen-mask
  comparison, not an all-data production calibration.

A prepared injected-RFI case is copied read-only. Its metrics include recall of
known injected training samples and additional flags outside those injections.
The latter are **not labelled false positives** because pre-existing real-data
contamination is unknown.

## Reproducibility

QuartiCal 0.2.7 remains unchanged in the original Python 3.12 environment.
Tricolour requires Numba 0.60 and is isolated in `/opt/tricolour`, not installed
over the solver dependencies. Both environments are pinned. Tricolour wheel
SHA256 is `7dd8dfcf8058bdc7351540d4d6248664169bab1debf8791234e9fa8846f1c63b`.
The child image is `rang-flagging-comparators:local`.

```sh
docker build --platform linux/amd64 -f tools/flagging/comparators/Dockerfile \
  -t rang-flagging-comparators:local .
bash tools/flagging/comparators/run-pilot.sh outputs/tv-comparators-new-run
```

Stimela2 recipe: `recipes/tv-flagging-comparators.yaml`. Python callable:
`rangtoy.flagging_comparators.run`, accepting either a pinned archive or a
read-only `prepared_dir`, never both. Outputs include native commands/logs/gains,
flag snapshots, Tricolour settings/versions, proposal masks, frozen calibration
diagnostics, `comparison.json`/`result.json`, `selected.ms` and `flag-audit.json`.
Each output directory must be fresh; nothing is overwritten. Runtime is offline
with read-only root/repository, explicit output and separate cache mounts.
Timings include amd64 emulation and cache effects, not native performance data.

## Measured first pilot, 2026-09-23

`outputs/tv-comparators-pilot-01` completed the full Stimela recipe. Baseline
TV was 0.1474368701, validation weighted MSE 25.2061226. No-change was selected;
all original flags, rows, DATA, weights, original-copy and source digests passed.

Native-whitened MAD 5/10 added 1.310% and increased TV to 0.148797. Native 8/16
added 0.020% and increased TV to 0.147528; native 12/24 added nothing. Default
unwhitened MAD 5/10 reduced TV to 0.144019 but added 3.756% and worsened validation
to 25.771327, so it failed both selection guards. Packaged-morphology Tricolour
added 76.641-88.671% at sigma 20-10 and lost held-out gain support. This is the
negative control motivating explicit missing-support-safe morphology, not proof
that Tricolour performs poorly on ordinary MeerKAT data.

The exact first-pilot code and result/audit backups are retained under
`outputs/flagging-comparator-backups/after-first-pilot`.

## Final matched controls, 2026-09-23

Final pinned image ID:
`sha256:fd87b9b71330adddcca1acba34bf6882aeaf961fd8613d4ce9d43975395ab7b8`.
The final clean Stimela recipe (`outputs/tv-comparators-pilot-02`) and the copied
strong narrowband injection (`outputs/tv-comparators-injection-01`) both passed
all seven flag/DATA/weight/source preservation audits and selected no-change.
The compact measured archive is `research/results/gain-tv-comparators.json`.

On clean input, holdout-safe SumThreshold sigma10 added 1.711%, reduced fixed
support TV from 0.147437 to 0.145074, but worsened validation MSE by 3.38%, failing
the 1% guard. Sigma15/20 added 1.347/1.834% but lost some baseline TV edges; those
TV comparisons are rejected rather than benefitting from smaller support. The
packaged-morphology sigma10 negative control still added 88.671% and lost valid
held-out predictions. An independent constant-input masked-holdout check using
the real Tricolour kernel and safe morphology added exactly zero new flags.

The strong injection contains 738 known contaminated training row/channels.
Native-whitened MAD 5/10 recovered 256 (34.7%), flagged another 903 outside the
injection and increased TV. Holdout-safe SumThreshold sigma10 recovered 373
(50.5%), added 2.218% overall and worsened validation by 3.27%, failing both
guards. Unguided residual sigma3 recovered 227 (30.8%), added only 37 outside
the injection and improved validation by 0.136%, but increased TV by 0.30%.
The TV-guided policy variants did not improve the selected objective. No-change
was selected on this case despite partial detector recovery; this is a useful
negative result for the TV-primary training design, not evidence that no RFI
was injected.

The injected comparator fixes gain normalization to its own contaminated
baseline scale (1.05251454). The injection-control branch uses the original
clean scale (1.05200391); absolute TV values differ by this convention while
the contaminated validation MSE matches exactly. Compare normalized within-run
ratios, not unmatched absolute TV across branches. Neither control qualifies
state-of-the-art science quality or native runtime.

Verification: six targeted Python tests, real-kernel constant-input check,
isolated dependency check, clean full Stimela recipe and copied injected-case
callable. Root runs the full project checks before committing the integrated
parallel work.

## Prepared-input safety boundary

After those measurements, `flagging_prepared.py` was added as a shared read-only
boundary gate. The comparator now rejects nested input/output paths in either
direction before creating its output. Before any calibration or flag writes it
checks the actual immutable original FLAG/FLAG_ROW and native weights against
saved state; actual working DATA/model/coordinates; actual MeerKAT L-band and
linear-four-correlation metadata; the scalar-sky requirement for the polar
gauge; and disjoint, boolean, originally eligible visibility splits. The
boundary audit and helper code SHA256 are recorded in every new run config.

Ten comparator regression tests and 24 helper tests passed. Independent
read-only actual-MS validation passed for both measured final comparator pilots
without changing them. Their code hashes continue to identify the pre-gate
implementation; the gate does not alter calibration, proposals or selection.
The exact pre-gate source/measurement backup remains in
`outputs/flagging-comparator-backups/final`.

A fresh shortened gated Stimela run, `outputs/tv-comparators-boundary-01`, also
passed end-to-end: authoritative boundary audit, baseline calibration, default
native MAD proposal/frozen evaluation, packaged Tricolour morphology negative
control, all TV-policy proposals, and final exact-mask/source/DATA/weight audit.
The sigma threshold sweeps were omitted in this safety smoke test. Baseline and
evaluated science values matched the corresponding earlier clean-pilot values.
The post-gate source/measurement checkpoint is
`outputs/flagging-comparator-backups/final-with-boundary`.

The safety smoke recorded its initial helper version SHA256
`25f4067f2cd31710e642d2577a4ea546c75cc3b87e9086fdff1011e04b100dc9`.
The final strengthened helper SHA256 is
`8c1878cdaa3259ca2e5416b78df2a89544a87cea86aa1b47099eaf4b3d96e8ab`;
it additionally checks original-DATA finite eligibility and manifest coherence
of channel window, split counts and positive integer gain intervals. Final
read-only validation of all three completed comparator artifacts passed those
strengthened checks; numerical measurements and their original hashes remain
unchanged. Final source checkpoint:
`outputs/flagging-comparator-backups/final-strengthened-boundary`.

Primary sources: [QuartiCal options](https://quartical.readthedocs.io/en/latest/options.html),
[Tricolour source](https://github.com/ratt-ru/tricolour),
[Tricolour MeerKAT paper](https://arxiv.org/abs/2206.09179).
