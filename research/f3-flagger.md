# F3: a fast supervised RFI flagger for MeerKAT L-band, second protocol

Task F3, branch `fp-f3-flagger` from main `8d3becd`. Follows [F2](f2-flagger.md) (outcome F in both
classes) at the owner's request of 2026-11-10 (F2 owner decision 1: continue, new protocol). **Status at
freeze: proposed; nothing implemented, fetched, run or trained.** Results go under "Measured result";
nothing above it changes except by dated, labelled amendment.

Landman's wishes (2026-11-06) are the goal: one weights file per observatory and band (MeerKAT L-band),
separate models for calibrators and targets, faster than the Rust Tricolour port with fewer tunable
parameters, **comparable** flag quality. Better calibration or imaging is not a goal and is not claimed.

## 1. What F2 got wrong, and what changes

| F2 failure | Cause (F2 section 9, post hoc) | F3 change |
| --- | --- | --- |
| LUNO injections 0.43 against T 0.99: scan-long narrowband 0.10-0.21, antenna-local 0.03, single-baseline 0 | planes 1-4 subtract the per-channel time median, so RFI on for the whole scan vanishes; plane 5 is one 33-channel profile per baseline | channel-local residual planes per correlation (section 3), in SNR units from a noise estimate, not a MAD of the residual |
| no cross-baseline context | per-baseline network | per-antenna and whole-array median planes (section 3) |
| held-out drifting carrier 0.74 against 0.98 | thin F-SIM mix | training injections with the morphologies F2 missed; drifting stays held out |
| adds 2-20 × T's flags on real LUNO | trained on simulation only | real LUNO and ESO137 backgrounds in training (section 4) |
| Q3 confounded; whole-band mask kept | shared wrapper kept the static mask T drops | wrapper W3 copies T's net static mask (section 2) |
| no AOFlagger | not run | arm A, AOFlagger 3.5 (section 2) |

## 2. Arms

| Arm | What | Role |
| --- | --- | --- |
| **T** | Rust Tricolour port `core_flag.flag_rows`, CARACal `8f7bb363`: calibrators `mk_rfi_flagging_calibrator_fields_firstpass.yaml`, targets `mk_rfi_flagging_target_fields_firstpass.yaml` | the bar |
| **A** | AOFlagger 3.5.0 (image `rang-aflag-aoflagger:3.5.0`, WSL Docker, `--network none`), shipped `generic-default.lua` (no MeerKAT strategy ships), run per baseline on the four correlations (8 real images), W3's flags as the input mask, ORed with W3 | second established flagger; spread against T |
| **N3** | the F3 network (section 3) inside W3; one weights file and one threshold τ per class | **the method** |
| Z2 | W3 OR (max over N3's eight residual planes before `asinh` > 10) | one-knob threshold on the new planes; stop rule |
| U3 | N3 with its untrained initial weights (init seed 0) | chance; kernel cost |
| F2 | F2's F-SIM weights at F2's τ inside F2's shared wrapper | reported: before/after |
| N | W3 only | reported |

**W3** = the class's YAML reduced to `flag_nans_zeros`, `apply_static_mask` (`uvrange: "0~550"`,
`or`), `flag_autos`, `combine_with_input_flags`, run by `flag_rows`. T's first `uvcontsub_flagger`
(`or_original_from_cycle: 1`) discards the whole-band static mask and everything before it (F2,
Stage 5 caveat), so T's net static mask is the `0~550` step only. **Check (frozen):** on one
validation scan per class W3's flags are a subset of T's final flags; if not, stop and report.
Every measure scores only cells W3 leaves unflagged ("eligible").

## 3. Network N3 (frozen)

Per scan, per cross-correlation baseline b, on the (time, channel) plane; `F` = cells flagged on input,
by W3, missing from the time grid, or with a non-finite or zero visibility.

**Features** (computed in float64, stored float32; 0 on `F`):

1. Noise per baseline and correlation: `σ_bc = 1.4826 · MAD(x) / √2`, `x` the real and imaginary parts
   of `V_c(t, f+1) − V_c(t, f)` over pairs with neither cell in `F`. Fewer than 16 pairs: the median of
   the baseline's valid `σ_bc`; none valid: all features of the baseline 0.
2. `a_c = |V_c| / σ_bc` (SNR units).
3. `P_c(f)` = median over unflagged times of `a_c`; time-local residual `r^t_c = a_c − P_c(f)`.
4. `S_c(f)` = running median of `P_c` over channels f−16 … f+16 (finite values only); `g_c(t)` = median
   over unflagged channels of `a_c / S_c`; channel-local residual `r^f_c = a_c − g_c(t) · S_c(f)`.
   A carrier on for the whole scan raises `P_c` in its channels but not `S_c` (≤ 8 channels against a
   33-channel median), so it stays in `r^f`; a broadband burst stays in `r^t`.
5. `u^t_b = max_c r^t_c`, `u^f_b = max_c r^f_c`. Per antenna k and cell, `M^x_k` = median of `u^x` over
   unflagged baselines containing k (at least 3, else 0); `M^x_all` = median over all unflagged
   baselines (at least 3).
6. Inputs, 15 planes: `asinh r^t_c` (4), `asinh r^f_c` (4), for x ∈ {t, f}: `asinh max(M^x_p, M^x_q)`,
   `asinh min(M^x_p, M^x_q)`, `asinh M^x_all` (6), the mask `F` (1). Amplitude only.

Single-baseline RFI: own planes high, antenna planes low. Antenna-local: own and max-antenna high,
min-antenna low. Array-wide: all high.

**Network.** F2's stack with 15 inputs: 3×3 convolutions, dilations 1, 2, 4, 8, 16 in (time, channel),
8 hidden channels, ReLU, zero padding ("same"), 1×1 head; receptive field 63 × 63 (the scans here have
10-32 dumps, so the time extent covers every scan). Weights: 1,088 + 4 × 584 + 9 = **3,433**. Flag where
logit > τ and the cell is not in `F`, uniform over correlations.

**Implementations.** Features and network in Rust (`core/src/f3flag.rs`, f32 network, float64
features), exposed as `rang._core.f3flag_features` (planes for training) and `f3flag_logits`
(inference). Reference: NumPy features (`rang.f3flag.features_numpy`) and the JAX network
(`rang.f3net`, float32, `enable_x64` off). Parity, frozen: features Rust against NumPy on one
validation scan max |Δ| ≤ 1e-4 (absolute, after `asinh`); logits Rust against JAX on the same features
|Δ| ≤ 1e-4 at the 99.9th percentile, ≤ 1e-3 max, flag disagreement ≤ 1e-5 of cells. F2's
`cnnflag` is not changed.

## 4. Data and labels

**Groups never read** (enforced by exact-name allowlists in code, no globs): LUNO `MAIN_16`-`MAIN_19`
(E2-B's acceptance scans 17-20), ESO137 ms1 primary and target `MAIN_4`-`MAIN_6` (E2-A).

**Calibrators.**

| Set | Role | Rows | Source |
| --- | --- | --- | --- |
| LUNO MAIN_3, MAIN_4, MAIN_5, MAIN_6 (1830−211, scans 4-7) | train (real background) | 15-18 k each | new fetch: DATA and FLAG tiles 8-23 (channels 1024-3071), ANTENNA1/2, TIME, FLAG_ROW; HEAD total must be ≤ 5 GB, else MAIN_6 is dropped and becomes validation |
| LUNO MAIN_7 (1830−211, scan 8) | validation (real) | 15,960 | same fetch |
| f2sim-1, -2, -3 calibrator scans (9) | train (simulation) | | F2's, on `D:\rang\outputs\f2-20261106-02-sim-train` |
| f2sim-v calibrator scans | validation (simulation) | | F2's |
| **LUNO MAIN_1 (1934−638, scan 2, whole array)** | **held-out real test** | 41,786 | on disk (F2's set) |
| **LUNO MAIN_2 (1830−211, scan 3)** | **held-out real test** | 15,400 | on disk (F2's set) |
| **f3sim-t calibrator scans** | **held-out simulation test** | | new: `f2flag_sim` generator, seeds 20263101-05 (not in `simtruth.SEEDS`, checked 2026-11-10; registered), start 2024-08-21T05:00, odd antennas, test role (drifting carriers in) |

**Targets.**

| Set | Role | Source |
| --- | --- | --- |
| ESO137 `ms1_target.zarr` MAIN_0 row chunks 2, 4, 6, 8 (channels 640-1151, 989.7-1096.6 MHz; 61 antennas) | train (real) | on disk (`D:\rang\data\eso137-pilot`, CC BY 4.0) |
| ESO137 MAIN_0 chunk 10 | validation (real) | same |
| f2sim-1..3 target scans (6) / f2sim-v target scans | train / validation (simulation) | F2's |
| **ESO137 MAIN_0 chunks 0 (F2's set), 14, 16** | **held-out real test** | same |
| **f3sim-t target scans** | **held-out simulation test** | new, as above |

The ESO137 chunks are time-disjoint parts of one target track, so "held-out real scan" for targets means
held-out time ranges of one observation; a target result is conditional on that.

**Training injections** (`rang.f3flag.inject`, seeded; train seeds 20263201 + k, validation 20263301 + k;
both disjoint from F2's 19-21 and the test seeds). Each realisation adds to DATA, on eligible cells only:

- T1 scan-long narrowband on all baselines: 1-4 events, 1-4 channels;
- T2 intermittent narrowband on all baselines: 1-4 events, 1-8 channels, runs of 1-8 dumps;
- T3 antenna-local: 1-3 events, 1-8 channels, scan-long (p = 0.5) or a run of 2-16 dumps;
- T4 single-baseline: 2-6 events, 1-8 channels, scan-long (p = 0.5) or a run;
- T5 broadband burst: 0-2 events, 1-2 dumps, 64-1,024 channels, all baselines.

Per event: amplitude α log-uniform 3-300 σ_b (per baseline, real-part σ from step 1 of section 3);
on all-baseline events α × exp(−|b|/L) with p = 0.5 (L log-uniform 0.1-5 km); per-correlation coupling
(1, ρ₁e^{iφ₁}, ρ₂e^{iφ₂}, ρ₃e^{iφ₃}), ρ uniform 0-1, normalised to max 1, randomly permuted; phase
φ₀ + 2π ν_b t + N(0, 0.15) with fringe rate ν_b uniform ±0.5 cycles per dump per baseline (p = 0.5,
else 0); amplitude constant (p = 0.5) or × (0.75 + 0.25 sin) over the event. Cell strength
`A = max_c |inj_c| / σ_b`.

**Held-out morphologies (never in training):** H1 drifting carrier (4 channels, moving 1-3 channels per
dump, all baselines, scan-long); H2 antenna cluster (3-6 antennas, every baseline with both ends in the
cluster, 1-8 channels, scan-long). F-SIM's own drifting carriers (f3sim-t) are H1 in simulation.

**Labels.**

- Simulation: positive where max(F-SIM's truth A, injection A) ≥ 3; negative where both are 0; ignored
  otherwise and on `F` (F2's rule plus the injections).
- Real: each training scan gets T and A on its **uninjected** DATA. Positive: injection A ≥ 3, or flagged
  by both T and A (consensus); negative: not injected and flagged by neither; ignored: flagged by exactly
  one, 0 < injection A < 3, and `F`. AOFlagger's and T's flags thus enter the labels; every agreement
  with T or A is reported with that stated.
- Realisations: real training scans 6 each (seeds 20263201 + 6·scan + k); simulation scans 1 each; a
  third of all realisations also get F2's synthetic input flags (8-256-channel bands, 1-8-dump blocks,
  occupancy uniform 0-0.6) before features are computed.
- Shards: per realisation, the features and labels of 256 baselines drawn uniformly (seeded), float16
  features, int8 labels, under `D:\rang\outputs\f3-*`; features are computed on the whole array first.

**Label audit (frozen, before training).** Per real training scan: counts of positive (injected,
consensus), ignored and negative cells; T's and A's recall of the injected cells (sanity); median `u^f`
and `u^t` of consensus positives against negatives. **Stop if** consensus positives exceed 10 % of
eligible cells on any scan, or the median `max(u^t, u^f)` of consensus positives is below 3 (labels
suspect).

## 5. Training (frozen)

JAX on the RTX 4070 Ti in WSL (CUDA JAX is Linux-only; a deviation from "WSL only for oracles",
recorded; venv `~/Build/tmp/20261110-f3-jaxcuda`, removed at the end). Shards are produced natively by
the Rust kernel; WSL runs NumPy and JAX only. Adam, rate 1e-3, 30,000 steps, batch 32 windows; a window
is one baseline's whole scan × 256 channels at a random offset, all from one shard per step; shards drawn
real : simulation = 1 : 1; unweighted binary cross-entropy over non-ignored cells; He-normal init from
seed 1, 2, 3 per class. Validation loss on all validation shards at the end. The weights file is the
median seed by validation loss.

**Threshold τ (frozen, on validation only).** Grid −4, −3.5, …, +2. Pick the τ with the largest
validation recall of positive cells (simulation and real validation pooled) such that N3's added cells on
the real validation scan's uninjected DATA are ≤ T's added cells there. If none qualifies, the τ with the
fewest added cells (reported). τ is stored beside the weights' sha256.

At most one change of hyperparameters per class, on validation, by dated amendment, before any held-out
set is read.

## 6. Measures (frozen; per class, T the reference)

**Held-out real** (calibrators: MAIN_1, MAIN_2; targets: ESO137 chunks 0, 14, 16).

| Gate | Measure | Bar |
| --- | --- | --- |
| R1 | F2's injection test (F1's `inject_mask`: narrowband, time-burst, antenna-local, single-baseline; seeds 19, 20, 21; 10 σ_b; eligible cells; ESO137 with unit weights), recall pooled over seeds, sets and morphologies | ≥ T − 0.05 |
| R1m | the same per morphology | each ≥ T − 0.10 |
| R2 | H1 and H2 at 10 σ_b, seeds 31, 32, 33, recall per morphology pooled over seeds and sets | each ≥ T − 0.05 |
| R3 | added cells on uninjected DATA (eligible cells newly flagged), per set, ratio to T | ≤ 1.5 |
| R4 | Jaccard of added cells with T, per set | ≥ J(A, T) − 0.05 |

**Held-out simulation** (f3sim-t, class scans).

| Gate | Measure | Bar |
| --- | --- | --- |
| S1 | Q1, recall of cells with A ≥ 10 | ≥ T − 0.05 |
| S2 | Q2, flagged fraction of eligible cells outside the truth mask dilated by one cell | ≤ T + 0.01 |
| S3 | recall of drifting cells (H1) with A ≥ 10 | ≥ T − 0.05 |

Q1 by morphology and strength decade, and Q3 (F2's gain-product error; calibrator decidability as F2's
Amendment 2: O ≤ 0.99 × N), are reported, not gated.

**Cost (timing claims allowed in this task).** LUNO MAIN_1 (calibrator) and ESO137 chunk 0 (target), same
rows in memory to flags in memory: N3 arm = W3 (`flag_rows`) + `f3flag_logits` + threshold; T =
`flag_rows` with the full YAML. Native Windows, one process per thread count, `RAYON_NUM_THREADS` 4 and 1,
three repeats alternating, median, heavy lock held. **Idle host (frozen):** before each repeat psutil
samples system CPU for 1 s, minus this process's own; the repeat is clean if the rest is ≤ 1 logical
CPU (6.25 % of 16), else the number is provisional. C2: peak working set (`peak_wset`) in separate
processes, decode included. A's wall (WSL Docker, one thread) is reported, not gated.

| | Beats (material) | Matches | Worse |
| --- | --- | --- | --- |
| C1 wall, N3 against T, 4 and 1 threads | ≤ 0.5 | 0.5-1.1 | > 1.1 |
| C2 peak working set against T | ≤ 0.8 | 0.8-1.2 | > 1.2 |

Training cost reported, never counted. **P:** F1/F2's tiers, `f2_params.py`'s count on W3 against the
full YAML; holds if N3's T1 kinds are under half of T's and no retraining was needed between sets.

## 7. Decision rule (per class, first that applies)

| Outcome | Condition | Reading |
| --- | --- | --- |
| **Stop-Z2** | Z2 meets R1, R3 on the real validation scan with F2-style injections (seeds 41, 42, 43) and S1, S2 on f2sim-v | report; no training for that class |
| **F** | any of R1, R1m, R2, R3, R4, S1, S3 fails, or C1 > 1.1 | not comparable, or not faster |
| **H** | all quality gates pass, C1 in 0.5-1.1 at either thread count | comparable, not materially faster |
| **S** | all quality gates pass, C1 ≤ 0.5 at 4 and 1 threads, C2 not worse, P holds | **Landman's request met** on these data |
| **S−** | S except S2 or P | as S, with that failure stated |

Against A: A is reported on every measure. No novelty claim follows from beating T on its own; a claim
needs N3 comparable to both T and A at lower cost than both, and A runs single-threaded in Docker here,
so any comparison of cost with A is stated as such.

## 8. Stages and stop rules

| Stage | Work | Stop if |
| --- | --- | --- |
| 0 | this protocol, committed | |
| 1 | fetch (≤ 5 GB, receipt with sha256), copy held-out inputs to `D:\rang\outputs\f3-*`; build f3sim-t unread; W3 subset check; Z2 on validation | W3 not a subset of T; **Stop-Z2** |
| 2 | Rust kernel, U3 weights; parity on validation; C1(U3) on LUNO MAIN_1 at 4 threads | parity fails after one round of fixes; **C1(U3) > 0.75** |
| 3 | T and A on the training and validation scans; injections; label audit; shards | label audit stop |
| 4 | training (3 seeds per class), median seed, τ on validation | |
| 5 | held-out sets, once: R1-R4, S1-S3, Q3 reported; cost; verdict; archive | |

Anything changed after a held-out result is post hoc, labelled, and followed by a held-out rerun on sets
not yet used for that change.

## 9. Licence of the weights

LUNO-trained weights are research-only. Shipping them is an owner decision (F1 item 4): the observer's
permission (Ben Hugo, 2026-10-29: use with the SARAO acknowledgement) covers use, not redistribution of
derived weights. ESO137 is CC BY 4.0 (Ramatsoku et al. 2020). F-SIM carries no data licence.

## 10. Not claimed

No better calibration or imaging. LUNO is processed (CASA flags, QuartiCal weights); ESO137 targets are
one track; simulated RFI is not shown to be realistic. Nothing about other bands or telescopes.

## Measured result

Not yet run.
