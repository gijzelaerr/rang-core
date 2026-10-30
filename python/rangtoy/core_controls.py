"""Run unmodified CARACAL Tricolour strategies on protected diagnostic copies.

Verbatim extract of the frozen `rangtoy.flagging_caracal` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_caracal.py at commit
2da566c (now history/python/flagging_caracal.py),
sha256 e1d946860f9069dc5314e5c9baf3c89c6aad66bc28edfee87733c39d9aa04fa8.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import numpy as np


def training_proposal(state, native_flags):
    """Couple correlations, importing additions only on eligible train samples."""
    native_flags = np.asarray(native_flags)
    if native_flags.dtype != np.bool_ or native_flags.shape != state["data"].shape:
        raise ValueError("native flags require the actual bool correlation shape")
    return state["train"] & native_flags.any(axis=-1)


def score_control(metrics, fixed_tv, baseline):
    """Diagnostic objective only; test losses never influence admissibility."""
    val, val0 = metrics["losses"]["validation"], baseline["losses"]["validation"]
    tv_valid = fixed_tv is not None and np.isfinite(fixed_tv) and fixed_tv >= 0
    baseline_valid = np.isfinite(baseline["tv"]) and baseline["tv"] >= 0
    fraction = metrics["added_fraction"]
    fraction_valid = np.isfinite(fraction) and fraction >= 0
    val_valid = (
        val is not None
        and val0 is not None
        and np.isfinite([val, val0]).all()
        and min(val, val0) >= 0
    )
    reasons = []
    if not tv_valid:
        reasons.append("fixed TV support lost")
    if not baseline_valid:
        reasons.append("invalid baseline TV")
    if not fraction_valid or fraction > 0.02:
        reasons.append("2% training flag budget exceeded")
    if not val_valid or val > 1.01 * val0:
        reasons.append("validation unavailable or exceeds 1% degradation")
    objective = (
        fixed_tv / max(baseline["tv"], 1e-30)
        + 2 * metrics["added_fraction"]
        + 0.25 * val / max(val0, 1e-30)
        if tv_valid and baseline_valid and fraction_valid and val_valid
        else None
    )
    return {"objective": objective, "guard_reasons": reasons, "guard_pass": not reasons}
