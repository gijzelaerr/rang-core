# Chunk task API, run multi-process on one node (multi-node stage 1)

Stage 1 of the multi-node path ([multi-node-scope.md, section 4](https://github.com/gijzelaerr/rang-core/blob/26b7fc1/research/multi-node-scope.md)
on branch `roadmap-v030`; issue gijzelaerr/rang-core#3). It turns the chunk loops of W3 ([w3-chunking.md](w3-chunking.md))
and W3b ([w3b-chainchunks.md](w3b-chainchunks.md)) into explicit tasks and adds a local process-pool executor. Branch
`claude/chunk-task-api-946978`, from main `30d9412`. This is infrastructure work, so no novelty or speed is claimed.
The gate is identity, and timing is measured later on an exclusive host.

**Status, 2026-11-13: proposed.** Sections 0 to 5 are frozen before any code is written.

## 0. Probes before the design (not comparisons)

The design rests on two facts, both checked on this host (Windows 11, main `30d9412`'s extension) before this note was
written:

- **Kernels do not depend on the thread count.** One `complex` solve (24 antennas, 12 dumps, 256 channels, 13 iterations),
  one `cal_apply.apply_jones` of its gains, and one Tricolour `flag_rows` with CARACal's first-pass strategy
  (16 antennas, 30 dumps, 512 channels) were each run at `RAYON_NUM_THREADS` 1, 2 and 4. The SHA-256 of their outputs
  was equal at every count. That makes N workers at T/N threads comparable to one process at T threads. The probe ran
  outside the heavy lock: 2-5 s per run, and the queue was 16 deep.
- **A second process can read while the parent writes.** A spawned process read DATA, FLAG and CORRECTED_DATA through
  `core_ms.open_table` while the parent held a `WriteBack` session open and wrote FLAG and CORRECTED_DATA in 7-row
  chunks (not aligned with tiles). It read the next chunk during the write and read each chunk back after the write.
  There were 0 mismatches over 240 rows (Windows). On Linux, `WriteBack` holds an fcntl lock. The reader takes no
  lock and does not refuse a locked table, which CI's Linux pytest of section 4 will show.

Why this holds: workers read only rows that no one has written in the current phase, or rows written and flushed
before the phase began (section 1.2). When the parent writes a tile, the bytes of the other rows in that tile do not
change.

## 1. Design (proposed)

### 1.1 The API (`rang.core_tasks`)

- **`ChunkSpec`**: the task, with no live objects in it.
  - `stage`, `kind`, `index` (the position in the plan, which is also the reduction order) and `ms`.
  - `key`: a JSON-able identity (group, block, term, partition, chunk, pass).
  - `params`: JSON-able scalars and lists.
  - `arrays`: NumPy arrays (the rows, the per-row metadata a kernel needs, and the solution slices the task applies).
  - `to_json()` and `from_json()` round-trip it exactly, with arrays as dtype, shape and base64 bytes. A stage 2
    executor (Dask) sends the same object. The local pool pickles it.
- **`plan_*(...) -> [ChunkSpec]`**: one function per splittable stage. It is built from W3/W3b's existing chunkers
  (`core_chunks.baseline_blocks`, `solve_chunks`, `Budget.rows`), with the same boundaries as today for the same
  budget.
- **`run(spec, source=None) -> partial`**: reads the cell columns it needs and runs the kernel. It never writes the MS.
  With `source=None` it opens its own reader (`core_ms.open_table(spec.ms)`), which is what a worker does. Inline, it is
  handed the stage's existing source (the `WriteBack` session or reader), so it reads exactly what today's loop reads.
- **reduce**: done by the parent, in plan order. It writes each partial through the stage's one `WriteBack` session
  (the single MS writer, as CTDS requires), adds up counts and assembles solutions by chunk index. Results are
  consumed in `index` order whatever order the workers finish in. So the reduction order is fixed, and floating-point
  sums (the summary fractions come from integer counts) and writes happen in the same order as the serial loop.
- **Executor**: `core_tasks.executor(config)` is a context manager with `map(specs, source) -> iterator of partials`,
  in spec order.
  - `data.executor: local` is the only choice for now. Stage 2 adds `dask`.
  - `data.processes` defaults to **1**. At 1 the map is a plain loop in this process with the stage's source and no
    pool, so the default path runs the same code as N > 1 but none of the multiprocessing machinery. E2 runs at the
    default and is unchanged.
  - At N > 1: `concurrent.futures.ProcessPoolExecutor` with the **spawn** context on every platform. The pool starts
    at the first pooled map, so a stage with nothing to split starts no process.
  - Each worker's initializer sets `RAYON_NUM_THREADS = max(1, T // N)` before any kernel runs. T is `data.threads`
    when set, else the parent's `RAYON_NUM_THREADS`, else `os.cpu_count()`.
  - At most N tasks are in flight. The parent holds at most N partials that are finished but not yet written.
- **Errors**: a failed task raises when its turn in plan order comes. Everything before it has been written, as in the
  serial loop, and nothing after it. Pending tasks are cancelled. So the MS on disk at a failure equals the serial
  run's.
- **Keys**: `data.executor`, `data.processes` and `data.threads` are resource keys. They join `RESOURCE_KEYS`, so they
  leave the stage hash unchanged (a test pins this). The summary records the executor under `chunking`, which the
  W3 cleaner already strips. `RANG_SOLVE_TRACE` (one trace file per process) is refused when N > 1.

### 1.2 What splits, and the barriers

| Stage, path | Task (`kind`) | Partial | Barrier | Through the pool at N > 1 |
| --- | --- | --- | --- | --- |
| flag | one (field, ddid, scan) group, or one block of its consecutive baselines on the group's full time grid (`flag-block`) | new FLAG of its rows, counts, seconds | none; the parent writes blocks in order | yes |
| calibrate, `complex` term, partition in one chunk | `solve-whole` | gains, flags, iterations, converged fraction | between terms | yes |
| calibrate, `complex` term, chunked partition | pass 1 `solve-pass1` (stop off, trace), then pass 2 `solve-pass2` (`max_iterations = j + 1`) | pass 1: per-iteration counts; pass 2: the chunk's gains and flags | pass 1 of every chunk of the term, then the stop replay per partition (`core_chunks.replay_stop`), then pass 2 | yes |
| apply, `complex` table (`applycal.apply_complex`) | one row chunk (`apply-rows`) with the time-bin slices of the gains its rows use | the output column and the new FLAG of its rows, counts | between tables of a target (table k reads the column that k−1 wrote) and between targets | yes |
| calibrate, models (`calmodels.set_model`) | not split | | | no: in the parent, as now |
| calibrate, chain terms K, G, B, A, F, Gpol, KCROSS, Xf, Df (`cal_chain.run`) | not split | | | no: in the parent, as now |
| apply, CASA tables (`applycal.applycal`) | not split | | | no: in the parent, as now |
| image, selfcal | not split | | | no |

Where this departs from the issue's wording:

- **Flag splits by baseline block, not by channel block.** SumThreshold and the other Tricolour windows run along
  frequency, so a channel cut would change the flags. Baselines are independent, and W3 split by them bit for bit. The
  issue's "per scan × channel block" is therefore per scan × baseline block here.
- **The chain terms stay serial in stage 1.** W3b's chunk loop sits inside `cal_gain`, `cal_delay`, `cal_bandpass`,
  `cal_pol` and `cal_fluxscale`, behind pre-applies and the reference-antenna and gauge passes over whole fields.
  Turning it into tasks is its own change:
  - pass 1 and pass 2 per chunk, as for `complex`;
  - the reductions: fluxscale, Df's streamed gauge median, and Xf and KCROSS across scans;
  - each needs the same identity gate.

  This is proposed as stage 1b. The identity runs on the chain cases (C, P) below check only that the executor
  plumbing leaves that path unchanged. **They are not evidence that chain terms run in parallel, because they do not.**

### 1.3 Memory

- `data.memory_limit_gb` stays the stage's whole budget. At N > 1, `core_chunks.budget` plans each process's chunks
  under `limit / N`. Each worker pays `BASE_BYTES` and the row bytes as a process of its own. Preflight therefore
  refuses before anything is written when one worker's smallest unit does not fit `limit / N`, with W3's messages and
  the per-process limit named. At N = 1 nothing changes.
- On top of that, the parent holds the stage's row metadata and up to N unwritten partials: 1 byte per cell for flag,
  9 for apply, solutions for calibrate. That is not inside `limit / N` per worker. Peak memory is **reported, not
  gated**, in this stage. On Windows there is no `/usr/bin/time` and no gate needs it.
- Chunk boundaries at N > 1 differ from N = 1 at the same limit. That changes nothing in the results (W3's and W3b's
  frozen claim), and the arms below test it again.

### 1.4 What changes in the code (proposed)

- New `python/rang/core_tasks.py`: `ChunkSpec`, the executor, the `plan_*` and `run` functions.
- `core_pipeline.stage_flag`: the block loop becomes plan, map and reduce.
- `_solve_term` and `solve_partition`: built on the same plan, map and reduce. `solve_partition` keeps its signature
  (tests call it) and runs inline.
- `applycal.apply_complex`: the row-chunk loop becomes plan, map and reduce. It takes `executor=None` (inline).
- `core_config`: the three keys, `RESOURCE_KEYS`, and their validation (`processes` ≥ 1, `threads` ≥ 1 or null).
- `core_chunks.budget`: `limit / processes`.
- `docs/cli.md`: regenerated.
- No Rust changes. `git diff 30d9412 -- core/ src/` stays empty.

## 2. Data and cases (frozen)

Every arm runs on a fresh copy of the MS in `D:\rang\outputs\cta-20261113-<nn>\<case>-<arm>\`. The sources are read
only. Inputs not already on D: are copied to `D:\rang\outputs\cta-20261113-inputs\`: O-CASA's slice from the WSL
checkout, CARACal's strategy at `8f7bb363` (equal to `research/results/e2-acceptance-scripts/`'s copy), and the public
fixture `outer_scans.zip` (sha256 `d4dae56f…`).

| Case | MS | Stages | Configuration |
| --- | --- | --- | --- |
| F | the public fixture, `1672727931_sdp_l0_scan_9.ms` (140 rows × 4096 ch, 4 antennas, J1939-6342) | flag, calibrate, apply | W3's complex configuration (CARACal's first-pass strategy; setjy; Gint `int`/16, G2 `2`/512, Gchan `inf`/1), fcal only |
| S | A1 small `D:\rang\outputs\fp-a1-20261106-simtruth\small\a1-small.ms` | flag, calibrate, apply | W3's case S |
| O | O-CASA's slice (copy in `cta-20261113-inputs`) | flag, calibrate, apply | W3's case O |
| W | W3's whole-array set `D:\rang\outputs\w3\data\w3.ms` (40,320 rows × 4096 ch, 8.0 GB) | flag, calibrate, apply | W3's case W |
| C | A1 small | calibrate, apply | W3b's case C (K, G, B, A; Gsec, Asec, F): chain, serial |
| P | C6w's poldx `D:\rang\outputs\c6w-20261106-01\prepared.ms` | calibrate, apply | W3b's case P (K, G, B; F; Gpol, KCROSS, Xf, Df; parang): chain, serial |

Arms:

- **U, today's single process (the oracle).** Main `30d9412`'s Python from a detached worktree
  (`~/Worktrees/rang/cta-oracle-30d9412`) with this branch's extension build. The Rust is identical (section 1.4), as
  in W3. Default configuration.
- **P1**: this branch at the defaults (`processes: 1`).
- **P4**: this branch with `processes: 4, threads: 4`, so one rayon thread per worker. The default limit gives 2 GiB
  per worker: on W the chunks are about those of W3's 2 GiB arm, and on the small sets one chunk per group or
  partition.
- **P2T**: this branch with `processes: 2, threads: 2`, `chunk_rows` 7 (F, S, O, C, P). That forces many chunks
  through the pool where P4 at the default limit splits nothing. Not run on W: W3's tiny arm there took hours of
  re-reads.

Cases and arms: F, S, O: U, P1, P4, P2T. W: U, P1, P4. C, P: U, P1, P4, P2T.

Each arm runs under the heavy lock at normal priority. Slots equal the arm's total threads (U and P1: 4 through
`RAYON_NUM_THREADS=4`; P4 4; P2T 2). Memory: 4 GB for the small sets; on W, 20 GB for U and P1 (W3's peaks were
5.0 GiB chunked, and today's default is chunked) and 12 GB for P4.

Hashes use rang's own reader (`core_ms`), not casacure, which the Windows venv lacks. That is enough for an
equality test between arms read the same way. Hashes are taken in row chunks of 128 MiB:

- the SHA-256 of every column;
- the FLAG and FLAG_ROW of every flag version, keyed by stage with the time stamp removed.

## 3. Criteria (frozen before the first comparison)

No tolerance is allowed: the executor changes no arithmetic (section 0, section 1). Every comparison is against U,
for each of P1, P4 and P2T, and a difference is a failure, reported as measured.

1. **Columns.** After each stage, every MS column's SHA-256 equals U's.
2. **Flag versions.** After the last stage, their list and their FLAG and FLAG_ROW hashes equal U's.
3. **Tables.** Every file under `<run>/calibrate/` except `summary.json` is byte-identical to U's: QuartiCal stores
   and CASA tables.
4. **Summaries.** Each stage's `summary.json` equals U's after W3's cleaner (`tools/oracles/w3/compare.py`
   `VOLATILE`: times, paths, flag-version names, `chunking`).
5. **Exit.** Every stage command exits 0 in every arm.
6. **Unit tests** (pytest; CI on Linux and Windows):
   - `ChunkSpec` JSON round-trip;
   - the three keys leave every stage hash unchanged and are validated;
   - on a synthetic MS (`w2.make_ms`), `flag`, `calibrate` (complex, with chunked partitions) and `apply` at
     `processes: 2` and 7-row chunks give columns, stores and cleaned summaries equal to `processes: 1`;
   - a failing task in the middle of a plan raises it with the earlier partials written and the later ones not;
   - preflight refuses when `limit / N` cannot hold one worker;
   - `RANG_SOLVE_TRACE` with N > 1 is refused;
   - a test on the public fixture (flag, calibrate, apply, N = 1 against N = 2) that skips when the fixture is absent.

**Decision:** stage 1's identity gate passes when criteria 1-6 pass on every case and arm. The timing runs (section 5)
then decide nothing on their own: they are reported as scaling efficiency for the stage 2 decision.

## 4. What is not checked (stated before the run)

- Chain terms through the pool: they do not go through it (section 1.2).
- Peak memory: not gated (section 1.3).
- Linux runs of the identity arms: Linux is covered by CI's unit tests only. macOS is not checked.
- Speed: section 5, not run by this task.
- A held-out case: none. Identity has no fitted parameter to hold out.

## 5. Timing runs (frozen here, run by the coordinator after E2 on an exclusive host)

- **Command:** `heavy_lock.py run -- <harness> timing W N` (exclusive).
- **Case W:** flag, calibrate, apply, each on a fresh copy.
- **Thread budget:** T = 16. N ∈ {1, 2, 4, 8} with `threads: 16`, so 16/N rayon threads per process.
- **Memory:** `memory_limit_gb: 32`, so each worker gets ≥ 4 GiB, and N = 1 chunks as at 32 GiB.
- **Baseline:** main `30d9412` at `RAYON_NUM_THREADS=16` and `memory_limit_gb: 32`.
- **Repeats:** 3 per point, in rotating order.
- **Reported:**
  - median wall per stage;
  - speed-up S(N) = t(1)/t(N);
  - efficiency S(N)/N;
  - the spawn overhead, measured as the time to the first task's start;
  - the identity of every repeat against the baseline (criteria 1-4).
- **Estimate:** about 35 min per point, 13 points, about 8 h exclusive. Two repeats take about 5 h, if the coordinator
  prefers that.

## 6. Results

(After the runs.)

## For the coordinator

(After the runs.)
