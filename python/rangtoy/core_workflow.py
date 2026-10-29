"""Core-native solve for the flagging workflow: no Measurement Set, no subprocess.

`core_solve` returns what `flagging_workflow.solve` returns (metrics, TV
dictionary, residuals, guidance) plus the dictionary that function writes as
`diagnostics.npz`. Gains come from the Rust port of QuartiCal's complex solver
and residuals and split losses from the Rust fused pass (research/core-phase2.md,
research/core-phase1.md). Solve-time flags are the arrays `set_flags` would
write, so the solver sees exactly what QuartiCal saw.
"""

import time

import numpy as np

from . import core
from .flagging import gain_tv, polar_gauge, protected_flags


def solve_flags(state, added, *, holdout=True):
    """The FLAG and FLAG_ROW arrays `flagging_workflow.set_flags` writes."""
    temporary = np.zeros_like(state["original_flags"])
    if holdout:
        temporary |= ~state["train"][..., None]
    temporary |= np.asarray(added, bool)[..., None]
    return protected_flags(state["original_flags"], state["original_rows"], temporary)


def gain_grid(state, time_interval, freq_interval):
    """Row and channel bin maps and the bin centres QuartiCal reports."""
    unique_times, inverse_times = np.unique(state["times"], return_inverse=True)
    time_map = inverse_times // time_interval
    freq_map = np.arange(len(state["frequencies"])) // freq_interval
    times = np.array(
        [
            np.mean(unique_times[i : i + time_interval])
            for i in range(0, len(unique_times), time_interval)
        ]
    )
    freqs = np.array(
        [
            np.mean(state["frequencies"][i : i + freq_interval])
            for i in range(0, len(freq_map), freq_interval)
        ]
    )
    return time_map, freq_map, times, freqs


def core_solve(
    state,
    added,
    time_interval,
    freq_interval,
    iterations,
    *,
    trial="",
    scale=None,
    gauge="polar",
):
    """Mirror of `flagging_workflow.solve` on the Rust core.

    Returns (metrics, tv, residuals, guidance, diagnostics).
    """
    if np.any(np.diff(state["times"]) < 0):
        raise ValueError("rows must be sorted by time, as in the prepared MS")
    flags, rows = solve_flags(state, added)
    time_map, freq_map, gain_times, gain_freqs = gain_grid(
        state, time_interval, freq_interval
    )
    nant = len(state["names"])
    started = time.perf_counter()
    solution = core.solve_complex(
        state["data"],
        state["weights"],
        flags,
        rows,
        state["antenna1"],
        state["antenna2"],
        time_map,
        freq_map,
        ntime_bins=len(gain_times),
        nfreq_bins=len(gain_freqs),
        nant=nant,
        model=state["model"],
        max_iterations=iterations,
    )
    gains = solution.gains
    valid = (solution.flags == 0) & np.isfinite(gains).all(axis=(-1, -2))
    labels = core.split_labels(
        train=state["train"], validation=state["validation"], test=state["test"]
    )
    fused = core.fused_pass(
        state["data"],
        state["weights"],
        state["antenna1"],
        state["antenna2"],
        time_map,
        freq_map,
        gains,
        valid,
        labels,
        model=state["model"],
        scores=False,
        normals=False,
    )
    elapsed = time.perf_counter() - started
    residuals = fused.residuals
    if scale is None:
        scale = float(np.median(np.linalg.norm(gains[valid], axis=(-1, -2))))
    raw_tv = gain_tv(gains, valid, gain_times, gain_freqs, scale=scale)
    if gauge == "polar":
        aligned, tv_valid = polar_gauge(gains, valid)
    elif gauge == "raw":
        aligned, tv_valid = gains, valid
    else:
        raise ValueError("gauge must be polar (unpolarized model) or raw")
    tv = gain_tv(aligned, tv_valid, gain_times, gain_freqs, scale=scale)
    maps = tv["map"]
    p, q = state["antenna1"], state["antenna2"]
    guidance = np.maximum(
        maps[time_map[:, None], freq_map[None], p[:, None]],
        maps[time_map[:, None], freq_map[None], q[:, None]],
    )
    added = np.asarray(added, bool)
    metrics = {
        "trial": trial,
        "seconds": elapsed,
        "tv": tv["total"],
        "raw_tv": raw_tv["total"],
        "time_tv": tv["time"],
        "frequency_tv": tv["frequency"],
        "scale": scale,
        "valid_gain_fraction": float(np.mean(valid)),
        "losses": fused.losses(),
        "invalid_predictions": fused.invalid_predictions(),
        "added_count": int(np.sum(added)),
        "added_fraction": float(np.sum(added) / np.sum(state["train"])),
        "solver": {
            "iterations": solution.iterations,
            "converged_fraction": solution.converged_fraction,
        },
    }
    diagnostics = {
        "gains": gains,
        "gain_valid": valid,
        "tv_valid": tv_valid,
        "gauge_gains": aligned,
        "edges": tv["edges"],
        "tv_map": maps,
        "raw_edges": raw_tv["edges"],
        "guidance": guidance,
        "residuals": residuals,
        "added": added,
        "gain_times": gain_times,
        "gain_frequencies": gain_freqs,
    }
    return metrics, tv, residuals, guidance, diagnostics
