# casacure as the second oracle in the wheel test jobs (task T1)

Task T1 of [big-plan.md](big-plan.md), branch `t1-casacure-ci` from
`17adc1e`. Defined by the casacure evaluation
([casacure-evaluation.md](casacure-evaluation.md), verdict (c): casacure
reads every column column-exactly, its writes are not trusted, and it stays
an optional, exactly pinned second oracle) and by E3/E4
([e3-table-writer.md](e3-table-writer.md),
[e4-table-create.md](e4-table-create.md)), which used it as a read-back
oracle on the Linux host only.

Status: **plan frozen 2026-10-30** in the commit that adds this file,
after one scratch inventory (below) and before any implementation.

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

(to be written)

## Measured results

(to be written)
