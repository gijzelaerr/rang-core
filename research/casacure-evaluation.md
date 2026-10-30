# casacure evaluation (task E2)

Task E2 of [big-plan.md](big-plan.md), branch `e2-casacure` from `29d67b4`.
Protocol frozen 2026-10-30 in the commit that adds this file, before any
measurement beyond opening the three MSs once to see whether casacure reads
them at all (it opened all three and returned DATA, FLAG, UVW, TIME and
WEIGHT_SPECTRUM with python-casacore's dtypes and shapes; nothing compared).
Status: **protocol frozen; nothing measured.**

The question: should **casacure** (Tim Molteno,
<https://github.com/tmolteno/casacure>, LGPL-3.0-or-later; crate and PyPI
wheel `casacure` 3.8.35, released 2026-10-21), a pure-Rust reimplementation
of the casacore table system, become the Measurement Set and casacore-table
I/O layer of the rang core, given the user's decision (2026-10-30) that the
core must read **and write** every format of the tools it replaces? And is
its code good enough to adopt, or should rang build its own table layer on
task E's reader (scope extension from the coordinator, same day: the user's
default is to build it ourselves unless the code is good enough)?

Under AGENTS.md this is an engineering evaluation, not a scientific result;
no archived result changes because of it.

## Inputs (frozen)

- casacure **3.8.35** from public PyPI (wheel SHA256 recorded in the
  receipts) and the crate `casacure = "=3.8.35"` from crates.io (checksum
  `5c7f5afe…`); source for the code review: a clone of
  `tmolteno/casacure` at the head of `main` on 2026-10-30, in
  `~/Build/tmp/20261030-casacure` (deleted at the end).
- The three MSs of task E, read in place and never written:
  ms0 fixture `outputs/tv-caracal-wsl-20261029-01/original.ms`
  (IncrementalStMan, StandardStMan, TiledShapeStMan, TiledColumnStMan), ms1
  LUNO export `outputs/luno-solve-20261029-02/work.ms` (StandardStMan only),
  ms2 imaging `outputs/tv-next-imaging-wsl-20261029-01/caracal-diagnostic.ms`
  (adds CORRECTED_DATA). Writes go only to copies in fresh
  `outputs/e2-casacure-20261030-NN` directories.
- **Oracle:** task E's frozen python-casacore 3.8.1 dump
  `outputs/core-e-oracle-20261029-01` (173 columns of 15 tables, file
  SHA256 of every MS file in `receipt.json`); its comparator precondition
  (two dumps equal, 173 of 173 perturbations caught) was measured by task E
  (`outputs/core-e-check-20261029-01`) and is not repeated. Fresh oracle
  reads of written or converted tables use the same script,
  `examples/oracle_ms_columns.py`, in the image built from
  `tools/ms-reader/Dockerfile` (`rang-ms-reader:local`, python-casacore
  3.8.1, NumPy 2.5.3; the earlier `rang-flagging:local` image is pruned).
- **Comparator:** `compare_table` / `compare_arrays` / `compare_strings`
  imported from `examples/check_ms_reader.py` unchanged, so "column-exact"
  means what it meant in task E: same dtype, same shape, same bytes (NaN
  payloads and signed zeros count); strings by value.
- astropy 8.0.2 with `astropy-iers-data` 0.2026.10.19, IERS auto-download
  off, for the measures comparison.

## Criteria (frozen before measurement)

Gated criteria decide the "works" verdict; reported items inform the
recommendation and are not pass/fail. Every run's receipts go to
`outputs/e2-casacure-20261030-NN/` with `result.json`.

### 1. Reads

- **R1 (gated).** For every table and column in the oracle receipt (173
  columns, 15 tables), casacure's Python `getcol` of the full column equals
  the oracle column-exactly, and so do reads of rows [0, 1) and [3, 5)
  (`getcol(name, start, n)`), as task E's criteria 1 and 2.
- **R2 (gated).** The SHA256 of every MS file except `table.lock` is
  unchanged by the casacure reads. `table.lock` before and after is
  reported separately (a reader that rewrites lock files is a finding).
- **R3 (gated).** A Rust program built against the crate with Rust 1.93
  (`cargo +1.93`, rang's toolchain pin) reads the same 173 columns and its
  bytes equal the oracle's (numeric columns; strings by value). If the
  crate does not build with 1.93, R3 fails as frozen and the build error
  is recorded; the program is then built with the stable toolchain and
  the comparison reported.
- **R4 (reported).** casacure equals `core_ms` on the same reads (implied by
  R1 and task E's pass, checked directly).
- **R5 (reported).** Column descriptions, data-manager info and table and
  column keywords from casacure against python-casacore's
  (`getcoldesc`, `getdminfo`, `getkeywords`, `getcolkeywords`) for the
  main table and the four subtables; variable-shape columns
  (`getvarcol`) where present; FLAG_CATEGORY (casacore itself cannot read
  it) reported.
- **R6 (gated).** Big-endian tables: the container deep-copies ms0 and ms1
  with `endian='big'` (python-casacore `table.copy(..., deep=True,
  valuecopy=True, endian='big')`), the copies' `getdminfo` is recorded,
  and casacure's and `core_ms`'s full-column reads of the copies equal the
  oracle `-01` arrays column-exactly (values are endian-independent once
  read). `core_ms`'s byte-swap path was untested in task E; its result is
  reported, casacure's gates.
- **R7 (reported).** TaQL. rang's live drivers use no TaQL (contiguous row
  ranges and NumPy masks; grep 2026-10-30). Five selections of the kind
  the drivers do in NumPy are run in casacure and in python-casacore (the
  container) and the selected row numbers and one selected column are
  compared exactly: `FIELD_ID == 1`, `ANTENNA1 != ANTENNA2`,
  `SCAN_NUMBER == <first>` with `ORDERBY TIME, ANTENNA1, ANTENNA2`,
  `TIME BETWEEN t0 AND t1`, and `SELECT UNIQUE ANTENNA1`.

### 2. Writes

- **W1 (gated).** casacure creates a `default_ms`, adds 140 rows and
  writes the fixture's main columns (DATA, FLAG, FLAG_ROW, WEIGHT,
  WEIGHT_SPECTRUM, SIGMA, UVW, TIME, ANTENNA1, ANTENNA2, DATA_DESC_ID,
  FIELD_ID, SCAN_NUMBER, INTERVAL, EXPOSURE, TIME_CENTROID), a MODEL_DATA
  column (the fixture's DATA times 0.5, so it is distinguishable), and
  the ANTENNA, SPECTRAL_WINDOW, FIELD and POLARIZATION subtables from the
  oracle arrays, in two variants: (a) default managers, (b) dminfo asking
  TiledColumnStMan for DATA, FLAG and WEIGHT_SPECTRUM. python-casacore in
  the container reads every written column back (`oracle_ms_columns.py`)
  and it equals the written array column-exactly; `getdminfo` of the
  result is recorded and, for (b), must name TiledColumnStMan for the
  three columns (the open-issue premise of the brief, casacure issue #20,
  closed upstream 2026-10-10).
- **W2 (reported).** `core_ms` reads both written MSs and equals the same
  arrays (it may refuse a manager it does not support; that is recorded).
- **W3 (reported).** Interop the other way: python-casacore in the
  container writes a column (`putcol` of FLAG with a pattern) into a copy
  of the casacure-written MS (a), casacure reads it back and equals the
  pattern.
- **W4 (gated).** In-place writes on copies: on a copy of ms0 (FLAG in
  TiledShapeStMan, which the casacure README does not list as writable)
  and of ms1 (StandardStMan), casacure writes a FLAG pattern with
  `putcol`, adds CORRECTED_DATA (`addcols`, the fixture DATA times
  (1 + 1j)) and writes it; python-casacore reads FLAG, CORRECTED_DATA
  and every other oracle column back; the written columns equal what was
  written and every other column equals the oracle. Reported: whether the
  FLAG column's manager changed, and which files changed bytes (SHA256
  before and after; a rewrite of unrelated files is a finding even when
  the values are equal, cf. casacure issue #22).
- **W5 (reported).** A CASA calibration table: a small synthetic G Jones
  table (4 antennas, 3 times, 1 spw, 2 correlations; columns TIME,
  FIELD_ID, SPECTRAL_WINDOW_ID, ANTENNA1, ANTENNA2, INTERVAL, SCAN_NUMBER,
  OBSERVATION_ID, CPARAM, PARAMERR, FLAG, SNR, WEIGHT; keywords ParType,
  MSName, VisCal, PolBasis; ANTENNA, FIELD, SPECTRAL_WINDOW, OBSERVATION,
  HISTORY subtables) written by casacure and read back by python-casacore:
  values equal, and the table type and subtype python-casacore reports
  (`info()`: CASA needs `Calibration` / `G Jones`; casacure issue #23 says
  casacure writes no `table.info`). If `table.info` is missing, a
  hand-written `table.info` is tried as a workaround and its effect
  recorded.

### 3. Measures (reported)

- **M1.** casacure `measures` against astropy `AltAz` (IERS auto-download
  off, data version recorded) for the LUNO phase centres (J1331+3030,
  J1939−6342, J1833−2103 from FIELD.PHASE_DIR) at MeerKAT (the ITRF
  position of `m000` from ANTENNA.POSITION, and the array centre) at the
  LUNO epochs (2021-08-18 13:44–13:48 UTC), the fixture epoch
  (2023-01-03) and two others (2010-01-01 and today 2026-10-30, inside the
  2026-06 to 2027-10 window where casacure's issue #15 says its bundled
  IERS data and astropy's are both extrapolating): azimuth, elevation and
  parallactic angle, `AZEL` and `AZELGEO`; ITRF to WGS84 position; UTC to
  TAI, TT and UT1 epochs. Where available python-casacore `measures` in the
  container gives a third column (it needs measures data; whether the
  wheel carries it is recorded).
- **M2.** The geodetic versus geocentric `AZEL` convention (QuartiCal PR
  #445, casacure issue #15): the size of the difference at MeerKAT for the
  three fields, and what it means for rang (`pointing.py` takes the
  rotation angle as an input; nothing in rang computes parallactic angles
  from an MS yet; B1 and the beam work will).
- **M3.** uvw: casacure has no uvw engine. Compare the fixture's and the
  LUNO MS's stored UVW with a uvw computed with astropy (ITRF baselines
  rotated to the J2000 phase centre at each TIME) to size what rang would
  need to build, and say what that is.

### 4. Platforms (gated where stated)

- **P1 (gated).** The `win_amd64` wheel installs into a fresh uv venv on
  native Windows (Python 3.14) and reads the fixture MS and the LUNO MS,
  copied out of WSL into the session scratchpad, with R1's comparison
  against the copied oracle dump: column-exact. Reading in place over
  `\\wsl.localhost` is tried once and reported.
- **P2 (reported).** The Rust program of R3 builds and runs natively on
  Windows with Rust 1.93 (MSVC) on the same copies.

### 5. Performance (reported)

One process per backend and repeat, five repeats, median and range;
`RAYON_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1` and any casacure thread
setting found in its source set to one. Read every column of the main
table and of every subtable of ms1 (the whole LUNO export) and, separately,
the fixture's DATA (TiledShapeStMan, where `core_ms` was 5× slower than
casacore): wall from `perf_counter` around the reads, peak RSS from
`getrusage` inside the process, for casacure (Python), casacure (Rust
program), `core_ms`, and python-casacore in the container (wall also
reported including the container start). Write: wall and peak RSS of
W1(a) and W1(b).

### 6. Licence, dependency and code review (reported)

- Licence obligations of an LGPL-3.0-or-later dependency of a
  GPL-3.0-or-later project (Python wheel and statically linked Rust
  crate); licence files actually shipped; transitive crate licences.
- Release cadence (PyPI and git tags with dates), contributors, bus
  factor, issue response times, the dask-ms 0.3 / arcae situation, the
  QuartiCal maintainer's comments on PR #445.
- **Code review** of the crate and the Python binding at the clone's head:
  architecture and module layout; `unsafe` blocks (count and
  justification); error handling (panics, `unwrap`/`expect` on data
  paths); test suite size and coverage (storage managers, endianness,
  TaQL, measures), run with `cargo test` and the Python tests; CI and
  release process; API stability (breaking changes across 0.2.x → 3.8.x);
  dependency tree; documentation; reader performance design (mmap,
  copies); rust-version and toolchain compatibility with rang's 1.93 pin.
- His other repositories that bear on rang (disko, the DDFacet and killMS
  casacure ports, TART tools): what each is, licence, state, overlap with
  the DF tasks, DF-IO and the beam/pointing work.

### 7. Decision rule (frozen)

- **(a) Adopt as the core's MS and casacore-table I/O** (Rust crate, with
  `core_ms` kept frozen as the oracle) only if R1, R2, R3, R6, W1, W4 and
  P1 pass, the crate builds with rang's Rust pin, the code review finds no
  defect class that would corrupt data silently, and the performance on
  the fixture DATA and the LUNO export is within 2× of `core_ms` or
  python-casacore, whichever is faster.
- **(b) Writes only** (keep `core_ms` for reads; casacure, Python or Rust,
  behind an optional extra for writing MSs and caltables) if the write
  criteria W1 and W4 pass but a read criterion or the build/review
  condition of (a) fails.
- **(c) Do not adopt, build rang's own table layer** if W1 or W4 fails, or
  the review finds silent-corruption defects, or the licence or
  maintenance terms are unacceptable; the effort for (c) is estimated
  from task E's reader (about 1,900 lines for three read-only managers).
- Whatever is recommended, the dependency is pinned exactly
  (`casacure==3.8.35`) and optional; it is never a hard dependency in this
  task.

## Measured result

Not measured yet.
