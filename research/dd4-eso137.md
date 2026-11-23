# DD4: the catalogue-pinned DD self-calibration loop on ESO 137-006

Issue #15, fourth piece. Branch `dd4-eso137`. Owner decision 2026-11-23,
relayed by the coordinator: DD4 runs on ESO137, with an external catalogue
for the facet-centre fluxes. The same approval covers reopening beam and
pointing later. Sections 1-6 are frozen 2026-11-23, before any code that
tests them and before the catalogue was queried; later changes are dated
amendments.

Status: **proposed; blocked on the catalogue download** (section 3: the
download needs the owner's explicit go-ahead for the named files).

## 1. What DD4 is, and what is not claimed

DD3c's loop on real data, scored against the same loop in QuartiCal 0.2.7 +
WSClean 3.7, and against rang's direction-independent loop as the baseline.
There is no truth, so the measures are image-based (section 5).

Not claimed: a gain over the state of the art. The oracle is the same
algorithm, so any improvement over DI is DD calibration's, not rang's.
There is no beam or pointing solve, and the primary beam is used only to
turn catalogue fluxes into apparent fluxes. Nothing beyond ESO 137-006's
field is in scope.

## 2. Data (checked on disk 2026-11-23)

The ESO 137-006 pilot, `D:/rang/outputs/20261103-gemclean-heldout/real/cal2.ms`
([gemclean-heldout.md](gemclean-heldout.md) §5-6,
[imaging-floor.md](imaging-floor.md)):
- 61 antennas, 1,830 baselines, 450 × 8 s (1 h), 823,500 rows;
- 256 channels of 0.418 MHz, 989.85-1096.44 MHz;
- `DATA` already corrected by the publisher's QuartiCal DI gains;
- set A's received flags (27.8 % of cells);
- `WEIGHT_SPECTRUM`;
- phase centre RA 243.80°, Dec −60.91° (`PHASE_DIR` 4.25504, −1.06301 rad).

The rest of the E2-A ESO137 data (the target scan 10 in
`D:/rang/data/e2-a/ESO137`, 4,096 channels) is not used. It would need a
fresh DI chain, and DD4 tests the DD step.

**Subset, frozen:** channels 96-159 (64 native channels, 1029.98-1056.32
MHz, centre 1043.15 MHz), every row, no averaging. Native resolution keeps
time and bandwidth smearing at the data's own level. At 0.5° and 0.418 MHz
the bandwidth term is about 0.1 of a beam. The subset holds 52.7 M cells,
which fits the loop's in-memory arrays.

## 3. The catalogue (choice frozen; query to be run and recorded)

**Choice:** RACS-low DR1 (887.5 MHz) and RACS-mid DR1 (1367.5 MHz), the
ASKAP Rapid ASKAP Continuum Survey component catalogues.
- **Coverage:** both cover Dec −60.9°. NVSS (Dec > −40°) does not.
- **Frequency:** they bracket 1043 MHz, so each source's flux is
  interpolated in log-log between the two surveys. A spectral index assumed
  from one survey would add error.
- **Resolution:** RACS-low's 25″ and RACS-mid's about 10″ are close to
  MeerKAT's here (about 7″). SUMSS (843 MHz, 45″) blends sources.
- **Cross-check:** SUMSS (843 MHz) is reported against the interpolation,
  not used for it.

**Query, to be recorded exactly when run** (in `research/results/dd4-eso137/catalogue/`):
- VizieR cone searches of radius 1.2° about (243.80°, −60.91°), over all
  components;
- the VizieR table IDs and versions;
- the query URLs and the UTC time;
- the returned files' SHA-256 and sizes.

The files are small, of order 100 kB to 1 MB. **They are not downloaded
until the owner confirms the download** (catalogue, source and size, as
the host's rules require for any download).

**Apparent fluxes:**
- `S_1043 = S_888 × (1043.15 / 887.5)^α`, with
  `α = log(S_1367.5 / S_888) / log(1367.5 / 887.5)`, for components
  matched within 10″ between the surveys. A component found in RACS-low
  only uses `α = −0.7`.
- `S_app = S_1043 × B(ρ)`, with the Mauch et al. (2020) MeerKAT L-band
  cosine-squared power beam:
  `B(ρ) = [cos(1.189 π ρ/θ_b) / (1 − 4 (1.189 ρ/θ_b)²)]²` and
  `θ_b = 57.5′ × (1.5 GHz / 1.04315 GHz) = 82.7′`.

## 4. Facets, start model, loop (frozen)

**Directions:**
- **d0:** the phase centre (ESO 137-006 and the field near it).
- **d1-d4:** up to four off-axis components with the highest `S_app`, of at
  least 50 mJy, at 0.15° to 1.0° from the centre and at least 0.2° from
  each other and from d0.
- **Facets:** the Voronoi cells of the directions, clipped to the image
  (DD2's construction).

**Pins:**
- d0 is pinned (`G.pinned_directions=[0]`, QuartiCal's default, and rang's
  `pinned_directions=[0]`). The publisher's DI calibration stays the
  centre's reference, and d0's flux is free in the minor cycle.
- d1-d4 hold their facet-centre components at the catalogue's `S_app`
  (DD3c's rule: no peak search within ±2 pixels).

**Start model M₀:** every RACS-low component with `S_app ≥ 5 mJy` inside
the image, as point components at its nearest pixel. Fluxes are `S_app`.
Gaussian components are placed as points at their centroids. The model
does not reproduce ESO 137-006's extended emission. The cycle-0 minor
cycle builds that, unpinned, in d0.

**Grid:** 2880 × 2880 pixels of 3″ (2.4°).
- The Nyquist pixel for the subset's longest |u|, |v| (about 7.7 km at
  1056 MHz) is about 3.8″.
- WSClean runs with `-no-min-grid-resolution` and, with facets,
  `-feather-size 0`.

**Loop: DD3c's arm C.** Five major cycles plus a final solve:
- `diag_complex` DD at the frozen cap (150, 1e-7, 0.99), with 4 × 8 s
  intervals and all 64 channels per interval;
- the facet predict;
- the flat-gain facet residual image;
- the shared Högbom rule (gain 0.1; 5 σ or 1 mJy; at most 5,000 components
  per cycle; peaks at least 3 pixels inside facets; ±2 pixels around the
  pinned components excluded);
- the PSF is rang's unit-gain PSF of the subset's weights, in both arms.

**Arms:**

| Arm | DD solve | Facet predict, imaging | Directions |
| --- | --- | --- | --- |
| **R** | rang `solve_dd` | rang | d0-d4 |
| **O** | QuartiCal 0.2.7 `G.type=diag_complex`, DD, `iter_recipe=[150]` | WSClean 3.7 (`-model-pb.fits`, `-feather-size 0`) | d0-d4 |
| **DI** | rang `solve_dd` with one direction | rang, one facet (whole image) | one; nothing pinned |

The DI arm runs the same loop, with the d1-d4 components still held at the
catalogue fluxes. The only difference from R is the number of directions.

## 5. Measures and frozen tolerances

All measures are on the final cycle's flat-gain residual image (cycle 4).

- **rms near each off-axis source, d1-d4:** 1.4826 × MAD of the residual in
  an annulus of 5-40 pixels (15″-2′) around the source, facet-interior
  pixels only.
- **Dynamic range:** the peak of the final model convolved with a Gaussian
  restoring beam fitted to the PSF's main lobe, plus the residual, divided
  by the field rms. The field rms is 1.4826 × MAD of the residual over
  facet-interior pixels at least 2′ from every model component of at least
  5 mJy.

**Gate L (R against O), per cycle:** DD3's tolerances.
- Identical component lists; fluxes within `1e-5 + 1e-4 |f|`.
- Gain products within 1e-5; equal flags.
- Residual within 1e-3 of the peak.
- If the lists first differ through a tie or a near-threshold choice
  (section 4 of DD3), the outcome is "parity up to the rule". Then gate S
  is read with a tolerance of 2 %.

**Gate S (R against O, final cycle):**
- each off-axis rms ratio R/O within `[0.999, 1.001]`;
- the dynamic-range ratio within `[0.999, 1.001]`;
- with parity only up to the rule, both within `[0.98, 1.02]`.

**Gain over DI (R against DI, final cycle; decision measure):**
- `q` is the median over d1-d4 of rms(R) / rms(DI).
- **DD helps:** `q ≤ 0.90` and DR(R) ≥ DR(DI).
- **Null:** `0.90 < q < 1.05`, or `q ≤ 0.90` with DR(R) < DR(DI).
- **DD worse:** `q ≥ 1.05`.

Reported, not gated:
- the per-source rms ratios and the cycle-by-cycle measures;
- the gain amplitudes per direction (median `|g|` and its spread);
- SUMSS against the interpolated fluxes;
- the thermal expectation for the subset, prorated from heldout §5's
  15.5 µJy at 256 channels by sqrt(256/64), about 31 µJy.

## 6. Decision rule (named before any result)

- **Pass and DD helps:** L and S hold, and `q ≤ 0.90` with DR(R) ≥ DR(DI).
  This is the first real-data DD result. It is parity with QuartiCal and
  WSClean, and a gain over DI.
- **Pass, null:** L and S hold, and the gain over DI is null. The DD loop is
  ported and real, but does not help this field at this depth. This is
  consistent with floor-5's unresolved DD fits.
- **Pass, DD worse:** L and S hold, and `q ≥ 1.05`. This is recorded. The
  likely causes, catalogue flux errors moved into the gains and smearing,
  are examined post hoc.
- **Parity failure:** L or S fails. The first differing cycle and quantity
  are recorded.
- **Setup:** a tool refuses an input, the catalogue yields fewer than two
  usable off-axis directions, or memory is exceeded. This is an amendment
  before any gate is read. With fewer than two directions, the 50 mJy floor
  is lowered to 20 mJy, a choice fixed here.

## 7. Measured result

Not yet measured.
