"""Task P4 (research/p4-eigen.md): the QL survey eigensolver keeps decisions."""

import importlib.util
import json
from pathlib import Path

import numpy as np
from rangtoy.core_influence import anchored_response, training_normals
from rangtoy.projector import _native_library

ROOT = Path(__file__).resolve().parents[1]


def scalar_block(stations, samples, seed):
    """One gain bin of TRAIN normals under a scalar, gauge-preserving model."""
    rng = np.random.default_rng(seed)
    gains = np.broadcast_to(np.eye(2), (1, 4, 2, 2)).astype(np.complex128)
    gains = gains + 0.1 * (
        rng.standard_normal((1, 4, 2, 2)) + 1j * rng.standard_normal((1, 4, 2, 2))
    )
    pairs = [(a, b) for a in range(stations) for b in range(a + 1, stations)] * samples
    n = len(pairs)
    scalar = 1 + 0.5 * rng.standard_normal(n) + 0.5j * rng.standard_normal(n)
    model = scalar[:, None, None] * np.eye(2)
    p, q = (np.array(x) for x in zip(*pairs, strict=True))
    h, _, _ = training_normals(
        gains,
        model,
        np.zeros((n, 2, 2), np.complex128),
        np.ones((n, 4)),
        p,
        q,
        np.zeros(n, int),
    )
    active = np.zeros(4, bool)
    active[:stations] = True
    return h[0], gains[0], active


def test_rank_statuses_match_the_rank_rule():
    zero = np.zeros(32)
    for stations, status, rank in ((4, 0, 28), (3, 0, 20), (2, 3, None)):
        for seed in range(3):
            h, gains, active = scalar_block(stations, 2, seed)
            result = anchored_response(h, zero, 0 * h, zero, gains, active)
            assert result["native_status"] == status
            if rank is not None:
                assert result["diagnostics"]["full_rank"] == rank
                assert result["diagnostics"]["retained_rank"] == rank
                assert result["diagnostics"]["condition"] < 1e10


def test_retained_rank_loss_and_deltas_are_stable():
    h, gains, active = scalar_block(4, 3, 11)
    zero = np.zeros(32)
    assert anchored_response(h, zero, h, zero, gains, active)["native_status"] == 4
    b = np.random.default_rng(5).standard_normal(32) * 1e-3
    drop_h, _, _ = training_normals(
        gains[None],
        np.eye(2)[None].astype(np.complex128),
        np.zeros((1, 2, 2), np.complex128),
        np.ones((1, 4)),
        np.array([0]),
        np.array([1]),
        np.array([0]),
    )
    first = anchored_response(h, b, drop_h[0], 0.1 * b, gains, active)
    second = anchored_response(h, b, drop_h[0], 0.1 * b, gains, active)
    assert first["native_status"] == 0
    assert np.array_equal(first["delta"], second["delta"])


def test_record_replay_and_dump_harness(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "bench_p4_eigen", ROOT / "examples/bench_p4_eigen.py"
    )
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    script = tmp_path / "calls.py"
    script.write_text(
        "import numpy as np\n"
        "import tests_p4_block as t\n"
        "from rangtoy.core_influence import anchored_response\n"
        "for stations in (2, 3, 4):\n"
        "    h, g, a = t.scalar_block(stations, 2, stations)\n"
        "    anchored_response(h, np.zeros(32), 0 * h, np.zeros(32), g, a)\n"
    )
    (tmp_path / "tests_p4_block.py").write_text(
        (Path(__file__)).read_text().split("def test_")[0]
    )
    calls = tmp_path / "calls.npz"
    bench.record(calls, [str(script)])
    lib = _native_library()._name
    out = tmp_path / "replay.json"
    bench.replay(calls, lib, lib, out, passes=2)
    report = json.loads(out.read_text())
    assert report["calls"] == 3
    assert report["status_identical"] and report["recorded_status_equals_a"]
    assert report["status_counts_a"] == {"0": 2, "3": 1}
    records = tmp_path / "records.f64"
    bench.dump(calls, records)
    assert records.stat().st_size == 3 * 2084 * 8
