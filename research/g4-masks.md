# Rang: masks, tapers and uv range in GeMClean (task G4)

Status, 2026-11-09: **implemented; protocol frozen (section 3) before the first comparison; not yet
measured.**

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

## For the coordinator

(Filled in at hand-back.)
