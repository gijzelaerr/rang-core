# Rang: what is proven about CLEAN, a Gram-matrix formalism, and MeerKAT measurements

Study requested by the user on 2026-10-30, outside the big-plan task list:
verify the claim that "CLEAN has never been proven or fully understood but
just works", build a better understanding, and from it a better formalism,
with a Rust implementation and Lean proofs where they help. Everything below
is labelled proposed, implemented or measured. Code:
[`core/src/clean.rs`](../core/src/clean.rs) (kernels, unit tests),
[`core/examples/clean_theory.rs`](../core/examples/clean_theory.rs) (the
measured experiments), [`formal/RangFormal/Clean.lean`](../formal/RangFormal/Clean.lean)
(machine-checked theorems). Archive:
[`results/clean-theory.json`](results/clean-theory.json); the full tables
of the run are in `outputs/clean-theory-20261030/stdout.md` (ignored).

Continued later on 2026-10-30 (branch `clean-theory-2`): Theorems 2 and 3
are now machine-checked in full generality, including the misfit floor
`Q_∞` and convergence of the model (§3); a noisy recovery experiment (E2c)
and the coherence of a multi-scale dictionary (E7) were added to §5.

## 1. Verdict on the claim

The claim is false in its strong form and true in a weaker one.

**Proven since 1978.** Schwarz (1978, A&A 65, 345) proved that Högbom CLEAN
converges, as a data-fitting iteration, under three conditions: the dirty
beam is symmetric, it is positive (semi)definite, and the dirty image lies in
the range of the beam. His own 1984 summary (IAU Colloquium 49, "The method
CLEAN - use, misuse and variations", pp. 261-275, read in full for this note)
states the result as: the norm `Q = Δtᵀ B Δt` "diminishes with each iteration
and hence converges to zero, if 0 < g < 2 (g = loop-gain), B is symmetric and
Q cannot become negative", with the increment `ΔH = g(2−g) r²` where `r` is
the maximum residual; he identifies CLEAN with "a well known iterative method
from the pre-computer time to solve a system of linear equations" (Temple's
1938 relaxation method), shows that in the uv plane it is a weighted least
squares fit of the components' visibilities to the observed ones, and that
the fit is unique when the components are fewer than the number of
independent data. Bridle's NRAO deconvolution notes and Thompson, Moran and
Swenson restate the three conditions; Lannes, Anterrieu and Maréchal (1997,
A&AS 123, 183) and Mallat and Zhang (1993) place CLEAN inside matching pursuit,
whose convergence theory is standard. So "never proven" is folklore.

**Not proven, then and now.**

- Nothing says the limit is the true sky or near it, except in the sparse
  regime: for exactly `k` on-grid point sources without noise, greedy
  selection stays on the true support when the dictionary is incoherent
  enough (Tropp 2004 for OMP; Gribonval and Vandergheynst 2006 for MP, which
  is CLEAN). No theorem covers extended emission; Schwarz 1984 (Fig. 2)
  shows CLEAN with gain 1 turning a smooth background into "a perfect
  artifact" while fitting the sampled visibilities exactly.
- There is no convergence proof for the algorithms that are actually run:
  Clark's minor cycle with a truncated beam patch, Cotton-Schwab major
  cycles, multi-scale and multi-frequency CLEAN, auto-masking. The 2025 A&A
  paper by Müller, Hsieh and Bhatnagar (arXiv:2511.17410), read in full, says
  of its own Newton reading of Cotton-Schwab CLEAN that "this identification
  is not a mathematically rigorous proof" and that "the Newton algorithm
  actually assumes that the beam is invertible, which is not the case".
  PolyCLEAN (Jarret et al. 2025, A&A) calls CLEAN's output "a sparse
  intermediate solution to a least-square problem, without any further
  guarantee of sparsity or recovery".
- Bridle's notes: "To date no one has succeeded in producing a noise analysis
  of CLEAN itself." That still holds for the greedy iteration; the
  least-squares error analysis (Schwarz 1978) covers the fit on a fixed
  support.
- The restoring step (components convolved with a Gaussian, residuals added)
  has no theory and mixes units; nothing here changes that.

Sources read in full: Schwarz 1984 (publisher PDF, OCR text), Müller et al.
2025 (arXiv PDF), the PolyCLEAN HTML, Bridle's lecture page. Schwarz 1978,
Marsh and Richardson 1987, Lannes et al. 1997 and Gribonval and
Vandergheynst 2006 were not retrievable in full from this host (ADS and HAL
refused the fetches); their content is taken from Schwarz's own summary, the
secondary sources above and the standard sparse-approximation literature,
and every theorem used below is proved here from scratch.

## 2. The formalism (proposed; Theorems 1-4 machine-checked)

### 2.1 Setting

Let `E` be the real inner-product space of weighted visibilities,
`⟨x, y⟩ = Σ_k w_k (Re x_k Re y_k + Im x_k Im y_k)`, `w_k ≥ 0`, `Σ_k w_k = 1`.
Each pixel `p` of an `N`-pixel grid has an atom `a_p ∈ E`, the visibilities
of a unit point source there, `(a_p)_k = exp(−2πi u_k · x_p)`, so `‖a_p‖ = 1`.
For data `v ∈ E` and a model `m ∈ ℝ^N`:

- residual `e(m) = v − Σ_p m_p a_p`;
- misfit `Q(m) = ½ ‖e(m)‖²`;
- residual dirty image `r_p(m) = ⟨e(m), a_p⟩ = −∂Q/∂m_p`;
- point-spread function `b(x_p − x_q) = ⟨a_p, a_q⟩ = B_pq`, the Gram matrix
  of the atoms, so `r(m) = d − B m` with `d_p = ⟨v, a_p⟩` the dirty image.

Högbom CLEAN with gain `γ` and a pick rule `pick` is the sequence `m_0 = 0`,
`m_{k+1} = m_k + γ r_{p_k}(m_k) e_{p_k}`, `p_k = pick(m_k)`. Högbom's rule
is `p_k = argmax_p |r_p|`; a `τ`-weak greedy rule only demands
`|r_{p_k}| ≥ τ max_p |r_p|`. This is the pure greedy algorithm (matching
pursuit) for the dictionary `{a_p}` in `E`, and Gauss-Southwell coordinate
descent on the convex quadratic `Q` with step `γ` times the exact
coordinate minimiser.

### 2.2 Theorems

**Theorem 1 (one step; Schwarz 1978 in Gram form).** For every `m`, `p`, `γ`:
`Q(m + γ r_p e_p) = Q(m) − γ(2−γ)/2 · r_p²`.
Proof: `‖e − γ r_p a_p‖² = ‖e‖² − 2γ r_p ⟨e, a_p⟩ + γ² r_p² ‖a_p‖²`.
Lean: `Clean.misfit_step`. Corollary: `Q` strictly decreases at every step
with `r_p ≠ 0` iff `0 < γ < 2` (`Clean.misfit_step_le`).

What changed against the classical statement: the three conditions collapse
to one structural fact. Symmetry and positive semidefiniteness of `B` are
automatic because `B` is a Gram matrix, and the dirty image lies in the range
of `B` because `d = ⟨v, a_·⟩` is the image of `v` under the same map. The
only hypothesis is that **the beam subtracted from the residual image is the
Gram matrix of the atoms under which the dirty image was formed**. Every
divergence of CLEAN in practice is a violation of that one hypothesis: a
beam patch (Clark), a beam computed on the image grid and therefore
truncated for components near the edge, a smoothed beam whose Fourier
transform goes negative (Schwarz 1984 §3.3a), gridding and grid-correction
mismatches between the dirty image and the PSF (Bridle).

**Theorem 2 (summability and convergence of the residual image).** For any
pick rule and `0 < γ < 2`, `Σ_{k<K} r_{p_k}² ≤ 2 Q_0 / (γ(2−γ))` for all `K`,
so the picked peaks tend to zero (`Clean.sum_peak_sq_le`,
`Clean.peak_tendsto_zero`); under a `τ`-weak greedy rule, `r_p(m_k) → 0` for
every pixel `p` (`Clean.dirty_tendsto_zero`). In prose, one step further: let
`S = span{a_p}` and `P` the orthogonal projection onto `S^⊥`. Then
`e_k − e_0 ∈ S`, so `e_k = P v + s_k` with `s_k ∈ S`, and
`⟨s_k, a_p⟩ = r_p(m_k) → 0` for all `p`; the linear map `s ↦ (⟨s, a_p⟩)_p` is
injective on `S`, hence bounded below on the finite-dimensional `S`, so
`s_k → 0`, `e_k → P v` and `Q_k ↓ Q_∞ := ½ ‖P v‖²`. `Q_∞` is the misfit of
the least-squares pixel model; CLEAN converges to the weighted least-squares
fit for any `N`, not only for `N ≤ R` as in Schwarz's uniqueness statement
(uniqueness is a different question, see Theorem 5).

**Theorem 3 (the rate is the greedy ratio).** Define
`κ_k = r_{p_k}² / (2 (Q_k − Q_∞))`. Theorem 1 gives the exact contraction
`Q_{k+1} − Q_∞ = (1 − γ(2−γ) κ_k)(Q_k − Q_∞)`. If `κ_k ≥ κ > 0` along the
sequence then `Q_K − Q_∞ ≤ (1 − γ(2−γ)κ)^K (Q_0 − Q_∞)`
(`Clean.misfit_geometric`, stated with `Q` in place of `Q − Q_∞`, which is the
case `P v = 0`; the general case is the same two lines). Two instances:

- *finite dimension, exact greedy rule:* `κ_* := min_{s∈S, ‖s‖=1} max_p ⟨s, a_p⟩²`
  is attained on a compact set and positive (if every `⟨s, a_p⟩` vanished,
  `s ⊥ S` and `s = 0`), so CLEAN always converges geometrically, with
  `κ_* ≥ λ_min⁺(G)/N`, `G = Σ_p a_p a_pᵀ` on `S`. The increments
  `|γ r_{p_k}|` are then summable, so **the model converges**,
  `m_k → m_∞` with `Σ_p (m_∞)_p a_p = v − P v`.
- *a residual supported on `k` pixels `S'`:* `κ ≥ λ_min(B_{S'S'}) / k`,
  because `max_{q∈S'} (B c)_q² ≥ ‖B c‖²/k ≥ λ_min cᵀ B c / k` and
  `‖s‖² = cᵀ B c`. The worst case is noise: `κ ≈ 1/N`, one pixel's worth of
  the reducible misfit per step.

**Theorem 4 (coherence condition for the pick).** Let
`μ = max_{p≠q} |⟨a_p, a_q⟩|` be the peak absolute PSF sidelobe within the
image. If the residual is `Σ_{i∈S} c_i a_i` with `|S| = k`, some `c_i ≠ 0`,
and `2μk < 1 + μ`, then `max_q |⟨e, a_q⟩|` is attained inside `S`
(`Clean.greedy_pick_in_support`: for `p = argmax |c_i|`,
`|⟨e, a_p⟩| ≥ (1+μ)|c_p| − μ‖c‖₁` and `|⟨e, a_q⟩| ≤ μ‖c‖₁` for `q ∉ S`, and
`2μ‖c‖₁ ≤ 2μk|c_p| < (1+μ)|c_p|`). By induction from a `k`-sparse noiseless
sky every CLEAN component lands on a true source, the residual stays in
`span(a_S)`, Theorem 3 applies with `κ ≥ (1 − (k−1)μ)/k` (Gershgorin), and
`m_k → m_true` at rate `(1 − γ(2−γ)(1 − (k−1)μ)/k)^k`. This is Tropp's
coherence corollary, transported to CLEAN; the proof in Lean is the
elementary one above.

The exact condition is Tropp's exact recovery coefficient,
`η(S) = max_{q∉S} ‖B_SS⁻¹ B_{S,q}‖₁ < 1`: for `e ∈ span(a_S)`,
`r_q = B_{qS} c = B_{qS} B_SS⁻¹ r_S`, so `|r_q| ≤ η(S) ‖r_S‖_∞ < ‖r_S‖_∞`.
It is a property of the actual source configuration and is cheap for a
component list (`k³ + k² N`). Implemented as `clean::erc`.

**Proposition 4' (separated sources).** Write `μ_d` for the peak `|b|` at
Chebyshev distance `≥ d` pixels. If the `k` sources are pairwise `≥ d ≥ 2`
apart and `(k−1)(μ_{⌈d/2⌉} + μ_d) < 1 − μ_1`, then `η(S) < 1`. Proof:
`‖B_SS⁻¹‖_{1→1} ≤ 1/(1 − (k−1)μ_d)` by the Neumann series; for `q ∉ S` at
most one source is closer than `d/2` to `q` (two such sources would be
closer than `d` to each other), so `‖B_{S,q}‖₁ ≤ μ_1 + (k−1)μ_{⌈d/2⌉}`.

**Theorem 5 (non-uniqueness).** When `N > dim S` (more pixels than
independent real data; Schwarz's `W > R`), `m_∞` is one of an affine family
`m_∞ + null(A)` of exact fits and depends on `γ` and the pick rule. Nothing
in Theorems 1-4 selects among them; this is the mechanism of the extended-
emission artefacts, measured in E6.

**Theorem 6 (Clark's minor cycle).** Let the working residual `r̃` be
updated with a beam patch and let `r` be the true residual. A component
`c = γ r̃_p` changes the true misfit by `ΔQ = −c r_p + c²/2`, so the step
descends iff `r_p / r̃_p > γ/2`. The truncation error after components
`c_1..c_j` is bounded by `‖r − r̃‖_∞ ≤ f Σ_j |c_j|` with `f` the peak `|b|`
outside the patch. Hence a **provable minor-cycle rule**: continue while
`f Σ_j |c_j| < (1 − γ/2) |r̃_p|`. Clark's rule (stop when the peak falls
below `f` times the cycle's initial peak) is not of this form and gives no
guarantee; E5 measures both.

### 2.3 Scope: what the formalism does not say

It does not say the limit is the sky (only in the sparse regime), it does
not treat noise beyond `Q_∞`, it says nothing about multi-scale or
multi-frequency dictionaries (their atoms have coherence near one), it does
not cover off-grid sources except as model misspecification (E4), and it
does not touch the restoring step. The formalism's value is that it makes
each of these a precise, separate question, and that it yields three
diagnostics no pipeline computes today (§6).

## 3. Lean formalisation (implemented; checked)

`formal/` is a Lake project on `leanprover/lean4:v4.33.1` with Mathlib
`v4.33.1`. `RangFormal/Clean.lean` proves, over any real inner-product space
`E` and finite pixel type `ι` with unit-norm atoms: `misfit_step` (Theorem 1),
`misfit_step_le`, `misfit_iterate` (the telescoped identity), `sum_peak_sq_le`,
`summable_peak_sq`, `peak_tendsto_zero`, `dirty_tendsto_zero` (Theorem 2 for
`τ`-weak greedy rules), `misfit_geometric` (Theorem 3 given a greedy-ratio
bound), and `greedy_pick_in_support` (Theorem 4).
`RangFormal/FiniteDim.lean` (added in the continuation) proves the
compactness step: `exists_energy_bound` (a `κ ∈ (0, 1]` with
`κ‖s‖² ≤ Σ_i ⟪s, a_i⟫²` on the span of the atoms, from the compact unit
sphere of the finite-dimensional span), `exists_pixel_bound` (one pixel
carries `κ/N` of `‖s‖²`), `misfit_geometric_of_mem_visible` (for data in the
span and any `τ`-weak greedy rule, `Q_K ≤ ρ^K Q_0` with
`ρ = 1 − γ(2−γ)τ²κ/N < 1`) and `misfit_tendsto_zero_of_mem_visible`.
`RangFormal/Projection.lean` proves the projection step: the dirty image,
every step and the whole CLEAN sequence ignore the component of the data
orthogonal to the atoms (`dirty_add_orthogonal`, `iterate_add_orthogonal`),
the misfit splits as `Q_{w+z}(m) = Q_w(m) + ½‖z‖²` (`misfit_add_orthogonal`),
hence `misfit_geometric_general`: for arbitrary data there is a floor `Q_∞`
below every model's misfit and `Q_K − Q_∞ ≤ ρ^K (Q_0 − Q_∞)`; and
`iterate_tendsto`: the CLEAN model converges, because the picked peaks are
bounded by `C ρ^{k/2}` and the increments are summable
(`iterate_eq_sum`, `abs_peak_le`). `RangFormal/Audit.lean` prints the
axioms: all thirteen audited theorems depend on `propext`,
`Classical.choice` and `Quot.sound` only. The build takes 41-44 s on the
Windows workstation after `lake exe cache get` (4 min 50 s, clone included).
Not formalised: Proposition 4' and Theorem 6, whose proofs are the short
arguments in §2.2.

## 4. Implementation (implemented; tested)

`core/src/clean.rs`: `Sampling` (weighted `(u, v)`), `Grid`, `Psf` over the
full `(2n−1)²` offset range (so subtraction is exact anywhere in the image;
`coherence`, `outside_patch`), direct-sum `psf`, `point_vis`, `add_atom`,
`predict`, `dirty`, `misfit`, `convolve`, `subtract` (with an optional patch),
`hogbom`, `gram`, `solve_dense`, `min_eigenvalue` (Jacobi), `erc`,
`least_squares_model` (conjugate gradients for `Q_∞`). Five unit tests check
the PSF is the Gram matrix of the atoms (`dirty ∘ predict = convolve` to
1e-10), the one-step identity to 1e-12 for gains 0.1-2.3 with the sign flip
above 2, exact recovery under the coherence bound, and the dense solvers.
The example `clean_theory` builds MeerKAT sampling from the 64 ITRF
positions in `data/meerkat.itrf.txt` (provenance in `data/README.md`;
2018 simms copy, adequate for a PSF, not survey geometry): 1.4 GHz, one
channel, declination −30°, a snapshot (2,016 baselines) and a 13-sample
±2 h track (26,208), natural and uniform weights, a 64 × 64 grid of
2″ pixels (about 2.8 pixels per fringe of the longest baseline). Seeds are
fixed; the run is deterministic.

## 5. Measured results (2026-10-30, Windows workstation, single run of the example, 68.8 s)

Configurations. `μ` is the peak absolute sidelobe within the 64-pixel image,
`k*` the largest `k` with `2μk < 1 + μ`, `μ_d` the peak beyond Chebyshev
distance `d`, `k_sep(d)` the largest `k` allowed by Proposition 4'.

| config | M | μ | k* | μ_8 | μ_16 | μ_32 | k_sep(8) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| snapshot-natural | 2,016 | 0.9315 | 1 | 0.391 | 0.184 | 0.062 | 1 |
| snapshot-uniform | 2,016 | 0.8008 | 1 | 0.219 | 0.219 | 0.219 | 1 |
| track-natural | 26,208 | 0.9308 | 1 | 0.377 | 0.149 | 0.020 | 1 |
| track-uniform | 26,208 | 0.6803 | 1 | 0.076 | 0.066 | 0.065 | 3 |

The coherence of the on-grid dictionary is the correlation of *adjacent*
pixels (0.68-0.93 at this sampling), so the classical coherence bound allows
one source. It is the wrong tool for CLEAN; the ERC is the right one (E2).

**E1, the one-step identity (Theorem 1).** Six sources plus visibility noise
(image noise about 0.5/√(2M) of a 1 Jy source), 400 steps, `Q` recomputed
from the model visibilities at every step. With the exact beam the maximum
relative deviation `|ΔQ − (−γ(2−γ)/2 · r²)| / Q` over all steps and the four
configurations is 2.2e-13 (gain 1.9) and below 3e-14 for gains ≤ 1.5; no
step raises `Q`. At gain 2.1 every step raises `Q` and `Q_400/Q_0` is
`10^32`. With a truncated beam the identity fails and monotonicity with it:

| beam (gain 1) | steps raising Q, of 400 (four configs) | Q_400/Q_0 |
| --- | --- | --- |
| exact | 0, 0, 0, 0 | 0.098, 0.075, 0.120, 0.108 |
| ±32 (a beam on the image grid) | 175, 227, 182, 214 | 0.113, 66, 0.123, 0.202 |
| ±16 | 246, 336, 240, 309 | 7.6e7, 1.20, 5.0e5, 0.350 |
| ±8 | 253, 371, 241, 338 | 2.4e24, 2.13, 2.6e23, 0.519 |
| ±8, gain 0.1 | 221, 95, 216, 100 | 1.19, 0.184, 1.36, 0.160 |

Order: snapshot-natural, snapshot-uniform, track-natural, track-uniform.
The same-size-grid beam (what a plain Högbom on an `n × n` PSF does for
components near the edge) already breaks descent on about half the steps;
the natural-weight beams with their 0.33-0.39 exterior sidelobes diverge
outright with gain 1 and a ±8 patch.

**E2, exact support recovery (Theorem 4 and the ERC).** Noiseless `k`-sparse
skies at random pixels, fluxes uniform in [0.2, 1], gain 1, run to
`|r| < 1e-9`; success means every component on the support and the model
within 1e-6 of the truth. 100 trials per `k`, `k = 1..12`, sources anywhere
or at least 8 pixels apart; 9,600 trials in all.

| | success, any positions (k = 2, 4, 6, 8, 12) | success, ≥ 8 px apart | trials with ERC < 1 that failed |
| --- | --- | --- | ---: |
| snapshot-natural | 100, 89, 86, 69, 26 | 100, 100, 97, 97, 84 | 0 |
| snapshot-uniform | 100, 94, 95, 84, 70 | 100, 100, 100, 100, 100 | 0 |
| track-natural | 100, 95, 89, 81, 60 | 100, 100, 100, 100, 100 | 0 |
| track-uniform | 100, 99, 99, 98, 95 | 100, 100, 100, 100, 100 | 0 |

The ERC is a perfect sufficient condition in 9,600 trials: no trial with
`η(S) < 1` failed. It is far from necessary (track-uniform, any positions,
`k = 12`: 95 successes, 76 with `η < 1`; separated sources on the tracks:
100 % success while `η < 1` drops to 1-3 % at `k = 12`). The coherence bound
(`k* = 1`) is vacuous, as predicted from `μ`. Separation of 8 pixels makes
recovery of 12 sources reliable on every configuration but the snapshot with
natural weights (84 %), whose exterior sidelobes are 0.39.

**E3, the greedy ratio (Theorem 3).** On the noiseless `k`-source runs the
measured minimum of `κ_k` over the run is 1.5-3.2 times the bound
`λ_min(B_SS)/k` on every configuration (twelve cases); the bound holds and
is tight to a small factor. With six sources plus noise and gain 0.1, `κ`
starts at 0.29-0.49 (one source's worth), then falls to 1e-3-5e-3 of the
reducible misfit once the sources are gone. On pure noise `κ` relative to
`Q − Q_∞` has median 2.3e-4 to 3.6e-4 against `1/N = 2.4e-4`: the worst case
of Theorem 3 is what noise does. `Q_∞` was computed by 400 conjugate-gradient
iterations (3-4 s each); it is an upper bound (CG stopped at relative
residuals 2e-4 to 2e-2), exact in the snapshot cases only in the sense that
there `N = 4,096 > 2M = 4,032`, so `Q_∞ = 0` and the atoms span the data
space; the CG bound there (0.82, 0.35) shows how ill-conditioned that span
is. On the tracks `Q_∞/Q_0` is 0.97 (natural) and 0.56 (uniform) for white
visibility noise: with uniform weights the weighted norm concentrates the
noise in the sparsely sampled cells, which the image can fit.

**E4, an off-grid source** (unit flux at +0.5, +0.3 pixels, noiseless, run
to `|r| < 1e-4`). `Q` converges (to 1e-6 to 3e-5 of `Q_0`), the total model
flux is 0.9999-1.0008, and the model occupies 157-713 pixels after 461-20,000
components. Theorem 2 holds; the sparse model is misspecified, which is the
whole content of the off-grid problem.

**E5, Clark's minor cycle (Theorem 6).** Two hundred minor-cycle steps from
the exact residual of the E1 scene, counting steps whose true `ΔQ > 0`.

| gain, patch | f (exterior peak) | rises in 200 (four configs) | rises under Clark's rule | steps under Clark's rule | rises under the provable rule | steps under the provable rule |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1, ±8 | 0.36, 0.22, 0.33, 0.08 | 119, 25, 113, 16 | 0, 0, 4, 7 | 36, 56, 45, 161 | 0, 0, 0, 0 | 19, 28, 22, 59 |
| 0.1, ±16 | 0.17, 0.22, 0.14, 0.07 | 89, 28, 89, 14 | 0, 0, 0, 12 | 52, 58, 64, 179 | 0, 0, 0, 0 | 31, 28, 36, 64 |
| 1, ±8 | as above | 123, 182, 119, 175 | 4, 0, 119, 32 | 8, 5, 200, 40 | 0, 0, 0, 0 | 1, 2, 2, 4 |
| 1, ±16 | as above | 112, 172, 123, 157 | 3, 0, 1, 28 | 9, 5, 7, 40 | 0, 0, 0, 0 | 3, 2, 3, 4 |

Clark's rule leaves 0-119 ascending steps per cycle (track-natural with gain
1 never triggers it in 200 steps); the provable rule leaves none in all 24
cases, as Theorem 6 requires, at the price of short cycles (1-4 steps at
gain 1, 17-64 at gain 0.1). A Cotton-Schwab loop (±8 patch, 100 minor steps,
gain 0.1, twelve major cycles with the exact residual recomputed from the
visibilities) decreased `Q` monotonically across major cycles on all four
configurations (to 0.10-0.13 of `Q_0`), with no theorem behind that
monotonicity: the major cycle resets the working residual, it does not make
the minor steps descend.

**E6, extended emission (Theorem 5).** A Gaussian disc of FWHM 12 pixels,
noiseless, run to `|r| < 1e-3` or 30,000 components.

| config | gain | components | Q_end/Q_0 | rms(model − truth) inside the FWHM, in peaks | most negative pixel | rms difference from the gain-0.01 model |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| track-uniform | 0.01 | 30,000 | 1.4e-3 | 0.18 | 0.00 | – |
| track-uniform | 0.1 | 10,041 | 5.3e-7 | 0.28 | 0.00 | 0.059 |
| track-uniform | 1 | 1,346 | 1.1e-6 | 1.57 | −0.33 | 0.289 |
| snapshot-natural | 0.01 | 30,000 | 1.6e-5 | 0.55 | −0.34 | – |
| snapshot-natural | 1 | 5,862 | 6.6e-7 | 1.70 | −1.60 | 0.356 |

Every gain fits the data (Theorem 2); the limits differ by 0.26-0.42 of the
peak in rms and the gain-1 models carry negative pixels of 0.3-1.9 peaks,
Schwarz's Fig. 2 artefact on MeerKAT sampling. Small gains give smoother
limits, as Schwarz 1984 §3.3b reports, and no theorem says why beyond
Theorem 5's statement that the limit is path-dependent.

**E2c, recovery with noise** (added in the continuation). Sources at least
8 pixels apart, fluxes 0.2-1, white visibility noise scaled to an image
noise of 0.01 (measured 0.0096-0.0101), gain 0.1, stop at `|r| < 5σ`,
100 trials per `k`. "Exact support" means every source has a component and
no other pixel does.

| config | exact support (k = 2, 4, 6, 8, 12) | mean fraction of picks on the support | mean false pixels (k = 2 … 12) | rms flux error on the support, in σ | trials with ERC < 1 |
| --- | --- | --- | --- | --- | --- |
| snapshot-natural | 31, 5, 0, 1, 0 | 0.95-0.90 | 1.1 → 14.8 | 5.7-7.0 | 100, 89, 45, 5, 0 |
| snapshot-uniform | 62, 35, 14, 7, 3 | 0.98 | 0.45 → 3.4 | 5.0-5.1 | 100, 100, 98, 87, 0 |
| track-natural | 17, 2, 0, 0, 0 | 0.93-0.89 | 1.6 → 15.9 | 5.5 | 100, 99, 85, 59, 4 |
| track-uniform | 78, 79, 61, 47, 32 | 0.99 | 0.23 → 1.13 | 4.9 | 100 × 5 |

With one per cent noise the picks still land on the support 89-99.7 % of
the time, but strict support recovery is rare except with the best PSF:
the failures are components on pixels adjacent to a source, where the
atom correlation is 0.68-0.93 (the on-grid coherence of §5's first table),
so a small noise shift of the residual peak moves a pick one pixel over.
The flux error on the support is the 5σ stopping threshold, as it must be.
The ERC is no longer predictive: its premise, a residual in the span of
the support atoms, fails as soon as noise is present (the rows "exact
support given ERC" equal "exact support"). This is the quantitative form of
Theorem 4's noiseless scope.

**E7, a multi-scale dictionary** (added in the continuation). Multi-scale
CLEAN is the same greedy algorithm on a dictionary of blobs; here delta,
and Gaussians of FWHM 2, 4 and 8 pixels, under each configuration's PSF,
inner products computed exactly through the Gram matrix. The largest
normalised inner product between distinct atoms (offsets `(d, 0)` and
`(d, d)`, `d ≤ 16`):

| config | delta vs 2 px (same centre) | 2 px vs 4 px | 4 px vs 8 px | 8 px, unit offset | overall |
| --- | ---: | ---: | ---: | ---: | ---: |
| snapshot-natural | 0.986 | 0.967 | 0.959 | 0.993 | 0.993 |
| snapshot-uniform | 0.966 | 0.904 | 0.831 | 0.980 | 0.980 |
| track-natural | 0.987 | 0.968 | 0.959 | 0.993 | 0.993 |
| track-uniform | 0.926 | 0.848 | 0.807 | 0.979 | 0.979 |

The coherence of a multi-scale dictionary is 0.98-0.99 on every PSF, so no
coherence-type recovery guarantee can exist for multi-scale CLEAN at pixel
resolution; Theorems 1-3 still hold for it verbatim (its atoms are vectors
of the same space, their Gram matrix is positive semidefinite, and the
one-step identity is the same), and the ERC of a given component list stays
computable. Measured, not proven: which scale the greedy pick prefers is
decided by sub-per-cent differences in correlation, which is why
multi-scale CLEAN's scale bias is set by its scale weighting rather than by
the data.

## 6. What follows for practice (proposed)

1. **A Gram-consistency check.** Per minor cycle, compare the exact change
   of `Q` (from the model visibilities, which a Cotton-Schwab major cycle
   computes anyway) with `−γ(2−γ)/2 Σ r̃²`. The gap is the beam-truncation
   error in misfit units; E1 shows it is of order the misfit itself for beam
   patches on MeerKAT natural-weight PSFs. No pipeline reports it.
2. **The reducible misfit `Q_∞`.** A few hundred CG iterations on the PSF
   give the floor CLEAN is heading for; stopping rules in terms of
   `(Q − Q_∞)/(Q_0 − Q_∞)` are the quantity Theorem 3 controls, and the
   greedy ratio `κ_k` read off each step tells whether CLEAN is still
   removing sources (`κ ~ 1/k`) or noise (`κ ~ 1/N`).
3. **An ERC certificate on the component list.** For a list of `k` component
   positions, `η(S) < 1` certifies that no residual in their span could have
   sent a pick elsewhere; it costs `k³ + k² N` and was never wrong in 9,600
   trials. It is a per-image statement about sidelobe confusion among the
   found sources, not a detection statistic.
4. **Minor cycles:** the provable rule of Theorem 6 or, equivalently, a
   patch large enough that `f Σ|c_j|` stays below `(1 − γ/2)` of the peak.
   With gain 1 it allows one to four steps per cycle on these PSFs; gain 0.1
   gives 17-64. This is the quantitative form of "use a small gain".

None of these is a pipeline change in rang; they are candidates for the
imaging comparator once the MeerKAT verdict (big plan L4) is in.

## 7. Novelty, as AGENTS.md asks

The theorems are known in optimisation and sparse approximation (Schwarz
1978; Temple 1938; Mallat and Zhang 1993; Tropp 2004; Gribonval and
Vandergheynst 2006). The contribution here is (i) the Gram-form statement
that reduces Schwarz's three conditions to one and explains every known
divergence mode as its violation, (ii) machine-checked proofs of the core
(first for CLEAN, as far as the literature search shows), (iii) the measured
bridge to MeerKAT PSFs: the coherence bound is vacuous at critical sampling,
the ERC is exact in practice, Clark's rule gives no guarantee while the
provable rule does, and the gain-dependence of the extended-emission limit
quantified, and (iv) three cheap diagnostics. No claim of higher imaging
quality or lower cost is made; this is an understanding result, not a
pipeline result.

## 8. Reproduction

From the repository root (Rust 1.93 or later):

```bash
cargo test --release --manifest-path core/Cargo.toml clean::
```

```bash
cargo run --release --manifest-path core/Cargo.toml --example clean_theory -- outputs/clean-theory-20261030
```

```bash
cd formal && lake exe cache get && lake build
```

Timings (Windows workstation, 2026-10-30): core test build 63 s; the
example 68.8 s of compute (71.1 s with E2c and E7; PSFs 0.02-0.33 s, CG
3-4 s per `Q_∞`, E2 dominating); Lean 4 min 50 s for the Mathlib cache and
41-44 s per build.

## 9. Next steps

- Done in the continuation: the projection and compactness steps are
  formalised (§3); E2c measures recovery with noise; E7 measures
  multi-scale coherence.
- Done on branch `clean-phase-transition`: the recovery transition across
  four real arrays, a sharper separated-source condition (Theorems 7, 8)
  and the exact two-source rule, in
  [clean-phase-transition.md](clean-phase-transition.md).
- Formalise Proposition 4' (Neumann series) and Theorem 6 (the provable
  minor-cycle rule); both are finite algebra.
- A noise-margin statement for Theorem 4: Tropp's `η(S) < 1 − 2ε/‖r_S‖_∞`
  explains E2c's adjacent-pixel failures quantitatively; measure it.
- Multi-scale CLEAN: with coherence 0.98-0.99 the guarantee question is
  closed; what remains is measuring the ERC of real multi-scale component
  lists and the scale-weighting bias.
- Wire the Gram-consistency check and `Q_∞` into the imaging comparator
  alongside the WSClean oracle (`research/core-i-imaging-replay.md`).
