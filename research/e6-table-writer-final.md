# Rang core, task E6: the last of the casacore table writer

Task E6 of [big-plan.md](big-plan.md): what E5
([e5-table-writer-rest.md](e5-table-writer-rest.md)) refused with errors
naming E6, written by the core's own table writer and byte-compared against
casacore. Branch `e6-table-writer-final` from `17653e4`. Protocol frozen
2026-10-31 in the commit that adds this file, before any E6 code. Before
freezing, scratch probes were made (listed below, labelled pre-freeze);
nothing else was measured.
Status: **implemented and measured (frozen run `outputs/e6-20261031-01`,
code `7721e96`): criteria 2, 4, 5, 6 and 7 pass; 1 and 3 fail as frozen
on one case.** 20 of 21 cases are byte-identical to casacore (17
identical, among them F-cont with its continuation blocks; F-multi,
F-multi-write and F-free identical but the masked MultiFile header tail);
IS-arrays differs only in alignment-gap bytes of its array file, but the
frozen gap walk does not reach the end of the file (string bodies a later
put left unreferenced; amendment 3), so its gaps are not masked
(criterion 1) and casacore's own twin and perturbed runs differ there
(criterion 3). Post hoc (labelled), the walk with those bodies consumed
masks all 677 differing bytes. TiledDataStMan hypercubes, TiledCellStMan,
IncrementalStMan string arrays, default tile shapes and MultiFile block
order with continuation headers are written as casacore writes them;
casacore 3.7.1 (C++) and 3.8.1 (python-casacore) write the cross-version
table identically; MultiHDF5 is refused as not supported (two casacore
runs differ); no writer error names E6. W4-4 (2-D string keywords in C
order) is absorbed. Archive:
[results/e6-table-writer-final.json](results/e6-table-writer-final.json).

The user's decision (2026-10-30) stands: the core reads and writes every
format of the tools it replaces ([ecosystem-survey.md](ecosystem-survey.md)
section 5.3). A reimplementation of a file format is not a scientific
contribution (AGENTS.md); no archived result changes because of it.

## Scope

1. **TiledDataStMan hypercubes** (`TiledDataStManAccessor::addHypercube`
   and `extendHypercube`): hypercube creation (a non-extensible cube goes to
   the shared tile file `table.f<N>_TSM0` at its current length, an
   extensible one gets its own `table.f<N>_TSM<k>`), extension, the row,
   cube and position maps of `TiledDataStMan::updateRowMap`, the hypercube
   records (`TSMCube::values_p`: id values and coordinate vectors, with
   `initCoordinates`/`extendCoordinates`), data values of the data columns,
   coordinate and id column reads and coordinate puts (`TSMCoordColumn`),
   rows added to the table and then to an existing hypercube, hypercubes of
   more than one row axis (`getHypercube`'s position over the axes after
   the cell axes).
2. **TiledCellStMan**: creation, one hypercube per row (`addRow64`; a
   FixedShape column gives every row its cube at once), a variable-shape row
   gets a cube when its shape is first set and a new cube appended to
   `table.f<N>_TSM0` when its shape changes (casacore allows it, the old
   space is left), rows without a value, rows added; removing rows refuses as
   in casacore.
3. **IncrementalStMan indirect string arrays** (`ISMIndColumn` with
   `StIndArray` strings: `StManArrayFile::putShape(String*)` reserves the
   offsets and zeroes them, `put(String*)` appends the bodies at the end of
   the file in batches of 4096 and then writes the offsets), variable-shape
   and FixedShape, cells of more than 4096 strings, edits inside intervals,
   rows added and removed (`handleCopy`/`handleRemove`, `copyArrayString`).
4. **MultiFile**: header continuation blocks (`writeRemainder`, the two
   alternating continuation sets, `readRemainder` when reading), logical
   files of more than one block, and block allocation in casacore's order:
   `MultiFileBase::write` extends a file (`extendVF`, free blocks taken
   from the tail of the descending free list first) at every write reaching
   past its last block, which also marks the header changed; `deleteFile`
   (a logical file reopened with `ByteIO::New`: every tiled manager's header
   at each flush, a recreated StandardStMan or IncrementalStMan) frees its
   blocks (`doTruncateFile`, sorted descending, `truncateIfNeeded` shrinking
   the container); the header is written at the end of each table flush if
   anything set it changed. The writes are those of casacore's managers in
   casacore's order: StandardStMan and IncrementalStMan bucket-cache
   evictions during a session, cache flushes in slot order, index buckets,
   headers; array files written directly (`MFFileIO`, no `FilebufIO`
   buffer); tile files at their manager's flush.
5. **MultiHDF5**: decided out of scope (below); the core refuses it with a
   "not supported" error giving the reason.
6. **Every E6 refusal** of E5 either works or carries a final "not
   supported" message with its reason: also the TiledShapeStMan without a
   default tile shape (`TSMCube::adjustTileShape` and
   `TiledStMan::makeTileShape` ported), TiledColumnStMan and TiledCellStMan
   without one, and the generic messages for other data managers.

## Pre-freeze probes (scratch, 2026-10-31)

Scripts and outputs in `~/Build/tmp/20261031-e6/probe` (deleted at the end
of the task). Each probe ran twice and once with `MALLOC_PERTURB_=85`.

- python-casacore 3.8.1 (`rang-ms-reader:local`) **can** make every item
  but TiledDataStMan hypercubes: a TiledCellStMan from a dminfo (SPEC
  DEFAULTTILESHAPE or none; variable shapes, a reshape of a row, rows
  added), IncrementalStMan variable and FixedShape string arrays with a cell
  of 5,000 strings, TiledShapeStMan and TiledColumnStMan without
  DEFAULTTILESHAPE (casacore chose tiles [4, 3, 2731] for a [4, 3] cell and
  [4, 16, 512] for a [4, 16] column), MultiFile tables with a block size
  from aipsrc (`table.storage.blocksize`, no minimum in `StorageOption`).
  Twins identical; under `MALLOC_PERTURB_` only the array file's gaps (34
  bytes of the string-array table) and the MultiFile header tail differ.
- A MultiFile table with 512-byte blocks and three flushes (the frozen case
  F-cont below) reached header continuation: header 787, 1073 and 1097
  bytes, one then two continuation blocks, block 0 entirely header. Twins
  and the perturbed run are identical, but the single continuation block of
  the first write ends with stale heap bytes (fragments of a freed AipsIO
  buffer: names of logical files and a `RecordDesc`) past its chunk:
  memory casacore never initialised, stable here only by chance of the
  allocator.
- The C++ oracle image (below) made a TiledDataStMan with two hypercubes,
  one extended twice; twins and the perturbed run identical.
- **MultiHDF5**: casacore 3.7.1 in the oracle image links
  `libhdf5_serial.so.103` (HDF5 1.10.10) and makes a MultiHDF5 table
  (`table.mfh5`, 8,404,680 bytes for a 20-row StandardStMan table). Two
  runs a second apart differ in 2 bytes (offsets 1981 and 3285: the low
  bytes of object modification times in seconds). The format is not
  reproducible between two casacore runs.
- `git diff v3.7.1 v3.8.1` of `tables/DataMan`, `casa/IO`,
  `tables/Tables/ColumnSet.cc`, `PlainTable.cc`, `StorageOption.cc`:
  `PtrBlock` → `Block` renames, `ftruncate` error checks, the
  `DataManInfo` loop index renamed, and `PlainTable::changeTiledDataOnly`
  (3.8.1, only when a program calls it; nothing in python-casacore or this
  task does). No change to any format written here.

## MultiHDF5 decision (frozen)

Out of scope. The oracle image has it, but the format is not documented
well enough to write byte-identically: a MultiHDF5 container is an HDF5
file written by libhdf5 1.10.10, whose layout (object headers, B-trees,
free-space and metadata-cache flush order) is libhdf5's internal behaviour,
not the HDF5 file format specification, and whose object headers carry
modification times, so two casacore runs differ (measured above). No
pure-Rust writer reproduces libhdf5, and the core takes no C library
dependency. The core refuses to create (`multifile="multihdf5"`) or open a
MultiHDF5 table with an error that says "MultiHDF5 ... not supported" and
gives this reason; the refusal is gated (criterion 6).

## Oracles (frozen)

- **O-py: python-casacore 3.8.1** in `rang-ms-reader:local` as E3–E5
  (`docker run --rm --network none --user $(id -u):$(id -g)`, inputs
  read-only, one writable output directory): `examples/oracle_ms_final.py`
  performs the cases marked O-py with python-casacore (one close per
  session; no reads inside a write session; values from the seeded
  generator, seed 20261031, stored in `values/<case>.npz`). MultiFile cases
  run each in their own container with `CASARCFILES` naming an aipsrc file
  with `table.storage.option: multifile` and the case's
  `table.storage.blocksize`. Modes `write`, `write-mf`, `readback` as E5.
- **O-cpp: casacore 3.7.1** (KERN-10 `casacore-dev=3.7.1-1kern1`,
  `libcasa-tables8=3.7.1-1kern1`, g++ 13 of Ubuntu 24.04) in
  `rang-casacore-cpp:3.7.1` built by `tools/oracles/casacore-cpp/build.sh`
  from `ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852`
  (the A-FLAG and O-CASA base), the image id, size and every deb version
  recorded in the run's `image.json`; run with `--network none`. The
  program `tools/oracles/casacore-cpp/oracle.cc` performs the cases marked
  O-cpp (TiledDataStMan hypercubes, which python-casacore cannot add; the
  cross-version case; the MultiHDF5 refusal input). Its values come from
  `examples/oracle_ms_final.py prepare` (the same seeded generator, written
  as raw little-endian files per case and as `values/<case>.npz` for the
  core side).
- **casacure 3.8.35** (host venv), second read-back oracle where it opens
  the format (recorded per case; formats it cannot open are listed, not
  failed).
- **The core**: `rang.core_ms_write` performs the same sequences with the
  stored values (new: `addhypercube`, `extendhypercube` on a table, in
  casacore axis order, values as an ordered dict; TiledCellStMan in
  dminfo; ISM string arrays; MultiFile block sizes); the core reads
  casacore's tables through its read path (`read_cells`, extended to
  TiledDataStMan data, coordinate and id columns, TiledCellStMan, ISM
  string arrays and MultiFile continuation headers).
- **Which casacore each case is compared with**: O-py cases with 3.8.1,
  O-cpp cases with 3.7.1. The cross-version case X-371 runs C-var's
  sequence with O-cpp and is compared byte for byte with O-py's C-var
  (criterion 7); the version diff above finds no format change.

## Masks (frozen)

Byte comparison of every file of the table tree as E5 (`table.lock` from
offset 260, the sync record). Only these bytes may differ:

1. **Alignment gaps of `table.fNi`**, E5's rule extended to string arrays.
   The walk starts at offset 16. At each position: if it is the start of a
   string body that an offset of a string-array record references (in the
   oracle's file), the body (a 4-byte length L, then L bytes) is consumed
   and the walk continues at its end, unaligned; otherwise the position is
   rounded up to a multiple of 8 (the skipped bytes, at most 7, are gap
   bytes) and a record is parsed there: (version 1: a 4-byte reference
   count,) ndim and the dimensions as Int in the file's byte order, then the
   values: Bool `ceil(n/8)` bytes, string arrays `4n` bytes of offsets,
   else `n ×` the element size of the column whose row references the
   record, or for a record no row references the case's orphan element
   size. The walk must end exactly at the end of the file and the files
   must have the same length; only gap bytes may differ.
2. **MultiFile header tails** (`table.mf`; the header is canonical
   big-endian: length at bytes 32–39, block size at 40–47, first
   continuation block at 8–15):
   a. header not longer than a block: block 0 from the header length to
      the end of block 0 (E5's mask);
   b. header continuation: the two continuation lists and `ncont_used`
      (the last 8 bytes of the header) name each set's blocks; the active
      set is the one whose first block is the first continuation block.
      Masked: in a set with `ncont_used` 1, its one used block from byte
      8 + C to its end, C being the header length minus the block size
      for the active set and 0 for the other set (the length of its chunk
      is not recorded; casacore leaves uninitialised heap memory after a
      single chunk, measured above); blocks of a set past its `ncont_used`
      (reserved, not rewritten by the set's last write) entirely. Whether
      the masked continuation bytes are in fact equal is reported, not
      gated.
3. Nothing else. Array values casacore reserves and never writes (E5's
   finding) are not masked; the cases avoid them.

## Frozen cases

Values from the seeded generator (seed 20261031): "runs" as E5 (values
drawn from five per column, repeated in runs of 1 to 9 rows); strings of 0
to 12 characters unless stated. Shapes of python-casacore calls in NumPy
order, of hypercube calls in casacore order.

TiledDataStMan (O-cpp, casacore 3.7.1; the core with
`addhypercube`/`extendhypercube`):

- **D-cubes** (11 rows): DATA Float FixedShape [4, 8], FLAG Bool FixedShape
  [4, 8], FREQ Double FixedShape [4] (coordinate of axis 0), TIME Double
  scalar (coordinate of axis 2), ID Int scalar (id); hypercolumn `TDS`
  (ndim 3; data DATA, FLAG; coordinates FREQ, "", TIME; id ID), one
  TiledDataStMan `TDS` holding the five. `addHypercube([4, 8, 3],
  [4, 4, 2], {ID 7, FREQ f, TIME t3})`, `addHypercube([4, 8, 0], [2, 8, 2],
  {ID 9})`, `extendHypercube(2, {ID 9, TIME t2})`, `extendHypercube(4,
  {ID 9})`, `addHypercube([4, 8, 2], [4, 8, 1], {ID 11, FREQ f', TIME
  t2'})`; `putcol` of DATA and FLAG (rows 0–10), `putcell` of TIME at row 4
  and of FREQ at row 3.
- **D-reopen**: on a copy of casacore's D-cubes: `addrows(4)`,
  `extendHypercube(4, {ID 9, TIME t4})`, `putcol` of DATA and FLAG rows
  11–14.
- **D-multiaxis** (0 rows): DATA Complex ndim 2 (variable shape), X Double
  scalar (coordinate of axis 2), TIME Double scalar (coordinate of axis 3);
  hypercolumn `TDM` (ndim 4; data DATA; coordinates "", "", X, TIME; no id);
  `addrows(9)`, `addHypercube([4, 2, 3, 0], [4, 2, 2, 2], {X x3})`,
  `extendHypercube(3, {TIME t3})`, `putcol` of DATA (cells [4, 2]),
  `putcell` of X at row 4.
- **D-be**: D-cubes' sequence in a big-endian table.

TiledCellStMan (O-py):

- **C-var** (6 rows): D Double and F Float, variable shape, ndim 2, one
  TiledCellStMan `TCS` with DEFAULTTILESHAPE [4, 4]; `putcell` D row 0
  (3, 4), F row 0 (3, 4), D row 2 (5, 8), D row 3 (2, 2), D row 0 (2, 3)
  (a new shape), `addrows(2)`, `putcell` D row 7 (2, 2), F row 7 (2, 2).
- **C-fixed** (4 rows): D Double FixedShape (3, 5), DEFAULTTILESHAPE
  [2, 2]; `putcol`, `addrows(3)`, `putcol` of rows 4–6.
- **C-write**: on a copy of casacore's C-var: `putcell` D row 2 (5, 8) (in
  place), D row 4 (6, 6), D row 3 (4, 4) (a new shape), `addrows(1)`,
  `putcell` D row 8 (1, 7).
- **C-be**: C-var's sequence in a big-endian table.
- **C-notile** (3 rows): D Double ndim 2 variable, no DEFAULTTILESHAPE;
  `putcell` row 1 (20, 20) and row 2 (200, 300).
- **X-371** (O-cpp): C-var's sequence and values by casacore 3.7.1.

IncrementalStMan string arrays (O-py):

- **IS-arrays** (300 rows): one ISM `ISM` BUCKETSIZE 2048: K Int, SV String
  ndim 1 variable (indirect), SF String FixedShape (2, 2) (indirect);
  `putcol` K (runs) and SF (runs of cells), `putcell` SV every third row
  (1 to 4 strings), `putcell` edits of SF at rows 10, 11, 50, 51, 52, 120,
  200, 201 and of SV at rows 3, 4, 30, 99; `addrows(20)`, `putcol` SF of
  rows 300–319, `putcell` SV rows 300 and 310; `removerows` of rows 0, 5
  and 150–199.
- **IS-big** (10 rows): one ISM, SV String ndim 1 variable; `putcell` row 0
  with 5,000 strings, row 1 with 9,000, row 2 with 3, row 0 with 4,097 (a
  new shape), row 5 with 4,096.

Tiled managers without a default tile shape (O-py):

- **T-notile** (4 rows): TiledShapeStMan `TSS` without DEFAULTTILESHAPE, D
  Double ndim 2 variable; `putcell` rows 0–3 with (3, 4), (20, 20), (3, 4),
  (1, 1000); `addrows(2)`, `putcell` row 5 (7, 9).
- **T-notile-fixed** (50 rows): TiledShapeStMan without DEFAULTTILESHAPE,
  F Float FixedShape (16, 4); `putcol`.
- **T-notile-column** (50 rows): TiledColumnStMan without DEFAULTTILESHAPE,
  D Double FixedShape (16, 4); `putcol`, `addrows(30)`, `putcol` of rows
  50–79.

MultiFile (O-py, block size from aipsrc):

- **F-multi** (block 4096; 2,000 rows): StandardStMan `A` (BUCKETSIZE 512,
  PERSCACHESIZE 2: I Int, D Double, S String), StandardStMan `B`
  (BUCKETSIZE 1024, PERSCACHESIZE 2: L Int64, V Double ndim 1 variable, an
  array file), IncrementalStMan `M` (BUCKETSIZE 512: M Int); `putcol` I,
  L, D, `putcell` V every third row (1 + row mod 7 values), `putcol` S, M
  (runs); `flush`; `addrows(1000)`; `putcol` I, L, D, M of rows 2000–2999,
  `putcell` V every fifth new row.
- **F-multi-write**: on a copy of casacore's F-multi: `putcol` I rows
  0–499, `putcell` V row 3 (its shape).
- **F-cont** (block 512; 400 rows; the pre-freeze probe): StandardStMan
  `A` (BUCKETSIZE 512, PERSCACHESIZE 2: I Int, V Double ndim 1, S String),
  TiledShapeStMan `T` (DEFAULTTILESHAPE [8, 4]: T Float ndim 1 variable),
  IncrementalStMan `M` (BUCKETSIZE 512: M Int); `putcol` I, `putcell` V
  every row (1 + row mod 9 values) and T every third row (1 + row mod 8),
  `putcol` M; `flush`; `putcol` S, `addrows(100)`, `putcol` I of the new
  rows, `putcell` T of the new rows (1 + row mod 13); `flush`; `putcol` M
  of all rows.
- **F-free** (block 1024; 200 rows): StandardStMan `A` (BUCKETSIZE 512: I
  Int, V Double ndim 1), IncrementalStMan `M` (M Int); `putcol` I, M,
  `putcell` V every row (1 + row mod 5); `flush`; `removerows` of every
  row; `addrows(50)`, `putcol` I, M, `putcell` V rows 0–49.
- **F-default** (casacore's default 4 MiB blocks; 9,000 rows):
  StandardStMan W Double Direct (64), I Int, IncrementalStMan M Int;
  `putcol` W, I, M; `addrows(1000)`, `putcol` W and I of the new rows.

Refusals:

- **R-tcsm-remove**: `removerows([1])` on a copy of casacore's C-var: both
  refuse; files unchanged.
- **R-mfh5**: the core's `create_table(..., multifile="multihdf5")` and an
  open (for writing and for reading) of O-cpp's MultiHDF5 table (H-mfh5: a
  20-row StandardStMan table, as the probe) refuse with "not supported";
  no table is left, no file changes.
- **R-other**: a column bound to a data manager the core does not write
  (`Adios2StMan` in the core's `create_table`) refuses with "not
  supported".

## Acceptance criteria (frozen)

Checked by `examples/check_ms_final.py` (host) with the oracles' modes in
their containers, written to `result.json`; every criterion gates.

1. **Byte identity.** For every case, every file of the core's table tree
   equals casacore's byte for byte and every `table.lock` sync record is
   equal, except only the masked bytes above. Refusal cases: both sides
   raise and the files equal the input.
2. **Read-back.** python-casacore reads every column (and cell
   definedness), keyword, column keyword and `table.info` of every
   core-written table exactly as it reads casacore's copy; casacure
   likewise where it opens the format (formats it cannot open are listed);
   the core reads casacore's tables column-exactly as python-casacore does.
3. **Determinism.** The core's outputs of every case are byte-identical
   between two runs and a run under `MALLOC_PERTURB_=85` (no mask).
   casacore's second run equals its first and its `MALLOC_PERTURB_=85` run
   differs only in masked bytes (recorded as measured; H-mfh5 is excluded
   and its run-to-run difference recorded).
4. **E3, E4 and E5 unchanged.** E3's and E4's checkers give their frozen
   verdicts as in E5's criterion 4; `examples/check_ms_rest.py cases`
   against `outputs/e5-20261031-01/oracle` gives E5's frozen case verdicts
   (21 identical or masked only; I-arrays and I-rows-all differ in exactly
   the bytes E5 measured); the E3, E4, E5 and T1 tests pass, with E5's E6
   refusals updated to what E6 writes.
5. **Serialisation identity.** `serialise(parse(x)) == x` for every
   TiledDataStMan header with hypercubes, TiledCellStMan header,
   TiledShapeStMan header and MultiFile header (continuation included, up
   to its length) of every oracle-written table, and E5's serialisation
   check of every table.
6. **Refusals.** R-tcsm-remove, R-mfh5 and R-other as stated; no error
   message of the writer (Rust sources under `core/src`, Python under
   `python/rang`) names E6.
7. **Cross-version identity.** X-371 (casacore 3.7.1) equals O-py's C-var
   (casacore 3.8.1) byte for byte, masks above only.

Reported, not gated: wall time of every core write next to casacore's,
bytes written, whether the masked continuation bytes were equal.

Failures are recorded as measured; any later fix is a new run labelled
post hoc, and the frozen result stays in this file.

## Amendments before the frozen run (deviations, 2026-10-31)

Made during implementation, before the frozen run; the frozen text above is
unchanged.

1. **C-fixed**: the frozen `putcol` of rows 4–6 makes casacore 3.8.1 raise
   (`TSMShape::offset - shapes do not conform`, found in a development
   oracle run): a ranged `putcol` of a TiledCellStMan goes through
   `TSMDataColumn::accessColumnCells`, which reads a row axis
   (`rowpos(lastAxis)`) a TiledCellStMan cube does not have (its position
   is the cell shape only; reading past an `IPosition`, undefined
   behaviour). A whole-column `putcol` and `putcell` work. The new rows are
   put with `putcell` one by one instead; the core writes a ranged `putcol`
   of a TiledCellStMan correctly (not compared with casacore).
2. **K-arrays (task W4-4, absorbed by E6 at the coordinator's request after
   the freeze)**: the wave-4 review (finding W4R-03) found the core storing
   2-D string-array keywords in Fortran element order. A case is added:
   O-py, 2 rows, table keywords S23 (string 2×3), D23 (Double 2×3), I32
   (Int 3×2), S222 (string 2×2×2) and column keywords of I: CS (string 3×2)
   and CF (Float 2×4); byte comparison under criterion 1, read-back under
   criterion 2 (python-casacore's and, added for this, casacure's keywords).
   Measured before the fix on the development oracle: `table.dat` differs
   in 61 bytes; after: identical. Numeric-array keywords were already in C
   order (the bytes of a C-contiguous array with the reversed shape).
3. **Mask 1 and orphaned string bodies**: in development the frozen walk
   does not reach the end of IS-arrays' `table.f0i`: a string record put
   again in place (`ISMIndColumn::putArrayPtr` keeps the record of the last
   row put when its shape is unchanged) leaves its first put's bodies after
   it, which no offset references. The frozen rule is kept (IS-arrays is
   expected to fail criterion 1 as frozen); a post hoc step walks again
   with those bodies consumed (`check_ms_final.py posthoc`, labelled).

## Implementation plan

- `core/src/tiled_data.rs` (new) or `ms_write.rs`: TiledDataStMan with
  hypercubes (header with cubes and maps, hypercube records, coordinate
  and id columns, multi-axis row positions), TiledCellStMan (header, one
  cube per row), `adjustTileShape`/`makeTileShape`.
- `core/src/ism.rs`: indirect string arrays.
- `core/src/multifile.rs`: casacore's `MultiFile` as a model (files, block
  lists, free list, change flag, header with continuation sets, container
  truncation) driven by the managers' write events; reading continuation
  headers.
- `core/src/ms_write.rs`: write events of StandardStMan, IncrementalStMan,
  array files and tiled managers in MultiFile tables; the managers above in
  `TableWriter`; `read_cells` for them; "not supported" refusals.
- `core/src/ms_create.rs`: TiledCellStMan and TiledDataStMan with
  coordinate and id columns, MultiFile block size, refusals.
- `core/py/src/lib.rs` (wiring; committed on the branch and listed
  verbatim): any new bindings. `python/rang/core_ms_write.py`:
  `addhypercube`, `extendhypercube`, MultiFile block size, MultiHDF5
  refusal.
- `tools/oracles/casacore-cpp/` (Dockerfile, build.sh, oracle.cc),
  `examples/oracle_ms_final.py`, `examples/check_ms_final.py`,
  `tests/test_e6_table_writer_final.py` (skips without Docker, the images,
  the oracle outputs or the binding).

Every tool run is timed and listed under Timings.

## What is implemented

As planned, with these additions (all measured by the frozen run):

- `core/src/tiled.rs` (new): `adjust_tile_shape` and `make_tile_shape`
  (casacore's `Float rem` kept in single precision), the hypercube values
  record (`Record` objects in the tiled header; array fields read and
  defined).
- `core/src/ms_write.rs`, tiled managers: one header type for the four
  kinds (TiledColumnStMan and TiledCellStMan write a tile shape first,
  TiledShapeStMan its default tile and 32-bit row maps, TiledDataStMan
  version 2 with `nrrowLast` and a 64-bit row map); one writer whose
  columns have roles from the hypercolumn definition (data in the tiles,
  coordinates and ids in each cube's record); a cell's place
  (`getHypercube(row, position)`: the row map of TiledShapeStMan and
  TiledDataStMan, positions over several row axes, one cube per row of a
  TiledCellStMan); `addHypercube`/`extendHypercube` (`makeHypercube`'s file
  choice, `initCoordinates`, `extendCoordinates`, `updateRowMap`,
  `getCubeIndex` by id values, the row check); coordinate and id reads and
  puts; TiledCellStMan `setShape` (new tiles appended, the old cube's cache
  dropped unflushed as `TSMCube::setShape` does: what was put into it since
  the last flush is lost, measured in C-var); and each cube's
  `BucketCache` (slots, LRU, dirty flags, `initializeBuckets`, the tiles in
  the file counted from its physical size, `calcCacheSize` for cell,
  column and row-range access), so tiles are written when casacore writes
  them. The header is rewritten at every flush after a change, as
  `TiledStMan::flush` does.
- `core/src/ism.rs`: indirect string arrays (`putShape` of strings: the
  offsets reserved and zeroed; the bodies appended in batches of 4096,
  then the offsets; reads), `putcell` of a string array as
  `ArrayColumn::put`.
- `core/src/multifile.rs` (rewritten): the header with continuation
  (`readRemainder`, `writeRemainder` with its two sets, the block count
  patched, chunks written through one buffer), casacore's `MultiFileBase`
  as a model (`write` extending and marking changed, `extendVF` from the
  descending free list's tail, `deleteFile` and `truncateIfNeeded`, slots
  of deleted files reused), and a write log the managers fill: the
  StandardStMan and IncrementalStMan bucket caches at every bucket write
  (evictions included), headers and indexes, array files written directly
  as `MFFileIO` does (no `FilebufIO` buffer), tile caches, tiled headers
  made anew at every flush, files made anew by `recreate`. At each table
  flush the log is replayed and the blocks of the written files are
  written from the staged contents.
- `core/src/ms_create.rs`: TiledCellStMan and TiledDataStMan (with
  coordinate and id columns) creation, the MultiFile block size; other
  managers refused as "not supported" with a reason; MultiHDF5 refused.
- `core/src/aipsio.rs`: `Record::write_kind` (a `Record` object), array
  type helpers, `decode_string_array`.
- `python/rang/core_ms_write.py`: `addhypercube`, `extendhypercube`,
  `multifile=<block size>`, the MultiHDF5 refusal, string-array `putcell`
  as `ArrayColumn::put`, and (W4-4) string-array keywords in C order.
- `tools/oracles/casacore-cpp/` (Dockerfile, build.sh, oracle.cc: the
  O-cpp cases through casacore's `TableProxy` with python-casacore's
  description records), `examples/oracle_ms_final.py`,
  `examples/check_ms_final.py`, `tests/test_e6_table_writer_final.py`.

## Measured result (2026-10-31)

Run `outputs/e6-20261031-01`, all steps by one script (scratch
`frozen_run.sh`: `image` (`build.sh` with the record `image.json`),
`oracle`, `oracle-twin`, `oracle-perturb` (`MALLOC_PERTURB_=85`), `cases`,
`determinism`, `readback`, `refusals`, `regress`, `serialisation`,
`crossversion`, `summary` → `result.json`, then `posthoc`, labelled post
hoc), every step timed in `timing/`, logs in `logs/`. Code `7721e96`
(`commit.txt`). Oracle image `rang-casacore-cpp:3.7.1`, id
`sha256:4484743b0289c45febbb0b71794cb05195314b8018a7fd9766b0dda60cbdc242`,
547,529,202 bytes, debs `casacore-dev=3.7.1-1kern1`,
`libcasa-tables8=3.7.1-1kern1`, `g++-13=13.3.0-6ubuntu2~24.04.1` (all in
`image.json`). Inputs read in place: E3's, E4's and E5's oracle runs.
Development runs preceded it in scratch (deleted); the frozen run is the
first E6 run in `outputs/`.

**Criterion 1, byte identity: fails as frozen (20 of 21 cases pass).**

| Case | Oracle | Files | Bytes | Against casacore | Core (ms) | casacore (ms) |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| D-cubes | 3.7.1 | 6 | 5,032 | identical | 30.8 | 37.1 |
| D-reopen | 3.7.1 | 6 | 5,608 | identical | 13.9 | 11.5 |
| D-multiaxis | 3.7.1 | 5 | 3,094 | identical | 6.5 | 23.8 |
| D-be | 3.7.1 | 6 | 5,031 | identical | 5.0 | 16.3 |
| C-var | 3.8.1 | 5 | 3,171 | identical | 6.4 | 17.1 |
| C-fixed | 3.8.1 | 5 | 3,209 | identical (amended, 1) | 6.0 | 16.6 |
| C-write | 3.8.1 | 5 | 4,374 | identical | 4.9 | 10.1 |
| C-be | 3.8.1 | 5 | 3,170 | identical | 6.6 | 15.2 |
| C-notile | 3.8.1 | 5 | 484,476 | identical | 7.6 | 18.6 |
| X-371 | 3.7.1 | 5 | 3,171 | identical | 5.3 | 17.6 |
| IS-arrays | 3.8.1 | 5 | 47,209 | **differs**: `table.f0i` 677 bytes, all alignment gaps (post hoc); the frozen walk does not end | 11.1 | 23.5 |
| IS-big | 3.8.1 | 5 | 361,736 | identical | 10.4 | 139.0 |
| T-notile | 3.8.1 | 8 | 1,052,407 | identical | 8.8 | 19.8 |
| T-notile-fixed | 3.8.1 | 5 | 132,348 | identical | 7.6 | 17.4 |
| T-notile-column | 3.8.1 | 5 | 263,228 | identical | 6.2 | 16.5 |
| F-multi | 3.8.1 | 4 | 194,427 | identical but 2,734 masked header-tail bytes | 40.4 | 98.8 |
| F-multi-write | 3.8.1 | 4 | 194,427 | identical but 3,250 masked header-tail bytes | 12.8 | 11.9 |
| F-cont | 3.8.1 | 4 | 57,995 | identical (continuation blocks included; nothing masked) | 62.4 | 73.4 |
| F-free | 3.8.1 | 4 | 40,178 | identical but 534 masked header-tail bytes | 26.6 | 45.6 |
| F-default | 3.8.1 | 4 | 16,778,527 | identical | 56.6 | 144.8 |
| K-arrays | 3.8.1 | 4 | 2,473 | identical (amended, 2) | 6.4 | 20.1 |

Every `table.lock` sync record is equal. casacore's times are its own
process's (container start excluded), the core's the checker's. No masked
continuation byte differs (reported, not gated).

**Criterion 2, read-back: passes.** 21 tables, 65,226 defined cells:
python-casacore reads every core-written table exactly as casacore's
(cells, definedness, keywords, column keywords, `table.info`); the core
reads casacore's tables column-exactly as python-casacore does (data,
coordinate and id columns of the TiledDataStMan tables included); casacure
3.8.35 reads 12 cases alike on both sides, keywords included, and cannot
open D-cubes, D-reopen, D-multiaxis, D-be (`unsupported data-manager type
TiledDataStMan`) and the five MultiFile cases (it looks for `table.f0`).

**Criterion 3, determinism: fails as frozen.** The core's outputs of every
case are identical between two runs and a `MALLOC_PERTURB_=85` run (no
mask). casacore's twin and perturbed runs differ only in masked bytes
(MultiFile header tails: F-multi 2,429 / 3,669, F-multi-write 3,425 /
3,668, F-free 472 / 472, F-default 4,194,072 in the perturbed run), except
IS-arrays' `table.f0i` (827 and 1,794 bytes), the gaps the frozen walk
cannot mask. H-mfh5 (excluded): every casacore run differs from the first
at byte 1980 (an HDF5 object modification time).

**Criterion 4, E3, E4 and E5 unchanged: passes.** E3: 20 cases identical,
4 identical but padding, round trip and serialisation pass; E4: 18 of 18
identical or gaps only; E5's `cases` against `outputs/e5-20261031-01`: 21
identical or masked, I-arrays and I-rows-all differing in exactly E5's
bytes (440 and 34); the E3, E4, E5, T1 and E6 tests pass (check-all
below).

**Criterion 5, serialisation identity: passes**: 21 tables, 14 tiled
headers (TiledDataStMan with hypercubes, TiledCellStMan, TiledShapeStMan,
TiledColumnStMan), 8 StandardStMan and 7 IncrementalStMan files, 5
MultiFile headers (F-cont's with continuation), and E5's tables again.

**Criterion 6, refusals: passes.** R-tcsm-remove: the core and
python-casacore refuse `removerows([1])`, files unchanged; R-mfh5: create
and open (write and read) refuse with "MultiHDF5 tables are not
supported: ..." and leave no table or change no file; R-other:
"Adios2StMan columns are not supported: ..."; no source line under
`core/src` or `python/rang` names E6.

**Criterion 7, cross-version identity: passes.** X-371 (casacore 3.7.1)
equals C-var (casacore 3.8.1) byte for byte, `table.lock` included.

**Post hoc (labelled)**: IS-arrays' 677 differing bytes all lie in gaps of
the walk with the first-put bodies consumed (`posthoc.json`).

## Deviations

- Amendments 1–3 above (before the frozen run): C-fixed's new rows put by
  `putcell` (casacore raises on the frozen ranged `putcol`); the K-arrays
  case added for W4-4; the frozen gap walk kept for IS-arrays, a post hoc
  walk added.
- The C++ oracle makes its tables through casacore's `TableProxy` with the
  records python-casacore builds rather than through `SetupNewTable`
  directly (the protocol named only "a C++ program"); X-371 shows the two
  oracles then write identical bytes.
- Tile-cache access paths of whole-column and row-range puts are modelled
  as `accessColumn`/`accessColumnCells` size their cache (`calcCacheSize`
  of the cube shape), the tiles of each cell fetched in order; the strided
  iteration order inside `accessStrided` is not ported (it changes no
  bytes; it could change MultiFile block order only when another logical
  file grows during the same put, which no case does).

## Open items

- What the writer still does not do, each refused with "not supported"
  and its reason: MultiHDF5 (libhdf5's layout and modification times);
  Adios2StMan and other data managers that are not MS or calibration-table
  storage managers; tiled headers, tile files or hypercube offsets of
  2 GiB or more and tiled managers of 2^31 rows or more (their version-2/3
  records); MultiFile containers with block CRCs (casacore's `useCRC`,
  off by default) and version-1 MultiFile headers.
- Coordinate and id columns are written for TiledDataStMan only (a
  hypercolumn with coordinates bound to a TiledShapeStMan or
  TiledCellStMan is not given coordinate values; no case or MS uses them).
- The gaps of string-array files under the frozen rule (IS-arrays), and
  E5's uninitialised values and gaps: the core writes zeros where casacore
  leaves heap memory.
- A ranged `putcol` of a TiledCellStMan is written correctly by the core;
  casacore raises (or misbehaves) there (amendment 1), so it is not
  compared.

## Timings

| Date | Tool / stage | Input | Wall | Notes |
| --- | --- | --- | ---: | --- |
| 2026-10-31 | `git clone --depth 1 --branch v3.8.1 casacore` (and v3.7.1) | | 4.4 s | format reference, scratch |
| 2026-10-31 | KERN-10 package probe (container, network) | | 54.5 s | deb versions before pinning |
| 2026-10-31 | `build.sh rang-casacore-cpp:3.7.1` (first build) | Dockerfile | 83.4 s | apt from KERN-10 |
| 2026-10-31 | `build.sh` rebuilds with `oracle.cc` | | 6.9 s / 1.8 s | cached layers; the second in the frozen run |
| 2026-10-31 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging,casacure]' ruff maturin pip` | worktree | 186 s | builds the extension |
| 2026-10-31 | pre-freeze probes (python-casacore, C++, MultiFile continuation), 3 runs each | | 1.6–5 s | scratch |
| 2026-10-31 | `cargo check --release` (core) | `core/` | 5.8–13 s | incremental, about 15 runs |
| 2026-10-31 | `maturin develop --release` | extension | 190–200 s | eight builds |
| 2026-10-31 | `cargo test --release` (core, 131 tests) | `core/` | 177 s | build included |
| 2026-10-31 | `pytest` E3, E4, E5, T1 table tests / E6 tests | | 8.9 s / 0.3 s | 44 passed / 6 passed, 1 skipped |
| 2026-10-31 | frozen `oracle` (python-casacore write + 4 write-mf + 6 C++ cases) | 21 cases + H-mfh5 | 8.8 s | twin 8.2 s, perturbed 8.2 s |
| 2026-10-31 | `check_ms_final.py cases` | 21 cases | 0.8 s | |
| 2026-10-31 | `check_ms_final.py determinism` | 2 × 21 cases | 2.0 s | |
| 2026-10-31 | `check_ms_final.py readback` | 21 tables | 12.9 s | container included |
| 2026-10-31 | `check_ms_final.py refusals` | 5 attempts | 1.1 s | one python-casacore container |
| 2026-10-31 | `check_ms_final.py regress` | E3, E4, E5 oracles | 16.1 s | |
| 2026-10-31 | `check_ms_final.py serialisation`, `crossversion`, `summary`, `posthoc` | | 0.3 s each | |

## For the coordinator

- Shared files, committed on the branch (the appendix has the exact diff
  against `17653e4`):
  - `core/src/lib.rs`, alphabetical: `pub mod tiled;` (no new dependency,
    `Cargo.lock` unchanged).
  - `core/py/src/lib.rs`: `MsWriter.add_hypercube`,
    `MsWriter.extend_hypercube`, `MsWriter.put_string_cell`, the
    `RecordItem` type and `record_of`, the `block_size` keyword argument of
    `ms_create_table`.
  - Also changed, not an owner file: `tests/test_e5_table_writer_rest.py`
    (`test_memory_and_tiled_data_managers` expected an E6 refusal of
    TiledDataStMan values; it now expects casacore's refusal of a row
    without a hypercube).
  - `README.md`, `research/README.md`, `research/STATE.md`,
    `research/tool-timings.md`, `research/big-plan.md`,
    `research/non-ratt-observations.md` and `python/rang/core_cli.py` are
    not touched; their changes follow.
- STATE paragraph: "E6 (the last of the core table writer) measured:
  rang's core now writes TiledDataStMan hypercubes (addHypercube and
  extendHypercube, coordinate and id values, rows added to a hypercube,
  hypercubes of several row axes), TiledCellStMan tables, IncrementalStMan
  string arrays, tiled managers without a default tile shape and MultiFile
  tables of any block size with casacore's block order (bucket- and
  tile-cache writes during a session, the free list, header continuation),
  as casacore does. 20 of 21 frozen cases are byte-identical to casacore
  (3.8.1 through python-casacore; 3.7.1 through a pinned C++ oracle for the
  hypercubes; 3 with the masked MultiFile header tail); IS-arrays differs
  only in array-file alignment gaps that the frozen gap walk could not
  mask (post hoc: all 677 bytes are gaps), so criteria 1 and 3 fail as
  frozen; read-back, E3-E5 regressions, serialisation, refusals and the
  cross-version check (3.7.1 and 3.8.1 write the same TiledCellStMan table)
  pass. MultiHDF5 is refused as not supported (libhdf5 layout; two
  casacore runs differ in an HDF5 modification time); no writer error
  names E6. W4-4 is absorbed: 2-D string-array keywords are now stored in
  C order as python-casacore stores them (a 2x3 keyword table.dat differed
  in 61 bytes before, identical after). `outputs/e6-20261031-01`,
  `research/results/e6-table-writer-final.json`."
- `research/README.md` index line:
  "[e6-table-writer-final.md](e6-table-writer-final.md) — E6:
  TiledDataStMan hypercubes, TiledCellStMan, ISM string arrays, default
  tile shapes and MultiFile block order and continuation in the core
  writer, MultiHDF5 refused; 20 of 21 cases byte-identical to casacore, the
  rest alignment gaps (measured); W4-4 absorbed."
- `research/tool-timings.md`: the Timings rows above and the check-all row.
- `research/big-plan.md`: E6 done 2026-10-31 (`e6-table-writer-final.md`);
  W4-4 done within E6; nothing of the table writer is left but the open
  items above.
- README: `rang.core_ms_write` writes every casacore storage manager of an
  MS or calibration table (TiledDataStMan hypercubes with
  `addhypercube`/`extendhypercube`, TiledCellStMan included), big-endian
  and MultiFile tables (`multifile=<block size>`); MultiHDF5 is not
  supported.
- Upstream observations (all non-RATT, for
  `research/non-ratt-observations.md`; nothing RATT, caracal-pipeline or
  saopicc):
  - casacore 3.8.1 (defect): a ranged `putcol` (`putColumnRange`) of a
    TiledCellStMan column goes through
    `TSMDataColumn::accessColumnCells`, which reads `rowpos(lastAxis)`, an
    axis a TiledCellStMan cube does not have (its position is the cell
    shape only), and raises `TSMShape::offset - shapes do not conform`
    (undefined behaviour: past the end of an `IPosition`); a whole-column
    `putcol` and `putcell` work.
  - casacore 3.8.1 (note): `TiledCellStMan::setShape` of a row whose cube
    has unflushed tiles deletes the cube's cache unflushed
    (`TSMCube::setShape` → `deleteCache`), so the values put into the old
    shape since the last flush never reach the file, while values flushed
    earlier stay in it as unreferenced bytes.
  - casacore 3.8.1 (defect): `MultiFile::writeRemainder` writes a single
    continuation chunk from a `malloc`'d buffer it does not clear; the
    block's bytes after the chunk are whatever the heap held (fragments of
    file names and an AipsIO `RecordDesc` in a probe).
  - casacore 3.7.1 (note): MultiHDF5 containers are not reproducible:
    libhdf5 1.10.10 writes object modification times (two runs a second
    apart differ at bytes 1980 and 3285).
  - python-casacore 3.8.1 (note): `getcell` of a string array of more than
    one axis returns a dict of its shape and strings, not an array.
  - casacure 3.8.35 (note): reads TiledCellStMan tables and
    IncrementalStMan string arrays like python-casacore; cannot open
    TiledDataStMan or MultiFile tables (as in E5).
- W4-4 (absorbed): the string-array keyword fix is in
  `python/rang/core_ms_write.py` (`_put_keyword`: C order instead of
  Fortran order); numeric-array keywords were already right; E3's and E4's
  byte-identity cases still pass (criterion 4); measured before/after on
  K-arrays: 61 bytes of `table.dat` differ / identical.
- DF-IO-CT should pick up: nothing new for calibration tables; MS writes
  may now use TiledDataStMan and TiledCellStMan tables (older MeasurementSets)
  and any MultiFile block size.
- Ignored output: `outputs/e6-20261031-01` (2.2 GB: `e5/` 1.7 GB and
  `e5-cases/` 213 MB are the E3, E4 and E5 regression re-runs and can be
  deleted; `dumps/` 46 MB can be trimmed to its JSON; `oracle*` 31 MB and
  `core*` 20 MB each, keep `oracle/` and `core/`) and
  `outputs/e6-20261031-check-all.log`.
- Scratch `~/Build/tmp/20261031-e6` (the casacore v3.7.1 and v3.8.1
  clones, the probes, development runs) is deleted at the end of the task;
  the image `rang-casacore-cpp:3.7.1` stays (the oracle).

## Appendix: the wiring diff

`git diff 17653e4 -- core/src/lib.rs core/py/src/lib.rs tests/test_e5_table_writer_rest.py` at the branch head (committed on the branch):

```diff
diff --git a/core/py/src/lib.rs b/core/py/src/lib.rs
index 3772cea..ca69ad9 100644
--- a/core/py/src/lib.rs
+++ b/core/py/src/lib.rs
@@ -1842,6 +1842,46 @@ impl MsWriter {
             .map_err(|e| PyOSError::new_err(e.0))
     }

+    /// `TiledDataStManAccessor::addHypercube` of the TiledDataStMan `name`:
+    /// shapes in casacore order, `values` the id and coordinate values as
+    /// (field, keyword kind, type code, shape, native bytes), in order
+    /// (research/e6-table-writer-final.md).
+    fn add_hypercube(
+        &mut self,
+        name: &str,
+        shape: Vec<i64>,
+        tile: Vec<i64>,
+        values: Vec<RecordItem>,
+    ) -> PyResult<()> {
+        let rec = record_of(values)?;
+        self.get()?
+            .add_hypercube(name, &shape, &tile, rec)
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    /// `TiledDataStManAccessor::extendHypercube` of the TiledDataStMan
+    /// `name` by `incr` on the last axis (`values` as in `add_hypercube`).
+    fn extend_hypercube(&mut self, name: &str, incr: u64, values: Vec<RecordItem>) -> PyResult<()> {
+        let rec = record_of(values)?;
+        self.get()?
+            .extend_hypercube(name, incr, rec)
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    /// Write one cell of a string-array column as `ArrayColumn::put` does
+    /// (`putcell`; research/e6-table-writer-final.md).
+    fn put_string_cell(
+        &mut self,
+        name: &str,
+        row: u64,
+        shape: Vec<i64>,
+        strings: Vec<String>,
+    ) -> PyResult<()> {
+        self.get()?
+            .put_string_cell(name, row, &shape, &strings)
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
     /// The columns as (name, type code, is array), in table order.
     fn columns(&mut self) -> PyResult<Vec<(String, i32, bool)>> {
         Ok(self
@@ -1900,6 +1940,20 @@ impl MsWriter {

 type CellTuple<'py> = (i32, Vec<i64>, Bound<'py, PyBytes>, Vec<String>);

+/// A record field: name, keyword kind, type code, shape, native bytes.
+type RecordItem = (String, i32, i32, Vec<i64>, Vec<u8>);
+
+/// The record of a hypercube's id and coordinate values.
+fn record_of(items: Vec<RecordItem>) -> PyResult<rang_core::aipsio::Record> {
+    let mut rec = rang_core::aipsio::Record::default();
+    for (name, kind, code, shape, data) in items {
+        let value = keyword_value(kind, code, &shape, &data, 0).map_err(PyValueError::new_err)?;
+        rec.define(&name, value)
+            .map_err(|e| PyValueError::new_err(e.0))?;
+    }
+    Ok(rec)
+}
+
 /// A hypercolumn definition: name, ndim, data, coordinate and id columns.
 type HypercolumnArgs = (String, u32, Vec<String>, Vec<String>, Vec<String>);

@@ -1922,7 +1976,7 @@ fn writer(w: rang_core::ms::Result<TableWriter>) -> PyResult<MsWriter> {
 /// (`ffi_ms_write::ColumnArgs`, `ManagerArgs`), `table.info` (type,
 /// subtype, readme), `nrows` rows; returned open for writing.
 #[pyfunction]
-#[pyo3(signature = (path, desc, columns, managers, info, nrows, big_endian=false, multifile=false, hypercolumns=Vec::new()))]
+#[pyo3(signature = (path, desc, columns, managers, info, nrows, big_endian=false, multifile=false, hypercolumns=Vec::new(), block_size=0))]
 #[allow(clippy::too_many_arguments)]
 fn ms_create_table(
     py: Python<'_>,
@@ -1935,6 +1989,7 @@ fn ms_create_table(
     big_endian: bool,
     multifile: bool,
     hypercolumns: Vec<HypercolumnArgs>,
+    block_size: i64,
 ) -> PyResult<MsWriter> {
     let spec = rang_core::ms_create::TableSpec {
         desc_name: desc.0,
@@ -1945,6 +2000,7 @@ fn ms_create_table(
         info,
         big_endian,
         multifile,
+        block_size,
         hypercolumns: hypercolumns
             .into_iter()
             .map(
diff --git a/core/src/lib.rs b/core/src/lib.rs
index 96bc816..0c5cd1d 100644
--- a/core/src/lib.rs
+++ b/core/src/lib.rs
@@ -54,6 +54,7 @@ pub mod predict;
 pub mod robust;
 pub mod solve;
 pub mod sumthreshold;
+pub mod tiled;
 pub mod weights;
 pub mod wgridder;

diff --git a/tests/test_e5_table_writer_rest.py b/tests/test_e5_table_writer_rest.py
index 11eac23..84e159d 100644
--- a/tests/test_e5_table_writer_rest.py
+++ b/tests/test_e5_table_writer_rest.py
@@ -182,8 +182,10 @@ def test_memory_and_tiled_data_managers(tmp_path):
     }
     with (
         w.create_table(tds, td, nrow=2, dminfo=dmi) as t,
-        pytest.raises(OSError, match="E6"),
+        pytest.raises(OSError, match="no hypercube"),
     ):
+        # E6 writes TiledDataStMan values; a row without a hypercube has
+        # none (casacore: `getHypercube: rownr is too high`).
         t.putcol("D", np.zeros((2, 4, 8), np.float32))
     assert w.read_cells(tds, "D", 0, 2) == [None, None]

```

Blank context lines of the diff are written without their leading space
(`git diff --check`); `git apply --ignore-whitespace` applies it.
