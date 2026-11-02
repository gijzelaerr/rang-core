/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.Clark

/-!
# What the gridder's arithmetic licenses

The companion of `research/gridder-theory.md`. A proof cannot make a gridder
faster; these statements say what a cheaper computation may rely on.

* Exact adjoints (`grid_eq_dirty`, `grid_degrid_eq_gram`, `gram_quadratic_nonneg`):
  if the gridder is the exact adjoint of the degridder, however approximate
  either is, the beam it forms is the Gram matrix of the *approximate* atoms,
  the residual is that of those atoms, and `dirty_update` is the
  visibility-free law `r(m + d) = r(m) − Aᴴ A d`. `misfit_add_single_general`
  and `misfit_step_general` give the one-step law with no unit-norm assumption.
* Perturbation (`residual_perturbation`, `dirty_perturbation`,
  `misfit_perturbation`, `gram_residual_bound`, `gram_quadratic_bound`): an
  operator error gives stated bounds on the residual image and on the misfit.
* Descent (`working_step_descends`, `operator_step_descends`): a step taken on a
  residual from an approximate normal operator lowers the misfit of the exact
  atoms when `(1 − γ/2) |r̃_p| > η ‖m‖₁`.
* The w-node sum (`gram_eq_node_sum`, `gram_node_sum_error`): the finite-sum
  identity behind the visibility-free operator, and its error from the error of
  the expansion in `w`.
* Toeplitz embedding (`sub_cast_injective`, `exists_embedding`, `dft_circConv`,
  `embedded_convolution`): the differences of `n` pixels fit on `ZMod (2n)`, and
  the convolution there is a product of DFTs.

Not proved here: the bound on the expansion itself (measured in Rust), the
gridder's own accuracy, and Poisson summation or any discrete aliasing identity.
-/

open scoped InnerProductSpace ComplexConjugate
open Finset

namespace Clean

variable {E : Type*} [NormedAddCommGroup E] [InnerProductSpace ℝ E]
variable {ι : Type*} [Fintype ι] [DecidableEq ι]

/-! ## Exact adjoints -/

section Adjoint

/-- The atom of pixel `i` under the degridder `A`: the image of a unit source. -/
def atomsOf (A : (ι → ℝ) →ₗ[ℝ] E) (i : ι) : E := A (Pi.single i 1)

/-- A linear degridder is the sum over its atoms. -/
theorem degrid_eq_sum (A : (ι → ℝ) →ₗ[ℝ] E) (m : ι → ℝ) :
    A m = ∑ i, m i • atomsOf A i := by
  conv_lhs => rw [← Finset.univ_sum_single m]
  rw [map_sum]
  refine Finset.sum_congr rfl fun i _ => ?_
  have h : (Pi.single i (m i) : ι → ℝ) = m i • Pi.single i 1 := by
    ext j
    by_cases hj : j = i
    · subst hj; simp
    · simp [hj]
  rw [h, map_smul, atomsOf]

variable (A : (ι → ℝ) →ₗ[ℝ] E) (Ah : E →ₗ[ℝ] (ι → ℝ))

/-- The gridder reads the inner product with the atoms when it is the exact
adjoint of the degridder. -/
theorem grid_apply (hadj : ∀ x e, ⟪A x, e⟫_ℝ = ∑ i, x i * Ah e i) (e : E) (p : ι) :
    Ah e p = ⟪e, atomsOf A p⟫_ℝ := by
  have h := hadj (Pi.single p 1) e
  rw [real_inner_comm] at h
  rw [atomsOf, h, Finset.sum_eq_single p]
  · simp
  · intro i _ hi; simp [hi]
  · simp

/-- The image of the residual visibilities is the residual dirty image of the
approximate atoms. -/
theorem grid_eq_dirty (hadj : ∀ x e, ⟪A x, e⟫_ℝ = ∑ i, x i * Ah e i) (v : E) (m : ι → ℝ) (p : ι) :
    Ah (v - A m) p = dirty v (atomsOf A) m p := by
  rw [grid_apply A Ah hadj, dirty, residual, degrid_eq_sum A m]

/-- The beam the gridder and degridder form is the Gram matrix of the approximate
atoms. -/
theorem grid_degrid_eq_gram (hadj : ∀ x e, ⟪A x, e⟫_ℝ = ∑ i, x i * Ah e i) (j q : ι) :
    Ah (A (Pi.single j 1)) q = ⟪atomsOf A j, atomsOf A q⟫_ℝ := by
  rw [grid_apply A Ah hadj]
  rfl

/-- That beam is symmetric. -/
theorem grid_degrid_symm (hadj : ∀ x e, ⟪A x, e⟫_ℝ = ∑ i, x i * Ah e i) (j q : ι) :
    Ah (A (Pi.single j 1)) q = Ah (A (Pi.single q 1)) j := by
  rw [grid_degrid_eq_gram A Ah hadj, grid_degrid_eq_gram A Ah hadj, real_inner_comm]

omit [DecidableEq ι] in
/-- The Gram matrix of any atoms is positive semidefinite. -/
theorem gram_quadratic_nonneg (a : ι → E) (c : ι → ℝ) :
    0 ≤ ∑ i, ∑ j, c i * c j * ⟪a i, a j⟫_ℝ := by
  have h : ∑ i, ∑ j, c i * c j * ⟪a i, a j⟫_ℝ = ‖∑ i, c i • a i‖ ^ 2 := by
    rw [← real_inner_self_eq_norm_sq, sum_inner]
    refine Finset.sum_congr rfl fun i _ => ?_
    rw [inner_sum]
    refine Finset.sum_congr rfl fun j _ => ?_
    rw [inner_smul_left, inner_smul_right, conj_trivial]
    ring
  rw [h]
  positivity

/-- The visibility-free law: the residual after a model change is the old residual
minus the normal operator on the change. -/
theorem dirty_update (hadj : ∀ x e, ⟪A x, e⟫_ℝ = ∑ i, x i * Ah e i)
    (v : E) (m d : ι → ℝ) (p : ι) :
    dirty v (atomsOf A) (m + d) p = dirty v (atomsOf A) m p - Ah (A d) p := by
  rw [← grid_eq_dirty A Ah hadj, ← grid_eq_dirty A Ah hadj, map_add]
  have : v - (A m + A d) = (v - A m) - A d := by abel
  rw [this, map_sub, Pi.sub_apply]

end Adjoint

/-- The one-step law for atoms of any norm: approximate atoms are not exactly unit. -/
theorem misfit_add_single_general (v : E) (a : ι → E) (m : ι → ℝ) (p : ι) (c : ℝ) :
    misfit v a (m + Pi.single p c) =
      misfit v a m - c * dirty v a m p + c ^ 2 * ‖a p‖ ^ 2 / 2 := by
  rw [misfit_add_eq, sum_single_smul, norm_smul, Real.norm_eq_abs, mul_pow, sq_abs]
  congr 2
  rw [Finset.sum_eq_single p]
  · simp
  · intro i _ hi; simp [hi]
  · simp

/-- A CLEAN step on atoms with `‖a_p‖² = 1 + η`. -/
theorem misfit_step_general (v : E) (a : ι → E) (γ η : ℝ) (m : ι → ℝ) (p : ι)
    (hp : ‖a p‖ ^ 2 = 1 + η) :
    misfit v a (m + Pi.single p (γ * dirty v a m p)) =
      misfit v a m - γ * (2 - γ * (1 + η)) / 2 * dirty v a m p ^ 2 := by
  rw [misfit_add_single_general, hp]
  ring

/-! ## Perturbation -/

section Perturbation

omit [DecidableEq ι] in
/-- Atoms within `ε` give residual visibilities within `ε ‖m‖₁`. -/
theorem residual_perturbation (v : E) (a b : ι → E) (m : ι → ℝ) {ε : ℝ}
    (h : ∀ i, ‖a i - b i‖ ≤ ε) :
    ‖residual v a m - residual v b m‖ ≤ ε * l1 m := by
  have : residual v a m - residual v b m = ∑ i, m i • (b i - a i) := by
    simp only [residual, smul_sub, Finset.sum_sub_distrib]
    abel
  rw [this]
  refine (norm_sum_le _ _).trans ?_
  rw [l1, Finset.mul_sum]
  refine Finset.sum_le_sum fun i _ => ?_
  rw [norm_smul, Real.norm_eq_abs, mul_comm, norm_sub_rev]
  exact mul_le_mul_of_nonneg_right (h i) (abs_nonneg _)

omit [DecidableEq ι] in
/-- The residual image of perturbed atoms. -/
theorem dirty_perturbation (v : E) (a b : ι → E) (m : ι → ℝ) (p : ι) {ε : ℝ}
    (h : ∀ i, ‖a i - b i‖ ≤ ε) :
    |dirty v a m p - dirty v b m p| ≤
      ‖residual v a m‖ * ε + ε * l1 m * ‖b p‖ := by
  have key : dirty v a m p - dirty v b m p =
      ⟪residual v a m, a p - b p⟫_ℝ + ⟪residual v a m - residual v b m, b p⟫_ℝ := by
    simp only [dirty, inner_sub_right, inner_sub_left]
    ring
  rw [key]
  refine (abs_add_le _ _).trans (add_le_add ?_ ?_)
  · refine (abs_real_inner_le_norm _ _).trans ?_
    exact mul_le_mul_of_nonneg_left (h p) (norm_nonneg _)
  · refine (abs_real_inner_le_norm _ _).trans ?_
    exact mul_le_mul_of_nonneg_right (residual_perturbation v a b m h) (norm_nonneg _)

omit [DecidableEq ι] in
/-- The misfit of perturbed atoms. -/
theorem misfit_perturbation (v : E) (a b : ι → E) (m : ι → ℝ) {ε : ℝ}
    (h : ∀ i, ‖a i - b i‖ ≤ ε) :
    |misfit v a m - misfit v b m| ≤
      ε * l1 m * (‖residual v a m‖ + ‖residual v b m‖) / 2 := by
  have hdiff := residual_perturbation v a b m h
  have htri : |‖residual v a m‖ - ‖residual v b m‖| ≤ ε * l1 m :=
    (abs_norm_sub_norm_le _ _).trans hdiff
  have key : misfit v a m - misfit v b m =
      (‖residual v a m‖ - ‖residual v b m‖) * (‖residual v a m‖ + ‖residual v b m‖) / 2 := by
    simp only [misfit]
    ring
  rw [key, abs_div, abs_mul, abs_of_nonneg (add_nonneg (norm_nonneg _) (norm_nonneg _)),
    abs_of_pos (by norm_num : (0 : ℝ) < 2)]
  have := mul_le_mul_of_nonneg_right htri
    (add_nonneg (norm_nonneg (residual v a m)) (norm_nonneg (residual v b m)))
  linarith

omit [DecidableEq ι] in
/-- A normal operator within `η` entrywise gives a residual within `η ‖m‖₁`. -/
theorem gram_residual_bound (G H : ι → ι → ℝ) (d m : ι → ℝ) {η : ℝ}
    (h : ∀ i j, |G i j - H i j| ≤ η) (p : ι) :
    |(d p - ∑ j, m j * G p j) - (d p - ∑ j, m j * H p j)| ≤ η * l1 m := by
  have : (d p - ∑ j, m j * G p j) - (d p - ∑ j, m j * H p j) =
      ∑ j, m j * (H p j - G p j) := by
    simp only [mul_sub, Finset.sum_sub_distrib]
    ring
  rw [this]
  refine (Finset.abs_sum_le_sum_abs _ _).trans ?_
  rw [l1, Finset.mul_sum]
  refine Finset.sum_le_sum fun j _ => ?_
  rw [abs_mul, mul_comm, abs_sub_comm]
  exact mul_le_mul_of_nonneg_right (h p j) (abs_nonneg _)

omit [DecidableEq ι] in
/-- The visibility-free misfit `Q₀ − ⟨d, m⟩ + ½⟨m, H m⟩` is within `η ‖m‖₁² / 2` of
the misfit with `G`. -/
theorem gram_quadratic_bound (G H : ι → ι → ℝ) (d m : ι → ℝ) (Q0 : ℝ) {η : ℝ}
    (h : ∀ i j, |G i j - H i j| ≤ η) :
    |(Q0 - ∑ i, d i * m i + (∑ i, ∑ j, m i * m j * G i j) / 2) -
        (Q0 - ∑ i, d i * m i + (∑ i, ∑ j, m i * m j * H i j) / 2)| ≤ η * l1 m ^ 2 / 2 := by
  have hη : 0 ≤ η ∨ IsEmpty ι := by
    by_cases he : IsEmpty ι
    · exact Or.inr he
    · obtain ⟨i⟩ := not_isEmpty_iff.mp he
      exact Or.inl ((abs_nonneg _).trans (h i i))
  have key : (Q0 - ∑ i, d i * m i + (∑ i, ∑ j, m i * m j * G i j) / 2) -
      (Q0 - ∑ i, d i * m i + (∑ i, ∑ j, m i * m j * H i j) / 2) =
      (∑ i, ∑ j, m i * m j * (G i j - H i j)) / 2 := by
    simp only [mul_sub, Finset.sum_sub_distrib]
    ring
  rw [key, abs_div, abs_of_pos (by norm_num : (0 : ℝ) < 2)]
  have hb : |∑ i, ∑ j, m i * m j * (G i j - H i j)| ≤ η * l1 m ^ 2 := by
    calc |∑ i, ∑ j, m i * m j * (G i j - H i j)|
        ≤ ∑ i, ∑ j, |m i * m j * (G i j - H i j)| :=
          (Finset.abs_sum_le_sum_abs _ _).trans
            (Finset.sum_le_sum fun i _ => Finset.abs_sum_le_sum_abs _ _)
      _ ≤ ∑ i, ∑ j, |m i| * |m j| * η := by
          refine Finset.sum_le_sum fun i _ => Finset.sum_le_sum fun j _ => ?_
          rw [abs_mul, abs_mul]
          exact mul_le_mul_of_nonneg_left (h i j) (by positivity)
      _ = η * l1 m ^ 2 := by
          rw [l1, sq, Finset.sum_mul_sum, Finset.mul_sum]
          refine Finset.sum_congr rfl fun i _ => ?_
          rw [Finset.mul_sum]
          refine Finset.sum_congr rfl fun j _ => ?_
          ring
  linarith

end Perturbation

/-! ## Descent on an approximate residual -/

omit [Fintype ι] in
/-- A step of size `γ t` taken on a working value within `e` of the exact residual
lowers the misfit when `(1 − γ/2) |t| > e`. -/
theorem working_step_descends [Fintype ι] (v : E) (a : ι → E) (m : ι → ℝ) (p : ι)
    (hp : ‖a p‖ = 1) {γ t e : ℝ} (h0 : 0 < γ) (herr : |dirty v a m p - t| ≤ e)
    (hmargin : e < (1 - γ / 2) * |t|) :
    misfit v a (m + Pi.single p (γ * t)) < misfit v a m := by
  rw [misfit_add_single v a m p _ hp]
  set r := dirty v a m p with hr
  have hee : 0 ≤ e := (abs_nonneg _).trans herr
  have ht : 0 < |t| := by
    by_contra hc
    have ht0 : |t| = 0 := le_antisymm (not_lt.mp hc) (abs_nonneg _)
    rw [ht0, mul_zero] at hmargin
    linarith
  have hprod : -(|t| * e) ≤ t * (r - t) := by
    have h1 : |t * (r - t)| ≤ |t| * e := by
      rw [abs_mul]
      exact mul_le_mul_of_nonneg_left herr (abs_nonneg _)
    exact (neg_le_neg h1).trans (neg_abs_le _)
  have hsq : |t| * |t| = t ^ 2 := by rw [← sq, sq_abs]
  have hgap : |t| * e < |t| * ((1 - γ / 2) * |t|) := mul_lt_mul_of_pos_left hmargin ht
  have hpos : γ * t ^ 2 * (γ / 2) < γ * (t * r) := by
    have h3 : t * r = t ^ 2 + t * (r - t) := by ring
    have h4 : (γ / 2) * t ^ 2 < t * r := by
      rw [h3]
      have : |t| * ((1 - γ / 2) * |t|) = (1 - γ / 2) * t ^ 2 := by rw [← hsq]; ring
      nlinarith
    nlinarith
  nlinarith

/-- A residual from an approximate normal operator `H`, entrywise within `η` of the
Gram matrix of the exact atoms: a step on it lowers the exact misfit when
`(1 − γ/2) |r̃_p| > η ‖m‖₁`. This links `gram_residual_bound` to the descent
theorems of `Clean` and `Clark`. -/
theorem operator_step_descends (v : E) (a : ι → E) (m : ι → ℝ) (H : ι → ι → ℝ) (p : ι)
    (hp : ‖a p‖ = 1) {γ η : ℝ} (h0 : 0 < γ)
    (h : ∀ i j, |⟪a j, a i⟫_ℝ - H i j| ≤ η)
    (hmargin : η * l1 m < (1 - γ / 2) * |⟪v, a p⟫_ℝ - ∑ j, m j * H p j|) :
    misfit v a (m + Pi.single p (γ * (⟪v, a p⟫_ℝ - ∑ j, m j * H p j))) < misfit v a m := by
  refine working_step_descends v a m p hp h0 ?_ hmargin
  have hd : dirty v a m p = ⟪v, a p⟫_ℝ - ∑ j, m j * ⟪a j, a p⟫_ℝ := by
    simp only [dirty, residual, inner_sub_left, sum_inner, inner_smul_left, conj_trivial]
  rw [hd]
  exact gram_residual_bound (fun i j => ⟪a j, a i⟫_ℝ) H (fun i => ⟪v, a i⟫_ℝ) m h p

/-! ## The w-node sum -/

section NodeSum

variable {P κ α : Type*} [Fintype P] [Fintype κ]

/-- `K_k(δ) = Σ_p W_p ψ_{p,k} χ_p(δ)`: the weights gridded to node `k`, a function
of the pixel difference only. -/
noncomputable def nodeKernel (W : P → ℝ) (ψ : P → κ → ℂ) (χ : P → α → ℂ) (k : κ) (δ : α) : ℂ :=
  ∑ p, (W p : ℂ) * ψ p k * χ p δ

/-- The identity behind the visibility-free operator. If for every visibility the
w-exponential between two pixels expands over fixed nodes, then the Gram entry is a
sum over nodes of a diagonal, a function of the pixel difference, and a diagonal. No
visibility index remains once `K` is tabulated. -/
theorem gram_eq_node_sum (W : P → ℝ) (ψ : P → κ → ℂ) (χ : P → α → ℂ) (s : κ → ℂ)
    (s' : κ → ℂ) (e : P → ℂ) (δ : α)
    (hexp : ∀ p, e p = ∑ k, ψ p k * (s k * conj (s' k))) :
    ∑ p, (W p : ℂ) * χ p δ * e p =
      ∑ k, s k * conj (s' k) * nodeKernel W ψ χ k δ := by
  simp only [nodeKernel, hexp, Finset.mul_sum]
  rw [Finset.sum_comm]
  refine Finset.sum_congr rfl fun k _ => Finset.sum_congr rfl fun p _ => ?_
  ring

/-- If the expansion holds to `ε` for every visibility and `|χ_p| ≤ 1`, the Gram
entry is within `ε Σ_p |W_p|`. With the triangle inequality over the model this is
the bound `‖(G − G̃) m‖_∞ ≤ ε ‖W‖₁ ‖m‖₁`. -/
theorem gram_node_sum_error (W : P → ℝ) (ψ : P → κ → ℂ) (χ : P → α → ℂ) (s s' : κ → ℂ)
    (e : P → ℂ) (δ : α) {ε : ℝ}
    (hexp : ∀ p, ‖e p - ∑ k, ψ p k * (s k * conj (s' k))‖ ≤ ε)
    (hχ : ∀ p, ‖χ p δ‖ ≤ 1) :
    ‖∑ p, (W p : ℂ) * χ p δ * e p - ∑ k, s k * conj (s' k) * nodeKernel W ψ χ k δ‖ ≤
      ε * ∑ p, |W p| := by
  have hexact := gram_eq_node_sum W ψ χ s s' (fun p => ∑ k, ψ p k * (s k * conj (s' k))) δ
    (fun _ => rfl)
  rw [← hexact, ← Finset.sum_sub_distrib]
  refine (norm_sum_le _ _).trans ?_
  rw [Finset.mul_sum]
  refine Finset.sum_le_sum fun p _ => ?_
  have hε : 0 ≤ ε := (norm_nonneg _).trans (hexp p)
  have : (W p : ℂ) * χ p δ * e p - (W p : ℂ) * χ p δ * ∑ k, ψ p k * (s k * conj (s' k)) =
      (W p : ℂ) * χ p δ * (e p - ∑ k, ψ p k * (s k * conj (s' k))) := by ring
  rw [this, norm_mul, norm_mul, Complex.norm_real, Real.norm_eq_abs]
  calc |W p| * ‖χ p δ‖ * ‖e p - ∑ k, ψ p k * (s k * conj (s' k))‖
      ≤ |W p| * 1 * ε := by
        have := abs_nonneg (W p)
        gcongr
        · exact hχ p
        · exact hexp p
    _ = ε * |W p| := by ring

end NodeSum

/-! ## Toeplitz embedding -/

section Embedding

open ZMod

/-- The differences of `n` pixels are distinct modulo `2n`: the box needs no more. -/
theorem sub_cast_injective {n : ℕ} {a b : ℤ} (ha : |a| < n) (hb : |b| < n)
    (h : ((a : ZMod (2 * n))) = ((b : ZMod (2 * n)))) : a = b := by
  have hd : ((2 * n : ℕ) : ℤ) ∣ a - b := by
    rw [ZMod.intCast_eq_intCast_iff_dvd_sub] at h
    have := (dvd_neg (a := ((2 * n : ℕ) : ℤ))).mpr h
    simpa using this
  have hlt : |a - b| < ((2 * n : ℕ) : ℤ) := by
    have h1 := abs_sub a b
    push_cast
    omega
  have := Int.eq_zero_of_abs_lt_dvd hd hlt
  omega

/-- A function of pixel differences `|δ| < n` extends to `ZMod (2n)`. -/
theorem exists_embedding {n : ℕ} [NeZero n] (T : ℤ → ℂ) :
    ∃ K : ZMod (2 * n) → ℂ, ∀ δ : ℤ, |δ| < n → K (δ : ZMod (2 * n)) = T δ := by
  classical
  refine ⟨fun x => T x.valMinAbs, fun δ hδ => ?_⟩
  have : NeZero (2 * n) := ⟨by have := NeZero.ne n; omega⟩
  have hspec : ((δ : ZMod (2 * n))).valMinAbs = δ := by
    rw [ZMod.valMinAbs_spec]
    refine ⟨rfl, ?_⟩
    rw [abs_lt] at hδ
    constructor <;> push_cast <;> omega
  simp only [hspec]

variable {N : ℕ} [NeZero N]

/-- Circular convolution on `ZMod N`. -/
noncomputable def circConv (K z : ZMod N → ℂ) (t : ZMod N) : ℂ := ∑ s, K (t - s) * z s

/-- The convolution theorem on `ZMod N`, from Mathlib's `ZMod.dft`. -/
theorem dft_circConv (K z : ZMod N → ℂ) (k : ZMod N) :
    𝓕 (circConv K z) k = 𝓕 K k * 𝓕 z k := by
  simp only [ZMod.dft_apply, circConv, smul_eq_mul, Finset.sum_mul, Finset.mul_sum]
  rw [Finset.sum_comm]
  refine Finset.sum_congr rfl fun s _ => ?_
  rw [← Equiv.sum_comp (Equiv.addRight s)]
  refine Finset.sum_congr rfl fun t _ => ?_
  simp only [Equiv.coe_addRight, add_sub_cancel_right]
  have h : -((t + s) * k) = -(t * k) + -(s * k) := by ring
  rw [h, AddChar.map_add_eq_mul]
  ring

/-- What the FFT pair computes: the inverse transform of the product is the circular
convolution. -/
theorem invDFT_product (K z : ZMod N → ℂ) :
    𝓕⁻ (fun k => 𝓕 K k * 𝓕 z k) = circConv K z := by
  have h : (fun k => 𝓕 K k * 𝓕 z k) = 𝓕 (circConv K z) := by
    funext k
    rw [dft_circConv]
  rw [h, LinearEquiv.symm_apply_apply]

/-- The Toeplitz embedding. Pixels are indices below `n`, the input is zero-padded by
`pad`, whose support is the image of `pos`; a kernel given on `|δ| < n` extends so that
the inverse transform of the product equals the Toeplitz sum at every pixel. -/
theorem embedded_convolution {n : ℕ} [NeZero n] [NeZero (2 * n)] (T : ℤ → ℂ)
    (z : Fin n → ℂ) (pad : ZMod (2 * n) → ℂ)
    (hpad : ∀ t, pad t = ∑ j : Fin n, if t = ((j : ℕ) : ZMod (2 * n)) then z j else 0)
    {K : ZMod (2 * n) → ℂ} (hK : ∀ δ : ℤ, |δ| < n → K (δ : ZMod (2 * n)) = T δ) (i : Fin n) :
    𝓕⁻ (fun k => 𝓕 K k * 𝓕 pad k) ((i : ℕ) : ZMod (2 * n)) =
      ∑ j : Fin n, T ((i : ℕ) - (j : ℕ)) * z j := by
  rw [invDFT_product, circConv]
  simp only [hpad, Finset.mul_sum]
  rw [Finset.sum_comm]
  refine Finset.sum_congr rfl fun j _ => ?_
  rw [Finset.sum_eq_single ((j : ℕ) : ZMod (2 * n))]
  · have hδ : |((i : ℕ) : ℤ) - (j : ℕ)| < n := by
      have h1 := i.isLt
      have h2 := j.isLt
      rw [abs_lt]
      constructor <;> omega
    have hcast : (((i : ℕ) : ZMod (2 * n)) - ((j : ℕ) : ZMod (2 * n))) =
        ((((i : ℕ) : ℤ) - (j : ℕ) : ℤ) : ZMod (2 * n)) := by
      push_cast
      ring
    rw [hcast, hK _ hδ]
    simp
  · intro s _ hs
    simp [hs]
  · simp

end Embedding

end Clean
