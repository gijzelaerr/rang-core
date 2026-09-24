# Frozen sky-completeness and calibration-response controls

Protocol approved before new measurements, 2026-09-24; common continuation
freeze commit `afe721f`. Status: measured, fresh precision-corrected run completes
2026-09-24 08:51:35UTC from checked implementation `1f53a17`. The first ten-solve
run failed evaluation, is preserved untouched and is not exportable; see the
[precision diagnosis](flagging-response-precision.md). Ten repeated solves use
the same physical controls, not ten new independent realizations.
The old [signal experiment](flagging-signal.md) and its bounded spectral fits
remain unchanged. This is a new diagnostic, not a retrospective bound expansion.

## Measured response: sky completeness matters more than this coarsening

Full evidence: [all controls, fits and provenance](results/gain-tv-response.json),
[independent replay](flagging-response-verification.md) and
[audit predicates/programs](results/gain-tv-response-audit.json).
The fixed-G0 reference fit recovers the signed 60/120mJy perturbations to native
storage precision. Every arm uses all9,169 original TEST samples, loses none,
and has rank2/condition1.92390. Ratios below are fitted total paired response
relative to each sign's fixed-G0 reference, not blind astrophysical flux recovery.

| Grid | Calibration sky | Compact + / − response | Extended + / − response |
| --- | --- | ---: | ---: |
| 2,32 | Omitted | 51.00% / 51.30% | 74.19% / 74.15% |
| 2,32 | Complete diagnostic | 99.96% / 99.95% | 98.92% / 98.92% |
| 14,128 | Omitted | 52.40% / 52.71% | 76.21% / 76.17% |
| 14,128 | Complete diagnostic | 101.10% / 101.10% | 99.92% / 99.91% |

In the positive fine omitted-sky arm, direct inverse-Jones correction gives
60.149/120.051mJy, but adapting the gains changes correction of the SAME original
DATA by −29.547/−31.020mJy. Total fitted response is30.601/89.030mJy. Both signs
show comparable attenuation. Visibility decomposition closes within8.253e-15Jy
and coefficient decomposition within6.267e-17Jy across all eight arms. This is
a measured conditional calibration-absorption mechanism, without any added flags.

The positive omitted fine control lowers TV from0.14744 to0.14685; including the
sources gives0.14728 while preserving substantially more response. Coarsening
reduces clean normalized polar TV to0.03393, but clean validation MSE rises from25.206
to31.678 (25.7% worse). Coarse baseline-Jones products differ about9.16% from
the empirical fineG0 products. Cross-grid support/gain freedom differ: neither
lower TV nor coarsening establishes better calibration or signal preservation.

The complete sky uses known injection truth as a diagnostic, not a deployable
policy. All spectra/locations/extents are known in evaluation; no beam/DDE,
independent noise, confidence intervals, blind detection or images are measured.
The TEST fit does not select masks/arms. Every final working FLAG/FLAG_ROW returns
exactly to the received state; original/source DATA, base model and all native
WEIGHT/SIGMA columns remain unchanged. Actual allocation is about0.828GiB,
within the checked1.5GiB budget; this is not an OS quota or native cost benchmark.
The independent replay confirms all native calibration inputs/settings and
prediction losses reproduce exactly. Nine gain products reproduce bit-for-bit;
the clean fine solve differs by≤3.141e-16 and shared normalization by one ulp.
The audit retains602/614 initial passes and12 strict exact-identity failures,
with24 separately passing roundoff checks and30 backup/boundary checks. These
are qualified numerical reproduction, not independent scientific realizations.

## Physical and solve freeze

Reference1283.791015625MHz, intrinsic unpolarized scalar sources relative to the
MS phase centre. Direction cosines use the arcminute-to-radian factor; include
the noncoplanar centre phase and tangent-plane circular-Gaussian Fourier shape.

| Source | Flux | l,m | FWHM | Fixed spectral index |
| --- | ---: | --- | ---: | ---: |
| Compact | 60mJy | +9,−6arcmin | point | −0.5 |
| Extended | 120mJy | −12,−14arcmin | 8arcmin | −0.9 |

Amplitude1, signs+1 and−1. This is deterministic: no new stochastic seed;
the original seed7 TRAIN/validation/TEST split and noisy DATA are reused.
Negative sign is a finite-perturbation response diagnostic, not a physical
negative-flux emitter. The new fine-grid clean empirical gains G0 corrupt both
perturbations as G0_p B G0_q^H. No beam, pointing or other DDE is included;
G0 is not asserted to be the physical telescope Jones response. Preserve
complex64 rounding and evaluate the actual rounded DATA difference.

Actual prepared fixture:14 integration centres,7.996617s spacing,
103.956024s centre-to-centre span (~112s with exposure). Native channels
1024:3072 remain the eligible window. Frozen grids:

| Grid, integrations/channels | TRAIN time/frequency bins | TRAIN antenna boxes |
| --- | ---: | ---: |
| 2,32 | 288 | 1150 |
| 14,128 | 11 | 44 |

The coarse solve assumes constant gains across the entire scan. Support counts
are not a rank/connectivity certificate; actual unsupported/ill-conditioned
solutions are retained as limitations, never silently removed from individual
comparisons. Keep all original weights, full2×2 QuartiCal `G.type=complex`,
identity initialization,50-iteration budget, unchanged convergence settings.
The existing Rust full-matrix TV kernel and instrumentation are retained.

Ten actual diagnostic solves, no native flagger or flag-policy search:

1. Clean fine/coarse baselines (two solves), shared by both signed pairs.
2. Each sign × each grid × omitted/complete diagnostic sky (eight solves).

Fine G0 defines one physical gain normalization for every solve. Report TV
relative to each grid's own baseline edge support. Coarsening changes support
and gain freedom, so lower cross-grid rawTV is not a quality claim.

## Sky and data boundaries

Source trees and immutable original.ms are read-only; only fresh copied work.ms
is changed. Observatory FLAG/FLAG_ROW, raw DATA and all native WEIGHT/SIGMA
columns remain unchanged in originals. Save whole working-MS/state backups
before DATA injection, plus pre/post flags. Injection affects only originally
eligible TRAIN/validation/TEST cells; no new noise and no added flags.

`RANG_MODEL_DATA` (or the prepared base model column) is always preserved.
The complete control appends the separate `RANG_RESPONSE_MODEL` column, after
exclusive schema/base-model/flags/state backups. Its truth-assisted calibration
sky includes the known intrinsic signed perturbation. This is an explicitly
labelled calibration diagnostic, NOT a deployable flag selector or a learned
sky model. All arms are frozen and run regardless of measured loss/recovery;
TEST/source truth never chooses a policy. The complete column is retained as a
documented diagnostic; final working flags return exactly to original state.

## Frozen evaluation

Use a single common original TEST support for all ten solves and both fixed-G0
reference responses. Report every unsupported/lost sample. Invert only finite,
valid Jones matrices with condition<=1e8. StokesI proxy is half the corrected
visibility trace and is invariant under the common right-unitary gauge.

Fix evaluation weights using native correlation weights propagated through the
fine-G0 Jones inverses. Independent correlation complex variance1/WEIGHT is a
diagnostic assumption. Paired values share original noisy DATA and estimated
gains: no independent-noise covariance, uncertainty interval or significance
claim is made.

Jointly fit both unit-Jy spatial templates multiplied by their frozen spectra
using real-coefficient linear least squares. Do not fit spectral indices, impose
positivity/bounds, discard negative/noisy values, or choose different support by
method. Report rank, condition, weighted residual/response energy, coefficients
and response relative to fixed-G0. Rank deficient/condition>1e8 fits are
unavailable, not invented zero flux. Known template positions/extents/spectra
are evaluation information, not blind detection or astrophysical inference.

Decompose the paired response exactly on that same fixed support/weight:

    total response = new-injected-gain correction of the actual injected delta
                   + change when correcting SAME original DATA with injected
                     versus clean paired gains

All three terms get the same linear template fit. Check visibility and fitted
coefficient closure before reporting cancellation/adaptation. This reveals a
conditional calibration mechanism; the original DATA need not be RFI-free.
Also report gauge-invariant baseline-Jones-product drift versus the same-grid
clean baseline and empirical fine-G0 reference, not raw gauge-dependent Jones
element errors. No actual dirty/deconvolved images are measured.

## Resources, interface and provenance

`rangtoy.flagging_response.run(run_dir, prepared_dir, iterations=50)`;
native Stimela2 entry `recipes/tv-flagging-response.yaml`. Root owns wrappers,
full verification, actual launch, compact archives and checked commits/pushes.
This track creates only its new module/tests/recipe/report; no shared runtime
or published artifact is edited.

Checked1.5GiB allocated-block budget per fresh run plus global8GiB free-disk
reserve. Check before every local write/copy/mutation; reserve80MiB before each
shared QuartiCal solve batch and inspect actual allocation afterwards. This is
NOT an OS-enforced filesystem quota. Any observed cap/reservation breach stops
further work without erasing failed outputs. Historical allocation forecasts
were exceeded; no forecast is substituted for actual filesystem checks.

`response-config.json` freezes sources, signs, grids, support/times, split,
source/model/helper/module/Rust-library/image/package provenance before solving.
Per-arm commands, gain products, metrics and checkpoints retain every control.
Backups are exclusive. Final audits check originals/source digests, exact flags,
documented injected DATA, unchanged base model and all native weight/SIGMA
columns. Pinned Africanus prediction is checked against the existing bounded
analytic DFT/Gaussian reference; public PyPI dependencies are unchanged.

No gain-TV-guided flagging improvement, native matched cost advantage, independent
observation transfer, astrophysical flux/slope recovery or images is established
by implementing this protocol. Null/negative controls must remain archived.

## Pre-measurement verification

25 pure/boundary tests pass: unrestricted positive/negative/zero linear flux,
retained noisy values, rank/conditioning failures, explicit support, fixed-weight
fit/decomposition closure, exact gain-adaptation cancellation, gauge-invariant
baseline products, real integration support and all checked-budget/namespace
guards. Ruff lint/format, in-memory byte compilation and whitespace checks pass.

Read-only checks in the existing pinned offline image validate native schema
JSON serialization (8185bytes), the separate complex StandardStMan column
descriptor, no name collision, exact clean source flags/DATA/model/all native
weight/SIGMA columns, and the frozen actual support counts. No column was added
and no calibration was run for these checks.

Conservative copy bounds in bytes: original.ms43339776, work.ms61718528,
state.npz24043520, manifest.json20480; one clone129122304. Three clones,
two pre-DATA working-MS/state backups and two pre-model state backups total
606978048bytes before predictions/new model columns/solver artifacts. These
are copy reservations, not a final-allocation measurement. The historical
paired16-solve signal tree is737MiB; expected new10-solve allocation is roughly
0.9GiB, checked dynamically against1.5GiB rather than promised from forecast.
Root must retain observed allocation and every failed/null checkpoint.
