# A multi-node executor for the chunk tasks (multi-node stage 2, step 1)

Issue gijzelaerr/rang-core#4, step 1: the short comparison #4 asks for, and a prototype of the chosen executor
against stage 1's `ChunkSpec` ([chunk-task-api.md](chunk-task-api.md), issue #3). Branch `multinode-executor`, from
main `9b4542c`. Infrastructure work: no novelty is claimed. The prototype's gate is identity; its scaling is
reported, not gated.

**Status, 2026-11-17: implemented and measured** (section 5). Sections 0 to 4 were frozen in `01189d8`, before any
executor code. The scoring in
section 2 applies the rule of section 1 to the probes of section 0; it was written in the same sitting, by the same
agent that builds the prototype, after the rule. A reader who disagrees with a score can rescore the table: the rule
is mechanical.

## 0. Probes before the rule (2026-11-17, read only)

From PyPI's JSON API and `gh api` (public, read only):

| | `distributed` (Dask) | `dask-jobqueue` | `ray` |
| --- | --- | --- | --- |
| Licence | BSD-3-Clause | BSD-3-Clause | Apache-2.0 |
| Latest release | 2026.8.0, 2026-08-24 | 0.9.0, **2024-08-22** | 2.60.0, 2026-11-04 |
| Releases in 2026 | 12 (three of them same-day backports on 2026-07-14) | 0 | 13 |
| Commits to the default branch, 2026-05-17 to 2026-11-17 | 75, of which 49 by one maintainer (`crusaderky`), 8 by dependabot | **0** | 2,245 |
| Open issues and pull requests | 1,530 | 57 | 3,810 |
| Core dependencies (no extras) | 14 (`dask`, `tornado`, `cloudpickle`, `msgpack`, `psutil`, `zict`, ...) | 5 | 8 (`protobuf`, `msgpack`, `jsonschema`, `requests`, ...) |
| Wheel | 1.0 MB + `dask` 1.5 MB, pure Python | pure Python | 79 MB manylinux x86_64, 30 MB win_amd64, cp314 present |

Simon Perkins's point (issue #4, 2026-11-13), as far as these numbers show it: `distributed` is maintained, but
mostly by one person over the last six months; `dask-jobqueue`, the piece #4's proposal named for Slurm and PBS, has had
no commit for six months and no release for 27 months. The "task-scaling limits" part is not tested here; section 0.2
shows why it does not bind at rang's task counts.

### 0.1 Facts of the target hosts

| Host | Scheduler | Shared filesystem | Containers | Source |
| --- | --- | --- | --- | --- |
| ilifu | Slurm | not checked (CephFS per #4's risks, not confirmed in a primary source) | Singularity | processMeerKAT docs ("the ilifu SLURM cluster", a CASA Singularity container) |
| CHPC Lengau | PBS Pro | Lustre (`/mnt/lustre/users/USERNAME/`) and NFS | not checked | CHPC wiki quick start ("uses PBSPro as its job scheduler") |
| nash | none | local disks, one host | Apptainer, podman ([nash-host.md](nash-host.md)) | this account |

Outbound internet from compute nodes: not checked on either cluster. Open ports between compute nodes of one job:
assumed (MPI needs them), not checked.

### 0.2 Task counts

- Case W (`w3.ms`, 40,320 rows x 4,096 channels, 8.0 GB) at `memory_limit_gb: 32`, one process: 5 flag blocks, 6 solve
  tasks (2 partitions x 3 terms), a few apply chunks ([chunk-task-api.md](chunk-task-api.md) 6.1, `summary.json`'s
  `chunking` on nash). At 2 GiB per worker: tens per stage step (counted by the prototype, section 4).
- A full MeerKAT L-band track (64 antennas, 2,080 baselines with autocorrelations, 8 h at 8 s, 4,096 channels, 4
  correlations, complex64): DATA alone is about 1 TB. At 4 GiB per task that is about 250 tasks per pass over the
  data, of the order of 10^3 per stage with the solve passes.
- Dask's reported scaling limits concern 10^5 to 10^6 tasks per graph (scheduler overhead per task of the order of
  1 ms, not measured here). At 10^3 coarse tasks of seconds to minutes each, no candidate is limited by task count.

### 0.3 What stage 1 fixes for every candidate

`core_tasks.Executor.map(specs, source)` yields the partials in plan order; the parent reduces them and is the single
MS writer (CTDS refuses concurrent writers); a stage has barriers between maps (terms, solve passes, apply tables).
`run(spec)` never writes the MS, so re-running a task is safe. `spec.ms` is absolute (`core_pipeline.execute`
resolves it). Workers read the MS in place: whichever executor is chosen, the MS must be on a filesystem every node
mounts at the same path. Partials are dicts of NumPy arrays and counts, an `int64` array, or a
`core.ComplexSolution`; the stage 1 pool already pickles all of them.

## 1. The decision rule (frozen)

**Hard gates.** A candidate that fails one is out.

- **G1 Licence.** OSI open source and GPL-3.0-compatible; no closed-source component (scheduler or otherwise) needed.
- **G2 Contract.** It fits behind `Executor.map(specs, source)` with plan-order consumption and the parent as the
  single writer, with no change to stage code.
- **G3 Install.** From public PyPI on Python 3.14, without root and without a system service.
- **G4 Testable here.** It runs end to end on nash (no Slurm, no PBS) and on GitHub's Linux and Windows runners,
  without opening any port beyond 127.0.0.1.
- **G5 Windows.** It runs on Windows for development.

**Ranked criteria.** Each scored pass, partial or fail, from section 0 and stated design only:

1. **R1 Reproducibility.** Results bit-identical to the single-process path by construction: task content and
   reduction order do not depend on scheduling.
2. **R2 Failure and retry.** A lost worker or a failed task ends in a re-run or a raised error in plan order, never
   a hang or a partial write out of order.
3. **R3 HPC install footprint.** Dependencies, size, extra services or ports on ilifu, Lengau and nash.
4. **R4 Maintenance.** Who maintains it and how actively (section 0); risk to ra-ng if it stops.
5. **R5 Data movement.** How MS chunks and partials move between the MS, workers and the writer.
6. **R6 Task scaling.** At the counts of section 0.2.

**Choice.** Among candidates passing G1-G5, the one with the most "pass" scores on R1-R6. A tie goes to the candidate
that scores better on the first criterion, in rank order, where they differ.

**What reverses it (frozen).** The choice is reopened, for the next-ranked candidate, if the prototype:
- fails the identity gate (section 3) for a reason in the executor's design rather than a fixable bug; or
- loses a task or hangs in the worker-kill test (section 3); or
- costs more than 10 % of a stage's wall at one worker against the inline path (`t(S1) / t(I) > 1.10`, section 4),
  on exclusive points; on shared points the same figure is reported as provisional and reopens nothing.

## 2. The comparison (rule of section 1 applied)

Candidates:

- **A. Plain job arrays** (Slurm `--array`, PBS `-J`), one array per `map` call, each array task running a slice of
  the specs and writing its partials to files; the parent (in a job of its own) waits and reduces.
- **B. Dask distributed** with dask-jobqueue's `SLURMCluster` and `PBSCluster`, as #4 proposed: `client.submit(run,
  spec)` in plan order, results gathered in order.
- **C. Ray**: `ray.remote(run)` tasks, results fetched in order, a Ray head and workers started per job.
- **D. A minimal executor of rang's own: a spool on the shared filesystem.** The parent writes each spec (its
  `to_json`, stage 1's wire format) into a spool directory; long-lived workers started by any launcher (a process on
  this host, `ssh`, `srun`, a Slurm or PBS job array of pilot workers, `mpirun`-free) claim specs by an atomic rename,
  run them and write the partial under a temporary name renamed into place. The parent consumes partials in plan
  order and deletes each after the reduce. Workers keep a heartbeat file; a claim whose worker's heartbeat is older
  than a lease is put back in the queue (at most a fixed number of attempts); a task that raises writes its traceback,
  which the parent raises in plan order. A job array is then only one way of starting workers, which removes A's
  queue wait at every barrier.

| | A job arrays | B Dask | C Ray | D spool |
| --- | --- | --- | --- | --- |
| G1 | pass | pass (BSD-3) | pass (Apache-2.0) | pass (in-repo, GPL) |
| G2 | pass | pass | pass | pass |
| G3 | pass (no Python dependency) | pass | pass | pass (no new dependency) |
| G4 | **fail**: needs Slurm or PBS, which nash and CI lack | pass (`LocalCluster` on 127.0.0.1) | pass (local head on 127.0.0.1) | pass (local processes) |
| G5 | **fail**: no Slurm or PBS on Windows | pass | pass (win_amd64 wheel; Ray's own Windows status not checked) | pass (rename on NTFS) |
| R1 | | pass | pass | pass |
| R2 | | partial: worker loss is retried (`allowed-failures`); the scheduler is a single point of failure; a dead dask-jobqueue job is resubmitted by the cluster object, untested here | partial: task retries built in; the head node is a single point of failure | pass by design (leases, attempts, errors raised in plan order), to be shown by the kill test |
| R3 | | partial: 16 packages, a scheduler process, TCP ports between nodes, dask-jobqueue for Slurm and PBS | fail: 79 MB wheel, a head with gRPC services, a shared-memory object store to size on HPC nodes | pass: nothing beyond rang; works inside an Apptainer image with the spool bind-mounted |
| R4 | | partial: `distributed` active but carried by one maintainer; dask-jobqueue inactive 27 months | pass: very active, company-backed | partial: about 300 lines that ra-ng maintains itself |
| R5 | | partial: MS read in place; specs and GB-sized partials (apply) move by TCP through the client | partial: MS read in place; partials through the object store | partial: MS read in place; specs and partials move through the shared filesystem the MS is on, written once and read once (#4's shared-filesystem bandwidth risk applies) |
| R6 | | pass | pass | pass (two files per task; at 10^3 tasks no metadata pressure; poll latency about 0.1 s per task) |
| Passes on R1-R6 | (out) | 2 | 3 | 4 |

**Outcome: D, the spool executor.** A is out on G4 and G5, but its file-based results and its use of the scheduler
as a launcher are kept in D. Of the rest, D scores 4 passes, Ray 3, Dask 2. Dask is not ruled out for good: if the
spool fails a reversal condition of section 1, Ray is next in rank and Dask after it, by this table.

**Multi-host across this Windows machine and nash: not attempted.** The two hosts share no filesystem and the MS
paths differ, so D (and B and C as well, since workers read the MS in place) would need the 8 GB MS copied and
GB-sized partials moved over ssh. The "nodes" are separate process groups on nash, each a worker with its own threads
and its own session (`setsid`), as section 4 freezes.

## 3. The prototype and its identity gate (frozen)

**Code (proposed).**
- `python/rang/core_spool.py`: the spool (claim, lease, heartbeat, results) and the worker
  (`python -m rang.core_spool worker SPOOL [--threads T]`).
- `core_tasks.Executor` gains `kind: spool`: `data.executor: spool` with `data.spool: <directory>`. `data.processes`
  is the number of workers the parent plans for (the 2N window and stage 1's `memory_limit_gb / processes` per
  worker, unchanged); it starts none. Workers set `RAYON_NUM_THREADS` from `--threads` before the core loads.
- The parent refuses a worker whose rang version or `_core` SHA-256 differs from its own (the worker writes them on
  start), so a mixed build cannot enter a run.
- No Rust change: `git diff origin/main -- core/ src/` stays empty, so one `_core` build serves the oracle and the
  branch.
- Partials are pickled (protocol 5) into the spool, which the parent creates with mode 0700. Anyone who can write
  into the spool can run code in the parent, so it must be private to the user; the parent refuses a spool not owned
  by it (POSIX).

**Oracle O.** origin/main `9b4542c`'s Python at its default `data` settings (`processes: 1`), with the branch's
`_core` build, from a checkout of that commit (on Windows the main checkout; on nash a detached worktree).

**Cases and arms.**

| Case | MS | Where | Arms against O |
| --- | --- | --- | --- |
| F | the public fixture `1672727931_sdp_l0_scan_9.ms` (chunk-task-api's case F configuration) | Windows | `Sp2` spool, 2 workers x 1 thread; `Sp4T` spool, 4 workers x 1 thread, `chunk_rows: 7` (many tasks) |
| W | `w3.ms`, a fresh copy per arm of `~/rang-data/outputs/w3/data/w3.ms` (read only, kept for the chunk-task-api matrix) | nash | every point of section 4 (`S1`, `S2`, `S4`, `S8`), and `I` |

Stages flag, calibrate, apply, with chunk-task-api's case F and case W configurations. The harness refuses to run a
stage on any path under `~/rang-data/outputs/w3`.

**Criteria (no tolerance).** Chunk-task-api's criteria 1-5 against O: every column's SHA-256 after each stage; flag
versions; every `calibrate/` file except `summary.json` byte for byte; cleaned summaries (`chunking` stripped); exit
0. Plus:
- **Kill test.** On F with `chunk_rows: 7` and 2 workers, one worker is killed (SIGKILL / `TerminateProcess`) after
  its first claim; the run must finish, re-run the lost task on the other worker or a replacement, and pass criteria
  1-5.
- **Unit tests** (pytest, CI on Linux and Windows): a spool round trip on a synthetic MS (`w2.make_ms`), flag,
  calibrate and apply at 2 spool workers equal to `processes: 1`; a raising task raises in plan order with earlier
  partials written; a lost claim is re-queued; a worker of another build is refused; config validation of
  `executor: spool` without `data.spool`.

**Decision.** The prototype gate passes when every arm of F and W meets criteria 1-5, the kill test passes, and the
unit tests pass.

## 4. Scaling S(N) on nash (frozen)

- **Case W**, flag, calibrate, apply, each point on a fresh copy in `~/Build/tmp/20261117-multinode/`.
- **A node brings its own cores**: every worker runs `t = 2` rayon threads, and every worker gets 2 GB:
  `memory_limit_gb = 2 N` with `processes: N`, so `memory_limit_gb / processes` = 2 GB and the plan is the same at
  every N. The harness records a digest of every map's spec list and asserts it is equal across the S points.
- **Points:** `I` (inline, `processes: 1`, `memory_limit_gb: 2`, `RAYON_NUM_THREADS=2`: the same plan, no spool);
  `S1`, `S2`, `S4`, `S8` (spool, N workers, each in its own process group). Each stage of a point is one reading of
  `tools/oracles/nash/timed.py`; the workers are children of the timed command, so their CPU and the nice level are
  inside it, and they exit when the stage driver ends.
- **Bookings:** shared lock tickets of `2 N + 1` slots (the parent uses about one core while it reduces and writes)
  and `16 + 3 N` GB; `I` books 3 slots and 16 GB. Every process under `nice -n 19 ionice -c3`.
- **Repeats:** one per point on the shared host (**provisional**: other jobs run beside it; the foreign load is
  recorded, nothing is void). Exclusive points: the same five, once, queued only when `heavy_lock.py status` shows no
  hold and an empty queue (chunk-task-api 5.1's rule), never waiting behind shared jobs; if no idle window comes in
  this task, they are reported as not obtained.
- **Reported:** wall per stage and in total; `S(N) = t(S1) / t(SN)`; efficiency `S(N) / N`; the spool's overhead
  `t(S1) / t(I)`; CPU-seconds and peak RSS (largest process) per stage; foreign load; task counts per stage;
  identity of every point against O. apply used about one core on nash at one process (chunk-task-api 6.1): its S(N)
  is reported as measured, also if below 1.

## 5. Results (measured 2026-11-17)

**Verdict: the prototype gate passes, and the choice stands.** Every arm of F (Windows and nash) and of W (nash) is
bit-identical to O on criteria 1-5; the kill test passes on both hosts; the unit tests pass on both. None of section
1's reversal conditions is met (the overhead condition only provisionally, section 5.3).

Code: branch `multinode-executor`, commits `2a00fe3` to `723c858` (the gates ran on `71417b4`'s package code;
`723c858` changes only a test, and `3ec6747` only names the encoding and newline of the worker's record file, which
the portability test requires). Oracle O: main `9b4542c` from detached worktrees (`~/Worktrees/rang/mn-oracle-9b4542c`
on both hosts) holding the branch's `_core` build; `git diff 9b4542c -- core/ src/` is empty. Builds: Windows
`_core.pyd` SHA-256 `caf80328…`, nash `_core.abi3.so` `e0c92694…`, the same on both sides of every comparison (the
harness checks it). Receipts: [results/multinode-executor/](results/multinode-executor/) (`windows/` and `nash/`:
`verdict.json`, nash's `report.json`, and every arm's `done.json`, `config.yaml` and `stage-*.json`). Harness:
`tools/oracles/multinode/run.py` and `nash_points.sh`.

### 5.1 Identity

| Case, host | Arm | Files compared | Result | Walls flag / calibrate / apply, s |
| --- | --- | ---: | --- | --- |
| F, Windows | Sp2 | 123 | identical | 3.7 / 3.7 / 2.6 (O 2.6 / 1.9 / 1.9) |
| F, Windows | Sp4T | 123 | identical | 3.3 / 4.9 / 4.8 |
| F, Windows | Kill | 123 | identical | 63.7 / 67.1 / 5.2 |
| F, nash | Sp2 | 123 | identical | 5.2 / 4.9 / 3.1 (O 5.5 / 2.1 / 1.7) |
| F, nash | Sp4T | 123 | identical | 6.0 / 6.7 / 3.4 |
| F, nash | Kill | 123 | identical | 64.3 / 69.7 / 67.5 |
| W, nash | I, S1, S2, S4, S8 | 240 each | identical | section 5.2 |

- **Kill test.** One worker was killed (`taskkill /F`, SIGKILL) right after its first claim in each stage. On nash
  the parent re-queued one task in each of flag, calibrate and apply after the 60 s lease, and the run finished
  identical. On Windows it re-queued one in flag and one in calibrate; in apply the killed worker had finished its
  task before the kill landed, so nothing was lost (re-queued 0, 5.2 s) and the other worker ran the rest. The
  60 s waits are the lease.
- **Unit tests:** `tests/test_spool.py` (7 tests) with `tests/test_chunk_tasks.py`: 15 passed, 2 skipped on Windows
  (the POSIX permission test; the fixture test without `RANG_FIXTURE`); `test_spool` 7 of 7 on nash.
- **Plans.** The parent's digest of every map's specs (the `ms` path left out) is equal at S1, S2, S4 and S8 in each
  stage, so every N ran the same tasks (section 4).

### 5.2 Scaling on nash (shared host: provisional)

Each point ran under its own shared ticket (`2N + 1` slots, `16 + 3N` GB; O 4 slots), at nice 19 and ionice idle,
on a fresh copy of `w3.ms`, one after another between 10:00 and 13:21 SAST. Workers: 2 rayon threads each, each in
its own session; `memory_limit_gb = 2N`, so 2 GB per worker.

| Point | flag, s | calibrate, s | apply, s | total, s | CPU-s flag / calibrate / apply | foreign load, cores | peak RSS (largest process), GB |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| O (main, defaults, 4 threads) | 512.4 | 739.5 | 176.5 | 1428.3 | 1835 / 2241 / 195 | 11.1 / 11.7 / 8.3 | 2.7 / 3.3 / 6.9 |
| I (inline, 2 threads, 2 GB) | 908.9 | 1461.0 | 182.5 | 2552.4 | 1747 / 2522 / 189 | 8.5 / 11.4 / 27.8 | 0.7 / 0.7 / 1.1 |
| S1 | 940.7 | 1488.9 | 156.4 | 2586.1 | 1818 / 2578 / 226 | 23.6 / 21.8 / 16.3 | 0.7 / 0.7 / 1.4 |
| S2 | 523.3 | 726.2 | 109.2 | 1358.7 | 1838 / 2396 / 222 | 10.7 / 6.9 / 12.1 | 0.7 / 0.7 / 1.4 |
| S4 | 296.4 | 430.1 | 120.8 | 847.3 | 1846 / 2496 / 224 | 12.1 / 17.0 / 15.2 | 0.7 / 0.7 / 1.4 |
| S8 | 192.3 | 254.6 | 107.2 | 554.1 | 1799 / 2494 / 228 | 7.2 / 7.1 / 4.5 | 0.7 / 0.7 / 1.4 |

| N | S(N) flag | calibrate | apply | total | efficiency S(N)/N, total |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 1.80 | 2.05 | 1.43 | 1.90 | 0.95 |
| 4 | 3.17 | 3.46 | 1.30 | 3.05 | 0.76 |
| 8 | 4.89 | 5.85 | 1.46 | 4.67 | 0.58 |

Bookings against the cores used (CPU-seconds / wall). The bookings followed section 4 (`2N + 1`); flag and
calibrate used about 60 % of them at N = 8, apply about 2 cores at every N, so the bookings were above use:

| Point | Booked slots | Cores used, flag / calibrate / apply |
| --- | ---: | --- |
| I | 3 | 1.9 / 1.7 / 1.0 |
| S1 | 3 | 1.9 / 1.7 / 1.4 |
| S2 | 5 | 3.5 / 3.3 / 2.0 |
| S4 | 9 | 6.2 / 5.8 / 1.9 |
| S8 | 17 | 9.4 / 9.8 / 2.1 |

The same plan ran at every point: the parent's spec digests are equal at S1 to S8, and the `chunking` records of the
stage summaries (flag blocks per group 5, 5, 2, 2, 3; the solve chunks per partition; the row budgets) are equal at
I, S1 and S8, so `t(S1) / t(I)` compares the same tasks.

Per stage at every N: 17 flag tasks, 132 solve tasks (three terms, two passes for the chunked partitions) and 54
apply tasks, with 0.66 GB, 0.05 GB and 11.0 GB of partials through the spool; no task was re-queued. The CPU-seconds
stay flat with N, so the spool adds no per-task work that grows with the worker count.

Post hoc reading (one repeat per point on a shared host; not a frozen claim):
- **flag** is bounded by its task count. 17 blocks over 8 workers means 3 rounds for the busiest worker against 2.1
  on average, which caps the efficiency near 0.71 for equal blocks; 0.61 was measured. A smaller per-worker budget
  gives more blocks.
- **calibrate** waits at every barrier (each term, each pass) for its slowest task: 0.73 at N = 8.
- **apply** stays near 1.5. It moves 11 GB of output columns through the spool, and the parent writes them alone,
  as the single writer must. This is #4's single-writer risk, measured. Any executor that keeps the single writer
  moves the same bytes (B and C by TCP).
- O is the identity reference, not a scaling point (other threads and budget).

### 5.3 Overhead and exclusive points

- Spool overhead at one worker, `t(S1) / t(I)`: flag 1.035, calibrate 1.019, apply 0.857, total 1.013. These are
  shared points, so by section 1 they are provisional and reopen nothing; all are under the 1.10 limit. apply's
  0.857 (the spool faster than inline) is not explained by the executor and is read as load.
- **Exclusive points: not obtained.** The lock was never idle during the task (41 of 44 slots booked at 13:05 SAST,
  for example), so by section 4 none was queued.

### 5.4 Changes during the work, recorded

- **The claim is not a rename** (implementation, 2026-11-17, before any gate run; section 2 described an atomic
  rename). The first spool unit test failed on Windows: two workers both renamed the same task file, the second
  moving it on, so a task could run twice or lose its file. A probe of three processes over 400 files showed it
  repeatably. The claim is now a file created with `O_CREAT | O_EXCL` (no duplicates in the same probe), and file
  operations retry Windows sharing violations, on one of which a worker died in the void run below.
- **Void F run, kept:** `D:\rang\outputs\mn-20261117-01-void`. O did not run (the harness asked the oracle for
  `core_spool`, which main lacks); the kill test killed nothing (on Windows a venv's `python.exe` is a launcher with
  another pid, so the harness now kills the pid named in the claim); one worker died on a sharing violation. No
  verdict was drawn from it. The rerun is `D:\rang\outputs\mn-20261117-02`.
- `tests/test_spool.py`'s stage test first used the arm's work directory as the spool, which the POSIX permission
  check refused on nash; fixed in `723c858`.

### 5.5 What this does not show

- No Slurm or PBS run: nash has neither. Workers started by `srun` or a job array run the same command, untested.
- No second host: the "nodes" are process groups on one host and one filesystem (local disk). Lustre and CephFS
  metadata and bandwidth (#4's risks) are not measured.
- No matched-accuracy comparison against QuartiCal or `wsclean-mp`, which #4 requires of stage 2 as a whole.
- Only flag, the complex solve and complex apply go through the executor; the chain terms stay serial (stage 1b).
- S(N) is at 2 threads per worker, so the cores grow with N (a node brings its own). It is not comparable with
  chunk-task-api section 5's fixed budget of 16 threads.
- The heartbeat is a Python thread. It beats during kernels because the extension releases the GIL (`py.detach` in
  `core/py/src/lib.rs`); task durations were not logged, but no task on W was re-queued while running.
- Job arrays (A) were excluded by the hard gates G4 and G5 and not scored on R1-R6. D's launch path on Slurm or PBS
  is itself a job array of pilot workers, and that path is untested.

## For the coordinator

- **Outcome:** the spool executor (D), ahead of job arrays (out: they need Slurm or PBS), Dask (2 passes:
  dask-jobqueue inactive for 27 months, `distributed` carried by one maintainer) and Ray (3 passes: a 79 MB wheel, a
  head and an object store).
- **Gate passes:** F on Windows and nash and W on nash, all bit-identical to main; the kill test passes.
- **S(N) on nash, shared:** 1.90 / 3.05 / 4.67 in total at N = 2 / 4 / 8; calibrate 5.85 at 8; apply stays near 1.5
  (the single writer). Exclusive points not obtained.
- **Next for #4:** a Slurm run on ilifu and a PBS run on Lengau (job arrays of pilot workers), a whole-array MeerKAT
  set on Lustre or CephFS, and the matched-accuracy comparisons. The apply ceiling needs a decision: accept it, or
  let workers write disjoint row ranges (CTDS refuses concurrent writers today).
- Not merged. The full `python tools/check_all.py` has not been run on the branch.
