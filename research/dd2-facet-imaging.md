# DD2: facet prediction and imaging with per-facet gains

Issue #15, second piece (plan in [dd1-facet-gains.md](dd1-facet-gains.md),
section 2). Branch `dd2-facets`. Sections 1-6 are frozen 2026-11-23, before
any code that tests them and before any WSClean output was read; later
changes are dated amendments, labelled post hoc where they could have seen a
result.

Status: **measured 2026-11-23**: H and arm P (facet predict with per-facet gains) **pass** against WSClean 3.7 (3.0e-7 of the peak, limit 1e-4); arm I (facet imaging) **not measured**. The first run's 0.5 % no-facet imaging gap was a setup mismatch (A3, A4); with a Nyquist-sampled 3″ grid and `-no-min-grid-resolution` (run `-03`) the no-facet and unit-gain imaging controls match WSClean to 4e-8 and 8e-8 and arm P to 3.7e-7. The normalisation control C2 still fails (1.3e-2 of the peak, limit 1e-3), so arm I is unread (A5).

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

Run `D:/rang/outputs/dd2-20261123-01` (prepare, rang and compare outputs;
WSClean products, logs and timings in `wsc/`); WSClean 3.7 `4f395b28`
(`rang-wsclean-native:3.7`); archive
[results/dd2-facet-imaging/](results/dd2-facet-imaging/) (`prepare.json`,
`rang.json`, `compare.json`, `facets.reg`). Host glacier, shared; rang at
`RAYON_NUM_THREADS=8`.

**Gains under the frozen DD cap (150, 1e-7, 0.99).** DD1's P1 data stop at
88 iterations (converged fraction 0.9935, nothing flagged); truth error
median 3.1e-3, unchanged from DD1 at 50. DD1's noiseless P3 under the same
rule: 88 iterations, max relative product error **1.9e-6** (DD1's gate T,
1e-4, would pass). No QuartiCal run at this cap (parity was measured at 50).

**H: pass.** All three H5parms (`unit`, `c2`, `solved`) read back equal;
every MS antenna is in the H5parm; each integration's nearest H5parm time is
its own interval's centre. 28 components kept, none within 3 pixels of a
facet boundary (per facet 9, 9, 3, 7).

**Predict controls and arm P: pass.**

| Case | max abs parallel-hand diff | relative to max \|V\| | cross hands |
| --- | --- | --- | --- |
| C0 (no facets, no solutions) | 2.9e-6 Jy | 6.0e-7 | 0 |
| C1 (facets, unit gains) | 1.5e-6 Jy | 3.0e-7 | 0 |
| **P (facets, solved gains)** | 1.7e-6 Jy | **3.0e-7** | 0 |

So rang's H5parm export, the facet regions (polygon, point, direction
name) and the facet-to-direction mapping reproduce WSClean's
`-apply-facet-solutions` predict to float32 rounding.

**Imaging controls: C0 fails, so arm I is not read (setup outcome).**

| Control | dirty, rel. interior diff | image | boundary band |
| --- | --- | --- | --- |
| C0 (no facets) | **5.0e-3** (limit 1e-3) | 5.0e-3 | 2.6e-4 |
| C1 (facets, unit gains) | 5.0e-3 | 5.0e-3 | 2.6e-4 |
| C2, candidate (a) / (b), facet d1 | 1.3e-2 / 3.3e-1 | 6.5e-1 / 3.7e-1 | – |

The mismatch exists without facets or solutions, so it is between rang's
`fits_image` and WSClean 3.7's dirty image of this MS, not in the facet
code. C2 picks no candidate; it also shows that WSClean writes `-image.fits`
and `-image-pb.fits` (and `-beam.fits`) when facet solutions are applied,
so the frozen expectation "`-image.fits` carries 1/c" was wrong: the
flat-gain product is presumably `-image-pb.fits` (amendment A2).

**Cost (indicative).** WSClean `-j 8`: predict 1.8-2.4 s, image 1.7-3.4 s,
0.24-0.41 GB. Rang (8 threads): predict 4.7-5.6 s, facet image 6.6-8.4 s per
case (four full-field grids, as section 1 says).

**Outcome under section 6.** H and P pass: facet prediction with per-facet
gains matches WSClean. Imaging is a setup outcome: the no-facet control
fails, the cause is open (amendment A2), arm I is not measured, and DD2's
imaging half is not done.

## 8. For the coordinator

(Updated 2026-11-23 after A3-A5: the imaging gap is closed as setup, and
the remaining C2 difference is below.)

- Mergeable as the predict half of DD2: the H5parm export and facet region
  writer (`tools/oracles/dd2/dd2.py`), and the DD cap evidence (88
  iterations, 1.9e-6 on P3). No core code changed.
- Not done: facet imaging (arm I). Next step, frozen before it runs: find
  why rang's dirty image of `dd1.ms` differs from WSClean 3.7's by 0.5 % of
  the peak without facets (A2's diagnostics narrow it to the uv weighting
  or gridding of WSClean's PSF), then rerun C0-C2 with `-image-pb.fits` as
  the flat-gain product, then arm I.
- WSClean's predict reads `<name>-model-pb.fits` when facet solutions are
  applied (A1); DD3's major cycle must write that file.

## Amendments

**A1, 2026-11-23, setup (no output compared yet).** With
`-apply-facet-solutions`, WSClean 3.7's `-predict` reads the flat-gain model
`<name>-model-pb.fits`, not `<name>-model.fits` (C1's first run stopped with
a CFITSIO error on the missing file; C0 had run). The run script now writes
the same model image under both names; nothing else changes. Run `-01` is
restarted into a fresh scratch directory.

**A2, 2026-11-23, post hoc (after C0-C2 were read; arm I unread).**
Diagnostics of C0, not part of any gate. The difference is not geometric:
the four bright sources' peak positions agree to under 0.005 pixel at up to
600 pixels from the centre, the peaks to 5e-5. Rang's dirty image is
WSClean's times 0.997 plus a PSF-shaped residual of about 0.3 % of each
source's peak, at every source including the centre. WSClean's own PSF
(`-make-psf`) differs from rang's by 4.9e-3: 0.7474 against 0.7425 one pixel
from the centre, equal further out (WSClean's PSF is slightly broader).
Ruled out: the w sign (flipping it gives 0.72), `divide_by_n` (5.0e-3),
single precision (5.0e-3), a frequency (uv) scale of ±0.1-0.3 % (worse in
every case). Open: WSClean's weighting or gridding of this MS (the predict
direction matches to 3e-7). For the rerun, the flat-gain comparison product
is to be `-image-pb.fits`, a change made after reading C2.

**A3, 2026-11-23, post hoc diagnosis of C0, then a frozen addendum (before
any rerun).** *Diagnosis.* Earlier parity runs (DF2b, the GeMClean
benchmark) also passed `-no-min-grid-resolution`; adding it leaves C0 at
5.0e-3 (WSClean logs that small inversion is not used here). The two PSFs'
Fourier transforms have a constant ratio 1.002985 at every uv radius, and
`1.002985 × PSF_rang − PSF_WSClean` is 0.002985 at the centre pixel and
below 5e-6 everywhere else: WSClean leaves out a set of visibilities spread
over the uv plane holding 0.2985 % of the weight. 0.2976 % of the
visibilities have |u| or |v| beyond 1/(2Δ) = 25,783 λ, the Nyquist limit of
the unpadded 4″ grid (longest |u|, |v| 30,400 λ; Nyquist pixel 3.39″),
which gives f/(1−f) = 0.2985 %. So WSClean 3.7 drops visibilities outside
the unpadded image's uv range, and rang's gridder keeps them. This is a
**setup mismatch**: DD2's 4″ pixel undersamples the longest baselines. It
is a difference of behaviour on undersampled images, not a gridding
difference on a Nyquist-sampled one.

*Addendum (frozen).* Rerun as `dd2-20261123-02` with everything in sections
3-6 unchanged except the following.
- The image grid is 3200 × 3200 pixels of 3″, which keeps the 2.67° field
  and is below the 3.39″ Nyquist pixel. The model image and the facet masks
  follow it. Components are again dropped within 3 pixels of a boundary.
- C2 and arm I compare `-dirty.fits` with rang's facet image times
  `1/sqrt(c)`, and **`-image-pb.fits`** (the flat-gain product) with rang's
  times `1/c`. `-image.fits` is reported, not gated.
- All controls (C0, C1, C2) and both arms (P, I) are rerun, P included,
  since the grid changed.

**A4, 2026-11-23, setup, after reading run `-02`.** At 3″ WSClean 3.7
switches on its minimal-inversion grid ("Minimal inversion size: 3751 ×
3751" without facets, "2043 × 1387" per facet), which the 4″ run had not
used. Run `-02` (recorded, not a gate): predict C0 1.1e-3, C1 2.8e-3, P
2.9e-3 of the peak; image C0 3.1e-4 (pass), C1 2.8e-3 (boundary band
1.1e-2); C2 matches neither candidate (a: dirty 1.3e-2, image-pb 6.8e-3).
DF2b and the GeMClean benchmark, the runs that matched WSClean to 1e-5 or
better, also passed `-no-min-grid-resolution`. *Addendum (frozen):* rerun as
`-03` with `-no-min-grid-resolution` added to every WSClean call, everything
else as A3.

**A5, 2026-11-23, run `-03` results and post hoc diagnosis of C2.** Run
`D:/rang/outputs/dd2-20261123-03` (WSClean with A4. The prepare and rang
outputs are copied from `-02`, since they do not depend on WSClean's
settings. Archive `results/dd2-facet-imaging/run-03/compare.json`; `-02` is
`results/dd2-facet-imaging/run-02-compare.json`):

| Case | relative difference | gate |
| --- | --- | --- |
| predict C0 / C1 / **P** | 4.5e-6 / 3.1e-7 / **3.7e-7** | pass (1e-4) |
| image C0 dirty, image | 4.0e-8 | pass (1e-3) |
| image C1 dirty, image-pb | 7.9e-8 (boundary band 3.4e-8) | pass |
| C2 candidate (a): dirty / image-pb, facet d1 | 1.3e-2 / 6.8e-3 | fail |
| C2 candidate (b): dirty / image-pb, facet d1 | 3.3e-1 / 4.1e-1 | fail |

So the gridding matches WSClean, and so do facets with unit gains. The 0.5 %
gap of run `-01` is closed: setup, not a gridding difference.

C2, post hoc and not gated. On facet d1, the best single scale between
rang's uncorrected-normalisation image and WSClean's gives
1/scale² = 8.012 for `-dirty.fits` and 1/scale = 8.022 for `-image-pb.fits`.
Candidate (a) is c = 8.031, within 0.24 % of both. Candidate (b) is 4.52.
So the scaling convention is (a): dirty times 1/sqrt(c), flat gain times 1/c.
But after the best scale a residual of 1.3e-2 (dirty) remains. With d1's gain
non-unit, the facets with **unit** gains also differ from rang's
(identical, by C1) plain dirty image: up to 1.7e-2 in facet d0, 5e-3 to
1.5e-2 at every distance from the boundaries, except deep inside facet d2
(5.3e-8 beyond 300 pixels). WSClean's image of a facet therefore depends on
another facet's gains. Rang's model (each facet imaged from all visibilities
corrected by that facet's own gains) does not have this, and the source read
in section 2 does not explain it. It is a real difference in facet-imaging
behaviour, not in gridding. Its mechanism is open: candidates are the facet
sub-image boxes with padding, and the stitching. Arm I is not read.
