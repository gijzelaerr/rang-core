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

## For the coordinator

- Frozen in its own commit before any F5 code. Held-out sets: F4's, all still unread.
- Decisions taken at the freeze: section 13 (reversible before Stage 3).
- Text for Landman: none needed before results; the 2026-11-19 comment covers the freeze.
