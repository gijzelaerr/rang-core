# SPDX-License-Identifier: MIT
"""DD13's image-gain rules and uv cut on small synthetic inputs
(research/dd13-absorb.md, section 5)."""

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _dd13():
    spec = importlib.util.spec_from_file_location(
        "dd13", ROOT / "tools" / "oracles" / "dd13" / "dd13.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_time_constant_amplitude_and_rules():
    dd13 = _dd13()
    rng = np.random.default_rng(3)
    shape = (5, 1, 3, 4, 2)
    amp = np.exp(0.1 * rng.normal(size=shape))
    g = amp * np.exp(1j * rng.normal(size=shape))
    flags = np.zeros(shape[:-1], np.int8)
    flags[0, 0, 1, 2] = 1  # one flagged cell
    g[:, 0, 2, 3, :] *= 10.0  # antenna 2 direction 3 untrusted everywhere
    bad = dd13.dd11.untrusted(g, flags)
    a = dd13.time_constant_amplitude(g, bad)
    assert a.shape == (1, 1, 3, 4, 2)
    ref = np.median(np.abs(g[1:, 0, 1, 2]), axis=0)  # the flagged interval left out
    assert np.allclose(a[0, 0, 1, 2], ref)
    assert np.all(a[0, 0, 2, 3] == 1.0)  # no trusted interval
    truth = np.exp(1j * rng.normal(size=shape))
    for rule, cyc in (("QA", 5), ("Q", 0), ("SA", 1)):
        ig, _b = dd13.image_gains(rule, g, flags, truth, cyc)
        assert np.allclose(np.abs(ig), 1.0)
    ig, _ = dd13.image_gains("Q", g, flags, truth, 2)
    assert np.allclose(ig[~bad], g[~bad])
    assert np.all(ig[bad] == 1.0)
    ig, _ = dd13.image_gains("SA", g, flags, truth, 2)
    assert np.allclose(np.abs(ig[~bad]), np.broadcast_to(a, g.shape)[~bad])
    assert np.allclose(np.angle(ig[~bad]), np.angle(g[~bad]))
    ig, _ = dd13.image_gains("ATa", g, flags, truth, 2)
    assert np.allclose(np.abs(ig[~bad]), np.abs(truth[~bad]))
    assert np.allclose(ig[bad], truth[bad])
    ig, _ = dd13.image_gains("ATp", g, flags, truth, 2)
    assert np.allclose(np.abs(ig[~bad]), np.abs(g[~bad]))
    assert np.allclose(np.angle(ig[~bad]), np.angle(truth[~bad]))


def test_uv_cut():
    dd13 = _dd13()
    assert abs(dd13.UV_MIN - 1074.3) < 0.1
    freq = np.array([1.0e9, 2.0e9])
    lam = dd13.C_LIGHT / freq
    uvw = np.array([[1000 * lam[0], 0, 0], [0, 1100 * lam[0], 5.0]])
    cut = dd13.uv_cut({"UVW": uvw, "freq": freq})
    assert cut.tolist() == [[True, False], [False, False]]
    c = {"FLAG": np.zeros((2, 2, 4), bool), "FLAG_ROW": np.zeros(2, bool)}
    cc = dd13.cut_ctx({"c": c}, cut)["c"]
    assert cc["FLAG"][0, 0].all() and not cc["FLAG"][1].any()
    assert not c["FLAG"].any()
