# Check a branch: quick check, push, CI

For: any agent session that changed code on a branch and needs to know it
passes. Ends in a branch whose CI run is green, and in a coordinator merge
check that is the one full local check the change gets. Background and
measurements: `research/speedup-tools.md`.

On the development host about eight sessions share one 16-thread machine
through the heavy lock (`tools/heavy_lock.py`). A full local check holds 8
slots for 20-50 min; the same tests on GitHub's runners cost the host nothing
and, on this public repository, cost nothing either (standard GitHub-hosted
runners are free for public repositories, per GitHub's Actions billing page).
So a session lets CI run the tests and keeps the host for what CI cannot do.

## 1. Quick check before pushing

```sh
python tools/check_all.py --quick
```

Any Python 3.10+ starts it, from PowerShell, cmd or Git Bash. It takes the
heavy lock itself (shared, 4 slots, 8 GB), so do not wrap it in another
`heavy_lock.py run`. It runs ruff, ruff format, `git diff --check`, cargo fmt,
clippy with warnings as errors, the root and core Rust tests, the extension
build into this worktree's `.venv` (created with `uv` if missing), pytest on
the test files the diff against `origin/main` touches, and the gain-hash gate.
It leaves out the two `gpu` steps. The log is
`outputs/check/<UTC time>-quick.log`, and the last line says
`check_all: PASS` or `check_all: FAIL`.

The wrapper also fixes the set-up faults that used to fail checks:
`RANG_ARCHIVE_OUTPUTS` mangled by Git Bash, or unset (`rang.check` repairs it,
or defaults to the WSL checkout's outputs when that exists); target
directories built by another rustc (E0514); and an outer `VIRTUAL_ENV` that
would receive the extension instead of this worktree's venv.

## 2. Push the branch and read CI

```sh
git push -u origin <branch>
gh run list --branch <branch> --workflow tests --limit 3
gh run watch <run-id> --exit-status
```

Never force-push. `tests.yml` runs on every push to a branch other than `main`
(and on pull requests): lint, clippy, the Rust tests, and pytest on Linux and
Windows against the branch's extension. A later push to the same branch
cancels the run still in progress. On failure, read the failing job with
`gh run view <run-id> --log-failed`, fix, run the quick check, and push again.

## 3. The gates CI lacks

CI has no archives and no oracles (CASA, QuartiCal, WSClean), so the gain-hash
gate and the oracle tests skip there. The quick check already runs the
gain-hash gate. If the change touches an oracle-gated path (calibration
solvers, imaging kernels, MS writing), either run the full check:

```sh
python tools/check_all.py
```

(8 slots, 12 GB, every step, log `outputs/check/<UTC time>-full.log`), or say
in the hand-back that it is left to the coordinator's merge check. The
coordinator runs one full check per merge, so a session does not need its own
on top of it.

## 4. The heavy lock's priority lane

`heavy_lock.py run --priority critical` puts a ticket ahead of every normal
ticket. It never preempts a running job: a critical exclusive ticket still
waits for the shared jobs to finish, and every normal ticket waits behind it.
It is only for the release's critical path (the E2 and E3 acceptance runs),
when the coordinator says so. Checks, builds, timing runs and everything else
queue normal. `python tools/heavy_lock.py status` shows the lane of each
waiting ticket.
