# Big plan task DF2b: `gridder="wgrid"` in the imaging drivers, and the C/I/K/L1 archives against WSClean 3.7's wgridder

Protocol frozen 2026-10-30 on branch `df2b-wgrid` (from `origin/main`
`3b875e0`), before any driver change. Task DF2b of [big-plan.md](big-plan.md)
("DDFacet/killMS" in "Documentation, teaching and upstream fixes"): wire the
exact gridder of DF1/DF2a ([df1-wgridder.md](df1-wgridder.md),
[df2-wgridder-speed.md](df2-wgridder-speed.md), `core/src/wgridder.rs`) into
the imaging drivers of tasks C, I, K and L1 as `gridder="wgrid"`, and
re-tolerance their image archives against WSClean 3.7's wgridder.

**Status at freeze: proposed.** Nothing below is implemented or measured
except the labelled precondition (section "Precondition").

## Scope and owner files

1. `gridder="wstack"|"wgrid"` in `core_grid.invert` and the drivers
   `core_imaging.image_job` (task I, with `run` and `python -m
   rang.core_imaging run --gridder`), `core_campaign.image_arm` (task K: the
   argument and its receipt field only) and `examples/run_core_gridder.py`
   (task C, `--gridder`, positional form unchanged); the CLI option through
   `rang-core imaging run --gridder` (shared `core_cli.py`, diff listed for
   the coordinator) and `rang-core gridder run ... --gridder` (the script's
   own argument). Receipts record the gridder and, for `wgrid`, ε and the
   kernel plan.
2. A two-weight entry point (open item 3 of DF2a): the reader weight and
   the imaging weight passed separately, their product formed in the core
   as an f32 × f32 multiply widened afterwards, so the drivers' `weights *
   imaging_weights` copy disappears. Kept only if bit-identical to
   `fits_image(weights * imaging_weights)` (gate G2 below).
3. Extension bindings for the `_ex` entry points (open item 5) in
   `core/py/src/lib.rs` (a coordinator file: applied locally, diff listed),
   so `core_wgridder` uses `rang._core` and stops building its standalone
   library (`RANG_DF1_LIB` and the standalone build stay as the fallback
   for an extension without the bindings).
4. The re-tolerancing: the C, I, K and L1 image comparators with `wgrid`,
   against the archived w-stacking images, against the archived
   exact-gridder images where they exist, and against WSClean 3.7's
   wgridder on the same inputs. Nothing archived is rewritten; new numbers
   go to `research/results/df2b-wgrid.json`.

Owner files: `python/rang/core_grid.py`, `python/rang/core_wgridder.py`,
`python/rang/core_imaging.py`, `python/rang/core_campaign.py` (`image_arm`
only), `examples/run_core_gridder.py`, `examples/compare_core_wgridder.py`,
`examples/compare_df2b.py` (new), `tests/test_df2b_wgrid.py` (new), this file
and `research/results/df2b-wgrid.json`. The two-weight entry point needs an
additive change in `core/src/wgridder.rs` (one `Weights` variant) and
`core/src/ffi_wgridder.rs` (new entry points; DF1's and DF2a's unchanged);
neither file is in the owner list, so both diffs are listed for the
coordinator as well. Not edited: `core_campaign_array.py` (L1's driver; see
"L1" below), `grid.rs`, the archived runs.

## The driver interface (frozen)

`core_grid.invert(uvw, frequencies, data, weights, imaging_weights, width,
height, scale_arcsec, w_layers, kernel_size, oversampling, padding,
gridder="wstack", epsilon=1e-6)`:

- `wstack` (default, the archive reproducer): the existing call, unchanged;
  output bit-identical to `3b875e0` (gate G1). The returned dict gains one
  key, `"gridder": "wstack"`; `stats` is unchanged.
- `wgrid`: `core_wgridder.fits_image` with the two weights (f64, ε 1e-6, one
  pass for dirty and PSF, data and weights read in place), WSClean's FITS
  orientation and PSF-centre normalisation (DF1 item 0). `w_layers`,
  `kernel_size`, `oversampling` and `padding` are accepted and ignored (the
  exact gridder needs no padding) and recorded. `stats` has the same keys:
  `image_weight` = Σ f64(f32(w · iw)), `gridded_count` = #(w · iw ≠ 0),
  `visibility_weight_sum` = Σ f64(w) over those, `max_gridded_weight`,
  `min_w`/`max_w` = the plan's `wmin_d`/`wmax_d` (|w| in wavelengths over the
  gridded samples, WSClean's log quantity), `psf_normalization` = image
  weight / raw PSF centre (so `core_campaign_array.grouped_invert`'s
  `dirty · W / N` sum holds unchanged), `n_w_layers` = the plan's planes.
  Sums are NumPy row-block sums (not `grid.rs`'s sequential order; the
  drivers' 1e-6/1e-9 relative checks are far above that). The kernel plan
  (`info`) is returned as `"wgridder"`.
- Threads: `RAYON_NUM_THREADS`; outputs bit-identical at any count (DF2a).

L1's driver (`core_campaign_array.image_arm` → `grouped_invert`) passes its
image dict to `core_grid.invert` as keywords, so `gridder` and `epsilon` in
that dict reach the call without editing the file. For `wgrid`, L1 is
imaged in **one call** (no channel groups; the groups existed for
w-stacking's memory), frozen; four groups are reported beside it.

## Inputs

- **C** (fifteen jobs): `outputs/tv-next-imaging-wsl-20261029-01` and the
  WSClean oracle export `outputs/core-c-20261029-01` through
  `run_core_gridder.py`; the dumped gridder inputs of the same jobs,
  `outputs/p2-gridder-20261030-01/inputs-c` (P2), for the cost runs and the
  WSClean MS.
- **I** (the same fifteen jobs through `core_imaging.run`, its own reader
  and Briggs weights).
- **K** (six arms): the archived fetched bytes are gone (DF1), so K is
  measured on P2's dumped gridder inputs `inputs-k` (as DF1's `kpixels`
  and DF2a), plus `core_campaign.image_arm` in a unit test.
- **L1** (whole array, 53 stations, 41,786 rows × 2048 channels, 1024² at
  1.5″): an image-only replay. The local LUNO tiles (checked against their
  receipts) are decoded and the state built by L1's own functions; the
  `original` arm's gains and additions are read from L1 run `-01`
  (`gains/original.npz`, `flags/original.npz`, hashes checked against the
  archive); `corrected_stokes` and the Briggs weights give the gridder
  inputs, saved once (`compare_df2b.py dump-l1`). No solve, flagger or TV
  loop is repeated. The `tricolour-firstpass` and `tv-policy` arms are
  dumped the same way for the reported residual-RMS call (wgrid only).

## Oracle: WSClean 3.7's wgridder (deviation: no DF0 container)

DF0's oracle container and `df0-oracles.md` do not exist. The WSClean 3.7
binary on the host is O-CASA's image `rang-o-casa:6.7.6.14`
(`sha256:24822b40…`, Ubuntu 24.04 + KERN-10 `wsclean=3.7-1kern1`,
`/usr/bin/wsclean` SHA256 `f098c035…`, python-casacore 3.7.1), used here
(recorded as a deviation from the plan's "DF0").

- **The MS.** WSClean's `-pol I` reader hands the gridder 0.5(XX + YY) and
  4 min(w_XX, w_YY) (task C). `compare_df2b.py write-ms` (inside the
  container) writes, from each dumped gridder input, XX = YY = the Stokes
  sample, XY = YX = 0, `WEIGHT_SPECTRUM` = f32(w · iw) / 4 on all four
  correlations (exact; checked), FLAG where that weight is zero, and the C
  jobs' archived antennas and phase centre (K and L1: their own antennas
  where dumped, else the four stations' six baselines in row order). With
  `-weight natural` WSClean's imaging weight is one, so it grids exactly the
  core's weighted samples. Precondition below: this MS reproduces the
  archived WSClean 3.6 Briggs image pixel for pixel under w-stacking.
- **The run.** `wsclean -size W H -scale S -weight natural -pol I
  -data-column DATA -gridder wgridder -wgridder-accuracy 1e-6 -j 1 -abs-mem 4
  -niter 0 -make-psf -no-update-model-required -no-min-grid-resolution
  -no-reorder` (padding left at its default 1.2: the exact image does not
  depend on it), `--network none`, one thread (deterministic kernel choice;
  O-CASA: `-j 4` is not bit-reproducible). WSClean's log does not print the
  precision it grids in; it is not assumed.
- **Counters before pixels.** WSClean's `WSCIMGWG` and `WSCNVIS` must equal
  the core's `image_weight` (1e-9 relative) and `gridded_count`, or the
  pixel comparison of that input is not reported.

## Comparisons and tolerances (frozen)

Metric: L∞ of the difference over the reference image's peak |·| (dirty),
absolute for PSFs (peak one); RMS, the central half (`[H/4:3H/4,
W/4:3W/4]`) and the outer two pixels reported beside it.

- **G1 — `wstack` bit-identity (gated).** Before any change (code
  `3b875e0` plus this protocol), the C driver's 30 FITS, the I run's 30 FITS
  and its `result.json` numbers, `core_grid.invert` on the six `inputs-k`
  arms (float64 arrays), the PC1 L1 precondition's replay images, and L1's
  dumped `original` input gridded with four groups are hashed
  (`outputs/df2b-20261030-01`). After implementation the same runs must give
  identical SHA256s of every image and identical image numbers.
- **G2 — two-weight entry and driver wiring (gated).** Every `wgrid` image
  of every driver is bit-identical (SHA256 of the float64 arrays) to
  `core_wgridder.fits_image(uvw, freq, data, weights * imaging_weights, …)`
  through the same extension on the same inputs. Otherwise the two-weight
  path is dropped (recorded) and the driver keeps the product.
- **G3 — bindings (gated).** `compare_core_wgridder.py hashes` through the
  extension equals DF2a's archived hashes (`outputs/df2-20261030-02/threads-final.json`,
  20 outputs) and `gates` passes DF1's five criteria; the standalone build
  is not invoked (no `core/target/df1-standalone` build in that process).
- **T1 — `wgrid` against archived exact-gridder images (gated where they
  exist).** The restated bound of DF2a's open item 4, set from the measured
  rounding floor of a legitimate reordering on these inputs
  (precondition): permuting the input rows moves the C image by 1.5e-11
  (dirty, at the border) and 2.1e-11 (PSF) and the K image by 1.8e-15;
  DF2a's own code changes moved images by 6–35× that floor (DF2a vs DF1:
  1.0e-10 against 1.7e-11 on `wide-0p3rad`, 2–6e-14 against this 1.8e-15
  on K). Frozen bound: **≤ 100 × the measured floor of that archive's
  input** (max of dirty and PSF): K 1.8e-13 against DF2a's reference arrays
  of DF1's code (`outputs/df2-20261030-01/ref/k_*_f64_eps1e-06_*.npy`, six
  arms, dirty and PSF). C and I: DF1's `science/c-run/images` and
  `science/i-run/images` are float32 FITS, so the floor there is the
  float32 quantum: **every pixel of f32(wgrid) within one float32 ulp of the
  archived pixel at the image's peak (L∞ ≤ 2⁻²³ × peak)**, number of
  differing pixels reported. DF1 used two `vis2dirty` calls (dirty plan
  `|vis|² w ≠ 0`), DF2a one pass (plan `w ≠ 0`); no C or K input has a
  visibility with zero data and nonzero weight (counted in the
  precondition), so the plans coincide. L1: **no exact-gridder archive
  exists**; T1 does not apply.
- **T2 — `wgrid` against the archived w-stacking images (reported, with a
  frozen prediction).** These archives are WSClean's padding-1.2
  Kaiser–Bessel images; DF1 measured the exact gridder 19–32 % of the peak
  away at the edge and 0.3–0.6 % in the central half (aliasing, not
  rounding). Prediction: central-half L∞ ≤ 1 % of the peak for the C, I and
  K dirty images (L1 reported only: a 64-station PSF, untested). Task A's
  w-stacking tolerances (8.8e-6 dirty, 2.8e-6 PSF, and the I metric
  tolerances) compare w-stacking with w-stacking and are not re-applied as
  gates; I's comparator (`compare_core_imaging.py`) and K's and L1's image
  metrics are rerun with `wgrid` and their moves reported (DF1 saw 23 of 860
  I values move outside A's tolerances, no sign change).
- **T3 — `wgrid` against WSClean 3.7's wgridder (gated, per archive).** On
  the same inputs (C: all fifteen jobs; I: its wgrid FITS against the same
  WSClean images, the I inputs being C's jobs; K: the six arms; L1:
  `original`), WSClean at `-wgridder-accuracy 1e-6`: **dirty L∞ ≤ 1e-5 of
  the peak and PSF L∞ ≤ 1e-5** (10 ε, the DF1 convention against an exact
  reference: each code is within ~0.1–0.4 ε of the DFT in DF1's gates, and
  WSClean's float32 FITS adds ≤ 6e-8 of the peak). Reported beside it,
  not gated: WSClean at its default accuracy 1e-4 and at 1e-8 (whether
  the agreement follows ε, i.e. what precision WSClean used), and a
  diagnostic of the core image with `divide_by_n=True` (whether WSClean's
  wgridder divides by n). A T3 pass also closes DF1's open item 4 (an
  external oracle of `fits_image`'s orientation and normalisation).
- **L1 reconstruction gate (gated, before any L1 `wgrid` number is
  trusted).** The dumped `original` input gridded by `wstack` with four
  groups (L1's frozen settings) must reproduce L1 run `-01`'s archived image
  metrics (peak, residual RMS, off-source RMS, with the archived boxes)
  within 1e-9 relative (PC1's tolerance for the P2 image bits) and its FITS
  pixels within one float32 ulp at the peak.

## Cost (reported)

Per image (dirty + PSF), each in a fresh process (`compare_df2b.py image`),
`RAYON_NUM_THREADS=4`, one-minute load recorded: wall of the gridder call
and whole-process peak RSS (`ru_maxrss`, inputs included; RSS after loading
the inputs beside it) for `wstack` and `wgrid`, three repeats for C (one
job, `clean-full`) and K (six arms), one `wstack` run (the reconstruction
gate run) and three `wgrid` runs for L1, plus one explicit 16-thread `wgrid`
run on L1. WSClean: the container's `/usr/bin/time` wall and peak RSS of
the whole WSClean run (MS read, PSF and dirty, FITS) and its own
`Inversion:` time from the log, at `-j 1` (the gated runs) and `-j 4`
(timing only).

## Precondition (measured before the freeze, labelled)

Run `outputs/df2b-20261030-00-precondition` (code `3b875e0` plus
`examples/compare_df2b.py` as committed with this protocol):

- **Rounding floor** (`floor`, seed 2032, ε 1e-6, f64, the exact gridder of
  `3b875e0` through its standalone build): rows permuted against rows in
  order, L∞ / peak: C `clean-full` dirty 1.5e-11 (border; interior 2.2e-12),
  PSF 2.1e-11; K `original` dirty 1.8e-15, PSF 1.4e-15. The C field is
  0.02 rad, so this is not correction amplification but the four-station
  sky-wide sidelobes' cancellation (84 weighted rows; as DF2a's slice).
- **MS harness** (`ms-inputs`, `make-ms`, `wsclean --gridder wstacking`): the
  MS written from C's dumped `clean-full` input with natural weights,
  imaged by WSClean 3.7 w-stacking with task C's settings, equals the
  archived WSClean 3.6 Briggs FITS (`outputs/core-c-20261029-01/images/clean-full-*`)
  **pixel for pixel** (dirty and PSF, L∞ 0); `WSCIMGWG` 322612.468523026
  and `WSCNVIS` 9169 equal; w = [6.52933, 148.919] λ as archived.
  (`WSCVWSUM` differs by construction: the imaging weight is folded into
  the visibility weight.) The pixel and header comparison is a scratch
  script (`harness-check.json` in the run directory). One `-gridder wgridder -wgridder-accuracy 1e-6`
  run was made to read its log (no precision or kernel is printed); its
  pixels were not compared before this freeze.
- **Plans**: no C or K input has a visibility with zero data and nonzero
  weight (21 inputs, all 0).

Failures are recorded as frozen; anything decided after this commit is
labelled post hoc.
