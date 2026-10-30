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
Status: **protocol frozen; not implemented.**

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
