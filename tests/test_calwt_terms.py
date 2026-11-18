# SPDX-License-Identifier: MIT
"""Task calwt-terms (research/calwt-terms.md): `calibrate.k_calwt`,
`g_calwt`, `gpol_calwt`, `kcross_calwt` and `df_calwt`. A solve's weights
are scaled by CASA's `calwt` factor F(p, h) F(q, h') of the pre-applied
tables that correct its data (lower VisCal type; B, G, T scale, K, KCROSS,
X, D do not), computed in the Rust kernel (`rang.cal_apply.calwt_scale`).
Off, nothing changes; on, the factor is CASA's `calcWtScale` product,
structural no-ops stay byte-identical, the chain threads each key to its
solve type only, and the keys are out of the stage hash at their default."""

import numpy as np
import pytest
from rang import (
    cal_apply,
    cal_bandpass,
    cal_chain,
    cal_delay,
    cal_gain,
    cal_pol,
    core_ms_write,
    core_pipeline,
)
from test_c2e_calibrate import calibrator_ms
from test_c6w_polwire import _with_feed
from test_xf_avg_fix import POL, cal_pol_budget, unit
from test_xf_calwt import _per_antenna

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

KEYS = ("k_calwt", "g_calwt", "gpol_calwt", "kcross_calwt", "df_calwt")


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    """C2e's calibrator MS with C6w's FEED and K, G, B solved on field 0."""
    pytest.importorskip("astropy")
    ms = _with_feed(
        calibrator_ms(tmp_path_factory.mktemp("calwtterms") / "c.ms", seed=34)
    )
    kw = {"field_id": 0, "refant": 0, "model": unit(ms, 0), "weight_column": "WEIGHT"}
    k = cal_delay.gaincal(ms, **kw)[0]
    g = cal_gain.gaincal(
        ms, calmode="ap", gaintable=[k], combine="scan", minblperant=2, **kw
    )[0]
    b = cal_bandpass.bandpass(
        ms, gaintable=[k, g], combine="scan", minblperant=2, **kw
    )[0]
    return ms, [k, g, b]


def _rows(ms, field):
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        pick = t.getcol("FIELD_ID") == field
        return (
            t.getcol("TIME")[pick],
            t.getcol("ANTENNA1")[pick],
            t.getcol("ANTENNA2")[pick],
        )


def _want(f, a1, a2):
    return np.stack(
        [f[a1, h1] * f[a2, h2] for h1, h2 in ((0, 0), (0, 1), (1, 0), (1, 1))], -1
    )


# -- the kernel (control C4) -----------------------------------------------------------


def test_kernel_is_calcwtscale_and_xf_calwt(solved):
    ms, tables = solved
    time, a1, a2 = _rows(ms, 1)
    got = cal_gain.calwt_factor(tables, "linear", "Xf", time, a1, a2, nant=4)
    want = _want(_per_antenna(tables, 4), a1, a2)
    assert np.allclose(got, want, rtol=1e-6, atol=0)
    assert np.ptp(want) > 0.05  # the fixture's amplitudes are not all one
    fld = cal_pol._PolField(
        ms, **cal_pol._load_defaults({"field_id": 1, "solved": "Xf", "gaintable":
                                       tables, "weight_column": "WEIGHT"})
    )  # fmt: skip
    xf_path = fld.calwt_factor(time, a1, a2)
    assert np.allclose(got, xf_path, rtol=1e-6, atol=0)


def test_only_the_tables_that_correct_the_data_count(solved):
    ms, (k, g, b) = solved
    time, a1, a2 = _rows(ms, 0)
    ones = np.ones((len(time), 4))
    # B is the lowest type; a G solve with K only, K forces calwt off.
    assert np.array_equal(
        cal_gain.calwt_factor([k, g], "linear", "B", time, a1, a2, 4), ones
    )
    assert np.array_equal(
        cal_gain.calwt_factor([k], "linear", "G", time, a1, a2, 4), ones
    )
    only_b = cal_gain.calwt_factor([b], "linear", "Df", time, a1, a2, 4)
    # A K solve with G and B: B corrects the data, G corrupts the model.
    assert np.array_equal(
        cal_gain.calwt_factor([g, b], "linear", "K", time, a1, a2, 4), only_b
    )
    # A G-type solve (Gpol) with G: G is not lower than G.
    assert np.array_equal(
        cal_gain.calwt_factor([k, g, b], "linear", "G", time, a1, a2, 4), only_b
    )
    both = cal_gain.calwt_factor([k, g, b], "linear", "Df", time, a1, a2, 4)
    assert not np.allclose(both, only_b)
    assert np.array_equal(
        cal_apply.calwt_scale(time, a1, a2, [k], nant=4), ones
    )  # K alone: no weight kind


# -- the solves --------------------------------------------------------------------


def _same(a, b):
    ta, tb = a[0], b[0]
    return np.array_equal(ta.params, tb.params) and np.array_equal(ta.flags, tb.flags)


def test_off_is_byte_identical_and_on_moves_the_solves(solved):
    ms, (k, g, b) = solved
    kw = {"field_id": 0, "refant": 0, "model": unit(ms, 0), "weight_column": "WEIGHT",
          "combine": "scan"}  # fmt: skip
    solves = {
        "K": lambda **o: cal_delay.gaincal(ms, gaintable=[g, b], **kw, **o),
        "G": lambda **o: cal_gain.gaincal(
            ms, calmode="ap", gaintable=[k, b], minblperant=2, **kw, **o
        ),
    }
    for name, solve in solves.items():
        base, off, on = solve(), solve(solve_calwt=False), solve(solve_calwt=True)
        assert _same(base, off), name
        assert not _same(base, on), name
        assert on[2].get("calwt") is True and "calwt" not in base[2]
    # Structural no-op: G with K only.
    noop = {"calmode": "ap", "gaintable": [k], "minblperant": 2}
    assert _same(
        cal_gain.gaincal(ms, **noop, **kw),
        cal_gain.gaincal(ms, **noop, solve_calwt=True, **kw),
    )


def test_polarisation_solves_and_load_paths(solved):
    ms, tables = solved
    kw = {"field_id": 1, "model": unit(ms, 1, POL), "weight_column": "WEIGHT",
          "gaintable": tables, "interp": "linear"}  # fmt: skip
    base = cal_pol.load(ms, solved="Kcross", **kw)
    on = cal_pol.load(ms, solved="Kcross", solve_calwt=True, **kw)
    time, a1, a2 = base.cols["TIME"], base.cols["ANTENNA1"], base.cols["ANTENNA2"]
    f = cal_gain.calwt_factor(tables, "linear", "Kcross", time, a1, a2, 4)
    ok = base.weights > 0
    ratio = on.weights / np.where(ok, base.weights, 1)
    assert np.allclose(np.broadcast_to(f[:, None, :], ratio.shape)[ok], ratio[ok],
                       rtol=2e-6)  # fmt: skip
    with pytest.raises(ValueError, match="not both"):
        cal_pol.load(ms, solved="Xf", calwt=True, solve_calwt=True, **kw)
    kc = cal_pol.kcross(ms, solve_calwt=True, **kw)[1]
    kc0 = cal_pol.kcross(ms, **kw)[1]
    assert kc.settings.get("solve_calwt") is True and "solve_calwt" not in kc0.settings
    dkw = dict(kw, field_id=0, model=unit(ms, 0), combine="scan", refant=0,
               minblperant=2)  # fmt: skip
    whole = cal_pol.df(ms, solve_calwt=True, **dkw)[1]
    plain = cal_pol.df(ms, **dkw)[1]
    assert not np.array_equal(whole.d, plain.d)
    chunked = cal_pol.df(
        ms, solve_calwt=True, budget=cal_pol_budget(1000, nrows=120), **dkw
    )[1]
    assert np.allclose(chunked.d, whole.d, atol=2e-6)


# -- the chain ---------------------------------------------------------------------


def test_the_chain_threads_each_key_to_its_type(solved, monkeypatch):
    ms, (k, g, b) = solved
    seen = []
    real = cal_gain.calwt_factor

    def spy(tables, interp, solved_type, *args, **kwargs):
        seen.append(solved_type)
        return real(tables, interp, solved_type, *args, **kwargs)

    monkeypatch.setattr(cal_gain, "calwt_factor", spy)
    tabs = {n: {"table": t} for n, t in zip(("K", "G", "B"), (k, g, b))}
    base = {"solint": "inf", "combine": "scan", "refant": 0, "refantmode": "flex",
            "minsnr": 3.0, "minblperant": 2, "uvrange": "", "interp": [],
            "max_iterations": 50, "stop_criterion": 1e-7, "stop_fraction": 0.99,
            "model": "unit"}  # fmt: skip
    gterm = dict(base, type="G", name="G2", calmode="ap", preapply=["K", "B"])
    kterm = dict(base, type="K", name="K2", preapply=["G", "B"])
    common = {"model_column": "MODEL_DATA", "weight_column": "WEIGHT"}
    for term, key in ((gterm, "K"), (kterm, "G"), (gterm, "Gpol")):
        cal_chain._solve_one(ms, term, 0, tabs, dict(common, solve_calwt={key}))
    assert seen == []
    cal_chain._solve_one(ms, gterm, 0, tabs, dict(common, solve_calwt={"G"}))
    cal_chain._solve_one(ms, kterm, 0, tabs, dict(common, solve_calwt={"K"}))
    assert seen and set(seen) == {"G", "K"}
    seen.clear()
    pterm = {"type": "KCROSS", "name": "Kc", "solint": "inf", "combine": "",
             "uvrange": "", "preapply": ["K", "G", "B"], "interp": [], "model": "unit",
             "parang": True, "refant": 0, "estimator": "casa"}  # fmt: skip
    cal_chain._solve_pol(ms, pterm, 1, tabs, dict(common, solve_calwt={"Df"}))
    assert seen == []
    cal_chain._solve_pol(ms, pterm, 1, tabs, dict(common, solve_calwt={"KCROSS"}))
    assert set(seen) == {"Kcross"}
    with pytest.raises(ValueError, match="solve_calwt takes"):
        cal_chain.run(ms, [], out_dir=ms.parent / "never", solve_calwt={"B"})


def test_the_keys_map_to_the_chain_types():
    assert set(core_pipeline.CALWT_KEYS) == set(KEYS)
    assert set(core_pipeline.CALWT_KEYS.values()) == cal_chain.CALWT_TYPES


def test_the_keys_are_out_of_the_stage_hash_at_their_default():
    from rang import core_config

    raw = {"version": 1, "fields": {"fcal": ["A"]},
           "calibrate": {"primary": {"terms": [{"type": "G", "name": "G"}]}}}  # fmt: skip
    config, errors = core_config.resolve(raw)
    assert not errors
    before = core_config.stage_hash(config, "calibrate")
    gone = dict(config, calibrate={k: v for k, v in config["calibrate"].items()
                                   if k not in KEYS})  # fmt: skip
    assert core_config.stage_hash(gone, "calibrate") == before
    for key in KEYS:
        assert config["calibrate"][key] is False
        on = dict(config, calibrate=dict(config["calibrate"], **{key: True}))
        assert core_config.stage_hash(on, "calibrate") != before
