"""Controlled, recoverable RFI injections on real MeerKAT L-band data.

Verbatim extract of the frozen `rangtoy.flagging_injections` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_injections.py at commit
2da566c (now history/python/flagging_injections.py),
sha256 93d151f2b5ea03af2fcd2e00c9fefa45aaefd00bc3acc69c1824d9660f48863d.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

from hashlib import sha256

import numpy as np

PATTERNS = ("narrowband", "time-burst", "antenna-local")


def make_injection(state, pattern, strength, seed, occupancy=0.005):
    """Make a reproducible small time/frequency/station patch on train only.

    Strength is complex visibility amplitude in original inverse-weight units,
    not a claim of measured thermal-noise sigma. All four correlations receive
    the same normalized additive phasor, with native per-correlation weights.
    These simple morphological controls are not a physical RFI simulator.
    """
    if pattern not in PATTERNS:
        raise ValueError("unknown injection pattern")
    if not np.isfinite(strength) or strength <= 0 or not 0 < occupancy < 0.1:
        raise ValueError("positive strength and small occupancy required")
    train = np.asarray(state["train"], dtype=bool)
    flags = state["original_flags"]
    if train.shape != flags.shape[:2]:
        raise ValueError("train mask and original flags have different shapes")
    protected = flags.any(axis=-1) | state["original_rows"][:, None]
    if np.any(train & protected):
        raise ValueError("training mask includes original protected samples")
    if np.any(train & (state["validation"] | state["test"])):
        raise ValueError("training and holdout masks overlap")
    p, q = state["antenna1"], state["antenna2"]
    if np.any(train & (p == q)[:, None]):
        raise ValueError("training contains autocorrelations")
    rng = np.random.default_rng(seed)
    channels = np.flatnonzero(state["window"])
    times = np.unique(state["times"])
    if not len(channels) or not len(times) or not train.any():
        raise ValueError("nonempty eligible data required")
    row_support = p != q
    selected_time = None
    selected_antenna = None
    if pattern == "time-burst":
        available_times = np.unique(state["times"][train.any(axis=1)])
        selected_time = float(rng.choice(available_times))
        row_support &= state["times"] == selected_time
    elif pattern == "antenna-local":
        antennas = np.unique(np.r_[p[train.any(axis=1)], q[train.any(axis=1)]])
        selected_antenna = int(rng.choice(antennas))
        row_support &= (p == selected_antenna) | (q == selected_antenna)
    target = max(1, int(occupancy * train.sum()))
    eligible_per_channel = train[row_support].sum(axis=0)
    width = max(1, int(np.ceil(target / max(eligible_per_channel[channels].mean(), 1))))
    width = min(width, len(channels))
    # Pick a contiguous, sufficiently populated patch, avoiding a fully flagged
    # band island. The choice does not inspect DATA, gains or held-out residuals.
    candidates = np.array(
        [
            i
            for i in range(len(channels) - width + 1)
            if np.all(np.diff(channels[i : i + width]) == 1)
            and eligible_per_channel[channels[i : i + width]].sum() >= target / 2
        ]
    )
    if not len(candidates):
        raise ValueError("no populated contiguous injection patch")
    first = int(rng.choice(candidates))
    selected_channels = channels[first : first + width]
    channel_support = np.zeros(train.shape[1], bool)
    channel_support[selected_channels] = True
    mask = train & row_support[:, None] & channel_support[None]
    if np.any(mask & protected) or np.any(mask & ~train) or not mask.any():
        raise ValueError("injection violated protected/training support")
    weights = state["weights"][mask]
    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("finite positive native weights required")
    # A largely coherent patch, with small sample-to-sample phase jitter.
    phase = rng.uniform(-np.pi, np.pi) + rng.normal(0, 0.15, mask.sum())
    phasor = np.exp(1j * phase)
    if selected_antenna is not None:
        rows = np.nonzero(mask)[0]
        phasor = np.where(p[rows] == selected_antenna, phasor, phasor.conj())
    delta = np.zeros_like(state["data"])
    delta[mask] = strength * phasor[:, None] / np.sqrt(weights)
    metadata = {
        "pattern": pattern,
        "seed": int(seed),
        "strength_inverse_weight_units": float(strength),
        "target_train_occupancy": float(occupancy),
        "actual_train_occupancy": float(mask.sum() / train.sum()),
        "injected_row_channel_count": int(mask.sum()),
        "channels": [int(selected_channels[0]), int(selected_channels[-1] + 1)],
        "time": selected_time,
        "antenna": selected_antenna,
        "delta_abs_jy_quantiles": np.quantile(
            np.abs(delta[mask]), [0, 0.5, 1]
        ).tolist(),
        "mask_sha256": sha256(mask.tobytes()).hexdigest(),
        "truth_used_by_policy": False,
    }
    return mask, delta, metadata


def injection_scores(added, truth, train):
    """Do not mislabel extra flags on an unlabeled real observation as false RFI."""
    added, truth, train = [np.asarray(x, bool) for x in (added, truth, train)]
    if not (added.shape == truth.shape == train.shape):
        raise ValueError("score masks have different shapes")
    if np.any((added | truth) & ~train):
        raise ValueError("score masks extend outside training")
    recovered = int(np.count_nonzero(added & truth))
    outside = int(np.count_nonzero(added & ~truth))
    return {
        "injection_recall": recovered / int(truth.sum()) if truth.any() else None,
        "recovered_injected_samples": recovered,
        "additions_outside_injections": outside,
        "outside_injection_train_fraction": outside / int(train.sum()),
        "added_fraction": float(added.sum() / train.sum()),
        "outside_additions_are_not_proven_false_positives": True,
    }


def reference_distance(state, residuals, diagnostics, clean_state, clean_diagnostics):
    """Compare fixed clean prediction/gain support; never drop unsupported bins."""
    prediction = state["data"] - residuals
    clean_prediction = clean_state["data"] - clean_diagnostics["residuals"]
    clean_valid = clean_diagnostics["tv_valid"]
    valid = diagnostics["tv_valid"]
    unsupported = int(np.count_nonzero(clean_valid & ~valid))
    gain_distance = (
        float(
            np.mean(
                np.abs(
                    diagnostics["gauge_gains"][clean_valid]
                    - clean_diagnostics["gauge_gains"][clean_valid]
                )
                ** 2
            )
        )
        if not unsupported
        else None
    )
    prediction_mse = np.mean(
        np.abs(prediction - clean_prediction) ** 2 * clean_state["weights"], axis=-1
    )
    return {
        "unsupported_clean_gain_bins": unsupported,
        "polar_gauge_gain_mse_to_clean": gain_distance,
        "weighted_prediction_mse_to_clean": {
            split: float(np.mean(prediction_mse[clean_state[split]]))
            if np.isfinite(prediction_mse[clean_state[split]]).all() and not unsupported
            else None
            for split in ("validation", "test")
        },
    }
