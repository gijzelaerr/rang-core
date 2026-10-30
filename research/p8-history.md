# P8: retire frozen recipes, containers and recipe-only modules to `history/`

Big plan wave 2 task P8 ([big-plan.md](big-plan.md); proposal in
[simplification-review.md](simplification-review.md) section 3 "P8", section 4
table row). Branch `p8-history` from origin/main `43dc3c7`, worktree
`~/Worktrees/rang/p8-history`. Status: **protocol frozen before any move**
(this section); the moves, checks and timings follow in later sections.

## Protocol (frozen before moving)

### What moves (70 files, 6,258 lines at `43dc3c7`)

Every file is moved with `git mv` so that `git log --follow` keeps its
history, and stays byte-identical: the sha256 of every file is recorded
before the move and compared after it (campaign receipts hash these files).

| Group | Files | Lines | From | To |
| --- | ---: | ---: | --- | --- |
| Frozen Stimela recipes | 23 | 992 | `recipes/tv-flagging*.yaml` | `history/recipes/` |
| Container builds, wrappers, fetch scripts, preflight, locks | 34 | 1,021 | `tools/flagging/` (8 Dockerfiles, 3 `requirements.lock`, 16 `run-*.sh` incl. `comparators/` and `sky/`, 4 `fetch-luno-*.sh`, `preflight.py`, `sky/verify_prediction.py`) | `history/tools/flagging/` (same subtree) |
| Recipe-only Python modules | 6 | 2,626 | `python/rangtoy/flagging_{concurrent,parallel,provenance,public,transfer,uncertainty}.py` | `history/python/` |
| Their tests, and the wrapper preflight test | 7 | 1,619 | `tests/test_flagging_{concurrent,parallel,provenance,public,transfer,uncertainty}.py`, `tests/test_flagging_preflight.py` | `history/tests/` |

S1 counted `tools/flagging/` as 35 files and 1,040 lines; `git ls-files`
gives 34 and 1,021 at `43dc3c7`. The difference is not `tools/ms-reader/`
(1 file, 9 lines). `tools/ms-reader/Dockerfile` **stays**: it builds the
python-casacore oracle of task E (`check_ms_reader.py`'s archived dump), not a
frozen campaign. `test_flagging_preflight.py` is added to S1's list because its
subject (`preflight.py` and the `run-*.sh` wrappers) moves.

Three test functions in live test files test moved files only; they are cut
out verbatim into new files under `history/tests/` (no `git mv` possible for a
part of a file; each new file names its origin):

- `test_flagging_balanced.py::test_balanced_wrapper_fails_before_cache_logs_or_docker`
  (copies `tools/flagging/run-balanced.sh` and `preflight.py`);
- `test_flagging_signal.py::test_signal_wrapper_invalid_namespaces_stop_before_cache_logs_or_docker`
  (copies `run-signal.sh` and `preflight.py`);
- `test_flagging_next.py::test_native_scatter_recipe_matches_runtime_cabs_and_frozen_plan`
  (reads `recipes/tv-flagging-next.yaml`).

`tests/test_core_cli.py` keeps its check that the 23 frozen recipes exist and
share no name with the core ones; its glob is repointed at `history/recipes`.

`examples/oracle_wsclean_predict.py` (the task 3c-a africanus oracle, run in
`rang-flagging:local`) puts `tools/flagging/sky` on `sys.path` for
`verify_prediction.read_catalog`; that one line is repointed at
`history/tools/flagging/sky`. Its archive (`core-phase3c-oracle-20261029-01`)
hashes `oracle.npz` and the catalogue, not the script.

### Archive or research file of each moved item's last run

| Moved item | Last run documented in | Archive |
| --- | --- | --- |
| `tv-flagging.yaml`, `run-pilot.sh`, base `Dockerfile`, `requirements.lock` | [flagging.md](flagging.md) | `results/gain-tv-flagging.json` |
| `tv-flagging-injections.yaml`, `run-injections.sh` | [flagging-injections.md](flagging-injections.md) | `results/gain-tv-injections.json` |
| `tv-flagging-sky.yaml`, `sky/` (Dockerfile, lock, `run-pilot.sh`, `verify_prediction.py`) | [flagging-sky.md](flagging-sky.md) | `results/gain-tv-sky.json` |
| `tv-flagging-comparators.yaml`, `comparators/` | [flagging-comparators.md](flagging-comparators.md) | `results/gain-tv-comparators.json` |
| `tv-flagging-actions.yaml` | [flagging-actions.md](flagging-actions.md) | `results/gain-tv-actions.json`, `gain-tv-actions-injected.json` |
| `tv-flagging-parallel.yaml`, `parallel/Dockerfile`, `run-parallel.sh`, `flagging_parallel.py` | [flagging-parallel.md](flagging-parallel.md) | `results/gain-tv-parallel.json` |
| `tv-flagging-caracal.yaml`, `run-caracal.sh` | [flagging-caracal.md](flagging-caracal.md) | `results/gain-tv-caracal.json` |
| `tv-flagging-structured.yaml`, `run-structured.sh` | [flagging-structured.md](flagging-structured.md) | `results/gain-tv-structured.json` |
| `tv-flagging-balanced.yaml`, `run-balanced.sh` | [flagging-balanced.md](flagging-balanced.md) | `results/gain-tv-balanced.json` |
| `tv-flagging-uncertainty.yaml`, `flagging_uncertainty.py` | [flagging-uncertainty.md](flagging-uncertainty.md) | `results/gain-tv-uncertainty.json` |
| `tv-flagging-public.yaml`, `run-public.sh`, `flagging_public.py` | [flagging-public-ingestion.md](flagging-public-ingestion.md) | `results/meerkat-public-ingestion.json`, `meerkat-public-pilot.json` |
| `tv-flagging-signal.yaml`, `run-signal.sh` | [flagging-signal.md](flagging-signal.md) | `results/gain-tv-signal.json` |
| `tv-flagging-transfer.yaml`, `flagging_transfer.py` | [flagging-transfer.md](flagging-transfer.md) | `results/gain-tv-transfer.json` |
| `tv-flagging-concurrent.yaml`, `run-concurrent.sh`, `flagging_concurrent.py` | [flagging-concurrent.md](flagging-concurrent.md) | `results/gain-tv-concurrent.json`, `-audit.json` |
| `tv-flagging-influence.yaml`, `run-influence.sh` | [flagging-influence.md](flagging-influence.md) | `results/gain-tv-influence.json`, `-audit.json` |
| `tv-flagging-response.yaml`, `response/Dockerfile`, `run-response.sh` | [flagging-response.md](flagging-response.md) | `results/gain-tv-response.json`, `-audit.json` |
| `tv-flagging-equivariance.yaml`, `run-equivariance.sh` | [flagging-equivariance.md](flagging-equivariance.md) | `results/gain-tv-equivariance.json`, `-audit.json` |
| `tv-flagging-next.yaml`, `next/Dockerfile`, `run-next.sh` | [flagging-next-results.md](flagging-next-results.md), [flagging-next-summary.md](flagging-next-summary.md) | `results/gain-tv-next.json`, `gain-tv-next-runtime.json` and the five `gain-tv-next-*` track archives |
| `tv-flagging-trend.yaml` | [flagging-trend.md](flagging-trend.md) | `results/gain-tv-next-trend.json` |
| `tv-flagging-prospective.yaml` | [flagging-next-prospective-verification.md](flagging-next-prospective-verification.md) | `results/gain-tv-next-prospective.json` |
| `tv-flagging-signal-guard.yaml` | [flagging-next-signal-verification.md](flagging-next-signal-verification.md) | `results/gain-tv-next-signal.json` |
| `tv-flagging-provenance.yaml`, `flagging_provenance.py` | [flagging-supported-provenance.md](flagging-supported-provenance.md), [flagging-next-provenance-verification.md](flagging-next-provenance-verification.md) | `results/gain-tv-next-provenance.json` |
| `tv-flagging-imaging.yaml`, `imaging/` and `next-imaging/` Dockerfiles, `run-imaging.sh` | [flagging-imaging.md](flagging-imaging.md) | `results/gain-tv-next-imaging.json`, `-invalid-basis.json`, `-audit.json` |
| `fetch-luno-probe.sh`, `fetch-luno-text.sh` | [flagging-luno-candidate.md](flagging-luno-candidate.md) | `results/meerkat-luno-candidate.json` |
| `fetch-luno-support.sh` | [flagging-luno-support.md](flagging-luno-support.md) | `results/meerkat-luno-support.json` (replaced live by `core_fetch`, task G) |
| `fetch-luno-solve.sh`, `run-luno-solve.sh` | [flagging-luno-solved.md](flagging-luno-solved.md) | `results/meerkat-luno-solved.json` |
| `preflight.py` | the wrappers above (sourced by every `run-*.sh`) | – |

### `history/` layout

```
history/README.md          what is here, why, which archive each item made, how to re-run
history/recipes/           the 23 tv-flagging*.yaml recipes
history/tools/flagging/    the former tools/flagging/ subtree, unchanged
history/python/            the 6 recipe-only modules (flat; they were rangtoy.* submodules)
history/tests/             their tests, the preflight test and the 3 cut-out test functions
```

`history/python/` has no `__init__.py` and is on no path: the moved modules
are not importable as `rangtoy.*` (checked in a fresh process). Re-running a
frozen campaign is done from the commit it recorded (or `43dc3c7`, the last
commit with everything in place), never from `history/`: the receipts hash
files at their original paths.

### What stays

- Every `research/*.md` and every `research/results/*.json`, unchanged except
  one added pointer line (below); the pinned image names
  (`rang-flagging*:local`) in research notes are not touched.
- All Rust, all `core_*` modules, every frozen module the core imports
  (including `flagging_sky.py` and its test: `validate_core_phase3c_a.py`
  imports `point_catalog_predict`), the 7 `recipes/core-*.yaml` (their
  comments name the frozen recipe each sits beside; the Stimela logs of task H
  record those recipes, so they are not edited), `tools/check-all.sh`,
  `tools/core-j-suite.sh`, `tools/ms-reader/`.
- Frozen modules keep the strings that name moved paths, unedited:
  `flagging_workflow.py` (hashes `recipes/tv-flagging.yaml`,
  `tools/flagging/Dockerfile`, `tools/flagging/requirements.lock` while
  preparing a QuartiCal run), `flagging_next.py` (`source_receipts()` globs
  both trees; `run_track("provenance")` imports `rangtoy.flagging_provenance`
  by name), `flagging_sky.py` (runs `tools/flagging/sky/verify_prediction.py`
  in the Crystalball step). All three are container-only paths; no live
  chain reaches them (S1 coverage). They are dangling by design after the
  move and are listed in `history/README.md`.

### Docs

- Navigation links that would 404 are repointed at `history/`: `README.md`
  (pilot recipe link, repository guide), `research/README.md` (recipe column,
  wrapper link, container line), and `CONTRIBUTING.md` / `examples/README.md`
  only where they name a moved path. Every changed line is listed for the
  coordinator.
- Each research note that names a moved path gains one line after its
  status paragraph: "Paths: the frozen recipes, `tools/flagging/` and the
  recipe-only modules named here moved to [`history/`](../history/README.md)
  on 2026-10-30 (task P8)." The historical text is not rewritten. Coordinator
  files (`STATE.md`, `upstream-notes.md`, `big-plan.md`) are left to the
  coordinator; `simplification-review.md` describes the pre-move tree and
  gets the same pointer line.

### Lint and test collection decisions

- **ruff**: `history/` is excluded deliberately (`[tool.ruff] extend-exclude
  = ["history"]` in `pyproject.toml`, with a comment): the files are frozen and
  hashed, so a newer ruff must never reformat them. `tools/check-all.sh`
  already passes explicit paths (`python examples tests`).
- **pytest**: `history/tests` is not collected (`testpaths = ["tests"]`
  already). The moved tests import `rangtoy.flagging_{concurrent,...}`, which
  no longer exists, so they cannot pass without putting the modules back;
  they ran green at `43dc3c7` (S1's 739 tests). The cut-out wrapper tests need
  no container but test files that no live chain uses.

### Acceptance

1. Byte identity: the sha256 manifest of the 70 files before and after the
   move is identical (paths aside).
2. `python -c "import rangtoy.flagging_X"` raises `ModuleNotFoundError` for
   each of the six, in a fresh process; `grep` finds no live import of them.
3. `bash tools/check-all.sh` passes (once, before the final commit).
4. S1's timed suite (`results/profiles-20261030/scripts/suite.sh`, with the
   worktree and `S=` adjusted) re-runs all 29 live steps with exit 0, and the
   S1 `-08` validators (phase 1 as archived: 4 fails, 4b passes; phase 3c-a,
   which imports `flagging_sky`; task G fetch checker) give their archived
   verdicts; `compare_core_backends.py` between S1's suite
   `outputs/simplification-review-20261030-01` and this one finds no
   numerical difference (non-numerical path and layout items are listed).
5. `grep -rn "tools/flagging\|tv-flagging-" --include=*.py --include=*.sh
   --include=*.yaml python examples tests tools recipes` finds no live use of
   an old path. Expected and whitelisted hits (each listed with file:line in
   the results): the unedited frozen modules above; docstrings and comments
   (`recipes/core-*.yaml`, `examples/build_luno_ms.py`,
   `examples/check_luno_sigma.py`, `examples/extract_luno_support.py`); the
   synthetic fixture of `test_flagging_next.py::test_source_receipts_*`, which
   builds a fake tree in `tmp_path` to test the frozen `source_receipts()`;
   and the repointed `history/` paths.
