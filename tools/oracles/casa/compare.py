"""Host side of the O-CASA oracle: the seed-7 split and the comparisons to rang.

Runs in the worktree venv (rangtoy importable). Read-only use of
`rangtoy.core_campaign` (research/o-casa.md, "Comparisons to rang").
  compare.py split <run>     write <run>/split.npz from build_state on the archived tiles
  compare.py compare <run>   CASA applied products and held-out MSE against the core
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from rangtoy import core_campaign as cc

ARCHIVED_ORIGINAL = {
    "validation": 0.27528890864724964,
    "test": 0.27600925040826674,
    "gains_sha256": "4ed2aa89a68aad5bce6f48a62da4071f948502e043c302812ceda094440d4aa8",
    "split": {"train": 94047, "validation": 11742, "test": 11767},
}
NAMES = ["m000", "m001", "m002", "m003"]


def state(chan_freq=None):
    arrays, _ = cc._section6().ingest()
    if chan_freq is None:  # the split does not use frequencies
        chan_freq = np.arange(arrays["DATA"].shape[1], dtype=float)
    extra = {"antenna_names": NAMES, "chan_freq": np.asarray(chan_freq, float)}
    return arrays, cc.build_state(arrays, extra)


def split(run):
    run = Path(run)
    started = time.perf_counter()
    arrays, st = state()
    counts = {k: int(st[k].sum()) for k in ("train", "validation", "test")}
    np.savez(
        run / "split.npz",
        validation=st["validation"],
        test=st["test"],
        train=st["train"],
        ANTENNA1=arrays["ANTENNA1"],
        ANTENNA2=arrays["ANTENNA2"],
        TIME=arrays["TIME"],
    )
    report = {
        "counts": counts,
        "matches_core_k": counts == ARCHIVED_ORIGINAL["split"],
        "validation_sha256": cc.array_sha256(st["validation"]),
        "test_sha256": cc.array_sha256(st["test"]),
        "seconds": time.perf_counter() - started,
    }
    cc.write_json(run / "split.json", report)
    print(json.dumps(report))
    return 0 if report["matches_core_k"] else 1


def bins(times, nchan):
    time_bins = np.unique(times, return_inverse=True)[1] // cc.GRID[0]
    freq_bins = np.arange(nchan) // cc.GRID[1]
    return time_bins, freq_bins


def core_prediction(st, gains, valid):
    """V = G_p M G_q^H per cell with the core's 2x2 gains; invalid where a gain is."""
    p, q = st["antenna1"], st["antenna2"]
    tb, fb = bins(st["times"], st["data"].shape[1])
    gp = gains[tb[:, None], fb[None, :], p[:, None]]
    gq = gains[tb[:, None], fb[None, :], q[:, None]]
    ok = (
        valid[tb[:, None], fb[None, :], p[:, None]]
        & valid[tb[:, None], fb[None, :], q[:, None]]
    )
    m = st["model"].astype(np.complex128).reshape(*st["model"].shape[:2], 2, 2)
    pred = gp @ m @ np.conj(np.swapaxes(gq, -1, -2))
    return pred.reshape(*pred.shape[:2], 4), ok


def mse(data, pred, weights, cells, ok):
    """Mean over cells of the correlation-mean w|r|^2 (core-k-luno-campaign.md)."""
    use = cells & ok
    r = data - pred
    per_cell = (weights * np.abs(r) ** 2).mean(axis=-1)
    return (
        float(per_cell[use].mean()) if use.any() else None,
        int(use.sum()),
        int((cells & ~ok).sum()),
    )


def casa_products(export):
    """P = DATA / CORRECTED per correlation; valid where unflagged and finite."""
    data = export["DATA"].astype(np.complex128)
    corrected = export["CORRECTED_DATA"].astype(np.complex128)
    flag = export["FLAG"]
    with np.errstate(divide="ignore", invalid="ignore"):
        product = data / corrected
    ok = ~flag & np.isfinite(product) & (np.abs(corrected) > 0)
    return product, ok


def compare_products(p_casa, ok_casa, p_core, ok_core, a1, a2):
    out = {}
    for corr, label in ((0, "XX"), (3, "YY")):
        use = ok_casa[..., corr] & ok_core
        ratio = p_casa[..., corr][use] / p_core[..., corr][use]
        amp = np.abs(np.abs(ratio) - 1)
        phase = np.degrees(np.abs(np.angle(ratio)))
        entry = {
            "cells": int(use.sum()),
            "amp_rel_diff_median": float(np.median(amp)),
            "amp_rel_diff_p95": float(np.percentile(amp, 95)),
            "amp_ratio_median": float(np.median(np.abs(ratio))),
            "phase_diff_deg_median": float(np.median(phase)),
            "phase_diff_deg_p95": float(np.percentile(phase, 95)),
            "per_baseline": {},
        }
        for p in range(4):
            for q in range(p + 1, 4):
                rows = (a1 == p) & (a2 == q)
                sub = use & rows[:, None]
                if not sub.any():
                    continue
                r = p_casa[..., corr][sub] / p_core[..., corr][sub]
                entry["per_baseline"][f"{NAMES[p]}-{NAMES[q]}"] = {
                    "cells": int(sub.sum()),
                    "amp_rel_diff_median": float(np.median(np.abs(np.abs(r) - 1))),
                    "phase_diff_deg_median": float(
                        np.median(np.degrees(np.abs(np.angle(r))))
                    ),
                }
        out[label] = entry
    return out


def compare(run):
    run = Path(run)
    started = time.perf_counter()
    arrays, st = state(np.load(run / "export-c.npz")["CHAN_FREQ"])
    core = cc.solve_arm(st, np.zeros(st["data"].shape[:2], bool), "original")
    gains = core["diagnostics"]["gains"]
    valid = core["diagnostics"]["gain_valid"]
    losses = core["metrics"]["losses"]
    pred_core, ok_core = core_prediction(st, gains, valid)
    data = st["data"].astype(np.complex128)
    weights = st["weights"].astype(np.float64)
    report = {
        "core": {
            "gains_sha256": cc.array_sha256(gains),
            "gains_match_core_k_archive": cc.array_sha256(gains)
            == ARCHIVED_ORIGINAL["gains_sha256"],
            "losses": losses,
            "losses_match_archive": all(
                abs(losses[k] / ARCHIVED_ORIGINAL[k] - 1) < 1e-9
                for k in ("validation", "test")
            ),
        },
        "arms": {},
    }
    numpy_core = {
        k: mse(data, pred_core, weights, st[k], ok_core)[0]
        for k in ("validation", "test")
    }
    report["core"]["numpy_losses"] = numpy_core
    report["core"]["numpy_matches_core"] = all(
        abs(numpy_core[k] / losses[k] - 1) < 1e-6 for k in numpy_core
    )
    for arm in ("c", "ch", "sh"):
        path = run / f"export-{arm}.npz"
        if not path.exists():
            report["arms"][arm] = {"available": False}
            continue
        ex = np.load(path)
        for c in ("ANTENNA1", "ANTENNA2", "TIME"):
            if not np.array_equal(ex[c], arrays[c]):
                raise SystemExit(f"row gate failed for {arm}: {c}")
        product, ok = casa_products(ex)
        model = ex["MODEL_DATA"].astype(np.complex128)
        pred = product * model
        ok_cell = ok.all(axis=-1)
        entry = {"available": True}
        for k in ("validation", "test", "train"):
            value, used, unavailable = mse(data, pred, weights, st[k], ok_cell)
            core_subset, _, _ = mse(data, pred_core, weights, st[k] & ok_cell, ok_core)
            entry[f"mse_{k}"] = value
            entry[f"cells_{k}"] = used
            entry[f"unavailable_{k}"] = unavailable
            entry[f"core_mse_{k}_same_cells"] = core_subset
            entry[f"ratio_{k}_casa_over_core"] = (
                (value / core_subset) if value and core_subset else None
            )
        # Diagonal-only core prediction: what the core would predict without its off-diagonal term.
        diag_gains = gains.copy()
        diag_gains[..., 0, 1] = 0
        diag_gains[..., 1, 0] = 0
        pred_diag, _ = core_prediction(st, diag_gains, valid)
        entry["core_diagonal_only_mse_test_same_cells"] = mse(
            data, pred_diag, weights, st["test"] & ok_cell, ok_core
        )[0]
        # The test MSE split into parallel (XX, YY) and cross (XY, YX) hands.
        test = st["test"] & ok_cell
        for hands, corrs in (("parallel", [0, 3]), ("cross", [1, 2])):
            for label, prediction, valid_cells in (
                ("casa", pred, ok_cell),
                ("core", pred_core, ok_core),
                ("core_diagonal_only", pred_diag, ok_core),
            ):
                entry[f"mse_test_{hands}_{label}"] = mse(
                    data[..., corrs],
                    prediction[..., corrs],
                    weights[..., corrs],
                    test,
                    valid_cells,
                )[0]
        # Products from the core gains directly (diagonal): g_pX g_qX*, g_pY g_qY*.
        tb, fb = bins(st["times"], st["data"].shape[1])
        gp = gains[tb[:, None], fb[None, :], st["antenna1"][:, None]]
        gq = gains[tb[:, None], fb[None, :], st["antenna2"][:, None]]
        p_core = np.zeros_like(product)
        p_core[..., 0] = gp[..., 0, 0] * np.conj(gq[..., 0, 0])
        p_core[..., 3] = gp[..., 1, 1] * np.conj(gq[..., 1, 1])
        entry["products_vs_core"] = compare_products(
            product, ok, p_core, ok_core, st["antenna1"], st["antenna2"]
        )
        report["arms"][arm] = entry
    report["seconds"] = time.perf_counter() - started
    cc.write_json(run / "compare.json", report)
    print(
        json.dumps(
            {
                k: report["core"][k]
                for k in (
                    "gains_match_core_k_archive",
                    "losses_match_archive",
                    "numpy_matches_core",
                )
            }
        )
    )
    return 0


def main(argv):
    if argv[1] == "split":
        return split(argv[2])
    if argv[1] == "compare":
        return compare(argv[2])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
