# MSv2 edge cases: ra-ng's reader against arcae and xarray-ms

2026-11-13, branch `claude/msv2-edge-cases-580d8b`, first part of
gijzelaerr/rang-core issue #5 (`research/multi-node-scope.md` section 7 on
branch `roadmap-v030`, Simon Perkins' reply). Status: **measured**. The
introduction and sections 1 to 4 were frozen in `c345bc1`, before ra-ng read
any case; section 5 and the post-hoc changes came later. This note makes no performance or science claim. It checks
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
| m01-ws-unwritten-tssm | WEIGHT_SPECTRUM in TiledShapeStMan, declared at creation, no cell written (as W4's `ws-undefined` in `w4-unsupported.md`, which removed the column and added it again) |
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
| writer and triage | WSL Ubuntu, uv venv `~/Build/tmp/20261113-msv2-oracle/venv`, Python 3.12 (`uv venv -p 3.12 venv && uv pip install -p venv/bin/python python-casacore==3.8.1 arcae==0.5.9 xarray-ms==0.5.14`, public PyPI; added post hoc) | python-casacore 3.8.1 |
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

## 5. Results (2026-11-13)

Run 01:

- **Reader:** the extension built by `tools/check_all.py --quick` (PASS),
  which started at `30d9412`, before the freeze. `core/`, `src/`,
  `Cargo.*` and `python/` are unchanged between `30d9412` and this branch's
  head, so it is the branch's reader. `rang._core` was loaded from the
  worktree.
- **Final receipt:** written by `check` at the committed script (the
  `commit` field), after the post-hoc changes below; the counts are those
  of the run before the last change.
- **Cases and dumps:** `D:\rang\outputs\msv2-edge-cases\20261113`.
- **Receipt:** [`results/msv2-edge-cases.json`](results/msv2-edge-cases.json).
  It holds, per table and column, the outcome, the manager and up to six
  notes, plus the xarray-ms outcomes and the versions. `check` takes 2 s.

**Scale:** 116 tables (10 standalone, 8 MS main tables, 98 subtables), 1009
columns and 5333 cells, of which arcae calls 276 unwritten.

**Oracle check:** arcae and python-casacore disagree on 0 cells.

**Outcome per column:**

| outcome | columns | where |
| --- | ---: | --- |
| match | 928 | everything not listed below |
| mismatch | **0** | – |
| refusal | 55 | t05 (1); t06 (5); t07 `ISM` (1); 6 POINTING columns in each of the 8 MSs (48) |
| ra-ng only | 26 | t01 `I32` (1); t10 (3); HISTORY `APP_PARAMS` and `CLI_COMMAND` in every MS (16); 6 more columns in m08 |

**Matches, by feature:**

- **Unwritten WEIGHT_SPECTRUM (m01 to m03):** values and unwritten masks
  are equal in all three forms: TiledShapeStMan, indirect StandardStMan,
  and a partly written column. Both readers report the same cells
  unwritten: 18 in m01, 18 in m02 and 12 in m03.
- **Never-written fixed-shape cells (m04 TiledColumnStMan, t02, t04):**
  arcae and casacore call them defined, and ra-ng returns the same bytes.
- **Variable-shape and partly filled columns (t01, t03, t08):**
  - In t01 and t03 (two shapes and unwritten rows, in StandardStMan and
    TiledShapeStMan, for float32, complex64, bool and an ndim 3 float64),
    every cell and mask is equal.
  - On whole-column reads over unwritten or mixed-shape rows, both readers
    refuse (parity).
  - The reverse-order `getcol_rows` route is equal wherever arcae reads.
  - In t08, alternating shapes and reused hypercubes are equal.
- **Variable shape across spectral windows (m05, m06):** DATA, FLAG and
  WEIGHT_SPECTRUM are equal cell by cell, in TiledShapeStMan and in
  StandardStMan, and so is SPECTRAL_WINDOW `CHAN_FREQ`.
- **String arrays:** t07 `VAR`, `FIXED` and `DIRECT`, and FEED
  `POLARIZATION_TYPE`, are equal, including an unwritten variable-shape
  cell and non-ASCII text.
- **Big-endian table (t09):** StandardStMan, IncrementalStMan scalars and
  TiledShapeStMan are equal.
- **Empty subtables and tables:** SOURCE, SYSCAL, HISTORY, STATE,
  PROCESSOR, FLAG_CMD, t10 and the m08 main table have equal row counts,
  column sets, types and fixed shapes.
- **Descriptions:** no table differs in row count, column set, value type
  or fixed shape.

**Refusals:**

- **TiledCellStMan (t05):** "storage manager TiledCellStMan is not
  supported". This refusal was not among the frozen predictions.
- **IncrementalStMan holding an array or string column (t06, t07,
  POINTING):** "IncrementalStMan array or string column S is not
  supported".
  - **Predicted:** the refusal of the array and string columns themselves.
  - **Not predicted:** the refusal is per storage manager, not per column.
    Every scalar column in the same IncrementalStMan is refused with it:
    t06 `I32`, `F64` and `B`, and POINTING `TIME`, `INTERVAL`, `NAME`,
    `NUM_POLY`, `TIME_ORIGIN` and `TRACKING`, even in POINTING tables with
    no rows.
  - **Real MSs:** `default_ms` puts most of POINTING, `DIRECTION` and
    `TARGET` included, in one IncrementalStMan, and so do CASA-written MSs
    (`D:\rang\c3a\c3a-20261106-01\A-casa.ms`,
    `D:\rang\outputs\c7a-20261106-03\M1-casa.ms`, both checked with ra-ng's
    description: those columns are marked unsupported). Only `ANTENNA_ID`
    (StandardStMan) is readable there. Both MSs checked have 0 POINTING
    rows.
  - **Current consumers:** none. No reader path in `python/rang` or
    `core/src` reads POINTING today (only `ms_create.rs` and
    `ms_schema.rs` write it).
  - **The refusal site:** `Ism::open` (`core/src/ms.rs`, about line 1097).
    It returns an error for the whole manager at the first array or string
    column, and the table binds that error to every column of the manager
    (`Manager::Unsupported`).

**ra-ng only** (arcae 0.5.9's limits; not ra-ng tasks):

- **A defined int32 cell of shape [0]** (t01 `I32` row 7): ra-ng returns
  the empty array, equal to casacore's `getcell`; arcae raises "list_size
  needs to be a strict positive integer".
- **Whole-column reads of variable-shape and string columns in 0-row
  tables:** arcae raises "Data partition produced no chunks!".

**xarray-ms 0.5.14, per MS:**

| MS | VISIBILITY | FLAG | WEIGHT | UVW | SIGMA_SPECTRUM |
| --- | --- | --- | --- | --- | --- |
| m01 to m07 (9 partitions) | match | match | match | match | derived by xarray-ms (no column) |
| m08 (no rows) | fails at open: "range() arg 3 must not be zero" | | | | |

- **Unwritten WEIGHT_SPECTRUM cells:** xarray-ms holds NaN exactly where
  ra-ng reports a cell unwritten, and equal values elsewhere.
- **Warnings:** every MS warns `ImputedMetadataWarning` about the empty
  STATE and PROCESSOR tables, and no column is left out.

**Post-hoc changes to `check`** (2026-11-13, after the first run; each is
marked in the script):

1. **SIGMA_SPECTRUM:** xarray-ms exposes it without such a column (derived
   from SIGMA), and the first run stopped with a KeyError. It is now
   recorded as derived and not compared.
2. **Booleans:** arcae returns boolean cells as uint8 0 and 1, where
   python-casacore and ra-ng return bool. Under the frozen rule (same dtype)
   every boolean column, every FLAG and FLAG_ROW among them, was a
   mismatch. They are now compared as bool when every value is 0 or 1; any
   other value still fails.
3. **Fixed shapes:** `getcoldesc` (arcae and python-casacore) gives a fixed
   shape in NumPy order, and ra-ng's description in casacore order. The
   frozen script assumed casacore order on both sides and reported 4
   description differences (t02, t04, t10); it now reverses ra-ng's shape
   first.
4. **Time:** xarray-ms's `time` coordinate is in Unix seconds and TIME is
   in MJD seconds, so every grid point first came out as "no row". Rows are
   now mapped at TIME = time + 3506716800 s.
5. **Triage scalars:** the triage compared python-casacore's scalar cells
   (Python numbers, so int64 and float64) by dtype, which gave 2255 false
   disagreements. Scalars are now compared by value.

6. **xarray-ms coverage:** a check was added that every main-table row of
   a partition's data description lies on xarray-ms's grid; rows off the
   grid had been skipped silently. The outcomes did not change.

Change 2 relaxes the frozen comparison itself. ra-ng's bool now counts as
equal to arcae's uint8 0 and 1, where the frozen rule required the same
dtype, and python-casacore's bool cells agree with ra-ng's. The other
changes fix the harness (the oracle's representation, row mapping,
triage) and leave the rule as frozen. After them, every match is exact in
values and in unwritten masks.

**Matches by parity of unrelated refusals:** 16 columns count as `match`
only because both readers refuse the whole-column read of a 0-row table,
for different reasons: POINTING `DIRECTION` and `TARGET` in each of the 8
MSs. arcae raises "no chunks"; ra-ng raises the IncrementalStMan refusal.
They count under the frozen rule, but they are R2's cases, not evidence
that ra-ng reads them.

**Paths covered:** every read through `ms::Table` (the extension's
`MsTable`, which gemclean, `ffi_ms` and the writer's sliced reads also
use). One path is not covered: the table writer's own `is_defined` and
`read_cells` in `core/src/ms_write.rs` (around line 5174), which read
through the writer's managers.

**Throughput (optional item 4):** not measured.

- The host was full (16 of 16 heavy-lock slots, about 14 jobs queued), and
  the task allowed no exclusive lock.
- arcae runs only in WSL, so it would read `D:` through the Windows mount
  while ra-ng reads natively.

Left open.

## 6. Reader tasks

None is started; fixes wait for the coordinator.

| id | task | cases | weight |
| --- | --- | --- | --- |
| R1 | IncrementalStMan: refuse per column, not per manager (`Ism::open` refuses the manager at its first array or string column). Supported scalars read even when the manager also holds an array or string column, and 0-row reads succeed. | t06 `I32`, `F64`, `B`; POINTING `TIME`, `INTERVAL`, `NAME`, `NUM_POLY`, `TIME_ORIGIN`, `TRACKING` (8 MSs) | no current consumer (nothing in ra-ng reads POINTING); needed by any future POINTING read, or by any table whose IncrementalStMan holds an array or string. Size not assessed |
| R2 | IncrementalStMan string scalars, string arrays and fixed-shape arrays, as arcae and casacore read them | t06 `S`, `ARR`; t07 `ISM`; POINTING `DIRECTION`, `TARGET` (16 columns that match now only by parity of refusals) | no current consumer; POINTING directions for pointing work |
| R3 | TiledCellStMan | t05 | low: seen in no MeerKAT or CASA MS here |

**Not covered, for a second round:**

- TiledDataStMan, adios2 and Dysco;
- a string array with a filled flag of 0;
- the cases Simon Perkins has seen break readers (asked in #5).

## For the coordinator

- **Run:** freeze `c345bc1`, then run 01 on `claude/msv2-edge-cases-580d8b`.
- **Matches:** of 1009 columns in 116 tables, 928 match arcae exactly, in
  values and in unwritten masks, and **0 mismatch**. The matching cases are
  unwritten WEIGHT_SPECTRUM in three forms, variable-shape DATA across
  spectral windows, partly filled columns, string arrays, the tiled
  managers, a big-endian table and empty subtables.
- **Refusals:** 55 refusals reduce to three reader tasks (section 6).
  - R1: IncrementalStMan refuses per manager, so the POINTING scalars of
    CASA-written MSs are refused.
  - R2: IncrementalStMan arrays and strings, such as POINTING `DIRECTION`.
  - R3: TiledCellStMan.

  Nothing in ra-ng reads POINTING today, so none of the three blocks a
  current path.
- **Parity, not reads:** 16 matches are both readers refusing a 0-row
  POINTING `DIRECTION` or `TARGET`.
- **Not covered:** the writer's own read path (`ms_write.rs`
  `is_defined`/`read_cells`).
- **ra-ng reads where arcae refuses:** 26 columns, all arcae 0.5.9 limits
  (a shape-[0] cell, whole reads of 0-row columns). Worth telling Simon.
- **xarray-ms:** equal to ra-ng on every variable it exposes in m01 to m07,
  NaN exactly at unwritten cells; it fails at open on an MS with no rows.
- **Post hoc:** six changes to `check`. One relaxes the frozen rule (bool
  against arcae's uint8); the others fix the harness (section 5).
- **Throughput:** not measured; a shared host gives no fair number.
- **Checks:** no reader code changed. `check_all --quick` passed; the full
  check is not needed.
- **Decision:** whether R1 and R2 wait for a POINTING consumer or are
  scheduled now.
