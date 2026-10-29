# Rang core, task E: read-only Measurement Set reader

Wave 1 task E of [core-parallel-plan.md](core-parallel-plan.md), on branch
`core/e-ms-reader` from `9e12326`. Protocol frozen 2026-10-29 in the commit
that adds this file, before any reader code. Status: **proposed; protocol
frozen; oracle and comparator precondition measured**. Phase 6 of the port
plan in [stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9.4: a Rust reader for casacore tables so python-casacore leaves the
hot path. Gate as frozen there: column-exact reads of the fixture and LUNO
MSs. A reimplementation of a file format; under AGENTS.md not a scientific
contribution, and no archived result changes because of it.

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

## What is proposed

- `core/src/ms.rs`: an AipsIO reader, `table.dat` parsing, and the three
  managers above, exposing `Table::open(path)`, column descriptions and
  `read_column(name, start, count)` returning native-endian bytes in
  casacore's Fortran cell order (what python-casacore's `getcol` returns
  after its reversed shape), strings length-prefixed. Read-only: the
  reader opens files for reading only and never touches `table.lock`.
  Variable-shaped columns are read when every requested row has the same
  shape (the `getcol` rule). Outside the task: IncrementalStMan arrays and
  strings, MemoryStMan, MultiFile tables, big-endian data files, and the
  deprecated `StManAipsIO`, which fail with a clear error.
- `core/src/ffi_ms.rs`: `rang_core_ms_open/close`, a JSON description of
  the table, `rang_core_ms_read_size` and `rang_core_ms_read`, and a
  thread-local last error, following `ffi.rs`.
- `python/rangtoy/core_ms.py`: `open_table(path)` with `nrows`, `columns`,
  `getcol(name, startrow, nrow)` returning arrays shaped as python-casacore
  does, and `subtable(name)`; registers its own ctypes symbols as
  `core_zarr.py` does.
- No new Rust dependency.

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

## For the coordinator

- Add to `core/src/lib.rs`: `pub mod ffi_ms;` and `pub mod ms;` (both
  written for Rust 1.93, edition 2024, no new dependencies).
- `research/tool-timings.md`: copy the rows of the Timings table above.
- README: `rangtoy.core_ms` is the MS edge of the core; python-casacore is
  still needed to write tables and for the oracle.
