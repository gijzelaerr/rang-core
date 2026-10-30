# Big plan task P9: one CLI, one receipt and archive format, one comparator engine

Protocol frozen 2026-10-30 in the commit that adds this file, before any
code of this task exists. Status: **implemented; measured: every comparator
verdict and count identical through the thin wrappers and through
`rang-core STAGE compare` on all 20 cases; `rang-core check` passes on
Linux and on native Windows; the CLI caps return about 0.8 CPU-s per
NumPy-importing process**.
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

### What changed (implemented)

- `python/rangtoy/core_compare.py`: the engine. The walker gained a
  per-class tolerance table, an accumulating `report` and the `not_dict`
  reason, so injections' own walker (classes exact, float 1e-9, distance
  1e-9 rel or 1e-12 abs, injection_float 1e-12; its `path[-2]` key rule
  kept) runs on it. The ten comparators owned by this task are in the
  module with their rules, print formats, receipt dump styles (`indent=1`
  plus newline; imaging `indent=2, sort_keys`; gridder and weights without
  the final newline) and exit semantics (weights and gridder always 0).
  Receipts are written with `newline="\n"` (identical bytes on Linux,
  LF on Windows). `run(name, argv)` returns the verdict contract.
  `unwrap()` accepts `rang.archive` oracles. **Labelled addition:** the
  backends comparator skips `*.rang-receipt.json` files (no suite before
  P9 holds one; the `p7-…-04` vs `-06` verdict is unchanged).
- `examples/compare_core_*.py`: 12–15-line wrappers, docstrings kept
  (1,573 lines removed from `examples/`; the engine is 1,659 lines).
- `python/rangtoy/core_cli.py`: the stage table below, the receipt, the
  archive verb, thread caps at entry, lazy driver imports (`import
  rangtoy.core_cli` no longer imports NumPy; `PATTERNS` and `trend_run`
  stay reachable through a module `__getattr__`), legacy forms, and
  `dispatch()` beside `main()`. **Pre-existing bug found and fixed:** the
  `rang-core` console script exited 1 after every successful stage or
  comparison, because `main()` returned the result dict and the console
  wrapper passes it to `sys.exit` (which prints it and returns 1); only
  `python -m rangtoy.core_cli` (which ignored the value) and the cabs
  worked. `main()` now returns 0; `dispatch()` returns the result.
- `python/rangtoy/check.py` and `tools/check-all.sh` (wrapper keeping its
  `exec flock`, `RANG_CHECKALL_LOCKED` handling and lock path).
  `--uv` is passed to `maturin develop` when the venv has no pip and `uv`
  is on PATH. On Windows the running `rang-core.exe` launcher is renamed
  aside before `ext-build` (a running `.exe` cannot be replaced, so
  `maturin develop` failed with "Access is denied" when the check ran
  through the launcher).
- `examples/bench_p1_solver.py sweep` and `bench_p2_gridder.py bench`:
  `--python NAME=VENV_PYTHON` replaces `--lib NAME=PATH`; each child runs
  under that interpreter, and the summary records the interpreter and the
  `rangtoy._core` file and SHA256 it loads (`extension_of`). Nothing moved
  to `history/`. Smoke runs (same venv twice): P2 `bench` on
  `c-unit-compact`, both builds deterministic and hash-equal
  (`outputs/p9-cli-20261030-01/bench-p2-smoke`); P1 `sweep`, `all_equal`
  true (`bench-p1-smoke`).
- `recipes/core-cabs.yaml`: the compare cab's info names the engine.
- **Deviations from section 2, item 3 (recorded, not hidden).** The
  default receipt name is `<primary>.<verb>.rang-receipt.json` (the verb
  keeps `run`, `environment` and `compare` receipts of one run directory
  apart). It sits beside the run directory for `run` verbs, but beside the
  comparator's receipt for `compare`, which is often inside a run directory
  (`.../actions/compare-archive.compare.rang-receipt.json`); suites stay
  comparable through the backends skip rule above. `rang-core check`
  writes a receipt only with `--receipt PATH` (verdict: each step's status
  and wall time), since a check has no output to sit beside. `commit.dirty`
  ignores untracked files (every worktree has the untracked `outputs`
  link).
- `pyproject.toml`: unchanged (`rang-core = "rangtoy.core_cli:main"` is
  still the entry; `check` needs no extra).

### The stage table (`rang-core -h`)

| Stage | Verbs | Kind |
| --- | --- | --- |
| injections, actions, prospective, signal | run, compare, archive | run: package function (cab); compare: engine |
| trend | mirror, run, compare, archive | package; engine |
| imaging | run, replay (`run_core_imaging.py`), compare, archive, legacy-archive (`archive_core_imaging.py`) | package; script; engine |
| campaign (K) | run, precondition, compare (K checker), archive, legacy-archive | package; scripts |
| campaign-array (L1), campaign-1830 (L2, plus fetch) | run, precondition, compare, archive, legacy-archive | scripts (`*_luno_array.py`, `*_luno_1830.py`) |
| flags (D) | run (`run_core_flags.py`), compare, archive | script; engine |
| weights (B) | compare (the comparator runs the core itself) | engine |
| gridder (C) | run (`run_core_gridder.py`), compare, archive | script; engine |
| ms (E) | compare (`check_ms_reader.py`) | script |
| section6 | run (`prototype_section6.py`), compare (`check_section6.py`), archive | scripts |
| backends | compare | engine |
| bench | f, p1 … p6 | scripts |
| environment, check; legacy `compare`, `trend-mirror` | — | package |

`compare` of an engine stage takes exactly the frozen script's arguments.
Script verbs pass their arguments through unchanged and need a checkout.

### Identity (criterion 1): pass, all 20 cases, both forms

`identity.py diff … before wrapper`, `… before cli-final` (the CLI at
`517e07b`), `… before cli-head` (`ed3e18c`), `… before cli-head2` (the
final CLI, through `python -m rangtoy.core_cli`) and `… before console`
(the final CLI through the `.venv/bin/rang-core` console script) report
**identical** for every case: exit status, stdout and the
comparator's receipt bytes, with the volatile fields of section 3 only
(weights `seconds`; MS checker read times; K precondition `seconds`,
`max_rss_mb`, `decode_seconds`, `step_seconds`, the last two not named in
the frozen list and found volatile by the before-vs-wrapper run, where the
precondition script itself is unchanged). The verdicts, from the CLI
receipts:

| Case | Exit | Verdict and counts (identical before and after) |
| --- | --- | --- |
| injections-archive | 0 | pass; exact 864, float 940, injection_float 24, distance 54; excluded 73 |
| injections-host | 0 | pass; exact 858, float 928, injection_float 24, distance 54; excluded 73 |
| actions-archive | 0 | pass; exact 61, float 102, difference 24; excluded 9 |
| actions-host | 0 | pass; exact 206, float 214, difference 24; excluded 20 |
| prospective-archive | 0 | pass; exact 1,875, float 1,239, difference 102; excluded 113 |
| signal-archive | 0 | pass; exact 261, float 208, difference 4, reported 12; excluded 15 |
| trend-frozen | 1 | fail as frozen, 28 failures; exact 875, float 168; excluded 1 |
| trend-posthoc | 0 | pass; exact 875, float 168; excluded 1 |
| imaging-archive | 0 | pass, pixels pass; exact 532, wcs 180, weight_sum 30, reported 65, psf_linf 15, unit_flux 4, response_fraction 16, template_flux 16, closure 2; excluded 423 |
| imaging-host | 0 | pass; same classes |
| flags-run (D) | 0 | criteria 1–5 pass |
| flags-archive-host (D) | 0 | pass, 68 fields |
| weights (B) | 0 | criteria 1–5 true, 19 jobs |
| weights-oracle-only (B) | 0 | archive, structure and repeat-pattern checks true |
| gridder (C) | 0 | measurement: 15 jobs, criterion 4 (WCS) true |
| ms (E), ms-self-check (E) | 0 | pass |
| campaign-precondition (K) | 0 | all eight checks pass, χ² 0.26823507037914956 |
| campaign-check (K) | 1 | `FileNotFoundError` on `outputs/core-k-20261030-01/fetch/result.json` before any criterion, in all three forms (the fetched bytes were pruned from `outputs`) |
| backends | 1 | 97 files, 5,213 JSON leaves, 58 arrays, 60 FITS HDUs; 47 non-numerical items (as before) |
| golden | — | `tests/test_core_backends.py` passes in both full runs below |

Criterion 2: the wrappers are the `wrapper` form above. The legacy cab
path (`rang-core compare STAGE R O REC`, which Stimela's
`rang-core-compare` cab calls as `core_cli.compare`) was run on the real
archives for trend (frozen and post-hoc), signal, actions, injections,
prospective and imaging-host: every receipt minus its `comparator` record
equals the `before` receipt, stdout is identical and the exit status
matches (`legacy-cab/`). The cab
`core_cli.compare` records `{"script": examples/compare_core_<stage>.py,
"engine": "rangtoy.core_compare", "sha256": <engine SHA256>, "exit",
"posthoc_slope_scale"}` (the K stage still hashes its script). No archive
in `research/results/` and no checker reads the comparator SHA256 (the
recipes' run directories carried it as provenance only; the trend
archive's `module_sha256` concerns `flagging_trend.py`, untouched).

Criterion 3: every CLI case wrote a `rang.receipt` v1 (for example
`cli-final/trend-frozen/rang-receipt.json`: inputs with SHA256, the
comparator receipt as output, thread variables with
`threads_pinned_by_cli`, platform, extension SHA256, timings, exit 1,
verdict 28 failures); `test_core_cli.py` checks the schema. A script verb
that raises still writes its receipt (`exit: "exception: …"`).

### `rang-core check` (criteria 4, 5)

- **Linux (WSL)**, `.venv/bin/rang-core check --all` at `902a74d` (plus
  the uncommitted receipt fix): **PASS** in 206 s, pytest 681 passed and 2
  skipped; the `## ` lines equal `p7-architecture-20261030-11/check-all.log`
  line for line (`rang-core-check-linux.{log,json}`).
- **Windows** (clone `C:\Users\gijsm\Build\tmp\20261030-rang-p9` with
  `core.autocrlf=false`, CPython 3.14.7, Rust 1.93.1 MSVC, uv venv):
  `.venv\Scripts\rang-core.exe check --all` at `ed3e18c`: **PASS** in
  106 s; root 23 and core 67 Rust tests, clippy, fmt, ext-build, ruff,
  ruff format, diff-check, pytest 640 passed and 44 skipped
  (`windows/check5.{log,json}`). Two earlier runs failed only `ext-build`,
  and both failures are recorded: at `902a74d` the running launcher
  `rang-core.exe` could not be replaced by `maturin develop` ("Access is
  denied"; fixed in `check.py`, the launcher is set aside); at `252c823`
  uv's default cache on this host failed ("too many temporary files",
  "Failed to query Python interpreter"), an environment issue, avoided with
  `UV_CACHE_DIR=C:\Users\gijsm\Build\cache\uv`. Every other step passed in
  all three runs.
- `bash tools/check-all.sh` (now the wrapper) at `ed3e18c` plus this
  report: **PASS** in 227 s, pytest 682 passed and 2 skipped; the `## `
  lines equal the P7 log line for line (`check-all.log`). After the
  review fixes (receipt for `check`, `dirty` without untracked files,
  wording) at `00c4be2`: **PASS** in 157 s, pytest 683 passed and 2
  skipped, `## ` lines identical (`check-all-2.log`). The Windows PASS predates those fixes, which do
  not touch `check.py`.
- Behaviour change of the wrapper: with no usable `.venv` (no
  `.venv/bin/python` or no editable `rangtoy`), `tools/check-all.sh` now
  exits nonzero before the first `## ` line and without `## overall:`;
  the old script ran the Rust steps first. Both exit nonzero.

### Thread caps (criterion 6, diagnostic)

Five alternating pairs at load 2.0–2.2 (`pinning*/pinning.tsv`):
the actions comparator no longer imports NumPy at all, so caps change
nothing there (0.05–0.07 s CPU either way); the flags comparator (NumPy,
four controls) took 0.33–0.39 s user CPU capped against 1.15–1.18 s with
`--no-pin-threads`, wall 0.45–0.50 s against 0.49–0.52 s, results and
stdout byte-identical. About 0.8 CPU-s per NumPy-importing process
returned, as S1 measured for the comparators.

## 5. For the coordinator

- **STATE paragraph.** "P9 merged: one CLI, `rang-core STAGE VERB`, for
  every stage, comparator and check (`rang-core -h`); the comparators live
  in `rangtoy.core_compare` and `examples/compare_core_*.py` are thin
  wrappers; every comparator verdict and count is identical through the
  wrappers and the CLI on a 20-case suite (research/p9-cli.md). Every CLI
  call writes a `rang.receipt` v1 beside its output, `STAGE archive` writes
  a `rang.archive` v1 that the comparators read, and the CLI caps the
  BLAS/XLA pools (opt out with `--no-pin-threads`). `rang-core check`
  (= `python -m rangtoy.check`, wrapped by `tools/check-all.sh`) runs the
  full checks on Linux and Windows. The `rang-core` console script no
  longer exits 1 after a successful command."
- **Timing rows** for `research/tool-timings.md`: the table at the end of
  this file.
- **README / CONTRIBUTING lines.** README, core section: "`rang-core -h`
  lists every stage and verb (`run`, `compare`, `archive`, …); `rang-core
  <stage> compare` takes the arguments of `examples/compare_core_<stage>.py`.
  Each call writes `<output>.<verb>.rang-receipt.json`." CONTRIBUTING, after
  the check-all sentence: "`rang-core check [--rust|--python|--all]` (or
  `python -m rangtoy.check`, which is what `tools/check-all.sh` runs) is the
  same check on any platform; on Windows run `.venv\Scripts\python -m
  rangtoy.check`."
- **Registrations for the siblings merged after this branch point** (L1-M
  and DF1 are on `main` at `06a59fc`; this branch merges cleanly,
  `git merge-tree` exit 0). Add to `STAGES` in `core_cli.py`:

  ```python
  "campaign-fieldmodel": {
      "help": "PKS 1934-638 field-model arms, task L1-M (research/l1-model-completeness.md)",
      "fetch": _script("fetch_l1m.py", _first),
      "run": _script("run_l1m.py", _first),
      "compare": _script("check_l1m.py", _first, "the L1-M checker"),
      "archive": ARCHIVE,
      "legacy-archive": _script("archive_l1m.py"),
  },
  "wgridder": {
      "help": "exact w-gridder ported from ducc0, task DF1 (research/df1-wgridder.md)",
      # Modes item0 | gates | threads put the output first or second: pass
      # --receipt PATH, or give the entry a mode-aware primary (with _last,
      # `gates` would name DUCC_SLICE, an input).
      "compare": _script("compare_core_wgridder.py", note="item0 | gates | threads"),
      "archive": ARCHIVE,
  },
  ```

  and `"df1": _script("bench_df1.py")` under `bench`. DF1's
  `compare_core_wgridder.py` (933 lines, modes item0/gates/threads, imports
  `resource`) is the one comparator not on the engine; `test_core_cli.py`
  lists it as pending. Porting it into `core_compare` (and replacing
  `resource` with `rangtoy.rusage`) is a follow-up of the same shape as
  this task.
- **What P12 must rename** (`rangtoy` → `rang`): `[project.scripts]`
  `rang-core = "rangtoy.core_cli:main"`; `tools/check-all.sh` (`-m
  rangtoy.check`); the wrappers' `from rangtoy.core_compare import main`;
  the cab commands `rangtoy.core_cli.*` in `recipes/core-*.yaml`;
  `importlib.metadata.version("rangtoy")` and
  `find_spec("rangtoy._core")` in `core_cli` (receipt) and in the two
  benches (`extension_of`); the `rangtoy_modules_imported` and
  `name.startswith("rangtoy")` logic of `environment`; the receipt key
  `environment.rangtoy` (schema change, bump `RECEIPT_VERSION`); docs
  (`python -m rangtoy.core_cli`, `python -m rangtoy.check`).
- **`history/` moves:** none (the benches were rewritten instead).
- **Branch note:** commit `c9a8c2e` has one failing test (the launcher
  copy-back test's old expectation), fixed in the next commit `ed3e18c`;
  every other commit's targeted tests pass. Squash on merge if wanted.
- **Evidence to keep:** `outputs/p9-cli-20261030-01/` (identity suite:
  `identity.py`, `before/`, `wrapper/`, `cli/`, `cli-final/`, `cli-head/`,
  `cli-head2/`, `console/`; `legacy-cab/`; Linux check
  log and JSON; `pinning*/`; bench smokes; `windows/`, the Windows logs).
- **Follow-ups (not done):** `tools/core-j-suite.sh` as a Python driver
  list on the CLI (`rang-core` verbs already cover every step); the K run
  `outputs/core-k-20261030-01` has no `fetch/` any more, so the K checker
  cannot be re-run from retained outputs (only the precondition can); the
  stage `run` verbs of B and E do not exist as separate drivers (their
  comparators run the core).
- **Upstream observations.** RATT / caracal-pipeline: none from this task
  (no CARACal code path changed). Non-RATT: maturin's `develop` (through
  `uv pip install --force-reinstall`) cannot replace a console-script
  launcher that is running on Windows; uv's default cache on this Windows
  host fails with "too many temporary files exist" (worked around with
  `UV_CACHE_DIR=C:\Users\gijsm\Build\cache\uv`, an environment issue);
  Git for Windows refuses to clone `\\wsl.localhost\…` without
  `safe.directory` ("dubious ownership").
- **Host note.** `C:\Users\gijsm\Github\rang` (the Windows checkout) holds
  untracked files named `Bool    ,`, `Char    ,`, `DComplex,` … created at
  15:54 by another session (casacore data-type names); not from this task.

## Timings (every tool run of this task)

| Date | Step | Wall | Notes |
| --- | --- | --- | --- |
| 2026-10-30 | WSL: `uv venv` + editable install + `maturin develop --release --offline` | 60 s | |
| 2026-10-30 | identity suite `before` at `f36ff80` (20 cases) | 6.8 s | outputs above |
| 2026-10-30 | identity suite `wrapper` (thin wrappers) | 5.7 s | identical to `before` |
| 2026-10-30 | identity suite `cli`, `cli-final` (`517e07b`), `cli-head` (`ed3e18c`) through `rang-core STAGE VERB` | 5.5 s, 7.9 s, 6.5 s | identical to `before` |
| 2026-10-30 | WSL: `rang-core check --all` at `902a74d` | 206 s (pytest 126 s) | PASS, 681 passed, 2 skipped |
| 2026-10-30 | thread caps, flags comparator, 5 pairs | 0.45–0.52 s each | 0.33–0.39 vs 1.15–1.18 user CPU-s |
| 2026-10-30 | bench smokes: P2 `bench` (one label, two runs), P1 `sweep` (one round) | 1.2 s, 1.8 s | hash-equal |
| 2026-10-30 | Windows: clone over `\\wsl.localhost` | 8.1 s | first attempt refused (`safe.directory`) |
| 2026-10-30 | Windows: `uv venv` + editable install (builds the extension) | 60.6 s | |
| 2026-10-30 | Windows: `rang-core.exe check --all` at `902a74d` | 212 s | FAIL on ext-build only (launcher in use) |
| 2026-10-30 | Windows: `rang-core.exe check --all` at `252c823`; `python -m rangtoy.check --python` | 113 s; 105 s | FAIL on ext-build only (uv cache) |
| 2026-10-30 | Windows: `python -m rangtoy.check --only ext-build`; `rang-core.exe check --all` at `ed3e18c` | 1.9 s; 106 s | PASS, 640 passed, 44 skipped |
| 2026-10-30 | WSL: `bash tools/check-all.sh` at `ed3e18c` + report | 227 s (pytest 140 s) | PASS, 682 passed, 2 skipped |
| 2026-10-30 | identity `cli-head2` (`-m`) and `console` (`.venv/bin/rang-core`), final CLI | about 7 s each | identical to `before` |
| 2026-10-30 | legacy cab path `rang-core compare` on 7 real-archive cases | about 1 s | receipts minus `comparator` equal `before` |
| 2026-10-30 | WSL: `bash tools/check-all.sh`, after the review fixes | 157 s (pytest 150 s) | PASS at `00c4be2`, 683 passed, 2 skipped |
