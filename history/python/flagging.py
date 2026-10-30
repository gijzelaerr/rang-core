"""Flag invariants, full-Jones TV and an interpretable TV-guided policy.

QuartiCal re-solves train the policy in flagging_workflow, without differentiating
through QuartiCal. The expensive TV edge kernel is implemented in Rust.
"""

import ctypes
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import numpy as np

from .projector import _native_library


def require_meerkat_lband(telescopes, frequencies):
    """Enforce this experiment's actual telescope and nominal L-band coverage."""
    names = {str(name).strip().casefold() for name in np.atleast_1d(telescopes)}
    frequencies = np.asarray(frequencies, float)
    if names != {"meerkat"}:
        raise ValueError("this experiment requires MeerKAT observation metadata")
    if (
        frequencies.ndim != 1
        or not len(frequencies)
        or not np.isfinite(frequencies).all()
        or np.any(np.diff(frequencies) <= 0)
        or frequencies.min() < 856e6 - 1
        or frequencies.max() > 1712e6 + 1
    ):
        raise ValueError(
            "this experiment requires MeerKAT L-band channels within 856–1712 MHz"
        )
    return {
        "telescope": "MeerKAT",
        "band": "L",
        "frequency_range_mhz": [
            float(frequencies.min() / 1e6),
            float(frequencies.max() / 1e6),
        ],
    }


def protected_flags(original, original_rows, additional):
    """Original cell and row flags are immutable lower bounds."""
    original = np.asarray(original, bool)
    rows = np.asarray(original_rows, bool)
    additional = np.asarray(additional, bool)
    if original.ndim != 3 or additional.shape != original.shape:
        raise ValueError("flag cubes must have identical row/channel/correlation shape")
    if rows.shape != (len(original),):
        raise ValueError("row flag shape mismatch")
    flags = original | rows[:, None, None] | additional
    return flags, rows | np.all(flags, axis=(1, 2))


def assert_preserved(original, original_rows, flags, rows):
    expected, expected_rows = protected_flags(original, original_rows, flags)
    if not np.array_equal(flags, expected) or np.any(expected_rows & ~rows):
        raise ValueError("observatory flag or full-row protection was violated")


def snapshot_flags(path, flags, rows, **metadata):
    """Create an exclusive, portable snapshot; existing backups cannot be replaced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        np.savez_compressed(stream, FLAG=flags, FLAG_ROW=rows, **metadata)
    return sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _tv_kernel():
    # Load the same checked native library as the other research kernels.
    function = _native_library().rang_gain_tv
    function.argtypes = [ctypes.c_size_t] * 3 + [
        np.ctypeslib.ndpointer(dtype=np.float64, flags=("C_CONTIGUOUS", "ALIGNED")),
        np.ctypeslib.ndpointer(dtype=np.uint8, flags=("C_CONTIGUOUS", "ALIGNED")),
        np.ctypeslib.ndpointer(dtype=np.float64, flags=("C_CONTIGUOUS", "ALIGNED")),
        np.ctypeslib.ndpointer(dtype=np.float64, flags=("C_CONTIGUOUS", "ALIGNED")),
        np.ctypeslib.ndpointer(dtype=np.float64, flags=("C_CONTIGUOUS", "ALIGNED")),
    ]
    function.restype = ctypes.c_int
    return function


def axis_weights(coordinates, gap_factor=3.0):
    """Dimensionless derivatives per typical grid spacing; break large gaps."""
    coordinates = np.asarray(coordinates, float)
    if coordinates.ndim != 1 or not np.isfinite(coordinates).all():
        raise ValueError("finite one-dimensional coordinates required")
    differences = np.diff(coordinates)
    if np.any(differences <= 0):
        raise ValueError("strictly increasing gain coordinates required")
    if not len(differences):
        return np.empty(0)
    spacing = np.median(differences)
    return np.where(differences <= gap_factor * spacing, spacing / differences, 0)


def polar_gauge(gains, valid, reference_antenna=0):
    """Fix the right U(2) gauge of an explicitly unpolarized model.

    G_ref = H U; multiply all antennas by U^H. This preserves Gp Gq^H
    and common physical amplitude. It is inappropriate for a general polarized
    sky: that has a different model stabilizer. Singular reference bins are invalid.
    """
    gains, valid = np.asarray(gains, complex), np.asarray(valid, bool).copy()
    if gains.ndim != 5 or gains.shape[-2:] != (2, 2):
        raise ValueError("full Jones gains must have shape time/frequency/antenna/2/2")
    if valid.shape != gains.shape[:3] or not 0 <= reference_antenna < gains.shape[2]:
        raise ValueError("gain validity/reference shape mismatch")
    safe = np.where(np.isfinite(gains), gains, 0)
    u, singular, vh = np.linalg.svd(safe[:, :, reference_antenna])
    ref_valid = valid[:, :, reference_antenna] & (
        singular[..., -1] > 1e-8 * np.maximum(singular[..., 0], 1e-30)
    )
    valid &= ref_valid[..., None]
    rotation = (u @ vh).conj().swapaxes(-1, -2)
    return safe @ rotation[:, :, None], valid


def gain_tv(gains, valid, times, frequencies, *, scale=1.0):
    """Return fixed-grid masked edges, incident maps, mean temporal/spectral TV.

    Anisotropic TV sums mean temporal and spectral Frobenius edge norms.
    Norms include all four complex Jones entries. Invalid cells never interpolate
    or contribute an edge. A common scale must be retained for all candidates.
    """
    gains = np.asarray(gains, np.complex128)
    valid = np.require(valid, dtype=np.uint8, requirements=["C", "A"])
    if gains.ndim != 5 or gains.shape[-2:] != (2, 2) or valid.shape != gains.shape[:3]:
        raise ValueError("full Jones gain/validity shape mismatch")
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("positive finite fixed gain scale required")
    shape = gains.shape[:3]
    if len(times) != shape[0] or len(frequencies) != shape[1] or min(shape) == 0:
        raise ValueError("gain coordinate shape mismatch")
    packed = np.require(gains / scale, requirements=["C", "A"]).view(np.float64)
    weights = [
        np.require(axis_weights(x), requirements=["C", "A"])
        for x in (times, frequencies)
    ]
    edges = np.empty((2, *shape))
    status = _tv_kernel()(*shape, packed, valid, *weights, edges)
    if status:
        raise ValueError(f"Rust TV kernel failed (status {status})")
    total, count = np.zeros(shape), np.zeros(shape)
    for axis, edge in enumerate(edges):
        finite = np.isfinite(edge)
        value = np.where(finite, edge, 0)
        total += value
        count += finite
        lower = [slice(None)] * 3
        upper = lower.copy()
        lower[axis], upper[axis] = slice(None, -1), slice(1, None)
        total[tuple(upper)] += value[tuple(lower)]
        count[tuple(upper)] += finite[tuple(lower)]
    maps = np.divide(total, count, out=np.zeros(shape), where=count > 0)
    means = [
        float(np.mean(e[np.isfinite(e)])) if np.isfinite(e).any() else 0.0
        for e in edges
    ]
    return {
        "edges": edges,
        "map": maps,
        "time": means[0],
        "frequency": means[1],
        "total": sum(means),
    }


def fixed_support_tv(edges, baseline_edges):
    """Reject missing baseline edges instead of rewarding disappearing solutions."""
    edges, baseline_edges = np.asarray(edges), np.asarray(baseline_edges)
    if edges.shape != baseline_edges.shape:
        raise ValueError("TV grid changed between candidates")
    support = np.isfinite(baseline_edges)
    if not support.any() or not np.isfinite(edges[support]).all():
        return None
    return sum(float(np.mean(e[s])) if s.any() else 0.0 for e, s in zip(edges, support))


def residual_features(residuals, eligible, antenna1, antenna2):
    """Positive robust log-amplitude outliers, estimated per baseline on train only."""
    residuals, eligible = np.asarray(residuals), np.asarray(eligible, bool)
    amplitude = np.sqrt(np.sum(np.abs(residuals) ** 2, axis=-1))
    z = np.zeros_like(amplitude, dtype=float)
    for p, q in sorted(set(zip(antenna1, antenna2))):
        baseline = (antenna1 == p) & (antenna2 == q)
        mask = eligible & baseline[:, None] & np.isfinite(amplitude)
        if not mask.any():
            continue
        log_amplitude = np.log(np.maximum(amplitude, 1e-30))
        median = np.median(log_amplitude[mask])
        deviation = max(1.4826 * np.median(np.abs(log_amplitude[mask] - median)), 0.05)
        z[mask] = np.maximum((log_amplitude[mask] - median) / deviation, 0)
    return z


def policy_mask(outliers, guidance, eligible, *, threshold, tv_weight, max_fraction):
    """TV lowers the residual threshold locally; zero TV provides no encouragement.

    Additional flags can increase or decrease across policies. Observatory flags
    are combined only by protected_flags, never part of policy decisions.
    """
    if not (threshold > 0 and tv_weight >= 0 and 0 <= max_fraction < 1):
        raise ValueError("invalid policy parameters")
    outliers, guidance, eligible = (
        np.asarray(x) for x in (outliers, guidance, eligible)
    )
    if not (outliers.shape == guidance.shape == eligible.shape):
        raise ValueError("policy feature shapes differ")
    eligible = eligible.astype(bool)
    positive = guidance[eligible & np.isfinite(guidance) & (guidance > 0)]
    scale = np.median(positive) if len(positive) else 1.0
    relative = np.clip(np.nan_to_num(guidance / max(scale, 1e-30), nan=0), 0, 5)
    score = outliers * (1 + tv_weight * relative)
    # Independent residual evidence is mandatory even under strong TV guidance.
    proposed = eligible & np.isfinite(score) & (outliers >= 2) & (score > threshold)
    limit = int(np.floor(max_fraction * np.count_nonzero(eligible)))
    indices = np.flatnonzero(proposed)
    if len(indices) > limit:
        order = np.argsort(-score.flat[indices], kind="stable")
        proposed.flat[indices[order[limit:]]] = False
    return proposed


def split_holdout(
    eligible,
    seed,
    validation_fraction=0.1,
    test_fraction=0.1,
    *,
    groups=None,
    minimum_train=2,
):
    """Fixed row-channel splits; all four correlations of a sample stay together."""
    if (
        min(validation_fraction, test_fraction) < 0
        or not 0 <= validation_fraction + test_fraction < 1
    ):
        raise ValueError("holdout fractions must leave training samples")
    rng = np.random.default_rng(seed)
    random = rng.random(np.shape(eligible))
    validation = eligible & (random < validation_fraction)
    test = (
        eligible
        & (random >= validation_fraction)
        & (random < validation_fraction + test_fraction)
    )
    if groups is not None:
        groups = np.asarray(groups)
        if groups.shape != np.shape(eligible) or minimum_train < 1:
            raise ValueError(
                "holdout groups must match samples and retain training data"
            )
        # Reserve support before solving, using only metadata/flags/seed.
        indices = np.flatnonzero(eligible)
        indices = indices[np.argsort(groups.flat[indices], kind="stable")]
        _, start = np.unique(groups.flat[indices], return_index=True)
        for block in np.split(indices, start[1:]):
            reserve = block[
                np.argsort(-random.flat[block], kind="stable")[:minimum_train]
            ]
            validation.flat[reserve] = test.flat[reserve] = False
    return eligible & ~(validation | test), validation, test
