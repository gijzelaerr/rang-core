"""Retrospective TRAIN-only full-Jones deletion response, not an RFI classifier.

Verbatim extract of the frozen `rangtoy.flagging_influence` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_influence.py at commit
2da566c (now history/python/flagging_influence.py),
sha256 a5b8b87aea5d771cd9443505704b4cf7e01416f92cc69b56c94cd5460750a6eb.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import ctypes
from functools import lru_cache

import numpy as np

from .projector import _native_library

INFO = (
    "full_rank",
    "retained_rank",
    "gauge_rank",
    "largest_curvature",
    "smallest_retained_curvature",
    "condition",
    "damping",
    "max_relative_step",
    "baseline_projected_score_norm",
    "gauge_null_relative",
)


REASONS = {
    1: "invalid/numerical block",
    2: "native panic",
    3: "underidentified full curvature",
    4: "retained rank loss",
    5: "non-PSD curvature",
    6: "U2 gauge-null mismatch",
}


@lru_cache(maxsize=1)
def _functions():
    lib = _native_library()
    real = np.ctypeslib.ndpointer(dtype=np.float64, flags=("C_CONTIGUOUS", "ALIGNED"))
    integer = np.ctypeslib.ndpointer(dtype=np.uintp, flags=("C_CONTIGUOUS", "ALIGNED"))
    byte = np.ctypeslib.ndpointer(dtype=np.uint8, flags=("C_CONTIGUOUS", "ALIGNED"))
    jac, normal, step = (
        lib.rang_response_jacobian,
        lib.rang_response_normals,
        lib.rang_response_step,
    )
    jac.argtypes = [real] * 4
    normal.argtypes = (
        [ctypes.c_size_t] * 2 + [real] * 4 + [integer] * 3 + [real] * 2 + [integer]
    )
    step.argtypes = [real] * 5 + [byte] + [real] * 2
    for fn in (jac, normal, step):
        fn.restype = ctypes.c_int
    return jac, normal, step


def _complex(value, shape):
    array = np.require(value, dtype=np.complex128, requirements=["C", "A"])
    if array.shape != shape:
        raise ValueError(f"complex shape {shape} required")
    return array


def jones_jacobian(gp, gq, model):
    """Eight Re/Im visibility rows × sixteen local p-then-q parameters."""
    inputs = [_complex(x, (2, 2)).view(np.float64).ravel() for x in (gp, gq, model)]
    if not all(np.isfinite(x).all() for x in inputs):
        raise ValueError("finite Jones matrices required")
    output = np.empty((8, 16))
    if _functions()[0](*inputs, output):
        raise RuntimeError("native Jones Jacobian failed")
    return output


def training_normals(gains, models, residuals, weights, p, q, bin_ids):
    """Caller supplies TRAIN samples only; weights are never replaced/scaled."""
    gains = np.require(gains, dtype=np.complex128, requirements=["C", "A"])
    if gains.ndim != 4 or gains.shape[1:] != (4, 2, 2) or not len(gains):
        raise ValueError("gain bins × four stations × 2×2 required")
    ids = []
    for value in (p, q, bin_ids):
        raw = np.asarray(value)
        if raw.ndim != 1 or raw.dtype.kind not in "iu" or np.any(raw < 0):
            raise ValueError("nonnegative integer sample indices required")
        ids.append(np.require(raw, dtype=np.uintp, requirements=["C", "A"]))
    p, q, bins = ids
    n = len(bins)
    model, residual = [_complex(x, (n, 2, 2)) for x in (models, residuals)]
    weight = np.require(weights, dtype=np.float64, requirements=["C", "A"])
    if (
        p.shape != bins.shape
        or q.shape != bins.shape
        or weight.shape != (n, 4)
        or np.any(p >= 4)
        or np.any(q >= 4)
        or np.any(p == q)
        or np.any(bins >= len(gains))
    ):
        raise ValueError("sample/baseline/bin shape or range mismatch")
    if (
        not np.isfinite(model).all()
        or not np.isfinite(residual).all()
        or not np.isfinite(weight).all()
        or np.any(weight <= 0)
    ):
        raise ValueError(
            "finite samples and positive native four-correlation weights required"
        )
    h, b, counts = (
        np.zeros((len(gains), 32, 32)),
        np.zeros((len(gains), 32)),
        np.zeros(len(gains), dtype=np.uintp),
    )
    status = _functions()[1](
        n,
        len(gains),
        gains.view(np.float64),
        model.view(np.float64),
        residual.view(np.float64),
        weight,
        p,
        q,
        bins,
        h,
        b,
        counts,
    )
    if status:
        raise RuntimeError(f"native TRAIN normals failed: {status}")
    return h, b, counts


def anchored_response(full_h, full_b, drop_h, drop_b, gains, active):
    """Return a horizontal gain delta or a structured missing prediction."""
    arrays = []
    for value, shape in zip(
        (full_h, full_b, drop_h, drop_b),
        ((32, 32), (32,), (32, 32), (32,)),
        strict=True,
    ):
        raw = np.asarray(value)
        if np.iscomplexobj(raw) or raw.shape != shape or not np.isfinite(raw).all():
            raise ValueError("finite real 32D normal block required")
        arrays.append(np.require(raw, dtype=np.float64, requirements=["C", "A"]))
    active = np.asarray(active)
    if active.dtype != np.bool_ or active.shape != (4,):
        raise ValueError("four bool active-station values required")
    gain = _complex(gains, (4, 2, 2)).copy()
    if not np.isfinite(gain[active]).all():
        raise ValueError("finite active-station gains required")
    gain[~active] = 0
    delta, info = np.zeros(32), np.full(10, np.nan)
    status = _functions()[2](
        *arrays,
        gain.view(np.float64),
        np.require(active, dtype=np.uint8, requirements=["C", "A"]),
        delta,
        info,
    )
    audit = {
        key: float(value) if np.isfinite(value) else None
        for key, value in zip(INFO, info, strict=True)
    }
    trust = status == 0 and audit["max_relative_step"] <= 0.1
    return {
        "delta": delta.view(np.complex128).reshape(4, 2, 2) if trust else None,
        "diagnostics": audit,
        "guard_pass": trust,
        "reason": None
        if trust
        else REASONS.get(status, "relative station step exceeds 0.1"),
        "native_status": status,
    }


def _npz(path, keys=None):
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in (archive.files if keys is None else keys)}


def _maps(state):
    time_map = np.unique(state["times"], return_inverse=True)[1] // 2
    return time_map, np.arange(len(state["frequencies"])) // 32


def _predict(state, gains, mask):
    rows, channels = np.where(mask)
    tm, fm = _maps(state)
    gp = gains[tm[rows], fm[channels], state["antenna1"][rows]]
    gq = gains[tm[rows], fm[channels], state["antenna2"][rows]]
    prediction = (
        gp
        @ state["model"][rows, channels].reshape(-1, 2, 2)
        @ gq.conj().swapaxes(-1, -2)
    ).reshape(-1, 4)
    return rows, channels, prediction


def _training_bundle(state, baseline):
    train = state["train"]
    shape = state["data"].shape[:2]
    if (
        state["data"].shape != (*shape, 4)
        or state["model"].shape != (*shape, 4)
        or state["weights"].shape != (*shape, 4)
    ):
        raise ValueError("four-correlation DATA/model/native weights required")
    if (
        state["original_flags"].dtype != np.bool_
        or state["original_flags"].shape != (*shape, 4)
        or state["original_rows"].dtype != np.bool_
        or state["original_rows"].shape != (shape[0],)
        or state["window"].dtype != np.bool_
        or state["window"].shape != (shape[1],)
    ):
        raise ValueError("bool original flags/rows/window shapes required")
    splits = [state[key] for key in ("train", "validation", "test")]
    if any(x.dtype != np.bool_ or x.shape != shape for x in splits) or any(
        np.any(splits[i] & splits[j]) for i in range(3) for j in range(i)
    ):
        raise ValueError("bool disjoint TRAIN/validation/test shapes required")
    protected = (
        state["original_flags"].any(axis=2)
        | state["original_rows"][:, None]
        | (state["antenna1"] == state["antenna2"])[:, None]
        | ~state["window"][None, :]
    )
    if np.any(train & protected) or not train.any():
        raise ValueError("TRAIN overlaps original flags/rows/autos/window")
    rows, channels, prediction = _predict(state, baseline["gains"], train)
    tm, fm = _maps(state)
    valid = (
        baseline["gain_valid"][tm[rows], fm[channels], state["antenna1"][rows]]
        & baseline["gain_valid"][tm[rows], fm[channels], state["antenna2"][rows]]
    )
    if not valid.all():
        raise ValueError("TRAIN baseline gain support missing")
    models = state["model"][rows, channels].reshape(-1, 2, 2)
    if (
        not np.isfinite(models).all()
        or not np.array_equal(models[:, 0, 0], models[:, 1, 1])
        or np.any(models[:, 0, 1] != 0)
        or np.any(models[:, 1, 0] != 0)
    ):
        raise ValueError("scalar unpolarized TRAIN model required for U2 gauge")
    residuals = (state["data"][rows, channels] - prediction).reshape(-1, 2, 2)
    return {
        "gains": baseline["gains"].reshape(-1, 4, 2, 2),
        "models": models,
        "residuals": residuals,
        "weights": state["weights"][rows, channels],
        "p": state["antenna1"][rows],
        "q": state["antenna2"][rows],
        "bin_ids": tm[rows] * baseline["gains"].shape[1] + fm[channels],
        "flat_indices": np.flatnonzero(train),
    }
