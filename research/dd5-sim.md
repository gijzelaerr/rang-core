# DD5: why the off-axis DD solves on ESO 137-006 do not converge, by simulation

Issue #15. Follows [dd4d-eso137.md](dd4d-eso137.md) (DD4d),
[dd4c-eso137.md](dd4c-eso137.md), [dd4b-eso137.md](dd4b-eso137.md) and
[dd4-eso137.md](dd4-eso137.md). Branch `dd5-sim`. Owner decision
2026-11-24, relayed by the coordinator. Sections 1-7 are frozen 2026-11-24,
before the code that runs them. Later changes are dated amendments.

Status: **proposed, frozen 2026-11-24.**

## 1. Question and hypotheses

On the real ESO137 pilot subset, no off-axis DD solve converges at any
interval from 4 × 8 s to the whole 1 h scan (DD4d), in `phase` and
`diag_complex`, cap 500, d0 pinned, catalogue-pinned facet fluxes, start
model M₀ᶜ (DI0's cycle-4 clean model). The simulations DD1-DD3c, on a
simpler 4-point-source sky with equal weights and no flags, converged and
reached parity with QuartiCal + WSClean.

DD5 rebuilds the real setup in simulation, factor by factor, with known
gains. The suspects, each with the arm that tests it (section 3):

| Suspect | Test |
| --- | --- |
| The uv coverage, flags, weights and the catalogue sky alone (weak d2, d3 against an 80 Jy d0) | arm A |
| Overlapping facet models with ESO 137-006's extended emission, even when the model is exact | arm B |
| The extended emission in the sky but not in the model | arm C |
| Catalogue pins that disagree with the data (d2, d3 too bright in the model) | arm P |
| A residual gain error on the pinned d0 (conditional, section 6) | arm D |

Not claimed: anything about the real sky beyond the factors simulated. A
factor that breaks convergence here is a sufficient cause in simulation, not
proof that it is the cause on the real data.

## 2. Data and simulated skies

**Layout:** the real subset `D:/rang/outputs/dd4-20261123/sub.ms` (DD4 A1):
61 antennas, 823,500 rows, 450 × 8 s, channels 96-159 (64 × 0.418 MHz),
XX and YY, its real `FLAG`, `FLAG_ROW`, `WEIGHT_SPECTRUM` and `UVW`. Each
simulated MS is a copy of it with only `DATA` replaced. Rows, channels,
flags and weights are unchanged.

**Directions, facets, grid, pins:** DD4's (`run-02/setup.json`): d0 at the
phase centre, d1-d3 at the three catalogue components, Voronoi facets,
2880 × 2880 pixels of 3″, pins at d1-d3's components.

**Skies** (pixel models on DD4's grid):
- **S_a:** DD4's catalogue model M₀, `run-02/model0.npy` (152 RACS-low
  components of at least 5 mJy, 92.6 Jy apparent).
- **S_b:** M₀ᶜ, `run-02/DI0/cycle-4/model.npy`, SHA-256
  `619891d3…4914a`: the catalogue plus DI0's clean components, ESO
  137-006's extended emission among them.
- **S_p:** S_b with the flux in d2's and d3's pin pixels multiplied by 0.5.
  DD4d's `diag_complex` put d2's and d3's median gain amplitude at 0.64-0.79
  on real data. An amplitude of about 0.7 is a flux ratio of about 0.5, so
  in S_p the model (which keeps the catalogue values) is 2 × too bright at
  d2 and d3. d1 is unchanged.

**Visibilities:** `DATA = Σ_f G_p,f V_f G_q,f^H + n`, per hand, where V_f is
the facet-f part of the sky predicted with exactly the predict the solver's
model uses (`dd4.facet_models`: ducc `dirty2vis`, ε 1e-7, per facet). So
"model = truth" is exact up to the predict's ε.

**Truth gains** (diagonal, per antenna, direction and hand):
- d0: exactly 1, as the pin, and as the DI-corrected real data assume.
- d1-d3: DD1's form (`tools/oracles/dd1/sim.py` `truth_gains`):
  `exp(0.1 a + 0.5 i b)`, with a and b each an offset N(0, 1) plus a
  sinusoid (amplitude U(0.2, 1), period U(0.5, 2) scans, random phase) per
  (antenna, direction, hand). Seed 1502 (DD1's), drawn for 4 directions and
  then d0 set to 1. Piecewise constant on blocks of 4 integrations (113
  blocks; the last block has 2). So amplitudes vary by about ±10-20 % and
  phases by about ±0.5-1 rad between antennas, and drift over the hour.
- The same gains are used for every sky.

**Noise:** complex Gaussian, N(0, k / w) in each real and imaginary part,
with w the real `WEIGHT_SPECTRUM` of the cell and hand. One realisation,
seed 5501, for every sky.
- The scale k is measured once on the real data, not assumed. R is the real
  `DATA` minus the unit-gain predict of M₀ᶜ. For adjacent channels c and
  c + 1, both unflagged, `d = R_c − R_{c+1}` has variance
  `k (1/w_c + 1/w_{c+1})` per part. So
  `k = (1.4826 MAD of Re d and Im d, each scaled by (1/w_c + 1/w_{c+1})^(-1/2))²`,
  pooled over both hands and all cells.
- k is recorded in the archive as setup, with the thermal image noise it
  implies.

## 3. Arms

| Arm | Sky (truth) | Model the solve uses | Factor isolated |
| --- | --- | --- | --- |
| **A** | S_a | S_a (= truth) | control: real layout, catalogue sky |
| **B** | S_b | S_b (= truth) | extended emission in sky and model (facet overlap) |
| **C** | S_b | S_a (catalogue only) | extended emission in sky, not in model (DD4's M₀ on real data) |
| **P** | S_p | S_b | pins 2 × too bright at d2, d3; otherwise exact |
| **D** (conditional) | S_b, d0 gains not 1 | S_b, d0 pinned at 1 | residual error on the pinned d0 |

For arm D, d0's truth gain is `exp(0.01 a + 0.02 i b)` (DD1's form, seed
5504): about 1 % in amplitude and 0.02 rad in phase. On 80 Jy, 1 % is
0.8 Jy, comparable to d1 and 8 × d2.

**Solve (each arm, each grid point): DD4d's.**
- `solve_dd`, d0 pinned, cap 500, stop criterion 1e-7, stop fraction 0.99,
  `refant=None`, full 64-channel band.
- Kinds: `phase` (each direction's own gain) and `diag_complex`.
- Intervals 4, 16, 64 and 450 integrations (32 s, 128 s, 512 s, whole
  scan).
- A second solve with one more iteration and stop fraction 1 gives each
  direction's converged fraction (DD4c section 3 with DD4d A1).
- The same truth gains are used for `phase`. Their amplitudes are not 1,
  so the `phase` model is incomplete by design, as on real data.

**Sanity gate N0 (first run):** arm A without noise, `diag_complex`,
4 × 8 s.

## 4. Measures

**Convergence per direction:** DD4c section 3's measure, unflagged cells
only. A direction converges if its fraction is ≥ 0.99. An (arm, kind)
converges at interval T if d1, d2 and d3 all converge. T* is the shortest
such interval.

**Gain error against truth, per direction d:**
- `e_d` = median over unflagged solution cells and antenna pairs p < q and
  hands of `|P − P̄| / |P̄|`. P = g_p g_q* is the solved product. P̄ is the
  truth product averaged (unweighted) over the truth blocks inside the
  solution interval, so at 4 × 8 s it is exact.
- For `phase`, both are first normalised to unit modulus (phase error
  only).
- **Noise prediction** `ê_d`: per solution cell, antenna p, direction d and
  hand, `I = Σ (w / 2k) |V_d|²` over the unflagged visibilities of
  baselines with p in the interval (|g| ≈ 1), so `Var g_p ≈ 1/I`.
  `ê_d = 0.83 × median over pairs of sqrt(Var g_p + Var g_q)` (the median
  of a complex Gaussian's modulus). It ignores covariance between
  directions, which is where an overlap degeneracy would show.
- **Accurate:** `e_d ≤ 2 ê_d`. Otherwise **biased**. This is read per
  direction, and only where the direction converges.

Reported, not gated: flagged gain counts, median |g| and phase spread per
direction, `e_d / ê_d` at every grid point.

## 5. Decision rule (frozen)

**N0 gate:** d1-d3 converge, and `e_d ≤ 1e-3` in each. If N0 fails, the
outcome is **setup: the solver does not recover noise-free truth on this
layout**. Stop and report; no noisy arm is read.

**Factor attribution**, read separately for `diag_complex` (primary, the
oracle's kind) and `phase`. An arm *converges* if it converges at some
grid interval.

| Arms that converge | Outcome |
| --- | --- |
| not A | **layout or SNR:** the real uv coverage, flags, weights and catalogue sky alone break convergence, with an exact model |
| A, not B | **facet overlap:** the extended emission breaks convergence even with an exact model |
| A, B, not C, P converges | **missing extended emission in the model** |
| A, B, C, not P | **pin mismatch** |
| A, B, not C, not P | **both: missing emission and pin mismatch** |
| A, B, C, P | **not reproduced** by these factors; then arm D (section 6) |

With arm D:
- D does not converge: **residual error on the pinned d0**;
- D converges: **not reproduced**. The real failure then comes from how the
  real sky or data differ from M₀ᶜ and from these gains (unmodelled
  structure, beam, smearing, non-diagonal or faster gains), which DD5 does
  not simulate.

A converging arm with `e_d > 2 ê_d` in some direction is recorded as
**converges, biased** in that direction. That is the expected reading for
C and P, since their models are wrong. It does not change the factor
outcome.

## 6. Stages and stop rules

1. **Setup:** measure k; build S_a, S_b and S_p's MS copies and
   `truth.npz`; run N0. Stop if N0 fails.
2. **Arms A, B, C, P at 4 × 8 s**, both kinds.
3. **Longer intervals:** for each (arm, kind) that does not converge at
   4 × 8 s, the intervals 16, 64 and 450, in that order. Stop at the first
   that converges.
4. **Arm D:** only if the `diag_complex` outcome is "not reproduced". The
   same 4 × 8 s first, then stage 3's order.
5. **Oracle parity**, in one configuration chosen by this rule:
   `diag_complex` at its T*, in the first of C, B, A that converges (the
   most realistic first). QuartiCal#459 breaks QuartiCal's DD `phase`, so
   there is no `phase` parity. If none of C, B, A converges in
   `diag_complex`, the outcome is **no converging configuration** and parity
   is not run.

**Parity (stage 5):** DD4's loop in both codes on that arm's simulated MS.
- **Rang:** `dd4.py rang` with `diag_complex`, cap 500, interval T*,
  d0 pinned, the per-direction measure each cycle.
- **Oracle:** QuartiCal 0.2.7 `G.type=diag_complex`, `G.time_interval=T*`,
  `G.freq_interval=0`, `iter_recipe=[500]`, `G.pinned_directions=[0]`, on
  the two-correlation MS; WSClean 3.7 on DD4 A5's matched four-correlation
  copy (`dd4.py oracle`, unchanged).
- Five major cycles plus the final solve; DD4's minor cycle with the d1-d3
  pins.
- **Start model:** the arm's model. For C that is M₀, as DD4. For B and A,
  it is the truth, so the residual is noise and Högbom may add few or no
  components. Gate L then reduces to the gain products, flags and
  residual. This is stated as such.
- **Gates:** L and S as DD4 section 5, with the up-to-rule relaxation of
  S (`dd4.score`).
- **Outcome:** **parity** (L and S hold), **parity up to the rule**, or
  **parity failure** (first differing cycle and quantity). If an off-axis
  direction falls below 0.99 in a later cycle of either code, that is
  recorded beside the reading.
- Reported: each cycle's `e_d` against truth in both arms.

## 7. Host use and cost

- glacier, 16 slots and 48 GB. A grid solve holds about 11-12 GB (DD4d), so
  at most three at once. Grid points with several intervals book 8 slots.
  A whole-scan solve is single-threaded and books 2.
- nash only for single-threaded whole-scan solves, and only after this
  branch's commit is built there; the simulated MS is copied, not
  regenerated.
- The oracle arm books 2 slots (QuartiCal single-threaded, WSClean `-j 2`,
  as DD4d).
- WSL scratch on ext4, deleted at the end. Wall time per step into
  [tool-timings.md](tool-timings.md).
- Expected: a converging solve stops well below the cap; a non-converging
  one costs DD4d's 520-7100 s per point.

## 8. Measured result

Not yet run.

## Amendments

None.
