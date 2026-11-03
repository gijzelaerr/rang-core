# Rang: GeMClean's default on held-out data

Status, 2026-11-03: **measured; merged.** Archive:
[results/gemclean-heldout.json](results/gemclean-heldout.json); scripts as run:
[results/gemclean-heldout-scripts/](results/gemclean-heldout-scripts/), with
`examples/gemclean_heldout_real.py` and `examples/gemclean_heldout_archive.py`. Raw
products: `D:\rang\outputs\20261103-gemclean-heldout\`. No wall time here is a result:
the host was shared and the speed run is postponed.

The claim under test ([gemclean.md](gemclean.md)): the default stop rule
(`MeasuredStale { rho: 1, g: 0.95 }`, chosen on S1-S3) gives 4-5 major cycles at
WSClean-level false flux. GeMClean binary built at `f0ca931`; `core/src/gemclean*` is
untouched here and no constant changed.

## 1. Result

- **The claim as stated did not survive on simulation.** By the bar written before any
  held-out run (§2), cycles were **6, 6, 8, 5** on H1-H4, against 5, 5, 4 on the tuning
  skies. Three of four skies miss "at most 5". The false-flux half survives on all four.
- **What did hold on simulation:** false flux within 1.37 × the better WSClean loop,
  misfit within 0.06 % of WSClean's plain loop, and the threshold reached exactly.
  Cycles are at most those of WSClean's fast loop on every sky, and more than its plain
  loop on two (H2 6 against 5, H3 8 against 6).
- **Real data: it held at 3 mJy, on settings that were not blind.** With the same flags and
  threshold for all three, GeMClean took 5 cycles (fast 5, plain 4) on the received flags at
  3.1 σ, and 3 (fast 5, plain 4) with bad baselines flagged at 5 σ. Off-source model flux 1.03
  and 1.02 × WSClean's. No divergence and no ascending cycle. The threshold and the extra flags
  were chosen after seeing WSClean's runs. At 1 mJy, about 1.3 σ, it took 8 cycles against
  the fast loop's 6, with 1.01 × its off-source flux; that pair is unmatched, GeMClean on 256
  channels and WSClean on the native 512.
- **Measured limit:** GeMClean's peak memory (17-18 GB on about 150 M visibilities) forced
  channel averaging on the pilot: at the full 512 channels it passed 24.5 GB.

## 2. The bar (pre-registered, commit `00387b2`)

Skies H1-H4 (`examples/gemclean_bench_simulate.py --sky H*`), abs threshold 100 µJy,
Briggs 0.5, gain 0.1, `-j 16`, `examples/gemclean_bench_compare.py score`, WSClean 3.7
`nominres` plain and fast at mgain 0.8. New sky seeds 20261201-4, new noise seeds
20261211-4. MeerKAT 64 dishes, 2 h, 8 × 25 MHz, 20 µJy natural noise, as the benchmark.

- H1 dec −75, 60 points 5 mJy-1 Jy. H2 dec +10, 300 points 0.2-200 mJy, blended. H3
  dec −30, 4096 × 1.5″ (twice the benchmark's field at its sampling), 120 points 5
  mJy-1 Jy. H4 dec −45, 30 points, 6 Gaussians FWHM 20-200″, a 25-Gaussian curved tail
  of 3 Jy.
- **Survives on a sky** if GeMClean has at most 5 major cycles, at most as many as
  WSClean's fast loop, and false |flux| at most 1.6 × the lower of WSClean's two loops
  (1.53 was the worst ratio on S1-S3), with Q/Q_truth within 0.2 % of WSClean plain and
  recovery no worse by more than 0.5 %.
- **The claim survives on simulation** if it holds on every sky. Partial is reported
  sky by sky. Extended flux on H4 is compared, not barred.
- **Real data has no truth:** the same numbers in spirit (cycles, off-source flux in a
  shared mask, misfit, residual peak), and anything unlike the simulations is reported.

The wording above is the commit's, apart from layout. One reading was added afterwards:
"recovery" is evaluated flux-weighted. The mean over sources also passes on all four skies
(GeMClean − plain +0.0001, +0.0010, 0.0000, −0.0003), so the verdict is the same either way.

## 3. Simulations (measured)

Checks: the core's dirty image equals WSClean's `-niter 0` to 6.5e-8 to 2.2e-7 of the
peak; Briggs noise 23.1-23.3 µJy; each MS unchanged by the runs (SHA-256 before and after).

| sky | imager | majors | comps | false px | false \|flux\| mJy | inner peak µJy | Q/Q_truth | recovery (flux-weighted) | flux err mJy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H1 | **GeMClean** | **6** | 88,533 | 114 | **1.43** | 100.0 | 1.01417 | 0.9957 | +0.82 |
| H1 | WSClean fast | 9 | 84,473 | 81 | 1.04 | 204.7 | 1.01471 | 0.9959 | +0.95 |
| H1 | WSClean plain | 6 | ≥ 87,000 | 117 | 1.47 | 114.5 | 1.01437 | 0.9956 | +0.94 |
| H2 | **GeMClean** | **6** | 54,670 | 408 | **6.16** | 99.9 | 1.00998 | 0.9987 | −5.30 |
| H2 | WSClean fast | 6 | 52,377 | 428 | 7.04 | 229.3 | 1.01058 | 0.9988 | −6.01 |
| H2 | WSClean plain | 5 | ≥ 54,000 | 562 | 8.87 | 116.6 | 1.00996 | 0.9986 | −5.70 |
| H3 | **GeMClean** | **8** | 163,497 | 705 | **11.84** | 100.0 | 1.02536 | 0.9998 | +2.08 |
| H3 | WSClean fast | 9 | 157,539 | 610 | 8.79 | 316.5 | 1.02605 | 0.9995 | +2.90 |
| H3 | WSClean plain | 6 | ≥ 164,000 | 1,577 | 23.46 | 121.8 | 1.02531 | 0.9998 | +1.26 |
| H4 | **GeMClean** | **5** | 55,685 | 406 | **5.33** | 100.0 | 1.00337 | 0.8073 | −252 |
| H4 | WSClean fast | 6 | 54,394 | 487 | 7.94 | 171.6 | 1.00308 | 0.8074 | −262 |
| H4 | WSClean plain | 5 | ≥ 57,000 | 2,064 | 33.15 | 118.3 | 1.00278 | 0.8073 | −264 |

"≥" is the last iteration logged by WSClean's plain loop, which reports no total.

| sky | at most 5 cycles | at most fast's | false ratio (bar 1.6) | Q over plain (bar +0.2 %) | recovery (bar −0.5 %) | survives |
| --- | --- | --- | ---: | ---: | ---: | --- |
| H1 | **no (6)** | yes | 1.37 | −0.02 % | +0.01 % | **no** |
| H2 | **no (6)** | yes (tie) | 0.87 | +0.00 % | +0.01 % | **no** |
| H3 | **no (8)** | yes | 1.35 | +0.00 % | 0.00 % | **no** |
| H4 | yes | yes | 0.67 | +0.06 % | −0.01 % | yes |

H4's recovery of 0.81 is the scorer's reading: points inside a Gaussian's 2-FWHM region
are not counted as recovered, for any imager. Flux inside those regions: GeMClean 6.179,
fast 6.171, plain 6.173 Jy, against 6.099 Jy of Gaussians (the excess is those points).

**Why the count rose (post hoc, not part of the bar).** Components and starting peak per cycle:

| sky | cycles |
| --- | --- |
| H1 | 663 / 840 mJy, 6,041 / 43 mJy, 27,352 / 1.28 mJy, 53,501 / 275 µJy, 959 / 112 µJy, 17 / 100.0 µJy |
| H2 | 2,222 / 195 mJy, 5,966 / 10.9 mJy, 22,819 / 951 µJy, 23,055 / 187 µJy, 573 / 106 µJy, 35 / 100.0 µJy |
| H3 | 964 / 981 mJy, 6,280 / 51 mJy, 31,852 / 2.14 mJy, 103,887 / 446 µJy, 19,824 / 138 µJy, 648 / 103 µJy, 41 / 100.0 µJy, 1 / 100.0 µJy |
| H4 | 884 / 269 mJy, 9,530 / 13.8 mJy, 44,555 / 1.31 mJy, 709 / 111 µJy, 7 / 100.0 µJy |

The last cycles only reach the threshold exactly and hold about 1 % of the components. To the
level where WSClean's plain loop stops (114.5, 116.6, 121.8, 118.3 µJy), GeMClean needs
**4, 4, 5, 3 cycles against plain's 6, 5, 6, 5**. That is a reading after seeing the data and
it does not rescue the bar: the benchmark's 5, 5, 4 also count those last cycles, and the
bar was set on them. A rule that stops at "close enough" would be a new proposal needing its
own held-out test. Stale errors fall with every cycle, no cycle ascends, and the largest
relative gap, 7.3e-4, is on the widest field (H3).

## 4. Pilot to a Measurement Set (measured)

- **Source.** `ms1_target.zarr`, MAIN_0, scan 2: 850,950 rows, 61 antennas, 450 dumps of
  8 s, channels 640:1152 (989.75-1096.54 MHz, 208.98 kHz), XX, XY, YX, YY. Numeric chunks only;
  no pickle decoded; `python -I`, scripts outside the data directory. String subtable columns
  are replaced by `ANT00`-style names. Provenance: `manifest.json` beside the data, copied to
  [results/gemclean-heldout-pilot-manifest.json](results/gemclean-heldout-pilot-manifest.json).
- **What comes from the source:** main-table columns, antenna positions, dish diameters,
  frequencies, channel widths, PHASE_DIR. **Made up, simulator defaults:** antenna names and
  mounts, FEED (receptors, angles), field name, OBSERVATION text. POLARIZATION is XX, XY, YX,
  YY, matching the store's CORR_TYPE. These subtables do not affect the Stokes I imaging here.
- **Writer change.** Rang's writer refused tile files of 2 GiB or more. `TsmHeader` now
  writes casacore's version-2 `TSMFile` and `TSMCube` records from 2 GiB, with a unit test.
- **Checks on `raw.ms` (20 GB).** All 850,950 rows identical to the Zarr in UVW, TIME,
  antennas, DATA, FLAG, WEIGHT_SPECTRUM through rang's reader; no non-finite cell.
  **python-casacore** reads rows 0, 410,000, 700,000, 849,999, 850,949 identical to the
  Zarr, which covers offsets beyond 2 GiB. **WSClean** images it: 303,028,947 visibilities.
- **Flagged fraction.** 30.4 % of all cells, 28.1 % of cross-correlations.
- Pitfall: a Zarr chunk is stored full size, so the last row chunk carries 49,050 fill rows,
  which the first conversion tried to write past the end of the table. `rows_in_chunk` clips it.

## 5. Calibration (measured)

**State of DATA:** uncalibrated. **Route:** apply the publisher's own QuartiCal net gain,
`ms1_gains.qc/GKB-net/GKB-net_0`, per 8 s, per channel, per antenna, per hand, matching the
pilot's channels to 0 Hz and its times to 0 s. **Why:** 545 MB (within the 3 GB allowance,
SHA-256 per object in
[results/gemclean-heldout-gains-manifest.json](results/gemclean-heldout-gains-manifest.json)),
it is the cheapest sound route, and no imager's model enters. So no self-calibration was run.

V_corrected = V / (g_p g_q*), weight × |g_p g_q|², XX and YY only:

| measure (row chunks 0 / 8) | raw | corrected | other conjugate |
| --- | ---: | ---: | ---: |
| XX−YY phase, median \|rad\| | 1.51 / 1.52 | **0.17 / 0.17** | 1.15 / 1.16 |
| Stokes I coherence over 32 channels | 0.967 / 0.963 | **0.991 / 0.991** | 0.981 / 0.977 |
| vector mean, baselines under 300 m, Jy | 0.55 / 0.41 | **6.91 / 6.58** | 2.21 / 1.61 |
| dirty peak, Jy/beam (4096 × 3″, Briggs 0.5) | 0.051 | **1.197** | – |
| dirty peak / whole-image MAD | 30 | **318** | – |

**Limits.** There is no independent flux check: the primary was not fetched, so the scale is
the gains' own and "model flux" is not validated. The gains come from a self-calibration
whose model is not public, so absolute positions and the sky model behind them are
inherited. The gains' field name is `ESO137-001`; the store's PHASE_DIR is 16h15m11.0s,
−60°54′21″, 51″ in RA from the documented target, and the peak lies about 7″ from the phase
centre; this does not affect a comparison between imagers. No direction-dependent solution
and no polarisation calibration. Gain flags added 0.012 % of the cells.

**Noise floor.** Channel differences give 0.238 Jy per part per visibility, so a thermal
Stokes I image noise of about 15.5 µJy for 1 h at Briggs 0.5. The off-source floor is about
1 mJy, 60 × that. Diagnostic at 3 mJy: baselines under 400 m hold 3.75 % of the weight and
63 % of Q. A few sit 40-200 × the median short-baseline misfit, steady in time, antenna 1 most
often. A per-channel flux scale removes only 2.8 % of it (the ratio does follow α ≈ −1, as
a single-term model over 10 % bandwidth must). The cause was not established.

Hence two data sets, both given identically to all three imagers:

- **A, received flags.** Calibrated, averaged 2× in frequency (below): 27.8 % flagged.
- **B, extra flags.** A plus 145 of 1,830 baselines whose misfit exceeds 5 × the median of
  their length bin against WSClean plain's A model (`badbaselines`). 3.35 % of the weight, 54 %
  of the misfit. 32.4 % flagged. The model is WSClean's, a small bias in its favour; the
  flags are the same for all. This pass was added after seeing A.

## 6. Real-data comparison (measured)

**Settings.** 4096 × 3″ = 3.41°: PSF 16.9″ × 9.6″ PA 128°, so 3.2 pixels across the minor axis;
main lobe to about the first null (radius 1.79° at 1043 MHz, FWHM 1.41°, katbeam
`MKAT-AA-L-JIM-2020`). Briggs 0.5, gain 0.1, Stokes I, one flat-spectrum term, no mask for
anyone, `-j 16`. WSClean `nominres`, mgain 0.8, GeMClean's default rule. Threshold 3 mJy
for the primary runs; fast at 1 mJy had shown 430,000 components, −35 Jy of model flux and a
residual MAD of 0.75 mJy, so cleaning into the noise.

**Averaging.** GeMClean on all 512 channels (303 M active visibilities, 4096²) passed 24.5 GB
RSS within about 50 s of its start and was stopped by my watchdog. So both imagers got 256 channels of
0.418 MHz (152.2 M active on A; smearing β about 0.26 at 1.78°). Weighted mean, flagged only
when both are. The scorer's dirty image equals WSClean's to 6.6e-8 of the peak, WSCNVIS equal,
WSCIMGWG to 3e-13; `exact_vs_imager_residual` 5e-8 to 8e-8 Jy, so weights and flags agree.
The exception is the WSClean fast job at 1 mJy, 1.25e-4 Jy, because it saw the native channels.

Scored through one gridder (ε 1e-7): Q = ½ Σw|V − Am|²/Σw, Q0 12.1526 (A), 9.6555 (B) Jy².
The source mask is the same for all: mean of the three common-beam (12.7″) images above 5 σ,
dilated by 2 beams; "off-source" residuals inside the inner two-thirds, model flux anywhere.

| set, threshold (σ) | imager | majors | comps | Q/Q0 | inner peak mJy | off-source rms mJy | off-source \|model\| Jy (px) | model flux Jy | negative Jy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B, 3 mJy (5.0) | **GeMClean** | **3** | 38,709 | 1.4845e-2 | 3.000 | 0.6972 | **1.998** (4,115) | 82.705 | −2.807 |
| B | WSClean fast | 5 | 38,302 | 1.4878e-2 | 3.096 | 0.6984 | 1.964 (4,023) | 82.665 | −2.767 |
| B | WSClean plain | 4 | ≥ 38,000 | 1.4877e-2 | 3.037 | 0.6984 | 1.963 (3,988) | 82.663 | −2.765 |
| A, 3 mJy (3.1) | **GeMClean** | **5** | 58,314 | 2.4207e-2 | 3.000 | 1.0568 | **8.567** (19,698) | 83.773 | −7.391 |
| A | WSClean fast | 5 | 57,233 | 2.4284e-2 | 3.584 | 1.0602 | 8.337 (19,008) | 83.701 | −7.256 |
| A | WSClean plain | 4 | ≥ 57,000 | 2.4280e-2 | 3.093 | 1.0600 | 8.350 (19,082) | 83.719 | −7.256 |
| A, 1 mJy (1.3) | **GeMClean** | **8** | 441,893 | 1.6712e-2 | 1.000 | 0.5995 | **57.56** (327,504) | 85.764 | −35.506 |
| A | WSClean fast, native channels | 6 | 432,895 | 1.6781e-2 | 1.171 | 0.6065 | 56.80 (321,232) | 85.585 | −35.144 |

σ is the inner residual MAD on that set: 0.60 (B), 0.96 and 0.75 mJy (A). WSClean's plain
loop was not run at 1 mJy (hours of the shared lock), and its fast job there saw 512 channels
and is rescored on the averaged data. Off-source model flux is nearly all negative (1.997 of
1.998 Jy on B, all imagers): a negative bowl around the source, not the balanced scatter of
the simulations. So it is an imperfect stand-in for false flux.

**Compact sources** (isolated peaks above 10 σ in the mean image, flux inside 1.5 beams, model
plus residual over the beam area), ratio to GeMClean, median (robust scatter):

| set | n | fast / GeMClean | plain / GeMClean | brighter half, fast; plain |
| --- | ---: | ---: | ---: | --- |
| B | 72 | 1.0000 (0.24 %) | 1.0003 (0.29 %) | 1.0004 (0.14 %); 1.0006 (0.09 %) |
| A | 43 | 1.0009 (0.31 %) | 1.0006 (0.27 %) | 1.0009 (0.19 %); 1.0010 (0.20 %) |

The images differ little: GeMClean − plain on B has an rms of 19 µJy, 3 % of the floor, and
peaks at 3.95 mJy.

**Unlike the simulations.**
- 3 cycles on B against 5-8 on simulated skies: the second cycle runs to the threshold,
  because the stale error after cycle 1 is only about 1 mJy against a 55 mJy peak.
- On A at 3 mJy, cycles 4 and 5 hold 8 and 4 components; at 1 mJy the last three of 8 hold 28,
  9 and 1. Exact stopping costs cycles here too.
- The floor is far above thermal, and all three clean the same rings and bowl. GeMClean's lower
  misfit (0.2-0.4 %) goes with its lower residual peak, not a demonstrably better sky.
- No divergence, no ascending major cycle (0 on all three runs), largest relative gap
  7.9e-4 (1 mJy). The gap and stale-error record behaves as in simulation.

**Appearance.** Against the abstract of Ramatsoku et al. 2020 (rms about 0.02 mJy/beam at about
10″; collimated threads linking extended, bent lobes; the most prominent about 80 kpc long,
about 4′ at the cluster's distance, and about 1 kpc wide, about 3″). Here: a core with two
jets feeding bent lobes, 79.9 Jy above 6 mJy over 16′ on set B, with thin filaments near and
between the lobes. The bent-lobe morphology agrees. **The threads are not established:** at
12.7″ and a floor 30 × the paper's rms, a 3″ thread is unresolved and a filament here could
be an artefact. Visual reading, not a measurement. A second structure lies 15.6′ north, 10′
long, 5.1 Jy, peak 219 mJy (measured on the same image). Elliptical rings about 5′ apart fill
the field at a few tenths of a mJy on B in all three imagers. Images: `real/gem-zoom.png`,
`real/gem-vs-plain.png`, `real/images3/`, `real/images/` under the output directory.

## 7. What is not comparable

- Restoring beams differ (GeMClean 15.4″ × 9.4″, WSClean 16.9″ × 9.6″); the comparison uses
  models, exact residuals and one common beam.
- The threshold and set B were chosen after seeing WSClean's runs on these data: matched, not blind.
- At 1 mJy, GeMClean had the 256-channel set and WSClean fast the native 512 channels, and
  WSClean plain did not run. Cycles and off-source flux there are not a matched pair.
- WSClean's `-mgain` is a peak fraction per cycle; GeMClean's first cycle is `g` 0.95 and
  later ones its stale rule. Cycles measure different hand-backs, by design.
- A single 1 h scan at 107 MHz near the Galactic plane, one flat-spectrum term, no truth. No
  `-channels-out`, no multiscale, which an astronomer would use on this source.
- No speed claim.

## 8. The full 7-hour track (proposed, not fetched)

- **Download:** about 126 GB for the same tiles of all 7 MAIN groups plus 3.8 GB of GKB-net
  gains; D: has 1.9 TB. MS: about 140 GB raw, 70 GB calibrated at 512 channels.
- **GeMClean memory, estimated, not measured:** 18.03 GB at 152.2 M active visibilities, 17.12 GB
  at 142.5 M (A and B, 4096²), so about 96 B per active visibility above about 3.8 GB, which
  also fits the native run's overflow (about 33 GB at 303 M). At 7 h: about 106 GB at 2× in
  frequency, 55 GB at 4×, 29 GB at 8×, 17 GB at 16×. A 24 GB budget needs about 10× (2.1 MHz,
  smearing β about 1.3 at the field edge), so the honest route is a host with about 110 GB.
  Two close points only: rough.
- **WSClean:** bounded by `-abs-mem`.
- **Calibration:** the same gains, per scan; the bad-baseline rule would need rechecking per scan.

## 9. Reproduction and tooling

`research/results/gemclean-heldout-scripts/` holds the drivers as run (`sims.sh`, `sims2.sh`,
`simscore.sh`, `conv.sh`, `gain.sh`, `cal.sh`, `avg.sh`, `real1.sh`, `real2.sh`, `bad.sh`,
`b.sh`, `realscore.sh`, the fetch and diagnostic scripts). Their paths are this host's;
the code they call is `examples/gemclean_heldout_real.py` (`convert`, `verify`, `gainload`,
`gaincheck`, `calibrate`, `average`, `prep`, `dirtycheck`, `badbaselines`, `score`, `compare`).
The binary is `sim/gemclean-f0ca931` on D:. Timings: [tool-timings.md](tool-timings.md).
