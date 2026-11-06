# C2c: K as `delay_and_offset`, the bandpass B, and the chain K, G, B

Task C2c of [finish-plan.md](finish-plan.md) (C2), step 5 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6, with the K-model decision of the finish plan
(section 7, item 11; [c2b-delay.md](c2b-delay.md) section 9). Branch `fp-c2c-bandpass`, from main `87af810`.
**Status: protocol frozen (sections 1 to 4), nothing compared yet.** Results are added below section 4, never
edited into it; this status line is the only edit above section 5.

## 1. Scope

Three parts, in this order. Each is a port with oracles; no novelty is claimed.

**Part 1: K as QuartiCal 0.2.7's `delay_and_offset`.** The coordinator's provisional choice (finish plan section 7,
item 11): CARACal solves K before any G, and plain `delay` missed CASA by 0.06-1.3 ns with nothing pre-applied
(C2b section 6), while QuartiCal's `delay_and_offset` met CASA's tolerance on those cases in C2b's probe -04.

- `core/src/cal/delay_offset.rs` (new, MIT notice kept): a translation of `quartical/gains/delay_and_offset/kernel.py`
  and `__init__.py` (`DelayAndOffset.init_term`). Parameters per antenna `[phi_x, tau_x nu_mid, phi_y, tau_y nu_mid]`
  (QuartiCal's `param_name` order `phase_offset_XX, delay_XX, phase_offset_YY, delay_YY`; only the delays scaled by
  `nu_mid`, `params[..., 1::2] *= mid_freq`); gains `exp(i (2 pi (nu / nu_mid - 1) p_1 + p_0))` per channel; the data
  scaled to the model's amplitude and the residual normalised by `|J|^2` as in `delay`; `jhr = [u_x, c u_x, u_y,
  c u_y]` and the block `[[t, c t], [c t, c^2 t]]` per hand (`compute_jhwj_jhwr_elem`, four correlations,
  `lop = I`); the update by QuartiCal's generalised `invert` (`gains/general/inversion.py`): conjugate gradients on
  the **one 4x4 system** with dot products over all four parameters, at most four steps, stop at `r^T r < 1e-30`,
  warm-started from the last (halved) update; every update halved (`update /= 2`); numbness 1e9; gain flags per
  channel; parameter flags the AND of their channels' gain flags, flagged parameters zeroed; `finalize_gain_flags`;
  `reference_params` (all four parameters minus the reference antenna's) when a reference antenna is given. The
  initial estimate is `Delay.init_term`'s FFT (the same code in both terms), reused from `delay.rs`
  (`initial_estimate`), filling the delays only; offsets start at 0. `delay.rs` is not changed in behaviour; private
  helpers are copied (C1 section 4, rule 1).
- The binding `cal_delay_offset_solve` (`core/py/src/cal_delay_offset.rs`, registered at the end of the module init).
- `rang.cal_delay.solve(..., model="delay_and_offset")` and `gaincal(..., model=...)`: **the default becomes
  `delay_and_offset`**, `model="delay"` keeps C2b's kernel; the model is recorded in `sol.settings["model"]`.
  CASA's K rules (C2b section 1) are unchanged: per interval and hand `tau_p - tau_r` to the first refant, an antenna
  without an unflagged cell on a baseline to the refant flagged, the refant unflagged at 0, no `minsnr`,
  `minblperant`, flex or strict. The offsets are referenced the same way (`phi_p - phi_r`) and returned in
  `DelaySolution.offsets` (radians). **The written table stays CASA's `K Jones`** (delays only, C2b's writer): the
  offset is not written. In CARACal's order G is solved next with K applied and absorbs it (a phase constant in
  frequency is a G). Recorded as such, not hidden.
- **The delay error with the offset.** Per interval: `chi2 = sum w |V - g_p M g_q^*|^2` with the offset in the model
  (`g = exp(i (2 pi tau (nu - nu_mid) + phi))`), over the unflagged parallel-hand cells with positive weight whose
  antennas are unflagged; `nWt` their count; `nPar` = 2 x the unflagged (antenna, hand) pairs (offset and delay);
  `k2 = chi2 / max(2 nWt - nPar, 1)`. Per antenna and hand, with `x = 2 pi (nu - nu_mid)` and the other antennas held
  fixed, `S_k = sum w x^k |V|^2` (k = 0, 1, 2) over the antenna's cells; the delay's variance is the (2,2) element of
  `k2 [[S0, S1], [S1, S2]]^-1`, `err = sqrt(k2 S0 / (S0 S2 - S1^2))` (the offset marginalised; 0 where the
  determinant is not positive). It ignores the covariance with the other antennas' parameters, as C2b's.

**Part 2: the bandpass B** (T3 of C1), CASA `bandpass(bandtype='B')` semantics, read for this note in the 2023
mirror and the 6.7.6.14 image:

- The task (`casatasks/private/task_bandpass.py`, 6.7.6.14): `setsolve(type='B', t=solint, combine, refant,
  minblperant, solnorm, minsnr, fillgaps)`; defaults `solint='inf'`, **`combine='scan'`**, `minblperant=4`,
  `minsnr=3`, `solnorm=False`, `fillgaps=0`; no `refantmode` argument, so `setsolve`'s default `'flex'`; tables to
  pre-apply set with `calwt=True`.
- The solve (`Calibrater.cc`, `genericGatherAndSolve`, mirror lines 6324-6362): per interval and per parameter
  channel (`focusChan`) a `VisCalSolver2` solve, then `formSolveSNR` and `applySNRThreshold` **per channel**;
  `verifyConstraints` (`minblperant`) per focus channel (`SolvableVisCal.cc:3741`). After all intervals,
  `globalPostSolveTinker` (`BJones::globalPostSolveTinker`, `StandardVisCal.cc:1227`): first
  `SolvableVisJones::applyRefAnt` (per window and time; a refant is good when it has an unflagged solution in any
  channel of each checked polarisation; the per-channel phasor, set to 1 where the refant's channel is flagged),
  then `fillChanGaps` when `maxgap > 0`.
- `fillChanGapArray` (`StandardVisCal.cc:1293`): per (time, antenna, polarisation), over channels: no change before
  the first unflagged channel or after the last; a gap of flagged channels between unflagged `ch1` and `ch2` is
  filled when `ch2 - ch1 <= maxgap + 1` by linear interpolation in amplitude and in phase (the phase difference
  wrapped into `[-pi, pi]` once), **in float32** (`Float a0, da, p0, dp, fch`), and its channels are unflagged.
  Rang ports it exactly, with a bounds check where CASA reads `solOKv(ich)` before testing `ich < nChan`.
  So the order is: `minblperant`, solve, `minsnr` per channel, refant, fill. A channel flagged by `minsnr` inside
  a short gap is filled and unflagged.
- Rang (`python/rang/cal_bandpass.py`, new; `core/src/cal/bandpass.rs`, new, for `fillgaps`): the solve is
  `rang.cal_gain.solve(..., freq_bin=arange(nchan), calmode='ap')`, i.e. `diag.rs`'s `diag_complex` per channel
  (QuartiCal's `diag_complex` with `freq_interval=1`), with CASA's rules per (interval, channel) from
  `reference.rs` (`minblperant`, `minsnr`, `applyRefAnt` over channels); then `fill_gaps` (binding
  `cal_bandpass_fill_gaps`). `bandpass(ms, ...)` is the Measurement Set route: `solint` and `combine` through
  `cal_gain.solint_bins`, `uvrange` on the rows, the pre-apply through `cal_gain._pre_apply(..., solved='B')`
  (B is CASA's lowest type, so every applied table corrupts the model), SIGMA weights when tables are pre-applied
  (as C2a measured for `gaincal`; not measured for `bandpass` before this note), `to_caltable` a CASA `B Jones` table
  (`CPARAM (nchan, 2)`, the full window, `ANTENNA2` the refant used, `PARAMERR`, `SNR`, `FLAG` per channel, `TIME`
  rang's centroid, `INTERVAL` the span). No `solnorm` (CARACal passes `False`), no `smodel`, no BPOLY, one window
  and one field per call.
- **Estimator difference, stated before measuring.** CASA averages the model-divided data over the interval before
  solving each channel; rang (QuartiCal's estimator) solves the least-squares problem on the cells (C2a item 3).
  With K and G applied the data inside an interval agree, so this is expected to be well inside class B; with
  `combine='scan'` and nothing applied it is not (C2a: about 1 %), which is why every class B case pre-applies.

**Part 3: the chain K, G, B** (C1 steps 1-3 of the solve sequence, finish plan C2's "chains of terms"):
`rang.cal_chain.primary(ms, field_id, ...)` (new): K by `cal_delay.gaincal` (`delay_and_offset`, nothing
pre-applied, no `uvrange`: CARACal passes `uvrange` to G, B and polcal only, C1 section 1.2), G by
`cal_gain.gaincal(gaintable=[K])`, B by `cal_bandpass.bandpass(gaintable=[K, G])`, each `interp='linear'`, returning
the three tables. Compared with the same chain run in CASA, term by term and on the composite.

Unchanged: `solve.rs`, `jones.rs`, `correct.rs`, `core.solve_complex`, `cal/apply.rs`, `diag.rs`, `reference.rs` and
`delay.rs` in behaviour (`git diff main` on them empty, except `pub(crate)` visibility if a helper must be shared;
none planned). `python/rang/cal_gain.py` is not edited (C2d works there). Not in scope: a second round (KGBAKGB),
the A step, F and `fluxscale` (C2d), `solnorm`, BPOLY, several windows or fields per call, CASA's own time-averaging
estimator as an option, and C1 step 5's whole-array scan (about 9 GB as an MS): not used here, because A1 small,
delay50 and the new held-out set cover 16 antennas with RFI and 64-256 channels, and the fetch and its MS are heavy
work outside this brief; stated as a substitution.

## 2. Tolerances (C1 section 6, restated before the first comparison)

**Class A (against QuartiCal 0.2.7).**

- K, `delay_and_offset` (`initial_estimate=true`): parameter flags and per-channel gain flags exact; every delay
  within `1e-6` ns; every offset within `1e-6` rad **modulo 2 pi** (QuartiCal's `trig_to_angle` may wrap it); every
  per-channel gain entry and parallel-hand product `g_p,h conj(g_q,h)` within `1e-6` absolute (both referenced to
  antenna 0 by QuartiCal's rule); iteration count equal per chunk; converged fraction equal to `1e-12`. Rang solves
  each scan separately, as QuartiCal's chunks; `casa_rules=False`.
- B, `diag_complex` with `freq_interval=1`, `time_interval=0` (one interval per scan chunk): gain flags exact; every
  gain entry and product per channel within `1e-6`; iterations equal per chunk; converged fraction to `1e-12`;
  `casa_rules=False`.

**Against CASA 6.7.6.14.**

- K (`gaincal(gaintype='K')`): over antennas other than the refant and hands both leave unflagged, `|tau_rang -
  tau_casa|` median `<= 0.01` ns and p95 `<= 0.03` ns, maximum reported; row-to-interval map equal (CASA's row `TIME`
  within `0.01` s of exactly one rang interval's row times, no rang interval without a CASA row); flags exact;
  `ANTENNA2` equal. Solution `TIME` reported, not gated (finish plan section 7, items 9 and 11).
- B (`bandpass(bandtype='B')`), class B per channel: on parallel-hand products `g_p,h(nu) conj(g_q,h(nu))` over
  pairs, channels and intervals both leave unflagged, relative difference median `<= 7e-4` and p95 `<= 3e-3`, the
  maximum reported. Flags gated exact per (interval, antenna, hand, channel), except a difference is reported and not
  gated where either side's SNR of that solution is within a factor 2 of `minsnr`, or where the antenna has exactly
  `minblperant` baselines in that interval and channel. **Filled channels** (flagged by the solve, unflagged by
  `fillgaps`) are gated exact as flags and their values enter the product comparison like any other. Intervals and
  `ANTENNA2` as for K; `TIME` reported.
- The chain (part 3), term by term: K by the K tolerance; G by C2a's class B on products (median `<= 7e-4`, p95
  `<= 3e-3`, flags as C2a); B by the B tolerance above. **Composite**: per row, channel and parallel hand the
  applied product of the three tables `J_p J_q^*` (each side's tables evaluated by `rang.cal_apply` corrupting a
  unit model), over cells both leave unflagged: relative difference median `<= 7e-4`, p95 `<= 3e-3` (C1 step 5,
  "B on the composite products"); composite flags exact.

**Class T (A1's simulated truth).**

- K alone, truth B pre-applied (corrects the data), **no G**, model A1's parallactic reference `P_p M P_q^T`: the
  offset must absorb G's per-scan phase. Noise-free twin: every per-channel K product `k_p,h conj(k_q,h)` with the
  table's pivot within `1e-5` of the truth's. With noise: the bias test in the **gauge-free form proposed by C2b
  (section 7) and adopted provisionally (finish plan item 11)**: delays centred on their antenna mean per interval
  and hand on both sides, `z = ec / err_p` with the part-1 error, pass when `|median z| <= 3 x 1.2533 / sqrt(N)`;
  `std(z)` reported, not gated. "Centred per interval" applies to referenced parameters (delays); products are
  already gauge-free.
- B alone, truth K and G pre-applied (both corrupt the model): noise-free twin, every per-channel parallel-hand
  product within `1e-5` absolute of the truth's; with noise, C2a's product test per channel: `z = (P_rang - P_truth)
  / s`, `s^2 = |b_q|^2 err_p^2 + |b_p|^2 err_q^2`, pass when `|median Re z|` and `|median Im z|` are both `<= 3 x
  1.2533 / sqrt(N)`; `std(z)` reported.
- The chain on the twin: only the **composite** is identifiable against the truth (K solved first absorbs any linear
  phase of A1's B, B absorbs what K and G leave), so the gate is the composite `J_p J_q^*` of rang's three tables
  against the truth's B, K, G composite, every cell within `1e-5` absolute. Per-term chain values are not compared
  with the truth. With noise the composite's median relative error is reported, not gated.

**Other gates.**

- CASA reads rang's B table: `applycal` with a rang B table against `rang.cal_apply` with the same table: class C
  (per cell `1e-6` relative or 11 float32 epsilons of the cell's largest correlation), flags exact.
- The B table layout equals a CASA-written B table's (O-CASA's `c.B0`): `VisCal`, `ParType`, `CPARAM`/`FLAG`/`SNR`/
  `PARAMERR` shapes, the window (all channels), `ANTENNA2`, `INTERVAL` convention; the values of `TIME` and
  `INTERVAL` reported.
- `fill_gaps` against a Python transcription of `fillChanGapArray` in float32 on random flag patterns: exact.
- `tools/check-all.sh`'s `gain-hashes` step passes (`4ed2aa89…`, `7b370c13…`, LUNO phase 2).

## 3. Data and settings

- **Slice:** O-CASA's `outputs/o-casa-20261030-01/work.ms` (LUNO 1934−638, field 1, scan 2, m000–m003, 32
  integrations, 2048 channels), stored `MODEL_DATA`, copied read-only into each run. O-CASA's CASA chain on it (the
  `c` arm, read from its CASA logs for this note: `setjy` CARACal's manual model into `c.ms`'s `MODEL_DATA`;
  `c.K0` `120s`; `c.G0` `120s`; `c.B0` `inf`, `combine='scan'`, `fillgaps=70`; `uvrange=''`, `minblperant=3`,
  `refant='m000'` throughout) is a second, existing CASA chain oracle; rang solves work.ms's DATA and FLAG with
  `c.ms`'s `MODEL_DATA` copied in (c.ms's own FLAG was changed by its `applycal`).
- **A1 small** (`/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/`, 16 antennas, 64 channels, 23 scans) and its
  twin; **delay50** (`/mnt/d/rang/outputs/c2b-20261106-d50`, 256 channels, delays to 50 ns). Fields 0 (J1939−6342)
  and 2 (SIM-GCAL); model A1's reference `P_p M P_q^T` (`check_gain.a1_model(..., parang=True)`); RFI mask (`any`)
  flagged on the noisy sets; truth tables `truth.K`, `truth.G`, `truth.B` (`casa-small`, `casa-delay50`).
- **Held-out set, new seeds (frozen here before it is generated):** a version `holdout256` of `rang.simtruth.design`:
  A1 small's antennas and schedule, 256 channels, `|tau|` uniform in 1-30 ns, seeds `jones 20261136, sky 20261137,
  rfi 20261138, noise 20261139` (none used before), generated as delay50 was (`examples/a1_simtruth.py generate`
  with and without `--noiseless`, then `tools/a1_checks.sh` for its truth tables and A1's checks). `as_json` of the
  existing versions unchanged.
- **QuartiCal (class A):** `rang-formats-oracle:20261030`, `/opt/qc`, C2b's options with `K.type=delay_and_offset`;
  for B `solver.terms=[B]`, `B.type=diag_complex`, `B.time_interval=0`, `B.freq_interval=1`, otherwise as C2a
  (`iter_recipe=[50]`, `convergence_criteria=1e-7`, `reference_antenna=0`, `robust=false`, `mad_flags.enable=false`,
  single-threaded, `WEIGHT_SPECTRUM`). On A1 the data and model columns hold rang's pre-applied arrays (`CDATA`,
  `CMODEL`) and FLAG the RFI mask, as C2b.
- **CASA:** `rang-o-casa:6.7.6.14`, O-CASA's container conventions. K: C2b's call (`gaincal(gaintype='K',
  refant='m000', minsnr=3, minblperant=4, combine='')`). B: `bandpass(bandtype='B', solint, combine, refant, minsnr=3,
  minblperant, solnorm=False, fillgaps, uvrange, gaintable, interp='linear')`. The run -02 CASA K tables and edited MS
  copies of C2b (`/mnt/d/rang/outputs/c2b-20261106-02/casa/`) are reused for the C2b cases (CASA is deterministic
  there; nothing is re-run on them). **Not blind:** C2b's probe -04 already ran QuartiCal's `delay_and_offset` on
  B-slice-inf, B-slice-int and B-a1-noapply-inf-f0; the held-out K cases below are CASA comparisons nobody has made.
- Rang: weights `WEIGHT_SPECTRUM` without a pre-apply, `1/SIGMA^2` with one (C2a section 6); autocorrelations
  excluded; 50 iterations, `1e-7`, stop fraction 0.99; twins `1e-10`, 1.0, 200.

## 4. Cases (frozen)

Run directories `/mnt/d/rang/outputs/c2c-20261106-NN`, one per run, heavy steps under `flock ~/.rang-heavy.lock`.
Host side: `examples/check_bandpass.py` (new; reuses `check_delay.py` and `check_gain.py`), container side
`examples/oracle_gain.py` (with a `casa-bandpass` command added).

**Part 1, K (`delay_and_offset`).**

| Case | Data | Oracle | Settings | Class |
| --- | --- | --- | --- | --- |
| A-K-slice-t1, -t4, -t0 | slice | QuartiCal `delay_and_offset` | `time_interval` 1, 4, 0 | A |
| A-K-a1-f0-t1, A-K-a1-f2-t0 | A1, `CDATA` (truth B), `CMODEL` (truth G), RFI | `delay_and_offset` | as C2b | A |
| A-K-d50-twin-f0-t1, A-K-d50-f0-t0, A-K-d50-f2-t1 | delay50, as above | `delay_and_offset` | as C2b | A |
| A-K-a1-noG-f0-t1 | A1, `CDATA` (truth B only), model A1's (no G), RFI | `delay_and_offset` | `time_interval=1` | A |
| A-K-d50-raw-f2-t0 | delay50, raw DATA, model A1's, RFI | `delay_and_offset` | `time_interval=0` | A |
| B-K (14 cases) | C2b's 13 `gaincal` K cases and `c.K0` | run -02's CASA tables | C2b's settings, rang `delay_and_offset` | B (K) |
| H-K-d50-noapply-inf-f0, H-K-d50-noapply-int-f2 | delay50, RFI flagged, nothing pre-applied | `gaincal` K (new) | `inf`, `int` | B (K), held out |
| H-K-a1-noapply-int-f2, H-K-a1-noapply-60s-f0 | A1, nothing pre-applied | `gaincal` K (new) | `int`, `60s` | B (K), held out |
| H-K-h256-noapply-inf-f0, -int-f2 | holdout256 | `gaincal` K (new) | `inf`, `int` | B (K), held out |
| T-K-{a1,d50}-{twin,noisy}-{int,inf}-f{0,2} | A1, delay50 | truth | truth B pre-applied only | T |

**Part 2, B.**

| Case | Data | Oracle | Settings | Class |
| --- | --- | --- | --- | --- |
| A-B-slice | slice, DATA, `MODEL_DATA` | QuartiCal `diag_complex`, `freq_interval=1` | `time_interval=0` | A |
| A-B-a1-f0, A-B-d50-f2 | A1 / delay50, DATA, `CMODEL` (truth K and G), RFI | as above | `time_interval=0` (per scan) | A |
| B-B-slice | slice, `gaintable=[c.K0, c.G0]` | `bandpass` | `inf`, `combine=''`, `minblperant=3`, `fillgaps=70` | B (B) |
| B-B-slice-nofill | as above | `bandpass` | `fillgaps=0` | B (B) |
| B-B-a1-f0-scan | A1, `gaintable=[truth.K, truth.G]` | `bandpass` | `inf`, `combine='scan'`, `fillgaps=0` | B (B) |
| B-B-a1-f2 | as above, field 2 | `bandpass` | `inf`, `combine=''` (10 solutions) | B (B) |
| B-B-a1-gaps | A1 f0, channels 20-22 and 40-49 flagged in every row | `bandpass` | `inf`, `combine='scan'`, `fillgaps=5` | B (B, fill) |
| B-B-a1-refchan | A1 f0, m000's rows flagged in channels 10-12 | `bandpass` | as B-B-a1-f0-scan | B (B, refant) |
| B-B-a1-snr | A1 f0, SIGMA of m009's rows x 20 | `bandpass` | as B-B-a1-f0-scan | B (B, `minsnr`) |
| B-B-d50-f0-scan | delay50, delay50's truth K and G | `bandpass` | `inf`, `combine='scan'`, `fillgaps=70` | B (B) |
| H-B-h256-f0, H-B-h256-f2 | holdout256, its truth K and G | `bandpass` | f0: `inf`, `combine='scan'`, `fillgaps=70`; f2: `inf`, `combine=''` | B (B), held out |
| T-B-{a1,d50}-{twin,noisy}-f{0,2} | A1, delay50 | truth | truth K, G pre-applied; `inf`, f0 `combine='scan'`, f2 `''` | T |
| R-B | delay50 f0 | CASA `applycal` of rang's B-B-d50-f0-scan table | `linear` | C (readback) |

**Part 3, the chain** (rang's `cal_chain.primary` against CASA's `gaincal` K, `gaincal` G (`calmode='ap'`),
`bandpass` run in sequence in one container, each with the earlier tables, `interp='linear'`; `minsnr=3`,
`refantmode` flex, `solnorm=False`).

| Case | Data | K / G / B `solint` | Other settings | Oracle |
| --- | --- | --- | --- | --- |
| C-slice | slice, field 1 | `inf` / `inf` / `inf`, `combine=''` | `minblperant=3`, `fillgaps=70`, `uvrange=''` | fresh CASA chain |
| C-slice-ocasa | slice with `c.ms`'s setjy model | `120s` / `120s` / `inf`, B `combine='scan'` | `minblperant=3`, `fillgaps=70`, `uvrange=''` | O-CASA's `c.K0`, `c.G0`, `c.B0` |
| C-a1-f0 | A1, field 0 | `inf` / `inf` / `inf`, B `combine='scan'` | `minblperant=4`, `fillgaps=70`, G and B `uvrange='>150'` | fresh CASA chain |
| C-d50-f0 | delay50, field 0 | `int` / `int` / `inf`, B `combine='scan'` | `minblperant=4`, `fillgaps=70` | fresh CASA chain |
| H-C-h256-f2 | holdout256, field 2 | `inf` / `inf` / `inf`, `combine=''` | `minblperant=4`, `fillgaps=70`, G and B `uvrange='>150'` | fresh CASA chain, held out |
| T-C-{a1,d50}-twin-f0 | A1 and delay50 twins, field 0 | `inf` / `inf` / `inf`, B `combine='scan'` | twin settings | truth composite (T) |
| T-C-{a1,d50}-noisy-f0 | A1 and delay50 | as above | | truth composite (reported) |

The held-out cases (prefix H) run once, after every other case of their part has been evaluated; any change after
that is labelled post hoc and needs a further held-out case.
