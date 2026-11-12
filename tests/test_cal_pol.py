"""Task C6 (research/c6-polterms.md): the polarisation terms on arrays."""

import math
from pathlib import Path

import numpy as np
import pytest
from rang import cal_apply, cal_pol, simtruth
from rang.formats import caltable

pytest.importorskip("rang._core")

RNG = np.random.default_rng(20261106)


def test_rotate_matches_the_truth_and_inverts():
    m = RNG.normal(size=(7, 5, 4)) + 1j * RNG.normal(size=(7, 5, 4))
    ap, aq = RNG.uniform(-3, 3, 7), RNG.uniform(-3, 3, 7)
    got = cal_pol.rotate(m, ap, aq)
    want = simtruth.rotate(m, ap, aq)
    assert np.max(np.abs(got - want)) < 1e-5
    back = cal_pol.rotate(got, ap, aq, inverse=True)
    assert np.max(np.abs(back - m)) < 1e-5


def test_casa_frame_angle_is_the_truths():
    pytest.importorskip("astropy")
    d = simtruth.design("poldx")
    times, _, fields, _ = simtruth.schedule(d)
    sel = np.flatnonzero(fields == 1)[:6]
    xyz, _, _ = simtruth.antenna_table()
    want = simtruth.parallactic_angle_casa(d, times[sel], fields[sel])
    _, ra, dec, _, _ = simtruth.FIELDS[1]
    for a in (0, 5):
        got = cal_pol.parallactic_angle_casa(
            times[sel], math.radians(ra), math.radians(dec), xyz[d.antennas[a]]
        )
        assert np.max(np.abs(got - want[:, a])) < 1e-12


def _loaded(data, model, a1, a2, tb, freq, nant, weights=None, flag=None):
    nrow, _nchan = data.shape[:2]
    weights = np.ones(data.shape, np.float32) if weights is None else weights
    flag = np.zeros(data.shape, bool) if flag is None else flag
    ntime = int(tb.max()) + 1
    return cal_pol.Loaded(
        ms=Path("unit.ms"),
        field_id=0,
        rows=np.arange(nrow),
        cols={
            "ANTENNA1": a1,
            "ANTENNA2": a2,
            "TIME": np.zeros(nrow),
            "SCAN_NUMBER": np.ones(nrow, int),
        },
        data=np.ascontiguousarray(data, np.complex64),
        model=np.ascontiguousarray(model, np.complex64),
        weights=np.ascontiguousarray(weights, np.float32),
        flag=np.ascontiguousarray(flag, bool),
        flag_row=np.zeros(nrow, bool),
        freq=np.asarray(freq, float),
        nant=nant,
        names=[f"m{a:03d}" for a in range(nant)],
        positions=np.arange(3 * nant, dtype=float).reshape(nant, 3),
        time_bin=tb,
        keys=[(0, t) for t in range(ntime)],
        angles=None,
    )


def _array(nant, ntime):
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    return np.tile(a1, ntime), np.tile(a2, ntime), np.repeat(np.arange(ntime), nbl)


def _polarised_model(nrow, nchan, angle):
    """A 3C 286-like point source rotated by the parallactic angle per row."""
    stokes = np.array([10.0, 0.6, 0.7, 0.0])
    m = simtruth.stokes_coherency(stokes)[None, None].repeat(nrow, 0).repeat(nchan, 1)
    return simtruth.rotate(m, angle, angle)


def test_kcross_and_xf_recover_the_cross_hand_terms():
    nant, ntime, nchan = 6, 4, 128
    a1, a2, t = _array(nant, ntime)
    freq = 856e6 + 856e6 * (np.arange(nchan) + 0.5) / nchan
    nu0 = freq.mean()
    angle = np.linspace(-1.0, 1.2, ntime)[t]
    model = _polarised_model(len(a1), nchan, angle)
    tau = 2.7
    x = np.exp(1j * (0.6 + 0.2 * np.sin(np.arange(nchan) / 20)))
    kc = np.exp(2j * np.pi * tau * 1e-9 * (freq - nu0))
    data = model.copy()
    data[..., 1] *= kc * x
    data[..., 2] *= np.conj(kc * x)
    # KCROSS sees the delay of kc x; with x's frequency structure removed
    # (the model corrupted by Xf), it sees tau alone.
    mx = model.copy()
    mx[..., 1] *= x
    mx[..., 2] *= np.conj(x)
    tb = np.zeros(len(a1), np.int64)
    k = cal_pol.kcross_solve(_loaded(data, mx, a1, a2, tb, freq, nant))
    assert k.ok[0] and abs(k.delay_ns[0] - tau) < 0.01
    # Xf on data with KCROSS removed: exact.
    dx = model.copy()
    dx[..., 1] *= x
    dx[..., 2] *= np.conj(x)
    xs = cal_pol.xf_solve(_loaded(dx, model, a1, a2, tb, freq, nant))
    assert xs.ok.all()
    assert np.max(np.abs(np.angle(xs.x[0] / x))) < 1e-5


def test_df_recovers_casa_referenced_leakages_and_refuses_a_constant_q():
    nant, ntime, nchan = 7, 3, 4
    a1, a2, _t = _array(nant, ntime)
    nrow = len(a1)
    d = 0.02 * (
        RNG.normal(size=(nant, nchan, 2)) + 1j * RNG.normal(size=(nant, nchan, 2))
    )
    model = np.zeros((nrow, nchan, 4), complex)
    model[..., 0] = model[..., 3] = 5.0
    data = model.copy()
    data[..., 1] += d[a1, :, 0] * model[..., 3] + np.conj(d[a2, :, 1]) * model[..., 0]
    data[..., 2] += d[a1, :, 1] * model[..., 0] + np.conj(d[a2, :, 0]) * model[..., 3]
    tb = np.zeros(nrow, np.int64)
    sol = cal_pol.df_solve(_loaded(data, model, a1, a2, tb, np.ones(nchan), nant),
                           refant=3)  # fmt: skip
    assert sol.gauge_fixed
    want = d.copy()
    want[..., 0] -= d[3, :, 0][None]
    want[..., 1] += np.conj(d[3, :, 0])[None]
    assert np.max(np.abs(sol.d[0] - want.transpose(1, 0, 2))) < 1e-6
    assert not sol.flags.any()
    assert (sol.refant_used == 3).all()
    # A polarised model without rotation: refused.
    q = model.copy()
    q[..., 0], q[..., 3] = 5.5, 4.5
    with pytest.raises(ValueError, match="parallactic coverage"):
        cal_pol.df_solve(_loaded(data, q, a1, a2, tb, np.ones(nchan), nant))


def _subtables(freq):
    return {"SPECTRAL_WINDOW": {"CHAN_FREQ": [np.asarray(freq, float)]}}


def test_rust_apply_of_kcross_and_xf_equals_the_python_reference():
    nant, ntime, nchan = 5, 3, 32
    a1, a2, t = _array(nant, ntime)
    time = 100.0 + 8.0 * t
    freq = 1e9 + 1e7 * np.arange(nchan)
    data = RNG.normal(size=(len(a1), nchan, 4)) + 1j * RNG.normal(
        size=(len(a1), nchan, 4)
    )
    flag = RNG.uniform(size=data.shape) > 0.95
    kc = np.zeros((1, nant, 1, 2))
    kc[..., 0] = 3.3
    kct = caltable.from_gains("Kcross", [108.0], list(range(nant)), kc,
                              subtables=_subtables([freq.mean()]), refant=-1)  # fmt: skip
    x = np.exp(1j * (0.4 + 0.01 * np.arange(nchan)))
    xv = np.broadcast_to(x[None, None, :, None], (1, nant, nchan, 1))
    xfl = np.zeros(xv.shape, bool)
    xfl[0, 2] = True  # antenna 2 flagged in every channel
    xft = caltable.from_gains("Xf", [108.0], list(range(nant)), xv, xfl,
                              subtables=_subtables(freq), refant=-1)  # fmt: skip
    for tables in ([kct], [xft], [kct, xft]):
        got, gf = cal_apply.apply(
            data, flag, time, a1, a2, freq, tables, interp="nearest"
        )
        want, wf = caltable.correct(data, flag, time, a1, a2, freq, tables,
                                    time_interp="nearest")  # fmt: skip
        ok = ~wf
        assert np.array_equal(gf, wf)
        assert cal_apply.class_c(got, want, ok)["pass"]


def test_apply_with_p_is_the_inverse_of_corrupt():
    nant, ntime, nchan = 4, 2, 8
    a1, a2, t = _array(nant, ntime)
    freq = 1e9 + 1e7 * np.arange(nchan)
    m = RNG.normal(size=(len(a1), nchan, 4)) + 1j * RNG.normal(size=(len(a1), nchan, 4))
    angles = (RNG.uniform(-3, 3, len(a1)), RNG.uniform(-3, 3, len(a1)))
    x = np.exp(1j * 0.3 * np.ones(nchan))
    xv = np.broadcast_to(x[None, None, :, None], (1, nant, nchan, 1))
    xft = caltable.from_gains("Xf", [108.0], list(range(nant)), xv,
                              subtables=_subtables(freq), refant=-1)  # fmt: skip
    time = 100.0 + 8.0 * t
    v, _ = cal_pol.apply(m, False, time, a1, a2, freq, [xft], angles=angles,
                         direction="corrupt", interp="nearest")  # fmt: skip
    back, f = cal_pol.apply(v, False, time, a1, a2, freq, [xft], angles=angles,
                            interp="nearest")  # fmt: skip
    assert not f.any()
    assert np.max(np.abs(back - m)) < 1e-5


def test_clip_df_flags_large_leakages():
    freq = np.array([1e9, 1.1e9])
    v = np.full((1, 2, 2, 2), 0.01 + 0j)
    v[0, 1, 0, 1] = 0.7
    t = caltable.from_gains("Df", [1.0], [0, 1], v, subtables=_subtables(freq))
    out, n = cal_pol.clip_df(t)
    assert n == 1
    assert out.flags.sum() == 1 and out.flags[1, 0, 1]


# --- Task df-flag-rule (research/p-flag-spread.md): P's flags. ---


def _lone_bad_leakage_case():
    nant, ntime, nchan = 4, 2, 6
    a1, a2, t = _array(nant, ntime)
    time = 100.0 + 8.0 * t
    freq = 1e9 + 1e7 * np.arange(nchan)
    data = RNG.normal(size=(len(a1), nchan, 4)) + 1j * RNG.normal(
        size=(len(a1), nchan, 4)
    )
    d = 0.05 * (
        RNG.normal(size=(1, nant, nchan, 2)) + 1j * RNG.normal(size=(1, nant, nchan, 2))
    )
    dflag = np.zeros(d.shape, bool)
    dflag[0, 1, :, 1] = True  # antenna 1's d_y bad in every channel: one leakage
    df = caltable.from_gains("Df", [108.0], list(range(nant)), d, dflag,
                             subtables=_subtables(freq), refant=-1)  # fmt: skip
    angles = (RNG.uniform(-3, 3, len(a1)), RNG.uniform(-3, 3, len(a1)))
    return data, time, a1, a2, freq, df, angles


def test_spread_flags_is_casas_general_jones_rule():
    f = np.zeros((3, 2, 4), bool)
    f[0, 0, 1] = True
    f[1, 1, 3] = True
    got = cal_pol.spread_flags(f)
    assert got[0, 0].all() and got[1, 1].all()
    assert got.sum() == 8
    assert np.array_equal(cal_pol.spread_flags(f, "none"), f)
    with pytest.raises(ValueError):
        cal_pol.spread_flags(f, "casa")


def test_p_spreads_a_bad_leakages_cross_hand_flags():
    data, time, a1, a2, freq, df, angles = _lone_bad_leakage_case()
    flag = np.zeros(data.shape, bool)
    _, f_tables = cal_apply.apply(data, flag, time, a1, a2, freq, [df],
                                  interp="nearest")  # fmt: skip
    # Df alone (C4a's rule): only cross hands, never XX or YY.
    assert f_tables[..., 1:3].any() and not f_tables[..., [0, 3]].any()
    _, f_none = cal_pol.apply(data, flag, time, a1, a2, freq, [df], angles=angles,
                              interp="nearest", parang_flags="none")  # fmt: skip
    assert np.array_equal(f_none, f_tables)
    v, f = cal_pol.apply(data, flag, time, a1, a2, freq, [df], angles=angles,
                         interp="nearest")  # fmt: skip
    assert np.array_equal(f, np.broadcast_to(f_tables.any(-1, keepdims=True), f.shape))
    # Rows on antenna 1 are flagged in all four correlations, the others not.
    on1 = (a1 == 1) | (a2 == 1)
    assert f[on1].all() and not f[~on1].any()
    # The values do not depend on the flag rule.
    v_none, _ = cal_pol.apply(data, flag, time, a1, a2, freq, [df], angles=angles,
                              interp="nearest", parang_flags="none")  # fmt: skip
    assert np.array_equal(v.view(np.uint32), v_none.view(np.uint32))
    # Corrupt flags the cells correct does.
    _, fc = cal_pol.apply(data, flag, time, a1, a2, freq, [df], angles=angles,
                          interp="nearest", direction="corrupt")  # fmt: skip
    assert np.array_equal(fc, f)


def test_p_spreads_input_flags_and_needs_angles():
    data, time, a1, a2, freq, _, angles = _lone_bad_leakage_case()
    flag = np.zeros(data.shape, bool)
    flag[0, 2, 0] = True  # XX only
    _, f = cal_pol.apply(data, flag, time, a1, a2, freq, [], angles=angles)
    assert f[0, 2].all() and f.sum() == 4
    _, f_no_p = cal_pol.apply(data, flag, time, a1, a2, freq, [])
    assert np.array_equal(f_no_p, flag)
    with pytest.raises(ValueError):
        cal_pol.apply(data, flag, time, a1, a2, freq, [], angles=angles,
                      parang_flags="casa")  # fmt: skip
