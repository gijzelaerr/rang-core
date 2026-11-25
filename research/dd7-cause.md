# DD7: what the real ESO 137-006 data carry that the DD5/DD6 simulations lack

Issue #15. Follows [dd6-d0.md](dd6-d0.md) (DD6), [dd5-sim.md](dd5-sim.md)
(DD5) and [dd4d-eso137.md](dd4d-eso137.md). Branch `dd7-cause`. Coordinator
brief 2026-11-25. A diagnostic, not a fix: no claim of better calibration or
imaging follows from it. Sections 1-7 are frozen 2026-11-25, before the code
that runs them and before any measurement. Later changes are dated amendments.

Status: **proposed** (nothing measured).

## 1. Question

On the real subset, the off-axis `diag_complex` solves (d1-d3) are lifted
above 0.10 only with d0 free and the deeper d0 model (MF), and only at
64 × 8 s (DD6: 0.794, 0.754, 0.752). At 4 × 8 s MF reads 0.066, 0.042,
0.011, and d0 itself, free and holding about 60 Jy, converges in only 0.152
of its cells. With d0 pinned (M), nothing lifts at any interval. In the
simulations, with the same layout, the same flags, weights and UVW and a
d0 gain of exactly 1, an exact model converges at 4 × 8 s (B: 0.997, 0.993,
0.956; BF: 0.988, 0.974, 0.939, accurate), and E-MF and E-M lift at
4 × 8 s (0.96-0.99). Which property of the real data, absent from the
simulations, takes the real solves from there to 0?

## 2. Candidates, ranked from the archives (before any DD7 measurement)

**Already in every simulation by construction.** Each DD5 `sim.ms` is the
real subset with only `DATA` replaced, so the real `FLAG`, `FLAG_ROW`,
`WEIGHT_SPECTRUM` values (both hands, median ratio 1.06), `UVW`, row order
and the 2-integration last interval are all in B, which converges. These
are not candidates as such, and no solve arm is spent on them. What is
left of "weights" is whether the real noise follows k/w; that is a stage-1
statistic (S1b). The short last interval only caps the 64 × 8 s measure
(DD6 A2), not the 4 × 8 s failure.

**Ranked out without an arm.**
- *Time-variable primary beam or pointing.* The truth gains already vary
  per antenna and direction by ±10-20 % in amplitude and ±0.5-1 rad in
  phase over the hour, and B converges with them. A faster real variation
  would make longer intervals worse; the real solves get better with longer
  intervals.
- *Time and bandwidth smearing.* DD4 section 2: about 0.1 beam at 0.5° and
  0.418 MHz; d1 is at 0.25°.

**Ranked candidates (most likely first), with the reason:**

1. **Baseline-based misfit on short baselines.** gemclean-heldout §5 found,
   on this observation against a WSClean model, that baselines under 400 m
   hold 3.75 % of the weight and 63 % of the misfit, and that 145 of 1,830
   baselines (`badbaselines.json`, 3.35 % of the weight) hold 54 % of it,
   steady in time, antenna 1 most often. The DD subset keeps them (set A's
   flags). No antenna gain can absorb a non-closing error; d0 is brightest
   on short baselines; and a steady error decorrelates from the rotating
   off-axis fringes over longer intervals, which fits the lift at 64 × 8 s.
   No simulation has it.
2. **d0 gain error left by the DI chain (relative to our model).** Free d0
   on real data has a phase spread of 0.097 rad (MF-4) and 0.137 rad (F-4),
   against 0.001-0.02 rad in every simulation (d0 truth exactly 1); arm D's
   1 % / 0.02 rad was about 5 × smaller. On 60 Jy that is several Jy per
   baseline. It fits "M fails, MF lifts": pinned, the error goes into the
   weak directions. The publisher's DI gains are per 8 s, per channel and
   antenna (gemclean-heldout §5), so part of it can vary inside a solution
   cell or across the band, where a free full-band d0 cannot follow it.
3. **Spectral structure.** The model is one flat-spectrum image; the real
   d0 follows α ≈ −1 (gemclean-heldout §5), ±1.2 % over this 2.5 % band
   on 60 Jy. k's adjacent-channel estimator cancels smooth structure, so
   nothing in DD5 measured it.
4. **Off-axis model incompleteness.** The deep model holds 65.77 Jy, 5.25 Jy
   outside facet d0, against 3.48 Jy of M₀ᶜ there, which d1-d3 keep in M
   and MF. But a deep clean of sim B overshoots its sky by 5.2 Jy too, and
   DD5's E1 (2.18 Jy of d1 error) stayed "partly", so this ranks below 1-3.
5. **Noise: non-Gaussian, non-stationary, or not k/w per hand.** k matched
   the expected 31 µJy (DD5), but only as a robust (MAD) pooled number.

## 3. Data and setup

Run root `D:/rang/outputs/dd7-20261125/` (Windows, glacier). DD5's root is
read only; its directories `a/` and `b/` are copied into the run root
(`a/` as the layout template, `b/` as the simulation base) before use.

- **Real subset, rebuilt as DD6 section 2** (`dd6.real_ms` with the copied
  `a/` as template, check S1), and the deeper model: DD6's frozen GeMClean
  run (A1's command) on it, composed into facet d0 over M₀ᶜ (`RM`, DD6's
  M model). Also kept whole (`deep`, every facet).
- **Simulation base: B** (sky M₀ᶜ = `b/sky.npy`, truth gains `truth.npz`,
  k = 0.5291). Departure from the brief's "C or E", for a reason: B is the
  only simulated set with an exact model and headroom in both d0 settings
  (pinned 0.997, 0.993, 0.956; free 0.988, 0.974, 0.939, accurate). So a
  drop after an insertion is caused by the inserted property alone. C-P,
  C-F and E-P are already at the floor; E's model was not "better" by DD6's
  M0; C-M (0.25, 0.19, 0.17) has too little headroom.
- **B's signal:** `DATA_B − n`, with n regenerated exactly as `dd5.simulate`
  drew it (seed 5501, k, the copied weights).

**Setup gates (frozen; a miss is a setup outcome: stop and report):**
- G1: S1 passes (DD6's columns equal, `DATA` written equal).
- G2: `RM` holds 63.999 Jy (60.518 Jy in facet d0) to 1e-3 Jy, the deep
  model 65.771 Jy to 1e-3 Jy.
- G3: B's regenerated signal equals the unit-noise-free predict
  `Σ_f G_f V_f G_f^H` (b/sky.npy, truth gains) to 1e-3 Jy max absolute.
- G4, the real reproduction, `diag_complex`, cap 500 (DD5's grid solve):
  real P-4 (d0 pinned, M₀ᶜ) 0, 0, 0 and 1,876 ± 1 % flagged off-axis gains;
  real MF-4 (d0 free, RM) and MF-64 within 0.01 of DD6 in d0-d3
  (MF-4: 0.152, 0.066, 0.042, 0.011; MF-64: 0.875, 0.794, 0.754, 0.752).

## 4. Measures

- **Per-direction converged fraction** (DD4c section 3, DD4d A1), levels
  as DD5 A1: ≥ 0.99 converges, > 0.10 partly, ≤ 0.10 does not. **Lifted**:
  every one of d1-d3 above 0.10.
- **Continuous companion (frozen, because real P, F and M read exactly 0
  and every point runs to the cap):** per direction, the median of
  `|Δg|²/|g|²` between the two solves (`step_stats`, already in every
  record). Converged cells sit below 1e-14 (the stop criterion squared).
- d0's own fraction, flagged gains, `e/ê` (simulation), d0's phase spread:
  reported.

## 5. Stage 1: statistics (no solve beyond G4)

All on the real residual after the best real solve,
`R64 = DATA − Σ_f G_f V_f G_f^H` with G4's MF-64 gains and `RM` (flagged
gain cells taken as 1), only unflagged cells, both hands, `z = R √(w/k)`
(unit variance per part for pure k/w noise; sims: R = n by construction):

- **S1a reduced χ²** `⟨|z|²⟩/2` by baseline length (0-100, 100-200,
  200-400, 400-1000, 1000-2000, 2000-4000, > 4000 m), by antenna, per
  4-integration interval and per channel; the share of the excess
  `Σ(|z|²/2 − 1)` on the 145 bad baselines and on baselines under 400 m.
- **S1b noise against k/w:** k from adjacent-channel differences (DD5's
  estimator) per hand, per weight decile and per baseline-length bin; the
  fraction of normalised differences with |·| > 5σ against the Gaussian
  5.7e-7.
- **S1c spectral structure:** per (row, hand), the least-squares linear
  term of z across the unflagged channels; its power as a share of
  `Σ|z|²`, against 2/64 for pure noise.
- **S1d model flux:** the deep model, RM and M₀ᶜ per facet.
- **S1e:** Spearman correlation, over the 113 intervals of G4's MF-4, of
  each interval's mean off-axis converged fraction with its χ² (S1a) and
  its flagged fraction.
- **S1f d0's gain error:** from G4's MF-4 d0 gains, the phase spread and
  amplitude spread per antenna, and the step to the next interval.

**Ranking rule (frozen):** stage 1 re-ranks the five candidates of
section 2 by the share of the χ² excess each can hold: candidate 1 by the
bad-baseline share; 3 by S1c's linear share minus 2/64; 5 by
`|k_XX/k_YY − 1|`, the spread of k over weight deciles and the tail
excess; 2 and 4 keep their section-2 rank unless S1f's spread is below
0.02 rad (then 2 drops to last). The ranking is recorded as an amendment
before any stage-2 arm is read. It sets the order of stage 2 only; every
stage-2 arm runs (up to the cap, section 7).

## 6. Stage 2: arms

All `diag_complex`, cap 500, stop criterion 1e-7, stop fraction 0.99,
`refant=None`, full 64-channel band, 4 × 8 s unless stated; DD5's grid
solve with its one-longer second solve.

**Transplant and bisection (on B; d0 free unless stated; model `b/sky.npy`,
exact).** `DATA = signal_B + X` on unflagged cells, X as below:

| Arm | X | Tests |
| --- | --- | --- |
| **T0**, d0 free and d0 pinned | R64 (the real residual, noise included) | is the cause in the real additive residual at all |
| **T1** | R64 on the 145 bad baselines, B's own noise n elsewhere | candidate 1 |
| **T4** | n on the 145 bad baselines, R64 elsewhere | the complement of T1 |
| **T2** | R64 on baselines under 400 m, n elsewhere | short baselines (1, 3) |
| **T3** | R64 with each cell's phase replaced by a uniform random phase (seed 7701) | coherence against amplitude (5 against 1-4) |
| **TS** | R64 with S1c's per-(row, hand) linear term removed, then that term alone added to n (two points) | spectral structure (3) |

**Insertion of d0's gain error (on B).** **I0**: B's d0 truth gain set to
G4's real MF-4 d0 gains (per 4 × 8 s, frequency-flat, per antenna and hand;
flagged cells 1): `DATA = DATA_B + (G0 V0 G0^H − V0)`, V0 B's d0-facet
predict, model `b/sky.npy`; d0 pinned (the real M analogue) and free (MF).
Free can absorb it exactly at this cell size, so I0-free is the control of
I0-pinned.

**Removal from the real data (d0 free, RM, as real MF-4):**
- **R1:** the 145 bad baselines flagged. **R1c:** the same number of other
  baselines, drawn (seed 7702) to match R1's weight share within ±10 %,
  flagged instead.
- **R2:** the deep model in every facet (removes off-axis incompleteness, 4).
- **R3:** a DI pre-solve: one direction (the whole deep model), per
  integration and per 8 channels, `refant=None`, cap 500; `DATA` divided by
  `g_p g_q*` and the weights multiplied by `|g_p g_q|²`; then MF-4 with RM
  (removes 2's within-cell and in-band parts).
- **R1-64, R3-64:** R1 and R3 at 64 × 8 s, read only if R1 or R3 is not
  lifted at 4 × 8 s.
- **L2000:** real MF-4 at cap 2000, to separate slow convergence from a
  stall (DD5 A1's N0 diagnostic).

## 7. Decision rule (frozen)

**Per arm:**
- A transplant or insertion arm **reproduces** if some d1-d3 falls to
  ≤ 0.10 where its base (B pinned or BF) is above 0.10, and **weakens** if
  it stays lifted but some d1-d3 drops by ≥ 0.20 or its step median rises
  by ≥ 100×.
- A removal arm **restores** if real MF-4 becomes lifted, and **helps** if
  the minimum of d1-d3 rises by ≥ 0.05 or the d3 step median falls by
  ≥ 10× against G4's MF-4, and R1 does so where R1c does not.

**Outcome per candidate:**

| Insertion (T/I arm) | Removal (R arm) | Reading |
| --- | --- | --- |
| reproduces | restores or helps | **identified**: a cause of the real failure |
| reproduces | neither, or no removal arm | **sufficient in simulation** |
| neither | restores or helps | **necessary on real data, not sufficient alone** |
| neither | neither | **not the cause** |

Candidate to arms: 1 ↔ T1 / R1 (with R1c); 2 ↔ I0-pinned (and T0 pinned
against T0 free) / R3; 3 ↔ TS / R3; 4 ↔ none / R2; 5 ↔ T3 / none.
- **T0 governs the rest:** if T0 free does not reproduce, the cause is
  **not in the additive residual**, and only candidate 2 (I0, R3) or a
  multiplicative property can carry it; the bisection arms are still run
  and reported.
- If T1 and T4 both reproduce, the residual holds more than one sufficient
  cause; if neither does while T0 does, the cause needs the whole residual
  (an interaction), and that is the reading.
- A null overall (no candidate identified or sufficient) is reported as
  **not found among the ranked candidates**, with T0's reading.
- Not claimed: anything about image quality, accuracy of the real gains,
  or speed. No oracle parity is run: DD7 diagnoses rang's own solve, which
  DD6 matched to QuartiCal 0.2.7 in flags, fraction and iterations.

## 8. Implementation, host and cost

- `tools/oracles/dd7/dd7.py`: `setup` (copies, realms, compose), `stats`
  (stage 1), `build` (one transplant, insertion or removal run directory:
  a copy of `sub.ms` or B's `sim.ms` with `DATA`, `FLAG` or weights
  replaced), and `grid` through `dd5.grid_point`. Unit tests on synthetic
  data in `tests/test_dd7.py` for the filters, the phase scramble, the
  linear-term split and the matched-control draw.
- glacier, shared, under the main checkout's `tools/heavy_lock.py`. A 4 × 8 s
  point books 4 slots and 15 GB, GeMClean 8 slots and 16 GB, a build 2
  slots and 10 GB, `stats` 4 slots and 15 GB. No exclusive or timing runs.
- **Cap:** 21 solve points: G4 3, T 8, I0 2, R 4, conditional R-64 2,
  L2000 1, one spare for a rerun; past it the remaining arms are not run and
  are reported as such.
- Expected 900-1,500 s per 4 × 8 s point (DD6), L2000 about 4×. Wall times
  go into [tool-timings.md](tool-timings.md). Built MS copies (about 2 GB
  each) are deleted at the end; the archive keeps the records.
