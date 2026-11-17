# Rang: GeMClean multiscale with a FITS mask (issue #35)

Status, 2026-11-17: **protocol frozen** (sections 1-5 written and committed before any new run).

Issue #35 (from [floor-5.md](floor-5.md) section 10.2, arm Dms03): GeMClean `-multiscale
-fits-mask <source-mask.fits> -threshold 0.0003` on the E2 pilot after one Sp round left a model
that is nonzero on 16,647,036 of 16,777,216 pixels, with 3.53 Jy outside the mask and −7.62 Jy
negative. The Högbom arm with the same mask (Dm03) has no flux outside it. Question: does GeMClean
lose the mask under `-multiscale` (a defect), or does it do what WSClean 3.7 does? The oracle is
WSClean 3.7 (`rang-wsclean-native:3.7`, WSL docker, as G4). No novelty claim.

## 1. What radler does (read in its source, to locate the behaviour only)

radler `76fe4474` (WSClean v3.7, the tree G4 read, WSL `~/Build/tmp/20261109-g4-wsclean-src`),
`cpp/algorithms/multiscale_algorithm.cc`:

- The scale peak search (`FindActiveScaleConvolvedMaxima` → `FindPeakDirect`) takes
  `peak_finder::FindWithMask(..., CleanMask(), border)` when a clean mask is set, or the per-scale
  automatic masks when they are in use (`use_per_scale_masks_`). The mask is the same at every
  scale.
- The sub-minor loop gets `subLoop.SetMask(CleanMask())` (or the scale's automatic mask), so its
  pixel selection (`findPeakPositions`) takes only masked pixels.
- After the sub-minor loop the components (at the masked centres) are transformed with the scale
  shape (`msTransforms.Transform(..., scale)`) and **added to the model image**. Nothing clips the
  shape to the mask.

So in radler the mask restricts the component centres. It does not restrict where a component's
shape puts flux. A centre inside a mask island at a 625-pixel scale puts flux up to 313 pixels
from it.

GeMClean (`core/src/gemclean/multiscale.rs`): `Run::find_maxima` uses `peak_masked` with
`mask_of(s)`, which is the FITS mask unless the automatic per-scale masks are in use. The
sub-minor selection takes `v >= thr && mask_of(sel)[p]`. The model gets the components convolved
with the shape. This is the same structure as radler's.

## 2. Evidence before this protocol (archived, development only)

- **G4's F2** ([g4-masks.md](g4-masks.md); `D:\rang\outputs\g4-20261109-01\runs\{g4,wsclean}\F2`,
  S2 with the truth mask, `-multiscale -mgain 0.8 -abs-threshold 0.0001`, GeMClean `b13f7d3`):

  | imager | total | inside mask | outside mask | Σ\|m\| outside | negative | nonzero pixels |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | GeMClean | 12.891 Jy | 12.792 | 0.099 | 0.236 | −1.512 | 4,194,304 of 4,194,304 |
  | WSClean 3.7 | 12.885 Jy | 12.794 | 0.092 | 0.250 | −1.524 | 4,194,304 of 4,194,304 |

  Högbom F1: no model pixel outside the mask in either imager. GeMClean's `fits_outside_picks` is 0
  of 90,481 picks.
- **Dms03 itself** (`research/results/floor-5/family2/Dms03*`): 9 scales (0-1250 px). The 39-625 px
  scales carry 66 Jy of the 96 Jy model (scale 625 px: 260 components, gain 1512, 2.67 Jy). The
  3.53 Jy outside the mask is 3.7 % of the model. Its mask record (`image-mask.json`) was not
  archived. Dms03 ran without `-mgain`, so GeMClean's measured rule applied (`MeasuredStale ρ 1,
  g 0.95`). WSClean has no such rule, so Dms03 has no WSClean counterpart.

Both figures say the same thing: "nonzero pixels" and "flux outside the mask" cannot tell a lost
mask from the kernel tails of centres inside it. Every pixel of an FFT-convolved model is nonzero
in both imagers. The test below compares the quantities with WSClean on runs built like Dms03.

## 3. Protocol (frozen)

Settings as G4 (section 3 there): GeMClean natively on Windows, built from this branch's base
(`origin/main` at the freeze commit, profile `gemclean`). WSClean 3.7 in `rang-wsclean-native:3.7`
with `-gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I
-no-update-model-required`. Common options: `-weight briggs 0.5 -niter 10000000 -gain 0.1 -mgain
0.95 -nmiter 1000 -data-column DATA -field 0 -j 8`. `-mgain 0.95` is given explicitly, because
GeMClean's default is its measured rule, which WSClean does not have. Each run goes under
`tools/heavy_lock.py` with shared slots (8 threads).

| run | data | options beyond the settings | role |
| --- | --- | --- | --- |
| RM | H4 (`20261103-gemclean-heldout/sim/data/h4.ms`) | `-size 2048 2048 -scale 1.5asec -abs-threshold 0.00004 -fits-mask h4-points.fits -multiscale` | **the reproduction** |
| RH | H4 | RM without `-multiscale` | Högbom control |
| PM | the pilot (`20261103-gemclean-heldout/real/cal2.ms`) | `-size 4096 4096 -scale 3asec -abs-threshold 0.0003 -fits-mask source-mask.fits -multiscale` | Dms03's settings on real data (its mask, size, depth and default scales) |

- **H4's mask** `h4-points.fits` is built from H4's catalogue only (`h4.json`), never from an
  imager's output: discs of radius 6 pixels around all 30 points. H4's 31 Gaussians (6.10 Jy,
  FWHM 20-200″) are left outside on purpose, as Dms03's extended emission was. It is float32 with
  the WCS of a WSClean H4 image at 2048² and 1.5″ (G4's A2 dirty image), stored as `data[y, x]`.
- **The H4 threshold**, 40 µJy, is about 1.6σ, with σ 24 µJy measured on G4's A2 WSClean residual.
  This matches Dms03's 0.3 mJy over 0.19 mJy, so the largest scales take part.
- **PM** uses `D:\rang\outputs\20261103-gemclean-heldout\real\images\source-mask.fits`, the file
  Dms03 used (floor-5's set A source mask), with the pilot's DATA, not Dms03's post-Sp
  CORRECTED_DATA, which is on nash only.

## 4. Criteria (frozen)

Definitions as G4: σ is 1.4826 MAD of WSClean's residual on the inner field (the central 2N/3), Ω
is the restoring-beam area in pixels from WSClean's header (`π/(4 ln 2) · BMAJ · BMIN / Δ²`). A
region of N pixels has the noise term `ε = 3 σ √(N / Ω)`. Fluxes are sums of the model image.

- **M1, centres.** No GeMClean component centre lies outside the FITS mask on any run, at any
  scale. The evidence is `fits_outside_picks` in `<name>-mask.json`, which tests every recorded
  pick against the mask file, and the unit test this task adds (section 6).
- **C, Högbom control (RH).** No nonzero model pixel lies outside the mask, in either imager.
- **O, the issue's quantities (RM, PM).** For the mask region and its complement, the signed flux
  `F_in` and `F_out`, and the negative flux outside, `N_out`. Each must satisfy
  `|X_G − X_W| ≤ 0.02 |X_W| + √2 ε_R`, which is G4's M2 form with the mask and its complement as
  the two apertures.
- **Reported, not gated:** `Σ|m|` outside, nonzero pixels, pixels outside with `|m| > 1e-6`
  of the peak, the components and flux per scale (WSClean's `Scale info` and per-scale log lines
  against GeMClean's), major cycles, wall time (shared host, no timing claim).

## 5. Decision rule (frozen)

- **Defect**: M1 or C fails on any run. GeMClean loses the mask. The task then locates the loss (scale peak search, sub-minor selection or component
  placement), fixes it with a test that no component lies outside the mask at any scale, regates
  RM, RH and PM (labelled post-fix), and reruns the archived multiscale cases (G2-G9, DF5-O, C5b)
  through their check gates.
- **Multiscale difference, not the mask**: M1 and C pass but O fails. The centres stay inside the
  mask, and the two imagers spread different flux through the scales. The per-scale table
  locates it. It is reported as a multiscale finding, not a mask defect. A fix needs its own
  protocol, unless it is a plain bug against radler's source.
- **No defect (null)**: M1, C and O pass. GeMClean's multiscale follows WSClean 3.7: the FITS mask
  confines component centres at every scale, and the model's support is the scale shapes around
  them in both imagers. The clean path is not changed. The task adds the per-scale confinement
  test and states the behaviour in the `-fits-mask` help, the docs and the CHANGELOG. The archived
  multiscale cases are then unchanged by construction: no line outside tests and help text
  changes. Clipping the model to the mask would depart from WSClean and is an owner decision.

## 6. The confinement test (added under every outcome)

A unit test in `core/src/gemclean/multiscale.rs` runs multiscale on a sky with extended emission
outside a box mask. It covers several scales including a large one, single and joined channels, a
FITS mask alone, and a FITS mask with the automatic mask. It asserts that every component centre
(`steps`) lies inside the mask in force, and that components were cleaned at two or more non-zero
scales, so the test covers the scales and not only scale 0.
