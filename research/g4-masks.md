# Rang: masks, tapers and uv range in GeMClean (task G4)

Status, 2026-11-09: **implemented and measured** (protocol frozen before the first comparison;
verdicts in section 9).

Goal (finish plan, G4; depends on G3): GeMClean gains WSClean 3.7's `-fits-mask`, `-auto-mask`
(with `-abs-auto-mask`, `-auto-mask-nmiter` and the default `dual` major-iteration mode),
`-taper-gaussian` (and the Tukey and edge tapers), `-minuv-l` / `-maxuv-l` and `-minuvw-m` /
`-maxuvw-m`; `rang-core image` passes them, and `rang.core_pipeline` builds them into the gemclean
call so that C5b can set them per self-calibration round. Oracle: WSClean 3.7. Without the new
options the output stays byte-identical to main. No novelty claim. First task done natively on
Windows (section 7 records the friction).

## 1. What WSClean 3.7 does (read in its source)

WSClean `v3.7` (`4f395b28abb5`) with radler `76fe4474c31c`, aocommon `aa4d6a47b864` and
schaapcommon `b553fd254c55`, cloned read-only to WSL `~/Build/tmp/20261109-g4-wsclean-src`, the
commit of `rang-wsclean-native:3.7`. Paths are relative to the WSClean tree; radler's are under
`external/radler/cpp`.

**Selection.**

- `-minuv-l`, `-maxuv-l`, `-taper-gaussian`, `-taper-tukey`, `-taper-inner-tukey`, `-taper-edge`,
  `-taper-edge-tukey` act on the **cells of the weight grid**, not on the visibilities
  (`io/imageweightcache.h`, `initializeWeightTapers`; `structures/imageweights.cpp`). A visibility
  takes its cell's value (`GetWeight`), so a cut or taper is evaluated at the cell's lower corner,
  `u = (x − W/2) / (W Δx)`, `v = y / (H Δy)` (`xyToUV`) on the padded (1.2×) half-plane grid. The
  order: finish (natural, uniform, Briggs), rank filter, Gaussian taper, then the inner Tukey taper
  or the minimum (`u² + v² < min²` zeroed), then the outer Tukey taper or the maximum
  (`u² + v² > max²` zeroed), then the edge Tukey taper or the edge. Briggs' normalisation and the
  rank filter's means are therefore computed before the cuts. The MF weights of `-join-channels`
  get the same tapers (`SetMFWeights`).
- `SetGaussianTaper(beam)`: `h = 1 / (2π beam)`, `m = h · 2 sqrt(2 ln 2)` with the constant in
  `long double` (x87 on the oracle), `m ← −2 m²`, cell `× exp((u² + v²) / m)` where nonzero. The
  beam is parsed with arcseconds as the default unit (`Angle::Parse(..., kArcseconds)`).
- `tukeyFrom0ToN(x, n) = ½ (1 + cos(π (x − n) / n))`; the outer Tukey taper multiplies cells with
  `(max − n)² < d² ≤ max²` by `tukey(max − d, n)`, the inner one cells with `min² ≤ d² <
  (min + n)²` by `tukey(d − min, n)`; the edge tapers measure from the grid's largest `u` and `v`.
- `-minuvw-m`, `-maxuvw-m` select **rows** (`MSSelection::IsSelected`, schaapcommon): a row is
  dropped when `sqrt(u² + v² + w²)` in metres is below the minimum or above the maximum (strict).
  Dropped rows enter neither the weight grid nor the images, and get no model column.
- With a Gaussian taper wider than the theoretic beam, the theoretic beam becomes the taper
  (`math/imageoperations.cpp`, `DetermineBeamSize`; `main/wsclean.cpp` sets `theoreticBeamSize`), so
  multiscale's scales follow the taper; the PSF fit starts from it.

**Masks** (`radler.cc`):

- `-fits-mask` (`ReadMask`): same width and height as the image, one plane or one per output
  channel; a pixel is in the mask when its value is nonzero (`!= 0.0`, NaN included). The Högbom
  peak search and the sub-minor loop's pixel selection only take masked pixels
  (`peak_finder::FindWithMask`, `SubMinorLoop::findPeakPositions`); multiscale's scale peaks and
  sub-minor loops likewise. The noise estimate for thresholds is over the whole image.
- `-auto-mask` / `-abs-auto-mask` (`Perform`): every major iteration estimates `σ` of the
  integrated residual by `MedianAndStdDevFromMAD` (1.48260221850560 × MAD of the finite pixels in
  single precision, even counts averaged). Phase 1 cleans to `max(σ · auto_mask, abs_auto_mask,
  abs_threshold)` (inside the FITS mask if given). When a major iteration's minor loop ends without
  wanting another (threshold reached, nothing cleaned, budget spent), the mask is finished:
  `Auto-masking threshold reached; continuing next major iteration with deeper threshold and mask.`
  The default strategy `dual` then continues image-based in the same major iteration, inside the
  mask, at the final threshold (`max(σ · auto_threshold, abs_threshold)`) and the continued gain
  `max(0, 1 − (1 − mgain) / (1 − achieved))`, `achieved = 1 − |end peak / start peak|`
  (`CalculateContinuedLoopGain`); a phase-1 iteration that hands back normally also continues
  inside the mask so far, at `mgain`. In phase 2 the minor-loop gain doubles (`min(1, 2 gain)`),
  local RMS is dropped, and the run stops after `-auto-mask-nmiter` (default 2) further major
  iterations. The threshold radler holds persists between iterations (`SetThreshold` is only called
  in phase 1, with `-auto-threshold`, and in the finishing continuation).
- **The Högbom mask** is built from the model's nonzero pixels the first time it is used
  (`SetAutoMaskMode`, guarded by `auto_mask_.empty()`) and **never grown after that**, so with
  `dual` it is the model after the first minor loop of major iteration 1. Multiscale keeps one mask
  per scale (`MultiScaleAlgorithm`): while tracking (phase 1) every sub-minor loop marks its
  component centres in its scale's mask (`UpdateAutoMask`); while using (phase-1 continuations and
  phase 2) each scale's peak search and sub-minor selection is confined to its own mask, and the FITS
  mask is ignored.
- `settings.cpp:491`: `-auto-threshold` at or above `-auto-mask` is an error.
- CARACal's selfcal (`workers/selfcal_worker.py`, `schema/selfcal_schema.yml`, the shipped
  sources in `outputs/c1-sources-20261105/caracal-8f7bb363`) uses `cleanmask_method: wsclean`,
  `cleanmask_thr: [10, 6]` as `-auto-mask`, `clean_cutoff` as `-auto-threshold`, `local-rms` off by
  default (`cleanmask_localrms: False`), and `-maxuv-l` with `-taper-tukey`, `-taper-gaussian` and
  `-minuvw-m` when set. `-local-rms` is not needed for that default and is refused here.

## 2. Implementation (implemented)

- `core/src/weights.rs`: `UvTapers` and `WeightGrid::apply_tapers`, all seven options in WSClean's
  order on the cells; the Gaussian's `long double` constant as an `f64` pair with an FMA product.
  `imaging_weights_tapered`; `imaging_weights` is it with no taper (unchanged results).
- `core/src/gemclean/input.rs`: `Selection.min_uvw_m`, `max_uvw_m` in `row_mask` (UVW read only
  when a limit is set); `gridding_weights_tapered`. `stokes::imaging_weights` takes the tapers.
- `core/src/gemclean/mask.rs`: the FITS mask reader (BITPIX 8/16/32/64/−32/−64, one plane, the
  image's size), radler's noise estimate, `continued_gain`, and `AutoState`, radler's phase machine
  (thresholds, the switch, the continuation, the doubled gain, `-auto-mask-nmiter`).
- `core/src/gemclean.rs`: `run_masked` (Högbom): the working map's tiled argmax takes a mask
  (`Working::set_mask`; tiles without masked pixels hold the bound 0); the cycle-start peak, every
  pick and the threshold checks are inside the mask; with the automatic mask the major loop follows
  `AutoState`, and a continued minor loop runs inside the mask in the same cycle (the working map
  made exact first). `run_with_bound` is `run_masked` without masks.
- `core/src/gemclean/joined.rs`: `run_joined_masked`, the same on the integrated residual, the
  Högbom mask the union of the channels' nonzero model pixels.
- `core/src/gemclean/multiscale.rs`: `run_multiscale_masked`: the FITS mask in `find_maxima` and the
  sub-minor pixel selection; per-scale automatic masks tracked from the sub-minor models' nonzero
  pixels and used in phase 2 and in continuations; the doubled gain sets each scale's gain
  `gain / psf_peak` and the activation rule.
- `core/src/bin/gemclean.rs`: the options; `-taper-gaussian` in arcseconds by default; the
  theoretic beam is `max(1 / longest baseline, taper)`; the tapers on every weight path (single,
  per output channel, MF, polarisations); `-minuvw-m` / `-maxuvw-m` also limit the rows the model
  column gets. With a mask, `<name>-mask.json` and one log line per auto-masked major cycle.
- **Refused, with a message**: `-local-rms*`, `-casa-mask`, `-horizon-mask`, `-clean-border`,
  `-major-iteration-mode` other than `dual`, a mask with several planes, masks with several
  polarisations, `-gram-operator`, `-audit` or `-stop-rule certified`; `-auto-mask` without `-mgain`
  or `-minor-to-threshold` (radler's stages are defined on the peak fraction; GeMClean's measured
  rule has no counterpart); `-auto-threshold ≥ -auto-mask` (WSClean's error).
- **Departures, by design** (recorded before any comparison): GeMClean's Högbom loop is its own
  (lazy exact corrections, not radler's sub-minor loop), as in G2-G5; at a cycle start without the
  automatic mask the run ends when the masked exact peak is below the threshold (GeMClean's rule),
  with it the run follows radler's `another_iteration_required`. f64 throughout, radler f32.
- Unit tests: tapers on cells (corner rule, Gaussian formula, Tukey midpoint, no-op default);
  radler's MAD; the continued gain; the phase machine; the masked peak; a FITS box mask confining
  Högbom and multiscale components; the automatic mask switching and leaving a source below its
  threshold uncleaned.

## 3. Protocol (written 2026-11-09, committed before the first comparison)

### Settings

GeMClean natively on Windows (`gemclean.exe`, profile `gemclean`, rustc 1.93.1, `x86-64-v3`);
WSClean 3.7 in `rang-wsclean-native:3.7` (WSL docker) with `-gridder wgridder
-no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I -no-update-model-required`, as G2-G9. Common
options: `-size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -mgain 0.8
-nmiter 1000 -data-column DATA -field 0 -j 16`, and `-abs-threshold 0.0001` unless the run says
otherwise. Both imagers read the same MS; nothing is written to it. Each run under
`tools/heavy_lock.py`.

| run | data | options beyond the settings | gated |
| --- | --- | --- | --- |
| T1 | S2 | `-niter 0 -taper-gaussian 10` (asec, the default unit) | S |
| T2 | S2 | `-niter 0 -minuv-l 300 -maxuv-l 20000` | S |
| T3 | S2 | `-niter 0 -minuvw-m 150 -maxuvw-m 5000` | S |
| T4 | S2 | `-niter 0 -minuv-l 300 -taper-inner-tukey 200 -maxuv-l 20000 -taper-tukey 5000` | S |
| T5 | D2 (G3, 16 channels) | `-niter 0 -channels-out 4 -join-channels -taper-gaussian 8asec -minuv-l 300` | S |
| T6 | S2 | `-niter 0 -taper-edge 2000 -taper-edge-tukey 1000` | S |
| F1 | S2 | `-fits-mask <S2 truth mask>` (Högbom) | S, M |
| F2 | S2 | `-fits-mask <S2 truth mask> -multiscale` | S, M |
| A1 | S2 | `-auto-mask 6 -auto-threshold 1`, no `-abs-threshold` (Högbom) | S, M, X |
| A2 | H4 | `-multiscale -auto-mask 6 -auto-threshold 1`, no `-abs-threshold` | S, M, X |
| A3 | H4 | `-multiscale -auto-mask 6 -auto-threshold 1 -taper-gaussian 8asec -minuv-l 300`, no `-abs-threshold` | S, M, X, B |
| A4 | D2 | `-channels-out 4 -join-channels -fit-spectral-pol 2 -auto-mask 6 -auto-threshold 1`, no `-abs-threshold` | S, M, X |
| P | the pilot (`20261103-gemclean-heldout/real/cal2.ms`, 256 channels) | `-size 4096 4096 -scale 3asec -multiscale -auto-mask 6 -auto-threshold 1`, no `-abs-threshold` | S, M, X |
| H | held out (below) | `-multiscale -auto-mask 6 -auto-threshold 1 -taper-gaussian 8asec -minuv-l 300 -maxuvw-m 6000`, no `-abs-threshold` | S, M, X, B |

Truth masks (F1, F2): from S2's catalogue only (`s2.json`), never from an imager's output: discs of
radius 6 pixels around every point of `S ≥ 30 mJy` and the disc of radius 2 FWHM around the Gaussian;
the ten points below 30 mJy (10.3-28.3 mJy, S2's faintest; a first draft said 1 mJy, which leaves
none out, and was changed before any run) are left out of the mask on purpose: they must stay in
the residual. Written as float32 FITS with the WCS of WSClean's T0 dirty image (untapered; the WCS
is the same in every T run); data in WSClean's orientation (`data[y, x]`).

### Criteria

Definitions as G5: `σ` is 1.4826 MAD of WSClean's residual on the inner field (central `2N/3`);
`Ω` the restoring-beam area in pixels from WSClean's header; an aperture of `N` pixels has noise term
`ε = 3 σ √(N / Ω)`; flux is the sum of the model image in the aperture.

**A. Without the new options, byte-identical to main.** Measured first (section 5): main
`0d6230d` built natively does **not** reproduce G2's and G3's Linux reference hashes (S1 and D1-C1
differ in every file, the dirty image included; Windows' UCRT maths against glibc). The rule is
therefore native against native: `main-native` (`gemclean-main.exe`, from a clean `git archive` of
`0d6230d`, sha256 `701eb781…`) and the G4 binary run G2's identity set (S1-S3, H1-H4 in the default
and coarse forms, the pilot at 256 channels) and G3's D1-C1 and D1-C3 natively, and every FITS file
of the G4 binary must have main-native's SHA-256. One differing file fails A.

**S. Selection** (every gated run, every file WSClean writes; for joined runs every channel and
MFS). `WSCNVIS` equal; `WSCIMGWG` and `WSCVWSUM` within 1e-6 relative; dirty image and PSF: the
largest |GeMClean − WSClean| at most 1e-5 of the largest |WSClean| of the file (G9's bound). For
cleaned runs the dirty image and PSF are the files compared. Restoring beam: `BMAJ`, `BMIN` within
1e-3 relative (reported against the untapered pair's agreement).

**B. Scales follow the taper** (A3, H): GeMClean's theoretic beam agrees with WSClean's
`Theoretic beam` line to the printed precision, and the scales (rounded) agree with its `- Scale`
lines (G5's criterion B).

**M. Mask behaviour.**

- M1, confinement: every GeMClean component pick (the report's steps) lies in the mask in force:
  the FITS mask (F1, F2); for A runs, every pick of a phase-2 or continued minor loop lies in the
  automatic mask, checked by GeMClean's own record (`mask.json` and the unit tests) and, for
  Högbom, by the model: every nonzero model pixel of either imager outside the truth support is
  reported. For F1 every nonzero model pixel of both imagers lies in the mask; for F2 every
  component centre of GeMClean in the mask, and WSClean's model support inside the mask dilated by
  the largest kernel half-side used (reported).
- M2, flux: for every truth aperture (G5's group apertures; points of `S/σ ≥ 200` as 6-pixel
  discs; on P the source mask `M` and region `R` of G5's criterion D) `|F_G − F_W| ≤ 0.02 |F_W| +
  √2 ε` (G5's 2 %, for the same reason: the component sequences differ after the first picks).
- M3, residual: the rms of GeMClean's residual in each aperture at most `max(1.5 r_W, r_W + 0.5 σ)`;
  for F1 additionally the masked-out points (`S < 30 mJy`) keep their residual peak: GeMClean's value
  at each such point within `3 σ` of WSClean's.

**X. Auto-mask switch-over** (A runs, P, H). From WSClean's log: the major iteration of
`Auto-masking threshold reached` and the `Estimated standard deviation of background noise` of
every major iteration; from GeMClean's `mask.json`. X1: the finishing major iteration is the same.
X2: in every major iteration up to and including the finishing one, GeMClean's σ within 1 % of
WSClean's printed value (or within its printed precision when that is coarser). X3: major cycles in
total equal, or GeMClean within one of WSClean.

**Reported, not gated:** components, major cycles, wall time (shared host; no timing claim); model
support overlap of the two imagers; the T runs' dirty agreement against the untapered T0 pair (S2,
`-niter 0`); peak memory is not measured natively (no GNU time on Windows).

### Held-out sky H

H4's recipe at dec −60 (the simulator's `M1` sky with new seeds: 30 points 5-300 mJy, 6 Gaussians
FWHM 20-200″, a tail of 25 Gaussians), 8 channels 1312.5-1487.5 MHz, 2 h at 8 s, 20 µJy natural
noise (`examples/gemclean_bench_simulate.py --sky M1 --sky-seed --noise-seed`). Its seeds are drawn
only after the freeze: a commit of `fp-g4-masks` and the sha256 of the `gemclean.exe` built from it,
both recorded in section 4 first; the seeds are the first 8 and the next 8 hex digits of
`sha256("<commit> <binary sha256> G4H")` as integers, moved on by 8 digits on a collision with
`python/rang/simtruth.py` `SEEDS` or the simulator's tables. Development runs (T, F, A, P) may change
GeMClean; after the freeze nothing changes without a post-hoc label, and H is not redrawn. All of
S, M, X and B apply to H.

### Not scored

The imaging-weight column itself (`-store-imaging-weights`; the header sums and images stand in for
it); masks with one plane per output channel (refused); `-local-rms`; joined polarisations with
masks (refused); Q against the truth through the exact gridder.

**Order of gate A** (added before any G4 output was seen, 2026-11-09): main-native first runs
`s1-def` a second time; if it does not reproduce its own hashes, A is reported as undetermined, not
failed. The full identity set runs once, on the freeze binary (section 4); development binaries run
`s1-def` only, as an early warning. The native-against-native rule above was set after measuring
main only (section 5), before any G4 binary existed.

## 4. Freeze record

Written 2026-11-09 after the development runs (section 6), before H was simulated. No code changed
after the protocol commit, so the freeze is the protocol commit itself.

- Code: `b13f7d357def1a64acdd5339ff6a78d560231c7a` (fp-g4-masks).
- Binary: `D:\rang\outputs\g4-bin\gemclean-g4.exe`, profile `gemclean`, rustc 1.93, native Windows,
  sha256 `f45a92ddfcd66ac3d6cda1ad1ee8fafe006992a6a8ecdf92f5ef0181269e8ae9` (provenance file
  beside it; the one "dirty" file at build time was `research/tool-timings.md`, line endings only).
- Seeds (`seeds.py b13f7d3… f45a92dd…`, digest `ba01b2ca…`, no collision): sky **3120673482**,
  noise **1953963431**. They follow from the two values above; computed when the freeze was
  decided, a few minutes before this record was written, and not used before it was committed.
- Post-hoc additions fixed here, before H: criterion B′ and T6′ (section 6), and the scorer fixes
  of section 6. H is scored on the frozen criteria and on B′.
- Erratum to section 3: S2 has **nine** points below 30 mJy (10.3, 10.9, 12.3, 14.0, 24.7, 25.4,
  26.9, 27.1, 28.3 mJy), not ten.

## 5. Measured: main on Windows against the Linux references

Main `0d6230d`, built natively (`gemclean-main.exe`, `D:\rang\outputs\g4-bin`), run on S1 (default
form) and D1-C1 (`D:\rang\outputs\g4-20261109-02\identity\main`): every FITS file differs from the
G2/G3 hashes made on Linux, the dirty image included. The difference is therefore upstream of CLEAN,
in the weights or the gridder; the likely cause is the C runtime's transcendental functions (UCRT on
Windows against glibc: `exp`, `sin`, `cos` of the gridding kernel and the phase terms are not
correctly rounded in either and can differ in the last bit). Not investigated further here (an owner
item: whether the Linux hashes stay the reference). An earlier, halted attempt queued WSClean's T
batch behind the lock; it never started (`g4-20261109-01/w_batch-T.log`), so no comparison output
existed before this protocol was committed.

## 6. Measured: development runs (T, F, A, P)

Binary `gemclean-g4.exe` (b13f7d3, section 4) against WSClean 3.7. Runs in
`D:\rang\outputs\g4-20261109-01\runs\{g4,wsclean}\<run>`, scores in `runs\g4\score-<run>.json`
(`score.py`, `table.py`), job logs `*_job-*.log` there. "Max flux diff" is over apertures with
`|F_W| > 10 ε`; "σ max diff" over the major iterations up to WSClean's finishing one.

| run | dirty/PSF max diff | WSCIMGWG rel | BMAJ G/W − 1 | M2 fail | M3 fail | max flux diff | finishing G/W | majors G/W | σ max diff | verdicts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |
| T0 | 2.5e-07 | 2e-09 | – | – | – | – | – | – | – | S pass |
| T1 | 3.6e-07 | 7e-11 | – | – | – | – | – | – | – | S pass |
| T2 | 9.3e-08 | 2e-09 | – | – | – | – | – | – | – | S pass |
| T3 | 7.8e-08 | 3e-09 | – | – | – | – | – | – | – | S pass |
| T4 | 9.2e-08 | 2e-09 | – | – | – | – | – | – | – | S pass |
| T5 | 8.1e-08 | 4e-10 | – | – | – | – | – | – | – | S pass |
| T6 | 2.5e-07 | 2e-09 | – | – | – | – | – | – | – | S pass (vacuous) |
| F1 | 3.1e-07 | 2e-09 | −0.280 | 0/48 | 0/48 | 0.001 | – | – | – | S FAIL (beam) M pass |
| F2 | 3.1e-07 | 2e-09 | −0.280 | 0/48 | 0/48 | 0.002 | – | – | – | S FAIL (beam) M pass |
| A1 | 3.1e-07 | 2e-09 | −0.280 | 0/51 | 0/51 | 0.006 | 6/8 | 8/10 | 0.178 | S FAIL (beam) M pass X FAIL |
| A2 | 1.7e-07 | 2e-09 | −0.268 | 0/25 | 2/25 | 0.017 | 5/5 | 6/6 | 0.098 | S FAIL (beam) B′ pass M FAIL X FAIL |
| A3 | 3.3e-07 | 3e-11 | −0.253 | 0/25 | 0/25 | 0.003 | 5/5 | 6/7 | 0.047 | S FAIL (beam) B FAIL B′ pass M pass X FAIL |
| A4 | 1.8e-07 | 4e-09 | −0.311 | 0/19 | 0/19 | 0.001 | 6/6 | 7/8 | 0.023 | S FAIL (beam, MFS NVIS) M pass X FAIL |
| P | 5.0e-08 | 1e-12 | −0.087 | 0/2 | 0/2 | 0.002 | 4/4 | 6/6 | 0.006 | S FAIL (beam) B′ pass M pass X pass |

**Selection (S).** The tapers, uv cuts and `|uvw|` row cuts agree: dirty images and PSFs within
3.6e-7 of the peak (bound 1e-5) and `WSCIMGWG` within 4e-9 (bound 1e-6), on every run and on every
channel and MFS file. Every frozen S failure is the restoring beam or a header convention, both on
main before G4:

- GeMClean's fitted restoring beam is narrower than WSClean's on every cleaned run (F1: 10.0″ × 8.0″
  against 13.9″ × 8.3″), G9's finding 6, unchanged by G4 (no beam code in the diff). Against the
  untapered pair (A2, H4's sky, `BMAJ` off by 26.8 %) the tapered A3 is off by 25.3 %: the taper
  does not add to the disagreement.
- A4's MFS dirty image: WSClean's `WSCNVIS` (3628800) is one channel's count and its `WSCVWSUM` a
  quarter of GeMClean's total; the per-channel files agree. A main convention (G3 gated only
  `WSCIMGWG`), not a G4 change.
- **Scorer fixes after the first T run** (no gate's meaning changed): at `-niter 0` WSClean writes
  `WSCNVIS = WSCVWSUM = 0` and fits no beam (`BMAJ = 0`), so those checks count only on the cleaned
  runs, which write them. The row and uv cuts of T2-T4 are therefore tested through `WSCIMGWG` and
  the images.
- T6 (`-taper-edge 2000`) is vacuous: the edge cuts cells beyond 66.8 kλ, the longest baseline is
  38.2 kλ, and T6 equals T0. **T6′ (post hoc):** `-taper-edge 35000 -taper-edge-tukey 5000`
  (section 6.1).

**Masks (M).** FITS mask: no GeMClean pick outside the mask (F1, F2), no model pixel of either
imager outside it in F1, and the nine masked-out points keep their residual (9/9 within 3σ of
WSClean's). Automatic mask: no pick outside the mask in any phase-2 or continued minor loop
(`g-mask.json` `outside_picks`; A1: 1080 masked picks). Fluxes within 1.7 % in every aperture (bound
2 % + √2 ε). A2 fails M3 on two 6-pixel point apertures (residual rms 83 and 71 µJy against
WSClean's 42 and 46 µJy; bounds 63 and 69 µJy). Multiscale models are nonzero on every pixel in both
imagers (kernel tails), so the support counts of F2 and the multiscale A runs carry no information.

**Switch-over (X).** σ of major iteration 1 agrees in every run to the printed digits. The phase
structure is radler's: in WSClean's log a continued minor loop inside the mask follows every
phase-1 iteration, and the gain doubles only after `Auto-masking threshold reached`; GeMClean's
`g-mask.json` shows the same. The finishing iteration agrees on A2, A3, A4 and P; major cycles are
within one on all but A1. σ of later iterations drifts by 0.6-18 % because the component sequences
differ after the first picks (as in G5), so the frozen 1 % bound fails on every simulated run. A1
(Högbom) finishes at 6 against 8: GeMClean's own Högbom loop (lazy exact corrections, by design,
section 2) cleans deeper per major cycle, so its σ falls faster from iteration 4 on (−1.5 %, −7 %,
−16 %) and its first minor loop reaches 6σ two iterations earlier. This is not a phase-machine
difference and was not changed. H is multiscale and does not exercise the Högbom automatic mask.

**Scales (B).** As frozen, B fails: WSClean prints `Theoretic beam = 5.4''` before the taper
replaces it, while its beam-fit line says `theoretical=8''` and its scales follow 8″ (21, 43, 85,
171, 341, 683 px), as GeMClean's do. GeMClean reports each scale's phase-2 gain, which radler
doubles after the switch (WSClean's last `- Scale` block shows 0.2 for scale 0, the first 0.1).
**B′ (post hoc):** the theoretic beam against the fit line's `theoretical=` value, scales, bias
factors and PSF peaks against the first block, gains against the last: pass on A2, A3 and P.

### 6.1 T6′ (post hoc)

`-taper-edge 35000 -taper-edge-tukey 5000` on S2 at `-niter 0`. The taper reaches the data:
WSClean's dirty image moves by 5.2e-3 of the peak from T0, and `WSCIMGWG` goes from 2.6592e9 to
2.6501e9. GeMClean against WSClean: dirty image within 2.5e-7 of the peak, `WSCIMGWG` within 2e-9.
S pass.

### 6.2 Gate A (byte identity, native against native)

main-native's `s1-def` run twice gives identical files (5/5), so A is determined. The full set
(S1-S3, H1-H4 and the pilot at 256 channels, each in the default and coarse forms, plus D1-C1 and
D1-C3): **18 runs, 150 FITS files, every one with main-native's SHA-256. A met.** Hashes are in
`D:\rang\outputs\g4-20261109-02\identity\{main,main-rep,g4dev,g4}\img`, logs in `id_job-*.log`.

## 7. Native Windows

The first G task done natively. The heavy lock is shared with E1 (one job at a time across
Windows and WSL; most of this task's wall time was lock waits). A session restart killed check run
3, and a WSL job launched without a wait never started, so every long job now writes START, RUN rc
and END lines (`job.ps1`, `g_job.ps1`, `id_job.ps1`, `w_job.sh`, `wait_end.ps1`). `Set-Content`
writes CRLF into tracked files. No GNU time, so no peak memory. WSClean runs in WSL docker reading
`/mnt/d`.

## 8. Measured: held-out sky H

Simulated after the freeze record (section 4) was committed (8a64030): M1, sky seed 3120673482,
noise seed 1953963431, `D:\rang\outputs\g4-20261109-03\data\h.ms` (14,515,200 visibilities, DFT
check 3.2e-14). Options as frozen: multiscale, `-auto-mask 6 -auto-threshold 1 -taper-gaussian
8asec -minuv-l 300 -maxuvw-m 6000`. Runs and scores are in `g4-20261109-03\runs`.

| criterion | result | verdict |
| --- | --- | --- |
| S selection | dirty 3.1e-7, PSF 1.0e-7 of the peak; `WSCIMGWG` 1.9e-10; `WSCNVIS` 14,311,578 in both (the `-maxuvw-m` cut); `WSCVWSUM` 4e-16 | met |
| S beam | `BMAJ` −26.4 %, `BMIN` −18.1 % (G9's finding 6, as on every run) | FAIL |
| B (frozen) | WSClean prints `Theoretic beam = 6.95''` before the taper replaces it; GeMClean 8.00″ | FAIL |
| B′ (post hoc) | 8″ against the fit line's `theoretical=8''`; scales, bias factors, PSF peaks and phase-2 gains agree | met |
| M1 | no pick outside the automatic mask | met |
| M2 | 27/27 apertures; largest flux difference 0.9 % | met |
| M3 | 25/27; two point apertures at 53 and 59 µJy against WSClean's 33 and 38 µJy (bounds 50 and 56 µJy) | FAIL |
| X1 | finishing iteration 5 in both | met |
| X2 | σ equal in iterations 1, 2 and 5; 6.1 % and 1.3 % off in iterations 3 and 4 | FAIL |
| X3 | 7 major cycles in both | met |

## 9. Verdicts against the frozen gates

| gate | development (T, F, A, P) | held-out H |
| --- | --- | --- |
| A byte identity without the new options | met: 18 runs, 150 files | – |
| S selection (weights, cuts, tapers, images, headers) | met on every run except A4's MFS `WSCNVIS` / `WSCVWSUM` (main's convention) | met |
| S restoring beam within 1e-3 | not met on any cleaned run (main's beam fit, G9 finding 6) | not met |
| B (B′ post hoc) | B not met (the protocol named the wrong log line); B′ met on A2, A3 and P | B not met; B′ met |
| M1 confinement | met everywhere | met |
| M2 flux | met everywhere | met |
| M3 residual | not met on A2 (2/25 apertures); met elsewhere, F1's masked-out points 9/9 | not met (2/27) |
| X1 finishing iteration | met on A2-A4 and P; not met on A1 (Högbom, 6 against 8) | met |
| X2 σ within 1 % | not met on A1-A4; met on P | not met |
| X3 major cycles within one | met except on A1 (8 against 10) | met |

Summary: the selection options (tapers, uv and `|uvw|` cuts) reproduce WSClean 3.7 to within 3.6e-7
of the peak on every run, the held-out one included, and leave the output unchanged when they are
not used (A). The FITS and automatic masks confine every pick and follow radler's phase machine.
They finish on the same major iteration on every multiscale run and match fluxes within 1.7 %. Four
frozen gates fail:

- the restoring beam (main's beam fit);
- the 1 % bound on σ per iteration: the component sequences diverge after iteration 2, as in G5,
  so the bound was set too tight;
- the residual rms in two point apertures per H4-type sky;
- the Högbom automatic mask on S2, which finishes two iterations early.

No novelty claim.

## 10. Not checked

The imaging-weight column; masks with several planes or polarisations (refused); `-local-rms`;
`-abs-auto-mask` against WSClean (unit-tested only); `-auto-mask-nmiter` other than 2; the Högbom
automatic mask on a held-out sky; peak memory (no GNU time on Windows); a Linux reproduction of
these runs (section 5). Wall times were on a shared host and dominated by lock waits, so they
support no timing claim.

## For the coordinator

Proposed STATE line: "G4 (masks, tapers, uv range in GeMClean): implemented and measured against
WSClean 3.7 (`research/g4-masks.md`). The selection options agree to 3.6e-7 of the peak, and
without them the output is byte-identical to main on 150 files. Masks confine every pick and finish
on WSClean's major iteration on multiscale runs. Frozen gates not met: the restoring beam (main's),
σ per iteration within 1 %, residual rms in two point apertures, and the Högbom automatic mask
finishing early. Branch fp-g4-masks."

Proposed README index row: `g4-masks.md`: GeMClean `-fits-mask`, `-auto-mask`, tapers and uv range
against WSClean 3.7 (G4).

Owner decisions:

1. Whether the Linux G2/G3 identity hashes stay the reference now that native Windows builds of
   main differ in every file (section 5), or native-against-native becomes the rule.
2. The restoring-beam fit (G9 finding 6) fails every S beam check. Assign it to G7/G8 or to a task
   of its own.
3. Whether to relax X2 (σ per iteration within 1 %) for later tasks: the sequences diverge after
   iteration 2 on every simulated sky, as G5 found for fluxes.
4. A1: the Högbom automatic mask finishes two major iterations earlier than radler on S2, a
   consequence of GeMClean's own Högbom loop. Decide whether that is acceptable for C5b, which uses
   multiscale, or needs a follow-up.
5. The MFS `WSCNVIS` / `WSCVWSUM` convention: WSClean writes one channel's values, GeMClean the
   total.
6. Heavy-lock contention with E1: most of G4's wall time was lock waits.
