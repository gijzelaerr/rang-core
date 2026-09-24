# Full-Jones local deletion-response surrogate

Implemented numerical experiment; retrospective real-action accuracy is pending.
The [checked protocol](flagging-reportable.md) froze the method before this
implementation. Seven completed balanced cases provide123 actual QuartiCal
counterfactual outcomes, all from one four-antenna MeerKAT L-band pointing scan.
The existing seed101/103/105 groups remain development TRAIN/validation/test-case
groups, not independent observations. No settings are tuned to the seed105 win.

## Physics and coordinates

For each native two-integration ×32-channel gain bin, `V=Gp M Gq^H` has32 real
parameters: antenna-major, row-majorXX/XY/YX/YY, adjacent real/imaginary entries.
The eight visibility rows use adjacent real/imaginary entries too. For a real
matrix basisE, p derivatives are `E M Gq^H` and `i E M Gq^H`; q derivatives are
`Gp M E^T` and `-i Gp M E^T`. The q imaginary sign is essential.

Rust accumulates `H=Re(J^H W J)` and `b=Re(J^H W r)` from DATA/model/actual
baseline gains and native four-correlation weights on TRAIN only. Each real and
imaginary output shares its original correlation weight; no weight replacement,
whitening normalization or holdout curvature is introduced. Common factors2 in
the least-squares gradient/Hessian cancel. This is a GN Hessian approximation,
not the exact residual-dependent nonlinear Hessian.

Four common right-U(2) gauge tangents `Ga*A` use skew-Hermitian bases: imaginary
XX/YY diagonals, real antisymmetric off-diagonals and imaginary symmetric
off-diagonals. Reorthogonalized Gram–Schmidt constructs Q on active stations only;
`P=I-QQ^T` defines the horizontal response. Scalar unpolarized models are required.
Unsupported station columns are inactive, not counted as missing global rank.
Two active stations retain additionalGL(2) ambiguities and must abstain.

Removed samples give `Hk=H-Hremoved`, `bk=b-bremoved`. The forecast is the
regularized kept-data GN step MINUS the same full-data GN step, both at the actual
baseline gains. This anchor makes no deletion predict exactly zero even when the
finite-iteration QuartiCal baseline is not stationary. At a stationary baseline
it reduces to the usual deletion-score influence response.

The full projected largest eigenvalue fixes damping1e-6 and spectral rank
cutoff1e-10. Expected identifiable rank is `8*Nactive-4`; retained rank loss,
non-PSD/asymmetric curvature, gauge-null/eigensystem failures and relative
station steps above0.1 produce missing forecasts, never clipped updates or zero
labels. Predicted gains are re-polar-gauged before Rust full2×2 Frobenius TV using
the baseline scale, coordinates and exact finite baseline edge support.

Complex calibration Jacobians and influence-based calibration are established
methods, not novelty here. See [Smirnov & Tasse2015](https://arxiv.org/abs/1502.06974)
and the prior-art links in the frozen protocol.

## Freeze and evaluation boundaries

The runner writes exclusive runtime/native-library/source receipts and settings
before forecasting. All123 TRAIN gain responses and canonical/raw gain caches
are serialized before validation DATA scores their objective. All validation
forecasts are then serialized before actual action outcome records are opened.
Only TRAIN101 labels fit the frozen mean/residual-score linear controls; there is
no validation tuning. No injection truth file is decoded, and no TEST visibility
or TEST-loss value is used. Reading a state NPZ loads its DATA bytes, but numeric
operations use TRAIN or subsequently validation cells only. Provenance hashing
may read label-file bytes without decoding them into predictions.

Report full objective benefit and benefit with the known `2*f` flag penalty
removed, alongside the `-2*f` no-response control. Missing predictions retain
their reasons and coverage. Error comparisons use identical covered labels;
the known-cost control also retains an all-label diagnostic. Canonical gain
change errors are computed only after forecasts freeze. One-slot physics,
residual-first and seeded-random rankings are retrospective within the previously
solved candidate union, not newly measured whole-family policies. Any suggested
action still needs genuine guarded re-solve confirmation before flagging.

The new derived-only namespace is `outputs/tv-influence-20260924-01`. Source MS,
original Observatory flags/rows, DATA/model and all native weight/SIGMA columns
are read-only; this experiment writes no MS/flags and performs no new QuartiCal
solve. A fresh destination beneath outputs is mandatory, with8GiB free reserve
plus256MiB prospective allowance before writes. Subsequent exclusive writes check
logical regular-file bytes below256MiB and reserve availability; symlinks are
rejected. This is a checked reservation/logical-byte budget, not an OS quota.
Whole source-tree and runtime receipts must agree at completion.

## Interfaces and checks

`jones_jacobian(gp,gq,model)` returns8×16 local real derivatives.
`training_normals(gains,models,residuals,weights,p,q,bin_ids)` returns native-bin
32×32 curvature,32D scores and sample counts. `anchored_response(...)` returns
delta/diagnostics or a structured abstention. `run(run_dir,source_dir)` stages
TRAIN freezes, validation freezes, post-forecast comparisons and a result JSON.
Root supplies the Stimela recipe/wrapper and schedules actual execution.

Three new Rust and14 Python/native tests pass: general-model finite differences,
q-conjugate sign, exact weighted normal equations, independent NumPy eigen
reference, baseline-drift anchoring, inactive-station rank handling, U(2)/GL(2)
guards, trust refusal, left receiver-phase equivariance, heldout-value invariance
of TRAIN curvature and resource preflight checks. These are numerical/software
checks, not measured real-action superiority. Rust-backed walltimes include FFI
orchestration; comparison with emulated QuartiCal cannot establish a fair speedup.
No independent transfer, imaging, robust RFI classification or SOTA claim.

First measured retrospective replay uses implementation `8836e85` at
`outputs/tv-influence-20260924-host-01`; see
[compact outcomes](results/gain-tv-influence.json),
[independent verification](flagging-influence-verification.md) and
[findings synthesis](flagging-findings.md). A later metadata-only change records
host Python/NumPy/platform versions before future runs. The original raw config,
module/native hashes and its audit remain unchanged; versions observed at
curation are explicitly labelled, not presented as a pre-run freeze.
