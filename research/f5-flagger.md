# F5: a fast supervised RFI flagger for MeerKAT L-band, fourth protocol

Task F5 (issue #40, DL3 of [dl-plan.md](dl-plan.md), track L), branch `dl3-f5` from origin/main
`dd6adc5d`. **Status at freeze: proposed; nothing implemented, trained or scored. No held-out set
has been read by F4 or F5.** The draft that stood here (branch `f5-draft`, written while F4 ran) is
in the git history; this version replaces it. Results go under "Measured result"; nothing above it
changes except by dated, labelled amendment (post hoc for anything a result could have shown).

**Why a fourth protocol.** F4 (`research/f4-flagger.md`) stopped on the calibrators at its Stage 2
cost gate: C1(U4) read 0.441, 0.452, 0.458 and 0.459 against a bar of 0.45, no reading clean, and
the coordinator stopped it on 2026-11-17 without reading a held-out set. Its quality steps had
passed what they reached: ZE's recall of F1's antenna-local injection 1.000 (calibrators) and 0.993
(targets) on validation; τ −1.0 with validation recall 0.954 at T's flag count (209,027 against
209,120 added cells on LUNO MAIN_7); C2 1.00. Its targets stopped at the label audit (ignored
uninjected cells 0.470-0.640, bar 0.40). F5 is built around those two stops: section 2 is about
cost, section 4 about labels.

Inputs: Landman Bester's review of F3 (issue #1, comment 6943748188, 2026-11-17) and his answers
(comment 6944726203, 2026-11-17); the owner's v0.4.0 rules ([next-session.md](next-session.md),
dl-plan sections 0, 6 and 10): no antenna-indexed inputs; gates G-sub, G-drop, G-perm, G-chan and
G-obs frozen before training; PyTorch for training; weights as ONNX; everything `off` by default.
Landman's status comment of 2026-11-19 (comment 7002083361) told him F5 freezes without waiting.

**Goal** (Landman, 2026-11-06, unchanged since F2): one weights file per observatory and band
(MeerKAT L-band), separate calibrator and target models, faster than the Rust Tricolour port (T)
with fewer tunable parameters, comparable flags. Calibrators first; the calibrator model can ship
alone. **No novelty claim**; better calibration or imaging is not a goal.

## 0. Landman's review against F4, and what F5 does

| Review item | In F4 (on main: `core/src/f4flag.rs`, `python/rang/f4flag.py`) | F5 |
| --- | --- | --- |
| Diagnosis: r^t, r^f and antenna medians miss a wide, scan-long, one-antenna event | same diagnosis; F4's spectral planes found it (ZE 1.000 / 0.993) | kept: F4's eight planes (section 2) |
| 1. Antenna planes from a robust factorisation of amplitudes | partly (scan-long spectra against the array median) | per time block, solved γ_p, low-order fit (2c) |
| 2. Noise-variance factorisation | no | 2d |
| 3. Antenna-local events to about 400 channels, coherent and noise-like, scan-long and partial | coherent only (T6) | T6 plus noise-like T7 (section 3) |
| 3. A new held-out morphology (two antennas, slow ramp) | H3 (same band on two antennas) | H3 plus H4, H4n ramps |
| 3. Classical per-antenna OR fallback | no | W4, chosen by a rule before any held-out read (section 3) |
| 4. Labels: positive injected A ≥ 3; ignored T or A flags, 0 < A < 3, F | no (L-A1s, L-INJ) | both classes (section 4) |
| 4. Image-domain gate | no | reported arm I (section 7) |
| 5. Reference A from a CARACal MeerKAT AOFlagger strategy | no | not in F5: A stays `generic-default.lua` (section 5) |
| Second reply: `pfb hci` settings; gain TV for validation; agent review of waterfalls | no | reported arms, targets stage (section 7) |
| v0.4.0: no antenna index; G-sub, G-drop, G-perm, G-chan, G-obs | not tested | section 8, gated |
| F4's own stop: Stage 2 cost 0.441-0.459 against 0.45 | | section 2: cost first |

## 1. What F3 and F4 miss (a reading of the code on main `dd6adc5d`, not a run)

**F3's fifteen planes** (`f3flag::residuals`, `aggregates`): per baseline and correlation `σ_bc`
is one MAD of adjacent-channel differences per scan; `a = |V| / σ_bc`; `P(f)` the time median of
`a`; `r^t = a − P`; `S(f)` a 33-channel running median of `P`; `r^f = a − g(t) S(f)`; antenna
planes are medians of `u^x = max_c r^x_c` over the antenna's baselines. A band on for every dump
is absorbed by `P`, and one wider than about 16 channels by `S`, so F1's antenna-local event (one
coherent phasor on all 52-55 baselines of one antenna, 178-322 of 2,048 channels on LUNO, 60-92 of
512 on ESO137, every dump) is invisible except at its edges: F3's recall 0.024 against T's 0.907.

**F4's eight spectral planes** (`f4flag::spectra`): `w_b,c(f) = P_b,c(f) − B_c(f)` against the
array median `B`, one median offset per baseline and correlation (Amendment 2), `e^φ_b` per family
(parallel XX, YY; cross XY, YX), antenna medians `E^φ_k`, array excess `X^φ`. They see the missed
event (ZE 1.000 on calibrators) for bands on fewer than half of the channels and on for more than
half of the dumps. They do not see: an antenna event on fewer than half of the dumps (`P` is a time
median); a per-antenna bandpass difference is not modelled (it stays in `e`); noise-like antenna
RFI (excess variance, little change in `|V|`'s median). The autocorrelation arm NA was expected to
fail its own sanity gate (δ at the top of its grid on both classes) and is not carried into F5.

**Signed shifts on calibrator parallel hands** (F4 Amendment 2): an additive phasor of 10 σ on a
50-70 σ source moves |V| by ±10 σ cos(φ_pq − θ); the source phase differs by baseline, so the
median over an antenna's baselines of the log-amplitude shift can be near zero while their scatter
is large. 2c adds a dispersion plane for that.

## 2. Cost first, then features, network and plane budget

### 2a. F4's stop, measured again before this freeze

Pre-freeze profile, 2026-11-19, glacier, native Windows, heavy lock shared (4 slots), host
otherwise nearly idle but **not** an exclusive hold: **provisional**. LUNO MAIN_1 (a training scan,
41,786 rows × 2,048 channels, 85.6 M cells), `RAYON_NUM_THREADS=4`, extension built from
`dd6adc5d`. Script and record: `outputs/dl3-f5/profile_f4.py`, `profile_f4_t4.json`,
`profile_feat.py`, `profile_feat_t4.json` (ignored outputs; numbers copied here).

| Step | Wall (s) |
| --- | ---: |
| T (`flag_rows`, full first-pass YAML) | 34.4 |
| W3 | 1.45, 1.49 |
| F3 kernel (`f3flag_logits`, 15 planes, untrained weights) | 11.1, 11.7 |
| F4 kernel (`f4flag_logits`, 23 planes, untrained weights) | 13.7, 14.2 |
| F3 / F4 features for 27 baselines (the passes over all baselines plus 27 baselines' planes) | 3.1 / 3.3 |
| F3 / F4 features for 275 baselines | 3.8 / 4.4-5.0 |

Readings:

- C1 from these walls: F3's arm (W3 + kernel) 12.9 / 34.4 = 0.37; F4's 15.4 / 34.4 = 0.45, as F4's
  exclusive attempts read (0.441-0.459). **T has become faster** since F3 timed 0.343 against T's
  48.1 s (2026-11-10): T read 42-47 s on 11-12 and 11-17 morning, 34-36 s on 11-17 evening and
  34.4 s here. F3's network against today's T would be about 0.37, not 0.34. Headroom has to be
  held against T measured in the same hold, never against an old T.
- Every input plane costs one `asinh` per cell. Rust's f64 `asinh` takes 12.7 ns per call
  (micro-benchmark, glacier, `rustc -O`, 10^8 calls; f32: 8.1 ns). F3 computes 14 per cell, F4 22:
  85.6 M × 22 × 12.7 ns / 4 threads ≈ 6.0 s of F4's 14 s. Eight of F4's 22 are on planes that are
  constant over time (`e`, `E`, `X`), so 2.2 s of F4's wall is the same `asinh` repeated over dumps.
- The fixed passes (residuals and antenna medians over all baselines) cost about 3 s; `planes`
  recomputes each baseline's residuals a second time.
- The draft's option B (F3's 15 + 10 new planes, about 0.40-0.44) does not hold against these
  numbers: at about 0.009 of C1 per per-cell plane, 25 per-cell planes would read about 0.46 before
  the new feature passes. Adding planes as per-cell inputs is what F5 cannot afford.

### 2b. Cost rules (frozen)

1. **Planes constant over a block enter at block resolution.** F4's eight spectral planes are
   computed (and transformed) once per (baseline, channel); 2c's and 2d's planes once per (antenna
   pair, time block, channel block). None is materialised per cell at inference.
2. **A linear stem.** The network's first operation is a 1×1 linear map (no activation) from all
   inputs to 8 channels. Because it is linear, it splits exactly into a per-cell part (F3's 15
   planes), a per-(baseline, channel) part (F4's 8) and a per-block part (2c, 2d), each evaluated
   at its own resolution and summed per cell (8 additions per part). Float32 reassociation is the
   only difference from the materialised form; the parity bars (2f) cover it.
3. **`asinh` in f32** in F5's kernel (any implementation within 2 × 10^-6 absolute of f64 `asinh`
   over finite f32 inputs, unit-tested). F3's and F4's kernels are not changed.
4. **Numerics-preserving optimisation** (reusing a pass, layout, vectorisation) is allowed at any
   time before Stage 6 if the parity bars still hold; it is recorded with its commit.
5. Memory: C2 (peak working set against T, separate processes, decode included) is measured, so a
   cache that keeps per-cell residuals between passes is allowed only if C2 stays ≤ 1.2.

### 2c. Robust amplitude factorisation (review item 1)

Per scan, correlation c, time block τ of `n_τ = 2` dumps (the last block takes 3 if nt is odd) and
channel block of 8 channels:

1. `y_pq,c(τ, j)` = log of the median of `|V_pq,c|` over the block's unflagged cells (`F` as F3);
   NaN if fewer than half are unflagged.
2. **Median polish, simultaneous updates** (order-independent): start `γ = 0`,
   `s = median_pq y`; five iterations of (i) `γ'_p = median over q of (y_pq − s − γ_q)` for every p
   from the same `γ`, (ii) `γ' ← γ' − median_k γ'_k`, (iii) `s = median_pq (y_pq − γ'_p − γ'_q)`,
   `γ ← γ'`. Medians over finite values, at least 3 (else NaN). This solves
   `log|V_pq| ≈ γ_p + γ_q + s(j)` robustly per (τ, j); on noise-dominated cross hands it factorises
   the noise amplitude, which 2d wants anyway.
3. Anomaly `𝒜_p,c(τ, j) = γ_p − fit_p,c(τ, j)`, `fit` a robust Chebyshev fit over the channel
   blocks of degree d per antenna, correlation and time block (Huber, k = 1.345 in MAD units, three
   IRLS passes). **d from {1, 2, 3} is chosen on validation before training** (Stage 2): the d with
   the largest recall of F1's antenna-local injection (seeds 41-43) and of a T6 event 0.4 nchan wide
   (seed 20265501) at `|z| > 5`, among the d whose clean (antenna, block) pairs with `|z| > 5` on
   uninjected DATA are ≤ 1 %; ties to the lower d; if none qualifies, d = 1.
4. `z_p,c = 𝒜_p,c / σ_𝒜`, `σ_𝒜` = 1.4826 MAD of `𝒜` over all antennas and channel blocks of the
   time block and correlation.
5. Dispersion `r_pq = y_pq − γ_p − γ_q − s`; `Q_p,c` = 1.4826 MAD over q of `r_pq`, divided by the
   median over antennas of `Q` (high when an antenna's baselines move in different directions: the
   signed-shift case).
6. Per family φ (par, cross): `z_p,φ` = the `z_p,c`, c ∈ φ, of larger magnitude (signed);
   `Q_p,φ = max_c∈φ Q_p,c`. Planes per baseline (p, q): `asinh max(z_p,φ, z_q,φ)`,
   `asinh min(z_p,φ, z_q,φ)`, `asinh max(Q_p,φ, Q_q,φ)`: **6 block planes**. NaN → 0 (F3's `pair`
   rule when one side is NaN).

### 2d. Noise-variance factorisation (review item 2)

Per baseline, time block of `ceil(nt / max(1, round(nt / 10)))` dumps (one block for LUNO's 10-dump scans,
three for MAIN_1's 30 and ESO137's 27-28), and channel block of 32 channels, pooled over the four
correlations:

1. `σ²_t` from time differences `V(t+1, f) − V(t, f)` and `σ²_f` from channel differences (both
   cells unflagged; real and imaginary parts; (1.4826 MAD / √2)²), at least 64 values, else NaN.
2. Median polish of `log σ²_pq ≈ τ_p + τ_q + c(j)` as in 2c (simultaneous updates), the same fit
   degree d, anomaly `𝒯_p` in MAD units as in step 4.
3. Planes: `asinh max(𝒯_p, 𝒯_q)` and `asinh min` for the time- and the channel-difference
   versions: **4 block planes**. They respond to noise-like antenna RFI, which changes the variance
   more than the median amplitude, and on targets they do not depend on the sky model.

Caveat recorded before any run: F1's and F3's coherent injections carry N(0, 0.15 rad) phase jitter
per sample, so a 10 σ injection adds about 2.1 σ to each component of a time difference: **the
variance planes will respond to the injector's jitter**, which real coherent RFI need not have. R1's
antenna-local recall is also reported with the 2d planes zeroed (an ablation, not gated).

### 2e. Network N5 and the plane budget

**Inputs, 33:** F3's 15 per-cell planes (numerics as `f3flag`, `asinh` in f32), F4's 8 spectral
planes per (baseline, channel) (numerics as `f4flag::spectra`), 2c's 6 and 2d's 4 block planes.

**Network:** stem 1×1 linear 33 → 8; then F3's stack: five 3×3 convolutions 8 → 8 with dilations 1,
2, 4, 8, 16 in (time, channel), ReLU, "same" zero padding; 1×1 head 8 → 1. Receptive field 63 × 63.
Weights: 33·8 + 8 + 5·(9·8·8 + 8) + 8 + 1 = **3,201**. Flag where logit > τ and the cell is not in
`F`, the same for all four correlations. Per-cell multiply-adds: 15·8 + 2·8 (adds) + 5·576 + 8 ≈
3,020, against F4's 3,968 and F3's 3,392. Weights are shared over baselines; nothing is indexed by
antenna.

**Plane ladder, decided by cost before training (Stage 2).** On U5 (N5 with untrained weights,
init seed 0), LUNO MAIN_1, 4 threads, heavy lock shared, 5 alternating pairs (T, U5), the estimate
`r̂` = median of the paired ratios U5 / T:

| Level | Inputs | Taken if |
| --- | --- | --- |
| L0 | 33 (all above) | `r̂ ≤ 0.42` |
| L1 | 29: L0 without 2d (and its pass) | L0 > 0.42 after one round of rule 4's optimisation |
| L2 | 21: L1 without F4's 8 spectral planes | L1 > 0.42 |
| stop | | L2 > 0.45: **Stop-C**, no training |

A level is taken only if its ZE5 check (Stage 2, section 10) still passes; otherwise the next
cheaper level is not taken either (Stop-E). The level is recorded before any shard is built. 0.42
leaves 0.08 under the 0.5 bar for the spread F4 saw within and between attempts (0.441-0.459, T
within one run ±7 %) and for a trained network's identical cost (weights do not change the work).

### 2f. Implementations and parity (frozen)

- Rust `core/src/f5flag.rs`, reusing `f3flag`'s residual pass and `f4flag`'s spectra; bindings
  `rang._core.f5flag_features` (all 33 planes materialised, for shards) and `f5flag_logits`
  (block-resolution stem, inference), `f5flag_anomaly` (per-antenna `z`, `Q`, `𝒯` for W4). NumPy
  reference `rang.f5flag.features_numpy`. Shipped behind an option that is `off` by default
  (`flag` step `f5flag`, or #38's `learned:` key if it is on main first; the move is
  bit-identical).
- PyTorch network `rang.f5net` (training-only extra `train`, no rang imports beyond NumPy): the
  F3/F4 stack (`stem=False`, F3 and F4's weight order) and N5 (`stem=True`); trainer
  `examples/f5_train.py`. The JAX code (`rang.f3net`, `examples/f3_train.py`) is frozen and not
  edited.
- Parity, the bars of F3 and F4: features Rust against NumPy on one validation scan per class,
  max |Δ| ≤ 1e-4 after `asinh`; logits Rust against PyTorch (CPU, float32) on the same features,
  p99.9 |Δ| ≤ 1e-4, max ≤ 1e-3, flag disagreement ≤ 1e-5 of eligible cells. The PyTorch port is
  checked first against the existing Rust kernels: `f3flag_logits` with U3 weights and
  `f4flag_logits` with F4's trained seed-2 weights (`a20b1abb…`), same bars.
- Cross-host (quality on nash, Linux; cost on glacier, Windows): T on nash against glacier's cached
  T flags of the validation scan, at most 1e-6 of cells differ; N5 logits Linux against Windows on
  the validation scan within the parity bars. Failure stops Stage 5 until explained.
- Weights: the trained network is exported from PyTorch to ONNX (opset 17), with a metadata header
  (stage `flag`, class, architecture `f5-n5`, input list and ladder level, τ, κ, training manifest
  sha256, teacher versions, gate scores, licence, validity envelope); the Rust kernel's flat
  weights are extracted from the ONNX initialisers into a `.npz` whose header records the ONNX
  sha256. #38's runtime may replace the hand kernel later, bit-identical or within the parity bars.

## 3. Training mix, held-out tests, fallback

**Injections.** F3's T1-T5 and F4's T6 unchanged (T6 width log-uniform 9 to min(400, 0.45 nchan),
scan-long with p = 0.75), plus **T7 noise-like antenna-local**: 1-3 events per realisation; one live
antenna; band as T6; scan-long with p = 0.5, else a run of 2 to nt dumps; every cross baseline of
the antenna gets independent complex Gaussian noise with standard deviation `√β · σ_b` per
component, β log-uniform 0.1-10. T7 strength: positive if β ≥ 0.5, ignored if 0 < β < 0.5.

**Sub-array augmentation (dl-plan section 6, item 7).** A quarter of the real training
realisations are built on a random sub-array: a uniform count of 24 to nant − 1 live antennas,
drawn uniformly (seeded), features computed on that sub-array alone. Sizes below 24 and the core-
and outer-only layouts are never drawn (they are G-sub's).

**Held-out morphologies (never in training):** F3's H1 (drifting carrier), H2 (antenna cluster),
F4's H3 (same band on two antennas), and **H4**: coherent, one antenna, band 0.1-0.4 nchan,
amplitude rising linearly from 0 at a dump in the first quarter of the scan to α at its end (or the
reverse, p = 0.5); **H4n**: the same ramp in T7's form (β from 0). F3's modulations never go below
half amplitude, so a ramp from zero is not drawn in training.

**Data** (F4's lists; all F4 held-out sets are unread).

| Class | Train | Validation | **Held-out, read once** | Reserved, unread (post hoc reruns only) |
| --- | --- | --- | --- | --- |
| Calibrators (LUNO, tiles 8-23) | MAIN_1, 2, 4, 5, 6; f2sim-1..3 | MAIN_7; f2sim-v | **MAIN_0** (3C 286), **MAIN_12**, **MAIN_14** (fetch `f4-20261111-01-fetch`, sha256 receipt); **f4sim-t** calibrator scans | MAIN_8-11, 13, 15 |
| Targets (ESO137 MAIN_0, ch 640-1151) | chunks 0, 2, 4, 6, 8, 14, 16; f2sim | chunk 10; f2sim-v | **chunks 11, 12, 13**; **f4sim-t** target scans | chunks 1, 3, 5, 7, 9, 15, 17 |

Never read: LUNO MAIN_16-19 (E2-B), ESO137 primary and target MAIN_4-6 (E2-A); exact-name
allowlists in code, as F4. Calibrator held-out sets are later scans of the training observation,
and the target sets chunks of the training track: neither is a new observation (G-obs, section 8).

**Fallback W4** (review item 3): W4 = per antenna and (time block, channel block), every cross cell
of the antenna's baselines in the block where `max(|z_p,φ|, Q_p,φ, 𝒯_p) > κ`, κ ∈ {3, 4, 5, 6, 8}.
**The method is fixed by rule on validation, before any held-out read:** τ by section 9's rule for
N5 alone; then κ is the smallest value whose N5 ∪ W4 added cells on the real validation scan's
uninjected DATA are ≤ 1.2 × T's there; the method is **N5W4** (N5 OR W4 inside W3) at that κ if one
qualifies and P still holds (T1 kinds W3's 2 + weights file + τ + κ = 5 against T's 21), else
**N5**. Both are scored; only the method enters the decision rule.

## 4. Labels (Landman's scheme, both classes)

- Positive: injected with A ≥ 3 (T7: β ≥ 0.5); simulation truth A ≥ 3.
- Ignored: flagged by T **or** A on the uninjected DATA; injected with 0 < A < 3 (T7 0 < β < 0.5);
  `F`.
- Negative: everything else.

Native RFI is learned only through injections and F-SIM; a natively flagged cell is never a
negative. The cost: unflagged cells where T and A both miss faint native RFI become negatives. R5
(recall of strong native consensus) is the gate that shows it on calibrators, R3's lower bound on
both classes.

**Label audit (frozen, before training).** Per real realisation: positives, ignored and negative
counts; T's and A's recall of the injected cells. **Stop the class if** ignored uninjected cells
exceed 40 % of eligible cells or injected positives are below 0.1 % on any realisation (F4's
bars). Expected from F4's counts: T ∪ A at most about 20 % on ESO137, so the target audit should
pass; this is the change that lets targets train at all.

Shards: 256 baselines per realisation, float16 planes (33 or the ladder's count), int8 labels; real
scans 6 realisations per training scan and 2 per validation scan; a third get F2's synthetic input
flags (as F3, F4). Seeds: realisation k of shard family f uses `base_f + k`, bases calibrator train
real 20265601, sim 20265651; validation real 20265701, sim 20265711; sub-array draws 20265801;
target train real 20265901, sim 20265951; validation real 20265961, sim 20265971. Built on nash.

## 5. Reference A

A = AOFlagger 3.5.0 with its shipped `generic-default.lua`, W3's flags as input mask, ORed with W3
(F3, F4's arm A), from the same image definition `rang-aflag-aoflagger:3.5.0`. It runs where the
evaluation runs (nash; the image is rebuilt there from the repository's definition with a receipt
of its digest); if that build fails, in glacier's WSL image, labelled. nash's native AOFlagger 3.4
is not used. CARACal's `firstpass_QUV.rfis` (AOFlagger 2.x XML; 3.x runs Lua only) is not
translated in F5; A stays a second established flagger for R4, R5 and the ignored set, never a
bar on its own.

## 6. Literature (read for the draft; no novelty claim)

| Paper | What it changes in F5 |
| --- | --- |
| Mesarcik et al. 2022, MNRAS 516, 5367 (Zenodo 10.5281/zenodo.6724065: LOFAR HBA and simulated HERA, CC BY 4.0, 21.9 GB of pickles) | not fetched: another telescope and band, Stokes-I magnitude only, conflicts with one weights file per observatory and band |
| Du Toit, Grobler & Ludick 2024, MNRAS 530, 613 | fine-tuning on a few well-labelled images unlearns AOFlagger's over-flagging; FLOPs do not predict wall time (C1 stays a wall-time measure) |
| Vafaei Sadr et al. 2020, MNRAS 499, 379 | a MeerKAT CNN of about 11-15 k weights exists; size alone is claimed for nothing |
| Kerrigan et al. 2019, MNRAS 488, 2605 | phase as a later input, not F5 (uncalibrated phase; the injector's jitter) |
| Sun et al. 2022, MNRAS 512, 2025 | nothing to reuse |

## 7. Reported arms (never gates; "not run" is an allowed entry)

- **N4**: F4's seed-2 weights (`a20b1abb…`) at τ −1.0 on F5's held-out sets: F4's result as it
  would have read, before and after F5.
- **I, image-domain check** (review item 4): per held-out set, flags from T, the method and W3, then
  identical `rang-core calibrate` (calibrators) and a GeMClean residual image (Briggs 0, no
  deconvolution); off-source RMS `R_X`, expected thermal `σ_th,X` from 2d's time-difference
  estimator; reported `R_N / R_T` with its positive control on validation first (W3 alone and an
  unflagged 10 σ copy of F1's antenna-local injection must each raise R by more than 5 %, else I is
  undecidable for that class).
- **`hci`** (pfb-imaging `1836fbcf8225624b0c4a040f470ac2b62b2b45aa`, Landman's settings of comment
  6944726203: residual `CORRECTED_DATA-MODEL_DATA`, `WEIGHT_SPECTRUM`, one integration and all
  channels per image, single precision, super-resolution 1.1, field of view 1.6°, robustness −0.5,
  padding 1.5, epsilon 1e-4, `minvar`, `flag-excess-rms` 2.5), targets only, on nash: validated on
  injected validation scans first (seeds 20265001-03; slot recall ≥ 0.9 at 10 σ_b for array-wide
  morphologies, flagged-slot rate ≤ T's), then the share of T's and N's added cells in
  `hci`-flagged slots per held-out target set. Never a training label in F5.
- **V-TV** (gain TV for validation, comment 6944726203): per held-out scan and arm, gains from
  `rang-core calibrate` at fixed settings, per-antenna `rang.core_policy.gain_tv`; Spearman between
  the TV an arm's flags remove and its added cells per antenna; median `TV_X / TV_T`.
- **R-AG** (agent review of waterfalls, comment 6944726203): protocol, prompt and sample committed
  before the first image; calibrated on injected validation scans (seeds 20265101-03) first; its
  reviewer and the flagger share the amplitude input, so agreement is not independent confirmation.
- A's wall time (single-threaded container), the 2d-ablated antenna-local recall, Q1 by morphology
  and strength decade, and E1 (expert labels) if any arrive.

## 8. Gates for a changing array (dl-plan section 6, frozen before training)

N5's inputs are per-baseline planes and symmetric functions (max, min, median) of per-antenna
quantities from order-independent computations; its weights are shared over baselines. The gates
test what that construction promises (G-perm, G-drop) and what it does not (G-sub, G-chan, G-obs).
Bounds were sized on validation with F4's network before this freeze (Measured result, "Before the
freeze"); they are scored on the held-out sets.

| Gate | Test | Bar |
| --- | --- | --- |
| **G-perm** | per held-out real set, antenna labels relabelled by a seeded permutation of the live antennas (seeds 20265201-03), the antenna table (positions) permuted alike; rows, data and row order unchanged | logits: largest absolute difference ≤ 1e-4 over eligible cells; flags differ on ≤ 1e-6 of eligible cells |
| **G-drop** | per held-out real set, all baselines of 1, 4 or 8 live antennas removed at inference (seeds 20265301-03, draw `default_rng(seed + 100 k)`); scored on the remaining baselines' eligible cells | the method's added cells change (symmetric difference against the full-array run) by ≤ 0.05, 0.20, 0.25 of its full-array added cells there, for k = 1, 4, 8, each seed (F4's network on validation: at most 0.029, 0.126, 0.173) |
| **G-sub** | per held-out real set, sub-arrays never drawn in training: **core16** (the 16 live antennas nearest the median antenna position) and **outer32** (the 32 farthest); f4sim-t (odd antennas) as a simulated layout; R1's injections drawn on the sub-array | per sub-array, pooled over sets: R1 ≥ T_sub − 0.05; R3 ≤ 1.5 and ≥ R3's lower bound; the method's R1 on the sub-array ≥ its R1 on the same sets at full array − 0.05 |
| **G-chan** | the held-out real sets averaged by 4 channels (836 kHz; data mean of four, flags OR), R1's injections drawn after averaging | R1 ≥ T − 0.05, R3 ≤ 1.5: **reported**, it sets the envelope's channel width (209 kHz only, or 209-836 kHz if it passes) |
| **G-obs** | an observation (capture block) never seen in training | **undecidable on the data on hand** (above); scored on session C's held-out blocks (29 antennas, `1678312253`; 32 outer-only, `1674958551`; `1579022459`) by a dated amendment before they are read; **required for shipping**, not for the outcome |

Only 4k channelisation (209 kHz) is on hand for both classes; G-chan is synthetic and says so.
Session C's blocks, if fetched before Stage 5, join G-sub as real sub-array sets by a dated
amendment written before they are read; if after, they are G-obs and a later G-sub amendment.

## 9. Training (frozen)

- **Host and framework.** glacier's RTX 4070 Ti, PyTorch from public PyPI in a WSL venv (the Linux
  wheel carries CUDA; the Windows PyPI wheel is CPU-only), venv `~/Build/tmp/20261119-f5-torch`,
  removed at the end. Every run is booked through `~/.gpu/gpu_run.py run --owner rang`; between
  checkpoints the trainer calls `gpu_run.py check` and on exit code 3 saves and exits (yield);
  nothing runs 06:05-06:45. Shards built on nash, copied to `D:\rang\outputs\f5-*` with a sha256
  manifest, only those a run needs, removed after.
- **Procedure** (F3 and F4's): Adam 1e-3 (β 0.9, 0.999, ε 1e-8), 30,000 steps, batch 32 windows of
  one baseline × 256 channels at a random offset, all from one shard per step; shards drawn real :
  simulation = 1 : 1; unweighted binary cross-entropy over non-ignored cells; He-normal init
  (`torch.Generator` seeded) seeds 1, 2, 3 per class; batch draws `numpy.random.default_rng(1000 +
  seed)` in F3's order. The weights file is the median seed by validation loss.
- **Resumable.** A checkpoint every 1,000 steps (an "epoch" here) and at least every 10 minutes of
  wall: weights, Adam state, step, the NumPy generator state and torch RNG states, written
  atomically with a sha256. Determinism: `torch.use_deterministic_algorithms(True)`, cuDNN
  benchmark off, `CUBLAS_WORKSPACE_CONFIG=:4096:8`. **Resume test before training** (seed 1, 3,000
  steps, calibrator shards): uninterrupted against 1,500 + 1,500 resumed; weights must be
  bit-identical; if not, the max |Δ| and the validation-loss difference are stated, and the
  difference is accepted only if it is smaller than the spread between seeds 1 and 2 at 3,000
  steps.
- **Budget:** 48 GPU hours for F5, three seeds per class included; expected about 30 min per seed
  (F4: 47 min per seed on nash's CPU, 55.9 steps/s in F4's GPU audit). One extension only on the
  owner's word.
- **Threshold τ** (validation only): grid −6, −5.5, …, +2; the τ with the largest pooled validation
  recall of positive cells such that N5's added cells on the real validation scan's uninjected DATA
  are ≤ T's there; if none, the τ with the fewest added cells (reported). Then κ (section 3).
- At most one change of hyperparameters per class, on validation, by dated amendment, before any
  held-out set is read.

## 10. Measures (frozen; per class, T the reference, "the method" as section 3)

**Stage 2 checks (validation only).**

| Check | Measure | Stop |
| --- | --- | --- |
| ZE5 | W3 OR (2c's largest `z` magnitude of the pair > 5, or F4's `e` > 5 before `asinh` if the level has it), recall of F1's antenna-local injection (seeds 41-43) on the real validation scan | **Stop-E** if < 0.5 |
| Z5 | W3 OR (F3's residual planes > 10) OR ZE5's rule, against R1 and R3 on the real validation scan (F2's injections, seeds 41-43) and S1, S2 on f2sim-v | **Stop-Z** if it meets all four: a threshold suffices; no training |

**Held-out real** (calibrators MAIN_0, 12, 14; targets ESO137 11, 12, 13).

| Gate | Measure | Bar |
| --- | --- | --- |
| R1 | F2's injection test (F1's `inject_mask`: narrowband, time-burst, antenna-local, single-baseline; seeds 19, 20, 21; 10 σ_b; eligible cells), recall pooled | ≥ T − 0.05 |
| R1m | the same per morphology | each ≥ T − 0.10 |
| R2 | H1, H2, H3, H4, H4n at 10 σ_b (H4n β = 2), seeds 31-33, recall per morphology pooled | each ≥ T − 0.05 |
| R3 | added cells on uninjected DATA, per set, ratio to T | ≤ 1.5, and ≥ 0.5 × min(T, A) / T |
| R4 | Jaccard of added cells with T, per set | ≥ J(A, T) − 0.05 (calibrators; reported for targets) |
| R5 | recall of strong native consensus (uninjected eligible cells flagged by T and A with F4's s ≥ 5), per set | ≥ 0.80 |
| G-perm, G-drop, G-sub | section 8 | section 8 |

**Held-out simulation** (f4sim-t, class scans): S1 recall of truth cells with A ≥ 10 ≥ T − 0.05;
S2 flagged fraction of eligible cells outside the truth mask dilated by one cell ≤ T + 0.01; S3
recall of drifting cells with A ≥ 10 (H1 at 10 σ_b, seeds 61-63, if fewer than 1,000) ≥ T − 0.05.

**Cost: one exclusive timing run** on glacier, native Windows, from 21:00 SAST, heavy lock held
exclusive. LUNO MAIN_1 and ESO137 chunk 0 (training scans, as F3 and F4), rows in memory to flags
in memory; the method (W3 + `f5flag_logits` + threshold + W4 if the method) against T (full
first-pass YAML). Per set and thread count (`RAYON_NUM_THREADS` 4 and 1, one process each): a 10 s
CPU sample first (other processes > 1 logical CPU: wait 15 min and retry, until 06:00); then **5
pairs** (T, method), alternating, each repeat with other processes' CPU sampled during the repeat.
A pair is clean if both repeats saw ≤ 1 other logical CPU on average.

- `C1` = median of the paired ratios method / T over the clean pairs if at least 3 are clean,
  else over all 5 (labelled provisional; a provisional C1 decides the same way).
- Reading per set and thread count: **beats** if the upper quartile of the paired ratios used is
  ≤ 0.5; **at the bar** if the median is ≤ 0.5 < the upper quartile (counted as matches); matches
  if 0.5 < median ≤ 1.1; worse above 1.1. Calibrators decide on MAIN_1, targets on chunk 0.
- C2: peak working set against T, separate processes, MAIN_1 and chunk 0, 4 threads; ≤ 0.8 beats,
  0.8-1.2 matches, > 1.2 worse. Measured outside the exclusive run (memory does not need an idle
  host).
- Interrupted runs: a pair interrupted is discarded and rerun in the same night; a night with no
  completed set moves the run to the next night. Nothing else from the run decides.

**P** as F3 and F4 (T1 kinds under half of T's 21, no retraining between sets).

## 11. Decision rule (per class, first that applies)

| Outcome | Condition | Reading |
| --- | --- | --- |
| **Stop-C** | plane ladder L2 `r̂` > 0.45 (Stage 2) | the antenna planes cannot be afforded; no training |
| **Stop-E** | ZE5 < 0.5 at the ladder's level | the planes do not see the missed class; no training |
| **Stop-Z** | Z5 meets R1, R3, S1, S2 on validation | a threshold suffices; report it; no training |
| **Stop-L** | label audit stop | no training for the class |
| **F** | any of R1, R1m, R2, R3, R4 (calibrators), R5, S1, S3, G-perm, G-drop, G-sub fails, or C1 worse at either thread count | not comparable, or not faster |
| **H** | all quality gates pass, C1 not "beats" at 4 or at 1 thread | comparable, not materially faster |
| **S** | all quality gates pass, C1 beats at 4 and at 1 thread, C2 not worse, P holds | **Landman's request met on these data** |
| **S−** | S except S2 or P | as S, with that failure stated |

**Shipping** (weights in the wheel behind the `off`-default option): outcome S or S−, and G-obs
passed on session C's held-out blocks (dated amendment before they are read). The calibrator model
ships without the target model. Targets add, whatever the outcome: "labels from injections and
simulation; not checked against expert flags" unless E1 was measured. No novelty claim follows
from beating T; a claim would need comparability to T and A at lower cost than both, and A runs
single-threaded in a container here.

## 12. Stages and stop rules

| Stage | Work | Host | Stop |
| --- | --- | --- | --- |
| 0 | this note, committed and pushed before any code | | |
| 1 | PyTorch port with parity against `f3flag`/`f4flag`; `f5flag.rs`, NumPy reference, parity; unit tests (polish recovers synthetic γ within 0.01; G-perm exact on a synthetic scan) | glacier (code), nash (build) | parity fails after one round of fixes |
| 2 | d; ZE5; Z5; plane ladder `r̂` (shared hold) | glacier for `r̂`, nash otherwise | **Stop-C**, **Stop-E**, **Stop-Z** |
| 3 | T and A on training and validation scans (F4's caches reused: `f4-20261111-06-shards-cal/calibrator/flags`, `-07-shards-target`); T on nash against them; injections, labels, audit, shards; resumable per realisation (done-marker and sha256 per shard) | nash | **Stop-L** |
| 4 | resume test; training 3 seeds per class; median seed; τ; κ and the method; ONNX export | glacier GPU (training), nash (τ, κ) | |
| 5 | W3 subset check on one held-out scan per class; held-out sets once: R1-R5, S1-S3, G-perm, G-drop, G-sub, G-chan; reported arms of section 7 that are ready; per (set, arm, seed) shards with done-markers and sha256 | nash | W3 not a subset of T |
| 6 | the exclusive timing run (C1); C2; P | glacier, from 21:00 | |
| 7 | G-obs on session C's held-out blocks (amendment); reported I, `hci`, V-TV, R-AG | nash | |

Anything changed after a held-out result is post hoc, labelled, and needs a held-out rerun on sets
not yet used for that change (the reserved lists in section 3).

## 13. Decisions taken at this freeze

The draft's ten open decisions, taken by session D under the owner's rule of 2026-11-19 ("we
decide [architecture]", dl-plan decision 8) and his v0.4.0 rules; the coordinator or owner may
reverse any by dated amendment before Stage 3.

1. *When to freeze:* now. F4 stopped at C1(U4) before any held-out read, so section 2 is rewritten
   around cost (the draft's "stopped at C1(U4)" branch).
2. *Labels:* Landman's scheme for both classes; F4's strong-consensus positives dropped; R5 kept.
3. *Reference A:* `generic-default.lua` only; no A-Lua, no A-2x.
4. *Plane budget:* all 33 at block resolution with a stem (neither draft option), cut by the
   ladder.
5. *W4:* chosen by section 3's rule on validation.
6. *Expert labels:* not requested by F5; posting is the owner's call.
7. *Mesarcik data:* not fetched.
8. *R-AG reviewer:* reported arm, model and sample fixed in its own commit before its first image.
9. *`hci` pin:* the commit above, installed from git on nash.
10. *Training host:* glacier's GPU through `gpu-run` (owner, 2026-11-19, decision 7).

## 14. Licence and not claimed

Weights ship only under section 11's shipping rule, with the SARAO acknowledgement and Ben Hugo's
permission of 2026-10-29 for LUNO-derived weights (owner, 2026-11-11, item 32); ESO137 is CC BY 4.0
(Ramatsoku et al. 2020). Not claimed: better calibration or imaging; realism of the simulated RFI;
anything for other bands, channelisations (beyond G-chan's envelope) or telescopes; anything about
new observations until G-obs.

## Amendments

**Amendment 1, 2026-11-19, after the freeze (`41b6160d`), during Stage 1 unit tests, before any
F5 feature was computed on real data, any training or any held-out read (pre-result).** Two test
bars written at the freeze cannot be met as stated; the estimators are not changed.

- *Section 2b rule 3* asked for f32 `asinh` within 2e-6 absolute of f64 over all finite f32
  inputs. Above |x| ≈ 3e27 the f32 result's half-ulp alone exceeds 2e-6. The bar becomes: 2e-6
  absolute for |x| ≤ 1e6, 1e-7 relative above (`ash32_is_within_the_bar_of_f64`). Feature parity
  (1e-4 against NumPy's f64) is unchanged.
- *Stage 1's polish test* ("recovers synthetic γ within 0.01"): simultaneous median updates reach
  a fixed point that is not the additive truth. On 12 antennas, γ_k = 0.1 sin(0.7 k), noise-free,
  the largest error is 0.0159 after 5, 20 and 100 iterations, with or without damping 0.5 (0.019
  with 0.02 noise per baseline; NumPy, glacier). The bias is per antenna and smooth in the gains,
  two orders below the log-amplitude shift of a 10 σ cross-hand event (about 2). The bar becomes
  0.02 on that case; G-perm's exactness under relabelling is unchanged and tested.

**Amendment 2, 2026-11-19, before Stage 3, any training or any held-out read (pre-result).**
R2's truth cells for H4 and H4n are the cells the labels call positive (H4 A ≥ 3, H4n β ≥ 0.5):
a ramp from zero puts cells at A < 3 that no flagger is expected to find, and section 4 ignores
them in training. H1-H3 keep F4's truth (every injected cell). No bar changes.

**Amendment 3, 2026-11-19 ~17:50 SAST, post hoc: after the calibrators' Stop-L (Stage 3), before
any calibrator training or any calibrator held-out read. Owner, 2026-11-19, verbatim (relayed by
the coordinator): "go with (b)".**

- *The frozen calibrator outcome stays Stop-L.* What follows is a labelled post hoc arm, **N5-ph**:
  it can never read S or S−, and no calibrator weights from it ship.
- *Training:* the shards already built (30 real realisations including `luno-MAIN_1-4`, 9 F-SIM
  scans; `runs/shards/calibrator/`), section 9's procedure, seeds 1, 2, 3, median seed by
  validation loss; τ and κ by section 9's and section 3's rules on validation MAIN_7 and f2sim-v.
- *Scoring, read once:* the reserved LUNO scans **MAIN_8, 9, 10, 11, 13, 15**, fetched fresh
  (receipt with sha256), with section 10's R1-R5, G-perm, G-drop, G-sub and G-chan measures, and
  f4sim-t's calibrator scans for S1-S3. **F4's unread held-out sets (MAIN_0, 12, 14) stay unread**,
  kept for a clean F6.
- *Real G-sub and G-obs, both classes:* session C's held-out blocks **1678312253** (29 antennas)
  and **1674958551** (32 outer antennas) for G-sub, and **1579022459** (58 antennas, 4,096
  channels, 8 s dumps; converted and sha256-checked on nash, unread; primary calibrator scans
  scan001, 071, 141, 189, 235, J0408-6545) for G-obs. Each block is read once, at scoring, through
  `dl2_teach.py --heldout-read`; calibrator scans go to N5-ph, target scans to the target method, in
  the same read. On these blocks the measures are section 10's R1 (F1's injections, seeds 19-21),
  R2, R3 and R5 against T on the block, with section 8's G-sub bars on the two sub-array blocks;
  G-obs passes if R1 ≥ T − 0.05 and R3 is within its bounds on 1579022459. The blocks use the full
  4,096 channels; the network is fully convolutional in channels, and a scan is cut into 2,048
  channel windows when memory needs it (whole-scan statistics per window, recorded).
- *The fix proposed for F6:* size the injected-positive bar on validation before the freeze, and
  pool it over a scan's realisations or guarantee a minimum number of strong (A ≥ 3) events per
  draw, so that one weak draw cannot stop a class.

**Amendment 4, 2026-11-20, post hoc: written after the validation dry run predicted F (R5, G-drop)
and before any held-out read. Owner, 2026-11-20, verbatim (relayed by the coordinator): "go with
your recommendation, keep the SARAO blocks".**

- F5 does **not** read session C's blocks 1678312253, 1674958551 and 1579022459. Section 8's G-sub
  is scored on the frozen simulated sub-arrays only (core16, outer32 of the held-out sets; f4sim-t's
  layout), and G-obs stays undecidable for F5, as section 8 already stated. The blocks stay unread
  for F6. Reason: R5 and G-drop already decide the outcome on validation, and these are the only
  real sub-array and unseen-observation held-out data on hand. Amendment 3's real G-sub and G-obs
  are withdrawn with it.
- N5-ph (Amendment 3) is not scored on f4sim-t's calibrator scans: f4sim-t is one of F4's held-out
  sets, which (b) keeps unread for F6, so N5-ph reports no S1-S3. The frozen targets keep
  section 10's f4sim-t target scans.
- Scoring then proceeds as frozen and read once: targets on ESO137 chunks 11, 12, 13 and f4sim-t's
  target scans; N5-ph on the reserved LUNO MAIN_8, 9, 10, 11, 13, 15.

## Measured result

Runs under `outputs/dl3-f5/` (glacier, ignored) and `~/rang-data/outputs/dl3-f5-<date>` (nash).

### Before the freeze (no held-out read; validation and training scans only)

- Cost profile: section 2a.
- **G-gate sizing** on LUNO MAIN_7 (validation) with F4's seed-2 weights at τ −1.0, W3 and T as
  frozen, 2026-11-19, glacier, shared 4 slots (`outputs/dl3-f5/size_gates.py`, `size_gates.json`,
  6.4 min; `size_perm.py`, `size_perm.json`). Full array: T adds 209,120 cells, N4 209,027.

  | Case | Antennas | N4 change / N4 full-array added | N4 added / T added on the sub-array | T changed |
  | --- | ---: | --- | --- | --- |
  | drop 1 (seeds 20265301-03) | 55 | 0.026, 0.029, 0.027 | 1.01, 1.00, 1.00 | 0 cells |
  | drop 4 | 52 | 0.126, 0.080, 0.071 | 0.95, 1.02, 1.02 | 0 |
  | drop 8 | 48 | 0.167, 0.173, 0.130 | 0.94, 1.01, 1.07 | 0 |
  | core16 | 16 | 0.73 (964 of 1,313) | **0.146** (1,209 against 8,261) | 0 |
  | outer32 | 32 | 0.21 | 1.20 | 0 |
  | random29 (seed 20265401) | 29 | 0.26 | 1.12 | 0 |

  Readings: T is per baseline (W3 and T unchanged on every sub-array), so a sub-array's T is the
  subset of the full array's. G-drop's bars are set from this table (about 1.5 × F4's worst).
  **F4's network under-flags the core baselines already at full array** (1,313 added cells against
  T's 8,261 on the 120 core16 baselines); pooled R3 hides it. Under Landman's label scheme native
  short-baseline RFI is ignored, never positive, so F5 may inherit this; G-sub's core16 R3 is where
  it would fail. Recorded before training, not acted on.
  A first G-perm probe that also shuffled the row order changed T itself (2.3-3.0 M cells):
  `flag_rows` depends on row order, so G-perm relabels antennas with rows in place (section 8). A
  second probe that relabelled without permuting the antenna positions changed W3 by 2.1 M cells
  (the static mask's uv range uses baseline lengths), so the positions are permuted with the labels.
  With both permuted (seeds 20265201-03): N4's logits, N4's flags, W3 and T **bit-identical** on all
  16,945,620 eligible cells, each seed. G-perm's bar (1e-4) leaves room for F5's reductions only.
- **PyTorch environment:** `uv` venv in WSL from public PyPI, torch 2.15.0+cu132,
  `torch.cuda.is_available()` true (log `outputs/dl3-f5/torch-venv.log`). GPU memory at 09:30: 11.2
  of 12.3 GB held by another process; F4's footprint was about 0.63 GB.

### Stage 1: code and parity (no held-out read)

- **PyTorch port against the Rust kernels** (`rang.f5net`, `stem=False`; `examples/f5_port_parity.py`;
  `outputs/dl3-f5/port-parity-MAIN_7.json`; glacier, torch 2.15.0+cpu, shared 4 slots, 49 s): F4's
  trained seed-2 weights (`a20b1abb…d90d`) on LUNO MAIN_7, 16,945,620 eligible cells: logits
  p99.9 |Δ| 9.5e-6, max 2.7e-5, flag disagreement at τ −1.0 **0**. PASS (bars 1e-4, 1e-3, 1e-5).
  On synthetic scans the port also matches `f3flag_logits` (U3-style init, non-zero biases) and
  `f4flag_logits`; its init equals `rang.f3net.init_params` bit for bit (`tests/test_f5_net.py`).
- **F5 kernel** (`core/src/f5flag.rs`, `rang.f5flag`): Rust features against the NumPy reference
  ≤ 1e-4 at levels 0, 1, 2 and degrees 1, 2, 3; split-stem Rust logits against PyTorch on the
  materialised planes within the parity bars at every level; logits and W4's anomaly
  bit-identical under antenna relabelling; on a synthetic 50 σ calibrator-like scan with a
  10 σ, 80-of-256-channel scan-long band on one antenna, W4's anomaly > 5 on ≥ 0.9 of the band's
  cells and ≤ 0.05 of the other baselines' (`tests/test_f5_flag.py`, Rust unit tests in
  `f5flag.rs`). Weights: 3,201 / 3,169 / 3,105 at levels 0 / 1 / 2.
- *Implementation detail, labelled:* N5's He-normal init is drawn with
  `numpy.random.default_rng(seed)` (`rang.f5net.init_arrays`, F3's order and scale; the stem
  with `√(1/n)`), not a `torch.Generator` as section 9 says, so the init is the same in any
  framework; the seeds are section 9's.

### Stage 2: the plane ladder (no held-out read)

- **`r̂` at L0**, 2026-11-19 10:08-10:12 SAST (corrected from the JSON's time; first written as 12:08), glacier, native Windows, heavy lock shared 4 slots /
  16 GB, `RAYON_NUM_THREADS=4`, LUNO MAIN_1 (training scan), U5 (init seed 0, τ 0, d = 2, the
  degree does not change the work), 5 alternating pairs (`examples/f5_cost.py pairs`,
  `outputs/dl3-f5/stage2-rhat-L0.json`, code `6d836527`):

  | Pair | T (s) | U5 (s) | Ratio | Clean |
  | --- | ---: | ---: | ---: | --- |
  | 0 | 35.2 | 13.5 | 0.383 | no (1.8 other CPUs) |
  | 1 | 34.1 | 13.5 | 0.395 | no (2.2) |
  | 2 | 33.3 | 13.7 | 0.412 | yes |
  | 3 | 33.2 | 13.8 | 0.415 | yes |
  | 4 | 33.1 | 13.8 | 0.418 | yes |

  **`r̂` = 0.412 ≤ 0.42: level L0 (all 33 inputs) is taken** (section 2e's rule; the median of the
  five pairs). The margin to the ladder's bar is 0.008 and to the final bar 0.088; F4's U4 read
  0.441-0.459 against the same T. U5 flags 0.997 of cells (untrained, τ 0); thresholding costs
  the same at any τ.
- *Implementation, labelled (section 2b rule 4, after `r̂`):* the method N5W4 needs W4's anomaly
  as well as the logits; `f5flag_logits_anomaly` computes both from one preparation pass
  (bit-identical to the two separate calls, tested), so W4 adds only the per-cell lookup. The
  `r̂` above is for N5 alone; Stage 6 times the method chosen at Stage 4. The per-cell anomaly
  lookup now takes a per-(block, antenna) maximum computed once (exactly equal; tested). N5W4 at
  κ 5 (U5, d 2), same set-up, 3 pairs, 11:30-11:33 SAST: T 35.9 / 33.9 / 33.5 s, N5W4 15.3 /
  14.8 / 14.3 s, ratio median 0.427 (one pair clean; `outputs/dl3-f5/stage2-w4-L0.json`).
- *Readings fixed before Stage 3 (labelled; the note left them open):* the fit degree d is chosen
  per class, on that class's validation scan, since each class has its own weights file. R2's
  truth cells for the ramps are the label positives (H4: A ≥ 3; H4n: β ≥ 0.5), not every
  injected cell (Amendment 2 below).

### Stage 2: fit degree (calibrators), nash, 2026-11-19

`examples/f5_eval.py degree`, LUNO MAIN_7, level 0, 8 slots, 72 s
(`runs/degree-calibrator.json`): recall at |z| > 5 of F1's antenna-local injection (seeds 41-43)
and a 10 σ T6 band 0.4 nchan wide (seed 20265501); clean (antenna, block) pairs over 5:

| d | Recall | Clean pairs over 5 |
| --- | ---: | ---: |
| 1 | **0.997** | 0.84 % |
| 2 | 0.978 | 0.90 % |
| 3 | 0.980 | 0.90 % |

All three under the 1 % bar; **d = 1** by the rule. *Targets* (ESO137 chunk 10, 1,064 s
including lock wait, `runs/degree-target.json`): d 1 / 2 / 3 recall 0.997 / 0.978 / 0.972, clean
pairs over 5 0.54 % / 1.73 % / 0.44 %: **d = 1**. The 2c planes alone see F1's antenna-local
event at 0.997, against F3's 0.024 and F4's ZE 1.000.

### Stage 2: ZE5 and Z5 (calibrators), nash, 2026-11-19

`examples/f5_eval.py stage2`, LUNO MAIN_7 and f2sim-v calibrator scans, L0, d = 1, 8 slots,
1,532 s (`runs/stage2-calibrator.json`):

- **ZE5** recall of F1's antenna-local injection (seeds 41-43): **1.000**. No Stop-E.
- **Z5** against T: R1 0.631 against 0.920 (fails R1 by far); R3 ratio 1.08 (lower bound 0.50);
  f2sim-v S1 0.909 against 0.797, S2 0.263 against 0.316. **No Stop-Z**: training goes ahead.
- *Targets* (ESO137 chunk 10 and f2sim-v target scans, 3,508 s including lock wait,
  `runs/stage2-target.json`): ZE5 **1.000** (T finds 0.60 of the same antenna-local cells, e.g.
  53,895 of 89,152 on seed 43); Z5 R1 0.785 against T 0.850, R3 1.25 (lower bound 0.05), f2sim-v
  S1 0.965 against 0.985, S2 0.015 against 0.111. No Stop-E, **no Stop-Z** (R1 fails by 0.065).

### Cross-host check (section 2f), 2026-11-19, LUNO MAIN_7 (validation)

nash (`~/Worktrees/rang/dl3-f5` at `0d7837ed`, Linux build, 8 slots, 132 s) against glacier
(Windows build, same commit's kernel for these paths; `examples/f5_crosshost.py`,
`~/rang-data/outputs/dl3-f5-20261119/runs/crosshost-MAIN_7.json`): W3 identical; **T identical**
(0 of 31.5 M cells differ, and 0 against glacier's cached `luno-MAIN_7-T.npy`); U5 logits p99.9
|Δ| 1.8e-7, max 5.4e-7, 0 flag disagreements; **A** through apptainer
(`rang-aflag-aoflagger_3.5.0.sif`, built on nash from glacier's `rang-aflag-aoflagger:3.5.0` image
by `docker save`, receipt `outputs/dl3-f5/xfer/ao_image.*`) **identical** to the cached
`luno-MAIN_7-A.npy`. PASS. Inputs on nash are byte copies of `D:\rang` with per-item sha256
manifests checked on nash (`outputs/dl3-f5/xfer/*.sha256`, `copy.log`).

### Stage 3: label audit (calibrators), nash, 2026-11-19 — **Stop-L as frozen**

`examples/f5_shards.py`, L0, d = 1 (`runs/shards/calibrator/`; validation 646 s, train 2,007 s,
8 slots, peak 17.9 GB). Validation (MAIN_7, 2 realisations): ignored uninjected 16.9 % and 16.5 %
of eligible cells (bar 40 %), injected positives 0.40 % and 2.5 % (bar 0.1 %); T and A find 0.949
and 0.940 of realisation 0's injected positives. Training (30 real realisations, 9 F-SIM scans):
ignored uninjected 11.8-27.3 %; injected positives 0.25-13.5 % on 29 realisations and **0.098 %**
on `luno-MAIN_1-4` (seed 20265615, a 37-antenna sub-array; its events are mostly below A = 3,
which the labels ignore). **Section 4's frozen stop fires: "injected positives below 0.1 % on any
realisation".** By section 11 the calibrator outcome is **Stop-L**: no training for the class.

Recorded, not acted on: the bar was F4's target bar, applied to both classes at this freeze; F4's
calibrator audit had none. The miss is 2 % below the bar on one realisation of thirty. Changing
the bar or the realisation after seeing this is post hoc; as with F4's C1(U4) (0.458 against 0.45)
the frozen reading stands. Whether a labelled post hoc calibrator arm is trained and scored (it
could not become S or S−, and it would spend F4's unread held-out sets) is the coordinator's or
owner's decision. Nothing has been trained; no held-out set has been read.

### Copy to nash capped, 2026-11-19 15:50 SAST

The owner (relayed by a network-check session): the copy filled the house's ~50 Mbit/s upload.
Found: an orphaned copier from before the crash still ran beside the per-file one (up to seven
streams). Both stopped by PID; the rest (F2/F4 simulated scans, glacier-only) goes as one stream
capped at 2.5 MB/s (`outputs/dl3-f5/xfer/copy4.sh`, `throttle.py`). ESO137 MAIN_0 and both SARAO
fetches were already on nash and verified, so no public data is still being sent.

### Stage 6 plan, fixed 2026-11-19 15:10 SAST, before the run (labelled)

The exclusive run starts at 21:00 SAST (`examples/f5_timing.sh`), whether or not a class has
trained weights by then: section 10's cost does not depend on the weights (F4 recorded the same;
the work is the same at any weights and τ), so U5 stands for the trained network. Both candidate
methods are timed (N5, and N5W4 at κ 5) at 4 and 1 threads on LUNO MAIN_1 (calibrators) and ESO137
chunk 0 (targets), 5 pairs each, with section 10's gate, pair and reading rules; d = 1 (the fit
degree barely changes the work; the targets' d, if different, is noted beside the reading). The
method fixed at Stage 4 picks its row; the other rows are reported. A dry run of one pair on ESO137
chunk 0 (shared hold, copies running, N5W4): ratio 0.40. No copy, WSL or GPU job of F5 runs during
the hold.

### Stage 3: label audit (targets, real training scans), nash, 2026-11-19 — passes

`f5_shards.py --only-real`, ESO137 chunks 0, 2, 4, 6, 8, 14, 16, 6 realisations each, L0, d = 1,
1,801 s (`runs/shards/target/train/`): injected positives 0.52-11.2 % of eligible cells (bar
≥ 0.1 %), ignored uninjected 10.5-23.2 % (bar ≤ 40 %; F4's L-INJ gave 47.0-64.0 % on the same
chunks). T and A find 0.75-0.94 and 0.79-0.99 of realisation 0's injected positives. **No stop
on the real target scans**: Landman's scheme is what lets the target class train. The F-SIM part
and the validation chunk follow when their simulations are on nash.

### Stage 4: resume test (section 9), glacier GPU, 2026-11-20 — passes

Post hoc calibrator arm's shards (L0, d = 1), torch 2.15.0+cu132, deterministic settings, booked
through `gpu_run.py run --owner rang`: seed 1 for 3,000 steps uninterrupted against 1,500 steps,
a checkpoint and 1,500 resumed: **weights bit-identical** (max |Δ| 0.0), validation loss 0.07949
both; seed 2 at 3,000 steps for the spread (max |Δ| of weights 1.23, validation loss 0.07806).
3,000 steps take 44 s after a 29 s shard load; peak VRAM per single-seed process 313 MB allocated,
524 MB reserved (`~/Build/tmp/20261119-f5-train/calibrator/resume-test.json`, `resume-a/train.json`).

*Implementation, labelled:* seeds 1-3 train in one process (`examples/f5_gpu_seeds.sh`): the
shards, about 25 GB in memory, are loaded once, and three processes would exceed WSL's 44 GB. Each
seed keeps its own model, optimiser, batch generator and checkpoint; a test shows seeds trained
together equal each seed alone, bit for bit. Seed 1 resumed from the checkpoint the stopped
sequential chain had written.

### Stage 4: post hoc calibrator arm N5-ph, three seeds (Amendment 3), glacier GPU, 2026-11-20

`examples/f5_gpu_seeds.sh`, one process, 30,000 steps per seed, 1,589 s wall (shard load
included), 26.2 GB host memory, 1.24 GB VRAM for the three:

| Seed | Validation loss | weights sha256 |
| --- | ---: | --- |
| 1 | 0.0474 | `fbea6b11…` |
| 2 | 0.0348 | `8d9f3b5b…` |
| **3** | **0.0443** | `c659d08b…` |

Median seed by validation loss: **seed 3**. The spread (0.035-0.047) is narrower than F4's
(0.033-0.210).

τ and κ (`examples/f5_tau.py`, nash, 8 slots, 355 s; `runs/tau-calibrator/`): **τ = −3.0**,
pooled validation recall **0.963** of 3.01 M positive cells (MAIN_7 two realisations, f2sim-v
three scans) with N5 adding 180,448 cells on MAIN_7's uninjected DATA against T's 209,120 (F4's
N4: 0.954 at 209,027). κ: N5 OR W4 adds 2.73 M / 1.58 M / 1.04 M / 0.76 M / 0.49 M cells at
κ 3 / 4 / 5 / 6 / 8, all above 1.2 × T (250,944), so **the method is N5** (no W4), by section
3's rule.

*Targets:* the full training audit (42 real realisations and 6 F-SIM scans; 890 s on nash at 16
slots) passes, `stop: null`; F-SIM positives 0.23-2.36 M cells per scan.

### Stage 4: targets, three seeds (frozen protocol), glacier GPU, 2026-11-20

`examples/f5_gpu_seeds.sh`, one process, 30,000 steps per seed, 1,899 s, 20.8 GB host memory:
validation losses seed 1 **0.0070**, seed 2 **0.0087**, seed 3 **0.0082** (weights sha256
`d25f8cb1…`, `dd81f073…`, `61e4ea81…`); median seed **3**.

τ and κ (`examples/f5_tau.py` on **glacier**, 12 threads, 37 min including lock wait, nash locked;
`D:\rang\outputs\dl3-f5-20261120-target\tau\`): **τ = −6.0**, the bottom of the grid, pooled
validation recall **0.988** of 3.39 M positive cells (chunk 10's two realisations, two f2sim-v
target scans), with N5 adding 124,140 cells on chunk 10's uninjected DATA against T's 2,414,858
(N5 alone adds 5 % of T's cells at every τ of the grid; recall 0.988-0.975 from −6.0 to −3.5).
κ: N5 OR W4 adds 3.85 M / **1.45 M** / 0.32 M / 0.18 M / 0.13 M cells at κ 3 / 4 / 5 / 6 / 8; the
smallest κ within 1.2 × T is **4**, and P holds, so **the target method is N5W4 at κ 4**. nash's
τ/κ run was cancelled before it started (the glacier result is the one used).

### nash locked, 2026-11-20 ~10:00 SAST: targets' τ/κ and held-out read moved to glacier (labelled)

nash's account was locked (login shell set to nologin) while F5's jobs ran there. Coordinator,
2026-11-20, before either result was seen: the targets' τ/κ (validation) and then their held-out
read (ESO137 11-13, f4sim-t's target scans) run on glacier's CPU (inputs already there; 12 of 16
threads; shards with done-markers; clear of glacier by 20:50 for the timing run); **the glacier
result is the one used**; if nash's τ/κ run also finished, both are reported. N5-ph's six held-out
reads were launched on nash at about 08:15 and are not re-run: if nash does not come back, N5-ph is
recorded as "read, results lost". Weights: target seed 3, sha256 `61e4ea81…` (copied from WSL to
`outputs/dl3-f5/target-seed3-weights.npz`, checked).

### Stage 6: the exclusive timing run, glacier, 2026-11-20 11:02-12:39 SAST

Run early on the owner's word, 2026-11-20 (relayed): "i'm not doing much at the computer at the
moment so feel free to run it as soon as you want" (`F5_TIMING_ANYTIME=1`; gate, pairs and
exclusive hold as section 10). One interruption: another session's full check held glacier's
shared slots 11:19-11:39; the next cell (MAIN_1, 1 thread, N5) was refused at its gate (1.31 other
CPUs), nothing was timed, and it reran at once on an idle host. U5 stands for the trained networks
(the cost does not depend on the weights). `outputs/dl3-f5/c1-20261120/`.

| Set, threads | N5: C1 (q25-q75) | N5W4 (κ 5): C1 (q25-q75) | clean pairs N5 / N5W4 |
| --- | --- | --- | --- |
| LUNO MAIN_1, 4 | **0.409** (0.405-0.413) | 0.417 (0.416-0.420), provisional | 5 / 0 |
| LUNO MAIN_1, 1 | **0.365** (0.361-0.368) | 0.369 (0.363-0.371) | 5 / 5 |
| ESO137 chunk 0, 4 | 0.392 (0.391-0.400) | **0.397** (0.391-0.402) | 5 / 5 |
| ESO137 chunk 0, 1 | 0.369 (0.368-0.369) | **0.371** (0.371-0.372) | 5 / 5 |

Bold: the rows each class's method picks (calibrators N5-ph: N5; targets: N5W4). **C1 beats at 4
and at 1 thread in both classes** (upper quartile ≤ 0.5), from clean pairs; F4's U4 read
0.441-0.459 against the same T. **C2** (peak working set, separate processes, 4 threads, after the
hold; `outputs/dl3-f5/c2-20261120/`): LUNO MAIN_1 N5 5.518 GB against T 5.518 GB, ESO137 chunk 0
N5W4 1.626 GB against 1.626 GB: **1.00**, matches (the decode sets the peak in every arm).

### Validation dry run of the held-out scorer (N5-ph, LUNO MAIN_7), nash, 2026-11-20 — no held-out read

`examples/f5_heldout.py real --validation` with N5-ph's `method.json` (seed 3, τ −3.0, N5), every
case of section 10 on the validation scan (2,063 s, 8 slots; `runs/dryrun/`). A test of the code
path; these are validation numbers and decide nothing:

| Measure | N5-ph | N4 (F4) | T | Bar |
| --- | ---: | ---: | ---: | --- |
| R1 pooled / antenna-local | 1.000 / 1.000 | | 0.900 / 0.731 | ≥ T − 0.05 / − 0.10 |
| R2 H1 / H2 / H3 / H4 / H4n | 1.00 / 0.998 / 1.00 / 0.992 / 0.946 | | 1.00 / 1.00 / 0.432 / 0.695 / 0.057 | ≥ T − 0.05 |
| R3 added / T | 0.863 | 1.000 | | 0.5-1.5 |
| R5 strong native consensus | **0.338** | 0.872 | 1.000 | ≥ 0.80 |
| G-perm | exact | | | 1e-4 |
| G-drop k = 1 / 4 / 8 | **0.14 / 0.30-0.42 / 0.49-0.59** | (F4, 11-19: 0.03 / 0.13 / 0.17) | | 0.05 / 0.20 / 0.25 |
| G-sub core16 added (T) | 820 (8,261) | 1,209 | | R3 ≥ 0.5 × min(T, A)/T |
| G-chan R1 / R3 | 1.000 / 0.80 | | 0.861 | reported |

Readings, written before any held-out read: R5 and G-drop would fail as frozen. R5 is the cost
section 4 predicted for Landman's scheme: strong native consensus is ignored, never positive, so
the network learns native RFI only through injections; F4's labels, which kept it positive, give
0.872. G-drop is F5's own: the block planes are normalised over the antennas present, and
simultaneous median polish has a rank-dependent bias (Amendment 1), so dropping one antenna moves
the planes of every baseline in the block; τ −3.0 puts many cells near the threshold. Neither is
changed here: the frozen targets and the post hoc arm are scored as they stand, unless the
coordinator or owner decides otherwise.

### glacier crash, 2026-11-19 12:52 SAST (a test of the resume rule)

glacier rebooted unannounced. Nothing of F5 ran on its GPU then. Lost: the three copy streams in
flight to nash (each item restarts from its start; items are whole F-SIM scans of 1.6-3.2 GB at
about 2 MB/s, so up to about 25 minutes of transfer per stream, over the 15-minute rule; the next
copy splits scans by file). Kept: the 16 finished items (done-markers, sha256 verified on nash).
nash was unaffected; Stage 2 there had already stopped on a missing `scipy` in F5's venv (needed by
the F-SIM path), installed and rerun detached from glacier (`setsid`) at 13:08.

## F6 proposal (2026-11-20, from F5's validation dry run; proposed, not frozen)

Written after F5's validation dry run and before any F5 held-out read. Each fix is first
measured on validation only (MAIN_7, f2sim-v and F4's validation and training scans); F6 then
freezes with whichever survive, on held-out sets F5 has not read.

1. **Labels: hybrid positives.** Landman's scheme stays for injected and simulated cells, and
   for native cells T or A flag alone (ignored). Native cells flagged by both T and A with strength
   s ≥ 3 on the uninjected DATA become positive again (F4's L-A1s rule), so the network learns
   native RFI that two established flaggers agree on. Target: R5 ≥ 0.80 on MAIN_7 (N5-ph 0.338,
   F4's N4 0.872) without losing R1 or R3. Cost: new shards and three seeds, about 1 h of nash and
   30 min of GPU per class. On targets the same rule needs F4's audit check that strong consensus
   stays under 10 % of eligible cells.
2. **Block planes robust to the antenna set.** G-drop changes 0.14 of N5-ph's flags for one
   dropped antenna (bar 0.05). Candidates, measured with `examples/f5_f6_probe.py` (which plane
   group drives the change) before any retraining: (a) normalise z and Q by a fixed robust scale
   per block (the median over antennas of the per-antenna MAD over channel blocks) instead of the
   MAD over all antennas and blocks; (b) replace simultaneous median polish by an M-estimator
   (Huber) solved to convergence, which has no rank-dependent fixed-point bias (Amendment 1);
   (c) train with antenna dropout on every realisation (section 3 used sub-arrays on a quarter).
   *Measured, 2026-11-20, validation MAIN_7, one antenna dropped (seed 20265301), 128 baselines,
   N5-ph seed 3 at τ −3.0 (`examples/f5_f6_probe.py`, `outputs/dl3-f5/f6-probe-k1.json`, glacier,
   4 slots):* N5's flags change on 0.152 of its 14,275 flagged cells. Share of eligible cells whose
   plane moves by more than 0.1 (asinh units): F3 residuals 0, F3 antenna and array medians 0.005,
   F4 spectral 0.004, **2c amplitude blocks 0.836, 2d variance blocks 0.780**. With 2c held at its
   full-array values the change is 0.103, with 2d held 0.110. So the block planes move almost
   everywhere when one antenna goes: their scale (one MAD over all antennas and blocks) and the
   polish's fixed point both depend on the set, consistent with (a) and (b). The residual 0.10
   with either group held points also at cells near τ (item 3).
3. **Threshold margin.** τ −3.0 leaves many cells near the threshold; G-drop counts flips.
   Proposed: G-drop scores flags with a ±0.5 logit dead band reported beside the frozen count, and
   τ's rule prefers the larger τ among those within 0.005 of the best recall.
4. **Label-audit bar sized before the freeze** (Amendment 3): injected-positive share pooled over a
   scan's realisations, or a minimum number of strong (A ≥ 3) events per draw.
5. **Unread sets for F6:** LUNO MAIN_0, 12, 14 and ESO137 11-13 (F4's), session C's blocks
   1678312253, 1674958551 and 1579022459, unless F5 spends them (coordinator's question to the
   owner, 2026-11-20).

## For the coordinator

- Frozen in its own commit before any F5 code. Held-out sets: F4's, all still unread.
- Decisions taken at the freeze: section 13 (reversible before Stage 3).
- Text for Landman: none needed before results; the 2026-11-19 comment covers the freeze.
