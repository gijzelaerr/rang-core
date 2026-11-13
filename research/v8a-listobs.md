# V8a: `listobs`, a parity port of CASA's summary task

Piece 3 of [v8-open-casa.md](v8-open-casa.md) (section 7), moved before v0.2.0
by the owner on 2026-11-12 (section 8.1, decision 1). Branch
`claude/v8a-listobs-1c691e` from `main` `452f9d5`.

**Status: measured, PASS (2026-11-12; section 8).** Protocol frozen before code; Sections 1-7 are committed
before any rang `listobs` code and before any comparison of rang's output with
CASA's. CASA's own output on the data below was produced by a probe run
(section 3) before or while this note was written; its output format guides the
comparison code, never the tolerances, which are the ones V8 section 7 proposed.

## 1. Hypothesis and what is not claimed

`rang-core listobs MS` and `rang.tasks.listobs(vis=MS)` report the observation,
scan, field, spectral-window, source and antenna summaries that CASA 6.7.6.14's
`listobs` reports, from rang's own Measurement Set reader, within the
tolerances of section 4, on every MS of section 2.

Not claimed: novelty (a reimplementation is not novelty, `AGENTS.md`); text
layout equal to CASA's; speed. It is a port with parity as the goal. Nothing
here touches code that E2 or E3 runs.

## 2. Data

All MSs are opened read-only by both tools (CASA through `:ro` container
mounts; rang's reader opens tables read-only). No E2 or E3 run directory is
opened.

| Name | MS | What it tests | Role |
| --- | --- | --- | --- |
| `fixture-scan{1,4,5,8,9}` | the public SKA pointing fixture, `outer_scans.zip` (sha256 `d4dae56f…144f`), the five `1672727931_sdp_l0_scan_N.ms` | 4 antennas, 1 field, 1 scan, 1 spw, SOURCE present | development |
| `luno` | the LUNO PKS 1934−638 slice, `outputs/luno-solve-20261029-02/work.ms` (WSL; [o-casa.md](o-casa.md) inputs) | 4 antennas, 3 FIELD rows, STATE intents, no SOURCE table | development |
| `a1` | A1's simulated MS as C2a's CASA run left it, `D:\rang\outputs\c2a-20261106-03\casa\a1.ms` ([a1-simtruth.md](a1-simtruth.md)) | 16 antennas, 4 fields, 20+ scans, 4 states | development |
| `eso137` | the ESO137 pilot raw MS, `D:\rang\outputs\20261103-gemclean-heldout\real\raw.ms` (850,950 rows) | 61 antennas, a real full-array antenna table | **held out**: rang's output is compared with CASA's once, after the development gate passes on the other seven |

Gap, stated now: no MS here has more than one spectral window or data
description. A multi-spw case waits for a suitable MS (E2's converted MSs, read
only, after E2 reports, are the candidate) and is not part of this gate.

## 3. Oracle

CASA `listobs` from `casatasks==6.7.6.14` in the image `rang-o-casa:6.7.6.14`
([o-casa.md](o-casa.md)), run by `tools/oracles/casa/listobs.sh` (WSL, Docker,
`--network none`, MSs mounted read-only) with
`listobs(vis=MS, listfile=OUT/NAME.txt, verbose=True)` for each MS. Kept per MS:

- the **returned record** (`NAME.json`): times, scans, fields, counts;
- the **listfile text** (`NAME.txt`): the header strings (observer, project,
  telescope), field row counts and source ids, the spectral-window frame, the
  SOURCE table, at printed precision;
- a **supplementary oracle** (`NAME.msmd.json`), labelled as such: CASA's own
  `msmetadata` tool (same image) for the spectral-window and antenna values
  that the record lacks and the text prints only rounded (channel frequencies
  and widths, bandwidth, reference and mean frequency, correlation types,
  antenna names, stations, diameters, positions, WGS84 longitude, latitude and
  height through CASA's `measures`).

No CASA source is read (owner decision 5, 2026-11-12). CASA's grouping and
timing conventions (how a scan is split into the record's sub-entries, what
`BeginTime`, `EndTime` and `IntegrationTime` mean, whether FIELD rows without
data are listed) are taken from casadocs 6.7 (`listobs` task page) and from the
probe's output, and are written down in section 6 as rang implements them.

## 4. Measures and frozen tolerances

Per MS, every value below in CASA's output must be present in rang's with the
same key and agree within its tolerance; a value present in one and absent in
the other is a difference.

| Section | Values | Tolerance |
| --- | --- | --- |
| observation | `BeginTime`, `EndTime` (MJD days) | 1 ms (1.1574e-8 d) |
| | `IntegrationTime` (s) | 1 ms |
| | `numrecords`, `nfields`; observer, project, telescope (text) | exact |
| scans | the set of scan keys and, per scan, the set of sub-entries | exact |
| | per sub-entry `BeginTime`, `EndTime`, `IntegrationTime` | 1 ms |
| | `FieldId`, `FieldName`, `SpwIds`, `StateId`, `nRow`, `scanId` | exact |
| fields | the set of field keys; `name`, `code`, `direction.refer` | exact |
| | `direction` RA (compared modulo 2π) and Dec | 1e-3 arcsec (4.848e-9 rad) |
| | rows per field, source id (text) | exact |
| spectral windows | count, `name`, `nchan`, correlation types, frame (text) | exact |
| | first channel frequency, every channel frequency and width, total bandwidth, reference and centre frequency | 1 Hz |
| sources (text, when SOURCE exists) | id, name, spw id | exact |
| | rest frequency, systemic velocity | the text's printed precision |
| antennas | count, `name`, `station`, diameter | exact (diameter to 1 mm) |
| | ITRF position | 1 mm per axis |
| | WGS84 longitude and latitude | 1e-3 arcsec |
| | WGS84 height | 1 mm |

Not gated, stated now: the antenna offsets from the array centre (they need the
observatory position from CASA's measures data, which rang does not carry; rang
v1 does not print them, a recorded gap); the text layout; wall time (measured
on a shared host, informational only).

## 5. Decision rule

- **Pass**: zero differences on all seven development MSs, then zero on the
  held-out `eso137` at its single comparison.
- **Fail**: any difference on the held-out MS after the development gate
  passed. The difference is recorded with its cause; a fix may follow, but the
  held-out result stays failed in this note and a fixed rerun is labelled post
  hoc.
- **Development**: differences on the seven development MSs are fixed in
  rang's code (not in the tolerances) until zero; every fix and its cause is
  listed in section 8. If a convention cannot be inferred from the docs and the
  probe without reading CASA's source, it is listed as a gap and the gate is
  reported as failed for that value.
- Tolerances are not changed after this commit; any later protocol change is a
  dated amendment labelled post hoc.

## 6. Implementation (proposed)

- `python/rang/listobs.py`: the summary, built only on `rang.core_ms`
  (`open_table`), reading only scalar MAIN columns (`TIME`, `INTERVAL`,
  `SCAN_NUMBER`, `FIELD_ID`, `DATA_DESC_ID`, `STATE_ID`, `ARRAY_ID`,
  `OBSERVATION_ID`), never `DATA` or `FLAG`, plus the subtables OBSERVATION,
  FIELD, DATA_DESCRIPTION, SPECTRAL_WINDOW, POLARIZATION, STATE, ANTENNA and,
  when present, SOURCE. FEED is not read (the FEED string-array fix on
  `claude/feed-poltype-read-ea1d2d` is not needed). It returns CASA's record
  layout (same keys, same units), with rang's additions (spectral windows,
  antennas, sources) under keys CASA's record does not use, so the comparison
  is a dictionary walk. WGS84 from ITRF is a closed-form/iterative conversion
  in NumPy (no measures data).
- `rang.tasks.listobs(vis, selectdata=True, spw="", field="", antenna="",
  uvrange="", timerange="", correlation="", scan="", intent="", feed="",
  array="", observation="", verbose=True, listfile="", listunfl=False,
  cachesize=50, overwrite=False)`: CASA's keyword names and defaults. Any
  selection or option rang does not implement (`spw` … `observation` non-empty,
  `verbose=False`, `listunfl=True`) is refused with a `ValueError` naming it,
  never ignored. `cachesize` has no effect and is accepted. `listfile` writes
  the text; an existing file is refused unless `overwrite=True`.
- `rang-core listobs MS [--listfile PATH] [--overwrite] [--json]`: the text on
  stdout (or the file), or the record as JSON. Read-only, so no receipt, as
  `rang-core config`.
- `tools/oracles/casa/compare_listobs.py`: the comparison of section 4, writing
  a verdict JSON per MS; a compact archive of CASA's fixture records goes in
  `research/results/` so a CI test can run the fixture comparison without CASA.

## 7. Cost and stop rules

Light work: CASA and every comparison run as shared heavy-lock jobs (one slot),
never exclusive, so E2's timed runs are not disturbed. Size: one to two
sessions, about 400 lines of Python. Stop: if the development gate is not met
after the fixes the docs and probe allow, the note records the remaining
differences and the gate as failed.

## 7a. Amendment 1 (2026-11-12, after the probe, before any CASA output on the new case)

Labelled as an amendment; the tolerances and decision rule of sections 4-5 are
unchanged.

- **Probe run** `outputs/v8a-listobs-20261112-00-probe` (WSL; image
  `rang-o-casa:6.7.6.14`, 124 s, 332 MB peak): CASA listed `luno`, `a1` and
  `eso137`, then stopped at the first fixture MS, because the fixture mount
  pointed at a cache that holds scan 9 only. `listobs.sh` now mounts B1's
  extraction of the same zip (`outputs/b1-20261030-03-fixture/outer_scans`,
  all five MSs). The gate run is `outputs/v8a-listobs-20261112-01`.
- **Conventions read off the probe** (no CASA source read): only fields with
  rows in MAIN are listed (`nfields` counts them; LUNO has 3 FIELD rows and
  `nfields = 1`); RA is returned in (−π, π]; the record carries
  `timeref: "UTC"`; `BeginTime`/`EndTime` are min(TIME − INTERVAL/2) and
  max(TIME + INTERVAL/2) in MJD days; a sub-entry's `IntegrationTime` is the
  mean INTERVAL; the listfile's "Lat." column is the geocentric ITRF latitude,
  not WGS84 (rang prints WGS84 and labels it); the Fields table has a SrcId
  column only when SOURCE exists. rang was changed to match the first three
  (development fixes, section 5); on `luno` and `a1` the comparison then
  showed zero differences (80 and 438 values). `eso137` was not compared.
- **New development case `edges`** (`tools/oracles/casa/listobs_edges.py`, written by
  rang's table writer to `D:\rang\scratch\v8a-20261112\edges.ms`): a field
  change inside a scan, a state change inside a scan, a FIELD row without
  data, and two spectral windows alternating in one scan. None of the earlier
  MSs had any of these, so how CASA splits a scan into sub-entries was
  untested. rang's rule as implemented before CASA's output on this MS was
  seen: a new sub-entry wherever observation, array, scan, field or state
  changes in time order, with the data descriptions inside a sub-entry
  collected into `SpwIds`.

## 7b. Amendment 2 (2026-11-12, development fix, before the held-out comparison)

Gate run `outputs/v8a-listobs-20261112-01` (WSL; CASA on all nine MSs, 126 s,
332 MB peak). The development comparison then gave zero differences on `luno`,
`a1` and the five fixture MSs, and 9 differences on `edges`: rang's
sub-entry rule of amendment 1 was wrong. CASA's rule, read off its record and
listfile for `edges` (no CASA source read): **one sub-entry per field within a
scan, in field-id order; every sub-entry carries the scan's whole time range;
a state change inside a scan does not split it** (scan 3 is one entry, its
listfile ScanIntent shows both states' modes). rang now does this, with
`StateId` = the state of the field's first row in time order. Gaps left, as no
MS here separates them: first-row state against lowest state id; a scan
number reused across observations or arrays. With the fix, all eight
development MSs show zero differences (`dev2.json`, section 8).

## 8. Measured result

**PASS.** Zero differences on the eight development MSs after the fixes below,
then zero on the held-out `eso137` at its one comparison.

| MS | values compared | differences | rang wall (s) | CASA wall (s) |
| --- | ---: | ---: | ---: | ---: |
| `luno` | 80 | 0 | 6.75 | 0.03 |
| `a1` | 438 | 0 | 0.01 | 1.36 |
| `edges` | 142 | 0 (9 before amendment 2) | 0.01 | 0.27 |
| `fixture-scan1`, `4`, `5`, `8`, `9` | 81 each | 0 | 2.2-13.5 | 0.03 each |
| `eso137` (held out) | 650 | **0** | 0.89 | 61.7 |

Walls are informational (section 4): rang's are dominated by reading MSs over
`\\wsl.localhost` on a host running E2's shared jobs (the same LUNO MS took
0.35 s in the first comparison); CASA's are inside the container on WSL's own
disk. `eso137`'s CASA wall is 62 s against rang's 0.9 s: CASA's
run on that MS takes longer (cause not investigated); not a claimed speed-up.

Worst |rang − CASA| over all nine MSs: times 0; IntegrationTime 7e-14 s;
directions 4e-16 rad; channel frequencies and widths, bandwidth, reference and
centre frequency 0 Hz; ITRF 9.3e-10 m; WGS84 longitude 0, latitude 9e-15 rad,
height 2.8e-9 m. Every check was also shown to fire just above its tolerance
(perturbation test: 2 ms, 2e-3 arcsec, 2 mm, 2 Hz, a row count, a missing scan;
0.5 ms passes).

Runs and receipts (WSL `~/Github/rang/outputs/`, ignored):

- `v8a-listobs-20261112-00-probe`: CASA on `luno`, `a1`, `eso137`; stopped at
  the fixture (amendment 1). 124 s, 332 MB peak.
- `v8a-listobs-20261112-01`: the gate run, CASA on all nine MSs (`meta.json`,
  `image.txt`, `code-sha256.txt`, `time.txt`: 126.3 s, 332 MB peak).
- `v8a-listobs-20261112-02-compare`: `dev.json` (before amendment 2: `edges`
  9 differences), `dev2.json` (development gate, all zero), `heldout.json`.
- `research/results/v8a-listobs-casa-fixture.json`: CASA's record, listfile
  and msmetadata on the five fixture MSs (channels as SHA-256), which
  `tests/test_v8a_listobs.py` compares rang against without CASA (needs the
  fixture: `RANG_FIXTURE` or `outputs/ska-pointing/outer_scans.zip`, else it
  skips).

Development fixes, in order (each from CASA's output, no CASA source read):
fields without rows are not listed; RA wrapped into (−π, π]; `timeref` added
(amendment 1); the sub-entry rule (amendment 2). The listfile parser was also
fixed twice (sections end at the next heading; SrcId only when printed); these
are comparator fixes, not rang fixes.

Gaps, not gated: antenna offsets from the array centre are not printed; the
text layout is rang's; `StateId` as first-row state against lowest id, and a
scan number reused across observations or arrays, are untested; a sub-entry spanning several states (as `edges` scan 3) shows one
`StateId` in rang's text, where CASA's listfile lists every intent; no real
multi-spw MeerKAT MS (only the synthetic `edges`, two spws); CASA's selection
keywords are refused, not implemented.

## 9. For the coordinator

- Branch `claude/v8a-listobs-1c691e`, not merged. The FEED fix
  (`claude/feed-poltype-read-ea1d2d`) was not needed: FEED is never read.
- STATE paragraph: *V8a `listobs` (2026-11-12): `rang-core listobs` and
  `rang.tasks.listobs` (CASA keywords; selections refused) match CASA
  6.7.6.14's `listobs` record, channels and antenna positions on eight
  development MSs and the held-out ESO137 MS (650 values, 0 differences;
  research/v8a-listobs.md). A test compares rang with an archive of CASA's
  output on the public fixture where the fixture is present; CI's `tests` job
  does not fetch it, so there it skips (wiring it is for the coordinator).*
- Plan line (v8-open-casa.md section 7, piece 3): done; next CASA piece is
  `flagdata` `tfcrop` after v0.2.0. A real multi-spw check waits for E2's
  converted MSs.

## 10. Resume state (2026-11-13, stopped on the owner's order)

- Done: the gate passed (section 8); fixture archive and tests committed.
- Full check: run 1 (2026-11-12) failed only
  `test_w4_6_portability.py::test_every_text_read_and_write_names_its_encoding`
  (two listfile writes without `newline=`), fixed in the last commit. Run 2
  passed every stage up to pytest (1247 passed, 86 skipped), and was stopped
  during `gain-hashes`. The full check has not completed on the head commit.
- Resume step: from the worktree, in PowerShell with
  `RANG_ARCHIVE_OUTPUTS=\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs`, run
  `python <main>\tools\heavy_lock.py run --slots 8 --mem 16 -- .venv\Scripts\python.exe -m rang.check`
  (on a fresh venv, run `maturin develop --release` first). Then add a
  tool-timings row, and hand the branch to the coordinator for merge.
- Left on disk: `D:\rang\scratch\v8a-20261112` (edges.ms, which
  `listobs_edges.py` rebuilds, and verdict copies; the verdicts are also in
  WSL `outputs/v8a-listobs-20261112-02-compare`); check logs
  `~/Build/tmp/20261112-v8a-check*.log`.
