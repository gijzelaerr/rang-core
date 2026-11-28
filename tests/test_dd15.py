# SPDX-License-Identifier: MIT
"""DD15's gated image rule, search mask, d3 clause and answer table on small
synthetic inputs (research/dd15-beam-gate.md)."""

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BNOM = np.array([1.0, 0.91752123, 0.81287221, 0.36065494])


def _dd15():
    spec = importlib.util.spec_from_file_location(
        "dd15", ROOT / "tools" / "oracles" / "dd15" / "dd15.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gains(seed=4):
    rng = np.random.default_rng(seed)
    shape = (4, 1, 3, 4, 2)
    g = np.exp(0.1 * rng.normal(size=shape)) * np.exp(1j * rng.normal(size=shape))
    g[:, 0, 1, 2, :] *= 10.0  # untrusted
    g[:, 0, 2, 3, :] *= 10.0  # untrusted in d3
    return g, np.zeros(shape[:-1], np.int8)


def test_partition():
    dd15 = _dd15()
    assert dd15.high_facets(BNOM).tolist() == [True, True, True, False]


def test_all_high_is_qn_bitwise():
    dd15 = _dd15()
    g, f = _gains()
    for cyc in (0, 1, 2, 7):
        qg, _ = dd15.image_gains_qg(g, f, cyc, BNOM, BNOM, thresh=0.0)
        qn, _ = dd15.dd14.image_gains("QN", g, f, None, cyc, bnom=BNOM)
        assert np.array_equal(qg, qn)


def test_real_form_reduces_to_qa_and_q():
    dd15 = _dd15()
    g, f = _gains()
    one = np.ones(4)
    for cyc in (0, 1, 2, 7):
        hi, _ = dd15.image_gains_qg(g, f, cyc, one, BNOM, thresh=0.0)
        qa, _ = dd15.dd13.image_gains("QA", g, f, None, cyc)
        assert np.array_equal(hi, qa)
        lo, _ = dd15.image_gains_qg(g, f, cyc, one, BNOM, thresh=2.0)
        q, _ = dd15.dd13.image_gains("Q", g, f, None, cyc)
        assert np.array_equal(lo, q)


def test_gated_low_facet_takes_solved_gains_from_cycle_2():
    dd15 = _dd15()
    g, f = _gains()
    early, bad = dd15.image_gains_qg(g, f, 1, BNOM, BNOM)
    late, _ = dd15.image_gains_qg(g, f, 2, BNOM, BNOM)
    ok3 = ~bad[..., 3]
    assert np.allclose(np.abs(early[..., 3, :][ok3]), np.sqrt(BNOM[3]))
    assert np.array_equal(late[..., 3, :][ok3], g[..., 3, :][ok3])
    assert np.allclose(late[..., 3, :][~ok3], np.sqrt(BNOM[3]))
    assert np.array_equal(
        late[..., :3, :], early[..., :3, :]
    )  # high facets and d0 unchanged


def test_search_mask():
    dd15 = _dd15()
    idx = np.repeat(np.arange(4), 4)[None, :].repeat(3, 0)  # (3, 16)
    clean = idx > 0
    pinned = clean.copy()
    pinned[1, [5, 9, 13]] = False  # a pin pixel in each of d1-d3
    hi = dd15.high_facets(BNOM)
    m = dd15.search_mask(clean, pinned, idx, hi, True)
    assert m[1, 5] and m[1, 9] and not m[1, 13]
    assert np.array_equal(dd15.search_mask(clean, pinned, idx, hi, False), pinned)
    assert np.array_equal(
        dd15.search_mask(clean, pinned, idx, np.ones(4, bool), True), clean
    )
    assert np.array_equal(
        dd15.search_mask(clean, pinned, idx, np.zeros(4, bool), True), pinned
    )


def _pt(e_sr, e_d, s=(1, 1, 1, 1), kpin=(0, 0, 0), reading="closes"):
    return {"e_sr": [0, *e_sr], "e_d": [0, *e_d], "s": list(s), "kappa_pin": list(kpin),
            "reading_sr": reading}  # fmt: skip


def test_d3_clause_and_answer():
    dd15 = _dd15()
    # DD14's M12 numbers (section 6): Q12, ATP12, QPN12, QP12
    q = _pt((0.356, 0.282, 0.886), (0.315, 0.328, 1.318))
    atp = _pt((0.090, 0.210, 1.216), (0.084, 0.214, 1.001))
    qpn = _pt(
        (0.141, 0.312, 1.249),
        (0.140, 0.308, 1.136),
        (1, 0.994, 0.983, 0.806),
        (-0.014, -0.035, 1.472),
    )
    qp = _pt((0.099, 0.285, 1.067), (0.147, 0.424, 1.721))
    assert dd15.effect15(atp, q, atp)["reading"].startswith(
        "helps"
    )  # the control passes
    assert not dd15.effect15(atp, q, atp)["d3_worse"]
    assert dd15.effect15(qpn, q, atp)["reading"].startswith("helps")
    assert dd15.effect15(qp, q, atp)["d3_worse"]
    ok = [True] * 3
    cq = dd15.criteria(qpn, q, atp, -0.278, ok)
    assert cq["G"] and cq["F_d1_d2"] and not cq["F_d3"] and cq["row"] == 0
    good = dict(qpn, kappa_pin=[-0.014, -0.035, 0.02])
    assert dd15.criteria(good, q, atp, -0.278, ok)["row"] == 1
    lim = dict(qpn, kappa_pin=[-0.014, -0.035, -0.30])
    assert dd15.criteria(lim, q, atp, -0.278, ok)["row"] == 2
    assert dd15.criteria(lim, q, atp, -0.278, [True, True, False])["row"] == 0
    assert dd15.answer([1, 1]).startswith("in:")
    assert dd15.answer([1, 2]).startswith("in for d1-d2")
    assert dd15.answer([2, 0]).startswith("out")
    assert dd15.answer([1, 1], stopped=True).startswith("out")
