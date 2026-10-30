# Rang core, wave 2 task K: the first real-data campaign on LUNO

Protocol frozen 2026-10-30 on branch `core/k-luno-campaign` (from origin/main
`d6a0916`), before any campaign code was written. Status: **protocol
frozen; not yet run.** Task K of
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

## Measured result

Not yet run.

## For the coordinator

To be filled after the run.
