"""Task P1 (research/p1-solver.md): the solver and fused pass give the same
bits at every rayon thread count. Rayon's global pool is fixed per process,
so each thread count runs in its own subprocess."""

import json
import os
import subprocess
import sys

import pytest

CHILD = r"""
import hashlib, json
import numpy as np
from rang import core

rng = np.random.default_rng(5)
pairs = [(p, q) for p in range(4) for q in range(p, 4)]
rows = [(t, p, q) for t in range(6) for p, q in pairs]
nrow, nchan = len(rows), 64
a1 = np.array([r[1] for r in rows], np.int32)
a2 = np.array([r[2] for r in rows], np.int32)
time_bin = np.array([r[0] // 2 for r in rows])
freq_bin = (np.arange(nchan) * 3) % 8
truth = np.eye(2) + 0.1 * (rng.standard_normal((4, 2, 2)) + 1j * rng.standard_normal((4, 2, 2)))
model = (np.eye(2) + 0.2 * rng.standard_normal((nrow, nchan, 2, 2))).astype(np.complex64)
data = np.einsum("rij,rcjk,rlk->rcil", truth[a1], model, truth[a2].conj())
data = data + 0.01 * rng.standard_normal(data.shape)
data = data.reshape(nrow, nchan, 4).astype(np.complex64)
model = model.reshape(nrow, nchan, 4)
weights = (1 + rng.random((nrow, nchan, 4))).astype(np.float32)
flag = rng.random((nrow, nchan, 4)) > 0.95
flag_row = np.zeros(nrow, bool)
out = {}
for name, settings in {"cap": {}, "early": {"stop_criterion": 1e-3, "stop_fraction": 0.5}}.items():
    s = core.solve_complex(data, weights, flag, flag_row, a1, a2, time_bin, freq_bin,
                           ntime_bins=3, nfreq_bins=8, nant=4, model=model, **settings)
    out[name] = [hashlib.sha256(s.gains.tobytes() + s.flags.tobytes()).hexdigest(),
                 s.iterations, s.converged_fraction.hex()]
split = rng.integers(0, 4, (nrow, nchan)).astype(np.uint8)
f = core.fused_pass(data, weights, a1, a2, time_bin, freq_bin, s.gains, s.flags == 0,
                    split, model=model)
out["fused"] = hashlib.sha256(b"".join(
    x.tobytes() for x in (f.residuals, f.scores, f.diag_h, f.diag_b, f.diag_count)
)).hexdigest()
out["stats"] = {k: {**v, "sum": v["sum"].hex()} for k, v in f.split_stats.items()}
print(json.dumps(out))
"""


def run_child(threads):
    env = {**os.environ, "RAYON_NUM_THREADS": str(threads), "OPENBLAS_NUM_THREADS": "1"}
    done = subprocess.run(
        [sys.executable, "-c", CHILD],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    if done.returncode:
        pytest.fail(done.stderr)
    return json.loads(done.stdout)


def test_solver_and_fused_pass_identical_across_thread_counts():
    one = run_child(1)
    # The early-stop case ends by the stop test, before the 50-iteration cap.
    assert one["cap"][1] == 50
    assert 1 < one["early"][1] < 50
    for threads in (2, 7):
        assert run_child(threads) == one
