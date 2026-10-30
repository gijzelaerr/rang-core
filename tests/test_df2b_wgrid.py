"""Big-plan task DF2b: `gridder="wgrid"` in the imaging drivers, the
two-weight entry point and the extension bindings (research/df2b-wgrid.md)."""

import inspect

import numpy as np
import pytest
from rang import core_campaign, core_grid, core_imaging, core_wgridder

C_LIGHT = 299792458.0


def _inputs(nrow=40, nchan=3, seed=5, scale_arcsec=120.0, npix=32):
    rng = np.random.default_rng(seed)
    freq = np.array([1.0e9, 1.1e9, 1.3e9])[:nchan]
    dx = scale_arcsec * core_grid.ARCSEC
    lam = freq.max() / C_LIGHT
    uvw = np.stack(
        [
            rng.uniform(-0.4, 0.4, nrow) / dx / lam,
            rng.uniform(-0.4, 0.4, nrow) / dx / lam,
            rng.uniform(-300, 300, nrow) / lam,
        ],
        axis=1,
    )
    data = (
        rng.standard_normal((nrow, nchan)) + 1j * rng.standard_normal((nrow, nchan))
    ).astype(np.complex64)
    weights = rng.uniform(0.5, 1.5, (nrow, nchan)).astype(np.float32)
    weights[2] = 0.0
    imaging = rng.uniform(0.1, 3.0, (nrow, nchan)).astype(np.float32)
    imaging[5, 1] = 0.0
    settings = {
        "width": npix,
        "height": npix,
        "scale_arcsec": scale_arcsec,
        "w_layers": 8,
        "kernel_size": 7,
        "oversampling": 1023,
        "padding": 1.2,
    }
    return uvw, freq, data, weights, imaging, settings


def test_extension_binds_the_gridder_without_the_standalone_build(monkeypatch):
    def refuse():
        raise AssertionError("the standalone build must not be needed")

    monkeypatch.setattr(core_wgridder, "build_standalone", refuse)
    assert core_wgridder.backend() == "extension"
    assert core_wgridder.library_path() == core_wgridder.core.library_path()
    assert core_wgridder.kernel_row(0) is not None
    uvw, freq, data, weights, _, _ = _inputs()
    # A core-side refusal (no float32 kernel reaches 1e-9) comes back with
    # the core's message through the extension.
    with pytest.raises(ValueError) as error:
        core_wgridder.dirty_psf(
            uvw=uvw,
            freq=freq,
            vis=data,
            wgt=weights,
            npix_x=32,
            npix_y=32,
            pixsize_x=1e-3,
            pixsize_y=1e-3,
            epsilon=1e-9,
            single=True,
        )
    assert str(error.value)


def test_wgrid_invert_equals_fits_image_of_the_product():
    uvw, freq, data, weights, imaging, s = _inputs()
    out = core_grid.invert(uvw, freq, data, weights, imaging, **s, gridder="wgrid")
    product = weights * imaging
    ref = core_wgridder.fits_image(uvw, freq, data, product, 32, 32, s["scale_arcsec"])
    assert np.array_equal(out["dirty"], ref["dirty"])
    assert np.array_equal(out["psf"], ref["psf"])
    assert out["gridder"] == "wgrid" and out["wgridder"]["epsilon"] == 1e-6
    assert out["psf"][16, 16] == 1.0
    st = out["stats"]
    live = product != 0
    assert st["gridded_count"] == int(live.sum()) == out["wgridder"]["nvis"]
    assert st["image_weight"] == pytest.approx(
        float(product.astype(np.float64).sum()), rel=1e-14
    )
    assert st["visibility_weight_sum"] == pytest.approx(
        float(weights[live].astype(np.float64).sum()), rel=1e-14
    )
    assert st["max_gridded_weight"] == float(product.max())
    assert st["n_w_layers"] == out["wgridder"]["nplanes"]
    # The grouped-sum identity of L1's driver: dirty * W / N is the raw image.
    raw_centre = out["wgridder"]["psf_centre_raw"]
    assert st["psf_normalization"] == pytest.approx(st["image_weight"] / raw_centre)


def test_two_weights_are_bit_identical_to_their_product():
    uvw, freq, data, weights, imaging, _ = _inputs(seed=8)
    common = {
        "uvw": uvw,
        "freq": freq,
        "vis": data,
        "npix_x": 32,
        "npix_y": 24,
        "pixsize_x": 1e-3,
        "pixsize_y": 1e-3,
        "epsilon": 1e-6,
    }
    one = core_wgridder.dirty_psf(wgt=weights * imaging, **common)
    two = core_wgridder.dirty_psf(wgt=weights, wgt2=imaging, **common)
    assert np.array_equal(one[0], two[0]) and np.array_equal(one[1], two[1])
    single = core_wgridder.dirty_psf(wgt=weights, wgt2=imaging, single=True, **common)
    assert np.array_equal(
        single[0],
        core_wgridder.dirty_psf(wgt=weights * imaging, single=True, **common)[0],
    )
    # Not both float32: NumPy's float64 product (not the float32 one).
    mixed = core_wgridder.dirty_psf(
        wgt=weights.astype(np.float64), wgt2=imaging, **common
    )
    exact = core_wgridder.dirty_psf(wgt=weights.astype(np.float64) * imaging, **common)
    assert np.array_equal(mixed[0], exact[0])
    assert np.allclose(mixed[0], one[0], rtol=0, atol=1e-6 * np.abs(one[0]).max())
    with pytest.raises(ValueError):
        core_wgridder.dirty_psf(wgt=weights, wgt2=imaging[:, :2], **common)


def test_wstack_stays_the_default_and_bad_names_fail():
    uvw, freq, data, weights, imaging, s = _inputs()
    default = core_grid.invert(uvw, freq, data, weights, imaging, **s)
    named = core_grid.invert(uvw, freq, data, weights, imaging, **s, gridder="wstack")
    assert default["gridder"] == "wstack" and "wgridder" not in default
    assert np.array_equal(default["dirty"], named["dirty"])
    assert default["stats"] == named["stats"]
    with pytest.raises(ValueError, match="gridder"):
        core_grid.invert(uvw, freq, data, weights, imaging, **s, gridder="idg")
    with pytest.raises(RuntimeError, match="no visibility"):
        core_grid.invert(uvw, freq, data, weights * 0, imaging, **s, gridder="wgrid")


def test_wgrid_through_the_imaging_driver():
    rng = np.random.default_rng(20261030)
    nrow, nchan = 12, 3
    data = np.zeros((nrow, nchan, 4), np.complex64)
    data[..., 0] = data[..., 3] = 1.0
    checkpoint = {
        "CORRECTED_DATA": data,
        "FLAG": np.zeros((nrow, nchan, 4), bool),
        "FLAG_ROW": np.zeros(nrow, bool),
    }
    checkpoint["FLAG_ROW"][1] = True
    inputs = {
        "UVW": rng.normal(0, 60.0, (nrow, 3)),
        "WEIGHT_SPECTRUM": np.ones((nrow, nchan, 4), np.float32),
        "CHAN_FREQ": np.array([1.0e9, 1.05e9, 1.1e9]),
        "PHASE_DIR": np.array([1.0, -0.5]),
        "rows": np.ones(nrow, bool),
        "nrow": nrow,
    }
    grid = {**core_imaging.GRID, "width": 32, "height": 32, "scale_arcsec": 120.0}
    w = core_imaging.image_job(inputs, checkpoint, grid=grid, channels=(0, 3))
    e = core_imaging.image_job(
        inputs, checkpoint, grid=grid, channels=(0, 3), gridder="wgrid"
    )
    assert e["gridder"] == "wgrid" and w["gridder"] == "wstack"
    assert (
        e["stats"]["gridded_count"] == w["stats"]["gridded_count"] == (nrow - 1) * nchan
    )
    assert e["stats"]["image_weight"] == pytest.approx(
        w["stats"]["image_weight"], rel=1e-12
    )
    assert e["psf"][16, 16] == 1.0
    # A unit point source at the phase centre: the exact dirty image peaks at
    # one in the centre pixel, as w-stacking's does.
    assert e["dirty"][16, 16] == pytest.approx(1.0, abs=1e-6)
    _, extra = core_imaging._fits_header(inputs, e["stats"], grid, 0.5, e)
    assert extra["RANGGRID"] == "wgrid" and extra["WSCGKRNL"] == e["wgridder"]["supp"]
    _, extra_w = core_imaging._fits_header(inputs, w["stats"], grid, 0.5, w)
    assert "RANGGRID" not in extra_w and extra_w["WSCGKRNL"] == 7


def test_driver_signatures_default_to_wstack():
    for fn in (core_grid.invert, core_imaging.image_job, core_imaging.run):
        assert inspect.signature(fn).parameters["gridder"].default == "wstack"
    assert (
        inspect.signature(core_campaign.image_arm).parameters["gridder"].default
        == "wstack"
    )
    assert (
        core_imaging._parser().parse_args(["run", "x", "--gridder", "wgrid"]).gridder
        == "wgrid"
    )
