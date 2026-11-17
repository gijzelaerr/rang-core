# V8b: CASA `flagdata`, tfcrop and the fixed-rule modes, parity ports

Pieces 1 and 2 of [v8-open-casa.md](v8-open-casa.md) (section 7), in the
order the owner set on 2026-11-12 (section 8.1, decision 2: tfcrop, then the
fixed-rule modes). Branch `claude/v8b-flagdata-8cce7c` from `main` `2a02470`,
with V8a (`claude/v8a-listobs-1c691e`, `2ebfbc4`, not yet on main) merged in
for `rang.tasks` and `docs/casa-users.md`.

**Status: measured (2026-11-13).** H2 (the fixed-rule modes): FLAG and every
summary count equal to CASA 6.7.6.14 on all 84 development and 54 held-out
cases; FLAG_ROW differed on six held-out ESO137 cases, so H2 **fails as frozen
for `manual`, `quack`, `elevation` and `shadow`** and passes for `clip`,
`unflag` and `summary`; after a post-hoc correction of one convention, 84/84
and 54/54 equal (section 9.2b, post hoc, 2026-11-13; ho1 is spent for that
rule). A second held-out split opened once afterwards (`luno-ho2`, amendment
3, 2,398 rows wholly flagged without FLAG_ROW): **9 of 9 cases equal in FLAG,
FLAG_ROW and every summary count** (section 9.2c). H1 (tfcrop): **stopped
after round 2 of 4, development gate not met** (CASA's band fit not
identified; best variant 54 of 112 probe planes; section 9.3); rounds 3 and 4
are left open and `rang.tasks.flagdata` refuses `mode='tfcrop'`. Sections 1-8
were committed (f5b0027) before any rang `flagdata` code and before any
comparison of rang's flags with CASA's; amendments 1-3 are dated.

## 1. Hypotheses and what is not claimed

- **H1 (tfcrop).** `rang.tasks.flagdata(vis, mode='tfcrop', ...)` and
  `rang-core flagdata` give CASA 6.7.6.14's `flagdata(mode='tfcrop')` flags on
  a Measurement Set within the toleranced gate of section 5.1, for the arms of
  section 4.1, with a Rust kernel.
- **H2 (fixed rules).** `manual`, `clip`, `quack`, `shadow`, `elevation`,
  `extend`, `unflag` and `summary` give CASA's FLAG and FLAG_ROW bit for bit,
  and `summary` CASA's counts exactly, on the cases of section 4.2, except
  for the measures-dependent boundary cells section 5.2 names.

Not claimed: novelty (a reimplementation is not novelty, `AGENTS.md`); better
flagging than Tricolour or AOFlagger (Tricolour stays rang's default A-step
flagger, decision 3); speed (walls recorded, informational).

**Source.** No CASA source is read for this task. The owner's answer to
decision 5 (2026-11-12) allows a source read only where CASA's licence allows;
a read of `FlagAgentTimeFreqCrop.cc` was not available to this session, so
both pieces work from casadocs 6.7 (`flagdata` task page, read 2026-11-13) and
from CASA's behaviour on probe MSs. That makes section 5.1 the scoping note's
**fallback gate** for tfcrop (≥ 99.9 % cell agreement, per-baseline fractions
within 1e-3), made non-vacuous by the added-flag measures below.

## 2. Scope: what is in, what is refused

In, on a Measurement Set: `mode` = `manual`, `clip`, `quack`, `shadow`,
`elevation`, `tfcrop`, `extend`, `unflag`, `summary`; selection keywords
`field`, `spw` (spw ids, channel ranges `a~b`, frequency ranges in Hz, kHz,
MHz, GHz, `*`, comma lists, `;` channel lists), `antenna` (ids, names,
`&`/`&&`/`&&&` baseline forms, `!` negation), `scan`, `timerange` (CASA's
`YYYY/MM/DD/hh:mm:ss[.s]` forms and `a~b`, `>a`, `<b`), `uvrange` (m, km,
`a~b`, `<b`, `>a`; no wavelength units), `observation`, `array`,
`correlation` (product names, and for `clip`/`tfcrop` the `ABS_`, `REAL_`,
`IMAG_`, `ARG_`, `NORM_` operators); `autocorr`; `datacolumn` `DATA`,
`CORRECTED`, `MODEL`, `RESIDUAL`, `RESIDUAL_DATA`; `flagbackup`.
The CARACal case list (flag worker at `8f7bb363`: unflag, `autocorr`, quack,
elevation, shadow, `flag_spw` channel ranges, `flag_time`, `flag_scan`,
`flag_antennas`, `flag_manual` rules, tfcrop) is covered by this list.

In, on a calibration table: `clip` on `CPARAM` with `ABS_ALL` (CARACal's
`clip clipminmax=[-0.6, 0.6]` on the Df table, C1 step 15).

Refused with `rang.tasks.Unsupported` before anything is written (the W4
rule): `rflag`, `antint`, `list`, `display`, `savepars`, `action` other than
`'apply'`, `intent`, `feed`, `uvrange` in wavelengths, `shadow addantenna`,
`clip channelavg=True`, `datacolumn` `FLOAT_DATA`, `WEIGHT`,
`WEIGHT_SPECTRUM`, tfcrop on calibration tables, and any other value not
listed above.

Not in, stated now: **tfcrop on calibration tables** (CARACal's Xf-table
call, `usewindowstats='both'`, `ntime='60s'`, `combinescans=True`). The one
measured case, C6's run of CASA's chain (C1 O2), shows CASA adding 0 flags on
that table, so no informative case exists; it is a later piece if one is
found.

`extend` reuses E0's kernel (`rang.flag_extend`, `core/src/flag_extend.rs`),
which E0 wrote from CASA's `FlagAgentExtension.cc` (`docs/licence.md`; not
this task's licence point). tfcrop's default `extendflags=True` runs it after
tfcrop with the parameters casadocs gives (growtime 50, growfreq 80,
extendpols), section 6.

## 3. Oracle

CASA `flagdata` from `casatasks==6.7.6.14` in `rang-o-casa:6.7.6.14`
([o-casa.md](o-casa.md)), run by a `tools/oracles/casa/flagdata.sh` (WSL,
Docker, `--network none`) with `flagbackup=False`. `flagdata` writes, so each
arm runs on its own fresh copy of the input MS under `D:\rang\scratch\v8b-*`
(never on the original); rang runs on a second copy of the same input.
Kept per arm: FLAG and FLAG_ROW as compressed arrays, SHA-256 of both columns,
CASA's returned dictionary (`summary`), its log, the parameters, image id,
code hashes and wall time. CASA's `flagdata(mode='summary')` on the CASA copy
after the arm supplies the counts for every arm.

Probe runs (CASA only, on probe MSs, to read off conventions such as whether
tfcrop's statistics skip flagged points, the number of iterations, CASA's
quack boundary and the elevation frame) may run after the freeze; their
outputs are labelled `probe` and every convention taken from them is listed as
a development fix in section 9.

## 4. Data and arms

### 4.1 tfcrop

Cases. Development: `syn-noise` (synthetic, rang's table writer: 6 antennas,
256 channels, 120 integrations of 8 s, 4 correlations, a smooth bandpass times
complex Gaussian noise, no RFI; every flag is marginal, the case that tests
the statistics), `syn-rfi` (the same plus narrow-band persistent lines, a
time burst, a broadband spike and 2 % pre-existing flags), `a1` (A1's small
simulated MS with its injected RFI, `D:\rang\outputs\c2a-20261106-03\casa\a1.ms`,
16 antennas, 64 channels), `luno` (the LUNO 1934−638 slice
`outputs/luno-solve-20261029-02/work.ms`, real RFI; O-CASA measured CASA's
tfcrop adding 1.49 % there). Held out, compared once after the development
gate passes: `eso137-ho`, one scan of the ESO137 pilot raw MS
(`D:\rang\outputs\20261103-gemclean-heldout\real\raw.ms`), not E2-A's scans 9,
10 or 11, channels 1024-2047 of spw 0, split by CASA `split` (`keepflags=True`,
`datacolumn='data'`) into `D:\rang\scratch`; its DATA was never compared by
any rang flagger.

Arms (run on every case unless marked):

| Arm | Settings (others at CASA's defaults) | Isolates |
| --- | --- | --- |
| T1 | `flagdimension='freq'`, `extendflags=False` | the frequency fit and its statistics |
| T2 | `flagdimension='time'`, `extendflags=False` | the time fit |
| T3 | `extendflags=False` (`freqtime`) | the two passes in order |
| T4 | CASA's defaults (`extendflags=True`) | the extension after tfcrop |
| T5 | CARACal's flag worker: `usewindowstats='std'`, `combinescans=False`, `flagdimension='freqtime'`, `timecutoff=4`, `freqcutoff=3`, `correlation=''`, `datacolumn='data'` | CARACal's call |
| T6 | `usewindowstats='both'`, `halfwin=2` (`syn-rfi`, `luno`) | window statistics |
| T7 | `timefit='poly'`, `freqfit='line'`, `maxnpieces=4`, `flagdimension='timefreq'` (`syn-rfi`, `luno`) | the other fits and order |
| T8 | `ntime='60s'`, `combinescans=True`, `correlation='ABS_XX,YY'` (`luno`, `a1`) | chunking and correlation selection |

The held-out case runs T4 and T5.

### 4.2 The fixed-rule modes

Cases. Development: `syn-edges` (rang's table writer: 6 antennas with two of
them 9 m apart so that one shadows the other at low elevation; scans of
different lengths, one shorter than the quack interval, one with its first
rows already flagged; a source track through 20° elevation; two spectral
windows with frequency ranges ending on a channel boundary and mid-channel;
autocorrelations; DATA values with NaN, Inf, exact zeros and amplitudes on and
next to a clip limit; existing FLAG and FLAG_ROW), `luno`, `a1`, and the C6 Df
table of CASA's chain for calibration-table `clip`. Held out: the five public
SKA fixture MSs (`outer_scans.zip`, sha256 `d4dae56f…144f`) and `eso137-ho`.

Arms (each a CASA call; the first eleven are CARACal's flag worker with its
schema examples):

| Arm | Call |
| --- | --- |
| M1 | `mode='unflag'` |
| M2 | `mode='manual', autocorr=True` |
| M3 | `mode='quack', quackinterval=8, quackmode='beg'` |
| M4 | quack `endb`, `tail`, `end` (three arms, interval 8 s), and `beg` with `quackincrement=True` |
| M5 | `mode='elevation', lowerlimit=0, upperlimit=90`; and `lowerlimit=20, upperlimit=60` |
| M6 | `mode='shadow', tolerance=0`; and `tolerance=2` |
| M7 | `mode='manual', spw='*:856~880MHz,*:1658~1800MHz,*:1419.8~1421.3MHz'` |
| M8 | `mode='manual', spw` channel forms: `'0:0~9;20~29'`, `'*:5~7'`, `'1'` |
| M9 | `mode='manual', timerange=` a `a~b` range inside a scan |
| M10 | `mode='manual', scan='1,3'`; `field=` a name and an id |
| M11 | `mode='manual', antenna=` one name; `'m001&m002'`; `'!m000'`; with a `timerange` |
| M12 | `mode='manual', uvrange='<100m'`; `'1~3km'` |
| M13 | `mode='manual', correlation='XY,YX'` |
| M14 | `mode='clip', clipminmax=[0, 50]` (`ABS_ALL`); `clipoutside=False`; `clipzeros=True`; `correlation='REAL_XX'`; NaN and Inf with an empty range |
| M15 | `mode='extend', growtime=80, growfreq=80, growaround=True, flagneartime=True, flagnearfreq=True, ntime='60s', combinescans=True` (E0's CARACal call) and the defaults |
| M16 | `mode='summary'` with defaults, with `basecnt=True`, with `spwchan=True, spwcorr=True` |
| M17 | `mode='clip', clipminmax=[-0.6, 0.6], datacolumn='CPARAM'` on the Df table |

Every arm runs on every case it applies to (M17 on the Df table only; M16
after M3, M6 and M7 so that the counts are not trivial). The held-out cases
run M1, M2, M3, M5, M6, M7, M14 and M16.

## 5. Measures and frozen tolerances

A **case** is one (input, arm) pair. Cells are the (row, channel,
correlation) cells of FLAG. Agreement is counted over every cell of the MS, and
over the arm's selection where the arm selects.

### 5.1 tfcrop (H1)

Per case, with A = cells flagged after the arm and not before:

- **G1** FLAG equal to CASA's on ≥ 99.9 % of cells;
- **G2** per baseline, |rang − CASA| flag fraction ≤ 1e-3;
- **G3** precision and recall of rang's A against CASA's A each ≥ 0.98;
- **G4** FLAG_ROW equal on every row.

A case is **informative** when CASA's A holds at least 0.01 % of the cells; a
flagger that adds nothing then fails G3, and one that flags everything fails
G1. Uninformative cases are reported and do not count for or against.

### 5.2 The fixed-rule modes (H2)

Per case: FLAG and FLAG_ROW equal to CASA's on every cell and row; `summary`:
every count in CASA's returned dictionary (`total`, `flagged`, and per
`antenna`, `array`, `correlation`, `field`, `observation`, `scan`, `spw`, and
`baseline`, `spw:channel`, `spw:correlation` when asked) present in rang's
with an equal value. Allowed differences, each counted and listed:

- `elevation`: cells of an (antenna, time) whose rang elevation is within
  3 arcsec of a limit (E2 measured casacore `AZELGEO` against astropy to
  ≤ 1.3 arcsec; the frame CASA uses, geodetic or geocentric, is read off a
  probe and recorded as a development fix);
- `shadow`: rows whose projected separation is within 1 mm of
  r1 + r2 − tolerance (whether CASA uses the MS UVW or recomputes it, and
  whether antennas without rows shadow, are read off a probe);
- `clip`: cells whose value is within 1e-6 relative of a limit (rang and CASA
  may form |V| in different precisions).

A case where CASA changes no flag is reported as uninformative for its mode.

### 5.3 Refusals

Every refused keyword of section 2 is tested to raise `Unsupported` before
the MS is opened for writing (FLAG's SHA-256 unchanged).

## 6. Implementation (proposed)

- `core/src/tfcrop.rs` (+ `core/py/src/tfcrop.rs`, `rang._core.tfcrop`): the
  per-(chunk, baseline) time-frequency kernel on amplitudes as casadocs
  describes it: mean spectrum over time, robust piecewise-polynomial (or line)
  fit, deviation in units of the residual standard deviation, up to five
  iterations, `freqcutoff`; then the time direction with `timecutoff`; window
  statistics with `halfwin`; flags only added. Rust unit tests on the impulse
  and step inputs.
- `python/rang/flagdata.py`: CASA's selection parser (the forms of section 2),
  the fixed-rule modes in NumPy over chunks of rows through
  `core_writeback.WriteBack` (flag backup, journal), CASA's chunking
  (`ntime`, `combinescans`, reusing `flag_extend.casa_chunks` where the
  convention is the same), the tfcrop driver, `summary`.
- `rang.tasks.flagdata(...)` with CASA's keyword names and defaults, refusing
  as section 2; `rang-core flagdata MS --mode ... [key=value ...]` printing
  the summary dictionary as JSON; a receipt for every writing call.
- `tools/oracles/casa/flagdata.sh`, `flagdata.py` (CASA side), `v8b_cases.py`
  (writes the synthetic MSs), `compare_flagdata.py` (section 5, a verdict JSON
  per case); a compact archive of CASA's FLAG hashes and summaries on the
  synthetic cases in `research/results/` so that a test runs without CASA.
- Docs: `docs/casa-users.md` rows for `flagdata`; the CLI page.

## 7. Decision rule

- **H1 passes** when every informative development case passes G1-G4, and
  then the held-out cases pass at their one comparison. **H2 passes per mode**
  when every development case of that mode passes, then the held-out cases. A
  mode or H1 that fails on a held-out case stays failed in this note; a fix
  may follow and its rerun is labelled post hoc.
- A failure of H1 does not affect H2's verdicts, and one mode's failure does
  not affect another's.
- Development differences are fixed in rang's code, never in the tolerances,
  and each fix is listed with its cause in section 9.
- **Stop rule.** tfcrop: at most four development rounds (a round = one CASA
  probe or gate run and the rang fixes it prompts); after the fourth, the
  remaining differences are recorded and H1 is reported failed on the
  development set, without opening the held-out case. Fixed modes: a
  convention that cannot be read off the docs and probes is a recorded gap and
  that mode fails.
- Tolerances are not changed after this commit; any change is a dated
  amendment labelled post hoc.

## 8. Cost

Light: CASA runs and comparisons are shared heavy-lock jobs (1-2 slots, a few
GB), never exclusive; walls are informational and recorded in
`research/tool-timings.md`. Disk: per-arm copies of the small MSs (under
0.1 GB each) and of `eso137-ho` (about 4 GB, created once, copied per arm and
deleted after). Size: three to four sessions.

## 8a. Amendment 1 (2026-11-13, before any held-out data is opened)

Labelled as an amendment; gates, tolerances and decision rules are unchanged.
The ESO137 pilot raw MS holds one scan (scan 2, the target `ESO137-pilot`,
3,598 s, 850,950 rows) with **512 channels**, not 4,096 (read with rang's
`listobs` metadata only), so "channels 1024-2047" does not exist. `eso137-ho`
is instead **all 512 channels of the first 600 s of scan 2**
(`split(timerange=<first 600 s>, keepflags=True, datacolumn='data')`), about
2.5 GB. Scan 2 is not one of E2-A's held-out scans (9, 10, 11).

## 8b. Amendment 2 (2026-11-13, after development run 01, before any held-out data)

Labelled as an amendment; gates, tolerances and decision rules are unchanged.
Three development cases are added, all synthetic, so that conventions read
off run 01 rest on more than one case:

- `v8b_cases.py` wrote UVW with the opposite sign to the MS convention
  (ANTENNA1's position minus ANTENNA2's, as the LUNO slice's UVW column
  has it; checked on six LUNO rows). It now writes the MS convention;
  `syn-edges-uvwneg` keeps the old sign, so that shadow on both tells
  whether CASA reads the UVW column or recomputes it from the positions.
- `syn-edges-nom001`: `syn-edges` without the rows of m001, the antenna
  that shadows m000. Does an antenna without rows shadow?
- uvrange arms `M12c` (`20~200m`), `M12d` (`0.02~0.2km`), `M12e` (`>500m`):
  in run 01 the only range arm (`1~3km`) selected no rows (CASA and rang
  both refused it with a null selection), so ranges and `km` were untested.

Development run 02 (`round.sh 02`) reruns every development case on the
rebuilt synthetic MSs.

## 8c. Amendment 3 (2026-11-13, after the held-out run ho1, before ho2 is opened)

Labelled as an amendment; gates, tolerances and decision rules are unchanged.
The R1 FLAG_ROW correction (section 9.2a) was fitted after `eso137-ho` was
compared, so **ho1 is spent for R1**: its post-hoc 54/54 (section 9.2b) shows
only that the rule fits. The coordinator asked for a second held-out split
that no V8 work has opened, compared once under section 5.2 and 7 with rang
at the commit that adds this amendment (R1 as corrected, nothing else
changed):

- `luno-ho2`: scan 19 (field `J1833-2103`, 11 integrations, 17,556 rows,
  56 antennas, 4,096 channels) of the E2-B LUNO calibrators MS
  `D:\rang\data\e2-b\e2b.ms`, by `split(scan='19', keepflags=True,
  datacolumn='data')` (`tools/oracles/casa/v8b_heldout2.sh`). The same
  observation as the development `luno` slice (4 antennas, scan 2), but other
  scans, times and 52 more antennas; no V8 task has opened `e2b.ms` (V8a used
  the SKA fixture and ESO137; V8b the slice). Reading FLAG for V8b produces
  no E2 numbers.
- Arms: the nine fixed-mode held-out arms (M1, M2, M3, M5a, M5b, M6a, M7,
  M14a, M16a), `v8b_plan.py heldout2`. tfcrop is not run (H1 has not passed
  its development gate).
- Result: the mode passes on ho2 when every case of that mode is equal in
  FLAG, FLAG_ROW and every summary count within section 5.2's tolerances. The
  number of rows wholly flagged in FLAG with FLAG_ROW false is recorded, since
  R1's correction is only exercised by such rows; if there are none, ho2 tests
  R1 only on the rows the modes flag.
- Recorded whichever way it goes; ho1's frozen verdict (H2 fails for four
  modes) stands regardless.

## 9. Development log and results

### 9.1 Runs

| Run | What | Where | Wall |
| --- | --- | --- | --- |
| CASA 01 | the 103 development cases of section 4 (plan `plan-dev.json`) | WSL `~/Github/rang/outputs/v8b-flagdata-20261113-01`, copy `D:\rang\scratch\v8b-20261113\casa-01` | 59.5 s, 304 MB |
| rang 01 | the same cases, first code (`6b6865f`) | `D:\rang\scratch\v8b-20261113\rang-01`, verdicts `dev-01.json` | 241 s |
| rang 01b, 01c | the fixed modes after the conventions below; tfcrop after F1 | `rang-01b`, `rang-01c`, `dev-01b.json`, `dev-01c.json` | – |
| round 02 | amendment 2: rebuilt synthetic MSs (UVW sign), the new cases, the `probe-fit` tfcrop probe | `casa-02`, `rang-02`, `dev-02.json` | – |

Run 01's synthetic MSs (old UVW sign) are kept in
`D:\rang\scratch\v8b-20261113\cases-r01`.

### 9.2 Fixed-rule modes: conventions read off CASA's output

Each is a development fix from CASA run 01 (no CASA source read), with the
case it was read from. After them, rang 01b: **77 of 77** fixed-mode
development cases equal (FLAG, FLAG_ROW and every summary count).

| Id | Convention | Read from |
| --- | --- | --- |
| Q1 | quack's window includes its boundary: `beg` flags TIME ≤ t0 + interval, `endb` TIME ≥ t1 − interval, `tail` TIME > t0 + interval, `end` TIME < t1 − interval, with t0, t1 the first and last TIME of the scan (of its unflagged rows with `quackincrement`) | `syn-edges` M3, M4a-d (8 s integrations, interval 8 s) |
| R1 | FLAG_ROW: set where a row is then wholly flagged only for `manual`, `quack`, `shadow`, `elevation` without a `spw` or `correlation` selection; left as it was by `clip`, `extend`, `tfcrop` and by any spw or correlation selection; `unflag` clears it where it leaves a cell unflagged | `syn-edges` M2 (set), M8c `spw='1'` and M14b (unchanged although rows became wholly flagged), M1 |
| A1 | a bare antenna name selects that antenna's cross-correlations only; `!name` removes them (the antenna's autocorrelation stays selected) | `syn-edges` M11a, M11c, M11d |
| H1 | shadow reads the UVW column in the MS convention (ANTENNA1 − ANTENNA2): in a row with projected distance below r1 + r2 − tolerance, ANTENNA2 is flagged when w > 0, else ANTENNA1, on all its rows (autocorrelation included) at that time | `syn-edges` M6a, M6b; `syn-edges-uvwneg` (UVW negated: CASA flags the other antenna, so it reads the column) |
| H2 | a pair of ANTENNA-table antennas with no row at that time is projected from the antenna positions and the field's direction in ITRS (astropy here), and can shadow | `syn-edges-nom001` M6a, M6b (m001 has no rows; CASA flags m000 at 61 times, rang's ITRS projection the same 61) |
| E1 | elevation uses the geocentric horizon (casacore `AZEL`), not astropy's geodetic one: the 20° crossing on `syn-edges` agrees to the integration with the geocentric elevation and is three integrations (0.1°) off with the geodetic one | `syn-edges` M5b |
| S1 | a frequency range selects from the first channel whose centre is ≥ the low end to the last whose centre is ≤ the high end; a range between two centres selects both neighbours | `a1` M7 (13.4 MHz channels: `1419.8~1421.3MHz` gives channels 41 and 42); `syn-edges` M7 |
| U1 | `summary` counts an autocorrelation once for its antenna; `basecnt=True` adds `baseline` (`A&&B`) and `antenna:scan` (`A:scan`) | `syn-edges` M16a, `luno` M16a |
| N1 | a selection with no rows is an error (CASA: "MSSelectionNullSelection"), raised before anything is written | `syn-edges` M12b |

Round 02 (amendment 2's cases, rebuilt MSs, rang at `cfc1f83`): **84 of
84 fixed-mode development cases equal** (`dev-02.json`, and `dev-02b.json`
for the shadow cases after H2), 63 of them informative, including the
uvrange ranges M12c-e and both shadow probes. The 21 uninformative ones
(CASA changed no flag): `syn-edges` M5a and M12b; on `luno` M2, M5a, M5b,
M6a, M6b, M7, M14a, M14c-e; on `a1` M2, M5a, M6a, M6b, M14a, M14c-e; the
`B-twin` Df table (M17).
Informative cases (CASA changed at least one flag) among run 01's 77: all
`syn-edges` arms except M12b; on `luno` and `a1` the shadow, elevation (0-90°)
and clip arms changed nothing (no shadowing, no NaN, amplitudes inside the
range), so those modes rest on `syn-edges`. Untested, stated now: `unflag`
with a spw or correlation selection (FLAG_ROW); `observation` and `array`
selections (every MS here has one of each); timerange without a date across
midnight; a field name pattern.

### 9.2a Held-out run (fixed modes, H2), 2026-11-13

Run `ho1` (`round.sh ho1` with the held-out plan, 54 cases: M1, M2, M3,
M5a, M5b, M6a, M7, M14a, M16a on each of the five SKA fixture MSs and
`eso137-ho`; CASA 300 s, 691 MB peak; rang 153 s; WSL
`~/Github/rang/outputs/v8b-flagdata-20261113-ho1`, copies `casa-ho1`,
`rang-ho1`, verdicts `dev-ho1.json`), rang at `5fd9eb0`, compared once:

- **FLAG equal to CASA's on all 54 cases; every `summary` count equal.**
  On `eso137-ho` both refuse CARACal's `flag_spw` string (CASA: "No valid SPW
  & Chan combination found"; rang: no channels selected), so M7 and M16a's
  spw call change nothing on either side.
- **FLAG_ROW differs on six `eso137-ho` cases** (M2, M3, M5a, M5b, M6a,
  M16a; 719 to 5,219 rows). `eso137-ho` has 5,219 rows wholly flagged in
  FLAG with FLAG_ROW false, which no development MS had. R1 set FLAG_ROW on
  every wholly flagged row; CASA sets it only on the rows the mode itself
  flags (checked: CASA's FLAG_ROW equals the input's OR the autocorrelation
  rows for M2, OR the quack rows for M3, and is unchanged for M5a and M6a,
  which flag nothing).

**Verdict as frozen (section 7): H2 fails on the held-out set for `manual`,
`quack`, `elevation` and `shadow` (FLAG_ROW); it passes for `clip`,
`unflag` and `summary`'s counts; `extend` was not in the held-out list.**

Post hoc (labelled; the held-out verdict above stands): R1 corrected to
"FLAG_ROW |= the rows the mode flags whole" (`_finish_rows`), then the
development cases and the held-out cases rerun against the same CASA output
(section 9.2b).

### 9.2b Post-hoc rerun after the R1 correction (labelled post hoc, 2026-11-13)

The R1 correction (`_finish_rows`, commit `2cb37ce`, 2026-11-13) was made
after the ho1 comparison and is post hoc. **ho1 (`eso137-ho`) is therefore
spent for R1**: it cannot test the corrected rule again; amendment 3's
`luno-ho2` is the fresh test (section 9.2c).

rang at `2cb37ce` against the same CASA outputs (no CASA rerun): **84 of 84
fixed-mode development cases** (`dev-02c.json`, 42 s) and **54 of 54
held-out cases** (`dev-ho2.json`, 157 s) equal in FLAG, FLAG_ROW and every
summary count. The held-out verdict of 9.2a stands as frozen; this rerun
shows only that the corrected rule fits both sets.

### 9.2c Second held-out run ho2 (`luno-ho2`, amendment 3), 2026-11-13

Run `ho2l` (`v8b_heldout2.sh`, then `PLAN=heldout2 round.sh ho2l`; the
prefix `ho2l` keeps it apart from 9.2b's `dev-ho2.json`): CASA `split` 50 s,
726 MB peak; CASA `flagdata` 288 s; rang 100 s; rang at `8090d08`
(amendment 3, R1 as corrected); WSL
`~/Github/rang/outputs/v8b-flagdata-20261113-ho2l`, copies `casa-ho2l`,
`rang-ho2l`, verdicts `dev-ho2l.json`; compared once.

- `luno-ho2`: 17,556 rows × 4,096 channels × 4 correlations, 53.4 % of
  cells flagged on input, **2,398 rows wholly flagged in FLAG with FLAG_ROW
  false** (FLAG_ROW false on every row), so the R1 case that failed ho1 is
  exercised: CASA leaves FLAG_ROW false on them unless the mode flags the
  row (M3 and M16a: 3,192 quack rows set; 1,962 wholly flagged rows stay
  FLAG_ROW false after M16a).
- **9 of 9 cases pass: FLAG, FLAG_ROW and every summary count equal.**
  Informative (CASA changed cells): M1 unflag (153.6 M cells), M3 quack
  (24.4 M), M7 the CARACal spw string (0.20 M), M16a (24.5 M, with the three
  summaries). Uninformative (CASA changed nothing, nor rang): M2 (the split
  has no unflagged autocorrelation cells to flag), M5a, M5b, M6a, M14a.

**Verdict: on ho2 R1 as corrected passes for `manual` (M7), `quack` and the
chain M16a; `elevation` and `shadow` are equal but uninformative on ho2. The
frozen ho1 verdict (H2 fails for `manual`, `quack`, `elevation`, `shadow`)
stands.**

### 9.3 tfcrop (H1)

Round 1 (CASA run 01 against rang 01 and 01c). rang 01's first guess (an
absolute residual, one sd per plane) gave precision and recall about 0.2 on
`syn-noise` T1. Reading CASA's flags on `syn-noise` (noise only, so every
flag is marginal):

- F1 (development fix): CASA flags both tails, near 3σ (T1); the scale is
  per time row. The relative residual r = data / fit − 1 against the fitted
  time-mean band, compared with 3 × the rms of r over the row's channels,
  reproduces CASA's flags on smooth bands with precision 0.98 and recall
  0.92 over 24 planes; the disagreeing cells all lie within 3 % of the
  threshold.
- Open: CASA's band fit. On planes whose synthetic band has a sharp minimum
  (`|polynomial|` through zero), CASA flags whole channels at every time
  well away from the minimum (`syn-noise` baseline 2-5 YY: channels 0-9),
  which no piecewise polynomial of degree 1-3 with 1-7 pieces, global
  polynomials of degree 3-7, or lower-envelope (positive-clipped) robust
  fits tried here reproduce. `probe-fit` (round 02) is designed to map it.
- rang 01c (F1 in the NumPy reference, one pass): `syn-noise` T1 precision
  0.96, recall 0.64 (the sharp-minimum planes); `syn-rfi` T1 1.00, 0.40;
  `a1` T1 0.65, 0.20. H1 fails G3 everywhere at round 1.

Round 2 (CASA round 02, the `probe-fit` probe: 112 planes, each a known band
shape times (1 ± e) with e = 0.002, 0.005 or 0.02 alternating in time and
channel, so that the relative deviation of every point is exactly e;
`flagdimension='freq'`, `extendflags=False`; arms P1 defaults, P2
`maxnpieces=1`, P3 3, P4 9, P5 `freqfit='line'`, P6 the time direction):

- F2 (read off P1-P5): the flagged channels barely depend on e, so the
  per-row threshold is 3 × the rms of r **including the fit's own misfit**,
  as F1 has it: a flag marks where the fit leaves the band by more than 3 ×
  the row's rms. Lines are never flagged (P1-P5), cubics never with one
  piece and x⁴ is (P2), so a piece is a cubic and `freqfit='line'` fits
  lines; steps, Vs and narrow bumps are flagged near the feature with every
  piece count.
- Open: the fit itself. With one piece (P2) the best of the fits tried
  (least squares, iterated one-sided or two-sided clipping at 1-3 sd, 1-10
  iterations, flag iterations 1-10, relative or absolute residual, float32 or
  float64 normal equations) reproduces CASA's channels on 54 of 112 planes
  (98.5 % of cells); plain least squares matches some shapes exactly
  (`sine2`: channels 253-255) and not others (`poly4`: CASA flags channels
  0-2 and 253-255 where least squares gives |r| / rms ≤ 2.4; a one-sided
  sine is flagged on one side only, which least squares cannot do).
- rang round 02 (F1 reference, unchanged): the same T verdicts as rang 01c;
  T5 and T6 (window statistics) now run and fail (precision 0.04-1.00,
  recall 0.26-0.59).

**Status of H1: stopped after round 2 of the four the stop rule allows
(coordinator, 2026-11-13); development gate not met; the held-out case was
not opened; rounds 3 and 4 are left open.**
`rang.tasks.flagdata` refuses `mode='tfcrop'` (the NumPy reference stays in
`rang.tfcrop` behind `ENABLED`, for the harness), and no Rust kernel was
written, since the algorithm it would port is not yet known. Two routes on:
two more probe rounds aimed at the fit (single-piece shapes with one feature
each, then piece boundaries), or the owner allowing a read of CASA's
`FlagAgentTimeFreqCrop.cc` under decision 5 (the file's licence header is
GPL or LGPL "or later" if it is like the flagging files E5 checked; this
session had no permission to read it).

## 10. For the coordinator

- Branch `claude/v8b-flagdata-8cce7c` (pushed; not merged). V8a is on main
  and `origin/main` is merged in (`2987521`). Coordinator decision
  (2026-11-13): V8b merges with H2 recorded as failed as frozen on ho1, R1
  post hoc, ho2 run (9/9), tfcrop stopped and refused.
- New: `rang.flagdata` (selections, fixed modes, summary, chunks),
  `rang.tfcrop` (NumPy reference, `ENABLED = False`), `rang.tasks.flagdata`
  (CASA keywords, refusals, a receipt per writing call), `rang-core
  flagdata MS key=value ...`, `rang.measures.elevation` (geodetic and
  geocentric), tools under `tools/oracles/casa/` (`flagdata.py/.sh`,
  `rang_flagdata.py`, `compare_flagdata.py`, `v8b_cases.py`, `v8b_plan.py`,
  `v8b_heldout.sh`, `archive_flagdata.py`), the CI archive
  `research/results/v8b-flagdata-casa-synthetic.json` (40 cases, checked by
  `tests/test_v8b_flagdata.py` without CASA), `docs/casa-users.md` section.
- No Rust: the fixed modes are row masks in NumPy (seconds on 141,825 rows ×
  512 channels); tfcrop's Rust kernel waits for the algorithm (section 9.3).
- Open for the owner: tfcrop rounds 3 and 4 (probe rounds aimed at the
  fit), or a read of `FlagAgentTimeFreqCrop.cc` under decision 5's licence
  condition (this session's permission to read it was denied).
- STATE paragraph: *V8b `flagdata` (2026-11-13): `rang.tasks.flagdata` and
  `rang-core flagdata` port CASA's manual, clip, quack, shadow, elevation,
  extend, unflag and summary modes; FLAG and summary counts equal CASA
  6.7.6.14 on 84 development and 54 held-out cases; FLAG_ROW differed on six
  held-out ESO137 cases (a convention no development MS exercised), so four
  modes fail as frozen; after a post-hoc fix a fresh LUNO held-out split
  (2,398 wholly flagged rows without FLAG_ROW) is equal on 9 of 9 cases.
  tfcrop stopped after two of four rounds (CASA's band fit unidentified);
  refused.
  research/v8b-flagdata.md.*
- Checks: `tests/test_v8b_flagdata.py` (56 passed) with
  `test_v8a_listobs.py` and `test_w4_1_receipts.py`; the full `python -m
  rang.check` result is in the hand-back.
- Process: early smoke runs and one 4-min rang run (06:28-07:20 UTC) ran
  outside the heavy lock, partly during another session's exclusive timed
  benchmark; everything after ran under it with 1 slot.
- Left on disk: `D:\rang\scratch\v8b-20261113` (synthetic MSs, CASA and
  rang runs, verdicts, the 4.4 GB `heldout/eso137-ho.ms`, which
  `v8b_heldout.sh` rebuilds, and the 4.4 GB `heldout/luno-ho2.ms`, which
  `v8b_heldout2.sh` rebuilds); WSL `~/Github/rang/outputs/v8b-flagdata-20261113-*`.
