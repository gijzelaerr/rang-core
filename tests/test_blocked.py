"""Dense, NumPy-blocked and Rust-blocked local information must agree."""

import pytest

jax = pytest.importorskip("jax")
jax.config.update("jax_enable_x64", True)
import jax.numpy as jnp
import numpy as np
from rangtoy.beams import load_katbeam, make_beam_predictor
from rangtoy.blocked import audit_blocked_design, prepare_blocked_design
from rangtoy.observability import sky_locked_information
from rangtoy.pointing import Observation


@pytest.fixture(scope="module")
def fixture(pointing_full_reference):
    # Session-scoped in conftest.py: built once for every module.
    _, components, obs = pointing_full_reference
    return components, obs


@pytest.fixture(scope="module")
def dense_reference(fixture):
    """The dense audit both frequency_blocking cases compare against.

    It does not depend on frequency_blocking, so it is computed once.
    """
    pytest.importorskip("katbeam")
    sky, obs = fixture
    table, metadata = load_katbeam()
    predictor = make_beam_predictor(table, metadata=metadata)
    covariance = 0.01**2 * np.eye(16)
    dense = sky_locked_information(
        sky,
        obs,
        8,
        noise_jy=0.001,
        predictor=predictor,
        gain_model="per_time_channel",
        differential_pointing=True,
        common_time_variation=True,
        log_flux_prior_covariance=covariance,
    )
    return predictor, covariance, dense


@pytest.mark.parametrize("frequency_blocking", [False, True])
def test_blocked_matches_dense_and_numpy(fixture, dense_reference, frequency_blocking):
    pytest.importorskip("katbeam")
    sky, obs = fixture
    predictor, covariance, dense = dense_reference
    for backend in ("rust", "numpy"):
        design = prepare_blocked_design(
            sky,
            obs,
            8,
            noise_jy=0.001,
            predictor=predictor,
            backend=backend,
            frequency_blocking=frequency_blocking,
        )
        block = audit_blocked_design(design, log_flux_prior_covariance=covariance)
        assert block["compressed_rows"] == 432
        assert block["local_nuisance_ranks"] == [74] * 24
        assert block["observable_common_modes"] == dense["observable_common_modes"]
        np.testing.assert_allclose(
            block["local_crlb_arcsec"], dense["local_crlb_arcsec"], rtol=1e-10
        )
        for key in ("data_only_information", "total_information", "local_covariance"):
            np.testing.assert_allclose(
                block["information_budget"][key],
                dense["information_budget"][key],
                rtol=1e-10,
                atol=1e-10,
            )


@pytest.mark.parametrize("frequency_blocking", [False, True])
def test_blocked_preserves_exact_null_and_flux_anchor_counts(
    fixture, frequency_blocking
):
    sky, obs = fixture
    design = prepare_blocked_design(
        sky,
        obs,
        8,
        noise_jy=0.001,
        beam_axis_ratio=1.1,
        frequency_blocking=frequency_blocking,
    )
    assert audit_blocked_design(design)["observable_common_modes"] == 0
    for fixed, rank in [([0], 0), ([0, 1], 1), ([0, 1, 2], 2)]:
        assert (
            audit_blocked_design(design, fixed_flux_sources=fixed)[
                "observable_common_modes"
            ]
            == rank
        )
    # Aggressive thinning also removes information with a non-Gaussian beam.
    sparse = Observation(*(x[::5] for x in obs))
    design = prepare_blocked_design(
        sky,
        sparse,
        8,
        noise_jy=0.001,
        beam_axis_ratio=1.1,
        frequency_blocking=frequency_blocking,
    )
    assert audit_blocked_design(design)["observable_common_modes"] == 0


def test_blocked_validation(fixture):
    sky, obs = fixture
    with pytest.raises(ValueError, match="gain model"):
        prepare_blocked_design(sky, obs, 8, noise_jy=0.001, gain_model="constant")
    with pytest.raises(ValueError, match="noise"):
        prepare_blocked_design(sky, obs, 8, noise_jy=-1)
    with pytest.raises(ValueError, match="indices"):
        prepare_blocked_design(
            sky,
            obs._replace(antenna1=jnp.full_like(obs.antenna1, 8)),
            8,
            noise_jy=0.001,
        )
