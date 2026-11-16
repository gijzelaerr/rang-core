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

None yet.

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
