"""Flags, weights and amplitudes per baseline and channel; Tricolour step by step.

Inspection functions read the loaded state. `run_strategy` calls the core's
Tricolour port (`core_flag.flag_rows`, research/core-d-tricolour.md) with the
per-step window flags switched on, so each step's effect can be shown as a
difference between consecutive windows. Nothing here flags anything itself.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from .. import core_flag
from . import _plot
from .data import CORRELATIONS, _search_roots

# A short strategy built from Tricolour's own task list for teaching: it is
# not one of CARACAL's files (those are found by `strategy_library`).
TEACHING_STRATEGY = [
    {"name": "nan_dropouts_flag", "task": "flag_nans_zeros", "kwargs": {}},
    {
        "name": "static_mask",
        "task": "apply_static_mask",
        "kwargs": {"accumulation_mode": "or", "uvrange": ""},
    },
    {"name": "background_flags", "task": "sum_threshold", "kwargs": {}},
    {"name": "flag_autos", "task": "flag_autos", "kwargs": {}},
    {
        "name": "combine_with_input_flags",
        "task": "combine_with_input_flags",
        "kwargs": {},
    },
]
CARACAL_STRATEGIES = {
    "caracal-calibrator-firstpass": "mk_rfi_flagging_calibrator_fields_firstpass.yaml",
    "caracal-calibrator-mild": "calibrator_mild_flagging.yaml",
    "caracal-calibrator-soft": "calibrator_soft_flagging.yaml",
    "caracal-calibrator-secondpass": "mk_rfi_flagging_calibrator_fields_secondpass.yaml",
}
TASK_NOTES = {
    "flag_nans_zeros": "flags cells whose visibility is NaN or exactly zero",
    "apply_static_mask": "flags channels on the MeerKAT static RFI mask "
    "(GSM, GPS, satellites), optionally only within a uv range",
    "sum_threshold": "SumThreshold (Offringa et al. 2010): flags runs of "
    "1, 2, 4, 8 cells whose summed deviation from a smoothed background "
    "exceeds a threshold that falls with run length",
    "uvcontsub_flagger": "fits a polynomial in frequency per time, subtracts "
    "it and flags sigma outliers of the residual",
    "flag_autos": "flags autocorrelation baselines",
    "combine_with_input_flags": "ORs the flags the data came with back in",
    "unflag": "clears every flag (CARACAL ships it commented out)",
}


def find_strategy_dir():
    """`RANG_STRATEGY_DIR`, else the CARACAL strategy inputs under `outputs/`."""
    configured = os.environ.get("RANG_STRATEGY_DIR")
    if configured:
        return Path(configured) if Path(configured).is_dir() else None
    for root in _search_roots():
        candidate = root / "outputs" / "caracal-strategy-inputs-8f7bb363"
        if candidate.is_dir():
            return candidate
    return None


def strategy_library(strategy_dir=None):
    """Strategy name -> step list: the teaching strategy plus every CARACAL
    file found in `strategy_dir` (default `find_strategy_dir()`)."""
    library = {
        "teaching": [dict(s, kwargs=dict(s["kwargs"])) for s in TEACHING_STRATEGY]
    }
    strategy_dir = Path(strategy_dir) if strategy_dir else find_strategy_dir()
    if strategy_dir is not None:
        for name, filename in CARACAL_STRATEGIES.items():
            path = strategy_dir / filename
            if path.is_file():
                library[name] = core_flag.parse_strategy(path.read_text())
    return library


def describe_strategy(strategies):
    """One row per step: name, task, what it does, its non-default kwargs."""
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "step": i,
                "name": s.get("name", ""),
                "task": s["task"],
                "what it does": TASK_NOTES.get(s["task"], ""),
                "kwargs": ", ".join(
                    f"{k}={v}" for k, v in (s.get("kwargs") or {}).items()
                ),
            }
            for i, s in enumerate(strategies)
        ]
    ).set_index("step")


# --- inspection --------------------------------------------------------------


def _corr(correlation):
    return (
        CORRELATIONS.index(correlation)
        if isinstance(correlation, str)
        else int(correlation)
    )


def baseline_cube(ds, pair, values):
    """(integration, channel, ...) array of `values` (row-major) on one
    baseline, NaN or False where a row is missing."""
    s = ds.state
    times = np.unique(s["times"])
    rows = np.flatnonzero((s["antenna1"] == pair[0]) & (s["antenna2"] == pair[1]))
    values = np.asarray(values)
    fill = False if values.dtype == bool else np.nan
    out = np.full((len(times), *values.shape[1:]), fill, dtype=values.dtype)
    out[np.searchsorted(times, s["times"][rows])] = values[rows]
    return out


def waterfall(ds, pair, quantity="amplitude", correlation="XX", flags=None, ax=None):
    """Time x frequency image of one baseline.

    `quantity`: "amplitude" (log10 |V|, flagged cells grey), "phase"
    (degrees), "weight" (WEIGHT_SPECTRUM, flagged grey), "flags" (the given
    or original flags, black flagged). `flags` defaults to the original
    FLAG of the chosen correlation.
    """
    s = ds.state
    c = _corr(correlation)
    if flags is None:
        flags = s["original_flags"][..., c] | s["original_rows"][:, None]
    flags = baseline_cube(ds, pair, np.asarray(flags, bool))
    freqs = s["frequencies"] / 1e6
    t = np.unique(s["times"])
    t = t - t[0]
    if ax is None:
        fig, axes = _plot.figure(width=7, height=3)
        ax = axes[0, 0]
    else:
        fig = ax.figure
    box = _plot.extent(freqs, t)
    if quantity == "flags":
        image = ax.imshow(
            flags,
            aspect="auto",
            extent=box,
            cmap="Greys",
            vmin=0,
            vmax=1,
            interpolation="nearest",
        )
        label = "flagged"
    else:
        if quantity in ("amplitude", "phase"):
            v = baseline_cube(ds, pair, s["data"][..., c])
            if quantity == "amplitude":
                values, label, name = (
                    np.log10(np.maximum(np.abs(v), 1e-12)),
                    "log10 |V| (Jy)",
                    "viridis",
                )
            else:
                values, label, name = np.degrees(np.angle(v)), "phase (deg)", "twilight"
        elif quantity == "weight":
            values = baseline_cube(ds, pair, s["weights"][..., c])
            label, name = "weight", "magma"
        else:
            raise ValueError("quantity must be amplitude, phase, weight or flags")
        shown = _plot.masked(values, flags | ~np.isfinite(values))
        image = ax.imshow(
            shown,
            aspect="auto",
            extent=box,
            cmap=_plot.cmap(name),
            interpolation="nearest",
        )
    ax.figure.colorbar(image, ax=ax, label=label)
    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("time (s)")
    ax.set_title(f"{ds.baseline_label(pair)} {CORRELATIONS[c]} {quantity}")
    return fig


def waterfall_grid(ds, quantity="amplitude", correlation="XX", flags=None):
    """`waterfall` for every cross baseline, one panel each."""
    pairs = ds.baselines()
    ncols = 2
    nrows = (len(pairs) + 1) // ncols
    fig, axes = _plot.figure(nrows, ncols, width=12, height=2.6 * nrows)
    for ax, pair in zip(axes.flat, pairs):
        waterfall(ds, pair, quantity, correlation, flags=flags, ax=ax)
    for ax in axes.flat[len(pairs) :]:
        ax.set_visible(False)
    return fig


def flag_fraction_by_antenna(ds, flags=None):
    """Fraction of cross-correlation cells flagged (any correlation) per
    antenna, and the share that is held out for validation/test."""
    import pandas as pd

    s = ds.state
    cells = (
        (s["original_flags"].any(-1) | s["original_rows"][:, None])
        if flags is None
        else np.asarray(flags, bool)
    )
    if cells.ndim == 3:
        cells = cells.any(-1)
    p, q = s["antenna1"], s["antenna2"]
    rows = []
    for a, name in enumerate(ds.names):
        mine = (p != q) & ((p == a) | (q == a))
        rows.append(
            {
                "antenna": name,
                "cross rows": int(mine.sum()),
                "flagged fraction": float(cells[mine].mean()) if mine.any() else np.nan,
                "train cells": int(s["train"][mine].sum()),
                "validation cells": int(s["validation"][mine].sum()),
                "test cells": int(s["test"][mine].sum()),
            }
        )
    return pd.DataFrame(rows).set_index("antenna")


def flag_fraction_by_channel(ds, flags=None, ax=None):
    """Flagged fraction of cross rows per channel, per antenna and in all,
    with the training window shaded."""
    s = ds.state
    cells = (
        (s["original_flags"].any(-1) | s["original_rows"][:, None])
        if flags is None
        else np.asarray(flags, bool)
    )
    if cells.ndim == 3:
        cells = cells.any(-1)
    p, q = s["antenna1"], s["antenna2"]
    freqs = s["frequencies"] / 1e6
    if ax is None:
        fig, axes = _plot.figure(width=8, height=3)
        ax = axes[0, 0]
    else:
        fig = ax.figure
    cross = p != q
    for a, name in enumerate(ds.names):
        mine = cross & ((p == a) | (q == a))
        ax.plot(freqs, cells[mine].mean(0), lw=0.6, label=name)
    ax.plot(freqs, cells[cross].mean(0), color="k", lw=1.0, label="all")
    window = s.get("window")
    if window is not None and not window.all():
        idx = np.flatnonzero(window)
        ax.axvspan(
            freqs[idx[0]],
            freqs[idx[-1]],
            color="0.9",
            zorder=0,
            label="training window",
        )
    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("flagged fraction")
    ax.set_ylim(-0.02, 1.02)
    ax.legend(fontsize="small", ncols=3)
    return fig


# --- Tricolour step by step --------------------------------------------------


def run_strategy(ds, strategies, masks=None):
    """Run a strategy through the core with every step's window kept.

    Returns the `core_flag.flag_rows` dict plus `input` (the window flags the
    data came with, `(bl, time, chan)`), `present` (which window cells hold
    a row), `strategies`, and `additions_on_train` (train cells the strategy
    flags), as `core_campaign.tricolour_arm` counts them.
    """
    s, e = ds.state, ds.extra
    result = core_flag.flag_rows(
        s["data"],
        s["original_flags"],
        s["antenna1"],
        s["antenna2"],
        s["times"],
        e["antenna_position"],
        s["frequencies"],
        e["chan_width"],
        e["corr_type"],
        strategies,
        masks=masks,
    )
    ubl = result["ubl"]
    lookup = {(int(a), int(b)): i for i, (a, b) in enumerate(ubl)}
    bl = np.array(
        [lookup[(int(a), int(b))] for a, b in zip(s["antenna1"], s["antenna2"])]
    )
    t = result["time_inv"]
    ntime, nchan = int(t.max()) + 1, s["data"].shape[1]
    window = np.zeros((len(ubl), ntime, nchan), bool)
    present = np.zeros((len(ubl), ntime), bool)
    window[bl, t] = s["original_flags"].any(-1)
    present[bl, t] = True
    result["input"] = window
    result["present"] = present
    result["strategies"] = strategies
    result["additions_on_train"] = s["train"] & result["flags"].any(-1)
    return result


def _stage_list(run):
    names = list(run["stages"])
    return names, [run["stages"][n][:, 0] for n in names]


def step_table(run, cross_only=True):
    """Per step: flagged fraction of the window after it, cells it newly
    flags and cells it clears (an `unflag`, or an override static mask).
    Fractions count window cells that hold a row."""
    import pandas as pd

    names, stages = _stage_list(run)
    present = run["present"][..., None] & np.ones(stages[0].shape[-1], bool)
    if cross_only:
        crossbl = run["ubl"][:, 0] != run["ubl"][:, 1]
        present = present & crossbl[:, None, None]
    previous = run["input"]
    rows = [
        {
            "step": "input",
            "task": "(flags the data came with)",
            "flagged fraction": float(previous[present].mean()),
            "newly flagged": 0,
            "cleared": 0,
        }
    ]
    for name, strategy, stage in zip(names, run["strategies"], stages):
        rows.append(
            {
                "step": name,
                "task": strategy["task"],
                "flagged fraction": float(stage[present].mean()),
                "newly flagged": int((stage & ~previous & present).sum()),
                "cleared": int((~stage & previous & present).sum()),
            }
        )
        previous = stage
    return pd.DataFrame(rows).set_index("step")


def step_waterfall(ds, run, step, pair=None):
    """Before, after and the difference of one step on one baseline.

    `step` is an index or a stage name; `pair` defaults to the first cross
    baseline. Red cells are newly flagged by this step, blue cells cleared.
    """
    names, stages = _stage_list(run)
    if not isinstance(step, str):
        step = names[int(step)]
    k = names.index(step)
    before = run["input"] if k == 0 else stages[k - 1]
    after = stages[k]
    pair = pair or ds.baselines()[0]
    b = [tuple(int(x) for x in u) for u in run["ubl"]].index(tuple(pair))
    freqs = ds.state["frequencies"] / 1e6
    t = np.unique(ds.state["times"])
    t = t - t[0]
    box = _plot.extent(freqs, t)
    fig, axes = _plot.figure(1, 3, width=14, height=3.2, sharey=True)
    missing = ~run["present"][b][:, None] & np.ones(len(freqs), bool)
    for ax, image, title in zip(axes[0], (before[b], after[b]), ("before", "after")):
        ax.imshow(
            _plot.masked(image.astype(float), missing),
            aspect="auto",
            extent=box,
            cmap=_plot.cmap("Greys", bad="#fde0c5"),
            vmin=0,
            vmax=1,
            interpolation="nearest",
        )
        ax.set_title(f"{title}: {image[~missing].mean():.1%} flagged")
        ax.set_xlabel("frequency (MHz)")
    diff = np.zeros(after[b].shape)
    diff[after[b] & ~before[b]] = 1
    diff[~after[b] & before[b]] = -1
    from matplotlib.colors import ListedColormap

    axes[0, 2].imshow(
        _plot.masked(diff, missing),
        aspect="auto",
        extent=box,
        cmap=ListedColormap([_plot.REMOVED, "white", _plot.NEW]),
        vmin=-1.5,
        vmax=1.5,
        interpolation="nearest",
    )
    axes[0, 2].set_title(
        f"{step}: +{int((diff > 0).sum())} / -{int((diff < 0).sum())} cells"
    )
    axes[0, 2].set_xlabel("frequency (MHz)")
    axes[0, 0].set_ylabel(f"{ds.baseline_label(pair)}\ntime (s)")
    return fig


def additions_by_antenna(ds, run):
    """Train cells the strategy would add, per antenna (the comparator arm's
    additions in the campaigns)."""
    import pandas as pd

    s = ds.state
    added = run["additions_on_train"]
    p, q = s["antenna1"], s["antenna2"]
    return pd.DataFrame(
        [
            {
                "antenna": name,
                "train cells": int(s["train"][(p == a) | (q == a)].sum()),
                "added by strategy": int(added[(p == a) | (q == a)].sum()),
            }
            for a, name in enumerate(ds.names)
        ]
    ).set_index("antenna")
