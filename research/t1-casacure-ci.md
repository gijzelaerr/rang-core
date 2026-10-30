# casacure as the second oracle in the wheel test jobs (task T1)

Task T1 of [big-plan.md](big-plan.md), branch `t1-casacure-ci` from
`17adc1e`. Defined by the casacure evaluation
([casacure-evaluation.md](casacure-evaluation.md), verdict (c): casacure
reads every column column-exactly, its writes are not trusted, and it stays
an optional, exactly pinned second oracle) and by E3/E4
([e3-table-writer.md](e3-table-writer.md),
[e4-table-create.md](e4-table-create.md)), which used it as a read-back
oracle on the Linux host only.

Status: **implemented and measured locally 2026-10-30/31.** Plan frozen
2026-10-30 in `16b4321`, after one scratch inventory (below) and before any
implementation. Checks 1–3 pass on WSL (Linux x86_64) and natively on
Windows, in the editable checks and in `tools/wheel/test.py` against fresh
wheels (Python 3.10 and 3.14); macOS and aarch64 run first on the merge
push. Two casacure read defects found and pinned (Deviations).

## Question

The core's Measurement Set reader (`rang.core_ms`, task E) and table writer
(`rang.core_ms_write`, E3 and E4) are checked against python-casacore,
which runs only in the Linux container. On the Windows and macOS wheel test
jobs (`wheels.yml` `test`, `tools/wheel/test.py`) nothing checks them: the
one MS case of `tests/test_core_backends.py` skips with "MS oracle not
present" everywhere, because its inputs live in the ignored `outputs/`.
casacure 3.8.35 has wheels for Windows and macOS. Which oracle checks can
run through it on every platform, and do they pass there?

## Scratch inventory (measured before freezing)

`~/Build/tmp/20261030-t1/inventory.py` (scratch, deleted at the end): the
public fixture `outer_scans.zip` (45,452,147 bytes, SHA256 `d4dae56f…144f`,
`rang.notebook.data.FIXTURE_*`) extracted (82 MB, five MSs), every table
(MAIN and the 13 subtable directories; 70 tables) and every column (665)
read with `core_ms.getcol` and casacure 3.8.35's `getcol`, 1.2 s.

- **Scan 9 is ms0.** Every one of the 79 files the task E oracle receipt
  hashes for `outputs/tv-caracal-wsl-20261029-01/original.ms` (ms0) has the
  same SHA256 in the zip's `1672727931_sdp_l0_scan_9.ms` (the zip adds five
  `table.lock` files). So ms0, and with it the golden archive's MS entry
  (`ms0.ANTENNA`), can be rebuilt from the public download on any runner.
- 585 of 665 columns are column-exact between the two readers. The other
  80 are 16 per MS, the same in all five:
  - `MAIN.FLAG_CATEGORY` (TiledShapeStMan, never written): the core refuses
    (`row 0 has no tiled array`); casacure returns a `(nrow,)` bool array of
    False (E2 candidate 7).
  - `POINTING` `ANTENNA_ID`, `INTERVAL`, `NAME`, `NUM_POLY`, `TIME_ORIGIN`,
    `TRACKING` (one IncrementalStMan that holds the string column NAME): the
    core refuses all six (`supported: false`); casacure reads the five
    numeric ones and refuses NAME (`IncrementalStMan strings are not
    supported yet`).
  - String-array columns `FEED.POLARIZATION_TYPE`, `HISTORY.APP_PARAMS`,
    `HISTORY.CLI_COMMAND`, `OBSERVATION.LOG`, `OBSERVATION.SCHEDULE`:
    `core_ms.getcol` fails with misleading errors (`io: No such file or
    directory`; `read of 130023424 bytes at 6 failed`): the task E reader
    treats a string array as an indirect numeric array (E4's open item).
    `core_ms_write.read_cells` reads them; casacure returns them from
    `getcol` as `{'shape', 'array'}` (python-casacore's convention) and per
    row from `getvarcol`.
  - The columns of the two 0-row tables FLAG_CMD and PROCESSOR: casacure
    returns an empty int32 array for every column (E3's twelfth casacure
    item); the four non-int32 ones differ in dtype, the int32 ones are
    equal only by accident.
- casacure's Python API has no `info()` (no `table.info` read) and no
  `iscelldefined`; it has `getkeywords`, `getcolkeywords`, `getcoldesc`,
  `getdminfo`, `getvarcol`, `getcell`, `getsubtables`.
- The core has no keyword read in Python (`core_ms.Table.description` holds
  `nrows`, `path`, `little_endian` and the columns; no keywords).

## PyPI wheel coverage of casacure 3.8.35 (PyPI JSON, 2026-10-30)

| Matrix cell (`wheels.yml` `test`) | 3.10 | 3.14 |
| --- | --- | --- |
| linux-x86_64 (`manylinux_2_17_x86_64`) | wheel | wheel |
| linux-aarch64 (`manylinux_2_17_aarch64`) | wheel | wheel |
| macos-arm64 (`macosx_11_0_arm64`) | **none** (cp311–cp314 only) | wheel |
| macos-x86_64 | **none** (no x86_64 macOS wheel at all) | **none** |
| windows-x86_64 (`win_amd64`) | wheel | wheel |

Otherwise only the 440 kB sdist, whose build needs Rust and a C compiler
(`zstd-sys`) and takes about a minute on the host (E2). The extra never
builds it: its environment marker lists exactly the platforms with wheels
and the test installs with `--no-build-package casacure` (uv) or
`--only-binary casacure` (pip). So **macOS acceptance means macos-arm64 on
Python 3.14 only**; the three cells without a wheel are a frozen list
(below) and an upstream observation.

## Plan (frozen)

### What moves from "skipped" to "runs through casacure"

1. **The MS reader.** For every table of the five fixture MSs (MAIN and
   every subtable directory): `nrows` and the set of column names equal in
   `core_ms` and casacure; MAIN's subtable links (casacure's `Table:`
   keywords) name exactly the subtable directories present. For every
   column of a table with rows: the core's full `getcol` equals casacure's
   (dtype, shape, bytes; NaN payloads and signed zeros count; strings by
   value), and so do rows [0, 1) and [3, 5) where the table has five rows or
   more. String-array columns are read in the core with
   `core_ms_write.read_cells` and compared cell by cell with casacure's
   `getvarcol` (deviation from "read by `rang.core_ms`": that reader cannot
   read them). The columns not compared are the frozen list of the
   inventory: per MS, `MAIN.FLAG_CATEGORY` and the six POINTING
   IncrementalStMan columns; the test asserts the core still refuses exactly
   these (and that casacure still refuses POINTING NAME and returns the
   `(nrow,)` False FLAG_CATEGORY), so drift in either reader fails. 0-row
   tables are compared on `nrows` and column names only.
   **The golden archive's MS entry:** casacure's read of ms0's ANTENNA
   (scan 9) equals the archived leaves `ms.1` (NAME), `ms.2` (POSITION),
   `ms.3` (POSITION rows 1–2) and `ms.4` (FLAG_ROW) byte for byte on every
   platform (these are file reads, not libm results), and the archived
   description's column names and dtypes equal casacure's `getcoldesc`.
   Keywords cannot be compared core against casacure (the core reads
   none); casacure's keyword fidelity on these tables is E2's R5 (keywords
   identical to python-casacore on ms0, ms1, ms2), and keywords are gated in
   check 2.
2. **The table writer (E3) and creation (E4).** On copies of scan 9 in the
   test's temporary directory, the core writes and casacure reads back:
   every written cell equals the value written and every untouched column
   equals casacure's read of the input (made, and the casacure table
   closed, before the core opens the copy for writing: casacure memory-maps
   its files, E2 candidate 4); table and column keywords after the writes
   equal those before plus the written ones. One test per case so that a
   first failure names the storage manager:
   - W-tiled: `putcol` of FLAG and WEIGHT_SPECTRUM rows 10–14
     (TiledShapeStMan), UVW (TiledColumnStMan); `putcell` of DATA row 3.
   - W-standard: `putcol` of FLAG_ROW (StandardStMan scalar) and
     ANTENNA1; SPECTRAL_WINDOW `CHAN_FREQ` (indirect array); ANTENNA `NAME`
     (strings shorter and longer than the stored ones); FEED
     `POLARIZATION_TYPE` (string array, `putcell`).
   - W-keywords: table keywords (Double, Int, String, Double array,
     sub-record) and column keywords (a new String on DATA, a replaced
     `QuantumUnits` on UVW).
   - W-addcols: `addcols` with the default binding (complex64 [64, 4]) and
     into a new TiledColumnStMan (Bool) and TiledShapeStMan (Float), each
     followed by `putcol`; casacure's `getdminfo` names the managers.
   - C-table: `create_table` with scalar Int and String, fixed Double
     array, variable Float array with undefined cells, variable and fixed
     string arrays, a table keyword: defined cells equal; what casacure
     returns for the undefined cells is recorded, not gated (it has no
     `iscelldefined`).
   - C-rows: `addrows` and `removerows` on a new StandardStMan table.
   - C-tiled: a new TiledShapeStMan table extended by `addrows`.
   - C-default-ms: `default_ms`: casacure opens MAIN and every subtable,
     `nrows` 0, column names equal the core's, the subtable links point at
     the subtable directories.
   - C-caltable: a G Jones table from `create_caltable`: every defined
     MAIN cell, the ANTENNA subtable and the keywords (ParType, MSName,
     VisCal, PolBasis, subtable links) equal what was written. `table.info`
     is not checked by casacure (no `info()`); the core's own test checks
     its text.
   casacure's writes are **not** used as a reference anywhere (E2 verdict
   (c): it accepts invalid descriptions and writes tables casacore cannot
   open); it only reads.
3. **The backend golden test's MS entry** (`tests/test_core_backends.py::
   test_ms_reader`, the core against the archive, no casacure needed) runs
   on every job instead of skipping: when `RANG_FIXTURE` names the fixture
   zip (or `outputs/` is absent but the zip is found), it reads ANTENNA
   from scan 9 extracted into the test's temporary directory and sets the
   description's `path` to the archived value before dumping it (the
   archived string carries the ms0 path, and `json.dumps` escapes
   backslashes on Windows, so the `str(ROOT)` replacement never matched
   there). A minimal hunk in a coordinator file, listed in "For the
   coordinator".

### What stays skipped, and where

- Docker-only byte comparisons stay Linux-only and outside the wheel job:
  `examples/check_ms_writer.py` and `check_ms_create.py` (byte identity with
  casacore 3.8.1 and CASA 6.7.6), and the archived-run spot checks of
  `tests/test_core_ms_write.py` and `tests/test_e4_table_create.py`.
- `tests/test_core_ms.py` and `tests/test_casacure_optional.py` (E2) still
  need the task E oracle dump and the LUNO and imaging MSs in `outputs/`;
  unchanged.
- The T1 tests skip with "casacure 3.8.35 has no wheel for this platform"
  on exactly macos-x86_64 (3.10, 3.14) and macos-arm64 3.10 (`sys.platform
  == "darwin"` and machine x86_64 or Python < 3.11), with "casacure not
  installed" elsewhere when it is absent, with "casacure <v> installed, the
  oracle is pinned to 3.8.35" on a version mismatch, and with "fixture MS
  not present" without the zip. In the wheel test only the first is
  allowed when `--fixture-cache` is given; without it (a local run with no
  network) the fixture skips stay allowed as now.

### Implementation (owner files)

- `pyproject.toml`: the extra `casacure = ["casacure==3.8.35; <marker>"]`,
  marker = the wheel table above. Named after the one package it installs,
  as E2 proposed it; `oracle` would suggest python-casacore too, which is
  in `flagging` and Linux-only.
- `python/rang/oracles/__init__.py`, `python/rang/oracles/casacure.py`: a
  thin read-only adapter (no write call is exposed): `PIN = "3.8.35"`,
  `available()`, `open_table(path)` (refuses any other installed version),
  `Table.nrows`, `colnames()`, `getcol(name, startrow, nrow)` in the core's
  conventions (string columns as object arrays; string arrays from the
  `{'shape', 'array'}` record), `getcells(name)` (per-row cells from
  `getvarcol`, strings as object arrays), `keywords()`, `colkeywords(name)`
  (NumPy scalars and arrays normalised to Python values), `subtables()`
  (link names), `coldesc(name)`, `managers()` (column to `getdminfo` TYPE),
  `close()` and a context manager.
- `tests/test_t1_casacure_oracle.py`: checks 1 and 2 above; finds the zip
  through `rang.notebook.data.find_fixture()` (`RANG_FIXTURE` or
  `outputs/ska-pointing/outer_scans.zip`), checks its SHA256 and extracts
  the five MSs once per session with the archive-member guards of
  `rang.notebook.data`.
- `tools/wheel/test.py`: installs `wheel[test,imaging,casacure]` with the
  sdist build blocked; new option `--fixture-cache DIR`: a `fixture` step
  runs `rang.notebook.data.download_fixture(DIR)` in the venv (hash
  verified, nothing downloaded when a verified copy is there) and the
  pytest step gets `RANG_FIXTURE=<zip>` (the one `RANG_*` variable set on
  purpose); adds `tests/test_t1_casacure_oracle.py` to the pytest step; the
  skip filter as above.
- `.github/workflows/wheels.yml` `test` job: `actions/cache@v4` of
  `~/.cache/rang-fixture` keyed on the fixture SHA256 (as `docs.yml`), and
  `--fixture-cache "$HOME/.cache/rang-fixture"` on the test step.

### Acceptance (frozen)

- The new tests pass, with no skip other than the frozen no-wheel cells, in
  the `test` matrix of `wheels.yml` (five platforms × 3.10 and 3.14, casacure
  from PyPI); this runs first on the merge push (this task never pushes),
  so before the merge it is checked locally: `tools/wheel/test.py` with
  `--fixture-cache` against a freshly built wheel on WSL (Linux x86_64) and
  on native Windows, `python -m rang.check` in a native Windows worktree,
  and `bash tools/check-all.sh` (`overall: PASS`) on WSL. macOS runs only
  in CI.
- The added wall per test job (casacure install, the fixture step with a
  warm cache, the new tests) stays under 3 minutes; measured locally here,
  and from the first CI run by the coordinator.
- `actionlint` clean on the workflow.

## Implementation

Commits after the frozen plan (`16b4321`): `2ac9eda` (extra, adapter,
tests), `3d6a08c` (wheel test, workflow, the golden-test hunk), `77ade3e`
(adapter guard for ragged columns, found while measuring), `9ce0332`
(`--only-binary` for uv too).

- `pyproject.toml`: `casacure = ["casacure==3.8.35; <marker>"]`, the marker
  true on exactly Linux x86_64/aarch64, Windows AMD64 and macOS arm64 with
  Python ≥ 3.11 (checked with `packaging` on the six matrix cases).
- `python/rang/oracles/casacure.py` (147 lines): reads only. `open_table`
  refuses any casacure other than 3.8.35; `getcol` returns string columns
  and `{'shape', 'array'}` string-array records as object arrays and
  **refuses a variable-shape numeric column whose rows differ in shape**
  (casacure's own `getcol` silently returns such a column in the first
  row's shape; observation 2 below); `getcells` (from `getvarcol`, keys taken
  in numeric order because casacure numbers them from the first row read);
  `keywords`, `colkeywords` (NumPy values as plain Python), `subtables`,
  `coldesc`, `managers` (`getdminfo` TYPE per column).
- `tests/test_t1_casacure_oracle.py` (15 tests): `test_core_reader_equals_casacure`
  ×5 MSs, `test_casacure_equals_the_golden_ms_entry`, the four write cases
  (`tiled`, `standard`, `keyword`, `addcols`) and the five creation cases
  (`created_table`, `rows`, `created_tiled`, `default_ms`, `caltable`).
  Module-level skips as frozen.
- `tools/wheel/test.py`: extras `test,imaging,casacure`, `--only-binary
  casacure` (uv and pip), `--fixture-cache DIR` (step `fixture`,
  `RANG_FIXTURE` for pytest), the new test file, the skip filter as frozen.
- `.github/workflows/wheels.yml`: `actions/cache@v4` of `~/.cache/rang-fixture`
  with `docs.yml`'s key, `--fixture-cache "$HOME/.cache/rang-fixture"`.
- `tests/test_core_backends.py` (coordinator's file, minimal hunk):
  `_fixture_antenna` and the fixture-first `test_ms_reader`.

## Measured results (2026-10-30/31)

### What now runs where

| Check | Linux x86_64 / aarch64 (3.10, 3.14) | Windows x86_64 (3.10, 3.14) | macOS arm64 3.14 | macOS arm64 3.10, macOS x86_64 |
| --- | --- | --- | --- | --- |
| 1. core reader = casacure, 5 MSs, 70 tables, 665 columns | runs (measured on WSL x86_64) | runs (measured natively) | runs (CI only) | skips: no casacure wheel |
| 1. golden MS entry through casacure | runs | runs | runs | skips: no wheel |
| 2. E3 writes and E4 creation read back by casacure (9 tests) | runs | runs | runs; the writer's first test on macOS | skips: no wheel |
| 3. `test_core_backends.py::test_ms_reader` (core vs archive) | runs from the fixture | runs from the fixture | runs | **runs** (no casacure needed) |
| Byte identity with casacore/CASA (`check_ms_writer.py`, `check_ms_create.py`, archived spot checks), `test_core_ms.py`, `test_casacure_optional.py` | Linux host with `outputs/` and Docker only | — | — | — |

aarch64 and macOS are not measured here: they run first on the merge push.

### Results

- **Check 1 passes** on WSL and natively on Windows: in each MS every
  column with rows is column-exact between `core_ms` and casacure (full
  column, rows [0, 1) and [3, 5)), string arrays cell by cell through
  `read_cells`; the frozen refusal lists hold exactly (FLAG_CATEGORY and the
  six POINTING IncrementalStMan columns in the core; POINTING NAME and the
  `(nrow,)` False FLAG_CATEGORY in casacure); `nrows`, column names and
  MAIN's 13 subtable links agree. More than 100 columns compared per MS.
- **The golden MS entry** read by casacure equals the archived leaves
  `ms.1`–`ms.4` byte for byte and the archived description's names and
  dtypes, on both.
- **Check 2 passes** on both: every written cell (TiledShapeStMan FLAG,
  WEIGHT_SPECTRUM rows 10–14 and DATA row 3; TiledColumnStMan UVW;
  StandardStMan FLAG_ROW, ANTENNA1, indirect CHAN_FREQ, NAME strings, the
  FEED string array; the three `addcols` columns, with the managers
  casacure reports), every untouched column, and the table and column
  keywords (Double, Int, String, Double array, sub-record; a new and a
  replaced column keyword) read back in casacure as written; the five E4
  creations read back (defined cells, rows after `addrows`/`removerows`,
  the tiled table, `default_ms`'s 12 subtables and links, the G Jones
  table's cells, keywords and 5 subtable links). Two measured exceptions,
  both casacure's (observations 1 and 2 below), are pinned in the test as
  casacure refusals rather than compared: the fixed-shape Direct string
  array `SD` of C-table, and `getcol` of the ragged column `V`.
- Undefined cells (recorded, not gated; `outputs/t1-20261030-01/undefined-cells.json`):
  casacure's `getcell` returns a 0-d `0.0` for an undefined cell of a
  variable-shape Float column (casacore raises; casacure issue #8 says
  defaults are by design), `getvarcol` the same per row; the core's
  `read_cells` returns None.
- **Check 3 passes**: `test_ms_reader` runs from the fixture zip in both
  wheel tests on WSL and Windows (no skip), and from `outputs/` in the
  editable checks; the archive is unchanged.
- **Wheel tests**, `tools/wheel/test.py --fixture-cache` against fresh
  wheels: WSL `rang_core-0.1.0-cp310-abi3-manylinux_2_35_x86_64.whl`
  (SHA256 `78697754…994e`), Python 3.10.22 and 3.14: `overall: PASS`, 52
  passed, 0 skipped each, `casacure==3.8.35` in the freeze. Native Windows
  `rang_core-0.1.0-cp310-abi3-win_amd64.whl` (`5abe8f29…fa53`), Python 3.10
  and 3.14: `overall: PASS`, 47 passed, 5 skipped each (only the P7 toy
  skips "archived on Linux x86_64", allowed as before).
- **Added time per job** (local): casacure in the install step (a 2 MB
  wheel; the install steps took 3.2 s and 0.2 s on WSL, 6.4 s and 1.0 s on
  Windows), the `fixture` step 4.6–4.9 s with a download and 0.5–1.2 s
  with a verified copy, the T1 tests 2.7 s in process (3.3 s with
  start-up) on WSL (the pytest step without the T1 file took 16.6 s in the
  same venv, with it 16.9 s: within the shared host's noise). So about
  10 s per job locally, plus the cache
  restore on the runner: well under the 3-minute bound. The CI numbers
  come with the first run.
- `actionlint` (via `actionlint-py`) on `wheels.yml`: clean.
- `bash tools/check-all.sh` on WSL: `overall: PASS` (Rust 23 + 126 tests, clippy, fmt, extension build, ruff, ruff format, diff-check, pytest 682 passed and 13 skipped in 322 s; log `outputs/t1-20261030-check-all.log`). Native Windows
  `python -m rang.check`: `overall: PASS` (pytest 651 passed, 44 skipped, the skips being the `outputs/`-dependent tests; `RANG_FIXTURE` set, so the T1 tests ran; log copied to `outputs/t1-20261030-01/windows-check.log`).

## Deviations

- Check 1's keywords are not compared core against casacure (the core
  reads no keywords; stated in the frozen plan); they are gated in check 2.
- String arrays are read in the core by `core_ms_write.read_cells`, not
  `core_ms` (frozen in the plan).
- C-table's fixed-shape string array `SD` is not compared: casacure cannot
  read a Direct fixed-shape string array at all, also one python-casacore
  3.8.1 wrote (measured after the freeze: `outputs/t1-20261030-01/sd-*.txt`);
  the test pins the refusal. The core's SD stays covered by E4's
  python-casacore read-back (criterion 3).
- The adapter's `getcol` refuses ragged variable-shape columns (added after
  the freeze, when casacure's truncation showed up); the C-table test pins
  it.
- The plan named uv's `--no-build-package`; uv 0.12.23 (WSL) has no such
  option, so `--only-binary casacure` is used with uv and pip alike.
- The fixture is found by `RANG_FIXTURE`; the wheel test sets this one
  `RANG_*` variable on purpose (the clean environment drops the others).

## Open items

- The CI run itself (aarch64, macOS arm64 3.14, the runners' times and the
  cache on Windows, whose `$HOME` in Git Bash is `/c/Users/runneradmin`,
  converted to a native path by MSYS for `test.py`) happens on the merge
  push.
- macOS x86_64 and macOS arm64 3.10 have no casacure oracle until casacure
  publishes those wheels (or the job builds the sdist, which needs Rust
  and about a minute; not done to keep the job short and the pin exact).
- The core writer's first macOS run is this job (E3 says it was never
  compiled or tested there; macOS writes without the inter-process lock).
- The core reader (`core_ms.getcol`) fails on string-array columns with
  misleading errors (`io: No such file or directory`; `read of 130023424
  bytes at 6 failed`) instead of a clean refusal or a read: an E5 item
  (`ms.rs` should route string arrays to the `read_cells` path or refuse
  them by name).
- casacure has no `info()`, so `table.info` stays checked by the core's own
  tests and E4's oracles only.

## Timings

2026-10-30/31, WSL host shared with four other tasks unless marked
Windows. Wall from `/usr/bin/time` or `Stopwatch`; RSS peak resident.

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin pip casacure==3.8.35` | worktree | 87.5 s | 1.21 GB | builds the extension |
| 2026-10-30 | scratch inventory, `core_ms` vs casacure | 5 fixture MSs, 70 tables, 665 columns | 1.20 s | 165 MB | includes extracting the 45 MB zip (82 MB) |
| 2026-10-30 | container python-casacore probes (string array, ragged column) | synthetic tables | < 2 s each | — | `rang-ms-reader:local` |
| 2026-10-30 | `pytest tests/test_t1_casacure_oracle.py` | fixture zip | 2.7 s (3.3 s process) | 238 MB | 15 passed |
| 2026-10-30 | `tools/wheel/build.py` (Linux) | worktree | 181.8 s | 1.14 GB | `CARGO_BUILD_JOBS=4`, shared host |
| 2026-10-30 | `tools/wheel/test.py --python 3.10 --fixture-cache` (WSL) | Linux wheel | 24.6 s | 256 MB | fixture downloaded 4.9 s; pytest 15.7 s; 52 passed |
| 2026-10-30 | same, `--python 3.14`, warm cache | Linux wheel | 18.4 s | 261 MB | fixture verify 0.5 s; pytest 16.9 s; 52 passed |
| 2026-10-30 | `actionlint` (`uv tool run --from actionlint-py`) | `wheels.yml` | 0.9 s | — | clean |
| 2026-10-30 | Windows: `uv venv` + editable install as above | worktree | 269.9 s | — | includes the extension build; shared host |
| 2026-10-30 | Windows: `pytest` T1 + `test_core_backends.py` | fixture zip | 12.3 s | — | 28 passed |
| 2026-10-30 | Windows: `tools\wheel\build.py` | worktree | 226.3 s | — | `win_amd64` wheel |
| 2026-10-30 | Windows: `tools\wheel\test.py --python 3.10 --fixture-cache` | Windows wheel | 38.3 s | — | fixture downloaded 4.6 s; pytest 24.6 s; 47 passed, 5 P7 skips |
| 2026-10-30 | Windows: same, `--python 3.14` | Windows wheel | 28.1 s | — | pytest 24.3 s |
| 2026-10-30 | `bash tools/check-all.sh` (`OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`) | branch at `9ce0332` | 1,291 s including the lock wait | 1.89 GB | PASS; pytest 682 passed, 13 skipped in 322 s |
| 2026-10-31 | Windows: `python -m rang.check` | branch at `9ce0332` | 696.5 s | — | PASS; pytest 651 passed, 44 skipped in 151 s |

## For the coordinator

**Shared-file hunks.**

`tests/test_core_backends.py` (on the branch, commit `3d6a08c`): verbatim

```diff
diff --git a/tests/test_core_backends.py b/tests/test_core_backends.py
index 5dc50bd..886611f 100644
--- a/tests/test_core_backends.py
+++ b/tests/test_core_backends.py
@@ -386,19 +386,45 @@ def test_flag_rows(golden):
     )


-def test_ms_reader(golden):
-    receipt = ROOT / "outputs/core-e-oracle-20261029-01/receipt.json"
-    if not receipt.is_file():
-        pytest.skip("MS oracle not present")
-    entry = json.loads(receipt.read_text())["tables"]["ms0.ANTENNA"]
-    path = ROOT / "outputs" / Path(*Path(entry["path"]).parts[2:])
-    if not path.is_dir():
-        pytest.skip("fixture MS not present")
+def _fixture_antenna(tmp_path):
+    """ms0's ANTENNA from the public fixture zip named by RANG_FIXTURE: scan
+    9 is ms0 file for file (research/t1-casacure-ci.md), so this runs where
+    outputs/ is absent (the wheel test jobs), or None."""
+    import zipfile
+
+    from rang.notebook import data as fixture_data
+
+    source = os.environ.get("RANG_FIXTURE")
+    if not source or not Path(source).is_file():
+        return None
+    if fixture_data._sha256(source) != fixture_data.FIXTURE_SHA256:
+        pytest.fail(f"{source} is not the pinned public fixture")
+    prefix = fixture_data.FIXTURE_SCAN + "/ANTENNA/"
+    with zipfile.ZipFile(source) as zipped:
+        for info in fixture_data._safe_members(zipped, prefix):
+            zipped.extract(info, tmp_path)
+    return tmp_path / prefix
+
+
+def test_ms_reader(golden, tmp_path):
+    path = _fixture_antenna(tmp_path)
+    if path is None:
+        receipt = ROOT / "outputs/core-e-oracle-20261029-01/receipt.json"
+        if not receipt.is_file():
+            pytest.skip("MS oracle not present")
+        entry = json.loads(receipt.read_text())["tables"]["ms0.ANTENNA"]
+        path = ROOT / "outputs" / Path(*Path(entry["path"]).parts[2:])
+        if not path.is_dir():
+            pytest.skip("fixture MS not present")
     assert core_ms.has_reader()
     with core_ms.open_table(path) as table:
+        # The archive's path (ms0 in outputs/), whichever copy was read.
+        description = dict(table.description)
+        description["path"] = (
+            "<ROOT>/outputs/tv-caracal-wsl-20261029-01/original.ms/ANTENNA"
+        )
         out = [
-            # Subtable keywords carry absolute paths; make them checkout-independent.
-            json.dumps(table.description, sort_keys=True).replace(str(ROOT), "<ROOT>"),
+            json.dumps(description, sort_keys=True),
             [str(x) for x in table.getcol("NAME")],
             table.getcol("POSITION"),
             table.getcol("POSITION", 1, 2),
```

`research/STATE.md`, at the top:

> T1 casacure as the second oracle (big plan), 2026-10-30 (implemented;
> measured locally; [t1-casacure-ci.md](t1-casacure-ci.md)). Plan frozen
> first. An optional `[casacure]` extra (`casacure==3.8.35`, with a marker
> for the platforms that have wheels: none for macOS x86_64 or for cp310 on
> macOS arm64) and a read-only adapter `rang.oracles.casacure`. The wheel
> test (`tools/wheel/test.py --fixture-cache`, `wheels.yml` `test` jobs)
> now downloads the public fixture (45 MB, hash-verified, cached) and runs
> `tests/test_t1_casacure_oracle.py`: the core reader against casacure on
> every column of the five fixture MSs (70 tables), the golden archive's MS
> entry through casacure, and the core's E3 writes and E4 creations read
> back by casacure (cells and keywords; casacure's writes are never a
> reference). The backend golden test's MS case now runs from the fixture
> (scan 9 is ms0 file for file) instead of skipping, on every job including
> macOS x86_64. Passes on WSL and natively on Windows (Python 3.10 and
> 3.14, wheels built fresh, no unexpected skip); macOS and aarch64 run on
> the merge push. Two new casacure defects: it cannot read a fixed-shape
> Direct string array even when casacore wrote it, and its `getcol` of a
> ragged variable-shape column silently returns the first row's shape (the
> adapter refuses it). The core reader's misleading errors on string-array
> columns are an E5 item. Next: the first CI run's timings.

`research/README.md` index entry:

> New, 2026-10-30: T1, [casacure in the wheel tests](t1-casacure-ci.md):
> casacure 3.8.35 as the second oracle of the core's reader, writer and
> table creation on Linux, Windows and macOS arm64 3.14, on the public
> fixture; the golden MS case runs on every job.

`research/big-plan.md`: mark T1 done 2026-10-30 (`t1-casacure-ci.md`).

`research/tool-timings.md`: the rows of the Timings table above.

`research/non-ratt-observations.md`, a new section:

> ## From T1 (2026-10-30; not reported by decision, casacure is outside the reporting rule)
>
> | Software | Observation | Evidence | What a report would say | Status |
> | --- | --- | --- | --- | --- |
> | casacure 3.8.35 (Tim Molteno) | A Direct fixed-shape string-array column (`makearrcoldesc(..., shape=[2], options=1)`) cannot be read at all: `getcol` and `getcell` raise `bad string reference: bucket 0, offset 8, length 0`, also for a table python-casacore 3.8.1 wrote; casacore and the rang core read it | `outputs/t1-20261030-01/sd-casacore.txt`, `sd-casacure.txt` | Read Direct string arrays (casacore stores them in the StandardStMan string buckets) | not reported by decision |
> | casacure 3.8.35 | `getcol` of a variable-shape array column whose rows differ in shape returns an array in the first row's shape, silently dropping the rest of every longer row; casacore raises `StManIndArray::get/put shapes not conforming` | `outputs/t1-20261030-01/ragged-*.txt` | Raise, as casacore, or return per-row cells | not reported by decision |
> | casacure 3.8.35 | `getcell`/`getvarcol` of an undefined cell return a 0-d `0.0` (casacore raises); no `iscelldefined` and no `info()` in the Python API | `outputs/t1-20261030-01/undefined-cells.json` | Raise or return None for undefined cells; add `iscelldefined` and `info` | not reported by decision (defaults by design, issue #8) |
> | casacure 3.8.35 | `getvarcol(name, start, n)` numbers its keys from the first row read (`r1`…), python-casacore from row 0 (`r{start+1}`…) | this file, Implementation | Use python-casacore's numbering | not reported by decision |
> | casacure 3.8.35 | No macOS x86_64 wheel and no cp310 macOS arm64 wheel on PyPI (Linux and Windows cover cp310–cp314) | PyPI JSON, 2026-10-30 | Publish them (the Windows/macOS wheels are not tested upstream either, E2 candidate 9) | not reported by decision |

**Ignored outputs.** `outputs/t1-20261030-01/` (`undefined-cells.json`,
`sd-casacore.txt`, `sd-casacure.txt`, `ragged-casacore.txt`,
`ragged-casacure.txt`; a few kB) and `outputs/t1-20261030-check-all.log`.

**Scratch.** `~/Build/tmp/20261030-t1` (inventory and probe scripts, the extracted fixture, the Linux wheel and its test venvs) and, on Windows, `C:\Users\gijsm\Build\tmp\20261030-t1-win` (fixture cache, wheel, test venvs) are deleted at the end of the task; the Windows worktree and its branch copy are removed.
