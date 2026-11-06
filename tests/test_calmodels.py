"""C3a calibrator models (research/c3a-models.md): point standards, manual
models, Stokes rows and component lists written to MODEL_DATA through the W1
write-back, on MSs written by the core writer inside each test."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from rang import calmodels, core, core_ms, core_ms_write, fluxstd
from rang import core_writeback as wb
from rang.formats import sky

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)
FIELDS = (
    ("J1939-6342", 5.146179, -1.111986),
    ("3C286", 3.539258, 0.532485),
    ("TGT", 5.2, -0.6),
)


def make_ms(path, nrow=60, nchan=16, ncorr=4, corr=None):
    ms = w1.make_ms(path, nrow, nchan, ncorr=ncorr)
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(len(FIELDS))
        t.putcol("NAME", [f[0] for f in FIELDS])
        for k, (_, ra, dec) in enumerate(FIELDS):
            for col in ("PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"):
                t.putcell(col, k, np.array([[ra, dec]]))
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FIELD_ID", (np.arange(nrow) % len(FIELDS)).astype(np.int32))
    if corr is not None:
        with core_ms_write.open_table(ms / "POLARIZATION", readonly=False) as t:
            t.putcell("CORR_TYPE", 0, np.array(corr, np.int32))
    return ms


def read(ms, name):
    with core_ms.open_table(ms) as t:
        return t.getcol(name)


@pytest.fixture
def ms(tmp_path):
    return make_ms(tmp_path / "m.ms")


def test_standard_is_fluxstd_in_float32_and_other_fields_untouched(ms):
    receipt = calmodels.set_model(
        ms, "J1939-6342", {"standard": "SR2016"}, chunk_rows=16
    )
    assert receipt["column_added"] and receipt["fields"]["J1939-6342"]["rows"] == 20
    model, fid = read(ms, "MODEL_DATA"), read(ms, "FIELD_ID")
    freq = read(ms / "SPECTRAL_WINDOW", "CHAN_FREQ")[0]
    i = fluxstd.flux("J1939-6342", freq, "Stevens-Reynolds 2016")[:, 0]
    sel = model[fid == 0]
    assert np.array_equal(
        sel[..., 0].real, np.broadcast_to(i.astype(np.float32), sel.shape[:2])
    )
    assert np.array_equal(sel[..., 0], sel[..., 3])
    assert np.all(sel[..., [1, 2]] == 0) and np.all(sel.imag == 0)
    rest = model[fid != 0]
    assert np.all(rest[..., [0, 3]] == 1) and np.all(rest[..., [1, 2]] == 0)
    assert wb.read_journal(ms)["state"] == "closed"


def test_manual_matches_fluxstd_and_casa_quantity(ms):
    spec = {
        "standard": "manual",
        "fluxdensity": [14.907688923, 0, 0, 0],
        "reffreq": "1.400000GHz",
        "spix": [-0.19473727, -1.3843252, 0.60533435, 1.43e-06],
    }
    calmodels.set_model(ms, [0, "3C286"], spec)
    freq = read(ms / "SPECTRAL_WINDOW", "CHAN_FREQ")[0]
    i = fluxstd.manual(freq, 14.907688923, 1.4e9, spec["spix"]).astype(np.float32)
    model, fid = read(ms, "MODEL_DATA"), read(ms, "FIELD_ID")
    for f in (0, 1):
        assert np.all(model[fid == f][..., 3].real == i)
    assert np.all(model[fid == 2][..., 0] == 1)


def test_existing_column_values_kept_outside_the_selection(ms):
    with wb.WriteBack(ms) as w:
        w.ensure_column("MODEL_DATA")
        for start, n in w.chunks():
            w.write("MODEL_DATA", start, np.full((n, 16, 4), 2 - 3j, np.complex64))
    calmodels.set_model(ms, "TGT", calmodels.Manual(1.0, 1e9, ()))
    model, fid = read(ms, "MODEL_DATA"), read(ms, "FIELD_ID")
    assert np.all(model[fid != 2] == 2 - 3j)
    assert np.all(model[fid == 2][..., [0, 3]] == 1) and np.all(
        model[fid == 2][..., [1, 2]] == 0
    )


def test_point_stokes_linear_and_circular(tmp_path):
    def stokes(nu):
        s = np.zeros(nu.shape + (4,))
        s[:, 0], s[:, 1], s[:, 2], s[:, 3] = 10.0, 0.5, -0.25, 0.125
        return s

    spec = calmodels.PointStokes(stokes)
    lin = make_ms(tmp_path / "lin.ms")
    calmodels.set_model(lin, 1, spec)
    m = read(lin, "MODEL_DATA")[read(lin, "FIELD_ID") == 1]
    assert np.all(m[..., 0] == 10.5) and np.all(m[..., 3] == 9.5)
    assert np.all(m[..., 1] == -0.25 + 0.125j) and np.all(m[..., 2] == -0.25 - 0.125j)
    circ = make_ms(tmp_path / "circ.ms", corr=[5, 6, 7, 8])
    calmodels.set_model(circ, 1, spec)
    m = read(circ, "MODEL_DATA")[read(circ, "FIELD_ID") == 1]
    assert np.all(m[..., 0] == 10.125) and np.all(m[..., 3] == 9.875)
    assert np.all(m[..., 1] == 0.5 - 0.25j) and np.all(m[..., 2] == 0.5 + 0.25j)


def test_skymodel_equals_direct_prediction(ms, tmp_path):
    sources = [
        sky.Source(name="A", ra=5.1462, dec=-1.11199, i=12.0, freq0=1.3e9, spi=(-0.1, -0.6)),
        sky.Source(name="B", ra=5.1440, dec=-1.11150, i=0.02, freq0=1.3e9, spi=(-1.0,),
                   emaj=3e-5, emin=1e-5, pa=0.4),
    ]  # fmt: skip
    path = tmp_path / "m.txt"
    path.write_text(sky.dumps_wsclean(sources))
    calmodels.set_model(ms, "J1939-6342", {"skymodel": str(path)}, chunk_rows=7)
    model, fid, uvw = read(ms, "MODEL_DATA"), read(ms, "FIELD_ID"), read(ms, "UVW")
    freq = read(ms / "SPECTRAL_WINDOW", "CHAN_FREQ")[0]
    comp = sky.components(sky.load_any(path), (FIELDS[0][1], FIELDS[0][2]))
    vis = core.predict_components(uvw[fid == 0], freq, **comp).astype(np.complex64)
    sel = model[fid == 0]
    assert np.array_equal(sel[..., 0], vis) and np.array_equal(sel[..., 3], vis)
    assert np.all(sel[..., [1, 2]] == 0)
    assert np.abs(vis).max() > 1.0


def test_refusals(ms, tmp_path):
    # C7a: polindex without polangle is refused (CASA would drop it silently).
    with pytest.raises(ValueError, match="together"):
        calmodels.spec_from_config(
            {
                "standard": "manual",
                "fluxdensity": 14.7,
                "reffreq": "1.47GHz",
                "polindex": [0.098],
            }
        )
    with pytest.raises(ValueError, match="not both"):
        calmodels.Manual([1, 0.1, 0, 0], 1e9, q=0.2)
    with pytest.raises(NotImplementedError):
        calmodels.spec_from_config({"standard": "SR2016", "scalebychan": False})
    with pytest.raises(ValueError, match="unknown model keys"):
        calmodels.spec_from_config({"standard": "SR2016", "colour": "red"})
    with pytest.raises(ValueError, match="no field named"):
        calmodels.set_model(ms, "NOPE", {"standard": "SR2016"})
    with pytest.raises(ValueError, match="not in"):
        calmodels.set_model(ms, "TGT", {"standard": "SR2016"})
    pol = tmp_path / "p.lsm.html"
    pol.write_text(
        sky.dumps_html([sky.Source(name="P", ra=5.1, dec=-1.1, i=1.0, q=0.1)])
    )
    with pytest.raises(NotImplementedError, match="Stokes I only"):
        calmodels.set_model(ms, 0, {"skymodel": str(pol)})
    assert calmodels.parse_frequency("1.47GHz") == 1.47e9
    assert calmodels.parse_frequency("856 MHz") == 856e6
    with pytest.raises(ValueError):
        calmodels.parse_frequency("1.4 parsecs")


def test_session_passed_by_the_caller(ms):
    with wb.WriteBack(ms, stage="calibrate") as w:
        calmodels.set_model(ms, 0, {"standard": "SR2016"}, session=w)
        calmodels.set_model(ms, 1, {"standard": "PB2010", "source": "3C286"}, session=w)
    journal = wb.read_journal(ms)
    assert journal["stage"] == "calibrate" and journal["state"] == "closed"
    model, fid = read(ms, "MODEL_DATA"), read(ms, "FIELD_ID")
    freq = read(ms / "SPECTRAL_WINDOW", "CHAN_FREQ")[0]
    i = fluxstd.flux("3C286", freq, "Perley-Butler 2010")[:, 0].astype(np.float32)
    assert np.all(model[fid == 1][..., 0].real == i)


# -- C7a: polarised manual models (research/c7a-polmodels.md) --------------------------

C = 299792458.0
NU = np.linspace(856e6, 1712e6, 37)


def reference_stokes(nu, s0, f0, spix, pi, pa, rm, q=0.0, u=0.0, v=0.0):
    """Section 2 of the note, written independently in vectorised float64."""
    i = fluxstd.manual(nu, s0, f0, spix)
    pi, pa = list(pi), list(pa)
    if q or u:
        if not pi or not pa:
            pi, pa = [0.0], [0.0]
        pi[0], pa[0] = np.hypot(q, u) / s0, 0.5 * np.arctan2(u, q)
    x = (nu - f0) / f0
    p = np.polynomial.polynomial.polyval(x, pi) if pi else 0 * x
    chi = np.polynomial.polynomial.polyval(x, pa) if pa else 0 * x
    chi = chi + rm * ((C / nu) ** 2 - (C / f0) ** 2)
    out = np.zeros(nu.shape + (4,))
    out[:, 0], out[:, 1], out[:, 2] = (
        i,
        p * i * np.cos(2 * chi),
        p * i * np.sin(2 * chi),
    )
    out[:, 3] = i * v / s0
    return out


@pytest.mark.parametrize(
    "kw",
    [
        {"polindex": [0.098], "polangle": [0.575959], "spix": [-0.4507, -0.1798, 0.0357]},
        {"polindex": [0.098, 0.02, -0.01], "polangle": [0.575959, 0.05], "rotmeas": 50.0,
             "spix": [-0.4507, -0.1798]},
        {"q": 0.6, "u": 1.2, "v": 0.05, "polindex": [0.098, 0.03], "polangle": [0.5, -0.04],
             "rotmeas": 10.0, "spix": [-0.45, -0.18]},
        {"q": 0.4, "u": 1.3, "rotmeas": -30.0, "spix": [-0.45, -0.18]},
        {"polindex": [0.099], "polangle": [0.5096], "rotmeas": -0.3, "spix": [-0.63]},
        {"v": 0.04, "spix": [-0.6]},
        {"q": 0.1, "u": -0.05, "rotmeas": 15.0, "spix": [-0.6]},
    ],
)  # fmt: skip
def test_polarised_manual_matches_an_independent_evaluation(kw):
    kw = dict(kw)
    spix = kw.pop("spix")
    q, u, v = kw.pop("q", 0.0), kw.pop("u", 0.0), kw.pop("v", 0.0)
    m = calmodels.Manual([14.7172, q, u, v], "1.47GHz", spix, **kw)
    ref = reference_stokes(
        NU, 14.7172, 1.47e9, spix, kw.get("polindex", ()), kw.get("polangle", ()),
        kw.get("rotmeas", 0.0), q, u, v,
    )  # fmt: skip
    got = m.stokes(NU)
    assert m.polarised
    assert m.casa_path == (
        "tabular"
        if len(spix) > 1
        or max(len(kw.get("polindex", ())), len(kw.get("polangle", ()))) > 1
        else "spectral-index-channel0"
    )
    assert np.allclose(got, ref, rtol=1e-12, atol=1e-12 * 14.7172)
    if m.casa_path == "tabular":
        assert np.array_equal(got[:, 0], ref[:, 0])


def test_unpolarised_manual_is_c3a_unchanged():
    m = calmodels.Manual(4.0, 1.4e9, [-0.6])
    assert not m.polarised and m.casa_path == "spectral-index"
    got = m.stokes(NU)
    assert np.array_equal(got[:, 0], fluxstd.manual(NU, 4.0, 1.4e9, [-0.6]))
    assert np.all(got[:, 1:] == 0)


def test_caracal_xcal_models_and_published_angles():
    for name, alias, p, chi_deg in (
        ("3C286", "J1331+3030", 0.098, 33.0),
        ("3C138", "J0521+1638", 0.078, -9.6),
    ):
        m = calmodels.caracal_xcal(alias)
        assert m == calmodels.caracal_xcal(name) and m.casa_path == "tabular"
        s = m.stokes(NU)
        assert np.allclose(np.hypot(s[:, 1], s[:, 2]) / s[:, 0], p, rtol=1e-12)
        chi = np.degrees(0.5 * np.arctan2(s[:, 2], s[:, 1]))
        assert np.all(np.abs(chi - chi_deg) < 0.01)
    with pytest.raises(ValueError, match="no CARACal"):
        calmodels.caracal_xcal("3C48")


def test_polarised_manual_writes_four_correlations(ms):
    spec = {
        "standard": "manual",
        "fluxdensity": [14.7172, 0, 0, 0.1],
        "reffreq": "1.47GHz",
        "spix": [-0.4507, -0.1798, 0.0357],
        "polindex": [0.098],
        "polangle": [0.575959],
        "rotmeas": 20.0,
    }
    receipt = calmodels.set_model(ms, "3C286", spec, chunk_rows=11)
    model, fid = read(ms, "MODEL_DATA"), read(ms, "FIELD_ID")
    freq = read(ms / "SPECTRAL_WINDOW", "CHAN_FREQ")[0]
    stokes = calmodels.spec_from_config(spec).stokes(freq)
    want = calmodels.correlations(stokes, (9, 10, 11, 12)).astype(np.complex64)
    sel = model[fid == 1]
    assert np.array_equal(sel, np.broadcast_to(want, sel.shape))
    assert np.all(sel[..., 1].imag == np.float32(stokes[:, 3]))
    assert np.array_equal(sel[..., 2], np.conj(sel[..., 1]))
    entry = receipt["fields"]["3C286"]["spectral_windows"]["0"]
    assert (
        len(entry["stokes_iquv_jy"]) == 3 and receipt["spec"]["casa_path"] == "tabular"
    )
    assert np.all(model[fid == 2][..., [0, 3]] == 1)
