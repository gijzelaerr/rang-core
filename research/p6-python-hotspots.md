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

## Baseline (before the frozen measurement)

Host: Ryzen 7 7700X, 8 physical cores, 16 threads, 30 GiB, shared with
sibling sessions (P4, P10, the whole-array campaign); 1-minute load 20–45
throughout, so every wall below is inflated against S1's (load 0.4–4.6).

Stage walls, `rang-core trend` / `rang-core signal` on the frozen inputs
(`/usr/bin/time`, `outputs/p6-hotspots-20261030-02`, run against the
working tree while this task's code was being written; failures as
frozen):

| Stage | Repeat | Exit | Wall s | User s | Peak RSS MB | Load before → after |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| trend | 1 | 1 | 89.86 | 47.65 | 344 | 31.4 → 32.2 |
| signal | 1 | 0 | 59.23 | 51.23 | 834 | 32.2 → 26.0 |
| trend | 2 | 1 | 68.19 | 46.69 | 341 | 26.0 → 28.3 |
| signal | 2 | 1 | 0.21 | 0.45 | 38 | 28.3 → 28.3 |
| trend | 3 | 1 | 84.77 | 48.16 | 340 | 28.3 → 30.7 |
| signal | 3 | 0 | 93.42 | 57.98 | 828 | 30.7 → 31.6 |

All three trend runs computed to the end and then failed the frozen
`flagging_trend.run` audit (`runtime_unchanged`): its `source_receipts`
hash every `python/rangtoy/*.py`, and this task's files were being created
during the runs. Signal repeat 2 failed on a half-written `core_signal.py`
(`NameError`). Lesson, applied below: measured runs only from a committed,
unchanging tree. The earlier `-01` failed for every run (`cargo` not on
`PATH` for the root crate's build-on-import). Neither changes the
baseline's use (stage cost and the profile); the frozen A/B is separate.

Hot functions (cProfile, one run each; `-03` signal, `-04` trend; cProfile
inflates Python-call-heavy code):

| Stage | Function | Calls | Cumulative s (of total) |
| --- | --- | ---: | ---: |
| trend | `flagging_structured_proposals.generate_candidates` | 56 (7 cases × 4 patterns × 2 modes) | 105.4 (of 121.4) |
| trend | inside it: `np.nonzero` / SHA256 | 1,338,344 / 1,329,225 | 5.4 / 1.6 |
| trend | `flagging_balanced.balanced_rank` | 84 | 8.6 |
| signal | `flagging_signal_guard.train_signal_guard` | 35 | 68.5 (of 85.2) |
| signal | `flagging_influence.anchored_response` (Rust eigen; P4's) | 9,069 | 34.7 |
| signal | `np.linalg.cond` | 192 | 19.6 |
| signal | `flagging_signal.corrected_intensity` (via `response._correct`) | 61 | 14.1 |
| signal | `flagging_structured_proposals.generate_candidates` (via `prospective.make_shortlist`) | 4 | 6.8 |
| signal | `flagging_influence.training_normals` | 70 | 6.9 |
| signal | `np.linalg.inv` | 122 | 2.2 |

One mirror case: TRAIN 140 rows × 4,096 channels, 73,720 TRAIN cells,
budget 1,474; per call 39,600 raw geometries, 15,687 under the minimum,
179 over budget, **23,734 admissible**, 405 aliases, 23,329 distinct
candidates (sizes 8–1,450, median 36).

## Design deviations (2026-10-30, after the baseline, before the frozen measurement; criteria unchanged)

1. **Trend.** S1's premise that most tiles are rejected by count is wrong:
   60 % are admissible, so prefix-sum counts alone (the first
   implementation, committed nowhere; profiled in `-04`) only took the
   trend stage from 121 to 103 s under cProfile: the time is in
   materialising, hashing and scoring 23,734 admissible tiles per call, 56
   calls. Added, each bit-identical by construction and by test:
   (a) the geometry (admissible tiles, sorted indices, mask ids, aliases,
   counters) depends only on TRAIN, times, antennas, window, widths,
   budget and minimum count, so it is built once per distinct input (key:
   SHA256 of those inputs; one entry kept) and reused by the eight calls
   per case; (b) the indices of every tile of one width come from one
   `np.nonzero` of the group's rows and a stable sort by tile (row-major
   order kept); (c) the elementwise score terms are computed once over the
   concatenated indices; (d) the per-candidate means: segments of at most
   128 values (NumPy's pairwise block size; most candidates) are summed
   together by an emulation of NumPy's float64 `pairwise_sum` (plain loop
   below 8, eight accumulators to 128) in which a step a segment does not
   take is masked out, never added as zero; the emulation is checked
   bitwise against `np.mean` on every length 1–128 once per process and
   abandoned for plain `np.mean` if it disagrees; longer segments call
   `np.mean` on their slice. The returned index arrays are copies, so a
   caller cannot alter the cache.
2. **Signal.** One helper serves all three sites: `cond`/`inv` once per run
   of bit-identical consecutive matrices (the protocol's per-(bin, antenna)
   gather for (a) and (b) would need the gain indices, which `inverse_tangent`
   does not receive; runs give the same elementwise-identical LAPACK calls
   on fewer matrices). The ports of `train_signal_guard`, `inverse_tangent`
   and `corrected_intensity` are checked to be the frozen source with only
   `np.linalg.cond(` → `_cond(` and `np.linalg.inv(` → `_inv(` changed (AST
   comparison in `tests/test_p6_signal.py`).
3. **Signal, extra site.** The profile shows the signal stage also spends
   6.8 s in `generate_candidates` through `prospective.make_shortlist`;
   with `RANG_P6=1` the ported function is installed there too
   (`core_trend.ported_candidates(prospective)`).
4. **Signal switch.** `core_signal.run` gains `ported=None` (None reads
   `RANG_P6`), so the coordinator's switch is one argument in
   `core_cli.signal`.
5. **Criterion 2 wall-time fields.** Besides `seconds_total`, the signal
   result carries per-solve `seconds` inside the metrics and
   `acceptance_digest_core`, a SHA256 over the acceptance records that
   include those `seconds`; both differ between any two runs. They are the
   wall-time fields the criterion excludes; the acceptance records are
   compared without their `seconds`. A profiled pair (`-03`) differed in
   exactly these 11 fields and nothing else.
