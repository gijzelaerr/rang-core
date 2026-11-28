# SPDX-License-Identifier: MIT
"""examples/gc-mosaic/gc_mosaic.py on synthetic images (no visibilities)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("scipy")
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "gc-mosaic" / "gc_mosaic.py"
spec = importlib.util.spec_from_file_location("gc_mosaic", SCRIPT)
gc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gc)

FREQ_MHZ = 1284.0
PIXEL_DEG = 20.0 / 3600.0
N = 256
SOURCE = SkyCoord(266.40 * u.deg, -28.94 * u.deg)  # between the two pointings
FLUX = 0.010  # Jy/beam, true (beam-corrected)


def write_pointing(path, centre):
    """A gemclean-like 4-axis image: one point source seen through the beam."""
    w = WCS(naxis=4)
    w.wcs.ctype = ["RA---SIN", "DEC--SIN", "FREQ", "STOKES"]
    w.wcs.crval = [centre.ra.deg, centre.dec.deg, FREQ_MHZ * 1e6, 1.0]
    w.wcs.cdelt = [-PIXEL_DEG, PIXEL_DEG, 856e6, 1.0]
    w.wcs.crpix = [N / 2 + 1, N / 2 + 1, 1.0, 1.0]
    cel = w.celestial
    x, y = cel.world_to_pixel(SOURCE)
    beam = gc.beam_mauch(SOURCE.separation(centre).deg, FREQ_MHZ)
    rows, cols = np.indices((N, N))
    sigma = 6.0  # pixels: wide enough that sub-pixel sampling costs < 1 %
    plane = FLUX * beam * np.exp(-((cols - x) ** 2 + (rows - y) ** 2) / (2 * sigma**2))
    header = w.to_header()
    header["BMAJ"] = header["BMIN"] = 2.3548 * sigma * PIXEL_DEG
    header["BPA"] = 0.0
    fits.writeto(path, plane[None, None].astype(np.float32), header)
    return x, y


def test_mauch_beam_half_power():
    theta_pb = (57.5 / 60.0) * (1500.0 / FREQ_MHZ)
    assert gc.beam_mauch(0.0, FREQ_MHZ) == pytest.approx(1.0)
    assert gc.beam_mauch(theta_pb / 2, FREQ_MHZ) == pytest.approx(0.5, abs=2e-3)
    r = gc.cutoff_radius(gc.beam_function("mauch"), FREQ_MHZ, 0.5)
    assert r == pytest.approx(theta_pb / 2, abs=2e-3)


def test_pbcor_and_mosaic_recover_the_flux(tmp_path):
    centres = [
        SkyCoord(266.25 * u.deg, -28.94 * u.deg),
        SkyCoord(266.55 * u.deg, -28.94 * u.deg),
    ]
    paths = []
    for i, c in enumerate(centres):
        p = tmp_path / f"p{i}-image.fits"
        write_pointing(p, c)
        paths.append(p)

    corrected, b = gc.pbcor(paths[0], tmp_path / "p0-pbcor.fits", beam_name="mauch")
    assert np.nanmax(corrected) == pytest.approx(FLUX, rel=1.5e-2)
    assert np.all(np.isnan(corrected[b < 0.5]))
    assert (tmp_path / "p0-pbcor-pb.fits").exists()

    for frame in ("galactic", "icrs"):
        out = tmp_path / f"mosaic-{frame}.fits"
        plane, den, wcs = gc.mosaic(out, paths, beam_name="mauch", frame=frame)
        x, y = wcs.world_to_pixel(SOURCE)
        peak = plane[round(float(y)), round(float(x))]
        assert peak == pytest.approx(FLUX, rel=2e-2)
        # both pointings contribute at the source: weight = sum of B^2
        bsum = sum(
            gc.beam_mauch(SOURCE.separation(c).deg, FREQ_MHZ) ** 2 for c in centres
        )
        w = den[round(float(y)), round(float(x))]
        assert w == pytest.approx(bsum, rel=2e-2)
        with fits.open(out) as hdul:
            assert hdul[0].header["BMAJ"] > 0


def test_render_two_colour_scheme(tmp_path):
    pytest.importorskip("matplotlib")
    rng = np.random.default_rng(1)
    plane = rng.normal(0.0, 1e-5, (64, 96))
    plane[30:34, 40:44] = 5e-3  # bright
    plane[0, 0] = np.nan
    rgb, used = gc.render_rgb(plane)
    assert rgb.shape == (64, 96, 3)
    assert used["sigma"] == pytest.approx(1e-5, rel=0.1)
    noise = rgb[50, 10]
    assert noise[0] == pytest.approx(noise[1]) == pytest.approx(noise[2])  # grey
    plane[10, 80] = 1e-3  # between faint_max and bright_max
    rgb, used = gc.render_rgb(plane, bright_max=5e-3)
    hot = rgb[10, 80]
    assert hot[0] > hot[2] + 0.1  # a heat-map colour, not grey
    assert np.all(rgb[0, 0] == 0.0)
    path = tmp_path / "m.fits"
    fits.writeto(path, plane.astype(np.float32))
    gc.render(path, tmp_path / "m.png", downsample=2)
    assert (tmp_path / "m.png").stat().st_size > 0
