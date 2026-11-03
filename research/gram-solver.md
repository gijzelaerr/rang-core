# Rang: a proximal solver on the visibility-free normal operator

Branch `gram-solver`, from `d39ec9d`, 2026-11-03. Status: **implemented and measured
on three simulated skies; instruction and cycle counts measured; wall times
provisional** (shared host, load 2-25, recorded per job). Archive:
[results/gram-solver.json](results/gram-solver.json). Code: `core/src/prox_solver.rs`,
`core/src/sara.rs`, `core/src/bin/gram_solver_bench.rs`,
`GramOperator::no_w` and `inverse_filter` in `core/src/gridder_gram.rs`,
`examples/gram_solver_run.sh`, `gram_solver_jobs.sh`, `gram_solver_derive.py`,
`gram_solver_archive.py`.

## 1. Summary

**Is there a real speed gain? Against the same solver on the exact gridder, yes.
Against the best alternative measured, no, not at this data size. Against CLEAN, no.**

- **The operator does what was claimed.** At the same iterates on S1, the Gram and
  exact objectives agree to 6.5e-7 over 300 iterations, and one iteration costs 22.7 G
  against 131 G instructions (×5.8), 29.5 G against 64.3 G cycles (×2.2 under load,
  ×3.5 on a sparse model at low load), 0.92 s against 3.14 s wall. Setup is repaid
  within 3-4 iterations.
- **That baseline is not the relevant one.** FISTA on a plain no-w PSF with a few exact
  major cycles reaches the same objective with the same number of iterations
  (F 7.2220e-3 at 3,200 iterations in both) for 2.55 G per iteration. Run wholly on the
  Gram operator the job costs 64.6 T instructions; the PSF route is about 9.5 T
  (apportioned from its measured 17.6 T for 6,000 iterations). **×6.8 against the
  operator.** The w-aware inner operator saved no iterations here, because S1's w-term
  error (2.1 mJy sup against a 1 Jy peak) is corrected well enough by the outer cycle.
- **Its best use here is the outer cycle, and it saves little at 14.5 M visibilities:**
  PSF inner, Gram outer, 15 cycles: 16.2 T against 17.6 T instructions, 16.9 T against
  19.6 T cycles (loads differ), and the same image (rel. L2 3.6e-6 between the two).
  Counted, this saving grows with `N_vis`: about ×3.8 at 10⁹ and ×5.3 at 10¹⁰ at 2048².
  **Extrapolation, not measured** (§8).
- **Quality against CLEAN: better on the misfit and false flux on all three skies, at
  much higher cost.** Signed ℓ1 at λ = 100 µJy against WSClean 3.7 and GeMClean at the
  same 100 µJy threshold: false flux 1.44, 1.45, 0.58 mJy against 4.87, 5.66, 1.59 mJy
  (GeMClean); the disc 2.7 mJy further from truth; the faintest decade of S3 less well
  recovered. Cost: 17.6 T against 1.07 T instructions, 19.6 T against 0.52 T cycles.
- **Non-negativity fails on these skies.** Non-negative ℓ1 on S1 reaches Q/Q_truth 1.45,
  83,190 false pixels holding 4.3 Jy and a 19.7 mJy residual peak, a converged and
  certified solution (gap 2.5e-5). Off-pixel point sources need negative pixels; CLEAN
  models carry −1.5 Jy, and clipping them raises Q about six-fold (§6.2).
- **Prior art and novelty.** Not new in idea, and the novelty rule is **not met**: the
  quality lead does not come at comparable cost, and the speed lead is not against a
  state-of-the-art method. No comparison was run with BASPLib (uSARA, AIRI, the
  holographic operator), PURIFY, resolve or pfb-imaging, so **no claim is made against
  any of them**. Fair next step: `rang-pfb-imaging:0.0.11` is already built locally.

## 2. The problem and the solver (implemented)

With normalised weights, `d = Φᴴ W y`, `G = Φᴴ W Φ` and
`F(m) = Q(m) + λ‖m‖₁`, `Q(m) = Q₀ − ⟨d, m⟩ + ½⟨m, G m⟩`, with `m ≥ 0` or signed. This
`Q` is the scorer's exact quadratic: the solver reads `prepare`'s arrays.

**λ is CLEAN's threshold.** At an optimum of signed ℓ1 the residual is `±λ` on the
support and at most `λ` elsewhere, the stopping condition of CLEAN at threshold λ. So
λ = 100 µJy (4.3 σ of the Briggs noise) is the matched setting of the benchmark. It is
one value on one array, not a study of λ.

`prox_solver::solve` is FISTA (Beck and Teboulle 2009) or forward-backward, with
O'Donoghue and Candès's gradient restart, generic over `Measurement`: the backends are
`WgridMeasurement` and `GramMeasurement`, interchangeable. Step `1/(1.01 L)`.

Three things cost no apply and were useful:

- **Objective at every iterate.** From `y = (1 + β)x − βx₋₁`,
  `G x = (G y + β G x₋₁)/(1 + β)`. Tested against a direct apply.
- **A visibility-free duality gap.** The dual point `s e`, `e = y − Φ m`, needs only
  `⟨y, e⟩ = 2Q₀ − ⟨d, m⟩` and `‖e‖² = 2Q`, and `s` from the residual peak. On the
  exact backend this bounds `F − F*` with no reference solution.
- **A curvature probe.** Consecutive gradients give `⟨Δy, G Δy⟩/‖Δy‖²` per iteration.

**Defect correction** (`defect_correction`) is what made it converge: solve on a cheap
`G̃` with its error at `m_j` moved to the data, `d_j = d − (G − G̃) m_j`, then repeat. Any
fixed point solves the exact problem whatever `G̃` is, so operator bias goes to zero if
the iteration converges (tested with a 20 % wrong operator). With `G̃` the no-w PSF and
λ_j = max(λ, 0.2 × residual peak), it is a major cycle around a FISTA minor cycle. This
is the structure of pfb-imaging (Bester et al. 2024), reached here independently; it is
not a new idea.

`Sara` (`core/src/sara.rs`) is the SARA dictionary, Dirac and db1-db8, 4 levels, scaled
to `ΨΨᵀ = I`, with dual forward-backward for the prox and `x ≥ 0` (Carrillo et al. 2012;
uSARA). Filters from spectral factorisation; tests check orthonormality, vanishing
moments and the prox's optimality.

## 3. Getting it to converge: negative results first (S1, Gram backend, λ = 100 µJy)

| recipe | applies | F | optimality residual | outcome |
| --- | ---: | ---: | ---: | --- |
| FISTA, non-negative | 301 | 1.37e-2 | 3.2 mJy | 328,407 pixels, 36 Jy; would take thousands more |
| + continuation in λ, ratio ½, 60 iterations a stage | 1,196 | 1.03e-2 | 1.6 mJy | stopped; support exploded below 2×λ |
| + active-set CG, steps cut at the boundary | 558 | 0.215 at its stage λ, 15 mJy | 21 mJy | worse than continuation alone; stopped |
| + active-set CG, clipped subspace step | 287 | 0.26 at its stage λ, 15 mJy | 44 mJy | no better; stopped |
| ADMM, ρ = 1, PSF-preconditioned CG, 3 per update | 280 | 1.75e-2 | 6.8 mJy | no better than plain FISTA; ρ not tuned; stopped |
| **PSF inner, exact outer, non-negative** | 5,167 + 8 exact | 9.986e-3 | 1.9 µJy | **converged, gap 2.5e-5** |

**Why it is slow** (estimate from the observed rate, not measured separately). `L` = 245
comes from the dense low-frequency core of the coverage; a point source between pixels
needs its flux shared among neighbours, whose difference modes have eigenvalues of
order 1e-3 to 1e-2. So `√(L/μ)` is hundreds of iterations per e-fold, and the optimality
residual fell 10 % per 60 iterations once the bright flux was in place. The published
experience agrees: uSARA and AIRI "typically" need thousands (Dabbech and Wiaux 2026).

CG on the support did not help because the support is wrong until late: new pixels
dominate the residual. A preconditioned forward step with a metric prox was not tried.

## 4. The same iterates (measured, S1)

Plain FISTA, signed ℓ1, zero start, one step (`L` = 244.54 from the Gram power iteration),
300 iterations. Gram: `S` 8, θ 0.69, `R` 12. Exact: ε 1e-6.

| iteration | F, Gram's own | F, exact gridder | rel. L2 of images | sup, Jy | flux, Jy |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 4.251809e-2 | 4.251850e-2 | 1.4e-6 | 4.2e-8 | 2.8e-5 |
| 100 | 2.388510e-2 | 2.388553e-2 | 3.1e-5 | 2.1e-6 | 1.4e-5 |
| 200 | 1.196841e-2 | 1.196882e-2 | 9.2e-4 | 2.0e-5 | 4.6e-4 |
| 300 | 9.56882e-3 | 9.56918e-3 | 1.6e-3 | 5.5e-5 | 1.5e-4 |

Largest objective difference 6.5e-7. Evaluated by the exact gridder, the Gram run's
iterates give 9.56926e-3 and the exact run's 9.56918e-3 at 300: 8e-8. The image difference
grows through thresholding, not through a bias: both are mid-flight (§5 gives the bias).

| per FISTA iteration | instr. | cycles | wall | loop memory |
| --- | ---: | ---: | ---: | ---: |
| exact gridder | 131.1 G | 64.3 G | 3.14 s (load 5-8) | 0.42 GB |
| Gram `R` 12 | 22.7 G | 29.5 G | 0.92 s (load 8-11) | 1.81 GB |
| ratio | ×5.8 | ×2.2 | ×3.4 | ×0.23 |

**Reaching a stated tolerance.** `(F_k − F*)/(F₀ − F*)` with `F*` = 7.21969e-3, the best
exact value found. Both backends reach each level at the same iteration:

| tolerance | iteration, both backends | exact gridder | Gram operator |
| ---: | ---: | ---: | ---: |
| 1e-2 | 69 | 9.1 T, 4.5 T cycles | 1.9 T, 2.2 T cycles |
| 3e-3 | 157 | 20.7 T, 10.1 T | 3.9 T, 4.8 T |
| 1e-3 | 276 | 36.3 T, 17.8 T | 6.6 T, 8.3 T |

Costs include the dirty image (67 G) and setup (303 G, 161 G cycles), apportioned per
iteration from the two 300-iteration runs (39.5 T and 7.13 T). 1e-3 is still 36 % above
`F*`; CLEAN's own objective, 7.277e-3, is at 2.2e-5, which plain FISTA did not reach here.

**Monitoring.** No rise of the objective in 300 iterations on either backend, no restart
triggered, no negative curvature (smallest probe 0.0879 on Gram, 0.0875 exact). Lanczos:
largest Ritz value 244.97 on both; smallest +8.8e-4 exact after 30 steps, **+5.1e-5** on
Gram (`S` 8) and **+6.0e-5** (`S` 6, θ 1.18) after 80. A positive Ritz value does not show
PSD; it only fails to show the opposite. **No negative curvature was found.** At `S` 4 the
operator's own objective did go negative (F̃ = −5.9e-4, with `½⟨m,(G̃−G)m⟩` = −7.8e-3, against an
exact F of 7.25e-3). That is not evidence of negative curvature: with `d` and `Q₀` from the
data and `G̃` from elsewhere, `Q̃` is no longer a sum of squares. It does mean the operator's
objective is useless as a monitor at that accuracy.

## 5. Accuracy: how `(S, θ)` moves the converged image (measured, S1)

Each operator's own minimiser, reached with PSF inner cycles and that operator in the
outer cycle, warm from the reference, 4 cycles of 150. Against a **control** with exact
outer cycles and the same warm start and iterations, so solver noise cancels: without
it the differences sit on a floor of 8.3e-4 that has nothing to do with the operator.
Exact certificate at ε 1e-6, score at ε 1e-9.

| `S`:θ | `R` | cube GB | `η` (`sup_error`) | rel. L2 of image | sup, µJy | flux, mJy | sup‖(G−G̃)m‖ | exact optimality | Q/Q_truth | exact F | false, mJy (px) | residual peak, µJy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2:1.0 | 4 | 0.5 | 6.7e-2 | 3.0e-2 | 10,442 | −35.8 | 2.85e-2 | 2.84e-2 | 1.4987 | 1.00499e-2 | 383.6 (17,779) | 28,543 |
| 4:1.2 | 6 | 0.75 | 7.2e-3 | 3.5e-3 | 1,496 | +9.7 | 2.82e-3 | 2.82e-3 | 1.0148 | 7.24865e-3 | 2.74 (209) | 2,719 |
| 6:1.18 | 8 | 1.0 | 5.2e-4 | 2.5e-4 | 109 | −0.72 | 2.00e-4 | 2.04e-4 | 1.01093 | 7.21984e-3 | 1.41 (118) | 304 |
| 8:0.69 | 12 | 1.5 | 4.7e-7 | 3.4e-7 | 0.12 | +0.0004 | 4.89e-7 | 8.9e-6 (solver) | 1.01084 | 7.21969e-3 | 1.44 (119) | 108.8 |
| control, exact | – | – | – | 0 | 0 | 0 | 0 | 8.5e-6 | 1.01084 | 7.21969e-3 | 1.44 (119) | 108.4 |

Read across: **the image bias is about half of `η`, relative in L2, over five decades**
(×0.45, 0.48, 0.47, 0.72). `S` 8 is indistinguishable from exact; `S` 6 saves a third of
the operator and is fine on every score except that its residual error, 200 µJy, is twice
λ, so it cannot certify the threshold; `S` 4 is not usable without correction.

### Relation to the proved bounds

`formal/RangFormal/Gridder.lean`, `gram_residual_bound`: entrywise `η` gives
`‖(G − G̃) m‖_∞ ≤ η ‖m‖₁`. **A corollary, on paper, not in Lean.** Let `m̃` be any stationary
point of `F̃`. Its operator residual meets the optimality conditions exactly, so its exact
residual meets them within `δ = η‖m̃‖₁`. Hence by convexity of `F`,

```text
F(m̃) − F* ≤ δ ‖m̃ − m*‖₁ ≤ η ‖m̃‖₁ (‖m̃‖₁ + ‖m*‖₁)
```

and `gram_quadratic_bound` gives `|F − F̃| ≤ η‖m‖₁²/2`. Neither assumes `G̃` is PSD. The
first says the operator acts like a change of threshold by `δ`. Against measurement:

| `S` | `η‖m‖₁` | measured sup | margin | exact optimality = measured sup? |
| ---: | ---: | ---: | ---: | --- |
| 2 | 9.0e-1 | 2.85e-2 | 32 | yes, 2.84e-2 |
| 4 | 9.8e-2 | 2.82e-3 | 35 | yes, 2.82e-3 |
| 6 | 7.0e-3 | 2.00e-4 | 35 | yes, 2.04e-4 |
| 8 | 6.4e-6 | 4.89e-7 | 13 | below the solver's floor, 8.9e-6 |

The relation between operator error and exact optimality holds to 1-2 %; the Lean bound
is true and loose by 13-35. The test `both_backends_reach_one_solution_within_the_operator_bound`
checks both statements on a small case. **Not proved:** a bound on the image. That needs
restricted strong convexity, whose constant here is small and not measured; the
measured relation `‖Δm‖/‖m‖ ≈ η/2` is empirical. On the objective the bound exceeds `F` itself
at `S` ≤ 6, and at `S` 8 it is 9e-5 against a measured difference below 1e-10 on the same iterations.
On `Q` as computed by the operator: `½⟨m,(G̃−G)m⟩` = −4.4e-7 at `S` 8 against the bound
`η‖m‖₁²/2` = 4.3e-5, a margin of 100; this is the −4e-7 offset of the Gram objective in §4, so that
offset is the operator's error, not a difference between iterates.

**Inexact gradients.** Accelerated methods accumulate a varying gradient error (Devolder,
Glineur, Nesterov 2014, from memory). Here the error is a fixed perturbation of a quadratic, so
FISTA converges to the perturbed minimiser with no accumulation while `G̃` is positive on
the iterates. Measured: no sign of accumulation at `S` 8. The drift of §4 is not it: F
agrees to 8e-8 while the images differ by 1.6e-3.

**Removing the bias.** With defect correction even a poor `G̃` gives the exact fixed point
at one exact pass per cycle: the no-w PSF's error is 2.15 mJy sup, 4,400 times that of
`S` 8, and the result matches the control to the solver's floor.

## 6. Against truth (measured; scorer as the benchmark)

`gemclean_bench_compare.py score` at ε 1e-9. WSClean 3.7 `nominres`, from the benchmark's FITS.
GeMClean at this commit, same command, `-j 8`. Solver: signed ℓ1, λ = 100 µJy, PSF inner, exact
outer, 15 cycles × 400. Gaps left open: 1.36e-4 (S1), 1.58e-4 (S2), 1.46e-5 (S3).

### 6.1 Signed ℓ1

| sky, imager | Q/Q_truth | false flux mJy (px) | model px | inner rms µJy | inner peak µJy | flux error mJy | recovery by decade, mean ± std |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| S1 WSClean fast | 1.01410 | 3.48 (171) | 2,781 | 25.67 | 230.9 | +0.4 | 1.001 ± .006, .999 ± .004 |
| S1 WSClean Högbom | 1.01361 | 5.41 (243) | 2,826 | 25.55 | 112.5 | +0.6 | 1.001 ± .006, .999 ± .004 |
| S1 GeMClean | 1.01343 | 4.87 (209) | 2,807 | 25.51 | 100.0 | +0.7 | 1.001 ± .006, .999 ± .004 |
| **S1 solver** | **1.01085** | **1.44 (118)** | 1,329 | 25.20 | 108.6 | +0.4 | 1.003 ± .005, .999 ± .002 |
| S2 WSClean fast | 1.01577 | 3.17 (194) | 4,241 | 26.16 | 196.7 | −3.8 | 1.002 ± .006, .999 ± .004 |
| S2 WSClean Högbom | 1.01536 | 6.72 (297) | 4,303 | 26.03 | 116.6 | −3.9 | 1.001 ± .006, .999 ± .004 |
| S2 GeMClean | 1.01485 | 5.66 (233) | 4,267 | 25.96 | 100.0 | −4.0 | 1.001 ± .006, .999 ± .004 |
| **S2 solver** | **1.01082** | **1.45 (114)** | 4,155 | 25.86 | 108.8 | −6.8 | 1.003 ± .005, .999 ± .002 |
| S3 WSClean fast | 1.01007 | 1.52 (119) | 4,804 | 26.77 | 245.0 | −13.8 | .658 ± .765, .985 ± .066, .999 ± .037 |
| S3 WSClean Högbom | 1.00989 | 1.65 (127) | 4,805 | 26.67 | 102.4 | −13.8 | .659 ± .760, .985 ± .065, .999 ± .038 |
| S3 GeMClean | 1.00987 | 1.59 (128) | 4,837 | 26.65 | 100.0 | −13.8 | .659 ± .759, .985 ± .065, .998 ± .040 |
| **S3 solver** | **1.00773** | **0.58 (98)** | 3,140 | 26.53 | 101.6 | −10.9 | .637 ± .753, .984 ± .052, 1.001 ± .016 |

Decades ascending: S1, S2 10-100 mJy, 0.1-1 Jy; S3 0.1-1, 1-10, 10-100 mJy.

**Better:** false flux ×2.7 to ×4.6 below GeMClean and Högbom, and ×2.2 to ×2.6 below WSClean's
fast loop; Q closer to truth (excess 1.08 % against 1.34 %, S1); scatter of bright sources
halved (S1, S2) and more (S3); total flux on S3.

**Worse:** S3's faintest decade by 0.02 (.637 against .659), the price of fewer false pixels;
faint decade of S1 and S2 biased +0.3 % against +0.1 %; S2's total flux and disc below; a
residual peak of 102-109 µJy where GeMClean stops at 100 (the gap is open; S3, the most
converged, is closest).

**The disc (S2; truth 2 Jy, 40″).** The solver 1.9929 Jy, 39.8″ × 39.7″, 2,838 pixels. WSClean fast
1.9957 Jy, 39.8″ × 39.8″; Högbom 1.9958; GeMClean 1.9956, 39.8″ × 39.8″. **Slightly worse**: 7.1 against
4.4 mJy short. All centroids within 0.001 pixels. Pixel ℓ1 is a point-source prior.
The SARA-style prior on S2 is in §6.3.

### 6.2 Non-negativity

| S1 | Q/Q_truth | false flux | model flux error | inner peak | exact F of its objective |
| --- | ---: | ---: | ---: | ---: | ---: |
| non-negative ℓ1, converged, gap 2.5e-5 | 1.45224 | 4.30 Jy (83,190 px) | +4.62 Jy | 19.7 mJy | 9.986e-3 |
| signed ℓ1 | 1.01085 | 1.44 mJy (118 px) | +0.4 mJy | 108.6 µJy | 7.220e-3 |
| GeMClean, negatives clipped | Q 5.9× higher | | | | 3.57e-2 |

This is a result on these skies, with sources at continuous positions on a 1.5″ grid: a
source between pixels is represented by a positive core and negative neighbours, as the
1.3-1.5 Jy of negative flux in the signed models of S1 and S2 (0.38 Jy on S3) shows. A non-negative solution pays in
misfit and fills the field with false flux. Not tested: finer pixels, or a model with
off-grid components. uSARA and AIRI enforce positivity and report good results on real
extended sky with images oversampled 1.5-2.5 times beyond the resolution (Dabbech et al.
2022); this note did not reproduce those conditions and makes no statement about them.


### 6.3 The SARA-style prior on S2

**First run, reported as a failed run, not as a quality result.** `lambda=1e-4`, λ_j =
max(λ, 0.2 × peak), 7 cycles × 100, 2 dual iterations: Q fell only from 2.759 to 2.297. The
scaled frame sums over 9 bases, so the effective threshold on a point is about 3 λ_j; the peak
then falls by 0.6 per cycle instead of 0.2, and 100 iterations a cycle was not enough. That is
my schedule, not a statement about SARA. @@SARA2@@

## 7. Cost (measured unless marked)

S1, 14.5 M visibilities, 2048². Instructions and cycles from `perf stat` differences of
whole processes; `-j 8`. Per apply, on a 200-pixel test model.

| operation | instr. | cycles | wall | CPU s | status |
| --- | ---: | ---: | ---: | ---: | --- |
| exact pass, grid + degrid, ε 1e-6 | 131 G | 68.5 G | 3.60 s (load 8-10) | 16.3 | measured |
| Gram apply, `S` 8, θ 0.69, `R` 12 | 19.2 G | 19.8 G | 0.634 s (load 3) | 4.2 | measured |
| no-w PSF apply, `R` 1 | 2.02 G | 2.01 G | 0.176 s (load 3) | 0.64 | measured |
| Gram setup, beyond the dirty image | 237 G | 129 G | 8.4 s | | measured |
| PSF setup | 22 G | 8 G | 1.1 s | | measured |

Whole jobs on S1:

| job | iterations + exact passes | instr. | cycles | wall, load | loop / peak GB | exact F |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GeMClean | | 1.07 T | 0.52 T | 75 s from `/mnt/d`, load not recorded | peak 3.2 | 7.277e-3 |
| FISTA on exact gridder, same schedule, to 7.222e-3 | 3,200 + 0 | **about 420 T: extrapolated** | | **about 2.8 h** | 0.42 / 2.7 | not run |
| **Gram only**, 8 cycles | 3,200 + 0 | **64.6 T** | **66.2 T** | 2,160 s, 7 | 1.81 / 3.2 | 7.22205e-3 |
| PSF inner, exact outer, 15 cycles | 6,000 + 16 | 17.6 T | 19.6 T | 1,527 s, 4-13 | 0.71 / 2.75 | 7.21973e-3 |
| same, apportioned to 8 cycles | 3,200 + 9 | about 9.5 T | about 10.5 T | | | 7.22204e-3 |
| PSF inner, Gram outer, 15 cycles | 6,000 + 1 | 16.2 T | 16.9 T | 1,248 s, 4-7 | 2.06 / 3.47 | 7.21973e-3 |

The PSF iteration's 2.55 G is 2.02 G of apply and 0.53 G of the solver's own arrays, which
would be worth reducing if this were kept. Gram memory: 1.81 GB in the loop against 0.42 GB
for the exact backend's visibilities, weights and `uvw` at this size; that would level out
near 60 M visibilities (**estimate**). Peak is set by the gridder in both, 2.7-3.5 GB.

**The prior is not free.** A proximal step with `Sara`: 18 transforms of 2048² per dual iteration (Dirac and db1-db8, each way, 4 levels). Measured over the first SARA run (S2, PSF inner, 2 dual iterations per step, 700 iterations): 47 G instructions and 39 G cycles per iteration, so about 22 G per dual iteration, more than a Gram apply (19.2 G). Against an exact pass the Gram operator's gain per iteration falls from ×5.8 to about ×2.6 with this prior (175 G against 66 G, sum of measured parts); uSARA's sub-iteration is the same kind of cost, and Dabbech et al. 2022 report it dominating its CPU hours against AIRI's denoiser.

## 8. Where it wins, from counted operations

Measured on S1 and two row subsets. All fits are of three points.

| `N_vis` | exact pass, instr. | cycles | Gram apply, instr. | cycles | setup beyond dirty |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.91 M | 25.2 G | 14.2 G | 19.2 G | 19.6 G | 68 G |
| 3.63 M | 48.0 G | 24.6 G | 19.2 G | 20.0 G | 105 G |
| 14.5 M | 131 G | 68.5 G | 19.2 G | 19.8 G | 237 G |

Fit: pass ≈ 18.9 + 7.74 N, setup ≈ 58 + 12.4 N (N in millions).

| comparison, 3,200 iterations, 9 outer cycles | break-even `N_vis` | status |
| --- | ---: | --- |
| Gram apply against an exact pass, instructions | below 0.9 M (the fit: 0.04 M) | below the measured range, so an extrapolation |
| Gram apply against an exact pass, cycles | 2-3 M | measured between two points |
| PSF + Gram outer against PSF + exact outer | about 1 M | fit; measured +8 % at 14.5 M with 16 passes |
| Gram-only against PSF + exact outer | **about 1.1 × 10⁹** in instructions | **extrapolation** |
| Gram-only against PSF + Gram outer | never at equal iterations, unless the PSF needs many more cycles | see below |

**Projection to 10⁹-10¹⁰ visibilities: EXTRAPOLATION.** A straight line through 0.9-14.5 M, in T
instructions, same 2048², same `W`, same convergence, no I/O:

| `N_vis` | exact pass | exact every iteration | PSF + exact outer | PSF + Gram outer | Gram only |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 14.5 M (fit) | 0.13 | 420 | 9.3 | 8.6 | 71 |
| 10⁸ | 0.79 | 2,540 | 15.3 | 9.6 | 72 |
| 10⁹ | 7.8 | 24,800 | 78 | 21 | 83 |
| 10¹⁰ | 77 | 248,000 | 705 | 132 | 194 |

So the outer-cycle use gains ×3.8 at 10⁹ and ×5.3 at 10¹⁰ over exact major cycles, bounded by
`M × 7.74 / 12.4`, about ×5.6 at `M` = 9, because setup itself grids `S` passes over all
visibilities. The Gram-only line is what uSARA-like use would see.

**Why this is optimistic.** Instructions flatter the operator, which is memory-bound
(×5.8 in instructions is ×2.2 in cycles under load). Data of 10⁹-10¹⁰ visibilities means wide
bands and, with them, usually larger images and larger `W`: `R` grows with `W X` and the cube as
the fourth power of the side (§3 of `gridder-theory.md`: 2048² 1.5 GB here; 8192² about 275 GB by
formula). A wideband solve needs several cubes. Time-variable beams, DD gains and new weights
break or rebuild it (§3 there). The PSF route's cycle count will rise with the w-term,
which this data does not test: `2πWX` is 2.84 rad on these tracks, and §7 of
`gridder-theory.md` names the larger values. **The case where the Gram operator should beat the
PSF inside the solver, large `W`, is untested here**; at that point `R` is also large.

## 9. Prior art (searched 2026-11-03; read as marked)

| source | what it does | relation |
| --- | --- | --- |
| Dabbech and Wiaux 2026, arXiv 2605.26347 (text read) | Resource-adaptive `Φ†Φ`: hybrid w-stacking/w-projection, optional sparse holographic `H_p`, "fully blind to the data size". Simulated MeerKAT, 1.18e9 visibilities, 8192², 23-74 w-layers. Build cost repaid in tens of iterations, an order of magnitude below cumulative application within hundreds; `H` about 3× cheaper than `G` overall. MATLAB in BASPLib | **The state of the art for this use, and the closest work.** Its observed amortisation is what §4 finds. **Code exists; not run.** Sparse `H_p` against one dense real plane per node is not compared |
| Terris et al. 2023, arXiv 2202.12959 (abstract); Dabbech et al. 2022, arXiv 2207.11336 (text read) | AIRI and uSARA: forward-backward with a denoiser or SARA prox. ESO 137-006, MeerKAT, 4096²: uSARA 1,120-2,377 CPU h, AIRI 480-1,028, CLEAN 132-236; operator build 427-652 CPU h more; noise heuristic `η/√(2L)` with a Briggs correction | Target solver class. uSARA at ×8-10 over CLEAN in CPU hours; this note's solver ×16.5 in instructions over GeMClean, different data and measure. **Not run** |
| Bester et al. 2024, arXiv 2412.10073 (pfb-imaging; earlier note, abstract level) | Major-minor forward-backward with a PSF Hessian approximation, PCG and primal-dual | **The recipe that wins here is of this kind.** Image `rang-pfb-imaging:0.0.11` exists locally. **Not run** |
| Kartik, Carrillo, Thiran, Wiaux 2017, arXiv 1609.02097 (from `gridder-theory.md`) | Fourier dimensionality reduction | Compresses the same operator. **Not run** |
| Fessler et al. 2005, IEEE TSP 53, 3393 (from `gridder-theory.md`) | Toeplitz normal operators with a field map, for iterative MRI | The operator's template, and iterative use is its original purpose |
| PURIFY: Pratley et al. 2019, arXiv 1903.04502 (abstract) | Distributed proximal methods, up to 5e10 visibilities on 25-100 nodes; pre-sampled gridding kernels | Keeps data per iteration; **not run** |
| resolve: Arras et al. 2021, A&A 646, A84, arXiv 2008.11435 (abstract) | Bayesian imaging against CLEAN on VLA data, higher cost stated without figures | Different objective. **Not run** |
| Beck and Teboulle 2009; O'Donoghue and Candès 2015; Wen et al. 2010; Devolder et al. 2014; Carrillo et al. 2012 (from memory) | FISTA, restart, FPC_AS, inexact oracles, SARA | Methods used. Not re-read |

**Verdict against the project's rule.** "Comparable quality at materially lower cost" against a
relevant state-of-the-art method: not shown. The ×5.8 lead is over FISTA on `ducc`-class exact
gridding at each iteration, which is a fair baseline for uSARA-like use but is not a measured
state-of-the-art code; the methods that matter have their own precomputed operator or a PSF.
"Higher quality at comparable cost": the quality lead over CLEAN on three simulated point-source
skies is real in the scorer and comes at ×16.5 in instructions and ×38 in cycles. It is not novel
in itself: that an ℓ1 solve beats CLEAN on false flux at a much higher cost is the standing
claim of this literature. **No comparison with their code means no claim against them.**

**What might be narrower and new**, as a gap in a limited search and not a claim: the
visibility-free duality gap used as a stopping certificate; the measured `η/2` image bias with the
exact-optimality identity of §5. Both are small.

## 10. Limits

| what | effect |
| --- | --- |
| Three simulated skies, one array, one track, no calibration errors, flat spectra, no beam | none of this is real data |
| λ fixed at 100 µJy, chosen to match CLEAN's threshold | no sweep; the quality lead may depend on it |
| Solves stopped with gaps open | 1.4e-4 on S1 and S2 against `Q` excess about 6e-5; F still falling at about 1e-7 a cycle; images will move slightly |
| FISTA tried with restart and continuation only | a variable-metric step might change the iteration count; ADMM's ρ was not tuned |
| One operator setting in whole jobs; f64 only | `f32` not run in the solver |
| `W` small on these tracks | the case for the w-aware operator in the inner loop is untested |
| Instruction counts include all threads under load | cycles and wall move with contention; instructions move little |
| WSClean not re-run | scored from the benchmark's FITS; its costs are in `gemclean-benchmark.md`, provisional: S1 Högbom 1,148 CPU-s, fast 501 CPU-s, against the solver's 4,136 user CPU-s |

## 11. To run on an idle host

1. Every wall time above, interleaved: `m-exact`, `m-gram`, `c1`, `r-gram`, `r-psfgram`, GeMClean.
2. The ratio in cycles at low load on dense iterates (×2.2 here under load 8-11; ×3.5 sparse at low load).
3. `rang-pfb-imaging:0.0.11` on S1-S3 with matched λ: the comparison that would decide the prior-art question for this recipe.
4. A larger `W` track (the `w6` set of `gemclean.md`, at `R` about 70 by formula) to find where the PSF's outer cycles stop being enough.

## 12. Reproduction

```bash
cargo +1.93 build --release --manifest-path core/Cargo.toml --bin gram_solver_bench --bin gemclean
# prep/{s1,s2,s3} and prep/sN.json: gemclean_bench_compare.py prepare, the benchmark's catalogues
export SOLVER_ROOT=$HOME/Build/tmp/20261103-gram-solver
examples/gram_solver_run.sh s1 c1 solve backend=psf prior=l1signed cycles=15 gamma=0.2 \
    iters=400 outer_kkt=2e-6 kkt=2e-6 lambda=1e-4
bash examples/gram_solver_jobs.sh counts spectrum matched gemclean_base accuracy evals s2 s3 recipes s2nn sara
# Each model: gemclean_bench_compare.py score prep/sN prep/sN.json runs/sN scores/NAME.json --jobs JOB
python examples/gram_solver_derive.py "$SOLVER_ROOT"
python3 examples/gram_solver_archive.py "$SOLVER_ROOT" research/results/gram-solver.json
```

`RAYON_NUM_THREADS=8`, each stage under `flock /home/gijsm/.rang-heavy.lock`. Noise seed 20261104 and
sky seeds as in the benchmark; power iteration seed 20261103, Lanczos 20261104. Data: prepared
arrays as in the benchmark (SHA-256 of the catalogues and noise in their `meta.json`). Run data was
in `/home/gijsm/Build/tmp/20261103-gram-solver` and has been deleted; the compact copy is the archive.
The non-converging recipes of §3 were probes (`probe`, `probe2`, `p3`, `p4`, `a1`) stopped by
hand: their trajectories are in the archive where they survive, and those with no perf file have
counts in the table only as applies.
