# TS-P3: unit weights, a control-referenced bias gate, and a run arm

Issue #9 (gijzelaerr/rang-core), time series; follow-up of
[ts-p2.md](ts-p2.md) on the coordinator's brief of 2026-11-23. Branch
`ts-p3`. Written 2026-11-23.

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

(none yet)
