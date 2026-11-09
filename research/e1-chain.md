# E1: the whole chain on A1's simulated truth

Task E1 of [finish-plan.md](finish-plan.md), on branch `fp-e1-chain` from main
`0d6230d`, 2026-11-09. Native Windows (`.venv` with uv, Python 3.14); WSL only
for the Tricolour 0.2.1 oracle.

**Status: protocol frozen (sections 1 to 6), committed before the first scored
run.** Results go below in later commits; this text changes only through a
dated, labelled amendment.

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
| Configuration, gates, scorer, control | proposed, frozen here |
| Runs | not run |
