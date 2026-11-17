# GeMClean's memory on joined polarisations, phase 3 (issue #32)

Status: **proposed, frozen before any code of its arms** (2026-11-17).
Sections 1-5 are the freeze; measurements will go in section 6.

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
