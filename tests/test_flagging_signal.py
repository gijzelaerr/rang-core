"""Numerical and namespace safeguards for paired faint-sky template response."""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from rangtoy.flagging_signal import (
    ARCMIN,
    REFERENCE_HZ,
    SOURCES,
    corrected_intensity,
    fit_signal,
    intrinsic_signal,
    run,
    select_policy,
    spatial_templates,
)


def test_frozen_sources_and_reference_frequency():
    assert REFERENCE_HZ == 1283791015.625
    assert [
        (
            s["flux_jy"],
            s["l_arcmin"],
            s["m_arcmin"],
            s["fwhm_arcmin"],
            s["spectral_index"],
        )
        for s in SOURCES
    ] == [
        (0.05, 12.0, 8.0, 0.0, -0.7),
        (0.1, -15.0, 10.0, 10.0, -1.0),
    ]


def test_gaussian_integrated_flux_and_casa_w_phase_independent_formula():
    frequencies = np.array([1e9, REFERENCE_HZ, 1.5e9])
    uvw = np.array([[0, 0, 0], [40, 30, 20]])
    templates = spatial_templates(uvw, frequencies)
    np.testing.assert_array_equal(templates[:, 0], np.ones((2, 3)))
    for i, source in enumerate(SOURCES):
        l, m, theta = (
            np.array([source["l_arcmin"], source["m_arcmin"], source["fwhm_arcmin"]])
            * ARCMIN
        )
        n_minus_one = np.sqrt(1 - l * l - m * m) - 1
        phase = np.exp(
            2j * np.pi / 299792458 * (40 * l + 30 * m + 20 * n_minus_one) * frequencies
        )
        shape = np.exp(
            -((np.pi * theta * frequencies / 299792458) ** 2)
            * (40**2 + 30**2)
            / (4 * np.log(2))
        )
        np.testing.assert_allclose(templates[i, 1], phase * shape, atol=1e-14)
    signal = intrinsic_signal(templates, frequencies)
    assert signal[0, 1].real == pytest.approx(0.15)
    assert signal[0, 1].imag == 0
    assert abs(templates[1, 1, 2]) < abs(templates[1, 1, 0])


def test_full_jones_inverse_and_weight_propagation_match_basis_response():
    rng = np.random.default_rng(91)
    gp = np.broadcast_to(np.eye(2), (2, 3, 2, 2)).astype(complex).copy()
    gp += 0.15 * (rng.normal(size=gp.shape) + 1j * rng.normal(size=gp.shape))
    gq = gp[::-1].copy() * (1 + 0.2j)
    coherency = rng.normal(size=gp.shape) + 1j * rng.normal(size=gp.shape)
    observed = (gp @ coherency @ gq.conj().swapaxes(-1, -2)).reshape(2, 3, 4)
    native_weights = np.broadcast_to([1, 2, 3, 4], observed.shape)
    intensity, variance, good = corrected_intensity(
        observed, gp, gq, np.ones((2, 3), bool), native_weights
    )
    np.testing.assert_allclose(
        intensity, np.trace(coherency, axis1=-2, axis2=-1) / 2, atol=1e-14
    )
    assert good.all()
    expected = np.zeros((2, 3))
    for corr in range(4):
        basis = np.zeros((2, 2), complex)
        basis.flat[corr] = 1
        coefficient = (
            np.trace(
                np.linalg.inv(gp) @ basis @ np.linalg.inv(gq).conj().swapaxes(-1, -2),
                axis1=-2,
                axis2=-1,
            )
            / 2
        )
        expected += np.abs(coefficient) ** 2 / native_weights[..., corr]
    np.testing.assert_allclose(variance, expected, atol=1e-14)
    # Common right-unitary full-Jones gauge changes do not change trace response.
    unitary = np.linalg.qr(rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2)))[0]
    rotated, rotated_variance, rotated_good = corrected_intensity(
        observed, gp @ unitary, gq @ unitary, good, native_weights
    )
    np.testing.assert_allclose(rotated, intensity, atol=1e-14)
    np.testing.assert_allclose(rotated_variance, variance, atol=1e-14)
    assert rotated_good.all()


def test_singular_or_unsupported_jones_are_unavailable_not_silently_inverted():
    gains = np.broadcast_to(np.eye(2), (2, 3, 2, 2)).astype(complex).copy()
    gains[0, 0] = 0
    mask = np.ones((2, 3), bool)
    mask[1, 1] = False
    intensity, variance, good = corrected_intensity(
        np.ones((2, 3, 4), complex), gains, gains, mask, np.ones((2, 3, 4))
    )
    assert not good[0, 0] and not good[1, 1]
    assert np.isnan(intensity[0, 0]) and np.isnan(variance[1, 1])
    assert good[0, 1]


def fit_fixture():
    rng = np.random.default_rng(47)
    uvw = rng.normal(size=(12, 3)) * 40
    frequencies = np.linspace(1.05e9, 1.5e9, 20)
    templates = spatial_templates(uvw, frequencies)
    mask = np.ones((12, 20), bool)
    return frequencies, templates, mask


def test_joint_flux_and_spectral_indices_recovered_for_exact_injected_family():
    frequencies, templates, mask = fit_fixture()
    sky = intrinsic_signal(templates, frequencies)
    result = fit_signal(sky, templates, frequencies, np.ones(mask.shape), mask)
    assert result["available"] and result["rank"] == 4
    for record, source in zip(result["sources"], SOURCES):
        assert record["recovered_flux_jy"] == pytest.approx(
            source["flux_jy"], abs=1e-10
        )
        assert record["recovered_spectral_index"] == pytest.approx(
            source["spectral_index"], abs=1e-9
        )


def test_nonpositive_response_is_measured_not_removed_from_flux_fit():
    frequencies, templates, mask = fit_fixture()
    result = fit_signal(
        -intrinsic_signal(templates, frequencies),
        templates,
        frequencies,
        np.ones(mask.shape),
        mask,
    )
    assert result["available"]
    assert all(record["recovered_flux_jy"] < 0 for record in result["sources"])
    assert result["sample_count"] == mask.sum()


def test_unidentifiable_templates_and_invalid_samples_do_not_invent_response():
    frequencies, templates, mask = fit_fixture()
    identical_sources = (SOURCES[0], {**SOURCES[0], "name": "same", "flux_jy": 0.1})
    duplicate = np.stack((templates[0], templates[0]))
    result = fit_signal(
        intrinsic_signal(duplicate, frequencies, identical_sources),
        duplicate,
        frequencies,
        np.ones(mask.shape),
        mask,
        identical_sources,
    )
    assert not result["available"] and result["rank"] < 4
    assert all(record["recovered_flux_jy"] is None for record in result["sources"])
    bad = intrinsic_signal(templates, frequencies)
    bad[0, 0] = np.nan
    with pytest.raises(ValueError, match="silently"):
        fit_signal(bad, templates, frequencies, np.ones(mask.shape), mask)


def test_source_truth_and_test_loss_never_choose_policy():
    records = [
        {
            "mask_id": "zero",
            "families": ["residual", "tv"],
            "guard_pass": True,
            "objective": 1.25,
            "added_count": 0,
            "test_loss": 0,
            "true_flux": 100,
        },
        {
            "mask_id": "best",
            "families": ["tv"],
            "guard_pass": True,
            "objective": 1.24,
            "added_count": 2,
            "test_loss": 1000,
            "true_flux": 0,
        },
        {
            "mask_id": "invalid",
            "families": ["tv"],
            "guard_pass": False,
            "objective": 0.1,
            "added_count": 1,
        },
    ]
    assert select_policy(records, "tv") == "best"
    assert select_policy(records, "residual") == "zero"
    records[0]["test_loss"], records[1]["test_loss"] = 10000, -10000
    assert select_policy(records, "tv") == "best"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"iterations": 0},
        {"iterations": True},
        {"max_fraction": 0.021},
        {"max_fraction": np.nan},
    ],
)
def test_invalid_run_settings_do_not_create_output(tmp_path, kwargs):
    output, source = tmp_path / "new", tmp_path / "prepared"
    with pytest.raises(ValueError):
        run(output, source, **kwargs)
    assert not output.exists()


@pytest.mark.parametrize("case", ["nested", "existing_logs", "ancestor", "override"])
def test_signal_wrapper_invalid_namespaces_stop_before_cache_logs_or_docker(
    tmp_path, case
):
    repo = Path(__file__).resolve().parents[1]
    tools = tmp_path / "tools/flagging"
    tools.mkdir(parents=True)
    for name in ("run-signal.sh", "preflight.py"):
        shutil.copy2(repo / "tools/flagging" / name, tools / name)
    source = tmp_path / "outputs/prepared"
    source.mkdir(parents=True)
    protected = source / "protected.dat"
    protected.write_bytes(b"never modify source")
    run_dir, prepared, extra = "outputs/prepared/new", "outputs/prepared", []
    if case == "existing_logs":
        run_dir = "outputs/new"
        (tmp_path / "outputs/new-logs").symlink_to(tmp_path / "outputs/missing")
    elif case == "ancestor":
        run_dir, prepared = "outputs/ancestor", "outputs/ancestor/child"
        (tmp_path / prepared).mkdir(parents=True)
    elif case == "override":
        run_dir, extra = "outputs/new", ["run-dir=/workspace/outputs/prepared/new"]
    completed = subprocess.run(
        ["bash", str(tools / "run-signal.sh"), run_dir, prepared, *extra],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert protected.read_bytes() == b"never modify source"
    assert not list((tmp_path / "outputs").glob("*numba-cache"))
    if case != "ancestor":
        assert not (tmp_path / run_dir).exists()
    else:
        assert list((tmp_path / run_dir).iterdir()) == [tmp_path / prepared]
    assert list(source.iterdir()) == [protected]
