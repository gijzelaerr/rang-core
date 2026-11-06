# W3: chunking by time and row for whole-array data

Task W3 of [finish-plan.md](finish-plan.md): the `rang-core` stages `flag`,
`calibrate` and `apply` must run on a whole-array MeerKAT Measurement Set (64
antennas, hours, 4096 channels; [meerkat-scope.md](meerkat-scope.md),
[a0-acceptance.md](a0-acceptance.md)) within a stated memory limit, and give the
same result as the unchunked run. `image` is gemclean's own reading (G2,
[g2-memory.md](g2-memory.md)) and is not changed here. Branch `fp-w3-chunking`
from main `5ec40e3`. Interface and resource work: no novelty is claimed.

**Status: implemented and measured; every criterion passes as frozen**
(code `56d64d4`, harness `e5f0862`; frozen run
`/mnt/d/rang/outputs/w3/run-01`, archive
[results/w3-chunking.json](results/w3-chunking.json)). Sections 0 to 4 were
committed (`8ce3c8f`) before any comparison; amendments 1 and 2 (`d0ab11f`,
`e5f0862`) changed the configuration and one arm's chunk cap after a probe and
before any comparison (section 2 and 5.1). On A1 small, O-CASA's slice and a
whole-array set at 4096 channels, FLAG, the flag versions, MODEL_DATA,
CORRECTED_DATA, every gain-store file and every stage summary are
bit-identical between main `5ec40e3` unchunked and this branch at the default
limit, at tiny chunks and at 2 GiB. At the default limit of 8 GiB the stages
peak at 3.0-5.0 GiB on the whole-array set (main: 8.7-17.6 GiB), at 2 GiB at
0.77-1.17 GiB, and calibrate on A1 full (35.8 GB) at 1.9 and 0.46 GiB. No
speed claim (shared host).

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

**Amendment 1** (2026-11-06, after the probe of section 5.1 and before any
comparison): `calibrate` with a setjy model and a secondary term is refused by
the configuration (models are written on the primary fields only; secondary
models are C2d's `fluxscale`), so the secondary term is replaced by a third
primary term `{type: complex, name: Gchan, solint: inf, freqint: 1}` on the
fcal field: one time bin per scan with a bin per channel, which on W does not
fit one chunk at either limit and so exercises the frequency-bin chunks. The
second primary term becomes `{solint: 2, freqint: 512}`: with `freqint: inf`
one of its intervals on W (2 dumps × 2016 baselines × 4096 channels) needs
4.6 GiB and the M arm (2 GiB) is refused by `config check`, as criterion 8
intends (on S and O, 512 channels or more is one bin, as `inf`). The primary
terms are named Gint, G2 and Gchan.

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

## 5. Runs

### 5.1 Probe (not a comparison)

`/mnt/d/rang/outputs/w3/probe-02`: `tools/oracles/w3/run.sh` case W, arm M
(2 GiB) with amendment 1's configuration, code `39fbc2e`, under the heavy
lock. No U arm was read. (`probe-01`, with the configuration before amendment
1, was refused at calibrate and then lost its log in a host reboot; it is
discarded.) The process before any visibility is read is about 40 MB; the
code reserves `BASE_BYTES` 640 MiB and `ROW_BYTES` 160 per row, so on W
(40,320 rows) 1.37 GiB of the 2 GiB is left for chunks.

| Stage | Chunks at 2 GiB | Peak RSS | Wall | Bytes per cell, measured (peak − 40 MB over the chunk's cells) | Factor in the code |
| --- | --- | --- | --- | ---: | ---: |
| flag | 2,803 rows; 5, 5, 2, 2, 3 baseline blocks for the 5 scans | 0.77 GiB | 4 min 28 s | about 18 | 32 |
| calibrate | 1,401 rows' worth of cells; 12 chunks for Gint and G2, 9 frequency-bin chunks for Gchan, per fcal scan; two passes | 0.95 GiB | 21 min 22 s | about 42 | 64 |
| apply | 1,869 rows | 1.49 GiB | 5 min 21 s | about 51 | 48, raised to **64** |

The apply factor was below what apply holds (DATA, FLAG, the output column,
the new flags and the kernel's outputs), so it was raised to 64 before any
comparison; the others keep their margin. Peaks are `/usr/bin/time -v`
maximum resident set, in GiB (2³⁰ bytes, the unit of the limit) here and
below.

**Amendment 2** (before any comparison): arm T on W uses `data.chunk_rows:
4096`, not 512. At 512 rows every Gint interval (2016 rows × 16 channels)
would be a chunk of its own, cut by frequency, and each such chunk reads its
2016 whole rows again (the reader returns whole cells): about 1,500 chunks per
scan and pass, terabytes of reads. At 4096 rows T on W still differs from D
and M: flag blocks of about 680 baselines, Gint chunks of two dumps, G2 one
bin per chunk, Gchan three frequency chunks per scan, apply row chunks of
4096. Reading only a channel range per chunk would need a sliced read in the
reader (not in W3).

### 5.2 Frozen run -01

`W3_ORACLE=~/Worktrees/rang/w3-oracle-5ec40e3 bash tools/oracles/w3/all.sh
/mnt/d/rang/outputs/w3/run-01`, at `e5f0862` (code `56d64d4` plus the
harness), 4 h 4 min in all; W and L arms one at a time under the heavy lock.
The U arm ran main `5ec40e3`'s Python (a detached checkout) with this
branch's extension, as section 2 states. Verdict: `run-01/verdict.json`
(`tools/oracles/w3/compare.py verdict`), copied into the archive.

| # | Criterion | Measured | Verdict |
| --- | --- | --- | --- |
| 1 | FLAG after flag and after apply; other columns; flag versions | S, O, W: D, T (and M on W) against U, casacure SHA-256 of every column after each stage: no column differs; the four flag versions (`rang_original`, flag, calibrate, apply) equal cell by cell | pass |
| 2 | MODEL_DATA | equal in every arm (hashed after calibrate and apply) | pass |
| 3 | Gain stores; iterations and converged fraction | every file of the three stores byte-identical in every arm; per-partition iterations and converged fraction equal (in the summaries) | pass |
| 4 | CORRECTED_DATA | equal in every arm | pass |
| 5 | summary.json without times, paths, version names, chunking | equal for flag, calibrate and apply in every arm | pass |
| 6 | L: D against M | stores byte-identical; D solved each fcal scan in one call, M in 7 chunks with the replayed stop; both stopped at 25 and 27 iterations (converged fractions 1.0 and 0.996) | pass |
| 7 | Peak RSS ≤ the limit for D and M on W and L | table below; every D and M stage within | pass |
| 8 | Refusal on W (one interval of 198 M cells at 2 GiB) | exit 2: "one solution interval of field 'J1939-6342' scan 1 holds 198180864 visibility cells and needs 12.444 GiB, above data.memory_limit_gb 2; ...", for scans 1 and 23; every column hash unchanged, no flag version, no run directory | pass |
| 9 | Unit tests (`tests/test_w3_chunking.py`, 13 tests) | pass in check-all | pass |

Peak RSS (GiB), `/usr/bin/time -v`:

| Case | Arm | Limit | flag | calibrate | apply |
| --- | --- | ---: | ---: | ---: | ---: |
| W (8.0 GB MS, 40,320 rows × 4096 ch) | U, main unchunked | none | 8.72 | 17.59 | 16.41 |
| | D | 8 | 3.02 | 3.51 | 4.99 |
| | T (4096 rows) | 8 | 1.11 | 2.29 | 3.04 |
| | M | 2 | 0.77 | 0.98 | 1.17 |
| L (35.8 GB MS, 2,842,560 rows × 256 ch) | D | 8 | | 1.90 | |
| | M | 2 | | 0.46 | |
| S (41 MB) | U / D / T | 8 | 0.09 / 0.06 / 0.05 | 0.16 / 0.10 / 0.05 | 0.12 / 0.12 / 0.05 |
| O (37 MB) | U / D / T | 8 | 0.11 / 0.09 / 0.05 | 0.13 / 0.11 / 0.06 | 0.11 / 0.11 / 0.05 |

The chunks behind those peaks (from each summary's `chunking` record):

- W, D: flag one block per scan (each fits), calibrate 2, 3 and 2 chunks per
  fcal scan for Gint, G2 and Gchan, apply 7,545 rows per chunk.
- W, T: flag 3, 3, 1, 1, 2 blocks; calibrate 3 chunks per scan and term;
  apply 4,096 rows.
- W, M: flag 5, 5, 2, 2, 3 blocks; calibrate 12, 12 and 9 chunks; apply
  1,401 rows.
- S, T: 1,960 flag blocks over 23 groups (single baselines), 182 solve chunks
  over 6 partitions (up to 64 in one), apply 7 rows. O, T: 6 flag blocks, 92
  solve chunks, apply 7 rows.

Reported, not gated:

- **The stop test on W.** Every partition of W's U arm ran its 50 iterations
  (converged fractions 0.97, 0.02 and 0.97 for Gint, G2 and Gchan), so on W
  the replay reproduced "run to the maximum". The early stop is exercised by
  L (25 and 27 iterations, one call against 7 chunks, byte-identical) and by
  the unit tests (`stops early`, `runs to its maximum`, a flagged interval).
- **Peak against MS size.** At 8 GiB, calibrate peaks at 3.5 GiB on W and
  1.9 GiB on L, whose MS is 4.5 times larger: the peak follows the chunk, not
  the MS. Both stay well below the limit because each partition (one fcal scan)
  fits fewer chunks than the limit allows; the factors are conservative
  (section 5.1).
- **Costs of chunking** (one run each, shared host, not timing measurements):
  calibrate on W 5 min 31 s unchunked, 10 min 4 s at 8 GiB and 21 min 45 s
  at 2 GiB, from the two passes and the re-reads of whole rows for frequency
  chunks; flag (3.5-4.3 min) and apply (5.4-8.0 min) took about as long in
  every arm on W, the unchunked arm included. On S and
  O, `chunk_rows: 7` makes every FLAG and CORRECTED_DATA write a few rows with
  a flush (W1's `WriteBack` flushes every put): 6 to 7 minutes per stage on S.
- **Receipts.** A1 full was not modified by calibrate (the receipt lists only
  the run directory as an output), so its 35.8 GB were not content-hashed.
  The W arms' receipts hashed their modified 18.6 GB copies; that time is
  inside the stage walls above.

## 6. Limits and what was not checked

- As section 4: no 4096-channel MS of hours (disk), no flag or apply on L, no
  Windows or macOS, no speed.
- One solution interval is the smallest solve chunk. `solint: inf` with
  `freqint: inf` on a whole-array scan is refused below about 12 GiB per
  6 dumps at 4096 channels (criterion 8). Splitting an interval would change
  the solver.
- A chunked partition replays the `gain` stop test only; other
  `RANG_SOLVE_OPTIONS` stop tests are refused for partitions that do not fit
  one chunk (not exercised in a run). A solver error in pass 1 fails the stage,
  also where the one-call loop would have stopped before the error (not seen).
- Frequency chunks re-read whole rows; a channel-sliced read in the reader
  would remove that cost.
- `cal_gain` and `cal_delay` now read only the rows of their field, but are not
  chunked (section 1.5); when C2c and C2d wire G, K and B into `rang-core
  calibrate`, their memory needs the same treatment (the CASA reference-antenna
  pass runs over all intervals at once).
- The factors were fitted on W (section 5.1) and then checked on W; L at
  256 channels is the held-out set for calibrate only.
- `flag` writes the selected rows only; the `5ec40e3` stage rewrote every row
  unchanged. FLAG is equal either way (criterion 1).

## 7. Timings

Rows added to [tool-timings.md](tool-timings.md); every stage's
`/usr/bin/time -v` is in `run-01/<case>-<arm>/timing/`.

## 8. Owner decisions

- **The default limit** `data.memory_limit_gb: 8` (GiB). Chosen so a 16 GB
  machine can run every stage; E2's processing host may set more. On W the
  stages peak at 3.0-5.0 GiB under it.
- **`data.chunk_rows`** stays as a cap on every chunk (it was "rows per write
  chunk"); its default (null) now follows the limit instead of 64 MiB of DATA.
- **Neither key enters the stage hash.** A run directory written before W3
  will see every finished stage as "changed" once, because the hash no longer
  includes `data.chunk_rows`; `--force` reruns it (or the coordinator may
  accept that).
- **The two-pass replay** costs up to 2 x the reads and `max_iterations` per
  chunk in pass 1; the alternative, QuartiCal-style independent chunks (each
  with its own stop test, as QuartiCal's `time_chunk` does), would be faster
  but not equal to the one-call solve. The coordinator's provisional choice:
  keep the exact replay.

## For the coordinator

- **research/README.md**, after the W2 line (this also makes
  `test_every_note_is_in_the_research_index` pass, the only check-all failure
  at the branch head):
  `- [W3, chunking](w3-chunking.md): flag, calibrate and apply run within data.memory_limit_gb (default 8 GiB) by chunking by time and row, bit-identical to the unchunked commands on A1 small, O-CASA's slice and a whole-array 4096-channel set; the complex solve replays its global stop test over chunks of solution intervals.`
- **research/STATE.md**, log, newest first:
  `W3, 2026-11-06 (implemented and measured; [w3-chunking.md](w3-chunking.md)). rang-core flag, calibrate and apply now run within data.memory_limit_gb (default 8 GiB) and read no visibility column whole (rang.core_chunks): the flagger takes blocks of baselines of a field and scan on the group's time grid, the complex solve takes chunks of whole solution intervals (time bins, or frequency bins of one time bin) and replays the solver's global stop test in two passes, apply and the models use row chunks. Every criterion passes as frozen: on A1 small, O-CASA's slice and a new whole-array set (64 antennas, 4096 channels, 20 dumps, 8.0 GB), FLAG, flag versions, MODEL_DATA, CORRECTED_DATA, gain stores (byte-identical) and stage summaries equal main 5ec40e3 unchunked at the default limit, at tiny chunks and at 2 GiB. Peaks on the whole-array set: 3.0-5.0 GiB at 8 GiB, 0.77-1.17 GiB at 2 GiB, against 8.7-17.6 GiB unchunked; calibrate on A1 full (35.8 GB) 1.9 and 0.46 GiB, chunked and one-call gains byte-identical. A solution interval larger than the limit is refused before anything is written, naming the GiB needed. Chunked solves cost up to two passes (calibrate 10 min at 8 GiB against 5.5 unchunked on the whole-array set; not a timing measurement). No novelty claim.`
  In "Current status", add W3 to the Done list.
- **research/finish-plan.md**, row W3: `**Done 2026-11-06** ([w3-chunking.md](w3-chunking.md)): bit-identical chunked and unchunked; 8 GiB default limit, whole-array 4096-channel set at 3.0-5.0 GiB.` before the task text. Section 2, row "Reading": the missing part (whole-array chunking in a general command) is done for flag, calibrate and apply. Section 7: add W3's decisions (section 8 here).
- **Shared files changed:** `python/rang/core_pipeline.py` (flag and
  calibrate rewritten around `core_chunks`; `inspect_ms` keeps TIME;
  `preflight` calls `memory_problems`; `solve_partition` takes a reader and
  returns a sixth item, the chunking record), `python/rang/core_config.py`
  (`data.memory_limit_gb`, `RESOURCE_KEYS` out of `stage_hash`),
  `python/rang/core_flag.py` (`flag_rows(time_grid=...)`),
  `python/rang/cal_gain.py` (`_ms_columns` reads only the selected rows; the
  only edit there), `python/rang/simtruth.py` and `examples/a1_simtruth.py`
  (design `w3`, `--chunk-ints`), `docs/cli.md` (regenerated), `CHANGELOG.md`.
  A branch that calls `solve_partition` or reads `info["rows"]` must follow.
  C2c and C2d, when they wire G, K and B into `stage_calibrate`, should take
  rows through `core_chunks.read_rows` and the budget of `core_chunks.budget`.
- **On disk:** `/mnt/d/rang/outputs/w3/data/w3.ms` (8.0 GB, the whole-array
  set; regenerate with `examples/a1_simtruth.py generate w3 DIR --scans
  1,3,4,5,23 --workers 3 --chunk-ints 1 --name w3`, 1 min 56 s) and
  `/mnt/d/rang/outputs/w3/run-01` (0.8 GB: hashes, run directories with the
  gain stores, timings; the MS copies were removed after each arm) and
  `probe-02` (90 MB). All can go after merge; keep `w3.ms` if E1 or E2 want a
  whole-array test set.
