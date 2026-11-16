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

## 13. Protocol 2: real-MS inputs, T4, T5 and T6 (frozen 2026-11-16, before any run)

Written after section 12 and before any code or data for it exists. Nothing
here is built or measured at this commit. Everything runs under the heavy
lock, pytest included. Bookings: 4 slots and 8 GB unless stated; T6 is
exclusive.

### 13.1 `tsp1-held2`: flags, weights and CORRECTED_DATA

**What stays as in 4.1.** The array, band, time, static sky, the six roles,
the layout rule and the 2048² grid at 2″ of 9.1.

**Seeds.** `tsp1-held2` uses 20261621-27, in the order jones (unused), sky,
noise, layout, rfi (unused), flags, weights.

**New in the data.**
- **Columns.**
  - CORRECTED_DATA = static sky + transients + noise.
  - DATA = CORRECTED_DATA × 2 e^{0.7i}, so that reading the wrong column
    doubles and rotates every flux.
  - MODEL_DATA = static sky.
  - RESIDUAL_DATA = CORRECTED_DATA − MODEL_DATA in complex64, for WSClean
    only.
  - `rang-core lightcurve` runs with its default column, which must pick
    CORRECTED_DATA.
- **Spectral, unequal weights in WEIGHT_SPECTRUM.**
  - w_pq,h(ν) = w0 · c(ν) · a_p,h · a_q,h, where w0 = 1/σ²,
    c(ν_k) = 1 + ½ cos(2π k / 64) and a_p,h ~ U(0.5, 1.5) per antenna and
    hand, drawn from the weights seed. XY and YX take √(w_XX w_YY).
  - The noise of each correlation is A1's unit draw scaled to
    σ_cell = 1/√w_cell.
  - WEIGHT is the channel mean of WEIGHT_SPECTRUM.
- **Flags** (drawn from the flags seed):
  - 3 % of (row, channel) cells flagged in all four correlations;
  - 2 % in XX only and 2 % in YY only;
  - channel 10 flagged in every row;
  - FLAG_ROW set on 2 % of rows, with their cells left unflagged, so that
    FLAG_ROW alone must remove them.
- **σ_snap per interval**, written to the truth from the cells actually used:
  σ_snap,k = √(Σ w_I² v) / Σ w_I, where w_I = min(4 w_XX, 4 w_YY) (zero if
  either hand is flagged or the row is), and v = (σ_XX² + σ_YY²)/4.

**Gates** on `tsp1-held2`, as amended: T1, T2a, T2b, T2c, T3a (3/√N),
T3b, T3c and T3d. In T3, σ is the per-interval σ_snap,k. The scorer forms its
own Stokes I from CORRECTED_DATA − MODEL_DATA, WEIGHT_SPECTRUM, FLAG and
FLAG_ROW, without the product's code. `tsp1-held2` is generated after the
code freeze of 13.5 and read once.

### 13.2 T4: blind candidates and false alarms

**Product.** `rang-core lightcurve --candidates U` lists the local maxima
(over the 8 neighbours) of each snapshot at or above U·σ_meas, and of the
negated image (the null), into `candidates.csv`. Each row gives the interval,
time, sign, pixel, RA/Dec, flux and S/N.

**Data: `tsp1-noise`.** As `tsp1-dev` but without transients. Seeds
20261631-35 (as dev's keys); 2048² at 2″; U = 5.

**Expectation.** For each interval, the expected Euler characteristic of a
stationary Gaussian field with correlation ρ = the normalised PSF (pixel
units):

E(u) = A √det Λ / (2π)^{3/2} · u e^{−u²/2} + (P/2) (det Λ)^{1/4} / (2π) · e^{−u²/2} + Q(u)

- A is the image area and P its perimeter.
- Λ comes from a least-squares fit of ln ρ = −½ xᵀΛx over the central
  pixels with ρ > 0.5 of the PSF of interval 0 (the scorer makes it with the
  product's snapshot function from unit visibilities).
- Q is the upper normal tail.
- The total E5 sums the 450 intervals with the interval-0 Λ.

**Gate T4:**
- no positive candidate ≥ 7σ_meas;
- the count of positive candidates ≥ 5σ_meas within 3√E5 of E5.

Negative counts and `tsp1-held2`'s blind recoveries are reported, not gated.

### 13.3 T5: GPU against CPU

**Product.** `--gridder wstack --device cpu|gpu` makes the snapshots with
rang's w-stacking gridder (X2's wgpu path on the GPU, f64; defaults: 64 w
layers, padding 1.2). The default stays the exact wgridder on the CPU.

**Data.** The extension is built with the `gpu` feature into a separate
venv (`~/Build/tmp/20261116-ts-p1-gpu`). It runs on `tsp1-held2`, intervals
0, 10, …, 440 (45 intervals), because the CPU w-stacking is slow.

**Gate T5:** max |GPU − CPU| ≤ 1e-6 × max |CPU| on every one of those
intervals. Reported, not gated: wstack against wgridder.

### 13.4 T6: cost

`rang-core lightcurve` (wgridder, 2048² at 2″, `RAYON_NUM_THREADS=16`)
against WSClean 3.7 `-intervals-out 450 -j 16`, same size, scale, weighting
and column, on `tsp1-held2`, each under its own exclusive hold
(`heavy_lock.py run -- …`).

**Gate T6:** rang's wall time ≤ 1.5 × WSClean's and peak memory ≤ 1.5 ×
WSClean's. WSClean's time includes its reorder; rang reads from D: (NTFS)
and WSClean from ext4, which is stated with the result.

### 13.5 Order, decision rule and what is not run

**Order.**
1. This note.
2. Code and tests; quick check PASS; commit, the code freeze.
3. `tsp1-noise` → T4.
4. `tsp1-held2` → T1-T3, then T5, then T6.

**Decision rule.**
- Each gate passes or fails as written. A failure is recorded with its
  numbers and is not retuned.
- A code fix needs `tsp1-held3` and a dated amendment.
- "Met on real-MS inputs (simulated)" needs T1-T3 to pass on `tsp1-held2`.
- T4, T5 and T6 are reported gate by gate.

**Not run in this protocol.**
- **T7.** It needs TRON's ω Cen data and a SARAO token (owner decision 2).
- **ESO137 ms1 scan 2.**
  - It needs about 150 GB per 4,096-channel target hour plus calibrator
    scans, 4-6 h of HTTP fetch at the measured 7-10 MB/s, a full K/G/B
    calibration and a deep model. That is owner decision 3.
  - D: has 251 GB free against the 200 GB stop rule, and E2-A needs room.
  - Proposed instead: a 512-channel averaged fetch, once the owner accepts
    it.
- **The uv-coverage default grid** (section 12, optional). Its snapshots
  would not put the frozen positions on pixel centres, so T2b could not
  gate it. It needs its own protocol.
### 13.6 Amendment, 2026-11-16, post hoc (after T5's first attempt failed to run)

The T5 run as frozen (2048², padding 1.2) stopped before its first
comparison. The GPU w-stacking path refused the grid: `RuntimeError: padded
width 2460 has a prime factor above 16` (2460 = 2²·3·5·41; X2's FFT takes
factors up to 16 only). The CPU path accepts it. This is recorded as a
limitation of the GPU path, not as a T5 measurement.

**Amended T5.**
- **Grid.** 2000² at 2″, which pads to 2400 = 2⁵·3·5². The field is 1.11°;
  C, at 0.5°, sits 900 px from the centre, inside the image. Every position
  stays on a pixel centre.
- **Unchanged.** Intervals, bound, data and code.
- The size was chosen only to make the GPU path run, before any GPU or CPU
  w-stacking image of `tsp1-held2` existed.
## 14. Protocol 2: measured result

The code freeze is `08bfefb`; protocol 2 itself was frozen at `834cf15`. Run
paths are in `D:\rang\outputs\ts-p1-20261116\` (`tsp1-noise.ms`,
`tsp1-held2.ms`, `lc-noise\`, `lc-held2\`, `score-t4.json`,
`score-held2.json`). WSClean ran in `~/Build/tmp/20261116-ts-p1/wsc-held2`.
The compact archives are in `research/results/ts-p1/`. Every run below went
under the heavy lock.

### 14.1 `tsp1-held2`: T1-T3 (read once)

- **Inputs.** The product picked CORRECTED_DATA and WEIGHT_SPECTRUM by
  default. Each interval kept 114,447-116,785 of 129,024 samples after the
  flags. σ_snap,k was 6.10-6.17e-5 Jy, and σ_meas matched it (median 6.137e-5
  Jy).

| Gate | Measured | Verdict |
| --- | --- | --- |
| T1 | max 0.194, median 0.128 of the peak | **fail** |
| T2a (against the NumPy Stokes I and DFT) | 6.5e-11 σ | pass |
| T2b | 4.2e-6 σ | pass |
| T2c | 0.51σ; WCS pixels equal rang's | **fail** |
| T3a | max E 0.036σ (bound 0.141) | pass |
| T3b | 0.912-1.024 | pass |
| T3c | all 450 equal | pass |
| T3d | 7 pulses; lowest S/N 11.0 | pass |

**Cause of T1 and T2c (post hoc diagnostic,
`research/results/ts-p1/diag_flagrow.py`).**
- WSClean 3.7 ignores FLAG_ROW. Its source tree (3.6, in
  `~/Build/tmp/20261109-g4-wsclean-src`) never reads the column, and
  schaapcommon's `ExtractWeights` uses only FLAG.
- tsp1-held2 sets FLAG_ROW on 2 % of rows (34, 41 and 59 rows in intervals
  0, 225 and 309) and leaves their cells unflagged.
- With FLAG_ROW applied, rang differs from WSClean by 0.128, 0.132 and 0.194
  of the peak. With FLAG_ROW ignored, the difference is 6.6e-8, 5.8e-8 and
  5.6e-8.
- So the rest of protocol 2 agrees with WSClean to about 6e-8 of the peak:
  per-cell and single-hand flags, the fully flagged channel, spectral and
  unequal WEIGHT_SPECTRUM with WSClean's `min(4 w_XX, 4 w_YY)` (read from
  that source), and the CORRECTED_DATA residual.
- rang follows the MS definition (CASA honours FLAG_ROW). An MS whose
  FLAG_ROW rows are not also flagged per cell will image differently in
  WSClean.
- `core/src/gemclean/input.rs` documents FLAG_ROW as giving weight zero
  "as in WSClean". On this evidence that is not what WSClean does, and
  GeMClean's FLAG_ROW handling was not tested here.

**Outcome as frozen: not met (oracle mismatch: FLAG_ROW).** T2 and T3 pass
on the real-MS inputs. The tolerances are not changed, and `tsp1-held2` is
spent.

### 14.2 T4: blind false alarms (`tsp1-noise`)

- **Measured.** No candidate reached 7σ_meas (0 positive, 0 negative;
  expectation 0.0016). At 5σ_meas there were 239 positive and 234 negative
  candidates, against the frozen E5 = 188.0 (3√E5 = 41).
- **Verdict.** **T4 fails** at 5σ: +3.7 Poisson σ.
- **Post hoc diagnostic** (`research/results/ts-p1/diag_t4_lambda.py`;
  the verdict stands):
  - The frozen Λ is a Gaussian fit to the main lobe above ρ = 0.5 (FWHM
    19″ × 14″, det Λ 0.0071 pixel⁻²). It gives a smaller curvature than the
    PSF has at its peak.
  - The finite-difference curvature at the peak, the Λ the EC formula
    actually uses, gives det 0.0189 and E5 = 307 (3√E = 53). The count is
    then −1.3σ.
  - Pixel-grid peak counting misses maxima that fall between pixels, which
    lowers the count against the continuous EC.
  - Positive and negative counts agree (239 against 234), so there is no
    excess of positive false alarms over the null. σ_meas equals σ_snap
    (median ratio 1.0000).
- **Reading.** The miss is in the frozen expectation, not in the
  candidates. A fixed rule needs a new noise set (`tsp1-noise2`) and a
  dated amendment.
- **Blind recovery on `tsp1-held2`** (reported):
  - Every interval with truth ≥ 7σ was found blind for A, B, C and D (2, 2,
    8 and 12 of 2, 2, 8 and 12); E was found in 61 of 108.
  - No negative candidate reached 7σ.
  - 37 positive candidates ≥ 7σ lie more than 3 px from every source. All
    of them fall in intervals with a ≥ 12σ source (mostly C's 42σ pulse,
    intervals 323-330): sidelobes of an undeconvolved snapshot.
### 14.3 T5: GPU against CPU (`tsp1-held2`, amendment 13.6)

- **Measured.** At 2000² and 2″, across 45 intervals (0, 10, …, 440), the
  GPU w-stacking (RTX 4070 Ti, Vulkan, f64) differs from the CPU w-stacking
  by at most 1.9e-15 of the peak. Median time per snapshot: GPU 2.5 s, CPU
  6.0 s (8 threads, shared host).
- **Verdict.** **T5 passes** (bound 1e-6).
- **Build.** The extension was built with `--features gpu` into
  `~/Build/tmp/20261116-ts-p1-gpu` (venv and cargo target). maturin's
  editable install also put that build into the worktree's
  `python/rang/_core.pyd`; the final quick check restores the default build.
- **Reported, not gated: w-stacking against the exact wgridder.**
  - The w-stacking (WSClean 3.6-1's algorithm as reproduced for the archive)
    differs from the wgridder by 0.28-0.41 of the peak over the full image.
  - In interval 0 that is 0.34 for the full image, 0.012 in the inner half
    and 0.0018 in the inner quarter (`research/results/ts-p1/diag_wstack.py`),
    so the difference sits at the edges of the image.
  - The GPU path therefore matches its CPU twin exactly, but not
    WSClean-grade snapshots at the field edge. The product's default stays
    the wgridder.
- **The 2048² padded width (2460) is refused by the GPU path** (13.6).
### 14.4 T6: not run

The exclusive ticket (rang, then WSClean, each `heavy_lock.py run -- …`
with 16 threads) reached the head of the queue but never started. The host
had one shared hold left: the E2-A scorer, pid 31176, 4 slots and 10 GB,
started 06:20 and IDLE at under 5 % of a core for more than four hours.
While waiting, the ticket kept every later shared job off the host, so it
was withdrawn. The hold was not touched.

T6 needs the coordinator to clear or schedule that hold. The command, with
`tsp1-held2` kept on D: for it, is:

    RAYON_NUM_THREADS=16 python tools/heavy_lock.py run -- python -m rang.core_cli lightcurve D:\rang\outputs\ts-p1-20261116\tsp1-held2.ms --field 3 --positions D:\rang\outputs\ts-p1-20261116\tsp1-held2.positions.csv --size 2048 --scale 2asec --out D:\rang\outputs\ts-p1-20261116\lc-t6
    (WSL) python3 ~/Github/rang/tools/heavy_lock.py run -- bash tools/oracles/ts-p1/wsclean_intervals.sh /mnt/d/rang/outputs/ts-p1-20261116/tsp1-held2.ms ~/Build/tmp/20261116-ts-p1/wsc-t6 16 450 2048 2asec

Shared-host figures from the scoring runs (4 threads, not T6):
- rang: 359 s, 288 MB.
- WSClean: 340 s, 274 MB.

### 14.5 Protocol 2 outcome

| Gate | Outcome |
| --- | --- |
| T1, T2c | **Not met (oracle mismatch).** WSClean ignores FLAG_ROW. With that one difference removed, rang matches WSClean to 6e-8 on flags, spectral and unequal weights, and CORRECTED_DATA |
| T2a, T2b, T3a-d | Met on the real-MS inputs |
| T4 | **Not met.** 0 candidates at 7σ (pass); at 5σ, 239 against the frozen E5 = 188 (+3.7σ). The expectation used the Gaussian-lobe Λ; the peak-curvature Λ gives 307 (−1.3σ). Positive and negative counts are equal |
| T5 | **Met** at 2000² (13.6, post hoc): 1.9e-15. The GPU path refuses the 2048² grid |
| T6 | **Not run.** The exclusive hold was blocked |
| T7, ESO137 | **Not run** (13.5: owner decisions 2 and 3) |
## 15. Coordinator decisions of 2026-11-16 (second set), amendments and results

The coordinator's decisions (message, 2026-11-16): rang keeps honouring
FLAG_ROW. WSClean's behaviour is recorded as a known oracle difference, and
T1/T2c report the raw comparison and the comparison with FLAG_ROW ignored.
GeMClean's FLAG_ROW handling is to be checked and fixed. T4 gets a dated
amendment and a fresh noise set. T6 runs when the host is free, with the
exclusive ticket at the head of the queue for at most about 10 minutes. T7
and ESO137 are left.

### 15.1 Correction to 14.2 and 14.5

14.2 and 14.5 gave the post hoc count as −1.3σ with the peak-curvature Λ.
That figure was in units of 3√E, not of Poisson σ. Correctly: (239 − 307)/√307
= **−3.9 Poisson σ**, outside 3√E as well. So neither Λ explains the count:
the Gaussian-lobe Λ predicts too few (188) and the peak-curvature Λ too many
(307).

### 15.2 Amendment to T4, dated 2026-11-16, post hoc (written after `tsp1-noise`, before `tsp1-noise2` exists)

**Λ.** Minus the Hessian of the normalised PSF of interval 0 at its peak, by
second-order central differences over one pixel, as in
`research/results/ts-p1/diag_t4_lambda.py`. This is the Λ the Euler
characteristic formula uses.

**Pixel-grid correction.**
- Candidates are local maxima of the sampled image, not of the continuous
  field. At high u, the field near a peak of height h follows h·ρ(x − x₀)
  (the conditional mean). The highest pixel is therefore at an offset δ from
  the peak, uniform in [−½, ½]² pixels, and reads h·ρ(δ), where
  ρ(δ) = exp(−½ δᵀΛδ).
- So E_grid(u) = mean over δ of E_cont(u / ρ(δ)), on a 41 × 41 grid of δ.
  E_cont is 13.2's formula with this Λ.
- The 5σ expectation is E5 = 450 · E_grid(5); likewise at 7σ.
- The size of the correction was judged from `tsp1-noise` (≈ 1 % of peak
  height at 7-10 pixels per FWHM, which is ≈ −24 % in count at u = 5), so it is
  post hoc.

**Data.** `tsp1-noise2` (seeds 20261641-45, otherwise as `tsp1-noise`, in
13.2), drawn once after this commit. Rang's settings as in 13.2.

**Gate (unchanged):** no positive candidate ≥ 7σ_meas, and
|N5 − E5| ≤ 3√E5. The PSF depends only on UVW and weights, which equal
those of `tsp1-noise`. The `tsp1-noise` count is reported against the new
expectation as a post hoc check, not gated.

### 15.3 T1/T2c: both comparisons

The scorer reports T1 and T2c as frozen (raw) and against rang's snapshots
remade with FLAG_ROW ignored (`flag_row_ignored`).
- The raw comparison stays the verdict.
- The FLAG_ROW-ignored one is labelled as the known-difference check, with
  the same bounds.
- It is applied to `tsp1-held2`, which was already read, by rescoring with
  the frozen code plus this report.