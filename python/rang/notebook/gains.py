"""Solve full-Jones gains on the core and look at amplitude, phase and TV.

`solve` is `core_workflow.core_solve` (the Rust port of QuartiCal's
`complex` solver plus the fused residual/loss pass, research/core-phase2.md)
with the solution intervals and iteration cap as arguments. The holdout
split stays the one the dataset was loaded with: it reserves training cells
on the (2, 32) grid, so other intervals can leave a held-out cell without a
valid gain, which the losses then report as an invalid prediction instead of
dropping it.
"""

from __future__ import annotations

import numpy as np

from ..core_workflow import core_solve, gain_grid
from . import _plot
from .data import CORRELATIONS

GAUGE_NOTE = (
    "Full-Jones gains on an unpolarized calibrator are only defined up to a "
    "common unitary matrix: G_p -> G_p U for every antenna leaves every "
    "model visibility G_p M G_q^H unchanged when M is a multiple of the "
    "identity. Raw per-entry phases (and the XY/YX split) are therefore not "
    "physical. Rang fixes the right unitary gauge on a reference antenna "
    "(polar decomposition G_ref = H U, every antenna times U^H) before "
    "computing TV; |G|_F, G_p G_q^H and TV in that gauge are what can be "
    "compared. A polarized model breaks this symmetry and needs gauge='raw'."
)
QUANTITIES = ("amplitude", "phase", "tv")


def solve(
    ds,
    added=None,
    time_interval=2,
    freq_interval=32,
    iterations=50,
    gauge="polar",
    scale=None,
):
    """One core solve. Returns a dict with `metrics`, `tv`, `residuals`,
    `guidance`, `diagnostics`, `added` and the `params` used."""
    s = ds.state
    added = np.zeros_like(s["train"]) if added is None else np.asarray(added, bool)
    metrics, tv, residuals, guidance, diagnostics = core_solve(
        s,
        added,
        int(time_interval),
        int(freq_interval),
        int(iterations),
        scale=scale,
        gauge=gauge,
        trial=f"t{time_interval}-f{freq_interval}-i{iterations}",
    )
    return {
        "label": metrics["trial"],
        "added": added,
        "metrics": metrics,
        "tv": tv,
        "residuals": residuals,
        "guidance": guidance,
        "diagnostics": diagnostics,
        "params": {
            "time_interval": int(time_interval),
            "freq_interval": int(freq_interval),
            "iterations": int(iterations),
            "gauge": gauge,
        },
    }


def losses_table(solutions):
    """Held-out losses and solver state for one solve or a dict of them.

    MSE is the inverse-variance weighted squared residual per cell, on the
    fixed train / validation / test cells; None means at least one held-out
    cell had no valid gain (counted in `invalid`).
    """
    import pandas as pd

    if "metrics" in solutions:
        solutions = {solutions["label"]: solutions}
    rows = []
    for label, sol in solutions.items():
        m = sol["metrics"]
        rows.append(
            {
                "solve": label,
                "train MSE": m["losses"]["train"],
                "validation MSE": m["losses"]["validation"],
                "test MSE": m["losses"]["test"],
                "invalid (val/test)": f"{m['invalid_predictions']['validation']}"
                f"/{m['invalid_predictions']['test']}",
                "TV (gauge)": m["tv"],
                "TV (raw)": m["raw_tv"],
                "valid gain fraction": m["valid_gain_fraction"],
                "iterations": m["solver"]["iterations"],
                "converged fraction": m["solver"]["converged_fraction"],
                "added cells": m["added_count"],
                "core seconds": m["seconds"],
            }
        )
    return pd.DataFrame(rows).set_index("solve")


def _element(element):
    return {"XX": (0, 0), "XY": (0, 1), "YX": (1, 0), "YY": (1, 1)}[element]


def gain_maps(ds, sol, quantity="amplitude", element="XX", gauge=True):
    """Per-antenna time-bin x frequency-bin maps of one Jones element.

    `quantity`: "amplitude", "phase" (degrees) or "tv" (the incident-edge TV
    map the policy uses, element ignored). `gauge=True` shows the
    polar-gauge gains TV is computed on; False shows the raw solver output.
    Invalid solutions (no data, singular reference) are grey.
    """
    d = sol["diagnostics"]
    gains = d["gauge_gains"] if gauge else d["gains"]
    valid = d["tv_valid"] if gauge else d["gain_valid"]
    freqs = d["gain_frequencies"] / 1e6
    times = d["gain_times"] - d["gain_times"][0]
    names = ds.names
    fig, axes = _plot.figure(
        1, len(names), width=3.6 * len(names), height=3.2, sharey=True
    )
    if quantity == "tv":
        values = d["tv_map"]
        label, name, vmin, vmax = (
            "TV map",
            "inferno",
            0,
            np.nanpercentile(values[valid], 99) if valid.any() else 1,
        )
    elif quantity in ("amplitude", "phase"):
        i, j = _element(element)
        entry = gains[..., i, j]
        if quantity == "amplitude":
            values, label, name = np.abs(entry), f"|G_{element}|", "viridis"
            ok = values[valid]
            vmin, vmax = (
                (np.percentile(ok, 1), np.percentile(ok, 99)) if ok.size else (0, 1)
            )
        else:
            values, label, name = (
                np.degrees(np.angle(entry)),
                f"arg G_{element} (deg)",
                "twilight",
            )
            vmin, vmax = -180, 180
    else:
        raise ValueError(f"quantity must be one of {QUANTITIES}")
    box = _plot.extent(freqs, times)
    for a, ax in enumerate(axes[0]):
        image = ax.imshow(
            _plot.masked(values[:, :, a], ~valid[:, :, a]),
            aspect="auto",
            extent=box,
            cmap=_plot.cmap(name),
            vmin=vmin,
            vmax=vmax,
            interpolation="nearest",
        )
        ax.set_title(names[a])
        ax.set_xlabel("frequency (MHz)")
    axes[0, 0].set_ylabel("time bin centre (s)")
    fig.colorbar(image, ax=axes[0, -1], label=label)
    fig.suptitle(
        f"{quantity} ({'polar gauge' if gauge else 'raw'}), "
        f"{sol['params']['time_interval']} int x {sol['params']['freq_interval']} ch bins"
    )
    return fig


def gain_spectra(ds, sol, time_bin=0, gauge=True):
    """Amplitude and phase of the diagonal elements against frequency for one
    time bin, every antenna; gaps are invalid bins."""
    d = sol["diagnostics"]
    gains = d["gauge_gains"] if gauge else d["gains"]
    valid = d["tv_valid"] if gauge else d["gain_valid"]
    freqs = d["gain_frequencies"] / 1e6
    fig, axes = _plot.figure(2, 2, width=11, height=5.5, sharex=True)
    for col, element in enumerate(("XX", "YY")):
        i, j = _element(element)
        for a, name in enumerate(ds.names):
            g = np.where(valid[time_bin, :, a], gains[time_bin, :, a, i, j], np.nan)
            axes[0, col].plot(freqs, np.abs(g), ".-", ms=3, lw=0.8, label=name)
            axes[1, col].plot(freqs, np.degrees(np.angle(g)), ".-", ms=3, lw=0.8)
        axes[0, col].set_title(f"G_{element}, time bin {time_bin}")
        axes[1, col].set_xlabel("frequency (MHz)")
    axes[0, 0].set_ylabel("amplitude")
    axes[1, 0].set_ylabel("phase (deg)")
    axes[0, 0].legend(fontsize="small")
    return fig


def gauge_figure(ds, sol, antenna=1, element="XX"):
    """The unitary-gauge caveat, shown: one antenna's phase spectrum in the raw
    solver output and after the polar gauge, plus |G|_F, which no unitary
    gauge changes (time bin 0)."""
    d = sol["diagnostics"]
    freqs = d["gain_frequencies"] / 1e6
    i, j = _element(element)
    fig, axes = _plot.figure(1, 2, width=11, height=3.2)
    for gains, valid, label in (
        (d["gains"], d["gain_valid"], "raw solver output"),
        (d["gauge_gains"], d["tv_valid"], "polar gauge on m000"),
    ):
        g = np.where(valid[0, :, antenna], gains[0, :, antenna, i, j], np.nan)
        axes[0, 0].plot(freqs, np.degrees(np.angle(g)), ".-", ms=3, lw=0.8, label=label)
        norm = np.where(
            valid[0, :, antenna],
            np.linalg.norm(gains[0, :, antenna], axis=(-1, -2)),
            np.nan,
        )
        axes[0, 1].plot(freqs, norm, ".-", ms=3, lw=0.8, label=label)
    axes[0, 0].set_title(f"{ds.names[antenna]} arg G_{element}: gauge dependent")
    axes[0, 0].set_ylabel("phase (deg)")
    axes[0, 1].set_title(f"{ds.names[antenna]} |G|_F: gauge invariant")
    for ax in axes[0]:
        ax.set_xlabel("frequency (MHz)")
        ax.legend(fontsize="small")
    return fig


def iteration_sweep(ds, caps=(1, 2, 4, 8, 12, 20, 30, 50, 80), **kwargs):
    """Losses, TV and convergence against the iteration cap (S1 found the
    frozen 50-iteration cap is not convergence: research/simplification-review.md)."""
    import pandas as pd

    rows = []
    base = None
    for cap in caps:
        sol = solve(ds, iterations=cap, **kwargs)
        m = sol["metrics"]
        gains = sol["diagnostics"]["gauge_gains"]
        if base is None:
            base = gains
        rows.append(
            {
                "iteration cap": cap,
                "iterations run": m["solver"]["iterations"],
                "converged fraction": m["solver"]["converged_fraction"],
                "validation MSE": m["losses"]["validation"],
                "test MSE": m["losses"]["test"],
                "TV (gauge)": m["tv"],
                "_gains": gains,
            }
        )
    last = rows[-1]["_gains"]
    for row in rows:
        diff = row.pop("_gains") - last
        row["max |G - G_last|"] = float(np.nanmax(np.abs(diff)))
    return pd.DataFrame(rows).set_index("iteration cap")


def plot_sweep(
    table, columns=("validation MSE", "converged fraction", "max |G - G_last|")
):
    """One panel per column of a sweep table against its index."""
    fig, axes = _plot.figure(1, len(columns), width=4 * len(columns), height=3)
    for ax, column in zip(axes[0], columns):
        ax.plot(table.index, table[column], "o-")
        ax.set_xlabel(table.index.name)
        ax.set_title(column)
        if column.startswith("max"):
            ax.set_yscale("log")
    return fig


def residual_waterfall(ds, sol, pair=None):
    """Whitened residual amplitude sqrt(w)|V - G M G^H| (all correlations) on
    one baseline: the evidence the TV policy demands before it flags."""
    from .flags import baseline_cube

    s = ds.state
    pair = pair or ds.baselines()[0]
    whitened = np.sqrt(np.sum(np.abs(sol["residuals"]) ** 2 * s["weights"], axis=-1))
    cube = baseline_cube(ds, pair, whitened)
    used = baseline_cube(ds, pair, s["train"] | s["validation"] | s["test"])
    freqs = s["frequencies"] / 1e6
    t = np.unique(s["times"])
    fig, axes = _plot.figure(width=8, height=3)
    image = axes[0, 0].imshow(
        _plot.masked(cube, ~used | ~np.isfinite(cube)),
        aspect="auto",
        extent=_plot.extent(freqs, t - t[0]),
        cmap=_plot.cmap("magma"),
        interpolation="nearest",
    )
    fig.colorbar(image, ax=axes[0, 0], label="whitened |residual|")
    axes[0, 0].set_title(f"{ds.baseline_label(pair)} residual after the solve")
    axes[0, 0].set_xlabel("frequency (MHz)")
    axes[0, 0].set_ylabel("time (s)")
    return fig


def solution_grid(ds, time_interval, freq_interval):
    """Row and channel bin maps, as the solver and imager use them."""
    return gain_grid(ds.state, time_interval, freq_interval)


__all__ = [
    "CORRELATIONS",
    "GAUGE_NOTE",
    "gain_maps",
    "gain_spectra",
    "gauge_figure",
    "iteration_sweep",
    "losses_table",
    "plot_sweep",
    "residual_waterfall",
    "solution_grid",
    "solve",
]
