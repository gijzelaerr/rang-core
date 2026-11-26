# DD9: why an exact deep off-axis sky slows the DD solve, and a constraint on the weak facet d3

Issue #15. Follows [dd8-offaxis.md](dd8-offaxis.md) (DD8) and
[dd7-cause.md](dd7-cause.md) (DD7). Branch `dd9-solver`. Coordinator brief
2026-11-26. A diagnostic with one constraint test in simulation; no claim of
better calibration or imaging on real data follows from it. Sections 1-9 are
frozen 2026-11-26, before the code that runs them and before any
measurement. Later changes are dated amendments, committed before the
reading they affect.

Status: **measured 2026-11-26.**
- **(a)** By the frozen readings, the linear rate explains the slowness
  (Ra1) and the shares are "both" (Ra2).
  - Gauss-Seidel over directions (I2) and the joint direction block (I3)
    close O-X's gap at cap 500 (min d1-d3 0.974 and 0.991, against 0.449)
    and stay accurate.
  - Neither is admissible: the frozen same-fixed-point check fails because
    the default's own answer is constrained by flags.
  - Post hoc (A2): the default DD update is linearly unstable at the
    solution in 56 of 113 O-X intervals (ρ up to 1.17) while every
    direction's own block is stable. That is facet coupling. Where the default
    converges there at all, it does so only after its flag ladder flags
    the unstable gains.
- **(b)** No d3 constraint qualifies.
  - Pinning or merging d3 tames it but raises d2's truth error from 0.54
    to 0.74.
  - The amplitude prior and the 16 × 8 s interval do not tame it.
  - d1's error (e/ê about 72), the model gap, is untouched.
- **(c)** The robust held-out score tracks truth on O-H by the frozen
  rule, at the extremes only. Post hoc, it rewards absorption.
- **Real data:** merging d3 lifts the real RM solve at 4 × 8 s (min 0.83).
  Gauss-Seidel does not help with the wrong model, on O or on real data.

## 1. Questions

DD8 built O (simulation B plus DEEP − M₀ᶜ in facets d1-d3, B's truth gains
and noise) and found:
- With the exact sky as model (O-X, d0 free, 4 × 8 s, cap 500) the solve
  converges at about half B's rate (0.540, 0.464, 0.449 in d1-d3, d0 0.639,
  against B-F's 0.988, 0.974, 0.939, d0 0.997) and stays accurate
  (e/ê 1.1-1.2).
- With M₀ᶜ as model (O-F) it fails like the real data (0.018, 0.009, 0.000),
  and the weak facet d3's gains run away (|g| up to 91 at cap 500, 784 at
  cap 2000), as they do on real data with RM (up to 58 and 156).

DD9 asks:

- **(a) The rate.** B and O-X share the truth gains, noise, flags, weights,
  solver, step rule, direction order and initial guess (all gains 1). They
  differ only in the model visibilities of d1-d3 (sky O: 4.43, 0.77,
  0.05 Jy net, with Σ|·| 21.2, 4.1, 2.8 Jy of DEEP − M₀ᶜ added). So the
  cause of the slower rate is in what those visibilities do to the problem's
  conditioning. Two hypotheses:
  - **Ha1, facet coupling:** the deep off-axis emission makes the
    directions' model visibilities overlap more, per antenna and interval,
    so the per-direction (Jacobi) update converges slowly through the
    cross-direction terms it ignores.
  - **Ha2, within-facet conditioning:** one facet's own problem (with the
    other directions held at the solution) becomes slow, for example d1's
    extended emission on short baselines or d3's weak net flux.
  The step rule, the direction order and the initial guess cannot be the
  cause (they are the same in B and O-X), but each is a remedy that may
  close the gap. They are run as interventions, each with its predicted
  rate.
- **(b) The weak facet d3.** On O with M₀ᶜ (the realistic model gap) does a
  constraint on d3 (pinned, merged into its neighbour, amplitude-regularised,
  or solved at 16 × 8 s) stop its runaway, and what does it do to the truth
  error of d1-d3?
- **(c) A robust held-out score,** frozen here before it is used: does it
  rank (b)'s arms on O as truth error does, and what does it say about the
  same arms on the real data with the 145 bad baselines flagged?

Not done (brief): the unit-gain deep clean (DEEP) is not used as a model on
real data. On simulations sky O is the truth, not a model proposal.

## 2. Data and inputs

DD7's root `D:/rang/outputs/dd7-20261125/` and DD8's root
`D:/rang/outputs/dd8-20261125/` are read only. DD9's root is
`D:/rang/outputs/dd9-20261126/`.

- **B:** DD7's `b/sim.ms`, sky M₀ᶜ `b/sky.npy`, truth `b/truth.npz`
  (per 4 integrations, d0 exactly 1), k = 0.5291.
- **O:** rebuilt in DD9's root by `dd8.insert` (DD8's code, unchanged), gate
  **GO** as DD8 froze it, and its `build.json` numbers equal DD8's
  `O/build.json` to 1e-9 relative. Sky O = DD8's `O/sky.npy` (equal to the
  rebuilt one, SHA-256 checked).
- **Real:** DD7's `real/sub.ms`, model RM `models/RM.npy`.
- **The 145 bad baselines:** `badbaselines.json` (DD7's `bad_pairs`).
  **Flagged in every real-data arm.**
- **Held-out baselines:** DD8's draw, `heldout.json` (169 baselines, seed
  8803), unchanged.
- Facet centres (`setup.json`): d3 at (l, m) = (0.01421, 0.00245); its
  nearest facet centre is d1's (0.0138 rad away; d0 0.0144, d2 0.0189).

## 3. The reference solver (the instrument)

Every DD9 solve runs in a numpy reference of rang's `diag_complex` DD kernel
(`core/src/cal/diag_dd.rs`, QuartiCal 0.2.7's update), written in
`tools/oracles/dd9/dd9.py`. No Rust changes.

**Compression (exact, not an approximation).** Inside one solution interval
a gain is constant over the cells of a baseline and hand, so the kernel's
`J^H r` and `J^H J` depend on the data only through, per (4-integration
block, baseline, hand), `A_dd' = Σ w conj(M_d) M_d'` (ndir × ndir) and
`b_d = Σ w conj(M_d) V`, summed over the cells `crate::solve::data_flags`
keeps (a cell is dropped if any of its four flags, its row flag, a zero
parallel-hand datum or a zero parallel-hand weight). Longer intervals sum
blocks. Also kept per block, baseline and hand: `Σ w |V|²` and the cell
count, so held-out scores come from the same sums.

**Default update, exactly as the kernel:** per gain, `jhr_p,d = Σ_q g_q,d
(b_d − Σ_d' A_dd' g_p,d' conj(g_q,d'))` (and the conjugate form for the q
side), `jhj_p,d = Σ_q |g_q,d|² A_dd`; no update if `jhj_x jhj_y < 1e-6`;
`g ← g + u/2` on every iteration (DD halving); flagged gains held at 1 and
kept in the model; QuartiCal's flag ladder (numbness 1e-6, trend limit
1e-6), the global stop at the first iteration whose converged fraction
reaches 0.99, `finalize_gain_flags`, `refant=None`; the one-longer second
solve for the per-direction measure. Initial gains 1.

**Gate GR (frozen; a miss stops DD9 at a setup outcome):**
- On O-X and O-F (sums from the rebuilt O, cap 500), against DD8's kept
  `grid/O-X.npz` and `grid/O-F.npz` (Rust): per-direction converged
  fraction within 0.005 in d0-d3; flagged gains per direction within 1 %;
  on cells converged in both, max |Δ(g_p conj g_q)| ≤ 1e-6.
- On B (cap 500): per-direction fraction within 0.005 of DD6's `B-F-4`
  (0.997, 0.988, 0.974, 0.939; it ran to the cap).
- One Rust point with no solver change, the merged arm **bM** on O
  (`cal_gain.solve_dd` with three model columns), against the reference's
  bM: the same three bullets' tolerances. It checks the reference off the
  default configuration.

**Oracle statement.** The Rust kernel's default path is unchanged and keeps
DD6's QuartiCal 0.2.7 parity status: flags, converged fraction and
iterations identical, gain products 5.4e-5 against a 1e-5 bar, **not met**.
The reference is checked against the Rust kernel (GR), not against
QuartiCal. The variants of sections 4 and 5 have no QuartiCal counterpart:
their oracle is O's and B's truth (`e_d`) and, for variants that should not
move the fixed point, the default's own converged solution (section 4,
same-fixed-point check). A variant that wins here is a proposal for a later
Rust change, which then needs its own parity (the default path unchanged)
and fixed-point checks; DD9 claims no solver gain.

## 4. Part (a): the rate on B and O-X (exact models, d0 free, 4 × 8 s)

**Points.** B-X (B, M₀ᶜ, which is B's sky) and O-X (O, sky O), default
update, run to cap 2000 with the per-iteration history kept: per interval,
direction and iteration, the converged fraction of that interval's gains and
the median step `|Δg|²/|g|²`. From it, per interval: **N_conv**, the first
iteration at which every direction's gains in the interval are at least
99 % converged (2000 + 1 if never). The cap-500 fractions are read from the
same run (iterations are deterministic).

**Linearised rate.** Per interval and hand, at the cap-2000 gains, the
Jacobian `J` of the one-iteration map `F(g)` in real coordinates (2 × 61 × 4
unknowns; flagged gains fixed), by central differences (relative step
1e-6). Each direction's global phase is a gauge (`F` is covariant, so `J`
has eigenvalue 1 there): project it out (`P J P`, `P` the projector off the
four gauge vectors `i g_·,d`). Then:
- **ρ_full** = spectral radius of `P J P`; decay time `τ = −1/ln ρ`
  iterations per e-fold; predicted iterations to the stop test
  `N_pred = τ ln(s₀ / 1e-7)`, with `s₀` the interval's median first-step
  size `|Δg|/|g|`.
- **ρ_within,d** = spectral radius of the gauge-projected diagonal direction
  block `J_dd` (direction d updated with the others fixed at the solution);
  `τ_within = max_d τ_within,d`, and the direction that attains it.
- Reported beside them (no reading): per antenna and interval the
  normalised direction overlap `|H_dd'| / sqrt(H_dd H_d'd')` of the
  per-antenna Hessian block `H_p[d,d'] = Σ_q g_q,d conj(g_q,d') A_dd'`
  (median and p90 per pair), and per direction the signal `Σ A_dd`.
- Intervals whose gains are not converged at cap 2000 are linearised at
  their cap-2000 state and reported separately; the readings below use the
  intervals converged at cap 2000 in both B-X and O-X unless fewer than 20
  are, then all.

**Readings (frozen):**
- **Ra1, does the linear rate explain the slowness.** Spearman correlation
  between N_conv and N_pred over the intervals of B-X and O-X pooled
  ≥ 0.7, and the ratio of the O-X to B-X medians of N_pred within a factor
  2 of the ratio of their N_conv medians: **explains**; correlation ≥ 0.4
  or the ratio within a factor 3: **partly**; else **does not explain**
  (the slowness is then transient or nonlinear, and the initial guess is the
  first suspect).
- **Ra2, coupling or within-facet.** On O-X, per interval, the coupling share
  `κ = 1 − τ_within / τ_full`. Median κ ≥ 0.5: **facet coupling dominates
  (Ha1)**; ≤ 0.2: **within-facet conditioning dominates (Ha2)**, naming the
  direction that most often attains τ_within; between: **both**. The same
  numbers on B-X are reported as the reference.

**Interventions (on B-X and O-X, all from the same reference, cap 500, and
their predicted ρ from the same linearisation where defined):**

| Arm | Change from the default | Moves the fixed point |
| --- | --- | --- |
| **I1** step rule | halve only on odd iterations (QuartiCal's DI rule, `loop_idx % 2 == 0` gets the full step); predicted per-iteration ρ = sqrt(ρ(J_½ J_1)), `J_1 = 2J − I` | no |
| **I2** order | Gauss-Seidel over directions: d0 updated, then d1 with the new d0, and so on, each with the halved step | no |
| **I3** joint directions | per antenna and hand, the 4 × 4 direction block `H_p` solved (u = H_p⁻¹ jhr_p, diagonal fallback if its condition number exceeds 1e12), then halved | no |
| **I4** initial guess | each interval starts from the previous interval's final gains (interval 0 from 1); flags start fresh | no |

**Rule per intervention (frozen):** with Δ = min_{d1-d3}(B-X) −
min_{d1-d3}(O-X) at cap 500 (default), an intervention **closes** the gap
if min_{d1-d3}(O-X under it) − min_{d1-d3}(O-X) ≥ 0.5 Δ, **partly** if
≥ 0.2 Δ, else **no**; it is **admissible** only if on B-X its min_{d1-d3}
is not below the default's by more than 0.02, on O-X its converged cells are
accurate (e/ê ≤ 2 in d1-d3), and it passes the **same-fixed-point check**:
on cells converged in both it and the default at cap 2000, the gain products
`g_p conj g_q` agree to median ≤ 1e-6 and p99 ≤ 1e-4.

**Outcome table (a):**

| Ra1 | Ra2 | Reading |
| --- | --- | --- |
| explains | coupling | the deep off-axis sky couples the facets; the Jacobi DD update is the bottleneck. If I3 or I2 closes: the remedy is a coupled direction update |
| explains | within-facet | one facet's own problem is ill-conditioned (named); the remedy is a constraint on it (part b) or a different parametrisation |
| explains | both | both, in the measured shares |
| partly or does not explain | any | the slowness is not the asymptotic rate; read I4 (initial guess) first |

Interventions are read in every row and reported as remedies, not causes.

## 5. Part (b): a constraint on d3, on O with M₀ᶜ (d0 free, 4 × 8 s)

**Arms (reference solver, cap 500; cap 2000 reported):**

| Arm | d3 |
| --- | --- |
| **b0** | free (the default; equals DD8's O-F through GR) |
| **bP** | pinned at 1 (the limiting control: d3's model kept, never solved) |
| **bM** | merged into d1 (nearest centre): one model column `M_d1 + M_d3`, three directions; d3's applied gain is d1's |
| **bR** | amplitude prior on d3 only: `λ (|g| − 1)²` per hand added to the χ² in the solver's units, `λ = k / σ_A²`, σ_A = 0.2, k = 0.5291 (λ = 13.2): `jhj += λ`, `jhr += λ g (1/|g| − 1)` before the update |
| **bL** | d3 solved at 16 × 8 s, d0-d2 at 4 × 8 s; the solve runs on 16-integration superblocks, the flag ladder and the stop test per gain as before |

**Scores per arm (frozen), on O against the truth:**
- `e_d` for d1, d2, d3 as DD5 (median |P − P̄| / |P̄| over unflagged cells,
  pairs and hands, P̄ the truth product averaged over the truth blocks of
  the solution interval), **absolute**, on all cells and on cells converged
  in both antennas. For bM, d3's e is the applied (d1) gain against d3's
  truth; for bP, d3's applied gain is 1. ê is reported but not compared
  across arms (it changes with interval and merged flux).
- Converged fraction per direction (cap 500 and 2000).
- d3 |g| p99, maximum, and cells with |g| > 10.

**Rule (frozen), against b0 (e⁰):**
- **tames d3**: d3 |g| max ≤ 10 and p99 ≤ 3 at both caps;
- **improves**: e_d ≤ 0.8 e⁰_d in each of d1, d2 and d3 (all cells, cap 500);
- **harms**: e_d > 1.2 e⁰_d in d1 or d2;
- otherwise **unchanged** in that direction.

| Arm result | Reading |
| --- | --- |
| tames and improves | **the constraint works on O**: d3's runaway also costs d1-d2 accuracy |
| tames, d1 and d2 unchanged | **d3 tamed, d1/d2 truth error unchanged**: the runaway is a symptom; O-F's error (d1 e/ê 72) is the model gap, and the next step is model work |
| tames and harms | **the constraint moves the error into the neighbours** |
| does not tame | **the constraint fails** on O |

**Best arm (frozen choice):** among arms that tame d3 and do not harm, the
one with the lowest max over d1-d3 of e_d / e⁰_d at cap 500; bP is a
control and cannot be chosen. If none qualifies, no best arm, and section
6's real arms report all of bM, bR, bL with no reading.

## 6. Part (c): the robust held-out score

**Frozen form.** On held-out cells (original flags off, w > 0, both hands),
`H_b = Σ w |r|² / (2k) / N_b` per held-out baseline b, all solutions in one
comparison scored on the same cells (a block is dropped if any compared
solution has a flagged gain on either antenna in any direction). The robust
score is **median_b H_b**; a pair A − B is read on the **median over
baselines of the per-baseline difference** `H_b(A) − H_b(B)`, **significant**
if the 99 % percentile bootstrap interval (2,000 resamples of the held-out
baselines, seed 9901) excludes 0. The 10 % trimmed mean of H_b is reported
beside it.

**Post hoc re-read of DD8 (labelled post hoc: the form was chosen after
DD8's medians were seen).** From DD8's kept `score/*.npz` (per-baseline S,
N), V1-V3 and DD8's pair readings in the robust form, reported only.

**Validation on O-H (frozen, before any real reading).** (b)'s arms solved
again on O-H (O with the 169 held-out baselines removed from the sums) and
scored: the robust score **tracks truth on O** if its order of the four
non-control arms b0, bM, bR, bL equals the order by mean over d1-d3 of
`e_d` (on O-H, all cells) in the best and the worst arm; **does not track**
otherwise.

**Real arms (flagged: the 145 bad and the 169 held-out baselines; model RM,
d0 free, 4 × 8 s, cap 500):** real-b0 (default) and the best arm of
section 5 (if none, bM, bR and bL reported only). Reading of best − b0 by
the frozen pair rule: **the constraint predicts better / worse / no
difference**, called an **accuracy proxy** if the O-H validation tracks,
**predictive quality only** otherwise. d3 |g| tails and converged fractions
reported.

## 7. What the outcomes mean for the DD plan

| Outcome | Next DD step |
| --- | --- |
| (a) coupling, and I3 or I2 closes and is admissible | A coupled-direction update in Rust, as an option beside the QuartiCal path: parity of the default path kept, fixed-point agreement with it, then O-X and real at 4 × 8 s |
| (a) within-facet, a named facet | Constrain or re-tile that facet (part b's result for d3; re-tile if it is d1) |
| (a) an intervention closes but is not admissible | Record; the remedy changes the answer, not only the speed |
| (a) does not explain | Initial guess and transients first (I4), then a longer cap as the working setting |
| (b) works on O, (c) tracks | Carry the constraint into the real DD recipe with the 145 flagged; score real solutions with the robust held-out score |
| (b) d3 tamed, d1/d2 unchanged | The weak-facet runaway is a symptom; model work next (an off-axis model from DD-corrected facet images, tested on O, where the truth is known) |
| (b) moves the error or fails | Drop the d3 constraint; model work next |
| (c) does not track | The robust held-out score is not a criterion for DD choices; accuracy only in simulation |

## 8. Not claimed

Image quality; real gain accuracy beyond what (c) supports; any speed or
accuracy gain of a solver variant (proposal only, section 3); anything about
QuartiCal beyond DD6's parity status.

## 9. Implementation, host and cost

- `tools/oracles/dd9/dd9.py`: `sums` (predict and compress one base and
  model into `sums/<name>.npz`), `solve` (the reference, arms of sections
  4-6), `jac` (section 4's linearisation), `score` (section 6), `gate`
  (GR), `rust-bm` (the one Rust point). Unit tests in `tests/test_dd9.py`:
  the compressed update equals a cell-by-cell update on synthetic data, the
  gauge projection, the bootstrap pair rule.
- glacier, shared, under the main checkout's `tools/heavy_lock.py`: `sums`
  and the Rust point 4 slots and 15 GB; reference solves, `jac` and scores
  2 slots and 6 GB. No exclusive or timing runs.
- **Point cap:** sums for O-M₀ᶜ, O-skyO, B-M₀ᶜ, O-M₀ᶜ-merged, real-RM
  (5, plus held-out variants made by masking); reference solves: B-X, O-X
  (cap 2000), I1-I4 on B-X and O-X (8, cap 2000 for the fixed-point
  check), b0, bP, bM, bR, bL on O and O-H (10, cap 2000), real arms (up
  to 4); one Rust point. One spare per class for a rerun.
- Expected: O rebuild about 150 s of work plus the 2.5 GB copy; each sums
  build about 60-120 s; reference solves seconds to minutes. Wall times go
  into [tool-timings.md](tool-timings.md). The rebuilt O copy is deleted at
  the end; the archive `results/dd9-solver/` keeps the records.

## 10. Measured result

Run root `D:/rang/outputs/dd9-20261126/`: `O/` (rebuilt; its MS since deleted), `sums/`, `gates/`,
`solve/`, `jac/`, `score/`, `logs/`, `times.log`. The archive is
[results/dd9-solver/](results/dd9-solver/). Host glacier, shared, under the
main checkout's `heavy_lock.py`. No Rust changes; the Rust point used the
main checkout's extension. Fractions are d0, d1, d2, d3 unless marked d1-d3.
e/ê is per direction, d1-d3.

**Setup and gate GR: pass.**
- O is rebuilt equal to DD8's (A1).
- The reference equals the Rust kernel:
  - O-F and O-X: per-direction fractions and flag counts identical to
    DD8's records; gain products on converged cells within 4e-14.
  - B-F: DD6's fractions to every digit.
  - The Rust bM point (three model columns): fractions and flags
    identical; products within 1.1e-7, from float32 rounding of the summed
    model column.
- `e_d` from this code on DD8's Rust gains equals DD8's to every digit.

### Part (a): B-X against O-X

| Point | cap 500 | cap 2000 (no global stop) | e/ê d1-d3 (all cells, cap 500) | flagged gains |
| --- | --- | --- | --- | --- |
| B-X default | 0.997, 0.988, 0.974, 0.939 | 1.000, 1.000, 1.000, 0.991 | 1.08, 1.02, 1.03 | 113, 113, 113, 121 |
| **O-X default** | **0.639, 0.540, 0.464, 0.449** | 0.841, 0.815, 0.817, 0.805 | 1.22, 1.09, 1.10 | 127, 117, 132, 156 |
| O-X I1 (DI step rule) | 0.363, 0.113, 0.048, 0.086 | 0.739, 0.739, 0.735, 0.722 | 1.91, 1.51, 1.49 | 545, 319, 311, 383 |
| **O-X I2 (Gauss-Seidel over directions)** | **0.997, 0.979, 0.974, 0.974** | 1.000, 1.000, 1.000, 0.980 | 1.21, 1.08, 1.08 | 113, 113, 113, 116 |
| **O-X I3 (joint direction block)** | **1.000, 1.000, 0.991, 0.991** | 1.000, 1.000, 1.000, 1.000 | 1.21, 1.08, 1.08 | 113, 113, 113, 114 |
| O-X I4 (warm start) | 0.748, 0.694, 0.619, 0.592 | 0.920, 0.842, 0.859, 0.843 | 1.24, 1.11, 1.12 | **1077, 1245, 1297, 1343** |
| B-X I1 / I2 / I3 / I4 | min d1-d3 0.983 / 0.956 / 1.000 / 1.000 | 1.000 / 0.980 / 1.000 / 1.000 | 1.08, 1.02, 1.03 (all four) | 113-118 |

113 flagged gains per direction is one per interval, an antenna with no
data. GR reproduces the cap-500 defaults.
- I4's fractions and accuracy cover only the gains it leaves unflagged: it
  flags 16-19 % of them, because the flag ladder's trend test starts from
  the small first step a warm start gives.

**Iterations to converge (per interval, default):**
- B-X: median N_conv 97 (p10-p90 88-110); 106 of 113 intervals converge
  within 500 iterations; one interval never converges, the short last one.
- O-X: median N_conv 1,094 (p10 142, p90 never); 47 intervals within 500,
  41 between 500 and 2000, 25 never.
- Median first step s₀: 0.31 in B-X, 0.32 in O-X.

**Frozen readings (section 4, on the 88 intervals converged at cap 2000 in
both):**
- **Ra1: explains.** Spearman(N_conv, N_pred) = 0.82. The medians are
  N_conv 99.5 in B-X and 219 in O-X (ratio 2.20) against N_pred 141 and 194
  (ratio 1.38), within a factor 1.59.
- **Ra2: both.** On O-X the median κ is 0.30 (p10-p90 0.27-0.34), against
  0.18 on B-X. Median ρ_full is 0.926 on O-X and 0.899 on B-X. τ_within is
  set by d1 in 71 of the 88 intervals and by d0 in 17.
- Reported beside them: the median normalised direction overlap is
  0.144, 0.131, 0.115, 0.139, 0.113, 0.082 on O-X (pairs 01, 02, 03, 12,
  13, 23), against 0.118, 0.111, 0.086, 0.104, 0.085, 0.052 on B-X.

**Interventions (section 4's rule, gap Δ = 0.490):**

| Arm | Lift of min d1-d3 on O-X | Reading | B-X not worse | O-X accurate | Same fixed point (B-X, O-X) | Admissible |
| --- | --- | --- | --- | --- | --- | --- |
| I1 | −0.401 | no | yes | **no** (e/ê 2.26, 1.78, 1.58 on converged cells) | no, no | no |
| I2 | +0.525 | **closes** | yes | yes | no, no | no |
| I3 | +0.542 | **closes** | yes | yes | no, no | no |
| I4 | +0.143 | partly | yes | yes | no, no | no |

**Frozen outcome:**
- Section 4's table: Ra1 explains, Ra2 both, giving "both, in the measured
  shares".
- I2 and I3 close the gap and I4 partly. All three are accurate and none
  is admissible, because each fails the same-fixed-point check.
- That is section 7's row "an intervention closes but is not
  admissible": the remedy changes the answer, not only the speed.

**Post hoc (A2), reported only.** Why the frozen readings miss the cause,
and what answer the remedies change:
- **The default iteration is unstable at the solution in half the O-X
  intervals.**
  - Linearised at I2's converged gains, the default map has ρ_full > 1 in
    56 of 113 O-X intervals, maximum 1.17:
    - 31 of the 41 that converge between 500 and 2000 (median 1.11);
    - 23 of the 25 that never do (median 1.13);
    - 2 of the 47 that converge within 500.
    The other 12 slow intervals are slow without being linearly unstable
    at this point.
  - Every direction's own block is stable in every interval (median
    ρ_within 0.87, 0.89, 0.75, 0.80; none above 1).
  - Under the same linearisation the coupled updates are stable
    everywhere: I2 0.923 (max 0.934), I3 0.932.
  - So the instability comes from coupling between the facets. The
    per-direction (Jacobi) update, which takes every direction's step from
    one residual and halves it, overshoots.
  - **It needs all four directions (A4).** At I2's gains every subset of
    two or three directions, with the rest held at the solution, is
    stable in all 113 intervals:
    - medians on the 56 unstable intervals 0.81-0.92;
    - the d0-d2 block with d3 held, 0.923.
    Only the four together exceed 1. Holding any one direction fixed (as
    bP does with d3) restores stability. The instability is a property of
    the coupled four-facet update, not of d3 alone.
  - On B-X no interval has ρ_full above 0.905.
  - I1's full step makes it worse: ρ 1.45-1.9 on O-X.
- **Where the default "converges" slowly, it does so by flagging.**
  - In all 41 intervals that converge between 500 and 2000, the default's
    flag ladder has hard-flagged 60 gains (set to 1) that I2 keeps.
  - It then converges on the remaining gains. Those are a different,
    constrained solution: products differ from I2's by up to 0.40 (p99
    0.003-0.057).
  - In the 61 intervals where the default flags no extra gain, the default
    and I2 agree to 2e-14.
  - On intervals whose flag arrays are identical (A4), all the updates
    give the same answer to 3e-14:
    - default against I3: 106 B-X and 61 O-X intervals;
    - I2 against I3: 108 B-X and 109 O-X intervals.
    Every difference therefore comes from the flag ladder.
  - So the frozen same-fixed-point check fails because the default's own
    answer is constrained by flags, on B-X too (d3 121 flagged against 113).
  - On all cells the coupled updates are at least as accurate as the
    default on O-X (e/ê 1.21, 1.08, 1.08 against 1.22, 1.09, 1.10).
  - The frozen restriction of Ra1 and Ra2 to intervals converged in both
    excluded the unstable ones. On the 88 it kept, the linear rate is
    nearly equal in B-X and O-X, so neither reading sees the cause.
- **With the wrong model it does not help (A3).**
  - **bGS** (O, M₀ᶜ, Gauss-Seidel):
    - cap 500: 0.075, 0.011, 0.004, 0.000; cap 2000: 0.698, 0.459,
      0.410, 0.291;
    - e 0.35, 0.54, 1.00 in d1-d3, the same as b0;
    - d3 |g| up to 59 at cap 500 and 116 at cap 2000.
  - **real-bGS** (RM, the 145 bad and 169 held-out baselines removed):
    - fractions 0.119, 0.023, 0.018, 0.018, against real-b0's 0.115,
      0.033, 0.026, 0.018;
    - robust held-out pair: no difference (median 0.0003, 99 % interval
      −0.0004 to 0.0013).
  - So the coupled update cures the exact-model slowness. It does not cure
    the failure O and the real data share, which follows the model gap.

### Part (b): a constraint on d3, on O with M₀ᶜ

e is the absolute truth error `e_d` in d1, d2, d3 on all unflagged cells.
For bM, d3's e is the applied d1 gain against d3's truth; for bP it is the
unit gain. λ = 13.2 for bR. Cap-500 values are first; cap 2000 is the solve
with at most 2000 iterations and the global stop.

| Arm | fractions, cap 500 (cap 2000) | e d1, d2, d3 | d3 \|g\| p99 / max (cap 500; cap 2000) | e ratio to b0 | Reading |
| --- | --- | --- | --- | --- | --- |
| **b0** | 0.094, 0.018, 0.009, 0.000 (0.702, 0.479, 0.419, 0.308) | 0.350, 0.538, 1.000 | 13.8 / 91; 17.8 / 784 | 1 | (reference) |
| bP, d3 pinned | 0.815, 0.696, 0.611, 1 (0.993, 0.969, 0.951, 1) | 0.394, **0.740**, 0.508 | 1 / 1 | 1.13, **1.37**, 0.51 | **moves the error into the neighbours** |
| bM, d3 into d1 | 0.832, 0.696, 0.617 (0.992, 0.991, 0.970) | 0.385, **0.740**, 0.911 | 1.40 / 1.57; same | 1.10, **1.38**, 0.91 | **moves the error into the neighbours** |
| bR, amplitude prior | 0.326, 0.049, 0.017, 0.007 (0.921, 0.790, 0.757, 0.712) | 0.356, 0.546, 0.996 | 6.3 / 10.4; 6.3 / 10.4 | 1.02, 1.02, 1.00 | **fails** (not tamed: p99 above 3) |
| bL, d3 at 16 × 8 s | 0.102, 0.008, 0.004, 0.000 (0.699, 0.488, 0.420, 0.237) | 0.353, 0.542, 0.999 | 12.9 / 36; 21.4 / 212 | 1.01, 1.01, 1.00 | **fails** |

**Frozen outcome (section 5):**
- No arm tames d3 without harm, so there is **no best arm**.
- Pinning or merging d3 stops its runaway and lets d1-d2 converge (0.97-0.99
  at cap 2000). But d2's truth error rises from 0.54 to 0.74, because d3's
  sky is then absorbed into d2's or d1's gains.
- The amplitude prior caps |g| near 10 but leaves the errors as they are.
  λ = 13.2 is 2.5 % of d3's median `J^H J` (527), so this is a null for a
  prior as wide as the truth spread (σ_A 0.2), not for amplitude
  regularisation in general.
- Solving d3 at 16 × 8 s changes nothing.
- In every arm d1's error stays at 0.35-0.39 (e/ê about 70-80), and that
  is the model gap.
- So by section 7 "the constraint moves the error or fails": drop the d3
  constraint and do the model work next.
- b0 at cap 500 equals DD8's O-F (GR). At cap 2000, b0's fractions are
  within 0.007 of DD8's Rust O-F-2000; products on cells converged in both
  agree to 6.4e-6, with 2 flag differences. That is floating-point
  divergence over 2000 iterations in unconverged cells.
- O-H (the same arms with the held-out baselines removed) gives the same
  pattern. bP and bM tame d3, with e ratios 1.10-1.13 in d1 and 1.32-1.33
  in d2. bR and bL do not tame it (ratios 0.998-1.014).

### Part (c): the robust held-out score

**Post hoc re-read of DD8 in the robust form.** From DD8's archived
per-baseline sums: 113 of the 169 held-out baselines have cells there.
Reported only.
- V1: truth gains on B-H, median H_b 1.0002.
- V2: robust ΔH of BH-F 2.01, 0.074, 0.026 in d1-d3, against the truth's
  2.01, 0.074, 0.027. All are significant.
- **V3 in the robust form rewards absorption.** On O-H, H_b(truth gains,
  M₀ᶜ) − H_b(OH-F) has median +0.70, 99 % interval 0.20 to 1.72. So
  gains that absorb the model gap predict unseen baselines better than the
  true gains do. DD8's mean form read "indistinct".
- DD8's real pairs in the robust form:
  - RH-L2000 against RH-MF: no difference (−0.0004, −0.0014 to 0.0002).
  - R2H against RH-MF: R2H predicts better (0.39, 0.36 to 0.46); the mean
    form read "the same".
  - Every DD point beats RH-DI (0.62-1.28).

**Validation on O-H (frozen rule): tracks truth on O.**
- The order by median H_b, b0 (1.467) < bL (1.476) < bR (1.480) < bM
  (1.516), equals the order by mean e over d1-d3: 0.634, 0.635, 0.636,
  0.676.
- Caveats, post hoc:
  - The truth gains predict worse than every solve (median 2.88 against
    1.47-1.52), the absorption above.
  - Three of the four arms differ in truth error by under 0.4 %.
  - The frozen pair rule reads bR and bL as predicting better than b0
    (median differences 0.0025 and 0.0016, significant), although their
    truth errors are slightly higher.
  - bP, the control with the lowest truth error (0.544, since unit d3
    gains are nearer the truth than runaway ones), predicts no differently
    from b0.
- On this evidence the robust score orders solutions by how well they
  absorb, and that agreed with truth error here only at the extremes.

**Real arms.** RM, d0 free, 4 × 8 s, cap 500, with the 145 bad and 169
held-out baselines removed (314 baselines); 113 held-out baselines scored.
No best arm, so these are reported only, without a reading.

| Arm | fractions d0-d3 | d3 \|g\| p99 / max | median H_b | against real-b0 (median, 99 % interval) |
| --- | --- | --- | --- | --- |
| real-b0 | 0.115, 0.033, 0.026, 0.018 | 10.3 / 71 | 1.651 | – |
| real-bM | **0.969, 0.890, 0.834, (0.890)** | 1.26 / 1.42 | 1.645 | bM better, 0.0098 (0.0006 to 0.0246) |
| real-bR | 0.473, 0.239, 0.191, 0.137 | 5.1 / 7.2 | 1.635 | bR better, 0.0071 (0.0038 to 0.0108) |
| real-bL | 0.139, 0.072, 0.071, 0.068 | 9.9 / 23 | 1.654 | bL better, 0.0020 (0.0006 to 0.0042) |
| real-bGS (A3) | 0.119, 0.023, 0.018, 0.018 | 9.7 / 31 | 1.653 | no difference |
| unit gains | – | – | 4.289 | – |

- Merging d3 into d1 lifts the real d0-free solve with RM at 4 × 8 s and
  cap 500 for the first time (min 0.83). It needs neither the unit-gain
  deep clean nor a longer interval.
- On O the same merge raises d2's truth error by 37 %, so this lift is not
  evidence of better real gains.
- The held-out differences are under 1 % of H.


**Cost (glacier, shared, 1-2 slots per job; walls include lock waits).**
- O rebuild: 235 s.
- Sums: 73-83 s each.
- Reference solves, full data:
  - default with history to cap 2000: about 1,620 s;
  - I1 1,610 s, I2 2,210 s, I3 3,550 s;
  - I4 (sequential, both caps) 460-500 s;
  - part (b), five arms to cap 2000: 5,350 s per base;
  - real arms: 490-720 s.
- Linearisation: 509-759 s per third of the intervals.
- The Rust bM point: 556 s (solve 252 s).
- Gate GR: 400 s.

**Points against section 9's cap.**
- Sums: 4 files. The merged bM sums are a linear transform of O-M₀ᶜ's,
  not a separate build.
- Reference solves:
  - B-X and O-X, default: 2;
  - I1-I4 on each base: 8;
  - part (b), five arms on O and on O-H: 10;
  - real arms: 6 (b0 twice, in `real.json` and `real-bGS.json`, plus bM,
    bR, bL and bGS), against "up to 4" plus a spare. That is one over, and
    the extra one is post hoc (A3).
  - Post hoc, beyond the list: bGS on O (A3).
- Linearisations: the frozen one at the default's gains, plus post hoc at
  I2's gains (A2) and on direction subsets (A4).
- One Rust point.
- One failed start: real-bGS first read a file that did not exist yet
  (rc 1, 11 s, no result); it was fixed and rerun.
- The 1-slot jobs used about 1.4 cores each (lock status).

## 11. For the coordinator

- **(a) Frozen:**
  - Ra1 "explains" and Ra2 "both" (κ 0.30).
  - I2 (Gauss-Seidel over directions) and I3 (joint direction block)
    **close** O-X's gap at cap 500 (min d1-d3 0.974 and 0.991, against
    0.449) and are accurate (e/ê 1.08-1.21).
  - Neither is admissible: the same-fixed-point check fails, on B-X too.
  - I4 (warm start) partly closes; I1 (DI step rule) does not and is
    inaccurate.
- **(a) Post hoc (A2), the cause:**
  - The default DD update (all directions from one residual, halved) is
    linearly unstable at the solution (ρ 1.0-1.17) in 56 of 113 O-X
    intervals. Each direction's own block is stable there (ρ ≤ 0.90), so
    it is facet coupling.
  - Where the default still converges slowly, it does so because its flag
    ladder flags the unstable gains (60 in 41 intervals) and settles on a
    constrained solution.
  - Where flags agree, the default and I2 give the same answer to 3e-14.
  - Every subset of two or three directions is stable (A4). So pinning
    any one facet would also stabilise the default; part (b) shows that
    pinning d3 costs d2 accuracy.
  - The frozen restriction to intervals converged in both hid this.
- **(b) Frozen: no best arm.**
  - Pinning or merging d3 tames it but moves the error into d2 (e 0.54
    to 0.74).
  - The amplitude prior (σ_A 0.2) and d3 at 16 × 8 s fail to tame it.
  - d1's error (e/ê about 72) is the model gap in every arm. By section 7,
    drop the d3 constraint; model work is next.
- **(c):**
  - The robust held-out score tracks truth on O-H by the frozen rule, but
    only at the extremes. In its robust form it rewards absorption (V3
    post hoc), so it is not a criterion for DD choices.
  - On real data, merging d3 lifts RM at 4 × 8 s to min 0.83 and predicts
    held-out baselines 0.6 % better; on O the same merge costs d2 37 %
    accuracy.
- **Non-convergence and inaccuracy are separate problems.**
  - d3's runaway blocks convergence: real-bM reaches min 0.83 at cap 500,
    and bM on O reaches 0.97 at cap 2000.
  - The model gap sets the error (d1's e/ê about 72 in every O arm).
  - This reframes the cap-500 "failures" of DD4-DD8: converging and being
    right are tested separately.
- **The coupled update does not fix the wrong-model failure (A3).**
  Gauss-Seidel on O with M₀ᶜ (bGS) and on real data (real-bGS) gives no
  lift, so the failure O and the real data share still follows the
  off-axis model gap.
- **Recommended DD10, frozen before code:**
  1. A Gauss-Seidel (or joint-block) direction update in the Rust kernel,
     as an option beside the QuartiCal path. The default stays
     bit-identical; the option equals this reference on O-X; at
     convergence it agrees with the default where flags agree.
     On sky O the default update is unstable. Whether a better off-axis
     model on real data meets the same instability is not shown: DD8's
     R12 reached 0.87-0.90 at cap 500 with the default update.
  2. With it, the off-axis model work on O, where the truth is known: an
     off-axis model from DD-corrected facet images (DD3's loop), scored on
     d1's truth error, which is the dominant error. The 145 bad baselines
     stay flagged on real data.
- **Checks:**
  - Gate GR and the Rust bM point pass.
  - `tests/test_dd9.py` (reference against the Rust kernel on synthetic
    data) passes.
  - `tools/check_all.py --quick` PASS. The full check is left to the
    coordinator's merge check; DD9 changes no Rust.
- **Disk:** the rebuilt O copy is deleted. Kept in the run root: sums
  (about 0.5 GB), gains and records. Archive `results/dd9-solver/`.

## Amendments

**A1, 2026-11-26, setup (code written and unit-tested on synthetic data,
O rebuilt, sums built; no DD9 solve on O, B or real data run or read).**
- O rebuilt (`dd8.insert`): GO passes; every `build.json` number equals
  DD8's and `sky.npy` has DD8's SHA-256.
- I1's rule as frozen in section 4 had QuartiCal's DI rule reversed:
  QuartiCal (and `core/src/cal/diag.rs`) halves the update when `loop_idx`
  is even and takes the full step when it is odd. I1 is that rule. The
  predicted rate `sqrt(ρ(J_½ J_1))` is unchanged.
- Section 4's runs (B-X, O-X, I1-I4) run without the global stop, so every
  interval runs to cap 2000 and N_conv is defined for each. The cap-500
  readings are unaffected: DD6's B-F-4 and DD8's O-X ran to the cap
  without reaching the stop fraction, and GR checks the cap-500 values with
  the stop active.
- I4 runs the intervals one after another (the warm start needs the
  previous interval's result), each to its cap without the global stop;
  cap 500 and cap 2000 are separate sequential passes.
- Part (b) keeps the global stop at 0.99, as the Rust kernel does; its
  "cap 2000" is the solve with at most 2000 iterations.
- bM is scored in four-direction form, with d3's gain equal to d1's. This
  is exactly the merged model column.
- N_pred per interval uses the larger ρ_full of the two hands, since
  convergence needs both.
- The unit tests (`tests/test_dd9.py`) show the reference equals the Rust
  kernel on synthetic data, with flags identical and gains to 1e-9 at
  1-40 iterations, pinned and free. I1-I3 reach the default's fixed point
  there.

**A2, 2026-11-26, post hoc (after section 4's frozen readings Ra1, Ra2 and
the I1, I2, I4 points were read; I3 and part (b) not yet read).** Section 4
restricts Ra1 and Ra2 to the 88 intervals converged at cap 2000 in both
B-X and O-X; O-X's 25 never-converged intervals sit outside them, and the
linearisation at their cap-2000 state gives ρ_full above 1. Reported only,
changing no frozen reading: the default map (and its per-direction blocks)
is linearised again at I2's cap-2000 gains, which converged in every O-X
interval but the short last one, for all O-X intervals
(`jac ROOT O-X START STOP I2`, written to `jac/at-I2/`). If I2 passes the
same-fixed-point check, these are the default map's rates at its own fixed
point. A ρ_full above 1 there means the default (Jacobi, halved) iteration
is linearly unstable at the solution in that interval.

**A3, 2026-11-26, post hoc (after I2 was read on B-X and O-X: it closes
O-X's gap at cap 500; part (b) not yet read).** Two arms are added and
reported only. Neither changes a frozen reading or enters section 5's
best-arm choice.
- **bGS**: b0 (O, M₀ᶜ, d0 free, 4 × 8 s) with I2's Gauss-Seidel update,
  caps 500 and 2000. It is scored as section 5's arms are (truth error, d3
  tails), and asks whether the update that converges on the exact model
  also converges with the wrong one, and whether it is then accurate.
- **real-bGS**: the real arm of section 6 (RM, the 145 bad and the 169
  held-out baselines removed, cap 500) with I2's update, beside real-b0.
  It gets fractions, d3 tails and the robust held-out pair against
  real-b0. Its reading would be "predictive quality only" unless the O-H
  validation tracks.

**A4, 2026-11-26, post hoc (after every frozen reading and A2-A3 were
read; on the advisor's review of the draft).** Two checks are added,
reported only. Neither changes a frozen reading.
- **Which facets carry the instability.** At I2's cap-2000 gains on O-X,
  the default map's spectral radius is computed on every subset of two and
  three directions, with the other directions held at the solution
  (`jac_subsets`, `jac/subsets-*.json`). If the d0-d2 block (d3 held) is
  stable where the full map is not, then d3's coupling carries the
  instability.
- **The fixed-point check on intervals whose flag arrays are identical.**
  Default against I3 and I2 against I3, on B-X and O-X
  (`solve/posthoc_fixed_point.json`).
