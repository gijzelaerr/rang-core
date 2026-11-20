# K solve without baselines to the reference antenna (issue #53)

Status: **measured 2026-11-21 (section 6): G1, G2 and G3 pass; ships as `refantmode: flex` for K. Frozen 2026-11-20 before any code.** Reported by an external tester in #51
(SARAO block 1680477139): when residual flagging removed every baseline to the reference antenna on a
calibrator scan, the K solve flagged 21-23 of 62 antennas, and G, Gsec and F followed (35-39 % of
solutions flagged). Procedure: `docs/agents/propose-and-measure.md`.

## 1. What rang and CASA do today (read)

- **rang** (`python/rang/cal_delay.py`, `casa_rules=True`, the default): the delays come from one
  joint solve over all baselines (QuartiCal's `delay_and_offset` kernel, `core/src/cal/delay_offset.rs`).
  The FFT start uses the baselines to the first refant only (`core/src/cal/delay.rs`,
  `initial_estimate`); an antenna without such a baseline starts at zero. Then CASA's rules are
  applied after the solve. An antenna without an unflagged cell on a baseline to the first refant is
  flagged. When the first refant has no data in an interval, every other antenna is flagged and the
  refant is kept at 0. `refantmode` and the rest of the refant list are not used.
  `tests/test_cal_delay.py::test_casa_k_referencing_flags_what_casa_cannot_solve` pins this.
- **CASA 6.7** (casa6 `KJones.cc`, `SolvableVisCal.h`, read 2026-11-20 from
  open-bitbucket.nrao.edu, branch master): `refant()` is `refantlist()(0)`. `DelayFFT` and
  `KJones::solveOneVB` use only the rows to `refant()`. An antenna without one gets no solution
  (`solveParOK` false), and the refant is set to 0 and OK. `KJones` overrides
  `globalPostSolveTinker()` with an empty body, so `applyRefAnt`, and with it `refantmode` flex or
  strict and the rest of the refant list, never applies to K. So CASA has the same limitation:
  rang reproduces CASA, and Killick's case is CASA's behaviour too.

So the fix is a deliberate deviation from CASA, in the cases CASA cannot solve. Elsewhere rang must
stay CASA's, bit for bit.

## 2. The change

Per solution interval (and frequency bin):

1. **Reference.** The interval's reference is the first antenna of the refant list that has an
   unflagged cross-correlation cell in the interval. If none has, it is the antenna with the most
   unflagged cross cells (lowest index on a tie). Delays are referenced to it, and `refant_used`
   records it per interval (the field exists). The K table's `ANTENNA2` stays -1, as CASA's. This is
   `refantmode: flex` for K, which CASA does not implement. Under `refantmode: strict` the
   interval is flagged, as today.
2. **Which antennas are solved.** An antenna is solved when it is connected to the interval's
   reference through unflagged baselines (any path), not only directly. Its delay is the joint
   solve's, which already uses every baseline. Antennas not connected stay flagged.
3. **Start.** In the FFT start, a time bin in which the estimate antenna (the first refant) has no
   rows uses the antenna with the most unflagged rows instead. Then a second pass starts each
   antenna that has data but no baseline to the estimate antenna. It uses the FFT on its rows to
   the best-linked already-started antenna, which becomes a hop: `tau_p = tau_h + tau_(p,h)`. The
   offsets of `delay_and_offset` start as today; for hop-started antennas that is 0.

**Bit-identical otherwise.** In an interval where the first refant has data and every antenna with
data has an unflagged baseline to it, none of 1-3 changes anything. The start's second pass and
fallback do not trigger, the connected set equals the directly linked set, and the reference is the
first refant.

## 3. Gates (frozen)

- **G1, bit-identical where the refant's baselines are present.** The test suite, the gain-hash gate
  (its K `original` slice, `4ed2aa89…`), and C2b's exact replays, unchanged. `refantmode: strict`
  keeps today's flagging. The one test that pins today's flagging of a missing reference is changed
  on purpose, and the change is stated.
- **G2, truth** (a simulation as `tests/test_cal_delay.py::simulate`: 12 antennas, 4 intervals,
  856-1712 MHz, delays uniform in ±8 ns and, as a second case, ±50 ns; `delay_and_offset` and
  `delay`):
  - case A: every baseline to the first refant flagged in interval 1 (refant list [r0, r1]);
  - case B: the first refant present, but one antenna's baseline to it flagged in interval 2;
  - noise-free twin: every solved delay, referenced to the interval's reference, within 1e-6 ns of
    the truth, and no antenna with data flagged (in case A, r0 itself has no data in interval 1);
  - with noise: C2b's class T bias test per case, `|median z| ≤ 3 × 1.2533 / sqrt(N)`.
- **G3, CASA 6.7.6.14** (`gaincal gaintype='K'`, `rang-o-casa_6.7.6.14.sif`; the noisy simulation as
  an MS; C2b's tolerances: median ≤ 0.01 ns, 95th percentile ≤ 0.03 ns, over antennas both solve):
  - CASA at refant r0 against rang on every interval and antenna CASA solves;
  - interval 1 of case A against CASA at refant r1 on that scan;
  - case B's antenna against a CASA solve at refant h (the hop) on that scan, composed with the r0
    run: `(tau_p − tau_h) + (tau_h − tau_r0)`, at √2 × the tolerances.
- **Decision.** G1, G2 and G3 pass: the change ships as the behaviour of `refantmode: flex` (the
  default), and `docs/limits.md` and `docs/concepts` say where rang now solves what CASA flags. G1
  fails: nothing ships. G2 or G3 fails: the failure is recorded; one dated revision is allowed within
  the day, then the outcome is recorded as is.

## 4. Host

Simulation and tests on glacier (free until Saturday 20:50); CASA on nash (apptainer image), or WSL.
Timing rows in `research/tool-timings.md`.

## 5. Clarification 1 (2026-11-21, after the first test run; the simulation, not the method)

The ±50 ns case of G2 at 64 channels over 856 MHz is aliased: the channel spacing of 13.375 MHz
repeats a delay every 74.8 ns, and relative delays reach 100 ns. The first run failed in an
interval with no flagging at all (antenna 10, hand Y: truth −63.79 ns, solved +11.0 ns, one period
apart), where the change does nothing, so the old code fails it as well. The ±50 ns case therefore
uses 256 channels (299 ns period); the ±8 ns case keeps 64. Tolerances and the rule are unchanged.

## 6. Measured (2026-11-21, nash; commit 47684e36 and its successor)

- **G1, bit-identity: pass.** Quick check on nash: 345 tests passed (4 skipped), the gain-hash gate
  passed (its K `original` slice among them), and Rust's 316 core tests passed.
  `tests/test_k_refant_53.py::test_flex_equals_strict_bit_for_bit_with_the_refant_present` checks
  delays, flags, errors, offsets and iterations bit for bit, for `delay` and `delay_and_offset`,
  on a noisy simulation with 20 % of non-refant baselines and 5 % of cells flagged. The old test
  of CASA's flagging now runs at `refantmode="strict"`, unchanged otherwise.
- **G2, truth, noise-free: pass.** `test_flex_solves_what_casa_flags` (±8 ns at 64 channels,
  ±50 ns at 256; both kinds): case A's interval is referenced to the next refant (`refant_used`
  [0, 1, 0, 0]), case B's antenna is solved, no antenna with data is flagged, and every delay is
  within 1e-6 ns of the truth. Without a listed refant with data, the best-connected antenna
  becomes the reference.
- **G2, truth, with noise, and G3, CASA** ([k53_g3.py](results/k53-scripts/k53_g3.py); 12 antennas,
  4 scans of 6 integrations, 64 channels, ±8 ns, 0.3 Jy noise on 10 Jy; run root
  `nash:~/rang-data/outputs/k53-20261121/`; [results/k53/](results/k53/)):

| Check | n | Median | p95 | Max | Tolerance | Result |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| G2 class T, all solved delays: median z | 86 | −0.31 | – | – | abs at most 0.405 (std z 0.96) | pass |
| G3, rang (flex) − CASA at m000, where both solve | 70 | 0.0005 ns | 0.0016 ns | 0.0019 ns | median 0.01, p95 0.03 | pass |
| G3, case A interval − CASA at m001 on that scan | 22 | 0.0006 ns | 0.0014 ns | 0.0017 ns | median 0.01, p95 0.03 | pass |
| G3, case B antenna (2 hands) − CASA composed (m001, then m000) | 2 | – | – | 0.0006 ns | 0.042 ns | pass |

  CASA at m000 leaves 12 antenna-intervals unsolved (the 11 antennas of case A's interval, and case
  B's antenna). rang with flex leaves none with data. With strict, rang flags the same as CASA.
- **Scoring correction, labelled.** The first score of G2's bias test divided by the antenna's
  error alone and failed (median z −0.44, bound 0.405, std 1.37). C2b's frozen definition, which
  section 3 names, uses s² = err_p² + err_ref². With it the test passes, as above, and also apart:
  intervals the change does not touch give −0.45 against 0.47 (N 64), the changed ones −0.08
  against 0.80 (N 22). The tolerance is unchanged; the script was wrong.

## 7. Outcome

G1, G2 and G3 pass, so under section 3's rule the change ships as the behaviour of
`refantmode: flex`, the default for K. `docs/limits.md` records that rang now solves K where CASA
leaves it flagged, and `calibrate.refantmode`'s comment says so. Not checked: Killick's block
1680477139 itself (not fetched here), and the downstream G, Gsec and F after a flex K (#51's
35-39 % of flagged solutions), which follow from K's flags but were not re-run.
