# Does it run on my cluster? Spool workers from Slurm and PBS (multi-node stage 2, step 2)

Issue gijzelaerr/rang-core#4, step 2. Step 1 ([multinode-executor.md](multinode-executor.md)) chose rang's own
spool executor (`data.executor: spool`, workers `python -m rang.core_spool worker DIR`) and excluded plain Slurm/PBS
job arrays as an *executor* because nothing here could test them (its gates G4, G5). It kept the job array as one way
of *starting workers* and left that path untested (its 5.5). This step makes that path testable: a launcher that
submits spool workers as a Slurm or PBS job array, a multi-node Slurm cluster (and a PBS one if it builds) in
containers on nash, a smaller Slurm run in CI, and the identity, recovery and scaling gates on it. Branch
`multinode-2`, from main `cd6cf276`. Infrastructure work: no novelty is claimed; the gates are identity and
recovery, timing is reported.

**Status, 2026-11-25: proposed.** Sections 0 to 5 are frozen in the commit that adds this note, before any launcher
code; 0.3.1 is the one dated addition allowed (0.3). Section 0 holds probes of the test bed only (no rang code ran
in it).

## 0. Probes before the design (2026-11-25, nash)

### 0.1 Containers on nash

- `docker`: the client is installed (29.1.3) but the daemon socket refuses this account (`permission denied ... 
  /var/run/docker.sock`); no compose provider (`podman compose`: "looking up compose provider failed").
- Rootless **podman 4.9.3** works (cgroup v2, systemd cgroup manager, netavark, aardvark DNS on user networks;
  subuid range of 65,536). `cpu`, `memory` and `pids` are delegated to containers, so `--cpus` and `--memory` hold.
- So the cluster is plain `podman` driven by a script, not docker compose. Apptainer is also installed but has no
  network namespace per container without root, so it cannot give each "node" its own hostname and daemons.

### 0.2 Slurm in rootless containers

- Ubuntu 24.04's Slurm 23.11.4: `slurmctld` runs; `slurmd` refuses to start without its cgroup plugin, and 23.11
  has no `CgroupPlugin=disabled` ("cannot find cgroup plugin for disabled"). With a writable cgroup tree
  (`--systemd=always`) and `IgnoreSystemd=yes`, `slurmd` starts, but every `slurmstepd` dies on a doubled scope
  path (`.../n1_slurmstepd.scope/system.slice/n1_slurmstepd.scope/cgroup.controllers`), so no job launches.
- **Debian 13 (trixie)'s Slurm 24.11.5** with `CgroupPlugin=disabled`, `ProctrackType=proctrack/linuxproc`,
  `TaskPlugin=task/none`, munge, `SlurmUser=root`: a controller and two `slurmd` containers on a private podman
  network come up idle in seconds; `sbatch --array=0-3 -c 1` ran two tasks on each node. Jobs run as uid 0 in the
  container (gijs on the host, by the user namespace) at **nice 19**, inherited from `nice -n 19 ionice -c3 podman
  run`. glibc 2.41, newer than nash's 2.39, so the host-built `_core` and uv's Python run from read-only mounts.
- Scripts: `tools/oracles/multinode/cluster/` (`Containerfile.slurm`, `slurm.conf.in`, `cgroup.conf`,
  `slurm_cluster.sh`). No port is published; the containers talk only on the podman network.

### 0.3 PBS

- OpenPBS (the open-source PBS Professional, which CHPC Lengau runs as PBS Pro) has no maintained container image
  and needs PostgreSQL for its server. Its build from source (`v23.06.06`) on Debian 13 was started under the lock
  on 2026-11-25 (`Containerfile.pbs`). The tagged release fails to compile on Python 3.13 (`eval.h: No such file
  or directory`; the header went in Python 3.11); a build of master `cd7ab5ed` (2026-04-10, after the fix in
  openpbs#2714) was running when this note was frozen. Its result goes in 0.3.1, filled in after the freeze: it
  only selects between branches that 1.2 and 3 already freeze (a PBS bed, or PBS not obtained).
- Torque: no maintained release (the open-source project ended with 6.1); no test bed is attempted. Its script
  dialect is tested as text only and labelled untested.

### 0.3.1 PBS result (2026-11-25, added after the freeze, as 0.3 allows)

- OpenPBS master `cd7ab5ed` builds on Debian 13 in 6 min 43 s (4 slots, nash); image 2.0 GB. A server container
  (`pbs_server`, `pbs_sched`, `pbs_comm`, PostgreSQL) and two `pbs_mom` containers on a podman network with fixed
  addresses come up `free` with `acl_roots = root`, `flatuid = true` and `$usecp *:/ /` (output copied on the
  shared filesystem); each node's `resources_available` is set to its container's `--cpus` and `--memory`.
  `qsub -J 0-3 -l select=1:ncpus=1:mem=500mb` ran two subjobs on each node, at nice 19, as uid 0.
- PBS refuses a non-rerunnable array job (`qsub: cannot submit non-rerunable Array Job`), so 1.1's `-r n` cannot
  apply to PBS arrays. The launcher marks only a one-worker PBS job `-r n`; a subjob that PBS reruns after a node
  loss is one more spool worker, which changes no result. A correction of 1.1 forced by the scheduler, recorded
  before any rang arm ran on PBS.
- So the PBS arms of section 2 run (`tools/oracles/multinode/cluster/pbs_cluster.sh`).

## 1. Design (proposed)

### 1.1 The launcher: `rang-core spool`

```
rang-core spool submit SPOOL --scheduler local|slurm|pbs|torque --workers N [--threads T]
                       [--mem-gb G] [--walltime HH:MM:SS] [--idle-exit S] [--name NAME]
                       [--python PATH] [--dry-run] [--clear-stop] [-- EXTRA SCHEDULER ARGS]
rang-core spool status SPOOL [--json]
rang-core spool stop SPOOL [--cancel]
```

- `submit` prepares `SPOOL` (core_spool's checks: 0700, owned by the caller), writes a worker script and the exact
  submit command under `SPOOL/launch/<id>/`, submits it unless `--dry-run`, and records `SPOOL/launch/<id>.json`
  (scheduler, job id, command, workers, threads, the parent's build). The script runs
  `exec PYTHON -m rang.core_spool worker SPOOL --threads T --idle-exit S`, with `PYTHON` the submitter's absolute
  interpreter (`sys.executable`), so the venv must be on the shared filesystem at the same path, as the MS and the
  spool already must be; `RAYON_NUM_THREADS` and `OMP_NUM_THREADS` are exported as `T`.
- **Dialects** (from each scheduler's documentation; each is a text golden test):
  - Slurm: `#SBATCH --array=0-(N-1)`, `--cpus-per-task=T`, `--mem=<G>G`, `--time`, `--job-name`,
    `--output=SPOOL/launch/<id>/%A_%a.out`, `--no-requeue` (recovery is the spool's lease, not Slurm's requeue);
    submitted with `sbatch --parsable`.
  - PBS Pro / OpenPBS: `#PBS -J 0-(N-1)` (PBS Pro refuses a one-element array, so N = 1 is a plain job),
    `-l select=1:ncpus=T:mem=<G>gb`, `-l walltime`, `-N`, `-o`/`-e` into the launch directory, `-r n`; `qsub`.
  - Torque: `#PBS -t 0-(N-1)`, `-l nodes=1:ppn=T,mem=<G>gb`; `qsub`. **Untested** (0.3).
  - local: N detached processes (own session on POSIX, own process group on Windows), logs in the launch
    directory; the Windows and CI path.
- Site arguments after `--` (account, partition, QOS, `module load` lines are the user's) go into the script's
  header unchanged.
- `submit` refuses when `SPOOL/stop` exists (a worker would exit at once) unless `--clear-stop`.
- Workers exit after `--idle-exit` seconds with nothing to do (default 600 s), so an allocation is not held after
  the run; the parent's own wait for a first live worker is `data.spool_wait_s` (default 600 s), which a user on a
  busy queue raises. No change to the parent or the stage code.
- `status`: live workers by heartbeat (host, pid, threads, scheduler job id), queued, claimed and done tasks, the
  launches. `stop`: the spool's `stop` file; with `--cancel` also `scancel` / `qdel` of the recorded job ids.
- `core_spool` workers additionally record the scheduler's job and array ids (`SLURM_JOB_ID`,
  `SLURM_ARRAY_JOB_ID`, `SLURM_ARRAY_TASK_ID`, `PBS_JOBID`, `PBS_ARRAY_INDEX`) in `workers/<worker>.json` and print
  their CPU-seconds on exit. No new `RANG_*` variable. No Rust change: `git diff origin/main -- core/ src/` stays
  empty, so one `_core` build serves the oracle and the branch.
- Docs: a how-to page "Run the spool on a Slurm or PBS cluster"; `docs/cli.md` regenerated.

### 1.2 The test cluster (nash, rootless podman)

- **Slurm:** a controller `ctl`, which is also the login node (the parent `rang-core` stage runs there through
  `podman exec`), and compute nodes `n1..nK`, each a container limited by `--cpus` and `--memory` to its node's
  share. Shared directory `~/Build/tmp/20261125-multinode-2/shared` (MS copies, spool, arm directories) mounted
  read-write at the same path in every container; the branch and oracle checkouts (with the venv) and uv's Python
  read-only at the same paths. The "shared filesystem" is a bind mount of one local disk.
- **PBS:** if 0.3.1 gives a working image: a server container (`pbs_server`, `pbs_sched`, `pbs_comm`, PostgreSQL),
  which is also the login node, and `pbs_mom` containers, with the same mounts.
- Every container runs under `nice -n 19 ionice -c3`; the nice level is checked inside a job (0.2 shows it is 19).
- **Fallback ladder (frozen):** nash rootless podman; if a bed cannot be brought up there, WSL on glacier through
  the Windows lock; else that scheduler's runs are reported as **not obtained**, with its launcher tested by text
  only.

### 1.3 CI (GitHub Actions)

- Service containers cannot see the extension the job builds, so the Linux `pytest` job instead installs
  `slurm-wlm` and `munge` from Ubuntu 24.04 on the runner (a VM with systemd, where Slurm 23.11's cgroup plugin
  works) and starts a single-node cluster before pytest. `tests/test_spool_launch.py` then submits a two-task
  `sbatch --array` of spool workers for a flag stage on the synthetic MS (`w2.make_ms`) and asserts identity with
  the inline path; the test skips when `sbatch` is not on `PATH` or `sinfo` reports no idle node, so Windows and
  local runs skip it. The golden-text tests (all dialects) and the `local` launcher test run on every OS.
- If the CI cluster cannot be made green on the branch, the CI step is removed and recorded as **not obtained**;
  no red run is left on the branch.

## 2. Oracle, cases and arms (frozen)

**Oracle O.** origin/main `cd6cf276`'s Python at its default `data` settings (`processes: 1`, inline), with the
branch's `_core` build copied into a detached worktree of that commit (`~/Worktrees/rang/mn2-oracle-cd6cf276` on
nash), run inside the `ctl` container, so O and the arms share the interpreter, the build and the container's
libraries. Configurations: chunk-task-api's case F and case W, as step 1's harness
(`tools/oracles/multinode/run.py`) writes them, extended with arms whose workers come from the launcher.

| Case | MS | Arm | Workers | Nodes (CPUs, memory each) | Event |
| --- | --- | --- | --- | --- | --- |
| F | the public fixture `1672727931_sdp_l0_scan_9.ms` | O | inline | (ctl) | |
| F | | Sl2 | Slurm array, 2 x 1 thread | 2 (1, 4 GB) | |
| F | | Sl4T | Slurm array, 4 x 1 thread, `chunk_rows: 7` | 2 (2, 8 GB) | |
| F | | SlKill | Slurm array, 2 x 1 thread, `chunk_rows: 7` | 2 (1, 4 GB) | the array task whose worker makes the first claim of each stage is `scancel`led |
| F | | SlNode | Slurm array, 3 x 1 thread, `chunk_rows: 7` | 3 (1, 4 GB) | the node container whose worker makes the first claim of each stage is SIGKILLed (`podman kill`); it is restarted before the next stage |
| F | | Pb2, PbKill | as Sl2 and SlKill through PBS (`qdel` of the subjob) | 2 (1, 4 GB) | only if 0.3.1 gives a bed |
| W | `w3.ms`, a fresh copy per arm from `~/rang-data/outputs/w3/data/w3.ms` (never written) | O | inline | (ctl) | |
| W | | Sl1, Sl2, Sl4 | Slurm array, N x 2 threads, `processes: N`, `memory_limit_gb: 2N` (step 1's S points) | N (2, 6 GB) | |
| W | | Sl8 | as above, N = 8 | 8 (2, 6 GB) | optional: only if the lock admits it within this task |
| W | | Pb4 | PBS, as Sl4 | 4 (2, 6 GB) | only if 0.3.1 gives a bed |
| W | | I | inline, `memory_limit_gb: 2`, `RAYON_NUM_THREADS=2` (step 1's I) | (ctl, 2 CPUs) | the overhead reference |

## 3. Criteria and the decision rule (frozen)

**Identity (no tolerance).** Chunk-task-api's criteria 1-5 against O, as step 1's `run.py verdict`: every column's
SHA-256 after each stage; flag versions; every `calibrate/` file except `summary.json` byte for byte; cleaned
summaries (`chunking` and the executor record stripped); exit 0.

**Recovery.** SlKill, SlNode (and PbKill): the stage finishes, meets identity, and its spool record shows at least
one re-queued task per stage in which the event hit a running task. A stage in which the killed worker had already
finished its task is recorded as such (re-queued 0), not failed. A hang (a stage not finished within three leases
plus O's wall for it) or a lost task (`SpoolError`) fails.

**Unit tests.** `tests/test_spool_launch.py`: golden scripts for slurm, pbs and torque; `--dry-run` writes and does
not submit; a stale `stop` is refused; the local launcher runs a flag stage on the synthetic MS identical to inline;
the Slurm test of 1.3 where `sbatch` exists. `tests/test_spool.py` still passes.

**Decision (frozen).**
- **Slurm: runs on a cluster (S)** when every Slurm arm of F and W meets identity, SlKill and SlNode meet recovery,
  and the unit tests pass on Windows, nash and CI. Otherwise **not shown (N)**, naming the failed criterion.
- **PBS:** **runs on a cluster (P)** when Pb2, PbKill and Pb4 meet identity and recovery; **not obtained (U)** when
  no bed comes up (0.3.1, 1.2's ladder), its launcher then tested as text only; **not shown (N)** when a bed ran and
  an arm failed.
- **CI:** green with the Slurm test running, or not obtained (1.3).
- What reopens step 1's choice: a failure of identity or recovery whose cause is in the spool's design (claims,
  leases, heartbeats over a shared filesystem), not a fixable launcher bug, sends #4 to step 1's next-ranked
  executor, as its section 1 freezes.

## 4. Scaling and what is reported (frozen)

- Case W points I, Sl1, Sl2, Sl4 (and Sl8, Pb4 when run), one repeat each, on the shared host: **provisional**,
  reported, not gated. Reported: wall per stage and in total (`tools/oracles/nash/timed.py` around the parent's
  `podman exec`; it does not see the workers' CPU), `S(N) = t(Sl1) / t(SlN)`, efficiency `S(N) / N`,
  `t(Sl1) / t(I)`, the workers' own CPU-seconds from their logs (1.1), task and re-queue counts, the plan digests
  (equal across N, as step 1), the foreign load from `heavy_lock.py status` at each point, and step 1's S(N) on
  process groups beside it.
- **Bookings:** one shared ticket per point for the whole cluster: `N x 2 + 2` slots (workers, the parent, the
  controller) and `16 + 3N` GB (step 1's), and the node containers' `--cpus` and `--memory` at or under it. F arms
  book 6 slots and 16 GB.
- Timing rows go to [tool-timings.md](tool-timings.md), host nash.

## 5. What this cannot show (stated before the runs)

- One host: the "nodes" are containers on nash, sharing its kernel, its clock and one local disk through a bind
  mount. A lease compares a heartbeat file's mtime (written by a worker) with the parent's clock; on a real cluster
  the file server's clock and the nodes' clocks differ, and NFS or Lustre attribute caching delays mtimes. Neither
  is exercised here. Lustre and CephFS metadata and bandwidth (#4's risks) are not measured.
- Jobs run as uid 0 inside the containers (one user on the host); site policies on job arrays, array size limits,
  `MaxArraySize`, and queue waits are not exercised.
- Slurm 24.11 (nash) and 23.11 (CI) only; ilifu's and Lengau's versions are not checked.
- No matched-accuracy comparison against QuartiCal or `wsclean-mp` (#4's requirement of stage 2 as a whole).

## 6. Results

Not yet measured.
