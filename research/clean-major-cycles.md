# Rang: how many major cycles does CLEAN need?

The user's question, 2026-11-02: the major/minor cycle convention of CLEAN
looks like a hack; can the same computation be done in Fourier space, or can
the number of major cycles be reduced, ideally to a few? Branch
`clean-major-cycles`, continuing the CLEAN programme of
[clean-theory.md](clean-theory.md) (the Gram formalism, Theorems 1-6) and
[clean-certified-imaging.md](clean-certified-imaging.md) (the instrumented
Cotton-Schwab driver and the Gram gap). Every claim is labelled proposed,
implemented or measured.

Code: [`core/src/clean_major.rs`](../core/src/clean_major.rs) (driver, FFT
batches, optimisation phase, w-term bound; five unit tests),
[`core/examples/clean_major_cycles.rs`](../core/examples/clean_major_cycles.rs)
(the simulations), [`formal/RangFormal/MajorCycle.lean`](../formal/RangFormal/MajorCycle.lean)
(the theorems of §3, machine-checked). Archive:
[`results/clean-major-cycles.json`](results/clean-major-cycles.json).

## 1. Summary

**Answer.** The alternation is not intrinsic. A major cycle exists to correct
the minor cycle's approximate Hessian; with the planar operator and a PSF on
the `2n` grid there is nothing to correct, and one pass suffices. Fourier space
removes the visibility pass only as far as the operator is shift-invariant: the
argmax still lives in the image, and the w-term is what keeps visibility passes
necessary. On these simulations "a few" means **two or three passes**, against
four to seven for WSClean's scheme. It does not mean one, and the reason is
not the misfit gap.

- **Theory (proposed; Lean except Proposition 7 and §4).** The Gram-gap identity
  for any pick order and any beam, per-cycle descent, a running gap bound, the
  forcing term of a greedy cycle, and the outer rate
  `Q_K − Q_∞ ≤ (1 − θc)^K (Q_0 − Q_∞)` without an invertible beam. The worst-case
  `c` is one Högbom step per cycle, so **the theory does not promise few
  cycles**; it says what sets the number.
- **Major cycles (measured; 512² field, 12 datasets, range and median).**
  WSClean's scheme 4-7 (5); double-size PSF with mgain 0.8, 3-4 (4); double-size
  PSF run to the threshold, 2-3 (2); the same with minor cycles stopping at 0.9
  of the threshold, 1-2 (2); the planar control 1 in all 14 cases, wide field
  included. Wide field (1024² of 4″, natural weights, two datasets), same order:
  5-6, 6, 3-4, 2, 1.
- **The gap (measured).** With the double-size PSF, max `|gap|/Q` per scheme is
  2e-5 to 2e-3 at 512² and up to 1.3e-2 on the wide field, against 9e-10 and
  3e-12 for the planar control. Theorem 3 is therefore far from binding. What
  forces the second pass is **pointwise**: after the first pass the exact peak
  is 15.6-24.2 mJy against the 15 mJy threshold (§6.3).
- **Negative results.** (i) The certified rules with the analytic w bound cost
  *more* passes than mgain: 7-30, with 19 of 36 runs stopped by the 30-pass cap
  and residual peaks up to 287 mJy. The bound exceeds the measured gap by 6e3 to
  4e6 and saturates at its cap of 2 on the wide field. (ii) A measured
  (uncertified) bound gives 2-8 passes, never fewer than plain run-to-threshold.
  (iii) The optimisation phase *raises* passes to 6-10, while lowering components
  by a third. (iv) The image-size PSF did not diverge on 64 dishes (`f` about
  1 %, 0 audited ascending steps), unlike the four-station LUNO slice.
- **Timing: PROVISIONAL (contended host, §6.6).** No wall-time difference between
  schemes is claimed unless it is far larger than the variation between repeats
  (up to a factor 2.8). Only one candidate survives, and it compares parallel
  code with serial code.

No imaging-quality improvement is claimed: skies are simulated on grid pixels,
and only `Q`, residual statistics and total flux were compared.

## 2. Setting

As in clean-theory.md §2.1: `E` is the real inner-product space of weighted
visibilities, `a_p ∈ E` the atom of pixel `p` (unit norm), `A m = Σ_p m_p a_p`,
`B = AᵀA` the Gram matrix (the exact PSF, `B_pq = ⟨a_p, a_q⟩`), the misfit
`Q(m) = ½‖v − A m‖²`, the residual image `r(m) = Aᵀ(v − A m) = −∇Q`, and the
floor `Q_∞ = inf_m Q(m)` (clean-theory Theorem 2). A *major cycle* evaluates
`r` and `Q` through the measurement operator (degrid and grid all
visibilities). A *minor cycle* takes greedy steps `c_k = γ r̃_k / b̃(0)` at
pixels `p_k` against a working residual updated with a beam `b̃`,
`r̃_k = r_{p_k} − Σ_{i<k} c_i b̃(p_k, p_i)`, where `b̃(q, j)` is what the
minor cycle subtracts at pixel `q` for a unit component at `j` (a shifted
PSF, a patch, a PSF computed on the image grid). The increment of the cycle
is `Δ = Σ_k c_k e_{p_k}`.

## 3. Theory (proposed; §3.1-3.5 machine-checked)

### 3.1 The exact change and what the minor cycle believes

**Theorem 1 (the batch is a quadratic step).** For any model `m` and any
batch, `Q(m + Δ) − Q(m) = −Σ_k c_k r_{p_k} + ½ Σ_k Σ_l c_k c_l B_{p_k p_l}`,
i.e. `−⟨r, Δ⟩ + ½ Δᵀ B Δ`. Proof: expand `‖e − A Δ‖²` and use
`‖Σ_k c_k a_{p_k}‖² = Σ_{k,l} c_k c_l ⟨a_{p_k}, a_{p_l}⟩`. Lean:
`Clean.misfit_add_batch`.

**Theorem 2 (the Gram-gap identity).** The minor cycle accumulates the
believed change `dQ̃ = Σ_k (−c_k r̃_k + ½ c_k² b̃(p_k, p_k))`. For any beam
`b̃`, symmetric or not,

`dQ − dQ̃ = Σ_k ( Σ_{i<k} c_k c_i D(p_k, p_i) + ½ c_k² D(p_k, p_k) )`,
`D = B − b̃`.

Proof: substitute `r̃_k` into `dQ̃`; the symmetric double sum of Theorem 1
splits as `½ Σ_{k,l} x_k x_l G_kl = Σ_k (Σ_{i<k} x_k x_i G_ki + ½ x_k² G_kk)`
(`Clean.half_double_sum`, by induction on the number of steps). Lean:
`Clean.misfit_batch_gap`. For a symmetric `b̃` the belief is the quadratic
model `−⟨r, Δ⟩ + ½ Δᵀ b̃ Δ` and the gap is `½ Δᵀ (B − b̃) Δ`, the framing of
the question; this is clean-certified-imaging.md §2.2, now proved for any
order of picks, repeated pixels and nonsymmetric beams (the w-gridded
double-size PSF of §4 is not centrosymmetric).

### 3.2 Per-cycle descent and a rule the minor cycle can evaluate

**Theorem 3 (per-cycle descent).** If `gap ≤ (1 − θ)(−dQ̃)` then
`dQ ≤ θ dQ̃`. With `dQ̃ < 0` and `θ ∈ (0, 1]` the cycle lowers the true misfit
by at least `θ |dQ̃|`. Lean: `Clean.misfit_batch_descent` (from
`descent_of_gap`, one line of arithmetic).

This is the acceptance test of a trust-region method, `ρ = dQ/dQ̃ ≥ θ`
(Moré 1983; Conn, Gould and Toint 2000), applied to the CLEAN cycle. What is
specific to CLEAN is that the gap has the closed form of Theorem 2, so the
ratio can be bounded *during* the minor cycle instead of tested after the
expensive major cycle.

**Theorem 4 (a bound the minor cycle can keep).** If `|D(q, j)| ≤ f(j)` for
every target pixel `q` (the error of the subtracted beam for a component at
`j`), then

`|gap| ≤ Σ_k |c_k| ( Σ_{i<k} |c_i| f(p_i) + ½ |c_k| f(p_k) )`.

Lean: `Clean.gapForm_le`. The inner sum `E_k = Σ_{i<k} |c_i| f(p_i)` is the
pointwise bound on `|r − r̃|` at step `k` (Theorem 6 of clean-theory.md with
a per-component `f`: `Clean.truncation_error_le_pixel`). Both are running
sums: `O(1)` work per step. Hence two provable stopping rules:

- **per step** (Theorem 6'): continue while `E_k < (1 − γ/2) |r̃_k|`; every
  step lowers the true misfit (`Clean.clark_minor_cycle_descends_pixel`).
  Implemented as `CycleRule::Provable`.
- **per cycle**: continue while `Σ_k |c_k| E_k (+ diagonal) ≤ (1 − θ)|dQ̃|`;
  the whole cycle lowers `Q` by at least `θ|dQ̃|`, although single steps may
  rise (`Clean.misfit_batch_descent_of_bound`). Implemented as
  `CycleRule::Cycle(θ)`. It is far more permissive than the per-step rule:
  for one source of flux `F` and an `f` that is constant, the cycle's
  `Σ|c| → F` and `|dQ̃| → F²/2`, so the rule never stops when `f < 1 − θ`,
  while the per-step rule stops once the residual falls to `f/(1 − γ/2)` of
  `F`.

With `b̃(0) = B_pp` (true for every beam used here: the PSF peak is the norm
of an atom) the diagonal term vanishes; the code keeps only `Σ_k |c_k| E_k`.

**WSClean's `-mgain`** stops when the working peak has fallen by the factor
`1 − mgain`. It is not of either form: it never looks at `f`, so it neither
protects against a large gap (the LUNO divergence of
clean-certified-imaging.md, gap 99 Q) nor exploits a small one (it forces
a visibility pass after every factor of five in the peak even when the beam
is exact). It is an unprincipled forcing term.

### 3.3 The forcing term and the outer rate

**Theorem 5 (the forcing term of a greedy cycle).** With a unit-diagonal
beam and `c_k = γ r̃_k`, `0 ≤ γ ≤ 2`, every believed step equals
`−γ(2−γ)/2 · r̃_k² ≤ 0`, so a cycle believes at least the decrease of its
first step, `dQ̃ ≤ −γ(2−γ)/2 · r_{p_0}²`, and that first step is exact
because the working residual was just reset. Lean: `Clean.predicted_le_first`.
With the greedy ratio of clean-theory Theorem 3, `κ = r_peak² / (2(Q − Q_∞))`,
this is `dQ̃ ≤ −γ(2−γ) κ (Q − Q_∞)`.

**Theorem 6 (outer linear rate).** If every major cycle satisfies
`Q_{K+1} − Q_K ≤ θ dQ̃_K` (Theorem 3) and every minor cycle believes
`dQ̃_K ≤ −c (Q_K − Q_∞)` with `0 ≤ θc ≤ 1`, then

`Q_K − Q_∞ ≤ (1 − θ c)^K (Q_0 − Q_∞)`.

Lean: `Clean.major_linear_rate` and `Clean.major_linear_rate_of_gap` (the
same with the gap identity and the gap condition as hypotheses). The number
of major cycles to reach `(Q − Q_∞) ≤ ε (Q_0 − Q_∞)` is at most
`log(1/ε) / (−log(1 − θc))`.

What the theorem does and does not promise. Its hypotheses are honest and
checkable: `θ` comes from the gap rule, `c` from what the minor cycle
believed. Its worst case is weak: Theorem 5 only guarantees `c = γ(2−γ)κ`,
one Högbom step's worth per major cycle, and on noise `κ ~ 1/N`
(clean-theory E3). So the theory **cannot** promise "a few" major cycles in
general; it says *what sets the number*: the believed decrease per cycle
relative to `Q − Q_∞` (large when the minor cycle runs long, i.e. when its
beam is good) and the factor `θ` the gap leaves. The number of major cycles
is a property of how inexact `b̃` is, not of CLEAN. In the limit of an exact
beam:

**Proposition 7 (one visibility pass).** If `b̃ = B` (the gap is zero) and
the minor cycle runs until its working peak is below the threshold `t`, the
working residual *is* the exact residual, so one visibility pass confirms
`max |r| < t` and the run ends. More generally, if the minor cycle stops at
`max |r̃| < t'` and `Σ_k |c_k| f(p_k) ≤ t − t'`, then `max |r| < t` after the
pass (Theorem 4's pointwise bound, `truncation_error_le_pixel`). The first
statement is the planar control of §6.3 (one pass in all 14 cases); the second
is a certificate in principle but, with the bounds of §4, `Σ|c| f` exceeds
the threshold by orders of magnitude, so a margin `t' = 0.9 t` is used as a
heuristic and measured.

Against the literature. Dembo, Eisenstat and Steihaug (1982) control the
residual of the inner linear solve, `‖∇Q + B Δ‖ ≤ η ‖∇Q‖`, with the exact
Hessian; here the inner solve is greedy and the *Hessian* is inexact, which
is the trust-region/approximate-Hessian setting, and the forcing is on
`Q − Q_∞` rather than on a gradient norm, so no invertibility of `B` is
needed. Müller, Hsieh and Bhatnagar (2025, A&A, arXiv:2511.17410) identify
Cotton-Schwab CLEAN with a Newton scheme and accelerate the major loop with
Nesterov momentum and conjugate-gradient orthogonalisation, reporting
several-fold faster convergence; they say themselves that the identification
is not rigorous and that Newton assumes an invertible beam (quoted in
clean-theory.md §1; only the abstract was re-read for this note, on 2026-11-02,
and it states no convergence theorem). Moré, Conn et al., Dembo et al., Clark
and Schwab are cited from memory and were not re-read for this note.
Theorems 3-6 are that rigorous statement for the plain loop, without
invertibility, and Proposition 7 says where acceleration of the major loop
can still win: only where the minor cycle is stopped early (by `mgain`) or
its beam is poor. Clark (1980) and Schwab (1984) are discussed in §4.4. The
theorems themselves are elementary; the new parts are the closed-form gap
inside the cycle, the per-component w bound of §4 and the measurements.

### 3.4 Lean status

`formal/RangFormal/MajorCycle.lean`: `misfit_add_batch` (Theorem 1),
`half_double_sum`, `misfit_batch_gap` (Theorem 2), `descent_of_gap`,
`misfit_batch_descent` (Theorem 3), `gapForm_le`,
`misfit_batch_descent_of_bound` (Theorem 4), `predicted_le_first`
(Theorem 5), `major_linear_rate`, `major_linear_rate_of_gap` (Theorem 6),
`truncation_error_le_pixel`, `clark_minor_cycle_descends_pixel`
(Theorem 6'). All twelve are in `Audit.lean` and rest on `propext`,
`Classical.choice` and `Quot.sound` only. Not formalised: Proposition 7
(a corollary in prose) and §4 (the w-term bound is analysis of the cosine,
measured instead; the circulant embedding is checked numerically).

## 4. What the double-size PSF makes exact (proposed; measured in §6)

### 4.1 Without the w-term

For the planar (w-free) measurement the Gram matrix is a function of the
offset only, `B_pq = Σ_k W_k cos(2π u_k·(x_q − x_p)) = b(x_q − x_p)`: a
two-level Toeplitz matrix. Two pixels of an `n × n` image have offsets in
`−(n−1)…(n−1)` on each axis; a PSF image on a grid of side `≥ 2n − 1`
centred on the phase centre holds every one of them. Hence:

1. **The minor cycle with the double-size PSF is exact** for the planar
   direct-Fourier operator: `D = 0`, the gap is zero, Theorem 1 of
   clean-theory.md holds step by step. What remains is the accuracy `ε`
   with which the gridder computes that PSF and the operator (`wgridder`
   tolerance; 1e-7 in §6). The *gridded* operator `A_ε` actually used in
   the major cycle is itself not exactly shift-invariant (the kernel's
   aliasing error depends on position), so its Gram differs from `b` by
   `O(ε)`. Measured: the planar gap is at most 9e-10 of `Q` at 512² and 3e-12 on the wide field (§6.4).
2. **The circulant embedding.** On a grid of side `L ≥ 2n − 1`, the
   circular convolution of the zero-padded component image with the
   wrapped kernel equals the linear convolution on the `n × n` window,
   because the offsets `−(n−1)…(n−1)` fall on distinct residues modulo `L`.
   With `L = 2n`, subtracting a batch of `K` components costs one forward
   and one inverse FFT of `(2n)²` points (`FftConvolver`) instead of `K`
   full-image subtractions of `n²`. Unit test: equal to direct subtraction
   to 1e-12 (`fft_batch_equals_direct_subtraction`, odd and even `n`).
3. **This is the Fourier-space form of the major cycle.** The FFT of the
   double-size PSF is the gridded sampling function on the `2n` uv grid, so
   "subtract the model and form the residual image" is
   `d − IFFT(Ŝ · FFT(pad m))`: no visibilities are touched. For a planar
   array the whole Cotton-Schwab iteration can run on the `2n` grid and the
   alternation image ↔ visibilities disappears, except for one final pass
   to account for `ε`.

### 4.2 With the w-term

With w-gridding the atoms carry the phase `w_k ñ(x)`, `ñ = √(1 − l² − m²) − 1`,
and the Gram matrix is

`B_pq = Σ_k W_k cos(2π(u_k·(x_q − x_p) + w_k(ñ_q − ñ_p)))`,

no longer shift-invariant. The double-size PSF is the column of the phase
centre, `b(Δ) = Σ_k W_k cos(2π(u_k·Δ + w_k ñ(Δ)))`, not centrosymmetric and
not a Gram matrix. Subtracting it for a component at `x_p` errs by

`|D(q, p)| ≤ 2π (Σ_k W_k |w_k|) · |ñ_q − ñ_p − ñ(x_q − x_p)| =: f_w(p, q)`,

because the `u·Δ` phases cancel and `|cos α − cos β| ≤ |α − β|`. To second
order `ñ_q − ñ_p − ñ(x_q − x_p) = −x_p·(x_q − x_p)`: zero for a component
at the phase centre, linear in its distance from it, and at most `L²` for a
square field of side `L` radians (corner to opposite corner). The per-pixel
bound `f_w(p) = max_q f_w(p, q)` is `w_term_bound` (maximum over the image
boundary, which the second-order form makes exact; checked against the full
maximum in the unit test `w_term_bound_holds_for_the_double_size_beam`,
where the true Gram columns of six pixels, from the gridder, stay within the
bound and the centre column equals the PSF to 1e-9). This gap **is the
irreducible reason for visibility passes** in a single-PSF scheme: it
scales with the weighted mean `|w|` (declination, weighting) and with the
square of the field of view in the bound (the measured deviation grows more slowly); §6.2 measures it.

### 4.3 What the double-size PSF does not fix

Direction-dependent effects (primary beam, pointing), multi-frequency
synthesis, time and bandwidth smearing and the gridding kernel are all part
of the operator and break shift invariance the same way the w-term does;
none is modelled here. Faceted PSFs (the double-size PSF computed at several
phase centres with `center_x`, `center_y`) would shrink `f_w` by the facet
size squared over the field size squared; proposed, not implemented.

### 4.4 Clark 1980 and Schwab 1984

Clark (1980, A&A 89, 377) introduced exactly the FFT batch: minor cycles on
a beam patch over the brightest pixels, then a "major cycle" that convolves
the components with the full beam by FFT and subtracts them from the
residual *image*. Schwab (1984, AJ 89, 1076) moved the subtraction to the
ungridded visibilities, which removes the aliasing of the image-plane
convolution and admits the w-term and other direction-dependent effects.
So proposal (B) below is Clark's scheme; what is added is the observation
that with a `2n` grid the image-plane correction is *exact* for the planar
operator (this note did not verify how Clark handled wrap-around), an
active-set batch that is exact inside the batch, and a schedule for the
remaining visibility passes from the w bound. The double-size PSF itself
("image a field twice the size, clean the inner quarter") is standard
practice and not new.

## 5. Implementation (implemented; tested)

`core/src/clean_major.rs`, registered in `core/src/lib.rs`, beside the
untouched `clean_certified::run` (the Python binding and the LUNO results
depend on it):

- `run_cycles(measurement, beams, settings, q_floor)`: the driver. Per
  cycle: a minor cycle (`Subtraction::Direct`: argmax over the image and a
  full beam subtraction per step; `Subtraction::Batched { active }`: picks
  on the `active` largest pixels, updated exactly with the beam per step, a
  batch ending when the active peak falls below the largest pixel left
  outside, then the whole image corrected by one `FftConvolver::apply`);
  stop rules `MajorGain(g)`, `Provable`, `Cycle(θ)`, `Threshold`, with the
  running bounds `E_k` and `Σ|c_k| E_k` from a uniform truncation bound plus
  a per-pixel bound; an optional minor threshold below the run threshold;
  the optimisation phase; one exact residual evaluation. Per cycle it
  records the components, FFT batches, `Q` before and after, `dQ`, `dQ̃`, the
  gap and its bound, the optimisation phase's support and model change, the
  greedy ratio and reducible fraction, and the minor, optimisation and
  major seconds separately. An optional step audit counts steps that raise
  the quadratic of a reference beam (the double-size PSF) when the minor
  beam is truncated; `O(J²)` per cycle of `J` steps instead of a second
  full-image residual. With the w-term on, the audit's reference is not the
  true Gram matrix; ascending *cycles* (`dQ > 0` from the exact misfit) are
  reported instead.
- `FftConvolver`: the wrapped kernel's FFT once; per batch a forward FFT of
  the first `n` rows (the rest are zero padding), a transpose, a forward
  FFT, the product, the inverse, and the inverse of the first `n` rows; rows
  in parallel (rayon), `rustfft` plans.
- `OptPhase { max_support, iterations }`: after the greedy picks, conjugate
  gradients on `B̃_TT y = r̃_T` over the cycle's distinct pixels `T`, with the
  symmetrised beam entries, from `y = 0`, i.e. started at the greedy
  increment, so the model misfit can only fall (CG decreases the quadratic
  monotonically); the increment becomes the exact least-squares fit on `T`
  when CG converges. CG rather than `solve_dense`: on coherent supports
  `B_TT` is singular to working precision (clean-certified-imaging.md §5.4).
- `w_term_bound`, `mean_abs_w`: §4.2.

Unit tests (`cargo test --release --manifest-path core/Cargo.toml clean_major`):
FFT batch equals direct subtraction to 1e-12 (`n` = 13, 16, 24); with the
exact beam a minor cycle run to the threshold needs one visibility pass and
its gap is below 1e-11 of `Q`, for direct and batched subtraction; with the
image-size beam the per-cycle gap equals its closed form to 1e-10 and stays
within the running bound, the cycle rule gives `dQ ≤ θ dQ̃` and the
per-step rule no ascending step (six seeds); the optimisation phase keeps
the support and lowers the final misfit, with model change equal to the
true change (six seeds); the w bound holds for true Gram columns from the
gridder.

## 6. Measurements (measured; timings provisional)

### 6.1 Set-up

`core/examples/clean_major_cycles.rs` at commit `de303bf`, Windows workstation,
16 threads, run `outputs/clean-major-cycles-20261102` (ignored); tables in its
`stdout.md`; archive [`results/clean-major-cycles.json`](results/clean-major-cycles.json).
MeerKAT 64 antennas, 1.4 GHz, one channel, hour angle −2 h to +2 h every 120 s
(243,936 visibilities, `2M` = 487,872), declinations −30° and −70°, natural and
Briggs 0 weights, `WgridMeasurement` with w-gridding on, ε = 1e-7. Gain 0.1,
threshold 15 mJy (3σ), divergence limit 4, at most 30 passes. Skies on grid
pixels, seeds 1000-1002, noise seeds 77-79: `points` (50 sources log-uniform
over two decades, brightest 1 Jy), `disc` (the same plus an off-centre 1 Jy
Gaussian of FWHM 20 px), `crowded` (500 sources); complex noise scaled to an
image rms of 5 mJy. 158 runs. The 1024² field of 4″ ran `points`, natural
weights, six schemes only. Its 4″ cell undersamples the longest baselines
(fringe about 5.5″), and its `N` exceeds `2M`.

Schemes: `wsclean` (image-size PSF, mgain 0.8); `image-provable` (per-step rule,
truncation plus analytic w bound); `double-mgain`; `double-provable`;
`double-cycle` (cycle rule θ = 0.5, analytic bound); `double-cycle-measured` (the
same, with twice the worst probe deviation scaled by distance from the phase
centre: **not a certificate**); `double-threshold`; `double-threshold-margin`
(minor cycles stop at 13.5 mJy); `fft-cycle-measured` and `fft-threshold-margin`
(batched, 4,096 active pixels); `opt-mgain` (optimisation phase, at most 50 CG
iterations); `planar-threshold` (data and operator without w).

### 6.2 What the w-term does to the double-size PSF

True Gram columns from the gridder at 11 probe pixels, all targets, against the
double-size PSF shifted there. The centre probe agrees to 6e-9 to 3.5e-8, the
gridder's tolerance. `f_trunc` is the image-size PSF's truncation. The last two
columns are the first cycle of `double-threshold` on `points` (natural weights
only on the wide field).

| field | dec | weights | mean \|w\| (λ) | f_trunc | analytic f_w max | measured max deviation | measured / bound | first-cycle \|gap\|/Q | exact peak after pass 1 (mJy) |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 512 × 2″ | −30 | natural | 1,159 | 0.0158 | 0.179 | 2.00e-3 | 0.013 | 2.1e-5 | 15.82 |
| 512 × 2″ | −30 | Briggs 0 | 2,177 | 0.0122 | 0.336 | 4.25e-3 | 0.015 | 9.0e-5 | 16.33 |
| 512 × 2″ | −70 | natural | 2,751 | 0.0114 | 0.425 | 2.66e-3 | 0.008 | 4.8e-5 | 15.63 |
| 512 × 2″ | −70 | Briggs 0 | 5,013 | 0.0092 | 0.775 | 6.83e-3 | 0.011 | 2.7e-4 | 17.34 |
| 1024 × 4″ | −30 | natural | 1,159 | 0.0127 | 2 (cap) | 9.12e-3 | 0.005 | 2.2e-3 | 18.57 |
| 1024 × 4″ | −30 | Briggs 0 | 1,857 | 0.0107 | 2 (cap) | 1.23e-2 | 0.006 | – | – |
| 1024 × 4″ | −70 | natural | 2,751 | 0.0117 | 2 (cap) | 1.13e-2 | 0.006 | 7.9e-3 | 23.17 |
| 1024 × 4″ | −70 | Briggs 0 | 4,393 | 0.0105 | 2 (cap) | 1.51e-2 | 0.008 | – | – |

The bound holds everywhere and is 67-185 times loose in the single entry
(`|cos α − cos β| ≤ |α − β|` ignores cancellation over baselines; the 1024² ratios
are against the capped value). The measured deviation grows more slowly than the
bound's `w̄ L²`: a field four times wider raises it by 4.2-4.6 with natural
weights, against 16; a mean `|w|` 2.4 times larger raises it by 1.2-1.3. The
explanation (phase errors decorrelate over baselines, so far offsets average down)
is proposed, not measured. The gap itself grows much faster than the entry, by a
factor of 100-165 for the wider field, because the first cycle holds more
components spread further apart: it is a quadratic form in the batch.

### 6.3 Major cycles

Passes per scheme. A superscript ᶜ marks a run stopped by the 30-pass cap above
the threshold (peaks 15.3-287 mJy, flux −6 to −61 %).

| dataset (dec, weights, sky) | wsclean | image-provable | double-mgain | double-provable | double-cycle | cycle-measured | double-threshold | threshold-margin | fft-cycle-measured | fft-margin | opt-mgain | planar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| −30 natural points | 5 | 11 | 3 | 9 | 7 | 2 | 2 | 1 | 2 | 1 | 6 | 1 |
| −30 natural disc | 4 | 17 | 4 | 14 | 12 | 2 | 2 | 1 | 2 | 1 | 6 | 1 |
| −30 natural crowded | 7 | 30ᶜ | 4 | 30ᶜ | 30ᶜ | 2 | 2 | 2 | 2 | 2 | 9 | 1 |
| −30 Briggs points | 4 | 26 | 4 | 24 | 21 | 2 | 2 | 2 | 2 | 2 | 10 | 1 |
| −30 Briggs disc | 5 | 30ᶜ | 4 | 30 | 27 | 2 | 2 | 2 | 2 | 2 | 8 | 1 |
| −30 Briggs crowded | 5 | 30ᶜ | 4 | 30ᶜ | 30ᶜ | 6 | 3 | 2 | 5 | 2 | 8 | 1 |
| −70 natural points | 5 | 20 | 4 | 19 | 17 | 3 | 3 | 1 | 3 | 1 | 6 | 1 |
| −70 natural disc | 4 | 30 | 4 | 28 | 26 | 3 | 3 | 1 | 3 | 1 | 10 | 1 |
| −70 natural crowded | 7 | 30ᶜ | 4 | 30ᶜ | 30ᶜ | 2 | 2 | 2 | 2 | 2 | 6 | 1 |
| −70 Briggs points | 5 | 30ᶜ | 4 | 30ᶜ | 30ᶜ | 2 | 2 | 2 | 2 | 2 | 9 | 1 |
| −70 Briggs disc | 5 | 30ᶜ | 4 | 30ᶜ | 30ᶜ | 2 | 2 | 2 | 3 | 2 | 9 | 1 |
| −70 Briggs crowded | 5 | 30ᶜ | 4 | 30ᶜ | 30ᶜ | 8 | 3 | 2 | 8 | 2 | 7 | 1 |
| wide −30 natural points | 6 | – | 6 | – | – | 3 | 3 | 2 | – | 2 | – | 1 |
| wide −70 natural points | 5 | – | 6 | – | – | 4 | 4 | 2 | – | 2 | – | 1 |

Reading it:

1. **mgain sets its own count.** Each cycle lowers the peak by five, so reaching
   15 mJy from 1 Jy takes `log₅(67) = 2.6`, hence 3 cycles plus any tail.
   `double-mgain` measures 3-4 at 512²: the count is the schedule, not the beam.
2. **The image-size PSF adds a tail.** `wsclean` needs 0-3 more cycles than
   `double-mgain`, near the threshold. It never ascended (0 audited steps against
   the double-size PSF, 0 ascending cycles); its max gap is 1.7e-2 of `Q`, on the
   crowded field. With a 1 % truncation this is mild, unlike LUNO's 77 %.
3. **Running to the threshold saves about two passes, and the planar control
   shows the rest is the w-term.** The same schedule without w takes one pass in
   all 14 cases. With w, the first pass holds 93-99 % of the components at 512²
   and the second cleans 11-557. It is forced because the exact peak after the
   first pass is 15.6-24.2 mJy, not because `Q` went wrong: `|gap|/|dQ̃|` is 1.4e-6
   to 2.0e-2. **Stopping at a threshold is an ℓ∞ criterion, and a gap of 1e-4 of
   `Q` can still move a pixel across it.**
4. **The margin is a heuristic and costs depth.** `t' = 0.9 t` gives one pass in
   4 of 12 datasets at 512², all natural weights with few sources, and two
   elsewhere. It cleans deeper (exact peaks to 13.5 mJy) with more components:
   median 2,942 against 1,865 at 512², 12,875 against 6,897 on the wide field.
   These runs are not the same stopping point as the others.
5. **Thread count.** Four schemes on one crowded sky, at 1 and at 16 rayon threads,
   gave identical passes, components and printed gaps, equal to the full run's. 74
   runs following the same schedule in the earlier smoke run gave identical passes
   and components. No dependence on thread count was seen where tested; only that
   one sky was tested at 1 thread.

### 6.4 Gap per scheme, and what each scheme reaches

Ranges over the datasets of each field. Gaps are relative to `Q` at the cycle's
start; `Q` is dominated by noise, so `|gap|/|dQ̃|` is the number Theorem 3 uses.
`θ = 0.5` would allow 0.5. Ascending cycles are 0 in all 158 runs. Capped runs are
included, which is why the provable rows have low gaps and large flux errors: they
stopped early.

| scheme | field | components (median) | max \|gap\|/Q | median \|gap\|/Q | max \|gap\|/\|dQ̃\| | median rms (mJy) | median flux error |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wsclean | 512² | 1,710 | 1.7e-2 | 7.8e-5 | 4.9e-2 | 4.99 | −5.9 % |
| image-provable | 512² | 1,420 | 3.7e-4 | 1.4e-6 | 1.7e-3 | 5.06 | −7.8 % |
| double-mgain | 512² | 1,676 | 1.4e-4 | 1.2e-5 | 3.5e-4 | 5.01 | −5.6 % |
| double-provable | 512² | 1,419 | 2.4e-5 | 5.6e-8 | 8.5e-5 | 5.06 | −7.6 % |
| double-cycle | 512² | 1,419 | 3.7e-5 | 2.8e-8 | 1.1e-4 | 5.06 | −7.5 % |
| double-cycle-measured | 512² | 1,865 | 2.7e-4 | 4.2e-5 | 4.8e-4 | 4.95 | −5.5 % |
| double-threshold | 512² | 1,865 | 1.2e-3 | 4.2e-5 | 1.3e-3 | 4.92 | −5.2 % |
| double-threshold-margin | 512² | 2,942 | 1.7e-3 | 1.2e-4 | 1.9e-3 | 4.78 | −4.6 % |
| fft-cycle-measured | 512² | 1,865 | 2.7e-4 | 1.5e-5 | 4.8e-4 | 4.95 | −5.5 % |
| fft-threshold-margin | 512² | 2,942 | 1.7e-3 | 1.2e-4 | 1.9e-3 | 4.78 | −4.6 % |
| opt-mgain | 512² | 1,104 | 2.9e-4 | 1.5e-7 | 1.0e-3 | 4.51 | −0.3 % |
| planar-threshold | 512² | 1,662 | 8.9e-10 | 8.4e-11 | 1.1e-9 | 5.02 | −5.6 % |
| wsclean | wide | 2,808 | 1.2e-4 | 3.0e-5 | 3.2e-3 | 4.78 | −5.7 % |
| double-mgain | wide | 2,744 | 3.4e-5 | 6.7e-6 | 2.1e-3 | 4.79 | −5.7 % |
| double-threshold | wide | 6,897 | 7.9e-3 | 7.9e-8 | 2.0e-2 | 4.51 | −4.5 % |
| double-threshold-margin | wide | 12,875 | 1.3e-2 | 8.8e-3 | 3.3e-2 | 4.26 | −3.5 % |
| planar-threshold | wide | 2,638 | 2.8e-12 | 2.1e-12 | 7.2e-12 | 4.80 | −5.4 % |

Final `Q/Q_0` barely separates schemes that reach the threshold: for example 0.6216
(`wsclean`), 0.6212 (margin) and 0.6193 (`opt-mgain`) on −30 natural points; 0.0880,
0.0867 and 0.0857 on −30 Briggs crowded. Per-dataset values are in the archive. The
flux error is against all simulated flux including sources below the threshold,
so the −5 % is at least partly faint sources left in the residual; it is not a bias
estimate. The running analytic bound held in all 1,136 cycles it covers, and the
measured one in all 79, but the first is 6e3 to 4e6 times `|gap|` on the first cycle
of `double-threshold`.

**`(Q − Q_∞)/(Q_0 − Q_∞)` is not usable here.** `Q_∞` is from 20 CG iterations,
stopped at relative residuals 6e-3 to 9e-2, so it is a loose upper bound. On
crowded natural-weight skies the fraction is *negative* (−2e-3 to −1e-2): CLEAN
went below the bound. It is archived, and nothing is concluded from it.

### 6.5 The proposals, one by one

- **(A) Exact-Gram minor cycles.** Already available on the LUNO branch as a beam
  choice; new here is the schedule. Without w, exact: one pass. With w, two to four.
  This is the main result.
- **(B) FFT-batched subtraction.** Exact against direct subtraction to 1e-12. The
  driver's pass counts stay within one of direct subtraction, with 4-19 batches per
  run at 512² (1,314-16,009 components). Its cost is §6.6.
- **(C) Optimisation phase.** Lowers `Q` on the same support, as proved. Passes
  go *up*, 6-10 against 3-4: after the main cycles it spends extra cycles of 1-116
  components near the threshold. A refit changes the residual off the support, and
  mgain sets each cycle's target from its first peak; this mechanism is proposed,
  not isolated. Components fall by a third, the flux error is smallest (median
  −0.3 %, range −6 to +3.2 %) and rms is lowest; whether that is better recovery or
  fitting noise was not measured. CG hit its limit of 50 in the larger cycles
  (supports to 575), so those are not exact fits.
- **(iii) Provable rules.** Sound (0 violations, 0 ascending cycles) and not
  competitive with this bound on this PSF, as §1 says. They would matter where the
  gap is large (the LUNO divergence); a tight certified w bound is what is missing.
  A second-order expansion was worked through on paper and rejected: its remainder
  is of order `(2π w δ)²/2`, about 0.2 for the long-w baselines, again ignoring the
  cancellation that makes the true deviation small.

### 6.6 Timing: PROVISIONAL (contended host)

**Every wall time in this note and its archive is provisional.** The host is
shared and was heavily loaded: the coordinator reports a load average of 16.8 of
16 cores from WSL builds, WSClean and fits on the same hardware. A snapshot taken
after the run, at 11:37 on 2026-11-02, read Windows CPU load 88 % and WSL load
average 12.43, 10.73, 9.21; this is not the load during the runs. **Process CPU time
and load during the runs were not recorded** (Git Bash's `time` does not report the
Windows executable's CPU time). The thread comparison below comes from two
timing-mode runs made before that report of the load arrived; nothing was run after
it.

Repeat variation: 74 runs following an identical path in the final run and in the
smoke run differ by a median factor of 1.16 in wall time, 90th percentile 1.52, and
at most 2.55 (minor 1.59, major 2.80). The smoke run (512² only, the earlier scheme
set, a cap of 60, stopped by hand near the end) competed with a Lean build, so one
side of each pair was more contended. **Below a factor of about 3 no conclusion is
drawn.**

Sums over the 12 datasets at 512² (s):

| scheme | wall | minor + optimisation | major |
| --- | ---: | ---: | ---: |
| wsclean | 63.7 | 44.7 | 18.9 |
| image-provable | 103.2 | 14.7 | 88.3 |
| double-mgain | 58.8 | 43.5 | 15.2 |
| double-provable | 111.3 | 16.7 | 94.5 |
| double-cycle | 104.7 | 16.1 | 88.4 |
| double-cycle-measured | 58.7 | 45.8 | 12.9 |
| double-threshold | 60.5 | 49.9 | 10.6 |
| double-threshold-margin | 67.0 | 59.7 | 7.4 |
| fft-cycle-measured | 20.9 | 7.7 | 13.2 |
| fft-threshold-margin | 15.7 | 7.6 | 8.0 |
| opt-mgain | 48.4 | 19.9 | 28.4 |
| planar-threshold | 48.4 | 45.3 | 3.1 |

The major column follows the pass count, as it must. In these direct-subtraction
runs that reach the threshold the major work is a minority of the wall (11-30 %), so
on this one-channel, 244k-visibility case fewer passes alone do not transform the
run time; data with far more visibilities shifts that balance and was not measured.

FFT batches, thread comparison (crowded −30 natural; one repeat each, same load
caveat; under `thread_comparison` in the archive):

| threads | direct subtraction / argmax per component (ms), 512² | FFT pair, 512² (ms) | crossover K, 512² (with argmax) | FFT pair, 1024² (ms) | crossover K, 1024² (with argmax) | minor s: wsclean, double-threshold, fft-margin |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 0.415 / 0.247 | 52.5 | 126 (79) | 191 | 65 (51) | 10.0, 7.4, 2.9 |
| 16 | 0.484 / 0.210 | 36.3 | 75 (52) | 78.4 | 38 (27) | 8.9, 7.2, 0.9 |

**This comparison is not like for like at 16 threads:** direct subtraction and its
argmax are serial and the batched path is parallel. The only difference above the
repeat variation is the minor-cycle factor of about 8 at 16 threads, which measures
parallel code against serial code as much as the algorithm. At one thread the factor
is 2.6, inside the variation, on one repeat, with the batched run doing 8 % more
components. So: batches pay beyond some tens to about a hundred components per
batch, and a speed-up from FFT batching itself is **not established** by these runs.

The whole run took 1,314 s under this load, over the fifteen minutes asked for
(runs 1,117 s, CG 108 s, PSFs, probes and data the rest).

## 7. What this does and does not change

For CLEAN practice (proposed): compute the PSF on the `2n` grid, as is standard;
stop forcing a pass per factor of five in the peak when the beam is good, and run to
the threshold; expect one or two more passes for the w-term, and report the exact
peak after each. For rang: `run_cycles` is a research driver, nothing is wired into a
pipeline, and `clean_certified::run` is unchanged. Against AGENTS.md's novelty bar:
no higher imaging quality or lower cost at matched accuracy is demonstrated; the
contribution is the statement, the machine-checked proofs and the measured
attribution of the remaining passes to the w-term's ℓ∞ effect.

## 8. Reproduction

From the repository root (Rust 1.93):

```bash
cargo test --release --manifest-path core/Cargo.toml clean_major
```

```bash
cargo run --release --manifest-path core/Cargo.toml --example clean_major_cycles -- outputs/clean-major-cycles-20261102
```

```bash
CLEAN_MAJOR_TIMING=1 RAYON_NUM_THREADS=1 cargo run --release --manifest-path core/Cargo.toml --example clean_major_cycles -- outputs/clean-major-cycles-20261102
```

```bash
cd formal && lake build
```

The fields `timing_status`, `cpu_time_recorded`, `machine_load`,
`repeat_variation_wall_ratio`, `code_commit` and `thread_comparison` of the archive
were added to the run's JSON afterwards; the code at `de303bf` wrote the rest, and
the thread comparison came from the timing mode added in the next commit. Every seed
is fixed and counts agree across the runs compared.

## 9. Next steps

- Record process CPU time and load with every timing, and repeat the §6.6 comparison
  on an idle host with a parallel direct path, before any cost claim.
- Real MeerKAT data with many visibilities, where the major cycle costs more and
  direction-dependent effects enter the gap.
- Faceted PSFs (§4.3), which attack the w-term's deviation directly.
- A tight certified bound on the w deviation, exploiting cancellation over
  baselines; without one the provable rules are not competitive on this PSF.
- An ℓ∞ stopping analysis: predict the exact peak after a pass, so the margin is
  chosen rather than guessed.
- Compare models with the simulated truth, which this study did not do.
