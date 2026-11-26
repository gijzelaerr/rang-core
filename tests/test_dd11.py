# SPDX-License-Identifier: MIT
"""DD11's fast Hogbom equals DD3's, bit for bit (research/dd11-start.md, section 3)."""

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _dd11():
    spec = importlib.util.spec_from_file_location(
        "dd11", ROOT / "tools" / "oracles" / "dd11" / "dd11.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fast_hogbom_equals_dd3():
    dd11 = _dd11()
    dd3 = dd11.dd3
    n = 48
    old = dd3.NX, dd3.NY
    dd3.NX = dd3.NY = n
    try:
        rng = np.random.default_rng(11)
        y, x = np.mgrid[-n:n, -n:n]
        psf = np.exp(-(x**2 + y**2) / 8.0) * (1 + 0.05 * np.cos(x / 3.0))
        res = 1e-4 * rng.normal(size=(n, n))
        for _ in range(6):
            sy, sx = rng.integers(8, n - 8, 2)
            res += (
                rng.uniform(0.01, 0.2) * psf[n - sy : 2 * n - sy, n - sx : 2 * n - sx]
            )
        interior = np.zeros((n, n), bool)
        interior[4:-4, 4:-4] = True
        search = interior.copy()
        search[20:25, 20:25] = False
        ca, _, ia = dd3.hogbom(res, psf, interior, search)
        cb, _, ib = dd11.hogbom_fast(res, psf, interior, search)
        assert len(ca) > 10
        assert list(ca) == list(cb)
        assert all(ca[k] == cb[k] for k in ca)
        assert ia == ib
    finally:
        dd3.NX, dd3.NY = old
