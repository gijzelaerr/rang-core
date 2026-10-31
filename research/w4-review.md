# W4: final review of the simplified core (big plan wave 4)

Status, 2026-10-31: **review done; nothing changed in the code.** The review
read `main` at `17653e4` closely, ran the static tools, the full check, a
determinism matrix, a local wheel and sdist build, and six reproduction
scripts. It found **17 findings: 1 high, 8 medium and 8 low.** No archived
result is affected. `bash tools/check-all.sh` passes (784 passed, 10
skipped), and every live kernel gives the same bits at 1, 2, 3 and 4 rayon
threads and under the gridder's SIMD and plane-group settings.

What is wrong:

- **Receipts can leave out the settings that changed a result.** The core
  solver reads `RANG_SOLVE_OPTIONS` inside every solve, and no receipt
  records it (W4R-01, the high finding).
- **Provenance is wrong outside a checkout.** An installed wheel records the
  commit of whatever git repository encloses its venv, and the trend run's
  source receipts raise `FileNotFoundError` (W4R-02).
- **The extension trusts the caller.** It takes array sizes on trust and
  reads Fortran-ordered arrays transposed. An 11-double out-of-bounds write
  was reproduced (W4R-04). One public wrapper, `core_flag.flag_rows`, can
  reach the same unchecked read (W4R-05).
- **Two kernels still run Cargo.** The closure and flux-standard kernels
  build a crate with `cargo` when they are first called, so they fail from
  the wheel. The README says nothing runs Cargo at a kernel call (W4R-06).
- **2-D string-array keywords are written in the wrong order.** The table
  writer stores them in a different element order from python-casacore
  3.8.1 (W4R-03).

**Release verdict for v0.1.0: not ready as it stands; ready after W4-1, W4-3
and W4-5.** Those are the provenance fix, the two kernels moved into the
extension, and the release metadata: `--version`, classifiers, a README that
renders on PyPI, a CHANGELOG and a check that the tag matches the version.
CI is green on all five wheel platforms at `17653e4`. The wheel's contents
are clean.

## Scope and method

**Read first:**

- `AGENTS.md`, `CONTRIBUTING.md`, `README.md`
- `research/README.md`, the head of `research/STATE.md`, `research/big-plan.md`
- `simplification-review.md`, `p7-architecture.md`, `p9-cli.md`,
  `p11-extract.md`, `p12-rename.md`
- `x1-crossplatform.md`, `wheel.md`, `d1-docs.md`

**Code read closely:**

- `python/rang/`: `__init__`, `core`, `core_cli`, `core_fetch`, `core_zarr`,
  `core_ms`, `core_ms_write`, `core_grid`, `core_weights`, `core_flag`,
  `core_closure`, `core_wgridder`, `core_receipts`, `check`, `rusage`,
  `fluxstd`, `formats/sky`, `formats/quartical_store`, `notebook/data`
- the campaign drivers' receipt, environment and fallback paths in
  `core_campaign*.py`
- `core/py/src/lib.rs`
- `core/src/`: `lib.rs`, `ffi.rs`, `ffi_flag.rs`, `ffi_grid.rs`,
  `ffi_fluxstd.rs`, `ffi_closure.rs`, `gpu/ffi.rs`
- `core/src/blosc.rs` in full
- the parallel and reduction sites of `fused.rs`, `solve.rs`, `grid.rs` and
  `wgridder.rs`; the option parsing in `solve.rs`; the endian handling in
  `ms.rs`
- `pyproject.toml`, the three `Cargo.toml`, `.github/workflows/wheels.yml`,
  `tools/check-all.sh`, `tools/wheel/build.py`

The `core_*` extracts and the other modules were skimmed for structure, with
greps for patterns:

- `unsafe` and `catch_unwind`
- `subprocess`, `pickle`, `/proc`, `resource`
- text I/O with no `encoding`
- `RANG_*` environment reads

**Tools, all public PyPI or rustup:**

- Rust 1.93.1 (`cargo`, `clippy 0.1.93`, `rustdoc`), maturin 1.16.0
- Python 3.14.8 and pytest 9 in a fresh `uv venv` with every extra in the brief
- ruff 0.17.3, vulture 2.16, radon 6.0.1, bandit 1.9.4, pip-audit 2.10.1,
  twine 7.0.0
- python-casacore 3.8.1 in a scratch Python 3.13 venv, as the oracle for
  W4R-03

`cargo-audit` was installed with `cargo install --locked`; its result is in
the timings. pyright was not run: the package has no type annotations to
check.

**Host:** AMD Ryzen 7 7700X with AVX-512, AVX2 and FMA. It was shared with
three other tasks (load 5–7), so wall times are load-dependent.

### Determinism (bit-identity claims): pass

`outputs/w4-review-20261031-03/r04_determinism.py` ran eight configurations,
each in its own process:

- `RAYON_NUM_THREADS` = 1, 2, 3 and 4, and 4 a second time
- `RANG_WGRIDDER_SIMD` = `baseline` and `avx2` (AVX-512 is the default on
  this CPU)
- `RANG_WGRIDDER_PLANE_GROUP=4`

It hashed the output of these kernels:

- the solver, both with the iteration cap and with early stopping, on 3 × 8
  intervals
- the fused pass
- the w-stacking and exact gridders, each on a small case and on a
  3000-row × 8-channel case
- the Tricolour strategies

**Every hash is identical in every configuration** (`r04.log`). The code
shows why. Parallel results are collected in input order and summed
serially (`fused.rs:400-424`, `grid.rs:572-590`). The only parallel
`reduce` (`wgridder.rs:1017-1039`) works on integers and min/max. Task
chunking depends on the data size, not on the thread count
(`wgridder.rs:1209`). The docstrings' claims that the gridder's SIMD level
and plane group do not change the result are confirmed. The 2 GPU tests
were not run (no `gpu` build in the check).

## Findings

Severity levels:

- **High** can change a scientific record silently.
- **Medium** is a defect with a concrete failure path.
- **Low** is latent, or affects only robustness or hygiene.

Categories follow the brief: 1 correctness and provenance, 2 boundary
safety, 3 portability, 4 packaging and release, 5 simplification debt, 6
documentation drift.

Verdicts:

- **C** (CONFIRMED) means reproduced, or unambiguous from the code.
- **P** (PLAUSIBLE) means it needs a run to be sure.

| Id | Sev | Cat | File:line | Defect | Failure scenario | Verdict | Fix (one sentence) | Owner files |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W4R-01 | High | 1 | `core/src/solve.rs:202-208,1227`; `python/rang/core_cli.py:83` | The solver reads `RANG_SOLVE_OPTIONS` inside every solve; no CLI or campaign receipt records it, nor `RANG_GRIDDER_DEVICE`/`_GPU_PRECISION`, `RANG_DF1_LIB` or `RANG_C1_LIB`. | A shell with `RANG_SOLVE_OPTIONS=qp_weights=transposed` (L5's opt-in) runs `rang-core campaign run`; the gains differ and the receipt looks like the archived default. | C (r02) | Read every result-affecting `RANG_*` from one registry, record it in `_environment_record` and every campaign `environment`, and pass solver options as an argument instead of the process environment. | `core_cli.py`*, `core.py`*, `core_campaign*.py`, `core_solver_study.py`, `core/src/solve.rs`, `core/src/ffi.rs`* |
| W4R-02 | Med | 1 | `core_cli.py:57,120-131,538-546`; `core_campaign.py:37,171-182`; `core_receipts.py:19-32` | `ROOT = parents[2]` is the checkout only for an editable install; in a wheel it is `<venv>/lib/python3.X`. | The receipt names the HEAD of any git repository around the venv as the commit (r05: an unrelated repository's HEAD, `dirty: false`); `source_receipts()` raises `FileNotFoundError` (`Cargo.lock`). | C (r05) | Use `check.find_root`'s test (Cargo.toml + core/Cargo.toml + pyproject.toml at ROOT), otherwise record `commit: null` with the distribution version and extension SHA256, and hash the installed package files. | `core_cli.py`*, `core_campaign.py`, `core_receipts.py`, `core_imaging.py` |
| W4R-03 | Med | 1 | `python/rang/core_ms_write.py:491-495` | 2-D string-array keywords are flattened in Fortran order with the shape reversed; numeric keywords and python-casacore use C order. | `putkeyword("TXT", [["a","b","c"],["d","e","f"]])` stores `a,d,b,e,c,f`; python-casacore 3.8.1 stores `a,b,c,d,e,f`. This breaks the byte-identity claim of E3–E5. | C (r03, r03b) | `arr.reshape(-1)` (C order), plus a 2-D string-keyword case in the oracle tests. | `core_ms_write.py`, `tests/test_t1_casacure_oracle.py` or `tests/test_e5_table_writer_rest.py` |
| W4R-04 | Med | 2 | `core/py/src/lib.rs:83-106` and the bindings `fused`, `solve_complex`, `predict_components`, `stokes_i`, `imaging_weights`, `grid_invert`, `grid_invert_gpu`, `flag_rows`; `core/src/ffi.rs:47-63` | The bindings pass pointers with no length check, and `as_slice` accepts F-contiguous arrays; the module docstring says non-contiguous arrays are refused. | Direct `rang._core` calls: a 1-element `split_stats` gets 11 doubles written past it (r01a); a Fortran-ordered `uvw` is read transposed and status 0 is returned (r01b). The shipped wrappers coerce to C order and size their outputs, so this is not reachable through them, except W4R-05. | C (r01) | `sized`/`sized_mut` on every binding (as P7's root-kernel bindings already do), an `is_c_contiguous()` check in `ptr`/`ptr_mut`, and `checked_mul` for `nrow*3`, `cells*2` and `ntime*nfreq*nant`. | `core/py/src/lib.rs`*, `core/src/ffi_grid.rs`, `core/src/gpu/ffi.rs`, `tests/test_p7_architecture.py` |
| W4R-05 | Med | 2 | `python/rang/core_flag.py:247-270` | `flag_rows` does not check that `antenna1`/`antenna2`/`times` have `nrow` entries (`zip` truncates `baseline_index`) or that `corr_type` has `ncorr`. | The kernel reads `nrow` and `ncorr` elements (`ffi_flag.rs:181-187`) past the shorter buffers and flags from heap bytes, with no error. | C (code) | Validate every length in the wrapper; W4R-04 also catches it in the binding. | `core_flag.py`, `tests/test_core_flag.py` |
| W4R-06 | Med | 4 | `core_closure.py:71-165`; `fluxstd.py:398-491` | The C1 closure and FS1 flux kernels build a standalone crate with `cargo` on first call, although `lib.rs` lists both modules and `_core.abi3.so` exports `rang_core_closure_scores` and `rang_core_fluxstd_eval`. | From the wheel both raise `RuntimeError: Run from the Rang checkout` (r05). The check builds `core/target/{c1,fs1}-standalone` during pytest. The README says nothing runs Cargo at a kernel call (README:136). | C (r05, nm, pytest) | Bind `closure_scores` and `fluxstd_eval` in the extension, call them from the wrappers, delete the standalone builders and verify the C1 and FS1 archives. | `core/py/src/lib.rs`*, `core_closure.py`, `fluxstd.py`, `tests/test_core_closure.py`, `tests/test_fluxstd.py` |
| W4R-07 | Med | 4 | `core_cli.py` (parser); `python/rang/__init__.py` | No `rang-core --version` and no `rang.__version__`. | `rang-core --version` prints "unknown option --version" and exits 1 (r05). | C (r05) | Add `--version` from `importlib.metadata.version("rang-core")` and `__version__` in `__init__`. | `core_cli.py`*, `python/rang/__init__.py` |
| W4R-08 | Med | 4 | `pyproject.toml:15-28`; `README.md:1,16,…` | The classifiers list only `Operating System :: POSIX :: Linux`, though CI builds and tests win_amd64 and macOS wheels. There are no Python version classifiers, and Repository is the only URL. On PyPI the README's logo (`docs/logo/lockup.svg`) and about 40 relative links break. | PyPI shows a Linux-only, logo-less page with dead links; `twine check` passes, so CI does not notice. | C | Add Windows, macOS and `Python :: 3.10`–`3.14` classifiers, Documentation and Issues URLs, and absolute URLs (or a short PyPI README). | `pyproject.toml`, `README.md`* |
| W4R-09 | Low | 1 | `core_zarr.py:24-31`; `core_fetch.py:39-44,56-70,297-312,409-462,486-489` | Zarr ingest never checks `.zarray` `order`, and `core_fetch` hard-codes the row-column dtypes. `core_fetch`'s block table lacks `core_zarr.read_rows`'s fallback for blocks stored out of order. | An F-order store would decode transposed without error, and a row column stored as `<i8` would be misread. A QuartiCal-style chunk with out-of-order blocks fails to decode instead of falling back. Latent: all 400 archived `.zarray` files are `order: C`, and the row dtypes match. | C (code), latent | Assert `order == "C"` and the expected dtypes, and share one block-table helper with the out-of-order fallback. | `core_zarr.py`, `core_fetch.py` |
| W4R-10 | Low | 2 | `core/src/blosc.rs:369-410`; `core/src/ffi_fluxstd.rs:14` | `decode_span_rows` does not check that every requested row lies inside blocks `first..first+count`. `rang_core_fluxstd_eval` has no `catch_unwind`. | Rows outside the run are left as the caller's `np.empty` bytes, and status 0 is returned (the wrappers always cover them). A panic in `fluxstd` aborts the process. | C (code) | Return 1 when a row is not covered, and wrap the function in `catch_unwind`. | `core/src/blosc.rs`, `core/src/ffi_correct.rs`, `core/src/ffi_fluxstd.rs` |
| W4R-11 | Med | 3 | 73 `read_text()` and about 29 `write_text(` with no `encoding`, e.g. `formats/sky.py:246,462,868,968,1116`, `formats/quartical_store.py:111-276`, `formats/_aipsio.py:193`, `formats/flagversions.py:29,94`, `core_ms_write.py:607` | Before Python 3.15, Windows reads and writes these in the locale code page. CI cannot see it because `wheels.yml:175` sets `PYTHONUTF8=1`. | A Tigger or BBS sky model with non-ASCII names, or a `table.info` readme, is mis-decoded or raises on a stock Windows Python. | C (code) | Pass `encoding="utf-8"` (and `newline="\n"` where a file is hashed), add a test or ruff `PLW1514` (preview), and run one CI job without `PYTHONUTF8`. | the files listed, `.github/workflows/wheels.yml` |
| W4R-12 | Low | 3 | repository root (no `.gitattributes`) | 13 tracked files are CRLF, including the packaged `python/rang/notebook/science.py`, `tests/test_core_imaging.py`, `tests/test_d3_notebooks.py`, `docs/execute_notebooks.py` and 7 SVGs. X1's `* text=auto eol=lf` was never added. | A Windows clone without `core.autocrlf=false` hashes and formats differently; the CI works around this with a global git setting. | C | Add `.gitattributes` and renormalise once; check that no receipt hashes a renormalised file. | `.gitattributes`, the 13 files |
| W4R-13 | Low | 4 | `.github/workflows/wheels.yml:190-241`; repository root | Publishing runs on any `v*` tag without checking that the tag equals `pyproject` `version`. There is no CHANGELOG. `checkout@v4`, `setup-python@v5`, `upload-`/`download-artifact@v4` and `cache@v4` run on the deprecated Node 20. | Tagging `v0.1.1` without the bump publishes a second `0.1.0` attempt, which PyPI rejects only after the release job has run. | C | Add a tag-equals-version step to `release` and `publish`, a `CHANGELOG.md`, and bump the actions. | `.github/workflows/wheels.yml`, `CHANGELOG.md` |
| W4R-14 | Low | 4 | `pyproject.toml` `[tool.maturin]` (no include/exclude) | The sdist packs the whole tree: 1,010 entries and 5.4 MB, including `research/` (393 files, among them derived statistics of the CC BY-NC 4.0 holography product), `history/` (116), `formal/` and `docs/`. | A GPL-3.0 sdist on PyPI redistributes CC BY-NC-derived numbers and frozen history; a licence ambiguity. | P | List the sdist's contents in `[tool.maturin] include`/`exclude` (crates, `python/`, `tests/`, README, LICENSE). | `pyproject.toml` |
| W4R-15 | Low | 5 | `python/rang/check.py:50-139` | The check never builds, lints or tests the `gpu` feature, so the X2 code is outside the gate; the 2 GPU tests skip in every check run. | A change to `core/src/gpu/` that breaks the build passes `rang-core check`. (Today `clippy --all-features -D warnings` and `cargo test --features gpu` pass; see the timings.) | C | Add the steps `core-clippy-gpu` (`--features gpu -D warnings`) and `core-test-gpu` (`--features gpu`). | `check.py`, `CONTRIBUTING.md` |
| W4R-16 | Low | 5 | `core_campaign_array.py:976-1000`; `core_wgridder.py:20-40,105-243` | Dead fallbacks. `correct_stokes_i`'s else branch names `core_fetch.CorrectInputs` and `core_fetch.p5_library`, which no longer exist, and `p5_extension()` never returns None. `core_wgridder.library()` checks the extension module for C symbols, so its ctypes and standalone path only runs with `RANG_DF1_LIB`. | Unreachable today; if reached, an `AttributeError` or a Cargo build. | C | Delete both fallbacks, with W4-3. | `core_campaign_array.py`, `core_wgridder.py`, `core_fetch.py` |
| W4R-17 | Low | 6 | AGENTS.md, README, CONTRIBUTING, docs/installation.md, `core/src/ffi.rs:1-5`, module docstrings | Statements the tree no longer matches; see "Documentation drift". | Readers and new sessions start from stale rules (the active experiment, supported hosts, "nothing runs Cargo"). | C | The edits listed under "Documentation drift", with the wave 4 documentation pass. | listed below |

\* Shared files that only the coordinator edits (`big-plan.md`, "Rules for
every session").

## Evidence per finding

**W4R-01, unrecorded settings that change results.**

- `Options::from_env` (`solve.rs:202`) runs at the start of every
  `solve::solve` (`solve.rs:1227`), inside the GIL-released call. It parses
  `qp_weights`, `stop`, `anderson` and `freeze`.
- `outputs/w4-review-20261031-02/r02_solve_env.py` solves one synthetic
  problem three times in fresh processes. The gains differ under
  `qp_weights=transposed` and under `anderson=3`.
- `core_cli._environment_record` records only `THREAD_VARIABLES`
  (`core_cli.py:83`). The output is `RANG_SOLVE_OPTIONS recorded ... even
  when set: False`.
- A grep of `core_campaign*.py`, `core_imaging.py` and `core_cli.py` finds
  `RANG_SOLVE_OPTIONS` only in `core_solver_study.py`, which sets it.
- The same holds for these variables:
  - `RANG_GRIDDER_DEVICE` and `RANG_GRIDDER_GPU_PRECISION`
    (`core_grid.py:46-47`). They switch an image to the GPU path, whose f32
    mode is tested only to 1e-4. Only the `gpu` key in the result says so,
    and only when the caller stores it.
  - `RANG_DF1_LIB` and `RANG_C1_LIB`, which swap in another binary. Their
    `library_path()` is hashed only by the campaigns that ask for it.
- The two `RANG_WGRIDDER_*` knobs were measured to have no effect (r04).
- A second-order point: the environment is read off the GIL, while
  `core_solver_study.solver_options` mutates `os.environ` (`putenv`). Two
  Python threads doing both at once race in libc. This is PLAUSIBLE only:
  no live chain does it. Passing options as an argument removes both
  problems.

**W4R-02, provenance outside a checkout.**

- `outputs/w4-review-20261031-02/r05_wheel.sh` installs the locally built
  wheel into a venv inside a scratch git repository, with cargo off `PATH`.
- `core_cli.ROOT` is `…/fakeproj/.venv/lib/python3.14`.
- `core_cli._commit()` returns the scratch repository's HEAD
  (`b6015c50…`, `dirty: False`). `core_campaign.git_status()` and
  `core_imaging` (line 374) use the same `ROOT`.
- `core_receipts.source_receipts()` raises `FileNotFoundError` on
  `…/lib/python3.14/Cargo.lock`. The trend run's receipts call it
  (`core_trend_run.py:202-210`).
- In a checkout, `source_receipts()` still globs
  `recipes/tv-flagging*.yaml` and `tools/flagging/`, which P8 moved to
  `history/`. The live receipt has silently shrunk, while
  `tests/test_core_receipts.py` tests a synthetic tree that still has those
  files.

**W4R-03, string-array keywords.**

- r03 writes a 2×3 int32 keyword and a 2×3 string keyword with
  `core_ms_write`. r03b writes the same pair with python-casacore 3.8.1 and
  reads both tables back with python-casacore.
- Numeric: both give `[[0,1,2],[3,4,5]]`.
- Strings, in storage order: python-casacore gives `a,b,c,d,e,f`; rang
  gives `a,d,b,e,c,f`.
- The cause is `arr.reshape(-1, order="F")` at `core_ms_write.py:492`. The
  string array columns (`put_string_cells`, line 376) already use C order.
- Only 1-D string keywords are tested (`test_t1_casacure_oracle.py:340`),
  which explains why the oracle tests pass. MS and caltable keywords rarely
  have 2-D string arrays, hence Medium.

**W4R-04, the extension's boundary.**

- `ptr()` returns `as_slice()?.as_ptr()`. rust-numpy's `as_slice` accepts
  C- *or* F-contiguous arrays.
- The C functions rebuild slices from the counts they are given
  (`ffi.rs:85-151`, `ffi_flag.rs:179-189`, `ffi_weights.rs:142-216`,
  `ffi_grid.rs:81-115`).
- `r01_ffi_bounds.py` shows both effects:
  - (a) `fused` with a 1-element `split_stats` view writes `big[1:12]`.
  - (b) `predict_components` returns a different second visibility for
    Fortran-ordered `uvw`, with status 0.
- `correct_stokes_i`, the wgridder bindings and P7's root-kernel bindings
  already check lengths. Those are the pattern to copy.
- `ffi_grid.rs:81-85` and `gpu/ffi.rs:45-49` multiply `nrow * 3` and
  `cells * 2` unchecked. The `correct_stokes_i` binding multiplies
  `ntime_bins * nfreq_bins * nant` unchecked (`lib.rs:487`).
- Wrapping is impossible at realistic sizes; the checked form costs
  nothing.

**W4R-05.** The wrapper builds `baseline_index` by
`zip(antenna1, antenna2)` (`core_flag.py:252-255`) and `time_inv` from
`times`, then passes `nrow` from `data.shape`. `corr_type` is never compared
with `ncorr`. The binding passes raw pointers (W4R-04).

**W4R-06, Cargo at a kernel call.**

- `core_closure.library()` always calls `build_standalone()` unless
  `RANG_C1_LIB` is set. `fluxstd.core_log10_poly` falls back to
  `rust_library()` because `rang._core` has no `fluxstd_eval`
  (`hasattr` → False).
- Both start with `core.core_root()`, which raises outside a checkout. From
  the wheel: `RuntimeError` for both (r05 `r05_wheel_kernels.log`).
- `nm -D` on the extension lists the C symbols `rang_core_closure_scores`,
  `rang_core_closure_last_error` and `rang_core_fluxstd_eval` (58 `rang_*`
  symbols in all). The kernels are already compiled in, and only the Python
  path is missing.
- The check run left `core/target/c1-standalone` and
  `core/target/fs1-standalone` behind. `test_core_closure` takes 6.8 s
  because it includes the build.
- Who says what:
  - `docs/installation.md:21-26` documents the limitation, but its own
    line 86 says "Python never runs Cargo itself".
  - `README.md:124-141` says the wheel "carries every kernel" and that
    "nothing runs Cargo … at a kernel call".
  - The module docstrings say "until `core/src/lib.rs` lists" the modules,
    which it now does.

**W4R-07 to W4R-08.** r05 printed `rang-core: unknown option --version`
(exit 1) and `has __version__: False`. The wheel's METADATA has a single
`Operating System :: POSIX :: Linux` classifier and a single `Project-URL`.
`twine check` passes for the wheel and the sdist. It does not resolve
relative links, so it cannot see that PyPI renders `docs/logo/lockup.svg`
and the relative links as broken.

**W4R-09.** The fetch path and the local path are listed here because both
feed every LUNO campaign:

- `core_zarr.read_rows` falls back to a whole-chunk decode when the block
  starts are not ascending (`core_zarr.py:87-103`).
- `core_fetch.block_table`, `plan_runs` and `read_rows_into` assume
  ascending starts (`ends = append(starts[1:], cbytes)`).
- When the starts are not ascending, the Rust span decoder fails with
  "block outside the span", so the failure is loud, not wrong data.

**W4R-10.** `decode_span_rows` (and the strided variant behind
`blosc_decode_span_rows_strided`) skips any row that ends before or starts
after the decoded blocks. The Python callers always pass covered rows, from
`_runs`. Under Rust 1.81 and later, a panic in a non-unwinding
`extern "C"` function aborts the process instead of being undefined
behaviour.

**W4R-11 to W4R-12.** These are X1's portability items 10 and 11. Two parts
of X1's inventory are partly or wholly undone in the live package:

- X1 counted 189 `read_text()` calls in the tree; 73 remain in
  `python/rang`.
- The `.gitattributes` it proposed was never added.

`core_campaign_array.mem_available_gib` reads `/proc/meminfo`, but the
value is only recorded (None elsewhere), so it is not a finding.

**W4R-13 to W4R-16.** Each is visible in the cited lines.

- The latest `wheels` run (`41146407352`, `17653e4`) is green on all five
  platforms and both Python versions.
- The `docs` deploy fails at `configure-pages` until Pages is enabled; that
  is a user item already.
- The derived-statistics licence point (W4R-14) comes from
  `research/b1-beam-pointing.md` ("CC BY-NC 4.0, derived statistics only
  committed").

## Release readiness (v0.1.0)

| Item | State | Edit needed |
| --- | --- | --- |
| Versions agree | pass | `pyproject.toml` 0.1.0; the three `Cargo.toml` are 0.1.0 with `publish = false`; `docs/conf.py` reads the installed metadata; the README names no version. |
| `rang-core --version`, `rang.__version__` | **fail** | W4R-07. |
| `[project.urls]` | partial | Repository is `gijzelaerr/rang-core`, which is correct. Add `Documentation = "https://gijzelaerr.github.io/rang-core/"` and `Issues = ".../issues"`. |
| Classifiers | **fail** | Add `Operating System :: Microsoft :: Windows`, `Operating System :: MacOS`, `Programming Language :: Python :: 3 :: Only`, `3.10`–`3.14`, `Programming Language :: Python :: Implementation :: CPython`. |
| Licence | pass | `License-Expression: GPL-3.0-or-later`; `LICENSE` is in `dist-info/licenses`; the Tricolour notice and its BSD licence ship in `rang/data/`. |
| README on PyPI | **fail** | W4R-08: absolute URLs for the logo and links (or `readme = "docs/pypi.md"`); fix the outdated "Linux x86_64 and aarch64" wheel sentence. |
| Wheel contents | pass | 95 entries: 88 tracked `python/rang` files, `_core.abi3.so`, 4 `dist-info` files, a licence and a CycloneDX SBOM. No `.pdb`, `__pycache__` or `history/`; the two static masks are present. 3.19 MB. |
| sdist contents | partial | W4R-14 (1,010 entries, 5.4 MB, includes `research/` and `history/`). |
| `twine check` | pass | wheel and sdist. |
| Extras | partial | `flagging` pins the frozen QuartiCal 0.2.7 / Stimela / python-casacore stack, which only `history/` uses. It still resolves on 3.14, but nothing live needs it, so drop it or document it as historical. `pointing` repeats `numpy`. |
| `wheels.yml` publish conditions | partial | Publishes only on `refs/tags/v*`, after `wheel`, `sdist` and `test`, with `id-token: write` and environment `pypi`. Missing: the tag-equals-version step (W4R-13). |
| CI state at `17653e4` | pass | `wheels` green on 5 platforms × 2 Pythons; `docs` build green, deploy fails until Pages is enabled (user item). |
| CHANGELOG / release notes | **fail** | Add `CHANGELOG.md` with a 0.1.0 entry and point `gh release create --notes-file` at it. |
| Kernels in the wheel | **fail** | W4R-06: closure and flux standards need a checkout and Cargo. |
| Receipts from a wheel install | **fail** | W4R-02. |
| Full check | pass | 730 s, `overall: PASS`. |

**Verdict: no-go as it stands. Go after W4-1, W4-3 and W4-5** (about a day
of work). W4-2 and W4-4 are recommended before the tag, but they do not
block it: their defects are not reachable through the documented chain, or
are rare. W4-6 to W4-8 can follow in 0.1.x.

## Simplification debt (ranked)

| Rank | Item | Lines | Proposed |
| ---: | --- | ---: | --- |
| 1 | Standalone Cargo builders and ctypes paths that duplicate the extension: `core_closure.py` loading section (lines 47–176), `fluxstd.py` standalone (398–472), `core_wgridder.py` ctypes and standalone fallback (about 20–40, 105–243) | ≈ 370 | W4-3: bind both kernels in the extension, then delete. |
| 2 | Dead P5 ctypes branch in `core_campaign_array.correct_stokes_i` and the `p5_extension` indirection | ≈ 30 | W4-3. |
| 3 | Duplicate helpers across the extracts: `_json_default` (6 copies), `decode_extra` (3), `verify_inputs` (2), `cpu_seconds` (3 wrappers of `rusage`), blosc block-table logic (`core_zarr.read_rows` vs `core_fetch.block_table`/`plan_runs`/`read_rows_into`), fixture extraction (`notebook/data.py` vs `notebook/science.py`) | ≈ 250 | Merge only the live (non-verbatim) ones; P11's verbatim extracts stay as they are by rule. The block-table merge goes with W4R-09. |
| 4 | ctypes-era names kept for receipts: `core.library()`, `backend_name()`, `BACKENDS`, `RANG_CORE_LIB`/`RANG_TOY_LIB` in `environment()`, `projector._native_library` shim, `ffi.rs` header "C ABI for the Python layer (ctypes)" | ≈ 80 | Keep the receipt keys and fix the comments; delete the shim once no frozen extract calls it. |
| 5 | Oversized frozen drivers (radon rank F): `pointing.solve_pointing` (533 lines, CC 92), `core_campaign_1830.run`/`check` (413/228, CC 54/79), `core_campaign_array.run`/`check` (399/171), `core_campaign.run`/`check` (243/198), `core_prospective.run` (209), `blocked.prepare_blocked_design` (179) | ≈ 2,800 | Leave as they are: the archives pin them. A refactor needs an archive replay per driver. |
| 6 | `core_receipts.source_receipts` globs paths that moved to `history/`; its test exercises a synthetic tree with those paths | ≈ 15 | W4-1. |
| 7 | `flagging` extra (frozen stack) | 1 | W4-5. |
| 8 | vulture at 80 % confidence finds only `ack` (`core_ms_write.py:665`, a python-casacore signature argument). At 60 %: 152 unused names, mostly the public API of the frozen extracts and notebook helpers | – | No action. |

No module in `python/rang` is orphaned. Every module is imported by the
package, the tests, the examples, the notebooks, the recipes or the docs
(`outputs/w4-review-20261031-01/importers.tsv`). The three `Cargo.lock`
files (root, `core`, `core/py`) agree on every common crate; the one
mismatch in a name-keyed comparison, `rustc-hash`, is a crate locked at
two versions.

## Documentation drift

| File | Statement | True now |
| --- | --- | --- |
| `AGENTS.md:6-7` | "The active experiment is MeerKAT L-band gain-TV-guided flagging" | L4 closed flagging as null (`flagging-verdict.md`); B1, beam and pointing on real data, is active. AGENTS.md also has no layout section, which the wave 4 doc pass asks for. |
| `README.md:33-52,157-161` | The "active real-data flagging experiment" and "Next research decision: for the active flagging objective…" | Flagging is closed as null; the next decision is B1-3. |
| `README.md:124-130` | Wheels for "Linux x86_64 and aarch64" only; "The Tricolour static masks … still read files from the checkout" | 5 platforms (`wheels.yml`); the masks are package data since P7 (`core_flag.static_mask_files`). |
| `README.md:136-141`, `docs/installation.md:18-19,86` | "nothing runs Cargo at import or at a kernel call"; "Python never runs Cargo itself" | False for `core_closure` and `fluxstd` (W4R-06). `docs/installation.md:21-26` lists `core_wgridder` among them, but it is in the extension since DF2b. |
| `docs/installation.md:30-38` | "the macOS jobs are written … but were not run"; macOS arm64 runner `macos-14` | They run green (`41146407352`); the runner is `macos-15`. |
| `CONTRIBUTING.md:45-55` | "Supported hosts are Linux and macOS. Native Windows runs the test suite since task P7 (622 passed, 43 skipped …)" | X1 and X2 made Windows a native build and CI target; the counts are from P7. |
| `CONTRIBUTING.md:10` | Install with `'.[pointing,beam,test]'` | The full check's optional tests also use `imaging`, `formats`, `casacure`, `docs` and `notebook`; otherwise more tests skip than the 10 seen here. |
| `core/py/src/lib.rs:10-11` | "non-contiguous arrays and read-only outputs are refused" | F-contiguous arrays are accepted and read in memory order (W4R-04). |
| `core/src/ffi.rs:1-5` | "C ABI for the Python layer (ctypes) … rather than PyO3" | The Python layer is PyO3 since P7; the C ABI remains for C consumers and benches. |
| `core_closure.py:20-23`, `fluxstd.py:396-398` | "Until `core/src/lib.rs` lists `closure` / `fluxstd`" | `lib.rs` lists both; the extension exports their symbols. |
| `research/README.md` | the index | Eight notes cannot be reached from it by links: `common-pointing-priors`, `flagging-signal-guard`, `frequency-blocking`, `pointing-history`, `relative-pointing`, `robustness-stress`, `sharing-draft`, `uncertainty-coverage` (some are linked from the top README). `tool-timings.md` is not indexed. No relative link is broken in README, CONTRIBUTING, AGENTS, the index, STATE or the docs index. |
| `research/STATE.md` | 2,564 lines, newest first | The wave 4 doc pass is to trim it to current truth with history linked; not done yet. |

## Timings (every tool run of this task)

| Run | Wall | Notes |
| --- | ---: | --- |
| `uv venv` + editable install with every extra in the brief (extension build) | 190 s | WSL, load 5–7 |
| static tools install (vulture, radon, pyright, bandit, pip-audit) | 4 s | |
| `bash tools/check-all.sh` at `17653e4` | 730 s | `overall: PASS`; pytest 784 passed, 10 skipped in 383.1 s; no lock wait |
| determinism matrix r04, 8 processes | 6 s | all identical |
| reproductions r01 / r02 / r03 / r03b | 0.18 s / 0.92 s / 0.25 s / about 1 s | |
| `tools/wheel/build.py --sdist` | 181 s | maturin 180.2 s, sdist 0.8 s |
| wheel probe r05 (scratch venv, install, probe) | about 3 s | |
| `twine check` (uv tool, twine 7.0.0) | 5 s | both pass |
| vulture 2.16, two passes | 2.7 s | |
| radon 6.0.1 cc | 2.6 s | |
| ruff 0.17.3 `PLW1514` (preview) | 0.04 s | 20 hits (the rule only sees `Path(...)` calls) |
| bandit 1.9.4 | 4 s | 5 × B310 (urlopen on fixed https URLs), no finding |
| pip-audit 2.10.1 | 31 s | no known vulnerabilities |
| python-casacore 3.8.1 scratch venv | under 1 s | uv cache |
| `uv pip compile quartical==0.2.7` for 3.14 and 3.12 | 3 s | resolves on both |
| `cargo clippy --all-targets --all-features -D warnings` (core, `gpu`) | 37.5 s | pass |
| `cargo clippy -W clippy::pedantic` core / ext / root | 7.3 s / 48.1 s / 1.5 s | 4,804 pedantic warnings in core, mostly literal separators, doc backticks and casts; the `usize→u32` casts are casacore format fields |
| `cargo doc --no-deps --all-features` (core) | 4.5 s | no warnings |
| `cargo test --release --features gpu` (core) | 327.3 s | 135 passed (129 without the feature); whether its GPU tests found an adapter was not checked |
| SEE_AUDIT_ROW |

Slowest tests (from the JUnit XML of the check run,
`outputs/w4-review-20261031-01/pytest-junit.xml`):

| s | Test |
| ---: | --- |
| 51.2 | `test_pointing::test_correlated_flux_constraints_do_not_create_data_information` |
| 28.1 | `test_d1_docs::test_site_builds_without_warnings` |
| 25.9 | `test_d3_notebooks::test_notebook_06_executes_with_switches_off` |
| 22.9 | `test_pointing::test_flux_anchor_geometry_controls_number_of_common_modes` |
| 18.9 | `test_blocked::test_blocked_matches_dense_and_numpy[False]` |
| 17.9 | `test_notebook_execute::test_notebook_runs_on_the_fixture[01-data-and-rank.ipynb]` |
| 16.6 | `test_beams::test_chromatic_shape_lifts_the_gaussian_gauge` |
| 16.4 | `test_pc1_preconditions::test_l1_precondition_replays_k` |
| 13.7 | `test_pointing::test_full_coverage_retains_modes_with_gains_and_differential_pointing` |
| 12.7 | `test_pc1_preconditions::test_l2_precondition_replays_k` |
| 9.4 | `test_pointing::test_nonquadratic_rotating_beam_breaks_local_gauge` |
| 7.2 | `test_p5_memory::test_decode_inputs_is_byte_identical_on_four_stations` |
| 6.8 | `test_core_closure::test_kernel_matches_numpy_reference[trace]` (includes the Cargo build, W4R-06) |
| 5.2 | `test_beams::test_beam_shape_derivatives_and_joint_recovery` |
| 5.1 | `test_toy::test_reproducibility_and_seed_changes` |
| 5.0 | `test_beams::test_joint_relative_antenna_width_and_common_pointing_recovery` |
| 4.7 | `test_beams::test_joint_width_recovery_and_derivative` |
| 4.5 | `test_pointing_example::test_pointing_example_exports_results` |
| 4.3 | `test_core_ms_write::test_the_lock_keeps_a_second_process_out` |
| 4.0 | `test_pointing::test_joint_smooth_gains_flux_and_relative_pointing[polynomial-True]` |
| 3.9 | `test_pointing::test_joint_smooth_gains_flux_and_relative_pointing[per_channel-True]` |
| 3.7 | `test_beams::test_common_and_relative_pointing_decomposition` |
| 3.3 | `test_d1_docs::test_cli_page_matches_help` |
| 3.0 | `test_p11_extract::test_no_live_file_imports_a_frozen_module` |
| 2.7 | `test_beams::test_custom_predictor_derivatives_and_solver` |

The 10 skips:

- `ducc0` absent
- the `[meerkat]` extra, 4 tests, plus `mvftoms`
- CARTA live (the switch is off)
- the task K fetch, an ignored input
- the GPU gridder not compiled, 2 tests

Ignored outputs:

- `outputs/w4-review-20261031-check-all.log`
- `outputs/w4-review-20261031-01/`: JUnit XML, vulture, radon, bandit,
  importers, `ruff-PLW1514`
- `outputs/w4-review-20261031-02/`: r01–r03b and r05, with logs and the
  tables they wrote
- `outputs/w4-review-20261031-03/`: r04 and its log
- `outputs/w4-review-20261031-04/`: wheel, sdist, listing, timings,
  build log
- `outputs/w4-review-20261031-05/`: Rust static passes

## For the coordinator

### Proposed fix tasks

W4-1, W4-2, W4-3 and W4-4 can change a recorded number or a written file,
so each is verified against the archives. W4-5 to W4-8 are grouped small
fixes.

**W4-1, receipts record what changed the result (provenance).**
Owners: `core_cli.py`*, `core.py`*, `core/src/solve.rs`, `core/src/ffi.rs`*,
`core/py/src/lib.rs`*, `core_campaign*.py`, `core_imaging.py`,
`core_receipts.py`, `core_solver_study.py`, `tests/test_core_cli.py`,
`tests/test_l5_solver.py`.

1. One registry of result-affecting variables in `core.py`:
   `RANG_SOLVE_OPTIONS`, `RANG_SOLVE_TRACE`, `RANG_GRIDDER_DEVICE`,
   `RANG_GRIDDER_GPU_PRECISION`, `RANG_DF1_LIB`, `RANG_C1_LIB`,
   `RANG_WGRIDDER_*`, `RANG_STRATEGY_DIR`.
2. Record the registry in `_environment_record` and in every campaign's
   `environment`/receipt.
3. Solver options: an explicit `options=` argument through
   `solve_complex` → `SolveInputs`, with the environment read only by the
   Python wrapper and recorded.
4. Checkout detection: `ROOT` is accepted only if it holds the three
   manifests. Otherwise `commit: null`, and the distribution version plus
   the extension SHA256 are recorded instead.
5. `source_receipts` hashes the installed package.

Acceptance:

- r02 shows the variable in the receipt.
- r05 records `commit: null` and `source_receipts` runs.
- The P9 identity suite and every campaign comparator (K, L1, L2, L1-M, C1,
  L5) pass unchanged with the variables unset.
- Default solves are bit-identical (`tests/test_p1_solver.py`,
  `test_core_backends.py`).

**W4-2, boundary checks at the extension and in the wrappers.**
Owners: `core/py/src/lib.rs`*, `core/src/ffi_grid.rs`,
`core/src/gpu/ffi.rs`, `core/src/blosc.rs`, `core/src/ffi_correct.rs`,
`core/src/ffi_fluxstd.rs`, `core_flag.py`, `core_zarr.py`, `core_fetch.py`,
`tests/test_p7_architecture.py`, `tests/test_core_flag.py`,
`tests/test_core_zarr.py`, `tests/test_core_fetch.py`.

1. `sized`/`sized_mut` and a C-contiguity check on every binding;
   `checked_mul` on the size products.
2. The length checks in `flag_rows`.
3. The coverage check in `decode_span_rows`.
4. `catch_unwind` on `fluxstd_eval`.
5. Zarr `order`/dtype assertions, and the out-of-order block fallback in
   `core_fetch` (W4R-04, -05, -09, -10).

Acceptance:

- r01 raises `ValueError` for both cases.
- A mismatched `flag_rows` raises.
- The backends comparator (`rang-core backends compare`) and the C, D, I, K
  and P5 comparators are bit-identical.
- `test_p5_memory` decode identity passes.

**W4-3, the last two kernels into the extension; dead fallbacks out.**
Owners: `core/py/src/lib.rs`*, `core_closure.py`, `fluxstd.py`,
`core_wgridder.py`, `core_campaign_array.py`, `core_fetch.py`,
`tests/test_core_closure.py`, `tests/test_fluxstd.py`,
`tests/test_df2b_wgrid.py`, `docs/installation.md`.

1. PyO3 `closure_scores` and `fluxstd_eval`, with sized buffers and the GIL
   released.
2. The wrappers call them.
3. Delete the standalone builders, the ctypes fallbacks and the dead P5
   branch (W4R-06, W4R-16; about 400 lines).

Acceptance:

- A clean pytest run leaves no `core/target/*-standalone`.
- r05 runs both kernels from the wheel with cargo off `PATH`.
- The C1 comparator and the FS1 setjy checks are bit-identical to their
  archives.
- `tools/wheel/test.py` adds a closure and a fluxstd smoke call.

**W4-4, the string-array keyword order.**
Owners: `core_ms_write.py`, and `tests/test_t1_casacure_oracle.py` or
`tests/test_e5_table_writer_rest.py`.

Write C order (W4R-03). Add a 2-D string keyword, and a 2-D string column
cell for completeness, to the python-casacore and casacure oracle checks.

Acceptance:

- r03b gives the same storage order for both writers.
- The E3, E4 and E5 byte-identity checks still pass.

**W4-5, release metadata (blocking for v0.1.0, grouped).**
Owners: `pyproject.toml`, `python/rang/__init__.py`, `core_cli.py`*,
`README.md`*, `CONTRIBUTING.md`, `docs/installation.md`,
`.github/workflows/wheels.yml`, `CHANGELOG.md`.

1. `--version` and `__version__`.
2. Classifiers, Documentation and Issues URLs.
3. A PyPI-safe README: absolute logo and link URLs, the 5-platform
   sentence, the masks are package data.
4. `CHANGELOG.md` with 0.1.0, and `--notes-file` in the release job.
5. The tag-equals-version step in `release` and `publish`.
6. Actions at Node 24 versions.
7. An sdist include/exclude list without `research/` or `history/`.
8. Drop or annotate the `flagging` extra.

Acceptance:

- `rang-core --version` prints `0.1.0`.
- `twine check` passes, and a rendered preview (`python -m readme_renderer
  README.md`) has no relative URL.
- A `workflow_dispatch` run on a branch is green.
- The sdist lists only the source needed to build and test.

**W4-6, portability hygiene (grouped).**
Owners: `formats/*.py`, `core_ms_write.py`, `core_campaign*.py`,
`core_imaging.py`, `core_state.py`, `core_solver_study.py`, `notebook/*.py`,
`.gitattributes`, `.github/workflows/wheels.yml`, `tests/` (a lint test).

1. `encoding="utf-8"` on every text read and write in `python/rang`, plus
   `newline="\n"` where the output is hashed or committed.
2. A test that greps `python/rang` for `read_text()` and for `write_text(`
   or `open(` in text mode with no `encoding` (ruff `PLW1514` misses
   `path.read_text()`).
3. `.gitattributes` with `* text=auto eol=lf`, and `*.staticmask`, `*.png`,
   `*.npz` as binary; renormalise the 13 CRLF files.
4. One Windows test job without `PYTHONUTF8`.

Acceptance:

- The Windows CI job is green without `PYTHONUTF8`.
- `git ls-files --eol` shows no `i/crlf`.
- The receipts that hash code are unchanged on Linux (none of the 13 files
  is in a `CODE_FILES` list; check this).

**W4-7, the GPU feature in the gate.**
Owners: `check.py`, `CONTRIBUTING.md`, `tests/test_core_cli.py`.

Add the steps `core-clippy-gpu` and `core-test-gpu` (W4R-15).

Acceptance: `rang-core check` runs and passes them on Linux and Windows.

**W4-8, documentation drift (with the wave 4 documentation pass).**
Owners: `AGENTS.md`*, `README.md`*, `CONTRIBUTING.md`,
`docs/installation.md`, `core/py/src/lib.rs`* (docstring only),
`core/src/ffi.rs`* (header only), `core_closure.py` and `fluxstd.py`
docstrings (after W4-3), `research/README.md`*.

Make every edit in the "Documentation drift" table.

Acceptance: a fresh reader's checklist. The link check finds no
unreachable note, or each one is listed as history.

\* Shared files that only the coordinator edits.

### STATE paragraph

W4 final review (big plan wave 4), 2026-10-31 (reviewed; measured;
[w4-review.md](w4-review.md)). It is a read-only `/code-review` of `main` at
`17653e4`:

- **Checks.** `bash tools/check-all.sh` passes (784 passed, 10 skipped,
  730 s). The live kernels are bit-identical at 1–4 rayon threads and under
  the gridder's SIMD and plane-group settings. Every archive comparator
  passes.
- **Findings.** 17: 1 high, 8 medium, 8 low.
- **High.** `RANG_SOLVE_OPTIONS` changes the solver's gains, and no receipt
  records it.
- **Medium.**
  - Wheel installs record the commit of any enclosing git repository.
  - The extension takes array sizes on trust and reads Fortran-ordered
    arrays transposed; an out-of-bounds write was reproduced.
  - `flag_rows` does not check its input lengths.
  - The closure and flux-standard kernels still build with Cargo, so they
    fail from the wheel.
  - 2-D string-array keywords are stored in an element order different from
    python-casacore 3.8.1.
  - There is no `--version`.
  - The classifiers list Linux only, and the README breaks on PyPI.
  - Text I/O depends on the Windows locale.
- **Release.** v0.1.0 is no-go as it stands; it is go after W4-1
  (receipts), W4-3 (kernels into the extension) and W4-5 (release
  metadata).
- **Fix tasks.** W4-1 to W4-8.
- **Outputs.** `outputs/w4-review-20261031-0{1..5}`.

### `research/README.md` index entry

New, 2026-10-31: W4, the [final review](w4-review.md): no archived result
is affected, and the kernels are bit-identical across thread counts. There
are 17 findings: 1 high, the solver options missing from receipts; 8
medium; 8 low. v0.1.0 is go after W4-1, W4-3 and W4-5.

### `research/tool-timings.md` rows

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-31 | big plan W4: `uv venv` + editable install, all extras | worktree | 190 s | – | extension built by maturin |
| 2026-10-31 | big plan W4: `bash tools/check-all.sh` | `17653e4` | 730 s | – | `overall: PASS`; pytest 784 passed, 10 skipped in 383.1 s (load 5–7) |
| 2026-10-31 | big plan W4: determinism matrix (8 processes) | synthetic P1/P2/DF2b/P3 cases | 6 s | – | every hash identical |
| 2026-10-31 | big plan W4: `tools/wheel/build.py --sdist` | `17653e4` | 181 s | – | maturin 180.2 s; wheel 3.19 MB, 95 entries |
| 2026-10-31 | big plan W4: `twine check` | wheel + sdist | 5 s | – | pass |
| 2026-10-31 | big plan W4: pip-audit 2.10.1 | worktree venv | 31 s | – | no known vulnerabilities |
| 2026-10-31 | big plan W4: bandit / vulture / radon | `python/rang` | 4 s / 2.7 s / 2.6 s | – | no security finding; one unused argument |
| 2026-10-31 | big plan W4: clippy `--all-features -D warnings` (core, `gpu`) | worktree | 37.5 s | – | pass |
| 2026-10-31 | big plan W4: clippy pedantic core / ext / root | worktree | 7.3 s / 48.1 s / 1.5 s | – | 4,804 pedantic warnings in core, none promoted |
| 2026-10-31 | big plan W4: `cargo doc --no-deps --all-features` | core | 4.5 s | – | no warnings |
| 2026-10-31 | big plan W4: `cargo test --release --features gpu` | core | 327.3 s | – | 135 passed (6 more than the check runs) |
| SEE_AUDIT_TT |
