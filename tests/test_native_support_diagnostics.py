"""Pure regression tests for read-only retrospective support diagnostics."""

import importlib.util
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "examples/diagnose_native_support.py"
SPEC = importlib.util.spec_from_file_location("native_support_diagnostics", SCRIPT)
diagnostics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostics)


def state():
    rng = np.random.default_rng(131)
    a = np.repeat([0, 0, 1], 20)
    b = np.repeat([1, 2, 2], 20)
    data = (rng.normal(size=(60, 4, 4)) + 1j * rng.normal(size=(60, 4, 4))).astype(
        np.complex64
    )
    sigma = np.ones(data.shape, np.float32)
    weights = np.ones_like(sigma)
    weights[..., 1:3] = 0
    return {
        "ANTENNA1": a,
        "ANTENNA2": b,
        "TIME": np.tile(np.arange(20), 3),
        "DATA": data,
        "SIGMA_SPECTRUM": sigma,
        "WEIGHT_SPECTRUM": weights,
        "FLAG": np.zeros(data.shape, bool),
        "FLAG_ROW": np.zeros(len(data), bool),
    }


def test_original_flags_and_rows_are_lower_bounds_and_inputs_unchanged():
    inputs = state()
    inputs["FLAG"][0, 0, 1] = True
    inputs["FLAG_ROW"][1] = True
    before = deepcopy(inputs)
    report = diagnostics.sigma_diagnostic(inputs, 1, "fixture", n_antennas=4)
    assert report["original_unflagged_cross_cells"] == 235
    assert report["original_support_graph_union"]["unsupported_native_ids"] == [3]
    assert report["WS_times_sigma_squared"]["XY_YX_exact_values"] == [0]
    for key in inputs:
        assert np.array_equal(inputs[key], before[key])


def test_spectral_zeros_not_replaced_by_row_weights_or_sigma():
    inputs = state()
    report = diagnostics.sigma_diagnostic(inputs, 1, "fixture", n_antennas=3)
    assert report["original_unflagged_cross_cells"] == 240
    assert report["WS_times_sigma_squared"]["XX_cell_quantiles"] == [1] * 7
    assert report["WS_times_sigma_squared"]["XY_YX_exact_values"] == [0]
    assert not np.any(inputs["WEIGHT_SPECTRUM"][..., 1:3])


def test_correlations_have_separate_noise_diagnostics():
    inputs = state()
    inputs["DATA"][..., 1] *= 3
    report = diagnostics.sigma_diagnostic(inputs, 1, "fixture", n_antennas=3)
    scales = report["normalized_component_scaledMAD_real_imag_by_corr"]
    assert scales[1][0] > 2 * scales[0][0]
    assert scales[1][1] > 2 * scales[0][1]


@pytest.mark.parametrize("column", ["FLAG", "FLAG_ROW", "SIGMA_SPECTRUM"])
def test_reject_bad_native_layout(column):
    inputs = state()
    inputs[column] = inputs[column][1:]
    with pytest.raises(ValueError, match="layout"):
        diagnostics.sigma_diagnostic(inputs, 1, "fixture", n_antennas=3)


def test_no_protected_support_refuses_diagnostic():
    inputs = state()
    inputs["FLAG"][:] = True
    with pytest.raises(ValueError, match="No original-protected"):
        diagnostics.sigma_diagnostic(inputs, 1, "fixture", n_antennas=3)


def test_graph_distinguishes_bipartite_and_triangle_and_isolates():
    a, b, mask = np.array([0, 1, 0]), np.array([1, 2, 2]), np.ones(3, bool)
    assert not diagnostics.support_graph(a, b, mask, 4)["bipartite"]
    mask[2] = False
    path = diagnostics.support_graph(a, b, mask, 4)
    assert path["bipartite"] and path["components"] == 1
    assert path["unsupported_native_ids"] == [3]


def test_analytic_and_central_jacobian_rank_gauge_dimensions():
    report = diagnostics.rank_diagnostic()
    assert [(r["rank"], r["nullity"]) for r in report] == [
        (14, 18),
        (28, 4),
        (24, 8),
        (28, 4),
        (30, 34),
        (60, 4),
        (56, 8),
        (60, 4),
    ]
    assert max(x["analytic_central_max_error"] for x in report) < 6e-10


def test_gauge_diagnostic_requires_existing_checked_native_library(monkeypatch):
    monkeypatch.delenv("RANG_TOY_LIB", raising=False)
    with pytest.raises(ValueError, match="existing checked Rust"):
        diagnostics.gauge_diagnostic()


def test_pinned_pilot_digest_checked_before_npz_load(tmp_path):
    path = tmp_path / "scan-1.npz"
    path.write_bytes(b"not a zip or an executable object")
    template = {
        "native_sigma_diagnostic": {"groups": [{"scan": 1, "pilot_sha256": "0"}]}
    }
    with pytest.raises(ValueError, match="digest mismatch"):
        diagnostics.regenerate(template, tmp_path, tmp_path)
