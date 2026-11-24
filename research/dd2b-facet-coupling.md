# DD2b: the cross-facet coupling in WSClean's facet images, and arm I

Issue #15, follow-up to [dd2-facet-imaging.md](dd2-facet-imaging.md), on
branch `dd2b-facets`. Section 1 is a post hoc reading of the source: it was
written after DD2's C2 control (run `-03`) had been read. Section 2 is frozen
2026-11-23 before arm I is read; arm I has not been read in any run.

Status: **measured 2026-11-23: pass.** With `-feather-size 0`, facet imaging with per-facet gains matches WSClean 3.7 to 7.3e-8 (dirty) and 7.5e-8 (flat gain) of the peak, against a limit of 1e-3. All controls pass, and C2 selects normalisation (a).

## 1. Where the coupling comes from (WSClean 3.7 `4f395b28`, read post hoc)

**What C2 showed (DD2 A5).** With a non-unit gain on facet d1 only, the
unit-gain facets also differ from rang. The difference is not a per-facet
scale: the best scale per facet is 0.997-1.0003, with a residual of 6e-3 to
1.5e-2 left after it. Of the pixels that differ by more than 2e-3, the
median distance to rang's facet boundary is 8-13 pixels. The rest lie in two
straight bands, at column x ≈ 1500-1531 and row y ≈ 1180-1212, up to about
300 pixels from any facet boundary. At one such pixel inside facet d0,
WSClean's value is 0.0493 and rang's is 0.0659, a ratio of 0.748. That is
the factor facet d1's gain gives on Stokes I there:
½(4 XX + ¼ YY) / sqrt(8.03).

**Mechanism: the feathered stitching of the facet images.**

- The per-visibility corrections are per facet and are not coupled across
  facets.
  - All facets share one read and one set of weights
    (`gridding/msgriddermanager.cpp` 360-430).
  - Each facet's gridder sums its own correction (`ApplyCorrections<kSum>`,
    403) and applies its own `parm_response` while gridding
    (`GridChunkForFacet`, 512-536, and
    `wgridder/wgriddingmsgridder.cpp` 136-157).
  - The normalisation (`total_weight_`, `visibility_weight_sum_`) is shared
    across facets, as it is in rang.
- The facet images are joined in `WSClean::stitchSingleGroup`
  (`main/wsclean.cpp` 1898-1970) as a weighted mean over facets.
  - The feather width defaults to 1 % of `sqrt(width × height)`, which is
    32 pixels here (`main/settings.h` 282-290; option `-feather-size`).
  - Each facet's polygon mask is convolved with a tophat of that radius
    (`tophat_convolution::Convolve`, line 1954). The facet image is added
    with that weight (`FacetImage::AddWithMask`,
    `schaapcommon/src/facets/facetimage.cc` 129-153), and the sum is divided
    by the summed weight (line 1967).
  - So within about 32 pixels of a boundary, a pixel mixes facet images
    corrected by different facets' gains.
- The tophat convolution is an FFT convolution, so it is circular
  (`math/tophatconvolution.cpp`, then
  `schaapcommon/src/math/convolution.cc` 118-128, `fftwf_plan_dft_r2c_1d`).
  - The mask is padded before convolving only when the facet's convolution
    box differs from its trimmed box (`needs_padding`, 1934-1956).
  - A facet that touches the image edge is not padded on that side. For
    facets d1 (x from 0) and d3 (y from 0), the mask's edge columns and rows
    wrap around to the opposite side of the facet's box.
  - That puts facet d1's image, at a weight of up to about ½, into a band
    32 pixels wide along x ≈ 1500-1531 (the right edge of d1's box). Facet
    d3's image lands in a band along y ≈ 1180-1212 (the top edge of d3's
    box). Both bands lie inside other facets.

So the coupling is a convention (feathering), plus an artefact of that
convention (the circular wrap of the feather mask when a facet touches the
image edge). Neither changes the visibilities or the per-facet gridding,
which C1 confirms: the same pipeline with unit gains matches rang to 7.9e-8.

## 2. Decision (frozen before arm I is read)

**The comparison excludes feathering; rang does not copy it.** Rang's facet
image (DD2 section 1) is the hard stitch: each pixel takes the facet image of
its own polygon. WSClean offers the same through its documented
`-feather-size 0`, which stops the mask convolution and the weighted mean
(`main/wsclean.cpp` 1904 and the `feather_size != 0` branches after it). Copying feathering would mean copying the
wrap artefact, which has no meaning on the sky.

Run `dd2-20261123-04`, with everything else as DD2 amendments A3 and A4:
- WSClean gets `-feather-size 0` on every image call. Predict calls take
  no feathering.
- The prepare and rang outputs are copied from `-02`/`-03`, since they do not
  depend on WSClean's settings.
- Controls: C0, C1 and C2, with DD2's tolerances and C2's candidate rule:
  `-dirty.fits` against `1/sqrt(c)`, and `-image-pb.fits` against `1/c`.
  Arm I is gated only if a single candidate passes C2.
- Arm I: `-dirty.fits` and `-image-pb.fits`. Every pixel at least 3 pixels
  inside its facet and the image edge must satisfy
  `|I_rang − I_wsc| ≤ 1e-3 × max|I_wsc|`. The boundary band is reported.
  `-image.fits` is reported, not gated.

Outcomes:
- **Pass:** C0-C2 and arm I pass. Facet imaging with per-facet gains
  matches WSClean without feathering.
- **Setup:** a control fails. Record it and stop.
- **Fail:** arm I fails with the controls passing. Record it with the
  first differing facet.

## 3. Measured result

Run `D:/rang/outputs/dd2-20261123-04` (WSClean 3.7 with `FEATHER=0`; the
prepare and rang outputs come from `-03`, as frozen). The archive is
[results/dd2-facet-imaging/run-04/compare.json](results/dd2-facet-imaging/run-04/compare.json).

| Case | relative interior difference | boundary band (reported) | gate |
| --- | --- | --- | --- |
| predict C0 / C1 / P | 4.5e-6 / 3.1e-7 / 3.7e-7 | – | pass (1e-4) |
| image C0 | 4.0e-8 | 5.0e-9 | pass (1e-3) |
| image C1 | 7.4e-8 | 4.2e-2 | pass |
| C2 (a), facet d1: dirty / image-pb | **5.3e-8 / 4.0e-8** | – | pass; (b) 0.33 / 0.41 fails |
| **arm I, dirty** | **7.3e-8** | 3.1e-2 | **pass** |
| **arm I, image-pb** | **7.5e-8** | 3.1e-2 | **pass** |
| arm I, `-image.fits` against 1/c (reported) | 1.7e-2 | – | – |

**Outcome: pass.** Without feathering, WSClean's facet image is rang's hard
stitch:
- each facet is imaged from `g_p^* V g_q` (a gain applied on each side),
- `-dirty.fits` carries `1/sqrt(c)`, with
  `c = Σ w ½(|g_px|²|g_qx|² + |g_py|²|g_qy|²) / Σ w`,
- `-image-pb.fits` carries `1/c`.

`-image.fits` is not the flat-gain product.

The boundary band is the pixels within 3 of a facet edge. It differs by up
to 4.2e-2 even with unit gains (C1), so at feather size 0 the two codes
rasterise the polygon edges differently. That band is outside the gate and
is the only remaining difference.

Without `-feather-size 0`, WSClean's default 32-pixel feather mixes
neighbouring facets within about 32 pixels of each boundary, and its
circular wrap (section 1) leaks a facet into bands deep inside other facets.
Rang reproduces neither; DD3 and any user comparison should pass
`-feather-size 0`.

Cost (indicative, `-j 8`): WSClean image 3.2-7.3 s per case, 0.33-0.51 GB; rang 6.6-8.4 s
per facet case, as DD2.

## 4. Earlier rang-vs-WSClean image comparisons: Nyquist pixel and minimal-inversion grid

A read-only audit of `research/`, nothing rerun. A comparison is at risk when
the pixel is coarser than `1/(2 max(|u|,|v|))`, because WSClean drops the
visibilities beyond the unpadded grid (DD2 A3). It is also at risk when
WSClean ran without `-no-min-grid-resolution` (or its older alias
`-no-small-inversion`) and logged "Minimal inversion size" (DD2 A4). Nyquist
pixels come from the notes where they state them; otherwise they are
estimated from 7,698 m at the band's top frequency.

| Note | Compared (reported agreement) | Pixel vs Nyquist | `-no-min-grid-resolution` | Risk |
| --- | --- | --- | --- | --- |
| [e2n-native](e2n-native.md), gate 3c and compact row | dirty L∞ 5.50e-2 (the same with `-no-small-inversion`); 3.3e-3 within 0.7°; compact scatter 2.68 % | 3″ vs about 2.35″ (856-1711 MHz), **under** | as frozen no; diagnostic yes | **high**: the largest gap, never separated from the channel-averaging explanation. Rerun 2026-11-24 ([gate3c-rerun](gate3c-rerun.md) 6.2): 2″ reads 5.46e-2, so not the grid; unaveraged arm D 1.13e-6, so rang's channel averaging; compact scatter 2.81 % |
| [e2-acceptance](e2-acceptance.md), E2-A gate 3c and target compact row | 4096² dirty L∞ 4.97e-3; 2.7e-3 within 0.7° | 3″ vs about 2.35-2.5″, **under** | as frozen no; diagnostic yes | **medium**: dropped long baselines never tested. Rerun 2026-11-23/24 ([gate3c-rerun](gate3c-rerun.md) 6.1): 2″ reads 4.97e-3, so not the grid; unaveraged arm D 9.19e-6, so rang's channel averaging |
| e2-acceptance, E2-B gate 3c | receipts on WSClean's default grid (minimal inversion 1165-1440 logged) | 2″, OK | no | low: cause already given in [e2b-misses](e2b-misses.md) 9.12; the rerun is an owner decision |
| [gemclean-benchmark](gemclean-benchmark.md) (and [gemclean](gemclean.md)) | dirty, `nominres` arm, 2.3e-7; the `minres` arms 9.2e-4 / 2.5e-3 | 1.5″ vs 2.70″, OK | both arms, labelled | low: the headline Q range mixes in the labelled `minres` arms |
| [ts-p1](ts-p1.md), T1 | snapshot against WSClean `-intervals-out`; WSClean dropped 530 of 129,024 samples, fixed to 2.7e-7 (amendment 9.1, 2″) | frozen 4″ vs 2.53″ under; amended OK | yes | none now; `rang-core lightcurve` still defaults to 1024² at 4″ (warns via `outside_grid`) |
| [clean-certified-imaging](clean-certified-imaging.md) | default grid 0.171; `nominres` 4.4e-5 and 2.6e-7 | 8″, OK | both, diagnosed there | none |
| core-c-gridder, [df2b-wgrid](df2b-wgrid.md), [df5o-deconv-oracles](df5o-deconv-oracles.md), [multiscale-df5o-a1](multiscale-df5o-a1.md), [g3](g3-spectral.md), [g6](g6-predict.md), [g7](g7-defaults.md), [g9](g9-stokes.md), [ts-p2](ts-p2.md) | dirty, PSF and predict at 1.7e-7 to 6.1e-7 | OK | yes | none |
| [g4](g4-masks.md), [g5](g5-multiscale.md), [rml-gap](rml-gap.md), [pol-join-squared](pol-join-squared.md), [gemclean-ms-mask](gemclean-ms-mask.md), [stop28-default](stop28-default.md), [wsclean38-rebaseline](wsclean38-rebaseline.md) H arms | quality against truth and WSClean | simulations 1.5″ OK; ESO137 pilot 3″ vs about 3.66″, OK | yes | none |

Skipped (no rang image compared with a WSClean image):
- weights only: core-b-weighting;
- WSClean only, or WSClean against networks: dl0-profile, dl4b-step0, dl4b-step1;
- GeMClean only: dl4c-mask, g2-memory, g8-wheel, gemclean-54, stop-rule-theorem.
  gemclean-54's H4 at 3″ is undersampled, but it is GeMClean only;
- memory, timing or smoke: gemclean-memory2, gemclean-speed, gpu-grid, nash-host;
- cites an existing match: df1-wgridder, df2c-campaign-gridder, o-casa
  (WSClean's default grid, already flagged in clean-certified);
- 3.7 against 3.8: wsclean38 arm P.

## 5. For the coordinator

- DD2's imaging half is done: facet imaging with per-facet gains matches
  WSClean 3.7 at `-feather-size 0` (7.3e-8 and 7.5e-8). Feathering is
  WSClean's convention, and rang does not copy it.
- A possible upstream report (not filed): WSClean 3.7's facet feather mask
  is convolved by FFT without padding when a facet touches the image edge.
  The mask wraps around, and a facet leaks into a 32-pixel band on the far
  side of its box.
- The audit's one high and one medium risk, E2-N and E2-A gate 3c, are both
  on 3″ pixels below Nyquist. Splitting them from the channel-averaging
  explanation needs a Nyquist pixel with `-no-min-grid-resolution`, or a
  rang image with the out-of-grid visibilities removed, as TS-P1 9.1 did.
  That is an owner decision.
- 2026-11-24, post hoc: the owner approved that rerun
  ([gate3c-rerun](gate3c-rerun.md)). On both legs the Nyquist grid changes
  nothing (E2-A 4.97e-3, E2-N 5.46e-2); with `-average-channels 1` the gap
  falls to 9.19e-6 and 1.13e-6. What remains is rang's channel averaging,
  not the grid and not the imager.
