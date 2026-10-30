"""The wgpu gridder of big-plan task X2 (research/x2-wgpu.md): device
selection, the clean failure without the feature or an adapter, and, where a
GPU is usable, agreement with the CPU path. The GPU tests skip (never fail)
on hosts without the feature or without an adapter, such as WSL."""

import math

import numpy as np
import pytest
from rang import core_grid

C_LIGHT = 299792458.0


def _point_source(nrow=150, nchan=3, seed=11):
    rng = np.random.default_rng(seed)
    angle = rng.uniform(0, 2 * math.pi, nrow)
    radius = rng.uniform(20.0, 400.0, nrow)
    uvw = np.stack(
        [radius * np.cos(angle), radius * np.sin(angle), rng.uniform(-30, 30, nrow)],
        axis=1,
    )
    frequencies = np.array([1.0e9, 1.2e9, 1.4e9])[:nchan]
    l, m = 4 * 30 * core_grid.ARCSEC, -3 * 30 * core_grid.ARCSEC
    n = math.sqrt(1 - l * l - m * m)
    lam = C_LIGHT / frequencies
    phase = (
        2
        * math.pi
        * (uvw[:, 0:1] * l + uvw[:, 1:2] * m + uvw[:, 2:3] * (n - 1))
        / lam[None, :]
    )
    data = np.exp(1j * phase).astype(np.complex64)
    weights = rng.uniform(0.5, 1.5, (nrow, nchan)).astype(np.float32)
    weights[rng.random((nrow, nchan)) < 0.1] = 0
    imaging = rng.uniform(0.2, 2.0, (nrow, nchan)).astype(np.float32)
    settings = {"width": 64, "height": 60, "scale_arcsec": 30.0, "w_layers": 12}
    return (uvw, frequencies, data, weights, imaging), settings


def test_device_and_precision_resolution(monkeypatch):
    monkeypatch.delenv(core_grid.DEVICE_ENV, raising=False)
    monkeypatch.delenv(core_grid.PRECISION_ENV, raising=False)
    assert core_grid.resolve_device() == "cpu"
    assert core_grid.resolve_precision() == "f64"
    monkeypatch.setenv(core_grid.DEVICE_ENV, "GPU")
    monkeypatch.setenv(core_grid.PRECISION_ENV, "f32")
    assert core_grid.resolve_device() == "gpu"
    assert core_grid.resolve_precision() == "f32"
    assert core_grid.resolve_device("cpu") == "cpu"
    monkeypatch.setenv(core_grid.DEVICE_ENV, "cuda")
    with pytest.raises(ValueError, match="RANG_GRIDDER_DEVICE"):
        core_grid.resolve_device()
    with pytest.raises(ValueError, match="RANG_GRIDDER_GPU_PRECISION"):
        core_grid.resolve_precision("f16")


def test_cpu_default_ignores_the_gpu(monkeypatch):
    args, settings = _point_source()
    monkeypatch.delenv(core_grid.DEVICE_ENV, raising=False)
    default = core_grid.invert(*args, **settings)
    monkeypatch.setenv(core_grid.DEVICE_ENV, "cpu")
    explicit = core_grid.invert(*args, **settings)
    assert "gpu" not in default
    assert np.array_equal(default["dirty"], explicit["dirty"])
    assert np.array_equal(default["psf"], explicit["psf"])


def test_gpu_request_fails_cleanly_without_feature_or_adapter():
    available, reason = core_grid.gpu_available()
    if available:
        pytest.skip(f"a GPU is usable here ({reason})")
    args, settings = _point_source()
    with pytest.raises(RuntimeError):
        core_grid.invert(*args, **settings, device="gpu")
    assert reason


@pytest.mark.parametrize(("precision", "tolerance"), [("f64", 1e-12), ("f32", 1e-4)])
def test_gpu_matches_cpu(precision, tolerance):
    available, reason = core_grid.gpu_available()
    if not available:
        pytest.skip(f"no GPU gridder: {reason}")
    if precision == "f64" and "SHADER_F64 yes" not in reason:
        pytest.skip(f"adapter without f64: {reason}")
    args, settings = _point_source()
    cpu = core_grid.invert(*args, **settings, device="cpu")
    gpu = core_grid.invert(*args, **settings, device="gpu", precision=precision)
    norm = "psf_normalization"
    assert abs(gpu["stats"][norm] / cpu["stats"][norm] - 1) <= tolerance
    assert {k: v for k, v in gpu["stats"].items() if k != norm} == {
        k: v for k, v in cpu["stats"].items() if k != norm
    }
    assert gpu["gpu"]["precision"] == precision
    for kind in ("dirty", "psf"):
        peak = np.abs(cpu[kind]).max()
        assert np.abs(gpu[kind] - cpu[kind]).max() <= tolerance * peak
    again = core_grid.invert(*args, **settings, device="gpu", precision=precision)
    assert np.array_equal(again["dirty"], gpu["dirty"])
    assert again["gpu"]["context_s"] == 0.0
    assert again["gpu"]["compile_s"] == 0.0
