# Rang core, big plan task P6: frozen Python hot spots in the trend and signal tracks

Protocol frozen 2026-10-30 in the commit that adds this file, before any
code of this task exists. Status: **proposed**.
Task P6 of [simplification-review.md](simplification-review.md) (sections
2.2 and 2.4 profiles, section 3 "P6 Frozen Python hot spots", section 4
row). Under AGENTS.md this is engineering, not a scientific contribution:
the gate is that the trend and signal tracks produce the same results as
the frozen code, bit for bit.

## Rule: port, do not edit

The frozen campaign modules (`flagging_trend.py`,
`flagging_structured_proposals.py`, `flagging_signal.py`,
`flagging_signal_guard.py`, `flagging_response.py` and the rest) are not
edited: archived receipts hash them, the trend archive checks
`flagging_trend.py`'s SHA256 (`module_sha256`, `audit.module_unchanged`),
and the phase 3 comparators rely on unedited consumers. The faster
functions live in core modules; the frozen ones stay as the oracle.

## What changes

### Trend (`python/rangtoy/core_trend.py`, new)

The trend stage (`rang-core trend`) is the frozen `flagging_trend.run` on a
core-solved mirror. S1 measured 92 % of its 31.4 s in
`flagging_structured_proposals.generate_candidates` (lines 212–238): for
every time scope × row group × frequency tile, a slice sum, `np.nonzero`,
index arithmetic and a SHA256, most of them for tiles rejected by count.

1. `core_trend.generate_candidates` has the frozen signature and argument
   validation (copied verbatim) and reuses the frozen `_inputs` and
   `_row_groups` by import. Per time scope × row group it forms the TRAIN
   column counts of the group's rows once and their prefix sum, so every
   tile's sample count is `cs[first + width] - cs[first]` (integers, exact).
   The rejection counters (`raw_geometry_count`, `rejected_under_minimum`,
   then `rejected_over_budget`) are incremented in the frozen order.
2. Only admissible tiles are materialised, exactly as frozen: the same
   `np.nonzero` of the same slice, the same int64 `'<i8'` index bytes into
   SHA256, the same alias handling and collision check, the same visit
   order (scope, group, tile), and the scores from `np.mean` over the same
   gathered arrays (not from prefix sums: pairwise summation order matters
   and `balanced_rank` breaks ties on score then mask id).
3. `core_trend.run(run_dir, source_dir)` sets
   `flagging_trend.generate_candidates` to the new function, calls the
   frozen `flagging_trend.run` and restores the original in `finally`. The
   frozen `run` therefore still records and checks its own `module_sha256`
   and receipts. Opt-in until the coordinator switches
   `core_cli.py` (see "For the coordinator").

### Signal (`python/rangtoy/core_signal.py`, existing driver, behind `RANG_P6`)

The plan names `core_signal.py` as a new file; it is the existing signal
driver (377 lines). The new code goes there behind the environment variable
`RANG_P6=1` (default off: the default path runs the same frozen calls as
before, unchanged). S1 measured about 45 % of the signal stage's 35.1 s in
NumPy, mostly `np.linalg.cond` and `np.linalg.inv` on per-cell 2 × 2 gain
matrices that are properties of each gain. Candidate sites:

- (a) `flagging_signal_guard.train_signal_guard` lines 140–141:
  `cond(gains[bins, p])`, `cond(gains[bins, q])` per TRAIN cell;
- (b) `flagging_signal_guard.inverse_tangent` lines 49–51, called once per
  source template per guard: `cond` and `inv` of the same per-cell `gp`,
  `gq`;
- (c) `flagging_signal.corrected_intensity` lines 144–149 (through
  `flagging_response._correct`, inside the guard and in `_evaluate`):
  `cond` and `inv` per cell of matrices already gathered per cell.

Design: for (a) and (b), verbatim copies of `train_signal_guard` and
`inverse_tangent` in `core_signal.py` in which only the `cond`/`inv` lines
change: `numpy.linalg` is called once per referenced (bin, antenna) entry
of the gain grid and the result gathered per cell (`cond(grid)[bins, p]` is
elementwise the same LAPACK call on the same matrix). For (c), which never
sees gain indices, a replacement `corrected_intensity` computes `cond` and
`inv` once per run of bit-identical consecutive matrices (cells come in
row-major order and the solution grid is 2 × 32, so channel runs share a
gain) and expands the results; it is installed as
`flagging_response.corrected_intensity` for the duration of the run (the
frozen `_correct` looks the name up at call time) and restored in
`finally`. The downstream matmul and coefficient arithmetic keep the frozen
shapes and dtypes; only where the inverses come from changes. `numpy.linalg`
is never called on an entry the frozen code would not have inverted
(non-finite or invalid entries are replaced by the identity first, as
frozen), so no new `LinAlgError` can appear. No closed-form 2 × 2 (not
bit-identical, could flip the 1e8 threshold). A site whose share in the
baseline profile is too small to measure is left frozen and recorded.

No new Rust.

## Inputs (frozen)

- Trend: `outputs/core-trend-mirror-20261029-01` (the archived core-solved
  mirror of `outputs/tv-concurrent-wsl-20261029-01`), read only.
- Signal: `outputs/tv-next-wsl-20261029-01/inputs` and
  `outputs/core-phase3c-b-uvw-20261029-01`, read only.
- Oracles: `research/results/gain-tv-next-trend.json` and
  `research/results/gain-tv-next-signal.json` through
  `rang-core compare trend … --posthoc-slope-scale` and
  `rang-core compare signal`.
- Outputs only in fresh `outputs/p6-hotspots-20261030-NN`.

## Acceptance criteria (frozen)

1. **Trend, full identity.** `result.json` and every `checkpoint-*.json`
   of the new run are byte-equal to those of a base run (frozen
   `flagging_trend.run`) on the same mirror.
2. **Signal, full identity.** The new run's `result.json` equals the base
   run's after removing only `seconds_total` (and any wall-time or
   output-path field, listed in the results if one exists).
3. **Comparators.** `compare trend … --posthoc-slope-scale` and
   `compare signal` pass through the switched drivers (labelled trial)
   with the same exact/float/excluded counts and verdicts as through the
   base drivers.
4. **Unit tests** (`tests/test_p6_trend.py`, `tests/test_p6_signal.py`, a
   few seconds each): new against frozen functions with exact equality
   (`np.array_equal(..., equal_nan=True)`, dict equality, same candidate
   order, mask ids, scores and stats) on an archived mirror case and on
   random inputs including edge cases: empty TRAIN, a group with no
   admissible tile, all tiles over budget, duplicate geometries (aliases),
   score ties; for the signal functions singular and ill-conditioned
   gains, a NaN gain on an unreferenced entry, all-invalid cells, empty
   inputs, a guard that abstains.
5. **Frozen modules unchanged.** `git diff 4c6df23 -- python/rangtoy/flagging_*.py`
   is empty; the trend result's `module_sha256` equals the archive's.
6. **Speed (reported, claim rule of P1).** Interleaved base/new pairs, three
   each, in one script, with the 1-minute load average before and after
   every run: trend base = frozen `flagging_trend.run`, new = `core_trend.run`;
   signal base = `RANG_P6` unset, new = `RANG_P6=1`. A speed-up is claimed
   only if the new minimum is below the base minimum by more than the base
   median-minus-minimum spread; otherwise it is reported as measured, not
   claimed.
7. **Checks.** Targeted pytest and `bash tools/check-all.sh` pass before the
   final commit.

The task is reported as passed only if criteria 1–5 and 7 pass as frozen;
any failure is recorded with its numbers.

## Baseline (before any code)

Filled in by the next commit: stage walls (three repeats each, load),
hot functions and call counts from one profiled run.
