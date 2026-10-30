"""Exact gridder of big-plan task DF1 (research/df1-wgridder.md)."""

import hashlib
from pathlib import Path

import numpy as np
import pytest
from rang import core_grid, core_wgridder

C_LIGHT = 299792458.0
ROOT = Path(__file__).resolve().parents[1]
# SHA256 of ducc0 0.42.0's KernelDB rows (ndim 2 and 3) as extracted from
# gridding_kernel.cc at tag ducc0_0_42_0 (oracle_ducc0.py kerneldb).
KERNEL_ROWS_SHA256 = "0427f5940e0faa20efc615a1f4fb73eadbf754465f483f216c11b317f4ae3831"


def _case(nx=32, ny=32, field=0.2, wmax=600.0, nrow=40, seed=3):
    rng = np.random.default_rng(seed)
    freq = np.array([1.0e9, 1.3e9])
    dx = field / nx
    lam = freq.max() / C_LIGHT
    uvw = np.stack(
        [
            rng.uniform(-0.45, 0.45, nrow) / dx / lam,
            rng.uniform(-0.45, 0.45, nrow) / dx / lam,
            rng.uniform(-wmax, wmax, nrow) / lam,
        ],
        axis=1,
    )
    vis = rng.standard_normal((nrow, 2)) + 1j * rng.standard_normal((nrow, 2))
    wgt = rng.uniform(0.5, 1.5, (nrow, 2))
    return uvw, freq, vis, wgt, nx, ny, dx


def _grid(nx, ny, dx):
    l1 = (np.arange(nx) - nx // 2) * dx
    m1 = (np.arange(ny) - ny // 2) * dx
    L, M = np.meshgrid(l1, m1, indexing="ij")
    return L, M, np.sqrt(1 - L**2 - M**2) - 1


def _dft_dirty(uvw, freq, vis, wgt, nx, ny, dx):
    L, M, N1 = _grid(nx, ny, dx)
    out = np.zeros((nx, ny))
    for r in range(uvw.shape[0]):
        for c, f in enumerate(freq):
            u, v, w = uvw[r] * f / C_LIGHT
            out += np.real(
                vis[r, c] * wgt[r, c] * np.exp(2j * np.pi * (u * L + v * M + w * N1))
            )
    return out


def test_kernel_table_is_ducc0s():
    src = (ROOT / "core" / "src" / "wgridder.rs").read_text().splitlines()
    a = src.index("// KERNEL_ROWS_BEGIN")
    b = src.index("// KERNEL_ROWS_END")
    text = "\n".join(line.rstrip(",") for line in src[a + 1 : b]) + "\n"
    assert hashlib.sha256(text.encode()).hexdigest() == KERNEL_ROWS_SHA256
    table = core_wgridder.kernel_table()
    assert len(table) == 939 == b - a - 1
    assert table[0] == (
        4,
        1.2,
        0.027638471,
        1.30709338717990464,
        0.588199361165364421,
        2,
        True,
    )
    assert table[-1][0] == 16 and table[-1][5] == 3 and table[-1][6] is False


def test_vis2dirty_matches_dft_both_precisions():
    uvw, freq, vis, wgt, nx, ny, dx = _case()
    ref = _dft_dirty(uvw, freq, vis, wgt, nx, ny, dx)
    common = {
        "uvw": uvw,
        "freq": freq,
        "npix_x": nx,
        "npix_y": ny,
        "pixsize_x": dx,
        "pixsize_y": dx,
    }
    d64, info = core_wgridder.vis2dirty(
        vis=vis, wgt=wgt, epsilon=1e-9, return_info=True, **common
    )
    assert np.abs(d64 - ref).max() / np.abs(ref).max() < 1e-8
    assert info["nvis"] == vis.size and info["nplanes"] > info["supp"]
    d32 = core_wgridder.vis2dirty(
        vis=vis.astype(np.complex64), wgt=wgt.astype(np.float32), epsilon=1e-4, **common
    )
    assert d32.dtype == np.float32
    assert np.abs(d32 - ref).max() / np.abs(ref).max() < 1e-3


def test_adjoint_and_dirty2vis():
    uvw, freq, vis, wgt, nx, ny, dx = _case(seed=8)
    rng = np.random.default_rng(1)
    x = rng.standard_normal((nx, ny))
    common = {
        "uvw": uvw,
        "freq": freq,
        "wgt": wgt,
        "pixsize_x": dx,
        "pixsize_y": dx,
        "epsilon": 1e-9,
    }
    ax = core_wgridder.dirty2vis(dirty=x, **common)
    aty = core_wgridder.vis2dirty(vis=vis, npix_x=nx, npix_y=ny, **common)
    lhs = np.real(np.vdot(ax, vis))
    rhs = np.sum(x * aty)
    assert abs(lhs - rhs) / (np.linalg.norm(ax) * np.linalg.norm(vis)) < 1e-12
    # One pixel against the direct sum.
    img = np.zeros((nx, ny))
    img[5, 20] = 2.0
    got = core_wgridder.dirty2vis(dirty=img, **common)
    L, M, N1 = _grid(nx, ny, dx)
    lam = freq / C_LIGHT
    u, v, w = (uvw[:, i, None] * lam for i in range(3))
    ref = (
        2.0 * wgt * np.exp(-2j * np.pi * (u * L[5, 20] + v * M[5, 20] + w * N1[5, 20]))
    )
    assert np.abs(got - ref).max() / np.abs(ref).max() < 1e-8


def test_zero_weights_and_bad_input():
    uvw, freq, vis, wgt, nx, ny, dx = _case(nrow=6)
    common = {
        "uvw": uvw,
        "freq": freq,
        "npix_x": nx,
        "npix_y": ny,
        "pixsize_x": dx,
        "pixsize_y": dx,
    }
    empty = core_wgridder.vis2dirty(
        vis=vis, wgt=np.zeros_like(wgt), epsilon=1e-6, **common
    )
    assert not empty.any()
    with pytest.raises(ValueError, match="ascending"):
        core_wgridder.vis2dirty(
            vis=vis, wgt=wgt, epsilon=1e-6, **{**common, "freq": freq[::-1]}
        )
    with pytest.raises(ValueError, match="kernel"):
        core_wgridder.vis2dirty(vis=vis, wgt=wgt, epsilon=1e-14, **common)


def test_matches_ducc0_when_available():
    ducc0 = pytest.importorskip("ducc0")
    uvw, freq, vis, wgt, nx, ny, dx = _case(seed=12)
    common = {
        "uvw": uvw,
        "freq": freq,
        "vis": vis,
        "wgt": wgt,
        "npix_x": nx,
        "npix_y": ny,
        "pixsize_x": dx,
        "pixsize_y": dx,
    }
    ours = core_wgridder.vis2dirty(epsilon=1e-7, **common)
    ref = ducc0.wgridder.vis2dirty(
        epsilon=1e-7,
        do_wgridding=True,
        nthreads=1,
        flip_w=True,
        divide_by_n=False,
        **common,
    )
    assert np.abs(ours - ref).max() / np.abs(ref).max() < 1e-9


def test_fits_image_matches_wstacking_orientation():
    # A well-padded w-stacking image (padding 2, kernel 15) is close to exact.
    rng = np.random.default_rng(4)
    width, scale = 48, 60.0
    freq = np.array([1.2e9, 1.4e9])
    lam = freq.max() / C_LIGHT
    cell = scale * np.pi / 648000.0
    uvw = np.stack(
        [
            rng.uniform(-0.4, 0.4, 60) / cell / lam,
            rng.uniform(-0.4, 0.4, 60) / cell / lam,
            rng.uniform(-100, 100, 60) / lam,
        ],
        axis=1,
    )
    l0, m0 = 7 * cell, -4 * cell
    n0 = np.sqrt(1 - l0**2 - m0**2) - 1
    u, v, w = (uvw[:, i, None] * freq / C_LIGHT for i in range(3))
    data = np.exp(-2j * np.pi * (u * l0 + v * m0 + w * n0)).astype(np.complex64)
    weights = np.ones(data.shape, np.float32)
    ref = core_grid.invert(
        uvw,
        freq,
        data,
        weights,
        weights,
        width,
        width,
        scale,
        w_layers=32,
        kernel_size=15,
        padding=2.0,
    )
    got = core_wgridder.fits_image(
        uvw, freq, data, weights, width, width, scale, epsilon=1e-7
    )
    assert np.abs(got["psf"] - ref["psf"]).max() < 1e-3
    assert np.abs(got["dirty"] - ref["dirty"]).max() < 1e-3


def test_psf_mode_and_borrowed_inputs_match_separate_calls(monkeypatch):
    # DF2a (research/df2-wgridder-speed.md): one pass gives the dirty image
    # and the PSF bit for bit as two calls; complex64 data and float32
    # weights read in place equal the cast arrays; plane groups change
    # nothing.
    uvw, freq, vis, wgt, nx, ny, dx = _case(seed=21, nrow=50)
    vis64 = vis.astype(np.complex64)
    wgt32 = wgt.astype(np.float32)
    wgt32[3, 1] = 0.0
    common = {
        "uvw": uvw,
        "freq": freq,
        "npix_x": nx,
        "npix_y": ny,
        "pixsize_x": dx,
        "pixsize_y": dx,
        "epsilon": 1e-7,
    }
    dirty, psf = core_wgridder.dirty_psf(vis=vis64, wgt=wgt32, **common)
    sep = core_wgridder.vis2dirty(
        vis=vis64.astype(np.complex128), wgt=wgt32.astype(np.float64), **common
    )
    ones = np.where(wgt32 != 0, 1.0, 0.0).astype(np.complex128)
    sep_psf = core_wgridder.vis2dirty(vis=ones, wgt=wgt32.astype(np.float64), **common)
    assert np.array_equal(dirty, sep) and np.array_equal(psf, sep_psf)
    single = {**common, "epsilon": 1e-4}
    d32, _ = core_wgridder.dirty_psf(
        vis=vis.astype(np.complex128), wgt=wgt, single=True, **single
    )
    assert d32.dtype == np.float32
    assert np.array_equal(
        d32, core_wgridder.vis2dirty(vis=vis64, wgt=wgt.astype(np.float32), **single)
    )
    x = np.random.default_rng(2).standard_normal((nx, ny))
    kw = {k: common[k] for k in ("uvw", "freq", "pixsize_x", "pixsize_y", "epsilon")}
    assert np.array_equal(
        core_wgridder.dirty2vis(dirty=x, wgt=wgt32, **kw),
        core_wgridder.dirty2vis(dirty=x, wgt=wgt32.astype(np.float64), **kw),
    )
    monkeypatch.setenv("RANG_WGRIDDER_PLANE_GROUP", "3")
    grouped = core_wgridder.dirty_psf(vis=vis64, wgt=wgt32, **common)
    assert np.array_equal(grouped[0], dirty) and np.array_equal(grouped[1], psf)
