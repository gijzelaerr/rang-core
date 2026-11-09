# E1: the whole chain on A1's simulated truth

Task E1 of [finish-plan.md](finish-plan.md), on branch `fp-e1-chain` from main
`0d6230d`, 2026-11-09. Native Windows (`.venv` with uv, Python 3.14); WSL only
for the Tricolour 0.2.1 oracle.

**Status: implemented and measured; no gate of A0's E1 table is met as
frozen.** The protocol (sections 1 to 6) was committed (`2c506eb`) before the
first scored run and is unchanged; results are in sections 7 to 9. Of the
failures (section 8):
- **shared with CASA, shown:** the five antennas lost to K's refant rule and the m034 delay;
- **known limit:** self-calibration (C5's model absorption);
- **rang only, cause not established:** K misses CASA's K at p95 (0.07 ns against 0.03) on m32 and never converges;
- **cause not established:** the rest, two of them noise-free (the cross-hand phase, the target composite's ramp).

No bug was located with truth, so nothing was fixed and E1 did not rerun. No
novelty claim and no timing claim.

## 1. What was read before this protocol

- [a0-acceptance.md](a0-acceptance.md): rules 5 and 6 (gauge, scorer), class T
  (6.2), the E1 table (6.3), the failure rule (6.5: an E1 failure is a bug,
  fixed and rerun; E1 is not held out).
- [a1-simtruth.md](a1-simtruth.md): the truth, its gauge (2.5), 7.5 "For E1"
  (models, refant m000, rang's parallactic frame, no input flags, the
  `above_5sigma` definition).
- [c2e-calibrate.md](c2e-calibrate.md) (the A step flags 63 % of A1 small's
  calibrator cells; decision 3 asks E1 to report it),
  [c6w-polwire.md](c6w-polwire.md) (strategy 1 in the command; the target
  polarisation estimator), [e0-refant-extend.md](e0-refant-extend.md)
  (`refant: auto` picks m022, m023, m024 on A1 full), [c5-selfcal.md](c5-selfcal.md)
  (the loop's truth gate T2 fails through model absorption; C5b after G4),
  [c2c-bandpass.md](c2c-bandpass.md) 8.1 (G's `linear` interpolation alone
  breaks 1e-5 on calibrator fields), [c6-polterms.md](c6-polterms.md) 7
  (KCROSS takes up the linear part of Xf), [w3-chunking.md](w3-chunking.md),
  [w6-imaging-inputs.md](w6-imaging-inputs.md), [g2-memory.md](g2-memory.md)
  (GeMClean holds about 90 bytes per visibility cell at 256 channels).
- CARACal's first-pass calibrator strategy
  (`caracal-strategy-inputs-8f7bb363/mk_rfi_flagging_calibrator_fields_firstpass.yaml`).

## 2. Data

| Set | What | Role |
| --- | --- | --- |
| **m32** (scored) | A1's `full` design (64 antennas, 256 channels, all 23 scans) keeping each scan's first 32 integrations: `examples/a1_simtruth.py generate full OUT --max-per-scan 32 --name a1-full-m32`. 558 integrations, 1,124,928 rows, 7 target scans × 32 = 224 target integrations | every gate |
| small twin | `fp-a1-20261106-simtruth/small/a1-small-twin.ms` as stored (16 antennas, 64 channels, all 104 integrations, noise- and RFI-free) | the noise-free tier of class T (4.1) |
| small | `fp-a1-20261106-simtruth/small/a1-small.ms` | dry run only: the chain must execute. Nothing on it is compared with truth |

Every run works on a copy under `D:\rang\outputs\e1-20261109-NN`; A1's files
are read only.

**Why m32, not the whole full MS (decided before any run).** The full MS's
target holds 2,016 × 1,200 × 256 = 619 M cells. G2 measured GeMClean's peak at
18.2 GB for 203 M cells at 256 channels (about 90 bytes per cell), so the full
target would need about 55 GB on a 30 GB host shared with task G4. m32 holds
115.6 M target cells (about 11 GB by the same rate). It keeps:
- A0's A1 requirements: 64 antennas, 856–1712 MHz, 256 channels, full
  polarisation, every Jones term;
- every scan's start time, so the polarised calibrator's four scans (all 30
  integrations kept) span the same 115° of parallactic angle;
- every gain-calibrator scan whole (15 integrations), so the gain-calibrator
  scans' mean times, and with them the truth's linear G on the target, are
  those of the full truth;
- the truth itself: `a1_simtruth.py` computes the Jones terms, RFI and noise
  (keyed by integration index) on the full schedule and writes the kept rows,
  so m32's rows are the full MS's rows and `full/truth.npz` is its truth. This
  is checked, not assumed (5.1).

The flux calibrator keeps 32 of 45 integrations per scan and each target scan
32 of 150 (four 8-integration blocks of the self-calibration term S).

## 3. The chain

### 3.1 Configuration

[results/e1-chain-scripts/e1_config.yaml](results/e1-chain-scripts/e1_config.yaml),
one `rang-core run config.yaml ms` with `run.stages: [flag, calibrate, apply,
selfcal]` (the selfcal stage ends with the final image):

- **flag:** the Tricolour port with CARACal's first-pass calibrator strategy on
  every field (as E2-A's configuration flags its calibrator and target with
  it), Tricolour's static masks, `write: replace` (the input FLAG is all
  false).
- **calibrate:** CARACal's full-Stokes chain as E2-B:
  - model `setjy` Stevens-Reynolds 2016 on J1939-6342; `uvrange '>150'`;
  - primary K (`inf`), G (`ap`, `inf`), B (`inf`, `combine scan`,
    `fillgaps 70`, as C6w);
  - secondary on SIM-GCAL: Gsec (`ap`, `inf`, K B), the A step `Asec`, F
    (`inf`, K B, `smodel [1,0,0,0]`, then `fluxscale`);
  - polcal strategy 1: model `nrao` 3C286 (CARACal's `nrao_xcal.yml`),
    `feed_angle_rotation -90` (a no-op here: FEED holds −90°),
    `extendflags: true`, Gpol (`p`, `60s`), KCROSS (`inf`, per scan), Xf
    (`inf`, `combine scan`), Df on J1939-6342 (`inf`, `combine scan`, clip
    0.6), each with `parang: true`.
- **apply** (`calwt: false`, `parang: true`, `calflag`): 3C286-SIM K G B Gpol
  KCROSS Xf Df; J1939-6342 K G B KCROSS Xf Df; SIM-GCAL and SIM-TARGET K F B
  KCROSS Xf Df with `gainfield [J1939-6342, nearest, J1939-6342, '', '', '']`;
  CARACal's interpolations.
- **selfcal** on SIM-TARGET: two rounds, Sp then Sa (C1 owner decision 1),
  `solint: 8` integrations from each scan start (S's blocks), refant m000,
  gain clip [0.5, 2.0]; input `CORRECTED_1GC` (copied from the apply),
  output `CORRECTED_DATA`.
- **image** (every round and the final image): 2048 × 2″, Briggs 0, 8 output
  channels joined with a 2-term spectral fit, `niter 100000`,
  `auto_threshold 3`, gridder accuracy 1e-6, `data.weights: uniform`
  (`-unit-weights`; A1's weights are all equal, so this changes nothing).

### 3.2 Deviations, fixed now

1. **refant m000, not `auto`.** E0 found `auto` chooses m022, m023, m024 on
   A1 full. Those have `d_x ≠ 0`, which brings back strategy 1's unobservable
   leakage gauge (about 0.2 points of p, A1 2.5). m000 is the only antenna
   whose `d_x` is 0 by construction, so E1 tests the implementation (A1 7.5).
2. **`polcal.frame: rang`** (schema default `casa`). The truth is in rang's
   frame (geodetic, ICRS north). CASA's angle is up to 0.54° away on a source
   11–24° from the zenith (A1 7.2); SIM-TARGET passes closer to the zenith.
   Using `casa` would spend part of the 1° χ budget on a known frame
   difference (A1 owner decision 1, still open).
3. **No `image.auto_mask`.** A0 rule 6 asks automatic masking at 5σ, then
   cleaning to 3σ. `auto_mask` is refused until G4 merges, so every image
   cleans to `auto_threshold 3` with no mask. This is the setting under which
   C5 found the CLEAN model absorbing gain errors.
4. **Stokes I self-calibration.** `rang-core selfcal` refuses `pol` other
   than I (G9 follow-up), so the polarisation measures (4.5) are taken in the
   visibility domain on the final column, not from an IQUV image.
5. **The target applied and self-calibrated**, which E2-B does not do (it has
   no usable target): the E2-A pattern (apply to the target, selfcal Sp, Sa)
   on E2-B's full-Stokes chain.
6. A0 rule 3 (same inputs for every arm) concerns E2/E3 arms; E1 has one arm
   plus the control (4.4).

## 4. Measures and gates (frozen)

Notation: σ = 0.05742 Jy, the noise per real part of every correlation in
m32 (A1 1). Truth arrays from `full/truth.npz`; `gauge0_*` is the truth in
CASA's gauge for refant m000. Rows map to truth integrations by TIME (exact
float64 match required). "Unflagged" means the cell's FLAG after the stage
being scored. ε₃₂ = 2⁻²³.

### 4.1 Each term against truth (class T)

**Noise-free tier (the small twin; C1's class T: within 1e-5).** The chain's
calibrate and apply stages on a copy of the small twin with the same
configuration except: no flag stage and no A step (the twin has no RFI; FLAG
stays all false), `run.stages: [calibrate, apply]`. Gates:

| Quantity | Gate (max over every parameter or unflagged cell) |
| --- | --- |
| K delays, centred per solution and hand (C2b's gauge-free form), against `gauge0_tau_ns` | ≤ 1e-4 ns (C5 T0's delay limit; the kernel's stop criterion) |
| SIM-TARGET 1GC composite, parallel hands: `J_p J_q*` of K F B (cal_apply, `corrupt` on unit data) against the truth's `(B K G)_p (B K G)_q*` without S, relative | ≤ 1e-5 |
| Cross-hand phase per channel, `arg(Kc(ν) Xf(ν))` against `arg(gauge0_kcross gauge0_xf)` | ≤ 1e-5 rad |
| Df, referenced, per antenna, hand, channel, against `gauge0_leakage` | ≤ 1e-5 absolute |

On 3C286-SIM the parallel hands carry G's `linear` interpolation from the
flux calibrator's two scans, which Gpol's 60 s bins follow only stepwise; the
residual sawtooth in each hand is an expected contributor to the cross-hand
phase error on the twin, named here before the run.

Reported, not gated: Gpol (it has no truth of its own: it absorbs the
interpolated G's error on 3C286-SIM); the composites on J1939-6342, 3C286-SIM and SIM-GCAL
(their own G or F applied with `linear` in time drifts inside each scan
towards the next scan's solution; the truth is constant within a calibrator
scan, so C2c 8.1's 0.015 is expected there, and only the target is
interpolation-exact by construction); KCROSS and Xf separately (C6: KCROSS
takes up the linear part of Xf; the truth's split between them is A1's stated
assumption); the F flux of SIM-GCAL against the truth's model.

**Noisy tier (m32).** "Each term's median error is at most 3 standard errors
of the expected thermal error" (A0 6.2) is read as: for each gated quantity,
with per-parameter (or per-cell) error `e` and thermal standard error `s`
predicted below,

> **median(|e| / s) ≤ 3**, over unflagged parameters or cells,

with `|e|` the modulus of a complex error (a Rayleigh variable of scale `s`
has median 1.18) or the absolute value of a real one. Reported beside it: the
signed bias `median(e/s)` (real and imaginary parts), `std(e/s)`, and median
and p95 of `|e|`.

`s` comes from the Fisher information of the term's own solve on the truth's
model and the truth's other Jones amplitudes, the unflagged cells after the
chain's flags and the solve's `uvrange` (not from the tables' PARAMERR, whose
scale C2b and C6 measured to be off by 1.5 to 30):

- a per-antenna complex gain factor on hand h from rows (p, q) with model
  `M_pq` and truth amplitudes `|J|`: per real part of `δg_p / g_p`,
  `v_p = σ² / (|J_p|² Σ_q |M_pq|² |J_q|²)`, summed over the solution's rows
  and channels;
- a delay (K per scan; KCROSS per scan): `s_τ = 1 / (2π sqrt(Σ (ν − ν̄)² |V|² / σ²))`,
  ν̄ the |V|²-weighted mean frequency (a free offset), V the truth's
  visibility of the hand pair the delay acts on;
- the cross-hand phase per channel: `s_φ = σ / sqrt(Σ |V_XY|² + |V_YX|²)` over
  3C286-SIM's rows (V the truth's corrupted cross hands, after P);
- Df per antenna, hand, channel: `v = σ² / Σ |I|² |J_p|² |J_q|²` over
  J1939-6342's rows containing the antenna (its coefficient in XY or YX);
- a product `P_pq = g_p g_q*`: per real part of `δP/P`, `v_p + v_q`, summed
  over the terms that make it (B per channel from J1939-6342, F per scan
  from SIM-GCAL with the apply's linear weights in time; K's contribution is
  part of B's per-channel phase and is not added).

Gated quantities: K delays (centred, per solution and hand, against
`gauge0_tau_ns` centred the same way); the SIM-TARGET 1GC composite
(parallel hands, relative error of `J_p J_q*` against the truth without S);
the cross-hand phase `arg(Kc Xf)` per channel; Df per antenna, hand and
channel; and, per A0 rule 5, **KCROSS and Xf separately** against
`gauge0_kcross` (as an effective delay τ_c + τ_x,r − τ_y,r) and
`gauge0_xf`. The last two are expected to fail through the known split
(C6 7); a failure there is recorded as that limit if, and only if, the
combined cross-hand phase passes. **K likewise:** K is solved per scan before
any B, so it can take up the linear part of the truth's bandpass phase, and
B the rest; a K failure (in either tier) is recorded as that K–B split if,
and only if, the target composite (which contains K·B) passes. Reported: the
calibrator fields' composites (interpolation drift, above), Gpol, F's fluxes.

### 4.2 Flags

On FLAG after the flag stage (the `rang_calibrate_*` flag version, saved by
the calibrate stage before its first write), against the m32 RFI mask
(`a1-full-m32.rfi_mask.npz`):

| Measure | How | Pass |
| --- | --- | --- |
| Recall | flagged cells among `above_5sigma` cells (a cell is flagged when its flags are set; the port flags all four correlations together) | ≥ 0.90 |
| False positives | flagged cells outside the `any` mask, against Tricolour 0.2.1 on the same MS copy, same strategy file, `-fs polarisation`, `-dc DATA`, all fields, default chunks, image `rang-tricolour:0.2.1-e1` (`results/e1-chain-scripts/e1_tricolour.Dockerfile`: the pinned base and lock of `history/tools/flagging/comparators`) | equal counts; and gate 3a: 0 cells differ, or ≥ 1 − 1e-4 of cells agree with every differing cell within one window of a chunk edge |

If the Tricolour run cannot be made, the false-positive gate is **not
checked**, not passed. Reported: flagged fractions per field after the flag
stage, after each A step and after `extendflags` (C2e decision 3), and the
static masks' share.

### 4.3 Image, Stokes I

The final image (`selfcal/SIM-TARGET/final`). **Sources:** the 36 point
components with no other component within 40″ plus that component's FWHM
(pre-counted from `truth.json`: indices 0–9, 11–26, 28–30, 32–35, 37–39 less
10, 27, 31, 36; listed in the scoring script), whose truth MFS flux (below)
is at least 50σ_img, σ_img the off-source rms of the **control** MFS image
(4.4), so the set does not depend on the chain's result.

- **Flux:** in each of the 8 output-channel images (`image-000c-image.fits`), a
  Gaussian fixed to that image's restoring beam (BMAJ, BMIN, BPA), amplitude
  and centre free, fitted to the 9 × 9 pixels around the truth position.
  Truth per output channel: the mean of `flux · (ν/ν_ref)^α` over the
  channel's 32 input channels. Ratio per source: `r = Σ_c F_c / Σ_c S_c`.
- **Position:** the same fit on the MFS image; offset from the truth's RA,
  Dec in units of the MFS BMAJ.
- **Pass:** `|median(r) − 1| ≤ 0.01`; robust scatter `1.4826 MAD(r) ≤ 0.01`;
  every source's offset ≤ 0.1 beam.
- **Scorer validation (fixed now):** the same measure on the control image.
  If the control misses `|median(r) − 1| ≤ 0.005` or scatter ≤ 0.005, the
  scorer's convention is not validated: the frozen result is reported as it
  is, marked "scorer not validated", and the chain-to-control ratios are
  reported beside it as a labelled secondary reading.

### 4.4 Residual, against a control with the true gains

- **Control:** `CORRECTED_TRUTH` = DATA corrected by the truth's exact inverse
  (`rang.simtruth.correct`: G with S folded in, K, B, KCROSS, Xf, linear Df
  and P in rang's frame, the truth's own construction), on SIM-TARGET's rows,
  written through `rang.core_writeback` after the chain; FLAG is the chain's
  final FLAG. It is imaged with exactly the final image's gemclean arguments
  (`core_pipeline.gemclean_arguments`), column `CORRECTED_TRUTH`.
- **Measure:** rms of the MFS restored image outside the off-source mask (A0
  rule 6: the mean of the two MFS images, above 5 × its MAD-based σ, dilated
  by 2 restoring-beam BMAJ), over the whole image.
- **Pass:** chain ≤ 1.1 × control.

### 4.5 Polarisation

Visibility domain (C6w's estimator, `check_c6w.target_pol`, chunked; per
channel, the component's own I visibility shape fitted to CORRECTED minus the
truth's other components, derotated by the truth's χ0 + RM λ²), on the final
`CORRECTED_DATA`; `CORRECTED_1GC` reported beside.

- **Polarised sources:** the target components with p ≥ 1 % (indices 0, 17,
  23, 30, 37 and the Gaussian 40), gated when their polarised SNR
  `|R| / σ_R` on the control column is ≥ 50. Pass: `|p − p_t| ≤ 0.002` and
  `|Δχ| ≤ 1°` for every gated source. If none qualifies, the gate is not
  checked.
- **Leakage, unpolarised sources:** SIM-GCAL (point at the phase centre, never
  in a polarisation solve): per channel the mean over unflagged cells of each
  correlation, then `sqrt(Q² + U² + V²) / I`; and every isolated unpolarised
  target point of truth flux ≥ 50 mJy (indices from 4.3's list): the same
  fit with a V term, `sqrt(a_Q² + a_U² + a_V²) / a_I` band-weighted. Pass:
  SIM-GCAL's median over channels ≤ 1e-3, and every target point ≤ 1e-3.
- **Circular, reported only:** 3C286-SIM's χ (Xf is solved on it against a
  33° model) and p; J1939-6342's leakage (Df is solved on it).

### 4.6 Self-calibration

"Gains recovered from a deliberately wrong starting model": the starting
model is round 1's CLEAN model, imaged from `CORRECTED_1GC`, which still
carries S. Per round and hand, the gauge-free products `g_p g_q*` of the
stored gains (`gains.qc`) against the truth's `S_p S_q*` on the same 8-integration
block, over antenna pairs both leave unflagged:

- round 1 (Sp): the phase error of the product; round 2 (Sa): the complex
  relative error.
- **Gate (class T, 4.1's form):** `median(|e| / s) ≤ 3`, with `s` from the
  Fisher information of the target sky (`simtruth.target_coherency`) per
  block and antenna.
- Reported against C5's T2 limits (round 1 phase median ≤ 1.0°, p95 ≤ 3.0°;
  round 2 phase ≤ 0.5° / 1.5°, amplitude ≤ 1 % / 3 %).

**Expected:** a failure, C5's model absorption (no mask, a first model from
S-corrupted data). It is recorded as that known limit, with C5b (masks and
per-round settings after G4) as the follow-up. It is not rescued here.

## 5. Procedure

1. Dry run of the configuration on A1 small (`-01-dry`): execution only.
2. m32 written (`-02-data`); **check, before any scoring:** m32's DATA equals
   A1 full's on the corresponding rows, for 3 integrations chosen now (the
   first of scan 1, the 32nd of scan 4, the 15th of scan 21): maximum
   absolute difference 0. Its RFI mask is the generator's own.
3. This protocol committed.
4. Scored chain run on a copy of m32 (`-03`), then the control column and
   image, then Tricolour on a fresh copy of m32 (`-04`, WSL); then the
   noise-free tier on the small twin (`-05`).
5. Scoring (`results/e1-chain-scripts/e1_score.py`) writes `result.json` per
   run; the archive goes to `research/results/e1-chain.json`.

### 5.1 Rules for failures (A0 6.5)

An E1 failure is located with truth. If it is a bug, it is fixed with a test,
and E1 reruns (new run number, the whole chain); both results are reported.
A known limit (named in 4.1, 4.6 or 3.2) is recorded, not rescued. Nothing in
section 4 changes after a result; added analyses are labelled post hoc.

## 6. Proposed, implemented, measured

| Item | State |
| --- | --- |
| Configuration, gates, scorer, control | proposed and frozen (`2c506eb`), then implemented |
| The chain on m32, the control, Tricolour, the twin tier | **measured** (section 7) |
| Causes of the failures | post hoc (section 8), labelled; some measured, some not established |

## 7. Results (measured 2026-11-09)

Archive: [results/e1-chain.json](results/e1-chain.json) holds:
- the scored run's `result.json` and the twin's;
- the control record and the m32 checks;
- every post-hoc diagnostic.

Runs are under `D:\rang\outputs\e1-20261109-NN`. Each has a `.code/` snapshot
(commit `2c506eb` plus the working-tree diff of the scripts) and a log with
START and END lines.

### 7.1 Execution

| Run | What | Result |
| --- | --- | --- |
| `-01-dry` | the configuration on A1 small (unscored) | exit 0. The control column, its image and the scorer also ran on it; the scorer's output was not read |
| `-02-data` | m32, written by `a1_simtruth.py`: 558 integrations, 1,124,928 rows, 14.2 GB | exit 0. RFI on 8.16 % of cells (`any`), 3.65 % above 5σ |
| `-03` | **the scored chain**: `rang-core run` on a copy of m32 | exit 0. Flag 109.7 s, calibrate 723.0 s, apply 98.6 s, selfcal 764.1 s |
| `-03/control` | `CORRECTED_TRUTH` and its image | exit 0. Write 110.8 s, image 133.8 s |
| `-04-tricolour` | Tricolour 0.2.1 on a fresh copy of m32 (WSL, `rang-tricolour:0.2.1-e1`) | exit 0, 20 min 25 s of flagging |
| `-05-twin` | calibrate and apply on the small twin | exit 0 (3.1 s, 1.6 s) |
| `-06-diag`, `-07-casak`, `-09-casak-twin` | post-hoc diagnostics, and CASA 6.7.6.14 `gaincal` K on m32 and the twin | section 8 |

**The m32 check (section 5, item 2) failed as frozen.** m32's DATA is not
bit-identical to A1 full's:
- On the three integrations checked, 4, 6 and 5 of 2,064,384 elements differ.
- Each differs by at most 1 float32 ulp of its real or imaginary part:
  2.4e-7 absolute, 6e-8 relative (post-hoc script `e1_verify_posthoc.py`).
- A1 full was written on Linux and m32 on native Windows. A1 section 4 already
  says that bit-identical regeneration across hosts is not claimed (libm).
- Scoring uses A1 full's `truth.npz`. A 1-ulp difference is 1e-6 of σ and
  changes no gate.

**Every self-calibration image stopped on `niter`.**
- Rounds 1 and 2 and the final image each stopped at 100,000 components after
  4 major cycles (`stop Components`; Q/Q0 0.095, 0.130 and 0.075). None reached
  the 3σ threshold.
- The control image did reach it: 83,646 components, 7 cycles, `stop
  Threshold`.
- So the chain's models and its final image are incomplete CLEANs.
  `niter: 100000` is the schema default, frozen in 3.1.

### 7.2 Against the frozen gates

| Gate (A0 6.3) | Measured | Verdict |
| --- | --- | --- |
| **Each term, class T, noisy (m32)**: median(\|e\|/s) ≤ 3 | K 5,160. Target 1GC composite 33.2 (median \|e\| 4.2e-3, s 1.2e-4). Cross-hand phase `arg(Kc Xf)` 195 (median 0.017 rad, p95 0.29 rad). KCROSS 14,628 (+0.11, +0.12, +0.11 and −0.017 ns against τ_c' = 2.943 ns). Xf 1,788 (median 0.155 rad). Df 18.9 (median 1.3e-3) | **not met** |
| **Each term, class T, noise-free (small twin)** | K max 0.089 ns (gate 1e-4). Target composite median 1.6e-6, p95 1.7e-5, max 1.2e-4 (gate 1e-5). Cross-hand phase max 0.25 rad (gate 1e-5). Df max 4.4e-3 (gate 1e-5) | **not met** |
| K, KCROSS and Xf "as the split" | the condition (target composite and combined phase both pass) does not hold | recorded as failures, not as the split |
| **Flags: recall** of `above_5sigma` | 0.8858 (Tricolour: 0.8858) | **not met** (≥ 0.90) |
| **Flags: false positives equal Tricolour's** | 71,465,778 against 71,465,544 (+234). 530 cells (2,120 elements) of 288 M differ: 362 flagged by rang only, 168 by Tricolour only. Agreement 1 − 1.8e-6 | **not met**: the counts differ, and the differing cells are not at chunk edges (27 baselines, every time of their scans, 414 of them in scan 1, 42 channels) |
| **Image, Stokes I** (35 sources ≥ 50σ) | chain: median ratio 1.0233, robust scatter 1.44 %, largest offset 0.046 beam | **not met**, and **scorer not validated**: the control gives 1.0296 and 1.42 % |
| Image, labelled secondary reading (chain / control, 4.3) | median 0.9929, scatter 0.80 % | – |
| **Residual**: off-source rms ≤ 1.1 × the control's | 64.3 μJy against 20.3 μJy: 3.16 × | **not met** |
| **Polarisation** (gated: components 0, 17, 30 and 40, polarised SNR ≥ 50 on the control) | Final column: component 0 Δχ +4.1°; 17 Δχ −1.87°; 30 Δp +0.58 points; 40 Δp +0.69 points and Δχ −2.3°. 1GC column, beside it: 0 passes (Δp −0.10 points, Δχ +0.19°); Δp −0.31 (17), −0.48 (30), −1.6 (40) points | **not met** |
| **Leakage** ≤ 0.1 % of I | SIM-GCAL: median 0.54 %, p95 2.6 %. The 11 unpolarised target points: 0.47–1.1 % on the final column (mostly Q, −0.4 to −1.1 %); 0.05–0.74 % on 1GC (mostly U, about +0.3 %) | **not met** |
| **Self-calibration**, class T | median \|e\|/s 32.6 for round 1 (Sp), 45.7 for round 2 (Sa) | **not met**, as 4.6 expected |
| Self-calibration against C5's T2 limits (reported) | Round 1 phase: median 0.76°, p95 3.15° (limits 1.0° and 3.0°). Round 2 phase: 0.61° and 2.32° (0.5° and 1.5°). Round 2 amplitude: 0.97 % and 2.93 % (1 % and 3 %), where S itself is 0.74 % | round 1's p95 and round 2's phase miss; round 2's amplitude error is larger than S |

**The scorers on the control (4.3–4.5).** On the control column every
polarisation and leakage measure passes:
- the four gated components: Δp ≤ 0.03 points, |Δχ| ≤ 0.25°, polarised SNR
  83–407;
- the 11 points: leakage ≤ 0.04 %.

So the visibility-domain estimators are validated, and the polarisation and
leakage failures come from the calibration. The image scorer is not validated:
the control gives 1.0296.

**Reported, not gated:**
- 3C286-SIM: p 0.0952 (truth 0.095); |χ − 33°| median 2.49°, p95 7.3°. This χ
  is circular, since Xf is solved on this source.
- J1939-6342: QUV/I median 1.8 %.
- `fluxscale` gives SIM-GCAL 4.289 Jy (truth 4.213 Jy at 1,284 MHz); on the
  twin, 4.292 Jy.
- The calibrators' own composites, which carry the interpolation drift of 4.1
  (median relative error):

| Field | m32 | Twin |
| --- | ---: | ---: |
| J1939-6342 | 3.1e-3 | 9.9e-5 |
| SIM-GCAL | 1.3e-2 | 2.0e-3 |
| 3C286-SIM | 1.7e-3 | 1.5e-3 |

**Flagged fractions** (C2e decision 3), as a share of cells. Injected RFI
(`any`) covers about 8 % of every field.

| Field | After the flag stage | After calibrate (A step, extendflags) | Final |
| --- | ---: | ---: | ---: |
| J1939-6342 | 33.7 % | 37.9 % | 44.6 % |
| 3C286-SIM | 34.2 % | 38.4 % | 45.5 % |
| SIM-GCAL | 32.9 % | 59.4 % (Asec takes it from 41.1 % to 59.4 %) | 59.4 % |
| SIM-TARGET | 26.8 % | 26.8 % | 36.3 % (apply's `calflag`, and selfcal) |

- `extendflags` added 16.0 M cells on 3C286-SIM and J1939-6342: `growtime`
  26,684, `growfreq` 3.0 M, `nearfreq` 12.9 M, `neartime` 0.28 M, `growaround`
  0.66 M.
- The flag stage flags 3.4 to 4.2 times the injected RFI. Tricolour does the
  same, so this is the strategy itself: its static masks, and its mask on
  baselines of 0–550 m.

## 8. Where the failures come from (post hoc, labelled)

Written after the results; nothing in section 4 changed. The scripts are in
`results/e1-chain-scripts/` (`e1_diag*.py`, `e1_casa_k.py`,
`e1_flagdiff.py`).

1. **Five antennas lose all calibration through the reference-antenna rule.**
   - K, G, Gsec, F and Gpol flag m007, m010, m017, m023 and m041 on one or both
     flux-calibrator scans.
   - The cause: the flag stage removed every cell of their baselines to m000 in
     those scans. m000 has 96 and 160 fully flagged rows in the two scans.
     CASA's KJones rule flags an antenna that has no cell on its baseline to the
     refant.
   - **CASA 6.7.6.14's `gaincal` K, on the same flags, flags the same antennas
     in both scans** (`-07-casak`).
   - Not a rang bug. It follows from deviation 3.2 item 1 (refant m000 instead
     of CARACal's `auto`, which picks the antenna with fewest flags) and from
     the strategy's short-baseline mask.
2. **K never converges, and one delay is wrong in CASA too.**
   - K reports a converged fraction of 0 in both intervals (50 iterations).
   - m034's Y delay on the first scan is 6.26 ns, against the truth's 7.91 ns
     (7.88 ns on the second scan). **CASA's K gives 6.22 ns there.**
   - Rang's K against CASA's (probe `e1_kcompare.py`, added after the first
     write-up): median 0.005 ns, **p95 0.068–0.071 ns, so K misses C1's class B
     (p95 ≤ 0.03 ns) against CASA on m32**; 13 and 14 antenna-hands exceed
     0.03 ns per scan. On the noise-free small twin, rang's and CASA's K agree
     (median 0.0023 ns, p95 0.010 ns), both 0.056–0.058 ns from the truth (the
     split), and rang's two scans are identical. So the m32 miss appears only
     with noise and flags, together with the non-convergence: **rang only,
     cause not established**. C2c's held-out CASA cases with nothing
     pre-applied passed (p95 ≤ 0.013 ns), on smaller data.
   - The 0.03–0.1 ns offsets between K and the truth are the same in both
     scans: the K–B split.
   - Interpolated to the target, the bad delay decorrelates F's `inf` solve and
     puts m034's Y-hand target composite off by a factor 3.6 in amplitude.
3. **Per-antenna amplitude errors of 0.27 % (median) in the target
   composite**, constant in time and channel.
   - Hypothesis, written before its probe: F is solved against CARACal's flat
     1 Jy model on a source with α −0.6, and each antenna's flagged channels
     give it its own effective frequency. C2d section 8 measured this mechanism
     at 0.5 % across antennas.
   - Probe `diag3`: correlation 0.30–0.37 with the prediction, and the
     predicted spread is too large.
   - Partly supported, not established.
4. **Cross-hand phase.**
   - Noise-free, the per-scan KCROSS values spread over 0.10 ns (0.017 to
     0.121 ns above τ_c'). With Xf combined over scans, the combined phase is
     then off by up to 0.25 rad at the band edges.
   - Possible cause: strategy 1 solves KCROSS and Xf before Df, while the cross
     hands hold 1–3 % leakage. The polarised part rotates with parallactic
     angle; the leakage does not.
   - C6w showed rang's polcal chain equal to CASA's (χ within 0.003°) on
     `poldx` and `polholdout`, where the per-scan KCROSS also spread by 0.11 ns
     (3.13–3.24 ns) in both rang and CASA, which supports a method limit. No
     CASA chain ran on m32 or on this twin, so **parity is not shown here**.
   - Df (probe `e1_diag6.py`): moving the truth's leakage into the chain's
     cross-hand gauge (d_x → e d_x, d_y → conj(e) d_y, e the chain/truth
     cross-hand phasor) lowers the twin's Df error from median 1.4e-3 (max 4.4e-3)
     to 5.5e-4 (max 1.7e-3). Part of Df's error is this gauge; the rest is not
     explained.
   - The +0.3 % U leakage on 1GC and the polarisation misses follow from this
     phase error.
5. **Self-calibration makes Q worse.**
   - On the final column, Q/I on unpolarised points is −0.4 to −1.1 %; on 1GC
     it is near 0.
   - Sa solves each hand against a Stokes I model, so it moves the XX/YY ratio.
     With incomplete models (7.1) and no mask, this is C5's model absorption.
   - Its round-2 amplitude error (0.97 %) is larger than the residual S it
     should remove (0.74 %).
   - A known limit. The follow-ups are C5b (masks and per-round settings, after
     G4) and self-calibration with polarisation (G9's follow-up).
6. **The residual is 3.2 times the control's.** The chain's final CLEAN stopped
   on `niter` (7.1), and its gains carry items 1–5. These runs cannot separate
   the two.
7. **The image scorer.** On the control, the fits sit at 1.03 in the channel
   images and at 0.95–0.99 in the MFS image (probe `diag4`). So the frozen
   truth convention, the plain mean of S over each output channel's input
   channels, does not match GeMClean's channel-image flux scale. Not traced.
8. **Flags against Tricolour: 530 cells differ** (1.8e-6 of the cells), none at
   chunk edges. On A1 small the same strategy gives 0 of 3,194,880 elements
   different (`-01-dry`). Cause not established. Two candidates, neither tested:
   - floating-point differences near a threshold between the native Windows
     build and Tricolour's Numba (main built on Windows is already known not to
     reproduce Linux bytes);
   - a window effect that only the whole-array data triggers.
9. **The twin's target composite** misses 1e-5 on three of the seven target
   scans only (1.7e-5 to 1.2e-4). The error is in amplitude and flat in channel;
   the other four scans sit at 8e-6. Not K: on the twin rang's two K solutions
   are identical. Cause not established: F on each gain-calibrator scan, or its
   interpolation in time.

**Bug or limit (A0 6.5).** No bug was located with truth, which is not the
same as none existing:
- shared with CASA, shown: item 1 and m034's delay in item 2;
- known limit: item 5;
- rang only, cause not established: K's class-B miss against CASA on m32 (item 2);
- cause not established: items 3, 4, 7, 8 and 9 (4 and 9 noise-free).

Nothing was fixed, so E1 did not rerun.

## 9. Owner decisions (open)

1. **The reference antenna for E1.**
   - m000 separates implementation from strategy 1's leakage gauge (A1 2.5).
     On this data it loses five antennas to CASA's K rule (section 8, item 1).
   - `auto` keeps those antennas but brings back the gauge error.
   - Either choice changes E1's numbers.
2. **`image.niter`.** The default of 100,000 is too small for the
   self-calibration images here. Raise the default, or set it per
   configuration. A rerun of E1 with a larger value is a new, labelled run.
3. **Whether E1 continues as frozen or becomes a diagnostic task.**
   - The frozen gates mix two things. One is implementation: rang against CASA
     and Tricolour. The other is the limits of CARACal's method on this truth:
     the flat secondary model, KCROSS per scan before Df, and Stokes I
     self-calibration.
   - Proposed: add a CASA-chain arm on m32 and the twin (the sequence of C6w's
     `check_c6w.py`). Each failure then splits into "CASA too" and "rang only".
     Rerun E1 after C5b and G4.
4. **The image scorer's convention** (section 8, item 7) must be fixed before
   any rerun, and validated on the control first, as 4.3 requires.
5. **The 530 flag cells that differ from Tricolour** (section 8, item 8). Next
   step: probe one differing baseline's windows, natively and in a Linux build.

## 10. Not checked

- A CASA or QuartiCal chain on m32 or the twin. Only CASA's first K ran.
- The full A1 MS: m32 holds only its first 32 integrations per scan.
- An IQUV image (deviation 3.2 item 4). Polarisation was measured in the
  visibility domain.
- The `casa` parallactic frame (deviation 3.2 item 2).
- Timing. No timing claim is made: the runs shared the host with task G4 under
  the lock.
- Whether a larger `niter`, a mask or `refant: auto` would change the verdicts.

## 11. Timings

Each run held `tools/heavy_lock.py`; lock waits are excluded unless stated.

| Run | Wall |
| --- | ---: |
| generate m32 (6 spawned workers) | 104.5 s |
| `rang-core run` on m32: flag, calibrate, apply, selfcal | 109.7 s, 723.0 s, 98.6 s, 764.1 s |
| control: write `CORRECTED_TRUTH`, then image | 110.8 s, 133.8 s |
| Tricolour 0.2.1 on m32 (WSL docker) | 20 min 25 s |
| Tricolour 0.2.1 on A1 small | about 5 min (from taking the lock to END) |
| CASA `gaincal` K on m32's flux calibrator | 46 s, container included |
| scorer, target pass (polarisation and the selfcal Fisher sums) | 40 min 14 s from START, lock waits included (at most 36 min of work) |
| twin: calibrate, apply | 3.1 s, 1.6 s |
| dry run on A1 small | about 6 min (selfcal 345 s) |

## 12. Files, and what is left on disk

- Note, scripts and archive:
  - this file;
  - `results/e1-chain-scripts/`: `e1_config.yaml`, `e1_job.ps1`, `e1_run.py`,
    `e1_score.py`, `e1_tricolour.sh`, `e1_tricolour.Dockerfile`,
    `e1_casa_k.py`, `e1_kcompare.py`, `e1_flagdiff.py`, `e1_diag*.py`, `e1_verify_posthoc.py`;
  - `results/e1-chain.json`.
- `D:\rang\outputs\e1-20261109-*`, about 83 GB:

  | Directory | Contents | Size |
  | --- | --- | ---: |
  | `-02-data` | m32 | 14 GB |
  | `-03` | the scored copy, with its added columns | 52 GB |
  | `-04-tricolour` | Tricolour's copy | 14 GB |
  | `-01-dry` | the dry run | 3 GB |
  | the others | | small |

- The WSL image `rang-tricolour:0.2.1-e1`.

## For the coordinator

**`research/STATE.md`, new top entry:**

> E1, 2026-11-09 (implemented, measured; [e1-chain.md](e1-chain.md)). The whole
> chain through `rang-core run` (flag, CARACal's full-Stokes calibrate, apply,
> selfcal Sp then Sa, image), on A1 full's first 32 integrations per scan (64
> antennas, 256 channels). It exits 0; **no E1 gate is met as frozen**.
> - Flags: recall 0.886, the same as Tricolour's. 530 of 288 M cells differ
>   from Tricolour 0.2.1.
> - Terms: every class-T measure fails, noisy and noise-free. CASA's own K flags
>   the same five antennas (no baseline left to refant m000 after flagging) and
>   makes the same 1.65 ns delay error.
> - Image: the flux scorer is not validated (control 1.03); chain against
>   control 0.993, scatter 0.8 %. Residual 3.2 × the true-gain control's. Every
>   selfcal CLEAN stopped at `niter` 100,000.
> - Polarisation: misses of 1.9–4.1° in χ and up to 0.7 points in p; leakage
>   0.5–1.1 % against a 0.1 % gate. On the control the estimators pass.
> - Selfcal: fails, as expected (C5's model absorption; C5b).
> - No bug located with truth. Shared with CASA (shown): the K flags and the
>   m034 delay. Known limit: selfcal. Rang only, cause not established: K misses
>   CASA's K at p95 (0.07 ns) on m32, but agrees on the twin. Cause not
>   established: the rest, two noise-free (cross-hand phase, a 1.2e-4 composite ramp).
> - Before a rerun the owner decides refant, `niter` and a CASA-chain arm.

**`research/README.md` index line:**

> New, 2026-11-09: E1, [the whole chain on simulated truth](e1-chain.md): no
> gate met as frozen; some causes shared with CASA, one rang-only K miss, the
> rest not established.

**`research/finish-plan.md`:**
- E1 row: "Run 2026-11-09 ([e1-chain.md](e1-chain.md)): no gate met as frozen;
  shared with CASA (K flags, one delay), known limit (selfcal), rang-only K
  class-B miss on m32, the rest not established; owner decisions in its
  section 9 before a rerun (after C5b and G4)".
- Section 7: add the decisions of section 9.

**`research/tool-timings.md`:** the rows of section 11, added on this branch.
