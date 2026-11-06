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

## Gain-hash gate (measured 2026-11-06, before any other change was compiled into the gate)

`tools/gain_hash_gate.py --json` on this branch with `.venv` (archive `~/Github/rang/outputs`): `4ed2aa89…` and
`7b370c13…` reproduced exactly; LUNO phase 2: 50 iterations, converged fraction `0.9833234067897558`, gain flags
equal to QuartiCal's. 2.0 s wall, 113 MB peak.
