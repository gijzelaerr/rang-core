# Rang: the gemclean benchmark, datasets and WSClean 3.7 baselines

Benchmark of gemclean (the reference CLEAN, measured at
`d94850e`) against WSClean 3.7 on simulated full-array MeerKAT data and the
LUNO 1934−638 four-station slice. Branch `gemclean-bench`, 2026-11-02. Status:
**implemented (simulator, run matrix, metrics); accuracy measured; speed not
measured to a usable standard.** Archive:
[results/gemclean-benchmark.json](results/gemclean-benchmark.json). Outputs:
`outputs/gmclean-bench-20261102/` in the worktree; the datasets are also in
`/home/gijsm/Build/tmp/20261102-gmclean-bench/`.

> **Every wall time, CPU time and speed comparison in this note is PROVISIONAL
> (contended).** All runs shared the 16-core host with other sessions
> (rustc builds, `b1_pointing_selfcal` fits, gemclean tuning, a check-all; load
> average 6 to 25, Windows jobs included). No gemclean against WSClean speed
> ratio here is final and none should be quoted. Section 7 lists the subset to
> rerun on a quiet host. Accuracy results do not depend on load; §5 says where
> they depend on the thread count, and every job name ends in its `-j`.

## 1. Summary

- **Implemented.** `examples/gemclean_bench_simulate.py` (exact DFT prediction
  through `core.predict_components`, MS written with rang's own table writer),
  `gemclean_bench_datasets.sh`, `gemclean_bench_run.sh` (the matrix for WSClean or
  any command template), `gemclean_bench_gemclean.sh` (the same for gemclean),
  `gemclean_bench_compare.py` (`prepare`, `score`, `truth`, `tables`: all imagers
  scored by the same exact quadratic), `gemclean_bench_archive.py` and
  `gemclean_bench_timing.sh` (the quiet-window rerun).
- **Measured, the datasets.** Three simulated MS of 1,814,400 rows × 8 channels
  × 4 correlations (971 MB each), read by python-casacore and WSClean 3.7. The
  core's exact dirty image and PSF match WSClean `-no-min-grid-resolution
  -wgridder-accuracy 1e-6` to 2.3e-7 of the peak; WSCNVIS equals rang's count;
  natural-weight image noise 19.84 µJy (target 20), Briggs 0.5 noise 23.19 µJy.
- **Measured, full array at matched settings (`abs`, 100 µJy, gain 0.1, mgain
  0.8).** Neither imager diverges. WSClean's Q/Q_truth is 1.0099 to 1.0158 and
  gemclean's 1.0096 to 1.0131: gemclean's misfit is lower by 0.03 to 0.27 %. Flux
  recovery per decade is the same within its scatter. gemclean reaches the
  threshold exactly (inner residual peak 100 µJy) where WSClean's fast loop
  stops at 178 to 245 µJy and its plain loop at 102 to 117 µJy. The two `-mgain`
  are not the same setting: WSClean's is a fraction of the peak, gemclean's of the
  misfit.
- **Negative result for gemclean.** On S1 and S2 it puts 263 to 368 mJy of
  absolute flux in 12,000 to 16,000 pixels more than two beams from any source,
  balanced in sign, against 3 to 7 mJy in 150 to 300 pixels for WSClean. The lower
  misfit is therefore not evidence of a better sky. With `-mgain 0.1` on S1 the
  false flux goes (169 pixels, 4.3 mJy) and gemclean lands on WSClean's plain-loop
  result (Q/Q_truth 1.01355 against 1.0136, 85,165 components), at 59 major cycles
  instead of 6; §4.3.
- **Measured, the slice.** WSClean diverges in every `abs` variant, including
  `-padding 2`, and cleans nothing at `-auto-threshold 3 -auto-mask 5` (its noise
  estimate, 3.54 Jy, makes the mask threshold 17.7 Jy, above the 14.95 Jy peak).
  gemclean converges (Q/Q0 4.72e-4 against 2.5e-2). Its total flux is +1.2 % but
  only 13.155 Jy (−12.0 %) lies in the central 65 pixels at `abs`, against −0.90 %
  at its `auto`; §4.4.
- **Thread count.** gemclean's FITS are bit-identical between `-j 1` and `-j 16`
  on all 8 jobs. WSClean's differ on all 6 default-grid simulated jobs (§5).

## 2. Datasets (measured)

Simulated, all three: `data/meerkat.itrf.txt` (64 dishes, longest baseline
7,698 m), phase centre dec −30°, RA 3.40860 rad, chosen so that the track runs
from hour angle −1 h to +1 h from TIME 2026-03-01 00:00 UTC; 900 integrations of
8 s; 8 channels of 25 MHz, 1312.5 to 1487.5 MHz; XX, XY, YX, YY; UVW =
uvw(ANTENNA1) − uvw(ANTENNA2) as katdal and mvftoms; no flags, no primary beam,
flat spectra. Sky seeds 20261102 (S1, S2) and 20261103 (S3).

- **S1**: 50 points, log-uniform 10 mJy to 1 Jy, uniform in the inner two-thirds
  of the 2048 × 1.5″ field, continuous positions, at least 10 pixels apart
  (measured minimum 11.0).
- **S2**: S1 plus a circular Gaussian, FWHM 40″, 2 Jy, at the inner-field grid
  point farthest from every S1 source (FITS pixel 1408.2, 421.3; nearest point
  325 pixels).
- **S3**: 500 points, log-uniform 0.1 to 100 mJy (the brief's "three decades";
  this range is my choice), same region, no separation limit (minimum 1.08
  pixels), so it is blended.
- **Noise**: seed 20261104, the same realisation for all three (the Stokes I
  noise file has one SHA-256, `20d7a0ed…`, regenerated three times in the first
  build). Sigma 0.10776 Jy per real and imaginary part per correlation; `WEIGHT` =
  `WEIGHT_SPECTRUM` = 1/σ² = 86.117, `SIGMA` = σ.
- **Prediction**: direct Fourier sums through the core for every sky, the
  disc as an analytic Gaussian component, so no pixelisation and no gridder in the
  data. This departs from the brief's degridder for the disc and S3: the DFT was
  fast enough (S3 about 166 s). Checked against an independent NumPy sum on 2,000
  rows: 8.7e-14, 8.2e-14 and 4.7e-14 relative.

| dataset | rows × chans | size | SHA-256 of the DATA file (`table.f0_TSM0`, prefix) | Q0 Jy² | Q_truth/Q0 |
| --- | --- | ---: | --- | ---: | ---: |
| S1 | 1,814,400 × 8 | 971 MB | `e40c8801b5cf85c1` | 2.6416 | 2.1969e-3 |
| S2 | 1,814,400 × 8 | 971 MB | `ac22eb20abbbb0b2` | 2.7591 | 2.1033e-3 |
| S3 | 1,814,400 × 8 | 971 MB | `e19323f6c5c5eeaa` | 0.2186 | 2.6547e-2 |
| slice | 192 × 2,048 | 61 MB | archive | 111.80 | – |

Every main-table file's SHA-256 is in the archive. The matrix ran on private
copies; their SHA-256 before and after are equal (`ms/*-sha256-*.txt`), so neither
imager wrote to the data. The slice is the `c.ms` of
[clean-certified-imaging.md](clean-certified-imaging.md) (§3), CORRECTED_DATA,
field 1: **117,556 visibilities and weight sum 669,036.3248, as that note says**.

Checks against WSClean `-niter 0 -make-psf` (`examples/gemclean_bench_datasets.sh`):

| dataset | default grid: dirty L∞/peak, inner half | `nominres`: dirty L∞/peak | `nominres` PSF L∞ | WSClean peak (Jy) at pixel (y, x) | brightest source (y, x, Jy) |
| --- | --- | ---: | ---: | --- | --- |
| S1 | 9.2e-4, 1.6e-5 | 2.3e-7 | 8.6e-8 | 0.9579 at (513, 810) | (512.5, 809.6, 0.9894) |
| S2 | 9.2e-4, 1.6e-5 | 2.3e-7 | 8.6e-8 | 0.9577 at (513, 810) | the same point |
| S3 | 2.5e-3, 2.4e-5 | 2.4e-7 | 8.6e-8 | 0.1018 at (1668, 1676) | (761.0, 994.7, 0.0997) |
| slice | 0.171, 0.027 | 2.8e-7 | 3.2e-7 | 14.950 at (256, 256) | (256, 256, 14.953) |

The S1 peak is 3 % under the source flux because the source sits half a pixel off
in both axes. The S3 peak is not at the brightest source: it is at the second
brightest (98.3 mJy at (1667.6, 1676.0), nearly on a pixel, with a 67 mJy neighbour
16 pixels away), and the brightest lies off a pixel. WSCIMGWG on the simulated data is
2,659,151,187.67 against rang's 2,659,151,193.42 (2.2e-9 relative; the slice agrees
to 1e-10). The simulated PSF is 13.88″ × 8.34″ (WSClean's fit), so "one beam" in
the metrics is 10.76″, the geometric mean.

**Error found and corrected.** The first build scaled the noise by σ/√2 per part
and gave a natural-weight noise of 14.03 µJy. It was caught by imaging the noise
alone and all datasets were rebuilt; nothing here uses the first build.

## 3. Settings and commands

Common to all jobs: 2048 × 2048 at 1.5″ (slice 512 × 512 at 8″), Briggs 0.5, gain
0.1, mgain 0.8, `-niter 1000000`, no major-cycle limit, Stokes I.

```
wsclean -gridder wgridder -data-column DATA -field 0 -size 2048 2048 -scale 1.5asec \
  -weight briggs 0.5 -pol I -j J -no-update-model-required -temp-dir /run/tmp \
  -niter 1000000 -nmiter 0 -gain 0.1 -mgain 0.8 THRESHOLD [GRID] [LOOP] -name NAME MS
gemclean -name NAME -size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 \
  -gain 0.1 -mgain 0.8 -nmiter 1000 THRESHOLD -data-column DATA -field 0 -j J MS
```

- `THRESHOLD`: `abs` is `-abs-threshold 100 µJy` for the simulations (4.3 σ of the
  Briggs noise) and 0.05 Jy for the slice, as the earlier note; `auto` is
  `-auto-threshold 3 -auto-mask 5` in WSClean and `-auto-threshold 3` in gemclean,
  which has no auto-mask. **Only `abs` is a matched setting.**
- `GRID` (WSClean): `minres` nothing (its default); `nominres`
  `-no-min-grid-resolution -wgridder-accuracy 1e-6`; `pad2` that plus `-padding 2`.
  On the simulations the default grids at 1372² instead of the padded 2458²
  ("Minimal inversion size: 1367"). `-padding 2` is gridding padding: the PSF
  FITS stays at the image size, and it also changes the Briggs weight grid. It is
  not a PSF twice the image size.
- `LOOP` (WSClean): `fast` the default sub-minor loop; `hogbom` `-no-fast-subminor`.
- gemclean has one exact gridder (default ε 1e-6, f64) and one loop, its defaults
  (patch ±64, `-drift 0.1`, `-tau-min 0.5`, `-resync-every 2000`), recorded under
  the job names `*-nominres-fast-*`.
- WSClean runs in `rang-o-casa:6.7.6.14`; gemclean runs natively, built with
  `cargo +1.93 build --release --manifest-path core/Cargo.toml --bin gemclean`.

Metrics (`gemclean_bench_compare.py score`): residual rms and peak in the central
2N/3 box, from the imager's FITS and from the exact residual; Q = ½ Σ w |V − A m|² /
Σ w through the core's exact gridder at ε 1e-9, with the Stokes I × Briggs 0.5
weights on the default weight grid for every model, so `pad2` is scored with
weights it did not use; Q_truth is the same sum over the known noise. Per-source
recovery gives each model pixel to its nearest true source, within one beam; false
components are model pixels beyond two beams from every source and outside 2 FWHM
of the disc. Checks: the pixelised catalogue scores recovery 1.000, no false flux
and disc 39.997″, and the scorer reproduces gemclean's own Q/Q0 (4.7185e-4 on
the slice).

## 4. Results (accuracy measured; wall and CPU PROVISIONAL)

All at `-j 16`. "≥" is the last logged iteration of WSClean's plain loop, which
reports no total. Full tables: `gemclean_bench_compare.py tables` on
`outputs/gmclean-bench-20261102/scores/*.json`, including every `-j 1` job.

### 4.1 Full array

| run | wall s | CPU s | RSS GB | majors | comps | inner rms µJy | inner peak µJy | Q/Q0 | Q/Q_truth | flux err mJy | recovery | false px | false \|flux\| mJy | model px |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| S1 WSClean abs minres fast | 53 | 244 | 0.54 | 9 | 85,158 | 25.61 | 178 | 2.2269e-3 | 1.0137 | +0.4 | 0.9992 | 196 | 5.7 | 2,783 |
| S1 WSClean abs nominres fast | 105 | 501 | 0.76 | 9 | 82,920 | 25.67 | 231 | 2.2278e-3 | 1.0141 | +0.4 | 0.9993 | 171 | 3.5 | 2,781 |
| S1 WSClean abs nominres hogbom | 514 | 1148 | 0.76 | 6 | ≥ 85,000 | 25.55 | 112 | 2.2268e-3 | 1.0136 | +0.6 | 0.9994 | 243 | 5.4 | 2,826 |
| S1 WSClean abs pad2 fast | 85 | 478 | 0.77 | 9 | 83,141 | 25.59 | 209 | 2.2278e-3 | 1.0141 | +0.4 | 0.9994 | 155 | 3.6 | 2,717 |
| **S1 gemclean abs** | 195 | 676 | 2.47 | 6 | 120,899 | 24.12 | 100 | 2.2222e-3 | 1.0115 | +2.1 | 0.9993 | 16,011 | 367.7 | 18,883 |
| S1 WSClean auto nominres fast | 83 | 500 | 0.76 | 9 | 72,852 | 27.21 | 443 | 2.2456e-3 | 1.0222 | +1.7 | 1.0009 | 13 | 0.5 | 2,142 |
| S1 gemclean auto | 249 | 987 | 2.47 | 10 | 126,755 | 23.93 | 71 | 2.2158e-3 | 1.0086 | +1.1 | 0.9989 | 4,383 | 54.0 | 7,583 |
| S2 WSClean abs minres fast | 49 | 221 | 0.54 | 9 | 90,155 | 26.07 | 178 | 2.1351e-3 | 1.0151 | −4.1 | 0.9992 | 221 | 5.6 | 4,287 |
| S2 WSClean abs nominres fast | 80 | 475 | 0.76 | 9 | 88,060 | 26.16 | 197 | 2.1365e-3 | 1.0158 | −3.8 | 0.9994 | 194 | 3.2 | 4,241 |
| S2 WSClean abs nominres hogbom | 480 | 1125 | 0.76 | 6 | ≥ 90,000 | 26.03 | 117 | 2.1356e-3 | 1.0154 | −3.9 | 0.9993 | 297 | 6.7 | 4,303 |
| S2 WSClean abs pad2 fast | 115 | 538 | 0.77 | 9 | 88,060 | 25.98 | 215 | 2.1355e-3 | 1.0153 | −3.7 | 0.9992 | 149 | 4.1 | 4,156 |
| **S2 gemclean abs** | 140 | 650 | 2.47 | 6 | 117,802 | 24.62 | 100 | 2.1310e-3 | 1.0131 | +0.1 | 0.9992 | 12,270 | 262.5 | 16,580 |
| S2 WSClean auto nominres fast | 65 | 445 | 0.75 | 11 | 98,540 | 27.72 | 221 | 2.1557e-3 | 1.0249 | −1.0 | 1.0007 | 16 | 1.0 | 3,729 |
| S2 gemclean auto | 221 | 1040 | 2.47 | 12 | 134,582 | 24.18 | 72 | 2.1239e-3 | 1.0098 | −2.0 | 0.9989 | 4,267 | 54.4 | 9,002 |
| S3 WSClean abs minres fast | 46 | 157 | 0.54 | 6 | 45,906 | 26.77 | 217 | 2.6814e-2 | 1.0101 | −13.7 | 0.9976 | 128 | 1.6 | 4,830 |
| S3 WSClean abs nominres fast | 72 | 320 | 0.76 | 6 | 45,842 | 26.77 | 245 | 2.6814e-2 | 1.0101 | −13.8 | 0.9976 | 119 | 1.5 | 4,804 |
| S3 WSClean abs nominres hogbom | 306 | 770 | 0.76 | 5 | ≥ 45,000 | 26.67 | 102 | 2.6810e-2 | 1.0099 | −13.8 | 0.9978 | 127 | 1.7 | 4,805 |
| S3 WSClean abs pad2 fast | 71 | 303 | 0.77 | 6 | 45,422 | 26.73 | 238 | 2.6818e-2 | 1.0102 | −13.8 | 0.9977 | 112 | 1.4 | 4,804 |
| **S3 gemclean abs** | 58 | 362 | 2.46 | 5 | 47,659 | 26.38 | 100 | 2.6802e-2 | 1.0096 | −12.6 | 0.9979 | 418 | 5.5 | 5,296 |
| S3 WSClean auto nominres fast | 67 | 340 | 0.76 | 6 | 34,676 | 29.54 | 409 | 2.6945e-2 | 1.0150 | −25.8 | 0.9964 | 0 | 0 | 3,642 |
| S3 gemclean auto | 169 | 793 | 2.48 | 10 | 72,631 | 24.50 | 72 | 2.6726e-2 | 1.0067 | −7.2 | 0.9985 | 3,427 | 39.3 | 9,607 |

Dynamic range is not tabulated here and is not comparable between imagers as `tables` prints it: gemclean restores with 10.0″ × 8.0″, WSClean with 13.9″ × 8.3″. The Briggs image noise of the noise alone is 23.19 µJy; the remaining `auto` jobs
of WSClean are in the archive. RSS does not depend on load.

### 4.2 Flux per decade and the disc

Recovery at `abs`, mean ± standard deviation of model flux within one beam over
true flux:

| dataset, decade (n) | WSClean nominres fast | WSClean nominres hogbom | gemclean |
| --- | ---: | ---: | ---: |
| S1, 10-100 mJy (23) | 1.001 ± 0.006 | 1.001 ± 0.006 | 1.000 ± 0.006 |
| S1, 0.1-1 Jy (27) | 0.999 ± 0.004 | 0.999 ± 0.004 | 0.999 ± 0.004 |
| S3, 0.1-1 mJy (176) | 0.658 ± 0.765 | 0.659 ± 0.760 | 0.678 ± 0.765 |
| S3, 1-10 mJy (162) | 0.985 ± 0.066 | 0.985 ± 0.065 | 0.986 ± 0.065 |
| S3, 10-100 mJy (162) | 0.999 ± 0.037 | 0.999 ± 0.038 | 0.998 ± 0.040 |

S3's scatter is mostly blending; its faintest decade is largely below the threshold.
S2's disc (`abs`, truth 2 Jy, 40″): WSClean fast 1.9957 Jy and 39.8″; gemclean
1.9965 Jy and 39.9″ × 39.8″; centroids within 0.002 pixels. Point-source CLEAN
recovers this smooth disc in both. Its second moments are of the model within 2
FWHM.

The pixelised catalogue (nearest pixel, `truth`) scores Q/Q_truth 13.97 on S1 and
S2 and 2.01 on S3, with an exact residual peak of 136 mJy on S1. Off-grid sources
matter here: both imagers do far better than snapping the truth to pixels, by
spreading each source over neighbouring pixels (the `model px` column).

### 4.3 The false components of gemclean

On S1 at `abs`, gemclean's 16,011 false pixels hold +184 and −184 mJy (largest
0.43 mJy), spread from 2 to 128 beams from the nearest source; the largest few, near
the bright sources, also appear in WSClean's model at nearly the same pixels. Its
mean false pixel is about 23 µJy, one step of gain 0.1 at about 230 µJy.

- **Rejected: the weak-greedy certificate.** `-tau-min 0.9` (1,009 resyncs against
  132) gives 120,905 components, 16,146 false pixels and 369 mJy.
- **Rejected: Högbom against Clark.** WSClean's plain loop has 243 false pixels.
- **Measured: the length of the minor cycle.** gemclean's major-cycle rule is a
  fraction of Q. Once Q is dominated by noise that fraction is out of reach, so one
  minor cycle runs to the threshold on the phase-centre beam: on S1 cycle 3 has
  115,150 of the 120,899 components, from a 23.6 mJy peak, with a gap of 1.6e-3 of
  Q; on S2 111,402 components and 1.0e-3; on S3 42,564 from 4.7 mJy, 2.6e-5, and
  only 418 false pixels. WSClean's peak-based mgain makes 5 to 9 major cycles. The
  same S1 job with `-mgain 0.1` (`gemclean_mgain_0p1_s1` in the archive; `-j 16`):

  | S1 `abs` | majors | comps | inner rms µJy | inner peak µJy | Q/Q_truth | false px | false \|flux\| mJy | model px |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
  | gemclean mgain 0.8 | 6 | 120,899 | 24.12 | 100 | 1.0115 | 16,011 | 367.7 | 18,883 |
  | gemclean mgain 0.1 | 59 | 85,165 | 25.55 | 100 | 1.01355 | 169 | 4.3 | 2,771 |
  | WSClean hogbom | 6 | ≥ 85,000 | 25.55 | 112 | 1.0136 | 243 | 5.4 | 2,826 |

  So the components are an effect of that long cycle, and a short-cycle gemclean
  gives WSClean's plain-loop answer. Why a long cycle spreads flux over the field
  (the w-term's position dependence of the beam is the candidate, since the gap
  tracks it) is proposed, not tested. Tested on S1 only.

What this means for the comparison: gemclean's lower Q on S1 and S2 at mgain 0.8
comes with no better recovery and with more false flux, so it is partly fitting
noise. Its lower residual rms (24.1 against 25.7 µJy, the noise alone being 23.2) is
the same fact: at mgain 0.1 it goes back to 25.55 µJy. What does survive is exact
stopping: a peak of 100 µJy where WSClean's plain loop leaves 112 µJy and its fast
loop 231 µJy. No imaging-quality gain over WSClean is claimed on full-array data.

### 4.4 The real slice

| run (`-j 16`) | wall s | majors | comps | diverged | inner rms mJy | inner peak mJy | Q/Q0 | model flux Jy | central 65 px Jy | vs 14.953 Jy |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| WSClean abs minres fast | 2.4 | 1 | 263 | yes | 16,504 | 49,502 | 21.70 | −38.565 | 11.354 | −24.07 % |
| WSClean abs minres hogbom | 2.7 | 1 | ≥ 200 | yes | 16,504 | 49,502 | 21.70 | −38.565 | 11.354 | −24.07 % |
| WSClean abs nominres fast | 2.4 | 3 | 304 | yes | 428.9 | 1,222 | 2.5250e-2 | 14.763 | 14.955 | +0.01 % |
| WSClean abs nominres hogbom | 2.4 | 3 | ≥ 300 | yes | 428.9 | 1,222 | 2.5250e-2 | 14.763 | 14.955 | +0.01 % |
| WSClean abs pad2 fast | 2.2 | 3 | 301 | yes | 302.9 | 864 | 1.1973e-2 | 15.523 | 14.914 | −0.26 % |
| WSClean abs pad2 hogbom | 2.0 | 3 | ≥ 300 | yes | 296.8 | 843 | 1.0750e-2 | 15.741 | 15.105 | +1.02 % |
| WSClean auto, all six | 1.6-3.0 | 2 | 0 | no | 3,874-3,957 | 14,948-14,972 | 1.0000 | 0 | 0 | −100 % |
| **gemclean abs** | 3.2 | 5 | 92 | no | 22.8 | 47.9 | 4.7185e-4 | 15.137 | 13.155 | −12.03 % |
| gemclean auto | 5.7 | 14 | 45 | no | 43.5 | 130.5 | 5.6655e-4 | 14.819 | 14.819 | −0.90 % |

These reproduce the earlier note's WSClean runs (−38.57 Jy; 14.764 Jy and Q/Q0
2.53e-2). `-padding 2` halves the misfit and still diverges. gemclean's `abs` model
has the lowest misfit of the table and the worst central flux of the converged
runs: 2 Jy lies on the main-lobe ridge outside the central 65 pixels. The earlier
note's `exact-mgain` (Q/Q0 4.66e-4) had 14.897 Jy there. That is Theorem 5's
non-uniqueness again: descent is certified, the model is not. The slice is the
worst case for an image-size PSF and says nothing about MeerKAT at large.

### 4.5 A later gemclean commit, one job (measured; report to the gemclean work)

`origin/gmclean` moved during this work. The same S1 `abs` `-j 16` command at
`0d804e4` ("run minor cycles to the threshold by default"), `-mgain 0.8` still passed,
**did not reach the threshold**: it stopped on the 1,000,000-component limit after 2
major cycles, with Q/Q_truth 1.2444 (1.0115 at `d94850e`), inner residual rms 93.6 µJy
and peak 1.07 mJy, 191,870 false pixels holding 20.3 Jy of absolute flux, and flux
recovery 0.9989. Its second minor cycle took 999,863 components from a 207 mJy peak in
918 resyncs, with a gap of 1.1e-2 of Q; no major cycle ascends. The cause was not investigated, and this is
one job at a moving branch tip. Everything else in this note is `d94850e`; none of its
gemclean numbers should be taken to describe `0d804e4` or later. Scores:
`gemclean_0d804e4_s1` in the archive.

## 5. Thread dependence (measured; model and residual FITS, `-j 1` against `-j 16`)

| group | jobs | model L∞ | residual L∞ |
| --- | ---: | ---: | ---: |
| gemclean, all | 8 | 0 (bit-identical) | 0 |
| WSClean, simulated, `nominres` and `pad2` fast | 11 of 12 | 0 | ≤ 9e-13 |
| WSClean, S2 `auto` `pad2` fast | 1 of 12 | 2.5 mJy | 333 µJy |
| WSClean, simulated, default grid fast | 6 | 7.8e-5 to 6.9e-3 Jy | 3e-5 to 3.2e-4 Jy |
| WSClean, slice | 6 | 0 to 1.9e-3 Jy | 2e-6 to 3e-3 Jy |

The `-j 1` scores are in the archive; the S1 `auto` default-grid job goes from Q/Q0
2.2430e-3 at `-j 16` to 2.2457e-3 at `-j 1`, so the choice of `-j` moves WSClean's
result at that level (the O-CASA note found 2e-6 pixel differences at `-j 4`). This
is why every number names its `-j`. WSClean's plain loop was not compared across
threads on the simulations except S1 `abs` `nominres`: model L∞ 0 Jy, residual L∞ 0 Jy (§10).

## 6. Costs seen so far (PROVISIONAL, contended; not a comparison)

From WSClean's own log at `-j 16`, S1 `abs` `nominres`: inversion 57.6 s, prediction
32.4 s, deconvolution 8.1 s for the fast loop, and 21.0, 10.9 and 476 s for the plain
loop. gemclean on S1 `abs`: resync 102 s, major 62 s, minor 9.3 s, peak RSS 2.47 GB
(an FFT of the 2n grid per resync) against 0.76 GB. `-j 1` jobs: WSClean fast 110 to
414 s, gemclean 284 to 603 s; Per job there is
`load/NAME.txt` (load before and after); from the `-j 1` WSClean jobs and gemclean's
matrix onward also `.samples.txt` (every 60 s) and `.busy.txt` (the commands above 50 %
CPU, WSL and Windows, before and after), which name the competing jobs. The `-j 16`
fast jobs of WSClean have the first record only. The script now holds
`/home/gijsm/.rang-heavy.lock` for each job (`BENCH_LOCK`), so heavy jobs take turns;
of the runs here only the `-mgain 0.1` test and its scoring held it.

## 7. Timing subset to rerun on a quiet host (proposed)

```bash
bash examples/gemclean_bench_timing.sh GEMCLEAN_BINARY outputs/gemclean-bench-timing 3
```

Three repeats, imagers interleaved, WSClean first on odd repeats and gemclean first on
even ones; load, busy processes, wall, user and sys CPU and RSS recorded per run:

- WSClean `{s1,s2,s3}-abs-{minres,nominres}-fast-j{16,1}` (12 jobs);
- gemclean `{s1,s2,s3}-abs-nominres-fast-j{16,1}` (6 jobs);
- WSClean `s1-abs-nominres-hogbom-j16` (1 job).

Estimated from the contended numbers: about 1.1 h per repeat, 3.3 h in all;
`BENCH_TIMING_DATASETS=s1` cuts it to about 1.5 h. Report Docker start-up for WSClean,
which runs in a container, as gemclean does not. Use the gemclean commit that will be
cited, and rerun its accuracy jobs too: `origin/gmclean` had already moved from
`d94850e` to `0d804e4` when this note was written (§4.5), and the matrix there must
go to a new RUN_DIR, because the run script skips any job with a timing file.

## 8. Timings of this work (PROVISIONAL)

See [tool-timings.md](tool-timings.md). Simulation 36.5, 36.8 and 206.9 s; `-niter 0`
checks 300 s (8 jobs); prepare 37.6, 31.2, 32.3 and 2.0 s; scoring about 20 s per
simulated model with 4 threads; `gemclean` release build 215 s; WSClean: 36 jobs at
`-j 16` 4,036 s, 30 at `-j 1` 4,551 s; gemclean: 8 at `-j 16` 1,043 s, 8 at `-j 1`
2,571 s, `-tau-min 0.9` on S1 601 s, `-mgain 0.1` on S1 479 s; `check-all` on `62670bf`
426 s (705 Python tests passed, 45 skipped).

## 9. Reproduction

```bash
export PATH=$HOME/.cargo/bin:$PATH
uv venv -p /usr/bin/python3.14 .venv
uv pip install --python .venv/bin/python --index-url https://pypi.org/simple -e '.[pointing,beam,test]' ruff maturin
bash examples/gemclean_bench_datasets.sh                         # outputs/gmclean-bench-20261102/{data,prep,wsclean-dirty}
bash examples/gemclean_bench_run.sh wsclean outputs/gmclean-bench-20261102/wsclean    # the whole WSClean matrix
bash examples/gemclean_bench_gemclean.sh BINARY outputs/gmclean-bench-20261102/gemclean # the gemclean matrix
O=outputs/gmclean-bench-20261102
.venv/bin/python examples/gemclean_bench_compare.py score $O/prep/s1 $O/data/s1.json $O/gemclean $O/scores/gemclean-s1.json
.venv/bin/python examples/gemclean_bench_compare.py tables $O/scores/*.json
.venv/bin/python examples/gemclean_bench_archive.py $O research/results/gemclean-benchmark.json
```

Any imager runs the same matrix with `BENCH_TEMPLATE` (`gemclean_bench_run.sh`, header).
The full WSClean matrix is 24 jobs per dataset; this run did not do all of it (§10).

## 10. Not done

- WSClean's plain loop on the simulations ran at `-j 16` on `nominres` only (6 jobs)
  and at `-j 1` on S1 `abs` `nominres` only (924 s, PROVISIONAL). The other 12 jobs at
  `-j 16` and 17 at `-j 1` were not run: about 6 h of the host lock, which the gemclean
  work also needs, for little: the fast-loop grids agree in Q to about 0.1 %. The run script skips
  finished jobs, so `bash examples/gemclean_bench_run.sh wsclean
  outputs/gmclean-bench-20261102/wsclean s1 s2 s3` completes the 24 jobs per dataset.
- The quiet-window timing (§7). No speed result exists.
- The gemclean matrix at the current tip of `gemclean`. gemclean work is continuing elsewhere;
  these results describe `d94850e` only, except §4.5.

## 8. Rerun at gemclean 58e07e1 (the corrected default)

gemclean d94850e's numbers above are superseded for the comparison. Commit
`58e07e1` fixes the forcing-rule regression and changes the default minor-cycle
stop to the pointwise error the last major cycle measured
([gemclean.md](gemclean.md)). `examples/gemclean_bench_gemclean.sh` no longer forces
`-mgain 0.8`, which now means WSClean's peak fraction. Run: `BENCH_THREADS=16`,
`-abs-threshold 100 µJy` on S1-S3, under the host lock, scored by
`gemclean_bench_compare.py score`; archive
[results/gemclean-benchmark-58e07e1.json](results/gemclean-benchmark-58e07e1.json).
Accuracy is measured; wall time is PROVISIONAL and is not quoted.

| S1 / S2 / S3, abs | majors | comps | inner peak µJy | Q/Q_truth | false \|flux\| mJy |
| --- | ---: | ---: | ---: | ---: | ---: |
| gemclean 58e07e1 | 5 / 5 / 4 | 85,337 / 90,905 / 45,803 | 100 / 100 / 100 | 1.0136 / 1.0151 / 1.0099 | 4.3 / 4.9 / 1.6 |

Slice at `abs`: 3 majors, Q/Q0 4.76e-4, central flux −12.4 %, 0 ascending majors;
at `auto`: 14 majors, central flux −0.9 %. WSClean's baselines above are unchanged.

Limits: the rule's two constants were chosen on S1-S3, so this table is not a
held-out test, and the rule has no theorem. At `auto`, gemclean has no auto-mask
and leaves 39-54 mJy of false flux, so `auto` is not a matched comparison with
WSClean's masked runs. S3's faintest decade recovers 0.66 ± 0.76 at `abs`, as
expected below the threshold.
