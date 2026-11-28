# Gate 3c: why channel averaging loses flux with radius, and what the unaveraged 1.31 % is

Issue #7, gate 3c on E2-N. Branch `gate3c-averaging`. Proposal frozen on 2026-11-28 before any
code that tests it and before any prediction below was computed. Follows
[gate3c-rerun.md](gate3c-rerun.md) section 7. No frozen verdict is rescored here: gate 3c on E2-N
stays not met as frozen, whatever this note finds.

## 0. What was seen before this note was written

These numbers come from the archived scores (`results/gate3c-compact-avg/g3c-n.json` for arm A,
`g3c-d.json` for arm U, `results/gate3c-rerun/e2n/g3c-n.json` for 6.2). They were computed on
2026-11-28 before this note was written, so they are **seen**, and nothing below is frozen on them.

- **U against WSClean (W2), inner 0.7°, by WSClean SNR.** Scatter 2.72 % at 10-15σ (n 124), 1.60 %
  at 15-25σ, 0.79 % at 25-50σ, 0.34 % at 50-200σ and 0.08 % above 200σ. Scatter × SNR is flat at
  0.26-0.31. The per-source difference U − W2 has a robust spread of 0.25-0.42σ in every SNR bin,
  with its median within 0.05σ of zero, where σ is WSClean's MFS residual MAD and the flux is the
  8-channel sum divided by 8. So the 1.31 % is an additive per-source term, not a flux-scale term.
- **WSClean against itself.** 6.2's GeMClean A and 7.1's GeMClean A are the same image (the logs
  match to every digit), so per source ratio(6.2) / ratio(7.1) = W2 / W1. Matched over 309
  sources, it reads median 0.9996 and scatter **0.66 %**, with 1.44 % at 10-15σ, 0.77 %, 0.37 %,
  0.11 % and 0.04 %. Scatter × SNR is 0.09-0.17.
- **A against WSClean, per output channel.** The medians run 1.0097 to 0.9852. The radial medians
  are as in 7.1.

The GeMClean-versus-WSClean term is therefore about twice WSClean's own run-to-run play,
1.13 % in quadrature above it. Both terms scale as 1/SNR.

## 1. Hypotheses

- **HA (averaging).** Arm A's radial loss is the decorrelation of averaging n native channels
  into one labelled with the group's unweighted mean frequency, as `spectral::average_channels`
  does. For a point source at direction (l, m), the averaged visibility of a row is the true one
  times F = (1/n_u) Σ_k exp(2πi τ (ν_k − ν̄)/c), summed over the group's unflagged channels k. Here
  τ = u l + v m + w (√(1 − l² − m²) − 1) in metres and ν̄ is the group's mean frequency. With full
  groups F = D_n(x) = sin(nπx) / (n sin πx), where x = τ δν / c and δν is the native channel width.
  The fitted peak at the source is therefore Σ w Re F / Σ w, taken over the imaging weights w.
  Nothing else (time smearing, native-channel smearing, the w-term, the gridder) differs between
  A and U.
- **HB (the unaveraged 1.31 %).** The residual scatter is additive disagreement between two
  deconvolutions of the same data. It is not a GeMClean flux, beam or gridding error. Part of it
  is WSClean's own run-to-run play (0.66 %, section 0). What is not claimed: that GeMClean's
  deconvolution equals WSClean's; that the 1.13 % quadrature excess is noise.

## 2. Measurements

### P1. E2-N: the averaging prediction against the archived A/U (measurement seen, prediction not)

- **Data.** E2-N `e2n.ms` on nash (field 3, ASKAPJ1745, cross-correlations): UVW, CHAN_FREQ,
  CHAN_WIDTH, the phase centre, and FLAG as after apply. The FLAG is the saved version
  `flags.rang_selfcal_20261117T072854Z`, which R1 showed equals FLAG after apply. A niced read-only
  extraction on nash (`nice -n 19 ionice -c3`) writes these to an `.npz`. It is copied to
  `D:/rang/outputs/20261128-gate3c-averaging/`, and nothing in E2-N's root is written. No imaging
  or calibration runs on nash.
- **Measured (seen).** Per source in `g3c-d.json`, m = Σ_c A_c / Σ_c U_c, using the 8 per-channel
  GeMClean fits of arm A (`g3c-n.json`) and arm U, matched by pixel. WSClean cancels.
- **Predicted (new).**
  - Imaging weights are WSClean's Briggs 0.5 with MF weighting, from `rang.core_weights.imaging_weights`
    on A's averaged visibilities. The geometry is GeMClean's: padded 6144² grid at 2″, rank filter
    (3, 16), and data weight 1 per unflagged Stokes I native sample, summed in a group. Stokes I is
    flagged where XX or YY is flagged.
  - Per output channel c, p_c = Σ w Re F / Σ w over the rows and groups of that channel. The direction
    (l, m) is the source's pixel on the SIN grid: l = −(x − N/2)·2″, m = (y − N/2)·2″.
  - The prediction is then p = Σ_c p_c U_c / Σ_c U_c.
  - A natural-weight variant is reported, not gated.
- **Tolerance (frozen).** In each of the scorer's five radial bins (0-0.35°, 0.35-0.7°, 0.7-1.0°,
  1.0-1.4°, 1.4-2.5°), |median(m) − median(p)| ≤ 0.005. Reported, not gated: for sources ≥ 50σ, the
  median and robust scatter of m − p.
- **Reading.**
  - **Explained:** every bin meets the tolerance.
  - **Partly explained:** a bin misses, but in the 1.4-2.5° bin the predicted loss 1 − median(p) is
    at least half the measured loss 1 − median(m). Then the partial-flag term, the fixed-beam fit and
    the restoring-beam difference are examined and named, post hoc.
  - **Not explained:** otherwise.

### P2. GeMClean's own predictor against GeMClean's own dirty images (unseen, synthetic)

- **Code under test.** GeMClean computes HA's prediction from its own imaging weights, for full
  groups D_n(x). It averages over 16 directions at azimuths 2πk/16, at radii of 0.25, 0.5, 0.75
  and 1.0 times the image half-width, and at the half-diagonal. It prints the loss 1 − p, and
  writes it to `-report.json` (`averaging`) whenever `-average-channels` > 1.
- **Data.** `examples/gemclean_bench_simulate.py`, noiseless (`--noise-ujy 0`): 64 MeerKAT dishes,
  2 h at 16 s, E2-N's declination, 32 channels of E2-N's native width from 1,284 MHz. The sky is
  1 Jy points at the 16 predictor azimuths and the 5 predictor radii (80 points) on pixel centres,
  for a 6144² × 2″ image.
- **Arms.** GeMClean dirty (`-niter 0`), Briggs 0.5, `-channels-out 8 -join-channels`,
  `-average-channels` 1, 2 and 4.
- **Measure.** At each radius, the mean over the 16 points of (MFS dirty pixel averaged / MFS dirty
  pixel unaveraged) at the true pixel, against GeMClean's printed p at that radius.
- **Tolerance (frozen).** |measured − p| ≤ 2e-3 at every radius, for n = 2 and n = 4. The
  allowance covers sidelobes of the other points, whose own decorrelation differs at other radii.
- **Reading.** Met: the predictor is validated. Missed: the predictor ships only as a labelled
  estimate, and the miss is reported.

### P3. The 1.31 %: each imager against a known truth (unseen, synthetic)

- **Data.** The same simulator with noise:
  - 64 dishes, 2 h at 16 s, E2-N's declination;
  - 64 channels across 856-1,712 MHz, so no averaging and no intra-channel smearing in either
    imager;
  - a flat-spectrum sky of point sources from a power law dN/dS ∝ S^−1.7 between 8σ and 1,000σ of
    the image noise, uniform over the image, drawn so that about 300 fall within 0.7° at ≥ 10σ;
  - 4 Gaussians of FWHM 30-120″ at 20-50σ peak, so that multiscale has work.
  - Seeds: sky 20261281, noise 20261282. The noise is set so that WSClean's MFS residual MAD is
    close to E2-N's (1.7e-5 Jy).
- **Image.** 3072² × 2″ (half-width 0.85°, so it holds every inner-0.7° source). Settings are E2-N's
  image stage otherwise: Briggs 0.5, `-channels-out 8 -join-channels -fit-spectral-pol 2`,
  `-multiscale`, `-auto-mask 5 -auto-threshold 3 -mgain 0.9 -niter 1000000`, `-wgridder-accuracy
  1e-4` and unit weights. WSClean also takes `-no-min-grid-resolution`.
- **Arms.**
  - G: GeMClean, 8 threads.
  - W1 and W2: WSClean 3.7 run twice, identically, at `-j 8`.
  - G-deep and W-deep: the same, with `-auto-threshold 1 -auto-mask 3`.
- **Measure.**
  - Candidates and per-source fluxes come from `e2_score3c_a.py`'s own functions, unchanged: the
    fixed-beam fit per channel, summed over the 8 channels.
  - Truth T is **noise-matched**, so that the noise both imagers share cancels in X/T. Per channel,
    T = S + the fixed-beam fit at the source on GeMClean's dirty image (`-niter 0`, same weighting
    and channels) of a noise-only twin MS. The twin has the same noise seed and no sky; the
    simulator gives the same noise for every sky. T is summed over the 8 channels, for points
    ≥ 10σ that are isolated by the scorer's rule. The Gaussians are excluded from the ratios.
  - Robust scatters of G/T, W1/T, W1/W2 and G/W1 are reported inner 0.7°, by SNR bin.
- **Reading (frozen).** Let s(X) be the inner-0.7° robust scatter.
  - **HB holds, equal imagers:** s(G/T) ≤ 1.2 s(W1/T). The G/W scatter is then two deconvolution
    errors of comparable size, and gate 3c's 1 % is a bound on agreement between two imagers, which
    neither can be held to alone. Outcome "null: additive deconvolution disagreement, not a rang
    defect".
  - **GeMClean worse:** s(G/T) > 1.2 s(W1/T). Then if G-deep brings s(G-deep/T) to ≤ 1.2
    s(W-deep/T), the cause is named as depth. Otherwise the defect is GeMClean's and is not
    attributed further here.
  - **GeMClean better:** s(G/T) < s(W1/T) / 1.2. The excess is WSClean's.
  - **Reported, not gated:** s(G/W1) beside s(W1/W2). If s(G/W1) ≤ 1.5 s(W1/W2) in the
    simulation, while E2-N shows about 2×, the E2-N excess is a feature of the real data that the
    simulation does not reproduce, such as extended emission or the 1,000,000-component cap that
    both E2-N arms hit. It is then not attributed.

## 3. The fix and its decision rule

- **The default is already `average_channels: 1`** (`core_config.py`). E2-N set 2 and E2-A set 8
  explicitly, so the radial loss is a choice made in the configuration, not a default.
- **What is built.**
  - (i) P2's predicted loss is printed and reported.
  - (ii) A warning is printed when the loss at the image half-width is above 1 %.
  - (iii) An opt-in `-average-channels-max-loss <f>` (rang: `image.average_channels_max_loss`,
    default null) picks the largest factor ≤ the requested one whose predicted loss at the
    half-width is ≤ f, using the natural (data) weights before averaging, and prints the choice.
  - Behaviour is unchanged when the option is unset: images byte-identical. Changing the default is
    left to the owner.
- **Not built, and the rule that would change that.** Baseline-dependent averaging (BDA) and an
  averaging-aware forward operator are not built. Their best case is the saving that averaging
  gives at all.
  - On E2-N, measured in 7.1, that saving is wall 56,353 → 50,547 s (1.11×) and peak RSS 72.4 →
    61.3 GB (−15 %). The dirty pair gives 2,273 → 2,132 s.
  - From E2-N's UVW, P1 also reports the fraction of visibilities that n = 2 could average at ≤ 1 %
    loss at the 1.7° half-width. BDA is recommended for a follow-up only if that fraction would save
    ≥ 25 % of visibility memory on E2-N, or on a 4,096-channel set by the same formula.
  - An averaging-aware degridder needs every native channel's phase on the forward and adjoint
    passes, so it keeps the gridding cost and saves only visibility memory. It is not pursued.
- **Byte identity.** Main's GeMClean and the branch's give byte-identical FITS with the option
  unset, on a small simulated case with `-average-channels` 1 and 2. This is checked before merge.

## 4. Cost and host

All runs are on glacier through `heavy_lock.py`, at ≤ 8 slots / 24 GB. WSClean runs in WSL Docker
(`rang-wsclean-native:3.7`), with scratch on WSL's own disk. Wall times and peak RSS go to
`tool-timings.md`. If P3's memory does not fit 24 GB at 3072², the image becomes 2560² × 2″
(half-width 0.71°), labelled.

## 5. Measured result

(Filled in below, per part.)

## A1. Amendment, 2026-11-28 (post hoc: written after P1 was read)

P1 read **partly explained** under the frozen rule: the predicted loss is at least half the measured
loss in the outer bin. In fact the prediction is twice the measured loss: 1.4-2.5° measured 0.947,
predicted 0.887 (section 5). Reading why, before computing anything new: P1 predicts the **dirty**
peak, which weighs every sampled baseline by its imaging weight. The scorer fits the **restored**
image, which is model ⊗ restoring beam + residual. When the deconvolution has fitted the smeared
data, the model's visibilities follow the decorrelated data. The restored peak is then the
decorrelation weighted by the restoring beam's Fourier transform, a Gaussian in uv. That Gaussian
weighs the long baselines, which decorrelate most, far less than Briggs 0.5 does.

- **HA′ (post hoc).** For a restoring beam with image-plane covariance Σ, the restored peak of an
  averaged point source at (l, m) in an output channel of central frequency ν is
  p′ = exp(−½ aᵀ Σ⁻¹ a / (2π)²), with a = π (δν / ν)(l, m). This is the Gaussian average of
  cos(π x) for n = 2. For general n it is the second-order term (n² − 1)/3 × (π δν/ν)² in place of
  π² (δν/ν)², which this note uses for n > 2.
- **P1′ (post hoc, seen measurement).** As P1, but p′ per channel. It uses WSClean's fitted beam for
  that channel from the archived `ws-n-clean.out` (GeMClean fits its own PSF on the same weights).
  The tolerance, bins and reading are P1's. It is labelled post hoc, because the measurement it is
  read against has been seen.
- **P2b (post hoc in design, unseen data).** P2's simulated MS, cleaned noiselessly with
  `-average-channels` 1 and 2. Settings are E2-N's clean settings, but with `-auto-threshold`
  replaced by `-threshold 1e-4` Jy and `-niter 200000`, since a noiseless residual has no
  noise-based threshold.
  - Measure: at each radius, the mean over the 16 points of the ratio of the fixed-beam fluxes
    (`e2_score3c_a.py`'s fit), summed over channels, against GeMClean's printed p′ at that radius.
  - Tolerance: |measured − p′| ≤ 3e-3 for n = 2 at every radius. Also reported: the same against p.
- **Code.** GeMClean also reports p′ (`averaging.restored_loss`), per radius, from its own fitted
  restoring beams after the PSF fit. The guard (`-average-channels-max-loss`) stays on the natural
  dirty-peak loss, which is the larger, conservative figure, because the restoring beam is not
  known before averaging.
