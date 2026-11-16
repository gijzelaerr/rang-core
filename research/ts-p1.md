# TS-P1: residual snapshot light curves at given positions

Issue #9 (gijzelaerr/rang-core), time series P1 of
[v1-timeseries-scope.md](v1-timeseries-scope.md). Owner approved P1 on
2026-11-13. Branch `ts-p1`. Written 2026-11-16.

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

None yet.

## 10. Measured result

Not measured yet.
