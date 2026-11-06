# Rang: GeMClean's output channels, joined channels and spectral fitting (task G3)

Status, 2026-11-06: **rule written; nothing compared yet.** The rule below is committed before the
first comparison of any multi-channel image with WSClean or with the truth. Later sections are added
as the work is done; a fix made after a comparison is labelled post hoc.

Goal (finish plan, G3): GeMClean gains WSClean's `-channels-out`, `-join-channels` and
`-fit-spectral-pol`, with `-channel-range` and channel averaging for the `rang-core image` options
`channels_out`, `join_channels`, `fit_spectral_pol` and `average_channels`, which `core_config.py`
refuses naming G3. Oracle: WSClean 3.7 on simulated spectral skies, then held-out skies made with a
new seed after the build is frozen. Single-channel behaviour stays byte-identical to main.

## What WSClean 3.7 does (read in its source, `4f395b2`)

WSClean v3.7 with its submodules radler and schaapcommon, cloned at the tag (`wsclean`
`4f395b28abb5`); paths are relative to the WSClean tree.

- **Output channels.** `main/wsclean.cpp`, `WSClean::makeImagingTable` collects the unique channel
  frequencies of the selected spectral windows in ascending order; `-channel-range s e` keeps
  `[s, e)` of them (`makeImagingTableEntry`). `makeImagingTableEntryChannelSettings` gives output
  channel `i` of `n` the input channels `i·N/n` to `(i+1)·N/n − 1` (integer division), and refuses an
  empty one. Its band runs from the lowest channel's frequency minus half its width to the highest's
  plus half; `CentralFrequency()` (`structures/imagingtableentry.h`) is the middle of that band.
- **Weighting.** `main/commandline.cpp:1591`: `mfWeighting = (joinedFrequencyDeconvolution &&
  !noMFWeighting) || mfWeighting`. With MF weighting one weight grid is made from all output
  channels together (`main/imageweightinitializer.cpp`, `InitializeMfWeights`); without it each
  output channel has its own (`InitializeWeights`, `cache.Get(..., outputChannelIndex, ...)`).
  Natural weighting is the same either way.
- **Channel weight.** Each channel's `imageWeight` is `MSGridderData::ImageWeight()`, the sum of the
  gridded weights over `GetNVisibilities(gain_mode)` (`gridding/msgridderdata.h`; 1 for Stokes I,
  `gridding/gainmode.h`), written as `WSCIMGWG`. It is the channel's weight in every sum below
  (`main/wsclean.cpp:112-113`, `channel_info.weight = entry.imageWeight`; radler's
  `WorkTableEntry::image_weight`).
- **Joined deconvolution.** radler `cpp/algorithms/generic_clean.cc`,
  `GenericClean::ExecuteMajorIteration`, with the default sub-minor loop
  (`settings.h:576`, `use_sub_minor_optimization = true`; `cpp/algorithms/subminor_loop.cc`,
  `SubMinorLoop::Run`): the peak is found on the integrated image, which for one polarisation and
  without `-squared-channel-joining` is the weighted mean of the channel residuals with the channel
  weights (`cpp/image_set.cc`, `GetLinearIntegratedWithNormalChannels` and
  `GetSquareIntegratedWithNormalChannels`, which reduce to the same sum). At the peak each channel's
  value is its own residual there times the gain (`componentValues[i] = residual_i[peak] · gain`);
  `PerformSpectralFit` then replaces the values by the fitted ones; each channel's model gets its
  value and each residual has its own PSF (peak 1) subtracted with its value. The major-cycle stop
  (`-mgain`) and the threshold apply to the integrated peak.
- **Spectral fit.** `external/schaapcommon/src/fitters/spectralfitter.cc`, `SpectralFitter::Fit`
  and `Evaluate` in `kPolynomial` mode (`-fit-spectral-pol n`): an ordinary polynomial in
  `x = ν/ν_ref − 1`, fitted by weighted least squares (`polynomialfitter.cc`, GSL
  `gsl_multifit_wlinear`) with the channel weights, over the channels of positive weight, with the
  number of terms cut to the number of points; evaluated at every channel's frequency. `ν_ref`
  (`ComputeReferenceFrequency`) is the weighted mean of the channel frequencies, those being the
  weighted means of the channels' central frequencies (`ImageSet::CalculateDeconvolutionFrequencies`;
  with no `-deconvolution-channels`, each output channel's own). `-fit-spectral-log-pol` is
  `kLogPolynomial`: a power law with logarithmic terms fitted non-linearly
  (`nlplfitter.cc`, `NonLinearPowerLawFitter`), a different fitter.
- **MFS images.** `math/imageoperations.cpp`, `MakeMFSImage`: each MFS image (dirty, PSF, model,
  residual) is the per-pixel weighted mean of the channel images with the channel weights; its band
  is the lowest to the highest channel edge, its `WSCIMGWG` the sum of the weights. The MFS restoring
  beam is fitted on the MFS PSF; `RenderMFSImage` restores the MFS model with that beam onto the MFS
  residual. Each channel image is restored with the beam fitted on its own PSF
  (`main/wsclean.cpp`, `processFullPSF` and the restore at line 1110). Names
  (`io/imagefilename.h`): `<name>-0000-<kind>.fits` per channel (four digits) and
  `<name>-MFS-<kind>.fits`, only when there is more than one output channel.
- **Channel averaging.** WSClean 3.7 has no option that averages channels before imaging.

## Rule (written 2026-11-06, committed before the first comparison)

### Settings

Both imagers, every run unless stated: `-size 2048 2048 -scale 1.5asec -weight briggs 0.5
-niter 1000000 -gain 0.1 -nmiter 1000 -data-column DATA -field 0 -j 16`. GeMClean in its default
form (f64, `-wgridder-accuracy 1e-6`, its default major-cycle rule). WSClean 3.7 in
`rang-wsclean-native:3.7` with `-gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6
-mgain 0.8 -pol I -nmiter 0 -no-update-model-required`, as G2 ran it. Configurations:

| | options | threshold |
| --- | --- | --- |
| C0 | none (one output channel): the baseline gap between the two imagers | `-abs-threshold 0.00015` |
| C1 | `-channels-out 8 -join-channels -fit-spectral-pol 4` | 0.00015 |
| C2 | `-channels-out 8 -join-channels` | 0.00015 |
| C3 | `-channels-out 4` (not joined; per-channel weighting, WSClean's default without joining) | 0.0003 |
| C4 | `-channel-range 2 14 -channels-out 3 -niter 0` (dirty and PSF only) | – |

### Simulated skies

A new script, `examples/g3_spectral_simulate.py`, from the benchmark's simulator
(`examples/gemclean_bench_simulate.py`: 64 MeerKAT dishes, exact direct Fourier sums through
`rang.core.predict_components`, rang's table writer, noise on all four correlations). Track 2 h at
16 s, 16 channels 900-1670 MHz (48.125 MHz each), natural MFS noise 20 µJy. Spectra
`S(ν) = S₀ (ν/ν₀)^(α + β ln(ν/ν₀))` with `ν₀ = 1.2 GHz` (`log_poly` with coefficients α, β).
Positions continuous (not on pixel centres), inside the inner two-thirds.

- **D1** (development, dec −30): 40 points, `S₀` log-uniform 2-500 mJy, α uniform in [−1.2, 0.3];
  every third point curved, β uniform in [−0.6, 0.6], the rest β = 0; at least 40 pixels apart.
- **D2** (development, dec −30): 20 points as D1, and 5 circular Gaussians of FWHM 15-60″ (log-uniform),
  `S₀` 0.1-1 Jy, α in [−1.2, 0], two of them with β in [−0.6, 0.6]; every Gaussian at least
  4 FWHM plus 40 pixels from every other component.
- **H1s** (held out): D1's recipe at dec −60. **H2s** (held out): D2's recipe at dec −10.

D1 and D2 have fixed seeds. H1s and H2s are drawn only after the build is frozen: the freeze is a
commit of `fp-g3-spectral` and the sha256 of the `gemclean` binary built from it, both recorded
here first; the held-out sky and noise seeds are the first 8 and the next 8 hex digits of
`sha256("<commit> <binary sha256> H1s")` (and `H2s`). No change to GeMClean is made after the
freeze without being labelled post hoc, and the held-out skies are not redrawn.

### Criteria

**A. Single channel unchanged (class A).** One output channel takes the code path of main untouched.
G2's identity set: the seven skies S1-S3 and H1-H4 in both forms (default; `-single
-wgridder-accuracy 1e-4`) at G2's settings, and the 256-channel pilot in the default form. The
reference is G2's final binary `83baf9f` (sha256 `647bc32a…620a0bfe`): no file of the gemclean code
changed between `83baf9f` and main `0cb508b` (only `core/src/cal` and `core/py`), so G2's stored runs
(`D:\rang\outputs\20261106-g2-memory\runs\c34\img`) are the reference, after one check: a build of
main `0cb508b` must give the same five files on S1 in the default form. All five FITS files of all
15 runs of the G3 binary must have the reference's SHA-256. One differing file fails A.

**B. The dirty images and PSFs against WSClean (C1, C3, C4, on all four skies).** Per channel and
MFS, the largest |GeMClean − WSClean| at most 1e-5 of WSClean's PSF peak (PSF) and of the largest
|WSClean dirty| (dirty); `WSCIMGWG` within 1e-6 relative per channel and MFS; `CRVAL3` and `CDELT3`
equal to 1e-9 relative; GeMClean writes every per-channel and MFS file of the five kinds that WSClean
writes under the same name. This checks the grouping, the weighting (MF or per channel), the
normalisation and the MFS sums.

**C. Truth (C1, on all four skies).** One estimator for the truth, GeMClean and WSClean alike:

- per output channel `k`, the flux `F_k` of a component is the sum of the channel-`k` model image
  within radius `R` of its true position (`R` = 6 pixels for a point, 2 FWHM for a Gaussian); for the
  truth, `T_k` is the mean of `S(ν)` over the channel's input channels;
- `ln F_k = a + α' ln(ν_k/ν₀) + β' ln²(ν_k/ν₀)`, weighted least squares over the 8 channels, with
  `ν_k` the channel's central frequency and weights `1/σ_ln,k²`, `σ_ln,k = σ_k/F_k`,
  `σ_k = σ_MFS √(W/w_k)` (`w_k` the channel weight, `W` their sum, `σ_MFS` 1.4826 MAD of WSClean's C1
  MFS residual on the inner field); the fitted `S'(ν₀) = e^a`, α', β' and their standard errors
  σ_α, σ_β from the fit's covariance. A channel with `F_k ≤ 0` fails the source.
- The estimator applied to `T_k` gives the reference `S_T`, `α_T`, `β_T` (so that the estimator's
  own bias cancels).

Points are scored when `SNR = S_T/σ_MFS ≥ 200`. A point passes when `|S'/S_T − 1| ≤ 0.02 + 3/SNR`,
`|α' − α_T| ≤ 0.03 + 3σ_α` and, for a curved point (β ≠ 0 in the truth), `|β' − β_T| ≤ 0.1 + 3σ_β`.
A sky passes C for an imager when at least 90 % of its scored points pass. **GeMClean passes C** on a
sky when it passes there, and in addition its median `|α' − α_T|` is at most WSClean's plus 0.01,
its median `|S'/S_T − 1|` at most WSClean's plus 0.005, and its failed points at most WSClean's plus
one. Gaussians (D2, H2s), Högbom on both sides: each passes when `|S'/S_T − 1| ≤ 0.05` and
`|α' − α_T| ≤ 0.1`, or, if WSClean misses those, when GeMClean's errors are at most WSClean's plus
0.03 (flux) and plus 0.05 (α); all must pass.

**D. MFS images against WSClean (C1, C2, C3 on all four skies), relative to C0.** Beam-independent:
the scorer restores both MFS models with one beam (WSClean's MFS `BMAJ`, `BMIN`, `BPA`, with
GeMClean's restoring kernel) and adds each imager's own MFS residual. On the inner field (central
2N/3): `d_rms` = rms of the difference / σ_MFS, `d_max` = largest |difference|, and the false flux
`FF` = MFS model flux outside the radius `R` of every true component. With `X` the value of the same
measure for C0 on the same sky, each configuration must have `d_rms ≤ max(1.5 X, X + 0.1)`,
`d_max ≤ max(1.5 X, X + 100 µJy)` and `|FF_G − FF_W| ≤ |FF_G − FF_W|(C0) + 1 mJy`. Joining, fitting
or splitting may add that much to the gap the single-channel imagers already have, no more.

**E. Channel averaging.** `-average-channels 2` (rang's own option; WSClean has none) on D1 against
the same MS averaged by CASA 6.7.6 `mstransform(chanaverage=True, chanbin=2, datacolumn='data')` in
`rang-o-casa:6.7.6.14`: GeMClean's dirty image and PSF with the option on D1 agree with GeMClean's
on the averaged MS within 1e-6 of the PSF peak and of the largest |dirty|, and with WSClean's on the
averaged MS within 1e-5, at `-niter 0`, one output channel and `-channels-out 4`.

**F. Memory.** Peak RSS (GNU `time -v`) for every multi-channel run of both imagers, reported. No
run may exceed 24 × 10⁹ bytes (G2's budget). No tuning.

**Held out.** B, C, D and F are applied to H1s and H2s exactly as to D1 and D2, after the freeze,
and reported apart. E is not repeated.

**Not scored.** Q/Q_truth through the exact gridder (it needs a per-channel predict the scorer does
not have); timing (the host is shared); `-fit-spectral-log-pol` (see the owner decisions).

### Owner decisions made here (the owner asked for none to be put to him)

1. `-fit-spectral-pol` only: `-fit-spectral-log-pol` is refused with a message, since its
   non-linear fitter is a separate port; recorded as left for later.
2. `average_channels` is rang's own option, since WSClean has none: Stokes I weighted means of
   `N` adjacent channels after `-channel-range` and before weighting, the weights summed, the
   frequency the plain mean, a last group of fewer than `N` kept; checked against CASA
   `mstransform`.
3. The joined loop keeps GeMClean's minor step (exact values at the pick, resyncs, its default
   major-cycle rule) on the integrated image, rather than WSClean's sub-minor loop; the per-channel
   values, the fit and the integrated peak follow WSClean.
4. Not implemented, refused by name: `-deconvolution-channels`, `-squared-channel-joining`,
   `-channel-division-frequencies`, `-divide-channels-by-gaps`; in joined mode also
   `-stop-rule certified`, `-gram-operator`, `-floor-iterations` and `-audit`.
5. MF weighting follows WSClean's default (on with `-join-channels`), with `-mf-weighting` and
   `-no-mf-weighting`.
6. With more than one output channel each channel's gridder frees its work grids after each pass,
   so the grids are held for one channel at a time (the same values; it is not done with one channel).

## Implementation (implemented)

- `core/src/gemclean/spectral.rs`: WSClean's channel grouping (`channel_groups`, with
  `-channel-range` on the channels in ascending frequency), channel selection, rang's channel
  averaging (`average_channels`) and schaapcommon's polynomial fit (`PolynomialFit`: weighted least
  squares in `x = ν/ν_ref − 1` by Householder QR over the channels of positive weight, terms cut to
  the number of points, `ν_ref` the weighted mean frequency, 150 MHz without weight). Unit tests:
  the grouping against WSClean's formula (ascending and descending bands, refusals), the fit against
  an exact polynomial with a zero-weight outlier and against the normal equations of a weighted
  line, and the averaging.
- `core/src/gemclean/joined.rs`, `run_joined`: GeMClean's loop (`run_with_bound`) on the integrated
  map `Σ a_k r̃_k` (`a_k = w_k / Σw`), with a working map and the components since the last resync
  per channel. At a pick each channel's exact value is its own gather on its own beam's exterior;
  the integrated value, `τ` (with `e = Σ a_k f_k b_k(0) Σ|c|_k`), the drift, the threshold, the
  peak-fraction and measured stale rules read the integrated values; the channel values are
  `γ r_k / b_k(0)`, then fitted and evaluated; each channel subtracts its own patch, and the
  integrated map the weighted patches. A resync makes every channel's map exact and rebuilds the
  integrated map from them. The predicted misfit change uses the general form `−c r + c² b(0)/2`.
  Unit tests: one channel of weight one gives [`run`]'s picks, components, residual, cycles and
  stop bit for bit; two channels of a sky with spectral slopes recover both sources' fluxes in both
  channels with a two-term fit.
- `core/src/bin/gemclean.rs`: `-channels-out`, `-join-channels`, `-fit-spectral-pol`,
  `-channel-range`, `-average-channels`, `-mf-weighting`, `-no-mf-weighting`; refusals of
  `-fit-spectral-log-pol`, `-deconvolution-channels`, `-squared-channel-joining`,
  `-channel-division-frequencies`, `-divide-channels-by-gaps`, of a fit without joined channels, and
  of the certified rule, the Gram operator, `-floor-iterations` and `-audit` with more than one output
  channel. With one output channel and no range or averaging the code path is main's, line for line.
  With more: the data are split per output channel (MF weights cut from one weight grid, or each
  channel's own), rows without weight in a channel dropped from it, one measurement, `2n` PSF, beam
  and fitted restoring beam per channel, then `run_joined` or `run` per channel. Files
  `<name>-0000-<kind>.fits` with the channel's band (`CHAN_WIDTH` edges), counters and beam, and
  `<name>-MFS-<kind>.fits`, the weighted means, the beam fitted on the MFS PSF, the MFS image
  restored from the MFS model and residual. One `-report.json` with every channel.
- `core/src/gemclean/measure.rs` and `wgridder.rs`: `GridMeasurement::releasing_grids` frees the
  gridder's work grids after each residual (`Prepared::release_grids`), used only with more than one
  output channel (owner decision 6). `fits::wcs_cards_band` is `wcs_cards` for a given band;
  `input::channel_widths` reads `CHAN_WIDTH`.
- `python/rang/core_config.py`, `core_pipeline.py`: the four G3 refusals are gone; a fit without
  `join_channels` and `channels_out ≥ 2` is a configuration error; `rang-core image` passes
  `-average-channels`, `-channels-out`, `-join-channels` and `-fit-spectral-pol`. Test:
  `test_the_spectral_image_options_reach_gemclean`.
- Simulator `examples/g3_spectral_simulate.py`; scripts in
  [results/g3-spectral-scripts](results/g3-spectral-scripts/) (`batch.sh`, `run_g.sh`, `run_w.sh`,
  `cfg.sh`, `score.py`, `identity.py`, `id_run.sh`, `avg_batch.sh`, `casa_avg.*`, `sim.sh`,
  `build.sh`, `main_ref.sh`).

The scorer's common restoring beam for criterion D is its own Gaussian (FWHM and PA from WSClean's
MFS header), applied identically to both imagers' models, not GeMClean's restore code; the rule
asked only that one beam be used for both.

## Freeze (recorded before the held-out skies were drawn)

Frozen 2026-11-06 at commit `92f0196d203f84b780162ca7379a9ea979b5336e` of `fp-g3-spectral`; `gemclean`
built from it (profile `gemclean`, rustc 1.93, `x86-64-v3`) has sha256
`f153db8d31779bd782af018ef592db3782f2c67a4cb3c2c1bc734c8a6c644ae2`, byte-identical to the development
binary `gemclean-dev1` used on D1 and D2, so the development runs are runs of the frozen binary.
Held-out seeds by the rule, `sha256("<commit> <binary sha256> <sky>")`:

| sky | sky seed | noise seed |
| --- | --- | --- |
| H1s | `0x1f3ee7f2` | `0x77d06fe6` |
| H2s | `0x588f203c` | `0xdab58ae3` |

A host reboot at 11:15 stopped the first development batch; its one partial run (D1-C0) and the
WSClean D1-C4 run made without `-make-psf` were deleted and rerun from scratch.
