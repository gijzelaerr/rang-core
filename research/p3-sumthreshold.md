# Big plan task P3: SumThreshold and the Tricolour strategies, parallel over baselines

Branch `p3-sumthreshold` from `43dc3c7` (worktree
`~/Worktrees/rang/p3-sumthreshold`). Proposal P3 of
[simplification-review.md](simplification-review.md) (section 3 and the
section 4 table row); plan rules in [big-plan.md](big-plan.md). Status:
**implemented and measured: acceptance criteria A1–A5 hold as frozen and
A6 (checks) is recorded in section 4; the K first-pass strategy goes from
1.65 s to 0.55 s on one thread and 0.14–0.16 s on 8–16 threads (10×), with
flags bit-identical.** Sections 1–3 were committed (`130c60c`) before any
change to `core/src/sumthreshold.rs` was built or committed; the baseline
was measured on the unmodified build. Results in section 4, archive
[results/p3-sumthreshold.json](results/p3-sumthreshold.json).

Owner files: `core/src/sumthreshold.rs`, `tests/test_p3_flags.py`,
`examples/bench_p3_flags.py`, this file. The C ABI (`ffi_flag.rs`), the
extension (`core/py/src/lib.rs`), `core/src/lib.rs` and the Python wrapper
`core_flag.py` are not edited; the thread count is set with
`RAYON_NUM_THREADS` (rayon's global pool).

## 1. What changes, and why no flag can change

The port of task D ([core-d-tricolour.md](core-d-tricolour.md)) runs on a
*window* of one correlation product per baseline, `(baseline, time,
channel)`. Reading `sumthreshold.rs` at `43dc3c7`, step by step:

- `sum_threshold_flagger`: per major iteration, baseline `b` reads only its
  own plane of the running flags and writes only its own plane of `out`;
  the running flags are then ORed with `out`, again plane by plane. No
  quantity is shared between baselines (thresholds, medians, backgrounds and
  chunk ends are per baseline or constants). So each baseline can run all its
  major iterations on one worker with exactly the serial loop's operations.
- `uvcontsub_flagger`: in this port each baseline's smooth fit, median and
  MAD use only that baseline's plane, and each cycle reads and writes only
  that plane. There is **no coupling between baselines** to preserve;
  each baseline runs its cycles on one worker, in order.
- `flag_nans_zeros`, `apply_static_mask`, `flag_autos`, the executor's OR and
  override accumulation: element- or baseline-wise; the accumulation across
  steps stays serial (one step after the other).

Planned changes, none of which changes an operation on any value:

1. rayon over baselines in `sum_threshold_flagger` and `uvcontsub_flagger`
   (and the two cheap element-wise steps), per-worker scratch buffers
   (`for_each_init`) instead of per-call allocations in the box filter,
   `masked_gaussian_filter` and the flagger loops;
2. the frequency-axis box filter, which runs `box_filter_axis0` with one
   column per time row (scalar, one allocation per row), runs on groups of up
   to 64 rows transposed into the lanes of the column-wise kernel; the
   frequency-axis SumThreshold (`sum_threshold` with `axis = 1`), which ran
   `sum_threshold_axis0` once per row, does the same. Each lane performs the
   same float operations in the same order as a one-column call (columns of
   these kernels are independent: per-column medians, accumulators, cumulative
   sums and smears), so values are bit-identical and the lane loops are the
   ones the compiler vectorises (x86-64-v3 since P0);
3. no change of association, no `mul_add`, no prefix-sum rewrite of the
   running boxcar.

## 2. Inputs and baseline (run `-01`, unmodified port, measured)

- **Task D**: the four CARACAL controls exported by the oracle step,
  `outputs/core-d-oracle-20261029-01/run/<control>/arrays.npz` (140 rows ×
  4,096 channels × 4 correlations, 10 baselines, 14 times), first-pass
  (`ce9ac66a…`) and mild (`835207c3…`) strategies from
  `outputs/caracal-strategy-inputs-8f7bb363`.
- **Task K**: the fetched LUNO chunk-0 slice
  `outputs/core-k-20261030-01/fetch` decoded and split as
  `core_campaign.build_state` does (192 rows × 2,048 channels × 4, 6
  baselines, 32 times), both strategies.

Baseline run `outputs/p3-sumthreshold-20261030-01` on `43dc3c7` (extension
backend, `OPENBLAS_NUM_THREADS=1`, Rust 1.93, P0 profile; load 2.8–4.1 for
the extension bench):

- **Comparator precondition.** `run_core_flags.py` (8.7 s) then
  `compare_core_flags.py run` (0.34 s): all five task D criteria pass;
  proposals 26,692 / 26,637 / 662 / 735 equal the archive.
- **K additions.** Both arms' `additions_sha256` equal
  `core-k-luno-campaign.json` (`211a9f57…` first-pass, `0fe85944…` mild).
- **Whole strategy** (`bench_p3_flags.py run`, 3 repeats, core seconds of
  the `flag_rows` call, best and median; CPU-s of the process; peak RSS of the
  bench process):

| Input | Strategy | Best s | Median s | CPU s | Peak RSS MB |
| --- | --- | ---: | ---: | ---: | ---: |
| D control 00 operational | first-pass | 2.523 | 2.612 | 2.527 | 89 |
| D control 00 holdout | first-pass | 2.536 | 2.557 | 2.538 | 107 |
| D control 01 operational | mild | 1.447 | 1.474 | 1.448 | 107 |
| D control 01 holdout | mild | 1.380 | 1.473 | 1.381 | 107 |
| K chunk 0 | first-pass | 1.650 | 1.703 | 1.642 | 123 |
| K chunk 0 | mild | 0.953 | 0.954 | 0.954 | 123 |

- **Per step** (single-step replay: each step alone with the previous
  step's window flags as input, best of 3, minus the 0.021–0.024 s packing
  overhead of a `flag_autos`-only call, which is the serial polarised-
  intensity packing and unpacking in `ffi_flag.rs`):

| Step | D 00 op. | K first-pass | Step | D 01 op. | K mild |
| --- | ---: | ---: | --- | ---: | ---: |
| 00 flag_nans_zeros | 0.000 | 0.000 | 00 flag_nans_zeros | 0.000 | 0.000 |
| 01 apply_static_mask | 0.000 | 0.000 | 01 sum_threshold | 0.861 | 0.551 |
| 02 sum_threshold | 1.592 | 0.957 | 02 uvcontsub_flagger | 0.013 | 0.013 |
| 03 uvcontsub_flagger | 0.049 | 0.035 | 03 flag_nans_zeros | 0.000 | 0.005 |
| 04 flag_nans_zeros | 0.000 | 0.002 | 04 sum_threshold | 0.213 | 0.154 |
| 05 apply_static_mask | 0.001 | 0.003 | 05 sum_threshold | 0.167 | 0.152 |
| 06 sum_threshold | 0.318 | 0.224 | 06 sum_threshold | 0.160 | 0.150 |
| 07 sum_threshold | 0.291 | 0.174 | 07 uvcontsub_flagger | 0.015 | 0.012 |
| 08 sum_threshold | 0.250 | 0.185 | 08 flag_autos | 0.000 | 0.003 |
| 09 uvcontsub_flagger | 0.064 | 0.047 | 09 combine_with_input_flags | 0.000 | 0.002 |
| 10 flag_autos | 0.000 | 0.003 | | | |
| 11 combine_with_input_flags | 0.000 | 0.000 | | | |

SumThreshold steps are 96–98 % of each strategy; `uvcontsub` 2–5 %;
everything else is within the packing overhead. All per-step numbers of all
six inputs are in `bench-ext/bench.json`.

## 3. Protocol (frozen)

**Builds.** `cargo +1.93 build --release --offline --manifest-path
core/Cargo.toml` and `RUSTUP_TOOLCHAIN=1.93 .venv/bin/maturin develop
--release --offline` after every change, before any measurement; the
extension's SHA256 is in each bench record. The unmodified extension of
`43dc3c7` is kept outside the checkout (`~/Build/tmp/20261030-rang-p3`) for
same-load A/B runs.

**Runs** (fresh `outputs/p3-sumthreshold-20261030-NN`, every run timed,
`OPENBLAS_NUM_THREADS=1`, load recorded before and after):

1. `bench_p3_flags.py run` on D and K at `RAYON_NUM_THREADS` = 1, 2, 4, 8,
   16, 3 repeats each, extension backend; per-step replay at 1 and 16.
2. Task D chain: `run_core_flags.py` and `compare_core_flags.py run` at
   `RAYON_NUM_THREADS` = 1 and 16.
3. Same-load A/B: baseline extension and new extension alternated (three
   pairs) at 16 threads on D and K, to separate the speed-up from the load
   of the sibling sessions.
4. Throughput probe (labelled a probe, not an archive): the K slice with its
   baselines replicated ×16 (96 baselines, the copies on new antenna indices
   whose positions duplicate the originals) at 1, 2, 4, 8, 16 threads; the
   flags of every copy must equal those of its original. This is the basis
   of the whole-array extrapolation, since K's six baselines cap the K
   speed-up near 6× and D's ten near 10×.

**Acceptance (all must hold; speed is reported, not gated).**

- A1. Task D comparator `run`: all five criteria pass at 1 and at 16 threads.
- A2. Task K: both arms' `additions_sha256` equal the archive at 1, 2, 4, 8
  and 16 threads.
- A3. `bench_p3_flags.py compare` against the baseline run `-01`: final
  flags and every per-step window hash identical, for every D and K input, at
  every thread count.
- A4. Rust unit tests: the lane-grouped frequency-axis box filter and
  SumThreshold equal per-row reference calls bit for bit on random data with
  odd sizes and radii; `sum_threshold_flagger` and `uvcontsub_flagger` give
  identical output in rayon pools of 1, 3 and 8 threads.
- A5. The probe's replicated baselines carry their originals' flags.
- A6. `cargo clippy -D warnings`, `cargo fmt --check`, `ruff`, the targeted
  pytest (`tests/test_core_flag.py`, `tests/test_p3_flags.py`), then
  `bash tools/check-all.sh` once before the final commit.

Any failure is recorded with its numbers before any fix; a fix is a labelled
post-hoc step with its own run directory.

**Expected (stated before measuring).** K first-pass 1.65 s → about 0.4 s
and D control 00 2.5 s → about 0.45 s at 8–16 threads (capped by 6 and 10
baselines and by the serial 0.02 s packing); the probe near 7× on 8 physical
cores; the frequency-axis lanes alone worth 10–30 % at one thread.

## 4. What was built and what was measured (2026-10-30)

**Code** (`6b38f6c`, `core/src/sumthreshold.rs` only on the Rust side):
rayon over baselines in `sum_threshold_flagger` (each baseline runs all
its major iterations on one worker) and `uvcontsub_flagger` (each baseline
runs all its cycles; new helper `uvcontsub_cycle` holds the unchanged
body), `flag_nans_zeros` and `static_mask` split by baseline; a `Scratch`
struct per worker (`for_each_init`) carries the box filter's padded block,
accumulators, lane buffer and weights; the frequency-axis box filter and
SumThreshold run groups of up to 64 rows transposed into lanes; the boxcar
lane loops (`lanes_add`, `lanes_slide`, `lanes_drain`) work on register
blocks of 8 lanes. Three new unit tests (per-row reference equality of the
lane-grouped box filter and SumThreshold on random data with odd sizes;
identical flagger output in pools of 1, 3 and 8 threads) and
`tests/test_p3_flags.py` (identity across `RAYON_NUM_THREADS` 1, 2, 5 in
child interpreters on a 21-baseline synthetic set; replicated baselines
carry their originals' flags; the K additions against the archive).

**Development note (post-hoc, before the frozen runs; `-02`).** The first
build with scratch buffers was slower per lane than intended: `perf`
showed `box_filter_axis0_with` at 35 % of a one-thread K run, in a scalar
loop. Passing reused `Vec`s by `&mut` hides that their heap buffers do not
overlap, so LLVM did not vectorise the boxcar (the unmodified port, with
fresh local allocations, was vectorised). Wrapping the loops in slice
functions did not help; loading 8-lane blocks into arrays and storing them
back did (box filter 35 % → 15 % of samples; K first-pass CPU 1.11 → 0.73 s
at that load). `perf` on WSL did not resolve the extension's symbols
itself; addresses were mapped with `nm` (text segment offset 0x1000).

**Acceptance, as frozen.**

- A1 passed: task D comparator `run`, all five criteria at 1 and at 16
  threads (`-03/d-compare-t1`, `-03/d-compare-t16`); final flags identical
  at all 2,293,760 elements per control, proposals 26,692 / 26,637 / 662 /
  735, all 44 stage windows identical, intensity bit-equal, host inputs
  unchanged.
- A2 passed: both K arms' `additions_sha256` equal the archive (`211a9f57…`,
  `0fe85944…`) at 1, 2, 4, 8 and 16 threads, and in the A/B and probe runs.
- A3 passed: `bench_p3_flags.py compare` against the baseline `-01`: 96 of
  96 input records identical (final flags and every per-step window) across
  the five thread counts, six A/B runs (old and new extension) and five
  probe runs (`-05/compare.log`).
- A4 passed: 11 module tests (8 old, 3 new). The box-filter reference
  calls `box_filter_axis0`, which now wraps the blocked kernel, so that
  test checks lane independence rather than equality with the pre-P3
  arithmetic; the SumThreshold reference uses the unchanged
  `sum_threshold_axis0`. Equality with the unmodified port is shown by A1
  and A3.
- A5 passed: in the ×16 probe every copy's flags equal those of the
  original K rows at every thread count, and the probe's flags equal the
  unmodified extension's (`-05/compare-probe.log`, 20 of 20).
- A6 passed: clippy `-D warnings`, `fmt --check`, ruff and the targeted
  pytest (12 tests, 3.5 s); `bash tools/check-all.sh` once, overall PASS
  (root 19 and core 50 Rust tests, clippy, fmt, extension build, ruff,
  742 pytest passed in 1,401 s; log `outputs/p3-sumthreshold-20261030-06/
  check-all.log`). Its `diff-check` step saw no unstaged change (every code
  file was committed), so `git diff --check 43dc3c7 HEAD` was run
  separately: clean. The commits after it are document-only.

**Speed** (run `-03`, best of 3, core seconds of the `flag_rows` call;
baseline `-01` at load 3–4, `-03` at load 6–10):

| Input | Baseline | 1 thread | 2 | 4 | 8 | 16 | Speed-up, 16 thr | CPU s, 1 / 16 thr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D 00 operational, first-pass (10 bl) | 2.523 | 1.107 | 0.569 | 0.354 | 0.257 | 0.279 | 9.0× | 1.11 / 1.77 |
| D 00 holdout, first-pass | 2.536 | 0.986 | 0.524 | 0.328 | 0.239 | 0.212 | 12.0× | 0.99 / 1.60 |
| D 01 operational, mild | 1.447 | 0.599 | 0.317 | 0.203 | 0.148 | 0.128 | 11.3× | 0.60 / 0.92 |
| D 01 holdout, mild | 1.380 | 0.551 | 0.294 | 0.188 | 0.137 | 0.118 | 11.7× | 0.55 / 0.82 |
| K first-pass (6 bl) | 1.650 | 0.549 | 0.290 | 0.203 | 0.136 | 0.159 | 10.3× | 0.55 / 0.72 |
| K mild | 0.953 | 0.319 | 0.172 | 0.122 | 0.090 | 0.102 | 9.3× | 0.32 / 0.43 |

One thread gains 2.3–3.0× from the lanes and the vectorised boxcar;
threads add 4–8× more until the baselines run out (6 for K, 10 for D: 8
and 16 threads are equal within noise). Peak RSS of the bench process
128 MB at 1 thread, 178 MB at 16 (per-worker scratch and rayon stacks).

**Per step** (single-step replay, best minus the packing overhead,
seconds): the dominant first SumThreshold step of K first-pass 0.957 →
0.300 (1 thread) → 0.066 (16 threads); D control 00 1.592 → 0.618 →
0.166; each later SumThreshold step about 0.2–0.3 → 0.05–0.12 → 0.01–0.02;
`uvcontsub` 0.03–0.06 → unchanged on one thread → 0.005–0.016. The serial
packing and unpacking in `ffi_flag.rs` stays at 0.021–0.026 s per call,
which is now 13–20 % of the 16-thread K and D times. Every step of every
input is in the archive.

**Same-load A/B at 16 threads** (`-05`, alternated old/new, load 20–22):
K first-pass 2.50 / 0.45, 2.23 / 0.46, 2.40 / 0.46 s (5.0–5.5×); K mild
1.24 / 0.36, 1.24 / 0.42, 1.33 / 0.15 s; D control 00 operational
3.68 / 0.50, 4.07 / 0.47, 3.12 / 0.65 s (4.8–8.7×). Under that load
both builds run about 1.5–3× slower than at load 3–10, the new one more
so (it competes for the cores the siblings use).

**Throughput probe** (K ×16 = 96 baselines; labelled probe; load rose from
6.6 to 24 during the sweep, so its walls at 4–16 threads are pessimistic):

| Strategy | Old build, 1 thr (load 21) | New 1 | 2 | 4 | 8 | 16 | CPU s new 1 / 16 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| first-pass | 43.80 (34.1 CPU-s) | 10.71 | 7.50 | 5.36 | 2.43 | 3.06 | 10.5 / 13.7 |
| mild | 25.05 (20.4 CPU-s) | 8.35 | 4.71 | 3.28 | 2.18 | 1.59 | 7.0 / 7.8 |

Peak RSS 0.78–0.85 GB for 96 baselines, about (830 − 130) MB / 96 ≈ 7 MB
per baseline in the bench process (input arrays, the replicated copies,
the window, stage windows and their `astype(bool)` copies in Python, and
repeat overlap); scaled naively to 1,540 baselines that is about 10 GB.

**Against the expectation stated in section 3**: K first-pass reached 0.14–
0.16 s rather than about 0.4 s and D control 00 0.21–0.28 s rather than
about 0.45 s, because the one-thread gain from vectorisation (2.3–3.0×) was
far above the 10–30 % expected; the probe's 4.4× at 8 threads is below the
7× expected, at load 20–24 on a 16-thread host.

**Not done.** Nested parallelism inside one baseline (it helps only slices
with fewer baselines than cores, not the whole array); the serial packing
in `ffi_flag.rs` (not this task's file); further single-thread work on
`convolve_flags`, `sum_threshold_axis0` and the medians (now 7–9 % each).

## 5. For the coordinator

- **STATE paragraph.** "Big plan task P3, 2026-10-30 (implemented;
  measured): the Tricolour port runs in parallel over baselines (rayon,
  `RAYON_NUM_THREADS`) with per-worker scratch and a vectorised,
  lane-grouped box filter and frequency-axis SumThreshold; flags
  bit-identical (task D comparator 5/5 at 1 and 16 threads, K additions
  hashes at 1–16 threads, every per-step window identical to the unmodified
  port). K first-pass 1.65 → 0.55 s on one thread and 0.14–0.16 s on 8–16;
  D controls 9–12×. Whole-array chunk 0 first pass estimated about 7 min →
  25–50 s. Archive `results/p3-sumthreshold.json`."
- **Timing rows** for `tool-timings.md`: the rows of the table below.
- **Whole-array first pass for L1 (extrapolated).** L1's smoke run
  (`outputs/luno-array-campaign-20261030-00-smoke-c`, 66 baselines, 32
  integrations, 2,048 channels, the same shape per baseline as K) took
  23.2 CPU-s for first-pass and 13.8 for mild on the old port (0.35 and 0.21
  CPU-s per baseline under load; K at load 3: 0.27 and 0.16). For 1,540
  baselines: old port about 420–540 CPU-s first-pass (7–9 min, single
  thread) and 245–320 s mild. New port: 0.092–0.109 CPU-s per baseline on
  one thread (140–170 s); at 8–16 threads the probe's measured rate under
  load 20–24 (0.025–0.032 s per baseline) gives **39–49 s first-pass and
  about 25 s mild**, and a quiet host at 6–7× about 22–26 s first-pass. Add
  the serial packing, which scales with cells: about 5 s at 1,540
  baselines (0.021 s per 6 baselines).
- **Memory at the whole array (for P5 and L1).** The port's window is
  re + im float32, about 0.8 GB at 1,540 baselines, plus bool planes of
  about 100 MB each for the running flags and each step's result.
  `core_flag.flag_rows` allocates the stage windows (one byte per window
  cell per step: 12 × 1,540 × 65,536 ≈ 1.2 GB for first-pass), returns
  them as `stages[i].astype(bool)` (a second 1.2 GB), and the intensity
  window (8 bytes per cell ≈ 0.8 GB); `core_campaign.tricolour_checks`
  uses the stages (monotone check), so L1 cannot simply pass
  `want_stages=False`. The probe's 7 MB per baseline in the bench process
  (section 4) suggests about 10 GB for a whole-array call through the
  current Python wrapper.
- **Autocorrelations.** If chunk 0 carries autocorrelation rows, the
  window has 1,596 rather than 1,540 baselines (about 3.6 % more work);
  the extrapolation above scales accordingly.
- **For P7** (owner of `ffi_flag.rs`): the packing loop (polarised
  intensity per cell) and the row unpacking are serial and are now 13–20 %
  of a 16-thread call on these slices; they split by row ranges the same
  way.
- **Upstream observations.**
  - RATT (Tricolour, `ratt-ru`): in Tricolour 0.2.1 `tricolour/flagging.py`
    (sdist in `outputs/core-d-20261029-01/pypi/sdist`), `_box_gaussian_filter`
    filters the frequency axis one row at a time (`for i in
    range(data.shape[0]): _box_gaussian_filter1d(data[i], …)`, lines
    461–463) and `_sum_threshold` with `axis == 1` calls `_sum_threshold1d`
    once per row (lines 724–727), while the time axis is processed in
    256-column blocks. Tricolour already parallelises over baselines through
    its dask chunks, so only the rows-as-lanes grouping could be news
    upstream; in the port it gave 2.3–3.0× on one thread. Not measured in
    Tricolour itself (Numba may vectorise differently), so not reproduced on
    the latest release and **not filed**; reproducing it would mean timing
    `sum_threshold_flagger` on 0.5.0-dev with and without the grouping.
    Issues #110 and #111 (U1) are unaffected.
  - RATT (`caracal-pipeline`: CARACal, Stimela): nothing new.
  - Non-RATT, not reported by decision: LLVM in rustc 1.93 did not
    vectorise lane loops over the heap buffers of `&mut Vec` parameters
    (aliasing not provable), which is expected compiler behaviour and was
    worked around in rang; `perf` 6.18 on WSL2 did not symbolise the
    extension's samples (addresses were mapped by hand). Neither is a
    defect report.
- **Evidence to keep.** This file, `results/p3-sumthreshold.json`,
  `examples/bench_p3_flags.py`, `tests/test_p3_flags.py`; the run
  directories `outputs/p3-sumthreshold-20261030-01` (baseline), `-03`
  (frozen), `-05` (post-hoc A/B and old probe), each with the driver
  scripts that produced it under `scripts/` and its run log (`-01` also
  keeps the unmodified extension as `baseline-_core.abi3.so`; `-05/scripts/
  archive.py` writes the archive). `-00` (smoke), `-02`
  (development smokes and `perf` symbol tables) and `-04` (failed tooling)
  may be deleted.

## Timings (every tool run of this task)

Date for every row: 2026-10-30. Load is the 1-minute average.

| Tool run | Input | Wall | Peak RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `uv venv -p /usr/bin/python3.14 .venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | worktree | 0.02 s + 20.8 s | 377 MB | load 16–19 |
| `cargo +1.93 build --release --offline` core / root, `maturin develop --release --offline` | `43dc3c7` | 17.9 s, 5.9 s, 17.9 s | 386 MB | load 22 |
| bench smoke (`-00/smoke`, K only, 1 repeat, per-step) | K fetch | 10.8 s | 104 MB | additions equal the archive; layout check only |
| `run_core_flags.py` (`-01/d-port`) | D oracle arrays | 8.74 s | 98 MB | load 3.0 |
| `compare_core_flags.py run` (`-01/d-compare`) | `-01/d-port` | 0.34 s | 65 MB | pass, criteria 1–5 |
| `bench_p3_flags.py run --per-step` (`-01/bench-ext`) | D + K | 73.1 s | 127 MB | load 2.8–4.1; extension |
| `bench_p3_flags.py run` with `RANG_CORE_LIB` (`-01/bench-ctypes`) | D + K | 52.0 s | 125 MB | load 4.1–14.1; a ctypes library rebuilt by the default toolchain; slower per CPU-s than the extension under that load, not used further |
| development builds, unit tests, clippy and smokes (`-02`, post-hoc development, not results) | worktree | `cargo build` 10–18 s each, `maturin develop` 12–18 s, module tests 0.15 s, smoke benches 7–30 s, three `perf record` runs about 30 s each | 186 MB (bench) | load 15–21; every smoke identical to `-01` |
| targeted pytest `tests/test_p3_flags.py tests/test_core_flag.py` | worktree | 4.2 s (3.5 s in pytest) | 167 MB | 12 passed |
| `measure.sh` (`-03`, frozen): bench at 1, 2, 4, 8, 16 threads | D + K | 30.5, 7.4, 4.9, 3.8, 12.1 s | 131–183 MB | load 6–10; per-step replay at 1 and 16 |
| `run_core_flags.py` + `compare_core_flags.py run` at 1 and 16 threads (`-03`) | D oracle arrays | 4.92 + 0.46 s; 1.75 + 0.36 s | 102 / 148 MB | pass 5/5 both |
| A/B at 16 threads (`-03`), new | D + K | 1.64–1.68 s each | 180 MB | the three old runs **failed** (0.1 s, exit 1): the shadow package of the old extension did not resolve `core_root()`; tooling, not a result |
| probe ×16 at 1, 2, 4, 8, 16 threads (`-03`) | K ×16 + K | 64.9, 45.7, 34.0, 21.2, 20.5 s | 800–853 MB | load 6.6 → 24; old-build probe and both `compare` calls **failed** as above |
| post-hoc `-04`: the same old runs with `core/` linked | D + K | old 0.14–1.1 s (exit 1), new 2.1–2.2 s | 309 MB | **failed** again: `core_campaign.STRATEGY_DIR` resolves beside the shadow package |
| post-hoc `-05`: shadow layout with `core`, `outputs`, `research`, `data` linked (`mkold.sh`, validated first in `~/Build/tmp`); A/B three pairs at 16 threads | D + K | old 16.8–16.9 s, new 3.7–3.9 s | 126 / 181 MB | load 20–22; extension hashes `f04c2f4c…` (old) and `72ae90ba…` (new) recorded |
| `-05` old-build probe at 1 thread | K ×16 + K | 75.4 s | 624 MB | load 21–22 |
| `-05` `bench_p3_flags.py compare` (all runs against `-01`) and `compare` of the probes against the old build | bench records | 0.25 s, 0.10 s | 40 MB | 96/96 and 20/20 identical |
| archive script (scratch, not committed) | run directories | under 1 s | – | `results/p3-sumthreshold.json` |
| `bash tools/check-all.sh` (once, `-06`), code of `6b38f6c`/`3155e74` with this file's results in the tree | branch | 1,432 s (pytest 742 passed in 1,401 s) | 1.89 GB | overall PASS; load 16 → 46 (sibling sessions); later commits document-only |
| `git diff --check 43dc3c7 HEAD` | branch | under 1 s | – | clean |
