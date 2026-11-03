# A theorem for gemclean's minor-cycle stop rule

Status, 2026-11-03: **theorems proved in Lean; a rule implemented behind
`-stop-rule certified`; measured on S1, S2, S3 and one wide field.** Times provisional
(shared host; the solver study held the heavy lock for much of this work). Code:
`formal/RangFormal/StopRule.lean`, `core/src/gemclean/stale_bound.rs`,
`core/examples/stop_rule_probe.rs`, `examples/stop_rule_archive.py`. Archive:
[results/stop-rule-theorem.json](results/stop-rule-theorem.json). Earlier notes:
[gemclean.md](gemclean.md) §2 and §4, [clean-major-cycles.md](clean-major-cycles.md).

Labels: **Lean** is machine-checked; **paper** is an argument here, not checked;
**measured** is what these runs did and no more.

## 1. Summary

**A rule's consequences are proved, for any valid bound on the beam error. The bound itself rests on paper plus a
measured gridder term, and it held at every pixel of every cycle. The rule is useful as a guard, not as a default: it
is worse on cycles.** The new finding is that the default has a real failure the theorem explains.

- **Proved (Lean).** With `|E(q, j)|` bounded and the rule `e ≤ κ |r̃_p|`: the true residual at the pick has the
  working sign and at least `(1 − κ)` of its size; a step lowers the true misfit by at least
  `γ (1 − κ − γ/2) r̃_p²`; no component lands on a pixel whose true residual is below `(1 − κ) T`; the net flux at a
  pixel is at most its excess over that level plus one step. Standard axioms, no `sorry`.
- **Bound (paper).** `E` depends on three variables, so its supremum takes about 100 PSF-sized gridder calls.
  Per entry on S1 it is 3-7 times the exact column maximum, where the analytic bound is 550-1,500 times (67-185 on the
  512² fields of the earlier note). Largest entry: 7.8e-3, against 1.2. Over a whole batch it is still 9-110 times
  the measured error, because a triangle inequality cannot see cancellation between components.
- **Cycles (measured).** S1, S2, S3: default 5, 5, 4; proved rule at `κ = 0.9` 15, 17, 10; at `κ = 0.5` 24, 26, 15.
  Plus a table of 143-241 s against a 15 s run. **The rule costs about three times the cycles and is about eleven times
  slower.** On the 3.4° field `w6`, with a sampled table only: 96 cycles against 11. It matches the earlier certified rules' pass counts, not the default's.
- **False flux (measured).** Level with the default: 4.28, 4.59, 1.53 mJy against 4.34, 4.88, 1.58 mJy, and `Q` equal to 1e-4.
- **Counterexample (measured).** `δ` is not a bound, and this matters: S1 plus 100 Jy at the phase centre. The first batch
  measures `δ = 2.3e-10`, the next cycle has no stop, and the default places **1,000,000 components (the budget) and
  50.6 Jy of false flux in 199,584 pixels**. The proved rule on the same data: 16 cycles and 4.15 mJy.
  A bright calibrator at the phase centre is an ordinary sky. The default is unchanged here; this is for the owner to decide (§9).
- **Not explained.** The contraction theorem holds on every run and is vacuous after the first cycle (§6.5), so nothing
  here proves why the default needs only 4-5 cycles.

## 2. The objects

The minor cycle holds `r = r₀ − B c`, exact for the phase-centre beam `B` on the `2n`
grid. This is the value the code calls exact. The true residual is
`r* = r₀ − G c`, with `G` the Gram matrix of the atoms. So, over the components of
the current cycle only (the major cycle resets the difference),

`r* − r = −E c`, `E = G − B`.

Two exact facts: `E(j, j) = 0`, and the column of the phase centre is zero. (The
patch map `r̃` of the code plays no part: lazy correction makes the pick's value
exact for `B`.) Below, `r̃` is that value, as in `Clark.lean`. Weights are normalised,
so `G(j, j) = 1`; measured `b(0) − 1 = −3e-11`.

## 3. The form of `E` and a bound for it

**Paper.** With `ñ(x) = √(1 − |x|²) − 1`, `Δ = x_q − x_j` and
`η(q, j) = ñ(x_q) − ñ(x_j) − ñ(Δ)`,

`E(q, j) = Φ(Δ, η(q, j))`,
`Φ(Δ, η) = Σ_k W_k [cos(φ_k(Δ) + 2π w_k η) − cos φ_k(Δ)]`, `φ_k(Δ) = 2π (u_k·Δ + w_k ñ(Δ))`.

`E` is a function of three variables, not four. For one `η`, the map `Δ ↦ Φ(Δ, η)` is one
PSF-sized gridder call with visibilities `exp(2πi w_k η)`, less the PSF.

**Paper: the range of `η`.** With `g(s) = 1 − √(1 − s)` and `s_j = |x_j|²`, `s_Δ = |Δ|²`,

`η = [g(s_j + s_Δ) − g(s_j + s_Δ + 2 x_j·Δ)] + [g(s_j) + g(s_Δ) − g(s_j + s_Δ)]`.

The first bracket is at most `g'_max · 2 |x_j·Δ|`. The second is
`−∫₀^{s_j} ∫₀^{s_Δ} g''`, at most `g''_max s_j s_Δ`. With `s* = 5 r_max²` bounding every argument,
`|η| ≤ |x_j| |Δ| [(1 − s*)^(−1/2) + |x_j| |Δ| (1 − s*)^(−3/2) / 4] =: |x_j| |Δ| (1 + ζ)`.
On S1 `H = max |η| = 2.2e-4`. The code refuses a field where `s* ≥ 1/2`.

**Lean.** Two bounds on `Φ` for fixed `Δ`, with `h_k = 2π w_k η`:

- `phi_lipschitz`: `|Φ| ≤ Σ_k W_k |h_k| = 2π |η| M₁`, the analytic bound of
  [clean-major-cycles.md](clean-major-cycles.md) §4.2 (`M₁ = Σ W_k |w_k|`).
- `phi_moment_bound`: `|Φ| ≤ 2π |η| |S(Δ)| + 2π² η² M₂`, with
  `S(Δ) = Σ_k W_k w_k sin φ_k(Δ)`, one PSF-sized image, and `M₂ = Σ W_k w_k²`. Sharp near a
  component and useless far from it: at `η = 2.2e-4` its second term is 1.6.

**Paper: the supremum in `η`.** On `|η| ≤ H_i`, write `η = H_i t`. Each term `exp(i a_k t)` with
`|a_k| ≤ a = 2π w_max H_i` has the Chebyshev expansion `J₀(a_k) + 2 Σ i^m J_m(a_k) T_m(t)`, and
`|J_m(a)| ≤ (a/2)^m / m!`. So `Φ(Δ, H_i t)` is a polynomial of degree `D` in `t` for every `Δ`, up to
`ε = 2 Σ_{m>D} (a/2)^m / m!`. A polynomial of degree `D` on `[−1, 1]` is bounded by its largest value on
the nodes `cos(jπ/N)` over `cos(πD/(2N))` (Ehlich and Zeller 1964). Therefore

`sup_{|η| ≤ H_i} |Φ(Δ, η)| ≤ (max_j |Φ(Δ, H_i cos(jπ/N))| + ε) / cos(πD/(2N)) + ε`.

The code uses ranges `H, H/4, H/16, …` down to where the moment bound's second term is `1e-5`, `ε ≤ 1e-6`
and `N = 2D`, so a factor `√2`. It adds `2ε_grid` for the gridder's relative accuracy, which is
**measured**, not proved: a run with 100 Jy at the phase centre needed it (§6).

From these images come three bounds on `|E(q, j)|`, loosest first:

| bound | form | cost per step |
| --- | --- | --- |
| global `Δ` | `Δ Σ|c|` | `O(1)` |
| radial `f(|x_j|)` | `Σ_j |c_j| f(|x_j|)`, the sup over offsets of a component at that radius | `O(1)` |
| envelope `g(Δ)` | `Σ_j |c_j| g(x_p − x_j)`, the sup over `η` for that offset | `O(K)`, as the lazy correction, and an FFT pair per resync |

All three are triangle inequalities over `j` (`truncation_error_le_pixel`,
`stale_error_le_envelope`). They cannot see cancellation between components.

## 4. The theorems (Lean)

`formal/RangFormal/StopRule.lean`, namespace `Clean`, 23 theorems, standard axioms only, no `sorry`.
Let `e` bound the error at the pick and let the rule be: **step while `e ≤ κ |r̃_p|`**.

**(a) Descent, with a rate.** `certified_step`: for `γ > 0`,
`Q(m + γ r̃_p e_p) ≤ Q(m) − γ (1 − κ − γ/2) r̃_p²`. So `κ < 1 − γ/2` descends: at `γ = 0.1`, `κ < 0.95`.
This is `clark_rule_descends` with a rate. It holds with `f` replaced by anything that bounds the error.

**(b) The pick is signal.** `pick_same_sign`, `pick_fraction`: for `κ < 1` the true residual has the working
sign and `|r*_p| ≥ (1 − κ) |r̃_p|`. `certified_stop_rule` states (a) and (b) end to end, with `e = Σ_k |c_k| f(p_k)`.

**(c) False flux.** Descent alone explains nothing: the misfit falls while error is fitted. What does:

- `pick_level`, `certified_pick`: a pick above the threshold `T` has `|r*_p| ≥ (1 − κ) T`. **A pixel whose
  true residual is below `(1 − κ) T` takes no component.** The default's `ρ = 1` has `κ = 1` in this reading, and so
  no such exclusion even if `δ` were a bound.
- `no_flux_of_below`: if `|r₀(q)| + S < L`, with `S` the reach of the other components' beams at `q`, nothing lands at `q`.
- `pixel_flux_le`: **the net flux at `q` is at most `max(0, |r₀(q)| + S − L) + C`**, with `L = (1 − κ) T` and
  `C` the largest step at `q`. Flux needs a true residual that exceeds the level, and is at most that excess and
  one step. No assumption on the signs of earlier picks.
- `certified_cycle_flux`: the flux of a cycle above `T` is at most `ΔQ / ((1 − κ − γ/2) T)`, `ΔQ` the fall of the
  true misfit.

**What these do not bound.** The benchmark's "false" flux is model flux more than two beams from any
source. A noise peak above `T` is true residual, and any rule cleans it. On S1 `T` is 4.3σ. (c) says that flux
placed is not *beam error*. It does not say the false-flux score is zero, and it cannot.

**(d) Why the small `f` makes cycles few.** `stop_peak_le`: where the rule stops,
`κ (1 − κ − γ/2) P_stop P_min ≤ f ΔQ`. `peak_contraction`: with the greedy ratio `Q₀ − Q_∞ ≤ P₀² / (2μ)` and
`P_next ≤ b P_stop`, `P_next² ≤ b² f / (2μκ(1 − κ − γ/2)) · P₀²`. `peak_geometric` iterates it. So the number of cycles
goes with `log(P₀/T) / log(1/Λ)`, `Λ ∝ f/μ`. The hypothesis on `μ` is a statement about the sky, not proved
for these data; §6 measures it. `μ` falls as the sky fills with faint components, which is why the last
cycles are the slow ones.

**(e) The measured `δ`.** §5.

## 5. When is the previous cycle's `δ` a bound for the next?

`δ_k = ‖E c^(k)‖_∞ / ‖c^(k)‖₁` is a value at one direction `c^(k)`. The hypothesis the conclusions (a) and (b)
need is exactly

**H(ρ):** at every step `t` of cycle `k+1` and at the pick `p_t`,
`|Σ_{i<t} c_i E(p_t, p_i)| ≤ ρ δ_k Σ_{i<t} |c_i|`.

Under H(ρ), the rule `ρ δ_k Σ|c| ≤ κ |r̃_p|` has the conclusions of §4 (`certified_step` and `pick_fraction` take
any `e`). Lean also has what is and is not known about H:

- `measured_le_column_sup`: `δ_k ≤ max_{supp c^(k)} f`. The sample is below the supremum, so it is the wrong side of it.
- `stale_of_columns_le`: if `f(p_i) ≤ ρ δ_k` for the next cycle's components, H(ρ) holds.
- `measured_not_a_bound`: a three-pixel example with zero diagonal, `δ = 0` on one batch and `1` on the next.

**Measured on real runs.** `δ_k / δ_{k−1}` at the end of each cycle of the default (from the benchmark reports of `184c3bc`,
identical to this tree on S1):

| data | cycle 1 | 2 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: |
| S1 | 0.36 | 0.35 | 0.63 | **2.54** |
| S2 | 0.30 | 0.43 | 0.65 | **3.99** |
| S3 | 0.46 | 0.51 | **3.37** | |
| slice (four stations) | **7.63** | 0.33 | | |

`δ` usually falls by 2-3 per cycle, which is the regularity the default leans on, and it does rise. Inside a cycle H(1) fails
on S1 at the first checkpoints of cycle 3 (`1.6 δ_2`) and all through cycle 4 (up to `27 δ_3`). Those violations are harmless on
S1-S3 only because the absolute error is then far below the threshold (`2-8e-8` Jy against `1e-4`): the
last cycles are short.

What the conclusions actually need is smaller than H: the error at the pick. At nine checkpoints per cycle of
the default on S1, `|E c(p_t)| / |r̃_{p_t}|` never exceeded **0.069** and every sign was right. So the default on S1 is well
inside the theorem's conclusions, while nothing a priori says it must be. That is the honest status of `ρ = 1`.

**Counterexample, constructed.** The zero column makes one directly. `a_centre_batch_measures_nothing_about_the_next_cycle`
is the test at 128². At 2048², S1 plus a source at the phase centre (`stop_rule_probe counter`):

| rule | sky | cycles | components | stop | false flux | false pixels |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| default | S1 | 6 | 85,263 | threshold | 4.34 mJy | 166 |
| proved, `κ = 0.9` | S1 | 16 | 84,974 | threshold | 4.29 mJy | 165 |
| default | S1 + 100 Jy | **2** | **1,000,000** | **budget** | **50,605 mJy** | **199,584** |
| proved, `κ = 0.9` | S1 + 100 Jy | 16 | 85,162 | threshold | 4.15 mJy | 166 |

(False flux here from the probe's own count, which matches the scorer to 0.1 % on S1, with the central source added to the catalogue. Prep arrays.) `δ_0 = 2.3e-10`; the measured `δ` of the budget-stopped cycle is `6.3e-5`, 280,000 times larger.

The sweep, with WSClean's peak fraction, which reads no measurement, on the same data:

| centre Jy | default: cycles, components, false flux, pixels | peak fraction 0.95: cycles, components, false flux, pixels |
| ---: | --- | --- |
| 10 | 6; 99,970; **395 mJy**; 4,663 | 6; 88,651; 9.5 mJy; 559 |
| 30 | **2; 1,000,000 (budget); 50.6 Jy; 199,502** | 7; 86,003; 4.5 mJy; 173 |
| 100 | **2; 1,000,000 (budget); 50.6 Jy; 199,584** | 7; 87,408; 5.9 mJy; 305 |

**The failure condition (paper).** Cycle 0 ends at `(1 − g)` of the first peak. If that is above every off-centre source, `S_c (1 − g) > S_b`, cycle 0 cleans only the central pixel and `δ_0` is rounding: with `g = 0.95` and `S_b = 0.99` Jy, `S_c > 20` Jy. The 30 and 100 Jy runs are in this case. At 10 Jy some off-centre flux enters cycle 0, `δ_0 = 8.1e-5`, and the harm is graded: 91 times S1's false flux. The 50.6 Jy is the figure of `-minor-to-threshold` in [gemclean.md](gemclean.md) §4.1: the default has become that mode.



The first cycle cleans only the central source, whose error column is zero, so `δ_0` is the gridder's rounding. The stop level of cycle 1 is then
`2e-10 Σ|c|`: no stop at all. This is the regression of [gemclean.md](gemclean.md) §4.1 reached by a different road. **No function of
`δ_{k−1}` alone can rule this out**: the failure is in the sampled direction, not in `ρ` or `g`.

## 6. Measurements

Same job as the benchmark: 2048², 1.5″, Briggs 0.5, threshold 100 µJy, gain 0.1, `-j 16`, one noise realisation;
scored by `gemclean_bench_compare.py score --beam-arcsec 10.76`. All times provisional (shared host).

### 6.1 Default images unchanged

`cmp` of model, residual, image, dirty and PSF FITS on S1, base `d39ec9d` against this tree: identical. Components and
per-cycle records equal. The final code repeats it for model, residual and image.

### 6.2 Tightness (S1; the same uvw and weights as S2, S3)

`M₁ = 859 λ`, rms `w` 1,297 λ, largest `|w|` 8,162 λ, `H = 2.2e-4`.

| largest `|E|` | value | over the exact maximum of 12 bright columns (0.8-2.2e-3) |
| --- | ---: | ---: |
| analytic, `2π H M₁` | 1.2 | 550-1,500 |
| Chebyshev table, per component | 2.1e-3 to 7.8e-3 | **3.1-6.8** per entry |
| uniform samples (16; 37 calls; measured, not a bound) | 1.5e-3 to 3.8e-3 | 1.3-3.0 per entry |

The exact maxima lie at far offsets (900-1,700 pixels), not near the source, so a bound on a patch would not help. A bound with `p` and
`j` restricted to the model support was not measured: bright sources fill these fields, so I do not expect much from it. The largest entry
on the 512² fields of [clean-major-cycles.md](clean-major-cycles.md) §6.2 was 67-185 times below its bound.

Bound over the measured `‖E Δm‖_∞` at the end of each cycle of the default on S1:

| cycle | stale µJy | `δ` | global `Δ` | radial `f` | 12 exact columns + radial | envelope `g` | (same, uniform samples: global, envelope) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 2,181 | 2.4e-4 | 33 | 21 | 13 | **9** | 16, 4.3 |
| 1 | 263 | 8.6e-5 | 92 | 55 | 51 | **22** | 44, 10 |
| 2 | 45 | 3.0e-5 | 264 | 164 | 156 | **62** | 127, 30 |
| 3 | 4.6 | 1.9e-5 | 421 | 255 | 247 | **94** | 204, 46 |

Exact columns for the 12 brightest pixels help only while few pixels hold the flux. The envelope is the
useful form. In runs of the rule itself, the bound over the measured error is 9.7-110 (Chebyshev) and 4.8-48 (uniform).

**Provenance.** The Chebyshev tables of this subsection come from the final code, the uniform-sample columns from a binary before the margin correction and the `2ε_grid` term. The S1-S3 rule runs of §6.3 used a binary built before the margin `ζ` was corrected from `4 r_max²` to `5 r_max²` (relative change about 1e-4 in the range of `η`): rerun on S1 with the final code, every cycle has the same components and misfit, the bound moves by at most 3.8e-5 relative, and there are no violations. S2, S3 and `w6` were not rerun.

**The bound held every time.** `bound_violations` compares `|r_exact − r̃|` with the bound at every pixel at the end of every
cycle: zero across all certified runs on S1, S2, S3 and the counterexample, once `2ε_grid` was added; before that, one pixel, the diagonal under 100 Jy,
at the gridder's accuracy. `stale_bound_holds_for_exact_columns` checks exact columns at 128². **With 64 uniform samples that test failed**
at 128², and it passes on Chebyshev nodes, so the sampled form is not a bound in practice as well as in principle. I did not diagnose the failure further.

**Wide field, measured only.** `w6`: S3's sky at 6″, 3.4° (`gemclean.md` §5.7). Chebyshev nodes would take 432 gridder calls (`a = 95` at the widest range, about 25 minutes), which I did not run. With 64 uniform samples (91 calls, 319 s; largest `|E|` 7.0e-3, `w` rms 1,083 λ): the bound over the measured `‖E c‖_∞` is 3.2-55. **Two pixels exceeded it, in the last cycle of the run, where four components sit near the threshold (bound 0.21 µJy): a sampled table is not a bound, as §3 says.** The default's `δ` ratios are 0.28, 0.46, 0.58, 0.69, then **2.04, 3.47, 2.34, 2.52, 1.30, 2.44** in its last cycles.

### 6.3 Cycles and false flux

| sky | rule | major cycles | components | Q/Q_truth | false mJy | false pixels | wall s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S1 | default | **5** | 85,337 | 1.01358 | 4.34 | 165 | 15 |
| S1 | proved, `κ = 0.9` | **15** | 85,162 | 1.01359 | 4.28 | 161 | 168 |
| S1 | proved, `κ = 0.5` | 24 | 85,084 | 1.01359 | 4.32 | 161 | 177 |
| S1 | uniform samples, `κ = 0.9` | 9 | 85,185 | 1.01359 | 4.29 | 163 | 73 |
| S1 | uniform, `κ = 0.5` | 14 | 85,054 | 1.01363 | 4.28 | 161 | 87 |
| S1 | uniform, radial, `κ = 0.9` | 25 | 84,999 | 1.01360 | 4.22 | 160 | 96 |
| S2 | default | **5** | 90,905 | 1.01507 | 4.88 | 180 | 15 |
| S2 | proved, `κ = 0.9` | **17** | 90,790 | 1.01511 | 4.59 | 156 | 188 |
| S2 | proved, `κ = 0.5` | 26 | 90,771 | 1.01509 | 4.69 | 163 | 181 |
| S2 | uniform samples, `κ = 0.9` | 10 | 92,529 | 1.01529 | 4.72 | 172 | 80 |
| S3 | default | **4** | 45,803 | 1.00986 | 1.58 | 126 | 14 |
| S3 | proved, `κ = 0.9` | **10** | 45,789 | 1.00987 | 1.53 | 121 | 157 |
| S3 | proved, `κ = 0.5` | 15 | 45,767 | 1.00988 | 1.51 | 121 | 180 |
| S3 | uniform samples, `κ = 0.9` | 6 | 45,694 | 1.00989 | 1.48 | 120 | 71 |

For reference ([gemclean.md](gemclean.md) §4.3): WSClean's Högbom loop 6, 6, 5 cycles and 5.41, 6.72, 1.65 mJy; its fast loop 9, 9, 6 and 3.48, 3.17, 1.52 mJy;
`-mgain 0.5` 15, 15 cycles. The inner peak is 100 µJy in every row.

**Plainly: the proved rule is no better on cycles.** Its 10-17 cycles at `κ = 0.9` are inside the 7-30 passes of the earlier certified rules,
though never the 30-pass failures, and its `Q` and false flux are at the default's level. The false flux agrees to 1-6 %, which is itself a result: on these three skies the default was
not fitting beam error (S1-S3 only; §5 shows that this is not a property of the rule). `κ = 0.9` is the value I would use, and I looked at it after seeing `κ = 0.5`; `κ < 0.95` is what descent needs.

The first cycle is where the rule is strong: it ends at 14 mJy on S1 against the default's 48 mJy, with no tuned `g`. By the second the default has passed it (0.85 against 1.5 mJy). The late cycles are the expensive ones: from
0.7 mJy down, each takes 0.1-0.3 Jy of flux, and a bound of about `1.8e-3` per Jy allows little of it.

**Wide field `w6`, uniform samples, measured only:** default 11 cycles, 713,726 components, Q/Q0 3.0039e-2, 46 s; rule at `κ = 0.9` **96 cycles**, 695,033 components, Q/Q0 3.0138e-2, 529 s. The scorer's false flux is 11.9 and 11.7 Jy in 56,007 and 50,567 pixels. At 6″ two beams are 3.6 pixels, and I did not examine what those pixels are, so I take only the agreement from it. **On a wide field the rule is about nine times worse than the default, not three**, at an uncertified table that a rigorous one would make worse again.

### 6.4 Where false flux goes (`pixel_flux_le`, S1 and `κ = 0.9`)

`stop_rule_probe counter` with no extra source. `S` is measured at the end of each cycle only; the theorem takes it over the cycle.

| cycles | first peak µJy | false pixels | net flux µJy | bound µJy | pixels over bound |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0-7 | 958,000 to 228 | 0 | 0 | 0 | 0 |
| 8 | 194 | 4 | 181 | 881 | 0 |
| 9 | 172 | 5 | 468 | 1,221 | 0 |
| 10 | 149 | 9 | 443 | 1,645 | 0 |
| 11 | 136 | 20 | 482 | 2,849 | 0 |
| 12 | 122 | 40 | 771 | 5,053 | 0 |
| 13 | 112 | 102 | 1,419 | 11,370 | 0 |
| 14-15 | 103, 100 | 50 | 526 | 5,136 | 0 |

The sum is the scored 4.29 mJy. No false pixel takes flux until the peak is below 200 µJy, about `8.5σ`; most arrive within `1.2 T`. Since this run's error is far below `T` there (§6.2),
**this false flux is noise above the threshold, not beam error**, and every rule places it. The bound is 2.6-10 times the flux, loose partly because `L = 0.1 T` at `κ = 0.9`.

### 6.5 The flux and contraction theorems on these runs

`certified_cycle_flux` holds on every cycle: the bound over the flux is at least 2.2 at `κ = 0.5`, and tight only in the last cycles, where the peak is at `T`. `stop_peak_le` holds on every rule-stopped cycle, with the next cycle's peak for `P_stop`: right over left at least 2.8 at `κ = 0.5`, and 25 at `κ = 0.9` (`B = 0.05` is then small).

`peak_contraction` holds and says little. With `Q_∞` the run's final misfit, `μ = P² / (2 (Q − Q_∞))` falls from 0.17 to 2e-4 on S1, `f` is 1.6-2.1e-3 per Jy, and `Λ = f / (2μκB)` is:

| S1, `κ = 0.9`, cycle | 0 | 1 | 2 | 3 | 5 | 8 | 13 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `μ` | 0.17 | 0.013 | 1.2e-3 | 4.9e-4 | 2.7e-4 | 2.3e-4 | 7.7e-4 |
| `Λ` predicted | 0.14 | 1.7 | 20 | 44 | 77 | 86 | 26 |
| measured `(P_next / P)²` | 2e-4 | 0.011 | 0.21 | 0.44 | 0.65 | 0.74 | 0.86 |

**`Λ > 1` after the first cycle on all three skies, so the theorem does not promise contraction there.** It does explain the shape: the rate is set by `f/μ`, and `μ` collapses as the sky becomes thousands of faint components. The measured contraction degrades the same way.

## 7. What remains unproved

- **Why the default needs only 4-5 cycles.** Nothing here proves it, and the default's constants stay tuned on S1-S3.
- Lean does not contain: `E = Φ` for the gridder's images, the range of `η`, Ehlich-Zeller, the Bessel tail, or the gridder's accuracy. These are on paper or measured (§3).
- The greedy ratio `μ` in the contraction is a hypothesis.
- That a run's rule uses the bound of §3 is code, tested per pixel per cycle (`bound_violations`), not proved.
- Nothing here bounds noise fitted above `T`.

## 8. Reproduction

```bash
# Bound, rule and probe; S1 at the benchmark settings (data: research/gemclean-benchmark.md)
cargo +1.93 build --release --manifest-path core/Cargo.toml --bin gemclean --example stop_rule_probe
gemclean -name OUT/s1 -size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 \
    -abs-threshold 0.0001 -data-column DATA -field 0 -j 16 -stop-rule certified -stop-rule-kappa 0.9 s1.ms
# -stop-rule-samples 16: uniform samples; -stop-rule-bound radial: the O(1) form
stop_rule_probe PREP/s1 OUT.json 0 12            # 0: Chebyshev nodes; 12 exact columns; tightness and checkpoints
stop_rule_probe counter PREP/s1 s1.json 100 0 0.9 OUT.json   # plus 100 Jy at the centre; the pixel flux check
python examples/stop_rule_archive.py RUNS SCORES PROBES research/results/stop-rule-theorem.json
# Lean: from formal/, lake build; the axioms print as info lines of Audit.lean
```

`w6`: `python -c "import gemclean_bench_simulate as m; m.main(['w6.ms', '--sky', 'S3', '--scale', '6', '--catalogue', 'w6.json'])"`, then the job above with `-scale 6asec -niter 3000000 -stop-rule-samples 64`. No data are kept: everything is regenerated from these commands and the benchmark's datasets on `/mnt/d/rang/outputs/20261102-gemclean/bench/`.

Seeds and data are the benchmark's (S1-S3). The prep arrays give S1 6 cycles where the MS path gives 5: the last has one component, from a
weight sum that differs in the ninth digit. Probe figures on S1 come from the prep arrays, run figures from the MS.

## 9. Next steps

1. **Owner decision: the default's failure on a centre source (§5).** The peak fraction `-mgain` does not read `δ`. Possible guards, **proposed, none tested**: floor `δ` at a
   fraction of one exact off-centre column (one gridder call); or end a cycle at the larger of the measured level and the bound over a measured looseness. Neither is a theorem.
2. **Cancellation is what is missing.** `E` is known by offset and `η`, so a signed sum over components at the pick is computable from the `Φ` images. It would need a rigorous
   remainder between `η` samples, which at affordable sampling (§3) exceeds `E` itself. So it would be an approximation, not a certificate. Not attempted.
3. **A smaller `f`.** §4 takes any bound. With the w-node operator of `core/src/gridder_gram.rs` in place of `B` in the minor cycle, `f` would be its expansion error (measured about
   1e-6, [gridder-theory.md](gridder-theory.md)) rather than 2e-3, and the same theorems would promise few gridder passes. Not attempted: it replaces the beam, so its minor cycle costs more.
4. **Oversampling the nodes.** `N = 3D` would drop the factor from 1.41 to 1.15, for 50 % more calls. Not run.
