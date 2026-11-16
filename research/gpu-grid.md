# GPU gridding in GeMClean, with CPU parity (issue #12)

Branch `gpu-grid` from `origin/main` `a931b6c`. Written 2026-11-16.

**Status at freeze: proposed. Nothing here is built or measured.** This note
is committed before any code that tests it. Any later change is a dated
amendment in section 9, labelled post hoc if it could have seen a result.

## 1. Hypothesis and what is not claimed

Hypothesis: GeMClean's major cycle (degrid the model, subtract, grid the
residual) run on the RTX 4070 Ti through the GPU module of task X2 gives the
same images as the CPU path within the tolerances of section 4, and shortens
GeMClean's wall time at `-j 16`.

Not claimed: a new imaging method (the arithmetic is the CPU wgridder's,
a port of ducc0's); a gain from anything but the major cycle (the PSF, the
minor cycles and the resyncs stay on the CPU); anything about GPUs other than
this card; anything about WSClean's IDG GPU gridder, which the issue names as
the comparator but is not built here (section 6).

The ceiling, from the G1 phase times at `-j 16` (gemclean-speed.md,
`-single -wgridder-accuracy 1e-4`): major cycles are 3.18 of 10.32 s on S1,
4.71 of 14.84 s on H2 and 8.68 of 36.37 s on H3. A GPU major cycle that
took no time at all would save at most 31 %, 32 % and 24 % of the wall.

## 2. Design

**What exists.** `core/src/gpu/` (task X2, `research/x2-wgpu.md`, feature
`gpu`) ports `grid.rs`, the w-stacking gridder with a tabulated 7 × 7
kernel, to wgpu. GeMClean does not use that gridder: its major cycle runs
through `wgridder.rs` (`Prepared::residual*`: `degrid_images` then
`grid_images_from`; ducc0's polynomial ES kernel, support 4-16, w-planes).
So the grid, degrid and w-screen shaders are new; the adapter and device
(`gpu/context.rs`), the Stockham FFT (`gpu/fft.rs`, `shader::FFT`), the
buffer helpers and the f64 `sincos` are reused.

**CUDA or wgpu (a deviation from the brief, for the coordinator).** The
brief and the issue say "CUDA first, portable". The project's earlier
decision (big plan X2, recorded in x2-wgpu.md) was wgpu instead of CUDA:
Vulkan, Metal and DX12 from one source, no toolkit at build or run time,
nothing CUDA in the lock file or the wheels. The CUDA toolkit (13.4) is on
this host, but a CUDA path would add a second GPU stack to maintain beside
X2's. This note stays on wgpu, which runs on the NVIDIA card through Vulkan
(where it has `SHADER_F64`). A CUDA backend is not built; the shaders are
written so that a port is mechanical (gather, no atomics, no subgroup
operations).

**Scope.** Only `Prepared`'s three calls go to the GPU: `residual` and
`residual_sorted` (the major cycle), `vis2dirty` and `dirty2vis`. The PSF
(`vis2dirty_multi`), the predict mode, `stale_bound`, the resync and the
minor cycles stay on the CPU. The GPU is chosen per measurement
(`GridMeasurement`), not process-wide.

**Algorithm on the GPU, per call.**

1. Host, once per `Prepared` and cached: for every active visibility in the
   CPU layout's sorted order, its first taps `(iu0, iv0)` and first plane
   from the CPU's own `getpix` and `minplane`; a stable counting sort by
   (first plane, 16 × 16 tile of the shifted first tap); the offsets of each
   (plane, tile) run; the permutation between the two orders. The order of
   the CPU layout is not changed.
2. Host, per call: the CPU code forms the stored values (`values`,
   `data_value`, the shift phase and weights) and, for `dirty2vis`, the
   corrected image, exactly as now; the values are permuted to the GPU order.
3. GPU, per batch of visibilities (contiguous in the GPU order, sized by a
   device-memory budget) and per w-plane the batch touches:
   - **gridding** by gather, no atomics: one workgroup per 16 × 16 output
     tile, one invocation per cell; the visibilities of the four source tiles
     that can reach the tile and of the planes active there are read in
     chunks into workgroup memory, each evaluating its u, v and w taps once
     (the CPU's even/odd Horner polynomials, `fma` as `mul_add`); each
     invocation adds the products for its cell in a fixed order (source tile,
     plane, visibility), so the result does not depend on scheduling;
   - the inverse 2-D FFT of the grid (X2's Stockham passes; `good_size_complex`
     sizes are 2^a 3^b 5^c 7^d 11^e, all radices ≤ 16; an explicit
     `KernelChoice` with a larger prime factor is refused with an error);
   - the projection: each image pixel adds `Re(grid · screen)` with the
     plane's w-screen formed on the GPU from the CPU's screen table (f64
     `sincos` as X2; f32 as the CPU, `2π(φ - floor φ)` then `sin`/`cos`).
   - **degridding**: the image times the plane's conjugate screen placed on
     the zeroed grid, the forward FFT (conjugate twiddles), then one
     invocation per visibility of the batch active on the plane, adding its
     S × S taps to its accumulator in plane order.
   Several batches touching one plane each grid and transform their own part
   of it; the projections add up, since gridding, FFT and projection are
   linear. With everything in one batch (S1) each plane is gridded once.
4. Host: the image (gridding) gets the CPU's global corrections
   (`correct_image`); the visibilities (degridding) are permuted back and get
   the CPU's final shift phase and weight loop.

**Precision.** The GPU path runs in the measurement's precision `T`
(`-single` f32, default f64), both on one WGSL source. The coordinates and
the screen phase are formed in f64 in both, as on the CPU, so the GPU path
needs `SHADER_F64` (Vulkan on NVIDIA and AMD; not Metal, not wgpu's DX12).
f64 runs at 1/64 of the f32 rate on this card, so the f64 path may not pay.

**Memory.** Per visibility on the device: the row-channel index and the
packed first taps (8 bytes) and the value (8 or 16 bytes); per row the uvw
and the `FixW` sign; two grids for the FFT's ping-pong, the image and the
screen table. Budget `RANG_GPU_MEMORY_MB` (X2's variable), default 1024 MiB
for this path, also `-gpu-memory MB`. Over budget the visibilities go in
batches; a grid pair alone over the budget is refused. The card is shared:
at the start of this task 11,388 of 12,282 MiB were in use by other
processes, so H3 (4096², two grids of up to 4096² × 2.5 in f64) may not fit
when the card is busy; that is recorded, not worked around.

**Interface.** GeMClean: `-gpu` (major cycles on the GPU), `-gpu-memory MB`.
The flags parse and appear in the usage text with or without the cargo
feature (so `docs/cli.md` does not depend on the build); without the
feature, or without a usable adapter, `-gpu` is an error naming the cause,
never a silent CPU run. The adapter is reported in the log and the report
JSON. Configuration: `image.gemclean_device: cpu | gpu` (default `cpu`),
passed as `-gpu`. Modes that do not go through `GridMeasurement` (predict)
ignore nothing silently: `-gpu` with `-predict` is refused.

**Builds.** The feature `gpu` of `rang-core` (and `core/py`'s forwarding
feature) stays off by default; the five wheel platforms build and run
exactly as now. With the feature off the GPU code is not compiled.

## 3. Data

The archived GeMClean cases of gemclean-speed.md and g8-wheel.md, read-only:

- S1, S2, S3 (`D:\rang\outputs\20261102-gemclean\bench\data\s{1,2,3}.ms`,
  seeds in their JSON; 14.5 M visibilities, 2048²);
- H1-H4, the held-out skies (`D:\rang\outputs\20261103-gemclean-heldout\sim\data`;
  H3 at 4096²);
- the pilot-512 (`D:\rang\outputs\20261103-gemclean-heldout\real\cal.ms`,
  823,500 rows × 512 channels, 405.8 M cells; real MeerKAT data, no truth).

Settings as gemclean-speed.md: `-scale 1.5asec -weight briggs 0.5 -niter
1000000 -gain 0.1 -nmiter 1000 -abs-threshold 0.0001 -data-column DATA
-field 0`, sizes 2048² (H3 4096²), in two forms: **coarse**
(`-single -wgridder-accuracy 1e-4`) and **default** (f64, 1e-6). Pilot
settings as g8-wheel.md section 11.

## 4. Oracles and frozen tolerances

**Oracle 1, the CPU path** (the reference; it stays). Same binary, same
inputs, `-gpu` off.

**Gate 0, CPU unchanged.** `gemclean` built from `a931b6c` before any Rust
edit (native Windows, profile `gemclean`) is the baseline. The final build
with the feature off, and with the feature on but without `-gpu`, must write
byte-identical model, residual and image FITS on S1 (coarse and default) and
H3 (coarse). Existing Rust and Python tests pass with the feature off and on.

**Gate 1, operator parity** (GPU against CPU, one `Prepared`, the same
inputs). Cases: S1, S2, S3, H1-H4 and the pilot-512 at their image sizes,
model = the final CPU GeMClean model of that sky. For `residual` (image and
misfit) and for `dirty2vis` (visibilities) separately:

| precision, accuracy | max \|GPU − CPU\| / max \|CPU\| | misfit \|Δq\| / q |
| --- | ---: | ---: |
| f64, 1e-6 | ≤ 1e-9 | ≤ 1e-9 |
| f32, 1e-4 | ≤ 1e-5 | ≤ 1e-5 |

Why: f64 differs from the CPU only in summation order, FFT algorithm and
`sincos` (X2: about 1e-15 of the peak); 1e-9 is far above that and three
orders below the gridder's 1e-6 accuracy. f32 rounds at about 6e-8 per
operation and the CPU's own f32 is not exact either; 1e-5 is a tenth of the
coarse gridder's accuracy, so the GPU's difference from the CPU is at most a
tenth of the error both already accept. The table is also reported in image
units (µJy/beam) against the 100 µJy threshold.
Plus determinism: GPU images and visibilities bit-identical over three
repeats in fresh processes, and between one batch and a forced small budget
(several batches).

**Gate 2, end to end** (full GeMClean runs, `-gpu` against the CPU, same
binary, `-j 16`). Component picks may diverge once residuals differ by
rounding, so the bounds are G1's (gemclean-speed.md), on the inner field
(central 2N/3), on S1-S3, H1-H4 in both forms:

- restored image: rms of GPU − CPU ≤ 0.1 σ (σ the sky's Briggs image noise)
  and largest difference ≤ 100 µJy;
- exact Q/Q_truth changes by ≤ 1e-3; false flux by ≤ 1 mJy; flux-weighted
  source recovery by ≤ 1e-3; peak of the exact inner residual by ≤ 10 µJy
  (`examples/gemclean_bench_compare.py score`).

Pilot-512 (no truth): restored rms of the difference ≤ 0.1 σ (σ the CPU
residual's inner rms), largest difference ≤ 100 µJy, total model flux within
1e-3 relative, major cycles reported.
Reported, not gated: whether the component lists are identical, and the
largest residual difference over the peak.

**Oracle 2, WSClean** (end to end). WSClean 3.7 built for this CPU
(`rang-wsclean-native:3.7`, as gemclean-speed.md). The GPU run's scores
against the truth (Q/Q_truth, false flux, recovery, exact inner peak) are set
beside the CPU GeMClean run's and WSClean's; Gate 2 bounds GeMClean GPU
against GeMClean CPU, whose comparison with WSClean is on record, so the GPU
path inherits it. WSClean's archived scores are not re-used for timing.

## 5. Cost measures and the decision rule

Native Windows for every GeMClean arm (WSL has no usable adapter; X2 and
TS-P1 T5). The gemclean-speed walls are from WSL and are not pooled with
these. Arms, interleaved, `-j 16`, three repeats each, under the heavy lock
held exclusive per run: GeMClean CPU coarse, GeMClean GPU coarse, GeMClean
CPU default, GeMClean GPU default, on S1, H2, H3; WSClean `minres` at
`-mgain 0.8` and `0.9` (in WSL, Docker, the same session; gemclean-speed
picked these as WSClean's best). The pilot: one run each of GeMClean CPU and
GPU coarse, if the card's free memory allows.

Measured per run: wall (process start to exit), peak host memory (Job
Object working set on Windows; GNU time in WSL), GPU memory (peak of
`nvidia-smi` memory.used during the run minus before, sampled at about
5 Hz, best effort, and the bytes the GPU path allocates), the phase times
from the log and the GPU path's own timings (upload, compute, download).
Before each GPU run `nvidia-smi` must show at least the budget plus 256 MiB
free; otherwise the run is **void** (starved, not a miss), recorded, and
retried later.

Decision, read from these numbers only:

- **Failure**: Gate 0 or Gate 1 fails on any case, or Gate 2 on any sky in
  either form. `-gpu` stays refused (the flag errors "not validated"), the
  code stays behind the off-by-default feature for the record, and the
  result is written as a failure.
- **Speed option kept** (opt-in, default off; no novelty): Gates 0-2 pass
  and the median paired wall saving of GPU against CPU, same form, is at
  least 10 % on at least two of S1, H2, H3 in at least one form, with no
  cell (sky × form) slower than its CPU arm by more than 2 %. 10 % because
  repeats spread up to 7.7 % on this host (G1); the ceiling of section 1
  leaves room for it.
- **Null**: Gates 0-2 pass but the saving rule is not met. `-gpu` stays,
  labelled experimental and not faster; the owner decides whether to keep
  it.
- **Novelty against WSClean** (AGENTS.md) only if, in addition: GPU
  GeMClean is at least 1.5 × faster than the faster WSClean `minres` arm on
  each of S1, H2, H3, at Q/Q_truth no worse by more than 1e-3 and false flux
  no worse than WSClean's, **and** its peak host memory is no larger than
  WSClean's. GeMClean's memory is 3-5 × WSClean's today and the GPU path
  does not change the host-side data, so this is expected not to be met;
  stated here before any run.

## 6. Not done here

- WSClean with IDG on the GPU (the issue's comparator): not built in the
  oracle container; listed for a later task.
- macOS, DX12 and AMD adapters: no `SHADER_F64` on Metal or wgpu's DX12, so
  the path refuses them; not tested.
- The PSF, the predict mode and the resync on the GPU.

## 7. Stages and stop rules

1. Gate 0 baseline saved before any Rust edit.
2. Implement; Rust tests: host transcription of the new index schemes, the
   GPU gridding and degridding against the CPU on small random cases
   (skipped without an adapter), determinism, batching.
3. Gate 1. If it fails, fix bugs in the port only (no tolerance changes),
   at most three rounds; then stop and record the failure.
4. Gate 2, then the timing runs. Timing holds the exclusive lock for one run
   at a time; a queued exclusive ticket is withdrawn after about 10 minutes
   at the head of the queue and retried later.
5. Record every arm, void run and miss in section 8 and the archive
   `research/results/gpu-grid.json`.

## 8. Measured results

Runs 2026-11-16 on this host (Windows 11, 16 threads, RTX 4070 Ti 12 GB, Vulkan, NVIDIA
driver 621.01, `SHADER_F64` yes). Outputs: `D:/rang/outputs/20261116-gpu-grid` (`base/`,
`gate0-9ad7e75-{cpu,gpu}/`, `gate1/`, `gate2/`, `timing/`, `wsclean/`). Binaries: baseline
`gemclean` from `a931b6c` (sha256 `ee933fff…`), and from the library at `9ad7e75` the feature-off
`gemclean` (`c434075a…`), the feature-on `gemclean` (`b9348d49…`) and `gpu_grid_parity`;
Gates 1 and 2 ran on those. The final build at `ac69867` (the command line's flag handling and
adapter line, a type alias; feature off `40f5869e…`, feature on `184b1adc…`) was checked again:
Gate 0 byte-identical (18 of 18 files) and its `-gpu` S1 coarse run byte-identical to the
`9ad7e75` GPU run's FITS. Gates 0-2 ran as shared jobs at `-j 8`
(images do not depend on the thread count); budget 4096 MiB unless stated, with 0.9-1.1 GB
of the card in use by others before each run (`gate1/*.gpu`). Archives:
[results/gpu-grid-gate1.json](results/gpu-grid-gate1.json),
[results/gpu-grid-gate2.json](results/gpu-grid-gate2.json),
[results/gpu-grid-gate2-pilot.json](results/gpu-grid-gate2-pilot.json); scripts:
[results/gpu-grid-scripts/](results/gpu-grid-scripts/).

### 8.1 Gate 0, CPU unchanged: **pass**

S1 coarse, S1 fine and H3 coarse with the feature-off build and with the feature-on build
without `-gpu`: model, residual and image FITS byte-identical to the `a931b6c` baseline (18 of 18),
at `9ad7e75` and again at `ac69867`.
The Rust tests pass with the feature off (quick check) and on (section 8.5).

### 8.2 Gate 1, operator parity: f64 **pass**; f32 **fails as frozen**; f32 passes amendment 9.3 on the seven skies, fails it on the pilot

GPU against CPU on one plan, model = the CPU GeMClean model of the sky. "res." is the
major cycle's residual image, its difference over the CPU residual's peak (100 µJy on the
skies, 3 mJy on the pilot) and in µJy; "misfit" is |Δq|/q; "d2v" the visibilities of
`dirty2vis`, over their peak. Amendment 9.3: (a) the residual difference over the dirty
image's peak; (b) the GPU's error against the f64 reference over the CPU's (µJy, CPU / GPU).

| sky | form | grid, supp, planes | res. | µJy | misfit | d2v | frozen | 9.3 (a) | 9.3 (b) | µJy vs f64 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| S1 | coarse | 4752², 5, 6 | 4.8e-4 | 0.048 | 8.5e-9 | 2.5e-7 | FAIL | 5.0e-8 | 1.20 | 0.089 / 0.107 |
| S2 | coarse | 4752², 5, 6 | 4.2e-4 | 0.042 | 6.1e-9 | 2.5e-7 | FAIL | 4.4e-8 | 1.09 | 0.078 / 0.085 |
| S3 | coarse | 4752², 5, 6 | 5.8e-5 | 0.006 | 3.5e-9 | 2.3e-7 | FAIL | 5.7e-8 | 1.26 | 0.012 / 0.016 |
| H1 | coarse | 3388², 6, 7 | 2.7e-4 | 0.027 | 4.1e-9 | 3.3e-7 | FAIL | 3.2e-8 | 0.92 | 0.152 / 0.140 |
| H2 | coarse | 4752², 5, 7 | 1.3e-4 | 0.013 | 4.7e-9 | 2.5e-7 | FAIL | 6.4e-8 | 1.22 | 0.017 / 0.021 |
| H3 | coarse | 6776², 6, 8 | 2.8e-4 | 0.028 | 5.9e-9 | 3.3e-7 | FAIL | 2.9e-8 | 1.18 | 0.089 / 0.105 |
| H4 | coarse | 4752², 5, 6 | 1.5e-4 | 0.015 | 2.2e-9 | 2.4e-7 | FAIL | 5.6e-8 | 1.17 | 0.023 / 0.027 |
| pilot | coarse | 6776², 6, 31 | 8.5e-5 | 0.256 | 2.2e-9 | 5.7e-7 | FAIL | 2.1e-7 | **4.73** | 0.056 / 0.264 |
| S1 | fine | 4752², 7, 8 | 4.3e-12 | 4e-10 | 7.4e-15 | 3.3e-13 | pass | | | |
| S2 | fine | 4752², 7, 8 | 4.2e-12 | 4e-10 | 2.0e-14 | 3.4e-13 | pass | | | |
| S3 | fine | 4752², 7, 8 | 1.0e-12 | 1e-10 | 2.2e-15 | 2.6e-13 | pass | | | |
| H1 | fine | 4752², 7, 9 | 5.5e-12 | 6e-10 | 1.8e-14 | 2.3e-13 | pass | | | |
| H2 | fine | 4752², 7, 9 | 2.1e-12 | 2e-10 | 7.4e-15 | 2.4e-13 | pass | | | |
| H3 | fine | 7200², 8, 11 | 7.4e-12 | 7e-10 | 3.4e-14 | 3.7e-13 | pass | | | |
| H4 | fine | 4752², 7, 8 | 1.2e-12 | 1e-10 | 5.2e-15 | 2.6e-13 | pass | | | |

- **f64** passes on all seven skies with three orders to spare (bound 1e-9).
- **f32** fails the frozen bound everywhere. Under amendment 9.3 it passes (a) everywhere
  (≤ 2.1e-7 of the dirty peak) and (b) on the seven skies (0.92-1.26 × the CPU's own f32
  error), but **fails (b) on the pilot**: 0.264 µJy against the CPU's 0.056 µJy (4.7 ×). The
  pilot is the only case gridded in several batches in this table (three per call, 302,978,293
  active visibilities over a 4096 MiB budget), but batching alone does not explain it: S1
  coarse in five batches per call (500 MiB) is as close to the f64 reference as in one
  (0.107 µJy in both). Its 31 w-planes against 6-8 on the skies may; not diagnosed further.
- **Determinism**: GPU residuals and visibilities bit-identical within a process (every
  case) and over three fresh processes (S1 coarse and fine: one hash each). Batching
  (amendment 9.1): S1 coarse at a 500 MiB budget (five batches per call) gives
  bit-identical `dirty2vis` visibilities and a different residual hash, with the same
  difference from the CPU (4.81e-4 of the peak, against 4.81e-4 in one batch). S1 fine does
  not fit 500 MiB (the two grids alone need 788 MiB) and is refused, as designed.
- Operator times inside these runs (shared host, 8 CPU threads, warm GPU call): the
  residual (degrid + grid) took 0.80-1.31 s on the GPU against 1.51-2.45 s on the CPU in f32,
  1.97-3.42 s against 2.48-4.12 s in f64; the pilot's 15.7 s against 33.5 s. The GPU plan's
  host setup (GPU order of the visibilities) adds 1-6 s once.

### 8.3 Gate 2, end to end: **pass** on all seven skies in both forms; the pilot **fails** one bound

GeMClean `-gpu` against the CPU (the Gate 0 baseline), G1's bounds on the inner field:

| sky | form | components CPU / GPU (cycles) | image rms/σ | image L∞ µJy | ΔQ/Q_truth | Δfalse mJy | Δrecovery | Δpeak µJy | pass |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| S1 | coarse | 85368 / 85339 (5/5) | 9.7e-3 | 6.0 | 1.8e-6 | 0.043 | 3.9e-6 | 0.68 | pass |
| S2 | coarse | 90861 / 90924 (5/5) | 2.4e-2 | 30.8 | 1.1e-6 | 0.012 | 6.0e-6 | 1.83 | pass |
| S3 | coarse | 45818 / 45788 (4/5) | 1.1e-2 | 5.8 | 6.2e-6 | 0.020 | 1.2e-5 | 0.06 | pass |
| H1 | coarse | 88584 / 88483 (6/6) | 8.7e-3 | 6.4 | 1.8e-5 | 0.000 | 1.6e-5 | 2.01 | pass |
| H2 | coarse | 54578 / 54654 (7/6) | 1.8e-2 | 7.0 | 1.5e-5 | 0.033 | 1.2e-5 | 0.39 | pass |
| H3 | coarse | 163175 / 163237 (7/7) | 8.5e-3 | 6.8 | 8.5e-6 | 0.001 | 1.4e-6 | 1.08 | pass |
| H4 | coarse | 55658 / 55671 (5/5) | 7.7e-2 | 31.3 | 1.1e-5 | 0.151 | 3.2e-5 | 0.67 | pass |
| S1-H4 | fine | identical counts and cycles on all seven | ≤ 5.7e-10 | ≤ 7.3e-6 | 0 | 0 | 0 | 0 | pass |

In f64 the GPU images equal the CPU's to the FITS float32 rounding (same components); in f32
the runs part at the first component picked differently and stay inside every bound, S3 and
H2 with one more or one fewer major cycle. Against WSClean (oracle 2) the GPU runs therefore
score as the CPU's (gemclean-speed.md): Q/Q_truth 1.00336-1.02541 coarse, within 2e-5 of the
CPU run on every sky.

Pilot-512 (coarse, the G7 default): restored rms of the difference 0.017 σ (σ = 1.09 mJy, the
CPU residual's inner rms; bound 0.1), total model flux 83.780 against 83.775 Jy (6.2e-5,
bound 1e-3), but the largest difference is **2.1 mJy against the 100 µJy bound: fail as
frozen**. The GPU run stopped after 4 major cycles, the CPU after 5 (58,320 against 58,369
components); the run's own threshold is 3 mJy, so the 100 µJy bound, written for the
simulated skies' 100 µJy threshold, is 30 times tighter than the pilot's stopping rule.
That is a reading, not an amendment. Its major cycles took 65.9 s on the GPU against 99.3 s
on the CPU (one cycle fewer; shared host, `-j 8`).

### 8.4 Timing (exclusive, `-j 16`): **not run**

The plan ([timing_plan.txt](results/gpu-grid-scripts/timing_plan.txt): S1, H2, H3 × coarse,
fine × CPU, GPU × 3 repeats, interleaved; WSClean `minres` at `-mgain` 0.8 and 0.9 × 3 in WSL)
ran its drivers from 17:07 to 18:25. No run started:
- **The host never went exclusive.** An IDLE 4-slot, 10 GB hold of another task (E2-A
  scoring, pid 62604, "using ~0.0 cores") held the shared lock throughout, beside other
  shared jobs. Each exclusive ticket was withdrawn after 10 min at the head of the queue, as
  the brief asks: GeMClean 4 times (`timing/withdrawn.txt`), WSClean 4 times
  (`wsclean/withdrawn.txt`). The lock stops backfilling only after a head ticket has waited
  15 min, so a ticket withdrawn at 10 min cannot drain the host; the two rules do not compose.
- **The card was taken.** From about 18:05, 10,868 of 12,282 MiB were in use by another
  process (a resident model server), below section 5's 4096 + 256 MiB: one GPU arm was
  recorded void (`timing/void.txt`) and every later GPU arm would have been.
- The drivers were stopped at 18:25; no ticket of this task is left in the queue.

What is known about cost comes from the shared `-j 8` runs of Gates 1 and 2 and is not
a timing result: end to end the GPU runs took 13.9-73.2 s against the CPU's 13.5-68.1 s on
the skies, slower in all seven fine runs (f64 at 1/64 of the f32 rate) and within ±7 % in
coarse; the pilot 189.5 s against 196.0 s. The GPU path's own split on S1 coarse (11 calls):
compute 2.38 s, upload 0.61 s, host 0.98 s, download 0.12 s, setup 1.20 s. Peak device
memory 588-1342 MiB on the skies, 4096 MiB (the budget) on the pilot.

### 8.5 Checks

- Rust, feature off: `tools/check_all.py --quick` (root and core tests, clippy, fmt) at
  `10bc238`'s parent; 291 core tests pass. Feature on: `cargo clippy --features gpu
  --all-targets -D warnings` clean and `cargo test --features gpu` 301 + 1 pass at `c3ceb00`,
  the GPU tests running on the RTX 4070 Ti (not skipped).
- CI: `tests` and `docs` green on `10bc238` (runs 43898387145, 43898387137) and `STATE` commit
  (43902831327, 43902831138).
- Python: `tests/test_w2_commands.py::test_the_gemclean_device_reaches_gemclean`, the
  environment registry and docs tests pass; `docs/cli.md` regenerated.

### 8.6 Outcome

Under section 5 as frozen: **Failure** (Gate 1 fails in f32; Gate 2 fails on the pilot's
L∞ bound). `-gpu` is not refused on the branch, as the Failure clause asks: it is labelled
experimental in the usage text, pending the coordinator's decision on amendment 9.3. No speed
result: the timing did not run (8.4). No novelty claim.

Not checked: WSClean was not run in this session (the oracle comparison is inherited through
GPU ≈ CPU and gemclean-speed.md); WSClean with IDG; the pilot in f64; pytest against an
extension built with the feature; Gates 1 and 2 at `-j 16` (they ran at `-j 8`; the images do
not depend on the thread count); `-gpu` with several channels or polarisations (refused);
macOS, DX12, AMD; the full `check_all` (left to the coordinator's merge check).

## 9. Amendments

**9.1, 2026-11-16, before any GPU run (not post hoc; seen: nothing measured).**
Gate 1's determinism clause said the GPU images are bit-identical "between
one batch and a forced small budget". That cannot hold for the design of
section 2: a plane touched by several batches is transformed once per batch
and the projections are added, and a sum of transforms does not round as the
transform of the sum. Amended: GPU results are bit-identical over three
repeats at a fixed budget; degridding (each visibility sums its planes in
order, the grids are the same in every batch) is bit-identical across
batchings; gridding across batchings must meet Gate 1's tolerance against the
CPU, and its difference from the one-batch result is reported.

**9.2, 2026-11-16, before any GPU run (not post hoc).** Since G7
(`research/g7-defaults.md`) GeMClean's default is already the coarse form
(`-wgridder-accuracy 1e-4`, single precision). Section 3's "default (f64,
1e-6)" form is therefore run as **fine**, `-wgridder-accuracy 1e-6` (double
precision, chosen by the accuracy); "coarse" is the shipped default and is
passed as `-single -wgridder-accuracy 1e-4` explicitly. Nothing else changes.

**9.3, 2026-11-16, post hoc (seen before writing: Gate 1 on S1 in both forms, with a
double-precision reference; nothing else of Gate 1, nothing of Gate 2 or the timing).**
As frozen, Gate 1 **fails in single precision**: on S1 coarse the GPU residual differs from
the CPU's by 4.8e-4 of the CPU residual's peak (0.048 µJy; bound 1e-5). In double precision
S1 fine passes (4.3e-12, bound 1e-9). The as-frozen verdict stands: the outcome under
section 5 is **Failure**.
Why, as far as seen: the residual's peak (100 µJy, the threshold) is about four orders below
the data's own scale, and f32 rounding scales with the data. Against the CPU path in double
precision with the same kernel and grid, the CPU's own f32 residual is off by 8.9e-4 of the
residual peak (0.089 µJy) and the GPU's by 1.07e-3 (0.107 µJy); `dirty2vis` (2.5e-7) and the
misfit (8.5e-9) pass. So the bound was normalised by the wrong peak; this is not a port bug,
and no fix rounds are spent on it.
Amended single-precision measure, reported beside the frozen one for the coordinator to
accept or not: (a) max |GPU − CPU| of the residual ≤ 1e-5 × the peak of the dirty image of
the same plan (model none), and (b) max |GPU − f64 reference| ≤ 2 × max |CPU − f64
reference|, the reference being the CPU path in double precision with the same kernel and
grid. Both can fail. Double precision keeps the frozen bound.
Section 7 says to stop after a Gate 1 failure. Gate 2 and the timing are run all the same,
labelled post hoc: the brief asks for them, and Gate 2's bounds (µJy, σ, scores) do not use
the normalisation that failed. They cannot change the frozen outcome.
