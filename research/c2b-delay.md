# C2b: the delay term K

Task C2b of [finish-plan.md](finish-plan.md) (C2), step 4 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6. Branch `fp-c2b-delay`, from main `1275f85`.
**Status: implemented and measured; class A met; against CASA and class T not met as frozen.** The protocol
(sections 1 to 4) was committed (`3a37a50`, two corrections in `707f5c0`) before the first comparison; results are
added below it, never edited into it, and this status line is the only edit above section 5.

- **Class A, QuartiCal 0.2.7 `delay`:** all eight cases pass at the first run (slice, A1 small, delay50 with delay
  differences to 88 ns): parameter and per-channel gain flags exact, delays within 1.4e-14 ns, gains and products within 2.1e-13,
  iterations and converged fractions equal per chunk.
- **Against CASA `gaincal(gaintype='K')`:** with the antenna phases removed by a pre-applied G (A1 and delay50, nine
  cases) every case passes, `|dtau|` median 0.0002-0.0015 ns, p95 up to 0.0048 ns, flags and the refant rule (also
  with the refant flagged, and refant m020) equal to CASA's. **Without a pre-applied G it fails:** the slice by
  0.06 ns median (antenna phases of only ±4°) and A1 without a pre-apply by 1.3 ns. Measured post hoc: the cause is
  QuartiCal's `delay` model, which has no phase offset (an unmodelled antenna phase biases the delay where the
  weights are not symmetric about mid-band); CASA's FFT peak ignores the phase. **QuartiCal's own
  `delay_and_offset` (FFT, then Gauss-Newton with a free phase) meets CASA's tolerance on all three failing cases**
  (0.0013-0.0033 ns median). CARACal solves K first with nothing pre-applied, so this is an owner decision
  (section 9).
- **Class T, A1 and delay50:** noise-free twins within 3.1e-8 (products) on all eight cases. With noise the frozen
  bias test fails on A1's field 0 (median z 0.36 and 1.14 against 0.20 and 0.49): every referenced delay of an
  interval shares the refant's error, so the z values are not independent. Post hoc, centred on the antenna mean
  (gauge-free), all eight pass. `std(z)` is 1.5-2.0: rang's error is low by that factor, consistent with the B
  correction amplifying the band-edge noise while the weights stay unscaled (estimated factor 2-5).
- CASA applies rang's K tables (slice, delay50 to 88 ns): class C, 2.6 float32 epsilons, flags exact. The
  `gain-hashes` step of check-all passes. No novelty claim: this is a port with oracles.

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
  (Added after the protocol commit, before any comparison:) class T compares the solution's float64 delays; a
  float32 table delay of 50 ns is rounded by up to 3e-6 ns, a phase of up to 8e-6 rad at the band edge, which is
  reported for the table separately and not gated.
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
| B-a1-refant5-inf-f2 | A1 small | `gaincal` K | `inf`, field 2, refant antenna 5 (`'m020'`; corrected before any comparison from `'m005'`, which A1 has no antenna of) | B (refant) |
| B-d50-inf-f0, -inf-f2, -int-f2 | delay50, RFI flagged | `gaincal` K | as named; delay50's `truth.B`, `truth.G` | B |
| T-a1-twin | A1 twin, fields 0 and 2 | truth | `int` and `inf`, pre-apply as above | T (noise-free) |
| T-a1-noisy | A1 small, fields 0 and 2 | truth | `int` and `inf` | T (bias) |
| T-d50-twin, T-d50-noisy | delay50 and twin | truth | as A1 | T |
| R-slice, R-d50 | slice; delay50 field 0 | CASA `applycal` of rang's table (B-slice-int; B-d50-inf-f0) | `linear` | C (readback) |

The twin cases solve to `stop_criterion=1e-10`, `stop_fraction=1.0`, 200 iterations, as C2a's twin did; every
other case uses the settings above.

## 5. Results (measured 2026-11-06)

Code: the working tree on top of `707f5c0` (the protocol commits); each run directory has a `.code/` snapshot
(`head.txt`, `diff.patch`, `untracked.tgz`, SHA-256 list), because the code was committed after the runs (section
8). Runs under `/mnt/d/rang/outputs/`, heavy lock held for each.

**delay50, made first** (`c2b-20261106-d50`): `examples/a1_simtruth.py generate delay50` (5.1 s) and `--noiseless`
(5.2 s), then `tools/a1_checks.sh` (57.5 s): A1's round trip passes on it (CASA `applycal` of the six truth tables
gives the twin's model to 8.4e-7 of the cell's largest correlation), the noise check passes (measured sigma
0.99977 of expected), and the parallactic check fails as it does on A1 small (CASA's frame, A1 section 7.2). True
delays −42.6 to 48.8 ns, differences to m000 up to 87.6 ns.

### 5.1 Class A against QuartiCal 0.2.7 `delay`, run -01: pass on all eight cases

`c2b-20261106-01`, 284.4 s, 1.0 GB peak (eight `goquartical` processes of 7.8-48.8 s and 404-778 MB; rang 0.06-0.51
s per case, all chunks).

| Case | Intervals (chunks) | Gains flagged | Max delay (ns) | Max gain entry | Max product | Iterations per chunk |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A-slice-t1 | 32 (1) | 175,193 of 262,144 | 4.2e-17 | 2.2e-16 | 4.3e-16 | 14 = 14 |
| A-slice-t4 | 8 (1) | 43,641 | 4.2e-17 | 2.2e-16 | 3.6e-16 | 14 = 14 |
| A-slice-t0 | 1 (1) | 5,447 | 1.4e-17 | 1.7e-16 | 3.0e-16 | 14 = 14 |
| A-a1-f0-t1 | 12 (2) | 0 | 3.6e-15 | 2.5e-14 | 3.9e-14 | 14, 15 = 14, 15 |
| A-a1-f2-t0 | 10 (10) | 0 | 1.8e-15 | 2.1e-14 | 3.2e-14 | 15-16, equal |
| A-d50-twin-f0-t1 | 12 (2) | 0 | 1.4e-14 | 2.0e-13 | 2.1e-13 | 16, 16 = 16, 16 |
| A-d50-f0-t0 | 2 (2) | 0 | 1.4e-14 | 2.0e-13 | 2.0e-13 | 16, 16 = 16, 16 |
| A-d50-f2-t1 | 20 (10) | 0 | 1.4e-14 | 2.0e-13 | 2.1e-13 | 16-17, equal |

Parameter and gain flags equal on every case (the slice's flagged channels flag 67 % of its per-channel gains on
both sides), converged fractions equal to the last digit. The largest delay difference grows with the delay (1.4e-14
ns at 88 ns, a relative 1.6e-16): rounding, as C2a's 1e-15. The FFT estimates were not compared on their own;
a different peak bin would most likely have shown as a different iteration count, and none did.

### 5.2 Against CASA `gaincal(gaintype='K')`, run -02: nine of fourteen pass; the slice and the no-apply case fail

`c2b-20261106-02`, 250.3 s, 415 MB (13 `gaincal` K calls of 1.0-3.0 s; rang 1.5-9.0 s per case including the MS
reads and the pre-apply).

| Case | Intervals | `|dtau|` median, p95, max (ns) | Flags (rang, CASA) | Max `|dTIME|` (s) | Verdict |
| --- | --- | --- | --- | ---: | --- |
| B-slice-inf | 1 = 1 | **0.059, 0.076**, 0.077 | 0, 0 | 122.9 | **fail** |
| B-slice-120s | 3 = 3 | **0.062, 0.080**, 0.083 | 0, 0 | 56.0 | **fail** |
| B-slice-int | 32 = 32 | **0.059, 0.088**, 0.102 | 0, 0 | 1e-6 | **fail** |
| B-slice-c.K0 (O-CASA's table) | 3 = 3 | **0.071, 0.091**, 0.094 | 0, 0 | – | **fail** |
| B-a1-inf-f0 | 2 = 2 | 0.00016, 0.00045, 0.00073 | 0, 0 | 0.037 | pass |
| B-a1-inf-f2 | 10 = 10 | 0.0010, 0.0032, 0.0067 | 0, 0 | 0.26 | pass |
| B-a1-int-f0 | 12 = 12 | 0.00039, 0.0012, 0.0024 | 0, 0 | 3e-6 | pass |
| B-a1-60s-f2 | 10 = 10 | 0.0010, 0.0032, 0.0067 | 0, 0 | 0.26 | pass |
| B-a1-noapply-inf-f0 | 2 = 2 | **1.30, 1.74**, 1.81 | 0, 0 | 0.037 | **fail** |
| B-a1-refant-flag | 12 = 12 | 0.00036, 0.0011, 0.0024 | 90, 90 | 3e-6 | pass |
| B-a1-refant5-inf-f2 | 10 = 10 | 0.0015, 0.0044, 0.0071 | 0, 0 | 0.26 | pass |
| B-d50-inf-f0 | 2 = 2 | 0.00022, 0.00062, 0.0011 | 0, 0 | 2e-6 | pass |
| B-d50-inf-f2 | 10 = 10 | 0.0010, 0.0032, 0.0055 | 0, 0 | 0.024 | pass |
| B-d50-int-f2 | 20 = 20 | 0.0015, 0.0048, 0.012 | 0, 0 | 4e-6 | pass |

`ANTENNA2` is −1 on every row on both sides. The refant rule copied from `KJones.cc` holds in 6.7.6.14: with m000
flagged in three integrations CASA flags the 15 other antennas in both hands there (90 flags) and writes m000
unflagged at 0, as rang; with refant m020 the delays are referenced to it on both sides. The bins equal CASA's on
every case, including `60s` across A1's scans.

**Solution `TIME`, reported (not gated):** CASA's K times are not the weighted centroid. On the slice the `inf`
solution sits at the first timestamp and the `120s` ones 7.7 s, 127.9 s and 247.9 s after it, while rang's are the
centroids (122.9 s, 59.8 s, 183.9 s, 247.9 s). On A1's short scans the difference is at most 0.26 s. CASA's rule for
K was not found; it moves where a linear interpolation in time pivots.

**Iterations.** Two cases ran to 50 iterations without converging: B-a1-noapply (fraction 0.0; section 6) and
B-a1-refant-flag (0.76): in the three intervals where m000 has no data the FFT estimate has no reference baselines,
Gauss-Newton starts from zero against delays of up to 25 ns and does not converge. CASA's rule flags those delays,
so nothing unconverged is written. QuartiCal would be expected to behave the same with its reference antenna's
data missing (the same estimate code); not run.

## 6. Post hoc: why the slice and the no-apply case fail

**Hypothesis, written into the probe before it ran** (`examples/probe_delay_phase.py`): QuartiCal's `delay` model is
`exp(2 pi i tau (nu - nu_mid))`, zero phase at mid-band and no phase offset, while CASA's estimator takes the peak of
`|FFT|`, which ignores a constant phase. An antenna's phase that the model does not carry then biases the
least-squares delay wherever the weights are not symmetric about mid-band (the slice's flagged channels, RFI). If
so, corrupting the model with the antenna phases (a G table pre-applied) brings rang to CASA.

**Probe -03** (`c2b-20261106-03-probe`, 67.1 s, host only, CASA's tables of run -02):

| Case | Pre-apply on the rang side | `|dtau|` median, p95, max against CASA (ns) |
| --- | --- | --- |
| slice `inf` | none (run -02) | 0.059, 0.076, 0.077 |
| slice `inf` | O-CASA's `c.G0` (phases −4.0° to +4.4°, median 2.7°) | 0.0090, 0.014, 0.014 |
| slice `120s` | `c.G0` | 0.0105, 0.014, 0.015 |
| slice `int` | `c.G0` | 0.0095, 0.022, 0.028 |
| A1 `inf` field 0, against CASA with no pre-apply | truth G only (no B) | 0.024, 0.062, 0.067 |
| CASA no pre-apply against CASA with B and G (A1 `inf` f0) | – | 0.061, 0.109, 0.151 |

So antenna phases of a few degrees move rang's delays by 0.06 ns on the slice, and removing them brings rang to
about the tolerance (one case at 0.0105 against 0.01). On A1, G alone (antenna phases per scan of up to tens of
degrees) brings the 1.30 ns median down to 0.024 ns; what is left is of the size by which B's phase ripple moves
CASA's own delays (0.061 ns). The hypothesis holds.

**Probe -04** (`c2b-20261106-04-probe`, 87.7 s, QuartiCal only): QuartiCal 0.2.7's `delay_and_offset` (a phase
offset and a delay per antenna and hand, FFT initial estimate, Gauss-Newton; C1's T12a kernel) on the same data,
nothing pre-applied, against CASA's tables of run -02:

| Case | `|dtau|` median, p95, max (ns) | Iterations |
| --- | --- | --- |
| slice `time_interval=0` against B-slice-inf | 0.0013, 0.0023, 0.0023 | 16 |
| slice `time_interval=1` against B-slice-int | 0.0018, 0.0047, 0.0064 | 17 |
| A1 field 0, raw DATA and A1's model, against B-a1-noapply-inf-f0 | 0.0033, 0.013, 0.014 | 30, 37 |

All within CASA's tolerance with 3-8 times headroom on the median. **The frozen verdict against CASA is not met;**
the cause is the estimator the brief fixed (QuartiCal's `delay`), not a defect of the port, which equals QuartiCal to
1e-14. CARACal's chain solves K first with nothing pre-applied, so with `delay` rang's K would be biased by the
antenna phases on real data. Owner decision 1 (section 9).

## 7. Class T on A1 and delay50, runs -05 and -06

`c2b-20261106-05` (264.8 s): `gaincal` route, refant m000, truth B and G pre-applied (SIGMA weights), delays against
`truth.npz` `raw_tau_ns` referenced to m000.

| Case | Twin: max product error, max `|dtau|` (ns) | Noisy: median z, limit, std z | Verdict (frozen) |
| --- | --- | --- | --- |
| a1, `int`, f0 | 2.9e-8, 9.5e-9 | **0.356**, 0.198, 1.59 | **fail** |
| a1, `int`, f2 | 3.1e-8, 1.0e-8 | −0.060, 0.153, 1.97 | pass |
| a1, `inf`, f0 | 2.9e-8, 9.5e-9 | **1.139**, 0.485, 1.15 | **fail** |
| a1, `inf`, f2 | 3.1e-8, 1.0e-8 | −0.195, 0.217, 1.99 | pass |
| d50, `int`, f0 | 1.2e-8, 3.5e-9 | −0.143, 0.198, 1.67 | pass |
| d50, `int`, f2 | 1.2e-8, 3.5e-9 | −0.022, 0.153, 1.62 | pass |
| d50, `inf`, f0 | 1.2e-8, 3.4e-9 | −0.246, 0.485, 1.65 | pass |
| d50, `inf`, f2 | 1.2e-8, 3.3e-9 | −0.012, 0.217, 1.46 | pass |

Every twin case passes (the twin columns of each row; 23-25 iterations). The float32 table delays are within 2.4e-7
ns (A1) and 3.8e-6 ns (delay50) of the truth, as section 2 expected. Median absolute errors with noise are 0.6e-4 to
5.4e-4 ns.

**The two failures, post hoc** (run -06, `check_delay.py truth --centred`, 311.5 s; the frozen numbers repeat to
the digit): the frozen z of one interval all contain the refant's own error (`tau_p - tau_r`), so a median over 15
antennas and two hands rests on two to four independent refant errors per case, not on `N`. With the delays
centred on their antenna mean per interval and hand (on both sides; gauge-free), z over `err_p`: median 0.042
(limit 0.192), 0.118 (0.149), 0.144 (0.470), 0.106 (0.210) on A1 and −0.035 to −0.322 within limits on delay50; all
eight pass. **`std(z)` is 1.5 to 2.0** in both forms: rang's `err` is low by that factor. Probable cause, estimated
and not tested: correcting by B (amplitude down to 0.23 at the band edges) amplifies the noise where the delay's
lever arm is largest, and neither rang nor the error formula rescales the weights; the expected inflation of the
delay error is 2.1-4.7 (median 3.0) for an unweighted fit on these bandpasses.

## 8. CASA applies rang's tables, run -07

`c2b-20261106-07` (15.6 s): `applycal` of run -02's `B-slice-int.rang.K` on the slice and `B-d50-inf-f0.rang.K`
(delays to 88 ns) on delay50 field 0 against `rang.cal_apply` with the same table: class C on all 470,224 and
1,474,560 cells (largest 2.6 float32 epsilons of the cell, 3.1e-7 relative), flags exact. So rang's `K Jones`
tables (one-channel window at the mean frequency, `ANTENNA2 = -1`) are read and applied by CASA as rang applies them.

## 9. What only the owner can decide

1. **The K model.** As frozen (QuartiCal's `delay`), rang's K matches QuartiCal exactly but is biased by antenna
   phases, and CARACal's chain solves K first, before any G. Options: (a) **proposed:** K solved with QuartiCal's
   `delay_and_offset` kernel (still FFT, then Gauss-Newton; the offset is discarded and G absorbs it next), which
   section 6 measured within CASA's tolerance where `delay` fails; it is C1's T12a kernel, which C1 assigns to
   `delay.rs` and C5b needs anyway, with QuartiCal as its class A oracle; (b) keep `delay` and require a G
   pre-applied, which is not CARACal's order; (c) CASA's FFT estimator alone.
2. **The solution `TIME` of K.** CASA's K times are not centroids (up to 123 s off on a 248 s `inf` scan). Reported,
   as decision 9 of the finish plan has it for G; porting the rule needs CASA's K time code found first.
3. **The delay error.** `err` ignores the weight change of a pre-applied B, and is low by 1.5-2 on A1's bandpasses.
   Accept and state it (it feeds only `PARAMERR`, which CASA leaves at 0), or rescale the weights by the pre-applied
   amplitudes (CASA's `calwt`), which C4b's weights gate may decide for the apply side.
4. **The class T bias test.** The frozen per-antenna test is not gauge-free; the centred form (section 7) is
   proposed for later C tasks.

## 10. Files, runs, provenance

Code: `core/src/cal/delay.rs` (5 Rust tests), `core/src/cal/mod.rs`, `core/py/src/cal_delay.rs` (and two lines
registering it in `core/py/src/lib.rs`), `python/rang/cal_delay.py`, `tests/test_cal_delay.py` (6 tests), the
`solved` argument of `rang.cal_gain._pre_apply`, the `delay50` version in `python/rang/simtruth.py` and
`examples/a1_simtruth.py` (small and full unchanged: the same random draws, `as_json` unchanged for them),
`examples/check_delay.py` (host side), `examples/oracle_gain.py` (several columns, FLAG edits, parameters and
chunks in `qc-copy` and `qc-solve`; C2a's calls are unchanged), `examples/probe_delay_phase.py`,
`examples/probe_delay_offset.py`. Unchanged: `solve.rs`, `jones.rs`, `correct.rs`, `diag.rs`, `reference.rs`,
`cal/apply.rs`, `core.solve_complex` (`git diff main` on them is empty). The code commit differs from the
runs' `.code/` snapshots only by `cargo fmt`, `ruff format` and two lint fixes (a `needless_range_loop` allow on
`delay.rs`'s test module, a list layout in `probe_delay_offset.py`); run -06 is the first with `--centred`.

Runs, ignored, under `/mnt/d/rang/outputs/`: `c2b-20261106-d50` (delay50, its twin, truth, RFI mask, A1's casa
checks and truth tables; 0.5 GB), `-01` (class A, `quartical.json`), `-02` (CASA, `casa.json`, CASA's `*.K` and
rang's `*.rang.K` tables, the edited MS copies), `-03-probe`, `-04-probe`, `-05` and `-06` (class T, `truth.json`;
-06 also saves every solution as `.npz`), `-07` (readback), each with its `.log` and `.code/`. Inputs read in place:
O-CASA's `work.ms`, `c.K0`, `c.G0`; A1's small version and `casa-small` truth tables. Seeds: delay50's 20261126 to
20261129; the tests 20261106 (Rust) and 20261106 and 1 (Python). Images: `rang-formats-oracle:20261030` (QuartiCal
0.2.7), `rang-o-casa:6.7.6.14`. Timings are in [tool-timings.md](tool-timings.md). Nothing was downloaded.

## 11. What was not checked

- An FFT peak that differs between rang's `rustfft` and numpy's pocketfft on a near-tie: none occurred (iteration
  counts would show it); not constructed.
- Several delay bins per window (`freq_bin`; QuartiCal's `freq_interval` for `delay`), which the kernel takes and the
  table route refuses; `combine='scan'` and `uvrange` against CASA; several windows; `initial_estimate=false` against
  QuartiCal.
- CASA's K time rule (section 5.2), and where CASA's K reads its weights (with a K FFT the per-baseline weight scale
  does not move the peak, so the cases cannot tell).
- C1's 16 x 256 x 60 set (A1 small and delay50 stand in), the whole array, and timing (forbidden here).
- `delay_and_offset` in rang: measured with QuartiCal's kernel only (section 6); not implemented.

## For the coordinator

Do not apply until merged; all text proposed.

**`research/STATE.md`, new top entry:**

> C2b, 2026-11-06 (implemented; measured; class A met, against CASA and class T not met as frozen).
> [c2b-delay.md](c2b-delay.md): the delay term K in Rust (`core/src/cal/delay.rs`, `rang.cal_delay`): QuartiCal
> 0.2.7's `delay` kernel with its FFT initial estimate (the owner's FFT, then Gauss-Newton), CASA's K conventions
> (referenced to the first refant, no flex, `minsnr` or `minblperant`, which CASA's K does not apply) and `K Jones`
> tables that CASA applies as rang does. Against QuartiCal all eight cases agree to 1e-14 ns with equal flags and
> iterations, with delay differences up to 88 ns (a new `delay50` version of A1's generator). Against CASA it
> passes wherever a G is pre-applied (nine cases, median 0.0002-0.0015 ns, refant rule equal) but fails without
> one: 0.06 ns on the slice, 1.3 ns on A1. Post hoc, the cause is `delay`'s missing phase offset; QuartiCal's
> `delay_and_offset` meets CASA's tolerance on all three failing cases. Since CARACal solves K before any G, the K
> model is an owner decision. Class T: twins within 3e-8; with noise the frozen bias test fails on A1's field 0
> because referenced delays share the refant's error; the gauge-free (centred) form, post hoc, passes everywhere.

**`research/README.md`, index line:**

> [C2b, the delay term K](c2b-delay.md): QuartiCal 0.2.7's `delay` with its FFT initial estimate in Rust, CASA's K
> referencing and tables, measured against QuartiCal, CASA `gaincal(gaintype='K')` and A1's simulated truth (with
> delays to 50 ns); why `delay` misses CASA without a pre-applied G, and `delay_and_offset` as the proposed K.

**`research/finish-plan.md`:**

- C2 row: C2b done (this note) with the K-model decision open; C2c (B, chain) should not start the chain on K until
  it is taken, since C1's step 1 solves K with nothing pre-applied.
- Section 7: add section 9's four decisions; decision 1 (the K model) blocks C2c's chain, not its B kernel.
- Note for C2c to C7: `rang.cal_gain._pre_apply` takes `solved=` (the type being solved); the class T bias test
  should be gauge-free (centred per interval, section 7).

**check-all and the index test.** As for C2a, `test_every_note_is_in_the_research_index` fails on this branch until
the README line above is applied; any other failure would be real.

**Merge notes.** This branch edits `python/rang/cal_gain.py` (one keyword of `_pre_apply`), `python/rang/simtruth.py`
and `examples/a1_simtruth.py` (the `delay50` version; small and full unchanged), `examples/oracle_gain.py`
(backwards-compatible), `core/py/src/lib.rs` (two lines next to C2a's) and `CHANGELOG.md`.

**Not removed:** `/mnt/d/rang/outputs/c2b-20261106-*` (5.7 GB: the delay50 set 1.5 GB and each run's MS copies and arrays; run -05's 1 GB repeats -06's and can
go first), kept for C2c
to C2d (delay50 has 256 channels and delays to 50 ns). `~/Github/rang/outputs/status/fp-c2b.md` can go after merge.
The two check-all logs are in `/mnt/d/rang/outputs/c2b/`, delay50's generation log in
`c2b-20261106-d50/make_d50.log`; `~/Build/tmp/20261106-c2b` (scratch scripts) is removed at the end of this task.

**Follow-up (code, not done here to keep the checked tree):** `rang.cal_delay`'s module docstring should carry the
same caveat as the CHANGELOG (CASA matched only with a G pre-applied).
