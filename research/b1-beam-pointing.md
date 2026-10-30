# Rang B1: beam and pointing on real data (protocol)

Protocol frozen 2026-10-30 on branch `b1-beam-protocol` (from main
`46a319f`), before any B1 code was written. Wave 3 task B1 of
[big-plan.md](big-plan.md), with the literature scan's additions B1-0 and
B1-1 ([literature-2024-2026.md](literature-2024-2026.md) §4.1, §4.2, §5
recommendations 4 and 5) and E2's measures recommendation
([casacure-evaluation.md](casacure-evaluation.md), M2).

Status: **proposed** (this section). Results are appended below the
protocol when measured; nothing above "Measured result" changes after this
commit except through a dated, labelled amendment.

Status (2026-10-30): **B1-0 and B1-1 (i) implemented and measured**, no
amendment. All gates pass: the holography product reproduces SARAO's own
metrics (0.08′, 0.2 %) and interpolates to 1e-3; the SARAO/SKA fit is
reproduced bit for bit on the five-scan fixture. katbeam errs 0.54×, EIDOS
1.8× the signal of a 30″ offset at half power; against the measured beam
the Gaussian fit over-recovers offsets by 1.2–1.5× and returns up to 0.6′ at
zero offset (about half of it the beam's squint). Details in "Measured
result".

Erratum (2026-10-30, after the measurement; citations only): in B1-1 (ii)
"Sridharan et al. 2025" should read Sridharan et al., URSI GASS 2023
(arXiv:2504.14449), as the literature scan cites it. "EVLA memo 84"
(Bhatnagar, Cornwell and Golap 2004) was checked against the papers that
cite it (EVLA Memo 100; arXiv:1501.05304), not read.

## Why

The flagging experiment is closed null (L1, L2, L1-M, C1; verdict L4). The
question that started the project returns
([meerkat-scope.md](meerkat-scope.md)): can MeerKAT science observations
constrain small physical pointing and primary-beam corrections, selected by
their distinguishability from uncertain sky emission, while limiting
distortion of faint emission and source spectra? Everything so far on that
question is toy or audit work: the Rust pointing solver (`src/`), the JAX
direct-Fourier reference path (`python/rangtoy/pointing.py`), the
observability, gain-observability and katbeam audits
(`examples/observability.py`, `gain_observability.py`,
`katbeam_observability.py`), beam-model selection
([beam-model-selection.md](beam-model-selection.md)) and the toy result that
adaptive protection adds nothing over joint fitting
([first-results.md](first-results.md)). The core now reads the public data,
predicts components, solves QuartiCal-exact gains and images, so the
question can be put to real data. Two things must be fixed first, and this
protocol fixes them before any rang method is run:

- **B1-0, the beam.** Every pointing or beam statement is relative to a
  reference beam E_p,0. The beams rang uses today are katbeam (PyPI 0.1,
  2020; a cosine taper with measured squint and width, co-polar only) and
  EIDOS (1.1.2, 2024; Zernike/DCT fits to older holography). The DDFacet
  study ([ddfacet-feasibility.md](ddfacet-feasibility.md)) measured that a
  facet-constant beam errs by 13–50× the signal of a 30″ pointing offset,
  so the reference beam must be good to well below that signal. SARAO's
  2023 holography release is the measured reference.
- **B1-1, the baselines.** The novelty rule (AGENTS.md) asks rang to beat
  the relevant state of the art at matched cost. For pointing that is the
  Gaussian fit to reference-pointing scans that SARAO runs on MeerKAT and
  the SKA SDP pipeline re-implements, and physical pointing self-calibration
  on science data (Bhatnagar and Cornwell 2017; routine in the ngVLA plan).

B1-2 (first rang experiment, an identifiability survey) and B1-3 (pointing
self-calibration and the rang method against both baselines) are specified
here so the metrics are fixed in advance; they run in later worktree tasks.

## Pre-protocol probe (labelled scratch)

Metadata, provenance and upstream source were read before this commit; no
beam comparison and no fit was computed. Runs (all WSL host, this branch):

| Run | Dir under `outputs/` | What | Wall | Peak RSS |
| --- | --- | --- | ---: | ---: |
| zip central-directory probe of `MeerKAT_L_band_primary_beam.npz` by HTTP range | (stdout) | member names, offsets, npy headers | ~5 s | – |
| small arrays + metrics file | `b1-20261030-01` | `pols`, `antnames`, `freq_MHz`, `margin_deg` by range; the 28 MB metrics npz whole | 9.1 s | 83 MB |
| upstream sources, shallow clones | `b1-20261030-02-ska-pointing-src` | ska-sdp-wflow-pointing-offset `5ede554`, ska-sdp-func-python `4056001`, ska-sdp-datamodels `74d4f22`, scikits.fitting 0.7.2 wheel | – | – |
| fixture extract | `b1-20261030-03-fixture` | `outer_scans.zip` (SHA256 `d4dae56f…144f`, as recorded) | ~3 s | – |
| ESO137 metadata probe | `b1-20261030-04-eso137-probe` | S3 listings and `.zarray` of every MAIN group; PHASE_DIR and CHAN_FREQ decoded with the core's blosc | 74.3 s + 2.2 s | 26 MB / 45 MB |

Facts found (the protocol below rests on them):

1. **The holography release** (de Villiers 2023, AJ 165, 78,
   arXiv:2301.06752; data DOI 10.48479/wdb0-h061, issued January 2023,
   files last modified 2023-04-10) holds per band one
   `MeerKAT_<band>_band_primary_beam.npz` (L band: 34,896,620,743 bytes) and
   one `..._metrics.npz` (L band: 28,235,140 bytes, SHA256
   `8fc965f7…a42f`). **Licence CC BY-NC 4.0** (the landing page), not the
   CC BY 4.0 of the ESO137 data; it is SARAO data, used here
   non-commercially, cited, never committed. The beams are for 60°
   elevation and 15 °C, averaged January 2020 to January 2022, and are
   reconstructed from aperture-plane holography (the paper).
2. **The npz is stored, not deflated.** `beam.npy` is complex64, C order,
   shape (4, 65, 1024, 128, 128) = (pol HH, HV, VH, VV; antennas m000–m063
   then `array_average`; channel; y; x), data at byte 186. One (pol,
   antenna, channel) map is a contiguous 131,072-byte span, so any subset
   can be read by HTTP range without the 35 GB download. Server ETag is a
   multipart tag, not a content hash; the whole-file SHA256 is not
   computed.
3. **Grid.** `margin_deg` runs −4° to +3.9375° in 0.0625° (3.75′) steps on
   both axes; index 64 is 0°. `freq_MHz` is 856 to 1711.164 MHz in
   0.8359375 MHz steps (1024 channels).
4. **Orientation.** `beam_orientation_diagram.pdf` (182,647 bytes; the
   landing page says 180 B) shows the supplied HV pattern with "downward
   side of beam" at the top and says to "flip patterns vertically" to
   obtain the upward side; left and right are the beam's left and right as
   seen from behind the dish. The paper puts y in the elevation plane of
   symmetry and x in cross-elevation. The frame is the antenna (az-el)
   frame, so a parallactic rotation is needed to reach the sky.
5. **The metrics file** has 64 per-(antenna, channel) arrays (65, 1024):
   centroids `Hx0, Hy0, Vx0, Vy0, Ix0, Iy0`, widths `*major, *minor,
   *angle`, sidelobe levels, cross-pol maxima, error-beam statistics
   (`Imaxerrbeam`, `Istderrbeam` ≈ 1e-3), aperture efficiencies. Units are
   not documented: `Hmajor` ≈ 52 at 856 MHz is not a power FWHM in
   arcminutes (that is about 100′ there). B1-0 gate G0a settles it.
6. **Controls.** katbeam `MKAT-AA-L-JIM-2020` tabulates squint and FWHM
   for H and V at 900–1650 MHz in 50 MHz steps (squint in arcminutes in
   the source table). EIDOS 1.1.2 (GPL-3.0, Asad et al. 2021,
   arXiv:1904.07155) ships `meerkat_beam_coeffs_ah_zp_dct.npy`, 870–1670
   MHz in 0.1 MHz steps, reconstructed on a 10° grid and selected by
   nearest channel. The common band of all three is **900–1650 MHz**.
7. **The SKA SDP pointing-offset pipeline**
   (ska-sdp-wflow-pointing-offset, BSD-3-Clause, commit `5ede554`,
   2026-08-13) follows "those used by SARAO for the MeerKAT array"
   (`beam_fitting.py`). Its end-to-end test runs `compute
   --use_source_offset_column --thresh_width=1.15 --num_chunks=16` on
   `outer_scans/` and checks all 12 output columns against
   `outer_scans/reference_offsets.txt` to `decimal=6`. The fixture also
   holds `reformatted_offsets.txt`, with different numbers and SKA-style
   antenna names, whose settings are not documented.
8. **The fixture is a five-point reference-pointing observation**, not a
   single scan. Mean SOURCE_OFFSET per scan (all four antennas move
   together): scan 1 (0, −1°), scan 4 (0, +1°), scan 5 (−1°, 0), scan 8
   (+1°, 0), scan 9 (0, 0); scans 1–8 have 2 dumps, scan 9 has 14 (8 s
   dumps); field J1939−6342 (PKS 1934−638). `SolveForOffsets` refuses
   fewer than five pointings, so the baseline cannot be run on scan 9
   alone: it is the five-scan fit, with scan 9 as the on-source point.
   **This is a stated deviation from the B1 brief's "scan 9" wording.**
9. **No public store holds pointing-scan structure.** POINTING has 0 rows
   in ESO137 `ms1_target`, `ms2_target`, `ms1_target_subset` and in both
   LUNO stores.
10. **ESO137 target data** (RATT bucket `ESO137/`, registry licence CC BY
    4.0, cite Ramatsoku et al. 2020): `ms1_target.zarr`, 7 scans (SCAN 2–14
    even) × 850,950 rows (61 antennas, 450 dumps of 8 s per scan), 4,096
    channels 856–1711.79 MHz, DATA 734 GB, WEIGHT_SPECTRUM 292 GB,
    MODEL_DATA 3.7 GB, CORRECTED_DATA 28 GB, FLAG 1.8 GB (compressed; 50,000
    rows × 128 channels × 4 per chunk); `ms2_target.zarr`, 58 antennas, no
    WEIGHT_SPECTRUM, DATA 661 GB; `ms1_target_subset.zarr`, scan 2 only,
    500 channels 1347.11–1451.40 MHz (0.209 MHz), DATA 12.6 GB,
    WEIGHT_SPECTRUM 5.0 GB, FLAG 19 MB, MODEL_DATA 61 MB. PHASE_DIR
    RA 243.79583°, Dec −60.90583° (16h15m11s, −60°54′21″; ESO 137-006).
    CORRECTED_DATA exists, so the FLAG column is a processing product
    (CARACal, per the publisher's documentation), not raw observatory
    flags; whether the target's XY/YX weights are zero as on the primary is
    not yet measured.

## Questions

- **Q0 (B1-0).** Is the holography product read, oriented, interpolated
  and normalised correctly, and how far are katbeam and EIDOS from it in
  the main lobe and first sidelobe across 900–1650 MHz, measured in units
  of the signal of a 30″ pointing offset?
- **Q1 (B1-1 i).** Does a faithful port of the SARAO/SKA Gaussian
  pointing-offset fit reproduce the published reference on the fixture,
  what does it estimate, with what uncertainty, and how biased is it when
  the beam is the measured one rather than a Gaussian?
- **Q2 (B1-2, later task).** Which pointing and beam directions can the
  LUNO calibrator scans and the ESO137 target constrain at all, once gains
  and sky are solved jointly?
- **Q3 (B1-3, later task).** At matched cost, does rang's
  distinguishability-selected correction beat both baselines on the
  metrics below?

## B1-0: the beam product (frozen)

**Source.** `beam.npy` of `MeerKAT_L_band_primary_beam.npz`, DOI
10.48479/wdb0-h061, read by HTTP range from
`https://archive-gw-1.kat.ac.za/public/repository/10.48479/wdb0-h061/data/`.
Provenance per fetched block: URL, byte range, SHA256 of the block, HTTP
size, Last-Modified and ETag; SHA256 of every derived file. Fetched into
`outputs/b1-20261030-05-holography/`; never committed.

**Frequency sampling.** The product holds:

- the **array average** (antenna index 64) at all 1,024 native channels
  (0.836 MHz), the interpolation reference;
- **every antenna** (64) at channels 0, 11, 22, …, 1012 and 1023 (95
  channels; 9.196 MHz spacing, 10.4 MHz for the last step), which meets
  the "10 MHz or finer" guidance of the SARAO knowledge base everywhere
  except that last edge step (1703–1711 MHz, outside the comparison band).

**Jones form.** Element order HH, HV, VH, VV as the file's `pols`, read as
the 2×2 voltage Jones matrix E = [[HH, HV], [VH, VV]], where HV is "the
horizontal dipole response to a vertically polarised wavefront" (the
diagram). MeerKAT's H and V feeds are the MS's X and Y. The **Stokes I
power beam** for an unpolarised source is I_b = ½ Σ_ij |E_ij|², which the
predictor uses per component as E_p I E_qᴴ / 2 summed for the parallel
hands.

**Coordinates.** Beam coordinates in degrees: x = `margin_deg[col]`,
y = s · `margin_deg[row]`, with s ∈ {+1, −1} the vertical flip of the
diagram. s is decided by gate G0a below and recorded; the frame is
antenna az-el (x cross-elevation, y elevation).

**Interpolation rule.** Spatial: cubic spline (`scipy.ndimage.map_coordinates`,
order 3, spline prefilter, mode `nearest`) on the real and imaginary
parts of each Jones element on the native 3.75′ grid; evaluation outside
±3.9° is refused. Frequency: linear in each complex Jones element between
the two nearest product channels; no extrapolation outside 856–1711.16
MHz. Derivatives (B1-2) are the analytic derivatives of the spline.

**Normalisation.** Every model (holography, katbeam, EIDOS) is normalised
per frequency so that its Stokes I power beam is 1 at the beam-coordinate
origin (the pointing centre), the response that gain calibration absorbs.
The co-polar voltage maps are normalised by the same factor (√ for
voltage).

**Interface.** `python/rangtoy/beam_holography.py` exposes one sampler
for the predictor's per-component beam: `jones(antenna, x_deg, y_deg,
freq_hz) → complex (..., 2, 2)` and `power_i(...)`, with katbeam and EIDOS
behind the same interface as controls (katbeam: diagonal Jones from
`HH`, `VV`; EIDOS: its four voltage maps, spline-interpolated on its own
grid, nearest channel as EIDOS does). Rotation from sky (l, m) to beam
(x, y) by the parallactic angle is the caller's (B1-2), with the measures
convention below.

### Gates (frozen; failure stops the product from being used)

- **G0a reader and orientation.** For the array average and antennas
  m000–m003 at the 95 product channels within 900–1650 MHz, fit a 2-D
  elliptical Gaussian to the co-polar power |HH|², |VV|² and to I_b above
  half power, and compare centroid and widths with the metrics file
  (`Hx0, Hy0, Vx0, Vy0, Ix0, Iy0`, `*major`, `*minor`). Pass if one unit
  and one width definition (to be identified and recorded: arcmin or
  degrees; FWHM, HWHM or σ) reproduce the metrics with median |Δ centroid|
  ≤ 0.2′ and median |Δ width| / width ≤ 1 %. The sign s is the one that
  matches the metrics' y-centroid sign, unless the metrics are found to be
  in array coordinates, in which case s = −1 (the diagram) and the
  katbeam V-squint sign comparison is recorded as a finding. Channel 0 is
  excluded from the medians (the metrics jump there).
- **G0b frequency interpolation.** Predict each held-out native channel of
  the array average in 900–1650 MHz from the two neighbouring product
  channels. Pass if, for I_b inside the first null, the median over
  channels of max |ΔI_b| ≤ 2e-3 and the 95th percentile ≤ 5e-3 (the
  product's own `Imaxerrbeam` is a few 1e-3). If it fails, the product
  sampling becomes native for the channels used.
- **G0c spatial interpolation.** Rebuild the spline from the even-indexed
  pixels only and evaluate at the odd ones (a 2× coarser grid than the
  product, so a conservative test). Pass if max |ΔI_b| inside the half-power
  contour ≤ 2e-3 at every comparison-band product channel.

### Comparison with katbeam and EIDOS (measured, not gated)

At every product channel in 900–1650 MHz, array average and per antenna,
in the antenna frame (no rotation needed: all three are antenna-frame
models):

- **Regions** from the holography I_b's azimuthal profile at that
  frequency: core r ≤ r_HP (half power), main lobe r ≤ r_N1 (first
  minimum), first sidelobe r_N1 < r ≤ r_N2 (second minimum).
- **Main lobe.** Power FWHM along x and y, centroid (squint) of each
  co-polar beam; max and RMS of |ΔI_b| (fraction of on-axis) in core and
  main lobe.
- **First sidelobe.** Peak level of the azimuthally averaged I_b, its
  radius, max and RMS |ΔI_b| in the annulus.
- **In pointing units.** The signal of a 30″ offset at a point is
  |∇I_b| · 30″; the ratio max|ΔI_b| / (|∇I_b| 30″) over the half-power
  ring is reported (the DDFacet study's 13–50× is the same ratio for a
  facet-constant beam).
- **At the data's offsets.** LUNO calibrators: the pointing centre and the
  components of CARACal's 196-component PKS 1934−638 model
  (`rangtoy.lsm`); LUNO target: the Moon at 44′, 98′ and 149′ (azimuthal
  mean and range at those radii, since the Moon's position angle in the
  beam frame needs the parallactic angle of B1-2); ESO137: no field model
  yet, so the annuli above stand for the field (core, half power, first
  null, first-sidelobe peak). A field model is a B1-2 item.
- **Antenna spread.** RMS over the 64 antennas of I_b(antenna) − I_b(array
  average) in the main lobe against frequency, beside the paper's 0.3 %
  (lower band) and 0.9 % (upper band) mean deviations.

## B1-1: the baselines (frozen)

### (i) Gaussian pointing-offset fit on reference-pointing scans

**Method, as published.** SARAO fits a Gaussian beam to the amplitude of
each antenna's response at a small set of commanded offsets around a
calibrator (katsdpcal/katpoint practice; `scikits.fitting.GaussianFit`);
the SKA SDP pipeline re-implements it. Rang ports the pipeline's default
path at commit `5ede554` (the one its end-to-end test exercises), with the
BSD-3-Clause notices of ska-sdp-wflow-pointing-offset, ska-sdp-func-python,
ska-sdp-datamodels and scikits.fitting kept, as `core/src/predict.rs` does
for africanus:

1. Read each scan's DATA, FLAG and the per-row **WEIGHT** (broadcast over
   channels; WEIGHT_SPECTRUM is not used) for all rows, autocorrelations
   included; flagged samples get weight 0 through (1 − flag).
2. Split the 4,096 channels into 16 chunks of 256 and drop the first and
   last (14 chunks; chunk frequency = mean of its channels).
3. Per chunk and **per integration**, solve un-normalised parallel-hand G
   gains against a unit point model at the phase centre: ska-sdp-func-python
   `solve_gaintable(phase_only=False, niter=200, tol=1e-6, crosspol=False,
   normalise_gains=None, solver="gain_substitution", jones_type="G",
   refant=0)`, i.e. Hamaker matrix gain substitution with the cross hands
   zeroed, the diagonal (autocorrelations) excluded, xwt normalised by its
   maximum, damping 0.5, phase referenced to antenna 0, gain weight
   Σ_j xwt_ij |g_j|².
4. Amplitude per (antenna, chunk, scan): weighted mean of |g_XX|, |g_YY|
   over integrations and both hands with the gain weights; its weighted
   **standard deviation** (unbiased, not the standard error) is the σ_y of
   the fit.
5. Position per (antenna, scan): the time mean of SOURCE_OFFSET
   (cross-elevation, elevation) after zero-order-hold interpolation to the
   visibility times; POINTING rows are antenna-major (the convention
   barrier of [measurement-set-inspection.md](measurement-set-inspection.md)).
6. Fit per (antenna, chunk) a 2-D Gaussian with diagonal covariance and
   free centre (2), height and widths (2) to the five points by
   Levenberg–Marquardt (`scipy.optimize.leastsq` with the analytic
   Jacobian, as scikits.fitting), starting at centre 0, height 1 and
   voltage FWHM √2 · k λ/D with k = (0.976, 1.098) for (x, y) and D = 13.5 m.
   The parameter covariance is (Jᵀ W J)⁻¹ with W = 1/σ_y², **not rescaled
   by the residual** (five points, five parameters: zero degrees of
   freedom). Valid if the centre is finite, the height positive and 0.9 <
   width/expected < 1.15 on both axes.
7. Combine the valid chunks per antenna by inverse-variance weighted mean,
   with the weighted standard error; report in radians.

**Gate G1a (reproduction).** All 12 columns of `reference_offsets.txt`
reproduced to `decimal=6` (|Δ| < 1.5e-6), as the upstream test asserts.
The Gaussian stage alone is also checked once against scikits.fitting
0.7.2 in a scratch environment (oracle, not a dependency).
`reformatted_offsets.txt` is reported as unexplained unless its settings
are identified (sep-pol, TARGET-column offsets, `fit_to_vis`).

**What it measures, and its uncertainty.** There is no independent truth
on the fixture: the reference is the pipeline's own estimate. Reported
per antenna: cross-elevation and elevation offsets in arcmin with (a) the
published formal σ (6–7 above), (b) the across-chunk scatter (weighted
standard deviation of the 14 chunk centres), (c) the H-only and V-only
fits (the pipeline's `--fit_to_sep_pol` path) as a consistency check. The
documented accuracy context: the SKA pipeline documentation gives no
accuracy figure; de Villiers (2023) removes a pointing error of about 0.6′
before combining holography measurements; the SARAO knowledge base still
calls reference pointing "under development" (literature scan §4.1).

**Gate G1b (the baseline's model bias, simulated truth).** With the frozen
B1-0 beam (array average I_b and the four fixture antennas' co-polar
beams), simulate the fixture's five pointings with injected per-antenna
offsets of 0, ±0.5′, ±1′ and ±2′ along each axis, noise-free and with the
fixture's σ_y, at the 14 chunk frequencies; run step 6–7 unchanged.
Reported: recovered minus injected offset (the bias of a Gaussian model
applied to the measured beam with ±1° throws, which sit near the voltage
half-power point), and the coverage of the formal σ over 200 noise
seeds (seeds 1–200). This is the "recovered offset against truth" metric;
on the real fixture only agreement within the combined σ can be scored.

### (ii) Physical pointing self-calibration

**Method.** Per-antenna pointing offsets δ_p(t) (two components per
solution interval) solved from science data with the beam model **fixed**
(the frozen B1-0 product shifted by δ_p, E_p(u) = E_p,0(u − δ_p)) and the
sky model fixed, alternating with the direction-independent gain solve
(Bhatnagar and Cornwell 2017, AJ 154, 197, arXiv:1709.08681, the Pointing
SelfCal algorithm; Bhatnagar, Cornwell and Golap 2004, EVLA memo 84; the
ngVLA calibration plan makes it routine, Sridharan et al. 2025,
arXiv:2504.14449). Rang's existing smooth solver and JAX DFT path
(`pointing.py`) are the implementation base; the antenna-based Jacobian is
the predictor's beam derivative from B1-0. This is the method rang must
beat at matched cost. It is specified here and run in B1-3.

### Metrics for Q3 (frozen now, measured in B1-3)

1. **Recovered offset against truth**: on simulations from the frozen
   beam (G1b's design, plus a science-field version with the B1-2 sky), the
   bias and RMS error of recovered δ_p in arcmin; on the fixture,
   agreement with the baseline within combined σ.
2. **Held-out visibility error**: L1's split machinery (seed 7, 80/10/10
   train/validation/test cells), test-cell weighted MSE after the full
   solve, against gains-only.
3. **Faint-source flux and spectral-index distortion**: a simulated field
   predicted with the frozen beam (per antenna, per component), 20 faint
   sources at 0.1–1 mJy placed between the half-power and first-null
   radii and 20 inside the core, injected pointing errors drawn with σ =
   0.6′ per antenna per hour; recovered flux ratio and spectral-index error
   per source after each method, against the truth and against
   no-correction.
4. **Cost**: wall, peak RSS and data volume read per method, same host and
   threads (`OPENBLAS_NUM_THREADS=1`, `RAYON_NUM_THREADS=4`); "matched"
   means within a factor 1.5 in wall for the same data.

Rang wins only if it improves 2 or 3 over both baselines with 1 no worse,
at matched cost (the novelty rule); otherwise the result is recorded as
null.

## B1-2: the first rang experiment, identifiability (frozen design)

**What.** The identifiability survey (the rank machinery of the solved
LUNO surveys and `flagging_influence.anchored_response`) extended from
gain and sky directions to beam derivative directions: per antenna and
solution interval ∂V/∂δ_x, ∂V/∂δ_y (pointing), and array-common
log-width, ellipticity and squint, each computed with the frozen B1-0
beam per component. For each direction, after profiling the nuisances
(per-antenna 2×2 diagonal gains per solution interval, the sky component
fluxes): the Fisher σ, the fraction of its signature outside the nuisance
span, and the anchored response.

**Data.** LUNO calibrators (PKS 1934−638 chunk 0 as in L1 and C1, with the
CARACal field model; PKS 1830−211 as in L2), and the ESO137 target pilot
below.

**Decision rule.** A direction is *constrainable* on a data set if its
profiled Fisher σ ≤ 0.3′ for pointing (half the 0.6′ that holography
removes) or ≤ 0.5 % for width and ellipticity, **and** at least 1 % of its
signature lies outside the nuisance span. B1-3 fits only constrainable
directions; if none is constrainable on any set, B1 closes null at B1-2.

**Expected outcome, stated honestly.** On the calibrators the flux sits at
the pointing centre, where ∂I_b/∂δ is zero apart from squint, so pointing
enters at second order and is absorbed by gain amplitude: expected **not
constrainable** per antenna, at best array-common width. On the ESO137
target, sources across the main lobe give first-order signatures:
expected constrainable for array-common pointing and width at the
arcminute level, per-antenna pointing per hour only for the brightest
off-axis sources, if at all. A null here is a result.

**Data decision (ESO137).** ESO137 is the B1 target field: CC BY 4.0
(registry; cite Ramatsoku et al. 2020), 61 antennas, a science field with
sources across the beam. The first fetch is bounded: from
`ms1_target_subset.zarr` (scan 2, 1347–1451 MHz), row chunk 0 (50,000
rows ≈ 26 dumps, 3.5 min) of DATA, FLAG, WEIGHT_SPECTRUM and MODEL_DATA
(each ~1/17 of the subset totals: about 0.75 GB DATA, 0.3 GB weights),
plus the subtables. The full `ms1_target` (734 GB DATA) is not fetched.
B1-2 first measures the target's XY/YX weights and flag occupancy, and
builds a field model (from the stored MODEL_DATA or an image of the pilot)
before the survey. The FLAG column is treated as an authoritative lower
bound and as a processing product, not native observatory flags.

## Measures convention (frozen)

The holography beam is in the antenna az-el frame. Sky (l, m) maps to beam
(x, y) by the parallactic angle q (plus the feed's RECEPTOR_ANGLE, read
from the MS FEED table and recorded). q is the **geodetic** parallactic
angle with **astropy** as the reference (E2: casacore `AZELGEO`, casacure
and astropy agree to ≤ 1.3″; casacore `AZEL` uses the geocentric horizon).
For the three LUNO fields the `AZEL`/`AZELGEO` difference in q is
0.009–0.29°; the ~2° of QuartiCal PR #445 is for a field 3° from the
zenith. QuartiCal or CARACal products made with python-casacore `AZEL`
will differ from rang's by those amounts; they are not "corrected". B1-1(i)
needs no measures (it reads SOURCE_OFFSET).

## Acceptance criteria (frozen)

- B1-0 is usable iff G0a, G0b and G0c pass; the comparison numbers are
  reported either way.
- B1-1(i) is a valid baseline iff G1a passes; G1b is reported either way.
- Every tool run is timed (date, tool, input, wall, RSS, notes); failures
  are kept, frozen and labelled post hoc.
- `bash tools/check-all.sh` passes before the final commit.

## Expected outcome, stated before running

- G0a: the metrics are probably in arcminutes with widths as half-power
  half-widths (52′ ≈ half of ~104′ at 856 MHz); the flip s is genuinely
  uncertain.
- katbeam reproduces the main lobe to about 1 % (its fit target) but not
  the sidelobes (a cosine taper); EIDOS is closer in the sidelobes. In
  pointing units both are expected to err by more than a 30″ offset's
  signal at the half-power ring, which is the reason for B1-0.
- G1a: should pass if the port is faithful; failure would most likely
  come from the per-integration gain solve or the weight path.
- G1b: a Gaussian fitted with ±1° throws to the measured beam is expected
  to be biased by a fraction of an arcminute, comparable to the 0.6′
  pointing error itself.

## Code to write after this commit (own files only)

- `python/rangtoy/beam_holography.py`: range reader for the holography
  npz, the B1-0 product, the sampler interface, katbeam and EIDOS
  controls, the gate and comparison functions.
- `examples/b1_beam_product.py`: fetch (or reuse) the product, run
  G0a–G0c and the comparison, write `research/results/b1-beam-product.json`.
- `examples/b1_baselines.py`: the port of the SARAO/SKA fit (steps 1–7),
  G1a against `reference_offsets.txt`, the sep-pol check, G1b.
- `tests/test_beam_holography.py`, `tests/test_b1_baselines.py`: offline
  (a synthetic stored npz for the range reader and offsets; the fixture
  test skips without `outputs/ska-pointing/outer_scans.zip`).

## Measured result (2026-10-30)

Status: **B1-0 and B1-1 (i) implemented and measured**; every gate passes
(G0a, G0b, G0c, G1a); G1b measured. B1-1 (ii), B1-2 and B1-3 are not run
(next tasks below). No amendment to the frozen protocol; one rule was
applied with a recorded reading (G0a's flip clause, below).

Runs (all on the WSL host, this branch, `OPENBLAS_NUM_THREADS=1`,
`RAYON_NUM_THREADS=4`):

| Dir under `outputs/` | What |
| --- | --- |
| `b1-20261030-05-holography` | the B1-0 product: array average at 1,024 native channels and all 64 antennas at the 95 product channels, 3.72 GB, by HTTP range; `manifest.json` with SHA256 per (pol, antenna) block; fetched by the scratch script `fetch_holography.py` kept in the directory (the layout of `beam_holography.fetch_product`, which was written after and not re-run), `small.npz` copied from `b1-20261030-01` |
| `b1-20261030-06-baseline` | G1a runs (two failures, then the pass) |
| `b1-20261030-07-oracle` | scikits.fitting 0.7.2 oracle venv and log |
| `b1-20261030-08-product-smoke` | B1-0 smoke run (every 20th channel) |
| `b1-20261030-09-product` | B1-0 full run; full archive `b1-beam-product-full.json` |
| `b1-20261030-10-baseline-g1b` | B1-1 (i) with G1b, 200 seeds; `b1-baselines.json` |
| `b1-20261030-11-posthoc` | post-hoc EIDOS orientation check (labelled) |

Product files: `array_average_native.npy` (536,871,040 B, SHA256
`7350498b…7e917`), `antennas_sampled.npy` (3,187,671,168 B, SHA256
`586df11d…19191`). Committed archive:
[results/b1-beam-product.json](results/b1-beam-product.json) (rounded to six
significant digits; the full one stays in `outputs/`).

### B1-0 gates

- **G0a pass.** 1,230 main-lobe fits (array average and m000–m003; H, V and
  I; 82 product channels in 900–1650 MHz). The metrics file's widths are
  **power half-widths at half maximum in arcminutes** (median |Δ| 0.21 %;
  the other candidate definitions miss by 15–100 %) and its centroids are in
  arcminutes: median centroid error **0.081′** with y = +`margin_deg[row]`,
  0.67′ with the opposite sign. The y-centroid sign agrees in every fit
  where |y0| > 0.2′. So **s = +1**. The frozen clause "unless the metrics are
  found to be in array coordinates" could not be tested independently; two
  facts support s = +1: katbeam's tabulated V elevation squint has the
  holography's sign at all 64 product channels where both exceed 0.2′, and
  the diagram reads consistently with s = +1 if "as supplied" means the
  usual image display with row 0 at the top (then the top row is the
  downward side, as drawn). The centre pixel of the co-polar maps is 1.0000
  (median |HH| 0.99999976, |VV| 0.99992), cross-polar 2e-5.
- **G0b pass.** Over 815 held-out native channels, linear interpolation
  from the 9.2 MHz product channels errs in I_b inside the first null by a
  median of max |ΔI| **1.02e-3**, 95th percentile 3.62e-3, worst 5.67e-3
  (gates 2e-3 and 5e-3).
- **G0c pass.** A spline built from every second pixel reproduces the
  skipped pixels inside half power to **6.1e-5** at worst (82 channels),
  30 times inside the gate; the native 3.75′ grid is ample for the spline
  and its derivatives.

### B1-0 comparison (array average, 82 channels 900–1650 MHz)

Medians over channels (range in brackets); |ΔI| in units of the on-axis
Stokes I power. A 30″ pointing offset changes I_b by **1.08 %** (median)
on the half-power ring.

| Quantity | katbeam | EIDOS |
| --- | --- | --- |
| I FWHM major / holography | 1.0001 (0.996–1.004) | 0.997 (0.993–1.004) |
| I FWHM minor / holography | 1.0010 | 1.0077 |
| max \|ΔI\|, core (r ≤ r_HP) | 0.60 % (max 1.27 %) | 2.06 % (max 3.72 %) |
| max \|ΔI\|, main lobe (r ≤ first null) | 0.83 % | 2.09 % |
| RMS \|ΔI\|, main lobe | 0.31 % | 0.64 % |
| max \|ΔI\|, first-sidelobe annulus | 0.37 % | 0.16 % |
| RMS \|ΔI\|, first-sidelobe annulus | 0.13 % | 0.051 % |
| first-sidelobe level (holography 0.56 %, 0.30–0.76 %) | 0.50 %, constant | 0.57 % |
| max \|ΔI\| on the HP ring / 30″ signal | **0.54** (0.16–1.33) | **1.82** (0.45–3.62) |
| mean \|ΔI\| at 44′ / 98′ / 149′ (LUNO Moon) | 0.24 % / 0.29 % / 0.023 % | 0.70 % / 0.063 % / 0.018 % |
| PKS 1934−638 field, flux-weighted mean \|ΔI\| | 5.6e-5 | 1.8e-4 |
| same, off-axis components only (2.4 % of the flux, to 68′) | 0.24 % | 0.75 % |

- katbeam reproduces the main lobe (width to 0.1 %, squint sign) to better
  than the signal of a 30″ offset at the median channel, but not at every
  channel (up to 1.33× at the worst), and it has a constant 0.50 % first
  sidelobe where the measured one varies from 0.30 % to 0.76 % across the
  band (its error grows outward: 0.29 % at 98′, near the first sidelobe).
- EIDOS reproduces the sidelobes best (RMS 0.05 %) but errs 2 % in the
  core, 1.8× the 30″ signal; its x-squint is identically zero and its
  y-squint does not track the holography's. *Post hoc (labelled):* with
  EIDOS read with the opposite vertical flip, the main-lobe max error halves
  to 0.94 % (ring ratio 0.91) and the sidelobe RMS rises to 0.084 %
  (`b1-20261030-11-posthoc`), so EIDOS's grid orientation relative to the
  holography release is ambiguous; the frozen numbers above use s = +1 for
  both.
- Antenna spread: the RMS over the 64 antennas of I_b(antenna) −
  I_b(array average) in the main lobe is **0.12 %** below 1284 MHz and
  **0.21 %** above (core 0.17 %; the median per-channel worst antenna 1.1 %).
  At the half-power ring that is 0.1–0.2× the 30″ signal on average and up
  to 1× for the worst antenna, so per-antenna beams matter for per-antenna
  pointing below about 30″.
- Expected outcome checked: katbeam was expected to err by more than a 30″
  signal at the ring; at the median channel it does not (0.54). EIDOS does
  (1.82). The expectation that EIDOS is closer in the sidelobes holds.

### B1-1 (i): the baseline

- **G1a pass, bit for bit.** The port reproduces all 12 columns of
  `reference_offsets.txt` to **8.9e-16** (heights; offsets to 1e-17 rad).
  Two failures came first (frozen, `b1-20261030-06-baseline`): (1) the port
  refused a fully flagged reference antenna, which upstream silently keeps
  (its `_determine_refant` picks a replacement and discards it); (2) with
  the current ska-sdp-datamodels reader the offsets missed by up to 4.4e-6
  rad, because the pipeline pins datamodels 1.1.0, which stamps each
  integration at TIME − INTERVAL/2 before the zero-order-hold interpolation
  of SOURCE_OFFSET. With both reproduced the match is exact. The Gaussian
  stage alone agrees with scikits.fitting 0.7.2 to 0.0′ on all 56 chunk
  fits (`b1-20261030-07-oracle`).
- **The estimate on the fixture** (Stokes I gain amplitudes, 14 chunks,
  arcmin; σ is the published formal error, scatter the weighted standard
  deviation of the valid chunk centres):

  | Antenna | xEl | σ | El | σ | valid (informative) chunks | chunk scatter xEl, El |
  | --- | ---: | ---: | ---: | ---: | ---: | --- |
  | m000 | −3.70 | 5.39 | +2.06 | 1.45 | 6 (3) | 8.2, 2.4 |
  | m001 | +5.24 | 3.57 | +1.37 | 1.18 | 7 (4) | 6.8, 1.8 |
  | m002 | +5.86 | 7.31 | −5.96 | 3.22 | 7 (4) | 11.6, 6.0 |
  | m003 | +3.40 | 2.77 | −1.72 | 2.16 | 6 (3) | 4.3, 2.5 |

  Every offset is within 1.9σ of zero; the formal σ (1.2–7.3′) is 2–12
  times the 0.6′ that holography removes. 6–7 of 14 chunks are marked
  valid (the 936, 1417, 1471 and 1631 MHz chunks fail the width check for
  every antenna, 1524 MHz for all but m002), but three of them per antenna
  carry no information: *post hoc (labelled, `b1-20261030-11-posthoc/stuck.log`)*,
  the 1204, 1257 and 1578 MHz chunks (the GNSS bands) are fully flagged,
  so their amplitudes and σ_y are 0, the fit stays at its starting values
  (centre 0, width ratio 1, which passes the width check) with NaN σ, and
  it drops out of the weighted mean only because `weighted_avg_and_std`
  masks NaN weights. Each published offset rests on 3–4 chunks (the
  estimate is unchanged when they are removed). The H-only and V-only fits disagree with the
  Stokes I fit: m000 xEl is +3.2′ (H) and +3.6′ (V) but −3.7′ combined,
  m002 xEl +13.3′ and +10.4′, so the estimate depends on which chunks pass
  the width check. `reformatted_offsets.txt` (SKA-style names, offsets
  −3.7′ to +3.0′) matches neither path and stays unexplained.
- **G1b, the bias against simulated truth** (frozen beam, m000–m003 co-polar
  |HH| and |VV| averaged as the pipeline averages the hands, the fixture's
  pointings and σ_y, 200 seeds). Noise-free, with no injected offset, the
  fit returns (xEl, El) = (−0.49, +0.23), (+0.13, +0.04), (+0.09, +0.27),
  (−0.62, −0.11)′ for m000–m003: the measured beam's squint and
  non-Gaussian shape at the ±1° throws. Injected offsets are over-recovered
  by a factor 1.2–1.5 (m000 xEl: injected ±2′ returns +2.42′ and −3.48′).
  With noise the RMS error is 0.3–1.4′, and the formal 1σ interval covers
  the truth in 59–78 % of cases (68 % nominal; worst at ±2′). So the
  baseline method, applied to the real MeerKAT beam, is biased by about
  half an arcminute per antenna and scales offsets by up to 1.5: comparable
  to the 0.6′ it is meant to measure, as expected. On the real fixture its
  noise is larger still (σ above).
- *Post hoc (labelled, `b1-20261030-11-posthoc/squint.log`):* how much of
  that zero point is the beam's own squint, which a pointing fit should
  find? The centroid of ½(|HH| + |VV|) at the chunk frequencies, combined
  with the fit's own chunk weights, is (−0.23, −0.10), (+0.14, −0.24),
  (−0.01, −0.07), (−0.25, −0.28)′ for m000–m003; subtracting it leaves
  (−0.26, +0.33), (−0.01, +0.28), (+0.10, +0.34), (−0.37, +0.17)′. So about
  half of the zero point is squint, and up to 0.37′ (a consistent +0.17 to
  +0.34′ in elevation) is shape bias from sampling the asymmetric beam at
  ±1°; the larger effect is the 1.2–1.5× scale. The fixture's σ_y = 0
  chunks drop out of the G1b fits as they do on the real data.

### What this shows, and what it does not

- The 2023 holography release can be read by range, oriented, interpolated
  (9.2 MHz, cubic spline) and normalised to well inside its own error beam;
  it is the reference beam for B1-2 and B1-3.
- katbeam is a good main-lobe control (fitted by the same group to earlier
  SARAO holography at 60° elevation; `MKAT-AA-L-JIM-2020` predates the end
  of this release's 2020–2022 averaging) with a fixed sidelobe; EIDOS is a good sidelobe control with a 2 % core error and
  an orientation ambiguity. Neither replaces the holography beam at the 30″
  level everywhere in the band.
- The SARAO/SKA Gaussian fit is now reproduced exactly in rang; on its own
  test data it does not resolve the pointing (σ of several arcminutes), and
  against the measured beam it is biased (G1b). That makes the bar for B1-3
  low on the fixture; the fair comparison is G1b's simulated design and
  science data.
- Not shown: anything about pointing on LUNO or ESO137, the
  identifiability of beam directions (B1-2), or pointing self-calibration
  (B1-3). No public store has pointing scans, so B1-1 (i) can only ever run
  on the fixture.

## Next tasks (proposed)

- **B1-2 identifiability survey** (frozen design above). Owner files:
  `python/rangtoy/beam_identifiability.py` (beam-derivative Jacobians per
  component with the B1-0 sampler; the rank and profiled-Fisher machinery;
  `anchored_response` on beam directions), `python/rangtoy/measures.py`
  (geodetic parallactic angle with astropy; FEED RECEPTOR_ANGLE),
  `examples/fetch_eso137_pilot.py` (the bounded `ms1_target_subset` fetch:
  row chunk 0 of DATA, FLAG, WEIGHT_SPECTRUM, MODEL_DATA plus subtables,
  about 1.2 GB), `examples/b1_identifiability.py`,
  `tests/test_beam_identifiability.py`, `tests/test_measures.py`,
  `research/b1-identifiability.md`,
  `research/results/b1-identifiability.json`.
- **B1-3 pointing self-calibration and the rang method against both
  baselines** (metrics frozen above), after B1-2 names the constrainable
  directions. Owner files: `python/rangtoy/pointing_selfcal.py`,
  `examples/b1_pointing_selfcal.py`, `examples/b1_faint_field.py`,
  `tests/test_pointing_selfcal.py`, `research/b1-pointing-selfcal.md`,
  `research/results/b1-pointing-selfcal.json`.

## Timings (every tool run of this task)

WSL host, this branch; wall and peak RSS from `/usr/bin/time` unless noted.

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | Python urllib, zip central-directory probe | L-band npz, 6 range reads | ~5 s | – | not timed; member offsets and npy headers |
| 2026-10-30 | Python urllib, small arrays + metrics npz | 4 range reads + 28,235,140 B | 9.1 s | 83 MB | `b1-20261030-01` |
| 2026-10-30 | git shallow clones + wheel | 3 GitLab repos, scikits.fitting 0.7.2 | – | – | not timed; `b1-20261030-02-ska-pointing-src` |
| 2026-10-30 | Python zipfile, fixture extract | `outer_scans.zip` | ~3 s | – | not timed; `b1-20261030-03-fixture` |
| 2026-10-30 | Python urllib, ESO137 S3 listing + `.zarray` probe | 3 stores, 15 MAIN groups | 74.3 s | 26 MB | latency-bound listings |
| 2026-10-30 | core blosc decode, PHASE_DIR / CHAN_FREQ | 5 small chunks | 2.2 s | 45 MB | |
| 2026-10-30 | uv venv + install, `maturin develop --release --offline` | worktree | 0.35 s (maturin) | 37 MB | extension already built in the checkout's target |
| 2026-10-30 | Python urllib, holography product fetch | 24,320 + 64 range reads, 3.72 GB | 1993.4 s | 6.9 GB | about 1.9 MB/s; RSS is the memmap's resident pages; user 82 s, sys 33 s |
| 2026-10-30 | `examples/b1_baselines.py` G1a, run 1 | fixture, 5 scans | 0.65 s | 226 MB | **failed**: refused a fully flagged reference antenna (upstream keeps it) |
| 2026-10-30 | `examples/b1_baselines.py` G1a, run 2 | fixture | 1.20 s | 221 MB | **G1a failed**: 4.4e-6 rad; current datamodels time stamps |
| 2026-10-30 | `examples/b1_baselines.py` G1a, run 3 | fixture | ~1.2 s | – | pass, 8.9e-16; wall not captured (the run 4 row times the same code) |
| 2026-10-30 | scikits.fitting 0.7.2 oracle | 56 chunk fits | 0.99 s | 87 MB | separate venv; 0.0′ difference |
| 2026-10-30 | EIDOS 1.1.2 probe, three attempts | 3 frequencies | 0.9 s each | 112 MB | **failed**: `recon_par` location; NumPy 2.5.4 refuses `np.sum(generator)` inside EIDOS (an error since 2.4.0); scipy `spline_filter` has no `axes` |
| 2026-10-30 | EIDOS probe, re-expressed reconstruction | 3 frequencies | 1.64 s | 131 MB | 0.2 s per channel |
| 2026-10-30 | `examples/b1_beam_product.py`, smoke | every 20th channel | 1.79 s | 2.93 GB | |
| 2026-10-30 | `examples/b1_beam_product.py`, full | 82 channels, 815 held-out channels | 23.3 s | 4.17 GB | rerun with the compact archive 23.8 s, 4.17 GB |
| 2026-10-30 | `examples/b1_baselines.py` with G1b, run 4 | fixture + 13 injections × 200 seeds | 55.9 s | 494 MB | baseline 0.37 s, sep-pol 0.38 s, G1b 54.5 s |
| 2026-10-30 | post-hoc EIDOS flip check | 82 channels × 2 flips | 36.1 s | 717 MB | labelled post hoc |
| 2026-10-30 | pytest, the two new test files | 13 tests | 1.6 s | – | |
| 2026-10-30 | `bash tools/check-all.sh` | worktree | 254.8 s | 1.67 GB | PASS; pytest 739 passed, 5 skipped in 123.9 s; log `outputs/b1-20261030-check-all.log` |
| 2026-10-30 | post-hoc squint decomposition of G1b | 4 antennas × 14 chunks | 2.65 s | 296 MB | first attempt gave NaN (NaN-σ chunks not excluded); `squint.log` is the rerun |
| 2026-10-30 | post-hoc stuck-chunk check | fixture amplitudes | ~1 s | – | not timed; `stuck.log` |
| 2026-10-30 | `bash tools/check-all.sh`, after the post-hoc edits | worktree | 95 s | – | PASS; pytest 739 passed, 5 skipped in 91.6 s (Rust steps cached); log `outputs/b1-20261030-check-all-2.log` |

## For the coordinator

- **Shared files.** None edited. Added: `research/b1-beam-pointing.md`,
  `research/results/b1-beam-product.json`, `python/rangtoy/beam_holography.py`,
  `examples/b1_beam_product.py`, `examples/b1_baselines.py`,
  `tests/test_beam_holography.py` (8 tests), `tests/test_b1_baselines.py`
  (5 tests; the fixture test skips without `outputs/ska-pointing/outer_scans.zip`).
  EIDOS is not in any extra; `EidosBeam` and its test skip without it
  (`pip install eidos==1.1.2`, GPL-3.0, public PyPI). A `[beam]` extra line
  (`eidos==1.1.2`) is a coordinator decision.
- **`STATE.md`**, new top entry:

  > B1 beam and pointing, B1-0 and B1-1 (i) (big plan wave 3), 2026-10-30
  > (implemented; measured; [b1-beam-pointing.md](b1-beam-pointing.md)).
  > Protocol frozen first. B1-0: SARAO's 2023 L-band holography cube
  > (de Villiers 2023, DOI 10.48479/wdb0-h061, **CC BY-NC 4.0**) is read by
  > HTTP range from its stored 35 GB npz (3.72 GB: array average at 1,024
  > channels, 64 antennas at 9.2 MHz), oriented (s = +1, from the metrics
  > file and katbeam's squint sign), spline-interpolated and normalised;
  > all three gates pass (metrics reproduced to 0.08′ and 0.2 %; frequency
  > interpolation 1.0e-3 median, spatial 6e-5). Against it, over
  > 900–1650 MHz, katbeam errs 0.83 % (median max) in the main lobe and
  > 0.54× the signal of a 30″ offset on the half-power ring, but has a
  > fixed 0.50 % sidelobe (measured 0.30–0.76 %); EIDOS errs 2.1 % in the
  > core (1.8× the 30″ signal) and 0.05 % RMS in the sidelobe, with an
  > ambiguous grid orientation (post hoc). Antennas differ from the array
  > average by 0.12–0.21 % RMS in the main lobe. B1-1 (i): the SARAO/SKA
  > Gaussian pointing-offset fit (SKA SDP pipeline `5ede554` with its pinned
  > dependencies) is ported and reproduces the pipeline's own reference on
  > the five-scan fixture to 8.9e-16 (the brief's "scan 9" is the on-source
  > point of a five-point pattern; the fit needs all five). On the fixture
  > it gives offsets of 1.4–6.0′ with formal σ 1.2–7.3′ (all within 1.9σ of
  > zero; 3–4 informative chunks of 14, plus three fully flagged GNSS chunks
  > that it marks valid at their starting values). Against simulated truth
  > with the holography beam it over-recovers offsets by 1.2–1.5× and
  > returns up to 0.6′ at zero offset, about half of it the beam's squint
  > and up to 0.37′ shape bias (post hoc).
  > ESO137 (`ms1_target`, 734 GB DATA) is the B1 target; no public store
  > has pointing scans. Next: B1-2 identifiability, then B1-3 pointing
  > self-calibration against both baselines.

- **`README.md`**, one line: B1 adds the SARAO holography beam as rang's
  reference beam (`rangtoy.beam_holography`: range reader, per-component
  Jones sampler, katbeam and EIDOS controls) and an exact port of the
  SARAO/SKA Gaussian pointing-offset fit (`examples/b1_baselines.py`;
  `research/b1-beam-pointing.md`).
- **`research/README.md`**: index line for `b1-beam-pointing.md` under the
  beam/pointing section.
- **`tool-timings.md`**: the rows of the timing table above.
- **`big-plan.md`**, wave 3: "B1-0 and B1-1 (i) done 2026-10-30
  (`b1-beam-pointing.md`): holography beam frozen and validated, katbeam and
  EIDOS measured against it, the SARAO/SKA fit ported exactly and its bias
  measured; B1-2 (identifiability survey, ESO137 pilot fetch, measures) and
  B1-3 (pointing self-calibration and the rang method at matched cost) are
  the next worktree tasks, owner files in the report." Also correct the
  literature scan's implication about the holography licence: it is
  CC BY-NC 4.0, not CC BY.
- **Upstream observations, non-RATT** (for `non-ratt-observations.md`):
  - *SARAO holography release (10.48479/wdb0-h061)*: the landing page lists
    `beam_orientation_diagram.pdf` as 180 B (it is 182,647 B and carries
    embedded JavaScript); the metrics file's units are undocumented (widths
    are power HWHM in arcminutes, centroids arcminutes, measured here); no
    checksums are published and the ETag is a multipart tag; the
    orientation diagram is ambiguous unless one assumes row 0 is displayed
    at the top.
  - *ska-sdp-func-python (`calibration/solvers.py`)*:
    `_determine_refant` computes a replacement reference antenna and never
    returns it, so a fully flagged `refant` stays the reference (its gains
    are set to 1 and σ_y becomes 0, which divides by zero in the fit). The
    same in 1.0.4 and 2.0.1.
  - *ska-sdp-wflow-pointing-offset `5ede554`*: a chunk whose data are all
    flagged (zero amplitude, σ_y = 0) yields a fit that never leaves its
    starting values (centre 0, width ratio 1) and is marked valid; it drops
    out of the average only because NaN weights are masked. On the fixture
    that is three of the 6–7 "valid" chunks per antenna (1204, 1257, 1578
    MHz). `BeamPatternFit.fit` also writes
    `all(fit_snr) > 0.0`, which tests that no SNR is zero rather than that
    every SNR is positive; the pinned ska-sdp-datamodels 1.1.0 stamps
    integrations at TIME − INTERVAL/2 (the pyproject notes that 1.1.1 changes
    the output), so offsets depend on the datamodels version at the 4e-6
    rad level; on its own test fixture only 6–7 of 14 chunks pass the width
    check and the Stokes I and per-hand answers disagree in sign;
    `reformatted_offsets.txt` is undocumented; the README says six
    Measurement Sets and lists five (known).
  - *katbeam 0.1 (ska-sa)*: last PyPI release 2020; the cosine-taper model
    fixes the first sidelobe at 0.50 % while the measured array average
    varies 0.30–0.76 % across 900–1650 MHz.
- **Upstream observations, RATT** (for `upstream-notes.md`):
  - *EIDOS 1.1.2 (ratt-ru/eidos)*: beam reconstruction fails under NumPy
    2.4 and later (`spatial.Zernike.reconstruct` calls `np.sum` on a
    generator: deprecated since 1.15, a `TypeError` since 2.4.0, gh-30068;
    seen on 2.5.4), so `eidos` cannot build a beam on a current stack; rang
    re-expresses the reconstruction with Python's `sum`. Its x-squint is
    identically zero, and its grid's vertical orientation relative to the
    2023 holography release is ambiguous (the opposite flip halves the
    main-lobe error, post hoc). Candidate issue with a one-line fix
    (`np.sum(...)` → `sum(...)`) after reproduction on the latest release.
- **Evidence to keep.** `outputs/b1-20261030-05-holography/` (the product
  with `manifest.json`, 3.72 GB; refetchable in about 33 min),
  `outputs/b1-20261030-09-product/b1-beam-product-full.json`,
  `outputs/b1-20261030-10-baseline-g1b/b1-baselines.json` (the baseline
  archive, 42 kB; a candidate for `research/results/` at merge),
  `outputs/b1-20261030-07-oracle/oracle.log`,
  `outputs/b1-20261030-11-posthoc/eidos_flip.log`,
  `outputs/b1-20261030-04-eso137-probe/` (store metadata). The upstream
  clones in `b1-20261030-02-ska-pointing-src` can be deleted after merge.
- **Open items.** EIDOS's grid orientation relative to the holography
  release (post hoc, ambiguous); `reformatted_offsets.txt` unexplained;
  `beam_holography.fetch_product` written but not exercised end to end (the
  product came from the scratch script of the same layout); `eidos` in no
  extra; the ESO137 target's XY/YX weights not measured (B1-2's first
  step); the 3.72 GB product must stay in `outputs/` (or be refetched,
  33 min).
- **User items.** None blocking. The holography data are CC BY-NC 4.0:
  fine for this research, never redistributed; a commercial use of rang's
  B1 products would need SARAO's permission. The committed
  `results/b1-beam-product.json` holds derived statistics only (widths,
  centroids, differences), no beam maps; whether that is acceptable inside a
  GPL repository is the user's call.
