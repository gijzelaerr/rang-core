# Reportable MeerKAT L-band flagging findings

Measured follow-up on 2026-09-24: surrogate/phase checkpoint `8836e85`,
precision-corrected calibration-response checkpoint `1f53a17`.
These are reproducible prototype mechanisms and limitations, not a new
state-of-the-art flagger. The seven development cases reuse one four-antenna
MeerKAT L-band pointing scan. Every original/received Observatory flag and
native DATA/weight/SIGMA column remains authoritative and protected.

## Latest prospective, specificity and image-domain evidence

The [five-track measured report](flagging-next-summary.md) now extends these
earlier results: estimated TRAIN scalar-trend removal preserves all21added-phase
rank comparisons; a frozen physical forecast matches measured shortlist-union
choices in all3fresh cases; corrected known-family dirty-image response is
49.17%/77.57% with omitted sky versus99.69%/98.65% with complete diagnostic sky.
All original Observatory flags/native columns and recoverable backups remain
protected. The single56-cell objective win is not a certified science mask.

The absolute TRAIN signal guard abstains at one two-cell underidentified bin.
A [separate complete rank survey](flagging-next-gain-support.md) shows that
99.997287% of TRAINcells meet its unchanged rank criterion; dropping the two
remaining cells posthoc is not authorized and identification would not by
itself solve signal absorption. Bounded provenance recovers one CASA split
but leaves public native noise/model gates unresolved. Both initial CLI failure
and second-run double-spectrum semantic failure remain explicitly retained;
fresh corrected03reuses saved gains, with no additional calibration solves.

This is promising prototype evidence for conservative physical triage plus
actual QC confirmation and science/support safeguards, not mature-method
quality/cost novelty. The final [Stimela2 research strategy](../recipes/tv-flagging-next.yaml)
is an isolated five-track experiment, not a production-certified flag exporter.

## A local physical surrogate predicts more than the flag cost

The TRAIN-only full-Jones deletion-response model forecasts the actual
QuartiCal TV/validation objective without a new calibration solve. It projects
out the common right-U(2) gauge and anchors against baseline nonstationarity.
TRAIN responses freeze before validation scoring, and all forecasts freeze
before retrospective action-label evaluation. See the
[method](flagging-influence.md) and [complete compact outcomes](results/gain-tv-influence.json).

| Development case group | Covered / labels | Physics-response RMSE | Known flag-cost-only RMSE |
| --- | ---: | ---: | ---: |
| Uninjected | 18 / 18 | 0.00009250 | 0.00041953 |
| Seed101, TRAIN | 34 / 35 | 0.00009383 | 0.00049656 |
| Seed103, validation | 33 / 34 | 0.00012129 | 0.00072908 |
| Seed105, held-out case group | 35 / 36 | 0.00008569 | 0.00062254 |

The held-out-case matched-coverage RMSE ratio is 7.26, and remains so after
removing the known flag penalty. This is not an independent-observation test.
Canonical predicted gain changes have median relative error 8.32% and median
cosine 0.99690 versus actual counterfactual gains. All three predicted-positive
actions are actually beneficial within these 120 covered outcomes. Do not
turn that finite retrospective observation into a precision/confidence claim.

The frozen 0.1 station-step trust guard abstains once in each strong time-burst
case. It rejects the best seed105 action, whose actual benefit is 0.00076859.
The physics recommendation instead achieves 0.00034731 and regret 0.00042128;
the other six cases retain no change. Missing predictions are not zero labels,
and the threshold is not relaxed after seeing this result. There is no fair
native-runtime benchmark, deployment, imaging or novelty claim.

## First-order TV is not specific to RFI instability

Grid-matched, smooth unit-modulus receiver phases transform actual saved
full-Jones gains and DATA in memory while leaving MODEL and native weights
unchanged. Across 520 replays, predictions transform equivariantly and residual
magnitudes remain unchanged: maximum
prediction-equivariance error 5.96e-15Jy, maximum native-weighted cell-MSE
change 3.41e-13. No source MS or flags are written and no injection truth is used.

On the clean case, adding the frozen delay-plus-drift raises polar-gauge TV
from 0.14744 to 0.27750, a factor 1.88. On the original fixed candidate sets,
five decisions change, all in time-burst seed105. Every nonidentity phase
pattern removes its previous TV-ranked improvement; residual choices also
change under frequency or combined phases. TV TRAIN rankings change in all
seven frequency/combined cases and three time-only cases, whereas residual
and seeded-random rankings remain unchanged. Newly ranked unmeasured masks
stay unknown and are never selected. The tiny combined-phase residual benefit
is not a robust win. Full evidence:
[compact replay](results/gain-tv-equivariance.json),
[independent verification](flagging-equivariance-verification.md).

Physical TV is not required to be receiver-phase invariant. The narrower
finding is that high first-order TV, even after the common gauge is fixed,
cannot by itself distinguish legitimate instrumental structure from RFI.
This is an exact saved-gain transformation, not a rerun of finite-iteration
QuartiCal from identity initialization on transformed DATA; solver equivariance
has not been measured.
At this earlier checkpoint estimated trend removal required new frozen work;
that [TRAIN-estimated specificity experiment](flagging-next-trend-verification.md)
now completes. The known phases in the earlier diagnostic are not used by its
estimator. Arbitrary Jones/beam and finite-iteration solver invariance remain
unmeasured.

## Native data support and noise provenance are separate gates

The acquired 61-antenna public calibrator has zero native XY/YX spectral weights
but positive SIGMA_SPECTRUM in all four products. QuartiCal can explicitly use
the original sigma column without overwriting stored weights. This is a possible
new protocol, not a validated noise choice. Native weight/sigma products and
adjacent-channel scales are inconsistent with one simple shared convention;
only 60 antennas have received-unflagged cross support, with native ID21
unsupported. No flags are restored or unit row weights substituted.

Parallel-hand-only scalar-sky data leave independent row-U(2) gauges, beyond
the common right-U(2) used by the present full-Jones TV metric. A numerical
counterexample changes canonical TV without changing either measured hand.
See [native support and gauge review](flagging-supported-data.md), its
[reproducible diagnostics](../examples/diagnose_native_support.py), and the
[bounded textual provenance design](flagging-supported-provenance-plan.md).
That plan was design-only at this checkpoint; the later
[bounded inert-text extraction](flagging-next-provenance-verification.md)
now completes. No object unpickling/native MS conversion has been performed;
DATA/noise provenance remains insufficient for the proposed sigma protocol.

## A smoother solve can still absorb a real sky perturbation

Ten signed-source fine/coarse and complete/omitted-sky QuartiCal controls now
complete on the fresh precision-corrected run. All9,169 TEST samples remain
supported, without any added flags. Fine-grid omitted-sky calibration preserves
51.00–51.30% of the compact and74.15–74.19% of the extended paired response.
Including the known sources in the diagnostic sky gives99.95–99.96% and
98.92%, respectively. The positive omitted fine control also lowers TV.

Direct correction preserves the positive60/120mJy perturbations, but gain
adaptation absorbs about29.5/31.0mJy when correcting the SAME original DATA.
Total=direct+adaptation closes within8.253e-15Jy. Coarsening improves omitted
response only to52.4–52.7%/76.2%, while clean validation error is25.7% worse,
despite much lower TV. This identifies a sky/gain-flexibility confound, not a
flagging win or blind astrophysical flux measurement. The complete control
uses truth, and positions/extents/spectra are known in evaluation; no images
or confidence intervals are claimed. [Protocol and measured table](flagging-response.md),
[complete compact evidence](results/gain-tv-response.json),
[independent numerical/preservation verification](flagging-response-verification.md).

The first failed run is retained untouched and not exportable;
[precision diagnosis](flagging-response-precision.md) records the narrow fix.
Native calibration inputs and settings were unchanged in the fresh rerun.
Ten failed plus ten fresh solves are20 actual invocations of ten frozen
physical controls, not20 independent realizations.

## Next decision

The useful next strategy is a conservative TRAIN-only physical surrogate for
candidate triage, actual guarded QuartiCal re-solves for confirmation, and
signal/support/prediction safeguards alongside full-Jones TV. Investigate
physical-trend specificity and independently supported data before training
or deploying a broad policy. Existing CARACAL strategies remain relevant
verification controls; no matched mature-method quality/cost win is established.

Executable Stimela2 entries:
[influence](../recipes/tv-flagging-influence.yaml),
[phase specificity](../recipes/tv-flagging-equivariance.yaml),
[calibration response](../recipes/tv-flagging-response.yaml).
See [STATE.md](STATE.md) for exact run paths, failures, backups and checked pushes.
