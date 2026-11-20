# K solve without baselines to the reference antenna (issue #53)

Status: **proposed, frozen 2026-11-20 before any code.** Reported by an external tester in #51
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
