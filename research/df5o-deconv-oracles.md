# Big plan task DF5-O: WSClean and pfb-imaging frozen as the deconvolution oracles on a simulated MeerKAT field

Protocol frozen 2026-10-31 on branch `df5o-deconv-oracles` (from `main`
`d4dcb20`), before any field is simulated or any oracle is run. Task DF5-O of
[big-plan.md](big-plan.md) (the DDFacet/killMS paragraph: "a simulated
MeerKAT target field is the DF3–DF5 oracle to start with"; the ecosystem
survey's recommendation 9 and its table 5.4, DF5 row: WSClean multiscale,
DDFacet HMP/SSD, pfb-imaging 0.0.11, truth from the simulated field;
[ddfacet-feasibility.md](ddfacet-feasibility.md), DF5 row: "model flux and
positions against truth within frozen tolerances; residual RMS no worse than
both tools at matched iterations").

**Status at freeze: proposed.** Nothing below is implemented or measured,
except the pfb-imaging image recipe and lock (tooling, section 2.3), which
were written before the freeze to find out whether pfb-imaging installs on
the host (it does not: it requires Python < 3.14).

This task writes no deconvolver and claims nothing about novelty. It freezes
a field with known truth, two external tools run on it at stated settings,
and the measures and tolerances DF5 (`core/src/deconv.rs`, Hogbom then
multiscale) will be judged by.

## 1. The simulated MeerKAT field (frozen)

### 1.1 Array, track, channels

- **Array**: the 64 MeerKAT antennas of `data/meerkat.itrf.txt` (ITRF metres),
  all 2,016 cross-correlations, no autocorrelations, no flags.
- **Phase centre**: RA 16h15m00.0s, Dec −60°54′00″ (J2000), near the
  radio galaxy ESO 137−006 of [b1-2-identifiability.md](b1-2-identifiability.md);
  the simulated sky is synthetic and only resembles it (section 1.2).
- **Track**: 120 dumps of 120 s, centred on transit, local hour angle
  −2 h to +2 h (dump centres at −1.983 h … +1.983 h). Times are UTC MJD
  seconds on 2026-03-21; the hour angle uses the IAU 1982 GMST formula and
  MeerKAT's longitude (21.443° E, from the array centre of the ITRF file).
  No precession, nutation or aberration (the UVW column defines the data for
  every tool; all three tools read UVW from the MS).
- **UVW**: `uvw = uvw(ANTENNA1) − uvw(ANTENNA2)` (mvftoms' convention,
  `rang.meerkat`), with the antenna `uvw` the standard rotation of the ITRF
  position by the Greenwich hour angle and declination (Thompson, Moran and
  Swenson eq. 4.1). Rows time-major, baselines `(a1 < a2)` in order:
  241,920 rows. No shadowing or elevation limit (the lowest elevation is
  about 54°).
- **Channels**: 16 channels of 48.125 MHz from 900 to 1,670 MHz (centres
  924.0625 … 1,645.9375 MHz). Every channel is imaged as its own image by
  every tool (section 2), so no spectral approximation enters the
  comparison. No bandwidth or time smearing: each visibility is the sky
  at its channel centre and dump centre.
- **Image grid**: 1,024 × 1,024 pixels of 2.0″ (34.1′), SIN projection at
  the phase centre. 2.0″ is 0.82 of the Nyquist cell at the top channel
  (2.44″ for the 7.70 km longest baseline).

### 1.2 Truth sky (seed 20261031)

All emission lies within 240 pixels (8.0′) of the centre, the inner half of
the image (the certified-imaging study's WSClean divergence came from
sources near the edge, where an image-size PSF is truncated). Every
component is defined **on the grid**: point sources on pixel centres,
Gaussians sampled at pixel centres and normalised so the pixels sum to the
component's flux. Spectra are power laws `S(ν) = S₀ (ν/ν₀)^α`,
`ν₀ = 1,284 MHz`. The truth of channel `c` is the image
`T_c = Σ_k S_k(ν_c) G_k`, and the MFS truth is the mean of the 16 channel
images (all channels have equal weight sums, section 1.3).

- **40 point sources**, `S₀` log-uniform in [15 µJy, 20 mJy] (about 10σ to
  13,000σ of the MFS image noise), `α ~ N(−0.7, 0.25)`, uniform in the
  240-pixel disc.
- **4 Gaussians** (FWHM major 12″, 24″, 40″, 64″; axial ratio uniform in
  [0.5, 1]; position angle uniform; `S₀` = 0.5, 1, 2, 4 mJy; `α = −0.8`).
- **One resolved radio galaxy** (an ESO 137−006-like wide-angle tail,
  about 4′ across, centred 150 pixels from the phase centre): a flat-spectrum
  core (point, 1 mJy, `α = 0`), two jets of five small Gaussians each
  (8″ × 5″, 0.15 mJy, `α = −0.6`) bending away from the core, two lobes
  (36″ × 18″, 2.5 mJy each, `α = −0.9`) and a diffuse tail (90″ × 36″,
  1.5 mJy, `α = −1.4`) joining them. It is scored as one source (section 3).
- Placement: rejection sampling with a minimum separation between any two
  sources' apertures (section 3.1) of 1.5 times the sum of their radii, so
  apertures never overlap.

The component list (positions, fluxes, shapes, spectra) is written as JSON
and as a WSClean source list through `rang.formats.sky.dumps_wsclean`
(synthetic; included in the results archive).

### 1.3 Visibilities, noise, weights

- **Prediction**: the core's exact degridder (`rang.core_wgridder.dirty2vis`,
  f64, ε = 1e-10, w-gridding on, `flip_v`, `flip_w`, no division by `n`),
  one call per channel on `T_c` (the adjoint of the orientation WSClean's
  FITS images have; DF1 item 0, DF2b). **Check**: the 41 point components
  (40 points and the core) predicted by the core's DFT
  (`rang.core.predict_components`) at the direction cosines of their pixel
  centres agree with the degridded visibilities of a points-only cube to
  ≤ 1e-8 of the summed flux on every channel (recorded). The orientation
  (which `(l, m)` sign the FITS pixel has) is established by that check and
  recorded; the component list's RA/Dec are the WSClean header's WCS at
  each pixel, and `direction_cosines(RA, Dec)` must reproduce the `(l, m)`
  used to 1e-12.
- **Correlations**: `XX = V + n₁`, `YY = V + n₂`, `XY = n₃`, `YX = n₄`, with
  independent complex Gaussian noise of σ per real and imaginary part
  (seed 5101, NumPy `default_rng`, drawn per block of rows in order).
  Stokes I, `(XX + YY)/2`, has noise σ_I = σ/√2.
- **Noise level** from the radiometer equation:
  `σ = SEFD / √(2 Δν τ)` with SEFD = 425 Jy (a representative MeerKAT
  L-band value, Tsys/η ≈ 22 K over 143 m², assumed), Δν = 48.125 MHz,
  τ = 120 s: σ = 3.955 mJy, σ_I = 2.797 mJy.
- **Weights**: `WEIGHT_SPECTRUM = 1/σ²` and `SIGMA_SPECTRUM = σ` on all four
  correlations, `WEIGHT = 1/σ²`, `SIGMA = σ`, every visibility equal, so
  every Stokes-I weighting rule (WSClean's `4 min(w_XX, w_YY)`, pfb's `l2`)
  is one global scale.
- **Image noise, exact**: with equal weights and natural weighting the noise
  of a channel's dirty image (normalised so that the PSF peak is one) is
  σ_I/√N_c with N_c = 241,920 Stokes-I samples, and of the MFS image
  σ_img = σ_I/√(16 N_c) = **1.42 µJy/beam** (σ_I = 2.797 mJy). This number,
  recomputed from the written weights, is the reference for every
  threshold and every residual. The noise-only MFS dirty image (the noise
  visibilities gridded alone) is reported beside it.
- **Gains, beam**: no gain errors, no direction-dependent effects, **no
  primary beam** (DF5 is deconvolution only; DF3/DF4 add directions and
  gains). WSClean runs without `-apply-primary-beam`, pfb without a beam
  model. The field lies well inside the half-power beam (radius about 34′
  at 1.28 GHz, 26′ at 1.67 GHz), so ignoring the beam is what a narrow
  survey field would have.

### 1.4 The Measurement Set and the truth image

- The MS is **created by the core** (`rang.core_ms_write.default_ms`, E4)
  with `DATA` (complex), `WEIGHT_SPECTRUM` and `SIGMA_SPECTRUM` (float)
  `[16, 4]` columns, and filled through the core writer: MAIN, ANTENNA (64
  rows, names `m000`… as the ITRF file, 13.5 m, ALT-AZ), SPECTRAL_WINDOW,
  POLARIZATION (XX, XY, YX, YY), DATA_DESCRIPTION, FIELD, OBSERVATION
  (MeerKAT). python-casacore is not used to write it.
- Precondition: python-casacore in each container (O-CASA's 3.7.1, pfb's
  3.8.1) reads `DATA`, `UVW`, `WEIGHT_SPECTRUM`, `FLAG`, `TIME` and the
  subtables of the core-written MS bit-identically to the arrays the core
  wrote (hashes compared).
- The truth is written on the same grid in WSClean's FITS orientation and
  header (`core_grid.wcs_header`): `truth-mfs.fits` and a 16-plane
  `truth-cube.fits` (float64), plus `field.npz` (Stokes-I visibilities,
  weights, UVW, frequencies, truth cube, noise-only visibilities) for the
  measures.
- Hashes: SHA256 of every file of the MS (sorted, and one digest of the
  list), of the FITS files and of `field.npz`, and of the arrays written
  (DATA, UVW, WEIGHT_SPECTRUM); seeds 20261031 (sky) and 5101 (noise).
  Recorded in `field.json` and the results archive.

## 2. The oracles (frozen)

Common to every arm: Stokes I, natural weighting, 1,024² × 2.0″, all 16
channels imaged as 16 images deconvolved jointly (peaks found on the
channel sum), w-gridding on, gridder accuracy 1e-6, at most
**N = 10 major cycles**, absolute threshold **3σ_img = 4.26 µJy** where the
tool takes one, no mask, no primary beam, 4 threads (the host is shared).
Every arm runs twice to measure its reproducibility spread. The `-niter 0`
dirty image and PSF of each tool are compared with the core's exact
`fits_image` (precondition, section 2.4).

### 2.1 WSClean 3.7 (O-CASA's image `rang-o-casa:6.7.6.14`, `--network none`)

Common flags: `-size 1024 1024 -scale 2asec -weight natural -pol I
-data-column DATA -gridder wgridder -wgridder-accuracy 1e-6
-no-min-grid-resolution -channels-out 16 -join-channels -nmiter 10
-threshold 4.26e-6 -niter 1000000 -gain 0.1 -mgain 0.8 -j 4
-no-update-model-required -save-source-list -no-reorder`
(no `-fit-spectral-pol`: every channel keeps its own component values, as
pfb's do).

- **`ws-hogbom`**: the common flags (WSClean's default Högbom minor loop
  with its fast sub-minor loop).
- **`ws-multiscale`**: the common flags plus `-multiscale
  -multiscale-scales 0,2b,4b,8b,16b -multiscale-gain 0.2` (WSClean's
  default multiscale gain and scale bias 0.6), with `b` the MFS PSF's
  FWHM major axis in pixels from the field simulation, rounded (the rule is
  frozen; the value is recorded in `field.json`).
- **`ws-multiscale-mask`** (reported, the practice setting; not a DF5 gate):
  as `ws-multiscale` with `-auto-mask 4 -auto-threshold 1` in place of
  `-threshold`.

`-save-source-list` makes WSClean write its component list, which the
comparison reads through `rang.formats.sky.load_wsclean` (and checks against
the model FITS, flux summed).

### 2.2 pfb-imaging 0.0.11 (image `rang-pfb-imaging:0.0.11`, section 2.3)

The legacy chain the release's recipes use (`init → grid → kclean|sara`),
with `--backend native --nthreads 4 --nworkers 1`, `--shm-size 8g` for
Ray, `--network none`:

- `pfb init --ms MS --output-filename OUT --data-column DATA
  --weight-column WEIGHT_SPECTRUM --channels-per-image 1 --chan-average 1
  --bda-decorr 1.0 --precision double --product I --integrations-per-image -1`
  (one band per channel: 16 bands);
- `pfb grid --output-filename OUT --nx 1024 --ny 1024 --cell-size 2.0
  --psf-oversize 1.4 --epsilon 1e-6 --do-wgridding` (robustness unset:
  natural);
- **`pfb-kclean`**: `pfb kclean --niter 10 --threshold 4.26e-6 --gamma 0.1
  --peak-factor 0.2 --epsilon 1e-6` (peak factor `1 − mgain`; pfb's default
  flux mop on). pfb-imaging 0.0.11 exposes no Högbom on its command line
  (`deconv/hogbom.py` is not called by any command): `kclean` is a Clark
  CLEAN with a sub-minor loop and a PCG "flux mop" (deviation from the
  task's "pfb's `clean` (Hogbom)", recorded).
- **`pfb-clark`**: as `pfb-kclean` with `--no-mop-flux` (the CLEAN-only
  arm, closest to Högbom).
- **`pfb-sara`**: `pfb sara --niter 10 --rmsfactor 1.0 --epsilon 1e-6` with
  the release's recipe settings (`bases self,db1,db2,db3`, `nlevels 2`,
  `l1-reweight-from 5`, `pd-tol 1.5e-4`, `pd-maxit 450`, `tol 5e-4`,
  `gamma 0.99`, `alpha 2`, `eta 5e-4`, `positivity 1`, `init-factor 0.5`).
  sara takes no absolute threshold; it stops on `tol` or `niter`.
- Outputs: the FITS cubes and MFS images of `MODEL` and `RESIDUAL` that the
  commands write; pfb's `.mds` component model is recorded but does not go
  through `rang.formats.sky` (no reader; open item).

### 2.3 The pfb-imaging image

`tools/oracles/pfb-imaging/` (Dockerfile, `build.sh`, `requirements.in`,
`requirements.lock`): Ubuntu 24.04 (the digest O-CASA pins), its Python
3.12, a uv 0.12.23 venv at `/opt/pfb` with `pfb-imaging[full]==0.0.11` and
its closure from public PyPI installed with hashes (lock resolved on the
host for CPython 3.12 manylinux_2_39; ducc0 0.42.0, the core wgridder's
reference). The image id, size, build time and the installed versions are
recorded.

### 2.4 Preconditions (before any CLEAN number counts)

- P1, the MS: section 1.4's read-back, per container.
- P2, the dirty images: each tool's `-niter 0` (WSClean) or `grid` (pfb)
  dirty image and PSF of every channel and of the MFS against the core's
  `fits_image` at ε 1e-9: L∞/peak ≤ 1e-5 (DF2b's tolerance) after the tool's
  own normalisation; counters WSClean `WSCNVIS`/`WSCIMGWG` (the visibility
  count and weight sum, up to WSClean's factor 4 on Stokes-I weights) and
  pfb's `WSUM`. pfb's orientation (transpose, flips, centre pixel) is found
  here once, on the dirty image, and applied to every pfb output; it is
  recorded.
- If a precondition fails, that tool's arm is recorded as failed and not
  scored.

### 2.5 DDFacet (optional)

DDFacet HMP in `rang-formats-oracle:20261030` (DDFacet 1.0.0.0) only if the
two required oracles are frozen with time left; otherwise an open item.

## 3. The frozen measures (truth known)

Computed by `examples/compare_df5o.py` from each arm's per-channel model
FITS (Jy/pixel) and MFS residual FITS, mapped to WSClean's orientation.

### 3.1 Per truth component

- **Apertures**: a disc around each source's truth centroid of radius
  `r = √(R_src² + b²)` with `b` the MFS PSF FWHM (major axis) and `R_src = 0`
  for a point, the FWHM major axis for a Gaussian, and the radius of the
  disc that holds the whole radio galaxy (its farthest component's centre
  plus that component's FWHM) for the radio galaxy.
- **Recovered flux**: the sum of the MFS model (mean of the 16 channel
  models) in the aperture against the MFS truth (mean of the channel
  truths) in the same aperture: `ΔS = S_model − S_truth`, `ΔS/S_truth` and
  `ΔS/σ_ap` with `σ_ap = σ_img √(N_beams in the aperture)`.
- **Position**: the flux-weighted centroid of the MFS model in the aperture
  against that of the MFS truth (arcsec).
- **Spectral index** (reported, not gated): a least-squares power-law fit to
  the 16 per-channel aperture fluxes, for components with
  `S_truth ≥ 100 σ_ap`.
- **Spurious flux**: the model flux outside every aperture, positive and
  negative parts separately.

### 3.2 Whole image

- Total model flux (MFS) against the total truth.
- **Residual RMS and peak against the noise**, from the **exact residual of
  the tool's model recomputed by the core** (each channel's model through
  `dirty2vis`, subtracted from the Stokes-I visibilities, gridded by
  `vis2dirty`, normalised by the weight sum; MFS the mean over channels):
  RMS over the inner half (`[256:768, 256:768]`) and the whole image, and
  `|peak|`, in units of σ_img. The tool's own MFS residual is reported
  beside it.
- **The tool's consistency**: `‖r_tool − r_core(m_tool)‖∞` and its RMS (MFS),
  which is what a tool's own residual hides.

### 3.3 CLEAN-theory diagnostics (from `core/src/clean.rs`, `clean_certified.rs`)

- `Q(m) = ½ Σ w |V − A m|² / Σ w` per channel (the certified driver's
  misfit, Jy²), and the field total `Q = Σ_c (W_c/W) Q_c`; `Q_0 = Q(0)`.
- `Q_∞` per channel by conjugate gradients on the normal operator through
  `rang.core_clean.certified_clean(..., floor_iterations=200)` (an upper
  bound on the floor; the CG budget sweep 100/200/400 on one channel is
  reported). Per arm: `Q/Q_0`, the reducible fraction
  `(Q − Q_∞)/(Q_0 − Q_∞)`, and the final greedy ratio
  `κ = r_peak² / (2 (Q − Q_∞))` on the core-recomputed MFS residual.
- `Q_truth`, the misfit of the truth cube (the noise energy), on the same
  scale: `(Q − Q_truth)/(Q_0 − Q_truth)` is the fraction of the signal left
  in the data; negative means the model fits noise.
- **Not computed, by construction**: the per-major-cycle Gram-consistency
  gap is a property of a tool's own minor loop (the beam it subtracts and
  where), and cannot be computed from its final model and residual. DF5's
  driver will record it per cycle (as `clean_certified` does); for the
  oracles only the consistency of section 3.2 is measured. The ERC
  certificate is not computed (with hundreds to tens of thousands of
  components on adjacent pixels it was singular to working precision in the
  certified-imaging study).

### 3.4 Cost

Per arm: wall time (container wall and the tool's own log), peak RSS
(`/usr/bin/time -v` inside the container), major cycles and minor
iterations (WSClean's log; pfb's log), and threads.

## 4. Deliverable and DF5's acceptance (frozen)

The frozen oracle archive: `outputs/df5o-20261031-NN/` (MS, truth, every
arm's FITS and logs, ignored) and `research/results/df5o-deconv-oracles.json`
(derived numbers only: the field's hashes and settings, the truth component
list, per arm the measures of section 3, the reproducibility spread, the
cost). `tests/test_df5o.py` recomputes the measures from the archive's
outputs (skips without them) and checks them against the JSON.

**DF5's acceptance tolerances**, run on this field with the same settings
(16 channels, natural weighting, N ≤ 10 major cycles, threshold 3σ_img,
gain 0.1, mgain 0.8, no mask), measured by `compare_df5o.py`:

- **A1, truth, flux**: total MFS model flux within 2 % of the truth; for
  every component with `S_truth ≥ 20 σ_ap`, `|ΔS| ≤ 0.05 S_truth + 3 σ_ap`.
- **A2, truth, positions**: for every point component with
  `S_truth ≥ 20 σ_ap`, the model centroid within 0.1 PSF FWHM of the truth;
  for extended sources within 0.25 PSF FWHM.
- **A3, residual against the oracles**: the core-recomputed MFS residual RMS
  (inner half) no worse than the best matched oracle of the same class,
  `≤ min(oracles) + max(0.02 min(oracles), 2 × spread)`, with `spread` the
  largest run-to-run difference of the matched oracles' RMS. Classes:
  DF5 Hogbom against `ws-hogbom` and `pfb-clark` (and `pfb-kclean`,
  reported); DF5 multiscale against `ws-multiscale`. `pfb-sara` and
  `ws-multiscale-mask` are reported references, not gates (a CLEAN is not
  held to a convex solver's or a masked run's residual).
- **A4, misfit**: the reducible fraction `(Q − Q_∞)/(Q_0 − Q_∞)` no larger
  than that of the best matched oracle by the same margin as A3.
- **A5, cost** (reported, not gated at DF5's first version): wall and RSS
  against the matched oracles at the same threads.
- A1 and A2 are also evaluated on every oracle arm: whether the tolerances
  are attainable at all on this field is part of the frozen result. If no
  matched oracle meets A1 or A2, DF5's A1/A2 become "no worse than the best
  matched oracle" for the components the oracles miss, recorded as such.

Nothing here claims novelty. A DF5 that passes A1–A4 is a port at oracle
quality, not an improvement.

## 5. Implementation plan (owner files)

`examples/simulate_df5_field.py` (truth, MS through the core, prediction,
FITS truth, hashes, `field.json`), `examples/oracle_wsclean_clean.py`
(WSClean arms in the container, timings), `examples/oracle_pfb.py` (pfb
arms in the container, timings), `examples/compare_df5o.py` (sections 3–4,
the archive), `tools/oracles/pfb-imaging/` (image), `tests/test_df5o.py`,
`research/results/df5o-deconv-oracles.json`, this note.
