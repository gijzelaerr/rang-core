# gemclean-57: SIGSEGV at gridding start on a 10.6 h MeerKAT track (#57)

Status: **open, not reproduced** (2026-11-25). Five simulated runs completed cleanly. Two of them match the
failing run's rows and visibilities per output channel. An audit found no 32-bit index or size in the
path that this shape could overflow. No fix is merged. The next step is the reporter's backtrace
(draft request in `outputs/drafts/gemclean-57-reply.md`).

## Report

- **Command:** rang-core 0.3.0 wheel, `python -m rang.gemclean`, called from `rang-core run` selfcal
  round 1. Options: `-size 10240 -scale 1.1asec -weight briggs -0.3 -niter 80000 -gain 0.15 -mgain 0.9
  -auto-threshold 3 -wgridder-accuracy 5e-5 -average-channels 2 -channels-out 8 -join-channels
  -fit-spectral-pol 4 -auto-mask 4 -multiscale -multiscale-scales 0,4,16,64 -data-column
  CORRECTED_1GC -field 3`.
- **Data:** 1 754 910 rows, 1024 channels averaged to 512, 4 correlations, 31 antennas.
- **Failure:** exit -11 within minutes of the line `512 channels into 8 output channels, MF weighting,
  joined, 187.68 s read, 56.72 s weights`. Nothing on stderr, and memory was not the cause (877 GB free).
- **Passing control:** the same command on RCW57 (146 k rows x 1024 channels).

## Audit (origin/main de22d05e; `core/src/wgridder.rs` identical to v0.3.0)

- **Sizes after the weights line.** Each output channel holds 1.75 M x 64 = 1.12e8 visibilities.
  The full read (1.75 M x 1024 x 4 = 7.2e9 cells) is read in chunks of at most about 256 MB.
  `split_channels`, `GridMeasurement`, the layout (`VisRef {row: u32, ch: u32}`, `order: Vec<u32>`
  over at most 1.12e8 refs) and every flat index are `usize`. `check_common` refuses 2^32 rows or
  channels.
- **Kernel choice depends on the visibility count** (`choose_kernel`). Plans were printed from a scratch
  test, with w over 0-44 kλ and epsilon 5e-5:

  | grid | vis / channel | f64 support | nu | nu*nv | planes |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | n = 10240 | 9.3e6 (RCW57) | 10 | 12 320 | 1.5e8 | 49 |
  | n = 10240 | 1.12e8 (#57) | 8 | 13 440 | 1.8e8 | 51 |
  | 2n = 20480 (PSF) | 9.3e6 / 1.12e8 | 10 | 24 640 | 6.1e8 | 168 |
  | 2n, f32 | any | 7 | 31 752 | 1.0e9 | 210 |

  No grid comes near 2^31 cells, so the support change (10 to 8) on the n grid is the only plan
  difference between the passing and the failing run.
- **Unsafe code read:**
  - tile dumps, column writes in `grid_to_image`, degrid writes and prefetches (`wgridder.rs`);
  - `Convolver` row blocks (`gemclean.rs`);
  - the SIMD gathers (`kernels.rs`, bounds from image geometry only);
  - `HugePageAlloc` (`host.rs`: mmap, head and tail trims, in-place shrink, `realloc`);
  - the allocation tables (`memory.rs`).

  None has an offset that depends on the visibility count in a way that could leave its buffer.
- **Stack overflow:** in the Python extension, Rust's guard handler is not installed, so a stack
  overflow would surface as a silent SIGSEGV.

## Reproduction attempts (null)

- **Simulated MS.** `core/examples/sim57.rs`, 64 antennas, 870 dumps, 1 753 920 rows, 10.6 h at
  dec -24.5 deg, 856-1712 MHz.
  - `sim128.ms`: 128 channels, 5 points plus noise.
  - `simf256.ms`: 256 channels, zero weights on all baselines of antennas 0-3, on two RFI bands and on
    20 % of the rest at random, with NaN data under every zero weight.
- **Locations.** Runs in `D:/rang/outputs/gemclean-57-20261125/` (glacier). The WSL copy is in
  `~/rang-scratch/gemclean-57/`, the nash copy in `~/rang-data/outputs/gemclean-57-20261125/`.
- **Results.**

| run | host / build | input | options changed from the report | result |
| --- | --- | --- | --- | --- |
| A | glacier, Windows `gemclean.exe` (system allocator), -j16, AVX-512 | sim128, 1.12e8 vis/ch | `-channels-out 2 -fit-spectral-pol 2`, no averaging | exit 0, 5 majors, 2 524 s |
| W030 | glacier WSL, Linux, **0.3.0 PyPI wheel** (`HugePageAlloc`), -j8 | sim128 | as A | exit 0, 5 majors, 3 850 s, 43.4 GB peak RSS |
| F | glacier Windows, -j8 | simf256 (flags, NaN), `-average-channels 2` to 2 x 64 ch | `-channels-out 2 -fit-spectral-pol 2` | exit 0, 4 majors, 1 335 s |
| dbg1 | glacier Windows **debug** build (overflow checks, debug asserts), -j4 | flagged 80 640 rows x 64 ch | `-size 1024 -scale 11asec`, otherwise as the report (`-average-channels 2 -channels-out 8 -fit-spectral-pol 4`) | exit 0, 4 majors, 1 104 s |
| stack | glacier Windows, `-size 2048 -nmiter 1`, -j8 | sim128 | `RUST_MIN_STACK` 64 KB / 128 KB / 256 KB | 64 KB: overflow at start (expected); 128 KB and 256 KB: exit 0 |

Run AVX2 (A with `RANG_WGRIDDER_SIMD=avx2 -simd avx2`) and run B8 (nash, Linux binary under gdb,
`-channels-out 8 -fit-spectral-pol 4` on sim128) were still to come when this note was written.

What these rule out:
- 1.12e8 visibilities per channel at n = 10240 with the reported clean settings;
- the Linux huge-page allocator at that load, on the released wheel;
- zero-weight rows, channels and cells, NaN data and `-average-channels`;
- a large per-thread stack need at 8 threads (gridding needs under 128 KB).

What they do not cover:
- 8 output channels at full load (about 3x the memory of runs A and W030);
- the reporter's thread count, CPU and environment;
- real uv coverage, with 31 antennas and the field-3 selection from a multi-field MS.

## Next

1. **The reporter's backtrace** (`gdb -batch -ex run -ex bt ...`), plus `nproc`, CPU flags, `ulimit -s`,
   `RANG_*`/`RAYON_*`, and one rerun each with `RUST_MIN_STACK=1073741824` and with `-j 8`. Draft in
   `outputs/drafts/gemclean-57-reply.md`; the owner approves posting.
2. **Full-shape run on nash** (8 x 64 channels, about 100 GB) with the Linux binary under gdb, once
   the queue has room. `sim::simulate` holds the cube several times over, so 512 or more channels
   needs a chunked writer.
