# W4-1: receipts record every result-affecting setting

**Status (2026-10-31): implemented and measured on branch `w4-1-receipts`
(from `main` ecccbf0, with `main` fdf186b merged in for W4-3); all acceptance items pass; check-all `overall: PASS`
(see "Checks").** Fix task W4-1 of the wave 4 plan, for findings W4R-01
(high) and W4R-02 (medium) of the final review (`research/w4-review.md`).
Nothing in a result changed: with every variable unset the P9 identity
suite and every campaign comparator are identical before and after, and the
receipts differ only in the new fields, the version and the hashes of the
edited code.

## What was wrong

- **W4R-01.** The Rust core read `RANG_SOLVE_OPTIONS` (and
  `RANG_SOLVE_TRACE`) inside every solve, and no receipt recorded it or
  the other result-affecting variables (`RANG_GRIDDER_DEVICE`,
  `RANG_GRIDDER_GPU_PRECISION`, and until W4-3 `RANG_DF1_LIB` and
  `RANG_C1_LIB`). A shell
  with an L5 opt-in set produced different gains under a receipt that
  looked like the archived default (reproduction r02).
- **W4R-02.** `ROOT = parents[2]` is the checkout only for an editable
  install. From a wheel the receipt named the HEAD of whatever git
  repository held the venv, and `core_receipts.source_receipts()` raised
  `FileNotFoundError` on `Cargo.lock` (r05).

## What changed, file by file

- `core/src/solve.rs`: the core reads no environment. `Options::from_env`,
  `OPTIONS_VAR` and `TRACE_VAR` are gone. `solve(problem, settings)` now
  means the archived options. The new `solve_recorded(problem, settings,
  options, trace: Option<&Path>)` is the FFI entry and writes the trace
  only when it is given a path. `Options::from_parts` and `Options::parts`
  convert to and from the C struct with `parse`'s checks. `MAX_ANDERSON` is
  now public. The options syntax doc moved to `OPTIONS_SYNTAX`. One new
  test covers the parts round trip, the rejected parts, and
  `solve_recorded` against `solve_with` and against `solve`, compared bit
  for bit.
- `core/src/ffi.rs` (coordinator file): `SolveInputs` gains three trailing
  fields. `options` is a `#[repr(C)] SolveOptions` (transposed, stop code,
  tolerance, anderson, freeze); all zero is the archived solver. `trace`
  and `trace_len` carry a UTF-8 path, and null or empty means no trace. A
  new `rang_core_solve_options_parse(text, len, out)` is the only parser
  of the options syntax (`solve::Options::parse`). An invalid options
  struct, a non-UTF-8 trace path or an unwritable trace gives status 1, as
  a malformed variable did before.
- `core/py/src/lib.rs` (coordinator file; only the solve bindings):
  - `solve_options_parse(text)` is a new binding.
  - `solve_complex` takes two more trailing positional arguments, `options`
    (the five parts) and `trace` (str or None).
  - Registration is one line beside `solve_complex`'s.
- `python/rang/core.py` (coordinator file):
  - The registry `ENVIRONMENT` holds 37 `Variable(name, default, kind,
    effect, report, reader)` entries, alongside `KINDS`,
    `RECORDED_KINDS`, `NOT_ENVIRONMENT` (`RANG_E3`, a Measurement Set
    keyword in a Rust test), `environment_variables()`,
    `environment_settings()` (the receipt record: 29 variables, null when
    unset) and `environment_markdown()` (the documentation).
  - `MANIFESTS` and `checkout_root()`: `parents[2]` counts as the checkout
    only if it holds `pyproject.toml`, `Cargo.toml` and `core/Cargo.toml`.
  - `SolveOptions` (frozen dataclass, `parts()`, `record()`) and
    `solve_options(options)`. Parsing goes through the core's parser and
    raises ValueError when the text is malformed.
  - `solve_complex(..., options=None, trace=None)`. When an argument is
    None, the wrapper reads `RANG_SOLVE_OPTIONS` or `RANG_SOLVE_TRACE`,
    once per call. Malformed options raise RuntimeError with "status 1",
    as before. `ComplexSolution` gains `options` and `trace`, both
    defaulting to None.
- `python/rang/core_cli.py` (coordinator file):
  - `rang.receipt` is now version 3; the bump is documented beside
    `RECEIPT_VERSION` and in the module docstring.
  - `environment.rang_environment` holds the registry snapshot taken when
    the command starts (`Receipt.__init__`). `_environment_record(pinned)`
    reads the registry live when no snapshot is passed, which is what r02
    calls.
  - The new top-level `source` records `checkout`, `distribution`,
    `version` and `extension_sha256`.
  - `commit` is null outside a checkout, and `_git` runs only inside one.
  - `rang-core environment` writes `rang_environment` into
    `environment.json`. `rang.core` is imported late, after the thread
    caps, as before.
- `python/rang/core_receipts.py`: this is now a live module. It was P11's
  verbatim extract of `flagging_next`. In a checkout it hashes what the
  extract hashed on disk: `python/rang/*.py`, `src/*.rs`, the root
  manifests and the loaded extension. The recipe and `tools/flagging`
  globs had matched nothing since P8 and are removed. Outside a checkout
  it hashes every file of the installed package (89 in r05) and the
  extension.
- Campaign and other receipt writers. Each adds `rang_environment` to a
  record that no comparator compares across runs:
  - K (`core_campaign.py`, `receipt.json`);
  - L1 (`core_campaign_array.py`, `receipt.json`);
  - L2 (`core_campaign_1830.py`, `receipt.json`);
  - L1-M (`core_campaign_fieldmodel.py`, `l1m.json`);
  - C1 (`core_campaign_closure.py`, `c1.json`);
  - imaging (`core_imaging.py`, `provenance` in `result.json`; the replay
    comparator walks the archived leaves only);
  - L5 (`examples/run_l5_solver_study.py`, `environment` and
    `environment_end`).
- `git_status()` in `core_campaign.py` and `_git_status()` in
  `core_imaging.py` return None outside a checkout.
- `python/rang/core_solver_study.py`: the `solver_options` context
  manager, which set `os.environ` around a solve, is gone. `solve()` passes
  `options=` and `trace=` explicitly; an unset trace is passed as "" (no
  trace, as before). This also removes the putenv race noted under W4R-01.
  `OPTIONS_VAR` and `TRACE_VAR` alias the names in `core`.
- `python/rang/core_compare.py`: `rang_environment` is added to
  `BACKENDS_VOLATILE`, so that a new suite compared with an archived one
  does not fail on the new key.
- `docs/gen_cli.py` and `docs/cli.md`: the intro says version 3, and a new
  "Environment variables" section is generated from the registry (kinds
  and the table). `tests/test_d1_docs.py` keeps it in step.
- Tests:
  - new `tests/test_w4_1_receipts.py`:
    - `options=` against the environment path, bit for bit, for four
      option sets, both as a string and as a parsed `SolveOptions`;
    - default against explicit archived options, and an explicit argument
      winning over a set variable;
    - malformed options;
    - the trace given as an argument, through the environment, and turned
      off by `""`;
    - **the grep test**: every `RANG_*` name in `python/rang`, `core/src`,
      `core/py/src` and `src` is registered or listed in
      `NOT_ENVIRONMENT`; no registered name is stale; each entry's report
      exists and its reader file names it;
    - the Rust core reads no solver variable;
    - the recorded kinds;
    - every receipt writer calls `environment_settings`;
    - `checkout_root()`.
  - `tests/test_core_cli.py`: version 3, `rang_environment` in registry
    order, `source`. New tests: a variable set when the command starts is
    recorded (r02), and outside a checkout `commit` is null and git is not
    run (r05).
  - `tests/test_core_receipts.py`: covers the checkout tree (three
    manifests; the dead globs are ignored) and the installed-package tree.
  - `tests/test_p11_extract.py` (deviation): 19 extracts instead of 20, and
    `core_receipts` → `flagging_next` in the import map, because
    `core_trend_run`'s verbatim body still imports `source_receipts` from
    it.

## The registry

`rang.core.ENVIRONMENT`, as generated (also the table in `docs/cli.md`).
Receipts record the kinds result, input, speed, output, process and refused
(29 variables). Viewer (5, CARTA connection details, one a session id),
test (1) and retired (2) are not recorded.

`RANG_C1_LIB` and `RANG_DF1_LIB` were read until W4-3 (merged as
fdf186b) moved both kernels into the extension. They stay in the
registry as retired entries, so that a receipt written before W4-3 can
still be explained. The grep test exempts them from its "still read"
check and asserts that no module reads them.

| Variable | Default | Kind | What it changes | Report | Read by |
| --- | --- | --- | --- | --- | --- |
| `RANG_SOLVE_OPTIONS` | unset (the archived solver) | result | solver options `qp_weights`, `stop`, `anderson`, `freeze`; read by `core.solve_complex` when `options=` is None | `research/l5-solver-science.md` | `python/rang/core.py` |
| `RANG_SOLVE_TRACE` | unset (no trace) | output | file for the per-iteration solver trace; read by `core.solve_complex` when `trace=` is None | `research/l5-solver-science.md` | `python/rang/core.py` |
| `RANG_GRIDDER_DEVICE` | cpu | result | `gpu` runs the inversion on wgpu (cargo feature `gpu`) | `research/x2-wgpu.md` | `python/rang/core_grid.py` |
| `RANG_GRIDDER_GPU_PRECISION` | f64 | result | `f32` selects the GPU path toleranced to 1e-4 | `research/x2-wgpu.md` | `python/rang/core_grid.py` |
| `RANG_GPU_ADAPTER` | unset (the best adapter) | result | substring of the name of the GPU adapter to use | `research/x2-wgpu.md` | `core/src/gpu/context.rs` |
| `RANG_GPU_MEMORY_MB` | 256 | speed | device-memory budget per GPU inversion (batching only) | `research/x2-wgpu.md` | `core/src/gpu/invert.rs` |
| `RANG_GPU_LAYERS_PER_BATCH` | unset (as many as the budget allows) | speed | upper bound on the w-layers per GPU batch | `research/x2-wgpu.md` | `core/src/gpu/invert.rs` |
| `RANG_DF1_LIB` | no longer read | retired | was a prebuilt w-gridder library loaded through ctypes (DF1); W4-3 removed the fallback | `research/w4-3-kernels.md` | `-` |
| `RANG_WGRIDDER_SIMD` | unset (AVX-512 where available) | speed | `avx2` or `baseline` caps the w-gridder's instruction set | `research/df2-wgridder-speed.md` | `core/src/wgridder.rs` |
| `RANG_WGRIDDER_PLANE_GROUP` | 1 | speed | w-planes gridded together | `research/df2-wgridder-speed.md` | `core/src/wgridder.rs` |
| `RANG_WGRIDDER_TIMING` | unset | output | phase timings of the w-gridder on stderr | `research/df2-wgridder-speed.md` | `core/src/wgridder.rs` |
| `RANG_C1_LIB` | no longer read | retired | was a prebuilt closure-score library loaded through ctypes (C1); W4-3 moved the kernel into the extension | `research/w4-3-kernels.md` | `-` |
| `RANG_P6` | unset (the frozen calls) | result | `1` runs the signal track's ported guard and influence functions | `research/p6-python-hotspots.md` | `python/rang/core_signal.py` |
| `RANG_TOY_BIN` | unset (the extension) | result | a pointing-toy binary run instead of the extension | `research/p7-architecture.md` | `python/rang/__init__.py` |
| `RANG_FLAGGING_SUITE_IMAGE` | unset | result | the container image the trend run's configuration records | `research/flagging-parallel.md` | `python/rang/core_trend_run.py` |
| `RANG_STRATEGY_DIR` | unset (the CARACAL strategy inputs under outputs/) | input | directory of the Tricolour strategies the notebook flags with | `research/d2-notebook.md` | `python/rang/notebook/flags.py` |
| `RANG_FIXTURE` | unset (outputs/ska-pointing/outer_scans.zip) | input | the notebook's pointing fixture | `research/d2-notebook.md` | `python/rang/notebook/data.py` |
| `RANG_LUNO_SLICE` | unset (task G's fetch) | input | the notebook's LUNO slice directory | `research/d2-notebook.md` | `python/rang/notebook/data.py` |
| `RANG_LUNO_EXTRA` | unset (the solve inputs) | input | the notebook's LUNO extra-columns directory | `research/d2-notebook.md` | `python/rang/notebook/data.py` |
| `RANG_HOLOGRAPHY_PRODUCT` | unset (outputs/b1-20261030-05-holography) | input | the notebook's holography product | `research/d3-science-notebooks.md` | `python/rang/notebook/science.py` |
| `RANG_NOTEBOOK_CACHE` | unset (~/.cache/rang-notebook) | process | the notebook's download cache | `research/d2-notebook.md` | `python/rang/notebook/data.py` |
| `RANG_NOTEBOOK_LUNO` | unset (off) | process | `1` runs the notebook's LUNO section | `research/d2-notebook.md` | `python/rang/notebook/science.py` |
| `RANG_NOTEBOOK_SLOW` | unset (off) | process | `1` runs the notebook's slow JAX audits | `research/d3-science-notebooks.md` | `python/rang/notebook/science.py` |
| `RANG_NOTEBOOK_HOLOGRAPHY` | unset (off) | process | `1` draws the notebook's holography maps | `research/d3-science-notebooks.md` | `python/rang/notebook/science.py` |
| `RANG_NOTEBOOK_CARTA` | 0 | process | `1` opens the notebook's images in CARTA | `research/nb-carta.md` | `python/rang/notebook/carta.py` |
| `RANG_PIN_THREADS` | unset (caps on) | process | `0` turns off the CLI's BLAS and XLA thread caps (the thread variables themselves are recorded under `threads`) | `research/p9-cli.md` | `python/rang/core_cli.py` |
| `RANG_CHECKALL_LOCK` | unset (~/.rang-checkall-v2.lock) | process | the check's host lock file | `research/p10-tests.md` | `python/rang/check.py` |
| `RANG_CHECKALL_LOCKED` | unset | process | set by the check while it holds the lock | `research/p10-tests.md` | `python/rang/check.py` |
| `RANG_CORE_BACKEND` | unset | refused | the removed ctypes backend; anything but `extension` is refused | `research/p7-architecture.md` | `python/rang/core.py` |
| `RANG_CORE_LIB` | unset | refused | the removed ctypes library; setting it is refused | `research/p7-architecture.md` | `python/rang/core.py` |
| `RANG_TOY_LIB` | unset | refused | the removed toy ctypes library; recorded by `rang-core environment` | `research/p7-architecture.md` | `python/rang/core_cli.py` |
| `RANG_CARTA_URL` | unset | viewer | the CARTA backend's URL | `research/nb-carta.md` | `python/rang/notebook/carta.py` |
| `RANG_CARTA_WEBDRIVER` | unset | viewer | the CARTA backend's webdriver | `research/nb-carta.md` | `python/rang/notebook/carta.py` |
| `RANG_CARTA_SESSION_ID` | unset | viewer | the CARTA session | `research/nb-carta.md` | `python/rang/notebook/carta.py` |
| `RANG_CARTA_DIR` | unset (`<RANG_NOTEBOOK_CACHE>/carta`) | viewer | where the images for CARTA are written | `research/nb-carta.md` | `python/rang/notebook/carta.py` |
| `RANG_CARTA_ROOT` | unset | viewer | that directory as the CARTA backend sees it | `research/nb-carta.md` | `python/rang/notebook/carta.py` |
| `RANG_MS_FIXTURE` | unset (the tests skip) | test | a real Measurement Set for the reader and writer unit tests | `research/core-e-ms-reader.md` | `core/src/ms.rs` |


## Measured acceptance

All runs were made in WSL Ubuntu, Python 3.14.8 and Rust 1.93, with
`OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4` and every registry variable
unset. Everything is under `outputs/w4-1-20261031-01/` (ignored):

- the driver `accept.sh`, the diffs `w41diff.py` and `diff.txt`, and the
  identity suite `identity.py` (P12's copy);
- the phases `before/` (ecccbf0, the editable install built from it) and
  `after/` (eca9061, rebuilt with `maturin develop --release`);
- the identity runs in `identity/console-{before,after}`, and `head-*.txt`.

| Item | Result | Evidence |
| --- | --- | --- |
| r02: the variable appears in the receipt | **pass**. Gains still differ under `qp_weights=transposed` and under `anderson=3`, as they must. `RANG_SOLVE_OPTIONS` is now in `_environment_record` (null when unset) and has the set value when set. Through the CLI, `RANG_SOLVE_OPTIONS=qp_weights=transposed rang-core environment` writes `qp_weights=transposed` into both the version-3 receipt and `environment.json` | `r02_solve_env.log`, `r02-cli/` |
| r05: the wheel outside a checkout | **pass**. The wheel was installed into a venv inside a scratch git repository, with cargo off `PATH`. `checkout_root()` is None, and `_commit()` and the receipt's `commit` are null. `source` names `rang-core 0.1.0` and the extension SHA256 `8cdfbf32…`; nothing names the scratch repository's HEAD. `source_receipts()` runs: 89 entries, all inside the installed package, the extension included. A `rang-core --receipt` run from the wheel also writes `commit: null` | `r05_wheel.sh`, `r05_wheel_probe.py`, `r05_wheel.log`, `r05_cli_receipt.json` |
| P9 identity suite, 20 cases through `rang-core` | **pass**: `identity.py diff` prints `identical`. Every exit status, stdout and comparator receipt is identical; exits are 17 × 0, with `trend-frozen`, `campaign-check` and `backends` at 1, as at P9 | `identity/` |
| K comparator (precondition and checker) | **pass, unchanged**: the precondition's `all_passed` is true (χ² 0.26823507), and the K checker is identical (it is in the identity suite) | `after/k-pre*` |
| L1 (precondition and checker on run `-01`) | **unchanged**. Every non-volatile leaf is identical. The checker exits 1 with criteria 2, 4 and 6 failing, as frozen; the precondition passes. The replay's `cost_clause` ratio and `comparable` are timing ratios on a shared host | `after/l1-*` |
| L2 (precondition and checker on runs `-02`) | **unchanged**, identical apart from timings | `after/l2-*` |
| L1-M (checker on `-01`, `-02b`, `-03`) | **unchanged**, identical; criteria pass as archived | `after/l1m-check*` |
| C1 (checker on `-01`) | **unchanged**, identical; criteria 1–6 pass | `after/c1-check*` |
| L5 (fixture sweep, now through `options=`) | **pass, bit-identical**. `result.json` before (environment-driven) and after (argument-driven) is identical except `environment`. It also equals the archived sweep `outputs/l5-solver-20261030-08` on all 32,244 shared non-timing leaves: the only additional key is the later `reused_R`, and the default gains SHA256 is `7b370c13…` | `after/l5-fixture/` |
| Every campaign writer run once | **pass**. `rang_environment` is present in K's `receipt.json` (a full K run at 4 workers, 116 s), in L1-M's `l1m.json` (stored-model smoke, stations 0–3) and in the imaging `provenance` (`core_imaging.run`). It is also in C1's `c1.json` (smoke, stations 0–3), rerun after merging W4-3: before the merge, C1's standalone build needed cargo on `PATH` | `writers/`, `writers.log`, `writers-c1.log` |
| Smoke run of the L1 driver (stations 0–3) | `receipt.json` and `environment.json` gain `rang_environment`; results are identical | `after/smoke-array*` |
| Receipts differ only in the new fields | **pass**. Across 27 CLI receipts the differences are `version` 2→3, `+source`, `+environment.rang_environment`, `commit.head`, the extension SHA256, and output tree hashes and sizes (the outputs now carry the record). Campaign records gain `rang_environment` and change only the `code_sha256` and `library_sha256` of the edited files | `diff.txt` |
| Default solves bit-identical | **pass**: `tests/test_p1_solver.py`, `tests/test_core_backends.py`, `tests/test_core.py`, `tests/test_p7_architecture.py` | targeted pytest |
| Rust | **pass**: `cargo test --release --lib solve::`, 15 tests, the new one included | – |
| After merging `main` (W4-3) | **pass**: the extension was rebuilt, then the receipt, L5, P11, D1, W4-3, P1, backends and PC1 tests ran (87 passed, 1 skipped) | targeted pytest |
| `tests/test_pc1_preconditions.py` | **pass**: 2 passed, none skipped | targeted pytest |

Before and after differ in `commit.dirty` and `git_status_unchanged` for
four cases, for this reason. The baseline's last cases ran while
`core/src/*.rs` was being edited, before the extension was rebuilt. So the
`before` tree was dirty but its extension was ecccbf0's: the extension
SHA256 `4a11496c…` is the same in every `before` receipt.

## Deviations

- **`core_receipts.py` is no longer a P11 verbatim extract.** Its one
  definition had to change, which the extract test forbids. In
  `tests/test_p11_extract.py` the count is now 19 and `core_receipts`
  maps back to `flagging_next` for `core_trend_run`'s in-body import
  (`core_trend_run` itself is still verbatim). `research/p11-extract.md`'s
  count of 20 is now historical.
- Files outside the owner list, each a minimal hunk:
  - `examples/run_l5_solver_study.py`, one line: L5's receipt writer is
    the driver's `environment()`.
  - `python/rang/core_compare.py`, one line: `rang_environment` in
    `BACKENDS_VOLATILE`.
  - `docs/gen_cli.py` and `docs/cli.md`: the version-3 intro and the
    generated variable table.
- The flags and backends stages write their records through
  `core_compare` or `examples/`. For them the `rang-core` CLI receipt
  (`environment.rang_environment`) is the record; their comparator
  receipts are unchanged, which the identity suite checks.
- Registry scope:
  - The registry covers every `RANG_*` read under `python/rang/` and the
    Rust sources, 37 names, beyond the eight the task listed.
  - `tools/` (check-all, wheel scripts, AOFlagger oracle probes) is
    outside the package and not in the grep. Its `RANG_WHEEL_*`,
    `RANG_AFLAG_PARAMS` and `RANG_SENS` are test-harness variables.
  - The GPU variables `RANG_GPU_ADAPTER`, `RANG_GPU_MEMORY_MB` and
    `RANG_GPU_LAYERS_PER_BATCH` are still read in Rust
    (`core/src/gpu/`). So are `RANG_WGRIDDER_SIMD`, `_PLANE_GROUP` and
    `_TIMING` (`core/src/wgridder.rs`).
  - Of those six, the speed and output kinds are measured result-neutral
    and are recorded. `RANG_GPU_ADAPTER` selects a device and is recorded
    as result-affecting. Only the solver variables were moved out of the
    core, as the task asks.
- Coordinator note (W4-3): `main` fdf186b is merged into the branch
  (merge commit c834eec, no conflicts). `RANG_C1_LIB` and `RANG_DF1_LIB`
  are now retired registry entries, not result-affecting ones.
- Malformed options are now caught before the solve, by
  `rang_core_solve_options_parse`. `core.solve_complex` still raises
  `RuntimeError("... status 1 ...")`, and `core.solve_options` raises
  ValueError.
- `rang.archive` stays at version 1. Its `commit` comes from the same
  `_commit()` and is therefore null outside a checkout, which is new
  behaviour for that field.
- The checkout predicate tests the three manifests at `parents[2]` only.
  It does not search upwards from the working directory as
  `check.find_root` does, because a working directory inside another
  checkout must not name that checkout's commit.

## Timings

| Step | Wall |
| --- | ---: |
| `uv venv` + `uv pip install -e .[...]` (builds the extension) | 230 s |
| baseline: identity suite / K pre / L1 pre / L1 check / L2 check / L1-M check / C1 check / L5 fixture sweep / L1 smoke / L2 pre | 20.1 / 4.0 / 19.8 / 7.0 / 8.7 / 18.6 / 5.8 / 12.2 / 37.8 / 15.4 s |
| after: same cases | 14.6 / 2.9 / 16.2 / 5.6 / 4.5 / 16.7 / 6.4 / 12.4 / 39.0 / 14.3 s |
| `cargo check --all-targets` (core) | 13.0 s |
| `maturin develop --release` | 188 s |
| `cargo test --release --lib solve::` | 173 s (build), 0.9 s tests |
| targeted pytest (10 files, 83 tests) / receipt tests (6 files) / after the merge (10 files) | 43.6 s / 10.2 s / 51.8 s |
| writers: C1 smoke (after the merge) / L1-M smoke / imaging run / K run at 4 workers | 35.7 / 41.3 / 8.6 / 116.1 s |
| `maturin develop --release` after merging W4-3 | 64 s |
| `maturin build --release` (wheel, target reused) | 1 s |
| r02 / r05 (venv, install from the uv cache, probe) | 1.1 s / 0.9 s |
| `bash tools/check-all.sh` | 1156 s, lock wait included |

## Checks

`bash tools/check-all.sh` at 98241a5, with this report in the tree, printed
`## overall: PASS`: pytest 750 passed, 18 skipped. Log:
`outputs/w4-1-20261031-check-all.log`.

## For the coordinator

### Coordinator-file hunks

These are the hunks in `python/rang/core.py`, `python/rang/core_cli.py`,
`core/src/ffi.rs` and `core/py/src/lib.rs`, verbatim
(`git diff fdf186b..w4-1-receipts -- <files>`, which is against `main` with W4-3 merged; blank context lines are shown empty). In `lib.rs` only the solve
bindings change, plus one registration line after `solve_complex`'s.

```diff
diff --git a/core/py/src/lib.rs b/core/py/src/lib.rs
index 6cd0ea1..4dd5538 100644
--- a/core/py/src/lib.rs
+++ b/core/py/src/lib.rs
@@ -213,7 +213,26 @@ fn fused(
     }))
 }

+/// `rang_core_solve_options_parse`; returns (status, transposed qp weights,
+/// stop code, tolerance, anderson, freeze), the parts `solve_complex` takes.
+#[pyfunction]
+fn solve_options_parse(text: &str) -> (i32, u8, u8, f64, usize, u8) {
+    let mut out = ffi::SolveOptions::default();
+    // SAFETY: `text` is a live UTF-8 buffer of its length; `out` is local.
+    let status = unsafe { ffi::rang_core_solve_options_parse(text.as_ptr(), text.len(), &mut out) };
+    (
+        status,
+        out.transposed_qp_weights,
+        out.stop,
+        out.tolerance,
+        out.anderson,
+        out.freeze,
+    )
+}
+
 /// `rang_core_solve_complex`; returns (status, iterations, converged fraction).
+/// `options` are the parts from `solve_options_parse` and `trace` the trace
+/// file or None (task W4-1: the core no longer reads the environment).
 #[pyfunction]
 #[allow(clippy::too_many_arguments)]
 fn solve_complex(
@@ -238,7 +257,11 @@ fn solve_complex(
     stop_fraction: f64,
     mut gains: Rw<'_, f64>,
     mut flags: Rw<'_, i8>,
+    options: (u8, u8, f64, usize, u8),
+    trace: Option<String>,
 ) -> PyResult<(i32, usize, f64)> {
+    let (transposed_qp_weights, stop, tolerance, anderson, freeze) = options;
+    let trace = trace.unwrap_or_default();
     let inputs = ffi::SolveInputs {
         nrow,
         nchan,
@@ -258,6 +281,15 @@ fn solve_complex(
         max_iterations,
         stop_criterion,
         stop_fraction,
+        options: ffi::SolveOptions {
+            transposed_qp_weights,
+            stop,
+            tolerance,
+            anderson,
+            freeze,
+        },
+        trace: trace.as_ptr(),
+        trace_len: trace.len(),
     };
     let mut iterations = 0usize;
     let mut converged = 0f64;
@@ -2234,6 +2266,7 @@ fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
     m.add_function(wrap_pyfunction!(data_address, m)?)?;
     m.add_function(wrap_pyfunction!(fused, m)?)?;
     m.add_function(wrap_pyfunction!(solve_complex, m)?)?;
+    m.add_function(wrap_pyfunction!(solve_options_parse, m)?)?;
     m.add_function(wrap_pyfunction!(predict_components, m)?)?;
     m.add_function(wrap_pyfunction!(blosc_size, m)?)?;
     m.add_function(wrap_pyfunction!(blosc_decode, m)?)?;
diff --git a/core/src/ffi.rs b/core/src/ffi.rs
index 721e06b..bc0e680 100755
--- a/core/src/ffi.rs
+++ b/core/src/ffi.rs
@@ -188,6 +188,94 @@ pub struct SolveInputs {
     pub max_iterations: usize,
     pub stop_criterion: f64,
     pub stop_fraction: f64,
+    /// Run-time solver options (task W4-1: passed, no longer read from
+    /// `RANG_SOLVE_OPTIONS` by the core); all zero is the archived solver.
+    pub options: SolveOptions,
+    /// UTF-8 path of a per-iteration trace to write, `trace_len` bytes; null
+    /// or empty means no trace (task W4-1: was `RANG_SOLVE_TRACE`).
+    pub trace: *const u8,
+    pub trace_len: usize,
+}
+
+/// The parts of `solve::Options` (see `solve::Options::from_parts`).
+#[repr(C)]
+#[derive(Clone, Copy, Debug, Default, PartialEq)]
+pub struct SolveOptions {
+    /// 1: issue 452's transposed qp weights; 0 archived.
+    pub transposed_qp_weights: u8,
+    /// 0 gain (archived), 1 product, 2 loss.
+    pub stop: u8,
+    /// Tolerance of the product and loss tests (ignored for gain).
+    pub tolerance: f64,
+    /// Anderson depth, 0 off, at most `solve::MAX_ANDERSON`.
+    pub anderson: usize,
+    /// 1: an interval that passes its test stops iterating.
+    pub freeze: u8,
+}
+
+impl SolveOptions {
+    fn options(&self) -> Result<solve::Options, solve::Error> {
+        if self.transposed_qp_weights > 1 || self.freeze > 1 {
+            return Err(solve::Error::Options("flags are 0 or 1"));
+        }
+        solve::Options::from_parts(
+            self.transposed_qp_weights == 1,
+            self.stop,
+            self.tolerance,
+            self.anderson,
+            self.freeze == 1,
+        )
+    }
+}
+
+/// Parse the `RANG_SOLVE_OPTIONS` syntax (`solve::OPTIONS_SYNTAX`), `len`
+/// UTF-8 bytes, into `out`: the one parser of the solver options, which the
+/// Python wrapper calls before `rang_core_solve_complex` (task W4-1).
+/// Returns 0 on success, 1 on malformed text or invalid arguments, 2 on a
+/// panic.
+///
+/// # Safety
+/// `text` must reference `len` live bytes (or be null with `len` 0) and
+/// `out` a live `SolveOptions`.
+#[unsafe(no_mangle)]
+pub unsafe extern "C" fn rang_core_solve_options_parse(
+    text: *const u8,
+    len: usize,
+    out: *mut SolveOptions,
+) -> i32 {
+    let result = std::panic::catch_unwind(|| {
+        // SAFETY: the caller passes a valid output pointer.
+        let Some(out) = (unsafe { out.as_mut() }) else {
+            return 1;
+        };
+        // SAFETY: `len` live bytes, per the contract.
+        let bytes = if len == 0 {
+            &[][..]
+        } else {
+            match unsafe { slice(text, len) } {
+                Some(b) => b,
+                None => return 1,
+            }
+        };
+        let Ok(text) = std::str::from_utf8(bytes) else {
+            return 1;
+        };
+        match solve::Options::parse(text) {
+            Ok(options) => {
+                let (transposed, stop, tolerance, anderson, freeze) = options.parts();
+                *out = SolveOptions {
+                    transposed_qp_weights: u8::from(transposed),
+                    stop,
+                    tolerance,
+                    anderson,
+                    freeze: u8::from(freeze),
+                };
+                0
+            }
+            Err(_) => 1,
+        }
+    });
+    result.unwrap_or(2)
 }

 /// Caller-owned outputs of the `complex` solver.
@@ -201,8 +289,10 @@ pub struct SolveOutputs {
     pub converged_fraction: *mut f64,
 }

-/// Run the ported QuartiCal `complex` solver. Returns 0 on success, 1 on
-/// invalid arguments, 3 on a complex division by zero, 2 on a panic.
+/// Run the ported QuartiCal `complex` solver with `inputs.options` and, if
+/// `inputs.trace` names a file, its trace. Returns 0 on success, 1 on
+/// invalid arguments (invalid options, an unwritable trace), 3 on a complex
+/// division by zero, 2 on a panic.
 ///
 /// # Safety
 /// Every non-null pointer must reference live, aligned, nonoverlapping
@@ -286,7 +376,18 @@ pub unsafe extern "C" fn rang_core_solve_complex(
                 stop_criterion: i.stop_criterion,
                 stop_fraction: i.stop_fraction,
             };
-            match solve::solve(&problem, &settings) {
+            let Ok(options) = i.options.options() else {
+                return 1;
+            };
+            let trace = if i.trace_len == 0 {
+                None
+            } else {
+                match slice(i.trace, i.trace_len).map(std::str::from_utf8) {
+                    Some(Ok(path)) => Some(std::path::Path::new(path)),
+                    _ => return 1,
+                }
+            };
+            match solve::solve_recorded(&problem, &settings, &options, trace) {
                 Ok(solution) => {
                     let gains = slice_mut(o.gains, 8 * ngains);
                     for (g, jones) in solution.gains.iter().enumerate() {
diff --git a/python/rang/core.py b/python/rang/core.py
index 88a0ce3..a1ce6d7 100755
--- a/python/rang/core.py
+++ b/python/rang/core.py
@@ -13,6 +13,15 @@ built by Cargo at run time: nothing here runs a compiler, and the extension
 releases the GIL around every kernel. `RANG_CORE_BACKEND` and `RANG_CORE_LIB`
 are no longer read, except that asking for the ctypes backend through either
 is refused, so an old command line cannot record a library it did not use.
+
+Task W4-1 (research/w4-1-receipts.md): `ENVIRONMENT` is the one registry of
+every `RANG_*` variable the package or the Rust core reads; receipts record
+`environment_settings()` and docs/environment.md is generated from it
+(`environment_markdown`). `solve_complex` takes `options=` and `trace=`
+explicitly; only when they are None does it read `RANG_SOLVE_OPTIONS` and
+`RANG_SOLVE_TRACE`, once per call, and the core itself reads neither.
+`checkout_root()` is the checkout the package runs from, or None for an
+installed wheel.
 """

 import os
@@ -26,6 +35,388 @@ SPLITS = ("train", "validation", "test")
 SPLIT_CODES = {"train": 1, "validation": 2, "test": 3}


+# --- the environment registry (task W4-1, research/w4-1-receipts.md) --------
+
+
+@dataclass(frozen=True)
+class Variable:
+    """One environment variable read by the package or the Rust core."""
+
+    name: str
+    default: str
+    kind: str
+    effect: str
+    report: str
+    reader: str
+
+
+# What each kind means; receipts record the kinds in RECORDED_KINDS.
+KINDS = {
+    "result": "changes computed numbers, or which code or binary computes them",
+    "input": "selects input data or files",
+    "speed": "changes speed or memory only (measured result-neutral)",
+    "output": "adds a diagnostic output; the results are unchanged",
+    "process": "changes how a command, check or notebook runs",
+    "refused": "removed; setting it is an error",
+    "viewer": "the notebook's CARTA viewer connection; not recorded",
+    "test": "a Rust unit-test fixture; not recorded",
+    "retired": "read by no code any more (kept so old receipts stay explained); not recorded",
+}
+RECORDED_KINDS = ("result", "input", "speed", "output", "process", "refused")
+
+
+def _v(name, default, kind, effect, report, reader):
+    return Variable(name, default, kind, effect, f"research/{report}.md", reader)
+
+
+ENVIRONMENT = (
+    _v(
+        "RANG_SOLVE_OPTIONS",
+        "unset (the archived solver)",
+        "result",
+        "solver options `qp_weights`, `stop`, `anderson`, `freeze`; read by "
+        "`core.solve_complex` when `options=` is None",
+        "l5-solver-science",
+        "python/rang/core.py",
+    ),
+    _v(
+        "RANG_SOLVE_TRACE",
+        "unset (no trace)",
+        "output",
+        "file for the per-iteration solver trace; read by "
+        "`core.solve_complex` when `trace=` is None",
+        "l5-solver-science",
+        "python/rang/core.py",
+    ),
+    _v(
+        "RANG_GRIDDER_DEVICE",
+        "cpu",
+        "result",
+        "`gpu` runs the inversion on wgpu (cargo feature `gpu`)",
+        "x2-wgpu",
+        "python/rang/core_grid.py",
+    ),
+    _v(
+        "RANG_GRIDDER_GPU_PRECISION",
+        "f64",
+        "result",
+        "`f32` selects the GPU path toleranced to 1e-4",
+        "x2-wgpu",
+        "python/rang/core_grid.py",
+    ),
+    _v(
+        "RANG_GPU_ADAPTER",
+        "unset (the best adapter)",
+        "result",
+        "substring of the name of the GPU adapter to use",
+        "x2-wgpu",
+        "core/src/gpu/context.rs",
+    ),
+    _v(
+        "RANG_GPU_MEMORY_MB",
+        "256",
+        "speed",
+        "device-memory budget per GPU inversion (batching only)",
+        "x2-wgpu",
+        "core/src/gpu/invert.rs",
+    ),
+    _v(
+        "RANG_GPU_LAYERS_PER_BATCH",
+        "unset (as many as the budget allows)",
+        "speed",
+        "upper bound on the w-layers per GPU batch",
+        "x2-wgpu",
+        "core/src/gpu/invert.rs",
+    ),
+    _v(
+        "RANG_DF1_LIB",
+        "no longer read",
+        "retired",
+        "was a prebuilt w-gridder library loaded through ctypes (DF1); W4-3 "
+        "removed the fallback",
+        "w4-3-kernels",
+        "-",
+    ),
+    _v(
+        "RANG_WGRIDDER_SIMD",
+        "unset (AVX-512 where available)",
+        "speed",
+        "`avx2` or `baseline` caps the w-gridder's instruction set",
+        "df2-wgridder-speed",
+        "core/src/wgridder.rs",
+    ),
+    _v(
+        "RANG_WGRIDDER_PLANE_GROUP",
+        "1",
+        "speed",
+        "w-planes gridded together",
+        "df2-wgridder-speed",
+        "core/src/wgridder.rs",
+    ),
+    _v(
+        "RANG_WGRIDDER_TIMING",
+        "unset",
+        "output",
+        "phase timings of the w-gridder on stderr",
+        "df2-wgridder-speed",
+        "core/src/wgridder.rs",
+    ),
+    _v(
+        "RANG_C1_LIB",
+        "no longer read",
+        "retired",
+        "was a prebuilt closure-score library loaded through ctypes (C1); "
+        "W4-3 moved the kernel into the extension",
+        "w4-3-kernels",
+        "-",
+    ),
+    _v(
+        "RANG_P6",
+        "unset (the frozen calls)",
+        "result",
+        "`1` runs the signal track's ported guard and influence functions",
+        "p6-python-hotspots",
+        "python/rang/core_signal.py",
+    ),
+    _v(
+        "RANG_TOY_BIN",
+        "unset (the extension)",
+        "result",
+        "a pointing-toy binary run instead of the extension",
+        "p7-architecture",
+        "python/rang/__init__.py",
+    ),
+    _v(
+        "RANG_FLAGGING_SUITE_IMAGE",
+        "unset",
+        "result",
+        "the container image the trend run's configuration records",
+        "flagging-parallel",
+        "python/rang/core_trend_run.py",
+    ),
+    _v(
+        "RANG_STRATEGY_DIR",
+        "unset (the CARACAL strategy inputs under outputs/)",
+        "input",
+        "directory of the Tricolour strategies the notebook flags with",
+        "d2-notebook",
+        "python/rang/notebook/flags.py",
+    ),
+    _v(
+        "RANG_FIXTURE",
+        "unset (outputs/ska-pointing/outer_scans.zip)",
+        "input",
+        "the notebook's pointing fixture",
+        "d2-notebook",
+        "python/rang/notebook/data.py",
+    ),
+    _v(
+        "RANG_LUNO_SLICE",
+        "unset (task G's fetch)",
+        "input",
+        "the notebook's LUNO slice directory",
+        "d2-notebook",
+        "python/rang/notebook/data.py",
+    ),
+    _v(
+        "RANG_LUNO_EXTRA",
+        "unset (the solve inputs)",
+        "input",
+        "the notebook's LUNO extra-columns directory",
+        "d2-notebook",
+        "python/rang/notebook/data.py",
+    ),
+    _v(
+        "RANG_HOLOGRAPHY_PRODUCT",
+        "unset (outputs/b1-20261030-05-holography)",
+        "input",
+        "the notebook's holography product",
+        "d3-science-notebooks",
+        "python/rang/notebook/science.py",
+    ),
+    _v(
+        "RANG_NOTEBOOK_CACHE",
+        "unset (~/.cache/rang-notebook)",
+        "process",
+        "the notebook's download cache",
+        "d2-notebook",
+        "python/rang/notebook/data.py",
+    ),
+    _v(
+        "RANG_NOTEBOOK_LUNO",
+        "unset (off)",
+        "process",
+        "`1` runs the notebook's LUNO section",
+        "d2-notebook",
+        "python/rang/notebook/science.py",
+    ),
+    _v(
+        "RANG_NOTEBOOK_SLOW",
+        "unset (off)",
+        "process",
+        "`1` runs the notebook's slow JAX audits",
+        "d3-science-notebooks",
+        "python/rang/notebook/science.py",
+    ),
+    _v(
+        "RANG_NOTEBOOK_HOLOGRAPHY",
+        "unset (off)",
+        "process",
+        "`1` draws the notebook's holography maps",
+        "d3-science-notebooks",
+        "python/rang/notebook/science.py",
+    ),
+    _v(
+        "RANG_NOTEBOOK_CARTA",
+        "0",
+        "process",
+        "`1` opens the notebook's images in CARTA",
+        "nb-carta",
+        "python/rang/notebook/carta.py",
+    ),
+    _v(
+        "RANG_PIN_THREADS",
+        "unset (caps on)",
+        "process",
+        "`0` turns off the CLI's BLAS and XLA thread caps (the thread "
+        "variables themselves are recorded under `threads`)",
+        "p9-cli",
+        "python/rang/core_cli.py",
+    ),
+    _v(
+        "RANG_CHECKALL_LOCK",
+        "unset (~/.rang-checkall-v2.lock)",
+        "process",
+        "the check's host lock file",
+        "p10-tests",
+        "python/rang/check.py",
+    ),
+    _v(
+        "RANG_CHECKALL_LOCKED",
+        "unset",
+        "process",
+        "set by the check while it holds the lock",
+        "p10-tests",
+        "python/rang/check.py",
+    ),
+    _v(
+        "RANG_CORE_BACKEND",
+        "unset",
+        "refused",
+        "the removed ctypes backend; anything but `extension` is refused",
+        "p7-architecture",
+        "python/rang/core.py",
+    ),
+    _v(
+        "RANG_CORE_LIB",
+        "unset",
+        "refused",
+        "the removed ctypes library; setting it is refused",
+        "p7-architecture",
+        "python/rang/core.py",
+    ),
+    _v(
+        "RANG_TOY_LIB",
+        "unset",
+        "refused",
+        "the removed toy ctypes library; recorded by `rang-core environment`",
+        "p7-architecture",
+        "python/rang/core_cli.py",
+    ),
+    _v(
+        "RANG_CARTA_URL",
+        "unset",
+        "viewer",
+        "the CARTA backend's URL",
+        "nb-carta",
+        "python/rang/notebook/carta.py",
+    ),
+    _v(
+        "RANG_CARTA_WEBDRIVER",
+        "unset",
+        "viewer",
+        "the CARTA backend's webdriver",
+        "nb-carta",
+        "python/rang/notebook/carta.py",
+    ),
+    _v(
+        "RANG_CARTA_SESSION_ID",
+        "unset",
+        "viewer",
+        "the CARTA session",
+        "nb-carta",
+        "python/rang/notebook/carta.py",
+    ),
+    _v(
+        "RANG_CARTA_DIR",
+        "unset (`<RANG_NOTEBOOK_CACHE>/carta`)",
+        "viewer",
+        "where the images for CARTA are written",
+        "nb-carta",
+        "python/rang/notebook/carta.py",
+    ),
+    _v(
+        "RANG_CARTA_ROOT",
+        "unset",
+        "viewer",
+        "that directory as the CARTA backend sees it",
+        "nb-carta",
+        "python/rang/notebook/carta.py",
+    ),
+    _v(
+        "RANG_MS_FIXTURE",
+        "unset (the tests skip)",
+        "test",
+        "a real Measurement Set for the reader and writer unit tests",
+        "core-e-ms-reader",
+        "core/src/ms.rs",
+    ),
+)
+# `RANG_` names in the sources that are not environment variables.
+NOT_ENVIRONMENT = {"RANG_E3": "a Measurement Set keyword written by a Rust test"}
+
+
+def environment_variables(kinds=RECORDED_KINDS):
+    """The registry entries of the given kinds, in registry order."""
+    return [v for v in ENVIRONMENT if v.kind in kinds]
+
+
+def environment_settings(environ=None):
+    """{name: value, or None when unset} of every recorded registry variable:
+    the `rang_environment` record of the receipts (task W4-1)."""
+    environ = os.environ if environ is None else environ
+    return {v.name: environ.get(v.name) for v in environment_variables()}
+
+
+def environment_markdown():
+    """The registry as a Markdown table (docs/environment.md)."""
+    lines = [
+        "| Variable | Default | Kind | What it changes | Report | Read by |",
+        "| --- | --- | --- | --- | --- | --- |",
+    ]
+    for v in ENVIRONMENT:
+        lines.append(
+            f"| `{v.name}` | {v.default} | {v.kind} | {v.effect} | "
+            f"`{v.report}` | `{v.reader}` |"
+        )
+    return "\n".join(lines) + "\n"
+
+
+MANIFESTS = ("pyproject.toml", "Cargo.toml", "core/Cargo.toml")
+
+
+def checkout_root():
+    """The source checkout the package runs from, or None.
+
+    `parents[2]` of this file is the checkout only for an editable install;
+    for an installed wheel it is `<venv>/lib/python3.X`, which may sit inside
+    any git repository. It counts only if it holds the three manifests
+    (`check.find_root`'s test), so a receipt names a commit only when there
+    is one (task W4-1)."""
+    root = Path(__file__).resolve().parents[2]
+    return root if all((root / name).is_file() for name in MANIFESTS) else None
+
+
 def core_root():
     """The core crate of the checkout (its `data/` holds the Tricolour static
     masks). Only a source checkout has it; the wheel does not need it."""
@@ -238,14 +629,78 @@ def fused_pass(
     return FusedResult(out_res, out_z, out_h, out_b, out_n, split_stats)


+SOLVE_OPTIONS_VAR = "RANG_SOLVE_OPTIONS"
+SOLVE_TRACE_VAR = "RANG_SOLVE_TRACE"
+STOP_TESTS = ("gain", "product", "loss")
+
+
+@dataclass(frozen=True)
+class SolveOptions:
+    """Parsed run-time solver options (`core/src/solve.rs`, task L5); the
+    defaults are the archived solver. `text` is what was parsed."""
+
+    text: str = ""
+    transposed_qp_weights: bool = False
+    stop: str = "gain"
+    tolerance: float = 0.0
+    anderson: int = 0
+    freeze: bool = False
+
+    def parts(self):
+        """The tuple the extension's `solve_complex` takes."""
+        return (
+            int(self.transposed_qp_weights),
+            STOP_TESTS.index(self.stop),
+            float(self.tolerance),
+            int(self.anderson),
+            int(self.freeze),
+        )
+
+    def record(self):
+        """The options as a receipt entry."""
+        return {
+            "text": self.text,
+            "qp_weights": "transposed" if self.transposed_qp_weights else "archived",
+            "stop": self.stop,
+            "tolerance": self.tolerance if self.stop != "gain" else None,
+            "anderson": self.anderson,
+            "freeze": self.freeze,
+        }
+
+
+def solve_options(options=None):
+    """`options` parsed by the core's one parser (`Options::parse`): a
+    `SolveOptions` as it is, a string in the `RANG_SOLVE_OPTIONS` syntax, or
+    None for that variable (unset means the archived solver). Raises
+    ValueError when malformed."""
+    if isinstance(options, SolveOptions):
+        return options
+    text = os.environ.get(SOLVE_OPTIONS_VAR, "") if options is None else str(options)
+    status, transposed, stop, tolerance, anderson, freeze = (
+        extension().solve_options_parse(text)
+    )
+    if status:
+        raise ValueError(
+            f"malformed solver options {text!r}: expected qp_weights=archived|"
+            "transposed, stop=gain|product:<tol>|loss:<tol>, anderson=<0..10>, "
+            "freeze=0|1"
+        )
+    return SolveOptions(
+        text, bool(transposed), STOP_TESTS[stop], tolerance, anderson, bool(freeze)
+    )
+
+
 @dataclass
 class ComplexSolution:
-    """Gains (time_bin, freq_bin, antenna, 2, 2), flags (1 flagged), counts."""
+    """Gains (time_bin, freq_bin, antenna, 2, 2), flags (1 flagged), counts,
+    and the options and trace file the solve used (task W4-1)."""

     gains: np.ndarray
     flags: np.ndarray
     iterations: int
     converged_fraction: float
+    options: SolveOptions | None = None
+    trace: str | None = None


 def solve_complex(
@@ -266,13 +721,28 @@ def solve_complex(
     max_iterations=50,
     stop_criterion=1e-7,
     stop_fraction=0.99,
+    options=None,
+    trace=None,
 ):
     """Ported QuartiCal 0.2.7 `complex` solve with rang's frozen settings.

     Rows must be sorted by time bin. See research/core-phase2.md for what is
     and is not ported. Defaults match rang's QuartiCal command (50 iterations,
     convergence criterion 1e-7) and QuartiCal's convergence fraction (0.99).
+    `options` (see `solve_options`) and `trace` (a file for the L5 trace)
+    default to `RANG_SOLVE_OPTIONS` and `RANG_SOLVE_TRACE`, read here once
+    per call; the solution records both. Malformed options raise
+    RuntimeError with status 1, as the core did before task W4-1.
     """
+    try:
+        options = solve_options(options)
+    except ValueError as exc:
+        raise RuntimeError(
+            f"rang core complex solve failed with status 1: {exc}"
+        ) from exc
+    if trace is None:
+        trace = os.environ.get(SOLVE_TRACE_VAR) or None
+    trace = None if trace is None or str(trace) == "" else str(trace)
     data = np.require(data, np.complex64, ["C", "A"])
     if data.ndim != 3 or data.shape[-1] != 4:
         raise ValueError("data must be (row, chan, 4) complex")
@@ -315,10 +785,14 @@ def solve_complex(
         stop_fraction,
         gains.view(np.float64),
         flags,
+        options.parts(),
+        trace,
     )
     if status:
         raise RuntimeError(f"rang core complex solve failed with status {status}")
-    return ComplexSolution(gains, flags, int(n_iterations), float(converged))
+    return ComplexSolution(
+        gains, flags, int(n_iterations), float(converged), options, trace
+    )


 def predict_components(
diff --git a/python/rang/core_cli.py b/python/rang/core_cli.py
index 1a22a6d..70819f6 100644
--- a/python/rang/core_cli.py
+++ b/python/rang/core_cli.py
@@ -15,8 +15,10 @@ driver in `examples/` unchanged (a checkout is needed); the others call the
 package. `rang-core STAGE archive RUN OUT.json` writes a `rang.archive`
 (version 1) that every comparator accepts as an oracle.

-Every invocation writes a `rang.receipt` (version 2): command, commit,
-environment (interpreter, platform, the extension and every thread setting),
+Every invocation writes a `rang.receipt` (version 3): command, commit (null
+outside a source checkout), source (checkout, distribution version and
+extension SHA256), environment (interpreter, platform, the extension, every
+thread setting and every recorded `RANG_*` variable of `core.ENVIRONMENT`),
 inputs and outputs with hashes, timings, exit status and, for `compare`, the
 verdict (`check` writes one only with `--receipt PATH`). By default it is
 written beside the primary output as `<output>.<verb>.rang-receipt.json`:
@@ -58,7 +60,11 @@ ROOT = Path(__file__).resolve().parents[2]
 RECEIPT_SCHEMA = "rang.receipt"
 # Version 2 (task P12, research/p12-rename.md): environment.rangtoy became
 # environment.rang_core when the package was renamed; nothing else changed.
-RECEIPT_VERSION = 2
+# Version 3 (task W4-1, research/w4-1-receipts.md): environment.rang_environment
+# (every recorded `core.ENVIRONMENT` variable, null when unset, read when the
+# command starts) and `source` (checkout, distribution, extension SHA256) were
+# added, and `commit` is null outside a checkout (`core.checkout_root`).
+RECEIPT_VERSION = 3
 ARCHIVE_SCHEMA = "rang.archive"
 ARCHIVE_VERSION = 1
 # The cab `compare` (legacy form): stage -> comparator script in examples/.
@@ -117,11 +123,23 @@ def _snapshot(inputs):
     }


+def _checkout():
+    """`core.checkout_root()`: ROOT if it holds the three manifests, else None
+    (an installed wheel; task W4-1). Imported late: `rang.core` loads NumPy."""
+    from .core import checkout_root
+
+    return checkout_root()
+
+
 def _git(*args):
+    """git in the checkout; None outside one, or when git fails."""
+    root = _checkout()
+    if root is None:
+        return None
     try:
         return subprocess.run(
             ["git", *args],
-            cwd=ROOT,
+            cwd=root,
             capture_output=True,
             text=True,
             check=True,
@@ -384,6 +402,8 @@ def environment(run_dir):
         "modules_with_quartical_references": sorted(
             m for m, v in modules.items() if v["quartical_references"]
         ),
+        # Task W4-1: every recorded RANG_* variable (null when unset).
+        "rang_environment": core.environment_settings(),
     }
     _write_json(Path(run_dir) / "environment.json", record)
     print(
@@ -532,12 +552,15 @@ def archive(stage, run_dir, out, status=None, comparisons=()):


 # ---------------------------------------------------------------------------
-# The receipt (rang.receipt version 2).
+# The receipt (rang.receipt version 3).


 def _commit():
     """HEAD and whether tracked files differ from it (untracked files such as
-    a worktree's `outputs` link do not make a tree dirty)."""
+    a worktree's `outputs` link do not make a tree dirty); None outside a
+    source checkout, where `_source` identifies the code (task W4-1)."""
+    if _checkout() is None:
+        return None
     head = _git("rev-parse", "HEAD")
     status = _git("status", "--porcelain", "--untracked-files=no")
     return {
@@ -596,11 +619,39 @@ def _extension():
     return {"path": origin.as_posix(), "sha256": _file_sha256(origin)}


-def _environment_record(pinned):
+def _distribution_version():
     try:
-        version = importlib.metadata.version("rang-core")
+        return importlib.metadata.version("rang-core")
     except importlib.metadata.PackageNotFoundError:
-        version = None
+        return None
+
+
+def _rang_environment():
+    """Every recorded `core.ENVIRONMENT` variable, None when unset (W4-1)."""
+    from .core import environment_settings
+
+    return environment_settings()
+
+
+def _source():
+    """What code ran (task W4-1): the checkout, or None for an installed
+    package, whose distribution version and extension SHA256 identify it."""
+    root = _checkout()
+    extension = _extension()
+    return {
+        "checkout": root.as_posix() if root is not None else None,
+        "distribution": "rang-core",
+        "version": _distribution_version(),
+        "extension_sha256": extension["sha256"] if extension else None,
+    }
+
+
+def _environment_record(pinned, rang_environment=None):
+    """The receipt's `environment`; `rang_environment` is the registry
+    snapshot taken when the command started (read now when None)."""
+    version = _distribution_version()
+    if rang_environment is None:
+        rang_environment = _rang_environment()
     return {
         "python": sys.version,
         "executable": Path(sys.executable).as_posix(),
@@ -612,6 +663,7 @@ def _environment_record(pinned):
         "extension": _extension(),
         "threads": {name: os.environ.get(name) for name in THREAD_VARIABLES},
         "threads_pinned_by_cli": pinned,
+        "rang_environment": rang_environment,
     }


@@ -632,6 +684,7 @@ class Receipt:
             p: _path_record(p, content=False) for p in self.paths if Path(p).exists()
         }
         self.started = datetime.now(timezone.utc).isoformat(timespec="seconds")
+        self.rang_environment = _rang_environment()
         self.clock = time.perf_counter()

     def record(self, exit_code, verdict=None):
@@ -656,7 +709,8 @@ class Receipt:
             "verb": self.verb,
             "started_utc": self.started,
             "commit": _commit(),
-            "environment": _environment_record(self.pinned),
+            "source": _source(),
+            "environment": _environment_record(self.pinned, self.rang_environment),
             "inputs": inputs,
             "outputs": outputs,
             "timings": {
```

### STATE paragraph

- **W4-1 (2026-10-31): receipts record what changed the result.**
  - `rang.receipt` version 3 records the value of every result-affecting
    `RANG_*` variable, from one registry (`rang.core.ENVIRONMENT`), and a
    `source` record. A grep test fails on any unregistered variable.
  - The K, L1, L2, L1-M, C1, imaging and L5 records carry the same
    `rang_environment`.
  - The solver takes `options=` and `trace=`. The Rust core reads no
    environment.
  - From a wheel, `commit` is null and `source_receipts()` hashes the
    installed package (W4R-01, W4R-02).
  - Results are unchanged. The P9 identity suite and the K, L1, L2, L1-M,
    C1 and L5 comparators are identical. L5 run through the new argument
    equals the archived sweep bit for bit.
  - Report: `research/w4-1-receipts.md`.

### `research/README.md` index entry

- [W4-1 receipts](w4-1-receipts.md): `rang.receipt` version 3 records the
  `RANG_*` registry and the source; the solver takes options explicitly;
  `commit: null` outside a checkout (W4R-01, W4R-02); results unchanged.

### `research/p9-cli.md` successor note

> **Successor (task W4-1, research/w4-1-receipts.md): `rang.receipt`
> version 3.** Version 3 adds `environment.rang_environment`, the value
> of every recorded variable of `rang.core.ENVIRONMENT` when the command
> starts, null when unset. It also adds a top-level `source` (`checkout`,
> `distribution`, `version`, `extension_sha256`). `commit` is null when
> the package does not run from a checkout, meaning `parents[2]` lacks
> `pyproject.toml`, `Cargo.toml` or `core/Cargo.toml`. Nothing else
> changed. Readers of version 2 receipts need no change. A comparison of
> version 2 with version 3 receipts treats the new keys as provenance, as
> P12 treated the version 1 to 2 rename.

### `research/tool-timings.md` rows

| Date | Tool | Input | Wall | Peak memory | Notes |
| --- | --- | --- | ---: | --- | --- |
| 2026-10-31 | big plan W4-1: `uv venv` + `uv pip install -e .[pointing,beam,test,imaging,formats]` | public PyPI | 230 s | – | builds the extension |
| 2026-10-31 | big plan W4-1: acceptance `before` (identity, K/L1/L2 pre, L1/L2/L1-M/C1 checks, L5 fixture sweep, L1 smoke) | `outputs/w4-1-20261031-01/before` | 20.1 + 4.0 + 19.8 + 7.0 + 8.7 + 18.6 + 5.8 + 12.2 + 37.8 + 15.4 s | – | at ecccbf0 |
| 2026-10-31 | big plan W4-1: acceptance `after` (same cases) | `outputs/w4-1-20261031-01/after` | 14.6 + 2.9 + 16.2 + 5.6 + 4.5 + 16.7 + 6.4 + 12.4 + 39.0 + 14.3 s | – | at eca9061; identical apart from the new fields |
| 2026-10-31 | big plan W4-1: `maturin develop --release` | worktree | 188 s | – |  |
| 2026-10-31 | big plan W4-1: `cargo test --release --lib solve::` | core | 173 s build, 0.9 s tests | – | 15 pass |
| 2026-10-31 | big plan W4-1: r02 / r05 (wheel in a scratch repository) | `outputs/w4-1-20261031-01` | 1.1 s / 0.9 s | – | wheel build 1 s (target reused) |
| 2026-10-31 | big plan W4-1: `bash tools/check-all.sh` | branch `w4-1-receipts` | 1156 s (lock wait included) | – | overall PASS; pytest 750 passed, 18 skipped |

### Ignored output directories

- `outputs/w4-1-20261031-01/` holds the acceptance phases, the identity
  suite, the r02 and r05 evidence and the diffs.
- `outputs/w4-1-20261031-check-all.log` is the check-all log.
- Scratch under `~/Build/tmp/20261031-w4-1/` (the wheel, the r05 scratch
  repository and the patch scripts) is deleted at the end.
