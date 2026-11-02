# Rang: a visibility-free major cycle, and what a proof can do for the gridder

Branch `gridder-gram`, from `58e07e1`, 2026-11-02. Status: **implemented as a
prototype behind a flag (`gemclean -gram-operator S,THETA`); accuracy measured;
instruction counts measured; wall times provisional** (load 2-5 for the operator
measurements, 4-17 for the whole jobs, shared host). The default of gemclean is
unchanged. Archive: [results/gridder-theory.json](results/gridder-theory.json).
Lean: [`formal/RangFormal/Gridder.lean`](../formal/RangFormal/Gridder.lean).
Code: `core/src/gridder_gram.rs`, `core/src/bin/gridder_gram_bench.rs`,
`examples/gridder_gram_jobs.sh`, `examples/gridder_gram_archive.py`.

## 1. Summary

- **A shortcut exists, for one operation.** One major-cycle pass costs a fixed
  23.7 G instructions on 2048² at any visibility count, against 307 G for
  grid+degrid at 31 M visibilities (×13 in instructions, ×5.6 in wall time at
  low load), at the same error against the gridder at ε 1e-10.
- **It does not pay on gemclean's own jobs.** Setting it up costs more than the 3-5
  major cycles gemclean runs recover. Whole jobs at 14.5-31 M visibilities: wall time
  equal or worse under load, user CPU from +1 to −26 %, peak memory +1.5 to +1.9 GB
  (some of which a production path would free). No speed claim follows.
- **It pays with many passes.** S1 at `-mgain 0.1`, 87 major cycles: 480 → 140 s
  wall, 2,873 → 619 s user CPU (load 13-15), with the same Q, false flux and
  residual peak. The natural customers are iterative solvers that apply the normal
  operator often, not gemclean's default.
- **It does not scale to wide fields.** Nodes grow as the square of the field, so
  the cube grows as its fourth power. At 4096² in `f32` one apply costs 31.5 CPU-s
  against 37.0 for a pass at 31 M visibilities, with an 8.3 GB cube. Measured.
- **Not novel in its main idea.** A visibility-free w-aware normal operator is
  published (Dabbech and Wiaux 2026), and the Toeplitz sum is Fessler et al. (2005)
  in another field. §4 says what narrower combination I did not find.
- **Lean.** 23 new theorems, no `sorry`, standard axioms. They license the operator;
  they do not make it faster. §5.

## 2. The operator (implemented)

With normalised weights `W_p` and `x = n − 1`, the normal operator of the measurement
has entries

```text
G(l, l') = Re Σ_p W_p exp(2πi (u_p·(l − l') + w_p (x(l) − x(l'))))
```

It depends on `l − l'` and on `x(l) − x(l')`, so it is not Toeplitz. Folding to
`w ≥ 0` does not change the real part. Expand the exponential over fixed nodes for
`|ξ| ≤ X`, `X` the range of `x` over the image:

```text
exp(2πi w ξ) ≈ Σ_k ψ_k(w) exp(2πi w_k ξ)

G̃ m = Re Σ_k e_k · (K_k ⊛ (conj(e_k) · m)),   e_k(l) = exp(2πi w_k x(l))
K_k(δ) = Σ_p W_p ψ_k(w_p) exp(2πi u_p·δ)
```

**One sum, not a double sum.** The price is bandwidth: `ξ` spans twice the range of
`x`, as Fessler et al. note for their eq. 24. The rank needed for accuracy ε is about
`2π W X / θ + S`, with `S` the stencil and `θ = 2π dw X` the phase step.

**Why not the gridder's own w-kernel.** Its correction function would be a function of
`x(l) − x(l')`, which does not separate into a factor per pixel. So `ψ` is fitted
without one: `S` nearest nodes, regularised least squares over `|ξ| ≤ X`, real
coefficients from a Toeplitz normal matrix, tabulated at 8,193 positions.

**Why compact support.** Setup grids `S` full passes of visibilities instead of `R`.

**Embedding.** `K_k` is needed only at `|δ| < n`, so it lives on `(2n)²` and its
transform is real: 8 bytes a cell in `f64`. Each `K_k` comes from one real gridder
call with the constant visibility `1 − i`: the output is `Σ W (cos θ + sin θ)`, whose
even and odd parts are `Re K` and `Im K` (a Hartley transform).

**Apply.** Per node: `n` row FFTs, `2n` column FFT pairs with the product inside the
pass, `n` inverse row FFTs, on two `n × 2n` buffers.

**Misfit.** `Q = Q₀ − ⟨d, m⟩ + ½⟨m, G̃m⟩`, from one gridding of the data.

### Complexity

| per major cycle | visibilities | FFTs | image-grid work |
| --- | --- | --- | --- |
| grid + degrid (today) | `2 N_vis S³` complex taps | `2 N_planes` on `(σn)²` | `2 N_planes n²` |
| this operator | **none** | `R` pairs on `(2n)²`, pruned to 3/4 | `2 R n² + R (2n)²` |
| once: setup | `S_w N_vis S²` taps | `R` on `(σ 2n)²` and `R` on `(2n)²` | |

### Variants rejected by count

| variant | why not |
| --- | --- |
| Double sum with the gridder's kernels (Fessler eq. 23) | Gram of approximate atoms, so PSD by construction, but `R (2S−1)` kernels: about 15 × 15 × 134 MB = 30 GB at 2048² |
| Global Chebyshev double sum (Jacobi-Anger) | `L` = 10-13 here, half the FFTs, PSD, closed-form bound; but `2L−1` = 19-25 kernels, each a pass over **all** visibilities, against `S` = 8; setup alone would exceed the cost of every pass it saves |
| Lagrange stencil | closed-form bound, but `R` = 40 against 28 by LS at 1e-6, `S` = 8 (numpy table, at `W` = 38,000) |
| Sparse spectra | 3-5 % of cells below 1e-7 of the peak on 2048² (16 % at 4096²): the `2n` crop's Dirichlet tails fill the plane |

The single sum is symmetric but **not provably PSD**: it can go negative at the level of its error.
gemclean tolerates this because its steps rest on the image-domain beam; a solver
that needs strict descent should check it. `operator_step_descends` needs no PSD
hypothesis on the approximate operator, only the margin, so it covers the single sum.

## 3. Measured

Data: `point` sky, 64 antennas, 4 h, 64 channels, 30,965,760 visibilities, 2048² at
1.5″, Briggs 0, `-j 8`, release profile. `W` = 14,864 λ, `X` = 5.55e-5, `2π W X` = 5.18.
Gridder plan at ε 1e-6: support 7, 8 planes, grid 4752².
Instructions from `perf stat` minus the read-only run.

### One operation, matched accuracy

Error against the gridder at ε 1e-10, the 204-component model; a white-noise image
gives the same relative L2.

| operator | rel. L2 | sup/‖m‖₁ | instr. per pass/apply | wall | CPU s | setup | memory held |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| gridder `f64`, ε 1e-6 | 2.8e-7 | 3.9e-9 | 307 G | 4.36 s | 31.3 | plan 1.2 s | vis, uvw, wgt |
| operator `f64`, S 8, θ 0.69, R 15 | 2.8e-7 | 4.8e-9 | **23.7 G** | 0.78 s (S 10, same R, load 2.7; S 8: 0.72-0.95 s at load 5-7) | 5.4 | 13.7 s, 443 G, 62 CPU-s | cube 2.0 GB + 0.4 GB work |
| gridder `f32`, ε 1e-4 | 3.3e-5 | 3.7e-7 | 184 G | 2.39 s | 17.4 | 0.9 s | |
| operator `f32`, S 6, θ 0.82, R 12 | 3.0e-5 | 5.1e-7 | not split | 0.40 s | 2.8 | 6.4 s | cube 0.8 GB |

Against the direct sum (32², 800 rows, two channels, large `w`, both flips): the unit
test `matches_the_direct_sum_within_the_stated_bound` holds for four stencils, with
final error below 1e-5.

Accuracy sweep (`f64`, ε 1e-6 on `K`): the error follows the expansion, rel. L2 about
half of `sup_error`, and sup/‖m‖₁ about 100× below it.

| S:θ | R | `sup_error` | rel. L2 |
| --- | ---: | ---: | ---: |
| 4:0.37 | 17 | 5.6e-5 | 3.5e-5 |
| 6:0.82 | 12 | 5.2e-5 | 3.0e-5 |
| 8:1.21 | 12 | 5.2e-5 | 2.7e-5 |
| 10:1.5 | 13 | 4.8e-5 | 2.3e-5 |
| 6:1.18 | 10 | 5.2e-4 | 2.7e-4 |
| 8:0.69 | 15 | 4.7e-7 | 2.8e-7 |
| 10:0.99 | 15 | 5.4e-7 | 2.9e-7 |
| 12:1.24 | 16 | 5.6e-7 | 2.9e-7 |
| 16:1.3 | 19 (K at 1e-8) | 1.6e-8 | 5.8e-9 |

### Crossover in `N_vis` (counted)

Every k-th row of `point`; S 8, θ 0.69, `f64`, 2048². Instructions in G.

| `N_vis` | gridder plan | pass | apply | setup |
| ---: | --- | ---: | ---: | ---: |
| 121 k | supp 12, 13 planes, 2592² | 20.3 | 23.7 | 66.8 |
| 484 k | supp 9, 10 planes, 3080² | 23.4 | 23.7 | 72.9 |
| 1.9 M | supp 8, 9 planes, 3600² | 36.8 | 23.7 | 95.4 |
| 7.7 M | supp 8, 9 planes, 3600² | 97.4 | 23.7 | 170 |
| 31 M | supp 7, 8 planes, 4752² | 307 | 23.7 | 443 |

A fit gives pass ≈ 19 + 9.3 N, setup ≈ 65 + 12.2 N (N in millions). Break-even in
instructions, not counting a PSF pass the setup might replace:

| major cycles | break-even `N_vis` |
| ---: | ---: |
| 1 apply against 1 pass | 0.5 M |
| 3 | 5 M |
| 5 | 2.6 M |
| 87 | 0.6 M |

**Instructions flatter the operator.** It is memory-bound and its setup has serial
parts. In wall time at low load the pass and the apply meet near 2 M visibilities
(0.85 against 0.81 s), and the setup costs 3.3 passes at 31 M (1.4 in instructions, 2
in CPU). At large `N_vis` the N-dependent cost of a job is about `(M + 1)` passes
today against `dirty + setup` ≈ 2.8 passes (with `-beam-no-w`, so no PSF pass), so the bound on the gain is ×1.4 at 3
cycles and ×2.1 at 5. A dedicated gridder for real weights might halve the setup
(**proposed, not implemented**): the prototype calls the complex gridder once per node.

### Whole jobs

`-j 8`; `gram` adds one exact pass at the end for the score, which a production path
could skip. Thresholds as in `gemclean.md` §5 for `point`, `disc`, `crowded` and as in
`gemclean-benchmark.md` for S1-S3. Load 4-17: **wall times are provisional and scatter
by more than some differences.** User CPU is less sensitive. Every variant of every
sky is in the archive; this table is a selection.

| job | wall s | user CPU s | majors | major s | setup s | peak GB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S1 default | 31.5 | 198 | 5 | 17.9 | | 2.7 |
| S1 gram | 31.1 | 155 | 5 | 3.6 | 10.2 | 4.2 |
| S1 gram, `-beam-no-w` | 31.1 | 148 | 5 | 3.9 | 11.8 | 4.2 |
| S2 default | 35.7 | 228 | 5 | 19.9 | | 2.7 |
| S2 gram | 34.0 | 169 | 5 | 4.0 | 10.4 | 4.2 |
| S3 default | 29.3 | 180 | 4 | 16.3 | | 2.7 |
| S3 gram | 35.5 | 173 | 5 | 4.4 | 12.4 | 4.2 |
| point default | 40.6 | 195 | 3 | 21.5 | | 3.8 |
| point gram | 51.2 | 197 | 3 | 5.1 | 19.0 | 5.8 |
| point gram, `-beam-no-w` | 49.9 | 168 | 3 | 3.4 | 24.9 | 5.7 |
| disc default | 49.2 | 243 | 4 | 25.9 | | 3.8 |
| disc gram, `-beam-no-w` | 51.5 | 182 | 4 | 6.5 | 19.6 | 5.7 |
| crowded default | 42.7 | 232 | 4 | 24.2 | | 3.8 |
| crowded gram, `-beam-no-w` | 50.6 | 184 | 5 | 8.6 | 19.6 | 5.7 |
| S1 `-single`, ε 1e-4 | 21.1 | 129 | 5 | 10.0 | | 1.9 |
| S1 gram `-single` | 22.5 | 116 | 5 | 2.1 | 5.5 | 2.6 |
| point `-single` | 26.1 | 114 | 3 | 12.0 | | 2.6 |
| point gram `-single` | 30.0 | 111 | 3 | 3.2 | 10.9 | 3.4 |
| **S1 `-mgain 0.1` default** | **480** | **2,873** | 87 | 450 | | 2.7 |
| **S1 `-mgain 0.1` gram** | **140** | **619** | 87 | 92 | 15.7 | 4.2 |

Science, by the benchmark's exact quadratic (`gemclean_bench_compare.py score`, gridder
at ε 1e-9, on `origin/gmclean-bench`):

| job | Q/Q_truth | false flux, pixels | exact residual peak, µJy | flux error, Jy |
| --- | ---: | ---: | ---: | ---: |
| S1 default | 1.013579 | 4.34 mJy, 165 | 100.01 | +0.0007 |
| S1 gram | 1.013584 | 4.38 mJy, 169 | 100.03 | +0.0007 |
| S1 gram, no-w beam | 1.013584 | 4.33 mJy, 164 | 99.99 | +0.0007 |
| S1 `-mgain 0.1` default | 1.013554 | 4.20 mJy, 161 | 99.97 | +0.0007 |
| S1 `-mgain 0.1` gram | 1.013574 | 4.16 mJy, 160 | 99.99 | +0.0008 |
| S2 default | 1.015067 | 4.88 mJy, 180 | 100.02 | −0.0034 |
| S2 gram | 1.015098 | 4.89 mJy, 181 | 100.10 | −0.0033 |
| S3 default | 1.009864 | 1.57 mJy, 126 | 100.00 | −0.0132 |
| S3 gram | 1.009878 | 1.55 mJy, 124 | 99.99 | −0.0133 |
| S1 `-single` | 1.013592 | 4.32 mJy, 166 | 125.29 | +0.0004 |
| S1 gram `-single` | 1.013574 | 4.33 mJy, 166 | 111.10 | +0.0008 |
| S2 `-single` | 1.015162 | 4.95 mJy, 176 | 123.78 | −0.0037 |
| S2 gram `-single` | 1.015115 | 4.98 mJy, 181 | 110.69 | −0.0031 |

The default path is untouched: `s1-base-model.fits` has the same SHA-256 as the `58e07e1`
benchmark job at `-j 16`, fat LTO.

**What the gram path certifies.** It stops at the threshold on the operator's residual,
not the gridder's. In `f64` the exact residual peak is 100.03, 100.10 and 99.99 µJy on S1,
S2, S3 against the 100.00 µJy threshold, and the last residual differs from the gridder's
by 0.49, 0.49 and 0.07 µJy in L-inf. The paper bound `sup_error ‖W‖₁ ‖m‖₁` is about
5 µJy on S1 (4.7e-7 × 11 Jy), so it holds there with a factor of 10 to spare.

Same science in `f64`, differences well inside what `-beam-no-w` itself moves. In `f32`
neither path meets the threshold in the exact residual; that is the known floor of
ε 1e-4 and is not caused by the operator.

### Memory and the field

| image | R (f64, `S` 8, θ 0.69) | cube | status |
| --- | ---: | ---: | --- |
| 2048² | 15 | 2.0 GB (`f32`, R 12: 0.8 GB) | measured |
| 4096² | 38 | 20 GB (`f32`, R 31: **8.3 GB, peak 11.0 GB**) | `f32` measured |
| 8192² | 128 | about 275 GB | formula |

These are at `W` = 14,864 λ, the value of these tracks. `R` grows with `W` too.

At 4096², `f32`, 31 M visibilities, load 8-10: pass 5.02 s, 37.0 CPU-s; apply 4.22 s,
31.5 CPU-s; setup 37 s. Gridder: support 6, 11 planes, 6776². **The crossover has
moved up to about 31 M visibilities.** As the field grows the gridder's plane
spacing is a phase step of 2.7-3.8 rad (`2π dw X`), and the operator's is under
1 rad because of the doubled bandwidth, so its FFTs should tend to about 5× the
gridder's (an estimate). It is a narrow-field, many-visibility method.

### Limits, plainly

| what | effect |
| --- | --- |
| Time-invariant beam | fine: `diag(B) G̃ diag(B)` |
| Time-variable beam, A-terms, DD gains | breaks the structure; a rank-`r` model multiplies `R` by up to `r²` (not implemented) |
| New weights, flags or DI gain amplitudes | rebuild the cube, one setup |
| Wideband model | one cube set per moment pair, `2τ − 1` moments (not implemented) |
| Off-grid components | not representable; pixel models only |
| Model visibilities for self-calibration | still one degrid |
| Misfit | `Q` loses digits by cancellation, bound `η ‖m‖₁² / 2`. Measured: `point` Q 1.197e-5 from the operator, 1.273e-5 from the gridder, `f64`; 1.05e-4 against 1.28e-5 in `f32`. **Do not use it for a stop rule near the floor.** S3 gram ran 5 cycles against 4; cause not isolated |
| PSD | not guaranteed (§2) |

## 4. Prior art

Searched 2026-11-02. The first four are the verdict.

| source | what it does | relation |
| --- | --- | --- |
| Fessler, Lee, Olafsson, Shi, Noll 2005, IEEE TSP 53, 3393 (read, §III-IV) | MRI with off-resonance. Eq. 23 is the double sum, eqs 24-26 the single sum of `D_l' T_l D_l` with `T_l` Toeplitz, time segmentation, doubled bandwidth from `z*_k + z_j`, LS interpolators from the autocorrelated histogram | **The template.** `w` for time, `x` for the field map. Mine differs in compact-support `ψ` and in the Hartley setup |
| Dabbech and Wiaux 2026, arXiv 2605.26347, eqs 7-8 | `Φ†Φ = Σ_p Z_p† F† H_p F Z_p`: single sum over w-layers, hybrid w-stacking/w-projection, sparse holographic `H_p = G_p† G_p`, "blind to the data dimension" | **The visibility-free w-aware operator in radio is theirs.** Sparse `H_p` on hard w-bins with w-kernels, not FFT-diagonal |
| Sullivan et al. 2012, ApJ 759, 17 (FHD) | Precomputed sparse `H = B̃ᵀB`; loop does not re-grid visibilities | Earliest found; w-projection deferred |
| Kartik, Carrillo, Thiran, Wiaux 2017, MNRAS (arXiv 1609.02097) | Fourier dimensionality reduction | Compression of the same operator; earlier and broader |
| Bester et al. 2024, arXiv 2412.10073 (pfb-imaging); 2021, arXiv 2101.08072 | No raw visibilities during deconvolution, but residuals still through `R†Σ⁻¹R`; PSF convolution without w as a Hessian approximation or preconditioner | Keeps the `N_vis` cost per pass |
| Wajer, Pruessmann 2001; Fessler 2007 | Toeplitz gridding kernels, no w | Background (from memory; not re-read) |
| Ruiz-Antolín, Townsend 2018, SISC 40, A529 | Low-rank NUFFT via Chebyshev | The rejected global basis |
| Arras et al. 2021, A&A 646, A58 (wgridder); Atemkeng et al. arXiv 2009.07010; Tasse et al. 2018 (DDFacet); Barry et al. arXiv 2610.22752; arXiv 2511.17410 (Momentum-CLEAN) | Gridder, position-dependent PSF approximations, faceting, normal-operator analysis, major cycle as gradient step | No Toeplitz w-sum in what I read; several only in part |
| Offringa et al. (WSClean); van der Tol et al. (IDG) | w-stacking, image-domain gridding | Not re-read; no normal-operator scheme known to me |
| "HyperCLEAN", Ye et al. | Named in the task | **Not located.** Ye et al. 2021 is cited by others for improved w-stacking |

**Verdict.** Not new: the idea of a visibility-free major cycle, with or without w,
and the Toeplitz single sum. **Not found in the literature searched:** this transposition
to the w-term in radio imaging with an FFT-diagonal `(2n)²` real spectrum, a
correction-free compact LS `ψ`, the one-call Hartley setup, and a matched comparison
against a gridder at ducc0's speed. That is a gap in a limited search, not a novelty claim.

Against the project's rule: "comparable quality at materially lower cost" is **not met**
on gemclean's own default jobs. It is met only for many passes, and only against the
gridder. **No comparison with Dabbech and Wiaux's code was run.** A dense real plane
stores one number per cell where a sparse `H_p` stores up to `(2S−1)²` per occupied
cell, which should favour the dense form when `N_vis ≫ n²` and the sparse one when
`N_vis ≪ n²`: an estimate, not a measurement.

## 5. What is proved, where

**In Lean** (`Gridder.lean`; 61 theorems in the audit, standard axioms only):

| theorem | statement |
| --- | --- |
| `grid_eq_dirty`, `grid_degrid_eq_gram`, `grid_degrid_symm`, `gram_quadratic_nonneg` | if grid is the exact adjoint of degrid, however inaccurate, the residual and the beam are those of the approximate atoms, and the beam is a symmetric PSD Gram matrix |
| `dirty_update` | `r(m + d) = r(m) − Aᴴ A d`: the visibility-free law |
| `misfit_add_single_general`, `misfit_step_general` | the one-step law with `‖a_p‖² = 1 + η`; approximate atoms are not exactly unit |
| `residual_perturbation`, `dirty_perturbation`, `misfit_perturbation` | atom error `ε` gives `ε‖m‖₁` on the residual visibilities, and stated bounds on the image and the misfit |
| `gram_residual_bound`, `gram_quadratic_bound` | entrywise `η` gives `η‖m‖₁` on the residual, `η‖m‖₁²/2` on the visibility-free misfit |
| `working_step_descends`, `operator_step_descends` | a step on an approximate residual lowers the exact misfit if `(1 − γ/2) |r̃_p| > η‖m‖₁` |
| `gram_eq_node_sum`, `gram_node_sum_error` | the finite-sum identity, and `‖G − G̃‖_entry ≤ ε Σ|W_p|` |
| `sub_cast_injective`, `exists_embedding`, `dft_circConv`, `invDFT_product`, `embedded_convolution` | pixel differences are distinct mod `2n`; the zero-padded FFT pair is the Toeplitz sum, exactly |

**On paper only:** the rank estimate of §2; the combination
`‖(G − G̃) m‖_∞ ≤ (ε_w + Λ ε_uv) ‖W‖₁ ‖m‖₁`, whose `ε_uv` term assumes the gridder meets ε.

**Measured only:** `ε_w` (`sup_error`, on a dense grid, not a theorem); `Λ` = 1.4-1.8;
the gridder's accuracy; everything in §3.

**Not proved:** a bound on the expansion as a function of `S` and `θ`; PSD of the single
sum; item (d) of the task, a discrete aliasing identity, not attempted; Poisson summation.

## 6. Other candidates

| candidate | result | decision |
| --- | --- | --- |
| Weight-aware error budget | Two valid bounds on `⟨e, a_p⟩`. Triangle, `Σ W_q |e_q|` (so `ε_q` as `1/W_q`): `Σ S³` ×0.64-0.87 Briggs 0 on `point`, ×0.70-0.97 Briggs 0.5 on S1, ×1.00 in one coarse case each. Weighted norm, `‖e‖_W` (the task's `√w` form): ×0.70-0.98 and ×0.75-0.99, again ×1.00 in one case each. The norm bound lies above the triangle bound, so it cannot save more, and it does not. Natural weights: **×1.00**. **Counted, not implemented, no error test.** Part of it is slack, not weights: at σ 2, ε 1e-6 the global support 8 reaches 1.2e-7, and the budget spends that gap. Kernels are about 60 % of a job, so at most some 20 % of a Briggs job | The best small lead here: needs per-visibility support inside the tiles. A follow-up, with a real error test |
| Per-baseline support or w-plane assignment | Gridding error does not depend on the baseline beyond its weight; a plane's FFT is run if any visibility touches it, and small-w visibilities already touch only central planes | Dropped, no gain to take |
| Sparse Δm, image to grid | Row skip saves under a quarter of the 4-5 % FFT share; the plane loop on the image side could skip empty pixels, up to about a tenth of a job from the profile in `gemclean.md` §5.1. **Estimate, not implemented** | Not pursued; the row skip exists in the operator and is not visible there |
| Visibility compression with a proved bound | Averaging moves an atom by about `δ²/24`. Rows left, time only: `point` (60 s) 1.000, 1.000, 0.997 at ε 1e-6, 1e-4, 1e-3; S1 (8 s) 1.000, 0.980, 0.834. Time-averaging estimated from earth rotation | Dropped: nothing at the gridder's accuracy |

## 7. To test on an idle host

1. Whole jobs of §3, interleaved: only the wall times are in doubt, and the CPU
   differences suggest the wall-time ordering may change at low load.
2. The setup's serial parts and a real-weight gridder: is setup near 1 pass?
3. The full-track `W` of real MeerKAT data, including low declination.
4. A direct run of the operator inside a solver with many passes
   (`misfit_floor`'s CG, or forward-backward), the case it fits.

## 8. Reproduction

```bash
cargo +1.93 build --release --manifest-path core/Cargo.toml --bin gridder_gram_bench --bin gemclean
B=core/target/release/gridder_gram_bench; M=$HOME/Build/tmp/20261102-gmclean-opt/point/sim.ms
$B $M 2048 1.5 0 pass 1e-6 double 2
$B $M 2048 1.5 0 apply 8 0.69 double 1e-6 3
GRAM_STRIDE=4 $B $M 2048 1.5 0 apply 8 0.69 double 1e-6 0
$B $M 2048 1.5 0 accuracy 1e-6:d,1e-4:s 8:0.69:1e-6:d,6:0.82:1e-4:s
GRAM_INTERVAL=60 $B $M 2048 1.5 0 budget
bash examples/gridder_gram_jobs.sh OUT 8,0.69 6,0.82
python3 examples/gridder_gram_archive.py RUN_DIR research/results/gridder-theory.json
```

`RAYON_NUM_THREADS=8`, each run under `flock /home/gijsm/.rang-heavy.lock`.
Run data: `/home/gijsm/Build/tmp/20261102-gridder-gram/` (to be deleted; compact copy
in the archive). Seeds: `20261102` and `424242` in the bench's test models.

Sources: [Fessler et al. 2005](https://web.eecs.umich.edu/~fessler/papers/lists/files/jour/05/pre/tsp,fessler.pdf),
[Dabbech and Wiaux 2026](https://arxiv.org/abs/2605.26347),
[Sullivan et al. 2012](https://arxiv.org/abs/1209.1653),
[Kartik et al. 2017](https://arxiv.org/abs/1609.02097),
[Bester et al. 2024](https://arxiv.org/abs/2412.10073),
[Bester et al. 2021](https://arxiv.org/abs/2101.08072),
[Ruiz-Antolín and Townsend](https://arxiv.org/abs/1701.04492),
[Arras et al. 2021](https://arxiv.org/abs/2010.10122),
[Atemkeng et al.](https://arxiv.org/abs/2009.07010),
[Tasse et al. 2018](https://arxiv.org/abs/1712.02078),
[Barry et al. 2026](https://arxiv.org/abs/2610.22752),
[Momentum-CLEAN](https://arxiv.org/abs/2511.17410).
