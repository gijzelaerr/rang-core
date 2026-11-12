# Sliced reads: channel chunks read only their channels

Finish-plan section 7 item 22 ([finish-plan.md](finish-plan.md)): W3b
([w3b-chainchunks.md](w3b-chainchunks.md) section 6) found that a channel
chunk of B, Xf or Df re-reads and re-prepares the whole interval's rows for
every chunk and both replay passes (Df four), because the pre-apply ran on
whole rows and the reader had no channel-sliced read. Its arms with one
channel per chunk took 16-32 min, and the whole-array calibrate 32 and 52 min.
E2 and E3 run whole-array data at 4096 channels, so this sits on the critical
path's wall time. Branch `sliced-read` from origin/main `bd15126`. Resource
work: no scientific novelty is claimed; the speed is measured against the same
code before the change on the same host.

**Status: measured** (sections 0 to 4 were frozen before any code was written; results in section 5).

## 0. What the code does at `bd15126`

- The Rust reader (`core/src/ms.rs`, `Table::read_column`; Python
  `rang.core_ms.Table.getcol`, `core_ms_write.Table.getcol` through the
  writer, `core_writeback.WriteBack.read`) reads whole cells of a run of
  consecutive rows. `core_chunks.read_rows(source, name, rows, chans,
  block_rows)` reads runs of rows, then cuts the channels in NumPy.
- `cal_chunks.load` reads a channel chunk in blocks of whole rows (all
  channels), runs the field's `prepare` (pre-apply of the earlier tables,
  SIGMA to weights, P's rotation for the polarisation terms, each row's
  weight sum `row_w`) on each block, and cuts the result to the chunk's
  channels.
- Tile shapes of the sets (casacure `getdminfo`): `w3.ms` DATA and
  WEIGHT_SPECTRUM `[4, 4096, 2]`, FLAG `[4, 4096, 16]` (TiledColumnStMan);
  poldx, polholdout and A1 small DATA `[4, 256, 32]`, FLAG `[4, 256, 256]`
  (A1: 64 channels, its own tiles). **Every tile of these sets spans all
  channels**, so a channel slice cannot skip bytes on disk there: what it
  saves is the decode and copy of the other channels, and, with a sliced
  prepare, the pre-apply and NumPy work on them.

## 1. Design (proposed)

1. **Reader.** `Table::read_column_slice(name, start, count, slice)` with a
   per-cell-axis range (casacore order; for visibilities axis 1 is the
   channel). TiledShapeStMan and TiledColumnStMan visit only the tiles that
   intersect the slice and copy only its pixels; other managers read the
   cells and cut them in Rust. A list of ascending rows is read in one call
   (`read_rows`) sharing one tile cache across its runs. `read_column` is the
   slice over every axis. Exposed on `MsTable.read`/`read_rows` and
   `MsWriter.read`/`read_rows`, and in Python as `getcol(..., chans=)` and
   `read_rows(..., chans=)`; columns without a channel axis (WEIGHT, SIGMA,
   scalars) are read whole.
2. **`core_chunks.read_rows`** with `chans` reads the slice through the
   reader (no read blocks of whole rows are needed then).
3. **Pre-apply on a channel window.** `cal_apply.apply(..., channels=)`:
   the frequencies stay the whole band and the data hold the window's
   channels. The kernel builds each (antenna, time) table on the whole band
   exactly as now (CASA's frequency resampling has a shortcut, `same`, taken
   only when the solution channels equal the data channels, so a subset
   given as the band would change B's and Xf's pre-applied values) and loops
   the cells of the window only.
4. **`cal_chunks.load`** reads a channel chunk's channels only and prepares
   them on the window. The rows' weight sums (`row_w`, a sum over all
   channels after the pre-apply's flags; partial sums would not be
   bit-identical) come from one pass of whole-row blocks per interval,
   memoised and reused by the interval's other chunks and the second pass.
5. Nothing else changes: chunk plans, budgets, stop-test replay, kernels.

## 2. Data and arms (frozen)

Sets and configurations are W3b's (section 2 there), read-only sources:
O (O-CASA's slice, copied once from the WSL home to
`D:\rang\outputs\sliced-read-data\o-casa-work.ms` and hashed), C (A1 small),
P (poldx), H (polholdout), W (`w3.ms`, calibrate K, G, B only). Each arm runs
on a fresh copy. Runs native on Windows (W3b ran on WSL), under
`D:\rang\outputs\sliced-read-<date>-<nn>`.

- **U**: main `bd15126` unchunked (W3b's U rule), a detached checkout with
  its own release extension. O, C, P, H.
- **D, T, M**: W3b's default limit, `chunk_rows: 7`, and its low limit rule
  (`compare.py m_limit`), on this branch. O, C, P, H, W (no T on W).
- **B-D, B-T, B-M** ("before"): the same arms on main `bd15126`, for the
  timings and, on W (which has no U), as the identity reference.

## 3. Criteria (frozen)

Tolerance: **bit-identical**. The change moves no arithmetic, so any
difference is a failure, reported as measured.

1. **Identity** on O, C, P against U for D, T, M, with W3b's comparison
   (`tools/oracles/w3b/compare.py verdict`): every calibrate run-directory
   file byte-identical, every MS column (casacure SHA-256) and flag version
   equal after calibrate and apply, summaries equal after W3b's cleaner.
2. **W identity**: branch D against B-D and branch M against B-M (tables,
   columns, flag versions, summaries), and D against M.
3. **Held-out** H: criterion 1 on H, run once after 1 and 2.
4. **Reader unit tests**: sliced and row-list reads equal `getcol(...)[:,
   chans]` of whole reads, and casacure's `getcolslice`, on tables whose
   tiles split the channel axis without dividing it, for TiledShapeStMan and
   TiledColumnStMan, a Bool column with a slice starting off a byte, complex,
   float and int columns, big-endian and little-endian tables, StandardStMan
   arrays (the cut path), and the reader's existing casacore (task E dump) and
   casacure oracle tests unchanged. The pre-apply on a window equals the
   whole-band pre-apply cut, for K, G, B (solution channels equal to the data
   channels, and not) and Xf/Df. `cal_chunks.load` sliced equals the
   whole-row path for G, B and the polarisation terms.
5. **Memory** on W: peak working set of calibrate at or below the limit (D 8
   GiB, M its limit).

## 4. Timing (reported, frozen protocol)

Wall time and peak working set of each stage (`calibrate`, `apply`) for
B-T and T on C, P, H, B-D, D, B-M and M on W, and B-D and D on P. Each timing
run takes the heavy lock exclusively (`tools/heavy_lock.py run --`, from the
main checkout), and `heavy_lock.py status` is recorded at its start. One run
per arm: the ratio is reported as measured, not as a distribution. The
change is kept if criteria 1 to 5 pass, whatever the timing shows; a slower
arm is reported.

## 5. Results

### 5.1 Where a channel chunk's time goes (profile, run -01)

`D:\rang\outputs\sliced-read-20261111-01-profile`, `tools/oracles/sliced/profile_b.py`:
B on poldx field 0 (`combine: scan`, K and G pre-applied, unit model,
`chunk_rows: 7`, so 256 one-channel chunks, 512 loads over the two replay
passes, 50 iterations), under cProfile, one run each as a shared heavy-lock
job (4 slots; not a timing measurement).

| Cumulative s | `bd15126` | branch `63fed2e` |
| --- | ---: | ---: |
| `bandpass` (wall) | 26.3 | 10.4 |
| `cal_chunks.load` | 25.0 | 9.3 |
| reads (`core_chunks.read_rows`) | 11.8 | 7.6 |
| `prepare` (pre-apply, weights, flags) | 12.6 | 1.6 |
| of which the pre-apply | 4.2 | 1.5 |
| the solve kernel (`_kernel`) | 1.2 | 1.1 |
| rows' weight sums from whole rows | (in `prepare`) | 0.07 |

The reader's share falls least: poldx's tiles (`[4, 256, 32]`) hold every
channel, so a one-channel read still reads every tile of the field's rows
(from the page cache); what it saves is the copy and decode of the other 255
channels and the per-run calls. Most of the gain is the prepare on one
channel instead of 256.

### 5.2 Run -02 and a change of how the arms take the lock (2026-11-12)

`D:\rang\outputs\sliced-read-20261111-02`, code `f003d1d` (branch) and
`bd15126` (base); the SHAs are in `sliced-read-20261111-02.code/head.txt`.

- **Per-arm tickets.** The run started with every arm in its own heavy-lock
  ticket, as section 4 says. By 2026-11-12 08:10 these had finished:
  - the shared arms O, C and P (U, D, T, M)
  - the timing arms C-BT, C-T, P-BT, P-T, P-BD, P-D, W-BD, W-D and W-BM
- **One exclusive hold.** On the coordinator's request, the remaining arms
  then ran back to back inside one exclusive hold
  (`heavy_lock.py run -- "C:/Program Files/Git/bin/bash.exe"
  tools/oracles/sliced/batch.sh`): W-M, the first verdict, H-U, H-D, H-M,
  H-BT, H-T and the last verdict. Each separate exclusive ticket had drained
  the host's shared jobs first and left it at about 14 % CPU.
  - The per-arm W-M ticket was cancelled before it started.
  - Each arm still records `heavy_lock.py status` at its start
    (`logs/lock-status.txt`).
- **A failed first attempt.** The first attempt of the batch named a bare
  `bash`. From Python this is WSL's `bash.exe`, so every arm failed to find
  `run.py` under `/mnt/c` and exited at once, writing nothing. It was rerun
  under Git Bash by its path, as recorded in `sliced-read-20261111-02.log`.
- **Post hoc for H-U, H-D and H-M.** Section 4 left them shared; they ran
  exclusive. This changes none of their outputs, and the timed arms'
  protocol is unchanged.

### 5.3 Identity (criteria 1 to 3): pass, 19 of 19

`verdict-1-2.json` (15 checks) and `verdict.json` (19), run -02, on the
branch at `f003d1d`, before any merge of origin/main. Bit-identical in every
check:
- calibrate run-directory files
- every MS column and flag version after calibrate and apply
- summaries and exits

The checks:
- O, C, P, H: D, T and M on the branch against U (main, unchunked), 12 checks.
- W: D against B-D, M against B-M, M against D, 3 checks.
- Reported: the base's own C-BT, P-BD, P-BT and H-BT against U, 4 checks, all
  equal, as in W3b.

### 5.4 Reader unit tests (criterion 4): pass

`tests/test_sliced_read.py`, 112 tests, cover the cases section 3 lists:
- both tiled managers, both endians, StandardStMan arrays
- Bool, complex, float and int columns
- casacure `getcolslice` and casacure-written tables
- the pre-apply on a window for K, G, B (with flagged channels) and Xf/Df
- channel-chunked B, Xf and Df equal to one call
- the three oracle MSs

The reader's existing casacore and casacure oracle tests pass unchanged, 22
with none skipped.

### 5.5 Timings and memory (section 4; criterion 5 passes)

Run -02, the same code as 5.3. Native Windows on the shared host (16 threads,
63 GB):
- One run per arm, each with the heavy lock held exclusively.
- At every timed arm's start `logs/lock-status.txt` shows the arm's own
  process (or the batch's) as the exclusive owner and 0 of 16 shared slots
  in use.
- Wall time is in seconds. Peak working set is in GiB (`rang.rusage`,
  K32GetProcessMemoryInfo), against the GiB limits.

| Arm | Stage | Before (`bd15126`) | After (branch) | Ratio | Peak GiB before / after |
| --- | --- | ---: | ---: | ---: | --- |
| C T (64 ch) | calibrate | 59.5 | 55.2 | 1.08x | 0.06 / 0.06 |
| C T | apply | 34.3 | 36.0 | 0.95x | 0.05 / 0.05 |
| P T (256 ch) | calibrate | 147.5 | 68.1 | 2.17x | 0.24 / 0.24 |
| P T | apply | 56.0 | 51.2 | 1.09x | 0.16 / 0.16 |
| H T (256 ch) | calibrate | 132.4 | 63.0 | 2.10x | 0.24 / 0.24 |
| H T | apply | 51.8 | 51.4 | 1.01x | 0.16 / 0.16 |
| P D | calibrate | 5.34 | 5.41 | 0.99x | 0.27 / 0.27 |
| P D | apply | 4.00 | 4.11 | 0.97x | 0.53 / 0.53 |
| W D (4096 ch) | calibrate | 806.7 | 607.9 | 1.33x | 3.21 / 3.21 (limit 8) |
| W M | calibrate | 1238.2 | 825.0 | 1.50x | 1.64 / 1.64 (limit 4.33) |

- Peak memory is unchanged in every arm. On W both peaks are within their
  limits (criterion 5).
- The stages that do not take the changed path differ between their two
  single runs by up to 9 % (0.95x to 1.09x). These are P D, which is one
  chunk, and every apply stage, whose row blocks read whole channels in
  `cal_chain`.
  - That is the only spread measured; it is not a distribution.
  - C T calibrate (1.08x, 64 channels) is inside it: no measurable change.
- The measured gains are in calibrate with channel chunks of B, Xf and Df:
  - 2.10x and 2.17x on the 256-channel sets
  - 1.33x (D) and 1.50x (M) on the 4096-channel whole-array set

### 5.6 After merging origin/main

The branch merged origin/main twice: `045cd4c`, then `e973303`, which takes
main's `calibrate.average_time` and `average_freq` (task E2). Both merges
were clean except for appended rows in `tool-timings.md`, and neither changed
the Rust after `d0e29d1`.

Main's averaged solves don't take the sliced path:
- `cal_chunks.load_averaged` still prepares whole rows, then cuts.
- `average_freq` solves one frequency bin, so whole-channel chunks.

`tests/test_e2_average_time.py`, `test_e2_average_freq.py`,
`test_sliced_read.py` and `test_w3b_chainchunks.py` pass on the merged tree:
153 passed, 2 skipped.

Identity rerun on the merged head `e973303` (run -03, `D:angoutputssliced-read-20261112-03`, one shared hold): O and P, D, T and M against U on the same code, 6 of 6 bit-identical.

Full local check (`python -m rang.check` after `maturin develop --release`,
heavy lock shared, 8 slots) on `d0e29d1`, after the first merge: overall
FAIL, on one test. Every other gate passes: fmt, ruff, clippy, cargo tests,
1271 pytest tests and the gain-hash gate. The test is
`tests/test_core_ms_write.py::test_the_lock_keeps_a_second_process_out`:
- No "locked" OSError is raised.
- It also fails on `bd15126` with the same venv and fixture: "1 failed",
  reason not inspected there.
- It runs only because this worktree holds its fixture MS
  (`outputs/tv-caracal-wsl-20261029-01/original.ms`); without the fixture
  it skips.

Log: `D:\rang\outputs\sliced-read-20261112-check4.log`. CHECK-HEAD

## 6. Limits and open points

- One run per arm, as frozen. The ratios are single measurements on a shared
  host held exclusively.
- On these sets a sliced read saves no disk bytes, because every tile spans
  all channels (section 0).
  - A tile shape that splits channels (for example `[4, 64, n]`) would let a
    channel chunk skip tiles on disk. The reader already visits only the
    intersecting tiles.
  - Changing the tile shape that rang writes is not part of this change; it
    is a possible follow-up.
- W's chunked calibrate is still 10 to 14 min native, and it was not
  profiled. On poldx (5.1) the reads were the largest remaining share after
  the change.
- The apply stage and the time-averaged solves (`load_averaged`) still
  prepare whole channels per row block. They were not changed here.

**Status: measured.** Criteria 1 to 5 pass. The change is kept.

## 7. For the coordinator

- **Branch:** `sliced-read`. Merges of origin/main: `045cd4c`, `e973303`.
- **Interfaces:**
  - The apply ABI `ApplyChunkC` gains `nband` and `first_chan`;
    `cal_apply.apply(..., channels=)` and `rang._core.cal_apply(...,
    first_chan=0)`.
  - `MsTable.read`/`MsWriter.read` gain `slice=`; `MsTable.read_rows` and
    `MsWriter.read_rows` are new.
  - `getcol(..., chans=)` and `getcol_rows` are new in Python.
- **E2's worktrees:** main's versions of `cal_chunks`, `cal_gain`, `cal_pol`
  and `cal_delay` merged cleanly. E2's uncommitted edits in its worktrees may
  still conflict.
- **Check:** see 5.6. The lock test is a follow-up; it predates this change.
- **Kept:**
  - `D:\rang\outputs\sliced-read-20261111-01-profile`, `-02` (logs, hashes,
    verdicts, 60 MB; the arms' MS copies removed) and `-03`
  - `sliced-read-data` (37 MB: O's copy and the strategy)
  - the check logs
  - the worktree's ignored `outputs/`, holding copies of five WSL oracle
    fixtures for the reader's oracle tests
- **Removed:** the base worktree `sliced-read-base`.
- **Follow-ups:** tile shapes that split channels (section 6); the Windows
  lock test.
