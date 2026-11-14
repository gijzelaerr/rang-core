# E2-B misses: diagnosis and proposed arms

Status, 2026-11-14: **diagnosis from code and archived numbers only; no new
measurement was run** (the host was held by E2-A's timed run). Every arm below
is **proposed**, not run. The frozen E2-B arm stays the record
(`research/e2-acceptance.md` section 6, on branch `fp-e2-acceptance`), and
nothing here changes it.

Sources:
- The E2-B archive is on branch `fp-e2-acceptance` at `8a8752d`, not on main.
  - `R` = `research/results/e2-acceptance/e2b/frozen/`; raw outputs in
    `D:\rang\outputs\e2-20261111-20-e2b`.
  - `RA` = `.../e2b/amended/`; raw outputs in
    `D:\rang\outputs\e2-20261112-21-e2b-amended`.
- Code is cited at the wheels that ran:
  - frozen arm: `b2d80dc`, the protocol-freeze commit 6.4 builds from;
  - amended arm: `50ba873`.
  - Line numbers are at those commits. Main has since moved (`parang_flags`,
    xf-avg-fix).
- Post hoc reads made for this note, with scripts and outputs in
  [results/e2b-misses/](results/e2b-misses/):
  - `cells_tables.py` → `cells-tables.json`: rang's B, Df and Xf flags at the
    2b cells, read from three tables of the frozen run;
  - `j1830_vector.py` → `j1830-vector.json`: 1830−211 as a polarisation
    vector, from `rows-j1830.json`.

Labels used below:
- **M**, measured: an archived number, or a read of a frozen file or table.
- **I**, inferred: a mechanism that fits the numbers and the code but was not
  isolated by a measurement.

## 0. Summary

| Miss (gate as frozen) | Most likely cause | Class | Evidence | Proposal |
| --- | --- | --- | --- | --- |
| 2b CASA applycal: 42 / 40 cells over class C, max 25.6 / 25.2 eps | float32 rounding in CASA's 8-term apply, concentrated where B or Df solutions are flagged and bridged across channels | tolerance (the 11 eps bound was measured on a shorter chain and about 1,000× fewer cells), possibly an interpolation difference in rang | I (enrichment M) | arm A1: localise per term; tolerance stays |
| 3b Gpol: 0.124° (amended), 0.278° (frozen), limit 0.1° | the phase-only estimator weights data differently: CASA `w\|R\|²` after `enforceAPonData`, rang `w\|M\|²`; and `average_freq` averages data and model separately, while CASA divides by the model first | convention or definition (estimator) | code M, effect I | arm A3: port CASA's weighting behind a key |
| 3b fcal and gcal K/G/B composites: 1.14e-3 / 1.12e-3 against 7e-4 | CASA's K, G, B solved on different inputs: rang's extend flags (added after rang's K, G, B) and WEIGHT_SPECTRUM, where rang used unit weights | scorer or oracle input (A0 rule 3) | inputs M, size I | arm A2: matched inputs, 2×2 |
| 3c as committed | oracle imaged with MS weights; rang `-unit-weights` | scorer | M (7.1, argv) | none; the matched reading replaces it as the diagnostic, while the frozen reading stays the record |
| 3c matched: dirty L∞ 1.2e-3 to 3.5e-3 | both gridders at ε 1e-4; the 1e-6 bound needs ε ≤ 1e-6 | protocol or tolerance | I (inner two-thirds 2.2e-5 to 3.0e-5 M) | arm A4: dirty images at ε 1e-6 |
| 3c matched: compact median 0.9942; off-source \|model\| 1.67, 2.27 | no clean mask in either arm (A0 rule 6 asks for 5σ), because rang refuses a mask on joined IQUV | rang limitation (GeMClean) plus algorithmic | refusal M, effect I | fix the mask, then arm A5 |
| 1830−211 \|Δχ\| up to 13° | p is 0.02–0.06 %, so χ amplifies a ΔP/I of 6e-5 to 7e-4 | tolerance (no p floor) | M | owner: limitation; vector measure reported beside |
| Transfer χ (\|χ − 33.1°\| ≤ 7°) | receptor angle −90° wrong for LUNO (post hoc, chi-offset), plus ionospheric RM | configuration or convention plus physical | chi-offset: "cause not found" under its rule; post hoc reading I | owner (chi-offset 10.1, 10.2) |
| Rang leakage 0.302 % (CASA 0.298 %) | X/Y amplitude drift between dev scan 2 and scan 18 under the phase-only per-scan G that 7.1 chose; rang − CASA is 0.004 points | physical plus recipe choice | M | owner: limitation; the ap-G reading (0.026 %) stays beside |

**No miss is shown to be a rang bug.** Two have a rang-side component:
- the Gpol estimator differs from CASA's in two coded places (section 2);
- GeMClean cannot mask joined IQUV images (section 4).

One is open to a rang interpolation difference: gate 2b (section 1).

## 1. Gate 2b, CASA applycal against rang's apply (class C)

Measured (`R/g2b-applycal.json`, `R/g2b-applycal-cells.json`,
`RA/g2b-applycal.json`):
- Frozen arm:
  - 42 of 408,827,131 compared cells are over (1.0e-7), max 25.6 eps of the
    cell maximum;
  - flags exact; 0 non-finite.
- Amended arm: 40 cells, max 25.2 eps.
  - Its cell list was not written: only the frozen arm has `g2b-applycal-cells.json`.
- Where the frozen cells lie:
  - field 1 (1934−638, scan 18): 30; field 2 (1830−211): 12.
  - Channel 1879: 22, all on field 1.
  - Baseline (35, 55): 17 of the 42. It is over in 17 of its 75 scan-18
    integrations, at channel 1879 (16) and 1878 (1).
  - Every channel is an RFI band:
    - 1862–1879 = 1245–1249 MHz (GLONASS L2);
    - 3331–3677 = 1552–1624 MHz (GPS / GLONASS L1, Iridium);
    - 322, 925, 1182 = 923, 1049, 1103 MHz (GSM, DME / ADS-B).
  - 29 of the 42 are over on the cross hands only.
  - On field 1 the over cells have cell maxima of 14–16 Jy (1934−638's I).
    The over correlations are cross hands of 0.15–1.2 Jy: an absolute error
    of 11–13 eps × 15 Jy, about 2e-5 Jy.
- Rang's solutions there (`cells_tables.py`, rang's frozen tables):
  - 30 of the 42 cells have B or Df flagged at that channel on one of the two
    antennas, so the apply bridges the solution in frequency.
  - For comparison, 43 % of all (antenna, channel) pairs have B or Df flagged
    (`base_rate_*`; this counts channels whose data are flagged too, so it
    is an upper reference, not the rate among compared cells).
  - At channel 1879, antennas 35, 15, 16, 17 and 5 have B flagged (run of 2
    channels). 35, 55, 15, 16 and 17 have Df flagged (run of 4–6).

The two implementations:
- **Rang** (`core/src/cal/apply.rs`, `b2d80dc`):
  - interpolates in float32, as CASA does (`fn track` at line 363,
    `resample_freq`);
  - then applies every term in **float64** and rounds once
    (`od[...] = v[k].re as f32`, line 808).
- **CASA's VisCal** applies each Jones in float32 `Complex`. The chain is B,
  K, G, Gpol, Kcross, Xf, Df, then P. P mixes the 15 Jy parallel hands into
  the cross hands, so every float32 rounding of XX and YY lands in a 0.4 Jy
  cross hand.

Diagnosis (I):
- Rounding accumulation over the long chain explains the size of the excess.
  The class C limit of 11 eps (A0 6.2) is the maximum measured by DF-IO
  (10.3 eps) on K, G, B, T and Df only, over about 352k cells
  (`research/dfio-formats.md` line 365). E2-B has three more terms, P, and
  about 1,160× as many cells, so a tail above 11 eps is expected.
- Rounding alone does not explain the clustering. Baseline (35, 55) at
  channel 1879 recurs in 17 integrations, and the cells are enriched in
  bridged solutions (30 of 42, against at most 43 %). That points to the
  frequency bridge of a flagged solution:
  - rang does it in mixed precision
    (`(f64::from(y[i]) + frac * f64::from(...)) as f32`,
    `apply.rs` `resample_freq`);
  - CASA's `CTPatchedInterp` does it in float32.
  - An ulp of a bridged parameter is too small (|d| ≈ 0.03) to give 2e-5 Jy
    by itself. A different choice of neighbour or of phase unwrap would give
    more. Which of the two it is is not known.
- 12 of the 42 cells have no flagged solution, so bridging is not the only
  route.

Classification: tolerance, possibly with an interpolation difference (I).
**Not a writer or schema bug.** Flags are exact, and casacore, CASA, WSClean
and dask-ms read everything (gate 2b's other rows met). A0's "blocks release"
reason for gate 2 assumes one.

**Proposed arm A1 (seen; localisation, no tolerance change).**
- Hypothesis: every over cell is explained by float32 accumulation in CASA's
  apply, with no difference in any term's interpolated value beyond 2 float32
  ulps.
- Data: the 42 frozen cells' rows, from `D:\rang\data\e2-b\e2b.ms`, copied
  into a small MS (about 40 rows × 4,096 channels).
- Settings:
  - CASA 6.7.6.14 `applycal` of rang's frozen tables, cumulatively: B; B+K;
    … ; all + P. Same interp as 2b.
  - Against it: rang's library apply with the same subsets (`cal_apply.apply`)
    in float64, and a float32 emulation script that rounds after each term.
  - Per term, the interpolated parameter as CASA applies it (`applycal` of
    that term alone to unit parallel-hand data), against rang's interpolated
    value for the same cell (`cal_apply.apply`, `direction='corrupt'` on
    unit data).
- Decision rule:
  - If every term's interpolated value agrees within 2 ulps and the float32
    emulation reproduces CASA within 2 eps of the cell maximum on all 42 cells,
    the miss is rounding. Report it as a documented limitation. The owner
    decides whether 2b's class C is read on rang's float64 output.
  - Otherwise the first term whose interpolated values differ by more than
    2 ulps is a rang difference; fix it.
- Frozen tolerance: class C as A0 (11 eps). Not loosened.
- Cost: under 0.2 CPU-hours; a 1 GB copy.

## 2. Gate 3b Gpol phase (class B: median ≤ 0.1°)

Measured:

| Reading | Median | p95 | Source |
| --- | --- | --- | --- |
| frozen | 0.278° | 2.17° | `R/g3b.json` |
| amended (`average_freq`) | 0.124° | 0.94° (max 1.21°) | `RA/g3b.json` |
| LUNO dev, without / with the key | 0.250° / 0.108° | – | `e2-average-freq.md`, `e2-average-time.md` 4.2 |

What the LUNO dev runs settled (M, `e2-average-time.md` 4.2):
- Not the refant gauge, the weights, the model column or the time averaging.
- The difference is per antenna: nearly constant in time and equal in both
  hands.
- It grows with distance from the centre: 1.0–3.0° on m049, m055–m059, m062
  and m063.

Two coded differences from CASA's estimator (code M, effect I):
1. **Phase-only weighting.**
   - Rang's `phase` kernel is QuartiCal's (`core/src/cal/diag.rs`, `b2d80dc`,
     lines 45–48 and 388–397). It scales each datum to the model's amplitude
     and keeps its weight `w`, so a datum's phase enters with weight `w|M|²`.
   - CASA's `G 'p'` first divides by the model, with weight `w|M|²`
     (`divideCorrByModel`). Then `enforceAPonData` divides each datum by its
     amplitude and multiplies its weight by `amp²`
     (`research/c1-calibration-chain.md` line 125, read from CASA's source).
     The net weight is `w|R|²`.
   - For a point model of a source partly resolved on the long baselines
     (`e2-average-time.md` 4.2's reading of 3C 286), |R| < |M| there. CASA
     down-weights the outer antennas' baselines more than rang does, so the
     structure phase splits differently among the antennas. That fits the
     signature: outer antennas, constant in time, both hands.
2. **The order of averaging under `average_freq`.**
   - `cal_gain.frequency_averaged` (`50ba873`, lines 658–675) averages data
     and model separately over the channels, `Σw R / Σw` and `Σw M / Σw`.
   - CASA divides by the model per channel, then averages: `Σ w M* R / Σ w|M|²`.
   - The two weight the band differently wherever R/M varies over the band.
     That is the case for the same source structure and for 3C 286's
     spectrum, 18.3 to 13.7 Jy across the band (receipt, `stokes_i_jy`).
   - The key took the miss from 0.278° to 0.124°, so band weighting is a
     dominant part. The rest is consistent with items 1 and 2.
3. Inherited (I): Gpol pre-applies K, G and B, and CASA's K, G and B differ
   from rang's by the composite miss of section 3 (B phase median 0.062°).
   Some of E2-B's 0.124° above LUNO's 0.108° may come from there.

Classification: convention or definition of the estimator, not a bug.
Rang's estimator is QuartiCal's, which the class A gate checks.

**Proposed arm A3 (seen; fix behind a key).**
- Code: `calibrate.casa_phase_weights` (default false, off byte-identical).
  For `calmode 'p'` it divides by the model per channel, normalises each
  datum to unit amplitude with weight `w|R|²` (CASA's `enforceAPonData`),
  and, with `average_freq`, averages the model-divided data.
- Validation first, on development data:
  - LUNO dev (`D:\rang\outputs\chi-offset-20261113-03-luno-s1\base\luno4.ms`,
    the only local copy of scans 1-2; read-only);
  - plus a simulated resolved source (A1 generator, a two-component 3C 286),
    where the CASA and rang estimators must agree within class B.
- Hypothesis: with the key, Gpol meets class B (median ≤ 0.1°) on LUNO dev
  and on E2-B scan 17.
- E2-B data: scan 17 with the frozen arm's flags after calibrate. Gpol
  re-solved by the library call the chain makes (`cal_chain.chain_terms`),
  K, G, B pre-applied from the frozen tables. CASA's Gpol from the 3b run.
- Decision rule:
  - Met on both: the key becomes the E2 configuration's for the next unseen
    leg (E2-A has no polcal, so E3 or the reserve).
  - Met on LUNO only: documented limitation, with the per-antenna table.
- Frozen tolerance: class B Gpol median ≤ 0.1°.
- Cost: code about half a day. LUNO about 0.5 CPU-hours, E2-B Gpol about
  0.3 CPU-hours, the simulation about 0.5 CPU-hours.

## 3. Gate 3b composites (class B: median ≤ 7e-4, p95 ≤ 3e-3)

Measured:

| Term | Frozen and amended | LUNO dev |
| --- | --- | --- |
| fcal K G B composite | median 1.14e-3, p95 1.52e-2, max 0.12; 0 flags differ | 4.5e-5, p95 2.2e-3 (met) |
| gcal K F B composite | median 1.12e-3, p95 1.51e-2 | – |
| B alone (reported) | relative median 1.15e-3, p95 7.0e-3, phase median 0.062°; 5,242 solution flags differ | relative 2.6e-3, but the composite was 4.5e-5 (K, G, B traded a gauge there) |
| G, Gsec, F alone | 1.8e-4, 3.7e-4, 2.4e-4 | – |

Both composites share K and B and agree to 2 %, and `average_freq` (which
does not touch K and B) moved neither. So the difference is in B (M).

**The CASA arm's inputs differ from rang's** (M, from the scripts and the run
summary):
1. **Flags.**
   - The frozen pipeline inserts `extendflags` before the polcal solves,
     after K, G and B (`core_pipeline.py` line 1572, `b2d80dc`). It covers
     fields 0 and 1, so 1934−638 is included.
   - In this run it added 33,362,888 flags: 2,497,588,404 → 2,530,951,292,
     2.4 % of the unflagged cells of fields 0 and 1
     (`rang-run/calibrate/summary.json`, step `extendflags`).
   - CASA's copy carries rang's FLAG *after* calibrate. CASA's K, G and B
     therefore saw those flags, and rang's did not. `e2_casa3b.py`'s
     docstring states it.
   - The LUNO dev validation ran with "no `extendflags` (neither arm)", the
     same flags on both sides (`e2-average-time.md` line 77), and met at
     4.5e-5.
2. **Weights.**
   - CASA's 3b arm solves with WEIGHT_SPECTRUM; rang uses unit weights
     (e2-acceptance 7.1, "Weights in 3b"). A0 rule 3 asks for uniform
     weights in every arm.
   - On `e2b.ms`, WEIGHT_SPECTRUM spans 0.13–0.17 in one scan and 1.1–17 in
     others (7.1). On LUNO dev it varied 2–4 %
     (`e2-average-time.md` 4.2).

Diagnosis (I): a noise-level difference in B from solving on about 2 %
different data, with different weights. The dev pass and the E2-B miss with
the same code fit both causes, and this note cannot separate them.

Classification: oracle input mismatch (scorer side), not rang.

**Proposed arm A2 (seen; matched inputs, 2×2).**
- Hypothesis: with CASA's K, G, B (and Gsec, F) solved on rang's own solve
  inputs, both composites meet class B.
- Data: a CASA copy of `D:\rang\data\e2-b\e2b.ms` (restored; 2a met),
  carrying FLAG = rang's flag-stage version (`rang_calibrate_*`, identical in
  both arms, 7.1).
- Settings: `e2_casa3b.py`'s K, G, B, Gsec and F calls, in 4 cases:
  - flags {flag-stage, after-calibrate} × weights {WEIGHT_SPECTRUM,
    `initweights(wtmode='ones')`};
  - `minsnr` 3, `minblperant` 4 as now (rang's chain uses 3.0, `cal_chain.py`
    line 80).
- Scored by `e2_score3b.py`'s composite code against the frozen rang tables.
- Decision rule:
  - The matched case (flag-stage, ones) meeting class B on both composites
    closes the miss as an oracle input error. The other three cases attribute
    it.
  - If the matched case misses, B is an estimator difference: open a B task
    under C2c.
- Frozen tolerance: class B, 7e-4 / 3e-3.
- Cost: 4 × K, G, B, Gsec, F on scans 18-20 in CASA, about 2 CPU-hours and
  1.5 h wall. The copy is about 60 GB on D: (600 GB free, 7.4).

## 4. Gate 3c (images against WSClean)

**As committed** (M, 7.1):
- The oracle imaged with WEIGHT_SPECTRUM; rang images with `-unit-weights`
  (`data.weights: uniform`). Found from the two argv lists before any 3c value
  was read.
- This is a scorer error. It explains only the gap between the as-committed
  and matched readings. The matched reading is the diagnostic; the
  as-committed one stays the record.

**Matched** (`R/g3c-matched.json`, `RA/g3c-matched.json`). It also misses,
measure by measure:

| Measure | Matched (frozen / amended) | Limit | Cause | Class |
| --- | --- | --- | --- | --- |
| Dirty L∞/peak | 3.5e-3, 2.9e-3, 1.2e-3 (both arms); inner two-thirds 3.0e-5, 2.4e-5, 2.2e-5 | 1e-6 | both gridders at ε 1e-4 (`image.wgridder_accuracy` default 1e-4, `core_config.py` line 361 at `b2d80dc`; WSClean 3.7's default). A0's 1e-6 was measured at matched higher accuracy (6.5e-8 to 2.2e-7, `gemclean-heldout.md`). The excess sits at the edges, where the gridder's error is largest; the inner value is at ε | protocol or tolerance (I) |
| Compact sources, median | 0.9942 / 0.9946 (scatter 0.97 % / 1.07 %) | within 0.5 % | dirty images agree to 2–3e-5 inside, so calibration and gridding are not it. The 0.5–0.6 % sits in deconvolution or restore | algorithmic (I) |
| Off-source \|model\| | 1.27, 1.67, 2.27 / 1.30, 1.66, 2.23 | ≤ 1.6 | **no clean mask in either arm.** A0 rule 6 requires a 5σ automatic mask. E2-B dropped it because rang refuses a mask on joined IQUV (`core_config.py` lines 1315–1319 at `b2d80dc`: "masks take one polarisation"; `e2b.yaml` header). Unmasked, the two cleaners put flux off-source differently. The dev reading already gave 1.58 and 3.16 (7.1) | rang limitation (GeMClean, G4) plus algorithmic (I) |
| Δα, unpolarised QUV | met | – | – | – |
| Q/Q₀ | not checked | – | – | – |

**Proposed arm A4 (seen; dirty L∞ at the accuracy the bound was measured at).**
- Hypothesis: at ε 1e-6 in both imagers, dirty L∞/peak ≤ 1e-6 on all three
  fields.
- Data: RANG_CORRECTED_DATA and rang's FLAG after apply on
  `D:\rang\outputs\e2-20261111-20-e2b\casa\e2b.ms`. Those columns are
  untouched by the 7.4 cases, which wrote CORRECTED_DATA and E2_XFER.
- Settings: gate 3c's geometry, unit weights; `gemclean` and WSClean 3.7
  `-niter 0` at `-wgridder-accuracy 1e-6`, double precision.
- Decision rule: met on all three, the dirty miss was the protocol's ε. If
  not met, a gridder difference: open a G task.
- Frozen tolerance: 1e-6.
- Cost: about 1 CPU-hour.

**Fix, then arm A5 (seen).**
- Code (GeMClean, G4 follow-up): an automatic mask from Stokes I, applied to
  every joined polarisation, as WSClean does with `-join-polarizations`.
- Then both arms at A0 rule 6: `-auto-mask 5`, threshold 3σ, matched weights,
  3 fields.
- Hypothesis: compact median within 0.5 % and off-source ratios ≤ 1.6.
- Decision rule: met → limitation closed. Not met on off-source → GeMClean's
  deconvolution default (G7) is a finish-line item.
- Frozen tolerances: A0 3c.
- Cost: code 1–2 days (with its own test against WSClean on the fixture);
  imaging about 4 CPU-hours.

## 5. 1830−211 row (|Δχ| ≤ 1°)

Measured, per 100 MHz bin, frozen arm (`j1830-vector.json`; amended within
2 %):

| Bin (GHz) | Unflagged | p (%) | ΔP/I | \|Δχ\| |
| --- | --- | --- | --- | --- |
| 1.0 | 0.78 | 0.022 | 6.1e-5 | 4.4° |
| 1.1 | 0.43 | 0.030 | 8.1e-5 | 5.5° |
| 1.2 | 0.25 | 0.037 | 8.4e-5 | 0.65° |
| 1.3 | 0.86 | 0.038 | 2.9e-5 | 2.1° |
| 1.4 | 0.69 | 0.041 | 1.7e-7 | 0.01° |
| 1.5 | 0.30 | 0.060 | 6.6e-4 | 13.2° |
| 1.6 | 0.61 | 0.038 | 6.0e-6 | 0.36° |

- I agrees within 2.5e-4, and |Δp| ≤ 0.062 points (met).
- |Δχ| is bounded by ΔP/(2p).
  - At p = 0.03 %, a 1° limit means ΔP/I ≤ 1.0e-5. That is 100× tighter than
    Df's class B median (1e-3), which this ΔP inherits.
  - The 13° bin is 1.5–1.6 GHz: 30 % unflagged (GPS and GLONASS L1), with
    ΔP/I 10× the other bins.
- Classification: tolerance. A0's row has no polarisation floor, and a
  source at 0.03 % has no defined χ at this precision.
- Proposal: no arm can meet 1° without loosening it.
  - Report ΔQ/I and ΔU/I (≤ 1e-3, the Δp limit in vector form) beside the
    frozen row, never instead of it.
  - The owner accepts the χ miss as a documented limitation, or does not.

## 6. Transfer row, χ (|χ − 33.1°| ≤ 7° at 1.3–1.5 GHz)

Measured:
- χ is −2.51° in rang (frozen), −2.55° in CASA (`R/transfer/xfer17-row.json`,
  `R/transfer-casa/xfer17-row.json`); the amended arm agrees within 0.04°.
- p 9.67 % (met).

`research/chi-offset.md` 9-10 is the authority here (merged on main,
`1863f58`):
- Under its own frozen rule the result is **"cause not found"**.
- Its post hoc reading (I): LUNO's receptor angle is about 0°, not the −90°
  of CARACal's strategy that E2-B configures. Xf then forces U to the model's
  sign, and χ follows −χ₀ + 2ψ − 90° plus ionospheric RM.
- With receptor 0, χ is still 7.47° (s17) and 9.31° (s1) from 33.1°. That is
  an RM of −1.4 and −2.1 rad m⁻² (3.6° and 5.6° at 1.4 GHz) plus a constant
  −3.6°. So even the corrected configuration misses the frozen 7°.

Classification:
- convention: the configured feed angle for this product;
- physical: RM not budgeted in A0's 7°.
- Not rang: rang and CASA agree to 0.04°.

Proposal: no arm. These are the owner's decisions chi-offset 10.1 (receptor
angle for LUNO) and 10.2 (accept the RM-corrected reading, or a dated
follow-up with an RM term in the 3C 286 model). Until then, no absolute-angle
claim in v0.2.0. xf-avg-fix does not touch E2-B (one 3C 286 scan).

## 7. 1934−638 leakage (each of Q/I, U/I, V/I ≤ 0.3 %)

Measured (`R/transfer/leak18p.json`, `R/transfer-casa/`, 7.4):

| Case | Q/I | U/I | V/I |
| --- | --- | --- | --- |
| Rang, phase-only per-scan G | 0.302 % | 0.288 % | 0.053 % |
| CASA, phase-only per-scan G | 0.298 % | 0.288 % | 0.053 % |
| Scan 18's own ap G, reported | 0.025–0.026 % in all arms | – | – |

- With scan 18's own amplitudes the leakage falls about 10× in every arm. So
  the gated number is the X/Y amplitude drift between dev scan 2 and scan 18,
  carried by the phase-only G that 7.1 chose for the recipe. Leakage itself
  is not the main term.
- Rang − CASA is 0.004 points of Q/I, inside the dev Df tables' class B
  difference.
- Classification: physical (gain drift) plus a recipe choice (7.1); not rang.
- Proposal: no arm; it cannot be met without changing the recipe after
  seeing it. The owner accepts it as a documented limitation, with the ap-G
  reading (0.026 %) beside it as the leakage measure.

## 8. What was not done

- No new measurement, image, solve or CASA call.
- Read for this note:
  - rang's frozen B, Df and Xf tables;
  - the archived JSON;
  - `rang-run/calibrate/summary.json`.
- Mechanisms marked I above are not isolated. Section 3's split between flags
  and weights, section 1's interpolation and section 2's weighting each need
  their arm.
- Gate 3b's B solution-flag difference (5,242) was not attributed. CASA's
  `minsnr` and `minblperant` match rang's chain defaults, so arm A2's flag
  case should explain it.

## For the coordinator

Which misses block v0.2.0 depends on the owner's reading of finish line
point 3. "Within a tolerance written before the run" is not met for 3b, 3c
and three rows as frozen. Under A0 6.6, any E2-B rerun is "seen".
- **Blocking, need work:**
  - 3c off-source and compact median: GeMClean cannot mask joined IQUV;
  - 3b composites: oracle input mismatch, so the gate is not validly read
    until A2 runs;
  - 2b: A0 calls gate 2 release-blocking. Most likely rounding, not a
    writer bug, but unproven until A1.
- **Blocking unless the owner accepts a documented limitation:** Gpol
  (estimator convention, fixable by A3).
- **Owner decisions, no code:**
  - transfer χ (chi-offset 10.1 and 10.2);
  - 1830−211 χ (no p floor);
  - rang leakage 0.302 % (recipe and drift).

Ordered fix list. Every arm is seen, its tolerance frozen as A0, and each
runs as a shared heavy_lock job after E2-A releases the host:
1. **A2**, composites, matched CASA inputs, 2×2: about 2 CPU-hours, 1.5 h
   wall, 60 GB on D:.
2. **A1**, applycal localisation: under 0.2 CPU-hours.
3. **A4**, dirty L∞ at ε 1e-6: about 1 CPU-hour.
4. **A3**, Gpol, `casa_phase_weights` key with LUNO and simulation
   validation: half a day of code, about 1.3 CPU-hours.
5. **GeMClean joined-IQUV auto-mask, then A5**: 1–2 days of code, about
   4 CPU-hours.

The owner must decide:
1. Whether v0.2.0 may ship on E2-B gates re-read as "seen" after these
   fixes. E2-A is the remaining unseen leg, and it has no polarisation.
2. Whether the transfer χ, the 1830−211 χ and the 0.302 % leakage are
   accepted as documented limitations, with the vector and ap-G measures
   reported beside them, or need new tolerances (A0 rule 1 forbids loosening
   them without the owner).
3. The receptor angle for LUNO (chi-offset 10.1).
