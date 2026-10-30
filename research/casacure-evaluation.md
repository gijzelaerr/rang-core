# casacure evaluation (task E2)

Task E2 of [big-plan.md](big-plan.md), branch `e2-casacure` from `29d67b4`.
Protocol frozen 2026-10-30 in the commit that adds this file, before any
measurement beyond opening the three MSs once to see whether casacure reads
them at all (it opened all three and returned DATA, FLAG, UVW, TIME and
WEIGHT_SPECTRUM with python-casacore's dtypes and shapes; nothing compared).
Status: **measured 2026-10-30. Verdict as frozen: (c), do not adopt
casacure as the core's table layer; build rang's own writer on task E's
reader, and keep casacure as an optional, exactly pinned second oracle**
(section "Recommendation"). Reads are column-exact everywhere (Python and
Rust crate, Linux and native Windows, little- and big-endian); in-place
writes and default-manager MS creation read back exactly in
python-casacore; W1(b) fails as frozen because casacure accepts a
TiledColumnStMan request for a variable-shape column and writes an MS that
casacore refuses to open. Eleven upstream candidates, two of them silent
(epoch conversions relabelled without converting; a fabricated
FLAG_CATEGORY), one a crash (SIGBUS on a file truncated under a mapping).

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

## Measured result (2026-10-30)

Everything below the frozen protocol is measurement or labelled post hoc.
Receipts are in `outputs/e2-casacure-20261030-01` … `-10` (table at the end
of this section). casacure 3.8.35 from PyPI throughout (Linux wheel
`cp314 manylinux_2_17_x86_64`, SHA256 `2a83a5cf…c777e`; Windows wheel
`cp314 win_amd64`, `1c493f22…993f7`; crate checksum `5c7f5afe…9566`).

### Verdict per criterion

| Criterion | Gated | Result |
| --- | --- | --- |
| R1 full columns and row ranges, 173 columns of 15 tables, Python API | yes | **pass** (`-01`): every column column-exact, both ranges |
| R2 MS files unchanged by the reads | yes | **pass**; `table.lock` also unchanged on all three MSs |
| R3 Rust crate with Rust 1.93, 173 columns | yes | **pass** (`-06`): the crate builds with `cargo +1.93` (no `rust-version` declared; edition 2021) and every column's bytes equal the oracle's |
| R4 casacure against `core_ms` | no | equal on all 173 columns; `core_ms` still equals the oracle |
| R5 descriptions, dminfo, keywords | no | LUNO: identical. Fixture and imaging MS: keywords identical; `getcoldesc` reports **`dataManagerType: StandardStMan` and group `StandardStMan` for the 12 IncrementalStMan columns** (28 and 30 differences), while `getdminfo` gives the right TYPE; dminfo NAMEs are the type name (`IncrementalStMan`) instead of the stored names (`TIME`, `Array_ID`, …); TiledShapeStMan hypercube SPEC fields empty (55 differences) |
| R6 big-endian copies (python-casacore `copy(endian='big')`) | yes | **pass** (`-03`): casacure column-exact on both copies; **`core_ms` also column-exact**, so its byte-swap path, untested in task E, now has a test input |
| R7 TaQL, 5 frozen selections × 2 MSs | no | 4 of 5 equal on both MSs (FIELD_ID ==, ANTENNA1 !=, SCAN == … ORDERBY TIME, ANTENNA1, ANTENNA2, SELECT UNIQUE); **`BETWEEN` is a parse error**. Post hoc: the bare `SELECT FROM $1 WHERE …` (valid TaQL) and `ORDERBY DESC TIME` are parse errors (`ORDERBY TIME DESC` and `>= AND <=` work); `rownumbers()` takes no table argument, so selection rows cannot be mapped to the parent as python-casacore's `rownumbers(t)` does |
| W1(a) `default_ms` + fixture columns + 4 subtables, default managers | yes | **pass** (`-04`): python-casacore reads every written column and subtable back column-exactly |
| W1(b) same with TiledColumnStMan for DATA, FLAG, WEIGHT_SPECTRUM | yes | **fail as frozen**: casacure accepts the request and writes the MS, `getdminfo` names the three TiledColumnStMan managers (so the brief's "dminfo ignored on create", issue #20, is stale: fixed upstream 2026-10-10), but python-casacore cannot open it: `TiledColumnStMan needs array column FLAG to be FixedShape`. python-casacore refuses the same request at creation (`-04/tiled-reference`) |
| W1(c) post hoc: FLAG redeclared with a shape | no | still unreadable by casacore: casacure stores the shape but not the `FixedShape` option (`option 0`; casacore sets 4 when a shape is given) |
| W1(d) post hoc: same with `options=4` | no | **passes** W1's checks: casacore reads it column-exactly; dminfo honoured |
| W2 `core_ms` reads the casacure-written MSs | no | all four variants column-exact, including (b) and (c), which casacore cannot open |
| W3 python-casacore writes FLAG into a casacure MS, casacure reads | no | exact |
| W4 in-place `putcol` FLAG + `addcols` CORRECTED_DATA, fixture copy (FLAG in TiledShapeStMan) and LUNO copy | yes | **pass** both: written columns and every other oracle column read back exactly in casacore; FLAG stays TiledShapeStMan (written in place into `table.f22_TSM1`). Reported: `addcols` rewrites the files of the manager it joins: on the fixture the 66 kB ANTENNA1 manager `table.f14` becomes `table.f25` + an 18 MB `table.f25i`; on LUNO the whole 38 MB `table.f0i` is rewritten as a 50 MB `table.f1i`. python-casacore, given the same `addcols` on a LUNO copy (post hoc), joins the same StandardStMan and extends `table.f0`/`table.f0i` in place. casacure's 3.8.35 changelog documents the rebuild of a joined manager. Fine for these sizes; on a multi-terabyte MS whose main StandardStMan holds DATA it is a full copy |
| W5 G Jones caltable | no | values read back exactly in casacore, keywords present; **no `table.info`** (open issue #23), so casacore reports type `''` and CASA would not recognise a calibration table; the API has no `putinfo`. Writing `table.info` by hand (`Type = Calibration`, `SubType = G Jones`) works: casacore then reports `Calibration` / `G Jones` |
| M1 measures | no | see below: AZEL/AZELGEO at 0.01–0.05″ of astropy; **epoch conversions UTC→TAI and UTC→UT1 return the input value relabelled** (off by 37 s and up to 0.13 s), UTC→TT and ITRF→WGS84 are refused |
| P1 Windows wheel, fixture + LUNO + imaging copies | yes | **pass** (`-07`): 173 columns column-exact, natively on Windows 11, CPython 3.14.7; also over `\\wsl.localhost` in place (15 s, mostly hashing over 9P) |
| P2 Rust crate natively on Windows (1.93.1 MSVC) | no | builds and passes R3 **only with a POSIX `date` on PATH**: the dependency `celestial-eop-data` 0.1.12 runs `date -u` in its build script and panics without it; with Git's `usr\bin` on PATH it builds in 13 s and is column-exact |

### Measures (M1–M3; `-05`)

30 cases: 3 LUNO fields × 5 epochs (LUNO start and end 2021-08-18, the
fixture 2023-01-03, 2010-01-01, 2026-10-30) × 2 sites (`m000` and the
MeerKAT array centre). astropy 8.0.2, `astropy-iers-data`
0.2026.10.19, auto-download off; python-casacore 3.8.1 in the container
(its wheel carries measures data; 2026-10-30 is beyond its IERS table, so
it sets UT1 = UTC there).

| Quantity | casacure vs astropy | casacore 3.8.1 vs astropy |
| --- | --- | --- |
| AZEL az·cos(el), el, 2010–2023 epochs | ≤ 0.013″, ≤ 0.045″ | `AZEL` 150–400″, 530–605″; `AZELGEO` ≤ 1.0″, ≤ 0.8″ |
| same, 2026-10-30 | 1.34″, 1.62″ (issue #15's documented IERS-extrapolation window) | `AZELGEO` 0.62″, 1.24″ |
| parallactic angle (posangle to the zenith), 2010–2023 | ≤ 0.031″ | `AZEL` frame 527–806″; `AZELGEO` ≤ 0.78″ |
| parallactic angle, 2026-10-30 | 1.90″ | `AZELGEO` 1.31″ |
| UTC → TAI, UT1 | **37 s and 0.13 s off: the value is returned unchanged with the new reference label** | exact (TAI), ≤ 54 ms (UT1, 0 with data) |
| UTC → TT; ITRF → WGS84 | refused (`bad reference type`) | exact; ≤ 2 nm |

M2, the convention. casacore's `AZEL` builds the horizon from the
geocentric latitude, `AZELGEO` and astropy from the geodetic one; casacure
returns the geodetic answer for both. For the three LUNO fields at MeerKAT
casacore's `AZEL` and `AZELGEO` parallactic angles differ by 0.009–0.29°
(largest for J1833−2103 near transit; the ~2° of QuartiCal PR #445 is for
a field 3° from the zenith). For rang: nothing computes parallactic angles
from an MS today (`python/rangtoy/pointing.py` takes `beam_angle_rad` as
an input), so nothing archived moves. B1 and the beam work will compute
them: they should use the geodetic convention (astropy, or casacore
`AZELGEO`), freeze that choice in the B1 protocol, and expect QuartiCal or
CARACal products made with python-casacore's `AZEL` (the default
QuartiCal parangle path before PR #445) to differ from rang's by up to a
few tenths of a degree at these geometries and by degrees near the zenith.

M3, uvw. casacure has no uvw engine. The stored UVW of both MSs equals
(with the MS sign, antenna 1 minus antenna 2) a first-order uvw from the
ITRF baselines and the phase centre to 0.30 m (LUNO) and 0.34 m (fixture)
on 74 m baselines; the residual does not change between a CIRS/ERA and a
J2000/GMST frame, so it reflects how the exports computed UVW, not the
frame. rang reads UVW from the MS everywhere; it needs its own uvw only
to synthesise MSs (DF0's simulated field, L3 if the native set lacks
UVW): J2000 → apparent (precession-nutation, aberration) with ERFA
(`pyerfa`, which astropy already brings) or `sofars` in Rust, rotated by
the Earth rotation angle, validated against python-casacore's `uvw`
measure in the container.

### Performance (section 5; `-08`)

Five repeats, one process each, `RAYON_NUM_THREADS=1` (casacure spawns no
threads: no `rayon` or `thread::spawn` in its non-test code), warm page
cache, medians (range). In-process wall from `perf_counter`; peak RSS
from `getrusage` (the container's from inside the container).

| Read | casacure (Python) | casacure (Rust) | `core_ms` | python-casacore |
| --- | --- | --- | --- | --- |
| whole LUNO export: 13 tables, every readable column (39.4 MB of arrays) | 50 ms (49–82), 100 MB | 30 ms process wall (30–50), 63 MB | 30 ms (30–37), 65 MB; 14 empty or unsupported subtable columns skipped | 44 ms (33–61), 87 MB; 0.83 s with the container start |
| fixture DATA, TiledShapeStMan, 140 × 4096 × 4 complex64 | 21 ms (19–39), 93 MB | — | 20 ms (19–21), 75 MB | 25 ms (16–29), 87 MB; 0.70 s with the container |
| Write: W1(a) default managers / W1(b) tiled, process | 0.29 s (0.28–0.41) / 0.27 s (0.23–0.28); 221 MB | | | |

At these sizes the three readers are within 2× of each other (casacure
1.65× `core_ms` on the whole LUNO export, equal on the tiled DATA), so the
performance condition of rule (a) holds. `core_ms` is now 7× faster on
the fixture DATA than in task E (20 ms against 147 ms; the changes since
task E made it so). casacure's Python reads go through
`getcol_raw` into the NumPy buffer; its public Rust `Table::getcol`
returns `Vec<RecordValue>` (one enum per scalar, one `Vec` per array cell),
so a core built on the crate would use `getcol_raw`/`getcol_raw_bits`.

### Robustness (post hoc, reported; `-09`, `-10`)

`examples/eval_casacure_robustness.py` reads DATA from damaged copies in a
child process. On the fixture, a tile file truncated **after** the table
was opened kills casacure's process with **SIGBUS** (signal 7): its data
files are memory-mapped (`memmap2`), and a mapped file shrunk by another
process is undefined behaviour in Rust; `core_ms` reports `failed to fill
whole buffer`. A truncated file before open, a corrupted `table.dat` and a
missing manager file give Python exceptions in both readers. casacure
also returns a `(nrow,)` bool array of `False` for the never-written
FLAG_CATEGORY of the fixture, where casacore raises (its issue #8: unset
cells return defaults by design; here the shape is wrong as well).

## Code review (casacure at `b3418ba`, 2026-10-28; reported)

Clone in `~/Build/tmp/20261030-casacure` (deleted at the end).

**Layout.** A Cargo workspace with two crates: `crates/casacure` (the
engine, 28 files, 22,675 non-test lines: `table.rs` 8,073, `taql.rs`
5,868, `tsm.rs` 2,942, `ssm.rs` 2,367, `record.rs` 1,802, `lockfile.rs`,
`quanta.rs`, `tabledesc.rs`, `ism.rs`, `measures.rs`, `images/`) and
`crates/casacure-python` (pyo3 0.27 binding, 7,920 lines, not published
as a crate). The engine mirrors casacore's module structure (AipsIO,
TableDesc, ColumnSet, one module per storage manager), which makes it
readable against the C++ sources. `table.rs` mixes reading, writing,
dminfo, views and growth in one 8,000-line file; a joined StandardStMan
is rebuilt on flush (W4).

**`unsafe`.** 10 in the engine, 2 in the binding: `libc` file locking
(`fcntl`, `kill`, `geteuid`), `memmap2::Mmap::map` and an unchecked
`DontNeed` advice in `datafile.rs`, and a byte view of numeric `Vec`s in
`record.rs`. All small and conventional; only 2 carry a `SAFETY` comment.
The mmap is the consequential one (SIGBUS above): casacore uses `pread`
and survives a concurrent truncation.

**Panics and errors.** The data paths return `Result` with `thiserror`
types (`TableReadError`, `WriteTableError`, …) and error messages that
name the file. In non-test engine code: 71 `.unwrap()` (24 of them on
`RwLock` guards), 17 `.expect(`, 2 `panic!`, 18 `unreachable!`; the binding
has 130 `.unwrap()`, 102 on lock guards (a poisoned lock becomes a Python
`PanicException`). None was hit by any probe here.

**Tests.** `cargo test --workspace --release`: **323 passed, 0 failed**
(87 s, 987 MB, stable 1.99.1 as `rust-toolchain.toml` pins). The Python
suite (24 files, 435 test functions, 9,834 lines) generates fixtures with
python-casacore and compares both ways: with the head built for CPython
3.12 next to python-casacore 3.8.1, **478 passed, 39 skipped, 3 xfailed,
6 failed** (28 s); the 6 failures are all in `test_memory_chunking.py`,
fail for the casacore parameter as well, and come from the harness, not
casacure (`'Variable' object has no attribute 'sum'` with the xarray that
an unpinned install resolves; the test dependencies are not pinned). Coverage by area:
storage managers (SSM, ISM, TiledColumnStMan read and write;
TiledShapeStMan and TiledCellStMan read; TiledDataStMan absent, issue
#18), endianness (both orders read and written), TaQL (a ported subset of
casacore's TaQL tests), measures (astropy grid 1926–2126, casacore AZELGEO
parity), dask-ms 0.2.32 suite through a shim, ThreadSanitizer and
free-threaded 3.14t jobs. Not covered, as this evaluation found: dminfo
requests casacore would refuse, the `FixedShape` option, epoch
conversions other than through AZEL, casacore-desc fidelity of
`getcoldesc` for ISM columns, truncation under a mapping.

**CI and releases.** `ci.yml` runs on Ubuntu only (tests, clippy
`-D warnings`, fmt, TSan, free-threaded); `publish-python.yml` builds the
Windows and macOS wheels **without running any test on them** (P1 here
is the first test of the Windows wheel we know of). `tasks.py` runs the CI
gate locally in Docker before tagging. Versions: 0.2.0–0.2.3 (2026-09-18/19),
then the scheme moved to `<casacore major.minor>.<patch>`: 3.8.1 on
2026-09-19 to **3.8.35 on 2026-10-21, 36 releases in 33 days** (gaps of
minutes on 2026-10-06 and 2026-10-08), crate and wheel published
together. The CHANGELOG (122 kB) marks no breaking change, but behaviour
changed under consumers: 3.8.25 moved `AZEL` to the geodetic horizon
(parallactic angles move by up to degrees), and downstream pins record
releases that read or wrote tables wrongly (skarabina's `pyproject.toml`
explains its `>=3.8.33` floor: 3.8.8 "could not read" ANTENNA and FEED
columns "and wrote them in a form casacore misreads").

**Dependencies.** `thiserror`, `libc`, `memmap2`, `sofars` 0.6 (MIT, a
Rust SOFA port), `celestial-eop-data` 0.1.12 (MIT/Apache, IERS tables
compiled in; its build script needs `date`, and stamps the build date into
the binary, so builds are not reproducible) and through it `zstd`/`zstd-sys`
(BSD-3, **a C library compiled with `cc`**, so the "no C toolchain" claim
holds for C++ only). Nothing heavy or abandoned; the two astronomy crates
are young, single-author crates.

**Documentation.** docs.rs builds; 2,211 `///` lines over 319 public
functions. The repository carries long design notes (`ARE_WE_CURED.md`,
`DIFFERENCES.md`, `MEASURES_ACCURACY.md`, `PORTING_DDFACET_KILLMS.md`),
and agent working files (`handover.md`, `MEMORY.md`, `.zcode/`), plus
committed test debris at the root (`PARENT.tab`, `SUB.tab`,
`tmp_tqsel.ms`). **No LICENSE or COPYING file** in the repository, the
crate or the wheel: the LGPL-3.0-or-later is declared only in metadata.

**Bus factor and responsiveness.** One contributor (240 commits under two
addresses of Tim Molteno, 86 of them on day two), 0 stars, 0 forks, 23
issues, 22 of them filed by the maintainer himself (one by dask-ms's
maintainer); issues are answered
within hours, usually with a fix on `main` the same day (issue #15,
#20, #21). The development pace and the handover files indicate
agent-assisted development directed by the maintainer: high output,
thorough tests of what was thought of, gaps where nobody looked.
External voices: the QuartiCal maintainer is "still a little wary of
casacure as a core dependency … it is moving incredibly fast" (PR #445,
open); dask-ms's maintainer (issue #13) is moving dask-ms 0.3 to arcae,
which leaves casacure no import site to hook into and drops the 2.x line,
so casacure's dask-ms route ends at 0.2.32.

**Verdict on the code.** Competent and well tested where tested; byte
compatibility with casacore is real for reads (every column here) and for
writes with valid descriptions. Not yet good enough to be the
foundation of rang's core I/O: one maintainer at 36 releases a month,
validation that lets an invalid description produce an MS casacore
cannot open, silent wrong answers in measures outside the AZEL path, a
memory-mapped reader that crashes rather than errors, no licence text,
untested Windows/macOS wheels, and a Rust API (`Vec<RecordValue>`,
8,000-line `table.rs`) that is shaped by the Python surface rather than by
a kernel's needs.

## His other repositories that bear on rang (reported)

| Repository | What | Licence | State (2026-10-30) | Overlap with rang |
| --- | --- | --- | --- | --- |
| `tmolteno/disko` | Discrete Sky Operator imaging (gridless, matrix-free), 2019– | GPL-3.0 | 1.4.4, active; depends on `casacure>=3.8` for MS reads | imaging alternative to the DF tasks; not a calibration tool |
| `tmolteno/DDFacet` (fork of `cyriltasse/DDFacet`) | DDFacet on casacure (`casacure>=3.8.35`), arm64, numpy 2, Rust `ddfacet-gridder` crate with rayon fan-out | GPL-2.0 (upstream's) | v0.16.10, 13 branches, active | DF0's oracle candidate on arm64; its Rust gridder is GPL-2.0 (only), so not portable into GPL-3 rang without relicensing |
| killMS port | killMS 3.15.12 on casacure with Rust `killms-core`/`native` crates (`PORTING_DDFACET_KILLMS.md`) | upstream GPL-2.0 | **source not public** under his account; only the image `ghcr.io/tmolteno/killms:v3.15.12` and the cabs | DF4's oracle; cannot be inspected |
| `tmolteno/dde-cargo` | Stimela cabs for DDFacet/killMS on arm64 and x86-64 | GPLv3 in metadata, no licence file | 0.3.0, 2026-10-24 | ready-made oracle containers for DF0 |
| `tmolteno/skarabina` | "a basic 1GC RFI flagger" (rflag/tfcrop with CASA-parity work) on dask-ms + casacure | GPL-3.0 | 1.0.21, active | flagging baseline next to Tricolour and CARACal for the flagging verdict (L4) |
| `tmolteno/spotless` | all-sky gridless deconvolution | GPL-3.0 | 2026-10 | no |
| forks: `QuartiCal` (branch `casacure-backend`, PR #445), `dask-ms` (`DASK_MS_BACKEND=casacure`), `meerkat-beams`, `eidos`, `stefcal`, `stimela` | casacure integration and fixes | upstream's | active | beam work (B1-0) uses `meerkat-beams`/`eidos` upstream, not the forks |
| `TART`, `tart_modules`, `tart_cal`, `tart-file-handling` (Rust and Python, Zarr) | the Transient Array Radio Telescope | GPL-3 / none in metadata | active | none directly; small-array calibration practice |

## Recommendation

**Frozen rule.** (a) needs W1, and W1(b) failed as frozen; (b) needs W1 as
well; so the rule gives **(c): do not adopt casacure as the core's I/O
layer, build rang's own**. The post-hoc variants show the W1(b) failure is
a validation defect (an invalid request accepted and written) rather than
a byte-level writer defect, so the rule's outcome rests on one fixable
defect; the code review independently points the same way (maintenance
pace and bus factor, silent measures errors, mmap crash, no licence
file), which is also the user's default.

In five lines:

1. Do not make casacure a dependency of the core (crate or wheel); extend task E's reader into a reader-writer in `core/src/ms*.rs` (owned, about 4,500–6,000 more lines with tests, 2–4 sessions).
2. Use casacure as an optional, exactly pinned **second oracle** (`casacure==3.8.35`): it reads every column we have column-exactly and is the only casacore-format implementation that runs natively on Windows and macOS, which closes X1's "casacore paths are Linux/container only" gap for tests.
3. Keep python-casacore in the container as the primary oracle for writes (casacore must open what rang writes), and add casacure as a second writer-oracle for round trips on every platform.
4. Measures: do not take them from casacure; use astropy/ERFA in Python (geodetic convention, frozen in B1) and `sofars` in Rust only if the core needs them.
5. Report the eleven candidates below to tmolteno (coordinator, after the user's say); revisit adoption when casacure has a licence file, a slower cadence, a second maintainer and fixes for candidates 1–4.

What the numbers say for each option: reads (R1, R3, R6, P1) would allow
(a); performance would allow (a) (≤ 1.65× `core_ms`); writes with valid
descriptions would allow (b) (W1(a), W1(d), W4 exact in casacore).
Option (b) is the realistic fallback if the own writer slips: casacure's
Python writer behind an optional extra, for writing MSs and caltables,
with `options=4` on every fixed-shape column and a hand-written
`table.info`.

**DF-IO coverage.** casacure covers the casacore-table formats: MS
(read, write, in place; not TiledDataStMan), CASA calibration tables
(values and keywords; `table.info` by hand), any casacore table, and CASA
images (`casacure.images`, not evaluated here). It does not cover zarr
(QuartiCal gain stores, rang's own stores), DDFacet `DicoModel` (pickle),
killMS solutions (`.npz`), Tigger `.lsm` / `.lsm.html`, or FITS beyond
images; those are rang's own work in DF-IO whatever is decided here.

### Migration plan (proposed plan tasks)

| | Task | Owns | Sequenced |
| --- | --- | --- | --- |
| E3 | **Core table writer.** In-place `putcol` for StandardStMan (scalars, direct and indirect arrays, strings), TiledColumnStMan and TiledShapeStMan (existing hypercubes), `addcols` as a new manager (casacore's behaviour, no rewrite of other files), `table.dat`/TableDesc/keyword writer, lock-file sync record; frozen protocol: python-casacore reads back every write column-exactly (container), casacure reads it back (all platforms), untouched files keep their SHA256. | `core/src/ms_write.rs`, `core/src/ffi_ms_write.rs` (or the P7 binding), `python/rangtoy/core_ms_write.py`, `tests/test_core_ms_write.py`, `research/e3-ms-writer.md` | after P7 (which replaces the ctypes path `core_ms.py` uses); parallel with P9; before P12, or rebased after it |
| E4 | **Table creation and schemas.** New tables and `default_ms` with the 17 subtables, CASA calibration tables (G, B, K, Df with `table.info`), FixedShape options set as casacore does; oracle: python-casacore's `default_ms` and a CASA-written caltable from the container | `core/src/ms_create.rs`, `python/rangtoy/core_caltable.py`, `research/e4-ms-create.md` | after E3; feeds DF-IO |
| E5 | **ISM arrays and strings, TiledDataStMan if a file turns up, MemoryStMan refused** (task E's refusals), big-endian writes | `core/src/ms.rs` (extension), tests | any time after E3; small |
| DF-IO | non-table formats: zarr gain stores, `DicoModel`, killMS npz, Tigger lsm | as in `ddfacet-feasibility.md` | with DF2; uses E3/E4 for MS and caltables |
| T1 | **casacure as an optional second oracle**: the pinned extra, `tests/test_casacure_optional.py` (this task) in the Windows/macOS CI jobs of `wheels.yml`, and E3/E4 round trips through it | `pyproject.toml` extra line, `.github/workflows/wheels.yml` test step | with X1's CI follow-up; coordinator |

B1 freezes the parallactic-angle convention (geodetic) and its
reference (astropy) in its protocol; no separate task.

### Upstream candidates for tmolteno/casacure (for the coordinator; not filed)

casacure is not a RATT or `saopicc` repository, so under the user's
reporting rule these go to `non-ratt-observations.md` unless the user
decides otherwise. Each reproduces on 3.8.35 with the scripts named.

1. **Invalid dminfo accepted and written.** `default_ms(path, desc, dminfo)` with TiledColumnStMan for the variable-shape FLAG column writes an MS casacore 3.8.1 cannot open (`TiledColumnStMan needs array column FLAG to be FixedShape`); casacore refuses at creation. `examples/eval_casacure.py write … ` variant b; `examples/eval_casacure_tiled_reference.py` for casacore's behaviour. Expected: `ValueError` at creation (the "fail loudly" of issue #20).
2. **`makearrcoldesc(..., shape=[…])` does not set `FixedShape`.** casacore sets option 4 whenever a shape is given; casacure stores `option 0`, so the column is variable-shape in casacore and TiledColumnStMan is refused (variant c). Expected: option 4, as python-casacore produces.
3. **Epoch conversions relabel without converting.** `dm.measure(dm.epoch('UTC', '59444.5d'), 'TAI')` returns `59444.5 d` with `refer: TAI` (37 s wrong); likewise `UT1`; `TT` raises. Expected: convert (casacure has the IERS and leap-second data compiled in) or raise for unsupported conversions instead of relabelling. `eval_casacure.py measures`.
4. **SIGBUS on a data file truncated under the mapping.** Open the fixture, truncate `table.f22_TSM1`… (`eval_casacure_robustness.py`, probe `truncate-after-open`): the process dies with signal 7; casacore and `core_ms` raise. Expected: an error (read with `pread`, or check the length before touching the mapping).
5. **`getcoldesc` misreports the manager of IncrementalStMan columns** (`dataManagerType`/`dataManagerGroup` say StandardStMan; `getdminfo` is right) and `getdminfo` returns the type name as `NAME` and empty hypercube SPEC fields for TiledShapeStMan. A `tablecopy(dminfo=t.getdminfo())` round trip then cannot reproduce the source layout. `eval_casacure.py describe`/`compare-describe`.
6. **TaQL gaps:** `BETWEEN … AND …`, the bare `SELECT FROM $1 WHERE …` (no column list), `ORDERBY DESC col`; and `rownumbers(parent)` is missing (python-casacore's selection-to-parent mapping).
7. **Never-written FLAG_CATEGORY** returns a `(nrow,)` `False` array; casacore raises; the shape does not match the column's 3-D description (issue #8 covers defaults, not the shape).
8. **No LICENSE/COPYING** in the repository, the crate or the wheel; LGPL-3.0 asks for the LGPL and GPL texts to accompany the work.
9. **Windows/macOS wheels are built but never tested in CI** (`publish-python.yml`); the Windows wheel passes here.
10. **Crate does not build natively on Windows without a POSIX `date`**: `celestial-eop-data` 0.1.12's `build.rs` runs `date -u +%Y-%m-%d` and panics, and its timestamp makes builds non-reproducible (an issue for `celestial-eop-data`, mentioned to casacure since it chose the dependency).
11. Enhancement, documented upstream: **`addcols` + `flush` rebuilds the StandardStMan the new column joins** (38 MB → 50 MB, `table.f0i` → `table.f1i` on LUNO); casacore joins the same manager and extends its files in place. Issue #22 fixed the whole-table rewrite and lists this case as remaining.

### Licence and dependency

LGPL-3.0-or-later is GPL-3.0 plus additional permissions, so rang
(GPL-3.0-or-later) may depend on casacure, link it statically into the
core, or even incorporate its code, and the combination is conveyed under
GPL-3.0-or-later. Obligations as a dependency: ship the LGPL-3.0 and
GPL-3.0 texts and casacure's copyright notice with any binary that
includes it (the wheel would statically link the crate), and let users
replace or relink the library, which a GPL-3 rang with its corresponding
source already does. casacure itself ships no licence text (candidate 8),
so rang would have to supply it. Its MIT/Apache/BSD dependencies need
their notices only. The proposed extra pins `casacure==3.8.35` exactly:
the cadence (36 releases in 33 days) and the behaviour changes between
patch releases rule out a range.

### Archives and receipts

| Directory | Contents |
| --- | --- |
| `outputs/e2-casacure-20261030-01` | R1, R2, R4 `result.json` (Linux, casacure Python) |
| `-02` | python-casacore and casacure descriptions and their diff (R5); TaQL (R7) for ms0 and ms1; the big-endian copies' receipt (copies deleted) |
| `-03` | R6 `result.json` |
| `-04` | W1–W5: `write.json`, `inplace.json`, `caltable.json`, the python-casacore read-backs, `tiled-reference/`, `result.json` (written MSs deleted) |
| `-05` | measures cases, casacore, casacure/astropy comparison; uvw |
| `-06` | R3 Rust result (column files deleted) |
| `-07` | P1, P2 Windows receipts |
| `-08` | performance JSON and `/usr/bin/time` files |
| `-09`, `-10` | robustness probes (LUNO, fixture) |

## Timings

Every tool run of this task, 2026-10-30, on the WSL host shared with other
sessions unless marked Windows. Wall from `/usr/bin/time` or `Stopwatch`;
RSS is peak resident set.

| Tool / stage | Input | Wall | RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `docker build` of `tools/ms-reader` (`rang-ms-reader:local`), first try | Dockerfile | 0 s | — | started with `&` inside `wsl -e bash -lc`; died with the shell, empty log |
| same, as a background tool run | Dockerfile | 28.3 s | 53 MB | python-casacore 3.8.1, NumPy 2.5.3 |
| `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin casacure` | worktree | 36.2 s | — | builds the extension |
| `git clone` casacure | GitHub | 1.5 s | — | 4.7 MB, 240 commits |
| casacure probe of the three MSs | 3 MSs | < 1 s | — | before the protocol (see the header) |
| `eval_casacure.py reads` (R1, R2, R4) | oracle `-01`, 173 columns | 1.86 s | 285 MB | casacure reads 0.26 s in process; full columns 97 ms (`core_ms` 105 ms) |
| container `describe`, `bigendian`, `taql` ×2 | 3 MSs | 0.99, 1.50, 0.77, 0.77 s | 31 MB | container start included |
| casacure `describe`, `compare-describe` | 3 MSs | 0.09, 0.17 s | 43, 38 MB | |
| `eval_casacure.py bigendian` (R6) | 2 big-endian copies | 4.88 s | 276 MB | casacure and `core_ms` |
| TaQL host / container, three rounds (scripts fixed between) | ms0, ms1 | 0.16–0.80 s / 0.61–1.86 s | 300–320 MB / 31 MB | |
| `eval_casacure.py write` W1(a, b) | fixture columns | 0.53 s | 226 MB | |
| `inplace` W4, `caltable` W5 | 2 copies; synthetic G | 0.55, 0.16 s | 221, 45 MB | |
| container read-backs (`oracle_ms_columns.py` ×5, `putflag`, `info`) | written tables | 0.54–1.27 s each | 30–31 MB | W1(b), W1(c) read-backs fail (casacore cannot open them) |
| `write` variants c, d (post hoc) | fixture columns | 0.50, 0.59 s | 172 MB | |
| `eval_casacure_tiled_reference.py` (container) | — | 2.84 s | 30 MB | |
| `verify-writes` | `-04` | 1.07, 0.69 s | 433–451 MB | |
| `measures-cases` + container `measures` | 30 cases | 0.78 s | 31 MB | |
| `measures` (casacure, astropy) | 30 cases | 1.08 s | 170 MB | |
| `uvw` | LUNO, fixture | 0.93, 0.87 s | 169 MB | plus one scratch variant (CIRS/ERA and J2000/GMST) |
| `cargo +1.93 fetch` + `cargo +1.93 build --release` of `examples/casacure_rs` | crate + 13 dependencies | 44.3 s | 499 MB | first build; rebuild 0.5 s; fmt and clippy clean |
| `eval-casacure-rs` (R3) | 15 tables | 0.46 s | 128 MB | |
| copy MSs and oracle to the Windows scratchpad | 257 MB | 2.9 s | — | |
| Windows `uv venv` + `uv pip install casacure==3.8.35 numpy` | PyPI | failed, then 3.1 s | — | uv cache "too many temporary files"; retried with `UV_CACHE_DIR=~/Build/cache/uv` |
| Windows `eval_casacure.py reads --no-core` (P1) | local copies | 1.17 s | 249 MB | 0.29 s in process |
| same, in place over `\\wsl.localhost` | WSL outputs | 15.1 s | — | hashing over 9P dominates |
| Windows `cargo +1.93 build --release` (P2) | crate | 17 s (fail); 13.1 s | — | fails without `date` on PATH (`celestial-eop-data` build script); passes with Git `usr\bin` on PATH |
| Windows `eval-casacure-rs` + compare | 15 tables | 0.45 s | — | |
| performance runs (section 5), 5 repeats × 8 runs | LUNO, fixture | about 1 min | see the table | |
| `eval_casacure_robustness.py` | LUNO, fixture | 0.81, 0.79 s | 69, 72 MB | 8 child processes each |
| casacure `cargo test --workspace --release` (stable 1.99.1) | clone | 87.1 s | 987 MB | 323 passed |
| casacure `cargo +1.93 build -p casacure --release` | clone | 18.2 s | 498 MB | |
| casacure `maturin build` (for 3.14 by mistake, then 3.12) | clone | 25.2, 42.0 s | 517, 505 MB | |
| casacure `make_fixtures.py` + `pytest tests/` | clone | 28.6 s | 460 MB | the first attempt failed at collection (wheel for the wrong interpreter) |
| python-casacore `addcols` on a LUNO copy (post hoc) | LUNO copy | < 2 s | — | container |
| `pytest tests/test_casacure_optional.py` | — | 0.52 s | 136 MB | 3 passed |

## For the coordinator

**STATE paragraph.** E2 casacure evaluation (2026-10-30,
`research/casacure-evaluation.md`): casacure 3.8.35 (Tim Molteno's
pure-Rust casacore tables, LGPL-3.0-or-later) reads all 173 task E oracle
columns column-exactly through Python and through the Rust crate (Rust
1.93), on Linux and natively on Windows, little- and big-endian; in-place
writes and default-manager MS creation read back exactly in
python-casacore. But it accepts a TiledColumnStMan request for a
variable-shape column and writes an MS casacore cannot open (W1(b) failed
as frozen), relabels epoch conversions without converting, crashes with
SIGBUS on a file truncated under its mapping, ships no licence file, and
has one maintainer at 36 releases in 33 days. Verdict as frozen: (c), do
not adopt; extend task E's reader into rang's own writer (E3, E4) and keep
casacure as an optional pinned second oracle that also runs on Windows
and macOS. `core_ms` passed its first big-endian test on the way.

**Plan lines** (big-plan.md, next to the DF-IO item):

- E2 casacure evaluation done 2026-10-30 (`casacure-evaluation.md`): verdict (c), own writer; casacure as an optional second oracle.
- E3 core table writer (in-place `putcol` for SSM and the tiled managers, `addcols` as casacore does, `table.dat`/description/keyword writer, lock sync record); after P7, parallel with P9, before P12 or rebased after it.
- E4 table creation: `default_ms` with subtables, CASA caltables (G, B, K, Df) with `table.info`; after E3; feeds DF-IO.
- E5 ISM arrays and strings, big-endian writes; small, any time after E3.
- T1 casacure as second oracle in the Windows and macOS test jobs of `wheels.yml`, with X1's follow-up.
- B1's protocol freezes the geodetic parallactic-angle convention with astropy as the reference.

**pyproject extra (proposed, not applied):**

```toml
casacure = ["casacure==3.8.35"]
```

**Upstream candidates.** The eleven under "Upstream candidates" above.
casacure is neither RATT nor `saopicc`, so under the recorded rule they go
to `research/non-ratt-observations.md` with the reproductions named there,
unless the user decides to report them; candidate 10 belongs to
`celestial-eop-data` (crates.io, MIT/Apache).

**`research/tool-timings.md`:** the rows of the Timings table above.

**Evidence to keep:** `outputs/e2-casacure-20261030-01` … `-10` (JSON
receipts, logs and read-backs).

**Deleted scratch:** the written and copied MSs in `-02/big` and
`-04/*.ms`, and the Rust column files in `-06/rust-linux` (regenerable
with the commands in this file); `~/Build/tmp/20261030-e2` (the example's
target directory and logs); `~/Build/tmp/20261030-casacure` (the clone,
its venv and targets); on Windows, the scratch copies and
`~/Build/tmp/20261030-e2-win`.

**Files on this branch:** `research/casacure-evaluation.md`,
`examples/eval_casacure.py`, `examples/eval_casacure_oracle.py`,
`examples/eval_casacure_tiled_reference.py`,
`examples/eval_casacure_robustness.py`, `examples/casacure_rs/` (its own
`[workspace]` and `Cargo.lock`, built with `--target-dir` outside the
tree, not part of `tools/check-all.sh`), `tests/test_casacure_optional.py`
(skips without casacure, the oracle or the MSs). No shared file is edited.

## Open items

- TiledDataStMan, MemoryStMan and CASA images were not evaluated (none in
  rang's inputs).
- Reader speed matters at the whole-array LUNO chunk; the comparisons here
  are on 37–75 MB MSs.
- The killMS casacure port's source is not public; DF4 cannot inspect it.
- The stored UVW of both exports differs from a first-order uvw by 0.3 m
  on 74 m baselines; the cause (the exports' own UVW computation) is not
  resolved here and matters only if rang synthesises UVW.
