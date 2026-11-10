"""G8 (research/g8-wheel.md): gemclean from the wheel, the console script
`gemclean` and `python -m rang.gemclean` over `rang._core.gemclean_main`.

In the wheel's pytest subset (tools/wheel/test.py), so nothing here skips:
exit codes and streams, `-version`, a small imaging run on an MS written
by the core writer, `-j` (fresh and in one process), Ctrl-C (SIGINT on
POSIX, CTRL_BREAK on Windows) and rang-core's `image.gemclean: auto`.
The byte-identity of the script's files and the source build's is
tests/test_g8_identity.py (checkout only)."""

import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

import numpy as np
from rang import _core, core, core_ms_write
from rang import core_pipeline as pipe

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)

NANT, NCHAN = 8, 8
NROW = 28 * 30  # 28 baselines x 30 integrations
SEED = 20261180  # not in rang.simtruth.SEEDS
FILES = ("dirty", "psf", "model", "residual", "image")
SMALL = [
    "-size", "128", "128", "-scale", "4asec", "-weight", "briggs", "0",
    "-niter", "200", "-gain", "0.1", "-mgain", "0.8", "-abs-threshold", "0.01",
    "-data-column", "DATA", "-field", "0", "-no-update-model-required",
]  # fmt: skip


def script():
    """The console script the installer wrote beside this interpreter."""
    scripts = Path(sysconfig.get_path("scripts"))
    name = "gemclean.exe" if os.name == "nt" else "gemclean"
    path = scripts / name
    if not path.is_file():  # a venv whose scripts dir differs from sysconfig's
        path = Path(sys.executable).parent / name
    assert path.is_file(), f"no console script {path}"
    return path


def tiny_ms(path):
    """W1's MS with 8 antennas, one field and a 1 Jy point source at the
    phase centre (XX = YY = 1, XY = YX = 0); 10 % of the cells flagged."""
    ms = w1.make_ms(path, NROW, NCHAN, ncorr=4, flag="tiled", seed=SEED, nant=NANT)
    base = np.array([5109224.0, 2006790.0, -3239100.0])
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(NANT)
        t.putcol("POSITION", base + 150.0 * np.arange(NANT)[:, None] * [1, 0.5, 0.2])
        t.putcol("NAME", [f"m{a:03d}" for a in range(NANT)])
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(1)
        t.putcol("NAME", ["CAL"])
        t.putcol("PHASE_DIR", np.array([[[0.0, -1.0]]]))
    data = np.zeros((NROW, NCHAN, 4), np.complex64)
    data[..., 0] = data[..., 3] = 1.0
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("DATA", data)
    return ms


def run(argv, **kw):
    return subprocess.run(
        [str(a) for a in argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=600,
        **kw,
    )


def test_exit_codes_and_streams(tmp_path):
    out = run([script(), "-version"])
    assert out.returncode == 0, out.stderr
    assert out.stdout == f"gemclean {_core_version()}\n" and out.stderr == ""
    out = run([sys.executable, "-m", "rang.gemclean", "--version"])
    assert out.returncode == 0 and out.stdout.startswith("gemclean ")
    out = run([script()])
    assert out.returncode == 2 and out.stdout == ""
    assert "exactly one Measurement Set is needed" in out.stderr
    assert "usage: gemclean" in out.stderr
    out = run([script(), "-h"])
    assert out.returncode == 2 and "usage: gemclean" in out.stderr
    out = run([script(), "-no-such-option", "x.ms"])
    assert out.returncode == 2 and out.stderr.startswith("gemclean: unknown option")
    out = run([script(), "-size", "64", "64", "-scale", "2asec", tmp_path / "none.ms"])
    assert out.returncode == 2 and out.stdout == ""
    assert out.stderr.startswith("gemclean: ")


def _core_version():
    # Not tomllib: the wheel is also tested on Python 3.10.
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'(?m)^version = "([^"]+)"', text).group(1)


def test_a_small_imaging_run(tmp_path):
    ms = tiny_ms(tmp_path / "x.ms")
    out = run([script(), "-name", tmp_path / "g", *SMALL, "-j", "2", ms])
    assert out.returncode == 0, out.stdout + out.stderr
    assert "wall" in out.stdout.splitlines()[-1]
    for kind in FILES:
        assert (tmp_path / f"g-{kind}.fits").is_file(), kind
    report = json.loads((tmp_path / "g-report.json").read_text(encoding="utf-8"))
    assert report["threads"] == "2" or report["threads"] == 2
    from astropy.io import fits

    dirty = np.squeeze(fits.getdata(tmp_path / "g-dirty.fits"))
    peak = np.unravel_index(np.argmax(dirty), dirty.shape)
    assert peak == (64, 64), peak
    assert abs(dirty[64, 64] - 1.0) < 1e-3, dirty[64, 64]
    model = np.squeeze(fits.getdata(tmp_path / "g-model.fits"))
    assert 0.9 < model.sum() < 1.1, model.sum()


def _report_threads(prefix):
    report = json.loads(Path(f"{prefix}-report.json").read_text(encoding="utf-8"))
    return int(report["threads"])


def test_threads_fresh_and_in_one_process(tmp_path):
    ms = tiny_ms(tmp_path / "x.ms")
    for j in (1, 3):
        out = run([script(), "-name", tmp_path / f"j{j}", *SMALL, "-j", str(j), ms])
        assert out.returncode == 0, out.stderr
        assert _report_threads(tmp_path / f"j{j}") == j
    for kind in FILES:
        a = (tmp_path / f"j1-{kind}.fits").read_bytes()
        assert a == (tmp_path / f"j3-{kind}.fits").read_bytes(), kind
    # Twice in one process: rayon's global pool exists after the first -j, so
    # the second run gets a pool of its own and still reports its -j.
    code = (
        "import sys; from rang import _core\n"
        "a = sys.argv[1:]; ms, p = a[-1], a[-2]\n"
        "opts = a[:-2]\n"
        "r1 = _core.gemclean_main(['-name', p + '-a', *opts, '-j', '1', ms])\n"
        "r2 = _core.gemclean_main(['-name', p + '-b', *opts, '-j', '3', ms])\n"
        "print('codes', r1, r2)\n"
    )
    out = run([sys.executable, "-c", code, *SMALL, tmp_path / "in", ms])
    assert out.returncode == 0 and "codes 0 0" in out.stdout, out.stdout + out.stderr
    assert _report_threads(tmp_path / "in-a") == 1
    assert _report_threads(tmp_path / "in-b") == 3
    for kind in FILES:
        a = (tmp_path / f"in-a-{kind}.fits").read_bytes()
        assert a == (tmp_path / f"j1-{kind}.fits").read_bytes(), kind


def interrupt(argv, timeout=120):
    """Start `argv`, wait for its first line on stdout, interrupt it as
    Ctrl-C does (SIGINT; CTRL_BREAK to its own process group on Windows)
    and return (exit status, seconds from the signal to the exit)."""
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    p = subprocess.Popen(
        [str(a) for a in argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw
    )
    try:
        first = p.stdout.readline()
        assert first, p.stderr.read()
        time.sleep(0.5)
        assert p.poll() is None, "finished before the signal"
        sent = time.perf_counter()
        if os.name == "nt":
            os.kill(p.pid, signal.CTRL_BREAK_EVENT)
        else:
            p.send_signal(signal.SIGINT)
        rc = p.wait(timeout=timeout)
        return rc, time.perf_counter() - sent
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        p.stdout.close()
        p.stderr.close()


# Long enough to be interrupted: a noise-free source never meets threshold 0.
LONG = [
    "-size", "1024", "1024", "-scale", "1asec", "-weight", "natural",
    "-niter", "100000000", "-gain", "0.01", "-nmiter", "1000", "-abs-threshold", "0",
    "-data-column", "DATA", "-field", "0", "-no-update-model-required", "-j", "2",
]  # fmt: skip

# The binary's status after Ctrl-C: killed by SIGINT, or Windows'
# STATUS_CONTROL_C_EXIT from the default console handler.
INTERRUPTED = 0xC000013A if os.name == "nt" else -signal.SIGINT


def test_ctrl_c_ends_the_run_at_once(tmp_path):
    ms = tiny_ms(tmp_path / "x.ms")
    rc, seconds = interrupt([script(), "-name", tmp_path / "c", *LONG, ms])
    assert rc == INTERRUPTED, rc
    assert seconds < 10, seconds
    rc, seconds = interrupt(
        [sys.executable, "-m", "rang.gemclean", "-name", tmp_path / "m", *LONG, ms]
    )
    assert rc == INTERRUPTED, rc
    assert seconds < 10, seconds


def test_rang_core_runs_the_extension(tmp_path):
    found = pipe.find_gemclean("auto")
    assert found.argv == [sys.executable, "-m", "rang.gemclean"]
    assert found.path == core.library_path() and hasattr(_core, "gemclean_main")
    ms = tiny_ms(tmp_path / "x.ms")
    log = tmp_path / "gemclean.log"
    seconds = pipe.run_gemclean(
        found, [*found.argv, "-name", str(tmp_path / "r"), *SMALL, str(ms)], log
    )
    assert seconds > 0 and (tmp_path / "r-image.fits").is_file()
    text = log.read_text(encoding="utf-8")
    assert text.startswith(sys.executable) and "wall" in text.splitlines()[-1]


def test_the_wheel_holds_no_gemclean_executable():
    package = Path(_core.__file__).resolve().parent
    names = sorted(p.name for p in package.iterdir() if "gemclean" in p.name.lower())
    assert names == ["gemclean.py"], names
