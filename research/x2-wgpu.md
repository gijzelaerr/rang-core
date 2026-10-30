# Big plan task X2: the w-stacking gridder and its FFT on the GPU through wgpu

Protocol frozen 2026-10-30 on branch `x2-wgpu` (from `origin/main`
`3b875e0`), before any GPU code was written. Status at freeze:
**proposed**. Task X2 of [big-plan.md](big-plan.md) ("GPU gridder and FFT
through `wgpu` behind a feature, after P2 and X1; measured against the task
C/I/K comparators on the RTX 4070 Ti from native Windows, no CUDA
toolkit"), following the GPU paragraph of
[simplification-review.md](simplification-review.md) section 3 (P2) with the
cross-platform decision of the plan (wgpu, Vulkan/Metal/DX12, instead of
cudarc/CUDA). An optimisation of an existing port, not a scientific
contribution under AGENTS.md: the result must be the same images within task
A's frozen tolerances, and only then is the speed reported.

## What is ported (fixed before code)

The CPU gridder of P2 ([p2-gridder.md](p2-gridder.md), `core/src/grid.rs`)
in this order: one serial pass over (row, channel) for WSClean's counters
and the placement of each sample (cell, sub-cell kernels, layer), a stable
counting sort by w-layer, then per layer: gridding of the dirty image and the
PSF with the 7 × 7 oversampled Kaiser–Bessel kernel, a 2-D unnormalised
backward FFT of each grid (`rustfft`, exact padded size), the projection
with the w-phasor `exp(-2πi w (n−1))` into a term image, and the ordered sum
of the term images over layers; then `1/image_weight`, the kernel correction
(type-III DCT), the trim to the image size and the PSF normalisation.

On the GPU (new module tree `core/src/gpu/`, cargo feature `gpu` of
`rang-core`, off by default):

1. **Gridding** of every layer: a gather, one invocation per (layer, grid
   cell), which adds the contributions of the samples whose 7 × 7 footprint
   covers the cell. No atomics (WGSL has no floating-point atomics, and
   atomics would make the sum order nondeterministic). The samples of each
   layer are sorted stably by cell on the host, so each invocation reads, for
   each of the 7 kernel rows, one contiguous run of samples.
2. **FFT** of every grid: a mixed-radix Stockham autosort transform written
   in WGSL (radix passes of 2, 3, 4, 5, 7, 8, 11, 13, 16 as generic radix-R
   DFTs, twiddles from a host-computed table of `exp(+2πi q/N)`), rows then
   columns, same sign and no scaling as the CPU (`FFTW_BACKWARD`). The exact
   padded size is kept (616 = 2³·7·11 for the 512² images, 1232 = 2⁴·7·11 for
   the whole-array image). Sizes with a prime factor above 16 are refused
   with an error (none of the comparator inputs has one). Crates evaluated:
   none on crates.io provides a maintained wgpu FFT in f64; `vkfft`-style
   bindings need a native library outside wgpu, so the transform is written
   here.
3. **Projection, w-correction and the layer sum**: one invocation per pixel
   computes the phasor of each layer (the `sqrt_lm` table and `−2πw` per layer
   come from the host, computed by the CPU code) and adds the terms into two
   accumulators in ascending layer order, as the CPU does.
4. The accumulated padded images are copied back; `1/image_weight`, the
   kernel correction, the trim and the PSF normalisation run on the host
   through the CPU code (O(pixels), unchanged).

Stays on the host and unchanged: the counters and placement pass and the
counting sort (the same `grid.rs` code, split into functions so the GPU path
can call it; the CPU path calls the same functions in the same order), plus
the per-layer sort by cell (new, GPU path only). **Deviation from the task
brief** (which limits `grid.rs` to the device dispatch): besides the dispatch,
`grid.rs` gets `pub(crate)` visibility on `Sample`, `Gridder` and their
helpers and one extracted function for the counters/placement pass and the
counting sort, and the normalisation tail of `Gridder::invert` becomes its
own function; no arithmetic is moved or reordered, and criterion 6 gates this
with bit-identity against the unedited `3b875e0` build.

**Where the GPU arithmetic differs from the CPU's** (documented, not hidden):
(a) the order of the additions into one grid cell (CPU: the samples' row-
channel order across the footprint; GPU: kernel row, then source cell, then
the samples' row-channel order within the cell); (b) the FFT algorithm
(Stockham with generic radix DFTs against rustfft's mixed-radix plans);
(c) `sin`/`cos` of the phasor (WGSL has no f64 trigonometry: a Cody–Waite
reduction by π/2 and fdlibm's kernel polynomials, against the platform libm
on the CPU); (d) the driver's shader compiler may contract `a*b + c` into
fused multiply-adds. None of these touches the counters, which stay the CPU's.

Runtime selection: `RANG_GRIDDER_DEVICE=cpu|gpu` (default `cpu`) and
`RANG_GRIDDER_GPU_PRECISION=f64|f32` (default `f64`), read by
`python/rang/core_grid.py` (also `device=` / `precision=` arguments). A GPU
request on an extension built without the feature, or on a host without a
usable adapter, raises a RuntimeError naming the cause; there is no silent
fallback to the CPU. The adapter, device and compiled pipelines are created
once per process and reused. Adapter choice: a discrete GPU first, then an
integrated one, never a `DeviceType::Cpu` adapter (Microsoft Basic Render
Driver on Windows, lavapipe/llvmpipe on Linux), so a software rasteriser can
neither be measured as "the GPU" nor turn a skip into a slow run;
`RANG_GPU_ADAPTER` (substring of the adapter name) can override. On macOS
(Metal) Apple GPUs have no f64, so only the f32 path could run there; macOS
is not tested here.

Dispatch granularity: Windows (WDDM) resets a device whose single dispatch
runs for more than about 2 s (TDR), and f64 runs at 1/64 of the f32 rate on
this card, so every dispatch covers one layer (gridding, projection) or one
radix pass of one batch (FFT), and each layer batch is its own submission.

Memory: the GPU on this host is shared. At 20:17 CAT `nvidia-smi` showed
11,343 of 12,282 MiB in use, about 10 GB of it by a resident Ollama
`llama-server.exe` (not ours; not stopped), so about 0.9 GB is free, not the
10 GB the task brief expected. Layers are therefore processed in batches
under a device-memory budget (default 512 MiB, `RANG_GPU_MEMORY_MB`), each
batch uploading only its own samples; the batch size does not change the
arithmetic (layer order and every sum are the same), which criterion 5
tests (the forced one-layer batch is set by `RANG_GPU_LAYERS_PER_BATCH=1`,
which caps the batch below what the budget allows).

Build plumbing: `wgpu` 30.0.1 and `pollster` 0.4.0 (to block on wgpu's
futures), both exact pins from crates.io, optional dependencies of
`rang-core` enabled by its feature `gpu`. The PyO3 crate `core/py` needs a
forwarding feature (`gpu = ["rang-core/gpu"]`) and the binding; both are
coordinator lines (the report lists them verbatim). Optional dependencies
are locked whether or not the feature is on, so `core/Cargo.lock` (and
`core/py/Cargo.lock` once the forwarding feature exists) gain wgpu's tree;
the feature-off `--locked` builds must keep passing on both platforms.

## Precision policy (frozen)

Precondition (measured before the freeze with a throwaway probe,
`C:\Users\gijsm\Build\tmp\20261030-rang-x2\probe`, wgpu 30.0.1, NVIDIA driver
621.01): the RTX 4070 Ti's **Vulkan** adapter exposes
`Features::SHADER_F64` (as does the AMD integrated GPU's); wgpu's **DX12**
adapters on this host do not expose it. A WGSL f64 kernel (multiply, add,
`round`, `floor`, `sqrt`, f64↔i32 conversion) agreed with the CPU to 2.5e-15
relative. Vulkan limits: max buffer 4 GiB − 1, max storage binding 2 GiB − 4.

Decision: **the GPU path is f64** (grids, kernels, twiddles, phasors and
accumulators in f64; the f32 samples and weights are widened exactly, as on
the CPU). The archived comparators then apply as frozen, and only the f64
path may stand in for the CPU path. It requires an adapter with
`SHADER_F64` (on this host: Vulkan; in wgpu 30 not DX12, and never Metal).

An **f32 path** (the same shaders instantiated with f32: grids, FFT,
kernels, twiddles, accumulators f32; the phasor with WGSL's f32 `sin`/`cos`)
is built and measured as a separate, experimental path. It is not gated, may
not replace the CPU path, and its verdicts under task A's tolerances are
recorded comparator by comparator. Prediction (stated before measuring):
f32 passes the C and K pixel tolerances (8.8e-6 of the peak, 2.8e-6), but
the task I response-fraction class (1.6e-7 absolute, CPU margin 1.31e-7) is
at risk.

## Inputs and comparators

Inputs copied read-only from the WSL archive to
`C:\Users\gijsm\Build\tmp\20261030-rang-x2\inputs\` (4.8 s, 532 MB) and
junctioned into the worktree's ignored `outputs/`:
`tv-next-imaging-wsl-20261029-01`, `core-c-20261029-01`,
`core-k-20261030-01`, `p2-gridder-20261030-01/inputs-{c,k}`,
`luno-solve-20261029-02/inputs/ANTENNA`.

- **Task C**: `examples/run_core_gridder.py` (fifteen archived jobs) and
  `examples/compare_core_gridder.py` against the archived WSClean FITS
  (`tv-next-imaging-wsl-20261029-01/images`), unedited, with the device set
  by the environment.
- **Task I**: `examples/run_core_imaging.py`, unedited (both comparisons and
  the side-effect audit), device by the environment.
- **Task K** (deviation, decided before the freeze): P2's frozen comparator
  `bench_p2_gridder.py k-replay` decodes `core-k-20261030-01/fetch/` (725 MB
  of fetched bytes), which is no longer in the archive (only `flags/`,
  `gains/`, `images/` and the JSON receipts remain). The inversion is
  therefore replayed from P2's dumped `core_grid.invert` arguments of the six
  arms (`p2-gridder-20261030-01/inputs-k`, dumped by P2's baseline replay
  whose image hashes equal the archive), and everything after the inversion
  is P2's comparison with P2's tolerances: `core_campaign.image_metrics`
  with the archived model flux, peak pixel, imaged cells, the gridder
  counters, the pixels against the archived FITS and the residual-RMS calls
  of the archived hypotheses (`examples/bench_x2_gpu.py k-inputs`). Not
  re-exercised: decoding, gain application and imaging weights, which are
  CPU code X2 does not touch. The `dirty_sha256` it records is of the
  float32 cast of the image (not the archive's definition) and is not
  compared.
- **Whole-array case**: DF2a's synthetic whole-array input
  (`bench_df2.array_case`, seed 2030: 53 MeerKAT stations, 41,340 rows × 640
  channels, 23.8 M gridded), saved in P2's input layout by
  `bench_x2_gpu.py array-inputs`, imaged with the w-stacking gridder at
  1024² and 1.5″ (padded 1232², 64 layers). There is no archived w-stacking
  image of it; its reference is the CPU path on this host.
- **Timing inputs**: the C (15) and K (6) gridder inputs of P2 and the
  whole-array case.

Precondition on native Windows, CPU path, extension built from `3b875e0`
with Rust 1.93.1 MSVC (`outputs/x2-20261030-01`):

| Check | Result |
| --- | --- |
| C driver + comparator (`c-cpu`) | criteria 1–3 pass on all fifteen jobs; dirty L∞ 6.11e-7 of peak, PSF 4.17e-7, WCS equal: P2's figures exactly; 4.8 s + 1.1 s |
| I driver (`i-cpu`) | both comparisons pass, 0 failures; response fraction 1.3120924657883393e-07 (P2: 1.312092e-7), template flux 1.43e-7, PSF 8.9e-8, inputs and git status unchanged; 5.7 s |
| K inputs replay (`k-cpu`) | pass, 0 failures; dirty pixels 3.19e-8 of peak, PSF 2.98e-8 (FITS rounding, P2's figures), dirty metrics 1.15e-14 relative, PSF metrics 4.4e-16, counters exact; 2.7 s |

## Acceptance criteria (frozen)

Gated, for the **f64** GPU path (`RANG_GRIDDER_DEVICE=gpu`, precision f64):

1. **Task C**: `run_core_gridder.py` criteria 1–3 on all fifteen jobs and
   `compare_core_gridder.py` against the archived WSClean FITS: dirty L∞ /
   archived peak ≤ 8.8e-6, PSF L∞ ≤ 2.8e-6, WCS keys equal.
2. **Task I**: `run_core_imaging.py` passes both comparisons under the
   frozen classes of `core_imaging.classify_replay` (task A's tolerances);
   the response-fraction margin is reported. The side-effect audit's inputs
   clause is gated, its git clause reported (as in P2).
3. **Task K** (`bench_x2_gpu.py k-inputs`, six arms): P2 criterion 3 as
   frozen there (pixels vs archived FITS dirty ≤ 8.8e-6 of peak and PSF ≤
   2.8e-6; counters to 1e-9 relative and exact where exact; dirty metrics to
   8.8e-6 relative, PSF metrics to 2.8e-6 absolute; peak pixel and imaged
   cells equal; residual-RMS calls unchanged).
4. **Agreement with the CPU path on the same host** (float64 images,
   `bench_x2_gpu.py compare`): for every C and K timing input and the
   whole-array case, max |GPU − CPU| ≤ 1e-10 of the CPU image's peak for the
   dirty image and the PSF (above DF2a's ~1e-11 legitimate-reordering floor,
   far below task A's tolerances); the eight counters exactly equal.
5. **Determinism**: the f64 GPU images are bit-identical across three
   repeats in fresh processes and between the default layer batching and a
   forced one-layer batch (`RANG_GPU_LAYERS_PER_BATCH=1`), on the C and K
   timing inputs.
6. **CPU path unchanged**: every C, K and whole-array CPU image, at 1 and
   16 threads, of the final build with the feature off **and** of the final
   build with the feature on (`device=cpu`) is bit-identical to the baseline
   images of the unedited `3b875e0` extension, saved before any Rust edit
   (`outputs/x2-20261030-01/baseline/`, extension `_core.pyd` SHA256
   `51ae3668…`); the existing Rust and Python tests pass with the feature
   off and on.
7. **Correctness tests**: Rust unit tests check the Stockham index scheme on
   the host against a direct DFT (factors 2, 3, 4, 5, 7, 8, 11, 13, 16 and
   1), and, where an adapter exists, the GPU FFT against `rustfft` (to 1e-12
   of the largest output) and a small GPU inversion against the CPU (to
   1e-12 of the peak).
8. **Clean failure**: `tests/test_x2_gpu.py` skips (does not fail) without
   the feature or without an adapter, and checks the RuntimeError of a GPU
   request in that case; on WSL (no Vulkan loader) it skips.
9. **Builds and checks on both platforms**: on native Windows, `cargo build`
   of `core/` with and without `--features gpu`, `cargo test --features gpu`
   and `python -m rang.check` pass; on WSL (Linux), `cargo build` and
   `cargo test --features gpu` of `core/` pass with the GPU tests returning
   early (no adapter) rather than failing, and `bash tools/check-all.sh`
   prints `overall: PASS` with the feature off.

Reported, not gated:

10. **The f32 path**: criteria 1–4 run the same way with
   `RANG_GRIDDER_GPU_PRECISION=f32`; each verdict is recorded.
11. **Speed**: per image (median of three repeats, each a fresh process),
    for CPU at 1 and 16 threads, GPU f64 and GPU f32, on the C, K and
    whole-array inputs: wall per image including transfers, and the GPU
    path's breakdown (host preparation, upload, compute, download, host
    finish), so the figure excluding transfers is compute alone; process
    CPU seconds; peak RSS; GPU memory (peak increase of `nvidia-smi`
    memory.used, sampled as fast as `nvidia-smi` answers, about 5–10 Hz,
    best effort, and the bytes the path allocates); the
    first-call cost (adapter, device and shader compilation) separately.
    The end-to-end C, I and K driver walls on both devices. The host's other
    load (the WSL VM's load average, sampled before and after each process)
    is recorded; nothing is built or edited in the worktree during a task I
    run (its side-effect audit compares git status before and after); the
    CPUs and the GPU are shared with sibling sessions and
    the resident Ollama server, so walls are upper bounds.

Failures are recorded as frozen; anything after the freeze that is not in
this protocol is labelled post hoc.
