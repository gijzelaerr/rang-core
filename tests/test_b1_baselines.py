"""B1-1 (i): the port of the SARAO/SKA Gaussian pointing-offset fit.

Unit tests are synthetic; the reproduction test runs the five-scan fixture
when `outputs/ska-pointing/outer_scans.zip` is present
(research/b1-beam-pointing.md, gate G1a)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "outputs" / "ska-pointing" / "outer_scans.zip"


@pytest.fixture(scope="module")
def b1():
    spec = importlib.util.spec_from_file_location(
        "b1_baselines", ROOT / "examples" / "b1_baselines.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chunks_drop_the_band_edges(b1):
    chunks = b1.split_chunks(4096)
    assert len(chunks) == 14
    assert chunks[0][0] == 256 and chunks[-1][-1] == 3839
    assert all(len(c) == 256 for c in chunks)


def test_weighted_average_and_std(b1):
    data = np.array([1.0, 2.0, 4.0])
    weights = np.array([1.0, 2.0, 1.0])
    mean, std = b1.weighted_avg_and_std(data, 0, weights)
    expected = np.average(data, weights=weights)
    v1, v2 = weights.sum(), (weights**2).sum()
    variance = np.sum(weights * (data - expected) ** 2) / (v1 - v2 / v1)
    assert float(mean) == pytest.approx(expected)
    assert float(std) == pytest.approx(np.sqrt(variance))
    _, err = b1.weighted_avg_and_std(data, 0, weights, std_error=True)
    assert float(err) == pytest.approx(np.sqrt(variance * v2) / v1)


def test_gain_solve_recovers_amplitudes(b1):
    rng = np.random.default_rng(5)
    nants, nchan = 4, 8
    gains = rng.uniform(1.5, 3.5, (nants, 2)) * np.exp(
        1j * rng.uniform(-1, 1, (nants, 2))
    )
    baselines = [(i, j) for i in range(nants) for j in range(i, nants)]
    vis = np.zeros((1, len(baselines), nchan, 4), complex)
    for b, (i, j) in enumerate(baselines):
        vis[0, b, :, 0] = gains[i, 0] * np.conj(gains[j, 0])
        vis[0, b, :, 3] = gains[i, 1] * np.conj(gains[j, 1])
        vis[0, b, :, 1:3] = 0.05
    scan = {
        "nants": nants,
        "baselines": baselines,
        "vis": vis,
        "weight": np.ones(vis.shape),
        "flags": np.zeros(vis.shape, int),
    }
    solved, weight = b1.solve_gains(scan, np.arange(nchan))
    np.testing.assert_allclose(
        np.abs(solved[0, :, 0, 0, 0]), np.abs(gains[:, 0]), rtol=1e-5
    )
    np.testing.assert_allclose(
        np.abs(solved[0, :, 0, 1, 1]), np.abs(gains[:, 1]), rtol=1e-5
    )
    assert np.all(solved[0, :, 0, 0, 1] == 0)
    assert np.angle(solved[0, 0, 0, 0, 0]) == pytest.approx(0.0, abs=1e-12)
    assert np.all(weight[0, :, 0, 0, 0] > 0)


def test_gaussian_fit_recovers_centre_and_width(b1):
    expected = b1.expected_voltage_width(1.3e9)
    centre = np.array([0.03, -0.05])
    x = np.array([[0, -1], [0, 1], [-1, 0], [1, 0], [0, 0]], float).T
    sigma = expected * 1.05 / b1.FWHM_PER_SIGMA
    y = 3.0 * np.exp(
        -0.5 * np.sum(((x - centre[:, None]) / sigma[:, None]) ** 2, axis=0)
    )
    fit = b1.beam_pattern_fit(x, y, np.full(5, 0.01), expected)
    np.testing.assert_allclose(fit["centre"], centre, atol=1e-9)
    np.testing.assert_allclose(fit["width"], expected * 1.05, rtol=1e-9)
    assert fit["height"] == pytest.approx(3.0)
    assert fit["valid"]
    wide = b1.beam_pattern_fit(
        x,
        3.0 * np.exp(-0.5 * np.sum((x / (2 * sigma[:, None])) ** 2, axis=0)),
        np.full(5, 0.01),
        expected,
    )
    assert not wide["valid"]


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture outer_scans.zip not present")
def test_fixture_reproduces_reference_offsets(b1, tmp_path):
    scans, reference, _ = b1.load_fixture(FIXTURE, tmp_path)
    result = b1.run_baseline(scans)
    expected = reference[:, 1:].astype(float)
    assert [str(n) for n in reference[:, 0]] == ["m000", "m001", "m002", "m003"]
    np.testing.assert_array_almost_equal(result["rows"], expected, decimal=6)
