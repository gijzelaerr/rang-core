# Rang core, task A: WSClean approximation sensitivity

Wave 1 task A of [core-parallel-plan.md](core-parallel-plan.md). Protocol
frozen 2026-10-29 in `07d8a16`, before any driver code was written. Status:
**implemented; measured: criteria 1, 2, 3 and 6 pass as frozen; spreads
measured and tolerances proposed**. A measurement of the oracle's own
approximation sensitivity; under AGENTS.md it is not a scientific
contribution, and no archived result changes because of it.

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
  each job writes the checkpointed columns (adding `CORRECTED_DATA` as the
  archived run did) and runs the variant's command. Only `-name`,
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

## Measured result of the frozen run (2026-10-29)

Run `outputs/core-a-20261029-01` with the committed driver (`e6d6825`), all
19 variants and 15 jobs, 285 inversions, 552 s wall inside the container
(single WSClean thread; 12 s for one w-layer to 72 s for 256). A two-job,
two-variant smoke run (`outputs/core-a-20261029-00-smoke`) preceded it and
is not part of the measurement.

- **Criterion 1 passes**: all 30 default-variant pixel digests equal the
  archive's FITS pixels. The archived family is reproduced bit for bit from
  the checkpointed columns alone.
- **Criterion 2 passes**: the five weight headers are identical across all
  19 variants for every job (`WSCVWSUM` 975612.123630524, `WSCNVIS` 9169,
  `WSCIMGWG` = `WSCNORMF` 322612.468523026 on the response MS). Imaging
  weights do not depend on the kernel, the oversampling or the w-layers.
- **Criterion 3 passes**: every variant's closures stay below 1e-6 Jy/beam
  (largest 1.8e-7 with one w-layer; the default has 3.5e-8 and 3.8e-8).
- **Criterion 6 passes**: the archive's three trees have the same digests
  before and after; `git status` is unchanged.

Spread against the default variant (criterion 4; `examples/summarize_imaging_sensitivity.py`).
Flux and RMS changes are relative, response changes absolute, pixel changes
in Jy/beam and relative to the default job's peak; the closures column is
omitted, complete:

| Variant | kernel | oversampling | w-layers | flux rel. | response abs. | dirty L∞ / peak | dirty L∞ Jy/beam | PSF L∞ | RMS rel. | beam rel. | closures Jy/beam | weights equal | s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| default | 7 | 1023 | 64 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3.54e-08, 3.81e-08 | – | 20 |
| kernel-3 | 3 | 1023 | 64 | 1.06e+00 | 6.31e-02 | 3.27e-01 | 2.97e+00 | 2.02e-01 | 1.88e-01 | 6.76e-02 | 3.73e-08, 3.75e-08 | yes | 20 |
| kernel-5 | 5 | 1023 | 64 | 3.66e-01 | 2.35e-02 | 1.19e-01 | 1.15e+00 | 7.56e-02 | 6.12e-02 | 1.38e-02 | 3.73e-08, 4.24e-08 | yes | 20 |
| kernel-9 | 9 | 1023 | 64 | 1.87e-01 | 1.53e-02 | 8.46e-02 | 8.46e-01 | 5.66e-02 | 3.54e-02 | 1.76e-03 | 3.54e-08, 4.91e-08 | yes | 19 |
| kernel-11 | 11 | 1023 | 64 | 2.79e-01 | 2.45e-02 | 1.49e-01 | 1.49e+00 | 9.97e-02 | 5.91e-02 | 1.92e-03 | 3.35e-08, 4.37e-08 | yes | 19 |
| kernel-15 | 15 | 1023 | 64 | 3.49e-01 | 3.27e-02 | 2.35e-01 | 2.34e+00 | 1.56e-01 | 8.20e-02 | 1.94e-03 | 3.73e-08, 3.97e-08 | yes | 23 |
| oversampling-63 | 7 | 63 | 64 | 4.10e-03 | 1.45e-04 | 2.13e-03 | 9.75e-03 | 6.28e-04 | 3.73e-04 | 2.81e-05 | 3.35e-08, 4.51e-08 | yes | 27 |
| oversampling-255 | 7 | 255 | 64 | 2.08e-04 | 3.58e-05 | 4.43e-04 | 2.16e-03 | 1.38e-04 | 9.16e-05 | 3.70e-06 | 3.54e-08, 4.48e-08 | yes | 28 |
| oversampling-511 | 7 | 511 | 64 | 1.35e-04 | 8.81e-06 | 3.31e-04 | 8.13e-04 | 4.85e-05 | 6.50e-05 | 4.41e-06 | 3.35e-08, 3.75e-08 | yes | 29 |
| oversampling-2047 | 7 | 2047 | 64 | 4.70e-05 | 3.87e-06 | 9.38e-05 | 4.19e-04 | 2.78e-05 | 1.31e-05 | 4.16e-06 | 3.73e-08, 4.46e-08 | yes | 29 |
| oversampling-4095 | 7 | 4095 | 64 | 9.28e-05 | 4.75e-06 | 1.10e-04 | 4.88e-04 | 3.14e-05 | 1.99e-05 | 4.15e-06 | 3.91e-08, 3.76e-08 | yes | 29 |
| wlayers-1 | 7 | 1023 | 1 | 1.01e-02 | 3.57e-04 | 3.93e-02 | 3.16e-01 | 2.11e-02 | 1.64e-03 | 2.46e-03 | 1.76e-07, 1.24e-07 | yes | 12 |
| wlayers-4 | 7 | 1023 | 4 | 5.82e-03 | 2.39e-04 | 4.14e-03 | 3.76e-02 | 2.53e-03 | 5.46e-04 | 5.20e-05 | 8.10e-08, 7.31e-08 | yes | 13 |
| wlayers-16 | 7 | 1023 | 16 | 5.23e-04 | 1.91e-05 | 4.81e-04 | 6.15e-03 | 3.90e-04 | 8.99e-05 | 9.03e-06 | 4.66e-08, 4.07e-08 | yes | 13 |
| wlayers-32 | 7 | 1023 | 32 | 2.19e-04 | 3.39e-06 | 2.42e-04 | 2.16e-03 | 1.46e-04 | 3.94e-05 | 2.37e-06 | 3.17e-08, 3.61e-08 | yes | 19 |
| wlayers-128 | 7 | 1023 | 128 | 1.45e-04 | 1.60e-06 | 8.78e-05 | 3.99e-04 | 2.76e-05 | 1.33e-05 | 2.67e-07 | 5.59e-08, 4.94e-08 | yes | 41 |
| wlayers-256 | 7 | 1023 | 256 | 1.07e-04 | 1.38e-06 | 1.13e-04 | 4.37e-04 | 2.93e-05 | 6.57e-06 | 2.71e-07 | 7.64e-08, 6.93e-08 | yes | 71 |
| coarse-3-63-1 | 3 | 63 | 1 | 1.05e+00 | 6.33e-02 | 3.37e-01 | 3.03e+00 | 2.06e-01 | 1.89e-01 | 7.13e-02 | 9.48e-08, 9.82e-08 | yes | 15 |
| fine-15-4095-256 | 15 | 4095 | 256 | 3.49e-01 | 3.27e-02 | 2.35e-01 | 2.34e+00 | 1.56e-01 | 8.20e-02 | 1.94e-03 | 6.71e-08, 7.33e-08 | yes | 72 |

Reference-fit coefficients (mJy) and the total conditional responses:

| Variant | compact ref | extended ref | omitted-total compact | omitted-total extended | complete-total compact | complete-total extended |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| default | 60.00000 | 119.99999 | 0.491670 | 0.775669 | 0.996916 | 0.986497 |
| kernel-3 | 60.00000 | 119.99999 | 0.439847 | 0.712618 | 0.993603 | 0.987111 |
| kernel-5 | 60.00000 | 120.00000 | 0.479520 | 0.752173 | 0.995773 | 0.986362 |
| kernel-9 | 59.99999 | 120.00000 | 0.498158 | 0.790977 | 0.997498 | 0.986677 |
| kernel-11 | 60.00000 | 119.99999 | 0.501892 | 0.800173 | 0.997787 | 0.986797 |
| kernel-15 | 60.00000 | 120.00000 | 0.505080 | 0.808338 | 0.998006 | 0.986901 |
| oversampling-63 | 60.00001 | 119.99998 | 0.491655 | 0.775524 | 0.996903 | 0.986504 |
| oversampling-255 | 60.00001 | 119.99998 | 0.491660 | 0.775633 | 0.996915 | 0.986496 |
| oversampling-511 | 59.99999 | 120.00001 | 0.491665 | 0.775660 | 0.996916 | 0.986496 |
| oversampling-2047 | 60.00000 | 119.99999 | 0.491674 | 0.775671 | 0.996916 | 0.986498 |
| oversampling-4095 | 60.00000 | 120.00000 | 0.491674 | 0.775674 | 0.996916 | 0.986498 |
| wlayers-1 | 60.00003 | 120.00001 | 0.492021 | 0.775519 | 0.996946 | 0.986487 |
| wlayers-4 | 60.00000 | 120.00009 | 0.491909 | 0.775474 | 0.996898 | 0.986507 |
| wlayers-16 | 60.00000 | 119.99998 | 0.491663 | 0.775688 | 0.996914 | 0.986499 |
| wlayers-32 | 60.00000 | 120.00000 | 0.491673 | 0.775670 | 0.996915 | 0.986497 |
| wlayers-128 | 60.00001 | 119.99999 | 0.491671 | 0.775667 | 0.996915 | 0.986497 |
| wlayers-256 | 60.00000 | 120.00000 | 0.491671 | 0.775668 | 0.996915 | 0.986497 |
| coarse-3-63-1 | 60.00002 | 119.99992 | 0.439057 | 0.712359 | 0.993650 | 0.987113 |
| fine-15-4095-256 | 60.00000 | 120.00000 | 0.505081 | 0.808337 | 0.998006 | 0.986901 |

### Reading the spread

- **Oversampling and w-layers are benign.** Around the defaults they move the
  dirty pixels by at most 3e-4 of the peak, the template fluxes by at most
  2e-4 relative and the response fractions by at most 1e-5 absolute; the
  reference fit recovers the 60/120 mJy injection to 1e-4 mJy in every
  variant. WSClean's suggested single w-layer costs 4% of peak in pixels but
  only 4e-4 in response fraction. Beyond 64 layers and 1023× oversampling
  the movements settle at about 1e-4 of the peak, which is the level of the
  family's own float32 FITS and complex64 column rounding, not a trend.
- **Kernel size is not benign for this family.** Changing it moves the
  dirty pixels by 8–33% of the peak and the omitted-sky total response by
  up to 0.063 absolute (0.44–0.51 compact against the archived 0.4917). The
  movement is concentrated at the image edges: for kernel 15 against the
  default, the omitted-total dirty image differs by RMS 5.7e-5 Jy/beam in the
  central 256×256 pixels and 2.2e-3 Jy/beam in the outer border (L∞ at the
  image edge). This is the Kaiser–Bessel gridding correction, whose
  anti-aliasing suppression near the edge of the field changes with the
  kernel width. Because the known-family fit is an unweighted least squares
  over all 262,144 pixels, the edge pixels move the *adaptation*
  coefficients (omitted-adaptation by −7.5 to +3.9 mJy) while the *direct*
  coefficients move by less than 0.1 mJy and the fixedG0 reference by
  less than 1e-4 mJy. The largest "relative flux change" (1.06) is the
  complete-adaptation compact coefficient, archived at −0.187 mJy, moving by
  −0.20 mJy; it is small in absolute terms. Kernel sizes 9, 11 and 15 drift
  monotonically away from 7 (0.498, 0.502, 0.505), and 15 equals the
  fine combination, so the archived response fractions carry a
  kernel-size dependence of a few percent absolute that the archive's own
  "conditional known-family diagnostic" caveat already covers. No archived
  number changes; this is recorded as a limitation for anyone reading the
  response fractions as more than a matched-family comparison.
- **Cost.** One w-layer halves the inversion time (12 s for 15 jobs); 256
  layers with the 0.5 GiB memory hint take 71 s. Oversampling above 255
  adds about 40% to the kernel set-up at this image size; kernel size barely
  matters at 9,169 visibilities.

### Proposed phase 4 tolerances (criterion 5)

From the six adjacent variants (one tenth of the smallest movement, floor
2⁻²³; `proposed_tolerances` in `result.json`):

| Quantity | Smallest adjacent movement | Proposed tolerance | For |
| --- | ---: | ---: | --- |
| dirty-image pixel L∞ relative to the job's peak | 8.78e-5 (w-layers 128) | **8.8e-6** | task C |
| PSF pixel L∞ (PSF peak 1) | 2.76e-5 (w-layers 128) | **2.8e-6** | task C |
| template-fit flux, relative | 4.70e-5 (oversampling 2047) | **4.7e-6** | wave 2 task I |
| conditional response fraction, absolute | 1.60e-6 (w-layers 128) | **1.6e-7** | wave 2 task I |
| imaging-weight sums `WSCVWSUM`, `WSCIMGWG`, relative | exact across all 19 variants | **1e-9** | task B |
| per-visibility imaging weights (`-store-imaging-weights`, float32) | not measured here | **1e-6 relative** (float32 storage), proposed, not measured | task B |

These are tolerances for a port that reproduces WSClean's algorithm at
matched settings (Kaiser–Bessel 7, 1023×, 64 layers, `-no-min-grid-resolution`).
They are 10–100× above float32 rounding of a 512² image and 10× below the
finest approximation change WSClean itself makes, so a port inside them
is indistinguishable from WSClean by this family while a kernel-shape or
gridding-correction error (which moves pixels by ≥1e-2 of the peak here)
is caught at once. Task C should compare pixels relative to each job's own
peak, since the fifteen peaks range from 0.063 to 0.99 Jy/beam, and should
report the central and edge regions separately, because this run shows
kernel-related differences live at the edges. The `pixel_digest` function
gives exact reproduction where the port is bit-compatible, as the default
variant was here; an exact match is not required by the proposal.

## Timings

| When | Tool run | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-10-29 | `compare_imaging_reproduction.py`, archive vs WSL reproduction | two result JSONs | 0.12 s | 44 MB | 0 failures; precondition |
| 2026-10-29 | venv creation (`uv venv --seed` + README pip line) | public PyPI | 51 s | – | `python3 -m venv` fails on this host: no `ensurepip` for 3.14 |
| 2026-10-29 | `run_imaging_sensitivity.py` smoke, 2 jobs × 2 variants, in `rang-flagging-next-imaging:local` | archive checkpoints | 5.7 s with container | – | pixel digests equal the archive |
| 2026-10-29 | `run_imaging_sensitivity.py` frozen run `-01`, 19 variants × 15 jobs | archive checkpoints, two 58 MB MS copies | 552 s with container (20 s per variant at defaults; 12 s for 1 w-layer, 71 s for 256) | – (client 33 MB) | 285 inversions, 730 MB of FITS and receipts |
| 2026-10-29 | `cargo +1.93 build --offline --release` root and core, `CARGO_BUILD_JOBS=4` | fresh worktree | 4.4 s | – | |
| 2026-10-29 | `pytest tests/test_imaging_sensitivity.py` | 11 tests | 0.06 s | – | |
| 2026-10-29 | `bash tools/check-all.sh`, `CARGO_BUILD_JOBS=4` | whole tree | 53 min 13 s (pytest 679 passed in 3180 s) | – | overall PASS; run once, with seven sibling sessions sharing the 16 cores |

## For the coordinator

- Shared files to update when merging: a row in `tool-timings.md` for the
  552 s sweep (above), a line in `STATE.md` and the research index
  (`README.md`) pointing here, and the phase 4 tolerance table above into
  the section 9 plan of the feasibility study as the tolerance for tasks B
  and C. No Rust module was added, so no `pub mod` line is needed.
- The kernel-size dependence of the archived response fractions (a few
  percent absolute) belongs in the limitations of
  [flagging-imaging.md](flagging-imaging.md) if the user agrees; this task
  did not edit that frozen report.
- `outputs/core-a-20261029-01` (730 MB) is the evidence; `-00-smoke` (10 MB)
  and `-00-precondition` can be deleted after merging.

## Open questions

- Should task C aim at bit-exact reproduction of the default variant (shown
  possible here for WSClean against itself) rather than the proposed
  tolerance? The tolerance is the safe floor; exactness is a stretch goal.
- The per-visibility weight tolerance for task B is proposed from float32
  storage, not measured here; task B measures it against
  `-store-imaging-weights`.
