# Rang L2: the LUNO PKS 1830−211 campaign

Protocol frozen 2026-10-30 on branch `l2-1830` (from origin/main `07dfb86`),
before any campaign code was written. Task L2 of [big-plan.md](big-plan.md),
wave 3.

Status: **proposed** (protocol only; nothing below "Measured result" exists
yet).

This is the gain-TV-guided flagging campaign of [task K](core-k-luno-campaign.md)
and [task L1](luno-array-campaign.md) on the second calibrator in
`LBAND_LUNO_CALIBRATORS.zarr`, the gain calibrator PKS 1830−211. K (four
stations) and L1 (whole array) on PKS 1934−638 were null. 1830−211 differs
in the ways that could change the answer: it is a lensed, variable,
polarised source; its stored MODEL_DATA has cross-hand terms of about 1e-3
that break the common-U(2) gauge of the support survey (status 6 on all 160
four-station bins, [flagging-luno-support.md](flagging-luno-support.md)); no
HISTORY row explains that model; its weights are nearly flat; and its row
chunk holds the whole 80 s scan.

The model decision is made here, as the user decided (big plan, "Solver
science" and wave 3): **both** models are arms of the protocol, (a) the
stored MODEL_DATA and (b) a scalar point model predicted by the core
predictor, and the identifiability survey is rerun under each.

Standing caveats: WEIGHT_SPECTRUM is a QuartiCal product (observer,
2026-10-29 15:37 SAST); neither calibrator's MODEL_DATA has a logged origin;
the inputs are processed (46.6 % of this chunk's cells are flagged). All
calibration numbers are conditional on the weights and on the model arm. The
licence is settled by user decision ([big-plan.md](big-plan.md)); results
are not labelled provisional on that account. Raw visibilities are never
committed: the archive holds numbers, flag fractions and hashes only.

## Question

On the whole MeerKAT array (LUNO PKS 1830−211, scan 3, 1070–1498 MHz), does
gain-TV-guided flagging change calibration or imaging quality relative to
the CARACAL first-pass Tricolour flags at comparable cost, under the stored
model and under a scalar point model? Everything runs on the core, exactly
as L1: the QuartiCal `complex` port, the fused pass, the Rust TV kernel, the
Tricolour/CARACAL port, Briggs weights and the w-stacking gridder, now with
the P1–P3 parallel kernels (`RAYON_NUM_THREADS=8`).

## Data cells (frozen; measured by the pre-protocol probes)

The two probes (`outputs/l2-1830-20261030-00-probe`, `probe.json` and
`probe2.json`) read only metadata, row columns, FLAG, WEIGHT_SPECTRUM and
MODEL_DATA; no DATA was read.

- Store `LBAND_LUNO_CALIBRATORS.zarr`, group **`MAIN/MAIN_2`** (FIELD_ID 2,
  PKS 1830−211, SCAN_NUMBER 3), **row chunk 0**. The group has 15,960 rows
  and one row chunk (zarr row chunk 15,960), so row chunk 0 is the whole
  scan. Channel tiles 8–23 (channels 1024–3071, 1070.0–1497.8 MHz), as K
  and L1.
- **Rows:** 15,400 cross-correlation rows, `FLAG_ROW` false on every row
  (no row is dropped), **1,540 baselines among all 56 stations**.
  - The 1,620 rows of m031, m040 and m044 (indices 25, 33, 37; 550 rows each
    less 30 shared) have every cell flagged in FLAG while FLAG_ROW is false.
    They are kept, as L1 kept the analogous rows; they hold no eligible
    sample.
- **Integrations:** 10 of 8.0 s (80 s). With the frozen 2-integration ×
  32-channel gain grid that is 5 time bins × 64 frequency bins × 56
  stations.
- **Sizes:** 15,400 × 2048 = 31,539,200 samples × 4 correlations. The
  original FLAG covers 46.57 % of cells. Eligible samples (no flag, positive
  finite weights, finite model) number 16,850,156 before the DATA
  finiteness test; per tile they range from 186,254 (tile 15) to 1,761,398.
- **Geometry:** maximum projected baseline 6,149 m (30,723 λ at 1497.8 MHz);
  maximum |w| 33,259 λ.
- **Weights:** median 0.38–0.40 in every tile, nearly flat, as the support
  survey reported.
- **Stored model:** median |Stokes I| 12.69 Jy, median |XY/XX| 1.24e-3 and
  |YX/XX| 1.24e-3. By baseline length the median |I| is 12.86, 12.74, 12.60
  and 12.48 Jy (0–200 m, 0.2–1 km, 1–3 km, 3–9 km) while the mean Re I is
  12.80, 12.61, 11.84 and 10.37 Jy: an offset from the phase centre (the
  1934−638 signature L1 found post hoc) plus a few per cent of resolved
  structure. On short baselines its |I| rises from 12.20 Jy (tile 8) to
  13.26 Jy (tile 23).

## Scope: the whole array directly (frozen)

The frozen run is the whole array. Four stations are not a second verdict:

- the four-station slice has 60 rows, and the archived survey there has no
  fully identified bin under the stored model;
- K showed that four stations are sidelobe-dominated and tree-limited;
- the whole scan is 37 % of L1's samples and affordable on the parallel
  kernels.

Four stations are used only for the identifiability survey (the native
normals are four-station) and for the labelled smoke (stations 0–11).

## Fetch (frozen)

Already on disk and hash-checked against their archived receipt lines
(`outputs/luno-support-20261029-01/slice/receipt.txt`): the MAIN_2 FLAG,
WEIGHT_SPECTRUM and MODEL_DATA tiles 8–23 (whole row chunks), their
`.zarray`, the row columns ANTENNA1, ANTENNA2, TIME, FLAG_ROW and
`MAIN/MAIN_2/.zattrs`. The ANTENNA, SPECTRAL_WINDOW, FIELD and POLARIZATION
subtables are shared by all groups and come from
`outputs/luno-solve-20261029-02/inputs` (its `receipt.txt`), as in L1.

Fetched, because no copy exists: **19 objects, 877,200,458 bytes** (sizes
from the probe's 16-byte ranged GETs):

- `MAIN/MAIN_2/DATA/.zarray` (369 B) and the 16 whole DATA tiles
  `MAIN/MAIN_2/DATA/0.{8..23}.0` (53,985,119–56,522,829 B each,
  876,893,850 B in all);
- `MAIN/MAIN_2/UVW/.zarray` (342 B) and `MAIN/MAIN_2/UVW/0.0` (305,897 B).

Every row of the chunk is needed, so ranged block fetches buy nothing; the
objects are fetched whole with `core_campaign.fetch_extra` (the task K whole
GET through `core_fetch.Client`, one connection) from the anonymous RATT
bucket into `outputs/l2-1830-20261030-01-fetch/objects`. The fetch writes
`receipt-extra.json` (status, bytes, seconds, SHA256 and response headers per
object) and a `receipt.txt` in the archived "bytes sha256 key" format, so
that one resolver serves three roots (fetch, support slice, solve inputs).
Expected: 877.2 MB in 1.5–4 min (task G moved 752 MB in 75 s with eight
workers; whole tiles ran at about 4 MB/s). The pre-protocol probes fetched
16 × 16 B tile heads, the two `.zarray` objects and UVW twice (about
0.61 MB); they are counted separately.

## The two model arms (frozen)

Every campaign arm below runs once under each model arm, in its own process
and run directory, so only one model array is held at a time.

**(a) `stored`:** MODEL_DATA as stored, cross-hand terms included.

**(b) `scalar`:** an unpolarised point source at the FIELD phase direction
with a power-law spectrum fixed from the data, predicted by the core
predictor (`core.predict_components`, the africanus `wsclean_predict` port
of [core-phase3c-a.md](core-phase3c-a.md)):

- **Flux rule.** Stokes I samples `0.5 (DATA_XX + DATA_YY)` on eligible
  samples (the stored arm's eligibility, see below) of rows with projected
  baseline `sqrt(u² + v²) < 200 m` (2,545 rows). Per channel tile, the
  median of |I|; tiles with fewer than 1,000 such samples are excluded (the
  probe gives eight tiles with support, 8–10 and 16–23, tile 23 with 6,667
  samples and 11–15 with none). An unweighted least-squares line through
  `log median` against `log(ν_tile/ν0)`, with ν_tile the tile's mean channel
  frequency and **ν0 = 1284 MHz**, gives `I0` and `α`.
- **Prediction.** One point component, `lm = (0, 0)`, `kind` point, flux
  `I0`, `log_poly` true, coefficient `[α]`, reference frequency ν0, on the
  run's UVW and channel frequencies. At `lm = (0, 0)` the predictor returns
  `I0 (ν/ν0)^α` exactly; the run asserts this to 1e-12 relative and a zero
  imaginary part. The model is XX = YY = S(ν), XY = YX = 0, stored as
  complex64.
- **Why the data and not a catalogue flux.** 1830−211 is variable; a
  published flux from another epoch would not be better, and none is quoted
  here without a source in hand. The overall flux and any smooth spectral
  slope are degenerate with the per-bin complex gains (32 channels span
  6.7 MHz, where a power law changes by less than 1 % for |α| ≤ 1), so
  the fit fixes the gain amplitude scale near the data rather than the
  physical flux. **No absolute flux is claimed from arm (b).** The data
  amplitudes contain the gain amplitudes, so `I0` is below the source flux
  by roughly the squared gain amplitude.
- **What (b) leaves out.** The source's polarisation (unmodelled cross-hand
  signal stays in the residual) and its lensed structure. An offset from the
  phase centre is antenna-separable and goes into the gain phases.
- The stored model's per-tile short-baseline |I| is reported beside the fit
  as a cross-check only.

**Comparability across model arms.** Eligibility includes a finite model;
the scalar model is finite everywhere, so the split can differ only if the
stored model is non-finite on an otherwise eligible sample. The run records
the SHA256 of the train, validation and test masks; criterion 7 requires
them identical across the two model arms. Tricolour additions do not depend
on the model and must also be identical across the arms. Cross-model
differences in held-out MSE are reported, descriptive only: arm (b) leaves
the polarised signal in the residual by construction, so the models are not
ranked by this campaign.

## The identifiability survey under each model (frozen)

The survey of [flagging-luno-support.md](flagging-luno-support.md) is rerun
per model arm. It is four-station (stations 0–3, the native
`flagging_influence.training_normals` limit):

- TRAIN cells: the four-station rows with FLAG_ROW false, no correlation
  flagged, all four weights positive, the arm's model finite;
- the 2 × 32 grid (5 × 64 = 320 bins), raw-eigenvalue rank with relative
  cutoff 1e-10, requirement `8 n_active − 4`, labels fully identified,
  underidentified, over-rank, no TRAIN, and, at solved gains, no solved
  gain;
- native status from `anchored_response(H, 0, 0, 0)` (the corrected call of
  the post-hoc audit);
- at two gain points: **identity**, and **the arm's own `original` solve**
  restricted to stations 0–3 (the whole-array gains of those stations).

Expected: under (a) at identity, the archived result exactly: 160 bins with
TRAIN data, 0 fully identified, 15 underidentified, 145 over-rank, 160
without TRAIN, native status 6 on all 160, 47,409 TRAIN cells (this is a
precondition check). Under (b), scalar models identify every bin with an
odd cycle: about 145 fully identified (status 0) and the 15 tree-shaped
bins underidentified (status 3).

**What the policy does with unsupported bins.** Nothing. As in K and L1, the
policy never consults the survey. Status-6, over-rank and underidentified
bins are solved, measured, entered in the TV map and flaggable like any
other bin; the full-Jones solver does not need the U(2) condition (the
cross-hand model removes gauge freedom, it does not add any). At array scale
the solver's valid-gain fraction, converged fraction and per-station valid
bins stand in for identifiability; no whole-array rank survey exists.

## Method (frozen; L1's unless stated)

Per model arm, in one process:

1. **Integrity.** Every object read is resolved across the three roots and
   must equal its receipt line (fetched objects: the fetch receipt;
   archived objects: their archived receipts) in size and SHA256 before it
   is decoded. Each tile's blosc `nbytes` must be 15,960 × 128 × 4 ×
   itemsize.
2. **Decode.** Row columns by `core.blosc_decode`; tiles by
   `core_zarr.read_rows` (Rust blosc) on the 15,400 kept rows into
   preallocated `(15400, 2048, 4)` arrays; json2 strings as plain JSON.
3. **Model.** Arm (a): MODEL_DATA. Arm (b): the scalar model above,
   replacing `arrays["MODEL_DATA"]` before the state is built.
4. **Eligibility and split.** L1's `build_state`, unedited: no original flag
   in any correlation, FLAG_ROW false, all four weights positive and
   finite, DATA and model finite; `split_holdout`, **seed 7**, 10 %
   validation, 10 % test, groups gain bin × baseline (`nant` = 56).
5. **Arms**, with L1's unedited functions (`solve_arm`, `tv_loop`,
   `tricolour_arm`, `image_arm`, `matched_calls`): `original`,
   `tricolour-firstpass` (`mk_rfi_flagging_calibrator_fields_firstpass.yaml`,
   the state-of-the-art comparator), `tricolour-mild`
   (`calibrator_mild_flagging.yaml`), `tv-policy` (the frozen one-round
   loop: τ ∈ {8, 5, 3} × α ∈ {0, 1, 3}, `max_fraction` 0.02, objective
   `fixed_support_TV/TV0 + 2 f + 0.25 MSE_val/MSE_val0`, admissible only if
   `MSE_val ≤ 1.01 MSE_val0` with fixed TV support, no change always
   available), `tv-unguided-best` (α = 0 ablation), `tricolour-firstpass+tv`
   (frozen first-pass loop) and **`tricolour-firstpass+tv-a1`** (L1's
   amendment 1 loop, adopted here from the start: validation fixed to the
   samples the first-pass base predicts; a candidate leaving any of them
   unpredicted is inadmissible). Solver: `G.type=complex`, 2 integrations ×
   32 channels, 50 iterations, convergence 1e-7, stop fraction 0.99, polar
   gauge on m000 for TV, held-out cells excluded and predicted afterwards.
   Additions are cells on training samples only.
6. **Images**, L1's geometry: **1024 × 1024 at 1.5″** (u_max × pixel = 0.22
   cycles per pixel at the top of the band; w-phase across the field at
   most 2.9 rad, 64 layers), Kaiser–Bessel 7, 1023×, padding 1.2, Briggs
   0.5, corrected `G_p^{-1} V G_q^{-H}`, invalid-gain cells flagged, the
   WSClean Stokes I reader rule. **One gridder group** (P2 holds 52 B per
   kept sample, under 1 GB here; L1 needed four groups and had a thin
   group-sum margin). Boxes from the `original` arm's PSF of the same model
   arm: main-lobe half-width `ceil(1.5 FWHM_max)`, far region outside
   half-width `min(width/4, max(32, ceil(20 FWHM_max)))` (width/4 = 256).
7. **Survey** (section above) after the arms, from the four-station rows
   and the model arm's own `original` gains.

## Quality metrics (frozen)

Per arm, L1's set: held-out weighted MSE (validation, test), training χ²,
fixed-support polar-gauge TV against `original`, raw/time/frequency TV,
valid-gain and converged fractions, median diagonal and off-diagonal gain
amplitudes, gauge-lost fraction, per-station valid bins; dirty-image peak,
PSF FWHM, PSF sidelobes, far-region RMS and robust σ, point-source residual
RMS (headline image metric), far residual RMS and robust σ; flagged
fractions, additions, Tricolour window fractions and newly flagged cells;
amendment 1's losses on each arm's validly predicted samples.

Added, pre-registered so that L1's post-hoc step is not repeated:

- **flux recovery against two denominators**, the mean Re model Stokes I
  and the mean |model Stokes I| over the imaged samples;
- **the model diagnostic**: the model's median |I| and mean Re I in the
  four baseline-length bands above, and the per-tile short-baseline |I|;
- for arm (b), `I0`, `α`, the tiles and sample counts used, and the
  predictor check.

## Cost metrics (frozen, measured)

L1's per-stage wall time, peak RSS (`getrusage` high-water mark and
`/usr/bin/time -v`) and cores busy, for: fetch (once), integrity, decode,
model, split, each solve, each Tricolour strategy, each TV loop, each image,
the amendment-1 calls, the survey and the whole campaign.

**Cost clause** (K's and L1's): the TV chain (reference solve with features
plus the `tv-policy` loop) is comparable if its wall is at most three times
the wall of the `tricolour-firstpass` port on the same cells. The kernels
are parallel since L1 ran (P1–P3), so stage times are not comparable to
L1's single-threaded table; both are reported, and the ratio is the
comparable quantity.

## What is never modified (frozen)

Input FLAG and FLAG_ROW: every arm builds new arrays through
`flagging.protected_flags`, and `assert_preserved` runs on every arm. No
file may change size or mtime under:

- `outputs/luno-support-20261029-01`
- `outputs/luno-solve-20261029-02`
- `outputs/core-k-20261030-01`
- `outputs/core-section6-20261029-02`
- `outputs/caracal-strategy-inputs-8f7bb363`
- `outputs/l2-1830-20261030-01-fetch` (after the fetch completes)

Runs write only into fresh `outputs/l2-1830-20261030-NN*` directories.

## Precondition (run before the fetch-dependent runs, gated)

In `outputs/l2-1830-20261030-00-precondition`:

1. **K's precondition reproduces on this host.** `core_campaign.precondition`
   runs unedited. All eight checks pass, and χ², the survey, the mask
   hashes and counts, the converged and flagged-gain fractions equal
   `precondition` and `section6_reference` in
   `results/core-k-luno-campaign.json` (L1's part 1).
2. **The L2 driver replays K.** The L2 driver on `MAIN/MAIN_1`, stations
   0–3, the stored model, K's image settings (512² at 8″, K's 9 × 9 and
   64 × 64 boxes) and one gridder group reproduces K's frozen run `-01`
   **exactly** in everything L1's `compare_replay` checks (shape, split
   counts, every arm's `additions_sha256`, `gains_sha256`, losses, TV,
   fixed-support TV, final flag fraction, additions; every candidate's
   mask hash, count, objective, acceptance; the Tricolour counts; the
   hypothesis calls) **except** the image products: P2 replaced the FFT,
   so `dirty_sha256` and `psf_sha256` no longer match by design
   ([p2-gridder.md](p2-gridder.md), images differ by about 2e-15 of the
   peak). For those, the peak and the residual RMS must agree within 1e-9
   relative and the hashes are reported. K's `result.json` must hash to the
   archive's `result_sha256`.
3. **The survey code reproduces the archive.** The stored-model,
   identity-gain four-station survey of MAIN_2 gives exactly the archived
   group 2 numbers (47,409 TRAIN cells; 160 / 0 / 15 / 145 / 160; status 6
   on all 160 under `(H, 0, 0, 0)`).

If any part fails, no campaign run starts and the failure is recorded here.

## Acceptance criteria (frozen)

Gated, per model arm unless stated:

1. **Input integrity.** The fetch receipt lists all 19 objects, each a 200
   response whose byte count equals the probe's size (877,200,458 B in
   all) and whose SHA256 equals the file on disk; every archived object
   equals its receipt line; every tile's blosc `nbytes` is
   15,960 × 128 × 4 × itemsize (65,372,160 B for DATA and MODEL_DATA).
2. **Flags preserved.**
   - For every arm and candidate: final ⊇ original cell for cell, no
     held-out cell carries an addition, `assert_preserved` passes;
   - the derived row flag equals `FLAG_ROW | (every cell flagged in the
     arm's final FLAG)` exactly (L1's post-hoc finding, pre-registered:
     expected 1,620 rows for `original`, the rows of m031, m040, m044). L1's
     literal clause, derived row flag equal to the input FLAG_ROW, is
     reported and is expected to be false;
   - the archived inputs and `git status` are unchanged.
3. **Precondition passed** (all three parts).
4. **Every arm solves** (L1's, unchanged): converged fraction ≥ 0.9, finite
   gains on every valid bin, zero invalid predictions on validation and
   test. An arm failing this is reported with its numbers and its primary
   hypothesis is undecidable.
5. **Tricolour arms well formed**: superset of the input, uniform over the
   correlations, monotone over the `or`-accumulated steps; and (across
   model arms) identical additions under (a) and (b).
6. **Hypotheses by the pre-registered rule** (K's, unchanged) on the fixed
   test cells, pairs (`tv-policy`, `tricolour-firstpass`) (headline),
   (`tv-policy`, `original`), (`tricolour-firstpass+tv`,
   `tricolour-firstpass`): *better* if `MSE_test(candidate) ≤ 0.99
   MSE_test(reference)`, *worse* if `≥ 1.01`, *null* otherwise; the same
   call on the point-source residual RMS beside it. A `tv-policy` that
   selects nothing is "no change selected", a null. Pass means every pair
   is decidable. **Amendment 1's matched-sample calls** (the three pairs
   plus `tricolour-firstpass+tv-a1` vs `tricolour-firstpass`, on held-out
   samples both arms predict) are computed for every pair from the start
   and reported as "primary: <call>; matched: <call> (dropped samples)".
7. **Model arms well formed** (across arms): the scalar model equals
   `I0 (ν/ν0)^α` to 1e-12 relative on every sample with zero cross-hands;
   the fit uses at least six tiles; `I0 > 0` and finite; the train,
   validation and test masks are hash-identical under (a) and (b).
8. **Outputs.** Per model arm `result.json`, `receipt.json`,
   `environment.json`, `side-effects.json`, `candidates.json`,
   `integrity.json`, `survey.json`, `flags/<arm>.npz` (additions only),
   `gains/<arm>.npz`, `images/<arm>-{dirty,psf}.fits`; the archive
   `results/luno-1830-campaign.json` under 200 KB with no visibilities.
9. `bash tools/check-all.sh` passes on the branch.

**The L2 verdict** (pre-registered, so that two model arms are not two
chances at a positive). Per model arm, the headline is the matched-sample
MSE_test call of `tv-policy` vs `tricolour-firstpass` (the primary call when
it is decidable and no sample is dropped, since the two then coincide),
with the cost clause.

- **Positive** only if the headline is *better* under **both** model arms,
  neither residual-RMS call is *worse*, and the cost is comparable.
- **TV worse** if the headline is *worse* under both.
- **Model-dependent** if the two headlines differ; this is reported as not
  established (it does not count as positive for L4).
- **Null** if both headlines are null (including "no change selected").
- An undecidable headline under one arm leaves the verdict to the other,
  labelled as resting on one model.

Reported, not gated: every cost number, the memory peak, the candidates,
the unguided best, the survey at solved gains, the cross-model losses, and
the model diagnostic.

The campaign runs once per model arm as frozen; failures are recorded with
their numbers, and any later step is labelled post-hoc with its own run
directory. A labelled smoke on stations 0–11 under both model arms precedes
the frozen runs and may fix bugs only, never frozen settings. The run is
deterministic: the split is seed 7, the solver is bit-identical at any
thread count (P1), and no other randomness exists.

## Memory budget (frozen)

Inputs held once: DATA and model complex64 1.01 GB each, WEIGHT_SPECTRUM
0.50 GB, FLAG 0.13 GB (2.65 GB). Arm (b) adds a 0.5 GB complex128
prediction transiently. L1's row-block code bounds the rest: float64
per-sample features 0.25 GB each during a TV loop, the Tricolour port about
1 GB, one gridder group under 1 GB plus about 0.5 GB of per-thread grids.
Planned peak about 6 GB; a peak above 10 GB is recorded as a budget
failure. A frozen run starts only if `MemAvailable` is at least 12 GiB (the
host's 30 GiB are shared with sibling sessions, including P5); the reading
is recorded, and the two model arms run one after the other.

## Expected outcome, stated before running

A null is the most likely result and is acceptable:

- K and L1 were null on 1934−638 at both scales; the frozen objective
  rejected every TV-guided mask there.
- The scan is short: five gain time bins, so the TV map is dominated by
  frequency edges.
- The weights are nearly flat (0.38–0.40), so the whitened residuals carry
  little weight structure for the scores to exploit.

Specific to 1830−211:

- **Under (a)**, the U(2) directions of the full-Jones gains are
  constrained only by the 1e-3 cross-hand model terms. Those directions are
  weakly determined, polar-gauge TV includes them, and convergence within
  50 iterations is likely below 0.9: criterion 4 probably fails as frozen,
  as in L1.
- **Under (b)**, the gauge is the common U(2) the survey assumes; the
  unmodelled polarisation and the lensed structure stay in the residuals,
  which may raise the residual-based outlier scores on long baselines and
  make unguided masks more attractive. Gains absorb the model offset as
  phase gradients.
- The stored model sits off the phase centre (mean Re I falls to 10.4 Jy at
  3–9 km), so under (a) the calibrated peak may land a pixel off centre and
  flux recovery against mean Re I will exceed 1; the |I| denominator is the
  meaningful one.
- The Tricolour first pass may again remove the whole training support of
  some station-bins, making the frozen headline undecidable; amendment 1's
  matched calls cover that case from the start.

What could move the answer: a bright, structured, polarised source whose
model errors are not uniform across baselines; if TV guidance has any value
on LUNO, it should show where the model is worst.

## Code to write after this commit (own files only)

- `python/rangtoy/core_campaign_1830.py`: group-, root- and
  model-parameterised fetch, integrity, decode and `run()`, composed from
  the unedited L1 building blocks (`solve_arm`, `strip`, `tv_loop`,
  `tricolour_arm`, `image_arm`, `valid_prediction`, `matched_calls`,
  `available_hypothesis`, `build_state`, `boxes_from_psf`,
  `compare_replay`) and K's (`precondition`, decision rule, receipts); the
  scalar model; the survey; the precondition and the checker.
- `examples/{fetch,precondition,run,check,archive}_luno_1830.py`.
- `tests/test_core_campaign_1830.py`: offline and synthetic (power-law fit
  and prediction, resolver, receipts, the derived row-flag clause, the
  verdict combination).

No Rust, no shared file and neither `core_campaign.py` nor
`core_campaign_array.py` is edited (P5 is changing them in parallel).

## Timings (every tool run of this task)

| When (UTC) | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 09:15 | `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | 83.4 s | – | includes the editable maturin build of the extension |
| 09:16 | `maturin develop --release` | 1.1 s | – | reused the editable build |
| 09:21 | probe 1: 16-byte ranged GETs of the 19 objects, MAIN_2 row columns, UVW, stored MODEL_DATA statistics (`-00-probe/probe.json`) | 13.1 s | 1.34 GB | before the protocol; no DATA |
| 09:23 | probe 2: FLAG structure, eligible support per tile, short-baseline support (`-00-probe/probe2.json`) | 6.8 s | 516 MB | before the protocol; no DATA |
