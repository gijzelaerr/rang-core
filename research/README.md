# Research handoff and index

Start with [STATE.md](STATE.md), then [active MeerKAT scope](meerkat-scope.md).
This index routes new collaborators to evidence; it is not a novelty claim.
Updated 2026-09-23. User instructions and Git attribution live in [AGENTS.md](../AGENTS.md).

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

Main findings: the current policies select no added flags; a strong time-burst
injection oracle benefits the guarded objective, but existing proposals miss
it. A fuller sky improves prediction while slightly increasing TV. Some masks
lower TV while worsening prediction. Outside-injection additions are not proven
false positives in unlabeled real data. No imaging or state-of-the-art advantage
has been established. The tiny fixture is a four-antenna dedicated pointing scan,
not a representative science observation.

[Pinned CARACAL strategy/worker inspection](flagging-caracal.md) records the
production-strategy differences and the next verification design.

Latest verified checkpoint: 14 Rust/171 Python tests, full local checks, six
recipe dry-runs, actual concurrent execution and 24 read-only prepared-input
audits. Commits `35e763b` and `f782921` were pushed to origin/main on 2026-09-23.
Further development must record its own checks rather than inherit these counts.

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
