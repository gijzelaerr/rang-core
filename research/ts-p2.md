# TS-P2: dynamic spectra, and the P1/P2 real track on E2-A's field

Issue #9 (gijzelaerr/rang-core), time series. The owner approved P1 on
2026-11-13, with P2 (dynamic spectra) next; the coordinator's brief of
2026-11-23 asks for P1 against WSClean `-intervals-out` and an exact DFT
(the v0.5.0 gate in [roadmap.md](roadmap.md)), then dynamic spectra, on
simulated transients and one real track. Branch `p1-lightcurves`. Written
2026-11-23.

**Status 2026-11-23: implemented and measured (section 10).** P2 met on the
held-out simulation. Real track (E2-A scan 10, injected transients): parity
with WSClean and the DFT met for P1 and P2, every pulse recovered; the bias
gates T3a and D3 not met (the residual's own mean at the positions).

**Status at freeze: proposed. Nothing in this note is built or measured.** It
is committed before any code that tests it. Later changes are dated
amendments in section 9, labelled post hoc when they could have seen a result.

## 0. What already exists (not redone here)

P1 is built and merged: `rang-core lightcurve` (`python/rang/lightcurve.py`,
Rust kernel `core/src/lightcurve.rs`), measured in [ts-p1.md](ts-p1.md):

- T1, T2a-c, T3a-d met on held-out simulations under the accepted post hoc
  amendments 9.1 (snapshot grid 2048² at 2″) and 9.2 (T3a bound 3/√N σ), with
  WSClean 3.7's FLAG_ROW behaviour a recorded oracle difference (15.3:
  the raw comparison is the verdict, the FLAG_ROW-ignored one is reported).
- T4 met under post hoc amendment 15.2, T5 met at 2000² (13.6), T6 met on
  nash (15.9).
- **Not done:** any real data (ESO137, E2-A's field), T7 (TRON ω Cen, owner
  decision 2), and P2.

This note adds the two missing pieces: **P2** (dynamic spectra) on
simulations, and **one real track** for P1 and P2. The tolerances and
amendments of ts-p1.md carry over unchanged; nothing in ts-p1.md is edited.

## 1. Hypotheses and claim

1. **P2.** `rang-core lightcurve --channels-out M` gives, per interval,
   channel group and position, the exact DFT flux of the Stokes I residual.
   It agrees with an independent NumPy DFT and with WSClean 3.7
   `-intervals-out N -channels-out M` dirty pixels within the frozen bounds
   of section 5, and recovers injected spectral transients without bias.
2. **Real track.** On E2-A's ESO137 target scan (section 4.2) with
   simulated transients injected into its real residual, P1 and P2 keep the
   same parity with WSClean and the DFT, and P1 recovers every injected pulse
   at or above 7σ_meas.

The claim is **parity**, not novelty ([AGENTS.md](../AGENTS.md), Claims): a
first open implementation of residual snapshot light curves and visibility
dynamic spectra in the chain, checked against WSClean and the DFT.

## 2. Product definition: `--channels-out M`

- **Option.** `rang-core lightcurve ... --channels-out M` (default off). M
  must divide the number of channels; otherwise the command refuses. Group g
  holds channels g·K to (g + 1)·K − 1, K = nchan / M, which is WSClean's
  `-channels-out M` grouping when M divides nchan (checked on dev, section 7).
- **Values.** For interval k, group g and position s:
  `S = Σ w Re[I · exp(−2πi (u l + v m + w (n − 1)) ν / c)] / Σ w`, over the
  cells of group g only, float64, natural weights, Stokes I and flags as P1
  (ts-p1.md section 3). A group with no weighted sample gives NaN (`null` in
  JSON, `nan` in CSV).
- **Kernel.** A new Rust function beside `dft_sums` (`core/src/lightcurve.rs`)
  returning per-group numerators and weight sums, in the same fixed row-block
  order. `dft_sums` and every P1 output stay unchanged: with and without
  `--channels-out`, `lightcurve.csv` is identical byte for byte (a test).
- **Outputs.** `dynspec.csv` (interval, time, position, group, first and last
  channel, mean frequency, flux, weight sum, samples) and a `dynspec` block in
  `lightcurve.json`. No per-group snapshot images are made (P2 is DFT only).

## 3. Oracles

- **O-DFT:** an independent float64 NumPy direct sum in the scorer, from the
  scorer's own Stokes I of the same columns, weights, FLAG and FLAG_ROW
  (ts-p1.md's `examples/ts_p1_measure.py` functions, extended per group).
- **O-WSC:** WSClean 3.7 (`rang-wsclean-native:3.7`, Docker on glacier's
  WSL, ext4 copy, no network), `-gridder wgridder -wgridder-accuracy 1e-6
  -no-min-grid-resolution -weight natural -pol I -niter 0 -intervals-out N
  -channels-out M -data-column RESIDUAL_DATA`, at 1024² and 2″ for P2 (size
  only sets the field of view: positions lie within 0.25° of the centre) and
  at 2048² and 2″ for P1's T1 (ts-p1.md 9.1). The pixel at each position is
  found from WSClean's FITS WCS by RA/Dec; positions lie on pixel centres.
- **WSClean output budget.** P2: N × (M + 1) × 1024² × 4 B = 450 × 17 × 4.19 MB
  = 32 GB per set (the M channel images and the MFS image); P1 T1 on the
  real track: 450 × 16.8 MB = 7.5 GB. The `-image.fits` copies are deleted as
  they appear (as ts-p1's script). One set at a time on WSL ext4, deleted
  after scoring.

## 4. Data

### 4.1 Simulations (`examples/ts_p2_sim.py`, built on `ts_p1_sim.py`)

As `tsp1-held2` (ts-p1.md 13.1): 64 antennas, 64 channels over
856-1712 MHz, 450 × 8 s, SIM-TARGET, static sky in DATA and exactly in
MODEL_DATA, CORRECTED_DATA = sky + transients + noise, DATA = CORRECTED_DATA
× 2e^{0.7i}, spectral unequal WEIGHT_SPECTRUM, cell flags (3 % all, 2 % XX,
2 % YY, channel 10 in every row), RESIDUAL_DATA for WSClean only. Changed:

- **FLAG_ROW on 0 % of rows** (tsp1-held2 already measured FLAG_ROW; here
  the raw WSClean comparison is then exact).
- **Channels 60-63 flagged in every row**, so group 15 at M = 16 is empty:
  its values must be NaN/null (gate D5).
- **Positions on pixel centres of the 2″ grid**, l = −dx·2″, m = dy·2″, all
  within 0.25° (|dx|, |dy| ≤ 450).
- **Spectra.** Each source's flux is a(t) × f(ν) with f normalised to a
  band mean of one over the 64 channels; a(t) in σ_snap units as P1:

| Role | Radius | a(t) (dev) | f(ν) |
| --- | --- | --- | --- |
| A | 0.0° | integration 40 at 20σ, 300 at 10σ | power law, α = −1.5 |
| B | 0.15° | integrations 100-101 at 15σ | Gaussian: centre 1.2 GHz, FWHM 200 MHz |
| C | 0.25° | integrations 200-207 at 8σ | 1 + 0.8 sin(2π ν / 150 MHz + 1.0) |
| D | 0.15° | 30 s every 20 min at 25σ, from 403 s | flat |
| E | 0.2° | 10σ (1 + ½ sin(2π t / 600 s)) | power law, α = +1.0 |
| F | 0.1° | none (control) | – |

  Dev pixels: A (0, 0), B (191, −191), C (−318, 318), D (−150, 230),
  E (250, 260), F (−127, 127) in 2″ units.
- **Held-out layout** from the layout seed by ts-p1.md 4.1's rule (radii as
  above; amplitudes 7-50σ for A-D, 5-20σ for E's mean); the spectra keep their
  shapes, with A's α uniform in [−2, 0], B's centre uniform in
  [1.0, 1.5] GHz and C's phase uniform in [0, 2π), from the layout seed.
- **Seeds** (`rang.simtruth.SEEDS`, keys jones (unused), sky, noise, layout,
  rfi (unused), flags, weights): `tsp2-dev` 20262301-07, `tsp2-held`
  20262311-17. `tsp2-held` is generated after the code freeze and read once.
- **σ per cell.** σ_k,g = √(Σ w_I² v) / Σ w_I over the cells of interval k
  and group g actually used (13.1's formula per group), written to the truth.

### 4.2 Real track: E2-A's field, ESO137 ms1 target scan 10

**Why this scan.** It is the gate dataset the issue names. The scope note
([v1-timeseries-scope.md](v1-timeseries-scope.md) section 5) and ts-p1.md 12
held it out because A0 reserved it for E2-A; E2-A has since run and been
scored on it ([e2-acceptance.md](e2-acceptance.md) 9.13, 9.14: verdict as
frozen, a rerun uses the reserve scans 12 and 13). Its visibilities, images
and model have been read by E2-A's chain and oracles, so it is no longer
held-out data for anything; here it is **development data**, and no
held-out claim is made on it. (The coordinator may overrule; see section 8.)
ESO137 scan 2 (the scope note's development scan) has no calibrated product
on disk; the TRON ω Cen set (T7) still needs the SARAO token.

**The residual: E2-A's chain replayed from its archived products**, in this
task's own run root `D:\rang\outputs\p1-lightcurves-20261123` (never in
`e2a-20261115`):

1. Copy `D:\rang\outputs\e2a-20261115\e2a.ms` (its 9.1 state) to
   `e2a-replay.ms`.
2. Restore the flag version `rang_selfcal_20261115T161755Z` (FLAG at the start
   of E2-A's selfcal; E2-A's apply added no flag, `apply/summary.json`).
   **Check:** 10,747,830,624 flagged cells in the MS and 7,843,952,228 in field
   ESO137-001, as E2-A's apply and selfcal summaries record.
3. `rang-core apply` with E2-A's configuration
   (`research/results/e2-acceptance-scripts/e2a-rerun.yaml`) and a run
   directory holding copies of E2-A's `calibrate/` tables K1, G1, B1 and its
   state: CORRECTED_DATA = 1GC.
4. Self-calibration replayed: round 2's store (`selfcal/ESO137-001/round-2/
   gains.qc`, Sa, solint 120) applied to CORRECTED_DATA in place with
   `cal_selfcal.apply`, its rows and bins rebuilt with `cal_selfcal.time_bins`
   (the rebuilt bin times must equal the store's `gain_time` exactly), and
   round 1's invalid-gain flags OR'd as E2-A's round 1 did. **Check:**
   8,082,693,644 flagged cells in field ESO137-001 after the replay (E2-A
   round 2's `cells_flagged_after`).
5. CASA 6.7.6.14 `split` (`rang-o-casa:6.7.6.14`, Docker on WSL), field ESO137-001,
   `datacolumn='corrected'`, `width=8`: 512 channels, as E2-A's imaging
   averaged 8 channels (`image.average_channels: 8`), into `scan10-512.ms`.
6. MODEL_DATA predicted into `scan10-512.ms` by `gemclean -predict` from
   E2-A's final model (`selfcal/ESO137-001/final/image-000[0-7]-model.fits`,
   `-channels-out 8`, 4096² at 3″, as E2-A's final image), so the residual
   is DATA − MODEL_DATA at E2-A's own imaging resolution.
7. Stop rule: if check 2 or 4 fails, the selfcal replay is dropped, the
   residual is 1GC − model, and that is recorded (not a gate failure).

**Injections** (seeds `tsp2-real` 20262321-27, layout key): a column
INJECTED_DATA = DATA + the transients predicted exactly
(`simtruth._predict`, unpolarised points, apparent flux, no primary beam),
with roles A-E and F as section 4.1's held-out rule but radii 0.05°, 0.15°,
0.25°, 0.15°, 0.2° and 0.1°, on pixel centres of the 2048², 2″ grid. A
position angle is redrawn while any pixel of E2-A's final MFS image
(`image-MFS-image.fits`) within 30″ exceeds 10 × that image's robust rms.
The flux unit u is the median σ_meas of intervals 0-9 of the uninjected
residual (read before INJECTED_DATA is written; a number, not a tuning).
Amplitudes 7-50 u for A-D, 5-20 u for E's mean; spectra as 4.1's held-out
rule. The injected truth is written beside the MS.

**Runs.** `rang-core lightcurve` on `scan10-512.ms` with
`--column INJECTED_DATA` and with `--column DATA` (uninjected), both with
`--size 2048 --scale 2asec --channels-out 16 --candidates 5`, positions A-F.
WSClean as section 3 on an ext4 copy whose RESIDUAL_DATA holds
INJECTED_DATA − MODEL_DATA in complex64.

**Pre-registered facts for the reading.** FLAG_ROW rows with unflagged cells
are counted on `scan10-512.ms` before any run; σ_meas is the measured snapshot
rms (data weights are not trusted for σ on MeerKAT, scope note 4).

## 5. Gates and frozen tolerances

σ in a gate is: σ_snap,k (P1) and σ_k,g (P2) on simulations; σ_meas,k (P1)
and σ_dyn,g (P2: 1.4826 × MAD over the 450 intervals of group g's DFT flux at
the control F in the uninjected run) on the real track.

**P1 on the real track** (ts-p1.md's definitions, amendments 9.1, 9.2, 15.3):

| ID | Quantity | Bound |
| --- | --- | --- |
| T1 | rang snapshot against WSClean, every interval, 2048² at 2″ | L∞ ≤ 1e-5 × max \|WSClean\| |
| T2a | DFT flux against O-DFT | \|Δ\| ≤ 1e-3 σ_meas,k |
| T2b | snapshot pixel against the DFT (pixel centres) | \|Δ\| ≤ 1e-3 σ_meas,k |
| T2c | DFT against the WSClean pixel | \|Δ\| ≤ 1e-3 σ_meas,k |
| T3a | injected sources A-E: mean(flux − expected) over 450 intervals; expected = Σ_Y S_Y B_t(X, Y) from the injected truth | ≤ 3/√450 σ_meas (0.141), σ_meas the median over intervals |
| T3c | time stamps | equal to TIME exactly |
| T3d | every injected pulse with peak truth ≥ 7σ_meas | as ts-p1.md T3d |

T3b (χ²) and T4 (candidates at 5σ and 7σ, positive and negative, uninjected
run) are reported, not gated, on real data (scope note T3, T4).

**P2** (on `tsp2-held`, and on the real track with σ_dyn,g):

| ID | Quantity | Bound |
| --- | --- | --- |
| D1 | DFT cell (k, g, s) against O-DFT | \|Δ\| ≤ 1e-3 σ per cell |
| D2 | DFT cell against the WSClean `-channels-out` pixel | \|Δ\| ≤ 1e-3 σ per cell |
| D3 | per source, mean over its cells of (flux − expected)/σ | \|·\| ≤ 3/√(N_cells) |
| D3b | reduced χ² of the same, simulations only | within 1 ± 3√(2/N_cells) |
| D4 | weighted mean over groups (weights Σw) against P1's `flux_jy` | \|Δ\| ≤ 1e-6 σ_snap,k (rounding) |
| D5 | an empty group (all cells flagged) | NaN in CSV, null in JSON, every interval and position |

On the real track D3 applies to the injected sources, and D3b is reported.

## 6. Decision rule (named before any result)

- **P2 met on simulation:** D1-D5 pass on `tsp2-held`, after passing on
  `tsp2-dev`. A dev failure is fixed and rerun on dev (each attempt logged);
  a held-out failure is recorded as not met with the gate and numbers, and a
  fix needs a dated amendment and `tsp2-held2`.
- **Oracle mismatch:** if D2 fails because WSClean's channel grouping or pixel
  convention differs, it is recorded as **not met (oracle mismatch)** with the
  measured difference and the convention, as ts-p1.md 6.
- **P1 met on real data:** T1, T2a-c, T3a, T3c and T3d pass on the real track.
  **P2 met on real data:** D1-D5 (D3 on A-E) pass there. Each is reported gate
  by gate; a failure is not retuned. The real track is development data: a fix
  after it is read gets a new injection seed (`tsp2-real2`), and the first
  reading stays in this note.
- T3b, T4 on real data, cost and T7 are reported or not run, never gated here.

## 7. Order, bookings, cost

1. This note (commit).
2. Code and tests; `python tools/check_all.py --quick`; commit = the code
   freeze, named in section 9.
3. `tsp2-dev`: generate, lightcurve (`--size 1024 --scale 2asec
   --channels-out 16 --no-images`, plus a run with images for D4's P1 side),
   O-DFT, O-WSC; check WSClean's grouping (its FITS `CRVAL3`/`CDELT3`
   against the group's channels).
4. `tsp2-held`, once.
5. The real track (4.2), steps 1-7, then the runs and scoring.

Bookings under `tools/heavy_lock.py` (main checkout), at most 8 slots:
simulation and lightcurve 4 slots, 8 GB; the copy and the replay 2 slots,
8 GB; CASA split 4 slots, 16 GB; gemclean predict 8 slots, 24 GB; WSClean
`-j 8`, 8 slots, 16 GB. Wall times are shared-host figures, recorded in
[tool-timings.md](tool-timings.md), not gated. Disk: the replay MS peaks at
about 330 GB on D: (195 GB copy + 137 GB CORRECTED_DATA), deleted once
`scan10-512.ms` (about 40 GB) exists; stop if D: falls below 200 GB free.

## 8. For the coordinator, at freeze

- **E2-A's field as development data** (4.2): the issue names it as a gate
  dataset; ts-p1.md 12 kept it held out while E2-A was unscored. E2-A has
  since been scored, so this note uses it, and claims no held-out result on
  it. Overrule if the reserve logic should extend to it.
- **The replay** reproduces E2-A's final CORRECTED_DATA from its archived
  tables and the final model, not by rerunning `rang-core run` (9 to 12 h at
  4,096 channels). The flag counts of 4.2 are its checks.

## 9. Amendments

None to the protocol. Code freeze: `f50b063e` (quick check PASS, CI green).
Oracle-script fix during dev (6, "fails on dev"), not a protocol change:
`edb36c96`. WSClean dev attempt 1 stopped at interval 1 because the script
deleted the per-channel `-image.fits` while WSClean still reads them to form
the MFS image; the script now deletes them after the run when M > 1.

## 10. Measured result

Run root `D:\rang\outputs\p1-lightcurves-20261123` (host glacier, shared
slots under the heavy lock). Simulations in `sim/`.

### 10.1 `tsp2-dev` (code `f50b063e`)

- Generated in 93 s (8.5 GB). `rang-core lightcurve --size 1024 --scale 2asec
  --channels-out 16`: 55 s wall (4 slots). WSClean 3.7 `-j 8`: 549 s, peak
  RSS 100 MB (attempt 2).
- **D1** 2.8e-12 σ; finite cells identical; weight sums equal exactly.
- **D2** 8.3e-7 σ; WSClean's CRVAL3 equals each group's mean frequency
  exactly (0 Hz), so `-channels-out 16` groups channels as the product does;
  the WCS pixel equals rang's at all six positions.
- **D3** |bias| ≤ 0.021σ against 3/√6750 = 0.037σ (A −0.0007, B +0.014,
  C +0.005, D −0.018, E −0.010, F −0.021).
- **D3b** χ² 0.956-1.016 within 1 ± 0.052.
- **D4** 1.7e-14 σ_snap. **D5** group 15 empty: null in JSON and `nan` in
  CSV for every interval and position.
- Dev passes every gate, so `tsp2-held` is run.

### 10.2 `tsp2-held` (read once, code `f50b063e`)

Layout drawn from seed 20262314: pixels A (0, 0), B (−246, 111),
C (253, 372), D (−240, 124), E (310, −183), F (143, 110). Lightcurve 57 s,
WSClean `-j 8` 778 s.

| Gate | Reading | Bound | Outcome |
| --- | --- | --- | --- |
| D1 | 2.3e-12 σ; finite cells and weight sums identical | 1e-3 σ | **met** |
| D2 | 1.8e-6 σ; CRVAL3 offset 0 Hz; WCS pixel = rang's at all six | 1e-3 σ | **met** |
| D3 | \|bias\| ≤ 0.023σ (A +0.006, B −0.009, C +0.023, D −0.003, E −0.001, F +0.012) | 0.037σ | **met** |
| D3b | χ² 0.986-1.025 | 0.948-1.052 | **met** |
| D4 | 1.3e-14 σ_snap | 1e-6 | **met** |
| D5 | group 15 empty: null / `nan` everywhere | – | **met** |

**P2 is met on the held-out simulation, as frozen.** `tsp2-held` is now spent.

### 10.3 Real track: E2-A's ESO137 scan 10 with injected transients

**Residual (4.2).** Every check of the replay held exactly:
- Step 2: 10,747,830,624 flagged cells in the MS and 7,843,952,228 in
  ESO137-001 after restoring `rang_selfcal_20261115T161755Z` (189 s).
- Step 3: K1, G1, B1 applied, flagged cells unchanged at 10,747,830,624, as
  E2-A's apply (1,314 s).
- Step 4: round 2's Sa store applied; rebuilt bin times equal the store's
  (difference 0 s, 4 bins); ESO137-001 then has 8,082,693,644 flagged cells,
  E2-A round 2's count exactly (571 s). Attempt 1 of step 4 stopped before any
  write on a flag-shape error in the replay script (`read_store` gives flags
  per antenna, the solution per hand); fixed and resumed (`--selfcal-only`).
- CASA split: 1,245 s, 850,950 rows, 512 channels, 21 GB. 27,450 FLAG_ROW
  rows: 27,000 cross-correlation rows (60 per integration) and 450 others.
  WSClean ignores FLAG_ROW (ts-p1.md 15.3); both comparisons are below.
- `gemclean -predict` of E2-A's eight final model images: 823,500 rows in 90 s.
- Subtraction check (not a gate): at the five brightest sources of E2-A's
  final image (0.15-0.57 Jy/beam), DATA − MODEL keeps 0.2-1.1 % of the DFT
  flux in intervals 0 and 200.

**Injection.** u = 1.748 mJy (median σ_meas of intervals 0-9; over all 450
the median σ_meas is 1.316 mJy, 1.19-1.94 mJy, against about 0.08 mJy thermal,
scope note 4). A and B were redrawn once each by the 30″ rule. Truth in
[results/ts-p2/tsp2-real.truth.json](results/ts-p2/tsp2-real.truth.json).

**P1 against WSClean 3.7** (`-intervals-out 450`, 2048² at 2″, 323 s at
`-j 8`; [results/ts-p2/score-real-p1.json](results/ts-p2/score-real-p1.json)):
- **T1** max 3.6e-7 of the snapshot peak (median 1.1e-7; worst interval
  426) against 1e-5: **met**. With FLAG_ROW ignored, 3.4e-7.
- **T2c** 1.0e-6 σ_meas against 1e-3: **met**; WSClean's WCS pixel equals
  rang's at all six positions. No sample lies beyond the 2″ grid.

**The other gates** (`--real`, σ_meas and σ_dyn,g = 0.9-5.2 mJy;
[results/ts-p2/score-real-p2.json](results/ts-p2/score-real-p2.json); D2's
`pixels_equal_rang` reads false only because rang's pixel indices are on the
2048² grid and WSClean's D2 images are 1024², an offset of 512 in each
axis):

| Gate | Reading | Bound | Outcome |
| --- | --- | --- | --- |
| T2a | 7.3e-13 σ_meas | 1e-3 | **met** |
| T2b | 6.5e-7 σ_meas | 1e-3 | **met** |
| T3a | mean(flux − expected): A −0.69, B −0.23, C −0.37, D −0.03, E −0.81 σ_meas (F, the control, +0.57) | 0.141 | **not met** (A, B, C, E) |
| T3c | interval times = TIME | equal | **met** |
| T3d | all 7 pulses ≥ 7σ recovered, S/N 8.5-18.7 at every bright integration, best interval inside each pulse | as frozen | **met** |
| D1 | 5.0e-12 σ_dyn | 1e-3 | **met** |
| D3 | A +0.015, B +0.008, C +0.095, D −0.018, E −0.192 σ_dyn (F +0.185) | 0.035 | **not met** (C, E) |
| D4 | 3.1e-14 σ_meas | 1e-6 | **met** |
| T3b, D3b | χ² 0.37-1.31 (band), 2.3-6.7 (cells) | reported | – |
| D2 | 1.5e-6 σ_dyn against the WSClean `-intervals-out 450 -channels-out 16` pixel (1024² at 2″, 929 s at `-j 8`); CRVAL3 offset 0 Hz | 1e-3 | **met** |
| T4 (control) | positive 14,220 at ≥ 5σ and 1,914 at ≥ 7σ; negative 272 and 8 | reported | – |

**Why T3a and D3 fail (post hoc diagnostic, not a gate:
`examples/ts_p2_diag_linear.py`,
[results/ts-p2/diag-linear-real.json](results/ts-p2/diag-linear-real.json)).**
- Injected run minus uninjected run against the injections' expected dirty
  value: |bias| ≤ 1.3e-8 σ_meas over the band and ≤ 6e-9 σ_dyn per cell; the
  largest single difference is 4.9e-7 σ_meas. The product recovers the
  injected signal exactly.
- The offsets are the uninjected residual's own time-mean at each position:
  −0.91, −0.30, −0.49, −0.04, −1.06 and +0.75 mJy at A-F, that is −14.6σ to
  +12.1σ of a 450-point mean. E2-A's own final residual (Briggs 0.5) is 0.00-
  0.09 mJy at the same pixels (robust rms 22 µJy), so the offsets come with the
  natural weighting of the snapshots: unmodelled or mis-subtracted large-scale
  flux and the sidelobes of the 0.2-1 % errors on the brightest sources.
- The same structure gives the positive excess of candidates (T4: 14,220
  positive against 272 negative at 5σ).
- So, as frozen, the real-track bias gates fail on the residual floor, not on
  the light-curve or dynamic-spectrum code. The gates stand as frozen; this is
  recorded as not met.

### 10.4 Outcome

| Claim | Outcome |
| --- | --- |
| P2 on simulation (`tsp2-held`) | **met**, every gate as frozen |
| P1 parity on real data (T1, T2a-c, T3c) | **met**: WSClean 3.6e-7 of the peak, the DFT 1.0e-6 σ_meas |
| P1 recovery on real data (T3d) | **met**: 7 of 7 pulses |
| P1 bias on real data (T3a) | **not met**: A, B, C, E at −0.23 to −0.81 σ_meas against 0.141 |
| P2 parity on real data (D1, D2, D4) | **met**: 5.0e-12 and 1.5e-6 σ_dyn |
| P2 bias on real data (D3) | **not met**: C +0.095, E −0.192 σ_dyn against 0.035 |

The real-track bias failures come from the natural-weighted residual's own
mean at the positions (post hoc diagnostic, 10.3), which the frozen gate
counts against the product; injected minus uninjected matches the
injections to 1e-8 σ. The roadmap's v0.5.0 gate ("within tolerance of WSClean
`-intervals-out` and an exact DFT") is met on simulations and on real data;
the scope note's real-residual bias gate is not.

## 11. For the coordinator

- **E2-A's scan 10** was used as development data (4.2, 8); no held-out claim
  is made on it. `tsp2-held` and the `tsp2-real` injection seed are spent.
- **The real-data bias gate** (scope note T3, frozen here at 3/√N σ_meas)
  measures the residual floor at the position as much as the product. A
  follow-up could subtract an uninjected control (as 10.3's diagnostic does)
  or a deep residual image, under a new protocol and seed (`tsp2-real2`);
  not done.
- **Residual floor.** Snapshot σ_meas 1.32 mJy (about 16 × thermal), positive
  5σ candidates 52 × the negative ones: the residual of the brightest sources
  (0.2-1 % of 0.15-0.57 Jy) and large-scale flux dominate. That limits blind
  search on this field, not forced photometry.
- **Not done.** T7 (ω Cen, SARAO token), a real known variable, and a
  `rang-core run` arm with `--channels-out`.
- **Checks.** Quick check PASS and CI green at `f50b063e`; the full check
  (`python tools/check_all.py`) and `wheels` are left to the merge check.
- **Data kept:** `D:\rang\outputs\p1-lightcurves-20261123\scan10-512.ms`
  (the replayed, split, predicted and injected MS) and its run logs; the
  replay copy, simulation MSes and WSL scratch are deleted.
