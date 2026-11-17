# GeMClean's memory on joined polarisations, phase 3 (issue #32)

Status: **implemented and measured, met** (2026-11-17). With arms A and B, J1833−2103 with `-reorder` peaks at 5.73 GiB (0.682 × 8.40, limit 6.30), every FITS file byte-identical; `-reorder` is now the default with `-join-polarizations` (`-no-reorder` to switch off).
Sections 1-5 were frozen before any code of the arms (`7b3b627`); measurements are in section 6.

Branch `gemclean-memory3`, worktree `~/Worktrees/rang/gemclean-memory3`,
from `main` 9b4542c. Inputs: phase 2's rebuilt E2-B fields
`D:\rang\outputs\gemclean-memory2-20261116\f?.ms` (read only). Run outputs
in `D:\rang\outputs\gemclean-memory3-20261117`; scripts in
[results/gemclean-memory3/](results/gemclean-memory3/). Phase 1:
[gemclean-memory.md](gemclean-memory.md); phase 2:
[gemclean-memory2.md](gemclean-memory2.md).

## 1. The problem

Phase 2's opt-in `gemclean -reorder` keeps the read and the compacted
visibilities in temporary files. On A5's argv (joined IQUV, 8 joined
channels, 2048², `-auto-mask 5`, `-j 4`) it met its 0.6 × rule on
J1331+3030 and J1939−6342 (0.575, 0.553). It missed the 0.75 × rule on
J1833−2103: 8.40 → 7.17 GiB tree RSS (0.854; limit 6.30 GiB), at
byte-identical output. Phase 2 attributed the rest to three image sets,
beams, PSF crops and the plans, but did not trace the peak itself.

## 2. Attribution of J1833−2103's peak (before any arm)

Commit `7be8c95` adds a tracer to `-memory-report` (no algorithm change).
The counting allocator keeps the live blocks of 1 MiB or more by exact
size and copies that table whenever the heap reaches a new high. The run:
binary `bin/gemclean-trace-7be8c95.exe`, `field.sh 2 trace-reorder ...
-memory-report -reorder`, 4 slots, shared host. All 153 FITS files,
`entries` and `image-mask.json` are byte-identical to phase 2's baseline
(`p2-base`, main 6909a31's binary) and to phase 2's `-reorder` run, so
phase 2's hashes stay the identity reference for this phase. Tree RSS
7.16 GiB, peak private 7.19 GiB, wall 380.3 s (shared).

The heap peaks at **7.662 GB** inside a resync of the minor cycle (the
phase ended by "cycle 2: minor"; every cycle's minor phase reaches
7.63-7.66). The blocks live at that moment:

| Blocks | Size (bytes) | GB | What they are |
| ---: | ---: | ---: | --- |
| 110 | 33,554,432 (n² `f64`) | 3.691 | 32 models, 32 residuals, 32 working maps, 8 PSF crops, and 6 single maps (integrated dirty, integrated residual, `Working::r`, the resync's `delta` and `conv`, one more) |
| 8 | 134,283,264 | 1.074 | beam spectra, 2n × (n+1) `c64` |
| 8 | 134,152,200 | 1.073 | beam exteriors, (2n−1)² `f64` |
| 8 | 67,141,632 | 0.537 | each beam's convolver row spectra, n × (n+1) `c64`: allocated at its first resync, kept to the end |
| 16 | 8,405,000 | 0.134 | gridder tables |
| 8 + 16 | per channel 1 × 8 B and 2 × 4 B per active visibility | 0.94 | the shared plans: sorted index (8 B), sorted weights (4 B) and visibility-order permutation (4 B), 8 channels |
| 3 | 4,194,304 | 0.013 | reader and file buffers |
| – | smaller blocks | 0.059 | |

The buffer table printed by `-memory-report` shows 0.000 for the row
spectra and the permutation: it is taken before the first residual and
the first resync, which make them. The major cycle's residuals peak lower
(held 7.0-7.2 GB): the same sets less the working maps, plus one entry's
gridder transients.

So 2.14 GB of the peak are buffers the arithmetic does not need in that
form: the models (32 dense images holding a few thousand nonzero pixels,
all at the same pixels, as every component goes into every entry) and 7
of the 8 row-spectra buffers (the resync convolves the entries one after
another, so one buffer serves all).

## 3. Hypothesis and arms

**Hypothesis.** J1833−2103's `-reorder` peak is set by the 110 image-sized
blocks, the beams and the row spectra of the minor cycle. Holding the
models sparse and one row-spectra buffer per run lowers the peak by about
1.5 GB with no change of arithmetic (the same operations on the same
values in the same order), so every FITS file stays byte-identical, at
no file traffic.

**Arm A, one row-spectra buffer.** The joined loop's resync passes one
work buffer to every beam's convolver (a `Convolver` method that takes
the buffer from the caller). The rows a convolution does not write are
marked zero in `nonzero` and never read, so another beam's earlier values
in them change nothing. The single-entry `run`, multiscale and the
Stokes I paths keep their own buffers. Saving: 7 × 67.1 MB = 0.47 GB.

**Arm B, sparse models.** In the joined loop the models are held as the
list of picked pixels (shared by every entry, in pick order), a pixel →
slot index, and per entry its values at those pixels. A step adds `c` to
the entry's value at the slot, starting from `0.0` as the dense image
does. Wherever a dense model is used (each residual of the major cycle,
the automatic mask's `from_models`, the integrated model and the
outcome), it is made from the sparse one, one entry at a time where the
use allows: the same array, so the same bits. Saving: 32 × 33.5 MB =
1.07 GB in the minor and in the major cycle.

A and B apply to every joined run, with or without `-reorder`, as neither
changes a value; no option.

**Predicted:** heap peak about 6.1 GB (in the minor cycle: 7.66 − 0.47 −
1.07), tree RSS about 5.7 GiB on J1833−2103 (0.68 × 8.40). The end of the
joined loop, where the dense models come back beside the beams, about 6.0
GB. Without `-reorder` the same saving applies.

**Arm C (fallback, run only if A + B miss the memory rule on
J1833−2103).** With `-reorder`, the residuals are kept in a temporary file
from their computation to their next use: each new residual is written as
it is made and the integrated residual summed entry by entry in channel
order (the same operations as `integrate`); the working maps are read from
it at the start of a minor cycle, and each resync reads its entry's
residual back. Saving about 1.07 GB, at about 1.07 GB read per resync (95
resyncs on J1833−2103, about 100 GB from the page cache), so it is
expected to cost wall time.

**Not in this phase:** `f32` working images (phase 2's arm F, changes
bits); the beams (2.15 GB, read in every minor step and every resync); the
plans (0.94 GB, used in every residual); the working maps (written in
every minor step).

## 4. Data, runs and measures

- **Data and argv:** phase 2's three fields and `field.sh` (A5's argv
  plus `-memory-report`), now in
  [results/gemclean-memory3/field.sh](results/gemclean-memory3/field.sh),
  which writes to this phase's output directory.
- **Binaries:** this branch's gemclean binary (`cargo build --profile
  gemclean --bin gemclean`, Rust 1.99.1 as phase 2); phase 2's baseline
  `gemclean-base-6909a31.exe` for the sweeps.
- **Runs (memory, shared host, 4 slots):**
  - J1833−2103 with `-reorder` and without, this branch;
  - J1331+3030 and J1939−6342 with `-reorder` and without, this branch
    (for the default rule);
  - J1833−2103 once through the wheel (`python -m rang.gemclean -reorder`).
- **Runs (time, exclusive lock, idle host):** each field with and without
  `-reorder`, this branch's binary, one run each; where the ratio falls in
  1.05-1.15, a second pair is run and the mean of each arm is used.
- **Measures:** memtime.py's summed tree RSS (A5's measure) and the
  largest process's peak working set and peak private bytes (GiB); the
  heap by phase and the traced blocks at the peak (GB); wall time;
  temporary bytes written; SHA-256 of every FITS file, the report's
  `entries` and `image-mask.json`.
- **Identity sweeps:** phase 2's `sweep.py` (21 cases on G8's tiny MS,
  joined and unjoined IQUV, `XX,YY`, `QU`, Stokes I joined and not,
  masked, fits, `-double`, `-no-plan-reuse`, `-channel-range`) with the
  baseline binary against this branch with and without `-reorder`, and
  its 6 cases on the regression test's two-chunk MS. The default leg
  matters as much as the `-reorder` leg, since A and B change the default
  path's code.
- **Gates:** `cargo test` for `core/` (the unit tests of the joined loop,
  the convolver and `gemclean_memory.rs`), and the gemclean pytest files
  run explicitly (`test_g6_model`, `test_g7_defaults`, `test_g8_gemclean`,
  `test_g8_identity`, `test_w2_commands`, `test_w4_unsupported`,
  `test_e5_final`), since `--quick` runs only the pytest files the diff
  touches.
- **Regression test:** `core/tests/gemclean_memory.rs` gains an
  image-dominated joined case (images, not visibilities, set the peak).
  Its bound is on the clean's peak heap in units of one n² `f64` image,
  frozen between the value before the arms (measured with main's code)
  and after them, so that it holds on Linux and Windows alike and a return
  of the dense models or of the per-beam row spectra fails it.

## 5. Decision rule (frozen before any code of the arms)

- **Identity (gate).** On each of the three fields, with and without
  `-reorder`, every FITS file (153 per field), the report's `entries` and
  `image-mask.json` are byte-identical to phase 2's baseline. Every sweep
  case is identical between the baseline binary and this branch, with and
  without `-reorder`. Any differing byte fails the arm that caused it,
  which is then dropped, not re-scored under a tolerance.
- **Memory (J1833−2103, `-reorder`).** Tree RSS (A5's measure) **at most
  6.30 GiB** (0.75 × phase 2's frozen baseline 8.40; the absolute number
  is kept, not re-based on the untrimmed 9.18), and peak private bytes at
  most 6.30 GiB too (the 2 s sampler can miss a resync's transient).
- **Time (J1833−2103, `-reorder`).** Wall at most 1.10 × phase 2's
  `-reorder` run (335.1 s, shared host), reported as such; the exclusive
  pairs below settle it.
- **Outcome of the phase.**
  - **Met:** identity and the memory and time rules hold with A + B (or A
    + B + C).
  - **Not met:** if A + B + C still miss, section 6 gives the traced peak
    that remains and the size of each buffer in it; below that the peak
    needs a change of arithmetic (WSClean's `f32` images, or the beams
    read from a file each minor cycle), which this phase does not make.
- **Default (frozen).** `-reorder` becomes the default for runs with more
  than one polarisation and `-join-polarizations` (exactly the runs
  where phase 2's `-reorder` acts and a joined clean follows), with a new
  `-no-reorder` to switch it off, only if all hold:
  1. identity as above, on all three fields and in every sweep case;
  2. memory: on each field the `-reorder` tree RSS is at most 0.8 × this
     branch's run without it, and within phase 2's limits (J1331+3030
     9.52, J1939−6342 9.88, J1833−2103 6.30 GiB);
  3. time: in the exclusive pairs, `-reorder`'s wall at most 1.10 × the
     same binary's without it, on each field;
  4. failure: a run whose temporary directory cannot be written stops
     with an error naming the file before any clean, and leaves no
     temporary file (checked with a `-temp-dir` that does not exist); the
     files' size (12 B per row, channel and polarisation read, plus 8 B per
     active visibility; about 28 GB on the large fields and 9 GB on
     J1833−2103) is stated in the help text and the CHANGELOG.
  If any fails, `-reorder` stays opt-in and the failing condition is
  named. A killed run leaves its files behind (`<name>-*.tmp`,
  `*.spill`), as in phase 2; this is documented, not a condition.
- **Booking.** Runs book 10 GB (J1833−2103) and 14 GB (the large fields)
  until measured; exclusive runs hold the whole host.

## 6. Measured (2026-11-17)

Code: arms A and B at `f20c06a` (binary `bin/gemclean-ab-f20c06a.exe`,
Rust 1.99.1); A and B were built and measured together, not apart. Arm C
was not needed and is not built. The default change is `bc62504`, after
the rule below was met. Scoring:
[compare.py](results/gemclean-memory3/compare.py) against phase 2's
baseline runs (`p2-base`, copied into this phase's `runs/`). Receipts:
[receipts/](results/gemclean-memory3/receipts/).

**Identity (gate): met.**

| Case | Files | Result |
| --- | ---: | --- |
| J1833−2103, `-reorder`, shared (`ab-reorder`) and exclusive (`x-`, `x2-reorder`) | 153 | identical to `p2-base`; `entries` and mask equal |
| J1833−2103, without `-reorder` (`x-`, `x2-plain`) | 153 | identical |
| J1331+3030 and J1939−6342, with and without `-reorder`, two exclusive runs each | 153 | identical |
| G8's tiny MS, 21 cases ([receipts/sweep-ab.json](results/gemclean-memory3/receipts/sweep-ab.json)): phase 2's baseline binary against `f20c06a` without and with `-reorder -temp-dir` | 0-85 | all identical in both legs (two cases refuse with the same message in all three); nothing left |
| the `-reorder` regression case's two-chunk MS, 6 cases ([receipts/sweep-regcase.json](results/gemclean-memory3/receipts/sweep-regcase.json)) | 17-51 | all identical in both legs; nothing left |
| the new image-dominated case (512², 4 channels, IQUV, masked): main's code (`7be8c95`) and `f20c06a`, with and without `-reorder` | 85 | identical |
| G8's 21 cases again with the default change (`bc62504`, [receipts/sweep-default.json](results/gemclean-memory3/receipts/sweep-default.json)): its default leg now runs `-reorder` for joined polarisations | 0-85 | all identical; nothing left |
| `core/tests/gemclean_memory.rs` (all three cases) | – | pass |
| J1833−2103 through the wheel, A5's argv with no `-reorder` flag (`python -m rang.gemclean`, this branch's extension at `bc62504`, so `-reorder` by default) | 153 | identical; mask equal; 5.78 GiB tree RSS, 5.78 private, 454.4 s (shared, 4 slots) |
| gemclean pytest files (`test_g6_model`, `test_g7_defaults`, `test_g8_gemclean`, `test_g8_identity`, `test_w2_commands`, `test_w4_unsupported`, `test_e5_final`, `test_d1_docs`) | – | 68 passed, 3 skipped, 1 xfailed |

**Memory, J1833−2103 with `-reorder` (the frozen rule).** Tree RSS
**5.73 GiB** in each of three runs (shared and two exclusive), peak private
5.76 GiB: **0.682 × 8.40**, under the 6.30 GiB limit; **met**. Heap peak
6.135 GB (from 7.662), in the minor cycle's resync as before. The traced
blocks at the peak: 78 n² images (2.62 GB: residuals 32, working maps 32,
PSF crops 8, single maps 6), beams 2.15, one row-spectra buffer 0.067, the
plans 0.94, tables 0.13. The end of the clean (dense models back beside
the beams) holds 5.94 GB, below the minor cycle's peak. Against WSClean
3.7's 1.34 GiB (phase 2, 9.29) this is 4.3 ×.

**Time, J1833−2103.** Shared, 380.2 s against phase 2's 335.1 s (1.135).
That reading is the host's load: the traced binary of main's code ran
380.3 s in the same hour. The exclusive pairs settle it: `-reorder` with
A and B runs 316.5 and 318.9 s, below phase 2's shared 335.1 s; **met**.

**All three fields, exclusive** (`heavy_lock.py run`, idle host, this
binary, `-memory-report`; tree RSS from pair 1, GiB; wall in s):

| Field | RSS without | RSS `-reorder` | Ratio (≤ 0.8) | Phase 2 limit | Peak private without → with | Wall without (2 runs) | Wall `-reorder` (2 runs) | Ratio of means (≤ 1.10) |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |
| J1331+3030 | 16.53 | **7.73** | 0.468 | 9.52 | 17.38 → 7.75 | 677.5, 682.0 | 712.0, 737.5 | 1.066 |
| J1939−6342 | 16.85 | **7.72** | 0.458 | 9.88 | 17.43 → 7.73 | 767.5, 784.3 | 817.5, 812.0 | 1.050 |
| J1833−2103 | 7.72 | **5.73** | 0.742 | 6.30 | 8.73 → 5.76 | 294.3, 354.9 | 316.5, 318.9 | 0.979 |

- All twelve exclusive runs ended by 14:34 host time on 2026-11-17, before
  the owner's order of that afternoon (no exclusive runs on this host
  before 21:00); none was stopped or voided, and none was left to
  reschedule. The work after it is shared only.
- Every first ratio fell in 1.05-1.15 (1.075, 1.051, 1.065), so every field
  got its second pair, as frozen.
- J1833−2103's second run without `-reorder` (354.9 s) is 21 % slower than
  its first on an idle host, unexplained; with its first run alone the
  ratio would be 1.075, still under 1.10.
- The sampled RSS of J1833−2103 without `-reorder` (7.72) is below its
  peak private bytes (8.73): the 2 s sampler missed the end-of-clean peak
  (9.33 GB heap, the dirty images back beside the beams). Against peak
  private the ratio is 0.66.
- Where `-reorder`'s time goes: the read and the imaging weights take
  75.96 + 27.15 s against 60.79 + 13.67 s on J1331+3030 (+28.7 s of the
  +45 s), 81.72 + 30.48 against 64.85 + 13.98 on J1939−6342 (+33.4 of
  +39), 21.32 + 7.68 against 17.13 + 3.81 on J1833−2103 (the per-channel
  temporary files; pair 1's logs).
- Arms A and B also lower the in-memory path's minor cycles (J1833−2103
  without `-reorder`: heap peak 9.33 GB against phase 2's 9.79, now at the
  end of the clean); its peak on the large fields stays in the build
  (18.6 GB).
- The large fields' `-reorder` heap now peaks at 8.27 / 8.26 GB in the
  first residuals (from 9.39 / 9.37).

**Outcome under the frozen rule: met** (identity, memory 0.682 against
0.75, time).

**Default: met, and made.** Conditions:
1. identity on all three fields with and without `-reorder`, and in every
   sweep case;
2. memory 0.468 / 0.458 / 0.742 (≤ 0.8), within 9.52 / 9.88 / 6.30 GiB;
3. time 1.066 / 1.050 / 0.979 (≤ 1.10);
4. failure: `-temp-dir` naming a directory that does not exist stops
   during the read (`...\g-read-51208.tmp: The system cannot find the path
   specified`, exit 2), before any clean, and leaves no file.

So `-reorder` is now the default when `-pol` has more than one
polarisation and `-join-polarizations` is given (`bc62504`), and
`-no-reorder` keeps the in-memory path. Unjoined polarisation runs keep
`-reorder` opt-in. The help text states the files' size. The two memory
tests that measure the in-memory path now pass `-no-reorder`; a unit test
covers the default's scope.

**Regression test.** `joined_clean_images_stay_under_the_frozen_bound`
(24 antennas, 40 dumps, 64 channels, 512², `-pol IQUV
-join-polarizations -channels-out 4 -join-channels -auto-mask 5 -j 2
-reorder`): the clean's peak heap is 105.86 images of 512² `f64` with
main's code (222,012,486 bytes) and 84.35 with A and B (176,898,150);
bound frozen at **89 images**, which a return of the dense models (+16)
or of the per-beam row spectra (+6) exceeds. The bound is in images, so it
should hold on Linux's allocator as on Windows'; the first CI run checks
that.

**Not done:** arm C (not needed); `f32` images (phase 2's arm F); the
beams (2.15 GB) and plans (0.94 GB), now 50 % of J1833−2103's peak.

## For the coordinator

- #32 phase 3: **met** at byte-identical output. J1833−2103 with
  `-reorder` 7.17 → 5.73 GiB (0.682 × 8.40; limit 6.30).
- Cause, from a trace of the peak: 32 dense model images (1.07 GB) and
  eight per-beam resync buffers (0.54 GB) in the minor cycle. Fixed by
  sparse models and one shared buffer, in every joined run.
- **Default changed** (`bc62504`): `-reorder` with `-join-polarizations`;
  `-no-reorder` for the old path. The frozen rule held on all three fields.
  Bookings for A5-style runs: about 9 GB (large fields) and 7 GB
  (J1833−2103) of memory, plus 28 / 9 GB of temporary files beside `-name`.
- Kept: phase 2's inputs `D:/rang/outputs/gemclean-memory2-20261116/f?.ms`
  (68 GB) are not deleted; this phase's outputs (binaries, logs, hashes,
  the regression MS, no FITS) are in
  `D:/rang/outputs/gemclean-memory3-20261117`, a few hundred MB.
- Open: the beams (2.15 GB) and plans (0.94 GB), byte-identical only if
  read from files; `f32` images (changes bits).
