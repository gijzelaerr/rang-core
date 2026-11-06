# C2a: the gain term G

Task C2a of [finish-plan.md](finish-plan.md) (C2), step 3 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6. Branch `fp-c2a-gain`, from main `c2aba02`.
**Status: protocol frozen (sections 1 to 4) before any comparison; implemented; not yet measured.**
Results are added below the protocol, never edited into it.

## 1. Scope

The gain term T2 of C1 (`G`, `calmode='ap'`) and its phase-only form (`calmode='p'`, which T8 Gpol and T12b
reuse), in Rust:

- `core/src/cal/diag.rs`: a translation of QuartiCal 0.2.7's `diag_complex` and `phase` kernels (MIT notice kept,
  as `solve.rs`): parallel hands only, QuartiCal's non-generalised 2x2 inverse with its `det.re < 1e-6` rule and the
  halved even-iteration update (`diag_complex`); data scaled to the model amplitude, `1/|J|^2` normalisation and
  conjugate gradients warm-started from the last update, no halving, numbness 1e9 (`phase`); the global
  converged-fraction stop over all gains, with intervals run in parallel in epochs as `solve.rs` does, so the result
  is the serial loop's at every thread count; QuartiCal's referencing (`reference_gains`, `reference_params`) when a
  reference antenna is given. It also computes CASA's solution statistics (below).
- `core/src/cal/reference.rs`: CASA's rules around a solve, written from `SolvableVisCal.cc` (C1 section 0):
  `minblperant` before the solve (`verifyConstraints`: per interval, recursive elimination; the eliminated
  antennas' data flagged for the solve), `minsnr` after it (`applySNRThreshold`, strictly greater), and the
  reference antenna over the finished table (`applyRefAnt`: per window and in time order, the choice list primary,
  last used, the user's others, the rest by distance from the user's last refant; a choice must be unflagged in the
  previous and the current interval; `flex` keeps an alternate's phase continuous; `strict` tries the primary only;
  no good choice flags the whole interval).
- `core/py/src/cal_gain.rs`: the bindings `cal_gain_solve`, `cal_gain_minblperant`, `cal_gain_apply_refant`.
- `python/rang/cal_gain.py`: `solint_bins` (CASA's row-to-interval map), `uvrange_keep` (metres), `solve` on
  arrays, `gaincal` on a Measurement Set (field selection, pre-apply through `rang.cal_apply`: types lower than G
  correct DATA, equal or higher types corrupt the model, as `VisEquation::collapse2`), and `to_caltable`, a CASA
  `G Jones` table through `formats/caltable.py` with per-row `ANTENNA2` (the refant used), `PARAMERR`, `SNR` and
  `FLAG`, solution `TIME` the weight centroid of the interval's unflagged rows.
- `tools/gain_hash_gate.py` and a `gain-hashes` step in `tools/check-all.sh` (through `rang.check`): the gate of
  C1 section 4 rule 2.

**CASA's SNR, as rang computes it.** `VisCalSolver2::getErrors` and `formSolveSNR`: over the interval's unflagged
parallel-hand cells with positive weight, `chi2 = sum w |r|^2` and `nWt` their count; per gain and hand
`hess = sum w |dV/dg|^2`; `k2 = chi2 / max(2 (nWt - nParOK), 1)`, `err = 1/sqrt(hess/k2/2)`, `SNR = |g|/err`.
CASA evaluates this on its pre-averaged, model-divided buffer; rang on the cells as they are. In the noise-limited
case both estimate the same thermal error; elsewhere they differ, which is why C1 reports rather than gates flag
differences near `minsnr`. `minblperant` counts a baseline when a cell has no flagged correlation (QuartiCal's data
flag) and positive XX+YY weight; CASA counts a baseline with any unflagged correlation. These are differences of
definition, stated, not hidden.

Unchanged: `solve.rs`, `jones.rs`, `correct.rs`, `core.solve_complex`, `cal/apply.rs` (`git diff main` on them is
empty; `diag.rs` uses `solve::Problem` and `solve::data_flags` read-only). Not in scope: K, B, F, `fluxscale`
(C2b to C2d), `solnorm`, `smodel`, `preavg`, `append`, several windows or fields per call, `uvrange` in
wavelengths (refused), and C1's frequency chunks (the kernel takes `freq_bin`; the CASA table route refuses more
than one bin).

## 2. Tolerances (C1 section 6, restated before the first comparison)

- **Class A, against QuartiCal 0.2.7** (`diag_complex`, and `phase` for `p`): gain flags exact; every complex gain
  entry and every parallel-hand baseline product `g_p,h conj(g_q,h)` over pairs QuartiCal leaves unflagged within
  `1e-6` absolute (both referenced to antenna 0 by QuartiCal's rule); iteration count equal; converged fraction
  equal to `1e-12` (reported with the iteration count; gated as part of "iterations equal"). CASA's rules are off on
  the rang side (`casa_rules=False`), since QuartiCal has none.
- **Class B, against CASA 6.7.6.14 `gaincal(gaintype='G')` on matched intervals:** on the parallel-hand products
  over pairs both leave unflagged, relative difference `|P_rang - P_casa| / |P_casa|` median `<= 7e-4` and 95th
  percentile `<= 3e-3`; the maximum reported, not gated. Held-out parallel-hand MSE (below) within `2e-4`
  relative of CASA's, reported as ratio and sign. CASA's rules on (`casa_rules=True`).
- **Flags in class B:** gated exact, except that a difference is reported and not gated where CASA's or rang's SNR
  of that parameter lies within a factor of 2 of `minsnr`, or where the antenna has exactly `minblperant`
  baselines in the interval (the SNR and the count are each solver's own).
- **Intervals in class B:** gated: the row-to-interval map equals CASA's (each CASA row's `TIME` lies in exactly
  one rang interval, and rang has no interval CASA lacks, except intervals where CASA wrote no row because
  nothing was solvable, which are reported); `TIME` within `0.01` s of CASA's; `ANTENNA2` (the refant used) equal
  per row. `INTERVAL` is reported, not gated.
- **Class T, A1's simulated truth:** on the noise-free twin, every parallel-hand product within `1e-5` absolute of
  the truth's. With noise, the test is for bias: per case, `z = (P_rang - P_truth) / s` per product and hand, with
  `s^2 = |g_q|^2 err_p^2 + |g_p|^2 err_q^2` from rang's own `err` (the CASA formula above); pass when
  `|median(Re z)|` and `|median(Im z)|` are both `<= 3 x 1.2533 / sqrt(N)` (three standard errors of the median of
  `N` standard-normal values). The ratio `std(z)` is reported, not gated. Products share antennas, so the `N` is an
  upper bound on independent values and the test is a little strict; stated.
- **Gain hashes:** `tools/gain_hash_gate.py` recomputes `4ed2aa89…` (core K `original`, slice) and `7b370c13…`
  (L5's D, fixture) through `core.solve_complex`, and core phase 2 on LUNO (50 iterations, converged fraction
  `0.9833234067897558`, gain flags equal to QuartiCal's archive). All must be exact. The rank survey (core-phase2
  criterion 6) is not replayed.

## 3. Data and settings

- **Slice:** O-CASA's `outputs/o-casa-20261030-01/work.ms` (LUNO 1934−638, stations m000–m003, 192 rows, 32
  integrations of 7.997 s in one scan, 2048 channels), copied read-only into each run; stored `MODEL_DATA`; O-CASA's
  K table `c.K0` for the pre-apply (`linear`), as C1's step 2 has K applied before G. Held-out cells: O-CASA's
  seed-7 split (`split.npz`, validation and test), flagged on both sides before the solve.
- **Fixture:** the clean case `outputs/tv-response-wsl-20261029-01/clean/work.ms` (4 stations, 14 integrations,
  4096 channels, `RANG_MODEL_DATA`), as stored. Class A only.
- **Simulated:** A1's small version (`/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/`: 16 antennas, 64
  channels, 104 integrations, 23 scans, four fields) and its noise-free twin. It stands in for C1's proposed
  16 × 256 × 60 set, which is not built; stated as a substitution. Fields used: 0 (J1939−6342, 14.0 Jy, unpolarised)
  and 2 (SIM-GCAL, 5.35 Jy, unpolarised); the model column is written on a copy from `truth.npz`
  `calibrator_stokes` (`XX = I+Q`, `YY = I−Q`, `XY = U+iV`, `YX = U−iV`, per channel); the polarised field is not
  used, since P enters there. Pre-apply: A1's CASA truth tables `casa-small/truth.K` and `truth.B` (`linear`);
  on the parallel hands of an unpolarised field the remaining terms (KCROSS, Xf, P, the linear Df) cancel or touch
  the cross hands only, so G is what is left. Noisy MS: A1's RFI mask (`a1-small.rfi_mask.npz`, `any`) flagged on
  both sides.
- **Settings.** QuartiCal (class A): `rang-formats-oracle:20261030`, `/opt/qc`, as C1 section 2.2: `solver.terms=[G]`,
  `G.type=diag_complex|phase`, `solver.iter_recipe=[50]`, `solver.convergence_criteria=1e-7`,
  `solver.reference_antenna=0`, `solver.robust=false`, `mad_flags.enable=false`, `output.flags=false`,
  `dask.threads=1`, `solver.threads=1`, `dask.scheduler=single-threaded`, weights `WEIGHT_SPECTRUM`. Rang: the same
  iterations, criterion and stop fraction (0.99), reference antenna 0, `casa_rules=False`, the same integer
  intervals, autocorrelations excluded. CASA (class B): `rang-o-casa:6.7.6.14`, O-CASA's container conventions,
  `gaincal(gaintype='G', calmode=..., refant='m000', refantmode=..., minsnr=3, minblperant=..., uvrange='',
  combine=..., gaintable=..., interp='linear', solnorm=False)`, everything else at 6.7.6.14 defaults. On the slice
  `minblperant=3`: with four stations CASA's default 4 rejects every solution (L5-C, smoke 3), and O-CASA used 3.

## 4. Cases (frozen)

Run directories `/mnt/d/rang/outputs/c2a-20261106-NN`, one per run, heavy steps under `flock ~/.rang-heavy.lock`.

| Case | Data | Oracle | Settings | Class |
| --- | --- | --- | --- | --- |
| A-slice-ap-t2 | slice | QuartiCal `diag_complex` | `time_interval=2`, `freq_interval=0` | A |
| A-slice-ap-t1f32 | slice | `diag_complex` | `time_interval=1`, `freq_interval=32` | A |
| A-slice-p-t2 | slice | `phase` | `time_interval=2`, `freq_interval=0` | A |
| A-slice-p-t1f32 | slice | `phase` | `time_interval=1`, `freq_interval=32` | A |
| A-slice-ap-K | slice, DATA corrected by `c.K0` through `rang.cal_apply` (written to a column of the copy) | `diag_complex` | `time_interval=2`, `freq_interval=0` | A |
| A-fixture-ap | fixture | `diag_complex` | `time_interval=2`, `freq_interval=32` | A |
| A-fixture-p | fixture | `phase` | `time_interval=2`, `freq_interval=32` | A |
| B-slice-inf | slice, held-out split flagged | `gaincal` | `solint='inf'`, `calmode='ap'`, flex, `gaintable=[c.K0]` | B |
| B-slice-60s | as above | `gaincal` | `solint='60s'` | B |
| B-slice-120s | as above | `gaincal` | `solint='120s'` | B |
| B-slice-p | as above | `gaincal` | `solint='inf'`, `calmode='p'` | B |
| B-a1-inf | A1 small, fields 0 and 2 | `gaincal` | `solint='inf'`, `minblperant=4`, flex, `gaintable=[truth.K, truth.B]` | B |
| B-a1-60s, B-a1-30s, B-a1-int | as above | `gaincal` | `solint='60s'`, `'30s'`, `'int'` | B (intervals) |
| B-a1-combine | A1 small, field 2 | `gaincal` | `solint='inf'`, `combine='scan'` | B (intervals) |
| B-a1-refant-flex | A1 small, field 0; m000's rows flagged in scan 23 | `gaincal` | `solint='int'`, flex | B (refant, flags) |
| B-a1-refant-strict | as above | `gaincal` | strict | B (refant, flags) |
| B-a1-minblperant | A1 small, field 0; m005 keeps 3 baselines in scan 1 | `gaincal` | `solint='inf'`, `minblperant=4` | B (flags) |
| B-a1-minsnr | A1 small, field 0; the weights of m007's rows times `1e-4` | `gaincal` | `solint='inf'` | B (flags) |
| T-twin-ap | A1 twin, fields 0 and 2 | truth | `solint='int'`, `ap`, CASA rules on | T (noise-free) |
| T-noisy-ap | A1 small, fields 0 and 2 | truth | `solint='int'` and `'inf'` | T (bias) |

**Intervals: how the rule is found.** `solint_bins` implements one reading of casacore's `MSInterval` (bins
`floor((t - t0) / solint)` from the group's first time). The slice cases B-slice-60s and -120s are where the rule
is first compared; if it fails there, the rule is changed post hoc, labelled so, and the A1 interval cases (several
scans and fields, `30s`, `60s`, `int`, `combine='scan'`) are the held-out test. The A1 interval cases are the
verdict on intervals either way.

**Held-out MSE (B-slice).** Each side's table applied by `rang.cal_apply` (`linear`) after `c.K0`, then
`mean(w |V_corr - M|^2)` over the held-out cells' unflagged parallel hands; the relative difference
`(MSE_rang - MSE_casa) / MSE_casa`.

## 5. Results of the frozen set (measured 2026-11-06)

Code: the working tree on top of `f215a5e` (this note's protocol commit); each run directory has a `.code/` snapshot
(`head.txt`, `diff.patch`, `untracked.tgz`, SHA-256 list) because the code was committed only after the runs
(section 9). Runs under `/mnt/d/rang/outputs/`, heavy lock held.

**Run -01: no comparison.** The container step that adds the `KDATA` column failed (`makecoldesc` from DATA's
description); fixed in `examples/oracle_gain.py`, nothing compared.

### 5.1 Class A against QuartiCal 0.2.7, run -02: pass on all seven cases

`c2a-20261106-02`, 139.8 s (seven `goquartical` processes of 8-38 s and 388-643 MB each; rang 0.02-0.08 s per solve).

| Case | Gains (flagged) | Max entry | Max product | Iterations (rang, QuartiCal) | Converged fraction |
| --- | ---: | ---: | ---: | --- | --- |
| A-slice-ap-t2 | 64 (0) | 2.2e-16 | 3.3e-16 | 15, 15 | 1.0, 1.0 |
| A-slice-ap-t1f32 | 8,192 (4,840) | 4.4e-16 | 5.6e-16 | 50, 50 | 0.98747…, equal |
| A-slice-p-t2 | 64 (0) | 1.4e-17 | 2.8e-17 | 15, 15 | 1.0, 1.0 |
| A-slice-p-t1f32 | 8,192 (4,841) | 6.5e-16 | 6.5e-16 | 50, 50 | 0.90871…, equal |
| A-slice-ap-K | 64 (0) | 2.2e-16 | 3.3e-16 | 15, 15 | 1.0, 1.0 |
| A-fixture-ap | 3,584 (1,398) | 3.6e-16 | 5.6e-16 | 50, 50 | 0.95334…, equal |
| A-fixture-p | 3,584 (1,398) | 1.4e-15 | 1.4e-15 | 50, 50 | 0.98170…, equal |

Gain flags equal on every case, converged fractions equal to the last digit, no entry differs by more than 1e-10.
As for `complex` (core-phase2), agreement is at rounding level, since QuartiCal compiles with `fastmath`.

### 5.2 Class B against CASA `gaincal`, run -03: the slice passes; A1 fails on four counts

`c2a-20261106-03`, 159.8 s (20 `gaincal` calls of 1.1-1.7 s). Two deviations from section 4 in what was run, found
when writing this section: B-a1-minsnr scaled m007's weights by **1e-10, not the 1e-4** of the table (1e-4 would
have left an SNR near 100 and tested nothing); B-a1-refant flagged m000 in integrations 3-5 of the six of scan 23
(field 0), not in the whole scan, so that flex has to hold an alternate after the primary returns.

| Case | Intervals | Max `|ΔTIME|` (s) | Products median, p95 (relative) | Flags differing | Refant | Held-out MSE | Verdict |
| --- | --- | ---: | --- | --- | --- | ---: | --- |
| B-slice-inf | 1 = 1 | 0.0007 | 4.5e-6, 1.1e-5 | 0 | equal | 0.0 | pass |
| B-slice-60s | 5 = 5 | 0.0036 | 4.0e-6, 1.3e-5 | 0 | equal | −1.3e-6 | pass |
| B-slice-120s | 3 = 3 | 0.0022 | 4.0e-6, 1.3e-5 | 0 | equal | −9.0e-7 | pass |
| B-slice-p | 1 = 1 | 0.0010 | 2.1e-5, 4.9e-5 (phase median 0.00095°) | 0 | equal | 0.0 | pass |
| B-a1-inf, -60s, -30s on field 0 | 2, 2, 4 | ≤ 0.0031 | ≤ 1.9e-5, ≤ 4.6e-5 | 0 | equal | – | pass |
| B-a1-int-f0, -int-f2, refant flex, strict | 12, 20, 12, 12 | – | – | – | – | – | **fail: not matched** |
| B-a1-inf, -60s, -30s on field 2 | 10 each | **0.0544** | 7.9e-5, 1.7e-4 | 0 | equal | – | **fail: TIME** |
| B-a1-combine-f2 | 1 = 1 | **0.411** | **9.3e-3, 2.4e-2** | 0 | equal | – | **fail: TIME, products** |
| B-a1-minblperant | 2 = 2 | 0.0020 | 1.4e-5, 3.1e-5 | 0 (m005 flagged on both) | equal | – | pass |
| B-a1-minsnr | 2 = 2 | 0.0008 | 2.8e-5, 6.2e-5 | **4 gated** (rang flagged m007, CASA did not) | equal | – | **fail: flags** |

**CASA's bins equal `solint_bins`' on every case**: the MSInterval reading was right at the first comparison (the
slice's `60s` and `120s`: 5 and 3 bins) and on A1's `30s` and `60s` across scans and fields. The failures:

1. **`int` (four cases): the checker, not the bins.** A one-integration interval is a point, and CASA's `TIME` for it
   differs from the integration's by up to about 1e-6 s, so containment with a 1e-6 s margin missed.
2. **`TIME` on field 2 (0.054 s) and the slice (up to 0.0036 s).** CASA's solution time is
   `SDBList::aggregateTimeCentroid` (read in `SolveDataBuffer.cc`): `TIME_CENTROID` weighted by each buffer's summed
   `weightSpectrum` at that point of its solve. Rang weights by the unflagged parallel-hand weight. Where RFI flags
   channels unevenly between integrations the two differ. Tried post hoc on run -03's tables (no new run): weights
   times `|M|^2` (CASA's division by the model) reduce it to ≤ 0.0067 s on A1 but not to zero and are worse on the
   slice's `inf`; SIGMA weights and B's `calwt` scaling do not close it. **Not resolved.** On an interpolated apply
   this is a shift under 0.7 % of an integration.
3. **`combine='scan'`:** one solution over ten scans spread over 3 h, whose true phases walk by tens of degrees between
   scans. CASA averages the visibilities over the interval before it solves; QuartiCal's estimator, which rang ports,
   does not. With a model that cannot fit, the two differ by about 1 %. This is the estimators' difference, not a bug;
   the bins (one interval) agree. The 0.41 s `TIME` is item 2 again.
4. **`minsnr`: CASA did not solve with the scaled weights.** Its SNR for m007 stayed near 12,800 (rang's: 0.14).
   Section 6 finds why.

## 6. Post hoc after run -03

**Probe `c2a-20261106-04-probe`** (`examples/probe_gain_weights.py`, 25.8 s), three copies of A1 small, field 0:

| Copy | Edit | Pre-apply | CASA's m007 SNR (X, Y; first scan) | m007 flagged |
| --- | --- | --- | --- | --- |
| w-noapply | WEIGHT_SPECTRUM and WEIGHT of m007 × 1e-10 | none | 1.6, 0.34 | yes |
| s-apply | SIGMA of m007 × 1e5 | truth K, B | 0.14, 0.16 | yes |
| s-noapply | SIGMA of m007 × 1e5 | none | 0.0, 0.0 | yes |

With tables to pre-apply, CASA solves with weights from SIGMA, not WEIGHT_SPECTRUM: the apply resets them first
(`resetWeightsUsingSigma`, C1 section 3.2). Rang's SNR at those weights (0.14, 0.15 in run -03) is CASA's
(0.14, 0.16). Without a pre-apply CASA reads WEIGHT_SPECTRUM. That s-noapply also flags m007, with an SNR of exactly
0, is **not explained** (the probe predicted it unflagged); recorded, not chased.

Changes, post hoc and labelled so:

- `rang.cal_gain.gaincal` solves with `1/SIGMA_SPECTRUM^2` (or `1/SIGMA^2` per channel; 0 where sigma is 0)
  whenever tables are pre-applied, as CASA does, and with `weight_column` otherwise.
- The checker matches an interval when CASA's `TIME` lies within the gated 0.01 s of the interval's row times (it
  used 1e-6 s).

**Re-evaluated on run -03's CASA tables with the changed code** (`check_gain.py recheck`, `casa-recheck.json`):
every case passes except **B-a1-inf, -60s and -30s on field 2** (`TIME` 0.0544 s, item 2) and **B-a1-combine-f2**
(`TIME` 0.411 s; products 9.3e-3 median, 2.4e-2 p95; item 3). The `int` cases now match (12 and 20 intervals,
products ≤ 1.1e-4 median and ≤ 2.5e-4 p95). **Refant flex and strict equal CASA's per interval**: flex uses m000 for
eight integrations, then the alternate m001, and keeps m001 after m000 returns; strict flags all antennas in the
three intervals without m000, 96 flags on both sides. Minblperant (m005 flagged in scan 1 on both) and minsnr (no
flag on either) agree. This is a fit to the run that found the problems, so section 7 holds out a further set.

## 7. Held-out class B set (frozen before run -05)

`check_gain.py casa <run> --heldout`, the same criteria as section 2, on new edits and settings not used above
(code as after section 6):

| Case | Data | Settings | What it tests |
| --- | --- | --- | --- |
| H-slice-p-60s | slice, held-out split flagged | `p`, `60s`, `minblperant=3` | phase-only on several intervals; held-out MSE |
| H-a1-20s-f0 | A1 small, field 0 | `ap`, `20s` | MSInterval bins inside 6-integration scans (3 per scan) |
| H-a1-16s-f0 | as above | `ap`, `16s` | the same at a width of exactly two integrations |
| H-a1-p-int-f2 | A1 small, field 2 | `p`, `int` | phase-only per integration |
| H-a1-refant-flex-f2 | A1 small; m000's rows flagged in scans 5 and 7 (field 2) | `ap`, `inf`, flex | an alternate over two whole scans, then continuity |
| H-a1-refant-strict-f2 | as above | strict | the two scans flagged |
| H-a1-minbl-f2 | A1 small; m011 left with its baselines to m001-m003 in scan 9 | `ap`, `inf`, `minblperant=4` | elimination in one interval of field 2 |
| H-a1-snr-sigma-f0 | A1 small; SIGMA of m009's field-0 rows × 1e4 (weights unchanged) | `ap`, `inf`, pre-apply | `minsnr` through SIGMA weights |

Predicted from section 6 before the run: field 2's `TIME` fails the 0.01 s gate wherever its RFI flags are uneven
(item 2), so H-a1-p-int-f2 is expected to pass (one integration per interval) and the field-2 `inf` cases to fail on
`TIME` alone; H-a1-snr-sigma-f0 flags m009 on both sides (an SNR near 1.3, outside the reported band 1.5-6).

## Gain-hash gate (measured 2026-11-06, before any other change was compiled into the gate)

`tools/gain_hash_gate.py --json` on this branch with `.venv` (archive `~/Github/rang/outputs`): `4ed2aa89…` and
`7b370c13…` reproduced exactly; LUNO phase 2: 50 iterations, converged fraction `0.9833234067897558`, gain flags
equal to QuartiCal's. 2.0 s wall, 113 MB peak.
