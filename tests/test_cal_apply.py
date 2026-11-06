"""The Rust apply kernel (task C4a, research/c4a-apply.md) against
`caltable.correct` by class C, its round trip, and its thread counts."""

import numpy as np
import pytest
from rang import cal_apply
from rang.formats import caltable

SEED = 20261106
NANT, NTIME, NCHAN = 5, 12, 48


def freqs(n):
    return 1.0e9 + 0.8e9 * np.arange(n) / n


def subtables(n):
    return {"SPECTRAL_WINDOW": {"CHAN_FREQ": [freqs(n)]}}


def chunk(rng):
    t0 = 5.0e9
    rows = [
        (t0 + 8.0 * t, p, q)
        for t in range(NTIME)
        for p in range(NANT)
        for q in range(p + 1, NANT)
    ]
    time = np.array([r[0] for r in rows])
    a1 = np.array([r[1] for r in rows])
    a2 = np.array([r[2] for r in rows])
    shape = (len(rows), NCHAN, 4)
    data = (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(np.complex64)
    flag = rng.random(shape) < 0.05
    return data, flag, time, a1, a2


def tables(rng, time):
    ants = list(range(NANT))
    t_sol = np.linspace(time.min() - 3.0, time.max() + 2.0, 4)
    g = (1 + 0.2 * rng.standard_normal((4, NANT, 1, 2))) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (4, NANT, 1, 2))
    )
    gflag = np.zeros(g.shape, bool)
    gflag[1, NANT - 1, 0, 1] = True
    gflag[3, 1, 0, 0] = True
    b = (1 + 0.1 * rng.standard_normal((1, NANT, NCHAN, 2))) * np.exp(
        1j * 0.3 * rng.standard_normal((1, NANT, NCHAN, 2))
    )
    bflag = np.zeros(b.shape, bool)
    bflag[0, 2, 10:17, :] = True
    k = rng.normal(0, 2.0, (2, NANT, 1, 2))
    tt = np.exp(1j * rng.uniform(-np.pi, np.pi, (4, NANT, 1, 1)))
    d = 0.05 * (
        rng.standard_normal((1, NANT, NCHAN, 2))
        + 1j * rng.standard_normal((1, NANT, NCHAN, 2))
    )
    dflag = np.zeros(d.shape, bool)
    dflag[0, 3, 20:25, 0] = True
    dflag[0, 1, :, 1] = True
    one, full = subtables(1), subtables(NCHAN)
    mid = [float(np.mean(time))]
    return {
        "G": caltable.from_gains("G", t_sol, ants, g, gflag, subtables=one),
        "B": caltable.from_gains("B", mid, ants, b, bflag, subtables=full),
        "K": caltable.from_gains("K", t_sol[[0, 3]], ants, k, subtables=one),
        "T": caltable.from_gains("T", t_sol, ants, tt, subtables=one),
        "Df": caltable.from_gains("Df", mid, ants, d, dflag, subtables=full),
    }


@pytest.fixture(scope="module")
def case():
    rng = np.random.default_rng(SEED)
    data, flag, time, a1, a2 = chunk(rng)
    return data, flag, time, a1, a2, tables(rng, time)


CASES = [
    ["G"],
    ["B"],
    ["K"],
    ["T"],
    ["Df"],
    ["K", "G", "B", "Df"],
    ["T", "Df", "B", "G", "K"],
]


@pytest.mark.parametrize("names", CASES, ids=["+".join(c) for c in CASES])
@pytest.mark.parametrize("mode", ["linear", "nearest"])
def test_against_caltable_correct(case, names, mode):
    data, flag, time, a1, a2, tabs = case
    chosen = [tabs[n] for n in names]
    exp, eflag = caltable.correct(
        data, flag, time, a1, a2, freqs(NCHAN), chosen, time_interp=mode
    )
    got, gflag = cal_apply.apply(
        data, flag, time, a1, a2, freqs(NCHAN), chosen, interp=mode
    )
    if "Df" not in names:
        assert np.array_equal(gflag, eflag)
    # With Df the flags differ by design: caltable.correct flags all four
    # correlations for a bad leakage, the kernel follows CASA's JonesGenLin
    # (research/c4a-apply.md), so values are compared where both are unflagged.
    summary = cal_apply.class_c(got, exp.astype(np.complex64), ~eflag & ~gflag)
    # The kernel tracks and unwraps phases in float32 as CASA does
    # (RIorAPArray::trackPhase, CTPatchedInterp::resampleInFreq); caltable.py
    # does not, so the two can differ by a few float32 steps beyond class C
    # (research/c4a-apply.md section 5.2). Against CASA itself the kernel is
    # within class C.
    assert summary["pass"] or summary["max_float32_eps_of_cell"] < 32, summary


def test_df_propagates_parallel_hand_flags_to_the_cross_hands(case):
    data, flag, time, a1, a2, tabs = case
    clean = np.zeros_like(flag)
    clean[:7, 3:9, 0] = True  # XX only
    unflagged = caltable.from_gains(
        "Df",
        [float(np.mean(time))],
        list(range(NANT)),
        tabs["Df"].params.reshape(1, NANT, NCHAN, 2),
        subtables=subtables(NCHAN),
    )
    _, gflag = cal_apply.apply(data, clean, time, a1, a2, freqs(NCHAN), [unflagged])
    want = clean.copy()
    want[:7, 3:9, 1:3] = True
    assert np.array_equal(gflag, want)
    _, gflag = cal_apply.apply(data, clean, time, a1, a2, freqs(NCHAN), [tabs["K"]])
    assert np.array_equal(gflag, clean)


def test_df_bad_leakage_is_minus_one_on_both(case):
    data, flag, time, a1, a2, tabs = case
    clean = np.zeros_like(flag)
    got, gflag = cal_apply.apply(data, clean, time, a1, a2, freqs(NCHAN), [tabs["Df"]])
    # Baseline (0, 1): antenna 1's d_y is bad, so YX uses d_x,1 = -1 (CASA's
    # setMatByOk) and stays unflagged.
    r = np.flatnonzero((a1 == 0) & (a2 == 1))
    d0 = tabs["Df"].params[0].astype(complex)  # antenna 0, (chan, 2)
    v = data[r].astype(complex)
    want = v[..., 2] - (d0[None, :, 1] * v[..., 0] + np.conj(-1.0) * v[..., 3])
    assert not gflag[r][..., 2].any()
    assert np.allclose(got[r][..., 2], want, rtol=1e-5, atol=1e-6)


def test_df_flags_the_cross_hand_that_uses_a_flagged_leakage(case):
    data, flag, time, a1, a2, tabs = case
    clean = np.zeros_like(flag)
    _, gflag = cal_apply.apply(data, clean, time, a1, a2, freqs(NCHAN), [tabs["Df"]])
    # Antenna 1's d_y is flagged in every channel; antenna 3's d_x only in
    # channels 20-24, which are bridged, not flagged.
    assert not gflag[..., 0].any() and not gflag[..., 3].any()
    assert np.array_equal(
        gflag[..., 1], np.broadcast_to((a2 == 1)[:, None], gflag.shape[:2])
    )
    assert np.array_equal(
        gflag[..., 2], np.broadcast_to((a1 == 1)[:, None], gflag.shape[:2])
    )


def test_round_trip(case):
    data, flag, time, a1, a2, tabs = case
    chosen = [tabs[n] for n in ("K", "G", "B", "Df")]
    for mode in ("linear", "caracal", "nearest,nearest"):
        bad, f1 = cal_apply.apply(
            data,
            flag,
            time,
            a1,
            a2,
            freqs(NCHAN),
            chosen,
            interp=mode,
            direction="corrupt",
        )
        back, f2 = cal_apply.apply(
            bad, flag, time, a1, a2, freqs(NCHAN), chosen, interp=mode
        )
        assert np.array_equal(f1, f2)
        assert np.all(f2 >= flag) and f2.any() and not f2.all()
        summary = cal_apply.class_c(back, data, ~f2)
        assert summary["pass"], (mode, summary)


def test_thread_counts_bit_identical(case):
    data, flag, time, a1, a2, tabs = case
    chosen = [tabs[n] for n in ("K", "G", "B", "Df")]
    ref = cal_apply.apply(data, flag, time, a1, a2, freqs(NCHAN), chosen, threads=1)
    for threads in (2, 4, 16):
        got = cal_apply.apply(
            data, flag, time, a1, a2, freqs(NCHAN), chosen, threads=threads
        )
        assert got[0].tobytes() == ref[0].tobytes()
        assert np.array_equal(got[1], ref[1])


def test_frequency_nearest_differs_from_linear_only_off_grid(case):
    data, flag, time, a1, a2, _ = case
    # Phase slopes that differ per antenna, so that a baseline's product is
    # not constant between solution channels.
    slope = (
        np.arange(1, NANT + 1)[None, :, None, None] * np.arange(6)[None, None, :, None]
    )
    coarse = caltable.from_gains(
        "B",
        [float(np.mean(time))],
        list(range(NANT)),
        np.exp(1j * slope * np.ones((1, 1, 1, 2))),
        subtables={"SPECTRAL_WINDOW": {"CHAN_FREQ": [freqs(NCHAN)[::8]]}},
    )
    lin, _ = cal_apply.apply(
        data, flag, time, a1, a2, freqs(NCHAN), [coarse], interp="linear,linear"
    )
    near, _ = cal_apply.apply(
        data, flag, time, a1, a2, freqs(NCHAN), [coarse], interp="linear,nearest"
    )
    on_grid = np.zeros(NCHAN, bool)
    on_grid[::8] = True
    assert np.allclose(lin[:, on_grid], near[:, on_grid], rtol=1e-6, atol=0)
    assert not np.allclose(lin[:, ~on_grid], near[:, ~on_grid], rtol=1e-3, atol=0)


@pytest.mark.parametrize("vis_cal", ["Kcross Jones", "Xf Jones"])
def test_malformed_cross_hand_tables_refused(case, vis_cal):
    # KCROSS and Xf are applied since task C6 (tests/test_cal_pol.py); a G
    # table relabelled as one has the wrong parameter layout and is refused.
    data, flag, time, a1, a2, tabs = case
    table = caltable.CalTable(
        vis_cal, tabs["G"].main, tabs["G"].subtables, dict(tabs["G"].keywords)
    )
    with pytest.raises(ValueError, match="params must hold|parameters per channel"):
        cal_apply.apply(data, flag, time, a1, a2, freqs(NCHAN), [table])


def test_interp_strings():
    assert cal_apply.parse_interp("linear") == (0, 0)
    assert cal_apply.parse_interp("nearest") == (1, 0)
    assert cal_apply.parse_interp("linear,nearest") == (0, 1)
    for bad in ("cubic", "linearflag", "linear,nearestflag", "a,b,c"):
        with pytest.raises(ValueError):
            cal_apply.parse_interp(bad)
