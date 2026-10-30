# TRAIN-supported trend guidance

Premeasurement design2026-09-24, implementing the frozen
[five-track plan](flagging-next-results.md). No new replay outcome is claimed at
this checkpoint. Existing actual QuartiCal full2×2 gains are used read-only.

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../history/README.md); this text keeps the paths it was written
with.

The Rust kernel estimates a scalar linear phase slope per station and axis:
median adjacent wrapped half-determinant increments divided by original native
time/frequency distances. Only valid TRAIN-supported gain bins contribute.
Time/frequency fits need2/4 edges; gaps exceeding3 median spacings and near-zero
normalized determinants are excluded. Missing fits stay missing, never filled.
The required assumption is absolute scalar step<pi/2. Wrapped determinants
alone cannot certify it; this is not a physical Jones-component decomposition.

Remove the same fitted scalar phase from all four complex matrix entries before
computing supplementary TV maps. The primary polar-gauged full-Jones TV objective
is unchanged. Counterfactual guidance uses baseline-frozen slopes; the prospective
family admits identical whole TRAIN rectangles and two slots per geometry group.
All-four-entry kernels and original coordinate-aware edge definitions are retained.

Frozen read-only diagnostic:7 historical baselines×4 predefined legitimate scalar
phase patterns=28 replays. Fit the estimator from each transformed baseline,
without supplying the known added phase to the estimator. Report raw/detrended TV,
slopes, supported edges and whole-mask ranking hashes. Never solve transformed
DATA, interpolate unsupported bins, write flags, decode injection truth or score
TEST. Estimator equivariance on saved gains does not prove finite-iteration
QuartiCal solver invariance or arbitrary phase/beam invariance.

Fresh output cap256MiB allocated blocks, checked8GiB free-space reserve; not an
OS quota. Source/runtime digests checked at completion. The old historical trees
and gain chunks remain intact. The [Stimela2 recipe](../recipes/tv-flagging-trend.yaml)
is a separate reproducible read-only stage.

Initial verification:2 Rust numerical tests and6 Python binding/coordinate/
missing-fit/heldout-poison/equivariance tests pass before any replay measurement.

## Measured replay2026-09-24

All28 frozen replays completed in140seconds in the final Linux image. All28
station trend fits are available; source/runtime audits pass. Across21 added
smooth-phase comparisons, raw-TV six-mask rankings change17 times, detrended
rankings0 times and residual rankings0 times. Clean rawTV changes from0.1474368701
to0.2774970166; detrended guidanceTV remains0.1472178101 within floating-point
roundoff. Primary solved-gain TV is not replaced. No new QC solve or flag write.

Exact raw projection: [archive](results/gain-tv-next-trend.json), raw namespace
`outputs/tv-next-20260924-01/experiments/trend`. Independent artifact/ranking audit
passes562/562 checks ([report](flagging-next-trend-verification.md)). This demonstrates robustness
to the fixed unaliased scalar-linear-phase family on saved gains, not universal
instrument/RFI separation, actual solver invariance or a deployed policy win.
