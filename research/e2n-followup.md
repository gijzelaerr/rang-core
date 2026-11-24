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

**Amendments and corrections after the plan's commit (dated, post hoc).**
- 2026-11-18 19:05, before `dump` ran: `fu_tricolour.py dump` also saves the whole time × channel plane (rang's,
  Tricolour's and the native FLAG, and DATA) of each affected scan and baseline. SumThreshold's windows are wider than
  the 7 × 7 window, and the restore drops Tricolour's FLAG.
- Section 1.1's CASA quote came from a search summary. On the gaincal page (casatasks, stable) it reads: K "solves
  for simple antenna-based delays via Fourier transforms of the spectra on baselines to (only) the reference
  antenna".
- "CASA used m022" is an inference. The K table's ANTENNA2 is −1 and `used_as_refant` is 0 for every antenna in the
  solvestats. m022 is first in the list, and the flagged set is exactly the set cut off from m022, not from m023 or
  m024.

### 2.1 Job 2: 3a's 73 cells placed

The rerun reproduces E2-N's reading exactly: **73 of 2,282,996,736 cells** (292 elements; 42 rang only, 31 Tricolour
only; no cell differs in only some correlations). Tricolour is deterministic here. The restore gave FLAG
`50c7ea35…194e` and FLAG_ROW `f2809997…c2ec9`, 9.1's hashes (`fu-3a-restore.json`, met). Records:
[3a/fu-3a-cells.json](results/e2n-followup/3a/fu-3a-cells.json) (every cell),
[3a/fu-3a-columns.json](results/e2n-followup/3a/fu-3a-columns.json) and
[3a/fu-3a-windows.npz](results/e2n-followup/3a/fu-3a-windows.npz). The whole planes (29 MB,
`fu-3a-planes.npz`, SHA-256 `e1cace97…a72c`) stay in the run root.

| Scan, field | Baseline | Cells | Where |
| --- | --- | ---: | --- |
| 7, J1744−5144 (14 dumps) | m007–m050 | 68 | 12 channels between 1,168.6 and 1,663.5 MHz; 62 cells in 6 channels where one arm flags all 14 dumps and the other does not |
| 2, J1331+3030 (74 dumps) | m017–m055 | 2 | channels 754 and 755 (1,486.3 and 1,487.1 MHz), dumps 37 and 48, Tricolour only |
| 8, ASKAPJ1745 (281) | m044–m046, m044–m047 | 1 + 1 | channel 365 at dump 120; channel 869 at dump 194; Tricolour only |
| 10, ASKAPJ1745 (282) | m053–m057 | 1 | channel 296 at dump 87; Tricolour only |

In m007–m050 on scan 7:
- Rang flags channels 835 and 882 in all 14 dumps, where Tricolour flags none.
- Tricolour flags channels 920, 922 and 923 in all 14 dumps, where rang flags 6, 10 and 5.
- On channel 855 rang flags 14 and Tricolour 5. On channel 876 rang flags 14 and Tricolour 11.
- The other 6 cells are single cells.
- The parallel-hand |DATA| of every differing cell is 3.6-4.2 Jy, the baseline's ordinary level (|XX|, |YY| about
  3.9). None is an outlier. Natively, channels 835, 855, 882 and 923 are unflagged on that baseline; 920, 922 and
  876 have 3, 9 and 11 dumps flagged.

Causes:
- **Chunk edge: ruled out for all 73 (measured).** Rang's flag stage gives each block whole baselines
  (`core_chunks.baseline_blocks`, "blocks of consecutive baselines"), so each baseline's whole scan plane goes through
  the flagger in one piece. Scan 7 (26,474 rows) is one block in any case (`flag/summary.json`). A0's chunk-edge
  clause therefore has nothing to act on.
- **Scan edge: not the cause.** Of the 73 cells, 4 are in dump 0 and 4 in dump 13 of scan 7; they belong to the
  same whole-channel columns as the interior dumps. The other 5 cells are interior.
- **Whole-channel decisions on a short scan (measured placement, cause inferred).** 62 of the 68 scan-7 cells lie in
  columns that one arm flags across the whole scan. The strategy's `sum_threshold` steps flag a whole channel once
  more than `flag_all_time_frac` 0.6 of its times are flagged, which is 9 of 14 dumps here. One more or one fewer
  flagged dump then moves all 14. On channels 835 and 882 Tricolour flags nothing at all, so the two arms already
  differed before that rule, in a step with channel-coherent effect (`uvcontsub_flagger`'s 20-term fit across
  frequency, or a SumThreshold background estimate). Which step it is was not established: the intermediate flags of
  each step were not saved.
- **The 5 single cells in scans 2, 8 and 10: threshold-level, inferred.** Each is isolated: 0 to 7 of its 3 × 3
  neighbours are flagged by both arms, and Tricolour flags each where rang does not. This is the kind of difference
  E1's 530 cells came from (float64 against complex64). That was not shown cell by cell.

**Reading:** 3a's miss is one baseline on one 14-dump scan (93 %), plus 5 isolated cells. It is not a chunking
effect. Gate 3a stays not met as frozen. Placing the 68 to a strategy step would need both flaggers' per-step flags
on m007–m050, scan 7; that is a small run (one baseline, 14 dumps) and not part of this job.

### 2.2 Job 1: CASA's K (measured 2026-11-23, scored 2026-11-24; seen, post hoc)

Rerun under the 2026-11-22 amendment, run root `~/rang-data/outputs/e2n-followup-20261122/` on nash; launcher
`fu_rerun.sh` finished 2026-11-23 12:19 SAST. It stopped once at `casa-prep-a` (2026-11-22 16:10, `psutil` missing
in a second Python, `R/chain.out`) and was resumed from its markers on 2026-11-23 05:53. Archive
[results/e2n-followup/rerun/](results/e2n-followup/rerun/) (JSON records and logs, no MS, no FITS).

**Checks (all met).** Extension equals E2-N's (`wheel-check.json`, `9c42ea72…83ed`). The copy and the original
`e2n.ms` hash equal before, mid and after (`fu-copy-hash.json`, `fu-original-hash-{before,mid,after}.json`), so
the original is untouched. Rang's flag versions (rang_original, flag, calibrate, apply) equal E2-N's surviving ones
(`fu-flagversions.json`, `all_equal: true`), so rang's side is reproduced and the CASA rows read against E2-N's
rang. prep-b's restored FLAG hash is `58120750…1705`; `g2a.json` and `final-restore.json` `met: true`.

**K (prediction of 1.2: confirmed).** CASA's K on the flag stage's flags flags **0 of 62** antennas; E2-N's CASA K,
regenerated (`k-only-e2n`, the after-calibrate flags), flags E2-N's same **19** (0, 1, 2, 3, 6, 7, 9, 11, 12, 15,
16, 18, 21, 23, 26, 29, 30, 41, 45); the m058 probe on the after-calibrate flags flags **0**, as predicted, so the
refant-baseline mechanism holds. Rang's K flags 0. |Δτ| rang against the follow-up's CASA K: median 1.24e-3 ns,
p95 4.73e-3, max 8.9e-3 (n 124 = 62 × 2); against E2-N's CASA K 1.09e-3 / 3.72e-3 (n 86). E2-N's and the
follow-up's CASA K agree to 1.8e-4 ns median where both solve (`fu-kcompare.json`).

**K-downstream rows: E2-N's value, then the follow-up's, beside the frozen tolerance** (`fu-compare.json`; every
follow-up value is seen, post hoc, and none is E2-N's outcome).

| Row | E2-N | Follow-up | Tolerance | Follow-up reads |
| --- | --- | --- | --- | --- |
| 3b K | 1.09e-3 / 3.72e-3 ns (n 86), flags differ 38 | 1.24e-3 / 4.73e-3 ns (n 124), flags differ 0 | ≤ 0.01, ≤ 0.03 ns | within |
| 3b KCROSS | 1.13e-3 ns | 1.27e-3 ns | ≤ 0.02 ns | within |
| 3b Xf | 0.249° / **2.085°** | 0.110° / 0.525° (n 840) | ≤ 0.5°, ≤ 2.0° | within |
| 3b Df | 1.47e-4 / 4.88e-4 | 2.93e-5 / 1.81e-4 | ≤ 1e-3, ≤ 5e-3 | within |
| 3b Gpol | 0.022° | 0.0026° | ≤ 0.1° | within |
| 3b fcal K G B composite | **1.85e-3 / 1.68e-2** | 1.65e-5 / 8.35e-4 (flags differ 0) | 7e-4, 3e-3 | within |
| 3b gcal K F B composite | **2.43e-3 / 1.69e-2** | 2.87e-5 / 8.31e-4 (flags differ 0) | 7e-4, 3e-3 | within |
| J1744−5144 | 6 bins; \|ΔI\| 0.095 %, \|Δp\| 0.010 pt, **\|Δχ\| 10.3°** | 7 bins; \|ΔI\| 0.0015 %, \|Δp\| 0.0016 pt, **\|Δχ\| 4.88°** | 1 %, 0.1 pt, 1° | **outside** (χ) |
| 3C 286 parity | \|Δp\| 0.088 pt, \|Δχ\| 0.31° | \|Δp\| 0.027 pt, \|Δχ\| 0.20° | 0.1 pt, 0.5° | within |
| J0408−6545 leakage, CASA arm | Q 0.143, U 0.163, V 0.086 % | Q 0.149, U 0.171, V 0.078 % | each ≤ 0.3 % | within |
| Target compact (≤ 0.7°, n 316) | median 0.9901, **scatter 13.3 %** | median 0.9961, **scatter 2.40 %** | within 1 %, ≤ 1.5 % | **outside** (scatter) |
| Target noise, dynamic range | 0.960 ×, 1.078 × | 1.014 ×, 0.981 × | ≤ 1.2 ×, ≥ 0.8 × | within |

Also reported (no E2-N row): G relative median / p95 4.9e-4 / 9.7e-4 (E2-N) to 7.8e-5 / 3.1e-4; B 1.8e-3 /
9.3e-3 to 1.2e-3 / 6.5e-3.

**Reading.** With each CASA solve on the flags rang solved it on, CASA's K keeps all 62 antennas, and every 3b row,
including Xf's p95 and both composites that E2-N missed, falls within its frozen tolerance; parity, leakage and the
target's noise stay within. Two rows stay outside: J1744−5144's χ (4.88° against 1°, now on 7 bins; E2-N 10.3°) and
the target's compact scatter (2.40 % against 1.5 %; E2-N 13.3 %). Neither is attributed here.
- **Not rerun (1.2):** 3c (no CASA table enters it; see [gate3c-rerun.md](gate3c-rerun.md) 6.2) and the
  self-calibration rows.

## Coordinator decisions (2026-11-18 evening, post hoc, after 2.1 and the K diagnosis)

- **The flag-state split is the oracle's standard:** each CASA solve runs on the flags in which rang solved that term
  (crosscal on the flag stage's flags, the polarisation solves and applycal after `extendflags`). Applying it to E2-A's
  and E2-B's 3b scripts is a later task, not done here.
- **Per-step flag dump on m007–m050, scan 7: yes,** shared and short only (section 2.3).
- **`as_is` arm: deferred** until the rerun's rows are in.

## Amendment, 2026-11-22: rerun from the start (post hoc; written before any rerun output)

- **What was lost.**
  - The follow-up's run root `e2n-followup-20261118` (201 GB) was found absent on 2026-11-19.
  - By 2026-11-22, E2-N's own `R/` was gone too: `rang-run`, `rows-rang.npy`, CASA's tables and the leakage records.
  - What is left: E2-N's `e2n.ms` with its flag versions, and the archives in `results/e2n/`. The MS's 9.1 hashes
    are checked before use.
- **Rang's side is regenerated first,** in a new run root, `~/rang-data/outputs/e2n-followup-20261122`:
  - **Binary:** E2-N's own wheel, rebuilt and bit-identical in its extension (`9c42ea72…83ed`, E2-N's receipt).
    - The PyPI rang-core 0.2.0 wheel is a different build. Its extension is `a256225c…a62f`, so the launcher
      stopped at its check.
    - E2-N's wheel was built on nash by `tools/wheel/build.py` at `99a5261` (toolchain 1.93.1, maturin 1.16.0,
      `--locked`), from `~/Worktrees/rang/e2n`.
    - A first rebuild from another path gave `9fce7fc4…`, because the source path is embedded in the extension.
      Rebuilt from E2-N's path, it gives `9c42ea72…83ed`.
  - **Steps:** E2-N's chain steps, unchanged (`e2n_nash_chain.sh`): columns-before, run, gate1, archive,
    prep-inplace, rows-snap-rang and restore.
  - **Configuration:** [e2n-rerun.yaml](results/e2n-followup/scripts/e2n-rerun.yaml) is E2-N's, but for
    `run.stages` [flag, calibrate, apply, image]. Selfcal is dropped, because its rows do not move (1.2).
  - **Checks:** the rerun's flag versions are hashed against E2-N's surviving ones
    ([fu_flagversions.py](results/e2n-followup/scripts/fu_flagversions.py)). prep-b's check of 3b's FLAG hash
    `58120750…1705` is kept.
- **E2-N's CASA K is regenerated** for [fu_kcompare.py](results/e2n-followup/scripts/fu_kcompare.py): step
  `k-only-e2n` runs K alone on the flags after calibrate, with E2-N's refant list. That is E2-N's 3b K call.
- **Job 2 (Tricolour, 2.1) is not rerun.** Its records are archived, and it reads nothing that was lost. Section
  2.3's per-step flag dump is not part of this rerun.
- **#53 (K's refant fallback, on main since 2026-11-21) is not in this run.**
  - Rang's arm is 0.2.0, and the oracle is CASA.
  - It would not change rang's K here in any case. Rang solves K on the flag stage's flags, where no baseline is
    wholly flagged (1.1: 0 of 1,891). The fallback has nothing to act on.
- **The night hold of 1.2 is kept:** target-wsclean does not start between 19:00 and 06:00 SAST. `HOLD=0` lifts
  it, on the coordinator's word only.
- **Launcher:** [fu_rerun.sh](results/e2n-followup/scripts/fu_rerun.sh). It is self-driving and leaves a
  done-marker per step in `R/done/`, so a second start resumes.
- **Scheduling change, 2026-11-22, on the coordinator's word (not a method change): `HOLD=0`.**
  - E3-A was stopped at the 0.3.0 tag and is not scheduled, so 1.2's night window has no job to protect.
  - The launcher was started with the hold on. If it reaches the hold, it is restarted from its markers with
    `HOLD=0`. While held, it is only sleeping.
- **Wheel venv,** 2026-11-22 10:27, before any rang output: E2-N's chain runs `e2_diskguard.py` with the wheel
  venv's Python, which needs `psutil`. `psutil` 7.2.2 was added to the wheel venv (rang itself is unchanged), and
  the launcher's wheel step now installs it.

## Resume and scoring (written 2026-11-22 when work paused; the rerun runs unattended)

**State at the pause.**
- [fu_rerun.sh](results/e2n-followup/scripts/fu_rerun.sh) runs on nash with `HOLD=0`, from the worktree
  `~/Worktrees/rang/e2n-followup` (branch `e2n-followup`).
- Run root: `~/rang-data/outputs/e2n-followup-20261122`.
- Markers done: copy, hash-copy, hash-original-before, wheel (extension `9c42ea72…83ed`, equal to E2-N's).
- rang's `run` (stages flag to image; 16 slots, 96 GB) started at 10:28 SAST and should take about 5.5 h. Then the
  launcher goes on by itself: `rang-gate1`, `rang-prep-inplace`, `rang-rows-snap-rang`, `rang-restore`,
  `flagversions`, `fu-to-leakage` (casa-prep-a to leakage-casa, with k-only-m058 and k-only-e2n),
  `hash-original-mid`, `fu-target` (target-wsclean to final-restore) and `hash-original-after`.
- Logs: `R/rerun.log` (one line per marker; it ends with "finished" or the step that stopped),
  `R/chain-steps.log`, `R/chain.out`.

**Resume.**
- If `R/rerun.log` names a stop, read the end of `R/chain.out`, fix the cause, and start the launcher again. It
  skips every step that has a marker in `R/done/`:

  `cd ~/Worktrees/rang/e2n-followup && HOLD=0 nohup bash research/results/e2n-followup/scripts/fu_rerun.sh >> ~/rang-data/outputs/e2n-followup-20261122/fu-rerun.out 2>&1 &`

- A stop inside the rang segment, or inside `fu-to-leakage` or `fu-target`, reruns that whole segment: its steps
  have no marker of their own.
- The `restore` step needs E2-N's `INPUT` hashes. Its `g2a.json` must read `met: true` before Tricolour or CASA
  reads the copy.

**Checks when it has finished.**
- `R/wheel-check.json`: `equal: true`.
- `R/fu-copy-hash.json`, and `fu-original-hash-{before,mid,after}.json`: `equal: true`. The original MS is
  untouched.
- `R/fu-flagversions.json`: rang's rang_original, flag, calibrate and apply versions against E2-N's surviving
  ones. `all_equal: true` means rang's side is reproduced. A difference is recorded first, and the CASA rows are
  then read as against the rerun's rang, not E2-N's.
- `R/casa3b-n-prep.json` (prep-b): the restored FLAG hash equals `58120750…1705`. fu_casa3b stops otherwise.
- `R/g2a.json` `met: true` after `restore`, and `R/final-restore.json` at the end.

**Scoring (section 2.2, read under 1.2's prediction: CASA's K on the flag stage's flags flags 0 of 62; the m058
probe flags 0).**
1. Per-antenna K, run in the formats image (python-casacore):

   `apptainer exec -B ~/rang-data/outputs/e2n-followup-20261122/R:/r -B ~/Worktrees/rang/e2n-followup:/w ~/rang-data/oracle-images/rang-formats-oracle_20261030.sif /opt/qc/bin/python /w/research/results/e2n-followup/scripts/fu_kcompare.py /r/rang-run/calibrate/K /r/k-only-e2n/K /r/casa/tables/K /r/k-only-m058/K /w/research/results/e2n-followup/probe/k-probe.json /r/fu-kcompare.json`

   Check the table paths against `R/rang-run/calibrate/` and `R/casa/` first: `casa/tables/` is where
   `e2n_casa3b` writes.
2. The K-downstream rows beside E2-N's:

   `.venv/bin/python research/results/e2n-followup/scripts/fu_compare.py research/results/e2n/score ~/rang-data/outputs/e2n-followup-20261122/R ~/rang-data/outputs/e2n-followup-20261122/R/fu-compare.json`

3. Archive the compact records in `research/results/e2n-followup/rerun/`:
   - fu-kcompare.json, fu-compare.json, g3b.json, rows.json, row-target.json and leakage-casa.json;
   - fu-flagversions.json, wheel-check.json, the hash JSONs, chain-steps.log and rerun.log.

   No MS and no FITS.
4. Write 2.2 as frozen:
   - flagged antennas in the follow-up's K against E2-N's 19, and the m058 probe;
   - each K-downstream row: E2-N's value, then the follow-up's, beside the frozen tolerance, read "seen, post hoc";
   - 3c and the selfcal rows are not rerun (1.2).
5. Add the tool-timings rows (host nash: the copy, the wheel builds of 336 s, rang's run, the CASA steps, the
   target WSClean), plus the README index line and the STATE paragraph.
6. Quick check on nash, commit, push `e2n-followup`, and read CI.

**Clean-up after scoring.**
- Remove the detached worktree `~/Worktrees/rang/e2n` (`99a5261`, used only to rebuild E2-N's wheel) and
  `~/Build/tmp/20261122-e2n-wheel`.
- Keep the run root until the coordinator has read 2.2. It holds a 105 GB MS copy plus rang's columns.
