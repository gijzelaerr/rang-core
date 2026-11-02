/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.Clark

/-!
# Major cycles as inexact Newton steps on the misfit

`research/clean-major-cycles.md`. A minor cycle places components `c k` at
pixels `p k` (`k < K`) against a working residual updated with an approximate
beam `Bt`; a major cycle then evaluates the true misfit.

* `misfit_add_batch`: the true change of the misfit for the whole batch is the
  quadratic `−Σ_k c_k r_{p_k} + ½ Σ_k Σ_l c_k c_l ⟪a_{p_k}, a_{p_l}⟫`.
* `half_double_sum`: for a symmetric kernel, half the double sum is the
  triangular sum the minor cycle accumulates step by step.
* `predicted`: what the minor cycle believes, `Σ_k (−c_k r̃_k + ½ c_k² Bt_kk)`
  with `r̃_k = r_{p_k} − Σ_{i<k} c_i Bt(p_k, p_i)`.
* `misfit_batch_gap`: the Gram-gap identity: true minus believed change is
  `Σ_k (Σ_{i<k} c_k c_i D(p_k, p_i) + ½ c_k² D(p_k, p_k))` with `D = ⟪a, a⟫ − Bt`.
* `misfit_batch_descent`: if the gap is at most `(1 − θ)` of the believed
  decrease, the true change is at most `θ` times the believed one.
* `gapForm_le`, `misfit_batch_descent_of_bound`: if `|D(q, j)| ≤ f j` for every
  target `q`, the gap is at most `Σ_k |c_k| (Σ_{i<k} |c_i| f(p_i) + ½|c_k| f(p_k))`,
  a number the minor cycle can keep; keeping it below `(1 − θ)|dQ̃|` is the
  provable per-cycle rule.
* `predicted_le_first`: with a unit-diagonal beam and gains in `[0, 2]`, every
  believed step is a decrease, so a cycle believes at least the decrease of its
  first (exact) step.
* `major_linear_rate`, `major_linear_rate_of_gap`: the outer theorem: with the
  descent factor `θ` and a forcing bound `dQ̃_k ≤ −c (Q_k − Q_∞)`, the misfit
  above any floor contracts by `1 − θ c` per major cycle.
* `truncation_error_le_pixel`, `clark_minor_cycle_descends_pixel`: Theorem 6
  with a per-component bound `f(p)` (the w-term of a double-size beam).
-/

open scoped InnerProductSpace
open Finset

namespace Clean

variable {E : Type*} [NormedAddCommGroup E] [InnerProductSpace ℝ E]
variable {ι : Type*} [Fintype ι] [DecidableEq ι]

/-- The pixel model of the components `c k` at pixels `p k`, `k < K`. -/
noncomputable def batch (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) : ι → ℝ :=
  ∑ k ∈ range K, Pi.single (p k) (c k)

omit [Fintype ι] in
theorem batch_apply (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) (i : ι) :
    batch p c K i = ∑ k ∈ range K, (Pi.single (p k) (c k) : ι → ℝ) i := by
  unfold batch
  exact Finset.sum_apply i _ _

theorem sum_batch_mul (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) (x : ι → ℝ) :
    ∑ i, batch p c K i * x i = ∑ k ∈ range K, c k * x (p k) := by
  simp only [batch_apply, Finset.sum_mul]
  rw [Finset.sum_comm]
  refine Finset.sum_congr rfl fun k _ => ?_
  rw [Finset.sum_eq_single (p k)]
  · simp
  · intro i _ hi
    simp [hi]
  · intro h
    exact absurd (Finset.mem_univ _) h

theorem sum_batch_smul (a : ι → E) (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) :
    ∑ i, batch p c K i • a i = ∑ k ∈ range K, c k • a (p k) := by
  simp only [batch_apply, Finset.sum_smul]
  rw [Finset.sum_comm]
  exact Finset.sum_congr rfl fun k _ => sum_single_smul (c k) (p k) a

omit [Fintype ι] [DecidableEq ι] in
theorem norm_sum_smul_sq (a : ι → E) (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) :
    ‖∑ k ∈ range K, c k • a (p k)‖ ^ 2 =
      ∑ k ∈ range K, ∑ l ∈ range K, c k * c l * ⟪a (p k), a (p l)⟫_ℝ := by
  rw [← real_inner_self_eq_norm_sq, sum_inner]
  refine Finset.sum_congr rfl fun k _ => ?_
  rw [inner_sum]
  refine Finset.sum_congr rfl fun l _ => ?_
  rw [real_inner_smul_left, real_inner_smul_right]
  ring

/-- **The exact change of the misfit for a batch.** `Q` is a quadratic with
Hessian the Gram matrix of the atoms. -/
theorem misfit_add_batch (v : E) (a : ι → E) (m : ι → ℝ) (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) :
    misfit v a (m + batch p c K) = misfit v a m - ∑ k ∈ range K, c k * dirty v a m (p k) +
      (∑ k ∈ range K, ∑ l ∈ range K, c k * c l * ⟪a (p k), a (p l)⟫_ℝ) / 2 := by
  rw [misfit_add_eq, sum_batch_mul, sum_batch_smul, norm_sum_smul_sq]

/-- Half a symmetric double sum is the triangular sum plus half the diagonal. -/
theorem half_double_sum (x : ℕ → ℝ) (G : ℕ → ℕ → ℝ) (hG : ∀ k l, G k l = G l k) (K : ℕ) :
    (∑ k ∈ range K, ∑ l ∈ range K, x k * x l * G k l) / 2 =
      ∑ k ∈ range K, (∑ i ∈ range k, x k * x i * G k i + x k ^ 2 * G k k / 2) := by
  induction K with
  | zero => simp
  | succ K ih =>
    have hsym : ∑ k ∈ range K, x k * x K * G k K = ∑ i ∈ range K, x K * x i * G K i := by
      refine Finset.sum_congr rfl fun k _ => ?_
      rw [hG k K]
      ring
    simp only [Finset.sum_range_succ, Finset.sum_add_distrib] at ih ⊢
    linear_combination ih + hsym / 2

/-- What a minor cycle believes it changed: `Σ_k (−c_k r̃_k + ½ c_k² Bt_kk)` with the
working residual `r̃_k = r_{p_k} − Σ_{i<k} c_i Bt(p_k, p_i)`. -/
noncomputable def predicted (r : ι → ℝ) (Bt : ι → ι → ℝ) (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) : ℝ :=
  ∑ k ∈ range K, (-(c k * (r (p k) - ∑ i ∈ range k, c i * Bt (p k) (p i))) +
    c k ^ 2 * Bt (p k) (p k) / 2)

/-- The quadratic form of a batch in a kernel `D`, in the order the minor cycle
meets its pairs. -/
noncomputable def gapForm (D : ι → ι → ℝ) (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) : ℝ :=
  ∑ k ∈ range K, (∑ i ∈ range k, c k * c i * D (p k) (p i) + c k ^ 2 * D (p k) (p k) / 2)

/-- **The Gram-gap identity.** The true change of the misfit minus the believed one is
the quadratic form of the batch in the beam the minor cycle got wrong. -/
theorem misfit_batch_gap (v : E) (a : ι → E) (m : ι → ℝ) (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ)
    (Bt : ι → ι → ℝ) :
    misfit v a (m + batch p c K) - misfit v a m - predicted (dirty v a m) Bt p c K =
      gapForm (fun q j => ⟪a q, a j⟫_ℝ - Bt q j) p c K := by
  have h := half_double_sum c (fun k l => ⟪a (p k), a (p l)⟫_ℝ)
    (fun k l => real_inner_comm _ _) K
  have hP : predicted (dirty v a m) Bt p c K =
      -(∑ k ∈ range K, c k * dirty v a m (p k)) +
        ∑ k ∈ range K, (∑ i ∈ range k, c k * c i * Bt (p k) (p i) +
          c k ^ 2 * Bt (p k) (p k) / 2) := by
    unfold predicted
    rw [← Finset.sum_neg_distrib, ← Finset.sum_add_distrib]
    refine Finset.sum_congr rfl fun k _ => ?_
    rw [mul_sub, Finset.mul_sum]
    have e : ∑ i ∈ range k, c k * (c i * Bt (p k) (p i)) =
        ∑ i ∈ range k, c k * c i * Bt (p k) (p i) :=
      Finset.sum_congr rfl fun i _ => by ring
    rw [e]
    ring
  have hD : gapForm (fun q j => ⟪a q, a j⟫_ℝ - Bt q j) p c K =
      ∑ k ∈ range K, (∑ i ∈ range k, c k * c i * ⟪a (p k), a (p i)⟫_ℝ +
          c k ^ 2 * ⟪a (p k), a (p k)⟫_ℝ / 2) -
        ∑ k ∈ range K, (∑ i ∈ range k, c k * c i * Bt (p k) (p i) +
          c k ^ 2 * Bt (p k) (p k) / 2) := by
    simp only [gapForm]
    rw [← Finset.sum_sub_distrib]
    refine Finset.sum_congr rfl fun k _ => ?_
    have e : ∑ i ∈ range k, c k * c i * (⟪a (p k), a (p i)⟫_ℝ - Bt (p k) (p i)) =
        ∑ i ∈ range k, c k * c i * ⟪a (p k), a (p i)⟫_ℝ -
          ∑ i ∈ range k, c k * c i * Bt (p k) (p i) := by
      rw [← Finset.sum_sub_distrib]
      exact Finset.sum_congr rfl fun i _ => by ring
    rw [e]
    ring
  rw [misfit_add_batch, h, hP, hD]
  ring

/-- Descent from a small gap, as plain arithmetic. -/
theorem descent_of_gap {dQ dQt gap θ : ℝ} (h : dQ = dQt + gap)
    (hgap : gap ≤ (1 - θ) * (-dQt)) : dQ ≤ θ * dQt := by
  have e : dQt + (1 - θ) * (-dQt) = θ * dQt := by ring
  rw [h]
  linarith

/-- **The per-cycle descent theorem.** If the Gram gap of a batch is at most `(1 − θ)`
of the decrease the minor cycle believes, the true misfit changes by at most `θ` times
the believed change. -/
theorem misfit_batch_descent (v : E) (a : ι → E) (m : ι → ℝ) (p : ℕ → ι) (c : ℕ → ℝ)
    (K : ℕ) (Bt : ι → ι → ℝ) {θ : ℝ}
    (hgap : gapForm (fun q j => ⟪a q, a j⟫_ℝ - Bt q j) p c K ≤
      (1 - θ) * (-predicted (dirty v a m) Bt p c K)) :
    misfit v a (m + batch p c K) - misfit v a m ≤ θ * predicted (dirty v a m) Bt p c K := by
  have h := misfit_batch_gap v a m p c K Bt
  exact descent_of_gap (by linarith) hgap

omit [Fintype ι] [DecidableEq ι] in
/-- **A bound the minor cycle can keep.** If the beam error at every target is at most
`f` of the source pixel, the gap is at most `Σ_k |c_k| (Σ_{i<k} |c_i| f(p_i) + ½|c_k| f(p_k))`. -/
theorem gapForm_le (D : ι → ι → ℝ) (f : ι → ℝ) (hD : ∀ q j, |D q j| ≤ f j) (p : ℕ → ι)
    (c : ℕ → ℝ) (K : ℕ) :
    |gapForm D p c K| ≤
      ∑ k ∈ range K, |c k| * (∑ i ∈ range k, |c i| * f (p i) + |c k| * f (p k) / 2) := by
  unfold gapForm
  refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun k _ => ?_)
  refine (abs_add_le _ _).trans ?_
  have h1 : |∑ i ∈ range k, c k * c i * D (p k) (p i)| ≤
      |c k| * ∑ i ∈ range k, |c i| * f (p i) := by
    rw [Finset.mul_sum]
    refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun i _ => ?_)
    rw [abs_mul, abs_mul]
    have hb := hD (p k) (p i)
    have hci := abs_nonneg (c i)
    have hck := abs_nonneg (c k)
    calc |c k| * |c i| * |D (p k) (p i)| ≤ |c k| * |c i| * f (p i) :=
          mul_le_mul_of_nonneg_left hb (mul_nonneg hck hci)
      _ = |c k| * (|c i| * f (p i)) := by ring
  have h2 : |c k ^ 2 * D (p k) (p k) / 2| ≤ |c k| * (|c k| * f (p k) / 2) := by
    rw [abs_div, abs_mul, abs_pow, abs_two]
    have hb := mul_le_mul_of_nonneg_left (hD (p k) (p k)) (sq_nonneg |c k|)
    calc |c k| ^ 2 * |D (p k) (p k)| / 2 ≤ |c k| ^ 2 * f (p k) / 2 := by linarith
      _ = |c k| * (|c k| * f (p k) / 2) := by ring
  calc _ ≤ |c k| * ∑ i ∈ range k, |c i| * f (p i) + |c k| * (|c k| * f (p k) / 2) :=
        add_le_add h1 h2
    _ = _ := by ring

/-- **The provable per-cycle rule.** If the beam is within `f(j)` of the Gram matrix for
every target and source `j`, and the running bound stays below `(1 − θ)` of the believed
decrease, the cycle lowers the true misfit by at least `θ` times the believed decrease. -/
theorem misfit_batch_descent_of_bound (v : E) (a : ι → E) (m : ι → ℝ) (p : ℕ → ι)
    (c : ℕ → ℝ) (K : ℕ) (Bt : ι → ι → ℝ) (f : ι → ℝ) {θ : ℝ}
    (hf : ∀ q j, |⟪a q, a j⟫_ℝ - Bt q j| ≤ f j)
    (hrule : ∑ k ∈ range K, |c k| * (∑ i ∈ range k, |c i| * f (p i) + |c k| * f (p k) / 2) ≤
      (1 - θ) * (-predicted (dirty v a m) Bt p c K)) :
    misfit v a (m + batch p c K) - misfit v a m ≤ θ * predicted (dirty v a m) Bt p c K := by
  apply misfit_batch_descent
  exact (le_abs_self _).trans ((gapForm_le _ f hf p c K).trans hrule)

omit [Fintype ι] [DecidableEq ι] in
/-- **The forcing term of a greedy minor cycle.** With a unit-diagonal beam and
`c_k = γ r̃_k`, `0 ≤ γ ≤ 2`, every believed step is a decrease, so the cycle believes at
least the decrease `γ(2−γ)/2 · r_{p_0}²` of its first step, which is exact. -/
theorem predicted_le_first (r : ι → ℝ) (Bt : ι → ι → ℝ) (p : ℕ → ι) (c : ℕ → ℝ) (K : ℕ)
    {γ : ℝ} (hγ0 : 0 ≤ γ) (hγ2 : γ ≤ 2) (hdiag : ∀ q, Bt q q = 1)
    (hc : ∀ k, c k = γ * (r (p k) - ∑ i ∈ range k, c i * Bt (p k) (p i))) (hK : 1 ≤ K) :
    predicted r Bt p c K ≤ -(γ * (2 - γ) / 2) * r (p 0) ^ 2 := by
  have ha : 0 ≤ γ * (2 - γ) / 2 := by
    have := mul_nonneg hγ0 (by linarith : (0 : ℝ) ≤ 2 - γ)
    linarith
  have hterm : ∀ k, -(c k * (r (p k) - ∑ i ∈ range k, c i * Bt (p k) (p i))) +
      c k ^ 2 * Bt (p k) (p k) / 2 =
        -(γ * (2 - γ) / 2) * (r (p k) - ∑ i ∈ range k, c i * Bt (p k) (p i)) ^ 2 := by
    intro k
    rw [hdiag, hc k]
    ring
  unfold predicted
  rw [Finset.sum_congr rfl fun k _ => hterm k]
  obtain ⟨K', rfl⟩ : ∃ K', K = K' + 1 := ⟨K - 1, by omega⟩
  rw [Finset.sum_range_succ']
  have h0 : ∑ i ∈ range 0, c i * Bt (p 0) (p i) = 0 := Finset.sum_range_zero _
  rw [h0, sub_zero]
  have hnonpos : ∑ k ∈ range K', -(γ * (2 - γ) / 2) *
      (r (p (k + 1)) - ∑ i ∈ range (k + 1), c i * Bt (p (k + 1)) (p i)) ^ 2 ≤ 0 := by
    refine Finset.sum_nonpos fun k _ => ?_
    have := mul_nonneg ha
      (sq_nonneg (r (p (k + 1)) - ∑ i ∈ range (k + 1), c i * Bt (p (k + 1)) (p i)))
    linarith
  linarith

/-- **The outer linear rate.** If every major cycle lowers the misfit by at least `θ`
times what its minor cycle believed, and every minor cycle believes a decrease of at
least `c` times the misfit above a floor `Q_∞`, the misfit above the floor contracts by
`1 − θ c` per major cycle. Nothing here needs the Gram matrix to be invertible. -/
theorem major_linear_rate (Q dQt : ℕ → ℝ) (Qinf θ c : ℝ) (hθ : 0 ≤ θ) (hθc : θ * c ≤ 1)
    (hstep : ∀ k, Q (k + 1) - Q k ≤ θ * dQt k)
    (hforce : ∀ k, dQt k ≤ -(c * (Q k - Qinf))) (K : ℕ) :
    Q K - Qinf ≤ (1 - θ * c) ^ K * (Q 0 - Qinf) := by
  induction K with
  | zero => simp
  | succ K ih =>
    have h2 := mul_le_mul_of_nonneg_left (hforce K) hθ
    have h3 : Q (K + 1) - Qinf ≤ (1 - θ * c) * (Q K - Qinf) := by
      calc Q (K + 1) - Qinf ≤ Q K - Qinf + θ * dQt K := by linarith [hstep K]
        _ ≤ Q K - Qinf + θ * -(c * (Q K - Qinf)) := by linarith
        _ = (1 - θ * c) * (Q K - Qinf) := by ring
    have h4 := mul_le_mul_of_nonneg_left ih (by linarith : 0 ≤ 1 - θ * c)
    rw [pow_succ]
    calc Q (K + 1) - Qinf ≤ (1 - θ * c) * (Q K - Qinf) := h3
      _ ≤ (1 - θ * c) * ((1 - θ * c) ^ K * (Q 0 - Qinf)) := h4
      _ = (1 - θ * c) ^ K * (1 - θ * c) * (Q 0 - Qinf) := by ring

/-- **The outer rate from the gap condition.** The same with the descent hypothesis
replaced by the gap identity and the provable rule of every cycle. -/
theorem major_linear_rate_of_gap (Q dQt gap : ℕ → ℝ) (Qinf θ c : ℝ) (hθ : 0 ≤ θ)
    (hθc : θ * c ≤ 1) (hid : ∀ k, Q (k + 1) - Q k = dQt k + gap k)
    (hgap : ∀ k, gap k ≤ (1 - θ) * (-dQt k)) (hforce : ∀ k, dQt k ≤ -(c * (Q k - Qinf)))
    (K : ℕ) : Q K - Qinf ≤ (1 - θ * c) ^ K * (Q 0 - Qinf) :=
  major_linear_rate Q dQt Qinf θ c hθ hθc (fun k => descent_of_gap (hid k) (hgap k)) hforce K

omit [Fintype ι] [DecidableEq ι] in
/-- **Truncation error with a per-component bound.** If the beam used for the working
residual differs from the exact one by at most `f p` for a component at `p` (any
target), the working and true residuals differ by at most `Σ_k |c_k| f(p_k)`. -/
theorem truncation_error_le_pixel (Bexact Btrunc : ι → ι → ℝ) (f : ι → ℝ)
    (hf : ∀ q p, |Bexact q p - Btrunc q p| ≤ f p) (pix : ℕ → ι) (c : ℕ → ℝ) (K : ℕ)
    (d : ι → ℝ) (q : ι) :
    |(d q - ∑ k ∈ range K, c k * Bexact q (pix k)) -
        (d q - ∑ k ∈ range K, c k * Btrunc q (pix k))| ≤ ∑ k ∈ range K, |c k| * f (pix k) := by
  have h : (d q - ∑ k ∈ range K, c k * Bexact q (pix k)) -
      (d q - ∑ k ∈ range K, c k * Btrunc q (pix k)) =
        -∑ k ∈ range K, c k * (Bexact q (pix k) - Btrunc q (pix k)) := by
    have hs : ∑ k ∈ range K, c k * (Bexact q (pix k) - Btrunc q (pix k)) =
        ∑ k ∈ range K, c k * Bexact q (pix k) - ∑ k ∈ range K, c k * Btrunc q (pix k) := by
      rw [← Finset.sum_sub_distrib]
      exact Finset.sum_congr rfl fun k _ => mul_sub _ _ _
    rw [hs]
    ring
  rw [h, abs_neg]
  refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun k _ => ?_)
  rw [abs_mul]
  exact mul_le_mul_of_nonneg_left (hf _ _) (abs_nonneg _)

/-- **Theorem 6 with a per-component bound.** If the subtracted beam is within `f i` of
the Gram matrix for a component at `i`, and `Σ_k |c_k| f(p_k) < (1 − γ/2)|r̃_p|`, the
next component `γ r̃_p` lowers the true misfit: the rule of `CycleRule::Provable`. -/
theorem clark_minor_cycle_descends_pixel (v : E) (a : ι → E) (m : ι → ℝ) (p : ι)
    (hp : ‖a p‖ = 1) {γ : ℝ} (hγ : 0 < γ) (Btrunc : ι → ι → ℝ) (f : ι → ℝ)
    (hf : ∀ q i, |⟪a i, a q⟫_ℝ - Btrunc q i| ≤ f i) (pix : ℕ → ι) (c : ℕ → ℝ) (K : ℕ)
    (htrue : ∀ q, dirty v a m q =
      dirty v a 0 q - ∑ k ∈ range K, c k * ⟪a (pix k), a q⟫_ℝ)
    (hrule : ∑ k ∈ range K, |c k| * f (pix k) <
      (1 - γ / 2) * |dirty v a 0 p - ∑ k ∈ range K, c k * Btrunc p (pix k)|) :
    misfit v a (m + Pi.single p
        (γ * (dirty v a 0 p - ∑ k ∈ range K, c k * Btrunc p (pix k)))) < misfit v a m := by
  refine clark_rule_descends v a m p hp hγ ?_ hrule
  rw [htrue p]
  exact truncation_error_le_pixel (fun q i => ⟪a i, a q⟫_ℝ) Btrunc f hf pix c K (dirty v a 0) p

end Clean
