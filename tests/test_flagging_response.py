"""Frozen response controls, unrestricted real fits and checked storage guards."""

from types import SimpleNamespace

import numpy as np
import pytest
from rangtoy import flagging_response as response
from rangtoy.flagging_signal import spatial_templates


def family():
    rng = np.random.default_rng(241)
    frequencies = np.linspace(1.05e9, 1.5e9, 24)
    spatial = spatial_templates(
        rng.normal(size=(20, 3)) * 60, frequencies, response.SOURCES
    )
    templates = (
        spatial
        * np.asarray(
            [
                (frequencies / response.REFERENCE_HZ) ** source["spectral_index"]
                for source in response.SOURCES
            ]
        )[:, None]
    )
    return templates, np.ones(templates.shape[1:]), np.ones(templates.shape[1:], bool)


def test_response_protocol_is_new_separate_and_small():
    assert response.GRIDS == ((2, 32), (14, 128))
    assert response.SIGNS == (("positive", 1), ("negative", -1))
    assert response.SKIES == ("omitted", "complete-diagnostic")
    assert response.CONTROL_COLUMN == "RANG_RESPONSE_MODEL"
    assert response.ALLOCATION_BYTES == 1610612736
    assert response.SOLVE_RESERVATION_BYTES == 80 * 1024**2
    assert [
        (
            s["flux_jy"],
            s["l_arcmin"],
            s["m_arcmin"],
            s["fwhm_arcmin"],
            s["spectral_index"],
        )
        for s in response.SOURCES
    ] == [(0.06, 9, -6, 0, -0.5), (0.12, -12, -14, 8, -0.9)]


@pytest.mark.parametrize(
    "flux", ([0.06, 0.12], [-0.06, -0.12], [-0.1, 0.0], [0.0, 0.0])
)
def test_linear_real_fluxes_have_no_positivity_or_spectral_bounds(flux):
    templates, weights, mask = family()
    intensity = np.sum(np.asarray(flux)[:, None, None] * templates, axis=0)
    fitted = response.linear_response(intensity, templates, weights, mask)
    assert fitted["available"] and fitted["rank"] == 2
    np.testing.assert_allclose(fitted["flux_jy"], flux, atol=1e-14)
    assert not fitted["positivity_or_parameter_bounds"]
    assert fitted["sample_count"] == mask.sum()
    assert fitted["weighted_mse_proxy"] < 1e-28
    assert "not fitted" in fitted["spectral_indices"]


def test_response_decomposition_is_linear_at_fixed_support_and_weights():
    templates, weights, mask = family()
    rng = np.random.default_rng(247)
    weights *= np.linspace(1, 3, weights.shape[-1])
    direct = np.sum(np.array([0.059, 0.119])[:, None, None] * templates, axis=0)
    adaptation = np.sum(np.array([-0.052, -0.108])[:, None, None] * templates, axis=0)
    adaptation += 0.01 * (
        rng.normal(size=mask.shape) + 1j * rng.normal(size=mask.shape)
    )
    fits = [
        response.linear_response(term, templates, weights, mask)
        for term in (direct + adaptation, direct, adaptation)
    ]
    np.testing.assert_allclose(
        fits[0]["flux_jy"],
        np.array(fits[1]["flux_jy"]) + fits[2]["flux_jy"],
        atol=1e-14,
    )
    assert all(f["sample_count"] == mask.sum() for f in fits)
    assert fits[0]["unexplained_weighted_response_energy_fraction"] > 0


def test_full_jones_correction_decomposition_can_show_exact_gain_cancellation():
    # A fitted gain can absorb an omitted signal even though direct inverse-gain
    # correction retains it. No noise/sign samples are removed from evaluation.
    count = 6
    identity = np.broadcast_to(np.eye(2), (count, 2, 2)).astype(complex).copy()
    valid = np.ones(count, bool)
    original = np.broadcast_to((100 * np.eye(2)).reshape(4), (count, 4)).copy()
    delta = np.broadcast_to(np.eye(2).reshape(4), (count, 4)).copy()
    fitted = identity * np.sqrt(1.01)
    weights = np.ones_like(original, float)
    clean = response._correct(original, weights, (identity, identity, valid))[0]
    injected = response._correct(original + delta, weights, (fitted, fitted, valid))[0]
    direct = response._correct(delta, weights, (fitted, fitted, valid))[0]
    adaptation = (
        response._correct(original, weights, (fitted, fitted, valid))[0] - clean
    )
    np.testing.assert_allclose(injected - clean, direct + adaptation, atol=1e-13)
    np.testing.assert_allclose(injected - clean, 0, atol=1e-13)
    np.testing.assert_allclose(direct, 1 / 1.01, atol=1e-13)
    np.testing.assert_allclose(adaptation, -1 / 1.01, atol=1e-13)


def test_rank_deficiency_does_not_invent_flux_and_negative_noise_is_not_dropped():
    templates, weights, mask = family()
    duplicate = np.stack((templates[0], templates[0]))
    fitted = response.linear_response(-templates[0], duplicate, weights, mask)
    assert not fitted["available"] and fitted["rank"] == 1
    assert fitted["flux_jy"] == [None, None]
    template = np.array([[1, 1j, -1, -1j]], complex)
    noisy = np.array([-0.5, -1j, 2, 3j])
    fitted = response.linear_response(noisy, template, np.ones(4), np.ones(4, bool))
    assert fitted["flux_jy"][0] < 0 and fitted["sample_count"] == 4


def test_high_condition_full_rank_is_reported_unavailable():
    templates = np.array([[1, 0], [0, 1e-9]], complex)
    fitted = response.linear_response(
        np.ones(2), templates, np.ones(2), np.ones(2, bool)
    )
    assert fitted["rank"] == 2 and fitted["condition"] > 1e8
    assert not fitted["available"] and fitted["flux_jy"] == [None, None]


@pytest.mark.parametrize("bad", ["data", "template", "weight", "mask"])
def test_invalid_selected_samples_raise_without_silent_discard(bad):
    templates, weights, mask = family()
    intensity = templates[0].copy()
    if bad == "data":
        intensity[0, 0] = np.nan
    elif bad == "template":
        templates[0, 0, 0] = np.inf
    elif bad == "weight":
        weights[0, 0] = 0
    else:
        mask = mask.astype(int)
    with pytest.raises(ValueError):
        response.linear_response(intensity, templates, weights, mask)


def test_nonselected_nan_values_do_not_change_explicit_support():
    templates, weights, mask = family()
    mask[0] = False
    intensity = 0.06 * templates[0] + 0.12 * templates[1]
    intensity[0] = np.nan
    fitted = response.linear_response(intensity, templates, weights, mask)
    np.testing.assert_allclose(fitted["flux_jy"], [0.06, 0.12], atol=1e-14)
    assert fitted["sample_count"] == mask.sum()


def test_gain_support_uses_actual_integrations_not_row_count():
    state = {
        "times": np.repeat(np.arange(14) * 8.0, 2),
        "names": np.array(["p", "q"]),
        "frequencies": np.linspace(1e9, 1.1e9, 128),
        "train": np.ones((28, 128), bool),
        "antenna1": np.zeros(28, int),
        "antenna2": np.ones(28, int),
    }
    fine, coarse = [response.grid_support(state, grid) for grid in response.GRIDS]
    assert fine["TRAIN_time_frequency_bins"] == 28
    assert fine["TRAIN_antenna_bins"] == 56
    assert coarse["TRAIN_time_frequency_bins"] == 1
    assert coarse["TRAIN_antenna_bins"] == 2
    assert coarse["TRAIN_row_channel_count_min_max"] == [3584, 3584]
    assert not coarse["rank_or_connectivity_certified"]
    for grid in ((True, 32), (0, 32), (2, 32.0)):
        with pytest.raises(ValueError):
            response.grid_support(state, grid)


def budget_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(
        response.shutil, "disk_usage", lambda _: SimpleNamespace(free=32 * 1024**3)
    )
    root = tmp_path / "fresh"
    budget = response.Budget(root)
    budget.mkdir(root)
    return root, budget


def test_budget_rejects_cap_and_reserve_before_write(tmp_path, monkeypatch):
    root, budget = budget_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(response, "ALLOCATION_BYTES", response.allocated_bytes(root))
    with pytest.raises(ValueError, match="allocation"):
        budget.json(root / "never.json", {"x": 1})
    assert not (root / "never.json").exists()
    monkeypatch.setattr(response, "ALLOCATION_BYTES", 1610612736)
    monkeypatch.setattr(
        response.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=response.RESERVE_BYTES),
    )
    with pytest.raises(ValueError, match="reserve"):
        budget.npz(root / "never.npz", x=np.ones(4))
    assert not (root / "never.npz").exists()


def test_budget_preserves_existing_backups_and_rejects_escape(tmp_path, monkeypatch):
    root, budget = budget_fixture(tmp_path, monkeypatch)
    budget.npz(root / "backup.npz", x=np.arange(3))
    original = (root / "backup.npz").read_bytes()
    with pytest.raises(FileExistsError):
        budget.npz(root / "backup.npz", x=np.ones(3))
    assert (root / "backup.npz").read_bytes() == original
    with pytest.raises(ValueError, match="exclusive"):
        budget.json(tmp_path / "escape.json", {})
    assert not (tmp_path / "escape.json").exists()


def test_copy_budget_rejects_source_symlinks_before_writes(tmp_path, monkeypatch):
    root, budget = budget_fixture(tmp_path, monkeypatch)
    source = tmp_path / "source"
    source.mkdir()
    protected = tmp_path / "protected.dat"
    protected.write_bytes(b"immutable")
    (source / "link").symlink_to(protected)
    with pytest.raises(ValueError, match="symlinks"):
        budget.copy(source, root / "copy")
    assert not (root / "copy").exists() and protected.read_bytes() == b"immutable"


def test_operation_observed_reservation_breach_preserves_artifact(
    tmp_path, monkeypatch
):
    root, budget = budget_fixture(tmp_path, monkeypatch)
    artifact = root / "preserve.dat"
    with (
        pytest.raises(ValueError, match="reserved allocation"),
        budget.operation(0, "test"),
    ):
        artifact.write_bytes(b"retained failure")
    assert artifact.read_bytes() == b"retained failure"


@pytest.mark.parametrize("iterations", [0, 49, True, 50.0])
def test_invalid_iterations_never_create_namespace(tmp_path, iterations):
    output = tmp_path / "new"
    with pytest.raises(ValueError):
        response.run(output, tmp_path / "missing", iterations=iterations)
    assert not output.exists()


def test_nested_existing_and_dangling_outputs_refused_before_source_reads(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(
        response, "load_state", lambda _: pytest.fail("source must not be read")
    )
    for output, prepared in (
        (source / "new", source),
        (source, source / "child"),
        (source, tmp_path / "other"),
    ):
        with pytest.raises(ValueError):
            response.run(output, prepared)
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError):
        response.run(dangling, source)
    assert dangling.is_symlink()


def test_baseline_product_distance_is_common_unitary_gauge_invariant():
    rng = np.random.default_rng(251)
    gains = np.broadcast_to(np.eye(2), (8, 2, 2)).astype(complex).copy()
    gains += 0.1 * (rng.normal(size=gains.shape) + 1j * rng.normal(size=gains.shape))
    unitary = np.linalg.qr(rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2)))[0]
    valid = np.ones(8, bool)
    reference = (gains, gains[::-1], valid)
    rotated = (gains @ unitary, gains[::-1] @ unitary, valid)
    assert response._product_distance(rotated, reference, np.ones(8), valid) < 1e-14
    changed = (gains * 1.01, gains[::-1], valid)
    assert response._product_distance(
        changed, reference, np.ones(8), valid
    ) == pytest.approx(0.01)
