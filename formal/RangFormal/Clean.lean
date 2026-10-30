/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import Mathlib

/-!
# Högbom CLEAN as greedy coordinate descent: the convergence core

The companion of `research/clean-theory.md`. The data live in a real inner
product space `E` (weighted visibilities); each pixel `i : ι` has an atom
`a i : E`, the response of a unit point source there, of norm one. For a
model `m : ι → ℝ` the residual is `e(m) = v − Σ_i m_i • a_i`, the misfit is
`Q(m) = ‖e(m)‖² / 2`, and the residual dirty image is `r_i(m) = ⟪e(m), a_i⟫`,
the negative gradient of `Q`. One CLEAN step at pixel `p` with gain `γ`
adds `γ r_p` to `m_p`.

Results, in the order of the note:

* `misfit_step` (Theorem 1, Schwarz 1978 in Gram form): the exact identity
  `Q(m') = Q(m) − γ(2−γ)/2 · r_p²`, for any pick and any gain. No positivity
  hypothesis appears: the point-spread function is the Gram matrix of the
  atoms, so it is positive semidefinite by construction.
* `misfit_step_le`: descent for `0 < γ < 2`.
* `sum_peak_sq_le`, `peak_tendsto_zero` (Theorem 2): along any CLEAN
  sequence `Σ_k r_{p_k}² ≤ 2 Q_0 / (γ(2−γ))`, so the picked peaks tend to zero.
* `dirty_tendsto_zero` (Theorem 2, greedy picks): with a `τ`-weak greedy
  pick rule the whole residual dirty image tends to zero.
* `misfit_geometric` (Theorem 3): a lower bound `κ` on the greedy ratio
  `r_{p_k}² / (2 Q_k)` gives `Q_K ≤ (1 − γ(2−γ)κ)^K Q_0`.
* `greedy_pick_in_support` (Theorem 4, the coherence condition): if the
  residual is a combination of `k` atoms and `2μk < 1 + μ` for the coherence
  `μ`, the largest residual peak lies on that support, so every greedy pick
  stays on it.
-/

open scoped InnerProductSpace
open Filter Topology Finset

namespace Clean

variable {E : Type*} [NormedAddCommGroup E] [InnerProductSpace ℝ E]
variable {ι : Type*} [Fintype ι] [DecidableEq ι]

/-- The residual `v − Σ_i m_i • a_i`. -/
noncomputable def residual (v : E) (a : ι → E) (m : ι → ℝ) : E :=
  v - ∑ i, m i • a i

/-- The misfit `‖e‖² / 2`. -/
noncomputable def misfit (v : E) (a : ι → E) (m : ι → ℝ) : ℝ :=
  ‖residual v a m‖ ^ 2 / 2

/-- The residual dirty image `r_p = ⟪e, a_p⟫`. -/
noncomputable def dirty (v : E) (a : ι → E) (m : ι → ℝ) (p : ι) : ℝ :=
  ⟪residual v a m, a p⟫_ℝ

/-- One CLEAN step at pixel `p` with gain `γ`: `m_p ← m_p + γ r_p`. -/
noncomputable def step (v : E) (a : ι → E) (γ : ℝ) (m : ι → ℝ) (p : ι) : ι → ℝ :=
  m + Pi.single p (γ * dirty v a m p)

omit [DecidableEq ι] in
theorem misfit_nonneg (v : E) (a : ι → E) (m : ι → ℝ) : 0 ≤ misfit v a m := by
  unfold misfit; positivity

theorem sum_single_smul (c : ℝ) (p : ι) (a : ι → E) :
    ∑ i, (Pi.single p c : ι → ℝ) i • a i = c • a p := by
  simp [Pi.single_apply, ite_smul]

theorem residual_step (v : E) (a : ι → E) (γ : ℝ) (m : ι → ℝ) (p : ι) :
    residual v a (step v a γ m p) = residual v a m - (γ * dirty v a m p) • a p := by
  unfold residual step
  simp only [Pi.add_apply, add_smul, Finset.sum_add_distrib, sum_single_smul]
  abel

/-- **Theorem 1.** The exact one-step change of the misfit. -/
theorem misfit_step (v : E) (a : ι → E) (γ : ℝ) (m : ι → ℝ) (p : ι) (hp : ‖a p‖ = 1) :
    misfit v a (step v a γ m p) = misfit v a m - γ * (2 - γ) / 2 * (dirty v a m p) ^ 2 := by
  have h := residual_step v a γ m p
  unfold misfit dirty at *
  rw [h, norm_sub_sq_real, norm_smul, hp, mul_one, Real.norm_eq_abs, sq_abs,
    real_inner_smul_right]
  ring

/-- Descent for every gain in the open window `(0, 2)`. -/
theorem misfit_step_le (v : E) (a : ι → E) {γ : ℝ} (m : ι → ℝ) (p : ι) (hp : ‖a p‖ = 1)
    (h0 : 0 < γ) (h2 : γ < 2) :
    misfit v a (step v a γ m p) ≤ misfit v a m := by
  rw [misfit_step v a γ m p hp]
  have h3 : 0 ≤ γ * (2 - γ) := mul_nonneg h0.le (by linarith)
  nlinarith [mul_nonneg h3 (sq_nonneg (dirty v a m p))]

/-- The CLEAN sequence from the empty model under a pick rule. -/
noncomputable def iterate (v : E) (a : ι → E) (γ : ℝ) (pick : (ι → ℝ) → ι) : ℕ → (ι → ℝ)
  | 0 => 0
  | k + 1 => step v a γ (iterate v a γ pick k) (pick (iterate v a γ pick k))

/-- The residual value at the pixel picked at step `k` (the component is `γ` times it). -/
noncomputable def peak (v : E) (a : ι → E) (γ : ℝ) (pick : (ι → ℝ) → ι) (k : ℕ) : ℝ :=
  dirty v a (iterate v a γ pick k) (pick (iterate v a γ pick k))

variable (v : E) (a : ι → E) (γ : ℝ) (pick : (ι → ℝ) → ι)

theorem misfit_iterate_succ (hall : ∀ i, ‖a i‖ = 1) (k : ℕ) :
    misfit v a (iterate v a γ pick (k + 1)) =
      misfit v a (iterate v a γ pick k) - γ * (2 - γ) / 2 * (peak v a γ pick k) ^ 2 :=
  misfit_step v a γ _ _ (hall _)

theorem misfit_iterate (hall : ∀ i, ‖a i‖ = 1) (K : ℕ) :
    misfit v a (iterate v a γ pick K) =
      misfit v a 0 - γ * (2 - γ) / 2 * ∑ k ∈ Finset.range K, (peak v a γ pick k) ^ 2 := by
  induction K with
  | zero => simp [iterate]
  | succ K ih =>
    rw [misfit_iterate_succ v a γ pick hall, ih, Finset.sum_range_succ]
    ring

/-- **Theorem 2.** The picked peaks are square-summable with an explicit bound. -/
theorem sum_peak_sq_le (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2) (K : ℕ) :
    ∑ k ∈ Finset.range K, (peak v a γ pick k) ^ 2 ≤ 2 * misfit v a 0 / (γ * (2 - γ)) := by
  have hpos : 0 < γ * (2 - γ) := mul_pos h0 (by linarith)
  have h := misfit_iterate v a γ pick hall K
  have hQ := misfit_nonneg v a (iterate v a γ pick K)
  rw [le_div_iff₀ hpos]
  nlinarith [h, hQ]

theorem summable_peak_sq (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2) :
    Summable (fun k => (peak v a γ pick k) ^ 2) :=
  summable_of_sum_range_le (fun _ => sq_nonneg _) (sum_peak_sq_le v a γ pick hall h0 h2)

/-- The picked peaks tend to zero. -/
theorem peak_tendsto_zero (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2) :
    Tendsto (peak v a γ pick) atTop (𝓝 0) := by
  have h := (summable_peak_sq v a γ pick hall h0 h2).tendsto_atTop_zero
  have habs : Tendsto (fun k => |peak v a γ pick k|) atTop (𝓝 0) := by
    have := h.sqrt
    simpa [Real.sqrt_sq_eq_abs] using this
  refine tendsto_of_tendsto_of_tendsto_of_le_of_le (g := fun k => -|peak v a γ pick k|)
    (h := fun k => |peak v a γ pick k|) ?_ habs ?_ ?_
  · simpa using habs.neg
  · intro k; exact neg_abs_le _
  · intro k; exact le_abs_self _

/-- A `τ`-weak greedy pick rule: the picked residual is at least `τ` times
every other one (`τ = 1` is Högbom's argmax). -/
def WeakGreedy (τ : ℝ) : Prop :=
  ∀ m i, τ * |dirty v a m i| ≤ |dirty v a m (pick m)|

/-- **Theorem 2, greedy form.** Under a weak greedy pick rule the residual dirty
image tends to zero at every pixel. -/
theorem dirty_tendsto_zero (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2) {τ : ℝ}
    (hτ : 0 < τ) (hg : WeakGreedy v a pick τ) (i : ι) :
    Tendsto (fun k => dirty v a (iterate v a γ pick k) i) atTop (𝓝 0) := by
  have hpk := peak_tendsto_zero v a γ pick hall h0 h2
  have habs : Tendsto (fun k => |peak v a γ pick k| / τ) atTop (𝓝 0) := by
    simpa using hpk.abs.div_const τ
  have bound : ∀ k, |dirty v a (iterate v a γ pick k) i| ≤ |peak v a γ pick k| / τ := by
    intro k
    have hpick : τ * |dirty v a (iterate v a γ pick k) i| ≤ |peak v a γ pick k| := hg _ _
    rw [le_div_iff₀ hτ]
    linarith
  refine tendsto_of_tendsto_of_tendsto_of_le_of_le (g := fun k => -(|peak v a γ pick k| / τ))
    (h := fun k => |peak v a γ pick k| / τ) ?_ habs ?_ ?_
  · simpa using habs.neg
  · intro k
    have := bound k
    linarith [neg_abs_le (dirty v a (iterate v a γ pick k) i)]
  · intro k
    have := bound k
    linarith [le_abs_self (dirty v a (iterate v a γ pick k) i)]

/-- **Theorem 3.** A lower bound `κ` on the greedy ratio `r_{p_k}² / (2 Q_k)` along
the sequence gives a geometric rate. -/
theorem misfit_geometric (hall : ∀ i, ‖a i‖ = 1) (h0 : 0 < γ) (h2 : γ < 2) {κ : ℝ}
    (hrate : 0 ≤ 1 - γ * (2 - γ) * κ)
    (hgreedy : ∀ k, 2 * κ * misfit v a (iterate v a γ pick k) ≤ (peak v a γ pick k) ^ 2)
    (K : ℕ) :
    misfit v a (iterate v a γ pick K) ≤ (1 - γ * (2 - γ) * κ) ^ K * misfit v a 0 := by
  induction K with
  | zero => simp [iterate]
  | succ K ih =>
    rw [misfit_iterate_succ v a γ pick hall, pow_succ]
    have hg := hgreedy K
    have hpos : 0 ≤ γ * (2 - γ) := mul_nonneg h0.le (by linarith)
    have step1 : misfit v a (iterate v a γ pick K) - γ * (2 - γ) / 2 * (peak v a γ pick K) ^ 2 ≤
        (1 - γ * (2 - γ) * κ) * misfit v a (iterate v a γ pick K) := by
      nlinarith [mul_le_mul_of_nonneg_left hg hpos]
    calc misfit v a (iterate v a γ pick K) - γ * (2 - γ) / 2 * (peak v a γ pick K) ^ 2
        ≤ (1 - γ * (2 - γ) * κ) * misfit v a (iterate v a γ pick K) := step1
      _ ≤ (1 - γ * (2 - γ) * κ) * ((1 - γ * (2 - γ) * κ) ^ K * misfit v a 0) :=
          mul_le_mul_of_nonneg_left ih hrate
      _ = (1 - γ * (2 - γ) * κ) ^ K * (1 - γ * (2 - γ) * κ) * misfit v a 0 := by ring

/-- Coherence: distinct atoms have `|⟪a_i, a_j⟫| ≤ μ`. For CLEAN this is the
peak absolute sidelobe of the point-spread function within the image. -/
def Coherent (a : ι → E) (μ : ℝ) : Prop :=
  ∀ i j, i ≠ j → |⟪a i, a j⟫_ℝ| ≤ μ

omit [Fintype ι] in
/-- **Theorem 4** (the coherence condition for greedy selection). If the residual is
a combination `Σ_{i∈S} c_i a_i` of the atoms on a support `S` with `|S| = k`, not all
`c_i` zero, and `2μk < 1 + μ`, then the largest `|⟪e, a_q⟫|` is attained on `S`:
Högbom's argmax lands on the support. Applied inductively from a `k`-sparse
sky, every CLEAN component lands on a true source. -/
theorem greedy_pick_in_support (hall : ∀ i, ‖a i‖ = 1) {μ : ℝ} (hμ0 : 0 ≤ μ)
    (hμ : Coherent a μ) (S : Finset ι) (c : ι → ℝ) (hc : ∃ i ∈ S, c i ≠ 0)
    (hk : 2 * μ * S.card < 1 + μ) :
    ∃ p ∈ S, ∀ q ∉ S,
      |⟪∑ i ∈ S, c i • a i, a q⟫_ℝ| < |⟪∑ i ∈ S, c i • a i, a p⟫_ℝ| := by
  obtain ⟨i₀, hi₀, hci₀⟩ := hc
  obtain ⟨p, hpS, hpmax⟩ := S.exists_max_image (fun i => |c i|) ⟨i₀, hi₀⟩
  have hcp : 0 < |c p| := lt_of_lt_of_le (abs_pos.mpr hci₀) (hpmax i₀ hi₀)
  set L := ∑ i ∈ S, |c i| with hL
  have hLk : L ≤ S.card * |c p| := by
    calc L = ∑ i ∈ S, |c i| := rfl
      _ ≤ ∑ _i ∈ S, |c p| := Finset.sum_le_sum fun i hi => hpmax i hi
      _ = S.card * |c p| := by simp
  -- expand the inner products
  have expand : ∀ q, ⟪∑ i ∈ S, c i • a i, a q⟫_ℝ = ∑ i ∈ S, c i * ⟪a i, a q⟫_ℝ := by
    intro q
    rw [sum_inner]
    exact Finset.sum_congr rfl fun i _ => real_inner_smul_left _ _ _
  refine ⟨p, hpS, fun q hq => ?_⟩
  -- off the support: |⟪e, a_q⟫| ≤ μ L
  have hoff : |⟪∑ i ∈ S, c i • a i, a q⟫_ℝ| ≤ μ * L := by
    rw [expand, hL, Finset.mul_sum]
    refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun i hi => ?_)
    rw [abs_mul]
    have hiq : i ≠ q := fun h => hq (h ▸ hi)
    calc |c i| * |⟪a i, a q⟫_ℝ| ≤ |c i| * μ :=
          mul_le_mul_of_nonneg_left (hμ i q hiq) (abs_nonneg _)
      _ = μ * |c i| := mul_comm _ _
  -- on the support: |⟪e, a_p⟫| ≥ |c_p| − μ (L − |c_p|)
  have hon : |c p| - μ * (L - |c p|) ≤ |⟪∑ i ∈ S, c i • a i, a p⟫_ℝ| := by
    rw [expand, ← Finset.add_sum_erase S _ hpS]
    have hpp : ⟪a p, a p⟫_ℝ = 1 := by
      rw [real_inner_self_eq_norm_sq, hall p]; norm_num
    rw [hpp, mul_one]
    have htail : |∑ i ∈ S.erase p, c i * ⟪a i, a p⟫_ℝ| ≤ μ * (L - |c p|) := by
      have hsplit : L - |c p| = ∑ i ∈ S.erase p, |c i| := by
        rw [hL, ← Finset.add_sum_erase S _ hpS]; ring
      rw [hsplit, Finset.mul_sum]
      refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun i hi => ?_)
      rw [abs_mul]
      have hip : i ≠ p := Finset.ne_of_mem_erase hi
      calc |c i| * |⟪a i, a p⟫_ℝ| ≤ |c i| * μ :=
            mul_le_mul_of_nonneg_left (hμ i p hip) (abs_nonneg _)
        _ = μ * |c i| := mul_comm _ _
    have := abs_sub_abs_le_abs_sub (c p) (-(∑ i ∈ S.erase p, c i * ⟪a i, a p⟫_ℝ))
    rw [abs_neg, sub_neg_eq_add] at this
    linarith
  -- combine: μ L < (1 + μ)|c_p| − μ L because 2 μ L ≤ 2 μ k |c_p| < (1 + μ) |c_p|
  have key : 2 * μ * L < (1 + μ) * |c p| := by
    calc 2 * μ * L ≤ 2 * μ * (S.card * |c p|) :=
          mul_le_mul_of_nonneg_left hLk (by positivity)
      _ = (2 * μ * S.card) * |c p| := by ring
      _ < (1 + μ) * |c p| := mul_lt_mul_of_pos_right hk hcp
  linarith

end Clean
