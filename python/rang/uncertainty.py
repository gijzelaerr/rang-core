"""Local Gauss–Newton uncertainty; not a model-mismatch error estimate."""

import numpy as np


def propagated_standard_deviation(residual_jacobian, output_jacobian):
    """Propagate inverse J.T J using SVD, without forming normal equations.

    J must include all prior rows. Noise is already whitened and is not
    re-estimated from residuals. A rank-deficient precision is rejected rather
    than reporting pseudoinverse zeros as certainty. Outputs may be correlated.
    """
    j, h = np.asarray(residual_jacobian, float), np.asarray(output_jacobian, float)
    if j.ndim != 2 or h.ndim != 2 or j.shape[1] != h.shape[1]:
        raise ValueError("Jacobian matrices must share parameter dimension")
    if not np.isfinite(j).all() or not np.isfinite(h).all():
        raise ValueError("Jacobians must be finite")
    if j.shape[1] == 0:
        return np.zeros(h.shape[0])
    _, singular, vt = np.linalg.svd(j, full_matrices=False)
    if len(singular) < j.shape[1] or np.any(
        singular <= singular[0] * max(j.shape) * np.finfo(float).eps
    ):
        raise ValueError("precision is numerically rank deficient")
    return np.linalg.norm((h @ vt.T) / singular, axis=1)
