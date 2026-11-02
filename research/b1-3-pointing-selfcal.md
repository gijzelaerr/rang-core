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

Status (2026-11-02): **implemented and measured; overall negative under the
frozen rule; B1 closes null.** Every frozen set and arm ran (two dated
amendments, below). The survey rerun: snapshot common pointing goes on S2, S3
and S4; per-antenna pointing and squint survive; the track's directions
survive; width fails where it would be fitted. Physical pointing
self-calibration works on simulations (0.62′ → 0.054′, held-out −3 %), R
matches (ii) there and beats (i) on the fixture but loses to (ii) on it. On
real data neither arm measures pointing with B1-2's self-calibrated model.
Details in "Measured result".

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

## Amendment 1 (2026-10-31, dated and labelled; before any F2 or real-set measurement)

Two implementation faults found while measuring, fixed for every arm and set
alike. No margin, set, arm, metric or rule changes.

1. **The gains were not re-solved exactly.** The protocol requires the gains
   "re-solved exactly for the current sky and beam" with B1-2's StefCal form
   (100 iterations, averaging 0.5, relative change 1e-8). From unit gains a
   minority of bins need thousands of averaged iterations: on F2 (G arm,
   first pass) a warm repeat at unchanged parameters lowered χ² by 16,936
   with the 100-iteration cap, by 2,107 with 300, by 201 with 1,000 and by
   15.8 with 3,000, while the sky step itself lowered it by 5,495 against a
   predicted 5,489 (so the reduced Hessian and gradient were right). Each
   later pass mostly continued the gain solve, and the LM objective fell
   linearly (the failed F2 runs reached the 10-pass limit at relative
   decreases of 5e-6). **From now on each bin's StefCal result is followed by
   Gauss–Newton steps on that bin's gains alone** (log-amplitude and phase
   from the gains-only normal equations, minimum norm in the phase gauge,
   until the largest update is below 1e-10 or after 5 steps). With it the
   warm repeat changes χ² by 0.0, at the same pass wall (29.5 s against
   29.3 s); 2.1 polishing steps per bin on the first pass, 1.0 after.
2. **The beam frequency of the simulations.** The fit evaluated the beam at
   the centre of each 16-channel sub-block, the Part 1 evaluation for native
   0.209 MHz channels. A simulated channel stands for R native channels (F2:
   224, F3: 20), so on F2 all 16 channels (900–1650 MHz) shared one beam
   frequency and the simulated beam was achromatic. **On the simulated sets
   the beam is evaluated at every simulated channel's own frequency** (in the
   simulation and in every fit); real sets keep the 16-native-channel
   evaluation. F2 and F3 are simulated again under this rule.

Bookkeeping: the F3 runs measured before this amendment
(`b1-3-20261030-10-F3-G`, `-11-F3-ii`, `-12-F3-R`) and their simulation
(`-06-sim-F3`) are kept and labelled superseded; the F2 runs `-13`, `-14`,
`-15` failed in the faint-source evaluation (the fitted beams were cropped to
the bright components' radius, a bug now fixed: the crop includes the faint
positions) and are kept as failures with their simulation `-07-sim-F2`. The
fixture runs (`-08-fixture`) are unaffected (no gains are solved there and
no visibilities are predicted). Every set is measured after this amendment.

**What had been seen when this amendment was written.** The fixture runs
(F1, F1r) and the first F3 runs. F1: RMS offset error (i) 0.634′, (ii)
0.200′, R 0.357′ (R holds an axis that fails its rule at zero; m003 x fails
in most seeds); F1r costs (i) 0.63 s, (ii) 0.90 s, R 0.81 s end to end.
First F3: offsets RMS (ii) 0.193′, R 0.110′, G 0.608′; held-out MSE G
2.06301, (ii) 2.054770, R 2.054771. One consequence follows from F1 alone
under the frozen overall rule and is stated here, before any ESO137 fit
under the amendment: R/(ii) on F1 is 1.78 > 1.1, so clause 1 ("metric 1 no
worse on F1") fails and the cost branch (which needs "matches" on every
set) is out. **The overall result can only be "matched" or "negative", and
B1 closes null** whatever the ESO137 sets show. The fixture rule for R is
not revisited (that would move a rule after a result).

## Amendment 1a (2026-10-31, dated and labelled; before any real-set measurement)

On the first real set (S4, arm G, run `b1-3-20261030-46-S4-G`, kept as a
failure) the polishing of amendment 1 diverged on some bins: an undamped
Gauss–Newton step from a poor StefCal start overflowed, the gains became
infinite and every trial objective was NaN. **The polishing is now
safeguarded:** a step is taken only if it does not raise that bin's χ²
(halving it up to 20 times, and never larger than 1 in log-amplitude or
phase); otherwise polishing stops. On the simulated sets the safeguard
changes nothing: the first-pass χ² of F3 and F2 equal the recorded ones of
runs `-35` and `-38` to the last digit (its halvings there are rounding-level
at the last step). The F2 and F3 results under amendment 1 therefore stand;
S4, S5, S1 and S2 are measured under 1a. No margin, set, arm or rule
changes.

## Bookkeeping fix (2026-11-02, labelled; before the S4 and S5 pointing arms)

Runs `b1-3-20261030-59-S4-ii`, `-60-S4-R`, `-62-S5-ii` and `-63-S5-R` (kept
as failures) stopped with "beam coordinates outside the cropped grid": an LM
trial put a pointing offset beyond the crop (the components' radius plus
7′). A trial outside the beam grid has no finite objective, so it is now
counted as a rejected step (λ × 10, as for any rejected step) instead of
ending the run; the count is recorded per arm. Nothing else changes.

## Implementation (2026-10-30/31)

**`python/rang/pointing_selfcal.py`** (new):

- `AntennaBeams`: per-antenna holography beams by the frozen rule. Spline
  coefficients of the native array average at the bracketing native
  channels plus the antenna's difference at the bracketing product channels,
  combined linearly in frequency (the prefilter is linear), cropped after
  prefiltering to the components' radius plus the taps, normalised so that
  each antenna's own Stokes I power is 1 at its origin. `sample_stack`
  evaluates value and analytic gradients at per-antenna points. Modes
  `antenna` (the rule) and `average`; `copolar` zeroes HV and VH.
  `ToyBeams` and `ScaledGaussianBeams` (the beam of `pointing.predict`)
  stand in for tests.
- `beam_terms`, `pair_terms`: the h row of each antenna's Jones at T_p,h(u)
  = D(e) (u − δ_p − σ_h s/2) and its derivatives (δ, e, w); per baseline the
  factor B_pq,h and its derivatives (fit mode, intrinsic fluxes) or the
  ratio dB/B (survey mode, apparent fluxes as B1-2).
- `_task`: one (scan, 32-channel block) of a pass, in forked workers. Per
  time bin and 16-channel run: the phase recurrence, the amplitudes of
  every channel of the run, the beam terms of each variant at its
  sub-block centre and their batched contraction with the amplitudes; per
  channel and hand: StefCal-form gains (warm start), the whitened normal
  equations from per-sample columns (`beam_identifiability.normals_columns`),
  Schur elimination of the gains with the right-hand side (`schur_rhs`),
  and the primary-arm moments Σ m, Σ lf m, Σ lf² m. Modes: `survey`,
  `fit`, `predict` (simulations), `eval` (held-out cells), `faint`
  (faint-source normal equations).
- `Problem`, `solve`: the profiled Levenberg–Marquardt solver of the
  protocol with the arms G, ii, R; `select_directions` (R's selection from
  its first pass), `physical_design` ((ii)), the formal σ of the beam
  parameters at the solution; `split_cells` (seed 7 on L1's grid, through
  `core_campaign_array.split_holdout_lean`, bit-identical to
  `core_policy.split_holdout`), `predictable`, `heldout`, `paired`.
- `RasterBeam`, `fit_raster`: the fixture's data type, all chunks at once.

**`python/rang/beam_identifiability.py`**, new functions only:
`normals_columns` (the per-antenna generalisation of `block_normals`, with
the gradient), `schur_rhs`, `lf_map`, `lf_map_vector`, `lf_assemble`,
`lf_assemble_vector`, `ChannelSurvey` (per-channel gain bins, primary-arm
moments per (scan, hand), strict blocks per (scan, 32-channel block, hand),
κ at combination, B1-2's label layout through `label_transform`).

**`examples/b1_survey_rerun.py`** (Part 1): B1-2's loaders, models and
noise records; the antenna-name maps (LUNO json2, ESO137 opcode names);
variants; G3a; the S1 convergence check; per-scan common pointing; the
candidate families.

**`examples/b1_pointing_selfcal.py`** (Parts 2–4): `fixture` (F1, F1r),
`simulate` (F2, F3), `fit SET ARM` (one arm per process; solver, held-out,
offsets, faint fit, cost), `compare` (the frozen calls and the archive).

**Validation** (`tests/test_b1_pointing_selfcal.py`, 18 tests, about 10 s):

- `normals_columns` equals B1-2's `block_normals` for identical beams to
  1e-10, and its gradient equals Jᵀr of the dense Jacobian;
- `ChannelSurvey` on one-channel bins equals B1-2's `Survey` (itself
  checked against a dense projection) to 1e-8 in all six information
  matrices;
- the per-antenna rule reproduces the antenna's own map at product
  channels and the average-plus-difference rule between them (1e-6), and
  its gradients equal central differences; the stack sampler equals
  `map_coordinates` to 1e-12; the raster sampler equals the B1-0 sampler;
- pair-term derivatives (pointing, squint, ellipticity) equal finite
  differences to 1e-7;
- **the JAX reference path:** the model and the analytic pointing columns
  equal `pointing.predict` and its `jax.jacfwd` to 1e-12 and 1e-10 after
  the convention map (phase conjugated, β = π − q, y flipped);
- (ii) recovers injected offsets on a toy array with per-channel gains to
  2e-3′ noise-free; R recovers them with every direction selected;
- R's selection measures from its first pass equal the per-channel
  survey's conditional σ to 1e-6 when the two models coincide;
- G3a on a toy: a single component with diagonal per-antenna beams gives
  ρ ≤ 1e-6 for every direction;
- polishing reaches the exact least-squares gains and never raises a bin's
  χ² from a bad start (amendments 1, 1a);
- the split reserves two training cells per group; the held-out error with
  the right pointing beats gains-only on a noisy toy; the raster fit
  recovers an injected offset.

**Speed.** One S4 task (32 channels × 14 bins × 2 hands) takes about 30 s
single-threaded: the normal equations about 10 ms per hand-bin, of which
the sky Gram (one BLAS syrk) 2.6 ms; StefCal 6 ms from unit gains; the
batched contraction 1 ms. B1-2's S2 survey was BLAS-bound and so is this;
the remaining cost is NumPy glue around small matrices, which a Rust port
would cut by perhaps 2×, not the order of magnitude that would change any
schedule decision, so **no Rust kernel** was written (Part 1's frozen
trigger, an extrapolated S2 rerun above 3 h, did not fire: it took 20 min).

## Measured result (2026-10-30 to 2026-11-02)

### Part 1: the survey rerun

Runs (WSL host, `OPENBLAS_NUM_THREADS=1`, four single-threaded workers):
`outputs/b1-3-20261030-01-rerun-S3`, `-02-rerun-S1`, `-03-rerun-S4`,
`-04-rerun-S5`, `-05-rerun-S2`, each with `survey.json`. The noise scale s²
recomputed by B1-2's `noise_for` equals B1-2's records exactly (relative
difference 0.0 on every set, scan and hand); c and κ = c²/s² are B1-2's.

**Gate G3a passes.** On S3 the `copolar` variant gives ρ ≤ 8.0e-9 for every
direction (gate 1e-6). With the full Jones the largest ρ is 3.3e-4, the
cross-polar terms (stated ≲ 1e-3). The array-average variant gives ρ = 0 to
rounding.

**Convergence check (S1): did not fire.** The 8-channel beam evaluation
changes the common directions' σ by at most 0.41 % and the median
per-antenna σ by 0.08 % (rule 5 %): with per-channel gains nothing depends
on the in-interval beam structure any more. The 16-channel evaluation is
the verdict evaluation on every set.

Tables: the verdict variant (per-antenna beams, per-channel gains, sub16),
beside the array-average variant with the same gains and B1-2's verdict
(32-channel gains, array average). σ in the direction's unit (arcmin, or a
fraction for width and ellipticity); per-antenna rows give the median (and
minimum) σ and the median ρ; "σ family" is the family-marginal σ.

**S1, 1934, four stations:** nothing is constrainable (as B1-2).

| Direction | σ | ρ | call | σ average beam | σ family | σ strict | B1-2 σ | B1-2 call |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| pointing x | 19.6 | 0.0022 | no | 19.8 | 26.8 | 31.3 | 1.56 | no |
| pointing y | 36.4 | 0.0011 | no | 36.2 | 50.3 | 46.7 | 0.564 | no |
| log-width | 0.315 | 0.015 | no | 0.318 | 0.504 | 0.654 | 0.297 | no |
| ellipticity | 0.323 | 0.026 | no | 0.325 | 0.433 | 0.409 | 0.308 | no |
| squint x | 1.72 | 0.051 | no | 1.72 | 2.06 | 1.72 | 1.46 | no |
| squint y | 1.70 | 0.049 | no | 1.71 | 1.81 | 1.70 | 0.922 | no |
| per-antenna x (4) | 31.4 (26.5) | 0.0036 | 0 of 4 | 31.7 | 30.8 | – | 3.26 | 0 of 4 |
| per-antenna y (4) | 56.4 (45.5) | 0.0017 | 0 of 4 | 57.2 | 63.3 | – | 1.16 | 0 of 4 |

**S2, 1934, whole array:** squint and per-antenna pointing survive; the
snapshot common pointing does not.

| Direction | σ | ρ | call | σ average beam | σ family | σ strict | B1-2 σ | B1-2 call |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| pointing x | 0.381 | 0.0041 | no | 0.393 | 0.697 | 0.838 | 0.0821 | yes |
| pointing y | 0.643 | 0.0035 | no | 0.678 | 0.864 | 1.12 | 0.0316 | yes |
| log-width | 0.00523 | 0.070 | no | 0.00548 | 0.0106 | 0.0125 | 0.00537 | no |
| ellipticity | 0.00692 | 0.070 | no | 0.00736 | 0.0116 | 0.0129 | 0.00721 | no |
| squint x | 0.0372 | 0.085 | **yes** | 0.0371 | 0.0376 | 0.0372 | 0.0357 | yes |
| squint y | 0.0530 | 0.084 | **yes** | 0.0530 | 0.0534 | 0.0530 | 0.0404 | yes |
| per-antenna x (53) | 0.189 (0.163) | 0.10 | **52 of 53** | 0.189 | 0.188 | – | 0.177 | 52 of 53 |
| per-antenna y (53) | 0.273 (0.238) | 0.065 | **48 of 53** | 0.274 | 0.271 | – | 0.177 | 52 of 53 |

**S3, 1830, a point:** every direction is absorbed (ρ ≤ 3.3e-4); what
passed in B1-2 was the 32-channel gain granularity, as its post hoc 1 said.

| Direction | σ | ρ | call | B1-2 σ | B1-2 call |
| --- | ---: | ---: | --- | ---: | --- |
| pointing x, y | 144, 170 | 2.5e-5, 3.2e-5 | no | 0.206, 0.0760 | yes, yes |
| log-width, ellipticity | ∞ (no signature at the centre) | – | no | ∞ | no |
| squint x, y | 288, 341 | 2.5e-5, 3.2e-5 | no | 0.412, 0.152 | no, yes |
| per-antenna x, y (53) | 280, 305 | 1.8e-4, 1.5e-4 | 0 of 53 | 1.50, 0.601 | 0 of 53 |

**S4, ESO137 pilot:** per-antenna pointing (60/60) and squint survive; the
common pointing that passed in B1-2 (y, alone only) does not; the
per-antenna beams improve width (0.56 % from 0.75 %) and ellipticity
(0.75 % from 1.35 %), neither enough.

| Direction | σ | ρ | call | σ average beam | σ family | σ strict | B1-2 σ | B1-2 call |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| pointing x | 0.382 | 0.011 | no | 0.468 | 0.552 | 0.380 | 0.331 | no |
| pointing y | 0.446 | 0.011 | no | 0.548 | 0.607 | 0.450 | 0.280 | yes (alone only) |
| log-width | 0.00559 | 0.087 | no | 0.00749 | 0.00702 | 0.00562 | 0.00748 | no |
| ellipticity | 0.00745 | 0.12 | no | 0.0135 | 0.00914 | 0.00768 | 0.0135 | no |
| squint x | 0.0104 | 0.81 | **yes** | 0.0104 | 0.0188 | 0.0104 | 0.0103 | yes |
| squint y | 0.0117 | 0.88 | **yes** | 0.0117 | 0.0208 | 0.0117 | 0.0116 | yes |
| per-antenna x (60) | 0.0637 (0.0357) | 0.80 | **60 of 60** | 0.0639 | 0.0869 | – | 0.0637 | 60 of 60 |
| per-antenna y (60) | 0.0716 (0.0420) | 0.83 | **60 of 60** | 0.0715 | 0.101 | – | 0.0714 | 60 of 60 |

**S5, ESO137 track:** everything B1-2 found survives; with the per-antenna
beams the log-width also passes conditionally (0.41 %, ρ 0.085), but only
alone (family-marginal 0.58 %), and width is excluded from fitting anyway.

| Direction | σ | ρ | call | σ average beam | σ family | σ strict | B1-2 σ | B1-2 call |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| pointing x | 0.00558 | 0.54 | **yes** | 0.00558 | 0.00738 | 0.00558 | 0.00555 | yes |
| pointing y | 0.00430 | 0.80 | **yes** | 0.00430 | 0.00521 | 0.00430 | 0.00428 | yes |
| log-width | 0.00408 | 0.085 | **yes** (alone only) | 0.00549 | 0.00579 | 0.00408 | 0.00545 | no |
| ellipticity | 0.000554 | 0.88 | **yes** | 0.000555 | 0.000744 | 0.000554 | 0.000553 | yes |
| squint x | 0.00710 | 0.84 | **yes** | 0.00709 | 0.00771 | 0.00710 | 0.00706 | yes |
| squint y | 0.00763 | 0.91 | **yes** | 0.00763 | 0.00766 | 0.00763 | 0.00761 | yes |

| S5 scan chunk | per-antenna x: pass, σ median | per-antenna y: pass, σ median | per-scan common pointing σ x, y (ρ) |
| --- | --- | --- | --- |
| 0 | 60, 0.092′ | 60, 0.107′ | 0.0088′, 0.0100′ (0.76, 0.80) |
| 1 | 60, 0.096′ | 52, 0.183′ | 0.0085′, 0.0166′ (0.79, 0.83) |
| 2 | 60, 0.083′ | 51, 0.211′ | 0.0073′, 0.0208′ (0.77, 0.86) |
| 3 | 60, 0.103′ | 57, 0.167′ | 0.0095′, 0.0150′ (0.81, 0.88) |
| 4 | 58, 0.147′ | 60, 0.114′ | 0.0137′, 0.0107′ (0.80, 0.86) |
| 5 | 48, 0.193′ | 60, 0.097′ | 0.0190′, 0.0086′ (0.77, 0.84) |
| 6 | 56, 0.173′ | 60, 0.082′ | 0.0180′, 0.0080′ (0.75, 0.83) |

Per-scan common pointing passes in every scan and axis.

**Which directions survive the rerun (the candidates for R):**

| Set | Candidates | Not candidates |
| --- | --- | --- |
| S1 | none | everything |
| S2 | per-antenna pointing (52/53 x, 48/53 y), squint | common pointing, width, ellipticity |
| S3 | none | everything (the control) |
| S4 (and F3) | per-antenna pointing (60/60), squint | common pointing, width, ellipticity |
| S5 (and F2) | per-antenna pointing, per-scan common pointing, squint, ellipticity | width (excluded; passes alone only) |

The expectation stated before running holds in every line: the snapshot
common pointing goes on S2, S3 and S4, everything else B1-2 found
survives, width fails wherever it would be fitted. The per-antenna beams
change the per-antenna and squint σ by under 1 % and the shape directions
on S4 by 25–45 %.

### Parts 2–4: the fits

Every number below is under amendments 1 and 1a. Archive:
[results/b1-3-pointing-selfcal.json](results/b1-3-pointing-selfcal.json)
(derived numbers only, keyed by set and arm, with run directories; `compare`
with the spec `outputs/b1-3-20261030-compare-spec.json`).

**The fixture, F1** (`-08-fixture`; 13 injections × 200 seeds × 4 antennas ×
2 axes; truth from the per-antenna beams):

| Arm | RMS error ′ | bias ′ | axes selected | wall per 4-antenna fit | R against it: RMS ratio, call |
| --- | ---: | ---: | ---: | ---: | --- |
| (i) Gaussian fit | 0.634 | −0.092 | – | 19 ms | 0.562, **better** |
| (ii) holography raster fit | 0.200 | 0.001 | all | 23 ms | 1.78, **worse** |
| R | 0.357 | 0.000 | 87.5 % | 22 ms | – |
| control: (ii), array-average beam fitted | 0.248 | −0.042 | all | 22 ms | – |
| control: R, array-average beam fitted | 0.379 | −0.017 | 87.5 % | 22 ms | – |

The mechanism is the selection, not a fault. R equals (ii) on 7 of the 8
antenna-axes. m003 x fails the rule in F1's design, so R
holds it at zero and carries the injection as error: RMS over the whole set
0.165′ at zero injection and for every y injection (better than (ii)'s
0.200′), growing to 0.72′ at x injections of ±2′. (ii)'s advantage over (i)
is largely the inverse crime (it fits the beam that made the data), but the
array-average control keeps most of it (0.248′).

**The real fixture, F1r** (`-08-fixture`; no truth):

| Antenna | (i) xEl, El ′ (σ) | (ii) xEl, El ′ (σ) | R xEl, El ′ |
| --- | --- | --- | --- |
| m000 | −3.70 (5.39), +2.06 (1.45) | −3.58 (0.19), −0.47 (0.22) | same as (ii) |
| m001 | +5.24 (3.57), +1.37 (1.18) | −4.28 (0.17), −4.58 (0.14) | same as (ii) |
| m002 | +5.86 (7.31), −5.96 (3.22) | +6.59 (0.21), −8.95 (0.26) | 0 (not selected, marginal σ 0.32′), −8.76 |
| m003 | +3.40 (2.77), −1.72 (2.16) | +4.38 (0.28), −6.32 (0.19) | same as (ii) |

Agreement with (i) within the combined σ: 4 of 8 axes for both (ii) and R. The
offsets of up to 9′ with formal σ of 0.2′ are not credible as pointing: the
raster fit's formal σ assumes the gain amplitudes follow the beam and nothing
else. End-to-end wall (read, gain solve, fit): (i) 0.63 s, (ii) 0.90 s
(1.42×), R 0.81 s (1.28×; 0.90× (ii)).

**The simulated science fields** (true beam fitted; inverse crime stated in
the protocol):

| Set | Arm | held-out MSE | offsets RMS (bias) ′ | squint ′, ellipticity | free beam parameters | passes | solver wall | peak RSS (workers) |
| --- | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| F3 snapshot | G | 2.063018 | 0.608 (−0.030) | – | 0 | 3 | 165 s | 1.43 GB |
| F3 | (ii) | 2.054765 | 0.173 (+0.018) | – | 120 | 3 | 195 s | 1.60 GB |
| F3 | R | 2.054767 | 0.110 (−0.030) | (0.0004, 0.010), – | 120 (120/120 antenna-axes as 118 contrasts, squint) | 3 | 202 s | 1.61 GB |
| F2 track, wide band | G | 2.153224 | 0.617 (−0.015) | – | 0 | 3 | 312 s | 2.92 GB |
| F2 | (ii) | 2.089364 | 0.0543 (−0.0075) | – | 840 | 4 | 579 s | 2.95 GB |
| F2 | R | 2.089363 | 0.0572 (−0.012) | (−0.0010, 0.0020), 0.085 % | 843 (840/840, 14 per-scan common, squint, ellipticity) | 4 | 585 s | 2.99 GB |
| F2, array-average beam fitted (control) | (ii) | 2.173959 | 0.181 (+0.023) | – | 840 | 4 | 567 s | 1.48 GB |
| F2, control | R | 2.173918 | 0.182 (+0.008) | (0.0044, 0.0069), 0.44 % | 843 | 4 | 589 s | 1.50 GB |
| F2-free (noise-free twin) | G | 0.1022 | 0.617 | – | 0 | 3 | 398 s | 2.89 GB |
| F2-free | (ii) | 0.03798 | 0.0323 | – | 840 | 4 | 610 s | 2.93 GB |
| F2-free | R | 0.03798 | 0.0326 | (−0.0005, 0.0005), 0.047 % | 843 | 4 | 712 s | 2.97 GB |

An MSE of 2 is pure noise (two real degrees of freedom per sample). Truth
offsets have RMS 0.61–0.62′. **Physical pointing self-calibration works on
simulated data:** 0.617′ → 0.054′ on F2 and 3.0 % lower held-out error than
gains-only (Δ −2.97e-2, margin 6e-4); on F3 0.608′ → 0.17′ and 0.40 % lower.

Faint sources on F2 (metric 3; the noise-free twin carries the call, medians
over the 40 sources):

| Run | Arm | median \|S/S_true − 1\| (outer, core) | median \|α − α_true\| (outer, core) |
| --- | --- | --- | --- |
| noise-free | G | 0.0588 (0.0772, 0.0546) | 0.118 (0.159, 0.056) |
| noise-free | (ii) | 0.0454 (0.0301, 0.0488) | 0.0420 (0.0592, 0.0376) |
| noise-free | R | 0.0455 (0.0306, 0.0489) | 0.0413 (0.0593, 0.0379) |
| noisy | G | 0.0631 (0.155, 0.0389) | 0.121 (0.387, 0.086) |
| noisy | (ii) | 0.0548 (0.0575, 0.0548) | 0.0965 (0.124, 0.090) |
| noisy | R | 0.0573 (0.0599, 0.0548) | 0.0967 (0.124, 0.091) |

Correcting pointing cuts the outer sources' flux error by 2.6× and the
spectral-index error by 2.7× on the noise-free twin. R and (ii) are the same.
The flux floor of about 4.5 %, with pointing recovered to 0.03′, is not
pointing (see post hoc 3).

**The real sets** (truth unknown; every arm stopped at the 10-pass limit):

| Set | Arm | held-out MSE (the frozen mean) | post hoc: median (mean of the lowest 99.9 %) | largest cell | offsets RMS, max ′ | squint ′, ellipticity | free beam parameters | passes accepted, rejected (outside the beam grid) | solver wall | peak RSS |
| --- | --- | ---: | --- | ---: | --- | --- | --- | --- | ---: | ---: |
| S4 | G | 2.77e9 | 12.09 (37.4) | 5.2e15 | – | – | 0 | 4, 5 (0) | 1488 s | 2.46 GB |
| S4 | (ii) | 9.85e5 | 12.83 (78.4) | 1.6e12 | 1.57, 7.3 | – | 120 | 2, 7 (7) | 714 s | 2.59 GB |
| S4 | R | 3.27e9 | 11.70 (39.7) | 6.4e15 | 7.38, 24.5 | (−0.005, 1.04), – | 94 (94/120, squint) | 3, 6 (5) | 1554 s | 2.70 GB |
| S5 | G | 2.67e5 | 11.88 (37.8) | 6.6e11 | – | – | 0 | 4, 5 (0) | 3553 s | 3.89 GB |
| S5 | (ii) | 2.19e5 | 12.90 (72.5) | 8.0e11 | 1.85, 11.4 | – | 840 | 2, 7 (7) | 2153 s | 3.89 GB |
| S5 | R | 1.83e5 | 12.24 (51.5) | 6.7e11 | 4.74, 20.5 | (0.035, 0.12), 1.3 % | 606 (603/840, 14 per-scan common, squint, ellipticity) | 2, 7 (7) | 1890 s | 3.89 GB |
| S1 | G | 3.80935 | 3.0765 (3.787) | 30 | – | – | 0 | 3, 6 (0) | 461 s | 1.78 GB |
| S1 | (ii) | 3.81994 | 3.0728 (3.797) | 30 | 1.50, 2.5 | – | 8 | 3, 6 (0) | 834 s | 1.78 GB |
| S1 | R | 3.80935 | identical to G | 30 | 0 | (0, 0) | 0 (no candidate survived) | 3, 6 (0) | 896 s | 1.78 GB |
| S2 | G | 2.60541 | 1.9552 (2.5758) | 800 | – | – | 0 | 4, 5 (0) | 5320 s | 7.13 GB |
| S2 | (ii) | 2.60515 | 1.9552 (2.5756) | 805 | 4.63, 9.3 | – | 106 | 4, 5 (0) | 4827 s | 7.34 GB |
| S2 | R | 2.60536 | 1.9551 (2.5757) | 813 | 2.35, 6.7 | (−0.48, −0.63), – | 69 (69/106, squint) | 4, 5 (0) | 4842 s | 7.32 GB |

S5's self-consistency (frozen diagnostics, not in the call):

| Arm | χ²/dof about the mean, antenna frame (median over 60 antennas) | same, sky frame | antennas lower in the sky frame | common mode against elevation (F-test p, x, y) | against (cos q, sin q) (p, x, y) |
| --- | ---: | ---: | ---: | --- | --- |
| (ii) | 41.5 | 29.6 | 37 of 60 | 0.56, 0.050 | 0.87, **0.0064** |
| R | 1031 | 833 | 48 of 60 | 0.35, 0.47 | **0.018**, **0.0034** |

Neither frame is near 1: the seven offsets of an antenna are not consistent
with each other within their formal σ. The lower scatter in the sky frame and
the common mode's significant sky-frame regression are what the protocol said
a sky-model artefact looks like. The per-scan common mode of R reaches 2.3′
(0.1–2.3′ in y), against formal family σ of 0.13–0.18′. **On real data this
fit does not measure pointing with this field model.** (ii)'s common mode
per scan: x −0.13 to +0.57′, y −0.12 to +1.21′.

### The frozen calls

Margins as frozen; held-out Δ = (MSE_R − MSE_B) / MSE_B on the same test
cells; m = max(2 SE, 1e-4).

| Set | Metrics, R against (ii) | wall ratio | Call against (ii) | Call against G (held-out Δ, wall ratio) |
| --- | --- | ---: | --- | --- |
| F1 | offsets ratio 1.78 worse; against (i) ratio 0.562 better, wall 1.28 → **beats (i)** | 0.90 | **worse** | not applicable |
| F2 (with the noise-free twin) | held-out Δ −3.7e-7 within (m 1e-4); offsets ratio 1.05 within; faint within | 1.01 | **matches** | better, −2.97e-2, wall 1.87 → worse (cost) |
| F3 | held-out Δ +8.5e-7 within; offsets ratio 0.637 better (both are required for "beats") | 1.03 | **matches** | better, −4.00e-3, wall 1.22 → beats |
| S4 | held-out Δ +3.3e3 within (m 6.6e3: the mean is a few cells) | **2.18** | **worse (cost)** | within, wall 1.04 → matches |
| S5 | held-out Δ −0.166 within (m 0.33) | 0.88 | **matches** | within, wall 0.53 → matches |
| S1 | held-out Δ −2.8e-3 better (m 5.2e-4): R = G, (ii) overfits | 1.07 | **beats** | identical, wall 1.94 → worse (cost) |
| S2 | held-out Δ +7.8e-5 within (m 1e-4) | 1.00 | **matches** | within, wall 0.91 → matches |

Control (reported, no call on the overall rule): F2 with the array-average
beam fitted: R against (ii) Δ −1.9e-5, offsets ratio 1.00, wall 1.04.

**Overall: negative. B1 closes null.** Clauses of the frozen rule:

| Clause | Holds? |
| --- | --- |
| metric 2 or 3 better than (ii) on an ESO137 set (F2, F3, S4, S5) | **no** |
| metric 2 or 3 worse than (ii) anywhere | no (good) |
| metric 1 no worse on F1, F2, F3 | **no** (F1, ratio 1.78) |
| wall ≤ 1.5× (ii) on every set | **no** (S4, 2.18) |
| metric 1 no worse than (i) on F1 | yes (ratio 0.56) |

The negative label (rather than matched) comes from one line: S4's wall ratio.
Amendment 1 already recorded that F1 fixes "matched or negative". The S4 ratio
is literal and frozen, but it is not a matched cost: 7 of (ii)'s 10 passes
were trials outside the beam grid, which cost almost nothing, against 5 of
R's, so (ii) computed 3 passes and R 5 (238 s and 311 s per computed pass;
1.31×). Had the S4 cost clause passed, the result would be matched and B1
would still close null. The novelty rule is not met on either branch.

### Deviations

- **Amendments 1 and 1a, and the trial-outside-the-grid fix**, above: dated,
  before the sets they apply to. F3 was measured twice; both versions are in
  this report (the first F3 runs: offsets (ii) 0.193′, R 0.110′; MSE G
  2.06301, (ii) 2.054770, R 2.054771). No call changed between them: R matches
  (ii), offsets better, held-out within.
- **R's family-marginal for the common family** is taken over the candidate
  common directions (per-scan common pointing, squint, ellipticity), without
  width, which is never fitted. B1-2's family included width.
- **c and κ in the rerun** are read from B1-2's records rather than recomputed
  (the same procedures; s² recomputed and identical).
- **Components with I_b < 0.01** are decided once per set in fit mode (at the
  set's lowest and highest frequency), not per block as in the survey, so that
  a component's base spectrum is one function.
- **The S5 regressions' σ** treat antennas as independent in the common mode's
  formal σ (no cross terms). The p-values are indicative.
- The anchored response and native S1 call are not repeated, as the protocol
  says. No Rust kernel; no CLI receipt writers, so main's receipt change does
  not touch this branch and main is not merged.

### Post hoc (labelled; none of this changes a call)

1. **The evidence for amendment 1** is in `outputs/b1-3-20261030-74-posthoc-gains`
   (scripts and log, rerun 2026-11-02 on the pre-amendment simulation `-07`).
   First pass of G on F2, warm repeat at unchanged parameters: χ² drop 16,936.1
   (StefCal cap 100), 2,106.9 (300), 201.1 (1,000), 15.8 (3,000), −0.0 (cap 100
   with polishing). Sky step: predicted decrease 5,488.9, actual 5,495.5.
2. **The real-set held-out means are set by a few cells.** Gains in badly
   constrained bins are unregularised and blow up under a poor model (largest
   cell 6e15 on S4). The frozen margin (2 SE) swallows this as "within". The
   medians are roughly 6× the noise value of 2 on ESO137 and do not separate
   the arms in a useful way: S4 G 12.09, (ii) 12.83, R 11.70; S5 G 11.88, (ii)
   12.90, R 12.24. The mean of the lowest 99.9 % orders S4 and S5 as G < R <
   (ii). The pointing arms made fewer accepted steps than G (2–3 against 4)
   because large trial offsets left the grid, so these are comparisons between
   unequally converged fits at the 10-pass limit (on S4 and S5 still falling 9–30 %
   per accepted pass). Read them as "not distinguishable, not converged".
3. **The faint-flux floor (4.5 %) is self-calibration suppression (inferred,
   not separately tested).** The faint sources are absent from the calibration
   model and the gains are free per channel and 2-dump interval. With pointing
   recovered to 0.03′ on noise-free data the floor remains, and it is the same
   for every arm that corrects pointing. It is a property of the frozen
   nuisance and exceeds the pointing distortion it is meant to expose in the
   core (G 5.5 %, (ii) 4.9 %).
4. **Spurious ellipticity on F2.** R returns 0.085 % where the truth is zero
   (first-pass family-marginal σ 0.028 %, about 3σ; 0.047 % on the noise-free
   twin), and 0.44 % with the array-average beam fitted. The unmodelled faint
   sources are the likely cause on the true-beam fit, and the shape error of
   the average beam on the control (not separately tested).
5. **Per-antenna beam differences matter at this sensitivity.** Fitting the
   array average to per-antenna truth triples the offset error (0.054′ → 0.18′)
   and makes held-out error (2.1740) worse than gains-only with the true beams
   (2.1532).
6. **R's real squint.** S2 returns (−0.48′, −0.63′) and S4 (−0.005′, +1.04′)
   against family σ of 0.04–0.06′ and about 0.01′, far outside anything the holography beam
   allows. The direction is constrainable, and it absorbs sky-model error.
   B1-2's "not shown" (whether these directions can be estimated without bias
   from real data) is answered no for this model.

### What this shows, and what it does not

- **Shown (simulation):** physical pointing self-calibration with the
  holography beam recovers 0.6′ errors to 0.05′ and lowers held-out error by
  3 % at full-band sensitivity. It reduces faint-source spectral-index error
  2.7× on the outer sources. Against the SARAO/SKA Gaussian fit's data type it
  has 3× lower error (2.5× with the array-average beam).
- **Shown (selection):** distinguishability selection adds nothing measurable
  over fitting every antenna. On F2 it selects everything. On F3 its only gain
  is not fitting the undetermined common mode (offsets 0.110′ against 0.173′),
  with no change in held-out error. On F1 it costs accuracy (holding a real
  offset at zero). On S1 it prevents (ii)'s overfit, by the trivial route of
  fitting nothing.
- **Shown (real data):** with B1-2's self-calibrated model neither arm measures
  pointing. Offsets of several to 24′, inconsistent between scans beyond their
  formal σ, sky-frame structure, squint at 10–140σ.
- **Not shown:** anything about real MeerKAT pointing, or the method with a
  good field model. The real-set failure is first of all the model's (the
  central galaxy only, amplitudes wrong by 3–4× by baseline length).
- The earlier toy result (adaptive protection adds nothing over joint fitting,
  [first-results.md](first-results.md)) now has a beam-level counterpart.

### Open items

- The real-set fits stop at the frozen 10 passes, unconverged. Regularised gains
  (a smoothness or amplitude prior) and a deeper model are the obvious
  next steps, neither frozen here.
- The ESO137 field-model limitation stands (no catalogue, no track image).
- R's fixture rule (hold a failing axis at zero) is costly by design; a
  shrinkage rule would be a new method, not tested here.
- Beam elevation dependence (34–60° on the track) could not be separated: the
  sky-model artefact dominates.

### What would change the answer

- A field model good enough that real-data χ² approaches noise (S4/S5 medians
  near 2, not 12), then S4/S5 rerun as frozen: the real-data rows could change,
  though F1's clause would still block "positive" under this rule.
- A selection rule that does not bias when it declines (fit with a prior,
  rather than hold at zero): a new protocol, since F1 is what blocks it here.
- Real pointing truth (reference-pointing scans alongside science data, none in
  the public stores), which is the only test of bias on real data.
- A set where the per-antenna rule actually fails for many antennas at full-band
  sensitivity; on every simulated set here R selected nearly everything.

### Timings (every tool run of this task)

WSL host, four workers (`OPENBLAS_NUM_THREADS=1`), date 2026-10-30 to 11-02.
Wall and peak RSS (largest process) from `/usr/bin/time`. The S4/S5 pointing
reruns and the post-hoc runs are 2026-11-02; everything else ran in one go on
2026-10-30/31 (a usage cut-off of the session on 10-31 hit no running job). The S4 and S5 (ii) and R runs `-70` to `-73` are reruns after the grid fix; the failed `-59`, `-60`, `-62`, `-63` are kept.

| Run | Wall | Peak RSS | Notes |
| --- | ---: | ---: | --- |
| uv venv + install | 78 s | 1.19 GB | builds the extension |
| ESO137 names probe (`-00-probe-names`) | 0.41 s | 43 MB | one GET each, opcode scan |
| `b1-3-20261030-06-sim-F3` smoke, F3 R smoke | 11 s, 45 s | 2.2, 1.25 GB | superseded by `-33` |
| `b1-3-20261030-01-rerun-S3` | 59 s | 3.18 GB |  |
| `b1-3-20261030-02-rerun-S1` | 157 s | 1.90 GB |  |
| `b1-3-20261030-03-rerun-S4` | 391 s | 2.23 GB |  |
| `b1-3-20261030-04-rerun-S5` | 792 s | 3.26 GB |  |
| `b1-3-20261030-05-rerun-S2` | 1180 s | 6.39 GB |  |
| `b1-3-20261030-07-sim-F2` | 26 s | 4.31 GB |  |
| `b1-3-20261030-08-fixture` | 285 s | 0.45 GB |  |
| `b1-3-20261030-10-F3-G` | 48 s | 1.02 GB | solver 41 s, 3 passes (2 accepted) |
| `b1-3-20261030-11-F3-ii` | 59 s | 1.18 GB | solver 52 s, 3 passes (2 accepted) |
| `b1-3-20261030-12-F3-R` | 65 s | 1.19 GB | solver 57 s, 3 passes (2 accepted) |
| `b1-3-20261030-13-F2-G` | 291 s | 1.11 GB | **failed**  |
| `b1-3-20261030-14-F2-ii` | 409 s | 1.27 GB | **failed**  |
| `b1-3-20261030-15-F2-R` | killed | – | stopped by hand |
| `b1-3-20261030-33-sim-F3` | 52 s | 2.55 GB |  |
| `b1-3-20261030-34-sim-F2` | 135 s | 6.09 GB |  |
| `b1-3-20261030-35-F3-G` | 213 s | 1.43 GB | solver 165 s, 3 passes (2 accepted) |
| `b1-3-20261030-36-F3-ii` | 244 s | 1.60 GB | solver 195 s, 3 passes (2 accepted) |
| `b1-3-20261030-37-F3-R` | 250 s | 1.61 GB | solver 202 s, 3 passes (2 accepted) |
| `b1-3-20261030-38-F2-G` | 523 s | 2.92 GB | solver 312 s, 3 passes (2 accepted) |
| `b1-3-20261030-39-F2-ii` | 808 s | 2.95 GB | solver 579 s, 4 passes (3 accepted) |
| `b1-3-20261030-40-F2-R` | 828 s | 2.99 GB | solver 585 s, 4 passes (3 accepted) |
| `b1-3-20261030-41-F2-ii-average` | 772 s | 1.48 GB | solver 567 s, 4 passes (3 accepted) |
| `b1-3-20261030-42-F2-R-average` | 821 s | 1.50 GB | solver 589 s, 4 passes (3 accepted) |
| `b1-3-20261030-43-F2-free-G` | 627 s | 2.89 GB | solver 398 s, 3 passes (2 accepted) |
| `b1-3-20261030-44-F2-free-ii` | 838 s | 2.93 GB | solver 610 s, 4 passes (3 accepted) |
| `b1-3-20261030-45-F2-free-R` | 979 s | 2.97 GB | solver 712 s, 4 passes (3 accepted) |
| `b1-3-20261030-46-S4-G` | killed | – | stopped by hand |
| `b1-3-20261030-58-S4-G` | 1547 s | 2.46 GB | solver 1488 s, 10 passes (4 accepted) |
| `b1-3-20261030-59-S4-ii` | 210 s | 2.49 GB | **failed**  |
| `b1-3-20261030-60-S4-R` | 285 s | 2.54 GB | **failed**  |
| `b1-3-20261030-61-S5-G` | 3717 s | 3.89 GB | solver 3553 s, 10 passes (4 accepted) |
| `b1-3-20261030-62-S5-ii` | 526 s | 3.89 GB | **failed**  |
| `b1-3-20261030-63-S5-R` | 464 s | 3.89 GB | **failed**  |
| `b1-3-20261030-64-S1-G` | 510 s | 1.78 GB | solver 461 s, 10 passes (3 accepted) |
| `b1-3-20261030-65-S1-ii` | 881 s | 1.78 GB | solver 834 s, 10 passes (3 accepted) |
| `b1-3-20261030-66-S1-R` | 940 s | 1.78 GB | solver 896 s, 10 passes (3 accepted) |
| `b1-3-20261030-67-S2-G` | 5665 s | 7.13 GB | solver 5320 s, 10 passes (4 accepted) |
| `b1-3-20261030-68-S2-ii` | 5086 s | 7.34 GB | solver 4827 s, 10 passes (4 accepted) |
| `b1-3-20261030-69-S2-R` | 5090 s | 7.32 GB | solver 4842 s, 10 passes (4 accepted) |
| `b1-3-20261030-70-S4-ii` | 795 s | 2.59 GB | solver 714 s, 10 passes (2 accepted) |
| `b1-3-20261030-71-S4-R` | 1648 s | 2.70 GB | solver 1554 s, 10 passes (3 accepted) |
| `b1-3-20261030-72-S5-ii` | 2296 s | 3.89 GB | solver 2153 s, 10 passes (2 accepted) |
| `b1-3-20261030-73-S5-R` | 2039 s | 3.89 GB | solver 1890 s, 10 passes (2 accepted) |
| `b1-3-20261030-74-posthoc-gains` | 536 s | 1.10 GB |  |
| `b1-3-20261030-75-compare` | 4 s | 0.37 GB |  |
| one S4 task, cProfile (3 attempts while optimising) | 29–31 s | – | 896 hand-bins |
| `tests/test_b1_pointing_selfcal.py` | about 10 s | – | 18 tests |
| 2026-10-31 scratch diagnostics: `linesearch.py` (twice, F2), `stefcal_diag.py` (cap sweep, then with polishing), `conv.py` (toy), `halvings.py` (F3, F2, S4) | about 2–10 min each | – | not timed; scripts in `-74-posthoc-gains`, the F2 ones rerun there with a log |
| F2 G smoke fit (4 passes, scratch), F2 simulation smoke | 3 min, 25 s | – | not timed; the first showed the slow convergence |
| partial `compare` dry runs (twice) | seconds | – | not timed |
| `bash tools/check-all.sh` | 17:35.65 | 1.74 GB | **overall: PASS**; pytest 679 passed, 9 skipped in 153.2 s; wall includes waiting for the host lock behind other tasks; log `outputs/b1-3-20261030-check-all.log`; ran on the code of the final commit (afterwards only this table changed) |

## For the coordinator

- **Shared files.** None edited. Added: `research/b1-3-pointing-selfcal.md`,
  `research/results/b1-3-pointing-selfcal.json`,
  `python/rang/pointing_selfcal.py`, `examples/b1_survey_rerun.py`,
  `examples/b1_pointing_selfcal.py`, `tests/test_b1_pointing_selfcal.py` (18
  tests; the JAX test skips without jax). Changed: `python/rang/beam_identifiability.py`
  (new functions only). No Rust: no `pub mod` or PyO3 change. No CLI receipt
  writers, so main is not merged.
- **`STATE.md`**, new top entry:

  > B1-3 pointing self-calibration against both baselines (big plan wave 3),
  > 2026-11-02 (implemented; measured;
  > [b1-3-pointing-selfcal.md](b1-3-pointing-selfcal.md)). Protocol frozen
  > first, two labelled amendments (the gains must be solved exactly: Gauss–Newton
  > polishing after StefCal; the beam frequency of the simulations). Survey rerun
  > with a per-channel bandpass and per-antenna beams: the snapshot common
  > pointing goes on S2, S3 and S4 (gate G3a: ρ ≤ 8e-9 for a diagonal beam on the
  > 1830 point); per-antenna pointing and squint survive (S4 60/60, S2 52/53 x,
  > 48/53 y); per-scan common pointing and ellipticity survive on the track; width
  > fails where it would be fitted. Fits in one solver (profiled Levenberg–Marquardt,
  > same nuisances): gains-only, physical pointing self-calibration (ii), and the
  > rang method R (selected from its own first pass). **Overall negative under the
  > frozen rule; B1 closes null.** On simulations pointing self-calibration works
  > (F2: 0.62′ → 0.054′, held-out −3 %, faint outer-source errors down 2.6×), and R
  > matches (ii) there (F3: better offsets, 0.110′ against 0.173′, held-out equal).
  > On the fixture R beats the SARAO/SKA Gaussian fit (0.357′ against 0.634′) but is
  > worse than (ii) (0.200′), because declining an axis holds a real offset at zero.
  > On real ESO137 and 1934 data neither arm measures pointing with B1-2's model:
  > offsets to 24′, squint at 10–140σ, sky-frame structure, all arms unconverged at
  > 10 passes; S4's negative label is a cost-clause ratio (2.18) from (ii)'s free
  > rejected trials. Archive `results/b1-3-pointing-selfcal.json`.
- **`research/README.md`** index entry:

  > New, 2026-11-02: B1-3, [pointing self-calibration](b1-3-pointing-selfcal.md):
  > overall negative, B1 closes null. Works on simulations (0.62′ → 0.05′), selection
  > adds nothing over fitting every antenna, and with the self-calibrated ESO137
  > model neither arm measures pointing on real data.
- **`big-plan.md`**, wave 3: "B1-3 done 2026-11-02 (`b1-3-pointing-selfcal.md`):
  overall negative under the frozen rule, B1 closes null. Rerun: snapshot common
  pointing goes, per-antenna, squint and the track's directions survive. (ii) and R
  work on simulations and match; R beats (i) and loses to (ii) on the fixture; the
  real-data fits are limited by the field model. Reopening needs a deeper ESO137
  model (user item) and regularised gains."
- **`tool-timings.md`**: the rows of the timings table above.
- **Upstream observations.** RATT: nothing new beyond B1-2's; the ESO137 subset's
  ANTENNA has 61 antennas without m014, m017, m032 (read by opcode scan). LUNO's
  ANTENNA table has 56, without m006, m008, m015–m017, m028, m034, m060.
  caracal-pipeline, saopicc: nothing. Non-RATT: *SARAO holography release*: at
  full-band sensitivity the per-antenna beams are needed for pointing below about
  0.2′ (array average 0.18′ against 0.054′ RMS on a simulated track); informational.
- **User items.** The catalogue decision (SUMSS, RACS) for the ESO137 model stays
  open and is now the first condition for reopening B1 on real data. Whether B1's
  rule should stand as frozen on the fixture clause is a question for a new
  protocol, not this one.
- **Ignored output directories** (none committed; ESO137 CC BY 4.0, holography
  CC BY-NC 4.0; total 1.3 GB):

  | Dir under `outputs/` | Size | Keep? |
  | --- | ---: | --- |
  | `b1-3-20261030-33-sim-F3`, `-34-sim-F2` | 61 MB, 274 MB | can be deleted (deterministic, 1–2 min each) |
  | `b1-3-20261030-06-sim-F3`, `-07-sim-F2` | 61 MB, 274 MB | superseded; `-07` is needed only to rerun post hoc 1 |
  | `b1-3-20261030-08-fixture` | 82 MB | keep `fixture.json`; the extracted fixture can go |
  | `b1-3-20261030-01…-05-rerun-*` | small | keep (`survey.json`) |
  | `b1-3-20261030-35…-45`, `-58`, `-61`, `-64…-73` (`arm.json`, `heldout.npz`) | about 500 MB | keep until merged (the paired calls need `heldout.npz`) |
  | `-10…-15`, `-46`, `-59`, `-60`, `-62`, `-63` | small | superseded or failed runs, kept with logs |
  | `b1-3-20261030-00-probe-names`, `-74-posthoc-gains`, `-compare-spec.json`, `-check-all.log` | small | keep |
- **Scratch.** `/home/gijsm/Build/tmp/20261030-b1-3/` is deleted; the diagnostic
  scripts were copied into `outputs/b1-3-20261030-74-posthoc-gains` first.
