"""C4b (research/c4b-apply-ms.md): `rang.applycal` on a synthetic MS written
by the core writer: field maps, weights for `calwt` both ways, chunking, the
channel median of WEIGHT, and the binned complex apply against a NumPy
reference. The comparison with CASA `applycal` is
`examples/check_apply_ms.py` (it needs the CASA container)."""

import importlib.util
import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import applycal, cal_apply, core_ms, core_ms_write
from rang.formats import caltable

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)
NANT, NCHAN, NROW = 4, 8, 120  # 6 baselines x 20 integrations


def make_ms(path):
    ms = w1.make_ms(path, NROW, NCHAN, flag="tiled", nant=NANT)
    rng = np.random.default_rng(20261109)
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(NANT)
        t.putcol("NAME", [f"m{a:03d}" for a in range(NANT)])
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(2)
        t.putcol("NAME", ["CAL", "TGT"])
        t.putcol("PHASE_DIR", np.array([[[0.0, -1.0]], [[0.1, -1.0]]]))
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FIELD_ID", ((np.arange(NROW) // 6) % 2).astype(np.int32))
        t.putcol("SIGMA", rng.uniform(0.5, 2.0, (NROW, 4)).astype(np.float32))
    return ms


def column(ms, name):
    with core_ms.open_table(ms) as t:
        return t.getcol(name)


def g_table(ms, field_id=0, flag=None, values=None, kind="G"):
    with core_ms.open_table(ms) as t:
        times = np.unique(t.getcol("TIME"))
    sub = caltable.subtables_from_ms(ms, single_channel=True)
    rng = np.random.default_rng(field_id + 1)
    npar = 1 if kind == "T" else 2
    if values is None:
        values = (1 + 0.3 * rng.random((1, NANT, 1, npar))) * np.exp(
            1j * rng.uniform(-1, 1, (1, NANT, 1, npar))
        )
    if kind == "K":
        values = rng.uniform(-2, 2, (1, NANT, 1, 2))
    return caltable.from_gains(
        kind,
        [float(times.mean())],
        list(range(NANT)),
        values,
        flag,
        subtables=sub,
        field_id=field_id,
    )


def two_field(ms):
    a, b = g_table(ms, 0), g_table(ms, 1)
    with core_ms.open_table(ms) as t:
        tm = np.unique(t.getcol("TIME"))
    b.main["TIME"] = [float(tm[-1])] * len(b.main["TIME"])
    main = {k: list(a.main[k]) + list(b.main[k]) for k in a.main}
    return caltable.CalTable(a.vis_cal, main, a.subtables, a.keywords, a.info)


def test_field_maps_follow_casa(tmp_path):
    ms = make_ms(tmp_path / "x.ms")
    info = applycal.ms_info(ms)
    t = two_field(ms)
    assert applycal.field_map(t, "", info) == {
        0: cal_apply.POOLED,
        1: cal_apply.POOLED,
    }
    assert applycal.field_map(t, "TGT", info) == {0: 1, 1: 1}
    assert applycal.field_map(t, "0", info) == {0: 0, 1: 0}
    assert applycal.field_map(t, "nearest", info) == {0: 0, 1: 1}
    one = g_table(ms, 1)
    assert applycal.field_map(one, "nearest", info) == {0: 1, 1: 1}
    with pytest.raises(applycal.ApplyError, match="no solutions"):
        applycal.field_map(one, "CAL", info)
    # Two table fields mirrored about the MS field: CASA refuses the tie.
    t.subtables = dict(t.subtables)
    t.subtables["FIELD"] = dict(t.subtables["FIELD"])
    t.subtables["FIELD"]["PHASE_DIR"] = [
        np.array([[-0.1, -1.0]]),
        np.array([[0.1, -1.0]]),
    ]
    tie = dict(info, phase_dir=np.array([[0.0, -1.0], [0.0, -1.0]]))
    with pytest.raises(applycal.ApplyError, match="equally near"):
        applycal.field_map(t, "nearest", tie)


def test_calwt_false_and_k_leave_weights_and_g_scales_them(tmp_path):
    ms = make_ms(tmp_path / "x.ms")
    before = {n: column(ms, n) for n in ("WEIGHT", "SIGMA", "DATA")}
    applycal.applycal(ms, [g_table(ms)], calwt=[False])
    assert column(ms, "WEIGHT").tobytes() == before["WEIGHT"].tobytes()
    applycal.applycal(ms, [g_table(ms, kind="K")], calwt=[True])
    assert column(ms, "WEIGHT").tobytes() == before["WEIGHT"].tobytes()
    flag = np.zeros((1, NANT, 1, 2), bool)
    flag[0, 2, 0, 0] = True  # antenna 2's X: weight scale 1 on that side
    t = g_table(ms, flag=flag)
    summary = applycal.applycal(ms, [t], calwt=[True])
    assert summary["weights_written"]
    g = np.abs(t.params[:, 0, :]) ** 2  # (antenna, receptor), slot rows
    g[2, 0] = 1.0
    a1, a2 = column(ms, "ANTENNA1"), column(ms, "ANTENNA2")
    scale = np.stack(
        [
            g[a1, 0] * g[a2, 0],
            g[a1, 0] * g[a2, 1],
            g[a1, 1] * g[a2, 0],
            g[a1, 1] * g[a2, 1],
        ],
        axis=-1,
    )
    want = scale / before["SIGMA"].astype(np.float64) ** 2
    got = column(ms, "WEIGHT")
    assert np.allclose(got, want, rtol=1e-6, atol=0)
    assert column(ms, "SIGMA").tobytes() == before["SIGMA"].tobytes()


def test_chunks_give_the_same_bytes(tmp_path):
    one = make_ms(tmp_path / "one.ms")
    many = tmp_path / "many.ms"
    shutil.copytree(one, many)
    t = two_field(one)
    kwargs = {"gainfield": ["nearest"], "calwt": [True], "field": ["TGT"]}
    applycal.applycal(one, [t], **kwargs)
    applycal.applycal(many, [t], chunk_rows=7, **kwargs)
    for name in ("CORRECTED_DATA", "FLAG", "FLAG_ROW", "WEIGHT"):
        assert column(one, name).tobytes() == column(many, name).tobytes()
    # Rows of the field not selected keep CORRECTED_DATA = DATA.
    cal = column(one, "FIELD_ID") == 0
    assert (
        column(one, "CORRECTED_DATA")[cal].tobytes()
        == column(one, "DATA")[cal].tobytes()
    )


def test_a_buffer_a_table_does_not_cover_is_left_alone(tmp_path):
    """`VBOKforCalApply`: when any table has no solutions for a field's
    window, CASA neither corrects nor resets weights there; `calflagstrict`
    flags it (an unexercised path against CASA, research/c4b-apply-ms.md)."""
    ms = make_ms(tmp_path / "x.ms")
    applycal.applycal(ms, [g_table(ms)], calwt=[True])
    before = {n: column(ms, n) for n in ("CORRECTED_DATA", "FLAG", "WEIGHT")}
    other = g_table(ms, field_id=1)
    other.main["SPECTRAL_WINDOW_ID"] = [1] * len(other.main["SPECTRAL_WINDOW_ID"])
    summary = applycal.applycal(ms, [g_table(ms), other], calwt=[True])
    assert summary["uncovered"]
    for name, values in before.items():
        assert column(ms, name).tobytes() == values.tobytes()
    applycal.applycal(ms, [g_table(ms), other], applymode="calflagstrict")
    assert column(ms, "FLAG").all()
    assert column(ms, "CORRECTED_DATA").tobytes() == before["CORRECTED_DATA"].tobytes()


def test_weight_is_the_lower_middle_channel_value():
    ws = np.array([[[4.0], [1.0], [3.0], [2.0]]], np.float32)  # (row, chan, corr)
    assert applycal._median_over_channels(ws)[0, 0] == 2.0
    assert applycal._median_over_channels(ws[:, :3])[0, 0] == 3.0


def test_apply_jones_matches_a_float64_reference():
    rng = np.random.default_rng(20261109)
    nrow, nchan, nant, nt, nf = 30, 6, 4, 3, 2
    data = (
        rng.standard_normal((nrow, nchan, 4))
        + 1j * rng.standard_normal((nrow, nchan, 4))
    ).astype(np.complex64)
    flag = rng.random((nrow, nchan, 4)) < 0.05
    a1 = rng.integers(0, nant - 1, nrow)
    a2 = a1 + 1
    gains = np.eye(2) + 0.2 * (
        rng.standard_normal((nt, nf, nant, 2, 2))
        + 1j * rng.standard_normal((nt, nf, nant, 2, 2))
    )
    valid = rng.random((nt, nf, nant)) > 0.2
    tb = rng.integers(0, nt, nrow)
    fb = np.arange(nchan) % nf
    got, gflag = cal_apply.apply_jones(data, flag, a1, a2, gains, valid, tb, fb)
    want = np.empty_like(data)
    wflag = np.empty(data.shape, bool)
    for r in range(nrow):
        for c in range(nchan):
            gp, gq = gains[tb[r], fb[c], a1[r]], gains[tb[r], fb[c], a2[r]]
            okp, okq = valid[tb[r], fb[c], a1[r]], valid[tb[r], fb[c], a2[r]]
            ip = np.linalg.inv(gp) if okp else np.eye(2)
            iq = np.linalg.inv(gq) if okq else np.eye(2)
            v = data[r, c].astype(complex).reshape(2, 2)
            want[r, c] = (ip @ v @ iq.conj().T).reshape(4)
            wflag[r, c] = flag[r, c].any() or not (okp and okq)
    assert cal_apply.class_c(got, want, np.ones(data.shape, bool))["pass"]
    assert np.array_equal(gflag, wflag)
    back, bflag = cal_apply.apply_jones(
        got, flag, a1, a2, gains, valid, tb, fb, direction="corrupt"
    )
    ok = ~wflag
    assert np.allclose(back[ok], data[ok], rtol=1e-5, atol=1e-5)
    assert np.array_equal(bflag, wflag)
