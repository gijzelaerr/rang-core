# Next research toward reliable TV-guided flagging

Updated 2026-09-24 after the completed five-track experiment. Proposed hypotheses below
are not established novelty. Keep the original user objective: MeerKAT L-band,
QuartiCal full complex 2×2 gains, TV-map guidance, original Observatory flags,
recoverable backups and Stimela2 execution.

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../history/README.md); this text keeps the paths it was written
with.

## Next discriminating work after the concurrent measurements

[All five requested tracks](flagging-concurrent.md) now have measured archives.
The balanced ranker wins one seed, the fitted model still chooses no-change,
legitimate delay gains can have high rawTV, and paired omitted-source recovery
has severe attenuation/bound-hit spectra. The new61-antenna numeric tiles lack
positive native cross-hand spectral weights. Do not respond by enlarging a model
or silently changing flags/weights/fit bounds on these same test outcomes.

1. Freeze a **science-preservation and identifiability** experiment before new
   outcomes. Compare complete versus omitted injected sky, justified gain grids
   and physical beam/pointing controls. Diagnose bound-hit spectral fits rather
   than treating their flux fractions as validated astrophysical recovery.
   Actual fixed-setting WSClean images require a verified executable and must
   remain separate from known-template visibility fits. Keep TV as requested,
   but require independent prediction/support/signal safeguards for acceptance.
2. Find a **representative, natively supported** public MeerKAT L-band input.
   Check original polarization/weight/flag/model provenance and safe native-MS
   metadata before bounded acquisition. The current two tiles reject only our
   strict four-correlation protocol; a partial-correlation full-Jones/gauge
   protocol requires separately justified frozen assumptions, not row-weight
   substitution. Recheck actual peak storage: the suite used6.9GiB against a
   6GiB forecast, with8GiB reserve retained and no cleanup authorized.
3. Test **real-solution excess-TV guidance** against residual and random rankings
   at identical geometry/solve budgets on new groups. Synthetic trend/noise
   thresholds cannot be imported into real gain maps without domain/uncertainty
   checks. Quantify influence/local-response savings only after numerical
   confirmation; report known flag-volume cost separately from learned benefit.
4. Once those prerequisites pass, split by **independent observation**, confirm
   learned nominations prospectively with actual full-Jones solves, and measure
   matched signal/image accuracy and native compute cost against relevant mature
   MAD/AOFlagger/Tricolour strategies. Existing CARACAL controls are useful
   verification, not a full science-pipeline or state-of-the-art victory.

These are proposals, not newly implemented or measured claims. Original flags,
copied-MS writes/backups and held-out/truth separation remain non-negotiable.

## Completed earlier experiment: structured actions

Verification prerequisite: [inspect CARACAL's full shipped strategies and
worker semantics](flagging-caracal.md), not just the reduced kernel comparator.
Pinned source inspection and four native full-strategy measurements are complete.

Measured motivation: the strong time-burst injection-only oracle improves the
current guarded objective, yet pointwise thresholds and a tiny local-action
ridge learner choose no-change. Test whether the proposal family is the limiting
factor before fitting a larger model.

Freeze multiscale rectangles before running: one or all integration times,
16/32/64/128-channel frequency windows, global-baseline, antenna-star and
single-baseline grouping. Score only training residual evidence; compare
residual-only and TV-conditioned rankings at identical shape/search budgets.
Propose whole eligible training rectangles, never fill held-out/Observatory
holes. Reject oversized proposals rather than trim their morphology.
Use actual QuartiCal re-solves with frozen baseline TV scale/support, existing
flag penalty, ≤2% additions and ≤1% validation degradation. Include no-change.
Test data and exact injection masks never choose an action or parameter.

Frozen before the first run: robust whitened training residual score
`mean(max(z,0))`; TV-conditioned score
`mean(max(z,0)*(1+clip(TV/median_positive_training_TV,0,5)))`.
Each ranking gets its top eight distinct admissible masks, stable hash ties,
and the same minimum eight samples. Shared masks reuse exactly one full solve;
separate objective selection includes no-change and never combines rectangles.
The pure generator confirms 23,329 unique masks on both first inputs. This is
implemented counterfactual selection, not a fitted transfer model. The first
seven actual [structured recipe](../recipes/tv-flagging-structured.yaml) runs
completed. [Measured report](flagging-structured.md) and
[archive](results/gain-tv-structured.json): 101 solves; all112ranked slots are
single-baseline actions despite broader available geometry. Two tiny objective
wins, no reliable injection recovery or robust TV-guidance advantage. This
experiment is complete; new ranking/aggregation settings must be frozen before
new seeds/scans, not tuned to these held-out results.

First diagnostics: the unmodified prepared scan and archived strong time burst;
then other frozen injection morphologies if capacity allows. Report all rejected
and negative results, distinct masks/solve counts, TV, fixed clean validation/test
MSE, added volume and post-selection known-injection recovery. Reusing this scan
does not establish independent-observation transfer. An objective improvement
without better test prediction/signal fidelity is not a scientific success.

## Other discriminating research questions

1. **Separate genuine gain structure from solution noise.** Use paired clean
   gain solutions, fixed-support comparisons, inverse-variance sampling controls
   and multiple gain grids. Estimate uncertainty of TV changes instead of
   asserting high TV always means RFI. A standardized excess-TV statistic could
   help only if calibrated on controls without injection/test-label leakage.
   Solution intervals already trade gain variability, noise, model error and RFI:
   [Sob et al. 2021](https://arxiv.org/abs/2103.12508).
   First-order TV measures accumulated variation, not nonsmoothness alone:
   even smooth delay-like complex phases can have large TV. Retain the requested
   full-gain TV objective, but test noise-aware excess-TV/trend or curvature
   guidance against genuine smooth/rapid-gain no-RFI controls before treating a
   high-TV map as flagging evidence.
2. **Preserve science signals, not just fit quality.** Inject held-out compact,
   extended and spectral signals before paired flagging/calibration; measure
   flux, spectrum, astrometry and morphology recovery at identical imaging
   settings. Test residual outliers from incomplete sky and genuine rapid gains
   as no-RFI controls. Real-data image improvement remains unmeasured.
3. **Make counterfactual training affordable.** Rank actions with an influence
   or local linear-response surrogate, confirm winners with full-Jones solves,
   and compare equal solve budgets against random actions, residual-only ranking,
   native MAD and full AOFlagger/Tricolour strategies. Influence-informed learning
   in calibration is established, not our invention:
   [Yatawatta & Avruch 2021](https://arxiv.org/abs/2102.03200).
4. **Test transfer on representative L-band data.** Find publicly accessible
   visibilities with normal calibrator/science coverage and explicit access/model
   provenance. Split by observation or scan, not neighboring samples; audit SNR,
   gain-bin support, polarization basis, sky adequacy and original flag origin.
   Acquisition/processing must fit disk capacity; do not silently discard backups.
   A [public normal primary-calibrator candidate](flagging-public-data.md) now has
   verified numeric metadata: 61 participants, eight scans and full L-band.
   [Bounded acquisition/inspection](flagging-public-ingestion.md) now complete:
   two61-antenna pilots have identically zero cross-hand spectral weights and
   no strict four-correlation eligible cells. Conversion/calibration/independent
   transfer remain unmeasured; no weights/flags are changed to force acceptance.
5. **Identify when flagging is the wrong action.** Include robust likelihoods
   and, for parameterizable moving RFI, subtraction as controls. TABASCAL reports
   simulated MeerKAT gains from joint modeling rather than discarding data;
   its single-channel satellite setting does not validate our broad-band policy:
   [Finlay et al., revised August2026](https://arxiv.org/html/2502.00106).
6. **Cross-check gain TV with gain-insensitive closure quantities.** Full-matrix
   closure traces cancel station-based gain/leakage terms under their assumptions:
   [Broderick & Pesce 2020](https://arxiv.org/abs/2010.00612),
   [Samuel, Nityananda & Thyagarajan 2022](https://arxiv.org/abs/2108.11400).
   Proposed diagnostic: compare noise-aware closure/model mismatch with TV maps
   to distinguish genuine rapid station gains from baseline corruption. This is
   an inference, not an implemented RFI classifier. Sky errors, thermal noise
   and near-singular visibility matrices also affect closure diagnostics; test
   those no-RFI controls and require conditioning/support guards first.

## Prior-art boundaries and possible contribution

Multiscale RFI morphology is not new:
[Offringa et al. 2012](https://arxiv.org/abs/1201.3364) defines the SIR operator.
Joint flagging/calibration pipelines are not new:
[FLAGCAL](https://arxiv.org/abs/1111.6415).
Recent lightweight morphology-aware neural segmentation with explicit signal
preservation is also proposed, but for filterbank/pulsar data, not our complex
interferometric gains:
[MARS, August2026](https://arxiv.org/abs/2608.05546).

The research candidate is **calibration-aware choice of where to add or remove
only non-Observatory flags, using measurable full-Jones TV response and explicit
quality/support/cost safeguards**. This is a hypothesis, not a novelty finding.
Require higher calibration/imaging/signal quality at comparable cost, or
comparable quality at materially lower runtime/resources than relevant mature
methods. Retain negative results; an oracle opportunity or toy-control win alone
does not satisfy that bar.
