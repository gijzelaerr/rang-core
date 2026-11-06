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
    with pytest.raises(NotImplementedError, match="C7a"):
        calmodels.spec_from_config(
            {
                "standard": "manual",
                "fluxdensity": 14.7,
                "reffreq": "1.47GHz",
                "polindex": [0.098],
            }
        )
    with pytest.raises(NotImplementedError, match="C7a"):
        calmodels.spec_from_config(
            {"standard": "manual", "fluxdensity": [1, 0.1, 0, 0], "reffreq": 1e9}
        )
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
