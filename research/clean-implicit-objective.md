# What CLEAN minimises: small-gain CLEAN is forward stagewise, and its limit is the monotone lasso

Research question 1 of the CLEAN programme ([clean-theory.md](clean-theory.md)),
started 2026-10-30 on branch `clean-implicit-objective`. Question: what
objective does Högbom CLEAN implicitly minimise (Marsh and Richardson 1987,
A&A 182, 174, "The objective function implicit in the CLEAN algorithm"), and
why do small loop gains give smooth extended-emission models while gain 1
gives striped, negative ones (Schwarz 1984 §3.3b; E6 of clean-theory.md)?
Every claim is labelled **proved** (a complete argument here), **checked**
(machine-checked in Lean), **measured**, or **conjectured**. Code:
[`core/examples/clean_implicit.rs`](../core/examples/clean_implicit.rs);
Lean: [`formal/RangFormal/Stagewise.lean`](../formal/RangFormal/Stagewise.lean);
archive: [`results/clean-implicit-objective.json`](results/clean-implicit-objective.json).
Status of this revision: §§1-5 written; the Lean names cited as "checked"
are the targets of §7 and the measurements of §6 are pending.

Sources read in full for this note: Hastie, Taylor, Tibshirani and Walther
(2007), "Forward stagewise regression and the monotone lasso", Electronic
Journal of Statistics 1, 1-29 (arXiv:0705.0269; cited as HTTW), and Freund,
Grigas and Mazumder (2017), "A new perspective on boosting in linear
regression via subgradient optimization and relatives" (arXiv:1505.04243,
2015; later in the Annals of Statistics; cited as FGM). Marsh and Richardson (1987)
was not retrievable from this host (ADS redirects to a page that returned
no text), so nothing here characterises their result. Efron, Hastie,
Johnstone and Tibshirani (2004, "Least angle regression") is cited only
through HTTW; the proofs below do not use it.

## 1. The answer in brief

1. **Identification (proved; checked).** Högbom CLEAN with gain `γ` is
   incremental forward stagewise regression (FS) on the pixel atoms with a
   variable increment: both take the argmax pixel of the residual dirty image
   and move its coefficient in the direction of `sign r_p`; FS moves by a
   fixed `ε`, CLEAN by `γ|r_p|`. In statistics CLEAN is LS-Boost(γ) (FGM call
   it matching pursuit). Both are the subgradient method on the peak
   residual `φ = max_p |r_p|` as a function of the visibility residual (FGM,
   Proposition 3.2); CLEAN is the explicit Euler scheme with step `γ` for the
   subgradient flow of `½φ²`.
2. **The small-gain limit (proved).** As `γ → 0`, parametrised by ℓ1 arc
   length `L = Σ_k γ|r_{p_k}|`, CLEAN converges to the same limit as `FS_ε`
   with `ε → 0`: in data space always, to the unique gradient flow of `φ` in
   the weighted visibility metric; in model space whenever the atoms tied for
   the peak are linearly independent, to the monotone lasso path of HTTW
   (their Definition 3), and the converged small-gain model to the end point
   of that path. So the conjecture of the task is a theorem, with a proof
   that does not need HTTW's sketched limit argument, Efron et al.'s
   "one at a time" condition, or any coherence bound, and holds on the
   rank-deficient (`N > 2M`), strongly correlated pixel dictionary.
3. **The implicit objective (proved, with HTTW).** There is no objective
   that the small-gain model minimises at each arc length (HTTW Lemma 2:
   no path minimises the misfit among all paths of a given ℓ1 arc length).
   What CLEAN optimises is local: at every arc length it lowers the misfit
   `Q` at the largest possible first-order rate per unit ℓ1 arc length,
   `dQ/dL = −max_p |r_p|`, and among the directions that achieve that rate it
   takes the one with the smallest second-order term (the non-negative least
   squares direction on the tied pixels). In data space this is steepest
   descent of the peak residual. The lasso, by contrast, optimises per unit
   ℓ1 *norm*; the two coincide exactly when the lasso path is monotone.
4. **Consequences (proved; measured in §6).** Gain 1 is a large Euler step
   of that flow: exact line search on one atom of a dictionary whose
   neighbouring atoms correlate at 0.68-0.93 overshoots, and the model pays
   in arc length that it later has to undo (negative components, stripes).
   Small gain is the flow itself, which never moves a coefficient against
   its residual. Small gain does **not** imply a non-negative model: the flow
   goes negative whenever the most negative residual pixel is the global
   peak. In Schwarz's `W > R` regime the small-gain limit is a definite exact
   fit, the end point of the monotone lasso, which is in general not the
   minimum-ℓ1 fit.

## 2. Setting and the identification

Notation of [clean-theory.md](clean-theory.md) §2.1: `E` is the real inner
product space of weighted visibilities, `a_p ∈ E` the unit-norm atom of pixel
`p` (`N` pixels), `v` the data, `m ∈ ℝ^N` a model, `e(m) = v − Σ_p m_p a_p`,
`Q(m) = ½‖e‖²`, `r_p(m) = ⟨e(m), a_p⟩` the residual dirty image, `B_pq =
⟨a_p, a_q⟩` the PSF. Write `φ(e) = max_p |⟨e, a_p⟩| = ‖r‖_∞` (the peak
residual) and `‖m‖₁ = Σ_p |m_p|`. Since `|B_pq| ≤ 1`,
`‖r(m) − r(m')‖_∞ ≤ ‖m − m'‖₁` (used throughout).

**A stagewise step.** From `m`, pick `p ∈ argmax_q |r_q(m)|`, `σ = sign r_p`
(the algorithm stops if `r = 0`), and a length `h > 0`; set
`m' = m + h σ e_p`. Then `FS_ε` is `h = ε`; CLEAN with gain `γ` is
`h = γ|r_p|`, because `γ r_p = (γ|r_p|) σ`. Both use the same pick rule and
sign; ties in the argmax are broken by the same rule (lowest index in
`clean::argmax_abs`), which plays no role in the limit below.

**Lemma 1 (exact step identities; checked, `Stagewise.misfit_add_single`,
`misfit_stagewise_step`, `misfit_clean_step`).** For any `c`,
`Q(m + c e_p) = Q(m) − c r_p + c²/2`. Hence a stagewise step of length `h`
changes `Q` by `−hφ + h²/2`; for FS that is `−εφ + ε²/2` (the first-order
decrease per unit ℓ1 arc length is `|r_p| = φ`, and FS raises `Q` once
`φ < ε/2`), and for CLEAN `−γ(1 − γ/2)φ²`, which is Theorem 1 of
clean-theory.md. Per unit arc length both lose `φ − h/2`.

**Lemma 2 (ℓ1 steepest descent; checked, `Stagewise.misfit_add_ge`,
`misfit_add_eq`).** For every direction `d ∈ ℝ^N`,
`Q(m + d) = Q(m) − Σ_p d_p r_p + ½‖Σ_p d_p a_p‖² ≥ Q(m) − φ ‖d‖₁`. So no move of
ℓ1 length `ℓ` can lower `Q` by more than `φℓ` to first order, and the
stagewise pick attains that rate. The greedy pick is steepest descent for the
ℓ1 geometry on the model (FGM, §2, make the same remark for LS-Boost).

**Lemma 3 (arc length; checked, `Stagewise.l1_iterate_le_arc`).** The CLEAN
model after `K` steps satisfies `‖m_K‖₁ ≤ Σ_{k<K} γ|r_{p_k}| = L_K`. In the
expanded dictionary `{a_p, −a_p}` (HTTW §3) every step adds `h ≥ 0` to one
coefficient, so every CLEAN path is monotone there for every gain, and `L` is
the expanded ℓ1 norm (HTTW Lemma 1). The excess `L − ‖m‖₁` is twice the total
amount by which coefficients have moved back towards or through zero.
Monotonicity in the expanded space is therefore not what small gain buys;
what it buys is the *direction* among tied pixels (§3).

**Data-space form (FGM Proposition 3.2).** The step acts on the residual as
`e' = e − h σ a_p`, and `σ a_p` is a subgradient of the convex function
`φ` at `e`: `φ(e'') ≥ σ⟨e'', a_p⟩ = φ(e) + σ⟨e'' − e, a_p⟩`. So FS is the
subgradient method on `φ` with constant step `ε`, and CLEAN the same with
step `γφ(e)`, which is the subgradient method with constant step `γ` on
`Φ = ½φ²` (its subgradient at `e` is `φ(e) σ a_p = r_p a_p`). The minimiser
of `φ` on `v + span{a_p}` is the least-squares residual `e_LS`
(clean-theory.md Theorem 2: `Q_∞ = ½‖e_LS‖²`).

## 3. The small-gain limit

Define the set-valued field `F(m) = {d ∈ ℝ^N : ‖d‖₁ ≤ 1, Σ_p d_p r_p(m) = φ}`;
for `r(m) ≠ 0` this is the convex hull of `{sign(r_j) e_j : j ∈ A(m)}` with
`A(m) = argmax_j |r_j(m)|`, the subdifferential of `‖·‖_∞` at `r(m)`. A
**flow** on `[0, T]` is a Lipschitz `m(L)` with `m(0) = 0` and
`ṁ(L) ∈ F(m(L))` for almost every `L`. Its residual `e(L) = e(m(L))` then
satisfies `ė ∈ −∂φ(e)` (chain rule: `∂φ(e) = {Σ_p d_p a_p : d ∈ F}`), so `e`
is the gradient flow of `φ` in the weighted visibility norm, run in the
time variable `L`, which is ℓ1 arc length because `‖ṁ‖₁ = 1` while `r ≠ 0`.

For a stagewise path with step lengths `h_k` write `m^h(L)` for its piecewise
linear interpolation in arc length; it is 1-Lipschitz from `[0, Σh_k)` to
`(ℝ^N, ‖·‖₁)`. For CLEAN, `h_k = γ|r_{p_k}| ≤ γ√(2Q_0)`, because
`|r_p| ≤ ‖e‖`.

**Theorem A (small-gain limit in data space; proved).** Let `L*` be the arc
length at which the flow reaches `e_LS` (finite, part (iv)). Take any
sequence of stagewise paths whose largest step tends to zero, CLEAN with
`γ_n → 0` or FS with `ε_n → 0` or any mixture. Then for every `L0 < L*`:

- (i) each path is eventually defined on `[0, L0]`, and every subsequence has
  a further subsequence converging uniformly on `[0, L0]` to a flow;
- (ii) all flows have the same residual `e(L)`; hence the residuals of the
  whole sequence converge, `e(m^h(L)) → e(L)` uniformly on `[0, L0]`, and so
  do the residual dirty images and the misfits;
- (iii) along the flow `Q(L) = Q_0 − ∫_0^L φ(e(ℓ)) dℓ`, and for almost every
  `L` the direction `ṁ = Σ_{j∈A} λ_j sign(r_j) e_j` has weights `λ` that
  minimise `‖Σ_{j∈A} λ_j sign(r_j) a_j‖²` over the simplex on `A = A(m(L))`;
  equivalently `ė` is the minimum-norm element of `−∂φ(e)` (the "lazy"
  selection of a gradient flow), and HTTW's normalised non-negative least
  squares direction;
- (iv) `L* ≤ φ(v)/c_min < ∞`, where `c_min > 0` is the smallest squared
  distance from the origin to `conv{s_j a_j : j ∈ A}` over the finitely many
  sign patterns `(A, s)` whose hull misses the origin.

**Theorem B (model space; proved).** If for almost every `L ∈ [0, L*]` the
atoms `{a_j : j ∈ A(m(L))}` are linearly independent, the flow is unique, it
is HTTW's monotone lasso path (their Definition 3, `ṁ = ml(m)`), and:

- (v) the CLEAN and FS models converge, `m^h(L) → m(L)` uniformly on `[0, L0]`
  for every `L0 < L*`;
- (vi) the converged CLEAN models converge to the end of the path,
  `lim_{γ→0} m_∞^γ = m(L*)`, and the total CLEAN arc length tends to `L*`.

**Proof.**

*Step 1, upper semicontinuity of the pick.* Fix `m` with `r = r(m) ≠ 0`,
`A = A(m)`, and let `ρ = min(φ, φ − max_{j∉A} |r_j|) > 0` (`ρ = φ` if `A` is
everything). If `‖m' − m‖₁ < ρ/2` then `‖r(m') − r‖_∞ < ρ/2`, so every `j ∉ A`
has `|r_j(m')| < φ − ρ/2 < |r_i(m')|` for `i ∈ A`, and the signs on `A` are
unchanged: `A(m') ⊂ A(m)` and `F(m')`'s vertices are vertices of `F(m)`.

*Step 2, limits are flows.* By Arzelà-Ascoli, 1-Lipschitz paths from
`m(0) = 0` have uniformly convergent subsequences on `[0, L0]`; let
`m^n → m̄`. The limit is 1-Lipschitz, hence differentiable almost everywhere.
At `L` with `r(m̄(L)) ≠ 0`, take `ρ` from Step 1 for `m̄(L)`, `n` with
`sup ‖m^n − m̄‖₁ < ρ/8` and largest step `< ρ/8`, and `0 < t < ρ/8`. Every
step of path `n` that overlaps `[L, L + t]` starts within `ρ/2` of `m̄(L)`,
so its direction is a vertex of `F(m̄(L))`, and
`(m^n(L+t) − m^n(L))/t ∈ F(m̄(L))` (a convex combination of those
directions). Let `n → ∞`, then `t → 0`, using that `F(m̄(L))` is closed:
`ṁ̄(L) ∈ F(m̄(L))`. Where `r(m̄(L)) = 0`, `F` is the unit ℓ1 ball and the
inclusion is the Lipschitz bound.

*Step 3, uniqueness in data space.* For two flows with residuals `e1`, `e2`
and residual images `r1`, `r2`, `D = ½‖e1 − e2‖²` is Lipschitz and for almost
every `L`
`D' = −⟨e1 − e2, Σ_p (ṁ1 − ṁ2)_p a_p⟩ = −(r1 − r2)·(ṁ1 − ṁ2)
   = −φ1 − φ2 + r1·ṁ2 + r2·ṁ1 ≤ 0`,
because `r_i·ṁ_i = φ_i` and `r_i·ṁ_j ≤ φ_i ‖ṁ_j‖₁ ≤ φ_i`. So `D` is
non-increasing from `D(0) = 0`, and `e1 ≡ e2`. (This is the monotonicity of
the subdifferential of `‖·‖_∞`; checked in Lean for right-differentiable
curves, `Stagewise.flow_residual_unique`.) Every subsequential limit in Step 2
therefore has the same residual, and the subsequence-of-a-subsequence
argument gives convergence of the whole sequence in data space.

*Step 4, the lazy direction.* `φ(L) = φ(e(L))` and every `|r_j(L)|` are
Lipschitz in `L`. At almost every `L` all of them and `m` are differentiable;
for `j ∈ A(L)` the function `sign(r_j) r_j ≤ φ` touches `φ` at `L`, so their
derivatives agree. Writing `ṁ = Σ_{i∈A} λ_i s_i e_i`
(`s = sign r`, `λ` in the simplex), `d/dL (s_j r_j) = −s_j (Bṁ)_j`, hence
`(G̃λ)_j = −φ'(L)` for every `j ∈ A`, with `G̃_ij = s_i s_j B_ij` on `A`. These
are the Karush-Kuhn-Tucker conditions, with zero multipliers, of the convex
quadratic programme `min λᵀG̃λ` over the simplex on `A`, so `λ` solves it;
that programme is HTTW's (18), whose solution they show to be the normalised
non-negative least-squares coefficients of `r` on the signed tied atoms
(HTTW Definition 2, part 2). `Σ_{i∈A} λ_i s_i a_i` is then the minimum-norm
element of `∂φ(e)`, `φ' = −λᵀG̃λ = −‖ė‖²`, and `dQ/dL = −r·ṁ = −φ`.

*Step 5, finite `L*`.* While `φ > 0`, `0 ∉ conv{s_j a_j : j ∈ A}` (else
`0 = ⟨e, Σλ_j s_j a_j⟩ = Σλ_j |r_j| = φ`), so `λᵀG̃λ ≥ c_min` and
`φ' ≤ −c_min` almost everywhere: `φ` reaches zero by `L = φ(v)/c_min`.
`φ = 0` exactly at `e_LS` (on `v + span{a_p}`). After `L*` Step 3 with the
constant flow keeps the residual at `e_LS`.

*Step 6, the paths reach `L0`.* FS paths are infinite. Suppose CLEAN's total
arc lengths `L_n → ℓ < L*` along a subsequence; extend each path constantly
by its limit `m_∞^{γ_n}` (which exists, clean-theory.md Theorem 3, and has
`r = 0`). A subsequential limit is a flow on `[0, ℓ)` (Step 2) with
`r(m̄(ℓ)) = lim r(m^n(L_n)) = 0`, so by Step 3 `φ(e(ℓ)) = 0` and `ℓ ≥ L*`,
a contradiction.

*Step 7, Theorem B.* Two flows have the same `e`, hence the same `r`, `A` and
signs; at almost every `L` their directions `S λ_1`, `S λ_2` satisfy
`Σ_j (λ_1 − λ_2)_j s_j a_j = 0`, so `λ_1 = λ_2` when the tied atoms are
independent; integrating, the flows coincide. By Step 4 the unique flow
satisfies `ṁ = ml(m)` almost everywhere, which is HTTW's Definition 3, and
the subsequence argument gives (v). For (vi) use clean-theory.md Theorem 3
in its finite-dimensional, exact-greedy form: there is `κ > 0`, independent
of `γ`, with `Q_{k+1} − Q_∞ ≤ (1 − γ(2−γ)κ)(Q_k − Q_∞)`, and
`|r_p| = |⟨e − e_LS, a_p⟩| ≤ √(2(Q − Q_∞))`. The CLEAN arc length after the
step at which the path passes `L0` is therefore at most
`γ√(2ΔQ) Σ_j (1 − γ(2−γ)κ)^{j/2} ≤ 2√(2ΔQ)/((2−γ)κ)` with
`ΔQ = Q_γ(L0) − Q_∞`, which tends by (ii) to `Q(L0) − Q_∞`, itself → 0 as
`L0 → L*`. So `m_∞^γ` is within `o(1)` of `m^γ(L0)`, which converges to
`m(L0)`, which is within `L* − L0` of `m(L*)`. ∎

**What the hypotheses mean for the pixel dictionary.** HTTW state their
results for standardised predictors and argue the `ε → 0` limit only
heuristically, through Efron et al.'s Lemma 11 (the active set changes one
variable at a time) and a unique non-negative least-squares direction. The
proof above needs neither: Theorem A holds for any finite set of unit
vectors in any real inner product space, which is exactly the pixel
dictionary under normalised weights (`‖a_p‖² = Σ_k w_k = 1`). In particular:

- *rank deficiency* (`N > 2M` on the snapshot, `N = 4,096`, `2M = 4,032`):
  irrelevant for Theorem A; `e_LS` is then the zero residual if the atoms
  span the data space. For Theorem B the tied set must stay independent,
  which fails automatically once more atoms are tied than the dimension of
  their span; near `L*` on the snapshot that is possible, and then the
  model limit is determined only up to the null space of the tied atoms
  (open, §8);
- *strong correlations* (neighbouring atoms 0.68-0.93): irrelevant for the
  theorems; they enter only `c_min` and `κ`, hence `L*` and the rate, and the
  conditioning of the tied Gram matrices, which the measurement reports;
- *exact ties* (a disc centred on the grid with a point-symmetric PSF ties
  mirrored pixels exactly; `B` is symmetric under `x → −x`): allowed; the
  flow treats them like any tie, and the argmax tie-break of the discrete
  algorithm disappears in the limit;
- *real inner product*: the weighted visibility space with
  `⟨x, y⟩ = Σ_k w_k (Re x_k Re y_k + Im x_k Im y_k)` is one, and the PSF is
  real and symmetric.

The rate of convergence in `γ` is not proved here (the step-2 compactness
argument gives none); §6 measures it.

## 4. What the implicit objective is, and what it is not

**No pointwise objective.** HTTW's Lemma 2 shows that in general no path
minimises the residual sum of squares among all paths of ℓ1 arc length at
most `L`, for every `L` (the lasso path, run at unit speed, would be the
only candidate, and it is not monotone in general). Their §5 also shows that
FS_0 does not minimise the integrated misfit over monotone paths. So the
small-gain CLEAN model at arc length `L` is not "the minimiser of" any
function of the model alone, and Marsh and Richardson's question, read
literally, has a negative answer for the small-gain limit; for finite gain
the path depends on `γ` (clean-theory.md Theorem 5), so it has none either.

**The local objective (proved, Theorem A(iii) with HTTW Theorem 2).**
Small-gain CLEAN makes, at every arc length, the move that decreases `Q` at
the optimal first-order rate per unit ℓ1 arc length (`dQ/dL = −φ`, the
largest rate any move of unit ℓ1 length can have by Lemma 2), and among
those the one with the smallest curvature, `min λᵀG̃λ`. The lasso makes the
optimal move per unit ℓ1 norm; the two differ when the optimal-norm move
would shrink a coefficient (HTTW Theorem 2 and its proof).

**The data-space objective (proved).** The residual of small-gain CLEAN is
the steepest-descent curve of the peak residual `φ(e) = max_p |⟨e, a_p⟩|` in
the weighted visibility metric, started at the data and run until `e_LS`.
The lasso residual at penalty `λ` is the Euclidean projection of the data
onto the sublevel set `{e ∈ v + span{a_p} : φ(e) ≤ λ}` (lasso duality; FGM
Appendix A.4.1). So the two methods are two ways of driving the same
function `φ` down: by projection (lasso) and by its gradient flow (CLEAN).
They agree exactly when the lasso path is monotone (HTTW §6, the condition
`S_A B_AA⁻¹ S_A 1 ≥ 0` over active sets and signs).

**A minimizing-movement reading (proposed).** The implicit Euler scheme of a
gradient flow of `φ` is `e_{k+1} = argmin_e φ(e) + ‖e − e_k‖²/(2h)`; since
`φ` is the support function of `K = conv{±a_p}`, this is
`e_{k+1} = e_k − P_{hK}(e_k)`: subtract from the current residual the
best-fitting model of ℓ1 norm at most `h`, a lasso with budget `h` on the
current residual. Implicit Euler schemes of convex gradient flows converge
to the flow as `h → 0` (Brezis 1973; Crandall and Liggett 1971; not
re-proved here), so small-gain CLEAN is also the limit of "iterated lasso
with an infinitesimal budget on the current residual, never revisiting what
was already subtracted". This is the sense in which CLEAN is a lasso that
cannot backtrack.

## 5. Consequences

**Gain 1 versus small gain (proved structure; measured size in §6).**
Finite-gain CLEAN is the explicit Euler scheme of the flow of `½φ²` with step
`γ` (§2). Gain 1 is the exact minimiser of `Q` along one atom. When a pixel's
neighbours correlate at 0.68-0.93 with it, putting the full `r_p` on `p`
reduces the residual at every neighbour by `B_pq r_p`, more than the flow
would put there, because the flow advances all tied pixels together along
the non-negative least-squares direction. The overshoot leaves negative
residuals that are later picked with negative sign: arc length is spent and
undone. Lemma 3 makes this measurable: `L − ‖m‖₁` is twice the backtracked
flux, and §6 reports it per gain together with the arc length spent on
negative picks.

**Non-negativity is not implied (proved negative statement).** The flow is
monotone in the expanded dictionary only; pixel `j` acquires negative flux
exactly while `−r_j` is the global peak of `|r|`. E6 of clean-theory.md
already shows CLEAN at gain 0.01 on the snapshot-natural PSF reaching −0.34 of
the peak on a positive Gaussian disc, so the small-gain limit is not
non-negative on every PSF. What small gain removes is the *overshoot*
mechanism, not negativity as such; the measured negative arc length (§6)
separates the two.

**Schwarz's W > R (proved, under Theorem B's hypothesis).** With more pixels
than independent data every exact fit belongs to an affine family
(clean-theory.md Theorem 5). The small-gain limit selects one member, the end
point `m(L*)` of the monotone lasso. HTTW note that this end point is unique
by construction but uncharacterised; it is in general not the minimum-ℓ1
exact fit, which is where the lasso ends as `λ → 0`. `‖m(L*)‖₁ ≤ L*`, with
equality iff no pixel ever backtracks. The gain dependence of the converged
models seen in E6 is the Euler error of the scheme and vanishes as `γ → 0`
(Theorem B(vi)); §6 measures how fast.

## 6. Measurements

Pending: filled in from `clean_implicit` (FS_ε, CLEAN for six gains, lasso
and non-negative lasso, matched-misfit comparisons, the monotonicity test of
the lasso path, tied-set sizes) on the E6 disc and the E1 six-source scene,
noiseless, track-uniform and snapshot-natural sampling.

## 7. Lean

Pending: `formal/RangFormal/Stagewise.lean`.

## 8. Open

- The rate of convergence of CLEAN(γ) to the flow (expected `O(γ)` in data
  space away from tie changes; not proved).
- Model uniqueness when more atoms are tied than their span's dimension
  (possible near `L*` when `N > 2M`).
- Whether `m(L*)` admits any variational characterisation (HTTW could not
  give one; none is offered here).
