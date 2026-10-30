# Rang L1: the whole-array LUNO campaign

Protocol frozen 2026-10-30 on branch `luno-array-campaign` (from origin/main
`df42ea0`), before any campaign code was written. Task L1 of
[big-plan.md](big-plan.md), wave 1. Status: **proposed** (protocol only; no
array computation has run).

This is [task K](core-k-luno-campaign.md) at the scale the method was designed
for. K ran gain-TV-guided flagging on the LUNO PKS 1934−638 four-station slice
(six baselines) and got a null result. Four stations are sidelobe-dominated and
leave most gain bins under-identified, so the real test is the whole array.
Everything that K froze is reused here: the arms, the seed-7 split, the solver
settings, the policy loop, the metrics and the decision rule. This protocol
changes only what the array's scale forces, and every such change is listed
under "What changes from K, and why".

Standing caveats: WEIGHT_SPECTRUM is a QuartiCal product (observer, 2026-10-29
15:37 SAST); the 1934−638 MODEL_DATA has no logged origin; SIGMA_SPECTRUM does
not match the DATA scatter. All calibration numbers are conditional on the
weights and on the model. The licence is settled by user decision
([big-plan.md](big-plan.md)). Raw visibilities are never committed: the
archive holds numbers, flag fractions and hashes only.

## Question

On the whole MeerKAT array (LUNO row chunk 0, PKS 1934−638, 1070–1498 MHz),
does gain-TV-guided flagging change calibration or imaging quality relative to
the CARACAL first-pass Tricolour flags at comparable cost? Everything runs on
the core: the core's QuartiCal `complex` port, the fused pass, the Rust TV
kernel, the Tricolour/CARACAL port, Briggs weights and the w-stacking gridder.
The run is also the first whole-array speed baseline for G2 of the big plan.

## Data cells (frozen)

- Store `LBAND_LUNO_CALIBRATORS.zarr`, group `MAIN/MAIN_1` (field J1939−6342 =
  PKS 1934−638, scan 2), **row chunk 0** (zarr rows 0–49,999), channel tiles
  8–23 (channels 1024–3071, 1070.0–1497.8 MHz).
- **Rows:** cross-correlation rows of all stations with `FLAG_ROW` false. That
  is **41,786 rows on 1,378 baselines among 53 stations**, measured from the
  archived row columns before freezing.
  - The 1540 − 1378 = 162 missing baselines are exactly those of m031, m040
    and m044 (indices 25, 33, 37). Every one of their rows has `FLAG_ROW` set,
    which matches the support survey's "no TRAIN cell" stations.
  - A further 138 baselines have some rows with `FLAG_ROW` set (antenna 39 is
    the main contributor). Those rows are dropped; the rest of each baseline
    is kept.
  - The solver and the TV map index all 56 stations; the three stations
    without rows get flagged gains, as in K.
- **Integrations:** 32. The 32nd is cut by the chunk boundary: 524 of its
  1,596 rows are in chunk 0. With the frozen 2-integration grid, gain time bin
  15 therefore holds one integration for most baselines. This is taken as is
  and recorded; it is the same chunk K used.
- **Sizes:** 41,786 × 2048 = 85,577,728 samples × 4 correlations.
- **K's 192 rows are a strict subset.** The four-station rows of this
  selection are exactly K's rows (stations 0–3, `FLAG_ROW` false), which the
  precondition below uses.

## No fetch: the inputs are already on disk (frozen)

Every whole tile and object the campaign needs is already archived locally, so
**nothing is fetched**. The fetch stage records 0 bytes and 0 requests.

- `outputs/luno-solve-20261029-02/inputs` (receipt `receipt.txt`, 2,625
  lines) holds the 16 whole DATA tiles `MAIN/MAIN_1/DATA/0.{8..23}.0`, UVW
  `0.0`, and the ANTENNA, SPECTRAL_WINDOW, FIELD and POLARIZATION subtables.
- `outputs/luno-support-20261029-01/slice` (receipt `receipt.txt`, 122
  lines) holds the 16 whole tiles of FLAG, WEIGHT_SPECTRUM and MODEL_DATA, and
  the row columns ANTENNA1, ANTENNA2, TIME and FLAG_ROW `0`. Their blosc
  headers give 204,800,000 / 102,400,000 / 25,600,000 bytes, which is
  50,000 × 128 × 4 × itemsize: whole row chunks, not slices.
- Each object is resolved by existence across the two roots (the lesson from
  K's checker). Its size and SHA256 must equal the archived receipt line
  before it is decoded.

Decode: the row columns through `core.blosc_decode`; the tile columns through
`core_zarr.read_rows` (Rust blosc) on the 41,786 selected rows, written
straight into preallocated `(41786, 2048, 4)` arrays so that no column is ever
held twice. json2 string arrays are decoded as plain JSON only.

## Method (frozen; K's method unless stated)

1. **Eligibility and split.** As K: no original flag in any correlation,
   `FLAG_ROW` false, all four weights positive, DATA and MODEL_DATA finite;
   `flagging.split_holdout` unedited, **seed 7**, 10 % validation, 10 % test,
   groups = gain bin × baseline (`nant` = 56), at least two training cells
   per group.
2. **Solve** per arm: the core's QuartiCal `complex` port with K's settings
   (`G.type=complex`, 2 integrations × 32 channels, 50 iterations,
   convergence 1e-7, stop fraction 0.99, polar gauge on reference antenna 0
   for TV, held-out cells excluded and predicted afterwards). One solve over
   the whole chunk.
   - The solve **cannot** be split by baseline group or frequency: the 0.99
     stop fraction is a global criterion over all bins, so a split solve is a
     different solve.
3. **Arms:** `original`, `tricolour-firstpass` (the state-of-the-art
   comparator: `mk_rfi_flagging_calibrator_fields_firstpass.yaml`),
   `tricolour-mild` (`calibrator_mild_flagging.yaml`), `tv-policy` (the
   frozen one-round loop over τ ∈ {8, 5, 3} × α ∈ {0, 1, 3}, `max_fraction`
   0.02, objective `fixed_support_TV/TV0 + 2 f + 0.25 MSE_val/MSE_val0`,
   admissible only if `MSE_val ≤ 1.01 MSE_val0` with fixed TV support;
   no-change is always available), `tv-unguided-best` (α = 0, reported as the
   ablation) and `tricolour-firstpass+tv` (the loop seeded from the first-pass
   arm).
   - The Tricolour port runs on all 41,786 rows with the original flags as
     input, the two shipped static masks and the ECEF positions of all 56
     antennas.
   - Additions are cells (coupled over the correlations) on training cells
     only. Held-out cells are never flagged by any arm.
4. **Imaging** per arm on its final flags. Corrected visibilities
   `G_p^{-1} V G_q^{-H}`, cells with an invalid gain flagged; the WSClean
   Stokes I reader rule; Briggs 0.5 weights on the padded grid with rank
   filter 3.0/16; `core_grid.invert` (Kaiser–Bessel 7, 1023×, 64 w-layers,
   padding 1.2). The image geometry is set from the array (next section).

### Imaging geometry from the array's resolution (frozen; fixes K's box error)

K's 512 × 512 at 8″ was copied from the 64-station fixture. For four stations
(maximum baseline 74 m) its 9 × 9 peak box sat inside the main lobe (largest
PSF value outside it 0.998). For the whole array that pixel is too coarse.
The maximum projected baseline of the kept rows is 7,639 m, which is 38,165 λ
at 1497.8 MHz, so λ/B_max is 5.4″ at the top of the band and 7.6″ at the
bottom.

- **Pixel 1.5″, 1024 × 1024** (25.6′ field, padded grid 1229²).
  u_max × pixel = 0.28 cycles per pixel, inside Nyquist (0.5). That gives
  about 3.6 pixels across λ/B_max at the top of the band, and more across the
  Briggs-0.5 main lobe. The maximum |w| is 26,500 λ; across the field
  (n − 1 ≤ 1.4e-5) that is a w-phase of at most 2.3 rad, well sampled by 64
  layers.
- **Boxes from the measured PSF.** After the `original` arm's PSF is made,
  its main-lobe FWHM is measured on the PSF itself:
  - Measure the half-power crossing, linearly interpolated, along the centre
    row, the centre column and both diagonals (diagonal distances × √2).
  - FWHM_max is the largest of the four.
  - Main-lobe box half-width `r = ceil(1.5 FWHM_max)` pixels. A Gaussian is
    at 2⁻⁹ there, and the first null of an Airy pattern is at 1.18 FWHM.
  - Far region: everything outside the square of half-width
    `R = min(width/4, max(32, ceil(20 FWHM_max)))`.
  - `r` and `R` are then fixed for every arm. Each arm's own FWHM_max is
    reported beside them.
- **Gridding in channel groups.** The core gridder materialises two
  40-byte samples per (row, channel) inside Rust, which is 6.85 GB for
  85.6 M samples. The array is therefore gridded in **four groups of 512
  channels** with the global Briggs weights.
  - The groups' unnormalised images are summed: `R_k = dirty_k · W_k / N_k`
    with `W_k` the image weight and `N_k` the PSF normalisation of group k.
    The result is `dirty = Σ R_k / Σ R_psf,k[centre]`, and the PSF likewise.
  - This is linear and exact except for the per-group w-layer placement.
  - A group with no weighted sample is skipped and recorded.
  - With one group the result is K's single call. The precondition checks the
    four-group sum against one group on K's slice.

## Quality metrics (frozen)

Per arm, as K:

1. Held-out weighted MSE on the fixed validation and test cells (fused-pass
   losses; the mean over cells of the correlation-mean `w|r|²`). Invalid
   predictions make it unavailable.
2. Training χ² `losses["train"]`. This is section 6's definition, the mean
   over training cells of the per-cell four-correlation mean of `w|r|²`
   ([core-section6.md](core-section6.md)).
3. Gain TV:
   - fixed-support polar-gauge TV against the `original` arm's support at its
     scale, raw TV, and the time and frequency components;
   - the valid-gain fraction and the converged fraction;
   - median diagonal and off-diagonal gain amplitudes;
   - the fraction of valid gain cells lost to the reference-antenna gauge
     (bins where m000 is invalid);
   - per-station valid-bin counts.
4. Dirty image:
   - **point-source peak** in the main-lobe box, and flux recovery = peak /
     mean model Stokes I over the imaged samples;
   - the PSF FWHM_max, and the PSF's largest |value| outside the main-lobe
     box;
   - **dirty-image noise far from the source**: RMS and robust σ
     (1.4826 MAD) of the dirty image in the far region;
   - the **point-source residual** `dirty − peak × PSF` (PSF unity at its
     centre): its RMS over the whole image (the headline image metric, as
     in K), and its RMS and robust σ in the far region;
   - imaging weight sums and gridded counts.
5. Flagged fraction: of all 41,786 × 2048 × 4 cells in the arm's final flags;
   additions as a count and as a fraction of training cells; for the
   Tricolour arms the port's window fraction, its per-step fractions and its
   newly flagged cells.

## Cost metrics (frozen, measured)

Per stage:

- wall time;
- peak RSS (`getrusage` high-water mark after the stage, and the process
  under `/usr/bin/time -v`);
- **cores busy** = Δ(user + system CPU) / Δwall from `getrusage`.

Stages: input integrity, decode, split, each solve, each Tricolour strategy,
each TV loop (scores, TV, candidate solves), each image (correct and weight,
grid), and the whole campaign.

Each stage is set against K's four-station numbers: solve 0.32 s, Tricolour
first pass 1.55 s, mild 0.89 s, TV loop 1.68 s, inversion 3.9 s, decode
0.36 s. The scaling factor from 4 to 56 stations is reported against the
ratio of samples (85,577,728 / 393,216 = 217.6) and of baselines
(1378 / 6 = 229.7).

The archived QuartiCal solve (27.5 s cold, about 3 s warm) is a
**four-station** figure. No whole-array QuartiCal baseline exists and none is
run here (it needs a Measurement Set build and the container). It is quoted
only as the four-station reference.

**Cost clause** (as K): the TV chain (reference solve plus scores, TV and
candidate solves) is *comparable* if its wall is at most three times the wall
of the `tricolour-firstpass` port on the same cells.

## What changes from K, and why (frozen)

| K | L1 | Reason |
| --- | --- | --- |
| stations 0–3, 192 rows | all stations, 41,786 rows | the question |
| range fetch from the bucket | local whole tiles, hash-checked against the archived receipts; 0 bytes fetched | the whole chunk is already on disk |
| 512² at 8″, 9 × 9 peak box, 64 × 64 off-source box | 1024² at 1.5″; boxes from the measured PSF FWHM | array resolution; K's recorded box error |
| one gridder call | four 512-channel groups summed | gridder sample memory (6.85 GB) |
| `core_workflow.core_solve` (residuals always returned) | the same calls through `core_campaign_array.solve_arm`; residuals only for the two base solves, as per-cell whitened amplitudes computed in row blocks; stored solves keep gains, TV and metrics only | complex128 residuals are 5.5 GB per solve |
| `flagging.residual_features` (a full-array `log` per baseline) | the same estimator per baseline on that baseline's rows | the original is O(baselines × cells); same values |
| `core_campaign.apply_gains` on the whole array | the same per-cell algebra in row blocks | six complex128 (row, chan, 2, 2) temporaries, 5.5 GB each |
| Tricolour intensity output | not requested (`want_intensity=False`) | an output only; flags unaffected |
| section 6 reference on the fetched bytes (criterion 3) | the four-station replay in the precondition | section 6 is four-station specific |

**Equivalence rule.** Every reimplementation above must be **bit-identical**
on K's slice; the precondition's replay gates this. The cost clause times the
reimplementations, since those are what run. The unedited
`residual_features` is not timed at array scale.

## Memory budget (frozen)

Inputs, held once: DATA and MODEL_DATA complex64, 2.738 GB each;
WEIGHT_SPECTRUM float32, 1.369 GB; FLAG bool, 0.342 GB; **7.19 GB in all**.

K's driver unchanged would not fit:

- complex128 residuals are 5.48 GB per solve, and K keeps every solve (up to
  eight in memory, about 44 GB);
- `residuals × √w` adds another 5.5 GB;
- `apply_gains` creates six 5.5 GB temporaries;
- the gridder adds 6.85 GB.

With the changes above, the planned peak is about 15 GB:

- 7.2 GB of inputs;
- about 1 GB of split masks and solve flags (bool, uint8 copies and labels);
- about 2.7 GB of float64 per-sample features during a TV loop (amplitude,
  outliers, guidance, policy temporaries; 0.68 GB each);
- about 2 GB in the Tricolour port (12 per-step window arrays of
  1378 × 32 × 2048 bytes, 1.08 GB, plus output flags and internal windows);
- at most 2 GB in imaging blocks and one gridder group (21.4 M samples ×
  80 B = 1.7 GB).

Peaks that do not overlap are not added. The host has 30 GiB shared with three
sibling agents. **The frozen run starts only if `free -g` shows at least 20 GiB
available**; the reading is recorded. A peak RSS above 20 GB is recorded as a
budget failure, not hidden.

## What is never modified (frozen)

Input FLAG and FLAG_ROW: every arm builds new arrays with
`flagging.protected_flags`, and `assert_preserved` runs on every arm. No file
under these paths may change size or mtime:

- `outputs/luno-support-20261029-01`
- `outputs/luno-solve-20261029-02`
- `outputs/core-k-20261030-01`
- `outputs/core-section6-20261029-02`
- `outputs/caracal-strategy-inputs-8f7bb363`

The run writes only into `outputs/luno-array-campaign-20261030-NN` and its
check directory.

## Precondition (run before the array, gated)

In `outputs/luno-array-campaign-20261030-00-precondition`:

1. **K's precondition reproduces on this host.**
   `core_campaign.precondition` runs unedited into a subdirectory. All eight
   checks must pass, and χ², the survey, the mask counts and the converged
   and flagged-gain fractions must equal `precondition` and
   `section6_reference` in `results/core-k-luno-campaign.json`.
2. **Four-station replay.** The L1 driver runs with stations (0, 1, 2, 3),
   K's image settings (512² at 8″, K's boxes) and one gridder group, from the
   local tiles. It must reproduce K's frozen run `-01`
   (`outputs/core-k-20261030-01/result.json` and `candidates.json`, whose
   hash the archive pins) **exactly**:
   - the shape and split counts;
   - for every arm: `additions_sha256`, `gains_sha256`, the losses (train,
     validation, test), fixed-support TV, the final flag fraction, and the
     image `dirty_sha256` and `psf_sha256`;
   - every candidate's `mask_sha256`, `mask_count` and objective;
   - the Tricolour newly flagged counts;
   - the hypothesis calls.
3. **Gridder groups.** On the replay's `original` arm, the four-group sum must
   match the single call: dirty within 1e-4 of the peak (L∞), PSF within 1e-4
   (L∞).

If any check fails, the array run does not start and the failure is recorded
here.

## Acceptance criteria (frozen)

Gated:

1. **Input integrity.** Every local object read has the size and SHA256 of
   its archived receipt line; each tile's blosc `nbytes` is
   50,000 × 128 × 4 × itemsize; 0 bytes fetched.
2. **Flags preserved.**
   - For every arm and candidate: final ⊇ original cell for cell, `FLAG_ROW`
     identical, and `assert_preserved` passes.
   - No held-out cell carries an addition.
   - The archived inputs are unchanged and `git status` is unchanged.
3. **Precondition passed** (all three parts above).
4. **Every arm solves.** Converged fraction ≥ 0.9, finite gains on every
   valid bin, and zero invalid predictions on validation and test. An arm
   that fails this is reported as unavailable with its numbers, and its
   hypothesis is undecidable.
5. **Tricolour arms well formed.** A superset of the input, uniform over the
   correlations, and monotone across the `or`-accumulated steps.
6. **Hypothesis by the pre-registered rule** (K's, unchanged). The pairs are
   (`tv-policy`, `tricolour-firstpass`), (`tv-policy`, `original`) and
   (`tricolour-firstpass+tv`, `tricolour-firstpass`), on the fixed test
   cells.
   - *better* if `MSE_test(candidate) ≤ 0.99 MSE_test(reference)`;
   - *worse* if the ratio is `≥ 1.01`;
   - *null* otherwise.
   - The same three-way call is made on the point-source residual RMS and
     reported beside it; the headline is the first pair's MSE_test call
     with the cost clause.
   - A `tv-policy` arm that selects nothing is "no change selected", a null.
   - Validation MSE is used only inside the selection objective.
   - Pass means every pair is decidable.
7. **Outputs.** `result.json`, `receipt.json`, `environment.json`,
   `side-effects.json`, `candidates.json`, `flags/<arm>.npz` (additions
   only), `gains/<arm>.npz` and `images/<arm>-{dirty,psf}.fits`. The archive
   `results/luno-array-campaign.json` is under 200 KB, with no visibilities.
8. `bash tools/check-all.sh` passes on the branch.

Reported, not gated: every cost number, the memory peak against the budget,
the nine candidates per loop, the unguided best, the image metrics beyond the
residual RMS, the per-station gain support, and the 4 → 56 scaling.

The campaign runs once as frozen; a failure is recorded with its numbers, and
any later step is labelled post-hoc with its own run directory. A labelled
smoke on a small subset precedes the run. It may fix bugs only, never frozen
settings. It is deterministic: the split is seed 7 and no other randomness
exists.

## Expected outcome, stated before running

A null result remains likely and is acceptable:

- 70 % of K's cells were already flagged by the processing, and the whole
  chunk is similarly pre-flagged (the masked RFI bands);
- the 1934−638 model fits the processed weights well (χ² 0.27 on four
  stations);
- on the fixture and on K's slice the frozen policy selected nothing.

What is different at array scale, and could move the answer:

- 1,378 baselines give each gain bin a well-conditioned solve. The
  under-identified tree-shaped bins K had are gone almost everywhere, so TV
  maps reflect gain structure rather than gauge freedom.
- The per-baseline MAD scores are estimated on 1,378 baselines, including
  long ones, instead of six short core baselines.
- The Tricolour port sees long baselines with different RFI statistics.

The first-pass arm may flag more than K's 0.14 % of training cells, and its
held-out MSE could move either way. The image metrics are now interpretable,
because the PSF main lobe is resolved and the boxes come from it. A
`tv-policy` arm returning `original` is a measured null, not a failure.

Cost expectation: every kernel is single-threaded. A solve should scale
roughly with samples (about 70 s each against K's 0.32 s), the Tricolour port
with baselines (several minutes), and the TV loop with up to seven solves per
loop. The whole run may take an hour.

## Code to write after this commit (own files only)

- `python/rangtoy/core_campaign_array.py`: imports `core_campaign` and reuses
  its decision rule, Tricolour checks and receipts.
- `examples/{run,check,precondition,archive}_luno_array.py`.
- `tests/test_core_campaign_array.py`: offline and synthetic. It checks the
  bit-identity of the row-block features, gain application and residual
  amplitudes against K's functions, and the gridder-group sum on a small
  case.

No Rust and no shared file is edited.
