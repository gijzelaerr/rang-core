# C2b: the delay term K

Task C2b of [finish-plan.md](finish-plan.md) (C2), step 4 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6. Branch `fp-c2b-delay`, from main `1275f85`.
**Status: protocol frozen (sections 1 to 4), nothing compared yet.** Results are added below section 4, never
edited into it; this status line is the only edit above section 5.

## 1. Scope

The delay term T1 of C1 (`K`, `gaincal(gaintype='K')`), with the owner's estimator (finish plan section 7, item 5:
an FFT initial estimate, then Gauss-Newton), in Rust:

- `core/src/cal/delay.rs`: a translation of QuartiCal 0.2.7's `delay` term (MIT notice kept, as `diag.rs`):
  - the initial estimate of `Delay.init_term` (`gains/delay/__init__.py`): per solution interval, the reference
    baselines' data averaged per antenna and channel (flagged cells zeroed, not weighted, not divided by the model),
    zero-padded to `ceil(2^15 / nchan) * nchan` points, `|FFT|` peak per parallel hand, no interpolation;
  - the `delay` kernel (`gains/delay/kernel.py`): parameters `tau * nu_mid` with `nu_mid = (min + max) / 2` of the
    window's `CHAN_FREQ`, gains `exp(2 pi i tau (nu - nu_mid))` per channel, the data scaled to the model's amplitude
    and the residual normalised by `|J|^2` as `phase`, conjugate gradients on the real 2x2 normal equations
    warm-started from the last update, **every update halved** (`update /= 2` in `finalize_update`), gain flags per
    channel with numbness 1e9, parameter flags the AND of their channels' gain flags (`update_param_flags`),
    `finalize_gain_flags`, and `reference_params` when a reference antenna is given;
  - the global converged-fraction stop over all per-channel gains, as QuartiCal's; intervals run in parallel inside
    an iteration and the counts are summed serially, so the result does not depend on the thread count;
  - a delay error per antenna and hand for `PARAMERR` and the class T test (below).
- `core/py/src/cal_delay.rs`: the binding `cal_delay_solve`.
- `python/rang/cal_delay.py`, reusing `rang.cal_gain` (`solint_bins`, the pre-apply, SIGMA weights with a
  pre-apply, solution times) and `rang.cal_apply`: `solve` on arrays, `gaincal` on a Measurement Set as
  `gaincal(gaintype='K')`, and `to_caltable`, a CASA `K Jones` table (`FPARAM (1, 2)` float32 delays in ns, one
  channel at the mean of the solved window's `CHAN_FREQ`, `ANTENNA2 = -1`, `INTERVAL 0`, `SNR 0` as CASA writes them;
  rang's error in `PARAMERR`, where CASA writes 0), applied through `rang.cal_apply`.

**CASA's rules around K, read in the 2023 mirror (`KJones.cc`, `Calibrater.cc`) and copied:**

- K is not a `VisCalSolver2` solve: `KJones::useGenericSolveOne()` is false, so CASA runs its own FFT
  (`solveOneSDB`, 8x padding, parabolic peak, reference baselines only, data weighted by `weightSpectrum`) and never
  calls `formSolveSNR` or `applySNRThreshold`. O-CASA measured `SNR = 0` in its K table and `minblperant=4` not
  stopping K on four stations. Rang therefore applies **no `minsnr` and no `minblperant` to K**.
- `KJones::globalPostSolveTinker()` is empty, so `applyRefAnt` never runs: no flex or strict, no alternate. The
  delays are referenced inside each solve to the user's first refant (`solveRPar` of the refant set to 0 and OK).
  Rang's CASA route does the same: per interval and hand `tau_p - tau_r`; an antenna with no unflagged cell on a
  baseline to `r` in the interval is flagged (CASA's FFT has nothing to transform there); `r` itself is unflagged
  at 0. `refantmode` is accepted and ignored, as CASA does. Whether 6.7.6.14 still does this is tested by the
  refant cases below.
- `ANTENNA2` is −1, `INTERVAL` 0, `PARAMERR` and `SNR` 0 in CASA's K tables (O-CASA's `c.K0`, A1's `truth.K`,
  read for this note). The window is one channel at the mean channel frequency (1283.896 MHz on the slice, 1284.0
  MHz on A1), with `CHAN_WIDTH` the summed width; `caltable.subtables_from_ms(single_channel=True)` writes this.

**The delay error (rang's, stated before use).** Per interval, over the unflagged parallel-hand cells with positive
weight at the solution: `chi2 = sum w |V - g_p M g_q^*|^2`, `nWt` their count, `nPar` the unflagged delays;
`k2 = chi2 / max(2 nWt - nPar, 1)` (real residual components minus real parameters); per antenna and hand
`hess = sum w |dV/dtau|^2 = sum w (2 pi (nu - nu_mid))^2 |V|^2` over the antenna's cells, the other delays held
fixed; `err = sqrt(k2 / hess)`. For a complex gain this is CASA's `1/sqrt(hess/k2/2)`; for a real parameter the 2
goes. It ignores the covariance with the other antennas' delays.

Unchanged: `solve.rs`, `jones.rs`, `correct.rs`, `core.solve_complex`, `cal/apply.rs` and `diag.rs`'s behaviour
(any helper shared with `diag.rs` is copied, C1 section 4 rule 1). Not in scope: KCROSS (C6b), `delay_and_offset`
(C5b), several windows or fields per call, `combine='spw'` (CASA's multi-band delay), CASA's own FFT estimator as an
option, and frequency parts of `solint` (CASA ignores them for K).

## 2. Tolerances (C1 section 6, restated before the first comparison)

- **Class A, against QuartiCal 0.2.7 `delay` (`initial_estimate=true`):** parameter flags and per-channel gain flags
  exact; every delay within `1e-6` ns absolute and every per-channel gain entry and parallel-hand product
  `g_p,h conj(g_q,h)` within `1e-6` absolute (both referenced to antenna 0 by QuartiCal's rule); iteration count equal
  per chunk; converged fraction equal to `1e-12`. QuartiCal solves each scan as its own chunk, so rang solves each
  scan separately for these cases. CASA's rules are off on the rang side (`casa_rules=False`).
- **Against CASA 6.7.6.14 `gaincal(gaintype='K')`:** over antennas other than the refant, hands and matched
  intervals both leave unflagged, `|tau_rang - tau_casa|` median `<= 0.01` ns and 95th percentile `<= 0.03` ns; the
  maximum reported. Both are referenced to the same refant by construction.
- **Intervals and flags against CASA:** gated: the row-to-interval map equals CASA's (each CASA row's `TIME` within
  `0.01` s of the row times of exactly one rang interval; no rang interval without a CASA row); flags exact (no
  `minsnr` band applies, since CASA computes no SNR for K); `ANTENNA2` equal. Solution `TIME` reported, not gated
  (finish plan section 7, item 9).
- **Class T, A1's simulated truth:** truth delays referenced to the refant per hand. Noise-free twin: every
  per-channel K product `k_p,h(nu) conj(k_q,h(nu))` with the table's pivot within `1e-5` absolute of the truth's;
  `|delta tau|` reported. With noise, the test is for bias: per case `z = (dtau_rang - dtau_truth) / s` per
  (interval, antenna other than the refant, hand), `s^2 = err_p^2 + err_r^2` from rang's `err`; pass when
  `|median z| <= 3 x 1.2533 / sqrt(N)`. `std(z)` reported, not gated; `s` ignores covariances, stated.
- **CASA reads rang's tables:** `applycal` with a rang K table against `rang.cal_apply` with the same table: class C
  (per cell within `1e-6` relative or 11 float32 epsilons of the cell's largest correlation), flags exact.
- **Gain hashes:** the `gain-hashes` step of `tools/check-all.sh` passes at the head (`4ed2aa89…`, `7b370c13…`,
  LUNO phase 2).

## 3. Data and settings

- **Slice:** O-CASA's `outputs/o-casa-20261030-01/work.ms` (LUNO 1934−638, field 1, scan 2, m000–m003, 192 rows, 32
  integrations, 2048 channels of 208.98 kHz, 1070.0–1497.8 MHz), stored `MODEL_DATA`, copied read-only into each
  run. Its delays are within ±0.011 ns of m000 (O-CASA's `c.K0`, `120s`), which is also compared.
- **A1 small:** `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/` (16 antennas, 64 channels of 13.375 MHz, 104
  integrations, 23 scans, delays 1–10 ns) and its twin. Fields 0 (J1939−6342) and 2 (SIM-GCAL); model A1's own
  reference `P_p M P_q^T` (`check_gain.a1_model(..., parang=True)`, C2a section 8). Pre-apply A1's truth tables
  `truth.B` (corrects the data: B is lower than K) and `truth.G` (corrupts the model: G is higher), `linear`. On the
  parallel hands of an unpolarised field KCROSS and Xf cancel and the linear Df touches the cross hands only, so K is
  what is left. Noisy MS: A1's RFI mask (`any`) flagged.
- **delay50 (new, made with A1's generator):** a version `delay50` of `rang.simtruth.design`: A1 small's antennas,
  schedule and construction, 256 channels (3.344 MHz, so the largest delay difference of 100 ns is inside the 150 ns
  Nyquist range), `|tau|` uniform in 1–50 ns with random sign, seeds 20261126 to 20261129. Generated as A1 does
  (MS and noise-free twin), its truth tables made by A1's own `tables` step (`tools/a1_checks.sh`, which also runs
  A1's round trip and noise checks on it). Used as A1 small.
- **QuartiCal (class A):** `rang-formats-oracle:20261030`, `/opt/qc`: `solver.terms=[K]`, `K.type=delay`,
  `K.time_interval=t`, `K.freq_interval=0`, `K.initial_estimate=true`, `solver.iter_recipe=[50]`,
  `solver.convergence_criteria=1e-7`, `solver.reference_antenna=0`, `solver.robust=false`, `mad_flags.enable=false`,
  `output.flags=false`, single-threaded dask and solver, weights `WEIGHT_SPECTRUM`. On A1 and delay50 the data and
  model columns hold rang's pre-applied arrays (`CDATA`, `CMODEL`) and FLAG the RFI mask, written into the copy, with
  `input_ms.select_fields=[f]`; rang solves the same columns on arrays. Rang: the same iterations, criterion, stop
  fraction (0.99) and reference, autocorrelations excluded.
- **CASA:** `rang-o-casa:6.7.6.14`, O-CASA's container conventions, `gaincal(gaintype='K', solint=..., combine='',
  refant='m000', minsnr=3, minblperant=4, gaintable=..., interp='linear')`, other parameters at their defaults.
  Rang's `gaincal`: the same selection and pre-apply, SIGMA weights when tables are pre-applied (C2a section 6),
  `WEIGHT_SPECTRUM` otherwise.

## 4. Cases (frozen)

Run directories `/mnt/d/rang/outputs/c2b-20261106-NN`, one per run, heavy steps under `flock ~/.rang-heavy.lock`.

| Case | Data | Oracle | Settings | Class |
| --- | --- | --- | --- | --- |
| A-slice-t1 | slice | QuartiCal `delay` | `time_interval=1` | A |
| A-slice-t4 | slice | `delay` | `time_interval=4` | A |
| A-slice-t0 | slice | `delay` | `time_interval=0` (one interval) | A |
| A-a1-f0-t1 | A1 small, field 0, `CDATA`, `CMODEL`, RFI flags | `delay` | `time_interval=1` (2 scans) | A |
| A-a1-f2-t0 | A1 small, field 2, as above | `delay` | `time_interval=0` (10 scans) | A |
| A-d50-twin-f0-t1 | delay50 twin, field 0, as above (no RFI) | `delay` | `time_interval=1` | A |
| A-d50-f0-t0 | delay50, field 0, with RFI flags | `delay` | `time_interval=0` | A |
| A-d50-f2-t1 | delay50, field 2, with RFI flags | `delay` | `time_interval=1` | A |
| B-slice-inf, -120s, -int | slice, field 1 | `gaincal` K | `solint` `inf`, `120s`, `int`; no gaintable | B |
| B-slice-c.K0 | slice | O-CASA's `c.K0` | `120s` | B |
| B-a1-inf-f0, -inf-f2, -int-f0, -60s-f2 | A1 small, RFI flagged | `gaincal` K | as named; `gaintable=[truth.B, truth.G]` | B |
| B-a1-noapply-inf-f0 | as above | `gaincal` K | `inf`, field 0, no gaintable (rang: `WEIGHT_SPECTRUM`) | B |
| B-a1-refant-flag | A1 small; m000's rows flagged in integrations 3-5 of scan 23 | `gaincal` K | `int`, field 0, `refantmode='flex'` | B (refant, flags) |
| B-a1-refant5-inf-f2 | A1 small | `gaincal` K | `inf`, field 2, `refant='m005'` | B (refant) |
| B-d50-inf-f0, -inf-f2, -int-f2 | delay50, RFI flagged | `gaincal` K | as named; delay50's `truth.B`, `truth.G` | B |
| T-a1-twin | A1 twin, fields 0 and 2 | truth | `int` and `inf`, pre-apply as above | T (noise-free) |
| T-a1-noisy | A1 small, fields 0 and 2 | truth | `int` and `inf` | T (bias) |
| T-d50-twin, T-d50-noisy | delay50 and twin | truth | as A1 | T |
| R-slice, R-d50 | slice; delay50 field 0 | CASA `applycal` of rang's table (B-slice-int; B-d50-inf-f0) | `linear` | C (readback) |

The twin cases solve to `stop_criterion=1e-10`, `stop_fraction=1.0`, 200 iterations, as C2a's twin did; every
other case uses the settings above.
