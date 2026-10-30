"""WSClean imaging weights and Stokes I on the Rang core (research/core-b-weighting.md).

Ports WSClean 3.6's Briggs, uniform and natural weighting (padded half-plane
weight grid, rank filter, nearest-cell lookup) and its Stokes I formation from
XX/YY. Calls the extension `rangtoy._core` (research/core-j-packaging.md,
research/p7-architecture.md). Geometry defaults are rang's imaging
settings: 512 pixels at 8 arcsec, padding 1.2, rank filter 3.0 over 16 cells.
"""

import numpy as np

from . import core

CLASSES = {"natural": 0, "uniform": 1, "briggs": 2}
DEFAULT_PADDING = 1.2
DEFAULT_RANK_FILTER = (3.0, 16)
SPEED_OF_LIGHT = 299792458


def padded_size(trimmed, padding=DEFAULT_PADDING):
    """WSClean's padded image size for `-size trimmed` (an even number)."""
    return int(core.extension().padded_size(int(trimmed), float(padding)))


def pixel_scale_radians(arcsec):
    """`-scale <arcsec>asec` as WSClean's angle parser evaluates it."""
    return float(arcsec) * np.pi / (180.0 * 60.0 * 60.0)


def wsclean_wavelengths(frequency_hz):
    """Channel wavelengths as `aocommon::BandData` computes them: the speed of
    light divided by the frequency in `long double`, rounded to float64.
    `np.longdouble` is the x86 80-bit type on the hosts this runs on."""
    freq = np.asarray(frequency_hz, dtype=np.longdouble)
    return (np.longdouble(SPEED_OF_LIGHT) / freq).astype(np.float64)


def grid_shape(width, height, super_weight=1.0):
    """The weight grid's (width, height) after the super weight."""
    ext = core.extension()
    status, *shape = ext.weight_grid_shape(int(width), int(height), float(super_weight))
    if status:
        raise ValueError("positive super weight required")
    return int(shape[0]), int(shape[1])


def stokes_i(data, weights, flags):
    """Stokes I visibilities and weights from four-correlation cells.

    `data` is complex64 `(..., 4)` in XX, XY, YX, YY order, `weights` float32
    and `flags` bool of the same shape. Returns complex64 and float32 arrays
    of shape `data.shape[:-1]`, following WSClean's `-pol I` rules exactly.
    """
    data = np.ascontiguousarray(data, dtype=np.complex64)
    weights = np.ascontiguousarray(weights, dtype=np.float32)
    flags = np.ascontiguousarray(flags, dtype=np.uint8)
    if data.shape[-1] != 4 or weights.shape != data.shape or flags.shape != data.shape:
        raise ValueError("data, weights and flags with four correlations required")
    shape = data.shape[:-1]
    ncell = int(np.prod(shape, dtype=np.int64))
    vis = np.zeros(shape, dtype=np.complex64)
    weight = np.zeros(shape, dtype=np.float32)
    ext = core.extension()
    code = ext.stokes_i(
        ncell,
        data.view(np.float32),
        weights,
        flags,
        vis.view(np.float32),
        weight,
    )
    if code:
        raise RuntimeError(f"core Stokes I failed with code {code}")
    return vis, weight


def imaging_weights(
    uvw,
    wavelength,
    weights,
    row_selected,
    mode="briggs",
    robust=0.5,
    width=None,
    height=None,
    pixel_scale=None,
    super_weight=1.0,
    rank_filter=DEFAULT_RANK_FILTER,
    return_grid=True,
):
    """WSClean imaging weights for every row and channel.

    `uvw` is `(nrow, 3)` metres, `wavelength` `(nchan,)` metres (see
    `wsclean_wavelengths`), `weights` the `(nrow, nchan)` Stokes I visibility
    weights (zero where flagged) and `row_selected` the `(nrow,)` mask of rows
    WSClean images (field, cross-correlations, data description). `width` and
    `height` are the padded image size and `pixel_scale` is in radians; the
    defaults are rang's 512-pixel, 8-arcsec image. Returns a dict with
    `weights` (float32, `(nrow, nchan)`), `sums` (visibility weight sum, total
    weight, max gridded weight, count) and, unless `return_grid` is false, the
    finished half-plane `grid` as float64 `(height // 2, width)`.
    """
    if mode not in CLASSES:
        raise ValueError(f"mode must be one of {sorted(CLASSES)}")
    width = padded_size(512) if width is None else int(width)
    height = padded_size(512) if height is None else int(height)
    pixel_scale = (
        pixel_scale_radians(8.0) if pixel_scale is None else float(pixel_scale)
    )
    uvw = np.ascontiguousarray(uvw, dtype=np.float64)
    wavelength = np.ascontiguousarray(wavelength, dtype=np.float64)
    weights = np.ascontiguousarray(weights, dtype=np.float32)
    selected = np.ascontiguousarray(row_selected, dtype=np.uint8)
    nrow, nchan = weights.shape
    if (
        uvw.shape != (nrow, 3)
        or wavelength.shape != (nchan,)
        or selected.shape != (nrow,)
    ):
        raise ValueError("uvw (nrow, 3), wavelength (nchan,), weights (nrow, nchan)")
    level, size = rank_filter if rank_filter is not None else (0.0, 0)
    out = np.zeros((nrow, nchan), dtype=np.float32)
    sums = np.zeros(4, dtype=np.float64)
    grid_w, grid_h = grid_shape(width, height, super_weight)
    grid = np.zeros((grid_h // 2, grid_w), dtype=np.float64) if return_grid else None
    ext = core.extension()
    code = ext.imaging_weights(
        nrow,
        nchan,
        uvw,
        wavelength,
        weights,
        selected,
        CLASSES[mode],
        float(robust),
        width,
        height,
        pixel_scale,
        pixel_scale,
        float(super_weight),
        float(level),
        int(size),
        out,
        grid,
        sums,
    )
    if code:
        raise RuntimeError(f"core imaging weights failed with code {code}")
    result = {
        "weights": out,
        "sums": {
            "visibility_weight_sum": float(sums[0]),
            "total_weight": float(sums[1]),
            "max_gridded_weight": float(sums[2]),
            "count": int(sums[3]),
        },
    }
    if grid is not None:
        result["grid"] = grid
    return result


def weight_sums(weights, imaging):
    """WSClean's header sums (`WSCVWSUM`, `WSCIMGWG`, `WSCNVIS`) for given
    visibility and imaging weights, computed as `ApplyWeights` does."""
    weights = np.ascontiguousarray(weights, dtype=np.float32).ravel()
    imaging = np.ascontiguousarray(imaging, dtype=np.float32).ravel()
    if weights.shape != imaging.shape:
        raise ValueError("weights and imaging weights must match")
    cum = weights * imaging
    has = cum != 0
    return {
        "visibility_weight_sum": float(np.sum(weights[has].astype(np.float64))),
        "total_weight": float(np.sum(cum.astype(np.float64))),
        "max_gridded_weight": float(cum.max(initial=0.0)),
        "count": int(has.sum()),
    }
