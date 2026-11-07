# W6: imaging inputs left by W4

Task W6 of [finish-plan.md](finish-plan.md), the three imaging inputs [w4-unsupported.md](w4-unsupported.md)
section 8 left open (and finish-plan section 7, item 12): scan selection in `rang-core image`,
`data.weights: uniform` for imaging without writing into the user's MS, and gemclean's fallback to WEIGHT
when WEIGHT_SPECTRUM cells are unwritten. Branch `fp-g6-predict`, after G6 ([g6-predict.md](g6-predict.md)).

Status, 2026-11-07: **implemented and measured; every criterion met on every case, development and held out.** The protocol was committed (`c6ad637`) before the first comparison, and the freeze (`0d5c890`, binary `5fb69682`) was recorded before any held-out case ran. `-scans` gives the images of a CASA split byte for byte. `-unit-weights` gives the images of a WEIGHT_SPECTRUM = 1 copy, without writing the MS. An unwritten WEIGHT_SPECTRUM gives the images of the MS without it. All three are within 3.2e-7 of WSClean 3.7. G2's identity set is byte-identical. No novelty claim.

## 1. What there is

- `rang-core image` refuses `data.scans` that leaves out a scan of an imaged field (gemclean has no scan
  selection), refuses `data.weights: uniform` naming W4, and refuses an MS whose WEIGHT_SPECTRUM is
  declared with row 0 unwritten (`core_pipeline.check_data`).
- gemclean reads WEIGHT_SPECTRUM when the column exists and row 0 can be read. On W4's ws-undefined MS
  that read succeeds and a later read fails ("read of 8 bytes at ... failed").
- WSClean 3.7 has no scan selection (`wsclean --help`: `-interval` selects time steps, not scans).
  It uses WEIGHT_SPECTRUM only when `isDefined(0)` holds, else WEIGHT, with a warning
  (`msproviders/msprovider.cpp`, `OpenWeightSpectrumColumn`, read in the 3.6 source).
- CARACal's `prep.specweights: uniform` writes WEIGHT_SPECTRUM = 1 into the MS, which loses the
  original weights.
- The E2-A and E2-B Measurement Sets are not on disk. Their fetches are an open owner decision
  (A0), so the E2 configurations are checked by validation and by a stand-in run on A1's small MS.

## 2. Design (proposed in this commit)

- **`-scans <list>`** (rang's own gemclean option; WSClean has none): a comma-separated list of scan
  numbers. A row is selected when its SCAN_NUMBER is in the list, as well as by field, data description
  and cross-correlation. The same selection applies to the imaging read and to G6's model write, so
  MODEL_DATA is written only on the selected scans' rows.
- **`-unit-weights`** (rang's own; named apart from `-weight uniform`, which is imaging weighting): every
  correlation's visibility weight is 1 in place of WEIGHT_SPECTRUM or WEIGHT, flags still applied. Stokes
  I then gets WSClean's `min(4 w_XX, 4 w_YY)` = 4. This is what imaging a copy with WEIGHT_SPECTRUM = 1
  gives, and nothing is written. The weight columns are not read, so an MS without them images too.
- **WEIGHT fallback**: WEIGHT_SPECTRUM is used when the column exists and row 0's cell holds
  `nchan × ncorr` values. Otherwise WEIGHT is used, repeated over the channels. This is WSClean's
  `isDefined(0)` rule (an undefined cell reads as no array). It is the test `rang-core calibrate`
  already makes (`core_pipeline._cell_defined`).
- **`rang-core image`**: `data.scans` → `-scans`, with the scans passed to G6's model write;
  `data.weights: uniform` → `-unit-weights`. The three refusals go. A scan selection with no rows of an
  imaged field is refused, as calibrate's is.

## 3. Cases (frozen)

All from A1's small MS (`/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms`: 12,480 rows,
64 channels, fields 0 J1939-6342, 1 3C286-SIM, 2 SIM-GCAL, 3 SIM-TARGET; SIM-TARGET in scans 4, 6, 10,
12, 16, 18, 20; SIM-GCAL in scans 3, 5, 7, 9, 11, 13, 15, 17, 19, 21). Fresh copies under
`/mnt/d/rang/outputs/w6-20261106-NN`. Images: 512², 2″, Briggs 0. The gemclean comparisons run at
`-niter 300`, so all five files are compared. WSClean 3.7 runs at `-niter 0 -make-psf`, with
`-gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I`. These are small runs, so
they use `nice` and 4 threads, without the heavy lock.

| ID | Edit of the copy | Selection | Role |
| --- | --- | --- | --- |
| SC-d | none | field 3, scans 4, 6, 10 | development |
| SC-h1 | none | field 3, scans 12, 16, 20 | **held out** |
| SC-h2 | none | field 2, scans 5, 9, 13, 17 | **held out** |
| U-d | WEIGHT_SPECTRUM uniform in [0.2, 5] (seed 20261181), WEIGHT its channel mean | field 3, all scans | development |
| U-h | as U-d | field 2, all scans | **held out** |
| WU | WEIGHT uniform in [0.2, 5] per row and correlation (seed 20261182); WEIGHT_SPECTRUM removed, then added again (StandardStMan) with no cell written | field 3 | development |
| NW | as WU, WEIGHT_SPECTRUM removed | field 3 | the twin of WU |
| E2 | none | an E2-A-shaped `rang-core image` config: `data.scans: [1, 4, 6]`, `data.weights: uniform`, target SIM-TARGET | **held out** |

Held-out cases run only after the freeze: a commit of `fp-g6-predict` and the SHA-256 of the `gemclean`
binary built from it, both recorded here first.

## 4. Criteria (frozen)

"Byte-identical" means equal SHA-256 for each of the five FITS files (`dirty`, `psf`, `model`,
`residual`, `image`). "B bounds" are G3's criterion B: per image, the largest |gemclean − WSClean| is at
most 1e-5 of WSClean's PSF peak (PSF) and of its largest |dirty| (dirty), and `WSCIMGWG` agrees to 1e-6
relative.

1. **Scans (SC-d, SC-h1, SC-h2).**
   - a. gemclean with `-scans` on the full copy is byte-identical to gemclean on CASA 6.7.6's
     `split(scan=..., datacolumn='data')` of it, with the field id the split gives.
   - b. WSClean on the split, against gemclean with `-scans` on the full copy at `-niter 0`, is within
     the B bounds.
   - c. After the clean, the full copy's MODEL_DATA differs from its pre-filled sentinel only on the
     selected rows (field, scans, cross-correlations).
2. **Unit weights (U-d, U-h).**
   - a. gemclean with `-unit-weights` on U is byte-identical to gemclean on U1, a copy of U with
     WEIGHT_SPECTRUM = 1 and WEIGHT = 1 written by python-casacore.
   - b. At least one file differs from gemclean on U without the option, so the option acts.
   - c. WSClean on U1 is within the B bounds of gemclean with `-unit-weights` on U at `-niter 0`.
   - d. `rang-core image` with `data.weights: uniform` and `image.write_model: false` leaves the SHA-256
     of every column of U unchanged.
3. **Fallback (WU, NW).**
   - a. gemclean on WU is byte-identical to gemclean on NW.
   - b. WSClean on WU is within the B bounds of gemclean on WU at `-niter 0`.
   - c. `rang-core image` on WU works (exit 0) and is byte-identical to `rang-core image` on NW. WU's
     edit is W4's ws-undefined case (`examples/check_w4_unsupported.py`, `undefined_weight_spectrum`).
4. **E2 configurations.**
   - a. `tests/data/w2/e2a.yaml` and `e2b.yaml` no longer wait for W4. E2-A waits only for C5a and G4;
     E2-B only for G9.
   - b. The E2 stand-in run exits 0 and is byte-identical to gemclean on the CASA split (scans 1, 4, 6)
     of a copy with WEIGHT_SPECTRUM = 1 and WEIGHT = 1.
5. **Otherwise byte-identical.** With none of the new options, the final binary run with
   `-no-update-model-required` on G2's identity set gives FITS files with the SHA-256 of G2's stored
   `runs/c34` references (`*.sha256`): S1-S3 and H1-H4 in both forms (the default and `-single
   -wgridder-accuracy 1e-4`), and the 256-channel pilot in the default form, 15 runs. This covers G6's
   changes too.

A failure is reported as measured and not reworded.

## Freeze (recorded before any held-out case ran)

Frozen 2026-11-07 at commit `0d5c890` of `fp-g6-predict`. `gemclean` built from it (profile `gemclean`,
rustc 1.93) has sha256 `5fb696825d9e53032ef7c8ed5c578248f5143f56a86eb4b12ae99057beead287` (copy
`/mnt/d/rang/outputs/w6-20261107-02-held/bin/gemclean-freeze`). Only the development cases had run, with
the release build of the same source (`/mnt/d/rang/outputs/w6-20261106-01-dev`). Criterion 5 runs with
this binary.

## 5. Implementation (code `0d5c890`)

- `core/src/gemclean/input.rs`: `Selection.scans` and `Selection.unit_weights`. `row_mask` reads
  SCAN_NUMBER only when scans are given. The WEIGHT_SPECTRUM test is now "row 0 reads as `nchan × ncorr`
  floats". `read_ms` reads no weight column under unit weights.
- `core/src/bin/gemclean.rs`: `-scans` (comma-separated, at least one) and `-unit-weights`, passed to the
  imaging read and to G6's model write. `scans` and `unit_weights` are added to `-report.json`.
- `python/rang/core_pipeline.py`: `gemclean_arguments(..., scans, unit_weights)`; `stage_image` passes
  `data.scans` and `data.weights` (and the scans to `write_model`). In `check_data`, the scan refusal
  and the ws-undefined refusal are gone, and the no-weights refusal applies only to `as_is`. In
  `_selection_problems`, an imaged field with no cross-correlation rows in `data.scans` is refused.
- `python/rang/core_config.py`: the `data.weights: uniform` imaging refusal and its TASKS entry are removed.
- Tests: `tests/test_w4_unsupported.py` now expects image to work on ws-undefined, to work with uniform
  weights on the MS without weights, and to pass `-unit-weights` and `-scans` without writing the MS. Its
  scan refusals for image now name the field. `tests/test_w2_commands.py`: E2-A waits for C5a and G4,
  E2-B for G9, and `gemclean_arguments` passes the new flags.
- Scripts: [`tools/oracles/w6`](../tools/oracles/w6/) (`run.sh`, `prep.py`, `casa_split.py`,
  `fits_cmp.py`, `rows_check.py`, `rescore.sh`, `identity.sh`).

## 6. Results (measured)

Development `/mnt/d/rang/outputs/w6-20261106-01-dev` (release build of the freeze's source). Held out
`/mnt/d/rang/outputs/w6-20261107-02-held` (frozen binary `5fb69682`). Identity set
`/mnt/d/rang/outputs/w6-20261107-03-identity`. Each has `.code/`, `results.jsonl` or `id/results.txt`,
logs and the images; the MS copies were deleted after scoring.

**Scorer fix (labelled; no criterion changed).** In the development run, `fits_cmp.py` ran under the
system Python, which has no numpy, so the image checks printed nothing. They were scored again on the
same files with the venv's Python (`rescore.sh`; `results-scored.jsonl`); no imager was rerun. `run.sh`
was fixed before the freeze, and the held-out run scored in place.

| Case | Check | Result |
| --- | --- | --- |
| SC-d (dev) | 1a `-scans 4,6,10` vs CASA split | all 5 files byte-identical |
| SC-d | 1b WSClean on the split | PSF 1.2e-7, dirty 3.2e-7, WSCIMGWG 1.7e-8 (bounds 1e-5, 1e-5, 1e-6) |
| SC-d | 1c MODEL_DATA rows written | 2,880 = the selected rows exactly |
| U-d (dev) | 2a `-unit-weights` vs WEIGHT_SPECTRUM = 1 | byte-identical |
| U-d | 2b vs no option | all 5 files differ (the option acts) |
| U-d | 2c WSClean on U1 | PSF 6.0e-8, dirty 3.1e-7, WSCIMGWG 4e-16 |
| U-d | 2d `rang-core image`, uniform | all 23 columns' SHA-256 unchanged |
| WU (dev) | 3a ws-undefined vs WEIGHT_SPECTRUM removed | byte-identical |
| WU | 3b WSClean on WU | PSF 6.0e-8, dirty 3.2e-7, WSCIMGWG 9.8e-12 |
| WU | 3c `rang-core image` on WU and NW | both exit 0, byte-identical |
| SC-h1 (held) | 1a `-scans 12,16,20` | byte-identical |
| SC-h1 | 1b | PSF 1.2e-7, dirty 3.1e-7, WSCIMGWG 3.4e-9 |
| SC-h1 | 1c | 2,880 = selected |
| SC-h2 (held) | 1a field 2, `-scans 5,9,13,17` | byte-identical |
| SC-h2 | 1b | PSF 1.8e-7, dirty 2.2e-7, WSCIMGWG 5.8e-9 |
| SC-h2 | 1c | 960 = selected |
| U-h (held) | 2a, 2b, 2c, 2d | byte-identical; differs without; PSF 1.2e-7, dirty 1.6e-7, WSCIMGWG 0; unchanged |
| E2 (held) | 4b E2-A-shaped `rang-core image` (scans 1, 4, 6, uniform) vs gemclean on the split of the unit-weight copy | exit 0; all 5 files byte-identical |

- **Criterion 1 (scans): met** on SC-d and the held-out SC-h1 and SC-h2.
- **Criterion 2 (unit weights): met** on U-d and the held-out U-h. The MS is not written.
- **Criterion 3 (fallback): met** on WU and NW. `rang-core image` runs on W4's ws-undefined case and
  gives the images of the MS without WEIGHT_SPECTRUM.
- **Criterion 4 (E2 configurations): met.** (a) `test_the_acceptance_configurations_parse_and_wait_for_their_tasks`
  now expects {C5a, G4} for E2-A and {G9} for E2-B, and passes. (b) The stand-in run passes. E2-B
  still cannot image, for G9 (`pol: IQUV`). Its scans and uniform weights are no longer refused.
- **Criterion 5 (otherwise byte-identical): met.** All 15 runs of G2's identity set gave all 5 FITS files with the SHA-256 of G2's `c34` references: S1-S3 and H1-H4 in both forms, and the 256-channel pilot. The runs used the frozen binary and `-no-update-model-required` (`w6-20261107-03-identity/id/results.txt`; peak RSS 1.94-12.24 GB). G6's and W6's changes leave the images of main's options unchanged.**

## 7. What was not checked

- The E2-A and E2-B Measurement Sets themselves (not fetched; an owner decision of A0).
- `-scans` together with `-channels-out` or joined channels (the selection is shared by both paths, but no
  case ran it). Scans of a field across several data descriptions.
- Unit weights with `-weight natural` or `uniform`; only Briggs 0 ran.
- A WEIGHT_SPECTRUM with row 0 defined and later rows undefined (WSClean's rule tests row 0 only, and so
  does gemclean's); such an MS still fails in the read.
- CASA's `split` renumbers fields. The comparison used the new field id, read from the split's FIELD table.

## For the coordinator

- **research/README.md**, index line:
  `- [W6, imaging inputs](w6-imaging-inputs.md): gemclean -scans, -unit-weights and WSClean's WEIGHT fallback; rang-core image takes data.scans and data.weights: uniform without writing the MS; images byte-identical to a CASA split and to a unit-weight copy, within G3's bounds of WSClean.`
- **research/STATE.md**, log, newest first:
  `W6, 2026-11-07 (implemented and measured; [w6-imaging-inputs.md](w6-imaging-inputs.md)). The three imaging inputs W4 left open. gemclean gains -scans (rang's own; WSClean has no scan selection) and -unit-weights (every correlation weighs 1, flags kept; nothing written), and falls back to WEIGHT when row 0 of WEIGHT_SPECTRUM holds no cell, as WSClean's isDefined(0). rang-core image passes data.scans and data.weights: uniform and no longer refuses them or W4's ws-undefined MS. Under a rule written first, on A1's small MS with held-out selections after a freeze: images byte-identical to gemclean on a CASA split of the scans and on a copy with WEIGHT_SPECTRUM = 1, and to the MS without WEIGHT_SPECTRUM; dirty images and PSFs within 3.2e-7 of WSClean 3.7 on the same selection; MODEL_DATA written on the selected scans' rows only; the E2-A-shaped stand-in run equal to its split twin. G2's 15-run identity set byte-identical with the final binary. No novelty claim.`
- **research/finish-plan.md**: row W6 `**Done 2026-11-07** ([w6-imaging-inputs.md](w6-imaging-inputs.md)).`
  Section 7 item 12: decisions 1 and 2 are implemented as provisionally chosen (a gemclean option; the
  fallback). E2-A's image stage waits only for G4 (auto_mask), E2-B's for G9.
- **Merge points:** `core_pipeline.py` (`check_data`'s weight and scan blocks, `_selection_problems`,
  `gemclean_arguments`, `stage_image`), `core_config.py` (the uniform-weights refusal and TASKS entry
  removed), and `tests/test_w4_unsupported.py` and `tests/test_w2_commands.py` (expectations). W3b edits
  `core_pipeline.py` and E0 edits `core_config.py`.
- **Owner decisions:** the names `-scans` and `-unit-weights` are rang's own, and G8's clash check could
  cover them. Unit weights mean per-correlation weight 1 (Stokes I weight 4), as a WEIGHT_SPECTRUM = 1
  copy gives.
