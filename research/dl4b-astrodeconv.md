# DL4b step 0: ASTRODECONV2019 regenerated (rang, route b)

Issue #42, data half of step 0. Branch `dl4b-astrodeconv` from main `2ea3bf71` plus `origin/dl0-profile`.
**Status at freeze (2026-11-19): proposed; nothing generated, no script written.** Results go under
"Measured result"; nothing above it changes except by dated, labelled amendment.

Purpose (`dl-plan.md` 1.1): a fixed benchmark for stage 7, the thesis's Vacuum Cleaner data, so that the
one-pass score can be reproduced and the iterated form measured on the same fields. This note covers
only generation. **No training here**; the benchmarks run later on glacier's GPU, after F5.

Specification source: `dl0-profile.md` 1.6 (route b) and the owner's decision of 2026-11-19, verbatim:
"go with all three flux sets, seeds 0-2999". **9,000 fields** = 3 flux sets × seeds 0-2999.

**Unresolved, carried, not fixed:** the thesis gives "10 000 image products" (p. 92) and a
94,000 / 3,000 / 3,000 split (p. 93). The published spiel job files hold 3,000 fields (1,000 seeds per
flux set). Which seeds made the published set is not recoverable. This note fixes what rang
regenerates, not what the thesis meant.

## 1. Specification per job file

Source: [spiel](https://github.com/gijzelaerr/spiel) commit `c4a8e315ae65176dda4871fabd1c241904ef5232`
(MIT, the owner's). `jobs/meerkat16_oleg_flux{10,100,1000}.yaml` differ only in `flux_scale_min/max`
(10, 100, 1000) and `random_seeds` (0-999, 1000-1999, 2000-2999). This was checked by `diff`.

| Input | Value | Used by |
| --- | --- | --- |
| `nant` | 16 | skymodel (Srms) |
| antennas | `data/MeerKAT16_ANTENNAS`: m000 m002 m005 m011 m012 m018 m020 m042 m049 m057-m063, 13.5 m, ALT-AZ | track |
| `dtime` | 10 s | track, Srms, noise |
| `freq0` | 1,049,833,007.8125 Hz, `nchan` 1 | channel centre |
| `ra` | 63.36° | phase centre, sky |
| `dec_min`, `dec_max` | −55, −65 (passed to `uniform` in that order) | randomize |
| `synthesis_min/max` | 7.5, 8 h | randomize |
| `dfreq_min/max` | 200e6, 300e6 Hz | randomize |
| `flux_scale_min = max` | 10, 100 or 1000 | randomize |
| `nsrc`, `pb_fwhm` | 100, 0.25° | skymodel |
| `sefd` | 520 Jy | skymodel, noise |
| `gain_errors` | 0; `[sim]` profile: no E (beam), no P, no smearing, Tigger LSM only | simulate |
| imaging | 256² at 1.6″, `-weight uniform -niter 100000000 -mgain 1.0 -auto-threshold 0.125 -auto-mask 5 -make-psf`, `-data-column DATA` | WSClean |
| big PSF | 512² at 1.6″, `-make-psf-only` (`steps/bigpsf.cwl`) | WSClean |
| sky image | `tigger-restore -b 0 --clear dirty.fits skymodel.txt` | truth |

### 1.1 Draws (port of `steps/randomize.cwl` and `steps/skymodel.cwl`, unchanged, draw order kept)

These use numpy's legacy global `RandomState`.

`randomize`, per seed s and flux set f:

- `seed(s)`
- `dec = uniform(−55, −65)`
- `synthesis = uniform(7.5, 8)`
- `dfreq = int(uniform(200e6, 300e6))`
- `flux_scale = uniform(f, f)`

`skymodel`:

- `Srms = 520 / sqrt(2·10·dfreq·16·15/2)`
- `noise = sqrt(2·Srms)`
- `seed(s)` again
- `fluxes = pareto(8, 100)·noise·flux_scale`
- `ras = 63.36 − randn(100)·0.125`
- `decs = dec − randn(100)·0.125`
- `spi = −0.7 + randn(100)·0.01`

Each source is written as a line `src%04d {ra:.5g} {dec:.5g} {flux:.3g} {freq0:.5g} {spi:.3f}`.

Consequences, read from the code:

- **The truth is the text file, not the draws.** MeqTrees and tigger-restore read `skymodel.txt`.
  - Positions are rounded to 0.001° (3.6″ in Dec, 1.8″ on the sky in RA at δ −60°), which is more than one 1.6″ pixel.
  - Fluxes are rounded to 3 significant figures.
  - The spectral reference is `1.0498e+09` (`%.5g`). At `freq0` the spectral factor is (1,049.833/1,049.8)^spi ≈ 1 − 2.2e-5.
  - rang simulates and pixelises from the parsed text.
- **Most sources are outside the image.** The 256² image is 0.114° wide.
  - σ is 0.125° in Dec and 0.125° of RA coordinate. With no cos δ, that is about 0.0625° on the sky.
  - Expected number inside is about 100 × P(|ΔRA·cosδ| < 0.057°) × P(|ΔDec| < 0.057°) ≈ 100 × 0.64 × 0.35 ≈ 20 (inferred).
  - All 100 sources are predicted; only the in-image ones enter the truth image. `n_inside` is recorded per field.
- **Shared seeds.** For one seed, all three flux sets draw the same dec, synthesis, dfreq, positions, spectral indices and Pareto shape (`flux_scale` is drawn but constant).
  - So the three are one sky at three flux scales.
  - uvw and the PSF are identical across the three; only the noise realisation differs.
  - **Splits are by seed** (section 4).

### 1.2 Observation (rang, route b)

- **Antennas.** Spiel's 16 positions (`data/MeerKAT16_ANTENNAS`, read with rang's table reader).
  - Measured 2026-11-19 against `data/meerkat.itrf.txt`: a common shift of (19.01, 7.51, −12.15) m, 23.8 m in all.
  - After the shift the positions agree to ≤ 0.16 m, and baseline vectors to ≤ 0.25 m (longest baseline 7,698 m).
  - Spiel's positions are used, embedded in the script.
- **Track.** One scan of `n = floor(synthesis·3600/10)` dumps of 10 s, centred on transit of (63.36°, dec).
  - simms (ratt-ru/simms `casasm.py`, current `e715505`): with no `--date` it uses today's date and `usehourangle=True`, and starts at −(scan length)/2. So the scan is centred on transit.
  - That KERN-3's 2018 simms did the same is inferred.
  - The date is fixed at MJD 61120 (2026-03-21). With transit centring it only matters through precession, which is not modelled.
  - uvw is computed as in `examples/simulate_df5_field.py` (`track`, GMST 1982, J2000 = date). No elevation limit: dec −55° to −65° at latitude −30.7° stays above 24° for ±4 h (inferred).
- **Channel and correlations.** One channel of width `dfreq`, centred at `freq0`. CASA `sm.setspwindow(freq=…)` gives the first channel's centre (inferred). Correlations XX, XY, YX, YY.
- **Prediction.** Exact, using the core DFT (`core.predict_components`) for 100 point sources at the parsed (ra, dec).
  - (l, m) come from `rang.formats.sky.direction_cosines`.
  - Flux at `freq0` is I·(freq0/1.0498e9)^spi.
  - XX = YY = I, XY = YX = 0 (unpolarised; MeqTrees' XX = I + Q convention).
  - No beam, no smearing, no gains, no w-term approximation (the DFT is exact).
- **Noise.** Complex Gaussian on every visibility and correlation, σ = 520/sqrt(2·10·dfreq) per real and imaginary part. This is spiel's `noise_stddev`; that MeqTrees' `GaussNoise` applies it per part is inferred.
  - Seeded per (s, f): `numpy.random.Generator(PCG64(SeedSequence([20261119, s, f])))`. Spiel's noise was unseeded (`random_seed = time`).
  - `WEIGHT_SPECTRUM` = 1/σ², `SIGMA` = σ, no flags.
- **MS.** Written by `rang.core_ms_write`, one per seed, with three data columns (`DATA_F10`, `DATA_F100`, `DATA_F1000`, imaged with `-data-column`). It lives in `/dev/shm` with the WSClean temp dir and is deleted after the seed.

### 1.3 Imaging

WSClean 3.7 (2026-02-16), the native `/usr/bin/wsclean` on nash. This is the same version as `rang-wsclean-native_3.7.sif`. Every call uses `-j 1`.

| Run | Settings | Products kept |
| --- | --- | --- |
| A, spiel | §1 settings, `-mgain 1.0` (one major cycle: the thesis's comparator, p. 93) | dirty, model, residual, image, psf; clean beam |
| B, full | as A but `-mgain 0.8` (WSClean default `-nmiter` 20) | model, residual, image; major cycles |
| P | 512², `-make-psf-only` (once per seed) | big PSF |

- Per field there are 6 calls: 3 flux sets × (A, B). Per seed there is 1 P call.
- The 256² PSF comes from A on `F10`. It is identical across flux sets (same uvw and weights); the pilot checks this.
- Timeout: 900 s per call. Iterations reached, major cycles, wall time and a timeout flag are recorded as outcomes, not dropped.
- Spiel's thesis comparator was 2019 WSClean. The version difference is recorded and not corrected.

### 1.4 Truth image (spiel's `tigger-restore -b 0 --clear`)

- Read from Tigger `Imaging.restoreSources` (ratt-ru/tigger-lsm, current `11131be`).
- With beam 0 each point source goes to pixel `int(round(x)), int(round(y))`, using the image's WCS (Tigger's `FITSWCSpix`, origin 0). Sources outside the image are skipped. Flux is added (`+=`), so two sources in one pixel sum.
- Spectral normalisation is at the model's reference frequency, so the value is the printed I.
- rang reproduces this with run A's dirty-image header: astropy-free SIN projection about (63.36°, dec), checked against the header on the pilot.

## 2. Identity check (before generation; stop and report if it fails)

1. Extract the Python text of `steps/randomize.cwl` and `steps/skymodel.cwl` (`valueFrom`) verbatim.
   - Substitute `$(inputs.X)` with the job values (Python `repr`, equal to JS shortest round-trip for these numbers).
   - Change `xrange` to `range` and `\\n` to `\n` (the CWL escape).
   - Run each in a subprocess in a fresh temp dir.
2. Run rang's port, `examples/astrodeconv_sim.py` functions `randomize` and `skymodel_text`, for the same inputs.
3. Inputs: seeds 0, 1, 2999 × flux sets 10, 100, 1000 (9 cases).
4. **Pass**, for all 9 cases:
   - randomize's JSON (dec, synthesis, dfreq, flux_scale) is equal as floats;
   - the `skymodel.txt` bytes are equal.
5. Record numpy's version. Also run spiel's snippet under the oldest numpy available on public PyPI for Python 3.8 (1.17.x, if `uv` can resolve it) as a cross-version check.
   - Limit stated now: both sides run in the same process family. This proves the port, not 2019 parity.
   - The legacy stream's stability is NumPy's policy (NEP 19), cited, not measured beyond that one older version.

## 3. Outputs per field (seed s, flux set f)

| Product | Shape, dtype | Note |
| --- | --- | --- |
| `dirty` | 256², float32 | run A's `-dirty` |
| `truth` | 256², float32 | §1.4 |
| `model_a`, `residual_a`, `image_a` | 256², float32 | run A |
| `model_b`, `residual_b`, `image_b` | 256², float32 | run B |
| components | 100 rows: ra, dec, I, spi, x, y, inside | text values |
| scalars | dec, synthesis, dfreq, n_dump, σ_vis, n_inside, flux_inside, clean beams A/B, iterations and major cycles A/B, wall s, timeouts | manifest |

Per seed: `psf` (256², float32), `bigpsf` (512², float32) and one FITS header of each kind (WCS) in the shard JSON. Size is about 1.8 MB per field plus 1.3 MB per seed, about 20 GB in all.

## 4. Split (fixed here, by seed)

- `perm = numpy.random.default_rng(20261119).permutation(3000)`.
- Train = `perm[:2820]`, validation = `perm[2820:2910]`, test = `perm[2910:]`. These are the thesis's 94/3/3 proportions.
- All three flux sets of a seed share its split.
- The split file (seed, split) is written before generation. Its SHA-256 goes in the measured result, and every field's row carries its split.
- A column `published` marks the as-published subset: flux10 seeds 0-999, flux100 seeds 1000-1999, flux1000 seeds 2000-2999. That gives 3,000 fields with the published (seed, flux) pairs, though not the published images.

## 5. Shards, manifest, resumability

- **Shards.** Shard k holds seeds 10k to 10k+9, that is 30 fields. There are 300 shards.
  - Each is written by one worker to `shard-KKK.npz.tmp`, then renamed. `shard-KKK.json` holds the scalars, headers and per-field SHA-256. `shard-KKK.done` holds the npz's SHA-256 and is written last.
  - A rerun skips a shard whose `.done` matches its npz's hash, and redoes it otherwise.
  - One shard is about 5-10 min of one core (estimate), so a kill loses less than 15 min per worker.
- **Field hash.** SHA-256 over the field's arrays (`dirty`, `truth`, `model_a`, `residual_a`, `image_a`, `model_b`, `residual_b`, `image_b`, in that order, C-contiguous float32 bytes). Each seed's `psf` and `bigpsf` are hashed the same way.
- **Manifest.** `manifest.csv` has one row per field: field id `s{seed:04d}-f{flux}`, seed, flux, split, published, shard, the scalars of §3, the field SHA-256 and the seed's PSF SHA-256. Its own SHA-256 is recorded here. The compact archive is `research/results/dl4b-astrodeconv/`: manifest, split file, identity-check output, a few PNGs, timings.
- **Host.** nash, under `tools/heavy_lock.py` (main checkout copy) at `nice -n 19 ionice -c3`, with `RAYON_NUM_THREADS=OMP_NUM_THREADS=1` per worker.
  - Run root: `~/rang-data/outputs/dl4b-astrodeconv-20261119/`.
  - MS and WSClean temp files go in `/dev/shm`. Only shard files reach disk.
  - Booking: 14 slots (what is free at freeze; 16 if free at start), `--mem` 32 GB (workers plus shm).

## 6. Pilot and acceptance (before the 9,000)

- **Pilot.** Shard 0 (seeds 0-9, 30 fields), timed. Accept and go on only if all of these hold:
  1. **Orientation.** On flux1000 seeds, the brightest in-image source's dirty-image peak lies within 1 pixel of its truth pixel, for every pilot seed that has an in-image source.
  2. **Flux.** For the same source, the model_b flux summed in a 3×3 box is within 10 % of its I. Neighbours within 5″ are excluded from the test.
  3. **PSF.** It is identical (max |Δ| < 1e-6 of peak) across the three flux sets of one seed.
  4. **Noise.** For each pilot seed, the residual_b RMS of flux10 is within 20 % of the RMS of a noise-only dirty image. That image comes from the same seed's uvw and weights, with an extra pilot-only column `DATA_NOISE` (sky-free, noise rule seeded with f = 0). This is a sanity bound, not a claim.
  5. **Time.** No timeout, or the timeout share is stated and the run continues with it recorded.
- A failure of 1-3 stops the run and is reported. Item 4 out of bound is reported and investigated before generation.
- **Rerun idempotence.** Shard 0 is regenerated once more, and the field hashes must be equal. This needs WSClean to be deterministic at `-j 1`; a difference is recorded, not hidden.

## Amendment 1, 2026-11-19 (after a one-seed smoke test, before the pilot; post hoc, labelled)

**Smoke test.** Seed 0, three flux sets, on nash, `logs/smoke.log`.

What was seen:

- Identity check on nash: PASS, numpy 2.5.5. On glacier: PASS with numpy 2.5.4 and 1.17.5 (`research/results/dl4b-astrodeconv/identity*.json`).
- Seed 0: n_inside 25, PSF identical across flux sets (max Δ 0), clean beam 6.23″ × 4.75″ at PA 149°.
- Noise-only dirty RMS was 1.8e-5 Jy. The flux10 `residual_b` peak was 34 mJy, about 16 % of the dirty peak, at every flux scale.
  - spiel's flux unit `noise = sqrt(2·Srms)` is 0.036 Jy here, against 6.6e-4 Jy for Srms. So sources are about 10³ times the image noise even at flux10.
  - 75 of the 100 sources lie outside the 256² image, where WSClean cannot clean them.
  - The residual is sidelobe-limited by spiel's design, not noise-limited. Criterion 6.4 as frozen cannot hold.
- Run A (`-mgain 1.0`) performed **2** major iterations, not 1: WSClean starts a second one when the auto-mask threshold is reached. Recorded per field as `major_a`.
- WSClean took 22 s per inversion for 340k rows and one channel. With spiel's settings a seed took 267 s.

Changes (none alters a draw, the truth or the imaging settings):

1. **MS storage.** Fixed-shape `FLAG`, `WEIGHT` and `SIGMA`, and `TiledColumnStMan` for the data and spectrum columns, as `examples/c5_selfcal_sim.py` does. The indirect StandardStMan arrays made casacore's row reads slow: inversion went from 22 s to 4.7 s.
2. **`-reorder`** on every WSClean call. One run-A call went from 7.3 s to 1.9 s. Reordering was WSClean's default in 2019 (inferred), so this is closer to spiel, not further.
3. **Criterion 6.4 replaced.** The flux10 `residual_b` RMS must be within 20 % of sqrt(noise² + outside²).
   - noise is the RMS of the noise-only dirty image (`DATA_NOISE`).
   - outside is the RMS of the noise-free dirty image of the out-of-image flux10 sources (`DATA_OUTSIDE`, pilot only; in or out decided on WSClean's grid, centre pixel n/2).
   - This tests that what WSClean leaves is the out-of-field sidelobes plus noise.
4. **Criterion 6.1 made concrete.** The peak is the dirty-image maximum in an 11×11 box around the truth pixel.
5. **Code.** The acceptance checks are `examples/astrodeconv_sim.py pilot-check`.

## Pilot result (shard 0, seeds 0-9, 2026-11-19, nash)

Run root `~/rang-data/outputs/dl4b-astrodeconv-20261119/pilot-a` and `pilot-b`. Checks are in
`results/dl4b-astrodeconv/pilot-check-000.json`.

| Criterion | Result |
| --- | --- |
| 6.1 orientation | PASS, 10/10, offsets 0 px (9) and 1 px (1) |
| **6.2 flux, as frozen** | **FAIL, 2/10**: model_b 3×3 sum against I is +1.7, +7.9, +3.2, −0.9, **+12.6**, +4.5, +5.3, +9.0, +5.4, **+11.9** % (seeds 0-9) |
| 6.3 PSF | PASS, 10/10, max Δ 0 across flux sets |
| 6.4 residual (amendment 1) | PASS, 10/10, ratio 1.00-1.04: the residual RMS is the out-of-field sidelobes (4.6-6.9 mJy at flux10) plus noise (1.7-2.1e-5 Jy) |
| 6.5 time | PASS, 0 timeouts. 306 s per shard on one core (30 s per seed, pilot extras included); peak RSS 0.32 GB |
| rerun | PASS: pilot-b reproduces all 30 field and 10 PSF hashes of pilot-a |

**The frozen stop fired (6.2). Generation has not started.**

## Amendment 2, 2026-11-19 (proposed, post hoc: written after 6.2 failed and after the tests below)

The tests were run after the failure and before this amendment was proposed. Outputs are in
`results/dl4b-astrodeconv/` (`scale-test.txt`, `flux-diag.json`, scripts beside them).

1. **Prediction scale and orientation are exact.** A 1 Jy point source on a pixel centre, noise-free, seed 4's track, at 4 positions:
   - dirty peak 1.0000 ± 2e-4, on the intended pixel;
   - run-B model total 0.997-1.000.
2. **The metric is biased for off-grid sources.** The same source half a pixel off the grid, at 4 positions:
   - model total 1.000-1.005;
   - 3×3 box sum **1.06-1.11**.
   - Off-grid CLEAN leaves a positive core and a negative ring outside the box. Spiel's rounded positions fall anywhere within a pixel, so the frozen 6.2 metric is biased upward even for perfect data.
3. **In-field against full sky.** Run B, noise-free:
   - with in-image sources only, the 3×3 errors are +2.0 to +8.4 %;
   - with all sources, −0.9 to +12.6 %.
   - Seed 4 goes from +4.4 to +12.6 %, seed 9 from +7.1 to +11.9 %. The two failures are among the three faintest test sources (13.6 and 7.93 Jy), as an additive sidelobe error predicts.

**Proposed:** replace 6.2 by item 1 (pixel-centre source, total model and dirty peak within 1 %). On the evidence above, release the 9,000. That is the coordinator's decision, not this session's. The frozen 6.2 stays recorded as FAIL.

**Accepted by the coordinator, 2026-11-19, post hoc.**

- The replacement check passed: dirty peak 1.0000 ± 2e-4, model total 0.997-1.000.
- 6.2 stays recorded as FAIL: +12.6 % on seed 4 and +11.9 % on seed 9.
- The failure is explained by the metric (an off-grid CLEAN ring outside the 3×3 box) and by sidelobes from out-of-field sources, not by the data.
- The generation was released at 14 slots on nash.

**For the benchmark half (#42):**

- The truth is nearest-pixel, while the sources are off-grid by up to half a pixel.
- WSClean's models carry negative rings.
- Small-box flux metrics are therefore biased by +6-11 % per source even when CLEAN is right. Score fluxes on beam-convolved images or with total-flux apertures, and state it.
- Out-of-field sidelobes are a property of the dataset, as they were in the thesis's: with all sources the 3×3 errors are −0.9 to +12.6 %, against +2.0 to +8.4 % with in-image sources only. The residual RMS is the out-of-field sidelobes (about 5 mJy at flux10), not the noise.

## 7. Label

"ASTRODECONV2019 regenerated (rang, route b)": matched to spiel's job files and draws, not bit-identical
to the published set. The uvw code, noise realisation and WSClean version differ, and the published images were never available here.

## Measured result

(empty at freeze)
