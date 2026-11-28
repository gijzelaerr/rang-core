# SPDX-License-Identifier: MIT
"""DD14's beam rule, nominal-beam image rule, apertures and QPC
renormalisation on small synthetic inputs (research/dd14-flux-scale.md)."""

import importlib.util
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _dd14():
    spec = importlib.util.spec_from_file_location(
        "dd14", ROOT / "tools" / "oracles" / "dd14" / "dd14.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_beam_rule():
    dd14 = _dd14()
    centres = [[0.0, 0.0], [0.0004855283034350155, 0.004300522648396143],
               [-0.004691544318547102, 0.004764539714805727],
               [0.014205637268958871, 0.0024530773631500358]]  # fmt: skip
    bn = dd14.b_nominal(centres)
    assert np.allclose(bn, [1.0, 0.91752123, 0.81287221, 0.36065494], atol=1e-7)
    q = np.linspace(-1.0, 1.0, 5)
    zero = np.zeros((3, 2))
    bt = dd14.beam_true(centres, q, zero, ell=0.0)
    assert bt.shape == (5, 3, 4)
    assert np.allclose(bt, bn[None, None, :])  # circular, no pointing: the nominal beam
    be = dd14.beam_true(centres, q, zero)
    assert np.allclose(be[..., 0], 1.0)
    assert not np.allclose(be[..., 3], bn[3])  # the ellipticity turns with q
    pt = dd14.pointing_offsets(61)
    assert pt.shape == (61, 2) and abs(pt.std() - 0.64 / math.sqrt(2)) < 0.1


def test_qn_rule_reduces_to_qa():
    dd14 = _dd14()
    rng = np.random.default_rng(4)
    shape = (4, 1, 3, 4, 2)
    g = np.exp(0.1 * rng.normal(size=shape)) * np.exp(1j * rng.normal(size=shape))
    flags = np.zeros(shape[:-1], np.int8)
    g[:, 0, 1, 2, :] *= 10.0  # untrusted
    qa, _ = dd14.image_gains("QA", g, flags, None, 5)
    qn, _ = dd14.image_gains("QN", g, flags, None, 5, bnom=np.ones(4))
    assert np.array_equal(qa, qn)
    bn = np.array([1.0, 0.9, 0.8, 0.36])
    qb, bad = dd14.image_gains("QN", g, flags, None, 5, bnom=bn)
    assert np.allclose(np.abs(qb), np.sqrt(bn)[None, None, None, :, None])
    assert bad[0, 0, 1, 2]


def test_apertures_and_qpc():
    dd14 = _dd14()
    n = 200
    yy, xx = np.mgrid[:n, :n]

    def blob(y, x, s):
        g = np.exp(-((yy - y) ** 2 + (xx - x) ** 2) / (2 * 2.0**2))
        return s * g / g.sum()

    sky = (
        blob(60, 60, 0.5)
        + blob(60, 85, 0.1)
        + blob(140, 140, 0.03)
        + blob(150, 60, 0.01)
    )
    idx = np.ones((n, n), int)
    interior = np.ones((n, n), bool)
    aps = dd14.select_apertures(sky, idx, interior, [(60, 62)], facets=(1,))[1]
    assert len(aps) == 2 and aps[0]["pin"] and not aps[1]["pin"]
    assert (aps[0]["y"] - 60) ** 2 + (
        aps[0]["x"] - 62
    ) ** 2 <= 16**2  # the disc-sum maximum
    assert 0.5 < aps[0]["sky"] <= 0.6 + 1e-9 and math.isclose(
        aps[1]["sky"], 0.03, rel_tol=1e-3
    )
    f_all, s_all = dd14.facet_flux(2 * sky, aps)
    assert math.isclose(f_all, 2 * s_all)
    model = np.zeros((n, n))
    model[60, 60] = 0.4  # compact: the box holds everything
    model[100, 100] = 0.3
    model[100, 110] = 0.3  # resolved: box 0.3 of disc 0.6
    fac = dd14.qpc_factors(model, [(60, 60), (100, 100)], [0.8, 0.5])
    assert fac[0]["compact"] and math.isclose(fac[0]["r"], 2.0)
    assert not fac[1]["compact"] and fac[1]["r"] == 1.0


def test_products_err_scale_removed():
    dd14 = _dd14()
    rng = np.random.default_rng(5)
    t = np.exp(0.1 * rng.normal(size=(6, 5, 2, 2)) + 1j * rng.normal(size=(6, 5, 2, 2)))
    g = (t * np.array([1.0, 0.7])[None, None, :, None])[:, None]
    flags = np.zeros((6, 1, 5, 2), np.int8)
    out = dd14.products_err(g, flags, t)
    assert np.allclose(out["s"], [1.0, 0.49])
    assert np.allclose(out["e_sr"], 0.0, atol=1e-12)
    assert np.isclose(out["e"][1], 0.51)
