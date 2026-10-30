"""W-stacking gridder of the Rang core (research/core-c-gridder.md).

The Rust module ports WSClean 3.6-1's `WStackingGridder` inversion path. This
wrapper adds what WSClean's Measurement Set reader does before gridding
(`stokes_i_reader`), calls the core (`invert`) and writes FITS images in
WSClean's pixel orientation (`write_fits`). Briggs weighting is task B's; the
imaging weights are an input here. The core is reached through the extension
`rangtoy._core` (research/core-j-packaging.md, research/p7-architecture.md).
"""

import math

import numpy as np

from . import core

ARCSEC = math.pi / (180.0 * 3600.0)
N_STATS = 8
STAT_NAMES = (
    "image_weight",
    "gridded_count",
    "visibility_weight_sum",
    "max_gridded_weight",
    "min_w",
    "max_w",
    "psf_normalization",
    "n_w_layers",
)


def kernel(kernel_size=7, oversampling=1023):
    """The oversampled Kaiser-Bessel windowed sinc, as WSClean builds it."""
    out = np.empty(kernel_size * oversampling, np.float64)
    ext = core.extension()
    code = ext.grid_kernel(kernel_size, oversampling, out)
    if code:
        raise ValueError("invalid kernel settings")
    return out


def kernel_reference(kernel_size=7, oversampling=1023, alpha=8.6):
    """Direct NumPy transcription of `makeKaiserBesselKernel` (criterion 6)."""

    def bessel0(x, precision=1e-8):
        d, ds, total = 0.0, 1.0, 1.0
        while True:
            d += 2.0
            ds *= x * x / (d * d)
            total += ds
            if ds <= total * precision:
                return total

    n = kernel_size * oversampling
    mid = n // 2
    ratio = 1.0 / oversampling
    sinc = np.empty(mid + 1)
    sinc[0] = ratio
    x = np.arange(1, mid + 1, dtype=float)
    sinc[1:] = np.sin(math.pi * ratio * x) / (math.pi * x)
    norm = oversampling / bessel0(alpha)
    out = np.empty(n)
    for i in range(mid + 1):
        term = i / mid
        out[mid + i] = sinc[i] * bessel0(alpha * math.sqrt(1.0 - term * term)) * norm
    out[:mid] = out[n - 1 : n - 1 - mid : -1]
    return out


def stokes_i_reader(data, weight_spectrum, flags, flag_rows=None):
    """What WSClean's reader hands the gridder for `-pol I` on XX,XY,YX,YY.

    `data`, `weight_spectrum` and `flags` are `(nrow, nchan, 4)`. Returns the
    Stokes sample `(XX + YY) / 2` as complex64 (zero where not finite) and the
    weight `4 min(w_XX, w_YY)` as float32, zero where either correlation is
    flagged or not finite, and zero on rows with `flag_rows` set.
    """
    data = np.asarray(data, np.complex64)
    weight_spectrum = np.asarray(weight_spectrum, np.float32)
    flags = np.asarray(flags, bool)
    if (
        data.shape != weight_spectrum.shape
        or data.shape != flags.shape
        or data.shape[-1] != 4
    ):
        raise ValueError(
            "four-correlation data, weights and flags of one shape required"
        )
    xx, yy = data[..., 0], data[..., 3]
    sample = (xx + yy) * np.float32(0.5)
    sample = np.where(np.isfinite(sample), sample, np.complex64(0)).astype(np.complex64)
    good_xx = ~flags[..., 0] & np.isfinite(xx)
    good_yy = ~flags[..., 3] & np.isfinite(yy)
    w_xx = weight_spectrum[..., 0] * np.float32(4.0)
    w_yy = weight_spectrum[..., 3] * np.float32(4.0)
    weight = np.where(good_xx & good_yy, np.minimum(w_xx, w_yy), np.float32(0)).astype(
        np.float32
    )
    if flag_rows is not None:
        weight[np.asarray(flag_rows, bool)] = 0.0
    return sample, weight


def invert(
    uvw,
    frequencies,
    data,
    weights,
    imaging_weights,
    width=512,
    height=512,
    scale_arcsec=8.0,
    w_layers=64,
    kernel_size=7,
    oversampling=1023,
    padding=1.2,
):
    """Dirty image and PSF, `(height, width)` arrays in FITS pixel order, with
    WSClean's counters. `data` is the complex64 Stokes sample per (row,
    channel), `weights` the reader weight and `imaging_weights` WSClean's
    per-channel imaging weight. The grid is `padding` times larger than the
    image and trimmed afterwards, as WSClean does by default."""
    uvw = np.ascontiguousarray(uvw, np.float64)
    frequencies = np.ascontiguousarray(frequencies, np.float64)
    data = np.ascontiguousarray(data, np.complex64)
    weights = np.ascontiguousarray(weights, np.float32)
    imaging_weights = np.ascontiguousarray(imaging_weights, np.float32)
    nrow, nchan = data.shape
    if uvw.shape != (nrow, 3) or frequencies.shape != (nchan,):
        raise ValueError("uvw must be (nrow, 3) and frequencies (nchan,)")
    if weights.shape != (nrow, nchan) or imaging_weights.shape != (nrow, nchan):
        raise ValueError("weights must match data")
    dirty = np.empty((height, width), np.float64)
    psf = np.empty((height, width), np.float64)
    stats = np.empty(N_STATS, np.float64)
    data_view = data.view(np.float32)
    ext = core.extension()
    code = ext.grid_invert(
        nrow,
        nchan,
        width,
        height,
        kernel_size,
        oversampling,
        w_layers,
        scale_arcsec * ARCSEC,
        scale_arcsec * ARCSEC,
        float(padding),
        uvw,
        frequencies,
        data_view,
        weights,
        imaging_weights,
        dirty,
        psf,
        stats,
    )
    if code:
        raise RuntimeError(f"core gridder failed with code {code}")
    record = dict(zip(STAT_NAMES, (float(v) for v in stats)))
    record["gridded_count"] = int(record["gridded_count"])
    record["n_w_layers"] = int(record["n_w_layers"])
    return {"dirty": dirty, "psf": psf, "stats": record}


def wcs_header(phase_dir_rad, width, height, scale_arcsec, frequencies):
    """FITS keywords in WSClean's convention for a SIN image at the phase
    centre; the frequency axis spans the channel edges."""
    ra = math.degrees(phase_dir_rad[0])
    if ra > 180.0:
        ra -= 360.0
    dec = math.degrees(phase_dir_rad[1])
    frequencies = np.asarray(frequencies, float)
    step = frequencies[1] - frequencies[0] if len(frequencies) > 1 else 0.0
    low, high = frequencies[0] - step / 2, frequencies[-1] + step / 2
    scale = scale_arcsec / 3600.0
    return {
        "BUNIT": "JY/BEAM",
        "BTYPE": "Intensity",
        "EQUINOX": 2000.0,
        "LONPOLE": 180.0,
        "CTYPE1": "RA---SIN",
        "CRPIX1": width / 2 + 1,
        "CRVAL1": ra,
        "CDELT1": -scale,
        "CUNIT1": "deg",
        "CTYPE2": "DEC--SIN",
        "CRPIX2": height / 2 + 1,
        "CRVAL2": dec,
        "CDELT2": scale,
        "CUNIT2": "deg",
        "CTYPE3": "FREQ",
        "CRPIX3": 1.0,
        "CRVAL3": (low + high) / 2,
        "CDELT3": high - low,
        "CUNIT3": "Hz",
        "CTYPE4": "STOKES",
        "CRPIX4": 1.0,
        "CRVAL4": 1.0,
        "CDELT4": 1.0,
        "SPECSYS": "TOPOCENT",
    }


def write_fits(path, image, header, extra=None):
    """Write a `(height, width)` image as a 4-axis float32 FITS file in the
    same pixel order WSClean uses (row y, column x; no flip)."""
    from astropy.io import fits

    image = np.asarray(image, np.float32)
    hdu = fits.PrimaryHDU(image[np.newaxis, np.newaxis, :, :])
    for key, value in header.items():
        hdu.header[key] = value
    hdu.header["ORIGIN"] = "Rang core gridder"
    for key, value in (extra or {}).items():
        hdu.header[key] = value
    hdu.writeto(str(path), overwrite=False)
