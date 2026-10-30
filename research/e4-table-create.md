# Rang core, task E4: casacore table creation

Task E4 of [big-plan.md](big-plan.md): new casacore tables written by the
core's own table writer (E3, [e3-table-writer.md](e3-table-writer.md)),
rows added and removed, string arrays, `default_ms` with its subtables and
CASA calibration tables (G, B, K, Df) with `table.info`, every one
byte-compared against casacore 3.8.1 (python-casacore in the pinned
`rang-ms-reader:local` image) or against CASA 6.7.6's own tables
(`rang-o-casa:6.7.6.14`, [o-casa.md](o-casa.md)). Branch `e4-table-create`
from `3b875e0`. Protocol frozen 2026-10-30 in the commit that adds this
file, before any E4 code. Before freezing, two scratch measurements were
made (the determinism inventory and the CASA deep-copy check below);
nothing else was measured.
Status: **implemented and measured (frozen check `outputs/e4-20261030-01`):
all eight criteria pass.** 18 casacore cases (new tables, rows added and
removed, string arrays, `default_ms`) and CASA's own K, G, B and Df tables
are byte-identical to casacore 3.8.1 / CASA 6.7.6, the alignment gaps of
`table.fNi` (E3's exception, masked by the frozen rule) excepted in 7 of 22;
CASA `applycal` with the core's copies gives bit-identical CORRECTED_DATA
and FLAG, and a core-made G table applies to 4.3e-7 relative. Archive:
[results/e4-table-create.json](results/e4-table-create.json).

The user's decision (2026-10-30) stands: the core reads and writes every
format of the tools it replaces ([ecosystem-survey.md](ecosystem-survey.md)
section 5.3). A reimplementation of a file format is not a scientific
contribution (AGENTS.md); no archived result changes because of it.

## Scope

In scope (E4), little-endian tables as casacore 3.8.1 writes them:

1. **New tables from a description**: `table.dat` (E3's `TableDat`),
   `table.info`, `table.lock` with casacore's write lock and sync record,
   StandardStMan (`SsmW::create`, bucket sizing as `setBucketSize`, SPEC
   `BUCKETSIZE`/`BUCKETROWS`/`PERSCACHESIZE`), TiledColumnStMan and
   TiledShapeStMan (FixedShape columns; the tiled header model of E3),
   table and column keywords (including table-valued keywords, the
   subtable links `Table: ...`, stored as `././NAME`), and cells left
   undefined (an indirect array never put has offset 0).
2. **Adding and removing rows**, on new tables and on existing managers:
   `addRow64` of StandardStMan (`SSMIndex::addRow` on an existing index,
   new buckets, the columns' `addRow`: zeroed slots, reserved FixedShape
   indirect arrays) and of TiledColumnStMan and TiledShapeStMan with
   FixedShape columns (the hypercube extended); `removeRow64` of
   StandardStMan (`SSMIndex::deleteRow`, data shifted within the bucket,
   empty buckets freed, strings released). The tiled managers cannot remove
   rows in casacore (`DataManager::canRemoveRow` is false); the core
   refuses exactly where casacore does.
3. **String arrays** in StandardStMan, both kinds: variable-shape
   (`SSMIndStringColumn`: `setShape` writes ndim, the dimensions and a 0
   flag through `SSMStringHandler::putShape`; the put then writes ndim,
   dimensions, flag 1 and the strings, replacing in place when the old
   record is at least as long, else removing it and appending) and
   fixed-shape Direct (`SSMDirColumn`: the strings without a shape header).
4. **`default_ms(path, desc, dminfo, source)`**: MAIN and the default
   subtables of `MeasurementSet::createDefaultSubtables` (ANTENNA,
   DATA_DESCRIPTION, FEED, FIELD, FLAG_CMD, HISTORY, OBSERVATION, POINTING,
   POLARIZATION, PROCESSOR, SPECTRAL_WINDOW, STATE) with casacore's
   required column set, data managers, keywords and `table.info`; SOURCE
   only on request (`createDefaultSubtables` does not make it), as
   python-casacore's `default_ms_subtable("SOURCE", ...)` plus the
   `SOURCE` keyword makes it.
5. **CASA calibration tables** G, B, K and Df, the schema read from the
   real CASA 6.7.6 tables (O-CASA run `-01`), not from the survey:
   - MAIN: 13 columns in this order: TIME, FIELD_ID, SPECTRAL_WINDOW_ID,
     ANTENNA1, ANTENNA2, INTERVAL, SCAN_NUMBER, OBSERVATION_ID (scalars,
     option 5), CPARAM (Complex; G, B, Df) or FPARAM (Float; K), PARAMERR,
     FLAG, SNR, WEIGHT (variable-shape arrays, indirect); no
     TIME_EXTRA_PREC and no ARRAY_ID. Units and MEASINFO as CASA writes.
   - One StandardStMan named `MSMTAB` with the default 32-row bucket, the
     column descriptions naming type and group `StandardStMan` (CASA's
     bytes; the 3.8.1 deep copy names the group `MSMTAB`, see below).
   - Table description name = the `VisCal` name, version `1.0`, comment
     `New calibration table`; keywords `ParType` (`Complex`/`Float`),
     `MSName` (as given; CASA writes the basename), `VisCal` (`G Jones`,
     `B Jones`, `K Jones`, `Df Jones`), `PolBasis`, `CASA_Version` (a
     parameter: the byte cases pass CASA's `6.7.6-14`), and the subtable
     links OBSERVATION, ANTENNA, FIELD, SPECTRAL_WINDOW, HISTORY in that
     order.
   - `table.info`: type `Calibration`, subType the VisCal name; subtables
     with an empty type.
   - Subtables OBSERVATION, ANTENNA, FIELD, SPECTRAL_WINDOW, HISTORY with
     CASA's column sets (each one StandardStMan `MSMTAB`).
   - Written as CASA writes them (`NewCalTable::writeToDisk`): rows sorted
     by (SPECTRAL_WINDOW_ID, TIME, ANTENNA1, ANTENNA2), then casacore's
     `deepCopy`: `makeEmptyTable` with all rows, `copyRows` row by row
     (each row's cells in column order, undefined cells skipped),
     `copyInfo`, then each subtable the same way. CASA sorts with a
     non-stable heap sort, so the core refuses duplicate sort keys.

Deferred to E5, refused with an error whose message names E5:
IncrementalStMan writes (so also adding or removing rows of any table that
has an IncrementalStMan, such as the fixture and every CASA-written MS),
big-endian tables, TiledShapeStMan rows without a hypercube (variable-shape
tiled columns), MultiFile storage, MemoryStMan, TiledDataStMan. Also
refused, as casacore refuses it: removing rows of a table with a tiled
manager.

## Scratch measurements before freezing

**Determinism inventory.** python-casacore 3.8.1 created three tables
four times (two plain runs, `MALLOC_PERTURB_=85`, `=170`): a 100-row
StandardStMan table with scalars of five types, variable and fixed
strings, Direct Double [3], variable Complex and Bool arrays, variable and
Direct string arrays, a keyword and `table.info`, then 40 rows added and 3
removed; a TiledShapeStMan table (Complex and Bool [16, 4], tile [4, 8,
8]); `default_ms`. Script and output `~/Build/tmp/20261030-e4/inv`
(scratch; 2.3 s for the four containers). **The two plain runs are
identical; under `MALLOC_PERTURB_` exactly one file differs**, the
StandardStMan table's `table.f0i` (1,093 bytes, the alignment gaps of
E3's known padding exception). The tiled table, `default_ms`, every
`table.dat`, `table.f0` (string buckets included), `table.info` and the
sync record are stable.

**CASA's caltables against a 3.8.1 deep copy.** python-casacore 3.8.1
deep-copied O-CASA's `c.G0`, `c.B0`, `c.K0` (`table.copy(deep=True,
valuecopy=True)`) and the copies were compared with CASA's files
(`~/Build/tmp/20261030-e4/ct`). Every subtable file, `table.f0`,
`table.info` and the sync record (modify 2, table change 2, manager change
[1]) are identical; `table.dat` differs only in the 13 column
descriptions' data-manager group (CASA `StandardStMan`, the 3.8.1 copy
`MSMTAB`); `table.f0i` differs only in alignment gaps (G 127 bytes, K 176
bytes; B identical). WEIGHT is undefined in every row of all three tables;
CPARAM/FPARAM, PARAMERR, SNR and FLAG are defined everywhere (G and K
cells [1, 2] in NumPy order, B [2048, 2]). **So CASA's own tables are a
valid byte target**, with the same padding exception, and the core replays
one sequence (CASA's `writeToDisk`).

## Oracles (frozen)

- **python-casacore 3.8.1** in `rang-ms-reader:local` (as E3: `docker run
  --rm --network none --user $(id -u):$(id -g)`, inputs mounted read-only,
  one writable output directory): `examples/oracle_ms_create.py` performs
  every frozen N/R/D case (below) with python-casacore's API, one close per
  session, and writes the values it used to `values/<case>.npz` (seeded
  generator, seed 20261030) so that the core writes exactly the same
  values; a `readback` mode dumps every column (with cell definedness),
  keyword and `table.info` of given tables.
- **CASA 6.7.6.14** in `rang-o-casa:6.7.6.14` (O-CASA conventions:
  `--network none`, `--tmpfs /tmp -e HOME=/tmp`, `OMP_NUM_THREADS=4`,
  inputs read-only, a fresh `outputs/e4-20261030-NN` mounted at `/run`):
  on a copy of O-CASA run `-01`'s `c.ms` (stored model, setjy already
  applied) it solves K, G and B exactly as O-CASA's arm C (refant `m000`,
  `minblperant=3`, no `uvrange`, the same solints and interpolation), then
  Df with `polcal(poltype='Df', solint='inf', combine='scan',
  gaintable=[K, G, B], refant='m000', minblperant=3)`; `applycal` (O-CASA's
  apply settings, with Df appended to the tables) on copies of the MS.
- **The core reader** `rang.core_ms` and the writer's own reads (string
  arrays and undefined cells, which the task E reader does not handle).
- **Comparators**: byte-for-byte file comparison as E3's
  `compare_trees` (every file but `table.lock`; `table.lock` from offset
  260, the sync record), with the single named exception below; column
  comparison as E3's `compare_arrays`/`compare_strings` (dtype, shape,
  bytes; NaN payloads and signed zeros count; strings by value), plus cell
  definedness.

**The one exception, named and masked explicitly** (E3's padding): in a
`table.fNi` file, the bytes of the alignment gap after each array record.
The mask is computed from casacore's (or CASA's) copy: walk the record
chain from offset 16 (the first record) where each record starts at the
8-byte-aligned end of the previous one; a record is the shape header
(version-0 file: ndim and the dimensions as little-endian Int) plus the
values (Bool `ceil(n/8)` bytes, else `n × element size`), the element size
being that of the column whose row references the record, or for a record
no row references any more (replaced by a shape change) that of the column
the case's operations name for it. The chain must end exactly at the end
of the file, the two files must have the same length, and every byte
inside a record must be equal; only gap bytes (at most 7 after each
record) may differ. No other byte of any file is masked; any other
difference fails the case.

## Frozen cases

Each case is one sequence of python-casacore calls on the oracle side and
the same sequence through `rang.core_ms_write` on the core side. N = 100
unless stated; values from the seeded generator.

New tables (default StandardStMan unless stated):

- **N-scalars**: `table(path, desc, nrow=100)`; columns Bool, uChar, Short,
  Int, uInt, Int64, Float, Double, Complex, DComplex, String (variable,
  lengths 0 to 40, both sides of 8), String with `maxlen=6`; `putcol` of
  every column in description order; table keywords (Double, Int, String,
  Double array, String array, a sub-record), column keywords (QuantumUnits
  string array and a MEASINFO record on the Double column); `putinfo`
  (type, subType, a two-line readme).
- **N-arrays** (60 rows): Direct Double [3] and Bool [7]; FixedShape
  indirect Complex [4, 8] (NumPy order [8, 4]); variable-shape Float
  (ndim 2), Bool (ndim 1) and Complex (ndim 2) with shapes depending on the
  row; `putcol` of the fixed ones, `putcell` row by row of the variable
  ones, row 5 of the variable Float column left undefined, then one
  `putcell` giving row 7 of the variable Complex column a new shape
  (orphaning its old record).
- **N-strarr** (80 rows): a variable string array (ndim 1) put cell by
  cell: empty arrays, short strings, a cell whose record does not fit the
  room left (both sides of the 50-byte rule), and a cell of more than one
  bucket of characters; a Direct string array [2] (`putcol`); then
  replacements of some cells with shorter and longer values; row 3 of the
  variable column left undefined.
- **N-tiled** (50 rows): Int (StandardStMan); TiledColumnStMan Complex
  [4, 16] (NumPy [16, 4]) tile [4, 8, 8]; TiledShapeStMan with Float and
  Bool [4, 16] in one hypercolumn, tile [4, 8, 8]; `putcol` of all.
- **N-buckets** (3,000 rows): two StandardStMan managers from a dminfo,
  one with `BUCKETSIZE` 1024 (Int, Double, variable String; its index
  outgrows half a bucket) and one with `BUCKETROWS` 100 (Float, Bool);
  `putcol` of all.

Rows:

- **R-add-new**: a 10-row table (Bool, Int, variable String, Direct
  Float [2], FixedShape indirect Complex [3, 2], variable Double ndim 1,
  variable string array), `addrows(45)` in the same session, then `putcol`
  of all 55 rows (cell by cell for the variable columns).
- **R-add-existing**: on copies of casacore's own N-scalars, N-arrays and
  N-tiled outputs, and of the LUNO export
  `outputs/luno-solve-20261029-02/work.ms` (all StandardStMan, 37 MB,
  read in place and never written: copies are written): `addrows(37)`
  (N-tiled: 20; LUNO: 120), then `putcol`/`putcell` of the new rows of
  every writable column (LUNO: FLAG, FLAG_ROW, TIME, ANTENNA1, ANTENNA2,
  DATA, UVW).
- **R-remove**: on copies of casacore's N-scalars (`removerows([0, 5, 6,
  7, 99])`), N-strarr (rows 10 to 39), N-buckets (every row of the first
  data bucket of the BUCKETSIZE-1024 manager, which empties it) and the
  LUNO export (rows 0 to 99); on N-tiled both sides must refuse.

`default_ms`:

- **D-plain**: `default_ms(path)`.
- **D-source**: `default_ms(path)`, then `default_ms_subtable("SOURCE",
  path + "/SOURCE")` and the `SOURCE` table keyword on MAIN.
- **D-data**: `default_ms(path, desc, dminfo)` with DATA Complex [4, 64]
  (NumPy [64, 4]) in a TiledShapeStMan (tile [4, 32, 8]), then
  `addrows(20)` and `putcol` of DATA, TIME, ANTENNA1, ANTENNA2, UVW and
  FLAG; ANTENNA `addrows(4)` and `putcol` of NAME, STATION, POSITION,
  DISH_DIAMETER.

Calibration tables (CASA oracle, run `outputs/e4-20261030-NN`):

- **C-K, C-G, C-B, C-Df**: the core reads CASA's table (every column of
  MAIN and the subtables, keywords, info, definedness) and writes a new
  caltable from those contents with `create_caltable` (MSName `x.ms` as
  CASA records it, CASA_Version `6.7.6-14`); every file compared with
  CASA's.
- **C-synthetic**: a G table the core makes from its own values (one
  solution per antenna, gains with a seeded amplitude and phase, a few
  flagged), with the ANTENNA, FIELD, SPECTRAL_WINDOW and OBSERVATION
  subtables taken from the MS; consumed by CASA `applycal` alone.

## Acceptance criteria (frozen)

Checked by `examples/check_ms_create.py` (host) with the oracles' modes in
the containers, written to `result.json`; every criterion gates.

1. **Byte identity, casacore cases.** For every N, R and D case, every file
   of the core's table tree (subtables included) equals casacore's byte
   for byte, and the sync record of every `table.lock` is equal, except
   only the masked alignment gaps of `table.fNi` files defined above.
2. **Byte identity, CASA caltables.** For C-K, C-G, C-B and C-Df, the
   core's table tree equals CASA's under the same rule.
3. **Read-back.** python-casacore reads every column (and cell
   definedness), keyword, column keyword and `table.info` of every
   core-written table exactly as it reads the oracle's copy; the core
   reads the oracle's tables column-exactly as python-casacore does
   (CASA's K, G, B and Df included).
4. **CASA consumes the core's tables.** `applycal` with the core's K, G,
   B and Df (C cases) gives CORRECTED_DATA and FLAG bit-identical to
   `applycal` with CASA's own tables on a second copy of the same MS. With
   C-synthetic alone, CORRECTED_DATA equals the correction computed on the
   host (V_pq / (g_p,a conj(g_q,b)) for correlation ab) to 1e-6 relative
   (max over unflagged cells of |V − V_expected| / |V_expected|), with the
   flags of flagged solutions applied.
5. **Determinism.** The core's outputs of every case are byte-identical
   between two runs and a run under `MALLOC_PERTURB_=85` (no mask).
   casacore's outputs of a second run and of a `MALLOC_PERTURB_=85` run
   equal its first run except in the masked gaps (recorded as measured).
6. **Refusals.** Each deferred item raises an error naming E5 and changes
   no file: creating with IncrementalStMan, MemoryStMan, TiledDataStMan, a
   variable-shape TiledShapeStMan column, MultiFile storage or big-endian
   format; adding and removing rows of the fixture (IncrementalStMan).
   Removing rows of N-tiled raises in both casacore and the core.
7. **E3 unchanged.** `examples/check_ms_writer.py` steps `cases`,
   `roundtrip` and `serialisation` against E3's oracle
   `outputs/e3-20261030-01` give E3's frozen verdicts (20 cases identical,
   4 identical but alignment padding; round trip and serialisation pass);
   `tests/test_core_ms_write.py` passes.
8. **Serialisation identity.** `serialise(parse(x)) == x` for every
   `table.dat`, StandardStMan header and index and tiled header of every
   oracle-written table (casacore's and CASA's).

Reported, not gated: wall time of every core creation next to casacore's
(and CASA's task times), bytes written.

Failures are recorded as measured; any later fix is a new run labelled
post hoc, and the frozen result stays in this file.

## Implementation plan

- `core/src/ms_create.rs`: `create_table` (a description as `ColDesc`s
  plus a data-manager list; the directory, `table.dat`, `table.info`,
  `table.lock`, the managers), returning an E3 `TableWriter`; the casacore
  required descriptions of MAIN and the default subtables
  (`default_ms`), as Rust data.
- `core/src/caltable.rs`: the NewCalTable schema (MAIN and five
  subtables) and `create_caltable` in CASA's write order.
- `core/src/ms_write.rs` (E3): `add_rows`/`remove_rows` on StandardStMan
  and the tiled managers, string-array puts, undefined cells, `table.info`
  writes, reads of string arrays and undefined cells.
- `core/src/aipsio.rs`: table-valued keywords.
- `core/src/ffi_ms_write.rs` and the extension (`core/py/src/lib.rs`,
  coordinator's file: applied locally and listed verbatim): the new calls.
- `python/rang/core_ms_write.py`: `create_table`, `default_ms`,
  `create_caltable`, `Table.addrows`/`add_rows`, `removerows`/
  `remove_rows`, `putinfo`, string-array `putcol`/`putcell`.
- `examples/oracle_ms_create.py` (containers), `examples/check_ms_create.py`
  (host), `tests/test_e4_table_create.py` (skips without Docker, the
  images, the oracle outputs or the binding).

Every tool run is timed and listed under Timings.

## What is implemented

As planned, with these additions (all measured by the frozen run):

- `core/src/ms_create.rs` (≈770 lines with tests): `create_table` (bound
  managers in `dminfo` order, then one manager per data-manager group of
  the unbound columns in column order, sequence numbers in that order; a
  new `table.lock`; `table.dat`, `table.info` and the sync record on the
  first flush through E3's `TableWriter`); `default_ms` and
  `default_ms_subtable` (POINTING bound as `createDefaultSubtables` binds
  it: IncrementalStMan `ISMPointing`, ANTENNA_ID in a 32768-byte
  StandardStMan `SSMPointing`); and, for that POINTING table only, the
  files of an **empty** IncrementalStMan (header, one bucket of default
  values, the index, an empty version-1 array file; its rows and values
  refuse, E5).
- `core/src/ms_schema.rs` (≈770, data): the required descriptions of MAIN,
  the 13 MS subtables and CASA's calibration MAIN table, generated once
  from casacore's and CASA's `table.dat` by a scratch tool and checked by
  the byte comparisons (column names, types, comments, units and measure
  references are the MS v2 and NewCalTable definitions). CASA's
  calibration subtables use exactly the MS descriptions (measured).
- `core/src/caltable.rs` (≈190): the calibration MAIN spec (CPARAM or
  FPARAM, one StandardStMan `MSMTAB` whose columns name type and group
  `StandardStMan`, the five keywords, the links, `table.info`) and the
  subtable specs.
- `core/src/ms_write.rs` (E3, +≈1,100): string arrays (variable-shape:
  `setShape`, then the put with shape and flag, replaced in place or
  removed and appended as `SSMStringHandler` does; Direct and FixedShape:
  no shape), undefined cells, read-only cell reads (`read_cells`),
  `add_rows` (`SSMIndex::addRow`, FixedShape indirect arrays reserved;
  TiledColumnStMan extends its cube, a FixedShape TiledShapeStMan makes
  and extends hypercube 1 with its row map), `remove_rows` (each column's
  `deleteRow`, including the Bool cache rewrite and the string-heap
  release, `SSMIndex::deleteRow`, emptied buckets freed), `put_info`,
  `mark_changed` (casacore's `rwKeywordSet`), `array_records` (the gap
  mask's record list), and a model of casacore's **bucket cache** (LRU
  slots, dirty flags and its scratch buffer `its_Buffer`): casacore writes
  that buffer into every bucket it frees, so freed buckets are now
  byte-identical (E3's open item; R-remove-buckets and R-remove-luno free
  buckets). Found on the way: casacore's string handler keeps one
  character buffer, so a new string bucket starts with the previous
  bucket's bytes (E3 zeroed it; no E3 case exercised it).
- `core/src/aipsio.rs`: table-valued keywords (`KeywordValue::Table`, the
  field naming an empty table description) and field comments
  (`MS_VERSION` has one).
- `core/src/ffi_ms_write.rs`: keyword kind 5 (table), C ABI
  `rang_core_ms_write_add_rows/remove_rows/put_info`, and the tuple types
  and converters of the extension's creation calls (creation itself is
  only in the extension; open item).
- `python/rang/core_ms_write.py`: `create_table` and a python-casacore
  style `table(name, desc, nrow, dminfo=...)`, `default_ms`,
  `default_ms_subtable`, `create_caltable` (CASA's write sequence: rows
  sorted by SPECTRAL_WINDOW_ID, TIME, ANTENNA1, ANTENNA2 with duplicates
  refused; MAIN filled row by row and flushed; each subtable created,
  filled row by row, flushed, marked changed and flushed again as
  `TableCopy::copySubTables` does; then MAIN's links defined and flushed),
  `read_cells`; on `Table`: string-array `putcol`/`putcell`, `getcell`,
  `iscelldefined`, `addrows`/`add_rows`, `removerows`/`remove_rows`,
  `putinfo` (a non-empty readme is one added line, as python-casacore),
  `Table: <path>` keywords. Two python-casacore 3.8.1 conventions adopted
  after measuring them: a Python int keyword is stored as Int64, and a
  default value's type follows Python's (int → Int, float → double,
  complex → DComplex).
- `examples/oracle_ms_create.py`: the frozen cases as functions run with
  either `casacore.tables` or `rang.core_ms_write` as `pt`; modes `write`,
  `readback`, `casa-solve` (K, G, B as O-CASA arm C on field J1939-6342,
  then Df) and `casa-apply`. `examples/check_ms_create.py`: the eight
  criteria and `summary`. `tests/test_e4_table_create.py`: 9 tests of the
  core alone (skipping without the E4 binding) and the archived verdict.

## Measured result (2026-10-30)

Run `outputs/e4-20261030-01`, all steps by one script, every step timed in
`timing/` with logs in `logs/`: `oracle` (casacore `write`), `oracle2`,
`oracle-perturb` (`MALLOC_PERTURB_=85`), then `cases`, `determinism`,
`casa`, `apply`, `readback`, `refusals`, `e3`, `serialisation`, `summary`
→ `result.json` (`all_pass: true`). Code: commit `c609f71` plus the
wiring diff of the appendix. Inputs read in place, never written: the LUNO
export, O-CASA run `-01`'s `c.ms` (copied inside the container), the
fixture (copied for the refusals), E3's oracle `outputs/e3-20261030-01`.
Development runs preceded it in scratch (deleted); the frozen run is the
first in `outputs/`.

**Criterion 1, casacore cases: passes.**

| Case | Files | Bytes | Against casacore 3.8.1 | Core (ms) | casacore (ms) |
| --- | ---: | ---: | --- | ---: | ---: |
| N-scalars | 4 | 18,085 | identical | 27.0 | 39.1 |
| N-arrays | 5 | 30,257 | identical but 580 gap bytes in `table.f0i` | 5.4 | 17.3 |
| N-strarr | 4 | 20,039 | identical | 6.1 | 20.7 |
| N-tiled | 8 | 46,864 | identical | 5.2 | 17.6 |
| N-buckets | 5 | 114,808 | identical | 8.9 | 33.5 |
| R-add-new | 5 | 16,239 | identical but 50 gap bytes in `table.f0i` | 4.9 | 15.9 |
| R-add-scalars | 4 | 22,765 | identical | 4.2 | 13.0 |
| R-add-arrays | 5 | 47,585 | identical | 3.6 | 12.1 |
| R-add-tiled | 8 | 59,664 | identical | 5.3 | 11.4 |
| R-add-luno (+120 rows) | 59 | 62,000,142 | identical | 24.0 | 58.3 |
| R-remove-scalars | 4 | 18,085 | identical | 4.8 | 11.3 |
| R-remove-strarr | 4 | 20,039 | identical | 3.4 | 10.3 |
| R-remove-buckets (a data bucket emptied) | 5 | 115,221 | identical | 4.1 | 21.0 |
| R-remove-luno (100 rows) | 59 | 38,257,794 | identical | 3.7 | 14.8 |
| R-remove-tiled | 8 | 46,864 | both refuse; files identical | 4.3 | 3.7 |
| D-plain | 59 | 149,144 | identical | 68.3 | 149.2 |
| D-source | 63 | 156,329 | identical | 74.5 | 173.3 |
| D-data | 61 | 207,569 | identical but 40 gap bytes in `table.f1i` | 56.6 | 162.6 |

Every `table.lock` sync record is equal. casacore's times are its own
process's (container start excluded), the core's the checker's.

**Criterion 2, CASA's calibration tables: passes.** CASA 6.7.6 solved on
a copy of O-CASA's `c.ms` (gaincal K 0.36 s, G 0.30 s, bandpass 0.37 s,
polcal Df 0.53 s); the core read each table and wrote it again with
`create_caltable`:

| Case | Rows | Files | Bytes | Against CASA | Core (ms) |
| --- | ---: | ---: | ---: | --- | ---: |
| C-K (FPARAM) | 12 | 27 | 66,366 | identical but 199 gap bytes | 105.9 |
| C-G | 12 | 27 | 66,464 | identical but 69 gap bytes | 72.2 |
| C-B | 4 | 27 | 395,264 | identical but 28 gap bytes | 71.6 |
| C-Df | 4 | 27 | 395,267 | identical but 28 gap bytes | 73.2 |

All differing bytes are gaps of MAIN's `table.f0i`; `table.dat`,
`table.f0`, `table.info`, every subtable file and every sync record (2,
2, [1] for MAIN and subtables) are identical.

**Criterion 3, read-back: passes.** 103 tables (the 18 cases with their
subtables on both sides, CASA's four and the core's four with subtables),
46,933 defined cells: python-casacore reads the core's tables exactly as
casacore's (keywords, column keywords, info, definedness, every cell), and
the core reads casacore's and CASA's tables exactly as python-casacore
does; one convention compared by value: python-casacore returns uChar
cells as uint16 (the core uint8).

**Criterion 4, CASA consumes the core's tables: passes.** `applycal` (K,
G, B, Df; O-CASA's apply settings) on two copies of the MS, CASA's tables
on one and the core's on the other: CORRECTED_DATA and FLAG bit-identical.
The synthetic G table (seeded gains, one solution per antenna, one
flagged, subtables from the MS with one channel per window as gaincal
writes them) applied alone: 345,362 unflagged cells of J1939-6342 compared
with V_pq / (g_p,a conj(g_q,b)) computed on the host, max relative error
4.3e-7; the flagged solution's correlations are flagged.

**Criterion 5, determinism: passes.** The core's outputs of every case are
identical between two runs and a `MALLOC_PERTURB_=85` run (no mask).
casacore's second run equals its first; its perturbed run differs only in
masked gaps (N-arrays 1,035 bytes, R-add-new 220, R-add-arrays 1,672,
D-data 76, all `table.fNi`), as the inventory predicted.

**Criterion 6, refusals: passes.** IncrementalStMan, MemoryStMan,
TiledDataStMan, a variable-shape TiledShapeStMan column, MultiFile and
big-endian creation refuse naming E5 and leave no table; adding and
removing rows of a fixture copy refuse (E5) and change no data file.

**Criterion 7, E3 unchanged: passes.** E3's checker against its frozen
oracle: 20 cases identical, 4 identical but alignment padding; round trip
and serialisation pass; `tests/test_core_ms_write.py` passes.

**Criterion 8, serialisation identity: passes**: 103 tables, 105
StandardStMan files and 7 tiled headers of casacore's and CASA's tables.

## Deviations

- Scope item 4 needed an IncrementalStMan: `createDefaultSubtables` binds
  POINTING to one. The core writes the files of an empty IncrementalStMan
  for that table only (inside `default_ms`); `create_table` still refuses
  IncrementalStMan (criterion 6) and the POINTING table's rows refuse (E5).
- The read-back comparator uses python-casacore's `getcol` for scalar
  cells (`getcell` returns Python ints) and compares uChar by value; both
  fixed in development, before the frozen run.
- C-synthetic's SPECTRAL_WINDOW has one channel per window: during
  development CASA aborted on a 2048-channel window for a one-channel G
  table.

## Open items

- Removing the last row of a StandardStMan (casacore recreates the
  manager) is refused.
- Table creation is not in the C ABI (extension only); rows and info are.
- The task E reader (`ms.rs`, not this task's file) still treats
  variable-shape string arrays as indirect arrays and refuses undefined
  cells; `core_ms_write.read_cells` and `Table.getcell` cover both.
- `default_ms` writes each subtable when it is created, casacore when MAIN
  closes; the files are identical (measured).
- Nothing large was created; speed was not tuned (the core is 1.5–4×
  faster than python-casacore on these tables).

## Timings

| Date | Tool / stage | Input | Wall | Notes |
| --- | --- | --- | ---: | --- |
| 2026-10-30 | `git clone --depth 1 --branch v3.8.1 casacore` | 43 MB | 5.1 s | format reference, scratch |
| 2026-10-30 | `git clone --sparse` casa6 mirror (CalTables, MSVis) | dic-case-studies/casa6 | ~60 s | NewCalTable reference, scratch, not timed precisely |
| 2026-10-30 | `git clone --depth 1 --branch v3.8.1 python-casacore` | | 1.3 s | `default_ms` reference, scratch |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin pip` | worktree | 74.7 s | |
| 2026-10-30 | `uv pip install casacure==3.8.35` | | 0.7 s | E3's second read-back oracle (criterion 7) |
| 2026-10-30 | determinism inventory, python-casacore 3.8.1, 4 containers | 3 tables | 2.3 s | pre-freeze scratch |
| 2026-10-30 | deep copy of O-CASA's K, G, B, python-casacore 3.8.1 | 3 caltables | ~3 s | pre-freeze scratch |
| 2026-10-30 | `cargo build --release` (core) | `core/` | 150.6 s | first build in the worktree |
| 2026-10-30 | `maturin develop --release` | extension | 108–265 s | six builds |
| 2026-10-30 | `cargo test --release` (core, 115 tests) | `core/` | 256.6 s | build included |
| 2026-10-30 | `pytest tests/test_e4_table_create.py tests/test_core_ms_write.py` | | 7.8 s | 18 passed, 1 skipped |
| 2026-10-30 | oracle `write` (run `oracle`) | 18 cases | 1.8 s | container; 103 MB |
| 2026-10-30 | oracle `write`, second / `MALLOC_PERTURB_=85` | 18 cases | 1.5 s / 1.6 s | |
| 2026-10-30 | `check_ms_create.py cases` | 18 cases | 0.7 s | |
| 2026-10-30 | `check_ms_create.py determinism` | 2 × 18 cases | 2.3 s | |
| 2026-10-30 | `check_ms_create.py casa` (CASA K, G, B, Df, dump, rebuild) | O-CASA `c.ms` | 5.7 s | container 4.6 s; CASA tasks 0.30–0.53 s |
| 2026-10-30 | `check_ms_create.py apply` | 3 × `applycal` | 6.9 s | container 6.5 s |
| 2026-10-30 | `check_ms_create.py readback` | 103 tables | 7.6 s | container 3.5 s |
| 2026-10-30 | `check_ms_create.py refusals` | 8 attempts | 0.4 s | |
| 2026-10-30 | `check_ms_create.py e3` | E3 oracle | 7.8 s | |
| 2026-10-30 | `check_ms_create.py serialisation` | 103 tables | 0.1 s | |
| 2026-10-30 | `bash tools/check-all.sh` (wiring diff present) | repo | 786 s | PASS: root 23, core 115 Rust tests; pytest 630 passed, 4 skipped (118 s); log `outputs/e4-20261030-check-all.log`; a first run (867 s) failed only `git diff --check` on this file's appendix |

## For the coordinator

- `core/src/lib.rs`, alphabetical: `pub mod caltable;`, `pub mod
  ms_create;`, `pub mod ms_schema;` (no new dependency, `Cargo.lock`
  unchanged).
- `core/py/src/lib.rs`: the appendix diff (new `MsWriter` methods
  `put_string_cells`, `columns`, `add_rows`, `remove_rows`, `is_defined`,
  `mark_changed`, `put_info`, `read_cells`; functions `ms_create_table`,
  `ms_default_ms`, `ms_default_ms_subtable`, `ms_caltable_main`,
  `ms_caltable_subtable`, `ms_read_cells`, `ms_array_records`; the
  `ffi_ms_write` import). Without it `tests/test_e4_table_create.py`
  skips. `tools/check-all.sh` ran with the diff present.
- STATE paragraph: "E4 (core table creation) measured: rang's core now
  creates casacore tables as casacore 3.8.1 does: new tables from a
  description (StandardStMan, TiledColumnStMan, TiledShapeStMan, keywords,
  `table.info`), rows added and removed on new and existing managers,
  string arrays, `default_ms` with its subtables (SOURCE on request), and
  CASA calibration tables (G, B, K, Df) written in CASA's own sequence. 18
  casacore cases and CASA 6.7.6's own K, G, B and Df tables are
  byte-identical except casacore's uninitialised alignment gaps in
  `table.fNi` (masked, 7 of 22); CASA `applycal` with the core's copies
  gives bit-identical CORRECTED_DATA and FLAG, a core-made G table applies
  to 4.3e-7; read-back, determinism (twin and MALLOC_PERTURB_), E5
  refusals, E3 and serialisation checks pass. `outputs/e4-20261030-01`,
  `research/results/e4-table-create.json`."
- `research/README.md` index line: "[e4-table-create.md](e4-table-create.md)
  — E4: casacore table creation, rows, string arrays, `default_ms` and CASA
  caltables in the core writer; byte-identical to casacore 3.8.1 and CASA
  6.7.6 (gaps masked), applycal bit-identical (measured)."
- `research/tool-timings.md`: the Timings rows above and the check-all row
  in the final report.
- `research/big-plan.md`: E4 done 2026-10-30 (`e4-table-create.md`).
- README: `rang.core_ms_write` creates casacore tables, MeasurementSets
  (`default_ms`) and CASA calibration tables; python-casacore is no longer
  needed to create them (it stays the oracle).
- Upstream observations (all non-RATT, for
  `research/non-ratt-observations.md`; nothing RATT, caracal-pipeline or
  saopicc):
  - casacore 3.8.1 (E3's item, confirmed): `table.fNi` alignment gaps hold
    uninitialised heap bytes (4 of 18 cases differ under
    `MALLOC_PERTURB_=85`).
  - casacore 3.8.1 (note): the bucket cache writes its scratch buffer (the
    last bucket read or written) into a freed StandardStMan bucket, and the
    string handler starts a new string bucket with the previous bucket's
    characters: file contents depend on access history (deterministic,
    unreferenced).
  - CASA 6.7.6 (note): calibration tables name the columns' data-manager
    group `StandardStMan` where a casacore 3.8.1 deep copy keeps `MSMTAB`;
    rows are sorted with a non-stable heap sort.
  - python-casacore 3.8.1 (note): Python int keywords become Int64,
    `getcell` returns Python scalars, uChar cells come back as uint16.
- DF-IO-CT should pick up: `create_caltable` (sorted rows, WEIGHT left
  undefined as CASA leaves it, SPECTRAL_WINDOW with one channel per window
  for G/K/Df), the `applycal` round trip of `check_ms_create.py apply`,
  and per-VisCal semantics (parameter layouts, interpolation, reference
  antenna), which E4 does not interpret.
- E5 should pick up: IncrementalStMan rows and values (only the empty
  POINTING ISM is written), big-endian, variable-shape tiled columns (more
  than one hypercube), MultiFile, MemoryStMan, TiledDataStMan, removing
  the last row of a StandardStMan, creation in the C ABI.
- Ignored output: `outputs/e4-20261030-01` (2.7 GB: `e3/` 1.7 GB, E3's
  re-run, can be deleted; `refusals/` 80 MB, `apply/` 183 MB and `dumps/`
  185 MB can be trimmed to their JSON) and
  `outputs/e4-20261030-check-all.log`.
- Scratch `~/Build/tmp/20261030-e4` (clones, development runs, the
  generator) is deleted at the end of the task.

## Appendix: the wiring diff

Exactly what `tools/check-all.sh` compiled (`git apply` from the
repository root):

```diff
diff --git a/core/py/src/lib.rs b/core/py/src/lib.rs
index 8cd49b9..e88889c 100644
--- a/core/py/src/lib.rs
+++ b/core/py/src/lib.rs
@@ -34,7 +34,9 @@ use rang_core::ffi;
 use rang_core::ffi_correct::CorrectInputsC;
 use rang_core::ffi_flag::{FlagInputs, FlagOutputs};
 use rang_core::ffi_grid::{GridInputs, GridOutputs};
-use rang_core::ffi_ms_write::{keyword_value, new_column};
+use rang_core::ffi_ms_write::{
+    ColumnArgs, ManagerArgs, column_descs, keyword_value, manager_specs, new_column,
+};
 use rang_core::ffi_weights::{
     ImagingWeightInputs, ImagingWeightOutputs, StokesIInputs, StokesIOutputs,
 };
@@ -1294,6 +1296,216 @@ impl MsWriter {
             None => Ok(()),
         }
     }
+
+    /// Write `count` rows of a string-array column from `start`, every
+    /// cell of `shape` (casacore order), strings in Fortran order.
+    fn put_string_cells(
+        &mut self,
+        name: &str,
+        start: u64,
+        count: u64,
+        shape: Vec<i64>,
+        strings: Vec<String>,
+    ) -> PyResult<()> {
+        self.get()?
+            .put_string_cells(name, start, count, &shape, &strings)
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    /// The columns as (name, type code, is array), in table order.
+    fn columns(&mut self) -> PyResult<Vec<(String, i32, bool)>> {
+        Ok(self
+            .get()?
+            .dat
+            .columns
+            .iter()
+            .map(|c| (c.name.clone(), c.dtype, c.is_array()))
+            .collect())
+    }
+
+    fn add_rows(&mut self, py: Python<'_>, n: u64) -> PyResult<()> {
+        let w = self.get()?;
+        detach(py, || w.add_rows(n)).map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    fn remove_rows(&mut self, py: Python<'_>, rows: Vec<u64>) -> PyResult<()> {
+        let w = self.get()?;
+        detach(py, || w.remove_rows(&rows)).map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    fn is_defined(&mut self, name: &str, row: u64) -> PyResult<bool> {
+        self.get()?
+            .is_defined(name, row)
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    /// Mark the table changed (casacore's `rwKeywordSet`).
+    fn mark_changed(&mut self) -> PyResult<()> {
+        self.get()?
+            .mark_changed()
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    fn put_info(&mut self, kind: &str, sub_kind: &str, readme: &str) -> PyResult<()> {
+        self.get()?
+            .put_info(kind, sub_kind, readme)
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    /// Flush, then read cells: (0 undefined / 1 values / 2 strings, shape
+    /// in casacore order, native bytes, strings) per row.
+    fn read_cells<'py>(
+        &mut self,
+        py: Python<'py>,
+        name: &str,
+        start: u64,
+        count: u64,
+    ) -> PyResult<Vec<CellTuple<'py>>> {
+        let w = self.get()?;
+        let cells =
+            detach(py, || w.read_cells(name, start, count)).map_err(|e| PyOSError::new_err(e.0))?;
+        Ok(cells.into_iter().map(|c| cell_tuple(py, c)).collect())
+    }
+}
+
+type CellTuple<'py> = (i32, Vec<i64>, Bound<'py, PyBytes>, Vec<String>);
+
+fn cell_tuple(py: Python<'_>, cell: rang_core::ms_write::Cell) -> CellTuple<'_> {
+    use rang_core::ms_write::Cell;
+    match cell {
+        Cell::Undefined => (0, Vec::new(), PyBytes::new(py, &[]), Vec::new()),
+        Cell::Values(shape, bytes) => (1, shape, PyBytes::new(py, &bytes), Vec::new()),
+        Cell::Strings(shape, strings) => (2, shape, PyBytes::new(py, &[]), strings),
+    }
+}
+
+fn writer(w: rang_core::ms::Result<TableWriter>) -> PyResult<MsWriter> {
+    w.map(|w| MsWriter { writer: Some(w) })
+        .map_err(|e| PyOSError::new_err(e.0))
+}
+
+/// Create a table (research/e4-table-create.md): description (name,
+/// version, comment), columns and data managers as tuples
+/// (`ffi_ms_write::ColumnArgs`, `ManagerArgs`), `table.info` (type,
+/// subtype, readme), `nrows` rows; returned open for writing.
+#[pyfunction]
+#[pyo3(signature = (path, desc, columns, managers, info, nrows, big_endian=false, multifile=false))]
+#[allow(clippy::too_many_arguments)]
+fn ms_create_table(
+    py: Python<'_>,
+    path: &str,
+    desc: (String, String, String),
+    columns: Vec<ColumnArgs>,
+    managers: Vec<ManagerArgs>,
+    info: (String, String, String),
+    nrows: u64,
+    big_endian: bool,
+    multifile: bool,
+) -> PyResult<MsWriter> {
+    let spec = rang_core::ms_create::TableSpec {
+        desc_name: desc.0,
+        desc_version: desc.1,
+        desc_comment: desc.2,
+        columns: column_descs(columns).map_err(PyValueError::new_err)?,
+        managers: manager_specs(managers),
+        info,
+        big_endian,
+        multifile,
+        ..Default::default()
+    };
+    writer(detach(py, || {
+        rang_core::ms_create::create_table(path, &spec, nrows)
+    }))
+}
+
+/// python-casacore's `default_ms(path, desc, dminfo)`.
+#[pyfunction]
+fn ms_default_ms(
+    py: Python<'_>,
+    path: &str,
+    columns: Vec<ColumnArgs>,
+    managers: Vec<ManagerArgs>,
+) -> PyResult<MsWriter> {
+    let extra = column_descs(columns).map_err(PyValueError::new_err)?;
+    let managers = manager_specs(managers);
+    writer(detach(py, || {
+        rang_core::ms_create::default_ms(path, &extra, &managers)
+    }))
+}
+
+/// python-casacore's `default_ms_subtable(name, path, desc, dminfo)`.
+#[pyfunction]
+fn ms_default_ms_subtable(
+    py: Python<'_>,
+    name: &str,
+    path: &str,
+    columns: Vec<ColumnArgs>,
+    managers: Vec<ManagerArgs>,
+) -> PyResult<MsWriter> {
+    let extra = column_descs(columns).map_err(PyValueError::new_err)?;
+    let managers = manager_specs(managers);
+    writer(detach(py, || {
+        rang_core::ms_create::default_ms_subtable(name, path, &extra, &managers)
+    }))
+}
+
+/// The MAIN table of a CASA calibration table with `nrows` rows.
+#[pyfunction]
+#[allow(clippy::too_many_arguments)]
+fn ms_caltable_main(
+    py: Python<'_>,
+    path: &str,
+    vis_cal: String,
+    float_param: bool,
+    ms_name: String,
+    pol_basis: String,
+    casa_version: String,
+    nrows: u64,
+) -> PyResult<MsWriter> {
+    let cal = rang_core::caltable::CalTable {
+        vis_cal,
+        float_param,
+        ms_name,
+        pol_basis,
+        casa_version,
+    };
+    let spec = rang_core::caltable::main_spec(&cal).map_err(|e| PyValueError::new_err(e.0))?;
+    writer(detach(py, || {
+        rang_core::ms_create::create_table(path, &spec, nrows)
+    }))
+}
+
+/// A calibration subtable (`OBSERVATION`, `ANTENNA`, `FIELD`,
+/// `SPECTRAL_WINDOW`, `HISTORY`) with `nrows` rows.
+#[pyfunction]
+fn ms_caltable_subtable(py: Python<'_>, path: &str, name: &str, nrows: u64) -> PyResult<MsWriter> {
+    let spec = rang_core::caltable::subtable_spec(name).map_err(|e| PyValueError::new_err(e.0))?;
+    writer(detach(py, || {
+        rang_core::ms_create::create_table(path, &spec, nrows)
+    }))
+}
+
+/// The array records a table's rows reference: (file, offset, element
+/// bits) (`ms_write::array_records`, the alignment-gap mask).
+#[pyfunction]
+fn ms_array_records(py: Python<'_>, path: &str) -> PyResult<Vec<(String, u64, u32)>> {
+    detach(py, || rang_core::ms_write::array_records(path)).map_err(|e| PyOSError::new_err(e.0))
+}
+
+/// Read cells of a table without writing (`ms_write::read_cells`).
+#[pyfunction]
+fn ms_read_cells<'py>(
+    py: Python<'py>,
+    path: &str,
+    name: &str,
+    start: u64,
+    count: u64,
+) -> PyResult<Vec<CellTuple<'py>>> {
+    let cells = detach(py, || {
+        rang_core::ms_write::read_cells(path, name, start, count, None)
+    })
+    .map_err(|e| PyOSError::new_err(e.0))?;
+    Ok(cells.into_iter().map(|c| cell_tuple(py, c)).collect())
 }

 /// The extension module `rang._core`.
@@ -1332,5 +1544,12 @@ fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
     m.add_class::<MsTable>()?;
     m.add_class::<MsWriter>()?;
     m.add_function(wrap_pyfunction!(ms_serialisation_check, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_create_table, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_default_ms, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_default_ms_subtable, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_caltable_main, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_caltable_subtable, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_read_cells, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_array_records, m)?)?;
     Ok(())
 }
diff --git a/core/src/lib.rs b/core/src/lib.rs
index 4df6968..fcc6932 100644
--- a/core/src/lib.rs
+++ b/core/src/lib.rs
@@ -22,6 +22,7 @@

 pub mod aipsio;
 pub mod blosc;
+pub mod caltable;
 pub mod clean;
 pub mod closure;
 pub mod correct;
@@ -40,7 +41,9 @@ pub mod fused;
 pub mod grid;
 pub mod jones;
 pub mod ms;
+pub mod ms_create;
 pub mod ms_desc;
+pub mod ms_schema;
 pub mod ms_write;
 pub mod predict;
 pub mod robust;
```
