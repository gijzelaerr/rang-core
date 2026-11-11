# F4: a fast supervised RFI flagger for MeerKAT L-band, third protocol

Task F4, branch `fp-f4-flagger` from local main `3eab67c` (ahead of origin/main `c2fe7cc` by the V6
merge). Follows [F3](f3-flagger.md) (calibrators outcome F, targets stopped at the label audit) on the
owner's answer of 2026-11-11 ([finish plan](finish-plan.md), section 7 item 32: "1. sure"). **Status at
freeze: proposed; nothing implemented, fetched, run or trained.** Results go under "Measured result";
nothing above it changes except by dated, labelled amendment.

The goal is Landman's (2026-11-06): one weights file per observatory and band (MeerKAT L-band), separate
models for calibrators and targets, faster than the Rust Tricolour port with fewer tunable parameters,
**comparable** flag quality. Better calibration or imaging is not a goal and is not claimed. LUNO-derived
weights may be shipped (owner, 2026-11-11, item 32; answers F1 item 4) if an outcome allows it.

**Amendment 1, 2026-11-11, after the freeze (`89eb0b7`), before any Stage 1-5 run, training or
held-out read: an antenna-domain arm NA.** Owner decision (relayed by the coordinator, 2026-11-11):
"yes add it to F4": an autocorrelation arm, framed as an arm with its own pre-written gates against the
cross-correlation-only arm and T, not a change to N4. Source: V. Ravi 2026, arXiv:2611.01308 (digest
`research/digests/2026-11-11.md`, section 1). N4, its gates and its decision rule (sections 3-7) are
unchanged.

- *Data (checked 2026-11-11, row columns and channel tile 8 or 5 of non-held-out groups only).*
  Autocorrelations are in the data: LUNO MAIN_4 and MAIN_7 560 of 15,960 rows (56 antennas × 10 dumps),
  MAIN_1 1,792 of 50,000 (FLAG_ROW set on all of them); ESO137 chunks 2 and 10 1,647 and 1,586 of
  50,000. Every auto cell has FLAG = 1 (processing's `flag_autos`), but DATA is real: |XX| median
  318-411, |XY| 2.1-3.4. NA reads auto DATA and ignores the auto FLAG/FLAG_ROW. F-SIM has no autos.
- *Arm NA (frozen).* Per antenna k and parallel hand c ∈ {XX, YY}, `A_kc(t, f) = Re V_kk,c`.
  Scan-long part: `M_kc(f)` = median over t; `ρ_kc(f) = M_kc(f) / median_k M_kc(f)`, divided by its own
  median over channels; `D_k(f) = max_c (ρ_kc(f) − q25_f ρ_kc)` (fractional excess power). Time-local
  part: `T_k(t, f) = max_c (A_kc / M_kc − 1) / s_kc(f)`, `s_kc(f)` = 1.4826 × MAD over t of
  `A_kc / M_kc`. NA flags every cross cell (t, f) of every baseline containing k where `D_k(f) > δ` or
  `T_k(t, f) > 5`. δ from the grid 0.005, 0.01, 0.02, 0.05, 0.1, on the real validation scan only: the
  smallest δ whose added cells on uninjected DATA are ≤ T's (else the largest δ, reported). Arms
  reported: NA (W3 ∪ NA), **N4+NA** (N4 ∪ NA), N4.
- *Gates of the arm (held-out real sets of section 4; they do not enter section 7).*
  G1: N4+NA's R5 ≥ N4's R5 and N4+NA's added cells ≤ 1.5 × T's, per set.
  G2 (sanity): NA's recall of an auto injection (one antenna, band as F1's on that set, scan-long,
  `+10 · σ_auto` added to `A_kc`, `σ_auto` the radiometer noise from channel differences; seeds 19-21)
  ≥ 0.9. G3: on strong native consensus cells (R5's) of baselines whose antennas NA flags anywhere in
  the scan, N4+NA's recall − N4's ≥ 0.05.
  Reading: **NA-useful** if G1, G2, G3 hold; **NA-neutral** if G1 and G2 hold and G3 fails;
  **NA-harmful** if G1 fails; **NA-broken** if G2 fails. F1's R1 injections touch cross-correlations
  only, so NA cannot see them; R1 for N4+NA is reported, and any gain there is not credited to NA.
  N4 cannot see an emitter that is uncorrelated between antennas by construction; that is stated with
  every NA result.
- *Cost.* NA's wall and N4+NA's C1 are reported, not gated.
- *Status.* Proposed at this amendment's commit; implementation and δ must be done before Stage 5
  reads any held-out set, otherwise NA is reported as not run, not dropped.

**Amendment 2, 2026-11-11, before any Stage 1-5 run, training or held-out read; found by a unit
test on synthetic data.** On a calibrator-like scan (50 σ source in the parallel hands) with F1's
antenna-local injection, the parallel-hand deviation `w` inside the band is a **signed** shift (the
phasor adds to or subtracts from the source amplitude), so the 25th-percentile offset of step 3 is
dragged negative and `e^par` is high on the antenna's baselines **outside** the band too (ZE flagged
33 % of the antenna's non-injected cells, 0 % elsewhere).

- Step 3's offset `o_{b,c}` becomes the **median** over channels of the finite `w_{b,c}` (at least 16),
  robust to a signed shift on fewer than half of the channels. Step 6's `X` keeps the 25th percentile.
- T6's width cap becomes min(400, **0.45** · nchan) (was 0.6): 230 channels on ESO137, 400 on LUNO,
  so trained bands stay under half of the channels. F1's antenna-local bands (16 % and 18 % of the
  channels) and H3 (≤ 0.4 · nchan) are unchanged.
- Section 3's reading "unbiased by a band that covers up to 75 % of the channels" is withdrawn: the
  spectral planes now hold for bands on fewer than half of the channels.
- *Check (NumPy reference, same synthetic case, band 103 of 256 channels on antenna 9):* with the
  median offset, cross-plane threshold 5 finds 1.00 of the injected cells and flags 0 % of the
  antenna's other cells (q25: 33 %). The Rust tests after the rebuild run first in the chain.

## 1. What F3 got wrong, and what changes

| F3 failure | Cause | F4 change |
| --- | --- | --- |
| antenna-local injection (R1m): calibrators 0.024 against T 0.907, targets 0.166 against 0.700 | F1's antenna-local band is scan-long and wide (measured before this freeze, `make_injection` metadata only, seeds 19-21 and 41-43: **200-320 channels** of 2,048 on LUNO MAIN_4 and MAIN_7, 10 dumps; **60-92 channels** of 512 on ESO137 chunks 2 and 10, 27-28 dumps). `r^t` subtracts the per-channel time median, `r^f` a 33-channel running median: both absorb it, and the antenna medians are built from them. Training had antenna-local bands of 1-8 channels only | scan-scale spectral planes per baseline against the **other baselines'** spectrum, per antenna and for the array (section 3); training injection T6, wide antenna-local bands 9-400 channels (section 4) |
| targets: consensus labels failed the frozen audit | T and AOFlagger disagree by an order of magnitude on ESO137; weak consensus cells are flag extension or faint RFI | target labels from injections and F-SIM only (L-INJ, section 4); expertly flagged data requested from Landman (section 4) |
| R3 had no lower bound and R4 could not fail on targets (F3 Amendment 1) | | new gate R5 (recall of strong native consensus) and a lower bound on R3 (section 6) |
| S3 undecidable for calibrators (f3sim-t had no drifting cells in calibrator scans) | F-SIM's drifting carriers are random per scan | S3 falls back to H1 injections when a class has fewer than 1,000 drifting cells (section 6) |
| F3's held-out sets now motivate this design | F3 section 8: a change after a held-out result needs sets not used for it | all F4 held-out sets are new (section 4); F3's sets become training or before/after reports |

## 2. Arms

| Arm | What | Role |
| --- | --- | --- |
| **T** | Rust Tricolour port `core_flag.flag_rows`, CARACal `8f7bb363`, the class's first-pass YAML (as F3) | the bar |
| **A** | AOFlagger 3.5.0, `generic-default.lua`, W3's flags as input mask, ORed with W3 (as F3) | second established flagger |
| **N4** | the F4 network (section 3) inside W3; one weights file and one τ per class | **the method** |
| Z4 | W3 OR (max over the eight residual planes before `asinh` > 10) OR (max(`e^par_b`, `e^x_b`) > 5) | one-knob threshold on F3's and F4's planes; stop rule |
| ZE | W3 OR (max(`e^par_b`, `e^x_b`) > 5) | feature check (Stage 2) |
| U4 | N4 with its untrained initial weights (init seed 0) | chance; kernel cost |
| N3 | F3's weights at F3's τ (`2cdeee17…` calibrators τ −2.5; `6d44b33f…` targets τ −4.0) | reported: before/after |
| N | W3 only | reported |

**W3** is F3's (the class's YAML reduced to `flag_nans_zeros`, `apply_static_mask` `0~550`,
`flag_autos`, `combine_with_input_flags`). F3's subset check passed on both classes; it is repeated on
one new held-out scan per class at Stage 5 (stop and report if W3 flags a cell T does not). Every measure
scores only cells W3 leaves unflagged ("eligible").

## 3. Network N4 (frozen)

Per scan, per cross-correlation baseline b, on the (time, channel) plane; `F` as in F3.

**F3's fifteen planes, unchanged** (F3 section 3, steps 1-6; `rang.f3flag.features_numpy` is their
reference): `asinh r^t_c` (4), `asinh r^f_c` (4), the six antenna and array planes of `u^t`, `u^f`, and
the mask `F`. They stay in planes 0-13 and 22 (the mask moves to the last plane).

**Eight new scan-scale spectral planes** (float64, stored float32; constant over time within a scan; 0 on
`F`). Correlations are split into families φ: parallel (XX, YY; indices 0, 3) and cross (XY, YX;
indices 1, 2).

1. `P_{b,c}(f)` = F3's step 3 (median over unflagged times of `a_c = |V_c| / σ_bc`); NaN where no time is
   unflagged or the baseline has no noise scale.
2. Array spectrum `B_c(f)` = median over baselines of the finite `P_{b,c}(f)` (at least 3, else NaN). This
   is the reference: other baselines, not the baseline's own spectrum, so a band wider than half of the
   channels is still visible.
3. Deviation `w_{b,c}(f) = P_{b,c}(f) − B_c(f)`; offset `o_{b,c}` = 25th percentile over channels of the
   finite `w_{b,c}` (NumPy's linear interpolation; at least 16 finite channels, else NaN); the 25th
   percentile is unbiased by a band that covers up to 75 % of the channels.
4. `e^φ_b(f) = max_{c∈φ} |w_{b,c}(f) − o_{b,c}|` (finite values only).
5. Per antenna k and channel, `E^φ_k(f)` = median of `e^φ_b(f)` over baselines containing k (at least 3
   finite, else NaN).
6. Array excess `X^φ(f) = max_{c∈φ} (B_c(f) − q25_f(B_c))` (signed; the 25th percentile over channels of
   the finite `B_c`, at least 16).
7. Planes 14-21, for φ ∈ {par, cross}: `asinh e^φ_b`, `asinh max(E^φ_p, E^φ_q)`, `asinh min(E^φ_p, E^φ_q)`,
   `asinh X^φ` (F3's `pair` rule when one antenna median is NaN; NaN → 0).

Reading: antenna-local, scan-long RFI on antenna k raises `P` on k's baselines only, so `B` is unchanged
and `e`, `max(E_p, E_q)` are high across the **whole** band while `min(E)` stays low; the network's
63-channel receptive field does not need to reach the band edges. On calibrators the parallel hands
carry the source (about 50-70 σ per visibility), so an additive phasor of 10 σ shifts their amplitude by
a signed amount that depends on phase; the cross hands are noise-dominated in both classes and show it as
a positive excess, hence the two families. Array-wide scan-long RFI raises `B` and shows in `X`. RFI on for
less than half of the dumps does not move `P` and stays the job of `r^t`.

**Network.** F3's stack with 23 inputs: 3×3 convolutions, dilations 1, 2, 4, 8, 16, 8 hidden channels,
ReLU, "same" zero padding, 1×1 head; receptive field 63 × 63. Weights: 9·23·8 + 8 + 4·584 + 9 =
**4,009**. Flag where logit > τ and the cell is not in `F`, uniform over correlations.

**Implementations.** Rust `core/src/f4flag.rs` (reuses `f3flag`'s residuals, aggregates and convolution;
F3's numerics are not changed), `rang._core.f4flag_features` and `f4flag_logits`; NumPy reference
`rang.f4flag.features_numpy`; JAX network `rang.f3net` with `nplanes=23`. Parity (frozen, as F3):
features max |Δ| ≤ 1e-4 after `asinh` on one validation scan per class; logits |Δ| ≤ 1e-4 at p99.9,
≤ 1e-3 max, flag disagreement ≤ 1e-5 of cells.

## 4. Data and labels

**Never read** (exact-name allowlists in code): LUNO `MAIN_16`-`MAIN_19` (E2-B), ESO137 ms1 primary and
target `MAIN_4`-`MAIN_6` (E2-A), and the F4 held-out sets below until Stage 5 (W3's subset check at Stage
5 is their first read). ESO137 MAIN_0 chunks 1, 3, 5, 7, 9, 15 and LUNO MAIN_8-MAIN_11, MAIN_13,
MAIN_15 are reserved, unread.

**Calibrators** (LUNO, 1830−211 unless stated; DATA and FLAG tiles 8-23, channels 1024-3071, row chunk 0).

| Set | Role | Source |
| --- | --- | --- |
| MAIN_1 (1934−638, scan 2), MAIN_2 (scan 3), MAIN_4, MAIN_5, MAIN_6 | train (real) | on disk (`f3-20261110-02-inputs`, `-01-fetch`); MAIN_1 and MAIN_2 were F3's held-out sets |
| MAIN_7 | validation (real) | on disk |
| f2sim-1..3 / f2sim-v calibrator scans | train / validation (simulation) | F2's |
| **MAIN_0 (3C 286, scan 1)**, **MAIN_12**, **MAIN_14** | **held-out real test** | new fetch, whole GETs with sha256 receipt; HEAD total ≤ 8 GB, else MAIN_14 is dropped |
| **f4sim-t calibrator scans** | **held-out simulation test** | new: `f2flag_sim`, seeds 20264101-05 (registered in `simtruth.SEEDS`), start 2024-08-22T05:00, odd antennas, test role |

MAIN_0 is a second calibrator source the network never sees; MAIN_12 and MAIN_14 are later 1830−211 scans.

**Targets** (ESO137 `ms1_target.zarr` MAIN_0, channels 640-1151; 210 s row chunks, contiguous in time).

| Set | Role |
| --- | --- |
| chunks 0, 2, 4, 6, 8, 14, 16 | train (real); 0, 14, 16 were F3's held-out set |
| chunk 10 | validation (real) |
| f2sim-1..3 / f2sim-v target scans | train / validation (simulation) |
| **chunks 11, 12, 13** | **held-out real test** (one block of 630 s; 13 borders training chunk 14) |
| **f4sim-t target scans** | **held-out simulation test** |

A target result remains conditional on one track.

**Training injections** (`rang.f4flag`; F3's T1-T5 unchanged, plus T6). Seeds: shards per (class, role,
kind) start at calibrator train real 20264201, sim 20264251; validation real 20264301, sim 20264311;
target train real 20264601, sim 20264651; validation real 20264701, sim 20264711; realisation k adds k
(real scans 6 realisations per training scan, 2 per validation scan, as F3).

- **T6 wide antenna-local** (the missed class): 1-3 events per realisation; one antenna drawn from the
  live antennas; band width log-uniform 9 to min(400, 0.6 · nchan) channels at a uniform offset; all
  dumps of the scan with p = 0.75, else a run of 2 to nt dumps; per-baseline amplitude × U(0.5, 1) (as
  T3); spectral envelope flat (p = 0.5) or raised-cosine edges over 10 % of the width at each side. All
  other per-event draws as F3 (α log-uniform 3-300 σ_b, coupling, fringe rate, modulation).

So antenna-local RFI of every width from 1 to 400 channels is now in training (T3 1-8, T6 9-400): F1's
antenna-local test is no longer a held-out morphology, only a held-out-data test.

**Held-out morphologies (never in training):** F3's H1 (drifting carrier) and H2 (antenna cluster), and
**H3 antenna pair**: two distinct live antennas with the **same** band (width uniform 0.1-0.4 · nchan),
scan-long, on every baseline of either antenna (T6 events draw independent bands, so a shared band on two
antennas is not trained).

**Labels.**

- Simulation (both classes): F3's (positive where max(truth A, injection A) ≥ 3, negative where both 0).
- **Calibrators, real, L-A1s**: F3's Amendment 1 labels with the strength on the uninjected DATA taken as
  `s = max(u^t, u^f, e^par_b, e^x_b)` (before `asinh`): positive if injection A ≥ 3, or T and A both flag
  and s ≥ 3; negative if not injected and flagged by neither; ignored otherwise and on `F`.
- **Targets, real, L-INJ**: positive if injection A ≥ 3; negative if not injected, flagged by neither T
  nor A, and s < 3; ignored otherwise (every native cell flagged by T or A, or with s ≥ 3) and on `F`.
  Native target RFI is learned from F-SIM only; R5 measures what this costs.
- A third of all realisations get F2's synthetic input flags (as F3). Shards: 256 baselines per
  realisation, float16 features, int8 labels, under `D:\rang\outputs\f4-*`; features on the whole array.

**Label audit (frozen, before training).** Per real training scan: positive (injected, consensus),
ignored and negative counts; T's and A's recall of realisation 0's injected cells; median s of positive
and negative cells. **Stop if** (calibrators) strong consensus exceeds 10 % of eligible cells on any scan;
(targets) ignored uninjected cells exceed 40 % of eligible cells, or injected positives are below 0.1 % of
eligible cells, on any realisation.

**Expert labels (asked of Landman, not posted by this task).** Proposed text, for issue #1 after the owner
has seen it:

> For the target model we need expertly flagged MeerKAT L-band target data: the visibilities as they
> were before flagging (online/static flags only) and the final FLAG you would image with, same rows,
> ideally one full-array track or three or more target scans of 10 min or longer, with a line on what
> was flagged by hand and what by a strategy, and permission to train on them and ship weights derived
> from them. Two different fields or dates would let us hold one out.

If such data arrive before Stage 5 they enter F4 only as a reported measure, E1 (per arm: recall of the
expert's flags outside W3, and added cells outside the expert's flags); training on them is F5. If
nothing arrives, the target outcome stands on L-INJ and F-SIM and is stated as "comparable on
injections, simulation and strong consensus; not checked against expert flags".

## 5. Training (frozen)

F3's: JAX on the RTX 4070 Ti in WSL (venv `~/Build/tmp/<date>-f4-jaxcuda`, removed at the end;
`XLA_PYTHON_CLIENT_PREALLOCATE=false`), shards built natively by the Rust kernel; Adam 1e-3, 30,000
steps, batch 32 windows of one baseline × 256 channels, real : simulation = 1 : 1, unweighted BCE over
non-ignored cells, He-normal init seeds 1, 2, 3 per class, batch rng 1000 + seed; the weights file is the
median seed by validation loss.

**Threshold τ (validation only).** Grid −6, −5.5, …, +2. The τ with the largest pooled validation
recall of positive cells such that N4's added cells on the real validation scan's uninjected DATA are
≤ T's there; if none qualifies, the τ with the fewest added cells (reported). Stored beside the weights'
sha256. At most one change of hyperparameters per class, on validation, by dated amendment, before any
held-out set is read.

## 6. Measures (frozen; per class, T the reference)

**Held-out real** (calibrators: MAIN_0, MAIN_12, MAIN_14; targets: ESO137 chunks 11, 12, 13).

| Gate | Measure | Bar |
| --- | --- | --- |
| R1 | F2's injection test (F1's `inject_mask`: narrowband, time-burst, antenna-local, single-baseline; seeds 19, 20, 21; 10 σ_b; eligible cells), recall pooled over seeds, sets and morphologies | ≥ T − 0.05 |
| R1m | the same per morphology | each ≥ T − 0.10 |
| R2 | H1, H2, H3 at 10 σ_b, seeds 31, 32, 33, recall per morphology pooled | each ≥ T − 0.05 |
| R3 | added cells on uninjected DATA, per set, ratio to T | ≤ 1.5, and ≥ 0.5 × min(T, A) / T |
| R4 | Jaccard of added cells with T, per set | ≥ J(A, T) − 0.05 (calibrators; reported for targets, where it cannot fail) |
| R5 | recall of strong native consensus: uninjected eligible cells flagged by T and A with s ≥ 5, per set | ≥ 0.80 |

**Held-out simulation** (f4sim-t, class scans).

| Gate | Measure | Bar |
| --- | --- | --- |
| S1 | recall of truth cells with A ≥ 10 | ≥ T − 0.05 |
| S2 | flagged fraction of eligible cells outside the truth mask dilated by one cell | ≤ T + 0.01 |
| S3 | recall of drifting cells with A ≥ 10; if the class's scans have fewer than 1,000 such cells, H1 at 10 σ_b (seeds 61, 62, 63) injected into them instead | ≥ T − 0.05 |

Q1 by morphology and strength decade, F3's sets (LUNO MAIN_1, MAIN_2; ESO137 0, 14, 16 are training now, so
N3 against N4 there is reported as fit, not test) and E1 if available: reported, not gated.

**Cost**, as F3 (timing claims allowed): LUNO MAIN_1 and ESO137 chunk 0 (label-free, comparable with F3's
0.343), rows in memory to flags in memory, N4 = W3 + `f4flag_logits` + threshold against T with the full
YAML; native Windows, `RAYON_NUM_THREADS` 4 and 1, three repeats alternating, median, heavy lock held;
**idle host**: other processes ≤ 1 logical CPU in the second before each repeat, else provisional. C2
peak working set in separate processes.

| | Beats (material) | Matches | Worse |
| --- | --- | --- | --- |
| C1 wall, N4 against T, 4 and 1 threads | **≤ 0.5** | 0.5-1.1 | > 1.1 |
| C2 peak working set against T | ≤ 0.8 | 0.8-1.2 | > 1.2 |

**P** as F3 (T1 kinds under half of T's, no retraining between sets).

## 7. Decision rule (per class, first that applies)

| Outcome | Condition | Reading |
| --- | --- | --- |
| **Stop-E** | ZE's recall of F1's antenna-local injection (seeds 41, 42, 43) on the real validation scan < 0.5 | the new planes do not see the missed class; no training for that class |
| **Stop-Z4** | Z4 meets R1, R3 on the real validation scan (F2's injections, seeds 41-43) and S1, S2 on f2sim-v | a threshold suffices; report; no training |
| **F** | any of R1, R1m, R2, R3, R4 (calibrators), R5, S1, S3 fails, or C1 > 1.1 | not comparable, or not faster |
| **H** | all quality gates pass, C1 in 0.5-1.1 at either thread count | comparable, not materially faster |
| **S** | all quality gates pass, C1 ≤ 0.5 at 4 and 1 threads, C2 not worse, P holds | **Landman's request met** on these data; weights may ship (item 32) |
| **S−** | S except S2 or P | as S, with that failure stated |

Targets add, whatever the outcome: "labels from injections and simulation; not checked against expert
flags" unless E1 was measured. Against A as F3: no novelty claim follows from beating T alone.

## 8. Stages and stop rules

| Stage | Work | Stop if |
| --- | --- | --- |
| 0 | this protocol, committed before any code | |
| 1 | fetch LUNO MAIN_0, MAIN_12, MAIN_14 (HEAD ≤ 8 GB, receipt), unread; build f4sim-t unread; Z4 and ZE on validation | **Stop-E**, **Stop-Z4** |
| 2 | Rust kernel, U4 weights; parity on validation; C1(U4) on LUNO MAIN_1 at 4 threads | parity fails after one round of fixes; **C1(U4) > 0.45** |
| 3 | T and A on training and validation scans (F3's caches reused where they exist); injections; label audit; shards | label audit stop |
| 4 | training (3 seeds per class), median seed, τ on validation | |
| 5 | W3 subset check on one held-out scan per class; held-out sets, once: R1-R5, S1-S3; cost; verdict; archive | W3 not a subset of T |

Anything changed after a held-out result is post hoc, labelled, and needs a held-out rerun on sets not
yet used for that change (the reserved chunks and groups in section 4).

## 9. Licence of the weights

The owner allowed shipping LUNO-derived weights (2026-11-11, item 32), with the SARAO acknowledgement and
Ben Hugo's permission of 2026-10-29 cited. ESO137 is CC BY 4.0 (Ramatsoku et al. 2020). Weights ship
only with outcome S or S−.

## 10. Not claimed

No better calibration or imaging. LUNO is processed (CASA flags, QuartiCal weights); ESO137 targets are
one track; simulated RFI is not shown to be realistic. Nothing about other bands or telescopes.

## Owner decisions

- 2026-11-11 (finish plan, section 7 item 32), on F3's decisions: "1. sure. 2. ship them sure. 3. only
  delete if we run out of data. 4. sure." F4 follows; LUNO-derived weights may ship; F2/F3 simulation
  data stay unless D: runs low; F3's message is posted to issue #1.
- 2026-11-11, relayed by the coordinator: "yes add it to F4": the antenna-domain (autocorrelation) arm,
  Amendment 1.
- Open: posting section 4's request for expertly flagged target data to Landman (issue #1).

## Measured result

Runs under `D:\rang\outputs\f4-20261111-NN-*` (each with `.code/`, `.log`, `.time`, written by
`examples/f4_run.py`). Native Windows unless stated; AOFlagger and training in WSL.

### Before the freeze (no held-out read)

- F1's antenna-local band width per set (`make_injection` metadata, W3 eligibility, no DATA read by the
  policy; seeds 19-21, 41-43): LUNO MAIN_7 201-320 channels, MAIN_4 200-320; ESO137 chunk 10 60-92,
  chunk 2 61-92 (5-7 s per set).
- ESO137 MAIN_0 row chunks (TIME only): 0-16 are 50,000 rows of 27-28 dumps, about 208 s apart; 17 has
  950 rows of one dump (reserved).

### Implementation (Stage 2 code, before any run)

- Rust `core/src/f4flag.rs`: F3's residual pass once per baseline (it now also returns the time-median
  spectrum `p`, F3's numerics unchanged), F3's antenna and array medians, then `B`, `e`, `E`, `X`
  (rayon over channels, baselines and antennas), planes, and F3's network with 23 inputs
  (`f3flag::network` and `weight_count_for` take the input count). Bindings `f4flag_features`,
  `f4flag_logits`.
- Python `rang.f4flag`: guards (held-out sets refused without `heldout=True`), loaders via F3's
  `read_luno`/`read_eso`, the NumPy reference, `strength_rows` (s), Z4, ZE, N4, T6, H3, L-A1s, L-INJ,
  R5's cells. F3's injector gained `codes`, `jitter` and an `envelope` argument (defaults keep F3's
  draws); `rang.f3net.init_params` takes `nplanes`; `examples/f3_train.py` takes `--nplanes`.
- Tests: `cargo test f4flag` (weight count 4,009; NumPy's percentile; a 30-of-64-channel scan-long band
  on one antenna is high in the cross spectral plane and the antenna max, low in the antenna min and in
  F3's `r^f`); `tests/test_f4_flag.py` (Rust against NumPy ≤ 1e-4 and F3's planes unchanged; logits
  against JAX; F1's antenna-local injection widened to 60-140 of 256 channels at 10 σ on a 50-σ
  calibrator-like scan: ZE ≥ 0.9 recall, Z2 ≤ 0.2, ZE false flags ≤ 1 %; T6/H3 seeded, widths, eligible
  cells; labels; guards).

### Arm NA (Amendment 1), implemented after the amendment

- `rang.f4flag.load_autos`, `na_statistics`, `na_antenna_hits`, `na_flags`, `auto_inject`;
  `f4_eval.py na-delta` (δ on validation) and arms `NA`, `N4NA` in `f4_eval.py real` (`--na-delta`;
  G2 and G3 written to the result). Test: synthetic autos (radiometer noise 1e-3, per-antenna
  bandpasses within 0.2 %), a 100-channel scan-long +10 σ_auto band on one antenna: ≥ 0.9 found, other
  antennas < 1 %, crosses of the other antennas < 2 %.
- Validation diagnostic (no flags compared, no held-out read): `D` median / p90 / p99 0.015 / 0.038 /
  0.102 on LUNO MAIN_7 (56 antennas), 0.028 / 0.071 / 0.121 on ESO137 chunk 10 (61); fraction of
  (antenna, channel) above δ = 0.005 … 0.1: 0.75, 0.61, 0.35, 0.04, 0.01 (LUNO) and 0.83, 0.76, 0.61,
  0.22, 0.03 (ESO137). Antenna bandpass mismatch alone exceeds the smaller δ, so the δ rule will pick
  0.05 or 0.1, and NA then sees only scan-long bands that raise power by 5-10 %. G2's +10 σ_auto is
  about +0.8 % of the auto power (σ_auto / A ≈ 1/√(Δν τ) = 7.7e-4 at 209 kHz and 8 s), so **G2 will
  probably fail at the δ the rule picks** (NA-broken) unless the time-local part catches it; that
  follows from the frozen design and is recorded here before anything is run.

- **Expectation, recorded before any NA run: NA is likely NA-broken (G2) and may be NA-harmful (G1)
  as frozen.** At δ = 0.1 about 1 % of LUNO (antenna, channel) pairs are above δ; every baseline of
  such an antenna is flagged, so of order 2 % of cross cells against T's 1.3 %. A label-free prototype
  on the same validation autos (not adopted, `log ρ` minus a 3× clipped degree-5 polynomial per antenna
  and hand, z in MAD units): clean (antenna, channel) pairs with z > 5 2.6 % (LUNO MAIN_7) and 0.1 %
  (ESO137 chunk 10); a scan-long band on antenna 5 (300 or 80 channels) is found at z > 5 for 15 % of
  its channels at +10 σ_auto and 96 % at +100 σ_auto on LUNO, 0 % at both on ESO137. A working
  antenna-domain detector needs its own design on validation (an Amendment 2 before Stage 5, or a
  separate task); the owner or coordinator decides. The frozen NA runs as written either way.

### Staged runs

Queued in order by `examples/f4_queue.py` (each step under the main checkout's `tools/heavy_lock.py`,
first come, first served since main `bd15126`; shared slots per step, `SHARE` in the script, and
exclusive only for C1(U4) and Stage 5's cost timing; E2 and other lock
holders first; the frozen stops are checked between steps and written to
`D:\rang\outputs\f4-20261111-queue.json`):

```bash
.venv/Scripts/python examples/f4_queue.py            # sim, stage1, parity, c1u4, shards
.venv/Scripts/python examples/f4_queue.py --from c1u4 # resume at a step
```

| Step | Run | Stop |
| --- | --- | --- |
| sim | `-02-sim-test` (`f2_simulate.py RUN f4sim-t`) | |
| stage1 | `-03-stage1-calibrator`, `-03-stage1-target` (`f4_eval.py stage1`, F3's T/A caches `-13`, `-08`) | Stop-E, Stop-Z4 per class |
| nadelta | `-03-nadelta-calibrator`, `-03-nadelta-target` (`f4_eval.py na-delta`, Amendment 1's δ) | |
| parity | `-04-parity-calibrator`, `-04-parity-target` (`f4_parity.py`, U4) | parity |
| c1u4 | `-05-c1u4` (`f4_cost.py time --n4 U4`, LUNO MAIN_1, `RAYON_NUM_THREADS=4`, idle host) | C1(U4) > 0.45 |
| shards | `-06-shards-cal`, `-07-shards-target` (`f4_shards.py`, validation then train, `--flags-from` F3's caches; T and A computed for MAIN_1, MAIN_2 and ESO137 0, 14, 16) | label audit |

The held-out fetch (`-01-fetch`, `f4_fetch.py`) ran first, network only, nothing decoded: 126
objects, 4,542,359,207 bytes (all three groups, under the 8 GB bar), 27.6 min, receipt with sha256.

**Queued 2026-11-11 15:51 (host clock)** as a detached process (`outputs/f4-chain.sh`, ignored): the
extension build under the heavy lock, then `tests/test_f4_flag.py`, `test_f3_flag.py`, `test_f2_sim.py`,
then `examples/f4_queue.py`; progress in `D:\rang\outputs\f4-20261111-00-build\chain.log`. Three
tests of `test_f4_flag.py` (Rust against NumPy, logits against JAX, the antenna-local band) need the
rebuilt extension and had not run at the code commit; the chain stops before Stage 1 if they fail.

**Stage 4, training (WSL, GPU; after the audit, by hand):**

```bash
wsl -d Ubuntu -- bash -lc 'uv venv ~/Build/tmp/20261111-f4-jaxcuda && uv pip install -p ~/Build/tmp/20261111-f4-jaxcuda "jax[cuda12]" numpy'
```

```bash
wsl -d Ubuntu -- bash -lc 'cd /mnt/c/Users/gijsm/Worktrees/rang/fp-f4-flagger && for c in calibrator:06-shards-cal target:07-shards-target; do k=${c%%:*}; d=${c#*:}; for s in 1 2 3; do XLA_PYTHON_CLIENT_PREALLOCATE=false python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots 4 --mem 16 -- ~/Build/tmp/20261111-f4-jaxcuda/bin/python examples/f3_train.py /mnt/d/rang/outputs/f4-20261111-$d/$k /mnt/d/rang/outputs/f4-20261111-08-train-$k/seed-$s --seed $s --nplanes 23; done; done'
```

Then per class the median seed by validation loss, and τ (native):

```bash
.venv/Scripts/python examples/f4_run.py f4-20261111-09-tau-calibrator --lock -- C:/Users/gijsm/Worktrees/rang/fp-f4-flagger/.venv/Scripts/python.exe examples/f4_tau.py RUN/tau.json --class calibrator --shards D:/rang/outputs/f4-20261111-06-shards-cal --n4 D:/rang/outputs/f4-20261111-08-train-calibrator/seed-K/weights.npz
```

**Stage 5 (held-out, once; `--heldout`):** per set `f4_eval.py real RUN/<set>.json --set luno:MAIN_0
--heldout --n4 W.npz@TAU` (then `luno:MAIN_12`, `luno:MAIN_14`; targets `eso:11`, `eso:12`, `eso:13`);
`f4_eval.py sim RUN/sim.json D:/rang/outputs/f4-20261111-02-sim-test/f4sim-t --class <class> --n4 …`;
cost `f4_cost.py time` at `RAYON_NUM_THREADS` 4 and 1 on `luno:MAIN_1` and `eso:0`, and `f4_cost.py rss`
per arm; quality runs under `f4_run.py … --lock --slots 4 --mem 16`, the cost timing under
`f4_run.py … --lock` (exclusive).

## For the coordinator

- **Commits (branch `fp-f4-flagger`, from local main `3eab67c`):** `89eb0b7` protocol (frozen before
  code); `249c282` Amendment 1 (NA); `0f2954d` code; later commits notes, the test fix and Stage 1
  reporting. Not pushed.
- **Not run here:** the full check-all (left to the coordinator at merge); training, τ and Stage 5.
  Three extension tests of `test_f4_flag.py` run first in the detached chain (they need the rebuilt
  `rang._core`; the chain stops if they fail).
- **Chain:** detached bash running `outputs/f4-chain.sh` (worktree, ignored); log
  `D:\rang\outputs\f4-20261111-00-build\chain.log`; verdicts `D:\rang\outputs\f4-20261111-queue.json`.
  It only waits on the heavy lock; it does not otherwise yield to E2.
- **Run outputs (ignored):** `D:\rang\outputs\f4-20261111-NN-*`; `-01-fetch` 4.54 GB.
- **`research/STATE.md`, new log paragraph (when results exist):** "F4, 2026-11-11 (protocol frozen;
  code; Stages 1-3 queued; [f4-flagger.md](f4-flagger.md)): F3's network with eight scan-scale
  spectral planes against the array (23 inputs, 4,009 weights) for wide-band scan-long antenna-local
  RFI, T6 injections 9-400 channels, target labels from injections and simulation, new held-out sets
  (LUNO MAIN_0, MAIN_12, MAIN_14; ESO137 11-13; f4sim-t), and an autocorrelation arm NA (Amendment 1)."
- **`research/finish-plan.md`, section 6, Landman:** "F4 protocol frozen 2026-11-11 (`f4-flagger.md`);
  the request for expertly flagged target data (section 4) awaits posting to issue #1."
- **`research/tool-timings.md`:** rows added in this branch.
