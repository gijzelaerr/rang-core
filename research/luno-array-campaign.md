# Rang L1: the whole-array LUNO campaign

Protocol frozen 2026-10-30 on branch `luno-array-campaign` (from origin/main
`df42ea0`), before any campaign code was written. Protocol commit
`e86bcb1`; amendment 1 (after the labelled smoke, before the frozen run)
`e6e0d07`. Task L1 of [big-plan.md](big-plan.md), wave 1.

Status: **implemented and measured; null result.**

- The precondition passes: K's run `-01` is reproduced bit for bit by the
  array driver on four stations.
- Frozen run `-01` covers all 53 stations with data: 1,378 baselines,
  41,786 rows and 342 M cells. It took 2 h 08 min with a 12.5 GB peak, on a
  host shared with sibling test runs.
- Criteria 1, 3, 5 and 7 pass. Criteria 2, 4 and 6 **fail as frozen**:
  - 2: the derived FLAG_ROW includes 571 rows that the input FLAG already
    flags completely;
  - 4: the converged fraction is 0.83 against 0.9, and the Tricolour arms
    have invalid predictions;
  - 6: the headline MSE call is undecidable, because the comparator's held-out
    loss is unavailable.
- Under amendment 1's matched-sample calls every decidable pair is **null**.
  The TV policy selected 21 unguided cells: every TV-guided candidate was
  worse than no change.
- The cost is comparable (ratio 1.85).

Details are in "Measured result". Archive:
[results/luno-array-campaign.json](results/luno-array-campaign.json).

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

## Amendment 1 (after the labelled smoke, before the frozen array run)

Committed 2026-10-30 after the labelled smoke on stations 0–11 and before the
frozen array run. Nothing else was tuned: pixel, image size, channel groups,
boxes, the split, the solver, the policy and the ±1 % band are unchanged.
The primary rule, criterion 4 and criterion 6 stay **exactly** as frozen, and
the frozen run reports them as they come out.

**What the smoke showed.** Smoke `-00-smoke-b` covered 66 baselines, 2,112
rows and 1,088,081 training samples. The `tricolour-firstpass` arm had
invalid predictions on 10 validation, 30 test and 183 training samples, so
all three of its frozen losses are unavailable.

The mechanism was checked sample by sample. The first pass flags *every*
training sample of stations 4 and 5 in gain frequency bin 9 (11–21 samples
per time bin), so the solver flags those station-bins. In the `original`
arm the same station-bins are valid. The held-out samples in those bins
cannot then be predicted.

This follows from the frozen design (holdout split before flagging; invalid
predictions make a loss unavailable), not from a driver bug. K's
bit-identical replay shows the driver mirrors K. Two consequences:

- the headline MSE call is undecidable;
- the frozen `tricolour-firstpass+tv` loop cannot start, because its base
  has no validation loss.

With 1,378 baselines the same is expected. The smoke also turned a crash in
that loop into the "unavailable" record criterion 4 asks for; that is a bug
fix.

**Added, secondary and pre-registered:**

1. **Matched-sample calls.** For each pair, take the held-out samples that
   *both* arms predict validly. MSE_test and MSE_val on those samples come
   from the fused pass, with the split labels restricted to them, and get
   the same ±1 % three-way call. The pairs are the three frozen pairs plus
   (`tricolour-firstpass+tv-a1`, `tricolour-firstpass`). The residual-RMS
   call is unchanged.
   - Every arm's train χ², validation and test losses on its own validly
     predicted samples are reported too.
   - A unit test checks that with no invalid prediction the matched loss
     equals the primary loss bit for bit.
2. **`tricolour-firstpass+tv-a1`.** The first-pass loop with its validation
   set fixed to the validation samples the first-pass base predicts validly.
   - The base is re-solved on that set: same flags, same gains, which is
     recorded.
   - MSE_val0 and every candidate's MSE_val are measured on that set.
   - A candidate that leaves any of those samples unpredicted has no
     validation loss and is inadmissible, like a loss of fixed TV support.
   - Everything else is the frozen loop.
   - It is imaged like any arm. The frozen `tricolour-firstpass+tv` is still
     attempted and reported as unavailable if its base has no validation
     loss.
3. **Reporting.** The headline is reported as "primary: <call or
   undecidable>; amendment 1, matched samples: <call>", with the number of
   dropped held-out samples. The `tv-policy` loop is unchanged; its base had
   no invalid prediction.

The precondition is rerun with the amended code into a fresh directory
before the frozen run (`-00-precondition-b`). The frozen run points at it.

## Timings (every tool run of this task)

| When (UTC) | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-30 | `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | 7.9 s | – | uv cache warm |
| 2026-10-30 | three scratch probes of the archived row columns, UVW and tile headers (row structure, uv extent, dead stations) | 1–3 s each | – | before the protocol |
| 2026-10-30 | `pytest tests/test_core_campaign_array.py` while writing (8, then 10 tests) | 0.2–1.6 s | 71–209 MB | one run failed on `cargo` missing from `PATH` (the TV kernel builds on demand), as in K |
| 05:40 | **precondition**, `examples/precondition_luno_array.py` (`-00-precondition`, code `4584936`) | 47.4 s | 310 MB | all three parts pass |
| 05:41 | labelled smoke, stations 0–11 (`-00-smoke`) | 69.9 s | 1.2 GB | **crashed**: the frozen first-pass TV loop raised because its base had no validation loss; bug fix (record the arm as unavailable), see amendment 1 |
| 05:43 | labelled smoke, stations 0–11 (`-00-smoke-b`) | 15 min 13 s | 2.6 GB | completed; found the invalid-prediction mechanism |
| 2026-10-30 | scratch mechanism check on `-00-smoke-b` (station-bins 4 and 5 × frequency bin 9) | about 10 s | – | after the smoke, before the amendment |
| 06:02 | **precondition** rerun with the amended code (`-00-precondition-b`, code `e6e0d07`) | 2 min 34 s | 314 MB | all three parts pass; ran beside the next smoke |
| 06:02 | labelled smoke, stations 0–11 (`-00-smoke-c`, amended code) | 19 min 30 s | 2.6 GB | amendment paths exercised |
| 06:22 | **frozen run `-01`**, `examples/run_luno_array.py` under `/usr/bin/time -v`; MemAvailable 27.2 GiB at start; load average 28 from sibling pytest runs | **2 h 07 min 40 s** (user 5,164 s, sys 140 s, 69 % CPU) | **12.46 GB** | stage table below |
| 08:31 | `examples/check_luno_array.py` (`outputs/luno-array-campaign-check-20261030-01`) | 5.7 s | 210 MB | criteria 2, 4 and 6 FAIL as frozen; 1, 3, 5 and 7 pass |
| 08:33 | post-hoc diagnostic (labelled): derived FLAG_ROW, and model Stokes I by baseline length (`outputs/luno-array-campaign-20261030-01-posthoc.json`) | 25.4 s | 5.3 GB | not part of the frozen run |
| 08:34 | `examples/archive_luno_array.py` | 0.1 s | 21 MB | 84.7 KB archive |
| 08:32 | `bash tools/check-all.sh`, once before the final commit (`outputs/luno-array-campaign-20261030-01.check-all.log`) | 22 min 04 s (pytest 749 passed in 21 min 22 s) | 1.87 GB | overall PASS (criterion 8); load average 19–27 from sibling sessions, against K's 96.6 s on an idle host |

Stage times inside the frozen run (`result.json` `stages`). Peak RSS is the
process high-water mark after the stage. Cores busy is
Δ(user + system) / Δwall; a value below 1 shows contention with sibling
sessions on the 8-core SMT host, since every kernel is single-threaded.

| Stage | Wall | Cores busy | Peak RSS | K (four stations) | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| input integrity (hash 92 objects, 5.9 GB, against the receipts) | 3.9 s | 0.62 | 51 MB | fetch 75.7 s | – |
| decode (64 whole tiles, Rust blosc) | 38.2 s | 0.54 | 7.25 GB | 0.36 s | 106 |
| split (seed 7) | 31.8 s | 0.50 | 9.87 GB | 0.04 s | – |
| solve `original` + per-baseline features | 269.0 s | 0.56 | 10.08 GB | 0.32 s | – |
| plain solve (`tricolour-firstpass`) | 90.7 s | 1.00 | 11.47 GB | 0.32 s | 283 |
| solve `tricolour-mild` | 149.6 s | 0.89 | 12.46 GB | 0.32 s | – |
| Tricolour first-pass port (12 steps) | 763.5 s | 0.62 | 11.42 GB | 1.55 s | 493 |
| Tricolour mild port (10 steps) | 278.2 s | 0.93 | 12.46 GB | 0.89 s | 313 |
| TV loop (scores, TV, 9 distinct candidate solves of 86–163 s each) | 1,146.9 s | 0.90 | 12.46 GB | 1.68 s (6 solves) | 683 |
| first-pass TV loop, frozen (its base has no validation loss) | 0.0 s | – | – | 1.67 s | – |
| first-pass TV loop, amendment 1 (base re-solve and 8 candidate solves) | 1,418.1 s | 0.82 | 12.46 GB | – | – |
| image, per arm (correct and weight, 4 × 512-channel grid groups) | 232–840 s | 0.42–0.97 | 12.46 GB | 3.9 s | 60 (at 0.97 busy) |
| amendment 1 calls (19 restricted fused passes) | 56.2 s | 0.92 | 12.46 GB | – | – |

## Measured result (2026-10-30)

### Precondition

Run `-00-precondition-b` (2 min 34 s) used the amended code, the same code
as the frozen run.

1. **K's precondition**, unedited, passes all eight of its checks. Its χ²,
   survey, mask hashes and counts, converged fraction and flagged-gain
   fraction equal the `precondition` and `section6_reference` blocks of
   `results/core-k-luno-campaign.json`.
2. **Four-station replay.** The L1 driver on stations 0–3 reproduces K's run
   `-01` **exactly**; K's `result.json` hashes to the archive's value.
   - Bit-identical: the split counts, all six arms' `additions_sha256` and
     `gains_sha256`, their train, validation and test losses, TV, final flag
     fractions, and image `dirty_sha256` and `psf_sha256`.
   - Equal: all 20 candidate records, the Tricolour counts and the three
     hypothesis calls.

   So every array-scale reimplementation is bit-identical on K's slice.
3. **Gridder groups.** Four channel groups against one call: the dirty-image
   L∞ is 7.5e-5 of the peak and the PSF L∞ is 7.6e-5. Both are within the
   frozen 1e-4, but the margin is thin.

The first precondition run (`-00-precondition`, code `4584936`) passed with
the same numbers.

### Frozen run `-01`

Run `outputs/luno-array-campaign-20261030-01`, checked in
`outputs/luno-array-campaign-check-20261030-01`.

**Cells.**

- 41,786 rows × 2048 channels × 4 correlations on 1,378 baselines: 53
  stations with rows and 32 integrations. m031, m040 and m044 have no rows.
- 59.99 % of cells carry an original flag.
- 34,238,823 eligible samples, split into 27,401,558 training, 3,419,206
  validation and 3,418,059 test samples.
- Nothing was fetched. All 92 objects (5.9 GB) equal their archived receipt
  lines.

**Criteria as frozen.**

| Criterion | Measured | Result |
| --- | --- | --- |
| 1 input integrity | 92 objects re-hashed by the checker, all equal to the receipts and to the run's own hashes; 64 blosc headers are whole chunks; 0 bytes fetched | **pass** |
| 2 flags preserved | final flags ⊇ original in every arm; no held-out cell added; `assert_preserved` passed; 5,198 archived input files and `git status` unchanged. But the *derived* row flag (`protected_flags` sets FLAG_ROW on rows whose every cell is flagged) differs from the input FLAG_ROW in every arm, `original` included: 571 kept rows are fully flagged in the input FLAG while FLAG_ROW is false. K's slice had none. | **fail** (FLAG_ROW clause) |
| 3 precondition | all three parts pass | **pass** |
| 4 every arm solves | converged fraction 0.833 (`original`, `tv-policy`), 0.831 (mild) and 0.807 (first pass): every arm is below 0.9 at the frozen 50-iteration cap. Invalid predictions (train / validation / test): first pass 5,948 / 680 / 678, mild 1,263 / 120 / 111, none in the other arms. The frozen `tricolour-firstpass+tv` arm is unavailable. | **fail** |
| 5 Tricolour arms well formed | both strategies: superset of the input, uniform over the correlations, monotone over the `or` steps | **pass** |
| 6 hypothesis | the headline and third pairs are undecidable, because the comparator's test MSE is unavailable; the second pair is decidable | **fail** (undecidable) |
| 7 outputs | every required file present | **pass** |

**Criterion 2, post-hoc diagnostic (labelled; no verdict changes).** The input
FLAG_ROW is never written, and the archived files are unchanged. The derived
row flag equals `FLAG_ROW | (every cell flagged in FLAG)` exactly in
`original` and `tv-policy`. The Tricolour arms complete 57 more rows (first
pass) and 43 more (mild) through their additions. No arm clears a flag. The
clause was written for K's slice, where the derived and input row flags
coincide.

**The arms.** "valid" means amendment 1's losses on each arm's validly
predicted samples. For arms without invalid predictions they equal the
frozen losses.

| Arm | Additions (train) | Final flag fraction | MSE_test frozen | MSE_test valid | χ²_train valid | Converged | Fixed-support TV vs `original` | Peak (Jy/beam) | Residual RMS (Jy/beam) | Far residual robust σ (Jy/beam) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `original` | 0 | 0.599910 | 0.2088876 | 0.2088876 | 0.2081362 | 0.8333 | 0.0260508 | 14.80039 | 0.0164236 | 0.0039958 |
| `tricolour-firstpass` | 613,116 (2.24 %) | 0.607074 | unavailable | 0.2089681 | 0.2082459 | 0.8075 | unavailable | 14.79826 | 0.0164992 | 0.0040557 |
| `tricolour-mild` | 299,575 (1.09 %) | 0.603410 | unavailable | 0.2089201 | 0.2081837 | 0.8314 | unavailable | 14.79945 | 0.0164884 | 0.0040023 |
| `tv-policy` (τ 5, α 0) | 21 | 0.599910 | 0.2088872 | 0.2088872 | 0.2081370 | 0.8333 | 0.0260440 | 14.80039 | 0.0164237 | 0.0039957 |
| `tv-unguided-best` (same mask) | 21 | 0.599910 | 0.2088872 | 0.2088872 | 0.2081370 | 0.8333 | 0.0260440 | 14.80039 | 0.0164237 | 0.0039957 |
| `tricolour-firstpass+tv` (frozen) | – | – | unavailable | – | – | – | – | – | – | – |
| `tricolour-firstpass+tv-a1` (no change selected) | 613,116 | 0.607074 | unavailable | 0.2089681 | 0.2082459 | 0.8075 | unavailable | 14.79826 | 0.0164992 | 0.0040557 |

**Gains and the Tricolour port.**

- The valid-gain fraction is 0.854 (`original`) and 0.842 (first pass).
- The median diagonal gain amplitude is 0.790 and the median off-diagonal
  0.0083.
- 1.6 % of valid gain cells drop out of TV support because of the m000 gauge.
- The first-pass port's window flag fraction is 0.609, with 762,924 newly
  flagged cells; mild gives 0.604 and 372,404.

**The image** (1024² at 1.5″, Briggs 0.5).

- **PSF.** The main-lobe FWHM_max is 10.4 pixels (15.6″) east–west and 5.0
  pixels north–south. That gives a main-lobe box half-width of 16 pixels and
  a far region beyond ±209 pixels. The largest PSF value outside the box is
  0.277; in the far region it is 0.038.
- **Noise.** The far-region dirty RMS is 0.071 Jy/beam, dominated by
  sidelobes. The point-source residual leaves a robust σ of 4.0 mJy/beam
  there.
- **Peak.** 14.800 Jy/beam at pixel (511, 512), one pixel off centre.
- **Flux recovery is 1.119 against the frozen denominator.** That
  denominator is the mean of *Re* model Stokes I, 13.22 Jy.
  - The post-hoc diagnostic shows MODEL_DATA has |I| = 14.96 Jy on every
    baseline length, but a phase that grows with baseline: mean Re I is
    14.95 Jy below 200 m and 8.45 Jy at 3–8 km.
  - So the model places 1934−638 about 1.5″ off the FIELD phase centre,
    which is where the calibrated peak lands.
  - Against |I| the recovery is 0.989.

**Hypothesis calls.**

| Pair | Frozen MSE_test | Frozen residual RMS | Amendment 1 matched MSE_test (dropped test samples) | Matched MSE_val |
| --- | --- | --- | --- | --- |
| `tv-policy` vs `tricolour-firstpass` (headline) | **undecidable** | 0.99542, null | **0.999426, null** (678 of 3,418,059) | 0.999386, null |
| `tv-policy` vs `original` | 0.999998, **null** | 1.000000, null | 0.999998, null (0) | 0.999995, null |
| `tricolour-firstpass+tv` vs `tricolour-firstpass` | **undecidable** (arm unavailable) | undecidable | undecidable | – |
| `tricolour-firstpass+tv-a1` vs `tricolour-firstpass` | – | – | 1.000000, null (678) | 1.000000, null |

**Cost clause.** The TV chain (reference solve with features, 269 s, plus the
loop, 1,147 s) took 1,416 s. The first-pass port took 764 s. The ratio is
1.85, inside the frozen factor of three: **comparable**. Neither method is
materially cheaper.

**What the candidates did.**

- **`tv-policy` loop.** Only the two smallest unguided masks lower the
  objective: τ 8 (2 samples, 1.249782) and τ 5 (21 samples, 1.249740), against
  1.25. The τ 5 mask is selected.
  - Every TV-guided mask (α 1 and 3, 8,422–147,850 samples) raises the
    objective, to 1.2543–1.2759. So does the unguided τ 3 mask (4,125
    samples, 1.2507).
  - TV guidance therefore contributes nothing. The selection is a 21-cell
    threshold mask that moves the held-out MSE by 2.3e-6 relative.
- **Amended first-pass loop.**
  - Its base re-solve gives gains identical to the first-pass arm, and the
    loop drops 680 unpredictable validation samples.
  - All eight distinct candidates are worse than no change: 5,615–160,770
    samples, objectives 1.2504–1.2743.

All 21 candidate records are in `candidates.json` and the archive.

### What this shows

On the whole MeerKAT array, the scale the method was designed for,
gain-TV-guided flagging does not change calibration or imaging quality on
LUNO 1934−638 row chunk 0. The frozen objective rejects every TV-guided
mask. The selected 21-cell unguided mask is indistinguishable from no
change.

On matched held-out samples, the TV policy and the CARACAL first-pass flags
agree within 6e-4 in MSE and 0.5 % in residual RMS. The first pass flags
2.2 % of training samples (0.14 % on four stations) and improves no metric.

Together with K, this is a **null result at both scales** with a matched
comparator: the expected outcome.

### What it does not show

- **The frozen headline call is undecidable.** The comparator removes the
  whole training support of some station-bins, so their held-out samples
  cannot be predicted. The verdict rests on amendment 1, which was committed
  after the subset smoke and before the frozen run.
- **Convergence.** Only 83 % of intervals converge within the frozen 50
  iterations, against 98 % on four stations. The gains are what the frozen
  solver gives. Convergence and initialisation belong to P1.
- **Inputs.** They are processed: 60 % flagged, QuartiCal weights, and an
  unlogged model about 1.5″ off centre. L2 (1830−211) and L3 (native flags)
  remain.
- **Timing.** The host was shared, so stage times are upper bounds; the
  cores-busy figure measures the contention.

### Post-hoc steps, labelled

- The first smoke's crash became an "unavailable" record, as criterion 4
  asks.
- Amendment 1 was committed before the frozen run.
- After the run: the criterion 2 and model-phase diagnostics
  (`-01-posthoc.json`, scratch script). Neither changes a frozen number or
  call.

## For the coordinator

- **Shared files.** None edited. `core/` is unchanged, so no `pub mod` line
  is needed. Added files:
  - `python/rangtoy/core_campaign_array.py`
  - `examples/{run,check,precondition,archive}_luno_array.py`
  - `tests/test_core_campaign_array.py` (10 tests)
  - this report
  - `research/results/luno-array-campaign.json` (84.7 KB)
- **`STATE.md`**, new top entry:

  > L1 (big plan wave 1), 2026-10-30 (implemented; measured; null). The
  > gain-TV-guided flagging campaign ran on the whole of LUNO 1934−638 row
  > chunk 0 on the core: 53 stations, 1,378 baselines, 342 M cells, local
  > whole tiles, no fetch. The array driver reproduces K's run bit for bit
  > on four stations. The run took 2 h 08 min with a 12.5 GB peak on a
  > shared host.
  >
  > Frozen criteria 2, 4 and 6 fail as frozen: the derived FLAG_ROW covers
  > 571 input-flagged rows, convergence is 0.83 at the 50-iteration cap, and
  > the headline is undecidable because the Tricolour comparator's held-out
  > loss is unavailable. Amendment 1's matched-sample calls are null on
  > every pair (TV policy vs first pass: MSE ratio 0.99943, residual RMS
  > 0.9954). The policy selects a 21-cell unguided mask and rejects every
  > TV-guided mask. Cost is comparable (1.85).
  >
  > The result is null at both four-station and array scale. Archive
  > `results/luno-array-campaign.json`. Next: L2 and L3 for L4; the array
  > solve's convergence goes to P1.

- **`README.md`**, one line: the whole-array LUNO campaign ran on the core
  (`rangtoy.core_campaign_array`, `research/luno-array-campaign.md`): null at
  array scale, about 2 h single-threaded on 342 M cells.
- **`tool-timings.md`**: the rows of both timing tables above.
- **`big-plan.md`**: L1 done (null; the frozen headline is undecidable,
  amendment 1 is null). The G2 whole-array baseline is the stage table
  above.
- **`flagging-luno-candidate.md`, "Still open"**: the 1934−638 MODEL_DATA is a
  14.96 Jy point about 1.5″ from the FIELD phase direction. Mean Re I falls
  to 8.45 Jy on 3–8 km baselines. This is more evidence for an unlogged
  prediction step.
- **Upstream observations** (observed, not raised):
  1. RATT, QuartiCal `complex` (ported): at whole-array scale with rang's
     settings, 50 iterations converge 83 % of intervals, against 98 % on four
     stations. U1 could check the default iteration cap and convergence
     criterion for full arrays on the latest release.
  2. RATT, CARACal first-pass strategy on pre-flagged calibrator data: it
     flags 762,924 new cells, and some station × 32-channel bins lose every
     unflagged sample, so a solver loses those gains.
  3. Non-RATT: the store's 50,000-row × 128-channel chunking forces
     whole-tile decode (38 s single-threaded).
- **Evidence to keep:**
  - `outputs/luno-array-campaign-20261030-00-precondition-b`
  - `outputs/luno-array-campaign-20261030-01` (68 MB) and `-01-posthoc.json`
  - `outputs/luno-array-campaign-check-20261030-01`
  - the `.log` files
- **Evidence that may be deleted:** `-00-precondition` (superseded by `-b`,
  same numbers) and the labelled smokes `-00-smoke`, `-00-smoke-b` and
  `-00-smoke-c` (93 MB).
- **For S1, the measured scaling from 4 to 56 stations** (cells × 217.6,
  baselines × 229.7):

  | Stage | Four stations | Whole array | Ratio | Note |
  | --- | ---: | ---: | ---: | --- |
  | plain solve | 0.32 s | 90.7 s | 283× | |
  | Tricolour first pass | 1.55 s | 763.5 s | 493× | about 305× in CPU at 0.62 cores busy |
  | Tricolour mild | 0.89 s | 278.2 s | 313× | |
  | TV loop | 1.68 s | 1,147 s | | nine candidate solves |
  | image | 3.9 s | 232 s | | at full occupancy; 4× grid area, and four channel groups multiply the 64-layer Bluestein FFT work by four on the 1229² padded grid |
  | decode | 0.36 s | 38.2 s | | whole tiles |
  | peak RSS | 461 MB | 12.46 GB | | |

  K's driver unchanged would have kept about 44 GB of complex128 residuals,
  33 GB of `apply_gains` temporaries and 6.85 GB of gridder samples. The
  row-block reimplementations here are bit-identical on K's slice and stay
  at 12.5 GB.

  Biggest wins:
  1. parallel solve and fused pass (20 solves are about half the wall);
  2. the gridder: power-of-two padding or FFT reuse, and compact samples so
     channel groups are not needed;
  3. a parallel Tricolour port over baselines;
  4. the fused pass's own scores instead of `residual_features`.
