# Run on a Slurm or PBS cluster

Flag, the `complex` solve and `complex` apply can hand their chunk tasks to
workers on other nodes: the spool executor ({gh}`research/multinode-executor.md`).
The stage itself (the *parent*) stays one process, reduces the partials in
plan order and is the only writer of the MS, so the results are bit-identical
to a run in one process, however many workers run and wherever they run.
`rang-core spool submit` starts the workers as a Slurm job array or a PBS
array job ({gh}`research/multinode-2.md`). The chain terms (K, G, B, F,
polarisation), CASA-table apply and imaging do not go through the spool yet.

## What the cluster must give you

- **One filesystem at the same path on every node** for the MS, the spool
  directory and the Python environment (a venv with rang installed). Workers
  open the MS in place by its absolute path and refuse a task from a parent
  of another build (rang version and the `_core` extension's SHA-256).
- **The parent on a node that may run for the whole stage**: a login node
  if your site allows long processes there, else a batch job of its own
  (below). It needs about one core and the memory of the reduce.
- Nothing else: no port between nodes, no service, no root. Workers and the
  parent talk only through files in the spool.

## Configuration

```yaml
data:
  executor: spool
  spool: /scratch/me/eso137/spool   # absolute; private to you (mode 700)
  processes: 8          # the workers you plan for: sets the plan's chunk sizes
  memory_limit_gb: 64   # the plan gives each worker memory_limit_gb / processes
  spool_wait_s: 3600    # how long the parent waits for a first live worker
```

Raise `spool_wait_s` above your queue's wait: the parent fails when no worker
has been seen for that long.

## Start the workers

Slurm (one worker per array task; `--directive` lines go into the script's
header unchanged):

```sh
rang-core spool submit /scratch/me/eso137/spool --scheduler slurm \
    --workers 8 --threads 4 --mem-gb 10 --walltime 04:00:00 \
    --directive=--account=b42 --directive=--partition=Main
rang-core run config.yaml my.ms
```

PBS Professional or OpenPBS (`qsub -J`; CHPC Lengau runs PBS Pro):

```sh
rang-core spool submit /mnt/lustre/users/me/spool --scheduler pbs \
    --workers 8 --threads 4 --mem-gb 10 --walltime 04:00:00 \
    --directive="-q normal" --directive="-P ASTR1234"
```

Torque (`qsub -t`) writes the same script in Torque's dialect; it has not
been run on a Torque cluster. `--scheduler local` starts the workers as
processes on this machine (any OS). `--dry-run` writes the script into
`SPOOL/launch/<id>/worker.sh` and submits nothing, so you can read or edit it
and submit it yourself.

Each worker runs `PYTHON -m rang.core_spool worker SPOOL --threads T
--idle-exit S` with the interpreter you ran `submit` with, and exits after
`--idle-exit` seconds (default 600) with nothing to do, so the allocation is
released when the run ends. Workers may start before or after the parent and
may join or leave during a stage.

## Follow and stop

```sh
rang-core spool status SPOOL      # live workers (host, job id), queued and done tasks
rang-core watch my.ms.rang-run    # the stage itself
rang-core spool stop SPOOL --cancel   # workers exit; scancel / qdel the jobs
```

`submit` refuses a spool with a `stop` file left in it (every worker would
exit at once); `--clear-stop` removes it.

## The parent as a batch job

When the login node may not run the stage, submit the parent as a job of its
own, after the workers:

```sh
#!/bin/bash
#SBATCH --cpus-per-task=2 --mem=32G --time=08:00:00
rang-core run config.yaml my.ms
rang-core spool stop /scratch/me/eso137/spool
```

## Lost workers and nodes

A worker keeps a heartbeat file in the spool. When a worker's heartbeat is
older than the lease (60 s), the parent puts its task back in the queue
(at most three runs per task) and another worker runs it; a task never
writes the MS, so a re-run gives the same partial. A worker killed by the
scheduler, or a node that disappears, therefore costs one lease and the
task's time, not the run. Slurm arrays are submitted with `--no-requeue`;
PBS requires array jobs to be rerunnable, so PBS may rerun a lost subjob,
which only adds a worker.

What was tested ({gh}`research/multinode-2.md`): Slurm 24.11 and OpenPBS
clusters in containers on one host, with a worker cancelled and a node
killed in each stage, bit-identical to one process; a one-node Slurm cluster
in CI. Not tested: a real site's shared filesystem (NFS, Lustre, CephFS
attribute caching and clock skew between nodes delay heartbeats), site
limits on array size, and Torque.
