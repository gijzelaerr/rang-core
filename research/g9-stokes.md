# Rang: GeMClean in Stokes I, Q, U, V and joined polarisations (task G9)

Status, 2026-11-07: **implemented; protocol frozen (this section 3), no gated comparison run yet.**
The results sections are added as the runs finish.

Goal (finish plan, G9): GeMClean images in Stokes I, Q, U and V and joined polarisations as WSClean 3.7
does: `-pol` (`I`, `IQUV`, `QU`, `xx,yy`, ...) as far as WSClean's semantics go for linear feeds,
`-join-polarizations`, and both with G3's `-channels-out` / `-join-channels`; wired through
`rang-core image` (E2-B's image stage was refused naming G9). Oracle: WSClean 3.7 on simulated
polarised and unpolarised skies, then a held-out sky drawn after the build is frozen.

## 1. What WSClean 3.7 does (read in its source, `4f395b2`, and probed)

WSClean v3.7 with radler, aocommon and schaapcommon at the tag (`4f395b28abb5`, the commit of
`rang-wsclean-native:3.7`), cloned read-only to `~/Build/tmp/20261107-g9-wsclean-src`.

- **The list.** `aocommon/polarization.h`, `Polarization::ParseList`: case-insensitive, `,` ` ` or
  `/` between entries, into a `std::set` in enum order I < Q < U < V < RR < RL < LR < LL < XX < XY <
  YX < YY. The images are made and named in that order.
- **Forming each polarisation.** `schaapcommon/src/reordering/reordering.cc`, `ExtractData` and
  `ExtractWeights` (the provider polarisation is the entry's for the wgridder without facets,
  `Settings::GetProviderPolarization`): a correlation the MS holds (XX, YY) is copied with its own
  weight (zero when flagged or not finite). Otherwise I = (XX + YY)/2, Q = (XX − YY)/2,
  U = (XY + YX)/2, V = −i (XY − YX)/2 (the value `(XY − YX)·0.5`, then `(im, −re)`), each with the
  weight `min(4 w_a, 4 w_b)` of its two correlations, zero when either is flagged or not finite;
  a formed value that is not finite becomes zero. The sky-frame convention is aocommon's: XX = I + Q,
  XY = U + iV, YX = U − iV, YY = I − Q, X north-south.
- **The PSF and the restoring beam.** `WSClean::runIndependentGroup`: the PSF is imaged only for
  the first polarisation of the set (`<name>[-0000]-psf.fits`, no polarisation in the name, its
  `CRVAL4` the first polarisation's); every polarisation of a channel is restored with that beam and
  deconvolved with that PSF.
- **The imaging-weight grid.** `io/imageweightcache.h`: the cache is keyed on the output channel
  only, so which polarisation's weights build it depends on the run order. Per-channel weighting:
  the first polarisation's, except with `-join-channels`, more than one output channel and
  polarisations not joined, where each polarisation's group recomputes it from its own weights. MF
  weighting (`InitializeMfWeights`, the front entry of every squared group): the first polarisation
  of each channel when polarisations are joined, every polarisation otherwise. Each polarisation's
  gridding weight is its own visibility weight times that imaging weight.
- **Header weights and MFS weights.** `WSCIMGWG` of a dirty image is its own entry's weight sum; of
  the PSF the first polarisation's. The per-channel `OutputChannelInfo::weight` is overwritten by
  every entry imaged in the channel (`main/wsclean.cpp:417`), so model, residual and restored
  images, and every MFS image of every polarisation (`math/imageoperations.cpp`, `MakeMFSImage`), use
  the **last** polarisation's channel weights. radler's channel weights for joined channels are the
  `image_weight` of each channel's first entry in the deconvolution group.
- **Joined polarisations.** `main/commandline.cpp:1595`: `-join-polarizations` links every imaged
  polarisation. WSClean's help says peaks are found "in the sum of squares of the polarizations".
  **The 3.7 binary's default loop does not do that.** The default sub-minor loop
  (`radler/cpp/algorithms/subminor_loop.cc`, `findPeakPositions` and `GetMaxComponent`) and the
  first peak of every major iteration (`generic_clean.cc:71`) read `ImageSet::GetLinearIntegrated`,
  which without `-squared-channel-joining` is the **linear** sum `f Σ_k a_k Σ_p r_kp` with `f` the
  polarisation normalisation (`image_set.h`: `1/P` for Stokes parameters without I, `0.5` for XX,YY
  or a full linear set, else 1). Only `-no-fast-subminor`'s loop reads `GetSquareIntegrated` after
  its first pick. Each linked entry's component is its own residual at the peak times the gain; the
  spectral fit is per polarisation over the channels (`MultiPolarizationFitAndEvaluate`).
- **Refusals.** XY and YX make complex images (an extra `XYi` image) and need joined cleaning;
  `-join-polarizations` with one polarisation is an error.
- **Names.** `io/imagefilename.h`: `<name>[-0000][-<pol>]-<kind>.fits`, the polarisation only when
  more than one is imaged; MFS `<name>-MFS[-<pol>]-<kind>.fits`; `CRVAL4` I 1, Q 2, U 3, V 4,
  XX −5, YY −6 (`aocommon/fits/fitswriter.h`).

**Probe (development, not scored; run before this protocol).** `/mnt/d/rang/outputs/g9-20261107-01-probe`
([probe.sh](results/g9-stokes-scripts/probe.sh), [probe_read.py](results/g9-stokes-scripts/probe_read.py)):
two sources, A (I = 1, Q = −0.8) and B (I = 0.6, Q = +0.5), 16 dishes, 4 channels, per-correlation
weights and flags (`--weights varied`). `-pol IQ -join-polarizations -niter 1` picks **B** in the
default loop and with `-no-fast-subminor` (a linear sum picks B, squares pick A): the source reading
stands. The probe's `WSCIMGWG` values (per polarisation and channel, with and without joined
channels and polarisations, MF and per-channel weights, `xx,yy`) are what the weight rules above
predict; GeMClean's development build reproduced every one within 3e-9 and every dirty image and PSF
within 1e-6 of the file's peak ([probe_g.sh](results/g9-stokes-scripts/probe_g.sh)).

## 2. Implementation (implemented)

- `core/src/gemclean/stokes.rs`: `Pol` (I, Q, U, V, XX, YY), WSClean's list parser (XY, YX and
  circular correlations refused with a message naming this note), the normalisation, the
  correlation indices and cell conversion of `ExtractData`/`ExtractWeights`, the weight-source rule
  (`weight_sources`), `imaging_weights` (one WSClean weight grid from several polarisations' weights
  over a channel set) and `set_stokes_card`. Unit tests: parsing, normalisation, the four Stokes
  parameters of the sky-frame coherencies with their weights and flags, the weight-source rule.
- `core/src/gemclean/input.rs`: `Selection::polarization` (default I); `read_ms` forms that
  polarisation; Stokes I keeps `stokes_cell`, unchanged, so the row selection and weight source of
  every polarisation are the same code.
- `core/src/gemclean/joined.rs`: `run_joined_pols`, `run_joined` over channel-major entries with one
  coefficient per entry, `a_k f` (the linear sum of section 1), per-polarisation spectral fits;
  `run_joined` calls it with one polarisation and `f = 1`, the same arithmetic. Unit test: two joined
  polarisations recover both skies (a negative Q included) and one polarisation equals `run_joined`.
- `core/src/bin/gemclean.rs`: `-pol`, `-join-polarizations` (refused with one polarisation, as
  WSClean; `-link-polarizations` refused). One polarisation, I or not, takes main's code path (a
  non-I polarisation only changes what is read and `CRVAL4`). Several: `run_polarizations` reads each
  polarisation, builds the weight grids by the rule, deconvolves in WSClean's groups (joined
  polarisations, joined channels, both, or each entry alone), shares a beam between polarisations of
  a channel only where rows and gridding weights are bit-identical (GeMClean's exact values need
  each measurement's own PSF; WSClean uses the first polarisation's PSF for all), writes WSClean's
  names, `CRVAL4` and header weights (section 1) and the MFS images with the last polarisation's
  channel weights. With several polarisations the certified rule, `-gram-operator`,
  `-floor-iterations` and `-audit` are refused.
- `python/rang/core_config.py`, `core_pipeline.py`: the G9 refusals are gone; `image.pol` is parsed
  as gemclean parses it, a join with one polarisation is a configuration error; `rang-core image`
  passes `-pol` and `-join-polarizations` only when they differ from the defaults (earlier argv and
  receipts unchanged); data with only XX and YY refuse an image of U or V. E2-B's image section
  validates. Test: `test_the_polarisation_options_reach_gemclean`.
- Simulator `examples/g9_stokes_simulate.py`; scripts in [results/g9-stokes-scripts](results/g9-stokes-scripts/).

## 3. Rule (written 2026-11-07, committed before the first gated comparison)

### Settings

Both imagers, every run: G3's settings, `-size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter
1000000 -gain 0.1 -nmiter 1000 -data-column DATA -field 0 -j 16`. GeMClean in its default form (f64,
`-wgridder-accuracy 1e-6`, its default major-cycle rule). WSClean 3.7 `rang-wsclean-native:3.7` with
`-gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -mgain 0.8 -nmiter 0
-no-update-model-required` and its default (fast sub-minor) loop, as G2 and G3 ran it, `-make-psf`
at `-niter 0`. Configurations ([cfg.sh](results/g9-stokes-scripts/cfg.sh)):

| | options | threshold |
| --- | --- | --- |
| Q0 | `-pol I`: the single-polarisation baseline gap | `-abs-threshold 0.00015` |
| Q1 | `-pol IQUV` (not joined) | 0.00015 |
| Q2 | `-pol IQUV -join-polarizations` | 0.00015 |
| Q3 | `-pol IQUV -join-polarizations -channels-out 8 -join-channels` (E2-B's shape, MF weights) | 0.00015 |
| Q4 | `-pol xx,yy -niter 0` | – |
| Q5 | `-pol IQUV -channels-out 4 -niter 0` (per-channel weights) | – |
| Q6 | `-pol QU -join-polarizations -channels-out 4 -join-channels` (normalisation 1/2, Faraday rotation) | 0.00015 |

### Skies

- **D1** (unpolarised, development): G3's D1 MS read in place
  (`/mnt/d/rang/outputs/20261106-g3-spectral/data/D1.ms`): 40 points with curved spectra, noise on
  all four correlations, the model in XX and YY only, uniform weights. Runs Q0, Q1, Q2.
- **P1** (polarised, development): `examples/g9_stokes_simulate.py --sky P1`, seeds 20261181 (sky)
  and 20261182 (noise), new (not in `rang.simtruth.SEEDS`, not G3's 20261161-72, not E0's
  20261191-93): G3's array, track and band (64 dishes, 2 h at 16 s, 16 channels 900-1670 MHz, 20 µJy
  natural MFS noise), dec −30; 36 points, `S0` 5-500 mJy, α in [−1.2, 0.3]; two thirds linearly
  polarised (p 0.02-0.3, χ0 uniform, RM in [−20, 20] rad/m² for half of them), every fourth with
  V/I of 0.005-0.05 either sign, the rest unpolarised; per-correlation weights (per-antenna factors
  0.7-1.3 per hand, cross hands 0.8 of the product), flags on XY only (2 %), YY only (1 %) and whole
  cells (0.5 %), the noise drawn with those weights. Runs Q0 to Q6.
- **H1p** (held out): P1's recipe at dec −45. Its sky and noise seeds are the first 8 and the next 8
  hex digits of `sha256("<commit> <binary sha256> H1p")`, the commit and the binary's sha256 of the
  freeze, both recorded in section 4 before the sky is drawn. Runs Q0 to Q5. No change to GeMClean
  after the freeze without a post-hoc label; the held-out sky is not redrawn.

### Criteria

**A. Single polarisation I unchanged (class A).** Main `0f5ef06` and the frozen G9 binary, both
built here, on D1: G3's C0 (default form), C0 with `-single -wgridder-accuracy 1e-4`, C1, C3, C4
(G3's settings and configurations), and C0 with `-pol I` given explicitly (against main's C0). Every
FITS file of every run has main's SHA-256. One differing file fails A. (The diff of the I path is a
default `Selection` field, a branch that calls the unchanged `stokes_cell`, `CRVAL4` written only for
a non-I polarisation, and `run_joined` delegating with the same arithmetic; G3's set of 15 is not
repeated, to spare the heavy lock.)

**B. Dirty images and PSFs (every run, every channel and MFS, on D1, P1 and H1p).** For every file
WSClean writes, GeMClean writes one of the same name. For dirty images and PSFs the largest
|GeMClean − WSClean| is at most 1e-5 of the largest |WSClean| of the same channel's first-polarisation
dirty image (or PSF peak) and at most 1e-5 of the largest |WSClean| of the file itself.
`WSCIMGWG` within 1e-6 relative for every file (dirty, PSF, model, residual, image, MFS); `CRVAL3`
and `CDELT3` within 1e-9 relative; `CRVAL4` equal. (G3 measured 3e-7, float32 rounding; the probe
6.5e-7 of a file's own peak.)

**C. No I-to-QUV leakage beyond WSClean's (D1 Q1, Q2; the unpolarised sources of P1 and H1p, Q1 to
Q3).** Q, U and V of an unpolarised source are zero in the data; the formation of Stokes parameters
cannot move I into them, so the imager's only route is CLEAN placing Q, U, V components at I peaks
(joined) or at noise. Scored sources: true I SNR ≥ 200 (σ_I as below), unpolarised in the truth. For
each imager, polarisation p ∈ {Q, U, V} and source: the model flux `F_p` within 6 pixels of the true
position and the restored value `R_p` at the true position's nearest pixel (MFS images for Q3). With
σ_p 1.4826 MAD of WSClean's restored p image on the inner field (central 2N/3), GeMClean passes C on
a run when, for every p:

- `median_s |R_p,G| / I_s ≤ median_s |R_p,W| / I_s + 1e-4` and `max_s |R_p,G| ≤ max_s |R_p,W| + 3 σ_p`;
- `Σ_s |F_p,G| ≤ 1.5 Σ_s |F_p,W| + 1 mJy`;
- the rms of GeMClean's restored p image on the inner field is at most 1.05 times WSClean's.

**D. Polarised truth (P1, H1p; Q1, Q2 one channel; Q3, Q6 per output channel).** One estimator for
both imagers: the flux of polarisation p of a component is the sum of its model image within 6
pixels of the true position; the truth is the mean over the output channel's input channels (all 16
for one channel) of the truth's Stokes p at those channels. σ_p: 1.4826 MAD of WSClean's p residual
on the inner field, per output channel for Q3 and Q6. Scored: linear polarisation where
`P_T = (Q_T² + U_T²)^½ ≥ 50 σ_QU` (σ_QU the mean of σ_Q and σ_U), circular where `|V_T| ≥ 50 σ_V`,
I where `I_T ≥ 200 σ_I` (not in Q6). A component passes linear when `|(F_Q − Q_T, F_U − U_T)| / P_T ≤
0.03 + 3/SNR_P`, circular when `|F_V − V_T| / |V_T| ≤ 0.03 + 3/SNR_V`, I when `|F_I / I_T − 1| ≤ 0.02
+ 3/SNR_I`. Per run, per kind (I, linear, circular), over sources and channels: an imager passes when
at least 90 % of the scored pass; **GeMClean passes D** when it passes, its failures are at most
WSClean's plus one, its median relative error at most WSClean's plus 0.005, and (linear) its median
|Δχ| (χ = ½ atan2(F_U, F_Q)) at most WSClean's plus 0.5°.

**E. Cleaned images against WSClean, relative to Q0 (Q1, Q2, Q3, Q6 on every sky; MFS images for
Q3 and Q6).** As G3's criterion D: both models restored with one Gaussian (WSClean's `BMAJ`, `BMIN`,
`BPA` of that file), each imager's own residual added; on the inner field `d_rms` = rms of the
difference / σ_p, `d_max` = largest |difference|. With `X` the I values of Q0 on the same sky, every
polarisation must have `d_rms ≤ max(1.5 X_rms, X_rms + 0.1)` and `d_max ≤ max(1.5 X_max, X_max + 100
µJy)`. Polarisations may add the gap the single-polarisation imagers already have, no more.

**F. Memory.** Peak RSS (GNU `time -v`) of every run of both imagers, reported. No run above
24 × 10⁹ bytes (G2's budget). No tuning, no timing claims.

**Held out.** B, C, D, E and F on H1p after the freeze, reported apart.

**Not scored.** WSClean's `-no-fast-subminor` and `-squared-channel-joining`; XY/YX; circular feeds;
`-link-polarizations`; timing.
