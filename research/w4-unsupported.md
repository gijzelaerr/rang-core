# W4: unsupported data in the rang-core commands

Task W4 of [finish-plan.md](finish-plan.md): `rang-core flag`, `calibrate`,
`apply` and `image` ([w2-commands.md](w2-commands.md), with C4b's apply,
[c4b-apply-ms.md](c4b-apply-ms.md)) must, on data they were not built for,
either work or refuse with a clear message that names the reason. Branch
`fp-w4-unsupported` from main `f6c53a6`. Interface work: no novelty is claimed.

**Status: implemented and measured** (code `1a3fd2e`; frozen run
`/mnt/d/rang/outputs/w4/run-01`, archive
[results/w4-unsupported.json](results/w4-unsupported.json)). **27 of the 28
cases pass as frozen; ws-undefined fails as frozen** on two of its five
steps: its `image` is refused, where the protocol expected it to work, because
gemclean itself stops on such an MS, and so `config check` refuses too
(section 5); 136 of 138 commands as frozen. Every comparison of section 4 holds. Sections 0 to 4 were
committed (`a6fcc80`) before any case ran; before that commit only
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
  entry in `core_config.TASKS`; owner decision 1 in section 8 (the frozen text
  said section 6; the sections after 4 were renumbered when the results were
  added).
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

## 5. Results (frozen run `-01`, code `1a3fd2e`)

`python examples/check_w4_unsupported.py /mnt/d/rang/outputs/w4/run-01` on a
clean tree at `1a3fd2e`; 3,740 s on a shared host (load about 14), 138
commands; gemclean SHA-256 `9e193e53…` (main's release build), strategy
`ce9ac66a…` (as W2). Per case: its configs, one log per command and the
run directories are in `run-01/<case>/`; the MS copies were removed at the
end. The whole record is `run-01/w4.json`; numbers only in
[results/w4-unsupported.json](results/w4-unsupported.json).

| ID | flag | calibrate | apply | image | Verdict |
| --- | --- | --- | --- | --- | --- |
| base | 0 | 0 | 0 | 0 (and before flag) | pass |
| spw-unused | 0, = base | 0, store = base (80 files) | 0, = base | 0, = base | pass |
| spw-two | 2 | 2 | 2 | 2 | pass |
| spw-widths | 2 | 2 | 2 | 2 | pass |
| dd-same-spw | 2 | 2 | 2 | 2 | pass |
| dd-one | 0, = base | 0, gains = base | 0, = base | 2 | pass |
| field-dup | 0, = base | 0, store = base | 0, = base | 2; by id 0, = base | pass |
| field-norow | 2 | 2 | 2 | 2 | pass |
| field-empty | 0, = base; variant 2 | 0, = base; variant 2 | 0, = base | 0, = base; variant 2 | pass |
| field-unknown | – | – | – | 2, 2 | pass |
| scans-none | 2 | 2, and 2 with setjy (no MODEL_DATA, no flag version) | 1 | 2 | pass |
| scans-other | 0 | 2 | 1 | 2 | pass |
| rows-zero | 2 | 2 | 2 | 2 | pass |
| field-flagged | 0 | 1 ("no valid solution") | 1 | 0 | pass |
| autos | 0, cross rows = base | 0, store = base | 0, cross rows = base; 1,664 auto rows, every calibrator auto row changed, finite; the others = DATA | 0, = base | pass |
| no-ws | 0, = base | 0, store = base | 0, = base | 0, = base | pass |
| ws-undefined | 0, = base | 0, store = base | 0, = base | **2 (expected 0)** | **fail** (two steps: `image`, and `config check`, refused for image's reason) |
| no-weight | 0, = base | 0, store = base | 0, = base | 0, = base | pass |
| no-weights | 0, = base | 2; `uniform` 0 | 0 | 2 | pass |
| no-sigma | 0, = base | 0, store = base | 0, = base | 0, = base | pass |
| uniform-image | – | – | – | 2, naming W4 | pass |
| no-flag-row | 2 | 2 | 2 | 2 | pass |
| no-flag | 2 | 2 | 2 | 2 | pass |
| corr-2 | 0, = the port's call | 2 | 2 | 0 (before flag), = base | pass |
| corr-circ | 2 | 2 | 2 | 2 | pass |
| corr-circ-2 | 2 | 2 | 2 | 2 | pass |
| corr-1 | 2 | 2 | 2 | 2 | pass |
| corr-order | 2 | 2 | 2 | 2 | pass |

Exit codes: 0 works, 1 fails, 2 refused. "= base": criteria 1 to 4, every
cell, gain, store file or image pixel bit-identical. Every refusal had its
frozen words, left every column's SHA-256, the flag-version list and the
stage's state unchanged, and `config check` refused exactly where a stage did,
with the same words. The messages, as printed (paths shortened to `<ms>`):

- several windows: `flag: <ms> uses 2 data descriptions [0, 1] (spectral
  windows [0, 1]); rang-core reads one: write-back, the solves and gemclean
  take one window and one correlation setup. Split one window out first, for
  example with CASA split or mstransform (spw=...) (unsupported data, task W4:
  research/w4-unsupported.md)`; different widths: `<ms>: DATA cells differ in
  shape or correlations between data descriptions ([(32, 4), (64, 4)], [(9,
  10, 11, 12)]); write-back needs one cell shape. Split one spectral window out
  first, ...`
- dd-one: `image: every row is on DATA_DESC_ID 1; gemclean images data
  description 0 only`.
- field-dup: `image.fields: the name 'SIM-TARGET' is used by field ids [2, 3];
  give the field id (one image per field)`.
- field-norow: `FIELD_ID 4 (960 rows) has no FIELD row (the FIELD table has 4
  rows)`.
- empty selections: `image.fields: field 'EMPTY' has no rows`;
  `calibrate.primary.terms[0].field, data.scans: no rows of fields
  ['J1939-6342'] in scans [4] (the MS has scans [1, ..., 23])`; `image:
  data.scans [4] is set, but gemclean has no scan selection and would image
  every scan of the field; leave data.scans out for image, or split the scans
  out first`.
- rows-zero: `<ms> has no rows`.
- weights: `calibrate: <ms> has no WEIGHT_SPECTRUM or WEIGHT (data.weights:
  as_is reads them); set data.weights: uniform to solve with unit weights`;
  `image: <ms> has no WEIGHT_SPECTRUM or WEIGHT, and gemclean reads them`;
  ws-undefined: `image: <ms> declares WEIGHT_SPECTRUM but row 0 has no cells
  of (64, 4) written; gemclean would read the column anyway (it tests only that
  row 0 can be read). Write it, or remove the column so WEIGHT is used`.
- uniform-image: `data.weights: uniform weights for imaging: gemclean reads the
  MS weights, so WEIGHT_SPECTRUM = 1 would have to be written into the MS (task
  W4: uniform imaging weights: ... an owner decision, ...)`.
- flag columns: `<ms> has no FLAG_ROW column; it is required by the
  Measurement Set definition, every stage reads it and every flag version saves
  it`.
- correlations: `calibrate: correlations XX, YY: the complex term solves and
  applies a full 2x2 Jones matrix and needs four correlations (XX, XY, YX, YY);
  diagonal terms on two correlations are C2a's G term`; `correlations RR, RL,
  LR, LL: circular feeds; rang-core handles MeerKAT's linear feeds only
  (research/meerkat-scope.md)`; `one correlation (XX): the flagger needs
  polarised intensity and Stokes I needs XX and YY`; `correlations in the
  order XX, YY, XY, YX; rang-core needs the order XX, XY, YX, YY`.

Each data refusal names every stage it applies to and ends with `(unsupported
data, task W4: research/w4-unsupported.md)`.

**The failed case, ws-undefined.** Found while writing the code, after the
protocol was frozen and before the run: rang's reader returns a one-element
array for a WEIGHT_SPECTRUM cell that was never written, and gemclean's own
test (a read of row 0 succeeds) takes the column as present. gemclean (main's
release build, run directly with the base's arguments on the case MS,
`run-00-smoke/ws-undefined/gemclean-direct/`) exits 2: `WEIGHT_SPECTRUM: read
of 8 bytes at 26956812 failed: failed to fill whole buffer`. So `image` is
refused, naming the reason, rather than left to fail inside gemclean;
`calibrate` checks the shape of row 0 and uses WEIGHT, and its gains equal the
base's. The case fails as frozen, on two steps: `image` (exit 2, expected 0)
and `config check` (exit 2, expected 0, the same refusal); making `image` work
needs gemclean to test
the cell shape as `calibrate` now does (a one-line change in
`core/src/gemclean/input.rs`, G2's file at present; section 7).

**Smoke run.** `run-00-smoke` (base, rows-zero, autos, ws-undefined, corr-2)
ran on the uncommitted code to debug the harness (1,315 s); its verdicts were
the same as run -01's. It is labelled and not the verdict.

**Post hoc, after run -01: the `image` and `data.scans` rule narrowed.** As
run in -01, `image` was refused whenever `data.scans` was set. A0's E2-A and
E2-B configurations set `data.scans` (`tests/data/w2/e2a.yaml`, `e2b.yaml`),
so imaging would have been refused there even on an MS holding only those
scans. The rule is now: `image` is refused when `data.scans` leaves out a scan
of an imaged field (gemclean would image it too), and runs when every scan of
the field is selected (gemclean then images the same rows). Run
`run-02-posthoc-scans` (scans-none and scans-other only, on the uncommitted
change, 177 s) gave the same verdicts as -01, with the message `image:
data.scans [4] leaves out scans [6, 10, 12, 16, 18, 20] of field
'SIM-TARGET', but gemclean has no scan selection and would image them too;
leave data.scans out for image, or split the scans out first`; a pytest covers
the case that now runs. Labelled post hoc; the -01 verdicts stand as measured.

## 6. What changed (code `1a3fd2e`, and the post-hoc commit after it)

- `python/rang/core_pipeline.py`: `inspect_ms` collects the facts and refuses
  only what no stage can read; `check_data` (new) and `_selection_problems`
  (new, called by `preflight`) give the refusals above, all at once, for the
  stages that will run; `calibrate` leaves autocorrelations out and reads
  WEIGHT_SPECTRUM only when row 0 has its cell shape.
- `python/rang/core_config.py`: `data.weights: uniform` with `image` names
  `W4` (a new `TASKS` entry).
- `python/rang/core_writeback.py`: the different-shapes message gives the
  remedy instead of "task W4".
- Tests: `tests/test_w4_unsupported.py` (23 tests, each row of section 3 on
  W2's synthetic MS, a few seconds; added after the run, two for `rang-core
  run`: a data refusal of `image` (DATA_DESC_ID 1, or `data.scans`) stops
  `run` with flag, calibrate and image before flag saves a version or writes
  FLAG; the harness ran only the single-stage commands and `config check`, so
  `run` is covered by these tests alone); `tests/test_w2_commands.py` (E2-A and E2-B
  now name W4 instead of C4; a two-correlation MS is flagged, and refused only
  by calibrate); `tests/test_w1_writeback.py` (the new message). Harness:
  `examples/check_w4_unsupported.py` (case builders shared with the tests).
- `docs/cli.md` regenerated: unchanged (no option or help text changed).

## 7. Limits and what was not checked

- **Tricolour itself on autocorrelations and two correlations.** `flag` passes
  autocorrelation rows to the port as baselines of their own and forms the
  polarised intensity from XX and YY alone; this equals the port's call, and
  the cross rows' flags equal those without autocorrelations, but Tricolour
  (or CARACal, which flags autocorrelations separately) was not run.
- **QuartiCal's handling of autocorrelations** was not read; the solve leaves
  them out as C2a's does.
- **CASA's apply on autocorrelations**: rang corrects them as every other row
  (`G_p^-1 V G_p^-H`); not compared with CASA here (C4b had none).
- **Undefined cells in other columns** (FLAG, DATA, WEIGHT, SIGMA,
  SIGMA_SPECTRUM): only WEIGHT_SPECTRUM was tested.
- **Several windows** are refused, not looped over; MeerKAT data as delivered
  has one. Data descriptions other than 0 work for flag, calibrate and apply
  (dd-one) but not image.
- **No SIGMA_SPECTRUM** is the base itself (A1 has none); a case with
  SIGMA_SPECTRUM present and SIGMA removed was not built.
- **Windows and macOS**: the run was on Linux; the pytest runs where the
  extension has the table writer (casacure cases skip without casacure).
- **Larger MSs**: `inspect_ms` now reads five row columns in full (about 20
  bytes a row); W3's chunking is untouched.

## 8. Owner decisions

1. **Uniform imaging weights** (`data.weights: uniform` with `image`, used by
   A0 for E2 and E3): either a step that writes WEIGHT_SPECTRUM = 1 into the MS
   as CARACal's `prep.specweights: uniform` does (the original weights are then
   lost unless a copy is kept), or a gemclean option that ignores the MS
   weights (after G2). Refused, naming W4, until decided. Not implemented here:
   the first changes the user's data outside W1's flag backups, the second is
   in gemclean, which G2 is changing now.
2. **gemclean and undefined WEIGHT_SPECTRUM cells**: whether gemclean should
   test row 0's cell shape (as `calibrate` now does) and fall back to WEIGHT
   (what WSClean does here was not checked); then ws-undefined's `image` works
   and its refusal goes.
3. **Autocorrelations in the solve**: left out (provisional, as C2a); the
   alternative is to solve with them, which QuartiCal's reading was not
   checked for.

## 9. Later case (post hoc, E5-39, 2026-11-11)

Added after the frozen run, not part of its protocol or its 28 cases
(research/e5-prereview.md, E5-39). Checked on W2's synthetic MS only, not on A1.

| ID | Case (edit of the copy) | flag | calibrate | apply | image |
| --- | --- | --- | --- | --- | --- |
| telescope-other | OBSERVATION row 0 TELESCOPE_NAME not MeerKAT (ASKAP in the test) | works, with a warning: "is from ASKAP, not MeerKAT", "task W4" | same | same | same |

Not refused, so that LOFAR stays possible (`research/meerkat-scope.md`). The
warning goes to the log of every pipeline command and to `rang-core config
check MS`; `state.json` records `telescope`. An empty OBSERVATION table, or
an empty name, gives no warning. Test:
`tests/test_w2_commands.py::test_data_from_another_telescope_is_warned_about_not_refused`.

## For the coordinator

All text proposed; do not apply until merged.

**`research/README.md`, index line (makes `test_every_note_is_in_the_research_index` pass):**

> [W4, unsupported data](w4-unsupported.md): `rang-core flag`, `calibrate`,
> `apply` and `image` on 28 kinds of data they were not built for (several
> windows and data descriptions, fields and empty selections,
> autocorrelations, missing weight and flag columns, other correlations): each
> works, bit-identical to the plain MS where it should, or is refused before
> anything is written with a message naming the reason.

**`research/STATE.md`, new top entry:**

> W4, 2026-11-06 (implemented and measured; [w4-unsupported.md](w4-unsupported.md)).
> The rang-core commands check the Measurement Set per stage before anything
> is written and report every problem at once, each naming its reason and,
> where there is one, a remedy. On 28 cases built from A1's small MS, 27 pass
> as frozen: several data descriptions in use, circular, single or reordered
> correlations, a FIELD_ID without a FIELD row, no FLAG or FLAG_ROW and an MS
> without rows are refused by every stage; two correlations (XX, YY) are
> flagged (equal to the port's call) and imaged (pixel-identical to the
> four-correlation image) and refused by calibrate and apply; autocorrelations
> are flagged and corrected, left out of the solve, with flags, gains,
> CORRECTED_DATA and image bit-identical to the MS without them; missing
> WEIGHT_SPECTRUM, WEIGHT or SIGMA, an unused window, a field without rows and
> a duplicate field name (imaged by id) change nothing; empty field and scan
> selections are refused before calibrate writes a model (at f6c53a6, by reading the code, MODEL_DATA
> and a flag version were written first). One case fails as frozen: a declared
> WEIGHT_SPECTRUM with no cells written is refused by image, because gemclean
> itself stops on it. `data.weights: uniform` for imaging now names W4 and
> waits for an owner decision. No novelty claim.

**`research/finish-plan.md`:** row W4: `**Done 2026-11-06** ([w4-unsupported.md](w4-unsupported.md)); 27 of 28 cases as frozen, uniform imaging weights an owner decision.` Section 7: add decisions 1 to 3 of section 8. C4b's decision 3 (who owns the uniform-weights refusal) is answered by W4: it now names W4, and E2-A and E2-B wait for W4 instead of C4 (`tests/test_w2_commands.py`). After merge that refusal names a finished task, so the plan needs a row (or G-task) that writes the weights or adds the gemclean option.

**Users will meet this:** `rang-core run` with `image` among `run.stages` and a `data.scans` that leaves out some scan of an imaged field is now refused as a whole (gemclean has no scan selection), where before it imaged every scan silently. A0's E2-A (`scans: [9, 10, 11]`) and E2-B (`[17, 18, 19, 20]`) set `data.scans`: their image stage runs only if the MS given holds no other scan of the target (split first), or once gemclean gains a scan selection.

**Merges.** C2a's, C2b's and C2d's branches change `core_config.refusals` and the E2 expectations in `tests/test_w2_commands.py`; the W4 line there (`"W4"` instead of `"C4"`) must survive the merge. `core_pipeline.inspect_ms` no longer refuses by itself: a branch that calls it and relied on its refusals must call `preflight` (or `check_data`). gemclean's WEIGHT_SPECTRUM test (decision 2) touches `core/src/gemclean/input.rs`, which G2 is changing.

**check-all.** At `1a3fd2e` and on the tree of the final commit (the post-hoc rule, the two `run` tests, this text), `tools/check-all.sh` fails only on `test_every_note_is_in_the_research_index` (pytest 939 and 941 passed, 68 skipped; logs `/mnt/d/rang/outputs/w4/check-all-2-code.log`, `check-all-3-results.log`).

**Not removed:** `/mnt/d/rang/outputs/w4/` (about 80 MB: run-01 and run-00-smoke logs, configs, run directories and images; the MS copies are gone; the drafts and scripts used on the way). It can go after merge. `~/Github/rang/outputs/status/fp-w4.md` can go after merge. The worktree's `.venv`.
