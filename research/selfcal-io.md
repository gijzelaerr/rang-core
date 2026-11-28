# selfcal-io: the input-column copy and the repeated averaged reads (#49, #50)

Status, 2026-11-28: **proposed** (this note is committed before the code). Source:
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

(not yet run)
