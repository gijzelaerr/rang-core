# QuartiCal: the qp half of the complex-term JHJ uses the pq weight order

Repository: ratt-ru/QuartiCal. Status: **to be filed** (URL recorded here once filed).
Checked 2026-10-30 on QuartiCal 0.2.7 (PyPI, identical to `main` 942f77f), Numba 0.68.1,
NumPy 2.5.4, Python 3.13; v0.2.8-dev (059c806) inspected, not run. Origin: rang's port of the
`complex` term ([stack-consolidation-feasibility.md](../stack-consolidation-feasibility.md)).

<!-- issue-title: complex term: JHJ for the conjugate (qp) side uses the pq weight order, swapping the XY and YX weights -->
<!-- issue-body -->
**Describe the bug**
In `nb_compute_jhj_jhr` (`quartical/gains/complex/kernel.py`, 0.2.7 / `main`), each row contributes to antenna p through V_pq and to antenna q through V_qp = V_pq^H. The weighted residual for the qp side is `iunpackct(wr_qp, wr_pq)`, i.e. (w∘r)^H = w^T∘r^H, so JHr for antenna q correctly pairs element XY of V_qp with the YX weight. JHJ for antenna q is accumulated with the untransposed `w` (`compute_jhwj_jhwr_elem(lop_qp_d, rop_qp_d, w, ...)`, lines 420-426), so its XY and YX weights are swapped relative to JHr. Whenever w_XY != w_YX, the JHJ used for antenna q is not J^H W J of the objective whose gradient is JHr.

The fixed point is unchanged (JHr is right), but every antenna's JHJ includes these swapped-weight terms from the baselines where it is `ANTENNA2`, so the update is not the Gauss-Newton step (see the one-step check below); I have not measured the effect on full solves. With `solver.robust=true`, `update_weights` sets `w[c] = eta * icov[c]` with a per-correlation `icov`, so w_XY != w_YX in ordinary use; a per-correlation WEIGHT_SPECTRUM does the same.

**To Reproduce**
QuartiCal's own element kernel against the exact J^H W J for antenna q (others fixed, noise-free data):
```python
import numpy as np
from numba.core import types
from quartical.gains.complex.kernel import compute_jhwj_jhwr_elem_factory
elem = compute_jhwj_jhwr_elem_factory(types.IntegerLiteral(4))
rng = np.random.default_rng(1)
c = lambda: rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2))
w = np.array([1.0, 0.2, 5.0, 1.0])  # XX, XY, YX, YY
wT = w[[0, 2, 1, 3]]                # weights of the elements of V_qp = V_pq^H
Gp, Gq_true, Gq0, I = c(), c(), np.eye(2, dtype=complex), np.eye(2, dtype=complex)
acc = {k: [np.zeros(4, complex), np.zeros((4, 4), complex)] for k in ("w", "wT")}
H = np.zeros((4, 4), complex)       # exact J^H W J for antenna q
for _ in range(16):                 # 16 samples in one solution interval
    M = c()
    r_pq = Gp @ M @ Gq_true.conj().T - Gp @ M @ Gq0.conj().T
    wr_qp = (w.reshape(2, 2) * r_pq).conj().T          # as iunpackct(wr_qp, wr_pq)
    rop_qp = Gp @ M                                    # V_qp = G_q @ rop_qp^H
    J = np.kron(I, rop_qp.conj())                      # d vec(V_qp) / d vec(G_q)
    H += J.conj().T @ np.diag(wT) @ J
    for k, wk in (("w", w), ("wT", wT)):
        elem(I.ravel().copy(), rop_qp.ravel().copy(), wk.copy(),
             np.zeros((4, 4), complex), wr_qp.ravel().copy(), *acc[k])
for k, (jhr, jhj) in acc.items():
    step = np.linalg.solve(jhj, jhr).reshape(2, 2)
    print(f"weights {k:2s}: max|JHJ - J^H W J| = {np.abs(jhj - H).max():.2e}, "
          f"one-step gain error = {np.abs(Gq0 + step - Gq_true).max():.2e}")
```
Output (QuartiCal 0.2.7, Numba 0.68.1):
```
weights w : max|JHJ - J^H W J| = 4.33e+02, one-step gain error = 6.84e+00
weights wT: max|JHJ - J^H W J| = 1.14e-13, one-step gain error = 3.14e-16
```
**Expected behaviour**
The qp contribution uses the transposed weights, as JHr already does (second line).

**Suggested fix**
Before the second `compute_jhwj_jhwr_elem` call, build `w_qp` with XY and YX swapped (`w_qp = (w[0], w[2], w[1], w[3])`) and pass it instead of `w`; untested beyond the check above. On v0.2.8-dev the shared loop in `gains/general/solver_components.py` passes the same `w` to the qp accumulation (lines 400 and 536), so the fix belongs there. `rotation`, `rotation_measure` and `crosshand_phase` follow the same call pattern and read w_1/w_2; I have not tested them. Kernels that read only w_0 and w_3 are unaffected.
<!-- end-issue-body -->
