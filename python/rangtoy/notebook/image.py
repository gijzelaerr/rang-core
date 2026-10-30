"""Briggs weights, dirty image and PSF on the core, and comparisons.

`image` composes the same calls as `core_campaign.image_arm` (gain
correction, WSClean's Stokes I reader, imaging weights, w-stacking
inversion, `image_metrics`) but returns arrays instead of writing FITS, and
takes the weighting, robustness and geometry as arguments. Autocorrelation
rows get zero weight.
"""

from __future__ import annotations

import numpy as np

from .. import core_grid, core_weights
from ..core_policy import protected_flags
from ..core_workflow import gain_grid
from . import _plot

DEFAULTS = {
    "width": 512,
    "height": 512,
    "scale_arcsec": 8.0,
    "w_layers": 64,
    "kernel_size": 7,
    "oversampling": 1023,
    "padding": 1.2,
}
MODES = ("natural", "uniform", "briggs")


def corrected_data(ds, sol):
    """G_p^-1 V G_q^-H with the solve's gains (`core_campaign.apply_gains`);
    returns the data and the mask of cells whose two gains are valid."""
    from ..core_campaign import apply_gains

    p = sol["params"]
    time_map, freq_map, _, _ = gain_grid(
        ds.state, p["time_interval"], p["freq_interval"]
    )
    return apply_gains(
        ds.state["data"],
        sol["diagnostics"]["gains"],
        sol["diagnostics"]["gain_valid"],
        ds.state["antenna1"],
        ds.state["antenna2"],
        time_map,
        freq_map,
    )


def image(ds, sol=None, added=None, mode="briggs", robust=0.5, **geometry):
    """Dirty image and PSF of one flag set.

    `sol`: a `gains.solve` result to image corrected data (its `added`
    flags are used unless `added` is given); None images the raw DATA.
    `added`: extra (row, chan) flags on top of the original ones. Returns
    `dirty`, `psf`, `metrics` (`core_campaign.image_metrics`: peak, PSF
    sidelobes, off-source RMS, point-source residual RMS), the reader and
    imaging weights, and the parameters.
    """
    from ..core_campaign import image_metrics

    s, e = ds.state, ds.extra
    params = {**DEFAULTS, **geometry}
    if added is None:
        added = sol["added"] if sol is not None else np.zeros_like(s["train"])
    final, final_rows = protected_flags(
        s["original_flags"],
        s["original_rows"],
        np.broadcast_to(np.asarray(added, bool)[..., None], s["original_flags"].shape),
    )
    if sol is not None:
        data, ok = corrected_data(ds, sol)
        final = final | ~ok[..., None]
    else:
        data = s["data"]
    autos = s["antenna1"] == s["antenna2"]
    sample, weight = core_grid.stokes_i_reader(
        data, s["weights"], final, flag_rows=final_rows | autos
    )
    padded_w = core_weights.padded_size(params["width"], params["padding"])
    padded_h = core_weights.padded_size(params["height"], params["padding"])
    imaging = core_weights.imaging_weights(
        e["uvw"],
        core_weights.wsclean_wavelengths(s["frequencies"]),
        weight,
        ~autos,
        mode=mode,
        robust=robust,
        width=padded_w,
        height=padded_h,
        pixel_scale=core_weights.pixel_scale_radians(params["scale_arcsec"]),
        return_grid=False,
    )
    products = core_grid.invert(
        e["uvw"], s["frequencies"], sample, weight, imaging["weights"], **params
    )
    imaged = weight > 0
    model_i = np.real(s["model"][..., 0] + s["model"][..., 3]) * 0.5
    model_flux = float(model_i[imaged].mean()) if imaged.any() else None
    metrics = image_metrics(products["dirty"], products["psf"], model_flux)
    metrics["imaged cells"] = int(imaged.sum())
    metrics.update({f"weights: {k}": v for k, v in imaging["sums"].items()})
    return {
        "dirty": products["dirty"],
        "psf": products["psf"],
        "metrics": metrics,
        "reader_weights": weight,
        "imaging_weights": imaging["weights"],
        "stats": products["stats"],
        "params": {
            "mode": mode,
            "robust": robust,
            "corrected": sol is not None,
            **params,
        },
    }


def _show(ax, values, scale_arcsec, title, zoom=None, cmap="inferno", symmetric=False):
    h, w = values.shape
    half = (zoom or w) // 2
    cy, cx = h // 2, w // 2
    cut = values[cy - half : cy + half, cx - half : cx + half]
    r = half * scale_arcsec / 60.0
    limit = np.abs(cut).max() if symmetric else None
    image = ax.imshow(
        cut,
        origin="lower",
        extent=(r, -r, -r, r),
        cmap=cmap,
        vmin=-limit if symmetric else None,
        vmax=limit,
    )
    ax.set_title(title, fontsize="medium")
    ax.set_xlabel("RA offset (arcmin)")
    return image


def image_figure(img, zoom=128):
    """Dirty image and PSF side by side (central `zoom` pixels)."""
    fig, axes = _plot.figure(1, 2, width=10, height=4.3)
    scale = img["params"]["scale_arcsec"]
    m = img["metrics"]
    a = _show(
        axes[0, 0],
        img["dirty"],
        scale,
        f"dirty: peak {m['peak_jy_per_beam']:.3f} Jy/beam",
        zoom,
    )
    fig.colorbar(a, ax=axes[0, 0], label="Jy/beam")
    b = _show(
        axes[0, 1],
        img["psf"],
        scale,
        f"PSF ({img['params']['mode']}, robust {img['params']['robust']})",
        zoom,
        cmap="RdBu_r",
        symmetric=True,
    )
    fig.colorbar(b, ax=axes[0, 1])
    axes[0, 0].set_ylabel("Dec offset (arcmin)")
    return fig


def compare(img_a, img_b, labels=("A", "B"), zoom=128, which="dirty"):
    """Two images of the same quantity and their difference (A - B)."""
    fig, axes = _plot.figure(1, 3, width=14, height=4.2)
    scale = img_a["params"]["scale_arcsec"]
    for ax, img, label in zip(axes[0], (img_a, img_b), labels):
        im = _show(ax, img[which], scale, f"{label}: {which}", zoom)
        fig.colorbar(im, ax=ax)
    diff = img_a[which] - img_b[which]
    im = _show(
        axes[0, 2],
        diff,
        scale,
        f"{labels[0]} - {labels[1]} (max |diff| {np.abs(diff).max():.2e})",
        zoom,
        cmap="RdBu_r",
        symmetric=True,
    )
    fig.colorbar(im, ax=axes[0, 2])
    axes[0, 0].set_ylabel("Dec offset (arcmin)")
    return fig


METRIC_COLUMNS = (
    "peak_jy_per_beam",
    "flux_recovery",
    "psf_max_outside_offsource_box",
    "offsource_rms",
    "residual_rms",
    "imaged cells",
)


def metrics_table(images):
    """The image metrics the campaigns compare, one row per image."""
    import pandas as pd

    return pd.DataFrame(
        {
            label: {k: img["metrics"].get(k) for k in METRIC_COLUMNS}
            for label, img in images.items()
        }
    ).T


def uv_coverage(ds, ax=None):
    """uv tracks in kilo-wavelengths at the band centre (both signs)."""
    e, s = ds.extra, ds.state
    cross = s["antenna1"] != s["antenna2"]
    lam = 299_792_458.0 / np.median(s["frequencies"])
    uv = e["uvw"][cross, :2] / lam / 1e3
    if ax is None:
        fig, axes = _plot.figure(width=4.5, height=4.5)
        ax = axes[0, 0]
    else:
        fig = ax.figure
    ax.plot(uv[:, 0], uv[:, 1], ".", ms=2)
    ax.plot(-uv[:, 0], -uv[:, 1], ".", ms=2, color="C1")
    ax.set_aspect("equal")
    ax.set_xlabel("u (kλ)")
    ax.set_ylabel("v (kλ)")
    ax.set_title(f"{int(cross.sum())} cross rows, {len(ds.baselines())} baselines")
    return fig


def weights_figure(ds, img, max_points=20000):
    """Imaging weight per visibility against uv distance: natural weighting
    is flat, uniform downweights dense uv cells, Briggs interpolates."""
    s, e = ds.state, ds.extra
    lam = 299_792_458.0 / s["frequencies"]
    radius = np.hypot(e["uvw"][:, 0], e["uvw"][:, 1])[:, None] / lam[None] / 1e3
    w = img["imaging_weights"]
    keep = img["reader_weights"] > 0
    r, v = radius[keep], w[keep]
    if len(r) > max_points:
        pick = np.random.default_rng(0).choice(len(r), max_points, replace=False)
        r, v = r[pick], v[pick]
    fig, axes = _plot.figure(width=6, height=3.2)
    axes[0, 0].plot(r, v / max(v.max(), 1e-30), ".", ms=1, alpha=0.4)
    axes[0, 0].set_xlabel("uv distance (kλ)")
    axes[0, 0].set_ylabel("imaging weight (normalised)")
    axes[0, 0].set_title(
        f"{img['params']['mode']} weighting, robust {img['params']['robust']}"
    )
    return fig


def robust_sweep(ds, sol=None, robusts=(-2.0, -1.0, 0.0, 0.5, 1.0, 2.0), **geometry):
    """Briggs robustness against PSF sidelobe, off-source RMS and residual RMS."""
    import pandas as pd

    rows = []
    for robust in robusts:
        m = image(ds, sol, mode="briggs", robust=robust, **geometry)["metrics"]
        rows.append({"robust": robust, **{k: m.get(k) for k in METRIC_COLUMNS}})
    return pd.DataFrame(rows).set_index("robust")
