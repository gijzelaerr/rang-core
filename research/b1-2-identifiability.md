# Rang B1-2: which beam and pointing directions can the data constrain? (protocol)

Protocol frozen 2026-10-30 on branch `b1-2-identifiability` (from main
`3b875e0`), before any B1-2 survey code was written. Task B1-2 of
[big-plan.md](big-plan.md) wave 3; the design it restates was frozen in
[b1-beam-pointing.md](b1-beam-pointing.md) ("B1-2: the first rang
experiment, identifiability", "Measures convention").

Status: **proposed** (this section). Results are appended below the
protocol when measured; nothing above "Measured result" changes after this
commit except through a dated, labelled amendment.

Status (2026-10-30): **implemented and measured; B1 does not close null at
B1-2.** No amendment. The frozen convergence rule fired on S1, so the
verdict uses the beam evaluated at 16-channel sub-blocks. Under the frozen
decision rule, these directions are constrainable:

- **Per-antenna pointing** on the ESO137 pilot and track: σ ≈ 0.06–0.2′,
  with ρ ≈ 0.8–0.9 of the signature outside the nuisance span. It is
  marginal on the whole-array 1934 set: σ ≈ 0.18′, ρ ≈ 0.12, 52 of 53
  antennas, and only with the recalibrated noise (0.43′ with the stored
  weights).
- **Squint** on S2, S4 and S5: σ ≈ 0.004–0.04′.
- **Array-common pointing and ellipticity** on the track. They come from
  its 160° of parallactic rotation: σ ≈ 0.005′ and 0.06 %.

Array-common width is constrainable on no set: σ = 0.54 % on S2 and S5,
against the 0.5 % threshold.

The array-common pointing that passes on the snapshots (S2, S3, S4) does so
only through the beam's frequency structure inside a 32-channel gain
interval. A per-channel bandpass would remove it exactly on the single
point source S3 (post hoc).

Details in "Measured result".

## The frozen B1-2 design, restated

From [b1-beam-pointing.md](b1-beam-pointing.md), unchanged:

- **Directions.** Per antenna and solution interval, the pointing
  derivatives ∂V/∂δ_x and ∂V/∂δ_y. Array-common log-width, ellipticity and
  squint. Each is computed with the frozen B1-0 beam (the SARAO 2023
  holography product, `outputs/b1-20261030-05-holography`) at every
  component.
- **Nuisances, profiled.** Per-antenna 2×2 diagonal gains per solution
  interval, and the sky component fluxes.
- **Measures per direction.** The profiled Fisher σ, the fraction of the
  direction's signature outside the nuisance span, and the anchored
  response.
- **Data.** The LUNO PKS 1934−638 calibrator, chunk 0, on four stations and
  on the whole array, with the CARACal field model. The PKS 1830−211 scans
  as in L2. The ESO137 target pilot.
- **Decision rule.** A direction is *constrainable* on a set if:
  - its profiled Fisher σ ≤ 0.3′ for pointing, or ≤ 0.5 % for width and
    ellipticity; **and**
  - at least 1 % of its signature lies outside the nuisance span.

  B1-3 fits only constrainable directions. If none is constrainable on any
  set, B1 closes null at B1-2.
- **Measures reference.** The geodetic parallactic angle, with astropy as
  the reference.
- **Expected outcome, from B1.**
  - Calibrators: not constrainable per antenna; at best array-common width.
  - ESO137: array-common pointing and width constrainable at the arcminute
    level; per-antenna pointing per hour only for the brightest off-axis
    sources, if at all.

  This expectation is sharpened below in the light of the probes.

## Pre-protocol probes (labelled scratch)

These probes read metadata and small objects only. No survey quantity, Fisher
matrix or image was computed. All runs were on the WSL host, on this branch.

| Run | Dir under `outputs/` | What | Bytes | Wall | Peak RSS |
| --- | --- | --- | ---: | ---: | ---: |
| `fetch_eso137_pilot.py probe` | `b1-2-20261030-00-probe` | S3 listings of `ms1_target_subset.zarr`; `.zarray` metadata; row columns, FLAG, MODEL_DATA and UVW of row chunk 0; subtable arrays | 5,531,329 | 14.5 s | 52 MB |
| DATA calibration probe (`core_fetch.fetch_slice`, stations 0–3) | `b1-2-20261030-00-probe-data` | DATA, FLAG, WEIGHT_SPECTRUM of the 162 four-station rows of row chunk 0, by HTTP range | 105,573,706 | 12.1 s | 67 MB |
| track sizing (HEAD requests) | `b1-2-20261030-00-probe-track` | `ms1_target.zarr`: 7 MAIN groups, sizes of the row-chunk-0 objects of channel tile 20 | – | 19.5 s | 24 MB |
| parallactic-angle spans (astropy) | `b1-2-20261030-00-probe/pa_spans.json` | the sets below | – | 1.3 s | 169 MB |

The scratch scripts are kept in `/home/gijsm/Build/tmp/20261030-b1-2/` until
the end of the task, and copied into the probe directories.

Facts found. The protocol rests on them.

1. **The ESO137 stored model is empty.** MODEL_DATA in row chunk 0 of
   `ms1_target_subset.zarr` is identically zero in all four correlations.
   Its compressed size, 3.4 MB per 800 MB chunk, matches the whole column's
   61 MB, so it is almost certainly zero everywhere. The stored-model branch
   of the B1 data decision is therefore dead: **the field model is built
   from an image of the pilot** (below).
2. **The subset's DATA is not calibrated.** The subset has no
   CORRECTED_DATA. On the six four-station baselines:
   - the XX–YY phase difference is coherent (|⟨e^{iΔφ}⟩| = 0.974–0.9996)
     but antenna-dependent: 1.50–1.90 rad on baselines to antenna 0,
     −0.07 rad on 1–2, and −0.42 and −0.52 rad on 2–3 and 1–3;
   - the XX/YY amplitudes differ by up to 16 %.

   For an unpolarised sky in calibrated data the XX–YY phase is near zero,
   so the parallel hands carry uncalibrated per-antenna, per-hand gains.
   They are stable over the 208 s: time-averaged amplitude over
   instantaneous amplitude is 0.99–1.005. **Imaging the pilot therefore
   needs a self-calibration**, which is frozen below.
3. **The pilot.** Row chunk 0 of the subset holds:
   - 50,000 rows: 27 dumps of 8 s (207.9 s), 61 antennas and 1,602
     autocorrelation rows;
   - 500 channels from 1347.11 to 1451.40 MHz (0.209 MHz).

   18.7 % of the cross-correlation samples are flagged, identically in all
   four correlations. The XY/YX weights are **not** zero: median 24.2 and
   25.4, against 25.5 (XX) and 24.2 (YY) on the probe rows. Chunk sizes:

   | Object | Bytes |
   | --- | ---: |
   | DATA | 742,999,616 |
   | WEIGHT_SPECTRUM | 294,835,092 |
   | FLAG | 1,137,763 |
   | MODEL_DATA | 3,411,207 |
   | UVW | 965,122 |
   | row columns and subtables | < 0.4 MB |
   | **total** | **≈ 1.0436 GB** |
4. **Feeds.** The FEED table has one group per antenna (FEED_0…FEED_60).
   FEED_0 RECEPTOR_ANGLE is −π/2 for **both** receptors. Taken literally,
   that is not an orthogonal pair.
5. **Pickle columns.** ANTENNA/NAME, FIELD/NAME, FEED/POLARIZATION_TYPE and
   the other string columns of the ESO137 stores are pickle-encoded object
   arrays. They are never decoded: antennas are used by index, and nothing
   in B1-2 needs their names.
6. **The track** (`ms1_target.zarr`). There are 7 MAIN groups, MAIN_0…MAIN_6,
   for scans 2, 4, …, 14. Each has 849,059–850,950 rows and 4,096 channels
   in tiles of 50,000 rows × 128 channels. Row chunk 0, channel tile 20
   (channels 2560–2687, 1391.0–1417.5 MHz, inside the pilot band), is
   **268,491,290–269,215,091 bytes per scan** for DATA, FLAG,
   WEIGHT_SPECTRUM, UVW and the row columns: **1,881,959,542 bytes for the
   seven scans**.
7. **Parallactic-angle spans** (geodetic, astropy, array-centre position):

   | Set | Span | Elevation | q |
   | --- | ---: | ---: | --- |
   | LUNO 1934−638, chunk 0 | 247.9 s | 22.7–23.2° | −113.41° → −112.56° (0.85°) |
   | LUNO 1830−211, MAIN_2 chunk 0 | 72.0 s | 17.6–17.8° | −116.75° → −116.68° (0.07°) |
   | ESO137 pilot | 207.9 s | 47.7–48.1° | −65.28° → −64.32° (0.96°) |
   | ESO137 track | ~8.0 h | 34–60° | −67.4° → +92.4° (160°) |

## What the probes change, stated before running

A time-constant array-common change (pointing, width, ellipticity) at fixed
parallactic angle only rescales each component's apparent flux, with a
slowly varying frequency dependence. With component fluxes free, it is
absorbed except for three parts:

- the XX/YY difference (squint, ellipticity of the separate hands);
- what a per-component flux and spectral index cannot follow across the band;
- the rotation of the beam on the sky with q.

All four chunk sets rotate by under 1°. The B1 expectation for ESO137
(array-common pointing and width at the arcminute level) is therefore
**optimistic for the snapshot pilot**, and this protocol says so before any
number exists.

To test the array-common directions at all, a track set S5 is added: one
3.5-min chunk from each of the seven scans, spread over 160° of q. It is
sized and named here, as the brief requires. A null on the snapshot sets
alone would say nothing about a track.

## Data sets (frozen)

LUNO sets use row chunk 0, channels 1024–3072 (2,048 channels, 1070–1498
MHz) and kept rows (cross-correlations, FLAG_ROW false), read from the
archived tiles exactly as K, L1 and L2 read them (`core_campaign_1830.decode_inputs`
with `roots_for`). Nothing is fetched for them.

| Set | Data | Rows | Field model |
| --- | --- | --- | --- |
| **S1** | LUNO `MAIN/MAIN_1` (J1939−6342), stations 0–3 | 6 baselines | L1-M CARACal lsm, 196 components |
| **S2** | LUNO `MAIN/MAIN_1`, all 64 stations | 2,016 baselines | L1-M CARACal lsm |
| **S3** | LUNO `MAIN/MAIN_2` (J1833−2103), all stations (L2's fetch `outputs/l2-1830-20261030-01-fetch`) | as L2 | L2's frozen scalar arm: a point at the phase centre, I₀ = 7.83892 Jy at 1.284 GHz, α = 0.222271 |
| **S4** | ESO137 pilot: `ms1_target_subset.zarr` row chunk 0, 61 antennas, 500 channels | 48,398 cross rows | from the pilot image (below) |
| **S5** | ESO137 track: `ms1_target.zarr` MAIN_0…MAIN_6, row chunk 0, channel tile 20 (128 channels, 1391.0–1417.5 MHz) | 7 × ≈ 48,400 | the S4 field model |

Notes on the models and sources:

- **The lsm fluxes are apparent.** This is how CARACal and L1-M predict
  them, without a beam. Each component's model visibility is its apparent
  Stokes I times its phase term; the beam enters only through derivatives
  (below).
- **Gaussian components** use the core predictor's envelope.
- **The S3 point model** carries a single component, so every beam
  direction is absorbed by the gains except through the 0.07° rotation. S3
  is the analytic degenerate control on real geometry.
- **Licences.** ESO137 is CC BY 4.0 (cite Ramatsoku et al. 2020). The
  holography beam is CC BY-NC 4.0 (cite de Villiers 2023,
  DOI 10.48479/wdb0-h061). Only derived numbers are committed.

## Fetch (frozen bounds)

`examples/fetch_eso137_pilot.py` is written for the probe and is extended,
after this commit, with the two fetches below. It refuses to fetch if the
listed sizes exceed the bound, and it records bytes, SHA256, ETag,
Last-Modified and time per object.

- **S4 pilot**: row chunk 0 of `ms1_target_subset.zarr` MAIN_0. The columns
  are DATA, FLAG, WEIGHT_SPECTRUM and MODEL_DATA (the B1 list), plus UVW,
  TIME, ANTENNA1, ANTENNA2, FLAG_ROW and INTERVAL, and these subtable
  arrays: ANTENNA POSITION and DISH_DIAMETER, SPECTRAL_WINDOW CHAN_FREQ and
  CHAN_WIDTH, FIELD PHASE_DIR, POLARIZATION CORR_TYPE, FEED_0 RECEPTOR_ANGLE
  and ANTENNA_ID, and OBSERVATION TIME_RANGE. **Bound: 1.25 GB** (expected
  ≈ 1.044 GB).
- **S5 track**: for each of MAIN_0…MAIN_6 of `ms1_target.zarr`, the objects
  `DATA/0.20.0`, `FLAG/0.20.0`, `WEIGHT_SPECTRUM/0.20.0`, `UVW/0.0`, and
  TIME, ANTENNA1, ANTENNA2 and FLAG_ROW `/0`, plus the `.zarray` and
  `.zattrs` files; also `SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ` and
  ANTENNA POSITION. **Bound: 2.0 GB** (expected 1.882 GB).

Nothing else is fetched. The 734 GB DATA column is never read beyond these
objects.

## Beam, frames and measures (frozen)

- **Beam.** The B1-0 product's **array average** at its 1,024 native
  channels, the same for every antenna. Interpolation is the frozen B1-0
  rule: cubic spline in space on the real and imaginary parts, linear in
  frequency.
  - Values and the gradients ∂/∂x, ∂/∂y are the **analytic derivatives of
    that spline**: direct evaluation of the cubic B-spline on the prefiltered
    coefficients and their derivative kernels. A test checks them against
    `map_coordinates` (values) and finite differences (gradients).
  - Normalisation is the B1-0 rule: I_b = 1 at the origin of the reference
    beam. The reference normalisation is kept under every perturbation, so
    a pointing offset lowers the on-axis response.
  - *Labelled check:* per-antenna product beams m000–m003 on S1, if
    stations 0–3 decode as m000–m003 by their json2 names. The antennas
    differ from the array average by 0.12–0.21 % RMS (B1-0).
- **Parallel hands.** X = H and Y = V, as frozen in B1-0. The beam product
  per hand is B_h(p, q) = Σ_m E_p[h, m] conj(E_q[h, m]), so the co-polar
  and cross-polar voltage terms are both included. The cross hands XY and YX
  are **not used**: the models are Stokes I, so they carry beam signal only
  through the leakage terms. This is a frozen restriction.
- **Pointing centre** is the FIELD phase direction for every set.
- **Sky to beam.** With the parallactic angle q (the position angle of the
  zenith seen from the source, measured from north through east):
  - ŷ (elevation) is toward the zenith, ŷ = (sin q, cos q) in (l, m);
  - x̂ (cross-elevation) is toward increasing azimuth, x̂ = (−cos q, sin q);
  - so **x = −l cos q + m sin q** and **y = l sin q + m cos q**.

  The holography maps are measured in the dish (H/V) frame, so the feed's
  RECEPTOR_ANGLE is **recorded, not applied** (fact 4).
  - *Labelled check:* on S1 and S4, the array-common family is rerun with
    the beam frame rotated by +90°.

  The sign of x̂ relative to the holography grid's x is a convention that
  B1-0 could not test independently. The survey is invariant to it up to a
  mirror of the beam, which the measures barely see.
- **Parallactic angle** (`python/rang/measures.py`).
  - The reference: astropy (`iers.conf.auto_download = False`, the bundled
    IERS tables). The zenith at the observing time and the array centre's
    `EarthLocation.from_geocentric` position is transformed to ICRS, and q is
    `source.position_angle(zenith)` in the ICRS frame of the J2000 phase
    direction.
  - The core has no parallactic-angle implementation, so there is no core
    tolerance to freeze. A closed-form implementation (the hour-angle
    formula on astropy's apparent coordinates) is checked against the
    reference at **≤ 0.01°** in a test, so that the fast path cannot drift.
  - q is evaluated at every gain time bin's mean time; the array is
    co-located to well inside 0.01° of q.
- **Components beyond the main lobe.** A component whose I_b < 0.01 at a
  block's centre frequency keeps its flux nuisance but contributes no beam
  derivative in that block. Its log-derivative is ill-defined from an
  apparent flux. The count is recorded.

## Directions and units (frozen)

Each direction is a perturbation of the reference voltage beam E(u), with u
= (x, y) in the antenna frame. All directions are evaluated at zero
perturbation.

| Direction | Perturbed beam | Unit | Threshold |
| --- | --- | --- | --- |
| per-antenna pointing δ_p (x, y) | E_p(u − δ_p) | 1′ | σ ≤ 0.3′ |
| array-common pointing c (x, y) | δ_p = c for all p | 1′ | σ ≤ 0.3′ |
| log-width w | E(u e^{−w}) | 0.01 (1 %) | σ ≤ 0.005 |
| ellipticity e (antenna x/y axes, one component) | E(x e^{−e}, y e^{+e}) | 0.01 | σ ≤ 0.005 |
| squint s (x, y) | H row E[0, :](u − s/2), V row E[1, :](u + s/2) | 1′ | σ ≤ 0.3′ |

- Squint has no threshold in B1. It takes the pointing threshold per
  component; this is a gap filled before running.
- Array-common pointing is not in B1's direction list but is in its expected
  outcome. Here it is the common mode of the per-antenna directions.

**Intervals.** Per-antenna pointing has one offset per antenna per chunk:
S1–S4 are single chunks of 72–248 s, and S5 has one offset per antenna per
scan chunk. The array-common directions are constant over the set, and over
the whole track on S5. The verdict is on the data as measured. A projection
to the one-hour interval of B1's metrics, σ × √(T/3600 s), is reported only
as a labelled **forecast**, never as the verdict.

## Nuisances (frozen)

- **Gains.** Diagonal complex gains g_{p,h}, per antenna and per hand
  (X, Y), per solution interval of 2 dumps × 32 channels: the K/L1/L2 grid
  (`core_campaign.GRID`). On S4 the 500 channels form 15 blocks of 32 and one
  of 20. On S5 the intervals are per scan. The parameters are log-amplitude
  and phase, linearised at unit gains.
- **Sky.** Shared by both hands (Stokes I). Two arms, both reported:
  - **primary**: per component, ln S₀ and a spectral index α about the
    set's mean frequency, with the α column evaluated at block centres;
  - **strict**: per component, a free flux in every 32-channel block.

  On S5 the sky is shared across the seven scans.
- **Verdict arm.** The verdict uses the primary arm. A direction that passes
  on the primary arm and fails on the strict arm is labelled "needs a
  spectral prior".

## Noise (frozen)

The thresholds are absolute, and σ scales as (weight scale)^−½. C1 measured
the LUNO weights as off by about 5.6. So the noise is calibrated per set and
per hand from the data, and σ is reported with the raw weights as well. The
verdict uses the calibrated weights.

- **Eligibility** per hand: cross-correlation; FLAG_ROW false; that hand's
  FLAG false; WEIGHT_SPECTRUM > 0; DATA finite.
- **Noise scale.** Take non-overlapping adjacent channel pairs (2j, 2j+1)
  with both samples eligible, and form
  z = (D_{2j+1} − D_{2j}) / √(1/w_{2j} + 1/w_{2j+1}).
  The scale s_h² is the median of the real and imaginary parts of z²,
  divided by 0.454936 (the χ²₁ median). The real and imaginary noise
  variance of a sample is then s_h²/w (the CASA convention).
- **Model units.** The data are V = c M + n with an amplitude scale c, so
  the variance in model units is s_h²/(w c_h²).
  - LUNO: c_h = median |D_h| / median |M| over the eligible samples (D and M
    on the same samples).
  - ESO137: c_h is the median over baselines of |g_{p,h} g_{q,h}| from the
    field-model gain solution (round 2 below), on that scan.
- **Reported per set:** s_h, c_h and the raw-weight σ for every direction.

## Measures (frozen definitions)

The whitened, real-stacked metric ⟨a, b⟩ = Σ_i Re(conj(a_i) b_i) / σ_i² is
taken over the eligible parallel-hand samples. For a direction θ with
signature s_θ:

- **F_raw** = ⟨s_θ, s_θ⟩.
- **F_prof** = ⟨P⊥ s_θ, P⊥ s_θ⟩, where P⊥ projects off the span of all
  nuisance columns (gains and sky) and the other beam directions are held
  at zero.
- **Conditional σ** = F_prof^−½, in the direction's unit. This is the
  decision measure, as B1 designed it ("for each direction, after profiling
  the nuisances").
- **Span fraction** ρ = ‖P⊥ s_θ‖ / ‖s_θ‖ = √(F_prof/F_raw), the whitened
  norm fraction of `observability.py`'s `retained_derivative_norm_fraction`.
  ρ² is reported too, along with ρ for gains alone and for the sky alone,
  which shows what absorbs the direction.
- **Family-marginal σ** (secondary; not in the rule).
  - Per-antenna pointing: all antennas' offsets free together, in the
    zero-mean parametrisation Σ_p δ_p = 0 per axis, with the common mode
    reported as array-common pointing.
  - Array-common family: the six common directions free together.

  A direction that passes conditionally but fails family-marginally is
  labelled "constrainable alone only". B1-3 must use family-marginal
  numbers for any joint fit. Across families the treatment is conditional:
  the other family is held fixed.
- **Anchored response.** The gain response to a unit perturbation (1′ or
  1 %), per gain bin, with the sky held fixed. It is the horizontal-gauge,
  minimum-norm solution of the bin's diagonal-gain normal equations, with
  the native constants: cutoff 1e-10 λ_max and damping 1e-6 λ_max. It is
  summarised as the median and maximum over bins of max_p |δg_p|/|g_p|, the
  relative station step.
  - On S1 the native `core_influence.anchored_response` is also called. It
    is full-Jones (8 parameters per station, U(2) gauge), with the bin
    normals from `training_normals` and the signature passed as the
    residual. The call is full_b = 0, drop_h = 0, drop_b = −score, so that
    delta = H⁺·score.
  - Its guard-pass and status counts are reported. Where it passes, the
    diagonal part of its delta is compared with the NumPy diagonal response
    at **relative tolerance 1e-6**. For a scalar model with a diagonal
    signature the off-diagonal block decouples, so the two must agree.
  - LUNO four-station bins have historically returned status 6 or a rank
    mismatch. Those are reported as they come; the native code is never
    patched to get a number.

## Computation (frozen)

The dense Jacobian is never built: S4 alone has about 10⁸ real rows. Per
gain bin (time bin × channel block × hand) the survey proceeds as follows:

1. Form the whitened component phase terms Z_ik = S_k(ν_i) K_ik / σ_i on
   the bin's eligible samples. K is the exact per-channel phase (and
   Gaussian envelope) at the row's UVW, with the core predictor's sign.
2. Accumulate the normal blocks of:
   - [gains (2 per antenna) | sky columns | per-antenna pointing (2 per
     antenna) | common (6)];
   - the beam log-derivatives are evaluated at the block's centre frequency
     and the bin's q.
3. Schur-eliminate the gains (pseudo-inverse after column equilibration,
   cutoff 1e-10 of the largest eigenvalue).
4. Sum the reduced blocks: over time bins and hands, per channel block for
   the strict arm; over everything for the primary arm, through the map
   from (ln S₀, α) to the block fluxes.
5. Eliminate the sky.

The generalised Schur complement with pseudo-inverses is exact for Gram
matrices, because the coupling columns lie in the range of the eliminated
block.

**Convergence check (frozen).** On S1 and S4 the beam is also evaluated at
16-channel sub-block centres. If any common direction's conditional σ, or
the median per-antenna σ, changes by more than **5 %**, the finer
evaluation is used for every set and the change is recorded.

Limits:

- The predictor has no time or frequency smearing (L1-M item 6).
- The survey is local, at the model: an incomplete field model removes
  information but does not invent it.

## ESO137 field model (frozen procedure)

The ESO137 field model is built from the S4 pilot's DATA, FLAG and
WEIGHT_SPECTRUM, on the eligible parallel hands.

1. **Round 0.** Phase-only diagonal gains per antenna, per hand and per
   32-channel block, constant over the pilot (fact 2: the gains are stable
   over the 208 s). They are solved by alternating least squares (StefCal
   form: 100 iterations, averaging 0.5, stop at a relative change of 1e-8)
   against a 1 Jy point at the phase centre. Correct the data.
2. **Image.** The corrected Stokes I with the core gridder
   (`core_grid.invert`): Briggs 0.5, 4096 × 4096 pixels of 4″, 128
   w-layers, padding 1.2, and the PSF from the same call. Then Högbom CLEAN
   (gain 0.1) in the central 2048 × 2048 window (±1.14°), down to 20× the
   robust σ (1.4826 MAD of the window's residual), or 5,000 iterations.
3. **Round 1.** Phase-only gains against the round-0 CLEAN model, predicted
   by the core predictor. Re-image, then CLEAN to 10σ (10,000 iterations).
4. **Round 2.** Amplitude-and-phase gains against the round-1 model.
   Re-image, then CLEAN to 5σ (20,000 iterations). These are the final
   components.
5. **Components.**
   - CLEAN components are merged on 12″ cells (3 × 3 pixels), keeping the
     summed flux at the flux-weighted position.
   - Only positive merged components within the first-null radius of the
     array-average I_b at 1347 MHz (from the B1-0 profile) are kept, and at
     most the **300** brightest.
   - Fluxes are apparent and in corrected-data units, with α = 0.
   - The kept and total CLEAN flux are reported.
6. **Gate E0 (field model usable).** The final residual-plus-model peak over
   the robust σ must be ≥ 50, **and** the kept components must carry ≥ 50 %
   of the CLEAN flux. If E0 fails, S4 and S5 are recorded as "no field
   model" (a failure, not a null), the verdict rests on S1–S3, and the
   ESO137 question stays open.
7. **S5 gains.** On each S5 scan, gains are solved against the field model
   with the round-2 settings, which give c_h per scan. The model is the S4
   field. The tile-20 band lies inside the pilot band.

## Decision rule (frozen, B1's with the gaps filled)

A direction is **constrainable** on a set if, on the primary sky arm with
calibrated noise:

- its conditional σ is ≤ 0.3′ (per-antenna pointing per antenna and axis,
  array-common pointing, squint), or ≤ 0.005 (log-width, ellipticity); and
- ρ ≥ 0.01.

The rule is applied to:

- every set (S1–S5) and every direction;
- per-antenna pointing per (antenna, axis), with the family line giving the
  count that passes ("constrainable" if all pass, "partly" if some, "not" if
  none).

Labels reported next to the verdict: "needs a spectral prior",
"constrainable alone only", the raw-weight σ, and the forecast.

**B1 closes null at B1-2 if and only if no direction passes on any set**,
counting every single antenna and axis. Thresholds are never moved after a
result is seen.

## Expected outcome, stated before running

- **S1, S2 (1934).** 97.6 % of the flux is at the centre and q turns by
  0.85°.
  - Per-antenna pointing is not constrainable: ρ ≪ 0.01, with σ of
    arcminutes on S1.
  - Array-common width or ellipticity on S2 may reach σ ≤ 0.5 %, but with ρ
    near or below 1 %.
  - Squint has the best chance on S2 through XX/YY.
- **S3 (1830, a point).** Every direction has ρ ≈ 0, a numerical control.
- **S4 (pilot).** Snapshot; components across the main lobe.
  - Per-antenna pointing σ of order an arcminute or worse, so not
    constrainable.
  - Array-common pointing and width largely absorbed by the free component
    fluxes, so not constrainable.
  - Squint possible.
- **S5 (track).** Array-common pointing and width constrainable at the
  arcminute and sub-percent level, which is B1's expectation moved to the
  set that can test it. Per-antenna pointing per scan chunk probably not.
- A null on every set closes B1 at B1-2. That is a result.

## Tests (fast, synthetic; `tests/test_b1_identifiability.py`)

- **Known degenerate.** A single point at the phase centre with a symmetric
  Gaussian toy beam and no rotation: every direction has ρ ≤ 1e-6.
- **Known identifiable.** Two components, one at the half-power radius,
  with gains fixed and fluxes fixed: per-antenna pointing has ρ = 1, and σ
  equals the analytic finite-difference Fisher value to 1e-6. With gains
  and fluxes free, ρ > 0.05 for the off-axis axis.
- The spline values match `map_coordinates` to 1e-12, and the analytic
  gradients match central differences to 1e-6 relative.
- The Schur-complement survey equals a dense projection on a small case to
  1e-9.
- measures: q at transit has the frozen sign; the closed form matches
  astropy to 0.01°.

## What is not used

The held-out split (seed 7, [flagging-verdict.md](flagging-verdict.md)) is
reserved for B1-3's held-out visibility metric. B1-2 fits nothing.

## Implementation (2026-10-30)

**`python/rang/beam_identifiability.py`** holds the survey.

- **Spline derivatives.** `spline_sample` evaluates the cubic B-spline and
  its derivative kernels directly on the B1-0 prefiltered coefficients.
  `HolographyGradient` applies the B1-0 interpolation and normalisation.
  `GaussianToyBeam` stands in for tests.
- **`direction_factors`** gives the log-derivative factors of every
  direction per component and hand, with the I_b < 0.01 floor.
- **`phase_terms` and `spectra`** reproduce the core predictor's terms
  (L1-M's direct DFT).
- **`block_normals`** gives the Gram matrix of one gain bin and hand,
  [gains | sky | per-antenna pointing | common] for each beam variant,
  from sparse antenna incidence and bincounts. With `slope` (post hoc) it
  adds per-antenna gain slopes.
- **`Survey`** does the following:
  - Schur-eliminates the gains per bin;
  - keeps raw and reduced blocks per (scan, block, hand) with raw weights,
    so κ is applied exactly at combination;
  - profiles the sky in the primary (ln S₀, α) and strict (per-block flux)
    arms;
  - records the NumPy anchored response.
- **`measures_from`, `verdict` and `summarise`** implement the frozen
  measures and rule.
- **`noise_scale`, `stefcal` and `hogbom`** serve the noise calibration and
  the field model.

**`python/rang/measures.py`** gives the parallactic angle with astropy as
the reference (ICRS position angle of the geodetic zenith), a closed form
with the apparent-to-ICRS rotation, and `sky_to_beam`.

**`examples/b1_identifiability.py`** has three subcommands:

- `fieldmodel`: the frozen three-round procedure, an orientation check, a
  model-sign check and E0;
- `survey SET`: loaders for the archived LUNO tiles and the ESO137
  fetches, noise and amplitude scales, the survey, the S1 native anchored
  response, and `survey.json`. The post-hoc options `--beam-sampling
  product`, `--gain-slope` and `--taper-json` are labelled in the output;
- `archive`: keyed by run directory with roles (verdict, trigger, post
  hoc, field model). `closes_null` comes from the verdict runs only.

**`examples/fetch_eso137_pilot.py`** does the probe and the bounded S4 and
S5 fetches, with receipts. It refuses object and pickle arrays.

**Validation** (`tests/test_b1_identifiability.py`, 13 tests, 2.5 s):

- spline values equal `map_coordinates` to 1e-12, and gradients equal
  central differences to 1e-6;
- the Schur-reduced survey equals a dense real-stacked projection to 1e-9,
  with and without gain slopes, for all six information matrices;
- the raw Fisher information of pointing, width, ellipticity and squint
  equals finite differences of the perturbed-beam model to 1e-6;
- a single off-axis component gives ρ ≤ 1e-6 for every direction;
- two components give ρ > 0.05;
- noise, StefCal and Högbom recover known inputs;
- q rises through zero on the ESO137 track, and the closed form matches
  astropy to 0.01°;
- on real data, the native anchored response agrees with the NumPy
  diagonal response to 2.5e-14.

**No Rust kernel.** The largest run (S2) is 51 min single-threaded, dominated
by the K² sky Gram per gain bin, a BLAS call. No Python loop was the
bottleneck, so `core/src/` is untouched.

## Errata and implementation notes (2026-10-30, after the protocol; labelled)

None of these changes a frozen threshold, set, direction or measure.

- **Station counts (erratum to the set table).** S2 is not "64 stations,
  2,016 baselines". The 1934 chunk has 53 stations with data and 1,378
  baselines (41,786 kept rows) of the 56 rows in the ANTENNA table, as L1
  recorded. S1 is 192 rows (6 baselines × 32 dumps); 70 % of its samples
  are flagged. S3 is 56 stations, 1,540 baselines and 15,400 rows over 72 s
  (10 dumps).
- **measures.** The first closed-form implementation skipped the rotation
  from apparent to ICRS north. Its test caught 0.21° (precession and
  nutation since J2000 at ESO137 in 2019) before any measurement, and the
  fix rotates by the ICRS position angle of apparent north. The frozen
  0.01° tolerance passes.
- **Inactive antennas.** Run `-03` (S1) counted antennas without data in its
  per-antenna family line (56 instead of 4) and in the family-marginal
  zero-mean constraint. Run `-06` repeats S1 with the fix; every
  conditional σ and ρ is identical to `-03`. `-03` is kept as the run that
  fired the convergence rule.
- **Amplitude scale from gains.** The first `scan_scale` took the median
  |g_p g_q| over every block, including fully flagged blocks whose gains
  stay at 1. Post-hoc run `-08` exposed it by taking that branch on S1 by
  mistake (c = 1). The fix (`gain_scale`: solved baseline-blocks only) was
  in place before S4 and S5 ran. The field model's own `fieldmodel.json` "c"
  predates it; the survey recomputes c. `-08` is superseded by `-18`.
- **Field-model bookkeeping.** The CLEAN threshold's robust σ is taken from
  the dirty window at the start of each round, not from the residual. E0's
  "residual-plus-model peak" is the dirty-image peak. The window is CLEANed
  as frozen.

## Measured result (2026-10-30)

Status: **implemented and measured** on all five frozen sets. The verdict
uses the 16-channel beam evaluation ("sub16"), as the convergence rule
requires. The 32-channel evaluation ("nominal") is reported beside it.

### Runs

All runs on the WSL host, this branch, `OPENBLAS_NUM_THREADS=1`,
`RAYON_NUM_THREADS=4`, under `outputs/`.

| Dir | Role | What |
| --- | --- | --- |
| `b1-2-20261030-00-probe`, `-00-probe-data`, `-00-probe-track` | pre-protocol probes | above |
| `b1-2-20261030-01-pilot` | fetch | S4 pilot, 1,043,366,221 B in 100.3 s (planned 1,043,355,673; bound 1.25 GB) |
| `b1-2-20261030-02-track` | fetch | S5 track, 1,882,001,185 B in 188.8 s (planned 1,881,959,542; bound 2.0 GB) |
| `b1-2-20261030-03-S1` | trigger | S1; fired the convergence rule |
| `b1-2-20261030-04-fieldmodel` | field model | ESO137 field model, three rounds, E0 |
| `b1-2-20261030-06-S1` | **verdict** | S1 (nominal, sub16, rot90 at 32 channels) and the native anchored response |
| `b1-2-20261030-07-S2` | **verdict** | S2 (nominal, sub16) |
| `b1-2-20261030-09-S3` | **verdict** | S3 (nominal, sub16) |
| `b1-2-20261030-12-S4` | **verdict** | S4 (nominal, sub16, rot90 at 16 channels) |
| `b1-2-20261030-13-S5` | **verdict** | S5 (nominal, sub16) |
| `b1-2-20261030-05-posthoc` | post hoc | factor chromaticity, noise by time differences, field-model gains, model against data by baseline length |
| `-10`, `-11` | post hoc | S3, S1 with the beam sampled at the 9.2 MHz product channels |
| `-14`, `-15` | post hoc | S3, S1 with a per-antenna gain slope across each gain bin |
| `-16`, `-17` | post hoc | S3 with per-channel beam evaluation, without and with the slope |
| `-18` | post hoc | S1 at 8-channel sub-blocks (supersedes `-08`) |
| `-19` | post hoc | S4 with the model scaled to the data's amplitude by baseline band |

Committed archive: [results/b1-2-identifiability.json](results/b1-2-identifiability.json).
It holds derived numbers only, keyed by run, with the role of each run.
`closes_null` is computed from the five verdict runs.

### Noise and amplitude scales

The noise is measured from adjacent-channel pairs (frozen). *Post hoc*, it
agrees with adjacent-dump differences on the same samples to 2–15 %
(`-05-posthoc/noise-*.json`). The stored weights are off by large factors
on LUNO.

| Set | s² (X, Y) | c (X, Y) | κ = c²/s² (X, Y) | adjacent-dump s² (post hoc) |
| --- | --- | --- | --- | --- |
| S1 | 0.103, 0.087 | 0.622, 0.618 | 3.74, 4.40 | 0.110, 0.092 |
| S2 | 0.071, 0.061 | 0.624, 0.624 | 5.49, 6.42 | – |
| S3 | 0.0167, 0.0152 | 1.000, 0.999 | 59.8, 65.7 | 0.0191, 0.0176 |
| S4 | 0.512, 0.513 | 0.967, 0.889 | 1.83, 1.54 | 0.522, 0.522 |
| S5 (7 scans) | 0.510–0.512 | 0.87–1.27 | 1.47–3.15 | – |

- The ESO137 (CARACal) weights are consistent with a complex-sample
  variance of 1/w.
- The LUNO (QuartiCal) weights over-state the noise variance by 10–16× on
  1934 and 60× on 1830. The raw-weight σ in the tables shows the size of
  that error.
- The amplitude scale c on LUNO is about the K/L1 gains squared (0.79²).

### The ESO137 field model (S4, S5)

Gate **E0 passes**: final peak S/N 79.5, and the kept components carry 100 %
of the CLEAN flux. The orientation check recovers an injected point at
(0.2°, −0.1°) to the pixel. The round-1 model fits the data better than its
conjugate (χ² 1.312e10 against 1.329e10).

| Round | Gains | Dirty peak | Dirty robust σ | CLEAN iterations | Components | CLEAN flux | Positive 12″ cells |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | phase, point at centre | 0.490 | 0.0063 | 84 | 70 | 1.60 | 23 |
| 1 | phase, round-0 model | 0.487 | 0.0061 | 468 | 380 | 4.94 | 107 |
| 2 | amplitude and phase, round-1 model | 0.882 | 0.0217 | 329 | 268 | 7.33 | 157 |

The model is 157 components (7.33 units of corrected flux). All of them lie
within 0.26° of the centre:

- 82 % of the flux is within 6′;
- 0.16 units are beyond 10′;
- the brightest component is 0.38.

The half-power radius is 0.53°, so this is ESO 137-006 and little else.
The snapshot CLEAN's σ is set by PSF sidelobes. The expectation
"components across the main lobe" is therefore **not realised by the
frozen procedure**, and S4/S5 test a bright, extended source at the
pointing centre. See "Post hoc" 3 and 4 for the model's amplitude errors.

### The convergence rule (fired)

On S1 the 16-channel evaluation changed the array-common pointing σ from
18.7′ to 1.56′ (x) and from 34.6′ to 0.56′ (y), and squint by 11–45 %. That
is far over the frozen 5 %. So sub16 is the verdict evaluation for every
set, as the rule says. On S4 the change is 30–49 % for common pointing,
under 1 % for everything else.

### Verdict tables (σ in the direction's unit; primary sky arm; calibrated noise)

Columns:

- **ρ**: the span fraction.
- **call**: the frozen rule on sub16.
- **σ nominal, ρ nominal**: the 32-channel evaluation.
- **σ family**: the family-marginal σ.
- **σ raw w**: σ with the stored weights.
- **anchored**: the median and maximum over gain bins of the relative
  station step per 1′ or per 1 % (diagonal gains, sky fixed).

Thresholds: 0.3′ for pointing and squint, 0.005 for width and ellipticity,
and ρ ≥ 0.01.

**S1, PKS 1934−638, four stations** (`-06`): nothing is constrainable.

| Direction | σ | ρ | call | σ nominal | ρ nominal | σ strict | σ family | σ raw w | anchored |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| pointing x (′) | 1.56 | 0.031 | no | 18.7 | 0.0026 | 1.66 | 1.71 | 3.08 | 1.5e-4, 1.2e-3 |
| pointing y (′) | 0.564 | 0.075 | no | 34.6 | 0.0012 | 0.758 | 0.749 | 1.17 | 2.5e-4, 8.8e-4 |
| log-width | 0.297 | 0.016 | no | 0.299 | 0.016 | 0.601 | 0.345 | 0.601 | 4.7e-5, 1.4e-4 |
| ellipticity | 0.308 | 0.028 | no | 0.309 | 0.028 | 0.383 | 0.367 | 0.622 | 2.6e-5, 1.0e-4 |
| squint x (′) | 1.46 | 0.066 | no | 1.64 | 0.059 | 1.48 | 1.66 | 2.93 | 7.5e-5, 5.9e-4 |
| squint y (′) | 0.922 | 0.091 | no | 1.67 | 0.050 | 1.03 | 1.24 | 1.89 | 1.3e-4, 4.4e-4 |
| per-antenna x (4) | 3.26 (median) | 0.036 | 0 of 4 | 30.4 | 0.0040 | – | 2.88 | – | – |
| per-antenna y (4) | 1.16 | 0.081 | 0 of 4 | 54.7 | 0.0017 | – | 1.03 | – | – |

**S2, PKS 1934−638, whole array** (`-07`):

| Direction | σ | ρ | call | σ nominal | ρ nominal | σ strict | σ family | σ raw w | anchored |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| pointing x (′) | 0.0821 | 0.032 | **yes** | 0.385 | 0.0068 | 0.0838 | 0.0852 | 0.193 | 1.0e-4, 1.2e-3 |
| pointing y (′) | 0.0316 | 0.075 | **yes** | 0.666 | 0.0036 | 0.0317 | 0.0358 | 0.0792 | 3.0e-4, 1.0e-3 |
| log-width | 0.00537 | 0.068 | no | 0.00537 | 0.068 | 0.0168 | 0.00768 | 0.0131 | 2.7e-5, 1.4e-4 |
| ellipticity | 0.00721 | 0.067 | no | 0.00722 | 0.067 | 0.0163 | 0.0103 | 0.0176 | 2.1e-5, 1.1e-4 |
| squint x (′) | 0.0357 | 0.148 | **yes** | 0.0365 | 0.144 | 0.0357 | 0.0364 | 0.0867 | 5.2e-5, 6.0e-4 |
| squint y (′) | 0.0404 | 0.118 | **yes** | 0.0524 | 0.091 | 0.0404 | 0.0457 | 0.0994 | 1.5e-4, 5.0e-4 |
| per-antenna x (53) | 0.177 (min 0.149) | 0.130 | **52 of 53** | 0.187 | 0.123 | – | 0.176 | – | – |
| per-antenna y (53) | 0.177 (min 0.147) | 0.111 | **52 of 53** | 0.271 | 0.073 | – | 0.176 | – | – |

The S2 per-antenna call **rests on the frozen noise calibration**. With the
stored weights the median σ is 0.43′ and 0.44′, and no antenna passes.
κ = 5.5–6.4 here, and the adjacent-dump check (post hoc 2) supports it. The
S4 per-antenna calls do not depend on it: with the stored weights they are
0.083′ and 0.093′, and 60/60 pass.

**S3, PKS 1830−211, point model** (`-09`):

| Direction | σ | ρ | call | σ nominal | ρ nominal | σ strict | σ family | σ raw w |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| pointing x (′) | 0.206 | 0.031 | **yes** (alone only) | ∞ | 0 | 0.206 | 0.444 | 1.60 |
| pointing y (′) | 0.0760 | 0.076 | **yes** | ∞ | 0 | 0.0760 | 0.109 | 0.612 |
| log-width, ellipticity | ∞ | – | no (no signature at the centre) | ∞ | – | ∞ | – | ∞ |
| squint x (′) | 0.412 | 0.031 | no | ∞ | 0 | 0.412 | 0.889 | 3.20 |
| squint y (′) | 0.152 | 0.076 | **yes** | ∞ | 0 | 0.152 | 0.217 | 1.22 |
| per-antenna x, y (53) | 1.50, 0.601 | 0.040, 0.085 | 0 of 53 | ∞ | 0 | – | 1.49, 0.598 | – |

The 32-channel evaluation reproduces the analytic control exactly
(ρ = 0). Everything that passes on S3 comes from inside a gain interval
("Post hoc" 1).

**S4, ESO137 pilot** (`-12`):

| Direction | σ | ρ | call | σ nominal | ρ nominal | σ strict | σ family | σ raw w | anchored |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| pointing x (′) | 0.331 | 0.013 | no | 0.469 | 0.0093 | 0.332 | 0.430 | 0.437 | 2.3e-3, 4.6e-2 |
| pointing y (′) | 0.280 | 0.018 | **yes** (alone only) | 0.551 | 0.0094 | 0.281 | 0.311 | 0.352 | 2.3e-3, 3.4e-2 |
| log-width | 0.00748 | 0.065 | no | 0.00749 | 0.065 | 0.00752 | 0.00896 | 0.00965 | 1.9e-4, 2.3e-3 |
| ellipticity | 0.0135 | 0.066 | no | 0.0135 | 0.066 | 0.0147 | 0.0175 | 0.0173 | 8.5e-5, 1.4e-3 |
| squint x (′) | 0.0103 | 0.844 | **yes** | 0.0103 | 0.844 | 0.0103 | 0.0202 | 0.0133 | 1.1e-3, 2.3e-2 |
| squint y (′) | 0.0116 | 0.887 | **yes** | 0.0116 | 0.887 | 0.0116 | 0.0186 | 0.0150 | 1.1e-3, 1.7e-2 |
| per-antenna x (60) | 0.0637 (min 0.0355) | 0.812 | **60 of 60** | 0.0638 | 0.812 | – | 0.0867 | – | – |
| per-antenna y (60) | 0.0714 (min 0.0419) | 0.841 | **60 of 60** | 0.0714 | 0.840 | – | 0.101 | – | – |

**S5, ESO137 track** (`-13`): seven scan chunks, q from −65° to +78°.

| Direction | σ | ρ | call | σ nominal | ρ nominal | σ strict | σ family | σ raw w | anchored |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| pointing x (′) | 0.00555 | 0.554 | **yes** | 0.00556 | 0.553 | 0.00556 | 0.00825 | 0.00832 | 1.9e-3, 4.7e-3 |
| pointing y (′) | 0.00428 | 0.811 | **yes** | 0.00429 | 0.811 | 0.00428 | 0.00639 | 0.00651 | 2.0e-3, 3.2e-3 |
| log-width | 0.00545 | 0.064 | no | 0.00544 | 0.064 | 0.00545 | 0.0160 | 0.0082 | 1.6e-4, 2.5e-4 |
| ellipticity | 0.000553 | 0.880 | **yes** | 0.000553 | 0.880 | 0.000553 | 0.000993 | 0.000813 | 1.2e-4, 2.1e-4 |
| squint x (′) | 0.00706 | 0.871 | **yes** | 0.00706 | 0.870 | 0.00706 | 0.0111 | 0.0104 | 9.7e-4, 2.4e-3 |
| squint y (′) | 0.00761 | 0.914 | **yes** | 0.00761 | 0.914 | 0.00761 | 0.00764 | 0.0110 | 9.9e-4, 1.6e-3 |

S5 per-antenna pointing per scan chunk (sub16; nominal identical):

| Scan chunk | x: pass of 60, σ median | y: pass of 60, σ median | ρ median (x, y) |
| --- | --- | --- | --- |
| 0 (q −65°) | 60, 0.092′ | 60, 0.107′ | 0.86, 0.87 |
| 1 (−44°) | 60, 0.095′ | 52, 0.182′ | 0.85, 0.85 |
| 2 (−18°) | 60, 0.083′ | 52, 0.210′ | 0.85, 0.82 |
| 3 (+10°) | 60, 0.103′ | 57, 0.166′ | 0.87, 0.88 |
| 4 (+37°) | 58, 0.146′ | 60, 0.114′ | 0.85, 0.90 |
| 5 (+59°) | 48, 0.193′ | 60, 0.096′ | 0.84, 0.89 |
| 6 (+78°) | 56, 0.173′ | 60, 0.082′ | 0.85, 0.88 |

**Summary of the frozen verdict (sub16):**

| Direction | S1 | S2 | S3 | S4 | S5 |
| --- | --- | --- | --- | --- | --- |
| per-antenna pointing | no | **52/53 each axis** (0.18′) | no | **60/60** (0.064–0.071′) | **48–60 of 60 per scan** (0.08–0.21′) |
| array-common pointing | no | **yes** (0.08′, 0.03′; sub16 only) | **yes** (0.21′ alone only, 0.076′; sub16 only) | y alone only (0.28′; sub16 only) | **yes** (0.0056′, 0.0043′) |
| log-width | no | no (0.54 %) | no | no (0.75 %) | no (0.55 %) |
| ellipticity | no | no (0.72 %) | no | no (1.35 %) | **yes** (0.055 %) |
| squint | no | **yes** (0.036′, 0.040′) | y only, sub16 only | **yes** (0.010′, 0.012′) | **yes** (0.007′, 0.008′) |

So **B1 does not close null at B1-2**.

### Native anchored response (S1)

There were 6,048 calls (14 directions × 432 gain bins with four-station
samples having all four weights positive):

- 5,446 passed the guard (status 0);
- 602 returned status 3, "underidentified full curvature": bins where a
  station drops out;
- no status 6.

Where the native call passes, the diagonal part of its full-Jones delta
equals the NumPy diagonal response to **2.5e-14** relative (frozen
tolerance 1e-6). The two definitions agree, and the anchored numbers in the
tables can be read as the native response's diagonal block.

### Labelled checks

- **Frame rotated by +90°.**
  - On S1 (at 32 channels) nothing changes the call.
  - On S4 (at 16 channels) the calls are unchanged: per-antenna 60/60,
    squint yes, common pointing y alone only.
  - Width and ellipticity trade places: width σ 0.0147, ellipticity σ
    0.0074. That is expected, since a 90° rotation swaps the x/y
    ellipticity axes.
- **Receptor angles.** They are recorded, not applied: [0, 0] on LUNO and
  [−π/2, −π/2] on ESO137.
- **Per-antenna beam check on S1: not run.** The factorised survey assumes
  one beam for all antennas; see "Deviations".

### Post hoc (labelled; none of this changes the verdict)

1. **The array-common pointing on the snapshots is bandpass granularity,
   not sky leverage.**
   - With a single component (S3), every beam direction multiplies V_pq by
     a factor separable into antenna terms E_p(ν) conj(E_q(ν)). Diagonal
     gains free per channel would absorb it exactly, so ρ = 0 identically.
   - The frozen gain interval is 32 channels. What the 16-channel
     evaluation adds is the change of the beam's on-axis gradient within an
     interval.
   - That change is real in the product. For the centre component, the
     pointing factor changes by 7 % (1070 MHz) and 11 % (1284 MHz) between
     the two halves of a block, against 0.5 % for components 12–50′ off
     axis (`-05-posthoc/chromatic.log`).
   - It survives sampling the beam only at the 9.2 MHz product channels
     (S3 `-10`: y 0.114′, ρ 0.051).
   - Freeing a per-antenna amplitude and phase slope across each gain bin
     removes x and most of y:

     | S3 run | beam evaluation | gain slope | common pointing x | common pointing y | squint y |
     | --- | --- | --- | --- | --- | --- |
     | `-09` | sub16 | no | 0.206′, ρ 0.031 | 0.076′, ρ 0.076 | 0.152′ |
     | `-16` | per channel | no | 0.179′, ρ 0.036 | 0.068′, ρ 0.085 | 0.137′ |
     | `-14` | sub16 | yes | 0.407′, ρ 0.016 | 0.150′, ρ 0.039 | 0.301′ |
     | `-17` | per channel | yes | 1.92′, ρ 0.0034 | 0.222′, ρ 0.026 | 0.444′ |

     What remains in y with per-channel evaluation is the curvature of the
     elevation gradient across 6.7 MHz in the native channels. A
     per-channel bandpass would absorb it too.
   - On S1 the slope raises the sub16 common-pointing σ from 1.56′/0.56′ to
     2.68′/1.08′ (`-15`), and product sampling gives 1.70′/0.93′ (`-11`).
   - The same mechanism carries S2's and S4's common pointing: nominal
     fails, sub16 passes.
   - Squint and per-antenna pointing on S2, S4 and S5, and every S5 common
     direction, are **not** of this kind. They pass identically at 32
     channels.
2. **The noise scale is not an artefact of correlated channels.**
   Adjacent-dump differences give s² within 2–15 % of the adjacent-channel
   value on S1, S3 and S4. That moves σ by at most 7 %.
3. **The field model's amplitude is wrong by baseline length.** Median
   |data| / |model| (raw data, no gains) is:
   - 3.9 below 200 m;
   - 2.1 at 0.2–1 km;
   - 0.84 at 1–3 km;
   - 0.33 above 3 km.

   The merged-point CLEAN model misses the diffuse emission and
   over-predicts long baselines (`-05-posthoc/fieldmodel-by-length.json`).
   Scaling the model's visibilities band by band to the data (`-19`) makes
   S4 *more* informative:
   - per-antenna pointing σ 0.026′/0.029′ (59 and 58 of 60);
   - squint 0.004′;
   - common pointing 0.12′/0.11′;
   - width 0.26 % and ellipticity 0.49 % pass.

   So the S4 per-antenna and squint calls are not an artefact of the
   model's long-baseline excess. The width call is sensitive to the model
   (0.75 % against 0.26 %) and stays "no" as frozen.
4. **The round-2 field-model gains are degenerate on the outer antennas.**
   - 385 of 1,920 solved amplitudes lie outside 0.5–2× the median, from
     0.005 to 2.65 (`-05-posthoc/fieldmodel-gains.json`).
   - Antennas 45, 46 and 54–57 collapse to 0.03–0.15, because the round-1
     model over-predicts their long baselines.
   - This is a property of the frozen procedure (amplitude self-calibration
     against an incomplete model), and it is recorded, not rerun. The
     medians c (0.97, 0.89) are not affected materially.
   - The S4 calls sit 4–30× inside their thresholds, so a factor-2 error in
     κ cannot change them. S4's common pointing y (0.28′) and S2's width
     (0.54 %) are the near-threshold numbers.
5. **Sub-block convergence.**
   - 8-channel evaluation on S1 lowers σ by a further 6 % (`-18`).
   - Per-channel evaluation on S3 lowers it by 10–13 % (`-16`).
   - The rule's evaluation (16 channels) has therefore not converged for
     the in-interval directions of item 1. It has converged for all others,
     which do not depend on it.

### What this shows, and what it does not

- **Squint and per-antenna pointing are first-order observable** on a bright
  extended source at the pointing centre. ESO 137-006 spans a few arcmin;
  the beam gradient across it differs between antennas, and gains cannot
  absorb that. The pilot gives about 0.07′ in 3.5 min, ρ ≈ 0.8.
  - B1's expectation was the opposite (per-antenna "if at all"), because it
    reasoned from compact sources.
  - On 1934 the off-axis 2.4 % of the flux gives 0.18′ with ρ ≈ 0.12.
- **Array-common pointing and ellipticity need parallactic rotation.** The
  track gives 0.004–0.006′ and 0.055 % with ρ 0.55–0.88. Every snapshot
  gives either nothing or the bandpass-granularity signal of item 1.
- **Array-common width is not constrainable anywhere.** σ is 0.54 % on S2
  and S5, 0.75 % on S4 and 30 % on S1, with ρ 0.016–0.068. Width is
  rotation-invariant and largely absorbed by free component fluxes. B1's
  calibrator expectation ("at best array-common width") fails narrowly.
- **Not shown:**
  - whether these directions can be *estimated* without bias from real data
    (B1-3);
  - whether the holography beam is good enough at the level these σ imply.
    A 0.07′ offset changes I_b by about 2e-4 at 2′ from the centre, which
    is comparable to the product's error beam (about 1e-3) and to
    antenna-to-antenna differences (0.12–0.21 % RMS in the main lobe);
  - how a deeper ESO137 field model (sources across the main lobe) changes
    any of this.

### Deviations

- **Per-antenna beam check on S1** (frozen as a labelled check): not run.
  The factorised Gram computation (`block_normals`) uses one beam per
  component for every antenna. Per-antenna beams need antenna-dependent
  factors in every block; that is a code change for B1-3.
- **The rot90 check on S1** ran at 32 channels (it was in run `-03` before
  the rule fired). S4's ran at 16 channels.
- **The S5 track set** goes beyond B1's data list. It was named, sized and
  frozen in this protocol before any survey ran.
- Nothing else deviates from the frozen procedure. The errata above are
  facts and bookkeeping.

### Open items

- The in-interval chromatic signal (post hoc 1) has not converged at 16
  channels, and it vanishes with a per-channel bandpass. B1-3 must decide
  the gain or bandpass nuisance first.
- The ESO137 field model is the bright central source only, with
  baseline-dependent amplitude errors of 3–4×.
- The per-antenna beam check is not run.
- The LUNO weights scale (10–60× in variance) is a processing product to
  report upstream.

### What B1-3 should do given this result

1. **Re-run the survey with a per-channel diagonal gain (bandpass) nuisance
   before fitting anything.** Any direction that survives only through
   gain-interval granularity is not a pointing measurement. Expected:
   - S2/S3/S4 snapshot common pointing goes;
   - squint, per-antenna pointing and the S5 common directions stay. This
     is to be verified, not assumed.
2. **Fit only what survives:**
   - per-antenna pointing on the ESO137 sets (and S2);
   - squint;
   - array-common pointing and ellipticity on the track.

   Width is excluded.
3. **Use per-antenna holography beams** (B1-0 product, m000–m063) or treat
   per-antenna beam-shape differences as a nuisance. At σ ≈ 0.07′ the
   per-antenna pointing signal is comparable to those differences.
4. **Build a deeper ESO137 field model** before the faint-source metric
   (B1 metric 3): an image of the track, or a catalogue if the user allows
   one.
5. **Treat the track's array-common directions with care.** S5 constrains
   array-common pointing to about 0.3″ and ellipticity to 0.06 % through
   parallactic rotation. Any beam-model error that rotates with q will be
   absorbed as "pointing" or "ellipticity" at that level. Elevation-dependent
   beam shape is one such error: the holography is a 60°-elevation average,
   and S5 spans 34–60°.
6. Keep B1's frozen metrics: recovered offset against truth, held-out
   visibility error (seed 7), faint-source distortion, and cost.

### Timings (every tool run of this task)

WSL host, this branch. Wall and peak RSS from `/usr/bin/time` unless noted.

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | uv venv + install (builds the extension) | worktree | 88.4 s | 1.12 GB | `.[pointing,beam,test,imaging]` ruff maturin pip |
| 2026-10-30 | `fetch_eso137_pilot.py probe` | subset metadata, row columns, FLAG, MODEL_DATA | 14.5 s | 52 MB | 5,531,329 B |
| 2026-10-30 | `core_fetch.fetch_slice` DATA probe | 4 stations, row chunk 0 | 12.1 s | 67 MB | 105,573,706 B |
| 2026-10-30 | HEAD sizing of the track | 7 scans × 8 objects | 19.5 s | 24 MB | |
| 2026-10-30 | astropy parallactic-angle spans | 4 sets | 1.3 s | 169 MB | |
| 2026-10-30 | `fetch_eso137_pilot.py fetch` (S4) | 1,043,366,221 B | 100.5 s | 969 MB | 10.4 MB/s |
| 2026-10-30 | `fetch_eso137_pilot.py track` (S5) | 1,882,001,185 B | 189.0 s | 284 MB | 10.0 MB/s |
| 2026-10-30 | `b1_identifiability.py survey S1` (`-03`) | 192 rows × 2,048 ch, 3 variants | 196.4 s | 1.22 GB | fired the convergence rule; family-line bug |
| 2026-10-30 | `b1_identifiability.py fieldmodel` (`-04`) | 46,822 rows × 500 ch | 1,979 s | 14.4 GB | orientation check 196 s, rounds 631, 591, 555 s; 4096² images |
| 2026-10-30 | survey S1 (`-06`) | as `-03` | 226.0 s | 1.21 GB | native anchored 6,048 calls included |
| 2026-10-30 | survey S2 (`-07`) | 41,786 rows × 2,048 ch, 196 components, 2 variants | 3,064.7 s | 6.48 GB | survey 2,663 s; noise + model 365 s |
| 2026-10-30 | survey S1-posthoc (`-08`) | as S1 | 90.1 s | 1.21 GB | superseded (c = 1 bug) |
| 2026-10-30 | survey S3 (`-09`) | 15,400 rows × 2,048 ch, 1 component | 70.9 s | 2.60 GB | |
| 2026-10-30 | post hoc: chromatic factors | 3 × 32 channels | ~2 s | – | not timed |
| 2026-10-30 | post hoc: noise by dump, S1 / S3 / S4 | – | 1.9 / 429.9 / 348.2 s | 0.13 / 2.97 / 2.38 GB | per-baseline Python loop |
| 2026-10-30 | post hoc: S3 product sampling (`-10`) | | 78.9 s | 2.43 GB | |
| 2026-10-30 | post hoc: S1 product sampling (`-11`) | | 108.0 s | 0.68 GB | |
| 2026-10-30 | survey S4 (`-12`) | 46,822 rows × 500 ch, 157 components, 3 variants | 1,471.6 s | 1.95 GB | |
| 2026-10-30 | survey S5 (`-13`) | 7 × ≈ 46,700 rows × 128 ch, 2 variants | 2,261.0 s | 2.97 GB | per-scan gain solves 662 s |
| 2026-10-30 | post hoc: S3 / S1 with gain slope (`-14`, `-15`) | | 129.3 / 78.8 s | 2.56 / 1.18 GB | |
| 2026-10-30 | post hoc: S3 per channel (`-16`, `-17`) | | 175.0 / 164.3 s | 2.74 / 2.74 GB | |
| 2026-10-30 | post hoc: S1 8-channel (`-18`) | | 80.6 s | 1.21 GB | |
| 2026-10-30 | post hoc: field-model gains, model by length | | ~10 s, 5.8 s | –, 1.67 GB | |
| 2026-10-30 | post hoc: S4 tapered (`-19`) | 1 variant | 545.2 s | 1.86 GB | |
| 2026-10-30 | `b1_identifiability.py archive` | 14 runs | 0.37 s | 91 MB | |
| 2026-10-30 | pytest `tests/test_b1_identifiability.py` | 13 tests | 2.5 s | – | |
| 2026-10-30 | `bash tools/check-all.sh` | worktree | 737 s | 1.91 GB | **overall: PASS**; pytest 630 passed, 5 skipped in 153.9 s; wall includes waiting for the host lock behind two other tasks; log `outputs/b1-2-20261030-check-all.log` |

## For the coordinator

- **Shared files.** None edited. Added:
  - `research/b1-2-identifiability.md` (this file);
  - `research/results/b1-2-identifiability.json` (259 kB, derived numbers
    keyed by run);
  - `python/rang/beam_identifiability.py`, `python/rang/measures.py`;
  - `examples/fetch_eso137_pilot.py`, `examples/b1_identifiability.py`;
  - `tests/test_b1_identifiability.py` (13 tests; the measures test skips
    without astropy, which is in the `[imaging]` extra).

  No Rust: the survey is NumPy/SciPy (the S2 run is 51 min single-threaded,
  dominated by the K² sky Gram per gain bin); no `pub mod` or PyO3 change.
- **`STATE.md`**, new top entry:

  > B1-2 identifiability survey (big plan wave 3), 2026-10-30 (implemented;
  > measured; [b1-2-identifiability.md](b1-2-identifiability.md)). Protocol
  > frozen first. Which beam and pointing directions can the data
  > constrain once per-antenna diagonal gains (2 dumps × 32 channels) and
  > the sky fluxes (flux and spectral index per component) are profiled?
  > Five sets: LUNO 1934−638 chunk 0 on four stations and on the whole array
  > (CARACal lsm), 1830−211 (a point), the ESO137 pilot (subset row chunk
  > 0, fetched 1.04 GB) and a new ESO137 track set (one 3.5-min chunk of
  > tile 20 from each of the 7 scans, 1.88 GB, 160° of parallactic angle).
  > Beam: the B1-0 holography array average with analytic spline
  > derivatives. Noise: calibrated from adjacent-channel differences (the
  > LUNO weights over-state the variance by 10–60×). Field model for ESO137:
  > the stored MODEL_DATA is all zero and the subset DATA is uncalibrated,
  > so three frozen self-calibration and CLEAN rounds; E0 passes, but the
  > model is the central radio galaxy only (157 components within 0.26°).
  > The frozen convergence rule fired, so the verdict uses 16-channel beam
  > evaluation. **B1 does not close null.** Per-antenna pointing is
  > constrainable on the ESO137 pilot (60/60 antennas, σ ≈ 0.07′ in 3.5 min,
  > ρ ≈ 0.8) and per track chunk, and marginally on 1934 (52/53, 0.18′, only
  > with the recalibrated noise). Squint is constrainable on 1934 and
  > ESO137 (0.004–0.04′). Array-common pointing and ellipticity are
  > constrainable only on the track (0.005′, 0.06 %), and array-common width
  > nowhere (0.54 % against 0.5 %). The snapshot array-common pointing that passes on 1934, 1830 and the
  > pilot is the beam's chromaticity inside a 32-channel gain interval: a
  > per-channel bandpass removes it exactly on the 1830 point (post hoc).
  > Native anchored response: 5,446 of 6,048 calls pass; it agrees with
  > NumPy to 2.5e-14. Next: B1-3, which first re-runs the survey with a
  > per-channel bandpass nuisance and per-antenna beams, then fits only the
  > surviving directions against both baselines.
- **`research/README.md`** index entry:

  > New, 2026-10-30: B1-2, [identifiability](b1-2-identifiability.md):
  > per-antenna pointing and squint are constrainable on ESO137 (0.07′ and
  > 0.01′ in 3.5 min) and marginally on 1934; array-common pointing and
  > ellipticity only on a 7-scan track; width nowhere; snapshot common
  > pointing is bandpass granularity; B1 continues to B1-3.
- **`big-plan.md`**, wave 3: "B1-2 done 2026-10-30 (`b1-2-identifiability.md`):
  not null. Constrainable on the frozen rule: per-antenna pointing and
  squint (ESO137, 1934), array-common pointing and ellipticity (ESO137
  track); width nowhere. B1-3 starts with a per-channel-bandpass rerun of
  the survey and per-antenna beams, then pointing self-calibration and the
  rang method on the surviving directions. It needs a deeper ESO137 field
  model (track image, or a catalogue: user decision)."
- **`tool-timings.md`**: the rows of the timings table above.
- **Upstream observations, RATT** (for `upstream-notes.md`; candidates to
  file in the RATT data stores' tracker):
  - *ESO137 `ms1_target_subset.zarr`* (ratt-public-data):
    - MODEL_DATA is identically zero (row chunk 0; 61 MB for the column);
    - DATA is uncalibrated: antenna-dependent XX–YY phases up to 1.9 rad,
      and no CORRECTED_DATA in the subset. This is worth documenting for
      users who image it directly;
    - every string column (ANTENNA/NAME, FIELD/NAME, FEED/POLARIZATION_TYPE,
      …) is a pickle-filtered object array, so reading names means
      unpickling remote data. json2 or vlen-utf8 would be safe;
    - FEED RECEPTOR_ANGLE is −π/2 for both receptors (LUNO has 0 for both).
  - *LUNO calibrator stores*: WEIGHT_SPECTRUM over-states the noise
    variance by 10–16× (1934, MAIN_1) and 60× (1830, MAIN_2). This was
    measured from adjacent-channel and adjacent-dump differences, which
    agree to 2–15 %. It extends C1's factor of about 5.6 for the closure
    noise.
  - caracal-pipeline, saopicc: nothing new.
- **Upstream observations, non-RATT** (for `non-ratt-observations.md`):
  - *SARAO holography release*: the array-average beam's on-axis gradient
    changes by 7–11 % between the halves of a 6.7 MHz interval at
    1070–1284 MHz, so the beam centroid has real frequency structure at
    that scale. This is informational: it matters to anyone solving
    pointing with coarse bandpass intervals.
  - *astropy 8.0.2*: none (the frame-rotation subtlety is documented here,
    not a bug).
- **Ignored output directories** (none committed; ESO137 is CC BY 4.0, the
  holography CC BY-NC 4.0):

  | Dir under `outputs/` | Size | Keep? |
  | --- | ---: | --- |
  | `b1-2-20261030-01-pilot` | 996 MB | yes, until B1-3 (refetch 100 s) |
  | `b1-2-20261030-02-track` | 1.8 GB | yes, until B1-3 (refetch 190 s) |
  | `b1-2-20261030-04-fieldmodel` | 193 MB | yes (components, gains, three 4096² FITS) |
  | `b1-2-20261030-00-probe-data` | 102 MB | can be deleted |
  | `b1-2-20261030-00-probe`, `-00-probe-track`, `-05-posthoc` | 5.8 MB | keep (scripts and logs) |
  | `b1-2-20261030-03-S1` … `-19-S4-posthoc-taper` (survey runs, `.log`, `.time`) | about 8 MB | keep (`survey.json` per run) |
  | `b1-2-20261030-check-all.log` | small | keep |
- **User items.** Whether to allow an external catalogue (SUMSS, RACS) for
  the ESO137 field model in B1-3: the protocol allowed only MODEL_DATA or
  an image.
- **Scratch.** `/home/gijsm/Build/tmp/20261030-b1-2/` is deleted. The probe
  and post-hoc scripts were copied into `outputs/b1-2-20261030-00-*` and
  `-05-posthoc` first.
