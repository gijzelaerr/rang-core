# F2: a fast supervised RFI flagger for MeerKAT L-band (protocol)

Task F2, branch `fp-f2-flagger` from main `ba65792`. Protocol frozen 2026-11-06 before any simulation,
training or comparison. **Status now (2026-11-07): implemented and measured; outcome F for calibrators and targets; nothing
proposed for `rang-core flag`** ([decision](#decision-frozen-rule-section-6)). **Status at freeze:
proposed; nothing implemented, run or trained.** Results go
under "Measured result"; nothing above it changes except by dated, labelled amendment.

**Amendment 1, 2026-11-06, after f2sim-v and the training observations were built, before the test
observations are built or any arm is scored on them.** The test observations are built by
`python/rang/f2flag_sim.py` sha256 `577deca402fb598c38542a7b44a3199b9ad321fa55aa0998cf08ab7452ec1300`,
`examples/f2_simulate.py` `dc0a0123c54f43e6acf34a7fce325f91b7e399d7646be7337476e40ba3b4833e` and
`python/rang/simtruth.py` `6da60bd467fae4441c07cf8b84ce6c37ec2ecc0266e387ad0b6f28a1cca6a475`, the files
that built f2sim-v and f2sim-1 to -3. The G5 and G6 variants are built by the same files
(`--variant line`, `--variant step`) from f2sim-t1's seeds. No threshold changes.

**Amendment 2, 2026-11-06, post hoc: after Stage 2 on f2sim-v (T, T-mild, N, Z, R, O), before any
training and before the test observations are read.** On validation calibrators N's Q3 (0.0232) is
below T's (0.0318): T's over-flagging costs more than the RFI it removes, so the frozen power rule
(N ≥ 1.01 × T) makes calibrator Q3 undecidable and no arm can "meet Q". Added, labelled post hoc
wherever used: Q3 has power if O ≤ 0.99 × N (removing the true RFI changes the gains); the call against
T is unchanged. Both readings are reported; the frozen one decides the frozen outcome. Nothing else
changes.

**Amendment 3, 2026-11-07, after the calibrator validation of the trained arms, before any test
result was seen: section 7's one change of hyperparameters, used on the flag threshold.**

- *What was seen.* Calibrators, f2sim-v, τ = 0: F-SIM Q1 0.717 against T 0.829 (worse), Q2 0.0048
  against 0.320, Q3 0.0043 against 0.0308. Target validation of the trained arms had not finished.
- *A stopped launch.* The first Stage 5 launch (`f2-20261107-01-stage5-quality`) went on from validation
  to the test observations at 01:39:47 and was stopped at about 01:41 while reading f2sim-t1's
  calibrator scans. Its output went to `/dev/null` and `test1-calibrator.json` was never written: no
  test number was produced or seen.
- *The change.* Per class and per trained arm (F-SIM, F-RES, F-IMI), the flag rule becomes logit > τ.
  τ = 0 unless the arm fails "meets Q" on f2sim-v at τ = 0 (calibrator Q3 read as in Amendment 2). Then τ
  is chosen on f2sim-v only, on the grid 0, −0.5, …, −6: the largest τ with Q1 ≥ T's validation Q1 and
  Q2 ≤ T's validation Q2 + 0.01; if none, the τ with the largest Q1 among those with Q2 ≤ T's Q2 + 0.01
  (if that is −6, the grid floor binds and is reported). U stays at 0, Z at 10.
- τ is fixed with the weights file (recorded beside its sha256); in P it counts under T2, not T1. Parity
  (flag disagreement) and every Stage 5 measure, guards included, use τ.
- If an arm still fails on test, its outcome is F. No second change.
- *Picks* (`f2-20261107-02-amend3`, f2sim-v; every arm failed Q at τ = 0). Calibrators: F-SIM τ = −3.0
  (validation Q1 0.844, Q2 0.0133; T 0.829, 0.320), F-RES −6.0 (floor binds; Q1 0.154), F-IMI 0 (Q1 0.879,
  Q2 0.173; it fails on Q3, which τ cannot fix). Targets: F-SIM −6.0 (floor binds; Q1 0.914, Q2 0.0355; T
  0.990, 0.140), F-RES −6.0 (floor binds; 0.589), F-IMI −0.5 (fallback; 0.814, 0.148). So target F-SIM is
  expected to fail Q1 on test.

Supersedes the route of [F1](f1-tv-flagger.md) (NO-GO, outcome D). Landman, 2026-11-06, verbatim: "The
TV norm was just a suggestion to get around expertly labeled data." One weights file per observatory and
band is acceptable; calibrator and target fields need separate strategies. The goal is F1's: faster than
the Rust Tricolour port, fewer tunable parameters, comparable flag quality. Better calibration or
imaging is not a goal and is not claimed.

## 1. Question

Can one fixed weights file per field class (calibrator, target), trained on labels, flag MeerKAT L-band
data like CARACal's Tricolour strategy for that class (Q1-Q3), at ≤ 0.5 × its wall (C1), with under half
its tunable-parameter kinds (P)?

## 2. Arms

| Arm | What | Role |
| --- | --- | --- |
| **T** | Rust Tricolour port, `core_flag.flag_rows`, CARACal `8f7bb363`: calibrators `mk_rfi_flagging_calibrator_fields_firstpass.yaml`, targets `mk_rfi_flagging_target_fields_firstpass.yaml` | the bar |
| T-mild | `calibrator_mild_flagging.yaml` (calibrators only; CARACal ships no second target strategy) | spread between two shipped strategies |
| N | no added flags | power check for Q3 |
| Z | max over correlations of the input z (section 3, before `asinh`) > 10 | one-knob threshold |
| U | the network with its untrained initial weights (init seed 0) | chance; kernel cost |
| R | residual z > 10: `core_campaign_array.baseline_scores` of the whitened residual amplitude of a `solve_complex` at grid (2, 32), solver defaults. Model: the true model on F-SIM (**privileged on targets**: a real target first pass has no model), MODEL_DATA on LUNO | is a solve needed? |
| **F-SIM** | the network trained on F-SIM truth labels; 3 training seeds per class; the median seed by validation loss is the weights file | **the method** |
| F-RES | the network fitted to R's mask on the F-SIM training observations, 1 seed per class | labels from a solve |
| F-IMI | the network fitted to T's mask (of that class) on the same observations, 1 seed per class | distillation, control only |
| A | AOFlagger 3.5 `tuned`; not run here. A-FLAG's archived numbers ([a-flag-aoflagger.md](a-flag-aoflagger.md)) cited where they cover the same cells | reported, not gated |
| O | the truth mask (amplitude > 0, section 4) | Q3 ceiling |

Every arm except T and T-mild runs inside the **shared wrapper**: the class's YAML with its
`sum_threshold` and `uvcontsub_flagger` steps removed (`flag_nans_zeros`, both `apply_static_mask`
steps with their `uvrange`, `flag_autos`, `combine_with_input_flags`), executed by `flag_rows`; the
arm's flags are OR-ed in. Q1 and Q2 are scored only on cells the shared wrapper leaves unflagged.

## 3. Network (frozen)

F1's architecture with one extra input plane. Per baseline, on the (time, channel) plane of one scan:

| Layer | Channels | Kernel, dilation | Weights |
| --- | --- | --- | ---: |
| 1 | 6 → 8 | 3×3, 1 | 440 |
| 2-5 | 8 → 8 | 3×3, dilation 2, 4, 8, 16 | 4 × 584 |
| head | 8 → 1 | 1×1 | 9 |
| total | | receptive field 63 × 63 | **2,785** |

ReLU; zero padding ("same"). Flag where logit > 0 (probability 0.5), uniform over correlations.

**Inputs.** `F` = cells flagged on input or by the shared wrapper. With `a_c = log|V_c|`:

- planes 1-4, per correlation c ∈ (XX, XY, YX, YY): `z_c = (a_c − med_t a_c(f)) / s_c`, the median over
  unflagged times of each channel, `s_c = max(1.4826 · MAD(a_c − med_t), 1e-3)` over the baseline's
  unflagged cells. **Deviation from F1:** `s` per correlation, not per baseline (cross hands have
  another scale).
- plane 5, the channel profile, broadcast over time: `p(f) = med_t (a_XX + a_YY)/2`, `r = p − runmed₃₃(p)`
  (running median over 33 channels, defined channels only), `z_p = r / max(1.4826 · MAD_f(r), 1e-3)`.
  **New:** the per-channel median of planes 1-4 removes a carrier that is on for the whole scan; plane 5
  restores it.
- plane 6, the mask `F`.

Planes 1-5 are 0 on `F` and pass through `asinh`. Z uses planes 1-4 before `asinh`. Amplitude only.
Network output on `F` is ignored (those cells are flagged already).

**Implementations.** Reference: NumPy features + JAX network (training, `enable_x64` off, float32).
Inference: one Rust kernel computing the features and the network from the same rows, f32. Parity on the
validation observation: |Δlogit| ≤ 1e-4 at the 99.9th percentile and ≤ 1e-3 max; flag disagreement
≤ 1e-5 of cells.

## 4. Data

**F-SIM** (`python/rang/f2flag_sim.py`, `examples/f2_simulate.py`), built from `rang.simtruth`:
`simtruth.jones`, `corrupt`, `sky_coherency`, `target_sky`, `calibrator_stokes`, `rfi_events`,
`rfi_chunk`, and its noise law.

- 2,048 channels × 208.984 kHz over 1070.0-1498.0 MHz (LUNO's window, channels 1024-3071 of the
  4k L-band), 8 s dumps, SEFD 420 Jy (σ = 0.230 Jy per real part).
- 32 antennas per observation: even-numbered `meerkat.itrf.txt` antennas (odd-numbered in test 2).
- Scans: F (J1939−6342, 32 dumps), G (gain calibrator, 16 dumps; flux log-uniform 2-10 Jy, spectral
  index −0.6), T (target, two scans of 32 dumps). Sequence F, G, T, G, T, simtruth's slew. Start UTC per
  observation below; Jones and target sky per seed. F, G and T only (unpolarised calibrators; the
  target's polarised components go through simtruth's P). The polcal field is not simulated.
- RFI: `simtruth.rfi_events` (persistent, intermittent DME and ADS-B, broadband bursts) plus, all through
  `rfi_chunk`'s geometry and baseline decay unless stated, with zero-baseline amplitudes log-uniform
  1-1000 σ:
  - 4-12 narrowband carriers at random frequencies, 1-4 channels, on for the whole scan or for random
    runs of 1-16 dumps;
  - 2-5 antenna-local carriers, 1-8 channels, on every baseline to one antenna, no decay, random time span;
  - 5-20 single-baseline carriers, 1-8 channels, random time span, no decay;
  - 1 pulsed comb, every 5th channel in 1070-1150 MHz, on in alternate dumps for a random run;
  - **test only**, the held-out morphology: 2-4 drifting carriers, 4 channels wide, moving 1-3 channels
    per dump.
  Then every cell with `A = max_c |RFI_c| / σ < 0.1` gets RFI 0 exactly. Truth mask: `A > 0`.
- Stored: DATA, the RFI layer and the truth (complex64, float32) under `/mnt/d/rang/outputs/f2-*`.

| Observation | Role | Seeds (jones, sky, rfi, noise, extra RFI) | Start UTC | Antennas |
| --- | --- | --- | --- | --- |
| f2sim-1, -2, -3 | train | 20262101-05, 20262111-15, 20262121-25 | 2024-08-18T15:00, T19:00, T23:00 | even |
| f2sim-v | validation | 20262131-35 | 2024-08-19T17:00 | even |
| f2sim-t1 | test | 20262141-45 | 2024-08-19T21:00 | even |
| f2sim-t2 | test | 20262151-55 | 2024-08-20T01:00, gain calibrator 2 Jy | odd |

None of these seeds is in `simtruth.SEEDS` or any worktree's simtruth (checked 2026-11-06); they are
registered there. The generator script's sha256 is recorded by amendment before the test observations
are generated; they are first read in Stage 5.

**Training labels.** F-SIM: positive where `A ≥ 3`, negative where `A = 0`, ignored where 0 < A < 3 and
on `F`. F-RES and F-IMI: positive where R's (T's) added flags are, negative elsewhere, ignored on `F`.

**Input-flag augmentation (all trained arms).** Each training window, with probability 0.5, gets
synthetic input flags at an occupancy drawn uniform in 0-0.6: 1-4 channel bands of 8-256 channels, 0-2
time blocks of 1-8 dumps, and with probability 0.05 the whole baseline. LUNO 1934−638 is 60 % flagged at
input; without this the network has never seen a flagged plane.

**Real data.**

| Set | Class | Use |
| --- | --- | --- |
| LUNO 1934−638, whole array (F1's cell: 41,786 rows × 2,048 channels, 60.0 % flagged at input; O-CASA's four stations are a subset) | calibrator | agreement with T; injections; C1, C2 |
| LUNO 1830−211 (15,400 rows, 46.6 %) | calibrator | agreement with T |
| ESO137 `ms1_target.zarr`, row chunk 0 (50,000 rows, 61 antennas), channels 1024-3071 (same 208.984 kHz) | target | exploratory: agreement and C1, not gated |

LUNO is processed (CASA flags, QuartiCal weights); conditional as in F1.

## 5. Measures (frozen)

T is the reference; each class is decided separately.

**Truth (F-SIM test).**

| Measure | Beats | Matches | Worse |
| --- | --- | --- | --- |
| Q1 recall of cells with `A ≥ 10`, overall | ≥ T + 0.05 | ±0.05 | < T − 0.05 |
| Q2 false flags: flagged fraction of cells outside the truth mask dilated by one cell in time and channel | ≤ T − 0.01 | ±0.01 | > T + 0.01 |
| Q3 gain-product error, ratio to T | ≤ 0.99 | 0.99-1.01 | ≥ 1.01 |

Q1 by morphology and by strength decade, and at `A ≥ 3`, reported. Q3: `solve_complex` (grid (2, 32),
defaults) per scan on DATA with the arm's flags; reference the same solve on RFI-free DATA with the
shared wrapper's flags; model the true apparent model (simtruth's P applied). Error =
`‖G_p G_qᴴ − G_p⁰ G_q⁰ᴴ‖_F / ‖G_p⁰ G_q⁰ᴴ‖_F` (2×2 products, all baselines), RMS over intervals valid for
every arm; intervals lost counted. **Q3 is undecidable unless N ≥ 1.01 × T.**

**Meets Q**: Q1 and Q2 match or beat, Q3 not worse and decidable.

**Agreement (LUNO, calibrators).** Jaccard of added cells (eligible cells newly flagged), on all cells
and on F1's far stratum (no input flag within ±3 dumps, ±8 channels, same baseline). Bar:
J(F-SIM, T) ≥ J(T-mild, T) − 0.05, both strata, on 1934−638 and 1830−211, same run. Far stratum under 5 %
of eligible cells: undecidable. Targets: reported only.

**Generalisation.** One weights file per class, no knob changed:

- Q1 and Q2 on each test observation within 0.05 and 0.01 of the validation observation;
- the held-out drifting carrier: Q1 (at `A ≥ 10`, drifting cells only) matches T;
- LUNO 1934−638 with injections (F1's `inject_mask`: narrowband, time-burst, antenna-local,
  single-baseline; seeds 19, 20, 21; strength 10 σ_b; on eligible cells): recall of injected cells
  matches T (±0.05), pooled over seeds and morphologies.

**Sky and gain guards (test 1).** G5, targets: a compact unmodelled line source added to the sky (5
channels, peak 20 σ per cell, on every baseline): flagged fraction of line cells ≤ T's + 0.05.
G6, both classes: 5 % amplitude and 0.1 rad phase step on one antenna mid-scan: flagged fraction of that
antenna's cells within ±2 dumps of the step ≤ its background fraction + 0.05.

**Cost (timing allowed here: speed is the claim).** LUNO 1934−638 whole array (calibrator) and the
ESO137 window (target, reported): the same rows in memory to flags in memory, the shared wrapper and
the network in Rust, against T's `flag_rows` (no intensity, no stages). Three repeats, arms alternating,
median; `RAYON_NUM_THREADS` 4 and 1; under `flock ~/.rang-heavy.lock`; load recorded, numbers provisional
if the 1-min load exceeds 2.

| | Beats (material) | Matches | Worse |
| --- | --- | --- | --- |
| C1 wall against T, 4 threads and 1 thread | ≤ 0.5 | 0.5-1.1 | > 1.1 |
| C2 peak RSS against T (separate processes, decode included) | ≤ 0.8 | 0.8-1.2 | > 1.2 |

Training cost is reported, never counted against inference.

**Parameters (P).** F1's tiers. T1 for the network arm: the shared wrapper's keys and the weights file
(F1 probe P1's `count.py` on the wrapper steps); T1 for T: the full YAML (calibrator first pass: 21
kinds; target: counted the same way in Stage 2). T2 (retraining) and T3 (architecture) are listed. P
holds if the network's T1 kinds are under half of T's, and Generalisation passes with no retraining;
otherwise T1 + T2 + T3 is compared.

## 6. Decision rule (per class, first that applies)

| Outcome | Condition | Reading |
| --- | --- | --- |
| **Stop-Z / Stop-R** | Stage 2: Z or R meets Q on validation | hand back before training that class |
| **G** | Z meets Q on test, C1(Z) ≤ 0.5 | a threshold does it |
| **F** | F-SIM does not meet Q, or Generalisation fails, or C1 > 1.1 | not comparable, or not faster |
| **H** | meets Q, Generalisation, C1 in 0.5-1.1 | comparable, not materially faster |
| **S** | meets Q, Generalisation, C1 ≤ 0.5 at 4 and 1 threads, C2 not worse, P, G5/G6 pass, and Q1 or Q2 better than Z and U | **Landman's request met** on simulated RFI (and, for calibrators, the agreement bar on LUNO) |
| **S-** | S except a guard or the agreement bar | as S, with that failure stated |

F-RES and F-IMI are reported beside F-SIM; if either is not worse on Q1-Q3 the note says labels from a
solve or from T suffice. **Novelty:** S on simulation and processed LUNO is a conditional result: "on
simulated RFI and processed L-band calibrator data, comparable to CARACal's first pass at under half its
wall". No claim against AOFlagger (not run), none on unprocessed data until L3, none for targets beyond
simulation.

## 7. Stages and stop rules

| Stage | Work | Stop if |
| --- | --- | --- |
| 0 | this protocol, committed | |
| 1 | F-SIM generator; build f2sim-v and the training observations; amendment with the script's hash; then build the test observations unread | build fails its checks (RFI layer equals DATA minus RFI-free DATA; truth fractions 1-8 % of cells per scan reported) |
| 2 | T, T-mild, N, Z, R on f2sim-v: Q1-Q3; P counts | **Z or R meets Q for a class: report, no training for that class** |
| 3 | Rust kernel with U weights; JAX parity on f2sim-v; C1 of U on LUNO 1934−638 | **C1(U) > 0.75 at 4 threads: no speed to win** |
| 4 | train F-SIM (3 seeds), F-RES, F-IMI per class (JAX, CPU); parity again with the trained weights; validation Q1-Q3 | |
| 5 | test observations, LUNO, ESO137, guards, C1, C2; verdict; archive | |

At most one change of hyperparameters per class, on validation, by dated amendment, before Stage 5.

**Training (frozen).** Adam, rate 1e-3, 4,000 steps, batch 16 windows; a window is one baseline's whole
scan in time × 256 channels, with the features computed on the full plane and the loss on the window
(so training equals full-plane inference); unweighted binary cross-entropy on non-ignored cells;
initialisation He-normal from the training seed (seeds 1, 2, 3; F-RES and F-IMI seed 1). Windows
uniform over (observation, scan, baseline, channel offset) of the class: calibrators from F and G scans,
targets from T scans. Validation loss: the same loss on f2sim-v, all windows. CPU JAX: the GPU had about
1.5 GB of 12 GB free on 2026-11-06 and a CUDA jaxlib is not installed.

**Files.** New: `python/rang/f2flag_sim.py`, `python/rang/f2flag.py` (features, JAX network, training,
measures), `core/src/cnnflag.rs` with its PyO3 binding, `examples/f2_*.py`, `tests/test_f2_*.py`,
`research/results/f2-*.json`. Edited: `python/rang/simtruth.py` (seed registration only),
`core/src/lib.rs`, `core/py/src/lib.rs`. Not edited: `core_flag.py`, `sumthreshold.rs`, the solver,
`core_pipeline`, `cal_chain`, gemclean. Weights: `/mnt/d/rang/outputs/f2-*` (ignored); their sha256 and
the run paths in the archive. Wiring into `rang-core flag` is proposed only, if S.

## 8. Not claimed

No better calibration or imaging. Simulated RFI is not shown to be realistic; LUNO is processed;
ESO137 is exploratory. Nothing about other bands or telescopes.

## 9. Measured result

Runs under `/mnt/d/rang/outputs/f2-20261106-NN-*` (each with `.code/`, `.log`, `.time`). Archive:
[results/f2-flagger.json](results/f2-flagger.json).

### Stage 1: F-SIM

f2sim-v (`-01`), f2sim-1 to -3 (`-02`), f2sim-t1, -t2 and t1's line and step variants (`-04`, built after
Amendment 1, unread until Stage 5). 6.0-6.5 min and 4.3 GB peak RSS per observation, 2 threads. Truth
(`A > 0`) 3.6-6.0 % of cells per scan, `A ≥ 10` 0.8-1.9 %. RFI check: max |DATA − RFI − RFI-free| 1e-5 at
|V| ≤ 15 Jy (float32 rounding). The shared wrapper flags 47 % of cells (static masks; the `0~550 m`
static mask on short baselines).

The test build's log and `.code/` record Amendment 1's three sha256 values. After Stage 5,
`f2flag_sim.py` changed for the portability test only (`Scan.open` renamed `Scan.from_dir`, an explicit
newline in `meta.json`'s write); the generated data do not depend on either.

### Stage 2: comparators on validation (f2sim-v, `-03`)

| Arm | Cal Q1 | Cal Q2 | Cal Q3 | Tgt Q1 | Tgt Q2 | Tgt Q3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T | 0.829 | 0.320 | 0.0318 | 0.990 | 0.140 | 0.0420 |
| T-mild | 0.681 | 0.202 | 0.0374 | – | – | – |
| N | 0 | 0 | 0.0232 | 0 | 0 | 0.412 |
| Z | 0.438 | 0.0066 | 0.0243 | 0.036 | 0 | 0.401 |
| R | 0.073 | 0 | 0.0163 | 0.448 | 0.0002 | 0.197 |
| O | 1 | 0 | 0.0038 | 1 | 0 | 0.0042 |

- **Stop rule not triggered:** Z and R are worse than T on Q1 in both classes.
- T flags 32 % (calibrators) and 14 % (targets) of clean cells outside the shared wrapper. Q2's bar is
  therefore loose. Cause not traced; the same direction as C2e's 63 % on A1's calibrators.
- Calibrator Q3: N < T, so undecidable as frozen (Amendment 2). Target Q3 decidable (N = 9.8 × T).
- Z misses carriers that are on for the whole scan (recall 0.01; the per-channel median removes them) and
  RFI ≥ 100 σ (0.03): planes 1-4 alone cannot see them.
- P (`-03/params.json`): T1 for the calibrator first pass and the target first pass, 21 kinds each (12
  steps); calibrator mild 19. Network wrapper: 2 kinds (`apply_static_mask` `accumulation_mode`,
  `uvrange`) plus the weights file, 3.

### Stage 3: kernel (`-05`)

Parity, U weights, f2sim-v: |Δlogit| p99.9 4.8e-7 (cal) and 3.8e-7 (tgt), max 1.6e-6, flag disagreement
8.7e-8 (3 of 34.4 M cells): pass. C1(U) on LUNO 1934−638 whole array, 4 threads, 3 repeats: 10.6 s
against T 44.1 s, **0.24** (1-min load 9.4-11.2, so provisional): stop rule (0.75) not triggered.

### Stage 4: training (`-07` calibrators, `-08` targets)

JAX 0.12.0.1 on CPU, 4 NumPy feature workers, under the heavy lock. 4,000 steps per run, 12-18 min per
run; preparation (shared wrapper, R and T labels of the 9 or 6 training scans and f2sim-v) 5.4 and
7.0 min. Peak RSS 9.5 GB (calibrators). Validation loss, F-SIM seeds 1, 2, 3: calibrators 0.082, 0.098,
0.060; targets 0.0182, 0.0183, 0.0136. Median seed 1 in both classes: weights sha256 `b3a1568a3c86…`
(calibrators) and `162c62337325…` (targets), 2,785 float32 each. Parity with the trained weights at the
picked τ (`-03`): p99.9 7.6e-6 and 4.8e-6, max 2.3e-5 and 1.3e-5, flag disagreement 0 and 2.9e-8:
pass.

At τ = 0 every trained arm failed Q1 on validation (Amendment 3); the thresholds of Amendment 3 apply
below.

### Stage 5: F-SIM test (`f2-20261107-03-stage5`)

Q1 / Q2 / Q3, pooled over f2sim-t1 and -t2 (`test-<class>.json`); validation in brackets.

| Arm | Calibrators | Targets |
| --- | --- | --- |
| T | 0.880 / 0.318 / 0.0299 (0.829 / 0.320 / 0.0308) | 0.987 / 0.138 / 0.0388 (0.990 / 0.140 / 0.0420) |
| T-mild | 0.868 / 0.171 / 0.0318 | – |
| N | 0 / 0 / 0.0093 | 0 / 0 / 0.193 |
| Z | 0.417 / 0.0064 / 0.0104 | 0.117 / 0 / 0.117 |
| R (targets: true sky) | 0.131 / 0 / 0.0077 | 0.585 / 0 / 0.0704 |
| O | 1 / 0 / 0.0028 | 1 / 0 / 0.0047 |
| **F-SIM** (τ −3, −6) | **0.909 / 0.0122 / 0.0030** (0.844 / 0.0133 / 0.0041) | **0.884 / 0.0374 / 0.0831** (0.914 / 0.0355 / 0.0118) |
| F-RES (τ −6, −6) | 0.123 / 0.0015 / 0.0086 | 0.828 / 0.0264 / 0.0714 |
| F-IMI (τ 0, −0.5) | 0.571 / 0.181 / 0.0653 | 0.778 / 0.155 / 0.141 |
| U | 0.216 / 0.279 / 0.0131 | 0.306 / 0.348 / 0.205 |

Calls of F-SIM against T:

| | Calibrators | Targets |
| --- | --- | --- |
| Q1 | matches (+0.029) | **worse** (−0.103) |
| Q2 | beats (0.012 against 0.318) | beats (0.037 against 0.138) |
| Q3 | undecidable as frozen (N 0.31 × T); post hoc (Amendment 2) beats, 0.10 × T | **worse**, 2.14 × T (t2: 2.89 ×) |
| Meets Q | no as frozen; yes post hoc | no |
| Generalisation: per observation within 0.05 / 0.01 of validation | Q1 t1 0.833, t2 0.936 against 0.844: **fails** on t2 (better by 0.092); Q2 passes | Q1 0.947, 0.835 against 0.914: passes; Q2 passes |
| Generalisation: held-out drifting carrier, Q1 | **worse**: 0.74 against T 0.98 | worse: 0.89 against 0.98 |
| G5, unmodelled 20 σ line | – | passes as frozen: flags 99.6 % of line cells, T 97.7 % (both remove the line) |
| G6, gain step | passes: 0.056 near the step against background 0.025 | passes: 0.068 against 0.050 |

- Recall by morphology at `A ≥ 10`, calibrators, F-SIM against T: intermittent 1.00 / 0.94, burst
  0.80 / 0.77, carrier 0.91 / 0.91, antenna-local 0.92 / 0.99, single-baseline 0.71 / 1.00, drifting
  0.74 / 0.98. Targets: intermittent 0.74 / 0.98, carrier 0.74 / 0.99, comb 1.00 / 0.99,
  single-baseline 1.00 / 1.00, drifting 0.89 / 0.98.
- On F-SIM, T leaves 32 % (calibrators) and 14 % (targets) of clean cells flagged, so Q2 hardly binds and
  Q1 decides. At matched calibrator Q1, F-SIM's false-flag fraction is 0.012 against T's 0.318.
- F-RES and F-IMI are worse than F-SIM on Q1 in both classes: labels from R (a residual threshold at 10)
  are too sparse, and labels from T carry T's 32 % false flags (F-IMI at τ = 0 flags 18 % of clean cells
  and is worse than T on Q3 by 2.2 ×). Neither replaces truth labels here.
- Z and R are far below T on Q1 in both classes.
- **Q3 caveat.** Every arm except T runs inside the shared wrapper, whose whole-band static mask removes
  A1's persistent GPS bands; T's own first `uvcontsub_flagger` step drops those flags
  (`or_original_from_cycle: 1`; the YAML: "flags are discarded at this point"), keeping only the
  `0~550 m` mask. So on calibrators N's Q3 is below T's partly because the wrapper drops channels T keeps.
  Q3 compares solves on different channel sets; this was not foreseen in the protocol.

### Stage 5: real data (`f2-20261107-04-stage5-real`)

The first real-data launch (inside `-03`) stopped on a missing `data` key in the injection state after
writing nothing; `-04` reran it with that fix and the post hoc stratum below.

**Agreement, LUNO calibrators.** Added cells (eligible cells newly flagged), Jaccard with T.

| Set, arm | added | J all (frozen) | J far (frozen) | J on wrapper-unflagged cells, all / far (post hoc) |
| --- | ---: | ---: | ---: | --- |
| 1934−638, T | 762,924 | – | – | – |
| 1934−638, T-mild | 372,404 | 0.230 | 0.013 | 0.185 / 0.012 |
| 1934−638, F-SIM | 7,196,379 | **0.070** | 0.0043 | 0.010 / 0.0013 |
| 1934−638, Z | 6,682,012 | 0.074 | 0.0045 | 0.002 / 0 |
| 1934−638, F-IMI | 11,066,905 | 0.060 | 0.0056 | 0.034 / 0.008 |
| 1934−638, U | 16,268,105 | 0.036 | 0.0026 | 0.008 / 0.002 |
| 1830−211, T | 226,016 | – | – | – |
| 1830−211, T-mild | 53,034 | 0.146 | 0.092 | 0.056 / 0.093 |
| 1830−211, F-SIM | 5,380,641 | **0.033** | **0.0029** | 0.012 / 0.0005 |

- Bar J(F-SIM, T) ≥ J(T-mild, T) − 0.05: 1934−638 fails on all cells (0.070 against 0.180), passes on
  the far stratum (0.004 against −0.037; far stratum 22 % of eligible cells); 1830−211 fails on both
  (0.033 against 0.096; 0.003 against 0.042). **Agreement bar: fails.**
- Most of every wrapper arm's additions are the whole-band static mask (6.7 M cells on 1934−638), which
  T drops (Stage 5 caveat above). On the cells the wrapper leaves unflagged F-SIM still adds 2.1 × T's
  cells on 1934−638 (516,827 against 248,696) and 20 × on 1830−211 (1,163,264 against 58,920; 9.2 % of
  those cells), with J ≤ 0.012.
- **LUNO 1934−638 with injections** (12 cases, 10 σ_b, 1.95 M scored injected cells): recall T 0.992,
  F-SIM **0.431**, F-IMI 0.536, U 0.290, Z 0.034, F-RES 0.014. By morphology, F-SIM against T:
  time-burst 0.998-0.999 against 1.000, narrowband 0.10 and 0.21 against 1.00, antenna-local 0.03 against
  0.96-1.00, single-baseline 0 against 1.0. (Seed 20 of three morphologies lies under the shared
  wrapper: no scored cells.) The missed morphologies are on for the whole scan, which planes 1-4 remove
  and plane 5 does not restore at this strength. **Generalisation clause 3: fails.**
- **ESO137 target (exploratory; 512 channels at 989.7-1096.6 MHz, outside the training window; 29.6 %
  input flags):** T adds 2,576,606, F-SIM 2,723,462, J 0.121 (far 0.100), U 0.128 (far 0.109): F-SIM
  agrees with T no better than random weights.

### Stage 5: cost (`f2-20261107-05-cost`) and P

Same rows in memory to flags in memory; the network arm is the shared wrapper (`flag_rows`) plus the Rust
kernel at the picked τ. Three repeats, alternating, median; heavy lock held. The recorded 1-min load
includes the measured process (about 4 at 4 threads, 1 at 1 thread); the other jobs on the host were idle
or single-core.

| Set | Cells | Threads | T | F-SIM | C1 | Load |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| LUNO 1934−638 (calibrator) | 85.6 M | 4 | 37.4 s | 8.37 s | **0.224** | 2.4-3.8 |
| LUNO 1934−638 | 85.6 M | 1 | 126.9 s | 25.6 s | **0.201** | 1.0-1.25 (first repeat 3.2) |
| ESO137 window (target, reported) | 24.8 M | 4 | 11.24 s | 2.96 s | 0.263 | 3.3-3.6 |
| ESO137 window | 24.8 M | 1 | 38.8 s | 8.91 s | 0.230 | 1.0-1.05 |

- **C1 beats (≤ 0.5) at 4 and 1 threads in both classes.** U on the same array, Stage 3: 0.24.
- C2: peak RSS 7.55 GB for both arms (T 7,551,512 kB, F-SIM 7,552,636 kB), ratio 1.000: the decode sets
  the peak, and neither flag step exceeds it. Matches.
- P: T1 network 3 kinds (wrapper's `accumulation_mode`, `uvrange`; the weights file) against 21 for both
  first-pass strategies. Generalisation fails, so P compares T1 + T2 + T3: 3 + 9 (the eight retraining
  settings of `-03/params.json` plus τ) + 5 = 17 against 21. **P fails.**

### Decision (frozen rule, section 6)

| | Calibrators | Targets |
| --- | --- | --- |
| Stop-Z / Stop-R | no | no |
| G (Z meets Q) | no: Z Q1 0.417 | no: 0.117 |
| Meets Q | no as frozen (Q3 undecidable); yes post hoc | no: Q1 −0.103, Q3 2.14 × T |
| Generalisation | fails: drifting 0.74 against 0.98; t2 Q1 0.092 above validation; LUNO injections 0.43 against 0.99 | fails with Q |
| Agreement bar (real data) | fails: 1934−638 all cells, 1830−211 both strata | reported only |
| C1, C2 | beats (0.224, 0.201); matches (1.00) | beats (0.263, 0.230), reported |
| P | fails (17 against 21; generalisation fails) | fails |
| G5, G6 | G6 passes | both pass as frozen |
| **Outcome** | **F** | **F** |

**No flagger meets the bar. Nothing is proposed for `rang-core flag`.**

What the record supports, for Landman, numbers only:

- The kernel is fast: C1 0.20-0.22 on LUNO 1934−638 (25.6 s against 126.9 s at 1 thread). Speed is not
  the obstacle.
- On F-SIM calibrators, with τ chosen on validation, F-SIM matches T's recall at `A ≥ 10` (0.909 against
  0.880) with 4 % of T's false flags (0.012 against 0.318) and 0.10 × T's gain-product error. T's false
  flags on F-SIM are 32 % of clean cells, so the comparison mainly rewards not over-flagging.
- It does not generalise to what it has not seen: the held-out drifting carrier, a different realisation
  (t2), and, decisively, real LUNO data: RFI on for a whole scan (narrowband, antenna-local,
  single-baseline injections) is missed (0-0.21), and on 1830−211 it flags 9.2 % of cells T leaves.
- Targets: not comparable. Recall 0.884 against 0.987 at the grid floor τ = −6, Q3 2.1 × T.
- Truth labels beat T's labels (F-IMI) and residual labels (F-RES) as training data in both classes.
- Post hoc reading (not a test): two design choices limit it. (1) The F-SIM RFI mix is thin in the
  morphologies that fail (scan-long carriers on one antenna or baseline at moderate strength; bursts:
  3 per observation). (2) Planes 1-4 remove the per-channel time median, so scan-long RFI is visible only
  through plane 5 (one profile per baseline at a 33-channel scale). A network that sees raw amplitudes
  across baselines, or a training set built from real flagged data (L3), would test this; neither is
  this protocol.

### Not checked

- AOFlagger (A, C3): not run; no claim against it.
- Real unprocessed data (L3): none available.
- G5 on calibrators; F-RES and F-IMI on ESO137 and in the guards.
- Training cost on the GPU (CPU only).
- Whether T's 32 % false-flag rate on F-SIM is a property of the simulation or of the strategy (also
  seen as 63 % on A1 in C2e); not traced.

## 10. Owner decisions

1. **Whether F2 continues.** As frozen it ends at F in both classes. A follow-up would need a new
   protocol: a training set closer to real RFI (real flagged data, L3, or LUNO-derived labels, which
   raises F1's licence question 4), inputs that keep scan-long RFI, and an AOFlagger comparison (C3).
2. **The shared wrapper.** CARACal's first pass discards its whole-band static mask at its first
   `uvcontsub_flagger` step; the frozen wrapper keeps it. A follow-up should copy T's net static-mask
   behaviour.
3. **What to tell Landman.** Proposed, in his terms: "a 2,785-weight network flags at a fifth of the
   Rust Tricolour port's wall, matches its recall on simulated calibrator RFI with a twentieth of its false
   flags, but misses scan-long RFI and over-flags on real LUNO data; targets are not comparable. Not
   shipped."

## 11. For the coordinator

- **Commits (branch `fp-f2-flagger`):** `7bc3522` protocol; `8484b17` Amendments 1-3; `0a4509f`
  Amendment 3's picks; the final commit with code, results and this section.
- **Run outputs (ignored), `/mnt/d/rang/outputs/`:** `f2-20261106-01-sim-v` (12 GB), `-02-sim-train`
  (36 GB), `-03-stage2-val`, `-04-sim-test` (48 GB), `-05-stage3-U`, `-06-train-smoke`,
  `-07-train-calibrator`, `-08-train-target` (weights), `f2-20261107-01-stage5-quality` (stopped launch;
  picks), `-02-amend3`, `-03-stage5`, `-04-stage5-real`, `-05-cost`; each with `.code/`, `.log`, `.time`.
  The F-SIM observations (96 GB) can be deleted once the result is accepted; the generator
  rebuilds them from the seeds.
- **Archive:** [results/f2-flagger.json](results/f2-flagger.json).
- **`research/STATE.md`, new log paragraph:** "F2, 2026-11-07 (implemented; measured; outcome F for
  calibrators and targets; [f2-flagger.md](f2-flagger.md)): a 2,785-weight per-baseline network
  (`rang.f2flag`, Rust inference `rang_core::cnnflag`, JAX training on CPU) trained on simulated MeerKAT
  L-band RFI with known masks (`rang.f2flag_sim`). Against the Rust Tricolour port: C1 0.22 at 4 threads
  and 0.20 at 1 thread on LUNO 1934−638 (37.4 s and 126.9 s for T). Simulated calibrators, threshold
  chosen on validation (Amendment 3): recall at ≥ 10 σ 0.909 against 0.880, false flags 0.012 against
  0.318, gain-product error 0.10 × T (undecidable as frozen). It fails generalisation: the held-out
  drifting carrier (0.74 against 0.98), LUNO injections (0.43 against 0.99; scan-long narrowband,
  antenna-local and single-baseline RFI missed) and agreement with T on LUNO; targets miss recall
  (0.884 against 0.987) and Q3 (2.1 × T). Labels from T or from a residual threshold train worse. Z and
  R do not match T. Nothing proposed for `rang-core flag`. No novelty claim."
- **`research/STATE.md`, current status:** replace the "Stopped before training" bullet's flagger
  clause with: "a flagger trained on gain TV (F1, NO-GO) and a supervised fast flagger (F2, outcome F:
  fast, but does not generalise to real data)".
- **`research/README.md`, new line beside F1:** "- [F2, a fast supervised flagger](f2-flagger.md):
  protocol and result; five times faster than the Tricolour port, matches it on simulated calibrators,
  fails on held-out morphologies and real LUNO data: outcome F."
- **`research/finish-plan.md`, section 6, Landman:** "F2 ran 2026-11-06/07 (`f2-flagger.md`): outcome
  F in both classes; not a second flagger for `rang-core flag`."
- **`research/tool-timings.md`:** rows added in this branch.
