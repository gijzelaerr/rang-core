# E2-N follow-up: CASA's K flags and the placement of 3a's 73 cells (2026-11-18)

Issue #7, the coordinator's decision of 2026-11-18 in [e2n-native.md](e2n-native.md). Both jobs are **seen and
post hoc**: E2-N's rows were read on 2026-11-18 and no frozen E2-N row is rescored from anything here. Host nash
(shared, nice 19, ionice -c3, heavy lock); run root `~/rang-data/outputs/e2n-followup-20261118` on nash, with its
own copy of `e2n.ms` (E2-N's run root and MS are only read). Scripts:
[results/e2n-followup/scripts/](results/e2n-followup/scripts/).

## 1. Plan (written before any CASA or Tricolour run)

### 1.1 What was read before this plan (read-only, labelled)

Before this section was written, two read-only probes ran on E2-N's MS and tables, and `e2n.ms` was copied into
the follow-up's run root (`cp -a`, one lock slot):
- [k_probe.py](results/e2n-followup/scripts/k_probe.py): CASA's K table on J1939−6342 (FPARAM, FLAG) beside the
  flags CASA was given (`rang_apply_20261117T034709Z`, rang's FLAG after calibrate), per antenna and per baseline to
  the refant list m022, m023, m024. Output [probe/k-probe.json](results/e2n-followup/probe/k-probe.json).
- [bl_versions.py](results/e2n-followup/scripts/bl_versions.py): wholly flagged baselines on J1939−6342 in three
  flag versions, on E2-N's MS and on the dry run's A1 small. Outputs
  [probe/bl-versions.json](results/e2n-followup/probe/bl-versions.json),
  [probe/bl-versions-dryrun.json](results/e2n-followup/probe/bl-versions-dryrun.json),
  [probe/dryrun-perscan.txt](results/e2n-followup/probe/dryrun-perscan.txt).

What they show:

| J1939−6342 flags | unflagged cells | wholly flagged baselines (of 1,891) | antennas with no unflagged cell to m022 |
| --- | ---: | ---: | --- |
| `rang_original` (native) | 66.3 % | 0 | none |
| `rang_calibrate_…` (after rang's flag stage) | 38.3 % | 0 | none |
| `rang_apply_…` (after rang's calibrate; what CASA got) | 32.6 % | **351** | **0, 1, 2, 3, 6, 7, 9, 11, 12, 15, 16, 18, 21, 23, 26, 29, 30, 41, 45** |

- That list is **exactly** the 19 antennas CASA's K left flagged with FPARAM 0. No other antenna is flagged in CASA's
  K, and every antenna with at least one unflagged cell on its baseline to m022 has a solution.
- The dry run repeats it per scan. On A1 small (refant m008, two J1939−6342 scans), the antennas with no unflagged cell
  to m008 after calibrate are 0, 1, 3, 5, 10 on scan 1 and 0, 1, 3, 10, 13 on scan 23. CASA's K flagged exactly those
  sets per solution interval. Before calibrate, only antenna 10 is cut off on each scan. Antenna 10 is also the one
  rang's K flagged on the dry run.
- Between the two versions, rang's calibrate touches J1939−6342's FLAG in one step only: `extendflags` (step 6 of
  `calibrate/summary.json`: `growtime` 80, `growfreq` 80, `growaround`, `flagnearfreq`, `flagneartime`, `ntime` 60,
  on fields 1 and 4). That step is CARACal's: it runs after crosscal, before the polarisation solves
  ([c1-calibration-chain.md](c1-calibration-chain.md) section 1.3, step 10; CARACal `8f7bb363` `polcal_worker.py`).
  Its `growtime`/`growfreq` rules flag a whole baseline's channel or time when 80 % of it is already flagged. After
  the flag stage 61.7 % of the cells are flagged, so whole baselines go.

**Hypothesis (from the probes; to be tested below).** CASA's `gaintype='K'` takes each antenna's delay from an FFT
of its baseline to the reference antenna. CASA's gaincal documentation: K "solves for simple antenna-based delays
via FFTs of the spectra on baselines to the reference antenna (This is not global fringe-fitting.)". E1 and
calchain-floor saw the same thing ([STATE.md](STATE.md): "no baseline left to refant m000"; "the FFT start (refant
baselines only)"). An antenna whose baseline to the refant is wholly flagged therefore gets no solution. `refantmode
flex` changes refant only when the refant itself is absent. That is not the case here: m022 is present, it simply
shares no unflagged cell with those 19 antennas. The flags come from the oracle's set-up: `e2n_casa3b.py prep` gave
**every** CASA solve rang's flags after calibrate. Those include `extendflags`, which rang's own K, G, B and Gsec
never saw: rang solved them at steps 0 to 3, before step 6. Neither `minsnr` nor `minblperant` is involved (CASA's
solvestats count all 62 antennas above both, and CASA's documentation says those thresholds are "not explicitly
applied for delay solutions"). Nor is the time or frequency range: one interval, the whole band, all 74 dumps.

### 1.2 Job 1: the CASA K fix (frozen now)

**The change, and only this one.** Each CASA solve runs on the flag state in which rang solved the same term, in
CARACal's order:
- setjy ×2, K, G, B and Gsec run on `rang_calibrate_20261117T022650Z`, rang's FLAG after the flag stage.
- Gapp/F, fluxscale, Gpol, KCROSS, Xf, Df and the Df clip run on `rang_apply_20261117T034709Z`, rang's FLAG after
  calibrate. That is E2-N's `casa3b-n-prep` state, and its SHA-256 `58120750…1705` is checked.
- CASA applycal runs on the same `rang_apply_…` flags, as E2-N's did.

Every CASA call is `e2n_casa3b.casa_calls` unchanged (refant m022, m023, m024 with `refantmode flex`, `minsnr` 3,
`minblperant` 4, `solint`, `combine`, `uvrange`, models). The refant, `minsnr` and `minblperant` are **not** changed.
A refant chosen so that the flags vanish would be tuned to this MS, and the thresholds are not what removes the
antennas. Script: [fu_casa3b.py](results/e2n-followup/scripts/fu_casa3b.py) (`prep-a`, `run-a`, `prep-b`, `run-b`).

Caveat, stated now: rang solved Gsec (field 2) before its `Asec` step flagged J1744−5144's corrected data. The
first state gives CASA's Gsec the same flags. F is solved after `Asec` in both arms.

**Prediction (written before the run).** CASA's K on the first state flags **0** of 62 antennas: no baseline to m022
is wholly flagged there. If it flags any antenna, the hypothesis is wrong for that antenna and is reported so.

**Mechanism probe (labelled, not the fix).** One extra CASA K call alone (`fu_casa3b.py k-only`) on the
`rang_apply_…` flags with refant `m058`. m058 is one of the 13 antennas with no wholly flagged baseline in that
version, the probe's own list. Prediction: 0 flagged. It tests the refant-baseline mechanism and is never used
downstream.

**Rerun and scoring.** On the follow-up's MS copy, after job 2 has restored it: `prep-a`, `run-a`, `prep-b`, `run-b`.
Then E2-N's own scripts, unchanged, from `score3b` to `final-restore`: score3b, corr-prep, applycal, rows-snap-casa,
rows-score (against E2-N's `rows-rang.npy`, copied), target-unit-on, leakage-casa, target-wsclean, target-unit-off,
target-score and final-restore. Script [fu_chain.sh](results/e2n-followup/scripts/fu_chain.sh), the same bookings as
E2-N's chain.

Reported for each K-downstream row (3b K, KCROSS, Xf, Df, Gpol and both composites; J1744−5144; 3C 286 parity;
J0408−6545 leakage, CASA arm; the target's compact sources and noise): E2-N's value, then the follow-up's, with the
frozen tolerance beside them. Each is read "seen, post hoc", never as E2-N's outcome.
- **3c does not move.** It compares rang's image with WSClean on rang's own CORRECTED data, so no CASA table enters.
  It is not rerun.
- **The self-calibration rows do not move** either (rang against QuartiCal on rang's data). They are not rerun.

**Night window.** E3-A's exclusive timing runs need the host from 22:00 to 06:00 SAST. During that window only small
shared steps run (at most 4 slots), and nothing here takes the lock exclusively. If `target-wsclean` (8 slots, about
3 h) cannot finish before 22:00, it waits until 06:00. The status file says so.

### 1.3 Job 2: Tricolour placement of 3a's 73 cells (frozen now)

E2-N's 3a container call, unchanged: `rang-tricolour:0.2.1-e1`, `tricolour -c mk_rfi_flagging_calibrator_fields_firstpass.yaml
-fs polarisation -dc DATA -dpm`, the whole MS, 16 threads. Its input is the follow-up's MS copy in its restored state:
FLAG equal to 9.1's hash, checked when the copy was made.

The comparison is E2-N's: Tricolour's FLAG against rang's `rang_calibrate_…` (after the flag stage); a cell is a row
and channel, and it differs if any correlation differs. This time **each differing cell is written out before the
restore**: row, time, scan, field, baseline, channel, frequency, both flag vectors, |DATA|, its index within the
scan, and a 7 × 7 time-by-channel window of both flag sets on its baseline. Script:
[fu_tricolour.py](results/e2n-followup/scripts/fu_tricolour.py) (`run`, `dump`, `restore`). The restore is
`e2_post.restore` to `rang_original`, checked against 9.1's hash.

The first check is that the rerun reproduces 73 cells (42 rang only, 31 Tricolour only, 68 in scan 7). If the count
differs, Tricolour is not deterministic here, and that is reported first.

Causes are assigned per cell, each labelled measured or inferred:
- **chunk edge:** whether the cell lies on a boundary of rang's flag-stage chunks (`flag/summary.json` chunking per
  group);
- **scan edge:** the first or last dump of a scan;
- **threshold or edge of a flagged region:** 3 × 3 neighbours flagged by both arms, the SumThreshold/dilation
  frontier that E1's 530 cells (float64 against complex64) suggest;
- **other.**

A cause is "established" only if it is shown for that cell. Otherwise it is an inference.

### 1.4 Checks and records

- After the first write step, and at the end, the original `e2n.ms` keeps 9.1's FLAG and FLAG_ROW hashes and its
  `table.f*` modification times.
- Timings go in [tool-timings.md](tool-timings.md) (host nash), including those of the two probes and the copy.
- Compact archive: [results/e2n-followup/](results/e2n-followup/). It holds the JSON records, the K tables' per-antenna
  readings, the 3a cell list and windows, and the chain logs. No FITS files and no MS.
- Status: `outputs/status/e2n-followup.md` in the nash worktree.

## 2. Results

(Filled in after the runs.)
