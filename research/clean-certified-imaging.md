# Rang: certified CLEAN on real MeerKAT data, against WSClean 3.7

Research question 3 of the CLEAN programme ([clean-theory.md](clean-theory.md)
§6): run Högbom/Clark/Cotton-Schwab CLEAN instrumented with the four
diagnostics of the formalism on real MeerKAT data from this repository and
compare it with the WSClean oracle at matched settings. Branch
`clean-certified-imaging`, 2026-10-30. Status: **implemented; measured on
the LUNO 1934−638 four-station slice**. Every number below is labelled
implemented or measured; nothing here is a pipeline change and no imaging
improvement over WSClean is claimed beyond what §6 measures on this slice.
Archive: [results/clean-certified-imaging.json](results/clean-certified-imaging.json)
(per-cycle tables of every run, the gates, the WSClean log lines, timings).

## 1. Summary

- **Implemented.** `core/src/clean_certified.rs`: a Cotton-Schwab driver
  whose major cycles go through a measurement operator (direct sums, or the
  exact `wgridder` gridder/degridder pair) and whose minor cycles subtract
  any beam within any patch, with Clark's stop rule, the provable rule of
  Theorem 6 and WSClean's `-mgain` rule, Radler's divergence limit, and per
  major cycle the Gram-consistency gap, an audit of ascending minor steps
  and the greedy ratio; `Q_∞` by conjugate gradients on the normal operator;
  the ERC of the final component list by one Cholesky factorisation. Six
  unit tests; `rang.core_clean.certified_clean` exposes it in Python (§9).
  The example `core/examples/clean_certified.rs` runs it on the slice;
  three scripts export the data through the core, run WSClean and compare.
- **Measured, the reference.** WSClean 3.7 at the O-CASA reference setting
  (`-gridder wgridder`, default minimum-grid-resolution) images this field on
  a 32 × 32 Nyquist grid and upsamples: its dirty image differs from the
  exact transform by **17 % of the peak** (2.7 % in the inner half), its PSF
  peaks at 1.0016 off centre and is not centrosymmetric (0.25). With
  `-no-min-grid-resolution -wgridder-accuracy 1e-6` it matches the core's
  exact gridder to **2.6e-7** of the peak. O-CASA's `r1-*.fits`, which
  o-casa.md recommends to DF1/DF2 as the reference, is the first kind.
- **Measured, the matched comparison.** At gain 0.1, mgain 0.8, absolute
  threshold 50 mJy, WSClean diverges in all four variants (with or without
  the upsampling, with or without its sub-minor loop). The certified driver
  with WSClean's beam, an image-size PSF, **reproduces WSClean's run to
  5.4e-6 Jy** (same 39 model pixels, same 304 components, divergence in the
  third major cycle) and shows why: the Gram gap of that minor cycle is
  **99 times Q**, 158 of its 272 steps raise the true misfit, and 24 of the
  39 model pixels sit within 8 pixels of the image edge, where the
  image-size beam is truncated (`f = 0.771`: this PSF's sidelobes stay at
  0.77 to the edge). The same driver with the exact beam (a 1024² PSF)
  converges: 65 components in 4 major cycles, no ascending step, residual
  rms 22.1 mJy and peak 47 mJy, model flux 14.885 Jy against the 14.953 Jy
  of the calibrator model weighted over the band (−0.45 %).
- **Measured, the diagnostics on real data.** Gram gap ≤ 9e-12 of `Q` per
  cycle without the w-term (the operator is then exactly shift-invariant)
  and ≤ 1.4e-4 with it (the w-term makes the true Gram matrix depend on
  position); `Q_∞/Q_0` ≤ 3.69e-4, flat to 0.1 % per doubling of the CG
  budget beyond 200 iterations (§5.3);
  greedy ratio 1.00, 1.00, 0.91, 0.25 over the four cycles (removing one
  source, then the residual floor); ERC not certifiable: `B_SS` is singular
  to working precision for most component lists and `η` = 85 to 23,000
  where it factorises (adjacent-pixel coherence 0.99972).
- **Negative results.** The task's expected test "the gap is positive with a
  patch" is false: the gap is the quadratic form
  `Σ_{i<j} c_i c_j D(x_j − x_i)` in the components with the ignored beam `D`,
  and both signs occur (§2.2). The provable rule removes ascending steps by
  construction, but on this beam Clark's rule had none either (its cycles
  are 1-12 steps because `f` is 0.77-0.98), and the low-misfit models of
  the provable-rule runs put 0.6-2.5 Jy into negative pixels and 4.7-7.0 Jy
  outside the central 65 pixels (Theorem 5's non-uniqueness, §5.5).
  Descent is certified; the model is not.

## 2. Implementation (implemented; tested)

### 2.1 The driver

`core/src/clean_certified.rs` (registered in `core/src/lib.rs`):

- `Measurement` (trait): `residual(m) → (r, Q)` with
  `r = Aᴴ W (V − A m)` and `Q = ½ ‖V − A m‖²_W`, weights normalised to
  `Σ w = 1` (PSF peak one, `Q` in Jy²), and `gram_apply(x) = Aᴴ W A x`.
  `DftMeasurement` wraps `clean::{predict, dirty, misfit}`;
  `WgridMeasurement` wraps `wgridder::{dirty2vis, vis2dirty}` in double
  precision (`dirty2vis` without weights, `vis2dirty` with them), and builds
  the beam over every offset `±(n−1)` from a PSF on a `2n × 2n` grid
  (`psf()`), or the image-size beam a deconvolver computes
  (`psf_from_image`, zero beyond the image's half-width).
- `run(measurement, minor, exact, settings, q_floor)`: major cycles
  recompute the exact residual and `Q` from the model visibilities; minor
  cycles pick `argmax |r̃|`, add `γ r̃` and subtract the `minor` beam within
  `±patch`. Stop rules: `MinorRule::Clark` (`|r̃| < f · first peak`),
  `MinorRule::Provable` (continue while `f Σ_j |c_j| < (1 − γ/2) |r̃_p|`),
  `MinorRule::MajorGain(g)` (`|r̃| < (1 − g) · first peak`, WSClean's
  `-mgain`); every rule takes the first step of a cycle, which is exact.
  `divergence_limit` (default 4, Radler's `divergence_limit`) ends the
  minor cycle when `|r̃|` exceeds 4 times the first peak, and the run after
  that major cycle. Run stops: threshold on the exact peak, the misfit
  floor rule `(Q − Q_∞)/(Q_0 − Q_∞) < tol`, component and major-cycle
  budgets, divergence.
- `truncation_bound(exact, minor, patch)`: `f = max_Δ |b(Δ) − b̃(Δ)|`, the
  constant of Theorem 6 for any subtracted beam (`Psf::outside_patch` when
  `b̃` is the exact beam in a patch).
- Per major cycle (`MajorCycle`): components, exact peak, `Q` before and
  after, `ΔQ` exact and predicted, the gap and `gap/Q`, the audit (`ΔQ`
  summed from an exact-beam residual kept beside the working one, and the
  count of steps with positive true `ΔQ`), `Σ|c|`, the greedy ratio
  `κ = r_peak²/(2(Q − Q_∞))`, the reducible fraction, the stop reason and
  the time.
- `misfit_floor`: CG on `Aᴴ W A m = d` through the gridder
  (`clean::conjugate_gradients`, now shared with `least_squares_model`),
  and `Q` of the CG model from its visibilities, an upper bound on `Q_∞`.
- `erc_certificate(psf, support, max_k)`: distinct positions, `B_SS = L Lᵀ`
  once (`k³/3`), two triangular solves per pixel outside `S` in parallel
  (`k² N`); `None` when a pivot falls below 1e-13 (singular to working
  precision), with the smallest pivot reported. The existing `clean::erc`
  solves a dense system per pixel (`k³ N`).

### 2.2 The Gram gap in closed form (proposed; tested to 1e-10)

Let `D(Δ) = b(Δ) − b̃(Δ)` be the part of the Gram beam the minor cycle does
not subtract. The working residual before step `j` is
`r̃_j = r_j + Σ_{i<j} c_i D(x_j − x_i)` (all `r̃ = r` at the start of the
cycle), the true change of step `j` is `−c_j r_j + ½ c_j² b(0)` and the
predicted one `−c_j r̃_j + ½ c_j² b̃(0)`, so over the cycle

`gap = Σ_{i<j} c_i c_j D(x_j − x_i) + ½ Σ_j c_j² D(0)`,

exactly. With a patch `D(0) = 0` and `D` is the beam outside the patch, an
indefinite kernel: the gap has no fixed sign. The test
`gram_gap_is_nonzero_with_a_patch_and_equals_its_closed_form` checks the
identity to 1e-10 of `Q` over eight seeds and finds both signs (the task's
expectation "positive with a patch" is therefore not tested; it is false).
On the slice, where the components cluster on one source and the exterior
beam is mostly positive (up to 0.77), the gap is positive in every cycle of
the provable-rule runs; Clark's ±16 run has cycles down to −1.5e-4 of `Q`
(§5.5).

### 2.3 Unit tests (`cargo test --release --manifest-path core/Cargo.toml clean_certified`)

On 16 × 16 grids with 60-300 random weighted samples, three sources and
white noise: the gap is ≤ 1e-11 of `Q` in every cycle with the exact beam
and every cycle descends; the closed form above; **the provable rule
produces no ascending step over 24 seeds × patches ±1, ±2, ±4** (72 runs),
while long `mgain 0.99` cycles on the same patches do ascend (so the
property is not vacuous); the floor stopping rule stops with
`(Q − Q_∞)/(Q_0 − Q_∞) < 0.05` and never below `Q_∞`; `erc_certificate`
equals `clean::erc` to 1e-10; the `WgridMeasurement` normal operator on a
32 × 32 grid equals its own beam shifted to an asymmetric off-centre pixel
to 1e-9, and CLEAN on its visibilities has a rounding gap. 117 core tests
pass.

## 3. Data and settings (measured run 2026-10-30, WSL, 16 threads)

- **Measurement Set.** O-CASA run `-01`'s arm C (CASA-calibrated
  CORRECTED_DATA, field 1 = PKS 1934−638; [o-casa.md](o-casa.md)), copied to
  `outputs/clean-certified-20261030-02-wsclean/c.ms` (WSClean writes into
  the MS it cleans; O-CASA's copy is never touched). 192 rows, 2,048
  channels 1,070-1,497.8 MHz, four stations (29-74 m baselines).
- **rang's path** (`examples/clean_certified_export.py`): the core MS reader
  (`rang.core_ms`) reads UVW, CORRECTED_DATA, FLAG, FLAG_ROW,
  WEIGHT_SPECTRUM and the subtables; rows with field 1, cross-correlations,
  data description 0; `core_weights.stokes_i` (WSClean's `-pol I`); Briggs
  0.5 on the padded 616-pixel weight grid (`core_weights.imaging_weights`,
  WSClean's rule, as task I); gridding weight = Stokes I weight × imaging
  weight. **117,556 weighted visibilities and weight sum 669,036.3248, both
  equal to WSClean's header (`WSCNVIS`, `WSCIMGWG`).** Raw arrays in
  `outputs/clean-certified-20261030-03/inputs/` (SHA256 in the archive).
- **Image.** 512 × 512 pixels of 8″, exact gridder ε = 1e-9 (f64),
  w-gridding on, `flip_v`, `flip_w` (WSClean's FITS image is the gridder
  image with v and w flipped, transposed; DF1 item 0); the beam on a
  1024 × 1024 grid of the same cell.
- **CLEAN settings (chosen for this study; the repository records no WSClean
  CLEAN run, every archived one is `-niter 0`).** Gain 0.1, mgain 0.8,
  absolute threshold 0.05 Jy (about 1.7 × the 0.029 Jy point-source
  residual rms of O-CASA's reference), at most 100,000 components, no mask,
  divergence limit 4 (Radler's default). WSClean:
  `wsclean -gridder wgridder -data-column CORRECTED_DATA -field 1 -size 512 512 -scale 8asec -weight briggs 0.5 -pol I -j 1 -niter 100000 -gain 0.1 -mgain 0.8 -nmiter 0 -abs-threshold 0.05 -no-update-model-required`
  in `rang-o-casa:6.7.6.14` (WSClean 3.7), plus
  `-no-min-grid-resolution -wgridder-accuracy 1e-6` ("nominres") and/or
  `-no-fast-subminor` ("hogbom") (`examples/clean_certified_wsclean.sh`).
- **rang configurations** (`core/examples/clean_certified.rs`), all gain 0.1,
  threshold 0.05 Jy, audit on: `exact-mgain` (exact beam, mgain 0.8: the
  matched run), `now-exact-mgain` (the same without w-gridding),
  `image-mgain` (the 512² PSF image as beam, WSClean's subtraction),
  `wsclean-{recorded,nominres}-mgain` (WSClean's own PSF FITS as beam, the
  exact operator for the major cycles), `patch{16,64}-{clark,provable}`
  (exact beam within ±16 or ±64 pixels), `exact-mgain-floor` (threshold
  off, stop at `(Q − Q_∞)/(Q_0 − Q_∞) < 1e-3`).
- **Expected flux.** CASA's setjy model of 1934−638 (Perley-Butler 2010,
  `outputs/o-casa-20261030-01/fs-pb2010-stokes-i.npy`) averaged over the
  channels with the gridding weights: **14.9532 Jy**.

## 4. The reference images (measured)

The core's exact dirty image and PSF against WSClean 3.7 `-niter 0`
(`examples/clean_certified_export.py --reference`):

| WSClean variant | dirty L∞ / peak | inner half | PSF L∞ | WSClean PSF max (pixel) |
| --- | ---: | ---: | ---: | --- |
| O-CASA `r1` = `d-recorded` (default minimum grid resolution) | 0.171 | 0.027 | 0.172 | 1.0016 at (254, 259) |
| `d-nominres` (`-no-min-grid-resolution`) | 4.4e-5 | 1.6e-5 | 4.4e-5 | 1.0 at the centre |
| `d-nominres-acc6` (and `-wgridder-accuracy 1e-6`) | **2.6e-7** | 2.6e-7 | 2.7e-7 | 1.0 at the centre |

`d-recorded` reproduces O-CASA's `r1-dirty.fits` pixel for pixel. WSClean's
log says why it differs: "Minimal inversion size: 18 x 18, using optimal:
32 x 32": with 360 λ baselines and 8″ pixels the image has about 71 pixels
per theoretical beam (9.54′) and is about 36 times finer than Nyquist
sampling (about 286″), so WSClean grids at the small size and upsamples; its help text
expects aliasing "in most cases <1%". Here it is 17 %, and the upsampled PSF
is not a Gram matrix (a Gram matrix has `|b| ≤ b(0)` and is
centrosymmetric). For DF1/DF2 this means the O-CASA reference should be
regenerated with `-no-min-grid-resolution` before WSClean wgridder pixels
are used as a tolerance oracle.

## 5. Results (measured)

### 5.1 All runs

`Q/Q0` from the exact operator (the same for every model, rang's and
WSClean's, through `examples/clean_certified_compare.py`); residual rms and
peak of the exact residual image (rang) or WSClean's residual FITS; flux in
Jy.

| run | components | major cycles | stop | Q/Q0 | residual rms | residual peak | model flux | central 65 px | negative flux | max \|gap\|/Q | ascending steps |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rang `exact-mgain` | 65 | 4 | threshold | 4.66e-4 | 0.0221 | 0.0472 | 14.885 | 14.897 | −0.040 | 1.4e-4 | 0 |
| rang `now-exact-mgain` | 65 | 4 | threshold | 4.66e-4 | 0.0220 | 0.0474 | 14.887 | 14.897 | −0.040 | 9.1e-12 | 0 |
| rang `image-mgain` | 304 | 3 | diverged | 2.53e-2 | 0.559 | 1.554 | 14.764 | 14.955 | −7.95 | 99 | 158 |
| rang `wsclean-nominres-mgain` | 304 | 3 | diverged | 2.53e-2 | 0.559 | 1.554 | 14.764 | 14.955 | −7.95 | 99 | 158 |
| rang `wsclean-recorded-mgain` | 290 | 1 | diverged | 11.0 | 12.85 | 40.25 | 29.87 | 74.21 | −245.9 | 142 | 148 |
| rang `patch16-clark` | 69 | 48 | threshold | 4.59e-4 | 0.0223 | 0.0492 | 14.965 | 14.963 | −0.062 | 1.9e-2 | 0 |
| rang `patch16-provable` | 75 | 8 | threshold | 4.39e-4 | 0.0186 | 0.0484 | 15.051 | 10.386 | −0.59 | 0.51 | 0 |
| rang `patch64-clark` | 67 | 18 | threshold | 4.59e-4 | 0.0205 | 0.0488 | 14.850 | 14.891 | −0.069 | 2.1e-2 | 0 |
| rang `patch64-provable` | 316 | 29 | threshold | 7.90e-4 | 0.0215 | 0.0474 | 16.155 | 9.194 | −2.48 | 0.32 | 0 |
| rang `exact-mgain-floor` | 48 | 3 | floor | 5.31e-4 | 0.0358 | 0.0952 | 14.855 | 14.855 | 0 | 6.1e-9 | 0 |
| WSClean `c-nominres-fast` | 304 | 3 | diverged | 2.53e-2 | 0.559 | 1.554 | 14.764 | 14.955 | −7.95 | – | – |
| WSClean `c-nominres-hogbom` | ≥ 300 (logged) | 3 | diverged | 2.53e-2 | 0.559 | 1.554 | 14.764 | 14.955 | −7.95 | – | – |
| WSClean `c-recorded-fast` | 263 | 1 | diverged | 21.7 | 19.75 | 74.85 | −38.57 | 11.35 | −260.4 | – | – |
| WSClean `c-recorded-hogbom` | ≥ 200 (logged) | 1 | diverged | 21.7 | 19.75 | 74.85 | −38.57 | 11.35 | −260.4 | – | – |

Matched pairs (model and residual L∞ in Jy):

| rang | WSClean | model L∞ | residual L∞ | same support |
| --- | --- | ---: | ---: | --- |
| `image-mgain` | `c-nominres-hogbom` | 5.4e-6 | 4.6e-6 | yes (39 pixels) |
| `wsclean-nominres-mgain` | `c-nominres-hogbom` | 5.8e-6 | 4.7e-6 | yes |
| `exact-mgain` | `c-nominres-hogbom` | 2.25 | 1.58 | no (WSClean diverged) |
| `wsclean-recorded-mgain` | `c-recorded-hogbom` | 74.0 | 102 | **not a matched pair**: WSClean's major cycles also use the upsampled operator, rang's the exact one |

The 5e-6 Jy agreement is float32 rounding in WSClean: the certified driver
with an image-size beam is WSClean's Högbom minor loop, and with the exact
beam it is the same loop made Gram-consistent. WSClean's fast sub-minor
loop and its plain loop give the same model here, so the divergence is not
a sub-minor artefact.

### 5.2 Why WSClean diverges (the diagnostics)

Per major cycle of the matched pair (`exact-mgain` against `image-mgain`;
both identical for the first two cycles):

| cycle | first peak (Jy) | Q before (Jy²) | exact: comps, ΔQ, gap/Q | image beam: comps, ΔQ, gap/Q, ascending |
| ---: | ---: | ---: | --- | --- |
| 0 | 14.950 | 111.80 | 16, −107.91, −3.5e-10 | 16, −107.91, −2.1e-10, 0 |
| 1 | 2.770 | 3.892 | 16, −3.705, −2.6e-10 | 16, −3.705, −1.2e-10, 0 |
| 2 | 0.513 | 0.1866 | 16, −0.1273, 6.1e-9 | **272, +2.636, 99.1, 158** |
| 3 | 0.095 | 0.0593 | 17, −0.00728, 1.4e-4 | – (stopped: diverged) |

In cycle 2 the image-beam minor loop believes it removed 15.9 Jy² of misfit
while the true misfit rose by 2.6 Jy² (14 times its value at the start of
the cycle). WSClean's log shows the same path: at iteration 60 the peak
jumps from the source (255, 257) to the image edge (511, 324) and the loop
then alternates between the edge and the source until the peak passes 4 ×
0.513 Jy. A component at the edge subtracts only the half of the beam that
the 512² PSF image holds, and on this beam the missing half is 0.77 of the
peak; the working residual there is not the true residual, the pick follows
the error, and the model ends with 22.7 Jy positive and 7.95 Jy negative
flux, 24 of its 39 pixels at the edge. With WSClean's upsampled PSF the
first minor cycle already diverges (gap 142 Q, 148 ascending steps, 290
components). With the exact beam, `f = 0` and the gap is the w-term's
position dependence only: 9e-12 of `Q` without w-gridding, 1.4e-4 with it
(the beam is computed at the phase centre; the largest difference between
the w-gridded and the planar beam over the 1024² grid is 0.141).

### 5.3 The misfit floor

`Q_∞` by CG on the w-gridded normal operator (`CLEAN_CERTIFIED_CG_SWEEP`,
run `outputs/clean-certified-20261030-04-cg-sweep`):

| CG iterations | Q_CG / Q0 (upper bound on Q_∞/Q0) | relative residual | CG model flux (Jy) | negative flux (Jy) | wall |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 3.9264e-4 | 3.2e-4 | −6.3 | −31.0 | 10.9 s |
| 100 | 3.7444e-4 | 5.7e-5 | −5.5 | −31.0 | 23.3 s |
| 200 | 3.7068e-4 | 1.8e-5 | −3.4 | −30.5 | 50.9 s |
| 400 | 3.6994e-4 | 1.3e-6 | +0.4 | −30.4 | 100.6 s |
| 800 | 3.6967e-4 | 7.4e-6 | +12.4 | −37.4 | 271.7 s |
| 1600 | 3.6939e-4 | 4.2e-6 | +29.2 | −90.0 | 512.3 s |

The floor reachable by CG flattens (−0.2 %, −0.07 %, −0.08 % per doubling
after 200 iterations) near 3.69e-4 of `Q_0`, although `N = 262,144` pixels
exceed `2M = 235,112` real data. That does not show the exact floor is
nonzero: a normal-equations residual of 4e-6 can hide misfit along
near-null directions (CG's residual norm rises again after 400 iterations;
CG was not restarted), and CLEAN cannot reach those directions either. A
nonzero reachable floor is expected (proposed, not measured): the 68′ field
cannot fit uv structure finer than about 50 λ, while 2,048 channels sample
each track at sub-λ spacing. The CG models are unphysical
and keep moving while `Q` does not: net flux from −6 to +29 Jy with −30 to
−90 Jy in negative pixels, the near-null space of Theorem 5. The quantities
built on `Q_∞` change by about 1 % between the 200- and 1600-iteration
bounds; with the 200-iteration bound used in the runs, `(Q − Q_∞)/(Q_0 − Q_∞)`
falls to 1.6e-4 at the start of `exact-mgain`'s last cycle and its final
value 9.5e-5; the floor rule at 1e-3 stopped after three cycles at Q/Q0
5.3e-4 with residual peak 95 mJy (above the 50 mJy threshold). The greedy
ratio `κ` is 0.9999, 0.997, 0.908 and 0.253 at the four cycle starts of
`exact-mgain`: the first three cycles remove a single source (`κ ≈ 1/k`,
`k = 1`), the last one the floor, as clean-theory's Theorem 3 reading
predicts. Q_∞ took 45 s (200 iterations, 0.23 s each), 45 times the CLEAN
run it diagnoses.

### 5.4 The ERC

| run | distinct positions k | η(S) | smallest Cholesky pivot |
| --- | ---: | ---: | ---: |
| `now-exact-mgain` | 16 | 23,186 | 3.4e-8 |
| `patch64-clark` | 16 | 1,664 | 4.1e-6 |
| `exact-mgain-floor` | 3 | 85.4 | 5.6e-4 |
| `exact-mgain`, `patch16-*`, `patch64-provable`, the diverged runs | 17-156 | not certifiable | −3e-7 to −4e-4 |

The ERC never certifies a component list on this beam. The nearest-neighbour
coherence is 0.99972 (the main lobe is 60′ × 4.4′, 450 × 33 pixels), so any
two components within the main lobe make `B_SS` nearly singular; with the
w-gridded beam it is slightly indefinite (negative pivots), because the
phase-centre PSF is not the Gram matrix of off-centre pairs. Each ERC took
under 0.01 s (k ≤ 156; `k² N` ≤ 6.4e9 multiply-adds). As clean-theory E2
and E2c found, the ERC is a sufficient condition for well-separated point
sources; for a resolved-out main lobe on four stations it says nothing.

### 5.5 Clark against the provable rule

On the exact beam within ±16 (`f = 0.982`) and ±64 (`f = 0.771`) pixels:

| patch, rule | major cycles | components per cycle | max gap/Q | gap sign | ascending | Q/Q0 | central flux | negative |
| --- | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: |
| ±16 Clark | 48 | 1-5 | 0.019 | both (−1.5e-4 … 0.019) | 0 | 4.59e-4 | 14.963 | −0.062 |
| ±16 provable | 8 | 9-10 | 0.51 | positive | 0 | 4.39e-4 | 10.386 | −0.59 |
| ±64 Clark | 18 | 3-12 | 0.021 | ≥ 0 (to rounding) | 0 | 4.59e-4 | 14.891 | −0.069 |
| ±64 provable | 29 | 2-12 | 0.32 | positive | 0 | 7.90e-4 | 9.194 | −2.48 |

Both rules reach the threshold without an ascending step. Clark's rule is
safe here only because `f` is close to one and ends its cycles after a few
steps (48 major cycles for 69 components on ±16); the provable rule allows
9-12 steps per cycle and lets the gap reach a third to a half of `Q` while
every step still descends, exactly what Theorem 6 promises and no more. The
models differ: the provable runs spread 5-7 Jy along the main-lobe ridge
outside the central 65 pixels, with negative pixels, at equal or lower
misfit. On a beam this coherent, many models fit equally well (Theorem 5),
and which one CLEAN reaches depends on the path; descent does not choose
between them.

## 6. Comparison with WSClean, honestly

1. **Correctness.** rang's MS reader, Stokes I, Briggs weights and exact
   gridder reproduce WSClean's visibility count and weight sum exactly and
   its dirty image and PSF to 2.6e-7 once WSClean's upsampling is off. The
   certified driver with WSClean's beam reproduces WSClean's CLEAN to 5e-6
   Jy, components and divergence included.
2. **Matched outcome.** At identical settings WSClean diverges in every
   variant and the exact-beam driver converges to the threshold with no
   ascending step: 65 components, residual rms 22 mJy, peak 47 mJy, model
   flux 14.885 Jy (−0.45 % against the band-averaged calibrator model);
   WSClean stops with residual rms 0.56 Jy, peak 1.55 Jy and 7.95 Jy of
   negative flux (nominres) or 19.7 Jy rms (recorded).
3. **What this does and does not show.** The failure is the image-size
   beam on a PSF whose sidelobes stay at 0.77 to the image edge: the worst
   case for that truncation, typical of four-station data and not of the
   64-dish array. A PSF twice the image size is not a new remedy (imaging a
   padded field and cleaning its centre is standard practice; it was not
   tried in WSClean here). What is new is that the diagnostics name the
   failure in numbers while it
   happens: a gap of 99 Q in one major cycle and 158 ascending steps are
   not visible in any WSClean output, which only reports the 4× peak rise.
   No imaging-quality improvement for MeerKAT at large is claimed.
4. **Cost.** WSClean: 1.1-2.6 s per job including container start (its own
   timer: inversion 0.9-1.2 s, prediction 0.07-0.5 s, deconvolution
   0.05-0.08 s). rang: 0.11 s per exact residual evaluation (degrid +
   grid, 16 threads, ε 1e-9), 0.23-0.28 s per normal-operator application,
   0.20-0.25 s for both 1024² beams, 1.0 s for `exact-mgain` with its audit;
   `Q_∞` 45 s. The slice is too small for a performance statement.

## 7. Timings

All on the WSL host, 16 threads, logged in [tool-timings.md](tool-timings.md):
uv venv + editable install 96.6 s; export 40.6 s first (standalone wgridder
library build) and 0.8 s after; WSClean exploration jobs 7.4 s (5 jobs),
final jobs 12.8 s (7 jobs, 1.1-2.6 s each); first core test build and the
new tests 70 s; full `cargo test` 67 s (117 tests); smoke run of the example
with 5 major cycles and no divergence limit 154 s (the image-beam run spent
105 s on 100,000 components before the limit existed); final example run
74.9 s (CG 45.4 s); comparison 3.5 s; CG sweep 970.5 s (3,150 iterations,
0.22-0.34 s each).

## 8. Reproduction

```bash
export PATH=$HOME/.cargo/bin:$PATH
bash examples/clean_certified_wsclean.sh outputs/clean-certified-20261030-02-wsclean
W=outputs/clean-certified-20261030-02-wsclean
.venv/bin/python examples/clean_certified_export.py $W/c.ms outputs/clean-certified-20261030-03/inputs \
  --reference r1=/home/gijsm/Github/rang/outputs/o-casa-20261030-03-wsclean-j1/r1 \
  --reference recorded=$W/d-recorded --reference nominres=$W/d-nominres \
  --reference nominres-acc6=$W/d-nominres-acc6 \
  --wsclean-psf recorded=$W/d-recorded-psf.fits --wsclean-psf nominres=$W/d-nominres-acc6-psf.fits
cargo run --release --manifest-path core/Cargo.toml --example clean_certified -- \
  outputs/clean-certified-20261030-03/inputs outputs/clean-certified-20261030-03/run 0.05
CLEAN_CERTIFIED_CG_SWEEP=50,100,200,400,800,1600 cargo run --release --manifest-path core/Cargo.toml \
  --example clean_certified -- outputs/clean-certified-20261030-03/inputs outputs/clean-certified-20261030-04-cg-sweep
.venv/bin/python examples/clean_certified_compare.py outputs/clean-certified-20261030-03/inputs \
  outputs/clean-certified-20261030-03/run $W outputs/clean-certified-20261030-03/compare.json \
  --flux-model /home/gijsm/Github/rang/outputs/o-casa-20261030-01/fs-pb2010-stokes-i.npy
.venv/bin/python examples/archive_clean_certified.py outputs/clean-certified-20261030-03/inputs \
  outputs/clean-certified-20261030-03/run outputs/clean-certified-20261030-03/compare.json \
  outputs/clean-certified-20261030-04-cg-sweep/cg-sweep.json $W research/results/clean-certified-imaging.json
```

The `r1` reference is O-CASA's. Runs are deterministic except WSClean's
float pixels (bit-identical at `-j 1` in O-CASA's test). Provenance: the
WSClean jobs, the export and the `-03` run (`run/`, `compare.json`) were
produced by the code committed as `df32491`; the CG sweep, the comparison
with `--flux-model` and the archive by `86fbe2b` (the archive's
`code_commit`); the Python cross-check by `8adebce`
(`examples/clean_certified_binding_check.py`).

## 9. Python interface (implemented; tested)

`rang.core_clean.certified_clean(uvw, freq, vis, weights, *, side, scale_arcsec,
epsilon, wgridding, flip_v, flip_w, gain, threshold, max_components,
max_major, max_minor, rule, mgain, patch, beam, floor_iterations,
floor_tolerance, divergence_limit, audit, erc_max_k)` calls
`rang._core.clean_certified` (`core/py/src/clean.rs`, PyO3, GIL released),
which runs `clean_certified::run` on a `WgridMeasurement` and returns the
model, the exact residual (gridder layout; `.T` is WSClean's FITS order with
the default flips), a summary (`Q_0`, `Q`, components, cycles, stop, `f`,
ascending steps, ERC, `Q_∞`) and one dict per major cycle.
`tests/test_core_clean.py` (3 tests, 1.2 s): Gram gap below 1e-8 of `Q` and
monotone descent with the exact beam, no ascending step under the provable
rule with a ±2 patch, refused inputs. On the slice the binding reproduces
the example's `exact-mgain` and `image-mgain` models and residuals bit for
bit (`examples/clean_certified_binding_check.py INPUTS RUN`, output
`outputs/clean-certified-20261030-05-binding-check.json`; 1.5 s and 2.2 s
from Python, including the 1024² beam).

## 10. Open items

- A position-dependent (w-term) Gram beam, or faceted beams, would remove
  the 1.4e-4 gap; not needed at this field size.
- The O-CASA WSClean reference (`r1`) should be regenerated with
  `-no-min-grid-resolution` before DF2b uses WSClean wgridder pixels as an
  oracle (§4).
- A full-array MeerKAT measurement set (64 dishes, the B1/L1 data) is the
  next test: there the sidelobes fall to a few per cent and the image-size
  truncation should matter far less; the diagnostics would then measure
  what Clark patches cost on real survey PSFs.
- Formalise the closed form of §2.2 with Theorem 6 in Lean (finite algebra).
