# DD7: what the real ESO 137-006 data carry that the DD5/DD6 simulations lack

Issue #15. Follows [dd6-d0.md](dd6-d0.md) (DD6), [dd5-sim.md](dd5-sim.md)
(DD5) and [dd4d-eso137.md](dd4d-eso137.md). Branch `dd7-cause`. Coordinator
brief 2026-11-25. A diagnostic, not a fix: no claim of better calibration or
imaging follows from it. Sections 1-7 are frozen 2026-11-25, before the code
that runs them and before any measurement. Later changes are dated amendments.

Status: **measured 2026-11-25. The real 4 × 8 s failure is slow convergence, not a stall: unchanged real MF-4 is lifted at cap 2000 (0.530, 0.501, 0.465; L2000). At the frozen cap 500, by the frozen table: the off-axis model incompleteness is necessary on real data (R2), the 145 bad baselines are necessary but not sufficient alone (R1, T1), d0's gain error is sufficient in simulation for the pinned failure only (I0), spectral structure and noise are not the cause; the cause is not in the additive residual (T0).** With the deep clean as the model of every facet (R2), the real d0-free solve is lifted at 4 × 8 s for the first time (0.304, 0.297, 0.297; DD6 0.066, 0.042, 0.011), but at 64 × 8 s the same model does worse than DD6's (0.25 against 0.75-0.79, reported only), so it is not a better model, only a different one. Flagging the 145 bad baselines helps (0.123, 0.104, 0.072; a weight-matched control does not) and at 64 × 8 s converges every interval but the short last one. The real d0 gain error (0.094 rad, static per antenna) inserted into simulation B breaks the pinned solve (0, 0, 0) and is absorbed exactly when d0 is free. No off-axis insertion arm was frozen; DD6's arm C, which lacks off-axis emission, comes closest to the real pattern (post hoc).

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

## 9. Measured result

Run root `D:/rang/outputs/dd7-20261125/` (`real/`, `b/`, one directory per
built arm, `grid/`, `times.log`); archive [results/dd7-cause/](results/dd7-cause/).
Host glacier, shared; the main checkout's extension, DD7 changes no Rust.
All points `diag_complex`, cap 500, every one ran to the cap. Fractions are
d1, d2, d3 (d0 in brackets); step = per-direction median `|Δg|²/|g|²`
(d3 shown); `e/ê` for d1-d3 on B-based arms.

**Setup and stage 1:** A2 (G1-G4 pass, the real points equal DD6 to every
digit; the ranking).

**Stage 2, simulation B with an inserted real property (bases: B pinned
0.997, 0.993, 0.956; BF 0.988, 0.974, 0.939, e/ê 1.0-1.1):**

| Arm | d0 | d1, d2, d3 (d0) | e/ê d1-d3 | Reading |
| --- | --- | --- | --- | --- |
| T0, R64 added | free | 0.800, 0.775, 0.761 (0.797) | 12, 11, 12 | neither (drops 0.19, 0.20, 0.18, below 0.20) |
| T0 | pinned | 0.930, 0.915, 0.884 | 12, 11, 12 | neither |
| T1, R64 on the 145 bad baselines | free | 0.992, 0.978, 0.948 | 4.5, 3.3, 3.0 | neither |
| T4, R64 on the other baselines | free | 0.926, 0.907, 0.903 | 12, 9.7, 9.3 | neither |
| T2, R64 under 400 m | free | 0.981, 0.967, 0.948 | 4.9, 2.9, 2.7 | neither |
| T3, R64 phase-scrambled | free | 0.984, 0.963, 0.939 | 1.8, 1.4, 1.4 | neither |
| TSa, R64 without its in-band linear term | free | 0.907, 0.886, 0.876 | 9.9, 9.1, 9.0 | neither |
| TSb, the linear term alone | free | 0.994, 0.983, 0.965 | 5.1, 3.8, 3.4 | neither |
| **I0, real MF-4 d0 gains as d0's truth** | **pinned** | **0.0006, 0, 0** | 17, 28, 20 | **reproduces** |
| I0 | free | 0.992, 0.977, 0.974 (0.999) | 1.08, 1.01, 1.03 | neither; accurate |

**Stage 2, candidates removed from the real data (real MF-4: 0.066, 0.042,
0.011, d3 step 1.2e-7):**

| Arm | d1, d2, d3 (d0) | d3 step | Reading |
| --- | --- | --- | --- |
| R1, the 145 bad baselines flagged | 0.123, 0.104, 0.072 (0.218) | 5.6e-8 | **helps** (min +0.061) |
| R1c, 145 weight-matched other baselines flagged (A3) | 0.028, 0.018, 0.0003 (0.074) | 2.5e-7 | worse: R1's help is specific |
| **R2, the deep model in every facet** | **0.304, 0.297, 0.297 (0.368)** | **1.6e-9** | **restores** (lifted at 4 × 8 s) |
| R3, DI pre-solve (per 8 s and 8 channels) then MF-4 | 0.043, 0.021, 0.009 (0.120) | 2.8e-7 | neither |
| R1-64 (conditional) | 0.875, 0.875, 0.875 (0.881) | 6e-33 | every interval but the 2-integration last one (MF-64: 0.794, 0.754, 0.752) |
| R3-64 (conditional) | 0.810, 0.752, 0.755 (0.873) | 5e-30 | as MF-64: no help |
| R2-64 (reported only, A4) | **0.254, 0.255, 0.256** (0.307) | 3.9e-11 | **worse than MF-64**: only intervals 0 and 1 converge |
| **L2000, real MF-4 at cap 2000** | **0.530, 0.501, 0.465 (0.705)** | **2.6e-13** | **lifted: slow convergence, not a stall** (step medians 4-6 orders below cap 500's; still at the cap) |

- R2's off-axis gains sit near 1 (median |g| 1.000, 1.001, 0.973; phase
  spread 0.13, 0.24, 0.40 rad) against MF-4's (0.978, 0.977, 0.811; 0.36,
  0.50, 1.19 rad). Its lift is all or nothing per interval like DD6's: 33 of
  113 intervals converge in all of d1-d3 (MF-4: 1), 76 not at all.
- The DI pre-solve (R3) converged (154 iterations, 0.990) with amplitudes
  0.986-1.023 (p10-p90) and cut d0's phase spread in the following MF-4
  from 0.097 to 0.021 rad, without lifting d1-d3.

**Outcome per candidate (section 7's table):**

| Candidate | Insertion | Removal | Reading |
| --- | --- | --- | --- |
| 4. off-axis model incompleteness | no arm | R2 restores at 4 × 8 s | **necessary on real data** by the frozen table; sufficiency not tested (no insertion arm); not monotone in interval (R2-64, below) |
| 1. baseline-based misfit (145 baselines) | T1 neither | R1 helps, R1c not | **necessary on real data, not sufficient alone** |
| 2. d0 gain error from the DI chain | I0-pinned reproduces | R3 neither | **sufficient in simulation**: it alone explains why real M (d0 pinned) fails; free, d0 absorbs it exactly (I0-free accurate) |
| 3. spectral structure | TSb neither | R3 neither | **not the cause** |
| 5. noise | T3 neither | none | **not the cause** |

- **T0 governs the rest:** the real additive residual added to an exact
  simulation does not reproduce the real failure (d0 free 0.76-0.80; T0
  pinned 0.88-0.93). So the cause is **not in the additive residual**. That
  fits candidate 4: R64 is the residual after the real MF-64 gains, and a
  wrong off-axis model is absorbed into those gains, not left in R64.
- **L2000 reframes every reading above.** Real MF-4, unchanged, is lifted
  at cap 2000 (0.530, 0.501, 0.465) and still moving. So the real failure at
  4 × 8 s is slow convergence that cap 500 cuts off, not a stall. B converges
  inside 500 iterations; the real data converge several times slower. The
  frozen readings are at cap 500, so "restores" (R2) and "helps" (R1) mean
  "speeds up the solve enough to show inside the cap", and "reproduces"
  (I0-pinned) means "slows it below the cap". Which property slows the real
  solve is what the arms rank.
- **What this says about DD7's question (interpretation, not a frozen
  reading):** the property the exact simulation B lacks, and the one whose
  removal changes the real solve most, is a wrong off-axis model. On real
  data the off-axis facets carry M₀ᶜ's off-axis part, against which the deep
  clean finds 4.43 Jy in d1 (M₀ᶜ 2.83), 0.77 Jy in d2 (0.45) and 0.05 Jy in
  d3 (0.20). B has an exact model and E's error sits mostly in d0. DD6's C
  does lack off-axis emission (7.2 Jy in d1, 0.25 Jy in d2), and post hoc it
  is the arm nearest the real pattern: C-X (d0 exact, pinned) 0.166, 0.107,
  0.094, and C-MF 0.20, 0.12, 0.10 / 0.15, 0.06, 0.04 / 0.75, 0.75, 0.75
  at 4, 16 and 64 × 8 s against real MF's 0.07, 0.04, 0.01 / 0.12, 0.09,
  0.04 / 0.79, 0.75, 0.75 (`results/dd6-d0/grid/`). That is the nearest
  thing to an insertion arm for candidate 4, and it was not frozen here.
- The bad-baseline reading rests on R1 at 4 × 8 s (min +0.061 against the
  0.05 bar, with R1c worse) and on R1-64; R1-64 differs from MF-64 in one
  interval (interval 1) and has no control at 64 × 8 s.
- **The caveat (R2-64, reported only):** at 64 × 8 s the deep model in
  every facet does worse than RM (0.25 against 0.75-0.79): intervals 0
  and 1 converge, the other six do not. So the deep off-axis model is not
  simply a better model. It changes which solves settle, and at 512 s it
  settles fewer. The off-axis model is where the real data differ from the
  simulations, but "a deeper unit-gain clean of the off-axis facets" is not
  the fix.
- Not shown: that the deep off-axis model is right (it was made from the
  same data with unit gains, so part of the DD effects is in it), that any
  lifted real gains are accurate, or anything about images.

**Cost (glacier, shared; walls include lock waits).** A 4 × 8 s point:
predict 43-57 s, each solve 338-433 s, walls 755-1,612 s; a 64 × 8 s point
the same per solve; builds 4-135 s of work (walls up to 3,325 s in the
queue); setup 15 s of work; deep clean 285 s; R64 378 s; stage 1 42 s.
Rows in [tool-timings.md](tool-timings.md).

## 10. For the coordinator

- The real d0-free solve at 4 × 8 s is not stuck; it is slow (L2000:
  lifted at cap 2000). DD4-DD6's "does not converge" readings at cap 500
  should be read as "has not converged in 500 iterations".
- Recommended DD8, frozen before code: (1) an off-axis insertion into B at
  the real size (sky B plus DEEP − M₀ᶜ in d1-d3, model M₀ᶜ there), which
  is the missing insertion arm for candidate 4; (2) an accuracy measure on
  real data in place of the step test (for example held-out-baseline
  prediction error), since convergence does not certify accuracy (DD6
  C-MF-64); (3) R1 and R2 combined, and real MF at cap 2000 at 16 and
  64 × 8 s, to see how much of the gap is iterations.
- Do not adopt the unit-gain deep clean as the off-axis model: it lifts
  4 × 8 s and hurts 64 × 8 s (R2-64).
- Run root kept: `D:/rang/outputs/dd7-20261125/` with `real/sub.ms`, `b/`,
  `models/`, `grid/` (gains `.npz`) and logs; the eleven built arm copies
  and `R64.npy` deleted.

## Amendments

**A1, 2026-11-25, setup (code written, nothing run or read).**
- S1c's expectation for pure noise is wrong as frozen: the linear term
  alone carries one complex degree of freedom per (row, hand), so its share
  of `Σ|z|²` is `(rows × hands) / Σ n_unflagged`, about 1/64, not 2/64. The
  code computes that exact expectation; the ranking rule uses it in place of
  2/64. The constant term's share is reported beside it.
- The stage-1 inputs need G4's MF-4 and MF-64 points, so the order is: G1-G3,
  G4, `resid`, stage 1, the ranking amendment, then stage 2.

**A2, 2026-11-25, the stage-1 ranking (section 5's frozen rule; after
G1-G4 and stage 1, before any stage-2 arm was read).** G1-G4 pass: S1
exact; RM 63.999 Jy, deep 65.771 Jy, as DD6; B's signal equals its predict
to 2.7e-6 Jy; real P-4, MF-4 and MF-64 equal DD6 to every digit
(`results/dd7-cause/setup/`). Stage 1 (`results/dd7-cause/stage1/stats.json`)
on R64:
- χ² 1.95: after the best real solve, the residual holds as much power
  beyond k/w as the noise itself.
- Candidate 1: the 145 bad baselines (4.1 % of the weight here) hold
  12.4 % of the excess (χ² 3.87 against 1.87 elsewhere); baselines under
  400 m 8.2 %. 84 % of the excess is on 400-4000 m baselines.
- Candidate 3: the linear term across the band holds 0.116 of `Σ|z|²`
  against 0.017 for noise, so 0.099, about 20 % of the excess; it peaks at
  1-2 km (0.145). The constant term (frequency-flat, per row) holds 0.311
  against 0.017, about 60 % of the excess; no candidate claims it by the
  rule.
- Candidate 5: k per hand 0.521 and 0.524 (ratio 0.995), flat to 0.3 %
  over weight deciles and length bins; tails beyond 5σ 1.9e-5 (Gaussian
  5.7e-7), too few to matter in power.
- Candidate 2: d0's phase spread in MF-4 is 0.097 rad, of which the static
  per-antenna part is 0.094 rad and the time-variable part 0.022 rad
  (median), with a 0.005 rad median step between 32 s intervals; above
  0.02 rad, so it keeps its rank. Amplitude 0.976-1.029 (p10-p90).
- Candidate 4: the deep model has 4.43, 0.77 and 0.05 Jy in d1-d3 against
  RM's 2.83, 0.45 and 0.20 Jy.
- S1e: the per-interval off-axis fraction correlates weakly with χ²
  (Spearman −0.28) and flags (−0.13).

**Ranking:** 1. spectral structure (3, 20 % of the excess); 2. d0's gain
error (2, rank kept); 3. baseline-based misfit (1, 12 %); 4. off-axis
incompleteness (4, rank kept); 5. noise (5). Stage 2 runs in this order
(TS, then I0 and R3, then T1/T4 and R1/R1c, then R2, then T3), with T0
first in each lane as the umbrella.

**A3, 2026-11-25, setup fix (after R1 and I0-pin were read, before R1c
was built).** R1c's random draw cannot meet ±10 % of R1's weight share in
20,000 draws: the 145 bad baselines are 7.9 % of the baselines but 4.1 %
of the unflagged weight (short, heavily flagged), so random sets of 145
hold about 7.9 %. The control is now built by pairing each bad baseline,
in random order (seed 7702), with the unused other baseline of nearest
unflagged weight; the ±10 % check stands. R1, R1c, I0-pin and the setup
lane ran alongside stage 1; none was read before A2.

**A4, 2026-11-25, post hoc (after R2 was read).** R2 at 64 × 8 s (R2-64)
runs on section 8's spare point, reported only; it changes no reading. It
shows how far the restored solve goes at DD6's lifted interval.
