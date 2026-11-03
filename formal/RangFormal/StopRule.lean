/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.MajorCycle
import RangFormal.Gemclean

/-!
# A stop rule for the minor cycle that is a theorem

`research/stop-rule-theorem.md`. A gemclean minor cycle works on `r̃ = r₀ − B c`,
with `B` the phase-centre beam, while the true residual is `r = r₀ − G c`, with
`G` the Gram matrix. Their difference is the beam error `E = G − B` over the
components of the cycle: nothing else, after the exact `2n` correction.

With `|E(q, j)| ≤ f j` and `e = Σ_k |c_k| f(p_k)`, the rule is: take the next step
at `p` only while `e ≤ κ |r̃_p|`, for a fixed `κ`. All statements are
finite-dimensional, and none assumes anything of `f` beyond being a bound.

* **The pick.** `pick_same_sign`, `pick_lower`, `pick_above_level`: for `κ < 1` the true
  residual at the pick has the working sign and at least `(1 − κ)` of its size,
  so a pixel whose true residual is below `(1 − κ) T` takes no component while the
  working peak is above `T`.
* **Descent.** `certified_step`: for `0 < γ` a step lowers the true misfit by at
  least `γ (1 − κ − γ/2) r̃_p²`. `certified_cycle_energy` sums this over a cycle.
* **Flux.** `certified_cycle_flux`: the flux placed by a cycle while the working
  peak is at least `T` is at most `ΔQ / ((1 − κ − γ/2) T)`.
* **One pixel.** `pixel_flux_le`, `no_flux_of_below`: the net flux at a pixel `q` is
  at most its excess `|r₀(q)| + S − (1 − κ) T` plus one step, `S` the reach of the
  other components' beams at `q`. This is the statement on false flux, and what
  it does not bound is in the note: a noise peak above the level is still cleaned.
* **Stopping point.** `stop_peak_le`, `peak_contraction`, `peak_geometric`: where the
  rule stops, `κ (1 − κ − γ/2) P_stop P_min ≤ f ΔQ`. With a greedy ratio `μ` on the
  reducible misfit the peak contracts by `f / (2 μ κ (1 − κ − γ/2))` in square per
  cycle: the small `f` of the w-term is what makes cycles few.
* **The measured `δ`.** `measured_le_column_sup`: a measured ratio sits below the
  column supremum. `stale_of_columns_le`: it bounds the next cycle if the next
  cycle's columns are within `ρ δ`. `measured_not_a_bound`: it does not otherwise,
  with `δ = 0` on one batch and error `1` per unit of flux on the next.
* **The w-term.** `phi_lipschitz`, `phi_moment_bound`: the first-order and moment
  bounds on `Φ(Δ, η) = Σ_k W_k [cos(φ_k + h_k) − cos φ_k]`, the form `E` takes.

Not proved here: `E = Φ` for the gridder's images, the range of `η` in the radius
of the component, and the supremum of `Φ` in `η` that the code samples.
-/

open scoped InnerProductSpace
open Finset

namespace Clean

variable {E : Type*} [NormedAddCommGroup E] [InnerProductSpace ℝ E]
variable {ι : Type*} [Fintype ι] [DecidableEq ι]

/-! ### The pick -/

/-- If the error at the pick is below the working value, the true residual has the
working sign. -/
theorem pick_same_sign {r rt e : ℝ} (herr : |r - rt| ≤ e) (hrule : e < |rt|) : 0 < r * rt := by
  have h := abs_le.mp herr
  rcases abs_cases rt with ⟨h1, h2⟩ | ⟨h1, h2⟩
  · have hrt : 0 < rt := by linarith [abs_nonneg (r - rt)]
    exact mul_pos (by linarith) hrt
  · have hrt : rt < 0 := by linarith
    exact mul_pos_of_neg_of_neg (by linarith) hrt

/-- The true residual at the pick is at least the working value less the error. -/
theorem pick_lower {r rt e : ℝ} (herr : |r - rt| ≤ e) : |rt| - e ≤ |r| := by
  have h : |rt| ≤ |r| + |r - rt| := by
    have := abs_sub_abs_le_abs_sub rt r
    rw [abs_sub_comm rt r] at this
    linarith
  linarith

/-- With `e ≤ κ |r̃|` the true residual is at least `(1 − κ) |r̃|`. -/
theorem pick_fraction {r rt e κ : ℝ} (herr : |r - rt| ≤ e) (hrule : e ≤ κ * |rt|) :
    (1 - κ) * |rt| ≤ |r| := by
  have := pick_lower herr
  linarith

/-- A working value above `T + e` means a true residual above `T`: a pixel whose true
residual is at most `T` is not picked at that level. -/
theorem pick_above_level {r rt e T : ℝ} (herr : |r - rt| ≤ e) (hrule : T + e < |rt|) : T < |r| := by
  have := pick_lower herr
  linarith

/-- The rule in the form the minor cycle holds: a pick with `|r̃| ≥ T` and `e ≤ κ |r̃|`,
`κ ≤ 1`, has a true residual of at least `(1 − κ) T`. -/
theorem pick_level {r rt e κ T : ℝ} (hκ : κ ≤ 1) (herr : |r - rt| ≤ e) (hrule : e ≤ κ * |rt|)
    (hT : T ≤ |rt|) : (1 - κ) * T ≤ |r| :=
  (mul_le_mul_of_nonneg_left hT (by linarith)).trans (pick_fraction herr hrule)

/-- What `pixel_flux_le` asks of a pick, from the rule: a certified pick above `T` has
`c r ≥ 0` and a true residual of at least `(1 − κ) T`. -/
theorem certified_pick {r rt e κ T γ : ℝ} (hκ : κ < 1) (hγ : 0 < γ) (hT : 0 < T)
    (herr : |r - rt| ≤ e) (hrule : e ≤ κ * |rt|) (hlevel : T ≤ |rt|) :
    0 ≤ γ * rt * r ∧ (1 - κ) * T ≤ |r| := by
  have hrt : 0 < |rt| := by linarith
  have hlt : e < |rt| := by nlinarith
  have hsign := pick_same_sign herr hlt
  refine ⟨?_, pick_level hκ.le herr hrule hlevel⟩
  have : γ * rt * r = γ * (r * rt) := by ring
  rw [this]
  exact (mul_pos hγ hsign).le

omit [Fintype ι] [DecidableEq ι] in
/-- The running error at any target from a per-pixel envelope `g q j` of the beam
error: the sharper form of `truncation_error_le_pixel`. -/
theorem stale_error_le_envelope (G B g : ι → ι → ℝ) (hg : ∀ q j, |G q j - B q j| ≤ g q j)
    (pix : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) (d : ι → ℝ) (q : ι) :
    |(d q - ∑ k ∈ range K, c k * G q (pix k)) - (d q - ∑ k ∈ range K, c k * B q (pix k))| ≤
      ∑ k ∈ range K, |c k| * g q (pix k) := by
  have h : (d q - ∑ k ∈ range K, c k * G q (pix k)) - (d q - ∑ k ∈ range K, c k * B q (pix k)) =
      -∑ k ∈ range K, c k * (G q (pix k) - B q (pix k)) := by
    have hs : ∑ k ∈ range K, c k * (G q (pix k) - B q (pix k)) =
        ∑ k ∈ range K, c k * G q (pix k) - ∑ k ∈ range K, c k * B q (pix k) := by
      rw [← Finset.sum_sub_distrib]
      exact Finset.sum_congr rfl fun k _ => mul_sub _ _ _
    rw [hs]
    ring
  rw [h, abs_neg]
  refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun k _ => ?_)
  rw [abs_mul]
  exact mul_le_mul_of_nonneg_left (hg _ _) (abs_nonneg _)

/-! ### Descent -/

/-- **The certified step.** A component `γ r̃_p` with `|r_p − r̃_p| ≤ e ≤ κ |r̃_p|` lowers
the true misfit by at least `γ (1 − κ − γ/2) r̃_p²`. For `κ < 1 − γ/2` this is the
descent rule `clark_rule_descends`, with a rate. -/
theorem certified_step (v : E) (a : ι → E) (m : ι → ℝ) (p : ι) (hp : ‖a p‖ = 1)
    {γ rt e κ : ℝ} (hγ : 0 < γ) (herr : |dirty v a m p - rt| ≤ e) (hrule : e ≤ κ * |rt|) :
    misfit v a (m + Pi.single p (γ * rt)) ≤ misfit v a m - γ * (1 - κ - γ / 2) * rt ^ 2 := by
  rw [misfit_add_single v a m p _ hp]
  have hcross : -(rt * (dirty v a m p - rt)) ≤ κ * rt ^ 2 := by
    have h1 : -(rt * (dirty v a m p - rt)) ≤ |rt * (dirty v a m p - rt)| := neg_le_abs _
    rw [abs_mul] at h1
    have h2 : |rt| * |dirty v a m p - rt| ≤ |rt| * (κ * |rt|) :=
      mul_le_mul_of_nonneg_left (herr.trans hrule) (abs_nonneg _)
    have h3 : |rt| * (κ * |rt|) = κ * rt ^ 2 := by
      rw [← sq_abs rt]
      ring
    linarith
  nlinarith [mul_le_mul_of_nonneg_left hcross hγ.le]

/-- Summed over a cycle: if every step lowers `Q` by at least `A x_t²`, the energy of
the picks is bounded by the decrease of the true misfit. -/
theorem certified_cycle_energy (Q x : ℕ → ℝ) {A : ℝ} (K : ℕ)
    (hstep : ∀ t < K, Q (t + 1) ≤ Q t - A * x t ^ 2) :
    A * ∑ t ∈ range K, x t ^ 2 ≤ Q 0 - Q K := by
  induction K with
  | zero => simp
  | succ K ih =>
    have h1 := ih fun t ht => hstep t (Nat.lt_succ_of_lt ht)
    have h2 := hstep K (Nat.lt_succ_self K)
    rw [Finset.sum_range_succ, mul_add]
    linarith

/-- The sum of `|x_t|` from their energy, when every `|x_t| ≥ T > 0`. -/
theorem sum_abs_le_energy (x : ℕ → ℝ) {T : ℝ} (K : ℕ)
    (hx : ∀ t < K, T ≤ |x t|) :
    T * ∑ t ∈ range K, |x t| ≤ ∑ t ∈ range K, x t ^ 2 := by
  rw [Finset.mul_sum]
  refine Finset.sum_le_sum fun t ht => ?_
  rw [← sq_abs (x t), sq]
  exact mul_le_mul_of_nonneg_right (hx t (Finset.mem_range.mp ht)) (abs_nonneg _)

/-- **The flux of a certified cycle.** If each step lowers `Q` by at least
`γ B x_t²` (`B = 1 − κ − γ/2 > 0`, from `certified_step`) and every working peak is at
least `T`, the flux placed is at most the decrease of the true misfit over `B T`. -/
theorem certified_cycle_flux (Q x : ℕ → ℝ) {γ B T : ℝ} (hγ : 0 < γ) (hB : 0 < B)
    (K : ℕ) (hstep : ∀ t < K, Q (t + 1) ≤ Q t - γ * B * x t ^ 2)
    (hx : ∀ t < K, T ≤ |x t|) :
    B * T * ∑ t ∈ range K, |γ * x t| ≤ Q 0 - Q K := by
  have henergy := certified_cycle_energy Q x K hstep
  have hflux := sum_abs_le_energy x K hx
  have hsum : ∑ t ∈ range K, |γ * x t| = γ * ∑ t ∈ range K, |x t| := by
    rw [Finset.mul_sum]
    exact Finset.sum_congr rfl fun t _ => by rw [abs_mul, abs_of_pos hγ]
  rw [hsum]
  have hpos : 0 < γ * B := mul_pos hγ hB
  have := mul_le_mul_of_nonneg_left hflux hpos.le
  nlinarith

/-! ### One pixel -/

omit [Fintype ι] in
/-- **The flux at one pixel.** The true residual at `q` through a run is its start, less
the flux `M t` placed at `q` (unit diagonal), less what the other components' beams
do there, which stays within `S`. If every pick at `q` has `c_t r_q(t) > 0` and
`|r_q(t)| ≥ L > 0` and `|c_t| ≤ C`, the net flux at `q` is at most the excess of
`|r₀(q)| + S` over `L`, plus one step. -/
theorem pixel_flux_le (G : ι → ι → ℝ) (hG : ∀ q, G q q = 1) (r0 : ι → ℝ) (q : ι) (p : ℕ → ι)
    (c : ℕ → ℝ) {S L C : ℝ} (hL : 0 < L) (hC : 0 ≤ C) (K : ℕ)
    (hS : ∀ t ≤ K, |∑ i ∈ (range t).filter (fun i => p i ≠ q), c i * G q (p i)| ≤ S)
    (hsign : ∀ t < K, p t = q →
      0 ≤ c t * (r0 q - ∑ i ∈ range t, c i * G q (p i)))
    (hlevel : ∀ t < K, p t = q → L ≤ |r0 q - ∑ i ∈ range t, c i * G q (p i)|)
    (hstep : ∀ t < K, p t = q → |c t| ≤ C) :
    |∑ i ∈ (range K).filter (fun i => p i = q), c i| ≤ max 0 (|r0 q| + S - L) + C := by
  set B := max 0 (|r0 q| + S - L) + C with hB
  have hB0 : 0 ≤ B := add_nonneg (le_max_left _ _) hC
  -- The residual splits into the flux at `q` and the rest.
  have hsplit : ∀ t, ∑ i ∈ range t, c i * G q (p i) =
      ∑ i ∈ (range t).filter (fun i => p i = q), c i +
        ∑ i ∈ (range t).filter (fun i => p i ≠ q), c i * G q (p i) := by
    intro t
    rw [← Finset.sum_filter_add_sum_filter_not (range t) (fun i => p i = q)]
    congr 1
    refine Finset.sum_congr rfl fun i hi => ?_
    rw [(Finset.mem_filter.mp hi).2, hG, mul_one]
  induction K with
  | zero => simpa using hB0
  | succ K ih =>
    have hprev := ih (fun t ht => hS t (Nat.le_succ_of_le ht))
      (fun t ht => hsign t (Nat.lt_succ_of_lt ht))
      (fun t ht => hlevel t (Nat.lt_succ_of_lt ht))
      (fun t ht => hstep t (Nat.lt_succ_of_lt ht))
    rw [Finset.range_add_one, Finset.filter_insert]
    by_cases hp : p K = q
    · rw [if_pos hp, Finset.sum_insert (by simp)]
      have hsK := hS K (Nat.le_succ K)
      have hlv := hlevel K (Nat.lt_succ_self K) hp
      have hsg := hsign K (Nat.lt_succ_self K) hp
      have hst := hstep K (Nat.lt_succ_self K) hp
      rw [hsplit K] at hlv hsg
      set M := ∑ i ∈ (range K).filter (fun i => p i = q), c i
      set R := ∑ i ∈ (range K).filter (fun i => p i ≠ q), c i * G q (p i)
      have hexcess : |r0 q| + S - L ≤ max 0 (|r0 q| + S - L) := le_max_right _ _
      have hr := le_abs_self (r0 q)
      have hr' := neg_abs_le (r0 q)
      have hR := abs_le.mp hsK
      have hM := abs_le.mp hprev
      have hc := abs_le.mp hst
      rcases le_abs'.mp hlv with hneg | hpos
      · -- The residual is at most `−L`, so the component is not positive.
        have hneg' : r0 q - (M + R) < 0 := by linarith
        have hc0 : c K ≤ 0 := by
          by_contra hcon
          have : c K * (r0 q - (M + R)) < 0 := mul_neg_of_pos_of_neg (not_le.mp hcon) hneg'
          linarith
        rw [abs_le]
        constructor <;> linarith
      · have hpos' : 0 < r0 q - (M + R) := by linarith
        have hc0 : 0 ≤ c K := by
          by_contra hcon
          have : c K * (r0 q - (M + R)) < 0 := mul_neg_of_neg_of_pos (not_le.mp hcon) hpos'
          linarith
        rw [abs_le]
        constructor <;> linarith
    · rw [if_neg hp]
      exact hprev

omit [Fintype ι] in
/-- **No flux below the level.** If `|r₀(q)| + S < L` the true residual at `q` stays below
`L` through the run, so a run in which every pick has a true residual of at least `L`
puts nothing at `q`. -/
theorem no_flux_of_below (G : ι → ι → ℝ) (r0 : ι → ℝ) (q : ι) (p : ℕ → ι)
    (c : ℕ → ℝ) {S L : ℝ} (hbelow : |r0 q| + S < L) (K : ℕ)
    (hS : ∀ t ≤ K, |∑ i ∈ (range t).filter (fun i => p i ≠ q), c i * G q (p i)| ≤ S)
    (hlevel : ∀ t < K, p t = q → L ≤ |r0 q - ∑ i ∈ range t, c i * G q (p i)|) :
    ∀ t < K, p t ≠ q := by
  -- The first pick at `q`, if any, sees only the other components.
  by_contra hcon
  push Not at hcon
  obtain ⟨t, htK, htq⟩ := hcon
  classical
  let P : ℕ → Prop := fun t => t < K ∧ p t = q
  have hex : ∃ t, P t := ⟨t, htK, htq⟩
  obtain ⟨hfK, hfq⟩ := Nat.find_spec hex
  set s := Nat.find hex with hs
  have hbefore : ∀ i ∈ range s, p i ≠ q := by
    intro i hi hiq
    have hi' := Finset.mem_range.mp hi
    exact Nat.find_min hex hi' ⟨hi'.trans hfK, hiq⟩
  have hfilter : (range s).filter (fun i => p i ≠ q) = range s :=
    Finset.filter_true_of_mem hbefore
  have hSs := hS s hfK.le
  rw [hfilter] at hSs
  have hlv := hlevel s hfK hfq
  have htri : |r0 q - ∑ i ∈ range s, c i * G q (p i)| ≤
      |r0 q| + |∑ i ∈ range s, c i * G q (p i)| := abs_sub _ _
  linarith

/-! ### The stopping point -/

/-- **Where the rule stops.** A cycle with `e_K ≤ f Σ|c_t|`, stopped because `κ P ≤ e_K`,
with every pick at least `P_min` and each step lowering `Q` by `γ B x_t²`: then
`κ B P P_min ≤ f ΔQ`. -/
theorem stop_peak_le (Q x : ℕ → ℝ) {γ B κ f P Pmin e : ℝ} (hγ : 0 < γ) (hB : 0 < B)
    (hPmin : 0 < Pmin) (hf : 0 ≤ f) (K : ℕ)
    (hstep : ∀ t < K, Q (t + 1) ≤ Q t - γ * B * x t ^ 2) (hx : ∀ t < K, Pmin ≤ |x t|)
    (he : e ≤ f * ∑ t ∈ range K, |γ * x t|) (hstop : κ * P ≤ e) :
    κ * B * P * Pmin ≤ f * (Q 0 - Q K) := by
  have hflux := certified_cycle_flux Q x hγ hB K hstep hx
  have h1 : κ * P ≤ f * ∑ t ∈ range K, |γ * x t| := hstop.trans he
  have h2 : B * Pmin * (κ * P) ≤ B * Pmin * (f * ∑ t ∈ range K, |γ * x t|) :=
    mul_le_mul_of_nonneg_left h1 (mul_pos hB hPmin).le
  have h3 : f * (B * Pmin * ∑ t ∈ range K, |γ * x t|) ≤ f * (Q 0 - Q K) :=
    mul_le_mul_of_nonneg_left hflux hf
  nlinarith

/-- **The peak contracts over a cycle.** With the bound of `stop_peak_le`, a greedy ratio
`Q₀ − Q_∞ ≤ P₀² / (2 μ)` on the reducible misfit, `Q_K ≥ Q_∞`, and the next cycle's
peak `P_next ≤ b P` with `P ≤ P_min`:
`P_next² ≤ b² f / (2 μ κ B) · P₀²`. -/
theorem peak_contraction {κ B f μ P Pmin P0 Pnext Q0 QK Qinf b : ℝ} (hκ : 0 < κ) (hB : 0 < B)
    (hf : 0 ≤ f) (hμ : 0 < μ) (hP : 0 ≤ P) (hPP : P ≤ Pmin) (hnext0 : 0 ≤ Pnext)
    (hnext : Pnext ≤ b * P) (hstop : κ * B * P * Pmin ≤ f * (Q0 - QK))
    (hgreedy : Q0 - Qinf ≤ P0 ^ 2 / (2 * μ)) (hfloor : Qinf ≤ QK) :
    Pnext ^ 2 ≤ b ^ 2 * f / (2 * μ * κ * B) * P0 ^ 2 := by
  have hden : 0 < 2 * μ * κ * B := by positivity
  have hQ : Q0 - QK ≤ P0 ^ 2 / (2 * μ) := by linarith
  have h1 : κ * B * P ^ 2 ≤ f * (P0 ^ 2 / (2 * μ)) := by
    have h2 : κ * B * P * P ≤ κ * B * P * Pmin :=
      mul_le_mul_of_nonneg_left hPP (by positivity)
    have h3 : f * (Q0 - QK) ≤ f * (P0 ^ 2 / (2 * μ)) := mul_le_mul_of_nonneg_left hQ hf
    nlinarith
  have h4 : P ^ 2 ≤ f / (2 * μ * κ * B) * P0 ^ 2 := by
    rw [div_mul_eq_mul_div, le_div_iff₀ hden]
    have h5 : P0 ^ 2 / (2 * μ) * (2 * μ) = P0 ^ 2 := by field_simp
    nlinarith [mul_le_mul_of_nonneg_right h1 (by positivity : 0 ≤ 2 * μ)]
  have h6 : Pnext ^ 2 ≤ (b * P) ^ 2 := pow_le_pow_left₀ hnext0 hnext 2
  calc Pnext ^ 2 ≤ b ^ 2 * P ^ 2 := by rw [mul_pow] at h6; exact h6
    _ ≤ b ^ 2 * (f / (2 * μ * κ * B) * P0 ^ 2) := mul_le_mul_of_nonneg_left h4 (by positivity)
    _ = b ^ 2 * f / (2 * μ * κ * B) * P0 ^ 2 := by ring

/-- Over cycles: `P_i² ≤ Λ^i P_0²`, and so the number of cycles to a threshold is
logarithmic when `Λ < 1`. -/
theorem peak_geometric (P : ℕ → ℝ) {Λ : ℝ} (hΛ : 0 ≤ Λ)
    (hstep : ∀ i, P (i + 1) ^ 2 ≤ Λ * P i ^ 2) (i : ℕ) : P i ^ 2 ≤ Λ ^ i * P 0 ^ 2 := by
  induction i with
  | zero => simp
  | succ i ih =>
    calc P (i + 1) ^ 2 ≤ Λ * P i ^ 2 := hstep i
      _ ≤ Λ * (Λ ^ i * P 0 ^ 2) := mul_le_mul_of_nonneg_left ih hΛ
      _ = Λ ^ (i + 1) * P 0 ^ 2 := by ring

/-! ### What a measured ratio is, and is not -/

omit [DecidableEq ι] in
/-- A measured stale value is below the column supremum of the components it saw: the
sample `δ = ‖E c‖_∞ / ‖c‖₁` is at most `max_{supp c} f`. -/
theorem measured_le_column_sup (Err : ι → ι → ℝ) (f : ι → ℝ) {F : ℝ}
    (hf : ∀ q j, |Err q j| ≤ f j) (c : ι → ℝ) (hF : ∀ j, c j ≠ 0 → f j ≤ F) (q : ι) :
    |∑ j, c j * Err q j| ≤ F * ∑ j, |c j| := by
  rw [Finset.mul_sum]
  refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun j _ => ?_)
  rw [abs_mul]
  by_cases hc : c j = 0
  · simp [hc]
  · calc |c j| * |Err q j| ≤ |c j| * F :=
          mul_le_mul_of_nonneg_left ((hf q j).trans (hF j hc)) (abs_nonneg _)
      _ = F * |c j| := mul_comm _ _

omit [Fintype ι] [DecidableEq ι] in
/-- **A sufficient hypothesis for the measured rule.** If the columns of the next cycle's
components are within `ρ δ`, the stale error of the next cycle is at most `ρ δ Σ|c|`,
at every step and every target, so `ρ δ Σ|c| ≤ κ |r̃_p|` is a certified rule. -/
theorem stale_of_columns_le (Err : ι → ι → ℝ) (f : ι → ℝ) {ρ δ : ℝ}
    (hf : ∀ q j, |Err q j| ≤ f j) (pix : ℕ → ι) (c : ℕ → ℝ) (K : ℕ)
    (hcol : ∀ k < K, f (pix k) ≤ ρ * δ) (q : ι) :
    |∑ k ∈ range K, c k * Err q (pix k)| ≤ ρ * δ * ∑ k ∈ range K, |c k| := by
  rw [Finset.mul_sum]
  refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun k hk => ?_)
  rw [abs_mul]
  calc |c k| * |Err q (pix k)| ≤ |c k| * (ρ * δ) :=
        mul_le_mul_of_nonneg_left
          ((hf q (pix k)).trans (hcol k (Finset.mem_range.mp hk))) (abs_nonneg _)
    _ = ρ * δ * |c k| := mul_comm _ _

/-- **The measured ratio is not a bound.** On three pixels with a zero column at the
phase centre, a batch at the centre measures `δ = 0`, and the next batch one pixel off
it has an error of `1` per unit of flux: no factor `ρ` turns the first into a bound on
the second. -/
theorem measured_not_a_bound :
    ∃ (Err : Fin 3 → Fin 3 → ℝ) (c c' : Fin 3 → ℝ), (∀ q, Err q q = 0) ∧
      (∀ q, ∑ j, c j * Err q j = 0) ∧ ∑ j, |c j| = 1 ∧
      ∑ j, |c' j| = 1 ∧ ∃ q, |∑ j, c' j * Err q j| = ∑ j, |c' j| := by
  refine ⟨fun q j => if (q = 1 ∧ j = 2) ∨ (q = 2 ∧ j = 1) then 1 else 0,
    ![1, 0, 0], ![0, 1, 0], ?_, ?_, ?_, ?_, ⟨2, ?_⟩⟩
  · intro q
    fin_cases q <;> simp
  · intro q
    fin_cases q <;> simp
  · simp [Fin.sum_univ_three]
  · simp [Fin.sum_univ_three]
  · simp [Fin.sum_univ_three]

/-! ### The form of the w-term error -/

/-- The first-order remainder of the cosine. -/
theorem abs_cos_add_sub_le (x h : ℝ) :
    |Real.cos (x + h) - Real.cos x + h * Real.sin x| ≤ h ^ 2 / 2 := by
  -- For `h ≥ 0`, by the derivative in `h`; the other sign by symmetry.
  have key : ∀ x h : ℝ, 0 ≤ h → |Real.cos (x + h) - Real.cos x + h * Real.sin x| ≤ h ^ 2 / 2 := by
    intro x h hh
    have hderiv : ∀ t : ℝ, HasDerivAt
        (fun t => Real.cos (x + t) - Real.cos x + t * Real.sin x)
        (-Real.sin (x + t) + Real.sin x) t := by
      intro t
      have h1 : HasDerivAt (fun t => x + t) 1 t := by
        simpa using (hasDerivAt_id t).const_add x
      have h2 : HasDerivAt (fun t => Real.cos (x + t)) (-Real.sin (x + t) * 1) t :=
        (Real.hasDerivAt_cos (x + t)).comp t h1
      have h3 : HasDerivAt (fun t : ℝ => t * Real.sin x) (Real.sin x) t := by
        simpa using (hasDerivAt_id t).mul_const (Real.sin x)
      have h4 := (h2.sub_const (Real.cos x)).fun_add h3
      simpa using h4
    have hpow : ∀ t : ℝ, HasDerivAt (fun t : ℝ => t ^ 2 / 2) t t := by
      intro t
      have h := (hasDerivAt_pow 2 t).div_const 2
      have hv : ((2 : ℕ) : ℝ) * t ^ (2 - 1) / 2 = t := by
        norm_num
      rwa [hv] at h
    have hslope : ∀ t : ℝ, 0 ≤ t → |-Real.sin (x + t) + Real.sin x| ≤ t := by
      intro t ht
      have := Real.abs_sin_sub_sin_le (x + t) x
      rw [show x + t - x = t by ring, abs_of_nonneg ht] at this
      rw [show -Real.sin (x + t) + Real.sin x = -(Real.sin (x + t) - Real.sin x) by ring, abs_neg]
      exact this
    have hmono1 : MonotoneOn
        (fun t => t ^ 2 / 2 - (Real.cos (x + t) - Real.cos x + t * Real.sin x))
        (Set.Ici 0) := by
      have hd : ∀ t : ℝ, HasDerivAt
          (fun t => t ^ 2 / 2 - (Real.cos (x + t) - Real.cos x + t * Real.sin x))
          (t - (-Real.sin (x + t) + Real.sin x)) t := fun t => (hpow t).fun_sub (hderiv t)
      apply monotoneOn_of_deriv_nonneg (convex_Ici 0)
      · exact fun t _ => (hd t).continuousAt.continuousWithinAt
      · exact fun t _ => (hd t).differentiableAt.differentiableWithinAt
      · intro t ht
        rw [interior_Ici] at ht
        rw [(hd t).deriv]
        have := abs_le.mp (hslope t (le_of_lt ht))
        linarith [this.1, this.2]
    have hmono2 : MonotoneOn
        (fun t => t ^ 2 / 2 + (Real.cos (x + t) - Real.cos x + t * Real.sin x))
        (Set.Ici 0) := by
      have hd : ∀ t : ℝ, HasDerivAt
          (fun t => t ^ 2 / 2 + (Real.cos (x + t) - Real.cos x + t * Real.sin x))
          (t + (-Real.sin (x + t) + Real.sin x)) t := fun t => (hpow t).fun_add (hderiv t)
      apply monotoneOn_of_deriv_nonneg (convex_Ici 0)
      · exact fun t _ => (hd t).continuousAt.continuousWithinAt
      · exact fun t _ => (hd t).differentiableAt.differentiableWithinAt
      · intro t ht
        rw [interior_Ici] at ht
        rw [(hd t).deriv]
        have := abs_le.mp (hslope t (le_of_lt ht))
        linarith [this.1, this.2]
    have h1 := hmono1 (Set.mem_Ici.mpr le_rfl) (Set.mem_Ici.mpr hh) hh
    have h2 := hmono2 (Set.mem_Ici.mpr le_rfl) (Set.mem_Ici.mpr hh) hh
    simp only [add_zero, zero_mul, sub_self, ne_eq, OfNat.ofNat_ne_zero, not_false_eq_true,
      zero_pow, zero_div] at h1 h2
    rw [abs_le]
    constructor <;> linarith
  rcases le_total 0 h with hh | hh
  · exact key x h hh
  · have := key (-x) (-h) (by linarith)
    rw [show -x + -h = -(x + h) by ring, Real.cos_neg, Real.cos_neg, Real.sin_neg] at this
    rw [show -h * -Real.sin x = h * Real.sin x by ring, neg_sq] at this
    exact this

variable {K : Type*} [Fintype K]

/-- **The Lipschitz bound.** `|Φ| ≤ Σ_k W_k |h_k|`: with `h_k = 2π w_k η` this is
the analytic bound `2π |η| Σ_k W_k |w_k|` of `research/clean-major-cycles.md`. -/
theorem phi_lipschitz (W φ h : K → ℝ) (hW : ∀ k, 0 ≤ W k) :
    |∑ k, W k * (Real.cos (φ k + h k) - Real.cos (φ k))| ≤ ∑ k, W k * |h k| := by
  refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun k _ => ?_)
  rw [abs_mul, abs_of_nonneg (hW k)]
  refine mul_le_mul_of_nonneg_left ?_ (hW k)
  have := Real.abs_cos_sub_cos_le (φ k + h k) (φ k)
  rwa [show φ k + h k - φ k = h k by ring] at this

/-- **The moment bound.** `Φ` is its first-order term, one PSF-sized image of
`W_k h_k sin φ_k`, up to `½ Σ_k W_k h_k²`. -/
theorem phi_moment_bound (W φ h : K → ℝ) (hW : ∀ k, 0 ≤ W k) :
    |∑ k, W k * (Real.cos (φ k + h k) - Real.cos (φ k))| ≤
      |∑ k, W k * h k * Real.sin (φ k)| + ∑ k, W k * h k ^ 2 / 2 := by
  have hrem : |∑ k, W k * (Real.cos (φ k + h k) - Real.cos (φ k) + h k * Real.sin (φ k))| ≤
      ∑ k, W k * h k ^ 2 / 2 := by
    refine (Finset.abs_sum_le_sum_abs _ _).trans (Finset.sum_le_sum fun k _ => ?_)
    rw [abs_mul, abs_of_nonneg (hW k), mul_div_assoc]
    exact mul_le_mul_of_nonneg_left (abs_cos_add_sub_le _ _) (hW k)
  have hsplit : ∑ k, W k * (Real.cos (φ k + h k) - Real.cos (φ k)) =
      ∑ k, W k * (Real.cos (φ k + h k) - Real.cos (φ k) + h k * Real.sin (φ k)) -
        ∑ k, W k * h k * Real.sin (φ k) := by
    rw [← Finset.sum_sub_distrib]
    exact Finset.sum_congr rfl fun k _ => by ring
  rw [hsplit]
  have := abs_sub (∑ k, W k * (Real.cos (φ k + h k) - Real.cos (φ k) + h k * Real.sin (φ k)))
    (∑ k, W k * h k * Real.sin (φ k))
  linarith

/-! ### The whole rule -/

/-- **The certified stop rule, end to end.** Let the working residual at `p` be the
residual `d` at the start of the cycle less components `c_k` at `p_k` through the beam
`B`, and the true one the same through the Gram matrix. If `|⟪a_j, a_q⟫ − B(q, j)| ≤ f j`
and `Σ_k |c_k| f(p_k) ≤ κ |r̃_p|` with `κ < 1`, then the true residual at `p` has the
working sign and at least `(1 − κ)` of its size, and the step `γ r̃_p` lowers the true
misfit by at least `γ (1 − κ − γ/2) r̃_p²`. -/
theorem certified_stop_rule (v : E) (a : ι → E) (m : ι → ℝ) (p : ι) (hp : ‖a p‖ = 1)
    {γ κ : ℝ} (hγ : 0 < γ) (hκ : κ < 1) (B : ι → ι → ℝ) (f : ι → ℝ)
    (hf : ∀ q i, |⟪a i, a q⟫_ℝ - B q i| ≤ f i) (pix : ℕ → ι) (c : ℕ → ℝ) (K : ℕ) (d : ι → ℝ)
    (htrue : ∀ q, dirty v a m q = d q - ∑ k ∈ range K, c k * ⟪a (pix k), a q⟫_ℝ)
    (hrule : ∑ k ∈ range K, |c k| * f (pix k) ≤
      κ * |d p - ∑ k ∈ range K, c k * B p (pix k)|)
    (hne : d p - ∑ k ∈ range K, c k * B p (pix k) ≠ 0) :
    0 < dirty v a m p * (d p - ∑ k ∈ range K, c k * B p (pix k)) ∧
    (1 - κ) * |d p - ∑ k ∈ range K, c k * B p (pix k)| ≤ |dirty v a m p| ∧
    misfit v a (m + Pi.single p (γ * (d p - ∑ k ∈ range K, c k * B p (pix k)))) ≤
      misfit v a m - γ * (1 - κ - γ / 2) * (d p - ∑ k ∈ range K, c k * B p (pix k)) ^ 2 := by
  have herr : |dirty v a m p - (d p - ∑ k ∈ range K, c k * B p (pix k))| ≤
      ∑ k ∈ range K, |c k| * f (pix k) := by
    rw [htrue p]
    exact truncation_error_le_pixel (fun q i => ⟪a i, a q⟫_ℝ) B f hf pix c K d p
  have hpos : 0 < |d p - ∑ k ∈ range K, c k * B p (pix k)| := abs_pos.mpr hne
  refine ⟨pick_same_sign herr ?_, pick_fraction herr hrule,
    certified_step v a m p hp hγ herr hrule⟩
  nlinarith

end Clean
