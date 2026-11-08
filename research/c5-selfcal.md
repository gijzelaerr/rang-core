# C5: self-calibration from MODEL_DATA

Task C5 of [finish-plan.md](finish-plan.md), on branch `fp-c5-selfcal` from
main `3defaae`, 2026-11-08.

**Status: implemented and measured.** The protocol (sections 1 to 5) was
committed (`637f168`) before any comparison and is unchanged; results and
post-hoc changes are in sections 6 to 8.

- **Met:** G2 (every round agrees with QuartiCal to 1e-15 relative,
  delays to 5e-8 ns, development and held out), G4 (intervals and apply),
  G5 (E2-A), T1 (the solve is at the Cramér-Rao bound on a perfect model,
  held out too), and T0 after one labelled post-hoc change (Sd starts at zero
  delay).
- **Not met as frozen: T2, the full loop against truth, on development and
  held-out cases alike** (so G1 partly and G3 partly). Phase misses by 2 to
  4 times in the median (round 1 2.0-2.5° against 1.0°, round 2 1.05-1.9°
  against 0.5°) and by about 10 times in the p95 (10-17° against 1.5-3°);
  the round-2 amplitude median is at or just above its 1 % limit
  (1.05-1.45 %); only the delay medians pass (0.006-0.007 ns against
  0.01), their p95s do not (0.07-0.08 ns against 0.03). The errors sit on
  the outer antennas. Section 7 shows, post hoc, that they come from the
  CLEAN model: imaged from gain-corrupted data without a mask, it absorbs
  the gain errors on long baselines. A model imaged with the same settings
  from the same noisy data corrected by the true gains gives 0.03° / 0.08°
  and 0.09 % / 0.29 % (median / p95), inside every limit.
- No novelty claim: this is a port of CARACal's loop with QuartiCal's
  kernels.

## 1. What CARACal does, and what rang-core does

Read in CARACal `8f7bb363` (`workers/selfcal_worker.py`, in the ignored
`outputs/c1-sources-20261105/caracal-8f7bb363/`) [C]:

- **Rounds.** `cal_niter` calibration rounds. The loop (lines 2300-2370)
  images (`image_1`), then calibrates round 1, images (`image_2`), calibrates
  round 2, and images once more (`image_{cal_niter+1}`): `cal_niter + 1`
  images, the last of the self-calibrated data.
- **One term per round.** `calibrate_cubical` (line 1392) takes the round's
  matrix type as `gain_matrix_type[num - 1 if len(...) >= num else -1]`
  (line 1430) and its interval as `gsols_timeslots[num - 1 if num <=
  len(...) else -1]` (line 1453): per-round lists whose last entry repeats.
- **Not cumulative.** CubiCal reads `data-column: DATA` of the split target
  MS (the 1GC-corrected data, line 1524) and `model-list: MODEL_DATA`
  (`cal_model_mode: vis_only`), and writes the corrected data. Every round
  solves the whole residual gain from the same 1GC data against the latest
  model.
- **Terms.** `GainDiagPhase` (phase-diag), `GainDiagAmp`, `GainDiag`,
  `Gain2x2`, and `Fslope` (CubiCal `f-slope`, `phase-diag`: a phase and its
  slope in frequency per antenna and hand). `g-time-int` in timeslots
  (integrations), `g-freq-int` in channels; `g-clip-low`/`g-clip-high`
  (`cal_gain_cliplow`/`high`) clip gain amplitudes.

**rang-core's form (implemented in this task):**

| CARACal | rang-core config | Here |
| --- | --- | --- |
| `cal_niter` | `selfcal.rounds` (default 2) | rounds of image, model, solve, apply; then a final image |
| `gain_matrix_type` per round | `selfcal.terms`, one term per round, the last repeating | `Sp` (phase-diag, QuartiCal `phase`), `Sa` (diag, QuartiCal `diag_complex`), `Sd` (`Fslope`, QuartiCal `delay_and_offset`) |
| `gsols_timeslots`, `gsols_chan` per round | each term's `solint` and `freqint` | `solint`: `inf` (the scan), `int`, N integrations from each scan start (CARACal's timeslots, QuartiCal's `time_interval`), or `Ns` (CASA's seconds bins, `rang.cal_gain.solint_bins`); `freqint` (Sp, Sa): `inf` or N channels |
| split MS, DATA = 1GC | `selfcal.input_column` (default `CORRECTED_1GC`) | copied from `apply.column` when this run's apply finished after the last copy; otherwise an existing column is used as it is |
| CubiCal output column | `selfcal.output_column` (default `CORRECTED_DATA`) | `S_p^-1 V S_q^-H` of the input column, on the solutions' own bins |
| MODEL_DATA from WSClean | `selfcal.model_column` (default `MODEL_DATA`) | gemclean's model images predicted by `rang.core_model.write_model_data` (task G6) each round, whatever `image.write_model` says |
| `cal_gain_cliplow/high` | `selfcal.gain_clip` (default `[0.5, 2.0]`) | solutions with an amplitude outside are flagged |
| `minuvw_m` | `selfcal.minuvw_m` | baselines shorter are left out of the solve |
| reference antenna | `selfcal.refant` (new; null: `calibrate.refant`, or 0) | QuartiCal's referencing (the solve is QuartiCal's kernel, `casa_rules=False`) |

The imaging of every round uses the `image` section (fields, size, weights,
`data.scans`), with the data column set by the round: round 1 images the
input column, round r > 1 and the final image the output column.

**Command path: the `selfcal` stage of `rang-core selfcal` and `rang-core
run`, with the rounds inside it.** W2 already gave it a slot (`STAGES`,
`STAGE_SECTIONS`, `WRITES_FLAGS`, the CLI). The rounds are one unit in
CARACal (a worker with its own loop), the round's state (which column is
imaged, which model is current) is internal to it, and splitting it over the
`image` and `calibrate` stages would need per-round stage state and would
break the stage hash and stale rules. The stage hash covers `fields`,
`data`, `image` and `selfcal` (W2's `STAGE_SECTIONS`), so `selfcal.refant`
is a key of its own and not read from `calibrate` silently.

**Flags.** Each round's apply ORs the flags of invalid solutions (kernel
flags, gain clip) into FLAG, so they accumulate over rounds, as later rounds
see the data the earlier rounds flagged. The stage saves its flag version
before its first write; a rerun first restores it (W2's rule).

**Solutions on disk.** Per field and round, `<run>/selfcal/<field>/round-N/`
holds the image files, the term's gains as a QuartiCal gain store
(`gains.qc`, one partition per scan, diagonal 2x2), and for Sd the delays
and offsets (`delays.npz`). A CASA table is not written: S follows P, which
CASA's type order cannot express (C1 section 3.2), so the stage applies its
own solutions.

**Left out (stated, not silent):** `complex` (2x2) self-calibration terms
are refused; CubiCal `madmax` flagging (C1 O5) and `aimfast` stopping (O10)
are not ported; image settings cannot vary per round (CARACal's
`cleanmask_thr`, `clean_cutoff` lists).

## 2. Oracles

- **QuartiCal 0.2.7** (`rang-formats-oracle:20261030`, `/opt/qc`), a
  substitute for CubiCal (not in any image here; C1 owner decision 1), on
  the same input column and the same MODEL_DATA as the round it is compared
  with: `G.type` `phase` (Sp), `diag_complex` (Sa), `delay_and_offset` (Sd),
  `G.time_interval` = the round's N, `G.freq_interval` = the round's freqint
  (0 for inf), `solver.reference_antenna` = the refant,
  `input_ms.weight_column=WEIGHT_SPECTRUM`, `solver.robust=false`,
  `mad_flags.enable=false`, `solver.iter_recipe=[50]`,
  `solver.convergence_criteria=1e-7`, one thread (C2a's `QC_OPTIONS`). The
  MODEL_DATA of round r is rebuilt on a copy of the MS from round r's model
  images with `rang.core_model.write_model_data` (G6: the same bits the
  stage wrote), and rang's library solve on that copy must equal the stage's
  stored gains bit for bit before QuartiCal's are compared.
- **Simulated truth** (section 3): the injected self-calibration gains.

## 3. Simulated truth (`examples/c5_selfcal_sim.py`)

A target-only Measurement Set through rang's table writer, built from A1's
geometry and target sky (`rang.simtruth`, `examples/a1_simtruth.py`'s
writer), as if 1GC were perfect: `DATA = S_p M S_q^H + noise`, where M is the
target's Stokes I coherency (XX = YY = I, XY = YX = 0) and S the diagonal
self-calibration gain. That isolates S from 1GC solve errors.

- 32 antennas (`range(0, 64, 2)` of `data/meerkat.itrf.txt`), 64 channels of
  13.375 MHz from 856 to 1712 MHz, 8 s integrations.
- The seven target scans of A1's schedule (scan numbers 4, 6, 10, 12, 16,
  18, 20, at A1's start times), 16 integrations each: 112 integrations,
  496 baselines, 55,552 rows. No calibrator rows.
- Sky: A1's `target_sky` from the case's sky seed (40 points of 1-500 mJy,
  5 Gaussians of 20-120″, an arc of 10 Gaussians of 0.3 Jy, within 0.4° of
  the phase centre), **unpolarised and with a flat spectrum** (p = 0,
  α = 0), so that the Stokes I, one-channel model the stage images can
  represent the sky; the imager's spectral and polarised modelling are G3's
  and G9's.
- Noise: σ = SEFD / √(2 Δν Δt) = 0.0287 Jy per real and imaginary part,
  SEFD 420 Jy, from `simtruth.noise_integration` (the noise seed); WEIGHT
  and WEIGHT_SPECTRUM 1/σ², SIGMA σ. No RFI, no flags, no autocorrelations.
- S is constant over blocks of 8 integrations from each scan start
  (`simtruth.SELFCAL_BLOCK`): two blocks per scan, 14 in all. Per antenna
  and hand (the reference antenna too):
  - **`pa` cases:** phase φ_base + φ_block, φ_base ~ U(−30°, 30°),
    φ_block ~ N(0, 10°); amplitude 1 + a_base + a_block, a_base ~
    U(−0.1, 0.1), a_block ~ N(0, 0.01). Constant in frequency.
  - **`delay` cases:** `exp(i(φ + 2π τ (ν − ν₀)))`, ν₀ = 1284 MHz (the band
    centre), τ = τ_base + τ_block with |τ_base| ~ U(0.05, 0.4) ns and a
    random sign, τ_block ~ N(0, 0.03 ns); φ = U(−20°, 20°) + N(0, 5°) per
    block; amplitude 1.
- A column `MODEL_TRUE` holds M (the core DFT, `simtruth.target_coherency`)
  for the perfect-model tiers; truth gains, blocks, sky and seeds go to
  `truth.npz`, `truth.json` and `provenance.json`. `--noiseless` writes the
  twin without noise.

**Cases and seeds** (none in `simtruth.SEEDS` or elsewhere in the
repository; `jones, sky, rfi, noise`, the rfi seed unused):

| Case | Truth | Seeds | Role |
| --- | --- | --- | --- |
| `c5pa` | pa | 20261301-04 | development |
| `c5delay` | delay | 20261311-14 | development |
| `c5pa-held` | pa | 20261321-24 | **held out**, frozen here |
| `c5delay-held` | delay | 20261331-34 | **held out**, frozen here |

**Stage settings** (every loop case): `image` size 2048 × 2048, scale
2asec, Briggs robust 0, niter 100000, auto_threshold 3, other image keys at
their defaults, `fields: [target]`; `selfcal.input_column: DATA` (the
simulated 1GC data), `refant: 0`, `gain_clip [0.5, 2.0]`, `minuvw_m: 0`,
term solver defaults (50 iterations, 1e-7, 0.99); `data.weights: as_is`.

| Loop | MS | rounds | terms |
| --- | --- | --- | --- |
| L-pa | `c5pa`, `c5pa-held` | 2 | `{Sp, solint 8}`, `{Sa, solint 8}` (the default phase then amplitude) |
| L-delay | `c5delay`, `c5delay-held` | 2 | `{Sd, solint 8}`, `{Sd, solint 8}` (CARACal's `Fslope, Fslope`) |
| L-solint | `c5pa` | 2 | `{Sp, solint 4, freqint 16}`, `{Sa, solint 64s}` |

## 4. Gates (frozen before the first comparison)

Comparisons are gauge-free: per hand, the baseline products
`P_pq = g_p conj(g_q)` (`rang.cal_gain.baseline_products`) over every
solution interval and antenna pair both leave unflagged; for Sd also the
delay differences `τ_p − τ_q` per hand. For truth, a solution is compared
with the truth of its interval (constant within it for solint 8 and 4).

**G1. Gains recovered on simulated truth, per round.** Three tiers.

- **T0, noiseless twin, perfect model** (library solve of DATA against
  `MODEL_TRUE`, solint 8, on the `--noiseless` twins of `c5pa` and
  `c5delay`): Sa products within 1e-5 relative (max); Sp product phases
  within 1e-5 rad (max); Sd delay differences within 1e-4 ns and products
  within 1e-4 relative (max). The applied output equals `MODEL_TRUE` within
  1e-5 relative (median of `|C − M| / |M|` over cells with `|M|` above 1 %
  of its maximum) and 1e-4 (max). Basis: C2a's class T (1e-5) for a solve
  whose stop criterion is 1e-7; the delay kernel's parameters converge
  more slowly, hence 1e-4.
- **T1, noisy, perfect model** (Sa, solint 8, against `MODEL_TRUE` on
  `c5pa` and `c5pa-held`). The predicted error per product: with
  `A_p = Σ |M_pq|² |g_q|²` over the interval's rows of antenna p, its
  channels and one hand, each part of `δg_p` has variance σ²/A_p, so
  `s_pq² = σ² (1/A_p + 1/A_q)` per part of `δP_pq` (|g| ≈ 1). For
  `r = |ΔP_pq| / s_pq`, Rayleigh gives median 1.18 and p95 2.45. Gate:
  median r ≤ 1.5 and p95 r ≤ 3.5.
- **T2, the self-calibration loop** (the `selfcal` stage with gemclean's
  models), on L-pa and L-delay, development and held-out cases alike. The
  limits allow for an incomplete CLEAN model (Högbom, no multiscale, a
  first model from uncorrected data); thermal noise alone gives about 0.03°
  and 0.05 % per product here (T1's s with |M| about 0.5 Jy).

  | Loop, round | Quantity | median | p95 |
  | --- | --- | --- | --- |
  | L-pa round 1 (Sp) | `|Δ arg P|` | ≤ 1.0° | ≤ 3.0° |
  | L-pa round 2 (Sa) | `|Δ arg P|` | ≤ 0.5° | ≤ 1.5° |
  | L-pa round 2 (Sa) | `| |P| / |P_true| − 1 |` | ≤ 1.0 % | ≤ 3.0 % |
  | L-pa round 2 (Sa) | that median against the uncorrected `| |P_true| − 1 |` median | ≤ 0.25 × | – |
  | L-delay round 1 (Sd) | `|Δ(τ_p − τ_q)|` | ≤ 0.02 ns | ≤ 0.06 ns |
  | L-delay round 2 (Sd) | `|Δ(τ_p − τ_q)|` | ≤ 0.01 ns | ≤ 0.03 ns |
  | L-delay rounds 1, 2 | `|Δ arg P|` per channel | ≤ 1.0° | ≤ 3.0° |

  Reported, not gated: round 1's amplitude error (Sp leaves it), the image
  noise and peak per round, flagged solutions, iterations and converged
  fractions, and L-solint against truth.

**G2. Each round's solve agrees with QuartiCal's on the same MODEL_DATA,
class B, gauge-free.** For every round of every loop (L-pa, L-delay,
L-solint; development and held out): products relative `|ΔP| / |P_qc|`
median ≤ 7e-4 and p95 ≤ 3e-3 (C2a's class B); for Sd also `|Δ(τ_p − τ_q)|`
median ≤ 0.01 ns and p95 ≤ 0.03 ns (C1's K class B). Precondition: rang's
library re-solve on the oracle's copy equals the stage's stored gains bit
for bit. The maximum difference is reported (the kernels are QuartiCal's
ports, so near class A, 1e-6, is expected but not gated).

**G3. The Fslope option recovers delays on a truth with residual delays.**
L-delay's T2 rows above, on `c5delay` and `c5delay-held`, and T0's Sd row.

**G4. Solution intervals are honoured.** For every round of every loop:
- per scan the store holds `ceil(n_int / N)` time bins for N integrations
  (one for `inf`, `n_int` for `int`), and for `Ns` exactly the bins of
  `rang.cal_gain.solint_bins` on the field's rows; `gain_time` is the mean
  of each bin's integration times; `ceil(nchan / freqint)` frequency bins
  with `gain_freq` the mean of each chunk's frequencies;
- for N-integration rounds QuartiCal's `gain_time` per chunk equals rang's
  (count, and values within 1e-6 s);
- the final output column equals `S_p^-1 V S_q^-H` recomputed in NumPy from
  the stored gains on each row's bin, for every target row: median relative
  difference ≤ 1e-6, max ≤ 1e-5 (float32), and FLAG is set exactly where an
  invalid solution says it must be.
- Unit tests cover `int`, `inf`, N, `Ns` and freqint on a small MS.

**G5. The E2-A configuration validates for its selfcal part.**
`core_config.refusals(e2a, ["selfcal"])` (tests/data/w2/e2a.yaml) holds no
refusal whose path starts with `selfcal` and none naming C5a or C5b; what
remains comes from the `image` keys the stage's imaging uses (G4's
`auto_mask`).

**G6. A held-out case, frozen before it runs.** `c5pa-held` and
`c5delay-held` (section 3), run once with the frozen settings; G1 (T1, T2),
G2, G3 and G4 apply to them as to the development cases.

## 5. Procedure

1. Implement the stage; unit tests; check-all.
2. Generate the four cases and the two noiseless twins under
   `/mnt/d/rang/outputs/c5-<date>-NN` (each with a `.code/` snapshot).
   Loops may run before this note's gates are applied, to check that they
   execute; nothing is compared with truth or QuartiCal before the commit
   of this protocol.
3. Development cases: G1, G2, G4; then the held-out cases, once.
4. Anything changed after a result is labelled post hoc and rerun on the
   held-out cases.

## 6. Results

Run directory `/mnt/d/rang/outputs/c5-20261108-02` (`.code/` holds the
code and diffs of each step; `/mnt/d/rang/outputs/c5-20261108-01` was the
execution probe, compared with nothing). Commands are in
`examples/check_c5.py`'s docstring; each writes `<step>.json` there.

### 6.1 T0, noiseless twins, perfect model

| Run | Sa products, max rel | Sp phase, max | Sd delays, max | Sd products, max | Apply, median / max | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| frozen (`t0-frozen-fft-estimate.json`) | 1.3e-7 | 1.3e-7 rad | **1.6 ns median, 30 ns max** | 2.0 | Sd fails | **Sd fails** |
| post hoc, Sd from zero delay (`t0.json`) | 1.3e-7 | 1.3e-7 rad | 7.2e-8 ns | 2.6e-7 | 2.2e-8 / 2.1e-7 (Sa), 4.9e-8 / 3.1e-7 (Sd) | pass |

The frozen Sd solve used the K term's FFT initial estimate, which on this
structured sky model picks the wrong peak on 59 % of antenna intervals
(a per-bin rerun gave the same, so it is the estimator and not a coupling
of bins; `.code/c5_dbg3.py`). QuartiCal 0.2.7's `initial_estimate`
defaults to false (`config/gain_schema.yaml`, line 100), so its
`delay_and_offset` starts from zero delay, and the post-hoc change takes
that start; G2's agreement to 1e-16 with no estimate on either side
supports it. That CubiCal's `f-slope` also starts from zero is assumed, not
read (section 10).
Two intermediate reruns (`t0-posthoc1-*.json`, `t0-posthoc2-*.json`)
reused twins whose FLAG the frozen run's apply had written into, so they
are discarded; the final row is on regenerated twins.

### 6.2 T1, noisy, perfect model (Sa, solint 8)

| Case | products | r median (Rayleigh 1.18) | r p95 (2.45) | s per product | Verdict |
| --- | --- | --- | --- | --- | --- |
| c5pa | 13,888 | 1.178 | 2.425 | 5.2e-4 (0.029°) | pass |
| c5pa-held | 13,888 | 1.178 | 2.461 | 4.8e-4 | pass |

The solve reaches the Cramér-Rao bound of the noise.

### 6.3 T2, the loop (gauge-free products against truth)

Medians / p95 of `|Δ arg P|`, `||P|/|P_true| − 1|` (the uncorrected
amplitude error's median in brackets) and `|Δ(τ_p − τ_q)|`:

| Case, round | Phase (°) | Amplitude | Delay (ns) | Frozen gate |
| --- | --- | --- | --- | --- |
| c5pa r1 Sp | 2.46 / 16.6 | (0.052) | – | fail (1.0 / 3.0) |
| c5pa r2 Sa | 1.88 / 13.6 | 0.0105 / 0.040 | – | fail; amplitude ratio 0.20 pass |
| c5pa-held r1 Sp | 2.26 / 14.9 | (0.061) | – | fail |
| c5pa-held r2 Sa | 1.88 / 12.9 | 0.0145 / 0.028 | – | fail (amplitude p95 passes, median not); ratio 0.24 pass |
| c5delay r1 Sd | 2.19 / 16.9 | – | 0.020 / 0.131 | fail |
| c5delay r2 Sd | 1.55 / 13.1 | – | 0.0061 / 0.079 | fail (delay median passes) |
| c5delay-held r1 Sd | 1.95 / 15.7 | – | 0.018 / 0.130 | fail |
| c5delay-held r2 Sd | 1.05 / 9.96 | – | 0.0074 / 0.070 | fail (delay median passes) |
| c5pa L-solint r1 Sp (4, freqint 16) | 2.49 / 16.8 | – | – | reported |
| c5pa L-solint r2 Sa (64s) | 1.93 / 14.4 | 0.011 / 0.041 | – | reported |

Round 2 is better than round 1 everywhere, and Sa removes 76-80 % of the
amplitude error. Per antenna (c5pa round 2) the median phase error is
0.1-1.7° on 21 of the 32 antennas and 3-14° on antennas 22-31.

### 6.4 G2, QuartiCal 0.2.7 on the same MODEL_DATA

Every N-integration round of every loop, development and held out
(`qc-*.json`): rang's re-solve on the oracle's copy equals the stage's
stored gains bit for bit; products differ from QuartiCal's by at most
1.0e-15 relative for Sp and Sa and 1.6e-7 for Sd (round 2), delays by at
most 4.9e-8 ns; QuartiCal's gain times equal rang's per chunk. L-solint's
round 2 (64s, CASA's bins) has no QuartiCal form and was not compared.
QuartiCal took 28-71 s per solve (single-threaded, Numba start-up
included).

### 6.5 G4, intervals and apply

Every round of every loop: the bins per scan (2 for solint 8, 4 for 4,
2 for 64s on these 16-integration scans), `gain_time`, the 4 frequency bins
of freqint 16 and `gain_freq` equal the frozen rule; the final output column
equals `S_p^-1 V S_q^-H` recomputed in NumPy within 2.2e-8 median and 6.0e-8
max relative over 14.2 M cells, and FLAG is exactly as the solutions imply
(no solution was flagged or clipped in any loop). Unit tests cover `int`,
`inf`, N, seconds, freqint, chunking (bit-identical) and the gain clip
(`tests/test_c5_selfcal.py`).

### 6.6 G5, E2-A

`core_config.refusals(e2a, ["selfcal"])` is `[image.auto_mask (G4)]`: the
selfcal part validates; its imaging waits for G4's masks, as `image` does.
Its terms `{Sp, solint: 120}`, `{Sa, solint: 120}` are 120 integrations,
CARACal's `gsols_timeslots: [120]`.

## 7. Why T2 fails: the model, not the solve (post-hoc diagnostics)

Each item was run after the frozen results, on development data only, and
is labelled post hoc; none changes the shipped settings.

- **The solve and apply are right.** T1 is at the noise bound and G2 equals
  QuartiCal to rounding, on the same MODEL_DATA.
- **The loop's model is wrong on long baselines.** In `pa-c5pa` after round
  2, MODEL_DATA against `MODEL_TRUE` (rms `|ΔM|` / rms `|M|`, XX) grows with
  baseline (`.code/c5_diag2.py`): 5.7 % below 500 m, 4.5 % at 0.5-1 km, 9.7 % at 1-2 km, 16 % at
  2-4 km, 22 % at 4-6 km and 28 % beyond 6 km. Antennas 22-31 have the most
  long baselines, which is where the solutions go wrong.
- **The imager alone is not the cause.** gemclean with the same arguments
  on `MODEL_TRUE` itself (noiseless, uncorrupted; `diag-imager/`,
  `.code/c5_diag3.py`) predicts
  the sky to 1.2, 0.2, 0.1, 0.1, 0.7 and 3.4 % in the same bins.
- **Pixel size is not the cause.** 1asec pixels on a 4096 image
  (`loop-pa-fine-c5pa.json`) give the same errors (round 2: 1.89° / 13.7°).
- **A model from uncorrupted data fixes it.** The same noisy DATA
  corrected by the true gains, imaged with the frozen arguments and
  predicted (`diag-imager/truecorr*`, `.code/c5_diag4.py`, `c5_diag5.py`),
  then Sa solved on the corrupted DATA against that model: phase 0.028° /
  0.082°, amplitude 0.089 % / 0.29 % (median / p95;
  `diag-truecorr-model.json`). Thermal noise and an unmasked 3σ CLEAN on
  this sky are therefore not the limit; the corruption in the imaged data
  is.
- **More rounds and a shallower CLEAN help a little.** Four rounds (Sp, Sp,
  Sa, Sa; `loop-pa4-c5pa.json`): phase p95 16.6, 13.7, 12.3, 11.7°;
  amplitude median 0.8 % after round 4. `auto_threshold: 10`
  (`loop-pashallow-c5pa.json`): round 2 at 1.87° / 12.8°, amplitude
  0.78 % / 3.3 %.

So a model CLEANed deeply, without a mask, from data with ±30° phase and
±10 % amplitude errors, absorbs part of those errors on the long baselines,
and later rounds converge slowly towards the truth from there. This is the
known failure that CARACal's per-round clean masks and cut-offs
(`cleanmask_thr: [10, 6]`, `clean_cutoff`) guard against. Masks are task G4,
and per-round image settings are not in the schema (section 1). The frozen
limits were set for a model good to about 1 % on every baseline, which this
loop does not give. **The gate stays failed and is not reworded.**

## 8. Gates against the frozen protocol

| Gate | Result |
| --- | --- |
| G1 T0 | **met after a post-hoc change** (Sd from zero delay; the frozen FFT start failed) |
| G1 T1 | met, development and held out |
| G1 T2 | **not met**, development and held out (section 6.3) |
| G2 QuartiCal class B | met, every compared round, development and held out (max 1.6e-7) |
| G3 Fslope recovers delays | T0 met (post hoc); T2 **not met** (delay medians pass, p95 0.07-0.13 ns against 0.03-0.06) |
| G4 intervals honoured | met |
| G5 E2-A validates for selfcal | met |
| G6 held out | run once with the frozen settings: same verdicts as development |

Code changes after a frozen result: only Sd's zero start (`rang.cal_selfcal`,
`initial_estimate=False`, as QuartiCal's default and CubiCal), applied
before the held-out runs; a quartical-store attribute renamed
(`rang_selfcal_type`, a check-all registry finding, no effect on results).

## 9. Owner decisions (open)

1. **The T2 failure.** Accept the loop as a working port with the stated
   model-absorption limit, with E1/E2 judging on real images; or require
   masks (G4) and per-round image settings (CARACal's `cleanmask_thr`,
   `clean_cutoff`, `img_*` lists) in selfcal before C5 is called done.
   Proposed: the first now, and a C5b task after G4 for per-round masks, with
   T2 re-run on the held-out cases.
2. **Sd's start.** Zero delay (provisional, as QuartiCal's default;
   CubiCal assumed) instead of the owner's K estimator (FFT, then Gauss-Newton; C1
   decision 3 is about K, not Sd). The FFT start failed on a sky model.
3. **Sd's per-channel flags.** QuartiCal's `finalize_gain_flags` (a gain
   whose update trend rises) flags channels; on clean data it flagged none,
   on a twin whose FLAG the frozen run had partly written it flagged 17 % of
   the channel gains (54 % of antenna intervals had one). Kept as
   QuartiCal's (provisional).
4. **Flags accumulate over rounds** (each round ORs its invalid-solution
   flags; provisional). A diagonal term's invalid antenna flags all four
   correlations (`apply_jones`'s general-Jones rule), not CASA's
   per-receptor rule.
5. **No CASA table** for selfcal solutions, only QuartiCal stores
   (C1 proposed `G Jones`, and `K` + `G` for Sd).
6. `complex` selfcal terms and `refant: auto` in selfcal are refused.

## 10. Not checked

- CubiCal itself (no image); `f-slope` taken as `delay_and_offset`, and
  its zero start assumed.
- Real data: E2-A's selfcal was validated, not run (it waits for G4).
- Several fields in `image.fields`, `data.scans` with selfcal, the
  `CORRECTED_1GC` copy after a real apply (unit-tested only),
  `minuvw_m > 0`, `data.weights: uniform`, `channels_out > 1` models.
- Chunking within a memory limit on the loop (bit-identity is unit-tested
  on a small MS only).
- Timing claims: none.

## For the coordinator

Proposed `research/README.md` row:

> C5, 2026-11-08 (implemented and measured; [c5-selfcal.md](c5-selfcal.md)). `rang-core selfcal` runs CARACal's rounds (image, MODEL_DATA, one Sp, Sa or Sd term per round, apply, final image) through `rang.cal_selfcal`. Each round's solve equals QuartiCal 0.2.7's on the same MODEL_DATA to 1e-15 (delays 5e-8 ns), is at the noise bound on a perfect model, and honours its intervals; E2-A's selfcal part validates. Against simulated truth the full loop fails its frozen limits on development and held-out cases (p95 10-17° on the outer antennas), because the unmasked CLEAN model absorbs gain errors on long baselines; masks (G4) and per-round image settings are the proposed follow-up. Sd starts at zero delay (post hoc). No novelty claim.

Proposed finish-plan C5 row: "Partly done 2026-11-08 ([c5-selfcal.md](c5-selfcal.md)): Sp, Sa, Sd in `rang-core selfcal`; QuartiCal, intervals, E2-A met; truth recovery in the full loop not met (model absorption without masks); C5b after G4: per-round masks and image settings, T2 re-run on c5pa-held and c5delay-held."

STATE.md: C5 as above; seeds 20261301-04, 11-14, 21-24, 31-34 registered in `rang.simtruth.SEEDS`.
