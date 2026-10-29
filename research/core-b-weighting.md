# Rang core, wave 1 task B: WSClean imaging weights and Stokes I

Protocol written 2026-10-30 on branch `core/b-weighting` before any weighting
code, as task B of [core-parallel-plan.md](core-parallel-plan.md). Status:
**implemented; measured: all seven frozen criteria pass as frozen, the core's
weights are bit-identical to WSClean's on all 19 oracle runs** (results
section below). The task ports WSClean 3.6's Briggs, uniform and natural imaging
weighting and its Stokes I formation from linear correlations into the Rust
core, and validates the port against WSClean's own stored imaging weights on
the fifteen archived imaging jobs. A reimplementation; under AGENTS.md not a
scientific contribution. A sibling task (C) ports the gridder and will consume
these weights; a sibling (A) proposes image tolerances. This task does not wait
for either and freezes its own tolerance from the measured WSClean
reproducibility, as the plan requires.

## What WSClean does (read from the verified 3.6-1 source)

Source: `outputs/wsclean-3.6-1-source-20261029/src/wsclean-v3.6/` (SHA256SUMS
there). Files: `structures/imageweights.{h,cpp}`, `io/imageweightcache.h`,
`main/imageweightinitializer.cpp`, `main/settings.cpp`,
`gridding/msgridderdata.{h,cpp}`, `msproviders/msreaders/contiguousmsreader.cpp`,
`external/schaapcommon/src/reordering/reordering.cc`,
`external/aocommon/include/aocommon/{polarization.h,banddata.h,units/angle.h}`,
`doc/source/weighting_and_gridding_details.rst`.

1. **Geometry.** The weight grid uses the *padded* image size:
   `padded = ceil(size * 1.2)` rounded up to a multiple of four (512 → 616),
   then divided by the super-weight (1.0 by default) and made even. The grid
   holds the upper half plane only, `width * height / 2` doubles. Pixel scale
   is `8 * M_PI / (180 * 60 * 60)` radians for `-scale 8asec`.
   `-no-min-grid-resolution` does not change the weight grid; it affects only
   the gridder (task C). A sample at (u, v) in wavelengths goes to
   `x = floor(u * width * scale + width / 2)`, `y = floor(v * height * scale)`
   after folding `v < 0` to `(-u, -v)`, and is kept when
   `0 <= x < width` and `y < height / 2`.
2. **Which samples.** Rows selected by field (`-field 0`), cross-correlations
   only, one data description; `FLAG_ROW` is **not** consulted. All channels of
   `-channel-range 1024 3072`. Wavelength is `299792458.0L / freq` computed in
   `long double` and rounded to double (`aocommon::BandData`), then
   `u = uInM / wavelength` in double.
3. **Per-visibility weight for Stokes I from four linear correlations**
   (`ExtractWeights`): `4 * min(w_XX, w_YY)` in float, or `0` if either of the
   XX or YY cells is flagged or its *data* value (the column being imaged,
   here `CORRECTED_DATA`) is not finite. WEIGHT_SPECTRUM is used when present.
4. **Gridding the weights.** Each selected sample adds its weight to its cell
   (double accumulation of float weights) and to a running total.
5. **Finish.** Briggs: `avgW = Σ cell² / total`, `f = 5 * 10^(-robust)`,
   `S² = f² / avgW`, `cell = 1 / (1 + cell * S²)` for non-zero cells; uniform:
   `1 / cell`; natural: `1` for non-zero cells. Zero cells stay zero.
6. **Rank filter, always on by default** (`-weight-rank-filter` level 3.0,
   size 16): each non-zero cell is clipped to `3 × mean` of the non-zero cells
   in its 16-cell window on the half grid, with WSClean's exact window bounds
   (`x1 = x - 8` or `0`, `x2 = min(x + 8, width)`, same for `y` against
   `height / 2`), computed from the unclipped grid.
7. **Lookup.** For every selected row and channel, the imaging weight is the
   cell value at that sample's (x, y) (nearest cell, no interpolation), `0`
   outside the grid, regardless of flags. `-store-imaging-weights` writes this
   value (as float) into `IMAGING_WEIGHT_SPECTRUM` for the XX and YY entries of
   the selected channels; the other entries stay at the zero the column was
   created with.
8. **Stokes I visibility** (`ExtractData` / `ConvertFromLinear`):
   `I = 0.5f * (XX + YY)` in complex float, `0` if the result is not finite.
9. **Applied weight and the header sums** (`ApplyWeights`): per channel the
   applied weight is `cum = w * imaging_weight` in float. WSClean accumulates
   `visibilityWeightSum += w` (where `cum != 0`), `totalWeight += cum`, and the
   gridded count, all in double, and writes them to the FITS header as
   `WSCVWSUM`, `WSCIMGWG` (also `WSCNORMF`) and `WSCNVIS`. The archive's
   headers are therefore an oracle for the weight path that needs no rerun.

## Inputs (frozen)

- Archive `outputs/tv-next-imaging-wsl-20261029-01`: `backups/response-input.ms`
  and `backups/caracal-input.ms` (140 rows, 4096 channels, XX XY YX YY), the
  fifteen `checkpoints/<label>-written.npz` (`CORRECTED_DATA`, `FLAG`,
  `FLAG_ROW`, `support`; the archived audit verified they equal what the work
  MS held while WSClean ran), `checkpoints/<label>-command.json`,
  `checkpoints/<label>-wsclean.log`, `images/<label>-{dirty,psf}.fits`.
- WSClean 3.6-1 from the `rang-flagging-next-imaging:local` image (binary
  SHA256 as recorded in the archive's `imaging-config.json`).
- The WSClean source above.

## Oracle production (`examples/oracle_wsclean_weights.py`, once)

Run inside the container with `outputs/` mounted; all writes go to a fresh
`outputs/core-b-20261030-01/`. For each of the fifteen labels:

1. Copy the role's input MS to `ms/<label>.ms`, write `CORRECTED_DATA`, `FLAG`
   and `FLAG_ROW` from the checkpoint, and verify the write.
2. Run the archived command verbatim with the paths rewritten to the new
   directory and `-store-imaging-weights` appended. Wall time is recorded.
3. Export `oracle/<label>.npz`: `IMAGING_WEIGHT_SPECTRUM`, `UVW`,
   `WEIGHT_SPECTRUM`, `FLAG`, `FLAG_ROW`, `FIELD_ID`, `ANTENNA1`, `ANTENNA2`,
   `DATA_DESC_ID`, `CORRECTED_DATA`, `CHAN_FREQ`, the wavelengths as
   `np.longdouble(299792458) / freq` rounded to float64, the rerun's dirty and
   PSF pixels, and the header keys `WSCVWSUM`, `WSCIMGWG`, `WSCNVIS`,
   `WSCENVIS` from the rerun and from the archive.
4. For two labels (`clean-full` and `caracal-firstpass-rejected`, the two
   distinct flag patterns) the run is repeated into a second MS copy to
   measure WSClean's own reproducibility, and `-weight uniform` and
   `-weight natural` runs are added into further copies for the other two
   weighting classes.

## Comparator precondition

Before the tolerance is frozen the comparator (`examples/compare_core_weights.py`
in `--oracle-only` mode) is run on archive versus host reproduction: the
rerun's dirty and PSF images against the archived FITS, the rerun's header sums
against the archived header sums, and the repeated runs' imaging weights
against the first runs. The result is recorded here before any core code.

## Tolerance rule

Imaging weights are compared where WSClean stored one (XX entry, selected
channels, selected rows). Zero/non-zero patterns must be identical. Non-zero
values must agree to a relative difference of at most
`max(4 float32 ulps, measured WSClean repeat spread)`. **Frozen 2026-10-30,
before core code: 4 × 2⁻²³ = 4.76837158203125e-7**, because the measured
WSClean repeat spread is exactly zero (see the precondition result).
Header sums are compared to a relative 1e-9 (fifteen printed digits). Stokes I
values and per-visibility weights are compared bit-exactly against a NumPy
float32 oracle of the formulas in items 3 and 8. Dirty/PSF reproduction uses
the phase 4 gate, 1e-6 Jy/beam absolute, with the measured maximum reported.

## Precondition result (measured 2026-10-30, before core code)

Oracle run: 21 WSClean inversions (15 jobs, 2 repeats, 2 uniform, 2 natural)
in `outputs/core-b-20261030-01` (33.4 s inside the container, 34.2 s with
`docker run`; 1.3–1.8 s per WSClean call, 0.11–0.16 s per MS copy and
checkpoint write, 0.04–0.24 s per export). WSClean binary SHA256
`1fd0ced9…671b8a`, equal to the archive's receipt. The flag had to go before
the MS argument; the first attempt put it last and WSClean read it as a table
name. `compare_core_weights.py --oracle-only` (`precondition.json`): every
rerun dirty and PSF image is pixel-identical to the archive (max |Δ| = 0),
every header sum identical, both repeats identical in weights and pixels
(spread 0), and the column structure holds on all 21 runs (XX = YY, XY/YX
zero, out-of-range channels zero, the 56 autocorrelation rows zero, 84 rows
selected). Criterion 1 is met; the tolerance is frozen above.

## Acceptance criteria (frozen)

1. **Reproduction.** Every rerun dirty and PSF image equals the archived one
   within 1e-6 Jy/beam; every rerun header sum equals the archive's to 1e-9
   relative.
2. **Imaging weights, Briggs 0.5.** On all fifteen jobs the core's weights
   equal `IMAGING_WEIGHT_SPECTRUM` under the tolerance rule; the oracle's XX
   and YY entries are equal, and its XY/YX entries and out-of-range channels
   are zero.
3. **Uniform and natural.** Criterion 2 on the two extra jobs for each class.
4. **Stokes I formation.** The core's Stokes I visibilities and per-visibility
   weights equal the NumPy float32 oracle bit-exactly on all fifteen jobs.
5. **Header sums.** The core's `WSCVWSUM`, `WSCIMGWG` and `WSCNVIS`, computed
   as in item 9 from its own weights, equal the archived headers to 1e-9
   relative on all fifteen jobs.
6. **Geometry helper.** The core's padded-size rule gives 616 for 512 at
   padding 1.2 and reproduces WSClean's rule for sizes 1–4096 (checked in a
   Rust unit test against the formula in `settings.cpp`).
7. **Timing.** The core's weight pass (grid, finish, rank filter, lookup) per
   job is timed in-process and reported; no threshold.

Failures are recorded as frozen; any later step is labelled post-hoc.

## Implementation plan

- `core/src/weights.rs`: `WeightClass` (Natural, Uniform, Briggs(robust)),
  `padded_size`, `WeightGrid` (new, grid, finish, rank_filter, sample),
  `stokes_i_from_linear` (data, weights, flags → I, weight), `apply_weights`
  sums. No new crates.
- `core/src/ffi_weights.rs`: C ABI with explicit lengths, in the style of
  `ffi.rs`.
- `python/rangtoy/core_weights.py`: registers its own ctypes symbols as
  `core_zarr.py` does; `imaging_weights(...)`, `stokes_i(...)`,
  `wsclean_wavelengths(freq)`.
- `examples/oracle_wsclean_weights.py`, `examples/compare_core_weights.py`,
  `tests/test_core_weights.py`.

## Results (measured 2026-10-30, run as frozen)

`compare_core_weights.py outputs/core-b-20261030-01 --tolerance 4.76837158203125e-07`
(`compare.json`), after the Rust unit tests and the Python tests passed:

| Criterion | Result |
| --- | --- |
| 1 reproduction | pass: 15/15 reruns pixel-identical, header sums identical |
| 2 Briggs 0.5 weights | pass on 15/15 jobs; **max relative difference 0.0**, every stored float identical, zero patterns identical; column structure holds |
| 3 uniform and natural | pass on 2 + 2 jobs, identical floats |
| 4 Stokes I formation | pass: visibilities and per-visibility weights bit-equal to the NumPy float32 oracle on 15/15 jobs |
| 5 header sums | pass: `WSCNVIS` exact (9169; 7812 on `caracal-firstpass-rejected`), `WSCVWSUM` and `WSCIMGWG` within 1.8e-15 relative (printed-digit rounding of the archive values) |
| 6 geometry helper | pass: 616 for 512; Rust test over sizes 2–4096 |
| 7 timing | reported below; no threshold |

Nothing was changed after the first comparison run; there is no post-hoc
step. Observations:

- The two distinct flag patterns give two distinct weight sets; the other
  thirteen jobs share the `clean-full` weights because WSClean's weights
  depend on the data only through finiteness (item 3). The oracle therefore
  has two independent Briggs cases, plus uniform and natural on each.
- **Grid coverage is thin.** The four-station fixture (84 cross rows, maximum
  baseline about 370 λ, cells of about 41.8 λ at 616 pixels) occupies only
  18 cells of the 616 × 308 half grid. Items 1, 2, 4, 5 and 7 are exercised
  exactly on real WSClean output; the rank filter and the Briggs finish are
  exercised on these 18 cells and otherwise by the Rust unit tests. A denser
  array would strengthen the oracle (open question below).
- Wavelengths: the `long double` division rounded to double differs from a
  plain float64 division on 3 of 4096 channels (3 of them in the imaged
  range) by one ulp; `core_weights.wsclean_wavelengths` reproduces WSClean's
  value with `np.longdouble`, and the core takes wavelengths as input.
- Rust's `exp` and glibc's may differ by an ulp in the Briggs factor
  `5 · 10^(−robust)`; on these jobs the stored floats are identical anyway.

### Timings

| Date | Tool / stage | Input | Wall | Notes |
| --- | --- | --- | ---: | --- |
| 2026-10-30 | task B oracle: 21 WSClean 3.6-1 inversions with `-store-imaging-weights` in `rang-flagging-next-imaging:local` | 15 jobs + 2 repeats + 2 uniform + 2 natural, 84 × 2048 × 4 | 33.4 s in-container (34.2 s with `docker run`) | 1.3–1.8 s per WSClean call, 0.11–0.16 s per MS copy and checkpoint write, 0.04–0.24 s per export; first attempt failed at once because the flag followed the MS argument |
| 2026-10-30 | task B comparator, `--oracle-only` | 21 oracle runs | about 1 s | precondition, all identical |
| 2026-10-30 | task B comparator, full (19 core jobs + oracles) | same | 3.4 s process including a 2.0 s core rebuild | |
| 2026-10-30 | core Stokes I formation, in-process | 140 × 2048 × 4 | 1.5–2.3 ms (5.9 ms once) | first call 2.0 s includes the ctypes library load |
| 2026-10-30 | core imaging weights (grid, Briggs finish, rank filter, lookup), in-process | 84 rows × 2048 channels on 616 × 308 | 4.7–9.2 ms | WSClean's "Precalculating weights" is not separately timed in its log |
| 2026-10-30 | `cargo test` (core, weights filter) and `pytest tests/test_core_weights.py` | 7 + 6 tests | 0.9 s and 2.0 s | |
| 2026-10-30 | `bash tools/check-all.sh` | repo (674 pytest tests, 25 core and 19 root Rust tests) | 3046 s (pytest 3028 s) | overall PASS, once before the final commit; pytest slow because eight sibling sessions shared the 16 cores |

### Open questions

- A denser uv coverage oracle (a real MeerKAT MS, or the LUNO slice once a
  full-resolution dataset arrives) would exercise the rank filter and the
  Briggs normalisation on many cells; the fixture covers 18.
- Task C's gridder should take `core_weights.imaging_weights(...)["weights"]`
  multiplied by the Stokes I weights (`ApplyWeights`, item 9), and
  `WeightSums` for `WSCVWSUM`, `WSCIMGWG`, `WSCNVIS` and the normalisation.
- `-super-weight`, tapers, `-minuv-l`/`-maxuv-l` and MF weighting are not
  ported (rang does not use them); `WeightGrid::shape` handles the super
  weight, nothing else.

## For the coordinator

- Add `pub mod ffi_weights;` and `pub mod weights;` to `core/src/lib.rs`. They
  were added locally and left uncommitted so that the branch's own commits
  touch no shared file; without them the branch's `tests/test_core_weights.py`
  and `compare_core_weights.py` cannot load the symbols.
- Copy the timing rows above into `tool-timings.md`.
- Upstream note: none filed. WSClean's `-store-imaging-weights` writes the
  column during both the PSF and the dirty passes with the same values, and
  must precede the MS argument on the command line (documented behaviour).
- Archive for `results/`: none; the oracle and comparison JSON live in
  `outputs/core-b-20261030-01` (889 MB, dominated by the 21 oracle `.npz`
  files, 43 MB each; the MS copies were deleted after export).
