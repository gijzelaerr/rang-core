# DD2b: the cross-facet coupling in WSClean's facet images, and arm I

Issue #15, follow-up to [dd2-facet-imaging.md](dd2-facet-imaging.md), on
branch `dd2b-facets`. Section 1 is a post hoc reading of the source: it was
written after DD2's C2 control (run `-03`) had been read. Section 2 is frozen
2026-11-23 before arm I is read; arm I has not been read in any run.

Status: **proposed**.

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

Not yet measured.
