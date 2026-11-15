"""E2-B arm A3 (research/e2b-misses.md 9.23): `calibrate.casa_phase_weights`,
CASA's phase-only estimator for calmode `p` solves. Off, every solve and the
stage hash are as before, and the key is refused without `average_freq`;
on, a calmode `p` G solve equals a NumPy reference of CASA's steps (divide
by the model per channel with weight w|M|^2, average in time and frequency,
normalise to unit amplitude with weight times amp^2, then the unchanged
solver on a unit model), chunked or not, alone and after `average_time`;
calmode `ap` ignores it; the chain passes it to Gpol only."""

import numpy as np
import pytest
from rang import (
    cal_chain,
    cal_delay,
    cal_gain,
    cal_pol,
    core_config,
    core_ms,
    core_ms_write,
)
from test_e2_average_freq import np_freq
from test_e2_average_time import budget, cal_ms, np_average, pol_ms, prepared, unit  # noqa: F401

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


def np_divided(data, model, weights, flag):
    """CASA's divideCorrByModel on the parallel hands, in NumPy."""
    data, model = data.astype(np.complex128), np.broadcast_to(model, data.shape)
    model = model.astype(np.complex128)
    weights = np.broadcast_to(weights, data.shape).astype(np.float64)
    flag = np.broadcast_to(flag, data.shape).copy()
    d, m, w = data.copy(), model.copy(), weights.copy()
    for c in (0, 3):
        ok = ~flag[..., c] & (np.abs(model[..., c]) > 0)
        d[..., c] = np.where(
            ok, data[..., c] / np.where(ok, model[..., c], 1), data[..., c]
        )
        w[..., c] = np.where(ok, weights[..., c] * np.abs(model[..., c]) ** 2, 0)
        m[..., c] = np.where(ok, 1, model[..., c])
        flag[..., c] |= ~ok
    return d, m, w, flag


def np_phase_only(data, weights, flag):
    d, w = data.astype(np.complex128).copy(), weights.astype(np.float64).copy()
    for c in (0, 3):
        a = np.abs(d[..., c])
        ok = ~flag[..., c] & (a > 0)
        d[..., c] = np.where(ok, d[..., c] / np.where(ok, a, 1), d[..., c])
        w[..., c] = np.where(ok, w[..., c] * a**2, w[..., c])
    return d, w


def test_divided_and_phase_only_equal_the_reference():
    rng = np.random.default_rng(921)
    shape = (5, 6, 4)
    cplx = lambda: rng.normal(size=shape) + 1j * rng.normal(size=shape)
    data, model = cplx().astype(np.complex64), cplx().astype(np.complex64)
    model[1, 2, 0] = 0  # a zero parallel-hand model: flagged, weight 0
    model[..., 1:3] = 0  # an unpolarised model: zero cross hands, left alone
    weights = rng.uniform(0.5, 2.0, shape).astype(np.float32)
    flag = rng.random(shape) < 0.2
    got = cal_gain.model_divided(data, model, weights, flag)
    want = np_divided(data, model, weights, flag)
    for g, w in zip(got, want):
        assert np.allclose(g, w, rtol=2e-6, atol=1e-7)
    assert got[3][1, 2, 0] and got[2][1, 2, 0] == 0
    for k, x in enumerate((data, model, weights, flag)):
        assert np.array_equal(got[k][..., 1:3], np.asarray(x)[..., 1:3])
    d, m, w = cal_gain.phase_only(got[0], got[1], got[2], got[3])
    wd, ww = np_phase_only(want[0], want[2], want[3])
    ok = ~got[3]
    assert np.allclose(d[ok], wd[ok], rtol=2e-6, atol=1e-7)
    assert np.allclose(w[ok], ww[ok], rtol=2e-6)
    assert np.allclose(np.abs(d[..., (0, 3)][ok[..., (0, 3)]]), 1, atol=1e-6)
    assert (m[..., (0, 3)][ok[..., (0, 3)]] == 1).all()


def test_off_is_the_plain_solve_the_hash_stays_and_on_needs_average_freq(cal_ms):  # noqa: F811
    kw = {"field_id": 0, "solint": "int", "refant": 0, "minblperant": 2, "calmode": "p",
          "model": unit(cal_ms, 0), "weight_column": "WEIGHT", "average_freq": True}  # fmt: skip
    a = cal_gain.gaincal(cal_ms, **kw)[0]
    b = cal_gain.gaincal(cal_ms, casa_phase_weights=False, **kw)[0]
    assert cal_chain._sha(a) == cal_chain._sha(b)
    with pytest.raises(ValueError, match="average_freq"):
        cal_gain.gaincal(
            cal_ms, **dict(kw, average_freq=False), casa_phase_weights=True
        )
    raw = {"version": 1, "fields": {"fcal": ["CAL"]},
           "calibrate": {"primary": {"terms": [{"type": "G", "name": "G"}]}}}  # fmt: skip
    config, errors = core_config.resolve(raw)
    assert not errors and config["calibrate"]["casa_phase_weights"] is False
    before = core_config.stage_hash(config, "calibrate")
    gone = dict(config, calibrate={k: v for k, v in config["calibrate"].items()
                                   if k != "casa_phase_weights"})  # fmt: skip
    assert core_config.stage_hash(gone, "calibrate") == before
    on = dict(config, calibrate=dict(config["calibrate"], casa_phase_weights=True))
    assert core_config.stage_hash(on, "calibrate") != before
    paths = [r.path for r in core_config.refusals(on, ["calibrate"])]
    assert "calibrate.casa_phase_weights" in paths
    both = dict(on, calibrate=dict(on["calibrate"], average_freq=True))
    paths = [r.path for r in core_config.refusals(both, ["calibrate"])]
    assert "calibrate.casa_phase_weights" not in paths


def resolved_model(ms, field, seed=922):
    """A model that is not the data's: the unit point times a smooth
    complex factor per row and channel, as a partly resolved source."""
    base = np.asarray(unit(ms, field))
    rng = np.random.default_rng(seed)
    nrow, nchan = base.shape[:2]
    f = 1 + 0.3 * rng.normal(size=(nrow, 1, 1)) * np.exp(
        1j * np.linspace(0, 1, nchan)[None, :, None] * rng.normal(size=(nrow, 1, 1))
    )
    return (base * f).astype(np.complex64)


@pytest.mark.parametrize("solint", ["inf", "int", 30.0])
@pytest.mark.parametrize("average_time", [False, True])
def test_p_equals_casas_steps_in_numpy(cal_ms, solint, average_time):  # noqa: F811
    model = resolved_model(cal_ms, 0)
    k = cal_delay.gaincal(
        cal_ms, field_id=0, refant=0, model=unit(cal_ms, 0), weight_column="WEIGHT"
    )
    fld, arr, _ = prepared(cal_ms, 0, "G", model=model, weight_column="WEIGHT",
                           gaintable=[k[0]], uvrange=">200")  # fmt: skip
    m = fld.meta
    tb, keys = cal_gain.solint_bins(m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], solint)
    fr = fld.flag_row | fld.auto
    d, mo, w, f = np_divided(arr["data"], arr["model"], arr["weights"], arr["flag"])
    if average_time:
        ref, tb2, a1, a2, fr2 = np_average(tb, m["ANTENNA1"], m["ANTENNA2"], fr,
                                           d.astype(np.complex64), mo.astype(np.complex64),
                                           w.astype(np.float32), f)  # fmt: skip
        d, mo, w, f = np_freq(ref["data"], ref["model"], ref["weights"], ref["flag"])
    else:
        tb2, a1, a2, fr2 = tb, m["ANTENNA1"], m["ANTENNA2"], fr
        d, mo, w, f = np_freq(d, mo, w, f | fr[:, None, None])
    d, w = np_phase_only(d, w, f)
    mo = np.where(f, 0, 1).astype(np.complex64)
    with core_ms.open_table(cal_ms / "ANTENNA") as t:
        positions = t.getcol("POSITION")
    want = cal_gain.solve(d.astype(np.complex64), mo, w.astype(np.float32), f, fr2, a1, a2,
                          tb2, nant=4, calmode="p", refant=0, minblperant=2,
                          positions=positions)  # fmt: skip
    kw = {"field_id": 0, "solint": solint, "refant": 0, "minblperant": 2, "calmode": "p",
          "gaintable": [k[0]], "model": model, "weight_column": "WEIGHT",
          "uvrange": ">200", "average_time": average_time, "average_freq": True}  # fmt: skip
    plain = cal_gain.gaincal(cal_ms, **kw)[1]
    for b in (None, budget(1600 if average_time else 8000)):
        _, got, info = cal_gain.gaincal(cal_ms, casa_phase_weights=True, budget=b, **kw)
        assert np.array_equal(got.flags, want.flags)
        ok = ~want.flags
        assert np.allclose(got.gains[ok], want.gains[ok], rtol=0, atol=2e-6)
        assert len(info["intervals"]) == len(keys)
    # A model that is not the data's: the estimators differ.
    assert not np.allclose(plain.gains[ok], got.gains[ok], rtol=0, atol=1e-5)


def test_the_solution_times_stay(cal_ms):  # noqa: F811
    kw = {"field_id": 0, "solint": 30.0, "refant": 0, "minblperant": 2, "calmode": "p",
          "model": resolved_model(cal_ms, 0), "weight_column": "WEIGHT",
          "average_freq": True}  # fmt: skip
    a = cal_gain.gaincal(cal_ms, **kw)[0]
    b = cal_gain.gaincal(cal_ms, casa_phase_weights=True, **kw)[0]
    assert np.array_equal(a.column("TIME"), b.column("TIME"))
    assert np.array_equal(a.column("INTERVAL"), b.column("INTERVAL"))


def test_ap_ignores_the_key(cal_ms):  # noqa: F811
    kw = {"field_id": 0, "solint": "inf", "refant": 0, "minblperant": 2, "calmode": "ap",
          "model": resolved_model(cal_ms, 0), "weight_column": "WEIGHT",
          "average_freq": True}  # fmt: skip
    a = cal_gain.gaincal(cal_ms, **kw)[0]
    b = cal_gain.gaincal(cal_ms, casa_phase_weights=True, **kw)[0]
    assert cal_chain._sha(a) == cal_chain._sha(b)


def test_gpol_takes_the_key(pol_ms):  # noqa: F811
    k = cal_delay.gaincal(pol_ms, field_id=0, refant=0, model=unit(pol_ms, 0),
                          weight_column="WEIGHT")  # fmt: skip
    gk = {"field_id": 1, "gaintable": [k[0]], "weight_column": "WEIGHT", "refant": 0,
          "minblperant": 2, "solint": "inf", "minsnr": 0.0, "average_freq": True,
          "model": unit(pol_ms, 1, (1.0, 0.05, 0.08, 0.0))}  # fmt: skip
    for extra in ({}, {"average_time": True, "budget": budget(1600)}):
        off = cal_pol.gpol(pol_ms, **gk, **extra)[1]
        on = cal_pol.gpol(pol_ms, casa_phase_weights=True, **gk, **extra)[1]
        again = cal_pol.gpol(pol_ms, casa_phase_weights=True, **gk, **extra)[1]
        assert np.array_equal(on.gains, again.gains)
        assert np.array_equal(off.flags, on.flags)
        assert not np.array_equal(off.gains, on.gains)


def test_the_chain_passes_the_key_to_calmode_p_only(cal_ms, tmp_path):  # noqa: F811
    terms = []
    for kind, name, extra in (("K", "K", {}), ("G", "G", {"calmode": "ap"}),
                              ("B", "B", {"fillgaps": 0}), ("G", "Gp", {"calmode": "p"})):  # fmt: skip
        terms.append({
            "type": kind, "name": name, "fields": [0], "solint": "inf", "combine": "",
            "refant": 0, "refantmode": "flex", "minsnr": 3.0, "minblperant": 2,
            "uvrange": "", "preapply": [t["name"] for t in terms if t["name"] != "Gp"],
            "interp": [], "max_iterations": 50, "stop_criterion": 1e-7,
            "stop_fraction": 0.99, "model": "unit", **extra,
        })  # fmt: skip
    out = {}
    for on in (False, True):
        res = cal_chain.run(cal_ms, terms, out_dir=tmp_path / f"t{on}", model_column="MODEL_DATA",
                            weight_column="WEIGHT", average_freq=True,
                            casa_phase_weights=on)  # fmt: skip
        out[on] = {
            n: cal_chain._sha(res["tables"][n]["table"]) for n in ("K", "G", "B", "Gp")
        }
    for n in ("K", "G", "B"):
        assert out[False][n] == out[True][n]
    with pytest.raises(ValueError, match="average_freq"):
        cal_chain.run(cal_ms, terms, out_dir=tmp_path / "x", model_column="MODEL_DATA",
                      weight_column="WEIGHT", casa_phase_weights=True)  # fmt: skip


def _term(kind, name, fields, preapply, **extra):
    return {
        "type": kind, "name": name, "fields": fields, "solint": "inf", "combine": "",
        "refant": 0, "refantmode": "flex", "minsnr": 0.0, "minblperant": 2,
        "uvrange": "", "preapply": preapply, "interp": [], "max_iterations": 50,
        "stop_criterion": 1e-7, "stop_fraction": 0.99, "model": "unit", **extra,
    }  # fmt: skip


def test_the_chain_gives_gpol_the_key(pol_ms, tmp_path):  # noqa: F811
    """Through `cal_chain.run` (the configuration's path), Gpol with the key
    equals the direct `cal_pol.gpol` call with it and differs from the
    chain without it; K and G (ap) do not move."""
    terms = [
        _term("K", "K", [0], []),
        _term("G", "G", [0], ["K"], calmode="ap"),
        _term("Gpol", "Gpol", [1], ["K", "G"], parang=True, frame="casa"),
    ]
    out = {}
    for on in (False, True):
        res = cal_chain.run(pol_ms, terms, out_dir=tmp_path / f"t{on}", model_column="MODEL_DATA",
                            weight_column="WEIGHT", average_freq=True,
                            casa_phase_weights=on)  # fmt: skip
        out[on] = {n: res["tables"][n]["table"] for n in ("K", "G", "Gpol")}
    for n in ("K", "G"):
        assert cal_chain._sha(out[False][n]) == cal_chain._sha(out[True][n])
    assert cal_chain._sha(out[False]["Gpol"]) != cal_chain._sha(out[True]["Gpol"])
    direct = cal_pol.gpol(
        pol_ms, field_id=1, solint="inf", combine="", refant=0, refantmode="flex",
        minsnr=0.0, minblperant=2, uvrange="", gaintable=[out[True]["K"], out[True]["G"]],
        interp="linear", parang=True, frame="casa", weight_column="WEIGHT",
        model=unit(pol_ms, 1), max_iterations=50, stop_criterion=1e-7,
        stop_fraction=0.99, average_freq=True, casa_phase_weights=True,
    )[0]  # fmt: skip
    assert np.array_equal(direct.params, out[True]["Gpol"].params)
    assert np.array_equal(direct.flags, out[True]["Gpol"].flags)


def test_the_e2b_amended_configuration_takes_the_key():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "research" / "results"
    path = path / "e2-acceptance-scripts" / "e2b-amended.yaml"
    if not path.exists():
        path = (
            Path(__file__).resolve().parents[1] / "tests" / "data" / "w2" / "e2b.yaml"
        )
    raw = core_config.load(path)
    raw["calibrate"]["average_freq"] = True
    raw["calibrate"]["casa_phase_weights"] = True
    core_config.validate(raw, ["calibrate"])
