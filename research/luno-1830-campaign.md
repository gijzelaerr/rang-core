# Rang L2: the LUNO PKS 1830−211 campaign

Protocol frozen 2026-10-30 on branch `l2-1830` (from origin/main `07dfb86`),
before any campaign code was written. Protocol commit `ee74d6c`; code
`df01a01`, replay-check fix `262ba2c` (before the frozen runs). Task L2 of
[big-plan.md](big-plan.md), wave 3.

Status: **implemented and measured; null under both model arms.**

- The precondition passes (run `-00-precondition-b`): K's precondition
  unedited, the L2 driver's replay of K run `-01` (image hashes exempt by
  P2, peak and residual RMS within 2e-15), and the stored-model survey of
  MAIN_2 equal to the archive.
- 877,200,458 bytes fetched in 19 whole GETs, 136.5 s, no retry.
- Frozen runs `-02-stored` (25 min) and `-02-scalar` (37 min) cover all 56
  stations: 1,540 baselines, 15,400 rows, 126 M cells, 6.5 GB peak, on a
  host with load average 46–97.
- Criteria 1, 2, 3, 5, 7, 8 and 9 (`check-all`) pass. Criteria 4 and 6 **fail as frozen**,
  as expected: the Tricolour arms have invalid held-out predictions, so the
  headline primary call is undecidable under both models, and the stored
  model converges 5.2 % of intervals.
- The pre-registered headline (amendment 1's matched-sample call) is
  **null under both models**: TV policy vs first pass MSE ratio 0.99977
  (stored) and 0.99969 (scalar). Verdict: **null**.
- The cost clause **fails**: on the parallel kernels the TV chain takes
  4.6× (stored) and 5.9× (scalar) the Tricolour first pass, against the
  frozen limit of 3.
- Under the scalar model the policy selects nothing; under the stored model
  it selects a 2,302-cell unguided mask. Every TV-guided mask is rejected
  under both.

Details are in "Measured result". Archive:
[results/luno-1830-campaign.json](results/luno-1830-campaign.json).

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
| 09:30 | `pytest tests/test_core_campaign_1830.py` while writing (17, then 18 tests) | 0.5–4.2 s | 67 MB | the first run built the ctypes library |
| 09:32 | **fetch**, `examples/fetch_luno_1830.py` (`-01-fetch`) under `/usr/bin/time -v` | 2 min 23 s (fetch 136.5 s) | 194 MB | 19 objects, 877,200,458 B, 6.4 MB/s on one connection, no retry |
| 09:33 | precondition, `examples/precondition_luno_1830.py` (`-00-precondition`, code `df01a01`) | 4 min 50 s | 615 MB | **part 2 failed** on its own comparison: the residual-RMS *call ratio* of the first hypothesis differs from K's by 1e-15 (an image product under P2), and the code compared it exactly. Everything else equal. Bug fix `262ba2c`; see "Post-hoc steps" |
| 09:35 | labelled smoke, stations 0–11, stored model (`-00-smoke-stored`) | 4 min 47 s | 1.31 GB | ran beside the precondition; converged fraction 0.022 |
| 09:40 | labelled smoke, stations 0–11, scalar model (`-00-smoke-scalar`) | 2 min 49 s | 1.30 GB | converged fraction 0.95; survey 145 × status 0, 15 × status 3 |
| 09:41 | **precondition** rerun (`-00-precondition-b`, code `262ba2c`) | 1 min 09 s | 607 MB | all three parts pass |
| 09:45 | **frozen run, stored** (`-02-stored`), `examples/run_luno_1830.py` under `/usr/bin/time -v`; MemAvailable 12.7 GiB; load average 47–62 | **25 min 15 s** (user 1,431 s, sys 113 s, 101 % CPU) | **6.43 GB** | stage table below |
| 10:10 | **frozen run, scalar** (`-02-scalar`); MemAvailable 14.0 GiB; load average 46–97 | **36 min 39 s** (user 1,417 s, sys 106 s, 69 % CPU) | **6.48 GB** | stage table below |
| 10:51 | `examples/check_luno_1830.py` (`-02-check`) | 17.8 s | 104 MB | criteria 4 and 6 FAIL as frozen under both models; the rest pass; verdict null |
| 10:52 | `examples/archive_luno_1830.py` | 0.3 s | 22 MB | 178.0 KB archive |
| 10:55 | `bash tools/check-all.sh`, once before the final commit (`outputs/l2-1830-20261030-02.check-all.log`) | 57 min 31 s (pytest 588 passed, 1 skipped in 46 min 20 s) | 1.93 GB | overall **PASS**; load average 52–79 from sibling sessions; started before the coordinator's `flock /home/gijsm/.rang-checkall.lock` rule, so no lock wait (any later suite runs under the lock with `RAYON_NUM_THREADS=4`, `OPENBLAS_NUM_THREADS=1`) |

Stage times inside the frozen runs (`result.json` `stages`; `RAYON_NUM_THREADS=8`).
Cores busy is Δ(user + system) / Δwall; values near or below 1 for the
parallel kernels show contention with sibling sessions on the 16-thread host.

| Stage | Stored: wall | busy | Scalar: wall | busy | L1 (1934−638, 41,786 rows, single-threaded) |
| --- | ---: | ---: | ---: | ---: | ---: |
| input integrity (hash 93 objects, 1.95 GB) | 7.6 s | 0.34 | 4.6 s | 0.42 | 3.9 s |
| decode (64 whole tiles) | 93.8 s | 0.24 | 27.9 s | 0.36 | 38.2 s |
| model (eligibility, diagnostic; scalar: fit and prediction) | 123.4 s | 0.10 | 23.2 s | 0.30 | – |
| split (seed 7) | 23.0 s | 0.28 | 16.5 s | 0.46 | 31.8 s |
| solve `original` + per-baseline features | 45.7 s | 1.55 | 48.4 s | 1.35 | 269.0 s |
| Tricolour first-pass port (12 steps) | 44.4 s | 2.34 | 55.0 s | 1.91 | 763.5 s |
| solve `tricolour-firstpass` (with features) | 39.2 s | 1.71 | 47.2 s | 1.35 | 90.7 s |
| Tricolour mild port (10 steps) | 33.3 s | 1.72 | 48.9 s | 1.17 | 278.2 s |
| solve `tricolour-mild` | 31.7 s | 1.94 | 35.7 s | 1.54 | 149.6 s |
| TV loop (scores, TV; distinct candidate solves: 6 stored, 7 scalar) | 159.6 s | 2.44 | 277.0 s | 1.43 | 1,146.9 s |
| first-pass TV loop, frozen (base has no validation loss) | 0.0 s | – | 0.0 s | – | 0.0 s |
| first-pass TV loop, amendment 1 (base re-solve; 6 stored, 7 scalar candidate solves) | 200.6 s | 2.26 | 359.4 s | 1.26 | 1,418.1 s |
| image, per arm (correct, Briggs weights, one gridder group) | 99–134 s | 0.35–0.45 | 123–277 s | 0.20–0.33 | 232–840 s |
| amendment 1 calls | 21.8 s | 0.71 | 27.2 s | 0.60 | 56.2 s |
| four-station survey (identity and solved) | 1.4 s | 0.36 | 2.8 s | 0.36 | – |
| whole run | 1,511 s | 1.02 | 2,196 s | 0.69 | 7,660 s |

## Measured result (2026-10-30)

### Fetch

`outputs/l2-1830-20261030-01-fetch`: the 19 frozen objects, 877,200,458 B,
in 136.5 s on one connection (6.4 MB/s), 19 requests, no retry, every
response 200, every size equal to the probe's, every SHA256 equal to the
file on disk (`result.json`, `receipt-extra.json` with ETags and
Last-Modified, `objects/receipt.txt`). The probes fetched about 0.61 MB
before the protocol.

### Precondition

Run `-00-precondition-b` (1 min 09 s, code `262ba2c`, the code of the
frozen runs):

1. **K's precondition**, unedited, passes all eight checks, and χ², the
   survey, the mask hashes and counts, the converged and flagged-gain
   fractions equal the K archive.
2. **Replay.** The L2 driver on MAIN_1, stations 0–3, reproduces K's run
   `-01` exactly: split counts, all six arms' additions, gains, losses, TV
   and fixed-support TV, flag fractions, all 20 candidate records, the
   Tricolour counts and the MSE calls. Image hashes differ (P2, by design);
   the peak agrees to 4.8e-16 and the residual RMS to 1.2e-15 relative,
   within the frozen 1e-9. K's `result.json` hashes to the archive's value.
3. **Survey.** The stored-model identity survey of MAIN_2 equals the
   archive: 47,409 TRAIN cells, 160 bins with TRAIN, 0 fully identified,
   15 underidentified, 145 over-rank, 160 without TRAIN, status 6 on all
   160.

The first precondition run (`-00-precondition`) failed part 2 only through
an over-strict comparison (see "Post-hoc steps").

### Cells and the scalar model

- 15,400 rows × 2048 channels × 4 correlations, 1,540 baselines, 56
  stations, 10 integrations; 46.57 % of cells originally flagged.
- 16,850,156 eligible samples under both models (the DATA finiteness test
  removes none), split 13,480,057 / 1,683,974 / 1,686,125. The train,
  validation and test masks are **hash-identical** across the model arms.
- **Scalar fit.** Eleven tiles (8–10, 16–23) with 6,667–313,918
  short-baseline samples each; `I0 = 7.839` Jy at 1284 MHz and
  **`α = +0.222`**, log RMS residual 0.0030. The stored model's
  short-baseline |I| rises from 12.34 Jy (tile 8) to 13.21 Jy (tile 23),
  a slope of about +0.2 as well. The data amplitudes are 0.62 of the stored
  model's, about the squared gain amplitude (0.79²) that the stored arm
  solves for.
- The predictor returns the power law to 2.2e-16 relative with zero
  imaginary part.

### The identifiability survey under each model

| Model | Gain point | Fully identified | Underidentified | Over-rank | No TRAIN | Native status |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| stored | identity | 0 | 15 | 145 | 160 | 6 on all 160 |
| stored | solved (`original`, stations 0–3) | 0 | 15 | 145 | 160 | 6 on all 160 |
| scalar | identity | 145 | 15 | 0 | 160 | 145 × 0, 15 × 3 |
| scalar | solved | 145 | 15 | 0 | 160 | 145 × 0, 15 × 3 |

Under the scalar model the four-station bins are identified as the support
survey's scalar dry run predicted: every bin with an odd cycle is fully
identified, and the 15 tree-shaped bins (baseline 0–2 or a path through it)
are underidentified with status 3. Under the stored model the cross-hand
terms remove the gauge null, and the native kernel answers status 6
everywhere. No bin has a flagged solved gain. The policy does not consult
the survey.

### Criteria as frozen

| Criterion | Stored | Scalar |
| --- | --- | --- |
| 1 input integrity | **pass**: 93 objects re-hashed equal the receipts and the run; whole-tile headers; fetch complete and equal to the probe | **pass** |
| 2 flags preserved | **pass**: supersets, no held-out addition, stored additions match, inputs and `git status` unchanged; the derived row flag equals FLAG_ROW or all-flagged in every arm (1,620 rows, those of m031, m040, m044). L1's literal clause is false, as predicted | **pass** (same) |
| 3 precondition | **pass** | **pass** |
| 4 every arm solves | **fail**: converged fraction 0.052 (`original`), 0.049 (first pass); invalid predictions (train / validation / test) first pass 687 / 85 / 63, mild 213 / 28 / 18; the frozen `tricolour-firstpass+tv` is unavailable | **fail**: converged 0.937 (`original` and first pass); invalid predictions first pass 724 / 94 / 67, mild 213 / 28 / 18; `tricolour-firstpass+tv` unavailable |
| 5 Tricolour well formed | **pass**; additions identical across the model arms | **pass** |
| 6 hypotheses decidable | **fail**: the headline and third pairs are undecidable | **fail** (same) |
| 7 model arms well formed (across) | **pass**: predictor check, 11 tiles, `I0` finite and positive, identical splits | |
| 8 outputs | **pass** | **pass** |
| 9 `bash tools/check-all.sh` (across) | **pass**: Rust 19 + 55 tests, clippy, fmt, ruff, pytest 588 passed, 1 skipped | |

### The arms

MSE values are fused-pass held-out losses. Residual RMS, peak and far
residual robust σ in Jy/beam (the scalar arm's flux scale is a gauge, see
the protocol).

| Model | Arm | Additions (train) | Final flag fraction | MSE_test | Converged | Fixed-support TV | Peak | Residual RMS | Far residual robust σ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| stored | `original` | 0 | 0.465739 | 0.0472257 | 0.052 | 0.028993 | 12.5753 | 0.010963 | 0.005654 |
| stored | `tricolour-firstpass` | 181,109 (1.34 %) | 0.471482 | unavailable | 0.049 | unavailable | 12.5765 | 0.010981 | 0.005679 |
| stored | `tricolour-mild` | 42,518 (0.32 %) | 0.467087 | unavailable | 0.052 | unavailable | 12.5757 | 0.010962 | 0.005658 |
| stored | `tv-policy` (τ 5, α 0) | 2,302 | 0.465812 | 0.0472255 | 0.052 | 0.028971 | 12.5753 | 0.010963 | 0.005654 |
| stored | `tricolour-firstpass+tv-a1` (no change) | 181,109 | 0.471482 | unavailable | 0.049 | unavailable | 12.5765 | 0.010981 | 0.005679 |
| scalar | `original` | 0 | 0.465739 | 0.0649976 | 0.937 | 0.035387 | 7.8680 | 0.001873 | 0.001359 |
| scalar | `tricolour-firstpass` | 181,109 (1.34 %) | 0.471482 | unavailable | 0.937 | unavailable | 7.8690 | 0.001877 | 0.001363 |
| scalar | `tricolour-mild` | 42,518 (0.32 %) | 0.467087 | unavailable | 0.937 | unavailable | 7.8683 | 0.001874 | 0.001360 |
| scalar | `tv-policy` (no change selected) | 0 | 0.465739 | 0.0649976 | 0.937 | 0.035387 | 7.8680 | 0.001873 | 0.001359 |
| scalar | `tricolour-firstpass+tv-a1` (no change) | 181,109 | 0.471482 | unavailable | 0.937 | unavailable | 7.8690 | 0.001877 | 0.001363 |

`tv-unguided-best` equals `tv-policy` under the stored model and is a 2-cell
mask under the scalar model (MSE_test 0.0649976, indistinguishable).

**Gains.** Stored: median diagonal amplitude 0.789, off-diagonal 0.0081,
valid-gain fraction 0.913, 0.67 % of valid gains lost to the m000 gauge.
Scalar: 1.0015 (the flux rule puts the gain amplitude near unity) and
0.0103, the same valid fraction. Raw TV 0.0303 stored (time 0.0179,
frequency 0.0111) and 0.0382 scalar (time 0.0183, frequency 0.0171).

**Tricolour port** (identical under both models): first pass window flag
fraction 0.4729, 226,016 newly flagged cells, 181,109 on training samples;
mild 0.4674, 53,034 and 42,518. Both well formed.

**Images** (1024² at 1.5″, Briggs 0.5, one gridder group).

- PSF FWHM_max 12.0 pixels (18″) east–west, 5.7 north–south; main-lobe box
  half-width 19, far region beyond ±241 pixels; largest PSF value outside
  the main lobe 0.178, in the far region 0.040.
- Stored: peak 12.575 Jy/beam at pixel (511, 512), one pixel off centre as
  for 1934−638 in L1. Flux recovery 1.044 against mean Re model I and
  0.992 against mean |I|, the two pre-registered denominators (on the
  set described under "Post-hoc steps").
- Scalar: peak 7.868 Jy/beam at the centre (512, 512); recovery 0.999.
  The point-source residual is 2.4e-4 of the peak, against 8.7e-4 under the
  stored model: calibrating to a point at the centre makes the image a
  point at the centre.

**Model diagnostic** (eligible samples, by baseline length 0–0.2, 0.2–1,
1–3 and 3–9 km). Stored |I| 12.92, 12.79, 12.65, 12.52 Jy and mean Re I
12.88, 12.64, 11.83, 10.30 Jy: the stored model is offset from the phase
centre and a few per cent resolved, as the probe showed. Cross-hands
|XY/XX| 1.22e-3 and |YX/XX| 1.23e-3.

**Cross-model losses (descriptive, not a hypothesis).** The `original`
held-out MSE_test is 0.04723 under the stored model and 0.06500 under the
scalar model (ratio 1.38): the stored model's polarisation and structure
fit the data better, while its gains converge on 5 % of intervals against
94 %.

### Hypothesis calls

| Model | Pair | Primary MSE_test | Residual RMS | Matched MSE_test (dropped test samples) | Matched MSE_val |
| --- | --- | --- | --- | --- | --- |
| stored | `tv-policy` vs `tricolour-firstpass` (headline) | undecidable | 0.99834, null | **0.99977, null** (63 of 1,686,125) | 0.99975, null |
| stored | `tv-policy` vs `original` | 0.999995, null | 1.00004, null | 0.999995, null (0) | 1.000002, null |
| stored | `tricolour-firstpass+tv` vs `tricolour-firstpass` | undecidable (arm unavailable) | undecidable | undecidable | – |
| stored | `tricolour-firstpass+tv-a1` vs `tricolour-firstpass` | – | – | 1.000000, null (63) | 1.000000, null |
| scalar | `tv-policy` vs `tricolour-firstpass` (headline) | undecidable | 0.99816, null | **0.99969, null** (67) | 0.99964, null |
| scalar | `tv-policy` vs `original` | 1.000000, null (no change) | 1.000000, null | 1.000000, null (0) | 1.000000, null |
| scalar | `tricolour-firstpass+tv` vs `tricolour-firstpass` | undecidable (arm unavailable) | undecidable | undecidable | – |
| scalar | `tricolour-firstpass+tv-a1` vs `tricolour-firstpass` | – | – | 1.000000, null (67) | 1.000000, null |

**The L2 verdict, by the pre-registered rule: null** (both headlines null;
it rests on both models).

**Cost clause.** The TV chain (reference solve with features plus the loop)
took 205.3 s (stored) and 325.4 s (scalar) against 44.4 s and 55.0 s for
the first-pass port: ratios **4.63 and 5.92, not comparable** under the
frozen factor of three. In L1 (single-threaded kernels) the ratio was
1.85. P3 made the Tricolour port parallel over baselines, while the TV
chain keeps serial Python stages (per-baseline scores, 12 s; policy masks)
around six (stored) or seven (scalar) candidate solves. Both runs shared the host with load averages
of 46–97, so the absolute times are upper bounds; the ratio is what the
clause measures.

**What the candidates did.**

- Stored `tv-policy` loop: the unguided τ 8 (14 samples, objective
  1.249999) and τ 5 (2,302 samples, 1.249572) masks lower the objective;
  τ 5 is selected and moves MSE_test by 4.9e-6 relative. The unguided τ 3
  mask (95,984 samples) raises it. **Every TV-guided mask (α 1 and 3,
  103,723 and 269,601 samples, the 2 % cap) is inadmissible** (TV support
  lost or validation degraded beyond 1 %).
- Scalar `tv-policy` loop: every candidate is worse than no change
  (objectives 1.250027–1.330676; the α 1 and 3 masks are admissible but
  score 1.287–1.331). No change is selected.
- Amended first-pass loops (validation fixed to the 1,683,889 and 1,683,880
  samples the first-pass base predicts; the base re-solve equals the
  first-pass gains): every candidate is worse or inadmissible under both
  models; no change is selected.

All candidate records are in `candidates.json` and the archive.

### What this shows

On LUNO's gain calibrator PKS 1830−211, over the whole array and under both
a stored model with cross-hand terms and a scalar point model,
gain-TV-guided flagging does not change calibration or imaging quality
against the CARACAL first-pass flags. The frozen objective rejects every
TV-guided mask under both models. With K and L1 the campaign is null on
both LUNO calibrators, at four-station and array scale, and under both
model choices for the source whose model was in doubt. On the parallel
kernels, measured on a contended host, the TV chain also took 4.6–5.9
times the wall of the Tricolour first pass, so it is neither better nor
cheaper.

### What it does not show

- **The frozen primary headline is undecidable** under both models (the
  first pass removes the training support of some station-bins, as in
  L1). The verdict rests on amendment 1's matched calls, pre-registered in
  this protocol.
- **Convergence.** Under the stored model only 5 % of intervals converge in
  50 iterations, so its gains along the near-degenerate U(2) directions are
  what the frozen solver gives. Under the scalar model 94 % converge.
  Convergence is the subject of the wave 3 solver protocol (L5).
- **The models.** Neither is the true sky. The stored model is unlogged,
  offset and resolved; the scalar model ignores polarisation and structure
  and has no absolute flux scale. The cross-model MSE difference is
  descriptive.
- **Inputs.** They are processed: 46.6 % flagged, QuartiCal weights, an
  80 s scan (five gain time bins). L3 (native flags) remains.
- **Timing.** The host was heavily shared; stage times are upper bounds.

### Post-hoc steps, labelled

- The first precondition run (`-00-precondition`, code `df01a01`) failed
  part 2 because the code compared the residual-RMS hypothesis *call*
  exactly, including its ratio: K's 0.9999581520151 against
  0.9999581520151007. The protocol exempts image products from exact
  equality and bounds them at 1e-9, and the residual RMS feeds that ratio.
  The fix (`262ba2c`, before any frozen run) compares the residual-RMS
  call's verdict exactly and its ratio within 1e-9, and keeps the MSE calls
  exact; a test covers both. The rerun `-00-precondition-b` passes and is
  the precondition the frozen runs point at.
- **Flux-recovery denominator set (implementation deviation).** The
  protocol says "over the imaged samples". The code averages the model
  over samples unflagged in the arm's final flags with positive weights,
  whereas `image_arm`'s own set also drops invalid-gain cells and applies
  the Stokes I reader rule. On the `original` arm the two sets give the
  same mean Re model I to every printed digit (`image_arm`'s
  `model_stokes_i_jy` 12.0496 Jy stored and 7.8752 Jy scalar, recovery
  1.0436 and 0.9991), so the Re denominator is unaffected; the |I|
  denominator (12.678 Jy stored) is on the code's set.
- **Criterion 2 on candidates.** The checker, like L1's, verifies the
  arms' final flags only. Candidates hold by construction (each is
  `base | policy_mask(…, train)`: a superset of the base with additions
  on training samples only) and are not re-checked.
- Nothing else after the protocol commit: no setting was tuned, and the
  smokes found no bug.

## For the coordinator

- **Shared files.** None edited; `core_campaign.py` and
  `core_campaign_array.py` are untouched. Added:
  - `python/rangtoy/core_campaign_1830.py`
  - `examples/{fetch,precondition,run,check,archive}_luno_1830.py`
  - `tests/test_core_campaign_1830.py` (18 tests)
  - this report and `research/results/luno-1830-campaign.json` (178 KB)
- **Names imported from L1 and K** (the P5 merge must keep them, or update
  this module). From `core_campaign_array`: `ARRAY_IMAGE`,
  `ARCHIVED_INPUTS`, `CODE_FILES`, `EXTRA_KEYS`, `K_ARCHIVE`, `K_RUN`,
  `ROOTS`, `ROW_BLOCK`, `Stages`, `archived_receipts`,
  `available_hypothesis`, `build_state`, `compare_replay`, `cpu_seconds`,
  `image_arm`, `matched_calls`, `mem_available_gib`, `resolve`,
  `solve_arm`, `strip`, `tricolour_arm`, `tv_loop`, `valid_prediction`,
  `verify_object`. From `core_campaign`: `BUCKET`, `GROUP`, `TILES`,
  `CHANNELS`, `SUPPORT`, `SOLVE_INPUTS`, `STATIONS`, `IMAGE`, `GRID`,
  `ITERATIONS`, the policy constants, `STRATEGIES`, `STRATEGY_DIR`,
  `ROBUST`, `BETTER`, `WORSE`, `SPLIT_SEED`, `decode_object`,
  `fetch_extra`, `precondition`, `array_sha256`, `call`, `file_sha256`,
  `git_status`, `rss_mb`, `snapshot`, `write_json`.
- **Upstream change wanted in `core_campaign_array`** (not made here): give
  `run()`, `verify_inputs`, `input_keys`, `decode_inputs` and
  `decode_extra` the zarr group, the resolver roots and a model hook as
  parameters (L2 re-implements them by wrapping); let `verify_inputs`
  report fetched bytes; make the criterion 2 clause `FLAG_ROW |
  all-flagged` (L1's post-hoc finding, frozen here); let `compare_replay`
  take the P2 image tolerance.
- **`STATE.md`**, new top entry:

  > L2 PKS 1830−211 campaign (big plan wave 3), 2026-10-30 (implemented;
  > measured; null). The gain-TV-guided flagging campaign ran on the whole
  > array for LUNO's gain calibrator PKS 1830−211 (MAIN_2, the whole 80 s
  > scan: 56 stations, 1,540 baselines, 126 M cells) under two model arms
  > fixed in the protocol: the stored MODEL_DATA with its 1e-3 cross-hand
  > terms, and a scalar point at the phase centre predicted by the core
  > with a power law fitted to the short-baseline data (α = +0.22). 877 MB
  > of DATA and UVW were fetched whole in 137 s; the L2 driver replays K on
  > four stations and reproduces the archived survey. Under the scalar
  > model the four-station survey is fully identified except 15 tree bins
  > (status 0 and 3); under the stored model it is status 6 everywhere.
  > Criteria 4 and 6 fail as frozen (the Tricolour arms leave held-out
  > samples unpredictable; the stored model converges on 5 % of intervals,
  > the scalar on 94 %). The pre-registered matched headline is null under
  > both models (TV policy vs first pass 0.99977 and 0.99969); every
  > TV-guided mask is rejected; the cost is not comparable on the parallel
  > kernels as measured on a contended host (TV chain 4.6–5.9× the first
  > pass). Verdict null. Archive
  > `results/luno-1830-campaign.json` ([luno-1830-campaign.md](luno-1830-campaign.md)).
  > Next: L3 (native flags) when the data arrive, then L4.

- **`README.md`**, one line: the LUNO PKS 1830−211 campaign ran on the core
  under a stored and a scalar model (`rangtoy.core_campaign_1830`,
  `research/luno-1830-campaign.md`): null under both, 25–37 min per model
  on the parallel kernels.
- **`tool-timings.md`**: the rows of both timing tables above.
- **`big-plan.md`**: L2 done 2026-10-30, null under both model arms;
  criteria 4 and 6 failed as frozen, the matched headline is null; cost
  not comparable (4.6–5.9).
- **`flagging-luno-candidate.md`, "Still open"**: the 1830−211 MODEL_DATA
  is offset from the phase centre (mean Re I 12.9 → 10.3 Jy from under
  0.2 km to 3–9 km), a few per cent resolved (|I| 12.9 → 12.5 Jy), with a
  rising spectrum (12.3 → 13.2 Jy across the band); three stations (m031,
  m040, m044) are fully flagged with FLAG_ROW false (1,620 rows).
- **Upstream observations** (observed, not raised):
  1. RATT, QuartiCal `complex` (ported): with a model carrying 1e-3
     cross-hand terms, 50 iterations converge 5.2 % of intervals on the
     whole array, against 93.7 % under a scalar model on the same data
     (L1: 83 % on 1934−638). Input for L5's convergence study and U2's
     QuartiCal convergence-criterion report.
  2. caracal-pipeline, the CARACal first-pass calibrator strategy (run
     through the Tricolour port) on pre-flagged calibrator data: as in L1,
     it removes the whole training support of some station-bins (85
     validation and 63 test samples become unpredictable). A second source
     for U2's CARACal first-pass report.
  3. RATT, Tricolour (ported, P3): parallel over baselines, the first pass
     now takes 17–22 % of the TV chain's wall on the same cells.
  4. Not software (data provenance, for the observer): the stored 1830−211
     model is offset, resolved and unlogged; fully flagged rows keep
     FLAG_ROW false (a CASA `flagdata` convention, non-RATT).
  5. Non-RATT: whole-object GETs from the af-south-1 bucket ran at
     6.4 MB/s on one connection, with no retry in 19 requests.
- **Evidence to keep:** `outputs/l2-1830-20261030-00-probe` (12 KB),
  `-00-precondition-b` (16 MB), `-01-fetch` (837 MB; the only local copy
  of the MAIN_2 DATA tiles, needed to rerun; re-fetchable in about 2 min,
  so it may be deleted after L4), `-02-stored` and `-02-scalar` (55 MB
  each), `-02-check`, and the `.log` files.
- **Evidence that may be deleted:** `-00-precondition` (superseded by
  `-b`; it failed only on the comparison bug) and the labelled smokes
  `-00-smoke-stored` and `-00-smoke-scalar` (116 MB).
- **What the L4 verdict can now say.** Gain-TV-guided flagging is null on
  both LUNO calibrators (1934−638 at four stations and on the whole array;
  1830−211 on the whole array under two models), with a matched
  state-of-the-art comparator, pre-registered decision rules and the same
  seed-7 split. The frozen objective never admitted a TV-guided mask that
  beat no change; the only selections were tiny unguided threshold masks
  (21 cells on 1934−638, 2,302 on 1830−211 stored, none on 1830−211
  scalar), all within 5e-6 of no change. On the parallel kernels the
  TV chain also took 4.6–5.9 times the wall of the CARACAL first pass
  (measured on a host at load average 46–97). What
  could still change the answer: native (unprocessed) flags and weights
  (L3), and a converged solver (L5), since the stored-model gains converge
  on 5 % of intervals.
