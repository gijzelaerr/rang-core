# F5: a fast supervised RFI flagger for MeerKAT L-band, fourth protocol (draft)

Task F5, branch `f5-draft` from origin/main `976b0eb`. **Status: proposed, not frozen; nothing
implemented, fetched, run or trained.** It is frozen only after F4's calibrator outcome is in (F4 is
frozen and running on branch `fp-f4-flagger`, head `475ad60` when this was written; its note
`research/f4-flagger.md` is on that branch only). Everything below may change before the freeze; after
it, the rules of F3 and F4 apply (dated, labelled amendments; held-out sets read once).

The source is Landman Bester's reply of 2026-11-17 on issue #1 (comment 6943748188). It has two parts:

- **Landman's own points.** Expertly flagged MeerKAT L-band data are hard to find, and even an
  expert's flags leave residual RFI, which is why he first proposed the unsupervised route (gain TV as
  the loss). He points to the expertly labelled, non-MeerKAT set released with Mesarcik et al. 2022, to
  four further papers, and to high time cadence imaging (pfb-imaging's `hci`) as a way to find RFI-hit
  time slots and so make labels.
- **A review of F3 that Landman forwarded**, written by an agent he asked to read
  [f3-flagger.md](f3-flagger.md). It answers F3's two questions (no public expert-flagged MeerKAT
  L-band set with calibrator and target scans is known; one more round with a narrow scope is worth
  it), diagnoses F3's miss and lists five items for "F4". It was written against F3 and without sight
  of the frozen F4 protocol, so its "F4" is what this note calls F5 where F4 does not already do it.
- **Landman's answers to three follow-up questions** (comment 6944726203, 2026-11-17): the `pfb hci`
  settings he uses; gain TV for validation rather than as an objective; and that he will not hand-check
  waterfalls, suggesting an agent review correlated with gain TV instead (section 6).

The goal is unchanged from F2-F4 (Landman, 2026-11-06): one weights file per observatory and band
(MeerKAT L-band), separate calibrator and target models, faster than the Rust Tricolour port (T) with
fewer tunable parameters, comparable flag quality. **No novelty claim**; better calibration or imaging
is not a goal. The image-domain gate below judges flag quality only.

## 0. The review's items against F4

| Review item | In F4 already (branch `fp-f4-flagger`) | New in F5 |
| --- | --- | --- |
| Diagnosis: r^t, r^f and the antenna medians cannot see a wide-band, scan-long, one-antenna event | yes, the same diagnosis (F4 section 1, from F3's post hoc reading) | the reading of the code in section 1 |
| 1. Antenna planes from a robust factorisation of raw amplitudes, wide smoother | partly: eight scan-scale spectral planes per baseline against the array spectrum (no factorisation, no smoother, scan-long only) | per time block, log amplitude, solved γ_p, low-order fit (section 2a) |
| 2. Noise-variance factorisation, σ from time differences too | no (σ is one scalar per baseline and correlation, from channel differences) | section 2b |
| 3. Antenna-local training events up to about 400 channels, coherent and noise-like, scan-long and partial | coherent only: T6, 9 to min(400, 0.45 nchan) channels, scan-long with p = 0.75 | noise-like events, T7 (section 3) |
| 3. New held-out morphology, e.g. RFI on two unrelated antennas or a slow ramp | H3 antenna pair (same band on two antennas) | H4, a slow onset ramp (section 3) |
| 3. Classical OR fallback (𝒜_p threshold) in a W4 wrapper, if P holds | no | arm W4 (section 3) |
| 4. Label scheme: positive injected A ≥ 3; ignored T or A flags, 0 < A < 3, F | targets L-INJ is close but also ignores cells with s ≥ 3; calibrators L-A1s keep strong consensus as positive | his scheme for both classes (section 4) |
| 4. Image-domain gate, N ≤ 1.05 × T achieved RMS | no (R5 and the R3 lower bound are F4's answers to the missing under-flagging test) | section 4 |
| 5. Reference A from a CARACal MeerKAT AOFlagger strategy | no (`generic-default.lua`) | section 5 |
| Lower priority: autoencoder novelty branch, tabascal injections | no | not in F5 either |
| Landman, second reply (comment 6944726203): `pfb hci` settings | no | label generator settings, pinned and validated on injections first (section 6) |
| Landman, second reply: gain TV for validation, not as an objective | F1 used it as the objective (NO-GO) | V-TV, a reported validation measure (section 6) |
| Landman, second reply: an agent, not he, reviews waterfalls, correlated with gain TV | no | R-AG, a weak-label arm, never training labels (section 6) |

## 1. What F3 and F4 miss, and why (a reading of the code, not a run)

Code read: `core/src/f3flag.rs` on main `976b0eb`; `core/src/f4flag.rs` and `python/rang/f4flag.py` on
`fp-f4-flagger` `475ad60` (f4flag.rs last changed in `ea5fa52`, Amendment 2); the injector
`python/rang/core_injection_model.py::make_injection` on main.

**F3's fifteen planes (`f3flag::residuals`, `aggregates`).** Per baseline and correlation:
`σ_bc` is one number per scan, the MAD of adjacent-channel differences over all unflagged cells;
`a = |V| / σ_bc`; `P(f)` is the median of `a` over time; `r^t = a − P(f)`; `S(f)` is the running
median of `P` over 33 channels (`RUNMED_HALF = 16`); `g(t)` the median over channels of `a / S`;
`r^f = a − g(t) S(f)`. The antenna planes `M^x_k` are medians over k's baselines of
`u^x = max_c r^x_c`. A band on for every dump enters `P` in full, so `r^t` is zero there; a band wider
than about 16 channels enters `S` in full, so `r^f` is zero there except within about 16 channels of
its edges; `M^x` are medians of those, so they inherit both blind spots. F1's antenna-local injection is
one coherent phasor (phase constant per event plus N(0, 0.15 rad) jitter per sample, conjugated on the
other side of the baseline) on every dump of all 52-55 baselines of one antenna, 178-322 channels wide
on LUNO and 60-92 on ESO137. **The review's diagnosis holds as a reading of the code:** that event is
invisible in all fifteen planes except near its band edges, which matches the measured 0.024 recall.

**F4's network planes (N4, `f4flag::spectra`)**, cross-correlations: `w_b,c(f) = P_b,c(f) − B_c(f)`,
`B` the median over baselines of `P`; one offset per baseline and correlation, the median of `w` over
all channels (Amendment 2; was the 25th percentile); `e_b = max_c∈φ |w − o|` per family (parallel XX,
YY; cross XY, YX); `E_k` the median of `e` over k's baselines; array excess `X = B − q25_f(B)`. Read
against the review:

- **Smoothing scale: none narrower than the band.** The only spectral baseline removed is one constant
  per baseline and correlation, a zeroth-order fit over the whole band. That is the review's extreme
  ("a low-order fit across the band"), so a 300-channel event cannot be absorbed by the smoother. The
  opposite risk is open: a per-antenna bandpass difference that the array median `B` does not remove
  stays in `e` and `E_k` as structure across the band. On calibrators the parallel hands carry the
  source at about 50-70 σ per visibility, so a few per cent of bandpass mismatch is a few σ in `e`.
  F4's ZE check (validation only) found F1's antenna-local injection at recall 1.000 (calibrators) and
  0.993 (targets) at threshold 5, so this did not stop the feature there; its false flags on native data
  are F4's R3/R4 to measure.
- **Scan-long only.** `P` is the time median, so an antenna event on fewer than half the dumps does not
  move `e`; F4 leaves that to `r^t`, which sees a wide partial-scan band as a time-local excess, and to
  `M^t`.
- **Linear SNR units, not a factorisation.** `E_k` is a median of per-baseline deviations, not a solved
  antenna term; it attributes robustly (antenna k's baselines are all high, any other antenna has one
  high baseline of about 55), but it does not separate a per-antenna gain from a per-baseline effect.
- **Valid for bands on fewer than half the channels** (Amendment 2's median offset; T6's cap
  0.45 nchan).

**F4's antenna-domain arm NA (Amendment 1, `f4flag.na_statistics`)**, autocorrelations: `M_kc(f)` the
time median of Re V_kk; `ρ = M / median_k M`, divided by its median over channels; `D_k(f) = max_c (ρ −
q25_f ρ)`; time-local `T_k = (A / M − 1)` in MAD units over time. **NA does not cover the missed event
and cannot:** F1's injection touches cross-correlations only, so the autos never see it (F4 says so).
Its smoothing scale is again a constant per antenna (one channel median and one 25th-percentile
offset), with no per-antenna bandpass model, so antenna bandpass mismatch alone exceeds the smaller δ:
F4 recorded D's p90 of 0.038-0.071 on validation, its δ rule picked 0.1 (the top of the grid) on both
classes, and F4 expects G2 to fail (NA-broken) before any NA result. Its time-local part divides by the
time median, so it has the same scan-long blind spot as `r^t`. NA would see a noise-like emitter at one
antenna (power in the auto), which is where it is complementary to section 2b.

**So:** for the coherent, scan-long, wide case the reply asks about, F4's cross-correlation spectral
planes are the counterpart of 𝒜_p, not NA. F5 adds what F4 lacks: time blocks (partial-scan events in
the antenna terms), a solved γ_p in log amplitude, an explicit low-order per-antenna fit for bandpass
mismatch, and a noise-variance term for noise-like antenna RFI.

Three properties of the data constrain the design:

- **Signed shifts on calibrator parallel hands** (F4 Amendment 2): an additive phasor of 10 σ on a
  50-70 σ source shifts |V| by ±10 σ cos(φ_pq − θ), and the source phase φ_pq differs by baseline
  (uncalibrated antenna phases), so the median over k's baselines of the log-amplitude shift can be
  close to zero while its scatter is large. A signed 𝒜_p alone can miss it; section 2a adds a
  dispersion plane (this note's addition, not in the reply).
- **ESO137 has 512 channels** (640-1151), so a ≥ 800-channel smoother is impossible there; only the
  low-order fit works for targets. LUNO has 2,048 (tiles 8-23).
- **LUNO calibrator scans have 10 dumps** (ESO137 chunks 27-28), so σ from time differences per
  (baseline, channel) has 9 pairs per scan; it has to be pooled over a channel block (section 2b).

## 2. Features

All new planes are computed in float64 and stored float32, 0 on `F` (F3's mask), constant within a
(time block, channel) cell, and fed as `asinh` of the quantity, F3's `pair` rule for max/min.

### 2a. Robust amplitude factorisation (the review's item 1)

Per scan, time block τ (default: the whole scan split into blocks of `n_τ` dumps, `n_τ` = 2 on LUNO
and 3 on ESO137, proposed) and channel block of 8 channels (anomalies narrower than 9 channels are F3's
planes' job; T3 covers 1-8, T6 9-400), per correlation c:

1. `y_pq,c(τ, f) = log` of the median of `|V_pq,c|` over the block's unflagged cells (NaN if fewer
   than half are unflagged).
2. Median polish over antennas: `s_c(f) = median_pq y`, `γ = 0`; five iterations of
   `γ_p ← median_q (y_pq − s − γ_q)`, `s ← median_pq (y_pq − γ_p − γ_q)`. That solves
   `log|V_pq| ≈ γ_p + γ_q + s(f)` robustly; for noise-dominated cross hands it factorises the noise
   amplitude instead, which is what section 2b wants anyway.
3. Anomaly `𝒜_p,c(τ, f) = γ_p − median_k γ_k − fit_p,c(τ, f)`, where `fit` is a robust (Huber,
   3 IRLS passes) Chebyshev fit over the band of degree `d` per antenna, correlation and block; `d ≤ 3`
   proposed. F1's widest bands are 320 of 2,048 channels (LUNO) and 92 of 512 (ESO137), about 1/6 of
   the band, which degree 3 follows poorly; T6 and T7 train up to 0.45 of the band, where a degree-3 fit
   starts to absorb the event, so the freeze picks `d` on validation from {1, 2, 3} by ZE-style recall
   of F1's antenna-local injection and of a 0.4-nchan T6 event at fixed false flags. On LUNO only, a running median of 801 channels is
   the alternative arm `fit = runmed`, reported.
4. Scale: `z_p = 𝒜_p / σ_𝒜`, `σ_𝒜` = 1.4826 MAD of `𝒜` over all antennas and channels of the block
   (robust to one antenna's band).
5. Dispersion (added here): `r_pq = y_pq − γ_p − γ_q − s`; `Q_p` = 1.4826 MAD over q of `r_pq`,
   divided by the array median of `Q`; this is high when k's baselines move in different directions
   (the signed-shift case).
6. Planes per family φ ∈ {par, cross}: `asinh max(z_p, z_q)`, `asinh min(z_p, z_q)` (signed, as the
   reply asks), `asinh max(Q_p, Q_q)`: **6 planes**.

Cost: step 1 is one pass over the cells (85.6 M on LUNO MAIN_1, 4 correlations); steps 2-5 run on the
block grid, `n_τ × 8` = 16-24 times fewer cells than the data, at O(N_bl) per grid cell per iteration.
For MAIN_1 that is about 4 × 5 × 2 × 85.6 M / 16 ≈ 2 × 10^8 median-selection operations, of order 1 s
on one thread (an estimate from F3's measured feature times: 1.2 s for 18.0 M cells, which include two
antenna medians per cell; not measured).

### 2b. Noise-variance factorisation (the review's item 2)

Per baseline, correlation family, time block of the whole scan (LUNO) or 9 dumps (ESO137), and
channel block of 32 channels:

1. `σ²_t` from time differences `V(t+1, f) − V(t, f)` (both cells unflagged; real and imaginary
   parts; 1.4826 MAD / √2, squared) and `σ²_f` from channel differences (F3's estimator, but per block
   instead of one per scan). At least 64 pairs, else NaN; a LUNO block has 9 × 32 × 2 = 576 values.
2. Median polish of `log σ²_pq ≈ τ_p + τ_q + c(f)` as in 2a, the same low-order fit, anomaly `𝒯_p`
   in MAD units.
3. Planes: `asinh max(𝒯_p, 𝒯_q)` and `asinh min` for the time- and channel-difference versions:
   **4 planes**. Amplitude planes are for coherent RFI, variance planes for noise-like RFI (receiver
   self-interference, a misbehaving chain), as the reply argues; on targets the variance planes do not
   depend on the sky model, which breaks 2a's amplitude factorisation.

Caveat recorded before any run: F1's and F3's coherent injections carry N(0, 0.15 rad) phase jitter per
sample, so a 10 σ injection adds about 10 × 0.15 × √2 ≈ 2.1 σ to each component of a time or channel
difference against the noise's √2 σ. **The variance planes will respond to the injector's jitter**,
which real coherent RFI need not have. R1's antenna-local recall is therefore also reported with the
variance planes zeroed (an ablation, not gated), and with a jitter-free copy of F1's injection
(reported).

Cost: one pass over the data (like F3's σ pass), then the polish on a grid 32 × (block length) times
smaller: well under 1 s on MAIN_1 (estimate).

### Where it sits in Rust, and the plane budget

A new `core/src/f5flag.rs` beside `f3flag.rs` and `f4flag.rs`, reusing F3's residual pass and
convolution and F4's `quantile`: `block_log_amp`, `median_polish(y, ant1, ant2, nant, iters)`,
`robust_cheb_fit`, `variance_blocks`, `planes`; rayon over (time block, channel block) for the polish
and over antennas for the fits. Bindings `rang._core.f5flag_features`, `f5flag_logits` and
`f5flag_anomaly` (the per-antenna `z`, `Q`, `𝒯` for W4). NumPy reference `rang.f5flag.features_numpy`;
parity bars as F3 and F4. F5's code depends on `f4flag.rs`, which is not on main: it is written after
F4 is merged, or on F4's head after its outcome.

**C1 headroom is thin.** At 4 threads on MAIN_1, T took 48.1 s (F3); C1's bar 0.5 is 24 s; F3's N3
took 16.5 s; F4's untrained U4 19.4-19.8 s per repeat (C1(U4) 0.441, provisional; F4's own stop is
0.45). The network's first layer is 9 × n_in × 8 multiply-adds per cell against 2,304 for the other four
layers, so each extra plane costs about 2-3 % of the network. Two options, an owner decision (section
8):

| Option | Inputs | Weights (9·n·8 + 8 + 4·584 + 9) | Expected C1 at 4 threads |
| --- | ---: | ---: | --- |
| A: F4's 23 + 10 new | 33 | 4,729 | about 0.48-0.52 (estimate: U4 plus 10 planes plus about 1-2 s of features): at the bar |
| B: F3's 15 + 10 new, replacing F4's eight spectral planes | 25 | 4,153 | about 0.40-0.44 (estimate) |

B is proposed: 2a's `z` and `Q` cover the scan-long case that F4's `e`, `E` cover, and also the
partial-scan case. If F4's calibrators pass R1m on the antenna-local case, B keeps the capability only
if a Stage 1 ZE-style check of the new planes alone matches F4's (recall of F1's antenna-local
injection ≥ 0.99 on validation); otherwise A.

## 3. Training mix, held-out tests, fallback

**Injections.** F3's T1-T5 and F4's T6 (coherent wide antenna-local, 9 to min(400, 0.45 nchan)
channels, scan-long with p = 0.75, else a run) unchanged, plus:

- **T7 noise-like antenna-local:** 1-3 events per realisation; one live antenna k; band as T6's;
  scan-long with p = 0.5, else a run of 2 to nt dumps; every cross baseline of k gets independent
  complex Gaussian noise with standard deviation `√β · σ_b` per component, β log-uniform 0.1-10 (excess
  noise variance 10 %-1000 %). Label strength for T7: positive if β ≥ 0.5, ignored if 0 < β < 0.5
  (proposed; a per-cell noise excess cannot be thresholded like A).
- Antenna-local events of every width from 1 to 400 channels are then in training, coherent (T3, T6) and
  noise-like (T7), scan-long and partial, as the review asks.

**Held-out morphologies (never in training).** F3's H1 (drifting carrier), H2 (antenna cluster), F4's
H3 (same band on two antennas), and new:

- **H4 slow onset ramp:** coherent, one antenna, band 0.1-0.4 nchan, amplitude rising linearly from 0 at
  a random dump in the first quarter of the scan to the event's α at the end (or the reverse, p = 0.5).
  Checked against the trained modulation: F3's events are constant or × (0.75 + 0.25 sin), which never
  goes below half amplitude and is periodic; a ramp from zero is not drawn.
- **H4n:** the same ramp in T7's noise-like form (β ramping from 0).

The reply's other example, wide-band RFI on two unrelated antennas, is F4's H3 when the band is shared
and is trained (T6, T7 draw 1-3 independent events) when it is not, so it is not new.

**Held-out data.** New sets only, from F4's reserved, unread lists: LUNO MAIN_8, MAIN_10, MAIN_13
(fetch, about 4.5 GB, receipt with sha256; MAIN_9, 11, 15 stay reserved) and ESO137 MAIN_0 chunks 3, 7,
15 (chunks 1, 5, 9 stay reserved). F4's held-out sets (LUNO MAIN_0, 12, 14; ESO137 11-13) become
training after F4 has read them; F3's and F4's results on them are before/after reports.

**Fallback W4** (the review's item 3): W4 = W3 OR, per antenna and (time block, channel block), every
cross cell of the antenna's baselines where `max(|z_p|, Q_p, 𝒯_p) > κ` (section 2's quantities).
κ from {3, 4, 5, 6, 8} on the real validation scan: the smallest κ whose added cells on uninjected
DATA are ≤ T's. Arms: N5 (network in W3), **N5+W4** (N5 OR W4's antenna term), W4 alone. N5+W4 counts as
the method only if P still holds (T1 kinds: W3's 2, weights file, τ, κ = 5 against T's 21: under half).
Whether N5 or N5+W4 is the method is fixed at the freeze, not after the held-out read.

## 4. Targets, labels and the image-domain gate

**Labels (the reply's scheme, both classes).**

- Positive: injected with A ≥ 3 (T7: β ≥ 0.5); simulation truth A ≥ 3.
- Ignored: flagged by T **or** A on the uninjected DATA; injected with 0 < A < 3; `F`.
- Negative: everything else.

Native RFI is learned through injections and F-SIM only, and the network is never taught that a
natively flagged cell is clean. Against F4: L-INJ (targets) ignores also every unflagged cell with
`s ≥ 3`, and that clause fired F4's target audit (ignored uninjected cells 0.470-0.640 of eligible cells,
bar 0.40). Under the reply's scheme the ignored share is bounded by T ∪ A: T adds 12-17 % on ESO137 and
A 1.3-2.5 %, so at most about 20 % (estimate from F4's audit counts; not measured as a union). The cost:
the 30-40 % of eligible target cells with `s ≥ 3` that T and A leave unflagged become negatives, so the
network is taught that whatever raises `s` there (mostly sky structure in a bright field, but also any
faint native RFI both flaggers miss) is clean. That is what the image gate has to catch. For
calibrators the scheme drops F4's strong-consensus positives (L-A1s); F4's R5 (recall of strong native
consensus) is kept as a gate so that the loss shows. Whether to adopt the scheme for targets, and also
for calibrators, is decision 2 in section 8.

**Image-domain gate I (new; the reply's item 4).** It judges flag quality, not imaging; it is not a
claim about better images.

- Per held-out set and class, flags from T, from the method (N5 or N5+W4) and from W3 alone (control),
  then identical processing: calibrators `rang-core calibrate` with fixed settings on the arm's flags,
  then the residual (CORRECTED − MODEL, the calibrator models `rang-core calibrate` uses) imaged by
  GeMClean with fixed settings (cell, size, Briggs 0, no deconvolution); targets: the ESO137 chunk
  calibrated with fixed settings (which gains and which field model apply to `ms1_target` is checked
  before the freeze), the model subtracted, imaged the same way.
- Measures: achieved off-source RMS `R_X` (inner two thirds of the image, outside a mask of sources
  above 5 σ in T's image, the same mask for all arms) and expected thermal noise
  `σ_th,X = √(Σ w_i² σ_i²) / Σ w_i` over the arm's unflagged visibilities, `w_i` the imaging weights,
  `σ_i` from section 2b's time-difference estimator per baseline and block (ESO137 carries unit weights,
  so the weights cannot give σ). `R_X` penalises over-flagging (higher `σ_th`) and leaked RFI (excess
  over `σ_th`) in one number; `R_X / σ_th,X` is reported.
- **Bar: `R_N ≤ 1.05 × R_T`** per set, and no artefact: no off-mask pixel above 6 × `R_T` in N's image
  that is not also in T's, plus a written look at the images (PNGs archived).
- **Positive control, before the freeze, on validation only.** The gate can fail only if it can see
  leaked RFI: `R_W3 > 1.05 × R_T` on the validation scan of each class, and an unflagged 10 σ copy of
  F1's antenna-local injection must raise R by more than 5 %. If either control fails for a class, gate
  I is undecidable there and reported only. This matters most for targets: floor-3 left the ESO137
  pilot's residual at 379 µJy, 8.6 × thermal; a 210 s chunk has a higher thermal noise, but if the
  floor still dominates a 5 % bar has no power, and the control says so before anything is read.
- The same gate on the calibrator fields tests F3's simulated false-flag advantage (Q2 0.0016 against T's
  0.325) on real data: fewer false flags lower `σ_th` and so `R`.

## 5. Reference A

**CARACal ships MeerKAT AOFlagger strategies.** At the commit T pins, `8f7bb363876f5f0daecbf2167c36bb597c7e5160`
(2026-09-14), `caracal/data/meerkat_files/` holds 23 `.rfis` files (two of them GMRT's,
`GMRT_GSB_First_Pass.rfis`, `GMRT_GSB_Second_Pass.rfis`) and no `.lua`; master `ee243f9` (2026-11-17)
has the same 23 names. CARACal's `meerkat-defaults.yml` and `meerkat-continuum-defaults.yml` at that
commit set `flag_rfi: flagger: aoflagger, strategy: firstpass_QUV.rfis` for both the calibrator and the
target flag workers (sha256 `edcb4131cae82b80e495ba719a2d0da19627586b2592f5ced400b1e9e90c69c8`, last
changed in `59ad90de`, 2020-04-09; written by AOFlagger 2.9.0; Stokes Q, U, V; two SumThreshold actions,
base sensitivity 1.5, thresholds 1.7, 2.1, 4). The worker runs it through Stimela's `cab/autoflagger`
(image `stimela/aoflagger:1.2.0`, `docker-apt-install aoflagger` on `stimela/base:1.2.0`; the AOFlagger
version inside is not checked here).

**But the files are AOFlagger 2.x XML, and rang's oracle is AOFlagger 3.5.0, which runs Lua only.**
AOFlagger's own guide ("Upgrading .rfis files") says a `.rfis` has to be rewritten by hand in Lua,
starting from the default strategy and a diff of the XML. AOFlagger 3.5's shipped strategies are
generic and per telescope; F3 recorded that none is MeerKAT's. So "use one" has two routes:

| Route | Work | Risk |
| --- | --- | --- |
| A-Lua: translate `firstpass_QUV.rfis` to Lua on 3.5.0 (as A-FLAG translated Tricolour's strategy) | a day; a fidelity check needs a 2.x run of the XML on one validation scan | a translation is not the shipped strategy; differences need the A-FLAG treatment |
| A-2x: run the XML in a pinned AOFlagger 2.x image (Stimela's, or a KERN build) | image, pin, receipt; Docker in WSL as now | old binary; its bugs; reproducibility of the image |

Either way A stays out of the labels except through the "ignored" set (section 4), and A is reported
for context if neither route passes a check on validation (agreement with the 2.x XML run of at least
0.95 of flagged cells for A-Lua). Decision 3 in section 8. `generic-default.lua` stays as A0, reported,
for continuity with F3 and F4.

## 6. Labels from data

**High time cadence imaging (pfb-imaging).** Read: `src/pfb_imaging/core/hci.py`,
`utils/hci_actors.py`, `utils/stokes2im.py` at `ratt-ru/pfb-imaging` main `1836fbcf8225624b0c4a040f470ac2b62b2b45aa`
(hci.py last changed `4d12c6f6`, 2026-11-14; MIT licence). `pfb hci` makes one residual image (DATA
minus an optional model, optional gains) per `integrations_per_image` (default 1 dump) and
`channels_per_image` (default the whole band) from MSv4 data (xarray-ms), Ray actors and ducc0's
w-gridder. Each image's rms is the standard deviation of the residual image; at the end an image is
flagged when its rms exceeds `flag_excess_rms` (default 1.5) times the median rms over time in its
(Stokes, band), and flagged images are removed from the mean cube.

As a label generator for RFI-hit time slots:

- **Granularity:** one label per (time image, band), for all baselines at once. It cannot say which
  baseline or antenna, so it gives cell labels only through a further rule (for example: every cell of a
  flagged slot not already flagged is ignored, never positive).
- **Blind spot:** the bar is relative to the band's median over time, so scan-long RFI raises the
  median and is not flagged: the same blind spot as `r^t`. Using `σ_th` from the weights (section 4)
  instead of the median would remove it; that is a change to `hci`, not its shipped behaviour.
- **Sensitivity:** array-wide bursts and satellites are its natural targets; one antenna's band
  reaches 55 of about 1,540 baselines, so it shows only when strong.
- **What it is good for here:** an independent, flagger-free audit of time slots on targets, where T and
  A disagree by an order of magnitude; and a per-dump version of gate I.
- **Settings (Landman, issue #1 comment 6944726203, 2026-11-17).** Asked how to run it, Landman gave
  a command; F5 adopts it as the label generator's frozen settings, paraphrased: residual
  `CORRECTED_DATA-MODEL_DATA`, weights `WEIGHT_SPECTRUM`, one integration per image, all channels in
  one image, single precision, super-resolution factor 1.1, field of view 1.6°, robustness −0.5,
  minimum padding 1.5, epsilon 1e-4, weighting mode `minvar` (the minimum over correlations, WSClean's
  Stokes I style), `flag-excess-rms` 2.5 (not the default 1.5). His `--nworkers 32 --nthreads 2` are
  host settings (nash); his `--temp-dir` is not an option of `pfb hci` at the pinned commit (checked in
  `src/pfb_imaging/cli/hci.py`), so it is dropped. `minvar` and every other option above exist there.
- **Pin.** pfb-imaging main `1836fbcf8225624b0c4a040f470ac2b62b2b45aa` (the code read above). The
  latest tag, v0.0.11 (`ee5b50b`, 2026-07-28), is older than the current `hci` (hci.py last changed
  2026-11-14), so the pin is the commit, installed from a git URL into a uv venv on nash; its
  dependencies come from public PyPI, and the source install of pfb-imaging itself is recorded.
- **Validation before any use (frozen at the F5 freeze; validation sets only).** Inject F1's
  time-burst, F3's T2 intermittent narrowband, T5 broadband bursts and F4's T6 wide antenna-local
  events at 3, 10 and 30 σ_b into the validation scans' DATA (seeds 20265001-03), form CORRECTED and
  MODEL as gate I does, run `pfb hci` with the settings above, and score per time image against the
  injected truth (a slot is truth-positive if it holds an injected cell with A ≥ 3). It becomes a label
  source only if slot recall is ≥ 0.9 at 10 σ_b for each array-wide morphology and its flagged-slot
  rate on uninjected data is ≤ T's. Antenna-local events are expected to fail (one antenna is 55 of
  about 1,540 baselines) and are reported, not gated. If it fails, it stays a reported measure.
- **Use, if validated:** a weak, slot-level label: every cell of an `hci`-flagged slot is **ignored**
  in the target training labels (never positive), and the share of T's and N's added cells in
  `hci`-flagged slots is a reported measure per target set.
- **Route:** the LUNO and ESO137 inputs here are zarr groups, not MSv4, so `hci` needs an MS export
  with CORRECTED_DATA, MODEL_DATA and WEIGHT_SPECTRUM written by rang (`rang-core apply` and the model
  stage); Ray on Windows is untested, so it runs on nash.

**Gain TV as a validation measure V-TV (Landman, comment 6944726203).** Landman suggests using the gain
TV for validation rather than as an objective term; F1 used it as the objective and was NO-GO. Frozen
definition (proposed): per held-out scan and arm X ∈ {T, A, N5, N5+W4, W3}, solve gains with
`rang-core calibrate` at fixed settings on X's flags; per antenna k, `TV_k,X` = `rang.core_policy.gain_tv`
(anisotropic Frobenius TV over time and frequency, all four Jones entries, polar gauge on the reference
antenna, the fixed scale of the W3 solve, edges valid in every arm's solve). Measures: (i) Spearman
correlation over antennas between `TV_k,W3 − TV_k,X` (the TV the arm's flags remove) and the arm's added
cells on k's baselines; (ii) the arm's median over antennas of `TV_k,X / TV_k,T`. Reported for every arm,
not a gate, because F1 measured that gain TV marks injected RFI weakly at array scale (patch AUC 0.54-0.64
on four of five morphologies at 10 σ, [f1-tv-flagger.md](f1-tv-flagger.md)): a low correlation is
expected even for a good flagger, and a high one is evidence only together with gate I.

**Agent review of waterfalls, arm R-AG (a weak-label arm; Landman's suggestion).** Landman will not
hand-check waterfalls; he suggests that a sub-agent review them and that its verdict be correlated with
gain TV. F5 designs that as a separate arm, **explicitly weaker than expert labels**:

- *Protocol written first.* The reviewer's prompt, model and version, the rendering (per baseline,
  amplitude in σ units, `asinh` scale, fixed colour map and size, the arm's flags as an overlay on a
  second panel), the question (per waterfall: "unflagged RFI present: yes / no / unsure", and for yes,
  the time-channel box) and the sample (a seeded draw of baselines per held-out set, stratified by
  antenna) are committed before any review is run. No prompt change after the first reviewed image.
- *Measured against truth first.* On validation scans with injections (F1's four morphologies, H1-H4,
  3-30 σ_b, seeds 20265101-03), the reviewer sees waterfalls whose truth is known; its recall and false
  "yes" rate per morphology and strength are the arm's calibration. If its recall at 10 σ_b is below
  T's on that morphology, its verdicts on that morphology are not used.
- *Then on held-out data:* per arm, the share of reviewed waterfalls marked "unflagged RFI present",
  and its Spearman correlation with V-TV's per-antenna terms. Reported, never a gate, never a training
  label, never fed back into τ, κ or any setting.
- *Risk stated with every R-AG result:* the reviewer looks at the same amplitude waterfalls the flagger
  sees, so they can share blind spots (scan-long wide bands look like bandpass structure; noise-like RFI
  looks like noise; an `asinh` stretch hides what it compresses). Agreement between R-AG, V-TV and N is
  therefore not independent confirmation; the injections and gate I are the checks that do not share
  the input.

**Mesarcik et al. 2022, Zenodo 10.5281/zenodo.6724065** (metadata only; nothing downloaded).
Licence CC BY 4.0. Creators Mesarcik, Boonstra, van Nieuwpoort, Ranguelova; published 2022-06-24.
Twelve Python pickle files, 21,937,525,397 bytes in all: `LOFAR_Full_RFI_dataset.pkl` 9.97 GB,
`L629174_RFI_dataset.pkl` and `L631961_RFI_dataset.pkl` 3.78 GB each, and ten HERA files of 440 MB each
(one per RFI-type combination). Telescopes: **LOFAR HBA** (five calibrator observations of 3C 295 and
3C 380, 2017-2018, 599 s, 243 subbands × 16 channels, 120-190 MHz) and **simulated HERA** (`hera_sim`).
The paper: LOFAR labels are AOFlagger's archive flags (weak labels) for about 7,500 training
spectrograms, plus 109 hand-labelled test baselines (strong labels); Stokes I magnitude only. The
RFI-NLN loader (`utils/data/lofar.py`) unpickles arrays of spectrograms and masks; whether baseline or
antenna identity survives in them is not known without opening a file.

- **Pretraining:** not for F5. Another telescope and band, one Stokes-I magnitude per baseline (no four
  correlations, no noise scale `σ_bc`), very likely no antenna index: it cannot fill N's antenna or array
  planes, and it conflicts with Landman's one-weights-file-per-observatory-and-band rule.
- **Validation:** usable only as an out-of-domain, reported test of a per-baseline arm (F2-style planes)
  against the 109 expert baselines, and as a measure of how much AOFlagger labels over-flag against an
  expert (Du Toit et al.'s point). Not a gate.
- **Handling:** pickles run code when loaded; if ever fetched, unpickle once in a container with no
  network and convert to `.npz`. Fetch the smallest useful file (a 3.78 GB LOFAR one) with a note first.

**Expert MeerKAT labels.** The review proposes building a small set (about 50-100 waterfalls) for
validation and fine-tuning only. F4 already holds the text of a request to Landman for expertly flagged
target data (not posted). F5 adds: if such a set exists by the freeze, it is a reported measure E1 and a
fine-tuning arm (Du Toit et al.), never a gate on its own.

## 7. Literature (read for this note; no novelty claim)

| Paper | Read | Summary | What it changes in F5 |
| --- | --- | --- | --- |
| Mesarcik et al. 2022, MNRAS 516, 5367, arXiv:2207.00351 | abstract; arXiv HTML (dataset sections) | Novelty detection (Nearest-Latent-Neighbours on generative autoencoders) trained on uncontaminated data only, picked with weak archive flags; HERA (simulated) and LOFAR (real) sets; a small expert-labelled LOFAR test set; better AUROC/AUPRC than supervised baselines, lower F1 on LOFAR | nothing in the method (the review defers a novelty branch); its set is assessed in section 6 |
| Du Toit, Grobler & Ludick 2024, MNRAS 530, 613, doi:10.1093/mnras/stae892 | MNRAS full-text page, first part only; no arXiv preprint found | A comparison framework for fully convolutional RFI detectors (U-Net, AC-Unet, RFI-Net, R-Net, two new) on Mesarcik's LOFAR and simulated HERA data, 19.9 k-809 k parameters; Dice loss gave the best F1; fine-tuning on 14 well-labelled images after pretraining on AOFlagger flags unlearns AOFlagger's over-flagging; FLOPs do not predict inference time | supports a small expert set as a fine-tuning arm (section 6); keeps wall time, not FLOPs, as the cost (C1 already); Dice loss not adopted (F5 changes features and labels, not the loss) |
| Vafaei Sadr et al. 2020, MNRAS 499, 379, arXiv:2005.08992 | abstract; arXiv HTML | R-Net (ResNet, about 11-15 k weights) beats MeerKAT's SDP online flagger (AOFlagger-based, two parameters tuned) on simulated MeerKAT L-band data (Montblanc RIME, satellites and towns as RFI, 4,096 channels); transfer learning to human-flagged KAT-7 data (12 h, 42 baselines) lifts AUC from 0.67 to 0.91; uncalibrated phase adds almost nothing | the amplitude-only inputs stand; simulation pretraining plus a little real expert data is the route the review suggests; labels at nσ match the A ≥ 3 rule; a MeerKAT network of this size exists, so F5 claims nothing for size alone |
| Kerrigan et al. 2019, MNRAS 488, 2605, arXiv:1902.08244 | abstract only | A deep fully convolutional network on simulated HERA visibilities with mock RFI, using amplitude and phase jointly; phase adds adjacent time-frequency context; recall 0.81, precision 0.58 on HERA-67 | a phase or fringe-rate plane is a candidate for a later protocol, not F5 (uncalibrated phase per Vafaei Sadr; the injector's own phase jitter, section 2b) |
| Sun et al. 2022, MNRAS 512, 2025, arXiv:2203.00298 | abstract only | A CNN trained on SKA1-LOW simulations with overlaid RFI, AUC 0.93, applied to real LOFAR and MeerKAT data with results comparable to AOFlagger | nothing beyond a further MeerKAT application; no labels or weights to reuse are named in the abstract |

## 8. Decisions for the owner and coordinator, and cost

**Decisions.**

1. **When to freeze, and what F5 is for**, after F4's calibrator outcome:
   - F4 calibrators **S or S−**: F5 is targets first (the label scheme and gate I are the new parts);
     calibrators get gate I as a reported check of F4's weights.
   - F4 calibrators **F on R1m antenna-local**: F5 as written, both classes.
   - F4 calibrators **F elsewhere** (R2, R3, R5, S1, S3) or **stopped at C1(U4)**: rewrite section 2
     around that failure before freezing.
2. **Labels:** the reply's scheme for targets (proposed); also for calibrators, dropping F4's
   strong-consensus positives (proposed yes, with R5 kept as a gate).
3. **Reference A:** A-Lua or A-2x (section 5), or A reported for context only.
4. **Plane budget:** option B (replace F4's spectral planes, 25 inputs) or A (add, 33 inputs).
5. **W4:** whether the method is N5 or N5+W4, fixed at the freeze.
6. **Expert labels:** whether to post F4's request (with the review's 50-100 waterfall suggestion) to
   issue #1. This task posts nothing.
7. **Mesarcik data:** not fetched for F5 (proposed); a 3.78 GB LOFAR file later only for an
   out-of-domain report.
8. **R-AG's reviewer:** which model reviews the waterfalls, and how many per set (proposed: 200 per
   validation scan for the calibration step, 100 per held-out set per arm).
9. **`hci` pin:** a git commit install of pfb-imaging on nash (proposed) or wait for a tagged release
   containing the current `hci`.
10. **Training host:** glacier's GPU (Ollama holds about 10 GB of 12 GB) or nash's CPU, as F4's 11-17
   deviation; nash CPU training wall is unmeasured until F4's run reports it.

**Cost estimate** (host time; estimates from F3's and F4's measured rows in
[tool-timings.md](tool-timings.md) and F4's branch; nothing here is measured).

| Step | Host | Estimate |
| --- | --- | --- |
| Fetch LUNO MAIN_8, 10, 13 (about 4.5 GB) | glacier, network | 30-55 min (F3 52 min for 4.56 GB, F4 28 min for 4.54 GB) |
| Rust features, NumPy reference, tests, parity | glacier, shared 4 slots | 1-2 h of runs (F4 parity 11-153 min, mostly lock wait) |
| f5sim-t; Stage 1 (ZE-style checks, image-gate positive control) | glacier, shared | 1-3 h (F4 stage1 46 + 26 min; f4sim-t 12 min) plus the control's images |
| Shards and label audit, two classes | glacier, shared | 2-2.5 h (F4 119 min incl. lock wait) |
| Training, 3 seeds × 2 classes | glacier GPU or nash CPU | GPU about 3 h (F4's estimate, 25-30 min per seed); nash CPU unknown |
| τ, κ | glacier | 1-1.5 h (F3 20 + 41 min) |
| Held-out quality, 6 sets, about 8 arms incl. A | glacier | 4-6 h (F3 78 min for 2 sets × 7 arms, A in Docker dominates) |
| Gate I: calibrate and image 6 held-out + 2 validation sets × 3 arms | nash (GeMClean; nice 19, ionice) | 3-5 h shared (about 24 runs; LUNO scans are small, ESO137 chunks a few min each) |
| `hci` set-up, injection validation (2 validation scans × 4 morphologies × 3 strengths), then held-out targets | nash, shared | 3-6 h incl. MS export and Ray set-up |
| V-TV: one fixed `rang-core calibrate` per held-out set and arm (about 30 solves) | glacier or nash, shared | 2-4 h |
| R-AG: render waterfalls, review (about 400 validation + 3,000 held-out images) | any host; reviewer cost outside the host | under 1 h of host time for rendering |
| Cost C1/C2 | glacier, exclusive | about 1 h in one hold |
| A-2x image or A-Lua translation check | glacier WSL | 2-4 h |

In all, about 17-29 h of shared glacier time plus 1 h exclusive, 8-15 h shared on nash, and 3 h of GPU
if the GPU is free. Disk: F4's shards take 31 GB; F5's at 25-33 planes about 35-45 GB on `D:\rang`.

## For the coordinator

- Branch `f5-draft` from origin/main `976b0eb`; one commit with this note, its README index line, a
  STATE log paragraph ("proposed") and a tool-timings row. Not merged; no code.
- Sources pinned: CARACal `8f7bb363` (and master `ee243f9`), pfb-imaging `1836fbc`, Zenodo record
  6724065 (metadata API), F4 `fp-f4-flagger` `475ad60`, issue #1 comments 6943748188 and 6944726203 (read only).
- Nothing was posted, commented or reacted to on GitHub.
- Proposed message for Landman: none yet; after the freeze, the coordinator may put sections 0, 1 and 8
  to him.
