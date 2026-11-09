# Rang: GeMClean's defaults on the real pilot (task G7)

Status, 2026-11-09: **protocol only; nothing measured yet.** Written and committed before the first
comparison and before the first timed run. Finish plan row G7; owner decision 3 ("coarse gridding:
after measuring"); G2's plane-group finding; G1's open `-beam-band` default; the speed note's
`-tau-min 0.2`; G9 finding 6 and G4 decision 2 (the restoring beam, BMAJ about −26 % on every
cleaned run).

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
