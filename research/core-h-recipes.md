# Rang core, task H: core-native Stimela recipes and a CLI

Wave 1 task H of [core-parallel-plan.md](core-parallel-plan.md). Protocol
frozen 2026-10-29 in the commit that adds this file, before any recipe or CLI
code was written. Status: **proposed; protocol frozen**. A packaging and
orchestration step; under AGENTS.md not a scientific contribution, and no
archived result may change because of it.

## Question

Can the five phase 3 stages (injections, actions, trend, prospective,
signal) be run through Stimela2 recipes and one command-line entry point on
the Rust core, in an environment that has no QuartiCal, and reproduce the
phase 3 archives ([core-phase3.md](core-phase3.md),
[core-phase3-actions.md](core-phase3-actions.md),
[core-phase3-trend.md](core-phase3-trend.md), [core-phase3b.md](core-phase3b.md),
[core-phase3c-b.md](core-phase3c-b.md)) under the criteria those phases
used? The frozen recipes under `recipes/tv-flagging-*.yaml` still call
`goquartical` inside container images; they are not edited.

## Design

- `python/rangtoy/core_cli.py`: one function per stage (`injections`,
  `actions`, `prospective`, `signal`, `trend_mirror`), each calling the
  phase 3 driver (`rangtoy.core_injections.run`, `core_actions.run`,
  `core_prospective.run`, `core_signal.run`, and for the trend mirror the
  seven core baseline solves of `examples/build_core_trend_mirror.py`) and
  writing the same side-effect audit as `examples/run_core_campaign.py`
  (`side-effects.json`: input sizes and times, `git status`, files written).
  The trend ablation itself is the frozen `rangtoy.flagging_trend.run`,
  unedited, on the mirror, as in phase 3. A `compare` function runs the phase
  3 comparator script of the stage (`examples/compare_core_<stage>.py`)
  unchanged, with `runpy`, and records the script's SHA256 in the receipt. An
  `environment` function writes `environment.json`: interpreter, installed
  distributions, whether `quartical` imports and whether `goquartical` is on
  `PATH`. `python -m rangtoy.core_cli <stage> ...` exposes all of them with
  `argparse`.
- Recipes `recipes/core-injections.yaml`, `core-actions.yaml`,
  `core-trend.yaml`, `core-prospective.yaml` and `core-signal.yaml`, with
  python-flavour cabs on the native backend calling `rangtoy.core_cli.*`,
  each with an `environment` step, the stage step(s) and a `compare` step
  against the archive. The `core-` prefix keeps them outside the
  `tv-flagging*.yaml` glob of `flagging_next.source_receipts`, so the frozen
  campaign receipts are unaffected.
- No `pyproject.toml` change in this branch; the desired
  `[project.scripts]` entry is listed under "For the coordinator".
- Environment: the worktree venv is built as README describes, plus
  `stimela==2.1.4` from public PyPI, and nothing else; QuartiCal is never
  installed. `RANG_CORE_LIB` points at the built `core/target/release/librang_core.so`
  and `RANG_TOY_LIB` at `target/release/librang_toy.so`, so no cab builds
  anything.

## Inputs (frozen)

Exactly the phase 3 inputs, read only:

| Stage | Inputs | Primary oracle | Secondary oracle | Phase 3 core run |
| --- | --- | --- | --- | --- |
| injections | `outputs/tv-injections-wsl-20261029-01` (`state.npz`, `manifest.json`, `cases/*`) | `results/gain-tv-injections.json` | `tv-injections-wsl-20261029-01/result.json` | `outputs/core-phase3-20261029-02/result.json` |
| actions | `outputs/core-phase3-actions-inputs-20261029-01` | `results/gain-tv-actions.json` | `tv-flagging-actions-wsl-20261029-01/result.json` | `outputs/core-phase3-actions-20261029-01/result.json` |
| trend | `outputs/tv-concurrent-wsl-20261029-01/experiments/<case>` (seven cases) | `results/gain-tv-next-trend.json` (`raw_result`) | – (the comparator takes the archive layout only) | `outputs/core-trend-20261029-01/result.json` |
| prospective | `outputs/tv-next-wsl-20261029-01/inputs/cases/{clean,time-burst-seed107,time-burst-seed109}` | `results/gain-tv-next-prospective.json` | `tv-next-wsl-20261029-01/experiments/prospective/result.json` | `outputs/core-phase3b-20261029-01/result.json` |
| signal | the two seed cases above and the UVW export `outputs/core-phase3c-b-uvw-20261029-01` | `results/gain-tv-next-signal.json` | `tv-next-wsl-20261029-01/experiments/signal/result.json` | `outputs/core-phase3c-b-20261029-01/result.json` |

The phase 3 core runs are oracles only if their `result.json` SHA256 equals
the `result_sha256` recorded in the matching `results/core-phase3*.json`
(for injections, the post-hoc run `-02`).

## Precondition: comparators on archive versus host reproduction

Run 2026-10-29 before freezing, receipts in
`outputs/core-h-20261029-01-precondition`. The phase 3 comparators take a
core-layout result in the first slot and an oracle in the second.

| Stage | Host reproduction as first argument, archive as oracle | Phase 3 core run against archive / against host |
| --- | --- | --- |
| injections | cannot run: the host `result.json` lacks the top-level `post_selection_candidate_recovery` the core driver writes (the comparator reads the host's sibling `candidate-recovery.json` only in the oracle slot) | pass / pass (864 and 858 exact, 940 and 928 floats within 1.3e-14, 54 distances) |
| actions | cannot run: the host `result.json` has no top-level `configuration` | pass / pass (61 and 206 exact, 102 and 214 floats within 1.6e-14, 24 differences within 5.8e-11) |
| prospective | **pass** as frozen: 1875 exact, 1239 floats within 9.6e-15, 102 differences within 1.5e-11 | pass / pass |
| signal | **pass** as frozen: 261 exact, 208 floats within 1.7e-11, 4 differences within 2.2e-12 | pass / pass |
| trend | **fails criterion 3 as frozen** (28 reference-antenna slopes, 0.61 relative), **passes** post-hoc criterion 3b | pass with 3b / the comparator takes the archive layout only |

Consequences, fixed now: the three phase 3 post-hoc rules are adopted as
frozen rules of this task (injections: the driver writes the three
archive-only fields; actions: `action.score` is a float; trend: slopes scaled
by the largest slope of the axis). Where the swapped direction cannot run,
the phase 3 core run is the third oracle, as in the table above.

## Acceptance criteria (frozen)

1. **Archive reproduction through the recipes.** For each stage, the
   `result.json` written by running the core recipe with Stimela passes the
   stage's phase 3 comparator against the primary oracle, with the phase 3
   classes and tolerances and the adopted rules above, and the number of
   compared fields per class equals the phase 3 report's (injections 864
   exact, 940 floats, 24 injection floats, 54 distances; actions 61, 102, 24;
   prospective 1875, 1239, 102; signal 261, 208, 4; trend 875, 168). Where a
   secondary oracle exists, the comparator passes against it too. For trend,
   the mirror receipt's criterion 1 passes and `flagging_trend.py` has the
   archived `module_sha256`.
2. **Same results as the phase 3 core runs.** The same comparator passes with
   the phase 3 core run's `result.json` (SHA256-verified) as oracle. The worst
   difference of every class is reported; equality to 0 is expected but not
   gated.
3. **Solve counts.** Injections 49, actions 17, prospective 54, signal 9,
   trend mirror 7, as in the phase 3 reports.
4. **No QuartiCal.** In the environment that runs the recipes,
   `import quartical` fails, no `quartical` distribution is installed and
   `goquartical` is not on `PATH`; `environment.json` written by the
   `environment` step records all three. The core recipes and every module
   `rangtoy.core_cli` imports contain no reference to `quartical` or
   `goquartical` (`grep` over `recipes/core-*.yaml` and the transitive
   `rangtoy` imports of `core_cli`, listed in the receipt). The Stimela log
   of each run shows every cab ran in that environment.
5. **Frozen recipes untouched.** `git diff` of `recipes/tv-flagging-*.yaml`,
   `tools/flagging/` and the phase 3 drivers, comparators and `core.py` is
   empty on the branch.
6. **No side effects.** Every input directory is unchanged (size and
   modification time of every file) and `git status` is unchanged; each stage
   writes only its run directory. The audit is `side-effects.json`.
7. **CLI without Stimela.** `python -m rangtoy.core_cli <stage>` run directly,
   once per stage, produces a result that passes criterion 1 as well.
8. **Cost (reported, not gated).** Wall time and peak RSS of each recipe run
   with `/usr/bin/time`, next to the direct CLI run and the phase 3 driver
   times (24.6 s, 9.2 s, 14.5 + 31.3 s, 32.8 s, 34.5 s), so that the Stimela
   overhead is visible. Every tool run of this task is timed and logged
   below.

The task is reported as passed only if criteria 1–7 pass as frozen; any
failure is recorded here with its numbers and is not hidden. Post-hoc steps
are labelled.

## Timings (every tool run of this task)

| When | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-29 | `uv venv` + `uv pip install -e '.[pointing,beam,test]' ruff` (public PyPI) | 26.0 s | 69 MB | `python3 -m venv` fails on WSL (no `ensurepip`); uv chose its managed Python 3.13 |
| 2026-10-29 | `uv pip install stimela==2.1.4` | 3.8 s | – | pulls omegaconf 2.4.0; no QuartiCal |
| 2026-10-29 | `cargo +1.93 build --release` core crate, `CARGO_BUILD_JOBS=4` | 1.8 s | 193 MB | shared cargo cache warm |
| 2026-10-29 | `cargo +1.93 build --release` root crate | 2.0 s | 194 MB | |
| 2026-10-29 | five phase 3 comparators, host versus archive (precondition) | 0.02–0.03 s each | 17 MB | `outputs/core-h-20261029-01-precondition` |
| 2026-10-29 | ten phase 3 comparators, phase 3 core runs versus archive and host | 0.01–0.02 s each | 17 MB | same directory, `core3-*` |
