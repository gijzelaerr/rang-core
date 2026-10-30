# P8: retire frozen recipes, containers and recipe-only modules to `history/`

Big plan wave 2 task P8 ([big-plan.md](big-plan.md); proposal in
[simplification-review.md](simplification-review.md) section 3 "P8", section 4
table row). Branch `p8-history` from origin/main `43dc3c7`, worktree
`~/Worktrees/rang/p8-history`. Status: **done, measured.** The protocol below was frozen and committed
(`ce6ff94`) before any move; results, timings and the coordinator notes follow it.

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

## Results (measured 2026-10-30)

Moves and edits are in commit `8cb2665` (on top of the protocol commit
`ce6ff94`); this section was added afterwards (document only).

### What changed

- **70 files moved** with `git mv` exactly as listed in the protocol; the
  sha256 manifest of all 70 is identical before and after (6,258 lines).
- **Three test functions cut** verbatim into
  `history/tests/test_flagging_{balanced_wrapper,signal_wrapper,next_recipe}.py`
  (102 lines; 9 collected tests), with the now unused imports removed from the
  three live files by `ruff --select F401 --fix` and one blank line by
  `ruff format`.
- `tests/test_core_cli.py`: `FROZEN_RECIPES` globs `history/recipes` (the
  count of 23 and the no-shared-name check are kept).
- `examples/oracle_wsclean_predict.py`: `sys.path` entry
  `tools/flagging/sky` → `history/tools/flagging/sky` (container-only oracle).
- `pyproject.toml`: `[tool.ruff] extend-exclude = ["history"]` with a comment.
- `history/README.md` (what, why, archive per item, how to re-run).
- Docs: `README.md`, `CONTRIBUTING.md`, `research/README.md` (lines listed
  under "For the coordinator"); `examples/README.md` names no moved path and is
  unchanged. 33 research notes gain the pointer line (the 31 under
  `research/` that name a moved path, `simplification-review.md` among them,
  and the two `research/upstream-issues/` drafts); `STATE.md`,
  `upstream-notes.md` and `big-plan.md` are left to the coordinator.

Live tree (`python`, `examples`, `tests`, `tools`, `recipes`, `src`, `core`
without `core/data`): **267 → 197 files, 59,145 → 52,772 lines (−6,373)**:
the 6,258 moved lines plus the 115 lines cut from three test files. Recipes
30 → 7, Dockerfiles 9 → 1 (`tools/ms-reader`), Python modules in
`python/rangtoy` 51 → 45. `history/` holds 74 files and 6,482 lines. Tests:
**739 → 555 collected** (175 in the seven moved files plus 9 cut out; collected on
the main checkout at `35e3cd5`, where these files equal `43dc3c7`'s; W1's
check-all on main reports the same 739).

### Acceptance

1. **Byte identity: pass** (`manifest.sh before|after`, 70 hashes equal).
2. **Not importable: pass.** `python -c "import rangtoy.flagging_X"` raises
   `ModuleNotFoundError` for all six in a fresh process. The only remaining
   name in the live tree is the frozen dispatch table of `flagging_next.py:104`
   (`"provenance": "flagging_provenance"`), reached only by the frozen
   `tv-flagging-next` recipe; its unit test monkeypatches `import_module`.
3. **`bash tools/check-all.sh`: PASS** on `8cb2665` (root 19 and core 47 Rust
   tests, clippy, fmt, extension build, ruff, ruff-format, diff-check, 555
   pytest passed in 663 s); 689.5 s wall, 1.72 GB peak; load 6 → 23 (sibling
   sessions). Log `outputs/p8-history-20261030-04-check-all.log`.
4. **S1 live-chain suite (`outputs/p8-history-20261030-01`): 28 of 29 steps
   exit 0 with their archived verdicts**: K precondition and checker pass;
   the offline K replay equals the archived gains, dirty images and PSFs of
   three arms hash for hash (`equality_with_archive` all true); phase 2 all
   pass; F bench check; actions, injections, prospective, signal and trend
   comparators `passed: true`; B, C, D, E and I pass. The 29th,
   `section6-check`, passes 10 of 11 criteria and fails `8_cost`, the
   wall-time limit (2.0 s excluding decode): 2.57 s at load 19–20 here and
   7.88 s in a re-run (`-05`) at load 14–20, against 1.46 s in S1's run.
   It is the same load-dependent criterion that task J's cold run failed
   (S1 section 1.4); the science criteria are unchanged and P8 changed no
   code on that path. Post-hoc A/B (labelled post-hoc; not in the frozen
   protocol): `prototype_section6.py` + `check_section6.py` alternated
   between a detached pre-move worktree at `43dc3c7` and this branch,
   three pairs pre-first (`-07`, load 26–30) and three post-first (`-08`,
   load 37–46). Every one of the 12 runs fails `8_cost` and passes the
   other 10 criteria. Wall excluding decode, pre / post: 3.17 / 4.00,
   2.14 / 3.57, 2.75 / 3.72 s (pre first), then 6.12 / 4.52, 3.91 / 5.64,
   4.33 / 4.92 s (post first): means 3.74 s pre and 4.40 s post, with the
   ordering effect larger than the difference; the pre-move tree fails the
   same way at the same load. So the criterion is load-bound here, not a
   P8 regression; it was not re-run on an idle host.
   **S1's `-08` validators (`outputs/p8-history-20261030-02`)**: phase 1 as
   archived (criterion 4 fails as frozen, post-hoc 4b passes); phase 3c-a
   all pass, bit-identical to africanus (it imports `flagging_sky`, which
   stays); task G fetch checker all pass.
   **`compare_core_backends.py`** S1's suite → this suite (167 files, 16,576
   JSON leaves, 242 arrays, 68 FITS HDUs): every array and FITS HDU equal;
   925 listed items, of which 860 are timing leaves this comparator does not
   treat as volatile (`calls/*/cpu`, bench `runs`, `image_seconds`, ...), and
   65 are: `cores_busy` (24), absolute paths naming the worktree (21), the
   timing parts of the survey bench (10), `git_head` and `library` path (2),
   `native_library_sha256` and `source_digest` (4; P0 rebuilt the library
   with thin LTO and `x86-64-v3` after S1, and the sources changed), the
   section 6 cost verdict (2), and four digests that hash timings:
   `core_prospective`'s `frozen_train_responses_sha256` (3) hashes
   `flagging_prospective._freeze_view`, which includes
   `full_training_normals_seconds`, and `core_signal`'s
   `acceptance_digest_core` (1) includes each arm's `metrics.seconds`. To
   check that these differ run to run and not because of P8, prospective and
   signal were re-run on the pre-move tree `43dc3c7` (detached worktree,
   `outputs/p8-history-20261030-03-baseline`): its digests differ from both
   S1's and this run's, and every other leaf of both results equals this
   run's apart from `seconds` fields.
5. **Acceptance grep**: no live use of an old path. Every hit, by category:
   - frozen modules, unedited (container-only paths, not reached by any live
     chain): `python/rangtoy/flagging_next.py:24` (and `:21`, the
     `tv-flagging*.yaml` glob, which the pattern does not match),
     `flagging_sky.py:226,488`, `flagging_workflow.py:265,266` (and `:264`,
     `recipes/tv-flagging.yaml`);
   - docstrings naming where an input came from:
     `examples/build_luno_ms.py:3,5`, `examples/check_luno_sigma.py:5`,
     `examples/extract_luno_support.py:3`;
   - comments in the core recipes, kept because task H's Stimela logs record
     these recipes: `recipes/core-{imaging,injections,prospective,trend,signal,actions}.yaml`
     (one line each);
   - the synthetic tree of
     `tests/test_flagging_next.py::test_source_receipts_*` (lines 213–244),
     built in `tmp_path` to test the frozen `source_receipts()`;
   - the repointed `examples/oracle_wsclean_predict.py:24`
     (`history/tools/flagging/sky`).

### Other observations

- A bare `ruff check .` from the repository root fails before and after this
  task on `research/results/profiles-20261030/scripts/` (S1's measurement
  scripts: SIM115, I001, BLE001, ...); `check-all` lints only `python examples
  tests`. Not changed here (S1's archived scripts).
- The wheel task (W1, merged on main as `4982e4b` after this branch's base)
  edits `pyproject.toml` elsewhere; `git merge-tree` of main and this branch
  is clean, and W1's `tools/wheel/` names no moved file.
- No upstream observation.

## Timings (every tool run of this task)

Date for every row: 2026-10-30. Load is the 1-minute average.

| Tool run | Input | Wall | Peak RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `uv venv -p python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin numcodecs` (public PyPI) | worktree | 23.3 s | – | |
| `maturin develop --release --offline` (Rust 1.93) | worktree | 24.1 s | 385 MB | first build of the extension in this worktree |
| `manifest.sh before`, `move.sh` (`git mv`), `manifest.sh after` | 70 files | under 1 s each | – | hashes identical |
| `extract.py`, `docs.py`, `pointer.py`, `wrap.py`, `ruff --fix`/`format` on 3 tests | tests, docs, 33 notes | under 1 s each | – | |
| `pytest` on the five edited or dependent test files | 53 tests | 2.5 s | 107 MB | 53 passed |
| S1 suite `suite.sh` (`-01`), 29 steps | archived inputs of every chain | 613 s in all | 846 MB (F bench) | load 8–20; 28 exit 0, `section6-check` exit 1 (cost criterion) |
| validators (`-02`): phase 1, phase 3c-a, task G fetch checker, backends comparator against S1's `-01` | archived inputs | 1.0 s, 11.4 s, 2.0 s, 4.3 s | 1.90 GB (3c-a) | load 12–17; verdicts above |
| pre-move baseline (`-03`): worktree at `43dc3c7`, venv, extension and both crates built, then `core_cli prospective`, `signal` | archived inputs | build not timed (about 2 min); 20.5 s, 52.7 s | 836 MB | worktree removed afterwards |
| `bash tools/check-all.sh` (once, on `8cb2665`) | branch | 689.5 s (pytest 555 passed in 663 s) | 1.72 GB | overall PASS; load 6–23 |
| `section6`, `section6-check` re-run (`-05`) | archived inputs | 19.0 s, 16.5 s | 437 MB | load 14–20; `8_cost` fails again (7.88 s), all else passes |
| post-hoc section 6 A/B (`-07` pre-first, `-08` post-first): pre-move worktree at `43dc3c7` rebuilt (venv, extension, both crates) twice, 3 + 3 alternating pairs | archived inputs | about 2 min build + about 4 min runs, each time | – | load 26–46; all 12 runs fail `8_cost` only; worktree removed both times |

## For the coordinator

- **STATE.md, new entry.** "P8 history (big plan wave 2), 2026-10-30
  (`p8-history.md`): the 23 frozen `tv-flagging*` recipes, `tools/flagging/`
  (8 Dockerfiles, wrappers, fetch scripts, preflight, locks) and the six
  recipe-only modules `flagging_{concurrent,parallel,provenance,public,transfer,uncertainty}`
  with their tests moved to `history/` by `git mv`, byte-identical (70 files,
  6,258 lines; 3 wrapper and recipe test functions cut there too). Live tree
  267 → 197 files and 59,145 → 52,772 lines; recipes 30 → 7; pytest 739 →
  555 tests. check-all passes; S1's live-chain suite reproduces every
  archived verdict and the K replay hash for hash, except section 6's
  wall-time cost criterion under shared load (2.6 s and 7.9 s against a 2 s
  limit, load 14–20; a post-hoc A/B shows the pre-move tree failing it the
  same way at load 26–46). Re-running a frozen campaign is done from `43dc3c7` or
  its recorded commit with the pinned images (`history/README.md`)."
- **tool-timings.md rows.** The table above, prefixed "P8".
- **README.md** (changed here; three places): line 20 link
  `recipes/tv-flagging.yaml` → `history/recipes/tv-flagging.yaml`; line 155
  "`recipes/`: frozen Stimela2 recipes beside core-native `core-*.yaml` ones"
  → "`recipes/`: core-native Stimela2 recipes `core-*.yaml`"; three new lines
  after the `data/` bullet: "`history/`: the frozen campaigns' Stimela
  recipes, container builds, wrappers and recipe-only modules, retired from
  the live tree by task P8 (`history/README.md`, `research/p8-history.md`)."
  Still to add by the coordinator: an index line for `p8-history.md`.
- **CONTRIBUTING.md** line 39: "the Linux filesystem (not `/mnt/c`) with
  Docker inside WSL." → "the Linux filesystem (not `/mnt/c`), with Docker
  inside WSL only to re-run the frozen campaigns in `history/`
  (`history/README.md`)." (one line became two).
- **research/README.md**: line 152 wrapper link → `../history/tools/flagging/run-imaging.sh`;
  lines 181–204, the recipe column of the 23 flagging rows, `../recipes/tv-flagging*`
  → `../history/recipes/tv-flagging*`; line 254 "Pinned container
  environments live under `tools/flagging/`" → "under
  `history/tools/flagging/` ([history/README.md](../history/README.md))"
  (one line became two). W1's merge adds 4 lines elsewhere in this file;
  the merge is clean.
- **pyproject.toml**: appended `[tool.ruff]` with the comment "history/ holds
  frozen files that campaign receipts hash (research/p8-history.md): never
  lint or reformat them." and `extend-exclude = ["history"]`. Merges cleanly
  with W1's edits.
- **STATE.md, upstream-notes.md, big-plan.md** name moved paths historically;
  give each the pointer line used in the other notes if wanted.
- **Docker images that may now be pruned (user item).** None is needed by a
  live chain: `rang-flagging:local`, `rang-flagging-comparators:local`,
  `rang-flagging-sky:local`, `rang-flagging-response:local`,
  `rang-flagging-next:local`, `rang-flagging-imaging:local`,
  `rang-flagging-next-imaging:local`, `rang-flagging-parallel:local` (about
  11.6 GB as listed by `docker images`, shared layers counted once by
  `docker system df`) and three dangling `<none>` images (1.14 GB, 901 MB,
  901 MB). Keep `tools/ms-reader` (the task E oracle's Dockerfile). The
  frozen campaigns ran in exactly these local builds; a rebuild from
  `history/tools/flagging/` gives new image IDs.
- **P10**: none of P10's files moved (`test_pointing.py`, `test_blocked.py`,
  `test_beams.py`); the six `test_flagging_*` files P10 must not edit are now
  in `history/tests/`.
- **Evidence to keep**: `outputs/p8-history-20261030-01` (suite), `-02`
  (validators, backends receipt), `-03-baseline` (pre-move prospective and
  signal), `-04-check-all.log`, `-05` (section 6 re-run), `-07-section6-ab`
  and `-08-section6-ba` (post-hoc A/B).
- **Upstream**: none.
