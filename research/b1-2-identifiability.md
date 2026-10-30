# Rang B1-2: which beam and pointing directions can the data constrain? (protocol)

Protocol frozen 2026-10-30 on branch `b1-2-identifiability` (from main
`3b875e0`), before any B1-2 survey code was written. Task B1-2 of
[big-plan.md](big-plan.md) wave 3; the design it restates was frozen in
[b1-beam-pointing.md](b1-beam-pointing.md) ("B1-2: the first rang
experiment, identifiability", "Measures convention").

Status: **proposed** (this section). Results are appended below the
protocol when measured; nothing above "Measured result" changes after this
commit except through a dated, labelled amendment.

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
