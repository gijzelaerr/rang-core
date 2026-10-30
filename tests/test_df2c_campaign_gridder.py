"""Big-plan task DF2c: `--gridder` for the campaign drivers and the plan in
their receipts (research/df2c-campaign-gridder.md)."""

import importlib.util
import inspect
import sys
from pathlib import Path

import numpy as np
import pytest
from rang import core_campaign, core_cli, core_grid, core_weights
from rang import core_campaign_1830 as l2
from rang import core_campaign_array as array
from rang import core_campaign_closure as c1
from rang import core_campaign_fieldmodel as l1m

ROOT = Path(__file__).resolve().parents[1]
C_LIGHT = 299792458.0
DRIVERS = (core_campaign, array, l2, l1m, c1)


class Reached(Exception):
    """Raised by a stub to stop a driver once its arguments are seen."""


def _stub(seen):
    def stub(*args, **kwargs):
        seen.append(kwargs)
        raise Reached

    return stub


def test_every_driver_defaults_to_wstack():
    for module in DRIVERS:
        assert inspect.signature(module.run).parameters["gridder"].default == "wstack"
    assert inspect.signature(core_cli.campaign).parameters["gridder"].default == (
        "wstack"
    )


def test_cli_campaign_run_passes_the_gridder(monkeypatch):
    seen = []
    monkeypatch.setitem(core_cli.COMMANDS, "campaign", lambda **kw: seen.append(kw))
    core_cli.main(["--no-receipt", "campaign", "run", "out", "--gridder", "wgrid"])
    core_cli.main(["--no-receipt", "campaign", "run", "out"])
    assert [kw["gridder"] for kw in seen] == ["wgrid", "wstack"]
    with pytest.raises(SystemExit):
        core_cli.main(["--no-receipt", "campaign", "run", "out", "--gridder", "x"])
    # The stage function hands it to K's driver.
    calls = []
    monkeypatch.setattr(core_campaign, "run", _stub(calls))
    with pytest.raises(Reached):
        core_cli.campaign("out", gridder="wgrid")
    assert calls[0]["gridder"] == "wgrid"


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "examples" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("script", "driver", "run_dir", "extra"),
    [
        ("run_luno_array.py", array, "outputs/df2c-test-l1", []),
        (
            "run_luno_1830.py",
            l2,
            "outputs/df2c-test-l2",
            ["--model", "stored", "--fetch", "f"],
        ),
        ("run_l1m.py", l1m, "outputs/l1m-df2c-test", ["--model", "stored"]),
        ("run_c1.py", c1, "outputs/c1-df2c-test", []),
    ],
)
def test_run_scripts_pass_the_gridder(monkeypatch, script, driver, run_dir, extra):
    module = _script(script)
    for argv, expected in (([], "wstack"), (["--gridder", "wgrid"], "wgrid")):
        seen = []
        monkeypatch.setattr(driver, "run", _stub(seen))
        monkeypatch.setattr(sys, "argv", [script, run_dir, "--smoke", *extra, *argv])
        with pytest.raises(Reached):
            module.main()
        assert seen[0]["gridder"] == expected


@pytest.mark.parametrize("driver", [l1m, c1])
def test_l1m_and_c1_hand_the_gridder_to_l1(monkeypatch, tmp_path, driver):
    seen = []
    monkeypatch.setattr(array, "run", _stub(seen))
    if driver is c1:
        monkeypatch.setattr(c1.core_closure, "library", lambda: None)
    with pytest.raises(Reached):
        driver.run(
            tmp_path / "run", *(("stored",) if driver is l1m else ()), gridder="wgrid"
        )
    assert seen[0]["gridder"] == "wgrid"


def test_image_settings_rule():
    image = dict(array.ARRAY_IMAGE)
    assert array.image_settings(image, 4, "wstack") == (image, 4)
    wimage, groups = array.image_settings(image, 4, "wgrid")
    assert groups == 1 and wimage == {**image, "gridder": "wgrid"}
    assert "gridder" not in array.ARRAY_IMAGE and "gridder" not in image
    # With the default argument a gridder named in the image dict holds
    # (DF2b's replays pass it that way); a contradiction is refused.
    assert array.image_settings(wimage, 4, "wstack") == (wimage, 1)
    with pytest.raises(ValueError):
        array.image_settings({**image, "gridder": "wstack"}, 4, "wgrid")
    for bad in ((image, "nufft"), ({**image, "gridder": "nufft"}, "wstack")):
        with pytest.raises(ValueError):
            array.image_settings(bad[0], 4, bad[1])


@pytest.mark.parametrize("driver", DRIVERS)
def test_unknown_gridder_is_refused_before_the_run_directory(tmp_path, driver):
    run_dir = tmp_path / "run"
    args = {core_campaign: (), array: (), l2: ("stored",), l1m: ("stored",), c1: ()}
    with pytest.raises(ValueError):
        driver.run(run_dir, *args[driver], gridder="nufft")
    assert not run_dir.exists()


def test_gridder_settings_record_the_plan(monkeypatch):
    assert core_campaign.gridder_settings("wstack") == {"name": "wstack"}
    monkeypatch.setenv("RAYON_NUM_THREADS", "3")
    rec = core_campaign.gridder_settings("wgrid")
    assert rec["name"] == "wgrid" and rec["epsilon"] == core_grid.WGRID_EPSILON
    assert rec["nthreads"] == 3 and rec["cpu_count"] >= 1
    assert rec["backend"] == "extension"
    assert rec["entry_point"].endswith("rang_core_wgridder_vis2dirty_ex2_f64")


def _synthetic(monkeypatch, nrow=60, nchan=3, seed=11, npix=48, scale=60.0):
    rng = np.random.default_rng(seed)
    freq = np.array([1.0e9, 1.1e9, 1.3e9])[:nchan]
    lam = C_LIGHT / freq.max()
    dx = scale * core_grid.ARCSEC
    uvw = np.stack(
        [
            rng.uniform(-0.4, 0.4, nrow) / dx * lam,
            rng.uniform(-0.4, 0.4, nrow) / dx * lam,
            rng.uniform(-50, 50, nrow),
        ],
        axis=1,
    )
    sample = (
        1.0
        + 0.1 * rng.standard_normal((nrow, nchan))
        + 0.1j * rng.standard_normal((nrow, nchan))
    ).astype(np.complex64)
    weight = rng.uniform(0.5, 1.5, (nrow, nchan)).astype(np.float32)
    weight[3] = 0.0
    monkeypatch.setattr(
        array, "corrected_stokes", lambda *a, **k: (sample.copy(), weight.copy())
    )
    monkeypatch.setattr(array, "model_stokes_mean", lambda *a, **k: (1.0, nrow))
    state = {"frequencies": freq, "model": None}
    extra = {"uvw": uvw, "phase_dir": [1.0, -0.5]}
    image = {
        "width": npix,
        "height": npix,
        "scale_arcsec": scale,
        "w_layers": 8,
        "kernel_size": 7,
        "oversampling": 1023,
        "padding": 1.2,
    }
    imaging = core_weights.imaging_weights(
        uvw,
        core_weights.wsclean_wavelengths(freq),
        weight,
        np.ones(nrow, bool),
        mode="briggs",
        robust=core_campaign.ROBUST,
        width=core_weights.padded_size(npix, 1.2),
        height=core_weights.padded_size(npix, 1.2),
        pixel_scale=core_weights.pixel_scale_radians(scale),
        return_grid=False,
    )["weights"]
    return state, extra, image, (uvw, freq, sample, weight, imaging)


def _header(path):
    from astropy.io import fits

    with fits.open(path) as hdul:
        return dict(hdul[0].header)


def test_l1_image_arm_through_both_gridders(monkeypatch, tmp_path):
    state, extra, image, inputs = _synthetic(monkeypatch)
    boxes = {"main_lobe_half_width": 3, "far_half_width": 12}
    solve = {"added": np.zeros(0, int), "diagnostics": {}}
    m_ws, p_ws = array.image_arm(
        state, extra, solve, tmp_path / "ws", "a", image, 1, boxes=boxes
    )
    direct = core_grid.invert(*inputs, **image)
    assert np.array_equal(p_ws["dirty"], direct["dirty"])
    assert np.array_equal(p_ws["psf"], direct["psf"])
    assert m_ws["gridder_name"] == "wstack" and "wgridder" not in m_ws
    assert "RANGGRID" not in _header(tmp_path / "ws" / "a-dirty.fits")

    wimage, groups = array.image_settings(image, 4, "wgrid")
    m_wg, p_wg = array.image_arm(
        state, extra, solve, tmp_path / "wg", "a", wimage, groups, boxes=boxes
    )
    direct = core_grid.invert(*inputs, **image, gridder="wgrid")
    assert np.array_equal(p_wg["dirty"], direct["dirty"])
    assert np.array_equal(p_wg["psf"], direct["psf"])
    assert m_wg["gridder_name"] == "wgrid"
    assert m_wg["wgridder"]["epsilon"] == core_grid.WGRID_EPSILON
    assert m_wg["wgridder"]["nplanes"] >= 1
    assert _header(tmp_path / "wg" / "a-dirty.fits")["RANGGRID"] == "wgrid"
    # Same sky, different kernel: not equal, close at the centre.
    assert not np.array_equal(p_wg["dirty"], p_ws["dirty"])
    c = image["height"] // 2, image["width"] // 2
    peak = np.abs(p_ws["dirty"]).max()
    assert abs(p_wg["dirty"][c] - p_ws["dirty"][c]) < 0.05 * peak


def test_wgrid_channel_groups_keep_their_plans(monkeypatch):
    _, _, image, (uvw, freq, sample, weight, imaging) = _synthetic(monkeypatch)
    out = array.grouped_invert(
        uvw, freq, sample, weight, imaging, {**image, "gridder": "wgrid"}, 3
    )
    used = [g for g in out["groups"] if not g["skipped"]]
    assert used and all("wgridder" in g for g in used)
    out = array.grouped_invert(uvw, freq, sample, weight, imaging, image, 3)
    assert all("wgridder" not in g for g in out["groups"])
