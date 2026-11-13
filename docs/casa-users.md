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
| `flagdata` `manual`, `clip`, `quack`, `shadow`, `elevation`, `extend`, `unflag`, `summary` | `rang-core flagdata MS key=value ...`; `rang.tasks.flagdata` | ported ({gh}`research/v8b-flagdata.md`) |
| `flagdata` `tfcrop` | – | not at parity yet, so `rang.tasks.flagdata` refuses it ({gh}`research/v8b-flagdata.md` section 9.3); `rang-core flag` (the Tricolour port) is the flagger |
| `flagdata` `extend` inside calibration | `calibrate.polcal.extendflags` in the configuration | exists |
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

## `flagdata`

```python
from rang.tasks import flagdata

flagdata(vis="my.ms", mode="manual", autocorr=True)
flagdata(vis="my.ms", mode="quack", quackinterval=8.0, quackmode="beg")
flagdata(vis="my.ms", mode="manual", spw="*:856~880MHz,*:1419.8~1421.3MHz")
flagdata(vis="my.ms", mode="shadow", tolerance=0.0)
flagdata(vis="my.ms", mode="elevation", lowerlimit=20.0)
counts = flagdata(vis="my.ms", mode="summary", basecnt=True)
flagdata(vis="my.Df", mode="clip", clipminmax=[-0.6, 0.6], datacolumn="CPARAM",
         flagbackup=False)
```

```text
rang-core flagdata my.ms mode=quack quackinterval=8
rang-core flagdata my.ms mode=summary spwchan=True
```

Keywords and defaults are CASA 6.7's. The selections `field`, `spw` (ids,
names, `*`, channel ranges `a~b` and `;` lists, frequency ranges in Hz, kHz,
MHz or GHz), `antenna` (names, ids, `A&B`, `A&&B`, `A&&&`, `!A`), `scan`,
`timerange`, `uvrange` (m, km), `observation`, `array` and `correlation`
(with `ABS_`, `REAL_`, `IMAG_`, `ARG_`, `NORM_` for `clip`) work as in CASA;
`intent`, `feed`, wavelength `uvrange`, channel steps, `rflag`, `antint`,
`list` mode, `addantenna`, `channelavg`, `action` other than `apply` and
`savepars` are refused before anything is written. On a calibration table
only `clip` on `CPARAM` is supported.

Every writing call saves the flags first (`flagbackup=True`: CASA's
`flagdata_<n>` version; `False`: rang's `rang_original`, once) and leaves a
receipt beside the MS, `<ms>.flagdata-<mode>-<time>.rang-receipt.json`.

CASA's conventions that the documentation leaves open, as rang implements
them (read off CASA 6.7.6.14's output, {gh}`research/v8b-flagdata.md`
section 9): quack's window includes its boundary; FLAG_ROW is set only by
whole-row selections of `manual`, `quack`, `shadow` and `elevation`; a bare
antenna name selects its cross-correlations only; `elevation` uses the
geocentric horizon; a frequency range inside one channel selects that
channel's two neighbours; `summary` counts an autocorrelation once for its
antenna.
