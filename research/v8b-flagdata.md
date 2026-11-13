# V8b: CASA `flagdata`, tfcrop and the fixed-rule modes, parity ports

Pieces 1 and 2 of [v8-open-casa.md](v8-open-casa.md) (section 7), in the
order the owner set on 2026-11-12 (section 8.1, decision 2: tfcrop, then the
fixed-rule modes). Branch `claude/v8b-flagdata-8cce7c` from `main` `2a02470`,
with V8a (`claude/v8a-listobs-1c691e`, `2ebfbc4`, not yet on main) merged in
for `rang.tasks` and `docs/casa-users.md`.

**Status: proposed (frozen 2026-11-13).** Sections 1-8 are committed before any
rang `flagdata` code and before any comparison of rang's flags with CASA's.
Nothing is implemented or measured at the freeze.

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

## 9. Development log and results

(Filled in as the work proceeds; empty at the freeze.)
