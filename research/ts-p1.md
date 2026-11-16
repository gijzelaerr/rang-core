# TS-P1: residual snapshot light curves at given positions

Issue #9 (gijzelaerr/rang-core), time series P1 of
[v1-timeseries-scope.md](v1-timeseries-scope.md). Owner approved P1 on
2026-11-13. Branch `ts-p1`. Written 2026-11-16.

**Status 2026-11-16: implemented and measured.** As frozen: **not met
(oracle mismatch, T1 and T2c)**, on dev and on the held-out set. Under the
post hoc amendments 9.1 and 9.2: **met** on the held-out simulation (section
10.3). The amendments await the coordinator's acceptance. `tsp1-held` is now
spent: it was scored on two grids, so any later change to the code needs
`tsp1-held2`. The real-data arms are deferred.

**Status at freeze: proposed. Nothing here is built or measured.** This note is
committed before any code that tests it. Any later change is a dated amendment
in section 9, labelled post hoc if it could have seen a result.

## 1. Hypothesis and claim

rang-core can make per-integration (8 s) light curves at given positions from
the residual visibilities that `rang-core run` leaves (data column minus
MODEL_DATA). They agree with WSClean 3.7 `-intervals-out` snapshot images and
with an independent exact DFT within the frozen tolerances of section 5, and
they recover injected transients without bias.

The claim is **parity** with WSClean and the DFT, not novelty
([AGENTS.md](../AGENTS.md), Claims). Nothing here claims a better light curve or
a lower cost.

## 2. Scope

| In | Deferred: not built, not measured |
| --- | --- |
| `rang-core lightcurve`: forced light curves at listed RA/Dec. Per interval: the DFT flux at the exact position; the snapshot dirty image pixel nearest to it; σ_meas | Blind candidate search and its false-alarm gate T4 |
| Snapshot dirty images per interval (natural weighting, Stokes I), optional FITS output | GPU path and its gate T5 |
| Gates T1, T2 and T3 of the scope note, at the values proposed there | Cost gate T6. It needs an exclusive hold agreed with the coordinator. Wall times are recorded in [tool-timings.md](tool-timings.md) as shared-host figures, not gated |
| Two simulations (development, held out); one `rang-core run` arm, reported and not gated (section 6) | T7 (TRON ω Cen, owner decision 2); ESO137 ms1 real-data arms |
| | E2-A's field (section 8) |

## 3. Product definition (`rang-core lightcurve`)

- **Input.** A Measurement Set after `rang-core run`. The residual is formed on
  the fly as `DATA_COLUMN − MODEL_COLUMN`, in complex64: by default
  CORRECTED_DATA when present, else DATA, minus MODEL_DATA. The command
  refuses when the model column is missing, unless `--no-model` is given. It is
  read-only on the MS.
- **Selection.** One field, data description 0, cross-correlations only.
  FLAG_ROW rows and flagged cells carry weight zero.
- **Stokes I.** As WSClean's `-pol I` and `gemclean`:
  `I = ½(XX + YY)`, weight `min(4 w_XX, 4 w_YY)` from WEIGHT_SPECTRUM (else
  WEIGHT), zero when either hand is flagged (`rang.core_weights.stokes_i`).
  Natural weighting.
- **Intervals.** The selected rows' distinct TIME values, sorted. Interval k
  holds the TIME values k·K to (k+1)·K − 1; K = `--interval-steps`, default
  1. With K = 1 and N timesteps this is WSClean's `-intervals-out N`. The
  reported time is the mean of the interval's TIME values; for K = 1 it is the
  TIME exactly.
- **DFT flux (primary column `flux_jy`).** At (l, m) from the position by the
  SIN projection about the field's PHASE_DIR:
  `S = Σ w Re[I · exp(−2πi (u l + v m + w (n − 1)) ν / c)] / Σ w`, in float64,
  with no division by n (WSClean's and the wgridder's `divide_by_n=False`).
  The kernel is in Rust (`core/src/lightcurve.rs`). Its sign convention is the
  one that recovers a source predicted by `rang.core.predict_components` (G6's
  MODEL_DATA predictor) at that position. The tests check this, and the
  WSClean arm checks it against an independent tool.
- **Snapshot flux (`flux_snapshot_jy`).** The pixel nearest to the position in
  the interval's dirty image, made with `rang.core_wgridder.fits_image` (the
  exact wgridder, ε = 1e-6, WSClean's FITS orientation and normalisation,
  [df1-wgridder.md](df1-wgridder.md)). The pixel's offset from the position
  is reported. Defaults: `--size 1024`, `--scale 4asec`; `--no-images` turns
  snapshots off and gives the DFT only.
- **σ_meas.** 1.4826 × the median absolute deviation from the median, over
  every pixel of the interval's snapshot image.
- **Outputs.** `lightcurve.csv`, one row per interval and position;
  `lightcurve.json` with settings and provenance; and, with `--fits`, one
  snapshot FITS per interval. A receipt (`rang.receipt` version 5) is written
  beside the output directory.

## 4. Data

### 4.1 Simulations (written by `examples/ts_p1_sim.py`)

The simulations reuse A1's MeerKAT geometry and noise (`rang.simtruth`:
`antenna_table`, `geometry`, `target_sky`, `noise_integration`), and the
target-only MS layout of the C5 simulator.

- **Array and band.** All 64 antennas; 64 channels over 856-1712 MHz.
- **Time.** dt = 8 s; SIM-TARGET (RA 300°, Dec −36°); one scan of 450
  integrations (1 h) from A1's `START_UTC`; no autocorrelations.
- **Static sky.** A1's target sky from the case's sky seed, unpolarised and
  flat in frequency (as C5). It is written into DATA and, exactly, into
  MODEL_DATA, so the residual is the transients plus noise. This stands in
  for a perfect deep model.
- **Transients.** Unpolarised point sources, flat spectrum, no primary beam
  (apparent flux). Each sits on a pixel centre of the 1024², 4″ snapshot grid:
  l = −dx·4″, m = dy·4″, with integer (dx, dy), converted to RA/Dec by
  `simtruth.radec`. The truth per integration is the source's flux averaged
  over the integration [TIME − 4 s, TIME + 4 s), evaluated at the integration
  centre (no time smearing, as A1).
- **Noise.** A1's per-integration thermal noise from the case's noise seed:
  σ = SEFD / √(2 Δν Δt) per real and imaginary part, with SEFD 420 Jy,
  Δν = 13.375 MHz, Δt = 8 s, so σ = 0.028710 Jy. WEIGHT = 1/σ².
- **Noise of one snapshot (σ_snap), derived.** I = ½(XX + YY) has variance
  σ²/2 per part. With equal weights, a DFT or pixel value averages
  N = 2016 baselines × 64 channels = 129,024 samples, so
  σ_snap = σ / √(2N) = 5.652e-5 Jy. A noise-only interval check (section 5,
  T3 χ²) tests this number. It is not derived from 1/Σw: the Stokes I weight
  `min(4 w_XX, 4 w_YY)` is not an inverse variance of I.
- **Seeds.** New entries in `rang.simtruth.SEEDS`: `tsp1-dev` 20261601-4 and
  `tsp1-held` 20261611-4, as (jones unused, sky, noise, layout).

**Development set `tsp1-dev`.** Amplitudes are in units of σ_snap. The
radius in brackets is the frozen offset from the phase centre.

| Name | (dx, dy) [radius] | Light curve |
| --- | --- | --- |
| A | (0, 0) [0.0°] | 8 s pulses: integration 40 at 20σ, integration 300 at 10σ |
| B | (191, −191) [0.300°] | 16 s pulse: integrations 100-101 at 15σ |
| C | (−300, 335) [0.500°] | 64 s pulse: integrations 200-207 at 8σ |
| D | (−100, −251) [0.300°] | 30 s pulse every 20 min, 25σ, starting 403 s, 1603 s and 2803 s after the scan start, so partial integrations occur at both ends |
| E | (250, 260) [0.401°] | variable: 10σ (1 + ½ sin(2π t / 600 s)), t from the scan start, integrated exactly over each integration |
| F | (−127, 127) [0.200°] | none (empty control) |

**Held-out set `tsp1-held`.** It has its own sky and noise seeds. Its layout
is drawn from its layout seed by a rule fixed now:

- the same six roles, with radii 0.0°, 0.3°, 0.5°, 0.3°, 0.4° and 0.2°;
- the position angle uniform, then (dx, dy) rounded to integers;
- pulse start integrations uniform, chosen so that no two pulses of A-D
  overlap;
- amplitudes log-uniform over 7-50σ for A-D, and 5-20σ for E's mean;
- D's period 20 min, its first start uniform within the first 20 min, at
  whole seconds.

It is generated only after the code is frozen (the commit named in section 7)
and is read once.

### 4.2 The `rang-core run` arm (reported)

`rang-core image` with `image.write_model: true` runs on a copy of
`tsp1-dev` whose MODEL_DATA has been removed. GeMClean's deep model then
becomes MODEL_DATA, and `rang-core lightcurve` runs with its defaults. This
is the real chain. A deep model made from the whole hour absorbs part of each
source's time-averaged flux (E's mean of 10σ_snap is about 210σ in the 1 h
image), so the curves are expected to be **biased low by about the source's
mean**. This bias is named now and is reported, not gated.

## 5. Measures and frozen tolerances

σ in every gate is σ_snap = 5.652e-5 Jy on the simulations. σ_meas is
reported beside it.

| ID | Quantity | Oracle | Frozen bound |
| --- | --- | --- | --- |
| T1 | Snapshot dirty image, every interval | WSClean 3.7 (`rang-wsclean-native:3.7`) `-intervals-out 450 -size 1024 1024 -scale 4asec -weight natural -pol I -gridder wgridder -wgridder-accuracy 1e-6 -no-min-grid-resolution -niter 0`, on an ext4 copy whose `RESIDUAL_DATA` column holds the same complex64 residual | max over pixels \|rang − WSClean\| ≤ 1e-5 × max \|WSClean\|, on every interval |
| T2a | DFT flux, every interval and position | an independent float64 NumPy direct sum in the measurement script (not the Rust kernel), on the same residual, weights and flags | \|Δ\| ≤ 1e-3 σ per point |
| T2b | Snapshot pixel flux (positions on pixel centres) | the Rust DFT flux at that position | \|Δ\| ≤ 1e-3 σ per point |
| T2c | DFT flux | the WSClean `-intervals-out` pixel at the position, found from WSClean's FITS WCS by RA/Dec | \|Δ\| ≤ 1e-3 σ per point |
| T3a | Flux bias, each source over all 450 intervals | the expected dirty value: injected fluxes × the interval's beam, Σ_Y S_Y(t) B_t(X, Y), computed by the measurement script's NumPy DFT from the injected list and the MS's UVW and weights (this includes the other sources' sidelobes) | \|mean(flux − expected)\| ≤ 0.1σ |
| T3b | Reduced χ² of (flux − expected)/σ, each source | as T3a | in [0.8, 1.2] |
| T3c | Time stamps | the simulation's TIME of each integration | equal exactly (float64), all 450 |
| T3d | Recovery: every pulse with a peak truth ≥ 7σ | truth | at each of its integrations with truth ≥ 7σ, flux/σ_meas ≥ 4; and the integration with the largest flux within [start − 3, end + 3] holds at least half the pulse's peak truth |

T3a against the expected dirty value is the gate. Bias against the injected
flux alone is also reported, at intervals where only that source is on.

## 6. Decision rule (named before any result)

- **Met:** T1, T2a-c and T3a-d all pass on `tsp1-held`. They must also have
  passed on `tsp1-dev` first, or the held-out set is not run.
- **Not met (gate named):** any gate fails on `tsp1-held`. The failing gate,
  intervals and numbers are recorded. Tolerances are not changed. A fix comes
  as a dated amendment and a new held-out seed (`tsp1-held2`), and the failure
  stays in this note.
- **Fails on dev:** fixed and rerun on dev; each attempt is logged in section
  7. If T1 or T2c cannot be met because WSClean's interval or pixel
  conventions differ, that is recorded as **not met (oracle mismatch)** with
  the measured difference, and the convention is documented.
- **The `rang-core run` arm:** reported. The expected bias of section 4.2 is
  not a failure.
- **Not checked:** T4, T5, T6 (cost; shared-host wall times reported only),
  T7, ESO137 and E2-A.

## 7. Stages, cost and stop rules

1. Freeze this note (this commit).
2. Rust kernel, Python command, tests; `python tools/check_all.py --quick`.
3. Generate `tsp1-dev` under the heavy lock, then run lightcurve and the NumPy
   oracle (T2a, T2b, T3) and WSClean on a WSL ext4 copy (T1, T2c).
4. Freeze the code (commit named here as an amendment), generate `tsp1-held`,
   and run everything once.
5. The `rang-core run` arm on a dev copy.

Bookings: the simulation and lightcurve use 4 threads and at most 8 GB;
WSClean uses `-j 4`. All are shared slots, so wall times are shared-host
figures. Outputs go to `D:\rang\outputs\ts-p1-20261116` (about 5 GB per MS).
The WSClean copies go on WSL ext4 under `~/Build/tmp`. Stop when D: falls
below 200 GB free (memory: keep 150 GB free; E2-A needs room).

## 8. Owner and coordinator items, at freeze

- **E2-A's field.** The issue names it as a gate dataset, but
  [v1-timeseries-scope.md](v1-timeseries-scope.md) section 5 lists ESO137
  ms1 target scan 10 (MAIN_4, E2-A) as **not usable**: A0 holds it out. Its MS
  (`D:\rang\outputs\e2a-20261115\e2a.ms`) is also being scored by another
  session, and a copy does not fit the D: free-space rule. Deferred; the
  coordinator decides which of the two documents governs.
- **A known variable in the ESO137 field** is still open (scope section 7).

## 9. Amendments

All three amendments are dated 2026-11-16 and are **post hoc**: they were
written after dev attempt 1 (section 10.1) had been seen. They were committed
before any rerun and before `tsp1-held` existed. They need the coordinator's
acceptance, as E2-A's 9.5 did. The held-out result is reported under the
frozen rule first and then under the amended rule.

**9.1 Snapshot grid: 2048² at 2″ for both arms (was 1024² at 4″).**
- **Why.** At 4″ the grid ends at 1/(2·4″) = 25.8 kλ, but MeerKAT's longest
  baselines reach 40.8 kλ in u and 34.4 kλ in v at the top channel (read from
  the dev MS's UVW). With `-no-min-grid-resolution`, WSClean drops the samples
  beyond the grid: 530 of 129,024 in interval 0. The exact gridder keeps them,
  aliased, which is exact at pixel centres, so T2b passes.
- **Proof.** Removing exactly those samples from rang's snapshot brings the
  difference from WSClean down to 2.7e-7, 2.0e-7 and 7.5e-8 of the peak in
  intervals 0, 225 and 430.
- **Change.** At 2″ the grid ends at 51.6 kλ, so no sample in the 450
  intervals lies beyond it. Every source keeps its pixel centre (pixel offsets
  double), and C (0.5°, 900 px) stays inside.
- **Unchanged.** Tolerances, data and seeds.
- **New in the product.** `rang-core lightcurve` counts the weighted samples
  beyond its grid (`outside_grid`) and warns. Its default stays 1024² at 4″;
  the coordinator decides whether to change it.

**9.2 T3a's bound on a noisy set: 3/√N σ (0.141σ at N = 450).**
- **Why.** The frozen 0.1σ is 2.1 standard errors of a 450-point mean
  (1/√450 = 0.047σ). With six sources, one of them fails by chance in about
  one set in five. Dev's E failed at 0.104σ.
- **Change.** 3/√N σ matches T3b, which already sits at about 3 standard
  errors (√(2/450) = 0.067).
- **Noise check, bound frozen before the run.** To show that E's offset is
  noise and not a flux-scale error, the noiseless twin of `tsp1-dev` (same
  seeds, `--noiseless`, DFT only) must give |bias| ≤ 0.01σ for every source.
  If it does not, there is a bug, and the run stops.
- **Kept.** The frozen 0.1σ is still reported, and the noise seed is not
  redrawn.

**9.3 Bookkeeping.**
- `rang.simtruth.SEEDS` needs an `rfi` key for its registry test, so the TS-P1
  entries carry an unused `rfi` seed: 20261605 for dev and 20261615 for
  held-out.
- One TS-P1 MS is 5.76 GB (DATA, MODEL_DATA, RESIDUAL_DATA; no
  WEIGHT_SPECTRUM), not "about 5 GB".
- At 2048² the snapshots are not written to disk. The scorer remakes rang's
  images in stream with the product's own `light_curves`, at the run's
  settings, and checks that the fluxes repeat bit for bit. It reads WSClean's
  FITS from the WSL ext4 directory. The FITS writer is covered by the tests and
  by dev attempt 1.

## 10. Measured result

### 10.1 Dev attempt 1 (frozen settings, 1024² at 4″), 2026-11-16

- **Code.** Commit `ec6bef5`. The extension was built during the first quick
  check, from the source before its clippy fix (an iterator rewrite of one
  loop, with no change to the numbers).
- **Run paths.**
  - Data and receipts: `D:\rang\outputs\ts-p1-20261116\` (`tsp1-dev.ms`,
    `tsp1-dev.truth.json`, `lc-dev\`, `score-dev.json`,
    `lc-dev.lightcurve.rang-receipt.json`).
  - WSClean: `~/Build/tmp/20261116-ts-p1/wsc-dev` (WSL); its dirty images
    were copied to `D:\...\wsc-dev`.
- **σ.** σ_meas median 5.660e-5 Jy = 1.0014 σ_snap (range 0.988-1.013), so
  the derived σ_snap holds.

| Gate | Measured | Frozen verdict |
| --- | --- | --- |
| T1 | max 0.082, median 0.033 of the peak (worst interval 430) | **fail** (WSClean drops the samples beyond the grid, 9.1) |
| T2a | 1.1e-10 σ | pass |
| T2b | 2.8e-6 σ | pass |
| T2c | 0.258σ; WCS pixels equal rang's for all six positions | **fail** (same cause) |
| T3a | A 0.027, B −0.048, C 0.039, D 0.031, **E 0.104**, F −0.026 σ | **fail** (E) |
| T3b | 0.975-1.103 | pass |
| T3c | all 450 times equal | pass |
| T3d | every pulse ≥ 7σ recovered | pass |

- **Timing** (shared host, 4 threads, not gated):
  - `rang-core lightcurve`: 108.6 s wall, 267 CPU-s, peak RSS 151 MB. Of the
    wall time, image 95.9 s, read 10.6 s, DFT 1.3 s.
  - WSClean `-intervals-out 450 -j 4`: 128.5 s wall, peak RSS 155 MB.
  - The simulation: 63 s.

### 10.2 Dev attempt 2 (amendment 9.1, 2048² at 2″) and the noiseless twin

- **Code freeze.** Commit `8270868` (quick check PASS; CI `tests` and `docs`
  green). Every run below used it.
- **Run paths.** `D:\rang\outputs\ts-p1-20261116\` (`lc-dev2\`,
  `score-dev2.json`, `lc-twin\`, `score-twin.json`). WSClean ran in
  `~/Build/tmp/20261116-ts-p1/wsc-dev2`, which was deleted after scoring.
- **Grid.** WSClean gridded all 129,024 samples in every interval, and rang
  counted 0 beyond its grid.

| Gate | Measured | Frozen | Amended |
| --- | --- | --- | --- |
| T1 | max 2.5e-7, median 4.2e-8 of the peak | pass | pass |
| T2a | 1.1e-10 σ | pass | pass |
| T2b | 1.4e-6 σ | pass | pass |
| T2c | 1.3e-6 σ; WCS pixels equal rang's | pass | pass |
| T3a | as attempt 1, max E 0.104σ (the DFT fluxes do not depend on the grid) | **fail** | pass (≤ 0.141) |
| T3b | 0.975-1.103 | pass | pass |
| T3c, T3d | all equal; every pulse recovered (lowest S/N C at 6.2) | pass | pass |

- **Twin** (`--noiseless`, the same seeds, DFT only). Max |bias| is
  7.6e-8 σ (C) against the 0.01σ bound, so E's 0.104σ is noise, not a flux
  scale error. The twin's Rust and NumPy DFTs agree to 4.4e-12 σ.
- **Dev passes** under the amended rule, so the held-out set was generated.

### 10.3 Held-out `tsp1-held` (read once, commit `8270868`)

**Layout** (drawn by the frozen rule):

| Source | Pixel | Signal |
| --- | --- | --- |
| A | (0, 0) | 8 s pulses at 117 (23.4σ) and 328 (28.6σ) |
| B | (−166, 213) | 16 s pulse at 170 (39.4σ) |
| C | (230, −387) | 64 s pulse at 234 (49.4σ) |
| D | (256, −86) | 8.6σ every 20 min from 504 s |
| E | (257, 252) | mean 6.4σ |
| F | (49, 173) | empty |

**Results, amended grid (2048² at 2″):**

| Gate | Measured | Frozen | Amended |
| --- | --- | --- | --- |
| T1 | max 3.0e-7, median 5.2e-8 of the peak | pass | pass |
| T2a | 1.4e-10 σ | pass | pass |
| T2b | 3.9e-6 σ | pass | pass |
| T2c | 2.5e-6 σ; pixels equal | pass | pass |
| T3a | A −0.016, B −0.003, C 0.042, D −0.017, E 0.002, F 0.006 σ | pass | pass |
| T3b | 0.910-1.037 | pass | pass |
| T3c | all 450 equal | pass | pass |
| T3d | 7 pulses; lowest S/N 7.1 (D, peak 8.6σ) | pass | pass |

- **σ.** σ_meas median 1.0004 σ_snap.
- **Frozen 1024² at 4″, run after the amended set for the record.**
  - T1 0.086 (median 0.050) and T2c 0.25σ: **fail**, as on dev.
  - Everything else passes: T2b 3.4e-6 σ, T3a 0.042σ.
  - rang warned of 265,415 weighted samples beyond the grid (590 per
    interval, 0.46 %).

**Outcome.**
- **As frozen: not met (oracle mismatch, T1 and T2c).** Dev failed T1, T2c
  and T3a. On the held-out set at the frozen grid, T1 and T2c fail because
  WSClean drops the samples beyond the grid (9.1).
- **Under the post hoc amendments 9.1 and 9.2: met.** Every gate passes on
  the held-out set. At the amended grid, the frozen tolerances (T3a's 0.1σ
  included) hold as well.
- **The amendments are not yet accepted.** `tsp1-held` was scored on two
  grids and is now spent.
- **The claim** is parity with WSClean `-intervals-out` and the exact DFT,
  within the scope given in 10.6. No novelty is claimed.

### 10.4 The `rang-core run` arm (reported, not gated)

- **What ran.** `rang-core image` (`tools/oracles/ts-p1/run-arm.yaml`:
  GeMClean, 2048² at 2″, Briggs 0, `auto_threshold 3`, `mgain 0.8`,
  `write_model`) on a copy of `tsp1-dev`, from DATA. It took 89.8 s
  (GeMClean 58 s, the MODEL_DATA write 31 s). `rang-core lightcurve` then ran
  on the result. The copy was deleted after scoring; the scores and the
  GeMClean report are in `research/results/ts-p1/`.
- **Bias against the expected dirty value (σ).** A +0.06, B +0.19, C −0.27,
  D +0.15, **E −9.57**, **F +10.67**.
  - E: the deep model absorbed its mean of 10σ, as named in 4.2.
  - F (empty control): F lies 34″ from a 48 mJy Gaussian of FWHM 45″ in the
    static sky, and 104″ from a 57 mJy, 50″ one. The +10.7σ (about 0.6 mJy)
    is consistent with that component's flux left behind by CLEAN without
    multiscale. **Unverified:** the model image at F was not inspected.
- **Departures from 4.2.**
  - MODEL_DATA was overwritten by GeMClean's predict rather than removed
    first. The result is the same.
  - The lightcurve ran at 2048² and 2″ (9.1), not at its defaults.
- **Noise and recovery.** σ_meas = 1.30 σ_snap: unmodelled extended emission
  raises the snapshot rms by 30 %. All 7 pulses ≥ 7σ are still recovered
  (lowest S/N 4.6, C).
- **Reading.** With a GeMClean deep model, the product's light curves are
  biased by the deep model's errors at the position. A constant offset per
  source is model error, not variability, so the light curves are relative
  unless the model is right there.

### 10.5 Timings (4 threads, shared host, not gated)

| Step | Dev | Held-out |
| --- | --- | --- |
| Simulation | 63 s | 76 s |
| `rang-core lightcurve` at 2048², 2″ | 241 s, 692 CPU-s, 285 MB | 319 s, 830 CPU-s, 285 MB |
| `rang-core lightcurve` at 1024², 4″ | 109 s | 126 s |
| WSClean 2048², 2″, `-j 4` | 312 s, 271 MB | 402 s, 273 MB |
| WSClean 1024², 4″ | 128 s, 155 MB | 126 s, 155 MB |

- **Where rang's time goes.** In the lightcurve runs, the DFT of six
  positions over 58 M Stokes I samples takes 1.3-1.6 s, and the snapshot
  images take 95-302 s.
- **DFT only** (`--no-images`, the twin): 13.6 s, 81 MB.
- On the shared host, rang's wall time is 0.77-0.79× WSClean's at 2048² and
  0.85-1.00× at 1024², at the same threads, with about the same peak memory.
  This is not T6: there was no exclusive hold.

### 10.6 Scope of the parity, and not done

**Untested by these simulations.** Both sets have:
- no flags;
- equal weights, from WEIGHT only (no WEIGHT_SPECTRUM);
- one field and one scan;
- DATA as the data column (no CORRECTED_DATA).

So T1 did **not** test the following against WSClean: the Stokes I weight
rule with unequal hands, flagged cells, FLAG_ROW, WEIGHT_SPECTRUM, or the
CORRECTED_DATA default. A real `rang-core run` MS has all of them. The rules
come from the tested `core_weights.stokes_i` (WSClean's `-pol I`), but their
use here is not gated.

**Not done.**
- T4 (blind search) and T5 (GPU) are not built.
- T6 needs an exclusive hold.
- T7, ESO137 and E2-A's field (section 8) are not run.
- No notebook or docs page beyond `docs/cli.md`.
- The proof of 9.1 is `research/results/ts-p1/diag_grid_4asec.py`, with its
  output and the command that regenerates its inputs.

## 11. For the coordinator

- **Amendments.** Accept or reject 9.1 (snapshot grid 2048² at 2″) and 9.2
  (T3a at 3/√N, with the twin check). As frozen, the outcome is not met;
  with both accepted, it is met.
- **CLI default.** `rang-core lightcurve` defaults to 1024² at 4″, which
  warns on MeerKAT L band: about 0.46 % of samples lie beyond the grid, which
  rang keeps and WSClean drops. Decide whether to change the default, for
  example to 2″, at four times the FFT cost.
- **E2-A.** The issue names E2-A's field as a gate, but the scope note holds
  it out (section 8).
- **Untested** (10.6): flags, unequal and spectral weights, and
  CORRECTED_DATA against WSClean. These need a third simulation or a real
  MS before a real-data claim.
- **With a GeMClean model**, the light curves carry the model's error at the
  position (10.4).
- **T6** needs an exclusive hold.
- **Checks not run.** The full local check (`python tools/check_all.py`) and
  the `wheels` workflow, since there is no pull request. The change touches
  `core/` (a kernel and its binding), so `wheels` will run on a pull request.
- **Data.** Two MSes (11.5 GB) remain in `D:\rang\outputs\ts-p1-20261116`;
  delete them when not needed.
- **Lock.** One `pytest -n 4` (about 3 min) ran outside the heavy lock early
  in the session.

## 12. Coordinator decisions, 2026-11-16 (owner delegated: "do whatever you think is best")

- **9.1 (snapshot grid 2048² at 2″) accepted, post hoc.** The frozen T1/T2c miss is an
  oracle-configuration mismatch, not a rang error: WSClean drops the 0.46 % of samples beyond
  1/(2·4″) and rang keeps them; removing exactly those samples gives 2.7e-7 of WSClean. The
  result is reported as "met on the held-out simulation under post hoc amendment 9.1", never as
  met as frozen.
- **9.2 (T3a bound 3/√N with the noiseless-twin check) accepted, post hoc**, with the same label.
- **CLI default stays 1024² at 4″, with its warning on MeerKAT L band.** Changing it is a code
  change that would need `tsp1-held2`. A later change sets the default from the uv coverage
  and is gated on `tsp1-held2`.
- **No real-data claim yet.** Flags, unequal or spectral weights and CORRECTED_DATA are untested
  against WSClean. E2-A's field stays held out as the scope note says. T4-T7 and ESO137 are
  next, with T6 under an exclusive hold.
