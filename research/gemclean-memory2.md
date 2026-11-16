# GeMClean's memory on joined polarisations, phase 2 (issue #32)

Status: **implemented and measured, partly met** (2026-11-16). Sections
1-5 were frozen before any code (`b10d485`); measurements are in section 6.
With `-reorder`, J1331+3030 goes from 15.87 to 9.12 GiB and J1939−6342 from
16.46 to 9.10 (both met), and J1833−2103 from 8.40 to 7.17 (not met). Every
FITS file is byte-identical, and the option is off by default.

Branch `gemclean-memory2`, worktree `~/Worktrees/rang/gemclean-memory2`,
from `main` 6909a31. Data and run outputs in
`D:\rang\outputs\gemclean-memory2-20261116`; scripts in
[results/gemclean-memory2/](results/gemclean-memory2/). Phase 1:
[gemclean-memory.md](gemclean-memory.md).

## 1. The problem

Phase 1 took GeMClean's joined-IQUV peak on arm A5's argv
(`-pol IQUV -join-polarizations -channels-out 8 -join-channels -auto-mask 5`,
2048², 2″, `-j 4`) from 20.2 to 9.2 GiB on J1833−2103 at byte-identical
output. E2-B's 9.28 re-run (`e2b-misses.md` 9.29, after #32) measured the
summed tree resident set (A5's measure, `a5_time.py`):

| Field | GeMClean clean (GiB) | WSClean 3.7 clean (GiB) | Ratio | GeMClean wall | WSClean wall |
| --- | ---: | ---: | ---: | ---: | ---: |
| J1331+3030 (113,960 rows read) | 14.56 | 1.94 (2,038,720 kB) | 7.5 | 1,028 s | 1,826 s |
| J1939−6342 (115,500 rows) | 16.7 | 1.95 (2,048,280 kB) | 8.6 | 983 s | 1,220 s |
| J1833−2103 (33,880 rows) | 9.2 | 1.34 (1,405,052 kB) | 6.9 | 422 s | 893 s |

Shared-host readings; GeMClean native on Windows, WSClean in WSL docker on
2 slots. The two large fields still book 30 GB.

Phase 1's buffer table on J1833−2103 (after its fixes, held through the
clean, GB of 10⁹): compacted sorted visibilities 2.16, sorted weights 0.27,
sorted index 0.54, gridder tables 0.14, beams 2.15, PSF crops 0.27, three
`f64` image sets 3.2; the peak (9.8 GB heap) is at the end of the clean,
when the dirty images come back from their file beside those sets.

WSClean keeps the visibilities in reordered temporary files (one per output
channel and polarisation, read again in every major cycle) and its images
in `f32`. GeMClean holds every entry's visibilities in memory for the whole
run, and reads a polarisation's whole band before building its entries.

## 2. Accounting on the three fields (before any code of this task)

Inputs rebuilt as 9.28 built them
([prep_queue.sh](results/gemclean-memory2/prep_queue.sh),
[prep_run.sh](results/gemclean-memory2/prep_run.sh),
[prep_win.py](results/gemclean-memory2/prep_win.py): 9.28's `c3_run.sh` and
`c3_win.py` with this task's paths; CASA's applycal, the 2b compare and the
WSL copy back are left out, as GeMClean reads none of their columns). C11
met: E's DATA and (FLAG, FLAG_ROW) hashes equal `c2b/hash_src.json`. Each
field's D: copy has rang's apply into `E2C_RANG_CORRECTED_DATA` from this
worktree's build of main 6909a31. The copies' file lists differ from 9.28's
in the main table's storage-manager files (FLAG is written by `make` here,
by `casa_done` there), so 9.29's runs are not claimed to be on these bytes;
every comparison below is against this task's own baseline.

J1939−6342's baseline was still running at the freeze (`b10d485`); its
column was filled in after it, on 2026-11-16 before any arm run on E2-B
data. The rule is relative to it, so the freeze does not depend on its
value.

Baseline: main 6909a31's `gemclean` binary (`bin/gemclean-base-6909a31.exe`,
Rust 1.99.1), A5's argv plus `-memory-report`
([field.sh](results/gemclean-memory2/field.sh),
[memtime.py](results/gemclean-memory2/memtime.py)), 4 slots, shared host.
Heap in GB (10⁹; the binary's counting allocator, bytes asked for);
memtime.py's figures in GiB.

| Phase (heap GB, most during) | J1331+3030 | J1939−6342 | J1833−2103 |
| --- | ---: | ---: | ---: |
| read (first polarisation's whole band) | 6.14 | 6.22 | 2.20 |
| weights (MF imaging-weight cache, band-sized `f32`) | 7.50 | 7.60 | 2.25 |
| build, highest (fourth polarisation: its band, the cache, every earlier entry) | **18.61** | **18.67** | 8.07 |
| minor cycles | 14.87 | 14.82 | 9.82 |
| end of the clean (dirty images back from their file) | 14.83 | 14.77 | **9.79** |

| Measure | J1331+3030 | J1939−6342 | J1833−2103 |
| --- | ---: | ---: | ---: |
| rows read | 113,960 | 115,500 | 33,880 |
| tree RSS peak (A5's measure, GiB) | 15.87 | 16.46 | 8.40 |
| peak working set / peak private (GiB) | 16.20 / 17.38 | 17.40 / 17.43 | 8.41 / 9.20 |
| wall (s) | 804.0 | 920.1 | 404.3 |

Buffers held through the clean (GB), J1331+3030: compacted visibilities
5.48, sorted weights 0.69, sorted index 1.37, tables 0.14, beams 2.15, PSF
crops 0.27, three image sets 3.2. J1833−2103's buffer table and heap phases
equal phase 1's to the printed digit (2.16, 0.27, 0.54, 0.14, 2.15, 0.27,
3.2), so the rebuilt input has phase 1's shape.

So on the two large fields the peak is in the **build**, not the clean: a
polarisation's whole band (12 B per row and channel, 5.6 GB), the
band-sized imaging-weight cache (1.9 GB) and every entry built so far,
visibilities included, are held at once. Visibilities in files alone (5.5
GB) would leave the build at about 13 GB. On J1833−2103 the peak is at the
end of the clean.

## 3. Hypothesis and arms

**Hypothesis.** GeMClean's joined-IQUV peak on A5's argv is set by data
held in memory that WSClean keeps in temporary files. Kept in files,
written once and read back where they are used, they leave the peak with
no change of arithmetic (each value read back is the value written, and
every operation runs in the same order), so every FITS file stays
byte-identical, at a wall-time cost of the file traffic on the NVMe D:
drive.

**Arm V** (new option `-reorder`, WSClean's name for its temporary
visibility files, off by default; new option `-temp-dir DIR` for the
files, default the directory of `-name`). Polarisation runs (`-pol` with
more than one polarisation) only; elsewhere `-reorder` changes nothing.

- **V1, the read.** Each polarisation is read in the reader's row chunks,
  and each chunk's cells (Stokes visibility `c32`, weight `f32`) are
  appended per output channel to a temporary file, instead of holding the
  whole band. The imaging-weight grids are filled from the same chunks, in
  the same polarisation and row order (the grid's sums are serial in that
  order); each entry's imaging weights are looked up from its grid for its
  own channels (`WeightGrid::lookup_rows` is per cell) instead of being
  sliced from a band-sized cache. Each entry is then built from its
  channel's file. Not with `-channel-range` or `-average-channels` (the
  band is then read as now).
- **V2, the measurements.** Each entry's compacted sorted visibilities
  (phase 1's fix 2) are appended to a temporary file when the entry is
  built and read back for each of its residuals (the first, then every
  major cycle), so one entry's visibilities are held at a time. The sorted
  index, sorted weights and permutation stay in memory.
- **V3, the end.** The measurements and beams are dropped before the dirty
  images come back from their file and the images are written.
- Every temporary file is removed when the run ends, also on an error
  return; a killed process leaves them behind (`<name>-*.tmp`).

Predicted heap peak with V (section 2's buffers): J1331+3030 and
J1939−6342 about 8.5-9 GB (in the minor cycles: three image sets, beams,
plans), J1833−2103 about 5.5-6 GB; the build phases below that.

**Arm F** (separate option: `f32` working images, the per-entry residual,
model and working maps in `f32` as WSClean's). It changes bits, so it has
its own tolerance (section 5), and saves at most half the image sets,
about 1.6 GB at 2048² × 32 entries. It runs only after V is measured; if it
is not run in this task it stays proposed.

Not in this phase: the plans (sorted index, weights, permutation; 2.7 GB on
J1331+3030) in files, and the beams (2.15 GB, used in every minor step).

## 4. Data, runs and measures

- **Data:** the three E2-B calibrator fields as rebuilt in section 2
  (`f0.ms`, `f1.ms`, `f2.ms` in the output directory), with A5's argv
  (`field.sh`): `-size 2048 2048 -scale 2asec -weight briggs 0.0
  -channels-out 8 -join-channels -pol IQUV -join-polarizations
  -data-column E2C_RANG_CORRECTED_DATA -field F -scans 17,18,19,20
  -unit-weights -no-update-model-required -j 4 -niter 1000000 -mgain 0.9
  -auto-threshold 3.0 -auto-mask 5 -wgridder-accuracy 0.0001`, plus
  `-memory-report` and the arm's option.
- **Runs:**
  - the baseline binary (section 2) and this branch's binary with
    `-reorder`, on each field;
  - this branch's binary without `-reorder` on J1833−2103 (the default
    path unchanged);
  - the adopted arm once through the wheel (`python -m rang.gemclean`) on
    J1833−2103.
- **Measures:**
  - memtime.py's summed tree RSS (A5's measure), and the largest process's
    peak working set and peak private bytes (GiB);
  - the binary's heap by phase (GB), the wall time and the temporary bytes
    written;
  - SHA-256 of every FITS file, the report's `entries` and
    `image-mask.json`.
- Reads are buffered, not mapped, so file data sits in the OS page cache,
  outside every one of these figures.
- Memory and time are shared-host readings (other jobs ran on the host).
  Exclusive timing is left to the coordinator:
  `python tools/heavy_lock.py run -- "C:/Program Files/Git/bin/bash.exe" research/results/gemclean-memory2/field.sh F TAG BIN [-reorder]`
  for F in 0, 1 and 2, and BIN the baseline and the branch binary.
- **Regression:** `core/tests/gemclean_memory.rs` gains a
  visibility-dominated case run with and without `-reorder`. The FITS
  files must be byte-identical, the `-reorder` heap peak must stay under a
  frozen bound that the run without it exceeds, and no temporary file may
  be left.

## 5. Decision rule (frozen before any code)

- **Arm V, identity (gate).** On each of the three fields, every FITS
  file (153 per field), the report's `entries` and `image-mask.json` are
  byte-identical to the baseline's. This branch without `-reorder` is
  byte-identical to the baseline on J1833−2103 and on the regression case.
  Any differing byte fails V, and V is then not re-scored under a
  tolerance in this task.
- **Arm V, memory.** The tree RSS peak (A5's measure) is at most **0.6 ×
  the baseline** on J1331+3030 and J1939−6342, and at most **0.75 ×** on
  J1833−2103: at most 9.52, 0.6 × J1939−6342's baseline (9.88, filled in after the freeze) and 6.30 GiB. It is reported
  beside as a ratio to WSClean 3.7's 1.94, 1.95 and 1.34 GiB (9.29).
- **Arm V, time.** Wall at most 1.10 × the baseline's on the same field
  (shared host, reported as such). A larger cost is reported with the file
  traffic that causes it, and V is then "met on memory, not on time", for
  the coordinator's exclusive timing to settle.
- **Outcome.**
  - **Met:** the identity gate, the memory rule and the time rule hold on
    all three fields.
  - **Partly met:** identity holds, and memory or time fails on some field
    (each named).
  - **Not met:** identity fails, or no field meets memory.
- **Default.** If V is met, the coordinator may make `-reorder` the
  default for polarisation runs, in a later separate commit with
  `-no-reorder` to switch it off. This task leaves it opt-in.
- **Arm F (if run).**
  - Against the `f64` path (V's images): for each MFS image (dirty,
    residual, restored; I, Q, U, V), the L∞ of the difference is at most
    1 % of the `f64` image's peak |I|, and the rms of the restored
    difference is at most 0.1 × the `f64` residual's rms.
  - Against WSClean 3.7 (oracle), on 9.28's frozen 3c cleaned measures
    (`c3_score.py clean-field`, with WSClean rerun on the same copies):
    each measure the `f64` path meets is still met, and the compact robust
    scatter is at most 0.1 percentage point above the `f64` path's.
  - Memory: tree RSS at least 1 GiB below V's on each field.
  - Met when all of these hold; otherwise not met, with each number.
- **Booking.** Baselines at 13 GB (J1833−2103) and 20 GB (the large
  fields), measured plus margin. V runs keep the baseline's booking until
  measured.

## 6. Measured (2026-11-16)

Code: arm V at `42ad6c6` (binary `bin/gemclean-v-42ad6c6.exe`, Rust
1.99.1). The binary held V1-V3 together, so the three parts are not
measured apart. Runs: [field.sh](results/gemclean-memory2/field.sh) under
the heavy lock, 4 slots, shared host (other jobs ran throughout). Scoring:
[compare.py](results/gemclean-memory2/compare.py). Receipts:
[receipts/](results/gemclean-memory2/receipts/) (`<field>-<run>-*`).

**Identity (gate): met.**

| Case | Files | Result |
| --- | ---: | --- |
| J1331+3030, `-reorder` against the baseline | 153 | identical; `entries` and `image-mask.json` equal |
| J1939−6342, `-reorder` | 153 | identical; `entries` and mask equal |
| J1833−2103, `-reorder` | 153 | identical; `entries` and mask equal |
| J1833−2103, this branch without `-reorder` | 153 | identical; `entries` and mask equal; heap phases equal to the baseline's to the printed digit |
| G8's tiny MS, 21 cases ([sweep.py](results/gemclean-memory2/sweep.py), [receipts/sweep-v1.json](results/gemclean-memory2/receipts/sweep-v1.json)): baseline, branch, branch with `-reorder -temp-dir` | 0-85 per case | all identical in both comparisons (two cases refuse with the same message in all three); no `.tmp` or `.spill` file left |
| regression case (`core/tests/gemclean_memory.rs`), with and without `-reorder` | 85 | identical |
| J1833−2103, the wheel (`python -m rang.gemclean -reorder`, this branch's extension at `04e3a86`) | 153 | identical; mask equal; 7.18 GiB tree RSS, 7.19 private, 330.9 s |

The sweep was run with a development build of the same code
(`gemclean-v1.exe`, before `cargo fmt`).

**Memory and time** (tree RSS is A5's measure; GiB; shared host):

| Field | Baseline RSS | `-reorder` RSS | Ratio | Rule | Peak private, before → after | WSClean 3.7 | × WSClean | Wall, before → after |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| J1331+3030 | 15.87 | **9.12** | 0.575 | ≤ 0.6: **met** | 17.38 → 9.14 | 1.94 | 4.7 | 804.0 → 791.1 s (0.98) |
| J1939−6342 | 16.46 | **9.10** | 0.553 | ≤ 0.6: **met** | 17.43 → 9.12 | 1.95 | 4.7 | 920.1 → 880.8 s (0.96) |
| J1833−2103 | 8.40 | **7.17** | 0.854 | ≤ 0.75: **not met** | 9.20 → 7.19 | 1.34 | 5.4 | 404.3 → 335.1 s (0.83) |

- **Where the peak now is:** in the minor cycles and the major cycle's
  residuals. The heap peaks at 9.39 / 9.37 / 7.66 GB: three image sets
  (3.2), beams (2.15), PSF crops (0.27), the plans (J1331+3030: index
  1.37, weights 0.69, permutation 0.69, tables 0.14) and one entry's
  residual transients.
- **Build and read:** the build peaks at 6.6 / 6.6 / 4.7 GB (from 18.6 /
  18.7 / 8.1), and the read at 0.77 GB (from 6.1-6.2).
- **Why J1833−2103 misses:** the prediction (5.5-6 GB) left out the minor
  cycle's working maps and the major cycle's transients. On this field the
  visibilities were only 2.2 of the 9.8 GB.
- **The baseline's RSS on J1833−2103 is low.** The same binary without
  `-reorder` read 9.18 GiB with the same heap phases and the same peak
  private bytes (9.20), so the baseline's 8.40 is the working set trimmed
  on a loaded host. Against that run the ratio is 0.78, which still misses
  0.75. The frozen measure is kept.
- **Files written per run:**
  - the read file, 12 B per row, channel and polarisation: 22.4, 22.7 and
    6.7 GB;
  - the visibility file: 5.48, 5.44 and 2.16 GB, read back once per
    residual (6 times).
  - The read and weights phases take 89.6 / 85.3 / 23.7 s read and 37.8 /
    31.4 / 9.7 s weights, against 83.4 / 66.0 / 27.4 s and 32.3 / 15.2 /
    5.7 s.
  - Each run's wall is lower than the baseline's. The host load differed,
    so this is no speed claim.

**Regression test.** `reorder_keeps_the_bytes_and_lowers_the_peak_heap`
(24 antennas, 120 dumps, 128 channels, 128², `-pol IQUV
-join-polarizations -channels-out 4 -join-channels -auto-mask 5 -j 2`):
- peak heap 351,758,344 bytes without `-reorder`, 232,370,794 with;
- bound frozen at 279,000,000 (1.2 × with), so a return of the in-memory
  path fails it;
- FITS byte-identical and no temporary file left;
- 315 s in a debug `cargo test` on this host;
- the phase 1 case still passes (101,622,276 bytes).
- **Post hoc, 2026-11-17:** on Linux (the `tests` workflow, run
  43966049067, `HugePageAlloc`) the case peaked at 282,702,156 bytes with
  `-reorder` and 402,089,822 without, so the Windows bound failed there.
  Linux now has its own bound, 339,000,000 (1.2 × its value). The run
  without `-reorder` exceeds it, and the Windows bound is unchanged.

**Outcome under the frozen rule: partly met.**
- Identity holds everywhere.
- Memory is met on J1331+3030 (0.575) and J1939−6342 (0.553), and not met
  on J1833−2103 (0.854 against 0.75).
- Time is met on all three.
- So `-reorder` stays opt-in. Making it the default is the coordinator's
  call, outside this rule's "met" branch.
- The two large fields can be booked at about 11 GB with `-reorder`,
  against 20-30 GB without it.

**Arm F: not run** (proposed). The `f32` working images need the joined
loop, the kernels and the beams made generic over the image precision. It
is not started in this task, and section 5's rule for it stands for a later
one. After V, the image sets (3.2 GB) and the beams (2.15 GB) are 60-70 %
of every field's peak, so they are the next target. The plans (up to 2.9
GB) are next after them.

**Exclusive timing (for the coordinator).** On an idle host, for F in 0, 1
and 2, run
`python tools/heavy_lock.py run -- "C:/Program Files/Git/bin/bash.exe" research/results/gemclean-memory2/field.sh F TAG BIN [-memory-report] [-reorder]`
with BIN `D:/rang/outputs/gemclean-memory2-20261116/bin/gemclean-base-6909a31.exe`
(TAG `x-base`) and `.../gemclean-v-42ad6c6.exe -reorder` (TAG
`x-reorder`). The inputs `f0.ms`, `f1.ms` and `f2.ms` are kept for this
(75 GB on D:) until the coordinator says they can go.

## For the coordinator

- #32 phase 2: **partly met** under the frozen rule, at byte-identical
  output (153 FITS files per field, `entries` and the mask equal).
- `-reorder` (opt-in, with `-temp-dir`) keeps the per-channel read and the
  compacted visibilities in temporary files.
- Tree RSS: J1331+3030 15.87 → 9.12 GiB, J1939−6342 16.46 → 9.10, both
  met; J1833−2103 8.40 → 7.17, not met (0.854 against 0.75).
- Wall time is not higher on any field (shared host). It is 4.7-5.4 ×
  WSClean's 1.34-1.95 GiB.
- Next memory: the `f32` images (arm F, not run) and the beams, which are
  now about two thirds of the peak.
- Booking with `-reorder`: about 11 GB on every field.
