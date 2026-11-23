# DD2: facet prediction and imaging with per-facet gains

Issue #15, second piece (plan in [dd1-facet-gains.md](dd1-facet-gains.md),
section 2). Branch `dd2-facets`. Sections 1-6 are frozen 2026-11-23, before
any code that tests them and before any WSClean output was read; later
changes are dated amendments, labelled post hoc where they could have seen a
result.

Status: **proposed**.

## 1. What DD2 is, and what it is not

DD1 solves one diagonal gain per (interval, antenna, facet direction). DD2
uses those gains where an imager needs them, in both directions of the
measurement operator:

- **Arm P, predict (forward):** the facet-corrupted model
  `V_pq = sum_f G_p,f M_f G_q,f^H`, `M_f` the model visibilities of the
  pixels in facet f. This is what a DD major cycle subtracts; it tests the
  H5parm export and the facet-to-direction mapping alone.
- **Arm I, imaging (adjoint):** per facet f, the visibilities multiplied by
  `G_p,f^H V G_q,f` (WSClean's imaging direction), gridded with rang's exact
  gridder over the full field, masked to facet f's polygon, normalised by the
  facet's averaged correction (section 4) and stitched.

Both against WSClean 3.7 with `-facet-regions` and `-apply-facet-solutions`
on the H5parm rang writes. Not claimed: deconvolution with facets, a facet
major cycle in GeMClean, primary-beam or facet-beam terms, time-frequency
smearing, speed (cost reported, not gated), any gain over WSClean. Rang's
facet imaging here grids the full field once per facet (cost ×n_facet); a
gridder with per-facet phase centres is later work if the cost matters.

## 2. What the oracle does (read in WSClean 3.7's source, `4f395b2`)

- `schaapcommon/facets/ds9facetfile.h`: facets are `polygon(ra, dec, ...)`
  in degrees (fk5); a following `point(ra, dec)` sets the facet direction,
  otherwise the polygon's pixel centroid.
- `gridding/visibilitymodifier.cpp`: per facet, the H5parm source **nearest**
  to the facet direction is used (`GetNearestSource`), with **nearest**
  interpolation in time and frequency, and antennas missing from the H5parm
  get **unit** gains (`MissingAntennaBehavior::kUnit`).
- `gridding/visibilitymodifier.h`: predict applies `g_p V g_q^*` per
  correlation for diagonal gains; imaging applies the conjugate,
  `g_p^* V g_q`. By default all four correlations are read and corrected.
- `gridding/averagecorrection.h`, `main/wsclean.cpp`: an average of the
  squared correction per facet is accumulated with the visibility weights;
  images are scaled per facet by `1/sqrt` of its Stokes I value ("flat
  noise" before deconvolution, "flat gain" after). Which output file carries
  which scaling, and the exact Stokes I value of a diagonal correction, are
  not settled by reading; control C2 measures them (section 4).

## 3. Data, facets, gains

- **Visibilities:** DD1's simulation (`dd1.ms`, seeds 1501-1503, 64
  antennas, 48 × 8 s, 16 channels), a copy per run.
- **Facets:** the Voronoi cells of DD1's four centres in the (l, m) plane,
  clipped to the image square, written as ds9 polygons with a `point` at each
  centre and `text=` the direction name; vertices converted to (RA, Dec) by
  the inverse SIN projection about the phase centre.
- **Image grid:** 2400 × 2400 pixels of 4″ (2.67° square), Stokes I.
- **Model image (arm P):** DD1's 28 components snapped to the nearest pixel
  centre, flat spectrum (one model image for all channels); components
  within 3 pixels of a facet boundary are dropped (count reported).
- **Gains:** `solve_dd` on DD1's `DATA` with P1's intervals (4 × 8 s, all
  channels), reference antenna 0, no pinned direction, and the **DD term's
  cap frozen here: 150 iterations, criterion 1e-7, stop fraction 0.99**
  (coordinator decision; DD1's P3-long converged in 140 at criterion 1e-10,
  stop fraction 1.0). Reported, not gated: where DD1's P3 stops under this
  rule and its truth error (rang only).
- **H5parm:** `amplitude000`, `phase000`, axes `time,freq,ant,dir,pol`
  (`rang.formats.h5parm.diagonal_solset`): times the interval centres in MS
  TIME units (MJD seconds), one frequency (the band centre), antenna names
  from the MS ANTENNA table, one source per facet at its centre. A flagged
  solution is written as amplitude 1, phase 0, weight 0. Guards asserted
  before WSClean runs: every MS antenna name is in the H5parm, and each MS
  integration's nearest H5parm time is its own interval's centre.

## 4. Cases, controls and frozen tolerances

WSClean: `rang-wsclean-native:3.7`, `-gridder wgridder -wgridder-accuracy
1e-6 -size 2400 2400 -scale 4asec -weight natural -pol I -niter 0`, default
padding; arm P adds `-predict` (model image `<name>-model.fits`), arm I writes
`-dirty.fits` and `-image.fits`. Rang: `core_wgridder.dirty2vis` /
`fits_image` (WSClean's FITS orientation, research/df1-wgridder.md item 0),
epsilon 1e-7, double precision.

Controls run first, each with its own pass rule:

| Control | WSClean | Pass rule |
| --- | --- | --- |
| C0 | no facets, no solutions: predict and dirty | as arms P and I below; settles the pixel convention |
| C1 | facets, an H5parm of unit gains | as arms P and I |
| C2 | facets, unit gains except one facet (d1) with constant `g_x = 2`, `g_y = 0.5 e^{iπ/4}` | selects the normalisation: rang's facet d1 image with `c` from candidate (a) `c = Σ w ½(|g_px|²|g_qx|² + |g_py|²|g_qy|²) / Σ w` or (b) `c = Σ w ¼(|g_px|²+|g_py|²)(|g_qx|²+|g_qy|²) / Σ w`, scaled by `1/sqrt(c)` for `-dirty.fits` and `1/c` for `-image.fits`; the candidate within arm I's tolerance on facet d1 is used for arm I |

**Arm P (gated):** every cell and parallel hand,
`|V_rang − V_wsc| ≤ 1e-4 × max|V_rang|`; cross hands `≤ 1e-4 × max|V_rang|`
in both.

**Arm I (gated):** `-dirty.fits` and `-image.fits`, every pixel at least
3 pixels inside its facet and the image edge,
`|I_rang − I_wsc| ≤ 1e-3 × max|I_wsc|`; the boundary band is reported.

**H (gated):** the H5parm read back by `rang.formats.h5parm` equals the
written gains exactly; the guards of section 3 hold.

## 5. Cost

Wall time and peak memory of rang's arms and of WSClean (`-j 8`), on glacier
under `heavy_lock`, indicative (shared host).

## 6. Decision rule (named before any result)

- **Setup outcome:** a control fails (C0 or C1, or C2 matches neither
  candidate, or WSClean refuses the H5parm). The convention is investigated,
  fixed and recorded as a dated amendment, and the controls rerun before any
  arm is read. Not a gate failure.
- **Pass:** H, P and I pass. Facet prediction and imaging with per-facet
  gains match WSClean; DD3 (the DD self-calibration loop) starts from them.
- **Export or mapping failure:** P fails (controls passed). Recorded with
  the first differing facet and quantity.
- **Normalisation or stitching failure:** P passes, I fails. Recorded; the
  predict side stands on its own.

## 7. Measured result

Not yet measured.
