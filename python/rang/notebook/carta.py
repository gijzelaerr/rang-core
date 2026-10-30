"""Open images and cubes in CARTA from a notebook (research/nb-carta.md).

Optional. CARTA (https://cartavis.org, GPL-3.0) shows large images and
cubes with tiled rendering, profiles and moments, which matplotlib does
not. This module writes a NumPy image, a cube or the core's dirty image to
FITS in a session directory and opens it in a running CARTA backend through
CARTA's Python wrapper, carta-python (GPL-3.0), which has no PyPI release:

    pip install -e '.[carta]'      # rang-core[carta] once released
    pip install 'carta @ git+https://github.com/CARTAvis/carta-python@989af8ed97238931abe5f235add37e0813bf7e0b'

(the PyPI package named `carta` is unrelated: never install it). The
backend runs natively (Linux, macOS) or in the pinned container
`CARTA_IMAGE`; CARTA has no Windows build, so on Windows `available()` is
False and the notebook cells print their skip line. Nothing here starts a
container or opens a port unless a function named for it is called
(`start_docker`); `docker_commands` only returns the command lines.

Configuration, all optional:

- `RANG_CARTA_URL`: the frontend URL with its token, as the backend prints
  it ("CARTA is accessible at ...");
- `RANG_CARTA_WEBDRIVER`: a WebDriver URL for a headless browser that draws
  the views (default `http://127.0.0.1:4444`, the pinned Chromium);
- `RANG_CARTA_SESSION_ID`: attach to a session open in your own browser
  instead (the session id shown in CARTA's "About" dialog);
- `RANG_CARTA_DIR`: the session directory the files are written to
  (default `<RANG_NOTEBOOK_CACHE>/carta`);
- `RANG_CARTA_ROOT`: that directory as the backend sees it, relative to the
  backend's top-level folder (default `/`: the container mounts it as its
  top-level folder `/images`; for a native backend started with the
  top-level folder `/`, the directory's absolute path).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

# Pinned by digest (research/nb-carta.md, install path).
CARTA_IMAGE = (
    "cartavis/carta:6.0.0"
    "@sha256:951834b9ff3f2de5b5ced18aa486ed6cdc00e52b526945ca321d53cf2d3d79f2"
)
CHROMIUM_IMAGE = (
    "selenium/standalone-chromium:155.0"
    "@sha256:c7c17cd79c62819a8329df00e610dbc4073c279da034a6f37135d454eb0d8870"
)
WRAPPER_COMMIT = "989af8ed97238931abe5f235add37e0813bf7e0b"  # carta-python v1.2.0
WRAPPER_REQUIREMENT = (
    f"carta @ git+https://github.com/CARTAvis/carta-python@{WRAPPER_COMMIT}"
)
INSTALL = f"pip install 'rang-core[carta]' '{WRAPPER_REQUIREMENT}'"
CONTAINER = "rang-carta"
BROWSER_CONTAINER = "rang-carta-chromium"
PORT = 3002
WEBDRIVER_PORT = 4444
DEFAULT_WEBDRIVER = f"http://127.0.0.1:{WEBDRIVER_PORT}"
MOUNT = "/images"  # the container's top-level folder
DEFAULT_ROOT = "/"  # the session directory, relative to the top-level folder
# CARTA draws the raster with WebGL; a headless Chromium without a GPU needs
# SwiftShader, or the snapshot shows the axes around an empty raster.
CHROME_OPTIONS = (
    "--window-size=1280,900",
    "--enable-unsafe-swiftshader",
    "--use-angle=swiftshader",
    "--ignore-gpu-blocklist",
)
# Copy at most this much into the session directory; mount larger files.
COPY_LIMIT = 1 << 30

SWITCH = "RANG_NOTEBOOK_CARTA"
SWITCH_TEXT = "open the images in a running CARTA backend (Linux or macOS)"


class CartaUnavailable(RuntimeError):
    """The wrapper or the backend is missing; the message says what to do."""


def switch():
    """True when `RANG_NOTEBOOK_CARTA` is set to 1 (default off)."""
    return os.environ.get(SWITCH, "0") == "1"


def skip_line(reason=""):
    """The line a gated cell prints, in the format of `rang.notebook.science`."""
    text = f"skipped: set {SWITCH}=1 to {SWITCH_TEXT}"
    return text + (f" ({reason})" if reason else "")


# --- availability -------------------------------------------------------------


def _platform():
    return sys.platform


def _wrapper():
    """carta-python's `Session` class, or raise `CartaUnavailable`."""
    try:
        from carta.session import Session
    except ImportError as error:
        raise CartaUnavailable(
            f"CARTA's Python wrapper is not installed ({error}); install it "
            f"with: {INSTALL}"
        ) from None
    if not all(
        hasattr(Session, name) for name in ("create", "interact", "save_rendered_view")
    ):
        raise CartaUnavailable(
            "the installed `carta` is not CARTA's wrapper (the PyPI package "
            f"`carta` is unrelated); install it with: {INSTALL}"
        )
    return Session


def frontend_url():
    """`RANG_CARTA_URL`, or None."""
    return os.environ.get("RANG_CARTA_URL") or None


def webdriver_url():
    return os.environ.get("RANG_CARTA_WEBDRIVER") or DEFAULT_WEBDRIVER


def _session_id():
    value = os.environ.get("RANG_CARTA_SESSION_ID")
    return int(value) if value else None


def _reachable(url, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def problem(timeout=2.0):
    """Why CARTA cannot be used from here, or None when it can.

    Checks, in order: the platform (no Windows build), the wrapper, the
    backend URL and that it answers, and the headless browser's WebDriver
    (unless a session in your own browser is configured). Starts nothing.
    """
    if _platform() == "win32":
        return (
            "CARTA has no Windows build; run the notebook in WSL or on Linux "
            "or macOS with a CARTA backend"
        )
    try:
        _wrapper()
    except CartaUnavailable as error:
        return str(error)
    url = frontend_url()
    if url is None:
        return (
            "no CARTA backend configured: set RANG_CARTA_URL to the URL the "
            "backend prints (start one with rang.notebook.carta.start_docker() "
            "or the commands of docker_commands())"
        )
    base = url.split("?", 1)[0]
    if not _reachable(base, timeout):
        return f"the CARTA backend at {base} does not answer"
    if _session_id() is None and not _reachable(
        webdriver_url().rstrip("/") + "/status", timeout
    ):
        return (
            f"no headless browser at {webdriver_url()} (set RANG_CARTA_WEBDRIVER, "
            "or RANG_CARTA_SESSION_ID to use a session open in your own browser)"
        )
    return None


def available(timeout=2.0):
    """True when the wrapper imports and the backend answers (`problem()`)."""
    return problem(timeout) is None


# --- FITS ---------------------------------------------------------------------


def session_dir():
    """The directory `open` writes to (`RANG_CARTA_DIR`), created on demand."""
    configured = os.environ.get("RANG_CARTA_DIR")
    if configured:
        path = Path(configured)
    else:
        from .data import default_cache_dir

        path = default_cache_dir() / "carta"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _header_items(wcs):
    if wcs is None:
        return {}
    if hasattr(wcs, "to_header"):  # astropy.wcs.WCS
        return dict(wcs.to_header().items())
    return dict(wcs)


def write_fits(array, path, *, wcs=None, overwrite=True):
    """Write a NumPy image `(y, x)` or cube `(plane, y, x)` as float32 FITS.

    `wcs`: an astropy WCS or a dict of FITS keys (`image_header`,
    `core_grid.wcs_header`). When the header names more axes than the array
    has (WSClean's FREQ and STOKES), degenerate axes are added, so a 2-D
    dirty image is written as rang's campaigns write it. Returns the path.
    """
    from astropy.io import fits

    data = np.asarray(array, np.float32)
    if data.ndim not in (2, 3, 4):
        raise ValueError(f"expected a 2-D image or a 3-D cube, got shape {data.shape}")
    header = _header_items(wcs)
    named = max(
        [
            int(key[5:])
            for key in header
            if key.startswith("CTYPE") and key[5:].isdigit()
        ]
        or [0]
    )
    while data.ndim < named:
        data = data[np.newaxis]
    hdu = fits.PrimaryHDU(data)
    for key, value in header.items():
        if key in ("SIMPLE", "BITPIX", "EXTEND") or key.startswith("NAXIS"):
            continue
        hdu.header[key] = value
    hdu.header.setdefault("ORIGIN", "rang.notebook.carta")
    path = Path(path)
    hdu.writeto(str(path), overwrite=overwrite)
    return path


def image_header(ds, img):
    """The WSClean-convention header of an `image.image` result on `ds`."""
    from .. import core_grid

    p = img["params"]
    return core_grid.wcs_header(
        ds.extra["phase_dir"],
        p["width"],
        p["height"],
        p["scale_arcsec"],
        ds.state["frequencies"],
    )


def channel_cube(ds, sol=None, planes=8, mode="briggs", robust=0.5, **geometry):
    """A cube of dirty images, one per block of adjacent channels.

    Each plane is `image.image` with the channels outside its block flagged
    on top of the solve's (or no) added flags; nothing is reimplemented.
    The channel count must divide by `planes` so the frequency axis is
    linear. A block whose cells are all flagged (an RFI-occupied band) is a
    NaN plane with metrics None. Returns `cube` `(planes, y, x)`, its
    `header`, the block centre `frequencies` and the per-plane `metrics`.
    """
    from . import image as imaging

    s = ds.state
    freqs = np.asarray(s["frequencies"], float)
    if len(freqs) % planes:
        raise ValueError(f"{len(freqs)} channels do not divide into {planes} planes")
    base = (
        np.asarray(sol["added"], bool) if sol is not None else np.zeros_like(s["train"])
    )
    params = {**imaging.DEFAULTS, **geometry}
    flagged = np.asarray(s["original_flags"], bool).all(axis=-1) | base
    blocks = np.arange(len(freqs)).reshape(planes, -1)
    cube, metrics = [], []
    for block in blocks:
        if flagged[:, block].all():
            cube.append(np.full((params["height"], params["width"]), np.nan))
            metrics.append(None)
            continue
        outside = np.ones(len(freqs), bool)
        outside[block] = False
        added = base | outside[np.newaxis, :]
        img = imaging.image(ds, sol, added=added, mode=mode, robust=robust, **geometry)
        cube.append(img["dirty"])
        metrics.append(img["metrics"])
    header = image_header(ds, {"params": params})
    step = freqs[1] - freqs[0] if len(freqs) > 1 else 0.0
    width = step * blocks.shape[1]
    header["CRVAL3"] = float(freqs[blocks[0]].mean())
    header["CDELT3"] = float(width)
    return {
        "cube": np.stack(cube),
        "header": header,
        "frequencies": freqs[blocks].mean(axis=1),
        "metrics": metrics,
    }


# --- the backend --------------------------------------------------------------


def backend_root():
    """The session directory as the backend sees it (`RANG_CARTA_ROOT`)."""
    return os.environ.get("RANG_CARTA_ROOT") or DEFAULT_ROOT


def connect(url=None, *, webdriver=None, session_id=None, timeout=30):
    """A carta-python `Session` on the running backend.

    With `session_id` (or `RANG_CARTA_SESSION_ID`) it attaches to a session
    open in your own browser; otherwise a headless browser at `webdriver`
    (`RANG_CARTA_WEBDRIVER`) opens a new one, which `close` shuts.
    """
    reason = problem() if url is None else None
    if reason is not None:
        raise CartaUnavailable(reason)
    Session = _wrapper()
    url = url or frontend_url()
    session_id = session_id if session_id is not None else _session_id()
    if session_id is not None:
        return Session.interact(url, int(session_id))
    from carta.browser import Browser
    from selenium import webdriver as selenium

    options = selenium.ChromeOptions()
    for option in CHROME_OPTIONS:
        options.add_argument(option)
    browser = Browser(
        selenium.Remote,
        command_executor=webdriver or webdriver_url(),
        options=options,
    )
    return Session.create(browser, url, timeout=timeout)


def _stage(path_or_array, wcs, name):
    """The FITS file in the session directory that the backend will open."""
    directory = session_dir()
    if isinstance(path_or_array, (str, os.PathLike)):
        source = Path(path_or_array).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.parent == directory.resolve():
            return source
        if source.stat().st_size > COPY_LIMIT:
            raise ValueError(
                f"{source} is larger than {COPY_LIMIT >> 30} GiB: point "
                "RANG_CARTA_DIR (and the backend's /images mount) at its "
                "directory instead of copying it"
            )
        target = directory / (name or source.name)
        shutil.copyfile(source, target)
        return target
    if isinstance(path_or_array, dict) and "dirty" in path_or_array:
        array = path_or_array["dirty"]  # an image.image result
    else:
        array = path_or_array
    stem = name or f"rang-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**6}"
    if not stem.endswith(".fits"):
        stem += ".fits"
    return write_fits(array, directory / stem, wcs=wcs)


def open(path_or_array, *, wcs=None, name=None, session=None):
    """Open a FITS file, a NumPy image or cube, or the dirty image of an
    `image.image` result in CARTA; returns the session handle.

    Arrays are written to FITS in `session_dir()` (with `wcs`, an astropy
    WCS or a dict of FITS keys such as `image_header(ds, img)`); a FITS path
    is copied there unless it already lies there. The file is opened in
    `session` (default: a new `connect()`). Raises `CartaUnavailable` with
    the install or start command when `available()` is False.
    """
    if session is None:
        reason = problem()
        if reason is not None:
            raise CartaUnavailable(reason)
    path = _stage(path_or_array, wcs, name)
    if session is None:
        session = connect()
    session.open_image(backend_root().rstrip("/") + "/" + path.name)
    return session


def _raster_drawn(png):
    """True unless the centre of the rendered view is transparent (the
    raster not drawn yet); True when matplotlib is not there to check."""
    try:
        import io

        import matplotlib.image as mpimg
    except ImportError:
        return True
    pixels = mpimg.imread(io.BytesIO(png), format="png")
    if pixels.ndim < 3 or pixels.shape[2] < 4:
        return True
    h, w = pixels.shape[:2]
    centre = pixels[h // 3 : 2 * h // 3, w // 3 : 2 * w // 3, 3]
    return bool((centre > 0).mean() > 0.5)


def snapshot(session, path, *, attempts=5, wait=1.0):
    """Save the current view of `session` as a PNG at `path`; returns it.

    CARTA may return a partly rendered view; the snapshot is retried until
    the raster is drawn (at most `attempts` times, `wait` seconds apart).
    """
    path = Path(path)
    png = b""
    for attempt in range(attempts):
        time.sleep(wait)
        png = session.rendered_view_data()
        if _raster_drawn(png):
            break
    path.write_bytes(png)
    return path


def close(session):
    """Close the headless browser of `session` (a session in your own
    browser is left open)."""
    session.close()
    # carta-python's Session.__del__ closes again; make that a no-op.
    session._browser = None
    session._backend = None


# --- containers (explicit only) -----------------------------------------------


def docker_commands(data_dir=None, port=PORT):
    """The `docker run` lines for the pinned backend and headless Chromium.

    The backend mounts `data_dir` (default `session_dir()`) read-only at
    /images and publishes its port and the WebDriver's on 127.0.0.1 only;
    Chromium shares the backend's network namespace, so both see the same
    `localhost` URL. Returned, not run.
    """
    data_dir = Path(data_dir) if data_dir else session_dir()
    backend = [
        "docker", "run", "-d", "--rm", "--name", CONTAINER,
        "-p", f"127.0.0.1:{port}:{port}",
        "-p", f"127.0.0.1:{WEBDRIVER_PORT}:{WEBDRIVER_PORT}",
        "-v", f"{data_dir.resolve()}:{MOUNT}:ro",
        CARTA_IMAGE, "--enable_scripting", "--port", str(port),
    ]  # fmt: skip
    browser = [
        "docker", "run", "-d", "--rm", "--name", BROWSER_CONTAINER,
        f"--network=container:{CONTAINER}", "--shm-size=2g",
        CHROMIUM_IMAGE,
    ]  # fmt: skip
    return [backend, browser]


def start_docker(data_dir=None, timeout=60):
    """Start the two pinned containers (only when called) and set
    `RANG_CARTA_URL`, `RANG_CARTA_WEBDRIVER` and `RANG_CARTA_DIR` for this
    process. Returns the frontend URL (with its token)."""
    import re

    data_dir = Path(data_dir) if data_dir else session_dir()
    # Create it first: a bind-mount source docker creates is owned by root.
    data_dir.mkdir(parents=True, exist_ok=True)
    for command in docker_commands(data_dir):
        subprocess.run(command, check=True, capture_output=True, text=True)
    pattern = re.compile(r"CARTA is accessible at (http://\S+)")
    started = time.perf_counter()
    url = None
    while time.perf_counter() - started < timeout:
        logs = subprocess.run(
            ["docker", "logs", CONTAINER], check=False, capture_output=True, text=True
        )
        match = pattern.search(logs.stdout + logs.stderr)
        if match:
            url = match.group(1)
            if _reachable(DEFAULT_WEBDRIVER + "/status", 2.0):
                break
        time.sleep(1)
    if url is None:
        raise CartaUnavailable(f"the CARTA container did not start in {timeout} s")
    os.environ["RANG_CARTA_URL"] = url
    os.environ["RANG_CARTA_WEBDRIVER"] = DEFAULT_WEBDRIVER
    os.environ["RANG_CARTA_DIR"] = str(data_dir)
    os.environ["RANG_CARTA_ROOT"] = DEFAULT_ROOT
    return url


def stop_docker():
    """Stop the containers `start_docker` started (they remove themselves)."""
    for name in (BROWSER_CONTAINER, CONTAINER):
        subprocess.run(
            ["docker", "stop", name], check=False, capture_output=True, text=True
        )
