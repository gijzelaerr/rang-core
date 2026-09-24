# Research handoff and index

Start with [STATE.md](STATE.md), then [active MeerKAT scope](meerkat-scope.md).
This index routes new collaborators to evidence; it is not a novelty claim.
Updated 2026-09-24. User instructions and Git attribution live in [AGENTS.md](../AGENTS.md).

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
| Baseline TV-conditioned outlier model | [Strategy](flagging.md) | [Baseline](results/gain-tv-flagging.json) | [Pilot](../recipes/tv-flagging.yaml) |
| Six controlled RFI cases and evaluation-only oracles | [Injections](flagging-injections.md) | [Controls](results/gain-tv-injections.json) | [Injections](../recipes/tv-flagging-injections.yaml) |
| Point, official primary and full apparent-scale catalog | [Sky adequacy](flagging-sky.md) | [Sky comparison](results/gain-tv-sky.json) | [Sky](../recipes/tv-flagging-sky.yaml) |
| Genuine QuartiCal MAD and Tricolour kernel | [Comparators](flagging-comparators.md) | [Matched diagnostics](results/gain-tv-comparators.json) | [Comparators](../recipes/tv-flagging-comparators.yaml) |
| Counterfactual patch-action ridge learner | [Action learning](flagging-actions.md) | [Clean](results/gain-tv-actions.json), [contaminated](results/gain-tv-actions-injected.json) | [Actions](../recipes/tv-flagging-actions.yaml) |
| Actual four-worker concurrent replay and preservation audits | [Parallel verification](flagging-parallel.md) | [Suite](results/gain-tv-parallel.json) | [Native scatter](../recipes/tv-flagging-parallel.yaml) |
| Unmodified full native CARACAL Tricolour strategies | [Production verification](flagging-caracal.md) | [Four controls](results/gain-tv-caracal.json) | [Native strategies](../recipes/tv-flagging-caracal.yaml) |
| Matched structured residual/TV rankings, seven controls | [Structured search](flagging-structured.md) | [101 solves](results/gain-tv-structured.json) | [Structured actions](../recipes/tv-flagging-structured.yaml) |
| Geometry-balanced residual/TV/random follow-up | [Balanced search](flagging-balanced.md) | [Seven cases,130 solves](results/gain-tv-balanced.json) | [Balanced](../recipes/tv-flagging-balanced.yaml) |
| Synthetic gain-TV/noise/physical-trend controls | [Uncertainty guidance](flagging-uncertainty.md) | [180 gain-only controls](results/gain-tv-uncertainty.json), not real solver uncertainty | [Uncertainty](../recipes/tv-flagging-uncertainty.yaml) |
| Bounded public numeric visibility acquisition/inspection | [Ingestion](flagging-public-ingestion.md) | [75 object hashes](results/meerkat-public-ingestion.json), [two61-antenna pilots](results/meerkat-public-pilot.json) | [Offline inspection](../recipes/tv-flagging-public.yaml) |
| Paired intrinsic science-signal diagnostic | [Signals](flagging-signal.md) | [16 paired solves and constrained fits](results/gain-tv-signal.json) | [Signals](../recipes/tv-flagging-signal.yaml) |
| Fitted grouped guarded-objective action predictor | [Transfer model](flagging-transfer.md) | [105 labels/frozen predictions](results/gain-tv-transfer.json) | [Transfer](../recipes/tv-flagging-transfer.yaml) |
| Five-track concurrent execution with label-dependent fit | [Frozen protocol](flagging-concurrent.md) | [Completed suite](results/gain-tv-concurrent.json) | [Concurrent](../recipes/tv-flagging-concurrent.yaml) |
| Projected TRAIN-only physical deletion-response surrogate | [Influence design](flagging-influence.md), [independent verification](flagging-influence-verification.md) | [123 retrospective forecasts/labels](results/gain-tv-influence.json), [audit](results/gain-tv-influence-audit.json) | [Influence](../recipes/tv-flagging-influence.yaml) |
| Signed complete/omitted sky and gain-grid response controls | [Response protocol and measurements](flagging-response.md), [independent checks](flagging-response-verification.md) | [Ten frozen controls and preserved retry provenance](results/gain-tv-response.json), [audit](results/gain-tv-response-audit.json) | [Response](../recipes/tv-flagging-response.yaml) |
| Legitimate smooth receiver-phase specificity controls | [Phase design](flagging-equivariance.md), [independent checks](flagging-equivariance-verification.md) | [520 saved-gain replays](results/gain-tv-equivariance.json), [audit](results/gain-tv-equivariance-audit.json) | [Equivariance](../recipes/tv-flagging-equivariance.yaml) |
| Native noise-column and partial-Jones support review | [Supported data](flagging-supported-data.md) | [Read-only diagnostics](results/meerkat-supported-data-candidates.json) | Diagnostic regeneration script, not a calibration recipe |

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
Pinned container environments live under `tools/flagging/`; the host Python3.14
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
