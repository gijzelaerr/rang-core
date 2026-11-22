# Rang: GeMClean multiscale with a FITS mask (issue #35)

Status, 2026-11-17: **measured: no mask defect.**

*2026-11-18:* restated against WSClean 3.8 in [wsclean38-rebaseline.md](wsclean38-rebaseline.md) section 7.2:
3.8 still diverges on RM and PM, so this outcome stands; on PM1 3.8 agrees with GeMClean to 3e-4 Jy.

- **Provenance.** The protocol (sections 1-5) was frozen in `51a9e5a` before any run. The post hoc
  section 7 was committed in `6457155`, before any PM number was read.
- **As frozen:** "multiscale difference, not the mask". M1 and C pass. O is not met, because
  WSClean 3.7 diverged on RM and on PM.
- **Under the post hoc `-nmiter 1` arms:** M1, C and O pass. That is the null.
- **What GeMClean does:** it keeps every component centre inside the mask, as WSClean does. The
  flux outside the mask comes from scale shapes centred inside it, in both imagers.
- **What changed:** nothing in the clean path. Added: a per-scale confinement test, help and docs
  lines, and a known limitation (section 8).

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

## 7. Post hoc amendment, 2026-11-17 (after RM and RH, before any PM number)

Labelled post hoc. Sections 1-5 are unchanged and RM is scored against them as frozen.

- **What RM's numbers forced.** On RM both imagers diverged. WSClean logged "Multiscale clean
  diverged" in major iteration 2, after 32,986 components, with 340.6 Jy at the 922-pixel scale.
  GeMClean's multiscale `end` is `Diverged` in its third cycle, after 1,345,339 components. O
  compares two diverged models, so it cannot decide anything. The frozen σ on RM (3.97 mJy) comes
  from WSClean's diverged residual, against 0.54 mJy on RH. That makes the N_out "pass" vacuous.
- **If PM diverges in either imager**, O on PM is recorded as **not met (unscorable)**, as on RM.
  Nothing else changes.
- **One comparison arm per case, `-nmiter 1`** (RM1 on H4, PM1 on the pilot). The settings are
  RM's and PM's with at most one major iteration. On RM, both imagers' first major iteration ended
  before any divergence (WSClean: peak 269.5 → 13.5 mJy in 410 iterations; GeMClean: 396
  components, `PeakRule`). The first minor loop is the stretch where the two runs are still
  comparable. O is scored on RM1 and PM1 as in section 4, with one change: σ is fixed in advance at
  RH's WSClean σ (0.539 mJy) for RM1, and at WSClean's printed σ of major iteration 1 for PM1.
  RM1 and PM1 count only if both imagers end their minor loop at the same level, within 2 % of
  the larger. The level is WSClean's "major iteration threshold" and GeMClean's cycle level,
  `(1 − mgain) · peak_start`. The decision rule of section 5 applies to RM1 and PM1, recorded as
  post hoc.
- **GeMClean wrote MODEL_DATA.** RM, RH and PM ran GeMClean without
  `-no-update-model-required`, so it wrote MODEL_DATA into `h4.ms` and `cal2.ms`. WSClean read
  DATA only, so neither imager's inputs changed. Every later GeMClean run passes the flag, as
  Dms03 did.

## 8. Results (2026-11-17)

Binary `D:\rang\outputs\gemclean-ms-mask-20261117\bin\gemclean-msm.exe` (`51a9e5a`, sha256
`e7e00cfd…`, [provenance](results/gemclean-ms-mask/gemclean-msm.exe.provenance)). The run root is
`D:\rang\outputs\gemclean-ms-mask-20261117`. Scores are in
[results/gemclean-ms-mask/](results/gemclean-ms-mask/) (`score-*.json`). GeMClean's logs and mask
records, and WSClean's scale and iteration lines, are in `logs/` there. The scripts are in
[results/gemclean-ms-mask-scripts/](results/gemclean-ms-mask-scripts/). All runs used the shared
host glacier, 8 slots per run, in the daytime, so no timing claim is made.

| run | imager | components | majors | end | F_in (Jy) | F_out (Jy) | N_out (Jy) | centres outside |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| RM | GeMClean | 1,345,339 | 3 | Diverged | 1.725 | 7.290 | −1.678 | 0 |
| RM | WSClean | 32,986 | 2 | diverged | 2.352 | 347.411 | −0.159 | 0 of 335 logged |
| RH | GeMClean | 41,900 | 5 | – | 1.6888 | 0 | 0 | 0 |
| RH | WSClean | – | – | – | 1.6890 | 0 | 0 | – |
| PM | GeMClean | 426,578 | 3 | Normal | 105.265 | 15.254 | −43.796 | 0 |
| PM | WSClean | 171,353 | 3 | diverged | 104.515 | −62.721 | −110.810 | 0 of 860 logged |
| RM1 | GeMClean | 396 | 1 | Normal | 1.4054 | 2.7191 | 0.0000 | 0 |
| RM1 | WSClean | 410 | 1 | – | 1.4043 | 2.9294 | −0.0285 | 0 of 26 logged |
| PM1 | GeMClean | 916 | 1 | Normal | 81.150 | 0.0922 | −0.0000 | 0 |
| PM1 | WSClean | 925 | 1 | – | 80.744 | 0.0732 | −0.0001 | 0 of 52 logged |

"Centres outside" means two different counts:

- **GeMClean:** `fits_outside_picks`, which tests every recorded centre against the mask file.
- **WSClean:** the centres its log prints (`Iteration …, scale … at x,y`), which are only a sample
  of its components.

In every run, in both imagers, every model pixel outside the mask is nonzero, because of the FFT
tails.

**As frozen (section 5): "multiscale difference, not the mask".**

- **M1 passes on every run.** No GeMClean centre lies outside the mask at any scale.
- **C passes on RH.** The model flux is 1.6888 Jy against 1.6890 Jy, and neither imager has a
  model pixel outside the mask.
- **O is not met on RM or PM.** In both, the oracle diverged. WSClean reported "Multiscale clean
  diverged": on RM with 340.6 Jy at the 922-pixel scale, on PM with −68.2 Jy at the 1250-pixel
  scale. RM's N_out "pass" is vacuous (section 7).

**Post hoc arms (section 7): null.** On RM1 and PM1, M1, C and O all pass:

- **Same stopping level.** Both imagers end the first minor loop at the same level: on RM1
  13.474 mJy against 13.470 mJy, on PM1 83.169 mJy against 83.170 mJy.
- **Same scales, almost the same counts** (GeMClean/WSClean):
  - RM1: 298/298 at scale 0, 21/26 at 115 px, 45/47 at 230 px, 32/39 at 461 px.
  - PM1: 88/88, 102/133, 413/393, 223/224, 85/86 and 5/1, from scale 0 to 156 px.
- **Outside the mask on RM1:** 2.72 Jy in GeMClean and 2.93 Jy in WSClean, outside a 3,394-pixel
  mask that holds only H4's points. This is the 230 px and 461 px shapes, centred on the points,
  taking up the 6.10 Jy of Gaussians that lie outside.
- **Outside the mask on PM1:** 0.09 Jy and 0.07 Jy. PM1's O bounds are wide (σ 3.76 mJy,
  WSClean's printed σ of major iteration 1), but the differences are only 0.02 Jy and 1e-4 Jy.

**What #35 saw.** Dms03 is the same behaviour, cleaned deep:

- The mask confines the centres. Shapes up to 625 px put flux outside the mask's islands.
- At 0.3 mJy (about 1.6σ) the 313-1250 px scales take part, with gains of 141 to 34,809. The model
  outside the mask then grows, positive and negative, in both imagers.
- On the pilot, PM ran Dms03's settings on DATA. Outside the mask it ends with +15.3 Jy, and
  −43.8 Jy negative, in GeMClean; WSClean, which diverged, has −62.7 Jy and −110.8 Jy.
- Dms03's own 3.53 Jy outside the mask and −7.62 Jy negative are of the same kind.
- Its "99 % of pixels" count is the FFT tails. G4's F2 models were nonzero everywhere too.

**Findings outside the fix scope (reported, not changed):**

1. **Divergence differs between the imagers.** radler's divergence limit (4) fired in WSClean on
   both RM and PM. In GeMClean it fired on RM only (cycle 3, after 1.3M components), not on PM.
   Two candidate causes:
   - GeMClean's residual after each sub-minor loop is exact for the image-domain beam
     (`multiscale.rs`, "What is gemclean's"); radler's is not.
   - The component sequences differ after the first loop.

   The runs are not comparable after divergence, so the cause is not separated here.
2. **Deep multiscale inside a mask of small islands is unstable in both imagers.** RM and PM have
   no sound model to compare. A user who wants nothing outside the mask has three options: use
   Högbom (RH, Dm03); cap the scales (`-multiscale-scales`, `-multiscale-max-scales`); or erode the
   mask by the largest shape's half-side. Clipping the shapes to the mask would depart from WSClean
   and is an owner decision.

**Archived multiscale cases (G2-G9, DF5-O, C5b).** No line of the clean path changed. The diff
touches only the help text, a config description, the docs and a `#[cfg(test)]` test, so every
archived output is unchanged by construction. The full `tools/check_all.py`, with its archive and
oracle gates, is left to the coordinator's merge check.

C5b's post hoc oracle-mask arm `mo` (multiscale with a FITS mask) used a mask that confined only
the centres. Its reading, "no better than the automatic mask", stands as a statement about that
behaviour, which WSClean shares.

**Test added:** `gemclean::multiscale::tests::a_fits_mask_confines_the_centres_at_every_scale`.

- **Sky:** 96², with two blobs and a point inside a box mask and one blob outside it; scales 0, 4,
  8 and 16.
- **Cases:** one channel and two joined channels, each with the FITS mask alone and with the FITS
  mask plus the automatic mask.
- **Asserts:**
  - every centre lies inside the mask;
  - two or more non-zero scales clean;
  - model pixels outside the mask lie within the largest used shape's half-side of the box;
  - the outside blob stays in the residual.

## 9. For the coordinator

- **#35 verdict: no mask defect.** GeMClean confines multiscale centres to the FITS mask at every
  scale, as WSClean 3.7 does. The flux outside the mask comes from the shapes. Suggest closing #35
  with this note; the coordinator posts.
- **floor-5 section 4.3 cannot be met with multiscale.** Its requirement, "a masked arm puts no
  component where F is measured", fails for multiscale with a mask in either imager. Dms03's D
  0.363 includes flux in F's pixels, and WSClean would do the same. The options are Högbom (Dm03,
  as used), capped scales, or a mask eroded by the largest shape's half-side.
- **Gated results: none affected.** None uses multiscale with a FITS mask. E2-A and E2-N use
  multiscale with the automatic mask, which has per-scale masks in the same radler structure and
  is gated by G4's X1 and X3. Since no defect was found, none of them is affected.
- **Owner decisions:**
  - whether to clip the shapes to the mask (a departure from WSClean);
  - whether to look into the divergence asymmetry (finding 1).
