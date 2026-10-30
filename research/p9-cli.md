# Big plan task P9: one CLI, one receipt and archive format, one comparator engine

Protocol frozen 2026-10-30 in the commit that adds this file, before any
code of this task exists. Status: **proposed** (protocol only).
Task P9 of [simplification-review.md](simplification-review.md) (section 3
"P9 One CLI, one archive format, one comparator engine; OpenBLAS pinned",
section 4 row P9), plus the `rang-core check` design and the remaining
POSIX assumptions of [x1-crossplatform.md](x1-crossplatform.md) section 5,
and the A/B benches that task P7 ([p7-architecture.md](p7-architecture.md))
left behind when it refused `RANG_CORE_LIB`. Under AGENTS.md this is
engineering, not a scientific contribution: the gate is that every
comparator gives the same verdict and the same counts as before, through
the frozen script and through the new CLI.

## 1. Inventory at `f36ff80`

### 1.1 Entry points

| Entry point | What it runs | Writes |
| --- | --- | --- |
| `rang-core` = `python -m rangtoy.core_cli` (`[project.scripts]`) | flat subcommands `injections`, `actions`, `prospective`, `signal`, `trend-mirror`, `trend`, `imaging`, `campaign`, `environment`, `compare <stage>` | `result.json` (driver), `side-effects.json` (`_audited`), `environment.json`; `compare` runs the stage's comparator script with `runpy` and adds `comparator: {script, sha256, exit, posthoc_slope_scale}` to its receipt |
| `recipes/core-{injections,actions,prospective,signal,trend}.yaml` + `core-cabs.yaml` | python-flavour cabs calling `rangtoy.core_cli.<function>` | as above |
| `recipes/core-imaging.yaml` | cabs calling `rangtoy.core_imaging` | task I's files |
| `examples/run_core_campaign.py <track>` | injections, prospective, actions, signal drivers with its own audit (`track` key) | `result.json`, `side-effects.json` |
| `examples/run_core_injections.py` | the injections driver with its own audit | same |
| `examples/run_core_flags.py` | task D's Tricolour port on four controls | `<control>/{flags,intensity,stages}.npz`, `receipt.json` |
| `examples/run_core_gridder.py` | task C's fifteen jobs | `images/*.fits`, `result.json` |
| `examples/run_core_imaging.py` | task I's replay and both comparisons | `result.json`, `side-effects.json`, `images/`, `compare-{archive,host}.json` |
| `examples/{run,precondition,check,archive}_luno_campaign.py` | task K (`core_campaign`) | run dir with `receipt.json`, `side-effects.json`, `environment.json`; check dir `result.json` |
| `examples/{run,precondition,check,archive}_luno_array.py`, `..._luno_1830.py`, `fetch_luno_1830.py` | tasks L1, L2 (`core_campaign_array`, `core_campaign_1830`) | same pattern |
| `examples/prototype_section6.py`, `check_section6.py` | section 6 chain and checker | run dir, check dir |
| `examples/bench_p1_solver.py` (`run`, `sweep --lib`), `bench_p2_gridder.py` (`c-inputs`, `k-replay`, `time`, `bench --lib`, `diff`) | P1 and P2 benches; `sweep` and `bench` A/B two libraries with `RANG_CORE_LIB`, which P7 refuses | bench JSON |
| `tools/check-all.sh` | 15 `## step` lines (root, core: build, test, clippy, fmt; ext-build, ext-clippy, ext-fmt; ruff, ruff-format, diff-check, pytest) under `flock ~/.rang-checkall-v2.lock` | stdout |
| `tools/core-j-suite.sh` | the archived chains under `/usr/bin/time` | suite dir |

### 1.2 Comparators: archive read, verdict and counts printed

| Comparator | Arguments | Oracle layout read | Engine | Printed verdict/counts | Exit |
| --- | --- | --- | --- | --- | --- |
| `compare_core_injections.py` | RESULT ARCHIVE RECEIPT | top level (`clean_reference`, `cases`, `post_selection_candidate_recovery` or sibling `candidate-recovery.json`, `configuration`) | own walker (classes exact, float 1e-9, distance 1e-9 rel or 1e-12 abs, injection_float 1e-12) | one JSON line: `passed`, `failures`, `classes{compared,max_rel}`, `excluded`, `selected_equal` | `SystemExit(1)` on fail |
| `compare_core_actions.py` | RESULT ORACLE RECEIPT | top level, `configuration` or sibling `action-config.json` | `core_compare.compare` | JSON line: `passed`, `failures`, `classes`, `excluded`, `selected` | same |
| `compare_core_prospective.py` | RESULT ORACLE RECEIPT | `raw_result_projection` or top level | `core_compare` | JSON line: `passed`, `failures`, `classes`, `excluded` | same |
| `compare_core_signal.py` | RESULT ORACLE RECEIPT | `raw_result` or top level | `core_compare` | same | same |
| `compare_core_trend.py` | RESULT ARCHIVE RECEIPT [`--posthoc-slope-scale`] | `raw_result` (required) | `core_compare` + post-hoc slope rule | same | same |
| `compare_core_imaging.py` | RESULT ORACLE RECEIPT [`--images` C R] | `raw_result` or top level | `core_imaging.compare_replay`, `pixel_comparison` | text table per class, `excluded N failures N`, pixel lines, `passed X` | returns 1 on fail |
| `compare_core_flags.py` | `archive-host` ARCHIVE HOST OUT, `run` CORE HOST ORACLE OUT | `result` (`gain-tv-caracal.json`), run dirs' `receipt.json` and npz | own | indented JSON of the result: `fields_compared`, `failures`, criteria 1–5 | `sys.exit(0/1)` |
| `compare_core_weights.py` | OUT [`--oracle-only`] [`--tolerance T`] | `OUT/oracle/*.json`, `*.npz` | own (runs the core) | criteria JSON (`1_reproduction` … `5_header_sums`) or precondition summary; per job `PASS/FAIL` to stderr | always 0 |
| `compare_core_gridder.py` | REFERENCE CANDIDATE OUTPUT | FITS dirs | own | per-job table, `summary`, `wcs` | always 0 (measurement) |
| `compare_core_backends.py` | REFERENCE CANDIDATE RECEIPT [IGNORE] | two suite dirs | own (volatile-key rules) | summary JSON: `files`, `json_leaves`, `arrays`, `fits_hdus`, `bytes_equal_files`, `pass`; volatile counts; `FAIL` lines | 1 on any difference |
| `check_ms_reader.py` (task E; not owned) | ORACLE OUT, or `--self-check` O1 O2 OUT | oracle dump | own | per-criterion `PASS/FAIL`, `overall` | `sys.exit` |
| `precondition_luno_campaign.py`, `check_luno_campaign.py` (task K; not owned) | OUT; RUN PRE OUT | archives via `core_campaign` | own | JSON line; criteria `PASS/FAIL`, `all pass` | 1 on fail |
| `tests/test_core_backends.py` (golden) | — | `tests/data/core-backends-golden.npz` | pytest | pytest | pytest |

### 1.3 Archive layouts in `research/results/` (86 files)

Four layouts are read by the comparators: (a) the result itself at top
level (`gain-tv-injections.json`, `gain-tv-actions.json`); (b)
`schema_version` + `raw_result` (`gain-tv-next-{signal,trend,imaging}.json`);
(c) `raw_result_projection` (`gain-tv-next-prospective.json`); (d) `result`
under `config`/`source_run` (`gain-tv-caracal.json`). The core task
archives (`core-*.json`, `luno-*-campaign.json`) are per-task summaries
with `schema_version`, `task`, `protocol`, `protocol_commit`, `status` and
task-specific keys; none is read back by a comparator except through the K,
L1 and L2 checkers.

### 1.4 Receipt fields written today

- `side-effects.json`: `core_cli._audited` writes `stage`, `inputs`,
  `input_files_checked`, `inputs_unchanged`, `git_status_unchanged`,
  `run_dir_files`, `only_result_written`, `seconds`; `run_core_campaign.py`
  writes `track` instead of `stage` and no `seconds`; K writes `inputs`,
  `changed`, `run_dir_files`.
- `environment.json`: interpreter, `rang_core_*`, distributions, QuartiCal
  presence, imported `rangtoy` modules.
- Run receipts: K `receipt.json` (fetch receipts, object and code SHA256,
  library and SHA256, backend, settings, seed, Python, NumPy); D
  `receipt.json` (library SHA256, masks, strategies, counts, versions,
  timings, host hashes).
- Comparator receipts as in 1.2; `core_cli compare` adds `comparator`.
- No receipt records the thread settings, the platform, the commit, or
  output hashes uniformly.

## 2. Target (to implement)

1. **One comparator engine.** `python/rangtoy/core_compare.py` holds the
   field walker (generalised to a per-class tolerance table, so injections'
   four classes run on it) and every comparator above that this task owns,
   rules moved verbatim (classify functions, tolerance constants, volatile
   lists, print formats, receipt dump styles, exit semantics). Contract:
   `core_compare.run(name, argv)` returns `{"name", "exit", "passed",
   "failures", "counts", "receipt"}` (`passed` is `None` for the
   measurement-only gridder and weights `--oracle-only`), and
   `core_compare.main(name, argv)` prints exactly what the frozen script
   printed and returns its exit code. Each `examples/compare_core_*.py`
   becomes a thin wrapper (docstring kept, `sys.exit(main(name,
   sys.argv[1:]))`) that writes no new files. Oracle loading also accepts
   the new archive format (item 3).
2. **One CLI.** `rang-core [--receipt PATH] [--no-pin-threads] <stage>
   <verb> ...` with a stage table: `run`, `compare`, `archive` for every
   stage, plus `mirror` (trend), `precondition`/`check` (campaigns),
   `fetch` (1830). Stages: injections, actions, prospective, signal, trend,
   imaging, campaign (K), campaign-array (L1), campaign-1830 (L2), flags
   (D), weights (B), gridder (C), ms (E), section6, backends, plus
   `environment` and `check`. Verbs whose code lives in a driver script
   that this task does not own delegate to that script unchanged with
   `runpy` (checkout required, as today); `compare` of the owned
   comparators runs in the package. The legacy forms `rang-core <stage>
   RUN ...` and `rang-core compare <stage> ...` and every cab function
   signature stay. The CLI prints the comparator's stdout unchanged; its
   own messages go to stderr.
3. **One receipt and archive format.** Every CLI invocation writes
   `rang.receipt` version 1 (default `<primary output>.rang-receipt.json`,
   beside the run directory or comparator receipt, never inside a stage
   run directory, so `only_result_written` and suite comparisons are
   unaffected): `schema`, `version`, `command`, `stage`, `verb`, `commit`
   (HEAD, dirty), `environment` (Python, executable, platform, machine,
   CPU count, extension path and SHA256, every thread variable and whether
   the CLI pinned it), `inputs` and `outputs` (path as POSIX string; files
   by content SHA256; input directories by a SHA256 of their (path, size,
   mtime) listing, output directories by a content tree SHA256), `timings`
   (wall, process CPU, peak RSS through `rangtoy.rusage`), `exit`, and for
   `compare` the verdict of item 1. `rang-core <stage> archive RUN OUT`
   writes `rang.archive` version 1 (`schema`, `version`, `stage`,
   `status`, `result`, the run's `side-effects`/`environment`/receipts,
   `receipt`); the comparators read it as an oracle. Existing archives are
   not rewritten.
4. **Thread pinning at CLI entry.** Before NumPy, SciPy or JAX is
   imported, the CLI applies `tests/conftest.py`'s caps
   (`OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS` default 1;
   `XLA_FLAGS` set only if absent); an explicit environment setting wins;
   `--no-pin-threads` (or `RANG_PIN_THREADS=0`) disables it.
   `RAYON_NUM_THREADS` is left alone and recorded. `core_cli` imports its
   drivers lazily so that pinning precedes NumPy.
5. **`rang-core check [--rust|--python|--all]`** = `python -m
   rangtoy.check`: the 15 steps of `tools/check-all.sh` as argument lists
   (cargo with `+1.93`; Python tools as `sys.executable -m ...`), the same
   `## step`, `FAILED: <words>`, `test result` and pytest `tail -2`
   output, no fail-fast, `## overall: PASS|FAIL` and exit status; the host
   lock `~/.rang-checkall-v2.lock` (`RANG_CHECKALL_LOCK`) taken with
   `fcntl.flock` on POSIX (interoperates with `flock(1)`) and
   `msvcrt.locking` on Windows unless `RANG_CHECKALL_LOCKED` is set;
   refuses to run outside a checkout; never imports `rangtoy.core`.
   `tools/check-all.sh` keeps its `exec flock` lock and becomes a wrapper
   of `python -m rangtoy.check`.
6. **POSIX leftovers in the CLI and receipt paths:** no `/usr/bin/time`
   (timings in-process), no `/tmp`, every path in a receipt via
   `as_posix()`.
7. **A/B benches:** `bench_p1_solver.py sweep` and `bench_p2_gridder.py
   bench` select the build by interpreter (`--python NAME=VENV_PYTHON`,
   one venv per extension build) instead of `--lib NAME=PATH`
   (`RANG_CORE_LIB`); their other modes are unchanged.

## 3. Acceptance (frozen)

**Identity suite** (`outputs/p9-cli-20261030-01/identity.py`, run from the
worktree root with `OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`). The
`before` pass ran at `f36ff80` before any edit
(`outputs/p9-cli-20261030-01/before/`); the same cases run again after the
change through the thin wrappers (`wrapper`) and through `rang-core
<stage> <verb>` (`cli`). For every case, the exit status, the stdout and
the comparator's own receipt file must be byte-identical to `before`
(after replacing the case directory path), except the fields named here as
volatile: weights' `seconds` (wall times inside `compare.json`) and its
stderr timing line; the K precondition's `seconds`, `max_rss_mb` (stdout
and `result.json`); the MS checker's read wall times.

| Case | Inputs | Before (exit) |
| --- | --- | --- |
| injections-archive | `p1-solver-20261030-21/injections/result.json` vs `gain-tv-injections.json` | pass, exact 864, float 940, injection_float 24, distance 54, excluded 73 (0) |
| injections-host | same vs `tv-injections-wsl-20261029-01/result.json` | pass (0) |
| actions-archive | `p7-architecture-20261030-06/actions` vs `gain-tv-actions.json` | pass (0) |
| actions-host | same vs `tv-flagging-actions-wsl-20261029-01/result.json` | pass (0) |
| prospective-archive | `p1-solver-20261030-21/prospective` vs `gain-tv-next-prospective.json` | pass (0) |
| signal-archive | `p7-architecture-20261030-06/signal` vs `gain-tv-next-signal.json` | pass (0) |
| trend-frozen | `p7-architecture-20261030-08/trend` vs `gain-tv-next-trend.json` | **fail as frozen**, 28 failures (1) |
| trend-posthoc | same, `--posthoc-slope-scale` | pass (0) |
| imaging-archive | `p7-…-06/i` vs `gain-tv-next-imaging.json`, `--images` | pass (0) |
| imaging-host | same vs `tv-next-imaging-wsl-20261029-01/result.json` | pass (0) |
| flags-run (D) | `run p7-…-06/d`, host `tv-caracal-wsl-20261029-01`, oracle `core-d-oracle-20261029-01/run` | pass (0) |
| flags-archive-host (D) | `archive-host gain-tv-caracal.json` | pass (0) |
| weights (B) | fresh dir + `core-b-20261030-01/oracle`, `--tolerance 4.76837158203125e-07` | criteria printed (0) |
| weights-oracle-only (B) | `--oracle-only` | precondition summary (0) |
| gridder (C) | archive images vs `p7-…-06/c/images` | measurement (0) |
| ms (E) | `core-e-oracle-20261029-01` | pass (0) |
| ms-self-check (E) | `--self-check` oracle `-01` vs `-02` | pass (0) |
| campaign-precondition (K) | fresh dir | all checks pass (0) |
| campaign-check (K) | `core-k-20261030-01` with `-00-precondition` | **fails before comparing (1)**: the run's `fetch/` was pruned from `outputs`; identity of the failure only, not a K verdict |
| backends | `p7-…-04` vs `p7-…-06` | fail (1), the known non-numerical items |
| golden | `pytest tests/test_core_backends.py` | pass |

Further gated criteria:

1. Every case above identical in all three forms (`identity.py diff`).
2. The frozen scripts still run by path with their documented arguments
   (they are the `wrapper` form). `core_cli.compare` (the cab) still
   writes `comparator` into the receipt; its `script` and `sha256` now name
   the engine module, which ran; no archived run or checker reads that
   hash (recorded in section 5).
3. Every CLI invocation of the suite writes a `rang.receipt` v1 that
   validates against the schema test, with thread settings and platform.
4. `rang-core check --all` prints the same 15 `## step` lines, in order, as
   `outputs/p7-architecture-20261030-11/check-all.log`, and passes on
   Linux (WSL) and on native Windows (clone of the branch at
   `C:\Users\gijsm\Build\tmp\20261030-rang-p9`, LF line endings, cargo
   1.93, Python 3.14, uv; deleted afterwards). If an environment issue
   outside this task's files (for example no cached cargo registry
   offline) blocks a Windows step, that is recorded, not hidden.
5. `bash tools/check-all.sh` passes once before the final commit, with the
   same `## step` lines and PASS/FAIL semantics.
6. Thread pinning measured: CPU seconds of one comparator through the CLI
   with and without `--no-pin-threads` (diagnostic, not gated).

Not gated: run-stage identity (the stage drivers are not edited; `run`
verbs call the same functions or scripts).

## 4. Results

(to be filled after implementation)

## 5. For the coordinator

(to be filled)

## Timings (every tool run of this task)

| Date | Step | Wall | Notes |
| --- | --- | --- | --- |
| 2026-10-30 | WSL: `uv venv` + editable install + `maturin develop --release --offline` | 60 s | |
| 2026-10-30 | identity suite `before` at `f36ff80` (20 cases) | 6.8 s | outputs above |
