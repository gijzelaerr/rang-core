# Frozen science-signal preservation experiment

Protocol frozen 2026-09-24 before any source-response measurement. Status:
implemented and targeted validation passed; actual QuartiCal outcomes pending.
This track follows the common `research/flagging-concurrent.md` protocol.

## Source and applicability freeze

Reference frequency1283.791015625MHz. Both sources are unpolarized, with intrinsic
scalar power-law spectra. Direction cosines are the stated l/m numbers multiplied
by the arcminute-to-radian factor relative to the MS phase centre.

| Source | Integrated flux at reference | l,m | Circular FWHM | Spectral index |
| --- | ---: | --- | ---: | ---: |
| Compact | 50mJy | +12,+8arcmin | 0 | -0.7 |
| Extended Gaussian | 100mJy | -15,+10arcmin | 10arcmin | -1.0 |

The positive CASA/MS Fourier convention includes w(n-1). The Gaussian uses the
standard tangent-plane Gaussian Fourier attenuation and its centre's exact
noncoplanar phase. Existing
[Africanus WSClean prediction](https://codex-africanus.readthedocs.io/en/latest/rime-api.html)
predicts both components; a bounded independent NumPy reference checks the full
prediction. The primary beam, antenna pointing and direction-dependent effects
are deliberately absent. This is not a claim that these fluxes would be observed
through the real MeerKAT off-axis beam, especially on this dedicated pointing scan.

Freeze the physical settings before a clean-reference full-Jones solve. Corrupt
the intrinsic source visibility B using those fixed clean gains, G0_p B G0_q^H,
and add it only to originally eligible TRAIN/validation/TEST cross-correlations.
This conditional DI-gain injection gives a known inverse-G0 reference response;
the empirical G0 is not asserted to be the physical telescope Jones response.
Native complex64 rounding is recorded, and evaluation compares with the actual
rounded DATA difference. No noise realization is added, so the seed-7 prepared
visibility split and the original noisy real DATA are common to both sides.

Neither source is added to the calibration sky. Original Observatory FLAG/
FLAG_ROW and all DATA/WEIGHT/SIGMA columns in source/original.ms remain unchanged.
Working DATA/state are backed up before injection, and flags are snapshotted.

## Frozen comparison and selection

Actual QuartiCal `G.type=complex`, full2x2 matrices,50iterations, identity
initialization, original weights and the prepared two-integration/32-channel
grid. Use the initial clean gain normalization throughout the paired experiment;
the injected baseline fixes TV edge support for the policy objective.

No-added-flags; the existing9-grid (thresholds8/5/3, TV weights0/1/3) with exact
mask deduplication; native-weighted QuartiCal MAD5/10, diagonal residuals. Residual
and TV families retain no-change. Selection remains fixed-support TV/TV0 plus
2*addedfraction plus.25*validationMSE/MSE0, <=2% flags and <=1% validation increase.
Every distinct proposal gets the identical mask on a clean/injected paired solve.
Exact per-family attempted/distinct masks and solve costs are recorded; do not
claim matched state-of-the-art runtime from this small emulated diagnostic.

Source templates and persisted truth are not supplied to selectors and are
decoded only after the frozen selections are written. Test loss does not choose
a policy. The optional genuine unmodified pinned CARACAL mild CLI is a separate
operational comparator: its features may see TEST DATA and it is not an unseen
holdout flagging evaluation or full CARACAL pipeline. It is disabled in the first
bounded run because each native CLI has a verified ~300s logger shutdown delay.

## Evaluation freeze

For each identical-mask pair, apply the two solved Jones inverses and measure
the difference in half the visibility matrix trace (StokesI proxy). This trace
is invariant under the common unpolarized U(2) gauge. Reject unsupported,
nonfinite or Jones-condition>1e8 samples before making a common TEST support;
record every lost reference TEST sample and each method's unsupported count.
All methods and the fixed inverse-G0 reference use precisely that common support.

Use fixed clean-reference native weights propagated through the StokesI inverse
Jones coefficients. This assumes independent original correlation noises with
complex variance1/WEIGHT; it is only a variance proxy. Paired measurements share
the same original noisy DATA, and gains are estimated from it, so no independent
noise covariance, confidence interval or statistical significance is claimed.

Jointly fit both known spatial templates' real fluxes and power-law spectral
indices with SciPy least_squares: flux bounds[-1,+1]Jy, index bounds[-5,+3],
100function evaluations maximum, analytic Jacobian, fixed source-parameter
initialization/scaling, all tolerances1e-11. Report convergence, boundary hits,
rank and scaled-Jacobian condition; unsupported fits are unavailable rather than
invented zero response. Fits with negative/noisy recovered flux are not dropped.
Report recovered/input flux, response relative to fixed-G0 reference, attenuation
or amplification, spectral-index error and TRAIN template-weighted coverage loss.

WSClean is absent on the host and in the pinned runtime image (read-only checks
before freeze). No dirty or deconvolved image is measured in this experiment.
Known-template visibility recovery is not source discovery, morphology recovery
or imaging validation; those checks remain pending.

## Interface and reproduction

`rangtoy.flagging_signal.run(run_dir, prepared_dir, iterations=50,
max_fraction=.02, include_native=False, mild_strategy=None)`.
The root launches measurements after the module/recipe/configuration freeze.

```sh
bash tools/flagging/run-signal.sh outputs/tv-signal-new outputs/tv-flagging-actions-01
```

Stimela2 recipe `recipes/tv-flagging-signal.yaml`; fresh run and log namespaces,
read-only source checkout, network-disabled container, isolated cache and8GiB
disk reserve. Source namespace preflight happens before creating logs/caches.
The root curates compact measured results after execution; do not overwrite
published observation or previous output artifacts.

## Pre-measurement validation

16 targeted tests pass: independent Gaussian/Fourier reference, full-Jones inverse
and native-weight propagation, common-unitary gauge invariance, singular/support
handling, exact joint source/spectrum recovery, retained negative response,
unidentifiable fits, truth/test-independent selection and invalid-call namespace
protection. Ruff lint/format, shell syntax and whitespace checks pass.
`outputs/tv-signal-recipe-dry-02-logs/` records successful offline Stimela2
prevalidation without QuartiCal solves. The first startup attempt exposed the
macOS Bash3.2 empty-array/set-u behavior; fixed by nonempty default recipe arguments,
retaining its fresh logs and never touching source observations.

Read-only executable checks found no WSClean on host or in the existing pinned
`rang-flagging-parallel:local` runtime. Image absence is explicit and no image
metric is substituted. Parent/root owns actual bounded concurrent execution and
compact result curation after this source/configuration freeze.
