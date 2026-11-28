# The Galactic Centre mosaic: from the SARAO archive to a picture

How to remake, with rang, the MeerKAT 1.28 GHz image of the Galactic Centre
that SARAO released in January 2022
([EarthSky's story](https://earthsky.org/space/milky-way-core-revealed-in-new-radio-mosaic-meerkat/),
image I. Heywood/SARAO): 20 pointings, 200 hours of telescope time,
6.5 deg² at 4″ resolution. The science paper is Heywood et al. 2022,
ApJ 925, 165 ([arXiv:2201.10541](https://arxiv.org/abs/2201.10541)).

```{warning}
**This recipe is proposed, not measured.** No Galactic Centre pointing has
been through rang yet. Each step below says whether it is *measured* (run by
the project on real MeerKAT data, with a report), *implemented* (the code
exists and is tested, but not on this field) or *proposed*. Nothing here
claims to match the paper's image. Compare your result with the released
mosaic (step 8) before you trust it. rang is a research demonstrator
({doc}`../limits`).
```

## What the paper did, and who does each step here

Heywood et al. calibrated with CASA (oxkat 0.1), flagged the targets with
Tricolour, imaged with WSClean and mosaicked with Montage. They did not use
direction-dependent calibration. That chain matches what rang ports, so most
of it maps onto `rang-core`:

| Step | Paper | Here | Status in rang |
| --- | --- | --- | --- |
| 1. Archive to MS | katdal | katdal's `mvftoms.py` | not rang; E2-N used this route ({gh}`research/e2n-native.md`) |
| 2. Flag | CASA, Tricolour | `rang-core flag` (Tricolour port, `known_rfi: meerkat_l`) | implemented; measured on E2-N |
| 3. 1GC | CASA: K, G, B on PKS B1934−638, gains on PKS B1827−360 | `rang-core calibrate`, `apply` | implemented; measured on E2-N (17 of 25 rows met) |
| 4. Image | WSClean, multiscale, Briggs −1.5 | `gemclean` through `rang-core image` | implemented; 6,144² untested on this field |
| 5. Self-cal | phase 64 s, then amplitude and phase per scan | `rang-core selfcal` | implemented; does not meet its limits on simulated truth ({gh}`research/c5-selfcal.md`) |
| 6. Beam correction | eidos, azimuthal average, cut at B = 0.5 | {gh}`examples/gc-mosaic/gc_mosaic.py` `pbcor` (katbeam) | not rang; tested on synthetic images |
| 7. Mosaic | Montage, weights B² | `gc_mosaic.py mosaic` | not rang; tested on synthetic images |
| 8. Picture | linear grey for faint, square-root heat map for bright | `gc_mosaic.py render` | not rang |

## What you need

- rang from source with the `beam` extra (katbeam) for step 6, `scipy` and
  `matplotlib` ({doc}`../installation`):
  `pip install -e '.[beam,plot]' scipy`.
- Linux, or WSL on Windows, for step 1: `mvftoms.py` needs python-casacore.
  `pip install katdal==0.24 python-casacore` in its own venv (on the WSL
  host make the venv with uv, since `python3 -m venv` lacks ensurepip there).
- Disk. These are estimates scaled from E2-N's measured MS (102 GiB for
  2.20 M rows at 1,024 channels, full polarisation, after `SIGMA_SPECTRUM` is
  dropped), not measurements on these blocks:

  | Per pointing | Estimate |
  | --- | --- |
  | rows (about 61 antennas, 1,830 baselines, 10.8 h at 8 s) | about 8.9 M |
  | MS at 1,024 channels after `mvftoms` | about 410 GiB |
  | with CORRECTED_DATA, MODEL_DATA and the self-cal copy | about 900 GiB (E2-N's own ratio, 2.2) |
  | archive data read by `mvftoms` (4,096 channels) | about 1.5 TB |

  All 20 pointings at once would need about 18 TB. Do one pointing at a
  time and keep only its images.
- Memory: the UHF gate books 128 GB for 6,144² images. GeMClean uses 2.0 to
  2.4 times WSClean's memory ({doc}`../limits`).

## 1. Choose a pointing and fetch it from the archive

The data are public, project code **SSV-20180505-FC-01**, in the SARAO
archive (<https://archive.sarao.ac.za>, free registration). The blocks,
from Table 1 of the paper:

| Pointing | Capture block | RA, Dec (J2000) |
| --- | --- | --- |
| TARGET | 1525645867 | 17:45:15.5 −28:47:35.3 |
| GC17 | 1528308058 | 17:43:35.9 −28:47:35.4 |
| GC16 | 1528394150 | 17:44:19.2 −29:06:18.3 |
| GC23 | 1528480450 | 17:45:58.7 −29:06:18.3 |
| GC22 | 1528566905 | 17:45:15.5 −29:25:01.3 |
| GC15 | 1528652884 | 17:43:35.9 −29:25:01.3 |
| GC29 | 1528739165 | 17:46:55.0 −29:25:01.3 |
| GC25 | 1528824954 | 17:45:58.7 −28:28:52.3 |
| GC18 | 1528911055 | 17:44:19.2 −28:28:52.3 |
| GC31 | 1528999219 | 17:46:55.0 −28:47:35.4 |
| GC30 | 1529082657 | 17:47:38.2 −29:06:18.3 |
| GC09 | 1529168752 | 17:42:39.6 −29:06:18.3 |
| GC33 | 1529254859 | 17:46:55.0 −28:10:09.5 |
| GC32 | 1529340951 | 17:47:38.2 −28:28:52.3 |
| GC21 | 1529427055 | 17:45:58.7 −29:43:44.2 |
| GC14 | 1529521526 | 17:44:19.2 −29:43:44.2 |
| GCX15 | 1529772166, 1529786044 | 17:41:36.5 −30:09:56.4 |
| GCXS16 | 1530030351 | 17:40:55.9 −29:29:23.7 |
| GCX32 | 1530288951 | 17:49:58.9 −28:25:27.9 |
| GCX21 | 1530461748 | 17:46:36.7 −30:16:24.3 |

GC23 (7′ from Sgr A*) and TARGET (14′) both hold Sgr A* well inside the
half-power circle. Start with one of them, then add GC31 and GC16 for a
first mosaic of four around the Galactic Centre.

In the archive, search for the capture block and ask for its
**`sdp_l0` RDB link**. That gives a URL with a personal token,
`https://…/<cbid>_sdp_l0.full.rdb?token=…`.

```{important}
The token is personal. Keep it in a file only you can read, pass it through
an environment variable, and never put it in a script, a log or a commit.
After conversion, search the logs and the MS's HISTORY table for `token=`.
```

Blocks from 2018 may be on tape. Before you start a 1.5 TB read, check that
the chunks are online and not just the RDB. The UHF fetch found blocks
whose object store held only the RDB ({gh}`research/uhf-s-fetch.md`):

```sh
python -c "import katdal, os; d = katdal.open(os.environ['RDB']); \
print(d); print(d.vis[0:1, 0:4, 0:1])"
```

If the archive says the block must be staged first, request it there and
wait.

## 2. Convert to a Measurement Set

`mvftoms.py` reads straight from the URL, so no local MVF copy is needed. It
averages the 4,096 channels to 1,024 (0.84 MHz). That keeps bandwidth
smearing at the half-power radius (0.55°) to about a third of the 4″ beam.
Do not average in time: 16 s smears by about 0.6 beam at that radius.

```sh
export RDB="$(cat ~/.sarao/1525645867.url)"       # the token stays out of argv history
mvftoms.py -f -a --chanbin 4 \
    --flags static,cam,data_lost,ingest_rfi,predicted_rfi \
    -o gc-1525645867.ms "$RDB" 2>&1 | grep -v token= > mvftoms.log
```

- `-f`: all four correlations (XX, XY, YX, YY), which rang expects of
  MeerKAT's linear feeds.
- `-a`: no autocorrelations.
- `--flags`: the observatory's online flags.
- No `-m`: rang writes MODEL_DATA and CORRECTED_DATA itself.
- No `--applycal`: the raw data.

These are E2-N's options (measured, {gh}`research/e2n-native.md` section 4)
plus `--chanbin`. `mvftoms` also writes SIGMA_SPECTRUM, which rang does not
read. On E2-N it took a quarter of the MS, so remove it with python-casacore's
`removecols` if disk is short.

Then look at what you have:

```sh
rang-core listobs gc-1525645867.ms
```

Note the FIELD names. Your configuration needs them exactly as written:
the flux calibrator J1939−6342 (PKS B1934−638), the secondary PKS B1827−360
and the target.

## 3. Flag, calibrate, apply, image and self-calibrate

{gh}`examples/gc-mosaic/config.yaml` is the whole chain for one pointing.
Copy it beside the MS and set `fields` from `listobs`. It passes
`rang-core config check --all`; against your MS, run:

```sh
rang-core config check config.yaml gc-1525645867.ms
rang-core run config.yaml gc-1525645867.ms
```

What it sets, against the paper:

| Setting | Paper | config.yaml |
| --- | --- | --- |
| flagging | auto-flag, then residual re-flag; telecom bands under 600 m | CARACal's first-pass strategy, `known_rfi: meerkat_l` (oxkat's bands under 600 m) |
| 1GC | K, G, B on 1934−638 (Reynolds model); gains on 1827−360 | K, G, B; Gsec and F (CASA `fluxscale`); setjy Stevens-Reynolds 2016 |
| solution intervals | delay and gain per 10 min, bandpass hourly | `solint: inf` per scan (E2-N's); set `600s` on K and G to follow the paper |
| imaging | Briggs −1.5, multiscale, 1.1″ pixels, 8 sub-bands, 4th-order polynomial | `robust: -1.5`, `multiscale`, `1.2asec`, `channels_out: 8`, `join_channels`, `fit_spectral_pol: 4` |
| masking | thresholded masks refined each cycle | `auto_mask: 5.0`, `auto_threshold: 1.0`; refining a FITS mask between rounds is `selfcal.cleanmask_method` |
| self-cal | phase 64 s, then amplitude and phase per scan, no spacings under 300 m | `Sp` at `64s`, then `Sa` at `inf`, `minuvw_m: 300` |
| final resolution | model convolved to 4″, residual homogenised (pypher) | not done: GeMClean restores with its fitted beam |

The run directory `gc-1525645867.ms.rang-run/` holds:

- the 1GC image in `image/<field>/image-image.fits`;
- each self-calibration round in `selfcal/<field>/round-<k>/`, and the final
  self-calibrated image in `selfcal/<field>/final/` (the stage's
  `summary.json` names the files);
- every stage's summary and the receipts. {doc}`../howto/check-results` and
{doc}`notebooks/08-reports-and-image-quality` show how to read them.

```{note}
**Where this field is hard for rang** ({doc}`../limits`):
- The Galactic Centre is extended emission everywhere. Multiscale with a mask
  can move flux outside the mask and diverge when cleaned deep (issue #35,
  {gh}`research/gemclean-ms-mask.md`). If the residual grows between major
  cycles, cap the scales (`multiscale_max_scales`) or clean less deep.
- Multiscale over-estimates compact sources by +9 to +18 µJy (median, on
  DF5-O's field).
- No direction-dependent calibration. The paper had none either, and its
  images are deconvolution-limited, not noise-limited.
- Self-calibration has not met its limits on simulated truth.
- Native MeerKAT data have been through the chain once (E2-N, 17 of 25 rows
  met).
```

To image again without recalibrating, `gemclean` takes the same settings
directly:

```sh
gemclean -name gc17 -size 6144 6144 -scale 1.2asec -weight briggs -1.5 \
    -multiscale -channels-out 8 -join-channels -fit-spectral-pol 4 \
    -niter 1000000 -mgain 0.9 -auto-mask 5 -auto-threshold 1 \
    -no-update-model-required gc-1525645867.ms
```

## 4. Correct for the primary beam

The images are not corrected for the primary beam, and rang does not
correct them. {gh}`examples/gc-mosaic/gc_mosaic.py` does it as the paper did:
the Stokes I power beam at the image frequency, azimuthally averaged, blanked
below B = 0.5. The beam comes from SARAO's katbeam model `MKAT-AA-L-JIM-2020`
in place of the paper's eidos. `--beam mauch` uses Mauch et al.'s (2020)
analytic beam instead. At 1,284 MHz the two put half power at 0.555° and
0.560° from the centre.

```sh
python examples/gc-mosaic/gc_mosaic.py pbcor \
    gc-1525645867.ms.rang-run/selfcal/TARGET/final/image-image.fits TARGET-pbcor.fits
```

It writes the corrected image and the beam (`TARGET-pbcor-pb.fits`). The
pointing centre is the image's reference pixel, which is MeerKAT's phase
centre.

## 5. Mosaic the pointings

```sh
python examples/gc-mosaic/gc_mosaic.py mosaic gc-mosaic.fits \
    TARGET-image.fits GC23-image.fits GC31-image.fits GC16-image.fits
```

Give it the uncorrected images. It forms

$$M = \frac{\sum_i B_i I_i}{\sum_i B_i^2},$$

which weights each corrected image $I_i/B_i$ by $B_i^2$. That is the paper's
variance weighting, assuming each pointing has the same noise. Pixels with
$B_i < 0.5$ do not count.

- `--frame galactic` (the default) puts the Galactic plane horizontal, as in
  the press image.
- `--pixel-arcsec` sets the pixel size; by default it is the inputs' finest.
- The header's restoring beam is the widest input's.
- `gc-mosaic-weight.fits` holds $\sum B_i^2$, a map of the relative noise.

Heywood et al. also shifted the headers by the median offset from VLA
positions (−1.16″ in RA, +0.53″ in Dec). Measure your own offset before you
apply one.

## 6. Make the picture

```sh
python examples/gc-mosaic/gc_mosaic.py render gc-mosaic.fits gc-mosaic.png \
    --downsample 2
```

This follows the paper's Figure 1:

- faint emission in linear greyscale from −2σ to `--faint-max`
  (default 10σ, with σ the mosaic's robust rms);
- brighter emission in the `afmhot` heat map with a square-root stretch up
  to `--bright-max` (default the 99.95th percentile).

The press image's exact levels are not published. On the released mosaic
(measured 2026-11-28, nash):

- the robust σ is 61 µJy/beam, extended emission included;
- the defaults (grey to 0.61 mJy/beam, heat map to 30 mJy/beam with
  `--bright-max 0.03`) show the filaments, the bubbles and the remnant shells;
- `--faint-max 0.0004` brings out more of the faint filaments.

The render took 16 s and 2 GB for the 10,121 × 10,527 mosaic with
`--downsample 4`. Downsampling averages N×N pixels, which keeps the PNG to a
manageable size.

## 7. All twenty pointings

Repeat steps 1 to 4 per block (GCX15 has two blocks: convert both and give
both MSs to the run, or image each and mosaic both). Delete each MS once its
images are checked. Then run step 5 on all twenty images.
{doc}`../howto/cluster` runs flag, solve and apply as Slurm or PBS array
jobs on a cluster.

## 8. Check against the released mosaic

SARAO published the paper's products at
<https://doi.org/10.48479/fyst-hj47>, under CC BY-NC 4.0:

- `MeerKAT_Galactic_Centre_1284MHz-StokesI.fits` (813 MB, 4″);
- the spectral index and its error (1.1 GB each, 8″).

Use the Stokes I mosaic as the reference:

- the same compact sources' fluxes, after you convolve your image to 4″;
- the rms in an empty patch (the paper quotes 26 µJy/beam over G0.8−0.4 as
  a pixel standard deviation);
- the filaments' brightness.

Expect differences. The paper homogenised the resolution, used eidos, and
cleaned with 0.5-1 million iterations per field in 2-4 cycles. Report what
you find ({doc}`../contributing`). A measured run is the next step for the
project.

To make only the picture, `render` works on the released FITS directly. Its
licence allows non-commercial use with attribution
(I. Heywood/SARAO, Heywood et al. 2022).
