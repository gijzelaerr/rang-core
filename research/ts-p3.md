# TS-P3: unit weights, a control-referenced bias gate, and a run arm

Issue #9 (gijzelaerr/rang-core), time series; follow-up of
[ts-p2.md](ts-p2.md) on the coordinator's brief of 2026-11-23. Branch
`ts-p3`. Written 2026-11-23.

**Status 2026-11-23: implemented and measured (section 9).** As frozen,
**(a) met**, **(b) met** for both weightings, **(c) met**. With unit weights
the uncontrolled bias at the positions falls from up to 0.90 to at most 0.16
σ_meas (reported, not gated).

**Status at freeze: proposed. Nothing in this note is built or measured.** It
is committed before any code that tests it. Later changes are dated
amendments in section 8, labelled post hoc when they could have seen a result.

## 0. Starting point (coordinator rulings, 2026-11-23)

- P2 merged (`2b9d1235`). Parity with WSClean and the DFT meets the v0.5.0
  gate; E2-A's scan 10 is development data; the real-track bias gates of
  ts-p2 (T3a, D3) stay **not met as frozen**. Nothing in ts-p2.md is edited.
- Seen before this note, post hoc in ts-p2 10.3: on the real track the
  injected run minus the uninjected run matched the injections to 1e-8 σ, and
  with every weight set to one the control's means at the positions fell from
  up to 1.06 mJy to at most 0.20 mJy. Both readings used seed `tsp2-real`;
  this note's real-track gates use a fresh seed, `tsp2-real2`.

## 1. Questions and claims

- **(a) Weights.** `rang-core lightcurve --weights unit|ms` (default `ms`,
  unchanged). `unit` is gemclean's `-unit-weights`: every correlation weighs
  1, FLAG and FLAG_ROW still applied, so the Stokes I weight is 4 where
  neither hand is flagged and 0 otherwise. Claim: parity with WSClean 3.7 on
  the same data with WEIGHT_SPECTRUM set to 1 (the oracle for unit weights),
  and with the NumPy DFT; the default's outputs unchanged.
- **(b) A control-referenced bias gate.** On the real track, the residual's
  own time-mean at a position is not the product's error (ts-p2 10.3). The
  gate measures recovery of the injected signal against the uninjected
  control: R = flux(injected) − flux(control) − expected. With the noise and
  the residual sky cancelled exactly, this is an exactness test of injection,
  DFT and grouping on real UVW, weights and flags, so its bound is a parity
  bound. Claim: |mean R| and max |R| within the bounds of section 4, both
  weightings.
- **(c) A `rang-core run` arm with `--channels-out`.** The ts-p1 4.2 arm
  (GeMClean's deep model as MODEL_DATA) extended to spectra: `rang-core run`
  with stage `image` (`channels_out 4`, joined, `fit_spectral_pol 2`,
  `write_model`) on a copy of `tsp2-dev`, then `rang-core lightcurve
  --channels-out 16`. Claim: parity of the product on that residual (gated);
  the bias against truth is reported, with the expected absorption named now.

No claim is a gain: this is parity and a better-posed gate.

## 2. Data

- **Real track.** `D:\rang\outputs\p1-lightcurves-20261123\scan10-512.ms`
  (ts-p2 4.2: E2-A's replayed residual, 512 channels, MODEL_DATA from E2-A's
  final model). New columns INJECTED2_DATA = DATA + the `tsp2-real2`
  injections, and RESIDUAL2_DATA = INJECTED2_DATA − MODEL_DATA (complex64,
  WSClean only). Layout and spectra by ts-p2 4.2's rule with seed
  `tsp2-real2` (20262331-37); the flux unit u is again the median σ_meas of
  intervals 0-9 of the uninjected residual **with MS weights** (1.748 mJy,
  read in ts-p2), so the amplitudes are comparable with ts-p2's.
- **WSClean's unit-weight copy.** An ext4 copy of `scan10-512.ms` whose
  WEIGHT_SPECTRUM is set to 1 in every cell (FLAG and FLAG_ROW unchanged),
  written with python-casacore in `rang-o-casa:6.7.6.14`.
- **Run arm.** `tsp2-dev` regenerated from its seeds (ts-p2 4.1; development
  data, already read), a copy for the run.

## 3. Runs

| Run | Data | Weights | Settings |
| --- | --- | --- | --- |
| R-ctl-ms, R-ctl-unit | DATA − MODEL_DATA | ms, unit | 2048² at 2″, `--channels-out 16`, `--candidates 5` |
| R-inj-ms, R-inj-unit | INJECTED2_DATA − MODEL_DATA | ms, unit | as above; R-inj-unit with `--fits` |
| W-unit-T1 | RESIDUAL2_DATA, unit copy | WEIGHT_SPECTRUM = 1 | WSClean `-intervals-out 450`, 2048² at 2″ |
| W-unit-D2 | as W-unit-T1 | as W-unit-T1 | WSClean `-intervals-out 450 -channels-out 16`, 1024² at 2″ |
| A-run | copy of `tsp2-dev` | ms | `rang-core run`, stage image (section 1c), then lightcurve 1024² at 2″, `--channels-out 16` |

## 4. Gates and frozen tolerances

σ: σ_meas (median over intervals, per run) for band values, σ_dyn,g
(1.4826 × MAD over the intervals of the control F's group-g DFT in the
matching control run) for cells; on the run arm, the truth's σ_snap,k and
σ_k,g.

**(a) Unit weights, on R-inj-unit:**

| ID | Quantity | Oracle | Bound |
| --- | --- | --- | --- |
| U1 | snapshot, every interval | W-unit-T1 | L∞ ≤ 1e-5 × max \|WSClean\| |
| U2a | DFT band flux | NumPy DFT with unit weights | ≤ 1e-3 σ_meas per point |
| U2b | snapshot pixel (pixel centres) | the DFT | ≤ 1e-3 σ_meas |
| U2c | DFT band flux | W-unit-T1 pixel by WCS | ≤ 1e-3 σ_meas |
| U3 | DFT cell | NumPy DFT per group | ≤ 1e-3 σ_dyn |
| U4 | DFT cell | W-unit-D2 pixel by WCS | ≤ 1e-3 σ_dyn |
| U5 | default unchanged | `--weights ms` and no option | `lightcurve.csv` and `dynspec.csv` byte-identical (a test, and on R-inj-ms against ts-p2's code path) |

**(b) Control-referenced bias, on R-inj-* against R-ctl-* of the same
weighting** (sources A-E; F reported):

| ID | Quantity | Bound |
| --- | --- | --- |
| C1 | per source, \|mean_k R_band\| / σ_meas | ≤ 1e-3 |
| C2 | per source, max_k \|R_band\| / σ_meas | ≤ 1e-3 |
| C3 | per source, \|mean_{k,g} R_cell\| / σ_dyn,g | ≤ 1e-3 |
| C4 | max \|R_cell\| / σ_dyn,g | ≤ 1e-3 |
| C5 | T3d (ts-p1) on R-inj-*, σ_meas of that run | as frozen in ts-p1 |

Also reported, not gated, for both weightings: the uncontrolled T3a and D3
of ts-p2 (flux − expected), χ², σ_meas, the control's means at the
positions, and the T4 candidate counts of R-ctl-*.

**(c) Run arm, on A-run** (gated: parity only):

| ID | Quantity | Bound |
| --- | --- | --- |
| A1 | DFT cell against NumPy on the run's residual | ≤ 1e-3 σ_k,g |
| A2 | group-weighted mean against the band DFT (D4) | ≤ 1e-6 σ_snap,k |
| A3 | T3d on the band light curve | as frozen in ts-p1 |

Reported: bias and χ² against truth per source and per cell. **Named now:**
the deep model absorbs each source's time-mean, so E (a variable with mean
10σ) and D (periodic) are expected biased low by about their means, in every
group and with the spectral shape of their mean; pulses (A, B, C) little.

## 5. Decision rule

- (a) **met** when U1-U5 pass; (b) **met** when C1-C5 pass for both
  weightings; (c) **met** when A1-A3 pass. Each is reported gate by gate;
  a failure is recorded with its numbers and not retuned.
- A code fix after a reading needs a dated amendment and fresh data: seed
  `tsp2-real3` for the real track; for the run arm, `tsp2-held` is spent, so
  a new simulation seed.
- If U1, U2c or U4 fail because WSClean's unit-weight reading differs (for
  example in cells with zero weight), that is **not met (oracle mismatch)**
  with the measured difference.

## 6. Order, bookings, disk

1. This note. 2. Code and tests (`--weights`, scorer support, injection into
named columns, seed `tsp2-real2`), quick check, commit = code freeze.
3. Inject `tsp2-real2`. 4. R-ctl-*, R-inj-* (4 slots each). 5. The unit copy
on ext4, W-unit-T1 and W-unit-D2 (`-j 8`, 8 slots). 6. Score (a), (b).
7. A-run (GeMClean 8 slots). 8. Delete the run root and the WSL scratch.

D: has about 818 GB free; the two new columns add about 28 GB to the 66 GB
run root, the ext4 copy about 90 GB on WSL's disk. Timings go into
[tool-timings.md](tool-timings.md) as shared-host figures.

## 7. For the coordinator, at freeze

- (b)'s gate is an exactness gate by construction (noise cancels); the
  science reading of the residual floor stays in the reported uncontrolled
  numbers.
- (c) is read as the ts-p1 4.2 arm with spectral imaging, not a new pipeline
  stage; a `lightcurve` stage inside `rang-core run` is not proposed here.

## 8. Amendments

(none)

## 9. Measured result

Run root `D:\rang\outputs\p1-lightcurves-20261123` (host glacier, shared
slots). Code freeze `d12123c9` (quick check PASS).

### 9.1 (c) The run arm (A-run)

- `tsp2-dev` regenerated from its seeds (92 s). `rang-core run
  tools/oracles/ts-p3/run-arm.yaml`: rc 0, 128 s (GeMClean 89 s, 8 threads):
  4 joined output channels, 2-term spectral fit, Briggs 0, 2048² at 2″; it
  stopped on the component limit (100,000 components, 7 major cycles,
  final peak 3.8e-5 Jy against the 3σ threshold 1.5e-5 Jy), not on the
  threshold. Then `rang-core lightcurve --size 1024 --scale 2asec
  --channels-out 16`: 59 s.
- Scorer: [results/ts-p3/score_run_arm.py](results/ts-p3/score_run_arm.py),
  [results/ts-p3/score-run-arm.json](results/ts-p3/score-run-arm.json).

| Gate | Reading | Bound | Outcome |
| --- | --- | --- | --- |
| A1 | 2.7e-12 σ_k,g against NumPy on the run's residual | 1e-3 | **met** |
| A2 | 9.9e-15 σ_snap | 1e-6 | **met** |
| A3 | 7 of 7 pulses; lowest S/N 5.0 (C) | ts-p1 T3d | **met** |

**(c) met.** Reported (named in 4): per-cell bias against truth A −0.12,
B −0.15, C −0.05, **D +0.48**, **E −1.61**, F −0.03 σ_k,g; χ² 1.03-1.28
except E 4.14. E's deep-model absorption appears as predicted (E's mean of
10σ_snap is about 2.5 σ_k,g per cell; −1.61 of it remains). D's positive
bias was not predicted; a CLEAN residual or a model component near D is
likely; unverified. σ_meas is 1.22 × σ_snap (the deep model's errors in the
snapshots). Group 15 (all flagged) is null throughout.

### 9.2 Injection `tsp2-real2`

INJECTED2_DATA and RESIDUAL2_DATA written into `scan10-512.ms`; u = 1.748 mJy
(as ts-p2, MS weights). Pixels A (−40, 81), B (214, 165), C (444, 73),
D (−123, −240), E (−168, −318), F (27, −178); redraws by the 30″ rule A 3,
C 2, D 1, F 1. Truth in
[results/ts-p3/tsp2-real2.truth.json](results/ts-p3/tsp2-real2.truth.json).
Four lightcurve runs (2048² at 2″, `--channels-out 16`, `--candidates 5`,
4 slots each, concurrent): R-ctl-ms, R-ctl-unit, R-inj-ms 464 s, R-inj-unit
346 s (`--fits`).

### 9.3 (b) Control-referenced bias, MS weights

[results/ts-p3/score3-ms.json](results/ts-p3/score3-ms.json), σ_meas
1.318 mJy (median).

| Gate | Reading (worst of A-E) | Bound | Outcome |
| --- | --- | --- | --- |
| C1 | 8.7e-9 σ_meas | 1e-3 | **met** |
| C2 | 5.5e-7 σ_meas | 1e-3 | **met** |
| C3 | 5.6e-9 σ_dyn | 1e-3 | **met** |
| C4 | 2.9e-6 σ_dyn | 1e-3 | **met** |
| C5 | 7 of 7 pulses; lowest S/N 6.8 | ts-p1 T3d | **met** |

Also met on this run (the ts-p2 parity gates, reported): band DFT against
NumPy 1.8e-12 σ_meas, snapshot pixel against the DFT 1.4e-6 σ_meas, cells
against NumPy 7.7e-12 σ_dyn. Reported, uncontrolled (ts-p2's T3a and D3 on a
fresh layout): band bias A −0.52, B +0.00, C +0.27, D +0.42, E −0.90,
F +0.12 σ_meas; cell bias −0.18 to +0.10 σ_dyn. As in ts-p2, the residual's
own mean at the positions is at the 0.1-1 σ_meas level with MS weights.

### 9.4 (a) Unit weights

WSClean 3.7 on the ext4 copy with WEIGHT_SPECTRUM = 1 (`unit_copy.sh`, 660 s
copy over 9p and 32 s rewrite): `-intervals-out 450` 2048² at 2″ in 265 s
(298 MB), and `-channels-out 16` 1024² at 2″ in 764 s (110 MB), both
`-j 8`. Scores in [results/ts-p3/score3-unit.json](results/ts-p3/score3-unit.json).

| Gate | Reading | Bound | Outcome |
| --- | --- | --- | --- |
| U1 | 3.3e-7 of the snapshot peak (median 8.3e-8; worst interval 124) | 1e-5 | **met** |
| U2a | 1.9e-12 σ_meas | 1e-3 | **met** |
| U2b | 2.8e-6 σ_meas | 1e-3 | **met** |
| U2c | 1.8e-6 σ_meas; WCS pixel = rang's at all six | 1e-3 | **met** |
| U3 | 6.3e-12 σ_dyn | 1e-3 | **met** |
| U4 | 3.2e-6 σ_dyn; CRVAL3 offset 0 Hz | 1e-3 | **met** |
| U5 | the test (`--weights ms` = no option, both CSVs byte-identical; unit differs and scores); on real data R-ctl-ms's `candidates.csv` is byte-identical to ts-p2's merged-code control run (SHA-256 `fd1842b1…`) and its σ_meas equal in all 450 intervals | equal | **met** |

U5 departs from 4's wording ("on R-inj-ms against ts-p2's code path"): the
injected columns differ from ts-p2's, so the uninjected control, whose
candidates and σ_meas do not depend on the positions, is the comparison.

### 9.5 (b) Control-referenced bias, unit weights

σ_meas 0.953 mJy (median; 1.318 with MS weights).

| Gate | Reading (worst of A-E) | Bound | Outcome |
| --- | --- | --- | --- |
| C1 | 1.6e-8 σ_meas | 1e-3 | **met** |
| C2 | 7.3e-7 σ_meas | 1e-3 | **met** |
| C3 | 4.5e-9 σ_dyn | 1e-3 | **met** |
| C4 | 2.5e-6 σ_dyn | 1e-3 | **met** |
| C5 | 7 of 7 pulses; lowest S/N 10.3 (6.8 with MS weights) | ts-p1 T3d | **met** |

**Reported (not gated), uncontrolled on the same layout:**

| | MS weights | unit weights |
| --- | --- | --- |
| σ_meas (median) | 1.318 mJy | 0.953 mJy |
| control mean at A-F | −0.69, +0.01, +0.35, +0.56, −1.19, +0.16 mJy | +0.11, +0.10, −0.06, −0.15, +0.01, −0.13 mJy |
| band bias A-E (σ_meas), ts-p2's T3a bound 0.141 | −0.52, +0.00, +0.27, +0.42, −0.90 | +0.11, +0.11, −0.06, −0.16, +0.01 |
| cell bias A-E (σ_dyn), D3 bound 0.035 | −0.18 to +0.10 | −0.16 to +0.09 |
| T4 control, ≥ 5σ / ≥ 7σ, positive (negative) | 14,220 (272) / 1,914 (8) | 3,144 (4,661) / 558 (764) |

With unit weights the band bias at A-E would pass ts-p2's 0.141 bound at
four of five positions (D at −0.16 would not); the cell bias would still fail
D3 at A, B and E. The candidate excess flips sign: positive with MS weights,
negative with unit weights. This is seen once, on one layout, after ts-p2;
it is a reading, not a gate.

### 9.6 Outcome (section 5, as frozen)

| Part | Verdict | Key numbers |
| --- | --- | --- |
| (a) `--weights unit` | **met** | WSClean 3.3e-7 of the peak, pixels 1.8e-6 / 3.2e-6 σ, DFT ≤ 6.3e-12 σ; default unchanged |
| (b) control-referenced bias | **met** (MS and unit) | worst ≤ 1.6e-8 σ (means), ≤ 2.9e-6 σ (any cell); 7/7 pulses both |
| (c) run arm | **met** | parity 2.7e-12 σ, 7/7 pulses; E absorbed (−1.61 σ per cell) as named |

## 10. For the coordinator

- **(b) is an exactness gate by construction** (noise and residual sky
  cancel); its pass shows the product recovers injected signals exactly on
  real UVW, weights and flags, not that the residual is clean.
- **Weights.** Unit weights cut σ_meas by 28 % and the residual offsets at
  the positions from up to 1.2 mJy to at most 0.15 mJy on this field, where
  E2-A's model was made with `-unit-weights`. Making `unit` the default, or
  following the imaging stage's weights automatically, is a product
  decision (it would change P1/P2 outputs; a new protocol). Not done.
- **Run arm.** GeMClean stopped on the 100,000-component limit, not the
  threshold; D's +0.48σ per-cell bias is unexplained (unverified).
- **Checks.** Quick check PASS on the code freeze and after; the full check
  and `wheels` are left to the merge check.
- **Cleanup.** The run root `D:\rang\outputs\p1-lightcurves-20261123` and
  the WSL scratch `~/Build/tmp/20261123-ts-p3` are deleted after scoring; the
  compact archive is [results/ts-p3/](results/ts-p3/).
