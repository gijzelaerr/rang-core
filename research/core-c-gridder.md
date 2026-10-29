# Rang core, wave 1 task C: the WSClean w-stacking gridder

Protocol frozen 2026-10-29 in `d410daa` on branch `core/c-gridder`, before
any gridder code was written. Status: **implemented; measured: the frozen run
`-02` passed gated criteria 1–4 but its reported pixel differences were up to
67 % of the image peak, because the frozen reading of WSClean missed the
default image padding; after the labelled post-hoc fix the core matches
WSClean's dirty images and PSFs to at most 6.1e-7 of the peak on all fifteen
jobs (run `-05`)**. Task C of [core-parallel-plan.md](core-parallel-plan.md):
port the w-stacking gridder of WSClean 3.6-1 (`gridding/wstackinggridder.cpp`,
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

**Missed in the frozen reading, found by the frozen run (post-hoc, see
below): image padding.** `Settings::imagePadding` defaults to 1.2. The
gridder's `ImageWidth()` is `paddedImageWidth = ceil(1.2 × 512) = 615`,
rounded up to a multiple of four, 616 (`main/settings.cpp`); the w-limit
bounds test, the FFT grid, the $(l, m)$ table and the kernel correction all use
616 × 616 at the unchanged pixel scale, and `Image::Trim` cuts the centred
512 × 512 (offset `(616 − 512)/2 = 52`) before the PSF normalisation and the
FITS writer. "The inversion grid at the image size" above was wrong: the
`-no-min-grid-resolution` flag only disables the *small* inversion.

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

## Measured results (2026-10-29)

Implementation: `core/src/grid.rs` (gridder, FFT, DCT, trim), `core/src/ffi_grid.rs`
(`rang_core_grid_invert`, `rang_core_grid_kernel`), `python/rangtoy/core_grid.py`
(`stokes_i_reader`, `invert`, `wcs_header`, `write_fits`), driver
`examples/run_core_gridder.py`, comparator `examples/compare_core_gridder.py`,
tests `tests/test_core_grid.py` and the Rust unit tests in `grid.rs`.
Criteria 5 and 6 are those unit tests; both pass (the point-source peak lands
at `(W/2 - 5, H/2 - 3)` and the kernel equals the NumPy transcription to
1e-15, is symmetric and has centre value 1).

**Frozen run `-02`** (`outputs/core-c-20261029-02`, grid at the image size,
no padding). Gated criteria 1–4 pass on all fifteen jobs: image weight equal
to `WSCIMGWG` to 1.4e-15 relative, `WSCVWSUM` to 3.6e-16, counts 9169 and
7812 equal, w limits equal to the log to 1.3e-7 and 8.1e-7 relative, PSF
centre exactly 1.0, WCS keys equal. Criterion 7 as frozen: dirty images
differ from the archive by up to 9.82 Jy/beam (66.7 % of the 14.73 Jy/beam
peak of `caracal-firstpass-rejected`; 60–91 % of the peak on every job), PSFs
by up to 0.655. The difference is below 2e-5 within 32 pixels of the centre
and grows smoothly with radius, so near-centre quantities (the archived
template fits, closures and PSF fits) would hardly have noticed, but the
images were not WSClean's. Gridding took 3.2–5.1 s per job (62 s in all).

**Diagnosis (post-hoc).** A NumPy transcription of the frozen reading
(gridding, FFT, projection, kernel correction) reproduces the Rust image to
1.5e-14, so the port was faithful to the reading and the reading was wrong.
WSClean reruns with one w-layer and with nearest-neighbour gridding
(`outputs/core-c-20261029-01/diag`) showed the w-term accounts for only 0.03
of the PSF and the kernel correction for 0.2, neither for 0.6. The remaining
candidate was the default `-padding 1.2` described above.

**Post-hoc run `-03`** (`outputs/core-c-20261029-03`; implementation change:
padded 616 × 616 inversion grid and centred trim, nothing else). Criteria
1–4 pass as before (the padded bounds test leaves the w limits unchanged on
these jobs). Criterion 7: every dirty image agrees with the archive to at
most 6.68e-6 Jy/beam, which is 6.1e-7 of the job's peak, RMS at most
8.9e-7 Jy/beam; every PSF to at most 4.17e-7, RMS at most 7.6e-8. This is
the single-precision level the protocol expected. Gridding took 29–59 s per
job (11 min in all) because the 616-point transforms went through an
unplanned Bluestein FFT.

**Post-hoc runs `-04` and `-05`** (FFT implementation only: `-04` a
mixed-radix transform, `-05` precomputed radix-2 and Bluestein plans with
cached twiddles and chirp spectrum). Both reproduce `-03` to within the
float32 FITS rounding (`-04` versus `-03`: 1.2e-10 Jy/beam dirty, 3.7e-9
PSF; `-05` versus `-04`: 1.2e-10 Jy/beam dirty, 0.0 PSF) and leave the archive comparison
unchanged. `-04` took 24–32 s per job (7.0 min); `-05` 27–37 s per job (7.8 min); the plans did not beat the mixed-radix transform, so the time is in the double-precision arithmetic itself.

Per job, core run `-05` against the archive (maximum absolute difference
in Jy/beam, RMS difference, archive peak, and the maximum relative to that
peak):

| Job | Dirty max abs | Dirty RMS | Dirty peak | Dirty max/peak | PSF max abs | PSF RMS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `caracal-firstpass-rejected` | 5.72e-06 | 7.22e-07 | 14.73 | 3.89e-07 | 4.17e-07 | 7.60e-08 |
| `caracal-mild` | 6.68e-06 | 8.74e-07 | 14.96 | 4.46e-07 | 3.58e-07 | 5.78e-08 |
| `caracal-no-change` | 5.72e-06 | 8.31e-07 | 14.96 | 3.83e-07 | 3.58e-07 | 5.78e-08 |
| `clean-full` | 5.72e-06 | 8.31e-07 | 14.96 | 3.83e-07 | 3.58e-07 | 5.78e-08 |
| `complete-adaptation` | 8.15e-10 | 1.14e-10 | 0.001402 | 5.81e-07 | 3.58e-07 | 5.78e-08 |
| `complete-direct` | 4.47e-08 | 4.86e-09 | 0.08574 | 5.21e-07 | 3.58e-07 | 5.78e-08 |
| `complete-full` | 6.68e-06 | 8.08e-07 | 14.93 | 4.47e-07 | 3.58e-07 | 5.78e-08 |
| `complete-total` | 5.22e-08 | 5.75e-09 | 0.08541 | 6.11e-07 | 3.58e-07 | 5.78e-08 |
| `fixedG0-reference` | 4.47e-08 | 5.81e-09 | 0.08573 | 5.21e-07 | 3.58e-07 | 5.78e-08 |
| `omitted-adaptation` | 2.24e-08 | 2.78e-09 | 0.0419 | 5.33e-07 | 3.58e-07 | 5.78e-08 |
| `omitted-direct` | 4.47e-08 | 4.83e-09 | 0.08585 | 5.21e-07 | 3.58e-07 | 5.78e-08 |
| `omitted-full` | 5.72e-06 | 8.85e-07 | 14.96 | 3.83e-07 | 3.58e-07 | 5.78e-08 |
| `omitted-total` | 3.73e-08 | 4.56e-09 | 0.06297 | 5.92e-07 | 3.58e-07 | 5.78e-08 |
| `unit-compact` | 4.17e-07 | 4.70e-08 | 0.9908 | 4.21e-07 | 3.58e-07 | 5.78e-08 |
| `unit-extended` | 2.38e-07 | 2.75e-08 | 0.4722 | 5.05e-07 | 3.58e-07 | 5.78e-08 |

Measured but not gated: WSClean's `WSCNVIS` equals the core's count on every
job; the PSF normalisation factor is 0.99997499 on the response jobs. The
PSF-centre criterion holds on all fifteen jobs, but `x × (1/x)` is not
guaranteed to be exactly one in floating point (the unit test on a 40-pixel
grid gives 1 − 1.1e-16); a future protocol should ask for one within an ulp.

## Tool-run log (seconds)

| Step | Time |
| --- | ---: |
| `uv pip install` of the venv extras | 19.4 |
| `cargo +1.93 build --release` of `core/` before the port | 1.3 |
| Oracle: fifteen WSClean runs in the container | 23.6 |
| WSClean diagnostic variants (three runs, one job) | about 6 |
| Core run `-02`, fifteen jobs (gridding only) | 62.0 |
| Core run `-03`, fifteen jobs (wall) | 659.6 |
| Core run `-04`, fifteen jobs (wall) | 420.6 |
| Core run `-05`, fifteen jobs (wall) | 467.8 |
| `compare_core_gridder.py`, 30 images | 2.4 |
| `cargo test` of the gridder (5 tests) | under 0.1 after a 3 s build |
| `pytest tests/test_core_grid.py` (4 tests) | 3.4–9.3 |
| `bash tools/check-all.sh` | 1978 (pytest 1943, 672 tests, PASS) |

The core is 20× slower than WSClean on these jobs (1.4 s with FFTW in
single precision, one thread). The time is in 128 two-dimensional
616-point double-precision transforms per job; an FFT crate or a faster
hand-written transform is a performance task, not a correctness one.

## For the coordinator

- Add `pub mod ffi_grid;` and `pub mod grid;` to `core/src/lib.rs` (added
  uncommitted here for local builds; stated in the final report).
- Upstream observation: `CalculateMsLimits` in `gridding/msprovidercollection.cpp`
  computes the y bound from `u` instead of `v`; the limits are unaffected for
  these jobs (measured). Not filed.
- Lesson for later protocols: a reading of a program's defaults should be
  checked against the program's own log or a one-parameter perturbation
  (here `-padding 1.0` would have shown it) before freezing; the comparator
  precondition only protects against comparator errors.
- `research/tool-timings.md` rows: the table above.
