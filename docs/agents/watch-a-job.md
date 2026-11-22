# Watch a running job

For: any agent session, or person, with a job in progress: a `rang-core run`,
a campaign, a training run, a fetch. Ends in a status that comes from the
job's own files and not from memory, in the status file or the hand-back.
Background: `research/live-view-scope.md` (section 9).

Both commands only read. Neither says how far a running stage has got: they
show liveness (a clock, the time since the last file change, the last log
line), not progress.

## 1. A job's directory: `rang-core watch`

```sh
rang-core watch RUN_DIR_OR_OUTPUT_DIR [MORE ...]      # a block on change, a line per tick
rang-core watch --once --json DIR                      # one snapshot, for a script or an agent
rang-core watch --interval 300 DIR >> watch.log        # a trace beside a long job
```

- A run directory (or an MS with `<ms>.rang-run` beside it): each stage's
  status and time, whether its process is still there, receipts.
- A spool directory (`data.spool`): tasks waiting, claimed, done and failed,
  and which workers are live.
- Any other directory, such as a training run's output directory: the newest
  file, its age and the last line of the newest `*.log`.

Read it before saying a job "is running". `process gone` under a stage still
marked `running`, or a last change much older than the job's usual step, means
it has stopped: look at the log before waiting any longer. `unknown (other
host)` and `unknown (other system on this host)` mean the watcher cannot see
that process (a run on nash watched from glacier; a WSL run watched from
Windows): run the command where the job runs, for example
`ssh HOST 'cd CHECKOUT && python -m rang.core_cli watch --once DIR'`.

## 2. The host: `tools/dev_status.py`

```sh
python tools/dev_status.py [DIR ...]
```

One screen for the development host: the heavy lock with booked slots against
real CPU use and the queue, the GPU bookings of `~/.gpu`, the status files of
this checkout and its worktrees with their age (`LATE` past 30 minutes), and
`rang-core watch --once` on the directories given.

- A coordinator runs it at every wake, before starting or waiting on anything.
  A hold that books slots at about 0 cores while jobs queue behind it is a
  blocked queue: find the session that owns the hold; do not start more work
  behind it.
- A session with a background task runs it (or `rang-core watch --once` on its
  output directory) when it writes `outputs/status/<task>.md`, and copies the
  last-change line into that file, so the status says what the files show.

## 3. What to report

In a status file or hand-back: the directory, the stage or step, the last
change and its age, the last log line, and whether the process was seen
alive, with the time of the reading. Say "not checked" for what was not read.
