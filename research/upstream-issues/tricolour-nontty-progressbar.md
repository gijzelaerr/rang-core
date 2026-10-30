# Tricolour: every non-interactive run waits up to 300 s for its progress bar

PR (task U2): **none, by maintainer direction.** sjperkins replied that 0.5.0 (no `ProgressBar`)
is about to be released and 0.2.x PRs are not wanted; the fix exists on `0.5.0-dev` (b01ac8f,
confirmed: no `ProgressBar` in `src/`).

Repository: ratt-ru/tricolour. Status: **filed 2026-10-30, https://github.com/ratt-ru/tricolour/issues/110**.
Checked 2026-10-30 on Tricolour 0.2.1 (PyPI; `master` 7514d81 has the same `app.py` lines),
dask 2026.8.0, Python 3.12. The 0.5.0-dev rework (b01ac8f) no longer uses `ProgressBar`.
Origin: the 300.01 s native runs in [flagging-caracal.md](../flagging-caracal.md) and
[core-d-tricolour.md](../core-d-tricolour.md), section 5.

<!-- issue-title: Non-interactive runs wait up to 5 minutes for the dask ProgressBar to finish -->
<!-- issue-body -->
**Describe the bug**
When stdout is not a TTY (containers, CARACal, batch jobs), `tricolour/apps/tricolour/app.py` (line 514 on `master`, the code in 0.2.1) enters `ProgressBar(minimum=1, dt=5*60)`. dask's `ProgressBar._finish` sets `_running = False` and then joins the timer thread, which is inside `time.sleep(dt)`. The compute therefore cannot return until the next 300 s tick: every non-interactive run takes at least 300 s, and its wall time is rounded up to a multiple of 300 s. The final bar also reports that inflated time as the duration.

On a small MeerKAT calibrator scan (140 rows x 4096 channels) each run took 302 s, while the same strategy steps take about 2 s with a warm Numba cache.

**To Reproduce**
The same context manager around a 1 s task, with stdout piped:
```python
import sys, time, dask
from dask.diagnostics import ProgressBar
print("dask", dask.__version__, "isatty", sys.stdout.isatty(), flush=True)
t0 = time.perf_counter()
with ProgressBar(minimum=1, dt=5 * 60):
    dask.delayed(time.sleep)(1.0).compute()
print(f"wall {time.perf_counter() - t0:.1f} s for a 1.0 s task", flush=True)
```
`python repro.py | cat` prints:
```
dask 2026.8.0 isatty False
[########################################] | 100% Completed | 300.00 s
wall 300.0 s for a 1.0 s task
```
**Expected behaviour**
The run ends when the flagging ends; the log is still throttled.

**Suggested fix**
Keep a short `dt` and throttle the printing instead, e.g. a small `ProgressBar` subclass whose `_update_bar` only draws when 300 s have passed since the last draw, or drop the progress bar when stdout is not a TTY. I see that the 0.5.0-dev rework no longer uses `ProgressBar`; this is for the 0.2.x line that CARACal and other pipelines install today.
<!-- end-issue-body -->
