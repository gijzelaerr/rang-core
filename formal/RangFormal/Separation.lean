/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import Mathlib

/-!
# Separated sources: the exact recovery coefficient below one (Proposition 4')

`research/clean-theory.md`, Proposition 4'. The pixels carry a metric (for
the image grid, the Chebyshev distance), `B` is the point-spread function
read as the Gram matrix of the atoms, with unit diagonal, and `S` is the
support of `k` sources pairwise at least `d` apart. Write `μ₁` for the peak
`|B|` between distinct pixels, `μ_h` for the peak at distance at least
`d / 2` and `μ_d` for the peak at distance at least `d`. If
`(k − 1)(μ_h + μ_d) < 1 − μ₁` then Tropp's exact recovery coefficient
`η(S) = max_{q ∉ S} ‖B_SS⁻¹ B_{S,q}‖₁` is below one. On the integer grid
"distance at least `d / 2`" is "distance at least `⌈d / 2⌉`", the form used
in the note and in `clean_theory`.

* `l1_le_of_offdiag_le`: the Neumann-series bound in ℓ1 form, without a matrix
  inverse: every solution of `B_SS x = b` has
  `(1 − (k − 1) μ_d) ‖x‖₁ ≤ ‖b‖₁`.
* `colsum_le_of_separated`: at most one source is closer than `d / 2` to any
  pixel, so `‖B_{S,q}‖₁ ≤ μ₁ + (k − 1) μ_h` for `q ∉ S`.
* `erc_lt_one_of_separated`: every solution of `B_SS x = B_{S,q}` has
  `‖x‖₁ < 1`.
* `exists_erc_solution`: such a solution exists (`B_SS` is invertible).
* `pick_in_support_of_separated`: for a symmetric `B` and a residual in the
  span of the support atoms, the largest residual peak lies on `S`; Högbom's
  argmax stays on the sources.
-/

open Finset

namespace Clean

variable {ι : Type*} [DecidableEq ι]

/-- **The Neumann-series bound, ℓ1 form.** With unit diagonal and off-diagonal
entries at most `μ` on `S`, every solution of `Σ_{j∈S} B i j x j = b i` (`i ∈ S`)
satisfies `(1 − (|S| − 1) μ) Σ_{i∈S} |x i| ≤ Σ_{i∈S} |b i|`. -/
theorem l1_le_of_offdiag_le (B : ι → ι → ℝ) (S : Finset ι) (x b : ι → ℝ) {μ : ℝ}
    (hdiag : ∀ i ∈ S, B i i = 1) (hoff : ∀ i ∈ S, ∀ j ∈ S, i ≠ j → |B i j| ≤ μ)
    (hsol : ∀ i ∈ S, ∑ j ∈ S, B i j * x j = b i) :
    (1 - ((S.card : ℝ) - 1) * μ) * ∑ i ∈ S, |x i| ≤ ∑ i ∈ S, |b i| := by
  set X := ∑ i ∈ S, |x i| with hX
  have hrow : ∀ i ∈ S, |x i| ≤ |b i| + μ * (X - |x i|) := by
    intro i hi
    have hsplit := hsol i hi
    rw [← Finset.add_sum_erase S _ hi, hdiag i hi, one_mul] at hsplit
    have hxi : x i = b i - ∑ j ∈ S.erase i, B i j * x j := by linarith
    have htail : |∑ j ∈ S.erase i, B i j * x j| ≤ μ * (X - |x i|) := by
      rw [hX, ← Finset.sum_erase_eq_sub hi, Finset.mul_sum]
      refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun j hj => ?_)
      rw [abs_mul]
      have hji : j ≠ i := Finset.ne_of_mem_erase hj
      calc |B i j| * |x j| ≤ μ * |x j| :=
            mul_le_mul_of_nonneg_right (hoff i hi j (Finset.mem_of_mem_erase hj) hji.symm)
              (abs_nonneg _)
        _ = μ * |x j| := rfl
    calc |x i| = |b i - ∑ j ∈ S.erase i, B i j * x j| := by rw [hxi]
      _ ≤ |b i| + |∑ j ∈ S.erase i, B i j * x j| := abs_sub _ _
      _ ≤ |b i| + μ * (X - |x i|) := by linarith
  have hsum : X ≤ ∑ i ∈ S, |b i| + μ * ((S.card : ℝ) * X - X) := by
    calc X = ∑ i ∈ S, |x i| := rfl
      _ ≤ ∑ i ∈ S, (|b i| + μ * (X - |x i|)) := Finset.sum_le_sum hrow
      _ = ∑ i ∈ S, |b i| + μ * ((S.card : ℝ) * X - X) := by
          rw [Finset.sum_add_distrib, ← Finset.mul_sum, Finset.sum_sub_distrib,
            Finset.sum_const, nsmul_eq_mul]
  calc (1 - ((S.card : ℝ) - 1) * μ) * X = X - μ * ((S.card : ℝ) * X - X) := by ring
    _ ≤ ∑ i ∈ S, |b i| := by linarith

variable [PseudoMetricSpace ι]

/-- **The off-support column.** For sources pairwise at least `d` apart, at most
one of them is closer than `d / 2` to any pixel `q ∉ S`, so
`Σ_{i∈S} |B i q| ≤ μ₁ + (|S| − 1) μ_h`. -/
theorem colsum_le_of_separated (B : ι → ι → ℝ) (S : Finset ι) (hS : S.Nonempty) (q : ι)
    (hq : q ∉ S) {μ₁ μh d : ℝ}
    (hsep : ∀ i ∈ S, ∀ j ∈ S, i ≠ j → d ≤ dist i j)
    (h1 : ∀ i j, i ≠ j → |B i j| ≤ μ₁) (hh : ∀ i j, d / 2 ≤ dist i j → |B i j| ≤ μh) :
    ∑ i ∈ S, |B i q| ≤ μ₁ + ((S.card : ℝ) - 1) * μh := by
  obtain ⟨i₀, hi₀, hmin⟩ := S.exists_min_image (fun i => dist i q) hS
  have hfar : ∀ i ∈ S.erase i₀, d / 2 ≤ dist i q := by
    intro i hi
    by_contra hge
    have hlt := not_le.mp hge
    have hne : i ≠ i₀ := Finset.ne_of_mem_erase hi
    have hiS := Finset.mem_of_mem_erase hi
    have h0 : dist i₀ q ≤ dist i q := hmin i hiS
    have htri : dist i i₀ ≤ dist i q + dist i₀ q := by
      have := dist_triangle i q i₀
      rw [dist_comm q i₀] at this
      exact this
    have := hsep i hiS i₀ hi₀ hne
    linarith
  rw [← Finset.add_sum_erase S _ hi₀]
  have hne₀ : i₀ ≠ q := fun h => hq (h ▸ hi₀)
  have hrest : ∑ i ∈ S.erase i₀, |B i q| ≤ ((S.card : ℝ) - 1) * μh := by
    calc ∑ i ∈ S.erase i₀, |B i q| ≤ ∑ _i ∈ S.erase i₀, μh :=
          Finset.sum_le_sum fun i hi => hh i q (hfar i hi)
      _ = ((S.card : ℝ) - 1) * μh := by
          rw [Finset.sum_const, Finset.card_erase_of_mem hi₀, nsmul_eq_mul,
            Nat.cast_sub (Finset.card_pos.mpr hS), Nat.cast_one]
  linarith [h1 i₀ q hne₀]

/-- **Proposition 4'.** For sources pairwise at least `d` apart with
`(k − 1)(μ_h + μ_d) < 1 − μ₁`, every solution of `B_SS x = B_{S,q}`, `q ∉ S`, has
`‖x‖₁ < 1`: the exact recovery coefficient is below one. -/
theorem erc_lt_one_of_separated (B : ι → ι → ℝ) (S : Finset ι) (q : ι) (hq : q ∉ S)
    {μ₁ μh μd d : ℝ} (hdiag : ∀ i ∈ S, B i i = 1)
    (hsep : ∀ i ∈ S, ∀ j ∈ S, i ≠ j → d ≤ dist i j)
    (h1 : ∀ i j, i ≠ j → |B i j| ≤ μ₁) (hh : ∀ i j, d / 2 ≤ dist i j → |B i j| ≤ μh)
    (hd : ∀ i j, i ≠ j → d ≤ dist i j → |B i j| ≤ μd) (hμh : 0 ≤ μh)
    (hcond : ((S.card : ℝ) - 1) * (μh + μd) < 1 - μ₁)
    (x : ι → ℝ) (hx : ∀ i ∈ S, ∑ j ∈ S, B i j * x j = B i q) :
    ∑ i ∈ S, |x i| < 1 := by
  rcases S.eq_empty_or_nonempty with hS | hS
  · simp [hS]
  have hoff : ∀ i ∈ S, ∀ j ∈ S, i ≠ j → |B i j| ≤ μd :=
    fun i hi j hj hij => hd i j hij (hsep i hi j hj hij)
  have hl1 := l1_le_of_offdiag_le B S x (fun i => B i q) hdiag hoff hx
  have hcol := colsum_le_of_separated B S hS q hq hsep h1 hh
  have hk : (1 : ℝ) ≤ S.card := by exact_mod_cast Finset.card_pos.mpr hS
  obtain ⟨i₀, hi₀⟩ := hS
  have hμ₁ : 0 ≤ μ₁ := (abs_nonneg _).trans (h1 i₀ q fun h => hq (h ▸ hi₀))
  have hk1 : 0 ≤ (S.card : ℝ) - 1 := by linarith
  have hpos : 0 < 1 - ((S.card : ℝ) - 1) * μd := by nlinarith [mul_nonneg hk1 hμh]
  have hlt : (1 - ((S.card : ℝ) - 1) * μd) * ∑ i ∈ S, |x i| < 1 - ((S.card : ℝ) - 1) * μd := by
    nlinarith [hl1, hcol]
  by_contra hlt
  have hge := not_lt.mp hlt
  nlinarith [mul_le_mul_of_nonneg_left hge hpos.le]

omit [PseudoMetricSpace ι] in
/-- `B_SS` is invertible under the hypotheses of Proposition 4', so the system
`B_SS x = B_{S,q}` that defines the exact recovery coefficient has a solution. -/
theorem exists_erc_solution (B : ι → ι → ℝ) (S : Finset ι) {μd : ℝ}
    (hdiag : ∀ i ∈ S, B i i = 1) (hoff : ∀ i ∈ S, ∀ j ∈ S, i ≠ j → |B i j| ≤ μd)
    (hpos : 0 < 1 - ((S.card : ℝ) - 1) * μd) (b : ι → ℝ) :
    ∃ x : ι → ℝ, ∀ i ∈ S, ∑ j ∈ S, B i j * x j = b i := by
  classical
  -- the restriction of `B` to `S` as a square matrix
  let M : Matrix S S ℝ := fun i j => B i j
  have hzero : ∀ y : S → ℝ, M.mulVec y = 0 → y = 0 := by
    intro y hy
    let x : ι → ℝ := fun i => if h : i ∈ S then y ⟨i, h⟩ else 0
    have hsol : ∀ i ∈ S, ∑ j ∈ S, B i j * x j = 0 := by
      intro i hi
      have := congrFun hy ⟨i, hi⟩
      simp only [Matrix.mulVec, dotProduct, Pi.zero_apply, M] at this
      rw [← this, ← Finset.sum_coe_sort S]
      refine Finset.sum_congr rfl fun j _ => ?_
      simp [x, j.2]
    have hl1 := l1_le_of_offdiag_le B S x 0 hdiag hoff hsol
    simp only [Pi.zero_apply, abs_zero, Finset.sum_const_zero] at hl1
    have hX : ∑ i ∈ S, |x i| = 0 := by
      have h0 : 0 ≤ ∑ i ∈ S, |x i| := Finset.sum_nonneg fun _ _ => abs_nonneg _
      nlinarith
    funext j
    have hj := (Finset.sum_eq_zero_iff_of_nonneg (fun i _ => abs_nonneg (x i))).mp hX j j.2
    simpa [x, j.2] using hj
  have hinj : Function.Injective M.mulVec := by
    intro y₁ y₂ hy
    have h0 : M.mulVec (y₁ - y₂) = 0 := by rw [Matrix.mulVec_sub, hy, sub_self]
    exact sub_eq_zero.mp (hzero _ h0)
  have hsurj : Function.Surjective M.mulVec :=
    Matrix.mulVec_surjective_iff_isUnit.mpr (Matrix.mulVec_injective_iff_isUnit.mp hinj)
  obtain ⟨y, hy⟩ := hsurj (fun i => b i)
  refine ⟨fun i => if h : i ∈ S then y ⟨i, h⟩ else 0, fun i hi => ?_⟩
  have := congrFun hy ⟨i, hi⟩
  simp only [Matrix.mulVec, dotProduct, M] at this
  rw [← this, ← Finset.sum_coe_sort S]
  refine Finset.sum_congr rfl fun j _ => ?_
  simp [j.2]

omit [DecidableEq ι] [PseudoMetricSpace ι] in
/-- **The pick stays on the sources.** For a symmetric `B` and a residual image
`r_j = Σ_{i∈S} B j i c_i` of a residual in the span of the support atoms, if every
`B_SS x = B_{S,q}` (`q ∉ S`) has a solution with `‖x‖₁ < 1` and `r` is not zero on
`S`, the largest `|r|` is attained on `S` and nowhere else. -/
theorem pick_in_support_of_erc [Fintype ι] (B : ι → ι → ℝ) (S : Finset ι)
    (hsymm : ∀ i j, B i j = B j i) (c : ι → ℝ) (r : ι → ℝ)
    (hr : ∀ j, r j = ∑ i ∈ S, B j i * c i)
    (herc : ∀ q ∉ S, ∃ x : ι → ℝ, (∀ i ∈ S, ∑ j ∈ S, B i j * x j = B i q) ∧
      ∑ i ∈ S, |x i| < 1)
    (hnz : ∃ i ∈ S, r i ≠ 0) :
    ∃ p ∈ S, ∀ q ∉ S, |r q| < |r p| := by
  obtain ⟨i₀, hi₀, hri₀⟩ := hnz
  obtain ⟨p, hpS, hpmax⟩ := S.exists_max_image (fun i => |r i|) ⟨i₀, hi₀⟩
  have hrp : 0 < |r p| := lt_of_lt_of_le (abs_pos.mpr hri₀) (hpmax i₀ hi₀)
  refine ⟨p, hpS, fun q hq => ?_⟩
  obtain ⟨x, hx, hx1⟩ := herc q hq
  -- r_q = Σ_i B_qi c_i = Σ_i (Σ_j B_ij x_j) c_i = Σ_j x_j r_j
  have hexp : r q = ∑ j ∈ S, x j * r j := by
    rw [hr q]
    calc ∑ i ∈ S, B q i * c i = ∑ i ∈ S, (∑ j ∈ S, B i j * x j) * c i := by
          refine Finset.sum_congr rfl fun i hi => ?_
          rw [hx i hi, hsymm q i]
      _ = ∑ j ∈ S, x j * ∑ i ∈ S, B j i * c i := by
          simp only [Finset.sum_mul, Finset.mul_sum]
          rw [Finset.sum_comm]
          refine Finset.sum_congr rfl fun j _ => Finset.sum_congr rfl fun i _ => ?_
          rw [hsymm i j]
          ring
      _ = ∑ j ∈ S, x j * r j := by
          refine Finset.sum_congr rfl fun j _ => ?_
          rw [hr j]
  rw [hexp]
  calc |∑ j ∈ S, x j * r j| ≤ ∑ j ∈ S, |x j| * |r j| := by
        refine (Finset.abs_sum_le_sum_abs _ _).trans (le_of_eq ?_)
        exact Finset.sum_congr rfl fun j _ => abs_mul _ _
    _ ≤ ∑ j ∈ S, |x j| * |r p| :=
        Finset.sum_le_sum fun j hj => mul_le_mul_of_nonneg_left (hpmax j hj) (abs_nonneg _)
    _ = (∑ j ∈ S, |x j|) * |r p| := by rw [Finset.sum_mul]
    _ < 1 * |r p| := mul_lt_mul_of_pos_right hx1 hrp
    _ = |r p| := one_mul _

end Clean
