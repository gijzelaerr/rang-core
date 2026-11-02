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

**Status now (2026-11-02): implemented; measured; the oracles are frozen**
([measured results](#6-measured-results-post-freeze-runs-as-frozen)). The
field is simulated through the core (MS by the core writer, prediction by
the exact degridder, DFT check 1.2e-11) and hashed; both tools read it
bit-identically and their dirty images agree with the core's to 1.7e-7
(WSClean) and 2.6e-7 (pfb) of the peak. WSClean Högbom and pfb kclean/Clark meet
the truth tolerances A1 and A2; WSClean multiscale meets A2 and fails A1 on
p16, p23 and p26 (29–85σ_ap, beside its large-scale flux); pfb sara at the release's
recipe settings has not converged in 10 major cycles (residual RMS 30σ).
DF5's acceptance bounds are in section 6.5. Deviations D1–D6 (section 7);
DDFacet was not run (open item). WSClean Högbom and pfb kclean/Clark are
bit-reproducible run to run (kclean to 8e-22 Jy); the multiscale arms and sara are not (residual
RMS spread ≤ 0.34 %).

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

## 5. Implementation (owner files)

`examples/simulate_df5_field.py` (truth, MS through the core, prediction,
FITS truth, hashes, `field.json`), `examples/oracle_wsclean_clean.py`
(WSClean arms in the container, timings), `examples/oracle_pfb.py` (pfb
arms in the container, timings), `examples/compare_df5o.py` (sections 3–4,
the archive), `tools/oracles/pfb-imaging/` (image), `tests/test_df5o.py`,
`research/results/df5o-deconv-oracles.json`, this note.

## 6. Measured results (post-freeze runs, as frozen)

Run `outputs/df5o-20261031-01` (field, WSClean arms, pfb sara, the misfit
floor, preconditions, measures) and `outputs/df5o-20261102-02` (the pfb
kclean/Clark arms, rerun after deviation D4); archive
[results/df5o-deconv-oracles.json](results/df5o-deconv-oracles.json)
(`examples/compare_df5o.py archive`: derived numbers and the synthetic truth
component list). Every number below was produced by the committed scripts.

### 6.1 The field (measured)

- 241,920 rows (2,016 baselines × 120 dumps), 16 channels; local hour angle
  −1.989 h to +1.989 h (120 s dumps of solar time), elevation 53.8°–59.6°.
- Noise: σ = 3.955 mJy per correlation, σ_I = 2.796 mJy, **σ_img = 1.421 µJy**
  (MFS, exact from the weights); the noise-only MFS dirty image has RMS
  1.408 µJy (whole image) and 1.433 µJy (inner half); threshold
  3σ_img = 4.264 µJy.
- PSF (natural, MFS): FWHM 11.58 × 7.23 pixels (23.2″ × 14.5″), so `b = 12`
  and the multiscale scales are 0, 24, 48, 96, 192 pixels.
- Truth: 58 components in 45 sources (40 points, 4 Gaussians, the radio
  galaxy of 14 parts), 97.94 mJy at 1,284 MHz, 99.71 mJy in the MFS truth
  image, brightest pixel 17.92 mJy.
- Checks: the FITS pixel `(x, y)` is the DFT direction `(−l_r, +m_r)` of the
  gridder layout (the other three sign choices miss by the full amplitude);
  the header WCS reproduces those `(l, m)` to 5.7e-16; the 41 point
  components through `predict_components` equal the degridded points-only
  cube to **1.2e-11** of the summed flux on every channel.
- Hashes (SHA256): MS digest (sorted file list) `978e2720…a684b877`;
  `field.npz` `b0f1fda4…02071a3f`; `truth-mfs.fits` `9b3a5253…d408ca4c1d`;
  `truth-cube.fits` `2883c85f…bb1e41a1e`; columns DATA `e6365242…f3393a`,
  UVW `e422f148…74e1dbf8`, WEIGHT_SPECTRUM `9fbc97e6…0e58217`; full digests
  in `field.json` and the archive.

### 6.2 Preconditions (measured)

| check | WSClean 3.7 (O-CASA image) | pfb-imaging 0.0.11 |
| --- | --- | --- |
| P1, python-casacore reads the core-written MS (DATA, UVW, WEIGHT_SPECTRUM, FLAG, TIME hashes, rows, CHAN_FREQ) | pass (3.7.1) | pass (3.8.1) |
| P2, dirty L∞/peak, worst channel | 1.74e-7 (MFS 1.49e-7) | 2.57e-7 |
| P2, PSF L∞ | 1.81e-7 | 1.35e-7 (central 1024² of its 1440² PSF) |
| counters | 241,920 visibilities gridded per channel (log) | – |
| orientation | WSClean's (by construction) | identity (the other seven symmetries miss by ≥ 0.85 of the peak), CRPIX 513 |

### 6.3 The misfit floor (measured)

`Q_0 = 4.432e-4 Jy²`, `Q_truth = 7.815e-6` (the noise: σ_I² = 7.819e-6),
`Q_∞ ≤ 6.278e-6` (200 CG iterations per channel, 66 min). The core's `Q_0`
equals the Python one to 1.5e-12. The CG budget sweep on channel 8 gives
6.311e-6, 6.240e-6, 6.205e-6 at 100, 200, 400 iterations: the bound still
falls by 0.6 % per doubling, so `Q_∞` is an upper bound, as stated. With
1 M pixels against 484 k real data per channel the floor lies below the
noise energy, so every reducible fraction below is dominated by the noise
(`(Q_truth − Q_∞)/(Q_0 − Q_∞) = 3.52e-3`).

### 6.4 The oracles (measured; repeat 1, repeat 2 in the archive)

Residuals are the **core-recomputed** exact residuals of each tool's model.
`cons.` is `‖r_tool − r_core(m_tool)‖∞`; `signal left` is
`(Q − Q_truth)/(Q_0 − Q_truth)`; κ is the MFS greedy ratio at the end.
pfb wall and RSS include `init` and `grid`.

| arm | model / truth | RMS inner (σ_img) | peak (σ_img) | cons. (σ_img) | Q/Q_0 | reducible | signal left | κ | A1 | A2 | spurious + / − (mJy) | major | minor | wall (s) r1 / r2 | RSS (MB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `ws-hogbom` | 0.99588 | 1.6055 µJy (1.130) | 3.16 | 0.0014 | 0.017630 | 3.514e-3 | −3.9e-6 | 6.6e-6 | pass | pass | 0.221 / −0.161 | 7 | 5,119 | 675 / 789 | 282 |
| `pfb-clark` | 0.99583 | 1.5663 µJy (1.102) | 2.94 | 0.0014 | 0.017628 | 3.512e-3 | −5.9e-6 | 5.7e-6 | pass | pass | 0.260 / −0.210 | 5 | – | 262 / 246 | 3,419 |
| `pfb-kclean` | equal to `pfb-clark` in every listed measure (cubes differ by ≤ 3.6e-12 Jy/pixel) | | | | | | | | pass | pass | | 5 | – | 257 / 327 | 3,423 |
| `ws-multiscale` | 0.99966 | 1.4463 µJy (1.018) | 3.42 | 0.0014 | 0.017635 | 3.519e-3 | +0.9e-6 | 7.7e-6 | **fail** (p16, p23, p26; r2: p23, p26) | pass | 2.861 / −3.335 | 7 | 40,819 | 1,199 / 1,437 | 915 |
| `ws-multiscale-mask` (reported) | 1.00115 | 1.2192 µJy (0.858) | 4.19 | 0.0014 | 0.017639 | 3.523e-3 | +5.4e-6 | 1.2e-5 | pass | pass | 3.318 / −3.085 | 7 | 84,749 | 2,452 / 2,182 | 918 |
| `pfb-sara` (reported) | 1.03052 | 42.52 µJy (29.9) | 693 | 0.0014 | 0.04800 | 3.43e-2 | 3.09e-2 | 0.032 | **fail** (30 sources) | **fail** (6) | 0 / 0 | 10 | – | 5,151 / 4,549 | 5,479 |

Per source (ΔS/S of repeat 1; all 45 are in the archive), the sources the
tolerances single out:

| source | S_truth (mJy) | S/σ_ap | ws-hogbom | pfb-clark | ws-multiscale | ws-ms-mask | pfb-sara |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| radio galaxy | 9.224 | 439 | −0.008 | −0.008 | +0.000 | +0.000 | −0.057 |
| g0 (12″) | 0.511 | 150 | −0.007 | −0.006 | +0.054 | +0.031 | −0.050 |
| g1 (24″) | 1.020 | 236 | −0.017 | −0.016 | +0.018 | +0.016 | −0.104 |
| g2 (40″) | 2.028 | 339 | −0.013 | −0.013 | −0.011 | −0.008 | −0.095 |
| g3 (64″) | 3.959 | 450 | −0.009 | −0.009 | +0.003 | +0.001 | −0.131 |
| p16 | 0.254 | 85 | −0.015 | −0.015 | +0.087 | +0.023 | −0.121 |
| p23 | 0.086 | 29 | −0.056 | −0.051 | +0.162 | +0.142 | −1.000 |
| p26 | 0.230 | 77 | −0.012 | −0.010 | +0.090 | +0.042 | −0.049 |
| p04 | 0.053 | 18 | −0.067 | −0.064 | +0.077 | +0.068 | −1.000 |
| p31 | 0.026 | 9 | −0.250 | −0.250 | −0.027 | −0.054 | −1.000 |

- The CLEANs lose 0.4 % of the flux (faint points 6–25 % low, below 20σ_ap
  where A1 does not apply); the multiscale arms recover the total to 0.03 %
  and 0.1 % but put ±3 mJy of large-scale flux outside every aperture (1 M
  non-zero pixels), which also lifts faint points beside it by 9–16 %.
- Positions: every point within 0.022 (Högbom, Clark), 0.056 (multiscale)
  and 0.041 (mask) of the PSF FWHM.
- Spectral indices (25 sources at ≥ 100σ_ap): median |Δα| 0.003 (Högbom,
  Clark), 0.017 (multiscale), 0.011 (mask), 0.041 (sara); worst 0.037,
  0.087, 0.054, 0.166.
- The tool residuals agree with the core-recomputed ones to 1.9e-9 Jy
  (0.0014σ_img) on every arm: the float32 FITS, nothing else. pfb's flux mop
  ran (`Extracting flux at iter 5`) but moved no pixel by more than 3.6e-12 Jy
  (kclean's model cube against Clark's, repeat 1), so the two coincide here.
- WSClean's source list (practice arm, `-fit-spectral-pol 4`): 4,953
  components (4,048 Gaussians), ordinary polynomial spectra, read by
  `rang.formats.sky.load_wsclean`; its flux per channel equals the model
  FITS to 1.1e-6 relative.
- sara: 10 cycles of about 12 min, stopped by `niter` with `eps = 7.8e-3`
  against `tol = 5e-4` (not converged); its `rmsfactor 1` threshold and
  positivity keep faint points at zero (the A1 failures are the sources
  below about 0.3 mJy plus the shrunk Gaussians).
- Reproducibility (repeat 2 − repeat 1, inner residual RMS): ws-hogbom 0,
  pfb-clark 0, pfb-kclean 2e-22 Jy, ws-multiscale 4.9e-9 Jy (0.34 %), mask
  2.6e-9 Jy (0.21 %), sara 5.6e-9 Jy (0.013 %); largest per-source flux
  difference 1.1 µJy (multiscale), 3.4 µJy (mask).

### 6.5 DF5's acceptance (frozen bounds, from the measured oracles)

For DF5 on this field with the protocol's settings (section 4):

- **A1 and A2, Högbom**: the matched oracles meet both, so DF5 Högbom must
  too: total MFS flux within 2 % of 99.71 mJy; every source with
  `S ≥ 20σ_ap` (39 of 45) within `0.05 S + 3σ_ap`; points within 0.1 PSF
  FWHM (2.3″), extended sources within 0.25.
- **A1, multiscale**: `ws-multiscale` fails A1 on p23 and p26 (both repeats)
  and p16 (repeat 1), so for those three DF5 multiscale must be no worse
  than ws-multiscale's worse repeat (ΔS/S ≤ +0.162, +0.090, +0.087); every
  other source as A1. A2 as Högbom.
- **A3, residual RMS (inner half, core-recomputed)**: Högbom
  **≤ 1.5976 µJy** (the best matched oracle, pfb-clark 1.5663 µJy, + 2 %;
  the matched spreads are 0); multiscale **≤ 1.4753 µJy** (ws-multiscale
  1.4463 µJy + 2 %, larger than twice its 4.9e-9 Jy spread).
- **A4, reducible fraction**: Högbom ≤ 3.582e-3, multiscale ≤ 3.589e-3
  (both noise-dominated, section 6.3; the more informative `signal left` of
  the matched oracles lies between −6e-6 and +1.6e-6).
- **A5, cost** (reported): ws-hogbom 675–789 s and 282 MB, pfb-clark
  246–262 s and 3.4 GB, ws-multiscale 1,199–1,437 s and 915 MB, at 4 threads.

## 7. Deviations from the protocol

- **D1**: WSClean 3.7 refuses `-save-source-list` with several output
  channels and no `-fit-spectral-pol` ("Saving a source list with multiple
  channels requires specifying a fitting method"). The matched arms run
  without it; the reported practice arm `ws-multiscale-mask` carries
  `-fit-spectral-pol 4 -save-source-list`, so it is no longer a pure
  masked variant of `ws-multiscale`. The first launch of the three arms
  failed on this flag within a second and was deleted.
- **D2**: WSClean opens the MS read/write even with
  `-no-update-model-required` ("cannot be opened for read/write" on the
  read-only mount, after the first minor cycle). Each WSClean run images a
  copy, checked unchanged (column hashes) after the run and removed; the
  failed runs were deleted.
- **D3**: the pfb-imaging closure needs `xarray<2026.4` (`requirements.in`):
  xarray 2026.4 dropped zarr 2 while dask-ms 0.2.32 requires zarr < 3, and
  pfb-imaging 0.0.11 states neither, so `pfb init` failed with
  `open_group() got an unexpected keyword argument 'zarr_format'`. xarray
  2026.2.0 is pinned; the image was rebuilt (`sha256:226e8e81…`).
- **D4**: `pfb kclean` forces `NUMBA_THREADING_LAYER=tbb`; the tbb wheel
  installs `libtbb.so.12` in `/opt/pfb/lib`, off the loader path, so kclean
  failed ("No threading layer could be loaded") in all four first attempts
  (`outputs/df5o-20261031-01/pfb/pfb-{kclean,clark}-r{1,2}`, logs kept). The
  driver now passes `LD_LIBRARY_PATH=/opt/pfb/lib`; the four runs were
  repeated into `outputs/df5o-20261102-02` (image unchanged). sara ran
  without it and completed.
- **D5**: small facts differ from the protocol's text: the hour angle spans
  ±1.989 h (the protocol gave the solar ±1.983 h), antenna names are the
  ITRF file's (`M000`…), and a FEED subtable is written.
- **D6**: the session was interrupted (API limit) between the floor run
  (2026-10-31) and the measures (2026-11-02); no run was cut, only D4's
  reruns and the measures were done after it.
- Caveat, not a deviation: WSClean runs with the frozen `-no-reorder`, which
  rereads the whole MS per channel image (a third of its wall is system
  time); its cost is not tuned.

## 8. Open items

- DDFacet HMP/SSD on this field (`rang-formats-oracle:20261030`): not run.
- pfb's `.mds` component model has no `rang.formats` reader.
- sara at a converging budget (its `tol`), as a convex-solver reference for
  a later novelty question; not a DF5 gate.
- Off-grid sources, a primary beam and Briggs weighting: the next field
  variants once DF5 passes this one.
- PyBDSF on the restored images (the survey's recovered-flux check): the
  aperture photometry against the known truth replaces it here.

## 9. Tool runs

| tool / step | input | wall | peak RSS | threads | notes |
| --- | --- | ---: | ---: | ---: | --- |
| `uv venv` + editable install (`.[pointing,beam,test,imaging,formats]`) | worktree | 172 s | – | 4 | extension built |
| `uv pip compile` pfb-imaging lock | requirements.in | 4.2 s | – | – | CPython 3.12, manylinux_2_39 |
| `docker build` pfb-imaging image (first; rebuilt for D3) | lock | 116 s; 76 s | – | – | 2.45 GB image |
| `simulate_df5_field.py` | – | 21.7 s | 857 MB | 4 | MS write 1.2 s, predict 4.9 s |
| P1 MS read-back (O-CASA; pfb image) | field.ms | 1.2 s; 1.4 s | – | 1 | |
| WSClean 3.7 `-niter 0` (16 channels, PSF) | field.ms | 137 s | 122 MB | 4 | |
| WSClean Högbom | field.ms | 675 s; 789 s | 282 MB | 4 | 7 major, 5,119 minor |
| WSClean multiscale | field.ms | 1,199 s; 1,437 s | 915 MB | 4 | 7 major, 40,819 minor |
| WSClean multiscale, auto-mask, fit-spectral-pol 4 | field.ms | 2,452 s; 2,182 s | 918 MB | 4 | 7 major, 84,749 minor |
| pfb init | field.ms | 41–68 s | 544 MB | 4 | |
| pfb grid | xds | 43–76 s | 1,120 MB | 4 | |
| pfb kclean (mop) | dds | 140 s; 154 s | 3,423 MB | 4 | 5 major |
| pfb kclean `--no-mop-flux` | dds | 111 s; 94 s | 3,419 MB | 4 | 5 major |
| pfb sara | dds | 5,020 s; 4,463 s | 5,479 MB | 4 | 10 major |
| `compare_df5o.py p2` | all dirty images | 20.1 s | 1,295 MB | 4 | |
| `compare_df5o.py floor` (16 channels × 200 CG, sweep 100/200/400) | field.npz | 3,986 s | 740 MB | 4 | 175–185 s per channel |
| `compare_df5o.py measure` (each of 12 runs) | FITS + field.npz | 19–30 s | 735 MB | 4 | |

### Reproduce

From the worktree, with `OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`, one job
at a time (`B=outputs/df5o-20261031-01`, `C=outputs/df5o-20261102-02`,
`F=$B/field`; `.venv/bin/python`):

```bash
bash tools/oracles/pfb-imaging/build.sh rang-pfb-imaging:0.0.11 outputs/df5o-20261031-00/pfb-image.json
python examples/simulate_df5_field.py $F
python examples/oracle_wsclean_clean.py msread-check $F $B/precondition/p1-ocasa.json
python examples/oracle_wsclean_clean.py msread-check $F $B/precondition/p1-pfb.json --image rang-pfb-imaging:0.0.11
python examples/oracle_wsclean_clean.py run $F $B/wsclean dirty --repeat 1
for rep in 1 2; do for arm in ws-hogbom ws-multiscale ws-multiscale-mask; do
  python examples/oracle_wsclean_clean.py run $F $B/wsclean $arm --repeat $rep; done; done
python examples/oracle_pfb.py run $F $B/pfb grid --repeat 1
for rep in 1 2; do python examples/oracle_pfb.py run $F $B/pfb pfb-sara --repeat $rep
  for arm in pfb-kclean pfb-clark; do       # in $C because of D4
    python examples/oracle_pfb.py run $F $C/pfb $arm --repeat $rep; done; done
python examples/compare_df5o.py floor $F $B/floor.json --iterations 200 --sweep-channel 8
python examples/compare_df5o.py p2 $F $B $B/precondition/p2.json
for d in $B/wsclean/ws-*-r[12] $B/pfb/pfb-sara-r[12] $C/pfb/pfb-*-r[12]; do
  python examples/compare_df5o.py measure $F $d $B/measures/$(basename $d).json \
    --floor $B/floor.json --p2 $B/precondition/p2.json; done
python examples/compare_df5o.py archive $F $B research/results/df5o-deconv-oracles.json
```

The pfb `.xds` and `.dds` stores and numba caches were deleted from the run
directories after the measures (they are per-run copies of the data); the FITS
the measures read are kept.

## 10. For the coordinator

### Shared-file lines (verbatim)

- `research/README.md`, after the "New, 2026-10-31: E5" paragraph:

  > New, 2026-11-02: DF5-O, the [deconvolution oracles](df5o-deconv-oracles.md):
  > a simulated MeerKAT field (core-made MS, truth on the grid, hashed),
  > WSClean 3.7 Högbom/multiscale and pfb-imaging 0.0.11 kclean/sara frozen
  > on it with truth measures and the CLEAN diagnostics; DF5's tolerances.

- `research/STATE.md`, new top paragraph:

  > DF5-O, the deconvolution oracles (big plan;
  > [df5o-deconv-oracles.md](df5o-deconv-oracles.md)), 2026-11-02
  > (implemented; measured): a simulated MeerKAT L-band field (64 antennas,
  > 4 h, 16 channels 900–1,670 MHz, radiometer noise σ_img = 1.42 µJy, 40
  > points from 15 µJy to 20 mJy, four Gaussians and an ESO 137−006-like
  > radio galaxy, all on the grid) predicted by the core's exact degridder
  > (DFT check 1.2e-11) into an MS the core creates, read bit-identically by
  > both tools' python-casacore; their dirty images agree with the core's to
  > 1.7e-7 (WSClean) and 2.6e-7 (pfb). Frozen, with the core-recomputed
  > residuals: WSClean Högbom 1.606 µJy RMS (1.13σ) in 7 major cycles and
  > pfb kclean/Clark 1.566 µJy in 5, both meeting the truth tolerances (flux
  > within 5 % + 3σ for every source above 20σ, points within 0.1 beam);
  > WSClean multiscale 1.446 µJy and total flux to 0.03 %, but ±3 mJy of
  > large-scale flux outside the sources and faint points beside it 9–16 %
  > high; pfb sara at its recipe settings unconverged in 10 cycles (30σ).
  > DF5 Högbom must reach ≤ 1.598 µJy, multiscale ≤ 1.475 µJy. pfb's flux mop
  > moved nothing here; two pfb packaging defects (closure, tbb path) and two
  > WSClean rules (read/write MS, source list) recorded. DDFacet open.
  > `outputs/df5o-20261031-01`, `outputs/df5o-20261102-02`,
  > `research/results/df5o-deconv-oracles.json`.

- `research/big-plan.md`, in the DDFacet/killMS paragraph after "DF3–DF5
  (facets with per-facet Jones, scalar CohJones, Hogbom/multiscale) after B1
  says what it needs;":

  > DF5-O done 2026-11-02 (`df5o-deconv-oracles.md`): DF5's acceptance on the
  > simulated field (16 channels, natural, ≤ 10 major cycles, 3σ threshold,
  > gain 0.1, mgain 0.8): total MFS flux within 2 % of the truth, every
  > source above 20σ_ap within 5 % + 3σ_ap (multiscale: p16, p23, p26 no
  > worse than WSClean multiscale), points within 0.1 PSF FWHM; the
  > core-recomputed inner residual RMS ≤ 1.598 µJy (Högbom, against WSClean
  > Högbom and pfb Clark) and ≤ 1.475 µJy (multiscale, against WSClean
  > multiscale); reducible fraction ≤ 3.58e-3 / 3.59e-3; the per-cycle Gram
  > gap recorded by DF5's driver; DDFacet HMP on the field open;

- `research/tool-timings.md`, rows:

  ```
  | 2026-10-31 | big plan DF5-O: `docker build` pfb-imaging 0.0.11 image (first; rebuilt for the xarray bound) | lock | 116 s; 76 s | – | 2.45 GB, `sha256:226e8e81…` |
  | 2026-10-31 | big plan DF5-O: `simulate_df5_field.py` | 241,920 rows × 16 channels | 21.7 s | 857 MB | 4 threads; MS write 1.2 s, predict 4.9 s |
  | 2026-10-31 | big plan DF5-O: WSClean 3.7 `-niter 0`, 16 channels | field.ms | 137 s | 122 MB | `-j 4`, `-no-reorder` |
  | 2026-10-31 | big plan DF5-O: WSClean 3.7 Högbom (two runs) | field.ms | 675 s; 789 s | 282 MB | 7 major, 5,119 minor; bit-identical |
  | 2026-10-31 | big plan DF5-O: WSClean 3.7 multiscale (two runs) | field.ms | 1,199 s; 1,437 s | 915 MB | 7 major, 40,819 minor |
  | 2026-10-31 | big plan DF5-O: WSClean 3.7 multiscale, auto-mask, fit-spectral-pol 4 (two runs) | field.ms | 2,452 s; 2,182 s | 918 MB | 7 major, 84,749 minor |
  | 2026-10-31 | big plan DF5-O: WSClean 3.7 arms, failed first launches (`-save-source-list`; read-only MS) | field.ms | ≤ 1 s; 147 s | 282 MB | deviations D1, D2 |
  | 2026-10-31 | big plan DF5-O: pfb 0.0.11 `init` (each arm) | field.ms | 41–68 s | 544 MB | 4 threads; first attempt failed on xarray/zarr (42 s, D3) |
  | 2026-10-31 | big plan DF5-O: pfb 0.0.11 `grid` (each arm) | xds | 43–76 s | 1,120 MB | 4 threads |
  | 2026-10-31 | big plan DF5-O: pfb 0.0.11 `sara` (two runs) | dds | 5,020 s; 4,463 s | 5,479 MB | 10 major, not converged |
  | 2026-10-31 | big plan DF5-O: pfb 0.0.11 `kclean`, failed on the tbb path (four runs) | dds | 10–14 s | 523 MB | deviation D4 |
  | 2026-11-02 | big plan DF5-O: pfb 0.0.11 `kclean` with mop (two runs) | dds | 140 s; 154 s | 3,423 MB | 5 major |
  | 2026-11-02 | big plan DF5-O: pfb 0.0.11 `kclean --no-mop-flux` (two runs) | dds | 111 s; 94 s | 3,419 MB | 5 major; bit-identical |
  | 2026-10-31 | big plan DF5-O: `compare_df5o.py floor` | 16 channels × 200 CG, sweep | 3,986 s | 740 MB | 175–185 s per channel |
  | 2026-11-02 | big plan DF5-O: `compare_df5o.py p2`; `measure` (12 runs) | FITS, field.npz | 20.1 s; 19–30 s each | 1,295 MB; 735 MB | 4 threads |
  | 2026-11-02 | big plan DF5-O: `bash tools/check-all.sh` | repo | see log | – | PASS: root 23, core 129 Rust tests; pytest 693 passed, 15 skipped (527 s); log `outputs/df5o-20261102-check-all.log` |
  ```

- `research/upstream-notes.md` (pfb-imaging is RATT; list for filing):
  1. pfb-imaging 0.0.11: the `[full]` closure resolves to xarray ≥ 2026.4,
     which needs zarr ≥ 3, while dask-ms 0.2.32 needs zarr < 3; `pfb init`
     fails (`open_group() got an unexpected keyword argument
     'zarr_format'`). Proposed: an `xarray<2026.4` bound in the `full` extra
     (or a zarr-3 dask-ms).
  2. pfb-imaging 0.0.11: `set_envs` forces `NUMBA_THREADING_LAYER=tbb` and
     loads the wheel's `libtbb.so` with `ctypes`, but numba's `tbbpool` still
     cannot find `libtbb.so.12` in a plain venv (`<venv>/lib` is not on the
     loader path): `kclean` stops with "No threading layer could be loaded".
     Proposed: preload `libtbb.so.12`, or fall back to `omp`.
  3. pfb-imaging 0.0.11: `kclean`'s flux mop moved no pixel by more than
     3.6e-12 Jy on this field (model cube with and without it, thresholds
     reached in 5 cycles). Observation, not an issue yet: whether the mop
     does anything at the threshold stop deserves a look.
  4. pfb-imaging 0.0.11 ships `deconv/hogbom.py` but no command uses it
     (`kclean` is Clark); a Högbom minor cycle on the CLI would give a Högbom
     oracle. Feature request.
- `research/non-ratt-observations.md` (WSClean; not filed):
  1. WSClean 3.7 opens the MS read/write with `-niter > 0` even with
     `-no-update-model-required`, failing on a read-only MS after the first
     minor cycle.
  2. WSClean 3.7 refuses `-save-source-list` with `-channels-out > 1` unless
     `-fit-spectral-pol` is given (by design; not in its help text).
  3. WSClean 3.7 warns that `-threshold` is deprecated for `-abs-threshold`.
  4. WSClean's fitted natural-weighting beam (52″ × 39″ at 924 MHz) is far
     wider than the half-maximum main lobe (about 32″ there; 23″ × 14″ MFS):
     MeerKAT's natural PSF plateau dominates the fit.

### No CLI stage

No `rang-core` stage is added; `core_cli.py` and `docs/cli.md` are unchanged.

### Ignored output directories

| directory | size | content |
| --- | ---: | --- |
| `outputs/df5o-20261031-00` | 20 KB | pfb image build log and record |
| `outputs/df5o-20261031-01` | 4.7 GB | field (MS, truth, npz: 697 MB), WSClean arms (FITS), pfb sara and grid (FITS; xds/dds stores removed), the failed first kclean attempts (logs only), floor, preconditions, measures |
| `outputs/df5o-20261102-02` | 2.1 GB | pfb kclean/Clark arms (FITS; stores removed) |
| `outputs/df5o-20261102-check-all.log` | small | check-all log |

Images kept on the host for DF5 reruns: `rang-pfb-imaging:0.0.11` (2.45 GB,
`sha256:226e8e81…`); the superseded first build was removed.
