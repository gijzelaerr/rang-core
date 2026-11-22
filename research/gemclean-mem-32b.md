# GeMClean memory, phase 5 (issues #32, #34): the Stokes I channel path's visibilities

Branch `gemclean-mem-32b` from origin/main `b1fa64a1`. **Frozen 2026-11-22 before any code.** Phase 4
is [gemclean-mem-32.md](gemclean-mem-32.md): its case I (E2-N target, Stokes I, multiscale,
4096², 8 joined channels) peaks at 40.17 GB against WSClean 3.7's 11.02 GB (3.6 ×). This is resource
work with no scientific claim. Results go under "Measured"; later changes are dated amendments.

## 1. Where case I's memory is (phase 4's arm 0 trace, by phase; heap GB held at the end)

| Phase | Held | Most |
| --- | ---: | ---: |
| read (1,024 channels read, averaged by 2) | 9.85 | 29.46 |
| weights (eight `ChannelData`) | 12.51 | 29.27 |
| channels 0-7: PSF and beam, each | +1.4 to +1.7 | |
| after channel 7 | 25.13 | 25.67 |
| multiscale minor cycles | 37.85 | 40.67 |

The peak is in the minor cycles, not in the read. At that peak the trace has 16 or more blocks of
0.37-0.82 GB, about 14 GB in all. Their sizes match each channel's f32 visibilities (1.6 M rows × 64
averaged channels × 8 B = 0.82 GB) and f32 weights (0.41 GB). They are held from the read to the end.
The channel path (`deconvolve_channels`) prepares each measurement but, unlike the polarisation path,
never calls `compacted()`. So it keeps the dense visibilities and weights, the zero weights of flagged
cells included (30-35 % of the input cells), next to the plan.

## 2. Arms (bit-identical by construction)

- **Arm V1, compaction.** After `prepare()`, the channel path calls `GridMeasurement::compacted()`,
  as the polarisation path does since phase 1. Only the active visibilities and weights are kept,
  in the plan's sorted order. Residuals read the same values from the same sorted places, so the
  images keep their bits (phase 1, `research/gemclean-memory.md`). It applies by default, where
  `compacted()` does: single-precision data, a prepared plan.
- **Arm V2, visibilities on disk.** With `-reorder` on a Stokes I run with `-channels-out` > 1, each
  compacted measurement's visibilities go to the temporary file (`on_disk`, phase 2). Each residual
  reads them back. Today `-reorder` with one polarisation is ignored with a warning; under V2 it acts
  on this path. Opt-in.

Expected on case I: V1 −3 to −4 GB (the zero-weight cells and the dense arrays); V2 a further −5 to
−6 GB (the active visibilities), at one read of about 5 GB per major cycle (4 here).

## 3. Measures and decision rule (frozen)

- **Data and runs:** phase 4's case I (`i.ms`, E2-N target, scans 6, 8, 10; `-niter 20000`, same
  argv) on nash, shared. Main against an arm, both in **one lock hold run side by side** (8 slots,
  so both see the same load), `/usr/bin/time -v` peak RSS and wall. V2 runs with
  `-reorder -temp-dir` on the run's directory.
- **Identity (gate):**
  - every FITS file and `image-mask.json` of case I byte-identical to main, for each arm;
  - G8's sweep (phase 3's `sweep.py`, 21 cases, without and with `-reorder`) identical against
    main's binary, nothing left behind;
  - `core/tests/gemclean_memory.rs` passes.
  A failed identity rejects the arm.
- **V1 is adopted (default)** if case I's peak RSS ≤ **0.95 ×** main's and wall ≤ **1.05 ×**.
  V1 adds no work beyond one sort of the arrays, hence the tight wall bar.
- **V2 is adopted (opt-in, behind `-reorder`)** if case I's peak RSS ≤ **0.85 ×** main's and wall
  ≤ **1.10 ×**. If a wall ratio falls within 0.05 of its bar, a second pair is run and the means are
  used.
- **Stated factor:** GeMClean / WSClean 3.7 peak RSS on case I, from phase 4's WSClean run (11.02
  GB), whatever it is.

## 4. Not claimed, not done

No speed or quality claim. The multiscale minor cycle's +12.7 GB (scale images and the convolver
caches) and the beams (exteriors and spectra, 9.7 GB) are left as they are: phase 4 showed the spectra
spill costs time, and the multiscale caches are their own proposal.

## Measured

(none yet)
