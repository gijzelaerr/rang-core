"""Known-family safety, true inverse-Jones tangents and no-TEST selection.

Live part of tests/test_flagging_signal_guard.py at commit 2da566c
(now history/tests/test_flagging_signal_guard.py,
sha256 1c0d1749c1b64a193d65a764df17dabe0db3437d28b6c7a4ba28b4334ff57983):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import copy

import numpy as np
import pytest
from rang import core_guard as guard


def family():
    rng = np.random.default_rng(307)
    templates = rng.normal(size=(2, 30)) + 1j * rng.normal(size=(2, 30))
    return templates, np.linspace(1, 3, 30)


def test_full_inverse_tangent_matches_central_difference_and_decomposition():
    rng = np.random.default_rng(331)
    n = 9
    matrices = [
        0.1 * (rng.normal(size=(n, 2, 2)) + 1j * rng.normal(size=(n, 2, 2)))
        for _ in range(4)
    ]
    gp, gq = matrices[0] + np.eye(2), matrices[1] + np.eye(2)
    dp, dq = matrices[2:]
    data = rng.normal(size=(n, 4)) + 1j * rng.normal(size=(n, 4))
    injected = 0.02 * (rng.normal(size=(n, 4)) + 1j * rng.normal(size=(n, 4)))
    total, direct, adaptation = guard.inverse_tangent(
        data, injected, gp, gq, dp, dq, np.ones((n, 4))
    )

    def value(epsilon):
        matrix = (
            np.linalg.inv(gp + epsilon * dp)
            @ (data + epsilon * injected).reshape(n, 2, 2)
            @ np.linalg.inv(gq + epsilon * dq).conj().swapaxes(-1, -2)
        )
        return 0.5 * np.trace(matrix, axis1=-2, axis2=-1)

    epsilon = 1e-5
    np.testing.assert_allclose(
        total, (value(epsilon) - value(-epsilon)) / (2 * epsilon), rtol=1e-8, atol=1e-10
    )
    np.testing.assert_allclose(total, direct + adaptation, rtol=0, atol=1e-15)
    assert np.linalg.norm(adaptation) > 0.01


def test_train_transfer_identity_certifies_and_negative_values_not_clipped():
    templates, weights = family()
    identity = guard.fit_transfer(
        templates, templates, np.zeros_like(templates), templates, weights
    )
    assert identity["guard_pass"] and identity["available"]
    np.testing.assert_allclose(
        identity["transfer_matrices"]["total"], np.eye(2), atol=1e-15
    )
    negative = guard.fit_transfer(
        -templates, templates, -2 * templates, templates, weights
    )
    assert not negative["guard_pass"]
    np.testing.assert_allclose(
        negative["transfer_matrices"]["total"], -np.eye(2), atol=1e-15
    )


def test_absolute_guard_never_normalizes_by_unsafe_baseline():
    templates, weights = family()
    unsafe = guard.fit_transfer(
        0.5 * templates, templates, -0.5 * templates, templates, weights
    )
    assert unsafe["available"] and not unsafe["guard_pass"]
    assert unsafe["absolute_transfer_operator_error"] == pytest.approx(0.5)


def test_transfer_cross_leakage_operator_norm_not_diagonal_only():
    templates, weights = family()
    transfer = np.array([[1, 0.11], [0, 1]])
    values = transfer.T @ templates
    report = guard.fit_transfer(
        values, templates, values - templates, templates, weights
    )
    assert not report["guard_pass"]
    np.testing.assert_allclose(
        report["transfer_matrices"]["total"], transfer, atol=1e-15
    )


def test_rank_deficiency_is_missing_not_invented_safe_response():
    templates, weights = family()
    templates[1] = templates[0]
    report = guard.fit_transfer(
        templates, templates, np.zeros_like(templates), templates, weights
    )
    assert not report["available"] and not report["guard_pass"]
    assert report["transfer_matrices"] == {}


def record(identifier, objective, safe=True):
    return {
        "mask_id": identifier,
        "guard_pass": safe,
        "predicted_objective": objective,
        "predicted_benefit": 1.25 - objective,
        "candidate": {"added_fraction": 0.001},
    }


def test_two_slots_deterministic_and_signal_guard_can_abstain():
    records = [record("a", 1.2), record("b", 1.21), record("c", 1.1, False)]
    signals = {
        "a": {"guard_pass": False},
        "b": {"guard_pass": True},
        "c": {"guard_pass": True},
    }
    assert guard.choose_slots(records, signals) == {
        "without_signal_guard": "a",
        "with_signal_guard": "b",
    }
    signals["b"]["guard_pass"] = False
    assert guard.choose_slots(records, signals)["with_signal_guard"] is None
    for r in records:
        r["TEST_loss"] = -1e20
        r["truth_flux"] = 1e20
    assert guard.choose_slots(records, signals)["without_signal_guard"] == "a"


def metrics(validation=1.0):
    return {
        "tv": 1.0,
        "added_fraction": 0.001,
        "losses": {"validation": validation, "test": 1.0},
        "invalid_predictions": {"train": 0, "validation": 0, "test": 0},
    }


def test_actual_acceptance_quality_1percent_and_TEST_loss_never_select():
    original, candidate = metrics(), metrics()
    candidate["losses"]["test"] = 1e30
    result = guard.actual_acceptance(candidate, 0.9, original, True, False)
    assert (
        result["without_signal_guard_accept"] and not result["with_signal_guard_accept"]
    )
    candidate["losses"]["validation"] = 1.011
    assert not guard.actual_acceptance(candidate, 0.9, original, True, True)[
        "with_signal_guard_accept"
    ]
    candidate["losses"]["validation"] = 1.0
    candidate["invalid_predictions"]["test"] = 1
    assert not guard.actual_acceptance(candidate, 0.9, original, True, True)[
        "with_signal_guard_accept"
    ]


@pytest.mark.parametrize("bad", [np.nan, 0.0, -1.0])
def test_inverse_tangent_rejects_invalid_native_weights(bad):
    gain = np.broadcast_to(np.eye(2), (2, 2, 2))
    weights = np.ones((2, 4))
    weights[0, 0] = bad
    with pytest.raises(ValueError, match="TRAIN"):
        guard.inverse_tangent(
            np.ones((2, 4)),
            np.zeros((2, 4)),
            gain,
            gain,
            np.zeros_like(gain),
            np.zeros_like(gain),
            weights,
        )


def test_quality_guard_unchanged_by_arbitrary_test_flux_and_truth_payload():
    baseline, candidate = metrics(), metrics()
    first = guard.actual_acceptance(candidate, 0.95, baseline, True, True)
    changed = copy.deepcopy(candidate)
    changed["losses"]["test"] = None
    changed["source_truth"] = {"flux": -1e50}
    assert guard.actual_acceptance(changed, 0.95, baseline, True, True) == first


def train_fixture():
    p, q = np.triu_indices(4, 1)
    data = np.zeros((6, 2, 4), complex)
    data[..., 0] = data[..., 3] = 1
    train = np.zeros((6, 2), bool)
    train[:, 0] = True
    state = {
        "data": data.copy(),
        "model": data.copy(),
        "weights": np.ones_like(data.real),
        "train": train,
        "validation": np.zeros_like(train),
        "test": ~train,
        "times": np.ones(6),
        "frequencies": np.array([1.28e9, 1.29e9]),
        "antenna1": p,
        "antenna2": q,
        "window": np.ones(2, bool),
        "original_flags": np.zeros_like(data, bool),
        "original_rows": np.zeros(6, bool),
    }
    gains = np.broadcast_to(np.eye(2), (1, 1, 4, 2, 2)).astype(complex).copy()
    baseline = {"gains": gains, "gain_valid": np.ones((1, 1, 4), bool)}
    rng = np.random.default_rng(347)
    templates = rng.normal(size=(2, 6, 2)) + 1j * rng.normal(size=(2, 6, 2))
    return state, baseline, templates


def test_native_train_signal_tangent_binding_and_no_TEST_values():
    state, baseline, templates = train_fixture()
    indices = np.empty(0, np.int64)
    first = guard.train_signal_guard(
        state, baseline, baseline["gains"], indices, templates
    )
    assert first["available"] and first["fits"]["total"][0]["rank"] == 2
    assert first["native_audits"][0][0]["diagnostics"]["full_rank"] == 28
    changed = copy.deepcopy(state)
    changed["data"][changed["test"]] = np.nan + 1j * np.inf
    changed["model"][changed["test"]] = -1e50
    changed["weights"][changed["test"]] = -1
    second = guard.train_signal_guard(
        changed, baseline, baseline["gains"], indices, templates
    )
    assert second == first


def test_guard_nonTRAIN_mask_and_lost_inverse_support_refuse():
    state, baseline, templates = train_fixture()
    with pytest.raises(ValueError, match="non-TRAIN"):
        guard.train_signal_guard(
            state, baseline, baseline["gains"], np.array([1]), templates
        )
    singular = baseline["gains"].copy()
    singular[..., 0, :] = 0
    report = guard.train_signal_guard(
        state, baseline, singular, np.empty(0, np.int64), templates
    )
    assert not report["available"] and not report["guard_pass"]


def test_probe_rank_loss_abstains_not_support_pruning():
    state, baseline, templates = train_fixture()
    # Removing every baseline incident to station0 cannot be called safe.
    indices = np.flatnonzero(state["train"] & (state["antenna1"] == 0)[:, None])
    report = guard.train_signal_guard(
        state, baseline, baseline["gains"], indices, templates
    )
    assert not report["available"] and not report["guard_pass"]
    assert "support lost" in report["reason"]


def test_root_forecast_contract_empty_family_and_nochange_slots():
    from rang import core_forecast as flagging_prospective

    state, baseline, _ = train_fixture()
    forecast = flagging_prospective.forecast_family(state, baseline, metrics(), [])
    assert forecast["raw_predicted_gains"].shape == (0, *baseline["gains"].shape)
    assert forecast["full_h"].shape == (1, 32, 32)
    assert forecast["full_b"].shape == (1, 32)
    assert forecast["records"] == []
    flagging_prospective.score_forecasts(state, forecast)
    assert guard.choose_slots(forecast["records"], {}) == {
        "without_signal_guard": None,
        "with_signal_guard": None,
    }


@pytest.mark.parametrize("dtype", [np.int64, np.uint64])
def test_signed_unsigned_unsorted_mask_rejected_before_curvature(dtype):
    state, baseline, templates = train_fixture()
    with pytest.raises(ValueError, match="sorted unique"):
        guard.train_signal_guard(
            state,
            baseline,
            baseline["gains"],
            np.array([4, 2], dtype=dtype),
            templates,
        )
