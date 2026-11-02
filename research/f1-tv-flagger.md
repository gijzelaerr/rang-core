# F1: a self-supervised flagger trained on the total variation of calibrated gains (protocol)

Task F1 of [big-plan.md](big-plan.md) ("Next, decided by the user 2026-11-02"). Protocol written
2026-11-02 on branch `f1-tv-flagger`. **Status: proposed.** Nothing here is implemented or trained.
The only measurements are the four sizing probes of section 10, labelled as probes. Results will be
appended under a "Measured result" heading. Nothing above that heading changes after this commit
except through a dated, labelled amendment.

**In one paragraph.** Train a 2,713-weight convolutional network that reads the raw visibility
amplitudes of one baseline and outputs a per-cell flag. Its only training signal is the gain TV of a
calibrator solve, differentiated through the solver's fixed point by an adjoint. At inference there
is no solve and no sky model. It is judged against the Rust Tricolour port on speed and tunable
parameters at comparable quality. Better calibration is not a goal. A saliency test that costs one
solve and one adjoint per case comes first, and the work stops there if TV carries no usable signal.
The negative I consider most likely is stated in section 9.

## 1. Question and success

Landman, 2026-11-02, verbatim: "I thought it was using TV on calibrated gains as a loss function to
train an ML algorithm for flagging (self-supercised style). I wasn't expecting marked improvements in
calibration and imaging, just a faster flagger with fewer tunable parameters." The owner's
instruction is to fulfil that.

**Question.** Can gain TV, with no flag labels, train a model that flags comparably to the CARACal
first pass on an observation it has not seen, materially faster, with fewer parameters a person has
to set?

**Success in Landman's terms** is all three on unseen observations, with the numbers of section 7:

1. comparable quality: recovers injected RFI like the first pass, does not flag more clean data, does
   not worsen the calibration measures;
2. faster: at most half the first-pass wall at matched threads;
3. fewer knobs: one fixed weights file, no per-observation retraining.

Better calibration or imaging is neither required nor claimed.

**The closed experiment does not answer this.** [The verdict](flagging-verdict.md) tested a
two-parameter threshold policy with about ten re-solves per observation. Its "not cheaper" clause
comes from those re-solves, which this flagger does not do at inference.

**Useful negatives**, each a result to record:

- TV gives no usable signal at the array sizes that matter (stop at Stage 1; costs little).
- TV gives a signal, but a network trained on residual-outlier or Tricolour labels does as well. Then
  the fast network is real and TV is not what made it possible.
- A one-parameter amplitude threshold matches the network on quality. Then no ML is needed.
- The weights do not transfer, so the knobs come back as retraining settings.

## 2. The model

**Architecture (frozen).** A per-baseline fully convolutional network on the (time, channel) plane:

| Layer | Channels | Kernel, dilation | Weights |
| --- | --- | --- | ---: |
| 1 | 5 → 8 | 3×3, 1 | 368 |
| 2–5 | 8 → 8 | 3×3, 2, 4, 8, 16 | 4 × 584 |
| head | 8 → 1 | 1×1 | 9 |
| **total** | | receptive field 63×63 | **2,713** |

ReLU activations, 2,672 multiply-adds per cell. It sees one baseline at a time, as the Tricolour
window does, so it does not depend on the array size and can run on 4 or 64 antennas.

**Inputs (frozen): raw DATA and input flags only.** No gains, no model, no solve. This decides the
speed claim: one whole-array solve costs 24.6–28.9 s against the first pass's 45.3 s at four threads
(C1, idle host), so a model that needs residuals cannot reach a factor of two.

Five channels per cell:

- `log|V|` of XX, YY, XY and YX, each with the per-channel median over time removed and divided by
  the baseline's MAD, computed on unflagged cells (flagged cells become 0);
- the input-flag mask.

Amplitude only. Phase is not used, so legitimate gain phase cannot change a flag at inference.

**Output.** A soft per-cell weight `a = sigmoid(logit / T)` in training, multiplying WEIGHT_SPECTRUM
in all four correlations. At inference a mask, `a < 0.5`, uniform over correlations (as Tricolour's
final flags are). Input flags are immutable lower bounds: `a` is forced to 0 there. Inference runs in
a Rust kernel with `f32` weights; JAX and Rust outputs must agree to 1e-4 in `logit` on the
validation set.

**Pipeline around the network, shared by both arms.** `flag_nans_zeros`, the two shipped static
masks, `flag_autos`, `combine_with_input_flags`. The network replaces the `sum_threshold` and
`uvcontsub_flagger` steps only. The static masks are knowledge about the MeerKAT band that a
translation-invariant network cannot have, so they are counted on both sides.

**What "tunable parameters" means here.** Weights are not tunable: nobody sets them. Tiers:

| Tier | Meaning | First pass | This flagger |
| --- | --- | --- | --- |
| T1 | must be set or chosen to flag an observation | 21 kinds of keyword (72 keys, 96 scalar values, 31 distinct task/key/value triples); 12 steps in order; 2 mask files (probe P1) | 2 mask files with `uvrange` (shared), the weights file; the threshold is fixed at 0.5 |
| T2 | must be set to retrain | none | 13: budget B, support floor, 2 penalty weights, time and frequency solution interval, time/frequency TV balance, Adam rate, number of refreshes, refresh interval K, batch size, window size, anneal end point |
| T3 | architecture | none (the step order is its analogue, counted in T1) | 5: inputs, depth, filters, kernel, dilations |

Two things keep this honest:

- Most users run CARACal's YAML unchanged, so "21 kinds" is what exists and what a tuner faces, not
  what everyone touches. CARACal does ship several variants (first pass, second pass, mild, soft,
  target), which is evidence that the numbers get tuned per use. The mild variant has 67 keys and 88
  values.
- T2 and T3 total 18. **If the weights do not transfer, T2 and T3 become user-facing, and 18 against
  21 is not a claim worth making.** The "fewer" claim stands only with one fixed weights file across
  the test observations (P in section 7).

## 3. The loss and its gradient

**Loss (frozen).** On one calibrator scan, with `g*(a)` the solver's fixed point at weights `a·w`:

```
L(a) = TV_fs(polar(g*(a))) / TV_fs(polar(g*(1))) + 10 · max(0, f(a) − B) / B + 10 · support(a)
f(a) = 1 − mean a over cells unflagged at input;   B = 0.10
support(a) = mean over gains of max(0, 8 − Σ_cells-of-gain a)² / 64
```

`TV_fs` is the existing anisotropic Frobenius TV (`src/tv.rs`, `rang.core_policy.gain_tv`) on the
fixed edge support and fixed scale `s0` of the unit-weight solve, after the polar gauge on a
reference antenna. There is no linear flag cost. The verdict's `2f` helps explain why it accepted so
little: on the injection pilot the TV gain from the perfect mask was at most about 1 % at 1 %
occupancy, against a 2 % penalty. The network pays for flagging only through the budget and through
the rise of noise TV when data go (section 4).

**Gradient (frozen): implicit differentiation at the fixed point, in a two-stage scheme.**

The solve is independent per interval (2 integrations × 32 channels, so at most 64 cells per
baseline). With `F_b(g_b, a) = ∇_{g_b} χ²_b = 0` the stationarity of interval `b`, and
`H_b = ∂F_b/∂g_b`:

```
λ_b = H_b⁺ ∂L_TV/∂g_b                       one solve per interval
s_c = ∂L_TV/∂a_c = −λ_b · ∂F_b/∂a_c         one term per cell, using only g_p, g_q and the residual r_c
```

TV couples neighbouring intervals only through its own gradient `∂L_TV/∂g_b`, so the adjoint needs
no global system.

Why this and not the alternatives:

- **Not unrolled.** The solver is Rust, and 65 Anderson iterations over the whole array would hold
  too many JAX tapes. The qp weight swap of QuartiCal issue 452 changes the iteration path but not
  the fixed point ([l5-solver-science.md](l5-solver-science.md)), which is an argument for depending
  on the fixed point alone. Unrolling is kept as a small-problem check.
- **Not a surrogate of TV.** A surrogate would test the surrogate.

**Two stages, alternating.**

1. Refresh: run the network over the scan; Rust solve at `a·w`, `options="anderson=3"`, cap 100;
   compute every `s_c`.
2. Fit: K = 20 Adam steps (rate 1e-3) on `Σ_c s_c a_θ(x_c)` plus the budget and support terms, on
   batches of 16 windows of 32 × 256 cells, with `s_c` held fixed.

200 refreshes, `T` from 1 to 0.25 geometrically. Each refresh logs the actual change of `L` against
the one predicted by the fixed `s_c`. If actual and predicted disagree in sign on more than a third
of refreshes after the first 20, K halves once, by dated amendment.

**Which code.**

- *Forward:* the Rust solver, unchanged (`rang.core.solve_complex`). `anderson=3`, because only 83 %
  of whole-array gains converge at the plain cap of 50, and implicit differentiation requires a real
  fixed point. Intervals with an unconverged gain are excluded from `L` and counted. The solver has
  no warm start today; adding one is not in scope unless Stage 4 is too slow.
- *Adjoint:* JAX reference path (`enable_x64`, as in `python/rang/pointing.py`). `H_b` is matrix-free,
  a `jvp` of the `grad` of `χ²_b`, solved with MINRES, batched over intervals. A hand-written Rust
  adjoint (`core/src/tvgrad.rs`) follows only if JAX misses the Stage 4 budget, and must then match
  JAX within the bounds below.
- *Network training:* JAX. This extends the JAX exception in AGENTS.md (owner question 5). Inference
  is Rust.

**Traps, written down.**

- `H_b` is singular along the gauge: U(2) for an unpolarised model, smaller for a polarised one.
  Tree-shaped bins are further underdetermined ([flagging-luno-support.md](flagging-luno-support.md)).
  The polar-gauge TV is gauge-invariant, so `∂L/∂g_b` has no component in the null space; MINRES then
  returns the right `λ_b`. This is checked, not assumed.
- `H_b` must be the exact Hessian including the `r_c` term, not the solver's diagonal Gauss–Newton
  block. Using the solver's block would give a wrong gradient that still looks plausible.
- The polar factor by SVD has an unstable derivative when singular values nearly coincide, and a
  reference gain close to a scalar times a unitary is exactly that. Use the closed 2×2 form
  `U = G · (GᴴG)^(-1/2)` with `sqrt(A) = (A + √det A · I) / √(tr A + 2√det A)`.
- The gain-flag ladder is discrete: hold it fixed at the solution (stop-gradient) and count what it
  flags.
- TV is not differentiable at a zero edge. Take the subgradient 0; count such edges.

**Validation against finite differences (Stage 1a, all gates frozen).** On a 12-antenna subset of
F-SIM and of the LUNO slice, solved to `stop_criterion=1e-13`, stop fraction 1.0, up to 5,000
iterations:

| Check | Pass |
| --- | --- |
| JAX Gauss–Newton polish started from the Rust solution: baseline products `G_p G_q^H` | relative change ≤ 1e-8 |
| `∂L/∂g_b` projected on the gauge directions | ≤ 1e-8 of its norm |
| Homogeneity. Rescaling all weights of an interval leaves `g*` unchanged, so `Σ_c a_c s_c = 0` per interval | ≤ 1e-7 of `Σ|a_c s_c|` |
| Central differences, ε = 0.02 and 0.01 (Richardson), 300 random cells above the difference noise floor | median relative error ≤ 1 %, 95th percentile ≤ 5 %, correlation ≥ 0.999 |
| Same, 30 contiguous patches | median relative error ≤ 1 %, 95th percentile ≤ 3 % |
| Unrolled JAX Gauss–Newton (200 iterations from the solution) against implicit | median relative error ≤ 1 % |

Weights are `f32` in the solver, so ε well below 1e-3 is not meaningful. The noise floor is measured
by repeating the difference at two solver tolerances. One round of fixes is allowed. If it still
fails, stop and report.

## 4. Trivial solutions, guards and the existing evidence

**Ways of lowering TV without flagging RFI.**

| Trap | Guard | Test (run in Stage 4 unless stated) | Pass |
| --- | --- | --- | --- |
| Flag everything, or empty gains until edges vanish | fixed edge support and fixed `s0` of the unit-weight solve; budget B; support floor | G1, B removed, training scan | reported, not a gate; shows what the budget is holding back |
| Uniform down-weighting of an interval is free, because `g*` is scale-invariant | `f(a)` counts removed weight, not its distribution; the output ends as a mask | homogeneity check, Stage 1a; G2, soft against hard: re-solve with the hard mask | TV_fs(mask) ≤ TV_fs(no flags) on the training scan; otherwise stop |
| Flag noise to fill the budget | none beyond B; noise TV rises as data go | G3, train on an RFI-free F-SIM scan | final mask ≤ 0.5 % of cells |
| Learned noise or chance | | G4, fit with `s_c` permuted between intervals | recall ≤ untrained arm's + 0.05 |
| Carve out a real sky signal the model lacks | no sky at inference, so only tests can show this | G5, F-SIM test scan with an unmodelled spectral line (peak 20σ per cell, 5 channels, compact source, on every baseline) | flagged fraction in line cells ≤ first pass's + 0.05, and ≤ 2 × background |
| Carve out a real gain change, which TV also dislikes | no gain input at inference | G6, 5 % amplitude and 0.1 rad phase step on one antenna mid-scan, and strong smooth phases | flagged fraction around the step ≤ background + 0.05; masks trained with and without smooth phases agree ≥ 0.95 Jaccard |

G5 and G6 run on an observation not used in training. [Flagging-findings](flagging-findings.md)
already showed smooth receiver phases changing TV-guided decisions, and signed sources being absorbed
by calibration.

**The evidence against, without softening.**

- Lower gain TV did not consistently mean better held-out prediction ([flagging.md](flagging.md)).
- On the fixture injections ([flagging-injections.md](flagging-injections.md)), strength-10
  contamination at 0.5–1 % occupancy raised TV by only 0.8–1.4 %. The injection-mask oracle lowered TV
  in all three strength-10 cases but **raised it in two of three strength-3 cases**, since removing
  data adds solution noise. That is four antennas.
- On LUNO, model error goes mostly to the residual and not to the gains (L1-M). The gain-TV map
  explains 0.35 % of the log-variance of the closure-TV map, and the closure map is where the GNSS
  structure is (C1).
- LUNO's input flags have already removed most RFI: 99.6 % and 99.8 % of the cells in the GNSS bins
  (A1).
- A policy with re-solves never selected a TV-guided mask anywhere.

**Dilution, by arithmetic (not measured).** With `n_c` cells per baseline in an interval, the gain
noise is `σ_g ≈ σ / (|M| √((N−1) n_c))`. An RFI patch of amplitude `A` on a fraction `φ` of the
interval's cells moves the gains by:

| Injection | `δg/σ_g` | N = 4, n_c = 64 | N = 56, n_c = 64 |
| --- | --- | ---: | ---: |
| one baseline | `(A/σ) φ √(n_c/(N−1))` | 4.6 φ A/σ | 1.08 φ A/σ |
| all baselines of one antenna | `(A/σ) φ √((N−1) n_c)` | 13.9 φ A/σ | 59 φ A/σ |

So a single-baseline carrier at 10σ in 4 of 32 channels (φ = 1/8) is about 1.4 σ_g on the whole
array: visible but weak. A single-baseline, single-cell 10σ spike is 0.17 σ_g: invisible, whatever
the gradient method. Antenna-local RFI is the best case. The fixture's numbers do not carry over; its
single-baseline response is 4.3 times larger.

**Two structural reasons TV may disappoint (derived; Stage 1 measures them).**

- *Information reaches a cell only through its residual.* `s_c = −λ_b · ∂F_b/∂a_c` is linear in
  `r_c`, projected on an adjoint direction. So at the level of one cell, TV saliency cannot be
  expected to rank better than the residual outlier score. Its possible value is different:
  stochastic gradients average `s_c` over many cells sharing a feature pattern, and TV ignores
  outliers that do not disturb the gains. That is why the go/no-go test below is on class means and
  patches, and why ranking worse than the residual score does not by itself stop the work. It
  determines what may be claimed (section 7).
- *TV has a dead zone.* Along a monotone sequence TV depends only on the end points. Where a gain
  drifts smoothly by more than a perturbation, successive edge directions line up, the interior
  contributions to `∂L/∂g_b` cancel, and the first-order signal vanishes. Where gains are
  noise-dominated, edges zigzag and the cancellation is partial. Probe P4 finds the four-station slice
  closer to noise-like (median cosine of successive edges −0.35 to −0.43; white noise gives −0.5), but
  the whole array has about 4 times lower noise and may sit in the dead zone. A squared-difference
  variant has no dead zone. It is computed beside TV in Stage 1 and not used unless the owner agrees
  (owner question 3).

**The go/no-go test (Stage 1b, frozen). No training.** Cost: one solve and one adjoint per case.

Cases: five morphologies (narrowband persistent; time burst; antenna-local narrowband;
**single-baseline narrowband**; drifting carrier), strengths 0, 3, 10, 30, 100 in units of the
measured per-baseline noise (scaled MAD of channel differences, not inverse weights: LUNO's weights
overstate the noise, χ² about 0.2), three seeds, on two datasets at full array: F-SIM and LUNO
1934−638 with injections on training cells. Saliency `s_c` is positive where down-weighting lowers
TV. Patches are the 8 × 8 tiles of a baseline's plane, scored by the mean of `s_c`.

**GO** requires all of:

| Gate | Statistic | Pass |
| --- | --- | --- |
| A | Stage 1a validation | all pass |
| B1 | strength 10: mean `s_c` over injected cells, against clean cells of the same intervals (t from a bootstrap over intervals) | t ≥ 5 on ≥ 3 of 5 morphologies, on each dataset |
| B2 | strength 10: patch AUC against the injection mask | ≥ 0.80 on the same ≥ 3 morphologies |
| C | strength 0, same mask: B1's statistic | \|t\| < 3 on all five (a null that must stay null) |
| D | re-solve with the injection mask removed: TV_fs lower than contaminated | ≥ 80 % of strength ≥ 10 cases, on each dataset |
| E | LUNO, no injection: mean `s_c` by amplitude bin of the input z-score | top bin (z ≥ 10) positive with t ≥ 5 |

**NO-GO** means stop and write it up. That is outcome D: "TV is not a usable training signal at
MeerKAT array scale".

Reported, not gating: the same tables for the residual z-score; the patch AUC of TV²; cell-level AUC;
AUC against first-pass additions away from input flags (section 6); the array-size curve at 8, 16,
32, 64 antennas; and the median cosine of successive edges, which measures the dead zone. If only TV²
passes, stop and ask the owner.

If the residual score beats TV saliency everywhere, proceed to Stage 2, whose arms need no TV. The
stage report says so in its first paragraph, and the owner decides whether Stage 3 still runs. The
reason this is not an automatic stop is the first structural point above: it is what the mathematics
predicts even if TV can train, so it would not test Landman's idea.

## 5. Data

Split by observation first, cells second. Tricolour labels are never used for F-TV's training.

| Set | What | Role | Today? |
| --- | --- | --- | --- |
| **F-SIM** | New, below. 6 simulated observations | train 3, validation 1, test 2; truth known | yes, to be built |
| **LUNO 1934−638** | L1's whole-array cell, 41,786 rows × 2,048 channels, 60.0 % flagged at input, on disk | go/no-go; optional training (F-TV-LUNO); cost | yes |
| **LUNO 1830−211** | L2's cell, 15,400 rows, 46.6 % flagged | test of F-TV-LUNO, with and without injections. **Same schedule block as 1934−638, so this is a split by scan and not by observation.** | yes |
| **Public fixture** | scan 9 of `outer_scans.zip`, 4 antennas, 140 rows, published flags | a different real observation; inference, agreement and cost only; too small to train on | yes |
| **ESO137 S4 pilot** | `ms1_target_subset.zarr`, 61 antennas, 500 channels, CC BY 4.0 | the only other multi-antenna real observation today. Target field, MODEL_DATA empty, so inference and agreement only, against the target first-pass YAML. Exploratory: not gating, because training is on calibrators | yes |
| **Native L-band (L3)** | the observer's offer; nothing has arrived. MK1's loader is ready | the decisive real test (below) | **waits** |

**LUNO is processed**: CASA flags, QuartiCal weights, unlogged models ([verdict](flagging-verdict.md)
section 2). Every LUNO call is conditional on that. Its residual RFI is what survived earlier
flagging, so it tests "no harm" and transfer, not recovery.

**F-SIM.** The DF5-O field cannot be reused: 16 channels of 48 MHz and 120 s dumps are incompatible
with windows up to 128 channels, and it has no gain corruption. It keeps its method
([df5o-deconv-oracles.md](df5o-deconv-oracles.md)): `data/meerkat.itrf.txt`, core prediction,
radiometer noise. New simulator, `examples/simulate_f1_field.py`:

- 64 antennas, 32 dumps of 8 s, 2,048 channels of 208.984 kHz over 1070–1498 MHz: LUNO's window, so
  costs compare directly. About 4.2 GB of DATA per observation, 25 GB in all, under
  `/mnt/d/rang/data/f1/`. Only one test observation is also written as an MS, for AOFlagger.
- Sky: one calibrator at the phase centre, 5–20 Jy by seed, with a model incomplete by a few faint
  sources, so the residual is not ideal.
- Noise: σ = 0.22 Jy per correlation, from SEFD 400 Jy, about the same as `0.5 × √0.2` from LUNO's
  weights and χ².
- Gains: per antenna and correlation; smooth bandpass, amplitude and phase drift; small leakage.
  Seeded.
- RFI, each observation a draw: persistent narrowband, intermittent carrier, broadband burst, pulsed
  comb (DME-like), antenna-local and single-baseline carriers, strengths log-uniform 1–1000σ, stronger
  on short baselines by a decorrelation law, total 1–8 % of cells. The drifting carrier is left out
  of the training observations and appears only in test: it is the held-out morphology. The second
  test observation has a 5 Jy calibrator, a different hour angle and 58 antennas.
- No input flags, which gives Tricolour's flags without the growth artefact of section 6.
- An RFI-free copy of every observation is kept for scoring: held-out cells are flagged while solving
  and scored against their RFI-free values.

**Possible today:** Stages 1–5 on F-SIM, LUNO, the fixture and ESO137. **Waiting for L3:** any
statement about real, unprocessed RFI. The frozen weights run on it unchanged, without retraining,
when it arrives.

## 6. Comparators

| Arm | What | Why |
| --- | --- | --- |
| **T** | Rust Tricolour port ([core-d-tricolour.md](core-d-tricolour.md), parallel since [P3](p3-sumthreshold.md)), first pass, `mk_rfi_flagging_calibrator_fields_firstpass.yaml`, CARACal `8f7bb363` | the bar |
| T-mild | `calibrator_mild_flagging.yaml` | how far two shipped strategies differ |
| **N** | no added flags | power check on every quality measure |
| **Z** | threshold: flag where any correlation's input z-score (section 2) exceeds τ = 10, the YAML's `outlier_nsigma` | the cheap control with one knob |
| **U** | the network with random weights | chance, and the cost of the kernel |
| R | residual z-score threshold, τ = 10, as `residual_features`. Costs a solve, though a pipeline that solves anyway pays nothing extra; report both | is the solve-free route needed? |
| **F-TV** | section 3, trained on F-SIM, 3 seeds; the median seed by validation loss is the frozen weights file | the method |
| F-TV-LUNO | same, one seed, trained on LUNO 1934−638 alone | Landman's setting on real gains; test on 1830−211 |
| F-RES | same network fitted to R's mask on the F-SIM training observations | same speed, labels from a solve, no TV |
| F-IMI | same network fitted to T's mask on the same observations | distillation; only ever a control |
| A | AOFlagger 3.5 `tuned` from [a-flag-aoflagger.md](a-flag-aoflagger.md), one thread | cost bar, and quality where it runs |
| O | the injection mask itself | ceiling for gain error |

**T's agreement is contaminated, and the measure has to allow for it.** A-FLAG found that the first
`sum_threshold` step of the first pass is mostly growth around input flags on these controls: 93,341
new flags fall to 224 when only the input flags leave the windows. So agreement with T on LUNO is
agreement with that artefact as much as with RFI. Every agreement number is reported on all cells and
on the **far stratum**: no input flag within ±3 dumps and ±8 channels on the same baseline
(`time_extend` 3; windows up to 8). If the far stratum holds under 5 % of unflagged cells, the
agreement call on that set is undecidable. On F-SIM there are no input flags, so the comparison is
clean.

## 7. Measures and decision rule (frozen)

All on observations not used for training or validation. T is the reference.

**Quality on F-SIM test observations, with truth.**

| Measure | Beats | Matches | Worse |
| --- | --- | --- | --- |
| Q1 recall of injected cells with per-cell amplitude ≥ 10σ, per morphology and overall | ≥ T + 0.05 | within ±0.05 | < T − 0.05 |
| Q2 false flags: cells outside the truth mask dilated by one cell, as a fraction of clean cells | ≤ T − 0.01 | within ±0.01 | > T + 0.01 |
| Q3 gain-product error against the simulated truth, as a ratio to T | ≤ 0.99 | 0.99–1.01 | ≥ 1.01 |
| Q4 held-out MSE and residual RMS (`dirty − peak × PSF`), ratio to T: the verdict's margin | ≤ 0.99 | 0.99–1.01 | ≥ 1.01 |

Recall is also tabulated at 3σ and by strength decade, not gated.

**The power rule.** The evidence says held-out error barely sees flagging: on LUNO `original` and T
differ by 0.06 %. A flagger that does nothing would "match". So: **Q3 or Q4 on a dataset is
undecidable, not "matches", unless N is ≥ 1.01 × T on that measure and dataset.** I expect F-SIM to
pass this and LUNO to fail it. On LUNO the only available statement is "not worse": F-TV ≥ 1.01 × T
on Q4 is a failure, and anything else says nothing about quality. Quality therefore rests on truth
(Q1, Q2) and on the simulated Q3.

**Agreement with T**, on real data, far stratum. Jaccard of added cells:

- LUNO 1830−211 and the fixture: J ≥ 0.40. The mild strategy added 299,575 cells and first pass
  613,116 on L1, so J(mild, first pass) cannot exceed 0.489 by counts. Two shipped strategies are that
  far apart.
- J is a bar for "behaves like a flagger of this family", not truth. Failing it blocks a real-data
  claim but not a simulated one.
- F-SIM: J reported, not gated. Q1 and Q2 decide.

**Sky.** G5 and G6 of section 4 pass.

**Generalisation.** One weights file, no knob changed. Q1 and Q2 on each F-SIM test observation within
0.05 and 0.01 of the validation observation; the held-out drifting carrier reaches Q1 matches; LUNO
with injections reaches Q1 matches using weights trained only on F-SIM.

**Cost.** Same cells in memory to mask in memory; idle host (load ≤ 2) or a recorded load; three
repeats, arms alternating, median reported:

| | Beats (material) | Matches | Worse |
| --- | --- | --- | --- |
| C1 wall against T at 4 threads and at 1 thread | ≤ 0.5 | 0.5–1.1 | > 1.1 |
| C2 peak RSS against T | ≤ 0.8 | 0.8–1.2 | > 1.2 |
| C3 wall against A, one thread, the same cells | ≤ 0.5 | 0.5–1.1 | > 1.1 |

C3 is needed because at matched threads the port costs 1.3–2.1 × AOFlagger's strategy time in A-FLAG.
Beating only the port might not beat the state of the art on speed. Training cost is reported
separately (wall, CPU, GPU, RSS, solves) and never counted against inference.

**Parameters.** P: F-TV counts T1 only, if and only if Generalisation passes with no retraining.
Otherwise T1 + T2 + T3. P holds if that count is under half of the first pass's 21 kinds.

**"Meets Q"**: Q1 and Q2 match or beat, Q3 not worse and decidable, Q4 not worse.

**Outcomes (first that applies).**

| Outcome | Condition | What it says |
| --- | --- | --- |
| **D** | Stage 1 NO-GO | TV carries no usable training signal at array scale. Stop. |
| **E** | Stage 3 fails, or G2, G3, G4, G5 or G6 fails | TV can be differentiated but does not train a sound flagger. |
| **F** | F-TV does not meet Q, or Generalisation fails, or C1 > 1.1 | Not comparable, or not faster. |
| **G** | Z meets Q and C1 ≤ 0.5 | A threshold does it; ML is not needed. |
| **B** | F-TV meets Q and C1 ≤ 0.5, but F-RES or F-IMI is not worse on Q1, Q2, Q3 | Fast network, yes; TV not shown necessary. Its one remaining advantage is needing no labels. |
| **A** | F-TV meets Q, C1 ≤ 0.5, C2 not worse, P, and beats Z, F-RES and U on Q1 or Q2 | **Landman's wish is met** on simulated RFI and processed real data. |
| **H** | anything else, for example C1 between 0.5 and 1.1 | Comparable, not materially faster. |

**A positive claim under the novelty rule** needs more than A. A software win against a toy baseline
establishes nothing ([AGENTS.md](../AGENTS.md)):

- Outcome A, **and** C3 ≤ 0.5, and agreement J ≥ 0.40 on real data;
- **and real, unprocessed data.** Until L3 runs, the strongest permitted sentence is: "on simulated
  RFI and on processed L-band data, comparable to the CARACal first pass at under half its wall". That
  is a conditional result, not a claim of a better flagger;
- with every negative arm of this table reported beside it.

Better calibration or imaging is not claimed under any outcome. If a Q3 or Q4 call is "beats", it is
reported and is not the result.

## 8. Cost and scope

| Stage | Work | Effort | Wall (4 threads) | Stop if |
| --- | --- | --- | ---: | --- |
| 0 | This protocol; owner decides section 11 | done | – | owner says so |
| 1a | JAX adjoint, finite-difference validation | 1 session | ≤ 30 min | validation fails after one round of fixes |
| 1b | F-SIM builder, injections, **go/no-go** | 1 session | ≤ 2 h | **NO-GO: outcome D** |
| 2 | Rust inference kernel with JAX parity; Z, U, R, F-RES, F-IMI; first look at Q1, Q2, C1 on validation | 1–2 sessions | ≤ 4 h | C1 > 0.75 for U on a real window: no speed to win. Z meets Q on validation: report to the owner before spending on TV |
| 3 | TV overfit test: train on one F-SIM observation, evaluate on it | 1 session | ≤ 4 h | recall < 0.50 at ≥ 10σ on its own training scan: outcome E |
| 4 | Full F-TV (3 seeds), guards G1–G6, F-TV-LUNO | 1–2 sessions | ≤ 4 h per seed; ≤ 20 h in total | a guard fails: outcome E |
| 5 | Frozen test observations, real data, cost; verdict; archive | 1 session | ≤ 2 h | – |
| 6 | L3 on the frozen weights, on arrival | ½ session | ≤ 1 h | – |

If it stops at the go/no-go, this costs about 2 sessions. All stages about 6–8.

**At most one change of hyperparameters** in the whole protocol, by dated amendment, on validation
only, before any test observation is opened. Test observations are generated by a script hashed at
Stage 1b and first read at Stage 5.

**One refresh, estimated.** Rust solve about 30 s (one whole-array solve is 24.6–28.9 s; Anderson's 65
iterations against 50 add time); adjoint about 10 s if MINRES takes 30 Hessian products (Stage 1a
measures it); network and fit about 20 s on four CPU threads, at about 1 G multiply-adds per step.
About 60 s × 200 refreshes, so about 3.3 h per seed. All estimated, not measured.

**GPU (RTX 4070 Ti, 12 GB, shared).** Not required. The network part is about a third of a refresh,
and it is the only part a GPU helps. A JAX CUDA wheel for Python 3.14 is not verified here. CPU is the
default; the GPU is used only if already convenient, and its use is reported.

**Disk.** F-SIM under `/mnt/d/rang/data/f1/`; large run outputs under `/mnt/d/rang/outputs/f1-*`.
Nothing large on C:. No venv on D:.

**Owner files** (new unless stated):

- `python/rang/tvflag_adjoint.py`, `python/rang/tvflag_train.py`, `python/rang/tvflag_eval.py`
- `core/src/cnnflag.rs`, with its registration in `core/src/lib.rs` and an FFI entry (edits);
  `core/src/tvgrad.rs` only if needed
- `examples/simulate_f1_field.py`, `examples/f1_saliency.py`, `examples/f1_train.py`,
  `examples/f1_measure.py`
- `tests/test_f1_adjoint.py`, `tests/test_f1_cnnflag.py`
- `research/f1-tv-flagger.md`, `research/results/f1-*.json`, `research/README.md` (one line)
- Weights: `core/data/` or the Python package, once owner question 4 is answered

Not edited: `core/src/solve.rs`, `core/src/sumthreshold.rs`, `python/rang/core_flag.py`, the verdict's
archives.

## 9. What this protocol does not claim

- It claims no better calibration or imaging. It does not reopen the verdict, which stands as tested.
- It claims nothing about target fields, other bands or other telescopes. Training and gating are on
  L-band calibrator scans; ESO137 is exploratory.
- It does not claim TV measures data quality. TV is used as a training signal only; lower TV is never
  used as evidence of quality, because the record shows it is not.
- It does not claim that simulated RFI is realistic. Agreement with real flags is conditional on
  processed data until L3.
- A surviving network has not been shown to be physically interpretable or robust outside its tests.

**A likely negative, stated in advance.** My expectation before any test (a prior, not a measurement)
is outcome D or B. Strong injected RFI should pass the go/no-go on class means, but a cell's
information reaches TV only through its residual, so TV is unlikely to teach anything that a residual
threshold does not teach more directly. The array dilutes baseline-local RFI about 4 times more than
the fixture does. A smooth whole-array solve may sit in TV's dead zone. The existing record gives TV
little support. The most probable useful end is: a small fast network is possible (probe P2 suggests
room for about a factor of ten), and TV is not the reason. That would still answer Landman and would
still give a faster flagger, trained on labels or residuals. Outcome G, a single threshold, is also
plausible on simulated RFI, which is why Z runs before any TV training.

## 10. Sizing probes (labelled scratch, run 2026-11-02, no flagger code)

`outputs/f1-20261102-00-probes/` (`count.py`, `kernel.rs`, `edges.py`, `edges.json`). Host load 5–7.

- **P1, YAML count** (`count.py`, from `outputs/caracal-strategy-inputs-8f7bb363`). First pass: 12
  steps, 72 kwarg keys, 96 scalar values, 21 distinct task-and-key kinds, 31 distinct task/key/value
  triples. Mild: 10 steps, 67, 88, 19, 26.
- **P2, kernel cost** (`kernel.rs`: a standalone `rustc -O -C target-cpu=x86-64-v3` file with the
  architecture of section 2, random weights, median and MAD per input plane, plain threads). Window
  of 1,378 baselines × 32 × 2,048 = 90.3 M cells: 4.38 s at 4 threads; 14.3 s at 1 thread (scaled from
  34 baselines). First pass on L1: 45.3 s at 4 threads (C1, archived, idle host, 85.6 M populated
  cells). So about a tenth, on a busier host, before input packing, the per-channel medians and real
  weights. This says the budget exists. It is not the C1 measure.
- **P3, adjoint block** (NumPy, one thread): 448 × 448 eigendecomposition 16 ms, 512 × 512 28 ms. Dense
  validation of small arrays is cheap; 1,024 whole-array intervals favour MINRES.
- **P4, gain edges on the LUNO four-station slice** (`edges.py`; `core-phase2-inputs-20261029-01`,
  `anderson=3`, 21–23 iterations, 0.02–0.04 s per solve). Full solve against two random half-sets of
  cells; edge noise taken as half the difference of the half-set edges. Time edges: median 0.0079
  against noise 0.0045 (ratio 1.76), 34 % above twice the noise, median cosine of successive edges
  −0.43. Frequency edges: 0.0081, 0.0046, 1.77, 42 %, −0.35. So at four stations the edges are mostly
  noise with some structure. **The whole array was not probed**; Stage 1b measures it.

Not probed, deliberately: saliency, AUC or any training. Those are Stage 1.

## 11. Decisions for the owner before training starts

1. **Pretrained or per-observation?** This protocol takes "faster" to mean a fixed weights file and no
   solve at inference. If Landman meant fitting on each observation, the solves come back and the speed
   target changes. Worth asking him.
2. **Is "comparable" acceptable as defined?** On truth from simulated RFI, and "not worse" on LUNO,
   because LUNO's held-out error cannot separate flaggers.
3. **If only squared differences pass the go/no-go**, is that still what Landman meant? This protocol
   stops and asks.
4. **Weights trained on what?** The frozen file is trained on simulation alone, which keeps shipped
   weights free of data-licence questions. If F-TV-LUNO is much better: may weights derived from LUNO
   (the observer's permission, SARAO acknowledgement) be shipped?
5. **JAX for network training and the adjoint.** AGENTS.md allows JAX for the smooth pointing solver;
   this extends it to training only, with inference in Rust. Is that acceptable?
6. **If the outcome is B**, a fast network fitted to Tricolour's or residual labels: is that a
   satisfactory end for Landman, or is the project only interested if TV does the training?

## 12. For the coordinator

Shared-file lines, verbatim:

- `research/STATE.md`, new top paragraph: "F1, self-supervised gain-TV flagger, 2026-11-02 (proposed;
  nothing trained): [protocol](f1-tv-flagger.md). A 2,713-weight per-baseline network on raw amplitudes,
  trained by the implicit gradient of gain TV through the solver's fixed point, judged against the
  Tricolour port on speed and tunable parameters at comparable quality. A no-training go/no-go comes
  first. Six questions wait for the owner."
- `research/big-plan.md`, "Next, decided by the user 2026-11-02": mark the flagger's protocol as
  written, `f1-tv-flagger.md`, Stage 1 waiting for the owner.
- `research/tool-timings.md`:

  | Date | Tool | Input | Wall | Peak RSS | Notes |
  | --- | --- | --- | --- | --- | --- |
  | 2026-11-02 | F1 probe P2, `kernel.rs` | 90.3 M cells, 4 threads | 4.38 s | not recorded | random weights, load 5 |
  | 2026-11-02 | F1 probe P4, `edges.py` | LUNO four-station slice, 3 solves | 0.25 s | not recorded | `anderson=3` |
