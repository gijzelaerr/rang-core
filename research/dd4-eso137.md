# DD4: the catalogue-pinned DD self-calibration loop on ESO 137-006

Issue #15, fourth piece. Branch `dd4-eso137`. Owner decision 2026-11-23,
relayed by the coordinator: DD4 runs on ESO137, with an external catalogue
for the facet-centre fluxes. The same approval covers reopening beam and
pointing later. Sections 1-6 are frozen 2026-11-23, before any code that
tests them and before the catalogue was queried; later changes are dated
amendments.

Status: **partly measured 2026-11-23, setup outcome on arm O (A3, A4).**
- Rang's loop (R) and the two baselines (DI, DI0) ran.
- The oracle arm O stopped at a setup mismatch. On the two-correlation MS
  (A3), WSClean's `-diagonal-visibilities` facet image is 1.93-1.94 ×
  rang's per facet. On a four-correlation copy (A4) it is exactly half of
  that, 0.96-0.98 × rang's, and fails A1's 1e-3 control by 3.0e-2, with
  unit gains as well. WSClean's own no-facet image of the copy matches
  rang to 1.1e-7.
- So gates L and S are not read, no arm O cycle was rerun, and the gain
  over DI is provisional (section 7).

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

Run `D:/rang/outputs/dd4-20261123/run-02`. It holds `setup.json`, `C0/`,
`R/`, `DI/`, `DI0/` and `O/cycle-0` (cycles 0-4 of each rang arm), plus
`score-rang-only.json`. The archive is
[results/dd4-eso137/](results/dd4-eso137/). Host glacier, shared, rang at
8 threads.

**C0 (A1, A2): pass.** Rang's dirty image of the subset matches WSClean's to
1.1e-7 of the peak, with WSClean's Stokes I weight `min(w_XX, w_YY)`.

**Arm O: setup outcome, gates L and S not read.** Cycle 0 completed:
QuartiCal in 651 s, then WSClean's corrupted predict and facet image with
`-diagonal-visibilities` (A3).

| | value |
| --- | --- |
| gain products, median R-O difference per direction | 0 (pinned d0), 1.6e-6, 1.3e-5, 1.4e-5 |
| gain products, maximum R-O difference | 1.1e-2, 1.8e-1, 5.1e-2 |
| flags | equal (538 flagged gains) |
| best scale O/R of the flat-gain residual, per facet | 1.942, 1.929, 1.927, 1.942 |

- In cycle 0 both solvers stop at the 150 cap with a converged fraction of
  0.25, which is the pinned direction only. The maxima are on gains that
  have not converged.
- The residual images differ by close to a factor 2 in every facet,
  including the pinned d0. The difference is in WSClean's imaging, not the
  gains.
- DD2b validated the four-correlation path (7.5e-8). The diagonal-visibility
  path, which this two-correlation MS forces, has a different flat-gain
  normalisation, not yet characterised.
- Arm O was stopped after cycle 0, since its later cycles would
  deconvolve a mis-scaled residual.

**Rang arms, provisional (final cycle 4, no oracle check):**

| Measure | R (DD, d0 pinned) | DI (frozen: free, one direction) | DI0 (post hoc: DI gains only) |
| --- | --- | --- | --- |
| rms near d1 (0.97 Jy at 0.25°) | 45.1 mJy | 462 mJy | **12.7 mJy** |
| rms near d2 (98 mJy at 0.38°) | **5.0 mJy** | 151 mJy | 11.6 mJy |
| rms near d3 (83 mJy at 0.83°) | **1.5 mJy** | 260 mJy | 4.0 mJy |
| field rms | **2.0 mJy** | 118 mJy | 4.6 mJy |
| dynamic range | **675** | 234 | 304 |

- **Against the frozen DI arm:** `q` = 0.033 and DR 2.9 ×, so the reading
  would be "DD helps". But the frozen DI arm diverges, because its one free
  direction absorbs the incomplete model (A3). That reading is not
  meaningful and is not claimed.
- **Against DI0 (post hoc):**
  - `q` = 0.43 and DR 2.2 ×.
  - d2, d3 and the field are 2.3-2.7 × better.
  - d1 is 3.6 × worse. d1 sits 15′ from ESO 137-006 and is probably part
    of its extended emission, which the start model lacks, so its facet's
    gains absorb that structure. That is a post hoc guess, not tested.
- Both rang arms are far above the 31 µJy thermal expectation, so
  deconvolving the extended source is the limit here.
- In R the DD solve hits the 150 cap in every cycle (converged fraction
  0.25).

**A4 controls (2026-11-23), on the four-correlation copy:** fail, so arm O
was not rerun. Run `D:/rang/outputs/dd4-20261123/run-02/C1` and `C1-unit`;
archive [results/dd4-eso137/C1/](results/dd4-eso137/C1/).

| Control | max difference / peak | best scale WSClean/rang, facets d0-d3 | |
| --- | --- | --- | --- |
| C0′: dirty image, no facets | **1.1e-7** | 1.0000 (all) | pass |
| C1: flat-gain facet image, arm O's cycle-0 gains | **3.0e-2** | 0.973, 0.959, 0.970, 0.974 | **fail** |
| C1 with unit gains | 3.0e-2 | 0.973, 0.975, 0.969, 0.973 | fail |
| for contrast: two-correlation MS, `-diagonal-visibilities`, cycle-0 gains | 4.9e-1 | 1.946, 1.918, 1.939, 1.948 | fail |
| the same, unit gains | 4.9e-1 | 1.946, 1.951, 1.938, 1.947 | fail |

- Every facet call gridded all 30,800,924 visibilities, so the flagged
  cross hands did not drop data. A4's fallback (unflagged cross hands) was
  not triggered.
- The diagonal-visibility image is 2.000 × the four-correlation one in
  every facet, so A3's factor is a missing ½ in Stokes I on that path.
- The remaining 2-4 % is on WSClean's facet-solution path itself. It is
  there with unit gains and in the pinned facet d0, whose gains are exactly
  1, so it is not the gains or the 1/c correction. It is also not a weight
  rule: rang's facet image with `min`, harmonic, sum, `w_XX` or `w_YY`
  weights leaves 3.0e-2 in every case (`c1-weight-candidates.json`).
  WSClean's log gives a different effective visibility count on that path
  (11.87 M four-correlation and 23.74 M diagonal, against 25.32 M without
  facets). Its weighting with facet solutions therefore differs from its
  plain Stokes I weighting on this MS, which has real flags and unequal
  `w_XX`, `w_YY`. DD2b's simulations had neither.
- The diagnosis stopped there, as instructed (a short look at the
  normalisation only).

**Outcome under section 6: setup.** The oracle's facet imaging is not
comparable on a two-correlation MS without a characterised normalisation, so
no gate is read. The rang numbers above are provisional and are not a
result of this note.

**Next steps (after A4):**
1. Find WSClean 3.7's Stokes I weighting with `-apply-facet-solutions`
   (source, `gridding/msgriddermanager.cpp`), or run C1 on a copy with
   `w_XX = w_YY` and no flags, to separate the two causes.
2. Then amend: either rang's facet image adopts that weight (arm R and DI
   rerun) or the O comparison uses a matched MS.
3. Rerun arm O, read L, S and the gain over DI as frozen.

Separately, the DD solve does not converge on real data within the cap, and
d1's facet takes extended structure. Both are for the owner before any
claim.

Cost (indicative, shared host):
- rang R about 2.2 min per cycle (solve 75-90 s, image 31-41 s, 5 cycles);
- DI about 35 s per cycle;
- QuartiCal cycle 0 651 s at 8.4 GB peak;
- the A4 controls (copy, conversion, three WSClean images, rang's two
  images) about 2.2 min.

## Amendments

**A1, 2026-11-23, before any loop ran.**

*The catalogue was downloaded with the owner's yes, relayed by the
coordinator.*
- It is in `results/dd4-eso137/catalogue/`, with `QUERY.md` recording the
  URLs, the UTC times and the SHA-256 of each file.
- The primary CDS VizieR server refused the automated request and returned
  a "Page unavailable" page. The same queries were served by the CfA VizieR
  mirror, with server version V7.6.1.
- The tables used:
  - RACS-low DR1 `J/other/PASA/38.58`, its Gaussian component tables
    `gausscut` and `gaussreg` (`Fgauss`, mJy);
  - RACS-mid DR1 `J/other/PASA/41.3`, its component table `gcompsm`
    (`Ftot`, mJy).
- 339 RACS-low components fall in the image; 257 of them match a RACS-mid
  component within 10″.

*Facet directions by section 4's rule (`tools/oracles/dd4/catalogue.py`).*
Only three off-axis components qualify, which is still at least two:

| Direction | Component | ρ | `S_1043` (α) | `B` | `S_app` |
| --- | --- | --- | --- | --- | --- |
| d1 | RACS_1633-62A_8018 | 0.248° | 1.052 Jy (−1.87) | 0.918 | 0.965 Jy |
| d2 | RACS_1633-62A_8326 | 0.383° | 0.121 Jy (−1.22) | 0.813 | 0.098 Jy |
| d3 | RACS_1633-62A_7234 | 0.826° | 0.229 Jy (−0.99) | 0.361 | 0.083 Jy |

The start model holds 152 components of at least 5 mJy, 92.6 Jy apparent in
total.

*The subset* `D:/rang/outputs/dd4-20261123/sub.ms` was made with CASA 6.7.6.14
`split(spw='0:96~159', datacolumn='data', keepflags=True)` in
`rang-o-casa:6.7.6.14`.

*The Stokes I gridding weight* in rang is `4 / (1/w_XX + 1/w_YY)` over
unflagged parallel hands. Section 4 did not state it. A control C0 (both
arms' dirty image of the subset, no facets, within 1e-3 of the peak, as
DD2) is added. It must pass before gate L is read; if it fails, that is a
setup outcome.

**A2, 2026-11-23, setup. C0 failed and was diagnosed (post hoc) before any
gate was read.** C0's first run, with the harmonic Stokes I weight of A1,
differed by 5.3e-3 of the peak, against a limit of 1e-3.
- Both codes grid the same 30,800,924 visibilities. There are no
  autocorrelations, no visibilities beyond the grid, and no zero or
  non-finite unflagged data.
- So the difference is the weight. On this MS `w_XX` and `w_YY` differ
  (median ratio 1.06, 1-99 % range 0.94-1.27).
- Against WSClean's `-make-psf`, rang's PSF with each candidate weight:

  | Weight | PSF difference |
  | --- | --- |
  | harmonic | 3.3e-3 |
  | sum | 3.7e-3 |
  | `w_XX` | 7.9e-3 |
  | `w_YY` | 1.2e-3 |
  | **`min(w_XX, w_YY)`** | **4.9e-8** |

- So WSClean 3.7 grids Stokes I with the smaller of the two parallel-hand
  weights. Rang's imaging weight is now that (the solver still uses each
  correlation's own weight), and C0 is rerun.
- DD1-DD3b are unaffected, since their simulations have equal weights.

**A3, 2026-11-23, setup and a reported baseline.**

*Setup.* With facet solutions, WSClean 3.7 refuses the pilot's
two-correlation MS: "This mode requires the four polarizations to be present
in the measurement set". This happened in arm O, cycle 0, at step 3, before
any gate was read. The facet calls now pass `-diagonal-visibilities`, which
reads XX and YY and applies the solutions to each hand. That is the
per-hand correction rang applies. Arm O is restarted from a fresh scratch
copy.

*Baseline (post hoc, reported only).* The frozen DI arm (one direction,
amplitude and phase, nothing pinned) leaves a residual σ of 0.22-0.31 Jy
in cycles 0-1, against the DD arm's 2-3 mJy. With nothing pinned, the
single direction's gains absorb the incomplete start model of the extended
80 Jy source. Its verdict is read as frozen. A second baseline **DI0** is
added: one direction, pinned, so the gains stay at the publisher's DI
calibration and only the deconvolution loop runs. DI0 is reported beside
the frozen comparison and does not replace it.

**A4, 2026-11-23, setup fix, post hoc (after arm O's cycle 0, before any
gate L or S was read).** Arm O images a four-correlation copy of the
subset, so that WSClean takes DD2b's validated four-correlation path
instead of `-diagonal-visibilities` (A3), whose flat-gain facet image came
out 1.93-1.94 × rang's in every facet.
- *The copy* `sub4.ms`, made on WSL ext4 from `sub.ms` by
  `tools/oracles/dd4/to_four_corr.py`: correlations XX, XY, YX, YY
  (`CORR_TYPE` 9, 10, 11, 12). XX and YY are the subset's own data, flags,
  weights and sigmas. XY and YX hold zero data and are flagged. Their
  `WEIGHT_SPECTRUM` and `WEIGHT` follow A2's rule, `min(w_XX, w_YY)`, so
  any Stokes I weight WSClean forms from the four hands equals rang's.
- *Fallback, fixed now:* if control C0′ below shows that WSClean drops a
  visibility whose cross hands are flagged, the copy is rebuilt with XY and
  YX unflagged (still zero data, same weights). The cross hands carry no
  signal and do not enter Stokes I.
- *What uses which MS:* WSClean's corrupted facet predict, the residual
  column and the flat-gain facet image (step 3) run on `sub4.ms`, without
  `-diagonal-visibilities`. QuartiCal's solve and its per-facet model
  predicts (steps 1-2) stay on the two-correlation `sub.ms`, as in cycle 0
  (A3), since `diag_complex` uses the parallel hands only.
- *Controls before any cycle is rerun,* each within A1's 1e-3 of the peak
  over interior pixels:
  - **C0′:** WSClean's dirty image of `sub4.ms` (no facets) against rang's
    C0 image;
  - **C1:** WSClean's flat-gain facet image (`-image-pb.fits`,
    `-feather-size 0`) of `DATA` in `sub4.ms` with arm O's cycle-0 gains
    applied, against rang's `residual_image` of the same data with the same
    gains and a zero model.
  If either fails with a factor near 1.94, the outcome stays "setup".
- Arm O is rerun from cycle 0 in a fresh scratch, and gates L and S and the
  gain over DI are then read as frozen in sections 5-6. DI0 stays reported
  only (A3).
