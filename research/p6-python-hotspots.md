# Rang core, big plan task P6: frozen Python hot spots in the trend and signal tracks

Protocol frozen 2026-10-30 in the commit that adds this file, before any
code of this task exists. Status: **implemented; measured: criteria 1–5 and
7 pass as frozen (trend result and checkpoints byte-equal, signal result
equal apart from wall-time fields, both comparators pass with identical
counts through the switched drivers); trend 3.1× faster (minima 34.5 →
11.2 s, claimed under the P1 rule at load 7–42); signal not faster in the
frozen wall-time A/B (minima 31.9 vs 33.0 s, not claimed) although its
`cond`/`inv` CPU drops from 13.1 to 0.8 s per run (post-hoc diagnostic)**.
Results archive: [results/p6-hotspots.json](results/p6-hotspots.json).
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

## Results (frozen measurement, `outputs/p6-hotspots-20261030-06`, head `0c074e6`, clean tree)

Interleaved pairs (pair 1 base first, pair 2 new first, pair 3 base
first), `/usr/bin/time`, the tree committed and unchanged during the
runs. Trend arms: `examples/bench_p6_hotspots.py trend frozen|ported`
(frozen `flagging_trend.run` / `core_trend.run`); signal arms:
`rang-core signal` with `RANG_P6` unset / `RANG_P6=1`. The load fell from
42 to 7 during the hour, so pair 1 is the most loaded.

| Stage | Arm | Walls s (pairs 1, 2, 3) | Min / median s | User s | Peak RSS MB | Load before (1 min) |
| --- | --- | --- | --- | --- | ---: | --- |
| trend | base | 124.89, 56.21, 34.48 | 34.48 / 56.21 | 51.0, 51.3, 35.0 | 340–341 | 34.5, 22.0, 11.6 |
| trend | new | 30.00, 17.23, 11.17 | 11.17 / 17.23 | 17.9, 15.6, 11.4 | 409–416 | 42.6, 23.9, 8.5 |
| signal | base | 67.68, 31.91, 37.68 | 31.91 / 37.68 | 52.6, 39.3, 41.8 | 827–829 | 39.3, 17.6, 7.3 |
| signal | new | 34.19, 32.97, 34.64 | 32.97 / 34.19 | 37.4, 36.6, 38.0 | 868–872 | 29.1, 19.4, 8.9 |

- **Criterion 1 (trend identity): pass, 3 of 3.** `result.json`,
  `config.json` and the seven `checkpoint-*.json` are byte-equal between
  the arms of every pair (`identity-trend-N.json`).
- **Criterion 2 (signal identity): pass, 3 of 3.** `result.json` equal
  after removing `seconds_total`, the per-solve `seconds` and
  `acceptance_digest_core` (design deviation 5). **The default path is
  unchanged against the pre-P6 driver** (`-10`, post hoc): baseline
  `-02` signal repeat 1 imported the original `core_signal.py` (it started
  more than two minutes before repeat 2, which failed on the half-edited
  file); its `result.json` equals `-06` pair 1's base *and* new arms under
  the same rule (`identity-signal-pre-p6-vs-{base,new}-1.json`).
- **Criterion 3 (comparators): pass.** Every arm of every pair: trend
  (`--posthoc-slope-scale`) passed, 875 exact, 168 float, 1 excluded, with
  the same frozen-slope failures as before (the known rounding-level
  reference slopes of [core-phase3-trend.md](core-phase3-trend.md),
  accepted by its post-hoc rule); signal passed, 261 exact, 208 float (max
  rel 1.74e-11), 4 difference, 12 reported, 15 excluded. Identical counts
  in both arms. **Labelled trial (`-09`, switch applied to `core_cli.py`,
  reverted after, `git status` clean again):** `rang-core trend` through
  `core_trend.run` 31.7 s, `rang-core signal` with `ported=True` 34.2 s
  (load 30–33); both comparators pass with the same counts; the
  side-effect audits report inputs unchanged and git status unchanged; the
  trial trend result equals base pair 1's in every key except
  `configuration.runtime_receipts`, whose only differing entry is
  `core_cli.py` (the switch itself); its `module_sha256` is the archive's
  `3c578c5e…`; the trial signal result equals base pair 1's under
  criterion 2.
- **Criterion 4 (unit tests): pass.** `tests/test_p6_trend.py` (13 tests:
  random states, aliases and ties, window exclusions, empty TRAIN, all
  over budget, validation errors, the switch, the geometry cache, bitwise
  segment means, an archived mirror case) and `tests/test_p6_signal.py`
  (11 tests: corrected intensity in both call shapes with singular,
  signed-zero, ill-conditioned (1e9) and NaN gains, all-valid,
  all-invalid, empty and one-cell inputs; inverse tangent including its
  1e8 refusal; one LAPACK call per run; the three ports verbatim apart
  from `cond`/`inv` by AST comparison; the switch), about 5 s together.
- **Criterion 5 (frozen modules): pass.** `git diff 4c6df23 --
  python/rangtoy/flagging_*.py` is empty; `module_sha256` as archived.
- **Criterion 6 (speed).** Trend: margin 34.48 − 11.17 = 23.31 s against a
  base spread of 21.73 s: **claimed, 3.1× (minima), 3.3× (medians), user
  CPU 3.1×**; peak RSS +70 MB (the geometry cache and the concatenated
  indices). Signal: the new minimum is 1.06 s *above* the base minimum:
  **not claimed**; peak RSS +41 MB.
- **Criterion 7:** see "Checks".

### Post-hoc diagnostic: where the signal time went (`-08`, labelled post hoc)

The frozen A/B contradicted the profiles (`-03`, `-07`: `cond` 13.5–19.6 s
of 60–85 s, ported 1.0–1.1 s), so
[signal_timed.py](results/p6-hotspots-scripts/signal_timed.py) (it wraps
`np.linalg.cond`, `np.linalg.inv`, `anchored_response`,
`training_normals`, `core_solve` and the shortlist's `generate_candidates`
with wall and process-CPU timers and calls
`core_signal.run(..., ported=False|True)`) ran two pairs at load 25–38:

| Arm | Wall s | CPU s | `cond` calls / wall s / CPU s | `inv` wall s / CPU s | `anchored_response` CPU s |
| --- | ---: | ---: | --- | --- | ---: |
| base | 91.0, 98.2 | 55.9, 55.0 | 192 / 21.7, 23.9 / 11.8, 11.8 | 2.3, 2.9 / 1.33, 1.40 | 20.2, 20.4 |
| new | 71.2, 65.8 | 41.2, 39.0 | 192 / 1.3, 1.4 / 0.72, 0.71 | 0.22, 0.20 / 0.10, 0.10 | 20.1, 19.3 |

So the port removes about 12 CPU-s of `cond`/`inv` and about 3 CPU-s of
candidate generation per signal run, as designed, and at load 25–38 the
stage is 20–30 s faster. In the frozen A/B the base's own CPU varied from
39 to 53 s between pairs for identical work (the per-matrix LAPACK calls
are the most load-sensitive part: wall about twice CPU here), and at load
7–19 the difference was inside the noise. The signal speed-up is
therefore measured but not claimed. The remaining signal cost is
`anchored_response` (Rust eigensolver, about 20 CPU-s; P4's).

## Checks

Targeted pytest (`tests/test_p6_trend.py tests/test_p6_signal.py
tests/test_core_cli.py`): 32 passed. `bash tools/check-all.sh` on the
final tree: **PASS** (all fifteen steps; pytest 584 passed, 1 skipped, in
4,280 s at load 27 rising to 99 with sibling suites running); log
`outputs/p6-hotspots-20261030-10/check-all.log`. After it passed, only
research and evidence files changed (this document, the results archive,
the scripts directory); the code is commit `0c074e6`, the one measured.

## Scripts

Every measurement was driven from
[results/p6-hotspots-scripts/](results/p6-hotspots-scripts/) (copied
from the session scratchpad, unchanged, run from the worktree root with
`.venv`): `baseline.sh` (`-01`, `-02`), `profile.sh`, `trend_run.py` and
`stats.py` (`-03`, `-04`, `-07`; `-04` and `-07` used the same commands
inline), `stats_case.py` and `quick_case.py` (one-case development timing;
`quick_case.py` is left in its last, ported-only state), `ab.sh` (`-05`
failed, `-06`), `signal_timed.py` (`-08`), `trial.sh` (`-09`),
`archive.py` (writes `results/p6-hotspots.json`), `jdiff.py` and
`trend_trial_cmp.py` (result diffs), `micro.py` (`cond`/`inv` per cell
against per run on 70,000 synthetic matrices: 49.0 → 5.0 ms and 9.9 → 2.1
ms at load 13), `negzero.py` (signed zeros, below).

Signed zeros (post hoc, `negzero.py`): on this build `np.mean` of
all-`-0.0` segments of length 1–130 is `+0.0` (the reduction starts from
`+0.0`), `segment_means` agrees, and `np.maximum(-0.0, 0)` returns `+0.0`,
so the scores cannot carry `-0.0`. The run-time probe
(`_short_sums_are_exact`) does not itself feed signed zeros.

## For the coordinator

**STATE paragraph.** Task P6 (frozen Python hot spots, branch
`p6-hotspots`, [p6-python-hotspots.md](p6-python-hotspots.md)): the trend
track's candidate generation is ported to
`core_trend.generate_candidates` (geometry built once per case by prefix
sums and one `np.nonzero` per row group, scores vectorised with a
bitwise-checked emulation of NumPy's pairwise sum), and the signal
track's `train_signal_guard`, `inverse_tangent` and `corrected_intensity`
are ported into `core_signal.py` with `cond`/`inv` once per run of
identical gain matrices. Frozen modules untouched. Trend results and
checkpoints byte-equal, signal results equal apart from wall times, both
comparators pass with identical counts through the switched drivers.
Trend 3.1× faster (34.5 → 11.2 s minimum, claimed); signal `cond`/`inv`
CPU 13.1 → 0.8 s per run but no wall gain measurable in the frozen A/B at
falling load (not claimed). Opt-in until the switch below.

**Switch lines** (verified in the labelled trial `-09`, then reverted):

```diff
diff --git a/python/rangtoy/core_cli.py b/python/rangtoy/core_cli.py
index 0f34056..ae5bdd1 100644
--- a/python/rangtoy/core_cli.py
+++ b/python/rangtoy/core_cli.py
@@ -46,7 +46,7 @@ from . import core, core_actions, core_injections, core_prospective, core_signal
 from .core_workflow import core_solve
 from .flagging_equivariance import CASES
 from .flagging_injections import PATTERNS
-from .flagging_trend import run as trend_run
+from .core_trend import run as trend_run
 from .flagging_workflow import load_state

 ROOT = Path(__file__).resolve().parents[2]
@@ -178,7 +178,7 @@ def signal(run_dir, inputs_dir, uvw_dir, iterations=50):
         run_dir,
         [inputs_dir, uvw_dir],
         lambda: core_signal.run(
-            run_dir, inputs_dir, uvw_dir, iterations=int(iterations)
+            run_dir, inputs_dir, uvw_dir, iterations=int(iterations), ported=True
         ),
     )

```

Optional, not tried here: the prospective stage (`core_prospective.run`,
about 20 s) calls the same frozen `generate_candidates` through
`flagging_prospective.make_shortlist`; wrapping its run in
`core_trend.ported_candidates(flagging_prospective)` would port it the
same way (its comparator would be the check). `core_cli.trend`'s docstring
("The frozen `flagging_trend.run`, unedited") stays true after the
switch: `core_trend.run` calls it unedited.

**Timing rows** for `tool-timings.md`: the "Timings" table below; the
headline rows are `-06` trend base/new 34.48/11.17 s minimum and signal
31.91/32.97 s minimum, load 7–42.

**Upstream observations.** RATT (caracal-pipeline, QuartiCal, africanus,
Stimela): none; this task touches only rang's own Python. Non-RATT:
NumPy's `np.mean` summation order (float64 `pairwise_sum`, block size 128,
eight accumulators) is an implementation detail, not API; `core_trend`
depends on it for the vectorised means and therefore checks it bitwise at
run time and falls back to `np.mean` if a future NumPy changes it. Not a
bug, no report. `np.linalg.cond`/`inv` on stacks of 2 × 2 matrices make
one LAPACK call per matrix (about 0.7 µs each); not an upstream issue.

**Evidence to keep.** [results/p6-hotspots.json](results/p6-hotspots.json)
(all timing rows, identity verdicts, comparator counts, the diagnostic and
the trial with its switch diff). Raw run directories (ignored):
`outputs/p6-hotspots-20261030-02` (baseline), `-03`, `-04`, `-07`
(profiles), `-06` (frozen A/B), `-08` (post-hoc diagnostic), `-09`
(labelled trial), `-10` (pre-P6 identity, check-all log); `-01` and
`-05` are failed attempts kept as frozen. Scripts:
[results/p6-hotspots-scripts/](results/p6-hotspots-scripts/).

**Open items.** (1) A low-load signal A/B (load below 2) would settle the
signal wall gain. (2) The prospective-stage port above. (3) P11 will copy
the frozen originals into core modules; the ports can then replace the
frozen consumers' imports directly instead of the attribute swap. (4) The
geometry cache keeps one entry (about 70 MB for a 140 × 4,096 case); a
whole-array state would need a size check first. (5) Add a few `-0.0`
values to the `_short_sums_are_exact` probe and to
`test_segment_means_bitwise` (hardening only; see "Scripts").

## Timings (every tool run of this task, 2026-10-30)

| Tool / input | Wall | Peak RSS | Notes |
| --- | --- | --- | --- |
| `uv venv` + `uv pip install -e .[...]` + `maturin develop --release` | about 2 min | – | background; cached wheels |
| root crate first build (`_native_library()`) | 10.3 s | – | `cargo` on `PATH` |
| baseline `-01`, trend and signal × 3 | 0.6–1.3 s each | 44–190 MB | **failed as frozen**: `cargo` not on `PATH` |
| baseline `-02`, trend × 3 | 89.9, 68.2, 84.8 s | 340–344 MB | exit 1: `runtime_unchanged` audit (files created during the runs); load 26–32 |
| baseline `-02`, signal × 3 | 59.2, 0.2, 93.4 s | 828–834 MB | repeat 2 failed (`NameError`, half-written file); load 28–32 |
| cProfile signal base / new (`-03`) | 85.2 / 60.8 s (profile totals) | – | load about 30; first signal port |
| cProfile trend frozen / prefix-sum-only port (`-04`) | 121.4 / 103.2 s | – | load 35–45; identity pass (all 9 files) |
| one case, 8 calls, frozen / ported (scratch, development) | 12.4–17.8 / 2.7–8.0 s | – | load 30–44; same results checked each time |
| pytest P6 files (development, several runs) | 3–8 s | – | |
| A/B `-05` | 0.05 s each | – | **failed as frozen**: `/usr/bin/time` cannot run shell functions (exit 127) |
| A/B `-06` (frozen measurement) | 12 runs, see Results | 340–872 MB | load 42 → 7 |
| identity and comparators in `-06` | under 1 s each | – | all pass |
| cProfile signal base / new (`-07`) | 60.3 / 44.1 s | 833 / 868 MB | load 15–22 |
| diagnostic `-08` (post hoc), 4 signal runs | 91.0, 71.2, 98.2, 65.8 s | – | load 25–38 |
| labelled trial `-09`: switched `rang-core trend` / `signal` | 31.7 / 34.2 s | 414 / 870 MB | load 30–33; comparators pass; reverted |
| `bash tools/check-all.sh` | 4,539 s | – | PASS; pytest 584 passed, 1 skipped (4,280 s); load 27 → 99 |
| `micro.py` (`cond`/`inv` per cell vs per run, 70,000 matrices) | about 1 s | – | load 13; default and one OpenBLAS thread |
| `negzero.py` (signed zeros, post hoc) | under 1 s | – | all agree |
| identity pre-P6 vs `-06` (`-10`, post hoc) | under 1 s | – | pass, both arms |
