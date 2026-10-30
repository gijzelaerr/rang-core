# Research handoff and index

Start with [STATE.md](STATE.md), then [active MeerKAT scope](meerkat-scope.md).
This index routes new collaborators to evidence; it is not a novelty claim.
Updated 2026-10-29 (wave 1 merged). User instructions and Git attribution live in [AGENTS.md](../AGENTS.md).

New, 2026-10-30: big plan task W1, the [distributable wheel](wheel.md):
manylinux_2_28 abi3 wheel tested on CPython 3.10–3.14 without cargo, a
wheels workflow, publication left to the user.

New, 2026-10-30: big plan task S1, the [simplification and optimisation
review](simplification-review.md) with [profiles](results/profiles-20261030/):
every archive reproduces, the core is single-threaded and FFT-bound, the
whole array is memory-bound; wave 2 tasks P0–P11 cut from it.

New, 2026-10-30: big plan task U1, [upstream issues](upstream-issues/) on RATT
software (QuartiCal #452, #453; Tricolour #110, #111) and the
[non-RATT list](non-ratt-observations.md); status per observation in
[upstream-notes.md](upstream-notes.md).

New, 2026-10-30: the [big plan](big-plan.md): simplification and
optimisation review, science to a verdict, RATT upstream issues and a
distributable wheel, run in parallel waves; licence settled by user decision.

New, 2026-10-30: wave 2 task K, the [first real-data LUNO campaign on the core](core-k-luno-campaign.md):
fetch, decode, solve, Tricolour port, TV policy and imaging in 110 s on the
PKS 1934−638 four-station slice; a null result by the pre-registered rule,
provisional under the open licence ([archive](results/core-k-luno-campaign.json)).

New, 2026-10-29: wave 2 task J, [PyO3/maturin packaging](core-j-packaging.md):
the core is the extension `rangtoy._core`, bit-identical to the ctypes path on
every archived comparator; `check-all.sh` now fails on failing tests.

New, 2026-10-29: wave 2 task I, the [imaging track replay on the core](core-i-imaging-replay.md),
reproduces the archived imaging track without WSClean within task A's
tolerances ([archive](results/core-i-imaging-replay.json)).

New, 2026-10-29: wave 1 of the [parallel work plan](core-parallel-plan.md) is
merged: [A, WSClean approximation sensitivity and phase 4 tolerances](core-a-imaging-sensitivity.md);
[B, imaging weights and Stokes I](core-b-weighting.md) bit-identical to WSClean;
[C, the w-stacking gridder](core-c-gridder.md) within 6.1e-7 of the peak;
[D, the Tricolour licence decision and SumThreshold port](core-d-tricolour.md)
reproducing the CARACAL controls ([archive](results/core-d-tricolour.json));
[E, a read-only Measurement Set reader](core-e-ms-reader.md), column-exact;
[F, solver and blosc performance](core-f-performance.md) with identical results;
[G, HTTP range fetch of the LUNO slice](core-g-http-fetch.md), 15 % of the bytes;
[H, core-native Stimela recipes and CLI](core-h-recipes.md) without QuartiCal.

New, 2026-10-29: the [section 6 prototype](core-section6.md) runs as frozen
from the LUNO zarr tiles to the rank survey with no Measurement Set: a Rust
blosc decoder reads only the 512 of 3136 blocks it needs, the core solves,
and all eleven criteria pass on the second run (1.67 s excluding decode,
140 MB; the first run failed the cost criterion at 2.86 s and 299 MB).
Against the measured chain this replaces MS build, a 28 s cold or 3.6 s warm
QuartiCal solve and the survey ([archive](results/core-section6.json)).

New, 2026-10-29: the [actions stage](core-phase3-actions.md) runs on the Rust
core in 9 s (17 solves) and passes as frozen against the archive; the host
reproduction needed one labelled post-hoc comparator rule for float metadata.
The [trend chain test](core-phase3-trend.md) hands seven core-solved baselines
to the unedited trend module, which reproduces its archived output; the frozen
float criterion failed only on rounding-level reference-antenna slopes, and a
labelled post-hoc scale passes. With the [signal track](core-phase3c-b.md) passing on its first run, every
stage of the phase 3 gate (injections, prospective, actions, trend, signal)
runs on the Rust core with no Measurement Set or container and reproduces its
archive, with qualifications: trend passes only under a labelled post-hoc
criterion (its frozen float criterion failed on rounding-level reference
slopes), and injections and actions needed labelled post-hoc comparator steps
(archive-only fields; float metadata in the host reproduction). The frozen
Stimela recipes still call QuartiCal; the core drivers run beside them. The signal track's
prerequisite, a [Rust component predictor](core-phase3c-a.md) ported from
codex-africanus, matches africanus bit for bit on three component sets,
including the 5153-component SARAO 1934−638 catalogue.

New, 2026-10-29: [phase 3b](core-phase3b.md) runs the prospective track (54
solves, frozen TRAIN-only forecasts) on the Rust core in 33 s and passes every
gated criterion against the archive and the host reproduction on its first
run; all decisions, including the seed-109 56-cell selection, are unchanged
([archive](results/core-phase3b.json)). The signal track waits for a Rust
component predictor (phase 3c).

New, 2026-10-29: [phase 3 of the core port](core-phase3.md) runs the injection
campaign (49 solves, six injected cases, the TV-guided policy grid) entirely
on the Rust core, with no Measurement Set or container, in 25 s against 296 s
for the host reproduction. Every decision and selected policy equals the
archive; floats agree to 1.3e-14. The frozen comparator missed three
archive-only fields; a labelled post-hoc rerun with them passes
([archive](results/core-phase3.json)).

New, 2026-10-29: [phase 2 of the core port](core-phase2.md) is implemented and
measured. A Rust port of the full-Jones complex solver of QuartiCal 0.2.7
reproduces its gains on the fixture and on LUNO to 1.4e-15, with identical gain
flags, iteration counts and converged fraction, and passes all eight frozen
criteria. The LUNO solve takes 0.77 s against 28.3 s (cold) and 3.6 s (warm) for
QuartiCal; the whole load-solve-statistics process takes 0.94 s and 96 MB
([archive](results/core-phase2.json)).

New, 2026-10-29: [phase 1 of the core port](core-phase1.md) is implemented
and measured: a fused Rust pass (`core/`) for residuals, split losses, robust
scores and antenna-diagonal normals. It reproduces the archived residuals to
5.7e-14 Jy and the split losses to 2e-15. Frozen criterion 4 failed because the
gradient cancels at the optimum; a labelled post-hoc criterion 4b passes
([archive](results/core-phase1.json)).

New, 2026-10-29: a [stack-consolidation feasibility study](stack-consolidation-feasibility.md)
asks whether one Rust core with a thin Python API could replace the tools rang
runs between reading visibilities and writing diagnostics. Verdict: partially.
Measured on the LUNO four-station slice, a cold QuartiCal solve costs 28.3 s and
a warm-cache one 3.6 s, of which about 1 s is the solve; the five-track campaign
spends 337 s of 435 s in 63 QuartiCal subprocesses and reads 21.7 GB to serve an
18 MB cube. The inner loop (predict, solve, statistics, TV, rank) is worth fusing;
MS tables, strategy flaggers and WSClean stay at the edges. Acceptance criteria
for a prototype are frozen in the study; nothing is implemented. A port plan
(section 9) counts about 6× fewer boundary crossings for the five-track
campaign (about 1,250 to about 205) once the solve wrapper, MS copies and
digests collapse into one in-memory pass.

New, 2026-10-29: every published five-track stage is reproduced on a second
host from re-fetched public inputs (see [STATE.md](STATE.md)). A
[second public L-band candidate](flagging-luno-candidate.md), the LUNO
calibrator observation, has positive weights in all four correlations, unlike
ESO137. It also carries 3C 286, PKS 1934−638 and a long PKS 1830−211 track, and
56 antennas. Its own metadata identifies it as a 2021 Moon observation (observer
B. Hugo) calibrated in CASA in 2022 and published as AfriCalim 2024 workshop
data. Its flags and weights are processing products, and no licence is
established ([provenance](flagging-luno-candidate.md#provenance-found-2026-10-29)).
A provisional [processed-support survey](flagging-luno-support.md) finds 389 of
432 supported 1934−638 bins fully identified for four stations, with failures
only in tree-shaped bins. The 1830−211 model is not scalar, so the frozen
condition does not apply to that scan.

[Latest measured five-track report](flagging-next-summary.md) and
[execution plan](flagging-next-results.md) freeze
TRAIN-estimated trend guidance, absolute signal guards, prospective candidate
confirmation, bounded textual provenance and actual imaging diagnostics.
All five now have measured and independently audited outcomes.
Original master gather did not succeed; the report explicitly
combines four original branches and a separate fresh imaging retry. Both
CLI and spectral-basis failures are retained; no novelty claim is implied.

New completed evidence: [trend-aware guidance](flagging-trend.md),
[28 replays](results/gain-tv-next-trend.json) with
[562-check verification](flagging-next-trend-verification.md), and
[bounded provenance](flagging-supported-provenance.md) with
[657-check verification](flagging-next-provenance-verification.md).
Also complete: [prospective three-case confirmation](flagging-next-prospective-verification.md),
[54solve archive](results/gain-tv-next-prospective.json), and
[TRAIN signal-guard abstention](flagging-next-signal-verification.md) with
[9paired-solve archive](results/gain-tv-next-signal.json).
The [419-check image verification](flagging-next-imaging-verification.md),
[actual dirty-image receipt](results/gain-tv-next-imaging.json) and
[paired-image figure](figures/gain-tv-dirty-response.png) reuse saved full-Jones
gains; the [invalid-basis failure](results/gain-tv-next-imaging-invalid-basis.json)
is retained separately. The [TRAIN rank survey](flagging-next-gain-support.md)
finds just one two-cell underidentified bin, not broad unsupported data.
[Real-parser and source-family gates](../history/tools/flagging/run-imaging.sh) protect
the separately fresh imaging step; raw measurements are never overwritten.

[Concurrent follow-up protocol](flagging-concurrent.md), started2026-09-24,
freezes five parallel workstreams before new measurements. All ten scatter
branches and the dependent fit now complete; [suite evidence](results/gain-tv-concurrent.json)
and [read-only checks](results/gain-tv-concurrent-audit.json) record outcomes and
limits. Latest exact run paths remain in [STATE.md](STATE.md).

[Persistent discriminating follow-up](flagging-reportable.md) freezes local
gain-response prediction, complete/omitted sky controls, smoothphaseTV specificity
and supported-data/gauge review. New implementations have separate recipes;
the physical surrogate and smooth-phase replays are measured. The calibration
response control completes a fresh precision-corrected rerun, preserving the
first evaluation failure untouched. [Reportable findings](flagging-findings.md) distinguish
the useful mechanisms from policy/novelty claims. The read-only
[supported-data review](flagging-supported-data.md) identifies a native-sigma
route requiring new provenance/noise controls, and additional parallel-hand
Jones ambiguities. These are not a working flagging-policy success claim.

## Active objective: MeerKAT L-band flagging

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

Main findings: the current policies select no added flags on the unmodified
fixture. Earlier structured search recovers only2.89% of a strong time-burst;
its TV ranking misses that action. The balanced follow-up improves one fresh
seed (TV19.69% versus residual10.10% known-injection recall), but not the other
five injected cases. Its fitted estimator recommends no-change on all six.
A fuller sky improves prediction while slightly increasing TV. Some masks
lower TV while worsening prediction. Outside-injection additions are not proven
false positives in unlabeled real data. No imaging or state-of-the-art advantage
has been established. The tiny fixture is a four-antenna dedicated pointing scan,
not a representative science observation. Smooth physical delay controls have
high rawTV without RFI. Paired omitted-source fits show strong attenuation and
bound-hit spectra, not validated flux/image preservation. The downloaded
61-antenna tiles have zero native cross-hand spectral weights: the current
strict four-correlation protocol accepts no cells, and no flags/weights are
changed to manufacture support.

[Pinned CARACAL strategy/worker inspection](flagging-caracal.md) records the
production-strategy differences, executable full-strategy recipe and four
completed measured controls. The [partial archive](results/gain-tv-caracal-progress.json)
retains its historical two-control/pending-final-audit checkpoint unchanged.
[Representative public data](flagging-public-data.md) records a bounded,
metadata-verified61-antenna primary-calibrator candidate. Actual numeric
acquisition/inspection now has separate evidence; native-MS conversion,
calibration and independent observation transfer remain unmeasured.

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
The concurrent-work implementation checkpoint `1739d48` passes14Rust/323Python
tests, full local checks and all three runtime dependency checks. Actual suite
execution finishes2026-09-24 07:18:30UTC; all13 module hashes/input boundaries
remain frozen. Measured archives distinguish retrospective search, gain-only
controls, conditional source response and real numeric inspection; they do not
establish robust flagging, observation transfer, imaging or SOTA superiority.

## Resume safely

Read [next flagging hypotheses](flagging-next.md) and latest state before editing.
Pinned container environments live under `history/tools/flagging/`
([history/README.md](../history/README.md)); the host Python3.14
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

## Earlier pointing/beam work

[Scientific assessment](status.md), [roadmap](development-roadmap.md),
[novelty boundaries](novelty.md), [smooth pointing](pointing-solutions.md),
[exact Gaussian gauge](gaussian-gauge.md), [antenna beam widths](antenna-beam-widths.md).
These reports have their own assumptions; they are not measured flagging gains.
