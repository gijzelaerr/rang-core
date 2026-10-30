/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.Clean

/-!
# CLEAN in finite dimension: a uniform greedy constant and geometric convergence

`research/clean-theory.md`, Theorem 3, first instance. The span of the atoms
is finite-dimensional, so its unit sphere is compact and the energy
`Σ_i ⟪s, a_i⟫²` has a positive minimum there: there is `κ > 0` with
`κ ‖s‖² ≤ max_i ⟪s, a_i⟫²` for every `s` in the span. For data in the span
and any `τ`-weak greedy pick rule this gives the geometric bound
`Q_K ≤ ρ^K Q_0` with `ρ = 1 − γ(2−γ) τ² κ < 1`, hence `Q_K → 0`.

* `exists_energy_bound`: the compactness argument.
* `exists_pixel_bound`: one pixel carries at least `κ / N` of `‖s‖²`.
* `misfit_geometric_of_mem_visible`: the geometric rate.
* `misfit_tendsto_zero_of_mem_visible`: the misfit tends to zero.
-/

open scoped InnerProductSpace
open Filter Topology Finset

namespace Clean

variable {E : Type*} [NormedAddCommGroup E] [InnerProductSpace ℝ E]
variable {ι : Type*} [Fintype ι] [DecidableEq ι] [Nonempty ι]

/-- The span of the atoms: the part of the data space an image can reach. -/
noncomputable abbrev visible (a : ι → E) : Submodule ℝ E :=
  Submodule.span ℝ (Set.range a)

/-- The energy of `s` on the atoms, `Σ_i ⟪s, a_i⟫²`. -/
noncomputable def energy (a : ι → E) (s : E) : ℝ :=
  ∑ i, ⟪s, a i⟫_ℝ ^ 2

omit [DecidableEq ι] [Nonempty ι] in
theorem energy_nonneg (a : ι → E) (s : E) : 0 ≤ energy a s :=
  Finset.sum_nonneg fun _ _ => sq_nonneg _

omit [DecidableEq ι] [Nonempty ι] in
theorem continuous_energy (a : ι → E) : Continuous (energy a) := by
  unfold energy
  exact continuous_finsetSum _ fun i _ => (continuous_id.inner continuous_const).pow 2

omit [DecidableEq ι] [Nonempty ι] in
theorem energy_smul (a : ι → E) (c : ℝ) (s : E) : energy a (c • s) = c ^ 2 * energy a s := by
  simp only [energy, real_inner_smul_left, mul_pow, Finset.mul_sum]

omit [DecidableEq ι] [Nonempty ι] in
/-- A vector of the span with zero energy is zero: `‖s‖² = Σ_i c_i ⟪s, a_i⟫`. -/
theorem eq_zero_of_energy_eq_zero (a : ι → E) {s : E} (hs : s ∈ visible a)
    (h : energy a s = 0) : s = 0 := by
  have hzero : ∀ i, ⟪s, a i⟫_ℝ = 0 := by
    intro i
    have hnonneg : ∀ j ∈ (univ : Finset ι), 0 ≤ ⟪s, a j⟫_ℝ ^ 2 := fun j _ => sq_nonneg _
    have := (Finset.sum_eq_zero_iff_of_nonneg hnonneg).mp h i (mem_univ i)
    exact (pow_eq_zero_iff two_ne_zero).mp this
  obtain ⟨c, rfl⟩ := (Submodule.mem_span_range_iff_exists_fun ℝ).mp hs
  have : ⟪∑ i, c i • a i, ∑ i, c i • a i⟫_ℝ = 0 := by
    rw [inner_sum]
    refine Finset.sum_eq_zero fun i _ => ?_
    rw [real_inner_smul_right, hzero i, mul_zero]
  exact inner_self_eq_zero.mp this

omit [DecidableEq ι] in
/-- The uniform greedy constant: a `κ ∈ (0, 1]` with `κ ‖s‖² ≤ energy a s` on the span. -/
theorem exists_energy_bound (a : ι → E) (hall : ∀ i, ‖a i‖ = 1) :
    ∃ κ : ℝ, 0 < κ ∧ κ ≤ 1 ∧ ∀ s ∈ visible a, κ * ‖s‖ ^ 2 ≤ energy a s := by
  have : FiniteDimensional ℝ (visible a) :=
    FiniteDimensional.span_of_finite ℝ (Set.finite_range a)
  set S : Set (visible a) := Metric.sphere (0 : visible a) 1 with hS
  have hcomp : IsCompact S := isCompact_sphere 0 1
  obtain ⟨i₀⟩ := ‹Nonempty ι›
  have hmem : a i₀ ∈ visible a := Submodule.subset_span (Set.mem_range_self i₀)
  have hne : S.Nonempty := ⟨⟨a i₀, hmem⟩, by simp [hS, hall i₀]⟩
  have hcont : ContinuousOn (fun x : visible a => energy a (x : E)) S :=
    ((continuous_energy a).comp continuous_subtype_val).continuousOn
  obtain ⟨x₀, hx₀S, hmin⟩ := hcomp.exists_isMinOn hne hcont
  have hx₀norm : ‖(x₀ : E)‖ = 1 := by
    have := hx₀S
    simpa [hS] using this
  have hpos : 0 < energy a (x₀ : E) := by
    rcases (energy_nonneg a (x₀ : E)).lt_or_eq with h | h
    · exact h
    · exfalso
      have h0 := eq_zero_of_energy_eq_zero a x₀.2 h.symm
      rw [h0, norm_zero] at hx₀norm
      exact zero_ne_one hx₀norm
  refine ⟨min (energy a (x₀ : E)) 1, lt_min hpos one_pos, min_le_right _ _, fun s hs => ?_⟩
  by_cases hs0 : s = 0
  · simp [hs0, energy]
  · have hnorm_pos : 0 < ‖s‖ := norm_pos_iff.mpr hs0
    set u : visible a := ⟨(‖s‖⁻¹ : ℝ) • s, (visible a).smul_mem _ hs⟩ with hu
    have huS : u ∈ S := by
      rw [hS, Metric.mem_sphere, dist_zero_right, Submodule.coe_norm]
      exact norm_smul_inv_norm hs0
    have hle : energy a (x₀ : E) ≤ energy a ((‖s‖⁻¹ : ℝ) • s) := (isMinOn_iff.mp hmin) u huS
    have hscale : energy a ((‖s‖⁻¹ : ℝ) • s) = ‖s‖⁻¹ ^ 2 * energy a s := energy_smul a _ s
    calc min (energy a (x₀ : E)) 1 * ‖s‖ ^ 2
        ≤ energy a (x₀ : E) * ‖s‖ ^ 2 :=
          mul_le_mul_of_nonneg_right (min_le_left _ _) (sq_nonneg _)
      _ ≤ energy a ((‖s‖⁻¹ : ℝ) • s) * ‖s‖ ^ 2 :=
          mul_le_mul_of_nonneg_right hle (sq_nonneg _)
      _ = energy a s := by
          rw [hscale]
          field_simp

omit [DecidableEq ι] in
/-- One pixel carries at least `κ / N` of `‖s‖²`: the greedy constant per pick. -/
theorem exists_pixel_bound (a : ι → E) (hall : ∀ i, ‖a i‖ = 1) :
    ∃ κ : ℝ, 0 < κ ∧ κ ≤ 1 ∧ ∀ s ∈ visible a, ∃ i, κ * ‖s‖ ^ 2 ≤ ⟪s, a i⟫_ℝ ^ 2 := by
  obtain ⟨κ, hκ, hκ1, hbound⟩ := exists_energy_bound a hall
  have hN : (0 : ℝ) < Fintype.card ι := by exact_mod_cast Fintype.card_pos
  have hN1 : (1 : ℝ) ≤ Fintype.card ι := by exact_mod_cast Fintype.card_pos
  refine ⟨κ / Fintype.card ι, div_pos hκ hN, (div_le_self hκ.le hN1).trans hκ1, fun s hs => ?_⟩
  obtain ⟨i, _, hi⟩ := Finset.exists_max_image univ (fun i => ⟪s, a i⟫_ℝ ^ 2) univ_nonempty
  refine ⟨i, ?_⟩
  have hsum : energy a s ≤ Fintype.card ι * ⟪s, a i⟫_ℝ ^ 2 := by
    have := Finset.sum_le_card_nsmul univ (fun j => ⟪s, a j⟫_ℝ ^ 2) (⟪s, a i⟫_ℝ ^ 2)
      (fun j hj => hi j hj)
    simpa [energy, nsmul_eq_mul, Finset.card_univ] using this
  have hb := hbound s hs
  rw [div_mul_eq_mul_div, div_le_iff₀ hN]
  nlinarith [hb, hsum]

variable (v : E) (a : ι → E) (γ : ℝ) (pick : (ι → ℝ) → ι)

omit [DecidableEq ι] [Nonempty ι] in
/-- The residuals of the CLEAN sequence stay in the span when the data lie in it. -/
theorem residual_mem_visible (hv : v ∈ visible a) (m : ι → ℝ) :
    residual v a m ∈ visible a := by
  unfold residual
  exact (visible a).sub_mem hv (Submodule.sum_mem _ fun i _ =>
    (visible a).smul_mem _ (Submodule.subset_span (Set.mem_range_self i)))

/-- **Theorem 3, finite-dimensional form.** For data in the span of the atoms and a
`τ`-weak greedy pick rule, the misfit decays geometrically with an explicit ratio. -/
theorem misfit_geometric_of_mem_visible (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2)
    {τ : ℝ} (hτ0 : 0 < τ) (hτ1 : τ ≤ 1) (hg : WeakGreedy v a pick τ) (hv : v ∈ visible a) :
    ∃ ρ : ℝ, 0 ≤ ρ ∧ ρ < 1 ∧
      ∀ K, misfit v a (iterate v a γ pick K) ≤ ρ ^ K * misfit v a 0 := by
  obtain ⟨κ, hκ, hκ1, hpix⟩ := exists_pixel_bound a hall
  have hg0 : 0 < γ * (2 - γ) := mul_pos h0 (by linarith)
  have hg1 : γ * (2 - γ) ≤ 1 := by nlinarith [sq_nonneg (γ - 1)]
  have hτsq : τ ^ 2 ≤ 1 := by nlinarith
  have hτκ : 0 < τ ^ 2 * κ := mul_pos (pow_pos hτ0 2) hκ
  have hτκ1 : τ ^ 2 * κ ≤ 1 := by nlinarith
  have hrate : 0 ≤ 1 - γ * (2 - γ) * (τ ^ 2 * κ) := by nlinarith
  refine ⟨1 - γ * (2 - γ) * (τ ^ 2 * κ), hrate, by nlinarith, fun K => ?_⟩
  apply misfit_geometric v a γ pick hall h0 h2 hrate ?_ K
  intro k
  obtain ⟨i, hi⟩ := hpix _ (residual_mem_visible v a hv (iterate v a γ pick k))
  have hi' : κ * ‖residual v a (iterate v a γ pick k)‖ ^ 2 ≤
      dirty v a (iterate v a γ pick k) i ^ 2 := hi
  have hpick : τ * |dirty v a (iterate v a γ pick k) i| ≤ |peak v a γ pick k| := hg _ _
  have e1 : τ ^ 2 * (κ * ‖residual v a (iterate v a γ pick k)‖ ^ 2) ≤
      τ ^ 2 * dirty v a (iterate v a γ pick k) i ^ 2 :=
    mul_le_mul_of_nonneg_left hi' (sq_nonneg τ)
  have e2 : τ ^ 2 * dirty v a (iterate v a γ pick k) i ^ 2 ≤ peak v a γ pick k ^ 2 := by
    have hsq := mul_self_le_mul_self (by positivity) hpick
    nlinarith [hsq, abs_mul_abs_self (peak v a γ pick k),
      abs_mul_abs_self (dirty v a (iterate v a γ pick k) i)]
  unfold misfit
  nlinarith [e1, e2]

/-- The misfit tends to zero for data in the span. -/
theorem misfit_tendsto_zero_of_mem_visible (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2)
    {τ : ℝ} (hτ0 : 0 < τ) (hτ1 : τ ≤ 1) (hg : WeakGreedy v a pick τ) (hv : v ∈ visible a) :
    Tendsto (fun K => misfit v a (iterate v a γ pick K)) atTop (𝓝 0) := by
  obtain ⟨ρ, h0ρ, hρ1, hbound⟩ :=
    misfit_geometric_of_mem_visible v a γ pick hall h0 h2 hτ0 hτ1 hg hv
  have hgeom : Tendsto (fun K => ρ ^ K * misfit v a 0) atTop (𝓝 0) := by
    simpa using (tendsto_pow_atTop_nhds_zero_of_lt_one h0ρ hρ1).mul_const (misfit v a 0)
  exact tendsto_of_tendsto_of_tendsto_of_le_of_le tendsto_const_nhds hgeom
    (fun K => misfit_nonneg v a _) hbound

end Clean
