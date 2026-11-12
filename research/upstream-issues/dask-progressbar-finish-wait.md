Target: https://github.com/dask/dask/issues
Status: ready to post
Reproduced on: dask 2026.8.0 (latest on PyPI), Python 3.13.16, Windows 11, 2026-11-12; code unchanged on main b4cc5c5
Duplicates checked: search/issues "repo:dask/dask ProgressBar in:title" (13 hits, open and closed; nearest #7371 logger interleaving, #1791 keeps running after exception, #1424 join before start), "ProgressBar dt sleep", "ProgressBar join timer", "ProgressBar _finish", "progress bar sleep"; PRs "ProgressBar" (#8604, #6938, #3669): none about the finish delay

Title: diagnostics.ProgressBar: compute() returns up to `dt` seconds late because _finish joins a thread in time.sleep(dt)
---
`ProgressBar._finish` sets `_running = False` and then joins the timer thread, which is usually inside `time.sleep(self._dt)`. The compute cannot return until that sleep ends, so every compute under the bar is delayed by up to `dt`, and the delay is counted in the printed duration and in `last_duration`.

With the default `dt=0.1` this is invisible. Callers that print rarely (e.g. `dt=300` to keep batch logs short) pay the whole interval: a 1 s task takes 300 s.

Reproduction (dask 2026.8.0, Python 3.13):

```python
import time, dask
from dask.diagnostics import ProgressBar

t0 = time.perf_counter()
with ProgressBar(minimum=1, dt=20):
    dask.delayed(time.sleep)(1.0).compute()
print(f"\nwall {time.perf_counter() - t0:.2f} s for a 1.0 s task")
```

Output:

```
[########################################] | 100% Completed | 20.00 s

wall 20.00 s for a 1.0 s task
```

With `dt=300` the same script takes 300.0 s.

Code (main at b4cc5c573b8548b5b80f198ad02bf02930880e28, `dask/diagnostics/progress.py`):

- lines 108-110: `_finish` sets `self._running = False`, then `self._timer.join()`, then computes `elapsed`.
- lines 123-129: `_timer_func` loops `while self._running: ... time.sleep(self._dt)`.

Suggested fix: replace the flag and the sleep with a `threading.Event`; `_timer_func` loops on `while not self._stop.wait(self._dt)` (or draws, then waits), and `_finish` calls `self._stop.set()` before `join()`. The thread then wakes at once and the reported duration is the compute's.
