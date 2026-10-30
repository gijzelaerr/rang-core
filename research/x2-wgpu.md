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

**Status now: implemented and measured** (protocol commit `34d8fb7`; code
`37ec2c2`, `b88dff3`, `465d06d`; [measured results](#measured-results-2026-10-30-post-freeze)).
The f64 GPU path passes every gated comparator as frozen: task C (dirty
6.11e-7 of peak, PSF 4.17e-7, the CPU's figures to every printed digit),
task I (response fraction 1.3121e-7, 82 % of 1.6e-7, unchanged) and task K
(pixels 3.19e-8, metrics 2.3e-14, calls unchanged); against the CPU path on
the same host its images differ by at most 2.2e-15 of the peak (bound
1e-10), they are bit-identical across repeats and batchings, and the CPU
path is bit-identical to the unedited build. One frozen clause fails:
criterion 4 asked all eight gridder counters to be exactly equal, and the
eighth, the PSF normalisation (1 / PSF centre), differs by 4.4e-16
relative (the seven counters proper are exact). Speed on the RTX 4070 Ti
(f64, transfers included, per image): four-station images 0.09–0.12 s
against 0.30 s on 16 CPU threads (2.5–3.3×) and 0.80–0.82 s on one (7–9×);
the 23.8 M-visibility whole-array image 2.5 s against 3.1 s and 7.6 s, of
which 1.1 s is the CPU's own serial counters pass that both paths share
(GPU compute alone 0.8 s, 0.43 s with a 4 GiB budget). The experimental f32
path passes C and I (I with a smaller response-fraction difference, 2.9e-8,
than f64: WSClean grids in f32) and **fails K** on the residual metrics
(1.2–3.5e-5 relative against 8.8e-6), so it cannot stand in for the CPU path.

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

## Design as built (post-freeze; deviations from the frozen design are listed below)

Owner files: `core/src/gpu/{mod,context,shader,fft,invert,ffi,tests}.rs`
(feature `gpu` of `rang-core`), `core/src/grid.rs` (the split and the
dispatch), `core/Cargo.toml`, `core/Cargo.lock`, `python/rang/core_grid.py`,
`examples/bench_x2_gpu.py`, `tests/test_x2_gpu.py`, this file and
`research/results/x2-wgpu.json`. The coordinator lines (module line, PyO3
binding, forwarding feature, `core/py/Cargo.lock`) are in the last section;
without them the feature is not reachable and `tests/test_x2_gpu.py`'s GPU
tests skip.

- **Dependencies**: `wgpu = "=30.0.1"` (default features off; `std`,
  `parking_lot`, `vulkan`, `metal`, `dx12`, `wgsl`) and `pollster = "=0.4.0"`,
  both optional. Optional dependencies are locked in any case, so
  `core/Cargo.lock` gains wgpu's tree (+995 lines: naga 30.0.1, ash,
  gpu-allocator, the windows 0.62 crates, the Metal/objc2 crates for macOS);
  none is compiled with the feature off, and the feature-off `--offline
  --locked` builds pass on both platforms.
- **Context** (`context.rs`): one `wgpu::Instance` (Vulkan, Metal, DX12);
  `DeviceType::Cpu` adapters are rejected (on this WSL host the only Vulkan
  adapter is llvmpipe, so the GPU tests skip there, as the protocol
  requires); ranking discrete > integrated > virtual, then SHADER_F64
  support, then Vulkan > Metal > DX12; `RANG_GPU_ADAPTER` filters by name.
  The device takes the adapter's full limits and `SHADER_F64` when present.
  Pipelines are compiled per precision on first use inside a validation
  error scope, so a shader error is an `Err`, not a panic. One inversion at
  a time per process (mutex).
- **Host preparation** (`invert.rs`): `grid::bucket` (the CPU path's own
  counters/placement pass and counting sort by layer, unchanged), then per
  layer a stable counting sort by cell (`pack_layer`, 16 layers at a time in
  parallel with rayon): two index words per sample (`x kernel | y kernel <<
  16`, cell x), three values (the f32 weighted sample and PSF weight,
  widened exactly to f64 on the host) and `cells + 1` run offsets.
- **Batches**: layers in batches sized by the device-memory budget
  (`RANG_GPU_MEMORY_MB`, default 256 MiB) and the binding limit,
  `RANG_GPU_LAYERS_PER_BATCH` caps it. Per batch: upload, then three
  submissions each waited for (gather, FFT passes, projection), so the
  stages are timed apart. The two running sums stay on the device; one
  download at the end. The longest single submission measured is the f64
  FFT of a 32-layer whole-array batch in the post-hoc 4 GiB run, about
  0.12 s (under 0.02 s at the default budget): far from the 2 s WDDM TDR
  limit.
- **Gather** (`shader::GRID`): workgroups of 8 × 4 cells × 7 kernel rows;
  invocation (cell, j) adds, for kernel row j, the samples of the seven
  source cells of that row (one contiguous run in cell order, or seven runs
  at the wrapped edges), source cells in ascending x, samples in row-channel
  order; the seven row sums are added in row order by one invocation
  (workgroup memory and a barrier), so the result is deterministic. Per
  sample `k = ky * kx`, then `re * k`, `im * k`, `weight * k`, as the CPU.
- **FFT** (`fft.rs`, `shader::FFT`): Stockham autosort with radices 4 first,
  then 2, then odd primes ≤ 13 (616 = 4·2·7·11, 1232 = 4·4·7·11), a generic
  radix-r DFT per butterfly (the `(q s) mod r` index advanced incrementally),
  the twiddle table `exp(+2πi q/N)` computed on the host in f64; rows then
  columns, ping-pong between two grid buffers. The host transcription
  (`stockham_reference`) is the unit-tested reference of the index scheme.
- **Projection** (`shader::PROJECT`): per pixel, for each layer of the batch
  in ascending order, `phasor = sincos(two_pi_w[l] * sqrt_lm[index])` and
  `sum += re cos − im sin` for the dirty image and the PSF, at the CPU's
  `target` index; `sqrt_lm` and `−2πw` are the CPU code's values. f64
  `sincos`: `round(x · 2/π)`, Cody–Waite with fdlibm's `pio2_1`/`pio2_1t`,
  fdlibm's kernel polynomials, quadrant select; f32: WGSL `sin`/`cos`.
- **Finish**: the sums come back; `Gridder::normalise` (`1/image_weight`,
  kernel correction) and `grid::finish` (trim, PSF normalisation), the CPU
  path's functions.
- **Errors**: no adapter, no SHADER_F64 for f64, a padded size with a prime
  factor above 16, a batch over the binding limit, shader or device errors:
  `Err(String)`, raised as RuntimeError by the binding, status 3 from the C
  ABI `rang_core_grid_invert_gpu`. A GPU request on an extension without the
  feature raises RuntimeError in the wrapper, naming the feature.
- **Python** (`core_grid.py`): `invert(..., device=None, precision=None)`,
  defaults from `RANG_GRIDDER_DEVICE` / `RANG_GRIDDER_GPU_PRECISION`;
  `resolve_device`, `resolve_precision`, `gpu_compiled`, `gpu_adapter`,
  `gpu_available`. A GPU result carries `gpu`, the 14 timings of
  `Timings::as_array`.

## Measured results (2026-10-30, post-freeze)

Runs (all in the worktree's ignored `outputs/`): comparators
`x2-20261030-03` (21:48–21:49 CAT; extension SHA256 in `extension.sha256`,
built from `465d06d` plus the wiring diff below), timing `x2-20261030-04`
(22:02–22:06 CAT, same extension), post-hoc large-budget timing
`x2-20261030-05`, baseline CPU images of the unedited `3b875e0` extension
`x2-20261030-01/baseline`. The `-03` bench timings are **void**: they
overlapped a WSL build of this task (operator error; the CPU figures were
1.4–2.6× slower than in `-04`); its comparator verdicts and image hashes
stand (they do not depend on load). Archive: `research/results/x2-wgpu.json`
(from `bench_x2_gpu.py summarize outputs/x2-20261030-04
outputs/x2-20261030-01/baseline … --comparators outputs/x2-20261030-03`).
Adapter: NVIDIA GeForce RTX 4070 Ti, Vulkan, driver 621.01, SHADER_F64. GPU
memory in use before the runs: 11,248 MiB at 21:48 (the resident Ollama
server), 1,133 MiB at 22:02 (Ollama had released its model). WSL load
average 3.7–7.2 throughout (sibling sessions; the CPUs are shared).

### Gated criteria (f64 GPU path)

| # | Criterion | Result | Figures |
| --- | --- | --- | --- |
| 1 | Task C, 15 jobs, vs the archived WSClean FITS | **pass** | criteria 1–3 pass on all jobs, WCS equal; dirty L∞ 6.106e-7 of peak (8.8e-6), PSF 4.172e-7 (2.8e-6): the CPU path's figures to every printed digit |
| 2 | Task I, both comparisons | **pass**, 0 failures | response fraction 1.3120924624576702e-7 = 82 % of 1.6e-7 (CPU 1.3120924657883393e-7), template flux 1.43e-7, PSF vs fixedG0 8.9e-8, weight sums 5.8e-16, dirty pixels 6.11e-7 of peak, PSF 4.17e-7; inputs unchanged, git status unchanged |
| 3 | Task K, six arms (`k-inputs`) | **pass**, 0 failures | pixels vs archived FITS dirty 3.19e-8 of peak, PSF 2.98e-8 (FITS rounding); dirty metrics 2.3e-14 relative, PSF metrics 5.6e-16; counters exact; peak pixel, imaged cells equal; the three residual-RMS calls unchanged (null, null, null) |
| 4 | Agreement with the CPU path, float64 | images **pass**; counter clause **fails as frozen** | max \|GPU − CPU\| / peak: K 2.2e-15 (PSF 1.6e-15), C 1.2e-15 (9.4e-16), whole array 1.0e-15 (1.2e-15), bound 1e-10. Seven counters exactly equal; the eighth entry, `psf_normalization` = 1 / PSF centre, is computed from the GPU PSF and differs by 4.4e-16 (K, array) and 2.2e-16 (C) relative |
| 5 | Determinism | **pass** | every C and K GPU image one SHA256 over three fresh-process repeats; default batching (K: 4 batches × 9 layers; C: 5 × 9) and one-layer batches bit-identical; the whole-array images too over the repeats |
| 6 | CPU path unchanged | **pass** | every C (15), K (6) and whole-array image at 1 and 16 threads bit-identical to the `3b875e0` baseline, with the feature-on extension (`device=cpu`, `x2-20261030-04/compare-*-cpu-t*.json`) and with the feature-off extension that the final Windows check built from `7af8917` (`x2-20261030-04/feature-off`) |
| 7 | Correctness tests | **pass** | Rust: `stockham_scheme_matches_a_direct_dft` (17 lengths, factors 2, 3, 4, 5, 7, 11, 13, lengths 1, 2, 16, 616; 1e-12), `gpu_fft_matches_rustfft` (f64 1e-12, f32 1e-5 of the largest output; 12×30, 77×13, 1×8, 16×5, three 616² grids), `gpu_inversion_matches_the_cpu_and_ignores_batching` (f64 1e-12 of peak, f32 1e-4; batching bit-neutral), `unsupported_sizes_are_refused`, `pack_layer_sorts_stably_by_cell`, `radices_cover_the_comparator_sizes` |
| 8 | Clean failure | **pass** | Windows, feature off: GPU tests skip, the RuntimeError test passes; WSL: `skipped: no usable GPU adapter …; seen: [llvmpipe (LLVM 21.1.8, 256 bits) (Vulkan, Cpu)]` |
| 9 | Builds and checks | **pass** (Windows check PASS; Linux check-all below) | see [Checks](#checks-on-both-platforms) |

### The f32 path (criterion 10, reported, not gated)

| Comparator | Verdict | Figures |
| --- | --- | --- |
| C vs WSClean FITS | pass | dirty 6.98e-7 of peak, PSF 4.77e-7 |
| I, both comparisons | pass | response fraction 2.89e-8 (18 % of 1.6e-7, smaller than f64's 1.31e-7), template flux 1.80e-7, closures 1.9e-9 |
| K, six arms | **fail** (12 failures) | pixels pass (dirty 9.7e-7 of peak, PSF 5.1e-7) but the residual metrics (`residual_rms`, `residual_rms_offsource`, `residual_max_abs` of dirty − peak·PSF) differ by 1.2–3.5e-5 relative (tolerance 8.8e-6); calls unchanged (ratios 0.99997, 1.0, 1.0 against 0.99996, 1.0, 1.0) |
| vs the CPU path | outside the 1e-10 agreement bound, inside task A's tolerances | K 9.5e-7 of peak (PSF 5.3e-7), C 4.8e-7 (4.0e-7), whole array 1.15e-6 (1.09e-6) |

The prediction was half wrong: f32 passes task I with the smaller
response-fraction difference (the WSClean images it is compared with were
themselves gridded in f32), and fails task K, whose residual metrics
subtract the scaled PSF from the dirty image and so amplify the f32
rounding. The f32 path stays experimental.

### Speed (criterion 11, `x2-20261030-04`)

Per image: median over three fresh-process repeats, then median [range]
over the images of the set; wall includes host preparation and transfers.
CPU-s is the process CPU per image. RSS is the whole process's peak working
set. GPU memory is the peak increase of `nvidia-smi` memory.used during the
process (includes the device context, about 220 MiB), beside the bytes the
path allocates.

| Set | Config | Per image wall | CPU-s | Speed-up vs CPU t16 / t1 | Peak RSS | GPU memory (allocated) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| K (6 arms, 117 k gridded) | CPU 1 thread | 0.821 s [0.775–0.833] | 0.81 | | 201 MB | |
| K | CPU 16 threads | 0.297 s [0.285–0.303] | 2.32 | 1 / 2.8 | 410 MB | |
| K | GPU f64 | 0.118 s [0.115–0.138] | 0.16 | **2.5 / 7.0** | 294 MB | +481 MiB (249 MB) |
| K | GPU f32 | 0.077 s [0.074–0.088] | 0.15 | 3.9 / 10.7 | 296 MB | +464 MiB (268 MB) |
| C (15 jobs, 9.2/7.8 k) | CPU 1 thread | 0.796 s [0.746–0.877] | 0.80 | | 227 MB | |
| C | CPU 16 threads | 0.299 s [0.283–0.308] | 2.30 | 1 / 2.7 | 444 MB | |
| C | GPU f64 | 0.092 s [0.088–0.111] | 0.05 | **3.3 / 8.7** | 322 MB | +481 MiB (248 MB) |
| C | GPU f32 | 0.060 s [0.057–0.073] | 0.06 | 5.0 / 13.3 | 323 MB | +465 MiB (267 MB) |
| whole array (23.8 M gridded, 1024²) | CPU 1 thread | 7.61 s | 7.53 | | 1634 MB | |
| whole array | CPU 16 threads | 3.06 s | 17.9 | 1 / 2.5 | 2239 MB | |
| whole array | GPU f64 | 2.55 s | 3.09 | **1.2 / 3.0** | 2054 MB | +608 MiB (255 MB) |
| whole array | GPU f32 | 1.96 s | 3.36 | 1.6 / 3.9 | 2094 MB | +535 MiB (338 MB) |

Where the GPU path's time goes (set totals, median of three; seconds):

| Set, precision | `grid::bucket` (CPU, serial) | packing | upload | gather | FFT | projection | download | finish | **compute only** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| K (6), f64 | 0.049 | 0.077 | 0.092 | 0.128 | 0.218 | 0.016 | 0.014 | 0.070 | **0.365** (0.061 per image) |
| K (6), f32 | 0.054 | 0.068 | 0.087 | 0.051 | 0.062 | 0.007 | 0.012 | 0.071 | 0.121 |
| C (15), f64 | 0.046 | 0.210 | 0.213 | 0.055 | 0.551 | 0.041 | 0.033 | 0.160 | **0.655** (0.044 per image) |
| C (15), f32 | 0.048 | 0.168 | 0.202 | 0.032 | 0.156 | 0.016 | 0.029 | 0.161 | 0.208 |
| whole array, f64 (64 × 1-layer batches) | 1.122 | 0.264 | 0.243 | 0.523 | 0.257 | 0.029 | 0.008 | 0.050 | **0.817** |
| whole array, f32 (22 × 3) | 1.115 | 0.276 | 0.232 | 0.178 | 0.068 | 0.009 | 0.008 | 0.050 | 0.257 |

"Compute only" (excluding transfers and host work) is the sum of gather, FFT
and projection. On the four-station images the f64 FFT dominates (FP64 runs
at 1/64 of the FP32 rate on this card, and the generic radix-7 and -11
butterflies cost r complex products per output); on the whole-array image
the CPU's serial counters/placement pass (`grid::bucket`, 1.1 s, the same
code and cost in the CPU path, P2's open item) is 44 % of the GPU path's
wall, and the 64 one-layer batches that a 256 MiB budget forces cost the
gather about 3× (per-submission overhead).

**First call** (fresh process): adapter, device and queue 0.58–0.66 s
(`gpu_adapter()`), shader compilation 8–12 ms per precision (the NVIDIA
driver's on-disk shader cache was warm; the first compilation ever, in the
development probe, took 85 ms). Both are paid once per process.

**Post hoc, budget 4 GiB** (`x2-20261030-05`, Ollama had released the GPU):
the whole-array image in 2 batches: f64 2.34 s per image (gather 0.18 s,
FFT 0.24 s, projection 0.01 s, compute 0.43 s; upload 0.48 s), f32 2.06 s;
K unchanged (0.118 s f64). GPU memory +5.2 GiB (4.5 GB allocated) for the
f64 array image: a large budget pays only when the card is free.

**End-to-end drivers** (`x2-20261030-03`, before the WSL build started;
run in the order f64, f32, CPU, the first with the inputs cold in the file
cache): task C, fifteen jobs, 12.1 s on the GPU (f64), 7.4 s (f32), 11.5 s
on the CPU (16 threads); task I 11.9 / 9.7 / 12.9 s; task K inputs replay
6.5 / 5.6 / 6.2 s (the same drivers took 4.8, 5.7 and 2.7 s on the CPU at
20:22, so these walls are load- and cache-bound; reported, not compared).
At four stations the gridding is about 4.5 s of a C driver run on 16 CPU
threads and 1.4 s on the GPU; reading, weighting and FITS writing are the
rest.

### Checks on both platforms

- **Native Windows**, `.venv\Scripts\python -m rang.check` on `7af8917`
  (the committed tree, wiring not applied, so the feature is off): **`##
  overall: PASS`**, 481 s; Rust root/core/extension build, test, clippy and
  fmt pass; pytest 593 passed, 34 skipped (`tests/test_x2_gpu.py`: 3 passed,
  2 GPU tests skipped "no GPU gridder: the GPU gridder is not compiled into
  rang._core …"). Log `outputs/x2-20261030-04/check-final.log`. The same
  check on the untouched CRLF checkout of `3b875e0` had failed 20
  `test_p11_extract` cases (deviation 10).
- **Native Windows, feature on** (wiring applied): `cargo build --release
  --features gpu`, `cargo test --release --features gpu -- gpu grid` (19
  passed, the GPU tests running on the RTX 4070 Ti), `cargo clippy
  --all-targets --features gpu -- -D warnings` and `cargo fmt --check` of
  `core/` and `core/py` clean; `maturin develop --release --features gpu`;
  `pytest tests/test_x2_gpu.py tests/test_p2_gridder.py` 6 passed, 1 skipped
  (the no-adapter test, which skips when a GPU is usable).
- **Linux (WSL), feature off and on**: `cargo build --offline --locked
  --release` of `core/` (feature off) passes; with the wiring applied to a
  scratch checkout, `cargo build --offline --release --features gpu` and
  `cargo test --offline --release --features gpu -- gpu grid` pass (19
  passed; the five GPU tests return early: `skipped: no usable GPU adapter
  (Vulkan, Metal or DX12, not a CPU rasteriser); seen: [llvmpipe (LLVM
  21.1.8, 256 bits) (Vulkan, Cpu)]`).
- **Linux (WSL), `bash tools/check-all.sh`** with
  `OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`, feature off: pending at this commit (recorded in the next one).

## Deviations and post-hoc items

1. **Task K comparator from P2's dumped inputs** (decided before the
   freeze, in the protocol): the archived fetched bytes are gone.
2. **Default budget 256 MiB, not 512** (post hoc): with the Ollama server
   resident (11.2 GB of 12 GB in use) a 532 MB allocation oversubscribed the
   card and WDDM paged it: the K f64 FFT took 113 ms at 512 MiB against
   36 ms at 256 MiB in the development probe. Batching is bit-neutral
   (criterion 5), so no result depends on the budget.
3. **Gather split over seven invocations per cell** (post hoc): one
   invocation per cell looping all seven kernel rows took 2.5 s for the
   whole-array f64 gather (load imbalance at the dense centre of the uv
   plane); one invocation per kernel row with an ordered workgroup sum took
   0.63 s. The frozen design text describes one invocation per cell; the
   order of additions within a cell changes accordingly (row partial sums,
   then rows in order), still deterministic (criteria 4 and 5 measured on
   the version as built). A 49-way split (one invocation per tap) was
   slower (0.99 s) and was not kept.
4. **Sample values widened on the host** (post hoc): three f64 values per
   sample instead of f32 bits converted in the shader (exact either way;
   saves three FP64-rate conversions per contribution).
5. **Radices**: the frozen text lists 8 and 16 among the pass radices; the
   plan as built uses 4, 2 and odd primes ≤ 13 (lengths 8 and 16 run as
   4·2 and 4·4 and are in criterion 7's tests).
6. **Criterion 4's counter clause fails as frozen** (above). Post hoc: the
   eighth stats entry is the PSF normalisation derived from the image, not
   a counter of the gridding pass; the seven counters are exact.
7. **Per-stage submissions**: each batch waits three times so the stages
   can be timed; this costs a few milliseconds per batch (visible in the
   64-batch whole-array run) and is part of every GPU figure above.
8. **The `-03` timings are void** (operator error, above); `-04` replaces
   them with the same extension.
9. **First-call measurement**: the wrapper calls `gpu_adapter()` before
   every GPU inversion, so the adapter cost lands in that call, which the
   bench times on its own; the first image's `context_s` is therefore 0.
10. **The Windows worktree was converted to LF in place** before the checks:
    the system Git config (`core.autocrlf=true`) checks out CRLF, and 20
    `tests/test_p11_extract.py` cases (verbatim-copy hashes) fail on a CRLF
    checkout (measured on the untouched tree: `check-pre.log`, 20 failed,
    570 passed). No Git config file was changed; Git ran with
    `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.autocrlf
    GIT_CONFIG_VALUE_0=false` in the environment.
11. **Shared GPU**: the protocol expected about 10 GB free; 0.9–1.0 GB was
    free during the comparator runs and 11 GB during the timing run.

## Open items

1. **`grid::bucket` in parallel** (P2's open item, now the largest single
   cost of the GPU path at whole-array scale, 1.1 s of 2.5 s): placement is
   independent per sample; the exact counters need only a serial sum over
   per-cell values. It would speed up both devices; it is a change of
   `grid.rs` beyond this task's owner rule.
2. **One submission per batch** (or GPU timestamps for the stage timings)
   and the batching budget from the free device memory (wgpu exposes none
   portably): the 64-batch whole-array run spends about 0.4 s more in
   compute than the 2-batch one.
3. **f64 FFT**: specialised radix-7/11 butterflies, or a real-to-complex
   transform for the PSF grid (its input is real), would cut the dominant
   four-station cost; the transform's rounding then changes again (within
   criterion 4's bound, to be measured).
4. **f32 path**: fails task K's residual metrics; an f32-grid/f64-sum hybrid
   (WSClean's own precision is f32 grids) needs its own protocol.
5. **macOS/Metal**: not tested; Apple GPUs have no f64, so only the f32
   path could run there. DX12 in wgpu 30 does not expose SHADER_F64 on this
   card (Vulkan does).
6. **Facet-IDG (DF6) and the exact wgridder on wgpu** can reuse
   `context.rs`, the Stockham kernel and the batching.

## Tool runs

All on native Windows unless marked WSL; walls of the loaded host (WSL load
3.7–7.2).

| When | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-30 | WSL `cp -r --no-preserve=mode` of the comparator inputs to `C:\Users\gijsm\Build\tmp\20261030-rang-x2\inputs` | 4.8 s | – | 532 MB (X1: 116 s for 1 GB) |
| 2026-10-30 | `uv venv -p 3.14` + `uv pip install -e ".[pointing,beam,test,imaging]" ruff maturin pip` | 130.7 s | – | builds the extension |
| 2026-10-30 | `cargo build --release` of the wgpu adapter probe (first wgpu 30.0.1 download) | 39 s | – | probe outside the repository |
| 2026-10-30 | C driver + comparator, CPU, precondition | 4.8 s + 1.1 s | – | |
| 2026-10-30 | I driver, CPU, precondition | 5.7 s | – | |
| 2026-10-30 | `bench_x2_gpu.py k-inputs`, CPU, precondition | 2.7 s | – | |
| 2026-10-30 | `bench_x2_gpu.py array-inputs` | 1.5 s | – | 424 MB npz |
| 2026-10-30 | baseline CPU images, C/K/array at 1 and 16 threads | 6.6 / 4.2, 3.3 / 2.0, 6.2 / 3.4 s | 1.6–2.2 GB (array) | `x2-20261030-01/baseline` |
| 2026-10-30 | `python -m rang.check` on the untouched CRLF tree | 508 s | – | FAIL: 20 `test_p11_extract` cases (CRLF), all else pass |
| 2026-10-30 | `cargo build --release` of `core/`, feature off / on | 86 s / 185 s | – | first build with wgpu |
| 2026-10-30 | `cargo test --release --features gpu` of `core/` (each, incl. build) | 159–302 s | – | 19 grid/gpu tests, 1–2 s to run |
| 2026-10-30 | `maturin develop --release --features gpu` | 310–412 s | – | thin LTO, codegen-units 1, with wgpu |
| 2026-10-30 | `cargo clippy --all-targets --features gpu -D warnings` | 18–75 s | – | |
| 2026-10-30 | development probe builds (`lto = false`, outside the repository) | 52–104 s | – | used for the post-hoc design iterations |
| 2026-10-30 | comparators `x2-20261030-03`: C driver + compare (f64 / f32 / CPU) | 12.1 + 3.8 / 7.4 + 3.7 / 11.5 + 3.6 s | – | |
| 2026-10-30 | I driver (f64 / f32 / CPU) | 11.9 / 9.7 / 12.9 s | – | |
| 2026-10-30 | K inputs replay (f64 / f32 / CPU) | 6.5 / 5.6 / 6.2 s | – | |
| 2026-10-30 | `bench_x2_gpu.py bench` K / C / array, 4 configs × 3 repeats (`-04`) | 42.0 / 74.6 / 64.8 s | 2.2 GB (array) | |
| 2026-10-30 | one-layer-batch GPU runs K / C | 2.7 / 3.2 s | – | |
| 2026-10-30 | post-hoc 4 GiB budget benches K / array (GPU configs) | 14 / 25 s | – | |
| 2026-10-30 | `bench_x2_gpu.py summarize` | about 15 s | – | |
| 2026-10-30 | WSL `cargo fetch --locked` of `core/` | 3.7 s | – | |
| 2026-10-30 | WSL `uv pip install -e …` | 104.1 s | – | |
| 2026-10-30 | WSL `cargo build --offline --locked --release` of `core/`, feature off | 76.8 s | – | |
| 2026-10-30 | WSL `cargo build --offline --release --features gpu` (wired copy) | 136.6 s | – | |
| 2026-10-30 | WSL `cargo test --offline --release --features gpu -- gpu grid` | 128.3 s | – | 19 passed, GPU tests skipped (llvmpipe rejected) |

## For the coordinator

- **Shared-file lines.** `core/src/lib.rs`, after `pub mod fused;`:

  ```rust
  #[cfg(feature = "gpu")]
  pub mod gpu;
  ```

  `core/py/Cargo.toml`, a forwarding feature:

  ```toml
  [features]
  # The wgpu gridder of the core (task X2, research/x2-wgpu.md).
  gpu = ["rang-core/gpu"]
  ```

  `core/py/src/lib.rs`: the two `#[cfg(feature = "gpu")]` functions
  `grid_invert_gpu` and `grid_gpu_adapter`, the `PyRuntimeError` import and
  their two `m.add_function` lines, verbatim in the appendix diff.
  `core/py/Cargo.lock` then gains wgpu's tree (93 packages, the versions of
  `core/Cargo.lock`): `cargo +1.93 build --offline --manifest-path
  core/py/Cargo.toml` writes it. Build the GPU extension with `maturin
  develop --release --features gpu`; the default build and the wheels stay
  feature-off (no `wheels.yml` change).
- **STATE paragraph (proposed):** "X2 GPU gridder (big plan), 2026-10-30
  (implemented; measured; [x2-wgpu.md](x2-wgpu.md)). The w-stacking
  gridder runs on the GPU through `wgpu` 30 behind the cargo feature `gpu`
  (`RANG_GRIDDER_DEVICE=gpu`), no CUDA: gather gridding without atomics, a
  mixed-radix Stockham FFT in WGSL at WSClean's exact padded size and the
  projection with an ordered layer sum, in f64 (Vulkan `SHADER_F64`) with
  the counters from the CPU code. On the RTX 4070 Ti from native Windows the
  f64 path passes the task C, I and K comparators with the CPU's margins
  (response fraction 1.31e-7 of 1.6e-7), differs from the CPU images by at
  most 2.2e-15 of the peak and is deterministic; one frozen clause fails
  (the PSF normalisation entry is not bit-equal, 4.4e-16). Per image, f64
  including transfers: four stations 0.09–0.12 s against 0.30 s on 16
  threads (2.5–3.3×), the 23.8 M-visibility whole-array image 2.5 s against
  3.1 s, where the CPU's serial counters pass (1.1 s) now dominates. An f32
  path passes C and I but fails K's residual metrics and stays
  experimental. Archive `results/x2-wgpu.json`."
- **`research/README.md` index line:** "- [x2-wgpu.md](x2-wgpu.md) — X2: the
  w-stacking gridder and FFT on wgpu (feature `gpu`, f64), C/I/K comparators
  pass on the RTX 4070 Ti, 2.5–3.3× over 16 CPU threads at four stations,
  1.2× at whole-array scale; f32 fails K."
- **`research/tool-timings.md` rows:** the "Tool runs" table above.
- **Upstream observations (listed, not filed):** RATT and caracal-pipeline:
  none. Non-RATT: (1) wgpu 30.0.1's DX12 backend does not expose
  `Features::SHADER_F64` on an RTX 4070 Ti (driver 621.01) although D3D12
  supports double-precision shaders; Vulkan exposes it on the same card;
  (2) naga's WGSL front end rejects `active` as an identifier (reserved
  word) with a clear message, fine; no f64 `sin`/`cos` exists in WGSL or
  SPIR-V GLSL.std.450, so an f64 phasor needs its own polynomial (a known
  limitation, not a bug); (3) wgpu has no portable query of free device
  memory, so a budget must be configured by hand on a shared GPU; (4) on
  WDDM a modest oversubscription is paged silently and slows compute about
  4×, with no error.
- **Ignored output directories** (worktree `outputs/`, mirror them to the
  data host if kept): `x2-20261030-01` (preconditions, baseline extension and
  CPU images, whole-array inputs; 672 MB, of which the array npz 424 MB is
  regenerable with `bench_x2_gpu.py array-inputs`), `x2-20261030-02`
  (development trials, deletable), `x2-20261030-03` (comparator runs; void
  timings), `x2-20261030-04` (timing run), `x2-20261030-05` (post-hoc
  budget run). The junctions in `outputs/` point at
  `C:\Users\gijsm\Build\tmp\20261030-rang-x2\inputs`.

## Appendix: the wiring diff

Applied with `git apply` from the repository root for every feature-on
build and test above (the lockfile change of `core/py/Cargo.lock` is left
out; cargo writes it). Blank context lines carry no leading space here
(`git diff --check`); `git apply` accepts them as they are (checked), and
the exact patch, lockfile included, is `outputs/x2-20261030-03/wiring.diff`:

```diff
diff --git a/core/py/Cargo.toml b/core/py/Cargo.toml
index bf5a16d..7297d2c 100644
--- a/core/py/Cargo.toml
+++ b/core/py/Cargo.toml
@@ -16,6 +16,10 @@ rang-core = { path = ".." }
 pyo3 = { version = "0.30.1", features = ["extension-module", "abi3-py310"] }
 numpy = "0.30.0"

+[features]
+# The wgpu gridder of the core (task X2, research/x2-wgpu.md).
+gpu = ["rang-core/gpu"]
+
 [profile.release]
 lto = "thin"
 codegen-units = 1
diff --git a/core/py/src/lib.rs b/core/py/src/lib.rs
index 8cd49b9..140d846 100644
--- a/core/py/src/lib.rs
+++ b/core/py/src/lib.rs
@@ -27,6 +27,8 @@
 use numpy::{
     Element, IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArrayDyn, PyReadwriteArrayDyn,
 };
+#[cfg(feature = "gpu")]
+use pyo3::exceptions::PyRuntimeError;
 use pyo3::exceptions::{PyOSError, PyValueError};
 use pyo3::prelude::*;
 use pyo3::types::PyBytes;
@@ -732,6 +734,79 @@ fn grid_invert(
     }))
 }

+/// `rang_core::gpu::ffi::grid_invert` (task X2, research/x2-wgpu.md):
+/// `grid_invert`'s buffers plus the precision (`"f64"` or `"f32"`) and a
+/// float64 array of `N_TIMINGS` timings; returns 0, or raises RuntimeError
+/// with the reason when the GPU path fails.
+#[cfg(feature = "gpu")]
+#[pyfunction]
+#[allow(clippy::too_many_arguments)]
+fn grid_invert_gpu(
+    py: Python<'_>,
+    nrow: usize,
+    nchan: usize,
+    width: usize,
+    height: usize,
+    kernel_size: usize,
+    oversampling: usize,
+    n_w_layers: usize,
+    pixel_size_x: f64,
+    pixel_size_y: f64,
+    padding: f64,
+    uvw: Ro<'_, f64>,
+    frequencies: Ro<'_, f64>,
+    data: Ro<'_, f32>,
+    weights: Ro<'_, f32>,
+    imaging_weights: Ro<'_, f32>,
+    precision: &str,
+    mut dirty: Rw<'_, f64>,
+    mut psf: Rw<'_, f64>,
+    mut stats: Rw<'_, f64>,
+    mut timings: Rw<'_, f64>,
+) -> PyResult<i32> {
+    let precision = rang_core::gpu::Precision::parse(precision).map_err(PyValueError::new_err)?;
+    if timings.as_slice()?.len() != rang_core::gpu::ffi::N_TIMINGS {
+        return Err(PyValueError::new_err("timings must hold N_TIMINGS doubles"));
+    }
+    let inputs = GridInputs {
+        nrow,
+        nchan,
+        width,
+        height,
+        kernel_size,
+        oversampling,
+        n_w_layers,
+        pixel_size_x,
+        pixel_size_y,
+        padding,
+        uvw: ptr(&uvw)?,
+        frequencies: ptr(&frequencies)?,
+        data: ptr(&data)?,
+        weights: ptr(&weights)?,
+        imaging_weights: ptr(&imaging_weights)?,
+    };
+    let mut outputs = GridOutputs {
+        dirty: ptr_mut(&mut dirty)?,
+        psf: ptr_mut(&mut psf)?,
+        stats: ptr_mut(&mut stats)?,
+    };
+    let timings = ptr_mut(&mut timings)?;
+    // SAFETY: as in `fused`; `timings` holds N_TIMINGS doubles.
+    detach(py, || unsafe {
+        rang_core::gpu::ffi::grid_invert(&inputs, &mut outputs, precision, timings)
+    })
+    .map(|()| 0)
+    .map_err(PyRuntimeError::new_err)
+}
+
+/// The adapter the GPU gridder uses (created on first call); RuntimeError
+/// when none is usable.
+#[cfg(feature = "gpu")]
+#[pyfunction]
+fn grid_gpu_adapter(py: Python<'_>) -> PyResult<String> {
+    detach(py, rang_core::gpu::adapter_description).map_err(PyRuntimeError::new_err)
+}
+
 /// `rang_core_grid_kernel` into a caller-owned float64 array; 2 on a panic
 /// of the kernel (task P7; before, `(7, 2)` aborted the process).
 #[pyfunction]
@@ -1321,6 +1396,10 @@ fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
     m.add_function(wrap_pyfunction!(imaging_weights, m)?)?;
     m.add_function(wrap_pyfunction!(grid_invert, m)?)?;
     m.add_function(wrap_pyfunction!(grid_kernel, m)?)?;
+    #[cfg(feature = "gpu")]
+    m.add_function(wrap_pyfunction!(grid_invert_gpu, m)?)?;
+    #[cfg(feature = "gpu")]
+    m.add_function(wrap_pyfunction!(grid_gpu_adapter, m)?)?;
     m.add_function(wrap_pyfunction!(flag_rows, m)?)?;
     m.add_function(wrap_pyfunction!(gain_tv, m)?)?;
     m.add_function(wrap_pyfunction!(trend_slopes, m)?)?;
diff --git a/core/src/lib.rs b/core/src/lib.rs
index 4df6968..d6e66aa 100644
--- a/core/src/lib.rs
+++ b/core/src/lib.rs
@@ -37,6 +37,8 @@ pub mod ffi_weights;
 pub mod ffi_wgridder;
 pub mod fluxstd;
 pub mod fused;
+#[cfg(feature = "gpu")]
+pub mod gpu;
 pub mod grid;
 pub mod jones;
 pub mod ms;
```
