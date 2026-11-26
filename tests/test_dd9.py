# SPDX-License-Identifier: MIT
"""DD9's reference solver (research/dd9-solver.md section 3): the compressed
update against rang's Rust DD kernel on synthetic data, the gauge projection
and the bootstrap pair rule."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dd9", ROOT / "tools" / "oracles" / "dd9" / "dd9.py"
)
dd9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dd9)


def synthetic(nant=7, ndir=3, ntime=8, nchan=6, seed=3, noise=0.05):
    rng = np.random.default_rng(seed)
    p, q = np.triu_indices(nant, 1)
    nbl = len(p)
    a1 = np.tile(p, ntime)
    a2 = np.tile(q, ntime)
    tindex = np.repeat(np.arange(ntime), nbl)
    nrow = len(a1)
    vis = [
        (rng.normal(size=(nrow, nchan)) + 1j * rng.normal(size=(nrow, nchan))).astype(
            np.complex64
        )
        * (2.0 if d == 0 else 0.5)
        for d in range(ndir)
    ]
    nblock = ntime // dd9.BLOCK
    g = np.exp(
        0.1 * rng.normal(size=(nblock, nant, ndir, 2))
        + 0.4j * rng.normal(size=(nblock, nant, ndir, 2))
    )
    blk = tindex // dd9.BLOCK
    data = np.zeros((nrow, nchan, 4), np.complex64)
    for h, corr in enumerate((0, 3)):
        for d in range(ndir):
            data[..., corr] += (
                g[blk, a1, d, h][:, None] * vis[d] * np.conj(g[blk, a2, d, h])[:, None]
            ).astype(np.complex64)
        data[..., corr] += (
            noise
            * (rng.normal(size=(nrow, nchan)) + 1j * rng.normal(size=(nrow, nchan)))
        ).astype(np.complex64)
    weights = rng.uniform(0.5, 2.0, (nrow, nchan, 4)).astype(np.float32)
    flag = np.zeros((nrow, nchan, 4), bool)
    flag[rng.random((nrow, nchan)) < 0.05] = True
    flag_row = np.zeros(nrow, bool)
    flag_row[:3] = True
    return {
        "data": data,
        "weights": weights,
        "flag": flag,
        "flag_row": flag_row,
        "a1": a1,
        "a2": a2,
        "tindex": tindex,
        "vis": vis,
        "nant": nant,
        "nblock": nblock,
    }


class Mem(dd9.Sums):
    def __init__(self, A, b, s, n, p, q, nant):
        self.A, self.b, self.s, self.n, self.p, self.q, self.nant = (
            A,
            b,
            s,
            n,
            p,
            q,
            nant,
        )
        self.nblock, self.nbl = n.shape[:2]
        self.ndir = A.shape[-1]


def build(sy):
    keep = dd9.kept_cells(sy["data"], sy["weights"], sy["flag"], sy["flag_row"])
    inv, p, q = dd9.baseline_index(sy["a1"], sy["a2"])
    block = sy["tindex"] // dd9.BLOCK
    A, b, s, n = dd9.compress(
        sy["data"],
        sy["weights"],
        keep,
        sy["vis"],
        block,
        inv,
        sy["nblock"],
        len(p),
        chunk=50,
    )
    return Mem(A, b, s, n, p, q, sy["nant"])


def rust(sy, cap, pinned=(), direction_update="jacobi"):
    cal_gain = pytest.importorskip("rang.cal_gain")
    models = np.zeros(sy["data"].shape[:2] + (len(sy["vis"]), 4), np.complex64)
    for d, v in enumerate(sy["vis"]):
        models[:, :, d, 0] = models[:, :, d, 3] = v
    sol = cal_gain.solve_dd(sy["data"], models, sy["weights"], sy["flag"], sy["flag_row"], sy["a1"], sy["a2"],
                            sy["tindex"] // dd9.BLOCK, nant=sy["nant"], refant=None, pinned_directions=list(pinned),
                            max_iterations=cap, stop_criterion=1e-7, stop_fraction=1.0, calmode="ap",
                            phase_last_direction_gain=False, direction_update=direction_update)  # fmt: skip
    return np.asarray(sol.gains)[:, 0], np.asarray(sol.flags)[:, 0]


@pytest.mark.parametrize("cap,pinned", [(1, ()), (3, ()), (40, ()), (40, (0,))])
def test_reference_equals_rust_kernel(cap, pinned):
    sy = synthetic()
    S = build(sy)
    P = dd9.Problem(S, np.arange(S.nblock), [1] * S.ndir, pinned=pinned)
    res = dd9.run(P, [cap], stop_fraction=2.0)[cap]
    g, f = dd9.stack_sol(res["g"], res["f"])
    gr, fr = rust(sy, cap, pinned)
    assert np.array_equal(f[:, 0], fr)
    assert np.abs(g[:, 0] - gr).max() < 1e-9


@pytest.mark.parametrize(
    "cap,pinned", [(1, ()), (3, ()), (40, ()), (40, (0,)), (40, (2,))]
)
def test_reference_gauss_seidel_equals_rust_option(cap, pinned):
    """DD10 gate K2a (research/dd10-gs.md): the kernel's Gauss-Seidel option
    against DD9's reference arm I2."""
    sy = synthetic()
    S = build(sy)
    P = dd9.Problem(S, np.arange(S.nblock), [1] * S.ndir, pinned=pinned)
    res = dd9.run(P, [cap], variant="I2", stop_fraction=2.0)[cap]
    g, f = dd9.stack_sol(res["g"], res["f"])
    gr, fr = rust(sy, cap, pinned, "gauss-seidel")
    assert np.array_equal(f[:, 0], fr)
    assert np.abs(g[:, 0] - gr).max() < 1e-9


def test_compressed_normal_equations_equal_cell_sums():
    sy = synthetic(nant=5, ndir=2, ntime=4)
    S = build(sy)
    P = dd9.Problem(S, np.arange(S.nblock), [1, 1])
    rng = np.random.default_rng(1)
    g = [np.exp(0.3j * rng.normal(size=(1, 5, 2))) * 1.1 for _ in range(2)]
    ne = P.normal(g)
    keep = dd9.kept_cells(sy["data"], sy["weights"], sy["flag"], sy["flag_row"])
    for h, corr in enumerate((0, 3)):
        w = np.where(keep, sy["weights"][..., corr], 0).astype(float)
        D = sy["data"][..., corr].astype(complex)
        gp = [g[d][0, sy["a1"], h][:, None] for d in range(2)]
        gq = [g[d][0, sy["a2"], h][:, None] for d in range(2)]
        r = D - sum(gp[d] * sy["vis"][d] * np.conj(gq[d]) for d in range(2))
        for d in range(2):
            jhr = np.zeros(5, complex)
            np.add.at(jhr, sy["a1"], (w * r * np.conj(sy["vis"][d]) * gq[d]).sum(1))
            np.add.at(jhr, sy["a2"], (w * np.conj(r) * sy["vis"][d] * gp[d]).sum(1))
            assert np.allclose(ne[d][0][0, :, h], jhr, rtol=1e-10, atol=1e-8)


def test_gauge_projector_removes_phase_modes():
    g0 = np.exp(1j * np.arange(12).reshape(4, 3))
    fi = np.arange(12)
    P = dd9.gauge_projector(g0, fi, 3)
    x = g0.ravel()
    for d in range(3):
        v = np.where(fi % 3 == d, 1j * x, 0)
        assert np.abs(P @ np.concatenate([v.real, v.imag])).max() < 1e-12
    assert np.allclose(P @ P, P)


def test_bootstrap_median_pair_rule():
    rng = np.random.default_rng(0)
    r = dd9.bootstrap_median(rng.normal(1.0, 0.5, 169))
    assert r["significant"] and r["lo"] > 0
    r = dd9.bootstrap_median(rng.normal(0.0, 1.0, 169))
    assert not r["significant"]
    assert dd9.trimmed_mean([0, 1, 2, 3, 4, 5, 6, 7, 8, 1000]) == pytest.approx(4.5)


@pytest.mark.parametrize("variant", ["I1", "I2", "I3"])
def test_interventions_reach_the_default_fixed_point(variant):
    sy = synthetic(noise=0.01)
    S = build(sy)
    P = dd9.Problem(S, np.arange(S.nblock), [1] * S.ndir)
    a = dd9.run(P, [300], stop_fraction=2.0)[300]
    b = dd9.run(P, [300], variant=variant, stop_fraction=2.0)[300]
    for d in range(S.ndir):
        pa = a["g"][d][:, :, None] * np.conj(a["g"][d][:, None, :])
        pb = b["g"][d][:, :, None] * np.conj(b["g"][d][:, None, :])
        assert np.abs(pa - pb).max() < 1e-6


def test_longer_interval_and_prior_arms_run():
    sy = synthetic(noise=0.01)
    S = build(sy)
    P = dd9.Problem(S, np.arange(S.nblock), [1, 1, 2], lam=[0, 0, 5.0])
    r = dd9.run(P, [50])[50]
    assert r["g"][2].shape[0] == 1 and r["g"][0].shape[0] == S.nblock
    fr, _ = dd9.perdir(r)
    assert all(0 <= x <= 1 for x in fr)
