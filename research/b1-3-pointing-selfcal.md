# Rang B1-3: pointing self-calibration and the rang method at matched cost (protocol)

Protocol frozen 2026-10-30 on branch `b1-3-pointing-selfcal` (from main
`65f2b87`), before any B1-3 code was written. Task B1-3 of
[big-plan.md](big-plan.md) wave 3. It answers question Q3 of
[b1-beam-pointing.md](b1-beam-pointing.md): at matched cost, does rang's
distinguishability-selected correction beat both baselines on B1's frozen
metrics? It builds on the B1-0 beam product, the B1-1 (i) port and the B1-2
verdict ([b1-2-identifiability.md](b1-2-identifiability.md)).

Status: **proposed** (this section). Results are appended below the
protocol when measured; nothing above "Measured result" changes after this
commit except through a dated, labelled amendment.

## What is frozen elsewhere and kept

- **Beam.** The B1-0 product (`outputs/b1-20261030-05-holography`, CC BY-NC
  4.0, de Villiers 2023, DOI 10.48479/wdb0-h061): array average at 1,024
  native channels, all 64 antennas at the 95 product channels; cubic spline
  in space with the analytic derivatives of B1-2, linear in frequency;
  Stokes I power 1 at the origin per frequency; s = +1.
- **Frames.** B1-2's: x = −l cos q + m sin q, y = l sin q + m cos q, q the
  geodetic parallactic angle (astropy reference, `measures.py`); X = H,
  Y = V; parallel hands only; per hand the beam product
  B_pq,h = Σ_m E_p[h, m] conj(E_q[h, m]); RECEPTOR_ANGLE recorded, not
  applied.
- **Directions and units.** B1-2's table: per-antenna pointing δ_p (1′),
  array-common pointing c (1′), log-width w and ellipticity e (1 %), squint
  s (1′; H row at u − s/2, V row at u + s/2).
- **Decision rule for identifiability** (B1-2): constrainable if the
  conditional σ ≤ 0.3′ (pointing, squint) or ≤ 0.005 (width, ellipticity)
  and ρ ≥ 0.01, on the primary sky arm (ln S₀ and α per component) with the
  noise calibrated from adjacent-channel differences. "Needs a spectral
  prior" and "constrainable alone only" labels as B1-2. B1-2 also requires
  that "B1-3 must use family-marginal numbers for any joint fit".
- **Metrics for Q3** (B1, frozen): (1) recovered offset bias and RMS error
  in arcmin on simulations; (2) held-out visibility error with L1's seed-7
  split (80/10/10, groups gain bin × baseline, two training cells reserved
  per group), against gains-only; (3) faint-source flux and spectral-index
  distortion on a simulated field (20 sources at 0.1–1 mJy between the
  half-power and first-null radii and 20 inside the core; pointing errors σ
  = 0.6′ per antenna per hour); (4) cost: wall, peak RSS and data volume,
  same host and threads, "matched" = within a factor 1.5 in wall for the
  same data.
- **B1's win rule:** "Rang wins only if it improves 2 or 3 over both
  baselines with 1 no worse, at matched cost; otherwise the result is
  recorded as null." Kept as the overall rule (below, with the
  applicability of each baseline made explicit; that is not a change of
  margins, which B1 did not fix).

## Pre-protocol probes (labelled scratch)

Metadata only; no survey quantity, fit or image was computed.

| Run | Dir under `outputs/` | What | Wall | Peak RSS |
| --- | --- | --- | ---: | ---: |
| uv venv + install (builds the extension) | – | `.[pointing,beam,test,imaging]` ruff maturin pip | 77.6 s | 1.19 GB |
| LUNO and ESO137 antenna tables | (stdout) | LUNO `ANTENNA/NAME` (json2, 56 names) and POSITION; ESO137 pilot POSITION (61) | ~2 s | – |
| ESO137 antenna names | `b1-3-20261030-00-probe-names` | `ms1_target_subset.zarr` `ANTENNA/ANTENNA_0/NAME` `.zarray` and chunk `0` (one HTTP GET each); string constants read by **opcode scan** (`pickletools.genops`), nothing unpickled | 0.41 s | 43 MB |

Facts found:

1. The ESO137 subset's ANTENNA/NAME is a pickle-filtered object array
   (protocol 5). Its opcode stream holds 61 names: m000–m013, m015, m016,
   m018–m031, m033–m063 (absent: m014, m017, m032). No pickle is executed:
   `pickletools.genops` only parses opcodes.
2. **Cross-check (authoritative):** 54 of the 61 ESO137 antennas coincide
   with a LUNO antenna to 0.0 m in ITRF POSITION, and every one of them
   carries the same name in LUNO's json2 table. The 7 others (m006, m008,
   m015, m016, m028, m034, m060) are absent from LUNO's 56 and sit between
   their neighbours in sort order, as the opcode names say. The data-index
   → holography-antenna map is therefore known for every antenna of every
   set: LUNO by its json2 names, ESO137 by the opcode names, the fixture
   (m000–m003) as B1-1.
3. The holography product holds all 64 antennas m000–m063, so every data
   antenna has its own beam.

The probe scripts are kept in `/home/gijsm/Build/tmp/20261030-b1-3/` until
the end of the task and copied into the probe directory.

## Part 1: the survey rerun (frozen)

B1-2's report asks for it before anything is fitted: its snapshot
array-common pointing came from the beam's chromaticity inside a 32-channel
gain interval (post hoc 1), and the per-antenna beams were not used.

**What changes, and only this:**

1. **Gain nuisance:** diagonal complex gains per antenna × hand × **channel**
   × 2-dump interval (the K/L1/L2 time grid, one channel wide). In the
   linearisation this span contains the span of any bandpass × gain model
   on the same grid (a per-channel bandpass times a per-interval gain is a
   special case), so a direction that survives it survives every gentler
   gain model; one that fails it may still pass under a smoother one, which
   is reported (B1-2's numbers) but not fitted.
2. **Per-antenna beams.** Each data antenna uses its own holography beam
   (names above), by one frozen interpolation rule: **the native array
   average plus the antenna's difference from it, the difference linear in
   frequency between the bracketing product channels**:
   E_p(ν) = E_avg(ν) + (1 − t) [E_p(ν_k) − E_avg(ν_k)] + t [E_p(ν_k+1) −
   E_avg(ν_k+1)], with ν_k, ν_k+1 the product channels around ν. At a
   product channel it is the antenna's own map exactly (a test checks the
   identity); between them it keeps the native chromaticity of the average,
   which B1-2 found real at 6.7 MHz. Spline and gradients as B1-2 (the
   prefilter is linear, so the difference's coefficients are the difference
   of coefficients). Each antenna is normalised so its own Stokes I power is
   1 at its origin at every frequency (the B1-0 rule).
3. **Beam evaluation** at the centre of each 16-channel sub-block (B1-2's
   verdict evaluation, "sub16"), for every channel bin inside it.
   *Convergence check (frozen):* on S1 the beam is also evaluated at
   8-channel sub-blocks; if any common direction's conditional σ, or the
   median per-antenna σ, changes by more than 5 %, the 8-channel evaluation
   is used for every set and the change is recorded.

Everything else is B1-2's: the five sets S1–S5 and their rows, channels and
models (CARACal lsm for S1/S2, the scalar point for S3, the B1-2 field model
for S4/S5); apparent fluxes with the beam entering through the
log-derivative factors (now per baseline: ∂B_pq/B_pq with each antenna's
beam, exact for the cross-polar terms); the noise calibration; the primary
and strict sky arms (strict: a free flux per component per 32-channel
block); the conditional σ, ρ, family-marginal σ (per-antenna family in the
zero-mean parametrisation over antennas with data); the I_b < 0.01 floor;
the frozen decision rule. The anchored response and the S1 native call are
**not** repeated (they do not enter the rule; B1-2 validated them).

**Variants reported in each rerun** (one pass, shared sky and gains):
`antenna` (per-antenna beams, sub16): **the verdict**; `average` (the
array-average beam, sub16): labelled, it separates the effect of the
bandpass from that of the per-antenna beams; on S1 also `antenna8` (the
convergence check) and on S3 `copolar` (below).

**Added derived directions** (no new data columns): on S5 the per-scan
array-common pointing (δ_p = c_s for every antenna of scan s), whose
information is 1ᵀF_ss1 of the per-antenna block of that scan; reported per
scan with the same rule. (B1-2's track-constant common pointing is kept.)

**Implementation gate G3a (frozen).** A single component is absorbed
exactly by per-channel gains when the beam is diagonal (each factor
separates into antenna terms; B1-2 post hoc 1). On S3 the variant
`copolar` (the per-antenna beams with HV and VH set to zero) must give **ρ ≤
1e-6 for every direction**. If it does not, the implementation is wrong and
nothing is fitted until it passes. The full-Jones ρ on S3 is reported; it
may exceed 1e-6 only through the cross-polar terms (B_pq is then a sum of
two separable terms), expected ≲ 1e-3.

**Cost plan.** S3 and S1 run first and are timed; the S2/S4/S5 cost is
extrapolated from them before they start. The work is split over time bins
in four single-threaded processes (`OPENBLAS_NUM_THREADS=1`; within the
4-thread budget). If the extrapolated S2 rerun exceeds 3 h, the per-bin
kernel is ported to Rust before S2 runs.

**Output of Part 1:** per set the verdict table as B1-2. **Only directions
that pass the rerun on a set are candidates for the rang method on that
set** (and on the simulations built from it, below). Width is excluded
everywhere, whatever the rerun says (the brief and B1-2).

## Part 2: the methods (frozen)

All arms run in **one solver** (`python/rang/pointing_selfcal.py`); they
differ only in which beam parameters are free. Same data, gain nuisance,
sky treatment, priors, iteration rule, host and threads.

### The model

V_pq,h(ν, t) = g_p,h(ν, t) conj(g_q,h(ν, t)) Σ_k S_k(ν) K_pq,k(ν, t)
B_pq,h,k(θ; ν, q(t)),

- K: the core predictor's per-component phase term (and Gaussian envelope)
  with its sign, as B1-2's `phase_terms`;
- **intrinsic** fluxes: S_k(ν) = S_base,k(ν) exp(a_k + b_k ln(ν/ν₀)), with
  S_base the model's apparent spectrum divided by the array-average I_b at
  the component (mean q of the set), ν₀ the set's mean frequency, and the
  free parameters (a_k, b_k) = (Δ ln S₀, Δα) (B1-2's primary sky arm).
  Components with I_b < 0.01 keep the apparent flux and no beam (B1-2's
  floor);
- B_pq,h,k = Σ_m E_p[h, m](T_p,h(u_k)) conj(E_q[h, m](T_q,h(u_k))) with each
  antenna's beam, u_k the component's antenna-frame position at the gain
  bin's q, and the perturbed coordinates T_p,h(u) = D(e) (u − δ_p − σ_h s/2),
  D(e) = diag(e^−e, e^+e), σ_H = +1, σ_V = −1 (B1-2's parametrisations
  composed); width only in the survey;
- gains: diagonal, per antenna × hand × channel × 2-dump interval (the
  Part 1 nuisance).

Analytic Jacobian: ∂T/∂δ = −D, ∂T/∂s = −σ_h D/2, ∂T/∂e = diag(−1, +1) T,
times the spline gradients; array-common pointing is the sum of the
per-antenna columns of an interval. Units: arcmin for δ and s, unit for e.

### The solver: profiled Levenberg–Marquardt (frozen)

Each pass, over the **training cells** only:

1. per gain bin, the gains are re-solved exactly for the current sky and
   beam (StefCal form as B1-2's `stefcal`: amplitude and phase, 100
   iterations, averaging 0.5, relative change 1e-8; warm start from the
   previous pass);
2. the normal equations of [gains | (a, b) | free beam parameters] are
   formed at those gains in the whitened metric (weights w / s_h², s_h² the
   adjacent-channel noise scale of the set, scan and hand), the gains are
   Schur-eliminated per bin (pseudo-inverse after equilibration, cutoff
   1e-10, as B1-2), and the reduced system is summed;
3. the step solves (H + λ diag H + P) Δ = b − Pθ, P the prior below.

Settings: λ₀ = 1e-3, ÷10 after an accepted step, ×10 after a rejected one
(the pass at the trial point is then discarded and counted); stop when an
accepted step lowers the objective by a relative 1e-7 or less, or after
**10 passes**, or at λ > 1e8. The objective is the training χ² plus the
prior term.

- **Sky gauge:** per-channel gains make the global flux scale and global
  spectral index degenerate with the sky; the brightest component's (a, b)
  are held at zero in every arm.
- **Prior (both pointing arms, identical):** independent zero-mean Gaussians
  on the free beam parameters: 3′ on every pointing and squint coordinate
  (the default `offset_prior_arcmin` of the existing `solve_pointing`), 0.05
  on ellipticity. No common-pointing prior from
  [common-pointing-priors.md](common-pointing-priors.md) is used (that note
  is a katbeam toy with achromatic gains; its prior would be an external
  assumption).
- **Gradient check:** the analytic columns are checked against central
  finite differences of the model, and on a Gaussian toy against JAX
  forward differentiation of the existing reference predictor
  `pointing.predict` (its conventions mapped: phase −2π and x = cos β l +
  sin β m with β = π − q, which flips y; the comparison is on the mapped
  quantities).

### The arms

- **G, gains-only** (metric 2's reference): θ = 0; gains and sky free.
- **(ii) physical pointing self-calibration, the SARAO/SKA way:** absolute
  per-antenna pointing offsets (2 per antenna per pointing interval) for
  **every** antenna with data, no squint, no common or shape terms, no
  selection; with the gains (Bhatnagar and Cornwell 2017). The sky fluxes
  are free as in every arm, so the nuisances are matched. *This specialises
  B1-1 (ii)'s wording "sky model fixed"*: with a free per-channel bandpass
  a fixed sky is not the same nuisance as rang's, and the brief asks for
  (ii) "in the same code with selection off". A fixed-sky (ii) is not run.
- **R, the rang method (distinguishability-selected corrections):** the
  candidate families are those that pass the Part 1 rerun on the set:
  per-antenna pointing, interval-common pointing, squint, ellipticity
  (width never). Per pointing interval and per family the selection is
  made **from R's own first pass** (θ = 0, training cells, gains solved),
  whose reduced and raw θ blocks give the frozen measures:
  - per-antenna pointing of antenna p, axis j, interval s: selected if its
    **family-marginal σ** (zero-mean parametrisation over the antennas with
    data in s, B1-2's definition) ≤ 0.3′ and its ρ ≥ 0.01. The selected
    antennas of an interval are fitted as **zero-mean contrasts** (their
    common mode is not a per-antenna direction);
  - interval-common pointing of interval s, axis j (δ_p = c_s,j for every
    antenna of s): selected if its family-marginal σ within the common
    family ≤ 0.3′ and ρ ≥ 0.01;
  - squint (x, y) and ellipticity: one value for the set (B1-2's
    intervals); selected by the same rule on the common family.

  Then passes 2… fit only the selected parameters. The selection pass is
  R's first pass (it is the normal-equation pass of step 2 with all
  candidate columns), so **its cost is charged to R's wall**. The
  separate Part 1 rerun is a research step and is not part of any arm's
  cost.
- **(i) the SARAO/SKA Gaussian fit** (B1-1, ported bit-exact): only where
  reference-pointing rasters exist, i.e. the fixture.

On the fixture (rasters, gain amplitudes, no visibilities to self-calibrate)
the same principle is applied to B1-1's data type: per antenna, the gain
amplitudes y[chunk, scan] are fitted as height_chunk × ½(|E_HH| + |E_VV|) at
the commanded positions minus the offset, with the B1-0 per-antenna sampler
(B1-1's G1b form), heights free per chunk, σ_y weights, chunks with σ_y = 0
dropped, the same 3′ prior; (ii) fits both axes of every antenna; R fits an
axis only if its marginal σ (heights profiled, the other axis free) ≤ 0.3′
and ρ ≥ 0.01 at zero offset, else holds it at zero.

## Part 3: the sets (frozen)

| Set | Data | Truth | Arms | Metrics |
| --- | --- | --- | --- | --- |
| **F1** | B1-1's G1b design: the fixture's five pointings, m000–m003, 14 chunk frequencies, injections 0, ±0.5′, ±1′, ±2′ per axis, seeds 1–200, the fixture's σ_y; truth from the B1-0 per-antenna co-polar beams | known | (i), (ii), R; control: (ii) and R fitted with the array average | 1 |
| **F1r** | the real fixture (`outer_scans.zip`), B1-1's gain amplitudes | unknown | (i), (ii), R | 1 (agreement within combined σ), 4 (end to end) |
| **F2** | science field on the S5 track geometry (7 scan chunks: UVW, TIME, antennas, row flags, and per sample the S5 tile-20 eligibility of channel 8f), **16 channels at 900 + (f + ½) 46.875 MHz** (900–1650 MHz) | known | G, (ii), R | 1, 2, 3 |
| **F3** | snapshot on the S4 pilot geometry (27 dumps; 25 channels at the 20-channel block centres of the pilot band; eligibility of the block's first channel) | known | G, (ii), R | 1, 2 |
| **S4** | ESO137 pilot (B1-2's S4, 500 channels) | unknown | G, (ii), R | 2, 4 |
| **S5** | ESO137 track (B1-2's S5, 7 × 128 channels) | unknown | G, (ii), R | 2, 4, self-consistency |
| **S2** | 1934 whole array (B1-2's S2), squint and marginal per-antenna pointing only | unknown | G, (ii), R | 2, 4 |
| **S1** | 1934 four stations (B1-2's S1), same | unknown | G, (ii), R | 2, 4 |
| S3 | 1830 point | – | rerun only (gate G3a) | – |

**Candidate families for R:** F2 takes S5's rerun verdict, F3 takes S4's;
S1, S2, S4, S5 their own. On S1/S2 only per-antenna pointing and squint are
candidates (the brief: "only for the squint direction and the marginal
per-antenna pointing").

**Simulated science fields (F2, F3), frozen:**

- Antennas: the 61 ESO137 antennas with their own beams (truth).
- Bright sky: B1-2's 157 components, intrinsic S₀ at 1.4 GHz = the apparent
  flux / array-average I_b at the component (the pilot's mean q), α = −0.7.
- Faint sky (F2 only): 20 sources between the array-average half-power and
  first-null radii at 1.4 GHz and 20 at radii 0.3° to the half-power
  radius, position angles uniform, intrinsic S₀ log-uniform in 0.1–1 mJy,
  α ~ N(−0.7, 0.2), seed 31. **They are not in the calibration model** of
  any arm.
- Pointing truth: one offset per antenna per scan chunk, each axis
  N(0, 0.6′) (B1's σ per antenna per hour; the chunks are about an hour
  apart; the pilot is one chunk), seed 2026. No injected squint or shape
  error (the beam carries its own).
- Gains truth: per antenna × hand × channel × scan, amplitude e^{N(0, 0.1)},
  phase uniform, constant within a scan chunk, seed 17.
- Noise (F2 and F3 noisy realisations): complex Gaussian with real and
  imaginary variance s²/(w R), s² = 0.512 and w the median S4 weight per
  hand, R the number of native channels a simulated channel stands for (F2:
  46.875/0.209 = 224.3; F3: 20): the simulated data carry the information
  of the full band of the same chunks. Seed 5. **F2 also has a noise-free
  twin**, on which metric 3 is called (the distortion is systematic; the
  noisy F2 values are reported).
- Inverse crime, stated: the fitted beams are the simulating beams. The
  labelled control repeats (ii) and R on noisy F2 with the array-average
  beam in the fit.
- Faint-source recovery (metric 3), after each arm: on the residual
  visibilities (data − the arm's final model, at its gains), a linear
  least-squares flux per faint source per channel jointly for the 40
  sources, with that arm's beam (its fitted θ) and gains; then α and S₀ by
  a weighted fit of ln S against ln ν. Reported per source and as medians
  of |S/S_true − 1| and |α − α_true| per group (outer, core). **Analytic
  noise floor, stated before running:** with about 8.4e6 complex samples
  of σ ≈ 0.0095, a source's intrinsic flux σ is ≈ 2.3 µJy / I_b (≈ 12 µJy
  between half power and null), so on noisy F2 a 0.1 mJy source has S/N ≈
  8 and σ_α ≈ 0.7; a 1 mJy source σ_α ≈ 0.07. The noise-free twin isolates
  the pointing distortion.

**Held-out split (all visibility sets), frozen:** seed 7, 80/10/10,
`minimum_train` = 2, on the cells eligible in both hands. **Groups on L1's
grid, not the fit's gain grid:** (2-dump bin × 32-channel block) × baseline
on real data (with per-channel gain bins a group of the gain grid would
hold two cells, both reserved, and nothing would be held out); on F2 (2-dump
bin × 4 simulated channels) × baseline, on F3 (2-dump bin × 2 simulated
channels) × baseline. The draw covers the set's (rows, channels) array, rows
in scan order. Validation cells are not used. Test MSE: the mean over test
cells of the hand mean of (w / s_h²) |r_h|², predicted with the arm's final
parameters and the bin's gains (which were solved without the test cells).
On S4/S5 the field model was imaged from all pilot cells, a leak shared
equally by every arm.

**S5 self-consistency (frozen diagnostics, not in the call):** per antenna
and axis, the χ²/dof of (ii)'s seven per-scan offsets about their weighted
mean in the **antenna frame** and, rotated by R(q_s) to the sky frame, about
their weighted mean there. A physical pointing error is fixed (or smooth)
in the antenna frame; a sky-model error is fixed on the sky and rotates with
q in the antenna frame, so a lower sky-frame scatter flags a sky-model
artefact. The per-scan common modes of (ii) (and R's interval-common
pointing where fitted) are regressed on elevation and on (cos q, sin q):
the 60°-average beam's elevation errors would follow elevation (34–60° on
the track), sky-frame errors (cos q, sin q). Counts of antennas with lower
sky-frame scatter, the regressions and their significance are reported.

## Part 4: the decision rule (frozen before running)

**Margins:**

- *Held-out (metric 2):* Δ = (MSE_R − MSE_B) / MSE_B on the same test
  cells; m = max(2 SE, 1e-4) with SE the standard error of the paired
  per-cell differences divided by MSE_B. Better if Δ < −m, worse if Δ > m.
- *Offsets (metric 1):* the RMS of recovered − true offsets over antennas,
  axes, intervals (and seeds and injections on F1), arcmin. Ratio r =
  RMS_R / RMS_B: better if r < 0.9, worse if r > 1.1. Bias (the mean error)
  reported.
- *Faint distortion (metric 3, noise-free F2):* better if the median |S/S_true
  − 1| or the median |α − α_true| (over all 40) is lower by ≥ 20 % and by
  ≥ 1e-3 (flux) or ≥ 0.005 (α), and neither is higher by those amounts;
  worse if either is higher by those amounts.
- *Cost (metric 4):* wall ratio within 1.5 (B1's factor) on the same data,
  host and threads; peak RSS reported.

**Per set, R against each applicable baseline** (the brief's labels):

- **beats**: every applicable quality metric is better (on simulated sets
  both held-out and offsets, plus metric 3 not worse on F2; on real sets
  held-out; on F1 offsets) and cost ≤ 1.5×;
- **worse**: any applicable quality metric is worse, or cost > 1.5×;
- **matches**: otherwise (nothing worse, cost within 1.5×).

Applicable baselines: (ii) and G on F2, F3, S1, S2, S4, S5; (i) and (ii)
on F1 and F1r. (i) has no visibility model, so on the ESO137 and 1934 sets
it is **not applicable** (no public store holds pointing scans; B1-0 fact
9). Against (i) only metric 1 exists; its cost is compared end to end on
F1r and reported.

**Overall (B1's rule with applicability explicit):** rang is **positive**
iff all of:

1. against (ii): metric 2 or 3 better on at least one ESO137 set (F2, F3,
   S4, S5); metric 2 and 3 worse on no set; metric 1 no worse on F1, F2,
   F3; wall ≤ 1.5× (ii)'s on every set;
2. against (i): metric 1 no worse on F1 (r ≤ 1.1), with metric 1
   agreement within combined σ on F1r reported.

The novelty rule's other branch (comparable quality at materially lower
cost) counts too: rang is **positive (cost)** if it matches (ii) on every set
at ≤ 0.5× (ii)'s wall. Otherwise the overall result is **matched** (R
matches or beats (ii) on every set but rule 1 fails) or **negative** (R
worse than (ii) on any ESO137 set). **B1 closes null unless the overall
result is positive.** No margin, set or arm moves after a result is seen.

## Part 5: the field model (frozen)

B1-2's self-calibrated model (157 components within 0.26°, E0 passed, the
central radio galaxy only, amplitude errors 3–4× by baseline length) is the
model for S4, S5, F2 and F3. **No external catalogue** (the user has not
allowed one; the limitation is recorded). The deeper option B1-2 permitted,
an image of the track, is **not built**: metric 3 runs on a simulated field
whose truth is known, and an image would add a second frozen procedure and
gate for the real sets only. The consequence is stated now: on S4 and S5
the held-out metric of every arm is dominated by the model's missing
diffuse and outer emission, which free component fluxes cannot absorb, and
pointing offsets there may absorb sky-model error (the self-consistency
diagnostics are designed to see it).

## Part 6: cost accounting (frozen)

Every arm runs as its own process on the WSL host with
`OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`, four single-threaded worker
processes over time bins (the same for all arms of a set). Recorded per
arm: solver wall (from data in memory to final parameters; decode, noise
calibration and held-out evaluation excluded and reported separately),
peak RSS of the process and its workers, passes (accepted, rejected),
gain bins solved and StefCal iterations, free parameters, and the data
volume read. On F1r the wall is end to end (read, gain solve, fit), because
(i)'s work is mostly the gain solve. On F1 (simulated amplitudes) the fit
wall is reported per fit.

## Expected outcome, stated before running

- **Rerun.** S3: G3a passes; full-Jones ρ ≲ 1e-3. Snapshot array-common
  pointing on S2, S3, S4 fails (B1-2 post hoc 1). Per-antenna pointing and
  squint survive on S4 and S5, per-antenna marginally on S2; S5's
  track-constant common pointing and ellipticity survive; width fails
  everywhere. Per-scan common pointing on S5 probably passes (σ ≈ 0.005′ ×
  √7). The per-antenna beams change σ by a few per cent.
- **F1.** (ii) and R remove the Gaussian model's bias (the inverse crime
  makes that almost automatic): r ≪ 0.9 against (i). With the array-average
  control the advantage shrinks. R = (ii) unless an axis fails selection.
  Cost: within 1.5× of (i) end to end on F1r only if the beam setup is
  small against the gain solve.
- **F2, F3.** R and (ii) recover offsets to well under the 0.6′ injected;
  on F3 (snapshot) (ii)'s common mode is weakly determined and R's
  zero-mean contrasts carry the true mean (≈ 0.6′/√61 ≈ 0.08′) as error; the
  RMS comparison can go either way. Held-out differences between R and (ii)
  are expected below a per cent, likely inside the margin; both beat G on
  the noisy F2 if the injected 0.6′ is visible. Metric 3: G distorts the
  faint outer sources by a few tenths of a per cent in flux; R and (ii) by
  much less on the noise-free twin.
- **S4, S5, S1, S2.** With 60/60 antennas passing on S4 the likely call is
  **matches**: R differs from (ii) by squint, the zero-mean constraint, and
  on S5 by the failing antenna-scans and the common directions. Held-out
  changes from pointing are sub-per-cent against model errors of factors of
  several.
- **Overall:** most likely **matched** (B1 closes null); positive only if
  squint or the selection improves held-out error beyond the margin on an
  ESO137 set while (ii) does not.

## Code to write after this commit (owner files)

- `python/rang/pointing_selfcal.py`: per-antenna beams (the frozen rule),
  the beam terms and their Jacobian, the per-bin profiled normal equations,
  the LM solver with selection on and off, the held-out evaluation, the
  raster (fixture) fit, the simulations.
- `python/rang/beam_identifiability.py`: new functions only (the
  per-channel survey accumulator, per-antenna factors); nothing existing
  changes.
- `examples/b1_survey_rerun.py` (Part 1, receipts), `examples/b1_pointing_selfcal.py`
  (Parts 2–4, receipts, archive).
- `tests/test_b1_pointing_selfcal.py`: fast synthetic cases (offsets
  recovered on a toy array with a known beam; the selection reproduces the
  identifiability verdict; per-channel accumulation equals a dense
  projection; per-antenna rule identity; Jacobian against finite
  differences and the JAX reference path; G3a on a toy).
- `research/results/b1-3-pointing-selfcal.json`: derived numbers only.

## What is not used

The validation cells of the split. Any catalogue. Any CLEAN image made in
B1-3. The B1-2 survey numbers as R's selection (R selects from its own first
pass; Part 1 decides only the candidate families).
