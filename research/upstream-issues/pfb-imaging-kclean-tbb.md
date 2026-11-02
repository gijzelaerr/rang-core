# pfb-imaging 0.0.11: kclean stops on the TBB threading layer

Repository: ratt-ru/pfb-imaging. Status: **filed 2026-11-02 (U4), https://github.com/ratt-ru/pfb-imaging/issues/391**. Held back at first because `kclean` is gone on
`main`; filed against 0.0.x on the owner's approval, relayed by the coordinator, 2026-11-02. Rerun on
0.0.11 the same day (`outputs/u4-20261102-04/logs/pfb-tbb-order.log`).

<!-- issue-title: 0.0.x: kclean fails with "No threading layer could be loaded" because set_num_threads runs before set_envs -->
<!-- issue-body -->
This is against the 0.0.x line: `kclean` is gone on `main` (4cbbf625), so this only matters if another 0.0.x release is planned, and it can be closed otherwise.

In pfb-imaging 0.0.11 (numba 0.68.1, tbb 2023.2.0, Python 3.12, fresh uv venv), `pfb kclean` stops with:

```
core/kclean.py:77   set_num_threads(nthreads)
ValueError: No threading layer could be loaded.
HINT: Intel TBB is required, try: $ conda/pip install tbb
```

The cause is the call order in `core/kclean.py`: `numba.set_num_threads` at line 77 runs before `set_envs` at line 78, and `set_envs` is what loads the wheel's `libtbb.so` with `ctypes`. Importing `pfb_imaging` has already set `NUMBA_THREADING_LAYER=tbb`, so numba needs the library at line 77.

```python
from pfb_imaging import set_envs
from numba import set_num_threads

set_num_threads(2)   # ValueError, as above
set_envs(2, 2)
```

With the two calls swapped there is no error. Setting `LD_LIBRARY_PATH=<venv>/lib` also gets `pfb kclean` through, to exit 0 on a simulated field. Swapping lines 77 and 78 should be the whole fix; I tested that order in the script above, not in `kclean` itself.
<!-- /issue-body -->

Measured, correcting DF5-O's wording (a plain venv is not the cause by itself):

- `pfb kclean` on the DF5-O field in a fresh uv venv: exit 1, `ValueError: No threading layer
  could be loaded`, raised from `core/kclean.py:77`
  (`outputs/u4-20261102-01/logs/pfb-kclean-plain.log`). With `LD_LIBRARY_PATH=<venv>/lib`: exit 0.
- `core/kclean.py` calls `numba.set_num_threads` (line 77) before `set_envs` (line 78), and
  `set_envs` is what loads the wheel's `libtbb.so` with `ctypes`.
- [../u4-upstream-files/pfb_repro_tbb_order.py](../u4-upstream-files/pfb_repro_tbb_order.py): in
  kclean's order the same `ValueError`; with the two calls swapped, no error. A parallel region
  after `set_envs` selects `tbb` with no `LD_LIBRARY_PATH`
  ([../u4-upstream-files/pfb_repro_tbb.py](../u4-upstream-files/pfb_repro_tbb.py)).

So the fix on the 0.0.x line would be to swap those two lines. Not checked: whether
`utils/stokes2im.py:229` on `main`, which calls `set_num_threads` in a worker, has an equivalent
order problem; `main` has rewritten `set_envs` around `_load_tbb`.
