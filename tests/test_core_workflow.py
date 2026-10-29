import numpy as np
from rangtoy.core_workflow import core_solve, gain_grid, solve_flags
from rangtoy.flagging import protected_flags


def _state(seed=2, nchan=64):
    rng = np.random.default_rng(seed)
    pairs = [(p, q) for p in range(4) for q in range(p, 4)]
    ntimes = 4
    p = np.tile([a for a, _ in pairs], ntimes).astype(np.int32)
    q = np.tile([b for _, b in pairs], ntimes).astype(np.int32)
    times = np.repeat(np.arange(ntimes, dtype=float), len(pairs))
    shape = (len(p), nchan, 4)
    truth = np.eye(2) + 0.05 * (
        rng.standard_normal((4, 2, 2)) + 1j * rng.standard_normal((4, 2, 2))
    )
    flux = np.linspace(1.0, 1.5, nchan)
    model = np.zeros(shape, np.complex64)
    model[..., 0] = model[..., 3] = flux
    data = (
        truth[p][:, None]
        @ (flux[None, :, None, None] * np.eye(2))
        @ truth[q][:, None].conj().swapaxes(-1, -2)
    ).reshape(shape)
    data = (
        data + 0.01 * (rng.standard_normal(shape) + 1j * rng.standard_normal(shape))
    ).astype(np.complex64)
    cross = (p != q)[:, None] & np.ones(nchan, bool)
    split = rng.integers(0, 10, (len(p), nchan))
    return {
        "data": data,
        "model": model,
        "weights": np.ones(shape, np.float32),
        "times": times,
        "frequencies": np.linspace(1.0e9, 1.1e9, nchan),
        "antenna1": p,
        "antenna2": q,
        "names": np.array(["m000", "m001", "m002", "m003"]),
        "original_flags": np.zeros(shape, bool),
        "original_rows": np.zeros(len(p), bool),
        "train": cross & (split < 8),
        "validation": cross & (split == 8),
        "test": cross & (split == 9),
    }


def test_solve_flags_match_set_flags_semantics():
    state = _state()
    added = np.zeros_like(state["train"])
    added[np.nonzero(state["train"])[0][0], np.nonzero(state["train"])[1][0]] = True
    flags, rows = solve_flags(state, added)
    expected = protected_flags(
        state["original_flags"],
        state["original_rows"],
        (~state["train"] | added)[..., None] & np.ones(4, bool),
    )
    np.testing.assert_array_equal(flags, expected[0])
    np.testing.assert_array_equal(rows, expected[1])
    # Autocorrelations are never in train, so their rows are fully flagged.
    assert rows[state["antenna1"] == state["antenna2"]].all()


def test_core_solve_returns_the_workflow_products():
    state = _state()
    metrics, _tv, residuals, guidance, diagnostics = core_solve(
        state, np.zeros_like(state["train"]), 2, 32, 50, trial="t"
    )
    for key in (
        "trial",
        "seconds",
        "tv",
        "raw_tv",
        "time_tv",
        "frequency_tv",
        "scale",
        "valid_gain_fraction",
        "losses",
        "invalid_predictions",
        "added_count",
        "added_fraction",
    ):
        assert key in metrics
    assert metrics["valid_gain_fraction"] == 1.0
    assert all(v is not None for v in metrics["losses"].values())
    assert residuals.shape == state["data"].shape
    assert guidance.shape == state["train"].shape
    assert set(diagnostics) >= {"gains", "gain_valid", "tv_valid", "gauge_gains"}
    _, _, times, freqs = gain_grid(state, 2, 32)
    assert diagnostics["gains"].shape[:3] == (len(times), len(freqs), 4)
    # Noise is 0.01 per component and weights are one: the loss is near 2e-4.
    assert 1e-4 < metrics["losses"]["train"] < 4e-4
