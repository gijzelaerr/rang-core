/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.Clean

/-!
# CLEAN as forward stagewise regression: step lemmas and uniqueness of the limit

The companion of `research/clean-implicit-objective.md`. A stagewise step at
pixel `p` adds `h · s` to the model coefficient `m_p`, with `s = ±1` the sign
of the residual dirty image `r_p`: incremental forward stagewise (`FS_ε`)
takes `h = ε`, Högbom CLEAN with gain `γ` takes `h = γ |r_p|`.

* `misfit_add_eq`: the exact misfit after adding any direction `d`,
  `Q(m + d) = Q(m) − Σ d_i r_i + ‖Σ d_i a_i‖² / 2`.
* `misfit_add_ge` (ℓ1 steepest descent): if `max_i |r_i| ≤ φ` then
  `Q(m + d) ≥ Q(m) − φ ‖d‖₁` for every `d`; no move of ℓ1 length `ℓ` lowers
  the misfit by more than `φ ℓ` to first order.
* `misfit_add_single`: a component `c` at `p` changes the misfit by exactly
  `−c r_p + c² / 2`.
* `misfit_stagewise_step`: a signed step of length `ε` lowers it by
  `ε |r_p| − ε² / 2`, so the first-order decrease per unit ℓ1 arc length is
  `|r_p|`, maximal at the argmax pick.
* `stagewise_pick_optimal`: exactly (second-order term included), the signed
  step at the argmax pixel leaves the smallest misfit among all steps `±ε` at
  any pixel.
* `step_eq_stagewise`, `l1_step_sub`: a CLEAN step is a stagewise step of
  length `|γ| |r_p|` in the direction of `sign r_p`.
* `l1_iterate_le_arc`: the ℓ1 norm of the CLEAN model never exceeds the ℓ1
  arc length `Σ_k |γ r_{p_k}|` of its path.
* `subgradient_monotone`: two directions in the subdifferential of the ℓ∞
  norm at `r1` and `r2` satisfy `(r1 − r2)·(d1 − d2) ≥ 0`.
* `flow_residual_unique`: two residual curves that start together and move
  by `ė = −Σ_j d_j(t) a_j` with `d(t)` in that subdifferential (the small-gain
  limit of CLEAN and of `FS_ε`, a gradient flow of the peak residual) are
  equal; this is the data-space uniqueness step of Theorem A in the note.
-/

open scoped InnerProductSpace
open Filter Topology Finset Set

namespace Clean

variable {E : Type*} [NormedAddCommGroup E] [InnerProductSpace ℝ E]
variable {ι : Type*} [Fintype ι] [DecidableEq ι]

/-- The ℓ1 norm `Σ_i |m_i|` of a model (Mathlib's norm on `ι → ℝ` is the sup norm). -/
def l1 (m : ι → ℝ) : ℝ := ∑ i, |m i|

omit [DecidableEq ι] in
theorem l1_nonneg (m : ι → ℝ) : 0 ≤ l1 m :=
  Finset.sum_nonneg fun _ _ => abs_nonneg _

omit [DecidableEq ι] in
theorem l1_add_le (m d : ι → ℝ) : l1 (m + d) ≤ l1 m + l1 d := by
  unfold l1
  rw [← Finset.sum_add_distrib]
  exact Finset.sum_le_sum fun i _ => abs_add_le (m i) (d i)

theorem l1_single (p : ι) (c : ℝ) : l1 (Pi.single p c : ι → ℝ) = |c| := by
  unfold l1
  rw [Finset.sum_eq_single p]
  · simp
  · intro i _ hi; simp [hi]
  · intro h; exact absurd (Finset.mem_univ p) h

omit [DecidableEq ι] in
theorem residual_add (v : E) (a : ι → E) (m d : ι → ℝ) :
    residual v a (m + d) = residual v a m - ∑ i, d i • a i := by
  unfold residual
  simp only [Pi.add_apply, add_smul, Finset.sum_add_distrib]
  abel

omit [DecidableEq ι] in
theorem inner_sum_smul (x : E) (a : ι → E) (d : ι → ℝ) :
    ⟪x, ∑ i, d i • a i⟫_ℝ = ∑ i, d i * ⟪x, a i⟫_ℝ := by
  rw [inner_sum]
  exact Finset.sum_congr rfl fun i _ => real_inner_smul_right _ _ _

omit [DecidableEq ι] in
/-- The exact misfit after an arbitrary move `d` of the model. -/
theorem misfit_add_eq (v : E) (a : ι → E) (m d : ι → ℝ) :
    misfit v a (m + d) =
      misfit v a m - ∑ i, d i * dirty v a m i + ‖∑ i, d i • a i‖ ^ 2 / 2 := by
  unfold misfit dirty
  rw [residual_add, norm_sub_sq_real, inner_sum_smul]
  ring

omit [DecidableEq ι] in
/-- The first-order term of any move is at most the peak residual times its ℓ1 length. -/
theorem sum_mul_dirty_le (v : E) (a : ι → E) (m d : ι → ℝ) {φ : ℝ}
    (hφ : ∀ i, |dirty v a m i| ≤ φ) : ∑ i, d i * dirty v a m i ≤ φ * l1 d := by
  unfold l1
  rw [Finset.mul_sum]
  refine Finset.sum_le_sum fun i _ => ?_
  calc d i * dirty v a m i ≤ |d i * dirty v a m i| := le_abs_self _
    _ = |d i| * |dirty v a m i| := abs_mul _ _
    _ ≤ |d i| * φ := mul_le_mul_of_nonneg_left (hφ i) (abs_nonneg _)
    _ = φ * |d i| := mul_comm _ _

omit [DecidableEq ι] in
/-- **ℓ1 steepest descent.** No move lowers the misfit by more than the peak
residual times its ℓ1 length (to first order, and the second-order term only
raises it). -/
theorem misfit_add_ge (v : E) (a : ι → E) (m d : ι → ℝ) {φ : ℝ}
    (hφ : ∀ i, |dirty v a m i| ≤ φ) : misfit v a m - φ * l1 d ≤ misfit v a (m + d) := by
  rw [misfit_add_eq]
  have h1 := sum_mul_dirty_le v a m d hφ
  have h2 : 0 ≤ ‖∑ i, d i • a i‖ ^ 2 / 2 := by positivity
  linarith

/-- **A single component.** Adding `c` at pixel `p` changes the misfit by exactly
`−c r_p + c² / 2` (Theorem 6 of `clean-theory.md`, first part). -/
theorem misfit_add_single (v : E) (a : ι → E) (m : ι → ℝ) (p : ι) (c : ℝ) (hp : ‖a p‖ = 1) :
    misfit v a (m + Pi.single p c) = misfit v a m - c * dirty v a m p + c ^ 2 / 2 := by
  rw [misfit_add_eq, sum_single_smul, norm_smul, hp, mul_one, Real.norm_eq_abs, sq_abs]
  congr 2
  rw [Finset.sum_eq_single p]
  · simp
  · intro i _ hi; simp [hi]
  · intro h; exact absurd (Finset.mem_univ p) h

/-- **The stagewise step.** A step of length `ε` at `p` in the direction `s` of the
residual (`|s| = 1`, `s r_p = |r_p|`) lowers the misfit by `ε |r_p| − ε² / 2`. -/
theorem misfit_stagewise_step (v : E) (a : ι → E) (m : ι → ℝ) (p : ι) (ε s : ℝ)
    (hp : ‖a p‖ = 1) (hs : |s| = 1) (hsr : s * dirty v a m p = |dirty v a m p|) :
    misfit v a (m + Pi.single p (ε * s)) = misfit v a m - ε * |dirty v a m p| + ε ^ 2 / 2 := by
  rw [misfit_add_single v a m p _ hp]
  have hs2 : s ^ 2 = 1 := by rw [← sq_abs, hs]; norm_num
  have : ε * s * dirty v a m p = ε * |dirty v a m p| := by rw [mul_assoc, hsr]
  rw [this, mul_pow, hs2, mul_one]

/-- The ℓ1 length of a stagewise step is `|ε|`. -/
theorem l1_stagewise_step (p : ι) (ε s : ℝ) (hs : |s| = 1) :
    l1 (Pi.single p (ε * s) : ι → ℝ) = |ε| := by
  rw [l1_single, abs_mul, hs, mul_one]

/-- The sign used by a stagewise step: `1` for `x ≥ 0`, else `−1`. -/
noncomputable def sgn (x : ℝ) : ℝ := if 0 ≤ x then 1 else -1

theorem abs_sgn (x : ℝ) : |sgn x| = 1 := by
  unfold sgn; split_ifs <;> norm_num

theorem sgn_mul_self (x : ℝ) : sgn x * x = |x| := by
  unfold sgn
  split_ifs with h
  · rw [one_mul, abs_of_nonneg h]
  · rw [abs_of_neg (not_le.mp h)]; ring

theorem sgn_mul_abs (x : ℝ) : sgn x * |x| = x := by
  unfold sgn
  split_ifs with h
  · rw [one_mul, abs_of_nonneg h]
  · rw [abs_of_neg (not_le.mp h)]; ring

/-- **The greedy pick is optimal among single-coordinate steps of the same ℓ1 size.**
If `p` carries the largest `|r|`, the signed step of length `ε ≥ 0` at `p` leaves a
misfit no larger than any step `±ε` at any pixel `q`, exactly (second-order term
included). -/
theorem stagewise_pick_optimal (v : E) (a : ι → E) (m : ι → ℝ) (p q : ι)
    (hp : ‖a p‖ = 1) (hq : ‖a q‖ = 1) {ε s : ℝ} (hε : 0 ≤ ε) (hs : |s| = 1)
    (hmax : ∀ i, |dirty v a m i| ≤ |dirty v a m p|) :
    misfit v a (m + Pi.single p (ε * sgn (dirty v a m p))) ≤
      misfit v a (m + Pi.single q (ε * s)) := by
  rw [misfit_stagewise_step v a m p ε _ hp (abs_sgn _) (sgn_mul_self _),
    misfit_add_single v a m q _ hq]
  have hs2 : s ^ 2 = 1 := by rw [← sq_abs, hs]; norm_num
  have hsq : s * dirty v a m q ≤ |dirty v a m p| :=
    calc s * dirty v a m q ≤ |s * dirty v a m q| := le_abs_self _
      _ = |dirty v a m q| := by rw [abs_mul, hs, one_mul]
      _ ≤ |dirty v a m p| := hmax q
  have hmul : ε * (s * dirty v a m q) ≤ ε * |dirty v a m p| :=
    mul_le_mul_of_nonneg_left hsq hε
  have hexp : (ε * s) ^ 2 = ε ^ 2 := by rw [mul_pow, hs2, mul_one]
  rw [hexp]
  nlinarith [hmul]

/-- **CLEAN is stagewise.** A CLEAN step with gain `γ` is the stagewise step of length
`γ |r_p|` in the direction of `sign r_p`. -/
theorem step_eq_stagewise (v : E) (a : ι → E) (γ : ℝ) (m : ι → ℝ) (p : ι) :
    step v a γ m p = m + Pi.single p ((γ * |dirty v a m p|) * sgn (dirty v a m p)) := by
  unfold step
  rw [mul_assoc, mul_comm |dirty v a m p| (sgn (dirty v a m p)), sgn_mul_abs]

/-- The ℓ1 size of a CLEAN step is `|γ| |r_p|`. -/
theorem l1_step_sub (v : E) (a : ι → E) (γ : ℝ) (m : ι → ℝ) (p : ι) :
    l1 (step v a γ m p - m) = |γ| * |dirty v a m p| := by
  unfold step
  rw [add_sub_cancel_left, l1_single, abs_mul]

/-- **Arc length bounds the norm.** The ℓ1 norm of the CLEAN model after `K` steps is
at most the ℓ1 arc length `Σ_{k<K} |γ r_{p_k}|` of its path. -/
theorem l1_iterate_le_arc (v : E) (a : ι → E) (γ : ℝ) (pick : (ι → ℝ) → ι) (K : ℕ) :
    l1 (iterate v a γ pick K) ≤ ∑ k ∈ Finset.range K, |γ * peak v a γ pick k| := by
  induction K with
  | zero => simp [iterate, l1]
  | succ K ih =>
    rw [Finset.sum_range_succ]
    have hstep : iterate v a γ pick (K + 1) =
        iterate v a γ pick K + Pi.single (pick (iterate v a γ pick K)) (γ * peak v a γ pick K) :=
      rfl
    rw [hstep]
    calc l1 (iterate v a γ pick K +
          Pi.single (pick (iterate v a γ pick K)) (γ * peak v a γ pick K))
        ≤ l1 (iterate v a γ pick K) +
            l1 (Pi.single (pick (iterate v a γ pick K)) (γ * peak v a γ pick K) : ι → ℝ) :=
          l1_add_le _ _
      _ = l1 (iterate v a γ pick K) + |γ * peak v a γ pick K| := by rw [l1_single]
      _ ≤ _ := by linarith

omit [DecidableEq ι] in
/-- `e · r ≤ S ‖e‖₁` when every `|r_k| ≤ S`. -/
theorem sum_mul_le_l1 (r e : ι → ℝ) {S : ℝ} (h : ∀ k, |r k| ≤ S) :
    ∑ j, e j * r j ≤ S * l1 e := by
  unfold l1
  rw [Finset.mul_sum]
  refine Finset.sum_le_sum fun j _ => ?_
  calc e j * r j ≤ |e j * r j| := le_abs_self _
    _ = |e j| * |r j| := abs_mul _ _
    _ ≤ |e j| * S := mul_le_mul_of_nonneg_left (h j) (abs_nonneg _)
    _ = S * |e j| := mul_comm _ _

omit [DecidableEq ι] in
/-- **Monotonicity of the ℓ∞ subdifferential.** If `d1`, `d2` have ℓ1 norm at most one
and attain the peaks of `r1`, `r2` (`|r_i k| ≤ d_i · r_i` for all `k`), then
`(r1 − r2) · (d1 − d2) ≥ 0`. -/
theorem subgradient_monotone (r1 r2 d1 d2 : ι → ℝ) (hn1 : l1 d1 ≤ 1) (hn2 : l1 d2 ≤ 1)
    (h1 : ∀ k, |r1 k| ≤ ∑ j, d1 j * r1 j) (h2 : ∀ k, |r2 k| ≤ ∑ j, d2 j * r2 j) :
    0 ≤ ∑ j, (r1 j - r2 j) * (d1 j - d2 j) := by
  -- the cross term of a direction against the other peak is at most that peak
  have cross : ∀ (r d e : ι → ℝ), l1 e ≤ 1 → (∀ k, |r k| ≤ ∑ j, d j * r j) →
      ∑ j, e j * r j ≤ ∑ j, d j * r j := by
    intro r d e he h
    set S := ∑ j, d j * r j with hS
    have hS0 : 0 ≤ S := by
      rcases isEmpty_or_nonempty ι with hι | ⟨⟨k⟩⟩
      · simp [hS, Finset.univ_eq_empty]
      · exact (abs_nonneg _).trans (h k)
    have hb := sum_mul_le_l1 r e h
    calc ∑ j, e j * r j ≤ S * l1 e := hb
      _ ≤ S * 1 := mul_le_mul_of_nonneg_left he hS0
      _ = S := mul_one S
  have c1 := cross r1 d1 d2 hn2 h1
  have c2 := cross r2 d2 d1 hn1 h2
  have expand : ∑ j, (r1 j - r2 j) * (d1 j - d2 j) =
      (∑ j, d1 j * r1 j - ∑ j, d2 j * r1 j) + (∑ j, d2 j * r2 j - ∑ j, d1 j * r2 j) := by
    simp only [← Finset.sum_sub_distrib, ← Finset.sum_add_distrib]
    exact Finset.sum_congr rfl fun j _ => by ring
  rw [expand]
  linarith

omit [DecidableEq ι] in
/-- **Uniqueness of the small-gain limit in data space.** Two residual curves on
`[0, T]` that start at the same point and move, from the right, by
`ė = −Σ_j d_j(t) a_j` with `d(t)` of ℓ1 norm at most one attaining the peak of
the residual dirty image `⟪e(t), a_j⟫` (a subgradient of the ℓ∞ norm there),
coincide on `[0, T]`. Both the small-gain limit of CLEAN and that of forward
stagewise are such curves (`research/clean-implicit-objective.md`, Theorem A). -/
theorem flow_residual_unique (a : ι → E) {T : ℝ} (e1 e2 : ℝ → E) (d1 d2 : ℝ → ι → ℝ)
    (hc1 : ContinuousOn e1 (Icc 0 T)) (hc2 : ContinuousOn e2 (Icc 0 T))
    (hd1 : ∀ t ∈ Ico 0 T, HasDerivWithinAt e1 (-∑ j, d1 t j • a j) (Ici t) t)
    (hd2 : ∀ t ∈ Ico 0 T, HasDerivWithinAt e2 (-∑ j, d2 t j • a j) (Ici t) t)
    (hn1 : ∀ t ∈ Ico 0 T, l1 (d1 t) ≤ 1) (hn2 : ∀ t ∈ Ico 0 T, l1 (d2 t) ≤ 1)
    (hs1 : ∀ t ∈ Ico 0 T, ∀ k, |⟪e1 t, a k⟫_ℝ| ≤ ∑ j, d1 t j * ⟪e1 t, a j⟫_ℝ)
    (hs2 : ∀ t ∈ Ico 0 T, ∀ k, |⟪e2 t, a k⟫_ℝ| ≤ ∑ j, d2 t j * ⟪e2 t, a j⟫_ℝ)
    (h0 : e1 0 = e2 0) : ∀ t ∈ Icc 0 T, e1 t = e2 t := by
  set f : ℝ → ℝ := fun t => ‖e1 t - e2 t‖ ^ 2 with hf
  have hcont : ContinuousOn f (Icc 0 T) := ((hc1.sub hc2).norm).pow 2
  have hderiv : ∀ t ∈ Ico 0 T, HasDerivWithinAt f
      (2 * ⟪e1 t - e2 t, -∑ j, d1 t j • a j - -∑ j, d2 t j • a j⟫_ℝ) (Ici t) t :=
    fun t ht => ((hd1 t ht).sub (hd2 t ht)).norm_sq
  have hneg : ∀ t ∈ Ico 0 T,
      2 * ⟪e1 t - e2 t, -∑ j, d1 t j • a j - -∑ j, d2 t j • a j⟫_ℝ ≤ 0 := by
    intro t ht
    have hmono := subgradient_monotone (fun j => ⟪e1 t, a j⟫_ℝ) (fun j => ⟪e2 t, a j⟫_ℝ)
      (d1 t) (d2 t) (hn1 t ht) (hn2 t ht) (hs1 t ht) (hs2 t ht)
    have hin : ⟪e1 t - e2 t, -∑ j, d1 t j • a j - -∑ j, d2 t j • a j⟫_ℝ =
        -∑ j, (⟪e1 t, a j⟫_ℝ - ⟪e2 t, a j⟫_ℝ) * (d1 t j - d2 t j) := by
      rw [inner_sub_right, inner_neg_right, inner_neg_right, inner_sum_smul, inner_sum_smul]
      have hsum : ∑ j, (⟪e1 t, a j⟫_ℝ - ⟪e2 t, a j⟫_ℝ) * (d1 t j - d2 t j) =
          ∑ j, d1 t j * ⟪e1 t - e2 t, a j⟫_ℝ - ∑ j, d2 t j * ⟪e1 t - e2 t, a j⟫_ℝ := by
        rw [← Finset.sum_sub_distrib]
        refine Finset.sum_congr rfl fun j _ => ?_
        rw [inner_sub_left]
        ring
      rw [hsum]
      ring
    rw [hin]
    linarith
  have hle : ∀ t ∈ Icc 0 T, f t ≤ 0 := by
    intro t ht
    refine image_le_of_deriv_right_le_deriv_boundary (B := fun _ => 0) (B' := fun _ => 0)
      hcont hderiv ?_ continuousOn_const (fun x _ => hasDerivWithinAt_const _ _ _) hneg ht
    simp [hf, h0]
  intro t ht
  have h := hle t ht
  have hz : ‖e1 t - e2 t‖ ^ 2 = 0 := le_antisymm h (sq_nonneg _)
  rw [pow_eq_zero_iff two_ne_zero, norm_eq_zero, sub_eq_zero] at hz
  exact hz

end Clean
