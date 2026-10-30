/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.Stagewise

/-!
# Clark's minor cycle: when a step taken on a truncated beam still descends (Theorem 6)

`research/clean-theory.md`, Theorem 6. In a Clark minor cycle the residual
image `r̃` is updated with a beam patch, so it drifts from the true residual
`r_p = ⟪e, a_p⟫`. A component `c = γ r̃_p` is placed at the working peak.

* `misfit_add_single` (in `Stagewise.lean`): the true misfit changes by exactly
  `−c r_p + c² / 2`.
* `clark_descends_iff`: for `γ > 0` and `r̃_p ≠ 0` the step lowers the true
  misfit iff `r_p / r̃_p > γ / 2`.
* `truncation_error_le`: if the subtracted beam differs from the exact one
  (the Gram matrix) by at most `f` everywhere, after components `c_1 … c_K`
  the working and true residual images differ by at most `f Σ_k |c_k|`.
* `dirty_add`: the true residual image after a model change `d` is
  `r − Σ_i d_i ⟪a_i, a_q⟫`, i.e. the exact beam is the Gram matrix.
* `clark_rule_descends`: the provable minor-cycle rule. If
  `|r_p − r̃_p| ≤ δ < (1 − γ/2)|r̃_p|` the step descends; with
  `δ = f Σ_k |c_k|` this is "continue while `f Σ_k |c_k| < (1 − γ/2)|r̃_p|`".
* `clark_minor_cycle_descends`: the two combined for a whole minor cycle.
-/

open scoped InnerProductSpace
open Finset

namespace Clean

variable {E : Type*} [NormedAddCommGroup E] [InnerProductSpace ℝ E]
variable {ι : Type*} [Fintype ι] [DecidableEq ι]

/-- **Theorem 6, the descent condition.** A component `γ r̃_p` at pixel `p` lowers the
true misfit iff the true residual there exceeds `γ/2` of the working one in ratio. -/
theorem clark_descends_iff (v : E) (a : ι → E) (m : ι → ℝ) (p : ι) (hp : ‖a p‖ = 1)
    {γ rt : ℝ} (hγ : 0 < γ) (hrt : rt ≠ 0) :
    misfit v a (m + Pi.single p (γ * rt)) < misfit v a m ↔ γ / 2 < dirty v a m p / rt := by
  rw [misfit_add_single v a m p _ hp]
  have hpos : 0 < γ * rt ^ 2 := by positivity
  have key : -(γ * rt * dirty v a m p) + (γ * rt) ^ 2 / 2 =
      γ * rt ^ 2 * (γ / 2 - dirty v a m p / rt) := by
    field_simp
    ring
  constructor
  · intro h
    have hneg : γ * rt ^ 2 * (γ / 2 - dirty v a m p / rt) < 0 := by linarith [key]
    by_contra hc'
    have hc := not_lt.mp hc'
    have : 0 ≤ γ * rt ^ 2 * (γ / 2 - dirty v a m p / rt) :=
      mul_nonneg hpos.le (by linarith)
    linarith
  · intro h
    have hneg : γ * rt ^ 2 * (γ / 2 - dirty v a m p / rt) < 0 :=
      mul_neg_of_pos_of_neg hpos (by linarith)
    linarith [key]

omit [Fintype ι] [DecidableEq ι] in
/-- **Truncation error.** If the beam used for the working residual differs from the
exact beam by at most `f` everywhere, then after components `c_k` at pixels `p_k`
the working and true residual images (both started from the same dirty image)
differ by at most `f Σ_k |c_k|`. -/
theorem truncation_error_le (Bexact Btrunc : ι → ι → ℝ) {f : ℝ}
    (hf : ∀ q p, |Bexact q p - Btrunc q p| ≤ f) (pix : ℕ → ι) (c : ℕ → ℝ) (K : ℕ)
    (d : ι → ℝ) (q : ι) :
    |(d q - ∑ k ∈ range K, c k * Bexact q (pix k)) -
        (d q - ∑ k ∈ range K, c k * Btrunc q (pix k))| ≤ f * ∑ k ∈ range K, |c k| := by
  have h : (d q - ∑ k ∈ range K, c k * Bexact q (pix k)) -
      (d q - ∑ k ∈ range K, c k * Btrunc q (pix k)) =
        -∑ k ∈ range K, c k * (Bexact q (pix k) - Btrunc q (pix k)) := by
    have hs : ∑ k ∈ range K, c k * (Bexact q (pix k) - Btrunc q (pix k)) =
        ∑ k ∈ range K, c k * Bexact q (pix k) - ∑ k ∈ range K, c k * Btrunc q (pix k) := by
      rw [← Finset.sum_sub_distrib]
      exact Finset.sum_congr rfl fun k _ => mul_sub _ _ _
    rw [hs]
    ring
  rw [h, abs_neg, Finset.mul_sum]
  refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun k _ => ?_)
  rw [abs_mul]
  calc |c k| * |Bexact q (pix k) - Btrunc q (pix k)| ≤ |c k| * f :=
        mul_le_mul_of_nonneg_left (hf _ _) (abs_nonneg _)
    _ = f * |c k| := mul_comm _ _

omit [DecidableEq ι] in
/-- The true residual image after a model change `d`: the exact beam is the Gram
matrix `⟪a_i, a_q⟫` of the atoms. -/
theorem dirty_add (v : E) (a : ι → E) (m d : ι → ℝ) (q : ι) :
    dirty v a (m + d) q = dirty v a m q - ∑ i, d i * ⟪a i, a q⟫_ℝ := by
  unfold dirty
  rw [residual_add, inner_sub_left, sum_inner]
  congr 1
  exact Finset.sum_congr rfl fun i _ => real_inner_smul_left _ _ _

/-- **The provable minor-cycle rule.** If the working residual `r̃_p` is within `δ` of
the true one and `δ < (1 − γ/2)|r̃_p|`, the component `γ r̃_p` lowers the true misfit. -/
theorem clark_rule_descends (v : E) (a : ι → E) (m : ι → ℝ) (p : ι) (hp : ‖a p‖ = 1)
    {γ rt δ : ℝ} (hγ : 0 < γ) (herr : |dirty v a m p - rt| ≤ δ)
    (hrule : δ < (1 - γ / 2) * |rt|) :
    misfit v a (m + Pi.single p (γ * rt)) < misfit v a m := by
  have hrt : rt ≠ 0 := by
    intro h
    rw [h, abs_zero, mul_zero] at hrule
    linarith [abs_nonneg (dirty v a m p - rt)]
  rw [clark_descends_iff v a m p hp hγ hrt]
  have habs : 0 < |rt| := abs_pos.mpr hrt
  -- r_p / r̃_p = 1 + (r_p − r̃_p)/r̃_p ≥ 1 − δ/|r̃_p| > γ/2
  have hsplit : dirty v a m p / rt = 1 + (dirty v a m p - rt) / rt := by
    field_simp
    ring
  have hlow : -(δ / |rt|) ≤ (dirty v a m p - rt) / rt := by
    have h1 : |(dirty v a m p - rt) / rt| = |dirty v a m p - rt| / |rt| := abs_div _ _
    have h2 : |dirty v a m p - rt| / |rt| ≤ δ / |rt| :=
      div_le_div_of_nonneg_right herr habs.le
    have h3 := neg_abs_le ((dirty v a m p - rt) / rt)
    linarith
  have hδ : δ / |rt| < 1 - γ / 2 := by
    rw [div_lt_iff₀ habs]
    linarith
  linarith

/-- **Theorem 6, a whole minor cycle.** Let the working residual `r̃` be the dirty
image `d` minus components `c_k` at `p_k` (`k < K`) convolved with a beam that is
within `f` of the exact one, and let the model `m` hold the same components, so
the true residual is `d` minus them convolved with the Gram matrix. If
`f Σ_k |c_k| < (1 − γ/2)|r̃_p|`, the next component `γ r̃_p` lowers the true
misfit. -/
theorem clark_minor_cycle_descends (v : E) (a : ι → E) (m : ι → ℝ) (p : ι)
    (hp : ‖a p‖ = 1) {γ f : ℝ} (hγ : 0 < γ) (Btrunc : ι → ι → ℝ)
    (hf : ∀ q i, |⟪a i, a q⟫_ℝ - Btrunc q i| ≤ f) (pix : ℕ → ι) (c : ℕ → ℝ) (K : ℕ)
    (htrue : ∀ q, dirty v a m q =
      dirty v a 0 q - ∑ k ∈ range K, c k * ⟪a (pix k), a q⟫_ℝ)
    (hrule : f * ∑ k ∈ range K, |c k| <
      (1 - γ / 2) * |dirty v a 0 p - ∑ k ∈ range K, c k * Btrunc p (pix k)|) :
    misfit v a (m + Pi.single p
        (γ * (dirty v a 0 p - ∑ k ∈ range K, c k * Btrunc p (pix k)))) < misfit v a m := by
  refine clark_rule_descends v a m p hp hγ ?_ hrule
  rw [htrue p]
  exact truncation_error_le (fun q i => ⟪a i, a q⟫_ℝ) Btrunc hf pix c K (dirty v a 0) p

end Clean
