# C2c: K as `delay_and_offset`, the bandpass B, and the chain K, G, B

Task C2c of [finish-plan.md](finish-plan.md) (C2), step 5 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6, with the K-model decision of the finish plan
(section 7, item 11; [c2b-delay.md](c2b-delay.md) section 9). Branch `fp-c2c-bandpass`, from main `87af810`.
**Status: implemented and measured. Part 1 (K) and part 2 (B) met, part 1 after three labelled post-hoc changes
tested on held-out cases; part 3 (the chain) met on the composite, not as frozen term by term.** The protocol
(sections 1 to 4) was committed (`deed0ae`) before the first comparison; results are added below it, never edited
into it, and this status line is the only edit above section 5.

- **K, `delay_and_offset`:** class A against QuartiCal ten of ten at the first run (delays within 1.4e-14 ns,
  products 2.4e-13, iterations equal). Against CASA, C2b's fourteen cases pass, including the four C2b failed (the
  slice by 0.0013-0.0018 ns median where `delay` missed by 0.06; A1 without a pre-apply 0.0033 where it missed by
  1.3). Class T failed on two delay50-twin cases (a sidelobe, 1.67 ns): post hoc, rang's offset start (not
  QuartiCal's), a phase-only delay error, and the start with a model phase; then class T sixteen of sixteen, C2b's
  cases fourteen of fourteen, and **six held-out CASA cases with nothing pre-applied pass** (median 0.002-0.004 ns,
  p95 ≤ 0.013).
- **B:** class A three of three; CASA `bandpass` eight of eight (median ≤ 1e-5, p95 ≤ 2.2e-4, flags and `fillgaps`
  channels exact) and two of two held out; class T eight of eight; CASA reads rang's B table (class C).
- **Chain K, G, B:** against CASA's chain the composite passes on all five cases (one held out; median 6e-6 to
  5e-4), K passes everywhere, flags and filled channels equal; **G or B alone misses class B on all five** (they
  absorb the two K's difference, post-hoc probe). The twins' composite misses the truth's 1e-5 gate (0.015) only
  through G's `linear` interpolation (1.1e-5 with `nearest`, post hoc).
- The `gain-hashes` step of check-all passes. No novelty claim: ports with oracles.

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

## 5. Results, part 1: K as `delay_and_offset` (measured 2026-11-06)

Runs `/mnt/d/rang/outputs/c2c-20261106-NN`, each with a `.code/` snapshot (`head.txt` = the protocol commit `deed0ae`,
`diff.patch`, `untracked.tgz`, SHA-256 list) and a `.log`; heavy lock held for each. The held-out set was generated
first (`c2c-20261106-h256`: `generate holdout256` 13.1 s and `--noiseless` 10.1 s, `tools/a1_checks.sh` 73.2 s): A1's
round trip and noise checks pass on it (noise ratio 1.00009), and the parallactic check fails as on A1 small and
delay50 (CASA's frame, A1 section 7.2).

**Naming, not semantics:** the keyword is `kind=` (`"delay_and_offset"` default, `"delay"`), not section 1's
`model=`, because `model` is already `solve`'s visibility-model argument.

### 5.1 Class A against QuartiCal 0.2.7 `delay_and_offset`, run -01: ten of ten pass at the first run

`c2c-20261106-01`, 431.0 s, 1.27 GB (the container 295.9 s: ten `goquartical` of 8.6-81.9 s, 404-791 MB; rang
0.06-1.47 s per case).

| Case | Intervals (chunks) | Gains flagged | Max delay (ns) | Max offset (rad, mod 2 pi) | Max product | Iterations |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A-K-slice-t1 | 32 (1) | 175,193 | 7.5e-18 | 1.4e-17 | 2.3e-16 | 17 = 17 |
| A-K-slice-t4 | 8 (1) | 43,641 | 9.5e-18 | 1.4e-17 | 1.2e-16 | 17 = 17 |
| A-K-slice-t0 | 1 (1) | 5,447 | 1.7e-18 | 1.4e-17 | 1.2e-16 | 16 = 16 |
| A-K-a1-f0-t1 | 12 (2) | 0 | 3.6e-15 | 3.0e-15 | 4.1e-14 | 14, 15 equal |
| A-K-a1-f2-t0 | 10 (10) | 0 | 3.6e-15 | 3.1e-15 | 4.3e-14 | 15-16 equal |
| A-K-d50-twin-f0-t1 | 12 (2) | 0 | 1.4e-14 | 2.3e-14 | 2.4e-13 | 16, 16 equal |
| A-K-d50-f0-t0 | 2 (2) | 0 | 1.4e-14 | 2.2e-14 | 2.4e-13 | 16, 16 equal |
| A-K-d50-f2-t1 | 20 (10) | 0 | 1.4e-14 | 2.3e-14 | 2.1e-13 | 16-17 equal |
| A-K-a1-noG-f0-t1 | 12 (2) | 0 | 1.8e-15 | 2.7e-15 | 3.6e-14 | 34, 33 equal |
| A-K-d50-raw-f2-t0 | 10 (10) | 0 | 1.4e-14 | 2.5e-14 | 2.1e-13 | 28-50 equal |

Parameter and gain flags exact everywhere, converged fractions equal to the last digit. QuartiCal's written offsets
were not wrapped (raw and mod-2-pi differences equal). One chunk of A-K-d50-raw-f2-t0 runs 50 iterations with a
converged fraction of 0.0 on both sides: QuartiCal's own behaviour, reproduced. The class A route uses
`offset_start=False` (section 6); with it the kernel is QuartiCal's. The class A set was repeated on the final code
of section 6 as run -21 (443.3 s): ten of ten pass again.

### 5.2 Against CASA `gaincal(gaintype='K')`, C2b's cases, run -02 (frozen code): fourteen of fourteen pass

`c2c-20261106-02`, 209.6 s, 423 MB, on run -02 of C2b's CASA tables and edited MS copies (read only). Every case
C2b passed still passes, and the four C2b failed now pass (not blind for three, see section 3):

| Case | C2b (`delay`) median, p95 (ns) | `delay_and_offset` median, p95, max (ns) | Offsets (median, max) |
| --- | --- | --- | --- |
| B-slice-inf | 0.059, 0.076 | 0.0013, 0.0023, 0.0023 | 2.8°, 4.1° |
| B-slice-120s | 0.062, 0.080 | 0.0012, 0.0030, 0.0033 | 3.2°, 5.0° |
| B-slice-int | 0.059, 0.088 | 0.0018, 0.0047, 0.0064 | 2.9°, 5.0° |
| B-slice-c.K0 (O-CASA's table) | 0.071, 0.091 | 0.0092, 0.013, 0.014 | – |
| B-a1-noapply-inf-f0 | 1.30, 1.74 | 0.0033, 0.013, 0.014 | 92°, 292° |
| the nine with B and G pre-applied | 0.0002-0.0015, ≤ 0.0048 | 0.00016-0.0015, ≤ 0.0048 | ≤ 0.17° |

Flags (90 on B-a1-refant-flag on both sides), `ANTENNA2` and the bins equal CASA's on every case. B-slice-c.K0 is
near the median limit (0.0092 against 0.01) because O-CASA solved `c.K0` against its `setjy` model, while rang (and
the B-slice-120s CASA table, 0.0012 ns) used the stored model; reported, as in C2b.

### 5.3 Class T, run -03 (frozen code): fourteen of sixteen pass; the delay50 twin's field 2 fails

`c2c-20261106-03`, 151.8 s. Truth B pre-applied only, so the offsets must carry G's per-scan phases (tens of degrees
to 180°). Field 0 and A1 twins pass (products within 3.0e-8), the noisy cases pass the centred bias test, but **the
delay50 twin fails on field 2** (T-K-d50twin-int-f2 and -inf-f2): four delays 1.671 ns off, product error 2.0.
`std(z)` on field 2 was 30-47 (outliers of the same kind on the noisy sets: 37 of 640 on A1 `int`, 2 on delay50).

## 6. Post hoc, part 1: three changes, labelled, then the held-out cases

**Change 1, the offset start (after run -03).** 1.671 ns is the first sidelobe of a uniform 856 MHz band's delay
response (1.4303 / 856 MHz). Hypothesis, written into `examples/probe_offset_start.py` before it ran: the FFT
estimate is on the main lobe and Gauss-Newton started from a zero offset walks to the sidelobe when the true offset
is large. Probe `c2c-20261106-06-probe` (5.2 s): on all four bad delays the FFT estimate is within 0.0008 ns of the
truth (over all delays of the case within 0.0045 ns), and the solve ends 1.671 ns away. **The hypothesis holds, and
it is QuartiCal's behaviour** (its `delay_and_offset` starts every offset at 0; class A reproduces it). Rang's change
(`offset_estimate` in `delay_offset.rs`, `offset_start=True`, the default of `rang.cal_delay`): the offsets start at
the phase of the refant baselines' averaged data derotated by the estimated delay about `nu_mid`, with the
estimate's sign convention. Run -08 (148 s): all sixteen class T cases pass.

**Change 2, the delay error (after run -08).** With the offset start, `std(z)` was 0.04-0.35: the error was too large
by up to 25, because section 1's chi2 used the raw residual, which carries the G amplitudes (0.8-1.25) that the
phase-only term does not model. The error now uses the kernel's own residual (each datum scaled to the model's
amplitude) with one real (tangential) component per cell, `k2 = chi2 / max(nWt - nPar, 1)`.

**Change 3, the start with a model phase (after run -09).** Run -09 (C2b's CASA cases with change 1) failed
B-a1-inf-f2 and -60s-f2 (p95 1.68 ns): there the pre-applied G corrupts the model, the true offsets are near 0, and
the start taken from the data alone was the G phase. The start now averages `V conj(M)`. A Rust test covers a model
phase. Run -12 used an extension built before changes 2 and 3 compiled (a type error) and is superseded.

**With all three (the final code):**

- **Class T, run -13** (170.0 s): sixteen of sixteen pass. Twins: products within 3.1e-8 (A1) and 1.3e-8 (delay50),
  23-25 iterations (46-187 before). Noisy, centred: median z 0.001-0.12 against limits 0.15-0.47; **`std(z)` 1.39-1.71**,
  the same factor as C2b's (rang's error low by about 1.5 where B's correction amplifies the band-edge noise and the
  weights stay unscaled; C2b decision 3).
- **C2b's CASA cases, run -14** (227.2 s): fourteen of fourteen pass, every number of section 5.2 within 1e-6 ns or
  better of run -02's, with fewer iterations (13-18 against 16-37).
- **Held-out K, run -17** (84.8 s; frozen in section 4, never run before; run -16 was cut by a host reboot after four
  cases and is set aside as `c2c-20261106-16-partial-reboot`, not used):

| Case | Intervals | `|dtau|` median, p95, max (ns) | Flags differing | Offsets, median |
| --- | ---: | --- | ---: | ---: |
| H-K-d50-noapply-inf-f0 | 2 | 0.0020, 0.0050, 0.0060 | 0 | 81° |
| H-K-d50-noapply-int-f2 | 20 | 0.0021, 0.0055, 0.0085 | 0 | 90° |
| H-K-a1-noapply-int-f2 | 20 | 0.0037, 0.013, 0.022 | 0 | 81° |
| H-K-a1-noapply-60s-f0 | 2 | 0.0033, 0.013, 0.014 | 0 | 89° |
| H-K-h256-noapply-inf-f0 | 2 | 0.0037, 0.0089, 0.011 | 0 | 74° |
| H-K-h256-noapply-int-f2 | 20 | 0.0034, 0.0090, 0.012 | 0 | 84° |

All six pass, with antenna phases of up to 180° left in the data: **K as `delay_and_offset` (with rang's offset start)
meets CASA's K tolerance with nothing pre-applied**, on cases not used to make the changes. The written table holds
the delays only; the offsets (up to 180° here) are returned in `DelaySolution.offsets` and dropped from the `K Jones`
table, so G must absorb them; part 3 measures that it does.

## 7. Results, part 2: the bandpass B

### 7.1 Class A against QuartiCal `diag_complex`, `freq_interval=1`, run -04: three of three pass

`c2c-20261106-04`, 189.2 s (container 103.4 s). A-B-slice (2,048 channels, 5,447 gains flagged on both sides), A-B-a1-f0
and A-B-d50-f2: gain flags exact, entries within 6.5e-8 and products within 1.4e-7 (rang's B is stored as
complex64, the table's precision), iterations and converged fractions equal per chunk (41; 50, 50 at 0.89; ten
chunks of 50 at 0.87).

### 7.2 Against CASA `bandpass`, run -05: eight of eight pass

`c2c-20261106-05`, 305.4 s. The script stopped after the eight cases on a bug in its layout check (a boolean
unpacked as a pair), so `bcasa.json` was not written; the case results are in the log, and the checks after the cases
were rerun on run -05's tables as run -07 (`bextras`, 3.7 s), fixed.

| Case | Intervals | Products median, p95, max (relative) | Flags (both), differing | Filled by rang, flags differing | Refant |
| --- | ---: | --- | --- | --- | --- |
| B-B-slice | 1 | 1.0e-5, 3.7e-5, 5.3e-4 | 12,416, 0 | 0 | equal |
| B-B-slice-nofill | 1 | as above | 12,416, 0 | – | equal |
| B-B-a1-f0-scan | 1 | 4.4e-7, 3.2e-5, 2.0e-4 | 158, 0 | – | equal |
| B-B-a1-f2 | 10 | 1.6e-6, 2.2e-4, 1.7e-3 | 1,612, 0 | – | equal |
| B-B-a1-gaps | 1 | 5.7e-7, 7.5e-5, 0.11 | 384, 0 | 190 filled, 0; filled products 4.2e-6, 6.5e-5, 1.0e-4 | equal |
| B-B-a1-refchan | 1 | 4.7e-7, 3.2e-5, 2.0e-4 | 164, 0 | – | equal |
| B-B-a1-snr | 1 | 3.9e-7, 2.8e-5, 1.9e-4 | 158, 0 | – | equal |
| B-B-d50-f0-scan | 1 | 5.5e-7, 2.7e-6, 0.12 | 0, 0 | 920 filled, 0; 3.0e-7, 1.1e-6, 4.7e-6 | equal |

The slice's 2,048-channel B has no gap of 70 channels or fewer between its RFI-flagged blocks, so `fillgaps=70`
filled nothing there; A1 with gaps of 3 and 10 channels and `fillgaps=5` fills the first and keeps the second, as CASA
does; delay50's RFI gaps are filled as CASA fills them. B-B-a1-snr's SIGMA x 20 did not bring m009 to `minsnr` on
either side (no flag; it tests less than intended). B-B-a1-refchan: m000 stays the refant on both sides with three
channels flagged on it. The largest single differences (0.11-0.12) are reported, not gated; they are rare (p95
below 1e-4). Solution `TIME`: CASA's B time is the interval's first timestamp and its `INTERVAL` 0 (`c.B0` and run
-05's tables); rang writes the weighted centroid and the span; reported, not gated (finish plan item 9).

**Run -07, the other gates:** `fill_gaps` against a float32 Python transcription of `fillChanGapArray` on 400 random
patterns: flags equal, values within 8.4e-7 (Rust's `f32::cos` against numpy's); the B table layout equals CASA's
(`c.B0` and run -05's `B-B-slice.B`): `VisCal`, `ParType`, `CPARAM`/`FLAG`/`SNR`/`PARAMERR` `(2048, 2)`, the full window,
`ANTENNA2`.

### 7.3 Class T, run -10: eight of eight pass

`c2c-20261106-10`, 330.8 s. Truth K and G pre-applied (both corrupt the model). Twins: products within 4.5e-7 (A1)
and 4.4e-7 (delay50), the complex64 table rounding. Noisy: median Re z and Im z within 0.008 against limits
0.005-0.032 (T-B-d50-f2: 0.0018 and -0.0006 against 0.0051), `std` 0.70-0.71, what a correct complex error gives.

### 7.4 CASA reads rang's B table, run -11; held-out B, run -15

- R-B (`c2c-20261106-11`, 9.0 s): `applycal` of run -05's B-B-d50-f0-scan rang table against `rang.cal_apply`: class C
  on 1,474,560 cells (2.9 float32 epsilons of the cell, 3.9e-7 relative), flags exact.
- H-B-h256-f0 and -f2 (`c2c-20261106-15`, 110.4 s, run once): pass. Products 5.4e-7 / 1.1e-5 (f0) and 1.9e-6 / 4.5e-5
  (f2) median / p95; 504 and 5,712 channels filled by `fillgaps=70` with flags equal to CASA's and filled products
  within 1.9e-5; refant equal.

B is solved with SIGMA weights when tables are pre-applied, as C2a measured for `gaincal`; that `bandpass` does the
same is now supported by every class B case (all pre-apply), not shown directly.

## 8. Results, part 3: the chain K, G, B

### 8.1 Run -18 (frozen cases) and run -19 (held out): the composite passes everywhere; G and B alone do not

`c2c-20261106-18` (294.7 s; CASA's three tasks 1.1-1.8 s each, rang's chain 4.5-17.5 s) and `-19` (52.3 s, run once).
Rang's K is `delay_and_offset` with the offset start (the final code of section 6).

| Case | K `|dtau|` median, p95 (ns) | G products median, p95 | B products median, p95 | Composite `K G B` median, p95, max | Flags | Verdict (frozen) |
| --- | --- | --- | --- | --- | --- | --- |
| C-slice | 0.0013, 0.0023 | **8.0e-4**, 1.8e-3 | 3.2e-4, 2.1e-3 | 1.9e-5, 2.4e-4, 1.2e-3 | equal, refant equal | fail (G) |
| C-slice-ocasa (O-CASA's tables) | 0.0089, 0.015 | **5.4e-3, 1.1e-2** | **2.1e-3, 1.2e-2** | 5.3e-4, 2.8e-3, 1.0e-2 | equal | fail (G, B) |
| C-a1-f0 (`uvrange='>150'`) | 0.0033, 0.013 | 5.1e-4, 2.8e-3 | **4.8e-3, 3.1e-2** | 1.6e-4, 7.5e-4, 1.5e-2 | equal; 158 filled, equal | fail (B) |
| C-d50-f0 | 0.0021, 0.0051 | 2.1e-4, 8.5e-4 | **2.7e-3, 1.2e-2** | 2.3e-4, 1.2e-3, 5.4e-3 | equal; 920 filled, equal | fail (B) |
| H-C-h256-f2 (held out, `'>150'`) | 0.0034, 0.0091 | **1.5e-3, 4.9e-3** | **4.0e-3, 2.0e-2** | 5.9e-6, 4.9e-5, 2.3e-2 | equal; 5,712 filled, equal | fail (G, B) |

So **every K passes, every composite passes class B, every flag, filled channel, bin and refant equals CASA's**, and
G or B alone misses class B on all five, by up to a factor 7 (G) and 10 (B) on the median. The class T twins:

| Case | Composite against the truth, max abs | Median relative | Verdict (frozen) |
| --- | ---: | ---: | --- |
| T-C-a1twin-f0 | **0.015** | 6.7e-6 | fail |
| T-C-d50twin-f0 | **0.017** | 8.1e-6 | fail |
| T-C-a1-f0, T-C-d50-f0 (noisy, reported) | 0.30, 0.47 | 9.7e-4, 9.8e-4 | – |

### 8.2 Post hoc: what the failures are (probe -20)

`examples/probe_chain_terms.py`, `c2c-20261106-20-probe` (149.7 s, rang only, run -18's CASA tables), with both
hypotheses written into it before it ran.

1. **G and B alone carry K's difference.** Partial composites, median / p95 relative to CASA's:

   | Case | B alone | `K B` | G alone | `K G` | `K G B` |
   | --- | --- | --- | --- | --- | --- |
   | C-a1-f0 | 4.8e-3 / 3.1e-2 | 5.8e-4 / 3.2e-3 | 5.1e-4 / 2.8e-3 | 4.8e-3 / 3.1e-2 | 1.6e-4 / 7.5e-4 |
   | C-d50-f0 | 2.7e-3 / 1.2e-2 | 3.8e-4 / 1.4e-3 | 2.1e-4 / 8.5e-4 | 2.7e-3 / 1.2e-2 | 2.3e-4 / 1.2e-3 |
   | C-slice | 9.7e-4 / 4.0e-3 | 9.4e-4 / 2.0e-3 | 8.0e-4 / 2.0e-3 | 9.9e-4 / 4.0e-3 | 1.9e-5 / 2.4e-4 |

   These are applied cells through `rang.cal_apply`, which bridges flagged solution channels by frequency
   interpolation, so on the slice (12,416 flagged B solutions) they include bridged channels that section 8.1's
   per-term table comparison leaves out (B alone there: 3.2e-4 against 9.7e-4 here); the composite's equal flags
   likewise count applied cells, not solutions. On A1 and delay50, B absorbs the residual phase slope of the two sides' K (0.002-0.013 ns of delay difference is
   0.5-3.5° at the band edges): `K B` is 8-10 times closer to CASA's than B alone. G absorbs the rest (the phase at
   the pivot, including the offsets rang's K table drops), so only the full composite is a like-for-like quantity.
   On the slice the four antennas' differences are small everywhere and the composite agrees to 2e-5. **The
   hypothesis holds for B; for G it holds in the sense that only `K G B` is gauge-free**, which C1 section 2.1 said
   for K ("compare applied products only after G") and which, with K's offsets dropped, extends to G and B: the
   per-term gates of section 2 were not gauge-free in a chain. **Rang's chain equals CASA's where the chain is
   identifiable (the composite), and differs term by term by how the two K estimators split phase between K, G and
   B.**
2. **The twins' composite misses only through G's time interpolation.** With `interp='nearest'` (each row gets its
   scan's G, which steps from scan to scan in A1) on both rang's and the truth's tables, the composite meets the
   truth to **1.03e-5 (A1) and 1.13e-5 (delay50)** against the 1e-5 gate, against 0.015-0.017 with `linear`, the
   difference being rows between a scan's solution time and its end, which `linear` pulls towards the next scan's G.
   What is left is at the size of the float32 K table's rounding (C2b section 2: up to 8e-6 rad per antenna at the
   band edge). The gate was written with `linear`, as CARACal applies; the error is the interpolation of per-scan
   solutions across A1's scan-to-scan steps, not the solves'. CASA's chain tables were not put through the same
   comparison. Post hoc, not a pass as frozen.

### 8.3 What the chain can and cannot claim

- **Can:** rang's K, G, B chain in CARACal's order (K first, nothing applied) gives an applied calibration whose
  composite `J_p J_q^*` equals CASA 6.7.6.14's chain within class B on the slice, A1, delay50 and a held-out set
  (median 6e-6 to 5e-4, p95 5e-5 to 2.8e-3), with flags, filled channels, intervals and refants equal; K alone is
  within CASA's K tolerance on every case; against the truth, the twins' composite is within 1.1e-5 when G is applied
  `nearest`.
- **Cannot (as frozen):** term-by-term class B for G and B against CASA's chain (they absorb the K difference), and
  the 1e-5 twin gate with `linear`. A later task that compares single terms of a chain against CASA should pre-apply
  CASA's own earlier tables to rang's solve (as part 2 did), or compare composites.

## 9. What only the owner can decide

1. **The K model and its start** (finish plan item 11, provisional): `delay_and_offset` is now rang's default K and
   meets CASA with nothing pre-applied (section 6, held out). It needs rang's offset start, which is not QuartiCal's
   (QuartiCal 0.2.7 starts the offsets at 0 and can end on the delay response's first sidelobe, 1.43 / bandwidth
   away; class A reproduces that with `offset_start=False`). Options: accept the start (proposed; it keeps "FFT, then
   Gauss-Newton", the FFT now seeding the offset too), or report the sidelobe to QuartiCal and keep its start.
2. **K's offsets are not written.** The `K Jones` table holds delays; the offsets (up to 180°) are left for G. CASA's
   K has no offset either, so the chain is CASA's; a K table alone applied without G leaves the offsets in the data.
   Proposed: keep, and say so wherever a K table is applied alone.
3. **The chain's per-term gates.** Term-by-term comparisons in a chain are not gauge-free (section 8.2). Proposed: in
   C2d to C7, gate a chain on the composite and each term with the oracle's own earlier tables pre-applied.
4. **The delay error** (C2b decision 3, still open): with the phase-only residual, rang's error is low by 1.4-1.7 on
   A1's bandpass-corrected data, as C2b found.
5. **B's `TIME` and `INTERVAL`:** CASA writes the interval's first timestamp and `INTERVAL` 0 for B; rang writes the
   weighted centroid and the span. Reported, as for G and K (item 9).

## 10. Files, runs, provenance

Code: `core/src/cal/delay_offset.rs` (6 Rust tests), `core/src/cal/bandpass.rs` (`fillgaps`, 3 tests),
`core/src/cal/mod.rs`, `core/py/src/cal_delay_offset.rs` (`cal_delay_offset_solve`, `cal_bandpass_fill_gaps`;
three lines at the end of `core/py/src/lib.rs`'s module init and one `mod` line), `python/rang/cal_delay.py`
(`kind`, `offset_start`, `offsets`), `python/rang/cal_bandpass.py`, `python/rang/cal_chain.py`, the `holdout256`
version in `python/rang/simtruth.py` and `examples/a1_simtruth.py` (other versions unchanged),
`tests/test_cal_delay.py` (C2b's tests pinned to `kind="delay"`, four new), `tests/test_cal_bandpass.py` (6),
`examples/check_bandpass.py`, `examples/probe_offset_start.py`, `examples/probe_chain_terms.py`, the `casa-tasks`
command of `examples/oracle_gain.py`. **Unchanged:** `solve.rs`, `jones.rs`, `correct.rs`, `diag.rs`,
`reference.rs`, `delay.rs`, `cal/apply.rs`, `core.solve_complex`, `python/rang/cal_gain.py`. Runs used the working
tree on `deed0ae`, snapshot per run in `.code/`; the code commit adds formatting and this note.

Runs under `/mnt/d/rang/outputs/`: `c2c-20261106-h256` (holdout256, its twin, truth, RFI mask, truth tables, A1's
checks; 1.5 GB), `-01` (K class A), `-02` (K vs CASA, frozen code), `-03` (K class T, frozen code), `-04` (B class
A), `-05` (B vs CASA; JSON not written, see 7.2), `-06-probe`, `-07` (B extras), `-08` (K class T after change 1),
`-09` (K vs CASA after change 1: two failures), `-10` (B class T), `-11` (B readback), `-12` (superseded: stale
extension), `-13` (K class T, final), `-14` (K vs CASA, final), `-15` (held-out B), `-16-partial-reboot.log` (cut by
the host reboot; its outputs deleted, not used), `-17` (held-out K), `-18` (chain), `-19` (held-out chain),
`-20-probe` (chain terms), `-21` (K class A repeated on the final code). Inputs read in place: O-CASA's `work.ms`,
`c.ms` (its model), `c.K0`, `c.G0`, `c.B0`; A1 small, delay50 and their truth tables; C2b's run -02 CASA tables and
MS copies. Seeds: holdout256's 20261136-20261139; tests 20261106 (Rust, Python) and 1, 7 (Python). Images:
`rang-formats-oracle:20261030` (QuartiCal 0.2.7), `rang-o-casa:6.7.6.14`. Timings in
[tool-timings.md](tool-timings.md). Nothing was downloaded.

## 11. What was not checked

- C1 step 5's whole-array scan (section 1, substitution), several windows, `combine='spw'`, `solnorm`, BPOLY, a
  second round (KGBAKGB), `uvrange` on K (CARACal does not pass it), `refantmode='strict'` for B (CASA's `bandpass`
  has no such argument).
- B's `minsnr` flag against CASA: B-B-a1-snr's SIGMA x 20 flagged nothing on either side; no case reached the
  threshold. The time-averaging estimator difference was never large enough to show (all class B cases pre-apply).
- The offset start's accuracy as a phase estimate on its own (only the solve's end point is gated); `offset_start`
  with `freq_bin` of more than one delay bin.
- Nothing further on class A: K's was run on the frozen code (-01) and repeated on the final code (-21, 443.3 s:
  ten of ten pass again, `offset_start=False`); class A for B uses the unchanged `diag.rs`.
- Timing (forbidden here).

## For the coordinator

Do not apply until merged; all text proposed.

**`research/STATE.md`, new top entry:**

> C2c, 2026-11-06 (implemented; measured; parts 1 and 2 met after labelled post-hoc changes and held-out runs; the
> chain met on the composite, not term by term). [c2c-bandpass.md](c2c-bandpass.md): K is now QuartiCal 0.2.7's
> `delay_and_offset` in Rust (`core/src/cal/delay_offset.rs`, `rang.cal_delay` default; `kind="delay"` keeps C2b's),
> equal to QuartiCal to 2.4e-13 (products) on ten cases. With rang's offset start (post hoc: QuartiCal's zero start lands on the
> delay response's first sidelobe, 1.67 ns off, when antenna phases are large) it meets CASA's K with nothing
> pre-applied on C2b's fourteen cases and six held-out ones. The bandpass B (`rang.cal_bandpass`: `diag_complex`
> per channel, CASA's per-channel `minblperant`, `minsnr`, refant and `fillgaps`, `B Jones` tables) equals QuartiCal
> (1e-7, complex64), CASA `bandpass` (eight cases and two held out, median ≤ 1e-5, p95 ≤ 2.2e-4, flags and filled
> channels exact)
> and A1's truth. The chain K, G, B (`rang.cal_chain.primary`) equals CASA's chain on the composite on five cases
> (one held out), but G and B alone miss class B because they absorb the two K estimators' difference; the twin
> truth gate misses 1e-5 only through G's `linear` interpolation (1.1e-5 with `nearest`).

**`research/README.md`, index line:**

> [C2c, K as delay_and_offset, the bandpass B and the chain](c2c-bandpass.md): QuartiCal's `delay_and_offset` in
> Rust with rang's offset start, CASA's `bandpass` with `fillgaps`, and the chain K, G, B, measured against
> QuartiCal, CASA and A1's simulated truth with a new held-out set (`holdout256`).

**`research/finish-plan.md`:**

- C2 row: C2c done (this note); C2d open. The K model (item 11) is implemented as proposed; its offset start is a new
  owner decision.
- Section 7: add section 9's decisions 1 to 3 and 5 to item 11 (decision 4 is C2b's decision 3).
- Note for C2d to C7: compare a chain on the composite, or pre-apply the oracle's earlier tables to each term;
  `rang.cal_delay` defaults to `delay_and_offset`; `holdout256` is a fresh held-out simulated set (256 channels).

**check-all and the index test.** `test_every_note_is_in_the_research_index` fails on this branch until the README
line above is applied; any other failure would be real.

**Merge notes.** This branch edits `core/py/src/lib.rs` (one `mod` line, three registration lines at the end),
`core/src/cal/mod.rs`, `python/rang/cal_delay.py`, `python/rang/simtruth.py`, `examples/a1_simtruth.py`,
`examples/oracle_gain.py` (backwards-compatible) and `CHANGELOG.md`; it does not edit `python/rang/cal_gain.py` (C2d).

**Not removed:** `/mnt/d/rang/outputs/c2c-20261106-*` (about 7.3 GB; `-01`, `-04`, `-05`, `-17` hold MS copies and can
go first; keep `-h256` for later tasks as a held-out set). `~/Github/rang/outputs/status/fp-c2c.md` can go after
merge. `~/Build/tmp/20261106-c2c` (scripts) is removed at the end of this task.
