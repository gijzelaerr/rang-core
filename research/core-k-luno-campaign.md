# Rang core, wave 2 task K: the first real-data campaign on LUNO

Protocol frozen 2026-10-30 on branch `core/k-luno-campaign` (from origin/main
`d6a0916`), before any campaign code was written. Protocol commit `c1aa882`.
Status: **implemented; measured: the precondition and the single frozen run
`-01` pass all seven gated criteria; the pre-registered hypothesis returns
null on every pair (TV-guided flagging selects no additional flag on the
LUNO 1934−638 slice; the Tricolour first-pass strategy adds 128 training
cells and moves the held-out MSE by 6e-5 relative); cost comparable (TV
chain 2.0 s against 1.5 s for the Tricolour port); results provisional
under the open licence** (section "Measured result"). Archive:
[results/core-k-luno-campaign.json](results/core-k-luno-campaign.json).
Task K of
[core-parallel-plan.md](core-parallel-plan.md): the first science campaign
on real MeerKAT data with the Rust core, on the LUNO PKS 1934−638 calibrator
scan that the [candidate report](flagging-luno-candidate.md),
[support survey](flagging-luno-support.md), [solved-gain
survey](flagging-luno-solved.md), [section 6 prototype](core-section6.md)
and [task G](core-g-http-fetch.md) prepared. Unlike every `core-*` task
before it, this is not a reimplementation: it asks a scientific question
and may return a null result, which is acceptable and will be recorded.

## Licence precondition (open; results provisional)

- The LUNO stores carry no licence text. The observer, Ben Hugo, said in
  chat on 2026-10-29 at 15:36 SAST: "you can use it. Just cite the Sarao
  data usage acknowledgement". Written confirmation from SARAO is pending.
- Every result of this campaign is therefore **provisional** until SARAO
  confirms. No visibilities are redistributed: fetched bytes stay in
  ignored `outputs/`; the committed archive
  `results/core-k-luno-campaign.json` holds numbers, flag fractions, hashes
  and small summaries only, never DATA, MODEL_DATA, WEIGHT_SPECTRUM or UVW.
- The exact SARAO data-usage acknowledgement text must be checked against
  the MeerKAT data policy before any publication; the wording commonly used
  is recorded in [flagging-luno-candidate.md](flagging-luno-candidate.md#still-open).
- Also open and inherited from the candidate report: WEIGHT_SPECTRUM is a
  QuartiCal product (observer, 15:37 SAST), SIGMA_SPECTRUM does not match
  the DATA scatter, the 1934−638 MODEL_DATA has no logged origin, and the
  observer's full-resolution L-band dataset has not arrived and is not
  waited for or touched. Every solve below is weighted by the processed
  WEIGHT_SPECTRUM against the unlogged model, so all calibration numbers
  are conditional on both.
- `FLAG` and `FLAG_ROW` of the inputs are never modified. Flags are
  produced as new arrays, compared, and kept in the run directory; the
  original flags are an immutable lower bound in every arm
  (`rangtoy.flagging.protected_flags`).

## Question

On the real LUNO PKS 1934−638 four-station slice, does gain-TV-guided
flagging, run entirely on the core (fetch through `core_fetch`, decode
through `core_zarr`, solve through the core's QuartiCal `complex` port, MAD
scores and split losses through the fused pass, TV through the Rust kernel,
flags compared with the core's Tricolour/CARACAL port, Stokes I, Briggs
weights and dirty images through `core_weights`, `core_grid`), change
calibration and imaging quality relative to the Tricolour/CARACAL baseline
flags, at comparable cost?

Under AGENTS.md the claim to test is: higher calibration/imaging quality at
comparable cost, or comparable quality at materially lower cost, against a
relevant state-of-the-art method, here the CARACAL first-pass calibrator
strategy as Tricolour 0.2.1 runs it (ported flag for flag in
[task D](core-d-tricolour.md)). Comparisons are matched: same cells, same
held-out cells, same solver, same model, same weights, same imager. The
unguided threshold ablation (TV weight 0) is part of the grid, not the
state-of-the-art comparator.

## Data cells (frozen)

- Store `LBAND_LUNO_CALIBRATORS.zarr`, group `MAIN/MAIN_1` (field
  J1939−6342 = PKS 1934−638, scan 2), row chunk 0 (32 integrations, about
  248 s), stations 0–3 (m000–m003), cross rows with `FLAG_ROW` false (192
  rows), channels 1024–3071 (tiles 8–23, 1070.0–1497.8 MHz). These are
  exactly the cells of the solved-gain survey, section 6 and task G.
- Why not wider. The four-station slice is the only LUNO cell set with
  oracles: QuartiCal's archived gains and flags
  (`results/meerkat-luno-solved.json`), the section 6 arrays and products,
  and task G's byte hashes. The comparator precondition below needs them.
  Widening to the whole array for the same 16 tiles would move 4.87 GB in
  about 679 s whole-tile (task G) with no archive to check against, and
  the whole-array solve would be a new, un-oracled computation; it is a
  follow-up, not this campaign. The cost of the frozen slice is known:
  751.8 MB in 74.5 s (task G run `-01`).
- Additional objects, fetched whole and hash-checked against the archived
  `outputs/luno-solve-20261029-02/inputs/receipt.txt` lines:
  `MAIN/MAIN_1/UVW/0`, `ANTENNA/ANTENNA_0/POSITION/0.0`,
  `ANTENNA/ANTENNA_0/NAME/0` (json2), `SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ/0.0`,
  `SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH/0.0`,
  `FIELD/FIELD_0/PHASE_DIR/0.0.0`, `FIELD/FIELD_0/NAME/0` (json2),
  `POLARIZATION/POLARIZATION_0/CORR_TYPE/0.0`, and their `.zarray` files.
  They are needed by the Tricolour port (antenna positions for the
  `uvrange` static mask, channel frequencies and widths, correlation
  types) and by the imager (UVW, phase centre). Nothing else is fetched.
- PKS 1830−211 (`MAIN_2`, scan 3) is **not** in the gated scope. The
  support survey found that its MODEL_DATA carries unlogged cross-hand
  terms that break the frozen common-U(2) gauge (native status 6 on all
  160 supported bins) and the row chunk holds only 10 integrations. Running
  the campaign on it would need a model decision this protocol does not
  make. It is recorded as a follow-up.
- Nothing from the observer's offered full-resolution dataset is used.

## Method (frozen)

Everything runs in one Python process on the core; no Measurement Set,
container, QuartiCal, Tricolour, WSClean or python-casacore.

1. **Fetch** with `rangtoy.core_fetch.fetch_slice` exactly as task G
   (eight workers, single byte ranges, retries recorded), plus the whole
   objects above through the same `Client`. Receipt per request as in G.
2. **Decode** with `core_fetch.decode_slice` (Rust blosc, block-selective);
   json2 string arrays are decoded as plain JSON only (no pickle), as the
   earlier probes did.
3. **Eligibility and split.** Eligible cells: no original flag in any
   correlation, `FLAG_ROW` false (all 192 rows), all four weights
   positive, DATA and MODEL_DATA finite. `rangtoy.flagging.split_holdout`
   with **seed 7**, 10 % validation, 10 % test, groups = gain bin ×
   baseline, minimum two training cells per group: the frozen rule of
   `flagging_workflow.prepare`. The same split is used by every arm, so
   validation and test cells are identical across arms.
4. **Solve** per arm with `rangtoy.core_workflow.core_solve` (the core
   mirror of the frozen `flagging_workflow.solve`): `G.type=complex`, 2
   integrations × 32 channels, 50 iterations, convergence 1e-7, stop
   fraction 0.99, reference antenna 0, polar gauge for TV, held-out cells
   excluded from the solve and predicted afterwards. Flags seen by the
   solver are `protected_flags(original, rows, holdout ∪ additions)`.
5. **Arms** (additions are cells, coupled over the four correlations, and
   only on training cells, as `flagging_caracal.training_proposal` imports
   external flags; held-out cells are never flagged by any arm):
   - `original`: no additions. The reference.
   - `tricolour-firstpass`: `rangtoy.core_flag.flag_rows` with
     `mk_rfi_flagging_calibrator_fields_firstpass.yaml` from
     `outputs/caracal-strategy-inputs-8f7bb363` (SHA256 in
     `results/caracal-strategies.json`), on DATA of the 192 rows with the
     original flags as input, the two shipped static masks, the ECEF
     positions of all 56 antennas. Additions = training cells the port
     flags. This is the state-of-the-art comparator.
   - `tricolour-mild`: the same with `calibrator_mild_flagging.yaml`
     (the second control of task D). Reported beside the first.
   - `tv-policy`: the frozen training loop of `flagging_workflow.train`
     on the core: from the `original` solve, robust log-amplitude scores
     `residual_features` on whitened residuals, TV guidance from the
     polar-gauge TV map, the nine policy masks τ ∈ {8, 5, 3} × α ∈ {0, 1,
     3} with `max_fraction` 0.02, one round; each distinct mask re-solved;
     objective `fixed_support_TV/TV0 + 2 f + 0.25 MSE_val/MSE_val0` with
     `MSE_val ≤ 1.01 MSE_val0` and fixed TV support; the best accepted
     candidate is the arm, and no-change is always available. All nine
     candidates are recorded; `tv-unguided-best` (α = 0) is reported as the
     ablation.
   - `tricolour-firstpass+tv`: the same loop seeded from the
     `tricolour-firstpass` solve (candidates = first-pass additions ∪
     policy mask, objective relative to the first-pass arm). Does TV add
     anything on top of the comparator?
6. **Imaging** per arm, on the arm's final flags (original ∪ additions;
   held-out cells are not excluded from imaging): corrected visibilities
   `G_p^{-1} V G_q^{-H}` per cell from the arm's gains, cells with invalid
   gains flagged; Stokes I sample and weight by `core_grid.stokes_i_reader`
   (WSClean's reader rule); Briggs 0.5 imaging weights by
   `core_weights.imaging_weights` on the padded 616-pixel grid, rank filter
   3.0/16; `core_grid.invert` 512 × 512 at 8″, Kaiser–Bessel 7, 1023×, 64
   w-layers, padding 1.2 (the archived rang imaging settings of tasks C
   and I, chosen so the four-station PSF of a few arcminutes is well
   sampled). FITS written with `core_grid.wcs_header` at the FIELD phase
   direction.

## Quality metrics (frozen)

Per arm, after its solve:

1. **Held-out weighted MSE** on the fixed validation and test cells
   (`losses["validation"]`, `losses["test"]` of the fused pass, the frozen
   definition: mean over cells of the correlation-mean `w|r|²`). Invalid
   predictions make the metric unavailable, never dropped.
2. **Training χ²** `losses["train"]` on the arm's own training cells (the
   section 6 residual definition; equal to the section 6 value for the
   `original` arm only without holdout, see the precondition).
3. **Gain TV**: fixed-support polar-gauge TV against the `original` arm's
   edge support at the `original` arm's scale (the training objective), raw
   TV, time and frequency components, valid-gain fraction, converged
   fraction, median diagonal and off-diagonal gain amplitude.
4. **Dirty image**: peak within the central 9 × 9 pixels (the calibrator at
   the phase centre, Jy/beam), the imaging weight sum and gridded count,
   the PSF's largest sidelobe outside the central 9 × 9, the RMS outside
   the central 64 × 64 box, and the **point-source residual RMS**: RMS over
   the whole image of `dirty − peak × PSF` (PSF unity at the centre). With
   six baselines the dirty image is sidelobe-dominated and the PSF differs
   between arms through the flags, so the residual RMS, not the off-source
   RMS, is the calibration-quality indicator; both are reported. Flux
   recovery = peak / mean Stokes I of MODEL_DATA over the imaged cells.
5. **Flagged fraction**: fraction of all 192 × 2048 × 4 cells flagged in
   the arm's final flags, additions as a count and as a fraction of
   training cells, and for the Tricolour arms the port's window flag
   fraction and per-step fractions.

## Cost metrics (frozen, measured)

Wall time and peak RSS (`resource.getrusage` after each stage; the whole
process under `/usr/bin/time -v`) for: fetch (against task G's 74.5 s,
751.8 MB, 2,124 requests), decode, split, each solve (against QuartiCal's
archived 27.5 s cold / about 3 s warm for the same cells, and the core's
0.62 s in section 6), each Tricolour strategy (against task D's 4.16 s CPU
for the port and 1.19 s warm Numba plus 74 s compilation for Tricolour on
140 rows × 4096 channels), TV and the nine masks, each inversion (against
task I's 4.0 s per job on an idle machine and WSClean's 1.4–1.7 s), and the
whole campaign. "Comparable cost" for the hypothesis below means the
TV-policy chain (reference solve, scores, TV, nine candidate solves) takes at
most three times the wall of the `tricolour-firstpass` port on the same
slice; otherwise the cost clause fails and is recorded.

## Precondition: comparators on archive versus host (run before the campaign)

Before the campaign runs, in `outputs/core-k-<date>-00-precondition`, the
section 6 pass (`examples/prototype_section6.ingest` and `section6_pass`,
unedited) is run on the archived local tiles and must reproduce:

- gain flags identical to QuartiCal's archived `gain_flags.npy`, baseline
  gain products within 1e-6 of the archived `gains.npy`
  (`results/meerkat-luno-solved.json` hashes), as section 6 criteria 1–2;
- χ² within 1e-9 of 0.26823507037914956 (`results/core-section6.json`);
- rank survey 389 / 43 / 592 / 0 with statuses 389 × 0 and 43 × 3;
- the nine policy-mask SHA256 and counts of section 6 run `-02`;
- converged fraction 0.9833234067897558 and flagged-gain fraction
  0.590087890625 of `results/meerkat-luno-solved.json`, equal to 1e-12.

If the precondition fails, the campaign does not run and the failure is
recorded here.

## Acceptance criteria (frozen)

Gated:

1. **Fetch integrity.** Every ranged response is `206` with the requested
   `Content-Range` over the archived size and every whole object `200`
   with the archived size (task G criterion 1); every fetched span and
   object is hash-equal to the same bytes of the archived tiles and
   objects (G criterion 2); the decoded 192 × 2048 × 4 arrays and the four
   row arrays equal `core_zarr.read_rows` on the archived tiles exactly; the
   extra objects equal their archived receipt hashes. Bytes at most
   770,000,000 and requests at most 2,230 (G's limits plus the extra
   objects). Wall time reported against 74.5 s, not gated.
2. **Flags preserved.** For every arm and candidate, final flags ⊇
   original flags cell for cell, `FLAG_ROW` identical, `assert_preserved`
   passes; held-out cells carry no addition; no file under the archived
   inputs (`outputs/luno-support-20261029-01`, `outputs/luno-solve-20261029-02`,
   `outputs/core-g-20261029-01`, `outputs/core-section6-20261029-02`,
   `outputs/caracal-strategy-inputs-8f7bb363`) changes size or mtime; the
   campaign writes only into its own `outputs/core-k-<date>-NN`.
3. **Reference reproduction on the fetched bytes.** The section 6 pass on
   the fetched-and-decoded arrays gives gains, χ², survey and mask hashes
   identical to the precondition's (the arrays are equal, so this must
   hold; a difference means a decode fault).
4. **Every arm solves.** Each arm and candidate solve returns with
   converged fraction at least 0.9, finite gains on every supported bin,
   and validation and test losses available (zero invalid predictions);
   an arm that fails this is reported as unavailable with its numbers, not
   dropped, and the hypothesis is then undecidable for it.
5. **Tricolour arms are well formed.** The port's flags are a superset of
   its input flags, uniform across the four correlations, and the per-step
   window fractions are non-decreasing across the `or`-accumulated steps.
6. **Hypothesis, decided by a pre-registered rule.** For each of the pairs
   (`tv-policy`, `tricolour-firstpass`), (`tv-policy`, `original`) and
   (`tricolour-firstpass+tv`, `tricolour-firstpass`), on the fixed test
   cells: *better* if `MSE_test(candidate) ≤ 0.99 MSE_test(reference)`,
   *worse* if `≥ 1.01`, *null* otherwise; the same three-way call on the
   point-source residual RMS, reported beside it. The headline is the
   first pair's MSE_test call together with the cost clause. Validation
   MSE is used only inside the selection objective, never for this call.
   A `tv-policy` arm that selects no candidate is the `original` arm and
   is reported as "no change selected" (a null result).
7. **Outputs and receipts.** The run directory holds `result.json`,
   `receipt.json` (every fetched object's SHA256 and response headers, the
   code and library SHA256, settings, seed, strategy hashes),
   `environment.json` from `rangtoy.core_cli.environment`,
   `side-effects.json`, `candidates.json`, `flags/<arm>.npz` (additions
   only, compressed), `gains/<arm>.npz`, `images/<arm>-{dirty,psf}.fits`.
   The archive `results/core-k-luno-campaign.json` carries numbers, flag
   fractions, hashes and the hypothesis calls, no visibilities and no
   arrays larger than the nine candidate summaries.
8. `bash tools/check-all.sh` passes on the branch.

Reported, not gated: every cost number, the nine candidates, the unguided
best, the image metrics beyond the residual RMS, and 1830−211's absence.

The campaign is run once as frozen. A failure is recorded here with its
numbers; any later step is labelled post-hoc with its own run directory.
Deterministic throughout: the core is deterministic, the split uses seed
7, and no other randomness exists.

## Expected outcome, stated before running

A null result is the likely outcome and is acceptable. Reasons: on the
fixture the frozen policy selected no additional flags in every pilot and
the Tricolour controls did not improve the objective
([flagging-caracal.md](flagging-caracal.md)); the LUNO slice already
carries processed flags on about 70 % of its cells (the RFI bands are
masked), the section 6 χ² of 0.27 shows a model that fits the processed
weights well, and four stations give a solve with little redundancy for a
MAD score to work with. What would count as a positive result is defined
in criterion 6 and nowhere else. A `tv-policy` arm that returns the
`original` arm is a measured null, not a failure.

## Code to write after this commit (own files only)

`python/rangtoy/core_campaign.py` (fetch of the extra objects, eligibility
and split, arms, gain application, image metrics, decision rule, receipts),
`examples/run_luno_campaign.py` (the frozen run), `examples/check_luno_campaign.py`
(criteria 1–7 against the archive and the precondition),
`examples/precondition_luno_campaign.py`, `examples/archive_luno_campaign.py`,
`tests/test_core_campaign.py` (offline, synthetic). No Rust is needed: every
kernel exists. No shared file is edited. A Stimela recipe
`recipes/core-k-*.yaml` is **not** added on this branch: task H's static
test hard-codes the list of `recipes/core-*.yaml` files and requires their
cabs to call `rangtoy.core_cli`, so a recipe needs edits to
`tests/test_core_cli.py` and `core_cli.py`; the cab lines are listed under
"For the coordinator" instead, as task I did.

## Timings (every tool run of this task)

| When | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-30 | `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI, maturin backend builds `rangtoy._core`) | 9.0 s | – | uv cache warm |
| 2026-10-30 | `cargo +1.93 build --release` core and root, `CARGO_BUILD_JOBS=8` | 3.3 s | – | |
| 2026-10-30 | `pytest tests/test_core_campaign.py` (7 tests), three times while writing | 0.1–1.5 s | – | the first run failed on `cargo` missing from `PATH` (the root crate's TV kernel builds on demand); passes with `~/.cargo/bin` on `PATH` as check-all sets it |
| 2026-10-30 | labelled smoke of the chain on the archived local objects, no network (`outputs/core-k-20261030-00-smoke`, scratch script) | 13.2 s | 391 MB | found the UVW chunk key (`0.0`, not `0`) and a `protected_flags` broadcast shape; both fixed before the freeze of the code commit `50cb137`; one Tricolour arm, one TV loop, two images |
| 2026-10-30 | **precondition**, `examples/precondition_luno_campaign.py` (`outputs/core-k-20261030-00-precondition`) | 3.6 s | 147 MB | all eight checks pass |
| 2026-10-30 | **frozen run `-01`**, `examples/run_luno_campaign.py` under `/usr/bin/time -v` (`outputs/core-k-20261030-01`), started 04:09:05 UTC, load 0.7 | 110.4 s (107.5 s inside Python) | 461 MB | fetch 75.7 s of it; stage times below |
| 2026-10-30 | `examples/check_luno_campaign.py`, first call | 0.6 s | 54 MB | **failed in the checker, not the run**: the checker looked for `MAIN/MAIN_1/UVW/.zarray` in the support slice; post-hoc fix of the archive-path lookup (checker only; the run's bytes and results are untouched) |
| 2026-10-30 | `examples/check_luno_campaign.py`, after the fix (`outputs/core-k-check-20261030-01`) | 1.3 s | 121 MB | criteria 1–7 pass |
| 2026-10-30 | `examples/archive_luno_campaign.py` | 0.1 s | – | 43 KB archive |
| 2026-10-30 | `bash tools/check-all.sh`, once before the final commit (`outputs/core-k-20261030-01.check-all.log`) | 96.6 s (pytest 739 passed in 74.3 s) | 1.68 GB | overall PASS; machine otherwise idle |

Stage times inside the frozen run (`result.json` `stages`; peak RSS is the
process high-water mark after the stage):

| Stage | Wall | Peak RSS so far | Against |
| --- | ---: | ---: | --- |
| fetch (2,124 ranged/whole requests + 17 extra objects) | 75.7 s (74.2 s for the slice, 1.5 s for the extras) | 75 MB | task G 74.5 s, 751.8 MB; whole tiles 679 s |
| decode (2048 blocks, 751.6 MB, Rust) | 0.36 s | 110 MB | task G 0.74 s |
| section 6 reference pass | 1.23 s | 172 MB | section 6 1.67 s |
| split (seed 7) | 0.04 s | 172 MB | |
| solve `original` | 0.32 s | 172 MB | QuartiCal 27.5 s cold / about 3 s warm; section 6 0.62 s |
| Tricolour first-pass port (12 steps) | 1.55 s | 172 MB | task D 4.16 s CPU on 140 × 4096; Tricolour 1.19 s warm + 74 s JIT |
| Tricolour mild port (10 steps) | 0.89 s | 182 MB | |
| each further solve (five) | 0.31–0.33 s | | |
| TV loop (scores, TV, 6 distinct candidate solves) | 1.68 s | 293 MB | |
| TV loop on the first-pass arm | 1.67 s | 323 MB | |
| each inversion (six arms) | 3.87–3.96 s | 461 MB | task I 3.96–4.09 s; WSClean 1.4–1.7 s |

## Measured result (2026-10-30, provisional)

**Precondition** (`outputs/core-k-20261030-00-precondition`, 3.6 s): the
unedited section 6 pass on the archived local tiles reproduces QuartiCal's
gain flags exactly, the baseline gain products to 5.6e-16, χ² =
0.26823507037914956 (equal to the archive), the survey 389 / 43 / 592 / 0
with statuses 389 × 0 and 43 × 3, the nine policy-mask hashes and counts of
section 6 run `-02` (whose `result.json` hashes to the archive's
`result_sha256`), the converged fraction 0.9833234067897558 and the
flagged-gain fraction 0.590087890625 of `meerkat-luno-solved.json`; the
QuartiCal arrays on disk hash to the archive. All eight checks pass, so the
campaign ran.

**Frozen run `-01`** (`outputs/core-k-20261030-01`; receipts `result.json`,
`receipt.json`, `candidates.json`, `environment.json`, `side-effects.json`;
725 MB of fetched bytes under `fetch/`, 13 MB of FITS under `images/`;
checked in `outputs/core-k-check-20261030-01`): **criteria 1–7 pass as
frozen.**

| Criterion | Measured | Result |
| --- | --- | --- |
| 1 fetch integrity | 2,124 + 17 requests, 2,141 attempts (no retry), 752,794,333 bytes, 74.2 s for the slice; every ranged response `206` with the requested `Content-Range`, every whole object `200`; every span and object hash-equal to the archived tiles and receipt lines; the eight decoded arrays equal `read_rows` on the archived tiles | **pass** (≤ 770 MB, ≤ 2,230 requests) |
| 2 flags preserved | six arms: final flags ⊇ original, `FLAG_ROW` identical, no held-out cell flagged; 5,151 archived input files unchanged; `git status` unchanged | **pass** |
| 3 reference on fetched bytes | gains, gain flags, χ², survey, mask hashes and counts identical to the precondition | **pass** |
| 4 every arm solves | converged fraction 0.98332 in all six arms (the same 50-iteration cap as QuartiCal), 41.0 % valid gains (the supported station-bins), zero invalid predictions | **pass** |
| 5 Tricolour arms well formed | both strategies: superset of the input, uniform over correlations, monotone across `or` steps | **pass** |
| 6 hypothesis | all three pairs decidable: **null** on MSE_test and on the residual RMS | **pass** (decidable); outcome null |
| 7 outputs | all required files present; `environment.json` records Python 3.14.4, the `extension` backend, 19 distributions, no QuartiCal | **pass** |

**The arms.** 192 rows × 2048 channels × 4 correlations; 70.10 % of cells
carry an original (processed) flag; 117,556 eligible cells split into
94,047 training, 11,742 validation and 11,767 test cells (seed 7, two
reserved per baseline and gain bin).

| Arm | Additions (train cells) | Final flag fraction | MSE_val | MSE_test | χ²_train | Fixed-support TV vs `original` | Dirty peak (Jy/beam) | Flux recovery | Residual RMS (Jy/beam) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `original` | 0 | 0.701040 | 0.2752889 | 0.2760093 | 0.2674104 | 0.0187946 | 14.92457 | 0.998959 | 0.071221 |
| `tricolour-firstpass` | 128 (0.136 %) | 0.701365 | 0.2752978 | 0.2760261 | 0.2674314 | 0.0187511 | 14.92458 | 0.998951 | 0.071224 |
| `tricolour-mild` | 10 | 0.701065 | 0.2752807 | 0.2760092 | 0.2674112 | 0.0187970 | 14.92457 | 0.998959 | 0.071221 |
| `tv-policy` (= `original`, no change selected) | 0 | 0.701040 | 0.2752889 | 0.2760093 | 0.2674104 | 0.0187946 | 14.92457 | 0.998959 | 0.071221 |
| `tv-unguided-best` (τ 3, α 0; reported) | 9 | 0.701063 | 0.2752956 | 0.2760102 | 0.2674121 | 0.0188022 | 14.92459 | 0.998960 | 0.071223 |
| `tricolour-firstpass+tv` (= first-pass, no change selected) | 128 | 0.701365 | 0.2752978 | 0.2760261 | 0.2674314 | 0.0187511 | 14.92458 | 0.998951 | 0.071224 |

Every arm has median diagonal gain amplitude 0.788 and off-diagonal 0.006;
the raw TV is 0.01698 (`original`) to 0.01691 (first pass). The model
Stokes I over the imaged cells is 14.940 Jy. The imaging weight sums,
gridded counts (117,556 down to 117,428 cells) and PSFs are in the archive.

**Hypothesis calls (pre-registered rule, ±1 % band on the fixed test cells).**

| Pair | MSE_test ratio | Call | Residual RMS ratio | Call |
| --- | ---: | --- | ---: | --- |
| `tv-policy` vs `tricolour-firstpass` (headline) | 0.99994 | **null** | 0.99996 | **null** |
| `tv-policy` vs `original` | 1.00000 | null | 1.00000 | null |
| `tricolour-firstpass+tv` vs `tricolour-firstpass` | 1.00000 | null | 1.00000 | null |

**Cost clause:** the TV chain (reference solve 0.32 s plus scores, TV and
six distinct candidate solves, 1.68 s) took 2.00 s against 1.54 s for the
Tricolour first-pass port on the same slice, ratio 1.30, inside the frozen
factor of three: **comparable**. Neither arm is cheaper by a material
margin, so the second AGENTS.md route (same quality, much lower cost) is not
claimed either.

**What the candidates did.** In the `tv-policy` loop the two α = 0 masks
at τ 8 and 5 are empty (duplicates of no-change); τ 3 proposes 9 cells, the
guided masks 31, 207, 398 and 515 cells (the 515-cell mask is the α = 1,
τ 3 and both α = 3, τ ≤ 5 proposals, the set of all cells with z ≥ 2 and
score above threshold). Every candidate *raises* the fixed-support TV
(0.018802–0.019046 against 0.018795) and the validation MSE (by 2e-5 to
8e-4 relative), so every objective exceeds the baseline's 1.25
(1.25060–1.27454) and none is accepted. Seeded from the first-pass arm the
picture is the same (masks of 9–516 cells, objectives 1.25060–1.27471,
none accepted). The unguided best (τ 3, 9 cells) is also worse than
no-change. All nineteen records are in `candidates.json` and the archive.

**What this shows.** On the real LUNO 1934−638 four-station slice, run
entirely on the core from the public bucket to dirty images in 110 s
(75 s of which is the transfer), gain-TV-guided flagging does not change
calibration or imaging quality relative to the CARACAL first-pass flags: it
selects nothing, and the first-pass strategy itself adds only 128 training
cells (0.14 %) to a slice whose processing already flagged 70 % of cells,
moving the held-out MSE by 6e-5 relative and the point-source residual RMS
by 4e-5. This is the null result the protocol expected, now measured on
real data with a matched comparator and cost. It is also the first
end-to-end science run of the core on real MeerKAT data, with no
Measurement Set, container, QuartiCal, Tricolour or WSClean in the loop.

**What it does not show.** The licence is unconfirmed, so nothing here may
be published or redistributed yet. Four stations give six baselines: the
PSF's largest value outside the central 9 × 9 pixels is 0.998 (the main
lobe is wider than the frozen box; outside the 64-pixel off-source box it
is 0.936), so the dirty-image metrics are sidelobe-dominated and only the
point-source residual RMS is interpretable, and that moved by 4e-5. The
weights are a QuartiCal product and the model has no logged origin, so the
absolute χ² (0.267) and MSE values are conditional. The processed input
flags leave the frozen policy little to find: 70 % of cells are flagged
before it starts, and the MAD score proposes at most 515 of 94,047 training
cells. A whole-array run, a run on the native flags once the observer's
full-resolution data arrive, and PKS 1830−211 with a model decision are the
follow-ups; none of them is started here.

**Post-hoc steps, labelled.** One: the checker's archive-path lookup
(`core_campaign.check`) was fixed after it failed on `MAIN/MAIN_1/UVW/.zarray`
on its first call; the run, its receipts and its bytes were not touched,
and the empty first check directory was removed before the check was
repeated into `outputs/core-k-check-20261030-01`. The labelled smoke before
the code commit found two bugs (the UVW chunk key and a broadcast shape);
both were fixed before the frozen run and are recorded in the timings.

**Checks.** `ruff check` and `ruff format --check` on the new files and
`tests/test_core_campaign.py` (7 tests) pass; `bash tools/check-all.sh` was
run once before the final commit: overall PASS, 739 pytest tests in 74.3 s,
96.6 s in all (log `outputs/core-k-20261030-01.check-all.log`).

## For the coordinator

- Shared files: none edited. `core/` is unchanged; no `pub mod` line is
  needed. Added files only: `python/rangtoy/core_campaign.py`,
  `examples/{run,check,precondition,archive}_luno_campaign.py`,
  `tests/test_core_campaign.py`, this report and
  `research/results/core-k-luno-campaign.json`.
- `python/rangtoy/core_cli.py` (not edited): to expose the campaign as
  `rang-core campaign`, add a subparser `campaign` with `run_dir`,
  `--precondition`, `--workers` delegating to `rangtoy.core_campaign.run`
  followed by `environment(run_dir)`, and `COMPARATORS["campaign"] =
  "check_luno_campaign.py"` (arguments `run precondition check`). A recipe
  `recipes/core-k-luno-campaign.yaml` would then have the steps
  `precondition` (`rangtoy.core_campaign.precondition`, input `out_dir`),
  `campaign` (`run_dir`, `bucket`, `workers`, `precondition_dir`),
  `environment` and `check` (`run_dir`, `precondition_dir`, `check_dir`);
  `tests/test_core_cli.py` would need the new file in its hard-coded list
  and an exception for cabs calling `rangtoy.core_campaign`, as task I's
  `core-imaging.yaml` has. Stimela needs the 3.13 venv (task I).
- `README.md`: a line that the first real-data campaign on LUNO ran on the
  core (`rangtoy.core_campaign`, `research/core-k-luno-campaign.md`) with a
  null result, provisional under the open licence.
- `STATE.md`, new top entry: "Core task K (wave 2), 2026-10-30
  (implemented; measured; provisional). The first real-data campaign on the
  LUNO PKS 1934−638 four-station slice ran entirely on the core: range fetch
  (752.8 MB, 74.2 s), Rust decode, the frozen seed-7 split, six arms solved
  with the core's QuartiCal port (0.32 s each), the Tricolour first-pass and
  mild strategies ported in task D (1.55 s and 0.89 s), the frozen TV
  policy loop (1.7 s) and corrected-data Briggs dirty images (3.9 s each);
  110 s and 461 MB in all, criteria 1–7 pass as frozen. Outcome: a null
  result by the pre-registered rule: the TV policy selects no flag (every
  candidate raises the fixed-support TV and the validation MSE), the
  first-pass strategy adds 128 of 94,047 training cells and moves the
  held-out test MSE by 6e-5 relative and the point-source residual RMS by
  4e-5; cost comparable (ratio 1.30). Provisional: SARAO's written licence
  confirmation is pending (observer permission in chat 2026-10-29 15:36
  SAST), no visibilities are redistributed. Archive
  `results/core-k-luno-campaign.json` (`core-k-luno-campaign.md`). Next: a
  whole-array run and the native-flag run once the observer's data arrive;
  1830−211 needs a model decision."
- `tool-timings.md`: the rows of the timings table above and the stage
  table (fetch, decode, solve, Tricolour port, TV loop, inversion).
- `core-parallel-plan.md`: task K done (null result, provisional);
  `flagging-luno-candidate.md` "Still open": add that the campaign ran and
  that its results wait on the licence confirmation.
- `upstream-notes.md` (observed, not raised): (1) the four-station LUNO
  solve reaches the 50-iteration cap with 98.3 % of intervals converged in
  QuartiCal and in the port alike, on real data as on the fixture; a
  convergence-criterion note for QuartiCal's `complex` term on sparse
  arrays may be worth raising once more data are solved. (2) The CARACAL
  first-pass strategy on a 2048-channel sub-band flags 166 new cells of a
  slice that is already 70 % flagged: the `uvcontsub_flagger` step drops the
  running flags to 39 % (as designed, `or_original_from_cycle: 1`) and the
  static masks and SumThreshold rebuild them to 66 %; the final
  `combine_with_input_flags` restores the input. Nothing wrong, but the
  strategy's intermediate state on pre-flagged calibrator data is
  worth knowing when reading its logs.
- Evidence to keep: `outputs/core-k-20261030-00-precondition`,
  `outputs/core-k-20261030-01` (738 MB, of which 725 MB are the fetched
  bytes under `fetch/`; they may be deleted once the archive hashes are
  accepted, as the same bytes are in `core-g-20261029-01`), and
  `outputs/core-k-check-20261030-01`. `outputs/core-k-20261030-00-smoke`
  (labelled smoke, 13 MB of FITS) can be deleted. The worktree venv and
  `core/py/target` are the usual ignored build outputs.
- Lesson for later protocols: a checker that reads archived objects from two
  roots should resolve each key by existence, not by column name; and the
  PSF-sidelobe box should be set from the array's resolution, not copied
  from the 64-station fixture.
