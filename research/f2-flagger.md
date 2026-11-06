# F2: a fast supervised RFI flagger for MeerKAT L-band (protocol)

Task F2, branch `fp-f2-flagger` from main `ba65792`. Protocol frozen 2026-11-06 before any simulation,
training or comparison. **Status at freeze: proposed; nothing implemented, run or trained.** Results go
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
