"""C6w (research/c6w-polwire.md): Gpol, KCROSS, Xf, Df and P in
`rang-core calibrate` and `apply`. The configuration takes the polcal
section with CARACal's defaults and refuses what `rang.cal_pol` cannot run;
`applycal(parang=True)` equals `rang.cal_pol.apply` bit for bit whatever the
chunking; the KCROSS refinement removes the FFT parabola's bias. The
command-against-library identity on `poldx` is gate 1 of the note (a run,
not a unit test)."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import applycal, cal_pol, core_config, core_ms, core_ms_write, core_pipeline
from test_w2_commands import make_ms

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

POLCAL = {
    "version": 1,
    "fields": {"fcal": ["CAL"], "xcal": ["TGT"]},
    "calibrate": {
        "refant": "m000",
        "model": {"source": "unity"},
        "primary": {"terms": [{"type": "K"}, {"type": "G", "preapply": ["K"]}]},
        "polcal": {
            "model": {"source": "nrao", "name": "3C286"},
            "terms": [
                {"type": "Gpol", "solint": "60s", "preapply": ["K", "G"]},
                {"type": "KCROSS", "name": "Kc", "preapply": ["K", "G", "Gpol"]},
                {"type": "Xf", "combine": "scan", "preapply": ["K", "G", "Gpol", "Kc"]},
                {"type": "Df", "field": ["fcal"], "combine": "scan",
                 "preapply": ["K", "G", "Kc", "Xf"]},
            ],
        },
    },
    "apply": {
        "parang": True,
        "targets": [{"field": ["xcal"], "tables": ["K", "G", "Gpol", "Kc", "Xf", "Df"]}],
    },
}  # fmt: skip


def _config(**changes):
    import copy

    raw = copy.deepcopy(POLCAL)
    for path, value in changes.items():
        node = raw
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return raw


def _problems(raw, stages=("calibrate", "apply")):
    config, errors = core_config.resolve(raw)
    assert errors == [], errors
    return {(r.path, r.task) for r in core_config.refusals(config, stages)}


def test_the_polcal_section_runs_with_carcals_defaults():
    config = core_config.validate(POLCAL, ["calibrate", "apply"])
    pol = config["calibrate"]["polcal"]
    assert pol["frame"] == "casa" and pol["model"]["source"] == "nrao"
    assert "C6" not in "".join(core_config.TASKS)
    text = core_config.defaults_yaml()
    assert "Gpol, KCROSS, Xf, Df (C6w)" in text


def test_what_cal_pol_cannot_run_is_an_error_without_a_task():
    terms = POLCAL["calibrate"]["polcal"]["terms"]
    bad = [dict(t) for t in terms]
    bad[0]["calmode"] = "ap"
    bad[2]["parang"] = False
    bad[2]["preavg"] = 300.0
    bad[3]["clip"] = [0.1, 0.6]
    got = _problems(_config(**{"calibrate.polcal.terms": bad}))
    for path in (
        "calibrate.polcal.terms[0].calmode",
        "calibrate.polcal.terms[2].parang",
        "calibrate.polcal.terms[2].preavg",
        "calibrate.polcal.terms[3].clip",
    ):
        assert (path, "") in got, path
    # A polarisation term outside polcal, and a K term inside it.
    raw = _config()
    raw["calibrate"]["primary"]["terms"].append({"type": "Xf", "name": "X2"})
    raw["calibrate"]["polcal"]["terms"].append({"type": "K", "name": "K2"})
    got = _problems(raw)
    assert ("calibrate.primary.terms[2].type", "") in got
    assert ("calibrate.polcal.terms[4].type", "") in got
    # Polarisation tables need apply.parang; extendflags runs since task E0.
    got = _problems(_config(**{"apply.parang": False}))
    assert ("apply.targets[0].tables", "") in got
    got = _problems(_config(**{"calibrate.polcal.extendflags": True}))
    assert ("calibrate.polcal.extendflags", "") not in got
    got = _problems(_config(**{"calibrate.polcal.model.name": "3C999"}))
    assert ("calibrate.polcal.model.name", "") in got


def _with_feed(ms, angle=-np.pi / 2):
    with core_ms.open_table(ms / "ANTENNA") as t:
        nant = t.nrows
    with core_ms_write.open_table(ms / "FEED", readonly=False) as t:
        t.addrows(nant)
        t.putcol("ANTENNA_ID", np.arange(nant, dtype=np.int32))
        t.putcol("NUM_RECEPTORS", np.full(nant, 2, np.int32))
        t.putcol("RECEPTOR_ANGLE", np.full((nant, 2), angle))
    return ms


def test_chain_terms_give_the_polcal_specs(tmp_path):
    ms = _with_feed(make_ms(tmp_path / "x.ms"))
    config = core_config.validate(POLCAL, ["calibrate"])
    info = core_pipeline.inspect_ms(ms)
    terms = core_pipeline.chain_terms(config, info, tmp_path / "c.yaml")
    pol = {t["name"]: t for t in terms[2:]}
    assert [t["type"] for t in terms] == ["K", "G", "Gpol", "KCROSS", "Xf", "Df"]
    assert pol["Gpol"]["fields"] == [1] and pol["Df"]["fields"] == [0]
    # CARACal's interpolation for pre-applied tables without an interp.
    assert pol["Kc"]["interp"] == ["linear", "linear", "linear"]
    assert pol["Xf"]["interp"] == ["linear", "linear", "linear", "nearest"]
    assert pol["Df"]["interp"] == ["linear", "linear", "nearest", "nearest"]
    assert pol["Df"]["clip"] == 0.6 and pol["Df"]["model"] == "unit"
    assert pol["Kc"]["estimator"] == "casa" and pol["Kc"]["combine"] == ""
    assert pol["Xf"]["model_column"] == "MODEL_DATA"
    assert all(t["parang"] and t["frame"] == "casa" for t in pol.values())
    assert core_pipeline.polcal_models(config, info) == [(1, "3C286")]


def test_applycal_parang_equals_cal_pol_apply_whatever_the_chunking(tmp_path):
    pytest.importorskip("astropy")
    src = _with_feed(make_ms(tmp_path / "src" / "x.ms"))
    copies = []
    for rows in (7, None):
        ms = Path(shutil.copytree(src, tmp_path / f"c{rows}" / "x.ms"))
        applycal.applycal(ms, [], parang=True, field=[0, 1], chunk_rows=rows)
        copies.append(ms)
    with core_ms.open_table(copies[0]) as t:
        a = t.getcol("CORRECTED_DATA")
    with core_ms.open_table(copies[1]) as t:
        b = t.getcol("CORRECTED_DATA")
        c = {k: t.getcol(k) for k in ("DATA", "FLAG", "TIME", "ANTENNA1", "ANTENNA2",
                                       "FIELD_ID")}  # fmt: skip
    assert np.array_equal(a.view(np.uint32), b.view(np.uint32))
    with core_ms.open_table(src / "SPECTRAL_WINDOW") as t:
        freq = t.getcol("CHAN_FREQ")[0]
    for f in (0, 1):
        rows = np.flatnonzero(c["FIELD_ID"] == f)
        ang = cal_pol.row_angles(src, c["TIME"][rows], c["ANTENNA1"][rows],
                                 c["ANTENNA2"][rows], f)  # fmt: skip
        want, _ = cal_pol.apply(c["DATA"][rows], c["FLAG"][rows], c["TIME"][rows],
                                c["ANTENNA1"][rows], c["ANTENNA2"][rows], freq, [],
                                angles=ang)  # fmt: skip
        assert np.array_equal(want.view(np.uint32), b[rows].view(np.uint32))
    # A receptor angle given in memory equals FEED holding it.
    ms = Path(shutil.copytree(src, tmp_path / "r" / "x.ms"))
    with core_ms_write.open_table(ms / "FEED", readonly=False) as t:
        t.putcol("RECEPTOR_ANGLE", np.zeros((len(t.getcol("ANTENNA_ID")), 2)))
    applycal.applycal(ms, [], parang=True, field=[0, 1], receptor_angle=-np.pi / 2)
    with core_ms.open_table(ms) as t:
        r = t.getcol("CORRECTED_DATA")
    assert np.array_equal(r.view(np.uint32), b.view(np.uint32))


def test_kcross_refinement_removes_the_parabola_bias():
    freq = 856e6 + 3.34375e6 * np.arange(256)
    worst_fft, worst_refined = 0.0, 0.0
    for tau in np.linspace(-12, 12, 49):
        s = np.exp(2j * np.pi * tau * 1e-9 * (freq - freq.mean()))
        t0 = _fft_delay(s, freq[1] - freq[0])
        t1 = cal_pol.kcross_refine(s, freq, t0)
        worst_fft = max(worst_fft, abs(t0 - tau))
        worst_refined = max(worst_refined, abs(t1 - tau))
    assert worst_fft > 1e-5
    assert worst_refined < 1e-9


def _fft_delay(s, df):
    """CASA's FFT and parabola (`crosshand.rs` `fft_peak_delay`), in numpy."""
    n = 8 * len(s)
    amp = np.abs(np.fft.fftshift(np.fft.fft(s, n)))
    k = int(np.argmax(amp))
    a0, a1, a2 = amp[k - 1], amp[k], amp[k + 1]
    f = k + 0.5 - (a2 - a1) / (a0 - 2 * a1 + a2)
    return (f - n / 2) / n / df * 1e9


def test_applycal_parang_flags_spread_by_default(tmp_path):
    """Task df-flag-rule (research/p-flag-spread.md): with parang, a cell
    with one correlation flagged is flagged in all four (CASA's general-Jones
    P); `parang_flags='none'` keeps the input flags."""
    pytest.importorskip("astropy")
    src = _with_feed(make_ms(tmp_path / "src" / "x.ms"))
    with core_ms_write.open_table(src, readonly=False) as t:
        flag = np.zeros(t.getcol("FLAG").shape, bool)
        flag[3, 2, 0] = True  # XX only
        flag[5, 1, 2] = True  # YX only
        t.putcol("FLAG", flag)
    got = {}
    for mode in ("spread", "none"):
        ms = Path(shutil.copytree(src, tmp_path / mode / "x.ms"))
        s = applycal.applycal(ms, [], parang=True, field=[0, 1], parang_flags=mode)
        assert s["parang_flags"] == mode
        with core_ms.open_table(ms) as t:
            got[mode] = (t.getcol("FLAG"), t.getcol("CORRECTED_DATA"))
    assert np.array_equal(got["none"][0], flag)
    want = np.broadcast_to(flag.any(-1, keepdims=True), flag.shape)
    assert np.array_equal(got["spread"][0], want)
    assert np.array_equal(
        got["spread"][1].view(np.uint32), got["none"][1].view(np.uint32)
    )
    with pytest.raises(applycal.ApplyError):
        applycal.applycal(src, [], parang=True, parang_flags="casa")
