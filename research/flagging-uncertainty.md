# Gain-TV noise and legitimate-structure controls

Frozen protocol, 2026-09-24, before numerical control measurements.
Implemented controls are synthetic gain-only diagnostics, not uncertainty
estimates from actual QuartiCal solutions and not proof of an RFI classifier.
The requested primary objective remains existing native Rust full complex
2×2 gain TV. Detrended TV and curvature are guidance only.

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../history/README.md); this text keeps the paths it was written
with.

Two grids cover the same 112 s and 1070–1497.791015625 MHz interval:
4×32 and 8×64 time/frequency bins, four antennas, fixed gain scale 1.
All norm evaluations use `rangtoy.flagging.gain_tv`, including every complex
Jones entry. Polar-gauge alignment requires an explicitly scalar-unpolarized
model. Incomplete gain/edge support, singular reference gains and coordinate
gaps are refused; no support interpolation or edge disappearance is rewarded.

Three separately calibrated no-RFI families are frozen:

- Flat unit diagonal gains.
- Smooth physical gains: antenna delays [0,3,6,9] ns, linear delay changes
  [0,0.3,-0.3,0.5] ns across normalized time, and voltage log-amplitude
  slopes [0,0.04,-0.04,0.08]. Phase is `2π*(frequency-midfrequency)*delay`.
- Rapid but smooth physical gains: twice the smooth delays, delay changes
  and log-amplitude slopes. These are legitimate no-RFI controls.

Independent circular complex gain perturbations have RMS modulus 0.005 on
all four entries. Seeds 101–110 calibrate, 111–115 validate, and 116–120
evaluate; none of these are the transferable learner's case-group split.
A separate seed stream (`seed+1000000`) selects an 80% TRAIN gain-cell mask.
Statistics inspect only that mask. These masks are not real visibility splits.
Calibration is separate for every grid and physical family, never pooled
across different legitimate trends.

A fixed four-column [1,time,frequency,time×frequency] fit to log-amplitude
and unwrapped phase defines the smooth trend. Entries below 1% of median
diagonal amplitude are treated as absent in that trend; they remain in all
norm calculations. This small bounded fit is orchestration, not a replacement
TV kernel. The trend is descriptive, not a fitted sky or general gain model.
Detrended TV uses the native kernel on gain-minus-trend. Curvature guidance
uses the same kernel on each axis's first differences and averages their
incident maps. Grid dependence is retained explicitly.

Per-grid/per-family no-RFI TRAIN maps provide median, MAD×1.4826 (floor
1e-6), and a fixed 95th-percentile threshold for raw, detrended and curvature
TV. Excess is `max((map-q95)/scale,0)`, capped at 5. If curvature is supplied,
the minimum of detrended and curvature excess is used. The 95th percentile
is an empirical descriptive threshold, not a promised false-positive rate or
confidence interval. Validation/test never tune it.

Evaluation-only stress controls on seeds 116–120: tenfold gain-noise RMS
0.05, or a station-1 phase jump 0.75 rad plus voltage amplitude factor 1.15
from the midpoint onward. Each stress has a paired no-RFI seed/family/grid.
These are perturbed gains, not injected visibility RFI. Report all controls,
raw primary TV, detrended/curvature summaries, positive-excess fractions,
support/refusal, and paired effects. Do not choose a flag mask from these tests.

API: `gain_evidence(gains, valid, times, frequencies, scale=1,
unpolarized=True)`; `calibrate_guidance(controls, grid_key=..., trend_key=...)`;
`excess_guidance(state, guidance, calibration, grid_key=..., trend_key=...,
curvature=None, evidence_kind="detrended_tv")`. The last returns a map zero
outside TRAIN plus an audit. Applying it to real gains requires matched
independently established no-RFI calibration and known trend/domain; absent
those, refusal is preferable to pretending these controls quantify real noise.

Stimela2 entry: [tv-flagging-uncertainty.yaml](../recipes/tv-flagging-uncertainty.yaml).
Run outputs and exclusive original-gain backups belong in fresh ignored
directories. No Measurement Set, Observatory flag, DATA or native weight is
written by this workstream. Measured findings will be recorded separately;
old tiny within-scan objective wins do not establish significance.

## Measured gain-only pilot

Completed `outputs/tv-uncertainty-controls-01/result.json`: 180 controls,
60 no-RFI calibration, 30 no-RFI validation, 30 no-RFI test and 60 paired
test-only perturbations. Every input gain array has an exclusive pre-analysis
NPZ backup; the 180 per-control checkpoints and frozen calibrations survive.
All support/gauge audits pass. Code SHA256
`e84d18b495cbd4d7a2b6ab87a1d8439f913d16f2bfb616fc1501b209dfe61c42`;
native macOS library SHA256
`e587bafb33d499c8a7026b3d0b821c79db24d6242407890c75c66aa1498d9eb6`.
No QuartiCal solves or Measurement Set writes were performed in this pilot.

Test-seed mean primary TV for flat/smooth/rapid physical gains is
0.02965/0.64223/1.22441 on 4×32 and 0.02986/0.31762/0.62017 on 8×64.
Thus legitimate rapid smooth gains have more raw TV than the flat tenfold-noise
control (0.29672/0.29859), and physical TV depends strongly on grid size.
Detrended no-RFI TV stays around 0.0296–0.0299. This validates the numerical
control hypothesis that high first-order TV alone is not nonsmoothness or RFI.

Combined detrended/curvature excess is positive on a mean 3.18–4.21% of
TRAIN cells in the six no-RFI test grid/family combinations; 3.50–4.28% in
validation. The paired tenfold-noise stress has positive excess on all TRAIN
cells; midpoint station-jump controls have 17.33–27.61% positive. These are
descriptive effects under exactly matched gain-only trends and known noise,
not visibility-RFI detection rates, calibrated confidence or real-data success.
Small off-diagonal entries and unrestricted physical/sky mismatch remain
important failure domains. No flags were recommended from these controls.

Targeted verification at this step: 21 tests across uncertainty and transfer,
Ruff lint/format. Later integrated checks/runs must record their own counts.
