"""Self-checks of the A1 simulated truth (research/a1-simtruth.md)."""

import math

import numpy as np
import pytest

pytest.importorskip("astropy")
from rang import core
from rang import simtruth as st

pytestmark = pytest.mark.skipif(
    not hasattr(core.extension(), "predict_components"),
    reason="needs the core extension",
)


@pytest.fixture(scope="module")
def case():
    d = st.Design("unit", [0, 5, 21, 40, 63], 16, st.SMALL_LENGTH, st.SEEDS["small"])
    times, scans, fields, within = st.schedule(d)
    uvw, q, elev = st.geometry(d, times, fields)
    truth = st.jones(d, times, scans, fields, within)
    a1, a2 = np.triu_indices(len(d.antennas), 1)
    tix = np.arange(len(times))
    rows = st.Rows(
        np.repeat(tix, len(a1)), np.tile(a1, len(tix)), np.tile(a2, len(tix))
    )
    ruvw = uvw[rows.tindex, rows.a1] - uvw[rows.tindex, rows.a2]
    sky = st.target_sky(d)
    cal = st.calibrator_stokes(d)
    rf = fields[rows.tindex]
    m = np.zeros((len(rows.tindex), d.nchan, 4), complex)
    for f in range(4):
        sel = rf == f
        if f == 3:
            m[sel] = st.target_coherency(ruvw[sel], d.freq, sky)
        else:
            m[sel] = st.stokes_coherency(cal[f])[None]
    return {
        "d": d,
        "times": times,
        "fields": fields,
        "scans": scans,
        "q": q,
        "elev": elev,
        "truth": truth,
        "rows": rows,
        "uvw": ruvw,
        "m": m,
        "sky": sky,
    }


def test_schedule_and_parallactic_coverage(case):
    d, q, fields = case["d"], case["q"], case["fields"]
    assert len(np.unique(case["scans"][fields == 1])) >= 3
    qx = (
        np.unwrap(np.degrees(q[fields == 1, 0]) * 2 * math.pi / 360)
        * 360
        / (2 * math.pi)
    )
    assert np.ptp(qx) >= 90.0
    assert case["elev"].min() > 20.0
    assert d.freq[0] > 856e6 and d.freq[-1] < 1712e6


def test_corrupt_correct_round_trip(case):
    v = st.corrupt(case["m"], case["truth"], case["d"], case["rows"], case["q"])
    back = st.correct(v, case["truth"], case["d"], case["rows"], case["q"])
    scale = np.abs(case["m"]).max(axis=-1, keepdims=True)
    assert np.max(np.abs(back - case["m"]) / scale) < 1e-12


def test_linear_leakage_against_matrix_chain(case):
    d, rows, q, m = case["d"], case["rows"], case["q"], case["m"]
    truth = dict(case["truth"])
    v_lin = st.corrupt(m, truth, d, rows, q)
    v_mat = st.corrupt_matrix(m, truth, d, rows, q)
    scale = np.abs(m).max(axis=-1, keepdims=True)
    gp, gq = st.diagonal(truth, d, rows)
    g = np.abs(gp).max(-1) * np.abs(gq).max(-1)
    dmax = np.abs(truth["leakage"]).max()
    ap = q[rows.tindex, rows.a1] + st.RECEPTOR_ANGLE
    aq = q[rows.tindex, rows.a2] + st.RECEPTOR_ANGLE
    w = st.rotate(m, ap, aq)
    cross = np.abs(w[..., 1:3]).max(-1)
    # CASA's linear Df leaves out d times the cross hands in the parallel
    # hands and everything of second order in d.
    bound = g * (2 * dmax * cross + 3 * dmax**2 * np.abs(w).max(-1))
    assert np.all(np.abs(v_lin - v_mat).max(-1) <= bound + 1e-12 * scale[..., 0])
    truth["leakage"] = np.zeros_like(truth["leakage"])
    diff = np.abs(
        st.corrupt(m, truth, d, rows, q) - st.corrupt_matrix(m, truth, d, rows, q)
    )
    assert np.max(diff / scale) < 1e-12


def test_casa_gauge_is_the_same_chain(case):
    d, rows, q, m = case["d"], case["rows"], case["q"], case["m"]
    truth = case["truth"]
    g = st.casa_gauge(truth, d.refant, d.freq, d.nu0)
    as_truth = {
        "bandpass": g["bandpass"],
        "k": g["k"],
        "kcross": g["kcross"],
        "gain": g["gain"],
        "selfcal": np.ones_like(truth["selfcal"]),
        "xf": g["xf"],
        "leakage": g["leakage"],
    }
    v = st.corrupt(m, truth, d, rows, q)
    vg = st.corrupt(m, as_truth, d, rows, q)
    # The removed refant phase leaves one common phase per hand pair, which
    # cancels on every baseline; the truth is built so that it is exact.
    scale = np.abs(v).max(axis=-1, keepdims=True)
    assert np.max(np.abs(vg - v) / scale) < 1e-10
    assert np.all(g["tau_ns"][d.refant] == 0)
    assert np.all(g["leakage"][d.refant, :, 0] == 0)
    assert np.allclose(np.angle(g["gain"][:, d.refant]), 0, atol=1e-12)


def test_jones_ranges(case):
    t = case["truth"]
    tau = np.abs(t["tau_ns"])
    assert tau.min() >= 1.0 and tau.max() <= 10.0
    leak = np.abs(t["leakage"])
    leak[0, :, 0] = 0.02
    assert leak.min() >= 0.01 - 1e-12 and leak.max() <= 0.03 + 1e-12
    xf = np.degrees(np.angle(t["xf"]))
    assert np.ptp(xf) > 10.0 and 10.0 < np.abs(xf).mean() < 90.0


def test_target_prediction_against_numpy(case):
    d, sky, uvw = case["d"], case["sky"], case["uvw"]
    sel = np.flatnonzero(case["fields"][case["rows"].tindex] == 3)[:50]
    got = st.target_coherency(uvw[sel], d.freq, sky)
    nu = d.freq
    u, v, w = (uvw[sel, k][:, None] for k in range(3))
    ref = np.zeros((len(sel), len(nu), 4), complex)
    for c in sky:
        n1 = math.sqrt(1 - c["l"] ** 2 - c["m"] ** 2) - 1
        ph = np.exp(2j * math.pi * nu / st.C * (u * c["l"] + v * c["m"] + w * n1))
        fw = c["fwhm_arcsec"] * st.ARCSEC
        env = np.exp(
            -(math.pi**2) / (4 * math.log(2)) * fw**2 * (u**2 + v**2) * (nu / st.C) ** 2
        )
        i = c["flux"] * (nu / c["ref_freq_hz"]) ** c["alpha"] * env * ph
        chi = c["chi0_deg"] * st.DEG + c["rm"] * (st.C / nu) ** 2
        qq, uu = c["p"] * np.cos(2 * chi) * i, c["p"] * np.sin(2 * chi) * i
        ref += np.stack([i + qq, uu, uu, i - qq], -1)
    assert np.max(np.abs(got - ref)) / np.abs(ref).max() < 1e-9


def test_noise_is_keyed_by_integration(case):
    d = case["d"]
    a = st.noise_integration(d, 7, 10)
    b = st.noise_integration(d, 7, 10)
    c = st.noise_integration(d, 8, 10)
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    big = st.noise_integration(d, 3, 2000)
    parts = np.concatenate([big.real.ravel(), big.imag.ravel()])
    se = d.sigma / math.sqrt(2 * (len(parts) - 1))
    assert abs(parts.std() - d.sigma) < 4 * se


def test_rfi_mask_matches_events(case):
    d, rows = case["d"], case["rows"]
    events = st.rfi_events(d, len(case["times"]))
    r = st.rfi_chunk(events, d, rows, st.enu_baselines(d))
    assert np.any(r != 0)
    chans = sorted({c for e in events for c in e["chans"]})
    other = np.setdiff1d(np.arange(d.nchan), chans)
    assert np.all(r[:, other] == 0)
