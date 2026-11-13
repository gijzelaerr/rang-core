# MSv2 edge cases: ra-ng's reader against arcae and xarray-ms

2026-11-13, branch `claude/msv2-edge-cases-580d8b`, first part of
gijzelaerr/rang-core issue #5 (`research/multi-node-scope.md` section 7 on
branch `roadmap-v030`, Simon Perkins' reply). Status: **proposed and frozen**
(this section and sections 1 to 4 were committed before any case was read
by ra-ng). This note makes no performance or science claim. It checks
reader correctness against an oracle.

## Question

Simon Perkins wrote that arcae plus xarray-ms handle many unpleasant MSv2
edge cases, such as variable-shaped and partially filled columns. ra-ng
keeps its own Rust reader (`core/src/ms.rs`, reached through `rang.core_ms`
and the extension's `MsTable`) as the fast path. This note asks three
questions on a small case set written by casacore:

- Where does that reader return the same values and the same "unwritten"
  cells as arcae?
- Where does it refuse?
- Where does it disagree?

## 1. The case set (frozen)

The writer is python-casacore 3.8.1 (casacore 3.8). The cases are generated
by `research/results/msv2-edge-cases/edge_cases.py make <dir>`, which takes
seconds and writes about 2 MB. Each table carries one risky feature, so a
refusal at open does not hide the other columns. Each case's row count,
shapes and written rows are in the script.

Standalone tables (`tables/`):

| id | storage manager | feature |
| --- | --- | --- |
| t01-ssm-var-partial | StandardStMan, indirect | variable-shape float32, complex64 and int32 arrays: rows with shapes [4,2] and [8,2], and rows never written |
| t02-ssm-fixed-unwritten | StandardStMan | fixed-shape [4,2] float32, direct and indirect, with odd rows never written |
| t03-tssm-partial | TiledShapeStMan | variable-shape float32, complex64, bool (ndim 2) and float64 (ndim 3) arrays: two hypercubes and unwritten rows |
| t04-tcsm-partial | TiledColumnStMan | fixed-shape [4,2] complex64 and bool, half of the rows written |
| t05-tcellsm | TiledCellStMan | variable-shape float32, a different shape per row |
| t06-ism | IncrementalStMan | int32, float64, bool and string scalars set at a few rows only; a fixed-shape float32 array |
| t07-strings | StandardStMan, IncrementalStMan | string arrays: variable shape partly written, fixed shape indirect partly written, direct; an IncrementalStMan string array |
| t08-tssm-alternating | TiledShapeStMan | shapes [4,2] and [8,2] alternating row by row (hypercubes reused, a row map not contiguous per cube); a variable-shape ndim 1 float64 column |
| t09-big-endian | StandardStMan, IncrementalStMan, TiledShapeStMan | a big-endian table: scalars, a variable-shape array, a tiled array |
| t10-empty | all of the above | a table with no rows |

Measurement Sets (`ms/`), from `casacore.tables.default_ms`: 4 antennas, 6
cross-correlation baselines with ANTENNA1 < ANTENNA2, 3 times, rows sorted
by (time, data description, baseline). Correlations are XX, XY, YX and YY
(types 9 to 12), with DATA, FLAG, WEIGHT, SIGMA and UVW written:

| id | feature |
| --- | --- |
| m01-ws-unwritten-tssm | WEIGHT_SPECTRUM in TiledShapeStMan, declared but no cell written (the W4 case, `w4-unsupported.md` `ws-undefined`) |
| m02-ws-unwritten-ssm | WEIGHT_SPECTRUM in StandardStMan (indirect), declared but no cell written |
| m03-ws-partial-tssm | WEIGHT_SPECTRUM in TiledShapeStMan written for the first time step only |
| m04-ws-fixed-tcsm | WEIGHT_SPECTRUM fixed-shape in TiledColumnStMan, never written |
| m05-var-spw-tssm | two spectral windows of 4 and 8 channels, two data descriptions; DATA, FLAG and WEIGHT_SPECTRUM in TiledShapeStMan |
| m06-var-spw-ssm | as m05 with DATA in StandardStMan (indirect) |
| m07-empty-subtables | m05's layout with SOURCE, POINTING and SYSCAL tables of no rows, and HISTORY empty |
| m08-no-rows | an MS whose main table has no rows |

Not covered, as python-casacore cannot write them simply: TiledDataStMan
(`TiledDataStMan` needs explicit hypercube definitions), adios2 and Dysco,
and a filled flag of 0 in a string array (as in `feed-poltype-read.md`).

## 2. The comparison (frozen)

There are three steps, as python-casacore and arcae run in WSL, in separate
processes (arcae's own `table()` warns of library conflicts between them),
and the reader runs natively:

1. `make` (WSL, python-casacore) writes the cases.
2. `dump` (WSL) writes one pickle per case:
   - **arcae 0.5.9** (`dump-arcae`): the oracle.
   - **python-casacore** (`dump-casacore`): only for triage, so that an
     arcae-casacore disagreement is not booked as a ra-ng fault.
   - **xarray-ms 0.5.14** (`dump-xms`, on the MSs).
3. `check` (Windows, `rang.core_ms` over `MsTable`, that is
   `rang_core::ms::Table`) reads the same cells and writes
   `research/results/msv2-edge-cases.json`. `check` prints the extension it
   loaded (`rang._core.__file__`) and the commit.

**Oracle per column**, in the main table and in every subtable:

- **Unwritten mask:** a cell is unwritten when arcae's `row_shapes(column)`
  has a null for it. Scalar columns have no unwritten cells.
- **Values:** arcae's `getcol(column, index=([row],))` for each defined row,
  and `getcol(column)` for the whole column. The whole-column read is
  recorded as a refusal with its message when arcae raises.
- **Description:** row count, column names, value type, and the cell shape
  of fixed-shape columns.
- **Axis order:** python-casacore's (NumPy order, the casacore axes
  reversed), which `rang.core_ms` also returns. The arcae probe below
  showed `row_shapes` in that order. `dump-arcae` checks the order against
  python-casacore's `getcell` on every defined cell. Any difference is
  recorded as an oracle disagreement, not as a ra-ng outcome.

**ra-ng per column:**

- **Unwritten mask:** a cell is unwritten when the one-row read
  `getcol(column, row, 1)` raises an error containing `has no array` or
  `has no tiled array`, the reader's only undefined-cell messages
  (`core/src/ms.rs`, `Ssm::read` and `Tsm::locate`). `MsTable` has no other
  "is defined" call.
- **Refusals:** any other error is a refusal; its message is recorded.
- **Reads:** besides the one-row reads, `getcol(column)` for the whole
  column, and `getcol_rows(column, rows)` for the defined rows in reverse
  order (the second read route). These are compared with arcae's whole
  read and with arcae's `getcol(column, index=(rows,))`.
- **Open failure:** if a table does not open, every column in it counts as
  refused, with the open error.

**Equality:**

- Exact: the same NumPy shape, the same dtype, and byte-identical values
  (so NaN payloads and signed zeros count).
- String arrays: equal element by element.
- No tolerance.

**Outcome per cell, then per column:**

| ra-ng | arcae | outcome |
| --- | --- | --- |
| equal values | values | match |
| unwritten | unwritten | match |
| different values or shape | values | **mismatch** |
| values | unwritten | **mismatch** (the dangerous direction: ra-ng invents a cell) |
| unwritten | values | **mismatch** (mask) |
| refuses | values | **refusal**: a reader task |
| refuses | refuses (whole-column reads only) | parity, not a task |
| values | refuses (whole-column reads only) | ra-ng only, recorded, not a task |

- A column is `match` only when every cell matches and both read routes
  match or refuse in parity.
- Otherwise it takes the worst outcome among its cells and reads, in the
  order mismatch, refusal, ra-ng only.
- A different description (row count, column set, value type, or the shape
  of a fixed-shape column) is a mismatch for the table.
- Unwritten fixed-shape cells get no rule of their own. Wherever arcae says
  a cell is defined (casacore's `iscelldefined` is true for direct and
  tiled fixed-shape cells), ra-ng must return the same bytes; wherever
  arcae says undefined, ra-ng must report unwritten.

**xarray-ms, per MS:**

- `xarray.open_datatree(ms, engine="xarray-ms:msv2")`.
- Each correlated dataset's VISIBILITY (DATA), FLAG, WEIGHT
  (WEIGHT_SPECTRUM, or WEIGHT when that is absent), SIGMA_SPECTRUM and UVW
  is compared with ra-ng's read of the same main-table rows.
- Rows are mapped by (TIME, ANTENNA1, ANTENNA2) to the dataset's (time,
  baseline) grid, never by order, and by data description to the partition.
- A grid point is `match` when ra-ng's cell is equal (exact, NaN equal to
  NaN), or when ra-ng reports the cell unwritten and xarray-ms holds its
  fill value (NaN, or 1 for FLAG).
- Further per-MS outcomes:
  - `not exposed`: xarray-ms leaves a column out of the dataset, with or
    without a warning. Recorded with the warning; not a ra-ng task.
  - `xarray-ms fails`: it raises at open or at load.
  - The same mismatch and refusal outcomes as above.

**Predicted refusals** (labelled as predictions from the code, before any
run):

- IncrementalStMan arrays and string arrays: "is not supported", in t06 and
  t07.

Every refusal and mismatch becomes a reader task in section 5. Fixes wait
for the coordinator's word.

## 3. Probe before the freeze

Before this note, a table of two columns, written by python-casacore in the
oracle's venv, was read with arcae 0.5.9 (`probe.tab`; not kept). That probe
established three things:

- `row_shapes` returns shapes in NumPy order with nulls for unwritten cells.
- `getcol` over undefined rows raises `ArrowInvalid` ("Row 1 is not defined
  for column V and missing rows are not configured").
- `getcol` over rows of different shapes raises `TypeError` ("Can't convert
  variably shaped column").

A tiled scalar column (TiledColumnStMan over a scalar) was planned as t08,
but python-casacore refuses to write it ("TiledStMan: unknown dimensionality
for column F64"), so t08 became the alternating-shape case.

`make` and the three dumps ran before the freeze, on the oracle side only;
`dumps/*.pkl` are those runs. arcae's own limits show there already:

- it refuses a defined cell of shape [0] ("list_size needs to be a strict
  positive integer", t01 `I32` row 7);
- it refuses a whole-column read of a table with no rows ("Data partition
  produced no chunks!");
- xarray-ms refuses the MS with no rows ("range() arg 3 must not be zero").

These count as "ra-ng only" or parity under the rule above, never as ra-ng
tasks. No ra-ng read was made before the freeze.

## 4. Environment

| part | where | version |
| --- | --- | --- |
| writer and triage | WSL Ubuntu, uv venv `~/Build/tmp/20261113-msv2-oracle/venv`, Python 3.12 | python-casacore 3.8.1 |
| oracle | the same venv | arcae 0.5.9 (pyarrow 26.0.1), xarray-ms 0.5.14, xarray 2026.9.0 |
| reader | Windows 11 host, worktree `.venv`, extension built by `tools/check_all.py --quick` from this branch | rang-core at the branch head |
| cases and dumps | `D:\rang\outputs\msv2-edge-cases\20261113` (`/mnt/d/...` in WSL) | – |

The steps to regenerate the cases and dumps:

```bash
wsl -e bash -lc 'cd <worktree> && V=~/Build/tmp/20261113-msv2-oracle/venv/bin/python; D=/mnt/d/rang/outputs/msv2-edge-cases/20261113; $V research/results/msv2-edge-cases/edge_cases.py make $D && for s in dump-casacore dump-arcae dump-xms; do $V research/results/msv2-edge-cases/edge_cases.py $s $D; done'
```

The native comparison:

```bash
.venv/Scripts/python research/results/msv2-edge-cases/edge_cases.py check D:/rang/outputs/msv2-edge-cases/20261113 research/results/msv2-edge-cases.json
```

## 5. Results

Not run yet.

## For the coordinator

Not run yet.
