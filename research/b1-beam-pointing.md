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
