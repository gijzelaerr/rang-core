# gemclean-57: SIGSEGV at gridding start on a 10.6 h MeerKAT track (#57)

Status: **open, not reproduced** (2026-11-25). Every simulated run at the reported options completed cleanly. Two of them match the
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

Run AVX2 repeated A at -j8 with `RANG_WGRIDDER_SIMD=avx2 -simd avx2`, so the gridder and the clean
kernels took their AVX2 paths. It exited 0 after 5 majors in 2 313 s, so the AVX2 path is covered as
well as AVX-512.

Run B8, the nash Linux binary under gdb with 8 output channels at -j8, was cancelled before it ran.
Every -j8 arm had been null, and B8 held an 80 GB ticket in a blocked queue.

### Reporter's facts (2026-11-25, via the coordinator; reported, not verified)

- **Intermittent:** the identical command on the same MS ran clean twice (07:51; 09:38, 80 000
  components in 4 479 s) and segfaulted on the third run (11:00). Two wsclean jobs ran throughout; a
  disk-heavy job had just started when it crashed.
- **Host:** AMD EPYC 9555P (Zen 5, AVX-512), 128 threads, `ulimit -s 8192`, no `RANG_`/`RAYON_`/`RUST_`
  variables, wheel 0.3.0.

Intermittency on fixed input points away from a size limit and towards a race, or towards
scheduling-dependent stack depth at 128 threads.

### Stack depth against thread count (measured; hazard, not shown to be #57)

Without `-j`, gemclean runs in rayon's default global pool. Its threads have 2 MiB stacks; `cli.rs`
sets no `stack_size`. Inside the extension, a stack overflow is a silent SIGSEGV.

| case | threads | `RUST_MIN_STACK` | result |
| --- | ---: | ---: | --- |
| sim128 `-size 2048 -nmiter 1`, 16 cores | 16 | 96, 128, 192, 256, 512 KiB | all exit 0 |
| same | 128 | 96, 128, 192 KiB | overflow within 1-9 s |
| same | 128 | 256 KiB | overflow right after the weights line, the reported place |
| same | 128 | 512 KiB | exit 0 |
| sim128 full options `-size 10240 -nmiter 1`, 16 cores | 128 | 1, 2, 2, 4 MiB | 4 of 4 exit 0, 720-738 s |
| `stack57 beam`: `theoretic_beam` alone, 1 or 64 channels, pinned to 4 cores | 128 | 256 KiB | exit 0 |
| same | 128, 256, 512, 1024 | 2 MiB | exit 0 (500 loops at 1 channel, 100 loops at 64 channels) |

Findings:
- The stack need grows with the thread count: under 96 KiB at 16 threads, 256-512 KiB at 128.
- No case reached the 2 MiB default. The full-size run passed even at 1 MiB, and oversubscription to
  1024 threads on 4 cores did not overflow 2 MiB.
- So the margin at the default is at least 2x on these hosts. Whether a 128-core Zen 5 under I/O
  load crosses it is open, and only the reporter's backtrace can decide it.
- The same hazard applies to every rayon user in the extension, not only gemclean.

What decides it in the backtrace:
- **Stack overflow:** the fault address (`$_siginfo._sifields._sigfault.si_addr`) lies just below
  `$rsp`, under hundreds of repeating rayon join/steal frames.
- **Race or corruption:** a fault address far from `$rsp`. The next arm is then a ThreadSanitizer build
  of the stack57 harness on Linux.

What these runs rule out:
- 1.12e8 visibilities per channel at n = 10240 with the reported clean settings;
- the Linux huge-page allocator at that load, on the released wheel;
- zero-weight rows, channels and cells, NaN data and `-average-channels`;
- the AVX2 and AVX-512 paths at 8-16 threads;
- a stack need near 2 MiB at up to 1024 threads on 4 cores.

What they do not cover:
- 8 output channels at full load (about 3x the memory of runs A and W030);
- 128 real cores;
- the reporter's machine under concurrent I/O load;
- real uv coverage, with 31 antennas and the field-3 selection from a multi-field MS.

## Next

1. **The reporter's backtrace** (running on their side 2026-11-25), with `si_addr` against `$rsp` and the
   frame count of the faulting thread. If it is clean, rerun with `RUST_MIN_STACK=1073741824` and with
   `-j 8`. The draft follow-up is in `outputs/drafts/gemclean-57-reply.md`; the owner approves posting.
2. **If it is a stack overflow:** give every pool gemclean runs in an explicit `stack_size` (in
   `cli::run`, both the global and the private branch, also without `-j`), sized from the table above
   with a wide margin (for example 64 MiB, reserved rather than committed). Add a regression test that
   builds its pool through the same function, and consider the same for the extension's other rayon
   users.
3. **Full-shape run on nash** (8 x 64 channels, about 100 GB) with the Linux binary under gdb, once
   the queue has room. `sim::simulate` holds the cube several times over, so 512 or more channels
   needs a chunked writer.
