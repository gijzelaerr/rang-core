# Rang core, wave 1 task C: the WSClean w-stacking gridder

Protocol frozen 2026-10-29 on branch `core/c-gridder`, before any gridder
code was written. Status: **proposed; protocol frozen; not yet implemented or
measured**. Task C of [core-parallel-plan.md](core-parallel-plan.md): port the
w-stacking gridder of WSClean 3.6-1 (`gridding/wstackinggridder.cpp`,
`gridding/wsmsgridder.cpp`, `main/wsclean.cpp`, read from the verified Debian
source in `outputs/wsclean-3.6-1-source-20261029/`, GPL-3.0) into the Rust
core and measure its dirty images and PSFs against WSClean's own FITS on the
fifteen archived imaging jobs. A reimplementation; under AGENTS.md not a
scientific contribution. The acceptance tolerance is task A's; this file
reports differences as measured and leaves pass/fail against A's tolerance to
the coordinator.

## What is ported (read from the source, fixed before code)

Settings as rang runs WSClean (`flagging_imaging.wsclean_command`): 512 × 512
pixels of 8 arcsec, `-pol I`, channels 1024–3071 of one spectral window,
`-gridder wstacking -wstack-nwlayers 64 -j 1 -abs-mem 0.5 -niter 0 -make-psf
-no-min-grid-resolution -no-reorder`, Briggs 0.5 weighting.

- **Reader (`ContiguousMSReader`, schaapcommon `reordering.cc`).** For
  `-pol I` with four linear correlations the provider yields one
  polarization per channel: data $I=\tfrac12(XX+YY)$ (zero if not finite) and
  weight $w = 4\min(w_{XX}, w_{YY})$, zero if either correlation is flagged
  or not finite. Rows with `FLAG_ROW` are skipped by the row selection.
  The gain mode is therefore `kTrace` with one visibility per channel.
- **Imaging weight** (task B's port; here taken from WSClean itself).
  `CalculateWeightsImplementation` looks up the Briggs grid at
  $(u,v)/\lambda$ per channel; `-store-imaging-weights` writes exactly that
  per-channel value into `IMAGING_WEIGHT_SPECTRUM` (XX and YY entries
  equal). `ApplyWeights` forms `cumWeight = w × imagingWeight` in single
  precision, multiplies the Stokes I sample by it, and accumulates
  `total_weight_ += cumWeight` (double), `gridded_visibility_count_ += (cumWeight != 0)`,
  `visibility_weight_sum_ += w`. With one polarization
  `ImageWeight() = total_weight_` (FITS `WSCIMGWG`, `WSCNORMF`).
- **w limits** (`msprovidercollection.cpp`). Over all rows and channels with
  $w\neq0$ and imaging weight $\neq0$ whose grid position passes a bounds
  test, `max_w = max|w/\lambda|`, `min_w = min|w/\lambda|`. The bounds test
  in 3.6 uses $x = u\,\Delta_x W$ and $y = u\,\Delta_y H$ (u twice; upstream
  observation for the coordinator, ported as written). `-wstack-nwlayers 64`
  fixes the layer count; `-no-min-grid-resolution` keeps the inversion grid at
  the image size with the image pixel scale.
- **Gridder (`WStackingGridder<float>`).** Kernel: Kaiser–Bessel windowed
  sinc, $\alpha = 8.6$, 7 pixels, 1023× oversampling, computed in double
  as `makeKaiserBesselKernel` (series $I_0$ to $10^{-8}$) and stored as
  1023 float kernels of 7 taps in reversed index order. Samples with
  $w<0$ are conjugated and mirrored. `WToLayer` rounds
  $(|w|-w_{\min})(N-1)/(w_{\max}-w_{\min})$; `LayerToW` inverts it.
  `AddDataSample` rounds $x = u\Delta_xW$, $y = v\Delta_yH$ to the nearest
  cell, chooses the sub-cell kernels from the rounded fractional offsets
  `(round(frac × 1023) + 1534) % 1023`, keeps samples with
  $-W/2 < x \le W/2$, $-H/2 < y \le H/2$, wraps negative cells, and adds the
  7 × 7 separable kernel with modular wrapping at the grid edge. Each layer is
  inverse-FFTed (unnormalised FFTW backward transform), then
  `projectOnImageAndCorrect` multiplies by $e^{-2\pi i w(\sqrt{1-l^2-m^2}-1)}$
  with $l = (W/2 - x_{src})\Delta_x$, $m = (y_{src}-H/2)\Delta_y$ and adds
  the real part to the image at `[xSrc + ySrc*W]` with
  `xSrc = (x + W/2) mod W`, `ySrc = (H - y + H/2) mod H`.
  `FinalizeImage(1/ImageWeight)` scales the image and divides by the
  kernel's image-plane response: the type-III DCT (FFTW `REDFT01`, length
  $W\cdot1023/2$) of the right half of the oversampled 1-D kernel, sampled at
  $|x - W/2|$ and $|y-H/2|$, times $1/1023^2$.
- **PSF and normalisation (`wsclean.cpp`).** The PSF grids unit
  visibilities with the same weights. WSClean then multiplies the PSF by
  $1/\mathrm{PSF}[H/2\cdot W + W/2]$ so its centre is one, and the dirty
  image by the same factor (`psfNormalizationFactor`; `siCorrection` = 1).
- **FITS orientation.** `FitsWriter` writes the image array in natural order
  (`fits_write_pixnull` of `width × height` values), so FITS pixel
  `(x, y)` (0-based, y the slow axis) is `image[x + y*W]`; `CRPIX = W/2+1`,
  `CDELT1 = -scale`, `CDELT2 = +scale`, `RA---SIN`/`DEC--SIN` at the FIELD
  phase centre. No flip.

Not ported here: Briggs weighting (task B), the "small inversion"
resampling and trimming (disabled by rang's flags), facets, IDG, w-gridder,
prediction, multi-pass memory splitting (the 64 layers fit one pass; the
result does not depend on the split), threading (`-j 1`).

## Additions, fixed before code

- **Precision.** The core grids and transforms in double precision with its
  own radix-2 FFT and a direct type-III DCT sum (no new crates). WSClean grids
  in single precision with FFTW. The expected agreement is therefore at
  WSClean's single-precision rounding level, roughly $10^{-7}$ to $10^{-6}$ of
  the image peak, not bit equality. `cumWeight` is formed as an `f32` product
  so that the image weight sum can be compared tightly.
- **Scope of the core module.** `core/src/grid.rs` takes per-row UVW in
  metres, channel frequencies, one complex Stokes sample and one combined
  weight per (row, channel), and returns the dirty image, the PSF, the image
  weight, the gridded count, the weight sum and the w limits. Stokes I
  formation and the WSClean reader's weight rule live in
  `python/rangtoy/core_grid.py`, which also writes FITS through astropy with
  the WCS above. `core/src/ffi_grid.rs` holds the C ABI; the wrapper
  registers its own ctypes symbols as `core_zarr.py` does.
- **Oracle step.** `examples/oracle_wsclean_gridder.py` runs once inside
  `rang-flagging-next-imaging:local` (WSClean 3.6-1, binary SHA256
  `1fd0ced9…`). For each of the fifteen archived jobs it writes the archived
  checkpoint columns into a fresh copy of the archived diagnostic MS, reruns
  the archived command with `-store-imaging-weights`, and exports UVW,
  frequencies, `WEIGHT_SPECTRUM`, `FLAG`, `FLAG_ROW`, phase centre and
  `IMAGING_WEIGHT_SPECTRUM` to `.npz`, with the rerun FITS, logs and a
  receipt (`outputs/core-c-20261029-01`).
- **Comparator.** `examples/compare_core_gridder.py` reads two sets of FITS
  (and headers) and reports per job and per image kind: maximum absolute
  difference, RMS difference, maximum difference relative to the reference
  peak, and the WCS keys. It is run on archive versus rerun first.

## Comparator precondition (measured before freezing)

Oracle run `outputs/core-c-20261029-01`, 2026-10-29, 23.6 s for fifteen
WSClean runs (1.35–1.67 s each). Every rerun dirty image and PSF equals the
archived FITS pixel for pixel (maximum absolute difference 0.0 on all 30
images); the files are not byte-identical (header only). `WSCIMGWG`
= 322612.468523026 (response jobs, 9169 gridded visibilities) and
262157.784039497 (`caracal-firstpass-rejected`, 7812), w = [6.52933, 148.919]
wavelengths, 64 layers in one pass, in rerun and archive alike.

## Acceptance criteria (frozen)

Gated (pass/fail decided here):

1. **Weight sum.** The core's image weight equals the FITS `WSCIMGWG` of the
   rerun within $10^{-6}$ relative, and its gridded visibility count equals
   the log's `Gridded visibility count`, for all fifteen jobs.
2. **w limits.** The core's `min_w` and `max_w` equal the log's
   `w=[min:max]` within $10^{-4}$ relative (the log prints six digits).
3. **PSF centre.** The core PSF's pixel `(W/2, H/2)` is exactly 1.0 after
   normalisation, for all jobs.
4. **WCS.** The FITS the wrapper writes carries the same `CRPIX1/2`,
   `CRVAL1/2`, `CDELT1/2`, `CTYPE1/2` as the archive (floats to $10^{-9}$
   degrees).
5. **Orientation, synthetic.** A unit test grids one unit visibility set
   predicted for a point source at a known offset $(l, m)$ on a tiny array
   and finds the dirty-image maximum at the pixel WSClean's convention gives
   (`x = W/2 - l/\Delta`, `y = H/2 + m/\Delta`).
6. **Kernel.** The core's oversampled 1-D kernel reproduces
   `makeKaiserBesselKernel` as written (the centre value is
   $1023/I_0(8.6)\cdot I_0(8.6)/1023 = 1$ times the sinc at zero, and the table
   is symmetric), checked in a unit test against a direct NumPy transcription.

Reported, not gated (task A proposes the tolerance; the coordinator decides):

7. For every job and for dirty and PSF: maximum absolute pixel difference
   (Jy/beam), RMS difference, and the maximum difference relative to the
   archive's peak, core versus archive (identical to core versus rerun by
   the precondition).
8. Timing: core gridding per job, the oracle, builds and tests, in the log
   below.

Failures are recorded as frozen; any later step is labelled post-hoc.

## Tool-run log (seconds)

| Step | Time |
| --- | ---: |
| `uv pip install` of the venv extras | 19.4 |
| `cargo +1.93 build --release` of `core/` before the port | 1.3 |
| Oracle: fifteen WSClean runs in the container | 23.6 |

## For the coordinator

- Add `pub mod ffi_grid;` and `pub mod grid;` to `core/src/lib.rs` (added
  uncommitted here for local builds; stated in the final report).
- Upstream observation: `CalculateMsLimits` in `gridding/msprovidercollection.cpp`
  computes the y bound from `u` instead of `v`; the limits are otherwise
  unaffected for these jobs (checked when measured). Not filed.
