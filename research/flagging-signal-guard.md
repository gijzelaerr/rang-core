# Frozen TRAIN-only signal-response guard

Protocol approved 2026-09-24 before implementation or new measurements. Status:
implemented with21 targeted tests passing; actual paired diagnostics pending. Root owns
the common freeze commit, shared runtime image, launches, result archives and
full pre-commit verification. This track edits only its new module/tests/report/
Stimela2 recipe; historical modules and measured artifacts remain unchanged.

## Cases, masks and actual calibration budget

Use the existing four-antenna MeerKAT L-band pointing fixture with original
split seed7. Two NEW time-burst controls use seeds107/109, strength10 in native
inverse-weight units and target TRAIN occupancy0.005. Root's prospective track
creates immutable prepared cases under
`outputs/tv-next-20260924-01/inputs/cases/time-burst-seed{107,109}`.
New seeds on the same observation are not independent-observation validation.

Root's shared deterministic shortlist has two slots per global/antenna-star/
baseline group for residual, rawTV, seed137 random and detrendedTV rankings:
their deduplicated union is at most24 masks per seed. Geometry/2% TRAIN budget
and tie rules are shared; all candidate forecasts and refusals remain retained.
No old measured best mask or known RFI/source injection truth enters rankings.
The historical selected58-cell mask and trust-abstained best mask remain
read-only historical evidence, not bypasses or candidates on these new seeds.

Native Rust full-Jones Jacobians, TRAIN normal equations and anchored deletion
response provide the existing curvature/rank/U(2)-gauge checks, damping1e-6
times the full projected largest eigenvalue, spectral rank cutoff1e-10 and
station-relative step limit0.1. Do not relax those refusals for a better label.
Use genuine QuartiCal `G.type=complex` full2x2 gains, fine grid2integrations /
32channels, original WEIGHT_SPECTRUM, identity initialization and50iterations.

After all TRAIN forecasts are serialized, score predicted validation residual
MSE using validation DATA only. Rank by the existing objective
TV/TV0 + 2*added_fraction + 0.25*VAL_MSE/VAL_MSE0; baseline1.25. Require predicted
improvement>1e-6, native/support/2% gates, and deterministic mask-ID ties. Freeze
at most two counterfactual slots per seed: best admissible predicted objective
without the signal guard, and best admissible with it. No-change is always
retained. Deduplicate identical slots rather than solve them twice.

Actual clean-RFI re-solves use the same TV support/scale. Final acceptance also
requires actual objective improvement>1e-6, VAL_MSE<=1.01*baseline, no invalid
held-out prediction/support loss and the native/2% gates. The signal-guarded
acceptance additionally requires the frozen TRAIN signal constraint. Serialize
actual acceptances before any held-out signal-response fits. Rejected masks
remain diagnostic counterfactuals; do not substitute a new candidate afterwards.

For each retained mask, share one clean-RFI/base-model solve between two paired
signal controls: positive injected DATA with omitted sky, and the same DATA
with complete diagnostic sky. Thus at most3masks*3solves*2seeds=18actual QC
invocations, including the reused no-change baselines. All masks/controls run
regardless of final acceptance; missing/failed results are never invented.

## TRAIN-only absolute signal constraint

Frozen known intrinsic unpolarized template family, reference1283.791015625MHz:
compact at(+9,-6)arcmin, fixed spectrum-0.5; circular Gaussian at(-12,-14)arcmin,
FWHM8arcmin, fixed spectrum-0.9. Positions are direction-cosine offsets; retain
the centre w phase and tangent-plane Gaussian Fourier shape. This is a bounded
design family, not a blind-source claim or access to held-out injected truth.

For each template separately use a deterministic1mJy infinitesimal reference
probe, corrupted by the case's frozen no-change fine-grid empirical G0. This
does not write DATA. For an admissible mask, recompute native TRAIN curvature
at its forecast gains on retained TRAIN cells. Solve the probe's TRAIN tangent
response with the existing gauge/rank/trust machinery. Include BOTH direct
inverse-Jones correction of the probe and the derivative of correction of the
SAME original noisy/RFI DATA through the resulting gain tangent. Do not call
inverse correction alone calibration-response preservation.

Evaluate predicted derivatives on the same fixed original TRAIN support for
every candidate, using fixed G0 inverse-Jones/native-weight variance. Require
finite/condition<=1e8 Jones inverses and no support loss. Joint unrestricted-real
fixed-spectrum fitting gives the two columns of a2x2 unit-Jy transfer matrix T;
require full template rank/condition<=1e8 and operator norm ||T-I||2<=0.1.
No positivity, spectral fit, confidence interval or candidate-specific support
cherry-pick is allowed. Keep the complete matrix and direct/adaptation terms.

This is an ABSOLUTE near-identity constraint. It may reject every added mask
because the omitted calibration sky already suppresses this family. Preserve
that negative finding and an explicitly UNCERTIFIED no-change fallback; never
silently switch to a relative-to-unsafe-baseline constraint. Known family safety
in a local linear TRAIN approximation is not a guarantee for new sky directions,
nonlinear finite perturbations, primary-beam/DDE errors or an unknown science
sky. Unit probe amplitudes and TEST flux recovery must not choose a policy.

## Evaluation only after acceptance freeze

Positive60mJy compact /120mJy extended sources use the frozen family above, with
no new noise and fixed case-G0 empirical DI corruption. Injection touches only
originally eligible TRAIN/validation/TEST cells. Sources are absent from the
omitted calibration sky; complete-sky truth is an explicitly labelled diagnostic
control using a new RANG_RESPONSE_MODEL column, never a deployable selector.
Preserve original RANG_MODEL_DATA. No negative-sign or coarse-grid arms here.

Use one common original TEST support across every mask/control of both cases,
fixed per-case no-change G0 evaluation weights and unrestricted-real linear
fixed-spectrum template amplitudes. Report rank/condition, support losses,
negative/noisy coefficients, response versus fixed-G0 and exact total/direct/
gain-adaptation decomposition with unchanged1e-10Jy numerical closure guards.
No source truth or TEST loss enters candidate construction, ranking, tuning or
acceptance. RFI truth is read only after acceptance for diagnostic recall.
No imaging, fitted spectral slopes, CI or matched SOTA/cost advantage is claimed.

## Immutable boundaries and checked capacity

Source case trees/raw sources/original.ms are read-only. Choose a fresh exclusive
guard output; two clean/injected copied MS trees per seed, four clones total.
Back up full work.ms/state before source DATA additions, flags before/after,
and schema/base-model/flags/state before adding the complete-control column.
Original FLAG/FLAG_ROW, raw DATA and all four native WEIGHT/WEIGHT_SPECTRUM/
SIGMA/SIGMA_SPECTRUM columns remain exact. Final fresh working flags return
exactly to the received original state, not to an accepted-policy export.
Record explicitly documented RFI and source DATA differences in working states.

Checked1.5GiB allocated-block cap for this track and global8GiB disk reserve;
conservative pre-write/copy checks and80MiB reservation before each QC batch.
These checks are NOT an OS-enforced quota. Stop before further work on any
observed breach, preserve failures/backups and do not delete to force a pass.
Preflight conservative copy bounds and measure actual allocation; no forecast
is substituted for a resource observation. Root coordinates global concurrency.

Freeze input/source/model/split/helper/module/Rust-library/image/package hashes
before first solve and verify them at the end. Use the existing pinned offline
solver image, network disabled, repository/source mounts read-only and separate
writable run namespace/cache. No downloads or solves from this track before
root's checked source/runtime freeze. API planned:
`rangtoy.flagging_signal_guard.run(run_dir, prepared_cases, iterations=50)`;
`prepared_cases` is a list of exactly the two prepared paths. Shared
`flagging_prospective.make_shortlist` supplies the common candidate family;
`forecast_family(state, baseline, metrics, candidates)` returns TRAIN-only
records/raw gain forecasts/normal blocks, and `score_forecasts` is called only
after those TRAIN forecasts and signal constraints are serialized. Independent
copied baselines allow concurrent execution without reading prospective outcomes.
These interface details cannot broaden the frozen scientific settings.

## Implementation verification before measurement

The new module and native Stimela2 recipe implement the protocol above. All21
guard tests pass, including full non-diagonal inverse-Jones tangent versus
central difference, direct/adaptation closure, negative/noisy response retained,
cross-template leakage/operator norm, rank-deficient refusal and absolute unsafe
baseline refusal. Native Rust probe binding certifies the expected28-dimensional
four-station projected curvature on a pure test and produces exactly unchanged
TRAIN results when all TEST DATA/model/weights are replaced by invalid/extreme
values. Lost inverse/station support and unsigned-unsorted mask inputs refuse.
The shared prospective empty-family contract returns an uncertified no-change
slot rather than an invented safe action.

Combined guard/influence/trend/response targeted suite:68 tests pass. Ruff lint/
format, in-memory source compilation and whitespace checks pass. Source inputs
are preflight-checked for4stations/14integrations and raw-exact DATA outside
TRAIN; loaded native-library path and every used helper source receive frozen
digests. Shared shortlist record order/full-Jones shapes and the24-unique-mask
limit are checked explicitly. RFI truth is opened only after the acceptance
checkpoint and all paired solves; its diagnostics cannot mutate that checkpoint.

Actual QC count remains0 for this implementation verification. The future run
upper bound is18; two no-change-only abstentions need6, not18, actual solves.
Independent copied baselines are not counted as extra outside that bound. Root's
full local verification and fresh image containing the new Rust trend exports
must precede real execution; the old solver-only image is a dependency base,
not falsely advertised as containing the new native symbols. Rejections/nulls,
actual allocation and all solver invocations will be archived by root.
