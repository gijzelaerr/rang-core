"""TS-P1 (research/ts-p1.md): residual snapshot light curves. A small version
of the TS-P1 simulation is written inside the test (8 antennas, 8 channels,
45 integrations); the frozen sets are not."""

import csv
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest
from rang import core, core_cli, core_ms_write, simtruth
from rang import lightcurve as lc

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"examples/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

sim = _load("ts_p1_sim")
measure = _load("ts_p1_measure")
SIZE = 1024


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    out = tmp_path_factory.mktemp("tsp1")
    ms = sim.main(
        ["tsp1-dev", str(out), "--ntime", "45", "--nant", "8", "--nchan", "8"]
    )
    truth = json.loads((out / "tsp1-dev.truth.json").read_text(encoding="utf-8"))
    return ms, out / "tsp1-dev.truth.json", truth


def positions(truth):
    return [(s["name"], s["ra_deg"], s["dec_deg"]) for s in truth["sources"]]


def test_positions_parse_and_project_back():
    assert lc.parse_position("X=300.5,-36.25") == ("X", 300.5, -36.25)
    name, ra, dec = lc.parse_position("20:00:00,-36:00:00", 3)
    assert name == "p3" and math.isclose(ra, 300.0) and math.isclose(dec, -36.0)
    with pytest.raises(lc.LightcurveError):
        lc.parse_position("300,95")
    ra0, dec0 = math.radians(300.0), math.radians(-36.0)
    for el, em in ((0.0, 0.0), (0.004, -0.007), (-0.0087, 0.0091)):
        ra, dec = simtruth.radec(el, em, ra0, dec0)
        back = lc.lm_from_radec(ra, dec, ra0, dec0)
        assert np.allclose(back, (el, em), atol=1e-15)


def test_kernel_recovers_a_predicted_source():
    rng = np.random.default_rng(1)
    uvw = rng.uniform(-4000, 4000, (500, 3))
    freq = np.linspace(0.9e9, 1.6e9, 5)
    el, em = 0.003, -0.005
    comp = {
        "kind": "point",
        "l": el,
        "m": em,
        "flux": 1.7,
        "alpha": 0.0,
        "fwhm_arcsec": 0.0,
        "ref_freq_hz": 1.284e9,
    }
    vis = simtruth._predict(uvw, freq, simtruth._component_arrays([comp]))
    weight = rng.uniform(0.5, 2.0, vis.shape).astype(np.float32)
    flux, wsum, samples = lc.dft(
        uvw, freq, vis.astype(np.complex64), weight, [[el, em]]
    )
    assert abs(flux[0] - 1.7) < 1e-6
    assert samples == vis.size and math.isclose(
        wsum, float(weight.sum(dtype=np.float64))
    )
    # The independent NumPy sum of the measurement script agrees.
    phi = measure.phases(uvw, freq, [(el, em)])
    ref = measure.numpy_dft(vis.astype(np.complex64), weight, phi)
    assert abs(ref[0] - flux[0]) < 1e-9


def test_light_curves_match_the_oracles_on_the_small_simulation(small):
    ms, _, truth = small
    res = lc.light_curves(ms, positions(truth), field=3, size=SIZE)
    assert res["intervals"] == 45 and res["field"]["name"] == "SIM-TARGET"
    assert res["time_mjd_s"] == truth["time_mjd_s"]  # T3c: TIME exactly
    flux = np.array(res["flux_jy"])
    dft, expected = measure.oracle(ms, truth)
    sig = truth["sigma_snap_jy"]
    assert np.max(np.abs(flux - dft)) / sig < 1e-6  # T2a
    snap = np.array(res["flux_snapshot_jy"], float)
    assert np.max(np.abs(snap - flux)) / sig < 1e-3  # T2b, every pixel centred
    assert all(p["pixel_offset_arcsec"] < 1e-6 for p in res["positions"])
    # A's 8 s pulse at integration 40 (20 sigma_snap) stands out.
    a = flux[:, 0] / np.array(res["sigma_meas_jy"])
    assert int(np.argmax(a)) == 40 and a[40] > 7
    assert np.isfinite(expected).all()


def test_noiseless_twin_gives_the_expected_dirty_values(tmp_path):
    ms = sim.main(
        ["tsp1-dev", str(tmp_path), "--ntime", "42", "--nant", "6", "--nchan", "4",
         "--noiseless"]
    )  # fmt: skip
    truth = json.loads((tmp_path / "tsp1-dev.truth.json").read_text(encoding="utf-8"))
    res = lc.light_curves(ms, positions(truth), field="SIM-TARGET", images=False)
    _, expected = measure.oracle(ms, truth)
    scale = np.max(np.abs(expected))
    # complex64 rounding of DATA and MODEL_DATA (about 1 Jy of static sky)
    assert np.max(np.abs(np.array(res["flux_jy"]) - expected)) < 1e-4 * scale
    assert res["flux_snapshot_jy"][0] == [None] * 6
    # Without the model the static sky's sidelobes dominate.
    raw = lc.light_curves(
        ms, positions(truth), field=3, model_column=None, images=False
    )
    assert np.max(np.abs(raw["flux_jy"])) > 5 * scale


def test_interval_steps_group_integrations(small):
    ms, _, truth = small
    res = lc.light_curves(ms, positions(truth)[:1], field=3, interval_steps=4,
                          images=False)  # fmt: skip
    assert res["intervals"] == 12 and res["timesteps"][-1] == 1
    assert math.isclose(res["time_mjd_s"][0], float(np.mean(truth["time_mjd_s"][:4])))


def test_refusals(small, tmp_path):
    ms, _, truth = small
    with pytest.raises(lc.LightcurveError, match="CORRECTED_DATA|not in the MS"):
        lc.light_curves(ms, positions(truth), field=3, column="CORRECTED_DATA")
    with pytest.raises(lc.LightcurveError, match="MODEL_X"):
        lc.light_curves(ms, positions(truth), field=3, model_column="MODEL_X")
    with pytest.raises(lc.LightcurveError, match="not in the MS"):
        lc.light_curves(ms, positions(truth), field="NOPE")
    with pytest.raises(lc.LightcurveError, match="no cross-correlation rows"):
        lc.light_curves(ms, positions(truth), field=0)


def test_command_line_writes_outputs_and_receipt(small, tmp_path):
    ms, _, truth = small
    out = tmp_path / "lc"
    argv = ["lightcurve", str(ms), "--field", "3", "--out", str(out), "--fits",
            "--size", "512", "--interval-steps", "15"]  # fmt: skip
    for s in truth["sources"][:2]:
        argv += ["--position", f"{s['name']}={s['ra_deg']!r},{s['dec_deg']!r}"]
    result = core_cli.dispatch(argv)
    assert result["intervals"] == 3
    with open(out / "lightcurve.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 6 and rows[0]["position"] == "A"
    assert len(list((out / "snapshots").glob("*.fits"))) == 3
    receipt = json.loads(
        (tmp_path / "lc.lightcurve.rang-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["exit"] == 0 and receipt["stage"] == "lightcurve"
    with pytest.raises(SystemExit) as exc:  # the output exists
        core_cli.dispatch(argv)
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:  # no such model column
        core_cli.dispatch(
            ["--no-receipt", "lightcurve", str(ms), "--out", str(tmp_path / "x"),
             "--field", "3", "--model-column", "MODEL_X", "--position", "1,2"]
        )  # fmt: skip
    assert exc.value.code == 2


def test_samples_beyond_the_grid_are_counted():
    limit = 1.0 / (2.0 * 4.0 * lc.ARCSEC)  # wavelengths
    freq = np.array([299_792_458.0])  # 1 m wavelength
    uvw = np.array([[0.5 * limit, 0, 0], [limit, 0, 0], [0, -1.5 * limit, 0]])
    weight = np.array([[1.0], [1.0], [0.0]], np.float32)
    assert lc.outside_grid(uvw, freq, weight, 4.0) == 1
    assert lc.outside_grid(uvw, freq, np.ones((3, 1), np.float32), 4.0) == 2
    assert lc.outside_grid(uvw, freq, weight, 1.0) == 0


def test_extension_has_the_kernel():
    assert hasattr(core.extension(), "lightcurve_dft")


def test_protocol2_small_simulation_matches_the_numpy_oracle(tmp_path):
    ms = sim.main(
        ["tsp1-held2", str(tmp_path), "--ntime", "40", "--nant", "8", "--nchan", "16"]
    )  # fmt: skip
    truth = json.loads((tmp_path / "tsp1-held2.truth.json").read_text(encoding="utf-8"))
    res = lc.light_curves(ms, positions(truth), field=3, size=SIZE, scale_arcsec=4.0)
    assert res["settings"]["column"] == "CORRECTED_DATA"
    assert res["settings"]["weight_column"] == "WEIGHT_SPECTRUM"
    dft, _ = measure.oracle(ms, truth)
    sig = np.array(truth["sigma_snap_interval_jy"])[:, None]
    flux = np.array(res["flux_jy"])
    assert np.max(np.abs(flux - dft) / sig) < 1e-6
    snap = np.array(res["flux_snapshot_jy"], float)
    ok = np.isfinite(snap)
    assert np.max(np.abs(snap - flux)[ok] / np.broadcast_to(sig, snap.shape)[ok]) < 1e-3
    # Flags and FLAG_ROW removed samples: fewer than baselines x channels.
    assert max(res["samples"]) < 28 * 16
    # The wrong column would double and rotate every flux.
    wrong = lc.light_curves(ms, positions(truth), field=3, column="DATA",
                            images=False)  # fmt: skip
    assert not np.allclose(wrong["flux_jy"], res["flux_jy"])


def test_candidates_and_pixel_round_trip():
    image = np.zeros((16, 16))
    image[5, 7] = 10.0
    image[5, 8] = 9.0  # a neighbour, not a peak
    image[12, 3] = -8.0
    found = lc.candidates(image, 1.0, 5.0, 0, 1.0, 16, 4.0, (math.radians(300.0),
                          math.radians(-36.0)))  # fmt: skip
    assert [(c["sign"], c["x"], c["y"]) for c in found] == [(1, 7, 5), (-1, 3, 12)]
    ra, dec = found[0]["ra_deg"], found[0]["dec_deg"]
    el, em = lc.lm_from_radec(math.radians(ra), math.radians(dec),
                              math.radians(300.0), math.radians(-36.0))  # fmt: skip
    x, y, offset = lc.pixel_of(el, em, 16, 4.0)
    assert (x, y) == (7, 5) and offset < 1e-6


def test_wstack_snapshot_matches_the_wgridder(small):
    ms, _, truth = small
    a = lc.light_curves(ms, positions(truth)[:1], field=3, size=256, interval_steps=15)
    b = lc.light_curves(ms, positions(truth)[:1], field=3, size=256, interval_steps=15,
                        gridder="wstack")  # fmt: skip
    fa, fb = (
        np.array(a["flux_snapshot_jy"], float),
        np.array(b["flux_snapshot_jy"], float),
    )
    assert np.max(np.abs(fa - fb)) < 1e-3 * np.max(np.abs(fa)) + 1e-9
    assert b["settings"]["gridder"] == "wstack"


def test_t4_expectation_pieces():
    t45 = _load("ts_p1_t4t5")
    size = 64
    y, x = np.mgrid[:size, :size] - size // 2
    a = 0.05  # rho = exp(-a (x^2 + y^2) / 2): Lambda = a I
    psf = np.exp(-0.5 * a * (x * x + y * y))
    lam = t45.peak_lambda(psf, size)
    assert np.allclose(lam, a * np.eye(2), rtol=0.02)
    fit, _ = t45.fit_lambda(psf, size)
    assert np.allclose(fit, a * np.eye(2), rtol=1e-6)
    cont = t45.expected_ec(5.0, 1e6, 4e3, lam)
    grid = t45.expected_grid(5.0, 1e6, 4e3, lam)
    assert 0.8 * cont < grid < cont  # sampling lowers the highest pixel
