# DD4d: longer off-axis solution intervals on ESO 137-006

Issue #15. Follows [dd4c-eso137.md](dd4c-eso137.md) (DD4c),
[dd4b-eso137.md](dd4b-eso137.md) and [dd4-eso137.md](dd4-eso137.md).
Branch `dd4-eso137`. Owner decision 2026-11-24, relayed by the coordinator.
Sections 1-5 are frozen 2026-11-24, before the code that runs them. Later
changes are dated amendments.

Status: **proposed.**

## 1. Hypothesis

In DD4b and DD4c, 0.4-2.4 % of the off-axis solution cells converged at
4 × 8 s intervals, in every mode. The off-axis sources are 83 mJy to 0.97 Jy
apparent. At 32 s per solution, each antenna's solution has too little
signal from them to fix its gain.

**Hypothesis:** longer solution intervals give each solution more signal.
At some interval the off-axis solves converge. At that interval, DD against
DI0 and parity with QuartiCal and WSClean can be read on determined gains.

## 2. Step 1: the interval grid (rang only)

**Solves:** one cycle-0 solve per grid point.
- d0 is pinned. M₀ is DD4c's start model: DI0's cycle-4 model, SHA-256
  `619891d3…4914a`.
- Cap 500, stop criterion 1e-7, stop fraction 0.99. Directions, facets and
  the subset are as in DD4.

**Grid:**

| Axis | Values |
| --- | --- |
| kind | `phase` (each direction's own gain, as DD4c's Rc), `diag_complex` (amplitude and phase) |
| time interval | 4, 16, 64 and 450 integrations of 8 s (32 s, 128 s, 512 s, and the whole 1 h scan) |
| frequency interval | the full 64-channel band |

That is 8 solves. Only the full band is used. A narrower frequency interval
holds less data per solution, so it cannot converge where the full band
does not. Frequency chunks are tried only if the full band converges at
4 × 8 s.

**Convergence criterion:** DD4c section 3's per-direction measure.
- Each solve is repeated with the cap one iteration longer and the stop
  fraction at 1.
- A cell has converged if `|Δg|²/|g|² < 1e-14` between the two solves.
  Flagged cells are left out.
- A direction converges if its fraction is ≥ 0.99.
- A grid point converges if d1, d2 and d3 all converge.

**Choice of interval and kind (frozen):**
- If `diag_complex` converges at some grid interval, the loop uses
  `diag_complex` at the shortest such interval T*. It is preferred because
  QuartiCal#459 affects only QuartiCal's DD `phase`.
- Otherwise, if `phase` converges at some grid interval, the loop uses
  `phase` at its shortest T*.
- Otherwise the outcome is **no converging interval in the grid**. The loop
  and the oracle are not run.

## 3. Step 2: the loop at T* (arms)

| Arm | Solve | Imaging |
| --- | --- | --- |
| **Rd** | rang, the chosen kind, interval T*, d0 pinned, cap 500 | rang |
| **DI0c** | none (DI0, frozen in DD4b; DD4c's run is reused, since the interval does not act on a pinned direction) | rang, one facet |
| **Od** | QuartiCal 0.2.7, the same kind (`G.type`), `G.time_interval` = T*, `G.freq_interval=0`, `iter_recipe=[500]`, `G.pinned_directions=[0]` | WSClean 3.7 on DD4 A5's matched copy (the workaround for [aroffringa/wsclean#211](https://gitlab.com/aroffringa/wsclean/-/issues/211)) |

Some details by kind:
- With `phase`, the parity arm uses QuartiCal's last-direction gain in rang
  (arm **Rdq**), as in DD4c's Rq. Rd itself keeps each direction's own
  gain.
- With `diag_complex`, Rd is its own parity arm.

Five major cycles plus the final solve, and the minor cycle and measures of
DD4, as before. Each cycle records Rd's per-direction convergence.

## 4. Decision rules (frozen)

- **DD against DI0 (Rd against DI0c):** DD4b's `q₀` rule.
  - **DD helps (rang only):** `q₀ ≤ 0.90` and DR(Rd) ≥ DR(DI0c).
  - **Null:** `0.90 < q₀ < 1.05`, or `q₀ ≤ 0.90` with DR(Rd) < DR(DI0c).
  - **DD worse:** `q₀ ≥ 1.05`.
- **Parity (Rd, or Rdq, against Od):** gates L and S as DD4 section 5, with
  the implemented rule: S is relaxed to 2 % only with parity up to the rule.
- **Outcome:**
  - **Pass and DD helps:** L and S hold, every cycle's off-axis solve
    converges, and `q₀ ≤ 0.90` with DR(Rd) ≥ DR(DI0c). This would be the
    first oracle-checked real-data DD gain.
  - **Pass, null** or **pass, DD worse:** L and S hold, with the
    corresponding `q₀` reading.
  - **Parity failure:** L or S fails. The first differing cycle and
    quantity are recorded.
  - **Not converged in the loop:** an off-axis direction falls below 0.99
    in a later cycle. This is recorded beside the readings, which then stay
    rang only.

## 5. Host use

- rang solves book 8 slots.
- The QuartiCal arm books **2 slots**. QuartiCal runs single-threaded, and
  WSClean runs with `-j 2` in that arm, so that the booking is honest. That
  is a thread-count change only.
- WSL scratch goes on ext4 and is deleted at the end.

## 6. Measured result

Not yet run.

## Amendments

**A1, 2026-11-24, measure fix, post hoc (after one grid point,
`diag_complex` at 64 integrations; no decision was read).**
- The per-direction measure compared the solver's *referenced* output
  gains. Referencing rotates every gain of an interval by the reference
  antenna's gain (`reference_gains` in `core/src/cal/diag_dd.rs`). So the
  reference antenna's own change between iteration n and n + 1 counts
  against every cell, and the measure overstates non-convergence.
- The solver's own test is on the unreferenced iterates.
- **Fix:** the grid's two solves run with `refant=None`. The measure is
  then exactly the solver's step test, per cell. The gain products, which
  the predict, the imaging and gate L use, do not depend on the reference.
- The first point (`diag_complex`, 64) read 0.0 in d1-d3 by the old
  measure; it is rerun. The solver's aggregate fraction there was 0.276,
  that is 3.5 % of the off-axis cells.
- DD4c's per-direction numbers used the same referenced measure. Their
  verdict does not change, because the solver's aggregate fraction was 0.25
  there: no off-axis cell converged by the solver's own count. A note is
  added to DD4c.
- The step-2 loop records the measure with `refant=None` solves as well.
  Its science solve keeps `refant=0` (DD4).

- *Check of the measure (2026-11-24, `diag_complex` at 64 integrations, 20
  and 60 iterations).*
  - Two solves with the same cap are identical (maximum difference 0), so
    the measure is not seeing run-to-run noise.
  - The unflagged off-axis cells keep moving. The median relative change
    per iteration, `|Δg|²/|g|²`, falls from 7.5e-6 to 3.0e-7 (d1) and from
    4.4e-4 to 4.0e-5 (d2) between iteration 20 and 60, against the 1e-14
    test.
  - The cells that do not move are the flagged ones, about 19 % in d2 and
    d3, whose gains are set to 1. Flags also change between successive
    iterations.
  - The solver's aggregate count (0.274-0.276) is above 0.25 by about this
    flag bookkeeping, not by converged unflagged cells.
  - So the per-direction measure (unflagged cells only) stands.
