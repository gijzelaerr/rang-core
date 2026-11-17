# SPDX-License-Identifier: MIT
"""Task xf-gap (research/xf-gap.md section 7): `calibrate.xf_calwt`. CASA
6.7.6.14's polcal weights an Xf solve's cells as `calwt` scales them by the
pre-applied tables: per row and correlation (h, h') F(p, h) F(q, h'), F the
antenna's |G|^2 times its channel mean of |B|^2. Off, nothing changes; on,
the factor is that product, unit-amplitude tables leave the weights alone,
and every load path (whole, chunked, time-averaged) carries it."""

import numpy as np
import pytest
from rang import cal_bandpass, cal_chain, cal_delay, cal_gain, cal_pol, core_ms_write
from test_c2e_calibrate import calibrator_ms
from test_c6w_polwire import _with_feed
from test_xf_avg_fix import POL, cal_pol_budget, unit

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    """C2e's calibrator MS with C6w's FEED and K, G, B solved on field 0."""
    pytest.importorskip("astropy")
    ms = _with_feed(calibrator_ms(tmp_path_factory.mktemp("xfcalwt") / "x.ms", seed=33))
    kw = {"field_id": 0, "refant": 0, "model": unit(ms, 0), "weight_column": "WEIGHT"}
    k = cal_delay.gaincal(ms, **kw)[0]
    g = cal_gain.gaincal(
        ms, calmode="ap", gaintable=[k], combine="scan", minblperant=2, **kw
    )[0]
    b = cal_bandpass.bandpass(
        ms, gaintable=[k, g], combine="scan", minblperant=2, **kw
    )[0]
    return ms, [k, g, b]


def _kw(ms, tables):
    return {"field_id": 1, "model": unit(ms, 1, POL), "weight_column": "WEIGHT",
            "gaintable": tables, "interp": "linear"}  # fmt: skip


def _per_antenna(tables, nant):
    """F(p, h) from the tables' cells: |G|^2 (one solution per antenna) times
    the channel mean of |B|^2 over unflagged channels."""
    _, g, b = tables
    assert len(np.unique(g.main["TIME"])) == 1
    f = np.ones((nant, 2))
    for t, chan_mean in ((g, False), (b, True)):
        p, fl = np.abs(t.params.astype(np.complex128)) ** 2, t.flags
        for r, a in enumerate(t.main["ANTENNA1"]):
            for h in range(2):
                v = p[r, :, h][~fl[r, :, h]]
                f[a, h] *= v.mean() if chan_mean else v[0]
    return f


def test_off_is_unchanged_and_on_is_the_product(solved):
    ms, tables = solved
    kw = _kw(ms, tables)
    base = cal_pol.load(ms, solved="Xf", combine="scan", **kw)
    off = cal_pol.load(ms, solved="Xf", combine="scan", calwt=False, **kw)
    assert np.array_equal(base.weights, off.weights)
    on = cal_pol.load(ms, solved="Xf", combine="scan", calwt=True, **kw)
    assert np.array_equal(on.data, base.data) and np.array_equal(on.model, base.model)
    f = _per_antenna(tables, base.nant)
    a1, a2 = base.cols["ANTENNA1"], base.cols["ANTENNA2"]
    want = np.stack(
        [f[a1, h1] * f[a2, h2] for h1, h2 in ((0, 0), (0, 1), (1, 0), (1, 1))], -1
    )
    got = on.weights / np.where(base.weights > 0, base.weights, 1)
    ok = base.weights > 0
    assert np.allclose(
        np.broadcast_to(want[:, None, :], got.shape)[ok], got[ok], rtol=2e-6
    )
    assert np.ptp(want) > 0.05  # the fixture's amplitudes are not all one


def test_unit_amplitude_tables_leave_the_weights(solved):
    ms, tables = solved
    kw = _kw(ms, tables[:1])  # K alone: phases only
    off = cal_pol.load(ms, solved="Xf", combine="scan", **kw)
    on = cal_pol.load(ms, solved="Xf", combine="scan", calwt=True, **kw)
    assert np.allclose(on.weights, off.weights, rtol=1e-6)


def test_every_load_path_carries_it(solved):
    ms, tables = solved
    kw = _kw(ms, tables)
    whole = cal_pol.xf(ms, combine="scan", calwt=True, **kw)[1]
    plain = cal_pol.xf(ms, combine="scan", **kw)[1]
    assert not np.allclose(whole.x, plain.x, atol=0, rtol=0)
    chunked = cal_pol.xf(
        ms, combine="scan", calwt=True, budget=cal_pol_budget(1000, nrows=120), **kw
    )[1]
    assert np.allclose(chunked.x, whole.x, atol=2e-6)
    avg = cal_pol.xf(ms, combine="scan", calwt=True, average_time=True, **kw)[1]
    avg_off = cal_pol.xf(ms, combine="scan", average_time=True, **kw)[1]
    assert not np.allclose(avg.x, avg_off.x, atol=0, rtol=0)
    assert whole.settings.get("calwt") is True and "calwt" not in plain.settings


def test_chain_threads_it_to_xf_only(solved, monkeypatch):
    seen = []
    real = cal_pol.load

    def spy(*args, **kwargs):
        seen.append((kwargs.get("solved"), kwargs.get("calwt", False)))
        return real(*args, **kwargs)

    monkeypatch.setattr(cal_pol, "load", spy)
    ms, tables = solved
    term = {"type": "Xf", "name": "Xf", "solint": "inf", "combine": "scan",
            "uvrange": "", "preapply": ["K", "G", "B"], "interp": [], "model": "column",
            "parang": True}  # fmt: skip
    tabs = {n: {"table": t} for n, t in zip(("K", "G", "B"), tables)}
    term["model"] = "unit"
    common = {"model_column": "MODEL_DATA", "weight_column": "WEIGHT", "xf_calwt": True}
    cal_chain._solve_pol(ms, term, 1, tabs, common)
    assert ("Xf", True) in seen


def test_the_chunked_solve_is_several_chunks(solved, monkeypatch):
    ms, tables = solved
    n = []
    real = cal_pol._each_chunk

    def spy(*args, **kwargs):
        for item in real(*args, **kwargs):
            n.append(1)
            yield item

    monkeypatch.setattr(cal_pol, "_each_chunk", spy)
    cal_pol.xf(ms, combine="scan", calwt=True, budget=cal_pol_budget(1000, nrows=120),
               **_kw(ms, tables))  # fmt: skip
    assert len(n) > 1
