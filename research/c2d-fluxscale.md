# C2d: the flux-scale term F and `fluxscale`

Task C2d of [finish-plan.md](finish-plan.md) (C2, "C2d (F, `fluxscale`)"), step 6 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6 (T5 in its term list, row 8 of its solve
sequence). Branch `fp-c2d-fluxscale`, from main `f6c53a6`.
**Status: protocol only (sections 0 to 6), committed before any comparison. Nothing is measured yet.**
Results will be added below section 6, never edited into it; this status line is the only edit allowed above it.

## 0. What was read before this protocol

Read, not recalled:

- **CASA C++ at the oracle's own tag.** `SolvableVisCal.cc` and `Calibrater.cc` of casa6 at tag `6.7.6.14`,
  fetched from NRAO's server into the ignored `outputs/c2d-sources-20261106/casa6-nrao/` (SHA-256 in
  `SHA256SUMS` there). `SolvableVisJones::fluxscale` (1,239 lines) and both `Calibrater::fluxscale`
  overloads are **identical** to C1's 2023 mirror, so unlike C1's [M] items this part is read at the oracle's
  version.
- **casacore 3.7.1** (`MaskArrMath.{h,tcc}`, `ArrayMath.h`, `GenericL2Fit.tcc`, `LSQFit.cc`, `LSQFit2.tcc`), in
  `outputs/c2d-sources-20261106/casacore-3.7.1/`. The casacore inside the CASA image is not identified, so the
  median and fit rules below are read from 3.7.1 and **the oracle decides** (case P-full64 probes the median).
- `task_fluxscale.py` of casatasks 6.7.6.14 in `rang-o-casa:6.7.6.14` (it also writes the MS HISTORY, so CASA
  needs a writable copy).
- CARACal `8f7bb363` `crosscal_worker.py`: for an `F` term it copies the primary's G table, runs `gaincal`
  with `append=True` into the copy (`smodel=[1,0,0,0]` unless an imaging step came first; K and B pre-applied,
  not G), then `transfer_fluxscale` calls `fluxscale(vis, caltable=copy, fluxtable=F, reference=<fcal>,
  transfer='')` and **nothing else**, so `gainthreshold=-1`, `fitorder=1`, `incremental=False`.

### 0.1 What CASA's `fluxscale` does (this corrects C1's T5 sketch)

C1 wrote "the mean over antennas of the ratio … after median-based cuts". The source says otherwise:

1. **Fields.** The reference fields are the user's; a reference field also listed in `transfer` is dropped from
   the transfer list (logged). `transfer=''` means every field in the table that is not a reference. With a
   non-empty `transfer`, the table is loaded with `FIELD_ID IN [ref + transfer]`, so **other fields' rows are
   not written to the output table**; with `transfer=''` every row is kept. Only `G Jones` and `T Jones` tables
   are accepted.
2. **Median gain per field and spw** (float32): `median` over every unflagged amplitude `|CPARAM|` (both
   hands, all rows of that field and spw). Used only for `gainthreshold`.
3. **Threshold.** With `gainthreshold = t >= 0`, an amplitude enters only if
   `lo·med <= |g| <= (1 + t)·med`, `lo = 1 − t` for `0 < t < 1`, `lo = 1` for `t = 0`, else `lo = 0`. With the
   default `t = -1` every unflagged amplitude enters. **There are no median cuts by default.**
4. **Per antenna and hand**, per field and spw: the unweighted mean of the amplitudes over time (`wt = 1`).
5. **Several reference fields:** per antenna, hand and spw, the mean of the reference fields' means over those
   where it is valid (CAS-4758).
6. **Ratios** `r = mean_transfer / mean_reference` over (hand, antenna) where both are valid and the reference
   mean is positive; the reference spw is `refspwmap[spw]` when given.
7. **Scale and flux per field and spw:** `mgratio = median(r)` over all `nPA` valid (hand, antenna) values,
   **not a mean**; `mgrms = stddev(r)` (ddof 1); `fd = mgratio²`; `fderr = 2·mgrms/√(nPA − 1)`; with
   `nPA = 1` both errors are 0. Note `fderr` has no factor `mgratio`: it is CASA's formula, ported as is.
8. **casacore's median** (`median(MaskedArray)`): for an even count of valid values it takes the mean of the
   two middle values **only when the array's total element count, masked ones included, is <= 100**;
   otherwise the lower of the two. For the ratios the array is (hand, antenna): 2 × 64 = 128 elements for
   MeerKAT, so the lower middle value; 2 × 16 = 32 for A1 small, so the mean.
9. **Spectral fit** per transfer field over its valid spws (`nValid`): with `nValid = 1`, `fitFluxd = fd` at
   that spw's frequency and the coefficients are zero (no fit). Otherwise a weighted linear least-squares
   polynomial of order `fitorder` in `x = log10 f − mean(log10 f)` to `y = log10 fd` with `σ = fderr/fd`;
   points with `σ = 0` are skipped (`GenericL2Fit::buildMatrix`); `fitorder < 0` becomes 1; **with
   `nValid = 2` and `fitorder > 1` the order is left at 0** (an unset branch in the source). Errors are
   `√(cov_ii)·√(χ²/max(1, n − m))` (`LSQFit::getErrors`, `CHI2`), the covariance is the unscaled inverse normal
   matrix, `fitFluxd = 10^c0`, `fitFluxdErr = ln 10 · 10^c0 · err0`, `fitRefFreq = 10^mean(log10 f)`.
   The frequency of a spw is `CHAN_FREQ[nchan/2]` of the caltable's window (one channel for G).
10. **Output (`incremental=False`).** For every row of a (spw, transfer field) with a scale,
    `CPARAM /= Complex(Float(mgratio))`; reference rows, other fields, PARAMERR, SNR and FLAG unchanged.
    Duplicate (time, field, spw, antenna) rows raise. `incremental=True` writes a different table (`1/mgratio`
    per field); CARACal does not use it.

## 1. Scope

- **F as CARACal builds it:** G on the secondary field(s) against a unit point model (`smodel=[1,0,0,0]`), with
  C2a's `rang.cal_gain.gaincal` (unchanged rules), appended to a copy of the primary's G table; then
  `fluxscale(reference=<fcal>, transfer='')`, producing the F table (a `G Jones` table CASA reads) and the
  fitted flux density and spectral index of each transfer field, in a record shaped as CASA's return value.
- **Rust:** `core/src/cal/fluxscale.rs` (new file): the statistics of 0.1 items 2 to 9 (amplitudes, medians
  with casacore's rule, threshold, means, ratios, the polynomial fit). Bindings in a new
  `core/py/src/cal_fluxscale.rs`, registered at the end of `lib.rs`'s module init.
- **Python:** `python/rang/cal_fluxscale.py`: the unit model (`smodel`), `append` (CASA's row append, with its
  duplicate check), `fluxscale` on CalTables (field and spw bookkeeping, the output table, the record) and a
  `bootstrap` helper for the CARACal sequence. `rang.cal_gain.gaincal` gains a `spw` argument (one window per
  call; a pre-apply is refused when the MS has more than one window), so per-spw solves exist for the
  spectral fit.
- **Not in scope:** `antenna`, `timerange`, `scan` selection, `incremental=True`, `display` and `listfile`
  (refused, except `listfile`, which is not written); the A step (CARACal's flagging of the corrected
  calibrator) and C1 step 6's Tricolour item, which `core_config.TASKS` and C1 attach to C2d but this brief
  does not (section "For the coordinator"); the command wiring (W2 refuses F and secondary models; the
  refusal text is the coordinator's); `combine`, `preavg` and the rest that C2a left out.

## 2. Oracles and classes

- **Class P, the port, on identical input.** CASA's own merged G table (copy of the primary G plus the
  appended secondary rows, made by CASA `gaincal`) goes to both CASA `fluxscale` and rang's `fluxscale`.
  A deterministic function of the same float32 amplitudes, so:
  - `numSol` and `freq` exact; the set of (field, spw) with a flux exact;
  - `fluxd`, `fluxdErr` within `1e-9` relative (absolute `1e-12` where the value is below `1e-12`);
  - `fitFluxd`, `fitFluxdErr`, `fitRefFreq`, `spidx`, `spidxerr`, `covarMat` within `1e-6` relative
    (absolute `1e-12` near zero); they go through CASA's `χ²` by subtraction, so they are not held to `1e-9`;
  - the output table: the same rows (as keys TIME, FIELD_ID, SPECTRAL_WINDOW_ID, ANTENNA1); every CPARAM
    element within `2 ε32 |c|` of CASA's (ε32 = 2⁻²³; the count of bit-identical values reported); FLAG,
    ANTENNA2, SCAN_NUMBER, INTERVAL, PARAMERR, SNR exactly equal to CASA's.
- **Class B, end to end** (C1 step 6 and A0's F tolerance): rang's G (C2a) on primary and secondaries plus
  rang's `fluxscale`, against CASA `gaincal` plus `fluxscale` on the same copy:
  - `fluxd` per (transfer field, spw) within `1e-3` relative of CASA's; the scale `mgratio = √fd` within
    `1e-3`; `fitFluxd` within `1e-3` relative; `spidx[1]` (the spectral index) within `5e-3` absolute;
    `numSol` equal; the set of (field, spw) with a flux equal;
  - the F table on the transfer rows: parallel-hand baseline products (C2a's `baseline_products`) relative
    difference median `<= 7e-4`, p95 `<= 3e-3` (C2a's class B); reference rows equal to rang's own input G
    (unchanged by `fluxscale`);
  - reported, not gated: `fluxdErr`, `spidxerr`, `fitFluxdErr` (scatter statistics of each solver's gains),
    row TIME (C2a's open TIME gate, owner decision 9).
- **Class T, against A1's simulated truth** (SIM-GCAL only; the polarised 3C286-SIM is a transfer field in
  P and B but not here, its unit-model gains absorb rotating Q). The expected flux density of spw `k` is
  `E_k = Σ w Re(M) / Σ w` over SIM-GCAL's unflagged parallel-hand cells of that spw, with `M` A1's reference
  `P_p M P_qᵀ` (C2a section 8: `I(ν) cos(q_p − q_q)` here) and `w` the solve weight. The expected spectral
  index `α_E` and flux `S_E` are CASA's fit (0.1 item 9) applied to `(f_k, E_k)` with rang's own `fderr_k`
  and the run's `fitorder`.
  - **Noise-free twin:** every `fd_k` within `2e-4` relative of `E_k`; `fitFluxd` within `2e-4` of `S_E`;
    `|α − α_E| <= 1e-3`.
  - **With noise:** every `fd_k` within `1e-3` relative of `E_k`; `fitFluxd` within `1e-3` of `S_E`;
    `|α − α_E| <= 5e-3`. Reported: `z_k = (fd_k − E_k)/fderr_k`, and the difference from the nominal
    `S(ν)` (4 Jy at 1.4 GHz, α −0.6: about 1e-3 from averaging over a spw, not gated).
  - The thermal error of `fd_k` is about 1e-4 here (sigma 0.0287 Jy, ~480 samples per antenna and scan, ten
    scans, a median of 32 ratios), so the noisy bounds are about 10 standard errors; they test for bias
    beyond noise, not the noise.
- **Class C, CASA reads rang's F table:** CASA `applycal` with A1's truth K and B and rang's F table
  (`gainfield=['', '', 'nearest']`, `interp` linear, `calwt=False`) on SIM-GCAL and SIM-TARGET of a fresh copy,
  against `rang.applycal` with the same three tables on another: C4b's criteria 1 and 2 (CORRECTED_DATA per
  correlation `<= 1e-6 |c|` or `<= 11 ε32 max_k |c_k|`, every cell of the selected rows; FLAG exact).

## 3. Data and settings

All copies and outputs under `/mnt/d/rang/outputs/c2d-20261106-NN/` (one per run), heavy steps under
`flock ~/.rang-heavy.lock`; inputs read in place, read-only.

- **slice2:** O-CASA's slice (`outputs/o-casa-20261030-01/work.ms`, LUNO 1934−638, four stations, one scan of
  32 integrations, 2,048 channels, stored MODEL_DATA) on a copy where integrations 16-31 become a second field
  `SLICE-SEC` (a new FIELD row with 1934−638's directions; FIELD_ID 1 on those rows) and their DATA is
  multiplied by `0.6`. **A substitution, labelled so:** O-CASA has one field, and LUNO's secondary scans are
  A0's held-out E2-B. Pre-apply `c.K0` (`linear`); `minblperant=3` (four stations, as C2a). The expected
  `fd ≈ 0.36·S̄_model` is reported, not gated (real data, no truth).
- **a1:** A1 small (`fp-a1-20261106-simtruth/small/a1-small.ms`, 16 antennas, 64 channels, one spw), RFI
  mask `any` flagged on a copy (as C2a), MODEL_DATA from `truth.npz` `calibrator_stokes` on J1939−6342
  (`XX = YY = I`, cross hands 0, as C2a); pre-apply A1's `truth.K` and `truth.B` (`linear`). **a1-twin:** the
  same from the twin, no flags.
- **a1x4, a1x4-twin:** the same copies corrected by `truth.K` and `truth.B` in CASA (`applycal`, `calwt=False`,
  `parang=False`), then `mstransform(datacolumn='corrected', regridms=True, nspw=4, mode='channel')` into four
  windows of 16 channels; the RFI flags are written after the transform. Before this protocol a probe
  (`c2d-20261106-00-probe`, data preparation only, no rang solve) found DATA in the four windows bit-identical
  to the input's CORRECTED_DATA, frequencies equal, WEIGHT_SPECTRUM equal and SIGMA within 4e-9. No
  pre-apply, so both sides solve with `WEIGHT_SPECTRUM` (C2a's path without a pre-apply, not compared by
  C2a; here `WEIGHT_SPECTRUM = 1/SIGMA²` to float32, so the two weight readings coincide and this does not
  test that path). Needed because **CASA fits a spectral index only across spws**; one MeerKAT window
  gives no fit (0.1 item 9).
- **full64:** A1's full twin (`full/a1-full-twin.ms`: 64 antennas, 256 channels, scans 1-4, 63 integrations),
  fields J1939−6342 and SIM-GCAL, `casa-full/truth.K`, `truth.B` pre-applied, model as a1. For casacore's
  median above 100 elements (0.1 item 8).
- **Solves (both sides):** `gaintype='G'`, `calmode='ap'`, `solint='inf'`, `combine=''`, `refant='m000'`,
  `refantmode='flex'`, `minsnr=3`, `minblperant=4` (3 on slice2), `uvrange=''`, `solnorm=False`; primary with
  its MODEL_DATA, secondaries with `smodel=[1,0,0,0]` (rang: the unit model array), `append=True` into a copy
  of the primary table (rang: `cal_fluxscale.append`); per spw on a1x4 (rang: `gaincal(spw=k)`). Then
  `fluxscale(reference='J1939-6342' or field 0, transfer='')` unless a case says otherwise; CASA defaults
  `gainthreshold=-1`, `fitorder=1`, `refspwmap=[-1]`, `incremental=False`.

## 4. Cases (frozen)

| Case | Input table | `fluxscale` settings or edit | Class |
| --- | --- | --- | --- |
| P-slice2 | CASA's merged table, slice2 | reference field 0 | P |
| P-a1 | CASA's, a1 (fields 0, 1, 2) | defaults | P |
| P-a1-transfer | as P-a1 | `transfer='SIM-GCAL'` (field 1's rows not written) | P |
| P-a1-reftran | as P-a1 | `transfer='J1939-6342,SIM-GCAL'` (the reference listed twice) | P |
| P-a1-tworef | as P-a1, with m003's rows of field 0 flagged in the table | `reference='J1939-6342,3C286-SIM'`, `transfer='SIM-GCAL'` | P |
| P-a1-threshold | as P-a1, m005's amplitudes on SIM-GCAL scans 3 and 5 × 1.2 | `gainthreshold=0.05` | P |
| P-a1x4 | CASA's, a1x4 | defaults (fitorder 1) | P |
| P-a1x4-fit2 | as P-a1x4 | `fitorder=2` | P |
| P-a1x4-2valid | as P-a1x4, SIM-GCAL's spws 2 and 3 flagged in the table | `fitorder=2` (the order-0 branch) | P |
| P-a1x4-npa1 | as P-a1x4, all but m001 X of SIM-GCAL flagged in spw 3 | defaults (`nPA = 1`, σ = 0 skipped) | P |
| P-a1x4-refspw | as P-a1x4, J1939−6342's spws 1-3 flagged in the table | `refspwmap=[0,0,0,0]` | P |
| P-full64 | CASA's, full64 (128 ratios, even) | defaults | P |
| B-slice2, B-a1, B-a1x4, B-full64 | rang's chain against CASA's on the same copy | defaults | B |
| T-a1-twin, T-a1x4-twin | rang's chain, twin copies | defaults | T, noise-free |
| T-a1, T-a1x4 | rang's chain, noisy copies | defaults | T, noise |
| C-a1 | rang's F table from B-a1 | CASA and rang `applycal`, truth K, B, F (`nearest`) on SIM-GCAL and SIM-TARGET | C |

Edits to the CASA tables of P cases are made once, written as new tables, and fed to both sides.

## 5. Held-out set (frozen now, generated only after the frozen run)

A new A1 small version, `c2d-heldout`, generated by `examples/a1_simtruth.py` with seeds jones `20261136`,
sky `20261137`, rfi `20261138`, noise `20261139` (C2b uses 20261126-29) and SIM-GCAL changed to **2.5 Jy at
1.4 GHz with spix (−1.1, −0.4)** (a curved spectrum); everything else as A1 small; its noisy MS and twin. The
override must leave the default versions bit-identical (A1's regeneration test). Cases, criteria as above:

| Case | What | Class |
| --- | --- | --- |
| HP-1, HP-4, HP-4-fit2 | CASA's merged tables on the 1-spw and 4-spw copies; defaults, and `fitorder=2` | P |
| HP-threshold | HP-1's table, m009's SIM-GCAL amplitudes in scans 7 and 9 × 0.7 | P, `gainthreshold=0.1` |
| HB-1, HB-4 | rang's chain against CASA's | B |
| HT-twin-4, HT-4, HT-1 | rang's chain against the truth (fitorder 1, and `fitorder=2` on HT-twin-4 and HT-4) | T |

## 6. Rules for failures

Following C2a and C4b: a failed frozen case stays failed in the results table. A cause found afterwards is
described, and a fix is labelled **post hoc**; any change to the code after the first comparison is followed by
the held-out set of section 5, whose verdict stands as it comes out. Where CASA's behaviour is unclear the
port follows its sources (file and function cited); anything fitted to data seen here is labelled post hoc.

## 7. Results of the frozen set (measured 2026-11-06)

Code: the working tree on top of `6ab6924` (this protocol), snapshot in each `/mnt/d/rang/outputs/c2d-20261106-NN.code/`
(`head.txt`, `diff.patch`, `untracked.tgz`). Heavy lock held for every run.

**Run -01: no comparison.** CASA's first `gaincal` selected no rows: O-CASA's slice holds its one field at id 1
(J1939−6342 of three FIELD rows), not 0 as section 3 assumed, so the harness's relabelled field was the
primary itself. Fixed in the harness only (`slice2` copies the slice's own FIELD row to a new id 3; primary
id 1); no rang code changed, nothing compared. Before run -02, rang's side alone was run on -01's other copies
as a smoke test (no CASA output was read).

**Run -02, the frozen verdict** (`c2d-20261106-02`, 1,220 s wall including waits for the heavy lock; 18 CASA
`fluxscale` calls 35.7 s, 11 `gaincal` 44.1 s). The data preparation passed its own checks: the four-window
copies equal their sources' corrected data, model, flags and weights exactly in every window; `slice2` moved
96 rows (integrations 16-31) to field 3. The class C step crashed in the harness (it deleted the copy's
`table.lock`, which the writer opens), so `compare` was rerun on -02's outputs with the same code and class C run afterwards
(`readback.json`, section 8). The numbers below were read from that comparison; its file was later
overwritten by a comparison of the recheck's outputs (now `compare-after-recheck.json`, which adds the
`E_med` rows of section 8). rang's frozen outputs are kept in `rang-run02/`.

| Class | Cases | Verdict | Largest differences |
| --- | --- | --- | --- |
| P | 12 | **fail, all 12** | `fluxd` 1.2e-7 relative (gate 1e-9); `fluxdErr` up to 1.5e-2 (P-full64); fit 3.5e-3 (fitorder 2), covariance on the four-window cases; output rows on P-a1-transfer and P-a1-reftran (192 against CASA's 256). numSol, frequencies and the valid (field, spw) sets equal everywhere; CPARAM within 1.9 ε32 where the rows matched |
| B | 4 | **pass, all 4** | `fluxd` 1.6e-5 (slice2), 1.7e-4 (a1, on 3C286-SIM; 1.1e-5 on SIM-GCAL), 1.5e-6 (a1x4), 2.5e-8 (full64); scale at half those; fitted flux ≤ 1.7e-4; spectral index 9.4e-7 and 2.6e-6 (a1x4); F-table products median 6e-7 to 1.6e-4, p95 3e-6 to 4.9e-4; reference rows unchanged |
| T, noise-free | 2 | **pass** | `fd` 3.2e-6 of `E_k` per window (T-a1x4-twin) and 3.2e-6 (T-a1-twin); fitted flux 3.2e-6; α 1.6e-10 |
| T, noise | 2 | **fail, both** | T-a1 `fd` 1.18e-3 of `E_k` (gate 1e-3); T-a1x4 window 3 1.95e-3 (others 7.6e-4, 5.9e-4, 1.2e-4); fitted flux 3.2e-5 and α 1.4e-3 pass |

Reported: the slice's pseudo-secondary has `fd` 9.0291 Jy against `0.36 × S̄_model` (not gated); the fitted α of
SIM-GCAL on the twin is −0.6025 against the nominal −0.6 (the windows are 214 MHz wide; `E_k` gives the same
−0.6025, so this is the averaging over a window, as section 2 expected); per-window `fd` on the noisy 1-spw
copy is 2.1 % above the nominal `S(ν)` at the window frequency (one window, a 40 % slope across it).

## 8. Post hoc after run -02

**P: CASA's amplitude.** `probe_fluxscale_median.py` (on -02's CASA tables) recomputed the ratios with six
amplitude rules and three median choices. Only one rule reproduces CASA's `fluxd` exactly on all twelve
(field, window) values: the amplitude is `float32(sqrt(re² + im²))` **evaluated in float64**, not the float32
`hypot` rang used (`|z|` of complex64 in NumPy); the frozen median rule (the mean of the two middle values at
32 elements, the lower one at 128) is confirmed, the alternatives miss by 1e-8 to 1e-2. The 1e-8 differences
in `fluxd` were this; the larger `fluxdErr` and fit differences were the same, amplified by `ratio / stddev`
(1e6 on the noise-free 64-antenna twin). Ported, post hoc (`rang.cal_fluxscale`).

**P: the output rows.** CASA writes **every** row of the input table; with `transfer` given, the other
fields' rows are written unscaled, so section 0.1 item 1's "not written" was wrong (the `select` of
`Calibrater::fluxscale` limits what is read into the calculation, not `storeNCT`'s output). Ported, post hoc.

**Recheck** (`compare-recheck-run02.json`: rang's side rerun on -02's CASA tables and copies with the changed
code, 1,158 s with lock waits): **P passes on 10 of 12** with `fluxd`, `fluxdErr`, numSol, frequencies, tables
(bit-identical CPARAM on every row of every case) and covariances exact or within 2e-10. **P-a1x4-fit2 and
P-a1x4-2valid still fail**, on `spidxerr` and `fitFluxdErr` of 3C286-SIM at fitorder 2: 8.7e-6 against the
1e-6 gate (coefficients and fitted flux within 6e-16). With four windows and three coefficients `n − m = 1`,
and CASA's `χ²` is `SUMLL − sol·known` with weights near 1e10 (3C286-SIM's `fderr/fd` about 1e-5), so `χ²` of
order 1 is the difference of numbers near 1e10: about 1e-5 of it is rounding in either implementation's
accumulation order. Not a port error and not chased (an exact match would need casacore's normal-matrix order
and its triangular inversion). B unchanged (all pass); T unchanged.

**T with noise: the expected value was wrong, and the noise estimate was low.** CASA and rang agree on these
values to 1e-5, so the miss is in section 2's expectation, not in rang. `probe_fluxscale_truth.py`: under the
RFI mask each antenna's baselines lose different channels, so each antenna's gain carries its own effective
spectrum; on SIM-GCAL these per-antenna expectations `E_a,h` span 4.282 to 4.304 Jy (0.5 %) on the one-window
copy and up to 0.5 % per window on the four-window copy (the twin: 1e-5). `fluxscale` takes the **median** of
per-antenna ratios, so the expectation is `E_med`, the square of casacore's median of `√E_a,h`, not one
weighted mean over all cells. Against `E_med`: T-a1 5.8e-4; T-a1x4 3.9e-4, 2.8e-4, 6.3e-5, 9.9e-4 per window,
fitted flux 1.7e-5, α 7.3e-4 (twins 1.7e-6). The rest is noise, larger than section 2 estimated: the
per-antenna ratios scatter by 1.4e-3 (`fderr` 1.0e-3 Jy at 4.3 Jy), so the median of 32 has a standard error
near 3e-4 in the ratio, 6e-4 in `fd`; the protocol's "about 1e-4" left out that scatter, so its noisy bound is
about 1.7 standard errors, not 10.

**Class C, CASA reads rang's F table** (`readback.json`, 37.9 s; rang's `applycal` 21.2 s, most of it the flag
version on `/mnt/d`): CASA `applycal` with truth K, B and rang's F table from the recheck (`nearest` field map)
on SIM-GCAL and SIM-TARGET of a fresh copy, against `rang.applycal` with the same tables: **0 of 2,334,720
cells over class C** (worst 6.5 ε32 of the cell), FLAG exact. **Pass.** (Run after the post-hoc change; the F
table's amplitudes differ from run -02's by at most a float32 rounding of `mgratio`.)

## 9. Held-out set: amendments frozen before it is generated

Written after section 8 and before the held-out version exists. Section 5's cases and the section 2 criteria
are run **as frozen**, with the code as after section 8, and their verdicts are reported as frozen. Added, and
labelled post hoc:

- **T, `E_med`** (section 8) as the expectation, with section 2's bounds unchanged, reported beside the frozen
  `E_k` verdict. **Prediction:** the noisy held-out cases fail against `E_k`; against `E_med` they are
  marginal, since SIM-GCAL is 2.5 Jy at 1.4 GHz there (about 1.7 times the relative noise of A1 small at
  4 Jy), so 1e-3 is close to one standard error and a pass is not expected on every window.
- **P at fitorder 2** is predicted to fail its frozen 1e-6 on the fit errors wherever `n − m = 1` and the SNR
  is high (section 8); its coefficients and fitted flux are predicted within 1e-12.
- **P at fitorder 1, B, T on the twin**: predicted to pass.
