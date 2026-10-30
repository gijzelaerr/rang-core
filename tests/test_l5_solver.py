"""Task L5 (research/l5-solver-science.md): the run-time solver options reach
the core through `RANG_SOLVE_OPTIONS` (one backend since task P7), default to the archived solver,
fail loudly when malformed, and the trace replays the core's stop rule."""

import importlib.util
import os

import numpy as np
import pytest
from rang import core
from rang import core_solver_study as study


def synthetic(seed=5):
    rng = np.random.default_rng(seed)
    pairs = [(p, q) for p in range(4) for q in range(p + 1, 4)]
    rows = [(t, p, q) for t in range(6) for p, q in pairs]
    nrow, nchan = len(rows), 64
    a1 = np.array([r[1] for r in rows], np.int32)
    a2 = np.array([r[2] for r in rows], np.int32)
    time_bin = np.array([r[0] // 2 for r in rows])
    freq_bin = np.arange(nchan) // 16
    truth = np.eye(2) + 0.1 * (
        rng.standard_normal((4, 2, 2)) + 1j * rng.standard_normal((4, 2, 2))
    )
    model = (np.eye(2) + 0.2 * rng.standard_normal((nrow, nchan, 2, 2))).astype(
        np.complex64
    )
    data = np.einsum("rij,rcjk,rlk->rcil", truth[a1], model, truth[a2].conj())
    data = data + 0.01 * rng.standard_normal(data.shape)
    weights = (1 + rng.random((nrow, nchan, 4))).astype(np.float32)
    split = rng.random((nrow, nchan))
    return {
        "data": data.reshape(nrow, nchan, 4).astype(np.complex64),
        "model": model.reshape(nrow, nchan, 4),
        "weights": weights,
        "flag": np.zeros((nrow, nchan, 4), bool),
        "flag_row": np.zeros(nrow, bool),
        "antenna1": a1,
        "antenna2": a2,
        "time_map": time_bin,
        "freq_map": freq_bin,
        "ntime_bins": 3,
        "nfreq_bins": 4,
        "nant": 4,
        "gain_times": np.arange(3.0),
        "gain_frequencies": np.arange(4.0),
        "train": split < 0.8,
        "validation": (split >= 0.8) & (split < 0.9),
        "test": split >= 0.9,
    }


@pytest.fixture(params=["extension"])
def backend(request, monkeypatch):
    # The ctypes backend was removed by task P7 (research/p7-architecture.md).
    if importlib.util.find_spec("rang._core") is None:
        pytest.skip("rang._core is not built")
    monkeypatch.delenv("RANG_CORE_BACKEND", raising=False)
    monkeypatch.delenv("RANG_CORE_LIB", raising=False)
    core.reset_backend()
    assert core.backend_name() == request.param
    yield request.param
    core.reset_backend()


def test_default_and_explicit_archived_options_are_identical(backend, monkeypatch):
    problem = synthetic()
    monkeypatch.delenv(study.OPTIONS_VAR, raising=False)
    plain = core.solve_complex(
        problem["data"],
        problem["weights"],
        problem["flag"],
        problem["flag_row"],
        problem["antenna1"],
        problem["antenna2"],
        problem["time_map"],
        problem["freq_map"],
        ntime_bins=3,
        nfreq_bins=4,
        nant=4,
        model=problem["model"],
    )
    explicit = study.solve(problem, "qp_weights=archived,stop=gain,anderson=0,freeze=0")
    assert plain.gains.tobytes() == explicit["gains"].tobytes()
    assert plain.iterations == explicit["iterations"]
    # The options are restored after the block.
    assert study.OPTIONS_VAR not in os.environ


def test_options_change_the_solve_and_malformed_options_fail(backend):
    problem = synthetic()
    archived = study.solve(problem, "")
    transposed = study.solve(problem, "qp_weights=transposed")
    assert archived["gains"].tobytes() != transposed["gains"].tobytes()
    early = study.solve(problem, "stop=product:1e-3", max_iterations=200)
    assert early["iterations"] < 200
    with pytest.raises(RuntimeError, match="status 1"):
        study.solve(problem, "stop=sideways")


def test_trace_replays_the_stop_rule(tmp_path, backend):
    problem = synthetic()
    path = tmp_path / "trace.json"
    study.solve(problem, "", max_iterations=80, stop_fraction=2.0, trace=path)
    trace = study.load_trace(path)
    assert len(trace["gain_converged"]) == 80
    assert trace["product_change"].shape == (80, 12)
    for criterion, tolerance in (("product", 1e-4), ("loss", 1e-4)):
        want = study.stop_iteration(trace, criterion, tolerance, 0.9)
        assert want is not None and want < 80
        got = study.solve(
            problem,
            f"stop={criterion}:{tolerance:g}",
            max_iterations=80,
            stop_fraction=0.9,
        )
        assert got["iterations"] == want
        prefix = study.solve(problem, "", max_iterations=want, stop_fraction=2.0)
        assert prefix["gains"].tobytes() == got["gains"].tobytes()


def test_summary_metrics(backend):
    problem = synthetic()
    D = study.solve(problem, "")
    R = study.solve(problem, "", max_iterations=200, stop_fraction=2.0)
    scale = study.gain_scale(D["gains"], D["valid"])
    record = study.summary(problem, D, R, D, scale)
    assert record["product_distance_to_default"]["max"] == 0.0
    assert record["vs_default"]["relative"]["test"] == 0.0
    assert record["product_distance_to_reference"]["max"] < 1e-3
    assert record["losses"]["validation"] > 0
