# Rang core, task E3: the casacore table writer

Task E3 of [big-plan.md](big-plan.md), defined by the casacure evaluation
([casacure-evaluation.md](casacure-evaluation.md), verdict (c): build rang's
own table layer on task E's reader). Branch `e3-table-writer` from
`f36ff80`. Protocol frozen 2026-10-30 in the commit that adds this file,
before any writer code. Before freezing, one scratch measurement was made
(the determinism inventory below); nothing else was measured.
Status: **protocol frozen; not implemented.**

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

## Timings

| Date | Tool / stage | Input | Wall | Notes |
| --- | --- | --- | ---: | --- |
| 2026-10-30 | `git clone --depth 1 --branch v3.8.1 casacore` | 43 MB | 17.7 s | format reference, `~/Build/tmp/20261030-e3/casacore-src` |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin casacure==3.8.35` | worktree | 41.4 s | |
| 2026-10-30 | determinism inventory, python-casacore 3.8.1 in `rang-ms-reader:local` | 19 cases × 2 copies | 4.2 s | container included |
