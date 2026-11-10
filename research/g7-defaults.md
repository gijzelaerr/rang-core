# Rang: GeMClean's defaults on the real pilot (task G7)

Status, 2026-11-10: **measured; defaults set.** Coarse gridding (`-wgridder-accuracy 1e-4`, single
precision) is GeMClean's default from G7: on the 512-channel pilot it saves 32.7 % of the wall
at `-j 16` and 26.7 % at `-j 1` and 4.1 GB of peak memory, inside every class B bound. `-beam-band`
(2.7 %, 0.9 %), `-tau-min 0.2` (3.0 %, 3.4 %) and plane group 1 (7 % and 15 % slower, 0.8 GB less)
are not adopted. The restoring beam is now fitted as WSClean 3.7's binary fits it (within 4.3e-7 of
WSClean's BMAJ and BMIN on all 19 cases; it was 9-30 % narrower); the cause is a different
estimator, plus an unsigned-offset bug in schaapcommon that GeMClean copies. Against WSClean at
matched accuracy, native GeMClean is 1.55× (default form) and 1.52× (coarse) faster at `-j 16`,
1.13× faster and 1.31× slower at `-j 1`; built in WSL on WSClean's OS layer, coarse GeMClean is level at
`-j 16` (0.96× of WSClean's wall) and 1.24× slower at `-j 1`. Memory 2.0-2.4× WSClean's. No
novelty claim. The protocol below was committed before the first comparison (`409c7e4`).

Finish plan row G7; owner decision 3 ("coarse gridding: after measuring"); G2's plane-group
finding; G1's open `-beam-band` default; the speed note's `-tau-min 0.2`; G9 finding 6 and G4
decision 2 (the restoring beam, BMAJ about −26 % on every cleaned run).

## 1. The pilot and the binaries

- **Pilot:** ESO 137-006, `D:\rang\outputs\20261103-gemclean-heldout\real\cal.ms`, 512 channels,
  823,500 rows, 9.7 GB, set A (G2's pilot-512). Opened read-only by every run: GeMClean with
  `-no-update-model-required` (G6 writes `MODEL_DATA` by default), WSClean with the MS mounted
  `:ro` and `-no-update-model-required`.
- **Settings (G2's):** `-size 4096 4096 -scale 3asec -weight briggs 0.5 -niter 1000000 -gain 0.1
  -nmiter 1000 -abs-threshold 0.003 -data-column DATA -field 0`. GeMClean uses its own major-cycle
  rule (no `-mgain`); WSClean `-mgain 0.8 -pol I -gridder wgridder`.
- **GeMClean, native:** profile `gemclean`, `cargo +1.93`, `x86-64-v3` (`.cargo/config.toml`),
  built on this host. Reference `gemclean-5b0ffbe.exe` (main, before G7); candidates from recorded
  commits of `fp-g7-defaults`. Binaries and provenance under `D:\rang\outputs\g7-20261109-01\bin`.
- **GeMClean, Linux:** the same commit built in WSL (`cargo +1.93 --profile gemclean`, target dir in
  `~/Build/tmp/20261109-g7-target`, removed afterwards), for the same-OS comparison only.
- **WSClean 3.7** `4f395b2`, `rang-wsclean-native:3.7` (`-DPORTABLE=OFF`, built for this CPU, as in
  the speed run), in Docker in WSL. `nominres` = `-no-min-grid-resolution -wgridder-accuracy 1e-6`
  (GeMClean's default accuracy); `minres` = WSClean's own default grid and accuracy (1e-4).

## 2. The restoring beam

**Cause, read in source (WSClean 3.7, `math/imageoperations.cpp` `DetermineBeamSize`/`FitBeamSize`,
schaapcommon `fitters/gaussianfitter.cc` `Fit2DGaussianCentred`):** WSClean fits a unit-peak,
centred elliptical Gaussian `exp(−x²/2sx² + βxy/(sx sy) − y²/2sy²)` by GSL's `lmsder`
(Levenberg-Marquardt) to the PSF values in linear space over a square box, negatives included
(`fitBeamWithNegatives` defaults to true). The box side is `ceil(10 × estimate)` pixels, made even
(`beamFittingBoxSize` 10); the estimate is the theoretic beam (`1/max|uvw|/λ`, at least one pixel,
raised to the Gaussian taper if wider); if `0.8 × 10 × fitted major ≥ box`, the box is regrown to
`ceil(10 × major)` and the fit repeated from the larger estimate, at most 5 times. The stop is
`gsl_multifit_test_delta(1e-7, 1e-7)`, at most 500 iterations. For the MFS image the estimate is
the smallest channel theoretic beam. GeMClean instead fits `−ln(b/b0)` by linear least squares on
the connected pixels with `b ≥ b0/2` only. On MeerKAT's PSF the half-power core is narrower than
the Gaussian that best fits the core plus its pedestal over a 10-beam box. The cause is a different
estimator, isolated in `fit_restoring_beam`; it touches only the restored image and its `BMAJ`,
`BMIN`, `BPA` cards and report fields.

**Fix (proposed):** port WSClean's estimator (box, regrowth, negatives, estimate, MFS estimate) at
every call site; the theoretic beam is computed for every run, not only under `-multiscale`.

**Beam gate (B).** Against WSClean 3.7's fitted beam at the same size, scale, weighting and taper
(`BMAJ`, `BMIN`, `BPA` of its image FITS header, `nominres` runs): `|BMAJ_G/BMAJ_W − 1| ≤ 1e-3`,
`|BMIN_G/BMIN_W − 1| ≤ 1e-3`, `|BPA_G − BPA_W| ≤ 0.1°` (modulo 180°). Development: S1 and the
pilot-512 (G2's `runs/wsclean/img/p512-nominres-image.fits`). **Held out, frozen here, not read
before the fix is committed:** S2, S3 (`20261102-gemclean/bench/wsclean/*-abs-nominres-fast-j16`),
H1-H4 (`20261103-gemclean-heldout/sim/wsclean/*-abs-nominres-fast-j16`), the pilot-256 (G2
`p256-nominres`), G4's tapered A3 (`g4-20261109-01/runs/wsclean/A3`, `-taper-gaussian`) and G3's
joined D1-C1 (`20261106-g3-spectral/runs/wsclean/D1-C1`, per-channel and MFS beams). A diagnostic,
not a gate: the ported fit applied to WSClean's own `psf.fits` must give WSClean's header beam to
1e-4, which separates the estimator from PSF differences.

**Identity (gate A, labelled change).** Reference: `gemclean-5b0ffbe.exe` built natively here (G4:
native builds differ from the Linux G2/G3 hashes in every file, so native against native). Set:
G2's 15 runs (S1-S3, H1-H4 at default and coarse, the pilot-256 at default) and G3's D1-C1 and
D1-C3 at default, as G4's `id_run.py`. With the beam fix, `dirty`, `psf`, `model` and `residual`
(and per-channel and MFS files) must stay byte-identical; `image` changes on every cleaned run,
by the beam alone: the new `image` must equal `residual + model ⊛ G_new` recomputed from the
written files to 1e-6 of the image peak. Any other changed file rejects the fix.

## 3. Candidate defaults

Each is one change from the current default **GD** (f64, `-wgridder-accuracy 1e-6`, plane group 4,
`-tau-min 0.5`, no `-beam-band`), at the binary with the beam fix:

| arm | change | question |
| --- | --- | --- |
| GC | `-single -wgridder-accuracy 1e-4` | coarse gridding as the default (owner decision 3) |
| GB | `-beam-band` | G1's flag as a default |
| GT | `-tau-min 0.2` | the speed note's provisional setting |
| GP | `RANG_WGRIDDER_PLANE_GROUP=1` | memory against time; not bit-neutral (G2), so class B |
| GX | the adopted changes together | confirmation of the chosen set (only if two or more are adopted) |
| WN, WM | WSClean `nominres`, `minres` | the oracle at matched accuracy: GD against WN, GC against WM |

Deferred, not decided here: G5's multiscale `-mgain` rule, the stop rule and its floor, Briggs
robustness, `-nmiter`, the predict accuracy for `MODEL_DATA` (it follows `-wgridder-accuracy`).

## 4. Accuracy measure (no truth on real data)

**Exact scoring.** Every arm's final `model.fits` is put through one exact operator: rang's
`core_wgridder` at f64 and ε = 1e-7 with WSClean's flips, the Stokes I visibilities and the
Briggs 0.5 gridding weights of `examples/gemclean_bench_compare.py` (`weights`), read in row
blocks so the pilot fits memory (`g7_score.py`; linear in the rows, so blocks add exactly up to
summation order). Per model: `Q = ½ Σ w|V − Am|² / Σ w`, the exact residual's inner-field (central
2N/3) rms, MAD and peak, total and negative model flux. A block-check: the exact dirty image of the
first arm against that arm's `dirty.fits` to 1e-5 of the peak, or the scorer is wrong and no score
is used.

**Common-beam restored image.** `exact residual + model ⊛ G_D`, with GD's fitted beam for every arm,
so the beam does not enter the comparison. σ = 1.4826 × MAD of GD's exact inner residual.

**Class B bounds (one candidate against GD, on the pilot):**

- restored image (common beam, inner field): rms of the difference ≤ 0.1 σ, largest ≤ 3 mJy (the
  threshold);
- `|ΔQ/Q| ≤ 1e-3`;
- exact inner residual peak: change ≤ 0.3 mJy (a tenth of the threshold);
- total model flux: `|ΔS/S| ≤ 1e-3`.

For GP, in addition, on S1 and H3 at G2's identity settings (images only, not timed): `model` and
`residual` byte-identical to group 4, or restored rms of the difference ≤ 0.1 σ and largest
≤ 100 µJy (G1's bounds, σ the sky's Briggs noise in `gemclean-speed.md`).

Against the oracle (reported, not a gate): the same exact Q, peak and flux for WN and WM, and the
common-beam restored-image difference GD − WN and GC − WM.

## 5. Timing method

- **Host.** 16 threads, Windows 11 and WSL 2 on the same machine. Every timed run holds
  `tools/heavy_lock.py`. Before and after each run the probe records Windows processes above half a
  core (`Win32_PerfFormattedData_PerfProc_Process`) and WSL processes above half a core (`top`),
  plus `/proc/loadavg`. A run is **spoiled** if any process other than the probe's own (`WmiPrvSE`,
  `top`, `powershell` of the probe) and the VM host (`vmmem`, `VmmemWSL`) is above half a core
  before it. Before a run the driver waits up to 10 minutes for a clean probe (checked every 60 s),
  then runs anyway and marks it spoiled. Spoiled runs stay in the record; each cell is decided on
  its clean runs if it has at least as many as planned, otherwise on all, and both are reported.
- **Measures.** Wall time from process start to exit, measured by the driver. Native GeMClean: user
  and kernel CPU time and peak working set (`GetProcessTimes`, `GetProcessMemoryInfo` on the
  process handle). WSClean and Linux GeMClean: GNU `time -v` (wall, user, sys, maximum RSS), inside
  the container for WSClean. Phase times from each imager's log (GeMClean's read, PSF, beam, major
  cycles, minor; WSClean's inversion, prediction, deconvolution). CPU/wall is reported for every
  run, as the check that `-j 1` used one core.
- **Threads.** `-j 16` and `-j 1`. WSClean at `-j 1` also gets `-parallel-reordering 1` and
  `OMP_NUM_THREADS=1` (at `-j 16`, `OMP_NUM_THREADS=16` and its default reordering).
- **Different OS layers.** Native GeMClean reads `D:` through NTFS; WSClean runs in Linux in a
  Hyper-V VM and reads `/mnt/d` through 9p, which is slower, and its temporary reordered files go
  to the VM's own disk (`~/Build/tmp/20261109-g7-wsctmp`, mounted at `/run/tmp`, emptied after
  each run), not to `/mnt/d` as in G2. So native GeMClean against WSClean mixes the imagers with
  the OS layer. The **same-OS figure** is GeMClean built in WSL running GX (or the chosen default)
  on the same `/mnt/d` input, against WSClean.
- **Repeats and order.** `-j 16`: 3 repeats of GD, GC, GB, GT, GP, WN, WM; `-j 1`: 2 repeats of GD
  and GC, 1 of GB, GT, GP, WN, WM. Arms interleaved within a repeat (order GD, GC, WN, WM, GB, GT,
  GP; reversed on even repeats). Then GX (if any) at 3 / 2 repeats and the Linux GeMClean at 3 / 1.
  **Budget contingency (written now):** if GD's first `-j 1` run takes more than 60 min, every
  `-j 1` cell drops to 1 repeat. The order of thread counts: all `-j 16` first, then `-j 1`.
- **Saving** of a candidate: per repeat, `(wall_GD − wall_X)/wall_GD` against GD of the same repeat
  and thread count (the second GD repeat at `-j 1` pairs with nothing when X has one repeat: then
  against the median of GD's). The median over repeats is the figure.

## 6. Decision rules

For each of GC, GB, GT:

1. If any class B bound of section 4 fails: **not adopted**.
2. Else, if the median wall saving is at least **10 %** at both `-j 16` and `-j 1` and the peak
   working set does not rise by more than 1 % (and 50 MB): **adopted** as the default.
3. Else, if it saves at least 10 % at one thread count only: **not adopted**, recorded as an owner
   decision with the figures.
4. Else: not adopted.

Why 10 %: G1's bar, set from three-repeat spreads of up to 7.7 % on this host and one changed
cycle count moving a run by more.

For GP (memory against time, since the pilot fits 24 GB at group 4, G2: 19.7 GB):

1. If a class B bound fails (pilot, S1 or H3): **not adopted**.
2. Else, if the median wall cost is at most **3 %** at both thread counts: **adopted** (the memory it
   saves is then nearly free).
3. Else: not adopted; the saving in GB and the cost in % are recorded for the owner.

GX, if run, must hold the class B bounds against GD; if it does not, the adopted change with the
largest `-j 1` saving is kept alone and the others are recorded for the owner.

The plane group comment in `core/src/wgridder.rs` ("Results do not depend on it") is corrected
whatever the outcome.

## 7. Where things go

Outputs `D:\rang\outputs\g7-20261109-01` (`bin/`, `runs/<arm>-j<j>-r<rep>/`, `load/`, `runs.tsv`,
`identity/`, `beam/`, `scores/`), each run directory with the command, log, timing and load
probes, and `.code/` with a snapshot of the scripts. Scripts in
[`results/g7-defaults-scripts/`](results/g7-defaults-scripts/). Status:
`C:\Users\gijsm\Github\rang\outputs\status\fp-g7.md`.

## 8. Freeze record (2026-11-10, before any held-out beam comparison)

- **Development diagnostic, after the protocol (post hoc to section 2's description):** the
  estimator as described in section 2, solved to its minimum with scipy, does not give WSClean's
  beam on S1 (13.58″ × 9.47″ against 13.88″ × 8.34″) and its cost is lower than that of WSClean's
  beam, so WSClean does not minimise that objective. Reading `FittingCentered` again: `xi` and
  `yi` are `size_t`, `x_mid` and `y_mid` `int`, so `xi − x_mid` is unsigned and every negative
  offset becomes about 1.8e19 pixels; the model is 0 there and the residual a constant. Only the
  quadrant `x ≥ 0, y ≥ 0` of the box shapes the fit. (Its analytic Jacobian also has the sign of
  the β terms in `dsx`, `dsy` wrong; GSL's step acceptance makes that harmless here.) The
  quadrant fit in numpy (`beam_diag.py`, scratch variant) gives WSClean's header beam on both
  development cases: S1 13.8785″ × 8.3446″, PA −29.806° (WSClean 150.194°, the same axis), the
  pilot-512 16.8602″ × 9.6205″, PA 128.639° (WSClean's log 16.86″ × 9.62″, 128.64°), on GeMClean's
  PSF there (G2 `c34r`).
- **Frozen fix:** `fit_restoring_beam` ports the binary's behaviour, the quadrant included
  (commit `c7ca268`, binary `gemclean-beam-c7ca268.exe`, sha256 `309b9cd7…2ca4ba`). On S1 its
  header beam is within 3e-7 of WSClean's. No change follows the held-out cases; if one fails, it is
  reported as failed.
- The held-out cases of section 2 are unchanged.

## 9. Measured: the restoring beam (gates A and B)

Binary `gemclean-beam-c7ca268.exe` against the native reference `gemclean-5b0ffbe.exe`, both
built here. Archives: [`g7-defaults-beam.json`](results/g7-defaults-beam.json) (gate B) and
[`g7-defaults-identity.json`](results/g7-defaults-identity.json) (gate A).

**Gate B, met on every case.** GeMClean's header beam against WSClean 3.7's, `nominres` runs at the
same size, scale, weighting and taper; ΔPA modulo 180° (WSClean writes 150.19° where GeMClean
writes −29.81°, the same axis):

| case | GeMClean | WSClean | BMAJ G/W − 1 | BMIN G/W − 1 | ΔPA | before (`5b0ffbe`), BMAJ, BMIN G/W − 1 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| S1 (dev.) | 13.8785″ × 8.3446″, −29.806° | 13.8785″ × 8.3446″, 150.194° | −2.9e-7 | −2.7e-7 | 0.0000° | −0.280, −0.042 |
| pilot-512 (dev.) | 16.860″ × 9.620″, −51.36° (log) | 16.86″ × 9.62″, 128.64° (log) | < 3e-4 (printed) | < 5e-4 (printed) | 0.00° | −0.087, −0.023 (G2's binary) |
| S2, S3 | as S1 (same uv coverage) | as S1 | −2.9e-7 | −2.7e-7 | 0.0000° | as S1 |
| H1 | 17.6409″ × 8.6187″ | 17.6409″ × 8.6187″ | 3.5e-8 | 2.0e-8 | 0.0000° | −0.225, −0.079 |
| H2 | 17.5290″ × 9.0900″ | 17.5290″ × 9.0900″ | −1.8e-7 | 1.8e-9 | 0.0000° | −0.256, −0.111 |
| H3 | 14.3323″ × 8.4975″ | 14.3323″ × 8.4975″ | −2.5e-7 | 2.1e-8 | 0.0000° | −0.297, −0.056 |
| H4 | 14.0460″ × 8.3045″ | 14.0460″ × 8.3045″ | −8.5e-8 | 7.9e-8 | 0.0000° | −0.268, −0.042 |
| pilot-256 | 16.8609″ × 9.6211″ | 16.8609″ × 9.6211″ | 6.0e-8 | −2.8e-8 | 0.0000° | −0.087, −0.023 |
| A3 (G4, `-taper-gaussian 8asec -minuv-l 300`) | 21.2390″ × 15.7959″ | 21.2390″ × 15.7959″ | −1.1e-7 | −5.4e-8 | 0.0000° | – |
| D1-C1, 8 channels (G3) | 16.30″ × 10.31″ to 13.18″ × 7.98″ | the same | ≤ 4.1e-7 | ≤ 4.3e-7 | 0.0000° | – |
| D1-C1 MFS | 14.4694″ × 9.0101″ | 14.4694″ × 9.0101″ | −2.1e-7 | −1.3e-7 | 0.0000° | −0.262, −0.056 |

The pilot-512 line is the GD timing run's log against WSClean's log at G2 and here (both print
two decimals); the numpy diagnostic on GeMClean's PSF gave 16.8602″ × 9.6205″ there. The old fit
was 9-30 % narrower in BMAJ because it fitted only the half-power core; WSClean's fit takes the
core and its pedestal over a box of about 10 beams, on one quadrant of it.

**Gate A, met (with the post-hoc wording below).** 18 runs (S1-S3, H1-H4, pilot-256 at default and
coarse; D1-C1, D1-C3), 150 FITS files. Every file's sha256 changes, because every GeMClean file
carries `BMAJ`, `BMIN`, `BPA`, which section 2 had not foreseen. Amended check (post hoc,
[`identity_check.py`](results/g7-defaults-scripts/identity_check.py)): the reference rerun with the
files kept reproduces the first reference's hashes on all 18 runs; every `dirty`, `psf`, `model`
and `residual` file (channels and MFS included) has a byte-identical data unit and a header equal
but for the three beam cards; every `image` equals `residual + model ⊛ G_new` from its own header
to at most 6.9e-8 of its peak (bound 1e-6). So the change is the beam alone: in identity hashes,
**every FITS file of every cleaned run changes (header), and every restored image changes (data)**;
models, residuals, dirty images and PSFs keep their data.

Also changed: the log says `pixels fitted` (the quadrant's pixel count, 841 on the pilot) and the
report's `main_lobe_pixels` is now `fit_pixels`.

## 10. Measured: timings on the pilot

Runs 2026-11-10 00:42-05:32 by [`g7_run.py`](results/g7-defaults-scripts/g7_run.py) (plans
`j16`, `j1`, `lx`), each under the heavy lock, binary `gemclean-beam-c7ca268.exe` (native) and its
WSL build (`c7ca268`, sha256 `67115171…f5eabe`). **No run was spoiled**: every probe before a run
found no process above half a core but the probe's own. Archive:
[`g7-defaults.json`](results/g7-defaults.json) (every run, phases, probes, hashes);
[`analyse.py`](results/g7-defaults-scripts/analyse.py) makes the tables. The `-j 1` repeats
followed the protocol's plan (2 for GD and GC, 1 otherwise): GD's first `-j 1` run took 17 min,
under the 60-min contingency.

Wall in seconds, median (range); peak memory is the peak working set (native) or the maximum RSS
(`time -v`, WSL); CPU/wall is (user + system)/wall:

| arm | `-j` | runs | wall | CPU/wall | peak GB | major cycles | phases, s (median) |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| GD (default before G7) | 16 | 3 | 197.0 (191.0-201.4) | 11.8 | 19.73 | 4 | read 11.1, PSF 50.4, resync 15.2, major 89.3 |
| GC (coarse) | 16 | 3 | **132.4** (132.3-132.6) | 11.3 | **15.62** | 5 | read 10.8, PSF 24.1, resync 14.6, major 62.2 |
| GB (`-beam-band`) | 16 | 3 | 191.7 (188.9-193.8) | 11.8 | 19.58 | 4 | PSF 50.1, resync 12.7, major 88.9 |
| GT (`-tau-min 0.2`) | 16 | 3 | 185.3 (181.9-191.8) | 11.8 | 19.73 | 4 | PSF 51.4, resync 5.1, major 90.9 |
| GP (plane group 1) | 16 | 3 | 211.3 (208.7-216.8) | 12.0 | 18.90 | 4 | PSF 50.0, resync 15.1, major 106.6 |
| WN (WSClean `nominres`) | 16 | 3 | 306.0 (304.9-306.9) | 8.4 | 8.35 | 5 | inversion 142.7, prediction 82.7, deconvolution 21.2 |
| WM (WSClean `minres`) | 16 | 3 | 201.8 (201.1-202.6) | 5.0 | 7.77 | 5 | inversion 84.4, prediction 37.5, deconvolution 20.6 |
| LX (coarse, WSL build) | 16 | 3 | 193.9 (193.5-195.5) | 7.9 | 15.65 | 4 | read 78.5, PSF 25.4, resync 16.5, major 50.5 |
| GD | 1 | 2 | 1026.4 (1024.4-1028.4) | 1.00 | 19.67 | 4 | read 12.2, PSF 207.5, resync 55.2, major 634.6 |
| GC | 1 | 2 | **751.9** (750.4-753.5) | 1.00 | 15.19 | 5 | read 12.3, PSF 144.6, resync 53.6, major 453.9 |
| GB | 1 | 1 | 1015.7 | 1.00 | 19.51 | 4 | PSF 206.9, resync 44.8, major 634.8 |
| GT | 1 | 1 | 989.6 | 1.00 | 19.67 | 4 | PSF 208.1, resync 18.4, major 633.8 |
| GP | 1 | 1 | 1180.6 | 1.00 | 18.84 | 4 | PSF 212.0, resync 53.2, major 771.7 |
| WN | 1 | 1 | 1158.8 | 0.96 | 8.33 | 5 | inversion 574.8, prediction 500.6, deconvolution 24.7 |
| WM | 1 | 1 | 575.1 | 0.91 | 7.76 | 5 | inversion 281.3, prediction 209.8, deconvolution 25.2 |
| LX | 1 | 1 | 714.0 | 0.92 | 15.22 | 4 | read 80.0, PSF 140.5, resync 53.0, major 351.8 |

Saving against GD, per repeat paired, median (pairs):

| candidate | `-j 16` | `-j 1` | peak memory, GB (`-j 16`, `-j 1`) |
| --- | --- | --- | --- |
| GC | **32.7 %** (32.7, 30.7, 34.2) | **26.7 %** (26.8, 26.7) | −4.12, −4.48 |
| GB | 2.7 % (2.7, −1.5, 6.2) | 0.9 % | −0.15, −0.15 |
| GT | 3.0 % (2.6, 3.0, 9.7) | 3.4 % | 0.00, 0.00 |
| GP | −7.2 % (−7.2, −13.5, −3.7) | −15.2 % | −0.83, −0.83 |

At matched accuracy (WSClean wall over GeMClean wall): GD against WN 1.55 (`-j 16`) and 1.13
(`-j 1`); GC against WM 1.52 and 0.76. **On the same OS layer** (LX against WM, both reading the MS
from `/mnt/d` through 9p): 1.04 and 0.81. LX's read takes 78-80 s through 9p against 11-12 s
natively; its other phases are close to the native ones. WSClean loaded the data into memory in
every run (`Loading data in memory...`), so its temporary directory held no reordered files (G2's
19-min WSClean run had its `-temp-dir` on `/mnt/d`).

**Reproducibility, seen in passing.** Every GeMClean arm's model is byte-identical over its repeats
and between `-j 1` and `-j 16` (GD and GC five runs each, GB, GT, GP, LX four each). WSClean
`minres` gave four different models in four runs; `nominres` one model at `-j 16` (three runs) and
another at `-j 1`. The WSL build of GeMClean gives a different model from the native one (4 cycles
against 5; G4's native-against-Linux finding).

## 11. Measured: accuracy on the pilot (exact scoring)

[`g7_score.py`](results/g7-defaults-scripts/g7_score.py) on the `-j 16` repeat-1 models, 12.6 min.
Block check: the scorer's exact dirty image equals GD's `dirty.fits` to 6.9e-8 of the peak
(bound 1e-5). Two scorer fixes, made before any score was read: the pilot has XX and YY only, so
the scorer pads them to four correlations (XY and YX flagged, of zero weight; Stokes I then equals
`(XX + YY)/2` exactly); and its first pass gave `dirty2vis` the weights, which ducc multiplies in
(every Q came out as Q0), so it now passes the active cells as a mask. Only the corrected pass is
reported. [`compare.py`](results/g7-defaults-scripts/compare.py) applies the bounds. σ = 0.959 mJy
(1.4826 × MAD of GD's exact inner residual); the common beam is GD's 16.86″ × 9.62″.

| arm | Q/Q0 | inner rms, mJy | inner peak, mJy | model flux, Jy | negative, Jy | model pixels |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GD | 2.649969e-2 | 1.0925 | 3.000 | 83.7630 | −7.4011 | 43,389 |
| GC | 2.649695e-2 | 1.0925 | 3.001 | 83.7751 | −7.3952 | 43,567 |
| GB | 2.649686e-2 | 1.0924 | 3.000 | 83.7611 | −7.4079 | 43,475 |
| GT | 2.649925e-2 | 1.0924 | 3.000 | 83.7765 | −7.4000 | 43,480 |
| GP | 2.649969e-2 | 1.0925 | 3.000 | 83.7630 | −7.4011 | 43,389 |
| WN | 2.658221e-2 | 1.0969 | 3.469 | 83.7079 | −7.2522 | 42,558 |
| WM | 2.658576e-2 | 1.0971 | 3.590 | 83.6876 | −7.2528 | 42,474 |

| pair | restored rms / σ | largest, mJy | ΔQ/Q | Δ inner peak, mJy | ΔS/S | class B |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| GC − GD | 0.019 | 1.62 | −1.0e-4 | +0.001 | 1.4e-4 | **pass** |
| GB − GD | 0.015 | 0.35 | −1.1e-4 | 0.000 | −2.2e-5 | pass |
| GT − GD | 0.020 | 1.79 | −1.7e-5 | 0.000 | 1.6e-4 | pass |
| GP − GD | 0 | 0 | 0 | 0 | 0 | pass (model identical) |
| bound | 0.1 | 3 | 1e-3 | 0.3 | 1e-3 | |
| GD − WN (oracle) | 0.024 | 2.07 | −3.1e-3 | −0.469 | 6.6e-4 | reported |
| GC − WM (oracle) | 0.024 | 2.26 | −3.3e-3 | −0.589 | 1.0e-3 | reported |

GP's own residual differs from GD's in 2 of 16.8 M pixels by at most 4.5e-13 Jy (the G2 effect,
at rounding level here); on S1 and H3 (G2's identity settings, images only) all five files of
group 1 have data identical to group 4's. WSClean stops above the threshold (inner peaks of 3.47
and 3.59 mJy against 3 mJy) with a 0.3 % higher misfit, as in the held-out note.

## 12. Decisions under section 6

| candidate | class B | `-j 16` | `-j 1` | memory | decision |
| --- | --- | --- | --- | --- | --- |
| GC, coarse gridding | pass | 32.7 % | 26.7 % | −4.1 GB | **adopted** (rule 2) |
| GB, `-beam-band` | pass | 2.7 % | 0.9 % | −0.15 GB | not adopted (rule 4) |
| GT, `-tau-min 0.2` | pass | 3.0 % | 3.4 % | 0 | not adopted (rule 4) |
| GP, plane group 1 | pass (pilot, S1, H3) | 7.2 % slower | 15.2 % slower | −0.83 GB | not adopted (GP rule 3) |

GX was not run: only one change was adopted. The defaults now in the code (`7d5619a`):

- `gemclean`: `-wgridder-accuracy` defaults to 1e-4, and the gridder runs in single precision for
  an accuracy of 1e-5 or coarser; `-double` forces double precision, `-single` single, and
  `-wgridder-accuracy 1e-6` alone gives the form before G7 (f64, 1e-6). Test
  `gridder_precision_defaults`.
- `rang-core`: `image.wgridder_accuracy` defaults to 1e-4 (was 1e-6); the model column written after
  imaging (`image.write_model`, the selfcal rounds) follows gemclean's precision rule
  (`_gridder_single`, `tests/test_g7_defaults.py`). `docs/cli.md` regenerated. The image and
  selfcal stage hashes change once (runs made before need `--force`).
- Plane group 4, `-tau-min 0.5`, `-beam-band` off: unchanged. The plane-group comments in
  `core/src/wgridder.rs` now say that the group is not bit-neutral in every layout.

## 13. Owner decisions (open)

1. **Coarse gridding as the default** (owner decision 3): adopted under the rule written first. It
   also sets the accuracy of the `MODEL_DATA` predicted for self-calibration (1e-4, WSClean's
   default). To revert: `-wgridder-accuracy 1e-6` (or `image.wgridder_accuracy: 1.0e-06`).
2. **The restoring beam copies a WSClean bug.** WSClean's fit sees one quadrant of its box
   (`size_t` offsets in schaapcommon's `FittingCentered`; its β Jacobian terms also have the wrong
   sign, which is harmless here). GeMClean follows the binary, the oracle, as G9 decision 1 did. The
   intended estimator (the whole box) would give 13.58″ × 9.47″ on S1 and 16.97″ × 9.41″ on the
   pilot (WSClean 13.88″ × 8.34″, 16.86″ × 9.62″). Open: an upstream report to schaapcommon, and
   whether GeMClean gets an option for the whole-box fit.
3. `-beam-band`, `-tau-min 0.2` and plane group 1 stay options; on the pilot none clears 10 %.
4. Every GeMClean FITS header changes with the beam (gate A as amended): hashes of images made
   before G7 do not carry over.

## 14. What was not checked

- Only the pilot-512, set A, at G2's settings: no multiscale, masks, several channels or
  polarisations in the timed runs (their beams are in gate B).
- One host; WSClean in Docker in WSL, GeMClean native, with the same-OS figure from one WSL build.
- `-j 1` with one or two repeats per cell; spreads at `-j 16` were at most 5.4 % (GD).
- The coarse form's effect on self-calibration (E1, E2) is not measured here.
- G5's multiscale `-mgain` rule and the stop rule (deferred in section 3).

## For the coordinator

- `research/README.md` index line: `[g7-defaults.md](g7-defaults.md) — G7: GeMClean's defaults on
  the 512-channel pilot; coarse gridding adopted (−33 % wall at -j16, −27 % at -j1, −4.1 GB); the
  restoring beam fitted as WSClean 3.7's binary fits it (BMAJ was 9-30 % narrower).`
- `research/STATE.md`: "G7, GeMClean's defaults, 2026-11-10 (measured;
  [g7-defaults.md](g7-defaults.md)). Restoring beam: WSClean 3.7 fits a unit-peak Gaussian in linear
  space over a 10-beam box and, through an unsigned-offset bug in schaapcommon, on one quadrant of
  it; GeMClean now does the same: BMAJ and BMIN within 4.3e-7 of WSClean's on 19 cases (S1-S3,
  H1-H4, both pilots, a tapered run, 8 channels and MFS), where they were 9-30 % narrow; only the
  restored images and the beam cards change. On the pilot-512 at -j16 / -j1, idle host: coarse
  gridding (1e-4, single) saves 32.7 % / 26.7 % and 4.1 GB within the class B bounds and is now the
  default; -beam-band (2.7 / 0.9 %), -tau-min 0.2 (3.0 / 3.4 %) and plane group 1 (7 / 15 %
  slower, −0.8 GB) are not adopted. Against WSClean at matched accuracy: 1.52-1.55× faster at
  -j16, 0.76-1.13× at -j1; on the same OS layer 1.04× and 0.81×; memory 2.0-2.4×. No novelty
  claim."
- `research/finish-plan.md`: G7 done; owner decision 3 answered (coarse gridding adopted, can be
  reverted); G9 decision 6 and G4 decision 2 answered (beam fixed in G7); G8 measures speed on the
  wheel with the new defaults.
- Branch `fp-g7-defaults`; outputs `D:\rang\outputs\g7-20261109-01` (`bin/`, `runs/`, `identity/`,
  `beam/`, `scores/`, `.code/`).
