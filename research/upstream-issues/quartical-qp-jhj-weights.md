# QuartiCal: the qp half of the complex-term JHJ uses the pq weight order

PR (task U2): **none, by maintainer direction.** JSKenyon replied "I will fix it on the dev
branch as soon as possible". Checked on v0.2.8-dev 059c806 (no fix yet): the shared loop in
`gains/general/solver_components.py` passes the pq `w` to both qp accumulations, so `complex`,
`rotation`, `rotation_measure` and `crosshand_phase` are all affected; a conjugate-baseline
invariance test (swap ANTENNA1/2, conjugate-transpose DATA and MODEL, transpose WEIGHT)
fails 8/8 (4 terms x 1 and 2 directions; JHR invariant, JHJ differs by up to 2e3) and passes
8/8 with `w_qp = tuple_unpackct(w)` in both qp calls. Not pushed; details in
[../upstream-prs.md](../upstream-prs.md).

Repository: ratt-ru/QuartiCal. Status: **filed 2026-10-30, https://github.com/ratt-ru/QuartiCal/issues/452; fixed in #456 (v0.2.8-dev d54c46b), verified 2026-10-30 (section at the end).**
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

## 2026-10-30: fix verified on v0.2.8-dev d54c46b (PR #456)

Reported on the issue: https://github.com/ratt-ru/QuartiCal/issues/452#issuecomment-6523517450

Maintainer fix: [ratt-ru/QuartiCal#456](https://github.com/ratt-ru/QuartiCal/pull/456),
merged 2026-10-30 into `v0.2.8-dev` as d54c46b (parent 059c806). It adds
`tuple_unpackt_factory` and passes `w_qp` (XY and YX swapped) to the ANTENNA2 accumulation in
both paths of the shared loop (`gains/general/solver_components.py`), so no term kernel
changes, and adds `testing/tests/gains/test_baseline_orientation.py` (every solvable term,
unequal cross-hand weights). **Correction to the record above:** `leakage` is also affected
(the PR lists complex, leakage, rotation, rotation_measure, crosshand_phase; U2's test did
not include leakage). Both dev installs report version `0.2.7`; cite the commits.

Setup: WSL, uv venvs (Python 3.13, Numba 0.68.1, NumPy 2.5.4, dask-ms 0.2.32), QuartiCal 0.2.7
(PyPI), 059c806 and d54c46b (git), each with a fresh `NUMBA_CACHE_DIR`;
`OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=4`. Scripts: `../upstream-prs-files/q452-*`
(paths inside point at the session scratch; scratch deleted afterwards).

**Measured, loop level** (`q452-loopcheck.py`): the complex `compute_jhj_jhr` (whole shared
loop), 5 antennas, 4 times x 4 channels in one interval, noise-free V = G_p M G_q^H, base
weights uniform(0.5, 1.5) per sample and correlation (so w_XY != w_YX even at scale 1),
one antenna at identity and the rest at the truth; exact J^H W J with the weights of the
visibility the antenna sees; one Gauss-Newton step.

| weights (scale on XX, XY, YX, YY) | 0.2.7 and 059c806, ANTENNA2-only antenna | d54c46b, same |
| --- | --- | --- |
| control, w_YX = w_XY | 3e-13 to 7e-13 / 2e-16 to 2e-15 | 3.4e-13 / 2.2e-16 |
| (1, 1, 1, 1) | 3.34e1 / 1.45e-1 | 1.1e-13 / 2.2e-16 |
| (1, 0.2, 5, 1) | 1.74e3 / 3.78 | 9.1e-13 / 4.0e-16 |
| (1, 1, 4, 1) | 1.10e3 / 1.36 | 4.6e-13 / 3.4e-16 |
| (1, 1, 25, 1) | 8.72e3 / 10.9 | 3.6e-12 / 2.2e-16 |

(max |JHJ - J^H W J| / one-step max gain error.) The ANTENNA1-only antenna is at rounding
(<= 3e-12 / <= 1e-15) in all three builds. The issue's element snippet on 0.2.7 reproduces
4.33e2 / 6.84 (w) and 1.14e-13 / 3.1e-16 (w^T).

**Measured, tests:** U2's `test_conjugate_baseline.py` (complex, rotation,
rotation_measure, crosshand_phase x 1 and 2 directions): 059c806 8 failed, all on the JHJ
assertion (max abs JHJ difference 1.3e3, 2.0e3, 1.2e3, 1.4e3, 0.87, 6.9, 1.1e3, 1.9e3),
d54c46b 8 passed (130 s each incl. JIT). PR #456's test: 059c806 5 failed (complex, leakage,
rotation, rotation_measure, crosshand_phase), 9 passed; d54c46b 14 passed (about 1000 s each
incl. JIT, both run concurrently with other jobs).

**Measured, solves on scan 9** (`outer_scans.zip`, `prep.py`: 140 rows, 4 antennas, 14 dumps
x 4096 channels, 46.8 % flagged, MODEL_DATA = 1 on XX/YY; `G.type=complex`, 2 x 32
intervals, criterion 1e-7, fraction 0.99, cap 100; dev runs with `G.referenced=false`
unless stated). Reference: d54c46b, 500 iterations, fraction 2.0. Weight arms: unit (no
weight column), native `WEIGHT_SPECTRUM` (w_YX/w_XY over unflagged cross-hand samples:
5th-95th percentile 0.86-1.18, median 1.01), native with YX x 4 (`q452-weights.py`).
Products P_pq = G_p G_q^H over the 546 of 896 intervals with no flagged antenna.

| arm | 0.2.7 | 059c806 | d54c46b |
| --- | --- | --- | --- |
| unit: converged / flagged antenna-intervals | 98.76 % / 39.0 % | same | same |
| native: converged / flagged | 98.76 % / 39.0 % | same | same |
| YX x 4: converged / flagged | **67.42 % / 81.50 %** | **67.37 % / 81.53 %** | 98.76 % / 39.01 % |

All cap-100 runs stop at the cap (the 0.99 fraction is not reached on scan 9, as in #455).
39.0 % of antenna-intervals are flagged by the data flags alone, so before the fix the YX x 4
solve loses about 70 % of the solvable antenna-intervals to gain flags; after it, the same
as unit weights. Product distance to the reference, median / max: unit 1.2e-16 to 1.4e-16 / 0.215 in
every build; native 1.5e-16 / 0.218 (0.2.7, 059c806) vs 3.7e-17 / 0.217 (d54c46b); YX x 4
d54c46b 3.9e-17 / 0.204 (the max is the ~1 % of intervals that hit the cap). Exact gains:
unit 059c806 = d54c46b bit for bit, 0.2.7 vs dev max 2.0e-14 (loop rewrite, not bit-exact);
native 059c806 vs d54c46b max 0.17 (only unconverged intervals move; median product
distance to the reference unchanged). `G.referenced=true` (default) vs false on d54c46b:
products agree to <= 6.8e-16 in all arms (diagonal model, so referencing is a pure gauge
change). Walls (3-5 s per warm run, dominated by start-up) are not a performance measure.

**Measured, rang's port on the same arrays** (`q452-ms2npz.py`, `q452-rangsolve.py`, autos
excluded through FLAG_ROW, `RAYON_NUM_THREADS=4`, cap 100, 1e-7, 0.99): `qp_weights=archived`
vs QuartiCal 0.2.7 max gain difference 2.3e-14 (unit), 6.3e-15 (native); on YX x 4 both flag
81.5 % (port 81.53 % = 059c806; 0.2.7 81.50 %, divergence amplifies rounding) and converge
67.4 %. `qp_weights=transposed` vs d54c46b: 9.2e-15 (unit), 4.1e-15 (native), 1.5e-14
(YX x 4), so rang's opt-in option equals the upstream fix. Unit weights: archived =
transposed bit for bit. Each port solve 0.3 s (cap 100), 1.1 s (cap 500).

**What v0.2.8-dev changes for rang's archived comparisons** (input for re-validating the
port against dev; 0.2.7 stays the archived reference):
- #456: qp weights transposed. Matches `qp_weights=transposed`; archived results differ
  wherever w_XY != w_YX (native MeerKAT weights already differ by +-15 %; robust
  reweighting more). If rang adopts dev as the reference, `transposed` becomes the
  compatible default.
- #430: all terms on one shared loop. With unit weights complex gains match 0.2.7 to 2e-14,
  not bit for bit, so bit-exact port checks against dev need a new archive or a tolerance.
- #440: `referenced` per term, default true, now applied to `complex`: default dev output
  is gauge-fixed (reference antenna's diagonal phases zero). Compare products or set
  `G.referenced=false`; with a non-diagonal model referencing moves the solution off the
  fit (PR text).
- #443 reference antenna by name; #441/#447 beam and parallactic angles about the pointing;
  #448 antennas aligned by name when loading solutions; #451 FEED subtable partitioning;
  #427-#429, #437 term-spec/jhj sizing and identity fills; #368 DDID handling, feed-flip
  term, optional chain collapse, scalar mode for diagonal parameterised terms. None
  touches the complex-only scan 9 path measured here, but the angle and DDID changes
  matter for any parallactic-angle or multi-SPW comparison.
- Performance: not measured here (dev's solver wiki cites measured 1.4-2.8x speedups for the
  tuple-style accumulation of #430); a matched timing needs warm caches and a larger MS.
