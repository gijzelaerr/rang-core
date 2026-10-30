# L5 solver science: the qp weight fix, the stop criterion and Anderson acceleration

Protocol frozen 2026-10-30 in the commit that adds this file, before any
change to `core/src/solve.rs`. Status: **implemented and measured
2026-10-30; as frozen no default changes** (Q1 no held-out effect, |Δ| ≤ 8e-9;
Q2 the selected cap-8 fails the fixture; Q3 Anderson m = 3 reaches the
0.99 gain criterion in 21–65 iterations instead of 55 to > 300, same
held-out error, but needs 65 on the whole array, so the 50 cap still binds
there). Options stay opt-in through `RANG_SOLVE_OPTIONS`.
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

## Amendment 2 (2026-10-30, after the fixture and slice sweeps, before any array run)

Written after seeing the fixture (`-03`, `-06`) and slice (`-04`, `-07`)
sweeps and the post-hoc diagnostic `-05`; the fixture and slice results
under this amendment are therefore **post hoc**, the array results
**prospective**.

- **Observed-pair product distance.** Run `-05` showed that 26 slice
  intervals have only two observed baselines (one gain hard-flagged, the
  third baseline without an unflagged cell): the third baseline product is
  then not constrained by the data, and long runs that agree to 1e-16 in
  training χ² differ there by up to 1.9e-4 (R_T) and 2.0e-7 (Anderson). The
  frozen "all pairs valid in both" distance is kept and reported; the Q1
  clause "R_T and R agree in gain products" and the Q3 clause "same fixed
  point" are, under this amendment, evaluated on **observed pairs** (pairs
  with at least one cell the solver uses in the interval), with the
  precision at which R settled taken as the larger of its last-iteration
  product change and its distance to a 10× longer run where measured
  (slice: R500 vs R5000, 1.6e-13).
- **Anderson depth.** The rule of acceptance 5 extended to m: the smallest
  m tied for the fewest iterations to the gain criterion on the slice,
  i.e. **m = 3** (21 iterations; m = 5 also 21, m = 2 23). The array and
  the confirm runs use `anderson=3` with the archived cap 50 and fraction
  0.99.
- **Missing frozen arms added**: Anderson m = 2, 3, 5 under the criterion
  Q2 selected (a fixed cap of 8, fraction 2), and `freeze=1` under the same
  configuration; both run on all three data sets.
- **Combined arm**: `qp_weights=transposed,anderson=3` with cap 50 and
  fraction 0.99 on all three data sets, because a joint default
  recommendation would otherwise rest on an unmeasured combination.
- **Confirm runs** (A/B pairs, images) for `anderson=3` and for the
  combined arm; five A/B pairs on the fixture and slice (cheap; the host
  load is about 55), three on the array.
- As frozen, Q2 selected `cap-8` (slice validation −6.9e-5 relative, within
  δ) and it fails on the fixture test (+3.9e-3 relative), so the frozen
  Q2 outcome is **no default change**; this amendment does not reopen it.

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

## Implemented (commit 8f58db3 and later on branch `l5-solver-science`)

`core/src/solve.rs`: `Options` (`qp_weights`, `stop`, `anderson`, `freeze`)
parsed from `RANG_SOLVE_OPTIONS` inside `solve::solve`, `solve_with` and
`solve_traced` for explicit options, `Trace` (written to
`RANG_SOLVE_TRACE`), the const-generic `accumulate_interval<TRANSPOSED,
CHI2>` (the default instance does exactly the archived operations), the
per-interval product change and χ², the safeguarded `Anderson` state per
interval, and `unit_counts` feeding P1's unchanged integer `decide`. Two
new `Error` variants (`Options`, `Trace`) map to status 1 through the
existing `Err(_)` arm of `ffi.rs`. No C ABI, extension signature or
default changed; `lib.rs`, `ffi.rs`, the PyO3 binding and `core.py` are
untouched. Python: `python/rangtoy/core_solver_study.py`,
`examples/run_l5_solver_study.py` (`sweep`, `select`, `confirm`; `--lean`
for the array), `examples/diagnose_solver_study.py` (post hoc),
`examples/archive_solver_study.py`, `tests/test_l5_solver.py`.

Rust tests (`cargo test --release --lib solve::`, 14 pass): the issue 452
one-step check (a single Gauss–Newton step for antenna q with weights
(1, 0.2, 5, 1) lands on the truth to < 1e-10 with transposed weights and
misses by > 1e-2 with the archived ones); transposed weights bit-identical
to archived when w_XY = w_YX; explicit default options and the traced solve
bit-identical to P1's serial reference solver; every new option
bit-identical at 1, 3 and 8 threads with stops inside the first and second
epoch, and the product stop equal to the trace replay and to the prefix of
the long run; Anderson m = 2, 3, 5 on noiseless data reaches the true
baseline products in no more iterations than plain; option parsing rejects
every malformed key or value.

## Measured result (2026-10-30)

All runs `RAYON_NUM_THREADS=4`, library SHA256 `3a4b1378…` (core) on host
load 5–80 (siblings), timings as A/B pairs in one process. Runs:
compatibility `-02`; fixture sweep `-08` (identical arms in `-03`, `-06`),
slice sweep `-09` (`-04`, `-07`), post-hoc diagnostic `-05`, 32-station
sweep `-15`, whole-array sweep `-18` (`--lean`); confirms: fixture `-10`
(anderson=3), `-11` (combined), slice `-12`, `-13`, `-14` (cap-8),
32 stations `-16`, `-17`, array `-19`. Archive:
[results/l5-solver-science.json](results/l5-solver-science.json).

**Data-set note.** The whole array did not fit at first (MemAvailable 6–11
GiB for 45 min under sibling runs), so the protocol's fallback ran first:
the largest station subset that fitted, **stations 0–31** (`stations-32`,
14,836 rows, a fresh seed-7 split of 7,313,333 / 912,683 / 912,380 cells).
Memory then freed and the **whole array** (56 stations, L1's split
27,401,558 / 3,419,206 / 3,418,059, D's gains hash `13ba1c66…` = L1's
`original` arm) ran with the `--lean` sweep: criteria that the trace says
never stop within 300 iterations reuse R (a bit-identical prefix, checked
on every other arm) instead of re-solving, and the held-out curve has
seven points. Both are reported; the array is the prospective data set.

### Compatibility (acceptance 1): pass

| Check (`-02`, new library) | Result |
| --- | --- |
| `bench_core_f.py check --target solve`, options unset, 1 / 4 / 8 threads | all 5 checks pass at each |
| the same with the explicit archived option string, 4 threads | all 5 pass |
| `validate_core_phase2.py` | all 11 criteria pass |
| K precondition | all checks pass, χ² 0.26823507 |
| D on the slice / array | gains SHA256 = K's / L1's `original` arm |
| slice D image | residual RMS 0.07122052624593866 vs K's 0.07122052624593858 (the dirty-image hash differs: P2 replaced the gridder after K) |

### Convergence of the archived solver (the curve; R = 500 / 500 / 300 iterations)

Fraction of gains passing the 1e-7 test (stop needs 0.99):

| Iteration | 8 | 15 | 45 | 50 | 100 | 200 | 300 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixture | 0.000 | 0.002 | 0.970 | 0.984 (stops at 55) | 1.000 | | |
| slice | 0.073 | 0.492 | 0.983 | 0.983 (stops at 91) | 0.991 | | |
| 32 stations | 0.028 | 0.449 | 0.601 | 0.603 | 0.715 | | 0.863 |
| whole array | 0.002 | 0.089 | 0.831 | 0.833 | 0.940 | 0.976 | 0.980 |

Held-out test MSE relative to R (prefix solves; positive = worse):

| Iteration | 8 | 12 | 16 | 24 | 50 | 100 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixture | +3.9e-3 | +4.8e-4 | (15: +2.2e-4) | (25: +2.5e-5) | +1.2e-7 | +4e-12 |
| slice | −1.2e-4 | −3.2e-5 | (15: −1.5e-5) | (25: −5.4e-7) | +7.8e-8 | +4.1e-9 |
| 32 stations | +3.0e-4 | +7.0e-5 | +2.1e-5 | −1.2e-6 | −4.4e-6 | −2.4e-6 |
| whole array | +1.1e-3 | +1.1e-4 | +3.2e-5 | +8.8e-6 | +6.7e-7 | +5.4e-8 |

On real data the held-out error is within 1e-4 of the long run by
iteration 12–16 and within 1e-5 by 24, while 17 % (array) to 40 % (32
stations) of gains have still not passed the gain test at the cap of 50,
and R itself is still moving at 300 iterations on the array and on 32
stations (largest per-iteration product change 1.7e-4 and 2.3e-4, median
3e-16): a handful of poorly constrained intervals keep the gain test from
ever reaching 0.99. The fixture (simulated, near noise-free) keeps
improving to iteration ~50.

### Q1: the qp weight fix

| | fixture | slice | 32 stations | whole array |
| --- | ---: | ---: | ---: | ---: |
| MSE_test(D_T)/MSE_test(D) − 1 | +6.9e-10 | +7.3e-10 | −3.4e-9 | +8.2e-9 |
| MSE_val ratio − 1 | +6.5e-11 | −7.3e-9 | +2.0e-10 | −5.1e-9 |
| valid-gain fraction | equal | equal | equal | equal |
| iterations to the gain criterion (R vs R_T) | 55 / 55 | 91 / 91 | > 300 / > 300 | > 300 / > 300 |
| products D_T vs D, max (all pairs / observed) | 1.5e-7 / 1.3e-7 | 1.9e-4 / 4.4e-6 | 1.1e-2 / 3.0e-4 | 3.2e-3 / 8.4e-4 |
| products R_T vs R, max (all pairs / observed) | 4.8e-16 / 4.8e-16 | **1.9e-4** / 6.3e-16 | 1.1e-2 / 5.4e-5 | 3.2e-3 / 5.9e-4 |
| R settled to (last max product change) | 3.3e-16 | 1.1e-14 | 2.3e-4 | 1.7e-4 |
| residual RMS ratio D_T/D (slice) | | 1 + 4.8e-10 | | |

**Answer.** Correcting the qp weights does not change the held-out error
(|Δ| ≤ 8e-9 relative everywhere), the valid gains or the iteration count;
it moves the iterate at the cap by up to 8e-4 in the observed products of
a few array intervals and leaves the converged products unchanged where R
converged (fixture 5e-16, slice 6e-16 on observed pairs). As frozen (all
pairs) the clause "R_T and R agree to the precision R settled" **fails** on
the slice (1.9e-4 against 1e-14); the post-hoc diagnostic `-05` traced this
to 26 intervals with only two observed baselines, whose third product the
data do not constrain (training χ² identical to 16 digits). Under
amendment 2 (observed pairs) it passes on the fixture and the slice and is
**undecidable** on 32 stations and the array, where R has not settled
(R_T − R 5.4e-5 and 5.9e-4 against R's own per-iteration change 2.3e-4 and
1.7e-4; medians 1.3e-16). Held-out margin, valid fraction: pass on all
four.

### Q2: the stop criterion

As frozen, the selection rule on the slice's validation MSE picked
**cap-8** (−6.9e-5 relative, the fewest iterations within δ = 1e-4), and it
fails the confirmation on the fixture (MSE_test +3.9e-3) and on the array
(+1.1e-3): **no default change**. The rule "fewest iterations within δ on
one data set" structurally favours the least adaptive candidate; the
slice's held-out error happens to be lowest at 5–8 iterations (the solve
slightly over-fits there), which a fixed cap exploits and other data sets
punish.

The criteria, post hoc (iterations; MSE_test relative to D):

| Criterion | fixture | slice | 32 stations | whole array |
| --- | --- | --- | --- | --- |
| D: gain 1e-7, 0.99, cap 50 | 50; 0 | 50; 0 | 50; 0 | 50; 0 |
| gain 1e-7 uncapped | 55; −7.6e-8 | 91; −7.1e-8 | > 300; +4.4e-6 | > 300; −6.7e-7 |
| gain 1e-5 | 37; +1.9e-6 | 45; +2.5e-8 | > 300; +4.4e-6 | 205; −6.4e-7 |
| product 1e-3 | 21; +5.8e-5 | 7; −2.0e-4 | 33; −1.6e-7 | 35; +1.9e-6 |
| product 1e-4 | 31; +6.9e-6 | 29; −9.1e-8 | 167; +3.4e-6 | 83; −5.8e-7 |
| product 1e-5 / 1e-6 | 39 / 49 | 49 / 71 | > 300 / > 300 | > 300 / > 300 |
| loss 1e-5 | 28; +1.2e-5 | 44; +2.8e-8 | 184; +3.6e-6 | 88; −6.0e-7 |
| loss 1e-6 / 1e-7 / 1e-8 | 34 / 40 / 44 | 64 / 80 / 96 | > 300 | > 300 |
| cap 12 | +4.9e-4 | −3.2e-5 | +7.4e-5 | +1.1e-4 |
| cap 16 | +1.6e-4 | −9.7e-6 | +2.5e-5 | +3.2e-5 |
| cap 24 | +2.8e-5 | −7.7e-7 | +3.2e-6 | +8.2e-6 |

Every interval-criterion stop equalled the trace replay (`matches_trace`
on all arms of all four sweeps). **Answer.** No candidate both stops
earlier than the cap of 50 on the real data and keeps the fixture: the
gauge-invariant product criterion at 1e-3 stops at 7–35 iterations within
δ on the three LUNO sets but costs 5.8e-5 on the fixture; at 1e-4 it is
within δ everywhere but runs past 50 on 32 stations (167) and the array
(83), like the loss criterion at 1e-5 (184, 88). The products change as
slowly as the gains in the few unsettled intervals (consistent with task
U2's QuartiCal #455 measurement on scan 9), and the per-interval χ² change
has the same tail. A cap of 16–24 is within δ on all four sets but is not
adaptive. The held-out floor itself may be sky-model limited on 1934−638
(task L1-M); these arms keep K/L1's model for comparability.

### Q3: Anderson acceleration

| | fixture | slice | 32 stations | whole array |
| --- | ---: | ---: | ---: | ---: |
| iterations to gain 1e-7 / 0.99: plain | 55 | 91 | > 300 (0.863) | > 300 (0.980) |
| m = 2 / 3 / 5 | 27 / 27 / 27 | 23 / 21 / 21 | 97 / 65 / 59 | 69 / 65 / 55 |
| m = 3 under the cap of 50: iterations, converged fraction (D's) | 27, 0.990 (0.984) | 21, 0.993 (0.983) | 50, 0.969 (0.603) | 50, 0.982 (0.833) |
| MSE_test(m = 3) vs D | −1.0e-7 | −8.8e-8 | +5.1e-6 | −6.1e-7 |
| A/B median solve wall D → C (s) | 0.556 → 0.388 | 0.673 → 0.306 | 6.75 → 6.29 | 20.17 → 19.82 |
| A/B median CPU D → C (s) | 0.249 → 0.173 | 0.303 → 0.159 | 26.1 → 24.6 | 76.0 → 75.5 |
| Anderson long run vs R, observed products (max / p99) | 4.5e-16 | 1.1e-13 / 3.6e-16 | 0.19 / – | 3.8e-2 / 1.0e-14 |
| Anderson long runs settled to | 3e-16 | 4e-16 | 2.4e-6 | 2.3e-10 |
| flagged gains | unchanged | unchanged | unchanged | unchanged |
| residual RMS ratio C/D | | 1 + 2.0e-7 | 1 + 1.2e-6 | 1 − 1.6e-9 |
| mixes / resets to the stop (m = 3) | 4,318 / 4,866 | 4,721 / 3,583 | 26,191 / 7,377 | 29,784 / 5,352 |

**Answer.** Anderson acceleration of the two-step map cuts the iterations
to the archived gain criterion by 2.0× (fixture), 4.3× (slice) and from
more than 300 to 55–65 on the array, without changing the held-out error
(|Δ| ≤ 5e-6, within δ). Where the plain iteration converged it reaches the
same fixed point (observed products 4.5e-16 and 1.1e-13; as frozen, all
pairs, the slice gives 2.0e-7: **fail as frozen**, the unconstrained
products again). On the array the three depths agree with each other and
have settled (2e-10 per iteration) while plain R has not; they differ from
R only in the unsettled intervals (p99 1e-14, max 3.8e-2), so "same fixed
point" is undecidable there for lack of a converged plain reference, not
contradicted. **Cost:** under the archived cap of 50 the wall drops by 30 %
(fixture) and 55 % (slice), but on 32 stations and the array Anderson
needs 59–65 iterations for the 0.99 fraction, so the solve still ends at
50 and costs the same (converged fraction 0.969 / 0.982 instead of 0.603 /
0.833):
the frozen clause "iterations to the criterion in force drop ≥ 20 % on S
and A" **fails on A as frozen** (both 50); counted to the criterion
without the cap it drops by > 78 %. Anderson under a cap of 8 is worse on
every set (fixture +9.2e-3). `freeze=1` under cap 8 changes nothing (no
interval passes the gain test within 8 iterations): null.

### Combined arm (qp_weights=transposed, anderson=3, cap 50)

Indistinguishable from `anderson=3` alone: fixture 27 iterations,
MSE_test −1.0e-7; slice 21, −8.8e-8, residual RMS ratio 1 + 2.0e-7;
32 stations 50, +5.1e-6; array 50, converged fraction 0.982, observed
products to R p99 as Anderson.

## Decision and recommendation

- **As frozen: no default changes.** Q2's selected cap-8 fails the
  fixture; Q3's cost clause fails on the array (Anderson needs 55–65
  iterations there, so the 50 cap still binds); Q1's product clause fails
  on the slice under the frozen all-pairs metric.
- **Under amendment 2 (prospective on the array)**: Q1 passes on the
  fixture and slice and is undecidable on the array (R unsettled), with
  no held-out effect anywhere; Q3's same-fixed-point clause passes on the
  fixture and slice and is undecidable on the array; its cost clause
  still fails on the array.
- Recommendation to the coordinator (see "For the coordinator"): keep the
  archived defaults; offer `RANG_SOLVE_OPTIONS=qp_weights=transposed,anderson=3`
  as the documented opt-in for anyone who needs converged gains (it turns
  the array's 83 % at 50 iterations into 98 % at the same cost, and
  reaches 0.99 at 65); revisit the default with a Python-level option
  (a binding change, outside this task) together with a cap of about 70
  under Anderson, which on the array would reach 0.99 at lower cost than
  the uncapped plain solve and at the same held-out error.

## Open items

- The product criterion and the product-distance metric should count only
  observed pairs (the trace and `solve.rs` count every pair of unflagged
  gains); changing `solve.rs` needs a new compatibility run.
- A converged plain reference on the array (thousands of iterations, or
  Anderson-seeded) to decide the "same fixed point" clauses there.
- The loss criterion lags one iteration by design; a post-update χ² would
  cost one extra pass per iteration.
- Anderson's safeguard resets often (resets ≈ mixes on the fixture);
  a residual-based restart rule tuned on the slice could cut iterations
  further, but that is a new protocol.

## Tool timings

| When (UTC) | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 09:30 | venv + `maturin develop` (setup) | 83 s | | |
| 09:38 | precondition `-01` (build, validator, K precondition, bench) | 54.5 + 12.4 + 7.4 + 5.2 s | 151 MB | all pass |
| 09:52 | compatibility `-02` (build 94 s, maturin 148 s, bench ×4, validator, K precondition) | ≈ 5 min | 151 MB | load 57; all pass |
| 10:00 | `cargo test --release --lib solve::` | 2 min 45 s build, 9.3 s tests | | 14 pass |
| 10:00 | `pytest tests/test_l5_solver.py` | 3.5 s | | 8 pass |
| 10:00–10:16 | fixture sweeps `-03`, `-06`, `-08` | 57–59 s each | 205–211 MB | load 55–60 |
| 10:01–10:14 | slice sweeps `-04`, `-07`, `-09` | 63–84 s each | 231 MB | |
| 10:01 | diagnostic `-05` (slice, R to 5,000 iterations) | 4 min 46 s | 93 MB | post hoc |
| 10:15–10:17 | confirms `-10`…`-14` | 7–35 s each | 118–506 MB | load 66–75 |
| 11:03–11:56 | 32-station sweep `-15` | 52 min 50 s | 3.5 GB | load 75–80 |
| 11:56–11:58 | 32-station confirms `-16` (images), `-17` | 1 min 59 s, 43 s | 5.8 GB | load 6–19 |
| 11:58–12:24 | whole-array lean sweep `-18` | 25 min 41 s | 10.1 GB | load 5; MemAvailable 29.9 GiB at start |
| 12:24–12:29 | whole-array confirm `-19` (3 A/B pairs, images of D and C, 59 s and 55 s) | 4 min 38 s | 12.2 GB | load 4–5; D's residual RMS 0.01642364968142557 = L1's `original` 0.016423649681425574 |
| 12:30–12:35 | `flock ~/.rang-checkall.lock bash tools/check-all.sh` (`-20.check-all.log`), head 4f9f70e | 5 min 16 s (lock wait 0 s) | | **PASS**: Rust 19 + 62 tests, clippy, fmt, ruff, pytest 578 passed, 1 skipped |
| 12:36 | `validate_core_phase2.py` `-21` on the check-all extension (Rust 1.93 build) | 2.1 s | | all 11 criteria pass |

## For the coordinator

**STATE paragraph.** L5 solver science (branch `l5-solver-science`,
[l5-solver-science.md](l5-solver-science.md)): the core solver gains
run-time options through `RANG_SOLVE_OPTIONS` (default = archived QuartiCal
0.2.7, bit-identical: task F checks at 1/4/8 threads, phase 2 validator, K
precondition, K's and L1's `original` gains hashes): the issue 452 qp weight
fix, gauge-invariant product and loss stop tests, safeguarded Anderson
acceleration of the two-step Gauss–Newton map, per-interval freeze, and a
per-iteration trace (`RANG_SOLVE_TRACE`). Measured on the fixture, the
four-station slice, 32 stations and the whole array (56 stations):
the weight fix changes no held-out error (≤ 8e-9 relative); no stop
criterion beats the 50 cap on all sets (the frozen selection, cap 8, fails
the fixture by 3.9e-3); Anderson m = 3 reaches the 0.99 criterion at 27 /
21 / 65 / 65 iterations where plain needs 55 / 91 / > 300 / > 300, with the
same held-out error and fixed point where the plain run converged, and at
the cap of 50 lifts the array's converged fraction from 0.833 to 0.982 at
equal cost. As frozen no default changes; the options are opt-in.

**Timing rows** (research/tool-timings.md): the "Tool timings" table above;
the longest are the 32-station sweep (52 min 50 s, 3.5 GB, load 75–80), the
whole-array lean sweep (25 min 41 s, 10.1 GB, load 5) and its confirm with
two array images (4 min 38 s, 12.2 GB); check-all 5 min 16 s, PASS, no lock wait.

**Binding lines.** None needed: no new module (everything is in
`core/src/solve.rs`), no `pub mod`, no C function and no extension change.
The options reach both backends through the environment variable read in
`solve::solve`. A later Python keyword (e.g. `solve_complex(...,
options="...")`) would be one string argument passed to `solve::solve_with`
after `Options::parse`; that is a binding change for whoever owns
`core/py/src/lib.rs`, `ffi.rs` and `core.py`.

**Recommendation on defaults (with numbers).** Keep the archived defaults
(as frozen nothing passes). Offer `qp_weights=transposed,anderson=3` as the
documented opt-in: on the whole array at the 50 cap it gives converged
fraction 0.982 vs 0.833, MSE_test −6.8e-7 relative, residual RMS ratio
1 − 1.6e-9, wall 19.8 vs 20.2 s; on the slice it stops at 21 iterations
(wall −55 %, MSE_test −8.8e-8). If the user wants a default change, the
candidate for a new protocol is `qp_weights=transposed,anderson=3` with a
cap of 70 (array 0.99 at 65), judged against a converged plain reference.

**Upstream QuartiCal improvement (convergence criterion).** Task U2 has
filed ratt-ru/QuartiCal#455 (QuartiCal 0.2.7 on scan 9: the iteration cap
ends the solve). Numbers to add there as a comment (from the validated
port of 0.2.7's `complex` term, not a fresh QuartiCal run, except the 50-
iteration figure on the LUNO slice, which is QuartiCal's own archived
0.9833):

> On MeerKAT L-band 1934−638 (LUNO row chunk 0, 2 × 32 solution intervals,
> stop_crit 1e-7, fraction 0.99): the fraction of gains passing at 50
> iterations is 0.983 on four stations (0.99 reached at 91), 0.603 on 32
> stations and 0.833 on 56 stations, and 0.86 / 0.98 after 300 iterations
> on 32 / 56 stations. The held-out (10 % validation, 10 % test) weighted
> MSE is within 1e-4 of a 300–500 iteration solve by iteration 12–16 and
> within 1e-5 by 24 on all three. The gains that never pass sit in a few
> poorly constrained intervals (the median baseline-product change per
> iteration is 3e-16 at 300 iterations, the maximum 2e-4). Gauge-invariant
> products G_p G_q^H converge as slowly there, so a product criterion at
> 1e-5 does not stop by 300 either. Anderson acceleration (type II, depth
> 3, applied to the pair of half and full steps, with a reset when the
> residual grows) reaches the 0.99 criterion at 21 / 65 / 65 iterations
> on 4 / 32 / 56 stations, with the same held-out error and, where the
> plain iteration converged, the same baseline products to 1e-13.
> Suggestions: count only intervals/baselines constrained by data in the
> stop fraction, report the stop reason (cap or criterion), and consider
> Anderson acceleration of the update.

**Evidence to keep.** `research/results/l5-solver-science.json` (compact
archive: every arm's metrics, the R and Anderson curves per iteration, the
confirms and the post-hoc diagnostic); run directories
`outputs/l5-solver-20261030-01` (precondition), `-02` (compatibility),
`-05` (diagnostic), `-08`, `-09`, `-15`, `-18` (sweeps, with the traces of
R, R_T and Anderson), `-10`…`-14`, `-16`, `-17`, `-19` (confirms, images)
and their `.log` files. The superseded sweeps `-03`, `-04`, `-06`, `-07`
(identical arms, fewer metrics) can be deleted.
