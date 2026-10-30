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

Until `core/src/lib.rs` lists `wgridder` and `ffi_wgridder` in a library
loadable through ctypes (the extension does not bind them), the two files
are built as a standalone cdylib in `core/target/df1-standalone` and loaded
through ctypes; `RANG_DF1_LIB` selects a prebuilt library.
"""

import ctypes
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

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
SOURCES = ("wgridder.rs", "ffi_wgridder.rs")
SYMBOLS = (
    "rang_core_wgridder_vis2dirty_f64",
    "rang_core_wgridder_vis2dirty_f32",
    "rang_core_wgridder_dirty2vis_f64",
    "rang_core_wgridder_dirty2vis_f32",
    "rang_core_wgridder_vis2dirty_ex_f64",
    "rang_core_wgridder_vis2dirty_ex_f32",
    "rang_core_wgridder_dirty2vis_ex_f64",
    "rang_core_wgridder_dirty2vis_ex_f32",
    "rang_core_wgridder_kernel_row",
    "rang_core_wgridder_last_error",
)
ARCSEC = np.pi / (180.0 * 3600.0)
# Kinds of the `_ex` entry points (ffi_wgridder.rs).
VIS_KIND = {np.dtype(np.complex64): 1, np.dtype(np.complex128): 2}
WGT_KIND = {np.dtype(np.float32): 1, np.dtype(np.float64): 2}


class Options(ctypes.Structure):
    _fields_ = [
        ("nx", ctypes.c_size_t),
        ("ny", ctypes.c_size_t),
        ("pixsize_x", ctypes.c_double),
        ("pixsize_y", ctypes.c_double),
        ("epsilon", ctypes.c_double),
        ("center_x", ctypes.c_double),
        ("center_y", ctypes.c_double),
        ("sigma_min", ctypes.c_double),
        ("sigma_max", ctypes.c_double),
        ("do_wgridding", ctypes.c_int32),
        ("divide_by_n", ctypes.c_int32),
        ("flip_u", ctypes.c_int32),
        ("flip_v", ctypes.c_int32),
        ("flip_w", ctypes.c_int32),
        ("allow_nshift", ctypes.c_int32),
        ("kernel_index", ctypes.c_int64),
        ("nu", ctypes.c_size_t),
        ("nv", ctypes.c_size_t),
    ]


def standalone_dir():
    return core.core_root() / "target" / "df1-standalone"


def write_standalone():
    """Write the standalone crate (`rang_df1_core`) whose root includes the
    two DF1 files by path; rayon and rustfft come from the core's lock."""
    root = core.core_root()
    out = standalone_dir()
    out.mkdir(parents=True, exist_ok=True)
    _write_if_changed(
        out / "Cargo.toml",
        "[package]\n"
        'name = "rang-df1-core"\n'
        'version = "0.1.0"\n'
        'edition = "2024"\n'
        'license = "GPL-3.0-or-later"\n'
        "publish = false\n\n"
        "[lib]\n"
        'name = "rang_df1_core"\n'
        'path = "root.rs"\n'
        'crate-type = ["rlib", "cdylib"]\n\n'
        "[dependencies]\n"
        'rayon = "1.12.0"\n'
        'rustfft = "6.4.1"\n\n'
        "[profile.release]\n"
        'lto = "thin"\n'
        "codegen-units = 1\n\n"
        "[workspace]\n",
    )
    modules = "".join(
        f'#[path = "{(root / "src" / name).as_posix()}"]\npub mod {name.removesuffix(".rs")};\n'
        for name in SOURCES
    )
    _write_if_changed(
        out / "root.rs",
        "//! Standalone build of the DF1 gridder until core/src/lib.rs lists it.\n"
        + modules,
    )
    _write_if_changed(out / "Cargo.lock", (root / "Cargo.lock").read_text())
    return out


def _write_if_changed(path, text):
    """Write only on change, so that cargo's fingerprints stay valid."""
    path = Path(path)
    if not path.is_file() or path.read_text() != text:
        path.write_text(text)


def build_standalone():
    out = write_standalone()
    subprocess.run(
        [
            "cargo",
            "build",
            "--offline",
            "--release",
            "-q",
            "--manifest-path",
            str(out / "Cargo.toml"),
        ],
        cwd=out,
        check=True,
    )
    return (
        out
        / "target"
        / "release"
        / {"win32": "rang_df1_core.dll", "darwin": "librang_df1_core.dylib"}.get(
            sys.platform, "librang_df1_core.so"
        )
    )


def _declare(lib):
    dptr = ctypes.POINTER(ctypes.c_double)
    fptr = ctypes.POINTER(ctypes.c_float)
    u8ptr = ctypes.POINTER(ctypes.c_uint8)
    opt = ctypes.POINTER(Options)
    size = ctypes.c_size_t
    vptr = ctypes.c_void_p
    i32 = ctypes.c_int32
    for prec, ptr in (("f64", dptr), ("f32", fptr)):
        for name in (
            f"rang_core_wgridder_vis2dirty_{prec}",
            f"rang_core_wgridder_dirty2vis_{prec}",
        ):
            fn = getattr(lib, name)
            fn.argtypes = [opt, size, size, dptr, dptr, ptr, ptr, u8ptr, ptr, dptr]
            fn.restype = ctypes.c_int
        fn = getattr(lib, f"rang_core_wgridder_vis2dirty_ex_{prec}")
        fn.argtypes = [opt, size, size, dptr, dptr, vptr, i32, vptr, i32, u8ptr]
        fn.argtypes += [ptr, ptr, dptr]
        fn.restype = ctypes.c_int
        fn = getattr(lib, f"rang_core_wgridder_dirty2vis_ex_{prec}")
        fn.argtypes = [opt, size, size, dptr, dptr, ptr, vptr, i32, u8ptr, ptr, dptr]
        fn.restype = ctypes.c_int
    lib.rang_core_wgridder_kernel_row.argtypes = [size, dptr]
    lib.rang_core_wgridder_kernel_row.restype = ctypes.c_int
    lib.rang_core_wgridder_last_error.argtypes = [ctypes.c_char_p, size]
    lib.rang_core_wgridder_last_error.restype = size
    return lib


@lru_cache(maxsize=1)
def library():
    """A ctypes handle exporting the gridder's symbols: `RANG_DF1_LIB` if
    set, else the core library when it exports them, else the standalone
    build."""
    configured = os.environ.get("RANG_DF1_LIB")
    if configured:
        return _declare(ctypes.CDLL(str(Path(configured).resolve())))
    lib = core.library()
    if all(hasattr(lib, name) for name in SYMBOLS):
        return _declare(lib)
    return _declare(ctypes.CDLL(str(build_standalone())))


def library_path():
    return Path(library()._name).resolve()


def _ptr(array, kind):
    return None if array is None else array.ctypes.data_as(ctypes.POINTER(kind))


def _options(npix_x, npix_y, pixsize_x, pixsize_y, epsilon, kw):
    kernel = kw.pop("kernel", None)
    opts = Options(
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
    return opts


def _check(lib, status):
    if status == 0:
        return
    if status == 1:
        n = lib.rang_core_wgridder_last_error(None, 0)
        buf = ctypes.create_string_buffer(n + 1)
        lib.rang_core_wgridder_last_error(buf, n)
        raise ValueError(buf.raw[:n].decode())
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


def _gridding(uvw, freq, vis, wgt, mask, npix, pix, epsilon, single, outputs, kw):
    """Call `vis2dirty_ex` for `outputs`, a subset of ("dirty", "psf")."""
    uvw, freq, shape = _coords(uvw, freq)
    vis = _borrow_vis(vis, shape)
    wgt, mask = _borrow_weights(wgt, mask, shape)
    opts = _options(npix[0], npix[1], pix[0], pix[1], epsilon, dict(kw))
    real = np.float32 if single else np.float64
    kind = ctypes.c_float if single else ctypes.c_double
    images = {name: np.empty((int(npix[0]), int(npix[1])), real) for name in outputs}
    info = np.empty(N_INFO, np.float64)
    lib = library()
    fn = getattr(lib, f"rang_core_wgridder_vis2dirty_ex_{'f32' if single else 'f64'}")
    status = fn(
        ctypes.byref(opts),
        shape[0],
        shape[1],
        _ptr(uvw, ctypes.c_double),
        _ptr(freq, ctypes.c_double),
        vis.ctypes.data,
        VIS_KIND[vis.dtype],
        None if wgt is None else wgt.ctypes.data,
        0 if wgt is None else WGT_KIND[wgt.dtype],
        _ptr(mask, ctypes.c_uint8),
        _ptr(images.get("dirty"), kind),
        _ptr(images.get("psf"), kind),
        _ptr(info, ctypes.c_double),
    )
    _check(lib, status)
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
    **kw,
):
    """The dirty image of `vis` and the PSF (unit visibilities with the same
    weights and mask) in one pass over the data, in single or double
    precision. Both use the plan of the PSF's active visibilities
    (`wgt * mask != 0`); a separate `vis2dirty` call uses
    `|vis|^2 * wgt * mask != 0`, so the two agree bit for bit when no
    visibility with nonzero weight is exactly zero."""
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
    lib = library()
    fn = getattr(lib, f"rang_core_wgridder_dirty2vis_ex_{'f32' if single else 'f64'}")
    kind = ctypes.c_float if single else ctypes.c_double
    status = fn(
        ctypes.byref(opts),
        shape[0],
        shape[1],
        _ptr(uvw, ctypes.c_double),
        _ptr(freq, ctypes.c_double),
        _ptr(dirty, kind),
        None if wgt is None else wgt.ctypes.data,
        0 if wgt is None else WGT_KIND[wgt.dtype],
        _ptr(mask, ctypes.c_uint8),
        _ptr(vis.view(real), kind),
        _ptr(info, ctypes.c_double),
    )
    _check(lib, status)
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
    if library().rang_core_wgridder_kernel_row(int(index), _ptr(out, ctypes.c_double)):
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
):
    """Dirty image and PSF as `(height, width)` arrays in WSClean's FITS
    pixel order, both scaled so that the PSF centre is one (as
    `core_grid.invert`). WSClean's FITS image is the rang-convention image
    of the data with v and w flipped, transposed (research/df1-wgridder.md,
    item 0). `weights` is the full gridding weight (reader weight times
    imaging weight). One pass over the data gives both images (`dirty_psf`,
    the plan of `weights != 0`); data and weights are read in place."""
    dirty, psf, info = dirty_psf(
        uvw=uvw,
        freq=freq,
        vis=data,
        wgt=weights,
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
