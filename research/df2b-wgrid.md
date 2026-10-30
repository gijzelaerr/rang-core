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

**Status now: implemented and measured; every gated criterion passes as
frozen** ([Measured results](#measured-results-2026-10-30-post-freeze-runs-as-frozen)).
`gridder="wgrid"` reaches the C, I, K and L1 image paths. `wstack` stays the
default and is bit-identical to `3b875e0` on every C, I, K and L1 image. The
two-weight entry point is bit-identical to the product, so the drivers no
longer copy `weights * imaging_weights`. `core_wgridder` now runs through
`rang._core`, and DF2a's hashes and DF1's gates pass through it.
Against WSClean 3.7's wgridder (ε 1e-6, same inputs) the exact gridder
agrees within 2.5–4.0e-7 of the peak on all 15 C/I jobs, 6 K arms and L1's
whole-array image (tolerance 1e-5). This closes DF1's open item 4
(orientation and normalisation). It also shows that WSClean does not divide
by n. Against the archived exact-gridder images: K 5.8e-14 (bound 1.8e-13);
C and I within one float32 ulp. Against the archived w-stacking images the
move is aliasing, as predicted: 17–32 % of the peak at the edge and
≤ 0.56 % in the central half for C/I/K, but only 0.45 % and 0.01 % on L1's
53-station whole-array image. No hypothesis call changes. Per image at 4 threads,
`wgrid` is 2.5–3.8× faster than `wstack` with 2.6–3.2× less memory on four-station
images; on L1 it takes 8.9 s against 23.5 s.

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

## What was built (post-freeze, branch `df2b-wgrid`)

The protocol and harness are `abfb2e4`. The G1 baselines were taken at
`abfb2e4`, before any driver change (`outputs/df2b-20261030-01`). Then:

- **`a62e232` — the core.** `wgridder::Weights::F32Product(a, b)` gives
  the weight of visibility i as `f64::from(a[i] * b[i])`: one float32
  multiply, widened afterwards, exactly NumPy's float32 product. Unequal
  lengths are refused.
  - New C entry points `rang_core_wgridder_vis2dirty_ex2_{f64,f32}` take a
    second weight pointer and the new `WGRIDDER_WGT_F32_PRODUCT` kind.
  - The DF2a `_ex` entry points are unchanged; they now pass a null second
    pointer to the shared body.
  - New Rust test `product_weights_match_their_product`: the dirty image,
    PSF and plan are bit-identical, and a short array is refused.
- **`7e61681` — bindings.** `core/py/src/lib.rs` gains:
  - `wgridder_vis2dirty_{f64,f32}` (through `_ex2`; data complex64 or
    complex128, weights float32 or float64, an optional float32 `wgt2`,
    borrowed in place);
  - `wgridder_dirty2vis_{f64,f32}` (through `_ex`);
  - `wgridder_kernel_row` and `wgridder_last_error`.

  The options are passed as a list of the 18 `WgridderOptions` fields. The
  GIL is released as in every other kernel call.

  `core_wgridder.extension()` uses these bindings whenever they are present
  and `RANG_DF1_LIB` is unset. `backend()` and `library_path()` report which
  path ran. The ctypes standalone build is now only the fallback.
  `fits_image` and `dirty_psf` take `imaging_weights` / `wgt2`, and
  `fits_image` passes gridder keywords through (used for the `divide_by_n`
  diagnostic).
- **`1663cee` — drivers.**
  - `core_grid.invert(..., gridder="wstack", epsilon=1e-6)` behaves as the
    protocol describes. `_weight_counters` computes the counters in row
    blocks of 4,096 without keeping a full product.
  - `core_imaging.image_job` / `run` and `python -m rang.core_imaging run`
    take `--gridder`. The result records `gridder` (and, for wgrid,
    `wgrid_epsilon` and the per-job `wgridder` plan). The FITS get
    `RANGGRID`/`RANGEPS` and `WSCGKRNL` = support, for wgrid only.
  - `core_campaign.image_arm(..., gridder="wstack")` records
    `gridder_name`, `wgridder` and `RANGGRID` (wgrid only).
  - `examples/run_core_gridder.py ... --gridder` uses argparse; the
    positional form is unchanged; it adds `RCGRID` (wgrid only).
  - `rang-core imaging run --gridder` and `recipes/core-imaging.yaml` (the
    cab's `gridder` input) are coordinator files.
  - `tests/test_df2b_wgrid.py` has 6 tests.
  - Every new FITS key is written for `wgrid` only, so `wstack` FITS stay
    byte-identical.
- **`f27cc92` — harness.** `examples/compare_df2b.py` gains `compare` and
  `summary`, and `research/results/df2b-wgrid.json` is added.

**Post hoc, labelled:**

- `core_imaging.main` calls `run` with three arguments when the gridder is
  the default. This keeps task I's dispatch test unchanged.
- The cab input was added to the recipe because
  `test_recipe_cabs_match_the_module_signatures_and_name_no_imager` requires
  the cab inputs to equal `run`'s parameters.

## Measured results (2026-10-30, post-freeze runs as frozen)

**Runs:**

| Run | Contents |
| --- | --- |
| `outputs/df2b-20261030-00-precondition` | Before the freeze |
| `outputs/df2b-20261030-01` | G1 baselines at `abfb2e4`; the L1 dumps `l1-inputs/` |
| `outputs/df2b-20261030-02` | Code `1663cee`: G1 after, G2, G3, the wgrid driver runs, cost images, and WSClean in `wsclean/`. Then `compare.json` |

The compact result is `research/results/df2b-wgrid.json`.

Host: WSL2, 16 threads, 30 GiB. The one-minute load was 10–20 from sibling
tasks during `-02` (2–7 during `-00`/`-01`), so the cost figures are noisy.

### Gated criteria

| # | Criterion | Result | Figure |
| --- | --- | --- | --- |
| G1 | `wstack` bit-identity | **pass** | C: 30 FITS SHA256 and every counter equal. I: 30 FITS and every image number (fits, responses, closures, PSF L∞, diagnostics) equal. K: 6 arms' float64 arrays and stats equal. L1 precondition: replay FITS (14) equal and `all_passed` true. L1 whole-array `original` with four groups: arrays and stats equal |
| G2 | two weights and driver wiring | **pass** | `invert(gridder="wgrid")` is SHA256-equal to `fits_image(weights * imaging_weights)` on 15 C jobs, 6 K arms and 3 L1 arms. The C driver's FITS equal float32 of those arrays. I's wgrid FITS equal C's (I's inputs are C's). K's and L1's driver functions: see "K's and L1's drivers end to end" below (post hoc) |
| G3 | bindings | **pass** | `compare_core_wgridder.py threads` through the extension at 1 and 4 threads: 20 hashes equal to DF2a's `threads-final.json`. `gates`: all of DF1's gated checks pass, the kernel table equals (939 rows), and single visibilities are within 1.9e-12; library `_core.abi3.so` |
| T1 | against archived exact-gridder images | **pass** | K: 5.8e-14 (`tricolour-mild` dirty) against DF2a's references of DF1's code, bound 1.8e-13. C and I: 3.2e-8 of the peak (`omitted-full` dirty) against DF1's float32 FITS, bound 2⁻²³ = 1.2e-7; 250 of 7.9 M pixels flip one float32 ulp. L1: no archive |
| T3 | against WSClean 3.7 wgridder, ε 1e-6 | **pass** | Dirty L∞ / peak and PSF L∞ in the table below. Counters: `WSCIMGWG` within 1.6e-15 relative and `WSCNVIS` equal on all 37 inputs |
| L1 recon | reproduce L1 run `-01` | **pass** | All three arms (`original`, `tricolour-firstpass`, `tv-policy`): peak, residual RMS and off-source RMS within 1.1e-15 relative; FITS within one float32 ulp |

T3 per archive (worst over the inputs; tolerance 1e-5):

| Archive (inputs) | Dirty L∞ / peak | Central half | Border | PSF L∞ |
| --- | ---: | ---: | ---: | ---: |
| C (15 jobs) | 2.67e-7 | 2.67e-7 | 1.45e-7 | 2.47e-7 |
| I (15 jobs, I's FITS) | 2.69e-7 | 2.69e-7 | 1.35e-7 | 2.38e-7 |
| K (6 arms) | 4.01e-7 | 4.01e-7 | 3.03e-7 | 3.91e-7 |
| L1 `original` (34.2 M visibilities, 1024² at 1.5″) | 3.09e-7 | 3.09e-7 | 5.4e-9 | 3.09e-7 |

**Reported beside T3**, on C `clean-full`, K `original` and L1 `original`:

- **WSClean's accuracy sweep** (dirty L∞ / peak against the core at ε 1e-6):

  | WSClean accuracy | C | K | L1 |
  | --- | ---: | ---: | ---: |
  | 1e-4 (its default) | 1.5e-5 | 4.2e-5 | 3.7e-5 |
  | 1e-6 | 2.5e-7 | 4.0e-7 | 3.1e-7 |
  | 1e-8 | 2.5e-7 | 3.3e-7 | 1.7e-7 |

  - At WSClean's default the gap is WSClean's kernel accuracy.
  - At 1e-6 and 1e-8 it stops at 2–4e-7 of the peak, about 3–7 float32 ulp
    at the peak. That is more than one float32 FITS rounding (6e-8).
    WSClean's float32 image buffers are the likely cause. This is not
    verified in WSClean's source: open item.
- **`divide_by_n=True`** in the core moves it away from WSClean. The gap
  becomes 3.2e-5 on C and 4.0e-5 on K (3.1e-7 on L1, where n − 1 < 1.4e-5
  across the field). So WSClean 3.7's wgridder does not divide by n, which
  is `fits_image`'s convention.
- **Orientation and normalisation.** This is the external check that DF1's
  open item 4 asked for. The pixel map, w sign and PSF-centre normalisation
  of `fits_image` agree with WSClean's own wgridder FITS to 4e-7 on every
  input. **Closed.**

### K's and L1's drivers end to end (post hoc, labelled)

The frozen G2 measured K through `invert` on P2's dumps. After the review,
`compare_df2b.py kdriver` (`outputs/df2b-20261030-04-kdriver`, 13.0 s,
499 MB) ran K's own `core_campaign.image_arm`.

**Setup.**

- K's four-station cells are decoded from the local tiles by L1's
  functions.
- K run `-01`'s saved gains and dense additions are used for `original` and
  `tricolour-firstpass`; their SHA256 equal the K archive.

**`core_campaign.image_arm`, both arms.**

- `gridder="wstack"` reproduces K's archived peak, residual RMS and
  off-source RMS within 1.2e-15 relative.
- `gridder="wgrid"`:
  - its images are SHA256-equal to `fits_image(weights * imaging)` on the
    gridder inputs it built;
  - those inputs equal P2's dumps bit for bit;
  - the metrics record `gridder_name` and the plan (8 planes).
  - On `original` the peak is 14.924568 and the residual RMS 0.071682.

**L1's driver.** `core_campaign_array.run` replayed K on four stations with
`image=dict(core_campaign.IMAGE, gridder="wgrid")` and one group (7.7 s).
Against K run `-01`, exactly as PC1's comparison:

- every leaf is equal except the image products of the six arms (hashes,
  peak, residual RMS) and the residual-RMS ratio of hypothesis 0;
- its `original` and `tricolour-firstpass` images are SHA256-equal to those
  of `core_campaign.image_arm` above.

So both drivers' wgrid paths are exercised end to end.

The first run, `-03-kdriver`, gave the same numbers. Its summary flag
`only_image_products_differ` was false only because the predicate counted
the comparison's own `all_equal` leaf. That predicate was fixed and the run
repeated as `-04`.

### T2: against the archived w-stacking images (reported; prediction held)

- **C and I** (WSClean 3.6's archived FITS):
  - dirty L∞ is 16.7–31.5 % of the peak, but ≤ 0.56 % in the central half;
  - PSF 20.8 % (0.55 % central).
  - Prediction (central half ≤ 1 %): **holds**.
- **K** (K run `-01`'s FITS): dirty 19.0 % (0.32 % central), PSF 19.0 %.
  **Holds.**
- These are DF1's aliasing figures again. WSClean's padding-1.2 KB kernel
  folds four-station sky-wide sidelobes into the field edge.
- **L1** (53-station PSF, far sidelobes ≤ 0.04): dirty L∞ is only 0.45 % of
  the peak (0.01 % central, RMS 0.05 %), PSF 0.45 %. The aliasing that
  dominates the four-station archives is small on the whole-array image.
- **I's comparator** (`compare_core_imaging.py`, A's tolerances) fails as
  expected, with 53 failures:
  - 30 header-exact `WSCNWLAY` values (11 planes against 64 layers), by
    construction;
  - the same 23 science values DF1 saw: 12 response fractions, 10 template
    fluxes and one PSF L∞.
  - `omitted-total` moves 0.4917 → 0.5060 and 0.7757 → 0.8117;
    `omitted-adaptation` −0.5103 → −0.4959 and −0.2242 → −0.1883;
    `complete-adaptation` −0.0031 → −0.0020. No response fraction changes
    sign.
  - Template fluxes move by up to 37 % relative, on the near-zero
    `complete-adaptation` coefficient.
  - Exact fields, WCS, weight sums, unit fluxes and closures (3.1e-8 Jy/beam
    difference) pass.
- **K's metrics** (K's `image_metrics`, wgrid against the archive) on
  `original`:
  - peak 14.924568 against 14.924569;
  - residual RMS 0.07168 against 0.07122 (+0.65 %);
  - off-source RMS 3.832 against 3.813.
  - The residual-RMS calls are unchanged. The headline `tv-policy` /
    `tricolour-firstpass` ratio is 0.99994 against 0.99996, still **null**;
    the other two pairs are 1.00000.
- **L1's metrics** (archived boxes 16 / 209 px), wgrid against the archive,
  on `original`:

  | Metric | wgrid | Archive |
  | --- | ---: | ---: |
  | Peak (Jy/beam) | 14.800390 | 14.800389 |
  | Residual RMS | 0.016365 | 0.016424 |
  | Off-source RMS | 0.06879 | 0.07069 |
  | Robust σ of the residual | 3.88 mJy | 4.00 mJy |

  - The residual RMS drops by 0.36 %, the off-source RMS by 2.7 % and the
    robust residual σ by 3 %.
  - The flux recovery and peak pixel are unchanged.
  - The headline residual-RMS ratio (`tv-policy` / `tricolour-firstpass`)
    is 0.995422 against the archive's 0.995419, still **null**.
- **L1 wgrid with four channel groups** against one call: 3.0e-8 of the
  peak. Each group gets its own plan (kernel and planes for its own w
  range), so the sum differs at the ε level, not at rounding. This is why
  the protocol froze one call for wgrid.

### Cost (reported)

Per image (dirty + PSF), fresh process, 4 threads, median of three where
three were run. RSS is the whole process's peak, inputs included:

| Archive | `wstack` | `wgrid` | WSClean 3.7 wgridder, `-j 1` (gated run) | WSClean `-j 4` |
| --- | ---: | ---: | ---: | ---: |
| C `clean-full` (9,169 visibilities, 512²) | 0.66 s, 218 MB | 0.19 s, 68 MB | 2.27 s wall (inversion 2.17 s), 71 MB | 4.37 s (load 19) |
| K, six arms (117 k, 512²) | 0.56–0.70 s, 222 MB | 0.18–0.22 s, 85 MB | 1.59–2.21 s, 71 MB | 2.06 s (`original`) |
| L1 `original` (34.2 M, 1024²) | 23.5 s, 2.74 GB (four groups; 16.9 s in the baseline run at load 5) | 8.9 s (8.7–13.9), 2.41 GB; **16 threads: 4.4 s, 2.45 GB** | 67.7 s, 847 MB | 42.4 s, 847 MB |

- The core's RSS includes the dumped inputs loaded from `.npz` (1.34 GB on
  L1, 41 MB on C/K).
- WSClean's figure is the whole run in the container: the MS read, two
  inversions and the FITS writes.
- The L1 MS (4.4 GB) was written in 27.3 s, 2.4 GB peak.

So the exact gridder is 2.5–3.8× faster per image than the core's w-stacking
at four stations, and 2.6× faster on the whole array at 4 threads. It needs
2.6–3.2× less memory at four stations and 12 % less on L1. Against the same
algorithm in WSClean 3.7 it is 4.8× faster on L1 at 4 threads (7.6× against WSClean's one-thread gated run). That
WSClean figure includes its MS reading, so it is not a pure gridder
comparison.

## Deviations from the plan and the protocol

1. **No DF0.** WSClean 3.7 is O-CASA's image, as stated at the freeze.
2. **WSClean's MS is written from the dumped gridder inputs**, with natural
   weighting and the imaging weight folded into `WEIGHT_SPECTRUM`. It is
   not the job's own MS with Briggs weighting, so T3 tests the gridder and
   not WSClean's weighting (task B tested the weighting). The precondition
   validated this: WSClean 3.7 w-stacking on this MS equals the archived
   WSClean 3.6 Briggs image pixel for pixel.
3. **Inputs.** K is measured on P2's dumps (the fetched bytes are gone).
   L1 is an image-only replay from L1 run `-01`'s saved gains and additions.
   `core_campaign.run` and `core_campaign_array` are not edited:
   - L1's driver takes `gridder` through its image dict;
   - `rang-core campaign run` / `campaign-array run` get no `--gridder`
     (open item).
4. **Files outside the owner list:**
   - `core/src/wgridder.rs` and `core/src/ffi_wgridder.rs` (additive, for
     the two-weight entry point);
   - `recipes/core-imaging.yaml` (cab input, for the recipe signature
     test);
   - the coordinator files `core/py/src/lib.rs` and
     `python/rang/core_cli.py`.

   All of them are listed under "For the coordinator".
5. **Failed tool runs:**
   - The first `compare_core_wgridder.py gates` failed: ducc0 was not in
     the venv. `ducc0==0.42.0` was installed from PyPI and the run
     repeated.
   - The first `compare_df2b.py compare` failed: WSClean's file names
     format 1e-4 as `0.0001`. Fixed and repeated.
   - Neither failure touched a measured image.
6. **Accuracy sweep and `-j 4` runs.** These were run where the protocol
   lists them (C `clean-full`, K `original`, L1 `original`).
7. **L1's receipts do not meet the frozen "ε and the kernel plan" clause.**
   `core_campaign_array.image_arm` stores only `products["stats"]` (and the
   groups), so a wgrid image records its gridder only through the run's
   `settings.image` dict, when `gridder` is passed there, and not the plan.
   The fix belongs in `core_campaign_array.py`, outside this task. Suggested
   lines in `image_arm` after `metrics["gridder_groups"] = ...`:

   ```python
   metrics["gridder_name"] = image.get("gridder", "wstack")
   if "wgridder" in products:
       metrics["wgridder"] = products["wgridder"]
   ```

   For one group, `grouped_invert` must also return `out` unchanged (it
   already does), and for several groups keep `part["wgridder"]` in each
   group record.
8. **Provenance of run `-02`.** Its `head.txt` reads `1663cee` with
   `M examples/compare_df2b.py`. The uncommitted edit was the WSClean run
   names' `-j4` suffix, made before `measure.sh` started. The `compare` and
   `summary` subcommands were added after the runs. All of these are
   harness code, committed in `f27cc92`; no image path was involved.

## Open items

1. `rang-core campaign run` (K) and `campaign-array run` (L1) have no
   `--gridder`: it would need edits to `core_campaign.run` and
   `core_campaign_array.run`, outside this task's owner files. The driver
   functions themselves take it and were run end to end (post hoc
   `kdriver`). L1's receipts lack the plan (deviation 7).
2. WSClean's agreement floor of 2–4e-7 of the peak at accuracies 1e-6 and
   1e-8, above one float32 FITS rounding. The likely cause is WSClean's
   float32 image arithmetic; reading `wgriddingmsgridder` would confirm it.
3. With `wgrid`, L1's channel groups should not be used: they differ by
   3e-8 (per-group plans). L1's driver still defaults to four groups, for
   w-stacking's memory.
4. The default stays `wstack`. Making `wgrid` the default (DF2) changes
   archived numbers outside task A's tolerances: the 23 I values; K's and
   L1's residual RMS by 0.4–0.7 %. DF2 decides, with WSClean 3.7's wgridder
   now as the reference.
5. K's science calls from a fresh fetch (DF1 open item 3) and the L2, L1-M
   and C1 images were not re-imaged here.
6. The DF1/DF2a standalone target `core/target/df1-standalone` is no longer
   built by default; the coordinator may delete it.

## Tool runs

All runs 2026-10-30. Wall and peak RSS come from GNU `time` unless noted.

| Tool | Input | Wall | Max RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `uv venv -p 3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin pip` | worktree | 73.0 s | 1.18 GB | builds `rang._core` |
| `compare_df2b.py floor` | C `clean-full`, K `original` | 48.9 s | 1.02 GB | includes the standalone cargo build (about 40 s) |
| `compare_df2b.py ms-inputs` + `make-ms` + WSClean 3.7 w-stacking and wgridder (precondition) | C `clean-full` | 0.2 + 1.1 + 2.8 + 1.7 s | 55 MB (host) | pixel-identical to the 3.6 archive |
| harness check (scratch script) | precondition run | 0.65 s | 73 MB | |
| `run_core_gridder.py` (base) | 15 C jobs | 6.5 s | 302 MB | |
| `python -m rang.core_imaging run` (base) | 15 I jobs | 5.2 s | 365 MB | |
| `compare_df2b.py kinvert` (base) | 6 K arms | 1.9 s | 242 MB | |
| `precondition_luno_array.py` (base) | K slice, four stations | 12.9 s | 360 MB | pass |
| `compare_df2b.py dump-l1` | whole array, three arms | 36.0 s | 9.2 GB | decode, state, correct, Briggs |
| `compare_df2b.py image` wstack, four groups (base) | L1 `original` | 17.9 s | 2.80 GB | gridding 16.9 s |
| `cargo build --release` (`core/py`, first) | bindings | – | – | **failed**: 12 type errors (`len()` returns `PyResult` on dynamic arrays); fixed with `as_array().len()` |
| `maturin develop --release` ×3 | worktree | 34.4 s (one timed) | 611 MB | |
| `cargo test --release --lib wgridder` | core | 117.2 s | 1.14 GB | 8 passed (build-dominated) |
| `cargo clippy --release --all-targets -D warnings` (core and `core/py`), `cargo fmt` | | 8.6 s | – | clean after `cargo fmt` |
| pytest (first): `test_df2b_wgrid`, `test_core_wgridder`, `test_core_grid`, `test_core_imaging` | 25 tests | 3.1 s | 85 MB | **4 failed**: two test-side errors in the new file and the two task I tests above; fixed |
| pytest, the same files plus `test_core_cli` and `test_core_campaign` | 54 tests | 1.1 s | – | 53 passed, 1 skipped (ducc0, before it was installed) |
| `compare_core_wgridder.py threads` (extension, 1 and 4 threads) | DF1 gate cases | 4.9 s | 65 MB | 20 hashes equal DF2a's |
| `compare_core_wgridder.py gates` (first) | all cases | 0.19 s | 37 MB | **failed**: no ducc0 in the venv |
| `uv pip install ducc0==0.42.0` | venv | 0.6 s | – | public PyPI |
| `compare_core_wgridder.py gates` | all cases | 7.7 s | 86 MB | all gated checks pass |
| `run_core_gridder.py` / `core_imaging run` / `kinvert` / L1 precondition / L1 wstack image (after) | as base | 11.0 / 11.7 / 5.5 / 18.8 / 27.3 s | 0.31 / 0.36 / 0.24 / 0.35 / 2.80 GB | load 10–20 |
| `rang-core gridder run ... --gridder wgrid` | 15 C jobs | 3.8 s | 140 MB | criteria 1–3 pass |
| `rang-core imaging run ... --gridder wgrid` | 15 I jobs | 3.9 s | 212 MB | |
| `compare_core_imaging.py` (wgrid I against the archive) | I run | 1.1 s | 67 MB | exit 1: 53 failures, as reported |
| `compare_df2b.py kinvert --gridder wgrid` | 6 K arms | 1.1 s | 97 MB | |
| `compare_df2b.py image` ×42 (C, K; wstack and wgrid, 3 repeats) | per input | 0.3–0.9 s each | 70–227 MB | table "Cost" |
| `compare_df2b.py image` wgrid ×3 (4 threads), ×1 (16 threads), four groups ×1 | L1 `original` | 11.6–18.8 / 5.6 / 12.0 s | 2.46–2.51 GB | process wall; gridding 8.7–13.9 / 4.4 / 10.8 s |
| `compare_df2b.py image` wgrid and wstack (four groups) | L1 `tricolour-firstpass`, `tv-policy` | 12.2–13.7 / 21.8–27.2 s | 2.45 / 2.80 GB | |
| `compare_df2b.py image` wgrid ×15 | C jobs | 0.3–0.7 s each | 70 MB | |
| `compare_df2b.py make-ms` (container) ×21 | C jobs, K arms | 0.6–1.1 s each | 36–82 MB | |
| `compare_df2b.py make-ms` (container) | L1 `original` | 27.3 s | 2.43 GB | 4.4 GB MS |
| WSClean 3.7 wgridder `-j 1`, accuracy 1e-6 ×21 | C jobs, K arms | 1.6–3.2 s each | 70–71 MB | container wall |
| WSClean 3.7 wgridder `-j 1`, accuracy 1e-4 / 1e-6 / 1e-8 | L1 `original` | 98.1 / 67.7 / 133.2 s | 833–847 MB | |
| WSClean 3.7 wgridder `-j 1`, accuracy 1e-4 and 1e-8 | C `clean-full`, K `original` | 1.9–2.6 s | 70–75 MB | |
| WSClean 3.7 wgridder `-j 4`, accuracy 1e-6 | C `clean-full` / K `original` / L1 `original` | 4.4 / 2.1 / 42.4 s | 70 / 71 / 847 MB | timing only; load about 20 |
| `compare_df2b.py compare` (first) | run `-02` | 35.1 s | 2.87 GB | **failed**: accuracy file names (`0.0001`); fixed |
| `compare_df2b.py compare` | run `-02` | 40.7 s | 2.91 GB | all gates pass |
| `compare_df2b.py summary` | `compare.json` | 0.3 s | – | `research/results/df2b-wgrid.json` |
| `compare_df2b.py kdriver` (post hoc, first) | K four stations, local tiles | 16.0 s | 499 MB | numbers as below; summary predicate counted `all_equal` (fixed) |
| `compare_df2b.py kdriver` (post hoc) | same | 13.0 s | 499 MB | K `image_arm` both gridders; L1 driver replay with wgrid 7.7 s |

## For the coordinator

**STATE paragraph.**

DF2b, the exact gridder in the imaging drivers (big plan), 2026-10-30
(implemented; measured; [df2b-wgrid.md](df2b-wgrid.md)). The imaging paths
of tasks C, I, K and L1 now take `core_grid.invert(...,
gridder="wstack"|"wgrid")`: `run_core_gridder.py --gridder`,
`rang-core imaging run --gridder`, `core_campaign.image_arm` and L1's
driver through its image dict. `wstack` stays the default and is
bit-identical to before on every C, I, K and L1 image. A two-weight entry
point (`Weights::F32Product`, `vis2dirty_ex2`) forms the reader × imaging
weight in the core, bit-identical to the float32 product, so the drivers'
copy is gone. `rang._core` binds the gridder, so `core_wgridder` no longer
builds its standalone library; DF2a's 20 hashes and DF1's gates pass
through the binding. Against WSClean 3.7's wgridder (O-CASA's image, ε
1e-6, run on an MS written from the same gridder inputs), the exact
gridder agrees within 2.5–4.0e-7 of the peak on the 15 C/I jobs, the six K
arms and L1's 34 M-visibility whole-array image. The counters are equal.
That MS harness was first checked pixel for pixel against the archived
WSClean 3.6 image. The comparison closes DF1's open item 4 (orientation
and normalisation) and shows that WSClean does not divide by n; at
WSClean's default accuracy 1e-4 the gap is 1.5–4.2e-5. Against archived
exact-gridder images: K 5.8e-14 (bound 1.8e-13, set from a measured
row-permutation floor); C and I within one float32 ulp. Against the
archived w-stacking images the move is the predicted aliasing: 17–32 % of
the peak at the edge and ≤ 0.56 % in the central half for C/I/K, but
0.45 % and 0.01 % on L1's whole-array image. I's 23 metric values move as
DF1 found, K's residual RMS by +0.65 % and L1's by −0.36 %, and no
hypothesis call changes. Per image at 4 threads the exact gridder takes
0.19 s against 0.66 s (68 against 218 MB) at four stations, and 8.9 s
against 23.5 s on L1 (4.4 s at 16 threads); WSClean 3.7 needs 42 s at
`-j 4`. Open: `--gridder` for `campaign run` and `campaign-array run`, and
the plan in L1's receipts.

**One-line `research/README.md` index entry.**

New, 2026-10-30: DF2b, the [exact gridder in the imaging drivers](df2b-wgrid.md):
`gridder="wgrid"` for C/I/K/L1, `wstack` bit-identical, the archives within
4e-7 of WSClean 3.7's wgridder, two-weight entry point and extension
bindings.

**Plan line for `research/big-plan.md`** (in the DDFacet/killMS
sentence): "DF2b done 2026-10-30 (`df2b-wgrid.md`): `gridder="wgrid"` in the
C/I/K/L1 drivers, `wstack` the bit-identical default, every archive within
4e-7 of WSClean 3.7's wgridder; `--gridder` for the campaign runs open".

**Timing rows for `research/tool-timings.md`:** the rows of "Tool runs"
above, each prefixed `2026-10-30 | big plan DF2b: `.

**Upstream observations (listed, not filed).**

- **Non-RATT, WSClean 3.7** (KERN `3.7-1kern1`):
  1. The log does not state the gridder's precision or kernel. The
     agreement with an exact gridder stops at 2–4e-7 of the peak even at
     `-wgridder-accuracy 1e-8`, which points to float32 image buffers
     after the inversion (not verified in the source).
  2. The default accuracy 1e-4 leaves 1.5–4.2e-5 of the peak. Users who
     compare images at the 1e-6 level need to set it.
  3. The wgridder does not divide by n, consistent with its w-stacking:
     worth a line in the documentation, since ducc0's default
     (`divide_by_n=True`) is the opposite.
  4. On L1 (one run each, load 10–13) accuracy 1e-4 took longer than 1e-6
     (98 s against 68 s). Not investigated.
- **Non-RATT, ducc0 0.42.0:** none new.
- **RATT, caracal-pipeline:** none. **saopicc:** none.

**Shared and non-owner file changes** (applied on the branch; verbatim
diffs against `3b875e0` in the appendix):

- `core/py/src/lib.rs` (coordinator): the six `wgridder_*` bindings and
  their registration.
- `python/rang/core_cli.py` (coordinator): `imaging(..., gridder)` and
  `--gridder`.
- `recipes/core-imaging.yaml` (task I's recipe): the cab's `gridder` input.
- `core/src/wgridder.rs` and `core/src/ffi_wgridder.rs` (DF1/DF2a files, not
  in this task's owner list; additive): `Weights::F32Product`,
  `WGRIDDER_WGT_F32_PRODUCT`, `rang_core_wgridder_vis2dirty_ex2_{f64,f32}`,
  one Rust test.
- No change to `core/src/lib.rs`, `python/rang/core.py`, `README.md`,
  `research/README.md`, `research/STATE.md`, `research/tool-timings.md`,
  `research/big-plan.md`, `research/upstream-notes.md` or
  `research/non-ratt-observations.md`. Their texts are above.

**Ignored output directories:**

| Directory | Size | Contents |
| --- | ---: | --- |
| `outputs/df2b-20261030-00-precondition` | 97M | floor, MS harness, `c-clean-full.ms` |
| `outputs/df2b-20261030-01` | 4.0G | G1 baselines (`base-*`) and the L1 dumps `l1-inputs/` (3 × 1.37 GB; regenerated by `dump-l1` in 36 s; deletable after merge) |
| `outputs/df2b-20261030-02` | 1.1G | G1 after, G2/G3 runs, the wgrid driver runs, `images/` (float64 `.npy` per image), `wsclean/` (21 small MS, FITS, logs, timings), `compare.json` |
| ,  | 24 MB each | post-hoc K  and L1-driver replay ( superseded by ; deletable) |
|  | – | the final check-all |

The L1 MS `outputs/df2b-20261030-02/wsclean/l1-original.ms` (4.4 GB) was
deleted after the comparison. `make-ms` rebuilds it in 27 s from
`l1-inputs/l1-original.npz`; its WSClean FITS, logs and timings are kept.

**Scratch:** `~/Build/tmp/20261030-df2b` (the run scripts `pre.sh`,
`base.sh`, `measure.sh`, the patch helpers and the precondition's harness
check, copied to the precondition run as `harness_check.py`) is deleted at the end.

## Appendix: diffs of shared and non-owner files (against `3b875e0`)

Blank context lines are shown without their leading space (whitespace check); apply with `git apply --ignore-whitespace` or take the files from the branch.

### `core/py/src/lib.rs`

```diff
diff --git a/core/py/src/lib.rs b/core/py/src/lib.rs
index 8cd49b9..8fc7fd1 100644
--- a/core/py/src/lib.rs
+++ b/core/py/src/lib.rs
@@ -25,7 +25,8 @@
 //! did under ctypes (which also released the GIL): do not do that.

 use numpy::{
-    Element, IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArrayDyn, PyReadwriteArrayDyn,
+    Complex32, Complex64, Element, IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArrayDyn,
+    PyReadwriteArrayDyn,
 };
 use pyo3::exceptions::{PyOSError, PyValueError};
 use pyo3::prelude::*;
@@ -38,9 +39,11 @@ use rang_core::ffi_ms_write::{keyword_value, new_column};
 use rang_core::ffi_weights::{
     ImagingWeightInputs, ImagingWeightOutputs, StokesIInputs, StokesIOutputs,
 };
+use rang_core::ffi_wgridder::{self, WgridderOptions};
 use rang_core::ms::{DataType, Table};
 use rang_core::ms_write::TableWriter;
 use rang_core::toy;
+use std::ffi::c_void;

 type Ro<'py, T> = PyReadonlyArrayDyn<'py, T>;
 type Rw<'py, T> = PyReadwriteArrayDyn<'py, T>;
@@ -751,6 +754,403 @@ fn grid_kernel(
     }))
 }

+// ------------------------------------------- exact gridder (DF2b bindings)
+
+/// `WgridderOptions` from its 18 fields in declaration order (sizes and
+/// flags as floats; every value is exact in a double).
+fn wgridder_options(o: &[f64]) -> PyResult<WgridderOptions> {
+    if o.len() != 18 {
+        return Err(PyValueError::new_err("18 gridder options required"));
+    }
+    Ok(WgridderOptions {
+        nx: o[0] as usize,
+        ny: o[1] as usize,
+        pixsize_x: o[2],
+        pixsize_y: o[3],
+        epsilon: o[4],
+        center_x: o[5],
+        center_y: o[6],
+        sigma_min: o[7],
+        sigma_max: o[8],
+        do_wgridding: o[9] as i32,
+        divide_by_n: o[10] as i32,
+        flip_u: o[11] as i32,
+        flip_v: o[12] as i32,
+        flip_w: o[13] as i32,
+        allow_nshift: o[14] as i32,
+        kernel_index: o[15] as i64,
+        nu: o[16] as usize,
+        nv: o[17] as usize,
+    })
+}
+
+/// A borrowed visibility array of either complex precision (or none:
+/// unit visibilities).
+enum VisArg<'py> {
+    Unit,
+    C64(Ro<'py, Complex32>),
+    C128(Ro<'py, Complex64>),
+}
+
+impl<'py> VisArg<'py> {
+    fn extract(a: Option<&Bound<'py, PyAny>>) -> PyResult<Self> {
+        let Some(a) = a else {
+            return Ok(VisArg::Unit);
+        };
+        if let Ok(v) = a.extract::<Ro<'py, Complex32>>() {
+            return Ok(VisArg::C64(v));
+        }
+        if let Ok(v) = a.extract::<Ro<'py, Complex64>>() {
+            return Ok(VisArg::C128(v));
+        }
+        Err(PyValueError::new_err("vis must be complex64 or complex128"))
+    }
+
+    fn len(&self) -> Option<usize> {
+        match self {
+            VisArg::Unit => None,
+            VisArg::C64(v) => Some(v.as_array().len()),
+            VisArg::C128(v) => Some(v.as_array().len()),
+        }
+    }
+
+    fn ptr_kind(&self) -> PyResult<(*const c_void, i32)> {
+        Ok(match self {
+            VisArg::Unit => (std::ptr::null(), ffi_wgridder::WGRIDDER_VIS_UNIT),
+            VisArg::C64(v) => (ptr(v)? as *const c_void, ffi_wgridder::WGRIDDER_VIS_C64),
+            VisArg::C128(v) => (ptr(v)? as *const c_void, ffi_wgridder::WGRIDDER_VIS_C128),
+        })
+    }
+}
+
+/// A borrowed weight array of either real precision, or none.
+enum WgtArg<'py> {
+    None,
+    F32(Ro<'py, f32>),
+    F64(Ro<'py, f64>),
+}
+
+impl<'py> WgtArg<'py> {
+    fn extract(a: Option<&Bound<'py, PyAny>>) -> PyResult<Self> {
+        let Some(a) = a else {
+            return Ok(WgtArg::None);
+        };
+        if let Ok(w) = a.extract::<Ro<'py, f32>>() {
+            return Ok(WgtArg::F32(w));
+        }
+        if let Ok(w) = a.extract::<Ro<'py, f64>>() {
+            return Ok(WgtArg::F64(w));
+        }
+        Err(PyValueError::new_err("weights must be float32 or float64"))
+    }
+
+    fn len(&self) -> Option<usize> {
+        match self {
+            WgtArg::None => None,
+            WgtArg::F32(w) => Some(w.as_array().len()),
+            WgtArg::F64(w) => Some(w.as_array().len()),
+        }
+    }
+
+    fn ptr_kind(&self) -> PyResult<(*const c_void, i32)> {
+        Ok(match self {
+            WgtArg::None => (std::ptr::null(), ffi_wgridder::WGRIDDER_WGT_NONE),
+            WgtArg::F32(w) => (ptr(w)? as *const c_void, ffi_wgridder::WGRIDDER_WGT_F32),
+            WgtArg::F64(w) => (ptr(w)? as *const c_void, ffi_wgridder::WGRIDDER_WGT_F64),
+        })
+    }
+}
+
+/// The `_ex2` gridding entry point of one precision.
+type V2dFn<T> = unsafe extern "C" fn(
+    *const WgridderOptions,
+    usize,
+    usize,
+    *const f64,
+    *const f64,
+    *const c_void,
+    i32,
+    *const c_void,
+    *const c_void,
+    i32,
+    *const u8,
+    *mut T,
+    *mut T,
+    *mut f64,
+) -> i32;
+
+/// The `_ex` degridding entry point of one precision.
+type D2vFn<T> = unsafe extern "C" fn(
+    *const WgridderOptions,
+    usize,
+    usize,
+    *const f64,
+    *const f64,
+    *const T,
+    *const c_void,
+    i32,
+    *const u8,
+    *mut T,
+    *mut f64,
+) -> i32;
+
+/// One gridding call of either precision through the `_ex2` entry point.
+#[allow(clippy::too_many_arguments)]
+fn wgridder_v2d<T: Element>(
+    py: Python<'_>,
+    opts: Vec<f64>,
+    uvw: Ro<'_, f64>,
+    freq: Ro<'_, f64>,
+    vis: Option<&Bound<'_, PyAny>>,
+    wgt: Option<&Bound<'_, PyAny>>,
+    wgt2: Option<Ro<'_, f32>>,
+    mask: Option<Ro<'_, u8>>,
+    mut dirty: Option<Rw<'_, T>>,
+    mut psf: Option<Rw<'_, T>>,
+    mut info: Rw<'_, f64>,
+    run: V2dFn<T>,
+) -> PyResult<i32> {
+    let opts = wgridder_options(&opts)?;
+    let nrow = uvw.as_array().len() / 3;
+    let nchan = freq.as_array().len();
+    let n = nrow * nchan;
+    let npix = opts.nx * opts.ny;
+    let vis = VisArg::extract(vis)?;
+    let wgt = WgtArg::extract(wgt)?;
+    let (vis_ptr, vis_kind) = vis.ptr_kind()?;
+    let (wgt_ptr, mut wgt_kind) = wgt.ptr_kind()?;
+    let wgt2_ptr = match &wgt2 {
+        None => std::ptr::null(),
+        Some(b) => {
+            // Two weights: both float32, multiplied in the core.
+            if wgt_kind != ffi_wgridder::WGRIDDER_WGT_F32 {
+                return Err(PyValueError::new_err("two weights must both be float32"));
+            }
+            wgt_kind = ffi_wgridder::WGRIDDER_WGT_F32_PRODUCT;
+            ptr(b)? as *const c_void
+        }
+    };
+    let sizes_ok = uvw.as_array().len() == nrow * 3
+        && vis.len().is_none_or(|l| l == n)
+        && wgt.len().is_none_or(|l| l == n)
+        && wgt2.as_ref().is_none_or(|b| b.as_array().len() == n)
+        && mask.as_ref().is_none_or(|m| m.as_array().len() == n)
+        && dirty.as_ref().is_none_or(|d| d.as_array().len() == npix)
+        && psf.as_ref().is_none_or(|d| d.as_array().len() == npix)
+        && info.as_array().len() == rang_core::wgridder::N_INFO;
+    if !sizes_ok {
+        return Err(PyValueError::new_err("gridder array sizes disagree"));
+    }
+    let uvw_ptr = ptr(&uvw)?;
+    let freq_ptr = ptr(&freq)?;
+    let mask_ptr = opt_ptr(&mask)?;
+    let dirty_ptr = opt_ptr_mut(&mut dirty)?;
+    let psf_ptr = opt_ptr_mut(&mut psf)?;
+    let info_ptr = ptr_mut(&mut info)?;
+    // SAFETY: every pointer borrows a live NumPy buffer of the checked
+    // length for the duration of the call.
+    Ok(detach(py, || unsafe {
+        run(
+            &opts, nrow, nchan, uvw_ptr, freq_ptr, vis_ptr, vis_kind, wgt_ptr, wgt2_ptr, wgt_kind,
+            mask_ptr, dirty_ptr, psf_ptr, info_ptr,
+        )
+    }))
+}
+
+/// `rang_core_wgridder_vis2dirty_ex2_f64`: data of either complex
+/// precision and weights of either real precision read in place (`wgt2`,
+/// float32, multiplies a float32 `wgt` in the core); `dirty` and/or `psf`
+/// float64 outputs; `info` the plan. Returns the status code.
+#[pyfunction]
+#[pyo3(signature = (opts, uvw, freq, vis, wgt, wgt2, mask, dirty, psf, info))]
+#[allow(clippy::too_many_arguments)]
+fn wgridder_vis2dirty_f64(
+    py: Python<'_>,
+    opts: Vec<f64>,
+    uvw: Ro<'_, f64>,
+    freq: Ro<'_, f64>,
+    vis: Option<&Bound<'_, PyAny>>,
+    wgt: Option<&Bound<'_, PyAny>>,
+    wgt2: Option<Ro<'_, f32>>,
+    mask: Option<Ro<'_, u8>>,
+    dirty: Option<Rw<'_, f64>>,
+    psf: Option<Rw<'_, f64>>,
+    info: Rw<'_, f64>,
+) -> PyResult<i32> {
+    wgridder_v2d(
+        py,
+        opts,
+        uvw,
+        freq,
+        vis,
+        wgt,
+        wgt2,
+        mask,
+        dirty,
+        psf,
+        info,
+        ffi_wgridder::rang_core_wgridder_vis2dirty_ex2_f64,
+    )
+}
+
+/// As `wgridder_vis2dirty_f64`, working in single precision (float32
+/// outputs).
+#[pyfunction]
+#[pyo3(signature = (opts, uvw, freq, vis, wgt, wgt2, mask, dirty, psf, info))]
+#[allow(clippy::too_many_arguments)]
+fn wgridder_vis2dirty_f32(
+    py: Python<'_>,
+    opts: Vec<f64>,
+    uvw: Ro<'_, f64>,
+    freq: Ro<'_, f64>,
+    vis: Option<&Bound<'_, PyAny>>,
+    wgt: Option<&Bound<'_, PyAny>>,
+    wgt2: Option<Ro<'_, f32>>,
+    mask: Option<Ro<'_, u8>>,
+    dirty: Option<Rw<'_, f32>>,
+    psf: Option<Rw<'_, f32>>,
+    info: Rw<'_, f64>,
+) -> PyResult<i32> {
+    wgridder_v2d(
+        py,
+        opts,
+        uvw,
+        freq,
+        vis,
+        wgt,
+        wgt2,
+        mask,
+        dirty,
+        psf,
+        info,
+        ffi_wgridder::rang_core_wgridder_vis2dirty_ex2_f32,
+    )
+}
+
+/// One degridding call of either precision through the `_ex` entry point;
+/// `vis` is the real view (`2 * nrow * nchan` values) of the output.
+#[allow(clippy::too_many_arguments)]
+fn wgridder_d2v<T: Element>(
+    py: Python<'_>,
+    opts: Vec<f64>,
+    uvw: Ro<'_, f64>,
+    freq: Ro<'_, f64>,
+    dirty: Ro<'_, T>,
+    wgt: Option<&Bound<'_, PyAny>>,
+    mask: Option<Ro<'_, u8>>,
+    mut vis: Rw<'_, T>,
+    mut info: Rw<'_, f64>,
+    run: D2vFn<T>,
+) -> PyResult<i32> {
+    let opts = wgridder_options(&opts)?;
+    let nrow = uvw.as_array().len() / 3;
+    let nchan = freq.as_array().len();
+    let n = nrow * nchan;
+    let wgt = WgtArg::extract(wgt)?;
+    let (wgt_ptr, wgt_kind) = wgt.ptr_kind()?;
+    let sizes_ok = uvw.as_array().len() == nrow * 3
+        && dirty.as_array().len() == opts.nx * opts.ny
+        && vis.as_array().len() == 2 * n
+        && wgt.len().is_none_or(|l| l == n)
+        && mask.as_ref().is_none_or(|m| m.as_array().len() == n)
+        && info.as_array().len() == rang_core::wgridder::N_INFO;
+    if !sizes_ok {
+        return Err(PyValueError::new_err("gridder array sizes disagree"));
+    }
+    let uvw_ptr = ptr(&uvw)?;
+    let freq_ptr = ptr(&freq)?;
+    let dirty_ptr = ptr(&dirty)?;
+    let mask_ptr = opt_ptr(&mask)?;
+    let vis_ptr = ptr_mut(&mut vis)?;
+    let info_ptr = ptr_mut(&mut info)?;
+    // SAFETY: as in `wgridder_v2d`.
+    Ok(detach(py, || unsafe {
+        run(
+            &opts, nrow, nchan, uvw_ptr, freq_ptr, dirty_ptr, wgt_ptr, wgt_kind, mask_ptr, vis_ptr,
+            info_ptr,
+        )
+    }))
+}
+
+/// `rang_core_wgridder_dirty2vis_ex_f64`; returns its status code.
+#[pyfunction]
+#[pyo3(signature = (opts, uvw, freq, dirty, wgt, mask, vis, info))]
+#[allow(clippy::too_many_arguments)]
+fn wgridder_dirty2vis_f64(
+    py: Python<'_>,
+    opts: Vec<f64>,
+    uvw: Ro<'_, f64>,
+    freq: Ro<'_, f64>,
+    dirty: Ro<'_, f64>,
+    wgt: Option<&Bound<'_, PyAny>>,
+    mask: Option<Ro<'_, u8>>,
+    vis: Rw<'_, f64>,
+    info: Rw<'_, f64>,
+) -> PyResult<i32> {
+    wgridder_d2v(
+        py,
+        opts,
+        uvw,
+        freq,
+        dirty,
+        wgt,
+        mask,
+        vis,
+        info,
+        ffi_wgridder::rang_core_wgridder_dirty2vis_ex_f64,
+    )
+}
+
+/// `rang_core_wgridder_dirty2vis_ex_f32`; returns its status code.
+#[pyfunction]
+#[pyo3(signature = (opts, uvw, freq, dirty, wgt, mask, vis, info))]
+#[allow(clippy::too_many_arguments)]
+fn wgridder_dirty2vis_f32(
+    py: Python<'_>,
+    opts: Vec<f64>,
+    uvw: Ro<'_, f64>,
+    freq: Ro<'_, f64>,
+    dirty: Ro<'_, f32>,
+    wgt: Option<&Bound<'_, PyAny>>,
+    mask: Option<Ro<'_, u8>>,
+    vis: Rw<'_, f32>,
+    info: Rw<'_, f64>,
+) -> PyResult<i32> {
+    wgridder_d2v(
+        py,
+        opts,
+        uvw,
+        freq,
+        dirty,
+        wgt,
+        mask,
+        vis,
+        info,
+        ffi_wgridder::rang_core_wgridder_dirty2vis_ex_f32,
+    )
+}
+
+/// `rang_core_wgridder_kernel_row` into seven doubles; 1 past the end.
+#[pyfunction]
+fn wgridder_kernel_row(index: usize, mut out: Rw<'_, f64>) -> PyResult<i32> {
+    let Some(p) = sized_mut(&mut out, 7)? else {
+        return Ok(1);
+    };
+    // SAFETY: `p` holds seven doubles.
+    Ok(unsafe { ffi_wgridder::rang_core_wgridder_kernel_row(index, p) })
+}
+
+/// The message of this thread's last status-1 gridder failure.
+#[pyfunction]
+fn wgridder_last_error() -> String {
+    // SAFETY: a null buffer asks for the length only; `buf` then holds it.
+    let n = unsafe { ffi_wgridder::rang_core_wgridder_last_error(std::ptr::null_mut(), 0) };
+    let mut buf = vec![0_u8; n];
+    // SAFETY: `buf` holds `n` bytes.
+    unsafe { ffi_wgridder::rang_core_wgridder_last_error(buf.as_mut_ptr(), n) };
+    String::from_utf8_lossy(&buf).into_owned()
+}
+
 /// `rang_core_flag_rows`; returns its status code.
 #[pyfunction]
 #[allow(clippy::too_many_arguments)]
@@ -1321,6 +1721,12 @@ fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
     m.add_function(wrap_pyfunction!(imaging_weights, m)?)?;
     m.add_function(wrap_pyfunction!(grid_invert, m)?)?;
     m.add_function(wrap_pyfunction!(grid_kernel, m)?)?;
+    m.add_function(wrap_pyfunction!(wgridder_vis2dirty_f64, m)?)?;
+    m.add_function(wrap_pyfunction!(wgridder_vis2dirty_f32, m)?)?;
+    m.add_function(wrap_pyfunction!(wgridder_dirty2vis_f64, m)?)?;
+    m.add_function(wrap_pyfunction!(wgridder_dirty2vis_f32, m)?)?;
+    m.add_function(wrap_pyfunction!(wgridder_kernel_row, m)?)?;
+    m.add_function(wrap_pyfunction!(wgridder_last_error, m)?)?;
     m.add_function(wrap_pyfunction!(flag_rows, m)?)?;
     m.add_function(wrap_pyfunction!(gain_tv, m)?)?;
     m.add_function(wrap_pyfunction!(trend_slopes, m)?)?;
```

### `python/rang/core_cli.py`

```diff
diff --git a/python/rang/core_cli.py b/python/rang/core_cli.py
index ce2d9d3..8a85222 100644
--- a/python/rang/core_cli.py
+++ b/python/rang/core_cli.py
@@ -402,14 +402,16 @@ def environment(run_dir):
     return record


-def imaging(run_dir, archive_dir=None, export_dir=None):
-    """The imaging track replay on the core (task I, `rang.core_imaging`)."""
+def imaging(run_dir, archive_dir=None, export_dir=None, gridder="wstack"):
+    """The imaging track replay on the core (task I, `rang.core_imaging`);
+    `gridder="wgrid"` uses the exact gridder (research/df2b-wgrid.md)."""
     from . import core_imaging

     return core_imaging.run(
         run_dir,
         archive_dir=archive_dir or core_imaging.DEFAULT_ARCHIVE,
         export_dir=export_dir or core_imaging.DEFAULT_EXPORT,
+        gridder=gridder,
     )


@@ -762,6 +764,7 @@ def _configure_imaging(p):
     p.add_argument("run_dir")
     p.add_argument("--archive-dir")
     p.add_argument("--export-dir")
+    p.add_argument("--gridder", choices=("wstack", "wgrid"), default="wstack")


 def _configure_campaign(p):
```

### `recipes/core-imaging.yaml`

```diff
diff --git a/recipes/core-imaging.yaml b/recipes/core-imaging.yaml
index e780dc9..7de08ef 100644
--- a/recipes/core-imaging.yaml
+++ b/recipes/core-imaging.yaml
@@ -16,6 +16,7 @@ cabs:
       run_dir: {dtype: str, required: true}
       archive_dir: {dtype: Directory, required: true}
       export_dir: {dtype: Directory, required: true}
+      gridder: {dtype: str, required: false, default: wstack, info: "wstack (the archive reproducer) or wgrid (the exact gridder, research/df2b-wgrid.md)"}
   rang-core-imaging-compare:
     info: Compare a core replay with an archived imaging result field by field and, when image directories are given, pixel by pixel; fails the recipe on any difference outside task A's tolerances.
     flavour: python
```

### `core/src/wgridder.rs`

```diff
diff --git a/core/src/wgridder.rs b/core/src/wgridder.rs
index 8665aac..78e86de 100644
--- a/core/src/wgridder.rs
+++ b/core/src/wgridder.rs
@@ -942,12 +942,17 @@ impl VisData<'_> {
     }
 }

-/// Weights of a call, borrowed in either precision.
+/// Weights of a call, borrowed in either precision. `F32Product` is two
+/// float32 weights (a reader weight and an imaging weight, DF2b) whose
+/// product is formed per visibility as one float32 multiply and widened
+/// afterwards, exactly as NumPy's `a * b` of two float32 arrays, so the
+/// caller need not materialise the product.
 #[derive(Clone, Copy, Debug)]
 pub enum Weights<'a> {
     None,
     F32(&'a [f32]),
     F64(&'a [f64]),
+    F32Product(&'a [f32], &'a [f32]),
 }

 impl Weights<'_> {
@@ -956,6 +961,12 @@ impl Weights<'_> {
             Weights::None => None,
             Weights::F32(w) => Some(w.len()),
             Weights::F64(w) => Some(w.len()),
+            // Unequal lengths never match a visibility count.
+            Weights::F32Product(a, b) => Some(if a.len() == b.len() {
+                a.len()
+            } else {
+                usize::MAX
+            }),
         }
     }

@@ -965,6 +976,7 @@ impl Weights<'_> {
             Weights::None => None,
             Weights::F32(w) => Some(T::of(f64::from(w[i]))),
             Weights::F64(w) => Some(T::of(w[i])),
+            Weights::F32Product(a, b) => Some(T::of(f64::from(a[i] * b[i]))),
         }
     }
 }
@@ -3902,4 +3914,68 @@ mod tests {
         let freq = vec![1.4e9, 1.2e9, 1.0e9];
         assert!(vis2dirty(&c.opts, &c.uvw, &freq, &c.vis, None, None, &mut dirty).is_err());
     }
+
+    /// DF2b: two float32 weights multiplied in the core give the same bits
+    /// as their float32 product passed as one array, for dirty and PSF.
+    #[test]
+    fn product_weights_match_their_product() {
+        let c = case(32, 24, 0.2, 400.0, 40, 7);
+        let mut s = 99_u64;
+        let a: Vec<f32> = c.wgt.iter().map(|&w| w as f32).collect();
+        let b: Vec<f32> = (0..a.len())
+            .map(|i| {
+                if i % 7 == 0 {
+                    0.0
+                } else {
+                    (0.1 + lcg(&mut s)) as f32
+                }
+            })
+            .collect();
+        let product: Vec<f32> = a.iter().zip(&b).map(|(x, y)| x * y).collect();
+        let vis: Vec<Complex<f32>> = c
+            .vis
+            .iter()
+            .map(|v| Complex::new(v.re as f32, v.im as f32))
+            .collect();
+        let opts = Options {
+            epsilon: 1e-6,
+            ..c.opts
+        };
+        let run = |wgt: Weights| {
+            let mut dirty = vec![0.0_f64; 32 * 24];
+            let mut psf = vec![0.0_f64; 32 * 24];
+            let plan = vis2dirty_multi(
+                &opts,
+                &c.uvw,
+                &c.freq,
+                VisData::C64(&vis),
+                wgt,
+                None,
+                Some(&mut dirty),
+                Some(&mut psf),
+            )
+            .unwrap();
+            (dirty, psf, plan.to_array())
+        };
+        let one = run(Weights::F32(&product));
+        let two = run(Weights::F32Product(&a, &b));
+        assert_eq!(one.0, two.0);
+        assert_eq!(one.1, two.1);
+        assert_eq!(one.2, two.2);
+        let mut dirty = vec![0.0_f64; 32 * 24];
+        let short = &b[..b.len() - 1];
+        assert!(
+            vis2dirty_multi(
+                &opts,
+                &c.uvw,
+                &c.freq,
+                VisData::C64(&vis),
+                Weights::F32Product(&a, short),
+                None,
+                Some(&mut dirty),
+                None,
+            )
+            .is_err()
+        );
+    }
 }
```

### `core/src/ffi_wgridder.rs`

```diff
diff --git a/core/src/ffi_wgridder.rs b/core/src/ffi_wgridder.rs
index c38437a..da11537 100644
--- a/core/src/ffi_wgridder.rs
+++ b/core/src/ffi_wgridder.rs
@@ -304,6 +304,9 @@ pub const WGRIDDER_WGT_NONE: i32 = 0;
 pub const WGRIDDER_WGT_F32: i32 = 1;
 /// `wgt_kind`: doubles.
 pub const WGRIDDER_WGT_F64: i32 = 2;
+/// `wgt_kind` of the `_ex2` entry points: two float arrays (`wgt`, `wgt2`)
+/// whose product, one float multiply per visibility, is the weight (DF2b).
+pub const WGRIDDER_WGT_F32_PRODUCT: i32 = 3;

 /// Borrow `n` visibilities of kind `kind` at `ptr`.
 ///
@@ -327,11 +330,18 @@ unsafe fn vis_data<'a>(ptr: *const c_void, kind: i32, n: usize) -> Result<VisDat
     }
 }

-/// Borrow `n` weights of kind `kind` at `ptr`.
+/// Borrow `n` weights of kind `kind` at `ptr` (and, for the product kind,
+/// `ptr2`; null otherwise).
 ///
 /// # Safety
-/// `ptr` must hold `n` values of that kind (or be ignored without weights).
-unsafe fn weights<'a>(ptr: *const c_void, kind: i32, n: usize) -> Result<Weights<'a>, String> {
+/// `ptr` (and `ptr2`) must hold `n` values of that kind (or be ignored
+/// without weights).
+unsafe fn weights<'a>(
+    ptr: *const c_void,
+    ptr2: *const c_void,
+    kind: i32,
+    n: usize,
+) -> Result<Weights<'a>, String> {
     // SAFETY: forwarded contract.
     unsafe {
         match kind {
@@ -344,6 +354,12 @@ unsafe fn weights<'a>(ptr: *const c_void, kind: i32, n: usize) -> Result<Weights
                 ptr as *const f64,
                 n,
             ))),
+            WGRIDDER_WGT_F32_PRODUCT if !ptr.is_null() && !ptr2.is_null() => {
+                Ok(Weights::F32Product(
+                    std::slice::from_raw_parts(ptr as *const f32, n),
+                    std::slice::from_raw_parts(ptr2 as *const f32, n),
+                ))
+            }
             _ => Err("invalid weight array or kind".into()),
         }
     }
@@ -363,6 +379,7 @@ unsafe fn run_ex<T: Real>(
     vis: *const c_void,
     vis_kind: i32,
     wgt: *const c_void,
+    wgt2: *const c_void,
     wgt_kind: i32,
     mask: *const u8,
     dirty: *mut T,
@@ -388,7 +405,7 @@ unsafe fn run_ex<T: Real>(
                 std::slice::from_raw_parts(uvw, nrow * 3),
                 std::slice::from_raw_parts(freq, nchan),
                 vis_data(vis, vis_kind, n),
-                weights(wgt, wgt_kind, n),
+                weights(wgt, wgt2, wgt_kind, n),
                 (!mask.is_null()).then(|| std::slice::from_raw_parts(mask, n)),
                 (!dirty.is_null()).then(|| std::slice::from_raw_parts_mut(dirty, npix)),
                 (!psf.is_null()).then(|| std::slice::from_raw_parts_mut(psf, npix)),
@@ -451,7 +468,20 @@ pub unsafe extern "C" fn rang_core_wgridder_vis2dirty_ex_f64(
     // SAFETY: forwarded contract.
     unsafe {
         run_ex::<f64>(
-            opts, nrow, nchan, uvw, freq, vis, vis_kind, wgt, wgt_kind, mask, dirty, psf, info,
+            opts,
+            nrow,
+            nchan,
+            uvw,
+            freq,
+            vis,
+            vis_kind,
+            wgt,
+            std::ptr::null(),
+            wgt_kind,
+            mask,
+            dirty,
+            psf,
+            info,
         )
     }
 }
@@ -480,7 +510,86 @@ pub unsafe extern "C" fn rang_core_wgridder_vis2dirty_ex_f32(
     // SAFETY: forwarded contract.
     unsafe {
         run_ex::<f32>(
-            opts, nrow, nchan, uvw, freq, vis, vis_kind, wgt, wgt_kind, mask, dirty, psf, info,
+            opts,
+            nrow,
+            nchan,
+            uvw,
+            freq,
+            vis,
+            vis_kind,
+            wgt,
+            std::ptr::null(),
+            wgt_kind,
+            mask,
+            dirty,
+            psf,
+            info,
+        )
+    }
+}
+
+/// As `rang_core_wgridder_vis2dirty_ex_f64`, with a second weight array
+/// (DF2b): with `wgt_kind` = `WGRIDDER_WGT_F32_PRODUCT`, `wgt` and `wgt2`
+/// hold `nrow * nchan` floats each and the weight of a visibility is their
+/// product as one float multiply (bit-identical to passing the product
+/// array as `WGRIDDER_WGT_F32`); other kinds ignore `wgt2`.
+///
+/// # Safety
+/// As `rang_core_wgridder_vis2dirty_ex_f64`; `wgt2` likewise.
+#[unsafe(no_mangle)]
+#[allow(clippy::too_many_arguments)]
+pub unsafe extern "C" fn rang_core_wgridder_vis2dirty_ex2_f64(
+    opts: *const WgridderOptions,
+    nrow: usize,
+    nchan: usize,
+    uvw: *const f64,
+    freq: *const f64,
+    vis: *const c_void,
+    vis_kind: i32,
+    wgt: *const c_void,
+    wgt2: *const c_void,
+    wgt_kind: i32,
+    mask: *const u8,
+    dirty: *mut f64,
+    psf: *mut f64,
+    info: *mut f64,
+) -> i32 {
+    // SAFETY: forwarded contract.
+    unsafe {
+        run_ex::<f64>(
+            opts, nrow, nchan, uvw, freq, vis, vis_kind, wgt, wgt2, wgt_kind, mask, dirty, psf,
+            info,
+        )
+    }
+}
+
+/// As `rang_core_wgridder_vis2dirty_ex2_f64`, working in single precision.
+///
+/// # Safety
+/// As `rang_core_wgridder_vis2dirty_ex2_f64`.
+#[unsafe(no_mangle)]
+#[allow(clippy::too_many_arguments)]
+pub unsafe extern "C" fn rang_core_wgridder_vis2dirty_ex2_f32(
+    opts: *const WgridderOptions,
+    nrow: usize,
+    nchan: usize,
+    uvw: *const f64,
+    freq: *const f64,
+    vis: *const c_void,
+    vis_kind: i32,
+    wgt: *const c_void,
+    wgt2: *const c_void,
+    wgt_kind: i32,
+    mask: *const u8,
+    dirty: *mut f32,
+    psf: *mut f32,
+    info: *mut f64,
+) -> i32 {
+    // SAFETY: forwarded contract.
+    unsafe {
+        run_ex::<f32>(
+            opts, nrow, nchan, uvw, freq, vis, vis_kind, wgt, wgt2, wgt_kind, mask, dirty, psf,
+            info,
         )
     }
 }
@@ -521,7 +630,7 @@ unsafe fn run_d2v_ex<T: Real>(
                 std::slice::from_raw_parts(uvw, nrow * 3),
                 std::slice::from_raw_parts(freq, nchan),
                 std::slice::from_raw_parts(dirty, o.nx * o.ny),
-                weights(wgt, wgt_kind, n),
+                weights(wgt, std::ptr::null(), wgt_kind, n),
                 (!mask.is_null()).then(|| std::slice::from_raw_parts(mask, n)),
                 std::slice::from_raw_parts_mut(vis as *mut Complex<T>, n),
             )
```
