# Tricolour: an integer `spike_width_time` compiles the SumThreshold kernel twice

Repository: ratt-ru/tricolour. Status: **to be filed** (URL recorded here once filed).
Checked 2026-10-30 on Tricolour 0.2.1 (PyPI), Numba 0.60.0, NumPy 2.0.2, Python 3.12;
`master` 7514d81 and 0.5.0-dev b01ac8f have the same `default.yaml` line and kernels.
Origin: the 39 s second compilation in [core-d-tricolour.md](../core-d-tricolour.md), section 5.
Also checked, not raised: `uvcontsub_flagger` masks the whole window once per
baseline-correlation (`vis_scratch[result_flags] = np.nan` inside the `cp` loop), so its cost
grows quadratically with the window (0.9 to 2.7 ms per baseline from 32 to 256 baselines), but
the default `--baseline-chunks 16` keeps windows small.

<!-- issue-title: Integer spike_width_time in the default strategy triggers a second Numba compilation (about 28-39 s) -->
<!-- issue-body -->
**Describe the bug**
`sum_threshold_flagger` passes `spike_width_time` and `spike_width_freq` unchanged into the jitted `_get_flags_impl`. The shipped `tricolour/conf/default.yaml` (line 102, also `src/tricolour/conf/default_config.yaml` on 0.5.0-dev) gives `spike_width_time: 2` as an integer while the other steps use floats, so Numba compiles a second specialisation of the kernel within the same run. Strategies derived from it inherit the integer: all of CARACal's MeerKAT Tricolour strategies (`mk_rfi_flagging_*` and `calibrator_*_flagging.yaml`) have the same `spike_width_time: 2` step. With a cold cache this costs 28 s below and took 39 s in a full strategy run in a container; a warm cache hides it, but fresh containers and CI pay it every time.

**To Reproduce**
```python
import time, numpy as np, numba
from importlib.metadata import version
from tricolour.flagging import sum_threshold_flagger, _get_flags_impl
print("tricolour", version("tricolour"), "numba", numba.__version__)
rng = np.random.default_rng(0)
vis = (rng.normal(size=(1, 1, 64, 256)) + 0j).astype(np.complex64)
flags = np.zeros(vis.shape, np.bool_)
for swt in (6.5, 6.5, 2, 2.0):
    t0 = time.perf_counter()
    sum_threshold_flagger(vis, flags, spike_width_time=swt, num_major_iterations=1)
    print(f"spike_width_time={swt!r:5}: {time.perf_counter() - t0:7.2f} s, "
          f"_get_flags_impl signatures: {len(_get_flags_impl.signatures)}")
```
With an empty `NUMBA_CACHE_DIR`:
```
tricolour 0.2.1 numba 0.60.0
spike_width_time=6.5  :   50.77 s, _get_flags_impl signatures: 1
spike_width_time=6.5  :    0.00 s, _get_flags_impl signatures: 1
spike_width_time=2    :   28.15 s, _get_flags_impl signatures: 2
spike_width_time=2.0  :    0.00 s, _get_flags_impl signatures: 2
```
**Expected behaviour**
One specialisation per run: the parameters are documented as floats.

**Suggested fix**
Cast the float-valued arguments in `sum_threshold_flagger` (`spike_width_time`, `spike_width_freq`, and for the same reason `outlier_nsigma`, `background_reject`, `rho` and the two `flag_all_*_frac`) with `float(...)` before calling `_get_flags_impl`, which also covers user strategy files; and write `2.0` in `default.yaml`.

**Minor, same area**
`uvcontsub_flagger` calls `np.nanmean(..., axis=0)` on windows with fully flagged channels, so NumPy emits `RuntimeWarning: Mean of empty slice` once per baseline-correlation and major cycle (256 warnings for 256 baselines and one flagged channel, one cycle). The NaN result is already handled by the next line; wrapping the call in `warnings.catch_warnings()` with that warning ignored would keep logs readable.
<!-- end-issue-body -->
