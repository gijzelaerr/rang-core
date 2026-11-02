# pfb-imaging 0.0.11: kclean stops on the TBB threading layer in a plain venv

Repository: ratt-ru/pfb-imaging. Status: **not filed (U4, 2026-11-02): reproduced on 0.0.11, but
`kclean` no longer exists on `main`** (4cbbf625; README: the legacy `init`, `grid`, `kclean`,
`sara`, `fluxtractor` pipeline "was removed in 0.1.0"). Issues are skipped when already fixed,
so this stays here for the owner's say.

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
