"""E2 flag probe: Tricolour 0.2.1 on one extracted scan group, as its app does
(`tricolour -fs polarisation -dc DATA`, apps/tricolour/app.py and
strat_executor.py), with the window flags kept after each strategy step.
Runs inside rang-tricolour:0.2.1-e1:

    python e2_flagprobe_tricolour.py GROUP.npz STRATEGY.yaml OUT.npz [all]

By default only the probed baseline's rows (GROUP.npz `probe`) are flagged;
`all` flags the whole group. OUT.npz holds `stages` (step, bl, time, chan) for
the probed baseline, `flags` (its rows' final row flags, any corr) and
`ubl`.
"""

import sys
import time

import dask
import dask.array as da
import numpy as np
from tricolour.apps.tricolour.app import load_config
from tricolour.dask_wrappers import (
    apply_static_mask,
    flag_autos,
    flag_nans_and_zeros,
    polarised_intensity,
    sum_threshold_flagger,
    uvcontsub_flagger,
)
from tricolour.mask import collect_masks, load_mask
from tricolour.packing import pack_data, unique_baselines, unpack_data
from tricolour.stokes import stokes_corr_map


def strategies_run(
    flag_windows, vis_windows, ubl, antspos, chan_freq, chan_width, masks, strategies
):
    """strat_executor.StrategyExecutor.apply_strategies, keeping each step."""
    original = flag_windows.copy()
    stages = []
    for strategy in strategies:
        task = strategy["task"]
        kw = strategy.get("kwargs", {})
        if task == "sum_threshold":
            new = sum_threshold_flagger(vis_windows, flag_windows, **kw)
            flag_windows = da.logical_or(new, flag_windows)
        elif task == "uvcontsub_flagger":
            flag_windows = uvcontsub_flagger(vis_windows, flag_windows, **kw)
        elif task == "flag_autos":
            flag_windows = da.logical_or(flag_autos(flag_windows, ubl), flag_windows)
        elif task == "combine_with_input_flags":
            flag_windows = da.logical_or(flag_windows, original)
        elif task == "unflag":
            flag_windows = da.zeros_like(flag_windows)
        elif task == "flag_nans_zeros":
            flag_windows = flag_nans_and_zeros(vis_windows, flag_windows)
        elif task == "apply_static_mask":
            new = apply_static_mask(
                flag_windows, ubl, antspos, masks, chan_freq, chan_width, **kw
            )
            if kw["accumulation_mode"].strip() == "or":
                flag_windows = da.logical_or(new, flag_windows)
            else:
                flag_windows = new
        else:
            raise ValueError(task)
        flag_windows = flag_windows.persist()
        stages.append(flag_windows)
    return flag_windows, stages


def main():
    group, strategy, out = sys.argv[1:4]
    whole = len(sys.argv) > 4 and sys.argv[4] == "all"
    dask.config.set(scheduler="single-threaded")
    g = np.load(group)
    _scan, a1, a2 = g["probe"]
    if whole:
        rows = np.arange(len(g["time"]))
    else:
        rows = np.flatnonzero((g["antenna1"] == a1) & (g["antenna2"] == a2))
    GD = load_config(strategy)
    masks = [load_mask(fn, dilate=False) for fn in collect_masks()]
    vis = da.from_array(g["data"][rows], chunks=(10000, -1, -1))
    flags = da.from_array(g["flag_in"][rows], chunks=(10000, -1, -1))
    antenna1 = da.from_array(g["antenna1"][rows], chunks=10000)
    antenna2 = da.from_array(g["antenna2"][rows], chunks=10000)
    times = da.from_array(g["time"][rows], chunks=10000)
    corr_type = g["corr_type"].tolist()
    stokes_map = stokes_corr_map(corr_type)
    stokes_pol = tuple(v for k, v in stokes_map.items() if k != "I")
    vis = polarised_intensity(vis, stokes_pol)
    flags = da.any(flags, axis=2, keepdims=True)
    ubl = unique_baselines(antenna1, antenna2)
    utime, time_inv = da.unique(times, return_inverse=True)
    utime, ubl = dask.compute(utime, ubl)
    ubl = ubl.view(np.int32).reshape(-1, 2)
    bl_range = np.arange(ubl.shape[0], dtype=ubl.dtype)[:, None]
    ubl = np.concatenate([bl_range, ubl], axis=1)
    probe = int(np.flatnonzero((ubl[:, 1] == a1) & (ubl[:, 2] == a2))[0])
    ubl_d = da.from_array(ubl, chunks=(16, 3))
    vis_w, flag_w = pack_data(
        time_inv, ubl_d, antenna1, antenna2, vis, flags, utime.shape[0]
    )
    t0 = time.perf_counter()
    final, stages = strategies_run(
        flag_w,
        vis_w,
        ubl_d,
        g["antenna_position"],
        g["chan_freq"],
        g["chan_width"],
        masks,
        GD["strategies"],
    )
    unpacked = unpack_data(antenna1, antenna2, time_inv, ubl_d, final)
    rowflags = (da.sum(unpacked, axis=2, keepdims=True) > 0)[..., 0].compute()
    seconds = time.perf_counter() - t0
    st = np.stack([np.asarray(s[probe, 0].compute()) for s in stages])
    vis_probe = np.asarray(vis_w[probe, 0].compute())
    sel = np.flatnonzero((g["antenna1"][rows] == a1) & (g["antenna2"][rows] == a2))
    np.savez(
        out,
        stages=st,
        flags=rowflags[sel],
        ubl=ubl,
        vis=vis_probe,
        seconds=seconds,
        rows=len(rows),
        names=np.array([s["task"] for s in GD["strategies"]]),
    )
    print(
        "tricolour",
        "all" if whole else "baseline",
        "rows",
        len(rows),
        "seconds",
        round(seconds, 1),
        "flagged",
        int(rowflags[sel].sum()),
    )


if __name__ == "__main__":
    main()
