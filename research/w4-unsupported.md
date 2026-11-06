# W4: unsupported data in the rang-core commands

Task W4 of [finish-plan.md](finish-plan.md): `rang-core flag`, `calibrate`,
`apply` and `image` ([w2-commands.md](w2-commands.md), with C4b's apply,
[c4b-apply-ms.md](c4b-apply-ms.md)) must, on data they were not built for,
either work or refuse with a clear message that names the reason. Branch
`fp-w4-unsupported` from main `f6c53a6`. Interface work: no novelty is claimed.

**Status: the case list, the expected behaviour and the criteria below are
proposed and committed before any case is run.** Before this commit only
`probe_a1.py` ran (`/mnt/d/rang/outputs/w4/`), which describes A1's small MS
(columns, fields, scans, weights) and runs no command.

## 0. What the code does today (read at `f6c53a6`)

- `core_pipeline.inspect_ms` refuses, for every command alike: an MS whose data
  descriptions differ in cell shape (`core_writeback.layout`), more than one
  data description in use, and correlations other than XX, XY, YX, YY. Each
  message says "task W4".
- Not refused, and failing during a stage or after a write:
  - **Empty selections.** `stage_calibrate` calls `write_models` before its "no
    rows" check, so with `model.source: setjy` and `data.scans: [99]` MODEL_DATA
    and a flag version are written and then the stage fails. `stage_flag` on an
    empty selection writes FLAG back unchanged and saves two flag versions.
  - **Duplicate FIELD names.** `stage_image` makes `<run>/image/<name>/` per
    field id, so two fields of one name raise `FileExistsError` (a traceback,
    not a refusal).
  - **One data description in use that is not 0.** gemclean has no data
    description option and images DATA_DESC_ID 0 only.
  - **WEIGHT_SPECTRUM declared with undefined cells** (common in real MSs).
    gemclean tests a read of row 0 and falls back to WEIGHT; `calibrate` checks
    the column name only and its `getcol` raises.
  - **No WEIGHT and no WEIGHT_SPECTRUM**, **no FLAG_ROW**, **no FLAG**: raw
    reader exceptions. Flag versions store FLAG and FLAG_ROW
    (`formats/flagversions.py`), gemclean reads FLAG_ROW, the solver takes it.
  - **A FIELD_ID with no FIELD row**: an `IndexError` in `flag`.
  - **Autocorrelations** enter the `complex` solve (`core.solve_complex` does not
    skip p = q rows); gemclean already drops them, as WSClean.
  - **`data.scans` and `image`**: gemclean has no scan selection, so `image`
    silently images every scan of the field.
- `data.weights: uniform` with `image` is refused naming C4, which is done.

## 1. Design (proposed)

- `inspect_ms` collects facts and refuses only what no stage can read: not an
  MS, no rows, no DATA, cells of different shapes. It also reads the row
  columns FIELD_ID, DATA_DESC_ID, SCAN_NUMBER, ANTENNA1 and ANTENNA2 (small)
  and records which of WEIGHT, WEIGHT_SPECTRUM (with a defined row 0, as
  gemclean tests), SIGMA, SIGMA_SPECTRUM, FLAG and FLAG_ROW exist.
- A new `core_pipeline.check_data(config, info, stages)`, called from
  `preflight` (so `rang-core config check CONFIG MS` reports the same), returns
  every problem for the stages that will run, all at once. Each message names
  the stage, what was found, why it is not supported and, where there is one, a
  remedy, and ends with `(unsupported data, research/w4-unsupported.md)`. A
  refusal is exit 2 before anything is written.
- `calibrate` leaves autocorrelation rows out of the solve (C2a's solves do the
  same, [c2a-gain.md](c2a-gain.md) section 3). `apply` corrects autocorrelation
  rows as every other row, as CASA's apply does. `flag` passes them to the
  Tricolour port as baselines of their own.
- `calibrate` reads WEIGHT_SPECTRUM only when row 0 is defined, else WEIGHT, as
  gemclean does, so the two stages use the same weights.
- `data.weights: uniform` for imaging is **not implemented**: it means writing
  WEIGHT_SPECTRUM into the user's MS (CARACal's `prep.specweights: uniform`),
  which W1's flag backups do not cover, or a gemclean option (gemclean is G2's
  to change now). The refusal is renamed to W4 with that reason and a `W4`
  entry in `core_config.TASKS`; owner decision 1 in section 6.
- `tests/test_w2_commands.py::test_unsupported_data_is_refused_naming_w4`
  changes deliberately: a two-correlation MS is no longer refused by
  `inspect_ms`; `flag` and `image` run on it, `calibrate` and `apply` refuse.

## 2. Data

Every case MS is a copy of A1's small MS
(`/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms`: 12,480 rows,
64 channels, XX XY YX YY, 16 antennas, no autocorrelations, fields J1939-6342
(id 0), 3C286-SIM, SIM-GCAL, SIM-TARGET (id 3), WEIGHT and WEIGHT_SPECTRUM
both 1213.15 everywhere, so WEIGHT repeated over channels equals
WEIGHT_SPECTRUM bit for bit; SIGMA, no SIGMA_SPECTRUM; FLAG all false), edited
by `examples/check_w4_unsupported.py` under `/mnt/d/rang/outputs/w4/run-NN/`
with the core writer and casacure (`removecols`, `addcols`). MSs with a
different cell shape are written anew by the core writer from the base's
columns. The edit of each case is in its row of section 3.

Configuration (as W2's run): `fields: {fcal: [J1939-6342], target:
[SIM-TARGET]}`; `flag.strategy` CARACal's
`mk_rfi_flagging_calibrator_fields_firstpass.yaml` (`8f7bb363`); primary term
`{type: complex, solint: int, freqint: 16}`, model `unity`; image 512 × 512 at
2″, Briggs 0, `niter` 2000, `threads` 1, gemclean
`~/Github/rang/core/target/release/gemclean` (SHA-256 recorded). Variants of a
case change one key, named in its row.

Commands per case, each on the case's copy and run directory, in this order
unless the row says otherwise: `config check CONFIG MS` with `--stage` flag,
calibrate, apply, image; then `flag`, `calibrate`, `apply`, `image`. The
light runs are not under the heavy lock (W4 is not heavy); `nice`, one thread.

## 3. Cases and expected behaviour (frozen)

"works": exit 0. "refused": exit 2, the message contains the quoted words,
and the command changed nothing (SHA-256 of every column of the MS and the
list of flag versions equal before and after it, no new state for the stage).
"fails": exit 1 with the quoted words. Twin comparisons are in section 4.
`config check` must refuse exactly when one of the four stages is refused, with
the same words.

| ID | Case (edit of the copy) | flag | calibrate | apply | image |
| --- | --- | --- | --- | --- | --- |
| base | none | works | works | works | works |
| spw-unused | a second SPECTRAL_WINDOW row (32 channels) no data description uses | works = base | works = base | works = base | works = base |
| spw-two | a second window of 64 channels above the first and a second data description; SIM-TARGET's rows on it | refused: "2 data descriptions", "spectral windows [0, 1]", "split" | refused, same | refused, same | refused, same |
| spw-widths | as spw-two, the second window 32 channels | refused: "differ in shape" | refused, same | refused, same | refused, same |
| dd-same-spw | a second data description on window 0; SIM-TARGET's rows on it | refused: "2 data descriptions" | refused, same | refused, same | refused, same |
| dd-one | two data descriptions on window 0; every row on DATA_DESC_ID 1 | works = base (gains) | works = base (gains) | works | refused: "DATA_DESC_ID 1", "gemclean images data description 0" |
| field-dup | SIM-GCAL renamed SIM-TARGET | works = base | works = base | works | refused: "SIM-TARGET", "field ids [2, 3]", "give the field id"; variant `image.fields: [3]` works = base |
| field-norow | SIM-TARGET's scan-20 rows given FIELD_ID 4 (no FIELD row 4) | refused: "FIELD_ID 4", "no FIELD row" | refused, same | refused, same | refused, same |
| field-empty | a fifth FIELD row EMPTY with no rows | works = base | works = base | works | works = base; variants `image.fields: [EMPTY]`, `fields.fcal: [EMPTY]` (calibrate) and `flag.fields: [EMPTY]` refused: "EMPTY", "no rows" |
| field-unknown | none; variants `image.fields: [NOPE]` and `[9]` | – | – | – | refused: "NOPE"; "field id 9" |
| scans-none | none; variant `data.scans: [99]`, and calibrate also with `model.source: setjy` | refused: "scans [99]", "no rows" | refused, same (and no MODEL_DATA written) | fails: "finished calibrate" | refused: "data.scans", "no scan selection" |
| scans-other | none; variant `data.scans: [4]` (a SIM-TARGET scan) | works | refused: "J1939-6342", "scans [4]", "no rows" | fails: "finished calibrate" | refused: "data.scans", "no scan selection" |
| rows-zero | every row removed | refused: "no rows" | refused, same | refused, same | refused, same |
| field-flagged | FLAG true on every J1939-6342 row | works (J1939-6342 stays flagged) | fails: "no valid solution" | fails: "finished calibrate" | works |
| autos | an autocorrelation row per antenna and integration (DATA XX, YY 15 + noise, XY, YX noise; FLAG false; weights 1213.15; UVW 0), appended | works; cross rows = base | works; autos left out, = base | works; cross rows = base; autos corrected | works = base |
| no-ws | WEIGHT_SPECTRUM removed | works = base | works = base (WEIGHT per channel) | works = base | works = base |
| ws-undefined | WEIGHT_SPECTRUM removed and added again as a column with no cells written | works = base | works = base | works = base | works = base |
| no-weight | WEIGHT removed (WEIGHT_SPECTRUM kept) | works = base | works = base | works = base | works = base |
| no-weights | WEIGHT and WEIGHT_SPECTRUM removed | works = base | refused: "WEIGHT_SPECTRUM or WEIGHT", "data.weights: uniform"; variant `data.weights: uniform` works | works (after the variant) | refused: "WEIGHT_SPECTRUM or WEIGHT", "gemclean" |
| no-sigma | SIGMA removed (A1 has no SIGMA_SPECTRUM) | works = base | works = base | works = base | works = base |
| uniform-image | none; variant `data.weights: uniform` | – | – | – | refused: "data.weights", "task W4", "WEIGHT_SPECTRUM" |
| no-flag-row | FLAG_ROW removed | refused: "FLAG_ROW", "required" | refused, same | refused, same | refused, same |
| no-flag | FLAG removed | refused: "FLAG", "required" | refused, same | refused, same | refused, same |
| corr-2 | written anew with XX and YY only (base's correlations 0 and 3, CORR_TYPE [9, 12]) | works = the port's call | refused: "XX, YY", "four correlations" | refused, same | works = base (image before flag, against base's image before flag) |
| corr-circ | CORR_TYPE relabelled RR, RL, LR, LL | refused: "circular", "linear" | refused, same | refused, same | refused, same |
| corr-circ-2 | corr-2 relabelled RR, LL | refused: "circular", "linear" | refused, same | refused, same | refused, same |
| corr-1 | written anew with XX only | refused: "one correlation" | refused, same | refused, same | refused, same |
| corr-order | CORR_TYPE relabelled XX, YY, XY, YX | refused: "order", "XX, XY, YX, YY" | refused, same | refused, same | refused, same |

Notes on the expectations:

- `flag` reads no weights, so it works on every weights case. It works on two
  linear correlations because the port forms Tricolour's polarised intensity
  from the correlations it finds (Q from XX and YY, as `polarised_map`); on one
  correlation there is no polarised intensity, so it refuses.
- Circular feeds are outside the scope ([meerkat-scope.md](meerkat-scope.md):
  MeerKAT has linear feeds), although gemclean could image RR and LL.
- Several windows in use are refused rather than looped over: write-back needs
  one cell shape, gemclean images one data description, and the solve groups
  have one CHAN_FREQ. The remedy given is CASA `split` or `mstransform` with
  one `spw`.

## 4. Criteria (frozen)

Pass: every cell of section 3 as written, plus these comparisons. A failure is
reported as measured and not reworded.

1. **"= base" for flag**: FLAG of the case equals the base's FLAG on the rows
   the two share (for autos: the cross rows), every cell.
2. **"= base" for calibrate**: every partition's gains and gain flags
   bit-identical to the base's (read with `quartical_store`); for spw-unused,
   field-dup, field-empty, autos and the weights cases also every file of the
   store byte-identical. dd-one: gains and flags only (its partitions carry
   DATA_DESC_ID 1).
3. **"= base" for apply**: CORRECTED_DATA and FLAG bit-identical to the base's
   on shared rows. autos: the autocorrelation rows' CORRECTED_DATA is finite and
   differs from their DATA wherever the gains are valid.
4. **"= base" for image**: the pixel arrays of `image-image.fits`,
   `image-model.fits`, `image-residual.fits` and `image-dirty.fits` (those that
   exist) bit-identical to the base's (headers not compared).
5. **corr-2 flag = the port's call**: `core_flag.flag_rows` per field, data
   description and scan group on arrays read with casacure from a pristine
   copy, as W2 criterion 2, every cell.
6. **scans-none with setjy**: no MODEL_DATA column and no flag version exist
   after the refusal.
7. **Pytest**: each row of section 3 has a case in
   `tests/test_w4_unsupported.py` on W2's synthetic MS (`make_ms`, 240 rows),
   with a fake gemclean where `image` runs; the image comparisons (criterion
   4) are only in the run.

Reported, not gated: wall time per command (shared host; not a timing
measurement).

## 5. Results

Not yet run.

## 6. Owner decisions

1. **Uniform imaging weights** (`data.weights: uniform` with `image`, used by
   A0 for E2 and E3): either a step that writes WEIGHT_SPECTRUM = 1 into the MS
   as CARACal's `prep.specweights: uniform` does (the original weights are then
   lost unless a copy is kept), or a gemclean option that ignores the MS
   weights (after G2). Refused, naming W4, until decided.

## For the coordinator

To be written with the results.
