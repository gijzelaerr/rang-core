# Rang core, task E3: the casacore table writer

Task E3 of [big-plan.md](big-plan.md), defined by the casacure evaluation
([casacure-evaluation.md](casacure-evaluation.md), verdict (c): build rang's
own table layer on task E's reader). Branch `e3-table-writer` from
`f36ff80`. Protocol frozen 2026-10-30 in the commit that adds this file,
before any writer code. Before freezing, one scratch measurement was made
(the determinism inventory below); nothing else was measured.
Status: **implemented and measured (frozen check `outputs/e3-20261030-02`).
Criteria 2 to 8 pass; criterion 1 fails as frozen for 4 of 24 cases**: the
four `addcols`/new-array cases differ from casacore only in the alignment
padding between arrays in `table.fNi`, which casacore fills from an
uninitialised buffer and which differs between two casacore runs (section
"Measured result"). Every other file of every case, the 41 round-tripped
tables and both 342 M-flag writes are byte-identical to casacore. Archive:
[results/e3-table-writer.json](results/e3-table-writer.json).

The user's decision (2026-10-30): the core must read **and write** every
format of the tools it replaces ([ecosystem-survey.md](ecosystem-survey.md)
section 5.3; here MS v2 and, from E4, CASA calibration tables). E3 is the
writer for **existing** tables. Under AGENTS.md a reimplementation of a
file format is not a scientific contribution; no archived result changes
because of it.

## Scope

In scope (E3), all on little-endian tables as written by casacore 3.8:

1. **In-place `putcol` and `putcell` of existing columns**, whole columns and
   row ranges:
   - StandardStMan: scalar columns of every numeric type and Bool (bit
     packed); Direct fixed-shape arrays (numeric, Bool); indirect arrays
     (numeric, Bool) in `table.fNi`, overwritten in place when the shape is
     unchanged and appended the way `StManArrayFile::putRes` does when the
     row has no array or a different shape (variable-shape columns only;
     FixedShape columns refuse a new shape, as casacore does); the
     StandardStMan index and 512-byte header rewritten on flush exactly as
     `SSMBase::writeIndex` does when a bucket changed (half-bucket toggle,
     or new index buckets with the old ones put on the free list).
   - TiledColumnStMan and TiledShapeStMan: rows that have a hypercube; the
     tiles are rewritten in place (Bool bit packed per tile, columns of a
     hypercolumn at their offsets in the tile). The header file is left as
     it is (casacore 3.8.1 rewrites it with identical bytes, measured).
   - The columns and shapes the drivers write: FLAG (Bool [4096, 4] TSS in
     the fixture, [2048, 4] SSM indirect in the LUNO export), FLAG_ROW,
     DATA, CORRECTED_DATA, MODEL_DATA, WEIGHT_SPECTRUM, UVW, WEIGHT, SIGMA.
   - Strings, lower priority: fixed-length and variable-length scalar
     string columns of StandardStMan. If they are not done, they are
     refused with an error and listed as deferred to E4 in the result.
2. **Keywords**: table keywords and column keywords, put and remove, of
   scalar (Bool, Int, Int64, Float, Double, Complex, DComplex, String),
   array (numeric and String) and sub-record values; `table.dat` rewritten
   through `table.dat_tmp` and a rename, as `BaseTable::writeStart/End` do.
3. **`addcols`**, two cases, both checked against casacore's layout:
   - (a) the drivers' path, `addcols(desc)` without a data-manager spec
     (`flagging_workflow.py`, `flagging_imaging.py`,
     `flagging_response.py`): casacore binds the column to an existing
     StandardStMan (measured: the fixture's seq 6, whatever the group
     name), using the best-fit free space of an existing SSM index or a
     new index with `bucketSize × 8 / bits` rows per bucket and new
     buckets; variable-shape arrays get indirect storage in `table.fNi`.
   - (b) a new data manager from a spec: TiledColumnStMan and
     TiledShapeStMan with a FixedShape column and a tile shape, and a new
     StandardStMan.
4. **The table description and `table.dat`**: a complete model of
   `table.dat` (Table, TableDesc with keyword records, column descriptions,
   ColumnSet, data-manager blobs) that serialises back to the same bytes.
5. **The lock file**: the writer takes casacore's fcntl write lock on
   `table.lock` (byte `4 × locknr`, length 1, lock number 0) before
   writing and releases it after; on flush it writes the sync record
   (`TableSyncData::write`: row count, column count, modify counter, table
   change counter, one change counter per data manager) after the data
   files and `table.dat`, so that a casacore process holding the table open
   resynchronises on its next lock. Flushes follow casacore's schedule: one
   sync update per flush (the Python API flushes on `flush()` and on
   close), not per `putcol`. No lock-request ids are written (an
   auto-locking casacore reader that holds a read lock and is idle keeps
   the writer waiting; the writer then fails after a bounded number of
   attempts with a "table is locked" error). Platforms without fcntl
   (Windows) write without an inter-process lock; this is stated in the
   API.

Deferred, refused with an error naming the follow-on:

- IncrementalStMan writes, ISM arrays and strings (E5); the bookkeeping
  columns are not written by any driver.
- Big-endian tables (E5; the writer refuses `table.dat` format flag 0).
- TiledShapeStMan rows without a hypercube (cube 0, e.g. the fixture's
  FLAG_CATEGORY) and shape changes in tiled columns (E5).
- New tables, rows added or removed, `default_ms`, caltables (E4).
- String arrays (Direct or indirect), MultiFile tables, MemoryStMan,
  TiledDataStMan, `removecols`/`renamecol` (E4/E5 as they are needed).

## Determinism inventory (measured before freezing, scratch)

python-casacore 3.8.1 in `rang-ms-reader:local` did one write of each kind
on two fresh copies of the three MSs (permanent locking, writes, one close),
script and output in `~/Build/tmp/20261030-e3/inv` (scratch, 4.2 s with the
container). **Every case gave byte-identical files in the two runs.** What
changed against the original:

| Write | Files changed (besides `table.lock`) | Sync record |
| --- | --- | --- |
| SSM scalar FLAG_ROW, ANTENNA1 (fixture); FLAG_ROW, Direct UVW (LUNO) | `table.fN` only, same size (index and header rewritten) | changes |
| SSM indirect, same shape: LUNO FLAG, MODEL_DATA; imaging CORRECTED_DATA | `table.fNi` only | **unchanged** (the manager reports no change) |
| TSS FLAG, WEIGHT_SPECTRUM; TCS UVW (fixture) | the tile file only; header file unchanged | changes |
| table keyword, column keyword | `table.dat` | changes |
| `addcols(desc)` with or without a group name (fixture) | `table.dat`, `table.f6` grows 16,896 → 25,088 bytes, new `table.f6i` | changes |
| `addcols` with a TiledColumnStMan or TiledShapeStMan spec | `table.dat`, new `table.f25` and tile file | changes, record grows by 4 bytes |
| `putcell` changing the shape of a variable-shape row | `table.f6i` appended | changes |

So byte identity with casacore is the target for every case in scope.

Post hoc (2026-10-30, after the frozen run): twin runs were not a
sufficient test of determinism. The alignment gaps that new indirect
arrays leave in `table.fNi` hold uninitialised memory, identical in twin
runs with the same process history but different between runs
("Measured result", criterion 1); `MALLOC_PERTURB_` runs expose it.

## Oracles (frozen)

- **python-casacore 3.8.1** in `rang-ms-reader:local` (`tools/ms-reader/`,
  NumPy 2.5.3), the reference writer and reader:
  `examples/oracle_ms_write.py` copies each input MS, performs each frozen
  case with `table(..., readonly=False, lockoptions="permanent")`, the
  writes, one close; it writes the values it used to an `.npz` (seeded
  generator, seed 20261030) so the core writes exactly the same values, and
  in a second mode reads back the core's written copies with `getcol` (and
  `getkeywords`/`getcolkeywords`) into an oracle dump.
- **casacure 3.8.35** (`casacure==3.8.35`, host venv), a second read-back
  oracle only: its read side is column-exact (E2); its writer is not used.
- **The core reader** `rangtoy.core_ms` (task E), the third read-back.
- **Comparator**: `compare_arrays`/`compare_strings` from
  `examples/check_ms_reader.py`, unchanged (dtype, shape and bytes; NaN
  payloads and signed zeros count; strings by value), plus byte-for-byte
  file comparison.

Inputs, read in place and never written (copies are written): the fixture
`outputs/tv-caracal-wsl-20261029-01/original.ms`, the LUNO export
`outputs/luno-solve-20261029-02/work.ms` and the imaging MS
`outputs/tv-next-imaging-wsl-20261029-01/caracal-diagnostic.ms`, with the
SHA256 of every file recorded before and after. For scale (no L1 MS is on
disk; L1 kept no visibility MS), two synthetic tables of 41,786 rows with a
Bool FLAG of cell shape [2048, 4] (342,315,008 flags, the size of L1's
LUNO chunk 0), built by python-casacore in the container: one with FLAG as
a FixedShape indirect StandardStMan column (the LUNO export's layout), one
with FLAG in a TiledShapeStMan (the fixture's CASA layout, tile [4, 2048,
16]). Outputs only in fresh `outputs/e3-20261030-NN`.

### Frozen cases

On copies of the fixture (F), LUNO export (L), imaging MS (I):

- F: FLAG_ROW, ANTENNA1, FLAG (TSS), WEIGHT_SPECTRUM (TSS), DATA (TSS),
  SIGMA (TSS [4]), UVW (TCS), a row range of FLAG (rows 10–49) and of
  FLAG_ROW, one `putcell` of FLAG and of DATA; table keyword (Double, Int,
  String, Double array, sub-record) and column keyword (String on DATA,
  replacing an existing keyword value on UVW's QuantumUnits); all in one
  session for a multi-write case.
- F: `addcols` (a) as `flagging_workflow.py` (no group) and as
  `flagging_imaging.py` (group name), each followed by `putcol` of a
  complex64 [4096, 4] array; a `putcell` that changes the shape of one row
  of that column.
- F: `addcols` (b) TiledColumnStMan Bool [4096, 4] tile [4, 64, 16] and
  TiledShapeStMan Float [4096, 4] tile [4, 64, 16], each followed by
  `putcol`; and a new StandardStMan for a complex64 column.
- L: FLAG and MODEL_DATA (indirect), WEIGHT_SPECTRUM, FLAG_ROW, UVW
  (Direct), a table keyword.
- I: CORRECTED_DATA (indirect in the FLAG_ROW manager).
- Strings, if implemented: ANTENNA NAME (variable length) and STATION of
  the fixture, values longer and shorter than 8 characters.
- Round trip: every column the core can read and write, of F, L and I and
  their subtables, read with `core_ms` and written back unchanged with the
  writer, in one session per table.

## Acceptance criteria (frozen)

Checked by `examples/check_ms_writer.py` on the host and the oracle's
read-back mode in the container, written to `result.json`; each criterion
gates.

1. **Byte identity.** For every frozen case, every file of the core's
   written copy except `table.lock` equals casacore's written copy byte for
   byte, and the sync record of `table.lock` (the bytes from offset 260:
   length and the `sync` object; the request-id region before it is not
   compared) is equal too.
2. **Read-back.** python-casacore (container), casacure and `core_ms` read
   every written column of every core-written copy column-exactly equal to
   the values the oracle wrote (and every untouched column equal to the
   input's); keywords read by python-casacore equal casacore's own
   copy's.
3. **Round-trip identity.** For F, L and I and their subtables, writing
   back every readable and writable column unchanged gives (i) column-exact
   read-back identical to the input in all three readers and (ii) files
   byte-identical to casacore performing the same round trip (getcol and
   putcol of the same columns, one session).
4. **Task E unchanged.** `examples/check_ms_reader.py` against
   `outputs/core-e-oracle-20261029-01` passes its three criteria;
   `core_ms.py`, `check_ms_reader.py`, `oracle_ms_columns.py` and the
   reader's unit tests are unchanged.
5. **`addcols` columns belong to casacore.** After the core's `addcols`
   and `putcol`, python-casacore opens the table, reads the new column,
   writes new values into it with `putcol`, reads them back exactly, and
   the core reads casacore's rewrite exactly.
6. **Lock protocol.** (i) While a casacore process holds a write lock on a
   copy, the core's open-for-write fails with a lock error after its
   bounded attempts and changes no file; after casacore releases, the
   core's write succeeds. (ii) A casacore reader that has the copy open
   (auto locking, read, `unlock()`) before the core's write sees the new
   values on its next `getcol` without reopening.
7. **Serialisation identity.** `serialise(parse(x)) == x` for every
   `table.dat` (keyword records included), every StandardStMan header and
   index, and every tiled header file of the three MSs and all their
   subtables (Rust unit tests on embedded examples plus the checker over
   the real files).
8. **Scale.** The whole-array FLAG write (342,315,008 flags, one `putcol`
   from a NumPy bool array) into copies of both synthetic tables is byte
   identical to casacore's write of the same array (criterion 1 on these
   tables), and the writing process's peak RSS grows by at most 64 MiB
   during the call (`VmHWM` before and after, input already allocated).
   Reported, not gated: wall time next to casacore's `putcol`.

Reported, not gated: wall time of every core write next to casacore's
(casacore's measured in the container), and bytes written.

Failures are recorded as measured, frozen; any later fix is a new run
labelled post hoc, and the frozen result stays in this file.

## Implementation plan

- `core/src/aipsio.rs`: AipsIO writer (magic, nested objects with length
  back-patching, canonical big-endian and little-endian), the record model
  (`RecordDesc`, `TableRecord` values kept as typed fields or raw bytes),
  `IPosition`, `Block`, `SimpleOrderedMap`.
- `core/src/ms_desc.rs`: the `table.dat` model (parse and serialise).
- `core/src/ms_write.rs`: `TableWriter` (open for write, lock, put, keyword
  edits, `addcols`, flush, close) on top of `ms::Table` for locating cells;
  `ms.rs` gains public accessors where the writer needs reader state, with
  every reader test and the task E comparator unchanged.
- `core/src/ffi_ms_write.rs`: additive C ABI; the extension class
  `MsWriter` in `core/py/src/lib.rs` (coordinator wires both; until then the
  lines are present only in the working tree for testing, as task E did).
- `python/rangtoy/core_ms_write.py`: a separate module (so `core_ms.py`
  stays byte-unchanged) with `open_table(path, readonly=False)` returning a
  table with `getcol` (through `core_ms`), `putcol`, `putcell`,
  `putkeyword`, `putcolkeyword`, `removekeyword`, `addcols`, `flush`,
  `close`.
- `examples/oracle_ms_write.py` (container), `examples/check_ms_writer.py`
  (host), `tests/test_core_ms_write.py` (skips without the oracle outputs,
  the MSs or the writer binding).

Every tool run is timed and listed under Timings.

## What is implemented

As planned above, with these differences from the plan: the writer keeps
its own models of the manager headers (needed for byte-exact rewrites) and
uses `ms.rs` only for the AipsIO cursor (now public) and for reads; `ms.rs`
also gains `Table::open_with_rows` (below). No new Rust dependency; fcntl is
declared directly (Linux layout, `cfg(target_os = "linux")`).

- `core/src/aipsio.rs` (≈770 lines with tests): the AipsIO writer and the
  record model (`RecordDesc` version 2, `TableRecord`, fixed sub-records
  stored inline, variable ones as objects; new array fields described with
  shape [-1] and a field of the same type replaced in place, as casacore
  does).
- `core/src/ms_desc.rs` (≈470): `TableDat::parse/serialise` for the whole
  of `table.dat`; column class names as `ValType::getTypeStr` spells them
  (`ArrayColumnDesc<Complex `, eight characters, no closing bracket).
- `core/src/ms_write.rs` (≈2,950): the lock file and sync record; the
  StandardStMan header, index (written as `writeIndex` does: half-bucket
  toggle, or new buckets with the old ones freed), buckets, bit-packed
  scalars and Direct arrays, indirect arrays, the string-bucket handler
  (`SSMStringHandler` step for step), `addColumn` into an existing manager
  (best-fit free space or a new index) and a new StandardStMan
  (`setBucketSize`, `init`, `create64`); the indirect-array file driven
  through a replica of casacore's `FilebufIO` (block-aligned 64 KiB buffer,
  whole blocks bypass it), because the bytes that end up in alignment gaps
  depend on its history; tiled writes a tile row at a time, new
  TiledColumnStMan and TiledShapeStMan managers (`adjustTileShape` clips
  the tile; the header keeps the tile as given); keywords; `put_file` with
  casacore's flush schedule; `check_serialisation` (criterion 7).
- `core/src/ffi_ms_write.rs`: `rang_core_ms_write_open/close/flush/nrows/
  put/put_strings/put_keyword/remove_keyword/add_column/last_error`,
  additive; panics caught.
- `python/rangtoy/core_ms_write.py`: `open_table(path, readonly=False)`,
  `Table.putcol/putcell/getcol/putkeyword/putcolkeyword/removekeyword/
  removecolkeyword/addcols/flush/close`, `makescacoldesc`,
  `makearrcoldesc`, `maketabdesc` with python-casacore's semantics (cell
  axes reversed; a shape forces FixedShape; `DEFAULTTILESHAPE` taken as
  given, in casacore order, as python-casacore passes it).
- Found while implementing, all measured:
  - casacore rewrites `table.dat` and the sync record whenever it releases
    a write lock (`PlainTable::putFile(True)` from the release callback),
    so closing a table opened for writing corrects a stale row count in
    `table.dat` (the subtables of all three MSs say 0 rows there); the
    writer's `close` does the same, `flush` writes `table.dat` only when the
    table changed.
  - An in-place write of an indirect array with the same shape does not
    change the manager (`SSMIndColumn::putArrayV` dirties no bucket): only
    `table.fNi` changes and the sync counters stay.
  - fcntl locks are per process and closing *any* descriptor of
    `table.lock` drops them (POSIX). The task E reader opens and closes
    `table.lock` to read the row count, so reading the table being written
    in the same process silently dropped the writer's lock (found by
    `tests/test_core_ms_write.py`). The writer now reads the lock file only
    through its locked descriptor, reads its own table through
    `ms::Table::open_with_rows`, which skips `table.lock`, and the Python
    wrapper describes the table before taking the lock. As a guard it also
    re-takes the lock before every change; that fails only if another
    process holds the lock at that moment. If the lock was dropped and
    another process wrote and released in between, the writer would not
    notice and would flush its stale state over the other write (open
    item: compare the sync counters on re-taking).
  - python-casacore's `lock()` returns None and raises on failure; opening
    a table with user locking waits for a read lock, so a casacore process
    simply waits while the core holds the write lock.

## Measured result (2026-10-30)

Runs: oracle `outputs/e3-20261030-01` (`oracle_ms_write.py write`,
`scale-build`, `scale-write`; 2.7 s, 0.6 s, 2.3 s with the container),
frozen check `outputs/e3-20261030-02` (all steps, then `summary` →
`result.json`). Post hoc, labelled: `-03` criterion 6 again with a fixed
casacore probe, `-04` criterion 8 again with the peak RSS reset per table,
`-05` a second casacore oracle `write` (padding nondeterminism). After
`-01`, `oracle_ms_write.py` changed only in its `try-lock` mode; after
`-02`, `check_ms_writer.py` changed only in criterion 6 (iii) and the
peak-RSS reset. The SHA256 of all 205 files of the three input MSs
(`table.lock` excluded) is the same before and after the frozen runs.

**Criterion 1, byte identity: fails as frozen (20 of 24 cases identical).**

| Case | Files against casacore's copy | Core (ms) | casacore (ms) |
| --- | --- | ---: | ---: |
| F-flagrow, F-ant1 (SSM scalars) | identical | 24.0, 26.2 | 29.3, 10.5 |
| F-flag, F-ws, F-data, F-sigma (TSS) | identical | 3.9, 7.4, 6.5, 4.7 | 7.9, 10.7, 11.3, 7.0 |
| F-uvw (TCS) | identical | 4.8 | 7.2 |
| F-ranges (row ranges, `putcell`) | identical | 4.7 | 10.2 |
| F-keywords (five table keywords, two column keywords) | identical | 5.9 | 6.8 |
| F-multi (three columns and a keyword, one session) | identical | 8.9 | 16.3 |
| F-add-default, F-add-group (driver `addcols`) | `table.f6i`: 323 bytes differ, all in alignment padding | 22.7, 25.9 | 24.8, 26.4 |
| F-add-shape (`putcell` with a new shape) | `table.f6i`: 323 bytes, padding only | 20.5 | 25.2 |
| F-add-tcs, F-add-tss (new tiled managers) | identical | 20.4, 17.4 | 11.3, 16.3 |
| F-add-ssm-new (new StandardStMan) | `table.f25i`: 323 bytes, padding only | 17.8 | 25.6 |
| F-antenna-strings (variable-length strings, both sides of 8 bytes) | identical | 3.9 | 8.9 |
| L-flag, L-model, L-ws (SSM indirect) | identical | 3.4, 6.4, 4.0 | 4.4, 5.7, 5.4 |
| L-flagrow, L-uvw (SSM scalar, Direct) | identical | 4.0, 3.1 | 9.4, 11.5 |
| L-kw | identical | 4.0 | 6.9 |
| I-corr (indirect in the FLAG_ROW manager) | identical | 7.0 | 7.7 |

The 323 differing bytes are the 4-byte gaps between consecutive arrays
(each array starts at a multiple of 8; a [4096, 4] complex array with its
12-byte shape ends 4 bytes short). Post hoc (labelled; not a change to the
criterion): `check_ms_writer.py` masks the gaps by walking the arrays and
then finds every file identical (`pass_masking_alignment_padding: true`).
casacore does not write defined bytes there: `StManArrayFile::putRes`
extends the file by writing one byte at the end of the reserved space, and
`FilebufIO` loads a block past the end of the file by reading nothing into
its buffer, so the gap keeps whatever the buffer held, ultimately bytes of
an uninitialised `new char[65536]`. Evidence:

- In the container, a copy of the fixture, `addcols` of RANG_MODEL_DATA as
  in F-add-default, `putcol` of ones, one close, then bytes 131096–131108 of
  `table.f6i` (scratch script, run three times): without
  `MALLOC_PERTURB_` the first gap holds `77640000`, with
  `MALLOC_PERTURB_=85` `aaaaaaaa`, with `=170` `55555555`.
- casacore's own copies disagree between runs: `-05` (post hoc, the same
  oracle code as `-01`) differs from `-01` in 2 bytes of the first gap of
  each of the four files (`-05/casacore-vs-01.json`; every other file of
  every case is identical between the two runs); an earlier development
  run differed from `-01` in all 323 bytes. Under the padding mask all
  casacore runs and the core agree. The core's files are identical between
  its runs.
- The writer replays casacore's buffer operations (the development run
  differed from the core's file in 2 bytes) and writes zeros where
  casacore's buffer was never initialised.

So criterion 1 could not be met for these four cases by any writer, and
the determinism inventory missed it: twin runs with identical process
histories reproduce the same uninitialised bytes. The gaps are
unreferenced: every reader (criteria 2, 3 and 5) reads the arrays exactly.

**Criterion 2, read-back: passes.** For all 24 cases python-casacore reads
every column of the core's copy exactly as it reads casacore's copy, the
written columns equal the values the oracle wrote, keywords and column
keywords are equal (table paths normalised), the same columns fail to read
in both (FLAG_CATEGORY), and casacure and `core_ms` agree column-exactly.
Container read-back 3.4 s for 48 tables.

**Criterion 3, round-trip identity: passes.** 41 tables (the three MSs and
all subtables), 328 columns read with `core_ms` and written back unchanged
(FLAG_CATEGORY, unreadable in all readers, skipped on both sides; string
arrays and IncrementalStMan columns are not written by either side): every
file byte-identical to casacore's round trip (which includes `table.dat`
of the subtables, whose stale row count both rewrite), and read-back
identical to the inputs in python-casacore, casacure and `core_ms`. casacure
is excluded for the columns of 0-row subtables (FLAG_CMD, HISTORY, POINTING,
PROCESSOR), where it returns empty int32 arrays for every column on the
unwritten input too. Writes: core 0.32 s, casacore 0.52 s in total.

**Criterion 4, task E unchanged: passes.** `check_ms_reader.py` against
`outputs/core-e-oracle-20261029-01` passes its three criteria; `core_ms.py`,
`check_ms_reader.py`, `oracle_ms_columns.py` and the reader tests are
unchanged; `ms.rs` changes by 44 lines (visibility, documentation and
`open_with_rows`).

**Criterion 5, `addcols` columns belong to casacore: passes** for all six
added columns (default binding twice, the shape-changed column on its
uniform rows 4–139, TiledColumnStMan, TiledShapeStMan, new
StandardStMan): casacore reads the core's values, rewrites the column,
reads its values back, and `core_ms` reads casacore's rewrite exactly.

**Criterion 6, lock protocol: passes.** (i) While casacore holds the write
lock, the core's open fails after its three attempts (2.0 s) and no file
changes; after the release the core writes. (ii) A casacore reader with
auto locking that read FLAG_ROW and unlocked sees the core's new values on
its next `getcol` without reopening. Reported, not gated, (iii): in the
frozen run the casacore probe was wrong (it took `lock()`'s None as
failure) and reported nothing usable; post hoc (`-03`, labelled) the fixed
probe shows byte 0 of `table.lock` taken while the core holds it, casacore's
open waiting 8.05 s (the whole hold) and then getting the lock, and getting
it at once after the core closed; (i) and (ii) pass again there.

**Criterion 7, serialisation identity: passes.** `table.dat`, every
StandardStMan header and index and every tiled header of 14 + 13 + 14
tables (17 + 13 + 17 StandardStMan files, 8 + 0 + 8 tiled headers) parse
and serialise to the same bytes.

**Criterion 8, scale: passes.** One `putcol` of 41,786 × 2,048 × 4 =
**342,310,912** flags (the protocol's "342,315,008" is an arithmetic slip
for the same array) into copies of the two synthetic tables:

| Table | Core | casacore | Peak RSS growth during the call | Files |
| --- | ---: | ---: | ---: | --- |
| FLAG FixedShape indirect StandardStMan (LUNO layout) | 0.103 s | 0.056 s | 2.3 MB | identical |
| FLAG TiledShapeStMan, tile [4, 2048, 16] (CASA layout) | 0.136 s | 0.089 s | 0 MB, **not a valid measurement** | identical |

The frozen TiledShapeStMan memory figure is invalid: the peak RSS before
that call (471 MB) already held the 90 MB peak of comparing the first
table's files, so an allocation of up to about 85 MB would have shown as
0. Post hoc (`-04`, labelled), with the peak reset to the current RSS
before each table (`/proc/self/clear_refs` 5, checked): growth 2.3 MB and
0 MB from peaks of 381 MB and 383 MB; files identical; core 0.085 s and
0.100 s. Within the 64 MiB bound (the borrowed 342 MB input is not copied).
The core is 1.1–1.8× slower than casacore here and similar or faster on
the small cases above; nothing was tuned.

Failures recorded as frozen: criterion 1 (4 cases, padding only), the
criterion 6 (iii) probe (reported item), the TiledShapeStMan memory
figure of criterion 8 (measurement flaw, re-measured post hoc). No other
criterion failed.

Scope deviation: frozen scope item 5 exempts platforms *without* fcntl
from the inter-process lock. macOS has fcntl, but its `struct flock`
differs from Linux's and the writer declares fcntl for Linux only, so on
macOS (as on Windows) it writes without the lock. Not compiled or tested
here.

## Timings

| Date | Tool / stage | Input | Wall | Notes |
| --- | --- | --- | ---: | --- |
| 2026-10-30 | `git clone --depth 1 --branch v3.8.1 casacore` | 43 MB | 17.7 s | format reference, `~/Build/tmp/20261030-e3/casacore-src` |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin casacure==3.8.35` | worktree | 41.4 s | |
| 2026-10-30 | determinism inventory, python-casacore 3.8.1 in `rang-ms-reader:local` | 19 cases × 2 copies | 4.2 s | container included |
| 2026-10-30 | `cargo +1.93 test` (core, 85 tests, fixture set) | `core/` | 35.8 s | build included; 0.8 s of tests |
| 2026-10-30 | `maturin develop --release --offline` (with the binding lines) | extension | 31–43 s | |
| 2026-10-30 | `pytest tests/test_core_ms_write.py tests/test_core_ms.py` | fixture, LUNO | 4.5 s | 9 passed, 4 skipped (before the oracle run) |
| 2026-10-30 | `oracle_ms_write.py write` (run `-01`) | 24 cases | 2.7 s | container included |
| 2026-10-30 | `oracle_ms_write.py scale-build` / `scale-write` | 2 tables, 342 M flags | 0.6 s / 2.3 s | container; casacore `putcol` 0.056 s and 0.089 s |
| 2026-10-30 | `check_ms_writer.py cases` (`-02`) | 24 cases | 2.1 s | |
| 2026-10-30 | `check_ms_writer.py readback` | 48 tables | 6.3 s | container 3.4 s |
| 2026-10-30 | `check_ms_writer.py roundtrip` | 41 tables | 3.4 s | casacore container 1.1 s, read-back container 1.0 s |
| 2026-10-30 | `check_ms_writer.py reader` | task E oracle | 0.9 s | |
| 2026-10-30 | `check_ms_writer.py addcols` | 6 columns | 4.3 s | 6 containers |
| 2026-10-30 | `check_ms_writer.py locks` | fixture copies | 22.2 s | includes the 12 s and 8 s holds |
| 2026-10-30 | `check_ms_writer.py serialisation` | 41 tables | 0.07 s | |
| 2026-10-30 | `check_ms_writer.py scale` | 2 × 342 M flags | 0.7 s | peak RSS 460 MB (input 342 MB) |
| 2026-10-30 | `check_ms_writer.py locks` post hoc (`-03`) | fixture copies | 22.4 s | |
| 2026-10-30 | `check_ms_writer.py scale` post hoc (`-04`) | 2 × 342 M flags | 0.7 s | peak reset per table |
| 2026-10-30 | `oracle_ms_write.py write` post hoc (`-05`) | 24 cases | 2.9 s | container; padding comparison with `-01` |
| 2026-10-30 | `bash tools/check-all.sh` (with the wiring diff of the appendix present) | repo | 3.5 min | PASS: root 23, core 85 Rust tests; pytest 661 passed, 3 skipped (98 s); log `outputs/e3-20261030-02/check-all.log` |

## For the coordinator

- `core/src/lib.rs`, in alphabetical order: `pub mod aipsio;`,
  `pub mod ffi_ms_write;`, `pub mod ms_desc;`, `pub mod ms_write;` (Rust
  1.93, edition 2024, no new dependency; `Cargo.lock` unchanged).
- `core/py/src/lib.rs`: the `MsWriter` class and `ms_serialisation_check`
  function in the appendix diff below, which also has
  `use rang_core::ffi_ms_write::{keyword_value, new_column};`,
  `use rang_core::ms_write::TableWriter;`, `PyReadonlyArray1` in the
  `numpy` import, and in `_core`: `m.add_class::<MsWriter>()?;` and
  `m.add_function(wrap_pyfunction!(ms_serialisation_check, m)?)?;`.
  `tools/check-all.sh` was run once with all these lines present (PASS,
  Timings); without them `tests/test_core_ms_write.py` skips.
- STATE paragraph: "E3 (core table writer) measured: rang's core now writes
  existing casacore tables as casacore 3.8.1 does: putcol/putcell for
  StandardStMan (scalars, Direct and indirect arrays, variable-length
  strings) and the tiled managers, keywords, addcols (the drivers' default
  binding, new StandardStMan, TiledColumnStMan, TiledShapeStMan) and the
  fcntl lock with the sync record. Against python-casacore: 20 of 24 frozen
  cases byte-identical, the other 4 identical except the alignment padding
  casacore fills from uninitialised memory (criterion 1 fails as frozen);
  read-back, round trip of 41 tables (byte-identical), addcols, locks,
  serialisation identity and the 342 M-flag write (0.09–0.14 s, at most
  +2.3 MB peak RSS, byte-identical) pass. `outputs/e3-20261030-02`,
  `research/results/e3-table-writer.json`."
- `research/tool-timings.md`: the Timings rows above.
- README: `rangtoy.core_ms_write` writes existing casacore tables for the
  core (python-casacore stays the oracle and is still needed to create
  tables until E4).
- E4 should pick up: table creation reuses `TableDat` (`serialise`),
  `SsmW::create` (bucket sizing as `setBucketSize`), the tiled header
  model and `empty_values_record`; adding rows (`SSMIndex::addRow` is
  implemented for new indices, `addRow64` on existing managers is not);
  string arrays (`SSMStringHandler` array puts, the reader's
  `StringBuckets::strings`); `table.info`; caltable schemas. The drivers'
  `addcols` path (default binding into the first StandardStMan) is done.
- E5 should pick up: IncrementalStMan writes, big-endian writes (the
  writer refuses `table.dat` format flag 0 and big-endian hosts),
  TiledShapeStMan rows without a hypercube and shape changes in tiled
  columns, MultiFile tables; and the freed-bucket scratch content (below).
- DF-IO-CT: caltables are StandardStMan tables with keywords and
  `table.info`; the writer covers their column and keyword writes once E4
  creates them.
- Upstream observations (all non-RATT, for
  `research/non-ratt-observations.md`; nothing RATT or caracal-pipeline):
  - casacore 3.8.1: `StManArrayFile`/`FilebufIO` write uninitialised heap
    bytes into the 8-byte alignment gaps of `table.fNi` (non-reproducible
    file contents, valgrind-visible); a report would ask `putRes` to write
    the gap explicitly. Evidence in "Measured result".
  - casacore 3.8.1 (note, not a defect): every write-lock release rewrites
    `table.dat`, so tables written by tools that never close for write keep
    a stale row count there; readers must use `table.lock`.
  - casacure 3.8.35, a twelfth item: every column of a 0-row table is read
    as an empty int32 array (FLAG_CMD, HISTORY, POINTING, PROCESSOR of the
    three MSs).
  - python-casacore 3.8.1 (note): `addcols` passes `DEFAULTTILESHAPE`
    through in casacore axis order while shapes in column descriptions are
    reversed; `lock()` returns None and raises on failure.
- Evidence to keep: `outputs/e3-20261030-01` (1.7 GB; the 24 casacore case
  copies, values, the two synthetic tables), `-02` (4.3 GB; could be
  trimmed to its JSON files and the `core/` case copies), `-03` (locks), `-04` (scale with the peak reset), `-05` (second casacore write; could keep only `casacore-vs-01.json` and the four addcols case copies).
- Scratch: `~/Build/tmp/20261030-e3` (casacore clone, inventory,
  development runs, the `MALLOC_PERTURB_` probe) was deleted at the end of
  the task; the casacore v3.8.1 clone takes 18 s to repeat.

## Open items

- casacore's free-bucket content: when the StandardStMan index outgrows
  half a bucket, casacore puts the old index buckets on the free list and
  writes its cache's scratch buffer into them; the writer writes the last
  bucket it flushed. No frozen case exercises this (every index here fits
  half a bucket); the bytes are unreferenced.
- Speed: the core is 1.5–1.8× slower than casacore on the 342 M-flag
  write; the indirect path makes one shape read per row through the
  emulated buffer, the tiled path re-derives strides per row.
- The writer flushes on `getcol` (it reads through the reader); casacore
  serves reads from its caches without flushing, so a session that reads
  between writes increments the sync counters once more than casacore.
- Windows and macOS: no inter-process lock (fcntl is declared for Linux
  only; the macOS gap is a scope deviation, see "Measured result");
  macOS's `struct flock` differs and needs its own declaration.
- Lock re-taking does not detect a write by another process during a
  silently dropped lock; compare the sync record's modify counter with
  the one read at open when re-taking, and refuse on a change.
- E4: test determinism with `MALLOC_PERTURB_` runs, not only twin runs.

## Appendix: the wiring diff

Exactly what `tools/check-all.sh` compiled (`git apply` from the
repository root; module lines kept in the order the test script put them,
sort them alphabetically when applying by hand):

```diff
diff --git a/core/py/src/lib.rs b/core/py/src/lib.rs
index 4115bf7..0edbeaa 100644
--- a/core/py/src/lib.rs
+++ b/core/py/src/lib.rs
@@ -24,7 +24,9 @@
 //! into an input array during the call races with the kernel, exactly as it
 //! did under ctypes (which also released the GIL): do not do that.

-use numpy::{Element, IntoPyArray, PyArray1, PyReadonlyArrayDyn, PyReadwriteArrayDyn};
+use numpy::{
+    Element, IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArrayDyn, PyReadwriteArrayDyn,
+};
 use pyo3::exceptions::{PyOSError, PyValueError};
 use pyo3::prelude::*;
 use pyo3::types::PyBytes;
@@ -32,10 +34,12 @@ use rang_core::ffi;
 use rang_core::ffi_correct::CorrectInputsC;
 use rang_core::ffi_flag::{FlagInputs, FlagOutputs};
 use rang_core::ffi_grid::{GridInputs, GridOutputs};
+use rang_core::ffi_ms_write::{keyword_value, new_column};
 use rang_core::ffi_weights::{
     ImagingWeightInputs, ImagingWeightOutputs, StokesIInputs, StokesIOutputs,
 };
 use rang_core::ms::{DataType, Table};
+use rang_core::ms_write::TableWriter;
 use rang_core::toy;

 type Ro<'py, T> = PyReadonlyArrayDyn<'py, T>;
@@ -1102,6 +1106,196 @@ impl MsTable {
     }
 }

+/// `serialise(parse(x)) == x` over a table and its subtables (the table
+/// writer's criterion 7): (tables, StandardStMan files, tiled headers,
+/// failures).
+#[pyfunction]
+fn ms_serialisation_check(
+    py: Python<'_>,
+    path: &str,
+) -> PyResult<(usize, usize, usize, Vec<String>)> {
+    let c = detach(py, || rang_core::ms_write::check_serialisation(path))
+        .map_err(|e| PyOSError::new_err(e.0))?;
+    Ok((c.tables, c.ssm_files, c.tiled_headers, c.failures))
+}
+
+/// A casacore table open for writing (research/e3-table-writer.md); holds
+/// casacore's write lock until `close`.
+#[pyclass(unsendable)]
+struct MsWriter {
+    writer: Option<TableWriter>,
+}
+
+impl MsWriter {
+    fn get(&mut self) -> PyResult<&mut TableWriter> {
+        self.writer
+            .as_mut()
+            .ok_or_else(|| PyValueError::new_err("table is closed"))
+    }
+}
+
+#[pymethods]
+impl MsWriter {
+    #[new]
+    fn new(py: Python<'_>, path: &str, attempts: u32, wait_ms: u64) -> PyResult<Self> {
+        let wait = std::time::Duration::from_millis(wait_ms);
+        match detach(py, || TableWriter::open(path, attempts, wait)) {
+            Ok(writer) => Ok(MsWriter {
+                writer: Some(writer),
+            }),
+            Err(e) => Err(PyOSError::new_err(format!("{path}: {e}"))),
+        }
+    }
+
+    fn nrows(&mut self) -> PyResult<u64> {
+        Ok(self.get()?.nrows)
+    }
+
+    /// Write `count` rows (0: to the end) from `start`: `data` the cells'
+    /// native bytes as a uint8 array (borrowed, not copied), `shape` the
+    /// cell shape in casacore order (empty for scalars).
+    fn put(
+        &mut self,
+        py: Python<'_>,
+        name: &str,
+        start: u64,
+        count: u64,
+        shape: Vec<i64>,
+        data: PyReadonlyArray1<'_, u8>,
+    ) -> PyResult<()> {
+        let bytes = data.as_slice()?;
+        let w = self.get()?;
+        detach(py, || w.put_column(name, start, count, &shape, bytes))
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    /// Flush, then read `count` rows (0: to the end) from `start`, packed as
+    /// `MsTable.read` packs them; the table's lock is kept.
+    fn read<'py>(
+        &mut self,
+        py: Python<'py>,
+        name: &str,
+        start: u64,
+        count: u64,
+    ) -> PyResult<Column<'py>> {
+        let w = self.get()?;
+        let data = detach(py, || w.read_column(name, start, count))
+            .map_err(|e| PyOSError::new_err(e.0))?;
+        if data.shape.len() > 8 {
+            return Err(PyOSError::new_err("more than 8 cell axes"));
+        }
+        let dtype = data.dtype.unwrap_or(DataType::Str);
+        let nstrings = data.strings.len();
+        let mut bytes = data.bytes;
+        if dtype == DataType::Str {
+            bytes = Vec::with_capacity(data.strings.iter().map(|s| 4 + s.len()).sum());
+            for s in &data.strings {
+                bytes.extend((s.len() as u32).to_le_bytes());
+                bytes.extend_from_slice(s.as_bytes());
+            }
+        }
+        Ok((
+            bytes.into_pyarray(py),
+            data.nrows,
+            data.shape,
+            dtype.code(),
+            nstrings,
+        ))
+    }
+
+    fn put_strings(&mut self, name: &str, start: u64, values: Vec<String>) -> PyResult<()> {
+        self.get()?
+            .put_strings(name, start, &values)
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    /// Define a keyword: kind 0 scalar, 1 string, 2 array, 3 string array,
+    /// 4 empty record (`rang_core_ms_write_put_keyword`).
+    #[pyo3(signature = (column, path, kind, code, shape, data, strings))]
+    #[allow(clippy::too_many_arguments)]
+    fn put_keyword(
+        &mut self,
+        column: Option<String>,
+        path: Vec<String>,
+        kind: i32,
+        code: i32,
+        shape: Vec<i64>,
+        data: Vec<u8>,
+        strings: Vec<String>,
+    ) -> PyResult<()> {
+        let value = if kind == 3 {
+            Ok(rang_core::aipsio::KeywordValue::StringArray(shape, strings))
+        } else {
+            keyword_value(kind, code, &shape, &data, 0)
+        }
+        .map_err(PyValueError::new_err)?;
+        let parts: Vec<&str> = path.iter().map(String::as_str).collect();
+        self.get()?
+            .put_keyword(column.as_deref(), &parts, value)
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    fn remove_keyword(&mut self, column: Option<String>, path: Vec<String>) -> PyResult<()> {
+        let parts: Vec<&str> = path.iter().map(String::as_str).collect();
+        self.get()?
+            .remove_keyword(column.as_deref(), &parts)
+            .map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    /// `addcols` of one column; `manager` 0 default binding, 1 a new
+    /// TiledColumnStMan, 2 a new TiledShapeStMan named `manager_name`.
+    #[allow(clippy::too_many_arguments)]
+    fn add_column(
+        &mut self,
+        py: Python<'_>,
+        name: String,
+        dtype: i32,
+        array: bool,
+        ndim: i32,
+        shape: Vec<i64>,
+        option: i32,
+        max_length: u32,
+        comment: String,
+        dm_type: String,
+        dm_group: String,
+        default: Vec<u8>,
+        manager: i32,
+        manager_name: String,
+        tile: Vec<i64>,
+    ) -> PyResult<()> {
+        let spec = new_column(
+            name,
+            dtype,
+            array,
+            ndim,
+            shape,
+            option,
+            max_length,
+            [comment, dm_type, dm_group],
+            default,
+            manager,
+            manager_name,
+            tile,
+        )
+        .map_err(PyValueError::new_err)?;
+        let w = self.get()?;
+        detach(py, || w.add_column(&spec)).map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    fn flush(&mut self, py: Python<'_>) -> PyResult<()> {
+        let w = self.get()?;
+        detach(py, || w.flush()).map_err(|e| PyOSError::new_err(e.0))
+    }
+
+    /// Flush and release the lock; the table is closed even on an error.
+    fn close(&mut self, py: Python<'_>) -> PyResult<()> {
+        match self.writer.take() {
+            Some(w) => detach(py, || w.close()).map_err(|e| PyOSError::new_err(e.0)),
+            None => Ok(()),
+        }
+    }
+}
+
 /// The extension module `rangtoy._core`.
 #[pymodule]
 fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
@@ -1136,5 +1330,7 @@ fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
     m.add_function(wrap_pyfunction!(project_out, m)?)?;
     m.add_function(wrap_pyfunction!(toy_cli, m)?)?;
     m.add_class::<MsTable>()?;
+    m.add_class::<MsWriter>()?;
+    m.add_function(wrap_pyfunction!(ms_serialisation_check, m)?)?;
     Ok(())
 }
diff --git a/core/src/lib.rs b/core/src/lib.rs
index 5634028..53d74c5 100644
--- a/core/src/lib.rs
+++ b/core/src/lib.rs
@@ -20,6 +20,7 @@
 //! the P4 eigensolver, projector, the pointing toy) and nothing builds the
 //! root crate at run time.

+pub mod aipsio;
 pub mod blosc;
 pub mod correct;
 pub mod ffi;
@@ -27,11 +28,14 @@ pub mod ffi_correct;
 pub mod ffi_flag;
 pub mod ffi_grid;
 pub mod ffi_ms;
+pub mod ffi_ms_write;
 pub mod ffi_weights;
 pub mod fused;
 pub mod grid;
 pub mod jones;
 pub mod ms;
+pub mod ms_desc;
+pub mod ms_write;
 pub mod predict;
 pub mod robust;
 pub mod solve;
```
