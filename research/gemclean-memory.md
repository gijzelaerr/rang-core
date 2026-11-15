# GeMClean's memory on joined polarisations (issue #32)

Status: **implemented and measured, target met** (2026-11-15). Accounting
and decision rule frozen before any fix (sections 1-4, commit `72265c8`);
fixes and measurement in section 5, one fix added post hoc (dated there).
J1833−2103: 20.24 to 9.20 GiB, every FITS file byte-identical.

Branch `gemclean-memory`, worktree `~/Worktrees/rang/gemclean-memory`,
from `main` 756997f. Data and run outputs in
`D:\rang\outputs\gemclean-memory-20261115`; scripts in
[results/gemclean-memory/](results/gemclean-memory/).

## 1. The problem

E2-B arm A5 ([e2b-misses.md](e2b-misses.md) 9.22) ran GeMClean with
`-pol IQUV -join-polarizations -channels-out 8 -join-channels -auto-mask 5`
at 2048² and 2″ on three calibrator fields. GeMClean (the wheel,
`python -m rang.gemclean`, 4 threads) peaked at 40.3, 44.9 and 20.2 GB
resident (J1331+3030, J1939−6342, J1833−2103; the sum over the process
tree, `a5_time.py`), WSClean 3.7 at 2.0, 2.0 and 1.4 GB on the same data.
On the 63 GB host this forces 46 GB lock bookings, and an under-booked run
made the host thrash on 2026-11-15. The speed run found 3-5 × on Stokes I
([gemclean-speed.md](gemclean-speed.md)).

## 2. How it was measured

- **Heap accounting.** `-memory-report` existed for the Stokes I path on
  Linux only (the binary's `HugePageAlloc` counts requested bytes). Commit
  `2eec8c1` (no algorithm change) adds a counting system allocator for the
  binary on every other platform (`host::CountingAlloc`), the Windows
  working set in each phase record, the peak working set as
  `peak_memory_bytes`, and for the polarisation path a buffer table summed
  over the entries plus the `memory` section in `-report.json`. Heap bytes
  are bytes asked for, not pages touched; the peak working set is beside
  them.
- **Probe.** [probe.py](results/gemclean-memory/probe.py) writes a synthetic
  MS with the W1 writer (16 or 32 antennas, 256 or 64 channels, four
  correlations, a 1 Jy point source in XX and YY plus noise, 10 % of the
  cells flagged in all four correlations at once as after E2-B's P flag
  spread, unit weights) and runs one joined configuration with
  `-memory-report` (briggs 0, mgain 0.9, auto-threshold 3, ε 1e-4, `-j 4`).
  [matrix.sh](results/gemclean-memory/matrix.sh): Stokes I and joined IQUV
  × 256²-2048² × 1, 2, 4, 8 joined channels on 24,000 rows of 64 channels.
  [visaxis.sh](results/gemclean-memory/visaxis.sh): joined IQUV, 8 channels,
  1024², `-auto-mask 5`, on 37,200, 74,400 and 148,800 rows of 256 channels.
- **The A5 field.** J1833−2103 (field 2, scans 17-20) on a private
  matched-state copy rebuilt with A5's own `a5_slim.py`, unchanged
  ([slim.sh](results/gemclean-memory/slim.sh)); its FLAG and
  RANG_CORRECTED_DATA SHA-256 equal A5's receipt (`c2609912…`,
  `26ed8be6…`), no chunk differs, WEIGHT is 1
  ([receipts/slim.json](results/gemclean-memory/receipts/slim.json)). Runner
  [j1833.sh](results/gemclean-memory/j1833.sh): A5's argv, then the images'
  SHA-256, then the images deleted; [memtime.py](results/gemclean-memory/memtime.py)
  records the tree's summed resident set as A5 did, plus the largest
  process's peak working set and peak private bytes (the commit charge,
  which is what thrashed).

## 3. Where the memory goes (before any fix)

Per **entry** (one output channel × one polarisation; 32 at 8 × IQUV), at
`-j 4`, gridder in `f32` (the default; `gridder_single`), images `f64`:

| Buffer | Bytes | Kept |
| --- | --- | --- |
| Read: the whole band per polarisation, `StokesI` vis `c32` + weight `f32` | 12 per row × channel × **polarisation** | all four until every entry is built |
| `PolEntry`: vis `c32` + gridding weight `f64` of the kept rows | 16 per cell | all 32 until the measurements are built |
| Measurement: vis `c32` + normalised weight `T` | 12 per cell (dense, zero weights included) | whole run |
| Gridder plan: sorted index `VisRef` (8), stored sorted values `c32` (8), visibility-order permutation `u32` (4) | 20 per **active** visibility | whole run (stored and order from the first residual on; `release_grids` frees only the grids) |
| Gridder tables, baselines, uvw (twice) | ~4 MB + 48 per row | whole run |
| Beam (one per channel here: all four polarisations have the same rows and weights): exterior `(2n−1)²` `f64`, FFT spectrum `2n × (n+1)` `c64` | 2 × 134 MB at 2048² | whole run |
| Joined loop: model, residual, dirty copy; per major cycle `models_major` and `maps` copies; `next` residual beside `residuals` in the major | 6 × n² `f64` = 6 × 33.5 MB at 2048² | 5 in the minor cycle, 6 in the major |
| PSF `2n × 2n` `f64` per beam | 134 MB | transient |

WSClean keeps the visibilities in reordered temporary files, not in memory,
and its images in `f32`; this is the difference.

**Synthetic scaling** (heap peak, GB; `D:\rang\outputs\gemclean-memory-20261115\matrix-base`
and `visaxis-base`; peak working set within 0.02 GB of the heap figure):

| Pol | n | 1 ch | 2 ch | 4 ch | 8 ch |
| --- | ---: | ---: | ---: | ---: | ---: |
| I | 256 | 0.13 | 0.10* | 0.12* | 0.16* |
| I | 512 | 0.15 | 0.19* | 0.25* | 0.41* |
| I | 1024 | 0.45 | 0.54* | 0.80* | 1.40* |
| I | 2048 | 1.43 | 1.80* | 2.92* | 5.29* |
| IQUV | 256 | 0.23 | 0.25 | 0.30 | 0.40 |
| IQUV | 512 | 0.33 | 0.41 | 0.56 | 0.90 |
| IQUV | 1024 | 0.64 | 0.96 | 1.60 | 2.88 |
| IQUV | 2048 | 2.00 | 3.26 | 5.70 | 10.72 |

`*`: peak working set (the Stokes I joined-channel path has no buffer
report). On these 1.5 M cells per polarisation the images and beams
dominate: joined IQUV grows as channels × polarisations × n². The
visibility axis (IQUV, 8 channels, 1024², masked) adds the data: 3.86, 5.16
and 7.56 GB on 9.5, 19 and 38 M cells per polarisation, 33 B per cell and
polarisation, of which the buffer table names 12 (dense visibility and
weight) plus 8 (sorted index); the rest is the stored sorted values and the
permutation the first residual adds (12 B per active visibility).

**J1833−2103, before any fix** (the instrumented binary `2eec8c1`, A5's
argv plus `-memory-report`; `j1833/base-bin`):

| Phase | Heap held at its end | Most during | Peak working set so far |
| --- | ---: | ---: | ---: |
| read (all four polarisations, whole band) | 6.67 | 13.58 | 10.36 |
| weights (all 32 entries built) | 7.56 | 14.81 | 14.82 |
| PSFs, beams, first residuals; cycle 1 minor | 20.19 | 20.23 | 20.25 |
| cycles 2-5 (minor, then the major cycle) | 20.19 | 21.65 | 21.70 |
| after the clean | 17.97 | 21.66 | 21.70 |
| write | 3.49 | 17.97 | 21.70 |

GB of 10⁹. Buffers held through the clean, summed over the 32 entries:

| Buffer | GB |
| --- | ---: |
| measurement visibilities (dense, `c32`) | 3.77 |
| measurement weights (dense, `f32`) | 1.88 |
| gridder sorted index (8 B × 270 M active visibilities) | 2.16 |
| gridder stored sorted values + permutation (12 B × 270 M, from the first residual on) | 3.24 |
| gridder tables | 0.54 |
| uvw, baselines | 0.04 |
| 8 beams (exterior 1.07, spectrum 1.07) | 2.15 |
| 8 PSF crops | 0.27 |
| joined loop: 6 image sets of 32 × 33.5 MB (5 in the minor cycle) | 6.44 |

Sum 20.5, against the 21.7 GB peak (allocator slack and per-thread
buffers). 33,880 rows are read, 4,096 channels; 270 M of the 32 × 15.9 M
cells have nonzero weight (54 %). Wall 416.6 s, 3.38 cores; peak working
set 20.21 GiB and peak private bytes 20.25 GiB (`memtime.py`): A5's
figure (20.24 GiB, `a5_time.py`, the wheel) reproduced by the binary. The
153 FITS files' SHA-256 are the identity reference
([receipts/j1833-base-bin-fits.sha256](results/gemclean-memory/receipts/j1833-base-bin-fits.sha256)).

## 4. Decision rule (frozen before any fix)

- **Outputs.** Every FITS file of the J1833−2103 run and of the regression
  case must be **byte-identical** to the run before the fix (SHA-256 of
  every file), with the same binary flags, `-j` and host. None of the fixes
  planned changes arithmetic, so no tolerance applies; if one turns out to
  change any byte, it is dropped or re-scored against WSClean within A5's
  frozen 3c tolerances and labelled post hoc here.
- **Run-to-run identity first.** Two runs of the same build on the small
  case must be byte-identical, or byte identity cannot be the gate.
  Met: two runs of `2eec8c1` at `-j 4` on the 16-antenna case
  (512², 4 channels, IQUV joined, masked; [rep.sh](results/gemclean-memory/rep.sh))
  give the same 85 files.
- **Seen before the freeze.** Fixes 1-3 and part of 5 were written while the
  J1833 baseline ran, and one development build of them gave the same 85
  files on that small case. No J1833 run and no measurement of memory was
  made with them.
- **Target.** Bit-identical outputs put a floor under the peak (section
  3): the beams (2.15 GB), the PSF crops (0.27 GB), three `f64` image sets
  the minor cycle cannot do without (model, residual, working map: 3.2 GB)
  and the visibilities with one shared plan per channel (about 3.4 GB) are
  about 9 GB on J1833−2103. WSClean's 1.4 GB × 3 = 4.2 GB cannot be
  reached without changing the arithmetic. The target is **J1833−2103 at
  most 10 GiB peak** measured as A5 measured it (summed tree resident set
  of `python -m rang.gemclean`, `-j 4`, `memtime.py`), against 20.24 GiB
  before: at least 2 × lower. Below that needs `f32` images or visibilities
  on disk (WSClean's route); both change bits and are not in this task.
- **Time.** Wall time within 10 % of the run before the fix on J1833−2103
  (reported; a larger cost is reported and the fix that causes it named).
- **Paths.** The GPU gridder (`--features gpu`) builds and its tests pass;
  any change to the CPU gridder that the GPU path shares keeps them equal.
- **Regression test.** A small joined-IQUV case whose heap peak (the
  binary's counting allocator, deterministic at fixed `-j`) must stay under
  a bound frozen at 1.2 × the fixed value; it fails on any return of the
  removed copies.

Planned fixes, none changing arithmetic, with the J1833 saving the
accounting predicts:

1. The read: build each polarisation's entries and measurements as soon as
   its data are read, then drop the data, instead of holding all four
   polarisations' band and all 32 entries at once (the 14.8 GB read and
   weights peak).
2. Measurements keep only the active visibilities and their weights, in the
   gridder's sorted order, and drop the dense arrays after the plan is made
   (the residual reads them by sorted index; the misfit is still summed in
   visibility order through the permutation): 5.65 to 3.24 GB.
3. The gridder's stored sorted values are freed with the grids after every
   residual (they are rewritten in full by the next): 2.16 GB.
4. Polarisations of a channel with the same rows and weights (all four
   here) share one gridder plan (sorted index, permutation, tables) and
   one sorted weight array: about 3.6 GB.
5. The joined loop drops the working maps before the major cycle and
   writes each new residual in place; the major-cycle models are kept only
   at the pixels the minor cycle touched (the resync's difference is `0.0`
   elsewhere, as before); the dirty images wait in a file beside the
   outputs until they are written: up to 3 image sets, 3.2 GB.

## 5. The fixes, measured (2026-11-15)

All five planned fixes are in (commit `c06cdd1`), plus one found by the
first measurement (post hoc, dated 2026-11-15, before the final runs): the
MS reader's chunks are bounded to about 256 MB of complex cells (it read
20,000 rows at a time, 7 GB of transient buffers at 4,096 channels × 4
correlations, while the earlier polarisations' measurements were held:
14.2 GB heap at the fourth polarisation's read in the first fixed run).
Rows are independent, so the chunk size changes no value.

**Identity.** Every FITS file byte-identical to the run before the fix:

| Case | Files | Result |
| --- | ---: | --- |
| 16-antenna case, 512², 4 ch, IQUV, masked (`rep.sh`), fixes 1-5 | 85 | identical |
| regression case (`core/tests/gemclean_memory.rs`), 256², 4 ch | 85 | identical |
| J1833−2103, A5's argv, fixes 1-5 (binary) | 153 | identical |
| J1833−2103, fixes 1-5 + reader chunks (binary, built by Rust 1.93; the reference by 1.99) | 153 | identical |
| J1833−2103, the wheel (`python -m rang.gemclean`, this branch's extension) | 153 | identical |

**Option sweep** (post hoc, 2026-11-15, after the J1833 runs:
[sweep.py](results/gemclean-memory/sweep.py), receipt
[receipts/sweep.json](results/gemclean-memory/receipts/sweep.json)). The
cases above all have the four polarisations sharing rows and weights, MF
weighting and joined polarisations. On G8's tiny MS (8 antennas, 8
channels, W1's per-correlation flags and weights, so I and Q share one
beam and U and V another: the lookup also finds a non-first polarisation)
the binary before (`2eec8c1`) and after (`c06cdd1`'s build) give the same
exit code, FITS files, report `entries` and mask record on all 20 cases:
joined IQUV with MF weighting, masked, per-channel weighting, one output
channel, `-fit-spectral-pol 2`, `-no-plan-reuse` and `-double`; joined
`XX,YY` and `QU`; unjoined IQUV with MF weighting (weights from every
polarisation), per-channel weighting and one channel; and unjoined IQUV
with `-audit` or `-auto-mask`, which both refuse with the same message (so
no reachable path needs a compacted measurement's dense arrays); and Stokes
I without `-pol` (added in a second sweep: plain, masked, `-channels-out
2`, joined channels, joined and masked, `-fit-spectral-pol 2`), which shares
the joined loop, the gridder's freed buffers and the reader's chunks. The
reference binary of the second sweep was rebuilt from `2eec8c1`. No
`.spill` file is left after a run that ends normally; one that fails in
the clean leaves it beside the outputs. On J1833−2103 the report's
`entries` and `image-mask.json` are also equal.

New unit test `compacted_and_shared_measurements_keep_the_bits`
(`measure.rs`: compacted and plan-sharing measurements against the dense
one, residual images and misfits bit for bit, both precisions), beside the
existing `sorted_residual_has_the_bits_of_the_dense_one`. The GPU
gridder is separate code (`core/src/gpu`) and not changed; with
`--features gpu` the core builds and its 6 `gpu` tests pass (filtered run,
`cargo test --features gpu --lib gpu`); the full check's gpu steps are left
to the coordinator's merge check. Pytest on this branch's extension:
`test_g8_gemclean`, `test_g8_identity` (the wheel against the source
binary, byte for byte), `test_g6_model`, `test_g7_defaults`,
`test_w4_unsupported`, `test_w2_commands`, `test_e5_final`: 64 passed, 3
skipped, 1 xfailed.

**Memory and time on J1833−2103** (4 slots, `-j 4`):

| Run | Peak heap (GB) | Peak working set (GiB) | Peak private (GiB) | Sampled tree RSS (GiB, A5's measure) | Wall (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| before (binary `2eec8c1`) | 21.66 | 20.21 | 20.25 | 20.21 | 416.6 |
| A5 (wheel, `b7c4cca`) | – | – | – | 20.24 | 430.2 |
| fixes 1-5 (binary) | 14.17 | 10.19 | 13.23 | 9.51 | 398.2 |
| fixes 1-5 + reader chunks (binary) | 9.82 | 9.19 | 9.20 | 9.18 | 419.0 |
| the same, the wheel | – | 9.20 | 9.22 | **9.20** | 398.3 |
| WSClean 3.7 (A5, masked) | – | – | – | 1.34 (1,402,732 kB max RSS) | 1,076 |

Buffers held through the clean after the fixes (GB): visibilities 2.16
(sorted, active only), weights 0.27 and sorted index 0.54 (one per
channel, shared by the four polarisations), tables 0.14, beams 2.15, PSF
crops 0.27, three image sets 3.2.

**Regression test.** `core/tests/gemclean_memory.rs` (in `cargo test` for
`core/`, so in the `tests` workflow's Linux `rust` job, where it passed on the first push, run 43712203693): 24 MeerKAT antennas, 40 dumps, 64
channels, 70 % of the cells at zero weight, 256², `-pol IQUV
-join-polarizations -channels-out 4 -join-channels -auto-mask 5 -j 2`. Peak
heap 149,499,552 bytes before, 101,622,308 after; bound frozen at
122,000,000 (1.2 × after), so the run before the fix fails it. Only that
whole return was shown to fail (2026-11-15): a single copy coming back may
stay under the bound (the case's images are 0.5 MB each). The bound
was measured on Windows (the binary's `CountingAlloc`); Linux counts the
same requested bytes through `HugePageAlloc`.

**Outcome under the frozen rule.** **met.** J1833−2103 peaks at 9.20 GiB by A5's measure
(the wheel; 9.20 GiB peak working set, 9.22 GiB peak private bytes)
against 20.24 GiB before: 2.2 × lower, under the 10 GiB target, with all
153 FITS files byte-identical. Wall 398.3 s against A5's 430.2 s (the
binary: 419.0 s against 416.6 s, +0.6 %), within the 10 % rule. It is
still 6.9 × WSClean's 1.34 GiB on this field: the rest is three `f64`
image sets, the beams and the in-memory visibilities (section 4).

Not measured here: J1331+3030 and J1939−6342 (40.3 and 44.9 GiB in A5).
They have more rows; the visibility part scales with them and the image
and beam part does not, so their saving should be at least as large, but
it is not a result. The Stokes I paths gain only the gridder's freed
stored values and the joined clean's fewer copies (`-channels-out
-join-channels`); their measurements are not compacted.

**Booking.** A joined-IQUV 8-channel 2048² run on J1833−2103 now needs
about 10 GB, not 24-46 GB. J1331+3030 and J1939−6342 keep the 46 GB
booking until they are measured; the estimate is about 12 B per weighted
visibility and polarisation plus 6 GB for images and beams at 2048² × 8
channels.

**Next, not in this task** (each changes bits, so each needs its own
proposal and tolerance): `f32` working images; the visibilities on disk
between major cycles (WSClean's route); a band-limited beam spectrum by
default (`-beam-band`, measured in G1).

## For the coordinator

- **#32: met at byte-identical output.** J1833−2103 (A5's argv) peaks at
  9.20 GiB against 20.24 GiB (2.2 ×), WSClean 1.34 GiB (6.9 ×); 153 FITS
  files identical, wall 398 s against 430 s.
- Fixes in `c06cdd1`: per-polarisation read and build, compacted sorted
  measurements, shared plans across polarisations, freed gridder buffers,
  sparse major-cycle models, dirty images in a `.spill` file, bounded
  reader chunks. `-memory-report` now works on Windows.
- Regression test `core/tests/gemclean_memory.rs` (peak heap ≤ 122 MB;
  149.5 MB before) runs in CI's `cargo test`.
- Identity also on a 20-case option sweep (Stokes I included) (unjoined, per-channel
  weighting, `-fit-spectral-pol`, `-no-plan-reuse`, `-double`, `XX,YY`,
  `QU`, polarisations with different weights). Full check and gpu steps
  left to the merge check.
- Owner: J1833−2103 can be booked at about 10 GB; J1331 and J1939 keep 46
  GB until measured. WSClean × 3 (4.2 GB) is below the floor of
  bit-identical arithmetic; going below about 9 GB needs `f32` images or
  on-disk visibilities (a new proposal, bits change).
