# Rang: multiscale CLEAN in GeMClean (task G5)

Status, 2026-11-07: **implemented; protocol written and committed before any comparison; nothing
measured yet.**

Goal (finish plan, G5; owner decision 2, "in"): GeMClean gains WSClean 3.7's `-multiscale`, with
its scale selection, `-multiscale-scales`, `-multiscale-max-scales`, `-multiscale-scale-bias`,
`-multiscale-shape` (tapered quadratic and Gaussian), `-multiscale-gain` and the sub-minor loop,
combined with G3's `-channels-out` / `-join-channels` / `-fit-spectral-pol` and with
`-auto-threshold`; `rang-core image` passes the options. Oracle: WSClean `-multiscale` on S2 (G2's
sky set), on an extended real field (the ESO 137-006 pilot) and on a held-out sky frozen before it
runs. Without `-multiscale` the output stays byte-identical to main.

## 1. What WSClean 3.7 does (read in its source)

WSClean `v3.7` (`4f395b28abb5`) with radler `76fe4474c31c` and schaapcommon as submodules, the
tree G3 read. Paths are relative to the WSClean tree; radler's are under `external/radler/cpp`.

- **Options** (`main/commandline.cpp:1113-1146`, mapped in `main/settings.cpp:642-650`):
  `-multiscale` selects radler's `kMultiscale`; `-multiscale-gain` is radler's
  `sub_minor_loop_gain` (default 0.2), `-multiscale-scale-bias` its `scale_bias` (0.6),
  `-multiscale-max-scales` its `max_scales` (0, no limit), `-multiscale-scales` a comma list in
  pixels, `-multiscale-shape` `tapered-quadratic` (default) or `gaussian`,
  `-multiscale-convolution-padding` (1.1) and `-no-multiscale-fast-subminor`. The component
  gain is `-gain` (radler's `minor_loop_gain`), the major-cycle gain `-mgain`. radler's
  `divergence_limit` defaults to 4 (`settings.h:392`); WSClean sets it only for IUWT.
- **The beam that sets the scales** is the smallest theoretic beam of the output channels,
  `minTheoreticalBeamSize` (`main/wsclean.cpp:1002-1010`, passed to radler at 1557-1559), not the
  fitted PSF. Each is `1 / MaxBaseline()` (`gridding/msgridder.cpp:27`), the largest `|uvw|/λ`
  (three-dimensional, metres over the channel's wavelength) over visibilities with nonzero MS
  weight and nonzero imaging weight whose `x = u·Δx·N` satisfies `⌊x⌋ > −N/2` and `⌈x⌉ < N/2`,
  where WSClean tests `u` for the second axis as well (`y = u * pixel_size_y * image_height`;
  `gridding/msprovidercollection.cpp:15-39`, the loop at 204-228). In pixels it is divided by the
  larger pixel scale; a non-positive or non-finite one becomes one pixel
  (`multiscale_algorithm.cc:153-163`, `radler.cc:394-396`).
- **Scales** (`InitializeScales`, `multiscale_algorithm.cc:90-131`): without a list, 0 and then
  `4b, 8b, 16b, …` (the do-while starts at `2b`, pushes 0 for the first entry and doubles), each
  below half the image side, at most `max_scales` of them. A given list is sorted ascending,
  duplicates kept, with no size check.
- **Shapes** (`multiscale/multiscale_transforms.h`): the tapered quadratic on
  `k = 2⌈s/2⌉ + 1` pixels, `hann(r) · (1 − (r/s)²)` for `r < s` with
  `hann(r) = ½(1 + cos(2πr/(k+1)))` for `2r ≤ k + 1`; the Gaussian with `σ = 3s/16` on
  `k = 2⌈6σ⌉ + 1` pixels, capped at the image side (made odd); both normalised to unit sum. Scale
  0 is a delta.
- **Per-scale numbers** (`ConvolvePsfs`, 29-88, recomputed every major iteration, which also
  makes every scale active): `psf_peak` is the integrated PSF convolved with the shape, at the
  centre; the component gain is `gain / psf_peak`; the bias factor is
  `scale_bias^(−log2(s / 2b))`, 1 for scale 0 or a single scale. So the first automatic scale,
  `4b`, has `1/0.6`.
- **Peaks** (`FindActiveScaleConvolvedMaxima`, 580-636; `threaded_deconvolution_tools.cc`,
  `FindSingleScalePeak`): for every active scale the integrated residual (the weighted channel
  mean) is convolved with the shape and the largest `|value|` found inside a border of `⌈s/2⌉`
  pixels (scale 0: none). `SelectMaximumScale` (133-151) takes the largest `|value · bias|`.
  `Transform` convolves circularly on the `n × n` image (`schaapcommon` `Convolve` after
  `PrepareSmallConvolutionKernel`).
- **The minor loop** (`ExecuteMajorIteration`, 183-578): the cycle level is
  `max((1 − mgain) · first biased peak, threshold)`; while the selected scale's biased peak is
  above it, the components budget is not spent, a countdown of `max(8, 3·scales/2)` is not
  exhausted and the run does not diverge: convolve every channel's residual with the shape and
  every channel's once-convolved PSF again (the twice-convolved PSF); run the sub-minor loop at
  `max(peak·bias·(1 − sub_minor_gain), level)` (when the level is the larger, the countdown falls
  by one); subtract the components convolved with the once-convolved PSF from each residual on a
  padded grid (`CorrectResidualDirty`) and add them, convolved with the shape, to each model;
  `ActivateScales` (638-658) with the values found before the sub-minor loop (a scale stays
  active if it is the last one or its biased peak exceeds `(1 − gain)` times the last one's);
  find the peaks again.
- **The sub-minor loop** (`subminor_loop.cc`, `SubMinorLoop::Run`, `findPeakPositions`): the
  pixels inside the border whose convolved integrated value is at least `threshold / bias` are
  selected (the second, "considered pixel" threshold is set but never read); among them the
  largest `|integrated|` is cleaned with each channel's value at the pick times the scale's
  gain, spectrally fitted when asked (`PerformSpectralFit`), each channel subtracting its
  twice-convolved `n × n` PSF from the selected values where the offset falls inside the image;
  until the largest is at most the threshold, or diverges past 4 × its start.
- After the minor loop the major cycle (`radler.cc`) continues unless the threshold was the
  level (`isFinalThreshold`), the budget is spent or the run diverged.

## 2. Implementation (implemented)

- `core/src/gemclean/multiscale.rs`, `run_multiscale`: radler's algorithm for `K` channels with
  weights (one channel of weight one is a plain run), an optional G3 `PolynomialFit`, and
  gemclean's major cycles. Shapes (`shape_function`), scales (`scale_list`), bias
  (`bias_factor`) and the theoretic beam (`theoretic_beam`, WSClean's `u`-on-both-axes test
  included) as above. Unit tests: shape sides, normalisation and symmetry, the Gaussian's
  profile and cap; the automatic list for a 2.5-pixel beam on 2048 (0, 10, … 640), the max-scales
  cut, a sorted list with duplicates, the bias factors; the theoretic beam against a hand
  computation with a zero weight and a visibility outside the grid; and a 64² simulation with a
  Gaussian and a point whose fluxes are recovered, with one channel's run equal to the
  integrated one and a first-cycle relative gap under 1e-3.
- **Departures from radler, by design** (each a GeMClean choice, recorded here before any run):
  1. After every sub-minor loop each channel's map is made exact for its `2n` beam,
     `r̃ = r_major − B (m − m_major)` (one FFT pair per channel), where radler subtracts the
     components convolved with the `n × n` once-convolved PSF. The model is the shape-convolved
     components cut at the image edge, and the residual is updated with exactly that model.
  2. Shape convolutions are linear (zero outside the image) by gemclean's `Convolver`, where
     radler's are circular on the `n × n` image. The twice-convolved PSF is the `n × n` PSF crop
     convolved twice (linearly); the sub-minor loop uses it with radler's offset rule.
  3. `f64` throughout; radler is `f32`.
  4. The level at which a minor cycle hands back is gemclean's rule on the biased peak:
     `-mgain g` is radler's `(1 − g) · first peak`; without `-mgain` the measured rule
     (first cycle `g` = 0.95, later `max(ρ δ Σ|c|, floor · first peak)` with `δ` from the
     previous major cycle, as in `run`), read at the start of every sub-minor loop;
     `-minor-to-threshold` runs to the threshold. A major cycle starts only while the largest
     biased peak over all scales is at least the threshold, and a cycle that cleans nothing ends
     the run (`end: Stalled` in the report). Unlike WSClean, reaching the threshold as the level
     does not end the run by itself: the next major cycle checks the exact residual.
  5. The convolvers of the shapes and the twice-convolved PSFs are held in two
     least-recently-used caches of 2 × 10⁹ bytes each; what does not fit is rebuilt with the same
     bits, so the caches change no image.
- Refused with `-multiscale`: `-stop-rule certified`, `-mgain-misfit`, `-gram-operator`,
  `-floor-iterations`, `-audit`, `-multiscale-convolution-padding` (no padding: the convolutions
  are linear), `-no-multiscale-fast-subminor` (only the sub-minor loop is implemented). A
  `-multiscale-*` option without `-multiscale` is refused (WSClean ignores it silently).
  `-auto-mask` does not exist in gemclean (task G4); `rang-core image` keeps refusing
  `auto_mask` naming G4.
- `core/src/bin/gemclean.rs`: the options; the theoretic beam from the gridded visibilities
  (the smallest over output channels); single channel, joined (one run over all channels, with
  the fit) and unjoined (one run per channel) multiscale. Without `-multiscale` the code path
  is main's. The report gains `multiscale` (null without it): the scales with their kernel side
  and peak, bias, PSF peak, gain, components and flux, the theoretic beam, sub-minor loops and
  convolutions. The log prints WSClean's per-scale numbers.

## 3. Protocol (written 2026-11-07, committed before the first comparison)

### Settings

Simulated skies, both imagers: `-size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000
-gain 0.1 -mgain 0.8 -nmiter 1000 -abs-threshold 0.0001 -data-column DATA -field 0 -j 16
-multiscale`, WSClean's multiscale defaults unless a configuration says otherwise. GeMClean in its
default form (f64, `-wgridder-accuracy 1e-6`). WSClean 3.7 in `rang-wsclean-native:3.7` with
`-gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I
-no-update-model-required`, as G2 and G3 ran it, default memory budget. `-mgain 0.8` on both
sides for every gated run (the matched hand-back; GeMClean's measured rule has no radler
counterpart). Real field: `-size 4096 4096 -scale 3asec`, threshold 3 mJy, otherwise the same.

| run | data | options beyond the settings | gated |
| --- | --- | --- | --- |
| S2 | G2's S2 (`20261102-gemclean/bench/data/s2.ms`): 50 points and a 2 Jy Gaussian of FWHM 40″ | – | B, C |
| S2g | S2 | `-multiscale-shape gaussian` | B, C |
| H4 | `20261103-gemclean-heldout/sim/data/h4.ms`: 30 points, 6 Gaussians FWHM 20-200″, a tail of 25 | – | B, C |
| H4l | H4 | `-multiscale-scales 0,5,15,45,135` | B, C |
| D2j | G3's D2 (`20261106-g3-spectral/data/D2.ms`): 20 points, 5 Gaussians, curved spectra, 16 channels | `-channels-out 8 -join-channels -fit-spectral-pol 4 -abs-threshold 0.00015` | B, E |
| P | the pilot, set A (`20261103-gemclean-heldout/real/cal2.ms`, 256 channels) | `-size 4096 4096 -scale 3asec -abs-threshold 0.003` | B, D |
| M1 | held out (below) | – | B, C |

Reported only, GeMClean alone: S2 and H4 without `-mgain` (the measured rule); S2 with
`-auto-threshold 3` instead of the absolute threshold; D2 with `-channels-out 4` unjoined; the
same three also with WSClean where the options match (`-auto-threshold` is WSClean's own RMS
estimate, not GeMClean's MAD, so that pair is not matched).

### Criteria

Common definitions. `σ` is 1.4826 times the MAD of WSClean's residual on the inner field (the
central `2N/3`), outside every aperture below. `Ω` is the restoring beam area in pixels,
`π · BMAJ · BMIN / (4 ln 2)`, from WSClean's header. An aperture of `N` pixels has the noise term
`ε = 3 σ √(N / Ω)` (a sum of `N` pixels of beam-correlated noise, in Jy). Flux in an aperture is
the sum of the model image there (Jy/pixel), the same estimator for both imagers.

**A. Without `-multiscale`, byte-identical to main.** No file of the gemclean code changed between
G3's frozen build `92f0196` (binary `f153db8d…`) and main `b504ff9` (only `core/src/cal`,
`cnnflag`, `flag_extend`, `core/py` and two `mod` lines of `core/src/lib.rs`). The references are
G2's stored identity runs (`20261106-g2-memory/runs/c34`, as G3 used them) and G3's development
runs D1-C1 and D1-C3 (`20261106-g3-spectral/runs/dev1`), after one check: a build of main
`b504ff9` made here gives the same five files on S1 (default form) and the same files of D1-C1.
Then the G5 binary must give all five FITS files with the reference's SHA-256 on G2's 15 runs
(S1-S3 and H1-H4 in the default and the coarse form, the pilot at 256 channels in the default
form) and every per-channel and MFS FITS file of D1-C1 and D1-C3. One differing file fails A.

**B. Scale selection against WSClean's log** (every gated run). GeMClean's theoretic beam agrees
with WSClean's `Theoretic beam = …` line to the precision WSClean prints; the scales agree in
number and, rounded to whole pixels, in value with WSClean's `- Scale …` lines; the bias factors
agree to the printed 0.1; the PSF peaks and gains agree within 1e-4 relative.

**C. Extended flux on simulated skies** (S2, S2g, H4, H4l, M1). Apertures: a disc of radius
2 FWHM around every true Gaussian; overlapping discs are merged into one group. The truth `T` of
a group is the flux of its Gaussians inside its aperture (by integration over the pixels at 8×8
subsamples) plus every true point inside it. With `F_G`, `F_W` the two model fluxes and `ε` the
group's noise term:

- C1, truth: `|F_G − T| ≤ 0.02 T + ε`, or GeMClean no worse than WSClean by more than that
  margin, `|F_G − T| ≤ |F_W − T| + 0.01 T + ε`.
- C2, WSClean: `|F_G − F_W| ≤ 0.02 T + √2 ε`, or GeMClean nearer the truth, `|F_G − T| ≤
  |F_W − T|`.
- C3, cleaned: the rms of GeMClean's residual inside the aperture is at most
  `max(1.5 r_W, r_W + 0.5 σ)`, `r_W` WSClean's.
- C4, points: over the true points with `S/σ ≥ 200` and no Gaussian aperture within 6 pixels,
  the flux in a 6-pixel radius; GeMClean's median `|F/S − 1|` at most WSClean's plus 0.005.

A run passes C when every group passes C1, C2 and C3 and C4 holds. Why these numbers: the noise
term is the derived part. The 2 % (1 % against WSClean's own error) is a choice, not a
measurement: the Högbom pairs agreed to 0.04 % on S2's disc (`gemclean-benchmark.md`), within
0.1 % on G3's Gaussians and 0.09 % on the pilot's total model flux, but multiscale changes the
basis the model is built from, and departures 1-3 above make the two imagers' component sequences
differ after the first sub-minor loop; ten to twenty times the Högbom agreement is allowed for
that.

**D. The real field** (P). Regions from the source mask the held-out comparison made from its
Högbom images (`20261103-gemclean-heldout/real/images/source-mask.fits`, 5 σ, dilated by two
beams; no G5 output enters it): `M`, the whole mask; `R`, the mask within 10′ of the image centre
(the radio galaxy; its peak is 7″ from the phase centre). `σ` here is 1.4826 MAD of WSClean's
residual on the inner field outside `M`. For `M` and `R`: `|F_G − F_W| ≤ 0.02 F_W + √2 ε`; and in
`R` the rms of GeMClean's residual at most `max(1.5 r_W, r_W + 0.5 σ)`. The 2 % is the same
choice as in C; the floor there is 60 × thermal, and the Högbom pair's off-source model flux
already differed by 0.23 Jy of 83.7 (0.3 %).

**E. Joined channels** (D2j). G3's criterion C for Gaussians on the eight channels, unchanged: a
Gaussian passes when `|S'/S_T − 1| ≤ 0.05` and `|α' − α_T| ≤ 0.1`, or when GeMClean's errors are
at most WSClean's plus 0.03 (flux) and plus 0.05 (α); all five must pass. And C1-C3 on the MFS
models with the MFS truth (the channel truths' weighted mean with the channel weights).

**F. Reported, not gated**: per run the false flux (model flux outside every aperture: radius
6 pixels around points, the group apertures; on P, outside `M`), major cycles, components in
total and per scale, sub-minor loops, peak RSS (GNU `time -v`) and wall time (a shared host: no
timing claim). No run may exceed 24 × 10⁹ bytes RSS; such a run is stopped and reported.

### Held-out sky M1

H4's recipe (30 points 5-300 mJy, 6 Gaussians FWHM 20-200″ and 0.1-2 Jy, a curved tail of 25
Gaussians holding 3 Jy) at dec −60, 8 channels 1312.5-1487.5 MHz, 2 h at 8 s, 20 µJy natural
noise, through the same simulator (`examples/gemclean_bench_simulate.py --sky M1`). Its seeds are
drawn only after the build is frozen: the freeze is a commit of `fp-g5-multiscale` and the
sha256 of the `gemclean` binary built from it, both recorded here first; the sky and noise seeds
are the first 8 and the next 8 hex digits of `sha256("<commit> <binary sha256> M1")`, read as
integers; a seed equal to one in `python/rang/simtruth.py` `SEEDS` or the simulator's seed tables
moves on to the next 8 digits. Development runs (S2, S2g, H4, H4l, D2j, P) may change GeMClean;
after the freeze none is made without being labelled post hoc, and M1 is not redrawn. C and F
apply to M1 exactly as above.

### Not scored

Q against the truth through the exact gridder; timing; `-multiscale-convolution-padding` and
`-no-multiscale-fast-subminor` (refused); `-auto-mask` (G4); joined polarisations (G9).

## 4. Freeze (recorded before the held-out sky was drawn)

Frozen 2026-11-08 at commit `135f9e16e3c6b0714f9a66b4fdb80fefa45987b6` of `fp-g5-multiscale`
(main `3defaae` merged in, `277f888`); `gemclean` built from it (profile `gemclean`, rustc
1.93.1, `x86-64-v3`) has sha256
`2eb814f3e716d5846ebef29fe0822ae20b0ca4ba085788e8d9f60f2e228a34bf`, byte-identical to the
development binary `gemclean-dev3`, so the dev3 runs are runs of the frozen binary. M1's seeds
follow from these two by the rule in section 3.

## 5. Results

Not yet complete.

## For the coordinator

To be written with the results.
