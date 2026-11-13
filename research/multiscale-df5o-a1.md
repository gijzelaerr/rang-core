# Rang: GeMClean multiscale on DF5-O's field, the A1 flux miss (issue #23)

Status, 2026-11-13: **protocol written before any run; measurement only, no fix.**
Issue [gijzelaerr/rang-core#23](https://github.com/gijzelaerr/rang-core/issues/23), steps 1-3.
Oracle and field: [df5o-deconv-oracles.md](df5o-deconv-oracles.md); GeMClean's multiscale:
[g5-multiscale.md](g5-multiscale.md).

## 1. Question

DF5-O measured WSClean 3.7 multiscale meeting A2 and failing A1 on p16, p23 and p26 (repeat 1;
repeat 2 p23 and p26), with ΔS/S +0.087, +0.162, +0.090 (repeat 1), while WSClean Högbom and pfb
Clark meet A1. GeMClean's multiscale is radler's algorithm (G5). Does GeMClean `-multiscale` on the
same field, scored the same way, fail A1 on the same sources, and by how much?

## 2. Data and oracle (frozen in DF5-O)

- Field: DF5-O's MS and truth, `outputs/df5o-20261031-01/field` (WSL `~/Github/rang`), copied to
  `D:\rang\outputs\u23-20261113-01\field`. The copy is checked against `field.json`'s per-file MS
  hashes before the first run and after the last; a mismatch stops the measurement.
- Oracle values: DF5-O's measure files (`measures/ws-multiscale-r{1,2}.json`,
  `ws-hogbom-r{1,2}.json`) and the archive `results/df5o-deconv-oracles.json`.
- **Scorer reproduction first:** the wrapper used for GeMClean rescoring `ws-multiscale-r1`'s FITS
  must reproduce its measure file's per-source `ds_rel`, total ratio and core-recomputed inner RMS
  to 1e-9 relative. Otherwise nothing is scored.

## 3. Settings

DF5-O's `ws-multiscale` argv given to gemclean (built from this branch's base, main `30d9412`,
profile `gemclean`): `-size 1024 1024 -scale 2asec -weight natural -pol I -data-column DATA
-wgridder-accuracy 1e-6 -channels-out 16 -join-channels -j 4 -no-update-model-required -nmiter 10
-niter 1000000 -gain 0.1 -mgain 0.8 -threshold 4.263913e-06 -multiscale -multiscale-scales
0,24,48,96,192 -multiscale-gain 0.2`. Differences from WSClean's argv, all forced: `-gridder
wgridder` (gemclean has only the wgridder), `-no-min-grid-resolution` and `-no-reorder` (not
gemclean options) are dropped. `-mgain 0.8` stays explicit: it selects gemclean's peak-fraction
major-cycle rule (WSClean's) instead of its default measured-stale rule. GeMClean in its default
form otherwise (f64). Evidence of matched settings: gemclean's scale lines (scale, bias factor,
PSF peak, gain) against `wsclean.log`'s.

Arms (each under `tools/heavy_lock.py run --slots 4 --mem 6`):

- `gc-multiscale` r1, r2 (reproducibility);
- `gc-hogbom` r1: the same without the three multiscale options (control: GeMClean Högbom should
  meet A1 as WSClean Högbom does).

## 4. Reading rule (frozen)

Step 1, per `gc-multiscale` repeat, from DF5-O's `tolerances` (A1: total within 2 %; every source
with `S ≥ 20σ_ap` within `0.05 S + 3σ_ap`; A2):

- **passes A1**: no A1 failure → issue step 2 (find the setting that differs from DF5-O's WSClean
  run; no diagnosis).
- **shares the miss**: A1 fails on at least one of p16, p23, p26 with ΔS > 0. Reported with ΔS/S
  and ΔS/σ_ap per source, against WSClean's two repeats, and against DF5-O 6.5's multiscale bound
  (no worse than WSClean's worse repeat: p23 ≤ +0.162, p26 ≤ +0.090, p16 ≤ +0.087).
- **fails otherwise**: any other A1 or A2 failure is reported by name.

Also reported: total model flux ratio, spurious flux outside apertures (+/−), core-recomputed
residual RMS (inner) against DF5-O's multiscale bound 1.4753 µJy, major cycles, minor iterations,
wall and peak RSS (shared host, 4 threads; no timing claim).

## 5. Diagnosis (step 3, only if GeMClean shares the miss; development field only)

One change at a time from `gc-multiscale`:

| variant | change | question |
| --- | --- | --- |
| v1 | `-multiscale-scales 0,24,48,96` | does the 192 px scale carry the excess? |
| v2 | `-multiscale-scales 0,24,48` | the 96 and 192 px scales? |
| v3 | `-multiscale-scale-bias 0.8` (default 0.6) | does a stronger small-scale preference remove it? |
| v4 | `-multiscale-gain 0.1` (default 0.2) | the sub-minor loop's gain and stop |

Not variable: radler's `-no-multiscale-fast-subminor` (gemclean refuses it, G5). Neighbouring
extended emission: from the truth, p16, p23 and p26 lie 133-170 px from the nearest Gaussian or
the radio galaxy and 37-45 px from the nearest point, so beyond every aperture but inside the
footprint of the 96 and 192 px scales.

Measures per run: the three sources' ΔS/S; per scale the component count and flux from gemclean's
scale lines; a **pedestal estimate** per source: the mean model per pixel in the annulus
`r < d ≤ 2r` around the source (pixels in other sources' apertures excluded), times the aperture's
pixel count, against ΔS. Reading: a scale "takes the flux" when removing it (v1, v2) brings the
three sources within A1 and the pedestal estimate accounts for at least half of ΔS in
`gc-multiscale`. The extended sources' (g0-g3, rg) ΔS/S are reported per variant, so a variant that
trades compact for extended flux is visible. No fix is chosen here (issue step 4 needs its own
frozen note and held-out field).

## 6. Results

Not yet measured.
