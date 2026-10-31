"""Task W4-3: the closure scores and the flux-standard evaluator run in the
extension; no call builds anything (research/w4-3-kernels.md)."""

import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest
from rang import core, core_closure, core_wgridder, fluxstd

TARGET = Path(__file__).resolve().parents[1] / "core" / "target"


def closure_case(nant=8, nchan=3, seed=4):
    """Every baseline of `nant` antennas at one time; data near the model."""
    rng = np.random.default_rng(seed)
    a1, a2 = np.triu_indices(nant, 1)
    nrow = len(a1)
    model = np.zeros((nrow, nchan, 4), np.complex64)
    model[..., 0] = model[..., 3] = 10.0
    noise = rng.normal(size=(nrow, nchan, 4)) + 1j * rng.normal(size=(nrow, nchan, 4))
    data = (model + 0.05 * noise).astype(np.complex64)
    return {
        "data": data,
        "model": model,
        "weights": np.ones((nrow, nchan, 4), np.float32),
        "usable": np.ones((nrow, nchan), np.uint8),
        "antenna1": a1.astype(np.uint32),
        "antenna2": a2.astype(np.uint32),
        "time_index": np.zeros(nrow, np.uint32),
        "stations": np.arange(nant, dtype=np.uint32),
    }


def raw_closure(c, **override):
    """Call the binding directly, with arrays the test may replace."""
    a = dict(c, **override)
    nrow, nchan = a["usable"].shape
    out = {
        "residual": np.empty((nrow, nchan), np.float32),
        "tv": np.empty((nrow, nchan), np.float32),
        "count": np.empty((nrow, nchan), np.uint16),
    }
    out.update({k: v for k, v in override.items() if k in out})
    core.extension().closure_scores(
        a["data"], a["model"], a["weights"], a["usable"], a["antenna1"],
        a["antenna2"], a["time_index"], a["stations"], len(c["stations"]), 1, 0, 5, 3,
        out["residual"], out["tv"], out["count"],
    )  # fmt: skip
    return out


@pytest.fixture
def no_subprocess(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("no subprocess (cargo) may run at a kernel call")

    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)


def test_kernels_run_in_the_extension_without_a_build(no_subprocess):
    before = sorted(TARGET.glob("*-standalone"))
    c = closure_case()
    out = core_closure.scores(
        c["data"], c["model"], c["weights"], c["usable"], c["antenna1"],
        c["antenna2"], c["time_index"], c["stations"], "trace",
    )  # fmt: skip
    assert np.isfinite(out["residual"]).all() and out["count"].min() == 6
    coeffs, nu = (1.2481, -0.4507, -0.1798, 0.0357), np.geomspace(0.5e9, 20e9, 41)
    rs = fluxstd.core_log10_poly(coeffs, 1e9, nu)
    assert np.max(np.abs(rs / fluxstd.log10_poly(coeffs, 1e9, nu) - 1)) < 1e-13
    assert core_wgridder.kernel_row(0) is not None
    assert core_closure.library() is core.extension()
    assert fluxstd.rust_library() is core.extension()
    assert core_closure.library_path() == core.library_path()
    for module, names in (
        (core_closure, ("build_standalone", "write_standalone", "standalone_dir")),
        (fluxstd, ("build_standalone", "write_standalone", "standalone_dir")),
        (core_wgridder, ("build_standalone", "write_standalone", "standalone_dir")),
    ):
        for name in names:
            assert not hasattr(module, name), (module.__name__, name)
    assert sorted(TARGET.glob("*-standalone")) == before


def test_closure_binding_refuses_bad_buffers():
    c = closure_case()
    raw_closure(c)  # the unmodified case passes
    with pytest.raises(TypeError):
        raw_closure(c, data=c["data"].astype(np.complex128))
    with pytest.raises(TypeError):
        raw_closure(c, antenna1=c["antenna1"].astype(np.int64))
    with pytest.raises(ValueError, match="C-contiguous"):
        raw_closure(c, weights=np.asfortranarray(c["weights"]))
    with pytest.raises(ValueError, match="C-contiguous"):
        raw_closure(c, data=np.concatenate([c["data"], c["data"]], axis=1)[:, ::2])
    with pytest.raises(ValueError, match="antenna1 must have shape"):
        raw_closure(c, antenna1=c["antenna1"][:-1])
    with pytest.raises(ValueError, match="time_index must have shape"):
        raw_closure(c, time_index=c["time_index"][:-1])
    with pytest.raises(ValueError, match="model must have shape"):
        raw_closure(c, model=c["model"][:, :1].copy())
    with pytest.raises(ValueError, match="count must have shape"):
        raw_closure(c, count=np.empty((1, 1), np.uint16))
    with pytest.raises(ValueError, match=r"data must be \(row, chan, 4\)"):
        raw_closure(c, data=c["data"][..., :2].copy())
    with pytest.raises(
        ValueError, match=r"closure kernel failed \(1\): .*not in the cycle"
    ):
        raw_closure(c, stations=c["stations"][:-1].copy())


def test_fluxstd_binding_refuses_bad_buffers():
    ext = core.extension()
    coeffs = np.array([1.0, -0.5])
    freq = np.array([1.0e9, 2.0e9, 4.0e9])
    out = np.empty(3)
    ext.fluxstd_eval(coeffs, 1e9, freq, out)
    assert np.max(np.abs(out / fluxstd.log10_poly((1.0, -0.5), 1e9, freq) - 1)) < 1e-13
    with pytest.raises(ValueError, match="out must have shape"):
        ext.fluxstd_eval(coeffs, 1e9, freq, np.empty(2))
    with pytest.raises(ValueError, match="C-contiguous"):
        ext.fluxstd_eval(coeffs, 1e9, np.repeat(freq, 2)[::2], out)
    with pytest.raises(ValueError, match="freq must have shape"):
        ext.fluxstd_eval(coeffs, 1e9, freq.reshape(3, 1), out)
    with pytest.raises(TypeError):
        ext.fluxstd_eval(coeffs, 1e9, freq.astype(np.float32), out)
    with pytest.raises(ValueError, match="rejected its input"):
        ext.fluxstd_eval(np.empty(0), 1e9, freq, out)
    with pytest.raises(ValueError, match="rejected its input"):
        fluxstd.core_log10_poly((1.0,), 1e9, [-1.0])
    readonly = np.empty(3)
    readonly.flags.writeable = False
    with pytest.raises(Exception):  # noqa: B017 (numpy's borrow error type)
        ext.fluxstd_eval(coeffs, 1e9, freq, readonly)


def test_closure_kernel_runs_in_threads():
    """Two threads run the kernel concurrently; both equal the serial result."""
    c = closure_case(nant=12, nchan=16)
    serial = raw_closure(c)
    results = [None, None]

    def work(k):
        results[k] = raw_closure(c)

    threads = [threading.Thread(target=work, args=(k,)) for k in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for r in results:
        for key in serial:
            assert r[key].tobytes() == serial[key].tobytes()
