# Smooth receiver-phase controls for gain-TV specificity

Frozen2026-09-24 before replay; seven balanced development cases, one observation.
Per native gainbin define diagonal unit-modulusD_a, same phase for both receptors:
`2*pi*delay_a*(frequency-referenceHz)+drift_a*(time-time0)/timeSpan`.
Reference1283.791015625MHz; span is actual first-to-last gaincentre span (zero
drift for one-time grid). Referenceantenna0 hasD0=I. Frozen settings:

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../history/README.md); this text keeps the paths it was written
with.

| Pattern | Delay ns, antennas0–3 | Total drift rad, antennas0–3 |
| --- | --- | --- |
| Identity | 0,0,0,0 | 0,0,0,0 |
| Smooth frequency | 0,3,6,9 | 0,0,0,0 |
| Smooth time | 0,0,0,0 | 0,0.2,-0.2,0.4 |
| Both | 0,3,6,9 | 0,0.2,-0.2,0.4 |

UseG'=DG, DATA'=Dp DATA Dq^H, scalar-unpolarizedMODEL unchanged. Phase is
constant inside existing gainbins: grid-matched control, not a continuous
high-resolution hardware simulation. Predictions/residuals receive identical
per-correlation phases, preserving every native-weighted squared residual and
RFI support/amplitude. Transformations in memory only; original FLAGS/DATA/
weights/model never written. No truth decoded/used.

Re-polar-gauge, nativeRustfull2x2 TV, originalscale and baselineedge support.
Recompute objectives/no-change on OLD fixed six-slot counterfactual actionsets.
Separately recompute TRAIN residual/TV ranks using the original whole family;
newly reranked masks with unavailable QC outcomes are missing, never selected.
Verify actual baseline/candidate predictions and TRAIN/VAL/TEST weightedloss
invariance; TEST is only invariance/evaluation, never selection. Identity must
reproduce archive within floating tolerance. Report allTV/guard/rank/sign changes,
source/result digests before/after and new source/image receipts/checkpoints.

This tests specificity of high first-orderTV to RFI instability. It does NOT
prove physicalTV should be receiverphase invariant or estimated trend removal
is safe. Known transforms are unavailable to a deployable selector; future
trend/curvature guidance requires new support/domain/noise controls.
Fresh`outputs/tv-equivariance-20260924-01`, checked≤256MiB and8GiB globalreserve;
130 existing gainproducts perpattern, zeroMS copies/newQC in first diagnostic.

Implementation entry `rangtoy.flagging_equivariance.run(run_dir,source_dir)`;
Stimela2 [recipe](../recipes/tv-flagging-equivariance.yaml), namespace-protected
offline wrapper `bash tools/flagging/run-equivariance.sh outputs/fresh-run
outputs/completed-suite`. Frozen source/native-library/module hashes are
checked again after the complete replay. Fourteen targeted tests cover
full-matrix prediction/residual invariance, legitimate smooth-phase TV,
TEST-value objective independence and fresh/capped checkpoint writes.
Unit tests alone imply no measured policy success; the first actual replay
is routed below.

Measured first replay and independent audit use implementation `8836e85`:
`outputs/tv-equivariance-20260924-host-01`, compact
[gain-tv-equivariance.json](results/gain-tv-equivariance.json), independent
[verification](flagging-equivariance-verification.md). A later metadata-only
fix splits an ambiguous combined no-write/no-decode field and records host
versions before future runs. Numeric DATA/model/weights ARE decoded; injection
truth is not. Old raw configuration/hashes are retained unchanged, with an
explicit wording correction in the compact archive. This is not a numerical
rerun or additional independent evidence.
