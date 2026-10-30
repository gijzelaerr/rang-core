# Rang core, big plan task P1: solver and fused pass over solution intervals

Protocol frozen 2026-10-30 in the commit that adds this file, before any
kernel change. Status: **proposed** (protocol only; baseline below).
Task P1 of [simplification-review.md](simplification-review.md) section 3
("P1 Solver") and section 4. Under AGENTS.md this is engineering, not a
scientific contribution: the gate is that the phase 2 solver archive is
reproduced bit for bit and the phase 1 fused pass within its frozen
tolerance, at every thread count.

## What changes

1. **Solver** (`core/src/solve.rs`). The outer Gauss–Newton iteration loop
   stays serial and global: the stop test uses the converged fraction over
   all gains and the `km1_gain` copy depends on it. Inside each iteration,
   one rayon fork–join runs over solution intervals (time bin × frequency
   bin; each interval owns `nant` contiguous gains): accumulate `J^H W J`
   and `J^H W r`, `fill_lower`, conjugate gradients, `finalize_update` and
   `update_gain_flags`, each task returning integer converged and flagged
   counts. An interval walks its time bin's rows in ascending order and,
   within a row, its frequency bin's channels in ascending order, pq before
   qp, which is exactly each gain's serial summation order. No float is
   reduced across tasks, so results cannot depend on the thread count.
   Conversions that do not depend on the gains (f32 → f64 of data, model and
   weights; the cell flag test) move out of the iteration loop only where a
   measurement shows a gain and the memory cost stays bounded (phase 2
   criterion 8: ≤ 200 MB for the LUNO process). The `#[inline(always)]`
   copies of `jones::mul`/`adjoint`/`from_f32` are dropped if, with thin LTO
   and one codegen unit (P0), the instruction count does not rise.
2. **Fused pass** (`core/src/fused.rs`). When rows are sorted by time bin,
   per-cell work runs in parallel over time-bin row groups; normals are
   written per interval (disjoint gains, same summation order); per-baseline
   amplitudes are concatenated in group order, so the robust scores see the
   serial order; split sums are formed by one serial fold of the per-cell
   values in cell order. The design target is therefore bit identity, not
   only the phase 1 tolerance. Unsorted rows take the unchanged serial path.
3. Thread count: rayon's global pool, `RAYON_NUM_THREADS` (default: all
   logical CPUs). No C ABI or extension signature changes.

## Inputs (frozen, read-only)

- LUNO four-station slice: `outputs/core-phase2-inputs-20261029-01/arrays.npz`
  (192 rows × 2,048 channels, 16 time bins × 64 frequency bins, 4 antennas;
  the K chain's `original` arm solves the same grid on the same rows).
  QuartiCal's `outputs/luno-solve-20261029-02/solve/` gains and flags.
- Fixture clean case: `outputs/tv-response-wsl-20261029-01/clean`
  (140 rows × 4,096 channels; FLAG from `backups/clean-t2-f32-solve.npz`).
- Task F's solver/blosc/survey snapshot:
  `outputs/core-f-20261029-01/baseline.json`.
- The base library: `core/target/release/librang_core.so` built at
  `43dc3c7` (P0 profile), copied to
  `outputs/p1-solver-20261030-01/librang_core-base-43dc3c7.so`
  (SHA256 `29126bec…`).

## Acceptance criteria (frozen)

1. **Solver bit identity.** `examples/bench_core_f.py check … <task F
   baseline.json>` passes every check (solver gains, flags, iterations and
   converged fraction SHA256 on LUNO and fixture; QuartiCal equalities; LUNO
   convergence; blosc oracle and rows; survey) with `RAYON_NUM_THREADS` 1, 4
   and 16, each run in its own process on the new library.
2. **Phase 2 validator.** `examples/validate_core_phase2.py` passes all
   criteria (extension backend, default threads), including criterion 8
   (`--cost`: LUNO solve ≤ 2.0 s, process ≤ 200 MB).
3. **Fused pass.** `examples/validate_core_phase1.py` passes as it did at
   the archive (`all_passed_with_posthoc_4b`; tolerances 1e-12/1e-13).
4. **Determinism and identity across threads.** `examples/bench_p1_solver.py
   sweep` with the base and new libraries at 1, 2, 4, 8 and 16 threads:
   every output hash (gains, flags, iterations, converged fraction, fused
   residuals, scores, `diag_h`, `diag_b`, `diag_count`, split statistics
   with sums in hex) equals the base library at one thread, on both inputs.
   The fused part of this criterion is stricter than criterion 3; if it
   fails while criterion 3 passes, that is recorded as a failure of the
   bit-identity design target, and the fused result is accepted only at
   criterion 3's tolerance.
5. **K precondition.** `examples/precondition_luno_campaign.py` passes on a
   fresh directory (section 6 pass, QuartiCal and archive comparisons).
6. **Checks.** New Rust unit tests (serial pool versus 8-thread pool on a
   synthetic problem with several time and frequency bins, an
   autocorrelation row, a flagged cell and a non-finite cell), a fast
   pytest `tests/test_p1_solver.py` (subprocesses at different
   `RAYON_NUM_THREADS`), clippy `-D warnings`, `cargo fmt`, and
   `bash tools/check-all.sh` once before the final commit.

## Measurement (frozen)

- Speed: `bench_p1_solver.py sweep`, three rounds, five repeats per process,
  threads 1, 2, 4, 8, 16, base and new libraries alternating within each
  round so both see the same load; ctypes backend through `RANG_CORE_LIB`,
  `OPENBLAS_NUM_THREADS=1`. Reported per cell: minimum and median wall,
  minimum CPU seconds (all threads), median peak RSS of the process, load.
  The speed-up of a cell is the base one-thread minimum over the new
  minimum. A speed-up is claimed only where the new minimum is below the
  base minimum by more than the base median-minus-minimum spread.
- Micro-choices (hoisting, `#[inline(always)]`): `perf stat -e
  instructions:u` of one `bench_p1_solver.py run` at one thread, because the
  host's load (8–25 from sibling sessions) makes wall times noisy.
- Load: the 1-minute load average before and after each process is
  recorded. 8 physical cores, 16 SMT threads; sibling tasks run in
  parallel, so absolute walls are lower bounds on the achievable speed-up.

## Baseline (measured before any kernel change)

Filled in by the baseline commit.
