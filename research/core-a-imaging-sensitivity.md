# Rang core, task A: WSClean approximation sensitivity

Wave 1 task A of [core-parallel-plan.md](core-parallel-plan.md). Protocol
frozen 2026-10-29 in the commit that adds this file, before any driver code
was written. Status: **proposed** (the measured section below is filled in
after the frozen run). A measurement of the oracle's own approximation
sensitivity; under AGENTS.md it is not a scientific contribution, and no
archived result changes because of it.

## Question

The phase 4 port of the WSClean w-stacking imager (tasks B and C) needs a
tolerance for weights, dirty images and PSFs. How far do the archived
fifteen-job dirty-image diagnostics ([flagging-imaging.md](flagging-imaging.md),
archive [gain-tv-next-imaging.json](results/gain-tv-next-imaging.json)) move
when WSClean's own gridding approximations are varied around its defaults:
the Kaiser–Bessel kernel size (7 pixels), the kernel oversampling (1023×) and
the number of w-layers (64 in the frozen family, where WSClean suggested 1)?
A port that agrees with WSClean at matched settings to a small fraction of
that movement is indistinguishable from an approximation change WSClean
itself makes.

## Precondition: comparator on archive versus host reproduction (done)

Following the phase 3 lesson, the comparator was written and run before this
protocol was frozen. `examples/compare_imaging_reproduction.py` compares the
`raw_result` of the curated archive (the 2026-09-24 run `-03`) with the WSL
reproduction `outputs/tv-next-imaging-wsl-20261029-01/result.json`, using
`rangtoy.imaging_sensitivity.classify_reproduction`:

| Class | Compared | Worst relative difference |
| --- | ---: | ---: |
| exact (strings, integers, booleans, headers) | 980 | 0 |
| float (RMS, peaks, beam, closures, PSF differences) | 192 | 0 |
| difference (fit coefficients, responses, MSE proxies, rounding) | 44 | within 1e-12 absolute |
| reported (precast visibility closures, ~1e-14 Jy) | 2 | 4.4e-2 |
| excluded (FITS file hashes, wall times, backup digests, allocation counter) | 32 | – |

Zero failures (receipt
`outputs/core-a-20261029-00-precondition/archive-vs-wsl-reproduction.json`,
0.12 s). The FITS file hashes differ only because WSClean writes the output
path into the FITS `HISTORY` cards; every pixel-derived number agrees. The
sensitivity run therefore compares pixel digests (`pixel_digest`, SHA256 of
the float32 array), not file hashes.

## Design

- Inputs are the archived checkpoints only: for each of the fifteen jobs,
  `checkpoints/<job>-written.npz` holds the exact `CORRECTED_DATA` (complex64),
  `FLAG` and `FLAG_ROW` the archived run wrote before its inversion, and
  `checkpoints/<job>-command.json` the exact WSClean command. The two
  whole-MS backups `backups/response-input.ms` and `backups/caracal-input.ms`
  are the clean inputs those columns were written into. No gain is re-solved,
  no visibility is recomputed, no injection is regenerated.
- The driver `examples/run_imaging_sensitivity.py` runs inside
  `rang-flagging-next-imaging:local` (WSClean 3.6-1, python-casacore,
  astropy), with the worktree mounted read-only and `outputs/` writable. It
  copies the two backups into a fresh `outputs/core-a-<date>-NN/`, and for
  each job writes the checkpointed columns once (adding `CORRECTED_DATA` as
  the archived run did) and runs every variant's command. Only `-name`,
  `-temp-dir` and the MS path change in the archived command; the three
  gridding options are appended (`variant_command`). The run is
  single-threaded (`-j 1`, as frozen).
- Variants (`rangtoy.imaging_sensitivity.variants`), 19 in all:
  the defaults (7, 1023, 64); kernel size 3, 5, 9, 11, 15; oversampling 63,
  255, 511, 2047, 4095; w-layers 1, 4, 16, 32, 128, 256; and two
  combinations, coarse (3, 63, 1) and fine (15, 4095, 256). WSClean requires
  an odd kernel size. 285 inversions.
- For every variant the archived metrics are recomputed with the unedited
  `flagging_imaging.linear_image_fit` and `image_diagnostics`: the unit basis
  and fixedG0 reference fit of that variant, known-family fluxes and
  conditional responses of the eight paired jobs, offsource RMS, PSF
  L∞ against the variant's own fixedG0 PSF, the two dirty-image closures, the
  fitted beam and the weight headers (`WSCVWSUM`, `WSCNVIS`, `WSCIMGWG`,
  `WSCNORMF`, `WSCENVIS`). Pixel differences against the default variant are
  reported per job as L∞ and RMS, absolute and relative to the default peak.
- `-image.fits` (the niter-0 restored image, no information beyond the dirty
  image) is deleted after each inversion; dirty and PSF FITS are kept.

## Acceptance criteria (frozen)

1. **Reproduction.** The default variant's dirty and PSF pixel digests equal
   those of the archived FITS files in
   `outputs/tv-next-imaging-wsl-20261029-01/images/` for all fifteen jobs
   (30 exact digests). If any differs, the L∞ pixel difference is recorded
   and the run is reported as failed on this criterion.
2. **Weights are kernel-independent.** `WSCVWSUM`, `WSCNVIS`, `WSCIMGWG`,
   `WSCNORMF` and `WSCENVIS` are equal (exactly, as FITS floats) across all
   19 variants for every job. WSClean grids imaging weights by nearest cell
   before any kernel is involved, so a difference is a finding about the
   weighting path that task B must know, and fails this criterion.
3. **Family closures.** Every variant's omitted and complete dirty-image
   closures stay below the family's frozen 1e-6 Jy/beam. Reported per
   variant; a variant that breaks it is named, not hidden.
4. **Spread (measured, not gated).** For every variant against the default:
   the largest relative change of any template-fit flux (eight paired jobs
   and the reference fit), the largest absolute change of any conditional
   response fraction, the largest dirty L∞ (absolute and relative to peak),
   the largest PSF L∞, the largest relative change of offsource RMS and of
   the fitted beam. `rangtoy.imaging_sensitivity.spread`.
5. **Tolerance rule.** The proposed phase 4 tolerances are computed by
   `proposed_tolerances` from the six variants adjacent to the defaults
   (kernel 5 and 9, oversampling 511 and 2047, w-layers 32 and 128): one
   tenth of the smallest adjacent movement for each of dirty L∞ relative to
   peak, PSF L∞, template flux (relative) and response fraction (absolute),
   floored at float32 resolution 2⁻²³ ≈ 1.2e-7 (a FITS comparison cannot
   resolve less). Weight sums: 1e-9 relative if criterion 2 holds. The rule
   is fixed now; the numbers come from the run.
6. **No side effects.** The archive's `checkpoints/`, `images/` and
   `backups/` trees are digested before and after the run and must be
   unchanged; the tracked tree is unchanged; the run writes only into its
   fresh `outputs/` directory.
7. **Cost (reported).** Wall time per inversion and per variant inside the
   container, the whole run with `/usr/bin/time`, logged below.

A failure is recorded here with its numbers. The task is reported as done
only if criteria 1, 2 and 6 pass as frozen; criterion 3 is reported.

## Timings

| When | Tool run | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-10-29 | `compare_imaging_reproduction.py`, archive vs WSL reproduction | two result JSONs | 0.12 s | 44 MB | 0 failures; precondition |
| 2026-10-29 | venv creation (`uv venv --seed` + README pip line) | public PyPI | 51 s | – | `python3 -m venv` fails on this host: no `ensurepip` for 3.14 |

## For the coordinator

- Nothing in shared files yet; filled in after the run.
