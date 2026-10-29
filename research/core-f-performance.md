# Rang core, wave 1 task F: performance with unchanged results

Protocol frozen 2026-10-29 in the commit that adds this file, before any
benchmark or kernel change. Status: **proposed**. Task F of
[core-parallel-plan.md](core-parallel-plan.md): make three parts of the core
faster without changing a result. Under AGENTS.md this is engineering, not a
scientific contribution; the gate is that the phase 2 and section 6 archives
are reproduced, not improved.

## Targets, and where each kernel lives

1. **Solver inner loop.** Rust, `core/src/solve.rs` (`solve`, `accumulate`,
   `conjugate_gradient`), called through `rang_core_solve_complex` and
   `rangtoy.core.solve_complex`. The whole kernel is in the file this task
   may change.
2. **Blosc decode.** Rust, `core/src/blosc.rs` (`lz4_decompress`,
   `unshuffle`, `decode_block_bytes`, `decode_span_rows`), called through
   `rangtoy.core.blosc_decode` (whole chunks) and `rangtoy.core_zarr.read_rows`
   (block-selective rows). The whole kernel is in the file this task may
   change. Reference implementation: c-blosc through `numcodecs` from public
   PyPI, installed into this worktree's venv (numcodecs 0.17.1, c-blosc
   1.21.7.dev; the section 6 oracle used 1.21.6 in the container).
3. **Rank survey.** Not in `core/`. It is three kernels and a Python loop:
   the TRAIN normal equations in the root crate (`src/response.rs`,
   `rang_response_normals`, through `rangtoy.flagging_influence.training_normals`),
   one batched `numpy.linalg.eigvalsh` (LAPACK), and the per-bin anchored
   response status in the root crate (`rang_response_step`, through
   `anchored_response`), driven by a per-bin Python loop in
   `examples/prototype_section6.py` (`section6_pass`) and, in the same form,
   `examples/validate_core_phase2.py` (`rank_survey`). None of those files
   may be changed by this task, so for target 3 the deliverable is a
   measured breakdown and, if a restructuring helps, a measured candidate in
   new benchmark code that produces the identical survey, offered to the
   coordinator under "For the coordinator"; the prototype itself is not
   edited here.

## Rules this task follows

- Changes to existing code are confined to the bodies of `core/src/solve.rs`
  and `core/src/blosc.rs`. Public functions, signatures, error values and
  results stay as they are. `core/src/lib.rs`, `core/src/ffi.rs`,
  `core/Cargo.toml` and `python/rangtoy/core.py` are not touched, so the
  release profile is Cargo's default and no dependency is added.
- New files only otherwise: `examples/bench_core_f.py` (benchmark and
  equality harness), new Rust unit tests inside the two modules, new pytest
  tests in `tests/test_core_f.py` if needed, this file, and fresh
  `outputs/core-f-20261029-NN` directories (ignored).
- Toolchain: `cargo +1.93 build --offline --release` for every measured
  library, with `RANG_CORE_LIB` pointing at that library so Python never
  rebuilds with another toolchain. Profiling builds set
  `CARGO_PROFILE_RELEASE_DEBUG=1` in the environment only, in a separate
  target directory, and are never the measured library.

## Inputs and oracles (frozen)

- **Solver.** LUNO: `outputs/core-phase2-inputs-20261029-01/arrays.npz`
  (SHA256 `8b221f7b…`, as in the phase 2 archive), grid (2, 32), 50
  iterations; QuartiCal's `outputs/luno-solve-20261029-02/solve/gains.npy`
  and `gain_flags.npy`. Fixture: `outputs/tv-response-wsl-20261029-01/clean`
  (`state.npz`, `backups/clean-t2-f32-solve.npz`,
  `trials/clean-t2-f32/diagnostics.npz`) as `validate_core_phase2.py` loads
  them. Archive: [core-phase2.json](results/core-phase2.json).
- **Blosc.** The 68 chunks of the section 6 ingest oracle,
  `outputs/core-section6-oracle-20261029-01/receipt.json` (decoded SHA256 per
  chunk; container paths `/workspace/outputs/…` map to `outputs/…`), and the
  prototype's row selection (stations 0–3, cross rows with FLAG_ROW false,
  tiles 8–23) as `examples/prototype_section6.py` computes it. Archive:
  [core-section6.json](results/core-section6.json).
- **Survey.** The LUNO arrays above, the gains and flags of the solver run,
  and the archived counts 389 / 43 / 592 with status keys
  `fully_identified status0` and `underidentified status3`.

## Equality criteria (frozen)

Every criterion is checked by `examples/bench_core_f.py` against a baseline
snapshot it writes once from the unchanged code (commit `9e12326`'s kernels)
into `outputs/core-f-20261029-01/baseline.json`, before any kernel change.

1. **Solver.** On LUNO and the fixture, the new library's gains (complex128
   bytes), gain flags, iteration count and converged fraction are
   bit-identical to the baseline snapshot (SHA256 of the arrays). The
   archived comparison with QuartiCal is re-run and must still give flags
   identical, gain entries ≤ 1e-6 (reported to full precision; baseline
   3.3e-16 LUNO, 1.4e-15 fixture), iterations 50 and fraction
   0.9833234067897558 to 1e-12 on LUNO. If an optimisation needs a different
   floating-point order, the bit-identity criterion may be relaxed to the
   archived tolerances only if this file says so before the change is made,
   with the reason.
2. **Blosc.** Every one of the 68 chunks decodes in full to the oracle's
   SHA256. The block-selective path (`core_zarr.read_rows` on the prototype's
   rows, every tile column) produces bytes whose SHA256 equals the baseline
   snapshot. The Rust unit tests in `blosc.rs` keep passing, and new tests
   cover any new code path (short blocks, overlapping matches near the
   output end, odd typesizes).
3. **Survey.** The survey dictionary equals the baseline (which must equal
   the archived counts), and the per-bin label and native status vectors
   equal the baseline exactly. Candidates computed in new code are compared
   the same way.

## Timing method (frozen)

- All timings are wall seconds from `time.perf_counter` around the ctypes
  call (solver, blosc) or the survey block, single process, no threads.
  Each measurement is repeated: solver 7 runs, blosc 5 runs over the whole
  chunk set, survey 7 runs; the minimum and median are reported. The
  1-minute load average from `/proc/loadavg` is recorded before and after
  each series, because seven sibling sessions share the 16 cores. A
  speed-up is claimed only if the new minimum is below the baseline minimum
  by more than the baseline's median-minus-minimum spread.
- Solver: LUNO 50 iterations (archive 0.62–0.77 s), fixture (archive
  0.49 s).
- Blosc: (a) whole-chunk decode of the 16 DATA tiles (the largest, 205 MB
  each decoded) by the Rust decoder against `numcodecs.blosc.decompress`
  with `numcodecs.blosc.set_nthreads(1)`, and also at numcodecs' default
  thread count, reported separately; (b) the block-selective ingest as the
  prototype runs it (2048 of 12544 blocks, archive 1.29 s decode). Bytes
  decoded per second are reported alongside.
- Survey: the `rank_survey` block of the prototype (archive 0.73 s), split
  into normals, eigenvalues, the per-bin loop and its `anchored_response`
  calls.
- Profiling before optimising: `perf record` on the benchmark with a debug
  release build; the top symbols are recorded here per target as the
  baseline profile. The baseline timings are frozen in this file before any
  kernel change and are not re-measured afterwards except to report the
  load at the time.
- Every tool run is timed and logged in the measurement log below.

## What counts as done

Each target ends in one of: a measured speed-up with criteria 1–3 passing
as frozen; or a documented null result (the profile, what was tried, the
numbers). Failures of a criterion are recorded with their numbers; any step
taken after a failure is labelled post-hoc.

## Baseline (frozen, measured 2026-10-29 before any kernel change)

Run `outputs/core-f-20261029-01/baseline.json` by
`examples/bench_core_f.py baseline`, on the unchanged kernels of `9e12326`
(protocol commit `48cad0f`), library built with `cargo +1.93`
(SHA256 `19abe21c…`), Python 3.14.4, numpy 2.5.4, numcodecs 0.17.1 with
c-blosc 1.21.7.dev. Load average 0.8–0.9 throughout (the sibling sessions
were mostly idle at the time); every series has a median within 3% of its
minimum. Note for every later comparison: numpy's OpenBLAS keeps eight
spinning threads alive during the whole benchmark (17–18% of all perf
samples, on other cores); they do not run on the measured thread but do
occupy cores the siblings share.

| Target | Measurement | Minimum | Median |
| --- | --- | ---: | ---: |
| Solver | LUNO, 50 iterations (archive 0.62–0.77 s) | 0.6125 s | 0.6224 s |
| Solver | fixture clean case (archive 0.49 s) | 0.3984 s | 0.3991 s |
| Blosc | 16 DATA tiles decoded in full, 3.28 GB, Rust | 1.917 s (1.71 GB/s) | 1.943 s |
| Blosc | same, c-blosc through numcodecs, 1 thread | 0.513 s (6.39 GB/s) | 0.516 s |
| Blosc | same, c-blosc, default 8 threads | 0.223 s | 0.226 s |
| Blosc | block-selective ingest, 2048 blocks, 752 MB read, decode only (archive 1.29 s) | 0.725 s | 0.729 s |
| Blosc | same, wall including file reads | 0.831 s | 0.849 s |
| Survey | whole block (archive 0.73 s) | 0.739 s | 0.748 s |
| Survey | of which `training_normals` (root crate) | 0.132 s | 0.133 s |
| Survey | of which batched `eigvalsh` | 0.009 s | 0.009 s |
| Survey | of which per-bin loop | 0.584 s | 0.587 s |
| Survey | of which the 432 `anchored_response` calls inside the loop | 0.511 s | 0.513 s |

Equality at baseline: solver flags identical to QuartiCal, gain entries
3.34e-16 (LUNO) and 1.41e-15 (fixture), products 5.6e-16 and 2.8e-16,
50 iterations, fraction 0.9833234067897558 (LUNO), as archived. All 68
chunks equal the ingest oracle's SHA256; numcodecs and the Rust decoder
produce identical bytes on every DATA tile. Survey 389 / 43 / 592 with the
archived status keys. The snapshot hashes (gains, flags, selected rows,
per-bin labels and statuses) are in `baseline.json`.

**Baseline profile** (`perf record -F 2000`, release build with
`CARGO_PROFILE_RELEASE_DEBUG=1` in `~/Build/tmp/20261029-rang-core-f`,
samples bucketed by symbol address range; OpenBLAS spin threads excluded):

- Solver: `solve::accumulate` 78% (the 4×4 `J^H W J` update, computed on a
  Kronecker product with the identity, so three quarters of its complex
  multiplications are by zero or one, plus a conjugate copy of the lower
  triangle on every call), the rest of the row loop and conjugate gradients
  17%.
- Blosc: `decode_block_bytes` with the inlined byte-wise `unshuffle` 57%,
  libc `memcpy`/`memmove` from the short LZ4 literal and match copies 22%,
  the rest of `lz4_decompress` 20%.
- Survey (one solve plus three survey passes): the root crate's Jacobi
  eigen solver `rang_toy::linalg::eigen` 33% of all samples (two 32×32
  decompositions per bin inside `rang_response_step`, 1.2 ms per call),
  `response::normals` 8%, NumPy and Python 11%; the solve at the start of
  the run accounts for the `solve::` samples.

## Measurement log

| When | What | Wall | Note |
| --- | --- | --- | --- |
| 2026-10-29 | `uv venv` + `uv pip install -e .[pointing,beam,test] ruff numcodecs` (public PyPI) | 20.7 s | numpy 2.5.4 (archive 2.5.3), numcodecs 0.17.1 |
| 2026-10-29 | `cargo +1.93 build --release` of `core/` (warm cache) | 1.9 s | `CARGO_BUILD_JOBS=4` |
| 2026-10-29 | venv recreated on `/usr/bin/python3.14` (`uv venv -p`, same packages) | 1.4 s | uv cache warm; first venv had picked uv's 3.13 |
| 2026-10-29 | `examples/bench_core_f.py baseline outputs/core-f-20261029-01` | 48.0 s | solve 7.3 s, blosc 34.7 s, survey 5.9 s; load 0.8–0.9 |
| 2026-10-29 | perf record of solve (5 solves), blosc (16 tiles × 2), survey (3 passes) | 3.6 s, 5.5 s, 3.3 s | debug-symbol builds in `~/Build/tmp/20261029-rang-core-f` |
