# DD9: why an exact deep off-axis sky slows the DD solve, and a constraint on the weak facet d3

Issue #15. Follows [dd8-offaxis.md](dd8-offaxis.md) (DD8) and
[dd7-cause.md](dd7-cause.md) (DD7). Branch `dd9-solver`. Coordinator brief
2026-11-26. A diagnostic with one constraint test in simulation; no claim of
better calibration or imaging on real data follows from it. Sections 1-9 are
frozen 2026-11-26, before the code that runs them and before any
measurement. Later changes are dated amendments, committed before the
reading they affect.

Status: **proposed 2026-11-26.**

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

## Amendments

None yet.
