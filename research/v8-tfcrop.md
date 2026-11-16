# V8 tfcrop: CASA `flagdata(mode='tfcrop')` at parity, a proposal

Next piece of issue #8 and of [v8-open-casa.md](v8-open-casa.md) (piece 1).
Branch `v8-tfcrop` from `main` `d2013ea`, written 2026-11-16 before any new
tfcrop code and before any new CASA probe.

**Status: proposed; nothing measured under this note.** This note takes over
V8b's H1 ([v8b-flagdata.md](v8b-flagdata.md), section 9.3) with a new
protocol. V8b's own verdict stands as recorded there: H1 stopped after
round 2 of 4, development gate not met, held-out case not opened. Nothing
below changes that verdict; this is a second attempt with its own stop
rule, gates carried over unchanged.

## 1. Hypothesis and what is not claimed

- **H.** `rang.tasks.flagdata(vis, mode='tfcrop', ...)` and `rang-core
  flagdata MS mode=tfcrop ...`, with a Rust kernel in `core/`, give CASA
  6.7.6.14's `flagdata(mode='tfcrop')` FLAG and FLAG_ROW on a Measurement
  Set within the gate of section 4, for the parameters of section 2.
- Not claimed: novelty (a reimplementation is not novelty, `AGENTS.md`);
  better flagging than Tricolour or AOFlagger (Tricolour stays the default
  A-step flagger, V8 decision 3); speed (walls recorded, informational).

## 2. Parameters covered

On a Measurement Set, DATA or CORRECTED (and the other columns V8b's
selection accepts): `ntime` (`'scan'` and seconds), `combinescans`,
`timecutoff`, `freqcutoff`, `timefit` and `freqfit` (`line`, `poly`),
`maxnpieces` (1-9), `flagdimension` (`freq`, `time`, `freqtime`,
`timefreq`), `usewindowstats` (`none`, `sum`, `std`, `both`), `halfwin`
(1-3), `extendflags` (True runs V8b's `extend` after tfcrop), `correlation`
(product names and the `ABS_` operator, CASA's default `ABS_ALL`), and V8b's
selection keywords. Refused with `Unsupported`, as V8b: tfcrop on calibration
tables (CARACal's Xf call; no informative case, V8b section 2),
`channelavg`/`timeavg` pre-averaging, `REAL_`/`IMAG_`/`ARG_`/`NORM_`
operators for tfcrop until a case covers them.

CARACal at `8f7bb363` (read 2026-11-16 in WSL `~/Github/caracal`): the flag
worker's `flag_rfi` with `flagger: tfcrop` (full-Stokes config) and the
crosscal `A` step both call `flagdata(mode='tfcrop', usewindowstats='std',
combinescans=False, flagdimension='freqtime', timecutoff=4.0,
freqcutoff=3.0, correlation='', flagbackup=False)` (schema examples), on
`data` (flag worker) or `corrected` (crosscal `flag: col`); every other
parameter at CASA's default (`ntime='scan'`, `maxnpieces=7`,
`timefit='line'`, `freqfit='poly'`, `halfwin=1`, `extendflags=True`). That
call is arm T5 below, and it is the arm that matters most.

## 3. Data and arms

Development cases, as V8b section 4.1 (the same MSs, rebuilt bit-identical
where synthetic): `syn-noise`, `syn-rfi`, `a1`, `luno`; arms T1-T8 of V8b
section 4.1 unchanged (T5 is CARACal's call above).

Held-out cases, compared once after the development gate passes, arms T4
(defaults) and T5 (CARACal): `eso137-ho` (V8b amendment 1), `luno-ho2` (V8b
amendment 3) and the five public SKA fixture MSs (`outer_scans.zip`, sha256
`d4dae56f…144f`, V8a's set). V8b and V8a opened these for the fixed modes
and `listobs`; **no tfcrop rule has been fitted or compared on any of
them** (V8b never ran tfcrop on a held-out case), so they are held out for
this hypothesis.

Probe MSs (labelled `probe`, never gate cases): synthetic MSs written for
identification, with designed band shapes, single-cell offsets and graded
ladders so that one CASA run reads many thresholds; any number of planes.
Every convention taken from a probe is listed in section 7 with its probe
id; every convention taken from documentation cites the sentence.

## 4. Gate (frozen; carried over from V8b section 5.1 unchanged)

A case is one (input, arm) pair; cells are FLAG's (row, channel,
correlation) cells; A = cells flagged after the arm and not before.

- **G1** FLAG equal to CASA's on ≥ 99.9 % of cells;
- **G2** per baseline, |rang − CASA| flag fraction ≤ 1e-3;
- **G3** precision and recall of rang's A against CASA's A each ≥ 0.98;
- **G4** FLAG_ROW equal on every row.

A case is **informative** when CASA's A holds at least 0.01 % of the cells;
uninformative cases are reported and do not count. Reported beside the gate,
not gated: exact equality of FLAG (the fraction of cases bit-identical).

## 5. Decision rule and stop rule

- **H passes** when every informative development case passes G1-G4 with
  the Rust kernel, and then every informative held-out case passes at its
  one comparison. A held-out failure stays a failure in this note; a fix
  may follow and its rerun is labelled post hoc.
- **Budget.** Probes are cheap (V8b: 103 CASA cases in 60 s), so they are
  not rationed by count: identification may use any number of probe runs
  within **two working sessions** (to 2026-11-17 end of day). Development
  **gate runs** (rang against CASA on the development cases) are limited to
  **three**. If the third gate run fails, or the session budget runs out,
  H is reported failed on the development set, the remaining differences
  are recorded per arm, and the held-out cases are not opened.
- **Miss branch.** If H fails or is not reached: `rang.tasks.flagdata` keeps
  refusing `mode='tfcrop'`, the kernel stays behind `rang.tfcrop.ENABLED`,
  whatever conventions were identified are recorded in section 7, and the
  partial result (per-arm G1-G3 numbers) is reported. If H passes on
  development and fails held-out: the same, plus the held-out numbers.
- **Pass branch.** `rang.tasks.flagdata` accepts tfcrop with the parameters
  of section 2; `docs/casa-users.md` and `docs/cli.md` updated; a compact
  archive of CASA's tfcrop flags on the synthetic cases committed so that CI
  tests the kernel without CASA.
- Development differences are fixed in rang's code, never in the gate.
  Gates and this rule are not changed after this commit; any change is a
  dated amendment labelled post hoc.

## 6. Method and provenance (clean room)

- Sources: casadocs (the `flagdata` task page, and the "Mode tfcrop" text of
  casadocs' data examination and editing chapter, `notebooks/data_examination`),
  the version-exact `casatasks.flagdata.__doc__` of the 6.7.6.14 image, and
  CASA's behaviour on probe MSs. **No CASA source and no port derived from
  it is read**; nothing is written from recalled CASA internals. A choice
  that cannot be tied to a doc sentence or a probe is a hypothesis and is
  tested before it is used.
- Documentation facts this starts from (2026-11-16): the robust fit runs
  "in up to 5 iterations", "begins with a straight line fit across the full
  range, and gradually increases to 'maxnpieces' number of pieces with
  third-order polynomials in each piece"; at each iteration values beyond
  N-stddev are excluded and the fit refitted; "Iterations stop when the
  stddev changes by less than 10%, or when 5 iterations are completed";
  then the clean band is divided out and per timestep the stddev of the
  flattened data sets a threshold, again in up to 5 iterations; then the
  same in the other direction. V8b's round 2 tried single-stage fits only;
  the staged fit is the first hypothesis here.
- Order of identification: `freqfit='line'`, then `poly` with
  `maxnpieces=1`, 2, 3, ... (piece boundaries); the flattened-data
  statistic and its precision (float32 against float64 at the threshold);
  T2 (time); T3 ordering; window statistics; extension; chunking.
- Build order: NumPy reference in `rang.tfcrop` until the probes agree;
  then `core/src/tfcrop.rs` (+ the `rang._core` binding) with a test that it
  equals the reference on every probe plane; then the gate runs; then the
  held-out cases once.

## 7. Conventions identified (filled in as work proceeds)

(empty at the freeze)

## 8. Runs and cost

CASA in `rang-o-casa:6.7.6.14` (WSL, Docker, `--network none`), on ext4
copies of the inputs (`~/Github/rang/outputs/v8-tfcrop-20261116-*` in WSL;
casacore bulk I/O over 9p hit ENOMEM before); compact outputs copied to
`D:\rang\outputs\v8-tfcrop-20261116`. Every CASA run, build, test and gate
run is a shared `tools/heavy_lock.py` job (1-4 slots, a few GB); walls in
`research/tool-timings.md`. Disk: under 20 GB (held-out copies made once,
deleted after).

## 9. Results

(none at the freeze)
