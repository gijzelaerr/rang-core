"""Task xf-avg-fix (research/xf-avg-fix.md): `calibrate.average_time` never
averages a P-rotated solve (Gpol, KCROSS, Xf, Df) across scans or across more
than `cal_chunks.PSI_TOL_DEG` of the parallactic angle. Where no average
crosses such a step the averaging is unchanged; on the public fixture with a
second scan 3 h later (P's angle 64 deg on), the averaged Xf equals the
unaveraged one, which the old whole-interval average does not."""

import dataclasses
import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import cal_chunks, cal_fluxscale, cal_pol, core_ms, core_ms_write
from test_c2e_calibrate import calibrator_ms
from test_c6w_polwire import _with_feed

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

POL = (1.0, 0.05, 0.08, 0.0)
XF_TRUE = 0.7  # rad, the cross-hand phase put into the data
LEAK = 0.02 + 0.01j  # a constant cross-hand term (leakage of I), not rotating


def unit(ms, field, stokes=(1.0, 0.0, 0.0, 0.0)):
    nrow, nchan = cal_fluxscale._field_rows(ms, field, 0)
    return cal_fluxscale.smodel_view(nrow, nchan, stokes)


# -- the groups ----------------------------------------------------------------------


def test_one_scan_within_the_tolerance_is_no_group():
    tb = np.zeros(6, np.int64)
    psi = np.radians([10.0, 11.0, 12.0, 13.0, 14.0, 14.9])
    assert cal_chunks.psi_groups(tb, np.ones(6), psi) is None


def test_scans_of_one_interval_are_groups():
    tb = np.zeros(6, np.int64)
    scan = np.array([1, 1, 1, 4, 4, 4])
    psi = np.radians([10.0, 10.1, 10.2, 70.0, 70.1, 70.2])
    assert list(cal_chunks.psi_groups(tb, scan, psi)) == [0, 0, 0, 1, 1, 1]
    # Intervals that are one scan each stay ungrouped.
    assert cal_chunks.psi_groups(np.array([0, 0, 0, 1, 1, 1]), scan, psi) is None


def test_a_wide_scan_is_cut_into_equal_pieces():
    tb = np.zeros(7, np.int64)
    psi = np.radians([0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0])  # 12 deg: 3 pieces of 4
    got = cal_chunks.psi_groups(tb, np.ones(7), psi)
    assert list(got) == [0, 0, 1, 1, 2, 2, 2]
    got = cal_chunks.psi_groups(tb, np.ones(7), psi, tol_deg=20.0)
    assert got is None


def test_the_span_is_circular():
    """A scan crossing +-180 deg spans 4 deg, not 356."""
    tb = np.zeros(4, np.int64)
    psi = np.radians([178.0, 179.5, -179.5, -178.0])
    assert cal_chunks.psi_groups(tb, np.ones(4), psi) is None


def test_groups_keep_the_interval_and_order_the_rows():
    tb = np.array([0, 0, 0, 0, 1, 1])
    a1 = np.array([0, 0, 0, 0, 0, 0])
    a2 = np.array([1, 1, 1, 1, 1, 1])
    group = np.array([0, 1, 0, 1, 2, 2])
    avg = cal_chunks.Average(tb, a1, a2, np.zeros(6, bool), group)
    assert list(avg.time_bin) == [0, 0, 1]
    assert list(avg.inverse) == [0, 1, 0, 1, 2, 2]
    plain = cal_chunks.Average(tb, a1, a2, np.zeros(6, bool))
    assert list(plain.time_bin) == [0, 1] and list(plain.inverse) == [0, 0, 0, 0, 1, 1]


# -- the fixture with two scans far apart in P's angle ------------------------------


@pytest.fixture(scope="module")
def split_ms(tmp_path_factory):
    """C2e's calibrator MS with C6w's FEED; field 1's last 10 of 20 times
    moved 3 h later as scan 9 (P's angle -80 deg, then -16 deg), and its
    DATA the P-rotated polarised model with XF_TRUE on the cross hands plus
    LEAK."""
    pytest.importorskip("astropy")
    ms = _with_feed(calibrator_ms(tmp_path_factory.mktemp("xfavg") / "x.ms", seed=611))
    with core_ms.open_table(ms) as t:
        field = t.getcol("FIELD_ID")
        time = t.getcol("TIME")
        scan = t.getcol("SCAN_NUMBER")
        data = t.getcol("DATA")
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
    rows = np.flatnonzero(field == 1)
    late = rows[time[rows] >= np.unique(time[rows])[10]]
    time[late] += 3 * 3600.0
    scan[late] = 9
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("TIME", time)
        t.putcol("SCAN_NUMBER", scan)
    model = cal_pol.rotate(
        unit(ms, 1, POL), *cal_pol.row_angles(ms, time[rows], a1[rows], a2[rows], 1)
    )
    v = np.array(model, np.complex64)
    v[..., 1] = v[..., 1] * np.exp(1j * XF_TRUE) + LEAK
    v[..., 2] = v[..., 2] * np.exp(-1j * XF_TRUE) + np.conj(LEAK)
    data[rows] = v
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("DATA", data)
    return ms


def _reference(ld, group):
    """`ld` averaged per (interval, group, baseline) by plain loops."""
    keys = sorted(
        {
            (int(t), int(g), int(p), int(q))
            for t, g, p, q in zip(
                ld.time_bin, group, ld.cols["ANTENNA1"], ld.cols["ANTENNA2"]
            )
            if p != q
        }
    )
    shape = (len(keys), *ld.data.shape[1:])
    data = np.zeros(shape, np.complex64)
    model = np.zeros(shape, np.complex64)
    weights = np.zeros(shape, np.float32)
    flag = np.ones(shape, bool)
    row_flag = np.ones(len(keys), bool)
    for i, (t, g, p, q) in enumerate(keys):
        r = np.flatnonzero(
            (ld.time_bin == t)
            & (group == g)
            & (ld.cols["ANTENNA1"] == p)
            & (ld.cols["ANTENNA2"] == q)
        )
        used = ~ld.flag[r] & ~ld.flag_row[r][:, None, None]
        w = np.where(used, ld.weights[r].astype(float), 0.0)
        sw = w.sum(0)
        ok = sw > 0
        data[i] = np.where(ok, (w * ld.data[r]).sum(0) / np.where(ok, sw, 1), 0)
        model[i] = np.where(ok, (w * ld.model[r]).sum(0) / np.where(ok, sw, 1), 0)
        weights[i], flag[i], row_flag[i] = sw, ~ok, ld.flag_row[r].all()
    k = np.array(keys).reshape(-1, 4)
    return dataclasses.replace(
        ld, data=data, model=model, weights=weights, flag=flag, flag_row=row_flag,
        time_bin=k[:, 0], cols={"ANTENNA1": k[:, 2], "ANTENNA2": k[:, 3]},
    )  # fmt: skip


def _xf_deg(sol):
    return np.degrees(np.angle(sol.x[sol.ok]))


def _off(a, b):
    """|a - b| in degrees, on the circle."""
    return np.abs(np.degrees(np.angle(np.exp(1j * np.radians(np.asarray(a) - b)))))


def test_xf_averages_each_scan_and_equals_the_unaveraged_solve(split_ms):
    kw = {"field_id": 1, "model": unit(split_ms, 1, POL), "weight_column": "WEIGHT"}
    plain = cal_pol.xf(split_ms, combine="scan", **kw)[1]
    ld = cal_pol.load(split_ms, solved="Xf", combine="scan", **kw)
    assert len(ld.keys) == 1
    scans = ld.cols["SCAN_NUMBER"]
    want = cal_pol.xf_solve(_reference(ld, (scans == 9).astype(int)))
    old = cal_pol.xf_solve(_reference(ld, np.zeros(len(scans), int)))
    for b in (None, cal_pol_budget(400)):
        got = cal_pol.xf(split_ms, combine="scan", average_time=True, budget=b, **kw)[1]
        assert np.array_equal(got.ok, want.ok) and got.ok.all()
        assert np.allclose(got.x[want.ok], want.x[want.ok], atol=2e-6)
        # The per-scan average is the unaveraged solve's estimator, near the
        # truth; the whole-interval average (before the fix) is not.
        assert _off(_xf_deg(got), _xf_deg(plain)).max() < 0.5
    assert _off(_xf_deg(plain), np.degrees(XF_TRUE)).max() < 2.0
    assert np.median(_off(_xf_deg(old), _xf_deg(plain))) > 4.0  # 6.0 measured


def cal_pol_budget(cells, nrows=480):
    from rang import core_chunks

    return core_chunks.ChainBudget(
        chunk_bytes=core_chunks.CHAIN_ROW_BYTES * nrows
        + cells * core_chunks.CELL_BYTES["chain"]
    )


def test_every_p_rotated_term_is_grouped(split_ms, monkeypatch):
    """Gpol (through `rang.cal_gain`), KCROSS, Xf and Df all average per
    scan with P on, and not at all differently with P off."""
    seen = []
    real = cal_chunks.Average

    def spy(*args, **kwargs):
        avg = real(*args, **kwargs)
        seen.append(len(avg))
        return avg

    monkeypatch.setattr(cal_chunks, "Average", spy)
    kw = {"field_id": 1, "model": unit(split_ms, 1, POL), "weight_column": "WEIGHT",
          "average_time": True, "combine": "scan"}  # fmt: skip
    cal_pol.gpol(split_ms, refant=0, minblperant=2, minsnr=0.0, solint="inf", **kw)
    cal_pol.kcross(split_ms, **kw)
    cal_pol.xf(split_ms, **kw)
    cal_pol.df(split_ms, minblperant=2, minsnr=0.0, **kw)
    assert seen == [12, 12, 12, 12]  # 6 baselines x 2 scans, one interval
    seen.clear()
    cal_pol.xf(split_ms, parang=False, **kw)
    assert seen == [6]


def test_a_scan_wider_than_the_tolerance_is_cut(split_ms, monkeypatch):
    """With the tolerance at 0.3 deg each 10-time scan (0.6-1.0 deg) is cut
    into pieces; the averaged Xf equals the reference averaged per piece."""
    monkeypatch.setattr(cal_chunks, "PSI_TOL_DEG", 0.3)
    kw = {"field_id": 1, "model": unit(split_ms, 1, POL), "weight_column": "WEIGHT"}
    ld = cal_pol.load(split_ms, solved="Xf", combine="scan", **kw)
    psi = ld.angles[0]
    group = cal_chunks.psi_groups(ld.time_bin, ld.cols["SCAN_NUMBER"], psi)
    assert group is not None and group.max() + 1 > 2
    want = cal_pol.xf_solve(_reference(ld, group))
    got = cal_pol.xf(split_ms, combine="scan", average_time=True, **kw)[1]
    assert np.array_equal(got.ok, want.ok)
    assert np.allclose(got.x[want.ok], want.x[want.ok], atol=2e-6)


def test_the_unsplit_fixture_is_unchanged(tmp_path):
    """The fixture's field (one scan, 1.2 deg) forms no group: the averaged
    rows are the ungrouped ones."""
    pytest.importorskip("astropy")
    ms = _with_feed(calibrator_ms(tmp_path / "x.ms", seed=611))
    ld = cal_pol.load(ms, solved="Xf", combine="scan", field_id=1,
                      model=unit(ms, 1, POL), weight_column="WEIGHT")  # fmt: skip
    assert (
        cal_chunks.psi_groups(ld.time_bin, ld.cols["SCAN_NUMBER"], ld.angles[0]) is None
    )
    shutil.rmtree(Path(ms), ignore_errors=True)
