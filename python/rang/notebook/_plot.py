"""Shared plotting conventions: bare `Figure` objects, no pyplot state.

A `matplotlib.figure.Figure` made without pyplot is never shown twice by
Jupyter and works headless (scripts, tests, CI) with no backend choice.
Unsupported or flagged cells are drawn grey, never as low values
(research/flagging.md: "Unsupported bins are grey in plots").
"""

import numpy as np

BAD = "0.82"
NEW = "#d62728"
REMOVED = "#1f77b4"


def figure(nrows=1, ncols=1, *, width=None, height=None, squeeze=False, **kwargs):
    from matplotlib.figure import Figure

    width = width or 4.2 * ncols
    height = height or 3.2 * nrows
    fig = Figure(figsize=(width, height), layout="constrained")
    axes = fig.subplots(nrows, ncols, squeeze=squeeze, **kwargs)
    return fig, axes


def cmap(name, bad=BAD):
    import matplotlib

    return matplotlib.colormaps[name].with_extremes(bad=bad)


def masked(values, invalid):
    return np.ma.masked_array(values, mask=np.asarray(invalid, bool))


def extent(xs, ys):
    """imshow extent for cell centres xs (columns) and ys (rows)."""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    dx = (xs[1] - xs[0]) if len(xs) > 1 else 1.0
    dy = (ys[1] - ys[0]) if len(ys) > 1 else 1.0
    return (xs[0] - dx / 2, xs[-1] + dx / 2, ys[-1] + dy / 2, ys[0] - dy / 2)
