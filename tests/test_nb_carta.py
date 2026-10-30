"""Task NB-CARTA: the optional CARTA helper `rang.notebook.carta`
(research/nb-carta.md).

The FITS writer, the header of a core image and the unavailable path
(Windows, a missing or wrong wrapper, no backend, an unreachable backend)
run everywhere and start nothing. The notebook 04 cell is executed in
isolation with the switch off and on-but-unavailable. The live path opens an
image in a running CARTA backend and runs only with `RANG_NOTEBOOK_CARTA=1`
and `available()`.
"""

import contextlib
import io
import os
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from rang.notebook import carta

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def no_backend(monkeypatch, tmp_path):
    for name in (
        "RANG_CARTA_URL",
        "RANG_CARTA_WEBDRIVER",
        "RANG_CARTA_SESSION_ID",
        "RANG_CARTA_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RANG_CARTA_DIR", str(tmp_path / "session"))
    return tmp_path


@pytest.fixture
def fake_wrapper(monkeypatch):
    """A stand-in for carta-python's `carta.session` (no network)."""

    class Session:
        @classmethod
        def create(cls, *args, **kwargs):
            raise AssertionError("must not connect")

        interact = create

        def save_rendered_view(self, path):
            raise AssertionError("must not render")

    package = types.ModuleType("carta")
    module = types.ModuleType("carta.session")
    module.Session = Session
    package.session = module
    monkeypatch.setitem(sys.modules, "carta", package)
    monkeypatch.setitem(sys.modules, "carta.session", module)
    return Session


def test_write_fits_image_gains_wsclean_axes(tmp_path):
    fits = pytest.importorskip("astropy.io.fits")
    from rang import core_grid

    image = np.arange(12, dtype=np.float64).reshape(3, 4)
    header = core_grid.wcs_header(
        np.array([np.radians(294.85), np.radians(-63.71)]),
        4,
        3,
        8.0,
        np.array([1.0e9, 1.1e9]),
    )
    path = carta.write_fits(image, tmp_path / "a.fits", wcs=header)
    with fits.open(path) as hdul:
        data, h = hdul[0].data, hdul[0].header
    assert data.shape == (1, 1, 3, 4) and data.dtype.newbyteorder("=") == np.float32
    np.testing.assert_array_equal(data[0, 0], image.astype(np.float32))
    assert h["CTYPE1"] == "RA---SIN" and h["CTYPE3"] == "FREQ"
    assert h["CRPIX1"] == 3.0 and h["CDELT1"] == pytest.approx(-8.0 / 3600)
    assert h["ORIGIN"] == "rang.notebook.carta"


def test_write_fits_cube_and_plain_array(tmp_path):
    fits = pytest.importorskip("astropy.io.fits")
    cube = np.random.default_rng(1).normal(size=(5, 6, 7))
    header = {
        "CTYPE1": "RA---SIN",
        "CTYPE2": "DEC--SIN",
        "CTYPE3": "FREQ",
        "CRVAL3": 1.0e9,
        "CDELT3": 1.0e6,
        "CTYPE4": "STOKES",
    }
    with fits.open(carta.write_fits(cube, tmp_path / "c.fits", wcs=header)) as hdul:
        assert hdul[0].data.shape == (1, 5, 6, 7)
        assert hdul[0].header["CDELT3"] == 1.0e6
    with fits.open(carta.write_fits(cube[0], tmp_path / "p.fits")) as hdul:
        assert hdul[0].data.shape == (6, 7)
    with pytest.raises(ValueError):
        carta.write_fits(np.zeros(3), tmp_path / "bad.fits")


def test_write_fits_accepts_an_astropy_wcs(tmp_path):
    fits = pytest.importorskip("astropy.io.fits")
    wcs = pytest.importorskip("astropy.wcs")
    w = wcs.WCS(naxis=2)
    w.wcs.ctype = ["RA---SIN", "DEC--SIN"]
    w.wcs.crval = [294.85, -63.71]
    path = carta.write_fits(np.ones((4, 4)), tmp_path / "w.fits", wcs=w)
    with fits.open(path) as hdul:
        assert hdul[0].header["CTYPE2"] == "DEC--SIN"
        assert hdul[0].header["CRVAL1"] == pytest.approx(294.85)


def test_image_header_from_an_image_result():
    ds = types.SimpleNamespace(
        extra={"phase_dir": np.array([np.radians(294.85), np.radians(-63.71)])},
        state={"frequencies": np.linspace(0.9e9, 1.6e9, 8)},
    )
    img = {"params": {"width": 64, "height": 32, "scale_arcsec": 4.0}}
    h = carta.image_header(ds, img)
    assert h["CRPIX1"] == 33.0 and h["CRPIX2"] == 17.0
    assert h["CRVAL1"] == pytest.approx(-65.15)
    assert h["CDELT2"] == pytest.approx(4.0 / 3600)


def test_stage_writes_arrays_and_copies_paths(no_backend, tmp_path):
    pytest.importorskip("astropy")
    staged = carta._stage({"dirty": np.ones((4, 4))}, None, "x")
    assert staged == carta.session_dir() / "x.fits" and staged.is_file()
    again = carta._stage(staged, None, None)
    assert again == staged.resolve()  # already in the session directory
    outside = tmp_path / "outside.fits"
    outside.write_bytes(staged.read_bytes())
    copied = carta._stage(outside, None, None)
    assert copied.parent == carta.session_dir() and copied.name == "outside.fits"
    with pytest.raises(FileNotFoundError):
        carta._stage(tmp_path / "missing.fits", None, None)


def test_windows_is_unavailable(monkeypatch, no_backend, fake_wrapper):
    monkeypatch.setattr(carta, "_platform", lambda: "win32")
    assert not carta.available()
    assert "no Windows build" in carta.problem()
    with pytest.raises(carta.CartaUnavailable, match="Windows"):
        carta.open(np.zeros((4, 4)))


def test_missing_wrapper_names_the_install_command(monkeypatch, no_backend):
    monkeypatch.setattr(carta, "_platform", lambda: "linux")
    monkeypatch.setitem(sys.modules, "carta", None)  # import fails
    monkeypatch.setitem(sys.modules, "carta.session", None)
    reason = carta.problem()
    assert carta.WRAPPER_COMMIT in reason and "not installed" in reason
    with pytest.raises(carta.CartaUnavailable, match="989af8ed"):
        carta.open(np.zeros((4, 4)))


def test_the_unrelated_pypi_carta_is_refused(monkeypatch, no_backend):
    monkeypatch.setattr(carta, "_platform", lambda: "linux")
    package = types.ModuleType("carta")
    module = types.ModuleType("carta.session")
    module.Session = type("Session", (), {})
    monkeypatch.setitem(sys.modules, "carta", package)
    monkeypatch.setitem(sys.modules, "carta.session", module)
    assert "unrelated" in carta.problem()


def test_no_backend_configured(monkeypatch, no_backend, fake_wrapper):
    monkeypatch.setattr(carta, "_platform", lambda: "linux")
    reason = carta.problem()
    assert "RANG_CARTA_URL" in reason and "docker_commands" in reason
    with pytest.raises(carta.CartaUnavailable):
        carta.connect()
    # Nothing was written: the check comes before staging.
    assert not any(carta.session_dir().iterdir())


def test_unreachable_backend(monkeypatch, no_backend, fake_wrapper):
    monkeypatch.setattr(carta, "_platform", lambda: "linux")
    monkeypatch.setenv("RANG_CARTA_URL", "http://127.0.0.1:9/?token=x")
    assert "does not answer" in carta.problem(timeout=0.5)
    assert not carta.available(timeout=0.5)


def test_docker_commands_bind_loopback_only(tmp_path):
    backend, browser = carta.docker_commands(tmp_path)
    assert backend[:2] == ["docker", "run"] and carta.CARTA_IMAGE in backend
    assert "--enable_scripting" in backend
    ports = [backend[i + 1] for i, a in enumerate(backend) if a == "-p"]
    assert ports and all(p.startswith("127.0.0.1:") for p in ports)
    assert f"{tmp_path.resolve()}:/images:ro" in backend
    assert carta.CHROMIUM_IMAGE in browser
    assert f"--network=container:{carta.CONTAINER}" in browser
    assert "@sha256:" in carta.CARTA_IMAGE and "@sha256:" in carta.CHROMIUM_IMAGE


def test_skip_line_and_switch(monkeypatch):
    monkeypatch.delenv(carta.SWITCH, raising=False)
    assert not carta.switch()
    monkeypatch.setenv(carta.SWITCH, "1")
    assert carta.switch()
    assert carta.skip_line() == (
        "skipped: set RANG_NOTEBOOK_CARTA=1 to open the images in a running "
        "CARTA backend (Linux or macOS)"
    )
    assert carta.skip_line("why").endswith(" (why)")


def _carta_cell():
    nbformat = pytest.importorskip("nbformat")
    book = nbformat.read(ROOT / "notebooks" / "04-imaging.ipynb", as_version=4)
    cells = [c for c in book.cells if c.cell_type == "code" and "carta" in c.source]
    assert len(cells) == 1
    assert not cells[0].outputs and cells[0].execution_count is None
    return cells[0].source


@pytest.mark.parametrize("switch", ["0", "1"])
def test_notebook_cell_prints_its_skip_line(monkeypatch, no_backend, switch):
    pytest.importorskip("IPython")
    monkeypatch.setenv(carta.SWITCH, switch)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(_carta_cell(), {"display": print})  # noqa: S102
    line = out.getvalue().strip()
    assert line.startswith("skipped: set RANG_NOTEBOOK_CARTA=1")
    assert (line != carta.skip_line()) == (switch == "1")  # the reason when on


@pytest.mark.skipif(
    os.environ.get("RANG_NOTEBOOK_CARTA") != "1", reason="RANG_NOTEBOOK_CARTA != 1"
)
def test_live_open_and_snapshot(tmp_path):
    if not carta.available():
        pytest.skip(carta.problem())
    pytest.importorskip("astropy")
    yy, xx = np.mgrid[:256, :256]
    blob = np.exp(-((xx - 128.0) ** 2 + (yy - 100.0) ** 2) / 200.0)
    session = carta.open(blob, name="test-nb-carta.fits")
    try:
        frame = session.active_frame()
        assert list(frame.shape)[-2:] == [256, 256]
        png = carta.snapshot(session, tmp_path / "view.png")
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        carta.close(session)
