# L5 solver science: the qp weight fix, the stop criterion and Anderson acceleration

Protocol frozen 2026-10-30 in the commit that adds this file, before any
change to `core/src/solve.rs`. Status: **proposed** (protocol only).
Task L5 of [big-plan.md](big-plan.md) (user decision 2026-10-30: one
protocol fixes QuartiCal issue 452 in the core as a validated deviation
behind a compatibility flag that keeps the archived behaviour, and studies
a loss-based or gauge-invariant convergence criterion, and Anderson
acceleration, against the 50-iteration cap; a default changes only if the
protocol passes, and every archive comparator keeps passing under the
compatibility flag).

## Background

- The core solver (`core/src/solve.rs`) is a bit-exact port of QuartiCal
  0.2.7's `complex` term ([core-phase2.md](core-phase2.md)), parallel over
  solution intervals since task P1 ([p1-solver.md](p1-solver.md)): each
  interval runs epochs of 8 iterations and the global stop test is
  replayed serially, iteration by iteration, from integer counts.
- **Issue 452** ([upstream-issues/quartical-qp-jhj-weights.md](upstream-issues/quartical-qp-jhj-weights.md),
  https://github.com/ratt-ru/QuartiCal/issues/452): the qp half of `J^H W J`
  uses the pq weight order, swapping the XY and YX weights. `J^H W r` and
  hence the fixed point are right; the Gauss–Newton step is not. The port
  reproduces this on purpose.
- **Convergence** ([simplification-review.md](simplification-review.md)
  section 2.7, LUNO four-station slice): 7.3 % of gains pass the 1e-7
  relative-change test at 8 iterations, 49 % at 15, 98.33 % at 45; the
  0.99 stop fraction is reached only at 91. Held-out MSE is within 2e-5
  relative of the 50-iteration value by iteration 12, while baseline gain
  products still move 1.3e-3 between 50 and 91. Whole array
  ([luno-array-campaign.md](luno-array-campaign.md)): 83 % converged at the
  50-iteration cap on 53 stations.
- **Weights on our data** (measured 2026-10-30 before this protocol, on
  unflagged cells with all four weights positive): LUNO slice
  (`outputs/core-phase2-inputs-20261029-01/arrays.npz`, 117,556 cells)
  w_XY ≠ w_YX in 100 % of cells, w_XY/w_YX in [0.990, 1.028] (median
  1.007); w_XY/w_XX ≈ 1.85. The fixture clean case
  (`outputs/tv-response-wsl-20261029-01/clean/state.npz`) has w_XY ≠ w_YX in
  60 % of cells. So Q1 is testable on real data, but the asymmetry is a
  few per cent.

## Questions

- **Q1.** Does correcting the qp weights change the converged gains, the
  iteration count and the held-out error on real data with w_XY ≠ w_YX?
- **Q2.** Which stop criterion ends the solve when the gains stop
  mattering? Candidates: (a) the current per-gain relative gain change
  1e-7 with stop fraction 0.99 and the 50-iteration cap (the archived
  default, `D`); (b) a gauge-invariant criterion on baseline products
  `G_p G_q^H`; (c) a loss-based criterion on the weighted residual; (d) a
  fixed small cap.
- **Q3.** Does Anderson acceleration (depth m = 2, 3, 5) of the
  Gauss–Newton fixed-point iteration reduce iterations without changing
  the fixed point?

## Implementation (to be done after this commit)

All in `core/src/solve.rs`; no C ABI, extension signature or default
changes (`ffi.rs`, `lib.rs`, the PyO3 binding and `python/rangtoy/core.py`
are not edited).

- **Options** are read inside `solve::solve` from one environment variable,
  `RANG_SOLVE_OPTIONS`, a comma-separated `key=value` list, so both the
  ctypes and the extension backends see them. Unset or empty means the
  archived behaviour. Keys:
  - `qp_weights=archived|transposed`: `transposed` passes
    `(w_XX, w_YX, w_XY, w_YY)` to the qp accumulation of `J^H W J` (both the
    finite and the general path); `J^H W r` is unchanged.
  - `stop=gain|product|loss`: the per-unit convergence test. `gain` is the
    archived per-gain test `|Δg|² / |g_{k-1}|² < τ²`, units = gains.
    `product`: an interval passes when `max_{p<q} ‖ΔP_pq‖_F / ‖P_pq,k-1‖_F < τ`
    over pairs of unflagged gains, `P_pq = G_p G_q^H`; units = intervals.
    `loss`: an interval passes when `|χ²_{k-1} − χ²_k| / χ²_k < τ`, with
    `χ²` the interval's weighted squared residual summed during the `J^H W r`
    accumulation, i.e. evaluated at the gains entering the iteration (a lag
    of one iteration, documented); units = intervals. In every case τ is the
    existing `stop_criterion` argument and the fraction is the existing
    `stop_fraction` argument, applied to the count of passing units over
    the count of unflagged units (an interval is unflagged if any of its
    gains is). The flag ladder (`update_gain_flags`) runs unchanged under
    every criterion.
  - `anderson=m` (0 = off): type-II Anderson acceleration per interval on
    the real vector of all unflagged gains of the interval. Because the
    archived iteration halves the update on even iterations, one map
    evaluation is the **pair** (even half step, odd full step); mixing is
    applied after each odd iteration with the last m secant pairs,
    Tikhonov-regularised normal equations (λ = 1e-12 × trace) and a
    safeguard: the history is reset and the plain step taken if the mix is
    non-finite, the set of unflagged gains changed, or the pair residual
    norm grew. The output snapshot of an iteration is the unmixed iterate;
    the mixed point is where the next iteration starts. `m = 0` must be
    bit-identical to the archived path.
  - `freeze=0|1` (exploratory, measured only for the criterion Q2
    selects): an interval that passes its interval criterion stops
    iterating and keeps reporting its last state. This is the only option
    that can cut cost per iteration rather than the iteration count.
  An unknown key or malformed value makes the solve fail (status 1), never
  a silent default.
- **Trace.** `RANG_SOLVE_TRACE=<path>` writes, after the solve, one JSON
  record per iteration built serially from the epoch records in interval
  order: the gain-test pass count and flagged count, the per-interval
  product change and χ² (arrays over intervals), and the unflagged-unit
  counts. From one forced long run (stop fraction 2, never met) the stop
  iteration of any criterion and tolerance is then computed by the same
  rule as `decide`. Every float reduction is serial in interval order, so
  the trace and every criterion stay identical at every thread count.
- Python: `python/rangtoy/core_solver_study.py` (option context, trace
  reader, stop-iteration replay, metrics), `examples/run_l5_solver_study.py`
  (the measurement), `tests/test_l5_solver.py`.

## Data sets (read-only)

1. **F, fixture clean case**: `outputs/tv-response-wsl-20261029-01/clean`,
   the phase 2 validator's inputs (`state.npz`, the solve flags of
   `backups/clean-t2-f32-solve.npz`, the archived split in `state.npz`), grid
   2 × 32.
2. **S, LUNO four-station slice**: `core_campaign_array.decode_inputs`
   with stations 0–3 and `build_state(nant=4)`, seed-7 split (must give
   94,047 / 11,742 / 11,767 training / validation / test cells, K's
   counts), solve flags `solve_flags(state, 0)`, grid 2 × 32 (task K's
   `original` arm).
3. **A, whole array**: the same with all stations (task L1's `original`
   arm), only if `free -g` shows at least 20 GiB available at the start;
   otherwise the largest station subset that fits, stated as such.

## Arms and settings

`RAYON_NUM_THREADS=4` throughout; grid 2 integrations × 32 channels.

- **D (default, archived)**: `qp_weights=archived`, `stop=gain`, τ = 1e-7,
  fraction 0.99, cap 50, no Anderson. Must reproduce K's and L1's
  `original` gains bit for bit.
- **Trace runs** (cap 500 on F and S, 300 on A; fraction 2.0): weights
  archived and transposed with m = 0; weights archived with m = 2, 3, 5.
  The m = 0 archived-weights trace run is the **reference R**, the
  "converged" solution for gain-product distances (whether it actually
  settled is reported: last-iteration max relative gain and product
  change).
- **Criteria grid** (stop iterations computed from the trace, then the
  gains obtained by re-solving with `max_iterations = k`, which is a
  deterministic prefix of the long run; for the selected criterion and
  every implemented criterion at least once per data set, the criterion is
  also run directly and its stop iteration must equal the trace's):
  - `gain` τ ∈ {1e-7, 1e-6, 1e-5}, fraction 0.99, no cap below 500;
  - `product` τ ∈ {1e-3, 1e-4, 1e-5, 1e-6}, fraction 0.99;
  - `loss` τ ∈ {1e-5, 1e-6, 1e-7, 1e-8}, fraction 0.99;
  - fixed caps K ∈ {8, 12, 16, 24} (fraction 2.0).
  Each candidate keeps a safety cap of 500 (300 on A); a candidate that
  hits it is reported as not stopping.
- **Q1 arms**: D and D with `qp_weights=transposed` (D_T); R and R_T (the
  transposed trace run).
- **Q3 arms**: Anderson m ∈ {2, 3, 5} with archived weights, under the
  `gain` criterion 1e-7/0.99 and under the criterion selected in Q2.

## Metrics

Per arm: held-out weighted MSE on the validation and test cells and
training χ² (`fused_pass` losses: the section 6 residual definition, the
mean over cells of the correlation-mean `w|r|²`, as K and L1); when two
arms' valid gain sets differ, the comparison uses L1's matched cells
(`restricted_losses` on cells both arms predict). Gain products: max and
median relative `‖P_pq − P_pq^R‖_F / ‖P_pq^R‖_F` against R over pairs valid
in both, and the per-iteration product change from the trace. Iterations,
converged fraction, valid-gain fraction, flagged-gain count, polar-gauge
TV (reported, not gated; the flagging experiment consumes it). Cost: solve
wall seconds and CPU seconds (`getrusage` delta), as A/B pairs D, C, D, C,
D, C alternating in one process under the same load, load average before
and after. Point-source **residual RMS** of the dirty image (K's
definition and image settings) on S for D, D_T, R and the candidate
default; on A for D and the candidate default only (an array image takes
4–14 minutes), with L1's image settings.

## Acceptance (frozen)

1. **Compatibility.** With `RANG_SOLVE_OPTIONS` unset, and set to the
   explicit archived values, `examples/bench_core_f.py check` (target
   `solve`) against `outputs/core-f-20261029-01/baseline.json` passes at
   `RAYON_NUM_THREADS` 1, 4 and 8, the phase 2 validator passes all
   criteria, the K precondition passes, P1's serial-equivalence Rust test
   passes, and D on S and A reproduces K's and L1's `original` gains hash.
2. **Deviations documented.** Every non-default option is reported with
   its numbers against D and R, as a deviation from QuartiCal 0.2.7.
3. **Held-out margin.** δ = 1e-4 relative (five times the 2e-5 by which S1
   saw the held-out MSE settle at iteration 12).
4. **Q1 decision.** `qp_weights=transposed` is recommended as the default
   if, on F, S and A, MSE_test(D_T) ≤ (1 + δ) MSE_test(D) on matched cells,
   the valid-gain fraction is not lower, and R_T and R agree in gain
   products to the precision at which R settled. Expected: near-null (the
   asymmetry is a few per cent and the fixed point does not move).
5. **Q2 selection and decision.** Selection on **S validation** only: among
   the non-default criteria, the one with the fewest iterations whose
   MSE_val is within δ of MSE_val(D) on S. Confirmation on **F, S and A
   test**: the selected criterion C replaces the default only if on all
   three MSE_test(C) ≤ (1 + δ) MSE_test(D) (matched cells), the residual
   RMS is not worse by more than 1 % (K's call threshold; S and A), the
   valid-gain fraction is not lower by more than 0.1 % absolute, and the
   median solve wall of the A/B pairs is lower on S and A.
6. **Q3 decision.** Anderson is recommended if, for some m, the iterations
   to the criterion in force drop by at least 20 % on S and A, the margin
   of 5 holds, the flagged-gain count does not rise, and the Anderson long
   run agrees with R in gain products to within ten times the precision at
   which R settled ("same fixed point").
7. Any failure is recorded as frozen; anything decided after seeing
   results is labelled post hoc.

## Seeds and determinism

The seed-7 split (K, L1) is the only randomness. The core is
deterministic and every new option is designed to be bit-identical at
every thread count (tested at 1, 3 and 8 threads in Rust).

## Expected outcome (stated before measuring)

- Q1: near-null. Held-out MSE changes below 1e-5 relative at the cap;
  iteration counts may move by a few; converged products equal to the
  precision of R.
- Q2: the `product` and `loss` criteria stop on S at 10–25 iterations with
  held-out MSE within δ of D, a 2–5× cut in iterations; on A, where 17 % of
  gains have not passed the gain test at 50, the gain test is the wrong
  measure (it watches gauge-dependent gains) and an interval criterion
  should stop earlier with the same held-out error. A fixed cap of 12–16
  is likely as good on held-out error but is not adaptive.
- Q3: uncertain. If the slow mode is a near-linear drift, Anderson cuts
  the iterations to the gain criterion substantially; the flag ladder and
  the half-step pairing may make it erratic.

## Amendment 1 (2026-10-30, after implementation, before any measurement)

- The tolerance of the interval criteria is part of the option
  (`stop=product:<tol>`, `stop=loss:<tol>`), not the `stop_criterion`
  argument: the flag ladder of `update_gain_flags` uses `stop_criterion`
  (its "converged" branch resets soft flags), so reusing it would change
  the dynamics with the tolerance. With the tolerance in the option, a
  product or loss run is a deterministic prefix of the archived long run
  and the trace predicts its stop exactly (tested in Rust and pytest). The
  gain criterion at τ = 1e-6 and 1e-5 changes the ladder and is therefore
  run directly, not replayed.
- The interval criteria, like the archived gain test, cannot pass before
  iteration index 2.
- `freeze=1` under `stop=gain` freezes an interval when every gain of it
  that is not hard-flagged passed the gain test in the same iteration.

## Comparator precondition (run before any code change, 2026-10-30)

Run `outputs/l5-solver-20261030-01` (log `outputs/l5-solver-20261030-01.log`),
`RAYON_NUM_THREADS=4`, worktree at 07dfb86, `MemAvailable` 24 GiB:

| Check | Result | Wall |
| --- | --- | ---: |
| `cargo build --release` (core) | built | 54.5 s |
| `validate_core_phase2.py` | all 11 criteria pass | 12.4 s |
| `precondition_luno_campaign.py` (K) | all checks pass, χ² 0.26823507 | 7.4 s |
| `bench_core_f.py check --target solve` vs `core-f-20261029-01` | all 5 checks pass (library SHA256 `2017b928…`) | 5.2 s |

The precondition holds; measurements may proceed.
