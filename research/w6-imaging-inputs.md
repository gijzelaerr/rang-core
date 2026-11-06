# W6: imaging inputs left by W4

Task W6 of [finish-plan.md](finish-plan.md), the three imaging inputs [w4-unsupported.md](w4-unsupported.md)
section 8 left open (and finish-plan section 7, item 12): scan selection in `rang-core image`,
`data.weights: uniform` for imaging without writing into the user's MS, and gemclean's fallback to WEIGHT
when WEIGHT_SPECTRUM cells are unwritten. Branch `fp-g6-predict`, after G6 ([g6-predict.md](g6-predict.md)).

Status: **protocol frozen (this commit), nothing compared yet.**

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

Frozen 2026-11-07 at commit  of .  built from it (profile ,
rustc 1.93) has sha256  (copy
). Only the development cases had run, with
the release build of the same source (). Criterion 5 runs with
this binary.
