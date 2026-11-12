# V8a: `listobs`, a parity port of CASA's summary task

Piece 3 of [v8-open-casa.md](v8-open-casa.md) (section 7), moved before v0.2.0
by the owner on 2026-11-12 (section 8.1, decision 1). Branch
`claude/v8a-listobs-1c691e` from `main` `452f9d5`.

**Status: proposed (protocol frozen before code).** Sections 1-7 are committed
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

(Not yet run.)
