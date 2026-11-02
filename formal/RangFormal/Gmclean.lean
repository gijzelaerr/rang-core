/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.Clean

/-!
# The arithmetic of a gmclean minor step

The companion of `research/gmclean.md`. Three short facts:

* `exact_value_identity`: a working map that subtracts `Btrunc` differs from
  the exact residual by the ignored beam `B − Btrunc` over the components.
  This is the per-step correction of gmclean.
* `exact_value_step`: a step taken with the exact value is a CLEAN step, so
  `misfit_step` applies whatever pixel the working map proposed.
* `weak_greedy_of_certificate`: the recorded certificate. If the working map
  is within `e` of the exact residual everywhere and bounded by `M`, then
  `|r_p| ≥ τ (M + e)` makes the pick `τ`-weak greedy; holding this along the
  run with `τ = τ_min` gives `dirty_tendsto_zero`.
-/

open scoped InnerProductSpace
open Finset

namespace Clean

variable {E : Type*} [NormedAddCommGroup E] [InnerProductSpace ℝ E]
variable {ι : Type*} [Fintype ι] [DecidableEq ι]

omit [DecidableEq ι] in
/-- The exact value from the working value: the correction is the ignored beam
over the components. -/
theorem exact_value_identity (r0 : ι → ℝ) (B Btrunc : ι → ι → ℝ) (c : ι → ℝ) (q : ι) :
    (r0 q - ∑ j, c j * B q j) =
      (r0 q - ∑ j, c j * Btrunc q j) - ∑ j, c j * (B q j - Btrunc q j) := by
  have h : ∑ j, c j * (B q j - Btrunc q j) =
      ∑ j, c j * B q j - ∑ j, c j * Btrunc q j := by
    rw [← Finset.sum_sub_distrib]
    exact Finset.sum_congr rfl fun j _ => by ring
  rw [h]
  ring

/-- A step with the exact value at any proposed pixel is a CLEAN step: the
misfit falls by exactly `γ(2−γ)/2 · r_p²`, with no condition on the working map. -/
theorem exact_value_step (v : E) (a : ι → E) (γ : ℝ) (m : ι → ℝ) (p : ι) (hp : ‖a p‖ = 1) :
    misfit v a (step v a γ m p) = misfit v a m - γ * (2 - γ) / 2 * (dirty v a m p) ^ 2 :=
  misfit_step v a γ m p hp

omit [Fintype ι] [DecidableEq ι] in
/-- The per-step certificate: a stale error at most `e` and a working map bounded
by `M` make `|r_p| ≥ τ (M + e)` a weak-greedy inequality at every pixel. -/
theorem certificate_bound (r rt : ι → ℝ) {e M τ : ℝ} (p : ι) (hτ : 0 ≤ τ)
    (herr : ∀ q, |r q - rt q| ≤ e) (hM : ∀ q, |rt q| ≤ M)
    (hcert : τ * (M + e) ≤ |r p|) (q : ι) : τ * |r q| ≤ |r p| := by
  have h1 : |r q| ≤ M + e := by
    have h2 : |r q| ≤ |r q - rt q| + |rt q| := by
      simpa using abs_add_le (r q - rt q) (rt q)
    linarith [herr q, hM q]
  exact (mul_le_mul_of_nonneg_left h1 hτ).trans hcert

omit [DecidableEq ι] in
/-- A run whose every step passes the certificate with `τ` follows a `τ`-weak
greedy rule, so `dirty_tendsto_zero` applies to it. -/
theorem weak_greedy_of_certificate (v : E) (a : ι → E) (pick : (ι → ℝ) → ι) {τ : ℝ}
    (hτ : 0 ≤ τ) (rt : (ι → ℝ) → ι → ℝ) (e M : (ι → ℝ) → ℝ)
    (herr : ∀ m q, |dirty v a m q - rt m q| ≤ e m) (hM : ∀ m q, |rt m q| ≤ M m)
    (hcert : ∀ m, τ * (M m + e m) ≤ |dirty v a m (pick m)|) :
    WeakGreedy v a pick τ := fun m i =>
  certificate_bound (dirty v a m) (rt m) (pick m) hτ (herr m) (hM m) (hcert m) i

end Clean
