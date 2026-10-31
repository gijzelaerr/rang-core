"""Exact gridder and degridder of the Rang core (research/df1-wgridder.md,
research/df2-wgridder-speed.md).

The Rust module `core/src/wgridder.rs` ports ducc0 0.42.0's wgridder
(Arras et al. 2021): `vis2dirty` (visibilities to a dirty image) and
`dirty2vis` (an image to visibilities), f32 and f64, with the
exponential-of-semicircle kernel, w-planes and ducc0's kernel table. The
kernel and grid are chosen by ducc0's cost model evaluated for one thread,
so results do not depend on the thread count (and are bit-identical at any
`RAYON_NUM_THREADS`).

Conventions are rang's direct Fourier transform's: the image is `(nx, ny)`
with the first axis l, pixel `(i, j)` at `l = (i - nx/2) dx`,
`m = (j - ny/2) dy`, `dirty = sum wgt Re[V exp(+2 pi i (u l + v m + w (n-1)))]`
and `V = wgt sum I exp(-2 pi i (...))`. ducc0 gives the same with
`flip_w=True`; `flip_w` here flips w relative to this convention, and
`divide_by_n` defaults to False. `fits_image` gives WSClean's FITS
orientation and normalisation (research/df1-wgridder.md, item 0).

Since DF2a the data and weights are passed to the core as they are
(complex64 or complex128, float32 or float64, read in place and converted
exactly as NumPy's cast would), and `dirty_psf` grids a dirty image and its
PSF in one pass (`fits_image` uses it).

Since DF2b (research/df2b-wgrid.md) the extension `rang._core` binds the
`_ex` entry points (`wgridder_vis2dirty_f64` etc.) and every call goes
through it; `fits_image` and `dirty_psf` also take the imaging weight
separately (`imaging_weights` / `wgt2`, float32), multiplied by the reader
weight in the core (bit-identical to passing the float32 product). Task W4-3
(research/w4-3-kernels.md) removed the ctypes fallback and its standalone
build (`RANG_DF1_LIB`, `core/target/df1-standalone`).
"""

import numpy as np

from . import core

N_INFO = 14
INFO_NAMES = (
    "kernel_index",
    "supp",
    "nu",
    "nv",
    "nplanes",
    "nvis",
    "wmin_d",
    "wmax_d",
    "nm1min",
    "nm1max",
    "nshift",
    "dw",
    "wmin",
    "ofactor",
)
ARCSEC = np.pi / (180.0 * 3600.0)
# Kinds of the `_ex` entry points (ffi_wgridder.rs).
VIS_KIND = {np.dtype(np.complex64): 1, np.dtype(np.complex128): 2}
WGT_KIND = {np.dtype(np.float32): 1, np.dtype(np.float64): 2}


def extension():
    """The extension module that runs the gridder (`rang._core`)."""
    return core.extension()


def backend():
    """ "extension" (recorded in receipts; the ctypes path is gone)."""
    return "extension"


def library_path():
    """The binary the gridder runs in: the extension."""
    return core.library_path()


def _options(npix_x, npix_y, pixsize_x, pixsize_y, epsilon, kw):
    """The 18 gridder options as floats, in the order of `WgridderOptions`
    (ffi_wgridder.rs), as the extension takes them."""
    kernel = kw.pop("kernel", None)
    opts = (
        int(npix_x),
        int(npix_y),
        float(pixsize_x),
        float(pixsize_y),
        float(epsilon),
        float(kw.pop("center_x", 0.0)),
        float(kw.pop("center_y", 0.0)),
        float(kw.pop("sigma_min", 1.1)),
        float(kw.pop("sigma_max", 2.6)),
        int(bool(kw.pop("do_wgridding", True))),
        int(bool(kw.pop("divide_by_n", False))),
        int(bool(kw.pop("flip_u", False))),
        int(bool(kw.pop("flip_v", False))),
        int(bool(kw.pop("flip_w", False))),
        int(bool(kw.pop("allow_nshift", True))),
        -1 if kernel is None else int(kernel[0]),
        0 if kernel is None else int(kernel[1]),
        0 if kernel is None else int(kernel[2]),
    )
    if kw:
        raise TypeError(f"unexpected options {sorted(kw)}")
    return [float(v) for v in opts]


def _check(status):
    if status == 0:
        return
    if status == 1:
        raise ValueError(extension().wgridder_last_error())
    raise RuntimeError(f"core gridder failed with status {status}")


def _coords(uvw, freq):
    uvw = np.ascontiguousarray(uvw, np.float64)
    freq = np.ascontiguousarray(freq, np.float64)
    if uvw.ndim != 2 or uvw.shape[1] != 3 or freq.ndim != 1:
        raise ValueError("uvw must be (nrow, 3) and freq (nchan,)")
    return uvw, freq, (uvw.shape[0], freq.shape[0])


def _borrow_weights(wgt, mask, shape):
    """Weights as given when float32 or float64 (contiguous; the core reads
    them in place, any other dtype is cast to float64); the mask as uint8."""
    if wgt is not None:
        wgt = np.asarray(wgt)
        if wgt.dtype not in WGT_KIND:
            wgt = wgt.astype(np.float64)
        wgt = np.ascontiguousarray(wgt)
        if wgt.shape != shape:
            raise ValueError("wgt must be (nrow, nchan)")
    if mask is not None:
        mask = np.ascontiguousarray(mask, np.uint8)
        if mask.shape != shape:
            raise ValueError("mask must be (nrow, nchan)")
    return wgt, mask


def _borrow_vis(vis, shape):
    vis = np.asarray(vis)
    if vis.dtype not in VIS_KIND:
        vis = vis.astype(np.complex128)
    vis = np.ascontiguousarray(vis)
    if vis.shape != shape:
        raise ValueError("visibility arrays must be (nrow, nchan)")
    return vis


def _two_weights(wgt, wgt2, shape):
    """`wgt2` (the imaging weight) beside a float32 `wgt`: both float32 and
    contiguous, multiplied in the core. Any other dtype pair falls back to
    NumPy's product (the same value the core would form for float32)."""
    if wgt2 is None:
        return wgt, None
    wgt2 = np.asarray(wgt2)
    if wgt is None:
        raise ValueError("wgt2 needs wgt")
    if wgt.dtype == np.float32 and wgt2.dtype == np.float32:
        wgt2 = np.ascontiguousarray(wgt2)
        if wgt2.shape != shape:
            raise ValueError("wgt2 must be (nrow, nchan)")
        return wgt, wgt2
    return np.ascontiguousarray(wgt * wgt2), None


def _gridding(
    uvw, freq, vis, wgt, mask, npix, pix, epsilon, single, outputs, kw, wgt2=None
):
    """Call `vis2dirty_ex2` for `outputs`, a subset of ("dirty", "psf")."""
    uvw, freq, shape = _coords(uvw, freq)
    vis = _borrow_vis(vis, shape)
    wgt, mask = _borrow_weights(wgt, mask, shape)
    wgt, wgt2 = _two_weights(wgt, wgt2, shape)
    opts = _options(npix[0], npix[1], pix[0], pix[1], epsilon, dict(kw))
    real = np.float32 if single else np.float64
    images = {name: np.empty((int(npix[0]), int(npix[1])), real) for name in outputs}
    info = np.empty(N_INFO, np.float64)
    fn = getattr(extension(), f"wgridder_vis2dirty_{'f32' if single else 'f64'}")
    status = fn(
        opts,
        uvw,
        freq,
        vis,
        wgt,
        wgt2,
        mask,
        images.get("dirty"),
        images.get("psf"),
        info,
    )
    _check(status)
    return images, info_dict(info)


def vis2dirty(
    *,
    uvw,
    freq,
    vis,
    wgt=None,
    mask=None,
    npix_x,
    npix_y,
    pixsize_x,
    pixsize_y,
    epsilon,
    return_info=False,
    **kw,
):
    """The dirty image `(npix_x, npix_y)` of `vis` `(nrow, nchan)`; the
    precision follows `vis` (complex64: single, else double). Keywords as
    ducc0's (`do_wgridding=True`, `divide_by_n=False`, `flip_u/v/w`,
    `center_x/y`, `allow_nshift`, `sigma_min/max`) plus
    `kernel=(row, nu, nv)`. Data and weights are read in place."""
    single = np.asarray(vis).dtype == np.complex64
    images, info = _gridding(
        uvw,
        freq,
        vis,
        wgt,
        mask,
        (npix_x, npix_y),
        (pixsize_x, pixsize_y),
        epsilon,
        single,
        ("dirty",),
        kw,
    )
    if return_info:
        return images["dirty"], info
    return images["dirty"]


def dirty_psf(
    *,
    uvw,
    freq,
    vis,
    wgt=None,
    mask=None,
    npix_x,
    npix_y,
    pixsize_x,
    pixsize_y,
    epsilon,
    single=False,
    return_info=False,
    wgt2=None,
    **kw,
):
    """The dirty image of `vis` and the PSF (unit visibilities with the same
    weights and mask) in one pass over the data, in single or double
    precision. Both use the plan of the PSF's active visibilities
    (`wgt * mask != 0`); a separate `vis2dirty` call uses
    `|vis|^2 * wgt * mask != 0`, so the two agree bit for bit when no
    visibility with nonzero weight is exactly zero. `wgt2` (float32, with a
    float32 `wgt`) multiplies the weight in the core (DF2b)."""
    images, info = _gridding(
        uvw,
        freq,
        vis,
        wgt,
        mask,
        (npix_x, npix_y),
        (pixsize_x, pixsize_y),
        epsilon,
        single,
        ("dirty", "psf"),
        kw,
        wgt2=wgt2,
    )
    if return_info:
        return images["dirty"], images["psf"], info
    return images["dirty"], images["psf"]


def dirty2vis(
    *,
    uvw,
    freq,
    dirty,
    wgt=None,
    mask=None,
    pixsize_x,
    pixsize_y,
    epsilon,
    return_info=False,
    **kw,
):
    """Visibilities `(nrow, nchan)` of the image `dirty` `(nx, ny)`; the
    precision follows `dirty` (float32 or float64). Weights are read in
    place."""
    dirty = np.asarray(dirty)
    single = dirty.dtype == np.float32
    real = np.float32 if single else np.float64
    dirty = np.ascontiguousarray(dirty, real)
    uvw, freq, shape = _coords(uvw, freq)
    wgt, mask = _borrow_weights(wgt, mask, shape)
    opts = _options(
        dirty.shape[0], dirty.shape[1], pixsize_x, pixsize_y, epsilon, dict(kw)
    )
    vis = np.empty(shape, np.complex64 if single else np.complex128)
    info = np.empty(N_INFO, np.float64)
    fn = getattr(extension(), f"wgridder_dirty2vis_{'f32' if single else 'f64'}")
    status = fn(opts, uvw, freq, dirty, wgt, mask, vis.view(real), info)
    _check(status)
    if return_info:
        return vis, info_dict(info)
    return vis


def info_dict(info):
    rec = dict(zip(INFO_NAMES, (float(v) for v in info), strict=True))
    for key in ("kernel_index", "supp", "nu", "nv", "nplanes", "nvis"):
        rec[key] = int(rec[key])
    return rec


def kernel_row(index):
    """Row `index` of the kernel table: (W, ofactor, epsilon, beta, e0,
    ndim, singleprec), or None past its end."""
    out = np.empty(7, np.float64)
    if extension().wgridder_kernel_row(int(index), out):
        return None
    return (int(out[0]), *(float(v) for v in out[1:5]), int(out[5]), bool(out[6]))


def kernel_table():
    rows = []
    while (row := kernel_row(len(rows))) is not None:
        rows.append(row)
    return rows


def fits_image(
    uvw,
    freq,
    data,
    weights,
    width,
    height,
    scale_arcsec,
    epsilon=1e-6,
    single=False,
    imaging_weights=None,
    **kw,
):
    """Dirty image and PSF as `(height, width)` arrays in WSClean's FITS
    pixel order, both scaled so that the PSF centre is one (as
    `core_grid.invert`). WSClean's FITS image is the rang-convention image
    of the data with v and w flipped, transposed (research/df1-wgridder.md,
    item 0). `weights` is the full gridding weight (reader weight times
    imaging weight), or, with `imaging_weights` given, the reader weight:
    two float32 arrays are then multiplied in the core (DF2b, bit-identical
    to passing their float32 product). One pass over the data gives both
    images (`dirty_psf`, the plan of `weights != 0`); data and weights are
    read in place. `kw` passes gridder options (e.g. `divide_by_n`)."""
    dirty, psf, info = dirty_psf(
        uvw=uvw,
        freq=freq,
        vis=data,
        wgt=weights,
        wgt2=imaging_weights,
        **kw,
        npix_x=width,
        npix_y=height,
        pixsize_x=scale_arcsec * ARCSEC,
        pixsize_y=scale_arcsec * ARCSEC,
        epsilon=epsilon,
        single=single,
        return_info=True,
        flip_v=True,
        flip_w=True,
    )
    norm = psf[width // 2, height // 2]
    return {
        "dirty": (dirty.T / norm).astype(np.float64),
        "psf": (psf.T / norm).astype(np.float64),
        "info": info,
        "info_psf": info,
        "psf_centre_raw": float(norm),
    }
