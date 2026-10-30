"""Rank first: which gain bins can the data identify, and why not.

The identifiability survey of research/flagging-luno-support.md, on any
four-station dataset. For every gain bin of the solution grid it builds the
32 x 32 real normal matrix of the full-Jones problem from the bin's cells
(`flagging_influence.training_normals`, Rust), counts its rank, compares it
with the `8 * active - 4` that a scalar (unpolarized) model can reach, and
asks the native gauge-aware step (`anchored_response`) for its status code.

Why `8 * active - 4`: each active station has a 2 x 2 complex gain, 8 real
numbers. A scalar model leaves G_p -> G_p U (U in U(2), 4 real numbers)
invisible, so at most 8n - 4 directions are constrained. Fewer means some
gain combination is not fixed by the data at all.
"""

from __future__ import annotations

import numpy as np

from . import _plot

CUTOFF = 1e-10
RANDOM_SEED = 20261029
STATUS = {
    0: (
        "identified",
        "full curvature has the expected rank; the gauge-fixed step is solvable",
    ),
    1: ("invalid block", "non-finite or malformed normal block"),
    2: ("native panic", "the Rust kernel caught a panic (a bug, never expected)"),
    3: (
        "underidentified",
        (
            "full curvature has rank below 8*active-4: some gain direction is "
            "not constrained by the data (typically a tree-shaped baseline graph)"
        ),
    ),
    4: (
        "retained rank loss",
        (
            "the curvature left after removing the dropped cells has lost rank; "
            "with drop_h = full_h (the frozen LUNO crosscheck) that is every bin"
        ),
    ),
    5: ("non-PSD curvature", "the normal matrix is not positive semi-definite"),
    6: (
        "U(2) gauge-null mismatch",
        (
            "the null space is not the common-U(2) gauge: the model is not scalar "
            "(e.g. cross-hand MODEL_DATA terms), so the unpolarized gauge does not apply"
        ),
    ),
}
LABELS = ("identified", "underidentified", "over-rank", "no data")


def status_table():
    """The native status codes, as a teaching table."""
    import pandas as pd

    return pd.DataFrame(
        [{"code": k, "name": v[0], "meaning": v[1]} for k, v in STATUS.items()]
    ).set_index("code")


def _cells(ds, cells):
    s = ds.state
    if cells == "train":
        return s["train"]
    if cells == "eligible":
        return s["eligible"]
    raise ValueError("cells must be 'eligible' (all clean cross cells) or 'train'")


def gain_point(nbins, point="identity", nant=4):
    """The gain point the normals are evaluated at: identity, or the
    fixed-seed random point I + 0.1 (N + iN) of the LUNO survey."""
    identity = np.broadcast_to(np.eye(2), (nbins, nant, 2, 2)).astype(np.complex128)
    if point == "identity":
        return np.ascontiguousarray(identity)
    if point == "random":
        noise = np.random.default_rng(RANDOM_SEED).standard_normal(
            (nbins, nant, 2, 2, 2)
        )
        return identity + 0.1 * (noise[..., 0] + 1j * noise[..., 1])
    raise ValueError("point must be identity or random")


def is_tree(active, edges):
    """True when the baseline graph on the active stations is connected and
    has no cycle (edges == stations - 1)."""
    stations = sorted(active)
    if not stations:
        return False
    parent = {a: a for a in stations}

    def root(a):
        while parent[a] != a:
            a = parent[a]
        return a

    for p, q in edges:
        parent[root(p)] = root(q)
    connected = len({root(a) for a in stations}) == 1
    return connected and len(edges) == len(stations) - 1


def identifiability(
    ds,
    grid=(2, 32),
    cells="eligible",
    point="identity",
    cutoff=CUTOFF,
    crosscheck="corrected",
):
    """One row per gain bin: support, rank, required rank, label, native status.

    `cells="eligible"` is the survey's TRAIN definition (every clean cross
    cell: unflagged, positive weights, finite model, no holdout);
    `cells="train"` uses the solve's training split only. `crosscheck`:
    "corrected" calls `anchored_response(H, 0, 0, 0)` (the original survey's
    call); "frozen" repeats the LUNO protocol's `(H, 0, H, 0)`, which
    returns status 4 on every identified bin (post-hoc correction in
    research/flagging-luno-support.md).
    """
    import pandas as pd

    from ..core_influence import anchored_response, training_normals

    s = ds.state
    nant = len(ds.names)
    if nant != 4:
        raise ValueError("the native normals are written for four stations")
    mask = _cells(ds, cells) & np.isfinite(s["model"]).all(-1)
    integration = np.unique(s["times"], return_inverse=True)[1]
    nchan = s["data"].shape[1]
    ntb = int(integration.max()) // grid[0] + 1
    nfb = (nchan + grid[1] - 1) // grid[1]
    nbins = ntb * nfb
    rows, chans = np.nonzero(mask)
    bins = (integration[rows] // grid[0]) * nfb + chans // grid[1]
    p, q = s["antenna1"][rows], s["antenna2"][rows]
    models = s["model"][rows, chans].astype(np.complex128).reshape(-1, 2, 2)
    weights = s["weights"][rows, chans].astype(np.float64)
    gains = gain_point(nbins, point, nant)
    h, _, counts = training_normals(
        gains, models, np.zeros_like(models), weights, p, q, bins
    )
    centres = s["frequencies"][
        np.minimum(np.arange(nfb) * grid[1] + grid[1] // 2, nchan - 1)
    ]
    order = np.argsort(bins, kind="stable")
    starts = np.searchsorted(bins[order], np.arange(nbins + 1))
    records = []
    zeros_h, zeros_b = np.zeros((32, 32)), np.zeros(32)
    for b in range(nbins):
        record = {
            "bin": b,
            "time bin": b // nfb,
            "freq bin": b % nfb,
            "freq (MHz)": float(centres[b % nfb] / 1e6),
            "cells": int(counts[b]),
        }
        if not counts[b]:
            record.update(
                label="no data",
                rank=0,
                required=0,
                active=(),
                edges=(),
                tree=False,
                status=None,
                reason="no cells in this bin",
            )
            records.append(record)
            continue
        members = order[starts[b] : starts[b + 1]]
        edges = tuple(
            sorted({(int(x), int(y)) for x, y in zip(p[members], q[members])})
        )
        active = np.zeros(nant, bool)
        for x, y in edges:
            active[x] = active[y] = True
        eig = np.linalg.eigvalsh(h[b])
        rank = int(np.sum(eig > cutoff * eig[-1])) if eig[-1] > 0 else 0
        required = 8 * int(active.sum()) - 4
        label = (
            "identified"
            if rank == required
            else "underidentified"
            if rank < required
            else "over-rank"
        )
        drop_h = h[b] if crosscheck == "frozen" else zeros_h
        native = anchored_response(h[b], zeros_b, drop_h, zeros_b, gains[b], active)
        status = int(native["native_status"])
        record.update(
            label=label,
            rank=rank,
            required=required,
            active=tuple(int(a) for a in np.flatnonzero(active)),
            edges=edges,
            tree=is_tree(np.flatnonzero(active), edges),
            status=status,
            reason=STATUS.get(status, ("?", ""))[0],
        )
        records.append(record)
    table = pd.DataFrame(records).set_index("bin")
    table["status"] = table["status"].astype("Int64")
    table.attrs.update(
        grid=tuple(grid),
        shape=(ntb, nfb),
        cells=cells,
        point=point,
        crosscheck=crosscheck,
        cutoff=cutoff,
    )
    return table


def rank_summary(table):
    """Bin and cell counts per label, and whether the native status agrees
    (status 3 exactly on underidentified bins)."""
    supported = table[table["label"] != "no data"]
    agree = (
        (supported["status"] == 3) == (supported["label"] == "underidentified")
    ).sum()
    out = {f"{label} bins": int((table["label"] == label).sum()) for label in LABELS}
    out.update(
        {
            "bins": len(table),
            "bins with data": len(supported),
            "identified cells": int(
                table.loc[table["label"] == "identified", "cells"].sum()
            ),
            "underidentified cells": int(
                table.loc[table["label"] == "underidentified", "cells"].sum()
            ),
            "native status counts": {
                int(k): int(v)
                for k, v in supported["status"].value_counts().sort_index().items()
            },
            "status 3 agrees with rank label": f"{int(agree)}/{len(supported)}",
            "underidentified bins that are trees": int(
                table.loc[table["label"] == "underidentified", "tree"].sum()
            ),
        }
    )
    return out


def failure_shapes(table):
    """Underidentified and over-rank bins grouped by baseline graph: the
    mechanism is visible in the edge lists (a tree has no odd cycle)."""
    bad = table[table["label"].isin(["underidentified", "over-rank"])]
    if bad.empty:
        import pandas as pd

        return pd.DataFrame(
            columns=["label", "edges", "rank", "required", "bins", "cells"]
        )
    return (
        bad.groupby(["label", "edges", "rank", "required"])
        .agg(bins=("cells", "size"), cells=("cells", "sum"))
        .reset_index()
        .sort_values("bins", ascending=False)
    )


def rank_map(table, ax=None):
    """Time bin x frequency bin map of the labels."""
    from matplotlib.colors import ListedColormap

    ntb, nfb = table.attrs["shape"]
    codes = (
        table["label"]
        .map({k: i for i, k in enumerate(LABELS)})
        .to_numpy()
        .reshape(ntb, nfb)
    )
    freqs = table["freq (MHz)"].to_numpy()[:nfb]
    if ax is None:
        fig, axes = _plot.figure(width=10, height=2.2 + 0.25 * ntb)
        ax = axes[0, 0]
    else:
        fig = ax.figure
    colours = ListedColormap(["#2ca02c", "#d62728", "#9467bd", "0.85"])
    ax.imshow(
        codes,
        aspect="auto",
        cmap=colours,
        vmin=-0.5,
        vmax=3.5,
        extent=_plot.extent(freqs, np.arange(ntb)),
        interpolation="nearest",
    )
    from matplotlib.patches import Patch

    ax.legend(
        handles=[
            Patch(color=colours(i), label=label) for i, label in enumerate(LABELS)
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.25),
        ncols=4,
        fontsize="small",
    )
    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("time bin")
    g = table.attrs["grid"]
    ax.set_title(
        f"identifiability per gain bin ({g[0]} integrations x {g[1]} channels)"
    )
    return fig


def support_graph(ds, table, bins, ax=None):
    """Draw the baseline graph of one or more bins on the four stations, with
    rank against the requirement. A tree (no cycle) cannot fix full-Jones
    gains; adding the edge that closes a triangle can."""
    bins = [bins] if np.isscalar(bins) else list(bins)
    positions = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], float)
    if ax is None:
        fig, axes = _plot.figure(1, len(bins), width=2.8 * len(bins), height=3)
        axes = axes[0]
    else:
        fig, axes = ax.figure, [ax]
    for panel, b in zip(axes, bins):
        row = table.loc[b]
        for x, y in row["edges"]:
            panel.plot(*positions[[x, y]].T, "-", color="k", lw=2)
        for a, name in enumerate(ds.names):
            on = a in row["active"]
            panel.plot(*positions[a], "o", ms=14, color="#1f77b4" if on else "0.8")
            panel.annotate(
                name,
                positions[a],
                xytext=(0, -18 if positions[a][1] == 0 else 12),
                textcoords="offset points",
                ha="center",
                fontsize="small",
            )
        colour = {"identified": "#2ca02c", "underidentified": "#d62728"}.get(
            row["label"], "#9467bd"
        )
        panel.set_title(
            f"bin {b}: rank {row['rank']}/{row['required']}\n{row['label']}"
            f"{' (tree)' if row['tree'] else ''}",
            color=colour,
            fontsize="medium",
        )
        panel.set_xlim(-0.35, 1.35)
        panel.set_ylim(-0.4, 1.4)
        panel.set_axis_off()
    return fig


def example_bins(table):
    """One bin of each support shape worth drawing: an identified bin and the
    most common underidentified shapes."""
    picks = []
    good = table[table["label"] == "identified"]
    if not good.empty:
        picks.append(int(good.index[0]))
    shapes = failure_shapes(table)
    for edges in shapes["edges"].head(3) if not shapes.empty else []:
        match = table[table["edges"] == edges]
        picks.append(int(match.index[0]))
    return picks


def archived_luno_support(point="identity"):
    """The frozen LUNO survey's 1934-638 counts (results/meerkat-luno-support.json)."""
    from .experiment import load_archive

    record = load_archive("meerkat-luno-support.json")["groups"]["1"]["points"][point]
    return {k: v for k, v in record.items() if not isinstance(v, list)}
