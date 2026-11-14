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
  - The frozen run's receipt has `commit: None`, so `b2d80dc` is inferred
    from 6.4 ("the commit that carries this section").
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
| 2b CASA applycal: 42 / 40 cells over class C, max 25.6 / 25.2 eps | float32 rounding in CASA's 6- or 7-table apply plus P, clustered where B or Df solutions are flagged and bridged across channels | tolerance (the 11 eps bound was measured on a shorter chain and about 1,000× fewer cells), possibly an interpolation difference in rang | I (cell positions M) | arm A1: localise per term; tolerance stays |
| 3b Gpol: 0.124° (amended), 0.278° (frozen), limit 0.1° | the phase-only estimator weights data differently: CASA `w\|R\|²` after `enforceAPonData`, rang about `w` (derived from the kernels); and `average_freq` averages data and model separately, while CASA divides by the model first | convention or definition (estimator) | code M, net weights derived, effect I | arm A3 (after A2): port CASA's weighting behind a key |
| 3b fcal and gcal K/G/B composites: 1.14e-3 / 1.12e-3 against 7e-4 | CASA's K, G, B solved on different inputs: rang's extend flags (added after rang's K, G, B) and WEIGHT_SPECTRUM, where rang used unit weights | scorer or oracle input (A0 rule 3) | inputs M, size I | arm A2: matched inputs, 2×2 |
| 3c as committed | oracle imaged with MS weights; rang `-unit-weights` | scorer | M (7.1, argv) | none; the matched reading replaces it as the diagnostic, while the frozen reading stays the record |
| 3c matched: dirty L∞ 1.2e-3 to 3.5e-3 | both gridders at ε 1e-4, and an edge excess 12–35× ε that ε alone may not remove | protocol or tolerance, or an edge difference | I (inner two-thirds 2.2e-5 to 3.0e-5 M) | arm A4: ε scan with region profile |
| 3c matched: compact median 0.9942; off-source \|model\| 1.67, 2.27 | no clean mask in either arm (A0 rule 6 asks for 5σ), because rang refuses a mask on joined IQUV | rang limitation (GeMClean) plus algorithmic | refusal M, effect I | fix the mask, then arm A5 |
| 1830−211 \|Δχ\| up to 13° | p is 0.02–0.06 %, so χ amplifies a ΔP/I of 1.7e-7 to 6.6e-4 | tolerance (no p floor) | M | owner: limitation; vector measure reported beside |
| Transfer χ (\|χ − 33.1°\| ≤ 7°) | receptor angle −90° wrong for LUNO (post hoc, chi-offset), plus ionospheric RM | configuration or convention plus physical | chi-offset: "cause not found" under its rule; post hoc reading I | owner (chi-offset 10.1, 10.2) |
| Rang leakage 0.302 % (CASA 0.298 %) | X/Y amplitude drift between dev scan 2 and scan 18 under the phase-only per-scan G that 7.1 chose; rang − CASA is 0.004 points | physical plus recipe choice | M | owner: limitation; the ap-G reading (0.026 %) stays beside |

**Correction, 2026-11-14 (arm A1, section 9.3):** the 2b row's "float32
rounding" is not supported. Under A1's frozen rule the outcome is "rang
difference", with G as the first term over 2 ulps (2.004 ulps, 1
correlation). P (the parallactic angle) differs from CASA by 78–366 ulps on
every cell, and the class C excess appears only when P is applied (post hoc
reading). Measured and localised, not diagnosed.

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
  - Baseline (35, 55): 17 of the 42 cells, in 16 integrations of scan 18
    (one row has both channels 1878 and 1879).
  - Frequencies (M): 1862–1879 = 1245–1249 MHz; 3331–3677 = 1552–1624 MHz;
    322, 925, 1182 = 923, 1049, 1103 MHz. That these are RFI bands
    (GLONASS L2; GPS and GLONASS L1, Iridium; GSM, DME and ADS-B) comes from
    the known allocations, not from this data (I).
  - 29 of the 42 are over on the cross hands only.
  - On field 1 the over cells have cell maxima of 14–16 Jy (1934−638's I).
    The over correlations are cross hands of 0.15–1.2 Jy: an absolute error
    of 11–13 eps × 15 Jy, about 2e-5 Jy.
- Rang's solutions there (`cells_tables.py`, rang's frozen tables):
  - 29 of the 42 cells have B or Df flagged at that channel on one of the two
    antennas, so the apply bridges the solution in frequency. One more,
    (38, 54) at channel 3466, has only Xf flagged (a run of 75).
  - The rate among all compared cells is not known: that needs the MS. The
    per-(antenna, channel) rate in `cells-tables.json` (43 %) also counts
    channels whose data are flagged, so it is not comparable. The clustering
    is measured; an enrichment is not.
  - At channel 1879, antennas 35, 15, 16, 17 and 5 have B flagged (run of 2
    channels). 35, 55, 15, 16, 17 and 5 have Df flagged (run of 4–6).

The two implementations:
- **Rang** (`core/src/cal/apply.rs`, `b2d80dc`):
  - interpolates in float32, as CASA does (`fn track` at line 363,
    `resample_freq`);
  - then applies every term in **float64** and rounds once
    (`od[...] = v[k].re as f32`, line 808).
- **CASA's VisCal** applies each Jones in float32 `Complex` (I, from CASA's
  types; not read for this note).
- The chain, from `R/applycal-spec.json` (M):
  - fields 0 and 1: K, G, B, Gpol (time `linear`), Kcross, Xf, Df (time
    `nearest`; the frequency part is `linear`, so flagged channels are
    bridged), then P (`parang=True`);
  - field 2: K, F, B, Kcross, Xf, Df, then P.
- P mixes the 15 Jy parallel hands into the cross hands, so every float32
  rounding of XX and YY lands in a 0.4 Jy cross hand (I).

Diagnosis (I):
- Rounding accumulation over the long chain explains the size of the excess.
  The class C limit of 11 eps (A0 6.2) is the maximum measured by DF-IO
  (10.3 eps) on K, G, B, T and Df only, over about 352k cells
  (`research/dfio-formats.md` line 365). E2-B adds Gpol or F, Kcross, Xf and
  P, and has about 1,160× as many cells, so a tail above 11 eps is expected.
- Rounding alone does not explain the clustering. Baseline (35, 55) at
  channel 1879 recurs in 16 integrations, and 29 of 42 cells sit on bridged
  B or Df solutions. That points to the frequency bridge of a flagged
  solution:
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
1. **Phase-only weighting** (net weights derived from the code, not
   measured).
   - Rang's `phase` kernel is QuartiCal's (`core/src/cal/diag.rs`, `b2d80dc`,
     lines 45–48, 388–397 and `elem_phase`). It scales each datum to the
     model's amplitude, then normalises the residual by `1/|J|²`
     (`absdivsq`) in both `JᴴWr` and `JᴴWJ`. A datum's phase residual then
     enters with a weight of about `w`, whatever its amplitude.
   - CASA's `G 'p'` first divides by the model, with weight `w|M|²`
     (`divideCorrByModel`). Then `enforceAPonData` divides each datum by its
     amplitude and multiplies its weight by `amp²`
     (`research/c1-calibration-chain.md` line 125, read from CASA's source).
     The net weight is `w|R|²`.
   - For a point model of a source partly resolved on the long baselines
     (`e2-average-time.md` 4.2's reading of 3C 286), |R| < |M| there. CASA
     down-weights the outer antennas' baselines relative to rang, so the
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
- Confound: CASA's 3b Gpol pre-applies CASA's own K, G and B, which differ
  from rang's (section 3).
  - The E2-B comparison therefore uses a CASA Gpol re-solved after A2's
    matched case, with that case's K, G and B. Rang's Gpol pre-applies
    rang's.
  - A3 runs after A2.
- Decision rule:
  - Met on both: the key becomes the E2 configuration's for the next unseen
    leg (E2-A has no polcal, so E3 or the reserve).
  - Met on LUNO only: documented limitation, with the per-antenna table.
  - If A2's matched case leaves the composites outside class B, A3's E2-B
    reading is reported but not used for the decision.
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
does not touch K and B) moved neither. B's relative median equals the
composites', and K's delays agree to 0.00072 ns (median). So the difference
is most likely in B (I; K is not excluded).

**The CASA arm's inputs differ from rang's** (M, from the scripts and the run
summary):
1. **Flags.**
   - The frozen pipeline inserts `extendflags` before the polcal solves,
     after K, G and B (`core_pipeline.py` line 1572, `b2d80dc`). It covers
     fields 0 and 1, so 1934−638 is included.
   - In this run it added 33,362,888 flags: 2,497,588,404 → 2,530,951,292,
     2.4 % of the unflagged cells of fields 0 and 1 together
     (`rang-run/calibrate/summary.json`, step `extendflags`). 1934−638's
     share is not archived.
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
  - `minsnr` 3, `minblperant` 4 as now. Rang's chain defaults are the same
    (`cal_chain.py` lines 79–80 at `b2d80dc`).
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

**Proposed arm A4 (seen; dirty L∞ against ε).**
- At ε 1e-4 the edge L∞ is 12–35× ε, and the inner value 0.2–0.3× ε.
  - A linear scaling to ε 1e-6 would leave the edge near 1e-5, still a miss.
  - The ε of A0's 6.5e-8 to 2.2e-7 is not stated in `gemclean-heldout.md`
    section 3.
  - So A4 measures the scaling instead of assuming it.
- Hypothesis: the edge excess falls in proportion to ε. At the finest ε both
  imagers support in double precision (1e-7 or below), dirty L∞/peak is
  ≤ 1e-6 on all three fields.
- Data: RANG_CORRECTED_DATA and rang's FLAG after apply on
  `D:\rang\outputs\e2-20261111-20-e2b\casa\e2b.ms`. Those columns are
  untouched by the 7.4 cases, which wrote CORRECTED_DATA and E2_XFER.
- Settings:
  - gate 3c's geometry and unit weights;
  - `gemclean` and WSClean 3.7 `-niter 0` at ε 1e-5, 1e-6 and 1e-7;
  - L∞ over the full image, with the 5 % border excluded, and over the inner
    two-thirds (7.1's profile).
- Decision rule:
  - Met on all three fields at some ε: the dirty miss was the protocol's ε.
    The owner decides whether the finish line's images run at that ε.
  - The edge excess does not fall with ε: an edge difference between the
    gridders (padding or taper; rang's configuration has no padding key).
    Open a G task.
- Frozen tolerance: 1e-6.
- Cost: about 3 CPU-hours.

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
- chi-offset reran each scan at receptor 0, with Xf solved on that same
  scan.
  - χ is still 7.47° (s17) and 9.31° (s1) from 33.1°.
  - That is an RM of −1.4 and −2.1 rad m⁻² (3.6° and 5.6° at 1.4 GHz),
    plus a constant −3.6°.
  - The transfer recipe itself was not rerun at receptor 0. That it would
    also miss 7° is inferred.

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
| Rang, scan 18's own ap G, reported | 0.026 % | 0.029 % | 0.054 % |
| CASA, scan 18's own ap G, reported | 0.025 % | 0.028 % | 0.053 % |

- With scan 18's own amplitudes, Q/I and U/I fall about 10× in every arm,
  and V/I does not change. So
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
  `minsnr` and `minblperant` match rang's chain defaults (3 and 4 at
  `b2d80dc`), so arm A2's flag case should explain it.

## 9. Arms A2 and A1, frozen 2026-11-14 (before any run)

Branch `e2b-arms` from main `ad5f176`. This section is committed before the
scripts that test it (`results/e2b-misses/a2_*.py`, `a1_*.py`). It makes
sections 1 and 3's proposals exact; where it departs from their wording it
says so. Both arms are **seen** (A0 6.6): every E2-B number was read before.
Nothing here changes the frozen E2-B record.

Common:
- Rang side: this branch's extension (main `ad5f176`, built by
  `check_all --quick` into the worktree `.venv`); the frozen arm's tables
  `R/rang-run/calibrate` (`R` = `D:\rang\outputs\e2-20261111-20-e2b`).
  `R` and its CASA copy are read only; nothing is written under `R`.
- CASA 6.7.6.14 (`rang-o-casa:6.7.6.14`, docker in WSL), every input copied
  first to WSL's ext4 under `~/e2b-arms-20261114/` (deleted at the end).
- Outputs and receipts: `D:\rang\outputs\e2b-arms-20261114\`; compact
  receipts in `results/e2b-misses/`.
- Flag versions, from `R/casa/e2b.ms.flagversions`:
  - flag stage = `rang_calibrate_20261112T010110Z` ("flags before calibrate");
  - after calibrate = `rang_apply_20261112T013707Z` ("flags before apply",
    the input of 2b's applycal and of the 3b CASA arm).

### 9.1 A2, K/G/B composites on matched CASA inputs

Rang's solve inputs (M, `R/rang-run/calibrate/summary.json` steps, in order):
K, G, B on field 1 and Gsec on field 2 saw the flag stage's flags; then the
A step (`Asec`) flagged field 2 (52.55 % → 53.05 %); then F's appended G
(base G) was solved on field 2 with those flags; `extendflags` (fields 0
and 1 only) came after F. Weights: unit (`weight_column: unit`).

So "flag stage" in section 3 is exact for K, G, B and Gsec, but not for F.
The freeze defines the matched flag case per solve.

Data:
- `D:\rang\data\e2-b\e2b.ms` (51 GB, DATA never written by rang) copied to
  ext4. Precondition: its FLAG hash equals `R/flaghash-input.json`
  (restored state).
- Per case, a deep copy of the rows with FIELD_ID 1 or 2 (scans 18-20;
  FIELD_IDs and subtables unchanged) with that case's FLAG and weights.

The 2×2 cases (flags × weights):
- Flags:
  - **match**: rows from the flag stage for setjy, K, G, B and Gsec. Then
    field 2's FLAG is replaced by the after-calibrate version (flag stage
    plus Asec; extend does not touch field 2) before the Gapp append and
    `fluxscale` that give F. Before the swap, the same append and
    fluxscale also run once on the flag stage's flags, giving `F_fs`
    (section 3's literal case). `F_fs` is reported, not decided on.
  - **after**: every row from the after-calibrate version (the frozen 3b
    input).
- Weights:
  - **spec**: WEIGHT and WEIGHT_SPECTRUM as in the MS (the frozen 3b input);
  - **ones**: `initweights(wtmode='ones', dowtsp=True)`. Before any solve,
    WEIGHT and WEIGHT_SPECTRUM are read back and must be 1 in every cell,
    or the case is void.
- The matched case is (match, ones); (after, spec) is the frozen 3b run.

CASA calls: `e2_casa3b.casa_calls`'s setjy (J1939−638 only, since field 0
is absent), K, G, B, Gsec, `copytree` G → Gapp, the Gapp append on
J1833−2103 and `fluxscale` → F, with the same arguments: refant
m022,m023,m024 flex, minsnr 3, minblperant 4, uvrange >150. The polcal
calls and applycal are not run.

Score (`e2_score3b.scores`' composite code, `e2avg_common`):
- `composite_fcal_KGB`: K, G, B on J1939−638, pooled, every 8th time;
- `composite_gcal_KFB`: K, F, B on J1833−2103, table fields (1, 2, 1),
  every time.
- Rang's frozen tables against each case's tables. Rows and frequencies
  come from `R/casa/e2b.ms` (read only).
- Reported beside them: `term_diff` of K, G, B, Gsec, F (and `F_fs`), and
  B's solution flags that differ.

Controls, read before any case's score:
- **C0, scorer:** the archived `R/casa/tables` against
  `R/rang-run/calibrate` with this extension must reproduce `R/g3b.json`'s
  two composites: equal cell counts, median and p95 within 1e-3 relative.
  If not, the scorer is fixed before anything else is read.
- **C1, harness:** case (after, spec) must reproduce `R/g3b.json`'s
  composites (median and p95 within 1 % relative) and B's 5,242 differing
  solution flags (within 1 %). If not, the arm is void and is reported as
  such.

Decision rule (tolerance class B, median ≤ 7e-4 and p95 ≤ 3e-3, not
loosened), on the matched case (match, ones):
- Both composites met: the composite miss was an oracle input error, and
  3b's composites are closed as such. The other three cases attribute it
  between flags and weights, as a description, not a decision.
- Both missed: an estimator difference in B, the shared term (K not
  excluded). Open a B task under C2c.
- Primary met, secondary missed: K and B are matched, and the difference is
  in F (the Gapp append or `fluxscale`). Open an F task.
- Primary missed, secondary met: the difference is in the primary's G, the
  term the secondary composite does not use. Open a G task under C2c.

Cost: 4 cases of K, G, B, Gsec and F on scans 18-20. Booked by what one
pilot case uses, measured inside WSL.

### 9.2 A1, localising gate 2b's 42 cells

Data:
- A mini MS: deep copy of the 41 distinct rows of the 42 cells
  (`R/g2b-applycal-cells.json`) from `R/casa/e2b.ms`, all 4,096 channels,
  subtables kept (RECEPTOR_ANGLE −90, as `prep` set it for 2b).
- FLAG and FLAG_ROW from the after-calibrate version, which was 2b's input.
  The copy's own FLAG now holds later cases.
- Each row's antennas, field and scan must equal the cells file's.

Controls:
- **C2, CASA harness:** CASA `applycal` with 2b's call for each field
  (`R/applycal-spec.json`: tables, interp, gainfield, parang, calflag) on the
  mini MS must reproduce every archived per-correlation eps of the 42
  cells within 0.01 eps.
- **C3, rang harness:** `rang.applycal.applycal` with the frozen apply's
  arguments (`R/rang-run/apply/summary.json`; `parang_flags='none'`, the
  rule at `b2d80dc`) on the mini MS must reproduce RANG_CORRECTED_DATA bit
  for bit on every cell that RANG_FLAG leaves unflagged.
- If C2 or C3 fails, nothing else is read. C3 failing means the rang side
  is rebuilt at `b2d80dc`.

Order of terms: rang's `cal_gain.TYPE_ORDER`, which is CASA's VisEquation
order of correction: B, K, Kcross, G (and Gpol; F on field 2), Df, Xf,
then P.

Measurements:
- **M1, per term.** DATA = 1 + 0j in all four correlations and FLAG false.
  This departs from section 1's "unit parallel-hand data", which cannot
  show Kcross or Xf (they move only the cross hands).
  - For each term alone, and for P alone (no tables, `parang=True`): CASA
    `applycal` (2b's interp and gainfield, calflag) against rang's
    `cal_apply.apply(direction='correct')`, or `cal_pol.rotate` for P, with
    the same field map.
  - Both sides correct. Section 1's `corrupt` would compare J with J⁻¹.
  - Measure, per correlation: d = |c − r| / u, where
    u = `np.spacing(np.float32(max(|Re r|, |Im r|)))` (one float32 ulp of
    rang's value). Correlations with |r| < 1e-3 × max_k |r_k| (structural
    near-zeros) use u of the cell's largest |r_k| instead.
  - Agreement: d ≤ 2 on every correlation unflagged in both, on the 42
    cells. Also reported over every unflagged cell of the 41 rows.
- **M2, cumulative.** On the real DATA and the after-calibrate FLAG:
  - CASA `applycal` of the cumulative sets in that order. Field 1: {B},
    {B, K}, {+Kcross}, {+G}, {+Gpol}, {+Df}, {+Xf}, then all + P. Field 2:
    the same with F for G and Gpol.
  - Against rang's float64 apply of the same set (one rounding), and a
    **float32 emulation**: the terms applied one at a time in that order
    with `cal_apply.apply`, the result rounded to complex64 between terms,
    then P by `cal_pol.rotate`.
  - The emulation script is committed before CASA's cumulative outputs
    exist.
  - Measure: |c − x| / (eps32 × max_k |x_k|) per correlation, as 2b's
    compare does.

Decision rule (class C stays at 11 eps, not loosened):
- **Rounding:** M1 agrees on every term and P on all 42 cells, and the
  emulation at all + P is within 2 eps of CASA on all 42 cells. The miss is
  float32 rounding and is reported as a documented limitation. The owner
  decides whether 2b's class C is read on rang's float64 output.
- **Rang difference:** M1 exceeds 2 ulps for some term on any of the 42
  cells. The first such term in the order above is a rang difference. A fix
  task is opened; the fix is not part of this arm.
- **Not shown** (added at this freeze; section 1 had no branch for it): M1
  agrees on every term, but the emulation misses 2 eps on some of the 42
  cells. Rounding is then not shown, and no term is localised. The
  cumulative profile is reported, and 2b stays open.

Cost: under 0.2 CPU-hours; the copy is about 30 MB.

### 9.3 A1 measured, 2026-11-14

Runs:
- Results in `D:\rang\outputs\e2b-arms-20261114\a1`; receipts in
  [results/e2b-misses/a1/](results/e2b-misses/a1/) (`a1.json`, `mini.json`,
  `a1-spec.json`, `casa-results.json`, `p-term-size.json`).
- Scripts: `a1_casa.py`, `a1_rang.py`, `a1_run.sh` and `a1_rang_all.sh`,
  committed before the run.
- Rang side: this branch's extension at main `ad5f176`.
- CASA: 6.7.6.14, 32 `applycal` calls with no errors.

Controls (both met):
- **C2:** CASA's 2b calls on the mini MS reproduce every archived
  per-correlation eps of the 42 cells (maximum deviation 0.00 eps).
- **C3:** rang's library apply reproduces RANG_CORRECTED_DATA bit for bit
  on 390,636 unflagged correlations, flags equal. So main's apply equals
  `b2d80dc`'s here, and no rebuild was needed.

M1, each term alone on unit data, d in float32 ulps:

| Term | Over 2 ulps on the 42 cells (field 1 / field 2) | Max ulps on the 42 cells | Over 2 ulps, all cells of the 41 rows |
| --- | --- | --- | --- |
| B | 0/120 / 0/48 | 1.03 / 2.00 | 3,607 / 1,198 |
| K | 0/120 / 0/48 | 2.00 / 2.00 | 12,024 / 5,172 |
| Kcross | 0 / 0 | 1.00 / 1.00 | 0 / 0 |
| G (F on field 2) | **1/120** / 0/48 | **2.004** / 1.80 | 4,096 / 0 |
| Gpol | 23/120 / – | 3.01 / – | 90,112 / – |
| Df | 0 / 0 | 1.00 / 1.00 | 6 / 0 |
| Xf | 2/120 / 0/48 | 4.47 / 1.00 | 3,393 / 1,404 |
| **P** | **120/120 / 48/48** | **366 / 273** | **every cell** (median 151.5 / 78 ulps) |

- No flag differs on any term.
- P alone on unit data differs from CASA by up to 1.1e-5 (field 1) and
  5.1e-6 (field 2) in absolute value: median 9.8e-6 and 4.1e-6, on every
  cell of every row.

M2, cumulative, eps of the cell maximum on the 42 cells:
- Through every table term (B … Xf), CASA and rang agree within 5.3 eps
  (field 1) and 3.7 eps (field 2).
  - None of the 42 cells is over 11 eps before P.
  - The float32 emulation is within 4.7 and 4.6 eps.
- Adding P takes the maximum to 13.4 eps (field 1) and 25.6 eps (field 2).
  - rang's apply has 43 and 28 correlations over 11 eps.
  - The emulation is no closer: 13.5 and 25.7 eps, with 40 and 28
    correlations over 11.
  - Over all cells of the rows, the median rises from about 0.1 eps before
    P to 2.0 and 1.4 eps with P.

**Outcome under the frozen rule: rang difference, first term G** (field 1).
The first term in the order whose M1 value exceeds 2 ulps on one of the 42
cells is G: one correlation at 2.004 ulps. The emulation also misses 2 eps
on all + P.

What the rule allows us to conclude:
- The miss is **not shown to be float32 rounding**. The "rounding" branch
  fails on both of its conditions.
- Under the rule as frozen, G is the term named. This is the record.

What it does not allow:
- It does not show that G is the cause, or that any term has a bug.
- The measurement ranks the terms by size. G's excess is 0.004 ulps over
  the bound on 1 of 120 correlations. Gpol and Xf exceed by a few ulps.
- P differs by 78–366 ulps on every cell. M2 shows the class C excess
  appears only at the P step, and the emulation does not remove it.
- That P is the term that carries gate 2b's miss is a reading of these
  numbers (**post hoc**, not the rule's outcome). It fits an angle
  difference of order 1e-5 rad between rang's and CASA's parallactic
  angles.
- What makes that difference (time used, astrometry, receptor-angle
  handling) is **not measured**.

The frozen rule says a fix task is opened for the named term. Per the
coordinator, no fix and no new arm is started here; the next step is
proposed in "For the coordinator".

### 9.5 A1b, P alone: rang's parallactic angles against CASA's, frozen 2026-11-14 (before any run)

Asked by the coordinator after 9.3. This is a new arm, **seen**: it was
chosen after 9.3's P reading. No rang code changes in this branch.

Hypotheses, tested in this order (each a candidate for rang's angle):
- **H1, time column:** CASA's P uses TIME_CENTROID, or the integration's
  start or end (TIME ∓ INTERVAL/2), where rang uses TIME
  (`applycal.applycal` passes `group["TIME"]` to `cal_pol.table_angles`).
- **H2, UT1 − UTC (IERS source):** CASA's measures data in
  `rang-o-casa:6.7.6.14` gives a different UT1 − UTC for 2021-08-18 than
  astropy's bundled IERS. rang's `parallactic_angle_casa` uses
  `iers.conf.auto_download = False`.
- **H3, other astrometry:** precession/nutation model or latitude
  convention. This is not tested directly. It is what remains if H1 and H2
  fail.

Data: the A1 mini MS (41 rows, fields 1 and 2), its FEED (RECEPTOR_ANGLE
−90) and ANTENNA tables.

Probe:
- CASA `applycal` with no tables and `parang=True` on DATA = XX 1, XY = YX
  = YY 0, FLAG false. The same call is made in rang
  (`cal_pol.rotate(inverse=True)` with `angle_table_at` angles).
- Each antenna's angle is read back from the corrected correlations by one
  extraction function: χ_q from (XX, XY) and χ_p from (XX, YX).
- **Control C4:** the extraction applied to rang's probe recovers rang's own
  `angle_table_at` angles within 1e-9 rad on every row and antenna, or the
  extraction is fixed before CASA's output is read.

Measurement:
- Δχ = χ_CASA − χ_rang per row and antenna (82 values per field), and
  the time offset Δχ / (dχ/dt) per value.
- Candidates for rang's angle:
  - (a) as run;
  - (b) at TIME_CENTROID;
  - (c) at TIME − INTERVAL/2 and TIME + INTERVAL/2;
  - (d) with UT1 − UTC forced to CASA's value at that epoch, read in the
    container with `casatools.measures` (UTC → UT1 at the rows' times).
- Reported beside, not decided on: UT1 − UTC from astropy and from CASA,
  and the CASA image's measures data date.

Tolerance: a candidate explains the difference when max |Δχ| ≤ 2e-7 rad
over every row and antenna of both fields. That is about two float32
epsilons; P's M1 excess was about 1e-5.

Decision rule:
- The first candidate, in the order (b), (c), (d), that meets the
  tolerance names the cause:
  - (b) or (c): H1. Name rang's line and CASA's behaviour (which time its
    VisBuffer gives PJones).
  - (d): H2. A data difference in UT1 − UTC, not a code bug in either. Say
    which side's UT1 − UTC is the published one, if the container's data
    show their source.
- None meets it: cause not found under this rule (H3 open). The table of
  Δχ and the time offsets is reported.
- If (a) already meets the tolerance, the 9.3 P reading is not confirmed
  by this probe. Report that.
- A fix is out of scope here (coordinator).

Cost: seconds of CPU; 1 slot.

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
- **Blocking until read correctly:**
  - 3c dirty L∞: the protocol ran at ε 1e-4 against a bound measured at
    finer ε. A4 shows whether this is the ε or an edge difference in the
    gridder.
  - 3c as committed: not blocking on its own. It is a scorer error (MS
    weights); the matched reading carries the question, and the frozen
    reading stays the record.
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
3. **A4**, dirty L∞ against ε (1e-5 to 1e-7): about 3 CPU-hours.
4. **A3**, Gpol, `casa_phase_weights` key with LUNO and simulation
   validation, after A2: half a day of code, about 1.3 CPU-hours.
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
