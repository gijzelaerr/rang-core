# Rang core, big plan task P1: solver and fused pass over solution intervals

Protocol frozen 2026-10-30 in the commit that adds this file, before any
kernel change. Status: **implemented; measured: every equality criterion
passes as frozen (solver and fused pass bit-identical to the base at 1, 2,
4, 8 and 16 threads; phase 1 and 2 validators, task F checks, K
precondition); LUNO solve 5.4× and LUNO fused pass 3.8× faster at 8
threads under load 14–26; the fixture speed-up (5.5–5.7×) does not meet
the frozen claim rule at that load**.
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

**Design deviation (2026-10-30, after the baseline, before any frozen
measurement; criteria unchanged).** Item 1 as written (one fork–join per
iteration) was implemented first (`solve-v1-per-iteration.rs` and its
library in `outputs/p1-solver-20261030-08`) and was bit-identical, but under
this host's load (14–20 on 16 hardware threads) its wall time *grew* with
the thread count (LUNO 0.37 s at one thread, 0.68 s at 4, 1.11 s at 16,
CPU far below wall): with 50 barriers per solve, any preempted worker
stalls every other. It was replaced by **epochs**: until the global stop
test passes, an interval's trajectory depends only on its own state (the
`km1_gain` copy happens on every iteration that does not stop, and nothing
reads it after the loop), so each interval runs `EPOCH = 8` iterations on
its own, recording its converged/flagged counts and (gain, flag, trend)
after every iteration; the stop test is then applied serially, iteration
by iteration, to the summed integer counts, and the stopping iteration's
gains are taken from the record. An error (conjugate-gradient zero
division) counts only if it happens before the stop, as in the serial
loop. This is 7 barriers instead of 50 for a 50-iteration solve; the cost
is up to 7 iterations computed past an early stop and 80 B × 8 per gain of
records. The v1 library is in the frozen sweep as a third arm.

Micro-choices, measured with `perf stat -e instructions:u` on one
`bench_p1_solver.py run --repeats 3` at one thread (whole process,
including input loading, both inputs, the early-stop variants and the
fused passes; all variants bit-identical):

| Variant | Instructions | Kept |
| --- | ---: | --- |
| epochs, `#[inline(always)]` copies of `mul`/`adjoint`/`from_f32`/`all_finite` | 39.699 G | – |
| the same, copies removed (calls to the identical `jones` functions) | 39.699 G | yes: identical count, LTO inlines them |
| full hoist: per interval, f64 data, model and weights of unflagged cells | 36.447 G (−8.2 %) | no: +168 B per unflagged cell, about 5 GB on the whole array (P5's budget is about 150 B per cell in all) |
| index hoist: per interval, the unflagged cells' indices and antennas | 38.146 G (−3.9 %) | yes: 16 B per unflagged cell |

`data_flags` and `init_flags` (now derived from the per-interval cell
lists) also run on the pool; both are boolean, so order-free.

**Fused pass as implemented (deviation from item 2, same target).** Two
parallel sweeps instead of time-bin row groups, so unsorted rows need no
serial fallback: (a) row blocks of about 16,384 cells, in waves of 64
blocks, compute residuals (written to the block's slice of the output) and
record, in cell order, (label, valid, mean `w |r|^2`) of every labelled
cell and (cell, baseline, log amplitude) of every scored train cell; after
each wave one serial fold adds the records to the split statistics and the
per-baseline amplitude lists in cell order, exactly as the serial loop did
(the wave bounds the records at about 16 MB); (b) the normals run per
interval (time bin × frequency bin), over the interval's rows in ascending
order (a stable bucket of rows by time bin) and channels in ascending
order, recomputing the prediction of each valid train cell. Robust scores
run per baseline on the pool and are written serially. Every product is
bit-identical by construction; the price is the prediction computed twice
for valid train cells.

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

2026-10-30 09:00–09:01 SAST, load 3.8–6.4 (quiet for this host), base
library `librang_core-base-43dc3c7.so` (ctypes) and the extension built
from the same commit. Runs `outputs/p1-solver-20261030-02` to `-07`
(`-06` unused).

| Run | Result | Wall | Peak RSS |
| --- | --- | ---: | ---: |
| `bench_core_f.py check --target all` (`-02`, `RAYON_NUM_THREADS=1`) | all 8 checks pass (solver bit-identical on LUNO and fixture, QuartiCal, convergence, blosc oracle and rows, survey) | 36.0 s | 827 MB |
| `validate_core_phase2.py` (`-03`) | all 12 criteria pass | 1.96 s | 116 MB |
| `validate_core_phase2.py --cost` | solve 0.255 s, fused 0.024 s, 50 iterations, 96.5 MB | 0.40 s | 97 MB |
| `validate_core_phase1.py` (`-04`) | `all_passed_with_posthoc_4b` true (criterion 4 fails as frozen, as archived) | 1.02 s | 383 MB |
| `precondition_luno_campaign.py` (`-05-precondition`) | all checks pass, χ² 0.26823507037914956 | 2.34 s | 144 MB |
| `bench_p1_solver.py sweep`, base, one thread, 3 rounds × 5 repeats (`-07`) | all hashes equal across rounds | 8.3 s | 204 MB |

Kernel times from the sweep (minimum / median over 15 calls, one thread):

| Input | Solve wall s | Solve CPU s (min) | Fused wall s |
| --- | ---: | ---: | ---: |
| LUNO (192 × 2,048, 16 × 64 intervals) | 0.2462 / 0.2581 | 0.2462 | 0.0185 / 0.0209 |
| Fixture (140 × 4,096, 7 × 128 intervals) | 0.1698 / 0.1755 | 0.1698 | 0.0245 / 0.0257 |

`perf stat -e instructions:u,cycles:u` of one `bench_p1_solver.py run
--repeats 3` at one thread, base library: 28.717 G and 28.718 G
instructions, 8.25 G and 8.18 G cycles (two runs).

## Measured result (2026-10-30, as frozen)

Library `outputs/p1-solver-20261030-08/librang_core-new-0470c4d.so`
(SHA256 `9031718b…`, commit `0470c4d`), extension rebuilt from the same
commit. Load 14–26 throughout (sibling tasks: a whole-suite pytest at up to
10 cores, the whole-array campaign, P2 and P3 benchmarks), so walls are
upper bounds; the equality results do not depend on load.

| Criterion | Run | Result |
| --- | --- | --- |
| 1 solver bit identity, `bench_core_f.py check --target all` | `-09` (1 thread), `-10` (4), `-11` (16) | **pass**: all 8 checks in each (solver SHA256 on LUNO and fixture, QuartiCal, LUNO 50 iterations / 0.9833234067897558, blosc oracle and rows, survey); 55–57 s, 849–861 MB each |
| 2 phase 2 validator | `-12` | **pass**: all 12 criteria; 3.19 s, 120 MB |
| 2 criterion 8 (`--cost`) | not archived (stdout) | **pass**: 1 thread solve 0.53 s, fused 0.061 s, 99.7 MB self / 100 MB process; default threads solve 0.27 s, fused 0.044 s, 101 MB / 101 MB (limits 2.0 s, 200 MB; base 0.255 s, 96.5 MB at load 4) |
| 3 phase 1 validator | `-13` | **pass** as archived: `all_passed_with_posthoc_4b` true (criterion 4 fails as frozen, as at the archive) |
| 4 determinism and identity, sweep | `-16` | **pass**: `all_equal` true over 45 processes (base, v1, new × 1, 2, 4, 8, 16 threads × 3 rounds): gains, flags, iterations, converged fraction, the 8 early-stop variants (stops at 8, 15, 19, 35 on LUNO; 1, 3, 12 and 25 on the fixture), fused residuals, scores, `diag_h`, `diag_b`, `diag_count` and split sums all equal to the base at one thread |
| 5 K precondition | `-14-precondition` | **pass**: all checks, χ² 0.26823507037914956; 4.25 s, 155 MB |
| 6 checks | – | 51 core Rust tests (3 new: solver against the verbatim serial `reference_solve` at 1, 3, 8 threads over 324 settings including stops at iterations 1, inside the first and second epochs and caps at 8, 9 and 50; `decide`; cell order and `init_flags`; fused pass against the verbatim serial `reference_run` with unsorted rows, autocorrelations, stored and scalar models, an infinite weight, a NaN gain, an invalid gain and one-row blocks in waves of three), clippy and fmt clean; `tests/test_p1_solver.py` (1, 2, 7 threads) passes; check-all below |

A mutation check (cells of each interval reversed) made both solver tests
fail, so the tests do see the summation order.

**Speed (sweep `-16`, minimum / median over 15 calls per cell, seconds).**
Speed-up is the base one-thread minimum over the cell's minimum. The base
library is single-threaded at every `RAYON_NUM_THREADS`.

| Threads | LUNO solve new | speed-up | LUNO solve CPU s | Fixture solve new | speed-up | LUNO fused new | Fixture fused new | Peak RSS MB (base 204) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.2387 / 0.397 | 1.06× | 0.239 | 0.1529 / 0.224 | 1.14× | 0.0240 / 0.038 | 0.0270 / 0.038 | 213 |
| 2 | 0.1217 / 0.326 | 2.07× | 0.241 | 0.0834 / 0.252 | 2.08× | 0.0135 / 0.044 | 0.0156 / 0.023 | 214 |
| 4 | 0.0806 / 0.288 | 3.13× | 0.314 | 0.0481 / 0.216 | 3.61× | 0.0101 / 0.050 | 0.0120 / 0.044 | 217 |
| 8 | 0.0466 / 0.055 | 5.41× | 0.343 | 0.0314 / 0.038 | 5.53× | 0.0071 / 0.011 | 0.0102 / 0.013 | 218 |
| 16 | 0.0482 / 0.080 | 5.23× | 0.430 | 0.0306 / 0.055 | 5.67× | 0.0079 / 0.015 | 0.0107 / 0.013 | 223 |
| base, 1 | 0.2523 / 0.456 | – | 0.252 | 0.1736 / 0.336 | – | 0.0273 / 0.036 | 0.0248 / 0.048 | 204 |
| v1, 8 | 0.0589 / 0.064 | 4.28× | 0.375 | 0.0455 / 0.051 | 3.82× | – | – | 206 |
| v1, 16 | 0.0621 / 0.147 | 4.06× | 0.470 | 0.0487 / 0.116 | 3.56× | – | – | 206 |

The frozen claim rule (new minimum below the base minimum by more than the
base median-minus-minimum spread) is met by the LUNO solve at 8 and 16
threads (margins 0.206 and 0.204 s against a spread of 0.204 s, barely,
because the load inflated the base median to 0.456 s) and by the LUNO fused
pass at 2–16 threads (spread 0.0089 s); it is **not met** for the fixture
solve or fixture fused pass at any thread count (spreads 0.163 s and
0.023 s), although every fixture minimum and median is lower than the
base's. At this load the speed-up claim is therefore limited to the LUNO
solve (about 5.4× at 8 threads) and the LUNO fused pass (about 3.8×); the
rest is measured but not claimed. (Ratios of medians at 8 threads, 8.3×
and 8.8×, are inflated by the load on the base runs and are not claimed
either.) 16 threads is no faster than 8 (8
physical cores, and the host was oversubscribed). The epoch design beats
the per-iteration v1 at 8 and 16 threads on both inputs, by 1.26–1.6×,
with less CPU.

Peak RSS of the sweep process rises by 9–19 MB (per-interval cell lists,
epoch records, rayon threads' stacks and allocator arenas); the phase 2
cost process rises from 96.5 to 99.7–101 MB.

`perf stat` at one thread (whole bench process with the early-stop
variants, two runs each, load 16): base 39.241 G instructions, new 38.538 G
(−1.8 %; the index hoist saves more in the solver, the fused pass's second
prediction for the normals and the epoch overrun on the early-stop
variants give some back); cycles 17.2–20.2 G against 13.7–15.4 G.

**Whole-array implication (estimate, not measured).** The parallel work is
per interval; LUNO chunk 0 with 56 stations has the same 16 × 64 intervals
with about 257× more cells each, so the barriers are relatively cheaper
and the 8-core ceiling of about 6–8× should hold: review estimate 89 s →
about 13 s per solve. Task L1's run is the place to measure it.

## Open items and follow-ups

- **QuartiCal's swapped XY/YX weights in the qp half of `J^H W J`**
  (QuartiCal issue 452, STATE's U1 entry) are reproduced unchanged, since
  bit identity with the phase 2 archive is this task's criterion. Fixing it
  changes archived gains and belongs to a science protocol.
- The convergence criterion and warm starts (review section 2.7; "Not in
  P1") are unchanged.
- Fixture speed-up not claimable at this load under the frozen rule; a
  quieter repeat of the same sweep would settle it (not run: the host did
  not get quiet within this task).
- With `RAYON_NUM_THREADS` unset, the solver and fused pass now use every
  logical CPU; results are unchanged, but sibling sessions' timings and
  load will shift. Campaign drivers that run several processes at once
  should set it.
- `EPOCH = 8` was chosen, not tuned: it bounds the overrun past an early
  stop to 7 iterations and the barriers to 7 per 50 iterations.

**`bash tools/check-all.sh`** (once, on the working tree of the final
commit; `outputs/p1-solver-20261030-17-check-all.log`): overall **PASS**
(root 19 and core 51 Rust tests, clippy, fmt, extension build, ruff,
diff-check, pytest 740 passed in 1,665 s); 28 min 25 s, 1.73 GB, load
13.7 → 40.0.

## For the coordinator

- **STATE paragraph.** Task P1 (solver and fused pass over solution
  intervals, [p1-solver.md](p1-solver.md)): implemented and measured. The
  ported QuartiCal solver now runs each (time bin × frequency bin) interval
  on rayon in epochs of 8 iterations with a serial, iteration-by-iteration
  replay of the global stop test, and the fused pass sweeps row blocks in
  parallel with a serial fold of the order-dependent sums and per-interval
  normals. Every product is bit-identical to the single-thread code at 1, 2,
  4, 8 and 16 threads (task F checks, phase 1 and 2 validators, K
  precondition, a 45-process sweep including early-stop settings); LUNO
  solve 0.252 → 0.047 s (5.4×) and fused pass 0.027 → 0.007 s at 8 threads
  under load 14–26; the fixture's 5.5× is measured but below the frozen
  claim rule at that load. Thread count: `RAYON_NUM_THREADS` (default all
  logical CPUs). QuartiCal's swapped qp weights (issue 452) are reproduced
  unchanged.
- **No signature, `lib.rs`, `ffi*.rs`, `core/py/src/lib.rs` or `core.py`
  change.** The thread count is rayon's global pool from
  `RAYON_NUM_THREADS`; with it unset every chain now uses all 16 logical
  CPUs in these two kernels, so concurrent campaign processes should set it.
- **Timing rows** (`tool-timings.md`, all 2026-10-30, task P1):

| Tool | Input | Wall | Peak RSS | Notes |
| --- | --- | ---: | ---: | --- |
| venv (`uv venv` + `uv pip install -e .[…]`), core and root release builds, `maturin develop` | worktree | 65 s in all (core build 14.0 s, root 7.0 s, extension 22.5 s) | 385 MB | load 13.8–22.4 |
| baseline: `bench_core_f.py check --target all` (`-02`) | archived LUNO, fixture, blosc oracle | 36.0 s | 827 MB | base library, 1 thread, load 6.4 → 4.2, all 8 checks pass |
| baseline: phase 2 validator (`-03`), `--cost`, phase 1 validator (`-04`), K precondition (`-05`) | archived inputs | 1.96 s, 0.40 s, 1.02 s, 2.34 s | 116, 97, 383, 144 MB | load 4.2; all pass as archived |
| baseline: `bench_p1_solver.py sweep` (`-07`), base, 1 thread, 3 × 5 | LUNO + fixture | 8.3 s | 204 MB | load 3.9–4.1 |
| `bench_core_f.py check --target all` at 1, 4, 16 threads (`-09`–`-11`) | as above | 56.3, 57.5, 54.8 s | 849–861 MB | new library, load 21–23, all checks pass |
| phase 2 validator (`-12`), `--cost` (1 thread / default), phase 1 validator (`-13`), K precondition (`-14-precondition`) | archived inputs | 3.19 s, 0.93 / 0.56 s, 2.17 s, 4.25 s | 120, 100 / 101, 386, 155 MB | load 22.7–23.5; all pass |
| `bench_p1_solver.py sweep` (`-16`), base / v1 / new × 1–16 threads × 3 rounds × 5 | LUNO + fixture | 3 min 20 s | 229 MB | load 14.5–25.9; all 45 processes equal |
| `perf stat` instruction counts, development variants (8 pairs) | one bench run each | 2–4 s each | about 210 MB | load 6–20 |
| `cargo test` core (51 tests, release) | – | 1.0–3.1 s | – | – |
| `tests/test_p1_solver.py` | synthetic | 0.34–0.61 s | – | three subprocesses |
| `bash tools/check-all.sh` (`-17`) | branch | 28 min 25 s (pytest 740 passed in 1,665 s) | 1.73 GB | PASS; load 13.7–40.0 |

- **Upstream observations.** RATT: none new; the solver reproduces QuartiCal
  0.2.7 bit for bit at any thread count, including issue 452's swapped qp
  weights, which stay a science follow-up. A note QuartiCal could use:
  its intervals are independent until the global stop test, so per-interval
  epochs with a replayed stop test parallelise without changing results
  (not filed; an optimisation idea, not a bug). Non-RATT: none.
- **Evidence to keep** (ignored outputs): `outputs/p1-solver-20261030-01`
  (base library and commit), `-02`–`-05`, `-07` (baseline), `-08` (base,
  v1, full-hoist and final libraries, v1 source), `-09`–`-14-precondition`
  (validators), `-16` (sweep: 45 child JSONs and `summary.json`), `-17`
  check-all log. `-06` and `-15` unused.
