# Rang: GeMClean multiscale on DF5-O's field, the A1 flux miss (issue #23)

Status, 2026-11-13: **measured (section 6).**

- GeMClean shares WSClean's miss: p23 fails A1, and p16 and p26 pass by under 1 µJy.
- No single large scale takes the flux.
- Scale bias 0.8 removes the miss (a post hoc reading).
- No fix.

The protocol (sections 1-5) was committed in `1d956bf` before any run.
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

## 6. Results (measured 2026-11-13)

Run root `D:\rang\outputs\u23-20261113-01`. The host is Windows, shared under
`tools/heavy_lock.py`, and gemclean runs with `-j 4`. Outputs:

- `gc/<arm>-r<N>/`: FITS, `gemclean.log` and `run.json`;
- `measures/<arm>-r<N>.json`.

The gemclean binary is built from main `30d9412`, sha256 `de1cd860…aac6`. The field copy was
checked against `field.json` before the first run and after the last (`verify-before.json` and
`verify-after.json`: ok, 59 files). gemclean is deterministic here: r1 and r2 give identical
scores. Archive: [results/multiscale-df5o-a1.json](results/multiscale-df5o-a1.json); scripts:
[results/multiscale-df5o-a1-scripts/](results/multiscale-df5o-a1-scripts/).

**Scorer reproduction (section 2): passed.** Rescoring DF5-O's `ws-multiscale` FITS reproduces
its measure files:

- per-source `ds_rel` and the total ratio differ by 0;
- inner RMS differs by 1.8e-15 (r1) and 2.9e-15 (r2) relative;
- the A1 failures are identical (r1: p16, p23, p26; r2: p23, p26).

**Matched settings.** gemclean's scale lines equal `wsclean.log`'s to the printed digits:

- bias factors 1, 3.2, 5.4, 9, 15;
- PSF peaks 1, 0.5026, 0.326273, 0.157188, 0.0511696;
- gains 0.1, 0.198966, 0.306492, 0.636181, 1.95428;
- kernel peaks equal.

Both tools stop on the threshold after 7 major cycles.

### 6.1 Step 1 (reading rule): GeMClean shares the miss

| arm | A1 failures | p16 ΔS/S | p23 ΔS/S | p26 ΔS/S | total ratio | inner RMS µJy | wall s | peak RSS MB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ws-multiscale r1 (DF5-O) | p16, p23, p26 | +0.0870 | +0.1615 | +0.0898 | 0.99966 | 1.4463 | – | – |
| ws-multiscale r2 (DF5-O) | p23, p26 | +0.0853 | +0.1615 | +0.0901 | 0.99967 | 1.4513 | – | – |
| gc-multiscale r1 = r2 | p23 | +0.0817 | +0.1591 | +0.0850 | 0.99932 | 1.4447 | 325, 240 | 3739 |
| ws-hogbom r1 = r2 (DF5-O) | none | −0.0148 | −0.0561 | −0.0123 | 0.99588 | 1.6055 | – | – |
| gc-hogbom r1 | none | −0.0149 | −0.0572 | −0.0123 | 0.99586 | 1.6041 | 44 | 2892 |

**gc-multiscale shares the miss.**

- It fails A1 on p23 only: ΔS is +13.6 µJy against a tolerance of 13.3 µJy (4.55 σ_ap).
- p16 and p26 pass by under 1 µJy:
  - p16: +20.8 against 21.7 µJy (6.94 σ_ap);
  - p26: +19.6 against 20.5 µJy (6.54 σ_ap).
- The r1 and r2 model cubes are bitwise equal (17 model FITS each).
- It is inside DF5-O 6.5's bound on every source (p16 ≤ +0.087, p23 ≤ +0.162, p26 ≤ +0.090) and
  on inner RMS (1.4447 ≤ 1.4753 µJy).
- A2 passes.
- Spurious flux outside the apertures is +2.87 / −3.37 mJy (WSClean r1: +2.86 / −3.34).

gc-hogbom meets A1, as WSClean Högbom does, so the control holds. The two Högbom runs agree to
0.0011 in ΔS/S on these three sources.

Wall time and RSS come from a shared host with 4 threads; no timing claim is made.

### 6.2 Step 3: diagnosis

| variant | change | A1 failures | p16 | p23 | p26 | median ΔS, points ≥ 20σ (µJy) | median pedestal (µJy) | inner RMS µJy | components | wall s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gc-multiscale | – | p23 | +0.082 | +0.159 | +0.085 | +16.0 | −5.7 | 1.4447 | 40443 | 325 |
| v1 | scales 0,24,48,96 | p16 | +0.088 | +0.150 | +0.087 | +14.8 | −5.7 | 1.4479 | 40982 | 420 |
| v2 | scales 0,24,48 | p23 | +0.055 | +0.189 | +0.082 | +13.5 | −4.8 | 1.4702 | 41543 | 243 |
| v3 | scale bias 0.8 | none | −0.012 | −0.040 | +0.001 | −2.5 | 0.0 | 1.4862 | 6226 | 96 |
| v4 | multiscale gain 0.1 | p23 | +0.061 | +0.174 | +0.087 | +11.4 | −5.1 | 1.4272 | 39449 | 720 |
| gc-hogbom | – | none | −0.015 | −0.057 | −0.012 | −4.2 | 0.0 | 1.6041 | 5145 | 44 |

Per-scale flux, from gemclean's scale lines:

| scale | gc-multiscale components | gc-multiscale flux (mJy) | v3 components | v3 flux (mJy) |
| --- | --- | --- | --- | --- |
| 0 px | 10883 | 77.5 | 4888 | 84.4 |
| 24 px | 21767 | 24.4 | 1182 | 6.4 |
| 48 px | 6539 | 9.2 | 129 | 6.8 |
| 96 px | 1134 | −13.2 | 27 | 2.1 |
| 192 px | 120 | +1.8 | 0 | – |

The extended sources' ΔS/S in gc-multiscale (g0, g1, g2, g3, rg) are +0.057, +0.019, −0.010,
+0.002 and +0.000. Variants v1 to v4 stay within 0.01 of these, except:

- v2: g1 +0.027;
- v3: g0 +0.035, g1 −0.001, g3 −0.006;
- v4: g1 +0.027.

No variant trades compact flux for extended flux beyond A1's tolerance.

**Frozen reading (section 5): no scale "takes the flux".**

- Removing the 192 px scale (v1) leaves the miss and moves it to p16.
- Removing the 96 and 192 px scales (v2) leaves the miss and makes p23 worse (+0.189).
- The pedestal estimate is negative in every multiscale arm (median −5 to −6 µJy), so it cannot
  account for a positive ΔS.
- v4 (sub-minor gain) leaves the miss.
- v3 (scale bias 0.8) removes it.

#### Post hoc observations (not part of the frozen rule)

**The excess is a small offset on nearly every point source.**

- 33 of the 34 point sources ≥ 20σ_ap have positive ΔS in gc-multiscale; p25 is the exception
  (−8.3 µJy).
- Sources of 0.06-0.12 mJy have +5 to +9 µJy. p23 (0.086 mJy, +13.6) and p32 (0.132 mJy, +13.2)
  are higher.
- Sources of 0.18-7 mJy have +10 to +27 µJy.
- The brightest sources do not follow this:
  - p20 (14.6 mJy): +4.3 µJy;
  - p25 (14.2 mJy): −8.3 µJy;
  - p39 (17.9 mJy): +38 µJy.
- WSClean r1 has the same pattern.

So the excess is a few µJy to a few tens of µJy per aperture and is far from proportional to S.

- p16, p23 and p26 fail because it exceeds `0.05 S + 3σ_ap` there.
- p23 has the largest offset for its flux.
- Their neighbourhood of extended emission is not needed to explain the miss.

**It points at the small scales, not a large-scale pedestal.**

- Each source has a positive excess inside r = 11.6 px and a negative model in r < d ≤ 2r.
- The surround is local. In the ring around p16, p23 and p26, the model density is −1.8e-8,
  −0.8e-8 and −2.1e-8 Jy/px. The global mean off the apertures is −4.9e-10 Jy/px, so the rings are
  16-43 times denser.
- The ring-integrated model (density × 1264 px) is −22.9, −10.2 and −26.8 µJy, against aperture
  ΔS of +20.8, +13.6 and +19.6 µJy. That is close to a cancellation: flux is moved from the
  surround into the aperture rather than added. WSClean r1 gives −26.3, −10.8 and −29.4 against
  +22.1, +13.8 and +20.7.
- When the 24 px scale's components drop from 21767 to 1182 (v3), the excess goes.
- Together these suggest the 24 and 48 px scales fit each point with a positive core and a
  negative surround.

This is not tested: gemclean does not write per-scale model images, and no run isolated the 24 px
scale.

**v3 is not a fix.**

- It trades the miss for a higher inner residual RMS: 1.4862 µJy, above DF5-O's multiscale bound
  of 1.4753 and below gc-hogbom's 1.6041.
- g0 is still +0.035.
- It is one setting on the development field. Issue step 4 needs its own frozen note and a
  held-out field.

Timings are from the shared host, with lock-queue waits excluded:

- gemclean build: 228 s compile, after about 1 h in the queue;
- scoring: 16-21 s per arm;
- field verification: 1 s;
- the runs: as in the tables.

Rows are in [tool-timings.md](tool-timings.md).

## For the coordinator

**#23 outcome.**

- GeMClean reproduces WSClean's multiscale A1 miss on DF5-O: p23 fails, and p16 and p26 pass by
  under 1 µJy.
- The result is deterministic and inside DF5-O 6.5's bound.
- The Högbom control passes.
- It is not a GeMClean port error; it is the algorithm (radler's, G5).

**Diagnosis.**

- By the frozen rule, no large scale carries the excess.
- Post hoc, there is a small positive offset on 33 of 34 points (median +16 µJy). A local negative
  ring nearly cancels it, so flux is redistributed, not added.
- `-multiscale-scale-bias 0.8` removes it, at the cost of a residual RMS above the bound.
- A fix (issue step 4) needs a frozen note and a held-out field.
