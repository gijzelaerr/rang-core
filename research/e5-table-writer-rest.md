# Rang core, task E5: the rest of the casacore table writer

Task E5 of [big-plan.md](big-plan.md): what E3
([e3-table-writer.md](e3-table-writer.md)) and E4
([e4-table-create.md](e4-table-create.md)) deferred, written by the core's
own table writer and byte-compared against casacore 3.8.1 (python-casacore
in the pinned `rang-ms-reader:local` image). Branch `e5-table-writer-rest`
from `368e8ca`. Protocol frozen 2026-10-30 in the commit that adds this
file, before any E5 code. Before freezing, one scratch measurement was made
(the determinism inventory below); nothing else was measured.
Status: **protocol frozen; not yet implemented.**

The user's decision (2026-10-30) stands: the core reads and writes every
format of the tools it replaces ([ecosystem-survey.md](ecosystem-survey.md)
section 5.3). A reimplementation of a file format is not a scientific
contribution (AGENTS.md); no archived result changes because of it.

## Scope

In priority order (the task's order); each item is frozen as cases below.
An item that is not implemented by the frozen run is refused with an error
naming E6, and its cases count as failed and recorded as frozen; no case is
dropped.

1. **IncrementalStMan writes**, little-endian (big-endian under item 4):
   values (`putcol`, `putcell`) and rows (`addrows`, `removerows`) of
   existing and new ISM managers, every column kind casacore's ISM stores:
   scalars of every numeric type and Bool, scalar strings, Direct arrays
   (numeric, Bool, String), indirect arrays (variable-shape and FixedShape;
   ISM's version-1 array file with reference counts). Step for step as
   `ISMColumn::putValue` (last row put, equal-previous/next contraction,
   interval duplication, `putFromRow` into later buckets), `ISMBucket`
   (data and index layout, 32-bit or 64-bit row numbers, `simpleSplit` and
   the general split with `getSplit`), `ISMIndex`, `ISMBase` (`init`
   bucket sizing, the header version 5 with the endian flag, the index
   after the last bucket, `addRow64`, `removeRow64` with `recreate` at 0
   rows) and `ISMIndColumn` (shared arrays, `handleCopy`/`handleRemove`
   reference counts). casacore's `BucketCache` with its scratch buffer is
   modelled (PERSCACHESIZE 1 by default), because a bucket on disk holds
   the scratch buffer's old bytes after its index. New tables may bind
   columns to an IncrementalStMan (E4 refused it). This covers the MS
   bookkeeping columns casacore and CASA bind to ISM (the fixture binds 12
   MAIN columns, one ISM each, and 6 POINTING columns to one ISM) and
   `default_ms`'s POINTING (E4 writes it empty).
2. **Removing the last row of a StandardStMan** (`SSMBase::removeRow64`
   at one row: the manager is recreated, `recreate`), then adding rows
   again.
3. **TiledShapeStMan rows without a hypercube and more than one
   hypercube**: variable-shape columns (a row gets a hypercube, or extends
   one of its shape, when its shape is first set, as
   `TiledShapeStMan::setShape`/`findHypercube`/`extendHypercube` and
   `updateRowMap` do), rows left without a value (cube 0), new rows on a
   variable-shape manager (the fixture's DATA, FLAG, WEIGHT_SPECTRUM...),
   the fixture's FLAG_CATEGORY (every row without a hypercube) given
   values, a multi-shape DATA column. casacore refuses a new shape for a
   row that has one (`ArrayColumn::put` conformance error, measured below):
   both sides must refuse. **TiledDataStMan**: creation as python-casacore
   can make it (a hypercolumn defined in the description with
   `tabledefinehypercolumn`, no hypercube); python-casacore cannot add a
   hypercube (`TiledDataStManAccessor` is not exposed), so no oracle has
   TiledDataStMan data: data writes are refused naming E6.
4. **Big-endian tables** (`table.dat` endian flag 0; StandardStMan,
   IncrementalStMan, the tiled managers and the array files in canonical
   big-endian form) on this little-endian host: creation, values, rows and
   keywords. The oracle call is `pt.table(name, desc, nrow, dminfo=...,
   endian="big")`.
5. **MemoryStMan** (creation: no data file, the `table.dat` entry; values
   live only in the session) and **MultiFile tables** (one `table.mf`
   container holding the managers' files, casacore's `MultiFile` version 2
   format: header block, per-file block maps, free list, 4 MiB blocks by
   default): creation, in-place values and new rows. python-casacore has
   no storage-option argument (no `StorageOption` in its sources), so the
   oracle selects MultiFile through casacore's aipsrc: `CASARCFILES=<rc>`
   with the line `table.storage.option: multifile` (block size from
   `table.storage.blocksize`, default 4 MiB, so a small table's container
   is 4 MiB per file plus the header block).
6. **The C ABI**: not done. Task P7 removed the ctypes path
   ([p7-architecture.md](p7-architecture.md)); `rang.core` refuses
   `RANG_CORE_BACKEND=ctypes` and `RANG_CORE_LIB`, so no Python caller
   would use C-ABI creation. Recorded, skipped, as the task allows.

Not in scope (refused, naming E6): TiledCellStMan, MultiHDF5, Adios2 and
other storage managers; TiledDataStMan data; `removecols`/`renamecol`.

## Determinism inventory (measured before freezing, scratch)

python-casacore 3.8.1 ran nine probes four times (two plain runs,
`MALLOC_PERTURB_=85`, `=170`; script and output
`~/Build/tmp/20261030-e5/inv`, 4.4–5.3 s for the eight containers): a new
ISM table (BUCKETSIZE 1024, seven column kinds, 300 rows, edits, rows added
and removed), ISM `putcol` on a fixture copy, `default_ms` POINTING rows,
StandardStMan emptied by `removerows` and refilled, a variable-shape
TiledShapeStMan (two shapes, a row left undefined, rows added), an empty
TiledDataStMan, a big-endian table (StandardStMan, ISM, TiledShapeStMan),
a MemoryStMan table, a MultiFile table. **Twin runs are identical. Under
`MALLOC_PERTURB_` exactly two files differ**: the new ISM table's
`table.f0i` (172 bytes, the alignment gaps of the version-1 array file,
E3's exception) and the MultiFile container `table.mf` (4,193,963 bytes:
the header block from the end of the header, 341 bytes, to the end of the
block, which casacore fills from an uninitialised `MemoryIO` buffer).
Inside the MultiFile container the array file's alignment gaps are zeros
and stable (a second probe with Float [3] arrays: 225 header bytes and
nothing else differ; the same table without MultiFile differs in 76 gap
bytes of `table.f0i`). Also measured: casacore refuses a new shape for a
TiledShapeStMan row that has one; a TiledDataStMan table needs the
hypercolumn definition (`RecordInterface: field Hypercolumn_TDS is
unknown` without it); a MemoryStMan table reopened has its rows but
reading a MemoryStMan column raises `MSMColumn::findExt - rownr 0 ... out
of range`, and the process then aborts (`terminate called`) at exit.
casacure's `getdminfo` lists the fixture's 12 MAIN ISMs under one name
(python-casacore: one manager per column, names `Array_ID`, `EXPOSURE`,
...).

## Oracles (frozen)

- **python-casacore 3.8.1** in `rang-ms-reader:local` as E3 and E4
  (`docker run --rm --network none --user $(id -u):$(id -g)`, inputs
  read-only, one writable output directory): `examples/oracle_ms_rest.py`
  performs every frozen case with python-casacore's API (one close per
  session, no reads inside a write session: values that depend on an input
  are prepared before the session from a separate read-only open, or come
  from the seeded generator, seed 20261030) and stores the values in
  `values/<case>.npz`; MultiFile cases run in their own container with
  `CASARCFILES` set as above. A `readback` mode dumps every column cell by
  cell (definedness included), keywords, column keywords and `table.info`;
  MemoryStMan columns are read in a separate process each (casacore
  aborts), recording "raises" or the values.
- **casacure 3.8.35** (host venv), second read-back oracle where it reads
  the format (recorded per case; formats it cannot read are listed, not
  failed).
- **The core**: `rang.core_ms_write` writes the same sequences with the
  stored values; the core reads casacore's tables through the writer's
  read path (`read_cells`, extended by E5 to ISM arrays and strings,
  TiledShapeStMan rows without a hypercube, big-endian and MultiFile
  tables).
- **Comparators** as E4: byte comparison of every file of the table tree
  (`table.lock` from offset 260, the sync record), column comparison as
  `compare_arrays`/`compare_strings` (dtype, shape, bytes; NaN payloads and
  signed zeros count; strings by value) plus definedness.

**The two exceptions, named and masked explicitly; nothing else is
masked:**

1. *Alignment gaps of `table.fNi`* (E3's exception, E4's rule), extended to
   version-1 array files: walk the record chain from offset 16, each record
   at the 8-byte-aligned end of the previous one; a record is (version 1:
   a 4-byte reference count, then) ndim and the dimensions as Int (the
   file's byte order) and the values (Bool `ceil(n/8)` bytes, else `n ×`
   element size), the element size being that of the column whose row
   references the record (StandardStMan rows; ISM intervals, each distinct
   offset once), or for a record no row references any more that of the
   column the case names for it. The chain must end exactly at the end of
   the file, the files must have the same length, and every byte inside a
   record must be equal; only the gap bytes (at most 7 after each record)
   may differ.
2. *The MultiFile header tail*: in `table.mf`, the bytes of block 0 from
   the header length (the Int64 at bytes 32–39, big-endian) to the end of
   block 0 (the block size, the Int64 at bytes 40–47). Every other byte of
   the container (header, block maps, data blocks with their zero padding,
   the array files' gaps inside it) must be equal.

## Frozen cases

Each case is one sequence of python-casacore calls on the oracle side and
the same sequence through `rang.core_ms_write` on the core side; values
from the seeded generator ("runs": values drawn from five per column,
repeated in runs of 1 to 9 rows, so that ISM intervals form, merge and
split). The fixture is `outputs/tv-caracal-wsl-20261029-01/original.ms`
(read in place, copies written), the LUNO export
`outputs/luno-solve-20261029-02/work.ms`.

IncrementalStMan:

- **I-scalars** (2,000 rows): one ISM `ISM` with SPEC BUCKETSIZE 1024
  (many buckets and splits) holding Bool, uChar, Short, Int, uInt, Int64,
  Float, Double, Complex, DComplex and a variable String (lengths 0 to
  12); `putcol` of each column in description order (runs); then 40
  seeded `putcell` edits (fixed rows and columns, values from the runs'
  alphabets: equal to the previous, the next, both, inside an interval,
  of a single-row interval).
- **I-arrays** (400 rows): one ISM, BUCKETSIZE 2048: Direct Double [3],
  Direct Bool [5], Direct String [2], variable Double (ndim 1, indirect),
  FixedShape Float [2, 2] (indirect); `putcol` of the Direct columns and
  of the FixedShape column (runs of cells), `putcell` of the variable
  column every third row (shape by row), then `putcell` edits inside
  intervals of the variable and FixedShape columns.
- **I-rows**: on a copy of casacore's I-scalars: `addrows(150)`, `putcol`
  of the new rows of Int, Double and String; `removerows` of rows 0, 5,
  1200 to 1499 (empties buckets) and the last row.
- **I-rows-all**: on a copy of casacore's I-arrays: `removerows` of every
  row (the manager is recreated), `addrows(10)`, `putcol` of the Direct
  Double column and `putcell` of the variable column.
- **I-fixture**: on a fixture copy: `putcol` of SCAN_NUMBER, STATE_ID,
  FIELD_ID, TIME, INTERVAL, EXPOSURE (runs; TIME non-decreasing) and of
  ARRAY_ID with its current values (the equal-value exit), `putcell` of
  FIELD_ID at row 70.
- **I-fixture-pointing**: on a fixture copy, its POINTING (ISM: ANTENNA_ID,
  INTERVAL, NAME, NUM_POLY, TIME_ORIGIN, TRACKING; StandardStMan the
  rest): `putcol` of NAME, TRACKING and INTERVAL, `addrows(8)` and
  `putcol` of the new rows of every column, `removerows([0, 1, 2, 3])`.
- **I-pointing**: `default_ms(path)`, then its POINTING: `addrows(20)`,
  `putcol` of every column (DIRECTION and TARGET [2, 1] in casacore order).
- **I-create**: a new table with two managers from a dminfo, an ISM with
  default SPEC (scalars, a String) and an ISM with PERSCACHESIZE 3 (Double,
  Int), 120 rows, `putcol` of all (runs).

StandardStMan:

- **S-remove-all**: a new 50-row table (Int, variable String, variable
  Double ndim 1), `putcol`/`putcell` of all, `removerows` of every row,
  `addrows(5)`, `putcol` of Int.
- **S-remove-all-luno**: on a copy of the LUNO export MAIN (all
  StandardStMan): `removerows` of every row.

Tiled:

- **T-var** (20 rows): a TiledShapeStMan `TSS` (tile [4, 8, 4]) holding a
  variable-shape Float (ndim 2) and Bool (ndim 2) column of one
  hypercolumn; `putcell` of the Float column on every row but row 5 with
  shape [8, 4] or [16, 2] (NumPy order) by row, of the Bool column on row
  0; `addrows(5)`, `putcell` of row 22.
- **T-reshape**: on a copy of casacore's T-var: `putcell` of row 0 with a
  new shape. Both sides must refuse; files unchanged.
- **T-multishape**: `default_ms(path, desc, dminfo)` with DATA (Complex,
  ndim 2, variable) in a TiledShapeStMan (tile [4, 32, 8]); `addrows(30)`,
  `putcell` of DATA rows 0–14 with shape [64, 4] and rows 15–29 with
  [32, 4] (NumPy order), then `putcol` of rows 0–14 again.
- **T-fixture-add**: on a fixture copy: `addrows(10)`, then `putcol` of the
  new rows of DATA, FLAG, WEIGHT_SPECTRUM, SIGMA_SPECTRUM, WEIGHT, SIGMA,
  UVW, TIME, ANTENNA1, ANTENNA2, SCAN_NUMBER, FLAG_ROW (cell shapes taken
  from the input before the session); FLAG_CATEGORY left without a value.
- **T-fixture-flagcat**: on a fixture copy: `putcell` of FLAG_CATEGORY at
  rows 3 and 4 (the fixture's FLAG shape with a third axis of 1).
- **D-tds**: TiledDataStMan creation with `tabledefinehypercolumn` (Float
  [4, 8], hypercolumn `TDS`), nrow 0; and **D-tds-rows** the same with
  nrow 10. No values (none can be written by python-casacore).

Big-endian:

- **B-new** (30 rows, `endian="big"`): StandardStMan Int, Double, variable
  String, Bool, Direct Complex [2], variable Double ndim 1; a
  TiledShapeStMan Float [4, 8] (tile [4, 8, 4]); a TiledColumnStMan Double
  [3] (tile [3, 16]); an ISM Int and String; `putcol`/`putcell` of all, a
  table keyword.
- **B-write**: on a copy of casacore's B-new: `putcol` in place of Int,
  String, the tiled and ISM columns, `putcell` of the variable column with
  a new shape, a column keyword, `addrows(5)` and `putcol` of the new rows.
- **B-rows** (50 rows, `endian="big"`): StandardStMan and ISM only;
  `putcol` of all, `removerows([1, 2, 30, 49])`.

MemoryStMan and MultiFile:

- **M-new** (10 rows): a MemoryStMan `MSM` (Int, Direct Double [3]) and a
  StandardStMan Int; `putcol` of all, `addrows(5)`, close. Read-back: the
  StandardStMan column and the row count read as casacore's; a MemoryStMan
  column read raises in both.
- **F-new** (30 rows, MultiFile): StandardStMan Int, variable String,
  variable Double ndim 1, variable Float ndim 1 of 3 elements (alignment
  gaps); TiledShapeStMan Float [4, 8]; ISM Int; `putcol`/`putcell` of all.
- **F-write**: on a copy of casacore's F-new: `putcol` in place of Int,
  String, the tiled and ISM columns, `addrows(5)`, `putcol` of the new
  rows.

## Acceptance criteria (frozen)

Checked by `examples/check_ms_rest.py` (host) with the oracle's modes in
the containers, written to `result.json`; every criterion gates.

1. **Byte identity.** For every case, every file of the core's table tree
   (subtables included) equals casacore's byte for byte and every
   `table.lock` sync record is equal, except only the two masked
   exceptions above. Refusal cases (T-reshape): both sides raise and the
   files equal the input.
2. **Read-back.** python-casacore reads every column (and cell
   definedness), keyword, column keyword and `table.info` of every
   core-written table exactly as it reads casacore's copy (MemoryStMan
   columns: both raise); casacure likewise where it reads the format
   (formats it cannot read are listed); the core reads casacore's tables
   column-exactly as python-casacore does.
3. **Determinism.** The core's outputs of every case are byte-identical
   between two runs and a run under `MALLOC_PERTURB_=85` (no mask).
   casacore's second run equals its first and its `MALLOC_PERTURB_=85` run
   differs only in masked bytes (recorded as measured).
4. **E3 and E4 unchanged.** `examples/check_ms_writer.py` steps `cases`,
   `roundtrip` and `serialisation` against `outputs/e3-20261030-01` give
   E3's frozen verdicts (20 cases identical, 4 identical but gaps; round
   trip and serialisation pass); `examples/check_ms_create.py cases`
   against `outputs/e4-20261030-01` gives E4's (18 cases identical or gaps
   only); `tests/test_core_ms_write.py` and `tests/test_e4_table_create.py`
   pass, with E4's E5 refusals updated to what E5 now writes.
5. **Refusals.** Each item left out raises an error naming E6 and changes
   no file: TiledDataStMan values, TiledCellStMan, MultiHDF5 (aipsrc
   `multihdf5`), and any frozen case's item not implemented.
6. **Serialisation identity.** `serialise(parse(x)) == x` for every
   `table.dat`, StandardStMan header and index, tiled header, ISM header,
   index and bucket (data and index part) and MultiFile header (up to its
   length) of every oracle-written table.

Reported, not gated: wall time of every core write next to casacore's,
bytes written.

Failures are recorded as measured; any later fix is a new run labelled
post hoc, and the frozen result stays in this file.

## Implementation plan

- `core/src/ism.rs` (new): the IncrementalStMan model (header, index,
  buckets, columns, cache and scratch buffer, splits, rows, the version-1
  array file through E3's `ArrayFile`), endian-aware from the start.
- `core/src/multifile.rs` (new): the MultiFile container (header, block
  maps, free list, per-file buffers, `MFFileIO` semantics) and a logical
  file I/O used by the managers.
- `core/src/ms_write.rs`: the managers on a per-file I/O with an endian
  flag (StandardStMan, tiled managers, array files), TiledShapeStMan
  hypercubes and row maps, StandardStMan `recreate`, the ISM and
  MemoryStMan managers in `TableWriter`, `read_cells` for the new kinds,
  `array_records` over ISM intervals.
- `core/src/ms_create.rs`: ISM, MemoryStMan, TiledDataStMan, big-endian
  and MultiFile creation; private keywords (hypercolumn definitions).
- `core/py/src/lib.rs` (coordinator's file; committed on the branch and
  listed verbatim): any new bindings.
- `python/rang/core_ms_write.py`: columns from the writer on every open
  (the task E reader does not read MultiFile tables or ISM arrays), reads
  through `read_cells` where the reader cannot, `endian`, `multifile` and
  hypercolumn definitions in `create_table`/`table`,
  `tabledefinehypercolumn`.
- `examples/oracle_ms_rest.py` (containers), `examples/check_ms_rest.py`
  (host), `tests/test_e5_table_writer_rest.py` (skips without Docker, the
  images, the oracle outputs or the binding).

Every tool run is timed and listed under Timings.
