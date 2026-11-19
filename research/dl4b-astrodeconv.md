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

## 7. Label

"ASTRODECONV2019 regenerated (rang, route b)": matched to spiel's job files and draws, not bit-identical
to the published set. The uvw code, noise realisation and WSClean version differ, and the published images were never available here.

## Measured result

(empty at freeze)
