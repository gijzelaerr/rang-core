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

**Update, 2026-11-14 (arm A2, section 9.4):** the 3b composites row is
confirmed as an oracle input error. With CASA's K, G, B and F solved on
rang's own solve flags, both composites meet class B (medians 4.2e-5 and
5.9e-5, p95 1.24e-3 and 1.23e-3). The weights change nothing.

**Update, 2026-11-15 (arms A1c and A4, sections 9.8 and 9.10):**
- 2b's P: cause not found under A1c's rule (casacore's angle reproduces
  applycal only to 2.7e-7 rad, against 2e-7). Post hoc, the difference is
  in casacore's HADEC step, about 0.5″.
- 3c dirty L∞: not ε. At ε 1e-5, 1e-6 and 1e-7 the full-image values are
  unchanged (3.5e-3, 1.2e-3, 2.9e-3). It is an edge difference between
  the gridders; a G task is proposed.

**Update, 2026-11-15 (arms A4b and A1d, sections 9.12 and 9.14):**
- 3c dirty L∞: WSClean's small inversion. With `-no-small-inversion` the
  dirty images agree to 8.1e-8 (J1833−2103, ε 1e-6).
- 2b's P: 92–98 % is casacore's TOPO → HADEC conventions (a zenith-ward
  diurnal shift and polar motion). Not met at 2e-7 under the rule; no
  fix.

**Update, 2026-11-15 (arm A5, sections 9.21 and 9.22):** the 3c matched
compact-median and off-source misses were the missing mask. GeMClean now
masks joined IQUV as WSClean does. With A0 rule 6's 5σ mask in both arms,
the compact median is 0.99977 (scatter 0.72 %) and off-source 1.05–1.09.
Unmasked, with the same oracle, they stay at 0.9940 and up to 2.30.

**Update, 2026-11-15 (arm A3, sections 9.26 and 9.27):** the Gpol row is
closed as an estimator convention. With `calibrate.casa_phase_weights`
(CASA's phase-only datum, read from CASA's source), rang's Gpol meets
class B on E2-B scan 17: median 0.00038° against CASA re-solved on A2's
matched K, G, B (0.120° with `average_freq` alone, 0.270° without). On LUNO
dev it is 1.1e-4°, and on the simulation 1.6e-6°. The key's default
stays false; per the rule it becomes the E2 configuration's for the next
unseen leg.

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
  - **Correction, 2026-11-15 (9.21):** WSClean's mask is not from Stokes I.
    Its noise and peaks come from the joined I + Q + U + V sum, and the
    mask is the union of every polarisation's model pixels. A5 is frozen
    in 9.21.
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

### 9.4 A2 measured, 2026-11-14

Runs:
- Results in `D:\rang\outputs\e2b-arms-20261114\a2`; receipts in
  [results/e2b-misses/a2/](results/e2b-misses/a2/) (`a2.json`, `c0.json`,
  each case's `score.json`, `result.json`, `spec.json`, and
  `weights-identity.txt`).
- CASA 6.7.6.14, 1 slot per case at OMP 1. Wall: after-spec 1,051 s,
  match-ones 1,160 s, match-spec 1,411 s, after-ones 1,323 s. Scoring took
  61–96 s per case at 4 threads.
- Preconditions:
  - the source copy's FLAG hash equals `R/flaghash-input.json`;
  - the "ones" cases read back WEIGHT and WEIGHT_SPECTRUM as 1 in every
    cell;
  - the "spec" cases kept WEIGHT_SPECTRUM between 0 and 21.9.

Harness incidents, none of which changes the protocol:
- The first case run failed at start because the scripts had CRLF line
  endings.
- The first scoring run failed: `$n` was left unexpanded in the case paths
  (fixed in `a2f2fea`).
- A D:-full stop interrupted the work. Afterwards every surviving input was
  re-verified (FLAG hash, flag-version sha256) before reuse.

Controls (both met):
- **C0:** the archived 3b tables re-scored with this extension reproduce
  `R/g3b.json`'s two composites exactly (equal cells, 0.0 relative).
- **C1:** case (after, spec) reproduces them exactly (0.0 relative) and
  B's 5,242 differing solution flags.

| Case (flags, weights) | fcal K G B median / p95 | gcal K F B median / p95 | Class B | B flags differ | B rel. median |
| --- | --- | --- | --- | --- | --- |
| after, spec (= frozen 3b) | 1.14e-3 / 1.52e-2 | 1.12e-3 / 1.51e-2 | no / no | 5,242 | 1.15e-3 |
| after, ones | 1.14e-3 / 1.52e-2 | 1.12e-3 / 1.51e-2 | no / no | 5,242 | 1.15e-3 |
| **match, ones** | **4.2e-5 / 1.24e-3** | **5.9e-5 / 1.23e-3** | **yes / yes** | **0** | 8.2e-4 |
| match, spec | 4.2e-5 / 1.24e-3 | 5.9e-5 / 1.23e-3 | yes / yes | 0 | 8.2e-4 |

- In the match cases, F_fs (F's append on the flag stage's flags, without
  the A step's) gives 3.6e-4 / 1.6e-3 on the secondary composite. That is
  reported, not decided on.
- The weights change nothing.
  - CASA's K, G, B, Gsec and F are identical value for value, flags
    included, between the spec and ones cases with the same flags
    (`a2_weights_identity.py`).
  - Why CASA's solves are invariant to these weights here is not
    established.

**Outcome under the frozen rule: both composites met in the matched case.**
The 3b composite miss was an oracle input error. CASA's K, G and B had been
solved on rang's flags after calibrate, which include `extendflags`, rather
than on the flags rang's own solves saw. 3b's composites are closed as
such.

Attribution, descriptive only:
- The flags carry all of the miss. Matching them removes B's 5,242
  differing solution flags and lowers the composite medians 27× and 19×.
- The weights carry none of it.
- Section 3's inference, that most likely B differs, was right: the B
  solutions changed with the flags.
- Section 8's open item, B's 5,242 flag differences, is explained by the
  flag case.

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

### 9.6 A1b measured, 2026-11-14: void as frozen

Runs:
- `a1b_casa.py` took 7 s; `a1b_rang.py` 4,731 s, almost all of it queue.
  Both ran on 1 slot.
- Results in `D:\rang\outputs\e2b-arms-20261114\a1b`; receipts in
  [results/e2b-misses/a1b/](results/e2b-misses/a1b/) (`a1b.json`,
  `casa-ut1.json`).
- CASA's probe ran with no errors.

**Outcome under the frozen rule: void.** Control C4 is not met.
- The extraction recovers rang's own angles within 2.2e-8 rad on field 1
  and 2.0e-8 rad on field 2, against the frozen 1e-9.
- The other sign gives 0.75 rad, so the extraction's form is right; only
  its precision fails.
- The cause is the freeze, not the extraction: the probe's corrected
  correlations are complex64, and atan2 of float32 values carries about one
  float32 epsilon (6e-8). A 1e-9 bound could not be met by any extraction
  from this probe.
- The extraction was not changed afterwards, and the tolerance is not
  loosened here. CASA's output was read in the same run, so a relaxed C4
  would be post hoc.

Read beside the void outcome (**post hoc**; the 2.2e-8 floor is 1/300 of
the differences below, so the readings are informative):

| Candidate | Max \|Δχ\| field 1 / field 2 (rad) | Median Δχ field 1 / field 2 (rad) |
| --- | --- | --- |
| (a) as run | 7.1e-6 / 3.2e-6 | 6.9e-6 / 3.0e-6 |
| (b) TIME_CENTROID | identical: TIME equals TIME_CENTROID in every row | – |
| (c) TIME ∓ INTERVAL/2 (8.0 s) | 3.1e-4 and 3.0e-4 / 1.0e-4 and 1.1e-4 | – |
| (d) UT1 − UTC = CASA's (−0.1299 s) | 7.1e-6 / 3.2e-6 (changes Δχ by < 1e-9) | 6.9e-6 / 3.0e-6 |

- The difference is of the same size as 9.3's P reading: 7e-6 rad of angle,
  against 1.1e-5 absolute on unit data. It is about constant within each
  field.
- H1 is not supported:
  - TIME and TIME_CENTROID are the same column values here;
  - using the integration's start or end makes Δχ about 40× worse.
- H2 is not supported:
  - forcing CASA's UT1 − UTC (casacore data at `/usr/share/casacore/data`,
    IERSeop2000 VS_DATE 2025/07/28) does not move Δχ;
  - so astropy's bundled UT1 − UTC already matches it to well under a
    millisecond. Astropy's own value was not printed, because of a script
    bug in the report line (`to_value` on an array); the arm does not use
    it.
- Expressed as a clock offset, the difference is +0.091 s on field 1
  (J1939−6342) and −0.147 s on field 2 (J1833−2103): opposite signs on the
  two fields. So it is not one time error. It depends on the source
  direction, which points at H3 (precession or nutation, or the
  apparent-place or latitude convention) as the remaining candidate. **This
  is not tested.**

What this allows: nothing under the rule (void). Post hoc, the P
difference is real, about 1e-5 rad, and direction dependent. It is not
explained by the time column or by UT1 − UTC.

### 9.7 A1c, P astrometry: rang's angle against casacore's own, frozen 2026-11-14 (before any run)

Asked by the coordinator after 9.6 (branch `e2b-pastro`). **Seen**: chosen
after A1b's post hoc reading of a direction-dependent difference of
7.1e-6 rad (J1939−6342) and 3.2e-6 rad (J1833−2103). No rang code changes
before the measurement.

Hypotheses for the term that makes rang's `parallactic_angle_casa` differ
from CASA's applycal:
- **H3a, sidereal time:** casacore's local apparent sidereal time (GMST
  model, equation of the equinoxes) differs from astropy's.
- **H3b, apparent place:** the source's apparent RA and Dec differ, split
  into **precession and nutation** (casacore's IAU 1976/1980 models
  against astropy's IAU 2006/2000A) and **aberration** (annual and diurnal,
  and light deflection).
- **H3c, latitude or pole convention:** the latitude in the formula
  (rang: geocentric from ITRF; casacore's AZEL frame) or polar motion.

Data: the A1 mini MS (41 rows; fields 1 and 2; TIME, ANTENNA1/2, FIELD
PHASE_DIR, which equals DELAY_DIR and REFERENCE_DIR; ANTENNA POSITION), and
A1b's CASA probe (`D:\rang\outputs\e2b-arms-20261114\a1b\casa\probe_*.npz`,
not rerun).

Probe, all float64:
- **Container side** (`a1c_casa.py`, CASA 6.7.6.14's casatools, no `rang`):
  per field, distinct TIME and antenna in the rows, frame = UTC epoch at
  TIME and the antenna's ITRF position:
  - **K**, casacore's parallactic angle as `MSDerivedValues::parAngle`
    computes it: `me.posangle` of the field direction (J2000) converted to
    AZEL, against the HADEC pole (HA 0, Dec 90°) converted to AZEL;
  - K_geo, the same in AZELGEO (reported beside);
  - the source in HADEC (h, δ), APP and TOPO (RA, Dec), JTRUE (RA, Dec,
    precession and nutation only), and the LAST.
- **Rang side** (`a1c_rang.py`): rang's angle q (`parallactic_angle_casa`,
  receptor not added), astropy's TETE place and apparent sidereal time as
  that function uses them, and erfa's ICRS → true-of-date matrix
  (`pnm06a`, no aberration).

Controls:
- **C4** (extraction floor, now float32-aware): A1b's extraction applied to
  rang's probe recovers rang's own angles within **1e-7 rad** on every row
  and antenna. A1b measured 2.2e-8, so this bound is set knowing it is
  met; it guards the reuse of the probe, not a result.
- **C5:** the script's formula with astropy inputs reproduces
  `parallactic_angle_casa` within 1e-12 rad.
- **K1** (the oracle is the right one): casacore's K, plus RECEPTOR_ANGLE,
  matches the angles extracted from CASA's applycal probe within 2e-7 rad
  on every row and antenna of both fields.

Measurement: Δ = q_rang − K per row and antenna (82 values per field),
then rang's formula `atan2(sin h, tan φ cos δ − sin δ cos h)` with one input
at a time taken from casacore (or erfa), the rest rang's:
- (e) h and δ from casacore's HADEC, φ geocentric (rang's);
- (f) LAST from casacore, place from astropy TETE (sidereal time);
- (g) place from casacore APP, LAST from astropy (geocentric apparent
  place);
- (g') place from casacore TOPO, LAST from astropy (topocentric place);
- (g1) casacore JTRUE plus astropy's aberration (TETE minus erfa's true
  place), LAST from astropy: precession and nutation;
- (g2) erfa's true place plus casacore's aberration (TOPO minus JTRUE),
  LAST from astropy: aberration;
- (k) h and δ from casacore's HADEC, φ geodetic (WGS84);
- reported beside: K_geo − K, and casacore JTRUE against erfa's true place
  in arcseconds.

Tolerance: a candidate explains the difference when max |q_candidate − K|
≤ **2e-7 rad** over every row and antenna of both fields (as 9.5).

Decision rule:
- C4 or C5 not met: void.
- K1 not met: casacore's measures path is not what applycal applies; cause
  not found under this rule. Δ and the candidates are reported.
- K1 met and max |Δ| ≤ 2e-7: rang already equals casacore; A1b's reading
  is not confirmed. Report.
- K1 met and max |Δ| > 2e-7: the cause is in rang's angle, named by the
  first candidate in the order below that meets the tolerance:
  - (e) met: the term is in h or δ. Then (f) → H3a sidereal time;
    (g) or (g') → H3b apparent place; and within it (g1) → precession and
    nutation, (g2) → aberration. If (e) is met but none of (f), (g), (g')
    is, H3 is "h, δ, combination" and not split further.
  - (e) not met, (k) met: H3c latitude convention.
  - None met: cause not found under this rule (H3c pole or formula open).
- **Fix**, only if one term is named by the rule: change
  `cal_pol.parallactic_angle_casa` to that convention; it must reproduce K
  within 2e-7 rad on both fields and A1b's CASA probe within 2e-7 rad,
  with a unit test against casacore values committed as a fixture.
  Without a named single term there is no fix in this arm.

Cost: seconds of CPU; 1 slot each side.

### 9.8 A1c measured, 2026-11-15: cause not found (K1 not met)

Runs:
- `a1c_casa.py` (CASA 6.7.6.14's casatools, `a1c_run.sh`) took 3 s;
  `a1c_rang.py` 1,213 s, almost all of it queue. Both ran on 1 slot.
- Results in `D:\rang\outputs\e2b-pastro-20261114\a1c`; receipts in
  [results/e2b-misses/a1c/](results/e2b-misses/a1c/) (`a1c.json`,
  `a1c-casa.json`, `a1c-casa.npz`, `a1c-posthoc.json`).
- casacore logged "Leap second table TAI_UTC seems out-of-date" (the table's
  age against today's clock). No leap second has been added since 2017, so
  it does not affect 2021 epochs. A1b's applycal ran on the same data.
- The posangle check gives 0 for a point straight above, so `me.posangle(a,
  b)` is the position angle of b seen from a, as K was defined.

Controls:
- **C4 met:** 2.2e-8 and 2.0e-8 rad against 1e-7.
- **C5 met:** the script's formula equals `parallactic_angle_casa` exactly
  (0.0 rad).
- **K1 not met:** casacore's K against CASA's applycal probe is 2.28e-7 rad
  (field 1) and 2.73e-7 rad (field 2) at most, against the frozen 2e-7. The
  medians are −2.2e-8 and −1.3e-7.

**Outcome under the frozen rule: cause not found (K1 not met).**
casacore's measures path, as computed here, is not shown to be what
applycal applies. No fix is made, and the 2e-7 bound is not loosened.

Read beside the outcome (all values are max |·| over 82 values per field):

| | Field 1 (J1939−6342) | Field 2 (J1833−2103) |
| --- | --- | --- |
| rang − CASA probe (A1b) | 7.1e-6 rad | 3.2e-6 rad |
| K − CASA probe (K1) | 2.3e-7 | 2.7e-7 |
| Δ = rang − K | 7.0e-6 (median −7.0e-6) | 3.2e-6 (median −3.1e-6) |
| (e) casacore h, δ in rang's formula, geocentric φ | **0.0** (9e-16) | **0.0** |
| (f) casacore LAST | 6.7e-6 | 3.3e-6 |
| (g), (g') casacore APP, TOPO place | 5.0e-6 | 3.1e-6 |
| (g1) casacore precession and nutation | 7.8e-6 | 3.0e-6 |
| (g2) casacore aberration | 4.2e-6 | 3.2e-6 |
| (k) geodetic latitude | 2.0e-3 | 5.9e-3 |
| K_geo (AZELGEO) − K | 2.0e-3 | 5.9e-3 |

Post hoc readings (not the rule's outcome):
- casacore's K reproduces CASA's applycal to 3–4 % of rang's difference.
  So casacore is a near-oracle at the 2.7e-7 level, but not within the
  frozen 2e-7.
- (e) is exact. casacore's parallactic angle is rang's formula on
  casacore's HADEC (h, δ), with the geocentric latitude rang uses. The
  latitude and pole convention (H3c) are therefore not the difference;
  (k) and AZELGEO are 1e-3 away.
- The difference is in the source's hour angle and declination. casacore's
  HADEC differs from astropy's TETE hour angle and Dec by up to 0.41″ and
  0.53″ (field 1), and 0.43″ and 0.51″ (field 2).
- No single input explains it:
  - casacore's APP and TOPO places differ from TETE by ≤ 0.19″ (APP equals
    TOPO here);
  - its LAST differs from astropy's by 0.054″;
  - its JTRUE differs from erfa's IAU 2006/2000A true place by ≤ 0.07″;
  - substituting any one of these leaves 3–8e-6 rad.
  - So the 0.5″ is added in casacore's APP → HADEC step, not in the place
    or the sidereal time.
- Its size is that of polar motion (x 0.248″, y 0.352″ from astropy's IERS
  for 2021-08-18). But `a1c_posthoc.py` shows two things:
  - astropy's observed HADec frame, which applies polar motion and diurnal
    aberration, is further from casacore (PA 1.2e-5 and 3.9e-6 from K);
  - a simple polar-motion rotation of the TETE place, in either sign,
    leaves 0.25–0.33″.
  - What casacore's HADEC adds is **not identified**.

What this allows: nothing under the rule. Post hoc, rang's P differs from
casacore and CASA because casacore's HADEC conversion of the source adds
about 0.5″ that astropy's TETE place plus apparent sidereal time does not.
A follow-up would read casacore's `MCDirection` APP → HADEC route (polar
motion, diurnal aberration, the tables it reads) and freeze a candidate
before testing it. Until then `parallactic_angle_casa` stays as it is.

### 9.9 A4, dirty L∞ against ε, frozen 2026-11-14 (before any run)

Section 4's proposed arm A4, made concrete. **Seen**: gate 3c's matched
reading (ε 1e-4: full image 1.2e-3 to 3.5e-3 of the peak, inner two-thirds
2.2e-5 to 3.0e-5) is known.

Hypothesis (section 4): the dirty difference between GeMClean and WSClean
3.7, edge excess included, falls in proportion to the gridder accuracy ε.
At the finest ε both imagers support (1e-7), dirty L∞/peak is ≤ 1e-6 on all
three fields.

Data: `D:\rang\outputs\e2-20261111-20-e2b\casa\e2b.ms`, put in gate 3c's
matched state by `e2_post.py`'s own `UNIT_PY` ("on": FLAG is RANG_FLAG,
WEIGHT_SPECTRUM renamed away, WEIGHT 1), and returned by "off" after the
last run (the column list is checked against the one before). Both imagers
read RANG_CORRECTED_DATA from that one state. Gate 3c's rang images were
made from the rang-run MS's CORRECTED_DATA; A1's C3 showed that equals
RANG_CORRECTED_DATA bit for bit on the rows it read, and control C6 below
checks it for the images.

Settings, gate 3c's (`wsclean3c-unit-run.json`, the image stage argv) with
only ε and the thread count changed:
- common: `-size 2048 2048 -scale 2asec -weight briggs 0.0 -channels-out 8
  -join-channels -pol IQUV -join-polarizations -niter 0 -data-column
  RANG_CORRECTED_DATA -field <id> -wgridder-accuracy <ε>`, fields 0, 1, 2
  (J1331+3030, J1939−6342, J1833−2103);
- WSClean 3.7 (`rang-wsclean-native:3.7`): `-gridder wgridder
  -no-update-model-required -j 4`; its own precision choice;
- GeMClean (this branch's extension, Windows): `-unit-weights -scans
  17,18,19,20 -no-update-model-required -j 4`; its default precision rule
  (single at ε ≥ 1e-5, double finer);
- ε = 1e-5, 1e-6, 1e-7: 18 dirty runs.

Control **C6** (inputs and harness), before any A4 score is read: at ε 1e-4
on J1833−2103, WSClean reproduces the archived
`R\wsclean3c-unit\J1833m2103-dirty-*` images and GeMClean reproduces
`R\rang-run-moved\image\J1833-2103\image-*-dirty.fits`, each within 1e-6 of
that channel's WSClean I peak in L∞ over every channel, MFS and Stokes.
Not met: void; the inputs or the harness differ from gate 3c's.

Measures: gate 3c's (`e2_score3c.py`'s `dirty_linf`): per channel and MFS,
per Stokes, max |rang − WSClean| over the peak |I| of WSClean's dirty image
of that channel; over the full image (gated), and reported beside with the
5 % border excluded and over the inner two-thirds.

Frozen tolerance: 1e-6 (A0).

Decision rule, on the full-image L∞ (F(ε), per field):
- F ≤ 1e-6 on all three fields at some ε: the dirty miss was the protocol's
  ε. The owner decides whether the finish line's images run at that ε.
- Otherwise, with r = F(1e-7) / F(1e-5) per field:
  - r ≤ 0.1 on every field (the excess falls with ε, but not far enough):
    the miss is ε, the bound is not reached at 1e-7. Owner: a finer ε or a
    tolerance.
  - r > 0.5 on any field (the excess does not fall with ε): an edge
    difference between the gridders (padding or taper). Open a G task.
  - anything else: partial; reported, no conclusion.
- The inner two-thirds and 5 % border values are reported, not decided on.

Cost: about 3 CPU-hours; WSClean and GeMClean as shared jobs at 4 slots.

### 9.10 A4 measured, 2026-11-15: the difference does not fall with ε

Runs (`a4_queue.sh`, `a4_run.sh`, `a4_rang.sh`, `a4_score.py`, committed
before the runs; `runs.log` gives each wall time):
- WSClean 3.7 took 494–2,799 s per run at 4 slots; most of it is the
  reordering pass over `/mnt/d`. Inversion took 3–18 min.
- GeMClean (Windows) took 171–539 s per run at 4 slots.
- Results in `D:\rang\outputs\e2b-pastro-20261114\a4` (41 GB of images,
  kept for the follow-up below); receipts in
  [results/e2b-misses/a4/](results/e2b-misses/a4/) (`a4.json`, `c6.json`,
  `runs.log`, `unit-on.json`, `unit-off.json`).
- The CASA copy was put in the matched state at 00:25 and returned at
  04:39. Its column list afterwards equals the list before;
  `flag_row_not_all_rang_flag` is 0.

Harness incident, which does not change the protocol: the first GeMClean
queue failed at once on every run. A bare `bash` under heavy_lock on
Windows is WSL's, which could not see the `C:/` script path. Fixed to Git
Bash's path (committed) and rerun; no image had been made.

**C6 met.**
- GeMClean at ε 1e-4 reproduces gate 3c's archived J1833−2103 dirty images
  bit for bit (0.0).
- WSClean reproduces its archived images within 4.0e-7 of the peak, which
  is the thread count (-j 4 against -j 8).

Full-image dirty L∞ / peak (gated), with the 5 % border excluded and the
inner two-thirds:

| Field | ε 1e-5 | ε 1e-6 | ε 1e-7 | r = F(1e-7)/F(1e-5) | 5 % border (1e-7) | inner (1e-7) |
| --- | --- | --- | --- | --- | --- | --- |
| J1331+3030 | 3.460e-3 | 3.460e-3 | 3.460e-3 | 1.000 | 8.1e-5 | 3.0e-5 |
| J1939−6342 | 1.228e-3 | 1.228e-3 | 1.228e-3 | 1.000 | 3.0e-5 | 1.1e-5 |
| J1833−2103 | 2.894e-3 | 2.894e-3 | 2.894e-3 | 1.000 | 8.4e-5 | 2.4e-5 |

**Outcome under the frozen rule: the excess does not fall with ε (r > 0.5
on every field).** It is an edge difference between the gridders. Per the
rule, a G task is opened (proposed below; not started here). The bound is
not met at any ε. Gate 3c's dirty miss is not the protocol's ε.

Read beside the outcome (**post hoc**):
- ε took effect. Each imager's own images change by only 1.0–1.7e-6 of the
  peak between ε 1e-5 and 1e-7, so the gridders' ε-dependent error is
  about 1e-6. The rang − WSClean difference is 1,000× that and independent
  of ε, the inner two-thirds included (1.1e-5 to 3.0e-5, the same as at
  1e-4).
- The maximum sits on the image's outermost rows or columns, in channel
  0000, Stokes I: pixel (2046, 704), (0, 1596), (588, 0).
- It falls steadily inward. Excluding m pixels from each side, the maxima
  are:
  - 3.5e-3 at m = 0;
  - 1.8e-3 at m = 2;
  - 7.7e-4 at m = 8;
  - 2.3e-4 at m = 32;
  - 7.8e-5 at m = 102 (J1331+3030).
  The other fields scale alike.
- WSClean logs "Minimal inversion size 1139 x 1139, using optimal: 1152 x
  1152". By default it grids a smaller image than 2048² and interpolates
  it up (its small-inversion optimisation); GeMClean does not. A
  difference that grows towards the edge and does not depend on ε fits
  that, or a difference in the gridding-correction taper at the edge.
  **Not tested.**

Proposed G task (not started): WSClean at gate 3c's settings with
`-no-small-inversion` (and, separately, GeMClean's and WSClean's padding
matched) at ε 1e-6 on J1833−2103, the cheapest field (about 8 min of
WSClean). GeMClean's images from this arm are reusable. The decision rule
and tolerance (1e-6) need freezing before the run.

### 9.11 A4b, WSClean's small inversion, frozen 2026-11-15 (before any run)

Asked by the coordinator after 9.10. **Seen**: A4's edge profile is known.

Padding is already matched. GeMClean's `-padding` defaults to 1.2, as
WSClean's does (`core/src/grid.rs`), and gate 3c passed neither. So the arm
tests only the small inversion.

Hypothesis: the edge difference is WSClean's small-inversion optimisation.
WSClean grids at 1152² for J1833−2103 and interpolates the image up to
2048², where GeMClean grids at the full padded size. With
`-no-small-inversion`, WSClean's dirty images match GeMClean's within 1e-6
of the peak over the full image.

Data and settings: as 9.9, J1833−2103 (field 2) at ε 1e-6, WSClean only,
plus `-no-small-inversion`. The run reads the CASA copy in the matched
state (`a4_run.sh unit on`, then `off`; the column list is checked).
GeMClean's side is A4's `rang/J1833m2103-eps1e-06` images, unchanged.

Measures: as 9.9 (`a4_score.py`'s `linf`), giving F_nosi (this run) and
F_si = 2.894e-3 (9.10, same ε). Reported beside: the 5 % border and inner
two-thirds values, and WSClean with against without small inversion.

Frozen tolerance: 1e-6.

Decision rule:
- F_nosi ≤ 1e-6: the edge difference is WSClean's small inversion. Gate 3c's
  dirty comparison needs `-no-small-inversion` in the oracle; the owner
  decides whether that changes the gate's reading.
- F_nosi ≤ 0.1 × F_si, but above 1e-6: small inversion carries most of the
  edge excess; the rest is reported, not attributed.
- F_nosi > 0.1 × F_si: small inversion is not the cause; the edge
  difference stays open (gridding-correction taper is the next candidate).
- The inner two-thirds is reported, not decided on.

Cost: one WSClean run, about 10–40 min at 4 slots.

### 9.12 A4b measured, 2026-11-15: met, the difference is WSClean's small inversion

Runs:
- `a4b_queue.sh` ran unit on (25 s), one WSClean run with
  `-no-small-inversion` (481 s, 4 slots) and unit off. The column list of
  the CASA copy afterwards equals the one before.
- Scoring (`a4_score.py nosi`) ran at 2 slots.
- Receipts in [results/e2b-misses/a4/](results/e2b-misses/a4/) (`a4b.json`,
  `runs.log`).

J1833−2103 at ε 1e-6, L∞ / peak:

| Pair | Full image | 5 % border excluded | Inner two-thirds |
| --- | --- | --- | --- |
| **GeMClean − WSClean `-no-small-inversion`** | **8.1e-8** | 8.1e-8 | 8.1e-8 |
| GeMClean − WSClean default (9.10) | 2.894e-3 | 8.4e-5 | 2.4e-5 |
| WSClean default − WSClean `-no-small-inversion` | 2.894e-3 | 8.4e-5 | 2.4e-5 |

**Outcome under the frozen rule: met (8.1e-8 ≤ 1e-6).** The edge
difference is WSClean's small-inversion optimisation. With it off, the two
dirty images agree to 8e-8 of the peak over the whole image, edge and
inner alike. All of gate 3c's dirty difference was WSClean's interpolation
of its 1176² inversion up to 2048², not GeMClean.

Post hoc:
- The inner two-thirds' 2.4e-5, which A4 found independent of ε, is also
  small inversion.
- The owner decides whether gate 3c's dirty comparison reruns with
  `-no-small-inversion` in the oracle (A0 rule: a changed oracle setting
  makes the reading seen). This arm checked one field and one ε.

### 9.13 A1d, casacore's TOPO → HADEC step, frozen 2026-11-15 (before any run)

Asked by the coordinator after 9.8. **Seen**: A1c's post hoc reading places
about 0.5″ in casacore's step from the apparent place to HADEC.

casacore's route, as read in its source (`measures/Measures/MCDirection.cc`,
`MeasMath.cc`, `MeasTable.cc`, master at 2026-11-15; the container runs
casacore from CASA 6.7.6.14, which control C7 below checks against):
- J2000 → JNAT (light deflection) → APP (aberration, then precession and
  nutation) → TOPO → HADEC → AZEL.
- APP → TOPO (`applyAPPtoTOPO`) only applies parallax, scaled by 1/distance.
  For a direction (distance 0) it does nothing, so casacore's TOPO equals
  APP (as 9.8 found).
- TOPO → HADEC (`applyTOPOtoHADEC`) does two things:
  - "diurnal aberration": it adds the vector g₂ · u(LAST, LAT) to the
    source's unit vector and renormalises. g₂ = 2π R / 86,400 s · (UT → ST
    ratio) / c, about 1.5e-6 rad for MeasMath's RADIUS. u(LAST, LAT) is the
    unit vector of the local zenith in the apparent equatorial frame, so
    the shift is towards the zenith, by g₂ sin z. The physical diurnal
    aberration is towards the east point.
  - polar motion (`deapplyPolarMotion`): the rotation
    Euler(−x″, axis 2; −y″, axis 1; LAST, axis 3), then the sign of the
    second coordinate flipped to give the hour angle. x and y come from
    IERSeop2000 (MEASURED).
- HADEC → AZEL uses LAT, which 9.8's (e) showed is rang's geocentric
  latitude.
- Refraction is off: AZEL has none, and none is applied on this route.

rang's `parallactic_angle_casa` uses astropy's TETE at the antenna's
location. TETE includes the physical (eastward) diurnal aberration, and no
polar motion.

Hypothesis **H4:** the 3–7e-6 rad difference is casacore's TOPO → HADEC
step: the zenith-ward "diurnal aberration" in place of the eastward one,
plus polar motion.

Probe (all float64):
- Container side (`a1d_casa.py`):
  - synthetic directions (a grid, not the fields) in APP at the data's
    epochs and antenna positions, converted to HADEC, with LAST and TDB;
  - for the data rows: x and y read from IERSeop2000 at each TIME (linear
    in MJD, as MeasIERS interpolates), TDB and RADIUS (`me.measure` of the
    position).
- Rang side (`a1d_rang.py`): an emulation E of casacore's TOPO → HADEC in
  numpy, from the code above.

Controls:
- **C7** (the emulation equals the container's casacore): E applied to
  casacore's own APP place and LAST reproduces casacore's HADEC (h, δ)
  within 1e-9 rad on the synthetic directions. E's conventions (matrix
  order, signs) may be fixed until C7 is met, before the field rows are
  read. Not met: void.
- **C8:** E applied to casacore's APP place and LAST for the field rows
  reproduces K (9.8) within 1e-8 rad through rang's formula. Not met: void.
- **C5** as 9.7.

Candidates for rang's angle, through rang's formula with geocentric φ,
each against K (9.8):
- (H4) astropy's geocentric apparent place (TETE without location, so no
  diurnal aberration), then E (zenith shift and polar motion), LAST from
  astropy;
- (H4-L) the same, LAST from casacore;
- reported beside: (H4-noPM) without polar motion; (H4-noD) without the
  zenith shift.

Tolerance: 2e-7 rad, max |q − K| over every row and antenna of both fields
(as 9.7).

Decision rule:
- C7, C8 or C5 not met: void.
- (H4) met: H4 is the cause. The beside rows say which of the two terms
  carries it.
- (H4) not met, (H4-L) met: H4 plus the 0.054″ sidereal time difference.
- Neither met: H4 is not shown. The residual is reported.
- **Fix:** as 9.7, only if (H4) or (H4-L) is met *and* the new angle meets
  A1b's CASA probe within 2e-7 rad on both fields. Since 9.8 found casacore
  itself 2.7e-7 from the probe, that second condition may fail. Then there
  is no fix in this arm, and the owner decides whether rang should emulate
  casacore at a tolerance written for it.

Cost: seconds of CPU; 1 slot each side.

### 9.14 A1d measured, 2026-11-15: H4 not shown (5.5e-7 against 2e-7)

Runs:
- `a1d_casa.py` (`a1d_run.sh`) and `a1d_rang.py` took 1 s and 2 s, each on
  1 slot.
- Results in `D:\rang\outputs\e2b-pastro-20261114\a1d`; receipts in
  [results/e2b-misses/a1d/](results/e2b-misses/a1d/) (`a1d.json`,
  `a1d-casa.npz`).

Controls (all met):
- **C7:** the emulation reproduces casacore's HADEC on 270 synthetic
  directions within 4.4e-16 rad. The convention is chosen on them: sign
  +1, the product R₃R₂R₁, applied without transpose; the other seven
  conventions are 3e-6 rad or more away.
  - Both terms matter on the synthetic set. Without the zenith shift, C7
    would be 4.8e-6 rad; without polar motion, 7.4e-6 rad.
- **C8:** on the field rows, the emulation from casacore's APP place and
  LAST reproduces K exactly (1.3e-15 rad).
- **C5:** as 9.8.

Max |q − K| (median in brackets), rad:

| Candidate | Field 1 (J1939−6342) | Field 2 (J1833−2103) |
| --- | --- | --- |
| rang as is | 7.0e-6 (−7.0e-6) | 3.2e-6 (−3.1e-6) |
| **(H4)** geocentric TETE + E, astropy LAST | **5.5e-7** (5.4e-7) | **5.6e-8** (−4.4e-8) |
| (H4-L) the same, casacore LAST | 8.3e-7 | 1.5e-7 |
| (H4-noPM) without polar motion | 2.1e-6 | 3.0e-6 |
| (H4-noD) without the zenith shift | 1.6e-6 | 3.3e-7 |

**Outcome under the frozen rule: H4 not shown.** (H4) is 5.5e-7 rad on
field 1, against 2e-7; (H4-L) is not met either. No fix is made, and
`parallactic_angle_casa` is unchanged.

Read beside the outcome (**post hoc**):
- (H4) removes 92 % of rang's difference on field 1 and 98 % on field 2.
  Field 2 alone would meet the bound (5.6e-8).
- Both of casacore's TOPO → HADEC terms are needed. Dropping either one
  leaves 1.6e-6 to 3.0e-6.
- So most of the A1b/A1c difference is two casacore conventions that
  astropy does not share:
  - the zenith-ward "diurnal aberration";
  - polar motion applied in HADEC.
- The field 1 residual fits the remaining apparent-place difference:
  casacore's APP minus astropy's geocentric TETE is 0.067″ in RA·cos δ
  (0.070″ on field 2) and ≤ 0.012″ in Dec. That is the size of 9.8's
  JTRUE − erfa difference, i.e. casacore's precession and nutation models
  against IAU 2006/2000A. At δ −63.7° it weighs about 2× in h.
- That casacore's own angle is 2.7e-7 from applycal (9.8, K1) is
  separate and still open.

Whether rang should emulate these conventions is a choice of oracle, not
a correctness fix: astropy's diurnal aberration is the physical one. Two
options for the owner:
- a further arm with casacore's precession and nutation (IAU 1976/1980,
  erfa `pmat76` and `nut80`) in (H4), frozen first;
- accepting P's difference (≤ 7e-6 rad, ≤ 26 eps on gate 2b) as a
  documented convention difference between astropy and casacore.

### 9.15 P1, casacore's angle in `parallactic_angle_casa`, frozen 2026-11-15 (before the code)

Owner's decision, through the coordinator: the function exists to match
CASA, so it emulates casacore in full. Branch `e2b-pcasa`. **Seen**: 9.8
and 9.14 are known. This is a change of convention, chosen to match the
oracle; it claims no scientific gain.

Change (implemented after this note is committed):
- `cal_pol.parallactic_angle_casa(times, ra, dec, itrf_xyz)` computes
  casacore's AZEL parallactic angle (`MSDerivedValues::parAngle`) from
  astropy and erfa:
  1. the geocentric apparent place, astropy TETE without location
     (light deflection and annual aberration), taken from IAU 2006/2000A
     to casacore's IAU 1976/1980 equator and equinox of date by
     `pnm80 · pnm06aᵀ` (erfa; the input numbers are kept, as casacore
     reads J2000);
  2. casacore's apparent sidereal time, erfa `gst94` (UT1 from astropy's
     IERS) plus the ITRF longitude;
  3. casacore's TOPO → HADEC step, as emulated in 9.14 (C7):
     - the zenith shift g₂ · u(LAST, φ) with R = |ITRF position|;
     - polar motion with x, y from astropy's IERS table;
  4. rang's formula with the geocentric latitude φ.
- The previous function stays as `parallactic_angle_tete`, the TETE form
  that `simtruth`'s frozen CASA-frame truth uses. Its test compares simtruth
  with that function, so the archived truths and their tests are
  unchanged.
- The angle is computed in Python; the Rust kernel (`cal/parang.rs`) only
  rotates, so there is no Rust or GPU path to change.

Fixture and unit test:
- `tests/data/pa_casacore.json`: casacore's K (`me.posangle` in AZEL,
  CASA 6.7.6.14's casatools) at synthetic cases, generated in the
  container by a committed script:
  - 4 epochs from 2019 to 2024;
  - 3 MeerKAT antenna positions;
  - 12 directions with Dec from −85° to +40°.
  None of them is a field row.
- Test: the new function is within 2e-7 rad of K on every case.
- Development uses the fixture only.

Measurement (held out: the field rows, read once after the code and test
pass):
- **P1-a:** the new angle against K (9.8) on the 82 values per field of
  A1's mini MS. Tolerance **2e-7 rad**, max over both fields.
- **P1-b**, reported: the new angle against A1b's CASA applycal probe (9.8
  found casacore itself 2.7e-7 from it).
- **P1-c**, gate 2b re-score as the consequence: A1's `a1_rang.py rang` and
  `compare` rerun with the new code on the mini MS against A1's archived
  CASA outputs.
  - Reported: the 42 cells' maximum eps with P, against the 13.4 and 25.6
    eps of 9.3; the correlations over 11 eps; the median over all cells of
    the 41 rows.
  - Class C (11 eps) on the 42 cells is the reading; the frozen 2b record
    is not changed.
  - A1's C3 will now differ by design (P changed), and is reported as
    such.
  - The full-MS 2b re-score (a fresh CASA applycal on a 218 GB copy) is
    not run in this arm.

Decision rule:
- The unit test fails at 2e-7: the implementation is wrong. Fix it on the
  fixture before measuring; the held-out rows are not read until then.
- P1-a met: adopt. `frame='casa'` gives casacore's angle; STATE and the
  CLI docs are updated.
- P1-a not met: not adopted. Revert to the TETE form, and report the
  residual.

Cost: seconds of CPU per run; 1 slot.

### 9.16 P1 measured, 2026-11-15: met, adopted

Implemented in `720c8de` (`cal_pol.parallactic_angle_casa`;
`parallactic_angle_tete` keeps the earlier form). The fixture comes from
`p1_fixture_casa.py`: 432 cases, elevations −83° to +76°.

Unit test, on the fixture only and before the held-out rows were read:
- the new angle is within **3.6e-8 rad** of casacore (p99 2.4e-8, median
  8e-9);
- the old TETE form was within 4.5e-5 (median 1.2e-6).
- Test `test_casa_frame_angle_matches_casacore`, bound 2e-7.

Held out (`p1_measure.py`, 2 s; receipts
[results/e2b-misses/p1/](results/e2b-misses/p1/)):

| | Field 1 (J1939−6342) | Field 2 (J1833−2103) |
| --- | --- | --- |
| **P1-a** new − K, max | **1.3e-8 rad** | **4.3e-9 rad** |
| old − K, max (9.8) | 7.0e-6 | 3.2e-6 |
| P1-b new − CASA probe, max | 2.4e-7 | 2.7e-7 |
| K − CASA probe, max (9.8) | 2.3e-7 | 2.7e-7 |

**Outcome under the frozen rule: P1-a met (1.3e-8 ≤ 2e-7). Adopted.**
`frame='casa'` now gives casacore's angle. Against CASA's probe the new
angle is as close as casacore itself. The remaining 2.4–2.7e-7 is
between casacore's measures and what applycal applies (9.8, K1), and it
is still open.

**P1-c, gate 2b re-scored on A1's mini MS** (`a1_rang.py rang` and
`compare`, 6 s, 1 slot; against A1's archived CASA outputs; receipt
`p1/a1-rescore.json`):

| Cumulative set | Field 1: 42 cells max eps / over 11 | Field 2: 42 cells max eps / over 11 | All cells of the 41 rows: max eps / median |
| --- | --- | --- | --- |
| through Xf (unchanged) | 5.26 / 0 | 3.73 / 0 | 5.39, 4.79 / 0.11, 0.10 |
| + P, before (9.3) | 13.37 / 43 | 25.58 / 28 | 13.37, 25.58 / 1.95, 1.35 |
| **+ P, now** | **4.81 / 0** | **4.09 / 0** | **4.91, 4.77 / 1.07, 0.75** |

- On the cells that failed, gate 2b's CASA applycal comparison now meets
  class C (11 eps), with a maximum of 4.8 eps. No cell of the 41 rows is
  over 11.
- A1's rule reads the run as "void" only because C3 now differs, by
  design: rang's apply no longer equals the frozen RANG_CORRECTED_DATA,
  since P changed. Flags are equal.
- The frozen 2b record is not changed.
- A full-MS 2b re-score (a fresh CASA applycal on a 218 GB copy) was not
  run.
- The medians with P (1.07 and 0.75 eps against 0.1 before P) are the
  2.4–2.7e-7 rad that casacore's measures and applycal still differ by.

### 9.17 Gate 3c dirty with WSClean `-no-small-inversion`, all fields (seen, post hoc reading), 2026-11-15

Asked by the coordinator after 9.12. This is a **seen, post hoc reading**,
not a gate change. WSClean is rerun as 9.9's oracle plus
`-no-small-inversion`, at gate 3c's frozen ε (1e-4), on the three fields
(`a4_run.sh wsclean-nosi`, unit on/off as before). Each run is compared
with gate 3c's archived GeMClean dirty images
(`R\rang-run-moved\image\<field>`, which 9.10's C6 reproduced bit for bit)
by gate 3c's measure (full image, 5 % border, inner two-thirds), read
against A0's 1e-6.

Measured 2026-11-15 (`a4c_queue.sh`; WSClean 471, 2,030 and 2,485 s at
4 slots, almost all of it 9p I/O; unit on/off, the column list
restored; receipt `a4/g3c-nosi.json`):

| Field | Full image | 5 % border excluded | Inner two-thirds | Gate 3c as matched (9.10's ε 1e-4 row) |
| --- | --- | --- | --- | --- |
| J1331+3030 | 2.2e-5 | 2.2e-5 | 2.2e-5 | 3.5e-3 |
| J1939−6342 | 2.2e-5 | 2.2e-5 | 2.2e-5 | 1.2e-3 |
| J1833−2103 | 2.0e-6 | 2.0e-6 | 2.0e-6 | 2.9e-3 |

Reading (seen, post hoc):
- Without small inversion the edge excess is gone. The maximum is the same
  over the full image, the 5 % border and the inner two-thirds.
- At the protocol's ε 1e-4 the dirty difference is 2.0e-6 to 2.2e-5, which
  is the gridders' ε 1e-4 error. It is still above A0's 1e-6, whose bound
  was measured at finer ε.
- 9.12 gives 8.1e-8 on J1833−2103 at ε 1e-6 with the same oracle setting.
- So gate 3c's dirty measure would read as met only with both
  `-no-small-inversion` and a finer ε (1e-6). That is shown on one field;
  at 1e-4 it is not met.
- Owner: whether 3c's dirty comparison is re-read at ε 1e-6 with
  `-no-small-inversion` on all three fields. That costs 3 WSClean and 3
  GeMClean runs; book the dirty-only WSClean runs at 1–2 slots on an ext4
  copy, as the coordinator noted.
- The FITS images were deleted after scoring.

### 9.18 Gate 3c dirty at ε 1e-6 with `-no-small-inversion`: post hoc amendment, frozen 2026-11-15 (before any run)

**Dated post hoc amendment** to gate 3c's dirty measure, asked by the
coordinator (branch `e2b-close`). It is seen: 9.10, 9.12 and 9.17 are
known. The frozen record (3c dirty not met) stays. This adds a labelled
re-reading.

Amended oracle and settings: 9.9's common settings at **ε 1e-6** on the
three fields.
- WSClean 3.7 adds `-no-small-inversion` (A4's `-j` 4 replaced by `-j 2`).
- GeMClean runs as 9.9 at ε 1e-6, its default precision (double below
  1e-5).

Data:
- WSClean reads a reduced copy of `R\casa\e2b.ms` in WSL's ext4
  (`~/e2b-close/a5.ms`), made with casacore TaQL. It holds all rows; the
  columns WSClean reads (UVW, ANTENNA1/2, TIME, TIME_CENTROID, INTERVAL,
  EXPOSURE, FIELD_ID, DATA_DESC_ID, SCAN_NUMBER, FLAG_ROW, the id columns,
  SIGMA); RANG_CORRECTED_DATA; FLAG = RANG_FLAG; WEIGHT = 1; and every
  subtable. The copy is deleted after scoring.
- GeMClean reads `R\casa\e2b.ms` in the matched state (`UNIT_PY` on, then
  off; the column list is checked), as 9.10's C6 showed bit for bit.

Control **C10**, before any ε 1e-6 score is read: WSClean with its default
small inversion at ε 1e-4 on J1833−2103, reading the ext4 copy, reproduces
the archived `R\wsclean3c-unit\J1833m2103-dirty-*` within 1e-6 of the peak
(as C6). Not met: void.

Measure and bound: gate 3c's dirty L∞ / peak over the full image, frozen
**1e-6** (A0), with the 5 % border and inner two-thirds reported.

Reading: met on all three fields → gate 3c's dirty measure is met under
the amended oracle and ε (seen, post hoc); otherwise not met, with the
values reported.

Booking: WSClean dirty runs at 2 slots, GeMClean at 4.

**Measured 2026-11-15: met on all three fields (seen, post hoc
amendment).** Receipts in [results/e2b-misses/a5c/](results/e2b-misses/a5c/)
(`a5.json`, `c10.json`, `a5-copy.json`, `runs.log`).

- **C10 met:** WSClean at ε 1e-4 on J1833−2103, reading the ext4 copy,
  is within 6.3e-7 of the archived images (thread count).
- On ext4 WSClean took 232 s for that run, against 1,032 s for the same
  run over 9p (9.10).

| Field | Dirty L∞ / peak, ε 1e-6, `-no-small-inversion` | 9.10 (ε 1e-6, default oracle) |
| --- | --- | --- |
| J1331+3030 | **2.0e-7** | 3.5e-3 |
| J1939−6342 | **3.3e-7** | 1.2e-3 |
| J1833−2103 | **8.1e-8** | 2.9e-3 |

The 5 % border and inner two-thirds values equal the full-image ones.
Gate 3c's dirty measure is met under the amended oracle
(`-no-small-inversion`) at ε 1e-6. The frozen record (not met) stays.

Runs, all rc 0:
- the ext4 copy took 667 s; it was dropped after the runs;
- WSClean took 232–775 s at 2 slots;
- GeMClean took 198 s and 643 s at 4 slots, and 291 s for the J1331
  rerun at 46 GB.

Harness incidents:
- The ext4 copy lacked FLAG_CATEGORY, which WSClean opens. It was added
  without cells (`a5_fixcat.py`) before any image.
- The first GeMClean J1331+3030 run is **void**. It was booked at 16 GB
  but used about 45 GB private; with another agent's 40 GB GeMClean the
  host reached 139 GB committed on 63 GB RAM and thrashed.
  - The owner approved stopping it; it had already exited.
  - Its image was set aside unread and deleted.
  - It was rerun at `--mem 46` (291 s). Every joined-IQUV 8-channel 2048²
    GeMClean is now booked at 46 GB or more.
- The first Windows queue waited for gemclean-iquv-mask's read-only copy
  of the shared MS before any rename.
- The FITS images were deleted after scoring.

### 9.19 Gate 2b on the full MS with the new P, frozen 2026-11-15 (before any run)

The consequence of P1 (9.16) on the whole MS. It is seen: P1's mini-MS
re-score is known.

Procedure on `R\casa\e2b.ms` in place, with no 218 GB copy. Every step
renames or adds columns that are removed again at the end:
1. Save: CORRECTED_DATA → E2C_SAVE_CORRECTED_DATA, FLAG →
   E2C_SAVE_FLAG, FLAG_ROW copied to E2C_SAVE_FLAG_ROW. Record the column
   list and a FLAG hash (`a2_flaghash`-style sha256 over the rows).
2. FLAG and FLAG_ROW from the after-calibrate version
   `flags.rang_apply_20261112T013707Z`, as 2b's prep did. FEED
   RECEPTOR_ANGLE is already −90° from that prep.
3. CASA 6.7.6.14 `applycal` with 2b's own spec (`R\applycal-spec.json`, 3
   calls, calflag, parang) writes CORRECTED_DATA and FLAG. These are
   renamed to E2C_CASA_CORRECTED_DATA and E2C_CASA_FLAG.
4. Control **C9**: 2b's own comparison (`e2p_compare.py`'s rule) of
   E2C_CASA_* against the frozen RANG_CORRECTED_DATA and RANG_FLAG
   reproduces `R\g2b-applycal.json`: 42 cells over class C, max 25.58 eps,
   0 flag elements differing. Not met: void.
5. FLAG and FLAG_ROW from the after-calibrate version again. Then rang's
   apply with the new P (this branch at main `011232e`) is called with the
   frozen apply's arguments (`R\rang-run\apply\summary.json`, as A1's C3,
   `parang_flags='none'`), and writes CORRECTED_DATA and FLAG.
6. Measure: 2b's comparison of E2C_CASA_* against rang's new
   CORRECTED_DATA and FLAG.
   - Class C: per cell ≤ 1e-6 relative, or ≤ 11 float32 eps of the cell's
     largest correlation; flags exact.
   - Reported beside: rang new against RANG_CORRECTED_DATA (P's change
     alone).
7. Restore: remove CORRECTED_DATA, FLAG and E2C_CASA_*, then rename the
   E2C_SAVE_* columns back and copy FLAG_ROW back. The column list and the
   FLAG hash must equal step 1's; D: free space is recorded before and
   after.

Reading:
- 0 cells over class C and flags exact → gate 2b's CASA applycal leg is
  met with the new P (seen; the frozen 2b record stays).
- Otherwise not met, with the count and the maximum reported.

Booking: CASA applycal and casacore steps at 2 slots (9p I/O-bound),
rang's apply at 4. D: must keep ≥ 150 GB free; the new columns add about
85 GB.

**Column handling revised 2026-11-15, before any 9.19 run** (the
comparison, the controls and the reading are unchanged).
- The MS's data manager names would clash: CASA adds CORRECTED_DATA as
  `CorrectedTiled`, which the saved column keeps after a rename, and
  rang adds it as `TiledCorrected`, which RANG_CORRECTED_DATA already uses.
- So no column is created under those names:
  - step 1 *copies* CORRECTED_DATA into E2C_SAVE_CORRECTED_DATA (its own
    manager), so CASA's applycal writes the existing CORRECTED_DATA;
  - step 3 renames only FLAG, to E2C_CASA_FLAG;
  - step 5's rang apply writes `column='E2C_RANG_CORRECTED_DATA'` (its own
    manager) and FLAG, with `flag_backup='rang_original'` (exists, so no
    version is added), and the write-back journal is put back afterwards;
  - step 7 copies E2C_SAVE_CORRECTED_DATA back into CORRECTED_DATA and
    removes the E2C_* columns.
- The check in step 7 adds the sha256 of CORRECTED_DATA (equal to step
  1's) to that of FLAG and FLAG_ROW.

Scripts: `b2_cols.py`, `b2_run.sh`, `b2_rang.py`, `b2_queue.sh`.

**Harness incidents, 2026-11-15, before CASA or rang ran:**
- The first save failed while it hashed CORRECTED_DATA: a 262 MB read
  over 9p returned ENOMEM. Nothing had been renamed. Blocks are now 250
  rows.
- The second save failed while it copied CORRECTED_DATA into
  E2C_SAVE_CORRECTED_DATA: a 9p write returned ENOMEM, with WSL's page
  cache full. `b2_cols.py cleanup` removed the partial column. The column
  set equals the original again, and no original column was written.
- Step 1 now renames CORRECTED_DATA to E2C_SAVE_CORRECTED_DATA, with no
  data copy, and adds an empty CORRECTED_DATA on its own manager
  (`E2CCasaCorrected`) for CASA to write. Step 7 removes it and renames
  the saved column back.
- The third save failed again on a 9p read of CORRECTED_DATA (ENOMEM)
  while it hashed, before any rename. The hashes are now taken natively
  on Windows with rang's reader (`b2_hash.py`), before step 1 and after
  step 7.
- The fourth attempt reached CASA. applycal failed on all 3 calls with
  "TSM: no array in row …", because the empty CORRECTED_DATA was a
  variable-shape TiledShapeStMan column.
  - The queue's restore ran, and the native hashes of FLAG + FLAG_ROW and
    CORRECTED_DATA and the column set equal the ones before.
  - Step 1 now adds CORRECTED_DATA with a fixed shape on a
    TiledColumnStMan. This was tested on a 41-row copy, where CASA writes
    it, before the rerun.
- The fifth attempt's applycal wrote J1939−6342. The other two calls
  failed reading DATA over 9p (ENOMEM), with the host loaded by another
  agent's 40 GB GeMClean.
  - The restore was exact again: hashes and the column set equal.
  - The CASA step is now booked at 24 GB, which covers WSL's page cache,
    so the lock keeps other large jobs off while it reads and writes
    about 72 GB over 9p.

### 9.20 9.19 outcome, 2026-11-15: not run (harness); CASA copy damaged, then repaired

**Not run.** No CASA applycal output for all three fields and no rang
apply were produced, so there is no 2b reading with the new P on the full
MS. The mini-MS re-score (9.16, 4.8 eps) stays the only one.

The sixth attempt damaged the shared CASA copy `R\casa\e2b.ms`, and it was
repaired:
- **Damage (09:50:58).** Step 1 failed when the table closed. casacore was
  writing the new fixed-shape CORRECTED_DATA's cube (36 GB, zeros) over
  9p and got ENOMEM at 15.2 GB.
  - `table.dat` already named the new data manager (seqnr 25), but its
    header file `table.f25` was never written.
  - Neither casacore nor rang could open the MS.
  - Nothing else used it meanwhile; this note's queue had stopped at the
    failed step.
- **Safety first:**
  - the small metadata files were copied
    (`D:\rang\outputs\e2b-close-20261115\b2\ms-meta-backup-0951`);
  - every large data file was hard-linked into
    `...\b2\ms-hardlinks`;
  - the repair was rehearsed on an ext4 copy of A1's mini MS.
- **Rehearsal** (`b2/rehearse/`): `r1.py` builds the same structure,
  `table.f10` is deleted and its data file truncated, and the same open
  error follows.
  - A header from a twin table works once the twin's manager has the same
    sequence number: casacore checks "seqnr, #col".
  - The header fields that depend on the row count were found by diffing
    twins of 41, 300 and 1000 rows: nrrow at 0x60, the cube's last axis
    at 0xF7, and the data file length at 0x91. `patch2.py` reproduces the
    shape fields.
  - On the rehearsal, opening with the patched header and running
    `b2_cols.py restore` gives the original columns and the original
    CORRECTED_DATA, FLAG and FLAG_ROW, value for value.
- **Repair (10:01).**
  - A twin header for seqnr 25, patched to 272,916 rows and to a file
    length the existing partial data file covers, was installed as
    `table.f25` (copy in `b2/repair-table.f25`).
  - casacore then opened the MS, and `b2_cols.py restore` removed the new
    CORRECTED_DATA and FLAG and E2C_SAVE_FLAG_ROW, renamed E2C_SAVE_* back
    and copied FLAG_ROW back. The files f25–f27 are gone.
- **Check (10:05):**
  - the column set equals the original (`columns-original.json`);
  - rang's native sha256 of FLAG + FLAG_ROW and of CORRECTED_DATA equals
    `hash-before.json`, taken before attempt 4 on the restored original.
  - So the CASA copy is back as it was. Receipts: `restore-repair.json`,
    `hash-after-repair.json`.
- Earlier unit on/off cycles left four 6.5 MB `table.f1Ni` index files of
  removed StandardStMan columns. They are unused; this note did not remove
  them.

Lesson:
- casacore and CASA bulk I/O on `/mnt/d` over 9p failed with ENOMEM 6
  times in a row while the host was loaded. Smaller blocks,
  rename-instead-of-copy and a larger booking did not prevent it.
- Native Windows reads of the same files (rang's reader, 36 GB in 102 s)
  and ext4 work (WSClean 232 s against 1,032 s) did not fail.
- Proposed for a rerun, to be frozen first:
  - CASA on a reduced ext4 copy made from a read-only mount (`a5_copy.py`
    pattern, with DATA, the after-calibrate FLAG and RANG_*), with C9 as
    the control that validates the copy;
  - rang's apply natively on Windows into a column of its own;
  - the comparison reading the CASA columns after a plain file copy of
    the ext4 table to D: (no casacore write over 9p).
  - D: has 443 GB free; the ext4 vhdx grows by about 110 GB.

### 9.21 A5, joined-polarisation auto-mask, frozen 2026-11-15 (before any run)

Numbered 9.18 in this branch's commits up to `c52ed26`, then 9.20. Renumbered
9.21 on 2026-11-15, after main's 9.15–9.20 (e2b-pcasa, e2b-close). Only the
number changed.

Fix item 5 of the ordered list. **Seen**: gate 3c's matched scores (section
4) and A4b's small-inversion finding (9.12) are known. The code was written
before this section; no image was made with it before the freeze.

**What GeMClean now does, and what it matches.** Read in WSClean 3.7's radler
(`76fe4474c31c`, the G4 clone `~/Build/tmp/20261109-g4-wsclean-src` in WSL):
- `radler.cc` `Perform` estimates σ every major iteration as
  `integrated.MedianAndStdDevFromMAD()` of
  `residual_set.GetLinearIntegrated(integrated)`.
- With `-join-polarizations` (no `-link-polarizations`, no
  `-squared-channel-joining`), `image_set.cc`
  `GetLinearIntegratedWithNormalChannels` sums **every** polarisation of
  every channel, channel-weighted, times `polarization_normalization_factor_`
  (`image_set.h` `InitializePolFactor`: 1 for IQUV, 1/n for Stokes without
  I, 0.5 for dual or full correlations). So σ is that of I + Q + U + V,
  not of Stokes I and not of a squared sum. `threshold_bias` is 0 without
  squared joins.
- The mask threshold is `max(σ · auto_mask, abs_auto_mask, abs_threshold)`.
  The peaks are searched in the same integrated residual (the fast
  sub-minor loop, G9).
- `SetAutoMaskMode` builds the Högbom mask once, the first time it is used:
  the union over **every** model image of the set (each channel and each
  polarisation) of its finite nonzero pixels.
- One Radler per independent group (`wsclean.cpp` `runIndependentGroup`), so
  each group has its own mask.

GeMClean's `run_joined_masked` (`core/src/gemclean/joined.rs`, G4) already
computed all of this on `norm Σ_k a_k Σ_p r_kp` with
`stokes::normalisation` (G9). The only change is that the CLI and
`core_config` no longer refuse `-auto-mask` / `-abs-auto-mask` with
`-join-polarizations`, and the polarisation path calls the masked kernel and
writes `<name>-mask.json`. Still refused: masks on unjoined polarisations,
and `-fits-mask` on several polarisations (not validated here).

**Correction to section 4** (dated 2026-11-15): "an automatic mask from
Stokes I ... as WSClean does" is wrong against the source. WSClean's mask
and noise come from the joined I + Q + U + V sum. GeMClean matches that,
not a Stokes I mask.

**M0, development check against WSClean on a fixture** (before A5's E2-B
runs; development, not gated):
- Data: G9's P1, `D:\rang\outputs\g9-20261107-02\data\P1.ms`, read in place.
- Settings, both arms: G9's base (2048², 1.5″, briggs 0.5, gain 0.1,
  wgridder ε 1e-6, DATA, field 0), `-pol IQUV -join-polarizations
  -channels-out 8 -join-channels -mgain 0.8 -auto-threshold 3 -auto-mask 5`.
  WSClean 3.7 adds `-no-small-inversion -no-min-grid-resolution`.
- Criteria:
  - σ of every major iteration up to the finishing one: GeMClean's
    `auto-mask: major iteration i, sigma` against WSClean's "Estimated
    standard deviation of background noise", within 1 % (WSClean prints 3–4
    figures);
  - the same finishing iteration (WSClean's "Auto-masking threshold
    reached");
  - total major iterations within ±1.
- If any fails, A5 does not run: the implementation is fixed first, and the
  change is labelled post hoc here.

**A5 hypothesis.** With A0 rule 6's 5σ automatic mask in both arms, and the
oracle without small inversion, gate 3c's cleaned measures meet A0's 3c
tolerances:
- compact-source median ratio within 0.5 % of 1, with robust scatter
  ≤ 1 % (n ≥ 3);
- off-source |model| ratio ≤ 1.6 on each of the three fields.

**Data.** `D:\rang\outputs\e2-20261111-20-e2b\casa\e2b.ms` in gate 3c's
matched state (`a4_unit.py on`):
- FLAG is rang's FLAG after apply;
- WEIGHT is 1, with no WEIGHT_SPECTRUM;
- both arms read RANG_CORRECTED_DATA.

e2b-pcasa toggles the same state (`a4c_queue.sh`). A5 starts only after
that queue's `unit off`, and runs on, all of its runs, then off, as one
sequence. The column list is read read-only before and after every run.
A run whose list changed is void.

**Amendment, 2026-11-15, before any A5 run on E2-B data** (M0 had
started; no E2-B image was made). This changes the data route only, not the
data:
- A5 makes no rename on the shared CASA copy. `a5-mask/a5_slim.py` reads it
  read-only, in either state of `a4_unit.py`, and writes a private copy,
  `D:\rang\outputs\gemclean-iquv-mask-20261115\e2b-slim.ms`, with:
  - the row columns;
  - FLAG = rang's FLAG after apply;
  - RANG_CORRECTED_DATA;
  - WEIGHT = 1, with no WEIGHT_SPECTRUM;
  - the subtables.
- It then compares every copied column with its source, chunk by chunk.
  Any difference voids the copy (receipt `a5-mask/receipts/slim.json`, with SHA-256 of
  FLAG and RANG_CORRECTED_DATA).
- GeMClean reads that copy. WSClean reads a byte-identical copy in WSL's
  ext4 (`~/Build/tmp/20261115-gemclean-iquv-mask`, checked with sha256sum
  per file), which also holds its temp-dir.
- The column-list checks above are replaced by the copy's comparison.
- WSL jobs book the lock once, from the WSL side, at 2 slots (A5's WSClean
  used about 0.8 cores on 4; the coordinator, 2026-11-15).

**Settings.** Gate 3c's frozen settings (`e2b.yaml` `image`, E2-B's
GeMClean argv in `R\rang-run-moved\image\summary.json`):
- 2048² at 2″, briggs 0, 8 joined channels, IQUV joined;
- `-niter 1000000 -mgain 0.9 -auto-threshold 3`, wgridder ε 1e-4;
- unit weights, scans 17–20, fields 0, 1, 2;
- plus `-auto-mask 5`, with the default `-auto-mask-nmiter` (2).

Per arm:
- GeMClean: this branch's extension (the build commit goes in the
  receipt), `-unit-weights`, `-no-update-model-required`, `-j 4`.
- WSClean 3.7 (`rang-wsclean-native:3.7`): 9.12's oracle,
  `-no-small-inversion -no-update-model-required -j 4`.

**Control C** (attribution): WSClean as above, without `-auto-mask`.
- It is scored against E2-B's archived unmasked GeMClean images
  (`R\rang-run-moved\image\<field>`, which 9.10's C6 reproduced bit for bit
  in dirty).
- It separates the mask from the small inversion.

**Measures.** `e2_score3c.py`'s `score_field`, unchanged, called by
`a5-mask/a5_score.py` per field and pooled as its `main` pools. Dirty L∞ is not
re-measured here (9.12, 9.17).
- The source set is recomputed from each pair's own images, so n will not
  be gate 3c's 35.
- Reported beside, not decided on:
  - Δα and the unpolarised Q, U, V test;
  - both arms' σ per major iteration, finishing iteration and major cycles;
  - GeMClean's wall time and peak memory.

**Frozen tolerances** (A0 3c, as in `e2_score3c.py`):
- compact: |median − 1| ≤ 0.005 and robust scatter ≤ 0.01, with n ≥ 3;
- off-source: ratio ≤ 1.6 per field.

**Decision rule.**
- **A5 met** on compact and off-source on all three fields, **C not met**:
  the 3c cleaned miss was the missing mask. The limitation is closed; the
  owner decides whether gate 3c reruns with A0 rule 6's mask.
- **A5 met, C met**: the cleaned miss was WSClean's small inversion, not the
  mask. The mask is delivered anyway.
- **A5 not met on off-source**: GeMClean's deconvolution default (G7) is a
  finish-line item (section 4).
- **A5 off-source met, compact not met**: the compact median stays open as
  algorithmic (deconvolution or restore). It is not attributed to the mask.
- A void run (column list changed, or an arm's exit not 0) is rerun once in
  a fresh on/off sequence, then reported as void.

**Cost.**
- M0: two runs, about 10 min each at 4 slots.
- A5 and C: 3 GeMClean and 6 WSClean cleaned runs at 4 slots each. WSClean
  took 494–2,799 s per dirty run in A4, so allow 1–2 h per cleaned run;
  about 15 CPU-hours.
- Disk: about 3 GB of FITS per run, under 30 GB in all, in
  `D:\rang\outputs\gemclean-iquv-mask-20261115`. Per-case images are
  deleted once scored; the scores and logs are kept.

### 9.22 A5 measured, 2026-11-15: met, the cleaned miss was the missing mask

Build: this branch at `b7c4cca`, its own extension (`.venv` of the
worktree, built by `check_all.py --quick`). Receipts are in
[results/e2b-misses/a5-mask/receipts/](results/e2b-misses/a5-mask/receipts/):
- `m0.json`, `slim.json`, `flagcat.json`, `a5.json`, `control.json`;
- per-run time files and the noise lines of each log;
- `runs.log`.

**M0 (P1, against WSClean 3.7): met.**
- σ per major iteration agrees within 0.27 % (4e-6, 4.4e-4, 7.0e-5,
  2.5e-3, 2.6e-3 relative).
- Both arms finish the mask in iteration 5 and run 6 major iterations.

**Private copy (amendment): exact.**
- 272,916 rows; no chunk of any copied column differs from the source;
  WEIGHT is 1 throughout.
- The ext4 copy equals it file by file (sha256).

**A5 against control C** (frozen measures and tolerances):

| Measure | A5: both masked, oracle without small inversion | C: both unmasked, oracle without small inversion | Tolerance |
| --- | --- | --- | --- |
| Compact median (n) | **0.99977** (37) | 0.99395 (36) | within 0.5 % |
| Compact robust scatter | **0.72 %** | 1.27 % | ≤ 1 % |
| Off-source ratio, J1331+3030 | **1.053** | 2.298 | ≤ 1.6 |
| Off-source ratio, J1939−6342 | **1.083** | 1.264 | ≤ 1.6 |
| Off-source ratio, J1833−2103 | **1.086** | 1.663 | ≤ 1.6 |
| Δα, median (n), reported | 0.0088 (11) | 0.0124 (12) | ≤ 0.05 |
| Unpolarised Q, U, V, reported | met | met | – |

**Outcome under the frozen rule: A5 met, C not met.** Gate 3c's cleaned
miss (off-source and compact median) was the missing mask. The limitation
is closed. The owner decides whether gate 3c reruns with A0 rule 6's mask
(A0: a changed setting makes the reading seen).
- C reproduces gate 3c's matched reading (1.27, 1.67, 2.27; 0.9942), so
  WSClean's small inversion played no part in the cleaned measures.
- The scatter's ≤ 1 % gate also fails in C (1.27 %), not only the median.
  Gate 3c's matched reading had 0.97 %.

Reported beside:
- **Mask stages.** On all three fields both arms finish the mask in major
  iteration 4 and run 5 major iterations. σ per iteration agrees within
  0.67 %, 1.3 % and 2.6 % (J1331, J1939, J1833).
- **Off-source |model|, Jy** (GeMClean / WSClean):
  - masked: 1.73 / 1.64, 16.4 / 15.1, 1.79 / 1.65;
  - unmasked: 28.2 / 12.3, 115.2 / 91.2, 39.8 / 23.9.
  - Unmasked, GeMClean spreads 1.3–2.3 × WSClean's flux outside the
    sources. With the mask both put almost all of it inside.
- **Cost.**
  - GeMClean (4 slots): 1,533 s, 1,014 s and 431 s wall; peak resident
    memory 40.3, 44.9 and 20.2 GB; 2.7–3.5 cores on average.
  - WSClean masked (`-j 4`, booked 2): 1,914, 1,923 and 1,076 s; peak RSS
    2.0, 2.0 and 1.4 GB; 1.1–1.6 cores.
  - WSClean unmasked: 3,017, 3,337 and 909 s; 1.4 GB each.
- **Memory finding.** On joined IQUV, 8 channels, 2048², GeMClean holds
  10–22 × WSClean's peak memory: 45 GB against 2.0 GB on J1939−6342.
  - G5 measured 2–3 × on Stokes I.
  - The 32 entries (8 channels × 4 polarisations) each keep their gridded
    measurement, beam and working maps (I, not profiled).
  - Booking: a joined-IQUV 8-channel 2048² GeMClean run needs at least
    46 GB (the coordinator, after the first run held 40 GB on a 24 GB
    booking and the host thrashed with another run).

Post hoc, during the run, none changing a measure:
- WSClean refused the first private copy ("Table column FLAG_CATEGORY is
  unknown", exit 255 within 1 s, no image). `a5_flagcat.py` added the
  column, empty as in the source, to the ext4 copy only. GeMClean's copy
  lacks it, which changes no data column.
- GeMClean fields 1 and 2 ran after the WSClean lanes, booked at 46 GB.
- Per-case images (about 30 GB) and both private copies (34 GB each)
  were deleted after scoring.

## For the coordinator

**After A5 (9.21, 9.22; 2026-11-15, branch `gemclean-iquv-mask`):**
- **Code:** `gemclean -auto-mask` with `-join-polarizations`, as radler.
  The noise and peaks come from the joined I + Q + U + V residual, and the
  mask is the union of every polarisation's model pixels. `image.auto_mask`
  now takes `join_polarizations`.
  - Still refused: masks on unjoined polarisations, and `-fits-mask` on
    several polarisations.
  - M0 against WSClean on P1: σ within 0.27 %, the same finishing
    iteration.
- **A5: met; control C: not met.** With A0 rule 6's 5σ mask in both arms:
  - compact median 0.99977, scatter 0.72 % (n = 37);
  - off-source 1.05, 1.08, 1.09.
  - Unmasked, with the same oracle, C gives 0.9940, 1.27 %, and 2.30, 1.26,
    1.66.
  - So gate 3c's cleaned miss was the missing mask, not small inversion.
  - Owner: rerun gate 3c with the mask (seen).
- **Memory:** GeMClean peaks at 20–45 GB on these runs, against WSClean's
  1.4–2.0 GB (10–22 ×). Book joined-IQUV 8-channel 2048² runs at
  ≥ 46 GB. A memory task for GeMClean's polarisation path is worth
  opening.
### 9.24 Gate 2b on the full MS with the new P, on ext4, frozen 2026-11-15 (before any run)

9.19's measure and reading, with the I/O path changed after 9.20 (branch
`e2b-2b`).
- Numbered 9.24 at merge (2026-11-15, coordinator; first written as 9.22,
  which gemclean-iquv-mask took for A5 on main).
- Seen: P1's mini-MS re-score (9.16) is known.
- No casacore or CASA write touches `/mnt/d`, and the shared `R\casa\e2b.ms`
  is only read.

Steps:
1. **E, an ext4 copy** (`~/e2b-2b/e.ms`). It is made by TaQL from a
   read-only mount of `R\casa\e2b.ms` and holds:
   - every row and every subtable;
   - the row columns, DATA, WEIGHT and SIGMA;
   - FLAG and FLAG_ROW set from the after-calibrate version
     `flags.rang_apply_20261112T013707Z`, as 2b's prep did;
   - FEED RECEPTOR_ANGLE −90°, as in the source.
2. Control **C11** (the copy is exact):
   - sha256 of E's DATA and of FLAG + FLAG_ROW, taken in the container on
     ext4;
   - equal to the same hashes of the source's DATA and of the version's
     FLAG + FLAG_ROW, read natively on Windows with rang's reader.
   - Not met: void.
3. CASA 6.7.6.14 `applycal` with 2b's own spec (`R\applycal-spec.json`),
   pointed at E. It writes E's CORRECTED_DATA and FLAG. Then
   CORRECTED_DATA → E2C_CASA_CORRECTED_DATA and FLAG → E2C_CASA_FLAG, and
   FLAG and FLAG_ROW are set from the version again (all on ext4).
4. A plain `cp -a` of E to `D:\rang\outputs\e2b-2b-20261115\e2b-2b.ms`,
   checked by sha256 of every file on both sides. E is then deleted.
5. Rang's apply, natively on Windows, on the D: copy:
   - this branch at main `6587e43`, new P;
   - the frozen apply's arguments (`R\rang-run\apply\summary.json`, as
     A1's C3, `parang_flags='none'`);
   - writes `column='E2C_RANG_CORRECTED_DATA'` and FLAG.
6. Comparisons, natively with rang's reader, by 2b's rule (class C: per
   cell ≤ 1e-6 relative or ≤ 11 float32 eps of the cell's largest
   correlation; flags exact):
   - **C9:** E2C_CASA_* against the frozen RANG_CORRECTED_DATA and
     RANG_FLAG of `R\casa\e2b.ms` (row for row) reproduces
     `R\g2b-applycal.json`: 42 cells over class C, max 25.58 eps, 0 flag
     elements differing. Not met: void.
   - **Measure:** E2C_CASA_* against E2C_RANG_CORRECTED_DATA and FLAG.
   - **Beside:** E2C_RANG against RANG_CORRECTED_DATA (P's change alone).
7. The D: copy is deleted after scoring.

Reading:
- 0 cells over class C and flags exact → gate 2b's CASA applycal leg is
  met with the new P (seen; the frozen 2b record stays).
- Otherwise not met, with the count and the maximum reported.

Space:
- E holds about 82 GB with CASA's output, so the vhdx grows by about
  82 GB, and that growth stays until the vhdx is compacted.
- The D: copy takes about 82 GB and rang's column about 36 GB.
- D: had 496 GB free before; the expected low point is about 296 GB.

Booking:
- the copy and CASA at 2 slots, with 8 and 12 GB;
- the hashes and comparisons at 1 slot, 4 GB;
- rang's apply at 4 slots, 16 GB.

### 9.25 9.24 measured, 2026-11-15: gate 2b met on the full MS with the new P

Receipts in [results/e2b-misses/c2b/](results/e2b-misses/c2b/):
`hash_src.json`, `make.json`, `casa-result.json`, `casa_done.json`,
`apply.json`, `c9.json`, `g2b-new.json`, `p-change.json`, `runs.log`,
`disk.log` and `e-ext4.sha256`.

Runs, all rc 0 after one harness fix:
- the source hash took 946 s (native);
- the ext4 copy E took 665 s;
- CASA applycal took 336 s, against 1,061 s over 9p in the original 2b;
- the copy-out of 68 GB, with sha256 on both sides, took 1,025 s;
- rang's apply took 353 s (native);
- the three comparisons took 271–349 s.

Harness fix: the first `make` stopped at once. TaQL resolved `$s` to a
variable inside `taql` itself; it was renamed to `$srctab`, and nothing
had been written.

Controls (all met):
- **C11:** E's DATA and FLAG + FLAG_ROW hash equal to the source's DATA
  and the version's flags, read natively. 272,916 rows.
- **C9:** CASA's applycal on E against the frozen RANG_CORRECTED_DATA
  reproduces `R\g2b-applycal.json` exactly: 408,827,131 compared cells,
  42 over class C, max 25.5827 eps, 0 flag elements differing.
- The file sha256 lists of E and its D: copy are equal.

| Comparison | Cells over class C | Max eps of cell max | Flag elements differing |
| --- | --- | --- | --- |
| **CASA applycal against rang's apply with the new P (measure)** | **0** of 408,827,131 | **7.06** | **0** |
| CASA against rang with the old P (C9 = frozen 2b) | 42 | 25.58 | 0 |
| rang new P against rang old P (beside) | 28 | 26.49 | 0 |

**Outcome: met.** On the whole E2-B MS, gate 2b's CASA applycal leg
meets class C with the new P: 0 cells over 11 eps, a maximum of 7.06 eps,
and flags exact.
- This is a seen reading. The frozen 2b record (42 cells) stays.
- The 42 cells of 9.3 were P's convention, as 9.16 showed on the mini
  MS.

Space:
- D: went from 496 GB at the start to a low of 407 GB with the D: copy
  and rang's column, and is back to 508 GB after the copy was deleted.
- E (68 GB) was deleted on ext4, but the vhdx keeps the size it grew to
  until it is compacted.
- `R\casa\e2b.ms` was only read.

### 9.26 A3, Gpol on CASA's phase-only estimator (`calibrate.casa_phase_weights`), frozen 2026-11-15 (before the code)

Committed as 9.21 at `ba26fb2`. Renumbered 2026-11-15 on the
coordinator's word: main's A5 holds 9.21–9.22 and gate 2b's full-MS arm
9.24–9.25, and 9.23 is left unused. Only the numbers changed.

Branch `e2b-gpol` from main `02631b8`. Section 2's proposal made exact; where
this departs from it, it says so. **Seen** (A0 6.6): every E2-B Gpol number
was read before. Nothing here changes the frozen E2-B record. A null result
is a valid outcome and is recorded as such.

**CASA's estimator, read from source** (CASA's synthesis code as carried in
NRAO's LibRA, `github.com/ARDG-NRAO/LibRA` at `7925a46`; CASA 6.7.6.14 is
the oracle that is run). In `Calibrater::genericGatherAndSolve`
(`Calibrater.cc` 3342–3381, 3546, 3601) the solve's iterator is built as:
1. `addCalForSolving`: `CalSolvingVi2` resets the weights from SIGMA, then
   `VisEquation::collapse2` (`VisEquation.cc` 486–537) corrects the data by
   the lower terms, corrupts the model by the higher ones, and for a
   normalizable term calls `divideCorrByModel` (548–): per row, channel and
   correlation with |M| > 0, `X = R/M`, `W = w|M|²`, `M = 1`;
2. `addChanAve` (G-type terms are unchannelized, so all channels): the
   weighted average of X;
3. `addTimeAve` (the solint or `preavg`): the weighted average in time;
4. per solution, after gathering, `SDBList::enforceAPonData('P')`
   (`SolveDataBuffer.cc` 186–): each unflagged averaged datum is divided by
   its amplitude and its weight multiplied by amp².

So for calmode `p` the datum the solver sees is `X̄/|X̄|` with weight
`W̄|X̄|²`, where `X̄ = Σ w M* R / Σ w|M|²` over the channels and times of the
average and `W̄ = Σ w|M|²`. This corrects section 2 item 1: the amplitude
normalisation acts on the averaged datum, not per channel (net weight
`|Σ w M* R|² / Σ w|M|²`, not `Σ w|R|²`). Both averages are linear and
weighted, so their order (CASA: channels, then time; rang: time, then
channels) gives the same X̄.

**Implementation (frozen before it is written).**
- Key `calibrate.casa_phase_weights` (bool, default false; out of the stage
  hash at its default, as `average_freq`). Off is byte-identical.
- It requires `calibrate.average_freq: true` and is refused without it:
  CASA always averages a G-type solve over the channels, and the key's
  normalisation is defined on the averaged datum. It acts on calmode `p`
  solves only (in E2-B's recipe, Gpol alone); `ap` solves are unchanged.
- Input conditioning in Python beside `frequency_averaged`, no kernel
  change. With unit model, the `phase` kernel (`core/src/cal/diag.rs`) scales
  data to |M| = 1 and normalises by `1/|J|²` = 1, so each datum enters with
  the weight it is given. Steps in `cal_gain`:
  - in `_Field.prepare`, after the pre-apply and P: on the parallel hands,
    `X = R/M` and `w|M|²` where |M| > 0; weight 0 and flagged where M = 0;
    model 1. Cross hands untouched (the kernel zeroes them, and a flagged
    cross hand would drop the whole cell, `solve::data_flags`). The row
    weights that set the solution TIME are taken before this step;
  - time averaging (`average_time`) and `frequency_averaged` unchanged;
  - after them: `X̄/|X̄|`, weight × |X̄|² on the parallel hands; flagged where
    |X̄| = 0.
- Known remaining difference, not addressed: rang flags a whole cell when
  either parallel hand is flagged; CASA keeps the other hand.
- The SNR scale changes with the weights, so `minsnr` can flag differently:
  Gpol solution flags that differ are reported in every comparison.

**Data and arms.** One harness per data set; every rang arm on a data set
is scored against the same CASA Gpol. Scorer: `e2avg_common.term_diff`
(`phase`), median of |Δφ| over (interval, antenna, hand) unflagged in both;
both tables must have equal interval counts. Arms on each set:
`T` = `average_time` only (the frozen arm's estimator), `F` = `T` +
`average_freq` (the amended arm's), `K` = `F` + `casa_phase_weights`.
CASA's call: `e2_casa3b.casa_calls`'s Gpol (G, calmode p, solint 60s,
parang, uvrange >150, minsnr 3, minblperant 4, refant m022,m023,m024 flex).
CASA 6.7.6.14 (`rang-o-casa`, docker in WSL) on private ext4 copies under
`~/e2b-gpol-20261115/`; rang (this branch's extension) on private copies
in `D:\rang\outputs\e2b-gpol-20261115\`. `R/casa/e2b.ms`,
`D:\rang\data\e2-b\e2b.ms` and `luno4.ms` are only read. Copies are
deleted when scored.

1. **Simulation (S).** Field 0 rows of `luno4.ms` (LUNO scan 1, 4,096
   channels; its UVW, times and antennas), RECEPTOR_ANGLE −90, FLAG all
   false, WEIGHT, WEIGHT_SPECTRUM and SIGMA 1. Model: CASA `setjy` manual,
   an unpolarised point at the phase centre, I = 14.7172 Jy at 1.47 GHz,
   spix (−0.4507, −0.1798, 0.0357) (X286 without its polarisation), into
   MODEL_DATA; rang reads the same column. Data, generated in CASA's Python
   with seed 20261115:
   `V_pq = g_p (M + C) g_q*` on the parallel hands and 0 on the cross hands,
   plus complex Gaussian noise σ = 0.3 Jy per part on all four;
   - `C`: an unpolarised point, 1.5 Jy at 1.284 GHz, spectral index −1.0,
     offset (−1.6″, −2.0″) in (l, m) (3C 286's companion is about 2.5″
     away; here it makes the point model wrong on the long baselines);
   - `g`: per antenna and hand, unit amplitude, phase uniform on (−π, π]
     plus 0.2 rad × sin(2π t / 600 s + θ), θ uniform.
   - S-res is that; S-pt is the same with C = 0 (the control).
   - Polarisation is left out on purpose: P is then the identity on both
     components and both sides, so the arm tests the weighting under a
     resolved source and a spectral mismatch, not P (section 9.16's domain).
2. **LUNO dev (L).** `luno4.ms` (scans 1–2 only, 2 Gpol intervals, FLAG as
   the dry run left it), as read only. CASA's K, G, B of the chi-offset
   arm `casa-m90` (the same MS, RECEPTOR_ANGLE −90) are pre-applied on
   **both** sides; rang's own K, G, B of that dry run no longer exist
   (`e2-20261110-11-avg` was deleted). So L is the estimator alone. It is not
   the harness behind 0.250° and 0.108° (e2-average-freq.md 3), and those
   numbers are not expected to reproduce. CASA Gpol is re-solved on an ext4
   copy of field 0's rows (`setjy` X286). Rang reads `luno4.ms`'s MODEL_DATA,
   which must equal CASA's `setjy` model of the copy (max relative
   difference reported; ≤ 1e-6 or L is void).
3. **E2-B scan 17 (X).** Field 0's rows (118,104, rows 0–118,103, scan 17) of
   `D:\rang\data\e2-b\e2b.ms` (DATA never written), FLAG and FLAG_ROW from
   `R/casa/e2b.ms.flagversions/flags.rang_apply_20261112T013707Z` ("flags
   before apply", which is what rang's Gpol saw: the only calibrate steps
   after `extendflags` that touch field 0 are Gpol, KCROSS and Xf, which
   write no data flags; the X0 control below checks this).
   - Rang: MODEL_DATA written on its copy by `calmodels.set_model` with
     `caracal_xcal('3C286')`, as the chain did; K, G, B the frozen tables
     `R/rang-run/calibrate/{K,G,B}`; `receptor_angle` −90°; unit weights,
     8 GiB budget, as the frozen run.
   - CASA: RECEPTOR_ANGLE −90 and `setjy` X286 on its copy. Gpol solved
     three times on the same copy, by pre-applied K, G, B:
     - **CM**, A2's matched case `a2/match-ones/tables/{K,G,B}`: **the
       oracle the decision reads** (section 2's confound);
     - **CC**, the archived 3b tables `R/casa/tables/{K,G,B}`: the harness
       control;
     - **CR**, rang's frozen `R/rang-run/calibrate/{K,G,B}`: descriptive; it
       isolates the estimator (both sides pre-apply the same tables).
   - The two models (rang's on its copy, CASA's on its copy) must agree
     (max relative difference reported; ≤ 1e-5 or X is void).

**Controls, read before any arm's score.**
- **X-s, scorer:** `term_diff` on the archived tables gives
  `R/rang-run/calibrate/Gpol` against `R/casa/tables/Gpol` = 0.278° and
  `RA/rang-run/calibrate/Gpol` against `RA/casa/tables/Gpol` = 0.124°
  (within 1e-3° of `R/g3b.json`, `RA/g3b.json`).
- **X0, rang harness:** arm T on X reproduces `R/rang-run/calibrate/Gpol`
  (max |Δφ| ≤ 1e-4°, flags equal).
- **XC, CASA harness:** CC reproduces `R/casa/tables/Gpol` (median ≤ 1e-3°,
  flags equal).
- **LC, CASA harness:** CASA's L re-solve reproduces
  `casa-m90/tables/Gpol` (median ≤ 1e-3°, flags equal).
- **S-pt:** arms F and K each within class B of CASA on S-pt (median
  ≤ 0.1°). If not, S is void and the harness is fixed first.

A failed control voids its data set's reading; the others still count.

**Hypothesis.** With the key (arm K), rang's Gpol meets class B against
CASA's (median ≤ 0.1°) on S-res, L and X (against CM).

**Frozen tolerance:** class B, Gpol phase median ≤ 0.1° (A0 6.2, as E2-B's
gate 3b). Not loosened.

**Decision rule** (on arm K; arms T and F are reported beside it):
- **S fails** (K misses on S-res, or S-pt fails): the port is not CASA's
  estimator. Stop: no E2-B decision is read; X is reported only. *(Added at
  this freeze.)*
- **S has no power** (F already meets class B on S-res): S cannot tell the
  estimators apart. Reported; the rule reads L and X alone. *(Added.)*
- **Met on L and X:** the key becomes the E2 configuration's for the next
  unseen leg (E2-A has no polcal, so E3 or the reserve). The default stays
  false until then.
- **Met on X, not on L:** reported as found. L is the estimator alone, so a
  miss there with a pass on S puts the remaining difference in the data
  (the slice, its flags); it is described with the per-antenna table.
  *(Added.)*
- **Met on L only:** a documented limitation, with X's per-antenna table.
- **Met on neither:** a documented limitation; the key is not adopted.
- **L has no power** (F already meets class B on L): L is reported and the
  rule reads S and X. *(Added.)*
- CR is reported, not decided on. Section 2 said X's reading is not used if
  A2's matched case left the composites outside class B; A2 (9.4) met them,
  so it is used.

E2-B is solved with the key once, as frozen. Any later variant (another
averaging order, another flag rule) is post hoc and labelled so.

Cost: code about half a day. S about 0.3 CPU-hours, L 0.2, X about 1
(three CASA solves and three rang arms on 118,104 rows of 4,096 channels).
Disk: about 30–40 GB per field-0 copy of X, about 10 GB per copy of L and S;
at most four copies at once (D: holds WSL's ext4 too), with at least 150 GB
left on D:.

### 9.27 A3 measured, 2026-11-15: met on L and X; S and L without power

Committed as 9.22 at `c9d17ba`; renumbered with 9.26 (2026-11-15).

Runs:
- Code: this branch at `55f7b0b` (the key, committed after 9.26 at
  `ba26fb2`), extension built by `check_all --quick` into the worktree's
  `.venv`.
- Scripts: `a3_spec.py`, `a3_casa.py`, `a3_run.sh` (WSL, CASA 6.7.6.14 at
  OMP 1, 1 slot each) and `a3_rang.py` (Windows). Outputs in
  `D:\rang\outputs\e2b-gpol-20261115`; receipts in
  [results/e2b-misses/a3/](results/e2b-misses/a3/) (`a3.json` scores and
  controls, `scorer.json`, `models.json`, each set's CASA `result.json`,
  `spec.json`, `base.json` and rang `arms-*.json`).
- Copies: L's and S's field-0 base (20,000 rows, 8.6 GB) and X's (118,104
  rows, 22 GB), each a CASA deep copy with source rows checked
  (`base.json`: rows match the source, contiguous from row 0). X's FLAG
  from the flag version: 118,104 rows written. All copies were deleted after
  scoring.

Controls (all met):

| Control | Measure | Value | Bound |
| --- | --- | --- | --- |
| X-s, scorer | frozen / amended archived Gpol | 0.27808° / 0.12356° (equal to `g3b.json`) | within 1e-3° |
| X0, rang harness | arm T on X against `R/rang-run/calibrate/Gpol` | max 1.7e-6°, flags equal | max ≤ 1e-4° |
| XC, CASA harness | CC against `R/casa/tables/Gpol` | median 5.2e-6°, max 6.5e-5°, flags equal | median ≤ 1e-3° |
| LC, CASA harness | L re-solve against `casa-m90` Gpol | median 0.0, max 4.1e-5°, flags equal | median ≤ 1e-3° |
| S-pt | F and K against CASA, point model | 9.4e-5° and 1.7e-6° | median ≤ 0.1° |
| Models | rang's against CASA's `setjy` model, L / X | max relative 2.1e-11 / 2.5e-11 | 1e-6 / 1e-5 |

Gpol phase against CASA (median / p95 / max, degrees; 1,060 solutions on X,
148 on L, 224 on S; equal interval counts on every pair, no solution flag
differs except one on L arm F):

| Set (CASA oracle) | T (`average_time`) | F (+ `average_freq`) | **K (+ `casa_phase_weights`)** | Class B on K |
| --- | --- | --- | --- | --- |
| S-res (CASA on the same MS) | 0.0046 / 0.025 / 0.028 | 0.0020 / 0.010 / 0.012 | **1.6e-6 / 5.0e-6 / 8.1e-6** | met |
| S-pt (control) | 1.6e-4 / 4.9e-4 / 6.7e-4 | 9.4e-5 / 2.8e-4 / 4.0e-4 | 1.7e-6 / 5.7e-6 / 1.4e-5 | met |
| L (CASA's K, G, B both sides) | 0.162 / 0.69 / 1.08 | 0.073 / 0.32 / 0.46 | **1.1e-4 / 4.8e-4 / 1.9e-3** | met |
| **X against CM** (A2's matched K, G, B) | 0.270 / 2.18 / 2.92 | 0.120 / 0.96 / 1.22 | **3.8e-4 / 1.5e-3 / 2.7e-3** | **met** |
| X against CR (rang's K, G, B both sides; descriptive) | 0.271 / 2.18 / 2.92 | 0.120 / 0.96 / 1.22 | 1.8e-4 / 4.5e-4 / 7.2e-4 | – |

Against the simulation's true gains (m022's gauge; descriptive), CASA and
every rang arm are within 0.004° of each other: medians 0.444° (CASA) and
0.445–0.447° on S-res, 0.148° on S-pt, with the truth taken at the solution
TIME. Post hoc, with the true gain averaged over each solution's interval
(rang's INTERVAL; CASA writes 0, so its row cannot be read this way), rang's
S-pt median falls to 0.056° and S-res to 0.354–0.359°. So part of the
distance to the truth is the frozen 0.2 rad drift within a 60 s interval,
and on S-res the wrong model. The rest is not attributed; noise alone
predicts about 1e-3°. None of this bears on the CASA comparison.

**Outcome under the frozen rule: met on L and X; the key becomes the E2
configuration's for the next unseen leg** (E2-A has no polcal, so E3 or the
reserve). The default stays false until then.

Two power branches apply, as frozen:
- **S has no power.** F already meets class B on S-res (0.0020°): the
  frozen companion (1.5 Jy at 2.6″, about 10 % of I) moves the two
  estimators apart by far less than 0.1°. S is reported, and the rule reads
  L and X.
- **L has no power.** F already meets class B on L (0.073°). L is reported,
  and the rule reads S and X.
- Both together leave X as the deciding set. X is met by a factor of 260
  (0.00038° against 0.1°). L and S are also met on K. Neither power branch
  says what happens when both apply; this reading (X decides) is stated
  here, not frozen.

What the numbers show:
- On every set, K agrees with CASA 2–4 orders closer than F:
  - 1.6e-6° on the simulation, about float32 rounding (inferred, not
    shown);
  - 1.1e-4° on L, where both sides apply the same tables;
  - 1.8e-4° on X with the same tables (CR).
  So the port is CASA's estimator. Section 2's weighting and averaging
  order were the whole of the Gpol miss.
- The 3b confound (section 2 item 3) is small once the estimator matches:
  X against CM is 3.8e-4°, against CR 1.8e-4°. Under T and F it was
  invisible beside the estimator difference (0.270° and 0.120° against both).
- On X, arm F reproduces the amended miss (0.120° against the archived
  0.124°, which also had the amended arm's other inputs) and arm T the
  frozen one (0.270° against 0.278°). The residual differences are CASA's
  K, G, B (CM against the 3b run's).
- Flags: 0 of 1,060 Gpol solution flags differ on X in any arm. The
  rescaled SNR did not move `minsnr` here.

Cost: CASA L 1,107 s, S 1,305 s, X 638 s (setjy 115 s, three Gpol solves
165–181 s), peak RSS 1.6–3.7 GB; rang arms L 99–101 s, S 99–115 s, X 503–722
s at 4 threads, peak RSS 2.85 GB on every set (8 GiB budget); copies 728 s
(L) and 1,514 s (X).

## For the coordinator

**After A3 (2026-11-15, branch `e2b-gpol`; 9.26, 9.27):**
- **Met on L and X.** The new key `calibrate.casa_phase_weights` (needs
  `average_freq`; calmode `p` only; default false, off byte-identical) puts
  rang's Gpol at 0.00038° from CASA on E2-B scan 17 (class B 0.1°). It was
  0.120° with `average_freq` alone and 0.270° as frozen. LUNO dev: 1.1e-4°.
  Simulation: 1.6e-6°.
- The simulation and LUNO had no power as frozen (`average_freq` alone
  already met 0.1° there), so X decided. K is 2–4 orders closer than F on
  all three sets.
- CASA's order, read from source: divide by the model per channel, average,
  then normalise the averaged datum. This corrects section 2 item 1 (not
  per-channel `w|R|²`).
- Owner: set `casa_phase_weights: true` (with `average_freq`) in the E3 or
  reserve configuration, as the rule says; whether it becomes the default
  is not decided here.
- Every copy was deleted; the receipts are in `results/e2b-misses/a3/`.

**After 9.22–9.23 (2026-11-15, branch `e2b-2b`): gate 2b is met on the
full MS with the new P.**
- CASA applycal on an ext4 copy against rang's native apply: 0 of
  408,827,131 cells over class C, max 7.06 eps, flags exact.
- C9 reproduces the frozen 2b exactly (42 cells, 25.58 eps), and C11 (the
  copy is exact) is met.
- No write touched `R\casa\e2b.ms` or went over 9p.
- The vhdx may need compacting: it took up to about 70 GB, since freed
  inside ext4.

**After 9.18–9.20 (2026-11-15, branch `e2b-close`):**
- **9.18, gate 3c dirty at ε 1e-6 with `-no-small-inversion` (dated post
  hoc amendment): met on all three fields**, at 2.0e-7, 3.3e-7 and 8.1e-8
  (bound 1e-6). C10 met.
  - One GeMClean run was void through memory over-booking; it was rerun at
    46 GB.
- **9.19, full-MS gate 2b with the new P: not run (harness).** casacore
  and CASA bulk I/O over 9p failed with ENOMEM 6 times.
  - The sixth attempt left `R\casa\e2b.ms` unopenable. It was repaired
    by a rehearsed twin header plus restore, and the column set and
    native hashes equal the originals (9.20).
  - A rerun on ext4 is proposed; it must be frozen first.
  - Gate 2b's only reading with the new P is still the mini MS (9.16).

**After P1 and the 3c reading (2026-11-15, branch `e2b-pcasa`):**
- **P1 (9.15, 9.16): met and adopted.** `parallactic_angle_casa` now
  emulates casacore. It is 1.3e-8 rad from casacore on the held-out field
  rows, and 3.6e-8 on the 432-case fixture.
  - Gate 2b on A1's mini MS: 4.8 eps at most on the 42 cells (class C
    11), against 25.6.
  - Open: the full-MS 2b re-score, and casacore-to-applycal's 2.7e-7.
- **3c dirty with `-no-small-inversion` at ε 1e-4 (9.17, seen):** 2.2e-5,
  2.2e-5 and 2.0e-6. The edge excess is gone; the rest is ε 1e-4. Meeting
  1e-6 needs ε 1e-6 as well (9.12).

**After A4b and A1d (2026-11-15, branch `e2b-pastro`):**
- **A4b (9.11, 9.12): met.** Gate 3c's dirty difference is WSClean's small
  inversion. With `-no-small-inversion`, GeMClean and WSClean agree to
  8.1e-8 of the peak over the full image (J1833−2103, ε 1e-6), against
  2.9e-3 with the default.
  - Owner: rerun 3c's dirty comparison with that oracle setting (seen).
  - A4's 41 GB of images were deleted after scoring; logs and scores are
    kept.
- **A1d (9.13, 9.14): H4 not shown under the rule** (5.5e-7 on field 1,
  against 2e-7; 5.6e-8 on field 2). No fix.
  - Post hoc: casacore's TOPO → HADEC step accounts for 92 % and 98 % of
    P's difference. It applies a zenith-ward "diurnal aberration" and polar
    motion, which astropy's TETE does not.
  - The field 1 residual fits casacore's IAU 1976/1980 precession and
    nutation (0.067″).
  - Owner: emulate casacore in a further arm with pmat76/nut80, or accept
    P's ≤ 7e-6 rad as a documented convention difference.

**After A1c and A4 (2026-11-15, branch `e2b-pastro`):**
- **A1c (9.7, 9.8):** cause not found under the frozen rule. K1 is not
  met: casacore's own parallactic angle matches CASA's applycal within
  2.3e-7 and 2.7e-7 rad, against 2e-7. No fix was made, and
  `parallactic_angle_casa` is unchanged.
  - Post hoc, (e) is exact: casacore's angle is rang's formula on
    casacore's HADEC (h, δ).
  - The 3–7e-6 rad difference comes from about 0.5″ that casacore's APP →
    HADEC step adds to the source's h and δ.
  - It is not sidereal time (0.05″), precession and nutation (0.07″), the
    apparent place (≤ 0.19″) or the latitude.
  - Polar motion has the right size, but neither astropy's HADec nor a
    simple rotation reproduces it.
  - Next step: read casacore's MCDirection APP → HADEC route and freeze a
    candidate.
- **A4 (9.9, 9.10):** edge difference, as frozen. Dirty L∞ is 3.5e-3,
  1.2e-3 and 2.9e-3 at ε 1e-5, 1e-6 and 1e-7 alike (r = 1.000). The inner
  values are also unchanged. So gate 3c's dirty miss is not ε.
  - Proposed G task: WSClean `-no-small-inversion`, or matched padding, on
    J1833−2103 at ε 1e-6, frozen first.
- The ordered fix list below is unchanged apart from these two items.

**After A2, A1 and A1b (2026-11-14, branch `e2b-arms`):**

**After A2, A1 and A1b (2026-11-14, branch `e2b-arms`):**
- **A2 (9.4):** the 3b K/G/B composites miss is closed as an oracle input
  error. On matched flags both composites meet class B; the weights change
  nothing.
- **A1 (9.3):** gate 2b is not shown to be float32 rounding.
  - Under the frozen rule the outcome is "rang difference", with G named.
  - Post hoc, P (the parallactic angle) carries the excess.
- **A1b (9.6):** void as frozen; my C4 bound was below the float32 floor.
  Post hoc, the P difference is about 1e-5 rad and depends on the source
  direction. It is not TIME versus TIME_CENTROID, and not UT1 − UTC.
- **Proposed next step** (not started): a P astrometry arm. It would
  compare rang's `parallactic_angle_casa` against casacore's own
  parallactic angle computed in the container (`me.posangle`, or
  `msmetadata` per antenna and time) at the same rows. That splits
  precession and nutation from the latitude and apparent-place
  conventions.
  - Freeze C4 at about 1e-7, the float32 floor, or extract from a float64
    path.
  - Tolerance 2e-7 rad as in 9.5.
  - If casacore's angle matches CASA's applycal and differs from rang's,
    the fix is in `cal_pol.parallactic_angle_casa`.
- The section 0 rows for 2b and 3b composites carry dated lines.

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

### 9.28 E2-B confirmation of gates 2b and 3c on today's main, frozen 2026-11-16 (before any run)

Branch `e2b-confirm` from main `d2013ea`.

**Decisions, owner delegated to coordinator 2026-11-16** (the owner: "do
whatever you think is best"):
1. The E2-B gate 2b and 3c readings taken after the protocol froze stay
   labelled post hoc: 9.16 and 9.25 (2b with the new
   `parallactic_angle_casa`, following casacore), 9.17 and 9.18 (3c dirty
   with `-no-small-inversion` at ε 1e-6), and 9.22 (3c cleaned with
   GeMClean's joined-IQUV auto-mask). v0.3.0 cites a fresh confirmation
   run under a protocol frozen now, before any run: this section.
2. That confirmation includes gate 3c cleaned with the mask as a new
   frozen arm.
3. `calibrate.casa_phase_weights` (9.26, 9.27) stays an option, with its
   default (false) unchanged. E3's configuration turns it on, because E3 is
   scored against CASA and CARACal. That is E3's work, not this section's.

**Seen.** Every number in 9.16–9.27 is known. The confirmation's job is to
repeat them on today's code under rules fixed before the run, not to be
blind. The frozen E2-B record (section 0, e2-acceptance 7.3–7.5) stays.

**What is left of the inputs (read-only checks, 2026-11-16, before this
freeze; receipt [results/e2b-misses/c3/flags-check.json](results/e2b-misses/c3/flags-check.json)).**
`R\casa\e2b.ms`, its flag versions (with the after-calibrate version
`flags.rang_apply_20261112T013707Z`), `R\wsclean3c-unit` and
`D:\rang\data\e2-b\e2b.ms` were deleted on 2026-11-15 (STATE: E2-B's
copies deleted for E2-A's disk). So 9.24's and 9.18's scripts cannot run as
written. Left:
- `D:\rang\outputs\e3-20261111-input\e2b.ms` (E3-B's input; read only
  here): the converter's MS, 272,916 rows, DATA never written, FEED
  RECEPTOR_ANGLE 0.
- `R\df-flag-snapshot\flags-after-applycal.npz` (written by `e2p_snap.py`
  on 2026-11-12 from `R\casa\e2b.ms` after 2b's applycal): FLAG (CASA's
  applycal output) and RANG_FLAG (rang's FLAG after apply), packed over the
  four correlations, with the row columns.
- R's calibration tables (`R\rang-run\calibrate`), the frozen apply's
  arguments (`R\rang-run\apply\summary.json`) and 2b's spec
  (`R\applycal-spec.json`).
- Archived hashes: `c2b/hash_src.json` (DATA; FLAG + FLAG_ROW of the
  after-calibrate version), `a5-mask/receipts/slim.json` (rang's FLAG after
  apply), `c2b/e-ext4.sha256` (every file of 9.24's E after CASA).

Check (`c3_flags.py check`, native, rang's reader, 570 s under the lock,
1 slot): every input is recovered exactly.
- The snapshot's row columns (ANTENNA1/2, FIELD_ID, SCAN_NUMBER, TIME)
  equal the E3 input's, row for row.
- The E3 input's DATA hash equals `hash_src.json`'s `data_sha256`
  (`5a656501…`): the same DATA as `R\casa\e2b.ms`.
- The snapshot's RANG_FLAG hash equals `slim.json`'s FLAG (`c2609912…`),
  and its FLAG (CASA's output) equals its RANG_FLAG in every element.
- (RANG_FLAG, the E3 input's FLAG_ROW), hashed as `hash_src.json` hashes
  the version, equals its `flag_sha256` (`05c6e545…`). So the frozen apply
  added no flag, and the after-calibrate version is RANG_FLAG with the
  converter's FLAG_ROW. (FLAG_ROW = all of the row's FLAG does not match.)

So 2b's input state is rebuilt hash for hash, and C11 can be kept as it was
frozen. RANG_CORRECTED_DATA (rang's frozen apply output) cannot be rebuilt
with the old P, so C9 is lost (below).

**Route** (scripts in [results/e2b-misses/c3/](results/e2b-misses/c3/):
`c3_flags.py`, `c3_e.py`, `c3_run.sh`, `c3_win.py`, `c3_rang.sh`,
`c3_score.py`, `c3_queue.sh`; adapted from `c2b_*`, the e2b-close `a5_*`
and `a5-mask/`). Code: this branch, which is main `d2013ea` plus this note
and the scripts. Rang's apply and GeMClean run from this worktree's
extension, built by `check_all.py --quick`; the commit is in each receipt.
Outputs in `D:\rang\outputs\e2b-confirm-20261116` (P), ext4 work in
`~/Build/tmp/20261116-e2b-confirm` in WSL.

1. **E on ext4** (`c3_e.py make`). A TaQL copy of the E3 input from a
   read-only mount, as 9.24's make: every row and subtable, the row
   columns, DATA, WEIGHT, SIGMA, FLAG_CATEGORY. FLAG = the snapshot's
   RANG_FLAG, FLAG_ROW the E3 input's, FEED RECEPTOR_ANGLE −90° (2b's
   prep).
2. **Control C11** (inputs exact, as 9.24): E's DATA hash and its (FLAG, FLAG_ROW)
   hash, taken in the container on ext4, equal `c2b/hash_src.json`'s
   `data_sha256` and `flag_sha256` (the source DATA and the after-calibrate
   version). Not met: void, stop.
3. **CASA 6.7.6.14 `applycal`** with 2b's spec (3 calls, one per field,
   calflag, parang, calwt false) on E, then CORRECTED_DATA →
   E2C_CASA_CORRECTED_DATA and FLAG → E2C_CASA_FLAG, and FLAG and FLAG_ROW
   rebuilt again (all on ext4, as 9.24). Every file of E is hashed;
   the list is compared with `c2b/e-ext4.sha256` and reported (not gated:
   the HISTORY subtable and lock file differ by construction).
4. **Per field** (J1833−2103, J1939−6342, J1331+3030, one at a time, so
   that D: holds one field's copy):
   1. its rows of E (row columns, DATA, FLAG, FLAG_ROW, WEIGHT, SIGMA,
      FLAG_CATEGORY, every subtable) → an ext4 table, WEIGHT set to 1
      (gate 3c's matched state; no WEIGHT_SPECTRUM);
   2. `cp -a` to `P\f<FID>.ms`, sha256 of every file on both sides equal
      (not met: void);
   3. rang's apply, native, today's main (new P), with the frozen apply's
      arguments for that field (as 9.24 step 5: `parang_flags='none'`,
      `column='E2C_RANG_CORRECTED_DATA'`, FLAG written);
   4. `cp -a` back to ext4, sha256 of every file on both sides equal (not
      met: void). GeMClean reads the D: copy and WSClean the ext4 copy:
      the same bytes;
   5. gate 2b's comparison on that field (below), in the container on ext4;
   6. gate 3c's four runs (below), then the field's scores; then the
      field's FITS images, its D: copy and its ext4 copies are deleted (the
      logs, mask records, time files and scores are kept).
5. E is deleted after the last field.

**Gate 2b, CASA applycal leg** (A0 class C, the original gate's tolerance,
unchanged):
- Measure: per field, E's E2C_CASA_CORRECTED_DATA and E2C_CASA_FLAG
  against the field copy's E2C_RANG_CORRECTED_DATA and FLAG, row for row
  (TIME, ANTENNA1, ANTENNA2 asserted equal), by 2b's rule
  (`e2p_compare.py`, as `c2b_win.py`): a cell is over class C when any
  unflagged correlation differs by more than max(1e-6 × |rang|,
  11 float32 eps × the cell's largest |rang|); flags must be exact.
  Pooled over the three fields.
- Reported beside, not decided on: each side's flags against the
  snapshot (CASA's FLAG and rang's FLAG after apply as frozen).
- **Met**: 0 cells over class C and 0 flag elements differing. Otherwise
  **not met**, with the count, the maximum eps and the maximum relative
  difference.
- The other 2b legs (casacore, listobs, flagmanager, WSClean `-niter 0`,
  dask-ms) are not rerun: they read the frozen chain's MS, which no longer
  exists, and were met as frozen (e2-acceptance 7.3).
- Lost control: C9 (CASA on the copy reproduces the frozen 2b, 42 cells)
  needs the deleted RANG_CORRECTED_DATA. C11 (the inputs, hash for hash)
  and step 3's file list (CASA's output columns against 9.24's) take its
  place.

**Gate 3c** (A0 6.1 3c; GeMClean against WSClean 3.7 of the same column).
Common settings, both arms, as gate 3c's frozen image settings with 9.18's
and 9.21's oracle changes: 2048² at 2″, briggs 0, 8 joined channels
(`-channels-out 8 -join-channels`), `-pol IQUV -join-polarizations`, field
FID, data column E2C_RANG_CORRECTED_DATA (rang's apply output of today's
main), FLAG = rang's FLAG after apply, unit weights (WEIGHT = 1; GeMClean
also `-unit-weights`), `-no-update-model-required`. GeMClean `-scans
17,18,19,20 -j 4`, `python -m rang.gemclean` from this worktree. WSClean 3.7
(`rang-wsclean-native:3.7`) `-gridder wgridder -no-small-inversion`.
- **3c dirty:** `-niter 0`, wgridder ε 1e-6 in both arms (WSClean `-j 2`).
  - Measure (`a4_score.linf`, gate 3c's `dirty_linf`): per output channel
    and MFS and per Stokes, max |GeMClean − WSClean| over the full image,
    over the peak |I| of WSClean's dirty image of that channel. The 5 %
    border and inner two-thirds are reported.
  - **Met** when ≤ 1e-6 on all three fields (A0, unchanged).
- **3c cleaned, new frozen arm (decision 2):** `-niter 1000000 -mgain 0.9
  -auto-threshold 3 -auto-mask 5` (A0 rule 6's mask, default
  `-auto-mask-nmiter`), wgridder ε 1e-4 (gate 3c's frozen ε) in both arms
  (WSClean `-j 4`).
  - Measures: `e2_score3c.py`'s `score_field`, unchanged, per field, pooled
    as its `main` pools. The source set is recomputed from each pair's
    images.
  - Tolerances (A0 3c, unchanged, as in `e2_score3c.py`): compact-source
    flux ratio median within 0.5 % of 1 and robust scatter ≤ 1 %, pooled,
    n ≥ 3 (else not checked); spectral index median |Δα| ≤ 0.05 over
    sources ≥ 50σ; off-source |model| ratio ≤ 1.6 on each field; on
    J1939−6342, Q, U, V rms and peak near the source ≤ 1.2 × WSClean's.
    Q/Q₀ stays not checked.
  - **Met where checked** when every checked gate is met (as the original
    gate: never "met" while Q/Q₀ is unchecked). Otherwise **not met**, with
    each measure.
  - Reported beside: both arms' σ per major iteration, the finishing
    iteration, the number of major iterations, wall time and peak memory.
- The unmasked cleaned arm is not rerun. Its miss stands as frozen (7.4)
  and as reproduced by A5's control C (9.22).
- Lost control: C10 (WSClean on the ext4 copy reproduces the archived
  `R\wsclean3c-unit`) needs deleted images. The two copy checks in step 4
  take its place: both arms read the same bytes.

**Decision rule.**
- Each of gate 2b (CASA applycal leg), 3c dirty and 3c cleaned (masked) is
  read on its own, as met, not met or void, with its numbers.
- All three met: v0.3.0 cites 9.28 for E2-B gates 2b and 3c. The post hoc
  readings stay as they are.
- Any not met: recorded with its numbers beside the post hoc reading it
  fails to repeat. v0.3.0 then cites the miss as a known limitation, and no
  amendment is made in this section.
- Void (a control not met, a run's exit not 0, a copy that differs): rerun
  once from the failed step. If it is void again, it is reported as void.
  A harness fix that changes no measure or setting is dated here as post
  hoc.

**Booking** (heavy lock, main checkout's copy; WSL jobs from the WSL side):
- E and the field subsets: 2 slots, 8 GB. CASA: 2 slots, 12 GB.
- Copies and hashes: 1 slot, 2 GB. Comparisons: 1 slot, 4 GB.
- Rang's apply: 4 slots, 16 GB.
- WSClean: 2 slots, 4 GB (A5: 1.1–1.6 cores, at most 2.0 GB).
- GeMClean: 4 slots. 46 GB for every run except J1833−2103 cleaned, which is
  booked at 16 GB: gemclean-memory 5 measured 9.2 GiB on A5's argv after
  #32. The other runs are not measured after #32. A 46 GB ticket is put in
  only once it fits, so it does not block the queue's head.

**Disk.** D: had 251 GiB free at the start. E2-A's `e2_diskguard.py` stops
E2-A's own job below 165 GiB, so this queue keeps D: at or above 180 GiB.
Before each field it checks that the field's copy (about 31, 32 and
10 GiB with rang's column) plus 12 GiB of FITS fits above that, and stops
if not. The expected low point is about 205 GiB. Ext4 holds E (about
75 GB) and one field copy, inside the vhdx's free space (325 GB file,
178 GB used).

**Harness fix, 2026-11-16, post hoc (no measure or setting changed).**
Field 1's copy-out (14:46) failed while WSL's `sha256sum` read the D: copy
over 9p ("Cannot allocate memory", as in 9.20). No score had been read for
field 1, and its rang apply had not run. The D:-side hashes of the copy-out
and copy-back are now taken natively on Windows (Git Bash `sha256sum`, same
file-list format) and compared with the ext4 side's. Field 1 is rerun from
its subset step, as the rule allows once.
- The first rerun stopped at the new comparison: Git Bash's `sha256sum`
  writes ` *./` (binary mode) where WSL's writes `  ./`. Every hash was
  equal. The marker is now normalised, and field 1 is rerun from its subset
  step again. This is the same harness fix, and no field 1 score had been
  read.

**Booking amended, 2026-11-16, on the coordinator's word (no measure or
setting changed).** Field 1's GeMClean runs waited from 15:36 in
`fits46`, which waited for at most 2 GB booked on the host. heavy_lock now
backfills and drains for a large head (main `e3a9fa6`), so the pre-wait is
removed and the queue resumes, skipping steps already logged rc 0. The
J1833−2103 runs here peaked at 8.8 GB (dirty, ε 1e-6) and 9.2 GB (cleaned)
of summed tree RSS. Before #32, A5's J1939−6342 and J1331+3030 held
2.2 × J1833−2103, which puts them at about 20 GB now. They are booked at
30 GB, and their measured peaks are reported.
