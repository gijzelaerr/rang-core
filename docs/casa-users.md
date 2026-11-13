# For CASA users

ra-ng is growing, task by task, into an open replacement for the CASA tasks
that MeerKAT users run ({gh}`research/v8-open-casa.md`). Each port is checked
against CASA 6.7.6.14 run as an oracle, with the tolerance and the result in a
research note. This page maps CASA's tasks to rang's, and is extended as each
port lands; a row marked "planned" does not exist yet.

There are two ways in:

- **`rang.tasks`**, in Python, takes CASA's keyword names and defaults, so a
  CASA call reads the same: `from rang.tasks import listobs;
  listobs(vis="my.ms")`. A keyword value rang does not implement yet is
  refused with `rang.tasks.Unsupported` naming it, never ignored.
- **`rang-core`**, on the command line ({doc}`cli`): stage commands driven by
  one YAML configuration, as CARACal drives CASA.

## Tasks

| CASA task | rang | State |
| --- | --- | --- |
| `listobs` | `rang-core listobs MS [--json]`; `rang.tasks.listobs` | ported ({gh}`research/v8a-listobs.md`) |
| `flagdata` `tfcrop` | `rang-core flag` | planned, after v0.2.0 (Tricolour stays the default flagger) |
| `flagdata` `manual`, `shadow`, `quack`, `elevation`, `unflag`, `summary` | `rang-core flag` | planned, after `tfcrop` |
| `flagdata` `extend` | `calibrate.polcal.extendflags` in the configuration | exists |
| `flagmanager` (save, restore) | `rang.formats.flagversions`; every write saves a flag version first | exists |
| `setjy` | `calibrate.model.source: setjy` (also `manual`, `lsm`) | exists |
| `gaincal` (G, K, KCROSS), `bandpass`, `fluxscale`, `polcal` (Xf, Df) | `rang-core calibrate`, terms `G, K, B, F, Gpol, KCROSS, Xf, Df` | exists |
| `applycal` | `rang-core apply` | exists |
| `tclean` | `rang-core image`, `gemclean` (WSClean-style options, checked against WSClean) | exists |
| `ft` | `image.write_model` | exists |
| `exportfits` | not needed: images are written as FITS | exists |
| `split`, `mstransform` | – | planned |

Out of scope for now (owner decision, 2026-11-12): spectral line
(`uvcontsub`, Doppler regridding, cubes) and CASA image tables.

## `listobs`

```python
from rang.tasks import listobs

record = listobs(vis="my.ms")                      # prints the summary
record = listobs(vis="my.ms", listfile="my.txt")   # writes it instead
```

```text
rang-core listobs my.ms             # the summary
rang-core listobs my.ms --json      # the record, for scripts and agents
```

The returned record has CASA's keys and units: `BeginTime` and `EndTime` in
MJD days, `IntegrationTime` in seconds, `nfields`, `numrecords`, `field_N`
(name, code, direction in radians) and `scan_N` (per sub-entry `BeginTime`,
`EndTime`, `FieldId`, `FieldName`, `SpwIds`, `StateId`, `nRow`,
`IntegrationTime`, `scanId`). As in CASA, a scan has one sub-entry per field,
in field-id order, each with the scan's whole time range; a state change
inside a scan does not split it. rang adds what CASA prints but does not return:
`observation`, `spectral_windows` (every channel frequency and width),
`sources`, `antennas` (ITRF position and WGS84 longitude, latitude and
height), `fields_extra` (rows and source id per field) and `states` (the scan
intents).

Keywords: `vis`, `listfile`, `overwrite` work as in CASA; `selectdata` and
`cachesize` are accepted and have no effect. The selections (`spw`, `field`,
`antenna`, `uvrange`, `timerange`, `correlation`, `scan`, `intent`, `feed`,
`array`, `observation`), `verbose=False` and `listunfl=True` are refused.

Differences from CASA: the text layout is rang's own (the values are what is
compared); the antenna offsets from the array centre are not printed (they
need CASA's observatory table); the antenna table prints WGS84 longitude and
latitude, where CASA's "Lat." column is the geocentric latitude. On CASA
6.7.6.14 the record, channels and antenna positions agree with CASA's on nine
MSs within 1 ms, 1e-3 arcsec, 1 Hz and 1 mm (research/v8a-listobs.md).
