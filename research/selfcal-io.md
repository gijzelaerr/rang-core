# selfcal-io: the input-column copy and the repeated averaged reads (#49, #50)

Status, 2026-11-28: **identity met** on the pilot (section 4); exclusive timing **not run** (4.2). The note was
committed (1f704c4f) before the code (2cfac23d). Source:
[dl0-profile.md](dl0-profile.md) section 2.2. Branch `selfcal-io`, host glacier.

No scientific claim is made. Both changes are I/O: they must leave every number the self-calibration
stage writes unchanged, bit for bit, and they may only remove reads.

## 1. What changes

**#49, the copy.** After an apply in the same run directory the stage copies `apply.column`
(CORRECTED_DATA) into `selfcal.input_column` (CORRECTED_1GC) in a separate pass over every row
(`core_pipeline._copy_column`), before round 1. On E2-N this took about 5,530 s of the 49,613 s stage
(11 %), read-bound in `Table.getcol`; on E2-A 341 s (1.4 %). The source stays intact until round 1's
apply overwrites it (the default output column is the source). The change:

- round 1 of the first field images and solves on the source column itself (same values);
- round 1's apply reads the source once per chunk, writes CORRECTED_1GC from that chunk (every row,
  chunks without rows of the field included) and then the corrected output; when the output column is
  the source it no longer reads the output column a second time;
- the separate copy pass is gone. It stays (unchanged) only when no round runs, or when the model
  column is the source column;
- interruption: before each chunk's output is written, the copied rows are recorded in
  `selfcal-input.json` (`copied_rows`); a rerun of the same apply finishes the copy from there with
  the present chunked copy (rows past the mark are untouched in the source). The final marker is the
  present one (`column`, `copied_from`, `apply_finished`);
- the summary's round-1 image and solve name the column they read (the source), so `image.column`
  and the gemclean argv of round 1 differ from the present path; the images do not.

**#50, the averaged reads.** With `selfcal.average_time` an Sp or Sa solve reads every source row of
the field and averages it (`cal_chunks.load_averaged`). Counted on the present path:

- a solve of more than one chunk reads and averages every chunk **twice** (`cal_chunks.replayed`:
  the counted pass, then the solve pass); E2-N's 8 GiB plan holds about two of its nine intervals per
  chunk, so its Sp and Sa each read the input column twice;
- round 2 averages the same input column again, although only the model has changed.

So the present path reads the input column 2R times in R rounds of more than one chunk, R times with
one chunk. The change (`cal_chunks.AverageCache`, scratch files in the stage directory, deleted at the
end of the stage):

- the first pass of a solve writes each averaged chunk (data, model, weights, flags, row weights) to
  scratch and the second pass reads it back: one read of the rows per solve;
- the averaged input data of each chunk are kept for later rounds, with a digest of each read
  block's FLAG (and weight column, if any). A later round with the same averaging layout (rows,
  intervals, baselines, skipped rows, chunk, block size) reads only FLAG, the weights and the model;
  where a block's digest differs it falls back to the full read for that chunk. The weight sums are
  recomputed and must equal the kept ones bit for bit, or the chunk is read whole.
- So the input column is read **once per stage** for Sp and Sa at the same solint, and each round
  reads its model once. Counted (`reads` per column in the solve's summary) and asserted in tests.

Memory: one chunk is held at a time, as now; the scratch is at most the averaged arrays of one solve
plus the averaged data (E2-N about 6 GB on disk, the pilot well under 1 GB).

## 2. Oracle and data

- **Oracle:** the present path, `origin/main` at `24572b76`, its `python/rang` run with the same
  extension build as the branch (the change is Python only).
- **Data:** the four-correlation E2 pilot (`selfcal_grid.py base` from glacier's
  `D:/rang/outputs/20261103-gemclean-heldout/real/cal2.ms`, 823,500 rows × 256 channels, one 1 h scan;
  held-out channels flagged as `prepare` does), with CORRECTED_DATA added as a copy of DATA and this
  run directory's apply marked done, so that the copy runs. Each arm gets its own copy under
  `D:/rang/outputs/20261128-selfcal-io`.
- **Configuration:** E2's selfcal: Sp then Sa at `solint: 120`, `average_time: true`, uniform weights,
  `input_column: CORRECTED_1GC`, output CORRECTED_DATA; the pilot's 4096² image settings (p1.yaml).
  Two arms: **one chunk** (8 GiB) and **several chunks** (`data.chunk_rows` small enough for two or
  more chunks per solve, so that the replay's second pass runs).

## 3. Measures and decision rule (frozen)

Identity (every item, both arms, branch against oracle):

1. both gain stores (`gains.qc`) byte-identical, and the solutions (gains, flags, iterations,
   converged fraction) equal;
2. CORRECTED_DATA, CORRECTED_1GC, MODEL_DATA and FLAG of the MS equal bit for bit after the stage;
3. every FITS file of every round and the final image byte-identical (sha256 in the summaries);
4. `selfcal-input.json` equal.

Counts (branch): the solve summaries' `reads` show the input column read once in the stage (round 2
zero rows) and each model once per round, in both arms; the stage reads no separate copy pass.

Decision: **met** when 1-4 hold in both arms and the counts are as stated; **failed** otherwise, and
the branch is not offered for merge. Wall time is recorded (stage, copy, solves, applies; main and
branch, exclusive, one run each, from 21:00 on glacier) but carries no threshold: the pilot is small
(256 channels, images dominate) and E2-N is on nash, so the issue's 2 % of E2-N's selfcal is **not
measured here**; it is argued from the structure (the copy pass is removed, its write moves into
round 1's apply) and from the pilot's numbers.

Also checked by tests: a fused copy interrupted mid-apply and resumed gives the present path's
CORRECTED_1GC; the averaged solve with a cache equals the solve without one, one chunk and several.

## 4. Measured result

### 4.1 Identity (2026-11-28, glacier, shared heavy lock 8 slots 24 GB, `RAYON_NUM_THREADS=8`)

Run root `D:/rang/outputs/20261128-selfcal-io` (pilot base `grid/base/pilot.ms`, 823,500 rows x 256
channels x 4 correlations, 61 antennas, 1,830 baselines; built in 38.5 s). Arms M1, B1 (one chunk per
solve, 12 GiB) and MN, BN (`data.chunk_rows: 1830`, one averaged interval per chunk, four chunks per
solve, so the replay runs); M = main `24572b76` (its `python/rang` in `oracle-src` with the branch's
`_core.pyd`, checked in each `run.json`), B = branch `2cfac23d`. Driver
[results/selfcal-io/scripts/pilot.py](results/selfcal-io/scripts/pilot.py); archive
[results/selfcal-io/identity](results/selfcal-io/identity) (both `compare-*.json`, and per arm the
config, the summary, the state, the marker and `run.json`).

| Item (frozen rule) | M1 vs B1 | MN vs BN |
| --- | --- | --- |
| 1. both gain stores (41 files each) byte-identical; iterations, converged and flagged fractions equal | yes | yes |
| 2. CORRECTED_DATA, CORRECTED_1GC, MODEL_DATA, FLAG (and FLAG_ROW, DATA) equal, sha256 over all rows | yes | yes |
| 3. every FITS of round 1, round 2 and the final image byte-identical (5 per image) | yes | yes |
| 4. `selfcal-input.json` equal | yes | yes |

Solves: Sp 8 iterations (converged 1.0), Sa 39 (0.992), 4 intervals, 823,500 rows, flagged fraction
0.016 in every arm. Counts (branch, `reads` in the solve summaries): round 1 reads CORRECTED_DATA
(the source), FLAG and MODEL_DATA 823,500 rows each, once, also with four chunks; round 2 reads
CORRECTED_1GC **0 rows**, FLAG and MODEL_DATA 823,500 each. The present path reads the input column
once per solve with one chunk and twice with four (counted pass and solve pass), so 2 and 4 reads of
the input in the stage against the branch's 1. The summaries' `input.copy` is `fused`; round 1's
`image.column` and solve `input_column` name CORRECTED_DATA, as section 1 states. **Identity: met.**

Clarification (dated 2026-11-28, read after the first comparison): the driver first compared each
image's whole file record, which includes `image-report.json`; that report names the column read, the
MS path and the timings, so it differs by design (section 1). The comparison was narrowed to the FITS
files, which is the frozen item 3; nothing else changed.

Shared-host walls (not timing; the host ran another task): stage M1 715 s, B1 769 s, MN 869 s, BN
655 s; solves M1 62 + 81 s, B1 95 + 61 s, MN 134 + 165 s, BN 87 + 46 s; the remainder outside images,
predicts, solves and applies (main: the copy and the stores) M1 29.8 s, MN 49.3 s, branch 1.0-1.1 s.

### 4.2 Timing

Not run. The exclusive runs (TMN, TBN, TM1, TB1 in that order, each prepared just before its run so
that the page cache is in the same state for every arm) are scripted in `timing.sh` in the run root,
which waits for 21:00. A coordinator message lifted the 21:00 rule; starting the runs early was
refused by the session's permission check, so they were left for the coordinator or a later session.
Only the shared walls of 4.1 exist. They show the structure, not a gain: main's remainder (the copy
and the stores) of 30-49 s falls to 1 s; main's four-chunk solves (134, 165 s) take about twice its
one-chunk solves (62, 81 s) and the branch's four-chunk solves (87, 46 s) do not; round 1's apply
now carries the copy's write (B1 60 s against M1 29 s, BN 72 s against MN 37 s, on a shared host).

**E2-N's 2 % is not measured here** (E2-N is on nash). By the structure: the separate copy pass (a
read and a write of every row, about 5,530 s on E2-N under idle I/O) is gone; its read is replaced by
round 1's apply reading the source once (and no longer reading the output column a second time), and
its write moves into that apply. The write's share on E2-N was not measured (py-spy put the copy's
time in `getcol`).
