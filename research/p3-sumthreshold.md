# Big plan task P3: SumThreshold and the Tricolour strategies, parallel over baselines

Branch `p3-sumthreshold` from `43dc3c7` (worktree
`~/Worktrees/rang/p3-sumthreshold`). Proposal P3 of
[simplification-review.md](simplification-review.md) (section 3 and the
section 4 table row); plan rules in [big-plan.md](big-plan.md). Status:
**protocol frozen (this section and sections 1–3 are committed before any
change to `core/src/sumthreshold.rs`)**.

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
