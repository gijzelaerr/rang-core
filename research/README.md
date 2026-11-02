# Research index

This index routes collaborators to the evidence; it is not a novelty claim.
Each entry is one report and its verdict, newest first within a section.

## Start here

- [STATE.md](STATE.md): the current status and the log of recent work; [STATE-history.md](STATE-history.md) holds the entries before 2026-10-29.
- [big-plan.md](big-plan.md): the plan, the standing decisions and the user items.
- [meerkat-scope.md](meerkat-scope.md): the MeerKAT research scope.
- [AGENTS.md](../AGENTS.md): working conventions and Git attribution. [tool-timings.md](tool-timings.md): every tool run, wall-timed.

**The rename** ([p12-rename.md](p12-rename.md)). The project, repository and
PyPI distribution are **rang-core** and the Python package is **`rang`** (`import
rang`, extension `rang._core`, `python/rang/`); the command line stays
`rang-core`. Notes, receipts, `history/` and `research/results/` written before
2026-10-30 keep the old package name `rangtoy` (`python/rangtoy/…`,
`rangtoy.core_cli`, `import rangtoy`): read it as `rang` for the current tree.
CLI receipts are `rang.receipt` version 2 from then on (key
`environment.rang_core`, was `environment.rangtoy`), version 3 since
[W4-1](w4-1-receipts.md).

## The core port and simplification

- [W4-2 and W4-7, boundary checks](w4-2-boundaries.md): sized, C-order and overflow checks on every extension binding; `flag_rows` lengths; span-row coverage; zarr order and dtype checks and the out-of-order fallback in `core_fetch`; the `gpu` feature in `rang-core check`.
- [W4 final review](w4-review.md): no archived result is affected and the kernels are bit-identical across thread counts; 17 findings (1 high, the solver options missing from receipts; 8 medium; 8 low); v0.1.0 is go after W4-1, W4-3 and W4-5.
- [W4-3, closure and flux-standard kernels in the extension](w4-3-kernels.md): no kernel call runs Cargo; standalone builders and dead fallbacks deleted; byte-identical, and a wheel without cargo runs both (W4R-06, W4R-16).
- [W4-1, receipts](w4-1-receipts.md): `rang.receipt` version 3 records the `RANG_*` registry and the source; the solver takes options explicitly; `commit: null` outside a checkout (W4R-01, W4R-02); results unchanged.
- [PC1, preconditions](pc1-preconditions.md): the L1 and L2 precondition failures traced to two merge interactions and fixed; both now run in the test suite.
- [P12, the rename](p12-rename.md): package `rang`, project and distribution `rang-core`; everything identical through the CLI; both wheels pass with cargo absent.
- [P11, extract and retire](p11-extract.md): the 21 frozen modules to `history/`, 127 definitions as verbatim extracts, −7,817 live lines, suite identical.
- [P10, test-suite speed](p10-tests.md): the same 555 tests, 6,031 → 188 CPU-s by capping BLAS and XLA threads; check-all now locks.
- [P9, one CLI](p9-cli.md): `rang-core STAGE VERB`, one comparator engine, versioned receipts and archives, `rang-core check`.
- [P8, history](p8-history.md): the frozen recipes, container builds and recipe-only modules moved to `history/` ([history/README.md](../history/README.md)); live tree −6,373 lines, every archived verdict reproduced.
- [P7, architecture](p7-architecture.md): no ctypes, no cargo at import, kernels in the extension, panic-safe C ABI, GIL released; a wheel-only install reproduces every archived verdict; Windows suite 622 passed, 0 failed.
- [P6, frozen Python hot spots](p6-python-hotspots.md): trend 3.1× with byte-equal checkpoints, signal CPU cut, drivers switched.
- [P5, memory](p5-memory.md): one copy of the cube, Rust decode-in-place and gain correction, whole-array peak −20 %, identities kept.
- [P4, the survey eigensolver](p4-eigen.md): Householder + implicit QL replaces Jacobi, identical decisions on 13,989 calls, 5× per call.
- [P3, SumThreshold](p3-sumthreshold.md): rayon over baselines, bit-identical, 9–12×.
- [P2, gridder](p2-gridder.md): `rustfft`, parallel w-layers, 7× per image, margins unchanged.
- [P1, solver and fused pass](p1-solver.md): rayon over intervals, bit-identical, 5.4× at 8 threads.
- [S1, simplification and optimisation review](simplification-review.md) with [profiles](results/profiles-20261030/): every archive reproduces, the core is single-threaded and FFT-bound, the whole array is memory-bound; wave 2 tasks P0–P11 cut from it.
- [Task J, PyO3/maturin packaging](core-j-packaging.md): the core is the extension `rangtoy._core`, bit-identical to the ctypes path on every archived comparator; `check-all.sh` now fails on failing tests.
- [Parallel work plan](core-parallel-plan.md): the eight tasks of wave 1 and the handoff to wave 2.
- [Task I, imaging track replay](core-i-imaging-replay.md): reproduces the archived imaging track without WSClean within task A's tolerances ([archive](results/core-i-imaging-replay.json)).
- [Task H, core-native Stimela recipes and CLI](core-h-recipes.md): the stages run without QuartiCal.
- [Task G, HTTP range fetch of the LUNO slice](core-g-http-fetch.md): 15 % of the bytes.
- [Task F, solver and blosc performance](core-f-performance.md): faster with identical results.
- [Task D, the Tricolour licence decision and SumThreshold port](core-d-tricolour.md): reproduces the CARACAL controls ([archive](results/core-d-tricolour.json)).
- [Section 6 prototype](core-section6.md): runs as frozen from the LUNO zarr tiles to the rank survey with no Measurement Set; a Rust blosc decoder reads 512 of 3136 blocks, and all eleven criteria pass on the second run (1.67 s excluding decode, 140 MB; the first run failed the cost criterion at 2.86 s and 299 MB) ([archive](results/core-section6.json)).
- [Phase 3c-b, the signal track](core-phase3c-b.md): passes on its first run; every stage of the phase 3 gate now runs on the Rust core with no Measurement Set or container and reproduces its archive, with labelled post-hoc qualifications for trend, injections and actions.
- [Phase 3c-a, the component predictor](core-phase3c-a.md): ported from codex-africanus, matches africanus bit for bit on three component sets, including the 5153-component SARAO 1934−638 catalogue.
- [Phase 3, trend chain test](core-phase3-trend.md): seven core-solved baselines reproduce the archived output through the unedited trend module; the frozen float criterion failed only on rounding-level reference-antenna slopes, and a labelled post-hoc scale passes.
- [Phase 3, the actions stage](core-phase3-actions.md): 9 s for 17 solves, passes as frozen against the archive; the host reproduction needed one labelled post-hoc comparator rule for float metadata.
- [Phase 3b, the prospective track](core-phase3b.md): 54 solves with frozen TRAIN-only forecasts in 33 s; every gated criterion passes on the first run and all decisions, including the seed-109 56-cell selection, are unchanged ([archive](results/core-phase3b.json)).
- [Phase 3, the injection campaign](core-phase3.md): 49 solves entirely on the core, 25 s against 296 s for the host; every decision equals the archive, floats to 1.3e-14; the frozen comparator missed three archive-only fields and a labelled post-hoc rerun passes ([archive](results/core-phase3.json)).
- [Phase 2, the full-Jones solver](core-phase2.md): reproduces QuartiCal 0.2.7's gains on the fixture and LUNO to 1.4e-15 with identical flags and iteration counts; all eight frozen criteria pass; the LUNO solve takes 0.77 s against 28.3 s cold and 3.6 s warm, 0.94 s and 96 MB for the whole process ([archive](results/core-phase2.json)).
- [Phase 1, the fused statistics pass](core-phase1.md): `core/` reproduces the archived residuals to 5.7e-14 Jy and split losses to 2e-15; frozen criterion 4 failed because the gradient cancels at the optimum, and a labelled post-hoc 4b passes ([archive](results/core-phase1.json)).

## The flagging experiment and verdict

Closed 2026-10-30 as null: gain-TV-guided flagging on the fixture and both LUNO calibrators.

- [L4, the flagging verdict](flagging-verdict.md): 90 calls, none better or worse, not cheaper than the CARACal first pass; what would reopen it, and the move to B1.
- [C1, the closure-invariant arm](c1-closure-arm.md): a gauge-free closure statistic sees real GNSS-band structure but no flag improves on the first pass; the last pre-registered arm before the verdict.
- [L5-C, CASA gaincal comparator](l5c-casa-gaincal.md): CASA G on L5's intervals is within the held-out margin of the core on the slice (+7.6e-5) and outside it on the fixture (+1.2e-4), and slow in the same intervals (the slice's tail is in the data), at 75–350× the cost.
- [L5, solver science](l5-solver-science.md): the weight fix, stop criteria and Anderson acceleration as opt-in solver options; no default change passes as frozen; Anderson converges the array solve.
- [L2, the PKS 1830−211 campaign](luno-1830-campaign.md): null under a stored and a scalar model on the whole array, 25–37 min per model ([archive](results/luno-1830-campaign.json)).
- [L1-M, model completeness](l1-model-completeness.md): the stored 1934−638 model is a field model that beats CARACal's lsm, and the field model beats a point by 1.9 % in held-out MSE; TV decisions unchanged under all three; `rangtoy.lsm` reads Tigger lsm.
- [L1, the whole-array LUNO campaign](luno-array-campaign.md): null at array scale (342 M cells, 2 h single-threaded, 12.5 GB), frozen headline undecidable, matched-sample calls null ([archive](results/luno-array-campaign.json)).
- [A1, the RFI-band audit](a1-rfi-audit.md): the emptied station-bins are GNSS-band residue, excision as intended.
- [O-CASA](o-casa.md): a CASA 6.7.6 oracle image on KERN-10 runs CARACal's crosscal on the LUNO slice (after three necessary deviations): the matched baseline for the verdict, tfcrop/rflag flag fractions and a WSClean wgridder reference image.
- [Task K, the first real-data LUNO campaign on the core](core-k-luno-campaign.md): fetch, decode, solve, Tricolour port, TV policy and imaging in 110 s on the PKS 1934−638 four-station slice; null by the pre-registered rule ([archive](results/core-k-luno-campaign.json)).
- [LUNO support at solved gains](flagging-luno-solved.md): rank at QuartiCal's solved gains equals identity and random gains (389 fully identified bins, 43 tree-shaped underidentified), the declared consistency result; chi-squared fell from 73.75 to 0.27 ([archive](results/meerkat-luno-solved.json)).
- [LUNO processed-support survey](flagging-luno-support.md): 389 of 432 supported 1934−638 bins are fully identified for four stations, with failures only in tree-shaped bins; the 1830−211 model is not scalar, so the frozen condition does not apply there.
- [Second public candidate, the LUNO calibrators](flagging-luno-candidate.md): positive weights in all four correlations, unlike ESO137, with 3C 286, PKS 1934−638, a long PKS 1830−211 track and 56 antennas; a 2021 Moon observation (observer B. Hugo) calibrated in CASA in 2022 and published as AfriCalim 2024 workshop data; flags and weights are processing products ([provenance](flagging-luno-candidate.md#provenance-found-2026-10-29)).
- [Latest measured five-track report](flagging-next-summary.md) and [execution plan](flagging-next-results.md): TRAIN-estimated trend guidance, absolute signal guards, prospective confirmation, bounded provenance and actual imaging, all measured and independently audited; the master gather did not succeed, so the report combines four original branches and a fresh imaging retry; CLI and spectral-basis failures are retained.
- [Reportable findings](flagging-findings.md): a TRAIN-only physical gain-response surrogate predicts the counterfactual objective beyond the known flag cost (7.26× smaller matched-coverage RMSE in the held-out seed group), legitimate smooth receiver phases change TV-guided decisions despite invariant residual magnitudes, and signed-source controls show substantial calibration absorption when the sky is incomplete; these reuse one four-antenna observation and motivate triage and preservation controls, not an operational flagger.
- [Persistent discriminating follow-up](flagging-reportable.md): freezes local gain-response prediction, complete/omitted sky controls, smooth-phase TV specificity and supported-data/gauge review.
- [Concurrent follow-up protocol](flagging-concurrent.md): froze five parallel workstreams before new measurements; [suite evidence](results/gain-tv-concurrent.json), [read-only checks](results/gain-tv-concurrent-audit.json).
- [Next flagging hypotheses](flagging-next.md): structured multiscale proposals, noise/support-aware diagnostics, signal preservation and independent transfer, with go/no-go criteria; superseded by the verdict.
- [Parallel diagnostic suite](flagging-parallel.md): controlled RFI/oracle tests, a verified SARAO calibrator sky, established flagger comparisons and patch-action learning; lower gain TV does not consistently mean better prediction.
- [Strategy and experiment log](flagging.md): the policy, its first negative result and reproduction.

Further reports, all superseded by the verdict and all retaining their failures:

- [Trend guidance](flagging-trend.md) ([28 replays](results/gain-tv-next-trend.json), [562-check verification](flagging-next-trend-verification.md)).
- [Native string/HISTORY provenance](flagging-supported-provenance.md) ([657-check verification](flagging-next-provenance-verification.md)) and its [bounded plan](flagging-supported-provenance-plan.md).
- [Prospective three-case confirmation](flagging-next-prospective-verification.md) ([54-solve archive](results/gain-tv-next-prospective.json)).
- [TRAIN signal-guard protocol](flagging-signal-guard.md) and [its measured abstention](flagging-next-signal-verification.md) ([nine paired solves](results/gain-tv-next-signal.json)).
- [Matched dirty-image protocol](flagging-imaging.md), [419-check verification](flagging-next-imaging-verification.md), [dirty-image receipt](results/gain-tv-next-imaging.json), [paired-image figure](figures/gain-tv-dirty-response.png) and the retained [invalid-basis failure](results/gain-tv-next-imaging-invalid-basis.json); [real-parser and source-family gates](../history/tools/flagging/run-imaging.sh) protected the fresh imaging step.
- [TRAIN rank survey](flagging-next-gain-support.md): one two-cell underidentified bin, not broad unsupported data ([rank map](results/gain-tv-next-gain-support.json)).
- [Response precision failure and fix-forward](flagging-response-precision.md): the failed run is preserved unchanged, with no science claim.
- [Supported-data review](flagging-supported-data.md): a native-sigma route requiring new provenance/noise controls, and additional parallel-hand Jones ambiguities.
- [Representative public data](flagging-public-data.md): a bounded, metadata-verified 61-antenna primary-calibrator candidate; numeric acquisition is separate evidence, and native-MS conversion, calibration and observation transfer remain unmeasured.

### Evidence table

Use QuartiCal full complex 2×2 gain total variation as a training objective and
its antenna/time/frequency maps as guidance. Every original FLAG/FLAG_ROW is
protected; fresh writable MS copies, exclusive backups and provenance are
mandatory. Lower TV alone is not sufficient evidence for removing data.

| Evidence/workstream | Report | Compact measured archive | Executable recipe |
| --- | --- | --- | --- |
| Baseline TV-conditioned outlier model | [Strategy](flagging.md) | [Baseline](results/gain-tv-flagging.json) | [Pilot](../history/recipes/tv-flagging.yaml) |
| Six controlled RFI cases and evaluation-only oracles | [Injections](flagging-injections.md) | [Controls](results/gain-tv-injections.json) | [Injections](../history/recipes/tv-flagging-injections.yaml) |
| Point, official primary and full apparent-scale catalog | [Sky adequacy](flagging-sky.md) | [Sky comparison](results/gain-tv-sky.json) | [Sky](../history/recipes/tv-flagging-sky.yaml) |
| Genuine QuartiCal MAD and Tricolour kernel | [Comparators](flagging-comparators.md) | [Matched diagnostics](results/gain-tv-comparators.json) | [Comparators](../history/recipes/tv-flagging-comparators.yaml) |
| Counterfactual patch-action ridge learner | [Action learning](flagging-actions.md) | [Clean](results/gain-tv-actions.json), [contaminated](results/gain-tv-actions-injected.json) | [Actions](../history/recipes/tv-flagging-actions.yaml) |
| Actual four-worker concurrent replay and preservation audits | [Parallel verification](flagging-parallel.md) | [Suite](results/gain-tv-parallel.json) | [Native scatter](../history/recipes/tv-flagging-parallel.yaml) |
| Unmodified full native CARACAL Tricolour strategies | [Production verification](flagging-caracal.md) | [Four controls](results/gain-tv-caracal.json) | [Native strategies](../history/recipes/tv-flagging-caracal.yaml) |
| Matched structured residual/TV rankings, seven controls | [Structured search](flagging-structured.md) | [101 solves](results/gain-tv-structured.json) | [Structured actions](../history/recipes/tv-flagging-structured.yaml) |
| Geometry-balanced residual/TV/random follow-up | [Balanced search](flagging-balanced.md) | [Seven cases,130 solves](results/gain-tv-balanced.json) | [Balanced](../history/recipes/tv-flagging-balanced.yaml) |
| Synthetic gain-TV/noise/physical-trend controls | [Uncertainty guidance](flagging-uncertainty.md) | [180 gain-only controls](results/gain-tv-uncertainty.json), not real solver uncertainty | [Uncertainty](../history/recipes/tv-flagging-uncertainty.yaml) |
| Bounded public numeric visibility acquisition/inspection | [Ingestion](flagging-public-ingestion.md) | [75 object hashes](results/meerkat-public-ingestion.json), [two61-antenna pilots](results/meerkat-public-pilot.json) | [Offline inspection](../history/recipes/tv-flagging-public.yaml) |
| Paired intrinsic science-signal diagnostic | [Signals](flagging-signal.md) | [16 paired solves and constrained fits](results/gain-tv-signal.json) | [Signals](../history/recipes/tv-flagging-signal.yaml) |
| Fitted grouped guarded-objective action predictor | [Transfer model](flagging-transfer.md) | [105 labels/frozen predictions](results/gain-tv-transfer.json) | [Transfer](../history/recipes/tv-flagging-transfer.yaml) |
| Five-track concurrent execution with label-dependent fit | [Frozen protocol](flagging-concurrent.md) | [Completed suite](results/gain-tv-concurrent.json) | [Concurrent](../history/recipes/tv-flagging-concurrent.yaml) |
| Projected TRAIN-only physical deletion-response surrogate | [Influence design](flagging-influence.md), [independent verification](flagging-influence-verification.md) | [123 retrospective forecasts/labels](results/gain-tv-influence.json), [audit](results/gain-tv-influence-audit.json) | [Influence](../history/recipes/tv-flagging-influence.yaml) |
| Signed complete/omitted sky and gain-grid response controls | [Response protocol and measurements](flagging-response.md), [independent checks](flagging-response-verification.md) | [Ten frozen controls and preserved retry provenance](results/gain-tv-response.json), [audit](results/gain-tv-response-audit.json) | [Response](../history/recipes/tv-flagging-response.yaml) |
| Legitimate smooth receiver-phase specificity controls | [Phase design](flagging-equivariance.md), [independent checks](flagging-equivariance-verification.md) | [520 saved-gain replays](results/gain-tv-equivariance.json), [audit](results/gain-tv-equivariance-audit.json) | [Equivariance](../history/recipes/tv-flagging-equivariance.yaml) |
| Native noise-column and partial-Jones support review | [Supported data](flagging-supported-data.md) | [Read-only diagnostics](results/meerkat-supported-data-candidates.json) | Diagnostic regeneration script, not a calibration recipe |
| Five-track results strategy; four original branches plus corrected imaging retry | [Latest results](flagging-next-summary.md), [frozen plan](flagging-next-results.md) | Five next-* measured archives with individual source/hash receipts | [Stimela2 research graph](../history/recipes/tv-flagging-next.yaml) |
| TRAIN-estimated trend-aware full-Jones guidance | [Trend](flagging-trend.md), [verification](flagging-next-trend-verification.md) | [28 replays](results/gain-tv-next-trend.json) | [Trend](../history/recipes/tv-flagging-trend.yaml) |
| Prospective local physical confirmation, three cases | [Verification](flagging-next-prospective-verification.md) | [54 actual solves](results/gain-tv-next-prospective.json) | [Prospective](../history/recipes/tv-flagging-prospective.yaml) |
| Absolute signal guard and original TRAIN identifiability | [Guard](flagging-next-signal-verification.md), [rank survey](flagging-next-gain-support.md) | [Nine paired solves](results/gain-tv-next-signal.json), [rank map](results/gain-tv-next-gain-support.json) | [Guard](../history/recipes/tv-flagging-signal-guard.yaml) |
| Bounded textual native-data provenance recovery | [Verification](flagging-next-provenance-verification.md) | [85 chunks/21 HISTORY rows](results/gain-tv-next-provenance.json) | [Offline provenance](../history/recipes/tv-flagging-provenance.yaml) |
| Actual matched dirty-image/PSF and CARACAL diagnostics | [Frozen image protocol](flagging-imaging.md) | [15 corrected inversions](results/gain-tv-next-imaging.json), [retained semantic failure](results/gain-tv-next-imaging-invalid-basis.json) | [Images](../history/recipes/tv-flagging-imaging.yaml) |

### Pilot findings and checkpoints

Main findings: the current policies select no added flags on the unmodified
fixture. Earlier structured search recovers only 2.89% of a strong time-burst;
its TV ranking misses that action. The balanced follow-up improves one fresh
seed (TV 19.69% versus residual 10.10% known-injection recall), but not the other
five injected cases. Its fitted estimator recommends no-change on all six.
A fuller sky improves prediction while slightly increasing TV. Some masks
lower TV while worsening prediction. Outside-injection additions are not proven
false positives in unlabeled real data. No imaging or state-of-the-art advantage
has been established. The tiny fixture is a four-antenna dedicated pointing scan,
not a representative science observation. Smooth physical delay controls have
high raw TV without RFI. Paired omitted-source fits show strong attenuation and
bound-hit spectra, not validated flux/image preservation. The downloaded
61-antenna tiles have zero native cross-hand spectral weights: the current
strict four-correlation protocol accepts no cells, and no flags/weights are
changed to manufacture support.

[Pinned CARACAL strategy/worker inspection](flagging-caracal.md) records the
production-strategy differences, executable full-strategy recipe and four
completed measured controls. The [partial archive](results/gain-tv-caracal-progress.json)
retains its historical two-control/pending-final-audit checkpoint unchanged.

Baseline/follow-up verified checkpoint: 14 Rust/171 Python tests, full local checks, six
recipe dry-runs, actual concurrent execution and 24 read-only prepared-input
audits. Commits `35e763b` and `f782921` were pushed to origin/main on 2026-09-23.
Further development must record its own checks rather than inherit these counts.
Native CARACAL/structured-search checkpoint: 14 Rust/196 Python tests, local
build/lint/format and all three runtime dependency checks pass. Four native
controls and seven structured runs complete with source/export preservation
audits; neither an imaging nor a robust TV-guidance advantage is established.
Separate [artifact checks](results/gain-tv-artifact-audit.json) reproduce 318
predicates across all these controls. Wrapper/finite-value hardening found during
that review is a fix-forward implementation change, not a scientific rerun.
The hardening checkpoint passes 14 Rust/222 Python tests and full local checks;
all 98 recorded action/native scores are exactly unchanged under the new guards.
The concurrent-work implementation checkpoint `1739d48` passes 14 Rust/323 Python
tests, full local checks and all three runtime dependency checks. Actual suite
execution finishes 2026-09-24 07:18:30 UTC; all 13 module hashes/input boundaries
remain frozen. Measured archives distinguish retrospective search, gain-only
controls, conditional source response and real numeric inspection; they do not
establish robust flagging, observation transfer, imaging or SOTA superiority.

### Resume the frozen campaigns safely

Exact run paths of those campaigns are in [STATE-history.md](STATE-history.md). Pinned container environments live under `history/tools/flagging/`
([history/README.md](../history/README.md)); the host Python 3.14
cannot run the pinned QuartiCal solver. Sky and Tricolour dependencies need
separate venvs, not a combined pip environment. The checkout is mounted read-only
and solver runtime is network-disabled. QuartiCal uses `G.type=complex`, two
integrations × 32 channels, 50 iterations, original weights and identity startup.

Raw fixture: `outputs/ska-pointing/outer_scans.zip`; its checksum/provenance are in
[inspection](measurement-set-inspection.md). Official sky catalog lives in
`outputs/flagging-sky-inputs/`, is not redistributed, and has documented license.
Prepared clean input: `outputs/tv-injections-pilot-01/`; contaminated copies are
its `cases/{narrowband,time-burst,antenna-local}-s{3,10}` directories. Do not read
their injection-truth NPZs when constructing or selecting real policies.
Immutable published artifacts must not be edited; always choose fresh outputs.

Baseline/follow-up backups: `outputs/flagging-backups/20260923-parallel-final/`.
Final audit and verification metadata include helper hashes and commit identity.
Raw outputs are local/ignored and may not exist in a fresh clone; the tracked
compact archives and pinned recipe/settings survive. Preserve historical failed
or null runs. Disk availability was about 21 GiB before the next experiment;
check capacity before copying more MS. No cleanup has been authorized.

## Beam and pointing

Closed as null at B1-3. A deeper field model (an external catalogue, an owner decision) is the first condition for reopening it on real data.

- [B1-3, pointing self-calibration at matched cost](b1-3-pointing-selfcal.md): overall negative under the frozen rule; physical pointing self-calibration works in simulation (0.62′ to 0.054′, held-out error down 3 %), distinguishability selection adds nothing measurable over fitting every antenna, and on real ESO137 data with the self-calibrated model neither arm measures pointing.
- [B1-2, identifiability](b1-2-identifiability.md): per-antenna pointing and squint are constrainable on ESO137 (0.07′ and 0.01′ in 3.5 min) and marginally on 1934; array-common pointing and ellipticity only on a 7-scan track; width nowhere; snapshot common pointing is bandpass granularity.
- [B1-0 and B1-1, beam and pointing](b1-beam-pointing.md): the SARAO holography cube as the reference beam (katbeam 0.8 %, EIDOS 2.1 % off), the SARAO/SKA Gaussian pointing fit ported bit-exact and found weak on the fixture.

The 2026-09 simulations that led here are under [Historical pilots](#historical-pilots).

## CLEAN theory programme

- [How many major cycles does CLEAN need?](clean-major-cycles.md): theory in Lean (the Gram-gap identity, per-cycle descent, the outer rate); in simulations through the exact gridder, passes fall from 4-7 (WSClean's scheme) to 2-3 with a double-size PSF run to the threshold, and to 1 without the w-term; the certified rules cost more passes, not fewer; timings are provisional.
- [CLEAN phase transition](clean-phase-transition.md): when Högbom CLEAN recovers point sources exactly, on MeerKAT, VLA-C, WSRT and KAT-7. Proven: an exact gain-one two-source rule (an ℓ∞ ERC plus the first pick), which agrees with all 40,000 trials, and a sharper sufficient condition (Theorem 8, anchored), which certifies 14 of 80 cases against 3 for Proposition 4'. Measured: the transition `d*(k)` per array, coverage and weighting, with every sufficient condition far above it for `k ≥ 4`. Negative: no universal curve beyond the ERC threshold `η = 1`, and with 1 % noise no configuration reaches 95 % exact support ([archive](results/clean-phase-transition.json)).
- [What CLEAN minimises](clean-implicit-objective.md): small-gain Högbom CLEAN is forward stagewise regression, proved to converge (in ℓ1 arc length) to the same limit as FS_ε, unique in data space (the gradient flow of the peak residual) and equal to Hastie et al.'s monotone lasso when the tied atoms are independent (for extended emission that condition seems to fail, so model convergence there is measured, not proved); no pointwise objective, only steepest descent of the misfit per unit ℓ1 arc length. Measured on MeerKAT PSFs: CLEAN → FS₀ at rate about γ^0.8-1.4; the lasso path is far from monotone for extended emission (small gain wins on a disc, loses on point sources on the snapshot); 21 new Lean theorems, including Proposition 4' and Theorem 6 of the CLEAN note ([archive](results/clean-implicit-objective.json)).
- [Certified CLEAN](clean-certified-imaging.md) on the LUNO 1934−638 slice: the instrumented driver reproduces WSClean 3.7's CLEAN to 5e-6 Jy, divergence included, names the cause (image-size beam, Gram gap 99 Q, 158 ascending steps) and converges with the exact beam (65 components, rms 22 mJy); O-CASA's WSClean reference is 17 % off the exact transform because of WSClean's minimum-grid-resolution upsampling ([archive](results/clean-certified-imaging.json)).
- [CLEAN theory](clean-theory.md): the claim that CLEAN was never proven is folklore (Schwarz 1978 proved the data fit converges for 0 < g < 2); a Gram-matrix formalism reduces his three conditions to one, seven theorems are machine-checked in Lean (`formal/`), and MeerKAT measurements show the one-step identity to 1e-13, the coherence bound vacuous, Tropp's ERC exact in 9,600 trials, Clark's rule without guarantee and a provable minor-cycle rule with one ([archive](results/clean-theory.json)).

## Gridders and imaging

- [DF5-O, the deconvolution oracles](df5o-deconv-oracles.md): WSClean and pfb-imaging frozen on a simulated MeerKAT field; their dirty images agree with the core's to 1.7e-7 and 2.6e-7 of the peak; WSClean Högbom and pfb kclean/Clark meet the truth tolerances A1 and A2, and WSClean multiscale meets A2 and fails A1 on three sources.
- [DF2c, `--gridder` for the campaign runs](df2c-campaign-gridder.md): K/L1/L2/L1-M/C1 take `wgrid` with its plan in the receipts, the default bit-identical; L2, L1-M and C1 re-imaged post hoc, no call changes.
- [X2, the GPU gridder](x2-wgpu.md): the w-stacking gridder and FFT on wgpu (feature `gpu`, f64), C/I/K comparators pass on the RTX 4070 Ti, 2.5–3.3× over 16 CPU threads at four stations, 1.2× at whole-array scale; f32 fails K.
- [DF2b, the exact gridder in the imaging drivers](df2b-wgrid.md): `gridder="wgrid"` for C/I/K/L1, `wstack` bit-identical, the archives within 4e-7 of WSClean 3.7's wgridder, two-weight entry point and extension bindings.
- [DF2a, exact gridder speed](df2-wgridder-speed.md): the wgridder port at ducc0's speed on whole-array inputs, gates kept, the edge difference explained as rounding amplification.
- [DF1, the exact gridder](df1-wgridder.md): a port of ducc0's wgridder passing all gates; the 19 % w-stacking discrepancy is WSClean's padding-1.2 aliasing, not a defect.
- [Task C, the w-stacking gridder](core-c-gridder.md): within 6.1e-7 of the peak.
- [Task B, imaging weights and Stokes I](core-b-weighting.md): bit-identical to WSClean.
- [Task A, WSClean approximation sensitivity](core-a-imaging-sensitivity.md): the phase 4 tolerances.

## Measurement Set reader and writer

- [E6, the last of the core table writer](e6-table-writer-final.md): TiledDataStMan hypercubes, TiledCellStMan, IncrementalStMan string arrays and MultiFile block order written as casacore writes them; 20 of 21 cases byte-identical, IS-arrays differing only in alignment-gap bytes of its array file (criteria 1 and 3 fail as frozen on that case; a labelled post-hoc walk masks all 677 bytes); MultiHDF5 refused as not supported.
- [E5, the rest of the core table writer](e5-table-writer-rest.md): IncrementalStMan, last-row removal, tiled hypercubes, TiledDataStMan and MemoryStMan creation, big-endian and MultiFile tables; 21 of 23 cases byte-identical to casacore 3.8.1, the rest casacore's uninitialised memory.
- [E4, core table creation](e4-table-create.md): casacore tables, rows, string arrays, `default_ms` and CASA caltables created by the core writer, byte-identical to casacore 3.8.1 and CASA 6.7.6 (gaps masked), `applycal` bit-identical.
- [E3, the core table writer](e3-table-writer.md): in-place casacore table writes byte-identical to casacore 3.8.1 (bar uninitialised padding), locks included; `rangtoy.core_ms_write`.
- [casacure evaluation](casacure-evaluation.md): reads column-exact on every platform, writes and measures not trustworthy; verdict: build rang's own table writer, casacure as a pinned second oracle.
- [Task E, a read-only Measurement Set reader](core-e-ms-reader.md): column-exact.
- [Public MeerKAT pointing-scan inspection](measurement-set-inspection.md): the fixture's checksum and provenance.

## File formats and oracles

- [A-FLAG, AOFlagger 3.5 as a second SumThreshold oracle](a-flag-aoflagger.md): at kernel level the port is AOFlagger's intended SumThreshold up to its documented differences (A1/A2), bridged bit for bit; against the shipped 3.5.0 binary an AOFlagger defect adds more; at stage level the flaggers differ (0.60–0.95 agreement, mostly from Tricolour growing input flags); two AOFlagger 3.5.0 bugs found.
- [T1, casacure in the wheel tests](t1-casacure-ci.md): casacure 3.8.35 as the second oracle of the core's reader, writer and table creation on Linux, Windows and macOS arm64 3.14, on the public fixture; the golden MS case runs on every job.
- [DF-IO, the tools' file formats](dfio-formats.md): CASA caltables, QuartiCal stores, Tigger/WSClean/BBS sky models, DicoModel, ClusterCat, H5parm, killMS solutions and CASA flag versions, each judged by its own tool; `rang-core formats check|convert`.
- [MK1, the MVFv4 loader](mk1-katdal.md): a `[meerkat]` extra (katdal 0.23) and `rang.meerkat`, MVF archives into core row chunks with native flag bits; exact against raw chunks, katdal and mvftoms on a synthetic archive (no public MVF exists); L3 is ready when data arrive.
- [RV1, re-validation](rv1-revalidate.md): against the unreleased Tricolour 0.5.0-dev (`367ff54`: flag for flag identical to 0.2.1 and the core port, CLI included; the `uvrange` rule changed) and QuartiCal v0.2.8-dev (`d54c46b`: the #452 fix moves 50-iteration gains by up to 2.8e-4; the core's `qp_weights=transposed` reproduces it to 1e-15).
- [FS1, flux standards](fs1-flux-standards.md): CASA's `setjy` standards in the core to the last bit; an erratum for O-CASA's residuals.

## Upstream reporting

- [Upstream notes](upstream-notes.md): the status of each observation.
- [U4, findings filed](u4-upstream.md): ten filings on Tigger, Crystalball, pfb-imaging, Tricolour, QuartiCal, killMS and casacure, a casacure PR, and tricolour#114 rebased and green.
- [U3, saopicc upstream](upstream-saopicc.md): six issues and four pull requests on DDFacet and killMS; Hogbom diverges with more than one facet.
- [U2, upstream fixes](upstream-prs.md): three issues and four pull requests (tricolour#112 merged, caracal#1708 approved, tricolour#114 and stimela#620 open).
- [U1, upstream issues](upstream-issues/) on RATT software (QuartiCal #452, #453; Tricolour #110, #111) and the [non-RATT list](non-ratt-observations.md).

## Cross-platform, wheel, docs and release

- [W4-8, the documentation pass](w4-8-readme-docs.md): the README as a landing page, this index by theme, STATE trimmed with its history linked, AGENTS.md for the layout, a deploy job that skips without GitHub Pages.
- [W4-5, the release metadata](w4-5-release.md) for v0.1.0: `rang-core --version`, classifiers and URLs, a PyPI-safe README, the CHANGELOG, the tag-equals-version guard, Node 24 actions, the slim sdist (250 entries, 1.2 MB) and the release procedure.
- [NB-CARTA, the CARTA helper](nb-carta.md): `rang.notebook.carta` opens images and cubes in CARTA 6.0 from a notebook (open, snapshot), the `[carta]` extra and the pinned wrapper and containers; skips cleanly on Windows.
- [D3, the science notebooks](d3-science-notebooks.md): the flagging verdict and the beam and pointing question as guided notebooks on the site, every number from an archive or a live cell.
- [D2, notebook tooling](d2-notebook.md): `rangtoy.notebook` and five tutorial notebooks in `notebooks/`.
- [D1, the documentation site](d1-docs.md): Sphinx and myst-nb, executed tutorials, API from the docstrings, GitHub Pages deployment from `main`.
- [X1, cross-platform](x1-crossplatform.md): native Windows build and a bit-identical comparator, a five-platform wheel matrix with PyPI trusted publishing on tags.
- [W1, the distributable wheel](wheel.md): manylinux_2_28 abi3 wheel tested on CPython 3.10–3.14 without cargo, a wheels workflow, publication left to the user.

## Surveys and feasibility studies

- [Ecosystem survey](ecosystem-survey.md): KERN-10, CASA and CARTA with port/depend/oracle/format verdicts, the oracle per task and the 22-format table for DF-IO.
- [DDFacet/killMS feasibility study](ddfacet-feasibility.md): no faithful port; an exact wgridder-algorithm gridder first, facets later, DDFacet and killMS as oracles.
- [Literature scan 2023–2026](literature-2024-2026.md): calibrator model completeness is the strongest lead for the null results; ranked recommendations and what to drop.
- [Stack-consolidation feasibility](stack-consolidation-feasibility.md): one Rust core with a thin Python API could partially replace the tools; a cold QuartiCal solve costs 28.3 s and a warm one 3.6 s, of which about 1 s is the solve; the five-track campaign spends 337 s of 435 s in 63 QuartiCal subprocesses and reads 21.7 GB to serve an 18 MB cube; a port plan counts about 6× fewer boundary crossings (about 1,250 to about 205).

## Historical pilots

The 2026-09 pointing and beam simulations. These reports have their own
assumptions; they are matched-family synthetic tests or conventional baselines,
not measured flagging gains, measurements of MeerKAT beam errors or novelty.

| Beam treatment, eight antennas, synthetic 1% log-width scatter before removing the antenna mean | Relative pointing RMSE |
| --- | ---: |
| Ignore antenna differences; fit one shared width | 6.33–9.19 arcsec |
| Fit shared width and seven relative antenna widths | 0.79–1.10 arcsec |
| Supply the exact antenna widths (oracle) | 0.73–1.07 arcsec |

Ranges cover three seeds and two shared-pointing settings. Joint sky/beam/pointing
inference has prior art; this strengthens the baseline rather than proving
novelty ([experiment, controls](antenna-beam-widths.md) and
[reproduction](antenna-beam-widths.md#implementation-and-reproduction)).

- [Scientific assessment](status.md), [roadmap](development-roadmap.md) and [prior-art boundaries](novelty.md): the proposed decision rule (selecting pointing/beam parameters by separate limits on signal distortion and model-error contamination) was not implemented or validated.
- [Smooth pointing](pointing-solutions.md): the solver. The [smoke example and experiment guide](../examples/README.md) run it with a fixed, correct Gaussian beam and sky.
- [Antenna beam widths](antenna-beam-widths.md): the table above; [coverage](antenna-beam-widths.md#separate-relative-and-common-uncertainties) improves when widths are fitted, but shared-mode coverage remains less reliable.
- [Exact Gaussian gauge](gaussian-gauge.md): Gaussian beams admit an exact pointing–sky–gain ambiguity, including rotating elliptical beams when the compensating sky and gain freedom is available.
- [Common pointing priors](common-pointing-priors.md): an optional prior-constrained common trajectory is separate from the zero-mean convention, and its physical value is not established.
- [Relative pointing](relative-pointing.md): the solver can impose exactly zero antenna-mean pointing, following Oleg Smirnov's feedback; recovery and a mismatch control.
- [First results](first-results.md): good residuals do not guarantee accurate astronomy; a 2% beam-width error overestimates a faint source's flux by about 71% at 99.75% injected-signal response.
- [Spectral pointing](spectral-pointing.md): earlier mode selection did not improve pointing accuracy over a fairly tuned joint fit.
- [Chromatic gains](chromatic-gains.md): 168 fits in seven campaigns; polynomial gain compression fails when the fitted order is too low.
- [Beam rotation](beam-rotation.md): beam symmetry restricts which pointing modes can be measured; freeing the other common modes restores the Gaussian ambiguity.
- [Beam-model selection](beam-model-selection.md): an ordinary joint-fit baseline that needs a science-quality control.
- [Sky uncertainty](sky-uncertainty.md): 2% off-axis flux errors raise pointing RMSE from 2.40 to 30.24 arcsec when calibration holds the sky fixed.
- [Information budget](information-budget.md): separates unconstrained visibility information from what uncertain external flux constraints supply.
- [katbeam pointing](katbeam-pointing.md): chromatic beam shape supplies pointing information in the toy; a measurement-informed scalar model, not complete measured antenna Jones beams.
- [Uncertainty coverage](uncertainty-coverage.md): local Gauss–Newton marginal uncertainties and a beam-width recovery control.
- [Robustness stress](robustness-stress.md): toy controls showing the matched-model result is not sufficient.
- [Frequency blocking](frequency-blocking.md): standard structured least-squares elimination, a compute benchmark and not an end-to-end calibrator speedup.
- [Public pointing history](pointing-history.md): an inspection of the SARAO release (CC BY-NC 4.0), kept in ignored outputs.
- [Calibration research, 2026-09-11](calibration-research-2026-09-11.md): the first literature review and candidate method, superseded by the [MeerKAT scope](meerkat-scope.md).
- [Message draft](sharing-draft.md): an unsent note to Oleg Smirnov, kept for the record.

**Scope of those simulations.** Main experiments use eight approximate MeerKAT
core positions, scalar beams, four frequencies and a small component sky
([geometry and provenance](../data/README.md)). The DFT includes the non-coplanar
phase. The JAX solver supports smooth pointing, source fluxes/spectral indices,
complex gains and selected beam parameters; it is a reference implementation,
not a streaming or full-polarization pipeline. The katbeam adapter provides a
simplified holography-informed scalar response. A public Measurement Set reader
has been exercised, but antenna-label and pointing-coordinate conventions remain
unresolved. The pointing demonstrator does not establish real-observation
pointing calibration or improved deconvolved images. Actual QuartiCal gain solves
in the separate flagging pilots are visibility-space research diagnostics.
Structured projection benchmarks are not end-to-end calibrator speedups.

## Timeline

| Dates | Milestone |
| --- | --- |
| 2026-09-11 | The first pointing simulations and the [research status](status.md) |
| 2026-09-23 to 24 | The [flagging experiment](flagging.md) and its [five-track report](flagging-next-summary.md) |
| 2026-10-29 | The [feasibility study](stack-consolidation-feasibility.md), [core phases 1 to 3](core-phase3.md), the GPL decision and [wave 1](core-parallel-plan.md) |
| 2026-10-30 | The [big plan](big-plan.md), the [verdict](flagging-verdict.md), [B1](b1-beam-pointing.md), [CLEAN theory](clean-theory.md), the [rename](p12-rename.md) and the [docs site](d1-docs.md) |
| 2026-10-31 | The [final review](w4-review.md) and the [release metadata](w4-5-release.md) |
| 2026-11-02 | [B1-3](b1-3-pointing-selfcal.md) closes beam and pointing as null; [E6](e6-table-writer-final.md), [DF5-O](df5o-deconv-oracles.md), [W4-2 and W4-7](w4-2-boundaries.md), the [CLEAN major cycles](clean-major-cycles.md) |

The research manuscript draft on CLEAN is in `research/paper/clean-theory/`;
scripts and patches sent upstream are in `research/upstream-prs-files/` and
`research/upstream-saopicc-files/`.
