# Rang core, task E: read-only Measurement Set reader

Wave 1 task E of [core-parallel-plan.md](core-parallel-plan.md), on branch
`core/e-ms-reader` from `9e12326`. Protocol frozen 2026-10-29 in the commit
that adds this file (`1a9b8f4`), before any reader code. Status:
**implemented; measured: all three frozen criteria pass** (run `-02`, the
first implementation, and run `-03` after speed fixes). Phase 6 of the port
plan in [stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4: a Rust reader for casacore tables so python-casacore leaves the
hot path. Gate as frozen there: column-exact reads of the fixture and LUNO
MSs. A reimplementation of a file format; under AGENTS.md not a scientific
contribution, and no archived result changes because of it.

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../history/README.md); this text keeps the paths it was written
with.

## Storage-manager inventory (measured 2026-10-29)

Read with python-casacore 3.8.1 `getdminfo` in `rang-flagging:local`
(scratch script, output kept in the oracle receipts below) and confirmed by
parsing the headers directly. The task brief named StandardStMan and
TiledStMan; the fixture also uses **IncrementalStMan** for TIME, FIELD_ID,
SCAN_NUMBER and the other row bookkeeping columns, so the reader must
support three managers. Every table is little-endian data (`table.dat`
format flag 1) with big-endian canonical `table.dat` and tiled headers; the
StandardStMan and IncrementalStMan header files are little-endian.

| MS | Rows | Manager (seqnr) | Columns | Layout |
| --- | ---: | --- | --- | --- |
| LUNO `outputs/luno-solve-20261029-02/work.ms` (built by `build_luno_ms.py` with casacore 3.8.1; `table.dat` SHA256 `f7d51164…`) | 192 | StandardStMan (0), one manager, five SSM indices | all 25 main columns | scalars and UVW (Direct, [3]) in 4228-byte buckets of 32 rows; DATA, MODEL_DATA, WEIGHT_SPECTRUM, SIGMA_SPECTRUM as FixedShape [2048, 4] indirect arrays in `table.f0i` (one Int64 offset per row, 528 rows per bucket); FLAG and FLAG_CATEGORY likewise indirect, bit packed |
| fixture `outputs/tv-caracal-wsl-20261029-01/original.ms` (SKA pointing scan 9 via UVFITS; `table.dat` `166d53df…`; identical copies under `tv-injections-…` and `tv-flagging-actions-…`) | 140 | IncrementalStMan (1–5, 7–13) | ARRAY_ID, EXPOSURE, FEED1, FEED2, FIELD_ID, INTERVAL, OBSERVATION_ID, PROCESSOR_ID, SCAN_NUMBER, STATE_ID, TIME, TIME_CENTROID | one 32768-byte bucket each, one row interval |
| | | StandardStMan (6, 14, 15, 16) | FLAG_ROW, ANTENNA1, ANTENNA2, DATA_DESC_ID | one bucket each |
| | | TiledShapeStMan (17–20, 22–24) | DATA, FLAG_CATEGORY, WEIGHT_SPECTRUM, SIGMA_SPECTRUM, FLAG, WEIGHT, SIGMA | one hypercube per manager (cube 0 is the empty placeholder), cube [4, 4096, 140] with tiles [4, 4096, 8] (DATA, 1 MiB), [4, 4096, 16] (spectra), [4, 4096, 64] (FLAG, bit packed); WEIGHT and SIGMA cube [4, 140], tile [4, 32760]; FLAG_CATEGORY has no hypercube (never written, `getcol` fails in casacore too); data in `table.fN_TSM1` |
| | | TiledColumnStMan (21) | UVW | cube [3, 140], tile [3, 43680], `table.f21_TSM0` |
| imaging `outputs/tv-next-imaging-wsl-20261029-01/caracal-diagnostic.ms` (`table.dat` `7aa9cf89…`) | 140 | as the fixture, plus StandardStMan (6) | CORRECTED_DATA and RANG_MODEL_DATA added later to the FLAG_ROW manager as indirect [4096, 4] arrays in `table.f6i`, each with its own SSM index | the only CORRECTED_DATA among the inputs |

Subtables ANTENNA, FIELD, SPECTRAL_WINDOW and POLARIZATION of every MS are
single-manager StandardStMan with scalar, Direct array (OFFSET, POSITION) and
indirect array (CHAN_FREQ and friends, PHASE_DIR, CORR_TYPE, CORR_PRODUCT)
columns, plus variable-length string columns stored in SSM string buckets
(NAME, STATION, MOUNT, TYPE, CODE, FREQ_GROUP_NAME).

## Format sources

The on-disk format is defined by the casacore source, read at tag `v3.8.1`
(commit `5420b48`, the library python-casacore 3.8.1 bundles), cloned to
`~/Build/tmp/20261029-core-e/casacore-src`. casacore is LGPL-2.1-or-later
(`COPYING`); nothing is copied from it, the reader is written from the
format as read in these files, and this section records what was relied on:

- `casa/IO/AipsIO.cc`: every top-level object is preceded by the magic word
  `0xbebebebe`; each object is `uInt length` (counted from the length field
  to the object's end), `String type` (`uInt` byte count plus bytes), `uInt
  version`, body. Nested objects carry their own length, so unknown ones
  (keyword records) can be skipped.
- `casa/IO/TypeIO.cc`, `casa/OS/CanonicalConversion.h`, `casa/OS/Conversion.cc`:
  canonical sizes (1, 2, 4, 8 bytes, complex as two floats), `Bool` arrays
  packed eight per byte, least significant bit first.
- `casa/IO/ArrayIO.tcc`, `casa/IO/IPositionIO.cc`, `casa/Containers/BlockIO.tcc`:
  `Array` (version 3: `uInt ndim`, shape, `uInt n`, values), `IPosition`
  (version 1 `Int`, version 2 `Int64` elements) and `Block` (`uInt n`,
  values) framing.
- `tables/Tables/PlainTable.cc`, `TableDesc.cc`, `ColDescSet.cc`,
  `ColumnDesc.cc`, `BaseColDesc.cc`, `ScaColDesc.tcc`, `ArrColDesc.cc`,
  `ColumnSet.cc`, `PlainColumn.cc`, `ScaColData.tcc`, `ArrColData.cc`:
  `table.dat` (Table version 2: rows, endian format flag, type; TableDesc;
  column descriptions with data type codes from `casa/Utilities/DataType.h`
  and options from `tables/Tables/ColumnDesc.h`; the column set with the
  data-manager list, per-column manager sequence numbers and the
  per-manager byte blobs that `open64` reads).
- `tables/DataMan/SSMBase.cc`, `SSMIndex.cc`, `SSMColumn.cc`,
  `SSMDirColumn.cc`, `SSMIndColumn.cc`, `SSMStringHandler.cc`,
  `StIndArray.cc`, `StArrayFile.cc`, `casa/IO/BucketCache.cc`: StandardStMan
  header (`table.fN`, buckets from byte 512), index buckets, column offsets,
  bit-packed booleans, indirect arrays in `table.fNi` (version 0: `uInt n`,
  `Int` shape, data; version 1 adds a reference count), string buckets.
- `tables/DataMan/ISMBase.cc`, `ISMIndex.cc`, `ISMBucket.cc`,
  `ISMColumn.cc`: IncrementalStMan header, the index object after the
  initial buckets, and the per-bucket row-interval index.
- `tables/DataMan/TiledStMan.cc`, `TiledShapeStMan.cc`,
  `TiledColumnStMan.cc`, `TSMFile.cc`, `TSMCube.cc`, `TSMShape.cc`,
  `TSMDataColumn.cc`: tiled header files, hypercube records, row maps,
  `table.fN_TSMk` tile files (tile `i` at `fileOffset + i × bucketSize`,
  pixels in Fortran order of the tile shape, booleans bit packed per tile,
  data columns of one hypercolumn laid out in descending pixel size).

## What is implemented

- `core/src/ms.rs` (about 1,900 lines with tests): an AipsIO cursor,
  `table.dat` parsing, and the three managers above, exposing
  `Table::open(path)`, column descriptions and
  `read_column(name, start, count)` returning native-endian bytes in
  casacore's Fortran cell order (what python-casacore's `getcol` returns
  after its reversed shape), strings as a list. Every file is opened for
  reading only; `table.lock` is read for its sync record (below) and never
  written or locked. Variable-shaped columns are read when every requested
  row has the same shape (the `getcol` rule). Outside the task and refused
  with an error: IncrementalStMan arrays and strings, MemoryStMan,
  MultiFile tables, the deprecated `StManAipsIO`, tiled scalar columns and
  big-endian hosts; big-endian data files are handled by byte swapping but
  no such table was available to test.
- `core/src/ffi_ms.rs`: `rang_core_ms_open/close`, `rang_core_ms_describe`
  (JSON), `rang_core_ms_read` (a core-allocated buffer, freed with
  `rang_core_ms_free`) and a thread-local `rang_core_ms_last_error`,
  following `ffi.rs`.
- `python/rangtoy/core_ms.py`: `open_table(path)` with `nrows`, `columns`,
  `getcol(name, startrow, nrow)` returning arrays shaped as python-casacore
  does (object arrays for strings), and `subtable(name)`; registers its own
  ctypes symbols as `core_zarr.py` does. `tests/test_core_ms.py` compares
  seven main columns of both MSs and the ANTENNA subtable with the oracle
  and skips when the oracle, the MSs or the reader symbols are absent.
- No new Rust dependency.

Found while implementing, beyond the sources listed above:

- Every top-level AipsIO object is preceded by the magic word, so the
  StandardStMan index buffer and the IncrementalStMan index object start
  with one, and so does each `SSMIndex` in the buffer.
- The row count of a table is the one in the sync record of `table.lock`
  (260 bytes of lock requests, a canonical `uInt` length, then an AipsIO
  `sync` object), falling back to `table.dat` when that is 0
  (`PlainTable.cc`, `TableSyncData.cc`, `casa/IO/LockFile.cc`): the LUNO
  subtables say 0 rows in `table.dat` and 4, 3, 1 and 1 in the lock file.
- Strings up to 8 characters are stored inside the 12-byte slot of the data
  bucket (characters first, length last); longer ones in string buckets
  whose bookkeeping and per-string lengths are canonical big-endian even in
  a little-endian table (`SSMStringHandler.cc`).
- The indirect-array file written by these tables has version 0 (no
  reference count before the shape); version 1 is handled too.
- The tiled data managers' per-manager blob in `table.dat` is empty; a
  TiledShapeStMan keeps an empty placeholder as hypercube 0 and maps rows
  through three `uInt` blocks (`TiledShapeStMan.h`).
- The actual tile shapes differ from the `DEFAULTTILESHAPE` the inventory
  reports: casacore clipped them to the cube ([4, 4096, 8] for DATA).

## Inputs (frozen)

- The three MSs of the inventory, read in place and never written.
- **Oracle** (done, measured): `examples/oracle_ms_columns.py` run once in
  `rang-flagging:local` (python-casacore 3.8.1, NumPy 2.5.3) wrote
  `outputs/core-e-oracle-20261029-01`: for each MS the 22–23 main columns
  listed in the script that exist (CORRECTED_DATA only in the imaging MS,
  MODEL_DATA only in LUNO; FLAG_CATEGORY is not read because casacore
  itself cannot read it) and every column of the four subtables, with
  dtypes, shapes, per-`getcol` wall times and the SHA256 of every file of
  each MS (`receipt.json`). `ms0.npz` SHA256 `4c8e9e17…`, `ms1.npz`
  `73ad1c1b…`, `ms2.npz` `9b3e38f8…`. Wall time with the container: 1.16 s.
- **Comparator precondition** (done, measured): a second dump
  `outputs/core-e-oracle-20261029-02` (1.22 s) is byte-identical in every
  `.npz` and `.strings.json`; `examples/check_ms_reader.py --self-check`
  (`outputs/core-e-check-20261029-01`) reports the two dumps equal and
  catches every one of the 173 single-byte or single-character
  perturbations it applies to a copy of the second dump. The comparator
  compares dtype, shape and bytes (so NaN payloads and signed zeros count)
  and strings by value.

## Acceptance criteria (frozen)

Checked by `examples/check_ms_reader.py <oracle> outputs/<fresh>` on the
host (the core reads; no container, no python-casacore), written to
`result.json`:

1. **Full columns.** For every table and column in the oracle receipt, the
   core's full-column read equals the oracle array column-exactly: same
   dtype, same shape, same bytes; string columns equal by value.
2. **Row ranges.** Reads of rows [0, 1) and [3, 5) of every column equal the
   corresponding slices of the oracle arrays, column-exactly.
3. **Read-only.** The SHA256 of every file of each MS (`table.lock`
   excluded) is unchanged by the reads and equals the oracle receipt's.

All three gate. Reported, not gated: the wall time of every core read next
to the oracle's `getcol` time for the same column (both measured on this
host, the oracle's inside the container, so only large ratios mean
anything), and the number of bytes read per column.

## Measured result (2026-10-29)

**Run `-02`** (`outputs/core-e-check-20261029-02`, the first complete
implementation): criteria 1–3 pass. 173 columns of 15 tables (3 main
tables, 12 subtables) are column-exact, the two row ranges of every column
equal the oracle's slices, and the SHA256 of every file of the three MSs is
unchanged and equals the oracle receipt's. Wall 3.2 s, peak RSS 165 MB.

**Run `-03`** (`outputs/core-e-check-20261029-03`): after three
implementation changes with the criteria unchanged (tiles are copied per
intersecting tile instead of per axis-0 run with a hash lookup each,
booleans are unpacked a byte at a time, indirect arrays are read straight
into the output), criteria 1–3 pass again. Wall 2.8 s, peak RSS 161 MB.

Reported, not gated, full-column reads on the host (run `-03`) against the
oracle's `getcol` in the container (both warm page cache):

| Column | Core (ms) | python-casacore (ms) |
| --- | ---: | ---: |
| fixture DATA, 140 × 4096 × 4 complex64, TiledShapeStMan | 147 | 28 |
| fixture WEIGHT_SPECTRUM, float32, TiledShapeStMan | 42 | 28 |
| fixture FLAG, bool, TiledShapeStMan | 0.9 | 3.0 |
| fixture UVW, TiledColumnStMan | 0.45 | 2.9 |
| fixture TIME, IncrementalStMan | 0.6 | 0.1 |
| imaging CORRECTED_DATA, StandardStMan indirect | 80 | 12 |
| LUNO DATA, 192 × 2048 × 4, StandardStMan indirect | 20 | 12 |
| LUNO FLAG, StandardStMan indirect, bit packed | 14 | 0.9 |
| all 173 full columns | 526 | 133 |
| the 105 subtable columns | 2.6 | 0.8 |

The core is 1.5–5× slower than casacore on the large tiled and indirect
columns and faster on small tiled ones. Profiling (under load, so
indicative) puts about a third of the fixture DATA time in the ctypes
transfer and NumPy copy and the rest in the Rust read, which grows the
output vector row by row and copies it once more into a boxed slice.
Reserving the output once and handing NumPy the buffer without a copy are
the obvious next steps; neither changes a byte of the result. The
casacore numbers include its tile cache, which the core does not keep
between calls.

## Timings

| Date | Tool / stage | Input | Wall | Notes |
| --- | --- | --- | ---: | --- |
| 2026-10-29 | `uv venv` + `uv pip install -e '.[pointing,beam,test]' ruff` (README's `python -m venv` fails: no `ensurepip` on this Python 3.14) | worktree | 0.5 s | cached wheels |
| 2026-10-29 | `cargo +1.93 build --release` core crate, `CARGO_BUILD_JOBS=4` | `core/` | 2.6 s | before any task E code |
| 2026-10-29 | `git clone --depth 1 --branch v3.8.1 casacore` | 43 MB | 4.5 s | format reference |
| 2026-10-29 | python-casacore `getdminfo` inventory in `rang-flagging:local` | 2 MSs, 6 tables each | 0.73 s | container included |
| 2026-10-29 | `oracle_ms_columns.py` in `rang-flagging:local`, run `-01` | 3 MSs, 15 tables, 103 columns | 1.16 s | container included; `getcol` of the 140 × 4096 × 4 DATA 27 ms, of LUNO DATA 8 ms |
| 2026-10-29 | same, run `-02` | same | 1.22 s | byte-identical dumps |
| 2026-10-29 | `check_ms_reader.py --self-check` | the two dumps | 0.61 s | precondition passes |
| 2026-10-29 | `cargo +1.93 test` of `ms::` unit tests and the fixture smoke test | `core/` | 4.8 s build + 0.3 s | |
| 2026-10-29 | `pytest tests/test_core_ms.py` (4 tests, includes a core rebuild) | fixture, LUNO | 10 s | |
| 2026-10-29 | `check_ms_reader.py` run `-02` | 173 columns, 414 reads | 3.2 s | peak RSS 165 MB |
| 2026-10-29 | `check_ms_reader.py` run `-03` | same | 2.8 s | peak RSS 161 MB |
| 2026-10-29 | `bash tools/check-all.sh` (with the two `lib.rs` lines present) | repo | 51.6 min | PASS; pytest 672 passed in 3,070 s while seven sibling sessions shared the 16 cores (175–986 s earlier on a quiet host) |

## For the coordinator

- Add to `core/src/lib.rs`, in alphabetical order: `pub mod ffi_ms;` and
  `pub mod ms;` (Rust 1.93, edition 2024, no new dependencies). The branch
  does not edit `lib.rs`; `tools/check-all.sh` was run once with the two
  lines present, and `tests/test_core_ms.py` skips without them (and
  without the oracle dump or the MSs in `outputs/`).
- `research/tool-timings.md`: copy the rows of the Timings table above.
- README: `rangtoy.core_ms` reads Measurement Sets for the core;
  python-casacore is still needed to write tables and for the oracle.
- `research/upstream-notes.md`: nothing to file; the formats behaved as the
  casacore sources describe.
- Scratch to delete when done: `~/Build/tmp/20261029-core-e` (the casacore
  clone, 43 MB, and the inventory scripts).

## Open questions and follow-ups

- Speed: the gaps in the table above (reserve the output once, pass the
  buffer to NumPy without a copy, keep tiles between calls).
- Only little-endian tables were available; the byte-swapping path for
  big-endian data files (old MSs) is untested.
- IncrementalStMan array and string columns, MultiFile tables and
  MemoryStMan are refused; none of the inputs use them.
- Row selections are contiguous ranges; a row index list (the section 6
  prototype's selection) is one `getcol` per run for now.
