"""Read-only grid-matched phase controls for full-Jones TV specificity.

Verbatim extract of the frozen `rangtoy.flagging_equivariance` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_equivariance.py at commit
2da566c (now history/python/flagging_equivariance.py),
sha256 c2785e28e8881201244d710360b328f9d466f5c1522b3bd6dcf277005e19345e.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import numpy as np

REFERENCE_HZ = 1283791015.625


PATTERNS = {
    "identity": ([0, 0, 0, 0], [0, 0, 0, 0]),
    "smooth-frequency": ([0, 3, 6, 9], [0, 0, 0, 0]),
    "smooth-time": ([0, 0, 0, 0], [0, 0.2, -0.2, 0.4]),
    "both": ([0, 3, 6, 9], [0, 0.2, -0.2, 0.4]),
}


CASES = (
    "balanced-clean",
    "time-burst-seed101",
    "antenna-local-seed101",
    "time-burst-seed103",
    "antenna-local-seed103",
    "time-burst-seed105",
    "antenna-local-seed105",
)


def phase_factors(times, frequencies, pattern):
    """Frozen scalar station phase, smooth on the existing solved grid."""
    if pattern not in PATTERNS:
        raise ValueError("unknown frozen phase control")
    times, frequencies = np.asarray(times, float), np.asarray(frequencies, float)
    for coordinates in (times, frequencies):
        if (
            coordinates.ndim != 1
            or not coordinates.size
            or not np.isfinite(coordinates).all()
            or np.any(np.diff(coordinates) <= 0)
        ):
            raise ValueError("finite increasing nonempty gain coordinates required")
    delay, drift = (np.asarray(x, float) for x in PATTERNS[pattern])
    span = float(np.ptp(times))
    normalized_time = (times - times[0]) / span if span else np.zeros_like(times)
    phase = (
        2 * np.pi * (frequencies[None, :, None] - REFERENCE_HZ) * delay * 1e-9
        + normalized_time[:, None, None] * drift
    )
    if not np.isfinite(phase).all():
        raise ValueError("phase coordinate overflow")
    return np.exp(1j * phase)
