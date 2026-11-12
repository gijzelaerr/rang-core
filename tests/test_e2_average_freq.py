"""E2 (the pre-registered "E2-B amended" arm, research/e2-acceptance.md 6.7):
`calibrate.average_freq`, CASA's frequency pre-averaging of G-type solves
(G, F, Gpol). Off, every solve and the stage hash are as before; on, a G
solve equals a NumPy reference (the prepared rows averaged over channels,
then the unchanged solver on one channel), chunked or not, alone and after
`average_time`; K and B ignore it; Gpol equals the post hoc emulation of
research/e2-average-time.md 4.2 (the kernel's input averaged first)."""

from pathlib import Path

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
from test_e2_average_time import budget, cal_ms, np_average, pol_ms, prepared, unit  # noqa: F401

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


def np_freq(data, model, weights, flag):
    """The reference: per row and correlation the weighted means over the
    unflagged channels; a cell without weight flagged."""
    w = np.where(flag, 0.0, np.broadcast_to(np.asarray(weights, float), data.shape))
    sw = w.sum(1, keepdims=True)
    ok = sw > 0
    d = np.where(ok, (w * data).sum(1, keepdims=True) / np.where(ok, sw, 1), 0)
    m = np.where(ok, (w * model).sum(1, keepdims=True) / np.where(ok, sw, 1), 0)
    return d.astype(np.complex64), m.astype(np.complex64), sw.astype(np.float32), ~ok


def test_frequency_averaged_is_the_weighted_mean():
    rng = np.random.default_rng(7)
    shape = (5, 6, 4)
    data = (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(np.complex64)
    model = (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(np.complex64)
    weights = rng.uniform(0.5, 2.0, shape).astype(np.float32)
    flag = rng.random(shape) < 0.3
    flag[2, :, 1] = True  # one cell with no unflagged channel
    got = cal_gain.frequency_averaged(data, model, weights, flag)
    want = np_freq(data, model, weights, flag)
    assert got[0].shape == (5, 1, 4)
    for g, w in zip(got, want):
        assert np.allclose(g, w, rtol=1e-6, atol=1e-7)
    assert got[3][2, 0, 1] and got[1][2, 0, 1] == 0


def test_off_is_the_plain_solve_and_the_hash_stays(cal_ms):  # noqa: F811
    kw = {"field_id": 0, "solint": "int", "refant": 0, "minblperant": 2,
          "model": unit(cal_ms, 0), "weight_column": "WEIGHT"}  # fmt: skip
    a = cal_gain.gaincal(cal_ms, **kw)[0]
    b = cal_gain.gaincal(cal_ms, average_freq=False, **kw)[0]
    assert cal_chain._sha(a) == cal_chain._sha(b)
    raw = {"version": 1, "fields": {"fcal": ["CAL"]},
           "calibrate": {"primary": {"terms": [{"type": "G", "name": "G"}]}}}  # fmt: skip
    config, errors = core_config.resolve(raw)
    assert not errors and config["calibrate"]["average_freq"] is False
    before = core_config.stage_hash(config, "calibrate")
    gone = dict(config, calibrate={k: v for k, v in config["calibrate"].items()
                                   if k != "average_freq"})  # fmt: skip
    assert core_config.stage_hash(gone, "calibrate") == before
    on = dict(config, calibrate=dict(config["calibrate"], average_freq=True))
    assert core_config.stage_hash(on, "calibrate") != before


@pytest.mark.parametrize("solint", ["inf", "int", 30.0])
@pytest.mark.parametrize("average_time", [False, True])
def test_g_equals_the_numpy_reference(cal_ms, solint, average_time):  # noqa: F811
    model = unit(cal_ms, 0)
    k = cal_delay.gaincal(
        cal_ms, field_id=0, refant=0, model=model, weight_column="WEIGHT"
    )
    fld, arr, _ = prepared(cal_ms, 0, "G", model=model, weight_column="WEIGHT",
                           gaintable=[k[0]], uvrange=">200")  # fmt: skip
    m = fld.meta
    tb, keys = cal_gain.solint_bins(m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], solint)
    if average_time:
        ref, tb2, a1, a2, fr = np_average(tb, m["ANTENNA1"], m["ANTENNA2"],
                                          fld.flag_row | fld.auto, arr["data"],
                                          arr["model"], arr["weights"], arr["flag"])  # fmt: skip
        d, mo, w, f = np_freq(ref["data"], ref["model"], ref["weights"], ref["flag"])
    else:
        tb2, a1, a2 = tb, m["ANTENNA1"], m["ANTENNA2"]
        fr = fld.flag_row | fld.auto
        used = arr["flag"] | fr[:, None, None]
        d, mo, w, f = np_freq(arr["data"], arr["model"], arr["weights"], used)
    with core_ms.open_table(cal_ms / "ANTENNA") as t:
        positions = t.getcol("POSITION")
    want = cal_gain.solve(d, mo, w, f, fr, a1, a2, tb2, nant=4, refant=0,
                          minblperant=2, positions=positions)  # fmt: skip
    kw = {"field_id": 0, "solint": solint, "refant": 0, "minblperant": 2,
          "gaintable": [k[0]], "model": model, "weight_column": "WEIGHT",
          "uvrange": ">200", "average_time": average_time}  # fmt: skip
    # Unaveraged, a solint-inf interval holds 7,680 cells and is solved whole.
    for b in (None, budget(1600 if average_time else 8000)):
        _, got, info = cal_gain.gaincal(cal_ms, average_freq=True, budget=b, **kw)
        assert np.array_equal(got.flags, want.flags)
        ok = ~want.flags
        assert np.allclose(got.gains[ok], want.gains[ok], rtol=0, atol=2e-6)
        assert len(info["intervals"]) == len(keys)


def test_k_and_b_ignore_the_key_in_the_chain(cal_ms, tmp_path):  # noqa: F811
    terms = []
    for kind, name, extra in (("K", "K", {}), ("G", "G", {"calmode": "ap"}),
                              ("B", "B", {"fillgaps": 0})):  # fmt: skip
        terms.append({
            "type": kind, "name": name, "fields": [0], "solint": "inf", "combine": "",
            "refant": 0, "refantmode": "flex", "minsnr": 3.0, "minblperant": 2,
            "uvrange": "", "preapply": [t["name"] for t in terms],
            "interp": [], "max_iterations": 50, "stop_criterion": 1e-7,
            "stop_fraction": 0.99, "model": "unit", **extra,
        })  # fmt: skip
    out = {}
    for on in (False, True):
        res = cal_chain.run(cal_ms, terms, out_dir=tmp_path / f"t{on}", model_column="MODEL_DATA",
                            weight_column="WEIGHT", average_freq=on)  # fmt: skip
        out[on] = {
            n: cal_chain._sha(res["tables"][n]["table"]) for n in ("K", "G", "B")
        }
    assert out[False]["K"] == out[True]["K"]
    assert out[False]["G"] != out[True]["G"]  # B is solved after G, so it may move


def test_gpol_equals_the_kernel_emulation(pol_ms, monkeypatch):  # noqa: F811
    """The key equals research/e2-average-time.md 4.2's emulation (the
    kernel's input averaged over channels), with and without time averaging
    and chunking; the model is rotated by P before either average."""
    k = cal_delay.gaincal(pol_ms, field_id=0, refant=0, model=unit(pol_ms, 0),
                          weight_column="WEIGHT")  # fmt: skip
    gk = {"field_id": 1, "gaintable": [k[0]], "weight_column": "WEIGHT", "refant": 0,
          "minblperant": 2, "solint": "inf", "minsnr": 0.0,
          "model": unit(pol_ms, 1, (1.0, 0.05, 0.08, 0.0))}  # fmt: skip
    # minsnr 0: averaged over time and channels, the 4-antenna fixture leaves
    # 12 samples per interval for 8 parameters, so CASA's reduced-chi2 SNR
    # (rang.cal_gain, core/src/cal/diag.rs) falls below 3; the test is the
    # kernel's input, not the threshold.
    original = cal_gain._kernel

    def emulated(data, model, weights, flag, *args, **kw):
        d, m, w, f = cal_gain.frequency_averaged(data, model, weights, flag)
        return original(d, m, w, f, *args, **dict(kw, freq_bin=None))

    for extra in (
        {},
        {"average_time": True},
        {"average_time": True, "budget": budget(1600)},
    ):
        got = cal_pol.gpol(pol_ms, average_freq=True, **gk, **extra)[1]
        monkeypatch.setattr(cal_gain, "_kernel", emulated)
        want = cal_pol.gpol(pol_ms, **gk, **extra)[1]
        monkeypatch.setattr(cal_gain, "_kernel", original)
        assert np.array_equal(got.flags, want.flags)
        assert np.array_equal(got.gains, want.gains)
        plain = cal_pol.gpol(pol_ms, **gk, **extra)[1]
        assert not np.array_equal(plain.gains, got.gains)


def test_the_e2b_configuration_takes_the_key():
    raw = core_config.load(
        Path(__file__).resolve().parents[1]
        / "research"
        / "results"
        / "e2-acceptance-scripts"
        / "e2b.yaml"
    )
    raw["calibrate"]["average_freq"] = True
    core_config.validate(raw, ["calibrate"])
