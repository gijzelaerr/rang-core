# Rang core, task H: core-native Stimela recipes and a CLI

Wave 1 task H of [core-parallel-plan.md](core-parallel-plan.md). Protocol
frozen 2026-10-29 in `be63185`, before any recipe or CLI code was written.
Status: **implemented; measured: criteria 1, 3, 5, 6 and 7 pass as frozen;
criterion 2 fails as frozen on wall-time-bearing fields and criterion 4's
text-reference clause fails as frozen; both pass under labelled post-hoc
rules; two recipes failed to parse on their first run and were corrected**
(see the measured result below). A packaging and orchestration step; under
AGENTS.md not a scientific contribution, and no archived result may change
because of it.

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

## Measured result (2026-10-29)

Code written after the freeze: `python/rangtoy/core_cli.py`, six recipe
files (`recipes/core-cabs.yaml` holds the two shared cabs, included by the
five stage recipes with `_include`), `tests/test_core_cli.py`. Runs:
`outputs/core-h-20261029-02-stimela/<stage>` through Stimela (logs in
`logs/<stage>`), `outputs/core-h-20261029-03-cli/<stage>` through the CLI
directly. Every stage was run exactly once through each path, except the two
recipes noted under "Failures as frozen". All five phase 3 core run oracles
were SHA256-verified against `results/core-phase3*.json` before use.

How a recipe is run (from the worktree root, the venv's `python` first on
`PATH`, the two library variables set):

```bash
stimela -s opts.log.dir=outputs/<run>/logs run recipes/core-actions.yaml run-dir=outputs/<run>/actions prepared-dir=outputs/core-phase3-actions-inputs-20261029-01
```

The other four take `prepared-dir` (injections), `source-dir` and
`mirror-dir` (trend), `inputs-dir` (prospective) and `inputs-dir` plus
`uvw-dir` (signal); the archive path defaults to the stage's
`research/results/gain-tv-*.json`. Each recipe runs its stage cab, the
`environment` cab and the `compare` cab, which fails the recipe when the phase
3 comparator fails.

### Criterion 1 and 7: archive reproduction (pass as frozen)

Every stage, through Stimela and through the CLI, passes its phase 3
comparator against the primary and the secondary oracle with exactly the
phase 3 field counts. Worst relative differences (Stimela run; the CLI run
gives the same numbers):

| Stage | Against the archive | Against the host reproduction |
| --- | --- | --- |
| injections | 864 exact, 940 floats 1.3e-14, 24 injection floats 0, 54 distances 1.5e-14 | 858 exact, 928 floats 1.3e-14, 54 distances 9.6e-15 |
| actions | 61 exact, 102 floats 6.6e-15, 24 differences 1.8e-11 | 206 exact, 214 floats 1.6e-14, 24 differences 5.8e-11 |
| trend | 875 exact, 168 floats (TV values pass; slopes under the adopted rule, worst scaled 8.4e-14) | – |
| prospective | 1875 exact, 1239 floats 1.4e-14, 102 differences 7.6e-10 (4.4e-16 absolute, as phase 3b) | 2379 exact, 1599 floats 1.4e-14, 102 differences |
| signal | 261 exact, 208 floats 1.7e-11, 4 differences 1.4e-12 | 261 exact, 208 floats 6.4e-12, 4 differences 8.1e-13 |

These are the phase 3 numbers to the digit. The trend mirror receipt passes
criterion 1 of phase 3 (seven cases, gain validity identical, gains within
1.4e-15) and `flagging_trend.py` has SHA256 `3c578c5e…`, the archived
`module_sha256`. The comparator scripts' SHA256 are recorded in every
`compare-*.json` receipt.

### Criterion 2: same results as the phase 3 core runs (fails as frozen; post-hoc pass)

Against the hash-verified phase 3 core `result.json` files, every numeric
class has worst difference **0** in all five stages, through Stimela and
through the CLI (the Rust core is deterministic). Injections (992 exact,
940 floats, 24 injection floats, 54 distances), actions (242 exact, 214
floats, 24 differences) and trend (875 exact, 168 floats, with the phase 3
trend result wrapped as `{"raw_result": ...}` in
`outputs/core-h-20261029-01-precondition/phase3-trend-as-archive.json`,
since the trend comparator takes the archive layout) pass outright.

**Prospective fails with 4 exact-class failures and signal with 2**, in both
paths: `seconds_total` (a wall time the archive and host oracles never carry
at that path, so the phase 3 exclusion lists do not name it), the three
per-case `frozen_train_responses_sha256` and the signal
`acceptance_digest_core`. The two digests hash JSON that contains wall
times: `_freeze_view` includes `full_training_normals_seconds`
([flagging_prospective.py:368](../python/rangtoy/flagging_prospective.py:368)),
and the frozen acceptance list carries the clean arms' solve `metrics`,
which include `seconds`. They differ between any two runs by construction.
Receipts: `outputs/core-h-20261029-0{2,3}-*/{prospective,signal}-phase3.json`.

*Post-hoc rule (labelled; no rerun):* a field is excluded from criterion 2
when it is a wall time or a digest of a record that contains one. Under
that rule, criterion 2 passes for all five stages with every class at 0.
The phase 3 comparators are not edited; the rule is applied by reading the
receipts.

### Criterion 3: solve counts (pass)

Actions 17, prospective 54 and signal 9 from the results' `actual_QC_solves`;
the trend mirror 7 from `mirror-receipt.json`. The injection result carries
no solve count; counting records that carry a `solver` entry gives 1 clean
reference plus, per case, the contaminated and injected-mask-oracle solves
and the deduplicated policy trials: 6, 6, 5, 6, 6 and 6 trials, 49 solves,
the same accounting as the phase 3 run's result (identical record sets).

### Criterion 4: no QuartiCal (environment clauses pass; text clause fails as frozen)

`environment.json` of every Stimela run and CLI run records, in the venv
`/home/gijsm/Worktrees/rang/core-h-recipes/.venv/bin/python` (Python 3.13.16,
41 distributions: numpy 2.5.4, scipy 1.18.1, stimela 2.1.4, omegaconf 2.4.0,
jax, pytest, ruff and their dependencies):

- `quartical_distribution_installed: false`, `quartical_importable: false`,
  `quartical_modules_loaded: []`, `goquartical_on_path: null`;
- the Stimela logs (`logs/<stage>/log-core-<stage>.<step>.txt`) show each cab
  invoked as `python -u -c ...` with `rangtoy.core_cli.<function>(...)` and
  returning exit code 0, so every cab ran in that environment. No container
  image was needed, so none was built.

**The text clause fails as frozen.** `grep` finds no `quartical` in
`recipes/core-*.yaml`, but 19 of the transitively imported `rangtoy` modules
contain the string: `core_cli` itself (in the `environment` check that looks
for it), the phase 3 drivers and `core_workflow` and `core` (docstrings that
say what was ported from QuartiCal), and the frozen campaign modules the
drivers import for shared decision functions (`flagging_workflow`,
`flagging_injections`, `flagging_prospective`, `flagging_signal_guard`,
`flagging_response`, `flagging_actions`, `flagging_caracal`,
`flagging_comparators`, `flagging_signal`, `flagging_structured`,
`flagging_prepared`, `flagging`), whose `goquartical` subprocess paths exist
but are never called by the core drivers. The list is in every
`environment.json` under `modules_with_quartical_references`. The clause as
written counts documentation and dormant code; it was a poor proxy.

*Post-hoc rule (labelled; no rerun):* a dependency on QuartiCal is a loaded
`quartical` module or a `goquartical` subprocess. Neither occurred: no
`quartical` module is loaded in any run, the package is not installed, and
with `goquartical` absent from `PATH` any subprocess call would have failed
the stage. Under that rule criterion 4 passes. `tests/test_core_cli.py`
keeps the literal check where it is meaningful: the core recipes name no
solver, and `core_cli.py` names it only inside the environment check.

### Criterion 5: frozen files untouched (pass)

The branch adds files only (`git status`: `core_cli.py`, the six recipes,
the test, this report). `recipes/tv-flagging-*.yaml`, `tools/flagging/`,
the phase 3 drivers and comparators, `core.py` and `flagging_trend.py` have
no diff against `9e12326`.

### Criterion 6: no side effects (pass)

Every `side-effects.json`: inputs unchanged (3978 files for injections, 2
for actions, 11972 for the concurrent suite, 30 for the mirror, 501 for the
campaign inputs, 505 with the UVW export) and `git status` unchanged; the
stage steps wrote only `result.json` (the trend mirror writes the seven
`experiments/<case>` trees and its receipt, and the frozen trend module its
checkpoints and `config.json`, as in phase 3). The later `environment` and
`compare` steps add `environment.json` and `compare-archive.json` to the run
directory only.

### Failures as frozen, and what was changed after the freeze

- `core-prospective.yaml` and `core-signal.yaml` failed to load on their
  first Stimela run (exit 2 after 0.8 s and 1.0 s): the `info:` text of an
  input contained `{clean,...}` inside a YAML flow mapping. The strings were
  quoted and reworded; the logs of the failed loads are kept as
  `*.stimela.failed-yaml.log`. No stage code changed; the stage results are
  from the reruns.
- Criteria 2 and 4 as described above. No solve was rerun for either.
- A static recipe test and the solver-name test in `tests/test_core_cli.py`
  were adjusted twice while they were written (a regex overlap, and the
  realisation that `core_cli` must name the solver to check for it).

### Criterion 8: cost (reported)

Wall and peak RSS from `/usr/bin/time` around the whole `stimela` process
and around `python -m rangtoy.core_cli`. The Stimela and CLI batches ran at
the same time as each other and beside seven sibling sessions on the shared
16 cores, so the prospective, signal and trend times are 1.5–2× the phase 3
figures for load reasons, not Stimela's: within each Stimela run the stage
cab's own `seconds` is 8.0 s (actions), 25.6 s (injections), 16.6 + 60.0 s
(trend mirror and ablation), 50.1 s (prospective) and 54.7 s (signal), and
the `environment` and `compare` cabs take 0.1–0.2 s each.

| Stage | Stimela recipe | Direct CLI | Phase 3 driver | Stimela overhead (recipe wall minus cab seconds) |
| --- | ---: | ---: | ---: | ---: |
| actions | 9.3 s, 254 MB | 8.4 s, 245 MB | 9.2 s, 234 MB | 1.2 s |
| injections | 27.4 s, 752 MB | 26.6 s, 728 MB | 24.6 s, 738 MB | 1.8 s |
| trend (mirror + ablation) | 79.9 s, 355 MB | 18.5 + 60.4 s, 215 / 356 MB | 14.5 + 31.3 s | 3.3 s |
| prospective | 51.9 s, 568 MB | 50.8 s, 564 MB | 32.8 s, 548 MB | 1.8 s |
| signal | 56.7 s, 840 MB | 57.8 s, 837 MB | 34.5 s, 817 MB | 2.0 s |

Stimela adds one to three seconds per recipe (process start, validation,
three interpreter launches); the stage cost is the phase 3 driver's.

## What this shows

The five phase 3 stages run as Stimela2 recipes, and as one CLI, on the
Rust core in a venv that has never had QuartiCal, and reproduce the
gain-tv archives and the host reproductions to the phase 3 digits, with the
phase 3 comparators unchanged and the deterministic core giving the phase 3
core results exactly. The frozen recipes keep calling `goquartical`; the
core recipes beside them do not need it. What remains outside this task:
the stages still start from host-prepared inputs (`state.npz` from the
frozen `prepare` steps and the once-only UVW export), so an end-to-end
core-native campaign from a Measurement Set or zarr still needs the MS
reader (task E) or the zarr path of section 6; and a container image for the
core recipes was not needed and was not built.

## Timings (every tool run of this task)

| When | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-29 | `uv venv` + `uv pip install -e '.[pointing,beam,test]' ruff` (public PyPI) | 26.0 s | 69 MB | `python3 -m venv` fails on WSL (no `ensurepip`); uv chose its managed Python 3.13 |
| 2026-10-29 | `uv pip install stimela==2.1.4` | 3.8 s | – | pulls omegaconf 2.4.0; no QuartiCal |
| 2026-10-29 | `cargo +1.93 build --release` core crate, `CARGO_BUILD_JOBS=4` | 1.8 s | 193 MB | shared cargo cache warm |
| 2026-10-29 | `cargo +1.93 build --release` root crate | 2.0 s | 194 MB | |
| 2026-10-29 | five phase 3 comparators, host versus archive (precondition) | 0.02–0.03 s each | 17 MB | `outputs/core-h-20261029-01-precondition` |
| 2026-10-29 | ten phase 3 comparators, phase 3 core runs versus archive and host | 0.01–0.02 s each | 17 MB | same directory, `core3-*` |
| 2026-10-29 | `pytest tests/test_core_cli.py` (8 tests), three times while writing | 0.2 s | – | |
| 2026-10-29 | Stimela `core-actions` | 9.3 s | 254 MB | first recipe run, passed first time |
| 2026-10-29 | Stimela `core-injections` | 27.4 s | 752 MB | |
| 2026-10-29 | Stimela `core-trend` | 79.9 s | 355 MB | concurrent with the CLI batch |
| 2026-10-29 | Stimela `core-prospective`, failed YAML load, then rerun | 0.8 s; 51.9 s | 73 MB; 568 MB | |
| 2026-10-29 | Stimela `core-signal`, failed YAML load, then rerun | 1.0 s; 56.7 s | 73 MB; 840 MB | |
| 2026-10-29 | CLI actions, injections, trend-mirror, trend, prospective, signal | 8.4, 26.6, 18.5, 60.4, 50.8, 57.8 s | 245, 728, 215, 356, 564, 837 MB | concurrent with the Stimela batch |
| 2026-10-29 | 23 comparator runs through `core_cli compare` (archive, host, phase 3 oracles) | 0.1–0.3 s each | – | receipts beside the results |
| 2026-10-29 | `bash tools/check-all.sh` (cargo, clippy, fmt, ruff, 676 pytest tests) | 3042 s (pytest 3027 s) | 1999 MB | once, before the final commit; PASS, concurrent with sibling sessions |

## For the coordinator

- `pyproject.toml`: add under `[project.scripts]`
  `rang-core = "rangtoy.core_cli:main"` (the branch does not touch
  `pyproject.toml`; `python -m rangtoy.core_cli` works without it).
- `research/tool-timings.md`: the rows of the timings table above.
- `research/README.md` and `STATE.md`: this report as the task H entry;
  status "implemented; measured", with the two labelled post-hoc rules.
- Optional `[project.optional-dependencies]` extra `recipes = ["stimela==2.1.4"]`
  so the core recipes can be installed without the `flagging` extra that
  pins QuartiCal.
- Note for the environment: on this WSL host `python3 -m venv` fails
  (`ensurepip` missing); `uv venv` was used, which picked a uv-managed
  Python 3.13.16 rather than the system 3.14.
