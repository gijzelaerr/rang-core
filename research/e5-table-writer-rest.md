# Rang core, task E5: the rest of the casacore table writer

Task E5 of [big-plan.md](big-plan.md): what E3
([e3-table-writer.md](e3-table-writer.md)) and E4
([e4-table-create.md](e4-table-create.md)) deferred, written by the core's
own table writer and byte-compared against casacore 3.8.1 (python-casacore
in the pinned `rang-ms-reader:local` image). Branch `e5-table-writer-rest`
from `368e8ca`. Protocol frozen 2026-10-30 in the commit that adds this
file, before any E5 code. Before freezing, one scratch measurement was made
(the determinism inventory below); nothing else was measured.
Status: **implemented and measured (frozen check `outputs/e5-20261031-01`):
criteria 4, 5 and 6 pass; 1, 2 and 3 fail as frozen.** 21 of 23 cases are
byte-identical to casacore 3.8.1 (2 of them identical but the masked
MultiFile header tail); the 2 others (I-arrays, I-rows-all) differ only in
the value bytes of ISM arrays casacore reserves and never writes, which
hold uninitialised heap memory: casacore's own `MALLOC_PERTURB_` run differs
from its first run in every one of those bytes (post hoc check), so no
writer can match them (criteria 1 and 3). Criterion 2 fails on the same
arrays (python-casacore reads casacore's garbage in I-rows-all) and on the
frozen expectation for MemoryStMan columns, which python-casacore read as
zeros and uninitialised values instead of raising (the core refuses).
IncrementalStMan, the last StandardStMan row, variable-shape and
multi-hypercube TiledShapeStMan, TiledDataStMan and MemoryStMan creation,
big-endian and MultiFile tables are all written; C-ABI creation is skipped
(P7 removed the ctypes path). Archive:
[results/e5-table-writer-rest.json](results/e5-table-writer-rest.json).

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

## What is implemented

As planned, with these additions (all measured by the frozen run):

- `core/src/ism.rs` (new, ≈2,070 lines): the IncrementalStMan as casacore
  3.8.1 runs it. `ISMColumn::putValue` (last row put, the equal-value exit
  with `ObjCompare` semantics: IEEE equality, signed zeros equal, NaN
  unequal; contraction with equal neighbours; an interval split by a
  duplicate of the old value; `putFromRow` into every later bucket),
  `addData`/`replaceData`/`putData` with bucket splits (`simpleSplit` at
  the end of the table, else `split` with `getSplit` in casacore's unsigned
  arithmetic), `ISMBucket` (data, index of 32- or 64-bit row numbers,
  `removeData`/`insertData`/`shiftLeft`), `ISMIndex`, the header (version 5
  with the endian flag, version 4 big-endian), the index after the last
  bucket, `addRow64`, `removeRow64` (empty buckets freed; at no rows
  `recreate` truncates the file and the array file), and `ISMIndColumn`
  (`getArrayPtr`/`putArrayPtr`/`setShape` with their caching of the value
  last read, so a single-row interval gets a new array on every put and the
  old one a reference count of 0; `handleCopy`/`handleRemove` change
  reference counts in the version-1 array file). casacore's `BucketCache` is
  modelled with its LRU slots and its one scratch buffer `its_Buffer`,
  through which every bucket is read and written: a written bucket keeps
  the buffer's older bytes after its index, and an empty bucket 0 is written
  when the cache is made (`resync` flushes). Columns: scalars of every type,
  scalar strings, Direct numeric, Bool and string arrays, FixedShape and
  variable-shape indirect arrays; indirect string arrays refuse (E6). New
  tables may bind columns to an IncrementalStMan (SPEC BUCKETSIZE and
  PERSCACHESIZE; 32768-byte buckets from a SPEC, `ISMBase::init`'s size for
  `createDefaultSubtables`' POINTING); E4's empty-POINTING writer is gone.
- `core/src/multifile.rs` (new, ≈520): the MultiFile version-2 header
  (parse, serialise; packed block lists, free list, CRC and continuation
  lists), extraction of logical files, and a container the writer packs on
  every flush. Logical files live in `table.mf.rang-staging/` inside the
  table while it is open (removed at close); a file gets its blocks when
  casacore would first write it: an IncrementalStMan's file and any array
  file when the manager is created, tile files and a tiled manager's header
  at its flush (in manager order), a StandardStMan's file at its first
  flush; blocks past a file's end are zero; the change counter counts packs
  that changed anything. `table.dat` gets ColumnSet version -3 with storage
  option 0 (MultiFile) and the 4 MiB block size.
- `core/src/ms_write.rs` (E3/E4): byte order everywhere (StandardStMan
  header version 2 without the flag when big-endian, buckets, string slots,
  8-byte array offsets, values; tiled headers version 1 when big-endian and
  big-endian tiles; `ArrayFile` with byte order, version and reference
  counts); StandardStMan `recreate` at its last row (`init` again with the
  sizing state, a new file, index, string handler and array file; the
  `table.dat` blob rewritten on every flush); TiledShapeStMan `setShape`
  (find or add a hypercube with its own tile file, extend it) and the full
  `updateRowMap`, so variable-shape rows get a hypercube when their shape is
  first set, rows may stay without one, and a new shape for a row that has
  one is refused as casacore refuses it; tiled cell reads; the
  IncrementalStMan, MemoryStMan (no file; values checked and dropped; reads
  refuse) and TiledDataStMan (the header of a manager without hypercubes;
  values refuse, E6) managers; `put_cell` (`ArrayColumn::put`, which differs
  from a one-row `putcol` for ISM indirect columns); `describe`;
  `read_cells` for ISM, tiled, TiledDataStMan, MemoryStMan and MultiFile
  tables; `read_column` falling back to `read_cells`; `array_records` over
  ISM intervals; serialisation checks of ISM files, TiledDataStMan headers
  and MultiFile tables.
- `core/src/ms_create.rs`: IncrementalStMan, MemoryStMan, TiledDataStMan,
  variable-shape TiledShapeStMan, big-endian and MultiFile creation;
  hypercolumn definitions (`TableDesc::defineHypercolumn`: the private
  keyword `Hypercolumn_<name>` with ndim, data, coord, id, and the columns'
  data-manager type and group).
- `python/rang/core_ms_write.py`: columns from the writer on every open (no
  task E reader), `putcell` through `put_cell`, `create_table`/`table` with
  `endian` and `multifile`, `tabledefinehypercolumn`, `describe`;
  `read_cells` without the task E reader.
- `examples/oracle_ms_rest.py` (frozen cases; modes `write`, `write-mf`,
  `readback`, `read-column`), `examples/check_ms_rest.py` (steps `oracle`,
  `cases`, `determinism`, `readback`, `refusals`, `regress`,
  `serialisation`, `summary`, and the post hoc `posthoc`),
  `tests/test_e5_table_writer_rest.py` (7 tests). E3's and E4's tests that
  asserted E5 refusals now check what E5 writes
  (`tests/test_core_ms_write.py`, `tests/test_e4_table_create.py`).

## Measured result (2026-10-31)

Run `outputs/e5-20261031-01`, all steps by one script, every step timed in
`timing/` with logs in `logs/`: `oracle`, `oracle-twin`, `oracle-perturb`
(`MALLOC_PERTURB_=85`), `cases`, `determinism`, `readback`, `refusals`,
`regress`, `serialisation`, `summary` → `result.json`, then `posthoc`
(labelled post hoc). Code: commit `c194e3f`. Inputs read in place, never
written: the fixture, the LUNO export, E3's and E4's oracle runs.
Development runs preceded it in scratch (deleted); the frozen run is the
first in `outputs/`.

**Criterion 1, byte identity: fails as frozen (21 of 23 cases pass).**

| Case | Files | Bytes | Against casacore 3.8.1 | Core (ms) | casacore (ms) |
| --- | ---: | ---: | --- | ---: | ---: |
| I-scalars | 4 | 114,585 | identical | 406.3 | 408.3 |
| I-arrays | 5 | 44,813 | **differs**: `table.f0i` 440 bytes (395 in gaps, 45 in unwritten array values) | 17.1 | 24.7 |
| I-rows | 4 | 117,553 | identical | 3.7 | 11.3 |
| I-rows-all | 5 | 4,733 | **differs**: `table.f0i` 34 bytes (21 in gaps, 13 in unwritten array values) | 3.8 | 10.3 |
| I-fixture | 93 | 41,254,182 | identical | 3.7 | 14.8 |
| I-fixture-pointing | 93 | 41,254,950 | identical | 3.9 | 17.4 |
| I-pointing | 59 | 183,192 | identical | 47.1 | 178.3 |
| I-create | 6 | 69,825 | identical | 3.2 | 16.8 |
| S-remove-all | 5 | 3,282 | identical | 4.0 | 21.1 |
| S-remove-all-luno | 59 | 245,594 | identical | 4.3 | 15.2 |
| T-var | 6 | 4,959 | identical | 4.3 | 15.3 |
| T-reshape | 6 | 4,959 | both refuse; identical | 2.6 | 4.7 |
| T-multishape | 62 | 203,404 | identical | 45.6 | 134.0 |
| T-fixture-add | 93 | 44,399,910 | identical | 7.3 | 89.5 |
| T-fixture-flagcat | 94 | 42,384,586 | identical | 5.4 | 29.4 |
| D-tds | 4 | 1,343 | identical | 2.7 | 10.0 |
| D-tds-rows | 4 | 1,343 | identical | 3.9 | 10.8 |
| B-new | 10 | 47,721 | identical | 3.7 | 14.6 |
| B-write | 10 | 50,370 | identical | 4.2 | 10.8 |
| B-rows | 5 | 37,342 | identical | 3.0 | 14.2 |
| M-new | 4 | 2,158 | identical | 3.8 | 13.5 |
| F-new | 4 | 25,167,758 | identical but 6 masked MultiFile header-tail bytes | 25.6 | 74.0 |
| F-write | 4 | 25,167,758 | identical but 54 masked MultiFile header-tail bytes | 14.7 | 23.4 |

Every `table.lock` sync record is equal. casacore's times are its own
process's (container start excluded), the core's the checker's.

The differing bytes outside the gap mask in I-arrays and I-rows-all are the
values of arrays casacore reserves (`StManArrayFile::putRes` writes only the
last byte) and never writes: in I-arrays the first of the two records every
`putcell` on a single-row interval of the variable-shape column makes
(`ISMIndColumn::putArrayPtr` reserves a new array through a fresh
`StIndArray` whose shape is unknown, then the value put replaces it; the
first is left with reference count 0), in I-rows-all the FixedShape array
`ISMIndColumn::addRow` reserves for row 0 after the manager was recreated,
which no case value overwrites. casacore leaves `FilebufIO`'s buffer there,
uninitialised heap memory (fragments of text in the frozen copy); the core
writes zeros. Every record header and every written value is equal.
**Post hoc (labelled; not a change to the criterion)**: all 45 and 13 such
bytes are bytes where casacore's `MALLOC_PERTURB_` run differs from its first
run (`posthoc.json`: 0 not covered).

**Criterion 2, read-back: fails as frozen.** 111 tables (the 23 cases with
their subtables on both sides), 63,990 defined cells: python-casacore reads
every core-written table exactly as casacore's except I-rows-all's FF
column, whose cells hold the uninitialised values above in casacore's copy
(python-casacore returns them) and zeros in the core's; the core reads
casacore's tables column-exactly as python-casacore does (every case,
MultiFile and big-endian included); casacure 3.8.35 reads 18 cases' tables
alike on both sides and cannot open D-tds, D-tds-rows (`unsupported
data-manager type TiledDataStMan`), M-new (`MemoryStMan`), F-new and
F-write (it looks for `table.f0`: no MultiFile support). MemoryStMan: the
frozen expectation was that both sides raise; measured, python-casacore in
a fresh process reads the reopened M-new's MemoryStMan columns as 15 zeros
(Int) and as uninitialised doubles (Direct Double [3]), from casacore's
copy and the core's alike; the core refuses (`a MemoryStMan column holds no
data once its table is closed`). The inventory saw a raise
(`MSMColumn::findExt`) because it read another column first.

**Criterion 3, determinism: fails as frozen.** The core's outputs of every
case are identical between two runs and a `MALLOC_PERTURB_=85` run (no
mask). casacore's twin run equals its first except masked bytes (F-new 29,
F-write 2 MultiFile header-tail bytes); its perturbed run differs in masked
bytes (I-fixture-pointing 96 gap bytes of POINTING's `table.f1i`, F-new and
F-write 4,193,963 header-tail bytes) and outside the masks in I-arrays (601
bytes) and I-rows-all (51 bytes): the unwritten array values of criterion 1
and their gaps.

**Criterion 4, E3 and E4 unchanged: passes.** E3's checker against
`outputs/e3-20261030-01`: 20 cases identical, 4 identical but padding;
round trip and serialisation pass. E4's `cases` against
`outputs/e4-20261030-01/oracle`: 18 of 18 identical or gaps only.
`tests/test_core_ms_write.py`, `tests/test_e4_table_create.py` and
`tests/test_e5_table_writer_rest.py` pass (25 passed, 1 skipped before the
archive existed).

**Criterion 5, refusals: passes.** TiledCellStMan creation, TiledDataStMan
values and a MultiHDF5 storage option raise errors naming E6; no table is
left, and the refused TiledDataStMan put changes no data file.

**Criterion 6, serialisation identity: passes**: 111 tables, 115
StandardStMan files, 43 tiled headers (TiledDataStMan included), 66
IncrementalStMan files (header, index and every bucket) and 2 MultiFile
headers (their logical files extracted and checked too).

## Deviations

- Protocol scope 6 (C ABI) skipped as the protocol allows: P7 removed the
  ctypes path.
- The `readback` step reads MemoryStMan columns in separate containers as
  frozen; the frozen expectation "both raise" was wrong (criterion 2,
  measured above). The core keeps refusing them.
- `put_cell` became its own binding: python-casacore's `putcell` is
  `ArrayColumn::put`, which for ISM indirect columns reads the row's shape
  first and so reserves arrays differently from a one-row `putcol`.
- `table.mf.rang-staging/` exists inside a MultiFile table while the core
  has it open (removed at close and on drop).

## Open items

- MultiFile block order is modelled for logical files of at most one block
  (4 MiB) and without StandardStMan cache evictions during a session; larger
  files are written correctly (readable, header consistent) but may not get
  casacore's block numbers. Header continuation blocks are refused (E6).
- TiledDataStMan hypercubes (values) and reads of them: E6 (python-casacore
  cannot add one, so there is no oracle). Indirect string arrays in an
  IncrementalStMan: E6.
- The core writes zeros where casacore leaves uninitialised memory (gaps,
  unwritten array values, the MultiFile header tail); readers of casacore's
  tables see garbage there (I-rows-all), readers of the core's see zeros.
- MemoryStMan values in a session are checked and dropped (a read in the
  same session refuses).
- Speed was not tuned; the core is 1–12× faster than python-casacore on
  these cases (I-scalars, 2,000 rows with 40 edits, is equal).

## Timings

| Date | Tool / stage | Input | Wall | Notes |
| --- | --- | --- | ---: | --- |
| 2026-10-30 | `git clone --depth 1 --branch v3.8.1 casacore` | | 4.6 s | format reference, scratch |
| 2026-10-30 | `git clone --depth 1 --branch v3.8.1 python-casacore` | | 2.0 s | storage option, `tabledefinehypercolumn` |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin pip casacure==3.8.35` | worktree | 83.6 s | builds the extension |
| 2026-10-30 | determinism inventory, python-casacore 3.8.1, 8 containers | 9 probes × 4 runs | 4.4–5.3 s | pre-freeze scratch, three passes |
| 2026-10-30 | MultiFile gap probe, 4 containers | 2 tables | ~5 s | pre-freeze scratch, not timed precisely |
| 2026-10-30 | python-ptrace syscall trace of an ISM creation in the container | 1 table | >120 s, stopped | abandoned (too slow); the host's strace needs a newer glibc than the image |
| 2026-10-30 | `cargo check --release --all-targets` (core) | `core/` | 2–7 s | incremental, about 15 runs |
| 2026-10-30/31 | `maturin develop --release` | extension | 50–235 s | ten builds |
| 2026-10-31 | `cargo test` (core, 128 tests) | `core/` | 33 s | build included |
| 2026-10-31 | clippy (core, extension), fmt, ruff, `git diff --check` | repo | 5.8–14 s | |
| 2026-10-31 | `pytest` of the E3, E4 and E5 table tests | | 4.7–5.0 s | 25 passed, 1 skipped |
| 2026-10-31 | oracle `write` + `write-mf` (`oracle`, `-twin`, `-perturb`) | 23 cases | 2.4 / 2.2 / 2.3 s | containers; 217 MB each |
| 2026-10-31 | `check_ms_rest.py cases` | 23 cases | 1.1 s | |
| 2026-10-31 | `check_ms_rest.py determinism` | 2 × 23 cases | 2.8 s | |
| 2026-10-31 | `check_ms_rest.py readback` | 111 tables | 10.3 s | container 4.3 s, plus 4 MemoryStMan containers |
| 2026-10-31 | `check_ms_rest.py refusals` | 3 attempts | 0.1 s | |
| 2026-10-31 | `check_ms_rest.py regress` | E3 and E4 oracles | 6.9 s | |
| 2026-10-31 | `check_ms_rest.py serialisation` | 111 tables | 0.2 s | |
| 2026-10-31 | `check_ms_rest.py posthoc` | 2 cases | 0.1 s | post hoc |
| 2026-10-31 | `bash tools/check-all.sh` | repo | 327 s | PASS: root 23, core 128 Rust tests; pytest 655 passed, 6 skipped (137 s); log `outputs/e5-20261031-check-all.log` |

## For the coordinator

- Shared files, committed on the branch this time (the appendix has the
  exact diff against `368e8ca`):
  - `core/src/lib.rs`, alphabetical: `pub mod ism;` and `pub mod multifile;`
    (no new dependency, `Cargo.lock` unchanged).
  - `core/py/src/lib.rs`: `MsWriter.put_cell`; functions `ms_describe`,
    `ms_serialisation_check_e5`, `ms_multifile_check`; the `hypercolumns`
    keyword argument of `ms_create_table` with the `HypercolumnArgs` type;
    their three `m.add_function` lines.
  - Also changed, not shared files of this task but E3's and E4's tests: the
    tests that asserted E5 refusals now check what E5 writes
    (`tests/test_core_ms_write.py::test_formerly_deferred_writes_work`;
    `tests/test_e4_table_create.py`: `test_formerly_deferred_managers_are_created`,
    `test_tiled_data_needs_a_hypercolumn`,
    `test_variable_tiled_big_endian_and_multifile_are_created`, POINTING rows
    in `test_default_ms_has_the_subtables_and_info`).
  - `python/rang/core.py`, `core_cli.py`, README and the research index are
    not touched.
- STATE paragraph: "E5 (the rest of the core table writer) measured:
  rang's core now writes IncrementalStMan columns (values and rows, the MS
  bookkeeping columns and POINTING), removes the last row of a
  StandardStMan, writes variable-shape and multi-hypercube TiledShapeStMan
  columns (rows without a hypercube, the fixture's FLAG_CATEGORY, new rows
  of a CASA MS), creates TiledDataStMan (no hypercube) and MemoryStMan
  tables, and writes big-endian and MultiFile tables, all as casacore 3.8.1
  does. 21 of 23 frozen cases are byte-identical (2 with the masked
  MultiFile header tail); 2 ISM cases differ only in array values casacore
  reserves and never writes, which hold uninitialised heap memory
  (casacore's own MALLOC_PERTURB_ run differs there, post hoc), so criteria
  1-3 fail as frozen; python-casacore reads the reopened MemoryStMan
  columns as zeros and uninitialised values where the protocol expected an
  error (the core refuses). E3 and E4 unchanged, refusals (E6:
  TiledDataStMan values, TiledCellStMan, MultiHDF5) and serialisation pass;
  C-ABI creation skipped (P7 removed ctypes). `outputs/e5-20261031-01`,
  `research/results/e5-table-writer-rest.json`."
- `research/README.md` index line: "[e5-table-writer-rest.md](e5-table-writer-rest.md)
  — E5: IncrementalStMan, last-row removal, tiled hypercubes, TiledDataStMan
  and MemoryStMan creation, big-endian and MultiFile tables in the core
  writer; 21 of 23 cases byte-identical to casacore 3.8.1, the rest
  casacore's uninitialised memory (measured)."
- `research/tool-timings.md`: the Timings rows above and the check-all row
  below.
- `research/big-plan.md`: E5 done 2026-10-31 (`e5-table-writer-rest.md`);
  what is left is E6 (below).
- README: `rang.core_ms_write` writes every storage manager of a CASA MS
  (IncrementalStMan included), big-endian and MultiFile tables.
- Upstream observations (all non-RATT, for
  `research/non-ratt-observations.md`; nothing RATT, caracal-pipeline or
  saopicc):
  - casacore 3.8.1 (defect): `ISMIndColumn::putArrayPtr` puts a single-row
    interval's value through `StIndArray::setShape` on a freshly read
    `StIndArray` whose shape is not known yet, so it reserves a new array on
    every put even when the shape is unchanged; the old array stays in the
    file with reference count 0 (I-arrays: two records per `putcell`).
  - casacore 3.8.1 (defect): arrays reserved by `StManArrayFile::putRes` and
    never written hold uninitialised `FilebufIO` buffer memory; for an ISM
    FixedShape indirect column after a `recreate` (all rows removed, rows
    added) readers get that memory as cell values (I-rows-all FF; the
    values differ between runs).
  - casacore 3.8.1 (defect): `MultiFile::writeHeader` writes block 0 from a
    `MemoryIO` whose bytes past the header are uninitialised (4 MiB of heap
    memory per header write; 4,193,963 bytes change under
    `MALLOC_PERTURB_`).
  - casacore 3.8.1 (note): a reopened MemoryStMan table's columns read as
    zeros (Int) or uninitialised values (Direct Double array) in a fresh
    process, but raise `MSMColumn::findExt - rownr 0 ... out of range` after
    another column was read, and the process then aborts at exit
    (`terminate called`).
  - python-casacore 3.8.1 (note): no storage-option argument (MultiFile only
    through aipsrc `table.storage.option`, read via `CASARCFILES`); no
    `TiledDataStManAccessor`, so a TiledDataStMan cannot get a hypercube.
  - casacure 3.8.35 (note): cannot open TiledDataStMan, MemoryStMan or
    MultiFile tables (it looks for `table.f0` in a MultiFile table).
- DF-IO-CT should pick up: nothing new for calibration tables (they are
  StandardStMan only); `default_ms` POINTING now takes rows; MS writes may
  now touch every MAIN column of a CASA MS (the bookkeeping columns are ISM),
  and new rows of a CASA MS (variable-shape TiledShapeStMan) are written.
- E6 (what stays out, refused with errors naming E6): TiledDataStMan
  hypercubes and their values (needs an oracle that adds hypercubes, e.g. a
  C++ program against casacore), indirect string arrays in an
  IncrementalStMan, TiledCellStMan, MultiHDF5, MultiFile headers with
  continuation blocks and MultiFile block order for logical files of more
  than one block or with StandardStMan cache evictions during a session;
  C-ABI creation if a C caller ever needs it.
- Ignored output: `outputs/e5-20261031-01` (3.3 GB: `e3/` 1.7 GB, E3's
  re-run, can be deleted; `dumps/` 337 MB can be trimmed to its JSON; the
  three `oracle*` and three `core*` copies 213-217 MB each, keep `oracle/`
  and `core/`) and `outputs/e5-20261031-check-all.log`.
- Scratch `~/Build/tmp/20261030-e5` (the casacore and python-casacore
  clones, the inventory, development runs, the python-ptrace download) is
  deleted at the end of the task.

## Appendix: the wiring diff

`git diff 368e8ca -- core/src/lib.rs core/py/src/lib.rs` at the branch head
(committed on the branch):

```diff
diff --git a/core/py/src/lib.rs b/core/py/src/lib.rs
index 0fae781..e0f8779 100644
--- a/core/py/src/lib.rs
+++ b/core/py/src/lib.rs
@@ -1523,6 +1523,44 @@ fn ms_serialisation_check(
     Ok((c.tables, c.ssm_files, c.tiled_headers, c.failures))
 }

+/// `serialise(parse(x)) == x` for the MultiFile header of a table's
+/// `table.mf` (research/e5-table-writer-rest.md): the failures (empty when
+/// it round-trips).
+#[pyfunction]
+fn ms_multifile_check(py: Python<'_>, path: &str) -> Vec<String> {
+    match detach(py, || rang_core::multifile::check(path)) {
+        Ok(true) => Vec::new(),
+        Ok(false) => vec![format!("{path}/table.mf header differs")],
+        Err(e) => vec![format!("{path}/table.mf: {}", e.0)],
+    }
+}
+
+/// A table's row count and columns (name, type code, is array), read
+/// without writing (research/e5-table-writer-rest.md).
+#[pyfunction]
+fn ms_describe(py: Python<'_>, path: &str) -> PyResult<(u64, rang_core::ms_write::ColumnList)> {
+    detach(py, || rang_core::ms_write::describe(path)).map_err(|e| PyOSError::new_err(e.0))
+}
+
+/// `serialise(parse(x)) == x` as `ms_serialisation_check`, with the
+/// IncrementalStMan files (research/e5-table-writer-rest.md): (tables,
+/// StandardStMan files, tiled headers, IncrementalStMan files, failures).
+#[pyfunction]
+fn ms_serialisation_check_e5(
+    py: Python<'_>,
+    path: &str,
+) -> PyResult<(usize, usize, usize, usize, Vec<String>)> {
+    let c = detach(py, || rang_core::ms_write::check_serialisation(path))
+        .map_err(|e| PyOSError::new_err(e.0))?;
+    Ok((
+        c.tables,
+        c.ssm_files,
+        c.tiled_headers,
+        c.ism_files,
+        c.failures,
+    ))
+}
+
 /// A casacore table open for writing (research/e3-table-writer.md); holds
 /// casacore's write lock until `close`.
 #[pyclass(unsendable)]
@@ -1607,6 +1645,21 @@ impl MsWriter {
         ))
     }

+    /// Write one cell as `ArrayColumn::put` does (`putcell`): native bytes,
+    /// `shape` in casacore order (research/e5-table-writer-rest.md).
+    fn put_cell(
+        &mut self,
+        py: Python<'_>,
+        name: &str,
+        row: u64,
+        shape: Vec<i64>,
+        data: PyReadonlyArray1<'_, u8>,
+    ) -> PyResult<()> {
+        let bytes = data.as_slice()?;
+        let w = self.get()?;
+        detach(py, || w.put_cell(name, row, &shape, bytes)).map_err(|e| PyOSError::new_err(e.0))
+    }
+
     fn put_strings(&mut self, name: &str, start: u64, values: Vec<String>) -> PyResult<()> {
         self.get()?
             .put_strings(name, start, &values)
@@ -1772,6 +1825,9 @@ impl MsWriter {

 type CellTuple<'py> = (i32, Vec<i64>, Bound<'py, PyBytes>, Vec<String>);

+/// A hypercolumn definition: name, ndim, data, coordinate and id columns.
+type HypercolumnArgs = (String, u32, Vec<String>, Vec<String>, Vec<String>);
+
 fn cell_tuple(py: Python<'_>, cell: rang_core::ms_write::Cell) -> CellTuple<'_> {
     use rang_core::ms_write::Cell;
     match cell {
@@ -1791,7 +1847,7 @@ fn writer(w: rang_core::ms::Result<TableWriter>) -> PyResult<MsWriter> {
 /// (`ffi_ms_write::ColumnArgs`, `ManagerArgs`), `table.info` (type,
 /// subtype, readme), `nrows` rows; returned open for writing.
 #[pyfunction]
-#[pyo3(signature = (path, desc, columns, managers, info, nrows, big_endian=false, multifile=false))]
+#[pyo3(signature = (path, desc, columns, managers, info, nrows, big_endian=false, multifile=false, hypercolumns=Vec::new()))]
 #[allow(clippy::too_many_arguments)]
 fn ms_create_table(
     py: Python<'_>,
@@ -1803,6 +1859,7 @@ fn ms_create_table(
     nrows: u64,
     big_endian: bool,
     multifile: bool,
+    hypercolumns: Vec<HypercolumnArgs>,
 ) -> PyResult<MsWriter> {
     let spec = rang_core::ms_create::TableSpec {
         desc_name: desc.0,
@@ -1813,6 +1870,18 @@ fn ms_create_table(
         info,
         big_endian,
         multifile,
+        hypercolumns: hypercolumns
+            .into_iter()
+            .map(
+                |(name, ndim, data, coord, id)| rang_core::ms_create::Hypercolumn {
+                    name,
+                    ndim,
+                    data,
+                    coord,
+                    id,
+                },
+            )
+            .collect(),
         ..Default::default()
     };
     writer(detach(py, || {
@@ -1953,6 +2022,9 @@ fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
     m.add_class::<MsTable>()?;
     m.add_class::<MsWriter>()?;
     m.add_function(wrap_pyfunction!(ms_serialisation_check, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_serialisation_check_e5, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_describe, m)?)?;
+    m.add_function(wrap_pyfunction!(ms_multifile_check, m)?)?;
     m.add_function(wrap_pyfunction!(ms_create_table, m)?)?;
     m.add_function(wrap_pyfunction!(ms_default_ms, m)?)?;
     m.add_function(wrap_pyfunction!(ms_default_ms_subtable, m)?)?;
diff --git a/core/src/lib.rs b/core/src/lib.rs
index 8c77d69..36e95f7 100644
--- a/core/src/lib.rs
+++ b/core/src/lib.rs
@@ -40,12 +40,14 @@ pub mod ffi_wgridder;
 pub mod fluxstd;
 pub mod fused;
 pub mod grid;
+pub mod ism;
 pub mod jones;
 pub mod ms;
 pub mod ms_create;
 pub mod ms_desc;
 pub mod ms_schema;
 pub mod ms_write;
+pub mod multifile;
 pub mod predict;
 pub mod robust;
 pub mod solve;
```

Blank context lines of the diff are written without their leading space
(`git diff --check`); `git apply --ignore-whitespace` applies it.
