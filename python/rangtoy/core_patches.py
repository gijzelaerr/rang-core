"""Measure patch-removal effects and fit a small gain-TV action predictor.

Verbatim extract of the frozen `rangtoy.flagging_actions` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_actions.py at commit
2da566c (now history/python/flagging_actions.py),
sha256 a413c4649e592305547da2311a6fb0e62d51e05b62cc9891061cc428213a15fa.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import numpy as np

from .core_policy import residual_features

FEATURE_NAMES = [
    "log_sample_count",
    "median_residual_z",
    "p95_residual_z",
    "max_residual_z",
    "median_relative_tv",
    "max_relative_tv",
    "mean_log_whitened_amplitude",
    "std_log_whitened_amplitude",
]


def candidate_patches(state, residuals, guidance, count=16, *, seed=29):
    """Disjoint baseline x gain-time x gain-frequency training patches.

    Cover the joint residual/TV score range rather than only high-TV patches.
    Never read validation/test residuals to construct or describe an action.
    """
    if count < 6:
        raise ValueError("at least six actions required for train/validation/test")
    train = state["train"]
    if residuals.shape != state["data"].shape or guidance.shape != train.shape:
        raise ValueError("visibility feature shapes differ")
    time_interval, freq_interval = state["action_intervals"]
    time_bins = np.unique(state["times"], return_inverse=True)[1] // time_interval
    freq_bins = np.arange(train.shape[1]) // freq_interval
    n_ant = len(state["names"])
    baseline = state["antenna1"] * n_ant + state["antenna2"]
    groups = (
        time_bins[:, None] * (freq_bins.max() + 1) + freq_bins[None]
    ) * n_ant**2 + baseline[:, None]
    whitened = residuals * np.sqrt(state["weights"])
    z = residual_features(whitened, train, state["antenna1"], state["antenna2"])
    amplitude = np.sqrt(np.sum(np.abs(whitened) ** 2, axis=-1))
    positive = guidance[train & np.isfinite(guidance) & (guidance > 0)]
    tv_scale = np.median(positive) if len(positive) else 1.0
    relative_tv = guidance / max(tv_scale, 1e-30)
    indices = np.flatnonzero(train)
    indices = indices[np.argsort(groups.flat[indices], kind="stable")]
    _, starts = np.unique(groups.flat[indices], return_index=True)
    patches = []
    for cells in np.split(indices, starts[1:]):
        # A fixed metadata-only size guard excludes negligible/sparse actions.
        if len(cells) < 8:
            continue
        local_z, local_tv = z.flat[cells], relative_tv.flat[cells]
        local_amp = np.log(np.maximum(amplitude.flat[cells], 1e-30))
        features = np.array(
            [
                np.log1p(len(cells)),
                np.median(local_z),
                np.quantile(local_z, 0.95),
                np.max(local_z),
                np.median(local_tv),
                np.max(local_tv),
                np.mean(local_amp),
                np.std(local_amp),
            ]
        )
        if not np.isfinite(features).all():
            continue
        row, channel = np.unravel_index(cells[0], train.shape)
        patches.append(
            {
                "indices": cells,
                "features": features,
                "time_bin": int(time_bins[row]),
                "frequency_bin": int(freq_bins[channel]),
                "antenna1": int(state["antenna1"][row]),
                "antenna2": int(state["antenna2"][row]),
                "score": float(features[2] * (1 + features[4])),
            }
        )
    if len(patches) < count:
        raise ValueError(f"only {len(patches)} eligible disjoint patches, need {count}")
    # Seed controls ties without introducing another feature-selection trial.
    rng = np.random.default_rng(seed)
    permutation = rng.permutation(len(patches))
    order = permutation[
        np.argsort([patches[i]["score"] for i in permutation], kind="stable")
    ]
    chosen = np.rint(np.linspace(0, len(order) - 1, count)).astype(int)
    return [patches[i] for i in order[chosen]]


def split_actions(count, seed=29):
    if count < 6:
        raise ValueError("at least six disjoint actions required")
    order = np.random.default_rng(seed).permutation(count)
    reserved = max(1, count // 5)
    return {
        "train": order[2 * reserved :],
        "validation": order[reserved : 2 * reserved],
        "test": order[:reserved],
    }


def fit_action_model(features, targets, split, *, penalties=(0.1, 1.0, 10.0)):
    """Ridge model predicting normalized fixed-support TV change.

    Standardization uses train actions only, ridge selection validation actions
    only. Missing labels are counted explicitly and never replaced by zero.
    """
    features, targets = np.asarray(features, float), np.asarray(targets, float)
    if (
        features.ndim != 2
        or targets.shape != (len(features),)
        or not np.isfinite(features).all()
        or not penalties
        or not np.isfinite(penalties).all()
        or min(penalties) <= 0
    ):
        raise ValueError("finite features and positive ridge penalties required")
    combined = np.concatenate([np.asarray(split[key]) for key in split])
    if len(combined) != len(features) or not np.array_equal(
        np.sort(combined), np.arange(len(features))
    ):
        raise ValueError("action splits must be a disjoint exhaustive partition")
    valid = np.isfinite(targets)
    train = np.asarray(split["train"])[valid[split["train"]]]
    validation = np.asarray(split["validation"])[valid[split["validation"]]]
    if len(train) < 3 or len(validation) < 1:
        raise ValueError("insufficient supported train/validation action labels")
    center = np.mean(features[train], axis=0)
    scale = np.maximum(np.std(features[train], axis=0), 1e-12)
    design = np.column_stack((np.ones(len(features)), (features - center) / scale))
    regularizer = np.eye(design.shape[1])
    regularizer[0, 0] = 0
    trials = []
    for penalty in penalties:
        coefficients = np.linalg.solve(
            design[train].T @ design[train] + penalty * regularizer,
            design[train].T @ targets[train],
        )
        predictions = design @ coefficients
        mse = float(np.mean((predictions[validation] - targets[validation]) ** 2))
        trials.append((mse, float(penalty), coefficients, predictions))
    mse, penalty, coefficients, predictions = min(trials, key=lambda item: item[:2])
    return {
        "feature_names": FEATURE_NAMES,
        "center": center.tolist(),
        "scale": scale.tolist(),
        "coefficients": coefficients.tolist(),
        "ridge_penalty": penalty,
        "validation_action_mse": mse,
        "tuning": [{"penalty": p, "validation_mse": m} for m, p, _, _ in trials],
        "missing_labels": {
            key: int(np.count_nonzero(~valid[indices]))
            for key, indices in split.items()
        },
    }, predictions


def proposal_from_model(
    patches, predictions, training_actions, shape, train_count, *, max_fraction=0.02
):
    """Choose only model-training actions; untouched test labels stay diagnostic.

    Penalize additional flags and retain the no-change action. A union requires
    a fresh solve because individual counterfactual effects need not add.
    """
    if not np.isfinite(predictions).all() or not 0 <= max_fraction < 1:
        raise ValueError("finite predictions and fraction below one required")
    mask = np.zeros(shape, bool)
    selected = []
    scores = [
        (float(predictions[i]) + 2 * len(patches[i]["indices"]) / train_count, int(i))
        for i in training_actions
    ]
    for score, index in sorted(scores):
        if score >= 0:
            continue
        cells = patches[index]["indices"]
        if np.count_nonzero(mask) + len(cells) > int(max_fraction * train_count):
            continue
        mask.flat[cells] = True
        selected.append(index)
    return mask, selected
