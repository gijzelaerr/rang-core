# What CLEAN minimises: small-gain CLEAN is forward stagewise, and its limit is the monotone lasso

Research question 1 of the CLEAN programme ([clean-theory.md](clean-theory.md)),
started 2026-10-30 on branch `clean-implicit-objective`. Question: what
objective does Högbom CLEAN implicitly minimise (Marsh and Richardson 1987,
A&A 182, 174, "The objective function implicit in the CLEAN algorithm"), and
why do small loop gains give smooth extended-emission models while gain 1
gives striped, negative ones (Schwarz 1984 §3.3b; E6 of clean-theory.md)?
Every claim is labelled **proved** (a complete argument here, i.e.
proposed and argued but not machine-checked), **checked** (machine-checked
in Lean), **implemented**, **measured**, or **conjectured**. Code:
[`core/examples/clean_implicit.rs`](../core/examples/clean_implicit.rs);
Lean: [`formal/RangFormal/Stagewise.lean`](../formal/RangFormal/Stagewise.lean)
(and, for the companion note, `Separation.lean` and `Clark.lean`, §7);
archive: [`results/clean-implicit-objective.json`](results/clean-implicit-objective.json);
full tables of the run: `outputs/clean-implicit-20261030/stdout.md` (ignored).

Sources read in full for this note: Hastie, Taylor, Tibshirani and Walther
(2007), "Forward stagewise regression and the monotone lasso", Electronic
Journal of Statistics 1, 1-29 (arXiv:0705.0269; cited as HTTW), and Freund,
Grigas and Mazumder (2017), "A new perspective on boosting in linear
regression via subgradient optimization and relatives" (arXiv:1505.04243,
2015; later in the Annals of Statistics; cited as FGM). Marsh and Richardson
(1987) was not retrievable from this host (ADS redirects to a page that returned
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
5. **Measured (MeerKAT track-uniform and snapshot-natural PSFs, noiseless
   Gaussian disc and six point sources, §6).** At matched misfit the CLEAN
   model approaches the `FS_ε` reference as `γ` falls from 1 to 0.003: by a
   factor of 22-64 in rms on the disc and 280-2,400 on the point sources.
   The fitted rate between `γ = 0.03` and `0.003` is `γ^0.76` (track) and
   `γ^0.86` (snapshot) for the disc model, `γ^1.0-1.4` for the point-source
   model, and about `γ^0.9` for the residual where the reference is accurate
   enough to tell. The lasso path is far from monotone on the disc (5,836
   zero crossings down to `Q/Q_0 = 1e-5` on the track, path arc length 64
   times the final ℓ1 norm), so there lasso and small-gain CLEAN differ (rms
   0.13-0.25 of the peak); on the track six-source scene the lasso path is
   monotone and the two agree to 3e-7, as Hastie et al.'s theory requires.
   For the disc the small-gain model is much closer to the sky than the
   lasso (rms error 0.041 against 0.19 on the track); for the six point
   sources on the snapshot PSF the lasso and gain-1 CLEAN recover the sky
   (rms 1e-4 at `Q/Q_0 = 1e-5`) and small-gain CLEAN does not (0.0095, with
   a −0.11 pixel).

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
  (§6 measures near-tied sets; open, §10);
- *strong correlations* (neighbouring atoms 0.68-0.93): irrelevant for the
  theorems; they enter only `c_min` and `κ`, hence `L*` and the rate, and the
  conditioning of the tied Gram matrices; §6 finds the near-tied sets of the
  disc numerically dependent from `Q/Q_0 ≈ 1e-2` on the track, so for
  extended emission Theorem B's hypothesis is not met and model convergence
  there is measured, not proved;
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
(Theorem B(vi)); §6 measures how fast, and finds the snapshot's six point
sources ending in a non-sparse fit (ℓ1 norm 4.26 against the sky's 3.50,
with a negative pixel) while the lasso ends on the sky.


## 6. Measurements (2026-10-30, Windows workstation, one run of `clean_implicit`, 36.5 s)

**Setup (implemented).** The example reuses the geometry of `clean_theory`:
64 × 64 pixels of 2″, MeerKAT at 1.4 GHz and declination −30°, the
**track-uniform** configuration (13 hour angles over ±2 h, uniform weights,
`M = 26,208`, on-grid coherence 0.68) and the **snapshot-natural** one
(`M = 2,016`, coherence 0.93, `N = 4,096 > 2M = 4,032`, Schwarz's `W > R`).
Scenes, noiseless: the E6 Gaussian disc (FWHM 12 px, peak 1, ℓ1 norm 163.2)
and the E1 six-source scene with E1's seed and positions, its noise omitted
(fluxes 1, 0.8, 0.7, 0.5, 0.3, 0.2; ℓ1 norm 3.5). Everything runs in the
image domain on the exact PSF; `Q` is tracked by the exact step identity of
Lemma 1 and agrees with `Q_0 − ½ m·(d + r)` to 4e-8 relative at every
snapshot. Paths: `FS_ε` at `ε = 3e-5, 1.2e-4, 4.8e-4` times the dirty peak
(the finest is the reference, written FS₀ below; the coarser two measure its
own discretisation error), CLEAN at `γ = 1, 0.3, 0.1, 0.03, 0.01, 0.003`, and
the **exact** lasso and non-negative lasso paths by homotopy (LARS with the
lasso modification; a Cholesky factor of the active Gram matrix kept by
appends and Givens deletions). Every path is cut at matched misfit
`Q/Q_0 ∈ {0.1, 0.01, 0.001}` (the task) and `{1e-4, 1e-5}` (deeper, where E6
saw negative small-gain models), the crossing located inside the step or
homotopy segment that crosses it; the lasso solutions there satisfy the
optimality conditions to 2e-12 of `λ`. A first implementation of the lasso
by cyclic coordinate descent with a 1e-9 tolerance was abandoned after it
spent about nine minutes on the first case without finishing (correlated
atoms make coordinate descent crawl); the homotopy takes 4.5 s for the
hardest path.

**Convergence of CLEAN to FS₀ (measured; Theorem A).** Root-mean-square
difference over all 4,096 pixels at `Q/Q_0 = 1e-3`, model (units of the disc
peak, or of the brightest source) / residual image, and the log-log slope
between `γ = 0.03` and `0.003`:

| case | γ = 1 | 0.3 | 0.1 | 0.03 | 0.01 | 0.003 | slope, model / residual | FS at 4ε |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| track, disc | 0.287 / 2.7e-2 | 0.110 / 2.5e-3 | 0.062 / 7.8e-4 | 0.027 / 2.4e-4 | 0.012 / 8.7e-5 | 0.0047 / 2.9e-5 | 0.76 / 0.92 | 1.4e-3 / 7.7e-5 |
| track, six sources | 1.1e-3 / 2.3e-3 | 8.2e-5 / 1.7e-4 | 2.0e-5 / 4.1e-5 | 5.1e-6 / 1.0e-5 | 2.3e-6 / 4.6e-6 | 5.3e-7 / 1.1e-6 | 0.98 / 0.99 | 1.2e-6 / 2.4e-6 |
| snapshot, disc | 0.400 / 0.36 | 0.443 / 0.37 | 0.274 / 0.091 | 0.119 / 0.028 | 0.049 / 0.010 | 0.016 / 0.0064 | 0.86 / 0.65 | 2.2e-3 / 1.0e-3 |
| snapshot, six sources | 1.0e-2 / 4.7e-3 | 4.0e-3 / 1.2e-3 | 1.9e-3 / 2.3e-3 | 4.9e-4 / 1.4e-3 | 1.2e-4 / 2.0e-4 | 1.9e-5 / 1.1e-5 | 1.42 / 2.08 | 7.4e-6 / 2.3e-5 |

The same holds at every level: from `γ = 1` to `0.003` the model difference
falls by 61-64× (track disc), 22-59× (snapshot disc), 660-2,400× (track six)
and 280-690× (snapshot six). The arc length at matched misfit converges as
Theorem A(iii) requires (`Q(L)` is one function): track disc at `1e-3`,
`L = 166.84` (γ = 1), 154.88, 154.82, 154.809, 154.808, 154.808 against FS₀'s
154.808. Below `Q/Q_0 = 1e-4` the residual comparison is limited by the
reference itself: on the track disc at `1e-5` FS at 4ε differs from FS₀ by
8.5e-5 in the residual, CLEAN at 0.003 by 2.3e-5. Small-gain CLEAN is there
the better discretisation of the flow, because its step shrinks with the
residual while FS's does not.

**What the paths look like (measured).** At matched misfit; `L` is the ℓ1
arc length of each path (for the lasso, of the exact lasso path), "negative
arc" the arc length spent on steps against a negative residual, "error" the
rms difference from the true sky:

| case, Q/Q_0 | method | L | ‖m‖₁ | most negative | negative arc | error |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| track disc, 1e-3 | FS₀ | 154.81 | 154.81 | 0 | 0 | 0.041 |
| | CLEAN γ = 1 | 166.84 | 165.17 | −0.325 | 3.00 | 0.296 |
| | CLEAN γ = 0.1 | 154.82 | 154.82 | 0 | 0 | 0.053 |
| | CLEAN γ = 0.01 | 154.81 | 154.81 | 0 | 0 | 0.037 |
| | lasso | 5,770.9 | 154.80 | 0 | – | 0.193 |
| snapshot disc, 1e-3 | FS₀ | 159.76 | 159.07 | 0 | 0.34 | 0.103 |
| | CLEAN γ = 1 | 494.8 | 196.4 | −1.600 | 166.0 | 0.401 |
| | CLEAN γ = 0.1 | 164.23 | 163.84 | −1.236 | 2.11 | 0.307 |
| | CLEAN γ = 0.01 | 160.39 | 159.18 | 0 | 0.61 | 0.102 |
| | lasso | 6,082.0 | 155.62 | 0 | – | 0.222 |
| snapshot disc, 1e-5 | FS₀ | 180.76 | 166.53 | −0.223 | 8.80 | 0.102 |
| | CLEAN γ = 1 | 580.7 | 254.5 | −1.600 | 208.8 | 0.360 |
| | CLEAN γ = 0.01 | 181.56 | 166.97 | −0.341 | 9.20 | 0.101 |
| | lasso | 11,294.7 | 162.30 | 0 | – | 0.217 |
| track six, 1e-3 | FS₀, CLEAN γ ≤ 0.3, lasso | 3.38 | 3.38 | 0 | 0 | 0.0008 |
| snapshot six, 1e-5 | FS₀ | 4.27 | 4.26 | −0.113 | 0.39 | 0.0095 |
| | CLEAN γ = 1 | 4.66 | 3.50 | 0 | 0.58 | 0.0001 |
| | CLEAN γ = 0.01 | 4.28 | 4.27 | −0.114 | 0.39 | 0.0096 |
| | lasso | 4.24 | 3.49 | 0 | – | 0.0001 |

**Is the lasso path monotone here? (measured, exactly.)** Down to
`Q/Q_0 = 1e-5`; a segment "shrinks" when some active coefficient heads
towards zero, `s_j (B_AA⁻¹ s)_j < 0`, which is HTTW's condition (36) failing
on that active set:

| case | events | joins | zero crossings | shrinking segments | first at Q/Q_0 | path arc / final ‖m‖₁ | monotone |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| track, disc | 12,167 | 6,332 | 5,836 | 12,161 | 0.996 | 64.1 | no |
| track, six sources | 5 | 6 | 0 | 0 | – | 1.000 | yes |
| snapshot, disc | 7,259 | 3,757 | 3,503 | 7,256 | 0.932 | 69.6 | no |
| snapshot, six sources | 9 | 10 | 0 | 5 | 0.382 | 1.217 | no |

The non-negative lasso path is identical in all four cases (the lasso never
produced a negative coefficient on these positive skies). So the monotone
lasso equals the lasso only on the track six-source scene, where FS₀ and the
lasso agree to 3e-7 (the reference's own precision) at every level, as HTTW
§6 predicts. Everywhere else they differ, and the difference is large.

**Findings (measured).**

- *Small-gain CLEAN is the monotone lasso, not the lasso.* On the disc the
  lasso is sparse (324 active pixels at `1e-3` on the track) and hops: its
  path is 37-70 times longer than its norm, and its model is 0.13-0.25 of the
  peak (rms) away from FS₀ and 0.14-0.25 from the sky. FS₀ and small-gain
  CLEAN keep the model contiguous and are 0.041 (track) and 0.10 (snapshot)
  from the sky. The lasso has the smallest ℓ1 norm at every matched misfit,
  as it must (a sanity check of the solver), by 0.01-3 % against FS₀ on the
  disc and up to 18 % on the snapshot six-source scene.
- *Gain 1 overshoots.* On the snapshot disc gain 1 spends 166 of its 495
  units of arc length on negative picks by `Q/Q_0 = 1e-3` (FS₀: 0.34 of 160)
  and leaves a −1.60 pixel; `γ = 0.3` still spends 35, `γ = 0.1` 2.1. On the
  track disc, where neighbouring atoms correlate at most 0.68, every gain up
  to 0.3 has zero negative arc to `1e-5` and gain 1 up to 7.3.
- *Small gain does not guarantee non-negativity.* FS₀ itself goes negative on
  the snapshot PSF: −0.22 on the disc from `Q/Q_0 = 1e-4`, −0.11 on the six
  sources at `1e-5`; small-gain CLEAN follows it (−0.34 at `γ = 0.01` and
  0.003, the E6 value, against FS₀'s −0.22, with an rms model difference of
  0.017). §5's
  negative statement is therefore realised on MeerKAT sampling.
- *Point sources on the coherent snapshot favour sparsity.* At `1e-5` FS₀
  spreads the six sources over neighbouring pixels (‖m‖₁ 4.26 against 3.50,
  error 0.0095), while the lasso and gain-1 CLEAN recover the sky to 1e-4.
  This is Schwarz's `W > R` selection at work: FS₀ picks its own exact fit
  (§5), which here is not the sparse one. Small gain is the right choice for
  extended emission and the wrong one for isolated point sources on a PSF
  with 0.93 neighbour correlation.
- *Tied sets and Theorem B's hypothesis.* The pixels within `2ε` of the peak
  on the FS₀ path number 127, 240 and 549 on the track disc at `0.1, 0.01,
  1e-3`, and the smallest eigenvalue of their Gram matrix falls from 7.6e-4
  to 3.6e-7 and 5e-14 (dependent to working precision); on the snapshot disc
  24-119 pixels with eigenvalues 1.6e-4 to 6.7e-3 down to `1e-4`, then 844
  (dependent) at `1e-5`; on the six sources 5-6 pixels with eigenvalue 0.93
  on the track at every level and 7-13 with 0.04-0.06 on the snapshot down to
  `1e-3`, then 67 and 900 (dependent). At `4ε` the counts are larger (for
  example 213 against 80), so they are tolerance-dependent upper bounds on
  the flow's exact tied set, not the set itself. Theorem B's independence
  hypothesis is thus confirmed only for the sparse scene on the track; for
  extended emission it is plausibly violated from `Q/Q_0 ≈ 1e-2`, and the
  model convergence measured there lies outside what is proved
  (**conjectured**: the model limit is unique anyway). A likely reason for
  the dependence (**proposed**, not measured further): a contiguous patch of
  hundreds of pixels at 2.8 pixels per fringe has Fourier content between
  the longest baseline and the pixel Nyquist frequency, where nothing is
  sampled, so its Gram matrix has near-null vectors.

## 7. Lean (checked)

`formal/RangFormal/Stagewise.lean` (this note): `misfit_add_eq` (exact misfit
after any move), `misfit_add_ge` (ℓ1 steepest descent, Lemma 2),
`misfit_add_single` (Lemma 1), `misfit_stagewise_step` (a signed step of
ℓ1 size `ε` changes `Q` by `−ε|r_p| + ε²/2`), `l1_stagewise_step`,
`step_eq_stagewise` and `l1_step_sub` (a CLEAN step is the stagewise step of
length `|γ||r_p|`), `l1_iterate_le_arc` (Lemma 3), `subgradient_monotone`
(monotonicity of the ℓ∞ subdifferential) and `flow_residual_unique` (Step 3
of Theorem A: two right-differentiable residual curves driven by
subgradients of the peak residual from the same start coincide; proved with
Mathlib's `image_le_of_deriv_right_le_deriv_boundary`). Not formalised: the
compactness and almost-everywhere arguments of Steps 2 and 4-7, which need
Arzelà-Ascoli and Rademacher's theorem in a form Mathlib does not package
for this use.

For [clean-theory.md](clean-theory.md), whose §3 listed them as not
formalised: `Separation.lean` proves Proposition 4' as
`l1_le_of_offdiag_le` (the Neumann-series bound in ℓ1 form, without a
matrix inverse), `colsum_le_of_separated` (at most one source within `d/2`
of any pixel, in any pseudometric space), `erc_lt_one_of_separated`
(`‖B_SS⁻¹ B_{S,q}‖₁ < 1`), `exists_erc_solution` (`B_SS` is invertible) and
`pick_in_support_of_erc` (for a symmetric `B` the argmax then stays on the
sources); `Clark.lean` proves Theorem 6 as `clark_descends_iff` (descent iff
`r_p/r̃_p > γ/2`), `truncation_error_le` (`‖r − r̃‖_∞ ≤ f Σ|c_k|`), `dirty_add`,
`clark_rule_descends` and `clark_minor_cycle_descends` (the provable
minor-cycle rule, end to end). `RangFormal/Audit.lean` prints the axioms of
33 theorems (13 before, 20 new); all rest on `propext`, `Classical.choice`
and `Quot.sound` only.

## 8. Novelty, as AGENTS.md asks

Known: CLEAN is matching pursuit (Mallat and Zhang; clean-theory.md), which
FGM identify with LS-Boost(ε); FS and LS-Boost are subgradient methods on the
peak residual (FGM Proposition 3.2); FS₀ is the monotone lasso, with the
`ε → 0` limit argued heuristically (HTTW Theorem 1 and Proposition 1); the
gradient-flow theory of convex functions is classical (Brezis 1973). New
here, as far as the two papers read and the earlier literature search show:
a complete proof that small-gain CLEAN and `FS_ε` share one limit, unique in
data space for any dictionary (including rank-deficient ones), equal to the
gradient flow of the peak residual with its minimum-norm (HTTW) direction,
and the monotone lasso in model space under an independence condition; its
consequences for CLEAN (the negative answer to Marsh and Richardson's
question in pointwise form, the local objective, the `W > R` selection); the
measurement on MeerKAT PSFs that the lasso path is far from monotone for
extended emission, so small-gain CLEAN and the lasso are different
estimators there; and the Lean proofs. No claim of better imaging or lower
cost is made: this is an understanding result.

## 9. Reproduction

From the repository root (Rust 1.93 or later):

```bash
cargo run --release --manifest-path core/Cargo.toml --example clean_implicit -- outputs/clean-implicit-20261030
```

```bash
cd formal && lake build
```

The example writes `clean-implicit-objective.json` (copied to
`research/results/`) and prints every table above; the run is
deterministic (two runs gave identical output apart from timings). Run
time 36.5 s on the Windows workstation (track disc 28.7 s, of which 9 s is
the two homotopies and most of the rest the Gram eigenvalues of the tied
sets; the other cases 0.7-3.9 s). Lean timings are in
`research/tool-timings.md`.

## 10. Open

- The rate of convergence (measured `γ^0.76-1.4` for the model and about
  `γ^0.9` for the residual; not proved).
- Model uniqueness when the tied atoms are dependent, which the
  measurements suggest happens for extended emission (§6).
- A characterisation of the end point `m(L*)` (HTTW could not give one).
- Noise: with noisy data the flow runs to the least-squares residual, so
  the stopping arc length is the regulariser; how to choose it.
- Practice (**proposed**): the gain is a discretisation parameter of one
  flow. A path-following CLEAN that takes the non-negative least-squares
  direction on the tied set (HTTW's Algorithm 2b) would compute the `γ → 0`
  limit exactly, event by event; whether that is cheaper than small-gain
  CLEAN on real images, and whether Clark and Cotton-Schwab minor cycles
  approximate the same flow, are unmeasured.
