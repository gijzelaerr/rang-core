# E0: `refant: auto` and `extendflags` in `rang-core calibrate`

Task E0 of [finish-plan.md](finish-plan.md) (row E0; section 7 items 15 and 19). It removes the last two
configuration errors that stop E2-B's calibrate stage: `refant: auto` ([c2e-calibrate.md](c2e-calibrate.md)
section 9 item 1) and `calibrate.polcal.extendflags` ([c6w-polwire.md](c6w-polwire.md) section 7 item 4).
Branch `fp-e0-refant`, from main `ba65792`.
**Status: implemented and measured (sections 8 to 10). Gate 3 met. Gate 1 met on every case where CARACal's function
runs, and on the slice only with a post-hoc reference (CARACal's msutils crashes there). Gate 2: FLAG bit-identical to
CASA on every case; its rule-coverage condition was met only by a post-hoc case.** The protocol (sections 0 to 7) was
committed (`abc4855`) before the first comparison; this status line is the only edit above section 8.

## 0. What was read before this protocol

- CARACal `8f7bb363` (`outputs/c1-sources-20261105/caracal-8f7bb363/`, ignored): `workers/utils/manage_antennas.py`
  (whole file), `crosscal_worker.py` lines 150-170, `polcal_worker.py` lines 1400-1640, `schema/obsconf_schema.yml`
  and `schema/polcal_schema.yml`, `sample_configurations/meerkat-fullStokes-continuum-defaults.yml`, and, fetched
  for this note at the same commit, `caracal/workers/obsconf_worker.py` and `caracal/dispatch_crew/config_parser.py`.
- The Stimela cab `cab/flagstats` (Stimela 1.8.3 from the uv cache: `cargo/cab/flagstats/{parameters.json,src/run.py}`)
  and its base image `cargo/base/msutils/Dockerfile`, which runs an unpinned `pip install msutils`. msutils' last
  1.x release is 1.2.0 (PyPI, 2021-05-04); the next is 2.0.0b1 (2026-07-12), a rewrite without
  `MSUtils.flag_stats`. So the cab's msutils is taken to be **1.2.0** (sdist sha256 `a377d8b5...e17af`, in
  `outputs/c1-sources-20261105/msutils/`), read whole: `MSUtils/flag_stats.py`.
- CASA, the dic-case-studies `casa6` mirror at `9269a52f` (2023-01-18; the oracle is 6.7.6.14, newer, so the
  reading is checked by the comparison, not assumed): `FlagAgentExtension.{cc,h}`, `FlagAgentBase.cc`
  (`iterateAntennaPairsFlags`), `FlagDataHandler.cc` (`setIterationApproach`, `generateAntennaPairMap`),
  `FlagMSHandler.cc` (`generateIterator`, `flushFlags`), `AgentFlagger.cc` (`open`, `parseAgentParameters`),
  `task_flagdata.py` (`ntime`, mode `extend`), `flagdata.xml` (`extendpols`), `msvis/MSVis/{VisibilityIteratorImpl2,
  LayeredVi2Factory,MSIter2}.cc`. casacore 3.7.1: `ms/MeasurementSets/MSIter.cc` (`MSInterval::comp`,
  `construct`, `setState`) and `tables/Tables/BaseTabIter.cc` (`noCachedIterBoundariesNext`).
- The O-CASA image `rang-o-casa:6.7.6.14`: casacore measures data `casacore-data 20250826`, 57 observatories;
  `me.observatory("MeerKAT")` is WGS84, longitude 0.37426665946841203 rad, latitude -0.5360464638235224 rad,
  height 1050 m, and the lookup ignores case.
- rang: `core_config` (the two refusals, `_chain_refusals`), `core_pipeline.chain_terms`, `polcal_terms`,
  `stage_calibrate_chain`, `cal_chain.run` and `flag_corrected`, `core_writeback.WriteBack`; `tests/data/w2/e2b.yaml`.

## 1. What the sources do (read, not yet measured)

### 1.1 CARACal's `refant: auto`

`refant` defaults to `auto` (CARACal's `config_parser` takes a schema's `example` as its default; E2-B's
`meerkat-fullStokes-continuum-defaults.yml` sets no `refant`), `maxdist` to 1000 m and `minbase` to 150 m. The
crosscal worker calls `get_refant` once per MS at its start, and the polcal worker calls it again at its start.
`get_refant` runs `cab/flagstats` on the whole MS (no field or antenna selection is passed; its `fields` argument
is unused) and reads the antenna part of the JSON. msutils 1.2.0 writes, per ANTENNA row: the name, POSITION, the
fraction of FLAG cells set over every row that has the antenna as ANTENNA1 or ANTENNA2 (all fields, all
correlations, autocorrelations once; FLAG_ROW not read), and `array_centre_dist`, the distance from the array
centre. The centre is `me.observatory(TELESCOPE_NAME of OBSERVATION row 0)` taken as (lon, lat, height) and
converted by msutils' own `wgs84_to_ecef` (WGS84 ellipsoid); if that raises (an unknown telescope), the centre is
antenna 0's POSITION.

`_get_core_antennas` keeps antennas with `array_centre_dist <= maxdist`, then of those the ones whose distance to
**every other ANTENNA row** is `>= minbase`. Then `sorted(core_ants.items(), key=lambda x: x[1])` sorts on the
tuple `(name, flagged, position, array_centre_dist)`, so **the order is by antenna name** (string order); the flag
fraction only breaks ties between equal names. `_prioritised_antennas` returns the first three names joined by
commas, or `""` when none qualifies; CARACal then logs "Cannot auto-select ref antenna(s)" and passes `""` on.

**Erratum.** The code comment ("sorted by increasing flag data percentage"), C2e's section 0 and `core_config`'s
refusal text all describe a fewest-flags choice. The code chooses by name. E0 ports the code. For MeerKAT names
(`m000` to `m063`) the choice is the three lowest-numbered antennas within 1 km of the centre that have no other
antenna within 150 m, whatever their flags.

### 1.2 CARACal's `extendflags`

Under "preliminary flags" at the start of the polcal worker, **before** the strategy choice and every Gpol, KCROSS,
Xf and Df call (the task statement said "after the polcal solves"; the source says before, as rang's own key text
"on xcal and fcal first" does), and only when `pol_calib != "none"`:
`flagdata(vis, mode="extend", field=pol_calib, ntime="60s", combinescans=True, growtime=80.0, growfreq=80.0,
growaround=True, flagnearfreq=True, flagneartime=True, flagbackup=False)`, then the same with
`field=leakage_calib` if it differs. `extendpols` is left at its default, True. No scan selection.

### 1.3 CASA's `flagdata(mode="extend")`

- **Chunks.** `ntime="60s"` gives a 60 s interval; `combinescans=True` selects `COMBINE_SCANS_MAP_ANTENNA_PAIRS_ONLY`:
  sort OBSERVATION_ID, ARRAY_ID, FIELD_ID, DATA_DESC_ID, TIME (no SCAN_NUMBER), all timesteps of a chunk in one
  buffer (row blocking = the selection's rows). The iterator is casacore's `MSIter` (`useMSIter2` false), whose
  `TableIterator` runs without cached boundaries: a chunk starts at the first row t0 not yet used and takes the
  following rows, in sort order, while OBSERVATION_ID, ARRAY_ID, FIELD_ID and DATA_DESC_ID are equal and
  `floor((t - (t0 - 0.01)) / 60) == floor(0.01 / 60)`, that is `t - t0 < 59.99` s in float64 (`MSInterval`, whose
  offset is reset after every chunk and set from the first row on the next comparison).
- **Per chunk and baseline** (`ANTENNA_PAIRS_FLAGS`; each (ANTENNA1, ANTENNA2) pair as it occurs, autocorrelations
  included) the flag cube is (correlation, channel, row), the rows of that pair in time order, so a missing
  integration is skipped, not filled. Then, in this order (`FlagAgentExtension::computeAntennaPairFlags`):
  1. *Grow* into a separate cube, applied afterwards: a flagged cell flags its time neighbours (`flagneartime`) and
     channel neighbours (`flagnearfreq`); an unflagged cell with more than 4 flagged cells among its 3x3 time-channel
     neighbourhood (same correlation, edges cut) is flagged (`growaround`). Every test reads the flags before step 1.
  2. Per correlation, the flagged count of every row (over channels) and of every channel (over rows) is taken once;
     then rows with `100 * count / nchan >= growfreq` are flagged across all channels, and then channels with
     `100 * count / nrow >= growtime` (counts from before the frequency extension) across all rows.
  3. `extendpols`: a cell flagged in any correlation is flagged in all.
- Flags are only added. FLAG_ROW is not written (`flagRow_p` is set only when unflagging).

## 2. Design (implemented in the working tree after this protocol commit; runs snapshot it in `.code/`)

- **`rang.cal_refant`** (new, Python over rang's readers): `caracal_refant(ms, maxdist=1000.0, minbase=150.0)`
  reads ANTENNA (NAME, POSITION) and OBSERVATION (TELESCOPE_NAME, row 0), takes the centre from
  `rang/data/casacore_observatories.json` (the 57 entries of casacore-data 20250826 from the O-CASA image, name,
  refer and m0, m1, m2 as `me.observatory` returns them, looked up ignoring case), applies msutils' `wgs84_to_ecef`
  and `_distance` and CARACal's rules in their float64 arithmetic, and returns the names (up to three) and a
  record. Flag fractions affect the result only when two qualifying antennas have the same name; then rang refuses
  (it reads no FLAG at all). `auto` must stand alone (`refant: auto` or `[auto]`).
- **Config.** `calibrate.refant_maxdist` (1000.0) and `calibrate.refant_minbase` (150.0), CARACal's obsconf
  `maxdist` and `minbase`. `refant: auto` and `extendflags: true` are no longer errors; `extendflags: true` without
  a Gpol, KCROSS or Xf term is (CARACal extends only when there is a `pol_calib`).
- **Resolution in `core_pipeline`.** `stage_calibrate_chain` resolves `auto` once, before anything is written,
  replacing it in every term's refant by the chosen names; the choice depends on no flags, so CARACal's second
  call at the polcal worker's start gives the same names. When nothing qualifies, rang stops the stage before
  writing (CARACal passes `""` and CASA solves without a reference antenna; see section 7). The summary records
  the names and the per-antenna record. Preflight runs the same resolution so `rang-core calibrate` fails early.
- **`rang.flag_extend`** (new): `extend_flags(flag, a1, a2, time, groups, ...)` on arrays and `extend_ms(ms, fields,
  scans, ...)` on an MS: it builds CASA's chunks (section 1.3) on the selected rows, reads FLAG per batch of whole
  chunks within the memory budget, calls the Rust kernel and writes FLAG through `core_writeback.WriteBack`
  (`flag_backup` = the attempt's flag version, `stage="calibrate"`); FLAG_ROW is not written. Returns counts per
  rule.
- **Rust kernel** `core/src/flag_extend.rs` (`rang_core::flag_extend`), the three steps of 1.3 per (chunk,
  baseline) segment, segments in parallel; Python binding `core/py/src/flag_extend.rs` (`rang._core.flag_extend`).
- **The step in the chain.** `polcal_terms` puts one `extend` step first among the polcal terms when
  `extendflags` is true: fields = the fields of the Gpol, KCROSS and Xf terms (`pol_calib`), then those of the Df
  terms not among them (`leakage_calib`), each field extended separately (FIELD_ID is a sort key, so one call per
  field equals CARACal's two calls). `cal_chain.run` runs it after the primary and secondary terms (so after their
  A steps' flags) and before Gpol. With `data.scans`, only the selected scans are extended (section 7).
- Edits to `core_pipeline` and `cal_chain` are limited to: the resolution call and its summary line, the
  `extend` spec in `polcal_terms`, one `elif` in `cal_chain.run`. Task W3b edits the same files in parallel.

## 3. Data and cases (frozen here; held-out cases built only after the frozen ones have run)

Sources, read-only: **slice** `~/Github/rang/outputs/o-casa-20261030-01/work.ms` (LUNO, 4 MeerKAT stations m000-m003,
192 rows, field 1 J1939-6342, one scan of 32 integrations of 7.9966 s, 2048 channels, 70.1 % flagged, no
autocorrelations); **A1 small** `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms` (16 antennas,
64 channels, fields J1939-6342, 3C286-SIM, SIM-GCAL, SIM-TARGET, 23 scans, FLAG all false, RFI mask beside it);
**A1 full** `.../full/a1-full.ms` (64 antennas); **holdout128** `/mnt/d/rang/outputs/c2e-20261106-h128/holdout128/
a1-holdout128.ms` (C2e's held-out design, 128 channels); **polholdout** `/mnt/d/rang/outputs/c6-20261106-sets/
polholdout/a1-polholdout.ms` (C6's, 256 channels). No new simulated data and no new seeds. "Prepared" means a copy
whose FLAG is the RFI mask (`any`, all four correlations; `check_gain.rfi_flags`), written by python-casacore in the
CASA container, as C2e prepared A1.

### 3.1 Reference antenna (gate 1)

| Case | MS | Held out |
| --- | --- | --- |
| R1 | slice, as stored | no |
| R2 | A1 small, as stored | no |
| R3 | A1 full, as stored (only ANTENNA, OBSERVATION and FLAG are read) | yes |
| R4 | copy of A1 small: ANTENNA NAME reversed (row i takes row 15-i's name), and FLAG set on every row of the antenna whose new name sorts first among those that qualify by position | yes |
| R5 | copy of A1 small: TELESCOPE_NAME `E0-NOWHERE` (not in casacore's table: the centre is antenna 0) | yes |
| R6 (reserve) | copy of A1 small: NAME rotated (row i takes row (i+5) mod 16's name), TELESCOPE_NAME `meerkat` | reserve |

Oracle: CARACal's own `manage_antennas.get_refant`, imported from the CARACal tree by file path and called with a
stub `pipeline` (`msdir`, `input`) and a stub `recipe` whose `run()` calls msutils 1.2.0's
`flag_stats.save_statistics(msname, outfile=...)` with fields and antennas None, as the cab's `run.py` does. It runs in
a uv venv (Python 3.11, numpy < 2, python-casacore, dask-ms, dask, bokeh from public PyPI; versions recorded) with
casacore's `measures.directory` set to a copy of the O-CASA image's `/usr/share/casacore/data`; the run log must not
contain msutils' "Using the first id antenna" warning except on R5.

### 3.2 Flag extension (gate 2)

| Case | Input | `flagdata` calls (fields, scans) | Held out |
| --- | --- | --- | --- |
| X1 | slice, FLAG as stored | J1939-6342 | no |
| X2 | A1 small, prepared | 3C286-SIM, then J1939-6342 (CARACal's xcal, then fcal) | no |
| X3 | holdout128, prepared | 3C286-SIM, then J1939-6342, both with `scan="8,14,22,23"` (rang: `data.scans` [8, 14, 22, 23]) | yes |
| X4 | A1 small, prepared, then edited: SCAN_NUMBER 99 for the last four integrations of scan 4 (SIM-TARGET); TIME of scan 4's last integration set to t0 + 59.985 s and of scan 6's last to t0 + 59.995 s (t0: the scan's first time); the rows of baseline (m000, m004) at scan 4's second and third integrations removed | SIM-TARGET, then SIM-GCAL | yes |
| X5 (reserve) | polholdout, prepared | 3C286-SIM, then J1939-6342 | reserve |

Each case: one prepared copy is copied twice; CASA 6.7.6.14 in `rang-o-casa:6.7.6.14` runs the calls on one with
CARACal's parameters (section 1.2, plus `scan` on X3), rang's `flag_extend.extend_ms` runs the same fields and
scans on the other (on the host).

## 4. Gates (frozen)

1. **Reference antenna.** On R1, R2 and the held-out R3, R4, R5, `",".join(cal_refant.caracal_refant(ms).names)`
   equals the string CARACal's `get_refant` returns. Where CARACal returns `""`, the condition is instead that rang
   raises its "no antenna qualifies" error. Gate 1 is met when all five agree.
2. **Flag extension.** On X1, X2 and the held-out X3, X4, FLAG after rang's extension equals FLAG after CASA's,
   bit for bit, on every row; FLAG_ROW is equal and unchanged on every row; no other column differs between the two
   copies (SHA-256 of DATA, WEIGHT, SIGMA, TIME, SCAN_NUMBER). To mean anything the cases must not saturate: at least
   two cases, one of them held out, must each have at least 1 % of their selected cells newly flagged and at least
   10 % still unflagged. Across X1 to X4, rang's per-rule counts must show each of neartime, nearfreq, growaround,
   growfreq, growtime and extendpols adding cells somewhere (reported, and a protocol failure, not a pass, if one
   never fires). Gate 2 is met when all four cases are equal and the non-saturation condition holds.
3. **E2-B validates.** `rang-core config check --stage flag --stage calibrate --stage apply tests/data/w2/e2b.yaml`
   exits 0 with no error and no refusal. (Its image stage is still refused for tasks W4, G3 and G9, outside E0;
   reported.)

Also checked, not gated: `rang-core calibrate` on A1 small with an E2-B-like configuration (refant auto,
extendflags, the polcal terms) runs to the end, its summary records R2's names and the extension's counts, and FLAG
after the stage equals FLAG after a library replay of the same steps; the existing tests for the two refusals are
changed to test the new behaviour.

## 5. Rules for failures

A failed comparison is reported as failed. A change made after seeing a result is labelled post hoc in section 9 and
then checked on the reserve case (R6 or X5), which is run only then; if both reserves are used, the gate is reported
as not met as frozen. No tolerance is loosened.

## 6. Runs

Under `/mnt/d/rang/outputs/e0-20261106-NN/` with a `.code/` snapshot (`head.txt`, `diff.patch`, `untracked.tgz`);
CASA steps and check-all under `flock ~/.rang-heavy.lock`. Scripts: `examples/check_e0.py` and the reference runner
`tools/oracles/e0/caracal_refant.py`.

## 7. Owner decisions (open; defaults provisional)

1. **Port the code or the intent of `get_refant`.** The code picks by name; its comment and schema text say fewest
   flags. Provisional: the code (it is CARACal's behaviour). A fewest-flags option would be a deviation from CARACal.
2. **No qualifying antenna.** CARACal passes `""` and CASA then solves without a reference antenna; rang stops the
   calibrate stage before writing and asks for a refant. Provisional: stop. On MeerKAT this happens for any
   sub-array without an antenna 150 m from all others (the slice's four core stations).
3. **`data.scans` and the two steps.** CARACal's statistics and its extension cover the whole MS and field; rang's
   `refant: auto` uses only ANTENNA and OBSERVATION (so scans do not matter) and the extension covers the selected
   scans only, so rang never changes flags outside `data.scans`. Provisional: the selection.
4. **New keys in the calibrate hash.** `refant_maxdist` and `refant_minbase` change the calibrate stage hash, so a
   calibrate stage finished before E0 is rerun with `--force` once (as W3's decision 3).
5. **The observatory table.** rang carries casacore-data 20250826's observatory positions; CARACal's container uses
   whatever measures data its image has. Provisional: the frozen table.

## 8. Results (measured 2026-11-06)

### 8.1 Reference antenna (gate 1)

| Case | Run | CARACal's `get_refant` | Antenna part (post hoc, 9.1) | rang | Agree |
| --- | --- | --- | --- | --- | --- |
| R1 slice | -01, -02 | **fails**: msutils raises `IndexError` in `source_flags_field` | `""` | refuses (no antenna qualifies) | frozen: **no**; post hoc: yes |
| R2 A1 small | -02 | `m008,m024,m032` | `m008,m024,m032` | `m008,m024,m032` | yes |
| R3 A1 full (held out) | -04 | `m022,m023,m024` | same | `m022,m023,m024` | yes |
| R4 names reversed, `m020` fully flagged (held out) | -04 | `m020,m028,m036` | same | `m020,m028,m036` | yes |
| R5 unknown telescope (held out) | -04 | `m008,m024,m032`, with msutils' "first id antenna" fallback | same | same, centre antenna 0 | yes |

R1: the slice's FIELD table has three rows but only field 1 has data; msutils 1.2.0's `save_statistics` computes field
statistics first and indexes one result per FIELD row, so it raises before the antenna part, and CARACal's crosscal
worker would stop there. The frozen oracle therefore gives no answer on R1. R4 shows the name rule: `m020` has every
cell flagged and is still CARACal's first choice; a fewest-flags rule would have given `m028,m036,m052`. R5's fallback
centre (antenna 0, `m000`, 33 m from the true centre) happens to give the same names. Every other run's msutils log has
no fallback warning. Oracle environment (`~/Build/tmp/20261106-e0-msutils/freeze.txt`): Python 3.11.17, msutils 1.2.0,
numpy 1.26.4, python-casacore 3.8.1, dask 2024.7.1 (dask-ms 0.2.21 needs a dask before 2024.8), dask-ms 0.2.21,
bokeh 3.9.2, casacore-data 20250826 from the O-CASA image.

### 8.2 Flag extension (gate 2)

FLAG after rang's extension equals FLAG after CASA 6.7.6.14's `flagdata` with CARACal's settings, bit for bit, on
every row of every case; FLAG_ROW is equal and unchanged; rows outside the selection are untouched on both sides;
DATA, WEIGHT, SIGMA, TIME, SCAN_NUMBER, ANTENNA1 and ANTENNA2 are equal.

| Case | Run | Selected cells | Added by CASA | Unflagged after | Cells differing | rang's rules that fired |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| X1 slice | -03 | 1,572,864 | 0.92 % | 29.0 % | 0 | neartime, nearfreq, growaround, growtime |
| X2 A1 small | -03 | 860,160 | 9.53 % | 78.8 % | 0 | neartime, nearfreq, growaround |
| X3 holdout128, scans 8, 14, 22, 23 (held out) | -06 | 1,105,920 | 8.01 % | 80.0 % | 0 | neartime, nearfreq, growaround |
| X4 constructed stress (held out) | -06 | 2,334,208 | 10.2 % | 77.6 % | 0 | neartime, nearfreq, growaround |

rang's chunk counts follow section 1.3: 4 on X1 (32 integrations of 7.9966 s: 8, 8, 8, 8), 6 on X2 (one per scan of the
two fields), and 18 on X4, where SIM-TARGET's 7 and SIM-GCAL's 10 scans give 17 and scan 6's integration at
t0 + 59.995 s opens an 18th, while scan 4's at t0 + 59.985 s stays in its chunk and the renumbered scan 99 does not
split one (`combinescans`); CASA's FLAG agrees on all of it. X4 has 12,478 rows (two removed from baseline m000-m004).

### 8.3 E2-B validates (gate 3)

Run `-10-gate3`: `rang-core config check --stage flag --stage calibrate --stage apply tests/data/w2/e2b.yaml` prints
"valid for flag, calibrate, apply" and exits 0. `--all` still lists nine refusals, all for other tasks: W4 (uniform
imaging weights), G3 (`channels_out`, `join_channels`), G9 (`pol: IQUV`, `join_polarizations`), and C5a and G6 for
self-calibration, which E2-B does not run.

### 8.4 The command (also checked, not gated)

Run -11 (-09 stopped in the checker's own table hashing, on an unwritten WEIGHT column of a calibration table):
`rang-core calibrate` on A1 small prepared as X2, with K, G, B, F and the four polcal terms, three ways: (a) `refant:
auto`, `extendflags: true`; (b) `refant: [m008, m024, m032]`, `extendflags: true`; (c) `refant: auto`, `extendflags:
false`. All three finish. (a) records `refant_auto` m008, m024, m032 and runs the steps K, G, B, F, extend, Gpol,
KCROSS, Xf, Df; every table cell and FLAG of (a) equal (b)'s; (c) differs in FLAG. The extension in (a) runs on fields
1 then 0, 3,360 rows in 6 chunks, and adds 82,000 cells. With no A step, nothing else in (a) writes FLAG, so its final
FLAG can be set beside CASA's on X2's identical input: the SHA-256 of the whole column is equal (`6b62bc76...`), so the
command's FLAG equals CASA's bit for bit (checked after the run, read-only).

## 9. What changed after a result (post hoc)

1. **The refant oracle on R1** (after run -01). CARACal's own function fails on the slice (8.1). The oracle now also
   runs `get_refant`'s own lines after the cab (`_get_core_antennas`, the tuple sort, `_prioritised_antennas`) on
   msutils' antenna part alone (`flag_stats.antenna_flags_field`, which `save_statistics` calls third), written and
   read through JSON as the cab's file is. Nothing in rang changed. Every case reports both answers; they agree
   wherever `get_refant` runs (R2 to R5). Checked on the reserve R6 (run -08).
2. **Building X4** (after run -05). python-casacore cannot remove rows from A1's storage managers, so `casa_side.py
   edit` deep-copies the other rows into a new table instead. Only the case's construction changed; -06 ran X3 and X4
   afresh.
3. **X6, for the rules X1 to X4 never fire** (after run -06): A1 small, prepared with the RFI mask in XX only, plus an
   85 % band burst in XX at 3C286-SIM's second integration of scan 2, extended on 3C286-SIM and J1939-6342 (run -07).
   FLAG equals CASA's bit for bit (860,160 cells, 0 differ; CASA adds 26.1 %, 70.3 % stay unflagged), and rang's
   counts show `growfreq` (2,796 cells) and `extendpols` (191,796) firing, with neartime, nearfreq and growaround.
   Across X1 to X6 every rule has fired on a case equal to CASA.
4. **The reserve R6** (run -08, after change 1): A1 small with names rotated by five and TELESCOPE_NAME `meerkat`:
   CARACal `m028,m044,m052`, the antenna part the same, rang the same (the lower-case name finds casacore's MeerKAT).

## 10. Verdict against the frozen gates

1. **Gate 1, not met as frozen; met with the post-hoc reference.** R2 and the held-out R3, R4, R5 equal CARACal's own
   `get_refant`. On R1 CARACal's function raises inside msutils 1.2.0 and gives no answer to compare; with `get_refant`'s
   own lines run on msutils' antenna part (change 1), it chooses nothing and rang refuses, as frozen for that case. The
   reserve R6 also agrees.
2. **Gate 2: equality and non-saturation met; the rule-coverage condition not met as frozen.** FLAG equals CASA's bit
   for bit on X1, X2 and the held-out X3 and X4 (0 cells of 5.9 M differ), FLAG_ROW and the other columns too; X2, X3
   and X4 are non-saturated. `growfreq` and `extendpols` did not fire on those four, so as frozen the gate is a protocol
   failure on coverage; the post-hoc X6, a new case on unchanged code (not a retest after a fix), fires both and is
   equal too, so coverage stays not met as frozen. The reserve X5 was not needed (no change was made
   to rang's extension) and was not run.
3. **Gate 3 met.** E2-B validates for flag, calibrate and apply.

No novelty claim: both are ports for parity with CARACal.

## 11. What was not checked

- CARACal itself end to end: the reference runs `get_refant` with a stub Stimela recipe, not inside a CARACal
  pipeline; the cab's real container image (Stimela's `msutils` base, unpinned) was not pulled. msutils 1.2.0 is
  inferred from the release history.
- The oracle's python-casacore is 3.8.1 from PyPI, not the cab's; its measures data are the O-CASA image's.
- CASA's `flagdata` source was read from a January 2023 mirror; the oracle is 6.7.6.14. They agree on every case run.
- Autocorrelations and several data descriptions, observations or arrays in one extension (none of the cases has
  them); `ntime` other than 60 s; `extendflags` with `data.scans` through the command (X3 checks the library's scan
  selection against CASA's `scan=`).
- Flag extension on real E2-B data (the LUNO fetch awaits the owner).
- Throughput (no timing claim): rang's extension took 0.9-12 s per case on the host.

## 12. Files, runs, provenance

- Code: `python/rang/cal_refant.py`, `python/rang/flag_extend.py`, `python/rang/data/casacore_observatories.json`
  (from `tools/oracles/e0/observatories.py`), `core/src/flag_extend.rs`, `core/py/src/flag_extend.rs`; small edits in
  `core_config.py` (two keys, the two refusals replaced), `core_pipeline.py` (preflight, the resolution, the extend
  spec in `polcal_terms`), `cal_chain.py` (one `elif`); `tests/test_e0_refant_extend.py`; three tests updated.
- Oracles: `examples/check_e0.py`, `tools/oracles/e0/{caracal_refant.py,casa_side.py,msutils-venv.sh}`.
- Sources read (ignored): `outputs/c1-sources-20261105/caracal-8f7bb363/` (plus `obsconf_worker.py`,
  `worker_administrator.py`, `config_parser.py` fetched at 8f7bb363), `msutils/msutils-1.2.0.tar.gz`,
  `casa6-mirror/` (the flagging and msvis files above, `list.txt`), `casacore-3.7.1/`.
- Runs, each with `.code/`, `.log` and `.time` beside it, under `/mnt/d/rang/outputs/`: `e0-20261106-01` (R1 R2,
  CARACal fails on R1), `-02` (R1 R2, post-hoc reference), `-03` (X1 X2), `-04` (R3 R4 R5), `-05` (X3 X4, stopped
  building X4), `-06` (X3 X4), `-07` (X6), `-08` (R6), `-09` (command, checker failed), `-10-gate3`, `-11` (command).
- The oracle venv `~/Build/tmp/20261106-e0-msutils` (262 MB) is removed at hand-back; `msutils-venv.sh` rebuilds it.
- Code after the runs (diffed against run -11's `.code/`): in `python/rang` only `core_pipeline.preflight` changed,
  so the `refant: auto` check runs only when calibrate uses the K, G, B, A, F chain (a complex-only configuration
  ignores refant, as before E0); nothing of what the runs measured changed. `examples/check_e0.py` (the WEIGHT
  guard after -09, lint) and `tools/oracles/e0/caracal_refant.py` (formatting, a lint comment) changed afterwards.
- Test seeds 20261191-20261193 (`tests/test_e0_refant_extend.py`) appear nowhere else in the repository.

## For the coordinator

Proposed STATE log paragraph: "E0, 2026-11-07 (implemented; measured; gate 3 met, gates 1 and 2 met after labelled
post-hoc additions; [e0-refant-extend.md](e0-refant-extend.md)): `rang-core calibrate` runs `refant: auto` and
`extendflags`, so E2-B's flag, calibrate and apply validate. `auto` is CARACal's `get_refant`: the first three
antennas **by name** within 1 km of the array centre with no antenna closer than 150 m; CARACal's code sorts by name,
not by flags as its comment and C2e said. It equals CARACal's own function on A1 small, A1 full and two constructed
held-out sets (one with the first choice fully flagged), and on the slice CARACal's msutils 1.2.0 crashes on a FIELD
row without data, where its antenna part chooses nothing and rang refuses. `extendflags` is CASA's
`flagdata(mode='extend')` with CARACal's settings (Rust kernel), run before the polcal solves as CARACal does (not
after): FLAG equals CASA 6.7.6.14 bit for bit on five cases, held-out and stress cases included (60 s chunk edges,
scans merged in a chunk, missing rows, scan selection), and through `rang-core calibrate` on one; the four frozen
cases never fired growfreq or extendpols, which only the post-hoc fifth case does (rule coverage not met as frozen).
On the slice CARACal's own function crashes, so gate 1 is met there only with a post-hoc reference of its antenna
lines (the brief's 'faithful reference run' wording would accept it; the frozen protocol named `get_refant`). No
novelty claim."

Proposed finish-plan item (section 7): E0's five decisions, section 7 of the note (port the code, not the comment;
stop when nothing qualifies; both steps within `data.scans`; the calibrate hash changes once; the frozen observatory
table). Also for E2/E3: CARACal's own `refant: auto` crashes on an MS with a FIELD row without data (msutils 1.2.0).


Non-saturation holds on X2, X3 and X4 (X1 adds 0.92 %, under the 1 % bar). **The rule-coverage condition is not met as
frozen:** `growfreq` and `extendpols` never fire on X1 to X4, because A1's RFI mask flags all four correlations alike
and no 60 s chunk of a baseline has an 80 % flagged integration; `growtime` fires only on X1. X6 (post hoc, 9.3) adds
a case that fires them. X4 ran in -06 after the construction was changed (9.2); run -05 stopped while building X4.
