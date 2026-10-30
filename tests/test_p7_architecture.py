"""Task P7 (research/p7-architecture.md): one entry door, no cargo at run
time, the GIL released, no abort on a kernel panic, the parallel Tricolour
pack/unpack and the copy-free solver flags."""

import importlib
import os
import pkgutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import rangtoy
from rangtoy import core, core_flag
from test_core_backends import flag_case, solve, solve_case

ROOT = Path(__file__).resolve().parents[1]

NO_CARGO = r"""
import importlib, pkgutil, sys
import numpy as np
import rangtoy
skipped = []
for info in pkgutil.iter_modules(rangtoy.__path__, "rangtoy."):
    try:
        importlib.import_module(info.name)
    except ModuleNotFoundError as exc:  # an optional third-party extra
        if exc.name and exc.name.split(".")[0] != "rangtoy":
            skipped.append(info.name)
        else:
            raise
from rangtoy import flagging, flagging_influence, flagging_trend, projector, toy_output
g = np.tile(np.eye(2, dtype=complex), (3, 2, 2, 1, 1))
v = np.ones((3, 2, 2), bool)
flagging.gain_tv(g, v, np.arange(3.0), np.arange(2.0))
flagging_trend.estimate_trend(g, v, np.arange(3.0), np.arange(2.0), v)
flagging_influence.jones_jacobian(np.eye(2), np.eye(2), np.eye(2))
projector.project_out(np.ones((4, 1)), np.arange(8.0).reshape(4, 2))
toy_output("--pointing-reference")
print("ok", len(skipped))
"""


def test_no_cargo_at_import_or_kernel_call(tmp_path):
    """Criterion 2: a poisoned `cargo` first on PATH is never run."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "cargo-was-run"
    if os.name == "nt":
        (bin_dir / "cargo.bat").write_text(f'@echo ran > "{marker}"\r\n@exit /b 1\r\n')
    else:
        script = bin_dir / "cargo"
        script.write_text(f'#!/bin/sh\necho ran > "{marker}"\nexit 1\n')
        script.chmod(0o755)
    env = {
        **os.environ,
        "PATH": os.pathsep.join([str(bin_dir), str(Path(sys.executable).parent)]),
    }
    env.pop("RANG_CORE_LIB", None)
    env.pop("RANG_CORE_BACKEND", None)
    result = subprocess.run(
        [sys.executable, "-c", NO_CARGO],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("ok")
    assert not marker.exists(), "cargo was run"


def test_every_module_imports_without_build():
    for info in pkgutil.iter_modules(rangtoy.__path__, "rangtoy."):
        try:
            importlib.import_module(info.name)
        except ModuleNotFoundError as exc:
            assert exc.name and not exc.name.startswith("rangtoy"), exc
    assert not hasattr(rangtoy, "build")


def test_ctypes_backend_requests_are_refused(monkeypatch):
    for name, value in (("RANG_CORE_BACKEND", "ctypes"), ("RANG_CORE_LIB", "x.so")):
        monkeypatch.setenv(name, value)
        core.reset_backend()
        with pytest.raises(ValueError, match="p7-architecture"):
            core.extension()
        monkeypatch.delenv(name)
    core.reset_backend()
    assert core.backend_name() == "extension"
    assert core.library() is core.extension()
    assert core.library_path().name.startswith("_core")


def test_kernel_panic_returns_status_not_abort():
    """Criterion 4: `grid_kernel(7, 2)` aborted the process before P7."""
    code = (
        "import numpy as np\n"
        "from rangtoy import _core\n"
        "print(_core.grid_kernel(7, 2, np.zeros(14)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["2"]


def _long_solve():
    rng = np.random.default_rng(5)
    nant, ntime, nchan = 16, 40, 64
    pairs = [(a, b) for a in range(nant) for b in range(a + 1, nant)]
    p = np.tile([a for a, _ in pairs], ntime).astype(np.uint32)
    q = np.tile([b for _, b in pairs], ntime).astype(np.uint32)
    shape = (len(p), nchan, 4)
    model = (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)).astype(
        np.complex64
    )
    data = (model * 1.05).astype(np.complex64)
    return lambda: core.solve_complex(
        data,
        np.ones(shape, np.float32),
        np.zeros(shape, bool),
        np.zeros(len(p), bool),
        p,
        q,
        np.repeat(np.arange(ntime) // 4, len(pairs)).astype(np.uint32),
        np.zeros(nchan, np.uint32),
        ntime_bins=ntime // 4,
        nfreq_bins=1,
        nant=nant,
        model=model,
    )


def test_gil_is_released_during_a_kernel():
    """Criterion 3: another Python thread runs while the solver runs."""
    run = _long_solve()
    window = {}
    started = threading.Event()

    def kernel():
        started.set()
        window["start"] = time.perf_counter()
        run()
        window["end"] = time.perf_counter()

    worker = threading.Thread(target=kernel)
    ticks = []
    worker.start()
    started.wait()
    while worker.is_alive():
        ticks.append(time.perf_counter())
    worker.join()
    inside = [t for t in ticks if window["start"] < t < window["end"]]
    assert window["end"] - window["start"] > 0.01, "case too small to tell"
    # With the GIL held for the whole call this loop could not run at all.
    assert len(inside) > 100, (len(inside), window)


def test_solve_flags_reach_the_kernel_without_a_copy(monkeypatch):
    """Criterion 7: bool and uint8 flags are passed in place; same gains."""
    data, model, weights, p, q, tb, fb, flags, rows = solve_case()
    ext = core.extension()
    seen = []

    class Recorder:
        def __getattr__(self, name):
            return getattr(ext, name)

        def solve_complex(self, *args):
            seen.append(args[9].ctypes.data)
            return ext.solve_complex(*args)

    monkeypatch.setattr(core, "extension", lambda: Recorder())
    as_bool = solve(data, model, weights, p, q, tb, fb, flags, rows)
    as_uint8 = flags.astype(np.uint8)
    as_u8 = solve(data, model, weights, p, q, tb, fb, as_uint8, rows)
    twos = as_uint8 * 2  # nonzero means flagged, as np.asarray(flag, bool) did
    as_twos = solve(data, model, weights, p, q, tb, fb, twos, rows)
    assert seen == [flags.ctypes.data, as_uint8.ctypes.data, twos.ctypes.data]
    for other in (as_u8, as_twos):
        assert other[0].tobytes() == as_bool[0].tobytes()
        assert other[1].tobytes() == as_bool[1].tobytes()
        assert other[2:] == as_bool[2:]


def test_flag_pack_keeps_the_last_duplicate_row():
    """Criterion 6: parallel pack keeps the serial rule (later rows win)."""
    args = list(flag_case())
    data, _, a1, a2, times = args[:5]
    # Row 4 repeats (baseline, time) of row 1 with other data: it must win.
    dup = 4
    a1[dup], a2[dup], times[dup] = a1[1], a2[1], times[1]
    data[dup] = data[dup] * 3.0
    result = core_flag.flag_rows(*args, masks=[np.array([1.0e9 + 3.0e6])])
    keep = np.ones(len(times), bool)
    keep[1] = False
    reduced = list(flag_case())
    for i in range(5):
        reduced[i] = args[i][keep]
    expected = core_flag.flag_rows(*reduced, masks=[np.array([1.0e9 + 3.0e6])])
    assert result["intensity"].tobytes() == expected["intensity"].tobytes()
    assert result["flags"][keep].tobytes() == expected["flags"].tobytes()
    assert result["flags"][1].tobytes() == result["flags"][dup].tobytes()
