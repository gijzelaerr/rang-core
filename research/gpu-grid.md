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

### 8.4 Timing (exclusive, `-j 16`): **not run** on 2026-11-16 (run 2026-11-17: 8.7)

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
- **Second attempt, 18:40-18:57 (post hoc scope: coarse only, `-gpu-memory 1024`, the
  default, since the card had about 1.4 GB free; plan
  [timing_plan_coarse1024.txt](results/gpu-grid-scripts/timing_plan_coarse1024.txt)), after
  the IDLE hold had gone and the drivers' head-of-queue test was fixed (they had taken
  "waiting for head" of another ticket for being at the head). Again no run started: the
  WSClean ticket reached the head, passed the 15 min drain limit with a 1-slot data fetch and
  a 2-slot job of other tasks still running, and was withdrawn; the drivers were stopped at
  18:57. A shared 1-slot fetch that runs for hours keeps the host from ever going exclusive.

What is known about cost comes from the shared `-j 8` runs of Gates 1 and 2 and is not
a timing result: end to end the GPU runs took 13.9-73.2 s against the CPU's 13.5-68.1 s on
the skies, slower in all seven fine runs (f64 at 1/64 of the f32 rate) and within ±7 % in
coarse; the pilot 189.5 s against 196.0 s. The GPU path's own split on S1 coarse (11 calls):
compute 2.38 s, upload 0.61 s, host 0.98 s, download 0.12 s, setup 1.20 s. Peak device
memory 588-1342 MiB on the skies, 4096 MiB (the budget) on the pilot.

### 8.5 Checks

- `tools/check_all.py --quick` at `393ebd9` (the code of `ac69867`): **PASS** in 986 s (291 core
  tests, clippy, fmt, the extension, 518 pytest passed). Two earlier quick runs failed on
  `cargo fmt` and on the research index, both fixed. Feature on: `cargo clippy --features gpu
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
Timing, 2026-11-17 (8.7, partial, two repeats): the GPU is **not faster** at `-j 16`, 7-10 %
slower in f32 on S1 and H2 and level on H3, 18-53 % slower in f64; section 5's saving rule
is not met in either form, so the outcome stays Failure and no speed case for `-gpu` exists.

Not checked: WSClean was not run in this session (the oracle comparison is inherited through
GPU ≈ CPU and gemclean-speed.md); WSClean with IDG; the pilot in f64; pytest against an
extension built with the feature; Gates 1 and 2 at `-j 16` (they ran at `-j 8`; the images do
not depend on the thread count); `-gpu` with several channels or polarisations (refused);
macOS, DX12, AMD; the full `check_all` (left to the coordinator's merge check).

### 8.7 Timing, exclusive `-j 16`, 2026-11-17 (amendments 9.4, 9.5): **GPU not faster**

Glacier, one exclusive hold 20:32:20-20:51:35 (`heavy_lock.py run --drain 0`), binaries
`gemclean-9ad7e75-{cpu,gpu}.exe`, GPU budget 4096 MiB, outputs
`D:/rang/outputs/20261116-gpu-grid/timing-20261117b/` (per-run JSON and logs, `session.log`,
`nvidia-smi-{start,end}.txt`, `lock-{start,end}.txt`, `ollama-server.log`); archive
[results/gpu-grid-timing.json](results/gpu-grid-timing.json), scripts `session.py`,
`session_analyse.py`. Start: card 499 of 12,282 MiB, idle host 0.42 cores (60 s), so the
clean bound was 2.0 cores; end: 0.74 cores, card 10,235 MiB.
**Partial session.** At 20:45-20:46 a local Ollama client outside rang (it calls
Ollama on the quarter hours) loaded `qwen3:14b` (10 GB) onto the card
during `h3-fine-gpu-r2`: that run took 111.15 s (other CPU 2.77 cores, unclean); every later
run is unclean by the GPU-drift clause, and `s1-coarse-gpu-r3` was void, which ended the
session (9.5). So repeats 1 and 2 ran, repeat 3 and the pilot did not; 36 GeMClean arms
planned, 25 run, 22 clean (other-process CPU of the clean runs 0.84-1.67
cores; this task's own Ollama connection watcher, polling every 0.7 s from about 20:18 to
20:58, is inside the baseline and loads both arms alike).

Walls, s, medians of clean runs; saving = (CPU − GPU) / CPU per repeat pair:

| sky | form | accuracy of the GPU form | CPU | GPU | saving r1, r2 | major cycles CPU / GPU, s | GPU path / major (compute) | device MiB | host GB CPU / GPU |
| --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | --- |
| S1 | coarse (f32) | Gate 1 **fail** (4.8e-4 of the residual peak, bound 1e-5); Gate 2 pass | 10.85 | 11.84 | −9.1 %, −9.3 % | 3.12 / 3.40 | 94 % (65 %) | 758 | 2.18 / 2.18 |
| H2 | coarse (f32) | Gate 1 **fail** (1.3e-4); Gate 2 pass | 14.92 | 16.22 | −7.3 %, −10.0 % | 4.62 / 5.31 | 97 % (76 %) | 759 | 2.02 / 1.94 |
| H3 | coarse (f32) | Gate 1 **fail** (2.8e-4); Gate 2 pass | 34.79 | 34.94 | −1.0 %, +0.1 % | 8.31 / 7.96 | 91 % (72 %) | 1190 | 4.81 / 3.94 |
| S1 | fine (f64) | Gate 1 pass (4.3e-12); image = CPU | 14.63 | 19.13 | −30.4 %, −31.2 % | 5.81 / 9.18 | 101 % (88 %) | 1341 | 2.96 / 2.64 |
| H2 | fine (f64) | Gate 1 pass (2.1e-12); image = CPU | 18.67 | 28.37 | −50.5 %, −53.5 % | 7.30 / 15.41 | 102 % (92 %) | 1342 | 2.95 / 2.64 |
| H3 | fine (f64) | Gate 1 pass (7.4e-12); image = CPU | 50.80 | 59.91 | −17.9 % (r2 unclean: 51.84 / 111.15, −114 %) | 20.03 / 27.39 | 100 % (91 %) | 2360 | 5.41 / 4.59 |

- Repeat spread is small: the two clean walls of every arm agree within 2.8 %.
- **Section 5's rule, read as written: not met.** No cell saves 10 %; S1 and H2 are slower
  than their CPU arms by more than 2 % in both forms; H3 coarse is level (−0.4 %). H3 fine has
  one clean pair, so it is "not measured" under 9.4; it was 18 % slower. The session is
  partial (two repeats of three), but no third repeat could turn −7 % to −53 % pairs into a
  10 % saving.
- **Where the time goes.** The GPU path (host, upload, compute, download) takes 91-102 % of
  the GPU run's major-cycle time (over 100 % because its counters include GPU calls outside
  the log's major timer: one grid call more than there are cycles), compute alone 65-92 %, so the major cycle on the card is
  as long as or longer than the CPU's at 16 threads: in f32 by −4 % (H3) to +15 % (H2), in
  f64 1.4-2.1 × longer (f64 at 1/64 of the f32 rate). The rest of the run (PSF, minor
  cycles, resyncs, I/O) is unchanged, so (a reading) no wall saving is left to find in this design. At
  `-j 8` on a shared host (8.2) the GPU operator was faster; the reading is that at `-j 16`
  the CPU catches up.
- **Accuracy of the timed runs:** every clean run's model, residual and image FITS are
  byte-identical to the Gate 2 run of the same binary and form (CPU: the Gate 0 baseline;
  GPU: `gate2/gpu`), so the accuracy column holds for these walls. H2 coarse ran 7 major
  cycles on the CPU and 6 on the GPU, as in Gate 2.
- **WSClean 3.7** (`minres`, clean repeat 1 only; repeat 2 unclean by the GPU-drift clause,
  in brackets): S1 17.65 (18.33) s at `-mgain 0.8`, 12.69 (13.12) s at 0.9; H2 15.76 (16.31),
  16.14 (18.96); H3 40.42 (41.44), 40.55 (42.91); peak RSS 0.58 / 0.58 / 1.13 GB. The
  faster WSClean arm against GeMClean GPU coarse: S1 1.07 ×, H2 0.97 ×, H3 1.16 ×
  (GeMClean CPU coarse: 1.17 ×, 1.06 ×, 1.16 ×), at 3-4 × WSClean's memory. The novelty
  rule (1.5 × on each sky, memory no larger) is not met.
- **Not run:** repeat 3, the pilot (CPU and GPU coarse), the pilot in f64 through Gate 2;
  the post-merge build (`9606a6f` and later) was not timed and Gates 0-2 were not re-run on
  it.

Attempt 3 (`timing-20261117/`, 20:09:59-20:13:40, aborted, 9.5): the same Ollama client had
loaded the model at 20:10:23; six CPU walls and one WSClean wall, no GPU arm.

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

**9.4, 2026-11-17, the timing arm, frozen before any timed run (post hoc: Gates 0-2 and the
shared `-j 8` walls of 8.4 are known; no exclusive wall is).** The exclusive `-j 16` timing of
section 5, on glacier, run because the owner asked for it (the coordinator's reopening order,
pilot f64 through Gate 2 first, is not followed). It cannot change the outcome of 8.6
(Failure); it is a reading for the coordinator. Section 5 and `timing_plan.txt` hold, with
these deviations:

- **One exclusive hold for the whole session**, `heavy_lock.py run --drain 0 -- python
  session.py ...` ([results/gpu-grid-scripts/session.py](results/gpu-grid-scripts/session.py)),
  all arms and repeats inside it; no ticket per run, no 10-minute withdrawal.
- **Arms and order:** `timing_plan.txt` as written (S1, H2, H3 × coarse, fine × CPU, GPU ×
  3 repeats, interleaved, CPU first in r1 and r3, GPU first in r2; GPU budget 4096 MiB;
  binaries `gemclean-9ad7e75-{cpu,gpu}.exe`, sha256 `c434075a…`, `b9348d49…`, the ones
  Gates 1-2 measured), output under `timing-20261117/`. After each repeat's twelve GeMClean
  arms come that repeat's six WSClean 3.7 arms (`minres`, `-mgain` 0.8 and 0.9 on S1, H2,
  H3, `wsclean_run.sh` as written, `-j 16`), started from the same driver through `wsl -d
  Ubuntu`, not under a WSL lock of their own. Then the pilot, one run each of CPU and GPU
  coarse (`run_sky.sh`'s pilot settings, `-j 16`, 4096 MiB).
- **Warm-up, untimed, inside the hold:** every file of the four MS read once (page cache),
  one `docker run --rm rang-wsclean-native:3.7 true`, and one S1 coarse GPU run (shader
  cache, adapter). WSClean reads its MS copies from the WSL disk, GeMClean from D:.
- **Walls:** GeMClean process start to exit in a Job Object (`timing.py one`); WSClean
  GNU time's elapsed inside the container (Docker start excluded), as gemclean-speed.md.
- **Clean or not, per run** (all recorded, none dropped): other-process CPU = (host busy
  time from `GetSystemTimes` over the run − the run's own user + system time) / wall, in
  cores; the driver's 5 Hz `nvidia-smi` sampler counts as other. A run is **unclean** if
  that exceeds 1.0 core, or if the card's memory in use before the run exceeds the
  session's start by more than 512 MiB. A GPU arm with less than budget + 256 MiB free is
  **void** (section 5) and retried once at the end of the session. `nvidia-smi` (full) and
  the lock status are saved at the start and end of the session.
- **Medians:** per sky × form, the median of the paired savings (CPU − GPU) / CPU, paired
  by repeat, over the pairs where both runs are clean; walls are medians of clean runs. A
  cell with fewer than two clean pairs is "not measured". Section 5's saving rule (≥ 10 %
  on two skies in one form, no cell slower than 2 %) and novelty rule are then read as
  written, with the accuracy each form reached beside every number: f64 meets Gate 1 and
  equals the CPU image; f32 fails Gate 1, so an f32 speed gain does not make the f32 form
  acceptable.
- **GPU share:** from each GPU log, the GPU path's own time (host, upload, compute,
  download) and compute alone over the major-cycle time.
- **Accuracy of the timed runs:** their model and residual FITS hashed against the Gate 2
  runs of the same binary (`-j 8`); a mismatch is reported.

**9.5, 2026-11-17, post hoc (seen: the aborted session below; no GPU arm ran).** Attempt 3
(9.4) took the exclusive hold at 20:09:59 and was stopped at 20:13:40, in its first WSClean
arm (`timing-20261117/`, kept as recorded). At 20:10:23-20:10:32 a local client sent four
`/api/chat` requests to Ollama, which loaded `qwen3:14b` (10 GB, 100 % GPU, 15 min
keep-alive) onto the card; every GPU arm of repeat 1 was void (10,498 of 12,282 MiB used)
and every run unclean by 9.4's GPU-drift clause (`ollama-2010.txt`, `ollama-server.log`;
the same client sent a burst at 18:05). The idle host itself read 1.62 cores busy over 10 s
(0.5-1.4 cores in three later 15 s windows with WSL stopped; no user process above 0.03
core), so 9.4's 1.0-core bound sat below the floor and would have marked every run
unclean. Seen: the six CPU walls of repeat 1 (S1 10.88 / 14.55 s, H2 14.54 / 18.41 s,
H3 35.22 / 50.79 s, coarse / fine) and one WSClean wall (S1 `-mgain 0.8`, 17.51 s); they
are not pooled with the rerun. Changes for the rerun (`timing-20261117b/`), everything else
as 9.4:
- **Clean rule:** the idle baseline is measured over 60 s at the session start (and end),
  and a run is unclean if its other-process CPU exceeds max(2.0, baseline + 1.0) cores.
  The baseline is reported beside the results. The GPU-drift clause stays.
- **Pre-flight:** with less than 4096 + 256 MiB free on the card at the start, the session
  logs it and ends without timing.
- **The first void GPU arm ends the session**; no end-of-session retries. A partial
  session is reported as such and not pooled with another.
- Ollama is not stopped by this task (not its process); the rerun starts after the model
  has unloaded.

## Coordinator decision, 2026-11-16 (owner delegated)

- The frozen outcome, **Failure**, stands. The code (`core/src/gpu/wgrid.rs`, `gemclean -gpu`) stays on
  branch `gpu-grid` at `c203e02` and is **not merged**: f32 misses the frozen bound, the pilot misses Gate 2,
  and no run was faster, so an experimental flag would ship without a gain or a met tolerance.
- Amendment 9.3 is **not accepted** as a pass criterion; it stays a post hoc reading.
- wgpu instead of CUDA is accepted (X2: no toolkit in builds or wheels).
- Reopening needs, in order: the pilot in f64 through Gate 2, then the exclusive `-j 16` timing against
  WSClean on a quiet host with a free card (scripts in `results/gpu-grid-scripts/`, run with
  `heavy_lock.py run --drain 0`), under a new frozen arm. Only a speed-up at met parity would justify a merge.

## For the coordinator, 2026-11-17 (timing)

- The exclusive `-j 16` timing ran (8.7, partial: repeats 1-2 of 3, no pilot). GPU against CPU,
  same form: f32 −9 % S1, −9 % H2, −0.4 % H3; f64 −31 %, −52 %, −18 % (one clean pair). The
  saving rule of section 5 is not met; this adds a measured "not faster" to the frozen Failure.
  The f32 numbers sit beside its Gate 1 failure; only f64 has met parity, and it is the slower one.
- Reopening as the decision of 2026-11-16 put it ("a speed-up at met parity") is not supported
  on this card: the GPU path already takes 91-102 % of the major-cycle time, so a faster
  wgpu kernel, not more measurement, would be needed. Suggest closing #12 as measured, saving rule not met,
  for this design and leaving the branch parked.
- Blocker for any GPU timing on glacier: a local Ollama client outside rang sends
  Ollama `/api/chat` bursts on the quarter hours (seen 15:30-15:45, 16:00, 18:05, 20:10, 20:15,
  20:45), loading `qwen3:14b` (10 GB) for 15 minutes each. Timing needs it paused; this task
  did not touch it.
- Branch state: origin/main merged (`9606a6f`), SPDX after the MIT relicence (`gpu/wgrid.rs` held
  GPL as a wgridder child, `gpu_grid_parity.rs` MIT), quick check PASS. Not done: the full
  check, Gates 0-2 on the merged build, the pilot in f64.

## Coordinator decision, 2026-11-17

- **#12 closes for this design: the saving rule is not met.**
  - f64 passes accuracy and gives images equal to the CPU's, but on glacier at `-j 16` it is 18-52 % slower than the CPU path.
  - f32 is level to 9 % slower, and it still fails Gate 1.
  - The GPU path takes about all of the GPU run's major-cycle time, so the card does not shorten the cycle against 16 CPU threads.
- **Branch:** the code (`gemclean -gpu`, wgpu, opt-in) is not merged to main. It stays on branch `gpu-grid` at commit 93faa7b. Only this note, the timing archive and the session scripts come to main, as a negative result.
- **Not run:** the pilot, and a third repeat. A local GPU client outside rang loaded a 10 GB model onto the card every quarter hour. The two clean repeats agree within 2.8 %, so the verdict does not depend on the missing repeat.
- **Reopen only with a different design:** batched multi-visibility kernels, or CUDA, with the CPU path kept equal within a written tolerance (AGENTS.md). That would need a new proposal note.
