# W3: chunking by time and row for whole-array data

Task W3 of [finish-plan.md](finish-plan.md): the `rang-core` stages `flag`,
`calibrate` and `apply` must run on a whole-array MeerKAT Measurement Set (64
antennas, hours, 4096 channels; [meerkat-scope.md](meerkat-scope.md),
[a0-acceptance.md](a0-acceptance.md)) within a stated memory limit, and give the
same result as the unchunked run. `image` is gemclean's own reading (G2,
[g2-memory.md](g2-memory.md)) and is not changed here. Branch `fp-w3-chunking`
from main `5ec40e3`. Interface and resource work: no novelty is claimed.

**Status: proposed.** Sections 0 to 4 are written and committed before any
comparison is run.

## 0. What the code does at `5ec40e3`

- `rang-core flag` and `calibrate` read whole columns (`core_pipeline._read_columns`:
  DATA, FLAG, the weights and the model, for every row) and keep them for the
  whole stage. `flag` builds the new FLAG for the whole MS in memory and writes
  it in row chunks. W2 left this to W3 ([w2-commands.md](w2-commands.md), section 5).
- `rang-core apply` (`applycal.apply_complex`, C4b) and the models of
  `calibrate` (`calmodels.set_model`, C3a) already go through W1's
  `WriteBack` row chunks (`data.chunk_rows`, default about 64 MiB of DATA
  cells); only their row metadata (FIELD_ID, SCAN_NUMBER, DATA_DESC_ID, TIME)
  is read whole.
- `cal_gain.gaincal` and `cal_delay.gaincal` (C2a, C2b) read whole columns and
  index them; they are not yet called by the commands.
- The Tricolour port (`core_flag.flag_rows`) takes one field and scan group: a
  window (baseline, time, channel) whose time axis is the group's unique
  times. Every step of the port works baseline by baseline
  (`core/src/sumthreshold.rs`: `sum_threshold_flagger`, `uvcontsub_flagger`,
  `static_mask`, `flag_autos` and the element-wise steps).
- The `complex` solve (`core/src/solve.rs`, QuartiCal 0.2.7's loop): every
  solution interval (time bin × frequency bin, `nant` gains) evolves on its
  own, but the stop test is global over the partition (field, scan): the
  loop stops at the first iteration where converged gains / (gains − flagged
  gains) ≥ `stop_fraction`, summed over every interval (`decide`). So two
  halves of a scan solved separately do not, in general, stop where the whole
  scan stops.

On a whole-array MS at 4096 channels a row of DATA is 128 KiB, a dump of 2016
baselines 264 MB, an hour at 8 s about 120 GB: the `5ec40e3` stages cannot run.

## 1. Design (proposed)

### 1.1 The memory limit

- New key **`data.memory_limit_gb`** (float, GiB, default **8**): the peak
  resident memory a stage may use. A new module `rang.core_chunks` turns it
  into chunk sizes:
  - budget for chunk arrays `B = L − base − m · nrows`, with `base` the
    resident size of the Python process with the extension and the reader
    loaded and `m` the bytes held per MS row for the whole stage (the row
    metadata: TIME, FIELD_ID, SCAN_NUMBER, DATA_DESC_ID, ANTENNA1, ANTENNA2,
    row-to-bin maps);
  - per stage, bytes per visibility cell `c_stage` (DATA, FLAG, weights,
    model and the copies the kernels make), so a chunk holds at most
    `B / (c_stage · nchan · ncorr)` rows.
  - `base`, `m` and `c_stage` are fitted from a probe run (peak RSS against
    chunk size, section 5.1) before any comparison, and written into the code
    with a margin.
- **`data.chunk_rows`** (existing) stays: when set it caps the rows of every
  chunk (`min(chunk_rows, rows from the limit)`), and for `calibrate` a chunk
  never holds less than one solution interval. It exists for tests and for
  forcing chunk boundaries.
- Neither key enters a stage's configuration hash (`core_config.stage_hash`),
  because results do not depend on them (the claim of this task). Changing the
  limit therefore does not make a finished stage "changed".
- If the limit is below `base + m · nrows`, or a solve's smallest unit (one
  solution interval) does not fit `B`, the stage is **refused before anything
  is written**, naming the GiB needed.

### 1.2 flag

- Per (FIELD_ID, DATA_DESC_ID, SCAN_NUMBER) group as now. A group that fits
  `B` is one chunk (the `5ec40e3` call). Otherwise it is split into blocks of
  consecutive baselines in Tricolour's baseline order (`unique_baselines`),
  every block flagged on **the group's full time grid** (`flag_rows` gains a
  `time_grid` argument; without it a block missing a dump would shift the
  window and change `windows_time ≤ ntime`). The Rust kernel takes the time
  index and `ntime` as given, so no Rust change is needed.
- Reads and writes go through the `WriteBack` session in runs of consecutive
  rows. FLAG is written for the selected rows only; other rows keep their
  FLAG (the `5ec40e3` code rewrote them unchanged). The summary's
  `flag_sha256` is computed by re-reading FLAG in row order after the write.
- `freq_chunks` stays what it is, a Tricolour parameter.

### 1.3 calibrate

- Per partition (field, scan) as now, rows sorted stably by TIME, with the
  partition's own bins (`solution_grid`). A partition that fits `B` is solved
  by one `core.solve_complex` call, unchanged.
- Otherwise it is cut into chunks of whole solution intervals: consecutive
  time bins, and when one time bin's rows do not fit, consecutive frequency
  bins within it. The global stop test is replayed exactly:
  - **pass 1**: each chunk is solved with the stop test disabled
    (`stop_fraction` above 1, `max_iterations` unchanged) and the solver's
    trace on, which records per iteration the counts of converged and
    flagged gains. The counts are summed over chunks and the rule of
    `solve.rs::decide` is applied to the sums: the stop iteration `j` and the
    converged fraction are those of the unchunked loop;
  - **pass 2**: each chunk is solved again with `max_iterations = j + 1` and the
    stop test disabled, without the trace; since intervals evolve
    independently, its gains are the unchunked gains of its intervals. The
    gains are put back into the partition's arrays and written as before.
  - Allowed only with the default solver options (`RANG_SOLVE_OPTIONS`
    unset, stop test `gain`); otherwise a partition that does not fit is
    refused. A chunk whose pass-1 solve fails (a solver error) fails the
    stage, as the unchunked solve fails on an error before its stop; the case
    where the unchunked loop would have stopped before that error is not
    replayed (it fails here instead) and is stated as a limit.
  - Pass 1 costs up to `max_iterations` iterations per chunk and each chunk is
    read twice; that is the price of byte-identity and is reported, not
    tuned.
- MODEL_DATA from `calibrate.model` goes through `calmodels.set_model` with
  the row chunk of the limit.

### 1.4 apply

- `applycal.apply_complex` as now, with its row chunk from the limit (or
  `data.chunk_rows`). Its row metadata stays whole (counted in `m`).

### 1.5 Not in W3

- `image` (gemclean, G2). `cal_gain` and `cal_delay`: their whole-column read
  becomes a read of the selected rows only (bit-identical); they are not
  time-chunked, because the CASA reference-antenna pass
  (`cal_gain_apply_refant`) runs over all intervals at once, and they are not
  in the commands yet (C2c, C2d wire them).
- Receipts hash a modified MS in full by streaming it (1 MiB blocks); W3
  records the time on the large set but does not change it.

## 2. Data and cases (frozen)

| Case | MS | Size | Use |
| --- | --- | --- | --- |
| S | copy of A1 small, `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms` | 12,480 rows × 64 ch, 16 antennas, 4 fields, 23 scans, 41 MB | forced boundaries |
| O | copy of O-CASA's slice, `~/Github/rang/outputs/o-casa-20261030-01/work.ms` | 192 rows × 2048 ch, 4 antennas, one field in use | forced boundaries, real data |
| W | new whole-array set `w3` under `/mnt/d/rang/outputs/w3/`: A1's generator (`rang.simtruth`, design `w3` = 64 antennas, 4096 channels 856-1712 MHz, full polarisation, K, B, G, leakage, RFI, noise) with A1's schedule and seeds of its own, scans 1, 3, 4, 5 and 23 only (fcal, gcal, target, gcal, fcal) at 6, 2, 4, 2 and 6 dumps | 20 dumps × 2016 baselines = 40,320 rows × 4096 ch; DATA 5.3 GB, about 8.6 GB on disk | equality and memory at 4096 channels |
| L | A1 full, `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/full/a1-full.ms`, **read only** | 2,842,560 rows × 256 ch, 64 antennas, 3.5 h, 35.8 GB | memory of `calibrate` on a large MS (no MS write) |

The configuration of S, O and W (`fields.fcal` the 1934−638 field; `target` A1's
target on S and W):

- `flag`: CARACal's `mk_rfi_flagging_calibrator_fields_firstpass.yaml` at
  `8f7bb363` (as W2), on every field.
- `calibrate`: `model: {source: setjy}` on the primary section's fields;
  primary terms `{type: complex, solint: int, freqint: 16}` and
  `{type: complex, solint: 2, freqint: inf}`; on S and W also a secondary term
  `{type: complex, solint: inf, freqint: 1}` on the gcal field (O has no
  second field).
- `apply`: the default targets (each term on the fields it was solved on) into
  CORRECTED_DATA.

On L: `calibrate` only, `model: {source: unity}` (the solver's 1 Jy point; no
MODEL_DATA, so nothing is written into the MS), primary term `{type:
complex, solint: int, freqint: 16}` on the fcal field, run directory under
`/mnt/d/rang/outputs/w3/`.

Arms, each on a fresh copy of the MS (L: on the frozen MS, read only):

- **U, unchunked (the oracle):** main `5ec40e3`'s `rang-core flag`,
  `calibrate`, `apply` (a detached checkout, sharing this branch's extension
  build, since `git diff 5ec40e3 -- core/` is empty), with `data.chunk_rows`
  ≥ the MS's rows, so apply and the models are one chunk too. Not run on L
  (DATA 22 GiB plus weights 11 GiB do not fit the host's 30 GiB).
- **D, default:** this branch with `data.memory_limit_gb` at its default.
- **T, tiny chunks:** this branch with `data.chunk_rows: 7` (S, O) or `512`
  (W): every flag block a single baseline (S, O), every solve chunk one
  solution interval where an interval has more than 7 rows, row chunks
  unaligned with tiles, scans and dumps.
- **M, a low limit (W and L):** this branch with `data.memory_limit_gb: 2`.

## 3. Criteria (frozen before the first comparison)

Results must be bit-identical; no tolerance is allowed, because chunking
changes no arithmetic (section 1). A difference is a failure, reported as
measured.

1. **FLAG.** After `flag`, and again after `apply`: FLAG equal in every cell
   between U and each of D, T (and M on W); FLAG_ROW and every column other
   than FLAG (and, after apply, CORRECTED_DATA) unchanged from the pristine
   copy (SHA-256 of each column, read with casacure); the flag versions
   (`rang_original` and the stage versions) equal cell by cell.
2. **MODEL_DATA** bit-identical between U and each other arm.
3. **Gain stores** (`<run>/calibrate/*.qc`): every file byte-identical between
   U and each other arm; per partition `iterations` and
   `converged_fraction` in `summary.json` equal.
4. **CORRECTED_DATA** bit-identical between U and each other arm.
5. **summary.json** of each stage equal between arms after removing times,
   paths, flag-version names and the new chunking records.
6. **L consistency.** The gain stores of D and M on L byte-identical (no U
   there).
7. **Memory.** Peak RSS of every D and M command (`/usr/bin/time -v`,
   maximum resident set; the rang reader does not memory-map tables, so RSS is
   the process's own allocations) at or below its `data.memory_limit_gb`, on
   W and L. Reported, not gated: U's peak, and D and M peaks set against MS
   size (W 8.6 GB, L 35.8 GB). No speed is claimed (shared host).
8. **Refusal.** On W, `calibrate` with `{type: complex, solint: inf,
   freqint: inf}` and `data.memory_limit_gb: 2` is refused (exit 2) before
   anything is written, naming the GiB one interval needs: MS columns,
   flag-version list and run directory unchanged.
9. **Unit tests** (pytest, run by check-all): the traced and untraced solve
   give the same gains; a replayed chunked solve equals the one-call solve,
   bit for bit, on synthetic partitions that stop early, run to
   `max_iterations`, and have flagged intervals; flag blocks of one baseline
   with a dump missing for some baselines equal the one-call flags; the
   refusal of criterion 8 on a small MS.

## 4. What is not checked (stated before the run)

- Many hours at 4096 channels: about 120 GB per hour does not fit the 40 GB of
  disk this task may use. Hours are covered by L at 256 channels (read only,
  calibrate only) and 4096 channels by W at 20 dumps.
- `flag` and `apply` on L (they write, and a copy of L does not fit).
- Non-default solver options (`RANG_SOLVE_OPTIONS`) in a chunked partition:
  refused.
- Windows and macOS.
- Speed.
