/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.FiniteDim

/-!
# CLEAN for general data: the misfit floor and convergence of the model

`research/clean-theory.md`, Theorems 2 and 3 in full. Any data vector splits
as `v = w + z` with `w` in the span of the atoms and `z` orthogonal to every
atom. The dirty image, and therefore every CLEAN step, ignores `z`; the misfit
of every model is `Q(m) = Q_w(m) + ½‖z‖²`, so `Q_∞ = ½‖z‖²` is a floor no pixel
model can beat, and the span-case rate transfers:
`Q_K − Q_∞ ≤ ρ^K (Q_0 − Q_∞)`. The picked peaks then decay geometrically, the
model increments are summable, and the CLEAN model converges.

* `misfit_geometric_general`: the floor and the rate for arbitrary data.
* `iterate_tendsto`: the CLEAN model converges (in `ι → ℝ`).
-/

open scoped InnerProductSpace
open Filter Topology Finset

namespace Clean

variable {E : Type*} [NormedAddCommGroup E] [InnerProductSpace ℝ E]
variable {ι : Type*} [Fintype ι] [DecidableEq ι] [Nonempty ι]
variable (v : E) (a : ι → E) (γ : ℝ) (pick : (ι → ℝ) → ι)

omit [DecidableEq ι] [Nonempty ι] in
theorem residual_add_right (z : E) (m : ι → ℝ) :
    residual (v + z) a m = residual v a m + z := by
  unfold residual
  exact add_sub_right_comm v z _

omit [DecidableEq ι] [Nonempty ι] in
/-- Data orthogonal to every atom are invisible to the dirty image. -/
theorem dirty_add_orthogonal {z : E} (hz : z ∈ (visible a)ᗮ) (m : ι → ℝ) (i : ι) :
    dirty (v + z) a m i = dirty v a m i := by
  unfold dirty
  rw [residual_add_right, inner_add_left,
    Submodule.inner_left_of_mem_orthogonal (Submodule.subset_span (Set.mem_range_self i)) hz,
    add_zero]

omit [Nonempty ι] in
theorem step_add_orthogonal {z : E} (hz : z ∈ (visible a)ᗮ) (m : ι → ℝ) (p : ι) :
    step (v + z) a γ m p = step v a γ m p := by
  unfold step
  rw [dirty_add_orthogonal v a hz]

omit [Nonempty ι] in
/-- The CLEAN sequence ignores the invisible part of the data. -/
theorem iterate_add_orthogonal {z : E} (hz : z ∈ (visible a)ᗮ) (k : ℕ) :
    iterate (v + z) a γ pick k = iterate v a γ pick k := by
  induction k with
  | zero => rfl
  | succ k ih => rw [iterate, iterate, ih, step_add_orthogonal v a γ hz]

omit [DecidableEq ι] [Nonempty ι] in
/-- The misfit splits: `Q_{w+z}(m) = Q_w(m) + ½‖z‖²` for `w` in the span and `z` orthogonal. -/
theorem misfit_add_orthogonal (hv : v ∈ visible a) {z : E} (hz : z ∈ (visible a)ᗮ)
    (m : ι → ℝ) : misfit (v + z) a m = misfit v a m + ‖z‖ ^ 2 / 2 := by
  unfold misfit
  rw [residual_add_right, norm_add_sq_real,
    Submodule.inner_right_of_mem_orthogonal (residual_mem_visible v a hv m) hz]
  ring

omit [DecidableEq ι] [Nonempty ι] in
theorem weakGreedy_of_add_orthogonal {z : E} (hz : z ∈ (visible a)ᗮ) {τ : ℝ}
    (hg : WeakGreedy (v + z) a pick τ) : WeakGreedy v a pick τ := by
  intro m i
  have := hg m i
  rwa [dirty_add_orthogonal v a hz, dirty_add_orthogonal v a hz] at this

/-- **Theorems 2 and 3 for arbitrary data.** There is a floor `Q_∞` below every
model's misfit, and the CLEAN misfit approaches it geometrically under any
`τ`-weak greedy pick rule. -/
theorem misfit_geometric_general (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2) {τ : ℝ}
    (hτ0 : 0 < τ) (hτ1 : τ ≤ 1) (hg : WeakGreedy v a pick τ) :
    ∃ qinf : ℝ, (∀ m, qinf ≤ misfit v a m) ∧ ∃ ρ : ℝ, 0 ≤ ρ ∧ ρ < 1 ∧
      ∀ K, misfit v a (iterate v a γ pick K) - qinf ≤ ρ ^ K * (misfit v a 0 - qinf) := by
  have : FiniteDimensional ℝ (visible a) :=
    FiniteDimensional.span_of_finite ℝ (Set.finite_range a)
  have : CompleteSpace (visible a) := FiniteDimensional.complete ℝ _
  obtain ⟨w, hw, z, hz, rfl⟩ := (visible a).exists_add_mem_mem_orthogonal v
  refine ⟨‖z‖ ^ 2 / 2, fun m => ?_, ?_⟩
  · rw [misfit_add_orthogonal w a hw hz m]
    linarith [misfit_nonneg w a m]
  · obtain ⟨ρ, h0ρ, hρ1, hbound⟩ := misfit_geometric_of_mem_visible w a γ pick hall h0 h2 hτ0 hτ1
      (weakGreedy_of_add_orthogonal w a pick hz hg) hw
    refine ⟨ρ, h0ρ, hρ1, fun K => ?_⟩
    rw [iterate_add_orthogonal w a γ pick hz, misfit_add_orthogonal w a hw hz,
      misfit_add_orthogonal w a hw hz]
    linarith [hbound K]

omit [Nonempty ι] in
/-- The CLEAN model is the sum of its components. -/
theorem iterate_eq_sum (K : ℕ) :
    iterate v a γ pick K =
      ∑ k ∈ Finset.range K, Pi.single (pick (iterate v a γ pick k)) (γ * peak v a γ pick k) := by
  induction K with
  | zero => simp [iterate]
  | succ K ih =>
    rw [Finset.sum_range_succ, ← ih]
    rfl

omit [Nonempty ι] in
/-- Each picked peak is bounded by the residual norm (Cauchy–Schwarz). -/
theorem abs_peak_le (hall : ∀ i, ‖a i‖ = 1) (k : ℕ) :
    |peak v a γ pick k| ≤ ‖residual v a (iterate v a γ pick k)‖ := by
  unfold peak dirty
  have := abs_real_inner_le_norm (residual v a (iterate v a γ pick k)) (a (pick (iterate v a γ pick k)))
  rwa [hall, mul_one] at this

/-- **The CLEAN model converges**, for data in the span of the atoms. -/
theorem iterate_tendsto_of_mem_visible (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2)
    {τ : ℝ} (hτ0 : 0 < τ) (hτ1 : τ ≤ 1) (hg : WeakGreedy v a pick τ) (hv : v ∈ visible a) :
    ∃ mlim : ι → ℝ, Tendsto (iterate v a γ pick) atTop (𝓝 mlim) := by
  obtain ⟨ρ, h0ρ, hρ1, hbound⟩ :=
    misfit_geometric_of_mem_visible v a γ pick hall h0 h2 hτ0 hτ1 hg hv
  set r := Real.sqrt ρ with hr
  have hr0 : 0 ≤ r := Real.sqrt_nonneg ρ
  have hr1 : r < 1 := (Real.sqrt_lt' one_pos).mpr (by simpa using hρ1)
  have hrsq : r ^ 2 = ρ := Real.sq_sqrt h0ρ
  set C := Real.sqrt (2 * misfit v a 0) with hC
  have hC0 : 0 ≤ C := Real.sqrt_nonneg _
  have hCsq : C ^ 2 = 2 * misfit v a 0 := Real.sq_sqrt (by linarith [misfit_nonneg v a 0])
  -- the increment at step k has norm `γ |peak_k| ≤ γ C r^k`
  have hpeak : ∀ k, |peak v a γ pick k| ≤ C * r ^ k := by
    intro k
    have h1 := abs_peak_le v a γ pick hall k
    have he : ‖residual v a (iterate v a γ pick k)‖ ^ 2 =
        2 * misfit v a (iterate v a γ pick k) := by
      unfold misfit; ring
    have h2 : ‖residual v a (iterate v a γ pick k)‖ ^ 2 ≤ (C * r ^ k) ^ 2 := by
      rw [he, mul_pow, hCsq, ← pow_mul, mul_comm k 2, pow_mul, hrsq]
      nlinarith [hbound k]
    have hnn : 0 ≤ C * r ^ k := mul_nonneg hC0 (pow_nonneg hr0 k)
    have h3 : ‖residual v a (iterate v a γ pick k)‖ ≤ C * r ^ k := by
      calc ‖residual v a (iterate v a γ pick k)‖
          = Real.sqrt (‖residual v a (iterate v a γ pick k)‖ ^ 2) :=
            (Real.sqrt_sq (norm_nonneg _)).symm
        _ ≤ Real.sqrt ((C * r ^ k) ^ 2) := Real.sqrt_le_sqrt h2
        _ = C * r ^ k := Real.sqrt_sq hnn
    exact h1.trans h3
  have hsum : Summable (fun k =>
      (Pi.single (pick (iterate v a γ pick k)) (γ * peak v a γ pick k) : ι → ℝ)) := by
    refine Summable.of_norm_bounded (g := fun k => γ * C * r ^ k) ?_ ?_
    · exact (summable_geometric_of_lt_one hr0 hr1).mul_left (γ * C)
    · intro k
      rw [Pi.norm_single, Real.norm_eq_abs, abs_mul, abs_of_pos h0, mul_assoc]
      exact mul_le_mul_of_nonneg_left (hpeak k) h0.le
  refine ⟨∑' k, (Pi.single (pick (iterate v a γ pick k)) (γ * peak v a γ pick k) : ι → ℝ), ?_⟩
  convert hsum.hasSum.tendsto_sum_nat using 1
  funext K
  exact iterate_eq_sum v a γ pick K

/-- **The CLEAN model converges** for arbitrary data. -/
theorem iterate_tendsto (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2) {τ : ℝ}
    (hτ0 : 0 < τ) (hτ1 : τ ≤ 1) (hg : WeakGreedy v a pick τ) :
    ∃ mlim : ι → ℝ, Tendsto (iterate v a γ pick) atTop (𝓝 mlim) := by
  have : FiniteDimensional ℝ (visible a) :=
    FiniteDimensional.span_of_finite ℝ (Set.finite_range a)
  have : CompleteSpace (visible a) := FiniteDimensional.complete ℝ _
  obtain ⟨w, hw, z, hz, rfl⟩ := (visible a).exists_add_mem_mem_orthogonal v
  obtain ⟨mlim, hm⟩ := iterate_tendsto_of_mem_visible w a γ pick hall h0 h2 hτ0 hτ1
    (weakGreedy_of_add_orthogonal w a pick hz hg) hw
  refine ⟨mlim, ?_⟩
  have hfun : iterate (w + z) a γ pick = iterate w a γ pick :=
    funext (iterate_add_orthogonal w a γ pick hz)
  rw [hfun]
  exact hm

end Clean
