# Proposal: a compact frequency-transformed beam model for MeerKAT UHF

Status: **proposed, 2026-11-25 (digest [2026-11-25](../digests/2026-11-25.md), rank 1;
issue [#61](https://github.com/gijzelaerr/rang-core/issues/61), v0.5.0).
Nothing built or measured. A storage and accuracy claim for a beam model;
no calibration claim. Beam and pointing calibration (B1-3) stays closed.**

## Hypothesis

A MeerKAT UHF primary-beam model made of one base pattern per antenna (or
array average) under frequency-dependent scaling and shifting, fitted to the
de Villiers (2023) UHF holography, reproduces the holography on held-out
channels to within the holography's own noise (χ²/dof ≤ 1.2), at ≥ 100:1
compression against the 34.9 GB cube, so that #11 (UHF) gets a beam model
without shipping or streaming the cube.

Source: Pashapour-Ahmadabadi et al. 2026, a NIFTy generative beam on the
L-band array-averaged Stokes I holography: χ²/dof ≈ 1, 400:1 compression,
~150 kB per antenna, more than 10× lower mean squared deviation than
Gaussian, Airy, JimBeam, Eidos and EM simulation
([arXiv:2611.26713](https://arxiv.org/abs/2611.26713)). Its code and fitted
model are not stated as public.

## Why now

[uhf-scope.md](../uhf-scope.md) section 2.3: every beam model in
`python/rang/beam_holography.py` and `python/rang/beams.py` is L band only,
marked **BREAK at UHF**; the UHF holography
(`MeerKAT_U_band_primary_beam.npz`, 34.9 GB, CC BY-NC 4.0, DOI
10.48479/wdb0-h061) is the only measured UHF beam. The pipeline itself
applies no primary-beam correction, so this is needed by the simulator,
`rang.simtruth` and any later primary-beam step, not by `rang-core run` today.

## Oracle and data

- **Oracle:** the holography itself (de Villiers 2023, UHF), and the L-band
  holography where the paper's numbers can be reproduced first (the B1-0
  product, `outputs/b1-20261030-05-holography`).
- **Fit set:** every other holography channel; **held-out:** the remaining
  channels plus the band edges (544 MHz and the top channel), read once
  after the fit is frozen.
- **Arms:** (a) the existing `HolographyBeam` spline sampling of the full
  cube (the accuracy ceiling, zero compression); (b) the scaled-and-shifted
  base pattern (Zernike or spline base, fitted by least squares; rang need
  not use NIFTy); (c) a Gaussian with `1.02 λ/13.5 m` (`src/lib.rs:178`, the
  pipeline's current beam); (d) katbeam's `MKAT-AA-UHF-JIM-2020` (JimBeam,
  present in the installed katbeam 0.1, checked 2026-11-25; rang's wrapper is
  hard-coded to the L model, uhf-scope.md 2.3), fitted parameters as
  shipped; (e) the paper's model if its authors release it.

## Tolerance to freeze

- **Success:** on held-out channels, (b) has χ²/dof ≤ 1.2 against the
  holography noise and a main-lobe and first-sidelobe power error ≤ 1 % of
  peak, at ≥ 100:1 compression.
- **Null:** (b) is not better than (d) beyond the first null, or needs
  < 10:1 compression to meet the error bound.
- **Cost bound:** evaluating one antenna's beam on a 4,096² grid at one
  frequency in ≤ 0.1 s on one core.

## Matched comparison

The strongest baselines are arm (a) (full holography, no compression), the
UHF JimBeam (d), the published parametric model at this band, and the paper's
IFT model (e) if released. rang's Eidos coefficients are L band only; whether
an Eidos UHF fit exists was not checked. The novelty rule is not claimed: the method is published; this is a
port for a new band.

## Expected cost

About 2 days: fetch the cube to `D:\rang` (35 GB; the metrics file is
already on nash), fit, one held-out read. No heavy lock beyond the fetch and
fit (`--slots 4 --mem 16`).

## Owner decisions

- Whether #11 needs a UHF beam model before UHF data links arrive.
- CC BY-NC 4.0 on derived beam coefficients: may they ship in a wheel?
- Whether to ask the authors for their code or fitted model.
